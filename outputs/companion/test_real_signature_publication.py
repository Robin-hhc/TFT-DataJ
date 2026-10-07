"""Real text pixels through live OCR publication and visible Qt callbacks.

Brightness changes are controlled derivatives, not missing captured frames.
All windows are owned by the test and placed outside the user's desktop.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageEnhance

from app import QApplication
from vision import tracked_signature, unchanged
import test_runtime_stability as fixtures


FIXTURE = Path(__file__).parent / 'fixtures/hex-signature-20261007'


class RealSignaturePublicationTests(unittest.TestCase):
    tearDown = fixtures.RuntimeStability.tearDown

    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])
        cls.evidence = json.loads(FIXTURE.with_suffix('.json').read_text(encoding='utf-8'))
        png = FIXTURE.with_suffix('.png')
        if hashlib.sha256(png.read_bytes()).hexdigest() != cls.evidence['derived_png_sha256']:
            raise AssertionError('Real text fixture SHA-256 changed')
        with Image.open(png) as image:
            cls.dark = image.convert('RGB')
        cls.bright = ImageEnhance.Brightness(cls.dark).enhance(1.4)

    def setUp(self):
        fixtures.RuntimeStability.setUp(self)
        self.clock = 100.0
        self.stack.enter_context(patch('app.time.monotonic', side_effect=lambda: self.clock))
        self.stack.enter_context(patch('app.win.user.SetWindowPos', return_value=True))
        self.stack.enter_context(patch.object(self.p.items, 'tick'))
        self.p.automatic.setChecked(True)
        self.p.last_stage_probe = self.p.last_resource_guard = self.clock
        self.observation = deepcopy(self.evidence['observation'])
        for card, reviewed in zip(self.observation['cards'], self.evidence['reviewed_cards']):
            card['raw_text'] = reviewed['name']
            card['resolution'] = {'status': 'resolved', 'id': reviewed['id'],
                                  'name': reviewed['name'], 'readings': [reviewed['name']] * 3}
        # The identity reader has its own genuine OCR replay. These tests isolate
        # publication with real signature extraction and real statistics callbacks.
        self.p.adapter.hexes = lambda comp=None: {'data': [
            {'hexId': card['id'], 'roundStats': [
                {'round': 1, 'roundLabel': '3-2', 'avgPlacement': 4.5, 'sampleCount': 300}]}
            for card in self.evidence['reviewed_cards']], 'fetched_at': 0}

    def visible(self):
        self.qt.processEvents()
        return any(overlay.isVisible() for overlay in self.p.overlays)

    def run_next(self):
        # RuntimeStability's queue contains fn/done/failed only, in callback order.
        work, done, _ = self.jobs.pop(0)
        done(work())

    def complete_statistics(self):
        while self.jobs:
            self.run_next()

    def recognize(self, frame):
        self.p.last_frame = frame
        self.p.last_capture = self.clock
        with patch.object(self.p.vision, 'analyze_fast', return_value=self.observation):
            self.p.analyze(frame, True)
            self.run_next()

    def accept(self, frame):
        signature = tracked_signature(frame, self.observation)
        with patch.object(self.p, 'analyze') as analyze:
            self.p.accept_frame((frame, self.binding), False,
                                (([], None), signature), self.clock)
        return analyze

    def publish_bright(self):
        self.recognize(self.bright)
        self.complete_statistics()
        self.assertTrue(self.visible())

    def test_real_first_frame_signature_can_validate_itself(self):
        signature = tracked_signature(self.dark, self.observation)
        self.assertTrue(all(np.count_nonzero(mask) >= 8 for mask in signature.masks))
        self.assertTrue(unchanged(signature, signature))

    def test_real_first_ocr_publishes_verifiable_statistics_and_overlay(self):
        self.recognize(self.dark)
        self.complete_statistics()
        self.assertTrue(self.visible(), 'Legible real titles must not wait forever for brightness >= 200')
        self.assertEqual(self.p.session.stage, '3-2')
        self.assertIsNotNone(self.p.stats_payload)

    def test_dark_to_bright_keeps_visible_ranks_without_show_hide_blink(self):
        from PySide6.QtCore import QObject, QEvent
        events = []

        class VisibilityObserver(QObject):
            def eventFilter(self, widget, event):
                if event.type() in (QEvent.Type.Show, QEvent.Type.Hide):
                    events.append(event.type())
                return False

        observer = VisibilityObserver()
        for overlay in self.p.overlays:
            overlay.installEventFilter(observer)
        try:
            self.recognize(self.dark)
            self.complete_statistics()
            self.assertTrue(self.visible())
            self.clock += .5
            self.accept(self.bright)
            self.assertTrue(self.visible())
            self.clock += .5
            self.accept(self.bright.copy())
            self.assertTrue(self.visible())
            self.assertEqual(events, [QEvent.Type.Show] * 3)
        finally:
            for overlay in self.p.overlays:
                overlay.removeEventFilter(observer)

    def test_excessively_dim_frame_invalidates_instead_of_trusting_empty_masks(self):
        self.publish_bright()
        token = self.p.session.token()
        self.clock += .5
        self.accept(ImageEnhance.Brightness(self.dark).enhance(.25))
        self.assertFalse(self.visible())
        self.assertFalse(self.p.session.accepts(token))
        self.assertIsNone(self.p.stats_payload)

    def test_repeated_dark_frames_do_not_renew_manual_request_deadline(self):
        self.p.automatic.setChecked(False)
        self.p.once_active = self.p.once_ocr_pending = True
        self.p.once_deadline = 103.0
        for now in (100.0, 102.0):
            self.clock = now
            self.recognize(ImageEnhance.Brightness(self.dark).enhance(.25))
            self.assertEqual(self.p.once_deadline, 103.0)
            self.assertTrue(self.p.once_active)
            self.assertTrue(self.p.once_ocr_pending)
            self.assertEqual(self.jobs, [])
        self.clock = 103.001
        self.p.tick()
        self.assertFalse(self.p.once_active)
        self.assertFalse(self.p.once_ocr_pending)
        self.assertFalse(self.visible())

    def test_delayed_unreliable_ocr_does_not_renew_manual_deadline(self):
        self.p.automatic.setChecked(False)
        self.p.once_active = self.p.once_ocr_pending = True
        self.p.once_deadline = 103.0
        frame = ImageEnhance.Brightness(self.dark).enhance(.25)
        self.p.last_frame = frame
        self.p.last_capture = self.clock
        with patch.object(self.p.vision, 'analyze_fast', return_value=self.observation):
            self.p.analyze(frame, True)
            work, done, _ = self.jobs.pop(0)
            result = work()
        self.clock = 102.0
        self.p.accept_frame((frame.copy(), self.binding), False,
                            (([], None), None), self.clock)
        done(result)
        self.run_next()  # pixel check of the newer, equally unreadable frame
        self.assertEqual(self.p.once_deadline, 103.0)
        self.assertTrue(self.p.once_ocr_pending)
        self.assertFalse(self.visible())

    def test_controlled_brightness_variants_preserve_the_same_real_text(self):
        baseline = tracked_signature(self.dark, self.observation)
        for factor in (.7, .8, 1.0, 1.2, 1.4):
            with self.subTest(factor=factor):
                current = tracked_signature(ImageEnhance.Brightness(self.dark).enhance(factor), self.observation)
                self.assertTrue(unchanged(current, current))
                self.assertTrue(unchanged(baseline, current))

    def test_each_real_refresh_animation_rejects_old_ranks(self):
        stem = FIXTURE.with_name('hex-refresh-20261007')
        evidence = json.loads(stem.with_suffix('.json').read_text(encoding='utf-8'))
        png = stem.with_suffix('.png')
        self.assertEqual(hashlib.sha256(png.read_bytes()).hexdigest(), evidence['derived_png_sha256'])
        with Image.open(png) as opened:
            packed = opened.convert('RGB')
        for entry in evidence['entries']:
            with self.subTest(case=entry['case_id']):
                # Each archived animation starts from an independent confirmed
                # offer, rather than the previous offer's pending recheck.
                self.p.invalidate()
                self.publish_bright()
                animated = self.dark.copy()
                animated.paste(packed.crop(entry['packed_crop_box']), tuple(entry['source_crop_box'][:2]))
                signature = tracked_signature(animated, self.observation)
                self.assertEqual(np.count_nonzero(signature.masks[entry['changed_slot'] + 1]), 0)
                self.accept(animated)
                self.assertFalse(self.visible())
                self.assertIsNone(self.p.stats_payload)

    def test_true_refresh_of_all_real_titles_clears_old_ranks(self):
        self.publish_bright()
        refreshed = self.bright.copy()
        boxes = [(card['box'][0][0] - 24, 710, card['box'][1][0] + 24, 866)
                 for card in self.observation['cards']]
        for index, box in enumerate(boxes):
            refreshed.paste(self.bright.crop(boxes[(index + 1) % 3]), box[:2])
        before = tracked_signature(self.bright, self.observation)
        after = tracked_signature(refreshed, self.observation)
        self.assertTrue(all(not np.array_equal(a, b) for a, b in zip(before.masks[1:], after.masks[1:])))
        self.accept(refreshed)
        self.assertFalse(self.visible())
        self.assertIsNone(self.p.stats_payload)

    def test_one_real_title_change_clears_and_late_stats_cannot_repaint(self):
        self.recognize(self.bright)
        work, late_stats, _ = self.jobs.pop(0)
        statistics = work()
        changed = self.bright.copy()
        first, third = self.observation['cards'][0], self.observation['cards'][2]
        box = (first['box'][0][0] - 24, 710, first['box'][1][0] + 24, 866)
        changed.paste(self.bright.crop(box), (third['box'][0][0] - 24, 710))
        before, after = (tracked_signature(frame, self.observation) for frame in (self.bright, changed))
        for original, current in zip(before.masks[:3], after.masks[:3]):
            np.testing.assert_array_equal(original, current)
        self.assertFalse(np.array_equal(before.masks[3], after.masks[3]))
        self.accept(changed)
        late_stats(statistics)
        self.assertFalse(self.visible())
        self.assertIsNone(self.p.stats_payload)

    def test_closed_choice_frame_clears_real_ranks(self):
        self.publish_bright()
        self.accept(Image.new('RGB', self.bright.size, 'black'))
        self.assertFalse(self.visible())
        self.assertIsNone(self.p.stats_payload)
        self.assertIsNone(self.p.session.stage)

    def test_changed_real_round_clears_even_with_identical_three_titles(self):
        self.publish_bright()
        stem = FIXTURE.with_name('hex-round-2-1-20261007')
        evidence = json.loads(stem.with_suffix('.json').read_text(encoding='utf-8'))
        png = stem.with_suffix('.png')
        self.assertEqual(hashlib.sha256(png.read_bytes()).hexdigest(), evidence['derived_png_sha256'])
        changed = self.bright.copy()
        with Image.open(png) as opened:
            changed.paste(opened.convert('RGB'), tuple(evidence['source_crop_box'][:2]))
        previous, current = (tracked_signature(frame, self.observation)
                             for frame in (self.bright, changed))
        self.assertFalse(np.array_equal(previous.masks[0], current.masks[0]))
        for a, b in zip(previous.masks[1:], current.masks[1:]):
            np.testing.assert_array_equal(a, b)
        self.accept(changed)
        self.assertFalse(self.visible())
        self.assertIsNone(self.p.stats_payload)


if __name__ == '__main__':
    unittest.main()
