"""Spec-axis executable probes; no app changes or live game automation."""
from copy import deepcopy
from types import SimpleNamespace
import time
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from app import QApplication
import test_game_resource_inputs as fixtures
from entity_identity import EntityResolver


class InputSpecReviewTests(unittest.TestCase):
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
                                       rect=(0, 0, 1920, 1080), dpi=96, minimized=False)
        self.p.binding = self.binding
        self.stack.enter_context(patch('app.win.describe', return_value=self.binding))
        self.stack.enter_context(patch('app.win.foreground_root', return_value=7))
        self.stack.enter_context(patch('app.QTimer.singleShot', side_effect=lambda _, fn: fn()))
        self.stack.enter_context(patch.object(self.p, 'panel_open', return_value=False))

    def test_selected_hero_shortcuts_show_observable_form_labels(self):
        # Two real S18 form names with different skills, neither uses AD/AP.
        catalog = {'hero': [
            {'id': '15461', 'name': '拉克丝', 'price': 5, 'heroType': 0,
             'skillName': '黑荆棘', 'skillDesc': '黑荆棘技能'},
            {'id': '15462', 'name': '拉克丝', 'price': 5, 'heroType': 0,
             'skillName': '灵魂莲华', 'skillDesc': '灵魂莲华技能'}],
            'hex': [], 'equip': [], 'trait': []}
        resolver = EntityResolver(catalog)
        self.p.browser.input_bar.set_resources([
            {'kind': 'hero', 'entity': row} for row in resolver.entries('hero')])
        labels = [chip.text() for chip in self.p.browser.input_bar.chips]
        self.assertEqual(len(set(labels)), 2, 'Different hero forms became identical visible chips')
        self.assertTrue(any('黑荆棘' in label for label in labels), labels)
        self.assertTrue(any('灵魂莲华' in label for label in labels), labels)

    def test_query_retry_does_not_change_explicit_confirmation_event_identity(self):
        p = self.p
        p.browser.set_filter('hex', fixtures.CATALOG['hex'][0], can_confirm=True)
        p.confirm_condition()
        p.browser.retry()  # Only a statistics retry, not a new game selection.
        p.confirm_condition()  # Repeated confirmation callback for the same displayed choice.
        self.assertEqual(len(p.selected_resources.events), 1)

    def test_repeated_fresh_new_match_stage_does_not_keep_old_records_clickable(self):
        p = self.p
        p.browser.set_filter('hex', fixtures.CATALOG['hex'][0], can_confirm=True)
        p.confirm_condition()
        p.automatic.setChecked(True)
        p.last_probe_stage = '4-2'
        with patch('app.capture_stage', return_value=Image.new('RGB', (200, 60))), \
             patch.object(p.vision, 'read_round_crop', return_value='2-1'):
            p.probe_stage(); self.flush()
            p.probe_stage(); self.flush()
        # Spec 5.3 permits an uncertain-boundary state instead of automatic reset,
        # but previous-game shortcuts must then stop being current/clickable.
        chips = p.browser.input_bar.chips
        self.assertTrue(not chips or all(not chip.isEnabled() for chip in chips),
                        'Old-game confirmed resources remain active in the next 2-1')

    def test_close_between_resource_guards_clears_previous_game_records(self):
        p = self.p
        p.browser.set_filter('hex', fixtures.CATALOG['hex'][0], can_confirm=True)
        p.confirm_condition()
        p.selections.binding_changed(self.binding)
        p.automatic.setChecked(True)
        # The regular tick notices closure before the 3s resource guard runs.
        p.last_resource_guard = time.monotonic()
        with patch('app.win.describe', return_value=None), \
             patch('app.win.capture_block_reason', return_value='target_changed_or_closed'), \
             patch('app.game_windows', return_value=[]):
            p.tick(); p.tick()
        self.assertIsNone(p.binding)
        self.assertEqual(p.selected_resources.events, ())
        self.assertEqual(p.browser.input_bar.chips, [])

    def test_augment_route_keeps_same_frame_and_calls_original_rank_path(self):
        p = self.p
        frame = Image.new('RGB', (1920, 1080))
        reader = Mock()
        reader.read.return_value = {'route': 'augment_stats', 'status': 'unknown'}
        p.conditions.reader = reader
        before_scope = deepcopy(p.browser.scope)
        with patch('condition_controller.capture_image', return_value=(frame, self.binding)) as capture, \
             patch.object(p, 'captured') as original_ranks, \
             patch.object(p, 'showNormal') as expand:
            p.conditions.trigger(); self.flush()
        capture.assert_called_once_with(self.binding)
        from unittest.mock import ANY
        original_ranks.assert_called_once_with((frame, self.binding), True,captured_at=ANY)
        self.assertTrue(p.once_active and p.once_ocr_pending)
        self.assertEqual(p.browser.scope, before_scope)
        self.assertFalse(expand.called)
        self.assertEqual(p.selected_resources.events, ())


if __name__ == '__main__':
    unittest.main()
