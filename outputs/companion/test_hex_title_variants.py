"""Reviewed full-title variants must preserve conservative OCR identity gates."""
import hashlib
import json
from copy import deepcopy
from pathlib import Path
import unittest

from PIL import Image

from choice_reader import normalize_name
from core import resolve_name
from vision import Vision


FIXTURE = Path(__file__).parent / 'fixtures/hex-kingslayer-title-20261018'
EVIDENCE = json.loads(FIXTURE.with_suffix('.json').read_text(encoding='utf-8'))


class HexTitleVariantTests(unittest.TestCase):
    def test_real_kingslayer_title_resolves_frozen_identity(self):
        png = FIXTURE.with_suffix('.png')
        self.assertEqual(hashlib.sha256(png.read_bytes()).hexdigest(), EVIDENCE['crop_sha256'])
        with Image.open(png) as crop:
            result = Vision().read_name(crop, EVIDENCE['catalog'])
        # Original pixels, quality and description were independently reviewed;
        # neither OCR output nor statistics produced the accepted ID.
        self.assertEqual(result['status'], 'resolved', result)
        self.assertEqual(result['id'], '10196')
        self.assertEqual(result['name'], '弑君突刺')
        self.assertGreaterEqual(sum(normalize_name(value) in ('弑君突刺', '弒君突刺')
                                    for value in result['readings']), 2)

    def test_reviewed_variant_still_requires_two_trusted_complete_readings(self):
        catalog = EVIDENCE['catalog']
        self.assertEqual(resolve_name(['弒君突刺'], catalog)['status'], 'unrecognized')
        self.assertEqual(resolve_name(['弒君突刺', ''], catalog)['status'], 'unrecognized')
        for readings in (['弒君突刺'] * 2, ['弑君突刺', '弒君突刺']):
            with self.subTest(readings=readings):
                result = resolve_name(readings, catalog)
                self.assertEqual((result['status'], result['id']), ('resolved', '10196'))

    def test_any_conflicting_exact_title_vetoes_variant_consensus(self):
        catalog = EVIDENCE['catalog'] + [{'id': '10632', 'name': '双子守护神'}]
        result = resolve_name(['弒君突刺', '弒君突刺', '双子守护神'], catalog)
        self.assertEqual(result['status'], 'conflict')
        self.assertEqual({row['id'] for row in result['candidates']}, {'10196', '10632'})

    def test_literal_variant_catalog_identity_is_never_rewritten_to_canonical(self):
        catalog = EVIDENCE['catalog'] + [{'id': 'other-exact-id', 'name': '弒君突刺'}]
        literal = resolve_name(['弒君突刺'] * 2, catalog)
        self.assertEqual((literal['status'], literal['id']), ('resolved', 'other-exact-id'))
        # Once both literal catalog titles are observed, neither consensus nor
        # the reviewed character relationship may erase their disagreement.
        mixed = resolve_name(['弑君突刺', '弒君突刺', '弒君突刺'], catalog)
        self.assertEqual(mixed['status'], 'conflict')

    def test_duplicate_canonical_identities_remain_ambiguous(self):
        other = {**EVIDENCE['catalog'][0], 'id': 'another-canonical-id'}
        result = resolve_name(['弒君突刺'] * 2, EVIDENCE['catalog'] + [other])
        self.assertEqual(result['status'], 'ambiguous')
        self.assertEqual({row['id'] for row in result['candidates']},
                         {'10196', 'another-canonical-id'})

    def test_variant_never_crosses_frozen_season_domain_or_identity(self):
        mutations = [
            {'setId': '17'},
            {'setId': None},
            {'id': 'unknown-identity'},
            {'level': 2},
            {'icon': 'https://img.dataj.cc/images/equip/kingslayer1.png'},
            {'icon': 'https://untrusted.example/images/hex/kingslayer1.png'},
            {'icon': None},
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                row = {**EVIDENCE['catalog'][0], **mutation}
                self.assertEqual(resolve_name(['弒君突刺'] * 2, [row])['status'], 'unrecognized')

    def test_other_titles_and_numeric_roman_plus_suffixes_are_not_rewritten(self):
        catalog = deepcopy(EVIDENCE['catalog'])
        catalog.extend([
            {**EVIDENCE['catalog'][0], 'name': '弑君突刺 II'},
            {**EVIDENCE['catalog'][0], 'name': '弑君突刺+'},
            {'id': 'war', 'name': '战争财宝'},
            {'id': 'roman', 'name': '护甲 II++'},
        ])
        for reading in ('弒君突刺 II', '弒君突刺+', '弒君突刺2', '戰爭財寶',
                        '护甲 11++', '护甲 II+', '护甲 III++'):
            with self.subTest(reading=reading):
                self.assertEqual(resolve_name([reading] * 2, catalog)['status'], 'unrecognized')
        # Shared normalization remains a literal text/spacing operation; the
        # reviewed full-title rule belongs only to candidate resolution.
        self.assertNotEqual(normalize_name('弒君突刺'), normalize_name('弑君突刺'))
        self.assertEqual(resolve_name(['护甲 II++'] * 2, catalog)['id'], 'roman')


if __name__ == '__main__':
    unittest.main()
