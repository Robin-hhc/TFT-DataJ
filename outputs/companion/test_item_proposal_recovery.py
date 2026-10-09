"""Confirmed item titles survive a missing outline proposal, never changed text."""
from PIL import Image, ImageDraw
import unittest
from unittest.mock import patch

from item_controller import inspect_items
from item_vision import same_item_text
import test_item_overlay_stability as fixtures


class ItemProposalRecoveryTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.ItemOverlayStabilityTests.setUpClass.__func__)
    setUp = fixtures.ItemOverlayStabilityTests.setUp
    tearDown = fixtures.ItemOverlayStabilityTests.tearDown
    run_one = fixtures.ItemOverlayStabilityTests.run_one
    visible = fixtures.ItemOverlayStabilityTests.visible

    def inspect_without_outlines(self, frame):
        with patch('item_controller.item_boxes', return_value=[]):
            return inspect_items(frame, tuple(self.boxes))

    def test_same_titles_keep_loaded_ranks_when_outline_proposal_disappears(self):
        generation = self.p.items.generation
        rows = self.p.items.rows
        self.clock += .6
        with patch('item_controller.analyze_items') as ocr:
            handled = self.p.items.ingest(self.frame, self.binding,
                prepared=self.inspect_without_outlines(self.frame), frame_time=self.clock)
        self.assertTrue(handled, 'Missing card outlines discarded a verified item offer')
        self.assertTrue(self.visible())
        self.assertIs(self.p.items.rows, rows)
        self.assertEqual(self.p.items.generation, generation)
        self.assertEqual(self.p.items.last_seen, self.clock)
        self.assertEqual(self.jobs, [])
        self.assertFalse(ocr.called)

    def test_pending_statistics_finish_after_missing_outline_proposal(self):
        self.p.items.cache.clear()
        self.p.items.start_queries()
        work, done, _ = self.jobs.pop(0)
        result = work()
        self.clock += .6
        self.p.items.ingest(self.frame, self.binding,
            prepared=self.inspect_without_outlines(self.frame), frame_time=self.clock)
        done(result)
        self.assertTrue(self.p.items.active, 'Missing outlines canceled the pending data request')
        self.assertTrue(all(row['global']['status'] == 'ok' for row in self.p.items.rows))
        while self.jobs:
            self.run_one()
        self.assertTrue(self.visible())

    def test_changed_title_without_outlines_clears_ranks_immediately(self):
        changed = self.frame.copy()
        ImageDraw.Draw(changed).rectangle((260, 850, 420, 865), fill='black')
        self.clock += .6
        self.assertFalse(self.p.items.ingest(changed, self.binding,
            prepared=self.inspect_without_outlines(changed), frame_time=self.clock))
        self.assertFalse(self.p.items.active)
        self.assertFalse(self.visible())

    def test_disappeared_header_without_outlines_clears_ranks_immediately(self):
        changed = self.frame.copy()
        ImageDraw.Draw(changed).rectangle((820, 690, 1100, 700), fill='black')
        self.clock += .6
        self.assertFalse(self.p.items.ingest(changed, self.binding,
            prepared=self.inspect_without_outlines(changed), frame_time=self.clock))
        self.assertFalse(self.p.items.active)
        self.assertFalse(self.visible())

    def test_refresh_shape_proposal_does_not_override_confirmed_item_titles(self):
        self.clock += .6
        with patch('app.may_be_choice', return_value=True), \
                patch('item_controller.item_boxes', return_value=[]), \
                patch.object(self.p, 'analyze') as augment_ocr:
            self.p.captured((self.frame, self.binding), False, self.clock)
            self.run_one()
        self.assertTrue(self.p.items.active, 'A coarse augment proposal discarded exact item titles')
        self.assertTrue(self.visible())
        self.assertFalse(augment_ocr.called)

    def test_true_scene_change_still_routes_to_augment_recognition(self):
        self.clock += .6
        changed = Image.new('RGB', self.frame.size)
        self.p.stage_window_until = self.clock + 60
        with patch('app.may_be_choice', return_value=True), \
                patch.object(self.p, 'analyze') as augment_ocr:
            self.p.captured((changed, self.binding), False, self.clock)
            self.run_one()
        self.assertFalse(self.p.items.active)
        self.assertFalse(self.visible())
        augment_ocr.assert_called_once()

    def test_no_prior_titles_cannot_authorize_a_missing_proposal(self):
        frame = Image.new('RGB', self.frame.size)
        with patch('item_controller.item_boxes', return_value=[]):
            boxes, signature = inspect_items(frame)
        self.assertEqual(boxes, [])
        self.assertFalse(signature.masks)

    def test_missing_proposal_cannot_retain_titles_after_image_size_changes(self):
        self.clock += .6
        resized = Image.new('RGB', (self.frame.width, self.frame.height+10))
        resized.paste(self.frame, (0, 0))
        prepared = self.inspect_without_outlines(resized)
        self.assertTrue(same_item_text(prepared[1], self.signature))
        self.assertFalse(self.p.items.ingest(resized, self.binding,
            prepared=prepared, frame_time=self.clock))
        self.assertFalse(self.p.items.active)
        self.assertFalse(self.visible())


if __name__ == '__main__':
    unittest.main()
