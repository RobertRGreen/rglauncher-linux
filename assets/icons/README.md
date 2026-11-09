# Original Instrument/Score Aether icon sources

MIT licensed, copyright 2026 Robert R Green and contributors; see LICENSE.
All original vector geometry is in generate.py. No upstream paths, application
logos, fonts or raster assets were imported. Conventional object/action and
protocol signs do not imply universal recognition or trademark ownership.

The family contains 89 identities and 134 compatibility aliases. A 24-unit grid,
object-shaped material planes and optical 16/24/32/48px editions preserve small
size weight without thick large-size outlines. Symbolic assets use filled
currentColor contours for native GTK compatibility. No runtime Qt dependency is
introduced by those SVGs.

Regenerate from this source checkout:

```sh
python3 assets/icons/generate.py
python3 tools/build_icons.py assets/icons/generated/registry.json share/icons
python3 assets/icons/render.py --output /path/to/private-render-artifacts
python3 assets/icons/verify.py --gtk-symbolic --output /path/to/private-verification.json
```

Generation requires a C++ compiler, pkg-config and Qt6Gui/Qt6Svg development
libraries. Rendering requires librsvg GI, Cairo, Pango/PangoCairo. GTK verification
needs a display connection but opens no window. Previews and native test receipts
are deliberately excluded from release archives. palette.json is a reproducible
source snapshot; live semantic tokens remain the application's token authority.

Keep visible labels/accessibility names, file names/extensions and the fallback
icon chain. Capability icons are not measurements of battery, volume or signal.
Names and metaphors require audience/RTL testing; no worldwide comprehension
claim follows from passing render checks.
