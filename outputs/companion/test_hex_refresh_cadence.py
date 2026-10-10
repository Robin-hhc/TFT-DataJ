"""Controlled-clock regressions through real Qt augment scheduling callbacks.

No screen capture, game input, OCR engine, or external HTTP is performed. The
worker dispatcher is held; the production token, capture and publication gates
remain active. Native placement is disabled so synthetic results stay hidden.
"""
from copy import deepcopy
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from app import QApplication, CardOverlay
from vision import TextSignature
import test_runtime_stability as fixtures


class HexRefreshCadence(unittest.TestCase):
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
        self.stack.enter_context(patch.object(self.p.items, 'tick'))
        self.p.automatic.setChecked(True)
        self.p.last_stage_probe = self.p.last_resource_guard = self.clock
        self.frame = Image.new('RGB', (1280, 720))
        self.signature = TextSignature((np.ones((8, 20), dtype=bool),))
        mask = np.zeros((8, 20), dtype=bool)
        mask[:3, :8] = True
        self.changed = TextSignature((mask,))
        self.seed_results()
        self.p.signature = self.signature
        self.p.last_frame = self.frame

    def accept(self, frame=None, signature=None):
        self.p.accept_frame((frame or self.frame, self.binding), False,
                            (([], None), signature or self.signature), self.clock)

    def observation(self):
        obs = deepcopy(self.p.last_observation)
        obs['cards'] = [deepcopy(card) for card in obs['cards']]
        obs.update(elapsed_ms=1, image_size=self.frame.size)
        for card in obs['cards']:
            card['raw_text'] = '应急护甲 I'
            card['resolution']['name'] = '应急护甲 I'
        return obs

    def test_changed_group_still_requests_capture_after_half_second(self):
        self.p.choices_changed()
        self.clock += .51
        with patch.object(self.p, 'request_capture') as capture:
            self.p.tick()
        capture.assert_called_once_with()

    def test_pending_independent_confirmation_still_uses_half_second(self):
        obs = self.observation()
        self.p.choices_changed()
        self.p.pending_choice_confirmation = (self.frame, obs, self.signature, lambda *_: None)
        self.clock += .51
        with patch.object(self.p, 'request_capture') as capture:
            self.p.tick()
        capture.assert_called_once_with()

    def test_new_group_does_not_inherit_previous_success_cooldown(self):
        self.p.last_ocr = self.clock - .1
        self.p.next_ocr_allowed = self.clock + 1.4
        self.clock += .1
        self.accept(signature=self.changed)
        self.assertTrue(self.p.ocr_busy, 'A newly detected group waited for the old 1.5s cooldown')
        self.assertEqual(len(self.jobs), 1, 'Exactly one replacement OCR must be dispatched')

    def test_invalidated_success_cannot_delay_new_group(self):
        obs = self.observation()
        self.p.analyze(self.frame, True)
        _, done, _ = self.jobs.pop()
        self.p.choices_changed()
        self.p.next_ocr_allowed = 0
        self.clock += .1
        done((obs, self.signature))
        self.assertEqual(self.p.next_ocr_allowed, 0, 'An obsolete success imposed its cooldown on new cards')
        self.assertIsNone(self.p.last_observation)
        self.assertIsNone(self.p.stats_payload)
        self.assertFalse(self.p.ocr_busy)

    def test_invalidated_failure_cannot_delay_new_group(self):
        self.p.analyze(self.frame, True)
        _, _, failed = self.jobs.pop()
        self.p.choices_changed()
        self.p.next_ocr_allowed = 0
        self.clock += .1
        failed('synthetic OCR failure')
        self.assertEqual(self.p.next_ocr_allowed, 0, 'An obsolete failure imposed its backoff on new cards')
        self.assertIsNone(self.p.last_observation)
        self.assertIsNone(self.p.stats_payload)
        self.assertFalse(self.p.ocr_busy)

    def test_same_confirmed_group_for_thirty_seconds_never_repeats_ocr_or_http(self):
        payload = self.p.stats_payload
        token = self.p.session.token()
        self.p.last_ocr = self.clock - .1
        with patch.object(self.p.vision, 'analyze_fast') as ocr, \
             patch.object(self.p.adapter, 'hexes') as http:
            for _ in range(60):
                self.clock += .5
                self.accept(self.frame.copy())
                self.assertEqual(self.jobs, [])
        ocr.assert_not_called()
        http.assert_not_called()
        self.assertIs(self.p.stats_payload, payload)
        self.assertTrue(self.p.session.accepts(token))

    def test_valid_failure_keeps_same_group_retry_backoff(self):
        self.p.invalidate()
        self.p.once_active = self.p.once_ocr_pending = True
        self.p.once_deadline = self.clock + 30
        self.p.analyze(self.frame, True)
        _, _, failed = self.jobs.pop()
        failed('synthetic current OCR failure')
        self.assertEqual(self.p.next_ocr_allowed, 102.0)
        self.clock = 101.99
        self.accept()
        self.assertEqual(self.jobs, [], 'A current failure must not cause an every-frame OCR loop')
        self.clock = 102.01
        self.accept()
        self.assertEqual(len(self.jobs), 1)
        self.assertTrue(self.p.ocr_busy)

    def test_partial_unknown_slots_keep_their_existing_backoff(self):
        self.p.last_observation['cards'] = [deepcopy(card) for card in self.p.last_observation['cards']]
        self.p.last_observation['cards'][2]['resolution'] = {'id': None}
        self.p.session.set_choices('2-1', ['1023', '1023', None])
        self.p.stats_payload['token'] = self.p.session.token()
        self.p.last_ocr = 99.0
        self.p.next_ocr_allowed = 101.5
        self.clock = 101.49
        self.accept()
        self.assertEqual(self.jobs, [])
        self.assertEqual(self.p.partial_retries, 0)
        self.clock = 101.51
        self.accept()
        self.assertEqual(len(self.jobs), 1)
        self.assertEqual(self.p.partial_retries, 1)

    def prepare_confirmation(self):
        obs = self.observation()
        self.p.choices_changed()
        self.p.last_frame = self.frame
        self.p.last_capture = self.clock
        self.p.analyze(self.frame, True)
        _, done, _ = self.jobs.pop()
        done((obs, self.changed))
        self.assertIsNotNone(self.p.pending_choice_confirmation)
        return obs

    def test_refresh_result_requires_one_independent_matching_frame(self):
        with patch.object(self.p, 'query_stats') as query:
            self.prepare_confirmation()
            self.assertIsNone(self.p.stats_payload)
            query.assert_not_called()
            self.clock += .5
            self.accept(self.frame, self.changed)
            query.assert_not_called()
            self.accept(self.frame.copy(), self.changed)
            query.assert_called_once()
        self.assertIsNone(self.p.pending_choice_confirmation)
        self.assertFalse(self.p.choice_recheck_required)

    def test_exit_before_confirmation_cannot_publish_pending_ranks(self):
        with patch.object(self.p, 'query_stats') as query:
            self.prepare_confirmation()
            self.clock += .5
            board = Image.new('RGB', self.frame.size, 'blue')
            self.p.accept_frame((board, self.binding), False,
                                (([], None), None), self.clock)
            query.assert_not_called()
        self.assertIsNone(self.p.pending_choice_confirmation)
        self.assertIsNone(self.p.stats_payload)
        self.assertTrue(self.p.choice_recheck_required)

    def test_rapid_second_refresh_discards_first_pending_group(self):
        with patch.object(self.p, 'query_stats') as query:
            self.prepare_confirmation()
            old_pending = self.p.pending_choice_confirmation
            self.clock += .5
            self.accept(self.frame.copy(), self.signature)
            self.assertIsNone(self.p.pending_choice_confirmation)
            old_pending[3](old_pending[1], old_pending[2])
            query.assert_not_called()
        self.assertIsNone(self.p.stats_payload)
        self.assertTrue(self.p.choice_recheck_required)

    def test_repeated_half_second_ticks_do_not_queue_parallel_captures(self):
        self.p.choices_changed()
        self.clock += .51
        for _ in range(8):
            self.p.tick()
            self.clock += .05
        self.assertEqual(len(self.jobs), 1)
        self.assertTrue(self.p.capture_pending)

    def test_unverifiable_signature_waits_for_pixels_beyond_retry_backoff(self):
        obs = self.observation()
        self.p.analyze(self.frame, True)
        _, done, _ = self.jobs.pop()
        done((obs, None))
        self.assertIsNone(self.p.last_observation)
        self.assertTrue(self.p.once_ocr_pending)
        self.assertEqual(self.p.next_ocr_allowed, 101.5)
        self.clock = 101.49
        self.p.accept_frame((self.frame.copy(), self.binding), False,
                            (([], None), None), self.clock)
        self.assertEqual(self.jobs, [], 'Unverifiable pixels cannot cancel their own retry backoff')
        self.clock = 101.51
        self.p.accept_frame((self.frame.copy(), self.binding), False,
                            (([], None), None), self.clock)
        # Animation recovery now waits for readable strokes rather than
        # rerunning OCR merely because the previous backoff has elapsed.
        self.assertEqual(self.jobs, [])
        self.clock = 101.6
        self.accept(self.frame.copy(), self.changed)
        self.assertEqual(len(self.jobs), 1)

    def test_unknown_choice_page_keeps_retry_backoff(self):
        self.p.invalidate()
        self.p.analyze(self.frame, True)
        _, done, _ = self.jobs.pop()
        unknown = {'scene': 'choice_unresolved', 'round': None, 'cards': [],
                   'elapsed_ms': 1, 'image_size': self.frame.size}
        done((unknown, None))
        self.assertEqual(self.p.next_ocr_allowed, 101.5)
        self.clock = 101.49
        self.accept(self.frame.copy())
        self.assertEqual(self.jobs, [])
        self.clock = 102.01
        self.accept(self.frame.copy())
        self.assertEqual(len(self.jobs), 1)

    def test_rapid_refresh_only_latest_confirmed_candidates_fetch_and_publish(self):
        first = self.observation()
        first['cards'][0]['resolution'] = {'id': '1479', 'name': '便携锻炉', 'status': 'resolved'}
        first['cards'][0]['raw_text'] = '便携锻炉'
        latest = deepcopy(first)
        latest['cards'][0]['resolution'] = {'id': '1006', 'name': '装备百宝袋 I', 'status': 'resolved'}
        latest['cards'][0]['raw_text'] = '装备百宝袋 I'
        newest_mask = np.zeros((8, 20), dtype=bool)
        newest_mask[5:, 12:] = True
        newest_signature = TextSignature((newest_mask,))
        rows = [{'hexId': entity, 'roundStats': [{'round': 0, 'roundLabel': '2-1',
                 'avgPlacement': mean, 'sampleCount': 51}]}
                for entity, mean in [('1023', 4.76), ('1479', 5.5), ('1006', 3.25)]]
        with patch.object(self.p.adapter, 'hexes', return_value={'data': rows, 'fetched_at': 0}) as http:
            self.clock += .1
            self.accept(self.frame.copy(), self.changed)
            self.assertEqual(len(self.jobs), 1)
            _, first_done, _ = self.jobs.pop()
            first_done((first, self.changed))
            obsolete = self.p.pending_choice_confirmation
            self.assertIsNotNone(obsolete)
            self.clock += .5
            newest_frame = self.frame.copy()
            self.accept(newest_frame, newest_signature)
            self.assertEqual(len(self.jobs), 1)
            _, latest_done, _ = self.jobs.pop()
            latest_done((latest, newest_signature))
            self.assertIsNone(self.p.stats_payload)
            self.assertIsNotNone(self.p.pending_choice_confirmation)
            obsolete[3](obsolete[1], obsolete[2])
            self.assertIsNone(self.p.stats_payload)
            self.clock += .5
            self.accept(newest_frame.copy(), newest_signature)
            self.assertEqual(len(self.jobs), 1, 'Only the latest independently confirmed group may query')
            work, done, _ = self.jobs.pop()
            done(work())
        http.assert_called_once_with()
        self.assertEqual(self.p.session.choices, ('1006', '1023', '1023'))
        self.assertEqual(self.p.choice_table.item(0, 0).text(), '装备百宝袋 I')
        self.assertEqual(self.p.choice_table.item(0, 1).text(), '3.25 · 51局')
        self.assertEqual(self.jobs, [])


if __name__ == '__main__':
    unittest.main()
