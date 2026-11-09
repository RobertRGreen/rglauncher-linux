-- MIT: Robert R. Green and contributors.
-- Fractional tiled placement. Hyprland supplies the current logical work area
-- and applies borders/gaps via target:place(), including on monitor changes.
return function(nav)
    local layout = { rules = {} }
    local function area(r) return r.w * r.h end

    -- Pure geometry, also used by the offline layout checks.
    function layout.arrange(items)
        local occupied, claims, pending, candidates = {}, {}, {}, {}
        for y = 0, 5 do occupied[y] = {} end
        for _, item in ipairs(items) do
            if item.request then candidates[#candidates + 1] = item
            else pending[#pending + 1] = item end
        end
        table.sort(candidates, function(a, b)
            local ap, bp = a.request.priority or 0, b.request.priority or 0
            if ap == bp then return a.id < b.id end
            return ap > bp
        end)
        for _, item in ipairs(candidates) do
            local q = item.request
            local span = 6 / q.divisions
            local x1, x2 = q.column and q.column * span or 0, q.column and (q.column + 1) * span or 6
            local y1, y2 = q.row and q.row * span or 0, q.row and (q.row + 1) * span or 6
            local fits = true
            for y = y1, y2 - 1 do for x = x1, x2 - 1 do
                if occupied[y][x] then fits = false end
            end end
            if fits then
                for y = y1, y2 - 1 do for x = x1, x2 - 1 do occupied[y][x] = item.id end end
                claims[#claims + 1] = { item = item, box = { x = x1, y = y1, w = x2 - x1, h = y2 - y1 } }
            else pending[#pending + 1] = item end
        end
        local empty = false
        for y = 0, 5 do for x = 0, 5 do if not occupied[y][x] then empty = true end end end
        -- If every cell is claimed, divide the oldest claim to make room for
        -- an additional window. Never stack an overflow window over its peers.
        if #pending > 0 and not empty and #claims > 0 then
            local released = table.remove(claims)
            pending[#pending + 1] = released.item
            for y = released.box.y, released.box.y + released.box.h - 1 do
                for x = released.box.x, released.box.x + released.box.w - 1 do occupied[y][x] = nil end
            end
        end
        local free = {}
        -- Extract maximal free rectangles from the small 6x6 grid. This grid
        -- represents both halves and thirds exactly, without pixel rounding.
        while true do
            local best = nil
            for y1 = 0, 5 do for x1 = 0, 5 do
                if not occupied[y1][x1] then
                    for y2 = y1, 5 do for x2 = x1, 5 do
                        local fits = true
                        for y = y1, y2 do for x = x1, x2 do
                            if occupied[y][x] then fits = false; break end
                        end if not fits then break end end
                        local box = { x = x1, y = y1, w = x2 - x1 + 1, h = y2 - y1 + 1 }
                        if fits and (not best or area(box) > area(best)) then best = box end
                    end end
                end
            end end
            if not best then break end
            free[#free + 1] = best
            for y = best.y, best.y + best.h - 1 do
                for x = best.x, best.x + best.w - 1 do occupied[y][x] = true end
            end
        end
        while #free > 0 and #free < #pending do
            table.sort(free, function(a, b) return area(a) > area(b) end)
            local r = table.remove(free, 1)
            if r.w >= r.h then
                free[#free + 1] = { x = r.x, y = r.y, w = r.w / 2, h = r.h }
                free[#free + 1] = { x = r.x + r.w / 2, y = r.y, w = r.w / 2, h = r.h }
            else
                free[#free + 1] = { x = r.x, y = r.y, w = r.w, h = r.h / 2 }
                free[#free + 1] = { x = r.x, y = r.y + r.h / 2, w = r.w, h = r.h / 2 }
            end
        end
        table.sort(free, function(a, b)
            if area(a) ~= area(b) then return area(a) > area(b) end
            if a.x ~= b.x then return a.x < b.x end
            return a.y < b.y
        end)
        local result = {}
        for _, claim in ipairs(claims) do result[claim.item.id] = claim.box end
        for i, item in ipairs(pending) do result[item.id] = free[i] end
        return result
    end

    local function recalculate(ctx)
        local items = {}
        for i, target in ipairs(ctx.targets) do
            local w = target.window
            local id = w and w.address or "target:" .. i
            items[#items + 1] = { id = id, request = w and nav.placements[id], target = target }
        end
        local boxes = layout.arrange(items)
        for _, item in ipairs(items) do
            local r = boxes[item.id]
            if r then
                local a = ctx.area
                item.target:place({ x = a.x + a.w * r.x / 6, y = a.y + a.h * r.y / 6,
                    w = a.w * r.w / 6, h = a.h * r.h / 6 })
            end
        end
    end

    function layout.register()
        hl.layout.register("desktop-snap", {
            recalculate = recalculate,
            layout_msg = function() return true end,
        })
    end

    function layout.enable(ws)
        if not layout.rules[ws.id] then
            nav.base_layouts[ws.id] = nav.base_layouts[ws.id] or (ws.tiled_layout ~= "lua:desktop-snap" and ws.tiled_layout or "dwindle")
            nav.snap_workspaces[ws.id] = true
            layout.rules[ws.id] = hl.workspace_rule({ workspace = tostring(ws.id), layout = "lua:desktop-snap" })
        end
    end

    function layout.disable(id)
        -- An explicit replacement also refreshes the workspace's algorithm.
        hl.workspace_rule({ workspace = tostring(id), layout = nav.base_layouts[id] or "dwindle" })
        layout.rules[id], nav.snap_workspaces[id] = nil, nil
    end

    function layout.refresh()
        local ws = hl.get_active_workspace()
        if ws and ws.tiled_layout == "lua:desktop-snap" then
            hl.dispatch(hl.dsp.layout("recalculate"))
        end
    end

    return layout
end
