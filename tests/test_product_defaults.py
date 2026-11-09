"""Portable product assets, executable entry points and offline Lua geometry."""
import configparser
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ProductDefaultsTest(unittest.TestCase):
    def test_generic_bar_actions_have_public_commands(self):
        config = json.loads(re.sub(r"^\s*//.*$", "", (ROOT / "share/waybar/config.jsonc").read_text(), flags=re.M))
        supported = {"apps", "files", "windows", "audio", "wifi", "bluetooth", "settings"}
        for key, value in config.items():
            if isinstance(value, dict) and "on-click" in value and key != "hyprland/workspaces":
                self.assertRegex(value["on-click"], r"^rglauncher [a-z]+$")
                self.assertIn(value["on-click"].split()[1], supported)
        self.assertFalse(config["exclusive"])
        self.assertEqual(config["position"], "bottom")
        for row in ("modules-left", "modules-center", "modules-right"):
            self.assertTrue(all(name in config for name in config[row]))

    def test_desktop_entries_are_valid_and_use_included_icons(self):
        entries = sorted((ROOT / "share/applications").glob("rglauncher-*.desktop"))
        self.assertEqual(len(entries), 9)
        for path in entries:
            config = configparser.ConfigParser(interpolation=None)
            config.read(path)
            entry = config["Desktop Entry"]
            self.assertTrue(entry["Exec"].startswith("rglauncher "))
            self.assertEqual(entry["Terminal"], "false")
            icon = entry["Icon"] + ".svg"
            self.assertTrue(any((ROOT / "share/icons/aether-score/scalable").rglob(icon)), icon)
        validator = shutil.which("desktop-file-validate")
        if validator:
            result = subprocess.run([validator, *map(str, entries)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_bar_css_parses_when_gtk3_available(self):
        from rglauncher_linux.native import _gtk_probe
        probe = _gtk_probe(3, (ROOT / "share/waybar/style.css").read_text())
        if probe["available"]:
            self.assertEqual(probe["errors"], [])

    def test_lua_example_registers_and_fractional_windows_do_not_overlap(self):
        lua = shutil.which("lua")
        if not lua:
            self.skipTest("Lua is not installed")
        program = r'''
local binds, dispatched = {}, 0
local function dispatcher(...) return function() dispatched = dispatched + 1 end end
local namespace = setmetatable({}, { __index = function(t, k) local v = dispatcher; rawset(t,k,v); return v end })
hl = {
  monitor=function() end,config=function() end,curve=function() end,animation=function() end,layer_rule=function() end,
  dsp=setmetatable({window=namespace,cursor=namespace}, {__index=function() return dispatcher end}),
  bind=function(key,action,options) binds[key] = {action=action,options=options or {}} end,
  on=function() return {remove=function() end} end,
  layout={register=function() end},get_active_workspace=function() return nil end,
  dispatch=function() error("No action during config preparation") end,
}
dofile(os.getenv("RGL_RELEASE_ROOT").."/share/hyprland/hyprland.lua")
assert(binds["SUPER + F"] and binds["SUPER + C"] and binds["ALT + Tab"])
assert(binds["SUPER + SHIFT + left"] and binds["SUPER + 0"])
assert(binds["SUPER + Tab"].options.allow_input_capture)
assert(binds["ALT + Tab"].options.dont_inhibit)
assert(dispatched == 0)
local layout = rglauncher_nav.snap_layout
for count=2,12 do
  local windows = {{id="snap",request={divisions=3,column=0,priority=1}}}
  for i=2,count do windows[#windows+1] = {id=tostring(i)} end
  local boxes = layout.arrange(windows)
  for _, item in ipairs(windows) do
    local a=assert(boxes[item.id]);assert(a.w>0 and a.h>0 and a.x>=0 and a.y>=0 and a.x+a.w<=6 and a.y+a.h<=6)
    for _, other in ipairs(windows) do
      if other.id ~= item.id then
        local b=assert(boxes[other.id])
        assert(a.x+a.w<=b.x or b.x+b.w<=a.x or a.y+a.h<=b.y or b.y+b.h<=a.y)
      end
    end
  end
end
'''
        result = subprocess.run([lua, "-"], input=program, text=True, capture_output=True,
                                env=dict(os.environ, RGL_RELEASE_ROOT=str(ROOT)))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_arch_recipe_syntax(self):
        result = subprocess.run(["bash", "-n", str(ROOT / "packaging/arch/PKGBUILD")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
