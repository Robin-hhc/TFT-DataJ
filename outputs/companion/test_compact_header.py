"""Compact shell controls remain usable without changing game or process state."""
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPoint, QRect, Qt, QUrl
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QPushButton, QScrollArea
from app import QApplication
import win_capture as win
import test_game_resource_inputs as fixtures


class CompactHeaderTests(unittest.TestCase):
    flush = fixtures.GameResourceInputTests.flush
    response = fixtures.GameResourceInputTests.response
    tearDown = fixtures.GameResourceInputTests.tearDown

    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        self.quit_patch = patch.object(self.qt, 'quit')
        self.quit = self.quit_patch.start()
        self.addCleanup(self.quit_patch.stop)
        with patch('app.win.enumerate_mumu', return_value=[]):
            fixtures.GameResourceInputTests.setUp(self)
        self.p.show()
        self.qt.processEvents()

    def control(self, accessible_name):
        found = [button for button in self.p.findChildren(QPushButton)
                 if button.accessibleName() == accessible_name]
        self.assertEqual(len(found), 1, accessible_name)
        return found[0]

    def wait_until(self, predicate, message):
        deadline = time.monotonic() + 5
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(predicate(), message)

    def test_collapse_and_mark_reopen_preserve_complete_game_plan_and_guide_scroll(self):
        p = self.p
        p.versions_loaded(['18.2a'])
        p.browser.set_filter('hex', fixtures.CATALOG['hex'][0], can_confirm=True)
        self.flush()
        p.browser.input_bar.confirm.click()
        p.browser.pick_sort.click()
        p.browser.sample.setCurrentIndex(p.browser.sample.findData(500))
        self.flush()
        p.select_comp('112')
        self.flush()
        p.navigation[1].click()
        p.browser.search.setFocus()
        QTest.keyClicks(p.browser.search, 'local filter')
        p.navigation[2].click()

        # A local document exercises real WebEngine scroll retention without
        # depending on a live guide, authentication or external page changes.
        loaded = QSignalSpy(p.web.loadFinished)
        # GuidePage permits about:blank and DataJ only. Populate the allowed
        # blank document locally instead of weakening its navigation policy.
        p.web.setUrl(QUrl('about:blank'))
        self.wait_until(lambda: any(loaded.at(i)[0] for i in range(loaded.count())),
                        'Local guide did not finish loading')
        p.web.page().runJavaScript("document.body.innerHTML='<h1>Local guide acceptance</h1>';"
                                   "document.body.style.height='4000px';window.scrollTo(0,420)")
        # WebEngine reports zoomed view pixels (the production zoom is 0.75),
        # while window.scrollTo uses CSS pixels. Require a meaningful offset.
        self.wait_until(lambda: p.web.page().scrollPosition().y() > 100,
                        'Local guide did not scroll')
        scroll = p.web.page().scrollPosition()
        scope = deepcopy(p.browser.scope)
        resources = p.selected_resources.events
        detail = deepcopy(p.comp_detail)
        game_id = p.session.session_id
        guide_url = p.guide_requested_url
        page_url = p.web.url()
        self.assertEqual([(event.kind, event.entity_id) for event in resources],
                         [('hex', '20778')])
        self.assertEqual(p.session.target, '112')
        self.assertEqual(p.browser.search.text(), 'local filter')
        self.assertEqual(p.browser.sort_mode, 'pick')
        self.assertEqual(p.browser.min_sample, 500)
        self.assertTrue(p.copy_button.isEnabled())
        self.assertEqual(p.tabs.currentIndex(), 2)
        self.assertTrue(p.web.isVisible())
        self.assertEqual(self.pending, [])
        query = QSignalSpy(p.browser.queryRequested)
        requests = len(self.calls)
        loads = loaded.count()
        p.mark.show()

        QTest.mouseClick(p.collapse_button, Qt.MouseButton.LeftButton)
        self.qt.processEvents()
        self.assertFalse(p.panel_open())
        self.assertTrue(p.mark.isVisible())
        self.assertIn('展开', p.mark.button.accessibleName())
        self.quit.assert_not_called()
        QTest.mouseClick(p.mark.button, Qt.MouseButton.LeftButton)
        self.qt.processEvents()

        self.assertTrue(p.panel_open())
        self.assertIn('收起', p.mark.button.accessibleName())
        self.assertEqual(p.session.session_id, game_id)
        self.assertEqual(p.session.target, '112')
        self.assertEqual(p.browser.pinned, '112')
        self.assertEqual(p.comp_detail, detail)
        self.assertTrue(p.copy_button.isEnabled())
        self.assertEqual(p.browser.search.text(), 'local filter')
        self.assertEqual(p.browser.scope, scope)
        self.assertEqual(p.browser.input_bar.condition, scope)
        self.assertEqual(p.selected_resources.events, resources)
        self.assertEqual(len(p.browser.input_bar.chips), 1)
        self.assertEqual(p.browser.sort_mode, 'pick')
        self.assertTrue(p.browser.pick_sort.isChecked())
        self.assertEqual(p.browser.min_sample, 500)
        self.assertEqual(p.browser.sample.currentData(), 500)
        self.assertEqual(p.tabs.currentIndex(), 2)
        self.assertTrue(p.web.isVisible())
        self.assertEqual(p.guide_requested_url, guide_url)
        self.assertEqual(p.web.url(), page_url)
        self.assertAlmostEqual(p.web.page().scrollPosition().y(), scroll.y(), delta=1)
        self.assertEqual(loaded.count(), loads, 'Reopening reloaded the guide')
        self.assertEqual(query.count(), 0, 'Reopening issued another comp query')
        self.assertEqual(len(self.calls), requests)
        self.assertEqual(self.pending, [])
        self.quit.assert_not_called()

    def test_refused_game_focus_keeps_panel_usable_and_pauses_automatic(self):
        p = self.p
        binding = win.Binding(hwnd=123, pid=456, process='MuMuNxDevice.exe',
                              title='Local focus boundary', class_name='test',
                              rect=(0, 0, 1920, 1080), monitor=(0, 0, 1920, 1080),
                              dpi=96, minimized=False)
        p.binding = binding
        p.automatic.setChecked(True)
        with patch('app.win.describe', return_value=binding), \
                patch('app.win.user.SetForegroundWindow', return_value=False) as focus, \
                patch('app.win.foreground_root', return_value=999):
            QTest.mouseClick(p.collapse_button, Qt.MouseButton.LeftButton)
            self.qt.processEvents()
        focus.assert_called_once_with(binding.hwnd)
        self.assertTrue(p.panel_open())
        self.assertFalse(p.automatic.isChecked())
        self.assertEqual(p.activity_code, 'return_failed')
        self.assertIn('Windows 未允许切回游戏', p.activity.text())
        self.assertIn(p.activity.text(), p.mark.button.toolTip())
        self.quit.assert_not_called()
        # The search remains a real usable input after the failed return.
        p.navigation[1].click()
        p.browser.search.setFocus()
        QTest.keyClicks(p.browser.search, 'still usable')
        self.assertEqual(p.browser.search.text(), 'still usable')
        self.assertTrue(p.browser.search.isEnabled())

    def test_rightmost_collapse_keeps_process_and_left_close_quits(self):
        collapse = self.control('收起助手')
        close = self.control('退出助手')
        self.assertFalse(collapse.icon().isNull())
        self.assertIn('收起', collapse.text())
        self.assertLess(close.mapTo(self.p, QPoint()).x(), collapse.mapTo(self.p, QPoint()).x())
        collapse.click()
        self.qt.processEvents()
        self.assertFalse(self.p.panel_open())
        self.quit.assert_not_called()
        self.p.show()
        close.click()
        self.quit.assert_called_once_with()

    def test_long_fixed_name_keeps_one_header_row_and_complete_tooltip(self):
        full = '本局阵容：' + '重装女警和黑暗仪式蜘蛛' * 12 + ' · 已固定'
        self.p.target_label.setText(full)
        self.p.resize(760, 430)
        self.qt.processEvents()
        self.assertEqual(self.p.target_label.toolTip(), full)
        self.assertIn('…', self.p.target_label.text())
        controls = [self.p.target_label, self.p.copy_button,
                    self.control('退出助手'), self.control('收起助手')]
        bounds = [QRect(widget.mapTo(self.p, QPoint()), widget.size()) for widget in controls]
        self.assertEqual((self.p.width(), self.p.height()), (760, 430))
        self.assertTrue(all(self.p.rect().contains(rect) for rect in bounds))
        self.assertLessEqual(max(rect.center().y() for rect in bounds)
                             - min(rect.center().y() for rect in bounds), 2)
        self.assertTrue(all(not first.intersects(second)
                            for index, first in enumerate(bounds) for second in bounds[index + 1:]))

    def test_latest_guide_fits_without_an_extra_outer_scrollbar(self):
        self.p.versions_loaded(['18.2a'])
        self.p.select_comp('112')
        self.flush()
        self.qt.processEvents()
        self.assertTrue(self.p.web.isVisible())
        outer = self.p.tabs.widget(2)
        self.assertIsInstance(outer, QScrollArea)
        self.assertEqual(outer.verticalScrollBar().maximum(), 0)
        self.assertGreaterEqual(self.p.web.height(), 180)


class CompactHeaderExitProcessTests(unittest.TestCase):
    def test_close_button_exits_real_event_loop_and_process(self):
        code = textwrap.dedent('''
            from pathlib import Path
            import sys
            from unittest.mock import patch
            import bootstrap
            bootstrap.STATE_DIR = Path(sys.argv[1])
            from app import QApplication, Companion
            from PySide6.QtCore import QTimer, Qt
            from PySide6.QtTest import QSignalSpy, QTest

            qt = QApplication([])
            qt.setQuitOnLastWindowClosed(False)
            with patch('app.win.enumerate_mumu', return_value=[]):
                panel = Companion(offline=True, offline_catalog={
                    'hex': [], 'hero': [], 'equip': [], 'trait': []})
            panel.timer.stop()
            qt.aboutToQuit.connect(panel.shutdown)
            clicks = QSignalSpy(panel.close_button.clicked)
            panel.show()
            def close_via_button():
                assert panel.panel_open(), 'Panel never opened'
                QTest.mouseClick(panel.close_button, Qt.MouseButton.LeftButton)
            QTimer.singleShot(50, close_via_button)
            QTimer.singleShot(5000, lambda: qt.exit(97))
            result = qt.exec()
            assert result == 0, ('Close button failed to quit', result)
            assert clicks.count() == 1, 'Close button was not clicked'
            assert not panel.timer.isActive() and not panel.mark.isVisible()
            print('CLOSE_BUTTON_EVENT_LOOP_EXITED', flush=True)
            raise SystemExit(result)
        ''')
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, '-X', 'utf8', '-c', code, directory],
                                    cwd=Path(__file__).parent, capture_output=True,
                                    text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('CLOSE_BUTTON_EVENT_LOOP_EXITED', result.stdout)


if __name__ == '__main__':
    unittest.main()
