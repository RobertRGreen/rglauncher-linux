# Opt-in Hyprland session

RGLauncher runs on **Hyprland 0.56's Lua configuration API**. The supplied example
is an opt-in starting session, not a new compositor or a drop-in replacement for
someone's existing monitor/network/hardware configuration. Installation leaves
the existing Hyprland configuration alone. Never mix the example wholesale into
a configuration with duplicate bindings and running shelf controllers.

The example files are `share/hyprland/hyprland.lua`, `window-navigation.lua` and
`snap-layout.lua`. The latter two carry the accepted focus/pointer/fullscreen and
tiled fractional placement implementation, with portable module paths. It has no
private display-layout, remote-host, RGB, camera, voice or HCP dependency.

## Accepted window behavior

| Input | Behavior |
| --- | --- |
| Super+1…9, Super+0 | Focus workspaces 1…10 |
| Super+Shift+1…0 | Send the focused window to that workspace, without following |
| Super+F | Toggle fullscreen |
| Super+C | Close the focused window |
| Hold Super + left mouse drag | Move; explicitly detaches a tiled snap into a floating window |
| Hold Super + right mouse drag | Resize; explicitly detaches a tiled snap into a floating window |
| Super+arrows | Snap to a tiled half; combine perpendicular arrows during the same Super hold for quarters |
| Super+Shift+arrows | Thirds; repeated arrows step through the center third, perpendicular arrows combine axes |
| Release Super | End the current snap composition; the next hold begins a new shape |
| Super+Backspace | Restore the focused window's state from before its first snap |
| Alt+Tab / Alt+Shift+Tab | Stable MRU window cycling until Alt is released |
| Super+Tab or Super+W | Release input capture and open the window overview |
| Super+Space or Super+R | Open applications |
| Super+Q / Super+D / Super+comma | Terminal / files / settings |
| Super+B | Reveal the shelf by command |
| Super+Ctrl+Alt+Delete | Deliberate session exit |

Snapped windows stay tiled. Other tiled windows share the remaining logical work
area instead of being covered by a floating slab. The six-cell layout represents
halves and thirds exactly and recalculates through Hyprland's layout API as the
work area changes. It does not hard-code one monitor's physical pixel geometry.
More windows than requested regions share available area; a conflict does not
promise all competing windows the same requested cells.

Alt+Tab changes focus and moves the pointer into the selected target. That
deactivates the old client's active pointer constraint rather than immediately
letting pointer-follow focus hand it back to the game. A fullscreen client can
retain its client render mode while its compositor presentation is temporarily
suspended to show another window on the same workspace, then restored on return.
Super+Tab explicitly uses Hyprland's release-input-capture dispatcher. These are
tested accepted desktop mechanisms, not a guarantee against every broken game,
exclusive input device, nested compositor or future Hyprland API change.

The generic example uses native workspace focus. It does not include a personal
monitor-mirroring/display-layout service. Existing installed custom workspace
behavior remains untouched; users who need custom mirroring should adapt that
integration separately.

## Review and select for a new session

First install the verified software/dependencies and confirm `rglauncher doctor`.
Review the example's monitor policy, keyboard settings, actions and autostart.
The generic monitor rule chooses preferred mode/automatic position/scale 1;
replace it in a **user-owned copy** if your displays need fractional scale or a
specific arrangement. There is no forced HDR mode or GPU-specific configuration.
Ensure a working session Polkit agent and the desired portal backends using your
distribution's normal session setup.

For a versioned per-user installation, choose the active release explicitly:

```sh
export RGL_RELEASE_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/rglauncher-linux/current"
Hyprland --verify-config --config "$RGL_RELEASE_ROOT/share/hyprland/hyprland.lua"
```

`--verify-config` parses configuration without starting Hyprland. The installed
0.56.2 binary accepts the example. Syntax verification does not replace a real
new-session/monitor/input acceptance test. For a system Arch package, use
`RGL_RELEASE_ROOT=/usr/lib/rglauncher-linux` instead.

After saving work and leaving the old session through the user's normal logout
flow, a deliberate TTY session can source the prepared native environment and
select the example:

```sh
native_env="${XDG_CONFIG_HOME:-$HOME/.config}/rglauncher-linux/native/session.sh"
if [ -f "$native_env" ]; then . "$native_env"; fi
exec Hyprland --config "$RGL_RELEASE_ROOT/share/hyprland/hyprland.lua"
```

Do not run this `exec` inside a running desktop merely to test the theme. No
display-manager session is installed or selected automatically. If configuring
one, make a user-reviewed wrapper with explicit release/environment paths and
follow the display manager's session conventions. A versioned release is software;
keep personal monitor/keymap/idle/lock/wallpaper choices in user configuration.

The example starts one `rglauncher shelf run` controller on `hyprland.start`.
The controller manages one patched Waybar per physical output, reveals at the
bottom edge, has no permanent exclusive zone, and holds while recognized popups
are active. Generic bar files must first be installed at the user's Waybar
configuration location, or supplied via shelf command arguments. The software
installer owns that preparation and preserves existing unrelated bar actions.
Do not also autostart another Waybar for the same intended shelf.

To retain the current desktop, use only the application commands/native theme
adapters and keep this session example unselected. No reload or session restart
is needed to read, review or package it.
