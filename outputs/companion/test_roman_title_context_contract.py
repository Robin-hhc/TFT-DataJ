"""Authorization tests at the OCR boundary; no inferred suffix identities."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from vision import Vision


CATALOG = [{'id': '10615', 'name': '拥抱 I'},
           {'id': '10616', 'name': '拥抱 II'},
           {'id': '30615', 'name': '拥抱 III'},
           {'id': '30679', 'name': '秘法帮派 II++'}]


def title_pixels():
    image = Image.new('RGB', (300, 100), '#182a35')
    draw = ImageDraw.Draw(image)
    for box in ((70, 30, 75, 69), (76, 30, 100, 35),
                (95, 35, 100, 69), (110, 30, 115, 69),
                (115, 63, 140, 69), (160, 30, 164, 69)):
        draw.rectangle(box, fill='#f5e7c9')
    return image


class RomanTitleContextContractTests(unittest.TestCase):
    def recognize(self, focused, *, observed='拥抱', catalog=None, image=None, initial=()):
        crop = image if image is not None else title_pixels()
        vision = Vision()
        reads = iter(focused)
        initial = iter(initial)
        calls = []

        def engine(array, **kwargs):
            calls.append(array.shape)
            # Original band and old tight views differ from this padded
            # complete-title view: ink y30..69 plus 11px context above/below.
            if array.shape[:2] == (62, 111):
                text, score = next(reads, ('', 0))
            else:
                text, score = next(initial, (observed, .99))
            return SimpleNamespace(txts=[text], scores=[score])

        vision.engine = engine
        with patch('vision.roman_evidence', return_value=None):
            result = vision.read_name(crop, CATALOG if catalog is None else catalog)
        return result, calls

    def test_two_direct_complete_context_reads_resolve_exact_suffix(self):
        for suffix, identity in [('I', '10615'), ('II', '10616'), ('III', '30615')]:
            with self.subTest(suffix=suffix):
                result, calls = self.recognize([('拥抱'+suffix, .99)]*2)
                self.assertEqual(result['status'], 'resolved', result)
                self.assertEqual(result['id'], identity)
                self.assertEqual(sum(shape[:2] == (62, 111) for shape in calls), 2)

    def test_one_trusted_complete_context_read_is_insufficient(self):
        result, _ = self.recognize([('拥抱I', .99), ('拥抱I', .899)])
        self.assertEqual(result['status'], 'unrecognized', result)
        self.assertNotIn('id', result)

    def test_context_quality_conflict_cannot_be_outvoted(self):
        result, _ = self.recognize([('拥抱I', .99), ('拥抱II', .99)])
        self.assertEqual(result['status'], 'conflict', result)
        self.assertNotIn('id', result)

    def test_earlier_complete_quality_vetoes_two_context_reads(self):
        result, _ = self.recognize([('拥抱I', .99), ('拥抱I', .99)],
                                   initial=[('拥抱II', .99)])
        self.assertEqual(result['status'], 'conflict', result)
        self.assertNotIn('id', result)

    def test_numeric_lowercase_or_incomplete_reads_do_not_assign_suffix(self):
        for text in ('拥抱1', '拥抱l', '拥抱!', '拥抱', '拥抱II+'):
            with self.subTest(text=text):
                result, _ = self.recognize([(text, .99), (text, .99)])
                self.assertEqual(result['status'], 'unrecognized', result)
                self.assertNotIn('id', result)

    def test_unknown_prefix_does_not_add_context_calls(self):
        result, calls = self.recognize([('拥抱I', .99), ('拥抱I', .99)], observed='未知标题')
        self.assertEqual(result['status'], 'unrecognized', result)
        self.assertFalse(any(shape[:2] == (62, 111) for shape in calls))

    def test_two_complete_reads_cannot_disambiguate_duplicate_catalog_rows(self):
        result, _ = self.recognize([('拥抱I', .99), ('拥抱I', .99)],
                                  catalog=CATALOG+[{'id': 'other', 'name': '拥抱 I'}])
        self.assertEqual(result['status'], 'ambiguous', result)
        self.assertNotIn('id', result)

    def test_complete_plus_suffix_retains_exact_identity(self):
        result, _ = self.recognize([('秘法帮派II++', .99), ('秘法帮派II++', .99)], observed='秘法帮派')
        self.assertEqual(result['status'], 'resolved', result)
        self.assertEqual(result['id'], '30679')

    def test_plus_tier_conflict_rejects_both_context_readings(self):
        result, _ = self.recognize([('秘法帮派II+', .99), ('秘法帮派II++', .99)],
                                   observed='秘法帮派',
                                   catalog=CATALOG+[{'id': '30678', 'name': '秘法帮派 II+'}])
        self.assertEqual(result['status'], 'conflict', result)
        self.assertNotIn('id', result)

    def test_earlier_plus_tier_vetoes_two_matching_context_titles(self):
        result, _ = self.recognize([('秘法帮派II++', .99)]*2, observed='秘法帮派',
                                   initial=[('秘法帮派II+', .99)],
                                   catalog=CATALOG+[{'id': '30678', 'name': '秘法帮派 II+'}])
        self.assertEqual(result['status'], 'conflict', result)
        self.assertNotIn('id', result)

    def test_flat_background_cannot_create_context_title(self):
        result, calls = self.recognize([('拥抱I', .99), ('拥抱I', .99)],
                                      image=Image.new('RGB', (300, 100), '#182a35'))
        self.assertEqual(result['status'], 'unrecognized', result)
        self.assertEqual(len(calls), 3)

    def test_context_cannot_count_an_old_binary_input_as_a_second_read(self):
        crop = title_pixels()
        for point in ((0, 0), (299, 0), (0, 99), (299, 99)):
            crop.putpixel(point, (245, 231, 201))
        binary = ImageOps.grayscale(crop).point(lambda value: 255 if value > 200 else 0).convert('RGB')
        binary_pixels = np.asarray(binary)[:, :, ::-1].copy()
        exact_calls = []
        vision = Vision()

        def engine(array, **kwargs):
            exact = array.shape == binary_pixels.shape and np.array_equal(array, binary_pixels)
            if exact:
                exact_calls.append(array.copy())
            return SimpleNamespace(txts=['拥抱I' if exact else '拥抱'], scores=[.99])

        vision.engine = engine
        with patch('vision.roman_evidence', return_value=None):
            result = vision.read_name(crop, CATALOG)
        self.assertEqual(result['status'], 'unrecognized', result)
        self.assertNotIn('id', result)
        self.assertEqual(len(exact_calls), 1)

    def test_identical_native_and_gray_contexts_supply_only_one_new_read(self):
        crop = ImageOps.grayscale(title_pixels()).point(lambda value: 255 if value > 200 else 0).convert('RGB')
        context_calls = []
        vision = Vision()

        def engine(array, **kwargs):
            focused = array.shape[:2] == (62, 111)
            if focused:
                context_calls.append(array.copy())
            return SimpleNamespace(txts=['拥抱I' if focused else '拥抱'], scores=[.99])

        vision.engine = engine
        with patch('vision.roman_evidence', return_value=None):
            result = vision.read_name(crop, CATALOG)
        self.assertEqual(result['status'], 'unrecognized', result)
        self.assertNotIn('id', result)
        self.assertEqual(len(context_calls), 1)


if __name__ == '__main__':
    unittest.main()
