-- MIT: Robert R. Green and contributors.
-- Opt-in RGLauncher session example for Hyprland 0.56 Lua. Never auto-installed.
-- Review docs/hyprland-session.md before selecting this configuration.
local home = assert(os.getenv("HOME"), "HOME is required")
local data_home = os.getenv("XDG_DATA_HOME") or (home .. "/.local/share")
local release = os.getenv("RGL_RELEASE_ROOT") or (data_home .. "/rglauncher-linux/current")
local example = release .. "/share/hyprland/"

hl.monitor({ output = "", mode = "preferred", position = "auto", scale = 1 })
hl.config({
    general = {
        layout = "dwindle", gaps_in = 6, gaps_out = 14, border_size = 2,
        col = { active_border = { colors = { "rgba(73e4f2ee)", "rgba(bba6ffee)" }, angle = 45 },
                inactive_border = "rgba(33445fff)" },
    },
    decoration = {
        rounding = 10, active_opacity = 1.0, inactive_opacity = 1.0,
        blur = { enabled = true, size = 4, passes = 2, ignore_opacity = true },
        shadow = { enabled = false },
    },
    input = { follow_mouse = 1 },
    misc = { force_default_wallpaper = 0, disable_hyprland_logo = true },
})
hl.curve("rglauncherEase", { type = "bezier", points = { {0.23, 1}, {0.32, 1} } })
hl.animation({ leaf = "global", enabled = true, speed = 4, bezier = "rglauncherEase" })
hl.animation({ leaf = "borderangle", enabled = false, speed = 4, bezier = "rglauncherEase" })
for _, namespace in ipairs({ "cyber-carousel", "wifi-menu", "bt-menu", "audio-menu", "calc-menu", "waybar" }) do
    hl.layer_rule({ match = namespace, blur = true })
end

-- Clean old subscriptions if the example is explicitly reloaded.
local previous = _G.rglauncher_nav
if previous and previous.shutdown then previous.shutdown() end
local nav = dofile(example .. "window-navigation.lua")
if previous then
    for _, key in ipairs({ "suspended", "originals", "placements", "snap_workspaces", "serial", "base_layouts" }) do
        nav[key] = previous[key]
    end
end
_G.rglauncher_nav = nav
nav.install(example .. "snap-layout.lua")

-- Stable MRU switching releases the old client's active pointer constraint.
hl.bind("ALT + Tab", function() nav.step(1) end, { dont_inhibit = true })
hl.bind("ALT + SHIFT + Tab", function() nav.step(-1) end, { dont_inhibit = true })
for _, key in ipairs({ "Alt_L", "Alt_R" }) do
    hl.bind(key, function() nav.finish() end, { release = true, ignore_mods = true, non_consuming = true, dont_inhibit = true })
end
for _, key in ipairs({ "Super_L", "Super_R" }) do
    hl.bind(key, function() nav.end_snap() end, { release = true, ignore_mods = true, non_consuming = true, dont_inhibit = true })
end
hl.bind("SUPER + Tab", function() nav.escape() end, { dont_inhibit = true, allow_input_capture = true })
hl.bind("SUPER + W", function() nav.escape() end, { dont_inhibit = true, allow_input_capture = true })
hl.bind("SUPER + F", function() nav.toggle_fullscreen() end, { dont_inhibit = true })
hl.bind("SUPER + C", hl.dsp.window.close(), { dont_inhibit = true })
hl.bind("SUPER + mouse:272", function() nav.manual_move(false) end, { mouse = true, dont_inhibit = true })
hl.bind("SUPER + mouse:273", function() nav.manual_move(true) end, { mouse = true, dont_inhibit = true })
hl.bind("SUPER + BackSpace", function() nav.restore() end, { dont_inhibit = true })
for _, direction in ipairs({ "left", "right", "up", "down" }) do
    local axis = direction
    hl.bind("SUPER + " .. axis, function() nav.snap(axis, 2) end, { dont_inhibit = true })
    hl.bind("SUPER + SHIFT + " .. axis, function() nav.snap(axis, 3) end, { dont_inhibit = true })
end
for index = 1, 10 do
    local workspace = index
    local key = index == 10 and "0" or tostring(index)
    hl.bind("SUPER + " .. key, hl.dsp.focus({ workspace = workspace }), { dont_inhibit = true })
    hl.bind("SUPER + SHIFT + " .. key, hl.dsp.window.move({ workspace = workspace, follow = false }), { dont_inhibit = true })
end

hl.bind("SUPER + space", hl.dsp.exec_cmd("rglauncher apps"), { dont_inhibit = true })
hl.bind("SUPER + R", hl.dsp.exec_cmd("rglauncher apps"), { dont_inhibit = true })
hl.bind("SUPER + Q", hl.dsp.exec_cmd("rglauncher terminal"), { dont_inhibit = true })
hl.bind("SUPER + D", hl.dsp.exec_cmd("rglauncher files"), { dont_inhibit = true })
hl.bind("SUPER + comma", hl.dsp.exec_cmd("rglauncher settings"), { dont_inhibit = true })
hl.bind("SUPER + B", hl.dsp.exec_cmd("rglauncher shelf show"), { dont_inhibit = true })
-- Deliberate four-key exit, with no personal remote-control hook.
hl.bind("SUPER + CTRL + ALT + Delete", hl.dsp.exit())

-- These run only after the user chooses this example for a NEW session.
hl.on("hyprland.start", function()
    hl.dispatch(hl.dsp.exec_cmd("rglauncher shelf run"))
end)
