"""A failed global response must not turn unchanged frames into polling.

The actual Companion scheduling, DataJ validation and Qt failure callback run;
only HTTP transport, native placement and the OCR engine are deterministic.
"""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx
import numpy as np
from PIL import Image

from app import QApplication, CardOverlay
from dataj import DataJ
from vision import TextSignature
import test_runtime_stability as fixtures


class GlobalStatsRetryTests(unittest.TestCase):
    tearDown = fixtures.RuntimeStability.tearDown
    seed_results = fixtures.RuntimeStability.seed_results

    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        fixtures.RuntimeStability.setUp(self)
        self.clock = 100.0
        self.stack.enter_context(patch('app.time.monotonic', side_effect=lambda: self.clock))
        self.stack.enter_context(patch.object(CardOverlay, 'place'))
        self.stack.enter_context(patch.object(self.p.items, 'ingest', return_value=False))
        self.p.automatic.setChecked(True)
        self.p.stage.blockSignals(True)
        self.p.stage.setCurrentText('2-1')
        self.p.stage.blockSignals(False)
        self.frame = Image.new('RGB', (1280, 720))
        self.signature = TextSignature((np.ones((8, 20), dtype=bool),))
        mask = np.zeros((8, 20), dtype=bool)
        mask[:3, :8] = True
        self.changed = TextSignature((mask,))
        self.seed_results()
        self.p.signature = self.signature
        self.p.last_frame = self.frame
        self.p.last_ocr = self.clock - 3
        self.calls = []
        self.bad = True
        self.p.adapter = DataJ(patch='18.3', db=Path(self.tmp.name) / 'retry.db',
                               transport=httpx.MockTransport(self.response))
        self.p.session.patch = self.p.adapter.patch

    def response(self, request):
        self.calls.append(request)
        # Independent source oracle: avgPlacement=None is unusable statistics.
        data = [{'hexId': '1023', 'name': '应急护甲 I', 'roundStats': [
            {'round': 0, 'roundLabel': '2-1', 'avgPlacement': None if self.bad else 4.76,
             'sampleCount': 301}]}]
        return httpx.Response(200, json={'success': True, 'code': 200, 'data': data})

    def observation(self):
        result = deepcopy(self.p.last_observation)
        result.update(elapsed_ms=1, image_size=self.frame.size)
        for card in result['cards']:
            card['raw_text'] = '应急护甲 I'
            card['resolution']['name'] = '应急护甲 I'
        return result

    def run_jobs(self):
        while self.jobs:
            work, done, failed = self.jobs.pop(0)
            try:
                value = work()
            except Exception as error:
                if failed is None:
                    raise
                failed(str(error))
            else:
                done(value)

    def fail_global(self):
        ids = [card['resolution'].get('id') for card in self.p.last_observation['cards']]
        self.p.query_stats(ids, ['应急护甲 I'] * 3, True, refresh=True)
        self.run_jobs()
        self.assertEqual(len(self.calls), 1)
        self.assertIsNone(self.p.stats_payload)
        self.assertEqual(self.p.activity_code, 'stats_failed')
        self.assertEqual(self.p.choice_table.rowCount(), 0)

    def accept(self, *, once=False, signature=None):
        self.p.accept_frame((self.frame, self.binding), once,
                            (([], None), self.signature if signature is None else signature), self.clock)

    def test_invalid_http200_does_not_poll_or_repeat_ocr_for_unchanged_choices(self):
        self.fail_global()
        observation = self.observation()
        with patch.object(self.p.vision, 'analyze_fast', return_value=observation) as ocr, \
                patch('app.tracked_signature', return_value=self.signature):
            for _ in range(6):
                self.clock += 3
                self.accept()
                self.run_jobs()
        self.assertEqual(len(self.calls), 1,
                         'Unchanged frames must not poll a persistently corrupt HTTP 200 source')
        ocr.assert_not_called()
        self.assertIsNone(self.p.stats_payload)
        self.assertEqual(self.p.choice_table.rowCount(), 0)

    def test_manual_same_choices_recovers_without_repeating_ocr(self):
        self.fail_global()
        self.clock += 3
        self.bad = False
        with patch.object(self.p, 'analyze') as ocr:
            self.accept(once=True)
            self.run_jobs()
        ocr.assert_not_called()
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.p.choice_table.item(0, 1).text(), '4.76 · 301局')
        self.assertIsNotNone(self.p.stats_payload)

    def test_pending_side_key_retry_respects_source_cooldown_without_repeating_ocr(self):
        self.fail_global()
        self.p.adapter.next_request = self.clock + 60
        self.p.once_ocr_pending = True
        with patch.object(self.p, 'analyze') as ocr:
            self.accept()
            self.run_jobs()
        ocr.assert_not_called()
        self.assertEqual(len(self.calls), 1, 'Manual retry must still respect the shared source cooldown')
        self.assertFalse(self.p.once_ocr_pending)
        self.assertIsNone(self.p.stats_payload)
        self.assertEqual(self.p.activity_code, 'stats_failed')

    def test_changed_cards_after_failure_are_still_detected_and_recognized(self):
        self.fail_global()
        self.p.next_ocr_allowed = self.clock + 60
        with patch.object(self.p, 'analyze') as ocr:
            self.accept(signature=self.changed)
        ocr.assert_called_once_with(self.frame, True)
        self.assertIsNone(self.p.last_observation)

    def test_session_reset_after_failure_does_not_block_new_group(self):
        self.fail_global()
        self.p.session.reset()
        self.p.invalidate()
        self.clock += 3
        with patch.object(self.p, 'analyze') as ocr:
            self.accept()
        ocr.assert_called_once_with(self.frame, True)

    def test_changed_stage_after_failure_does_not_block_new_group(self):
        self.fail_global()
        self.p.last_probe_stage = '2-1'
        self.p.probe_stage()
        _, done, _ = self.jobs.pop(0)
        done('3-2')
        self.clock += 3
        with patch.object(self.p, 'analyze') as ocr:
            self.accept()
        ocr.assert_called_once_with(self.frame, True)

    def test_changed_patch_after_failure_does_not_block_new_group(self):
        self.fail_global()
        catalog = self.p.catalog
        self.p.patch.addItem('18.4')
        self.p.patch.setCurrentText('18.4')
        with patch.object(self.p, 'load_catalog'):
            self.p.change_patch()
        self.assertEqual(self.p.adapter.patch, '18.4')
        # Loading the new patch's catalog is separate from this capture gate.
        self.p.catalog = catalog
        self.clock += 3
        with patch.object(self.p, 'analyze') as ocr:
            self.accept()
        ocr.assert_called_once_with(self.frame, True)

    def test_failure_keeps_routine_capture_for_changed_card_detection(self):
        self.fail_global()
        self.p.last_stage_probe = self.p.last_resource_guard = self.clock
        self.clock += .6
        with patch.object(self.p, 'request_capture') as capture, patch.object(self.p.items, 'tick'):
            self.p.tick()
        capture.assert_called_once_with()

    def test_failed_partial_choices_keep_two_bounded_recognition_retries(self):
        self.p.last_observation['cards'] = deepcopy(self.p.last_observation['cards'])
        self.p.last_observation['cards'][2]['resolution'] = {}
        self.fail_global()
        observation = self.observation()
        with patch.object(self.p.vision, 'analyze_fast', return_value=observation) as ocr, \
                patch('app.tracked_signature', return_value=self.signature):
            for _ in range(6):
                self.clock += 3
                self.accept()
                self.run_jobs()
        self.assertEqual(ocr.call_count, 2,
                         'Failed statistics must preserve the existing two partial-title retries')
        self.assertEqual(len(self.calls), 3,
                         'Only the initial failure and two finite partial-title retries may reach HTTP')

    def test_late_failure_cannot_clear_new_group_results(self):
        observation = self.observation()
        self.p.query_stats(['1023'] * 3, ['应急护甲 I'] * 3, True, refresh=True)
        _, _, old_failed = self.jobs.pop(0)
        self.p.invalidate()
        self.p.last_observation = observation
        self.bad = False
        self.p.query_stats(['1023'] * 3, ['应急护甲 I'] * 3, True)
        self.run_jobs()
        payload = self.p.stats_payload
        activity = self.p.activity_code
        old_failed('late prior group failure')
        self.assertIs(self.p.stats_payload, payload)
        self.assertEqual(self.p.activity_code, activity)
        self.assertEqual(self.p.choice_table.item(0, 1).text(), '4.76 · 301局')

    def test_replaced_adapter_failure_cannot_poison_current_result(self):
        payload = deepcopy(self.p.stats_payload)
        self.p.query_stats(['1023'] * 3, ['应急护甲 I'] * 3, True, refresh=True)
        _, _, old_failed = self.jobs.pop(0)
        payload['token'] = self.p.session.token()
        self.p.stats_payload = payload
        self.p.adapter = DataJ(patch='18.4', db=Path(self.tmp.name) / 'new-patch.db',
                               transport=httpx.MockTransport(self.response))
        old_failed('late prior adapter failure')
        self.assertIs(self.p.stats_payload, payload)
        self.assertNotEqual(self.p.activity_code, 'stats_failed')


if __name__ == '__main__':
    unittest.main()
