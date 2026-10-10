"""Real DataJ duplicate titles must resolve to the current data identity safely."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from core import resolve_name
from entity_identity import EntityResolver
from snapshot_stats import stage_stat


FIXTURE = json.loads((Path(__file__).parent / 'fixtures/hex-identity-20261007.json').read_text(encoding='utf-8'))
GAP_FIXTURE = json.loads((Path(__file__).parent / 'fixtures/hex-catalog-gap-20261010.json').read_text(encoding='utf-8'))


class HexCatalogTests(unittest.TestCase):
    def project(self, rows=None, stats=None):
        from hex_catalog import canonical_hex_catalog
        return canonical_hex_catalog(rows if rows is not None else FIXTURE['catalog'],
                                     stats if stats is not None else FIXTURE['statistics'], set_id=18)

    def test_real_titles_resolve_to_the_same_id_as_display_and_selected_resource(self):
        catalog = self.project()
        resolver = EntityResolver({'hex': catalog})
        for name, identity, stage, avg in [('别再错过', '1625', '3-2', 4.27),
                                           ('自然庇护所', '20768', '2-1', 4.29)]:
            result = resolve_name([name] * 3, catalog)
            self.assertEqual(result['status'], 'resolved')
            self.assertEqual(result['id'], identity)
            self.assertEqual(stage_stat(FIXTURE['statistics'], result['id'], stage)['avg_placement'], avg)
            self.assertEqual(resolver.resolve_selection('hex', result['candidates'][0]).entity['id'], identity)
            self.assertFalse(resolver.resolve_selection('hex', {'id': '10784' if identity == '1625' else '30768',
                                                               'name': name}).confirmed)

    def test_real_different_qualities_are_not_filtered_by_stats_availability(self):
        result = resolve_name(['成吨的属性！'] * 3, self.project())
        self.assertEqual(result['status'], 'ambiguous')
        self.assertEqual({str(row['id']) for row in result['candidates']}, {'2705', '3705'})

    def test_projection_does_not_mutate_raw_catalog_or_weaken_title_consensus(self):
        original = deepcopy(FIXTURE['catalog'])
        catalog = self.project()
        self.assertEqual(FIXTURE['catalog'], original)
        self.assertNotEqual(resolve_name(['别再错过'], catalog)['status'], 'resolved')
        self.assertEqual(resolve_name(['别再错过', '自然庇护所'], catalog)['status'], 'conflict')
        self.assertNotEqual(resolve_name(['并肩作战1'] * 3, catalog)['status'], 'resolved')

    def test_missing_or_different_metadata_and_wrong_season_never_merge(self):
        pair = [deepcopy(row) for row in FIXTURE['catalog'] if row['name'] == '别再错过']
        for field in ('icon', 'descText', 'level', 'setId'):
            for value in (None, '', 'different'):
                with self.subTest(field=field, value=value):
                    rows = deepcopy(pair)
                    rows[1][field] = value
                    self.assertEqual(len(self.project(rows)), 2)
        pair[0]['setId'] = pair[1]['setId'] = 19
        self.assertEqual(len(self.project(pair)), 2)

    def test_no_active_id_multiple_ids_empty_or_invalid_statistics_never_merge(self):
        pair = [deepcopy(row) for row in FIXTURE['catalog'] if row['name'] == '别再错过']
        stat = next(deepcopy(row) for row in FIXTURE['statistics'] if row['hexId'] == 1625)
        other = {**deepcopy(stat), 'hexId': 10784, 'roundStats': [
            {'round': 0, 'roundLabel': '2-1', 'sampleCount': 1, 'avgPlacement': 1.0}]}
        for stats in ([], [stat, other], [stat, stat], [{**stat, 'roundStats': []}],
                      [{**stat, 'name': 'wrong title'}], [{**stat, 'icon': 'wrong icon'}],
                      [{**stat, 'roundStats': [{**part, 'sampleCount': 0} for part in stat['roundStats']]}]):
            with self.subTest(stats=stats):
                self.assertEqual(len(self.project(pair, stats)), 2)

    def test_real_missing_unsuffixed_title_never_resolves_to_a_plus_variant(self):
        catalog = self.project(GAP_FIXTURE['catalog'], GAP_FIXTURE['statistics'])
        result = resolve_name(['白银命运'] * 7, catalog)
        self.assertEqual(result['status'], 'unrecognized')
        self.assertIsNone(result.get('id'))
        self.assertEqual(result['candidates'], [])
        self.assertEqual({row['name'] for row in catalog}, {'白银命运+', '白银命运++'})
        self.assertEqual(stage_stat(GAP_FIXTURE['statistics'], result.get('id'), '2-1'),
                         {'status': 'missing_or_ambiguous_entity', 'avg_placement': None})

    def test_real_plus_variants_keep_their_own_ids_and_stage_statistics(self):
        catalog = self.project(GAP_FIXTURE['catalog'], GAP_FIXTURE['statistics'])
        for name, identity, stage, average, count in [
                ('白银命运+', '20494', '3-2', 4.45, 4927),
                ('白银命运++', '30494', '4-2', 4.35, 1839)]:
            with self.subTest(name=name):
                result = resolve_name([name] * 7, catalog)
                self.assertEqual(result['status'], 'resolved')
                self.assertEqual(result['id'], identity)
                self.assertEqual(result['name'], name)
                self.assertEqual(stage_stat(GAP_FIXTURE['statistics'], result['id'], stage),
                                 {'status': 'ok', 'avg_placement': average,
                                  'sample_count': count, 'stage': stage})

    def test_real_missing_stage_never_uses_overall_or_other_stage_statistics(self):
        for identity, missing_stages in [('20494', ('2-1', '4-2')),
                                         ('30494', ('2-1', '3-2'))]:
            for stage in missing_stages:
                with self.subTest(identity=identity, stage=stage):
                    self.assertEqual(stage_stat(GAP_FIXTURE['statistics'], identity, stage),
                                     {'status': 'no_stage_data', 'avg_placement': None})


if __name__ == '__main__':
    unittest.main()
