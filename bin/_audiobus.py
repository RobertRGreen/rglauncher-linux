"""Console-owned buses + per-app output rules, shared by audio-menu and audio-bus-sync.

Config  ~/.config/audio-console/buses.json:
  buses {slug: label}        user buses -> null sinks `ac_bus_<slug>`
  sends [[bus, sink], ...]   loopbacks from a user bus to an output
  apps  {app name: [sinks]}  where an app should play; several = fan-out
Fan-out = the stream is parked on a private null sink `ac_app_<app>_<idx>` that is looped to every
chosen output (a PipeWire stream can only sit on one sink). Everything here is idempotent: reconcile()
can run any time (login, PipeWire restart, a device or app appearing) and only fixes what differs.
"""
import json
import os
import re
import subprocess
import time
import _audioeq
from pathlib import Path

CONF = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "audio-console" / "buses.json"
APP_PREFIX, BUS_PREFIX = "ac_app_", "ac_bus_"


def pactl(*a):
    try:
        return subprocess.run(_audioeq.translate(["pactl", *a]), capture_output=True, text=True, timeout=5)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def pj(*a):
    r = pactl("-f", "json", *a)
    try:
        return json.loads(r.stdout) if r and r.returncode == 0 else None
    except json.JSONDecodeError:
        return None


def slug(s, n=24):
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")[:n]


# -- config -------------------------------------------------------------------------------

def load():
    try:
        cfg = json.loads(CONF.read_text())
    except (OSError, json.JSONDecodeError):
        cfg = {}
    return {"buses": cfg.get("buses", {}), "sends": cfg.get("sends", []), "apps": cfg.get("apps", {})}


def save(cfg):
    CONF.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONF.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=1, sort_keys=True))
    tmp.replace(CONF)  # atomic: the daemon never reads half a file


# -- live state -----------------------------------------------------------------------------

def snapshot():
    sinks = pj("list", "sinks")
    if sinks is None:
        return None
    inputs = pj("list", "sink-inputs") or []
    by_idx = {s["index"]: _audioeq.logical(s["name"]) for s in sinks}
    loops, loopmods, nullmods = {}, [], {}
    r = pactl("list", "modules", "short")
    for m in (l.split("\t") for l in (r.stdout if r else "").splitlines()):
        if len(m) < 2:
            continue  # continuation lines of multi-line module args
        args = dict(p.split("=", 1) for p in (m[2] if len(m) > 2 else "").split() if "=" in p)
        if m[1] == "module-null-sink" and "sink_name" in args:
            nullmods[args["sink_name"]] = m[0]
        elif m[1] == "module-loopback" and "source" in args and "sink" in args:
            src, dst = args['source'].removesuffix('.monitor'), _audioeq.logical(args['sink'])
            loops[(src, dst)] = m[0]
            loopmods.append({'source': src, 'sink': dst, 'raw_sink': args['sink'], 'id': m[0]})
    apps = []
    for i in inputs:
        p = i.get("properties", {})
        apps.append({"idx": str(i["index"]), "sink": by_idx.get(i.get("sink"), ""),
                     "raw_sink": next((s['name'] for s in sinks if s['index'] == i.get('sink')), ''),
                     "name": p.get("application.name") or p.get("media.name") or p.get("node.name") or "",
                     "module": i.get("owner_module") not in (None, "n/a")})
    return {"sinks": set(by_idx.values()), "sink_idx": {n: i for i, n in by_idx.items()},
            "raw_sinks": {s['name'] for s in sinks},
            "loops": loops, "loopmods": loopmods, "nullmods": nullmods, "apps": apps}


# -- building blocks --------------------------------------------------------------------------

def make_null(name, desc):
    r = pactl("load-module", "module-null-sink", f"sink_name={name}", "rate=48000", "channels=2",
              "channel_map=front-left,front-right", f"sink_properties=device.description={desc}")
    return r.stdout.strip() if r and r.returncode == 0 else None


def loopback(bus, dst):
    # PipeWire 1.6.9's delayed loopback reads uninitialized delay-buffer data at
    # startup. A silent source can emit ~1e34 PCM values, then ring through EQ.
    # Request the same scheduling quantum without allocating that delay buffer.
    return pactl("load-module", "module-loopback", f"source={bus}.monitor", f"sink={dst}",
                 "latency_msec=0", "source_dont_move=true", "sink_dont_move=true",
                 "sink_input_properties=node.latency=320/48000",
                 "source_output_properties=node.latency=320/48000")


def prune_loops(snap):
    """Remove abandoned/duplicate console sends before they can capture a default monitor."""
    seen, removed = set(), 0
    for m in snap.get('loopmods', []):
        if not m['source'].startswith((APP_PREFIX, BUS_PREFIX)):
            continue
        pair = (m['source'], m['sink'])
        if (m['source'] not in snap['sinks'] or
                m['raw_sink'] not in snap['raw_sinks'] or pair in seen):
            pactl('unload-module', m['id'])
            removed += 1
        else:
            seen.add(pair)
    return removed


def drop_bus(snap, bus):
    """Unload a null-sink bus: loopbacks from AND into it first (else they re-target the default sink)."""
    if not bus:
        return
    modules = snap.get('loopmods', [dict(source=s, sink=d, id=mid)
                                    for (s, d), mid in snap['loops'].items()])
    for m in modules:
        if bus in (m['source'], m['sink']):
            pactl("unload-module", m['id'])
    if bus in snap["nullmods"]:
        pactl("unload-module", snap["nullmods"][bus])


def route(snap, app, targets):
    """Make sink-input `app` (a snapshot['apps'] entry) play on exactly `targets`. True if it changed."""
    cur = app["sink"]
    bus = cur if cur.startswith(APP_PREFIX) else None
    have = {d for (s, d) in snap["loops"] if s == bus} if bus else {cur}
    if not targets:
        return False
    if have == targets:
        if not bus and len(targets) == 1:
            target = next(iter(targets))
            actual = _audioeq.live_map().get(_audioeq.key('sink', target), target)
            if app.get('raw_sink', cur) != actual:
                r = pactl('move-sink-input', app['idx'], target)
                return bool(r and r.returncode == 0)
        return False
    if len(targets) == 1:
        pactl("move-sink-input", app["idx"], next(iter(targets)))
        drop_bus(snap, bus)
        return True
    if not bus:
        bus = f"{APP_PREFIX}{slug(app['name'])}_{app['idx']}"
        if bus in snap["nullmods"]:  # made moments ago; pulse hasn't shown the stream on it yet
            have = {d for (s, d) in snap["loops"] if s == bus}
        else:
            if not make_null(bus, "Console-" + slug(app["name"]).replace("_", "-")):
                return False
            snap["nullmods"][bus] = "?"
            have = set()  # brand-new bus: nothing wired yet, even though the stream was on `cur`
    for _ in range(20):  # a just-created sink isn't movable-to until pipewire-pulse has registered it
        r = pactl("move-sink-input", app["idx"], bus)
        if r and r.returncode == 0:
            break
        time.sleep(0.1)
    else:
        return False
    for d in targets - have:
        loopback(bus, d)
    for d in have - targets:
        pactl("unload-module", snap["loops"][(bus, d)])
    return True


# -- reconcile (idempotent) ---------------------------------------------------------------------

def reconcile():
    """Recreate saved buses/sends and re-apply saved app routes. Returns a short change log."""
    cfg, log = load(), []
    snap = snapshot()
    if snap is None:
        return ["pulse unreachable"]
    count = prune_loops(snap)
    if count:
        log.append(f'{count} abandoned/duplicate sends removed')
        snap = snapshot()
    for key, label in cfg["buses"].items():
        name = BUS_PREFIX + key
        if name not in snap["sinks"] and make_null(name, "Bus-" + slug(label).replace("_", "-")):
            log.append(f"bus {key} recreated")
    snap = snapshot()
    for bus, dst in cfg["sends"]:
        if bus in snap["sinks"] and dst in snap["sinks"] and (bus, dst) not in snap["loops"]:
            loopback(bus, dst)
            log.append(f"send {bus}->{dst}")
    snap = snapshot()
    for a in snap["apps"]:
        rule = cfg["apps"].get(a["name"])
        if a["module"] or not rule:
            continue
        targets = {t for t in rule if t in snap["sinks"] and not t.startswith(APP_PREFIX)}
        if targets and route(snap, a, targets):
            log.append(f"{a['name']} -> {len(targets)} output(s)")
            snap = snapshot()
    return log
