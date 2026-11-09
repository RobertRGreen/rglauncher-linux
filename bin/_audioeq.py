"""Per-device native PipeWire EQ. Shared configuration and routing helpers.

The service owns filters; the console only writes settings. Closing the UI never
interrupts audio. Stable device names identify settings across reconnects.
"""
import hashlib
import cmath
import functools
import json
import math
import os
import subprocess
from pathlib import Path

ROOT = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'audio-console'
CONF = ROOT / 'equalizers.json'
RUNTIME = Path(os.environ.get('AUDIO_CONSOLE_EQ_RUNTIME',
                            str(Path(os.environ.get('XDG_RUNTIME_DIR', '/tmp')) / 'audio-console-eq')))
PREFIX = 'ac_eq_'

# Ten octave-spaced anchors, interpolated onto the user's current band count.
PRESET_ANCHORS = [31.5, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
PRESETS = {
    'Flat': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    'Bass boost': [5, 5, 3, 1, 0, 0, 0, 0, 0, 0],
    'Bass cut': [-6, -5, -3, -1, 0, 0, 0, 0, 0, 0],
    'Treble boost': [0, 0, 0, 0, 0, 0, 1, 2, 3, 3],
    'Vocal clarity': [-2, -2, -1, -2, -1, 1, 3, 2, 1, 0],
    'Warm': [2, 3, 2, 1, 0, 0, -1, -2, -2, -2],
    'Rock': [3, 2, 1, -1, -2, -1, 1, 2, 3, 2],
    'Pop': [1, 2, 1, 0, 1, 2, 2, 1, 2, 1],
    'Electronic': [4, 4, 2, 0, -2, -1, 0, 2, 3, 3],
    'Acoustic': [0, 1, 1, 0, 0, 1, 2, 2, 2, 1],
    'Gaming / footsteps': [-4, -3, -2, -1, 0, 1, 3, 4, 2, 0],
    'Gentle / less harsh': [0, 0, 0, 1, 1, 0, -2, -3, -2, -1],
}


def preset_gains(name, n):
    anchors = PRESETS[name]
    result = []
    for f in frequencies(n):
        for i in range(len(PRESET_ANCHORS) - 1):
            lo, hi = PRESET_ANCHORS[i:i + 2]
            if f <= hi or i == len(PRESET_ANCHORS) - 2:
                mix = max(0., min(1., math.log(f / lo) / math.log(hi / lo)))
                result.append(round(anchors[i] * (1 - mix) + anchors[i + 1] * mix, 2))
                break
    return result


def run(*args):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return None


def pj(*args):
    r = run('pactl', '-f', 'json', *args)
    try:
        return json.loads(r.stdout) if r and r.returncode == 0 else []
    except ValueError:
        return []


def load():
    try:
        return json.loads(CONF.read_text())
    except (OSError, ValueError):
        return {}


def key(kind, name):
    return kind + ':' + name


def virtual(kind, name):
    return PREFIX + hashlib.sha256(key(kind, name).encode()).hexdigest()[:16]


def settings(kind, name):
    return load().get(key(kind, name), dict(bands=10, gains=[0.] * 10,
                                          preamp=0., enabled=False, bypass=False))


def save(kind, name, value):
    cfg = load()
    cfg[key(kind, name)] = value
    ROOT.mkdir(parents=True, exist_ok=True)
    tmp = CONF.with_suffix('.tmp')
    tmp.write_text(json.dumps(cfg, indent=2))
    tmp.replace(CONF)


def frequencies(n):
    return [31.5 * (16000 / 31.5) ** (i / (n - 1)) for i in range(n)]


def q_value(n):
    ratio = (16000 / 31.5) ** (1 / (n - 1))
    return math.sqrt(ratio) / (ratio - 1)


@functools.lru_cache(maxsize=128)
def peak_boost(n, gains):
    """Peak of the combined response, including overlapping adjacent bands."""
    peak = 0.
    for rate in (44100, 48000):
        for i in range(768):
            freq = 20 * (20000 / 20) ** (i / 767)
            z = cmath.exp(-2j * math.pi * freq / rate)
            magnitude = 1.
            for center, gain in zip(frequencies(n), gains):
                a = 10 ** (gain / 40)
                w = 2 * math.pi * center / rate
                alpha = math.sin(w) / (2 * q_value(n))
                cs = math.cos(w)
                num = (1 + alpha * a) - 2 * cs * z + (1 - alpha * a) * z * z
                den = (1 + alpha / a) - 2 * cs * z + (1 - alpha / a) * z * z
                magnitude *= abs(num / den)
            peak = max(peak, 20 * math.log10(max(magnitude, 1e-12)))
    return peak


def effective_preamp(s):
    requested = float(s.get('preamp', 0.))
    if s.get('auto_headroom', True):
        boost = peak_boost(s['bands'], tuple(s['gains']))
        if boost > .01 or requested > 0:
            full = min(requested, -boost - 3.)
            amount = max(0., min(100., float(s.get('headroom_amount', 100.)))) / 100.
            return requested + amount * (full - requested)
    return requested


def controls(s):
    n = max(4, min(24, int(s['bands'])))
    freqs = frequencies(n)
    bypass = s.get('bypass', False)
    out = {'pre:Mult': 1. if bypass else 10 ** (effective_preamp(s) / 20)}
    for i in range(24):
        out.update({f'b{i}:Freq': freqs[i] if i < n else 1000.,
                    f'b{i}:Q': q_value(n),
                    f'b{i}:Gain': float(s['gains'][i]) if i < n and not bypass else 0.})
    return out


def graph_config(kind, name, desc, channels, s):
    """24 fixed slots: count/gain changes update Props without rebuilding audio."""
    v = virtual(kind, name)
    c = controls(s)
    nodes = [dict(type='builtin', name='pre', label='linear',
                  control={'Mult': c['pre:Mult'], 'Add': 0.})]
    for i in range(24):
        nodes.append(dict(type='builtin', name=f'b{i}', label='bq_peaking',
                          control={k: c[f'b{i}:{k}'] for k in ('Freq', 'Q', 'Gain')}))
    names = ['pre'] + [f'b{i}' for i in range(24)]
    links = [{'output': a + ':Out', 'input': b + ':In'} for a, b in zip(names, names[1:])]
    cap = {'node.name': v, 'node.description': desc + ' · EQ',
           'device.description': desc + ' · EQ', 'media.name': 'Audio Console EQ',
           'media.class': 'Audio/Sink', 'node.virtual': True,
           'node.latency': '1024/48000'}
    play = {'node.name': v + '_engine', 'target.object': name,
            'node.passive': True, 'node.dont-fallback': True, 'node.dont-reconnect': True}
    if kind == 'source':
        cap, play = (dict(play, **{'node.name': v + '_engine'}),
                     dict(cap, **{'media.class': 'Audio/Source'}))
        if name.endswith('.monitor'):
            cap['target.object'] = name.removesuffix('.monitor')
            cap['stream.capture.sink'] = True
    args = {'node.description': 'Audio Console EQ', 'media.name': 'Audio Console EQ',
            'audio.channels': channels,
            'filter.graph': {'nodes': nodes, 'links': links},
            'capture.props': cap, 'playback.props': play}
    return json.dumps({'context.spa-libs': {'audio.convert.*': 'audioconvert/libspa-audioconvert',
                                          'support.*': 'support/libspa-support'},
                       'context.modules': [{'name': 'libpipewire-module-rt',
                                            'flags': ['ifexists', 'nofail']},
                                           {'name': 'libpipewire-module-protocol-native'},
                                           {'name': 'libpipewire-module-client-node'},
                                           {'name': 'libpipewire-module-adapter'},
                                           {'name': 'libpipewire-module-filter-chain', 'args': args}]}, indent=2, ensure_ascii=False)


def live_map():
    try:
        return json.loads((RUNTIME / 'active.json').read_text())
    except (OSError, ValueError):
        return {}


def logical(name):
    return next((k.split(':', 1)[1] for k, v in live_map().items() if v == name), name)


def translate(args):
    """Apply console/bus routes through the EQ while keeping physical identities."""
    args = list(args)
    if not args or args[0] != 'pactl':
        return args
    mapping = live_map()
    for kind, move in (('sink', 'move-sink-input'), ('source', 'move-source-output')):
        if len(args) >= 4 and args[1] == move:
            args[3] = mapping.get(key(kind, args[3]), args[3])
    if len(args) > 2 and args[1:3] == ['load-module', 'module-loopback']:
        for i, a in enumerate(args):
            if a.startswith('sink='):
                args[i] = 'sink=' + mapping.get(key('sink', a[5:]), a[5:])
    return args
