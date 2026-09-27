import ctypes as c
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from mouse_shortcut import MouseEvent, MouseShortcut, released_button
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
