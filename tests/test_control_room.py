"""Truthful release messaging and hardware-free Control Room fixture behavior."""
import os
from pathlib import Path
import subprocess
import sys
import unittest

from rglauncher_linux.settings import feed_label, result_feedback


class ReleasePresentationTests(unittest.TestCase):
    def test_check_does_not_claim_installation(self):
        title, body, kind = result_feedback("check", {"update_available": False})
        self.assertEqual(title, "No newer release")
        self.assertIn("Nothing was installed", body)
        title, body, kind = result_feedback("check", {"update_available": True, "available_version": "1.2.3"})
        self.assertEqual(title, "Release available")
        self.assertIn("1.2.3", body)

    def test_noop_and_rollback_hold_are_not_changes(self):
        self.assertEqual(result_feedback("apply", {"changed": False})[0], "No release change")
        title, body, kind = result_feedback("apply", {"changed": False, "reason": "rollback_hold"})
        self.assertIn("held", body)

    def test_changed_release_survives_partial_surface_error(self):
        title, body, kind = result_feedback("apply", {"changed": True, "current_version": "1.2.3", "desktop_refresh": {"status": "partial"}}, "fixture refresh failed")
        self.assertEqual(kind, "warning")
        self.assertIn("1.2.3", body)
        self.assertIn("fixture refresh failed", body)

    def test_error_does_not_claim_release_change(self):
        title, body, kind = result_feedback("rollback", {}, "signature mismatch")
        self.assertEqual(kind, "error")
        self.assertEqual(body, "signature mismatch")

    def test_feed_identity_has_no_network_dependency(self):
        self.assertEqual(feed_label("https://updates.example.org/releases/feed.json"), "updates.example.org")
        self.assertEqual(feed_label("file:///fixture/feed.json"), "Local file feed")
        self.assertEqual(feed_label(None), "Not configured")
        self.assertEqual(feed_label("https://[invalid"), "Unrecognized feed address")

    @unittest.skipUnless(os.environ.get("DISPLAY"), "An X11 offscreen backend is required")
    def test_preview_actions_never_launch_write_preferences_or_update(self):
        program = r'''
import gi
gi.require_version("Gtk","3.0")
from gi.repository import Gtk
from unittest.mock import patch
from rglauncher_linux.settings import main
def deny(*args,**kwargs): raise AssertionError("Preview attempted an external action")
with patch("subprocess.Popen",deny),patch("subprocess.run",deny):
 w=main(window_class=Gtk.OffscreenWindow,run_loop=False)
 ui=w.rgl_ui
 assert ui["preview"]
 for button in ui["launches"].values():button.clicked()
 for button in ui["updates"].values():button.clicked()
 ui["automatic"].set_active(True)
 assert "not saved" in ui["feedback_body"].get_text()
 ui["show_result"]("apply",{"changed":True,"current_version":"1.2.3","desktop_refresh":{"status":"partial"}},"fixture failure")
 assert ui["fields"]["current_version"].get_text()=="1.2.3"
 assert "incomplete" in ui["feedback_body"].get_text()
 w.destroy()
'''
        result = subprocess.run([sys.executable, "-B", "-c", program], cwd=Path(__file__).resolve().parents[1],
                                env=dict(os.environ, GDK_BACKEND="x11"), capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
