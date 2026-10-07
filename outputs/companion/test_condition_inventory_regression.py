"""Native inventory details remain bounded when the assistant badge overlaps a border."""
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

from condition_reader import ConditionReader, detail_boxes
from entity_identity import EntityResolver
from vision import Vision


FIXTURES = Path(__file__).parent / 'fixtures'


class InventoryDetailRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vision = Vision()
        cls.vision.prepare()

    def fixture(self, name):
        path = FIXTURES / f'condition-inventory-{name}-20261008.png'
        metadata = json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), metadata['derived_png_sha256'])
        with Image.open(path) as source:
            return source.convert('RGB'), metadata

    def test_native_glove_detail_with_badge_occlusion_uses_primary_title(self):
        image, metadata = self.fixture('glove')
        result = ConditionReader(self.vision, EntityResolver(metadata['catalog'])).read(image)
        self.assertEqual(result['status'], 'resolved', result)
        self.assertEqual(result['entity']['id'], '1009')
        self.assertEqual(result['entity']['name'], '拳套')
        self.assertEqual(result['entity']['kind'], 'equip')
        self.assertEqual(result['evidence']['layout'], 's18_left_inventory_detail')
        self.assertLess(result['evidence']['title_rect'][3], 260)
        self.assertFalse(result['records_selected'])

    def test_native_tear_detail_keeps_its_identity_without_badge_occlusion(self):
        image, metadata = self.fixture('tear')
        result = ConditionReader(self.vision, EntityResolver(metadata['catalog'])).read(image)
        self.assertEqual(result['status'], 'resolved', result)
        self.assertEqual(result['entity']['id'], '1004')
        self.assertEqual(result['entity']['name'], '女神之泪')
        self.assertFalse(result['records_selected'])

    def test_inventory_header_without_its_icon_does_not_reach_ocr(self):
        image, metadata = self.fixture('tear')
        ImageDraw.Draw(image).rectangle((294, 48, 512, 300), fill='black')
        with patch.object(self.vision, 'read_name', side_effect=AssertionError('Unverified header reached OCR')):
            result = ConditionReader(self.vision, EntityResolver(metadata['catalog'])).read(image)
        self.assertIsNone(result['entity'])
        self.assertEqual(result['reason'], 'detail_header_icon_unconfirmed')

    def test_known_secondary_title_in_the_body_cannot_replace_primary_title(self):
        image, metadata = self.fixture('tear')
        glove, _ = self.fixture('glove')
        image.paste(glove.crop((500, 45, 1160, 250)), (500, 700))
        result = ConditionReader(self.vision, EntityResolver(metadata['catalog'])).read(image)
        self.assertEqual(result['entity']['id'], '1004', result)
        self.assertEqual(set(filter(None, result['evidence']['readings'])), {'女神之泪'})

    def test_short_border_occlusion_still_requires_real_top_and_bottom_caps(self):
        image, _ = self.fixture('glove')
        for rect in ((260, 22, 1185, 48), (260, 1940, 1185, 1975)):
            with self.subTest(removed_border=rect):
                incomplete = image.copy()
                ImageDraw.Draw(incomplete).rectangle(rect, fill='black')
                self.assertEqual(detail_boxes(incomplete), [])

    def test_long_missing_border_cannot_authorise_an_inventory_panel(self):
        image, _ = self.fixture('glove')
        ImageDraw.Draw(image).rectangle((260, 22, 290, 350), fill='black')
        self.assertEqual(detail_boxes(image), [])

    def test_missing_title_cannot_fall_through_to_a_recipe_name(self):
        image, metadata = self.fixture('tear')
        title_pixels = image.crop((500, 45, 1160, 250))
        ImageDraw.Draw(image).rectangle((500, 45, 1160, 250), fill='black')
        # Put actual known glyphs in the body: only their placement is
        # synthetic. No title OCR may be attempted on that recipe area.
        image.paste(title_pixels, (500, 700))
        with patch.object(self.vision, 'read_name', side_effect=AssertionError('Body reached OCR')):
            result = ConditionReader(self.vision, EntityResolver(metadata['catalog'])).read(image)
        self.assertIsNone(result['entity'])
        self.assertEqual(result['reason'], 'no_primary_title_strokes')


if __name__ == '__main__':
    unittest.main()
