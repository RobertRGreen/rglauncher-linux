# Portable native adapters

`rglauncher_linux.native.apply_native()` prepares the original **RGLauncher-Aether**
native theme from a verified release. It has no Sweet-Dark dependency and copies
no third-party CSS or fonts. GTK's installed built-in Adwaita (GTK3) or Default
(GTK4) resource supplies native behavior and control glyphs; original semantic
rules provide the reading surfaces, focus, selection and input boundaries.

```python
from pathlib import Path
from rglauncher_linux.native import apply_native

receipt = apply_native(
    release_root=Path("/verified/release"),
    config_home=Path("/fixture/config"),
    data_home=Path("/fixture/data"),
    activate=False,
    state_home=Path("/fixture/state"),
)
```

The installer must verify the release before calling this API. Required payloads
are `share/instrument-score-aether/tokens.json` and the release's pure adapter
modules `bin/_cyber_theme.py`, `_cyber_gtk.py`, `_aether_material.py`, `_aether_desktop.py`.
The module renders scoped GTK CSS and the central Qt palette in an isolated
Python subprocess with a temporary token configuration. `-B` prevents writes to
the release. No GTK application, device backend or menu constructor is imported.
Color roles and font values are validated before generation.

`activate=False` writes only under the explicit configuration/data/state roots.
Its default state root is `data_home.parent / "state"`, even when a real
`XDG_STATE_HOME` is set. It never calls gsettings, xrdb, systemd, a compositor,
hardware or a session/environment activation tool. Existing application processes
retain their state. The returned `environment` describes settings for a future
RGLauncher session; the function does not modify `os.environ`.

With `activate=True`, the default state root follows `XDG_STATE_HOME` when set,
otherwise `data_home.parent / "state"`. Only six `org.gnome.desktop.interface`
preferences and twelve owned X resource keys can be activated. All available
previous values are durably written to the receipt **before** the first mutation.
Missing tools/schemas or timeouts become explicit unavailable/partial results.
This does not restart portals, applications, services or the compositor.

## Owned outputs

| Root | Files |
| --- | --- |
| Data | `themes/RGLauncher-Aether/index.theme`, GTK2 `gtkrc`, GTK3/4 `gtk.css` and `gtk-dark.css` |
| Config | GTK3/4 `settings.ini` known theme/icon/font/dark keys; managed blocks in their existing `gtk.css` |
| Config | Qt5ct/Qt6ct palette files and known Appearance/Fonts/Interface keys; custom control QSS and arrow SVGs |
| Config/Data | Known KDE native color/font/icon settings and `color-schemes/RGLauncher-Aether.colors` |
| Config | Qt Quick Controls Material settings |
| Config | `kitty/rglauncher-aether.conf` palette plus one final managed include in `kitty/kitty.conf` |
| Data | Original ttk package under `rglauncher-linux/tcl` |
| Config | `rglauncher-linux/native/Xresources`, explicit `session.sh`, `environment.d/70-rglauncher-native.conf` |

There are 27 files on a fresh installation. INI editing preserves comments,
unknown keys and unrelated sections. User CSS outside the marked adapter block
is retained; incomplete/duplicate blocks fail before any installation write.
Qt's managed control sheet precedes existing custom stylesheets so application
or user decisions can remain authoritative. Existing file modes are retained.
Output symlinks and symlinked output descendants are rejected. Concurrent changes
detected between planning/backups/replacement abort with recoverable backups.
Kitty's generated palette has no font or key bindings; existing bindings/comments
and other theme includes are retained. One final managed include gives the new
palette precedence for subsequent terminal processes. Existing terminals are not
restarted or messaged by this function.

Default native GTK rules load at **THEME priority**. They do not force a global
USER-priority canvas. Scoped USER rules remain limited to the established
application/dialog adapters. Application-priority transparent overlay roots remain
transparent. Generic GTK controls retain native checkbox/radio glyphs, visible
spin buttons, switch handles and combo arrows. Cyan marks selection, violet
marks focus; stronger control boundaries are distinct from quiet reading dividers.
Native values use the exact-value font; normal labels use the reading font.

Qt5ct and Qt6ct use their respective configuration/palette files. Qt6ct supports
the shared `qt5ct` platform-theme alias on the tested implementation. The native
Qt preference can only affect applications loading those plugins; private app
themes and missing platform plugins remain application/dependency concerns.
No application executable, Qt plugin, base theme or font is bundled here.
Libadwaita/private web/Java/application rendering is not universally restyled by
GTK defaults. This module is a native adapter, not a claim to override every UI.

The ttk package is discoverable through the generated `TCLLIBPATH`. X11 Tk's
standard `*TkTheme` preference can select it after X resource/session activation;
applications may also explicitly require/use `rglauncher-aether`. The library
does not patch the system Tk startup code or inject code into existing processes.

## Receipt and rollback contract

The return value and durable `manifest` JSON contain:

- `theme`, `changed`, `new_paths`, `backup_dir`, `manifest`;
- `backups`: absolute changed path → saved original path, or `null` for a new file;
- `original_modes`: original permission bits by changed path, or `null` for a new file;
- `installed_sha256`: expected installed bytes for each changed path;
- `environment`: explicit session environment values;
- `validation`: each GTK version's availability, built-in base resource and parse errors;
- `activation`: `requested`, overall status and per-tool before values/status/errors.

Backups live in `state_home/rglauncher-linux/native-backups/<UTC>-<random>/`.
Original bytes and the receipt have mode 0600; the release backup directory has
mode 0700. The installer should retain this receipt in its own rollback record.
Before restoring/removing a changed file, verify its current hash against the
receipt to preserve edits made after installation. Restore saved originals or
remove matching newly created files; leave unrelated files and directories alone.
Restore each original file's recorded mode rather than its private backup mode.
Preference before values are gsettings GVariant text and the previous values
of the owned X resource keys, with `null` indicating absence. Restore these only
through an explicit coordinated rollback, preserving unrelated preference keys.

## Verification

Run `python3 -m unittest discover -s tests -p test_native.py -v`.
Ten focused tests verify isolated preparation, 27-file coverage, idempotence,
backups/modes, preservation, symlink rejection, invalid token rejection, toolkit
font roles, activation journaling/timeouts and GTK3/4 built-in CSS parsing when
the corresponding GI library is installed. Missing GTK GI reports unavailable;
an available GTK with invalid CSS fails before file installation.
Kitty coverage checks retained bindings/prior includes and deduplication.

The optional `tests/native_render.py RELEASE CONFIG DATA OUTPUT` creates only
`Gtk.OffscreenWindow` fixtures. It checks actual GTK3 generic controls and a real
file chooser widget against isolated native settings, and verifies a transparent
Aether application root. It uses synthetic chooser files. Outputs and runtime
receipts must remain outside distribution source/payload allowlists.

The 2026-11-09 integration run verified canvas `#090e18`, text `#edf4ff`, reading
font Noto Sans and overlay alpha 0. Both original theme and scoped CSS parse on
GTK3/4. Render inspection corrected inherited blue check/radio gradients and
gray sidebar/header regions without replacing native glyphs. The real GTK3 file
chooser's offscreen teardown emits GDK window assertions on this host; the same
assertions reproduce with unmodified built-in Adwaita. This fixture limitation
does not certify ordinary mapped file chooser behavior. No foreground chooser
was opened to work around it.

Existing native C++ probes were also rerun with the new isolated Qt5ct/Qt6ct
outputs and the `offscreen` Qt platform. Qt 5.15.19 and 6.11.2 returned the exact
canvas/text/selection palette and general/fixed fonts. Mouse hits changed the
synthetic spin 42→43→42; combo popup keyboard selection worked. A hidden Tk 8.6
interpreter loaded package 1.0, returning the expected field canvas, reading
Treeview font and fixed-value Spinbox font. These are bounded native controls,
not touch-target or every-application compatibility claims.
