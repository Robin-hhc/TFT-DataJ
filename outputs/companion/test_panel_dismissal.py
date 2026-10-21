"""Public outside-click transactions and actual Qt popup/modal lifecycles.

Owned widgets stay outside the desktop and never install a native mouse hook.
Expected behaviour comes from docs/design/点击外部自动收起-20261012.md.
"""
import importlib
import importlib.util
import math
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QDialog, QMenu, QWidget


class PanelDismissalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('panel_dismissal'),
                             'The outside-click transaction module is not implemented')
        module = importlib.import_module('panel_dismissal')
        self.Notice = module.PanelMouseNotice
        self.now = 10.0
        self.time_patch = patch('panel_dismissal.time.perf_counter', side_effect=lambda: self.now)
        self.time_patch.start()
        self.parent = QWidget()
        self.parent.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.parent.move(-5000, -4000)
        self.parent.resize(320, 180)
        self.parent.show()
        self.qt.processEvents()
        self.collapse = Mock()
        self.controller = module.PanelDismissal(self.parent, self.collapse)
        self.widgets = []
        self.addCleanup(self.cleanup_controller)
        self.controller.set_open(True)
        self.assertTrue(self.controller.tracking)
        self.assertFalse(self.controller.blocked)

    def cleanup_controller(self):
        self.controller.shutdown()
        for widget in self.widgets:
            try:
                widget.close()
                widget.deleteLater()
            except RuntimeError:
                pass  # A lifecycle test may already have destroyed its widget.
        self.parent.close()
        self.parent.deleteLater()
        self.qt.processEvents()
        self.time_patch.stop()

    def advance(self, seconds=.01):
        self.now += seconds
        return self.now

    def mouse(self, action, *, x=160, y=200, inside=False, blocked=False, at=None):
        if at is None:
            at = self.advance()
        notice = self.Notice(action, x, y, at, inside, blocked)
        self.controller.on_mouse(notice)
        return notice

    def menu(self):
        menu = QMenu(self.parent)
        menu.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        menu.addAction('Owned test action')
        menu.move(-5000, -4000)
        self.widgets.append(menu)
        return menu

    def show_menu(self, menu):
        self.advance()
        menu.show()
        menu.move(-5000, -4000)
        self.qt.processEvents()
        self.assertTrue(menu.isVisible(), 'The real owned menu never opened')
        self.assertTrue(self.controller.blocked, 'Menu Show did not block outside dismissal')
        return self.now

    def hide_menu(self, menu):
        self.advance()
        menu.hide()
        self.qt.processEvents()
        self.assertFalse(menu.isVisible())
        self.assertFalse(self.controller.blocked, 'Menu Hide left a stale blocker')
        return self.now

    def test_complete_external_click_collapses_once_only_after_release(self):
        self.mouse('down', x=-160, y=-200)
        self.collapse.assert_not_called()
        self.mouse('up', x=-160, y=-200)
        self.collapse.assert_called_once_with()
        self.mouse('up', x=-160, y=-200)
        self.collapse.assert_called_once_with()

    def test_both_ends_must_be_known_external_and_unblocked(self):
        for down_inside, up_inside, down_blocked, up_blocked in (
                (True, False, False, False), (False, True, False, False),
                (None, False, False, False), (False, None, False, False),
                (False, False, True, False), (False, False, False, True)):
            with self.subTest(down_inside=down_inside, up_inside=up_inside,
                              down_blocked=down_blocked, up_blocked=up_blocked):
                self.mouse('down', inside=down_inside, blocked=down_blocked)
                self.mouse('up', inside=up_inside, blocked=up_blocked)
                self.collapse.assert_not_called()

    def test_eight_pixel_tolerance_accepts_release_within_threshold(self):
        self.mouse('down')
        self.mouse('up', x=168)
        self.collapse.assert_called_once_with()

    def test_excursion_over_eight_cannot_be_hidden_by_returning_to_origin(self):
        self.mouse('down')
        self.mouse('move', x=169)
        self.mouse('move', x=160)
        self.mouse('up')
        self.collapse.assert_not_called()
        self.mouse('down')
        self.mouse('up', x=160, y=209)
        self.collapse.assert_not_called()

    def test_orphan_and_out_of_order_release_cannot_complete_click(self):
        self.mouse('up')
        self.collapse.assert_not_called()
        down = self.mouse('down')
        self.advance()
        self.mouse('up', at=down.at - .001)
        self.mouse('up')
        self.collapse.assert_not_called()
        self.mouse('down')
        self.mouse('up')
        self.collapse.assert_called_once_with()

    def test_repeated_down_cancels_until_release_then_accepts_next_click(self):
        self.mouse('down')
        self.mouse('down')
        self.mouse('up')
        self.collapse.assert_not_called()
        self.mouse('down')
        self.mouse('up')
        self.collapse.assert_called_once_with()

    def test_invalid_or_nonfinite_notice_cancels_pending_click(self):
        for invalid in (None, object(),
                        self.Notice('right', 160, 200, 10.1, False, False),
                        self.Notice('up', math.nan, 200, 10.1, False, False),
                        self.Notice('up', 160, math.inf, 10.1, False, False),
                        self.Notice('up', 160, 200, math.nan, False, False),
                        self.Notice('up', 160, 200, math.inf, False, False)):
            with self.subTest(invalid=repr(invalid)):
                self.mouse('down')
                self.advance()
                self.controller.on_mouse(invalid)
                self.mouse('up')
                self.collapse.assert_not_called()

    def test_future_and_over_age_queue_notice_cancel_without_deferred_collapse(self):
        for lag in (-.001, .7501):
            with self.subTest(lag=lag):
                self.mouse('down')
                self.advance(1.0)
                self.mouse('up', at=self.now - lag)
                self.mouse('up')
                self.collapse.assert_not_called()

    def test_notice_at_queue_age_limit_is_accepted(self):
        down_at = self.advance(.1)
        self.advance(.75)
        self.mouse('down', at=down_at)
        self.mouse('up')
        self.collapse.assert_called_once_with()

    def test_reopen_rejects_old_down_and_up_from_previous_open_period(self):
        down = self.mouse('down')
        self.advance()
        self.controller.set_open(False)
        self.assertFalse(self.controller.tracking)
        self.advance()
        self.controller.set_open(True)
        self.assertTrue(self.controller.tracking)
        self.mouse('down', at=down.at)
        self.mouse('up')
        self.collapse.assert_not_called()
        self.mouse('down')
        self.mouse('up')
        self.collapse.assert_called_once_with()

    def test_disable_and_enable_drop_transaction_and_reject_old_queue(self):
        down = self.mouse('down')
        self.advance()
        self.controller.set_enabled(False)
        self.assertFalse(self.controller.tracking)
        self.mouse('up')
        self.advance()
        self.controller.set_enabled(True)
        self.assertTrue(self.controller.tracking)
        self.mouse('down', at=down.at)
        self.mouse('up')
        self.collapse.assert_not_called()
        self.mouse('down')
        self.mouse('up')
        self.collapse.assert_called_once_with()

    def test_idempotent_open_update_keeps_current_valid_transaction(self):
        self.mouse('down')
        self.advance()
        self.controller.set_open(True)
        self.mouse('up')
        self.collapse.assert_called_once_with()

    def test_actual_menu_show_hide_barrier_rejects_first_external_queue(self):
        transitions = QSignalSpy(self.controller.tracking_changed)
        self.mouse('down')
        menu = self.menu()
        opened = self.show_menu(menu)
        self.collapse.assert_not_called()
        self.mouse('up', blocked=True)
        hidden = self.hide_menu(menu)
        # At consumption the popup is gone; an old down must still be refused
        # even if its notification lacks the original blocked snapshot.
        self.mouse('down', at=(opened + hidden) / 2, blocked=False)
        self.mouse('up')
        self.collapse.assert_not_called()
        self.mouse('down', at=hidden)
        self.mouse('up')
        self.collapse.assert_not_called()
        self.mouse('down')
        self.mouse('up')
        self.collapse.assert_called_once_with()
        self.assertGreaterEqual(transitions.count(), 2)
        blocked_values = [bool(transitions.at(i)[1]) for i in range(transitions.count())]
        self.assertIn(True, blocked_values)
        self.assertFalse(blocked_values[-1])

    def test_actual_menu_action_still_receives_its_qt_click(self):
        menu = self.menu()
        action = menu.actions()[0]
        triggered = QSignalSpy(action.triggered)
        self.show_menu(menu)
        self.advance()
        QTest.mouseClick(menu, Qt.MouseButton.LeftButton,
                         pos=menu.actionGeometry(action).center())
        self.qt.processEvents()
        self.assertEqual(triggered.count(), 1,
                         'The lifecycle observer consumed the menu action click')
        self.collapse.assert_not_called()
        self.assertFalse(menu.isVisible())
        self.assertFalse(self.controller.blocked)

    def test_actual_modal_dialog_pauses_and_its_close_rejects_old_queue(self):
        dialog = QDialog(self.parent)
        dialog.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        dialog.setModal(True)
        dialog.move(-5000, -4000)
        self.widgets.append(dialog)
        self.mouse('down')
        opened = self.advance()
        dialog.show()
        dialog.move(-5000, -4000)
        self.qt.processEvents()
        self.assertTrue(dialog.isVisible())
        self.assertTrue(self.controller.blocked)
        self.mouse('up')
        self.collapse.assert_not_called()
        hidden = self.advance()
        dialog.hide()
        self.qt.processEvents()
        self.assertFalse(self.controller.blocked)
        self.mouse('down', at=(opened + hidden) / 2)
        self.mouse('up')
        self.collapse.assert_not_called()
        self.mouse('down')
        self.mouse('up')
        self.collapse.assert_called_once_with()

    def test_destroyed_menu_releases_blocker_without_replaying_click(self):
        menu = self.menu()
        self.show_menu(menu)
        self.mouse('down', blocked=True)
        self.advance()
        menu.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.qt.processEvents()
        self.assertFalse(self.controller.blocked,
                         'Destroyed popup kept outside dismissal permanently blocked')
        self.mouse('up')
        self.collapse.assert_not_called()
        self.mouse('down')
        self.mouse('up')
        self.collapse.assert_called_once_with()

    def test_initially_visible_popup_is_tracked_and_released_on_destruction(self):
        # A controller can be recreated while an existing owned popup is open;
        # its constructor must register the same destruction protection.
        self.controller.shutdown()
        menu = self.menu()
        self.advance()
        menu.show()
        menu.move(-5000, -4000)
        self.qt.processEvents()
        module = importlib.import_module('panel_dismissal')
        self.controller = module.PanelDismissal(self.parent, self.collapse)
        self.controller.set_open(True)
        self.assertTrue(self.controller.blocked)
        self.mouse('down')
        self.mouse('up')
        self.collapse.assert_not_called()
        self.advance()
        menu.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.qt.processEvents()
        self.assertFalse(self.controller.blocked)
        self.mouse('down')
        self.mouse('up')
        self.collapse.assert_called_once_with()

    def test_nested_native_dialog_suspension_has_entry_and_exit_queue_barriers(self):
        self.mouse('down')
        entered = self.advance()
        with self.controller.suspended():
            self.assertTrue(self.controller.blocked)
            self.mouse('up')
            self.advance()
            with self.controller.suspended():
                self.mouse('down')
                self.mouse('up')
                self.assertTrue(self.controller.blocked)
                self.advance()
            self.assertTrue(self.controller.blocked,
                            'Ending a nested native dialog released the outer scope')
            self.advance()
        exited = self.now
        self.assertFalse(self.controller.blocked)
        self.mouse('down', at=(entered + exited) / 2)
        self.mouse('up')
        self.collapse.assert_not_called()
        self.mouse('down')
        self.mouse('up')
        self.collapse.assert_called_once_with()

    def test_shutdown_inside_native_scope_remains_terminal_after_scope_exit(self):
        self.advance()
        with self.controller.suspended():
            self.assertTrue(self.controller.blocked)
            self.advance()
            self.controller.shutdown()
            self.assertFalse(self.controller.blocked)
            self.assertFalse(self.controller.tracking)
        self.assertFalse(self.controller.blocked)
        self.assertFalse(self.controller.tracking)
        self.advance()
        self.controller.set_open(True)
        self.mouse('down')
        self.mouse('up')
        self.collapse.assert_not_called()

    def test_shutdown_is_terminal_despite_reopen_enable_and_popup_events(self):
        self.mouse('down')
        self.advance()
        self.controller.shutdown()
        self.assertFalse(self.controller.tracking)
        self.assertFalse(self.controller.blocked)
        transitions = QSignalSpy(self.controller.tracking_changed)
        self.advance()
        self.controller.set_open(True)
        self.controller.set_enabled(True)
        self.mouse('up')
        self.mouse('down')
        self.mouse('up')
        menu = self.menu()
        self.advance()
        menu.show()
        menu.move(-5000, -4000)
        self.qt.processEvents()
        menu.hide()
        self.qt.processEvents()
        self.assertFalse(self.controller.tracking)
        self.assertFalse(self.controller.blocked)
        self.assertEqual(transitions.count(), 0, 'Shutdown observer restarted on later Qt events')
        self.collapse.assert_not_called()


if __name__ == '__main__':
    unittest.main()
