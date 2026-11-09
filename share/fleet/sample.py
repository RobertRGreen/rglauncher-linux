"""Read-only Linux telemetry streamed over stdin-fed Python; installs nothing."""
from __future__ import annotations

import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import sys
import time

MAX_COMMAND_BYTES = 65536


def text(path, limit=262144):
    with Path(path).open("rb") as stream:
        return stream.read(limit).decode("utf-8", errors="replace")


def clean(value, limit=160):
    return "".join(character if character.isprintable() else " " for character in str(value))[:limit]


def parse_cpu(value):
    fields = next(line.split()[1:] for line in value.splitlines() if line.startswith("cpu "))
    values = [int(field) for field in fields[:8]]  # guest is already included in user/nice
    return sum(values), values[3] + (values[4] if len(values) > 4 else 0)


def parse_memory(value):
    fields = {}
    for line in value.splitlines():
        key, separator, rest = line.partition(":")
        if separator:
            parts = rest.split()
            if parts and parts[0].isdigit():
                fields[key] = int(parts[0]) * (1024 if len(parts) > 1 and parts[1] == "kB" else 1)
    total = fields.get("MemTotal", 0)
    available = min(total, fields.get("MemAvailable", sum(fields.get(key, 0) for key in ("MemFree", "Buffers", "Cached"))))
    swap = fields.get("SwapTotal", 0)
    swap_used = max(0, swap - fields.get("SwapFree", 0))
    return ({"total_bytes": total, "used_bytes": max(0, total - available), "available_bytes": available,
             "percent": round(100 * (total - available) / total, 2) if total else None},
            {"total_bytes": swap, "used_bytes": swap_used, "percent": round(100 * swap_used / swap, 2) if swap else 0})


def parse_network(value):
    interfaces = {}
    for line in value.splitlines():
        name, separator, values = line.partition(":")
        fields = values.split()
        name = name.strip()
        if separator and name != "lo" and len(fields) >= 16:
            interfaces[clean(name, 64)] = (int(fields[0]), int(fields[8]))
            if len(interfaces) >= 128:
                break
    return interfaces


def rate(current, previous, elapsed):
    return round(max(0, current - previous) / elapsed, 2) if previous is not None and elapsed > 0 else None


def parse_process(value, pagesize):
    begin, end = value.find("("), value.rfind(")")
    fields = value[end + 1:].split()
    if begin < 1 or end < begin or len(fields) < 22:
        raise ValueError("Invalid process stat")
    return {"pid": int(value[:begin]), "name": clean(value[begin + 1:end], 120),
            "ticks": int(fields[11]) + int(fields[12]), "start": fields[19],
            "memory_bytes": max(0, int(fields[21])) * pagesize}


def parse_filesystems(value):
    result = []
    for line in value.splitlines()[1:]:
        fields = line.split(None, 5)
        if len(fields) != 6:
            continue
        try:
            total, used, available = map(int, fields[1:4])
            if total <= 0:
                continue
            result.append({"mount": clean(fields[5], 256), "total_bytes": total, "used_bytes": used,
                           "available_bytes": available, "percent": round(100 * used / total, 2)})
        except ValueError:
            continue
        if len(result) >= 64:
            break
    return result


def command(arguments, *, timeout=2, limit=MAX_COMMAND_BYTES):
    """Bound time and output before parsing; discard command stderr entirely."""
    process = None
    try:
        process = subprocess.Popen(arguments, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, close_fds=True,
                                   env={**os.environ, "LC_ALL": "C", "SYSTEMD_COLORS": "0"})
        output, deadline = bytearray(), time.monotonic() + timeout
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Query timed out")
                for key, _event in selector.select(min(.1, remaining)):
                    chunk = os.read(key.fd, min(4096, limit + 1 - len(output)))
                    if not chunk:
                        selector.unregister(key.fileobj)
                    else:
                        output.extend(chunk)
                    if len(output) > limit:
                        raise ValueError("Query output exceeded limit")
            process.wait(timeout=max(.01, deadline - time.monotonic()))
        return (output.decode("utf-8", errors="replace"), None) if process.returncode == 0 else (None, "Query unavailable")
    except (OSError, ValueError, TimeoutError, subprocess.TimeoutExpired):
        return None, "Query unavailable or timed out"
    finally:
        if process:
            if process.poll() is None:
                process.kill()
            try:
                process.wait(timeout=.5)
            except subprocess.TimeoutExpired:
                pass
            if process.stdout:
                process.stdout.close()


class Sampler:
    def __init__(self, proc="/proc", sys_root="/sys", runner=command, clock=time.time, monotonic=time.monotonic):
        self.proc, self.sys = Path(proc), Path(sys_root)
        self.run, self.clock, self.monotonic = runner, clock, monotonic
        self.previous_cpu = self.previous_network = self.previous_io = self.previous_time = None
        self.previous_processes = {}
        self.cached, self.cache_times = {}, {}
        self.clock_ticks = os.sysconf("SC_CLK_TCK")
        self.pagesize = os.sysconf("SC_PAGE_SIZE")

    def _filesystems(self, now):
        output, error = self.run(["df", "-P", "-B1", "-x", "tmpfs", "-x", "devtmpfs", "-x", "squashfs"])
        return {"items": parse_filesystems(output) if output is not None else [], "error": error, "updated_at": now}

    def _services(self, now):
        if not shutil.which("systemctl"):
            return {"failed": [], "error": "systemd unavailable", "updated_at": now}
        output, error = self.run(["systemctl", "--failed", "--no-legend", "--plain", "--no-pager", "--no-ask-password"])
        failed = []
        if output:
            for line in output.splitlines()[:64]:
                fields = line.strip().lstrip("● ").split(None, 4)
                if len(fields) >= 4 and fields[0].endswith((".service", ".socket", ".mount", ".timer", ".target", ".scope", ".path", ".automount", ".swap", ".slice")):
                    failed.append({"unit": clean(fields[0], 160), "description": clean(fields[4]) if len(fields) > 4 else ""})
        return {"failed": failed, "error": error, "updated_at": now}

    def _containers(self, now):
        if not shutil.which("docker"):
            return {"items": [], "error": "Docker unavailable", "updated_at": now}
        # Select fields before output; {{json .}} would also collect Command,
        # mounts and ports, none of which diagnostics needs or should retain.
        template = '{"ID":{{json .ID}},"Names":{{json .Names}},"State":{{json .State}},"Status":{{json .Status}}}'
        output, error = self.run(["docker", "ps", "-a", "--no-trunc", "--format", template])
        items = []
        try:
            for line in (output or "").splitlines()[:128]:
                value = json.loads(line)
                items.append({"id": clean(value.get("ID", ""), 64), "name": clean(value.get("Names", ""), 160),
                              "state": clean(value.get("State", ""), 48), "status": clean(value.get("Status", ""), 160)})
        except (ValueError, TypeError, AttributeError):
            error, items = "Docker response unavailable", []
        return {"items": items, "error": error, "updated_at": now}

    def _io(self):
        try:
            names = {path.name for path in (self.sys / "block").iterdir()
                     if not path.name.startswith(("loop", "ram", "dm-", "md", "sr"))}
            reads = writes = 0
            for line in text(self.proc / "diskstats").splitlines():
                fields = line.split()
                if len(fields) >= 10 and fields[2] in names:
                    reads += int(fields[5]) * 512
                    writes += int(fields[9]) * 512
            return (reads, writes) if names else None
        except (OSError, ValueError):
            return None

    def sample(self):
        now, monotonic = self.clock(), self.monotonic()
        elapsed = monotonic - self.previous_time if self.previous_time is not None else 0
        cpu = parse_cpu(text(self.proc / "stat"))
        total_delta = cpu[0] - self.previous_cpu[0] if self.previous_cpu else 0
        idle_delta = cpu[1] - self.previous_cpu[1] if self.previous_cpu else 0
        memory, swap = parse_memory(text(self.proc / "meminfo"))
        network = parse_network(text(self.proc / "net/dev"))
        rx = tx = 0
        if self.previous_network is not None:
            for name, current in network.items():
                previous = self.previous_network.get(name, current)
                rx += max(0, current[0] - previous[0]); tx += max(0, current[1] - previous[1])
        io = self._io()
        processes, process_counters = [], {}
        visited = 0
        with os.scandir(self.proc) as entries:
            for path in entries:
                if not path.name.isdigit():
                    continue
                visited += 1
                if visited > 4096:
                    break
                try:
                    value = parse_process(text(Path(path.path) / "stat", 4096), self.pagesize)
                    identity = (value["pid"], value.pop("start"))
                    ticks = value.pop("ticks")
                    previous = self.previous_processes.get(identity)
                    value["cpu_percent"] = round(100 * max(0, ticks - previous) / self.clock_ticks / elapsed, 2) if previous is not None and elapsed > 0 else None
                    process_counters[identity] = ticks
                    processes.append(value)
                except (OSError, ValueError, IndexError):
                    continue
        processes.sort(key=lambda value: (value["cpu_percent"] or 0, value["memory_bytes"]), reverse=True)
        load = text(self.proc / "loadavg", 512).split()
        for name, query in (("filesystems", self._filesystems), ("services", self._services), ("containers", self._containers)):
            if name not in self.cached or monotonic - self.cache_times[name] >= 5:
                self.cached[name] = query(self.clock())
                self.cache_times[name] = monotonic
        filesystems = self.cached["filesystems"]
        # Heavy observations have their own timestamps; lightweight rates never
        # pretend a five-second cached filesystem measurement is current.
        metrics = {
            "cpu": {"percent": round(100 * max(0, total_delta - idle_delta) / total_delta, 2) if total_delta > 0 else None,
                    "cores": os.cpu_count() or 1, "updated_at": now},
            "memory": {**memory, "updated_at": now}, "swap": {**swap, "updated_at": now},
            "load": {"one": float(load[0]), "five": float(load[1]), "fifteen": float(load[2]), "updated_at": now},
            "uptime_seconds": float(text(self.proc / "uptime", 512).split()[0]),
            "network": {"rx_bytes_per_second": round(rx / elapsed, 2) if self.previous_network is not None and elapsed > 0 else None,
                        "tx_bytes_per_second": round(tx / elapsed, 2) if self.previous_network is not None and elapsed > 0 else None,
                        "interfaces": sorted(network), "updated_at": now},
            "disk": {"filesystems": filesystems["items"], "filesystems_updated_at": filesystems["updated_at"],
                     "error": filesystems["error"], "read_bytes_per_second": rate(io[0], self.previous_io[0], elapsed) if io and self.previous_io else None,
                     "write_bytes_per_second": rate(io[1], self.previous_io[1], elapsed) if io and self.previous_io else None, "updated_at": now},
            "processes": processes[:12], "services": self.cached["services"], "containers": self.cached["containers"],
        }
        self.previous_cpu, self.previous_network, self.previous_io, self.previous_time = cpu, network, io, monotonic
        self.previous_processes = process_counters
        return {"schema": 1, "sampled_at": self.clock(), "metrics": metrics}


def main():
    if not Path("/proc/stat").is_file():
        print(json.dumps({"schema": 1, "error": {"code": "unsupported", "message": "Linux /proc is unavailable"}}), flush=True)
        return 1
    interval = max(1, min(60, float(sys.argv[1]) if len(sys.argv) > 1 else 2))
    sampler = Sampler()
    try:
        while True:
            started = time.monotonic()
            try:
                print(json.dumps(sampler.sample(), ensure_ascii=False, allow_nan=False, separators=(",", ":")), flush=True)
            except (OSError, ValueError, IndexError, StopIteration):
                print(json.dumps({"schema": 1, "error": {"code": "unsupported", "message": "Required Linux telemetry is unavailable"}}), flush=True)
                return 1
            time.sleep(max(0, interval - (time.monotonic() - started)))
    except (BrokenPipeError, KeyboardInterrupt):
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
