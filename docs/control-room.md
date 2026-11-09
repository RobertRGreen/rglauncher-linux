# Control Room

The Control Room is an Instrument/Score Aether workbench, with software inspection
beside the instruments it supports. It uses opaque reading planes and original
material depth. A stronger application-launch surface and a quieter release
inspector replace two equal generic cards. Applications is the primary launch
action; Files, Terminal, Windows, Calculator and Audio Console retain distinct
identities, purposes and accessible button names.

The main application and home identities use original 40px hero SVGs; supporting
instruments use 32px editions of the same object family. Their source/runtime
location is `assets/shelf-icons`. Native theme icons provide the fallback.
Labels remain readable text rather than glyphs embedded in a private font.
Noto Sans handles reading; named heading/exact-value roles use JetBrains Mono.
Semantic fonts/colors still come from the shared role adapter.

Shortcuts shown for applications/files/terminal/windows match the supplied opt-in
session. Calculator and Audio Console show **Enter**, meaning native activation
while that button has focus; the tooltip and accessible name make that scope
explicit. The window retains Escape-to-close and the existing public
`main(window_class=..., run_loop=...)` API.

## Related software inspection

Selected release, retained recovery release, channel and feed host come from the
actual update command's JSON, not the version string of the running UI process.
The footer separately names the running software version. A read-only expandable
publisher section contains the configured feed address, full selectable pinned
publisher SHA-256 fingerprint, last-check time in UTC, automatic retry hold and
highest installed version. File feeds are labeled local; no host is fetched just
to display its name. Unknown/unavailable values remain explicit.

Checks, installation, rollback and desktop refresh run through the existing CLI
in background workers. Controls prevent overlapping update requests. GTK updates
return through its main loop; closing the room protects against stale UI callbacks.
Successful checks never claim installation. No-op/rollback-hold results never
claim a release change. If software selected a new release but its surface
refresh failed, the UI retains the new version and describes the remaining
problem rather than hiding the completed software selection behind a generic
failure. Error details remain text, never markup or executable content.

Automatic updates retain the existing explicit preference semantics: enabling
starts the user timer, then writes the preference; disabling writes the preference
the timer command also checks. This UI does not silently change channels,
publisher keys or service policy. Existing application launch and update commands
remain unchanged.

## Responsive native verification

The workbench stacks above the inspector at compact widths and when the reading
font needs more room. The breakpoint uses actual Pango line metrics. Typography
uses relative sizing rather than fixed pixel text. Normal vertical scrolling
keeps the expanded trust details and footer reachable. Pane top alignment avoids
stretching the workbench into a large empty slab when the inspector expands.

Five actual GTK3 offscreen compositions were rendered and inspected: 900px wide,
600px compact, 900px with the reading font increased from 10pt to 12pt, expanded
trust details, and a partial-refresh error. The compact pane allocation was 552px
inside a 600px window; at 120% font size, a 900px window stacks into 852px panes.
All five had zero missing Pango glyphs and no horizontal growth beyond the
requested viewport. Compact/larger-font compositions require vertical scrolling;
the implementation does not shrink the user's font to preserve a composition.

Three concrete render findings were corrected:

1. Changing orientation inside GTK's allocation callback left compact text in the
   previous narrow columns. Reflow now runs on idle and requests a fresh layout.
2. The initial two-line masthead consumed useful instrument space. A compact
   single-line Control Room title now leaves the hierarchy to the workbench.
3. Expanded trust details stretched both panes to the same height. Top-aligned
   unequal panes retain the workbench's useful shape while details expand.

`main(..., run_loop=False)` is explicitly an isolated preview. Its synthetic
release/domain/fingerprint are labeled as examples. Every launch/update/refresh
and automatic-preference handler is guarded; previews never start commands or
write preferences. Six focused regression tests cover truthful result feedback,
local/HTTPS/malformed feed identity, and an actual offscreen preview with all
external process calls replaced by failure spies. This is bounded native QA,
not a claim about every platform, international reading or hardware operation.

The related shelf Tools chooser was also rendered offscreen from a synthetic
pure command model, with no activation. Visual review caught title/icon tuple
ordering before release; the owner corrected it while retaining exact payload
strings. The final seven-item fixture presents instrument names and native icons,
preserves its alternate-action string and reports no activation.
