"""Structured result contract using the independently frozen comp-107 source."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from hex_results import ResultScope, build_hex_results


FIXTURE = json.loads((Path(__file__).parent / 'fixtures/hex-comp-107-stage-20261008.json').read_text(encoding='utf-8'))
CANDIDATES = [('20742', '四之力'), ('30668', '厨神阿福'), ('20708', '电火花 II')]
SCOPE = ResultScope(18, '18.3', '3-2', '107')


def source(data):
    return {'data': deepcopy(data), 'source': 'frozen', 'fetched_at': 123, 'cached': False}


def completed_comp():
    # Direct source's absence and three exact stage supplements are frozen
    # independently of this projection, just as in the existing UI replay.
    rows, sources = [], {}
    for item in FIXTURE['explorer']:
        rule = item['request']['filter']['rules'][0]
        if rule['hexRound'] != '1':
            continue
        identity = rule['targetId']
        selected = next(row for row in item['data']['comps'] if str(row['compId']) == '107')
        rows.append({'hexId': identity, 'roundStats': [{'round': 1, 'roundLabel': '3-2',
            'avgPlacement': selected['avgPlacement'], 'sampleCount': selected['sampleCount']}]})
        sources[identity] = {'source': 'frozen-explorer', 'fetched_at': 124, 'cached': False,
            'sample_count': selected['sampleCount'],
            'scope': {'set_id': 18, 'patch': '18.3', 'stage': '3-2', 'comp': '107', 'hex_id': identity}}
    return {**source(rows), 'supplemented_ids': list(sources), 'supplement_sources': sources}


class HexResultsTests(unittest.TestCase):
    def build(self, comp=None, *, scope=SCOPE, candidates=CANDIDATES, previous=None, finished=False):
        return build_hex_results(scope, candidates, source(FIXTURE['global']['data']), comp,
                                 previous=previous, comp_finished=finished)

    def test_frozen_statistics_keep_numeric_values_scope_and_provenance(self):
        result = self.build(completed_comp(), finished=True)
        self.assertEqual(result.rows[0][2], '4.23 · 13局 · 少')
        self.assertEqual([choice.comp_stat.average for choice in result.choices], [4.23, 4.54, 4.75])
        self.assertEqual([choice.comp_stat.samples for choice in result.choices], [13, 13, 8])
        self.assertEqual(result.comp_available, 3)
        self.assertEqual(result.supplemented_ids, ['20742', '30668', '20708'])
        self.assertEqual(result.supplement_sources['20742']['scope']['stage'], '3-2')
        self.assertEqual(result.choices[0].global_stat.source['scope']['hex_id'], '20742')

    def test_refresh_retains_confirmed_values_without_reading_display_rows(self):
        previous = self.build(completed_comp(), finished=True)
        projection = previous.rows
        projection[0][2] = '界面文案可以变化'
        result = self.build(previous=previous)
        self.assertEqual(result.choices[0].comp_stat.average, 4.23)
        self.assertEqual(result.rows[0][2], '4.23 · 13局 · 少')
        self.assertEqual(result.supplement_sources, previous.supplement_sources)

    def test_retention_cannot_cross_version_stage_target_or_candidate_identity(self):
        previous = self.build(completed_comp(), finished=True)
        for scope in [ResultScope(18, '18.2', '3-2', '107'), ResultScope(18, '18.3', '2-1', '107'),
                      ResultScope(18, '18.3', '3-2', '108'), ResultScope(17, '18.3', '3-2', '107')]:
            with self.subTest(scope=scope):
                self.assertEqual(self.build(scope=scope, previous=previous).comp_available, 0)
        changed = [('999', '另一身份')] + CANDIDATES[1:]
        self.assertEqual(self.build(candidates=changed, previous=previous).comp_available, 0)

    def test_finished_failure_drops_old_comp_values_and_remains_retryable(self):
        previous = self.build(completed_comp(), finished=True)
        result = self.build(previous=previous, finished=True)
        self.assertEqual(result.comp_available, 0)
        self.assertTrue(result.retryable)
        self.assertEqual(result.rows[0][2], '阵容数据暂不可用')
        self.assertEqual(result.supplemented_ids, [])

    def test_partial_progress_uses_new_source_for_new_value_and_retains_other_values(self):
        previous = self.build(completed_comp(), finished=True)
        fresh = completed_comp()
        fresh['data'] = fresh['data'][:1]
        fresh['data'][0]['roundStats'][0].update(avgPlacement=3.5, sampleCount=50)
        fresh['supplemented_ids'] = ['20742']
        fresh['supplement_sources'] = {'20742': {**fresh['supplement_sources']['20742'], 'fetched_at': 999}}
        result = self.build(fresh, previous=previous)
        self.assertEqual(result.rows[0][2], '3.50 · 50局')
        self.assertEqual(result.supplement_sources['20742']['fetched_at'], 999)
        self.assertEqual(result.rows[1][2], '4.54 · 13局 · 少')

    def test_unrecognized_and_unpinned_states_never_claim_numeric_statistics(self):
        result = self.build(completed_comp(), candidates=[(None, '未识别')], finished=True)
        self.assertEqual(result.rows, [['未识别', '— 未识别', '— 未识别']])
        self.assertEqual(result.available, 0)
        result = self.build(scope=ResultScope(18, '18.3', '3-2', None))
        self.assertEqual(result.rows[0][2], '未固定阵容')


if __name__ == '__main__':
    unittest.main()
