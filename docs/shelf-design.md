# Suspended instrument shelf

Robert's 2026-11-09 feedback reopens the desktop composition: the auto-hide bar
still looked like telemetry strips, and the design needed more detail. This pass
makes the main object an icon shelf, with a related Control Room. It preserves
accepted workspace, tiling, fullscreen, close, mouse and Alt+Tab behavior.

## Composition and material

The deck is centered and bounded, rather than stretched across an ultrawide.
Its three regions form one object: compact workspace/time context, dominant
illustrated instruments, and secondary status/utilities. The launch objects are
48px on a wide desktop and 36px in the compact edition. Smaller 24px utility
illustrations keep connection state subordinate. Names and shortcuts remain in
native tooltips; the main shelf contains no icon-font or emoji substitutes.

The eight primary identities have original layered SVG object planes, visible
side faces, inset details and restrained cyan/violet rims. A folder has layered
papers and a front lip; terminal and window objects have separate planes; the
Audio Console has actual fader-shaped controls. These are identity illustrations,
not simulated running-state meters. Their light editions preserve the same
silhouettes for future bright adapters. See [icon construction](shelf-icons.md).

A dark opaque reading bed prevents another application's title/transport controls
from showing through the shelf. Glass character comes from bounded highlights,
local object planes, thin rim illumination and the lower shelf lip. Text stays
opaque. The composition keeps Noto Sans for ordinary reading and JetBrains Mono
for time/workspace exactness. Cyan marks the real selected workspace; violet
remains keyboard focus. No permanent waveform, fake activity dot, magnification
or ambient motion is used.

## Workflows and adaptive behavior

| Context | Main shelf | Supporting work |
| --- | --- | --- |
| Wide desktop, ≥1800 logical px | Bounded1360px deck, large instrument illustrations | Core connections, health and remote status remain visible |
| Standard desktop | Bounded up to1200px | Less-used launch targets move into the searchable instrument chooser |
| Compact, <1100 logical px | Workspace disclosure, compact instruments, no inline clock | Same software/actions remain reachable; keyboard workspace navigation unchanged |

The two-pixel bottom edge reveals the shelf. It sits above windows, takes no
keyboard focus, reserves no work area and retracts after leaving its region.
The visible region includes the taller new deck. There is no compositor restart.
Native tray menus and the existing named utility layers hold it open as before.

Tools opens the established searchable score chooser instead of horizontally
expanding all telemetry across the monitor. It preserves configured primary and
alternate actions, including private camera/VR/resource tools; none of their
commands execute simply to compose or render the shelf. It uses the same scope,
search, Enter and Escape language as Apps/Windows and prevents duplicate instances.
The background-applications drawer retains native tray icons and menus. Its
capacity still depends on the number of third-party tray items and available
monitor width; a large tray on a very narrow output remains an explicit acceptance
case, not proof of universal layout coverage.

The adapter reads existing user Waybar definitions without replacing them. It
retains action commands and observed warning/remote-control classes. Custom server,
remote and camera implementations never enter the public software package.
The current-window title is deliberately represented by the Windows chooser
rather than repeated as an inline title across the shelf.

## Render critique and corrections

1. The first centered prototype still used small toolbar strokes on equal pads.
   Primary object silhouettes were replaced by purpose-drawn dimensional SVGs;
   they now dominate the smaller utility marks without growing on hover.
2. Faint media art and transport text showed through gaps behind controls. The
   bed was made opaque and rerendered over the actual busy desktop; ghost content
   disappeared. Translucency is not allowed to erase the instrument hierarchy.
3. The first1360/1200/928 designs exposed a17px minimum-width expansion on the
   compact version. Workspace/time disclosure and a separate tools chooser removed
   the competing horizontal content. Native Waybar renders then measured exactly
  1360×96,1200×96 and928×84 in those fixtures.
4. Workspace selection was heavier than the app subjects. Its vertical margins
   now form a compact locator; illustrated launch objects own the visual emphasis.

Actual Waybar renders used safe fixture status providers and disabled action
callbacks. Their local captures can contain private desktop content behind rounded
corners and are not public screenshots. Native show/hide/per-output checks separately
verify zero reserved area and unchanged keyboard focus. Offscreen Control Room
renders and synthetic tools-model checks do not claim physical hardware operation.

The broader language is still being developed. This pass establishes the icon
shelf and a more detailed related workbench; it does not declare every desktop
application or the universal design project complete.
