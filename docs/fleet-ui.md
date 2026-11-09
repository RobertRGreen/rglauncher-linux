# Servers / observed systems

`rglauncher_linux.fleet_ui.main()` presents read-only SSH diagnostics in the
Instrument/Score Aether language. Its stable window title is **Servers · RGLauncher**.
The command/singleton and trusted private host inventory belong to the shell
integration; this module contains no real host names, credentials or inventory.
It does not implement an AMP API integration.

## Observations and context

The left host list preserves identity, order and selection while snapshots update.
Rows and targets are updated in place. Their health and last-observation age stay
aligned; a growing age or longer state does not resize/reorder the targets.
The selected host receives the dominant workbench. The list moves above it at
compact widths or larger reading fonts, with its own bounded scroll region.
The selected-host evidence has an independent vertical viewport. Updating metrics
does not replace that viewport or reset its scroll position.

The view shows CPU, RAM, swap, logical cores, load averages and uptime; network
receive/transmit throughput and interfaces; storage read/write throughput;
filesystem capacity/use/available evidence; top process names/PIDs/CPU/RAM;
failed services; and container names/states/status. Native evidence tables retain
full model strings and resizable columns, with horizontal scrolling where needed.
There are no restart, kill, deployment or container-management controls.

Chart histories contain at most 120 received entries per host. One accepted
observation is a point, not fabricated history. An unavailable number remains
unknown rather than becoming zero. Explicit status gaps and sample intervals
longer than six seconds break the trace; no smooth interpolation or animated
activity is generated. Chart legends, sample counts and observed duration name
their evidence. A receiver wall-clock rollback starts a new chart era so live
metrics continue rather than freezing until the old time catches up.

Current values, older retained values and unavailable observations remain
distinct. Authentication required, host-key verification failure, unreachable,
unsupported sampler, stopped monitoring and stale reading each have explicit
text. An SSH/SFTP authentication failure is not presented as proof that the
server is offline. Older metrics remain visible with their age and last-observed
wording. The backend supplies receiver-clock normalized group timestamps;
filesystem, service and container caches expose their separate observation age.
Errors in those groups are displayed, not converted into zero failures or zero
containers. Empty inventory hides metric axes rather than inventing measurements.

## Runtime lifecycle and optional terminal

Only normal runtime imports the backend. It calls `load_hosts()`, `load_interval()`
and `FleetMonitor(hosts, interval=...).start()`; all configured hosts are monitored,
including those not selected. The GTK view reads thread-safe snapshots every two
seconds and publishes that same snapshot for the shell's cached server indicator.
Closing the window, Escape, SIGTERM or SIGINT stops the monitor and publishes its
stopped snapshot, retaining last observations without continuing to claim live
freshness. The shell's own cache policy still controls its indicator.

**Open SSH** is an explicit user action for the selected host. It obtains the
backend's interactive `ssh_argv(host, interactive=True)` and passes that list to
Kitty without a shell expression. No password prompt, terminal or management
command is automatically opened. The connection retains the backend's configured
host-key/authentication policy. Empty selection disables the button.

## Native fixtures and checks

The existing API `main(window_class=..., run_loop=False)` returns a native preview.
It uses clearly labeled synthetic `.example.invalid` hosts and values. It never
imports the backend, starts monitoring, publishes cache, reads private inventory
or executes a process. Its SSH button only explains that no action occurred.

Nine focused tests cover unknown/zero/nonfinite values, stable selection/order,
single/cached points, duplicate samples, stale gaps, bounded histories, removed
hosts, separate cache timestamps and receiver clock corrections. An actual GTK3
offscreen fixture replaces external process APIs with failure spies. A separate
fake-backend offscreen lifecycle test verifies start, live cache publication and
SIGTERM-driven stop/stopped publication without any SSH connection.

Actual native offscreen renders were inspected at 1100px, 900px and 600px; at a
20% larger reading font; with authorization failure, host-key failure, stale data,
empty inventory, complete evidence tables, and a synthetic 30-observation trace
with a gap. All viewports retained their requested widths and reported no missing
Pango glyphs. Vertical scrolling is intentional; fonts are not reduced to keep
the composition on one screen. Numerical values use the exact-value font while
reading and state explanations use the reading face.

Render review corrected these concrete issues before integration:

1. Selected host names inherited a base-theme dark foreground. Their selected
   text now explicitly uses the readable foreground on the raised selection.
2. Compact host lists clipped targets halfway through a row. A bounded two-row
   region and single-line identity/state cells now preserve stable target geometry.
3. Native tables gave nearly all width to the first column, hiding numerical units
   and container status. Explicit numerical/text column minima now preserve units,
   capacity and status; wider text columns share remaining space.
4. Empty and never-observed states displayed arbitrary metric axes. Empty inventory
   now hides measurements; missing samples show a text-only chart placeholder.

These fixtures validate composition, state presentation and bounded local
lifecycles. Live SSH reachability, permissions, remote operating systems and
host-specific sampler behavior remain backend/integration acceptance work.
