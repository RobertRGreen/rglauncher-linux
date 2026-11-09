"""Bottom-edge, non-exclusive Waybar shelf for Hyprland.

The hidden shelf has a two-pixel input sensor and no polling animation. Waybar
owns its existing widgets/actions; one child per physical output permits local
reveal. Gtk layer surfaces never take keyboard focus. Cursor/layer queries run
only while a shelf is visible. Hotplug is reconciled without a session restart.
"""
from __future__ import annotations
from dataclasses import dataclass
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import struct
import subprocess
import sys
import time

POPUPS = {"cyber-carousel", "wifi-menu", "bt-menu", "audio-menu", "power-menu",
          "cast-menu", "calc-menu", "remote-menu", "display-layout", "keybind-guide",
          "vrdesk-menu", "rofi"}


def runtime_dir():
    identity = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE', 'default')+'|'+os.environ.get('RGL_SHELF_INSTANCE', 'main')
    session = hashlib.sha256(identity.encode()).hexdigest()[:12]
    base = Path(os.environ.get('XDG_RUNTIME_DIR', str(Path.home()/'.cache')))/('rglauncher-'+session)
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    return base


def hypr_json(command):
    result = subprocess.run(['hyprctl', command, '-j'], capture_output=True, text=True,
                            timeout=.7, check=True)
    return json.loads(result.stdout)


def logical_geometry(monitor):
    rotated = monitor.get('transform', 0) % 2
    width, height = monitor['width'], monitor['height']
    if rotated:
        width, height = height, width
    scale = monitor.get('scale', 1) or 1
    return monitor['x'], monitor['y'], width/scale, height/scale


@dataclass
class ShelfState:
    visible: bool = False
    outside_since: float | None = None
    pinned_until: float = 0

    def enter(self, now):
        changed = not self.visible
        self.visible = True
        self.outside_since = None
        self.pinned_until = max(self.pinned_until, now+.25)
        return changed

    def should_hide(self, now, in_region, popup_open, grace=.55):
        if not self.visible:
            return False
        if in_region or popup_open or now < self.pinned_until:
            self.outside_since = None
            return False
        if self.outside_since is None:
            self.outside_since = now
        return now-self.outside_since >= grace


def in_shelf_region(monitor, cursor, height=88):
    x, y, width, screen_height = logical_geometry(monitor)
    return x <= cursor['x'] < x+width and y+screen_height-height <= cursor['y'] <= y+screen_height


class ShelfManager:
    def __init__(self, *, binary=None, config=None, style=None):
        import gi
        gi.require_version('Gtk', '3.0')
        gi.require_version('Gdk', '3.0')
        gi.require_version('GtkLayerShell', '0.1')
        from gi.repository import Gtk, Gdk, GLib, GtkLayerShell
        self.Gtk, self.Gdk, self.GLib, self.Layer = Gtk, Gdk, GLib, GtkLayerShell
        self.runtime = runtime_dir()
        managed = Path(__file__).resolve().parents[1]/'share/waybar/waybar'
        patched = Path.home()/'.local/lib/waybar-lua/waybar'
        self.binary = binary or os.environ.get('RGL_WAYBAR_BINARY') or str(managed if managed.exists() else patched if patched.exists() else Path('/usr/bin/waybar'))
        config_home = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home()/'.config')))
        self.config = config or str(config_home/'waybar/config.jsonc')
        self.style = style or str(config_home/'waybar/style.css')
        self.children, self.sensors, self.monitors, self.states = {}, {}, {}, {}
        self.started, self.pending_show = {}, set()
        self.native_menus, self.monitor_signals = {}, {}
        self.popup_cache = (0, False)
        self.visible_timer = None
        self.log = open(self.runtime/'waybar.log', 'a', buffering=1)
        self.socket = socket.socket(socket.AF_UNIX)
        path = self.runtime/'shelf.sock'
        if path.exists():
            path.unlink()
        self.socket.bind(str(path)); os.chmod(path, 0o600)
        self.socket.listen(64); self.socket.setblocking(False)
        GLib.io_add_watch(self.socket.fileno(), GLib.IO_IN, self._command)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGHUP, self._reload_signal)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self._quit)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self._quit)
        display = Gdk.Display.get_default()
        display.connect('monitor-added', self._monitor_added)
        display.connect('monitor-removed', self._monitor_removed)
        for index in range(display.get_n_monitors()):
            self._watch_monitor(display.get_monitor(index))
        self.reconcile()
        GLib.timeout_add_seconds(3, self._health)

    def _base(self):
        from .editor import load_jsonc
        config = load_jsonc(Path(self.config).read_text())
        if not isinstance(config, dict):
            raise ValueError('The shelf requires one Waybar configuration object')
        return config

    def _child_config(self, monitor):
        component_dir = Path(__file__).resolve().parents[1]/'bin'
        if str(component_dir) not in sys.path:
            sys.path.insert(0, str(component_dir))
        # Development checkouts can use installed source components until the
        # explicit export step. Distributed releases always contain bin/.
        if not (component_dir/'_aether_desktop.py').exists():
            sys.path.append(str(Path.home()/'.local/bin'))
        from _aether_desktop import adapted_bar
        config = adapted_bar(self._base(), monitor)
        config.update({'position': 'bottom', 'layer': 'overlay', 'exclusive': False,
                       'passthrough': False, 'start_hidden': True,
                       'on-sigusr1': 'toggle', 'on-sigusr2': 'reload',
                       'margin-top': 0, 'margin-bottom': 8})
        # A preset such as dock overrides the global layer/exclusive settings.
        # Default mode uses our explicit overlay and zero-reservation settings.
        config.pop('mode', None)
        name = hashlib.sha256(monitor['name'].encode()).hexdigest()[:12]
        path = self.runtime/(name+'.json')
        path.write_text(json.dumps(config, indent=2)+'\n')
        return path

    def _start(self, monitor):
        name = monitor['name']
        env = os.environ.copy()
        if '/waybar-lua/' in self.binary or Path(self.binary).resolve() == Path(__file__).resolve().parents[1]/'share/waybar/waybar':
            env['WAYBAR_HYPRLAND_LUA'] = '1'
        env['RGL_SHELF_SOCKET'] = str(self.runtime/'shelf.sock')
        env['RGL_SHELF_OUTPUT'] = name
        # User styles stay intact. A final owned rule guarantees that Waybar's
        # mapped, click-through invisible mode is actually transparent.
        style = self.runtime/'shelf.css'
        style.write_text('@import url("'+Path(self.style).resolve().as_uri()+'");\n'
                         'window#waybar.hidden { opacity: 0; }\n')
        child = subprocess.Popen([self.binary, '-c', str(self._child_config(monitor)), '-s', str(style)],
                                 env=env, stdout=self.log, stderr=self.log)
        self.children[name] = child
        self.states[name] = ShelfState()
        self.started[name] = time.monotonic()
        self.native_menus[name] = set()

    def _stop(self, name):
        child = self.children.pop(name, None)
        if child and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=.5)
            except subprocess.TimeoutExpired:
                child.kill(); child.wait(timeout=1)
        sensor = self.sensors.pop(name, None)
        if sensor:
            sensor.destroy()
        self.states.pop(name, None)
        self.started.pop(name, None)
        self.pending_show.discard(name)
        self.native_menus.pop(name, None)

    def _watch_monitor(self, monitor):
        if monitor in self.monitor_signals:
            return
        self.monitor_signals[monitor] = [monitor.connect(name, lambda *_: self.GLib.timeout_add(300, self._reconcile_once))
                                        for name in ('notify::geometry', 'notify::scale-factor')]

    def _monitor_added(self, _display, monitor):
        self._watch_monitor(monitor)
        self.GLib.timeout_add(300, self._reconcile_once)

    def _monitor_removed(self, _display, monitor):
        for handler in self.monitor_signals.pop(monitor, []):
            monitor.disconnect(handler)
        self.GLib.timeout_add(300, self._reconcile_once)

    def _sensor(self, monitor):
        Gtk, Layer = self.Gtk, self.Layer
        sensor = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        sensor.set_title('RGLauncher shelf edge')
        Layer.init_for_window(sensor)
        Layer.set_namespace(sensor, 'rglauncher-edge')
        Layer.set_layer(sensor, Layer.Layer.OVERLAY)
        Layer.set_keyboard_mode(sensor, Layer.KeyboardMode.NONE)
        Layer.set_exclusive_zone(sensor, 0)
        display = self.Gdk.Display.get_default()
        gdk_monitor = display.get_monitor_at_point(monitor['x']+1, monitor['y']+1)
        if gdk_monitor:
            Layer.set_monitor(sensor, gdk_monitor)
        for edge in (Layer.Edge.BOTTOM, Layer.Edge.LEFT, Layer.Edge.RIGHT):
            Layer.set_anchor(sensor, edge, True)
        sensor.set_app_paintable(True)
        visual = sensor.get_screen().get_rgba_visual()
        if visual:
            sensor.set_visual(visual)
        provider = Gtk.CssProvider(); provider.load_from_data(b'window.rglauncher-edge {background:transparent; min-height:0;}')
        sensor.get_style_context().add_class('rglauncher-edge')
        sensor.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_USER+2)
        edge_box = Gtk.EventBox(); edge_box.set_visible_window(False)
        edge_box.set_size_request(-1, 2)
        edge_box.add_events(self.Gdk.EventMask.ENTER_NOTIFY_MASK)
        edge_box.connect('enter-notify-event', lambda *_: self.show(monitor['name']))
        sensor.add(edge_box); sensor.show_all()
        self.sensors[monitor['name']] = sensor

    def reconcile(self, force=False):
        monitors = {m['name']: m for m in hypr_json('monitors')
                    if not m.get('disabled') and not m['name'].startswith(('VIRT-', 'VR-'))}
        for name in list(self.children):
            if name not in monitors or force or logical_geometry(monitors[name]) != logical_geometry(self.monitors[name]):
                self._stop(name)
        self.monitors = monitors
        for name, monitor in monitors.items():
            if name not in self.children:
                self._start(monitor); self._sensor(monitor)

    def _reconcile_once(self):
        try:
            self.reconcile()
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            print('Shelf monitor reconciliation:', error, file=sys.stderr)
        return False

    def show(self, name=None, hold=0):
        if name is None:
            try:
                name = next((m['name'] for m in hypr_json('monitors') if m.get('focused')), None)
            except (OSError, ValueError, subprocess.SubprocessError):
                name = None
            name = name or next(iter(self.monitors), None)
        if name not in self.states:
            return False
        state, child = self.states[name], self.children[name]
        if child.poll() is not None:
            return False
        # SIGUSR1 before Waybar installs its handler can terminate the child.
        # Allow configuration startup to finish and confirm a caught signal.
        try:
            status = Path(f'/proc/{child.pid}/status').read_text()
            caught = int(next(line.split(':', 1)[1].strip() for line in status.splitlines()
                              if line.startswith('SigCgt:')), 16)
        except (OSError, StopIteration, ValueError):
            return False
        elapsed = time.monotonic()-self.started[name]
        if elapsed < .8 or not caught & (1 << (signal.SIGUSR1-1)):
            if elapsed > 5:
                return False
            if name not in self.pending_show:
                self.pending_show.add(name)
                self.GLib.timeout_add(120, self._deferred_show, name, hold)
            return False
        if state.enter(time.monotonic()):
            child.send_signal(signal.SIGUSR1)
        state.pinned_until = max(state.pinned_until, time.monotonic()+hold)
        if self.visible_timer is None:
            self.visible_timer = self.GLib.timeout_add(120, self._visible_tick)
        return True

    def _deferred_show(self, name, hold):
        self.pending_show.discard(name)
        if name in self.children and self.children[name].poll() is None:
            self.show(name, hold)
        return False

    def hide(self, name):
        if name in self.states and self.states[name].visible:
            child = self.children[name]
            if child.poll() is None:
                child.send_signal(signal.SIGUSR1)
            self.states[name] = ShelfState()

    def _popup_open(self, now):
        if now-self.popup_cache[0] < .5:
            return self.popup_cache[1]
        layers = hypr_json('layers')
        opened = any(layer.get('namespace') in POPUPS for monitor in layers.values()
                     for level in monitor.get('levels', {}).values() for layer in level)
        self.popup_cache = (now, opened)
        return opened

    def _visible_tick(self):
        try:
            cursor, now = hypr_json('cursorpos'), time.monotonic()
            popup = self._popup_open(now)
            for name, state in list(self.states.items()):
                if state.should_hide(now, in_shelf_region(self.monitors[name], cursor),
                                     popup or bool(self.native_menus.get(name))):
                    self.hide(name)
        except (OSError, ValueError, subprocess.SubprocessError):
            # Keep a shown shelf usable during a temporary IPC interruption.
            pass
        if not any(state.visible for state in self.states.values()):
            self.visible_timer = None
            return False
        return True

    def _health(self):
        for name, child in list(self.children.items()):
            if child.poll() is not None and name in self.monitors:
                try:
                    self._start(self.monitors[name])
                except (OSError, ValueError, subprocess.SubprocessError) as error:
                    print('Shelf child restart:', error, file=sys.stderr)
        return True

    def _reload_signal(self):
        try:
            self.reconcile(force=True)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            print('Shelf reload:', error, file=sys.stderr)
        return True

    def _command(self, *_):
        try:
            connection, _ = self.socket.accept()
        except BlockingIOError:
            return True
        connection.settimeout(.15)
        try:
            request = json.loads(connection.recv(4096))
            if not isinstance(request, dict):
                raise ValueError('Shelf request must be a JSON object')
            command = request.get('command')
            if command == 'show':
                self.show(request.get('output'), min(float(request.get('hold', 0)), 30))
            elif command == 'hide':
                for name in list(self.states):
                    self.hide(name)
                    self.native_menus[name].clear()
            elif command == 'reload':
                self.reconcile(force=True)
            elif command in ('popup-open', 'popup-close'):
                output, menu = request.get('output'), str(request.get('menu', ''))
                pid, uid, _gid = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                if (uid != os.getuid() or output not in self.children or
                        pid != self.children[output].pid or not menu or len(menu) > 128):
                    raise ValueError('Popup notification is not from the managed Waybar child')
                if command == 'popup-open':
                    self.native_menus[output].add(menu)
                    self.show(output)
                else:
                    self.native_menus[output].discard(menu)
            elif command == 'stop':
                self.GLib.idle_add(self._quit)
            elif command != 'status':
                raise ValueError('Unknown shelf command')
            response = {'outputs': {name: {'visible': state.visible, 'pid': self.children[name].pid}
                                    for name, state in self.states.items()}}
            connection.sendall(json.dumps(response).encode())
        except (OSError, ValueError, TypeError, subprocess.SubprocessError) as error:
            try: connection.sendall(json.dumps({'error': str(error)}).encode())
            except OSError: pass
        finally:
            connection.close()
        return True

    def _quit(self):
        for name in list(self.children): self._stop(name)
        self.socket.close()
        try: (self.runtime/'shelf.sock').unlink()
        except FileNotFoundError: pass
        self.Gtk.main_quit()
        return False


def control(command, output=None, hold=0):
    client = socket.socket(socket.AF_UNIX); client.settimeout(3)
    try:
        client.connect(str(runtime_dir()/'shelf.sock'))
        client.sendall(json.dumps({'command': command, 'output': output, 'hold': hold}).encode())
        return json.loads(client.recv(16384))
    finally:
        client.close()


def session_available():
    """A stale per-session unit exits quietly instead of a restart loop."""
    display = os.environ.get('WAYLAND_DISPLAY', '')
    runtime = os.environ.get('XDG_RUNTIME_DIR', '')
    signature = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE', '')
    if not display or not runtime or not signature:
        return False
    path = Path(display) if Path(display).is_absolute() else Path(runtime)/display
    if not path.is_socket():
        return False
    try:
        return bool(hypr_json('monitors'))
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', nargs='?', default='run', choices=('run', 'show', 'hide', 'status', 'reload', 'stop', 'probe'))
    parser.add_argument('--output'); parser.add_argument('--hold', type=float, default=0)
    parser.add_argument('--binary'); parser.add_argument('--config'); parser.add_argument('--style')
    args = parser.parse_args(argv)
    if args.command == 'probe':
        return 0 if session_available() else 1
    if args.command != 'run':
        print(json.dumps(control(args.command, args.output, args.hold), indent=2)); return 0
    lock = open(runtime_dir()/'shelf.lock', 'a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        print(json.dumps(control('reload'))); return 0
    manager = ShelfManager(binary=args.binary, config=args.config, style=args.style)
    manager.Gtk.main()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
