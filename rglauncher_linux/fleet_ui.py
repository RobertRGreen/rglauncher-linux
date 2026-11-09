"""Read-only SSH diagnostics; fixture mode never loads or starts the backend."""
from __future__ import annotations
from collections import deque
import copy
import math
import signal
import subprocess
import sys
import time

from .paths import release_root

STATES = {
    "connecting": "Connecting", "online": "Live", "stale": "Stale observation",
    "auth_required": "Authorization required", "host_key_error": "Host key verification failed",
    "unreachable": "Unreachable", "unsupported": "Sampler unavailable", "error": "Observation error",
    "stopped": "Monitoring stopped",
}
LIST_STATES = {**STATES,"stale":"Stale","host_key_error":"Host key failure","unsupported":"Sampler unavailable","stopped":"Stopped"}


def number(value):
    if not isinstance(value,(int,float)) or isinstance(value,bool):return None
    try:return float(value) if math.isfinite(value) else None
    except (OverflowError,ValueError):return None


def amount(value, suffix="B"):
    value = number(value)
    if value is None: return "—"
    for unit in ("", "Ki", "Mi", "Gi", "Ti", "Pi"):
        if abs(value) < 1024 or unit == "Pi":
            return f"{value:.1f} {unit}{suffix}" if unit else f"{value:.0f} {suffix}"
        value /= 1024


def percent(value):
    value = number(value)
    return "—" if value is None else f"{value:.1f}%"


def age_text(value):
    value = number(value)
    if value is None: return "Not observed"
    value = max(0, int(value))
    if value < 60: return f"{value}s ago"
    if value < 3600: return f"{value // 60}m {value % 60:02d}s ago"
    return f"{value // 3600}h {(value % 3600) // 60:02d}m ago"


def uptime_text(value):
    value = number(value)
    if value is None: return "—"
    days, rest = divmod(max(0, int(value)), 86400)
    hours, rest = divmod(rest, 3600)
    return f"{days}d {hours:02d}h" if days else f"{hours}h {rest // 60:02d}m"


SERIES = {
    "cpu": ("cpu", "percent"), "ram": ("memory", "percent"), "swap": ("swap", "percent"),
    "load1": ("load", "one"), "load5": ("load", "five"), "load15": ("load", "fifteen"),
    "rx": ("network", "rx_bytes_per_second"), "tx": ("network", "tx_bytes_per_second"),
    "read": ("disk", "read_bytes_per_second"), "write": ("disk", "write_bytes_per_second"),
}


class FleetViewModel:
    """Stable host identity/selection and bounded *observed* history."""
    def __init__(self):
        self.hosts, self.order, self.selected = {}, [], None
        self.histories, self.last_observed, self.last_state = {}, {}, {}

    def update(self, snapshots, now=None):
        now = time.time() if now is None else now
        incoming = {str(row["id"]): row for row in snapshots if isinstance(row, dict) and row.get("id")}
        self.order = [key for key in self.order if key in incoming]
        self.order.extend(key for key in incoming if key not in self.order)
        self.hosts = incoming
        if self.selected not in incoming: self.selected = self.order[0] if self.order else None
        for key in self.order:
            row = incoming[key]
            history = self.histories.setdefault(key, deque(maxlen=120))
            observed = number(row.get("observed_at"))
            metrics = row.get("metrics") or {}
            if observed is not None and observed<self.last_observed.get(key,-math.inf) and metrics:
                # Preserve fresh evidence after a receiver wall-clock correction.
                # Separate clock eras instead of drawing reversed/fictitious time.
                history.clear();self.last_observed.pop(key,None)
            if observed is not None and observed > self.last_observed.get(key, -math.inf) and isinstance(metrics, dict) and metrics:
                values = {"time": observed}
                for name, (group, field) in SERIES.items(): values[name] = number((metrics.get(group) or {}).get(field))
                history.append(values)
                self.last_observed[key] = observed
            elif row.get("state") != "online" and self.last_state.get(key) == "online" and history:
                history.append({"time": now, "gap": True})
            self.last_state[key] = row.get("state")
        # Removed configuration entries should not retain unbounded histories.
        for mapping in (self.histories, self.last_observed, self.last_state):
            for key in list(mapping):
                if key not in incoming: del mapping[key]

    def select(self, identity):
        if identity in self.hosts: self.selected = identity


def fixture_snapshots(now=None):
    """Labeled synthetic evidence for the action-free native rendering hook."""
    now = time.time() if now is None else now
    metrics = {
        "sampled_at": now, "uptime_seconds": 1234567,
        "cpu": {"percent": 28.4, "cores": 4, "updated_at": now},
        "memory": {"used_bytes": 3565158400, "total_bytes": 8589934592, "available_bytes": 5024776192, "percent": 41.5, "updated_at": now},
        "swap": {"used_bytes": 0, "total_bytes": 2147483648, "percent": 0, "updated_at": now},
        "load": {"one": .72, "five": .55, "fifteen": .46, "updated_at": now},
        "network": {"rx_bytes_per_second": 258048, "tx_bytes_per_second": 1048576, "interfaces": ["eth0"], "updated_at": now},
        "disk": {"read_bytes_per_second": 4194304, "write_bytes_per_second": 1048576, "updated_at": now, "filesystems_updated_at": now-4,
            "filesystems": [{"mount": "/", "used_bytes": 24910810316, "total_bytes": 68719476736, "available_bytes": 43808666420, "percent": 36.3}, {"mount": "/srv/data", "used_bytes": 96636764160, "total_bytes": 214748364800, "available_bytes": 118111600640, "percent": 45}]},
        "processes": [{"pid": 1842, "name": "application-worker", "cpu_percent": 14.2, "memory_bytes": 268435456}, {"pid": 2291, "name": "database", "cpu_percent": 6.4, "memory_bytes": 536870912}],
        "services": {"updated_at": now-3, "failed": [{"unit": "example-backup.service", "description": "Synthetic failed unit for inspection"}]},
        "containers": {"updated_at": now-3, "items": [{"id": "fixture-web", "name": "web", "state": "running", "status": "Up 3 days"}, {"id": "fixture-job", "name": "batch-job", "state": "exited", "status": "Exited (0) 2 hours ago"}]},
    }
    stale = copy.deepcopy(metrics)
    stale["sampled_at"] = now-23
    for group in stale.values():
        if isinstance(group,dict):
            for field in ("updated_at","filesystems_updated_at"):
                if field in group:group[field]-=23
    return [
        {"id": "atlas", "label": "Atlas", "target": "atlas.example.invalid", "group": "VPS", "state": "online", "observed_at": now, "age": 0, "error": None, "metrics": metrics},
        {"id": "relay", "label": "Relay", "target": "relay.example.invalid", "group": "VPS", "state": "stale", "observed_at": now-23, "age": 23, "error": "Synthetic stream interruption; last values retained.", "metrics": stale},
        {"id": "studio", "label": "Studio", "target": "studio.example.invalid", "group": "LAB", "state": "auth_required", "observed_at": None, "age": None, "error": "Synthetic SSH authentication failure. Interactive authorization may be required.", "metrics": None},
        {"id": "edge", "label": "Edge", "target": "edge.example.invalid", "group": "VPS", "state": "host_key_error", "observed_at": None, "age": None, "error": "Synthetic host key verification failure. No observation was accepted.", "metrics": None},
    ]


def main(*, window_class=None, run_loop=True):
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("PangoCairo", "1.0")
    from gi.repository import Gtk, Gdk, GLib, GdkPixbuf, Pango, PangoCairo
    root = release_root()
    sys.path.insert(0, str(root / "bin"))
    from _cyber_theme import (BG, BG_CARD, BG_HOT, FG, MUTED, LINE, CONTROL_LINE, ACCENT2, PURPLE,
        SUCCESS, WARNING, DANGER, FONT_BODY, FONT_HEAD, FONT_MONO, rgba)
    from _aether_material import surface_declarations
    preview = not run_loop
    model = FleetViewModel()
    runtime = {"closed": False, "monitor": None, "timer": None, "signals":[], "hosts": {}, "backend": None, "selected": None, "compact": None}
    window = (window_class or Gtk.Window)(title="Servers · RGLauncher")
    window.set_default_size(1100, 850)
    if preview and isinstance(window, Gtk.OffscreenWindow): window.set_size_request(1100, 850)
    window.get_style_context().add_class("rgl-fleet")
    provider = Gtk.CssProvider()
    provider.load_from_data(f'''
window.rgl-fleet {{background:{BG};color:{FG};font-family:"{FONT_BODY}";}}
.rgl-fleet .shell {{padding:22px;}}
.rgl-fleet label {{text-shadow:none;}}
.rgl-fleet .title {{font-family:"{FONT_HEAD}";font-size:1.85em;font-weight:600;}}
.rgl-fleet .eyebrow {{font-family:"{FONT_MONO}";font-size:.8em;letter-spacing:.7px;color:{ACCENT2};}}
.rgl-fleet .subtitle,.rgl-fleet .muted {{color:{MUTED};font-size:.9em;}}
.rgl-fleet .preview {{font-family:"{FONT_MONO}";font-size:.8em;color:{WARNING};}}
.rgl-fleet .sidebar {{background:{BG_CARD};border:1px solid {LINE};border-radius:13px;padding:14px;}}
.rgl-fleet .workbench {{{surface_declarations(17)} padding:18px;}}
.rgl-fleet .host-list {{background:transparent;}}
.rgl-fleet .host-row {{background:transparent;border:0;border-left:3px solid transparent;border-radius:7px;padding:10px 8px;}}
.rgl-fleet .host-row:selected {{background:{BG_HOT};border-left-color:{ACCENT2};}}
.rgl-fleet .host-row:selected label.host-name {{color:{FG};}}
.rgl-fleet .host-name,.rgl-fleet .heading {{font-family:"{FONT_HEAD}";font-weight:600;font-size:1.1em;}}
.rgl-fleet .target,.rgl-fleet .value,.rgl-fleet .freshness {{font-family:"{FONT_MONO}";}}
.rgl-fleet .target,.rgl-fleet .freshness {{color:{MUTED};font-size:.8em;}}
.rgl-fleet .value {{font-size:1.3em;color:{FG};}}
.rgl-fleet .state {{font-size:.8em;color:{MUTED};}}
.rgl-fleet .state.online {{color:{SUCCESS};}}
.rgl-fleet .state.stale,.rgl-fleet .state.auth_required,.rgl-fleet .state.connecting,.rgl-fleet .state.stopped {{color:{WARNING};}}
.rgl-fleet .state.error,.rgl-fleet .state.host_key_error,.rgl-fleet .state.unreachable {{color:{DANGER};}}
.rgl-fleet .observation {{background:{BG};border-left:3px solid {ACCENT2};padding:10px;border-radius:6px;}}
.rgl-fleet .observation.stale,.rgl-fleet .observation.auth_required {{border-left-color:{WARNING};}}
.rgl-fleet .observation.error,.rgl-fleet .observation.host_key_error,.rgl-fleet .observation.unreachable {{border-left-color:{DANGER};}}
.rgl-fleet .stat {{border-bottom:1px solid {LINE};padding:8px 3px;}}
.rgl-fleet .chart {{background:{BG};border:1px solid {LINE};border-radius:9px;padding:10px;}}
.rgl-fleet .evidence {{border-top:1px solid {LINE};padding-top:12px;}}
.rgl-fleet treeview {{background:{BG};color:{FG};font-size:.9em;}}
.rgl-fleet treeview header button {{background:{BG_CARD};color:{MUTED};border:0;}}
.rgl-fleet button {{background-image:none;background-color:{BG_CARD};color:{FG};border:1px solid {CONTROL_LINE};border-radius:8px;padding:8px 11px;box-shadow:none;text-shadow:none;}}
.rgl-fleet button:hover {{background:{BG_HOT};border-color:{ACCENT2};}}
.rgl-fleet button:focus,.rgl-fleet row:focus {{outline:2px solid {PURPLE};outline-offset:1px;}}
.rgl-fleet button:disabled {{color:{MUTED};border-color:{LINE};}}
'''.encode())
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def label(text="", css=None, max_chars=42):
        widget = Gtk.Label(label=str(text), xalign=0)
        widget.set_line_wrap(True)
        widget.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        widget.set_max_width_chars(max_chars)
        if css:
            for part in css.split(): widget.get_style_context().add_class(part)
        return widget

    def box(css=None, spacing=7):
        widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)
        if css: widget.get_style_context().add_class(css)
        return widget

    def state_class(widget, value):
        context = widget.get_style_context()
        for name in STATES: context.remove_class(name)
        if value is not None:context.add_class(value if value in STATES else "error")

    shell = box("shell", 16)
    window.add(shell)
    header = Gtk.Box(spacing=12)
    icon_path = root / "assets/shelf-icons/aether-development.svg"
    icon = Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(str(icon_path), 40, 40, True)) if icon_path.is_file() else Gtk.Image.new_from_icon_name("network-server", Gtk.IconSize.DIALOG)
    header.pack_start(icon, False, False, 0)
    masthead = box(spacing=4)
    masthead.pack_start(label("RGLauncher / OBSERVED SYSTEMS", "eyebrow"), False, False, 0)
    masthead.pack_start(label("Servers", "title"), False, False, 0)
    header.pack_start(masthead, True, True, 0)
    close = Gtk.Button(label="Close")
    close.set_valign(Gtk.Align.CENTER)
    close.connect("clicked", lambda *_: window.close())
    header.pack_end(close, False, False, 0)
    shell.pack_start(header, False, False, 0)
    shell.pack_start(label("Read-only SSH diagnostics · all configured hosts are monitored while this room is open.", "subtitle"), False, False, 0)
    if preview: shell.pack_start(label("PREVIEW / SYNTHETIC HOSTS & OBSERVATIONS · no connections or actions", "preview"), False, False, 0)
    content = Gtk.Box(spacing=16)
    shell.pack_start(content, True, True, 0)
    sidebar = box("sidebar", 9)
    sidebar.set_valign(Gtk.Align.FILL)
    side_header = label("HOSTS / 0", "eyebrow")
    sidebar.pack_start(side_header, False, False, 0)
    host_list = Gtk.ListBox()
    host_list.get_accessible().set_name("Configured SSH hosts and observation states")
    host_list.get_style_context().add_class("host-list")
    host_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
    host_scroll = Gtk.ScrolledWindow()
    host_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    host_scroll.add(host_list)
    sidebar.pack_start(host_scroll, True, True, 0)
    sidebar_note=label("Health names describe the observation channel. Authentication failure does not establish that a server is offline.", "muted", 25)
    sidebar.pack_start(sidebar_note,False,False,0)
    content.pack_start(sidebar, False, True, 0)
    detail_scroll = Gtk.ScrolledWindow()
    detail_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    detail = box("workbench", 13)
    detail.set_valign(Gtk.Align.START)
    detail_scroll.add(detail)
    content.pack_start(detail_scroll, True, True, 0)
    selected_header = Gtk.Box(spacing=12)
    selected_text = box(spacing=4)
    selected_name, selected_target = label("Select a system", "title"), label("No host selected", "target")
    selected_text.pack_start(selected_name, False, False, 0)
    selected_text.pack_start(selected_target, False, False, 0)
    selected_header.pack_start(selected_text, True, True, 0)
    ssh_button = Gtk.Button(label="Open SSH")
    ssh_button.set_valign(Gtk.Align.CENTER)
    ssh_button.set_tooltip_text("Open an interactive SSH terminal for this selected host. No management command is sent.")
    selected_header.pack_end(ssh_button, False, False, 0)
    detail.pack_start(selected_header, False, False, 0)
    observation = box("observation", 5)
    observed_state, observed_note = label("No observations yet", "state"), label("", "muted")
    observation.pack_start(observed_state, False, False, 0)
    observation.pack_start(observed_note, False, False, 0)
    detail.pack_start(observation, False, False, 0)
    stat_grid = Gtk.Grid(column_spacing=14, row_spacing=8)
    stat_grid.set_column_homogeneous(True)
    stats = {}
    for index, (key, title) in enumerate((("cpu", "CPU"), ("memory", "RAM"), ("swap", "SWAP"), ("uptime", "UPTIME"))):
        panel = box("stat", 3)
        panel.pack_start(label(title, "eyebrow"), False, False, 0)
        value, context = label("—", "value"), label("Not observed", "muted", 24)
        panel.pack_start(value, False, False, 0)
        panel.pack_start(context, False, False, 0)
        stat_grid.attach(panel, index % 2, index // 2, 1, 1)
        stats[key] = (value, context)
    detail.pack_start(stat_grid, False, False, 0)
    freshness = label("", "freshness")
    detail.pack_start(freshness, False, False, 0)

    palette = {"cpu": ACCENT2, "ram": PURPLE, "swap": WARNING, "load1": ACCENT2, "load5": PURPLE, "load15": WARNING, "rx": ACCENT2, "tx": SUCCESS, "read": PURPLE, "write": WARNING}

    class Chart(Gtk.DrawingArea):
        def __init__(self, keys, fixed_max=None, rate=False):
            super().__init__()
            self.keys, self.fixed_max, self.rate = keys, fixed_max, rate
            self.set_size_request(120, 145)
            self.connect("draw", self.draw)

        def text(self, cr, text, x, y, color=MUTED):
            layout = self.create_pango_layout(text)
            font = self.get_pango_context().get_font_description().copy()
            font.set_family(FONT_MONO)
            font.set_size(max(8 * Pango.SCALE, int(font.get_size() * .8)))
            layout.set_font_description(font)
            cr.set_source_rgba(*rgb(color), 1)
            cr.move_to(x, y)
            PangoCairo.show_layout(cr, layout)

        def draw(self, widget, cr):
            width, height = self.get_allocated_width(), self.get_allocated_height()
            history = list(model.histories.get(model.selected, []))
            actual = [row for row in history if not row.get("gap")]
            left, right, top, bottom = 42, width-8, 22, height-28
            values = [row[key] for row in actual for key in self.keys if number(row.get(key)) is not None]
            if not values:
                self.text(cr,"No observed samples",8,top+28)
                return False
            maximum = self.fixed_max or max([1, *values]) * 1.15
            for fraction in (0, .5, 1):
                y = bottom - (bottom-top)*fraction
                cr.set_source_rgba(*rgb(LINE), .7)
                cr.set_line_width(1)
                cr.move_to(left, y); cr.line_to(right, y); cr.stroke()
            self.text(cr, amount(maximum, "B/s") if self.rate else f"{maximum:g}", 0, 0)
            self.text(cr, "0", 10, bottom-7)
            start, end = history[0]["time"], history[-1]["time"]
            duration = max(1, end-start)
            state = (model.hosts.get(model.selected) or {}).get("state")
            for key in self.keys:
                cr.set_source_rgba(*rgb(palette[key]), 1 if state == "online" else .5)
                cr.set_line_width(1.7)
                previous = None
                for row in history:
                    value = number(row.get(key))
                    if row.get("gap") or value is None:
                        previous = None
                        continue
                    x = (left+right)/2 if end == start else left+(right-left)*(row["time"]-start)/duration
                    y = bottom-(bottom-top)*max(0,min(1,value/maximum))
                    if previous and row["time"]-previous[0] <= 6:
                        cr.move_to(previous[1],previous[2]);cr.line_to(x,y);cr.stroke()
                    cr.arc(x,y,1.9,0,math.tau);cr.fill()
                    previous = (row["time"],x,y)
            caption=f"{len(actual)} observed sample"+("s" if len(actual)!=1 else "")
            if len(actual)>1:caption+=f" / {max(0,int(end-start))}s"
            self.text(cr,caption,left,height-18)
            return False

    def rgb(color): return tuple(int(color[index:index+2],16)/255 for index in (1,3,5))

    charts = []
    chart_grid = Gtk.Grid(column_spacing=12, row_spacing=12)
    chart_grid.set_column_homogeneous(True)
    for title, keys, legend, fixed, rate in (
        ("Compute / percent", ("cpu","ram","swap"), "CPU · RAM · Swap", 100, False),
        ("Load / average tasks", ("load1","load5","load15"), "1 min · 5 min · 15 min", None, False),
        ("Network / throughput", ("rx","tx"), "Receive · Transmit", None, True),
        ("Storage / throughput", ("read","write"), "Read · Write", None, True)):
        panel = box("chart", 4)
        panel.pack_start(label(title,"heading"),False,False,0)
        chart = Chart(keys, fixed, rate)
        panel.pack_start(chart,False,False,0)
        legend_row = Gtk.Box(spacing=10)
        for key, text in zip(keys,legend.split(" · ")):
            tag = label(text,"muted")
            tag.override_color(Gtk.StateFlags.NORMAL, Gdk.RGBA(*rgb(palette[key]),1))
            legend_row.pack_start(tag,False,False,0)
        panel.pack_start(legend_row,False,False,0)
        charts.append((panel,chart))
    detail.pack_start(chart_grid,False,False,0)
    throughput = label("", "value")
    detail.pack_start(throughput,False,False,0)
    io_freshness=label("","freshness")
    detail.pack_start(io_freshness,False,False,0)

    class Evidence:
        def __init__(self,title,columns,height):
            self.panel = box("evidence",6)
            self.panel.pack_start(label(title,"heading"),False,False,0)
            self.note = label("Not observed","freshness")
            self.panel.pack_start(self.note,False,False,0)
            self.model = Gtk.ListStore(*([str]*len(columns)))
            self.view = Gtk.TreeView(model=self.model)
            self.view.get_accessible().set_name(title+" observed evidence")
            self.view.get_selection().set_mode(Gtk.SelectionMode.NONE)
            for index,(name,numeric) in enumerate(columns):
                renderer = Gtk.CellRendererText()
                renderer.set_property("family",FONT_MONO if numeric else FONT_BODY)
                renderer.set_property("xalign",1 if numeric else 0)
                renderer.set_property("ellipsize",Pango.EllipsizeMode.END)
                column = Gtk.TreeViewColumn(name,renderer,text=index)
                column.set_resizable(True)
                column.set_expand(not numeric and name not in ("State",))
                column.set_min_width({"PID":65,"CPU":72,"RAM":100,"Used":100,"Available":100,"Total":100,"Use":72,"State":96,"Status":190,"Description":200}.get(name,140))
                self.view.append_column(column)
            scroll = Gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.AUTOMATIC,Gtk.PolicyType.AUTOMATIC)
            scroll.set_min_content_height(height)
            scroll.set_max_content_height(height)
            scroll.add(self.view)
            self.panel.pack_start(scroll,False,False,0)
            detail.pack_start(self.panel,False,False,0)

        def update(self,rows,note):
            self.note.set_text(note)
            for index,row in enumerate(rows):
                if index<len(self.model):
                    for column,value in enumerate(row):
                        if self.model[index][column]!=str(value):self.model[index][column]=str(value)
                else:self.model.append([str(value) for value in row])
            while len(self.model)>len(rows):self.model.remove(self.model.iter_nth_child(None,len(self.model)-1))

    files = Evidence("Filesystems",(("Mount",False),("Total",True),("Used",True),("Available",True),("Use",True)),120)
    processes = Evidence("Top processes",(("Process",False),("PID",True),("CPU",True),("RAM",True)),175)
    services = Evidence("Failed services",(("Unit",False),("Description",False)),105)
    containers = Evidence("Containers",(("Name",False),("State",False),("Status",False)),125)
    metric_widgets=(stat_grid,freshness,chart_grid,throughput,io_freshness,files.panel,processes.panel,services.panel,containers.panel)
    detail.pack_start(label("Observed evidence only. This room provides no restart, kill, deployment or container-management actions.","muted"),False,False,0)
    host_rows = {}

    def freshness_note(group,now,field="updated_at"):
        observed = number(group.get(field))
        return age_text(now-observed) if observed is not None else "Freshness unavailable"

    def show_selected():
        row = model.hosts.get(model.selected)
        if not row:
            selected_name.set_text("No configured systems")
            selected_target.set_text("Add trusted SSH hosts through the configured inventory.")
            observed_state.set_text("No host selected")
            observed_note.set_text("No connection was attempted from this view.")
            state_class(observed_state,None);state_class(observation,None)
            for widget in metric_widgets:widget.set_visible(False)
            ssh_button.set_sensitive(False)
            for value,context in stats.values():value.set_text("—");context.set_text("Not observed")
            for evidence in (files,processes,services,containers):evidence.update([],"Not observed")
            freshness.set_text("");throughput.set_text("")
            for _,chart in charts:chart.queue_draw()
            return
        for widget in metric_widgets:widget.show_all()
        now = time.time()
        metrics = row.get("metrics") or {}
        mode = row.get("state","error")
        selected_name.set_text(str(row.get("label") or row["id"]))
        selected_target.set_text(str(row.get("target") or "Unknown target")+" / "+str(row.get("group") or "Systems"))
        observed_state.set_text(STATES.get(mode,"Unknown observation state")+" · "+age_text(row.get("age")))
        state_class(observed_state,mode);state_class(observation,mode)
        note = "Current observed values." if mode=="online" else "Last observed values; this is not a live reading." if metrics else "No authenticated observation is available."
        if row.get("error"):note+=" "+str(row["error"])
        group_errors=[name+": "+str(value["error"]) for name,value in metrics.items() if isinstance(value,dict) and value.get("error")]
        if group_errors:note+=" Unavailable observations · "+"; ".join(group_errors)
        observed_note.set_text(note)
        ssh_button.set_sensitive(preview or model.selected in runtime["hosts"])
        cpu,mem,swap = (metrics.get(name) or {} for name in ("cpu","memory","swap"))
        stats["cpu"][0].set_text(percent(cpu.get("percent")))
        stats["cpu"][1].set_text((str(cpu["cores"])+" logical cores") if cpu.get("cores") is not None else "Core count unavailable")
        for key,group in (("memory",mem),("swap",swap)):
            stats[key][0].set_text(percent(group.get("percent")))
            stats[key][1].set_text(amount(group.get("used_bytes"))+" / "+amount(group.get("total_bytes")))
        stats["uptime"][0].set_text(uptime_text(metrics.get("uptime_seconds")))
        load = metrics.get("load") or {}
        stats["uptime"][1].set_text("Load "+" / ".join("—" if number(load.get(name)) is None else f"{load[name]:.2f}" for name in ("one","five","fifteen")))
        freshness.set_text("CPU "+freshness_note(cpu,now)+" · RAM "+freshness_note(mem,now)+" · swap "+freshness_note(swap,now)+" · load "+freshness_note(load,now))
        net,disk = metrics.get("network") or {},metrics.get("disk") or {}
        throughput.set_text("RX "+amount(net.get("rx_bytes_per_second"),"B/s")+" / TX "+amount(net.get("tx_bytes_per_second"),"B/s")+"\nRead "+amount(disk.get("read_bytes_per_second"),"B/s")+" / Write "+amount(disk.get("write_bytes_per_second"),"B/s"))
        throughput.set_tooltip_text("Network "+freshness_note(net,now)+" · storage IO "+freshness_note(disk,now))
        interfaces=", ".join(str(name) for name in net.get("interfaces",[])) or "not observed"
        io_freshness.set_text("Network "+freshness_note(net,now)+" · storage IO "+freshness_note(disk,now)+"\nInterfaces: "+interfaces)
        for _,chart in charts:chart.queue_draw()
        files.update([(item.get("mount","—"),amount(item.get("total_bytes")),amount(item.get("used_bytes")),amount(item.get("available_bytes")),percent(item.get("percent"))) for item in disk.get("filesystems",[])],str(disk.get("error") or "Filesystem observation · "+freshness_note(disk,now,"filesystems_updated_at")))
        processes.update([(item.get("name","—"),item.get("pid","—"),percent(item.get("cpu_percent")),amount(item.get("memory_bytes"))) for item in metrics.get("processes",[])],"Process observation · "+freshness_note(metrics,now,"sampled_at"))
        for evidence,name,field in ((services,"services","failed"),(containers,"containers","items")):
            group = metrics.get(name) or {}
            items = group.get(field) or []
            if name=="services":rows=[(item.get("unit","—"),item.get("description","—")) for item in items]
            else:rows=[(item.get("name") or item.get("id","—"),item.get("state","—"),item.get("status","—")) for item in items]
            available = number(group.get("updated_at")) is not None
            note = str(group["error"]) if group.get("error") else ("No failed units reported" if name=="services" else "No container entries reported") if available and not items else "Observation"
            if not available:note="Not observed"+(" · "+str(group["error"]) if group.get("error") else "")
            evidence.update(rows,note+" · "+freshness_note(group,now))

    def select(_list,row):
        if row is None:return
        model.select(row.fleet_id)
        show_selected()
    host_list.connect("row-selected",select)

    def apply_snapshots(snapshots):
        if runtime["closed"]:return False
        model.update(snapshots)
        for identity in list(host_rows):
            if identity not in model.hosts:
                host_list.remove(host_rows.pop(identity)[0])
        for identity in model.order:
            record = model.hosts[identity]
            if identity not in host_rows:
                row=Gtk.ListBoxRow();row.fleet_id=identity;row.get_style_context().add_class("host-row")
                row_box=box(spacing=4)
                name=label("","host-name",23);target=label("","target",25);health=label("","state",25);age=label("","freshness",25)
                for widget in (name,target,health,age):
                    widget.set_line_wrap(False);widget.set_ellipsize(Pango.EllipsizeMode.END)
                for widget in (name,target,health,age):row_box.pack_start(widget,False,False,0)
                row.add(row_box);host_list.add(row)
                host_rows[identity]=(row,name,target,health,age)
                row.show_all()
            row,name,target,health,age=host_rows[identity]
            name.set_text(str(record.get("label") or identity))
            target.set_text(str(record.get("target") or "Unknown target"))
            target.set_tooltip_text(str(record.get("target") or "Unknown target"))
            health.set_text(LIST_STATES.get(record.get("state"),"Unknown state"));state_class(health,record.get("state"))
            health.set_tooltip_text(STATES.get(record.get("state"),"Unknown state")+(" · "+str(record["error"]) if record.get("error") else ""))
            age.set_text(age_text(record.get("age")))
        side_header.set_text(f"HOSTS / {len(model.order)}")
        if model.selected:host_list.select_row(host_rows[model.selected][0])
        show_selected()
        return False

    def open_ssh(*_):
        if preview:
            observed_note.set_text("Preview only: no SSH terminal or command was started.")
            return
        host=runtime["hosts"].get(model.selected)
        if host is None:return
        try:
            arguments=runtime["backend"].ssh_argv(host,interactive=True)
            subprocess.Popen(["kitty","--title","SSH · "+host.label,"--",*arguments],start_new_session=True)
        except (OSError,ValueError) as error:observed_note.set_text("Could not open the SSH terminal: "+str(error))
    ssh_button.connect("clicked",open_ssh)

    def apply_layout(compact):
        if runtime["closed"]:return False
        content.set_orientation(Gtk.Orientation.VERTICAL if compact else Gtk.Orientation.HORIZONTAL)
        sidebar.set_size_request(-1 if compact else 210,-1)
        host_scroll.set_min_content_height(200 if compact else 300)
        host_scroll.set_max_content_height(200 if compact else -1)
        sidebar_note.set_visible(not compact)
        for child in chart_grid.get_children():chart_grid.remove(child)
        for index,(panel,_) in enumerate(charts):
            chart_grid.attach(panel,0 if compact else index%2,index if compact else index//2,1,1)
            panel.show_all()
        content.queue_resize()
        return False

    def reflow(_window,allocation):
        line_height=window.create_pango_layout("M").get_pixel_size()[1]
        compact=allocation.width<max(860,line_height*46)
        if runtime["compact"]!=compact:
            runtime["compact"]=compact;GLib.idle_add(apply_layout,compact)
    window.connect("size-allocate",reflow)
    window.connect("key-press-event",lambda _w,event:(window.close() or True) if event.keyval==Gdk.KEY_Escape else False)

    def tick():
        if runtime["closed"]:return False
        snapshots=runtime["monitor"].snapshot()
        apply_snapshots(snapshots)
        try:runtime["backend"].publish_cache(snapshots)
        except (OSError,ValueError):pass
        return True

    def destroy(*_):
        runtime["closed"]=True
        if runtime["timer"]:GLib.source_remove(runtime["timer"])
        for source in runtime["signals"]:
            if GLib.MainContext.default().find_source_by_id(source):GLib.source_remove(source)
        if runtime["monitor"]:
            runtime["monitor"].stop()
            try:runtime["backend"].publish_cache(runtime["monitor"].snapshot())
            except (OSError,ValueError):pass
        Gtk.StyleContext.remove_provider_for_screen(Gdk.Screen.get_default(),provider)
        if Gtk.main_level():Gtk.main_quit()
    window.connect("destroy",destroy)
    window.fleet_ui={"model":model,"apply_snapshots":apply_snapshots,"host_rows":host_rows,"host_list":host_list,"detail_scroll":detail_scroll,
        "selected_name":selected_name,"state":observed_state,"note":observed_note,"ssh":ssh_button,"runtime":runtime,"charts":charts,
        "tables":{"files":files,"processes":processes,"services":services,"containers":containers}}
    window.show_all()
    if preview:
        apply_snapshots(fixture_snapshots())
        return window
    def terminate():
        window.destroy()
        return False
    for signum in (signal.SIGTERM,signal.SIGINT):
        runtime["signals"].append(GLib.unix_signal_add(GLib.PRIORITY_DEFAULT,signum,terminate))
    try:
        from . import fleet
        runtime["backend"]=fleet
        hosts=fleet.load_hosts()
        runtime["hosts"]={host.id:host for host in hosts}
        runtime["monitor"]=fleet.FleetMonitor(hosts,interval=fleet.load_interval())
        runtime["monitor"].start()
        tick()
        runtime["timer"]=GLib.timeout_add_seconds(2,tick)
    except (OSError,ValueError) as error:
        apply_snapshots([])
        observed_state.set_text("Inventory or monitor unavailable")
        observed_note.set_text(str(error))
    Gtk.main()
    return 0
