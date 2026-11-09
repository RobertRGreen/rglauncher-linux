#!/usr/bin/env python3
"""Compile the exact bridge and test bounded transport plus real GTK menu signals.

The optional GTK fixture uses its own Broadway backend, never the active desktop.
"""
import argparse
import collections
import json
import os
from pathlib import Path
import shlex
import socket
import struct
import subprocess
import tempfile
import threading
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--broadway', action='store_true')
    args = parser.parse_args(); args.artifacts.mkdir(parents=True, exist_ok=True)
    package = Path(__file__).resolve().parents[1]
    probe = args.artifacts/'probe'
    flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'gtk+-3.0'], text=True))
    subprocess.run(['g++', '-std=c++20', '-O2', '-Wall', '-Wextra', '-Wno-deprecated-declarations',
                    '-I'+str(package), str(package/'tests/probe.cpp'), '-o', str(probe), *flags], check=True)
    output = subprocess.check_output([str(probe), 'format'], text=True).splitlines()
    first, second = json.loads(output[0]), json.loads(output[2])
    assert first['output'] == 'DP-1"\\\n\t\r\b\f'
    assert first['menu'] == 'menu"\\\n'
    assert second['output'] == '显示-1' and second['command'] == 'popup-close'
    assert output[-1] == 'bounded'
    temporary = tempfile.TemporaryDirectory(prefix='rgl-menu-')
    path = Path(temporary.name)/'test.sock'
    server = socket.socket(socket.AF_UNIX); server.bind(str(path)); server.listen(64)
    server.settimeout(.1)
    received, errors, stop = [], [], threading.Event()

    def collect():
        while not stop.is_set():
            try: client, _ = server.accept()
            except socket.timeout: continue
            try:
                client.settimeout(.5)
                pid, uid, gid = struct.unpack('3i', client.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                raw = b''
                while True:
                    part = client.recv(4096)
                    if not part: break
                    raw += part
                received.append({'payload': json.loads(raw), 'pid': pid, 'uid': uid, 'gid': gid})
            except Exception as error: errors.append(str(error))
            finally: client.close()

    worker = threading.Thread(target=collect); worker.start()
    env = os.environ.copy(); env.update(RGL_SHELF_SOCKET=str(path), RGL_SHELF_OUTPUT='DP-test')
    server_process = None
    try:
        sent = subprocess.run([str(probe), 'send'], env=env, capture_output=True, text=True, check=True)
        assert sent.stdout.strip() == 'sent'
        until = time.monotonic()+1
        while not received and time.monotonic() < until: time.sleep(.01)
        assert received[0]['payload'] == {'command': 'popup-open', 'output': 'DP-test', 'menu': 'fixture-1'}
        transport = received.pop(0)
        env['RGL_SHELF_SOCKET'] = str(path)+'.missing'
        started = time.monotonic()
        missed = subprocess.run([str(probe), 'send'], env=env, capture_output=True, text=True, timeout=1, check=True)
        missing_elapsed = time.monotonic()-started
        assert missed.stdout.strip() == 'miss'
        # Fill a listener's accept queue: the GTK callback must not wait for it.
        blocked = socket.socket(socket.AF_UNIX)
        blocked_path = Path(temporary.name)/'full.sock'
        blocked.bind(str(blocked_path)); blocked.listen(1)
        fillers = []
        try:
            for _ in range(4):
                client = socket.socket(socket.AF_UNIX); client.setblocking(False)
                try: client.connect(str(blocked_path)); fillers.append(client)
                except BlockingIOError: client.close(); break
            env['RGL_SHELF_SOCKET'] = str(blocked_path)
            started = time.monotonic()
            full = subprocess.run([str(probe), 'send'], env=env, capture_output=True, text=True, timeout=1, check=True)
            backlog_elapsed = time.monotonic()-started
            assert full.stdout.strip() == 'miss'
        finally:
            for client in fillers: client.close()
            blocked.close()
        env['RGL_SHELF_SOCKET'] = str(path)
        gtk = None
        if args.broadway:
            # Own unique abstract display number and bound only to localhost.
            display = 1000+os.getpid()%20000
            log = (args.artifacts/'broadway.log').open('w')
            server_process = subprocess.Popen(['broadwayd', '-a', '127.0.0.1', '-p', '0', ':'+str(display)],
                                              stdout=log, stderr=log)
            time.sleep(.3)
            assert server_process.poll() is None, 'Private Broadway backend failed'
            env.update(GDK_BACKEND='broadway', BROADWAY_DISPLAY=':'+str(display))
            fixture = subprocess.run([str(probe), 'gtk'], env=env, capture_output=True, text=True, timeout=10)
            (args.artifacts/'gtk-stderr.log').write_text(fixture.stderr)
            assert fixture.returncode == 0, fixture.stderr
            time.sleep(.15)
            assert not errors, errors
            by_id = collections.defaultdict(list)
            for item in received:
                assert item['uid'] == os.getuid() and item['pid'] > 0
                assert item['payload']['output'] == 'DP-test'
                by_id[item['payload']['menu']].append(item['payload']['command'])
            assert len(by_id) == 3, dict(by_id)
            assert all(events == ['popup-open', 'popup-close'] for events in by_id.values()), dict(by_id)
            gtk = {'unique_menus': len(by_id), 'events': received, 'private_backend': 'Broadway',
                   'nested_dynamic_destroy_balance': True}
        record = {'formatter_escape_unicode_and_bounds': True, 'transport': transport,
                  'missing_socket_seconds': missing_elapsed, 'full_backlog_seconds': backlog_elapsed,
                  'gtk': gtk, 'errors': errors}
        (args.artifacts/'result.json').write_text(json.dumps(record, indent=2)+'\n')
        print(json.dumps(record, indent=2))
    finally:
        stop.set(); worker.join(timeout=2); server.close(); path.unlink(missing_ok=True)
        temporary.cleanup()
        if server_process:
            server_process.terminate(); server_process.wait(timeout=3)


if __name__ == '__main__': main()
