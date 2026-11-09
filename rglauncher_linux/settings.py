"""Instrument/Score Aether workbench and truthful release inspector."""
from __future__ import annotations
from datetime import datetime, timezone
import json
import os
import re
import subprocess
import sys
import threading
from urllib.parse import urlsplit

from . import __version__
from .paths import config_dir, release_root


def feed_label(url):
    """Readable feed identity, without fetching or resolving its host."""
    if not url:
        return "Not configured"
    try: parsed = urlsplit(str(url))
    except ValueError: return "Unrecognized feed address"
    return "Local file feed" if parsed.scheme == "file" else parsed.hostname or "Unrecognized feed address"


def result_feedback(action, result, error=None):
    """Describe returned facts; a check or no-op is never an installation."""
    if result.get("changed") is True:
        version = result.get("current_version") or result.get("version") or "requested release"
        refresh = result.get("desktop_refresh", {}).get("status")
        if error or refresh == "partial":
            return ("Release selected · attention needed", f"Software switched to {version}. Desktop refresh is incomplete; retry Refresh surfaces." + (" " + str(error) if error else ""), "warning")
        return ("Previous release restored" if action == "rollback" else "Release selected", f"New launches use {version}. Existing applications keep running.", "success")
    if error:
        return ("Could not complete " + {"status": "release inspection", "check": "the check", "apply": "installation", "rollback": "recovery", "refresh": "surface refresh"}.get(action, "the action"), str(error), "error")
    if action == "check":
        if result.get("update_available"):
            held = result.get("automatic_update_held")
            return ("Release available", str(result.get("available_version")) + (" · automatic retry is held; a manual install can retry." if held else " is available on this channel. Review before installing."), "warning" if held else "info")
        return ("No newer release", "The signed feed has no newer eligible release on this channel. Nothing was installed.", "info")
    if action in ("apply", "rollback"):
        return ("No release change", "Automatic retry is held after rollback." if result.get("reason") == "rollback_hold" else "The selected release did not change.", "info")
    if action == "refresh":
        if result.get("status") == "partial":
            return ("Refresh needs attention", "Some desktop surfaces could not be reconciled. Existing applications keep running.", "warning")
        return ("Surfaces refreshed", "The desktop reconciler completed. Existing applications keep running.", "success")
    return ("Release inspection ready", "Software selection and publisher details are shown below.", "info")


def main(*, window_class=None, run_loop=True):
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Pango
    root = release_root()
    sys.path.insert(0, str(root / "bin"))
    from _cyber_theme import (BG, BG_CARD, BG_HOT, FG, MUTED, LINE, CONTROL_LINE,
        PURPLE, ACCENT2, SUCCESS, WARNING, DANGER, FONT_BODY, FONT_MONO, FONT_HEAD, rgba)
    from _aether_material import surface_declarations
    preview = not run_loop
    window = (window_class or Gtk.Window)(title="RGLauncher · Control Room")
    window.set_default_size(900, 760)
    if preview and isinstance(window, Gtk.OffscreenWindow): window.set_size_request(900, 760)
    window.set_position(Gtk.WindowPosition.CENTER)
    window.get_style_context().add_class("rgl-settings")
    provider = Gtk.CssProvider()
    provider.load_from_data(f'''
window.rgl-settings {{background:{BG};color:{FG};font-family:"{FONT_BODY}";}}
.rgl-settings .shell {{padding:24px;}}
.rgl-settings label {{text-shadow:none;}}
.rgl-settings .eyebrow {{color:{ACCENT2};font-family:"{FONT_MONO}";font-size:.8em;letter-spacing:1px;}}
.rgl-settings .title {{color:{FG};font-family:"{FONT_HEAD}";font-size:2.1em;font-weight:600;}}
.rgl-settings .subtitle,.rgl-settings .purpose,.rgl-settings .field-name {{color:{MUTED};}}
.rgl-settings .subtitle,.rgl-settings .purpose {{font-size:.95em;}}
.rgl-settings .header {{padding:0 0 18px;border-bottom:1px solid {LINE};}}
.rgl-settings .edition {{border:1px solid {LINE};border-radius:7px;padding:5px 8px;color:{MUTED};font-size:.8em;}}
.rgl-settings .preview {{color:{WARNING};font-family:"{FONT_MONO}";font-size:.8em;}}
.rgl-settings .workbench {{{surface_declarations(18)} padding:20px;}}
.rgl-settings .inspector {{background:{rgba(BG_CARD,.55)};border:1px solid {LINE};border-radius:14px;padding:18px;}}
.rgl-settings .heading {{color:{FG};font-family:"{FONT_HEAD}";font-weight:600;font-size:1.3em;}}
.rgl-settings .section {{font-family:"{FONT_MONO}";color:{MUTED};font-size:.8em;letter-spacing:.6px;}}
.rgl-settings .app-title {{color:{FG};font-weight:600;font-size:1.1em;}}
.rgl-settings .primary .app-title {{font-size:1.35em;}}
.rgl-settings button {{background-image:none;background-color:{BG_CARD};color:{FG};border:1px solid {CONTROL_LINE};border-radius:9px;padding:9px 12px;box-shadow:none;text-shadow:none;}}
.rgl-settings button.launch {{border-color:{CONTROL_LINE};padding:10px;}}
.rgl-settings button.launch.primary {{border-color:{rgba(ACCENT2,.65)};background-image:linear-gradient(105deg,{rgba(ACCENT2,.09)},{rgba(PURPLE,.07)});padding:14px 10px;}}
.rgl-settings button:hover {{background-color:{BG_HOT};border-color:{ACCENT2};}}
.rgl-settings button:focus {{border-color:{PURPLE};outline:2px solid {PURPLE};outline-offset:1px;}}
.rgl-settings button:disabled,.rgl-settings button:disabled label {{color:{MUTED};border-color:{LINE};}}
.rgl-settings .shortcut {{font-family:"{FONT_MONO}";color:{MUTED};font-size:.78em;border:1px solid {LINE};border-radius:5px;padding:4px 6px;}}
.rgl-settings .value {{color:{FG};font-family:"{FONT_MONO}";font-size:.95em;}}
.rgl-settings .current {{color:{ACCENT2};font-family:"{FONT_MONO}";font-size:1.35em;}}
.rgl-settings .field-name {{font-size:.8em;}}
.rgl-settings .release-line {{border-bottom:1px solid {LINE};padding-bottom:10px;}}
.rgl-settings .feedback {{background:{BG};border-left:3px solid {ACCENT2};border-radius:6px;padding:10px;}}
.rgl-settings .feedback.error {{border-left-color:{DANGER};}}
.rgl-settings .feedback.warning {{border-left-color:{WARNING};}}
.rgl-settings .feedback.success {{border-left-color:{SUCCESS};}}
.rgl-settings .feedback-title {{color:{FG};font-weight:600;}}
.rgl-settings .feedback-body {{color:{MUTED};font-size:.88em;}}
.rgl-settings .trust {{border-top:1px solid {LINE};padding-top:10px;}}
.rgl-settings .trust-body {{padding-top:10px;}}
.rgl-settings .gesture-row {{border-top:1px solid {LINE};padding-top:12px;}}
.rgl-settings .gesture-key {{color:{ACCENT2};font-family:"{FONT_MONO}";font-size:.82em;}}
.rgl-settings checkbutton {{color:{FG};font-size:.9em;}}
.rgl-settings .footer {{color:{MUTED};font-size:.85em;}}
'''.encode())
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    scroller = Gtk.ScrolledWindow()
    scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    shell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
    shell.get_style_context().add_class("shell")
    scroller.add(shell)
    window.add(scroller)
    state = {"closed": False, "busy": False, "result": {}}

    def label(text, css=None, selectable=False):
        widget = Gtk.Label(label=str(text), xalign=0)
        widget.set_line_wrap(True)
        widget.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        widget.set_max_width_chars(45)
        widget.set_selectable(selectable)
        if css:
            for name in css.split(): widget.get_style_context().add_class(name)
        return widget

    def box(css=None, spacing=8):
        widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)
        if css: widget.get_style_context().add_class(css)
        return widget

    def hero(name, size):
        path = root / "assets/shelf-icons" / (name + ".svg")
        if path.is_file():
            image = Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), size, size, True))
        else:
            image = Gtk.Image.new_from_icon_name(name, Gtk.IconSize.DIALOG)
            image.set_pixel_size(size)
        image.set_valign(Gtk.Align.CENTER)
        image.get_accessible().set_name("")
        return image

    header = box("header", 6)
    top = Gtk.Box(spacing=12)
    top.pack_start(label("RGLauncher / LINUX EDITION", "eyebrow"), True, True, 0)
    top.pack_end(label("DESKTOP SHELL", "edition"), False, False, 0)
    header.pack_start(top, False, False, 0)
    title_row = Gtk.Box(spacing=12)
    title_row.pack_start(hero("aether-home", 40), False, False, 0)
    title_row.pack_start(label("Control Room", "title"), True, True, 0)
    header.pack_start(title_row, False, False, 0)
    header.pack_start(label("Open your tools, then inspect the software that holds them together.", "subtitle"), False, False, 0)
    if preview: header.pack_start(label("PREVIEW / SYNTHETIC RELEASE DATA · actions isolated", "preview"), False, False, 0)
    shell.pack_start(header, False, False, 0)
    content = Gtk.Box(spacing=20)
    shell.pack_start(content, False, False, 0)
    work, inspector = box("workbench", 9), box("inspector", 11)
    work.set_valign(Gtk.Align.START)
    inspector.set_valign(Gtk.Align.START)
    work.set_hexpand(True)
    inspector.set_hexpand(False)
    content.pack_start(work, True, True, 0)
    content.pack_start(inspector, False, True, 0)
    work.pack_start(label("01 / WORKBENCH", "eyebrow"), False, False, 0)
    work.pack_start(label("Start with an instrument", "heading"), False, False, 0)
    launches = {}
    feedback = box("feedback", 4)
    feedback_title, feedback_body = label("Reading release state…", "feedback-title"), label("", "feedback-body")
    feedback.pack_start(feedback_title, False, False, 0)
    feedback.pack_start(feedback_body, False, False, 0)

    def notify(title, body, kind="info"):
        if state["closed"]: return False
        context = feedback.get_style_context()
        for name in ("info", "error", "warning", "success"): context.remove_class(name)
        context.add_class(kind)
        feedback_title.set_text(title)
        feedback_body.set_text(body)
        feedback.get_accessible().set_name(title + ". " + body)
        return False

    def launch(command):
        if preview:
            notify("Preview action", "Would open " + command + "; no process was started.")
            return
        try:
            subprocess.Popen([sys.executable, "-B", str(root / "bin/rglauncher"), command], start_new_session=True)
            notify("Opening instrument", "Launch requested for " + command + ".")
        except OSError as error:
            notify("Could not launch", str(error), "error")

    actions = [
        ("Applications", "Find any installed application", "apps", "aether-library", "Super Space"),
        ("Files", "Browse projects and documents", "files", "aether-folder", "Super D"),
        ("Terminal", "Work directly with your system", "terminal", "aether-development", "Super Q"),
        ("Windows", "Return to an open instrument", "windows", "aether-window", "Super Tab"),
        ("Calculator", "Evaluate an expression and copy its result", "calc", "aether-calculator", "Enter"),
        ("Audio console", "Shape levels, routing and sound", "audio", "aether-audio-console", "Enter"),
    ]
    for index, (title, purpose, command, icon, shortcut) in enumerate(actions):
        if index == 4: work.pack_start(label("PRECISION / SOUND", "section"), False, False, 5)
        button = Gtk.Button()
        button.get_style_context().add_class("launch")
        if index == 0: button.get_style_context().add_class("primary")
        row = Gtk.Box(spacing=10)
        row.pack_start(hero(icon, 40 if index == 0 else 32), False, False, 0)
        text = box(spacing=3)
        text.pack_start(label(title, "app-title"), False, False, 0)
        description = label(purpose, "purpose")
        description.set_max_width_chars(32)
        text.pack_start(description, False, False, 0)
        row.pack_start(text, True, True, 0)
        key = label(shortcut, "shortcut")
        key.set_valign(Gtk.Align.CENTER)
        if shortcut == "Enter": key.set_tooltip_text("Activate while this button has keyboard focus")
        row.pack_end(key, False, False, 0)
        button.add(row)
        button.get_accessible().set_name(title + ". " + purpose + ". " + ("Enter while focused" if shortcut == "Enter" else shortcut))
        button.connect("clicked", lambda _b, c=command: launch(c))
        work.pack_start(button, False, False, 0)
        launches[command] = button
    gestures = box("gesture-row", 4)
    gestures.pack_start(label("Super + arrows / tiled halves", "gesture-key"), False, False, 0)
    gestures.pack_start(label("Add Shift for thirds. Alt + Tab switches windows and leaves game capture behind.", "purpose"), False, False, 0)
    work.pack_start(gestures, False, False, 3)
    inspector.pack_start(label("02 / SOFTWARE & RECOVERY", "section"), False, False, 0)
    inspector.pack_start(label("Release inspector", "heading"), False, False, 0)
    fields = {}

    def field(name, title, parent=inspector, css="value"):
        row = box("release-line", 3)
        row.pack_start(label(title, "field-name"), False, False, 0)
        value = label("Reading…", css, True)
        value.set_max_width_chars(27)
        row.pack_start(value, False, False, 0)
        parent.pack_start(row, False, False, 0)
        fields[name] = value
    field("current_version", "SELECTED RELEASE", css="current")
    field("previous_version", "Recovery release")
    field("channel", "Channel")
    field("feed_host", "Feed")
    inspector.pack_start(feedback, False, False, 1)
    update_buttons = {}
    trust = Gtk.Expander(label="Publisher & trust details")
    trust.get_style_context().add_class("trust")
    trust_body = box("trust-body", 9)
    trust.add(trust_body)
    field("feed_url", "Configured feed address", trust_body)
    field("trusted_key_sha256", "Pinned publisher / SHA-256", trust_body)
    field("last_checked_at", "Last check (UTC)", trust_body)
    field("held_version", "Automatic retry hold", trust_body)
    field("highest_version", "Highest installed version", trust_body)
    trust_body.pack_start(label("Release signatures are checked against this configured publisher key before software is installed.", "purpose"), False, False, 0)
    settings_path = config_dir() / "updates.json"
    if preview:
        settings = {"feed_url": "https://updates.example.org/rglauncher/feed.json", "automatic": False}
    else:
        try: settings = json.loads(settings_path.read_text())
        except (OSError, ValueError): settings = {}
    automatic = Gtk.CheckButton(label="Install signed updates automatically")
    automatic.get_child().set_line_wrap(True)
    automatic.get_child().set_max_width_chars(26)
    automatic.set_active(bool(settings.get("automatic", False)))
    automatic.set_sensitive(bool(settings.get("feed_url")))

    def set_busy(busy):
        state["busy"] = busy
        for button in update_buttons.values(): button.set_sensitive(not busy)
        automatic.set_sensitive(not busy and bool(settings.get("feed_url")))

    def update_fields(result):
        state["result"].update(result)
        data = state["result"]
        fields["current_version"].set_text(str(data.get("current_version") or "No managed release"))
        fields["previous_version"].set_text(str(data.get("previous_version") or "None retained"))
        fields["channel"].set_text(str(data.get("channel") or "Not configured"))
        fields["feed_host"].set_text(feed_label(data.get("feed_url")))
        fields["feed_url"].set_text(str(data.get("feed_url") or "Not configured"))
        fingerprint = str(data.get("trusted_key_sha256") or "Not available")
        if re.fullmatch(r"[a-fA-F0-9]{64}", fingerprint): fingerprint = "\n".join(fingerprint[i:i+16] for i in range(0,64,16))
        fields["trusted_key_sha256"].set_text(fingerprint)
        checked = data.get("last_checked_at")
        try: date = datetime.fromtimestamp(checked, timezone.utc).strftime("%Y-%m-%d %H:%M") if checked is not None else "No check recorded"
        except (TypeError, ValueError, OSError): date = "Unknown timestamp"
        fields["last_checked_at"].set_text(date)
        fields["held_version"].set_text(str(data.get("held_version") or "None"))
        fields["highest_version"].set_text(str(data.get("highest_version") or "Not recorded"))

    def show_result(action, result, error=None):
        if state["closed"]: return False
        set_busy(False)
        if not isinstance(result, dict): result, error = {}, "The command returned invalid release data."
        if result and action != "refresh": update_fields(result)
        if error and action == "status" and not state["result"]:
            for name, value in fields.items(): value.set_text("Status unavailable" if name == "current_version" else "Unknown")
        notify(*result_feedback(action, result, error))
        if action == "status" and result.get("last_error"): notify("Previous update needs attention", str(result["last_error"]), "warning")
        return False

    def run(action):
        if state["busy"]: return
        if preview:
            notify("Preview action", "Would request " + action + "; no update, service or file was changed.")
            return
        set_busy(True)
        notify("Working…", {"status": "Reading the selected release and pinned publisher…", "check": "Checking signed metadata. Nothing is installed by a check.", "apply": "Verifying the release before installation…", "rollback": "Verifying the retained recovery release…", "refresh": "Reconciling desktop surfaces…"}[action])
        def worker():
            result, error = {}, None
            arguments = ["desktop", "refresh"] if action == "refresh" else ["update", action]
            try:
                completed = subprocess.run([sys.executable, "-B", str(root / "bin/rglauncher"), *arguments], capture_output=True, text=True)
                try:
                    result = json.loads(completed.stdout)
                    if not isinstance(result, dict): raise ValueError("Expected object")
                except ValueError: error = (completed.stderr or completed.stdout).strip()[-600:] or "The command returned no release data."
                if completed.returncode: error = error or completed.stderr.strip()[-600:] or "The command reported an incomplete operation."
            except (OSError, ValueError) as exception: error = str(exception)
            GLib.idle_add(show_result, action, result, error)
        threading.Thread(target=worker, daemon=True).start()

    for title, action in (("Check for updates", "check"), ("Install verified update", "apply"), ("Restore previous release", "rollback")):
        button = Gtk.Button(label=title)
        button.connect("clicked", lambda _b, a=action: run(a))
        update_buttons[action] = button
        inspector.pack_start(button, False, False, 0)

    def toggle(widget):
        if preview:
            notify("Preview preference", "Automatic-update preference was not saved.")
            return
        try:
            desired = widget.get_active()
            if desired:
                result = subprocess.run(["systemctl", "--user", "enable", "--now", "rglauncher-update.timer"], capture_output=True, text=True, timeout=15)
                if result.returncode: raise RuntimeError("Update timer could not start: " + result.stderr.strip()[-250:])
            data = json.loads(settings_path.read_text())
            data["automatic"] = desired
            temporary = settings_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(data, indent=2) + "\n")
            temporary.chmod(0o600)
            os.replace(temporary, settings_path)
            notify("Automatic updates " + ("enabled" if desired else "disabled"), "Signed automatic installs are enabled." if desired else "Manual checks remain available.")
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
            notify("Could not save preference", str(error), "error")
            widget.handler_block(toggle_handler)
            widget.set_active(not widget.get_active())
            widget.handler_unblock(toggle_handler)
    toggle_handler = automatic.connect("toggled", toggle)
    inspector.pack_start(automatic, False, False, 2)
    inspector.pack_start(trust, False, False, 0)
    footer = Gtk.Box(spacing=12)
    footer.pack_start(label("Shelf at the bottom edge · Escape closes this room\nRunning software " + __version__, "footer"), True, True, 0)
    refresh = Gtk.Button(label="Refresh surfaces")
    refresh.connect("clicked", lambda _b: run("refresh"))
    update_buttons["refresh"] = refresh
    footer.pack_end(refresh, False, False, 0)
    shell.pack_start(footer, False, False, 0)

    def apply_layout(compact):
        if state["closed"]: return False
        content.set_orientation(Gtk.Orientation.VERTICAL if compact else Gtk.Orientation.HORIZONTAL)
        inspector.set_size_request(-1 if compact else 285, -1)
        for widget in (work, inspector): widget.set_hexpand(compact or widget is work)
        content.queue_resize()
        return False

    def reflow(_window, allocation):
        line_height = window.create_pango_layout("M").get_pixel_size()[1]
        compact = allocation.width < max(780, line_height * 43)
        if state.get("compact") != compact:
            state["compact"] = compact
            # Do not mutate orientation from inside GTK's allocation callback.
            GLib.idle_add(apply_layout, compact)
    window.connect("size-allocate", reflow)
    window.connect("key-press-event", lambda _w, event: (window.close() or True) if event.keyval == Gdk.KEY_Escape else False)
    def destroy(*_):
        state["closed"] = True
        Gtk.StyleContext.remove_provider_for_screen(Gdk.Screen.get_default(), provider)
        if Gtk.main_level(): Gtk.main_quit()
    window.connect("destroy", destroy)
    window.rgl_ui = {"preview": preview, "workbench": work, "inspector": inspector, "content": content,
        "fields": fields, "trust": trust, "launches": launches, "updates": update_buttons,
        "automatic": automatic, "show_result": show_result, "feedback_title": feedback_title,
        "feedback_body": feedback_body, "state": state}
    window.show_all()
    if preview:
        update_fields({"current_version": "0.2.0-alpha.2", "previous_version": "0.2.0-alpha.1", "channel": "prerelease",
            "feed_url": settings["feed_url"], "trusted_key_sha256": "2d6b8af731c045b27a91e063df5278a4c00f93e1ba665ad47e31c09582be6470",
            "last_checked_at": 1794200400, "highest_version": "0.2.0-alpha.2", "held_version": None})
        notify("Preview / isolated instruments", "Example release data only. Launch, update and preference actions are disabled in this fixture.")
        return window
    run("status")
    Gtk.main()
    return 0
