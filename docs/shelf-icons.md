# Shelf object illustrations

The shelf has eight original Instrument/Score Aether object identities, authored
for dominant **40–48px** launch targets. They extend the established semantic
family without redrawing its 89 utility glyphs. Their actual object silhouette
supplies the volume: no generic rounded tile wraps every identity.

All geometry and generation code are original project work, MIT licensed under
the repository LICENSE, copyright Robert R Green and contributors. No upstream
icon paths, fonts, logos, bitmap textures or application-brand artwork were
copied. Terminal and code identities remain generic objects; they do not replace
known application brands in application lists.

## Exact integration paths

The default assets have transparent backgrounds and dark-shelf material planes:

| File under assets/shelf-icons/ | Identity and visual mechanism |
| --- | --- |
| aether-library.svg | Four separate library objects, each with a front plane, lower face and short specular edge |
| aether-folder.svg | Folder tab/back, overlapping inset papers, opaque folded front and lower lip |
| aether-development.svg | A terminal object with a recessed screen and geometric prompt; no letter/font dependency |
| aether-window.svg | Two overlapping windows with a title rail and sparse inset regions |
| aether-document-code.svg | Folded code page, physical side thickness and inset geometric code marks |
| aether-calculator.svg | Calculator body, recessed display and individually raised keys |
| aether-audio-console.svg | A sloped mixing surface with separate recessed tracks and slider caps |
| aether-home.svg | Pitched roof/eave, front and side planes and recessed doorway |

Each also has an `aether-NAME-light.svg` edition for bright surfaces, with the same
geometry and darker teal/violet identifying rims. These are **eight identities,
16 SVG files**, not 16 different actions. Root's shelf adapter chooses the source
paths; the asset generator does not install, theme or launch the shelf.

The terminal adapts the broader development identity to this specific launcher
role. Audio fader positions are an illustration of the console object, never a
readout of physical device levels. The calculator display contains no fabricated
answer. Home is a generic destination, not a new HCP brand mark. Labels/tooltips
and accessible names remain necessary; SVG titles alone do not prove native
screen-reader behavior or universal recognition.

## Material and optical construction

The source uses a 64-unit box, keeping visible geometry inside its edges. Opaque
front planes supply mass against the shelf; bounded cyan/violet rims, separate
rear/side faces, inset dark regions and small highlights supply depth. Glass is
represented through layered planes and restrained gradients rather than making
the whole object faint. No SVG blur/filter, unbounded glow, animation or shadow
image is required. The interior detail is sparse enough to remain legible at the
intended size; the original utility family remains the right source for tiny
status controls.

The first native sheets showed an overbright purple home side face. The side
material was darkened independently of its identifying rim so the house no
longer dominates the row. Dark and bright editions were rerendered and inspected.
The eight objects retain different silhouettes and shared light direction rather
than eight copies of the same container.

These assets are intended for native file-based SVG loaders, which isolate each
document's gradient IDs. Inline HTML must scope IDs per instance. Do not stretch
their aspect ratio or add a second blurred glow behind every object. Match host
target/hover/focus state to interaction; the asset itself does not fake an active
application, connected device or selection.

## Rebuild and native review

```sh
python3 -B tools/build_shelf_icons.py
python3 -B tools/build_shelf_icons.py --render /path/to/private-shelf-review
```

Generation uses Python's standard library and the repository's semantic token
file. The bright material interpretation is explicitly authored in the generator.
The optional render path requires librsvg GI, Cairo and Pango/PangoCairo. Fonts
are used only by the native contact-sheet labels; no font is embedded in SVGs.

The native review renders every identity/edition at **40, 48 and 64px**: 48 raster
cases and six actual-size contact sheets. It records output hashes, ink/opaque
pixel counts and boundary pixels in render-report.json. The current pass has no
ink touching a raster boundary and all objects retain opaque body pixels. SVG
structure checks found only local vector paths/rectangles/gradients/title data,
with no external references, fonts or bitmap resources. Deterministic generation
was checked against all 16 outputs.

The contact sheets and individual rasters are review artifacts, not private
desktop screenshots. They establish native rendering and size behavior; they do
not certify final shelf spacing, compositor effects, every DPI or audience
recognition. Inspect the integrated shelf separately and retain smaller utility
icons for supporting controls.
