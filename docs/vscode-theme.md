# VS Code / Code OSS — Instrument/Score Aether

Implemented for RGLauncher: Linux Edition, 2026-11-09. MIT, Robert R. Green and contributors.

## Package and ownership

The self-contained extension is built at `vscode/dist/rglauncher-aether-0.1.0.vsix`, extension ID **`rglauncher.rglauncher-aether`**. Runtime releases carry it at `share/vscode/rglauncher-aether.vsix`. It contributes three color themes and one file icon theme. The installer owns editor installation and merges only the selected theme/icon keys into existing JSONC preferences. QA used isolated editor directories; no foreground Code window, user source document or active editor profile was opened or changed.

The package contains theme/icon JSON, original SVG assets, license and documentation. There is no `main`, browser module, activation event, command, executable extension code, extension dependency, telemetry or marketplace publication. Native workbench/product codicons are untouched. The theme follows the supported [VS Code color-theme contribution model](https://code.visualstudio.com/api/extension-guides/color-theme).

## Editions and construction

| Edition | Intended construction |
|---|---|
| **RGLauncher Aether Night** | Primary nocturnal edition. A quiet dark-blue editor plane, darker navigation frame, raised slate controls, cyan subject/selection landmarks, violet focus, warm type/constant roles and readable comments. |
| **RGLauncher Aether Opaque** | The same structure with theme-authored translucent overlays composed into solid working-plane colors. It preserves hierarchy rather than dimming content or deleting state. On the same base plane it can intentionally look like Night; its distinction is how highlight surfaces compose over varying content. |
| **RGLauncher Aether Day** | A separately composed bright edition with near-white reading planes, cool structural framing and darker cyan/violet/green/amber/red roles. It is not a simple inversion of the dark colors. |

Each edition defines **471 verified workbench roles, 20 TextMate scope groups and 29 semantic selectors**. Coverage includes editor/gutter/indent guides, active/inactive tabs, primary/secondary navigation, menus, command/quick pick, lists, inputs/options/validation, settings, notifications, terminal/ANSI, debugger, source control/diff/merge, notebook cells/output, minimap and common inline/chat surfaces. Role names were checked against installed Code OSS 1.138's public registry and built-in contributions rather than leaving plausible unknown names ignored. The [official theme-color reference](https://code.visualstudio.com/api/references/theme-color) supplies the public role semantics.

Syntax keeps ordinary code and comments readable. Functions are cyan, keywords/decorators violet, type names/constants warm, strings green and parameters/properties quieter precise variants. Definitions can receive selective emphasis. Semantic selectors complement TextMate scopes and retain fallback behavior for language support supplied by other extensions, following the [semantic highlighting model](https://code.visualstudio.com/api/language-extensions/semantic-highlight-guide). The extension does not pretend to be a language server.

Authored control edges use a stronger role than decorative separators. Focus is violet; selected objects have cyan landmarks. Disabled/secondary text stays readable. ANSI black/white retain their color meanings for terminal/TUI background usage; they are not repurposed as secondary text. No palette can make every arbitrary foreground/background pair emitted by third-party terminal programs readable.

The native theme API cannot alter layout geometry, add compositor blur or install arbitrary spatial morphs. This package expresses the shared language through named work planes, hierarchy and roles within the editor's native construction. It does not inject CSS or fonts into application files. Font choices, motion preferences, accessibility settings and existing editor shortcuts remain user-controlled.

## Original file icon theme

**RGLauncher Aether Files** uses the original MIT Aether SVG family, optical16 dark and light editions, with provenance hashes. Sixty self-contained SVG assets cover file/folder states, code languages, settings, audio/media/table/archive/package types and named folder groups. Python, JavaScript, TypeScript, Rust, Go, C/C++, C#, shell, JSON, HTML, CSS, Markdown and YAML have original geometric letter/mark badges on the common document construction. These are not copied language/company logos or font glyphs.

File extensions, names and language IDs map to meaningful icons. Unknown languages can retain icons supplied by their language extensions; explorer disclosure arrows stay visible. The icon data follows the [file icon contribution model](https://code.visualstudio.com/api/extension-guides/file-icon-theme). No icon font or codicon replacement is bundled. Original source notices and the project MIT license are included.

## Verification

Run from `vscode/`:

```sh
python3 build.py
python3 -m unittest discover -s tests -v
```

The builder uses the standard library and local original assets from `assets/icons`. A standalone checkout can also rebuild using the bundled original SVG copies; it needs no private home tree or npm/network dependencies. That standalone rebuild produces a byte-identical VSIX.

Ten regression tests passed:

- Contribution paths, data-only manifest and expected role coverage.
- Supported public color IDs and hex format.
- Defined informative reading/selection/control pairs.
- All syntax and semantic foregrounds against their editor plane.
- Separate focus/selection and authored input boundaries.
- Opaque background handling and terminal black/white meanings.
- Every SVG reference, original-asset hash, dark/light association, no scripts/foreign objects/text/font injection.
- VSIX CRC, XML metadata, explicit archive allowlist, no traversal/private paths/executable code and deterministic output.
- Standalone reproducibility without the native icon source directory.

Selected token calculations in sRGB:

| Edition | Minimum syntax contrast | Minimum semantic contrast | Input boundary / input plane | Focus / input plane |
|---|---:|---:|---:|---:|
| Night | 8.50:1 | 8.65:1 | 4.10:1 | 8.13:1 |
| Opaque | 8.50:1 | 8.65:1 | 4.10:1 | 8.13:1 |
| Day | 6.14:1 | 6.14:1 | 4.17:1 | 6.68:1 |

These are defined token-pair calculations, not a claim that every composed pixel, extension view, display profile or arbitrary ANSI pair passes an accessibility audit. A local development build writes `vscode/validation-report.json`; runtime releases exclude development receipts.

Installed Code OSS 1.138 accepted the local VSIX through its actual CLI in isolated data/extension directories. Listing those directories returned `rglauncher.rglauncher-aether@0.1.0`. This validates archive recognition/installation; live editor theme activation was not screenshot-tested in this bounded headless run.

## Visual review artifacts and limits

Development Night, Opaque, Day and icon specimens were rendered using an isolated, network-disabled headless Chromium profile and visually inspected. The three workbench specimens show Python code, file identities, selection/focus, terminal, diff, notebook, settings and an exception. The icon sheet checks native16/24/32 pixel presentation in both editions. All images are generated from actual theme/icon data; these optional review artifacts are excluded from runtime and curated source payloads.

They are explicitly labeled **static specimens**, not screenshots of a running editor. No claim is made about complete language-provider behavior, native accessibility-tree operation, international reading or worldwide superiority. Those require appropriate later live/user testing. Development artifacts, source tests and previews are excluded from the VSIX.

## Integration and recovery

The installer installs the VSIX (or extracts its explicit `extension/` payload), then selects **RGLauncher Aether Night** and **`rglauncher-aether-files`** while preserving unrelated JSONC settings. Do not install the development folder wholesale as a replacement editor profile. No user font, keybinding, trust or extension preference needs to change for this theme.

The VSIX has no privileged installer or updater. RGLauncher's versioned package/update/recovery flow controls deployment; this document does not assert a public feed or a marketplace release. Removing the extension and restoring the prior two theme-selection keys returns the editor to its earlier presentation without touching source files.
