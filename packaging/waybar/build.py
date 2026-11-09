#!/usr/bin/env python3
"""Build the pinned Waybar + two local MIT patches; never install or launch it."""
import argparse
import hashlib
import json
import os
import platform
import sys
from pathlib import Path
import shutil
import subprocess
import tarfile

REVISION = '90b209add8937514d0a987aa842e701bd8f1232e'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='local upstream Git repository')
    parser.add_argument('--output', type=Path, required=True, help='new private build directory')
    parser.add_argument('--meson', default='meson')
    args = parser.parse_args()
    package = Path(__file__).resolve().parent
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = output/'source'; source.mkdir()
    archive = output/'upstream.tar'
    with archive.open('wb') as stream:
        subprocess.run(['git', '-C', str(args.source), 'archive', REVISION], stdout=stream, check=True)
    with tarfile.open(archive) as contents:
        contents.extractall(source, filter='data')
    patches = [package/'0001-hyprland-lua-workspace.patch', package/'0002-native-tray-popup-shelf.patch']
    for patch in patches:
        subprocess.run(['git', 'apply', str(patch)], cwd=source, check=True)
    if (source/'include/util/shelf_popup.hpp').read_bytes() != (package/'shelf_popup.hpp').read_bytes():
        raise ValueError('Packaged helper and patch diverged; regenerate the patch before building')
    build = output/'build'
    options = ['--buildtype=release', '--wrap-mode=nofallback', '-Ddbusmenu-gtk=enabled',
               '-Dsystemd=disabled', '-Dman-pages=disabled', '-Dmpd=disabled',
               '-Dtests=disabled', '-Djack=disabled', '-Dwireplumber=disabled',
               '-Dcava=disabled', '-Dgps=disabled']
    # Fixed source-export epoch, independent of local wall-clock/build time.
    env = os.environ.copy(); env['SOURCE_DATE_EPOCH'] = '1760054400'
    subprocess.run([args.meson, 'setup', str(build), str(source), *options], env=env, check=True)
    subprocess.run(['ninja', '-C', str(build), '-j', '2'], env=env, check=True)
    binary = output/'waybar'; shutil.copy2(build/'waybar', binary)
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    record = {'upstream': 'https://github.com/Alexays/Waybar', 'revision': REVISION,
              'version': '0.15.0', 'license': 'MIT', 'binary': str(binary),
              'sha256': digest(binary), 'patches': {p.name: digest(p) for p in patches},
              'meson_options': options, 'jobs': 2, 'source_date_epoch': env['SOURCE_DATE_EPOCH']}
    (output/'build-record.json').write_text(json.dumps(record, indent=2)+'\n')
    metadata = {'platform': sys.platform, 'architecture': platform.machine(),
                'source_revision': REVISION, 'sha256': record['sha256'],
                'features': ['hyprland-lua', 'shelf-popup-lifecycle'],
                'license': 'MIT', 'tested_waybar': '0.15.0'}
    (output/'backend.json').write_text(json.dumps(metadata, indent=2)+'\n')
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
