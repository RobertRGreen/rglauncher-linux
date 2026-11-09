"""RGLauncher: Linux Edition command surface and application integration."""
import argparse
import importlib.util
import json
import os
import hashlib
import platform
from pathlib import Path
import shutil
import subprocess
import sys
from . import __version__
from .paths import data_dir, config_dir, state_dir, release_root

APPS = {'apps': 'rofi-launcher', 'windows': 'hypr-windows', 'calc': 'calc-menu',
        'audio': 'audio-menu', 'wifi': 'wifi-menu', 'bluetooth': 'bt-menu'}


def command_app(name, args):
    if name == 'files':
        return subprocess.call(['thunar', *args])
    if name == 'terminal':
        return subprocess.call(['kitty', *args])
    path = release_root()/'bin'/APPS[name]
    if not path.is_file():
        raise RuntimeError('Application component is not installed: '+str(path))
    return subprocess.call([sys.executable, '-B', str(path), *args])


def doctor():
    required = {name: shutil.which(name) for name in ('hyprctl', 'waybar', 'thunar', 'kitty', 'pactl')}
    modules = {name: importlib.util.find_spec(name) is not None for name in ('gi', 'cairo', 'numpy', 'cryptography')}
    toolkits = {}
    try:
        import gi
        for name, version in (('Gtk', '3.0'), ('GtkLayerShell', '0.1')):
            try:
                gi.require_version(name, version); toolkits[name] = True
            except ValueError:
                toolkits[name] = False
    except ImportError:
        toolkits = {'Gtk': False, 'GtkLayerShell': False}
    backend = {'available': False, 'compatible': False}
    metadata = release_root()/'share/waybar/backend.json'
    binary = release_root()/'share/waybar/waybar'
    if metadata.exists() and binary.exists():
        spec = json.loads(metadata.read_text())
        backend = {'available': True, 'platform': spec['platform'], 'architecture': spec['architecture'],
                   'compatible': sys.platform == spec['platform'] and platform.machine() == spec['architecture'],
                   'digest_valid': hashlib.sha256(binary.read_bytes()).hexdigest() == spec['sha256'],
                   'features': spec.get('features', [])}
        # This is a locally pinned or signature-verified ELF, never a feed hook.
        if backend['compatible'] and backend['digest_valid']:
            result = subprocess.run(['ldd', str(binary)], capture_output=True, text=True, timeout=10)
            backend['shared_libraries_available'] = result.returncode == 0 and 'not found' not in result.stdout
        else:
            backend['shared_libraries_available'] = False
    return {'product': 'RGLauncher: Linux Edition', 'version': __version__,
            'required_commands': required, 'python_modules': modules,
            'optional_commands': {n: shutil.which(n) for n in ('amixer', 'code-oss', 'code', 'rofi', 'ssh')},
            'toolkits': toolkits, 'waybar_backend': backend,
            'session': {'wayland': bool(os.environ.get('WAYLAND_DISPLAY')),
                        'hyprland': bool(os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'))},
            'ok': all(required.values()) and all(modules.values()) and all(toolkits.values()) and
                  all(backend.get(name, False) for name in ('compatible','digest_valid','shared_libraries_available'))}


def updater():
    from .update import UpdateConfig, Updater
    path = config_dir()/'updates.json'
    if not path.is_file():
        raise RuntimeError('No update channel configured. Install a verified distribution first.')
    settings = json.loads(path.read_text())
    return Updater(UpdateConfig(data_dir=data_dir(), state_dir=state_dir(),
                                feed_url=settings['feed_url'], public_key=Path(settings['public_key']),
                                allow_file=settings.get('allow_file', False),
                                channel=settings.get('channel', 'stable')))


def preflight(path):
    """Only locally supplied callback; no executable hooks are read from a feed."""
    if not (Path(path)/'rglauncher_linux/cli.py').is_file():
        raise RuntimeError('Release is missing the RGLauncher entry point')
    if not (Path(path)/'LICENSE').is_file():
        raise RuntimeError('Release is missing its license')
    from .install import _required_payload
    _required_payload(Path(path))
    result = subprocess.run([sys.executable, '-B', '-c',
                             'import sys;sys.path.insert(0,sys.argv[1]);'
                             'from rglauncher_linux.cli import doctor;'
                             'assert doctor()["ok"], "Required dependency missing"', str(path)],
                            capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError('Release preflight failed: '+result.stderr[-1000:])


def _main(argv=None):
    parser = argparse.ArgumentParser(prog='rglauncher', description='RGLauncher: Linux Edition — Hyprland/Waybar desktop shell')
    parser.add_argument('--version', action='version', version=__version__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in [*APPS, 'files', 'terminal']:
        p = sub.add_parser(name); p.add_argument('arguments', nargs=argparse.REMAINDER)
    sub.add_parser('settings')
    p=sub.add_parser('servers');p.add_argument('action',nargs='?',default='open',choices=('open','status'))
    p.add_argument('--waybar',action='store_true')
    p = sub.add_parser('desktop'); p.add_argument('action', choices=('refresh',))
    p = sub.add_parser('editor'); p.add_argument('action', choices=('install',))
    p.add_argument('--variant', choices=('night','opaque','day'), default='night')
    p = sub.add_parser('doctor'); p.add_argument('--json', action='store_true')
    p = sub.add_parser('shelf'); p.add_argument('arguments', nargs=argparse.REMAINDER)
    p = sub.add_parser('install'); p.add_argument('--feed', required=True); p.add_argument('--public-key', type=Path, required=True)
    p.add_argument('--allow-file', action='store_true'); p.add_argument('--channel', choices=('stable','prerelease'), default='stable')
    p.add_argument('--enable-autoupdate', action='store_true')
    p = sub.add_parser('update'); p.add_argument('action', nargs='?', default='status', choices=('status','check','apply','rollback'))
    p.add_argument('--version', dest='release_version'); p.add_argument('--automatic', action='store_true')
    args = parser.parse_args(argv)
    if args.command in APPS or args.command in ('files', 'terminal'):
        return command_app(args.command, args.arguments)
    if args.command == 'doctor':
        result = doctor(); print(json.dumps(result, indent=2)); return 0 if result['ok'] else 1
    if args.command == 'settings':
        from .settings import main as settings_main
        return settings_main()
    if args.command == 'servers':
        from .servers import status,open_window
        return status(args.waybar) if args.action=='status' else open_window()
    if args.command == 'desktop':
        from .install import reconcile_current
        result = reconcile_current(activate=True)
        print(json.dumps(result, indent=2)); return 1 if result.get('status') == 'partial' else 0
    if args.command == 'editor':
        from .editor import install_editor
        print(json.dumps(install_editor(args.variant), indent=2)); return 0
    if args.command == 'shelf':
        from .shelf import main as shelf_main
        return shelf_main(args.arguments)
    if args.command == 'install':
        from .install import install
        result = install(args.feed, args.public_key, args.allow_file, args.channel, args.enable_autoupdate)
        print(json.dumps(result, indent=2)); return 1 if result.get('status') == 'partial' else 0
    service = updater()
    if args.automatic:
        settings = json.loads((config_dir()/'updates.json').read_text())
        if not settings.get('automatic', False):
            print(json.dumps({'status': 'automatic_updates_disabled'})); return 0
    if args.action == 'status':
        result = service.status()
    elif args.action == 'check':
        result = service.check()
    elif args.action == 'rollback':
        result = service.rollback(preflight=preflight)
    else:
        result = service.apply(version=args.release_version, preflight=preflight, automatic=args.automatic)
    if args.action in ('apply','rollback'):
        result['running_processes'] = 'unchanged'
        if result.get('changed') and not args.automatic and os.environ.get('HYPRLAND_INSTANCE_SIGNATURE') and os.environ.get('WAYLAND_DISPLAY'):
            from .install import reconcile_current
            activation = reconcile_current(activate=True)
            result['desktop_refresh'] = {'status':activation['status'], 'receipt':activation['manifest']}
            if activation['status'] == 'partial':
                print(json.dumps(result, indent=2)); return 1
            result['running_processes'] = 'shelf_refreshed; other_applications_unchanged'
    print(json.dumps(result, indent=2))
    return 0


def main(argv=None):
    from .update import UpdateError
    try:
        return _main(argv)
    except (UpdateError, RuntimeError, OSError, ValueError) as error:
        print('RGLauncher: '+str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
