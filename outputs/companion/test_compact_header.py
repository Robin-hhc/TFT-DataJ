"""Compact shell controls remain usable without changing game or process state."""
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QPushButton, QScrollArea
from app import QApplication
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


if __name__ == '__main__':
    unittest.main()
