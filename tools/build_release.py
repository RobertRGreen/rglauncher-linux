#!/usr/bin/env python3
"""Build curated flat-root USTAR releases; never sign, upload, install or run them."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import stat
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rglauncher_linux.update import PRODUCT, SCHEMA, UpdateError, Version, canonical_json, safe_path, validate_url, public_key
from tools.sign_release import build_manifest

BIN = ('rglauncher', 'rglauncher-shelf', 'rofi-launcher', 'hypr-windows', 'calc-menu',
       'audio-menu', 'wifi-menu', 'bt-menu', '_aether_score.py', '_aether_surfaces.py',
       '_aether_material.py', '_cyber_theme.py', '_cyber_gtk.py', '_cyber_particles.py',
       '_aether_desktop.py', '_aether_tokens.json', '_audiobus.py', '_audioeq.py',
       '_audioeq_ui.py', '_scarlett.py', '_wifi_secondary.py')
MODULES = ('__init__.py', 'cli.py', 'native.py', 'paths.py', 'shelf.py', 'update.py', 'install.py', 'settings.py', 'editor.py')
DOCS = ('build-release.md', 'native-theme.md', 'updates.md', 'vscode-theme.md',
        'component-provenance.json', 'installation.md', 'session.md', 'dependencies.md',
        'software.md', 'hyprland-session.md', 'releasing.md')
SYSTEMD = ('rglauncher-update.service', 'rglauncher-update.timer', 'rglauncher-shelf@.service',
           'rglauncher-session@.target')
DESKTOP = ('apps', 'files', 'calc', 'audio', 'settings', 'terminal', 'windows', 'wifi', 'bt')
ICON_SOURCES = ('generate.py', 'outline-symbolic.cpp', 'palette.json', 'render.py', 'verify.py', 'LICENSE', 'README.md')
TESTS = ('test_build_release.py', 'test_update.py', 'test_install.py', 'test_native.py', 'test_editor.py',
         'test_shelf.py', 'test_audio_initialization.py', 'test_product_defaults.py', 'native_shelf.py', 'native_render.py')
CONTEXTS = {'actions', 'apps', 'categories', 'devices', 'emblems', 'mimetypes', 'places', 'status'}
NAME = re.compile(r'[a-z0-9][a-z0-9.-]*\Z')
REQUIRED = ('LICENSE', 'THIRD_PARTY_NOTICES', 'share/instrument-score-aether/tokens.json',
            'share/waybar/config.jsonc', 'share/waybar/style.css', 'share/vscode/rglauncher-aether.vsix',
            'share/update-keys/rglauncher-2026.pub', *('bin/'+n for n in BIN),
            *('rglauncher_linux/'+n for n in MODULES), *('systemd/'+n for n in SYSTEMD))


def checked_file(root: Path, name: str):
    safe_path(name)
    path = root
    for part in Path(name).parts:
        path = path/part
        if path.is_symlink():
            raise UpdateError('Release allowlist contains a symlink: '+name)
    if not path.exists():
        return None
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise UpdateError('Release allowlist requires an unlinked regular file: '+name)
    return path


def select_files(root: Path, kind: str):
    """Names are code-reviewed; arbitrary files under an included tree are ignored."""
    names = {'LICENSE', 'THIRD_PARTY_NOTICES', 'README.md', 'pyproject.toml',
             'share/instrument-score-aether/tokens.json', 'share/waybar/config.jsonc',
             'share/waybar/style.css', 'share/waybar/backend.json', 'share/waybar/waybar',
             'share/waybar/LICENSE.Waybar', 'share/vscode/rglauncher-aether.vsix',
             'share/update-keys/rglauncher-2026.pub',
             'docs/images/icons.png', 'docs/images/editor-night.png',
             'share/hyprland/hyprland.lua', 'share/hyprland/window-navigation.lua',
             'share/hyprland/snap-layout.lua', 'share/hyprland/README.md',
             'packaging/waybar/LICENSE.Waybar'}
    names.update('bin/'+n for n in BIN)
    names.update('rglauncher_linux/'+n for n in MODULES)
    names.update('docs/'+n for n in DOCS)
    names.update('systemd/'+n for n in SYSTEMD)
    names.update('share/applications/rglauncher-'+n+'.desktop' for n in DESKTOP)
    registry_path = checked_file(root, 'assets/icons/generated/registry.json')
    required_icons = set()
    if registry_path:
        registry = json.loads(registry_path.read_text())
        for icon in registry['icons']:
            context = icon['context']
            aliases = [icon['id'], *icon.get('aliases', [])]
            if context not in CONTEXTS or not all(isinstance(n, str) and NAME.fullmatch(n) and '..' not in n for n in aliases):
                raise UpdateError('Invalid icon registry identity/context')
            for theme in ('aether-score', 'aether-score-light'):
                for alias in aliases:
                    for size in ('16x16', '24x24', '32x32', '48x48', 'scalable'):
                        required_icons.add(f'share/icons/{theme}/{size}/{context}/{alias}.svg')
                    symbolic = alias if alias.endswith('-symbolic') else alias+'-symbolic'
                    required_icons.add(f'share/icons/{theme}/symbolic/{context}/{symbolic}.svg')
            if kind == 'source':
                for relative in [*icon['files'].values(), *(p for sizes in icon.get('sized_files', {}).values() for p in sizes.values())]:
                    safe_path(relative)
                    if not relative.endswith('.svg') or relative.split('/')[0] not in ('color-dark', 'color-light', 'symbolic'):
                        raise UpdateError('Unexpected generated icon path')
                    names.add('assets/icons/generated/'+relative)
        for theme in ('aether-score', 'aether-score-light'):
            names.update(f'share/icons/{theme}/'+n for n in ('index.theme', 'PROVENANCE.txt', 'LICENSE'))
            required_icons.add(f'share/icons/{theme}/index.theme')
        if kind == 'source':
            names.update('assets/icons/generated/'+n for n in ('registry.json', 'files.sha256.json'))
            required_icons.update('assets/icons/'+n for n in ICON_SOURCES)
            required_icons.update('tools/'+n for n in ('build_release.py', 'build_icons.py', 'sign_release.py'))
    if kind == 'source':
        names.add('.github/workflows/ci.yml')
        names.discard('share/waybar/waybar'); names.discard('share/waybar/backend.json')
        names.update('assets/icons/'+n for n in ICON_SOURCES)
        names.update('tools/'+n for n in ('build_release.py', 'build_icons.py', 'sign_release.py'))
        names.update('packaging/waybar/'+n for n in ('build.py', 'README.md', 'shelf_popup.hpp',
                     '0001-hyprland-lua-workspace.patch', '0002-native-tray-popup-shelf.patch'))
        names.update(('packaging/arch/PKGBUILD', 'packaging/arch/README.md'))
        names.update('tests/'+n for n in TESTS)
        names.update('packaging/waybar/tests/'+n for n in ('probe.cpp', 'test_bridge.py'))
        names.update('vscode/'+n for n in ('build.py', 'file_icons.py', 'vsix.py', 'package.json', 'LICENSE',
                     'README.md', 'CHANGELOG.md', 'icons/LICENSE', 'icons/provenance.json',
                     'icons/aether-file-icons.json', 'tests/test_theme.py', 'tests/registered-color-ids.json'))
        names.update('vscode/themes/aether-'+n+'.json' for n in ('night', 'opaque', 'day'))
        icon_index = checked_file(root, 'vscode/icons/aether-file-icons.json')
        if icon_index:
            definitions = json.loads(icon_index.read_text())['iconDefinitions']
            for icon in definitions.values():
                relative = icon['iconPath']
                relative = relative[2:] if relative.startswith('./') else relative
                safe_path(relative)
                if not re.fullmatch(r'(dark|light)/[a-z0-9][a-z0-9_-]*\.svg', relative):
                    raise UpdateError('Unexpected VS Code icon path')
                names.add('vscode/icons/'+relative)
    names.update(required_icons)
    selected = {name: path for name in sorted(names) if (path := checked_file(root, name)) is not None}
    missing = (set(REQUIRED)|required_icons)-selected.keys()
    if missing:
        raise UpdateError('Required release files missing: '+', '.join(sorted(missing)))
    return selected


def compatibility(root, architecture, kind):
    if not re.fullmatch(r'[a-z0-9_+-]{1,32}', architecture):
        raise UpdateError('Invalid architecture')
    result = {'platform': 'linux', 'architectures': ['source'] if kind == 'source' else [architecture]}
    backend_path = checked_file(root, 'share/waybar/backend.json') if kind == 'binary' else None
    binary = checked_file(root, 'share/waybar/waybar') if kind == 'binary' else None
    if bool(binary) != bool(backend_path):
        raise UpdateError('Native Waybar binary and backend metadata must be supplied together')
    if binary:
        metadata = json.loads(backend_path.read_text())
        if metadata.get('platform') != 'linux' or metadata.get('architecture') != architecture:
            raise UpdateError('Native backend architecture/platform mismatch')
        if metadata.get('sha256') != hashlib.sha256(binary.read_bytes()).hexdigest():
            raise UpdateError('Native backend digest mismatch')
        if not checked_file(root, 'packaging/waybar/LICENSE.Waybar'):
            raise UpdateError('Native Waybar requires its upstream license')
        result['backend'] = {key: metadata[key] for key in ('platform', 'architecture', 'sha256', 'source_revision', 'features') if key in metadata}
        canonical_json(result)
    return result


def build_release(source, output, version, kind='binary', architecture=None, *,
                  artifact_url=None, issued_at=None, expires_at=None, source_revision=None):
    Version(version)
    if kind not in ('binary', 'source'):
        raise UpdateError('Unknown release kind')
    architecture = architecture or platform.machine().lower()
    source, output = Path(source).resolve(), Path(output).absolute()
    selected = select_files(source, kind)
    public_key(selected['share/update-keys/rglauncher-2026.pub'])
    compat = compatibility(source, architecture, kind)
    if source_revision is not None and not re.fullmatch(r'[0-9a-f]{40,64}', source_revision):
        raise UpdateError('Source revision must be a full hexadecimal commit digest')
    if any(x is not None for x in (artifact_url, issued_at, expires_at)) and not all(x is not None for x in (artifact_url, issued_at, expires_at)):
        raise UpdateError('Artifact URL, issuance and expiry must be supplied together')
    if artifact_url is not None:
        if kind != 'binary':
            raise UpdateError('Source distributions are not executable updater releases')
        validate_url(artifact_url, allow_file=True)
        if type(issued_at) is not int or type(expires_at) is not int or issued_at < 0 or expires_at <= issued_at:
            raise UpdateError('Invalid release issuance/expiry')
        canonical_json([issued_at, expires_at])
    output.mkdir(parents=True, exist_ok=False)
    payload = output/'payload'; payload.mkdir()
    metadata = {'schema': SCHEMA, 'product': PRODUCT, 'version': version, 'kind': kind, 'compatibility': compat}
    if source_revision:
        metadata['source_revision'] = source_revision
    contents = {}
    for name, path in selected.items():
        before = path.stat(); data = path.read_bytes(); after = path.stat()
        if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
            raise UpdateError('Source file changed during release capture: '+name)
        mode = 0o755 if before.st_mode & 0o111 else 0o644
        contents[name] = (data, mode)
    contents['release.json'] = (canonical_json(metadata)+b'\n', 0o644)
    inventory = []
    for name, (data, mode) in sorted(contents.items()):
        destination = payload/name; destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data); destination.chmod(mode)
        inventory.append({'path': name, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'mode': mode})
    suffix = 'source' if kind == 'source' else 'linux-'+architecture
    artifact = output/f'{PRODUCT}-{version}-{suffix}.tar.gz'
    with artifact.open('xb') as raw:
        with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0, compresslevel=9) as compressed:
            with tarfile.open(fileobj=compressed, mode='w', format=tarfile.USTAR_FORMAT, encoding='utf-8', errors='strict') as archive:
                for name, (data, mode) in sorted(contents.items()):
                    info = tarfile.TarInfo(safe_path(name)); info.size = len(data); info.mode = mode
                    info.uid = info.gid = info.mtime = 0; info.uname = info.gname = ''
                    archive.addfile(info, io.BytesIO(data))
    (output/'inventory.json').write_bytes(canonical_json(inventory)+b'\n')
    record = {**metadata, 'artifact': {'name': artifact.name, 'size': artifact.stat().st_size,
               'sha256': hashlib.sha256(artifact.read_bytes()).hexdigest(), 'format': 'tar.gz'}, 'file_count': len(inventory)}
    (output/'release-metadata.json').write_bytes(canonical_json(record)+b'\n')
    if artifact_url is not None:
        document = build_manifest(payload, artifact, artifact_url, version, issued_at, expires_at)
        if document['files'] != inventory:
            raise UpdateError('Signing helper inventory mismatch')
        document['compatibility'] = compat
        if source_revision:
            document['source_revision'] = source_revision
        (output/'manifest.unsigned.json').write_bytes(canonical_json(document)+b'\n')
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--kind', choices=('binary', 'source'), default='binary')
    parser.add_argument('--architecture', default=None)
    parser.add_argument('--source-revision')
    parser.add_argument('--artifact-url'); parser.add_argument('--issued-at', type=int); parser.add_argument('--expires-at', type=int)
    args = vars(parser.parse_args(argv))
    try:
        print(json.dumps(build_release(**args), indent=2)); return 0
    except (OSError, ValueError, KeyError, TypeError, UpdateError, tarfile.TarError) as error:
        parser.error(str(error))


if __name__ == '__main__': raise SystemExit(main())
