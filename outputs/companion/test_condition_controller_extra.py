"""Actual Qt input state survives failures and rejects obsolete side-key work."""
from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch, ANY

from PIL import Image
from app import QApplication
from entity_identity import EntityResolver
import test_game_resource_inputs as fixtures


class ConditionControllerExtraTests(unittest.TestCase):
    # Reuse only fixture helpers. Importing/inheriting the fixture TestCase itself
    # would make unittest collect its unrelated tests a second time.
    response = fixtures.GameResourceInputTests.response
    flush = fixtures.GameResourceInputTests.flush
    tearDown = fixtures.GameResourceInputTests.tearDown

    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        fixtures.GameResourceInputTests.setUp(self)
        self.flush()
        self.binding = SimpleNamespace(hwnd=7, pid=1, process='MuMuNxDevice.exe',
                                       rect=(0, 0, 1920, 1080), dpi=96)
        self.current_binding = self.binding
        self.foreground = 7
        self.p.binding = self.binding
        self.frame = Image.new('RGB', (1920, 1080))
        self.capture = Mock(return_value=(self.frame, self.binding))
        self.reader = Mock()
        self.reader.read.return_value = {'route': 'detail', 'status': 'resolved',
                                         'entity': fixtures.CATALOG['hex'][0], 'candidates': []}
        self.p.conditions.reader = self.reader
        self.stack.enter_context(patch('condition_controller.win.describe', side_effect=lambda _: self.current_binding))
        self.stack.enter_context(patch('condition_controller.win.foreground_root', side_effect=lambda: self.foreground))
        self.stack.enter_context(patch('condition_controller.QTimer.singleShot', side_effect=lambda _, fn: fn()))
        self.stack.enter_context(patch('condition_controller.capture_image', self.capture))
        self.stack.enter_context(patch.object(self.p, 'panel_open', return_value=False))
        self.expanded = self.stack.enter_context(patch.object(self.p, 'showNormal'))
        self.raised = self.stack.enter_context(patch.object(self.p, 'raise_'))
        self.activated = self.stack.enter_context(patch.object(self.p, 'activateWindow'))

    def run_one(self):
        self.assertTrue(self.pending, 'Expected an actual queued Companion job')
        function, done, failed = self.pending.pop(0)
        try:
            result = function()
        except Exception as exc:
            failed(str(exc))
        else:
            done(result)

    def queued_ocr(self):
        self.p.conditions.trigger()
        self.assertEqual(len(self.pending), 1)
        self.assertFalse(self.expanded.called)
        self.run_one()  # one capture; the existing OCR pool now contains its job
        self.capture.assert_called_once_with(self.binding)
        self.assertEqual(len(self.pending), 1)
        self.assertTrue(self.p.ocr_busy)
        self.assertFalse(self.expanded.called)

    def assert_no_accepted_input(self):
        self.assertEqual(self.p.selected_resources.events, ())
        self.assertFalse(self.expanded.called)
        self.assertFalse(self.raised.called)
        self.assertFalse(self.activated.called)

    def test_closed_game_between_capture_and_ocr_does_not_change_current_condition(self):
        p = self.p
        p.browser.set_filter('equip', fixtures.CATALOG['equip'][0]); self.flush()
        before = deepcopy(p.browser.scope)
        self.queued_ocr()
        self.current_binding = None
        self.run_one()
        self.assertEqual(p.browser.scope, before)
        self.assertFalse(p.ocr_busy)
        self.assert_no_accepted_input()

    def test_geometry_or_dpi_change_after_capture_rejects_queued_result(self):
        for change in ({'rect': (20, 0, 1940, 1080)}, {'dpi': 120}):
            with self.subTest(change=change):
                self.current_binding = self.binding
                self.capture.reset_mock()
                self.queued_ocr()
                self.current_binding = SimpleNamespace(**{**vars(self.binding), **change})
                self.run_one()
                self.assertIsNone(self.p.browser.scope)
                self.assert_no_accepted_input()

    def test_geometry_change_before_capture_completion_skips_ocr(self):
        self.p.conditions.trigger()
        self.current_binding = SimpleNamespace(**{**vars(self.binding), 'dpi': 120})
        self.run_one()
        self.assertEqual(self.pending, [])
        self.reader.read.assert_not_called()
        self.assertFalse(self.p.capture_pending)
        self.assertFalse(self.p.ocr_busy)
        self.assert_no_accepted_input()

    def test_capture_from_a_different_window_is_rejected_before_ocr(self):
        other = SimpleNamespace(**{**vars(self.binding), 'hwnd': 99, 'pid': 22})
        self.capture.return_value = self.frame, other
        self.p.conditions.trigger(); self.run_one()
        self.assertEqual(self.pending, [])
        self.reader.read.assert_not_called()
        self.assert_no_accepted_input()

    def test_repeated_trigger_during_capture_does_not_queue_another_screenshot(self):
        self.p.conditions.trigger()
        self.assertTrue(self.p.capture_pending)
        self.p.conditions.trigger()
        self.assertEqual(len(self.pending), 1)
        self.flush()
        self.capture.assert_called_once_with(self.binding)
        self.assertEqual(self.p.browser.scope[1]['id'], '20778')
        self.assertEqual(self.p.selected_resources.events, ())

    def test_foreground_loss_rejects_queued_detail(self):
        self.queued_ocr()
        self.foreground = 99
        self.run_one()
        self.assertIsNone(self.p.browser.scope)
        self.assert_no_accepted_input()

    def test_new_game_invalidates_queued_result_and_keeps_new_records_empty(self):
        self.queued_ocr()
        self.p.new_game()
        self.run_one()
        self.flush()
        self.assertIsNone(self.p.browser.scope)
        self.assert_no_accepted_input()

    def test_patch_switch_invalidates_queued_result_and_preserves_user_condition(self):
        p = self.p
        p.browser.set_filter('equip', fixtures.CATALOG['equip'][0]); self.flush()
        before = deepcopy(p.browser.scope)
        self.queued_ocr()
        p.patch.addItem('18.3'); p.patch.setCurrentText('18.3')
        with patch('app.Vision.prepare'):
            p.change_patch()
            self.run_one()
            self.flush()
        self.assertEqual(p.adapter.patch, '18.3')
        self.assertEqual(p.browser.scope, before)
        self.assert_no_accepted_input()

    def test_manual_different_condition_wins_over_queued_detail(self):
        self.queued_ocr()
        self.p.browser.set_filter('equip', fixtures.CATALOG['equip'][0])
        before = deepcopy(self.p.browser.scope)
        self.run_one(); self.flush()
        self.assertEqual(self.p.browser.scope, before)
        self.assert_no_accepted_input()

    def test_manual_reselecting_same_condition_invalidates_old_title_request(self):
        p = self.p
        p.browser.set_filter('equip', fixtures.CATALOG['equip'][0]); self.flush()
        self.queued_ocr()
        p.browser.set_filter('equip', fixtures.CATALOG['equip'][0])
        before = deepcopy(p.browser.scope)
        self.run_one(); self.flush()
        self.assertEqual(p.browser.scope, before)
        self.assert_no_accepted_input()

    def test_manual_clearing_already_empty_condition_cancels_queued_title(self):
        self.queued_ocr()
        self.p.browser.clear_filter()
        self.run_one(); self.flush()
        self.assertIsNone(self.p.browser.scope)
        self.assert_no_accepted_input()

    def test_capture_or_ocr_failure_keeps_original_condition_and_releases_busy_flags(self):
        p = self.p
        p.browser.set_filter('equip', fixtures.CATALOG['equip'][0]); self.flush()
        before = deepcopy(p.browser.scope)
        self.capture.side_effect = RuntimeError('capture failed')
        p.conditions.trigger(); self.flush()
        self.assertEqual(p.browser.scope, before)
        self.assertFalse(p.capture_pending or p.ocr_busy)
        self.assert_no_accepted_input()
        self.capture.side_effect = None
        self.reader.read.side_effect = RuntimeError('OCR failed')
        p.conditions.trigger(); self.flush()
        self.assertEqual(p.browser.scope, before)
        self.assertFalse(p.capture_pending or p.ocr_busy)
        self.assert_no_accepted_input()

    def test_unknown_or_invalid_entity_preserves_existing_condition(self):
        p = self.p
        p.browser.set_filter('equip', fixtures.CATALOG['equip'][0]); self.flush()
        before = deepcopy(p.browser.scope)
        for result in ({'route': 'none', 'status': 'unknown'},
                       {'route': 'detail', 'status': 'resolved', 'entity': {'id': '99999', 'name': '黑暗仪式', 'kind': 'hex'}}):
            with self.subTest(result=result):
                self.reader.read.return_value = result
                p.conditions.trigger(); self.flush()
                self.assertEqual(p.browser.scope, before)
                self.assert_no_accepted_input()

    def test_unread_detail_archives_the_exact_existing_capture_and_reason(self):
        result={'route':'none','status':'unknown','scene':'unknown',
                'reason':'detail_header_icon_unconfirmed','evidence':{'readings':[]}}
        self.reader.read.return_value=result
        with patch.object(self.p.bugs,'observed_condition',return_value=True) as report:
            self.p.conditions.trigger();self.flush()
        report.assert_called_once_with(result,self.frame)
        self.capture.assert_called_once_with(self.binding)
        self.assertIn('详情',self.p.browser.input_bar.note.text())
        self.assert_no_accepted_input()

    def test_obsolete_detail_failure_cannot_archive_or_replace_input(self):
        self.reader.read.return_value={'route':'none','status':'unknown','scene':'unknown',
                                      'reason':'detail_header_icon_unconfirmed'}
        with patch.object(self.p.bugs,'observed_condition') as report:
            self.queued_ocr();self.foreground=99;self.run_one()
        report.assert_not_called();self.assert_no_accepted_input()

    def test_augment_and_equipment_routes_use_same_capture_without_expanding_or_selecting(self):
        augment = self.stack.enter_context(patch.object(self.p, 'captured'))
        equipment = self.stack.enter_context(patch.object(self.p.items, 'ingest'))
        for route in ('augment_stats', 'equipment_stats'):
            with self.subTest(route=route):
                self.capture.reset_mock(); augment.reset_mock(); equipment.reset_mock()
                self.reader.read.return_value = {'route': route, 'status': 'unknown'}
                self.p.conditions.trigger(); self.flush()
                self.capture.assert_called_once_with(self.binding)
                if route == 'augment_stats':
                    augment.assert_called_once_with((self.frame, self.binding), True,captured_at=ANY)
                    equipment.assert_not_called()
                else:
                    equipment.assert_called_once_with(self.frame, self.binding, force=True,frame_time=ANY)
                    augment.assert_not_called()
                self.assertIsNone(self.p.browser.scope)
                self.assert_no_accepted_input()

    def test_ambiguity_waits_for_actual_button_then_queries_only_that_form(self):
        catalog = deepcopy(fixtures.CATALOG)
        catalog['hero'] += [{'id': '11506', 'name': '阿卡丽', 'heroType': 0, 'price': 1, 'tag': 'AD'},
                             {'id': '11513', 'name': '阿卡丽', 'heroType': 0, 'price': 1, 'tag': 'AP'}]
        p = self.p
        p.entity_resolver = EntityResolver(catalog); p.browser.set_catalog(catalog)
        candidates = list(p.entity_resolver.resolve('hero', '阿卡丽').candidates)
        self.reader.read.return_value = {'route': 'detail', 'status': 'ambiguous', 'entity': None, 'candidates': candidates}
        p.conditions.trigger(); self.flush()
        self.assertIsNone(p.browser.scope)
        self.assertEqual(p.selected_resources.events, ())
        self.assertEqual(len(p.browser.input_bar.alternative_buttons), 2)
        buttons = p.browser.input_bar.alternative_buttons
        self.assertTrue(all(button.isEnabled() for button in buttons))
        chosen = next(button for button in buttons if 'AP' in button.text())
        chosen.click(); self.flush()
        self.assertEqual(p.browser.scope[1]['id'], '1513')
        body = json.loads(next(call for call in reversed(self.calls) if call.method == 'POST').content)
        self.assertEqual(len(body['filter']['rules']), 1)
        self.assertEqual(body['filter']['rules'][0]['targetId'], '1513')
        self.assertEqual(body['filter']['rules'][0]['starCount'], '')
        self.assertEqual(p.selected_resources.events, ())


if __name__ == '__main__':
    unittest.main()
