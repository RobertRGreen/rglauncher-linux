-- MIT: Robert R. Green and contributors. Portable accepted window navigation. No shell commands or blocking I/O in callbacks.
local nav = { cycle = nil, suspended = {}, originals = {}, placements = {}, snap_workspaces = {}, base_layouts = {}, snap_session = nil, serial = 0 }

local function eligible(w)
    return w.mapped and not w.hidden and w.accepts_input and w.workspace
        and w.workspace.id > 0 and w.focus_history_id >= 0
end

local function windows()
    local result = {}
    for _, w in ipairs(hl.get_windows()) do
        if eligible(w) then result[#result + 1] = w end
    end
    table.sort(result, function(a, b)
        if a.focus_history_id == b.focus_history_id then return a.address < b.address end
        return a.focus_history_id < b.focus_history_id
    end)
    return result
end

function nav.focus(selector)
    local target = hl.get_window(selector)
    if not target or not target.mapped then return end
    -- The existing window picker also lists windows hidden with SUPER+H.
    if target.workspace and target.workspace.name == "special:minimized" then
        hl.dispatch(hl.dsp.window.move({ window = target, workspace = hl.get_active_workspace(), follow = false }))
        hl.dispatch(hl.dsp.window.clear_tags({ window = target }))
    end
    local active = hl.get_active_window()
    -- Keep the client's fullscreen state (and game render mode) intact while
    -- exposing another window on the same workspace. Restore on return.
    if active and active.address ~= target.address and active.fullscreen > 0
        and active.workspace and target.workspace
        and active.workspace.id == target.workspace.id then
        nav.suspended[active.address] = active.fullscreen
        hl.dispatch(hl.dsp.window.fullscreen_state({ window = active, action = "set", internal = 0, client = -1 }))
    end
    hl.dispatch(hl.dsp.focus({ window = target }))
    if target.floating then
        hl.dispatch(hl.dsp.window.alter_zorder({ window = target, mode = "top" }))
    end
    local mode = nav.suspended[target.address]
    if mode then
        nav.suspended[target.address] = nil
        hl.dispatch(hl.dsp.window.fullscreen_state({ window = target, action = "set", internal = mode, client = -1 }))
    end
    -- Changing keyboard focus deactivates the old surface's pointer constraint
    -- in Hyprland. Move the pointer into the selected app as well, so follow_mouse
    -- cannot immediately hand focus and the pointer lock back to the game.
    hl.dispatch(hl.dsp.cursor.move({
        x = math.floor(target.at.x + target.size.x / 2),
        y = math.floor(target.at.y + target.size.y / 2),
    }))
end

function nav.finish()
    nav.cycle = nil
end

function nav.step(direction)
    local active = hl.get_active_window()
    if not nav.cycle or not active or nav.cycle.selected ~= active.address then
        local order = {}
        for _, w in ipairs(windows()) do order[#order + 1] = w.address end
        nav.cycle = { order = order, selected = active and active.address }
    end
    -- Keep a stable MRU order while Alt is held, ignoring windows closed since
    -- the first Tab. Releasing Alt commits the selection and resets the order.
    local order = {}
    for _, addr in ipairs(nav.cycle.order) do
        local w = hl.get_window("address:" .. addr)
        if w and eligible(w) then order[#order + 1] = addr end
    end
    nav.cycle.order = order
    if #order < 2 then return end
    local index = 1
    for i, addr in ipairs(order) do
        if active and addr == active.address then index = i; break end
    end
    local addr = order[((index - 1 + direction) % #order) + 1]
    nav.cycle.selected = addr
    nav.focus("address:" .. addr)
end

function nav.toggle_fullscreen()
    local active = hl.get_active_window()
    if active then nav.suspended[active.address] = nil end
    hl.dispatch(hl.dsp.window.fullscreen({ action = "toggle" }))
end

function nav.escape()
    nav.finish()
    hl.dispatch(hl.dsp.release_input_capture())
    -- The overlay takes keyboard focus and deactivates the old pointer lock.
    -- Keep fullscreen intact if dismissed without selecting another window.
    hl.dispatch(hl.dsp.exec_cmd("rglauncher windows"))
end

function nav.end_snap()
    nav.snap_session = nil
end

function nav.restore()
    local w = hl.get_active_window()
    if not w then return end
    local original = nav.originals[w.address]
    if not original then return end
    nav.originals[w.address], nav.placements[w.address], nav.snap_session = nil, nil, nil
    nav.suspended[w.address] = nil
    hl.dispatch(hl.dsp.window.fullscreen_state({ window = w, action = "set", internal = 0, client = -1 }))
    hl.dispatch(hl.dsp.window.float({ window = w, action = original.floating and "enable" or "disable" }))
    if original.floating then
        hl.dispatch(hl.dsp.window.resize({ window = w, x = original.width, y = original.height, relative = false }))
        hl.dispatch(hl.dsp.window.move({ window = w, x = original.x, y = original.y, relative = false }))
    end
    nav.reconcile_layouts()
    if nav.snap_layout then nav.snap_layout.refresh() end
    hl.dispatch(hl.dsp.window.fullscreen_state({ window = w, action = "set", internal = original.fullscreen, client = original.client }))
end

function nav.snap(direction, divisions)
    local w = hl.get_active_window()
    if not w or not w.monitor then return end
    local addr = w.address
    if not nav.originals[addr] then
        nav.originals[addr] = { floating = w.floating, x = w.at.x, y = w.at.y,
            width = w.size.x, height = w.size.y, fullscreen = w.fullscreen, client = w.fullscreen_client }
    end
    local session = nav.snap_session
    if not session or session.address ~= addr or session.divisions ~= divisions then
        session = { address = addr, divisions = divisions }
        nav.snap_session = session
    end
    local horizontal = direction == "left" or direction == "right"
    local axis = horizontal and "column" or "row"
    local delta = (direction == "left" or direction == "up") and -1 or 1
    local previous = nav.placements[addr]
    local cell = session[axis]
    -- In thirds mode, repeated arrows step through the center third. A new
    -- Super hold composes a fresh shape; perpendicular arrows combine axes.
    if divisions == 3 then
        if cell == nil and previous and previous.divisions == divisions then
            cell = previous[axis]
        end
        if cell ~= nil then cell = math.max(0, math.min(divisions - 1, cell + delta)) end
    end
    if cell == nil then cell = delta < 0 and 0 or divisions - 1 end
    session[axis] = cell

    nav.suspended[addr] = nil
    nav.serial = nav.serial + 1
    nav.placements[addr] = { divisions = divisions, column = session.column, row = session.row, priority = nav.serial }
    hl.dispatch(hl.dsp.window.fullscreen_state({ window = w, action = "set", internal = 0, client = -1 }))
    nav.snap_layout.enable(w.workspace)
    hl.dispatch(hl.dsp.window.float({ window = w, action = "disable" }))
    nav.snap_layout.refresh()
end

function nav.reconcile_layouts()
    if not nav.snap_layout then return end
    local used = {}
    for addr in pairs(nav.placements) do
        local w = hl.get_window("address:" .. addr)
        if w and w.mapped and w.workspace and w.workspace.id > 0 then
            used[w.workspace.id] = true
            nav.snap_layout.enable(w.workspace)
        end
    end
    for id, rule in pairs(nav.snap_layout.rules) do
        if not used[id] then
            nav.snap_layout.disable(id)
        end
    end
end

function nav.manual_move(resize)
    local w = hl.get_active_window()
    if not w then return end
    nav.placements[w.address], nav.snap_session = nil, nil
    -- Explicit dragging/resizing detaches from a snap, as on conventional
    -- desktops. Keyboard snapping always returns the window to tiled layout.
    if not w.floating then
        local x, y, width, height = w.at.x, w.at.y, w.size.x, w.size.y
        hl.dispatch(hl.dsp.window.fullscreen_state({ window = w, action = "set", internal = 0, client = -1 }))
        hl.dispatch(hl.dsp.window.float({ window = w, action = "enable" }))
        hl.dispatch(hl.dsp.window.resize({ window = w, x = width, y = height, relative = false }))
        hl.dispatch(hl.dsp.window.move({ window = w, x = x, y = y, relative = false }))
    end
    nav.reconcile_layouts()
    hl.dispatch(resize and hl.dsp.window.resize() or hl.dsp.window.drag())
end

function nav.shutdown()
    if nav.active_subscription then nav.active_subscription:remove() end
    if nav.close_subscription then nav.close_subscription:remove() end
    if nav.move_subscription then nav.move_subscription:remove() end
end

function nav.install(layout_path)
    assert(layout_path, "Pass the RGLauncher snap-layout.lua path")
    nav.snap_layout = dofile(layout_path)(nav)
    nav.snap_layout.register()
    nav.reconcile_layouts()
    nav.active_subscription = hl.on("window.active", function()
        local w = hl.get_active_window()
        if not w then return end
        local mode = nav.suspended[w.address]
        if mode then
            nav.suspended[w.address] = nil
            hl.dispatch(hl.dsp.window.fullscreen_state({ window = w, action = "set", internal = mode, client = -1 }))
        end
    end)
    nav.close_subscription = hl.on("window.close", function()
        for _, map in ipairs({ nav.originals, nav.placements, nav.suspended }) do
            for addr in pairs(map) do
                local w = hl.get_window("address:" .. addr)
                if not w or not w.mapped then map[addr] = nil end
            end
        end
        nav.reconcile_layouts()
    end)
    nav.move_subscription = hl.on("window.move_to_workspace", function() nav.reconcile_layouts() end)
end

return nav
