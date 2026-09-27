"""Safety and geometry contract tests; no screenshots or game input."""
import unittest
from unittest.mock import patch
from dataclasses import replace
from win_capture import Binding, capture_block_reason, same_target
import win_capture

class CaptureGuardTest(unittest.TestCase):
    def setUp(self):
        self.bound = Binding(10, 20, "MuMuNxDevice.exe", "MuMu", "Qt", (-1920, 0, 0, 1080), (-1920, 0, 0, 1080), 144, False)

    def test_only_bound_foreground_is_captured(self):
        self.assertIsNone(capture_block_reason(self.bound, self.bound, 10))
        self.assertEqual(capture_block_reason(self.bound, self.bound, 11), "not_foreground")

    def test_reused_handle_is_rejected(self):
        self.assertFalse(same_target(self.bound, replace(self.bound, pid=21)))
        self.assertEqual(capture_block_reason(self.bound, None, 10), "target_changed_or_closed")

    def test_minimized_is_rejected(self):
        self.assertEqual(capture_block_reason(self.bound, replace(self.bound, minimized=True), 10), "minimized")

    def test_fullscreen_with_negative_monitor_coordinates(self):
        self.assertTrue(self.bound.fullscreen_geometry)
        self.assertFalse(replace(self.bound, rect=(-1900, 30, -10, 1060)).fullscreen_geometry)

    def test_mumu_fullscreen_tool_window_is_not_game(self):
        windows={10:self.bound,11:replace(self.bound,hwnd=11,class_name='Qt5156QWindowToolSaveBits')}
        def enumerate_windows(callback,_):
            for hwnd in windows:callback(hwnd,0)
        with patch.object(win_capture.user,'EnumWindows',side_effect=enumerate_windows), \
             patch.object(win_capture,'describe',side_effect=windows.get), \
             patch.object(win_capture.user,'GetWindowLongPtrW',side_effect=lambda hwnd,index:0x800a0 if hwnd==11 else 0):
            self.assertEqual([b.hwnd for b in win_capture.enumerate_mumu()],[10])

if __name__ == "__main__":
    unittest.main()
