#!/usr/bin/env python3
"""Instrument/Score Aether semantic adapter, retaining legacy import names.

The editable source is ~/.config/instrument-score-aether/tokens.json.
_aether_tokens.json is its generated portable default for copied installations.
GTK, rofi, native toolkit adapters, Kitty and Waybar consume these same roles.
Legacy pulse helpers remain for source compatibility; current surfaces suppress
decorative animation and use static material. Hardware color values must never
be derived from semantic text/status roles.

Run this module to emit shared.rasi; wallpaper regenerates it on each launch.
"""

# Instrument/Score Aether semantic token adapter; legacy names keep consumers working.
import json
import os
from pathlib import Path

TOKEN_PATH = Path(os.environ.get("XDG_CONFIG_HOME", Path.home()/".config")) / "instrument-score-aether/tokens.json"
TOKENS = json.loads((TOKEN_PATH if TOKEN_PATH.exists() else Path(__file__).with_name("_aether_tokens.json")).read_text())
C = TOKENS["color"]
INSTRUMENT_SCORE = True
BG, BG_CARD, BG_HOT = C["canvas"], C["surface"], C["raised"]
FG, MUTED, LINE = C["text"], C["secondary"], C["boundary"]
CONTROL_LINE = C.get("control_boundary", C["focus"])
ICON_THEME = TOKENS.get("icons", {}).get("theme", "aether-score")
ACCENT, ACCENT2, PURPLE = C["accent"], C["selection"], C["focus"]
SUCCESS, WARNING, DANGER = C["success"], C["warning"], C["danger"]
TILE_HUES = [ACCENT2, PURPLE, SUCCESS]
FRAME_HUES = [PURPLE]

def rgb_channels(color: str) -> tuple[int, int, int]:
    """Decode a theme token for CSS/Cairo consumers."""
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def rgba(color: str, alpha: float) -> str:
    """CSS alpha variant; RGB always comes from the source token."""
    r, g, b = rgb_channels(color)
    return f"rgba({r},{g},{b},{alpha:g})"


SCANLINE_ALPHA = 0.0
SCANLINE_PERIOD = 3


def scanline_background() -> str:
    """Legacy background hook: current material keeps glyph beds undisturbed."""
    if INSTRUMENT_SCORE:
        return "linear-gradient(to bottom, transparent, transparent)"
    return (f"repeating-linear-gradient(to bottom, {rgba(BG, SCANLINE_ALPHA)} 0px, "
            f"{rgba(BG, SCANLINE_ALPHA)} 1px, transparent 1px, "
            f"transparent {SCANLINE_PERIOD}px)")


def chromatic_shadow() -> str:
    """Legacy text-effect hook; precision text has no chromatic split."""
    return "text-shadow: none;"


# ---- typography -----------------------------------------------------------
# Split per design/DESIGN-SYSTEM.md: headings get the geometric CRT-readout
# face, body/values stay on the terminal mono already used everywhere.
# FONT_HEAD needs `ttf-sharetech-mono-nerd` (official `extra` repo, already
# Nerd-Font patched — verify the exact family fc-list reports after install,
# don't assume the name below survived patching unchanged).
FONT_HEAD = TOKENS["font"]["heading"]
FONT_BODY = TOKENS["font"]["reading"]
FONT_MONO = TOKENS["font"]["value"]

# ---- shared GTK CSS fragments ---------------------------------------------
# The 4 popout menus (power/rgb/wifi/bt) each hand-rolled an identical
# 3-stop pulse animation on their card border — same numbers, only the
# @keyframes name and CSS class prefix differed. Generate it once so a
# future glow tweak is one edit instead of four.

# Glassmorphism depth, GTK3-real (no backdrop-filter exists in GTK3 CSS —
# this is the honest substitute: a 1px inset highlight along the top inner
# edge of every card, the same trick a frosted-glass panel uses to catch a
# light source, stacked into the existing pulse box-shadow list rather than
# replacing it). Added to every popout card + the carousel card + the rofi
# theme so the "glass edge" reads as one system, not a per-menu accident.
GLASS_INSET = f"inset 0 1px 0 {rgba(ACCENT2, 0.07)}, inset 0 -1px 0 {rgba(BG, 0.35)}"


# Digital snaps limit distinct glow states while retaining the teal midpoint.
# Use the same GTK3 steps(..., end) syntax as the existing cursor blink.
PULSE_TIMING = "steps(4, end)"


def pulse_keyframes(prefix: str) -> str:
    """The purple->teal->purple border/glow pulse used by every popout's
    outer card. Pair with PULSE_TIMING in the animation declaration.
    `prefix` becomes the @keyframes name, e.g. "pm" -> "pm-pulse"."""
    return f"""@keyframes {prefix}-pulse {{
    0%   {{ border-color: {PURPLE};
            box-shadow: {GLASS_INSET},
                        0 0 0 1px {rgba(PURPLE, 0.20)},
                        0 0 46px 8px {rgba(PURPLE, 0.28)},
                        0 0 90px 20px {rgba(ACCENT, 0.16)}; }}
    50%  {{ border-color: {ACCENT2};
            box-shadow: {GLASS_INSET},
                        0 0 0 1px {rgba(ACCENT2, 0.26)},
                        0 0 60px 12px {rgba(ACCENT2, 0.34)},
                        0 0 100px 26px {rgba(ACCENT, 0.22)}; }}
    100% {{ border-color: {PURPLE};
            box-shadow: {GLASS_INSET},
                        0 0 0 1px {rgba(PURPLE, 0.20)},
                        0 0 46px 8px {rgba(PURPLE, 0.28)},
                        0 0 90px 20px {rgba(ACCENT, 0.16)}; }}
}}"""


def blink_keyframes(prefix: str) -> str:
    """The terminal-cursor blink used by every popout's title bar."""
    return f"""@keyframes {prefix}-blink {{
    0%   {{ opacity: 1; }}
    50%  {{ opacity: 0; }}
    100% {{ opacity: 1; }}
}}"""


def control_css() -> str:
    """Complete GTK3 form chrome for opt-in popouts, including detached menus.

    Use in a screen CSS provider: ComboBox menus are separate windows, so a
    selector rooted at the popout card cannot reach their menuitems.
    """
    return f"""
* {{ font-family: "{FONT_BODY}"; -gtk-icon-shadow: none; text-shadow: none; }}
label {{ color: {FG}; }}
button, entry, spinbutton {{
    background-image: none; background-color: {BG_CARD}; color: {FG};
    border: 1px solid {CONTROL_LINE}; border-radius: 5px; box-shadow: none;
    padding: 7px 9px; font-size: 11px;
}}
button:hover, button:focus, entry:focus {{ border-color: {PURPLE}; }}
button:active, button:checked {{ background-image: none; background-color: {BG_HOT}; border-color: {ACCENT2}; }}
button:disabled, entry:disabled {{ color: {MUTED}; border-color: {LINE}; }}
entry selection {{ background-color: {ACCENT2}; color: {BG}; }}
entry.error {{ border-color: {DANGER}; }}
scale {{ background-image: none; background-color: transparent; padding: 8px 2px; }}
scale trough {{ background-image: none; background-color: {LINE}; border: 1px solid {rgba(PURPLE, .35)};
    min-height: 6px; min-width: 6px; border-radius: 4px; box-shadow: none; }}
scale highlight {{ background-image: none; background-color: {ACCENT2}; border: none;
    min-height: 6px; min-width: 6px; border-radius: 4px; box-shadow: none; }}
scale slider {{ background-image: none; background-color: {ACCENT2}; border: 2px solid {BG};
    min-width: 14px; min-height: 14px; border-radius: 4px; box-shadow: 0 0 0 1px {ACCENT2}; }}
scale slider:hover, scale slider:active {{ background-color: {FG}; box-shadow: 0 0 0 2px {PURPLE}; }}
scale:disabled {{ opacity: .38; }}
scale value, scale marks {{ color: {ACCENT2}; font-size: 10px; }}
combobox button {{ background-image: none; background-color: {BG_CARD}; box-shadow: none; }}
combobox arrow, menu arrow {{ color: {ACCENT2}; min-width: 12px; min-height: 12px; }}
window.popup, menu, .menu, popover, popover.background {{
    background-image: none; background-color: {BG_CARD}; color: {FG};
    border: 1px solid {PURPLE}; border-radius: 7px; box-shadow: 0 3px 14px {rgba(BG, .8)};
}}
menu {{ padding: 5px; }}
menuitem {{ background-image: none; background-color: transparent; color: {FG}; padding: 8px 12px; border-radius: 4px; }}
menuitem:hover, menuitem:selected, modelbutton:hover, modelbutton:selected {{ background-image: none; background-color: {BG_HOT}; color: {ACCENT2}; }}
menuitem:disabled {{ color: {MUTED}; }}
menuitem label, combobox cellview {{ color: inherit; }}
list, listbox, treeview, viewport {{ background-color: transparent; color: {FG}; }}
row:selected, treeview:selected {{ background-color: {BG_HOT}; color: {ACCENT2}; }}
checkbutton, radiobutton {{ color: {ACCENT2}; padding: 5px; }}
check, radio {{ background-image: none; background-color: {BG}; color: {BG};
    border: 1px solid {PURPLE}; border-radius: 3px; min-width: 15px; min-height: 15px; box-shadow: none; }}
check:checked, radio:checked {{ background-image: none; background-color: {ACCENT2}; color: {BG}; border-color: {ACCENT2}; }}
check:hover, radio:hover {{ border-color: {FG}; }}
scrollbar, scrollbar trough {{ background-image: none; background-color: {BG}; border: none; box-shadow: none; }}
scrollbar slider {{ background-image: none; background-color: {rgba(PURPLE, .6)};
    border: none; border-radius: 4px; min-width: 6px; min-height: 6px; }}
scrollbar slider:hover {{ background-color: {ACCENT2}; }}
scrolledwindow, scrolledwindow junction {{ background-color: transparent; border: none; }}
scrolledwindow overshoot, scrolledwindow undershoot {{ background-image: none; background-color: transparent; }}
separator {{ background-color: {LINE}; min-height: 1px; min-width: 1px; }}
tooltip, tooltip.background {{ background-color: {BG_CARD}; color: {FG}; border: 1px solid {PURPLE}; }}
button.color-picker {{ padding: 5px 8px; }}
button.color-picker label {{ color: {ACCENT2}; font-size: 11px; }}
box.color-editor {{ padding: 14px; }}
"""


def build_rasi() -> str:
    """Emit the shared rofi theme (rasi) from these exact tokens. Written
    to ~/.config/rofi/shared.rasi; menu-specific rasi files @import it and
    add only what they genuinely need on top (see wallpaper.rasi for the
    -show-icons override)."""
    return f"""// GENERATED by _cyber_theme.py — do not hand-edit.
// Run `python3 _cyber_theme.py > ~/.config/rofi/shared.rasi` to resync
// after changing a token above (the `wallpaper` script does this on
// every launch, so in practice this file is always current).
//
// Two verified rasi constraints baked in below, don't reintroduce either:
//  1. Variable refs are `var(name)`, NOT `@name` — this rofi build (2.0.0)
//     silently fails theme parsing (falls back to stock default theme,
//     only a Rofi-WARNING on stderr, no line number) on `@name`. Confirmed
//     live by bisecting a minimal theme file.
//  2. `border: <width> <style> <color>` (the CSS 3-value shorthand) also
//     silently fails to parse. `border: <width> <style>;` alone works;
//     color MUST be a separate `border-color:` declaration. Also
//     confirmed live by bisection — same silent-fallback failure mode.
//  3. `var(name)` nested INSIDE a function call's argument list (e.g.
//     `linear-gradient(to bottom, {BG_CARD}, var(bg))`) also silently
//     fails — `var()` only works as a property's whole value, not as one
//     argument among several. Literal hex substituted via the f-string
//     instead wherever a token needs to sit inside a function call.

* {{
    bg:          {BG};
    bg-card:     {BG_CARD};
    bg-hot:      {BG_HOT};
    fg:          {FG};
    accent:      {ACCENT};
    accent2:     {ACCENT2};
    purple:      {PURPLE};
    muted:       {MUTED};
    line:        {LINE};

    font-head:   "{FONT_HEAD} 13";
    font-body:   "{FONT_BODY} 12";

    background-color: transparent;
    text-color:  var(fg);
}}

window {{
    background-color: var(bg);
    background-image: linear-gradient(to bottom, {BG_CARD}, {BG});
    /* TODO(supervisor): offline rofi-theme(5) documents only url() and
       linear-gradient(), not repeating-linear-gradient(). Disabled until
       parser AND rendering are tested in a scratch theme on rofi 2.x:
       background-image: {scanline_background()};
       Do not enable this in the live generated theme without that check. */
    border: 2.5px solid;
    border-color: var(purple);
    border-radius: 18px;
    /* rasi has no backdrop-filter and no clip-path — depth here is the
       layered gradient + border + the compositor blur from hyprland.lua's
       `layer_rule({{ match = "rofi", blur = true }})`, verified live against
       hyprctl's real "rofi" layer namespace. No fake box-shadow trick gets
       you real background blur in rasi; that rule is what actually does. */
    padding: 22px 26px;
    width: 640px;
    location: center;
}}

mainbox {{
    background-color: transparent;
    spacing: 16px;
    children: [ "inputbar", "message", "listview" ];
}}

inputbar {{
    background-color: var(bg-card);
    border: 2px solid;
    border-color: var(purple);
    border-radius: 12px;
    padding: 12px 18px;
    spacing: 10px;
    children: [ "prompt", "entry" ];
}}

prompt {{
    background-color: transparent;
    text-color: var(purple);
    font: var(font-head);
}}

entry {{
    background-color: transparent;
    text-color: var(fg);
    font: var(font-body);
    blink: true;
    cursor-color: var(accent2);
    cursor-width: 2px;
    hide-cursor-on-empty: false;
    placeholder: "search...";
    placeholder-color: var(muted);
}}

message {{
    background-color: var(bg-card);
    border: 1.5px solid;
    border-color: var(line);
    border-radius: 8px;
    padding: 8px 14px;
    text-color: var(muted);
    font: var(font-body);
}}

listview {{
    background-color: transparent;
    columns: 1;
    lines: 8;
    spacing: 6px;
    cycle: true;
    scrollbar: false;
    fixed-height: false;
}}

element {{
    background-color: {BG_CARD};
    border: 1.5px solid;
    border-color: var(line);
    border-radius: 10px;
    padding: 10px 14px;
    orientation: horizontal;
    spacing: 12px;
}}

element normal.normal {{
    text-color: var(fg);
}}

element selected.normal {{
    /* rasi has no `box-shadow` at all (confirmed live — parse-fails same
       as the border shorthand above), so there is no real per-row glow
       available here the way the GTK popouts get one. Selection instead
       reads through a tinted fill + a thicker saturated border — the
       honest rasi substitute, not a faked glow. */
    background-color: {BG_HOT};
    border: 2.5px solid;
    border-color: var(accent2);
    text-color: var(accent2);
}}

element-text {{
    background-color: transparent;
    text-color: inherit;
    font: var(font-body);
    vertical-align: 0.5;
}}

element-icon {{
    background-color: transparent;
    size: 28px;
    vertical-align: 0.5;
}}

scrollbar {{
    handle-color: var(purple);
    background-color: var(line);
}}
"""


def build_gtk_css() -> str:
    """Generate the Thunar GTK3 override from the shared theme tokens."""
    from _cyber_gtk import build_css
    return build_css()


def qt_palette() -> str:
    """One Qt5/Qt6 enum-role producer for native and export adapters."""
    colors = [FG, BG_CARD, PURPLE, LINE, BG, LINE, FG, FG, FG, BG, BG,
              LINE, ACCENT2, BG, ACCENT2, ACCENT, BG_CARD, FG, BG_CARD, FG, MUTED, ACCENT2]
    disabled = colors.copy()
    for index in (0, 6, 8, 19):
        disabled[index] = MUTED
    disabled[12], disabled[13] = LINE, FG
    return '[ColorScheme]\n' + ''.join(
        name + '_colors=' + ', '.join('#ff' + color[1:] for color in values) + '\n'
        for name, values in [('active', colors), ('inactive', colors), ('disabled', disabled)])


if __name__ == "__main__":
    print(build_rasi())
