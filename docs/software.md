# Software, dependencies and licensing

RGLauncher is a desktop shell assembled from original source and existing system
software. It does not replace Hyprland's compositor, Waybar's module system,
Thunar's file operations or PipeWire's audio engine. Original project code and
icons are MIT. External dependencies retain their upstream licenses; installing
an adapter does not relicense the application it styles.

## Included and integrated applications

| Surface | Implementation and boundary |
| --- | --- |
| Apps / Windows | Original GTK3 layer-shell score, GLib desktop entries, Hyprland window facts and focus selection |
| Shelf | Original edge controller plus pinned Waybar modules; native tray popups use the documented bridge |
| Calculator | Original bounded expression evaluator and optional Wayland clipboard copy |
| Audio Console | Original GTK3 interface using PipeWire's PulseAudio compatibility tools, routing/bus helpers and NumPy FFT display |
| Network | Original GTK3 interface to NetworkManager's D-Bus API; secondary camera-radio adapter is unconfigured in generic builds |
| Bluetooth | Original GTK3 BlueZ D-Bus interface; no shell dependency on bluetoothctl |
| Files | Thunar, launched through the public command surface |
| Terminal | Kitty, launched through the public command surface |
| Settings / Updates | Original project interface and signed per-user update client |
| Native appearance | Original GTK2/3/4, Qt5/6/KDE/Quick and Tk preferences from semantic roles; GTK imports its own installed built-in resource |
| Code editor | Optional data-only VS Code/Code-OSS color/file-icon extension; no executable extension code or marketplace publication |

Audio routing and physical controls perform real actions when the user invokes
them. Hardware-specific Scarlett controls are optional and depend on a supported
ALSA device/driver. A shell theme cannot manufacture an unavailable device,
permission agent or service. Spectrum monitoring uses `parec`; hardware control
uses `amixer`; runtime sample-rate settings use `pw-metadata`. Opening/rendering
synthetic QA fixtures does not invoke those backends.

## Distribution dependencies

Arch package names below are a packaging reference, not an instruction to install
packages or start services automatically.

| Capability | Packages / services |
| --- | --- |
| Core shell | `hyprland` 0.56 Lua API, `waybar`, Python ≥3.12, `python-cryptography` ≥41 |
| Native GTK surfaces | `gtk3`, `gtk4`, `gtk-layer-shell`, `python-gobject`, `python-cairo`, `python-dbus` |
| Files / terminal | `thunar`, `kitty` |
| Audio / spectrum | `pipewire`, `pipewire-pulse`, `wireplumber`, `libpulse`, `python-numpy`; optional `alsa-utils` for hardware mixer controls |
| Network / Bluetooth | `networkmanager`, `bluez`; the appropriate system service must already be configured |
| Privileged connection prompts | `polkit` plus a functioning session authentication agent, such as `hyprpolkitagent` |
| Fonts / icon fallback | `noto-fonts`, `ttf-jetbrains-mono-nerd`, and a system icon fallback; original Aether icons are included |
| Qt native integration | Optional `qt5ct`, `qt6ct` and their toolkit libraries/plugins |
| Tk native integration | Optional `tk`; uses original ttk theme plus standard X11 resource preferences |
| Clipboard | Optional `wl-clipboard` (`wl-copy`) |
| Desktop portals | Recommended `xdg-desktop-portal-hyprland` and a file-chooser backend appropriate to the user's session |
| Editor / optional preview | Code-OSS/VS Code for themes; `ffmpeg` only for an explicitly configured secondary video preview |

The captured shipped Python sources import NumPy, GI, Cairo and D-Bus.
They do **not** import PyQt6 or SciPy; `python-pyqt6`/`python-scipy` are therefore
not required dependencies of this build. Native Qt theme configuration does not
make a GTK application a PyQt application. Recheck actual imports when adding a
new implementation. Fonts and external applications are dependencies, not copied
into the original asset package.

The patched Waybar backend is dynamically linked and must be built for the
target distribution/architecture; an x86_64 archive is not a universal Linux
binary. Its dependency/provenance record belongs with its release. The stock
Waybar package satisfies ordinary runtime libraries, but does not by itself
establish compatibility with Hyprland's Lua workspace dispatch or the native
tray popup bridge. See [the exact backend recipe](../packaging/waybar/README.md).

The local [Arch recipe](../packaging/arch/PKGBUILD) consumes the builder's flat
`rglauncher-linux-0.2.0-alpha.1-linux-x86_64.tar.gz`. Place that target-Arch artifact
beside PKGBUILD and provide its verified digest as `RGL_SOURCE_SHA256` when
running makepkg. The recipe deliberately has no invented public download URL or
unchecked `SKIP` digest. It installs software and desktop/icon assets, with no
post-install service enablement, user configuration replacement or session
selection. Its command wrapper selects a managed per-user current release when
present, otherwise the packaged `/usr/lib/rglauncher-linux` release. A distributor
must publish the actual digest and compatible dependency/build provenance.

## Local license evidence

The following identifiers were checked against this Arch host's installed
`pacman -Qi` metadata on 2026-11-09, with installed license texts where provided.
They describe the packages inspected, not a legal audit of every transitive file.
Distributors must retain the matching notices/source obligations of what they
actually redistribute; using a system dependency is different from shipping it.

| Software | Installed package license declaration |
| --- | --- |
| Hyprland | BSD-3-Clause; installed `/usr/share/licenses/hyprland/LICENSE` |
| Waybar and local patches | MIT; upstream text retained in `packaging/waybar/LICENSE.Waybar` |
| Thunar | GPL-2.0-or-later and LGPL-2.1-only |
| Kitty | GPL-3.0-only |
| NetworkManager | LGPL-2.1-or-later and GPL-2.0-or-later |
| PipeWire / pipewire-pulse | MIT and LGPL-2.1-or-later / MIT respectively |
| WirePlumber | MIT |
| GTK3 / GTK4 / PyGObject | LGPL-2.1-or-later |
| gtk-layer-shell | LGPL-3.0-or-later |
| Pycairo | Package metadata `LGPL2.1`, `MPL`; retain the supplied dual-license notices |
| dbus-python | MIT |
| Python cryptography | Apache-2.0 and BSD-3-Clause |
| NumPy | Package metadata `custom`; retain its bundled license/notices rather than reducing all components to one identifier |
| BlueZ / libpulse / ALSA utilities | GPL-2.0-only / LGPL-2.1-or-later / GPL-2.0-or-later |
| qt5ct / qt6ct | BSD-3-Clause / BSD-2-Clause |
| Noto / JetBrains Mono Nerd fonts | OFL-1.1-no-RFN in the inspected packages; fonts are not bundled by this project |

The original icon family contains original vector paths and project MIT notices;
it does not copy third-party app logos or Nerd Font outlines. File-type badges
describe the document type without impersonating an application's identity.
The full source/payload allowlists must exclude profiles, recordings, network
identifiers, credentials, update signing keys and runtime receipts.
