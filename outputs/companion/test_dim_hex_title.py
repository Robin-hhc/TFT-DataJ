"""Real dim title pixels and conservative OCR-consensus contracts."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw

from vision import Vision
from choice_reader import normalize_name


FIXTURE = Path(__file__).parent / 'fixtures/hex-dim-hug-title-20261018'
CATALOG = [{'id': '10615', 'name': '拥抱 I'},
           {'id': '10616', 'name': '拥抱 II'}]


def dim_strokes(background=55, foreground=135):
    image = Image.new('RGB', (180, 50), (background,) * 3)
    draw = ImageDraw.Draw(image)
    for rectangle in ((45, 20, 49, 43), (53, 22, 70, 26),
                      (67, 26, 71, 42), (78, 20, 82, 43),
                      (82, 37, 100, 41), (116, 21, 119, 43),
                      (126, 21, 129, 43)):
        draw.rectangle(rectangle, fill=(foreground,) * 3)
    return image


class DimHexTitleTests(unittest.TestCase):
    def test_real_dim_hug_ii_title_preserves_exact_quality(self):
        evidence = json.loads(FIXTURE.with_suffix('.json').read_text(encoding='utf-8'))
        png = FIXTURE.with_suffix('.png')
        self.assertEqual(hashlib.sha256(png.read_bytes()).hexdigest(), evidence['crop_sha256'])
        with Image.open(png) as image:
            result = Vision().read_name(image, evidence['catalog'])
        self.assertEqual(result['status'], 'resolved', result)
        self.assertEqual(result['id'], '10616')
        self.assertEqual(result['name'], '拥抱 II')
        self.assertGreaterEqual(sum(normalize_name(value) == normalize_name('拥抱 II')
                                    for value in result['readings']), 2)

    def recognize_contract(self, crop, responses, initial=('', 0)):
        """The OCR boundary supplies trusted reads only for focused pixels.

        Initial name views retain the band's width or enlarge it; focused views
        are narrower. This tests authorization from actual input/output at
        Vision.read_name, without patching stroke extraction or title matching.
        """
        responses = iter(responses)
        vision = Vision()

        def engine(array, **kwargs):
            text, score = next(responses, ('', 0)) if array.shape[1] < crop.width else initial
            return SimpleNamespace(txts=[text], scores=[score])

        vision.engine = engine
        with patch('vision.roman_evidence', return_value=None):
            return vision.read_name(crop, CATALOG)

    def test_dim_context_requires_two_trusted_exact_title_reads(self):
        result = self.recognize_contract(dim_strokes(), [('拥抱Ⅱ', .99), ('拥抱Ⅱ', .99)])
        self.assertEqual(result['status'], 'resolved')
        self.assertEqual(result['id'], '10616')

    def test_one_trusted_dim_read_cannot_authorize_identity(self):
        result = self.recognize_contract(dim_strokes(), [('拥抱Ⅱ', .99), ('拥抱Ⅱ', .899)])
        self.assertEqual(result['status'], 'unrecognized')
        self.assertNotIn('id', result)

    def test_conflicting_dim_quality_titles_veto_identity(self):
        result = self.recognize_contract(dim_strokes(), [('拥抱I', .99), ('拥抱Ⅱ', .99)])
        self.assertEqual(result['status'], 'conflict')
        self.assertNotIn('id', result)

    def test_conflicting_initial_title_vetoes_dim_consensus(self):
        # One initial exact title plus two conflicting fallback reads must not
        # be turned into majority voting. Preserve all trusted title evidence.
        image = dim_strokes()
        reads = iter([('拥抱I', .99), ('', 0), ('', 0),
                      ('拥抱Ⅱ', .99), ('拥抱Ⅱ', .99)])
        vision = Vision()

        def engine(array, **kwargs):
            text, score = next(reads, ('', 0))
            return SimpleNamespace(txts=[text], scores=[score])

        vision.engine = engine
        with patch('vision.roman_evidence', return_value=None):
            result = vision.read_name(image, CATALOG)
        self.assertEqual(result['status'], 'conflict')
        self.assertNotIn('id', result)

    def test_dim_numeric_or_incomplete_suffix_never_becomes_roman_quality(self):
        for text in ('拥抱2', '拥抱1', '拥抱lI', '拥抱', '拥抱ⅡI'):
            with self.subTest(text=text):
                result = self.recognize_contract(dim_strokes(), [(text, .99), (text, .99)])
                self.assertEqual(result['status'], 'unrecognized')
                self.assertNotIn('id', result)

    def test_flat_low_contrast_and_smooth_backgrounds_cannot_authorize_identity(self):
        gradient = np.tile(np.linspace(35, 135, 180, dtype=np.uint8), (50, 1))
        backgrounds = {'flat': Image.new('RGB', (180, 50), (110,) * 3),
                       'low_contrast': dim_strokes(background=70, foreground=90),
                       'smooth_background': Image.fromarray(gradient).convert('RGB')}
        for label, image in backgrounds.items():
            with self.subTest(background=label):
                result = self.recognize_contract(image, [('拥抱Ⅱ', .99), ('拥抱Ⅱ', .99)])
                self.assertEqual(result['status'], 'unrecognized')
                self.assertNotIn('id', result)


if __name__ == '__main__':
    unittest.main()
