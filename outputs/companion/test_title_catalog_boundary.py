"""Freeze why a correctly read title can still have no safe data identity."""
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image

from core import resolve_name
from vision import Vision


FIXTURE = Path(__file__).parent / 'fixtures/hex-title-catalog-boundary-20261012.json'


class TitleCatalogBoundaryTests(unittest.TestCase):
    def test_repeated_missing_title_is_reported_as_catalog_lookup_failure_without_an_id(self):
        catalog = [{'id': '10579', 'name': '战时补给：巨人腰带'}]
        result = resolve_name(['战时补给:女神之泪', '战时补给：女神之泪'], catalog)
        self.assertEqual(result['status'], 'unrecognized')
        self.assertEqual(result.get('reason'), 'catalog_missing_title')
        self.assertEqual(result.get('consensus_title'), '战时补给:女神之泪')
        self.assertEqual(result.get('consensus_read_count'), 2)
        self.assertNotIn('id', result)

    def test_empty_single_and_disagreeing_unknown_reads_stay_title_unconfirmed(self):
        for readings in ([], ['', ''], ['未知名称'], ['未知名称', '另一名称'],
                         ['未知名称'] * 2 + ['另一名称'] * 2):
            with self.subTest(readings=readings):
                result = resolve_name(readings, [{'id': '1', 'name': '护甲 I'}])
                self.assertEqual(result.get('reason'), 'title_unconfirmed')
                self.assertNotIn('id', result)

    def test_partial_known_title_and_conflicting_exact_variants_remain_rejected(self):
        catalog = [{'id': '1', 'name': '护甲 I'}, {'id': '2', 'name': '护甲 II'}]
        single = resolve_name(['护甲 I', '护甲1'], catalog)
        self.assertEqual(single.get('reason'), 'title_unconfirmed')
        self.assertNotIn('id', single)
        conflict = resolve_name(['护甲 I'] * 3 + ['护甲 II'], catalog)
        self.assertEqual(conflict.get('reason'), 'title_conflict')
        self.assertEqual(conflict['status'], 'conflict')
        self.assertNotIn('id', conflict)

    def test_catalog_lookup_reason_does_not_assert_unknown_ocr_is_correct(self):
        result = resolve_name(['护甲1'] * 3, [{'id': '1', 'name': '护甲 I'}])
        self.assertEqual(result.get('reason'), 'catalog_missing_title')
        self.assertEqual(result['status'], 'unrecognized')
        self.assertNotIn('id', result)

    def test_real_anonymous_title_pixels_preserve_missing_and_ambiguous_boundaries(self):
        fixture = json.loads(FIXTURE.read_text(encoding='utf-8'))
        vision = Vision()
        for case in fixture['cases']:
            with self.subTest(title=case['independently_reviewed_title']):
                path = FIXTURE.parent / case['file']
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), case['crop_sha256'])
                with Image.open(path) as image:
                    result = vision.read_name(image, case['catalog'])
                self.assertEqual(result['status'], case['expected_status'])
                self.assertEqual(result.get('reason'), case['expected_reason'])
                self.assertIsNone(result.get('id'))
                self.assertGreaterEqual(len(result['readings']), 3)
                if case['expected_reason'] == 'catalog_ambiguous':
                    self.assertEqual({row['id'] for row in result['candidates']}, {'20760', '30760'})

    def test_missing_title_consensus_can_span_retry_views_without_claiming_an_id(self):
        from types import SimpleNamespace
        from PIL import ImageDraw
        image = Image.new('RGB', (160, 45), 'black')
        ImageDraw.Draw(image).rectangle((20, 10, 110, 32), fill='white')
        outputs = iter([('', 0)] * 4 + [('未知名称', .99)] * 2 + [('', 0)])
        vision = Vision()
        def engine(*args, **kwargs):
            text, score = next(outputs)
            return SimpleNamespace(txts=[text], scores=[score])
        vision.engine = engine
        with patch('vision.roman_evidence', return_value=None):
            result = vision.read_name(image, [{'id': '1', 'name': '护甲 I'}])
        self.assertEqual(result.get('reason'), 'catalog_missing_title')
        self.assertEqual(result.get('consensus_read_count'), 2)
        self.assertNotIn('id', result)


if __name__ == '__main__':
    unittest.main()
