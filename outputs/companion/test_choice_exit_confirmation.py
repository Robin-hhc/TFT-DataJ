"""Real choice/exit pixels through bounded re-publication callbacks."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image
from app import QApplication
from vision import tracked_signature, unchanged
import test_runtime_stability as fixtures


FIXTURE = Path(__file__).parent / 'fixtures/hex-exit-20261007.json'


class ChoiceExitConfirmationTests(unittest.TestCase):
    tearDown = fixtures.RuntimeStability.tearDown

    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])
        cls.evidence = json.loads(FIXTURE.read_text(encoding='utf-8'))
        cls.frames = {}
        for entry in cls.evidence['frames']:
            path = FIXTURE.parent / entry['derived_file']
            if hashlib.sha256(path.read_bytes()).hexdigest() != entry['derived_png_sha256']:
                raise AssertionError('Real exit fixture hash changed')
            with Image.open(path) as opened:
                cls.frames[entry['label']] = opened.convert('RGB')

    def setUp(self):
        fixtures.RuntimeStability.setUp(self)
        self.clock = 100.0
        self.stack.enter_context(patch('app.time.monotonic', side_effect=lambda: self.clock))
        self.stack.enter_context(patch('app.win.user.SetWindowPos', return_value=True))
        self.stack.enter_context(patch.object(self.p.items, 'tick'))
        self.p.automatic.setChecked(True)
        self.p.last_stage_probe = self.p.last_resource_guard = self.clock
        self.obs = deepcopy(self.evidence['observation'])
        self.p.adapter.hexes = lambda comp=None: {'data': self.evidence['statistics_rows'], 'fetched_at': 0}

    def run_next(self):
        work, done, _ = self.jobs.pop(0)
        done(work())

    def drain(self):
        while self.jobs:
            self.run_next()

    def visible(self):
        self.qt.processEvents()
        return any(overlay.isVisible() for overlay in self.p.overlays)

    def publish_initial(self):
        frame = self.frames['choice']
        self.p.last_frame = frame
        self.p.last_capture = self.clock
        with patch.object(self.p.vision, 'analyze_fast', return_value=self.obs):
            self.p.analyze(frame, True)
            self.drain()
        self.assertTrue(self.visible())

    def accept(self, frame):
        self.p.accept_frame((frame, self.binding), False,
                            (([], None), tracked_signature(frame, self.obs)), self.clock)

    def reread_animation(self):
        self.clock += 31
        with patch.object(self.p.vision, 'analyze_fast', return_value=self.obs):
            self.accept(self.frames['animation'])
            self.drain()

    def test_real_exit_animation_is_not_republished_from_its_own_ocr_frame(self):
        self.publish_initial()
        self.reread_animation()
        self.assertFalse(self.visible(), 'The real exit frame repaints old ranks without a later capture')
        self.assertIsNone(self.p.stats_payload)
        self.clock += .6
        with patch.object(self.p, 'analyze'):
            self.accept(self.frames['board'])
        self.assertFalse(self.visible())
        self.assertIsNone(self.p.stats_payload)

    def test_initial_choice_has_no_extra_confirmation_capture(self):
        self.publish_initial()
        self.assertEqual(self.p.session.stage, '2-1')
        self.assertEqual(self.jobs, [])

    def test_confirmed_new_capture_republishes_after_one_frame(self):
        self.publish_initial()
        self.reread_animation()
        self.assertFalse(self.visible())
        self.clock += .5
        self.accept(self.frames['animation'].copy())
        self.drain()
        self.assertTrue(self.visible())

    def test_same_image_object_cannot_confirm_itself(self):
        self.publish_initial()
        self.reread_animation()
        self.clock += .5
        self.accept(self.frames['animation'])
        self.drain()
        self.assertFalse(self.visible())

    def test_manual_deadline_not_extended_by_failed_later_capture(self):
        self.publish_initial()
        self.p.automatic.setChecked(False)
        self.publish_initial()
        self.p.once_active = self.p.once_ocr_pending = True
        self.p.once_deadline = 140.0
        self.reread_animation()
        deadline = self.p.once_deadline
        self.clock += .5
        with patch.object(self.p, 'analyze'):
            self.accept(self.frames['board'])
        self.assertEqual(self.p.once_deadline, deadline)
        self.clock = deadline + .01
        with patch.object(self.p, 'request_capture'):
            self.p.tick()
        self.assertFalse(self.p.once_active)
        self.assertFalse(self.visible())

    def test_real_refresh_new_title_waits_for_one_matching_capture(self):
        self.publish_initial()
        changed = self.frames['choice'].copy()
        changed.paste(changed.crop((1530, 700, 2300, 880)), (520, 700))
        updated = deepcopy(self.obs)
        updated['cards'][0]['resolution'] = deepcopy(updated['cards'][1]['resolution'])
        updated['cards'][0]['raw_text'] = updated['cards'][1]['raw_text']
        self.assertFalse(unchanged(tracked_signature(changed, self.obs), self.p.signature))
        self.clock += 2
        with patch.object(self.p.vision, 'analyze_fast', return_value=updated):
            self.accept(changed)
            self.drain()
        self.assertFalse(self.visible())
        self.clock += .5
        self.accept(changed.copy())
        self.drain()
        self.assertTrue(self.visible())
        self.assertEqual(self.p.session.choices, ('20480', '20480', '20471'))

    def test_later_capture_during_ocr_can_confirm_without_third_capture(self):
        self.publish_initial()
        self.clock += 2
        with patch.object(self.p.vision, 'analyze_fast', return_value=self.obs):
            self.accept(self.frames['animation'])
            work, done, _ = self.jobs.pop(0)
            result = work()
        self.clock += .5
        self.accept(self.frames['animation'].copy())
        done(result)
        self.drain()
        self.assertTrue(self.visible())
        self.assertIsNone(self.p.pending_choice_confirmation)

    def test_invalidated_pending_ocr_cannot_restore_old_ranks(self):
        self.publish_initial()
        self.reread_animation()
        pending = self.p.pending_choice_confirmation
        self.assertIsNotNone(pending)
        self.p.invalidate()
        pending[3](pending[1], pending[2])
        self.assertIsNone(self.p.pending_choice_confirmation)
        self.assertFalse(self.visible())
        self.assertEqual(self.jobs, [])

    def test_foreground_loss_clears_pending_confirmation(self):
        self.publish_initial()
        self.reread_animation()
        with patch('app.win.capture_block_reason', return_value='not_foreground'):
            self.p.tick()
        self.assertIsNone(self.p.pending_choice_confirmation)
        self.assertFalse(self.visible())

    def test_pending_ocr_does_not_start_extra_recognition(self):
        self.publish_initial()
        self.reread_animation()
        self.p.analyze(self.frames['animation'], True)
        self.assertFalse(self.p.ocr_busy)
        self.assertEqual(self.jobs, [])

    def test_capture_worker_uses_pending_observation_for_pixels(self):
        self.publish_initial()
        self.reread_animation()
        self.clock += .5
        self.p.captured((self.frames['animation'].copy(), self.binding), False, self.clock)
        self.drain()
        self.assertTrue(self.visible())

    def test_item_proposal_cannot_confirm_pending_augment(self):
        self.publish_initial()
        self.reread_animation()
        frame = self.frames['animation'].copy()
        self.clock += .5
        with patch.object(self.p.items, 'ingest', return_value=True):
            self.p.accept_frame((frame, self.binding), False,
                                (([(100, 400, 200, 500)] * 3, None),
                                 tracked_signature(frame, self.obs)), self.clock)
        self.assertFalse(self.visible())
        self.assertIsNone(self.p.stats_payload)

    def test_first_same_round_probe_preserves_required_later_capture(self):
        self.publish_initial()
        self.reread_animation()
        pending = self.p.pending_choice_confirmation
        self.p.last_probe_stage = None
        self.p.probe_stage()
        _, done, _ = self.jobs.pop(0)
        done('2-1')
        self.assertIs(self.p.pending_choice_confirmation, pending)
        self.assertTrue(self.p.choice_recheck_required)
        self.assertFalse(self.visible())

    def test_changed_round_probe_discards_pending_old_choice(self):
        self.publish_initial()
        self.reread_animation()
        token = self.p.session.token()
        self.p.last_probe_stage = '2-1'
        self.p.probe_stage()
        _, done, _ = self.jobs.pop(0)
        done('2-2')
        self.assertIsNone(self.p.pending_choice_confirmation)
        self.assertFalse(self.p.session.accepts(token))
        self.assertFalse(self.visible())


if __name__ == '__main__':
    unittest.main()
