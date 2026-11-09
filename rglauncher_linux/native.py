"""Portable original native adapters for a verified RGLauncher release.

No third-party theme CSS/fonts are copied. GTK uses its installed built-in base;
the project's scoped CSS and Qt palette are generated in an isolated subprocess
from the release's own semantic roles. Only explicit XDG-owned files are edited.
"""
from __future__ import annotations

import configparser
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid

THEME = "RGLauncher-Aether"
BLOCK_BEGIN = "/* BEGIN RGLauncher native scoped adapters */"
BLOCK_END = "/* END RGLauncher native scoped adapters */"
KITTY_BEGIN = "# BEGIN RGLauncher native theme"
KITTY_END = "# END RGLauncher native theme"
HEX = re.compile(r"#[0-9a-fA-F]{6}\Z")
REQUIRED_COLORS = ("canvas", "surface", "raised", "text", "secondary", "boundary", "focus", "selection", "accent", "success", "warning", "danger")


class NativeError(RuntimeError):
    """Native preparation failed before activation; backups remain recoverable."""


def _tokens(release_root):
    path = release_root / "share/instrument-score-aether/tokens.json"
    if path.is_symlink() or not path.is_file():
        raise NativeError("Verified release is missing its native semantic roles")
    data = json.loads(path.read_text())
    colors = data.get("color", {})
    if not all(HEX.fullmatch(str(colors.get(name, ""))) for name in REQUIRED_COLORS):
        raise NativeError("Invalid native semantic color role")
    if not HEX.fullmatch(str(colors.get("control_boundary", colors["focus"]))):
        raise NativeError("Invalid native control boundary")
    for name in ("reading", "heading", "value"):
        value = data.get("font", {}).get(name)
        if not isinstance(value, str) or not value or len(value) > 100 or any(ch in value for ch in '\r\n\t"{}[]\\$;,='):
            raise NativeError("Invalid native font role")
    return data


def _isolated_render(release_root, tokens):
    directory = release_root / "bin"
    for name in ("_cyber_theme.py", "_cyber_gtk.py", "_aether_material.py", "_aether_desktop.py"):
        if not (directory / name).is_file():
            raise NativeError("Verified release is missing native adapter " + name)
    code = '''import json,sys
sys.path.insert(0,sys.argv[1])
import _cyber_theme as t,_cyber_gtk as g,_aether_desktop as d
print(json.dumps({"gtk3":g.build_css(),"gtk4":g.build_css4(),"qt":t.qt_palette(),"kitty":d.kitty_conf()}))
'''
    with tempfile.TemporaryDirectory(prefix="rglauncher-native-roles-") as temporary:
        config = Path(temporary)
        target = config / "instrument-score-aether/tokens.json"
        target.parent.mkdir()
        target.write_text(json.dumps(tokens))
        environment = dict(os.environ, XDG_CONFIG_HOME=str(config), PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(directory)],
            env=environment, capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise NativeError("Native adapter generation failed: " + result.stderr[-1200:])
    try:
        rendered = json.loads(result.stdout)
        if not all(isinstance(rendered.get(name), str) for name in ("gtk3", "gtk4", "qt", "kitty")):
            raise ValueError("Missing adapter output")
        return rendered
    except ValueError as error:
        raise NativeError("Native adapter returned invalid data") from error


def _gtk_probe(major, css=None):
    """Probe built-in resources and parse CSS without connecting to a display."""
    code = '''import json,sys
try:
 import gi
 gi.require_version("Gtk",sys.argv[1]+".0")
 from gi.repository import Gtk,Gio
except (ImportError,ValueError) as e:
 print(json.dumps({"available":False,"reason":str(e)}));sys.exit(0)
paths=(["/org/gtk/libgtk/theme/Adwaita/gtk-contained-dark.css","/org/gtk/libgtk/theme/Adwaita/gtk-dark.css"] if sys.argv[1]=="3" else ["/org/gtk/libgtk/theme/Default/Default-dark.css","/org/gtk/libgtk/theme/Default/gtk-dark.css","/org/gtk/libgtk/theme/Adwaita/gtk-contained-dark.css"])
base=None
for path in paths:
 try:Gio.resources_get_info(path,Gio.ResourceLookupFlags.NONE);base=path;break
 except Exception:pass
css=sys.stdin.read();errors=[]
if css:
 p=Gtk.CssProvider();p.connect("parsing-error",lambda _p,_s,e:errors.append(str(e)))
 try:
  if sys.argv[1]=="4":p.load_from_string(css)
  else:p.load_from_data(css.encode())
 except Exception as e:errors.append(str(e))
print(json.dumps({"available":True,"base":base,"errors":errors}))
'''
    result = subprocess.run([sys.executable, "-I", "-c", code, str(major)], input=css or "",
                            capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise NativeError("GTK native probe failed: " + result.stderr[-1000:])
    try:
        data = json.loads(result.stdout)
    except ValueError as error:
        raise NativeError("GTK probe returned invalid data") from error
    if data.get("errors"):
        raise NativeError("GTK" + str(major) + " CSS failed: " + "; ".join(data["errors"]))
    return data


def _gtk_css(tokens, major, base):
    c, font = tokens["color"], tokens["font"]
    bg, plane, raised, fg, muted = (c[k] for k in ("canvas", "surface", "raised", "text", "secondary"))
    cyan, focus, line = c["selection"], c["focus"], c["boundary"]
    control = c.get("control_boundary", focus)
    reading, mono = json.dumps(font["reading"], ensure_ascii=False), json.dumps(font["value"], ensure_ascii=False)
    # These are original role declarations. The base is an installed GTK resource.
    roles = {
        "theme_bg_color": bg, "theme_fg_color": fg, "theme_base_color": bg, "theme_text_color": fg,
        "theme_selected_bg_color": cyan, "theme_selected_fg_color": bg,
        "theme_unfocused_bg_color": bg, "theme_unfocused_fg_color": fg,
        "theme_unfocused_base_color": bg, "theme_unfocused_text_color": fg,
        "theme_unfocused_selected_bg_color": raised, "theme_unfocused_selected_fg_color": fg,
        "insensitive_bg_color": plane, "insensitive_fg_color": muted, "insensitive_base_color": plane,
        "borders": line, "unfocused_borders": line, "success_color": c["success"],
        "warning_color": c["warning"], "error_color": c["danger"], "link_color": cyan,
    }
    if major == 4:
        roles.update({"window_bg_color": bg, "window_fg_color": fg, "view_bg_color": bg, "view_fg_color": fg,
            "headerbar_bg_color": plane, "headerbar_fg_color": fg, "card_bg_color": plane, "card_fg_color": fg,
            "dialog_bg_color": bg, "dialog_fg_color": fg, "popover_bg_color": plane, "popover_fg_color": fg,
            "accent_color": cyan, "accent_bg_color": cyan, "accent_fg_color": bg,
            "destructive_color": c["danger"], "destructive_bg_color": c["danger"], "destructive_fg_color": bg})
    definitions = "\n".join(f"@define-color {name} {value};" for name, value in roles.items())
    checks = "checkbutton check, radiobutton radio" if major == 3 else "checkbutton check, checkbutton radio"
    checked = "checkbutton check:checked, radiobutton radio:checked" if major == 3 else "checkbutton check:checked, checkbutton radio:checked"
    return f'''/* RGLauncher original native defaults; installed GTK supplies its own base. */
@import url("resource://{base}");
{definitions}
window.background {{ background-color: {bg}; color: {fg}; font-family: {reading}; }}
window.background headerbar, window.background menubar, window.background toolbar,
window.background statusbar {{ background-color: {plane}; color: {fg}; }}
window.background .view, window.background textview text {{ background-color: {bg}; color: {fg}; }}
window.background textview.monospace text, window.background entry.monospace {{ font-family: {mono}; }}
window.background .sidebar, window.background placessidebar, window.background placessidebar viewport {{
    background-color: {plane}; color: {fg};
}}
window.background .sidebar row:selected, window.background placessidebar row:selected {{ background-color: {cyan}; color: {bg}; }}
window.background treeview header button {{ background-image: none; background-color: {plane}; color: {muted}; border-color: {line}; }}
window.background button, window.background entry, window.background spinbutton, window.background combobox button {{
    background-image: none; background-color: {plane}; color: {fg}; border: 1px solid {control}; border-radius: 6px;
}}
window.background button:hover {{ background-color: {raised}; border-color: {cyan}; }}
window.background button:checked {{ background-color: {raised}; color: {cyan}; border-color: {cyan}; }}
window.background button:focus, window.background entry:focus, window.background spinbutton:focus {{
    border-color: {focus}; outline: 2px solid {focus}; outline-offset: 1px;
}}
window.background button:disabled, window.background entry:disabled {{ color: {muted}; border-color: {line}; }}
window.background entry selection, window.background textview text selection,
window.background .view:selected {{ background-color: {cyan}; color: {bg}; }}
window.background scale trough {{ background-image: none; background-color: {raised}; border-color: {control}; }}
window.background scale highlight {{ background-image: none; background-color: {cyan}; border-color: {cyan}; }}
window.background scale slider {{ background-image: none; background-color: {plane}; border-color: {cyan}; }}
window.background scale value, window.background spinbutton entry {{ color: {fg}; font-family: {mono}; }}
{checks} {{ background-image: none; background-color: {plane}; border-color: {control}; color: {fg}; box-shadow: none; }}
{checked} {{ background-image: none; background-color: {cyan}; border-color: {cyan}; color: {bg}; box-shadow: none; }}
window.background switch {{ background-color: {raised}; color: {fg}; border-color: {control}; }}
window.background switch:checked {{ background-color: {cyan}; color: {bg}; }}
window.background switch slider {{ background-image: none; background-color: {plane}; border-color: {control}; }}
window.background scrollbar slider {{ background-image: none; background-color: {control}; }}
window.background menu, window.background popover {{ background-color: {plane}; color: {fg}; }}
window.background entry.error {{ color: {fg}; border-color: {c['danger']}; }}
window.background label.error {{ color: {c['danger']}; background-color: transparent; }}
window.background label.warning {{ color: {c['warning']}; }}
window.background label.success {{ color: {c['success']}; }}
'''


def _merge_ini(existing, sections):
    """Change owned keys only, retaining comments, other keys and other sections."""
    lines = existing.splitlines(keepends=True)
    current = None
    seen_sections, seen_keys, out = set(), {}, []

    def missing(section):
        return [f"{key}={value}\n" for key, value in sections.get(section, {}).items()
                if key not in seen_keys.get(section, set())]

    for line in lines:
        header = re.match(r"\s*\[([^\]]+)\]\s*(?:[#;].*)?$", line.rstrip("\r\n"))
        if header:
            out.extend(missing(current))
            current = header.group(1)
            seen_sections.add(current)
            seen_keys.setdefault(current, set())
            out.append(line if line.endswith(("\n", "\r")) else line + "\n")
            continue
        key = re.match(r"(\s*)([^#;=\s][^=]*?)\s*=", line)
        if current in sections and key and key.group(2).strip() in sections[current]:
            name = key.group(2).strip()
            out.append(key.group(1) + name + "=" + str(sections[current][name]) + "\n")
            seen_keys[current].add(name)
        else:
            out.append(line)
    if out and not out[-1].endswith(("\n", "\r")):
        out[-1] += "\n"
    out.extend(missing(current))
    for section, values in sections.items():
        if section not in seen_sections:
            out.append("\n[" + section + "]\n")
            out.extend(f"{key}={value}\n" for key, value in values.items())
    return "".join(out)


def _managed_css(existing, css):
    if existing.count(BLOCK_BEGIN) != existing.count(BLOCK_END) or existing.count(BLOCK_BEGIN) > 1:
        raise NativeError("Incomplete managed GTK CSS block; preserving existing file")
    if BLOCK_BEGIN in existing:
        start = existing.index(BLOCK_BEGIN)
        end = existing.index(BLOCK_END, start) + len(BLOCK_END)
        existing = existing[:start] + existing[end:]
    return existing.rstrip() + "\n\n" + BLOCK_BEGIN + "\n" + css.rstrip() + "\n" + BLOCK_END + "\n"


def _read(path):
    if path.is_symlink():
        raise NativeError("Refusing native configuration symlink: " + str(path))
    return path.read_text() if path.exists() else ""


def _kitty_include(existing):
    if existing.count(KITTY_BEGIN) != existing.count(KITTY_END) or existing.count(KITTY_BEGIN) > 1:
        raise NativeError("Incomplete managed Kitty theme block; preserving existing file")
    if KITTY_BEGIN in existing:
        start = existing.index(KITTY_BEGIN)
        end = existing.index(KITTY_END, start) + len(KITTY_END)
        existing = existing[:start] + existing[end:]
    # Deduplicate only this project's exact include; other themes/bindings remain.
    existing = "".join(line for line in existing.splitlines(keepends=True)
                       if line.strip() != "include rglauncher-aether.conf")
    return existing.rstrip() + "\n\n" + KITTY_BEGIN + "\ninclude rglauncher-aether.conf\n" + KITTY_END + "\n"


def _rgba(color):
    return ",".join(str(int(color[i:i + 2], 16)) for i in (1, 3, 5))


def _tcl_word(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("[", "\\[").replace("]", "\\]") + '"'


def _tcl(tokens):
    c, f = tokens["color"], tokens["font"]
    control = c.get("control_boundary", c["focus"])
    return f'''# RGLauncher original Tk/ttk native adapter.
package require Tk 8.6
foreach namedfont {{TkDefaultFont TkTextFont TkMenuFont TkCaptionFont TkSmallCaptionFont TkIconFont TkTooltipFont}} {{
    if {{[lsearch -exact [font names] $namedfont] >= 0}} {{ font configure $namedfont -family {_tcl_word(f['reading'])} -size 10 }}
}}
font configure TkHeadingFont -family {_tcl_word(f['heading'])} -size 10
font configure TkFixedFont -family {_tcl_word(f['value'])} -size 10
if {{[lsearch -exact [ttk::style theme names] rglauncher-aether] < 0}} {{ ttk::style theme create rglauncher-aether -parent clam }}
ttk::style theme settings rglauncher-aether {{
    ttk::style configure . -background {c['surface']} -foreground {c['text']} -fieldbackground {c['canvas']} -troughcolor {c['canvas']} -bordercolor {control} -lightcolor {c['boundary']} -darkcolor {c['canvas']} -selectbackground {c['selection']} -selectforeground {c['canvas']} -focuscolor {c['focus']} -font TkDefaultFont
    ttk::style map . -background [list active {c['raised']} disabled {c['surface']}] -foreground [list disabled {c['secondary']}]
    foreach widget {{TEntry TCombobox TSpinbox Treeview}} {{
        ttk::style configure $widget -fieldbackground {c['canvas']} -background {c['canvas']} -foreground {c['text']} -insertcolor {c['selection']}
        ttk::style map $widget -fieldbackground [list readonly {c['surface']} disabled {c['surface']}] -background [list selected {c['selection']}] -foreground [list selected {c['canvas']} disabled {c['secondary']}]
    }}
    ttk::style configure TSpinbox -font TkFixedFont
    ttk::style configure Treeview -font TkTextFont
    ttk::style configure Treeview.Heading -font TkHeadingFont
    ttk::style configure TNotebook.Tab -background {c['surface']}
    ttk::style map TNotebook.Tab -background [list selected {c['raised']}] -foreground [list selected {c['selection']}]
}}
package provide ttk::theme::rglauncher-aether 1.0
'''


def _gtk2(tokens):
    c, f = tokens["color"], tokens["font"]
    return f'''# Original RGLauncher GTK2 fallback; no external theme engine.
gtk-theme-name="{THEME}"
gtk-icon-theme-name="aether-score"
gtk-font-name="{f['reading']} 10"
style "rglauncher-aether-default" {{
  font_name="{f['reading']} 10"
  bg[NORMAL]="{c['surface']}"
  fg[NORMAL]="{c['text']}"
  base[NORMAL]="{c['canvas']}"
  text[NORMAL]="{c['text']}"
  bg[SELECTED]="{c['selection']}"
  fg[SELECTED]="{c['canvas']}"
  base[SELECTED]="{c['selection']}"
  text[SELECTED]="{c['canvas']}"
  fg[INSENSITIVE]="{c['secondary']}"
  text[INSENSITIVE]="{c['secondary']}"
}}
class "GtkWidget" style "rglauncher-aether-default"
'''


def _atomic(path, data, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _safe(path, roots):
    if not any(path.is_relative_to(root) for root in roots):
        raise NativeError("Native output escaped its explicit XDG roots")
    for candidate in (path, *path.parents):
        if candidate in roots:
            break
        if candidate.is_symlink():
            raise NativeError("Refusing native output symlink: " + str(candidate))


def _activate(preferences, xresources, checkpoint):
    """Capture and durably journal *all* old preferences before any mutation."""
    result = {"status": "prepared", "gsettings": {"status": "unavailable", "before": {}, "errors": []},
              "xresources": {"status": "unavailable", "before": {}}}

    def run(command):
        try:
            return subprocess.run(command, capture_output=True, text=True, timeout=4)
        except (OSError, subprocess.TimeoutExpired):
            return None

    tool = shutil.which("gsettings")
    if tool:
        state = result["gsettings"]
        for key, value in preferences.items():
            old = run([tool, "get", "org.gnome.desktop.interface", key])
            if old is None or old.returncode:
                state["errors"].append(key)
                continue
            state["before"][key] = old.stdout.strip()
        state["status"] = "prepared"
    xrdb = shutil.which("xrdb")
    if xrdb and os.environ.get("DISPLAY"):
        old = run([xrdb, "-query"])
        if old is not None and old.returncode == 0:
            owned = {line.split(":", 1)[0] for line in xresources.read_text().splitlines() if line and not line.startswith("!")}
            before = {key: None for key in owned}
            for line in old.stdout.splitlines():
                key, separator, value = line.partition(":")
                if separator and key in owned:
                    before[key] = value.strip()
            result["xresources"] = {"status": "prepared", "before": before}
    checkpoint(result)
    if tool:
        state = result["gsettings"]
        for key, before in state["before"].items():
            if before.strip("'") != preferences[key]:
                changed = run([tool, "set", "org.gnome.desktop.interface", key, preferences[key]])
                if changed is None or changed.returncode:
                    state["errors"].append(key)
        state["status"] = "partial" if state["errors"] else "applied"
        checkpoint(result)
    if result["xresources"]["status"] == "prepared":
        merged = run([xrdb, "-merge", str(xresources)])
        result["xresources"]["status"] = "applied" if merged is not None and merged.returncode == 0 else "failed"
        checkpoint(result)
    statuses = [result[name]["status"] for name in ("gsettings", "xresources")]
    result["status"] = "partial" if any(status in ("partial", "failed") for status in statuses) else "applied" if "applied" in statuses else "unavailable"
    checkpoint(result)
    return result


def apply_native(release_root: Path, config_home: Path, data_home: Path, activate=True, *, state_home: Path | None = None):
    """Prepare native files under explicit XDG roots; optionally activate UI prefs.

    activate=False performs no gsettings/xrdb/systemd/environment activation. Its
    backup default is derived from the supplied fixture data root, not real HOME.
    Returned backup metadata includes every replaced/new file for root rollback.
    """
    release_root, config_home, data_home = (Path(p).expanduser().resolve() for p in (release_root, config_home, data_home))
    if state_home is None:
        state_home = Path(os.environ.get("XDG_STATE_HOME", data_home.parent / "state")) if activate else data_home.parent / "state"
    state_home = Path(state_home).expanduser().resolve()
    tokens = _tokens(release_root)
    c, f = tokens["color"], tokens["font"]
    rendered = _isolated_render(release_root, tokens)
    probes = {major: _gtk_probe(major) for major in (3, 4)}
    for major, probe in probes.items():
        if probe.get("available") and not probe.get("base"):
            raise NativeError("GTK" + str(major) + " has no supported built-in theme resource")
    bases = {3: "/org/gtk/libgtk/theme/Adwaita/gtk-contained-dark.css", 4: "/org/gtk/libgtk/theme/Default/Default-dark.css"}
    bases.update({major: probe["base"] for major, probe in probes.items() if probe.get("base")})
    themes = {major: _gtk_css(tokens, major, bases[major]) for major in (3, 4)}
    for major in (3, 4):
        if probes[major]["available"]:
            _gtk_probe(major, themes[major])
            _gtk_probe(major, rendered["gtk" + str(major)])
    plan = {}
    originals = {}
    original_modes = {}

    def add(path, text):
        _safe(path, (config_home, data_home))
        old = _read(path)
        originals[path] = path.read_bytes() if path.exists() else None
        original_modes[path] = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
        plan[path] = text.encode()

    def ini(path, values):
        _safe(path, (config_home, data_home))
        add(path, _merge_ini(_read(path), values))

    theme_dir = data_home / "themes" / THEME
    kitty = config_home / "kitty/kitty.conf"
    _safe(kitty, (config_home, data_home))
    add(config_home / "kitty/rglauncher-aether.conf", rendered["kitty"])
    add(kitty, _kitty_include(_read(kitty)))
    add(theme_dir / "index.theme", f"[Desktop Entry]\nType=X-GNOME-Metatheme\nName={THEME}\nComment=Original Instrument/Score Aether native defaults\n\n[X-GNOME-Metatheme]\nGtkTheme={THEME}\nIconTheme=aether-score\n")
    for major in (3, 4):
        for name in ("gtk.css", "gtk-dark.css"):
            add(theme_dir / f"gtk-{major}.0" / name, themes[major])
        ini(config_home / f"gtk-{major}.0/settings.ini", {"Settings": {
            "gtk-theme-name": THEME, "gtk-icon-theme-name": "aether-score",
            "gtk-font-name": f["reading"] + " 10", "gtk-application-prefer-dark-theme": "true"}})
        add(config_home / f"gtk-{major}.0/gtk.css", _managed_css(_read(config_home / f"gtk-{major}.0/gtk.css"), rendered["gtk" + str(major)]))
    add(theme_dir / "gtk-2.0/gtkrc", _gtk2(tokens))
    native = config_home / "rglauncher-linux/native"
    control = c.get("control_boundary", c["focus"])
    for name, points in (("up", "0,5 4,0 8,5"), ("down", "0,0 4,5 8,0")):
        add(native / ("arrow-" + name + ".svg"), f'<svg xmlns="http://www.w3.org/2000/svg" width="8" height="5" viewBox="0 0 8 5"><polygon points="{points}" fill="{c["secondary"]}"/></svg>\n')
    qss = native / "controls.qss"
    add(qss, f'''/* Original RGLauncher native control affordances. */
QLineEdit, QAbstractSpinBox, QComboBox, QPushButton {{ border: 1px solid {control}; border-radius: 4px; }}
QLineEdit:focus, QAbstractSpinBox:focus, QComboBox:focus, QPushButton:focus {{ border-color: {c['focus']}; }}
QLineEdit:disabled, QAbstractSpinBox:disabled, QComboBox:disabled, QPushButton:disabled {{ border-color: {c['boundary']}; }}
QAbstractSpinBox::up-arrow {{ image: url("{native / 'arrow-up.svg'}"); width: 8px; height: 5px; }}
QAbstractSpinBox::down-arrow {{ image: url("{native / 'arrow-down.svg'}"); width: 8px; height: 5px; }}
''')
    for version in (5, 6):
        palette = config_home / f"qt{version}ct/colors/{THEME}.conf"
        add(palette, rendered["qt"])
        target = config_home / f"qt{version}ct/qt{version}ct.conf"
        parser = configparser.ConfigParser(interpolation=None, strict=False)
        parser.read_string(_read(target))
        existing = parser.get("Interface", "stylesheets", fallback="").strip()
        styles = [str(qss)] + ([existing] if existing and existing != "@Invalid()" and str(qss) not in existing else [])
        if str(qss) in existing:
            styles = [existing]
        ini(target, {"Appearance": {"style": "Fusion", "custom_palette": "true", "color_scheme_path": str(palette), "icon_theme": "aether-score", "standard_dialogs": "gtk3"},
            "Fonts": {"general": f'"{f["reading"]},10,-1,5,50,0,0,0,0,0"', "fixed": f'"{f["value"]},10,-1,5,50,0,0,0,0,0"'},
            "Interface": {"stylesheets": ", ".join(styles)}})
    kde = {"General": {"ColorScheme": THEME, "Name": "RGLauncher Aether", "font": f['reading'] + ",10,-1,5,50,0,0,0,0,0", "fixed": f['value'] + ",10,-1,5,50,0,0,0,0,0"},
           "Icons": {"Theme": "aether-score"}, "KDE": {"widgetStyle": "Fusion"}}
    for section, bg, fg in (("Window", c['canvas'], c['text']), ("View", c['canvas'], c['text']), ("Button", c['surface'], c['text']), ("Tooltip", c['surface'], c['text']), ("Selection", c['selection'], c['canvas']), ("Complementary", c['surface'], c['text']), ("Header", c['surface'], c['text'])):
        kde["Colors:" + section] = {name: _rgba(value) for name, value in {
            "BackgroundNormal": bg, "BackgroundAlternate": c['surface'], "ForegroundNormal": fg,
            "ForegroundInactive": fg if section == "Selection" else c['secondary'], "ForegroundActive": c['selection'],
            "ForegroundLink": c['selection'], "ForegroundVisited": c['accent'], "ForegroundNegative": c['danger'],
            "ForegroundNeutral": c['warning'], "ForegroundPositive": c['success'], "DecorationFocus": c['focus'], "DecorationHover": c['selection']}.items()}
    ini(config_home / "kdeglobals", kde)
    ini(data_home / f"color-schemes/{THEME}.colors", kde)
    ini(config_home / "qtquickcontrols2.conf", {"Controls": {"Style": "Material"}, "Material": {
        "Theme": "Dark", "Accent": c['selection'], "Primary": c['surface'], "Background": c['canvas'], "Foreground": c['text']}})
    tcl = data_home / "rglauncher-linux/tcl"
    add(tcl / "pkgIndex.tcl", "package ifneeded ttk::theme::rglauncher-aether 1.0 [list source [file join $dir rglauncher-aether.tcl]]\n")
    add(tcl / "rglauncher-aether.tcl", _tcl(tokens))
    xresources = native / "Xresources"
    xroles = {"background": c['canvas'], "foreground": c['text'], "activeBackground": c['raised'], "activeForeground": c['selection'],
        "selectBackground": c['selection'], "selectForeground": c['canvas'], "insertBackground": c['selection'],
        "troughColor": c['surface'], "highlightColor": c['focus'], "highlightBackground": control,
        "TkTheme": "rglauncher-aether", "scheme": "gtk+"}
    add(xresources, "! Original RGLauncher X11/Tk/FLTK fallback.\n" + "\n".join("*" + key + ": " + value for key, value in xroles.items()) + "\n")
    environment = {"QT_QPA_PLATFORMTHEME": "qt5ct", "QT_QUICK_CONTROLS_STYLE": "Material",
        "QT_QUICK_CONTROLS_MATERIAL_THEME": "Dark", "QT_QUICK_CONTROLS_CONF": str(config_home / "qtquickcontrols2.conf"),
        "TCLLIBPATH": _tcl_word(str(tcl)), "GTK2_RC_FILES": str(theme_dir / "gtk-2.0/gtkrc")}
    add(config_home / "environment.d/70-rglauncher-native.conf", "\n".join(name + "=" + json.dumps(value) for name, value in environment.items()) + "\n")
    add(native / "session.sh", "# Source explicitly from the RGLauncher session.\n" + "\n".join("export " + name + "=" + shlex.quote(value) for name, value in environment.items()) + "\n")
    changed = {path: content for path, content in plan.items() if originals[path] != content}
    # Check all expected originals before replacing any file.
    for path in changed:
        if (path.read_bytes() if path.exists() else None) != originals[path]:
            raise NativeError("Native configuration changed concurrently: " + str(path))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    backup = state_home / "rglauncher-linux/native-backups" / stamp
    backup.mkdir(mode=0o700, parents=True)
    backups = {}
    for number, path in enumerate(changed):
        previous = originals[path]
        if previous is None:
            backups[str(path)] = None
        else:
            destination = backup / "files" / str(number)
            _atomic(destination, previous, 0o600)
            backups[str(path)] = str(destination)
    receipt = {"theme": THEME, "changed": [str(p) for p in changed], "new_paths": [str(p) for p in changed if originals[p] is None],
        "backups": backups, "backup_dir": str(backup), "manifest": str(backup / "manifest.json"), "environment": environment,
        "original_modes": {str(path): original_modes[path] for path in changed},
        "validation": {str(k): v for k, v in probes.items()}, "activation": {"requested": bool(activate), "status": "not-requested"},
        "installed_sha256": {str(p): hashlib.sha256(data).hexdigest() for p, data in changed.items()}}
    _atomic(backup / "manifest.json", (json.dumps(receipt, indent=2) + "\n").encode(), 0o600)
    for path, data in changed.items():
        _safe(path, (config_home, data_home))
        if (path.read_bytes() if path.exists() else None) != originals[path]:
            raise NativeError("Native configuration changed during installation; use backup manifest: " + str(path))
        mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
        _atomic(path, data, mode)
    if activate:
        preferences = {"color-scheme": "prefer-dark", "gtk-theme": THEME, "icon-theme": "aether-score",
            "font-name": f['reading'] + " 10", "document-font-name": f['reading'] + " 10", "monospace-font-name": f['value'] + " 10"}
        def checkpoint(activation):
            receipt["activation"] = {"requested": True, **activation}
            _atomic(backup / "manifest.json", (json.dumps(receipt, indent=2) + "\n").encode(), 0o600)

        receipt["activation"] = {"requested": True, **_activate(preferences, xresources, checkpoint)}
    _atomic(backup / "manifest.json", (json.dumps(receipt, indent=2) + "\n").encode(), 0o600)
    return receipt
