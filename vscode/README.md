# RGLauncher: Instrument/Score Aether

A precise, composed workbench within a luminous visual family. Editor content stays quiet and readable; named work planes, aligned values, cyan selection and violet focus carry the shared language.

The extension contributes only color and file icon themes. It has no executable extension code, commands, activation events, telemetry, network access or injected workbench CSS/fonts.

## Editions

- **Aether Night:** the primary nocturnal edition. Dark blue reading planes, cyan/violet structure, warm types and distinct syntax/evidence colors.
- **Aether Opaque:** the same hierarchy with solid composed highlight surfaces. It removes theme-authored translucent background overlays rather than fading content.
- **Aether Day:** a deliberately composed bright edition with dark cyan/violet accents, readable syntax and its own light file icons.

Terminal, debugger, notebook, settings, menus, quick pick, source control/diff, lists, tabs, panels and input states receive explicit roles. Semantic tokens and TextMate scopes complement each other; language support still comes from installed language extensions.

## Use

Install the local VSIX or copy this extension directory into the editor's extension directory. Choose a color edition using **Preferences: Color Theme**, then choose **RGLauncher Aether Files** using **Preferences: File Icon Theme**. RGLauncher Linux Edition's installer can perform the local installation while preserving other user settings.

Font choices remain yours. The desktop uses JetBrains Mono for code/exact values and Noto Sans for reading, but this extension does not override font or accessibility preferences. It supports ordinary editor zoom, semantic highlighting and existing keyboard navigation.

The native VS Code theme API controls colors and file icons, not window geometry, compositor blur or arbitrary spatial transitions. This package does not patch application files or claim that a static preview proves usability/accessibility across platforms.

## Original file icon family

File/folder artwork comes from RGLauncher's original MIT Instrument/Score Aether SVG family. Language badges are original simple geometric letterforms, not copied language/company logos. Familiar file extensions, language IDs and names retain their meanings. Unknown language icons can still come from their installed language extension. Product/action codicons are left intact.

## Build and verify

```sh
python3 build.py
python3 -m unittest discover -s tests -v
```

The builder uses Python's standard library and local original SVG sources; it does not install npm dependencies or publish to a marketplace. The resulting `dist/rglauncher-aether-0.1.0.vsix` contains an explicit data-only allowlist. Preview artifacts and test fixtures are excluded.

MIT © 2026 Robert R. Green and RGLauncher: Linux Edition contributors.
