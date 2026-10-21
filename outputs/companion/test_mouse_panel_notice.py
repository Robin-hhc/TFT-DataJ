"""Passive panel notices at the actual hook-to-Qt seam; no desktop input.

Only the Win32 query boundary is mocked. Native event structures, the hook
dispatcher, and Qt queued signal delivery are real. No hook is installed.
"""
import ctypes as c
from ctypes import wintypes as w
import importlib
import os
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from mouse_shortcut import MouseEvent, MouseShortcut
from selection_tracker import MouseNotice


class MousePanelNoticeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        self.hook = MouseShortcut()
        self.user = Mock()
        self.user.CallNextHookEx.return_value = 42
        self.user.GetForegroundWindow.return_value = 7
        self.user.WindowFromPoint.return_value = 11
        self.user.GetAncestor.return_value = 22
        self.user.GetWindowThreadProcessId.side_effect = self.write_other_pid
        self.hook.user = self.user
        # A sentinel is never registered with Windows. Tests call dispatch only.
        self.hook.handle = 99
        self.addCleanup(self.release_object)

    def release_object(self):
        self.hook.handle = None
        self.hook.deleteLater()
        self.qt.processEvents()

    @staticmethod
    def write_pid(pointer, pid):
        c.cast(pointer, c.POINTER(w.DWORD)).contents.value = pid
        return 123

    def write_other_pid(self, hwnd, pointer):
        return self.write_pid(pointer, os.getpid() + 1)

    def require_panel_api(self):
        self.assertTrue(hasattr(self.hook, 'panel_event'),
                        'The existing native hook must expose panel_event')
        self.assertTrue(callable(getattr(self.hook, 'set_panel_tracking', None)),
                        'Panel tracking must be explicitly enabled/disabled')
        return importlib.import_module('panel_dismissal').PanelMouseNotice

    @staticmethod
    def native_event(x=160, y=200, flags=0):
        event = MouseEvent()
        event.pt.x, event.pt.y, event.flags = x, y, flags
        return event

    def dispatch(self, message, event=None, code=0, at=10.0):
        event = event or self.native_event()
        with patch('mouse_shortcut.time.monotonic', return_value=at), \
                patch('mouse_shortcut.time.perf_counter', return_value=at):
            result = self.hook.dispatch(code, message, c.addressof(event))
        self.assertEqual(result, 42, 'Panel observation swallowed native input')
        return event

    def test_tracking_updates_only_flags_and_never_installs_another_hook(self):
        self.require_panel_api()
        self.hook.set_panel_tracking(True, blocked=True)
        self.hook.set_panel_tracking(False)
        self.hook.set_panel_tracking(True)
        self.assertEqual(self.user.mock_calls, [],
                         'Tracking changes must not install/query/uninstall a hook')
        self.assertEqual(self.hook.handle, 99)
        self.hook.handle = None
        self.hook.kernel = Mock()
        self.hook.kernel.GetModuleHandleW.return_value = 13
        self.user.SetWindowsHookExW.return_value = 88
        self.assertTrue(self.hook.start())
        self.assertTrue(self.hook.start())
        self.user.SetWindowsHookExW.assert_called_once()
        self.assertEqual(self.user.SetWindowsHookExW.call_args.args[0], 14)

    def test_closed_panel_skips_all_hit_queries_and_keeps_selection_notices(self):
        self.require_panel_api()
        panel, selection = [], []
        self.hook.panel_event.connect(panel.append)
        self.hook.left_event.connect(selection.append)
        self.hook.set_panel_tracking(False)
        self.dispatch(0x0201)
        self.dispatch(0x0200, self.native_event(180, 200))
        self.dispatch(0x0202, self.native_event(180, 200))
        self.assertEqual(panel, [])
        self.assertEqual([notice.action for notice in selection], ['down', 'move', 'up'])
        self.user.WindowFromPoint.assert_not_called()
        self.user.GetAncestor.assert_not_called()
        self.user.GetWindowThreadProcessId.assert_not_called()
        self.assertEqual(self.user.CallNextHookEx.call_count, 3)

    def test_owned_popup_is_inside_via_root_owner_process_identity(self):
        Notice = self.require_panel_api()
        notices = []
        self.hook.panel_event.connect(notices.append)
        self.hook.set_panel_tracking(True)
        self.user.GetWindowThreadProcessId.side_effect = (
            lambda hwnd, pointer: self.write_pid(pointer, os.getpid()))
        self.dispatch(0x0201)
        self.assertEqual(notices, [Notice('down', 160, 200, 10.0, True, False)])
        point = self.user.WindowFromPoint.call_args.args[0]
        self.assertEqual((point.x, point.y), (160, 200))
        self.user.GetAncestor.assert_called_once_with(11, 3)
        self.assertEqual(self.user.GetWindowThreadProcessId.call_args.args[0], 22)
        self.user.CallNextHookEx.assert_called_once()

    def test_other_root_owner_process_is_outside(self):
        Notice = self.require_panel_api()
        notices = []
        self.hook.panel_event.connect(notices.append)
        self.hook.set_panel_tracking(True)
        self.dispatch(0x0201)
        self.dispatch(0x0202, at=10.1)
        self.assertEqual(notices, [Notice('down', 160, 200, 10.0, False, False),
                                  Notice('up', 160, 200, 10.1, False, False)])
        self.assertEqual(self.user.CallNextHookEx.call_count, 2)

    def test_failed_hit_owner_or_pid_queries_emit_unknown_and_forward(self):
        self.require_panel_api()
        for failure in ('point', 'owner', 'thread', 'pid', 'exception'):
            with self.subTest(failure=failure):
                notices = []
                self.user.WindowFromPoint.return_value = 11
                self.user.WindowFromPoint.side_effect = None
                self.user.GetAncestor.return_value = 22
                self.user.GetWindowThreadProcessId.side_effect = self.write_other_pid
                if failure == 'point':
                    self.user.WindowFromPoint.return_value = 0
                elif failure == 'owner':
                    self.user.GetAncestor.return_value = 0
                elif failure == 'thread':
                    self.user.GetWindowThreadProcessId.side_effect = lambda hwnd, pointer: 0
                elif failure == 'pid':
                    self.user.GetWindowThreadProcessId.side_effect = lambda hwnd, pointer: 123
                else:
                    self.user.WindowFromPoint.side_effect = OSError('native hit query unavailable')
                self.hook.panel_event.connect(notices.append)
                self.hook.set_panel_tracking(True)
                try:
                    self.dispatch(0x0201)
                    self.assertEqual(len(notices), 1)
                    self.assertIsNone(notices[0].inside,
                                      'Unknown native ownership must not count as outside')
                finally:
                    self.hook.panel_event.disconnect(notices.append)
        self.assertEqual(self.user.CallNextHookEx.call_count, 5)

    def test_queued_notices_copy_native_memory_and_snapshot_blocked_state(self):
        Notice = self.require_panel_api()
        panel, selection, delivery_forwarded = [], [], []
        def accept_panel(notice):
            delivery_forwarded.append(self.user.CallNextHookEx.call_count == 1)
            panel.append(notice)
        self.hook.panel_event.connect(accept_panel, Qt.ConnectionType.QueuedConnection)
        self.hook.left_event.connect(selection.append, Qt.ConnectionType.QueuedConnection)
        self.hook.set_panel_tracking(True, blocked=True)
        event = self.dispatch(0x0201)
        self.assertEqual(panel, [])
        self.assertEqual(selection, [])
        self.user.CallNextHookEx.assert_called_once()
        event.pt.x, event.pt.y = 999, 888
        self.hook.set_panel_tracking(False, blocked=False)
        self.qt.processEvents()
        self.assertEqual(panel, [Notice('down', 160, 200, 10.0, False, True)])
        self.assertEqual(selection, [MouseNotice('down', 160, 200, 10.0, 7)])
        self.assertEqual(delivery_forwarded, [True])

    def test_bad_panel_receiver_cannot_swallow_input_or_remove_selection_notice(self):
        self.require_panel_api()
        selection = []
        self.hook.left_event.connect(selection.append)
        self.hook.set_panel_tracking(True)
        receiver = Mock()
        receiver.emit.side_effect = RuntimeError('deleted panel receiver')
        with patch.object(self.hook, 'panel_event', receiver):
            self.dispatch(0x0201)
        receiver.emit.assert_called_once()
        self.assertEqual(selection, [MouseNotice('down', 160, 200, 10.0, 7)])
        self.user.CallNextHookEx.assert_called_once()

    def test_injected_negative_idle_right_and_wheel_never_query_or_notify(self):
        self.require_panel_api()
        panel, selection = [], []
        self.hook.panel_event.connect(panel.append)
        self.hook.left_event.connect(selection.append)
        self.hook.set_panel_tracking(True)
        self.dispatch(0x0201, self.native_event(flags=1))
        self.dispatch(0x0202, self.native_event(flags=2))
        for code, message in ((-1, 0x0201), (0, 0x0200), (0, 0x0204),
                              (0, 0x0205), (0, 0x020A), (0, 0x020E)):
            self.assertEqual(self.hook.dispatch(code, message, 0), 42)
        self.assertEqual(panel, [])
        self.assertEqual(selection, [])
        self.user.WindowFromPoint.assert_not_called()
        self.user.GetAncestor.assert_not_called()
        self.user.GetWindowThreadProcessId.assert_not_called()
        self.user.GetForegroundWindow.assert_not_called()
        self.assertEqual(self.user.CallNextHookEx.call_count, 8)

    def test_drag_excursion_notices_stay_bounded_and_preserve_selection_stream(self):
        self.require_panel_api()
        panel, selection = [], []
        self.hook.panel_event.connect(panel.append)
        self.hook.left_event.connect(selection.append)
        self.hook.set_panel_tracking(True)
        self.dispatch(0x0201)
        for x in (161, 180, 190, 170, 160):
            self.dispatch(0x0200, self.native_event(x, 200))
        self.dispatch(0x0202)
        self.assertEqual([notice.action for notice in panel], ['down', 'move', 'up'])
        self.assertEqual([notice.action for notice in selection], ['down', 'move', 'up'])
        self.assertEqual([(notice.x, notice.y) for notice in panel],
                         [(160, 200), (180, 200), (160, 200)])
        self.assertEqual(self.user.WindowFromPoint.call_count, 3,
                         'Every mouse movement must not trigger ownership queries')
        self.assertEqual(self.user.CallNextHookEx.call_count, 7)


if __name__ == '__main__':
    unittest.main()
