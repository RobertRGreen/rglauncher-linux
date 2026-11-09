"""On-demand, bounded read-only SSH telemetry; private inventory stays local."""
from __future__ import annotations

import copy
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import tempfile
import threading
import time

from .paths import config_dir, release_root, state_dir

STALE_AFTER = 8
MAX_LINE = 262144
MAX_STDERR = 16384
MAX_HOSTS = 128
MAX_CACHE = 4 * 1024 * 1024
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
DESTINATION = re.compile(r"(?:[A-Za-z0-9_][A-Za-z0-9_.+\-]*@)?(?:[A-Za-z0-9_][A-Za-z0-9_.:\-]*|\[[0-9A-Fa-f:]+\])\Z")


def _label(value, name, maximum=160):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or any(not character.isprintable() for character in value):
        raise ValueError("Invalid server " + name)
    return value


def _local_path(value):
    if value is None:
        return None
    value = _label(value, "key/known-hosts path", 4096)
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError("Server key/known-hosts paths must be absolute or start with ~")
    return str(path)


@dataclass(frozen=True, slots=True)
class Host:
    id: str
    label: str
    target: str
    port: int = 22
    identity_file: str | None = None
    known_hosts_file: str | None = None
    group: str = "VPS"

    def __post_init__(self):
        if not isinstance(self.id, str) or not IDENTIFIER.fullmatch(self.id):
            raise ValueError("Invalid server id")
        _label(self.label, "label")
        _label(self.group, "group", 80)
        if not isinstance(self.target, str) or len(self.target) > 320 or not DESTINATION.fullmatch(self.target):
            raise ValueError("Invalid SSH target; use a hostname, address or SSH alias")
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValueError("Invalid SSH port")
        object.__setattr__(self, "identity_file", _local_path(self.identity_file))
        object.__setattr__(self, "known_hosts_file", _local_path(self.known_hosts_file))


def _reject_constant(_value):
    raise ValueError("Nonfinite JSON values are not supported")


def _configuration(path=None):
    path = Path(path) if path is not None else config_dir() / "servers.json"
    if not path.exists():
        return {"hosts": [], "interval": 2}
    with path.open("rb") as stream:
        data = stream.read(65537)
    if len(data) > 65536:
        raise ValueError("Server inventory exceeds its size limit")
    value = json.loads(data, parse_constant=_reject_constant)
    if not isinstance(value, dict) or not isinstance(value.get("hosts", []), list):
        raise ValueError("Server inventory must contain a hosts list")
    return value


def load_hosts(path=None):
    value = _configuration(path)
    records = value.get("hosts", [])
    if len(records) > MAX_HOSTS:
        raise ValueError("Too many server connections")
    hosts, identities = [], set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Each server must be an object")
        try:
            host = Host(**record)
        except TypeError as error:
            raise ValueError("Invalid server fields") from error
        if host.id in identities:
            raise ValueError("Server ids must be unique")
        identities.add(host.id); hosts.append(host)
    return hosts


def load_interval(path=None):
    value = _configuration(path).get("interval", 2)
    if not _number(value, minimum=1) or value > 60:
        raise ValueError("Server sample interval must be between 1 and 60 seconds")
    return float(value)


def ssh_argv(host, *, interactive=False, interval=2):
    if not isinstance(host, Host):
        raise TypeError("An immutable Host is required")
    result = ["ssh", "-o", "StrictHostKeyChecking=yes", "-o", "UpdateHostKeys=no", "-o", "ConnectTimeout=6",
              "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=2", "-p", str(host.port)]
    if host.identity_file:
        result += ["-i", host.identity_file, "-o", "IdentitiesOnly=yes"]
    if host.known_hosts_file:
        quoted = host.known_hosts_file.replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"')
        result += ["-o", 'UserKnownHostsFile="' + quoted + '"']
    if not interactive:
        result += ["-T", "-o", "BatchMode=yes", "-o", "RequestTTY=no", "-o", "PermitLocalCommand=no",
                   "-o", "ClearAllForwardings=yes", "-o", "ForwardAgent=no", "-o", "ForwardX11=no",
                   "-o", "ControlMaster=no", "-o", "ControlPath=none", "-o", "RemoteCommand=none",
                   "-o", "ForkAfterAuthentication=no", "-o", "StdinNull=no", "-o", "SessionType=default"]
    result += ["--", host.target]
    if not interactive:
        if not _number(interval, minimum=1) or interval > 60:
            raise ValueError("Invalid sample interval")
        result += ["python3", "-B", "-u", "-", format(interval, ".6g")]
    return result


def host_transport_id(host):
    value = {name: getattr(host, name) for name in ("target", "port", "identity_file", "known_hosts_file")}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def classify_error(stderr, returncode=None):
    """Return useful categories without persisting raw SSH banners/command text."""
    value = stderr.lower()
    if any(fragment in value for fragment in ("host key verification failed", "remote host identification has changed", "offending ")) or ("host key is known" in value and "no " in value):
        return "host_key_error", "The saved SSH host key could not be verified. Review it in a terminal."
    if any(fragment in value for fragment in ("permission denied", "authentication failed", "no supported authentication", "too many authentication", "sign_and_send_pubkey", "read_passphrase")):
        return "auth_required", "SSH authentication requires attention. Open an interactive terminal to authenticate."
    if returncode == 127 or ("python3" in value and any(fragment in value for fragment in ("not found", "no such file", "command not found"))):
        return "unsupported", "This connection does not provide a supported Python 3 Linux shell."
    if any(fragment in value for fragment in ("timed out", "could not resolve hostname", "connection refused", "no route to host", "network is unreachable", "connection closed", "connection reset")):
        return "unreachable", "The SSH connection is unavailable or timed out."
    return "error", "The SSH telemetry stream ended unexpectedly."


def _number(value, minimum=0):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and minimum <= value <= 1e20 and math.isfinite(value)


def _decode_sample(line, observed):
    value = json.loads(line, parse_constant=_reject_constant)
    if not isinstance(value, dict) or type(value.get("schema")) is not int or value["schema"] != 1:
        raise ValueError("Unsupported telemetry schema")
    if "error" in value:
        raise ValueError("Required Linux telemetry is unavailable")
    remote = value.get("sampled_at")
    metrics = value.get("metrics")
    if not _number(remote) or not isinstance(metrics, dict):
        raise ValueError("Invalid telemetry sample")
    required = ("cpu", "memory", "swap", "load", "network", "disk", "services", "containers")
    if not all(isinstance(metrics.get(name), dict) for name in required) or not isinstance(metrics.get("processes"), list) or len(metrics["processes"]) > 12:
        raise ValueError("Incomplete telemetry sample")
    fields = {
        "cpu": ("percent", "cores", "updated_at"),
        "memory": ("total_bytes", "used_bytes", "available_bytes", "percent", "updated_at"),
        "swap": ("total_bytes", "used_bytes", "percent", "updated_at"),
        "load": ("one", "five", "fifteen", "updated_at"),
        "network": ("rx_bytes_per_second", "tx_bytes_per_second", "interfaces", "updated_at"),
        "disk": ("filesystems", "filesystems_updated_at", "read_bytes_per_second", "write_bytes_per_second", "updated_at"),
        "services": ("failed", "updated_at"), "containers": ("items", "updated_at"),
    }
    projected = {}
    for name, names in fields.items():
        if any(field not in metrics[name] for field in names):
            raise ValueError("Incomplete telemetry fields")
        projected[name] = {field: metrics[name][field] for field in names}
        if "error" in metrics[name]:
            projected[name]["error"] = metrics[name]["error"]
    projected["uptime_seconds"] = metrics.get("uptime_seconds")
    for group, field, allowed, maximum in (
        ("disk", "filesystems", ("mount", "total_bytes", "used_bytes", "available_bytes", "percent"), 64),
        ("services", "failed", ("unit", "description"), 64),
        ("containers", "items", ("id", "name", "state", "status"), 128),
    ):
        items = projected[group][field]
        if not isinstance(items, list) or len(items) > maximum or not all(isinstance(item, dict) and all(key in item for key in allowed) for item in items):
            raise ValueError("Invalid telemetry collection")
        projected[group][field] = [{key: item[key] for key in allowed} for item in items]
    process_fields = ("pid", "name", "cpu_percent", "memory_bytes")
    if not all(isinstance(item, dict) and all(key in item for key in process_fields) for item in metrics["processes"]):
        raise ValueError("Invalid process telemetry")
    projected["processes"] = [{key: item[key] for key in process_fields} for item in metrics["processes"]]
    # Restrict primitive shapes/depth/output. Samplers expose process names and
    # container states, never environment, command arguments, logs or secrets.
    def normalize(item, depth=0, key=None):
        if depth > 8:
            raise ValueError("Telemetry nesting exceeds limit")
        if isinstance(item, dict):
            if len(item) > 64 or not all(isinstance(name, str) and len(name) <= 80 for name in item):
                raise ValueError("Invalid telemetry fields")
            return {name: normalize(content, depth + 1, name) for name, content in item.items()}
        if isinstance(item, list):
            if len(item) > 128:
                raise ValueError("Telemetry list exceeds limit")
            return [normalize(content, depth + 1) for content in item]
        if item is None or isinstance(item, bool):
            return item
        if isinstance(item, str):
            if len(item) > 512 or any(not character.isprintable() for character in item):
                raise ValueError("Invalid telemetry text")
            return item
        if not _number(item, minimum=-1e18) or abs(item) > 1e20:
            raise ValueError("Invalid telemetry number")
        if key and (key == "updated_at" or key.endswith("_updated_at")):
            return observed - min(86400 * 365, max(0, remote - item))
        return item
    metrics = normalize(projected)
    for name in required:
        group = metrics[name]
        if not _number(group["updated_at"]) or (group.get("error") is not None and not isinstance(group["error"], str)):
            raise ValueError("Invalid telemetry observation")
        for key, content in group.items():
            if key in ("percent", "cores", "total_bytes", "used_bytes", "available_bytes", "one", "five", "fifteen", "rx_bytes_per_second", "tx_bytes_per_second", "read_bytes_per_second", "write_bytes_per_second"):
                if content is not None and not _number(content):
                    raise ValueError("Invalid telemetry measurement")
    if type(metrics["cpu"]["cores"]) is not int or not _number(metrics["cpu"]["cores"], 1) or not _number(metrics["uptime_seconds"]) or not isinstance(metrics["network"]["interfaces"], list) or not all(isinstance(name, str) for name in metrics["network"]["interfaces"]):
        raise ValueError("Invalid telemetry counters")
    for group in ("cpu", "memory", "swap"):
        percent = metrics[group]["percent"]
        if percent is not None and not 0 <= percent <= 100:
            raise ValueError("Invalid utilization percentage")
    for process in metrics["processes"]:
        if type(process["pid"]) is not int or not _number(process["pid"], 1) or not isinstance(process["name"], str) or not _number(process["memory_bytes"]) or (process["cpu_percent"] is not None and not _number(process["cpu_percent"])):
            raise ValueError("Invalid process measurements")
    for filesystem in metrics["disk"]["filesystems"]:
        if not isinstance(filesystem["mount"], str) or not all(_number(filesystem[field]) for field in ("total_bytes", "used_bytes", "available_bytes", "percent")) or filesystem["percent"] > 100:
            raise ValueError("Invalid filesystem measurements")
    if not all(isinstance(item[field], str) for item in metrics["services"]["failed"] for field in ("unit", "description")) or not all(isinstance(item[field], str) for item in metrics["containers"]["items"] for field in ("id", "name", "state", "status")):
        raise ValueError("Invalid service/container observations")
    metrics["sampled_at"] = observed
    return metrics


class FleetMonitor:
    def __init__(self, hosts, interval=2):
        self.hosts = tuple(hosts)
        if len(self.hosts) > MAX_HOSTS or any(not isinstance(host, Host) for host in self.hosts) or len({host.id for host in self.hosts}) != len(self.hosts):
            raise ValueError("Invalid or duplicate server connections")
        # Validate once using the same numerical rule as the actual SSH argv.
        if not _number(interval, minimum=1) or interval > 60:
            raise ValueError("Invalid sample interval")
        self.interval = float(interval)
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._threads, self._processes, self._received_monotonic = [], {}, {}
        self._records = {host.id: {"id": host.id, "label": host.label, "target": host.target, "group": host.group,
                                  "port": host.port, "transport_id": host_transport_id(host),
                                  "state": "stopped", "observed_at": None, "error": None, "metrics": None} for host in self.hosts}

    def start(self):
        with self._lock:
            if any(thread.is_alive() for thread in self._threads):
                return self
            self._stop.clear()
            self._threads = []
            for host in self.hosts:
                self._records[host.id].update(state="connecting", error=None)
                thread = threading.Thread(target=self._worker, args=(host,), name="rglauncher-fleet-" + host.id, daemon=True)
                self._threads.append(thread); thread.start()
        return self

    @staticmethod
    def _terminate(process):
        try:
            # The leader may already have exited while its ProxyCommand child
            # still owns a pipe. The owned group remains ours in either case.
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    def stop(self):
        self._stop.set()
        with self._lock:
            processes, threads = list(self._processes.values()), list(self._threads)
        for process in processes:
            self._terminate(process)
        deadline = time.monotonic() + 2
        for thread in threads:
            thread.join(max(0, deadline - time.monotonic()))
        with self._lock:
            remaining = list(self._processes.values())
        for process in remaining:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + .4
        for thread in threads:
            thread.join(max(0, deadline - time.monotonic()))
        with self._lock:
            for record in self._records.values():
                record["state"] = "stopped"
        return self.snapshot()

    def snapshot(self):
        with self._lock:
            values = copy.deepcopy([self._records[host.id] for host in self.hosts])
            received = dict(self._received_monotonic)
        now = time.monotonic()
        values = _age_records(values, time.time())
        for value in values:
            if value["id"] in received:
                value["age"] = max(0, now - received[value["id"]])
                value["stale"] = value["age"] > STALE_AFTER
                if value["state"] in ("online", "stale"):
                    value["state"] = "stale" if value["stale"] else "online"
        return values

    def _set(self, host, **values):
        with self._lock:
            if not self._stop.is_set():
                self._records[host.id].update(values)
                if "observed_at" in values:
                    self._received_monotonic[host.id] = time.monotonic()

    def _worker(self, host):
        delay = 2
        while not self._stop.is_set():
            self._set(host, state="connecting", error=None)
            state, error = self._stream(host)
            self._set(host, state=state, error=error)
            if state in ("auth_required", "host_key_error", "unsupported") or self._stop.wait(delay):
                return
            delay = min(30, delay * 2)

    def _stream(self, host):
        process = None
        stderr = bytearray()
        try:
            source = (release_root() / "share/fleet/sample.py").read_bytes()
            if len(source) > 65536:
                return "error", "Bundled telemetry sampler exceeds its limit."
            environment = dict(os.environ, SSH_ASKPASS="/bin/false", SSH_ASKPASS_REQUIRE="never")
            process = subprocess.Popen(ssh_argv(host, interval=self.interval), stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment,
                                       start_new_session=True, close_fds=True)
            with self._lock:
                self._processes[host.id] = process
            if self._stop.is_set():
                return "stopped", None
            pending, incoming = memoryview(source), bytearray()
            received = False
            last_sample = time.monotonic()
            with selectors.DefaultSelector() as selector:
                for stream, event, kind in ((process.stdin, selectors.EVENT_WRITE, "stdin"), (process.stdout, selectors.EVENT_READ, "stdout"), (process.stderr, selectors.EVENT_READ, "stderr")):
                    os.set_blocking(stream.fileno(), False)
                    selector.register(stream, event, kind)
                while selector.get_map() and not self._stop.is_set():
                    if time.monotonic() - last_sample > max(20, self.interval * 4):
                        return "unreachable", "The SSH stream stopped delivering telemetry. Last observations are retained."
                    for key, _event in selector.select(.2):
                        if key.data == "stdin":
                            try:
                                written = os.write(key.fd, pending[:8192])
                                pending = pending[written:]
                            except BrokenPipeError:
                                pending = memoryview(b"")
                            if not pending:
                                selector.unregister(key.fileobj); key.fileobj.close()
                            continue
                        chunk = os.read(key.fd, 4096)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        if key.data == "stderr":
                            stderr.extend(chunk[:max(0, MAX_STDERR - len(stderr))])
                            continue
                        incoming.extend(chunk)
                        if len(incoming) > MAX_LINE and b"\n" not in incoming:
                            return "unsupported", "Remote telemetry exceeded its safe line limit."
                        while b"\n" in incoming:
                            line, _separator, remainder = incoming.partition(b"\n")
                            incoming = bytearray(remainder)
                            if len(line) > MAX_LINE:
                                return "unsupported", "Remote telemetry exceeded its safe line limit."
                            if not line.strip():
                                continue
                            try:
                                observed = time.time()
                                metrics = _decode_sample(line, observed)
                            except (ValueError, TypeError, RecursionError, UnicodeError):
                                return "unsupported", "The remote shell did not provide supported Linux JSON telemetry."
                            self._set(host, state="online", error=None, metrics=metrics, observed_at=observed)
                            received, last_sample = True, time.monotonic()
            if self._stop.is_set():
                return "stopped", None
            returncode = process.poll()
            if not received and not stderr and returncode == 0:
                return "unsupported", "Remote Python ended without telemetry."
            return classify_error(stderr.decode(errors="replace"), returncode)
        except (OSError, ValueError) as error:
            return "unreachable", "Could not start or read the SSH telemetry connection."
        finally:
            if process:
                self._terminate(process)
                try:
                    process.wait(timeout=.4)
                except subprocess.TimeoutExpired:
                    pass
                finally:
                    # Also reap an owned descendant when its SSH leader exited
                    # early and wait() therefore returned before the child did.
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    try:
                        process.wait(timeout=.4)
                    except subprocess.TimeoutExpired:
                        pass
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream and not stream.closed:
                        stream.close()
                with self._lock:
                    if self._processes.get(host.id) is process:
                        self._processes.pop(host.id)


def _age_records(values, now):
    for value in values:
        observed = value.get("observed_at")
        age = max(0, now - observed) if _number(observed) else None
        value["age"] = age
        value["stale"] = age is not None and (age > STALE_AFTER or observed > now + 1)
        if value.get("state") == "online" and (age is None or not isinstance(value.get("metrics"), dict) or not value["metrics"]):
            value["stale"] = True
        if value.get("state") == "online" and value["stale"]:
            value["state"] = "stale"
    return values


def _publisher_identity(pid):
    try:
        path = Path("/proc") / str(pid)
        if path.stat().st_uid != os.getuid():
            return None
        started = (path / "stat").read_text().rsplit(")", 1)[1].split()[19]
        return {"pid": int(pid), "start": started}
    except (OSError, ValueError, IndexError):
        return None


def publish_cache(snapshot):
    if not isinstance(snapshot, list) or len(snapshot) > MAX_HOSTS:
        raise ValueError("Invalid fleet cache snapshot")
    content = json.dumps({"schema": 1, "written_at": time.time(), "publisher": _publisher_identity(os.getpid()), "hosts": snapshot}, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
    if len(content) > MAX_CACHE:
        raise ValueError("Fleet cache exceeds its limit")
    directory = state_dir()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = directory.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o022:
        raise ValueError("Fleet state directory is writable by another user")
    descriptor, temporary = tempfile.mkstemp(prefix=".fleet-cache-", dir=directory)
    path = directory / "fleet-cache.json"
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content); stream.flush(); os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return path


def load_cache():
    path = state_dir() / "fleet-cache.json"
    try:
        with path.open("rb") as stream:
            info = os.fstat(stream.fileno())
            if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                return []
            content = stream.read(MAX_CACHE + 1)
        if len(content) > MAX_CACHE:
            return []
        value = json.loads(content, parse_constant=_reject_constant)
        if not isinstance(value, dict) or value.get("schema") != 1 or not isinstance(value.get("hosts"), list) or len(value["hosts"]) > MAX_HOSTS or not all(isinstance(host, dict) for host in value["hosts"]):
            return []
        publisher = value.get("publisher")
        active = isinstance(publisher, dict) and type(publisher.get("pid")) is int and publisher == _publisher_identity(publisher["pid"])
        records = _age_records(value["hosts"], time.time())
        for record in records:
            record["cache_active"] = bool(active)
            if not active and record.get("state") == "online":
                record.update(state="stale", stale=True)
        return records
    except (OSError, ValueError, TypeError, RecursionError):
        return []
