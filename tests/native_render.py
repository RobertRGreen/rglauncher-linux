#!/usr/bin/env python3
"""Opt-in native GTK3 offscreen integration audit of an isolated installation.

No top-level foreground window is ever mapped. File chooser data is synthetic.
Usage: native_render.py RELEASE CONFIG_HOME DATA_HOME OUTPUT_DIR
"""
import os
from pathlib import Path
import sys

release, config, data, output = (Path(p).resolve() for p in sys.argv[1:])
os.environ.update(XDG_CONFIG_HOME=str(config), XDG_DATA_HOME=str(data),
                  GTK_THEME="RGLauncher-Aether", GDK_BACKEND="x11")
sys.path.insert(0, str(release / "bin"))
import json
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Pango
import _cyber_theme as theme
import _cyber_gtk as scoped

output.mkdir(parents=True, exist_ok=True)
Gtk.Settings.get_default().set_property("gtk-enable-animations", False)
errors = []
screen = Gdk.Screen.get_default()
provider = Gtk.CssProvider()
provider.connect("parsing-error", lambda _p, _s, error: errors.append(str(error)))
provider.load_from_data(scoped.build_css().encode())
Gtk.StyleContext.add_provider_for_screen(screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)


def color(value):
    return "#" + "".join(f"{round(channel * 255):02x}" for channel in (value.red, value.green, value.blue))


def label(value):
    widget = Gtk.Label(label=value, xalign=0)
    return widget


def pump():
    for _ in range(24):
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)


def facts(window):
    context = window.get_style_context()
    bg = context.get_background_color(Gtk.StateFlags.NORMAL)
    return {"background": color(bg), "alpha": bg.alpha,
            "foreground": color(context.get_color(Gtk.StateFlags.NORMAL)),
            "font": context.get_font(Gtk.StateFlags.NORMAL).to_string()}


def capture(name, widget, width=760, app_css=None):
    application = None
    if app_css:
        application = Gtk.CssProvider()
        application.load_from_data(app_css.encode())
        Gtk.StyleContext.add_provider_for_screen(screen, application, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    window = Gtk.OffscreenWindow()
    window.set_default_size(width, -1)
    window.add(widget)
    window.show_all()
    pump()
    pixbuf = window.get_pixbuf()
    if pixbuf is None:
        raise AssertionError("Offscreen native render failed")
    pixbuf.savev(str(output / (name + ".png")), "png", [], [])
    result = facts(window)
    result["size"] = [pixbuf.get_width(), pixbuf.get_height()]
    window.hide()
    pump()
    window.destroy()
    if application:
        Gtk.StyleContext.remove_provider_for_screen(screen, application)
    return result


box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
for side in ("top", "bottom", "start", "end"):
    getattr(box, "set_margin_" + side)(28)
title = label("Native instruments / faithful controls")
title.get_style_context().add_class("title")
box.pack_start(title, False, False, 0)
box.pack_start(label("Original GTK defaults · reading text · exact values · clear states"), False, False, 0)
entry = Gtk.Entry(text="A long project title — Chamber movement 03")
box.pack_start(entry, False, False, 0)
focused = Gtk.Entry(text="Violet = keyboard focus; cyan = selection")
focused.set_state_flags(Gtk.StateFlags.FOCUSED, False)
box.pack_start(focused, False, False, 0)
row = Gtk.Box(spacing=12)
check = Gtk.CheckButton(label="Checked")
check.set_active(True)
row.pack_start(check, False, False, 0)
row.pack_start(Gtk.CheckButton(label="Unchecked"), False, False, 0)
switch = Gtk.Switch(active=True)
switch.set_valign(Gtk.Align.CENTER)
row.pack_start(switch, False, False, 0)
radio = Gtk.RadioButton.new_with_label_from_widget(None, "Radio")
row.pack_start(radio, False, False, 0)
box.pack_start(row, False, False, 0)
values = Gtk.Box(spacing=12)
spin = Gtk.SpinButton.new_with_range(0, 100, 0.25)
spin.set_value(62.5)
spin.get_style_context().add_class("monospace")
values.pack_start(spin, False, False, 0)
combo = Gtk.ComboBoxText()
for text in ("Current instrument", "Alternative instrument"):
    combo.append_text(text)
combo.set_active(0)
values.pack_start(combo, True, True, 0)
box.pack_start(values, False, False, 0)
scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
scale.set_value(62)
box.pack_start(scale, False, False, 0)
actions = Gtk.Box(spacing=12)
for title, sensitive in (("Continue", True), ("Unavailable", False)):
    button = Gtk.Button(label=title)
    button.set_sensitive(sensitive)
    actions.pack_start(button, True, True, 0)
box.pack_start(actions, False, False, 0)
results = {"native_controls": capture("native-controls", box)}

# Construct the real chooser widget; do not show any file chooser top-level.
synthetic = output / "synthetic-files"
synthetic.mkdir(exist_ok=True)
(synthetic / "Chamber movement.txt").write_text("Synthetic preview fixture.\n")
(synthetic / "Project archive").mkdir(exist_ok=True)
chooser = Gtk.FileChooserWidget(action=Gtk.FileChooserAction.OPEN)
chooser.set_local_only(True)
chooser.set_current_folder(str(synthetic))
chooser.set_size_request(820, 520)
results["file_chooser"] = capture("file-chooser", chooser, 820)

# Theme defaults must leave an application-priority transparent layer root free.
overlay = Gtk.OffscreenWindow()
overlay.get_style_context().add_class("aether-root")
overlay.set_app_paintable(True)
transparent = Gtk.CssProvider()
transparent.load_from_data(b"window.aether-root { background: transparent; }")
Gtk.StyleContext.add_provider_for_screen(screen, transparent, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
results["score_root"] = facts(overlay)
overlay.destroy()
Gtk.StyleContext.remove_provider_for_screen(screen, transparent)
results["css_errors"] = errors
results["theme"] = Gtk.Settings.get_default().get_property("gtk-theme-name")
results["no_foreground_windows"] = True
assert results["native_controls"]["background"] == theme.BG, results
assert results["native_controls"]["foreground"] == theme.FG, results
assert results["file_chooser"]["background"] == theme.BG, results
assert results["score_root"]["alpha"] == 0, results
assert not errors, results
(output / "results.json").write_text(json.dumps(results, indent=2) + "\n")
print(json.dumps(results, indent=2))
