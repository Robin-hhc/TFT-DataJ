import ctypes as c
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from mouse_shortcut import MouseEvent, MouseShortcut, released_button
from selection_tracker import MouseNotice
from app import Companion


class MouseShortcutTests(unittest.TestCase):
    def test_release_only_and_no_injected_clicks(self):
        event=MouseEvent();event.mouseData=1<<16
        self.assertEqual(released_button(0,0x020C,event),1)
        self.assertEqual(released_button(0,0x020B,event),0)
        self.assertEqual(released_button(-1,0x020C,event),0)
        event.mouseData=2<<16
        self.assertEqual(released_button(0,0x020C,event),2)
        event.flags=1
        self.assertEqual(released_button(0,0x020C,event),0)

    def test_hook_always_passes_input_through(self):
        user=Mock();user.CallNextHookEx.return_value=42;user.GetForegroundWindow.return_value=7
        obj=SimpleNamespace(user=user,handle=99,released=Mock())
        event=MouseEvent();event.mouseData=1<<16
        self.assertEqual(MouseShortcut.dispatch(obj,0,0x020C,c.addressof(event)),42)
        obj.released.emit.assert_called_once_with(1,7)
        obj.released.emit.reset_mock()
        self.assertEqual(MouseShortcut.dispatch(obj,0,0x0200,0),42)
        obj.released.emit.assert_not_called()

    def test_real_left_button_copies_notice_and_always_forwards_native_input(self):
        user = Mock(); user.CallNextHookEx.return_value = 42; user.GetForegroundWindow.return_value = 7
        obj = SimpleNamespace(user=user, handle=99, released=Mock(), left_event=Mock(),
                              left_down=None, drag_notified=False)
        event = MouseEvent(); event.pt.x = 160; event.pt.y = 200
        with patch('mouse_shortcut.time.monotonic', return_value=10):
            self.assertEqual(MouseShortcut.dispatch(obj, 0, 0x0201, c.addressof(event)), 42)
        obj.left_event.emit.assert_called_once_with(MouseNotice('down', 160, 200, 10, 7))
        obj.left_event.emit.reset_mock()
        with patch('mouse_shortcut.time.monotonic', return_value=10.1):
            self.assertEqual(MouseShortcut.dispatch(obj, 0, 0x0202, c.addressof(event)), 42)
        obj.left_event.emit.assert_called_once_with(MouseNotice('up', 160, 200, 10.1, 7))
        self.assertEqual(user.CallNextHookEx.call_count, 2)

    def test_injected_left_negative_code_and_idle_motion_create_no_notice(self):
        user = Mock(); user.CallNextHookEx.return_value = 42
        obj = SimpleNamespace(user=user, handle=99, released=Mock(), left_event=Mock(),
                              left_down=None, drag_notified=False)
        event = MouseEvent(); event.flags = 1
        for code, message, data in ((0, 0x0201, c.addressof(event)),
                                    (-1, 0x0201, 0), (0, 0x0200, 0)):
            self.assertEqual(MouseShortcut.dispatch(obj, code, message, data), 42)
        obj.left_event.emit.assert_not_called()
        user.GetForegroundWindow.assert_not_called()

    def test_drag_notice_is_bounded_and_excursion_cannot_hide_on_return(self):
        user = Mock(); user.CallNextHookEx.return_value = 42; user.GetForegroundWindow.return_value = 7
        obj = SimpleNamespace(user=user, handle=99, released=Mock(), left_event=Mock(),
                              left_down=None, drag_notified=False)
        event = MouseEvent(); event.pt.x = 160; event.pt.y = 200
        MouseShortcut.dispatch(obj, 0, 0x0201, c.addressof(event))
        event.pt.x = 161
        MouseShortcut.dispatch(obj, 0, 0x0200, c.addressof(event))
        event.pt.x = 180
        MouseShortcut.dispatch(obj, 0, 0x0200, c.addressof(event))
        for x in (190, 170, 160):
            event.pt.x = x
            MouseShortcut.dispatch(obj, 0, 0x0200, c.addressof(event))
        MouseShortcut.dispatch(obj, 0, 0x0202, c.addressof(event))
        notices = [call.args[0] for call in obj.left_event.emit.call_args_list]
        self.assertEqual([notice.action for notice in notices], ['down', 'move', 'up'])
        self.assertEqual(notices[1].x, 180)
        self.assertEqual(user.GetForegroundWindow.call_count, 3)
        self.assertEqual(user.CallNextHookEx.call_count, 7)

    def test_notification_failure_cannot_swallow_mouse_input(self):
        user = Mock(); user.CallNextHookEx.return_value = 42; user.GetForegroundWindow.return_value = 7
        obj = SimpleNamespace(user=user, handle=99, released=Mock(), left_event=Mock(),
                              left_down=None, drag_notified=False)
        obj.left_event.emit.side_effect = RuntimeError('deleted receiver')
        event = MouseEvent()
        self.assertEqual(MouseShortcut.dispatch(obj, 0, 0x0201, c.addressof(event)), 42)
        user.CallNextHookEx.assert_called_once()

    def test_real_qt_queued_notice_runs_only_after_native_hook_has_returned(self):
        application = QApplication.instance() or QApplication([])
        obj = MouseShortcut()
        user = Mock(); user.CallNextHookEx.return_value = 42; user.GetForegroundWindow.return_value = 7
        obj.user = user; obj.handle = 99
        notices = []
        obj.left_event.connect(notices.append, Qt.ConnectionType.QueuedConnection)
        event = MouseEvent(); event.pt.x = 160; event.pt.y = 200
        with patch('mouse_shortcut.time.monotonic', return_value=10):
            self.assertEqual(obj.dispatch(0, 0x0201, c.addressof(event)), 42)
        self.assertEqual(notices, [])
        user.CallNextHookEx.assert_called_once()
        event.pt.x = 999  # Queued signal owns a copy, not native hook memory.
        application.processEvents()
        self.assertEqual(notices, [MouseNotice('down', 160, 200, 10, 7)])
        obj.handle = None

    def test_foreground_filter_busy_filter_and_debounce(self):
        target=SimpleNamespace(hwnd=7,process='MuMuNxDevice.exe',class_name='Qt5156QWindowIcon')
        panel=SimpleNamespace(mouse_button=Mock(),capture_pending=False,ocr_busy=False,
                              last_mouse_trigger=-1,binding=None,capture_once=Mock())
        panel.mouse_button.currentData.return_value=1
        with patch('app.win.foreground_root',return_value=7),patch('app.win.enumerate_mumu',return_value=[target]),patch('app.time.monotonic',return_value=10):
            Companion.mouse_capture(panel,2,7)
            Companion.mouse_capture(panel,1,8)
            panel.capture_once.assert_not_called()
            Companion.mouse_capture(panel,1,7)
            Companion.mouse_capture(panel,1,7)
            panel.capture_once.assert_called_once()
            panel.last_mouse_trigger=-1;panel.ocr_busy=True
            Companion.mouse_capture(panel,1,7)
            panel.capture_once.assert_called_once()
        panel.ocr_busy=False;panel.capture_once.reset_mock()
        with patch('app.win.foreground_root',return_value=9),patch('app.win.enumerate_mumu',return_value=[target]):
            Companion.mouse_capture(panel,1,9)
            panel.capture_once.assert_not_called()

    def test_launcher_ignored_and_stale_binding_can_rebind(self):
        target=SimpleNamespace(hwnd=7,process='MuMuNxDevice.exe',class_name='Qt5156QWindowIcon')
        launcher=SimpleNamespace(hwnd=8,process='MuMuNxMain.exe',class_name='Qt5156QWindowIcon')
        panel=SimpleNamespace(mouse_button=Mock(),capture_pending=False,ocr_busy=False,
                              last_mouse_trigger=-1,binding=SimpleNamespace(hwnd=99),capture_once=Mock())
        panel.mouse_button.currentData.return_value=1
        with patch('app.win.foreground_root',return_value=7),patch('app.win.enumerate_mumu',return_value=[target,launcher]),patch('app.win.describe',return_value=None),patch('app.win.same_target',return_value=False):
            Companion.mouse_capture(panel,1,7)
        panel.capture_once.assert_called_once()


if __name__=='__main__':unittest.main()
