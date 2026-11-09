"""Static Aether material for existing specialized GTK menus.

Leaves child widgets, handlers, hardware commands and refresh logic untouched.
Called by the legacy install_particles entry point for compatibility.
"""
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from _cyber_theme import (
    BG, BG_CARD, BG_HOT, LINE, CONTROL_LINE, ACCENT2, PURPLE, FG, MUTED,
    SUCCESS, WARNING, DANGER, FONT_HEAD, FONT_BODY, FONT_MONO, rgba,
)
from _aether_material import surface_declarations

PREFIXES = ("pm", "wifi", "bt", "am", "cast", "rm", "kg", "calc", "rgb", "dl", "vr")
HEADING_ICONS = {
    "pm": ("system-shutdown", "system-shutdown-symbolic"),
    "wifi": ("aether-network", "network-wireless-symbolic"),
    "bt": ("aether-bluetooth", "bluetooth-symbolic"),
    "am": ("aether-audio-console", "audio-card-symbolic"),
    "cast": ("aether-cast", "video-display-symbolic"),
    "rm": ("aether-remote", "network-workgroup-symbolic"),
    "kg": ("preferences-desktop-keyboard-shortcuts", "input-keyboard-symbolic"),
    "calc": ("accessories-calculator", "accessories-calculator-symbolic"),
    "rgb": ("aether-settings", "preferences-system-symbolic"),
    "dl": ("aether-display", "video-display-symbolic"),
    "vr": ("aether-display", "video-display-symbolic"),
}


def roles(suffix, node="label"):
    """Same semantic role across the existing specialized menu class names."""
    return ",\n".join(f"box.aether-surface {node}.{prefix}-{suffix}" for prefix in PREFIXES)


CSS = f"""
box.aether-surface {{
    {surface_declarations()}
}}
box.aether-surface label {{ animation: none; text-shadow: none; }}
box.aether-surface button {{ border-radius: 8px; text-shadow: none; min-height: 24px; border-color: {CONTROL_LINE}; }}
box.aether-surface button:hover {{ background-color: {BG_HOT}; box-shadow: inset 0 1px {rgba(ACCENT2, .12)}; }}
box.aether-surface entry, box.aether-surface spinbutton,
box.aether-surface checkbutton check, box.aether-surface radiobutton radio {{ border-color: {CONTROL_LINE}; }}
box.aether-surface button:focus {{ outline: 2px solid {PURPLE}; outline-offset: 1px; box-shadow: none; }}
box.aether-surface entry:focus {{ border-color: {PURPLE}; box-shadow: inset 0 1px {rgba(PURPLE, .12)}; }}
box.aether-surface button.active, box.aether-surface button:checked {{
    color: {ACCENT2}; border-color: {ACCENT2}; background-color: {BG_HOT};
    box-shadow: inset 0 -2px {ACCENT2};
}}
box.aether-surface button.active label, box.aether-surface button:checked label {{ color: inherit; }}
box.aether-surface button.on {{ color: {SUCCESS}; border-color: {SUCCESS}; box-shadow: inset 0 -2px {SUCCESS}; }}
box.aether-surface button.on label {{ color: inherit; }}
box.aether-surface box:disabled {{ opacity: 1; }}
box.aether-surface label:disabled {{ color: {MUTED}; }}
box.aether-surface button:disabled, box.aether-surface button:disabled label {{
    color: {MUTED}; border-color: {LINE}; box-shadow: none; opacity: 1;
}}
box.aether-surface scale:not(.rgb-slider) trough {{ background-image: none; background-color: {LINE}; border-color: {CONTROL_LINE}; border-radius: 4px; }}
box.aether-surface scale:not(.rgb-slider) highlight {{ background-image: none; background-color: {ACCENT2}; border-radius: 4px; }}
box.aether-surface scale:not(.rgb-slider) slider {{ background-image: none; background-color: {BG_CARD}; border: 2px solid {ACCENT2}; }}
box.aether-surface scale value {{ color: {FG}; font-family: "{FONT_MONO}"; }}
box.aether-surface button.destructive-action, box.aether-surface label.error {{ color: {DANGER}; }}
box.aether-surface box.wifi-row-inner.connected, box.aether-surface box.bt-row-inner.connected {{
    border-color: {LINE}; border-left: 3px solid {SUCCESS}; box-shadow: none;
}}
box.aether-surface box.wifi-row-inner.hover, box.aether-surface box.bt-row-inner.hover,
box.aether-surface box.am-row.hover {{ background-color: {BG_HOT}; box-shadow: inset 0 1px {rgba(ACCENT2, .1)}; }}
box.aether-surface box.wifi-row-inner.connected label.wifi-ssid,
box.aether-surface box.bt-row-inner.connected label.bt-name {{ color: {FG}; }}
box.aether-surface box.am-colhead.k-out, box.aether-surface box.am-row.k-out {{ border-color: {LINE}; border-left: 3px solid {ACCENT2}; }}
box.aether-surface box.am-colhead.k-bus, box.aether-surface box.am-bus {{ border-color: {LINE}; border-left: 3px solid {PURPLE}; }}
box.aether-surface box.am-colhead.k-in, box.aether-surface box.am-row.k-in {{ border-color: {LINE}; border-left: 3px solid {SUCCESS}; }}
box.aether-surface label.am-tag.k-out {{ color: {ACCENT2}; }}
box.aether-surface label.am-tag.k-bus {{ color: {PURPLE}; }}
box.aether-surface label.am-tag.k-in {{ color: {SUCCESS}; }}
box.aether-surface box.am-colhead {{ background-color: {BG_CARD}; border-radius: 10px; box-shadow: inset 0 1px {rgba(ACCENT2, .08)}; }}
box.aether-surface box.am-colhead.default {{ border: 1px solid {LINE}; border-top: 2px solid {ACCENT2}; box-shadow: inset 0 1px {rgba(ACCENT2, .12)}; }}
box.aether-surface.vr-card label {{ font-size: 13px; }}
box.aether-surface.vr-card label.vr-title {{ font-size: 23px; }}
box.aether-surface.vr-card entry {{ font-family: "{FONT_MONO}"; }}
box.aether-surface label.vr-status.error {{ color: {DANGER}; }}
box.aether-surface label.vr-state.on {{ color: {SUCCESS}; }}
box.aether-surface button.am-tab, box.aether-surface button.am-tab label {{ letter-spacing: .5px; font-family: "{FONT_BODY}"; font-size: 14px; }}
box.aether-surface label.pending {{ color: {ACCENT2}; }}
{roles('signal')} {{ font-family: "{FONT_MONO}"; letter-spacing: 3px; font-size: 13px; color: {MUTED}; }}
box.aether-surface label.wifi-signal.strong, box.aether-surface label.wifi-signal.mid,
box.aether-surface label.bt-signal.strong, box.aether-surface label.bt-signal.mid {{ color: {ACCENT2}; }}
{roles('value')} {{ font-size: 13px; }}
{roles('title')} {{
    color: {FG}; font-family: "{FONT_HEAD}"; font-weight: bold;
    letter-spacing: .5px;
}}
box.aether-surface image.aether-heading-icon {{ color: {ACCENT2}; -gtk-icon-shadow: 0 0 8px {rgba(ACCENT2, .20)}; }}
{roles('status')}, {roles('hint')}, {roles('meta')}, {roles('help')} {{
    color: {MUTED}; font-family: "{FONT_BODY}"; letter-spacing: 0;
}}
{roles('status.offline')} {{ color: {WARNING}; }}
{roles('value')}, box.aether-surface label.calc-expr,
box.aether-surface label.calc-result, box.aether-surface label.kg-key {{ font-family: "{FONT_MONO}"; }}
/* State wins over ordinary metadata; do not inherit a base-theme red slab. */
box.aether-surface label.error {{ color: {DANGER}; background-color: transparent; background-image: none; }}
box.aether-surface label.pending {{ color: {ACCENT2}; background-color: transparent; background-image: none; }}
"""


def _walk(widget):
    yield widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            yield from _walk(child)


def _decorate_heading(card):
    """Add a noun locator to the existing heading without changing its actions."""
    theme = Gtk.IconTheme.get_default()
    for widget in list(_walk(card)):
        if not isinstance(widget, Gtk.Label):
            continue
        context = widget.get_style_context()
        # The old terminal block was decorative, not an editing cursor/status.
        if any(context.has_class(f"{prefix}-cursor") for prefix in PREFIXES):
            widget.set_no_show_all(True)
            widget.hide()
        prefix = next((p for p in PREFIXES if context.has_class(f"{p}-title")), None)
        if prefix is None:
            continue
        parent = widget.get_parent()
        if not isinstance(parent, Gtk.Box):
            continue
        icon_name, fallback = HEADING_ICONS[prefix]
        if not theme.has_icon(icon_name):
            icon_name = fallback
        icon = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.LARGE_TOOLBAR)
        icon.set_pixel_size(26)
        icon.get_style_context().add_class("aether-heading-icon")
        icon.set_valign(Gtk.Align.CENTER)
        icon.get_accessible().set_name("")  # Adjacent full heading carries meaning.
        if parent.get_orientation() == Gtk.Orientation.HORIZONTAL:
            parent.pack_start(icon, False, False, 0)
            parent.reorder_child(icon, 0)
            icon.set_margin_end(5)
        else:
            position = parent.get_children().index(widget)
            expand, fill, padding, pack_type = parent.query_child_packing(widget)
            parent.remove(widget)
            heading = Gtk.Box(spacing=12)
            heading.pack_start(icon, False, False, 0)
            heading.pack_start(widget, True, True, 0)
            if pack_type == Gtk.PackType.END:
                parent.pack_end(heading, expand, fill, padding)
            else:
                parent.pack_start(heading, expand, fill, padding)
            parent.reorder_child(heading, position)
    return card


def install_surface(card):
    if getattr(card, "_aether_provider", None) is not None:
        return card
    card.get_style_context().add_class("aether-surface")
    _decorate_heading(card)
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS.encode())
    screen = card.get_screen()
    Gtk.StyleContext.add_provider_for_screen(screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
    card._aether_provider = provider
    card.connect("destroy", lambda *_: Gtk.StyleContext.remove_provider_for_screen(screen, provider))
    return card
