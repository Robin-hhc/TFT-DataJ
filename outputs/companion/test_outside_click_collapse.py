"""Outside clicks travel through the production hook and real Qt queue."""
import ctypes
import os
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtCore import Qt, QUrl
from PySide6.QtTest import QTest, QSignalSpy
from app import QApplication
from app import Companion
from mouse_shortcut import MouseEvent, MouseShortcut
import test_game_resource_inputs as fixtures


class OutsideClickCollapseTests(unittest.TestCase):
    flush = fixtures.GameResourceInputTests.flush
    response = fixtures.GameResourceInputTests.response
    tearDown = fixtures.GameResourceInputTests.tearDown

    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        with patch('app.win.enumerate_mumu', return_value=[]):
            fixtures.GameResourceInputTests.setUp(self)
        self.flush()
        self.mouse = MouseShortcut(self.p)
        self.user = Mock()
        self.user.CallNextHookEx.return_value = 42
        self.user.GetForegroundWindow.return_value = 777
        self.user.WindowFromPoint.return_value = 888
        self.user.GetAncestor.return_value = 888
        def process_id(hwnd, pointer):
            ctypes.cast(pointer, ctypes.POINTER(ctypes.wintypes.DWORD)).contents.value = os.getpid() + 1
            return 1
        self.user.GetWindowThreadProcessId.side_effect = process_id
        self.mouse.user = self.user
        self.p.connect_mouse(self.mouse)
        self.p.move(-5000, -4000)
        self.p.mark.move(-5000, -4500)
        self.p.mark.show()
        self.p.show()
        self.qt.processEvents()

    def native(self, message, x=160, y=200, flags=0):
        event = MouseEvent()
        event.pt.x, event.pt.y, event.flags = x, y, flags
        self.assertEqual(self.mouse.dispatch(0, message, ctypes.addressof(event)), 42)

    def javascript(self, script):
        result = []
        self.p.web.page().runJavaScript(script, result.append)
        deadline = time.monotonic() + 5
        while not result and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(result, 'Local guide JavaScript callback did not complete')
        return result[0]

    def test_external_click_collapses_on_qt_queue_and_never_takes_game_focus(self):
        p = self.p
        p.automatic.setChecked(True)
        binding = SimpleNamespace(hwnd=123, pid=456, process='MuMuNxDevice.exe')
        p.binding = binding
        with patch('app.win.describe', return_value=binding), \
                patch('app.win.user.SetForegroundWindow', return_value=True) as focus:
            self.native(0x0201)
            self.native(0x0202)
            self.assertTrue(p.panel_open(), 'Hook must return before changing Qt widgets')
            self.qt.processEvents()
            self.assertFalse(p.panel_open(), 'A complete outside click must collapse the panel')
            focus.assert_not_called()
        self.assertTrue(p.mark.isVisible())
        self.assertIn('展开', p.mark.button.accessibleName())
        self.assertTrue(p.automatic.isChecked())

    def owned_click(self):
        def owned(hwnd, pointer):
            ctypes.cast(pointer, ctypes.POINTER(ctypes.wintypes.DWORD)).contents.value = os.getpid()
            return 1
        self.user.GetWindowThreadProcessId.side_effect = owned
        self.native(0x0201)
        self.native(0x0202)
        self.qt.processEvents()

    def test_fast_click_with_identical_legacy_monotonic_ticks_still_collapses(self):
        # Python 3.12 Windows monotonic uses 15.625ms GetTickCount64 ticks.
        # A press/release can share that tick; panel sequencing needs its own
        # high-resolution clock while the established selection clock is kept.
        with patch('mouse_shortcut.time.monotonic', return_value=10.0):
            self.native(0x0201)
            self.native(0x0202)
            self.qt.processEvents()
        self.assertFalse(self.p.panel_open())

    def test_native_file_dialog_scope_blocks_clicks_and_discards_queued_release(self):
        notices = []
        self.mouse.panel_event.connect(notices.append)
        def dialog(*args):
            self.assertTrue(self.p.dismissal.blocked)
            self.native(0x0201)
            self.native(0x0202)
            return '', ''
        with patch('app.QFileDialog.getOpenFileName', side_effect=dialog):
            self.p.open_image()
        self.qt.processEvents()
        self.assertEqual([notice.blocked for notice in notices], [True, True])
        self.assertTrue(self.p.panel_open())
        self.assertFalse(self.p.dismissal.blocked)
        self.native(0x0201)
        self.native(0x0202)
        self.qt.processEvents()
        self.assertFalse(self.p.panel_open())

    def test_internal_controls_and_owned_child_window_do_not_collapse(self):
        self.user.WindowFromPoint.return_value = 111
        self.user.GetAncestor.return_value = 222
        self.owned_click()
        self.assertTrue(self.p.panel_open())
        self.user.GetAncestor.assert_any_call(111, 3)
        QTest.mouseClick(self.p.navigation[3], Qt.MouseButton.LeftButton)
        self.assertTrue(self.p.panel_open())
        self.assertEqual(self.p.tabs.currentIndex(), 3)

    def test_marker_opening_release_and_old_queued_click_cannot_close_new_panel(self):
        p = self.p
        p.hide()
        self.native(0x0201)
        QTest.mouseClick(p.mark.button, Qt.MouseButton.LeftButton)
        self.native(0x0202)
        self.qt.processEvents()
        self.assertTrue(p.panel_open(), 'Opening marker release collapsed its new panel')
        self.native(0x0201)
        self.native(0x0202)
        p.hide()
        p.show()
        self.qt.processEvents()
        self.assertTrue(p.panel_open(), 'A previous opening generation closed the new panel')

    def test_real_drag_excursion_then_return_to_start_does_not_collapse(self):
        self.native(0x0201)
        self.native(0x0200, x=190)
        self.native(0x0200)
        self.native(0x0202)
        self.qt.processEvents()
        self.assertTrue(self.p.panel_open())
        self.assertEqual(self.user.WindowFromPoint.call_count, 3)

    def test_setting_disables_mid_click_and_persists_without_changing_side_key(self):
        p = self.p
        self.assertTrue(p.outside_collapse.isChecked())
        side = p.mouse_button.currentData()
        self.native(0x0201)
        p.offline = False
        p.outside_collapse.setChecked(False)
        self.native(0x0202)
        self.qt.processEvents()
        self.assertTrue(p.panel_open())
        self.assertEqual(str(p.mouse_settings.value('outside_click_collapse')), '0')
        with patch.object(Companion, 'load_versions'), patch('app.win.enumerate_mumu', return_value=[]):
            other = Companion(offline=False)
        try:
            other.timer.stop()
            self.assertFalse(other.outside_collapse.isChecked(), 'Disabled preference was not restored')
        finally:
            other.shutdown()
            other.deleteLater()
        p.outside_collapse.setChecked(True)
        self.assertEqual(str(p.mouse_settings.value('outside_click_collapse')), '1')
        self.assertEqual(p.mouse_button.currentData(), side)
        self.native(0x0202)
        self.qt.processEvents()
        self.assertTrue(p.panel_open(), 'A release from before re-enabling was treated as a fresh click')
        self.native(0x0201)
        self.native(0x0202)
        self.qt.processEvents()
        self.assertFalse(p.panel_open())

    def test_passive_collapse_preserves_plan_query_and_local_guide_scroll(self):
        p = self.p
        p.versions_loaded(['18.2a'])
        p.browser.set_filter('hex', fixtures.CATALOG['hex'][0], can_confirm=True)
        self.flush()
        p.browser.input_bar.confirm.click()
        p.select_comp('112')
        self.flush()
        p.browser.pick_sort.click()
        p.browser.sample.setCurrentIndex(p.browser.sample.findData(500))
        self.flush()
        p.browser.search.setText('saved search')
        p.navigation[2].click()
        loaded = QSignalSpy(p.web.loadFinished)
        p.web.setUrl(QUrl('about:blank'))
        deadline = time.monotonic() + 5
        # Setting the already current about:blank URL need not emit another
        # loadFinished. Verify the actual document before testing retention.
        ready = False
        while time.monotonic() < deadline:
            ready = self.javascript("location.href==='about:blank' && document.readyState==='complete'")
            if ready:break
            QTest.qWait(10)
        self.assertTrue(ready, 'Local guide document was not ready')
        self.assertEqual(self.javascript("document.body.innerHTML='<h1>Outside click guide acceptance</h1>';"
                         "document.body.style.height='4000px';window.scrollTo(0,420);"
                         "document.body.innerText"), 'Outside click guide acceptance')
        deadline = time.monotonic() + 5
        while p.web.page().scrollPosition().y() <= 100 and time.monotonic() < deadline:
            QTest.qWait(10)
        scroll = p.web.page().scrollPosition().y()
        self.assertGreater(scroll, 100)
        self.flush()
        state = (p.session.session_id, p.session.target, p.browser.scope,
                 p.selected_resources.events, p.guide_requested_url, p.web.url(), p.comp_detail)
        requests = len(self.calls)
        loads = loaded.count()
        self.native(0x0201)
        self.native(0x0202)
        self.qt.processEvents()
        self.assertFalse(p.panel_open())
        QTest.mouseClick(p.mark.button, Qt.MouseButton.LeftButton)
        self.qt.processEvents()
        self.assertTrue(p.panel_open())
        self.assertEqual((p.session.session_id, p.session.target, p.browser.scope,
                          p.selected_resources.events, p.guide_requested_url, p.web.url(), p.comp_detail), state)
        self.assertEqual(p.browser.search.text(), 'saved search')
        self.assertEqual(p.browser.sort_mode, 'pick')
        self.assertEqual(p.browser.min_sample, 500)
        self.assertEqual(p.tabs.currentIndex(), 2)
        self.assertAlmostEqual(p.web.page().scrollPosition().y(), scroll, delta=1)
        self.assertEqual(loaded.count(), loads, 'Reopening reloaded the guide')
        self.assertEqual(self.javascript('document.body.innerText'), 'Outside click guide acceptance')
        self.assertEqual(len(self.calls), requests, 'Reopening made another HTTP request')
        self.assertEqual(self.pending, [])

    def test_focus_change_without_click_and_shutdown_are_safe(self):
        from PySide6.QtCore import QEvent
        QApplication.sendEvent(self.p, QEvent(QEvent.Type.WindowDeactivate))
        self.assertTrue(self.p.panel_open())
        self.native(0x0201)
        self.native(0x0202)
        self.p.shutdown()
        self.qt.processEvents()
        self.assertTrue(self.p.panel_open(), 'Queued click ran after shutdown')
        self.assertFalse(self.mouse.panel_tracking)

    def test_hidden_to_minimized_never_enables_external_hit_tracking(self):
        self.p.hide()
        self.p.showMinimized()
        self.qt.processEvents()
        self.assertFalse(self.p.panel_open())
        self.assertFalse(self.mouse.panel_tracking)
        self.assertIn('展开', self.p.mark.button.accessibleName())
        self.p.showNormal()
        self.qt.processEvents()
        self.assertTrue(self.p.panel_open())
        self.assertTrue(self.mouse.panel_tracking)

    def test_first_fresh_click_after_expired_queued_release_is_accepted(self):
        self.native(0x0201)
        self.qt.processEvents()
        self.native(0x0202)
        with patch('panel_dismissal.time.perf_counter', return_value=time.perf_counter() + 2):
            self.qt.processEvents()
        self.assertTrue(self.p.panel_open())
        self.native(0x0201)
        self.native(0x0202)
        self.qt.processEvents()
        self.assertFalse(self.p.panel_open(), 'Expired release left a held-button flag behind')


if __name__ == '__main__':
    unittest.main()
