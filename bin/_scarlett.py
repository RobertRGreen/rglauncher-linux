"""Focusrite Scarlett (scarlett2 ALSA driver) state + presets.

Shared by audio-menu (the console UI) and scarlett-preset (CLI / reconnect watcher).
A preset is {control name: value} for every writable MIXER/CARD control, stored as
~/.config/audio-console/presets/<name>.json; `last` names the one to reapply.
"""
import json
import os
import re
import subprocess
from pathlib import Path

DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "audio-console"
PRESETS = DIR / "presets"
LAST = DIR / "last"
NAME_RE = re.compile(r"^[A-Za-z0-9 _-]{1,40}$")


def _run(args, timeout=3):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def hw_card():
    try:
        for line in Path("/proc/asound/cards").read_text().splitlines():
            if line.strip()[:1].isdigit() and ("Scarlett" in line or "Focusrite" in line):
                return line.split()[0]
    except OSError:
        pass
    return None


def hw_controls(card):
    r = _run(["amixer", "-c", card, "contents"])
    ctls, cur = [], None
    for ln in (r.stdout if r else "").splitlines():
        s = ln.strip()
        if ln.startswith("numid="):
            m = re.match(r"numid=(\d+),iface=(\w+),name='(.*)'", ln)
            cur = {"id": m[1], "iface": m[2], "name": m[3], "items": [], "type": "",
                   "rw": False, "min": 0, "max": 0, "val": ""}
            ctls.append(cur)
        elif cur is None:
            continue
        elif s.startswith("; type="):
            kv = dict(p.split("=", 1) for p in s[2:].split(",") if "=" in p)
            cur.update(type=kv["type"], rw=kv["access"][:2] == "rw",
                       min=int(kv.get("min", 0)), max=int(kv.get("max", 0)))
        elif s.startswith("| dBminmax"):
            mm = re.search(r"min=(-?[\d.]+)dB,max=(-?[\d.]+)dB", s)
            cur["db"] = (float(mm[1]), float(mm[2]))
        elif s.startswith("; Item"):
            cur["items"].append(re.search(r"'(.*)'", s)[1])
        elif s.startswith(": values="):
            cur["val"] = s.split("=", 1)[1].split(",")[0]
    return ctls


def _saveable(c):
    # autogain switches are excluded: switching one ON starts a run that overwrites the saved gain
    return (c["rw"] and c["iface"] in ("MIXER", "CARD") and "Autogain Capture Switch" not in c["name"]
            and c["type"] in ("ENUMERATED", "BOOLEAN", "INTEGER"))


def snapshot(card):
    return {c["name"]: c["val"] for c in hw_controls(card) if _saveable(c)}


def apply(card, values):
    """Write a {name: value} dict to the device; returns how many controls were set."""
    by_name = {c["name"]: c for c in hw_controls(card) if _saveable(c)}
    links = [n for n in values if n.endswith("Link Capture Switch") and n in by_name]
    # links off first (a linked pair would drag the other gain), restored last
    order = [(n, "off") for n in links] + [(n, v) for n, v in values.items() if n in by_name and n not in links]
    order += [(n, values[n]) for n in links]
    done = 0
    for name, val in order:
        r = _run(["amixer", "-q", "-c", card, "cset", f"numid={by_name[name]['id']}", str(val)])
        done += bool(r and r.returncode == 0)
    return done


# -- preset store ----------------------------------------------------------------------

def names():
    return sorted(p.stem for p in PRESETS.glob("*.json"))


def last():
    try:
        n = LAST.read_text().strip()
    except OSError:
        return None
    return n if (PRESETS / f"{n}.json").exists() else None


def set_last(name):
    DIR.mkdir(parents=True, exist_ok=True)
    LAST.write_text(name)


def save(name, card):
    if not NAME_RE.match(name):
        raise ValueError("preset name: letters, digits, space, _ or -, max 40")
    PRESETS.mkdir(parents=True, exist_ok=True)
    (PRESETS / f"{name}.json").write_text(json.dumps(snapshot(card), indent=1, sort_keys=True))
    set_last(name)


def load(name, card):
    values = json.loads((PRESETS / f"{name}.json").read_text())
    n = apply(card, values)
    set_last(name)
    return n


def delete(name):
    (PRESETS / f"{name}.json").unlink(missing_ok=True)
    if LAST.exists() and LAST.read_text().strip() == name:
        LAST.unlink()
