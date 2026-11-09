#!/usr/bin/env python3
"""Instrument/Score Aether launcher/overview. Stable native GTK3 score lanes.

Compatible with the existing run(prompt, tabs, on_activate, hint) wrappers.
Only the wrapper activates apps/windows, after this overlay releases focus.
No ambient timer, frame callback, command replay, thumbnails or fake telemetry.
"""
import json
import os
import subprocess
import unicodedata
import re
from pathlib import Path

# Include Flatpak exports before GLib initializes its desktop/icon search paths.
_data_home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
os.environ["XDG_DATA_DIRS"] = ":".join(dict.fromkeys([
    str(_data_home / "flatpak/exports/share"), "/var/lib/flatpak/exports/share",
    *(os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":"),
]))

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gtk, Gdk, GdkPixbuf, Gio, GLib, GtkLayerShell, Pango

try:
    gi.require_version("GioUnix", "2.0")
    from gi.repository import GioUnix
    DesktopAppInfo = GioUnix.DesktopAppInfo
except (ValueError, ImportError):
    # Older supported GLib releases expose the same API through Gio.
    DesktopAppInfo = Gio.DesktopAppInfo

from _cyber_theme import (
    BG, BG_CARD, BG_HOT, FG, MUTED, LINE, CONTROL_LINE, ACCENT2, PURPLE,
    FONT_HEAD, FONT_BODY, rgba,
)


CSS = f"""
window.aether-root {{ background: transparent; }}
box.aether-score {{
    background-color: {rgba(BG, .87)};
    background-image: radial-gradient(ellipse at left top, {rgba(ACCENT2, .16)}, transparent 58%),
                      radial-gradient(ellipse at right bottom, {rgba(PURPLE, .16)}, transparent 55%);
    border: 1px solid {rgba(PURPLE, .55)}; border-radius: 20px;
    padding: 24px;
    box-shadow: inset 0 1px {rgba(ACCENT2, .50)}, inset 1px 0 {rgba(ACCENT2, .13)},
                inset 0 -1px {rgba(PURPLE, .24)}, 0 18px 50px {rgba(BG, .8)},
                0 0 32px {rgba(PURPLE, .16)};
}}
.aether-score label {{ color: {FG}; font-family: "{FONT_BODY}"; font-size: 14px; text-shadow: none; }}
.aether-score label.aether-title {{ font-family: "{FONT_HEAD}"; font-size: 32px; font-weight: bold; }}
.aether-score label.aether-caption {{ color: {MUTED}; font-size: 12px; }}
.aether-score label.aether-locator {{ color: {ACCENT2}; font-family: "{FONT_HEAD}"; font-size: 12px; }}
.aether-score box.aether-masthead {{
    background-color: {BG_CARD};
    background-image: radial-gradient(ellipse at left top, {rgba(ACCENT2, .16)}, transparent 65%),
                      linear-gradient(110deg, {rgba(PURPLE, .08)}, transparent 70%);
    border: 1px solid {LINE}; border-top-color: {rgba(ACCENT2, .55)};
    border-radius: 12px; padding: 10px 20px;
    box-shadow: inset 0 1px {rgba(ACCENT2, .13)}, 0 6px 20px {rgba(BG, .25)};
}}
.aether-score box.aether-scope-track {{
    background-color: {BG_CARD};
    background-image: linear-gradient(to bottom, {rgba(ACCENT2, .06)}, transparent 45%);
    border: 1px solid {LINE}; border-left-color: {rgba(ACCENT2, .35)};
    border-radius: 10px; padding: 12px 8px;
}}
.aether-score box.aether-reading-bed {{
    background-color: {BG_CARD}; border: 1px solid {LINE}; border-radius: 10px; padding: 8px 0 0 0;
    box-shadow: inset 0 1px {rgba(ACCENT2, .08)};
}}
.aether-score label.aether-track-label {{ color: {MUTED}; font-family: "{FONT_HEAD}"; font-size: 11px; padding: 0 10px; }}
.aether-score label.aether-count {{ color: {FG}; font-family: "{FONT_HEAD}"; font-size: 13px; padding: 0 12px 4px; }}
.aether-score label.aether-coordinate {{ color: {MUTED}; font-family: "{FONT_HEAD}"; font-size: 11px; }}
.aether-score entry {{
    background: {BG_CARD}; color: {FG}; border: 1px solid {CONTROL_LINE};
    border-radius: 8px; padding: 12px 14px; font-family: "{FONT_BODY}";
    font-size: 15px; box-shadow: inset 0 1px {rgba(ACCENT2, .08)};
}}
.aether-score entry:focus {{ border-color: {PURPLE}; box-shadow: 0 0 0 1px {PURPLE}; }}
.aether-score entry selection {{ background: {ACCENT2}; color: {BG}; }}
.aether-score list {{ background: transparent; }}
.aether-score row {{ background: transparent; border: none; padding: 0; }}
.aether-score row:focus {{ outline: 2px solid {PURPLE}; outline-offset: -2px; }}
.aether-score row:focus box.aether-lane,
.aether-score row:focus box.aether-index-lane {{ box-shadow: inset 0 0 0 2px {PURPLE}; }}
.aether-score row:selected {{
    background-color: {BG_HOT};
    background-image: linear-gradient(to right, {rgba(ACCENT2, .07)}, transparent 80%);
}}
.aether-score box.aether-lane {{
    padding: 10px 12px; border-bottom: 1px solid {LINE};
    border-left: 3px solid transparent; min-height: 34px;
}}
.aether-score row:selected box.aether-lane {{ border-left-color: {ACCENT2}; }}
.aether-score row:selected label.aether-row-name {{ color: {ACCENT2}; }}
.aether-score box.aether-index-lane {{ padding: 10px 10px; border-left: 3px solid transparent; }}
.aether-score row:selected box.aether-index-lane {{ border-left-color: {ACCENT2}; }}
.aether-score box.aether-detail {{
    background-color: {BG_CARD};
    background-image: linear-gradient(to bottom, {rgba(PURPLE, .07)}, transparent 42%);
    border: 1px solid {LINE}; border-top-color: {rgba(PURPLE, .65)};
    border-radius: 12px; padding: 20px;
    box-shadow: inset 0 1px {rgba(PURPLE, .16)}, 0 8px 20px {rgba(BG, .22)};
}}
.aether-score label.aether-detail-title {{ font-size: 20px; font-weight: bold; }}
.aether-score button {{
    background: {BG_HOT}; color: {FG}; border: 1px solid {CONTROL_LINE};
    border-radius: 8px; padding: 10px 14px; box-shadow: none;
}}
.aether-score button:hover {{ border-color: {ACCENT2}; }}
.aether-score button:focus {{ outline: 2px solid {PURPLE}; outline-offset: 2px; }}
.aether-score button.aether-action {{
    border-color: {ACCENT2};
    background-image: linear-gradient(to bottom, {rgba(ACCENT2, .07)}, transparent);
    box-shadow: inset 0 1px {rgba(ACCENT2, .12)};
}}
.aether-score button.aether-action label {{ color: {ACCENT2}; }}
.aether-score button:disabled, .aether-score button.aether-action:disabled {{
    background: {BG_CARD}; border-color: {LINE}; box-shadow: none; transition: none;
}}
.aether-score button:disabled label, .aether-score button.aether-action:disabled label {{ color: {MUTED}; }}
.aether-score box.aether-empty {{ padding: 20px; }}
.aether-score label.aether-empty-title {{ font-size: 18px; font-weight: bold; }}
.aether-score label.aether-empty-copy {{ color: {MUTED}; font-size: 14px; }}
.aether-score separator {{ background: {LINE}; min-height: 1px; min-width: 1px; }}
.aether-score scrolledwindow {{ background: transparent; border: none; }}
.aether-score scrollbar {{ background: transparent; }}
.aether-score scrollbar slider {{ background: {LINE}; border-radius: 4px; min-width: 5px; min-height: 24px; }}
.aether-score scrollbar slider:hover {{ background: {ACCENT2}; }}
.aether-score combobox button {{ background: {BG_CARD}; }}
.aether-score label.aether-footer {{ border-top: 1px solid {rgba(LINE, .7)}; padding-top: 10px; }}
box.aether-score.compact {{ padding: 16px; }}
.aether-score.compact label.aether-title {{ font-size: 20px; }}
.aether-score.compact box.aether-masthead {{ padding: 10px 12px; }}
.aether-score.compact box.aether-detail {{ padding: 12px; }}
.aether-score.compact label.aether-detail-title {{ font-size: 15px; }}
box.aether-score.short {{ padding: 12px; }}
.aether-score.short entry {{ padding: 8px 10px; }}
.aether-score.short button {{ padding: 6px 10px; }}
.aether-score.short box.aether-masthead {{ padding: 6px 8px; }}
.aether-score.short box.aether-reading-bed {{ padding-top: 6px; }}
.aether-score.short label.aether-count {{ font-size: 12px; padding-bottom: 4px; }}
.aether-score.short label.aether-footer {{ padding-top: 2px; border-top: none; }}
.aether-score.short box.aether-detail {{ padding: 8px; }}
.aether-score.short box.aether-empty {{ padding: 8px 12px; }}
.aether-score.short label.aether-empty-title {{ font-size: 14px; }}
.aether-score.short label.aether-empty-copy {{ font-size: 12px; }}
.aether-score expander {{ color: {MUTED}; }}
scrolledwindow.aether-context-viewport {{ background: transparent; border: none; }}
"""


def typography_scale(settings):
    """Honor the user's GTK font point size; 10pt preserves the chosen default."""
    description = Pango.FontDescription.from_string(settings.get_property("gtk-font-name") or "Sans 10")
    size = description.get_size() / Pango.SCALE
    if description.get_size_is_absolute():
        size *= 72 / 96  # Absolute font-name px in GTK logical coordinates.
    return size / 10 if size > 0 else 1.0


def stylesheet(settings):
    scale = typography_scale(settings)
    return re.sub(r"font-size:\s*([0-9.]+)px", lambda match: f"font-size: {float(match[1]) * scale:g}px", CSS)


def label(text, style=None, ellipsize=False):
    widget = Gtk.Label(label=text, xalign=0)
    if style:
        widget.get_style_context().add_class(style)
    if ellipsize:
        widget.set_ellipsize(Pango.EllipsizeMode.END)
    return widget


def icon_identifier(icon):
    """Keep a GIcon's preferred theme name or absolute file path."""
    if isinstance(icon, Gio.FileIcon):
        return icon.get_file().get_path() or "application-x-executable"
    if isinstance(icon, Gio.ThemedIcon):
        names = icon.get_names()
        return names[0] if names else "application-x-executable"
    return "application-x-executable"


def set_icon(image, identifier, size, scale=None):
    """Support both installed theme icons and .desktop absolute Icon= files."""
    if identifier and os.path.isabs(identifier):
        try:
            scale = max(1, scale or image.get_scale_factor())
            pixels = GdkPixbuf.Pixbuf.new_from_file_at_scale(identifier, size * scale, size * scale, True)
            if scale > 1:
                image.set_from_surface(Gdk.cairo_surface_create_from_pixbuf(pixels, scale, None))
            else:
                image.set_from_pixbuf(pixels)
            return
        except GLib.Error:
            pass
    theme = Gtk.IconTheme.get_default()
    name = identifier if identifier and theme.has_icon(identifier) else semantic_icon("aether-application", "application-x-executable")
    image.set_from_icon_name(name, Gtk.IconSize.DIALOG)
    image.set_pixel_size(size)


SCOPE_ICONS = {
    "All": ("aether-library", "view-grid-symbolic"),
    "Recent": ("aether-recent", "document-open-recent-symbolic"),
    "Development": ("aether-development", "applications-development"),
    "Games": ("aether-games", "applications-games"),
    "Game": ("aether-games", "applications-games"),
    "Graphics": ("aether-graphics", "applications-graphics"),
    "Network": ("aether-network", "network-workgroup-symbolic"),
    "AudioVideo": ("aether-media", "applications-multimedia"),
    "Audio & video": ("aether-media", "applications-multimedia"),
    "Office": ("aether-office", "applications-office"),
    "System": ("aether-system", "preferences-system-symbolic"),
    "Other": ("aether-utilities", "applications-utilities"),
}


def semantic_icon(name, fallback):
    theme = Gtk.IconTheme.get_default()
    return name if theme.has_icon(name) else fallback


def scope_icon(name):
    if name.startswith("Workspace "):
        return semantic_icon("aether-workspace", "view-grid-symbolic")
    return semantic_icon(*SCOPE_ICONS.get(name, ("aether-library", "folder-symbolic")))


def item_parts(item):
    """Three-tuples remain valid; optional metadata never changes the payload."""
    icon, title, payload = item[:3]
    metadata = item[3] if len(item) > 3 and isinstance(item[3], dict) else {}
    return icon, title, payload, metadata


def searchable(text):
    # Match composed/decomposed input and case without changing displayed text.
    return unicodedata.normalize("NFKC", text).casefold()


def describe(payload, scope, metadata=None):
    """Expose actual window facts; application payloads are desktop entry IDs."""
    if isinstance(payload, dict):
        workspace = payload.get("workspace", {})
        destination = workspace.get("name") or str(workspace.get("id", "—"))
        monitor = payload.get("_aether_output", "")
        mode = "Fullscreen" if payload.get("fullscreen") else "Floating" if payload.get("floating") else "Tiled"
        info = [f"App  {payload['class']}" if payload.get("class") else "",
                f"Output  {monitor}" if monitor else "", f"Layout  {mode}"]
        return f"Workspace {destination}", "\n".join(filter(None, info))
    if metadata:
        return metadata.get("category") or scope, metadata.get("description") or "Installed application"
    return scope, str(payload)


def focused_monitor():
    display = Gdk.Display.get_default()
    monitor = display.get_primary_monitor() or display.get_monitor(0)
    try:
        result = subprocess.run(["hyprctl", "monitors", "-j"], capture_output=True,
                                text=True, timeout=.5, check=True)
        active = next(m for m in json.loads(result.stdout) if m.get("focused"))
        monitor = display.get_monitor_at_point(active["x"] + 1, active["y"] + 1) or monitor
    except (OSError, subprocess.SubprocessError, ValueError, StopIteration, KeyError):
        pass
    return monitor


class ScoreWindow(Gtk.Window):
    def __init__(self, prompt, tabs, hint="", *, layer=True, monitor=None, size=None, show=True):
        super().__init__(title=f"{prompt} · Instrument/Score Aether")
        self.prompt = prompt
        self.tabs = list(tabs) or [("All", [])]
        self.tab_index = 0
        self.items = []
        self.pending = None
        self.did_activate = False
        self._building = False
        self._closed = False
        self._monitor_handlers = []
        self._hotkeys = {t[2]: i for i, t in enumerate(self.tabs) if len(t) > 2 and t[2] is not None}
        self._explicit_hotkeys = any(len(t) > 2 for t in self.tabs)
        self.get_style_context().add_class("aether-root")
        monitor = monitor or focused_monitor()
        geometry = monitor.get_geometry()
        width = min(1180, max(280, geometry.width - 64))
        height = min(740, max(280, geometry.height - 96))
        if size:
            width, height = size
        self.wide = width >= 900
        self.short = not self.wide and height < 600
        self._icon_scale = monitor.get_scale_factor()
        if layer:
            GtkLayerShell.init_for_window(self)
            GtkLayerShell.set_monitor(self, monitor)
            GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
            # Keep the verified blur/focus namespace; no compositor reconfiguration.
            GtkLayerShell.set_namespace(self, "cyber-carousel")
            GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.EXCLUSIVE)
            for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM,
                         GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
                GtkLayerShell.set_anchor(self, edge, True)
        else:
            self.set_default_size(width + 64, height + 64)
        visual = self.get_screen().get_rgba_visual()
        if visual:
            self.set_visual(visual)
        self.set_app_paintable(True)
        self.provider = Gtk.CssProvider()
        self._settings = Gtk.Settings.get_default()
        self._font_handler = None
        self.provider.load_from_data(stylesheet(self._settings).encode())
        Gtk.StyleContext.add_provider_for_screen(self.get_screen(), self.provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        outer = Gtk.EventBox()
        outer.connect("button-press-event", self._outside)
        self.add(outer)
        card_events = Gtk.EventBox()
        card_events.set_visible_window(False)
        card_events.connect("button-press-event", lambda *_: True)
        card_events.set_halign(Gtk.Align.CENTER)
        card_events.set_valign(Gtk.Align.CENTER)
        outer.add(card_events)
        self.card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.card.get_style_context().add_class("aether-score")
        self.card.set_size_request(width if self.wide else -1, height if self.wide else -1)
        if not self.wide:
            self.card.get_style_context().add_class("compact")
            self.card.set_spacing(10)
        if self.short:
            self.card.get_style_context().add_class("short")
            self.card.set_spacing(8)
        # Bound the complete composition too: explicit larger-font preferences
        # may require scrolling, including in the wide edition. Never cap fonts
        # or strand controls beyond the output to preserve a still composition.
        self.panel = Gtk.ScrolledWindow()
        self.panel.get_style_context().add_class("aether-context-viewport")
        self.panel.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.panel.set_size_request(width, height)
        self.panel.add(self.card)
        card_events.add(self.panel)
        header = Gtk.Box(spacing=16)
        header.get_style_context().add_class("aether-masthead")
        heading = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        caption = label("WORKSPACES / OVERVIEW" if prompt == "Windows" else "APPLICATIONS / LIBRARY", "aether-locator")
        heading.pack_start(caption, False, False, 0)
        if self.short:
            caption.set_no_show_all(True)
        heading.pack_start(label("Windows" if prompt == "Windows" else "Applications", "aether-title"), False, False, 0)
        header.pack_start(heading, True, True, 0)
        close = Gtk.Button(label="Close")
        close.set_valign(Gtk.Align.CENTER)
        close.connect("clicked", lambda *_: self.close_menu())
        header.pack_end(close, False, False, 0)
        self.card.pack_start(header, False, False, 0)

        self.search = Gtk.SearchEntry()
        self.search.set_icon_from_icon_name(Gtk.EntryIconPosition.PRIMARY, semantic_icon("aether-search", "system-search-symbolic"))
        self.search.set_placeholder_text("Search windows in this scope…" if prompt == "Windows" else "Search applications in this scope…")
        self.search.get_accessible().set_name("Search current scope")
        self.search.connect("changed", lambda *_: self.rebuild())
        self.search.connect("activate", lambda *_: self.activate_selected())
        self.card.pack_start(self.search, False, False, 0)

        body = Gtk.Box(spacing=20)
        self.card.pack_start(body, True, True, 0)
        self.scope_list = Gtk.ListBox()
        self.scope_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.scope_list.set_activate_on_single_click(True)
        self.scope_list.get_accessible().set_name("Workspaces" if prompt == "Windows" else "Application categories")
        for i, tab in enumerate(self.tabs):
            row = Gtk.ListBoxRow()
            content = Gtk.Box(spacing=8)
            content.get_style_context().add_class("aether-index-lane")
            icon = Gtk.Image()
            set_icon(icon, scope_icon(tab[0]), 18, self._icon_scale)
            content.pack_start(icon, False, False, 0)
            scope_name = label(tab[0], ellipsize=True)
            scope_name.set_max_width_chars(16)
            content.pack_start(scope_name, True, True, 0)
            content.pack_end(label(str(len(tab[1])), "aether-caption"), False, False, 0)
            row.set_tooltip_text(tab[0])
            item_noun = "window" if prompt == "Windows" else "application"
            row.get_accessible().set_name(f"{tab[0]}, {len(tab[1])} {item_noun if len(tab[1]) == 1 else item_noun + 's'}")
            row.add(content)
            self.scope_list.add(row)
        self.scope_list.connect("row-selected", self._scope_selected)
        scope_model = Gtk.ListStore(str, str)
        self.scope_combo = Gtk.ComboBox.new_with_model(scope_model)
        self.scope_combo.get_accessible().set_name("Workspace scope" if prompt == "Windows" else "Application category")
        for tab in self.tabs:
            scope_model.append([scope_icon(tab[0]), tab[0]])
        scope_image = Gtk.CellRendererPixbuf()
        scope_image.set_property("stock-size", Gtk.IconSize.MENU)
        self.scope_combo.pack_start(scope_image, False)
        self.scope_combo.add_attribute(scope_image, "icon-name", 0)
        scope_text = Gtk.CellRendererText()
        scope_text.set_property("ellipsize", Pango.EllipsizeMode.END)
        scope_text.set_property("width-chars", 18)
        scope_text.set_property("max-width-chars", 18)
        self.scope_combo.pack_start(scope_text, True)
        self.scope_combo.add_attribute(scope_text, "text", 1)
        self.scope_combo.set_active(0)
        self.scope_combo.connect("changed", self._combo_changed)

        if self.wide:
            scope_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            scope_box.get_style_context().add_class("aether-scope-track")
            scope_box.set_size_request(172, -1)
            scope_box.pack_start(label("WORKSPACES" if prompt == "Windows" else "CATEGORIES", "aether-track-label"), False, False, 0)
            scope_scroll = Gtk.ScrolledWindow()
            scope_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scope_scroll.add(self.scope_list)
            scope_box.pack_start(scope_scroll, True, True, 0)
            body.pack_start(scope_box, False, False, 0)
        else:
            self.card.reorder_child(body, -1)
            self.card.pack_start(self.scope_combo, False, False, 0)
            self.card.reorder_child(self.scope_combo, 2)

        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4 if self.short else 8)
        main.get_style_context().add_class("aether-reading-bed")
        main.set_hexpand(True)
        self.count = label("", "aether-count", ellipsize=True)
        self.count.set_max_width_chars(70 if self.wide else 30)
        main.pack_start(self.count, False, False, 0)
        self.results = Gtk.ListBox()
        self.results.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.results.set_activate_on_single_click(True)
        self.results.get_accessible().set_name("Matching windows" if prompt == "Windows" else "Matching applications")
        self.results.connect("row-selected", self._selected)
        self.results.connect("row-activated", lambda *_: self.activate_selected())
        self.scroller = Gtk.ScrolledWindow()
        self.scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroller.set_size_request(-1, 150 if self.wide else 54 if self.short else 96)
        self.result_stack = Gtk.Stack()
        self.result_stack.set_transition_type(Gtk.StackTransitionType.NONE)
        self.result_stack.set_homogeneous(False)
        self.result_stack.add_named(self.results, "results")
        empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6 if self.short else 12)
        empty.get_style_context().add_class("aether-empty")
        empty.set_halign(Gtk.Align.CENTER)
        empty.set_valign(Gtk.Align.CENTER)
        self.empty_icon = Gtk.Image()
        set_icon(self.empty_icon, semantic_icon("aether-empty-search", "system-search-symbolic"), 20 if self.short else 40, self._icon_scale)
        empty.pack_start(self.empty_icon, False, False, 0)
        self.empty_title = label("", "aether-empty-title")
        self.empty_title.set_line_wrap(True)
        self.empty_title.set_max_width_chars(38)
        self.empty_copy = label("", "aether-empty-copy")
        self.empty_copy.set_line_wrap(True)
        self.empty_copy.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.empty_copy.set_max_width_chars(38 if self.wide else 32)
        empty.pack_start(self.empty_title, False, False, 0)
        empty.pack_start(self.empty_copy, False, False, 0)
        self.result_stack.add_named(empty, "empty")
        self.scroller.add(self.result_stack)
        self.result_stack.show_all()
        main.pack_start(self.scroller, True, True, 0)
        body.pack_start(main, True, True, 0)

        self.detail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14 if self.wide else 8)
        self.detail.get_style_context().add_class("aether-detail")
        self.detail.set_size_request(245 if self.wide else -1, -1)
        self.detail_icon = Gtk.Image()
        self.detail_icon.set_halign(Gtk.Align.START)
        if self.wide:
            self.detail.pack_start(label("SELECTED WINDOW" if prompt == "Windows" else "SELECTED APPLICATION", "aether-track-label"), False, False, 0)
            self.detail.pack_start(self.detail_icon, False, False, 0)
        self.detail_title = label("", "aether-detail-title")
        self.detail_title.set_line_wrap(True)
        self.detail_title.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.detail_title.set_max_width_chars(23 if self.wide else 55)
        self.detail_title.set_lines(3 if self.wide else 2)
        self.detail_title.set_ellipsize(Pango.EllipsizeMode.END)
        self.detail.pack_start(self.detail_title, False, False, 0)
        self.detail_scope = label("", "aether-locator")
        self.detail_scope.set_ellipsize(Pango.EllipsizeMode.END)
        self.detail_scope.set_max_width_chars(26 if self.wide else 36)
        self.detail.pack_start(self.detail_scope, False, False, 0)
        self.detail_info = label("", "aether-caption")
        self.detail_info.set_line_wrap(True)
        self.detail_info.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.detail_info.set_max_width_chars(26 if self.wide else 55)
        self.detail_info.set_lines(6 if self.wide else 4 if self.short else 3)
        self.detail_info.set_ellipsize(Pango.EllipsizeMode.END)
        self.detail.pack_start(self.detail_info, False, False, 0)
        if self.short:
            # Keep the direct action in sight on short logical displays. Full
            # identity/evidence is an explicit disclosure, never silently lost.
            metadata = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            for child in (self.detail_title, self.detail_scope, self.detail_info):
                self.detail.remove(child)
                metadata.pack_start(child, False, False, 0)
            disclosure = Gtk.Expander(label="Selected item details")
            disclosure.add(metadata)
            self.detail.pack_start(disclosure, False, False, 0)
        action = "Switch to window" if prompt == "Windows" else "Launch application"
        self.action = Gtk.Button(label=action)
        self.action.get_style_context().add_class("aether-action")
        self.action.connect("clicked", lambda *_: self.activate_selected())
        self.detail.pack_end(self.action, False, False, 0)
        if self.wide:
            body.pack_end(self.detail, False, False, 0)
        else:
            self.card.pack_start(self.detail, False, False, 0)

        footer = label("↑ ↓ select · Enter open · Esc close" if self.short else "↑ ↓ select · Enter open · Esc close · Ctrl+Tab scope · Alt+1–9 jump", "aether-caption")
        footer.set_tooltip_text("Ctrl+Tab / Ctrl+Shift+Tab cycle scopes · Alt+1–9 jump · Ctrl+F search")
        footer.get_style_context().add_class("aether-footer")
        footer.set_line_wrap(True)
        footer.set_max_width_chars(110)
        self.card.pack_start(footer, False, False, 0)
        self.connect("key-press-event", self._key)
        self.connect("destroy", self._destroyed)
        # Closing a transient chooser is safer than moving its targets under the
        # pointer when its output disappears or its logical geometry changes.
        self._monitor_geometry = (geometry.x, geometry.y, geometry.width, geometry.height, monitor.get_scale_factor())
        for signal in ("invalidate", "notify::geometry", "notify::scale-factor"):
            self._monitor_handlers.append((monitor, monitor.connect(signal, self._monitor_changed)))
        self.scope_list.select_row(self.scope_list.get_row_at_index(0))
        self._font_handler = self._settings.connect("notify::gtk-font-name", self._font_changed)
        if show:
            self.show_all()
            self.search.grab_focus()

    def _outside(self, _widget, event):
        if event.button == 1:
            self.close_menu()
        return True

    def _scope_selected(self, _box, row):
        if row is not None and row.get_index() != self.tab_index:
            self.jump_tab(row.get_index())
        elif not self.items:
            self.rebuild()

    def _combo_changed(self, combo):
        if combo.get_active() >= 0 and combo.get_active() != self.tab_index:
            self.jump_tab(combo.get_active())

    def jump_tab(self, index):
        if not 0 <= index < len(self.tabs):
            return
        self.tab_index = index
        self.scope_list.select_row(self.scope_list.get_row_at_index(index))
        self.scope_combo.set_active(index)
        self.search.set_text("")
        self.rebuild()
        self.search.grab_focus()

    def rebuild(self):
        query = searchable(self.search.get_text().strip())
        name, raw = self.tabs[self.tab_index][:2]
        def matches(item):
            _icon, title, payload, metadata = item_parts(item)
            words = [title, *describe(payload, name, metadata)]
            if isinstance(payload, str):
                words.append(payload)  # An app ID remains searchable, not ordinary display copy.
            words.extend(metadata.get("keywords", []))
            return query in searchable(" ".join(words))
        self.items = [item for item in raw if matches(item)]
        self.search.get_accessible().set_name(f"Search {'windows' if self.prompt == 'Windows' else 'applications'} in {name}")
        self._building = True
        for row in self.results.get_children():
            self.results.remove(row)
            row.destroy()
        for item in self.items:
            icon, title, payload, metadata = item_parts(item)
            row = Gtk.ListBoxRow()
            line = Gtk.Box(spacing=12)
            line.get_style_context().add_class("aether-lane")
            image = Gtk.Image()
            set_icon(image, icon, 28, self._icon_scale)
            line.pack_start(image, False, False, 0)
            title_label = label(title, "aether-row-name", ellipsize=True)
            title_label.set_max_width_chars(70 if self.wide else 38)
            line.pack_start(title_label, True, True, 0)
            context, _ = describe(payload, name, metadata)
            meta = label(context, "aether-coordinate", ellipsize=True)
            meta.set_width_chars(13 if self.wide else 8)
            meta.set_max_width_chars(13 if self.wide else 8)
            meta.set_xalign(1)
            meta.set_tooltip_text(context)
            line.pack_end(meta, False, False, 0)
            row.set_tooltip_text(title)
            row.get_accessible().set_name(f"{title}, {context}")
            row.add(line)
            self.results.add(row)
        self._building = False
        noun = "window" if self.prompt == "Windows" else "application"
        self.count.set_text(f"{name}  /  {len(self.items)} {noun if len(self.items) == 1 else noun + 's'}")
        self.count.set_tooltip_text(self.count.get_text())
        self.scope_combo.set_tooltip_text(name)
        self.results.show_all()
        self.empty_title.set_text("No matches" if query else "No windows" if self.prompt == "Windows" else "No applications")
        empty_symbol = ("aether-empty-search", "system-search-symbolic") if query else (
            ("aether-window", "view-grid-symbolic") if self.prompt == "Windows" else ("aether-library", "folder-symbolic"))
        set_icon(self.empty_icon, semantic_icon(*empty_symbol), 20 if self.short else 40, self._icon_scale)
        self.empty_copy.set_text("Try a shorter search or choose another scope." if query else
                                 "Open an application to see its window here." if self.prompt == "Windows" else
                                 "Installed applications appear in this scope.")
        self.result_stack.set_visible_child_name("results" if self.items else "empty")
        self.results.select_row(self.results.get_row_at_index(0))
        if not self.items:
            self._selected(self.results, None)

    def _selected(self, _list, row):
        if self._building:
            return
        if row is None:
            self.detail_title.set_text("No selection")
            self.detail_title.set_tooltip_text(None)
            self.detail_scope.set_text(self.tabs[self.tab_index][0])
            self.detail_scope.set_tooltip_text(self.tabs[self.tab_index][0])
            self.detail_info.set_text("Choose an item from the score to inspect it here.")
            self.detail_info.set_tooltip_text(None)
            self.detail_icon.clear()
            self.action.set_sensitive(False)
            self.action.get_accessible().set_name("Switch to window" if self.prompt == "Windows" else "Launch application")
            return
        icon, title, payload, metadata = item_parts(self.items[row.get_index()])
        scope, info = describe(payload, self.tabs[self.tab_index][0], metadata)
        self.detail_title.set_text(title)
        self.detail_title.set_tooltip_text(title)
        self.detail_scope.set_text(scope)
        self.detail_scope.set_tooltip_text(scope)
        self.detail_info.set_text(info)
        self.detail_info.set_tooltip_text(info)
        set_icon(self.detail_icon, icon, 56, self._icon_scale)
        self.action.set_sensitive(True)
        self.action.get_accessible().set_name(f"{'Switch to' if self.prompt == 'Windows' else 'Launch'} {title}")
        # Scroll only when selection leaves the visible range; no frame loop.
        GLib.idle_add(self._ensure_visible, row)

    def _ensure_visible(self, row):
        if self._closed or row.get_parent() is None:
            return False
        adjustment = self.scroller.get_vadjustment()
        bounds = row.get_allocation()
        if bounds.y < adjustment.get_value():
            adjustment.set_value(bounds.y)
        elif bounds.y + bounds.height > adjustment.get_value() + adjustment.get_page_size():
            adjustment.set_value(bounds.y + bounds.height - adjustment.get_page_size())
        return False

    def step(self, delta):
        if not self.items:
            return
        row = self.results.get_selected_row()
        index = ((row.get_index() if row else 0) + delta) % len(self.items)
        self.results.select_row(self.results.get_row_at_index(index))

    def _key(self, _widget, event):
        name = Gdk.keyval_name(event.keyval)
        ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        alt = bool(event.state & Gdk.ModifierType.MOD1_MASK)
        shift = bool(event.state & Gdk.ModifierType.SHIFT_MASK)
        focus = self.get_focus()
        in_results = focus is not None and (focus == self.results or focus.is_ancestor(self.results))
        if name == "Escape":
            self.close_menu()
        elif ctrl and name in ("f", "F") and not alt:
            self.search.grab_focus()
            self.search.select_region(0, -1)
        elif ctrl and name in ("Tab", "ISO_Left_Tab"):
            self.jump_tab((self.tab_index + (-1 if shift or name == "ISO_Left_Tab" else 1)) % len(self.tabs))
        elif alt and name and name.isdigit():
            digit = int(name)
            index = self._hotkeys.get(digit) if self._explicit_hotkeys else digit - 1
            if index is not None:
                self.jump_tab(index)
        elif name in ("Up", "Down") and (self.search.has_focus() or in_results):
            self.step(-1 if name == "Up" else 1)
        elif name in ("Return", "KP_Enter") and (self.search.has_focus() or in_results):
            self.activate_selected()
        elif name in ("Left", "Right") and in_results:
            self.step(-1 if name == "Left" else 1)
        elif in_results and not ctrl and not alt and (
                Gdk.keyval_to_unicode(event.keyval) or (name and name.startswith("dead_"))):
            self.search.grab_focus()
            return self.search.handle_event(event)
        else:
            return False
        return True

    def activate_selected(self):
        row = self.results.get_selected_row()
        if row is None or self._closed:
            return
        self.pending = self.items[row.get_index()][2]
        self.did_activate = True
        self.close_menu()

    def close_menu(self):
        if not self._closed:
            self.destroy()

    def _monitor_changed(self, monitor, param=None):
        if self._closed:
            return
        if param is None:
            self.close_menu()
            return
        geometry = monitor.get_geometry()
        current = (geometry.x, geometry.y, geometry.width, geometry.height, monitor.get_scale_factor())
        if current != self._monitor_geometry:
            self.close_menu()

    def _font_changed(self, *_):
        if self._closed:
            return
        self.provider.load_from_data(stylesheet(self._settings).encode())
        selected = self.results.get_selected_row()
        if selected:
            GLib.idle_add(self._ensure_visible, selected)

    def _destroyed(self, *_):
        self._closed = True
        if self._font_handler is not None:
            self._settings.disconnect(self._font_handler)
            self._font_handler = None
        for monitor, handler in self._monitor_handlers:
            monitor.disconnect(handler)
        self._monitor_handlers.clear()
        Gtk.StyleContext.remove_provider_for_screen(self.get_screen(), self.provider)
        if Gtk.main_level():
            Gtk.main_quit()


def run(prompt, tabs, on_activate, hint=""):
    window = ScoreWindow(prompt, tabs, hint)
    Gtk.main()
    if window.did_activate:
        on_activate(window.pending)
