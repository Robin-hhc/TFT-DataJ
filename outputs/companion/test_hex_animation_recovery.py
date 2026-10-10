"""Public Qt callback regressions for unreadable augment refresh animations.

Workers, clock and native placement are isolated; session invalidation, OCR
dispatch, later-frame confirmation and reporting remain the production paths.
No game capture, external requests or private screenshot fixture is required.
"""
from copy import deepcopy
import unittest
from unittest.mock import patch

import numpy as np

from vision import TextSignature
import test_hex_refresh_cadence as cadence


class HexAnimationRecovery(unittest.TestCase):
    setUpClass = classmethod(cadence.HexRefreshCadence.setUpClass.__func__)
    tearDown = cadence.HexRefreshCadence.tearDown
    seed_results = cadence.HexRefreshCadence.seed_results
    observation = cadence.HexRefreshCadence.observation
    accept = cadence.HexRefreshCadence.accept

    def setUp(self):
        cadence.HexRefreshCadence.setUp(self)
        self.stack.enter_context(patch('app.record'))

    def start_animation(self):
        observation = deepcopy(self.observation())
        observation['cards'][0]['resolution'] = {
            'status': 'unrecognized', 'readings': ['', '', ''], 'candidates': []}
        unreadable = TextSignature((np.zeros((8, 20), dtype=bool),))
        self.p.choices_changed()
        self.p.last_frame = self.frame
        self.p.analyze(self.frame, True)
        _, done, _ = self.jobs.pop()
        done((observation, unreadable))
        return observation, unreadable

    def test_refresh_animation_is_not_auto_archived_as_recognition_failure(self):
        with patch.object(self.p.bugs, 'observed_hex') as report:
            self.start_animation()
        report.assert_not_called()
        self.assertIsNone(self.p.stats_payload)

    def test_first_readable_title_frame_retries_before_old_ocr_cooldown(self):
        self.start_animation()
        self.clock += .5
        self.accept(self.frame.copy(), self.changed)
        self.assertEqual(len(self.jobs), 1,
                         'The first readable replacement titles waited for 1.5s/2s OCR backoff')
        self.assertTrue(self.p.ocr_busy)
        self.assertIsNone(self.p.stats_payload,
                          'Readable strokes alone must never restore old statistics')

    def test_continuous_animation_only_checks_existing_captures(self):
        _, unreadable = self.start_animation()
        with patch.object(self.p.vision, 'analyze_fast') as ocr, \
             patch.object(self.p, 'request_capture') as capture:
            for _ in range(60):
                self.clock += .5
                self.accept(self.frame.copy(), unreadable)
                self.assertEqual(self.jobs, [], 'Unreadable animation queued another OCR')
        ocr.assert_not_called()
        capture.assert_not_called()
        self.assertIsNone(self.p.stats_payload)

    def test_context_reset_cannot_keep_an_old_animation_gate(self):
        self.start_animation()
        self.p.invalidate()
        self.p.once_ocr_pending = True
        self.p.next_ocr_allowed = 0
        self.clock += .5
        self.p.accept_frame((self.frame.copy(), self.binding), False,
                            (([], None), None), self.clock)
        self.assertEqual(len(self.jobs), 1,
                         'A reset session was still blocked by the previous animation')

    def test_foreground_loss_clears_animation_gate(self):
        self.start_animation()
        with patch('app.win.foreground_root', return_value=99), \
             patch('app.win.capture_block_reason', return_value='not_foreground'):
            self.p.tick()
        self.assertIsNone(self.p.unverified_choice_observation)
        self.assertIsNone(self.p.stats_payload)

    def test_all_three_unreadable_titles_are_not_auto_archived(self):
        observation = self.observation()
        observation['scene'] = 'choice_unresolved'
        for card in observation['cards']:
            card['resolution'] = {'status': 'unrecognized', 'readings': ['', '', '']}
        self.p.choices_changed()
        self.p.last_frame = self.frame
        self.p.analyze(self.frame, True)
        _, done, _ = self.jobs.pop()
        with patch.object(self.p.bugs, 'observed_hex') as report:
            done((observation, TextSignature((np.zeros((8, 20), dtype=bool),))))
        report.assert_not_called()

    def test_unreadable_titles_with_unknown_round_are_not_auto_archived(self):
        base = self.observation()
        for scene in ('choice_candidates', 'choice_unresolved'):
            with self.subTest(scene=scene):
                observation = deepcopy(base)
                observation.update(scene=scene, round=None)
                for card in observation['cards']:
                    card['resolution'] = {'status': 'unrecognized', 'readings': ['', '', '']}
                self.p.invalidate()
                self.p.last_frame = self.frame
                self.p.analyze(self.frame, True)
                _, done, _ = self.jobs.pop()
                with patch.object(self.p.bugs, 'observed_hex') as report, \
                     patch.object(self.p, 'query_stats') as query:
                    done((observation, TextSignature((np.zeros((8, 20), dtype=bool),))))
                    report.assert_not_called()
                    query.assert_not_called()
                self.assertIsNotNone(self.p.unverified_choice_observation)

    def test_exit_to_board_drops_gate_in_capture_worker_callback(self):
        self.start_animation()
        self.clock += .5
        self.p.captured((self.frame.copy(), self.binding), False, self.clock)
        inspect, inspected, _ = self.jobs.pop()
        with patch('app.may_be_choice', return_value=False), \
             patch('app.inspect_items', return_value=([], None)):
            inspected(inspect())
        self.assertIsNone(self.p.unverified_choice_observation,
                          'A board frame still waited for the old augment titles')
        self.assertFalse(self.p.choice_recheck_required)
        self.assertIsNone(self.p.stats_payload)

    def test_recovered_ocr_still_requires_independent_frame_before_statistics(self):
        observation, _ = self.start_animation()
        observation['cards'][0]['resolution'] = {
            'status': 'resolved', 'id': '1023', 'name': '应急护甲 I'}
        self.clock += .5
        frame = self.frame.copy()
        with patch.object(self.p, 'query_stats') as query:
            self.accept(frame, self.changed)
            _, done, _ = self.jobs.pop()
            done((observation, self.changed))
            query.assert_not_called()
            self.clock += .5
            self.accept(frame, self.changed)
            query.assert_not_called()
            self.accept(frame.copy(), self.changed)
            query.assert_called_once()

    def test_first_stage_animation_recovery_requires_independent_frame(self):
        observation = self.observation()
        self.p.invalidate()
        self.p.last_frame = self.frame
        self.p.analyze(self.frame, True)
        _, done, _ = self.jobs.pop()
        done((observation, TextSignature((np.zeros((8, 20), dtype=bool),))))
        self.clock += .5
        recovery_frame = self.frame.copy()
        with patch.object(self.p, 'query_stats') as query, \
             patch.object(self.p.bugs, 'observed_hex') as report:
            self.accept(recovery_frame, self.changed)
            _, recovered, _ = self.jobs.pop()
            recovered((observation, self.changed))
            query.assert_not_called()
            report.assert_not_called()
            self.assertIsNotNone(self.p.pending_choice_confirmation)
            self.accept(recovery_frame, self.changed)
            query.assert_not_called()
            self.clock += .5
            self.accept(recovery_frame.copy(), self.changed)
            query.assert_called_once()
            report.assert_called_once()

    def test_recovered_catalog_misses_require_independent_frame_before_archive(self):
        observation = self.observation()
        observation['scene'] = 'choice_unresolved'
        for card in observation['cards']:
            card['resolution'] = {'status': 'unrecognized', 'readings': ['来源缺名'] * 3}
        self.p.invalidate()
        self.p.last_frame = self.frame
        self.p.analyze(self.frame, True)
        _, done, _ = self.jobs.pop()
        done((observation, TextSignature((np.zeros((8, 20), dtype=bool),))))
        self.clock += .5
        recovery_frame = self.frame.copy()
        with patch.object(self.p, 'query_stats') as query, \
             patch.object(self.p.bugs, 'observed_hex') as report:
            self.accept(recovery_frame, self.changed)
            _, recovered, _ = self.jobs.pop()
            recovered((observation, self.changed))
            query.assert_not_called()
            report.assert_not_called()
            self.assertIsNotNone(self.p.pending_choice_confirmation)
            self.clock += .5
            self.accept(recovery_frame.copy(), self.changed)
            query.assert_not_called()
            report.assert_called_once()

    def test_recovered_unknown_round_requires_independent_frame_and_no_rankings(self):
        observation = self.observation()
        observation.update(scene='choice_unresolved', round=None)
        for card in observation['cards']:
            card['resolution'] = {'status': 'unrecognized', 'readings': ['来源缺名'] * 3}
        self.p.invalidate()
        self.p.last_frame = self.frame
        self.p.analyze(self.frame, True)
        _, done, _ = self.jobs.pop()
        done((observation, TextSignature((np.zeros((8, 20), dtype=bool),))))
        self.clock += .5
        recovery_frame = self.frame.copy()
        with patch.object(self.p, 'query_stats') as query, \
             patch.object(self.p.bugs, 'observed_hex') as report:
            self.accept(recovery_frame, self.changed)
            _, recovered, _ = self.jobs.pop()
            recovered((observation, self.changed))
            report.assert_not_called()
            query.assert_not_called()
            self.assertIsNotNone(self.p.pending_choice_confirmation)
            self.clock += .5
            self.accept(recovery_frame.copy(), self.changed)
            report.assert_called_once()
            query.assert_not_called()
        self.assertIsNone(self.p.stats_payload)
        self.assertIsNone(self.p.unverified_choice_observation)

    def test_stable_catalog_miss_is_reported_after_frame_confirmation(self):
        observation = self.observation()
        observation['cards'][0]['raw_text'] = '白银命运'
        observation['cards'][0]['resolution'] = {
            'status': 'unrecognized', 'readings': ['白银命运'] * 3, 'candidates': []}
        self.p.choices_changed()
        self.p.last_frame = self.frame
        with patch.object(self.p.bugs, 'observed_hex') as report, \
             patch.object(self.p, 'query_stats'):
            self.p.analyze(self.frame, True)
            _, done, _ = self.jobs.pop()
            done((observation, self.changed))
            report.assert_not_called()
            self.clock += .5
            self.accept(self.frame.copy(), self.changed)
            report.assert_called_once_with(observation, self.frame)

    def test_stable_three_catalog_misses_still_have_signature_and_are_reported(self):
        observation = self.observation()
        observation['scene'] = 'choice_unresolved'
        for card in observation['cards']:
            card['resolution'] = {'status': 'unrecognized', 'readings': ['来源缺名'] * 3}
        self.p.invalidate()
        self.p.last_frame = self.frame
        with patch.object(self.p.vision, 'analyze_fast', return_value=observation), \
             patch('app.tracked_signature', return_value=self.changed), \
             patch.object(self.p.bugs, 'observed_hex') as report:
            self.p.analyze(self.frame, True)
            recognize, done, _ = self.jobs.pop()
            done(recognize())
            report.assert_called_once_with(observation, self.frame)

    def test_obsolete_recovered_ocr_callback_cannot_restore_statistics(self):
        observation, _ = self.start_animation()
        self.clock += .5
        self.accept(self.frame.copy(), self.changed)
        _, done, _ = self.jobs.pop()
        self.p.invalidate()
        with patch.object(self.p, 'query_stats') as query, \
             patch.object(self.p.bugs, 'observed_hex') as report:
            done((observation, self.changed))
            query.assert_not_called()
            report.assert_not_called()
        self.assertIsNone(self.p.stats_payload)
        self.assertIsNone(self.p.pending_choice_confirmation)

    def test_item_choice_keeps_priority_over_previous_animation_gate(self):
        self.start_animation()
        self.clock += .5
        with patch.object(self.p.items, 'ingest', return_value=True), \
             patch.object(self.p.vision, 'analyze_fast') as ocr:
            self.accept(self.frame.copy())
        ocr.assert_not_called()
        self.assertEqual(self.jobs, [])
        self.assertIsNone(self.p.unverified_choice_observation)
        self.assertFalse(self.p.choice_recheck_required)

    def test_capture_worker_uses_held_regions_for_readability_recovery(self):
        self.start_animation()
        self.clock += .5
        self.p.captured((self.frame.copy(), self.binding), False, self.clock)
        inspect, inspected, _ = self.jobs.pop()
        with patch('app.may_be_choice', return_value=True), \
             patch('app.tracked_signature', return_value=self.changed) as strokes:
            inspected(inspect())
        strokes.assert_called_once()
        self.assertEqual(len(self.jobs), 1)
        self.assertTrue(self.p.ocr_busy)

    def test_first_stage_animation_keeps_half_second_capture_after_stage_window(self):
        observation = self.observation()
        self.p.invalidate()
        self.p.last_frame = self.frame
        self.p.last_capture = self.clock
        self.p.analyze(self.frame, True)
        _, done, _ = self.jobs.pop()
        done((observation, TextSignature((np.zeros((8, 20), dtype=bool),))))
        self.p.offline = False
        self.p.stage_window_until = 0
        self.clock += .51
        with patch.object(self.p, 'request_capture') as capture:
            self.p.tick()
        capture.assert_called_once_with()

    def test_animation_lifecycle_ticks_dispatch_captures_without_repeated_ocr(self):
        _, unreadable = self.start_animation()
        self.p.offline = False
        with patch('app.capture_image', side_effect=lambda _: (self.frame.copy(), self.binding)) as capture, \
             patch('app.may_be_choice', return_value=True), \
             patch('app.tracked_signature', return_value=unreadable), \
             patch.object(self.p.vision, 'analyze_fast') as ocr:
            for _ in range(60):
                self.clock += .51
                self.p.last_stage_probe = self.clock
                self.p.tick()
                self.assertEqual(len(self.jobs), 1, 'Exactly one scheduled capture owns this tick')
                work, done, _ = self.jobs.pop()
                done(work())
                inspect, inspected, _ = self.jobs.pop()
                inspected(inspect())
                self.assertEqual(self.jobs, [], 'Unreadable animation dispatched another OCR')
        self.assertEqual(capture.call_count, 60)
        ocr.assert_not_called()


if __name__ == '__main__':
    unittest.main()
