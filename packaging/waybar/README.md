# Pinned native Waybar backend

RGLauncher uses Waybar's existing modules and application-owned tray menus. This
directory contains two narrow MIT patches against Waybar **0.15.0**, upstream
revision `90b209add8937514d0a987aa842e701bd8f1232e` from
<https://github.com/Alexays/Waybar>.

- `0001-hyprland-lua-workspace.patch`: preserves the existing opt-in Lua workspace
  dispatch compatibility (`WAYBAR_HYPRLAND_LUA=1`). Special/move-to-monitor behavior
  remains upstream behavior.
- `0002-native-tray-popup-shelf.patch`: hooks the local `DbusmenuGtkMenu` created by
  `src/modules/sni/item.cpp::makeMenu()`. The new helper reports actual native GTK
  map/unmap/destroy lifetimes so a controller can retain the corresponding shelf.
- `shelf_popup.hpp`: readable exact helper used by the second patch and fixtures.
  The build rejects divergence between this file and the applied patch.
- `LICENSE.Waybar`: upstream MIT text, preserved verbatim from the installed
  Waybar license. The original local additions are MIT, copyright 2026 Robert R
  Green and contributors, consistent with this project's LICENSE.

## Build without installation

Provide a local Git clone containing the pinned upstream revision and installed
development dependencies. This script exports committed source with `git archive`;
uncommitted changes in the input repository are never copied. It applies the two
patches, builds with **two jobs**, copies the resulting binary into the new output
directory and records its SHA-256, revision and patch hashes. It never starts the
bar, replaces a live binary, restarts the compositor or installs dependencies.

```sh
python3 packaging/waybar/build.py --source /path/to/Waybar.git \
  --output /path/to/new-private-build --meson meson
```

The output directory must be new. The recipe pins source/patches and a stable
`SOURCE_DATE_EPOCH`, disables wrap downloads and enables native tray support.
Meson/Ninja, a C++20 compiler and upstream Waybar development libraries must
already be installed. Selected optional dependencies remain `auto`, matching the
existing local backend; record `build/meson-info/intro-dependencies.json` when
comparing environments. This is a reproducible source recipe, **not** an assertion
that arbitrary compiler/library versions produce bit-identical binaries.

## Controller protocol

The bridge is inactive unless **both** environment variables exist:

```text
RGL_SHELF_SOCKET=/absolute/path/to/controller.sock
RGL_SHELF_OUTPUT=DP-1
```

Each event opens one AF_UNIX stream connection, connects and sends without
blocking, then closes without reading a response. It sends a bounded UTF-8 JSON
object with a newline terminator:

```json
{"command":"popup-open","output":"DP-1","menu":"12345-1"}
```

The corresponding close uses `"command":"popup-close"`. IDs contain only the
process ID and a monotonic local counter, never a widget pointer or application
identity. Each tracked menu retains its own ID through repeated mappings. UTF-8
is validated, JSON quote/backslash/control characters are escaped, output names
are limited to 128 bytes and menu IDs to 64. Total payload is under 1536 bytes;
socket paths must fit `sockaddr_un`. Transport uses `SOCK_NONBLOCK`, `SOCK_CLOEXEC`,
`MSG_DONTWAIT` and `MSG_NOSIGNAL`, with no shell commands, D-Bus inspection, reply
wait or global event monitoring.

The receiver must authenticate `SO_PEERCRED.pid` against its exact current
Waybar child for that output, validate fields and enforce limits. Maintain a set
of open IDs **per output**, so closing one nested menu does not clear another.
Duplicate opens/closes are idempotent. Clear all IDs on child death/replacement,
manager reload and shutdown. The expected capability marker in the binary is
`RGL_SHELF_SOCKET`.

The helper tracks existing and dynamically assigned submenus through
`notify::submenu`, `GtkMenuShell::insert`, container add and map-time discovery.
Map/unmap/destroy produce balanced state transitions; duplicate registration and
repeated unmap/destroy do not produce extra closes. Hooks are widget-owned and do
not capture a tray Item pointer after destruction.

**Limits:** notifications are best effort if the controller is absent, its queue
is full or a write cannot complete immediately. They never stall GTK. The
receiver must retain a user-accessible hide/reset path and clear state when its
child exits. This does not observe a remote application's `ContextMenu` fallback
when no local DbusmenuGtkMenu exists, application-owned non-GTK popups, tooltips
or every future Waybar menu implementation. Those are distinct integration
cases; this patch does not claim universal popup coverage.

## Tests without the active display

```sh
python3 packaging/waybar/tests/test_bridge.py --artifacts /path/to/private-tests \
  --broadway
```

The fixture compiles this exact helper, checks JSON escaping/Unicode/bounds,
records real Unix peer credentials, checks missing/full listener queues return
promptly, and maps GTK menus in its **own localhost-only Broadway backend**. It
does not connect to the active desktop or manipulate the pointer. Three menu
lifecycles cover root, nested, dynamically inserted/assigned submenu, duplicate
registration and active destruction. The headless Broadway viewport may emit GTK
allocation warnings; this test verifies signals/protocol, not native menu pixel
layout. See the artifacts' GTK stderr and JSON event record.

Actual compositor tray interaction and authenticated controller integration are
separate tests. Do not claim them from the isolated fixture alone.
