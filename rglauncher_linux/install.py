"""Verified per-user integration. Activation is explicit and session-scoped.

The installer owns only its wrappers, desktop entries, icon links and units.
Specialized local audio/calculator/network scripts and unrelated profiles remain
untouched. Every replacement is backed up and journaled for guarded restoration.
"""
from __future__ import annotations

from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import stat
import struct
import subprocess
import tempfile
import time
import uuid

from cryptography.hazmat.primitives import serialization
from .paths import config_dir, data_dir, state_dir
from .update import UpdateConfig, Updater, UpdateError

WRAPPERS = ("rglauncher", "rglauncher-shelf", "rofi-launcher", "hypr-windows", "waybar")
SESSION_ENV = ("WAYLAND_DISPLAY", "HYPRLAND_INSTANCE_SIGNATURE", "DISPLAY", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS")
REQUIRED_FILES = (
    "LICENSE", "THIRD_PARTY_NOTICES", "pyproject.toml",
    *("rglauncher_linux/" + name + ".py" for name in
      ("__init__", "cli", "paths", "shelf", "settings", "editor", "native", "install", "update")),
    *("bin/" + name for name in
      ("rglauncher", "rglauncher-shelf", "rofi-launcher", "hypr-windows", "calc-menu", "audio-menu", "wifi-menu", "bt-menu",
       "_aether_score.py", "_aether_desktop.py", "_aether_material.py", "_aether_surfaces.py", "_aether_tokens.json",
       "_cyber_theme.py", "_cyber_gtk.py", "_cyber_particles.py", "_wifi_secondary.py", "_scarlett.py", "_audioeq_ui.py", "_audioeq.py", "_audiobus.py")),
    "share/instrument-score-aether/tokens.json", "share/waybar/config.jsonc", "share/waybar/style.css",
    "share/waybar/waybar", "share/waybar/backend.json", "share/waybar/LICENSE.Waybar",
    "share/icons/aether-score/index.theme", "share/icons/aether-score-light/index.theme",
    "share/vscode/rglauncher-aether.vsix", "share/hyprland/hyprland.lua", "share/hyprland/snap-layout.lua", "share/hyprland/window-navigation.lua",
    "systemd/rglauncher-update.service", "systemd/rglauncher-update.timer",
    "systemd/rglauncher-shelf@.service", "systemd/rglauncher-session@.target",
)
REQUIRED_ACTIONS = {"apps", "windows", "files", "terminal", "calc", "audio", "wifi", "bluetooth", "settings"}


class InstallError(RuntimeError):
    pass


def _path(path):
    path = Path(path).expanduser()
    if not path.is_absolute() or any(ord(c) < 32 for c in str(path)):
        raise InstallError("Installation roots must be absolute paths without control characters")
    return path.resolve()


def _atomic(path, content, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode()


def _fingerprint(path):
    if path.is_symlink():
        return {"type": "symlink", "target": os.readlink(path)}
    if not path.exists():
        return {"type": "absent"}
    info = path.lstat()
    if stat.S_ISREG(info.st_mode):
        return {"type": "file", "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "mode": stat.S_IMODE(info.st_mode)}
    if stat.S_ISDIR(info.st_mode):
        return {"type": "directory"}
    raise InstallError("Refusing to replace a special filesystem object")


class _Receipt:
    def __init__(self, state, release):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
        self.directory = state / "install-backups" / stamp
        self.directory.mkdir(parents=True, mode=0o700)
        self.path = self.directory / "receipt.json"
        self.value = {"schema": 1, "release": str(release), "status": "preparing",
                      "manifest": str(self.path), "changes": [], "preserved": [], "errors": []}
        self.save()

    def save(self):
        _atomic(self.path, _json_bytes(self.value), 0o600)

    def _before(self, path):
        before = _fingerprint(path)
        record = {"path": str(path), "before": before, "after": None}
        if before["type"] == "file":
            backup = self.directory / "files" / str(len(self.value["changes"]))
            backup.parent.mkdir(exist_ok=True)
            shutil.copy2(path, backup)
            record["backup"] = str(backup)
        elif before["type"] == "directory":
            # Same-filesystem relocation preserves the actual directory, including
            # nested links, and never follows/deletes an external symlink target.
            backup = path.with_name("." + path.name + ".rglauncher-before-" + uuid.uuid4().hex)
            record["backup"] = str(backup)
        self.value["changes"].append(record)
        self.save()
        return record

    def file(self, path, content, mode=0o644, preserve=False):
        path = Path(path)
        if preserve and (path.exists() or path.is_symlink()):
            self.value["preserved"].append(str(path))
            return False
        desired = {"type": "file", "sha256": hashlib.sha256(content).hexdigest(), "mode": mode}
        if _fingerprint(path) == desired:
            return False
        record = self._before(path)
        if record["before"]["type"] == "directory":
            raise InstallError("Refusing to replace a directory with a generated file")
        _atomic(path, content, mode)
        record["after"] = desired
        self.save()
        return True

    def symlink(self, path, target):
        path, target = Path(path), str(target)
        desired = {"type": "symlink", "target": target}
        if _fingerprint(path) == desired:
            return False
        record = self._before(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if record["before"]["type"] == "directory":
            os.rename(path, record["backup"])
            self.save()
        temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex)
        try:
            temporary.symlink_to(target)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        record["after"] = desired
        self.save()
        return True


def systemd_quote(value, *, execute=False):
    """One systemd word; ExecStart alone performs dollar expansion."""
    value = str(value)
    if any(ord(c) < 32 for c in value):
        raise InstallError("Control characters are not allowed in unit paths")
    value = value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    if execute:
        value = value.replace("$", "$$")
    return '"' + value + '"'


def _environment_file(values):
    def quote(value):
        if "\x00" in value or "\n" in value or "\r" in value:
            raise InstallError("Invalid session environment value")
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return ("# Only the current Wayland session's required display/bus values.\n" +
            "\n".join(key + "=" + quote(value) for key, value in values.items()) + "\n").encode()


def _desktop_quote(value):
    # Desktop Entry string unescaping happens before Exec argument unescaping.
    value = str(value).replace("%", "%%")
    value = value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")
    return '"' + value.replace("\\", "\\\\") + '"'


def _desktop_entry(text, executable):
    output = []
    for line in text.splitlines():
        if line.startswith("Exec=rglauncher") and (line == "Exec=rglauncher" or line.startswith("Exec=rglauncher ")):
            # GLib checks the first executable before expanding %% field codes.
            # Put the escaped absolute wrapper in argv instead; /usr/bin/env
            # remains a fixed executable even when HOME contains a literal %.
            line = "Exec=/usr/bin/env " + _desktop_quote(executable) + line[len("Exec=rglauncher"):]
        elif line == "TryExec=rglauncher":
            line = "TryExec=" + str(executable)
        output.append(line)
    return ("\n".join(output) + "\n").encode()


def _wrapper(name, root, config_home, data_home, state_home, native_environment):
    environment = {"XDG_CONFIG_HOME": str(config_home), "XDG_DATA_HOME": str(data_home),
                   "XDG_STATE_HOME": str(state_home), **native_environment}
    common = f'''#!/usr/bin/env python3
# Managed RGLauncher entry point; resolve the release ONCE per invocation.
import os
from pathlib import Path
import runpy
import sys
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.environ.update({environment!r})
base = Path({str(root)!r})
current = base / "current"
if not current.is_symlink():
    raise SystemExit("RGLauncher has no verified current release")
release = current.resolve(strict=True)
if release.parent != (base / "releases").resolve() or not release.is_dir():
    raise SystemExit("RGLauncher release path is outside managed releases")
os.environ["RGL_RELEASE_ROOT"] = str(release)
'''
    if name == "rglauncher":
        body = 'from rglauncher_linux.cli import main\nraise SystemExit(main())\n'
    elif name == "rglauncher-shelf":
        body = 'from rglauncher_linux.shelf import main\nraise SystemExit(main())\n'
    elif name in ("rofi-launcher", "hypr-windows"):
        body = f'runpy.run_path(str(release / "bin" / {name!r}), run_name="__main__")\n'
    else:
        body = '''backend = release / "share/waybar/waybar"
if not backend.is_file() or not os.access(backend, os.X_OK):
    backend = Path("/usr/bin/waybar")
if backend.resolve() == Path(sys.argv[0]).resolve():
    raise SystemExit("Refusing a recursive Waybar backend")
os.environ["RGL_WAYBAR_BINARY"] = str(backend)
if backend == release / "share/waybar/waybar":
    os.environ["WAYBAR_HYPRLAND_LUA"] = "1"
if len(sys.argv) > 1:
    os.execv(str(backend), [str(backend), *sys.argv[1:]])
try:
    from rglauncher_linux.install import start_session
    result = start_session(release, base, Path(os.environ["XDG_CONFIG_HOME"]),
                           Path(os.environ["XDG_DATA_HOME"]), Path(os.environ["XDG_STATE_HOME"]),
                           cleanup=False)
    if result.get("status") == "running":
        raise SystemExit(0)
except (ImportError, RuntimeError, OSError):
    pass
from rglauncher_linux.shelf import main
raise SystemExit(main(["run"]))
'''
    pinned = f'''import os
from pathlib import Path
import runpy
import sys
sys.dont_write_bytecode = True
release = Path(os.environ["RGL_RELEASE_ROOT"])
base = Path({str(root)!r})
sys.argv.pop(0)
sys.path[:0] = [str(release), str(release / "bin")]
''' + body
    # exec makes the chosen release part of the process's *initial* environment,
    # observable to the session-scoped readiness check through /proc/environ.
    # The second stage never consults current, even if an update races the exec.
    return (common + f'os.execv(sys.executable, [sys.executable, "-B", "-c", {pinned!r}, str(Path(__file__).absolute()), *sys.argv[1:]])\n').encode()


def _required_payload(release):
    missing = [name for name in REQUIRED_FILES if not (release / name).is_file() or (release / name).is_symlink()]
    actions = set()
    for entry in (release / "share/applications").glob("*.desktop"):
        for line in entry.read_text().splitlines():
            words = line.removeprefix("Exec=").split()
            if line.startswith("Exec=") and len(words) >= 2 and words[0] == "rglauncher":
                actions.add(words[1])
    missing += ["desktop action " + action for action in sorted(REQUIRED_ACTIONS - actions)]
    if missing:
        raise InstallError("Release is missing required integration assets: " + ", ".join(missing))


def _run(arguments, **kwargs):
    try:
        result = subprocess.run(arguments, capture_output=True, text=True, timeout=15, **kwargs)
        return {"ok": result.returncode == 0, "returncode": result.returncode,
                "stdout": result.stdout.strip(), "stderr": result.stderr.strip()[-1000:]}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"ok": False, "returncode": None, "stdout": "", "stderr": str(error)}


def _process(pid):
    try:
        base = Path("/proc") / str(pid)
        if base.stat().st_uid != os.getuid():
            return None
        command = (base / "comm").read_text().strip()
        start = (base / "stat").read_text().rsplit(")", 1)[1].split()[19]
        environment = {}
        for field in (base / "environ").read_bytes().split(b"\x00"):
            key, separator, value = field.partition(b"=")
            if separator and key in (b"HYPRLAND_INSTANCE_SIGNATURE", b"RGL_RELEASE_ROOT"):
                environment[key.decode()] = value.decode(errors="replace")
        return {"pid": int(pid), "command": command, "start": start, **environment}
    except (OSError, ValueError, IndexError):
        return None


def _session_bars(signature):
    result = []
    for path in Path("/proc").iterdir():
        if path.name.isdigit():
            process = _process(path.name)
            if process and process["command"] == "waybar" and process.get("HYPRLAND_INSTANCE_SIGNATURE") == signature:
                result.append(process)
    return result


def _terminate_bars(processes, signature, release):
    result = []
    for old in processes:
        current = _process(old["pid"])
        if current != old or current.get("HYPRLAND_INSTANCE_SIGNATURE") != signature or current.get("RGL_RELEASE_ROOT") == str(release):
            continue
        try:
            os.kill(old["pid"], signal.SIGTERM)
            result.append({"pid": old["pid"], "status": "termination-requested"})
        except ProcessLookupError:
            result.append({"pid": old["pid"], "status": "already-exited"})
        except OSError as error:
            result.append({"pid": old["pid"], "status": "failed", "error": str(error)})
    return result


def _shelf_status(path, expected_pid):
    """Ask only the owned shelf socket, confirming its process credentials."""
    info = path.lstat()
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
        raise InstallError("Shelf control socket is not owned by this user")
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(.3)
        client.connect(str(path))
        pid, uid, _gid = struct.unpack("3i", client.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        if uid != os.getuid() or pid != expected_pid:
            raise InstallError("Shelf control socket process did not match its service")
        client.sendall(b'{"command":"status"}')
        content = bytearray()
        while len(content) <= 65536:
            chunk = client.recv(min(4096, 65537 - len(content)))
            if not chunk:
                break
            content.extend(chunk)
        if len(content) > 65536:
            raise InstallError("Shelf control response exceeds its limit")
        return json.loads(content)


def _wait_shelf(release, signature, runtime_dir, pid, *, timeout=5):
    """Require live same-release output children twice before removing old bars."""
    deadline, previous, identity = time.monotonic() + timeout, None, None
    error = "Shelf did not report any ready output children"
    while time.monotonic() < deadline:
        controller = _process(pid)
        if controller:
            if identity is not None and controller["start"] != identity:
                return {"ok": False, "reason": "Shelf service process identity changed during startup"}
            identity = controller["start"]
            for key, expected in (("HYPRLAND_INSTANCE_SIGNATURE", signature), ("RGL_RELEASE_ROOT", str(release))):
                if key in controller and controller[key] != expected:
                    return {"ok": False, "reason": "Shelf service process identity did not match the selected release/session"}
        if not controller or controller.get("HYPRLAND_INSTANCE_SIGNATURE") != signature or controller.get("RGL_RELEASE_ROOT") != str(release):
            # Type=simple can become active while /usr/bin/env or the stable
            # Python wrapper is still preparing its pinned exec. Missing initial
            # environment is transient; a conflicting identity is never trusted.
            error, previous = "Shelf wrapper has not finished entering the selected release", None
            time.sleep(min(.2, max(0, deadline - time.monotonic())))
            continue
        try:
            response = _shelf_status(runtime_dir / "shelf.sock", pid)
            outputs = response.get("outputs")
            if not isinstance(outputs, dict) or not outputs:
                raise InstallError("Shelf has no ready output children")
            children = {}
            for output, value in outputs.items():
                child_pid = value.get("pid") if isinstance(value, dict) else None
                if not isinstance(output, str) or type(child_pid) is not int or child_pid <= 0:
                    raise InstallError("Shelf returned an invalid output process")
                child = _process(child_pid)
                if not child or child["command"] != "waybar" or child.get("HYPRLAND_INSTANCE_SIGNATURE") != signature or child.get("RGL_RELEASE_ROOT") != str(release):
                    raise InstallError("Shelf output process is unavailable or belongs to another release/session")
                children[output] = child
            snapshot = {"controller": controller, "children": children}
            if snapshot == previous:
                return {"ok": True, "outputs": {name: value["pid"] for name, value in children.items()}, "stable_for_seconds": .2}
            previous = snapshot
        except (OSError, ValueError, TypeError, InstallError) as failure:
            error, previous = str(failure), None
        time.sleep(min(.2, max(0, deadline - time.monotonic())))
    return {"ok": False, "reason": error}


def start_session(release, data, config_home, data_home, state_home, *, cleanup=True):
    """Start only this Hyprland instance; never import global display variables."""
    signature = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    wayland = os.environ.get("WAYLAND_DISPLAY")
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not signature or not wayland or not runtime:
        return {"status": "not-requested", "reason": "No active Hyprland/Wayland session"}
    session = hashlib.sha256((signature + "|main").encode()).hexdigest()[:12]
    runtime_dir = _path(runtime) / ("rglauncher-" + session)
    if runtime_dir.is_symlink():
        raise InstallError("Session runtime directory cannot be a symlink")
    runtime_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    if runtime_dir.stat().st_uid != os.getuid() or runtime_dir.stat().st_mode & 0o077:
        raise InstallError("Session runtime directory must be private to this user")
    environment = {key: os.environ[key] for key in SESSION_ENV if os.environ.get(key)}
    environment["GDK_BACKEND"] = "wayland"
    _atomic(runtime_dir / "session.env", _environment_file(environment), 0o600)
    service = f"rglauncher-shelf@{session}.service"
    target = f"rglauncher-session@{session}.target"
    old_bars = _session_bars(signature) if cleanup else []
    steps = {}
    steps["daemon_reload"] = _run(["systemctl", "--user", "daemon-reload"])
    if not steps["daemon_reload"]["ok"]:
        return {"status": "partial", "service": service, "session": session, "steps": steps}
    active = _run(["systemctl", "--user", "is-active", service])
    restart = False
    if active["ok"]:
        pid = _run(["systemctl", "--user", "show", service, "--property=MainPID", "--value"])
        process = _process(pid["stdout"]) if pid["ok"] and pid["stdout"].isdigit() else None
        if not process or process.get("HYPRLAND_INSTANCE_SIGNATURE") != signature:
            return {"status": "partial", "service": service, "reason": "Active service session could not be verified", "steps": steps}
        restart = process.get("RGL_RELEASE_ROOT") != str(release)
    steps["target"] = _run(["systemctl", "--user", "start", target])
    steps["service"] = _run(["systemctl", "--user", "restart" if restart else "start", service])
    verification = _run(["systemctl", "--user", "is-active", service])
    pid = _run(["systemctl", "--user", "show", service, "--property=MainPID", "--value"])
    service_pid = int(pid["stdout"]) if pid["ok"] and pid["stdout"].isdigit() and int(pid["stdout"]) > 0 else None
    running = verification["ok"] and service_pid is not None
    readiness = _wait_shelf(release, signature, runtime_dir, int(pid["stdout"])) if running else {"ok": False, "reason": "Service is not running the selected release"}
    running = bool(running and readiness["ok"] and all(step["ok"] for step in steps.values()))
    result = {"status": "running" if running else "partial", "service": service, "session": session,
              "steps": steps, "verification": verification, "readiness": readiness, "pid": service_pid}
    if running and cleanup:
        result["old_waybars"] = _terminate_bars(old_bars, signature, release)
    return result


def _integrate(release, home, data, config_home, data_home, state_home, receipt, *, activate, enable_autoupdate, configure_timer=True):
    """Reconcile verified owned integration; preserve existing user defaults."""
    from .native import apply_native
    native = apply_native(release, config_home, data_home, activate=activate, state_home=state_home)
    receipt.value["native"] = native
    receipt.save()
    native_environment = native.get("environment", {})
    bin_dir = home / ".local/bin"
    for name in WRAPPERS:
        receipt.file(bin_dir / name, _wrapper(name, data, config_home, data_home, state_home, native_environment), 0o755)
    for name in ("aether-score", "aether-score-light"):
        receipt.symlink(data_home / "icons" / name, data / "current/share/icons" / name)
    receipt.file(config_home / "instrument-score-aether/tokens.json", (release / "share/instrument-score-aether/tokens.json").read_bytes(), preserve=True)
    for name in ("config.jsonc", "style.css"):
        receipt.file(config_home / "waybar" / name, (release / "share/waybar" / name).read_bytes(), preserve=True)
    for entry in sorted((release / "share/applications").glob("*.desktop")):
        receipt.file(data_home / "applications" / entry.name, _desktop_entry(entry.read_text(), bin_dir / "rglauncher"))

    unit_dir = config_home / "systemd/user"
    # systemd deliberately expands arguments differently from argv[0]. A fixed
    # env executable puts arbitrary %/$/space-containing user paths in argv[1],
    # where %% and $$ have their documented literal-escape behavior.
    replacements = {"@RG_LAUNCHER@": "/usr/bin/env " + systemd_quote(bin_dir / "rglauncher", execute=True),
                    "@SHELF_LAUNCHER@": "/usr/bin/env " + systemd_quote(bin_dir / "rglauncher-shelf", execute=True),
                    "@DATA_DIR@": systemd_quote(data), "@STATE_DIR@": systemd_quote(state_home / "rglauncher-linux")}
    for name in ("rglauncher-update.service", "rglauncher-update.timer", "rglauncher-shelf@.service", "rglauncher-session@.target"):
        text = (release / "systemd" / name).read_text()
        for marker, value in replacements.items():
            text = text.replace(marker, value)
        if any(marker in text for marker in replacements):
            raise InstallError("Unresolved service unit path")
        if name.endswith(".service"):
            env = {"XDG_CONFIG_HOME": str(config_home), "XDG_DATA_HOME": str(data_home), "XDG_STATE_HOME": str(state_home), **native_environment}
            text += "\n[Service]\n" + "\n".join("Environment=" + systemd_quote(key + "=" + value) for key, value in env.items()) + "\n"
        receipt.file(unit_dir / name, text.encode())
    if activate:
        activation = start_session(release, data, config_home, data_home, state_home)
        receipt.value["activation"] = activation
        if configure_timer and enable_autoupdate:
            receipt.value["autoupdate"] = _run(["systemctl", "--user", "enable", "--now", "rglauncher-update.timer"])
        else:
            receipt.value["autoupdate"] = {"ok": True, "status": "not-requested"}
        native_status = native.get("activation", {}).get("status")
        receipt.value["status"] = "installed" if activation["status"] == "running" and receipt.value["autoupdate"]["ok"] and native_status not in ("partial", "failed") else "partial"
    else:
        receipt.value.update(status="prepared", activation={"status": "not-requested"}, autoupdate={"status": "not-requested"})


def install(feed, public_key, allow_file, channel, enable_autoupdate, *, activate=True):
    home = _path(Path.home())
    data, config, state = _path(data_dir()), _path(config_dir()), _path(state_dir())
    config_home, data_home, state_home = config.parent, data.parent, state.parent
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(state / "install.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise InstallError("Another installation is in progress") from error
        service = Updater(UpdateConfig(data, state, feed, Path(public_key), allow_file=allow_file, channel=channel))
        from .cli import preflight
        def verify_candidate(path):
            _required_payload(path)
            preflight(path)
        update_result = service.apply(preflight=verify_candidate)
        with service._lock():
            version = service._link("current")
            if version is None:
                raise InstallError("The verified feed has no eligible release")
            service._receipt(version)
            release = service.releases / version
        _required_payload(release)
        if not update_result["changed"]:
            preflight(release)
        receipt = _Receipt(state, release)
        receipt.value["verified_update"] = update_result
        try:
            pin = config / "publisher.pub"
            receipt.file(pin, service.key.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
            updates_path = config / "updates.json"
            existing = json.loads(updates_path.read_text()) if updates_path.exists() else {}
            if not isinstance(existing, dict):
                raise InstallError("Existing update configuration must be an object")
            existing.update(feed_url=feed, public_key=str(pin), allow_file=bool(allow_file), channel=channel, automatic=bool(enable_autoupdate))
            receipt.file(updates_path, _json_bytes(existing), 0o600)

            _integrate(release, home, data, config_home, data_home, state_home, receipt,
                       activate=activate, enable_autoupdate=enable_autoupdate)
        except Exception as error:
            receipt.value["errors"].append(str(error))
            receipt.value["status"] = "partial"
        receipt.save()
        return receipt.value
    finally:
        os.close(descriptor)


def reconcile_current(*, activate=True):
    """Refresh this session from the current signed receipt, without a feed fetch.

    Automatic updates only select code. An explicit refresh applies native
    adapters and restarts solely this invocation's Hyprland shelf instance.
    """
    home = _path(Path.home())
    data, config, state = _path(data_dir()), _path(config_dir()), _path(state_dir())
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(state / "install.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise InstallError("Another integration refresh is in progress") from error
        settings = json.loads((config / "updates.json").read_text())
        updater = Updater(UpdateConfig(data, state, settings["feed_url"], Path(settings["public_key"]),
                                      allow_file=settings.get("allow_file", False), channel=settings.get("channel", "stable")))
        # Keep selection and its exact tree stable throughout local reconciliation.
        with updater._lock():
            version = updater._link("current")
            if version is None:
                raise InstallError("There is no verified current release")
            updater._receipt(version)
            release = updater.releases / version
            _required_payload(release)
            receipt = _Receipt(state, release)
            receipt.value["operation"] = "refresh-current"
            try:
                _integrate(release, home, data, config.parent, data.parent, state.parent, receipt,
                           activate=activate, enable_autoupdate=settings.get("automatic", False), configure_timer=False)
            except Exception as error:
                receipt.value["errors"].append(str(error))
                receipt.value["status"] = "partial"
            receipt.save()
            return receipt.value
    finally:
        os.close(descriptor)


def restore_owned(receipt_path):
    """Guarded restoration of this installer's files/links, not a full uninstall.

Native preferences/services have their own receipts/lifecycle and are not silently
changed here. Later user edits are preserved and reported as conflicts.
"""
    path = Path(receipt_path)
    receipt = json.loads(path.read_text())
    restored, conflicts = [], []
    for record in reversed(receipt["changes"]):
        target = Path(record["path"])
        if record.get("after") is None:
            continue
        if _fingerprint(target) != record["after"]:
            conflicts.append(str(target))
            continue
        before = record["before"]
        if before["type"] == "absent":
            target.unlink()
        elif before["type"] == "file":
            _atomic(target, Path(record["backup"]).read_bytes(), before["mode"])
        elif before["type"] == "symlink":
            temporary = target.with_name(".restore-" + uuid.uuid4().hex)
            temporary.symlink_to(before["target"])
            os.replace(temporary, target)
        elif before["type"] == "directory":
            target.unlink()
            os.rename(record["backup"], target)
        restored.append(str(target))
    return {"restored": restored, "conflicts": conflicts, "native_and_services_restored": False}
