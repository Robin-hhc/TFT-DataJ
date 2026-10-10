"""Controlled OCR-engine contract for independently resampled title pixels.

The pixels below are public synthetic strokes. Private original-frame replays
separately prove actual model recognition; these tests protect the extra view
and the complete-title, confidence and conflict rules at Vision.read_name.
"""
from collections import Counter
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw

from vision import Vision


CATALOG = [{'id': '10615', 'name': '拥抱 I'},
           {'id': '10616', 'name': '拥抱 II'}]


def title_crop():
    image = Image.new('RGB', (160, 45), '#193823')
    draw = ImageDraw.Draw(image)
    # Unequal strokes and colored edges keep Lanczos and Bicubic pixels
    # distinct without shipping any private game-frame crop.
    for box in ((20, 10, 24, 32), (30, 13, 50, 17), (48, 18, 53, 30),
                (65, 10, 70, 31), (70, 26, 91, 30), (106, 11, 109, 32)):
        draw.rectangle(box, fill='#f0eeda')
    draw.line((26, 12, 44, 32), fill='#55a070', width=2)
    return image


class TitleRetryViewTests(unittest.TestCase):
    def recognize(self, supplemental=('拥抱I', .923), first=('拥抱I', .93397),
                  native=('', 0), early=False, forbid_supplemental=False):
        crop = title_crop()
        # The independent fixture draws its outer white-stroke bounds at
        # x=20..109/y=10..32; the title reader's 4-pixel context is prescribed.
        tight = crop.crop((16, 6, 114, 37))
        width = round(tight.width * 1.6)
        wide = tight.resize((width, tight.height), Image.Resampling.BICUBIC)
        retry = tight.resize((width, tight.height), Image.Resampling.LANCZOS)
        pixels = lambda view: np.asarray(view)[:, :, ::-1].copy()
        primary_pixels, retry_pixels, native_pixels = map(pixels, (wide, retry, tight))
        self.assertFalse(np.array_equal(primary_pixels, retry_pixels))
        accepted_views = []
        calls = []
        vision = Vision()

        def engine(array, **kwargs):
            calls.append(array.copy())
            if array.shape == retry_pixels.shape and np.array_equal(array, retry_pixels):
                if forbid_supplemental:
                    self.fail('Already confirmed, conflicting or unknown title requested an extra OCR view')
                text, score = supplemental
                accepted_views.append('lanczos')
            elif array.shape == primary_pixels.shape and np.array_equal(array, primary_pixels):
                text, score = first
                accepted_views.append('bicubic')
            elif array.shape == native_pixels.shape and np.array_equal(array, native_pixels):
                text, score = native
            elif early:
                text, score = '拥抱I', .99
            else:
                text, score = '拥抱I', .82
            return SimpleNamespace(txts=[text], scores=[score])

        vision.engine = engine
        with patch('vision.roman_evidence', return_value=None):
            result = vision.read_name(crop, CATALOG)
        return result, accepted_views, calls

    def test_single_exact_wide_read_can_be_confirmed_by_distinct_resampling_pixels(self):
        result, accepted, _ = self.recognize()
        self.assertEqual(result['status'], 'resolved')
        self.assertEqual(result['id'], '10615')
        self.assertEqual(result['name'], '拥抱 I')
        self.assertEqual(Counter(accepted), {'bicubic': 1, 'lanczos': 1})
        self.assertEqual(sum(value == '拥抱I' for value in result['readings']), 2)

    def test_low_confidence_resampled_read_cannot_complete_consensus(self):
        result, accepted, _ = self.recognize(supplemental=('拥抱I', .899))
        self.assertEqual(accepted, ['bicubic', 'lanczos'])
        self.assertEqual(result['status'], 'unrecognized')
        self.assertNotIn('id', result)
        self.assertEqual(sum(value == '拥抱I' for value in result['readings']), 1)

    def test_resampled_numeric_suffix_cannot_be_rewritten_to_roman_quality(self):
        result, accepted, _ = self.recognize(supplemental=('拥抱1', .99))
        self.assertEqual(accepted, ['bicubic', 'lanczos'])
        self.assertEqual(result['status'], 'unrecognized')
        self.assertNotIn('id', result)
        self.assertIn('拥抱1', result['readings'])

    def test_resampled_different_quality_title_vetoes_identity(self):
        result, accepted, _ = self.recognize(supplemental=('拥抱II', .99))
        self.assertEqual(accepted, ['bicubic', 'lanczos'])
        self.assertEqual(result['status'], 'conflict')
        self.assertNotIn('id', result)
        self.assertEqual({row['id'] for row in result['candidates']}, {'10615', '10616'})

    def test_native_color_consensus_does_not_request_resampled_retry(self):
        result, accepted, calls = self.recognize(native=('拥抱I', .97), forbid_supplemental=True)
        self.assertEqual(result['id'], '10615')
        self.assertEqual(accepted, ['bicubic'])
        self.assertEqual(len(calls), 8)

    def test_native_color_conflict_does_not_request_resampled_retry(self):
        result, accepted, calls = self.recognize(native=('拥抱II', .99), forbid_supplemental=True)
        self.assertEqual(result['status'], 'conflict')
        self.assertNotIn('id', result)
        self.assertEqual(accepted, ['bicubic'])
        self.assertEqual(len(calls), 8)

    def test_already_confirmed_title_does_not_request_resampled_retry(self):
        result, accepted, calls = self.recognize(early=True, forbid_supplemental=True)
        self.assertEqual(result['id'], '10615')
        self.assertEqual(accepted, [])
        self.assertEqual(len(calls), 3)

    def test_missing_complete_catalog_title_does_not_request_resampled_retry(self):
        result, accepted, calls = self.recognize(first=('拥抱V', .99), forbid_supplemental=True)
        self.assertEqual(result['status'], 'unrecognized')
        self.assertNotIn('id', result)
        self.assertEqual(accepted, ['bicubic'])
        self.assertEqual(len(calls), 7)


if __name__ == '__main__':
    unittest.main()
