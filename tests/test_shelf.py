import unittest
import json
import os
import socket
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from rglauncher_linux.shelf import ShelfManager, ShelfState, in_shelf_region, logical_geometry, session_available


class ShelfPolicyTests(unittest.TestCase):
    def test_reveal_hide_hysteresis_and_popup_hold(self):
        state = ShelfState()
        self.assertTrue(state.enter(1))
        self.assertFalse(state.enter(1.1))
        self.assertFalse(state.should_hide(1.2, False, False))
        self.assertFalse(state.should_hide(2, False, True))
        self.assertFalse(state.should_hide(3, True, False))
        self.assertFalse(state.should_hide(4, False, False))
        self.assertFalse(state.should_hide(4.3, False, False))
        self.assertTrue(state.should_hide(4.6, False, False))

    def test_scaled_offset_and_rotated_outputs(self):
        monitor = {'x': -1280, 'y': 100, 'width': 2560, 'height': 1440, 'scale': 2}
        self.assertEqual(logical_geometry(monitor), (-1280, 100, 1280, 720))
        self.assertTrue(in_shelf_region(monitor, {'x': -10, 'y': 819}))
        self.assertFalse(in_shelf_region(monitor, {'x': 1, 'y': 819}))
        self.assertFalse(in_shelf_region(monitor, {'x': -10, 'y': 500}))
        monitor['transform'] = 1
        self.assertEqual(logical_geometry(monitor), (-1280, 100, 720, 1280))

    def test_native_popup_notifications_require_managed_child_credentials(self):
        # Real Unix peer credentials, without GTK or a foreground menu.
        with tempfile.TemporaryDirectory() as directory:
            manager = ShelfManager.__new__(ShelfManager)
            manager.socket = socket.socket(socket.AF_UNIX)
            address = str(Path(directory)/'shelf.sock');manager.socket.bind(address);manager.socket.listen(2)
            manager.children = {'DP-1':SimpleNamespace(pid=os.getpid())}
            manager.states = {'DP-1':ShelfState()};manager.native_menus={'DP-1':set()};manager.show=Mock()
            def request(command,menu='1'):
                with socket.socket(socket.AF_UNIX) as client:
                    client.connect(address)
                    client.sendall(json.dumps({'command':command,'output':'DP-1','menu':menu}).encode())
                    manager._command()
                    return json.loads(client.recv(4096))
            try:
                self.assertNotIn('error',request('popup-open'))
                self.assertEqual(manager.native_menus['DP-1'],{'1'});manager.show.assert_called_once_with('DP-1')
                request('popup-close');self.assertEqual(manager.native_menus['DP-1'],set())
                manager.children['DP-1'].pid += 1
                self.assertIn('error',request('popup-open'))
                self.assertEqual(manager.native_menus['DP-1'],set())
            finally:manager.socket.close()


if __name__ == '__main__':
    unittest.main()
