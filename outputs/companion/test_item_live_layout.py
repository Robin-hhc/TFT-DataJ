"""Private local MuMu screenshot regressions; never included in clean CI."""
from pathlib import Path
import json
import unittest

from PIL import Image, ImageDraw
import numpy as np
from bootstrap import ROOT
from item_controller import inspect_items
from item_vision import analyze_items, item_boxes, item_signature, same_item_text


RADIANT_FIVE = ROOT / 'work/input-experiments/match-20261006/readonly-200908-003-item_proposal.png'


class ItemLiveLayoutTests(unittest.TestCase):
    def test_real_same_offer_stays_stable_through_game_header_brightness_changes(self):
        signatures = []
        for index in range(2, 9):
            filename = RADIANT_FIVE.with_name(f'readonly-200908-{index:03d}-item_proposal.png')
            if not filename.exists():
                self.skipTest('Private local consecutive radiant-choice screenshots are not installed')
            with Image.open(filename) as frame:
                signatures.append(item_signature(frame, item_boxes(frame)))
        for index, (previous, current) in enumerate(zip(signatures, signatures[1:]), start=3):
            with self.subTest(frame=index):
                self.assertTrue(same_item_text(previous, current),
                                'Unchanged native equipment titles/header caused re-recognition')
                self.assertTrue(same_item_text(signatures[0], current))

    def test_real_five_radiant_cards_keep_all_left_to_right_slots(self):
        if not RADIANT_FIVE.exists():
            self.skipTest('Private local MuMu radiant-choice screenshot is not installed')
        with Image.open(RADIANT_FIVE) as frame:
            boxes = item_boxes(frame)
            self.assertEqual(len(boxes), 5, f'Full radiant row was truncated: {boxes}')
            centers = [(left + right) / 2 / frame.width for left, _, right, _ in boxes]
            for actual, expected in zip(centers, (.213, .359, .505, .650, .797)):
                self.assertAlmostEqual(actual, expected, delta=.01)

    def test_real_shop_grid_is_not_an_item_choice_proposal(self):
        filename = RADIANT_FIVE.with_name('readonly-200908-009-item_proposal.png')
        if not filename.exists():
            self.skipTest('Private local MuMu shop screenshot is not installed')
        with Image.open(filename) as frame:
            self.assertEqual(item_boxes(frame), [])

    def test_real_five_radiant_titles_have_exact_category_ids_and_slots(self):
        catalog_path = ROOT / 'work/s18-refresh-20260926/catalog.json'
        if not RADIANT_FIVE.exists() or not catalog_path.exists():
            self.skipTest('Private local MuMu screenshot/catalog is not installed')
        from vision import Vision
        vision = Vision()
        vision.prepare()
        catalog = json.loads(catalog_path.read_text(encoding='utf-8'))['data']['equip']
        with Image.open(RADIANT_FIVE) as frame:
            result = analyze_items(frame.convert('RGB'), vision, catalog)
        self.assertEqual(result['scene'], 'item_candidates')
        self.assertEqual([card['slot'] for card in result['cards']], [0, 1, 2, 3, 4])
        self.assertEqual([card['resolution'].get('id') for card in result['cards']], ['2085', '2091', '2078', '2092', '2070'])
        self.assertEqual([card['resolution'].get('name') for card in result['cards']], [
            '光明版狂徒铠甲', '光明版强袭者的链枷', '光明版适应性头盔', '光明版秘法手套', '光明版纳什之牙'])
        self.assertEqual({card['resolution']['candidates'][0]['type'] for card in result['cards']}, {'光明武器'})


class PrivateArtifactPixelRecoveryTests(unittest.TestCase):
    def test_real_four_artifact_titles_survive_changed_outline_brightness(self):
        filename = ROOT/'work/item-choice-samples/user-p3-720p-2232s.png'
        if not filename.exists():
            self.skipTest('Private original artifact-choice image is not installed')
        with Image.open(filename) as source:
            frame = source.convert('RGB')
        boxes = item_boxes(frame)
        self.assertEqual(len(boxes), 4)
        pixels = np.asarray(frame).copy()
        for left, top, right, bottom in boxes:
            height = bottom-top
            # Preserve every pixel in the actual title crop and shared header.
            for upper, lower in ((top, round(top+height*.44)),
                                 (round(top+height*.68), bottom)):
                pixels[upper:lower, left:right] = (pixels[upper:lower, left:right]*.65).astype('uint8')
        dimmed = Image.fromarray(pixels)
        self.assertEqual(item_boxes(dimmed), [], 'The original outline-dropout repro no longer applies')
        original = item_signature(frame, boxes)
        detected, tracked = inspect_items(dimmed, boxes)
        self.assertEqual(detected, [])
        self.assertTrue(same_item_text(tracked, original))
        regions = [(left, round(top+(bottom-top)*.44), right, round(top+(bottom-top)*.68))
                   for left, top, right, bottom in boxes]
        top = np.median([box[1] for box in boxes])
        height = np.median([box[3]-box[1] for box in boxes])
        regions.append((round(frame.width*.4), round(top-height*.48),
                        round(frame.width*.6), round(top-height*.08)))
        for region in regions:
            with self.subTest(erased_region=region):
                changed = dimmed.copy()
                ImageDraw.Draw(changed).rectangle(region, fill='black')
                self.assertFalse(same_item_text(inspect_items(changed, boxes)[1], original))


if __name__ == '__main__':
    unittest.main()
