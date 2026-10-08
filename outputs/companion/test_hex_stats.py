"""Exact stage supplementation against frozen public DataJ responses."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import httpx

from dataj import DataJ, SourceError
from snapshot_stats import stage_stat


FIXTURE = json.loads((Path(__file__).parent/'fixtures/hex-comp-107-stage-20261008.json').read_text(encoding='utf-8'))


class FastDataJ(DataJ):
    """Skip normal one-second pacing while retaining the failure cooldown."""
    def request(self, *args, **kwargs):
        if self.next_request - time.monotonic() <= 2:
            self.next_request = 0
        return super().request(*args, **kwargs)


class StageExplorerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.calls = []
        self.adapter = FastDataJ(patch='18.3', db=Path(self.temp.name)/'cache.db',
                                 transport=httpx.MockTransport(self.handle))

    def tearDown(self):
        self.temp.cleanup()

    def handle(self, request):
        self.calls.append(request)
        return httpx.Response(200, json={'code':200, 'success':True, 'data':{'comps':[]}})

    def test_exact_stage_is_encoded_using_the_verified_site_contract(self):
        for stage, expected in [('2-1','0'), ('3-2','1'), ('4-2','2')]:
            self.adapter.explore('hex', {'id':'20742','name':'四之力'}, hex_stage=stage)
            body = json.loads(self.calls[-1].content)
            self.assertEqual(body['version'], '18.3')
            self.assertEqual(body['setId'], 18)
            self.assertEqual(len(body['filter']['rules']), 1)
            self.assertEqual(body['filter']['rules'][0]['targetId'], '20742')
            self.assertEqual(body['filter']['rules'][0]['hexRound'], expected)

    def test_default_explorer_behavior_remains_any_stage(self):
        for kind in ('hex','equip','hero','trait'):
            self.adapter.explore(kind, {'id':'20742','name':'测试'})
            self.assertEqual(json.loads(self.calls[-1].content)['filter']['rules'][0]['hexRound'], '')

    def test_stage_is_rejected_for_other_kinds_and_unknown_values(self):
        for kind, stage in [('equip','3-2'), ('hero','3-2'), ('trait','3-2'),
                            ('hex','5-1'), ('hex','1'), ('hex',1)]:
            with self.subTest(kind=kind, stage=stage), self.assertRaises(ValueError):
                self.adapter.explore(kind, {'id':'20742','name':'测试'}, hex_stage=stage)
        self.assertEqual(self.calls, [])


class CompHexLookupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.calls = []
        self.direct = deepcopy(FIXTURE['direct']['data'])
        self.responses = {
            (item['request']['filter']['rules'][0]['targetId'],
             item['request']['filter']['rules'][0]['hexRound']): deepcopy(item['data'])
            for item in FIXTURE['explorer']}
        self.failures = {}
        self.adapter = FastDataJ(patch='18.3', db=Path(self.temp.name)/'cache.db',
                                 transport=httpx.MockTransport(self.handle))

    def tearDown(self):
        self.temp.cleanup()

    def handle(self, request):
        self.calls.append(request)
        if request.url.path.endswith('/hexes'):
            data = self.direct
        else:
            rule = json.loads(request.content)['filter']['rules'][0]
            failure = self.failures.get((rule['targetId'], rule['hexRound']))
            if failure:
                return httpx.Response(failure)
            data = self.responses.get((rule['targetId'], rule['hexRound']), {'comps':[]})
        return httpx.Response(200, json={'code':200,'success':True,'data':data})

    def lookup(self, stage, entities, comp='107', adapter=None):
        self.assertIsNotNone(importlib.util.find_spec('hex_stats'),
                             'The fixed-composition stage lookup seam is not implemented')
        return importlib.import_module('hex_stats').lookup_comp_hexes(
            adapter or self.adapter, comp, stage, entities)

    def explorer_calls(self):
        return [r for r in self.calls if r.url.path.endswith('/explorer/query')]

    def test_real_3_2_low_sample_rows_are_recovered_by_exact_id_and_stage(self):
        original = deepcopy(self.direct)
        result = self.lookup('3-2', [('20742','四之力'), ('30668','厨神阿福'), ('20708','电火花 II')])
        for identity, average, count in [('20742',4.23,13), ('30668',4.54,13), ('20708',4.75,8)]:
            with self.subTest(identity=identity):
                stats = stage_stat(result['data'], identity, '3-2')
                self.assertEqual(stats['status'], 'ok')
                self.assertEqual(stats['avg_placement'], average)
                self.assertEqual(stats['sample_count'], count)
        self.assertEqual(result['supplemented_ids'], ['20742','30668','20708'])
        self.assertEqual(result['supplement_errors'], {})
        self.assertEqual(len(self.explorer_calls()), 3)
        self.assertEqual(self.direct, original)

    def test_real_4_2_supplement_and_existing_shield_stage_are_kept_separate(self):
        result = self.lookup('4-2', [('10616','拥抱 II'), ('20489','应急护盾')])
        self.assertEqual(stage_stat(result['data'], '10616', '4-2')['avg_placement'], 5.26)
        self.assertEqual(stage_stat(result['data'], '10616', '4-2')['sample_count'], 23)
        self.assertEqual(stage_stat(result['data'], '20489', '4-2')['avg_placement'], 4.43)
        self.assertEqual(stage_stat(result['data'], '20489', '4-2')['sample_count'], 46)
        self.assertEqual(result['supplemented_ids'], ['10616'])
        self.assertEqual(len(self.explorer_calls()), 1)

    def test_more_than_three_distinct_candidates_fail_before_network(self):
        with self.assertRaises(ValueError):
            self.lookup('3-2', [('20742','四之力'), ('30668','厨神阿福'),
                                ('20708','电火花 II'), ('10616','拥抱 II')])
        self.assertEqual(self.calls, [])

    def test_duplicate_and_unresolved_candidates_do_not_cause_extra_queries(self):
        result = self.lookup('3-2', [(None,'未确认'), ('20742','四之力'),
                                    ('20742','四之力'), (None,'未确认')])
        self.assertEqual(result['supplemented_ids'], ['20742'])
        self.assertEqual(len(self.explorer_calls()), 1)

    def test_invalid_stage_comp_identity_or_candidate_name_fails_before_network(self):
        for stage, entities, comp in [
                ('5-1',[('20742','四之力')],'107'),
                ('3-2',[('20742','四之力')],None),
                ('3-2',[('20742','四之力')],'0'),
                ('3-2',[('invalid','四之力')],'107'),
                ('3-2',[('20742','')],'107'),
                ('3-2',[('20742',None)],'107'),
                ('3-2',[('20742','四之力'),('20742','其他名字')],'107')]:
            with self.subTest(stage=stage, entities=entities, comp=comp), self.assertRaises(ValueError):
                self.lookup(stage, entities, comp=comp)
        self.assertEqual(self.calls, [])

    def test_empty_and_zero_sample_responses_are_missing_without_query_errors(self):
        zero = deepcopy(self.responses[('20742','1')]['comps'][0])
        zero['sampleCount'] = 0
        self.responses[('20742','1')] = {'comps':[zero]}
        self.responses[('30668','1')] = {'comps':[]}
        result = self.lookup('3-2', [('20742','四之力'), ('30668','厨神阿福')])
        self.assertEqual(result['supplement_errors'], {})
        self.assertEqual(result['supplemented_ids'], [])
        for identity in ('20742','30668'):
            self.assertEqual(stage_stat(result['data'], identity, '3-2')['status'],
                             'missing_or_ambiguous_entity')

    def test_different_comp_id_with_the_same_name_is_never_substituted(self):
        wrong = self.responses[('20742','1')]['comps'][0]
        wrong['compId'] = '999'
        result = self.lookup('3-2', [('20742','四之力')])
        self.assertEqual(result['supplemented_ids'], [])
        self.assertEqual(result['supplement_errors'], {})
        self.assertEqual(stage_stat(result['data'], '20742', '3-2')['status'],
                         'missing_or_ambiguous_entity')

    def test_duplicate_matching_compositions_are_rejected_for_only_that_candidate(self):
        self.responses[('20742','1')]['comps'] *= 2
        result = self.lookup('3-2', [('20742','四之力'), ('30668','厨神阿福')])
        self.assertEqual(set(result['supplement_errors']), {'20742'})
        self.assertEqual(result['supplemented_ids'], ['30668'])
        self.assertEqual(stage_stat(result['data'], '30668', '3-2')['avg_placement'], 4.54)

    def test_missing_statistics_do_not_produce_a_rank_and_other_candidates_survive(self):
        del self.responses[('20742','1')]['comps'][0]['avgPlacement']
        result = self.lookup('3-2', [('20742','四之力'), ('30668','厨神阿福')])
        self.assertEqual(set(result['supplement_errors']), {'20742'})
        self.assertEqual(result['supplement_errors']['20742'], '阵容阶段补查暂不可用')
        self.assertEqual(result['supplemented_ids'], ['30668'])

    def test_primary_scope_failure_is_raised_without_explorer_fallback(self):
        self.direct['compId'] = '999'
        with self.assertRaises(SourceError):
            self.lookup('3-2', [('20742','四之力')])
        self.assertEqual(self.explorer_calls(), [])

    def test_missing_stage_preserves_other_stages_and_does_not_use_overall(self):
        existing = {'hexId':20742, 'name':'四之力', 'avgPlacement':1.11, 'sampleCount':999,
                    'rounds':['2-1'], 'roundStats':[{'round':0, 'roundLabel':'2-1',
                    'avgPlacement':2.22, 'sampleCount':11}]}
        self.direct['hexes'].append(deepcopy(existing))
        result = self.lookup('3-2', [('20742','四之力')])
        row = next(row for row in result['data'] if str(row['hexId'])=='20742')
        self.assertEqual(stage_stat(result['data'], '20742', '3-2')['avg_placement'], 4.23)
        self.assertEqual(stage_stat(result['data'], '20742', '2-1')['avg_placement'], 2.22)
        self.assertEqual(row['avgPlacement'], 1.11)
        self.assertEqual(row['sampleCount'], 999)
        self.assertEqual(row['rounds'], ['2-1','3-2'])
        self.assertEqual(self.direct['hexes'][-1], existing)

    def test_source_metadata_is_bound_to_exact_stage_version_and_identity(self):
        result = self.lookup('3-2', [('20742','四之力')])
        audit = result['supplement_sources']['20742']
        self.assertEqual(audit['scope'], {'set_id':18, 'patch':'18.3', 'comp':'107',
                                         'stage':'3-2', 'hex_id':'20742'})
        self.assertEqual(audit['sample_count'], 13)
        self.assertEqual(audit['source'], 'https://www.dataj.cc/api/web/explorer/query')
        self.assertGreater(audit['fetched_at'], 0)
        self.assertFalse(audit['cached'])

    def test_cache_separates_acquisition_stages_and_versions(self):
        self.direct['hexes'] = []
        first = self.lookup('3-2', [('20489','应急护盾')])
        again = self.lookup('3-2', [('20489','应急护盾')])
        later = self.lookup('4-2', [('20489','应急护盾')])
        another_version = FastDataJ(patch='18.2a', db=self.adapter.db,
                                    transport=httpx.MockTransport(self.handle))
        changed = self.lookup('3-2', [('20489','应急护盾')], adapter=another_version)
        self.assertEqual(stage_stat(first['data'], '20489', '3-2')['avg_placement'], 4.05)
        self.assertEqual(stage_stat(later['data'], '20489', '4-2')['avg_placement'], 4.43)
        self.assertTrue(again['supplement_sources']['20489']['cached'])
        self.assertFalse(changed['supplement_sources']['20489']['cached'])
        self.assertEqual(changed['supplement_sources']['20489']['scope']['patch'], '18.2a')
        calls = [json.loads(request.content) for request in self.explorer_calls()]
        self.assertEqual([(body['version'],body['filter']['rules'][0]['hexRound']) for body in calls],
                         [('18.3','1'), ('18.3','2'), ('18.2a','1')])

    def test_real_adapter_first_failure_preserves_cooldown_and_reports_later_candidates(self):
        self.failures[('20742','1')] = 503
        adapter = DataJ(patch='18.3', db=Path(self.temp.name)/'real-first-failure.db',
                        transport=httpx.MockTransport(self.handle))
        with patch('dataj.time.sleep'):
            result = self.lookup('3-2', [('20742','四之力'), ('30668','厨神阿福'),
                                        ('20708','电火花 II')], adapter=adapter)
        self.assertEqual(set(result['supplement_errors']), {'20742','30668','20708'})
        self.assertEqual(result['supplemented_ids'], [])
        self.assertEqual(len(self.explorer_calls()), 1)
        self.assertEqual(stage_stat(result['data'], '20489', '4-2')['avg_placement'], 4.43)
        with self.assertRaises(SourceError):
            adapter.request('/comp/rank')
        self.assertEqual(len(self.calls), 2)

    def test_real_adapter_last_failure_retains_the_first_two_successful_supplements(self):
        self.failures[('20708','1')] = 503
        adapter = DataJ(patch='18.3', db=Path(self.temp.name)/'real-last-failure.db',
                        transport=httpx.MockTransport(self.handle))
        with patch('dataj.time.sleep'):
            result = self.lookup('3-2', [('20742','四之力'), ('30668','厨神阿福'),
                                        ('20708','电火花 II')], adapter=adapter)
        self.assertEqual(result['supplemented_ids'], ['20742','30668'])
        self.assertEqual(set(result['supplement_errors']), {'20708'})
        self.assertEqual(stage_stat(result['data'], '20742', '3-2')['avg_placement'], 4.23)
        self.assertEqual(stage_stat(result['data'], '30668', '3-2')['avg_placement'], 4.54)
        self.assertEqual(stage_stat(result['data'], '20489', '4-2')['avg_placement'], 4.43)
        self.assertEqual(len(self.explorer_calls()), 3)

    def test_no_confirmed_candidates_does_not_query_the_explorer(self):
        result = self.lookup('3-2', [(None,'未确认')])
        self.assertEqual(result['data'], self.direct['hexes'])
        self.assertEqual(result['supplemented_ids'], [])
        self.assertEqual(result['supplement_errors'], {})
        self.assertEqual(self.explorer_calls(), [])

    def test_existing_invalid_zero_sample_stage_is_not_replaced_by_another_query(self):
        row = next(row for row in self.direct['hexes'] if str(row['hexId'])=='20489')
        part = next(part for part in row['roundStats'] if part['roundLabel']=='4-2')
        part['sampleCount'] = 0
        result = self.lookup('4-2', [('20489','应急护盾')])
        self.assertEqual(stage_stat(result['data'], '20489', '4-2')['status'], 'invalid_stat')
        self.assertEqual(self.explorer_calls(), [])
        self.assertEqual(result['supplemented_ids'], [])

    def test_new_stage_rows_do_not_invent_overall_statistics(self):
        result = self.lookup('3-2', [('20742','四之力')])
        row = next(row for row in result['data'] if str(row['hexId'])=='20742')
        self.assertNotIn('avgPlacement', row)
        self.assertNotIn('sampleCount', row)
        self.assertEqual(row['rounds'], ['3-2'])
        self.assertEqual(stage_stat(result['data'], '20742', '2-1')['status'], 'no_stage_data')
        self.assertEqual(stage_stat(result['data'], '20742', '4-2')['status'], 'no_stage_data')

    def test_cached_explorer_result_selects_each_composition_by_its_exact_id(self):
        other = deepcopy(self.responses[('20742','1')]['comps'][0])
        other.update(compId='108', name='另一阵容', avgPlacement=2.12, sampleCount=17)
        self.responses[('20742','1')]['comps'].append(other)

        def scoped_response(request):
            if not request.url.path.endswith('/hexes'):
                return self.handle(request)
            self.calls.append(request)
            comp_id = request.url.path.split('/')[-2]
            return httpx.Response(200,json={'code':200,'success':True,
                                           'data':{'compId':comp_id,'hexes':[]}})

        adapter = FastDataJ(patch='18.3', db=Path(self.temp.name)/'comp-isolation.db',
                            transport=httpx.MockTransport(scoped_response))
        first = self.lookup('3-2', [('20742','四之力')], comp='107', adapter=adapter)
        other_result = self.lookup('3-2', [('20742','四之力')], comp='108', adapter=adapter)
        self.assertEqual(stage_stat(first['data'], '20742', '3-2')['avg_placement'], 4.23)
        self.assertEqual(stage_stat(other_result['data'], '20742', '3-2')['avg_placement'], 2.12)
        self.assertTrue(other_result['supplement_sources']['20742']['cached'])
        self.assertEqual(other_result['supplement_sources']['20742']['scope']['comp'], '108')
        self.assertEqual(len(self.explorer_calls()), 1)

    def test_invalid_supplement_statistics_fail_closed(self):
        original = deepcopy(self.responses[('20742','1')]['comps'][0])
        for index, fields in enumerate([{'avgPlacement':None}, {'avgPlacement':True},
                {'avgPlacement':0}, {'avgPlacement':8.01}, {'sampleCount':-1},
                {'sampleCount':True}, {'sampleCount':1.5}]):
            with self.subTest(fields=fields):
                self.responses[('20742','1')] = {'comps':[{**original, **fields}]}
                adapter = FastDataJ(patch='18.3', db=Path(self.temp.name)/f'invalid-{index}.db',
                                    transport=httpx.MockTransport(self.handle))
                result = self.lookup('3-2', [('20742','四之力')], adapter=adapter)
                self.assertEqual(result['supplemented_ids'], [])
                self.assertEqual(set(result['supplement_errors']), {'20742'})
                self.assertEqual(stage_stat(result['data'], '20742', '3-2')['status'],
                                 'missing_or_ambiguous_entity')


if __name__ == '__main__':
    unittest.main()
