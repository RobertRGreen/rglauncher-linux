#!/usr/bin/env python3
"""Build Freedesktop icon themes from the original Aether SVG registry."""
import argparse
import configparser
import json
from pathlib import Path
import shutil

CONTEXT = {'actions': 'Actions', 'apps': 'Applications', 'categories': 'Categories',
           'devices': 'Devices', 'emblems': 'Emblems', 'mimetypes': 'MimeTypes',
           'places': 'Places', 'status': 'Status'}


def build(registry_path, destination, variant='color-dark'):
    registry_path, destination = Path(registry_path), Path(destination)
    registry = json.loads(registry_path.read_text())
    root = registry_path.parent
    destination.mkdir(parents=True, exist_ok=True)
    directories = {}
    count = 0
    for icon in registry['icons']:
        context, name = icon['context'], icon['id']
        aliases = [name, *icon.get('aliases', [])]
        for size in (16, 24, 32, 48, None):
            relative = icon.get('sized_files', {}).get(variant, {}).get(str(size), icon['files'][variant])
            source = (root/relative).resolve()
            if not source.is_relative_to(root.resolve()):
                raise ValueError('Icon registry path escaped source tree')
            folder = ('scalable' if size is None else f'{size}x{size}')+'/'+context
            (destination/folder).mkdir(parents=True, exist_ok=True)
            directories[folder] = {'Size': str(size or 48), 'Context': CONTEXT.get(context, context.title()),
                                   'Type': 'Scalable' if size is None else 'Fixed'}
            if size is None:
                directories[folder].update({'MinSize': '8', 'MaxSize': '512'})
            for alias in aliases:
                if '/' in alias or '..' in alias:
                    raise ValueError('Unsafe icon name')
                shutil.copyfile(source, destination/folder/(alias+'.svg')); count += 1
        folder = 'symbolic/'+context
        (destination/folder).mkdir(parents=True, exist_ok=True)
        directories[folder] = {'Size': '24', 'Context': CONTEXT.get(context, context.title()),
                               'Type': 'Scalable', 'MinSize': '8', 'MaxSize': '512'}
        source = root/icon['files']['symbolic']
        for alias in aliases:
            alias = alias if alias.endswith('-symbolic') else alias+'-symbolic'
            shutil.copyfile(source, destination/folder/(alias+'.svg')); count += 1
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str
    config['Icon Theme'] = {'Name': 'RGLauncher Aether' if variant=='color-dark' else 'RGLauncher Aether Light',
                            'Comment': 'Original Instrument/Score Aether icons — MIT licensed',
                            'Inherits': 'hicolor,Adwaita', 'Directories': ','.join(directories)}
    for folder, settings in directories.items():
        config[folder] = settings
    with open(destination/'index.theme', 'w') as stream:
        config.write(stream, space_around_delimiters=False)
    (destination/'PROVENANCE.txt').write_text('Original RGLauncher / Instrument-Score Aether SVG paths.\nMIT License; see distribution LICENSE and icon source provenance.\nApplication brand logos are not replaced by this family.\n')
    return count


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('registry', type=Path); parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    for name, variant in [('aether-score', 'color-dark'), ('aether-score-light', 'color-light')]:
        print(name, build(args.registry, args.destination/name, variant), 'renderable icon entries')
