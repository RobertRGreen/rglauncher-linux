"""Explicit native smoke test; not part of automatic unit discovery.

Creates static, noninteractive Waybar fixtures. Does not move the pointer, take
keyboard focus, launch utilities or issue hardware actions. Run inside Hyprland.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, required=True)
    args = parser.parse_args(); args.artifacts.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    config = args.artifacts/'config.json'
    config.write_text(json.dumps({'height': 60, 'modules-left': ['custom/test'],
                                 'modules-center': [], 'modules-right': [],
                                 'custom/test': {'format': 'RGLauncher shelf fixture', 'tooltip': False}}))
    env = os.environ.copy(); env['RGL_SHELF_INSTANCE'] = 'native-fixture'
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    def run(command):
        return subprocess.run(command, capture_output=True, text=True, check=True, env=env)
    def data(command): return json.loads(run(['hyprctl', command, '-j']).stdout)
    def control(*arguments): return json.loads(run([sys.executable, '-B', str(root/'bin/rglauncher-shelf'), *arguments]).stdout)
    def child_layers(layers, pids):
        return [(name, level, layer) for name, monitor in layers.items()
                for level, items in monitor['levels'].items() for layer in items if layer.get('pid') in pids]
    monitors = data('monitors'); active = data('activewindow').get('address')
    log = open(args.artifacts/'manager.log', 'w')
    process = subprocess.Popen([sys.executable, '-B', str(root/'bin/rglauncher-shelf'), 'run',
                                '--config', str(config), '--style', str(args.artifacts/'style.css')],
                               env=env, stdout=log, stderr=log)
    try:
        for _ in range(30):
            time.sleep(.1)
            try: status = control('status'); break
            except subprocess.CalledProcessError: pass
        else: raise AssertionError('Fixture manager did not start')
        time.sleep(1.2)
        pids = {entry['pid'] for entry in status['outputs'].values()}
        hidden = child_layers(data('layers'), pids)
        assert all(level != '3' for _, level, _ in hidden), 'Hidden bars must not occupy overlay layer'
        output = next(m['name'] for m in monitors if m.get('focused'))
        shown = control('show', '--output', output, '--hold', '2')
        time.sleep(.3)
        visible = child_layers(data('layers'), pids)
        overlays = [entry for entry in visible if entry[1] == '3']
        assert len(overlays) == 1 and overlays[0][0] == output, overlays
        monitor = next(m for m in monitors if m['name'] == output)
        assert overlays[0][2]['y'] >= monitor['y']+monitor['height']/monitor['scale']-100
        assert data('activewindow').get('address') == active, 'Shelf stole application focus'
        assert {m['name']: m['reserved'] for m in monitors} == {m['name']: m['reserved'] for m in data('monitors')}
        control('hide'); time.sleep(.2)
        assert all(level != '3' for _, level, _ in child_layers(data('layers'), pids))
        result = {'hidden_layer_entries': hidden, 'shown_overlay': overlays,
                  'focus_preserved': True, 'work_area_preserved': True,
                  'per_output_reveal': True, 'retracted': True}
        (args.artifacts/'result.json').write_text(json.dumps(result, indent=2)+'\n')
        print('PASS: per-output bottom overlay, hidden/reveal/retract, unchanged keyboard focus/work area')
    finally:
        try: control('stop')
        except Exception: process.terminate()
        process.wait(timeout=5)
        print('All fixture children stopped; original desktop bar was not replaced.')


if __name__ == '__main__': main()
