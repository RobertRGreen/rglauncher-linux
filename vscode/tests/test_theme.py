import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import build
import file_icons
import vsix


def rgba(value):
    result = [int(value[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return (*result, int(value[7:9], 16) / 255 if len(value) == 9 else 1)


def contrast(a, b):
    def luminance(c):
        linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgba(c)[:3]]
        return sum(v * w for v, w in zip(linear, (.2126, .7152, .0722)))
    low, high = sorted((luminance(a), luminance(b)))
    return (high + .05) / (low + .05)


class ThemeTests(unittest.TestCase):
    def setUp(self):
        self.package = json.loads((ROOT / "package.json").read_text())
        self.themes = {edition: json.loads((ROOT / "themes" / ("aether-" + edition + ".json")).read_text())
                       for edition in ("night", "opaque", "day")}

    def test_data_only_contributions(self):
        self.assertEqual(set(self.package["contributes"]), {"themes", "iconThemes"})
        self.assertEqual(len(self.package["contributes"]["themes"]), 3)
        for forbidden in ("main", "browser", "activationEvents", "scripts", "extensionDependencies", "extensionPack"):
            self.assertNotIn(forbidden, self.package)
        for contribution in self.package["contributes"]["themes"] + self.package["contributes"]["iconThemes"]:
            path = (ROOT / contribution["path"]).resolve()
            self.assertTrue(path.is_relative_to(ROOT) and path.is_file())

    def test_supported_workbench_roles_and_formats(self):
        known = set(json.loads((ROOT / "tests/registered-color-ids.json").read_text())["ids"])
        for edition, theme in self.themes.items():
            self.assertGreaterEqual(len(theme["colors"]), 450)
            self.assertFalse(set(theme["colors"]) - known)
            for key, color in theme["colors"].items():
                self.assertRegex(color, r"^#[0-9a-f]{6}(?:[0-9a-f]{2})?$", (edition, key))
            for prefix in ("terminal.", "debug", "diffEditor", "notebook.", "settings.", "menu.", "panel", "tab.", "editor."):
                self.assertGreaterEqual(sum(key.startswith(prefix) for key in theme["colors"]), 3, prefix)

    def test_reading_pairs(self):
        pairs = [
            ("editor.foreground", "editor.background"), ("sideBar.foreground", "sideBar.background"),
            ("input.foreground", "input.background"), ("input.placeholderForeground", "input.background"),
            ("dropdown.foreground", "dropdown.background"), ("descriptionForeground", "editor.background"),
            ("list.activeSelectionForeground", "list.activeSelectionBackground"),
            ("quickInputList.focusForeground", "quickInputList.focusBackground"),
            ("menu.selectionForeground", "menu.selectionBackground"), ("terminal.foreground", "terminal.background"),
            ("statusBar.foreground", "statusBar.background"), ("statusBarItem.warningForeground", "statusBarItem.warningBackground"),
            ("statusBarItem.errorForeground", "statusBarItem.errorBackground"), ("button.foreground", "button.background"),
            ("button.secondaryForeground", "button.secondaryBackground"), ("tab.inactiveForeground", "tab.inactiveBackground"),
        ]
        for edition, theme in self.themes.items():
            for fg, bg in pairs:
                self.assertGreaterEqual(contrast(theme["colors"][fg], theme["colors"][bg]), 4.5, (edition, fg, bg))

    def test_syntax_and_semantic_readability(self):
        for edition, theme in self.themes.items():
            bg = theme["colors"]["editor.background"]
            self.assertTrue(theme["semanticHighlighting"])
            self.assertGreaterEqual(len(theme["tokenColors"]), 18)
            self.assertGreaterEqual(len(theme["semanticTokenColors"]), 25)
            for rule in theme["tokenColors"]:
                self.assertGreaterEqual(contrast(rule["settings"]["foreground"], bg), 4.5, (edition, rule["name"]))
            for selector, value in theme["semanticTokenColors"].items():
                foreground = value if isinstance(value, str) else value.get("foreground")
                self.assertGreaterEqual(contrast(foreground, bg), 4.5, (edition, selector))
                self.assertEqual(len(foreground), 7)

    def test_focus_and_control_bounds(self):
        for edition, theme in self.themes.items():
            c = theme["colors"]
            self.assertNotEqual(c["focusBorder"], c["list.activeSelectionIconForeground"])
            for key in ("focusBorder", "input.border", "dropdown.border", "button.secondaryBorder"):
                for background in ("input.background", "editor.background", "dropdown.background"):
                    self.assertGreaterEqual(contrast(c[key], c[background]), 3, (edition, key, background))

    def test_opaque_edition_and_ansi_roles(self):
        opaque = self.themes["opaque"]
        for name, color in opaque["colors"].items():
            if name.lower().endswith(("background", "shadow", "fill")):
                self.assertEqual(len(color), 7, name)
        for edition, theme in self.themes.items():
            self.assertEqual(theme["colors"]["terminal.ansiBlack"], "#090e18")
            self.assertEqual(theme["colors"]["terminal.ansiWhite"], "#edf4ff")

    def test_original_icons_are_self_contained(self):
        theme = json.loads((ROOT / "icons/aether-file-icons.json").read_text())
        self.assertNotIn("fonts", theme)
        self.assertFalse(theme["hidesExplorerArrows"])
        self.assertTrue(theme["showLanguageModeIcons"])
        definitions = theme["iconDefinitions"]
        for icon, definition in definitions.items():
            self.assertEqual(set(definition), {"iconPath"})
            path = (ROOT / "icons" / definition["iconPath"]).resolve()
            self.assertTrue(path.is_relative_to(ROOT / "icons") and path.is_file())
            svg = ET.fromstring(path.read_text())
            self.assertTrue(svg.tag.endswith("svg"))
            self.assertEqual(svg.get("viewBox"), "0 0 24 24")
            for child in svg.iter():
                self.assertFalse(child.tag.endswith(("script", "foreignObject", "image", "text")))
                for key, value in child.attrib.items():
                    if key.endswith("href"):
                        self.assertTrue(value.startswith("#"))
        for variant in (theme, theme["light"]):
            for field in ("file", "folder", "folderExpanded", "rootFolder", "rootFolderExpanded"):
                self.assertIn(variant[field], definitions)
            for mapping in ("fileExtensions", "fileNames", "languageIds", "folderNames", "folderNamesExpanded"):
                for ref in variant[mapping].values():
                    self.assertIn(ref, definitions)
        self.assertNotEqual(theme["languageIds"]["python"], theme["languageIds"]["typescript"])
        self.assertNotEqual(theme["fileExtensions"]["wav"], theme["fileExtensions"]["png"])
        provenance = json.loads((ROOT / "icons/provenance.json").read_text())
        self.assertEqual(provenance["license"], "MIT")
        for asset in provenance["assets"]:
            path = ROOT / "icons" / asset["destination"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), asset["sha256"])

    def test_vsix_metadata_and_allowlist(self):
        path = ROOT / "dist" / (self.package["name"] + "-" + self.package["version"] + ".vsix")
        with zipfile.ZipFile(path) as archive:
            self.assertIsNone(archive.testzip())
            names = archive.namelist()
            self.assertIn("extension.vsixmanifest", names)
            self.assertIn("[Content_Types].xml", names)
            self.assertIn("extension/LICENSE", names)
            for name in names:
                self.assertFalse(name.startswith("/") or ".." in Path(name).parts)
                self.assertFalse(any(part in ("__pycache__", "previews", "tests", "dist", "node_modules") for part in Path(name).parts))
                self.assertNotIn(Path(name).suffix, (".py", ".js", ".ts", ".sh", ".woff", ".ttf"))
                self.assertNotIn(b"/home/robert", archive.read(name))
            manifest = ET.fromstring(archive.read("extension.vsixmanifest"))
            namespace = {"v": "http://schemas.microsoft.com/developer/vsx-schema/2011"}
            identity = manifest.find("v:Metadata/v:Identity", namespace)
            self.assertEqual(identity.get("Id"), self.package["name"])
            self.assertEqual(identity.get("Version"), self.package["version"])
            self.assertEqual(identity.get("Publisher"), self.package["publisher"])
            for asset in manifest.findall("v:Assets/v:Asset", namespace):
                self.assertIn(asset.get("Path"), names)

    def test_deterministic_vsix(self):
        first = vsix.build_vsix(ROOT).read_bytes()
        second = vsix.build_vsix(ROOT).read_bytes()
        self.assertEqual(first, second)

    def test_standalone_rebuild_without_native_source_tree(self):
        expected = (ROOT / "dist" / (self.package["name"] + "-" + self.package["version"] + ".vsix")).read_bytes()
        with tempfile.TemporaryDirectory(prefix="aether-standalone-test-") as temporary:
            project = Path(temporary) / "project"
            project.mkdir()
            shutil.copy2(ROOT.parent / "LICENSE", project / "LICENSE")
            target = project / "vscode"
            shutil.copytree(ROOT, target, ignore=shutil.ignore_patterns("previews", "dist", "__pycache__"))
            subprocess.run([sys.executable, str(target / "build.py"), "--icons-source", str(Path(temporary) / "absent")],
                           capture_output=True, text=True, check=True)
            actual = (target / "dist" / (self.package["name"] + "-" + self.package["version"] + ".vsix")).read_bytes()
            self.assertEqual(expected, actual)


if __name__ == "__main__":
    unittest.main()
