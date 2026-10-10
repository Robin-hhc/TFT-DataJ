"""Frozen public source rows distinguish missing statistics from other identities.

Expected IDs and stage values were recorded from the sources before calling
production code. Qt workers are held; no OCR, game capture or HTTP is performed.
"""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from core import resolve_description, resolve_name
from hex_catalog import canonical_hex_catalog
from snapshot_stats import STAGES, stage_stat
import test_runtime_stability as runtime


FIXTURE = json.loads((Path(__file__).parent / 'fixtures/hex-data-gaps-20261010.json')
                     .read_text(encoding='utf-8'))
ORACLE = FIXTURE['oracle']


def catalog():
    return canonical_hex_catalog(FIXTURE['catalog'], FIXTURE['statistics'],
                                 set_id=FIXTURE['source_manifest']['set_id'])


def resolution(identity):
    expected = next(row for row in ORACLE['resolutions'] if row['id'] == identity)
    readings = [expected['name']] * 3
    result = {**resolve_name(readings, catalog()), 'readings': readings}
    if 'description' in expected:
        result = resolve_description(result, [expected['description']] * 2)
    return result


class HexDataGapTests(unittest.TestCase):
    def test_available_statistics_do_not_choose_between_same_name_identities(self):
        for expected in ORACLE['title_ambiguities']:
            with self.subTest(name=expected['name']):
                result = resolve_name([expected['name']] * 3, catalog())
                self.assertEqual(result['status'], 'ambiguous')
                self.assertIsNone(result.get('id'))
                self.assertEqual({str(row['id']) for row in result['candidates']},
                                 set(expected['ids']))

    def test_reviewed_descriptions_resolve_the_exact_source_identity(self):
        for expected in ORACLE['resolutions']:
            with self.subTest(identity=expected['id']):
                result = resolution(expected['id'])
                self.assertEqual(result['status'], 'resolved')
                self.assertEqual(result['id'], expected['id'])
                self.assertEqual(result['name'], expected['name'])

    def test_missing_correct_ids_never_borrow_same_name_statistics(self):
        for identity in ORACLE['missing_global_ids']:
            for stage in STAGES:
                with self.subTest(identity=identity, stage=stage):
                    self.assertEqual(stage_stat(FIXTURE['statistics'], identity, stage),
                                     {'status': 'missing_or_ambiguous_entity',
                                      'avg_placement': None})

    def test_available_ids_keep_their_own_exact_stage_values(self):
        for expected in ORACLE['available_stages']:
            with self.subTest(identity=expected['id'], stage=expected['stage']):
                self.assertEqual(stage_stat(FIXTURE['statistics'], expected['id'],
                                            expected['stage']),
                                 {'status': 'ok', 'stage': expected['stage'],
                                  'avg_placement': expected['avg_placement'],
                                  'sample_count': expected['sample_count']})
        for expected in ORACLE['missing_stages']:
            with self.subTest(identity=expected['id'], stage=expected['stage']):
                self.assertEqual(stage_stat(FIXTURE['statistics'], expected['id'],
                                            expected['stage']),
                                 {'status': 'no_stage_data', 'avg_placement': None})


class HexDataGapApplicationTests(unittest.TestCase):
    setUpClass = classmethod(runtime.RuntimeStability.setUpClass.__func__)
    tearDown = runtime.RuntimeStability.tearDown

    def setUp(self):
        runtime.RuntimeStability.setUp(self)
        self.p.catalog_loaded({'data': {'hex': catalog(), 'hero': [],
                                       'equip': [], 'trait': []}}, offline=True)
        self.p.adapter.patch = FIXTURE['source_manifest']['patch']
        self.stack.enter_context(patch.object(self.p, 'display_overlays'))
        self.hexes = self.stack.enter_context(patch.object(
            self.p.adapter, 'hexes', return_value={
                'data': deepcopy(FIXTURE['statistics']), 'fetched_at': 0}))

    def publish(self, resolutions, stage):
        self.p.invalidate()
        observation = {'scene': 'choice_candidates', 'round': stage,
                       'image_size': (1280, 720), 'elapsed_ms': 1,
                       'cards': [{'slot': index, 'raw_text': result.get('name', '未确认选项'),
                                  'box': [[100 + index * 350, 260], [300 + index * 350, 260],
                                          [300 + index * 350, 300], [100 + index * 350, 300]],
                                  'resolution': result}
                                 for index, result in enumerate(resolutions)]}
        self.p.observed(observation, True)
        self.assertIsNone(self.p.stats_payload, 'Statistics published before the worker completed')
        self.assertEqual(len(self.jobs), 1)
        work, done, _ = self.jobs.pop()
        payload = work()
        self.assertIsNone(self.p.stats_payload, 'Worker changed Qt publication state')
        done(payload)
        self.assertEqual(self.jobs, [])
        rows = self.p.stats_payload['rows']
        for index, row in enumerate(rows):
            self.assertEqual(self.p.choice_table.item(index, 1).text(), row[1])
        return rows

    def test_confirmed_missing_ids_display_no_global_statistics(self):
        identities = ORACLE['missing_global_ids']
        for stage in STAGES:
            with self.subTest(stage=stage):
                rows = self.publish([resolution(identity) for identity in identities], stage)
                self.assertEqual(self.p.session.choices, tuple(identities))
                self.assertEqual([row[1] for row in rows], ['— 暂无全局统计'] * 3)
                self.assertEqual(self.p.activity_code, 'no_stage_data')
        self.assertEqual(self.hexes.call_count, 3)

    def test_gold_statistics_remain_separate_from_missing_prismatic_statistics(self):
        for expected in ORACLE['available_stages']:
            if expected['id'] != '2705':
                continue
            with self.subTest(stage=expected['stage']):
                rows = self.publish([resolution(identity)
                                     for identity in ('2705', '3705', '20764')],
                                    expected['stage'])
                self.assertEqual(self.p.session.choices, ('2705', '3705', '20764'))
                self.assertEqual([row[1] for row in rows],
                                 [expected['global_text'], '— 暂无全局统计', '— 暂无全局统计'])

    def test_ambiguous_titles_do_not_publish_the_data_bearing_namesake(self):
        unresolved = [resolve_name([row['name']] * 3, catalog())
                      for row in ORACLE['title_ambiguities']]
        rows = self.publish(unresolved + [resolution('20763')], '3-2')
        self.assertEqual(self.p.session.choices, (None, None, '20763'))
        self.assertEqual([row[1] for row in rows],
                         ['— 未识别', '— 未识别', '— 暂无全局统计'])


if __name__ == '__main__':
    unittest.main()
