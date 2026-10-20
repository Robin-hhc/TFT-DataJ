"""Recent original title bands must preserve complete Roman-I identities."""
import hashlib
import json
from pathlib import Path
import unittest

from PIL import Image

from vision import Vision
from choice_reader import normalize_name


FIXTURES = Path(__file__).parent / 'fixtures'


class RomanTitleContextTests(unittest.TestCase):
    def assert_reviewed_title(self, stem, identity, title):
        evidence = json.loads((FIXTURES / (stem + '.json')).read_text(encoding='utf-8'))
        embedded = json.dumps(evidence['catalog'], ensure_ascii=False, sort_keys=True,
                              separators=(',', ':')).encode('utf-8')
        self.assertEqual(hashlib.sha256(embedded).hexdigest(), evidence['embedded_catalog_sha256'])
        png = FIXTURES / (stem + '.png')
        self.assertEqual(hashlib.sha256(png.read_bytes()).hexdigest(), evidence['crop_sha256'])
        self.assertEqual(evidence['expected'], {'id': identity, 'name': title})
        with Image.open(png) as image:
            self.assertEqual(image.size, (691, 108))
            result = Vision().read_name(image, evidence['catalog'])
        # Reviewed original pixels and the frozen family catalog establish the
        # answer. All Roman variants remain competing identities in the input.
        self.assertEqual(result['status'], 'resolved', result)
        self.assertEqual(result['id'], identity, result)
        self.assertEqual(result['name'], title, result)
        # Vision records only OCR reads that passed its confidence threshold.
        # A glyph suggestion, incomplete prefix, or one trusted full title is
        # insufficient to publish this identity automatically.
        self.assertGreaterEqual(sum(normalize_name(value) == normalize_name(title)
                                    for value in result['readings']), 2, result)

    def test_real_hug_i_title_context_requires_two_trusted_complete_reads(self):
        self.assert_reviewed_title('hex-hug-i-title-context-20261020', '10615', '拥抱 I')

    def test_real_rolling_i_title_context_requires_two_trusted_complete_reads(self):
        self.assert_reviewed_title('hex-rolling-i-title-context-20261020', '1134', '嘀个痛快！ I')


if __name__ == '__main__':
    unittest.main()
