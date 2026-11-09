"""Observed-history/state semantics and an action-free native fleet fixture."""
import copy
import math
import os
from pathlib import Path
import subprocess
import sys
import unittest

from rglauncher_linux.fleet_ui import FleetViewModel, amount, age_text, fixture_snapshots, number, percent, uptime_text


class FleetModelTests(unittest.TestCase):
    def test_unknown_zero_and_unrepresentable_values_are_distinct(self):
        self.assertEqual(amount(None),"—")
        self.assertEqual(amount(0),"0 B")
        self.assertEqual(percent(0),"0.0%")
        for value in (True,"4",float("nan"),float("inf"),10**400):self.assertIsNone(number(value))
        self.assertEqual(age_text(None),"Not observed")
        self.assertEqual(age_text(23),"23s ago")
        self.assertEqual(uptime_text(86400),"1d 00h")

    def test_host_selection_and_order_are_stable_when_snapshots_reorder(self):
        model=FleetViewModel();rows=fixture_snapshots(100)
        model.update(rows,100);model.select("studio")
        model.update(list(reversed(rows)),102)
        self.assertEqual(model.order,["atlas","relay","studio","edge"])
        self.assertEqual(model.selected,"studio")
        model.update(rows[:2],104)
        self.assertEqual(model.selected,"atlas")

    def test_initial_and_cached_samples_are_real_points_without_invented_history(self):
        model=FleetViewModel();rows=fixture_snapshots(100)
        model.update(rows,100)
        self.assertEqual(len(model.histories["atlas"]),1)
        self.assertEqual(len(model.histories["relay"]),1)
        self.assertEqual(model.histories["relay"][0]["time"],77)
        self.assertEqual(len(model.histories["studio"]),0)
        model.update(rows,102)
        self.assertEqual(len(model.histories["atlas"]),1)

    def test_stale_transition_breaks_series_and_history_is_bounded(self):
        model=FleetViewModel();row=fixture_snapshots(100)[0]
        model.update([row],100)
        stale=copy.deepcopy(row);stale["state"]="stale";stale["age"]=9
        model.update([stale],109)
        self.assertTrue(model.histories["atlas"][-1]["gap"])
        model.update([stale],111)
        self.assertEqual(len(model.histories["atlas"]),2)
        for index in range(130):
            current=copy.deepcopy(row);current["observed_at"]=112+index*2
            model.update([current],current["observed_at"])
        self.assertEqual(len(model.histories["atlas"]),120)

    def test_removed_hosts_release_history(self):
        model=FleetViewModel();model.update(fixture_snapshots(100),100)
        model.update([],102)
        self.assertIsNone(model.selected)
        self.assertEqual(model.histories,{})

    def test_cached_group_timestamps_are_not_marked_fresh(self):
        stale=fixture_snapshots(100)[1]
        self.assertEqual(stale["metrics"]["cpu"]["updated_at"],77)
        self.assertEqual(stale["metrics"]["disk"]["filesystems_updated_at"],73)

    def test_receiver_clock_rollback_begins_a_new_chart_era(self):
        model=FleetViewModel();row=fixture_snapshots(100)[0]
        model.update([row],100)
        row=copy.deepcopy(row);row["observed_at"]=50;row["metrics"]["cpu"]["percent"]=17
        model.update([row],50)
        self.assertEqual(len(model.histories["atlas"]),1)
        self.assertEqual(model.histories["atlas"][0]["cpu"],17)
        row["observed_at"]=52;model.update([row],52)
        self.assertEqual(len(model.histories["atlas"]),2)

    @unittest.skipUnless(os.environ.get("DISPLAY"),"An X11 offscreen backend is required")
    def test_native_fixture_never_loads_backend_or_executes_ssh_and_preserves_rows(self):
        program=r'''
import sys,time,copy
import gi
gi.require_version("Gtk","3.0")
from gi.repository import Gtk
from unittest.mock import patch
from rglauncher_linux.fleet_ui import main,fixture_snapshots
def deny(*args,**kwargs):raise AssertionError("Fixture attempted an external process")
def pump():
 until=time.monotonic()+.08
 while time.monotonic()<until:
  while Gtk.events_pending():Gtk.main_iteration_do(False)
  time.sleep(.003)
with patch("subprocess.Popen",deny),patch("subprocess.run",deny):
 w=main(window_class=Gtk.OffscreenWindow,run_loop=False)
 w.set_size_request(600,900);w.set_default_size(600,900);pump()
 ui=w.fleet_ui
 assert ui["runtime"]["monitor"] is None and ui["runtime"]["backend"] is None
 assert "rglauncher_linux.fleet" not in sys.modules
 rows=fixture_snapshots();objects={key:value[0] for key,value in ui["host_rows"].items()}
 ui["host_list"].select_row(objects["studio"])
 ui["apply_snapshots"](list(reversed(rows)));pump()
 assert ui["model"].selected=="studio"
 assert all(ui["host_rows"][key][0] is value for key,value in objects.items())
 assert "Authorization required" in ui["state"].get_text()
 assert "offline" not in ui["state"].get_text().lower()
 ui["ssh"].clicked()
 assert "no SSH" in ui["note"].get_text()
 assert ui["runtime"]["compact"] and w.get_allocated_width()==600
 ui["apply_snapshots"]([]);pump()
 assert not ui["ssh"].get_sensitive()
 assert not ui["charts"][0][0].get_mapped()
 w.destroy()
'''
        result=subprocess.run([sys.executable,"-B","-c",program],cwd=Path(__file__).resolve().parents[1],
                              env=dict(os.environ,GDK_BACKEND="x11"),capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    @unittest.skipUnless(os.environ.get("DISPLAY"),"An X11 offscreen backend is required")
    def test_runtime_starts_all_hosts_and_publishes_stopped_state_with_fake_backend(self):
        program=r'''
import sys,types,os,signal
import gi
gi.require_version("Gtk","3.0")
from gi.repository import Gtk,GLib
from unittest.mock import patch
from rglauncher_linux.fleet_ui import main,fixture_snapshots
events=[];cache=[]
host=types.SimpleNamespace(id="atlas",label="Atlas",target="atlas.example.invalid")
class Monitor:
 def __init__(self,hosts,interval):assert hosts==[host] and interval==2;self.stopped=False
 def start(self):events.append("start")
 def stop(self):events.append("stop");self.stopped=True
 def snapshot(self):
  value=fixture_snapshots()[:1]
  if self.stopped:value[0]["state"]="stopped"
  return value
backend=types.ModuleType("rglauncher_linux.fleet")
backend.load_hosts=lambda:[host];backend.load_interval=lambda:2;backend.FleetMonitor=Monitor
backend.publish_cache=lambda value:cache.append(value[0]["state"])
class Offscreen(Gtk.OffscreenWindow):
 def __init__(self,**kwargs):
  super().__init__(**kwargs);self.set_size_request(900,700)
  GLib.timeout_add(120,lambda:(os.kill(os.getpid(),signal.SIGTERM) or False))
def deny(*args,**kwargs):raise AssertionError("Fake runtime attempted external process")
with patch.dict(sys.modules,{"rglauncher_linux.fleet":backend}),patch("subprocess.Popen",deny),patch("subprocess.run",deny):
 main(window_class=Offscreen,run_loop=True)
assert events==["start","stop"],events
assert cache[0]=="online" and cache[-1]=="stopped",cache
'''
        result=subprocess.run([sys.executable,"-B","-c",program],cwd=Path(__file__).resolve().parents[1],
                              env=dict(os.environ,GDK_BACKEND="x11"),capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__=="__main__":unittest.main()
