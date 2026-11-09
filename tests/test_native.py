"""Portable native preparation, preservation and rollback contract tests."""
import copy
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from rglauncher_linux import native


TOKENS = {"color": {
    "canvas": "#090e18", "surface": "#131c2d", "raised": "#1c2940",
    "text": "#edf4ff", "secondary": "#a3b3c9", "boundary": "#33445f",
    "control_boundary": "#667e9f", "focus": "#bba6ff", "selection": "#73e4f2",
    "accent": "#bba6ff", "success": "#78deb0", "warning": "#f2c77d", "danger": "#ff8f9f"},
    "font": {"reading": "Noto Sans", "heading": "JetBrainsMono Nerd Font", "value": "JetBrainsMono Nerd Font"}}


def fixture_release(root):
    roles = root / "share/instrument-score-aether/tokens.json"
    roles.parent.mkdir(parents=True)
    roles.write_text(json.dumps(TOKENS))
    (root / "bin").mkdir()
    # This release fixture deliberately reads only its isolated XDG_CONFIG_HOME.
    (root / "bin/_cyber_theme.py").write_text('''import json,os
from pathlib import Path
tokens=json.loads((Path(os.environ["XDG_CONFIG_HOME"])/"instrument-score-aether/tokens.json").read_text())
def qt_palette(): return "[ColorScheme]\\nactive_colors="+tokens["color"]["text"]+"\\n"
''')
    (root / "bin/_cyber_gtk.py").write_text('''from _cyber_theme import tokens
def build_css(): return "window.aether-root { background-color: transparent; color: "+tokens["color"]["text"]+"; }"
def build_css4(): return build_css()
''')
    (root / "bin/_aether_material.py").write_text("# Pure fixture dependency\n")
    (root / "bin/_aether_desktop.py").write_text('''from _cyber_theme import tokens
def kitty_conf(): return "background "+tokens["color"]["canvas"]+"\\nforeground "+tokens["color"]["text"]+"\\n"
''')


class NativeTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="rglauncher-native-test-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.release, self.config, self.data = (self.base / name for name in ("release", "config", "data"))
        fixture_release(self.release)
        self.probe = patch.object(native, "_gtk_probe", return_value={"available": False, "reason": "fixture"})
        self.probe.start()
        self.addCleanup(self.probe.stop)

    def apply(self, **kwargs):
        return native.apply_native(self.release, self.config, self.data, activate=False, **kwargs)

    def test_prepare_is_isolated_complete_and_idempotent(self):
        forbidden = self.base / "forbidden-real-state"
        with patch.dict(os.environ, {"XDG_STATE_HOME": str(forbidden)}), patch.object(native, "_activate", side_effect=AssertionError("activation")):
            result = self.apply()
        self.assertEqual(len(result["changed"]), 27)
        self.assertFalse(forbidden.exists())
        self.assertEqual(result["activation"]["status"], "not-requested")
        self.assertTrue(Path(result["backup_dir"]).is_relative_to(self.base / "state"))
        self.assertEqual(set(result["new_paths"]), set(result["changed"]))
        self.assertTrue(all(value is None for value in result["backups"].values()))
        self.assertFalse(any(self.release.rglob("__pycache__")))
        second = self.apply()
        self.assertEqual(second["changed"], [])
        self.assertEqual(second["backups"], {})
        self.assertTrue((self.data / "themes/RGLauncher-Aether/gtk-4.0/gtk-dark.css").is_file())
        self.assertIn("resource:///org/gtk/libgtk/theme/Adwaita", (self.data / "themes/RGLauncher-Aether/gtk-3.0/gtk.css").read_text())

    def test_existing_settings_comments_css_and_modes_preserved(self):
        gtk = self.config / "gtk-3.0/settings.ini"
        gtk.parent.mkdir(parents=True)
        original = "# keep this comment\n[Settings]\ngtk-theme-name=Other\ngtk-decoration-layout=:close\n[Private]\nunchanged=yes\n"
        gtk.write_text(original)
        gtk.chmod(0o600)
        css = gtk.with_name("gtk.css")
        css.write_text("/* User rule */\n.custom { color: red; }\n")
        qt = self.config / "qt6ct/qt6ct.conf"
        qt.parent.mkdir()
        qt.write_text("[Interface]\nstylesheets=/custom/user.qss\n[Private]\nkeep=42\n")
        result = self.apply(state_home=self.base / "own-state")
        self.assertIn("gtk-decoration-layout=:close", gtk.read_text())
        self.assertIn("# keep this comment", gtk.read_text())
        self.assertIn("[Private]\nunchanged=yes", gtk.read_text())
        self.assertEqual(stat.S_IMODE(gtk.stat().st_mode), 0o600)
        self.assertEqual(Path(result["backups"][str(gtk)]).read_text(), original)
        self.assertEqual(result["original_modes"][str(gtk)], 0o600)
        self.assertEqual(stat.S_IMODE(Path(result["manifest"]).stat().st_mode), 0o600)
        self.assertTrue(css.read_text().startswith("/* User rule */\n.custom"))
        self.assertIn("/custom/user.qss", qt.read_text())
        self.assertIn("[Private]\nkeep=42", qt.read_text())
        self.assertLess(qt.read_text().index("controls.qss"), qt.read_text().index("/custom/user.qss"))
        self.assertEqual(self.apply()["changed"], [])

    def test_symlinked_output_and_ancestor_are_rejected_before_writes(self):
        self.config.mkdir()
        other = self.base / "other"
        other.mkdir()
        (self.config / "gtk-3.0").symlink_to(other, target_is_directory=True)
        with self.assertRaises(native.NativeError):
            self.apply()
        self.assertEqual(list(other.iterdir()), [])
        self.assertFalse(self.data.exists())

    def test_kitty_preserves_bindings_and_prior_theme_with_one_last_include(self):
        config = self.config / "kitty/kitty.conf"
        config.parent.mkdir(parents=True)
        original = "# Personal comment\nmap ctrl+shift+t new_tab\ninclude instrument-score-aether.conf\ninclude rglauncher-aether.conf\n"
        config.write_text(original)
        result = self.apply()
        text = config.read_text()
        self.assertIn("map ctrl+shift+t new_tab", text)
        self.assertIn("# Personal comment", text)
        self.assertIn("include instrument-score-aether.conf", text)
        self.assertEqual(text.count("include rglauncher-aether.conf"), 1)
        self.assertTrue(text.rstrip().endswith(native.KITTY_END))
        self.assertEqual(Path(result["backups"][str(config)]).read_text(), original)
        self.assertEqual(self.apply()["changed"], [])

    def test_bad_managed_css_is_preserved_before_any_write(self):
        css = self.config / "gtk-3.0/gtk.css"
        css.parent.mkdir(parents=True)
        css.write_text(native.BLOCK_BEGIN + "\n.custom { color: red; }")
        with self.assertRaises(native.NativeError):
            self.apply()
        self.assertTrue(css.read_text().startswith(native.BLOCK_BEGIN))
        self.assertFalse(self.data.exists())

    def test_invalid_font_or_color_cannot_inject_native_configuration(self):
        roles = self.release / "share/instrument-score-aether/tokens.json"
        for name, value in (("reading", "font\n[Injected]"), ("reading", 'font"; color:red')):
            tokens = copy.deepcopy(TOKENS)
            tokens["font"][name] = value
            roles.write_text(json.dumps(tokens))
            with self.assertRaises(native.NativeError):
                self.apply()
        tokens = copy.deepcopy(TOKENS)
        tokens["color"]["surface"] = "red; background:lime"
        roles.write_text(json.dumps(tokens))
        with self.assertRaises(native.NativeError):
            self.apply()
        self.assertFalse(self.data.exists())

    def test_role_split_native_resources_and_no_private_theme_dependency(self):
        self.apply()
        qt = (self.config / "qt5ct/qt5ct.conf").read_text()
        self.assertIn('general="Noto Sans,', qt)
        self.assertIn('fixed="JetBrainsMono Nerd Font,', qt)
        tcl = (self.data / "rglauncher-linux/tcl/rglauncher-aether.tcl").read_text()
        self.assertIn('TkFixedFont -family "JetBrainsMono Nerd Font"', tcl)
        self.assertIn('TkHeadingFont -family "JetBrainsMono Nerd Font"', tcl)
        self.assertIn("-font TkTextFont", tcl)
        for path in self.config.rglob("*"):
            if path.is_file():
                self.assertNotIn("Sweet-Dark", path.read_text())
        theme = (self.data / "themes/RGLauncher-Aether/gtk-3.0/gtk.css").read_text()
        self.assertIn("border: 1px solid #667e9f", theme)
        self.assertIn("outline: 2px solid #bba6ff", theme)
        self.assertIn("checkbutton check:checked", theme)

    def test_activation_journals_preferences_before_mutation(self):
        resources = self.base / "Xresources"
        resources.write_text("*background: #090e18\n*foreground: #edf4ff\n")
        events, saved = [], []

        def run(command, **kwargs):
            events.append(command)
            if command[1] == "get":
                return subprocess.CompletedProcess(command, 0, "'Old Theme'\n", "")
            if command[1] == "-query":
                return subprocess.CompletedProcess(command, 0, "*background:\t#abcdef\nUnrelated:\tkeep\n", "")
            self.assertTrue(saved, "activation must checkpoint before mutation")
            self.assertEqual(saved[0]["gsettings"]["before"]["gtk-theme"], "'Old Theme'")
            self.assertEqual(saved[0]["xresources"]["before"]["*background"], "#abcdef")
            return subprocess.CompletedProcess(command, 0, "", "")

        def checkpoint(value):
            saved.append(copy.deepcopy(value))

        with patch.object(native.shutil, "which", side_effect=lambda command: "/usr/bin/" + command), patch.object(native.subprocess, "run", side_effect=run), patch.dict(os.environ, {"DISPLAY": ":test"}):
            result = native._activate({"gtk-theme": native.THEME}, resources, checkpoint)
        self.assertEqual(result["gsettings"]["status"], "applied")
        self.assertEqual(result["xresources"]["status"], "applied")
        self.assertNotIn("Unrelated", saved[0]["xresources"]["before"])
        self.assertIsNone(saved[0]["xresources"]["before"]["*foreground"])

    def test_activation_timeout_is_recorded_without_unjournaled_action(self):
        resources = self.base / "Xresources"
        resources.write_text("*background: #090e18\n")
        with patch.object(native.shutil, "which", side_effect=lambda name: "/usr/bin/gsettings" if name == "gsettings" else None), patch.object(native.subprocess, "run", side_effect=subprocess.TimeoutExpired("gsettings", 4)):
            result = native._activate({"gtk-theme": native.THEME}, resources, lambda result: None)
        self.assertEqual(result["gsettings"]["status"], "partial")
        self.assertEqual(result["gsettings"]["before"], {})


class GtkParserTest(unittest.TestCase):
    def test_available_native_gtk_bases_parse_without_display(self):
        for major in (3, 4):
            probe = native._gtk_probe(major)
            if probe["available"]:
                self.assertIsNotNone(probe["base"])
                parsed = native._gtk_probe(major, native._gtk_css(TOKENS, major, probe["base"]))
                self.assertEqual(parsed["errors"], [])


if __name__ == "__main__":
    unittest.main()
