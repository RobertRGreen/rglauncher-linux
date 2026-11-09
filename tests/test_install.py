import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import socket
import threading
import time
import unittest
from unittest.mock import Mock, patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from rglauncher_linux import install as installer
from rglauncher_linux.update import UpdateError
from tools.sign_release import build_manifest, write_signed


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="rglauncher-install-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.home = self.base / "home %value $profile space"
        self.config = self.home / "config %p $data"
        self.data = self.home / "data %p $data"
        self.state = self.home / "state %p $data"
        self.runtime = self.home / "run"
        self.runtime.mkdir(parents=True)
        environment = {"HOME": str(self.home), "XDG_CONFIG_HOME": str(self.config), "XDG_DATA_HOME": str(self.data),
                       "XDG_STATE_HOME": str(self.state), "XDG_RUNTIME_DIR": str(self.runtime),
                       "WAYLAND_DISPLAY": "wayland-fixture", "HYPRLAND_INSTANCE_SIGNATURE": "fixture-session",
                       "DBUS_SESSION_BUS_ADDRESS": "unix:path=" + str(self.runtime / "bus"), "INSTALL_TRACE": str(self.home / "trace.json")}
        self.env = patch.dict(os.environ, environment)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.publisher = Ed25519PrivateKey.generate()
        self.pin = self.base / "publisher.pub"
        self.pin.write_bytes(self.publisher.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        self.payload = self.base / "payload"
        self.payload.mkdir()
        self.feed = self.base / "feed.json"
        self._payload()
        self._publish()
        self.preflight = patch("rglauncher_linux.cli.preflight", return_value=None)
        self.preflight_mock = self.preflight.start()
        self.addCleanup(self.preflight.stop)
        self.native = patch("rglauncher_linux.native.apply_native", return_value={"environment": {}, "activation": {"status": "applied"}})
        self.native_mock = self.native.start()
        self.addCleanup(self.native.stop)

    def put(self, relative, content, executable=False):
        path = self.payload / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        path.chmod(0o755 if executable else 0o644)

    def _payload(self):
        code = '''import json,os,sys
from pathlib import Path
def main(argv=None):
    value={"args":sys.argv[1:] if argv is None else argv,"root":str(Path(__file__).resolve().parents[1]),"bytecode":sys.dont_write_bytecode}
    Path(os.environ["INSTALL_TRACE"]).write_text(json.dumps(value))
    print(json.dumps(value))
    return 0
'''
        self.put("LICENSE", "MIT fixture\n")
        self.put("rglauncher_linux/__init__.py", "")
        self.put("rglauncher_linux/cli.py", code)
        self.put("rglauncher_linux/shelf.py", code)
        for name in ("rglauncher", "rglauncher-shelf", "rofi-launcher", "hypr-windows"):
            self.put("bin/" + name, "from rglauncher_linux.cli import main\nraise SystemExit(main())\n", True)
        self.put("share/waybar/waybar", "#!/usr/bin/env python3\nimport json,sys,os;print(json.dumps({'backend':True,'args':sys.argv[1:],'lua':os.getenv('WAYBAR_HYPRLAND_LUA')}))\n", True)
        self.put("share/waybar/config.jsonc", '{"fixture":true}\n')
        self.put("share/waybar/style.css", "/* fixture */\n")
        self.put("share/instrument-score-aether/tokens.json", '{}\n')
        for theme in ("aether-score", "aether-score-light"):
            self.put("share/icons/" + theme + "/index.theme", "[Icon Theme]\nName=Fixture\n")
        root = Path(__file__).resolve().parents[1]
        for unit in ("rglauncher-update.service", "rglauncher-update.timer", "rglauncher-shelf@.service", "rglauncher-session@.target"):
            self.put("systemd/" + unit, (root / "systemd" / unit).read_text())
        for name in installer.REQUIRED_ACTIONS:
            self.put(f"share/applications/io.rglauncher.{name}.desktop", "[Desktop Entry]\nType=Application\nName=Fixture " + name + "\nExec=rglauncher " + name + "\nIcon=aether-application\n")
        for name in installer.REQUIRED_FILES:
            if not (self.payload / name).exists():
                self.put(name, "# Isolated signed installer fixture\n")

    def _publish(self):
        artifact = self.base / "release.tar.gz"
        with tarfile.open(artifact, "w:gz", format=tarfile.USTAR_FORMAT) as archive:
            for path in sorted(self.payload.rglob("*")):
                if path.is_file():
                    info = archive.gettarinfo(str(path), path.relative_to(self.payload).as_posix())
                    info.mtime, info.uid, info.gid = 0, 0, 0
                    info.uname = info.gname = ""
                    with path.open("rb") as stream:
                        archive.addfile(info, stream)
        now = int(time.time())
        manifest = build_manifest(self.payload, artifact, artifact.as_uri(), "0.2.0-alpha.1", now - 1, now + 3600)
        path = self.base / "manifest.json"
        encoded = write_signed(manifest, self.publisher, path)
        write_signed({"schema": 1, "product": "rglauncher-linux", "sequence": 1, "issued_at": now - 1,
                      "expires_at": now + 3600, "releases": [{"version": "0.2.0-alpha.1", "manifest_url": path.as_uri(),
                                                              "manifest_sha256": hashlib.sha256(encoded).hexdigest()}]}, self.publisher, self.feed)

    def run_install(self, activate=False, automatic=False):
        return installer.install(self.feed.as_uri(), self.pin, True, "prerelease", automatic, activate=activate)

    def test_prepare_is_verified_isolated_and_preserves_existing_files(self):
        waybar = self.config / "waybar/config.jsonc"
        waybar.parent.mkdir(parents=True)
        waybar.write_text("user Waybar config")
        local_audio = self.home / ".local/bin/audio-menu"
        local_audio.parent.mkdir(parents=True)
        local_audio.write_text("existing user's audio")
        with patch.object(installer, "_run", side_effect=AssertionError("No native/systemd commands in prepare")), patch.object(installer, "_session_bars", side_effect=AssertionError("No live process scan")):
            result = self.run_install()
        self.assertEqual(result["status"], "prepared", result)
        self.assertEqual(waybar.read_text(), "user Waybar config")
        self.assertEqual(local_audio.read_text(), "existing user's audio")
        self.assertFalse(list(self.runtime.glob("rglauncher-*")))
        self.assertFalse(self.native_mock.call_args.kwargs["activate"])
        self.assertEqual(self.native_mock.call_args.args[1:3], (self.config, self.data))
        settings = json.loads((self.config / "rglauncher-linux/updates.json").read_text())
        self.assertEqual(settings["feed_url"], self.feed.as_uri())
        self.assertFalse(settings["automatic"])
        self.assertTrue((self.data / "icons/aether-score").is_symlink())
        self.assertTrue(Path(result["manifest"]).is_file())

    def test_bad_signature_never_writes_wrappers_or_configuration(self):
        self.feed.write_text('{"signed":{},"signature":"bad"}')
        with self.assertRaises(UpdateError):
            self.run_install()
        self.assertFalse((self.config / "rglauncher-linux").exists())
        self.assertFalse((self.home / ".local/bin/rglauncher").exists())
        self.native_mock.assert_not_called()

    def test_missing_integration_asset_fails_before_activation(self):
        (self.payload / "share/waybar/style.css").unlink()
        self._publish()
        with self.assertRaises(UpdateError):
            self.run_install()
        self.assertFalse((self.data / "rglauncher-linux/current").exists())

    def test_repeated_prepare_is_idempotent_for_owned_files(self):
        first = self.run_install()
        second = self.run_install()
        self.assertEqual(first["status"], "prepared")
        self.assertEqual(second["status"], "prepared")
        self.assertFalse(second["changes"], second)

    def test_symlink_targets_and_existing_theme_directory_are_preserved(self):
        external = self.home / "repo-theme"
        external.mkdir()
        (external / "marker").write_text("keep target")
        icons = self.data / "icons"
        icons.mkdir(parents=True)
        (icons / "aether-score").symlink_to(external)
        old_light = icons / "aether-score-light"
        old_light.mkdir()
        (old_light / "marker").write_text("keep actual directory")
        result = self.run_install()
        self.assertEqual((external / "marker").read_text(), "keep target")
        restored = installer.restore_owned(result["manifest"])
        self.assertFalse(restored["conflicts"])
        self.assertEqual(os.readlink(icons / "aether-score"), str(external))
        self.assertEqual((icons / "aether-score-light/marker").read_text(), "keep actual directory")

    def test_guarded_restore_preserves_later_user_changes(self):
        result = self.run_install()
        wrapper = self.home / ".local/bin/rglauncher"
        wrapper.write_text("later user change")
        restored = installer.restore_owned(result["manifest"])
        self.assertIn(str(wrapper), restored["conflicts"])
        self.assertEqual(wrapper.read_text(), "later user change")

    def test_wrappers_use_pinned_release_and_waybar_backend_without_recursion(self):
        self.run_install()
        for name in ("rglauncher", "rglauncher-shelf", "rofi-launcher", "hypr-windows"):
            wrapper = self.home / ".local/bin" / name
            output = subprocess.run([sys.executable, "-B", str(wrapper), "fixture"], capture_output=True, text=True, check=True)
            data = json.loads(output.stdout)
            self.assertTrue(data["bytecode"])
            self.assertEqual(Path(data["root"]).name, "0.2.0-alpha.1")
        bar = self.home / ".local/bin/waybar"
        output = subprocess.run([sys.executable, "-B", str(bar), "--version"], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(output.stdout), {"backend": True, "args": ["--version"], "lua": "1"})
        output = subprocess.run([sys.executable, "-B", str(bar)], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(output.stdout)["args"], ["run"])
        self.assertFalse(any((self.data / "rglauncher-linux/releases").rglob("__pycache__")))

    def test_desktop_exec_and_units_quote_special_paths(self):
        self.run_install()
        entry = self.data / "applications/io.rglauncher.apps.desktop"
        # Launch this isolated fixture desktop file; the target only writes a
        # marker/JSON and exits. No desktop application/foreground UI is opened.
        import gi
        gi.require_version("GioUnix", "2.0")
        from gi.repository import GioUnix
        info = GioUnix.DesktopAppInfo.new_from_filename(str(entry))
        self.assertIsNotNone(info)
        info.launch([], None)
        trace = self.home / "trace.json"
        for _ in range(50):
            if trace.exists():
                break
            time.sleep(.02)
        self.assertEqual(json.loads(trace.read_text())["args"], ["apps"])
        unit = (self.config / "systemd/user/rglauncher-update.service").read_text()
        self.assertIn("%%", unit)
        self.assertIn("$$", unit)
        self.assertNotIn("@DATA_DIR@", unit)
        if shutil.which("systemd-analyze"):
            result = subprocess.run(["systemd-analyze", "--user", "verify", str(self.config / "systemd/user/rglauncher-update.service")], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_activation_failure_is_reported_as_partial(self):
        with patch.object(installer, "start_session", return_value={"status": "partial", "service": "fixture"}), patch.object(installer, "_run", return_value={"ok": False, "stderr": "fixture failure"}):
            result = self.run_install(activate=True, automatic=True)
        self.assertEqual(result["status"], "partial")
        self.assertFalse(result["autoupdate"]["ok"])

    def test_session_env_is_whitelisted_and_other_session_bars_survive(self):
        release = self.base / "release"
        old = {"pid": 111, "command": "waybar", "start": "20", "HYPRLAND_INSTANCE_SIGNATURE": "fixture-session"}
        new = {"pid": 222, "command": "python3", "start": "30", "HYPRLAND_INSTANCE_SIGNATURE": "fixture-session", "RGL_RELEASE_ROOT": str(release)}
        calls = []
        def run(command):
            calls.append(command)
            if "show" in command:
                return {"ok": True, "stdout": "222", "stderr": ""}
            return {"ok": True, "stdout": "active", "stderr": ""}
        with patch.dict(os.environ, {"UNRELATED_SECRET": "must-not-copy"}), patch.object(installer, "_run", side_effect=run), patch.object(installer, "_session_bars", return_value=[old]), patch.object(installer, "_process", side_effect=lambda pid: new if int(pid) == 222 else old), patch.object(installer, "_wait_shelf", return_value={"ok": True, "outputs": {"fixture": 333}}), patch.object(installer.os, "kill") as kill:
            result = installer.start_session(release, self.data, self.config, self.data, self.state)
        self.assertEqual(result["status"], "running")
        kill.assert_called_once_with(111, installer.signal.SIGTERM)
        environment = next(self.runtime.glob("rglauncher-*/session.env"))
        self.assertEqual(environment.stat().st_mode & 0o777, 0o600)
        self.assertNotIn("UNRELATED_SECRET", environment.read_text())
        self.assertIn('GDK_BACKEND="wayland"', environment.read_text())
        self.assertFalse(any("import-environment" in command for command in calls))
        self.assertTrue(all("@" + result["session"] in command[-1] for command in calls if "start" in command or "restart" in command))

    def test_shelf_requires_live_stable_children_from_same_release_and_session(self):
        release = self.base / "release"
        controller = {"pid": 222, "command": "python3", "start": "30", "HYPRLAND_INSTANCE_SIGNATURE": "fixture-session", "RGL_RELEASE_ROOT": str(release)}
        child = {**controller, "pid": 333, "command": "waybar", "start": "31"}
        process = lambda pid: controller if int(pid) == 222 else child
        with patch.object(installer, "_process", side_effect=process), patch.object(installer, "_shelf_status", return_value={"outputs": {"fixture": {"pid": 333}}}):
            ready = installer._wait_shelf(release, "fixture-session", self.runtime, 222, timeout=.5)
        self.assertTrue(ready["ok"])
        self.assertEqual(ready["outputs"], {"fixture": 333})
        for response in ({"outputs": {}}, {"outputs": {"fixture": {"pid": "333"}}}, {"error": "not ready"}):
            with self.subTest(response=response), patch.object(installer, "_process", side_effect=process), patch.object(installer, "_shelf_status", return_value=response):
                self.assertFalse(installer._wait_shelf(release, "fixture-session", self.runtime, 222, timeout=.01)["ok"])
        with patch.object(installer, "_process", return_value={**controller, "RGL_RELEASE_ROOT": "other"}):
            self.assertFalse(installer._wait_shelf(release, "fixture-session", self.runtime, 222, timeout=.01)["ok"])

    def test_unready_shelf_preserves_old_bars(self):
        release = self.base / "release"
        process = {"pid": 222, "command": "python3", "start": "30", "HYPRLAND_INSTANCE_SIGNATURE": "fixture-session", "RGL_RELEASE_ROOT": str(release)}
        def run(command):
            return {"ok": True, "stdout": "222" if "show" in command else "active", "stderr": ""}
        with patch.object(installer, "_run", side_effect=run), patch.object(installer, "_session_bars", return_value=[]), patch.object(installer, "_process", return_value=process), patch.object(installer, "_wait_shelf", return_value={"ok": False, "reason": "no outputs"}), patch.object(installer, "_terminate_bars") as terminate:
            result = installer.start_session(release, self.data, self.config, self.data, self.state)
        self.assertEqual(result["status"], "partial")
        terminate.assert_not_called()

    def test_session_start_waits_for_wrapper_pinned_exec_before_readiness(self):
        release = self.base / "release"
        wrapper = {"pid": 222, "command": "python3", "start": "30", "HYPRLAND_INSTANCE_SIGNATURE": "fixture-session"}
        controller = {**wrapper, "RGL_RELEASE_ROOT": str(release)}
        child = {**controller, "pid": 333, "command": "waybar", "start": "31"}
        observations = iter([wrapper, controller, controller])
        active_checks = 0
        def run(command):
            nonlocal active_checks
            if "is-active" in command:
                active_checks += 1
                return {"ok": active_checks > 1, "stdout": "active", "stderr": ""}
            return {"ok": True, "stdout": "222" if "show" in command else "", "stderr": ""}
        def process(pid):
            return next(observations) if int(pid) == 222 else child
        with patch.object(installer, "_run", side_effect=run), patch.object(installer, "_session_bars", return_value=[]), patch.object(installer, "_process", side_effect=process), patch.object(installer, "_shelf_status", return_value={"outputs": {"fixture": {"pid": 333}}}):
            result = installer.start_session(release, self.data, self.config, self.data, self.state)
        self.assertEqual(result["status"], "running", result)
        self.assertEqual(result["readiness"]["outputs"], {"fixture": 333})

    def test_startup_identity_rejects_conflicts_and_pid_reuse_without_socket_use(self):
        release = self.base / "release"
        wrapper = {"pid": 222, "command": "python3", "start": "30", "HYPRLAND_INSTANCE_SIGNATURE": "fixture-session"}
        for observations in ([{**wrapper, "RGL_RELEASE_ROOT": "other"}], [{**wrapper, "HYPRLAND_INSTANCE_SIGNATURE": "other"}], [wrapper, {**wrapper, "start": "31", "RGL_RELEASE_ROOT": str(release)}]):
            with self.subTest(observations=observations), patch.object(installer, "_process", side_effect=observations), patch.object(installer, "_shelf_status") as status:
                result = installer._wait_shelf(release, "fixture-session", self.runtime, 222, timeout=.5)
            self.assertFalse(result["ok"])
            status.assert_not_called()

    def test_shelf_socket_checks_peer_identity_and_status(self):
        path = self.base / "shelf.sock"
        listener = socket.socket(socket.AF_UNIX)
        self.addCleanup(listener.close)
        listener.bind(str(path)); listener.listen(1)
        def serve():
            with listener.accept()[0] as client:
                request = json.loads(client.recv(4096))
                self.assertEqual(request, {"command": "status"})
                client.sendall(b'{"outputs":{"fixture":{"pid":123}}}')
        thread = threading.Thread(target=serve)
        thread.start()
        self.assertEqual(installer._shelf_status(path, os.getpid()), {"outputs": {"fixture": {"pid": 123}}})
        thread.join(timeout=1)
        self.assertFalse(thread.is_alive())

    def test_reconcile_verifies_current_receipt_without_fetch_or_live_activation(self):
        self.run_install()
        with patch.object(installer.Updater, "_fetch", side_effect=AssertionError("Refresh is local only")), patch.object(installer, "_run", side_effect=AssertionError("No native service calls")):
            result = installer.reconcile_current(activate=False)
        self.assertEqual(result["status"], "prepared", result)
        self.assertEqual(result["operation"], "refresh-current")
        self.assertFalse(self.native_mock.call_args.kwargs["activate"])
        current = self.data / "rglauncher-linux/current"
        (current / "LICENSE").write_text("tampered")
        before = self.native_mock.call_count
        with self.assertRaises(UpdateError):
            installer.reconcile_current(activate=False)
        self.assertEqual(self.native_mock.call_count, before)


if __name__ == "__main__":
    unittest.main()
