import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from rglauncher_linux import fleet

SPEC = importlib.util.spec_from_file_location("fleet_sampler_fixture", Path(__file__).resolve().parents[1] / "share/fleet/sample.py")
sampler = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sampler)


def sample(now=1000):
    return {"schema": 1, "sampled_at": now, "metrics": {
        "cpu": {"percent": 12.5, "cores": 2, "updated_at": now},
        "memory": {"total_bytes": 1000, "used_bytes": 200, "available_bytes": 800, "percent": 20, "updated_at": now},
        "swap": {"total_bytes": 0, "used_bytes": 0, "percent": 0, "updated_at": now},
        "load": {"one": .1, "five": .2, "fifteen": .3, "updated_at": now},
        "uptime_seconds": 60,
        "network": {"rx_bytes_per_second": 100, "tx_bytes_per_second": 200, "interfaces": ["fixture0"], "updated_at": now},
        "disk": {"read_bytes_per_second": 0, "write_bytes_per_second": 1024, "filesystems": [], "updated_at": now, "filesystems_updated_at": now - 3},
        "services": {"failed": [], "error": None, "updated_at": now - 3},
        "containers": {"items": [], "error": "Docker unavailable", "updated_at": now - 3},
        "processes": [{"pid": 1, "name": "fixture worker", "cpu_percent": None, "memory_bytes": 100}],
    }}


class FleetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="rgl-fleet-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        environment = {"HOME": str(self.root), "XDG_CONFIG_HOME": str(self.root / "config"), "XDG_STATE_HOME": str(self.root / "state")}
        self.environment = patch.dict(os.environ, environment)
        self.environment.start(); self.addCleanup(self.environment.stop)
        self.host = fleet.Host("fixture", "Fixture node", "fixture-node", group="Test")

    def wait(self, predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.02)
        self.fail("Fixture condition was not reached before timeout")

    def fake_ssh(self, mode):
        executable = self.root / "ssh"
        executable.write_text('''#!/usr/bin/env python3
import json,os,sys,time
from pathlib import Path
Path(os.environ["FAKE_FLEET_PID"]).write_text(str(os.getpid()))
source=sys.stdin.buffer.read()
Path(os.environ["FAKE_FLEET_ARGV"]).write_text(json.dumps({"args":sys.argv[1:],"bytes":len(source),"askpass":os.environ.get("SSH_ASKPASS_REQUIRE")}))
mode=os.environ["FAKE_FLEET_MODE"]
if mode == "auth":
    print("Permission denied (publickey,password).",file=sys.stderr);sys.exit(255)
if mode == "hostkey":
    print("Host key verification failed.",file=sys.stderr);sys.exit(255)
if mode == "orphan":
    child=os.fork()
    if child:
        Path(os.environ["FAKE_FLEET_CHILD"]).write_text(str(child));sys.exit(0)
    import signal
    signal.signal(signal.SIGTERM,signal.SIG_IGN)
    while True: time.sleep(.1)
if mode == "oversize":
    print("x"*300000,flush=True);time.sleep(10)
if mode == "invalid":
    print("interactive shell banner",flush=True);time.sleep(10)
if mode == "stderr":
    sys.stderr.write("x"*100000);sys.stderr.flush()
if mode != "stall":
    print(os.environ["FAKE_FLEET_SAMPLE"],flush=True)
while True: time.sleep(.1)
''')
        executable.chmod(0o755)
        environment = {"PATH": str(self.root) + os.pathsep + os.environ["PATH"], "FAKE_FLEET_MODE": mode,
                       "FAKE_FLEET_SAMPLE": json.dumps(sample()), "FAKE_FLEET_PID": str(self.root / "ssh.pid"),
                       "FAKE_FLEET_ARGV": str(self.root / "ssh.args"), "FAKE_FLEET_CHILD": str(self.root / "ssh.child")}
        patched = patch.dict(os.environ, environment)
        patched.start(); self.addCleanup(patched.stop)

    def test_host_validation_paths_aliases_and_no_option_injection(self):
        for target in ("fixture-alias", "user@fixture.invalid", "user@2001:db8::1", "[2001:db8::1]"):
            self.assertEqual(fleet.Host("fixture", "Fixture", target).target, target)
        for target in ("-Fconfig", "fixture node", "user@host;id", "$(id)", "user\nnode", "ssh://fixture", "a@b@c"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                fleet.Host("fixture", "Fixture", target)
        for port in (0, 65536, True, "22"):
            with self.assertRaises(ValueError):
                fleet.Host("fixture", "Fixture", "fixture", port=port)
        host = fleet.Host("fixture", "Fixture", "fixture", identity_file="~/key fixture", known_hosts_file="~/known_hosts")
        self.assertEqual(host.identity_file, str(self.root / "key fixture"))
        with self.assertRaises(Exception):
            host.target = "different"

    def test_private_config_empty_duplicate_and_bounded_interval(self):
        self.assertEqual(fleet.load_hosts(), [])
        self.assertEqual(fleet.load_interval(), 2)
        path = self.root / "config/rglauncher-linux/servers.json"
        path.parent.mkdir(parents=True)
        host = {"id": "fixture", "label": "Fixture", "target": "fixture", "group": "Test"}
        path.write_text(json.dumps({"hosts": [host], "interval": 2.5}))
        self.assertEqual(fleet.load_hosts()[0].group, "Test")
        self.assertEqual(fleet.load_interval(), 2.5)
        path.write_text(json.dumps({"hosts": [host, host]}))
        with self.assertRaises(ValueError): fleet.load_hosts()
        for value in (True, 0, 61, "2", float("inf"), 10**400):
            path.write_text(json.dumps({"hosts": [], "interval": value}))
            with self.assertRaises(ValueError): fleet.load_interval()

    def test_ssh_stream_and_interactive_argv_have_distinct_auth_mechanisms(self):
        host = fleet.Host("fixture", "Fixture", "user@fixture", port=2200, identity_file="~/identity file", known_hosts_file="~/known hosts")
        argv = fleet.ssh_argv(host)
        self.assertIn("StrictHostKeyChecking=yes", argv)
        self.assertIn("BatchMode=yes", argv)
        self.assertIn("ClearAllForwardings=yes", argv)
        self.assertIn("PermitLocalCommand=no", argv)
        self.assertEqual(argv[-6:], [host.target, "python3", "-B", "-u", "-", "2"])
        interactive = fleet.ssh_argv(host, interactive=True)
        self.assertNotIn("BatchMode=yes", interactive)
        self.assertEqual(interactive[-2:], ["--", host.target])
        self.assertNotIn("python3", interactive)

    def test_errors_are_classified_without_raw_stderr_or_secret_commands(self):
        cases = [("Permission denied (publickey).", "auth_required"), ("Host key verification failed.", "host_key_error"),
                 ("WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!", "host_key_error"),
                 ("ssh: connect to host fixture: Connection refused", "unreachable"),
                 ("python3: command not found", "unsupported"), ("sensitive arbitrary banner", "error")]
        for message, expected in cases:
            state, error = fleet.classify_error(message)
            self.assertEqual(state, expected)
            self.assertNotIn(message, error)

    def test_sample_validation_normalizes_clock_skew_and_cached_group_ages(self):
        metrics = fleet._decode_sample(json.dumps(sample(1000)), 9000)
        self.assertEqual(metrics["sampled_at"], 9000)
        self.assertEqual(metrics["cpu"]["updated_at"], 9000)
        self.assertEqual(metrics["services"]["updated_at"], 8997)
        self.assertEqual(metrics["disk"]["filesystems_updated_at"], 8997)
        for value in ({"schema": 2}, {"schema": 1, "error": {"code": "unsupported"}}, {"schema": 1, "metrics": {}, "sampled_at": 0}):
            with self.assertRaises(ValueError): fleet._decode_sample(json.dumps(value), 9000)
        with self.assertRaises(ValueError): fleet._decode_sample('{"schema":1,"sampled_at":NaN}', 9000)
        for group, key, content in (("cpu", "cores", 10**400), ("memory", "percent", -1), ("cpu", "percent", 101)):
            value = sample(); value["metrics"][group][key] = content
            with self.assertRaises(ValueError): fleet._decode_sample(json.dumps(value), 9000)
        value = sample()
        value["metrics"]["processes"][0]["cmdline"] = "not a permitted telemetry field"
        self.assertNotIn("cmdline", fleet._decode_sample(json.dumps(value), 9000)["processes"][0])

    def test_exited_ssh_leader_cannot_leave_proxy_descendant_after_stop(self):
        self.fake_ssh("orphan")
        monitor = fleet.FleetMonitor([self.host]); self.addCleanup(monitor.stop)
        monitor.start()
        self.wait(lambda: (self.root / "ssh.child").exists())
        child = int((self.root / "ssh.child").read_text())
        monitor.stop()
        def terminated():
            try:
                status = Path("/proc", str(child), "stat").read_text().rsplit(")", 1)[1].split()[0]
                return status == "Z"  # init owns reaping after the SSH parent exited
            except (FileNotFoundError, ProcessLookupError):
                return True
        self.wait(terminated)
        self.assertFalse(any(thread.is_alive() for thread in monitor._threads))

    def test_fake_persistent_stream_is_bounded_and_stop_has_no_orphan(self):
        self.fake_ssh("online")
        monitor = fleet.FleetMonitor([self.host])
        self.addCleanup(monitor.stop)
        monitor.start()
        self.wait(lambda: monitor.snapshot()[0]["state"] == "online")
        record = monitor.snapshot()[0]
        self.assertLess(record["age"], 1)
        self.assertGreater(record["observed_at"], 1000)
        args = json.loads((self.root / "ssh.args").read_text())
        self.assertGreater(args["bytes"], 1000)
        self.assertEqual(args["askpass"], "never")
        pid = int((self.root / "ssh.pid").read_text())
        start = time.monotonic(); stopped = monitor.stop()
        self.assertLess(time.monotonic() - start, 2.5)
        self.assertEqual(stopped[0]["state"], "stopped")
        self.assertIsNotNone(stopped[0]["metrics"])
        self.assertFalse(Path("/proc", str(pid)).exists())
        self.assertFalse(any(thread.is_alive() for thread in monitor._threads))

    def test_auth_and_host_key_failures_do_not_background_retry(self):
        for mode, expected in (("auth", "auth_required"), ("hostkey", "host_key_error")):
            with self.subTest(mode=mode):
                self.fake_ssh(mode)
                monitor = fleet.FleetMonitor([self.host]); self.addCleanup(monitor.stop)
                monitor.start(); self.wait(lambda: monitor.snapshot()[0]["state"] == expected)
                self.wait(lambda: not any(thread.is_alive() for thread in monitor._threads))
                self.assertIsNone(monitor.snapshot()[0]["metrics"])
                monitor.stop()

    def test_invalid_oversized_or_noisy_streams_cannot_fake_health(self):
        for mode in ("invalid", "oversize", "stderr"):
            with self.subTest(mode=mode):
                self.fake_ssh(mode)
                monitor = fleet.FleetMonitor([self.host]); self.addCleanup(monitor.stop)
                monitor.start()
                expected = "online" if mode == "stderr" else "unsupported"
                self.wait(lambda: monitor.snapshot()[0]["state"] == expected)
                monitor.stop()
                self.assertFalse(monitor._processes)

    def test_stale_snapshot_is_clocked_without_a_new_stream_message(self):
        monitor = fleet.FleetMonitor([self.host])
        monitor._records[self.host.id].update(state="online", observed_at=1000, metrics={"cpu": {"percent": 10}})
        with patch.object(fleet.time, "time", return_value=1009):
            record = monitor.snapshot()[0]
        self.assertEqual(record["state"], "stale")
        self.assertTrue(record["stale"])
        self.assertEqual(record["age"], 9)
        record["metrics"]["cpu"]["percent"] = 100
        self.assertEqual(monitor._records[self.host.id]["metrics"]["cpu"]["percent"], 10)

    def test_monitor_age_is_monotonic_when_local_wall_clock_moves_back(self):
        monitor = fleet.FleetMonitor([self.host])
        with patch.object(fleet.time, "monotonic", return_value=100):
            monitor._set(self.host, state="online", observed_at=1000, metrics={"cpu": {"percent": 10}})
        with patch.object(fleet.time, "time", return_value=500), patch.object(fleet.time, "monotonic", return_value=109):
            record = monitor.snapshot()[0]
        self.assertEqual(record["state"], "stale")
        self.assertEqual(record["age"], 9)

    def test_stop_during_startup_and_stalled_stream_is_bounded(self):
        self.fake_ssh("stall")
        monitor = fleet.FleetMonitor([self.host]); self.addCleanup(monitor.stop)
        monitor.start(); self.wait(lambda: (self.root / "ssh.args").exists())
        started = time.monotonic(); monitor.stop()
        self.assertLess(time.monotonic() - started, 2.5)
        self.assertFalse(any(thread.is_alive() for thread in monitor._threads))
        monitor.start(); monitor.stop()
        self.assertFalse(any(thread.is_alive() for thread in monitor._threads))

    def test_cache_is_private_atomic_and_read_only_summary_ages_it(self):
        snapshot = [{"id": "fixture", "label": "Fixture", "target": "fixture", "state": "online", "observed_at": 1000, "metrics": {"cpu": {"percent": 5}}}]
        path = fleet.publish_cache(snapshot)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        with patch.object(fleet.time, "time", return_value=1009), patch.object(fleet.subprocess, "Popen", side_effect=AssertionError("Cache must not connect")):
            result = fleet.load_cache()
        self.assertEqual(result[0]["state"], "stale")
        with patch.object(fleet.time, "time", return_value=1001), patch.object(fleet, "_publisher_identity", return_value=None):
            result = fleet.load_cache()
        self.assertEqual(result[0]["state"], "stale")
        self.assertFalse(result[0]["cache_active"])
        for observed, metrics in ((None, {"cpu": {"percent": 5}}), (1000, None), (2000, {"cpu": {"percent": 5}})):
            invalid = [{**snapshot[0], "observed_at": observed, "metrics": metrics}]
            fleet.publish_cache(invalid)
            with patch.object(fleet.time, "time", return_value=1001):
                self.assertEqual(fleet.load_cache()[0]["state"], "stale")
        path.chmod(0o644)
        self.assertEqual(fleet.load_cache(), [])
        path.chmod(0o600); path.write_text("not JSON")
        self.assertEqual(fleet.load_cache(), [])

    def test_transport_identity_changes_with_target_port_or_key_profile(self):
        base = fleet.host_transport_id(self.host)
        for host in (fleet.Host("fixture", "Fixture", "different"), fleet.Host("fixture", "Fixture", self.host.target, port=2200), fleet.Host("fixture", "Fixture", self.host.target, identity_file="~/different-key")):
            self.assertNotEqual(base, fleet.host_transport_id(host))
        row = fleet.FleetMonitor([self.host]).snapshot()[0]
        self.assertEqual(row["transport_id"], base)
        self.assertEqual(row["port"], 22)


class SamplerTests(unittest.TestCase):
    def test_proc_parsers_guest_memory_network_and_process_names_not_args(self):
        self.assertEqual(sampler.parse_cpu("cpu  100 2 30 400 5 6 7 8 90 2\n"), (558, 405))
        memory, swap = sampler.parse_memory("MemTotal: 1000 kB\nMemAvailable: 400 kB\nSwapTotal: 200 kB\nSwapFree: 150 kB\n")
        self.assertEqual(memory["used_bytes"], 600 * 1024)
        self.assertEqual(swap["percent"], 25)
        network = sampler.parse_network("lo: 5 0 0 0 0 0 0 0 5 0 0 0 0 0 0 0\nfixture0: 10 0 0 0 0 0 0 0 20 0 0 0 0 0 0 0\n")
        self.assertEqual(network, {"fixture0": (10, 20)})
        fields = ["S"] + ["0"] * 23
        fields[11], fields[12], fields[19], fields[21] = "4", "6", "100", "3"
        value = sampler.parse_process("42 (worker ) name) " + " ".join(fields), 4096)
        self.assertEqual(value["name"], "worker ) name")
        self.assertEqual(value["ticks"], 10)
        self.assertEqual(value["memory_bytes"], 12288)
        filesystems = sampler.parse_filesystems("Filesystem 1B-blocks Used Available Use% Mounted on\n/dev/fixture 1000 200 800 20% /path with spaces\n")
        self.assertEqual(filesystems[0]["mount"], "/path with spaces")

    def test_sampler_rates_and_five_second_heavy_cache_from_proc_fixtures(self):
        with tempfile.TemporaryDirectory(prefix="rgl-proc-test-") as temporary:
            root = Path(temporary); proc, sys_root = root / "proc", root / "sys"
            (proc / "net").mkdir(parents=True); (sys_root / "block/vda").mkdir(parents=True)
            clock = [1000]
            def put(name, value): (proc / name).write_text(value)
            put("stat", "cpu  10 0 10 80 0 0 0 0\n")
            put("meminfo", "MemTotal: 1000 kB\nMemAvailable: 400 kB\nSwapTotal: 0 kB\n")
            put("net/dev", "fixture0: 100 0 0 0 0 0 0 0 200 0 0 0 0 0 0 0\n")
            put("diskstats", "252 0 vda 0 0 2 0 0 0 4 0 0 0 0\n")
            put("loadavg", "0.1 0.2 0.3 1/2 3\n"); put("uptime", "100 20\n")
            calls = []
            def command(argv):
                calls.append(argv)
                if argv[0] == "df": return "Filesystem 1B-blocks Used Available Use% Mounted on\n/dev/vda 1000 200 800 20% /\n", None
                if argv[0] == "systemctl": return "fixture.service loaded failed failed Fixture unit\n", None
                return '{"ID":"abc","Names":"fixture","State":"running","Status":"Up 1 hour"}\n', None
            with patch.object(sampler.shutil, "which", return_value="/fixture/tool"):
                instance = sampler.Sampler(proc, sys_root, command, clock=lambda: clock[0], monotonic=lambda: clock[0])
                first = instance.sample()["metrics"]
                self.assertIsNone(first["cpu"]["percent"])
                self.assertEqual(len(calls), 3)
                clock[0] = 1002
                put("stat", "cpu  20 0 10 90 0 0 0 0\n")
                put("net/dev", "fixture0: 2100 0 0 0 0 0 0 0 4200 0 0 0 0 0 0 0\n")
                put("diskstats", "252 0 vda 0 0 6 0 0 0 12 0 0 0 0\n")
                second = instance.sample()["metrics"]
                self.assertEqual(second["cpu"]["percent"], 50)
                self.assertEqual(second["network"]["rx_bytes_per_second"], 1000)
                self.assertEqual(second["disk"]["read_bytes_per_second"], 1024)
                self.assertEqual(second["disk"]["filesystems_updated_at"], 1000)
                self.assertEqual(second["disk"]["updated_at"], 1002)
                self.assertEqual(second["services"]["failed"][0]["unit"], "fixture.service")
                docker = next(argv for argv in calls if argv[0] == "docker")
                self.assertNotIn("{{json .}}", docker[-1])
                self.assertNotIn(".Command", docker[-1])
                self.assertEqual(len(calls), 3)
                clock[0] = 1006; instance.sample(); self.assertEqual(len(calls), 6)

    def test_read_only_command_output_and_time_are_bounded(self):
        output, error = sampler.command([sys.executable, "-c", "print('x'*10000)"], limit=256)
        self.assertIsNone(output); self.assertIsNotNone(error)
        started = time.monotonic()
        output, error = sampler.command([sys.executable, "-c", "import time;time.sleep(2)"], timeout=.05)
        self.assertIsNone(output); self.assertIsNotNone(error)
        self.assertLess(time.monotonic() - started, 1)


if __name__ == "__main__":
    unittest.main()
