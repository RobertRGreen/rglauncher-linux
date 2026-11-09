# Installation and release boundaries

The initial tested target is Arch Linux x86_64 with Hyprland 0.56.2 and Waybar
0.15.0. Other Linux distributions need a native Waybar build against their own
libraries and an adapter test pass. This alpha does not claim binary portability
to every Linux distribution, or install the compositor/OS itself.

Install the dependencies listed in [software.md](software.md) through your
distribution. The optional [Arch recipe](../packaging/arch/PKGBUILD) describes
those dependencies and packages a verified runtime archive. It enables no system
services and changes no user configuration during a package-manager transaction.

The [GitHub release](https://github.com/RobertRGreen/rglauncher-linux/releases/tag/v0.2.0-alpha.4)
contains the runtime archive, matching source archive, signed manifest and hashes.
The public key is `share/update-keys/rglauncher-2026.pub`; its SHA-256 over the PEM
file is `20507e6951b03677b115f657aa681cf299751b36d61dfd3fc61d6f3e5ed1521d`.
The fingerprint printed here is useful for comparison; obtaining both software
and key from the same compromised account would not independently establish trust.

To build from the public source, first clone the upstream Waybar repository and
run `python3 packaging/waybar/build.py --source /path/to/Waybar --output /new/build`.
The helper checks its pinned revision and applies the two included patches.
Copy its verified `waybar` and generated `backend.json` into `share/waybar/`.
The metadata records platform, architecture and SHA-256. The backend metadata in the
runtime archive records the tested build. Build icons with `tools/build_icons.py`
and the editor extension with `vscode/build.py` as described in their docs. The
original vector sources and data-only editor source are included.

The installer verifies the signed feed, manifest, complete archive inventory and
local dependencies before selecting an immutable release. It creates per-user
wrappers, desktop entries, icon links, native appearance adapters and systemd
units, with backups and receipts. Existing Waybar configuration and compositor
bindings are preserved. A new installation receives the generic Waybar defaults;
the full portable Hyprland example is explicitly opt-in. Desktop launchers do not
copy private network identities, audio profiles, signing keys or machine services.

Use the README's `install` command to select the pinned prerelease channel.
`rglauncher doctor --json` reports native backend/platform/library availability.
`rglauncher settings` opens the Control Room. `rglauncher editor install` installs
the data-only VS Code extension and changes only its color/icon preferences;
`--variant opaque` and `--variant day` select the alternatives.

Automatic updates verify and select new code; already running applications keep
their pinned release. The shelf uses new code on its next start. Use
`rglauncher desktop refresh` to apply native adapters and refresh only the current
session's shelf immediately. Interactive update/rollback commands also refresh
the current Hyprland session after a successful selection. Updates never run a
system package-manager upgrade, restart Hyprland or overwrite personal documents.

`rglauncher update rollback` verifies the retained previous release and holds
automatic reapplication of that version until a newer fix arrives or the user
explicitly reapplies it. The first installation has no previous software release;
installer/native/editor receipts preserve its prior configuration. Guarded
`restore_owned` in the installer restores its owned links/files when unchanged;
it deliberately reports native preferences/services as separate recovery steps.
Read their receipts before reverting; user edits after installation are conflicts,
not expendable files. A complete one-command uninstall is not part of this alpha.
