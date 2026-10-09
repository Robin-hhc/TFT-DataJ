"""Per-pin exact augment prewarming against the real DataJ HTTP contract."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import importlib
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import httpx

from dataj import DataJ, SourceError
from hex_stats import lookup_comp_hexes
from snapshot_stats import stage_stat


class HexPrewarmTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.calls = []
        self.call_lock = threading.Lock()
        self.global_rows = [self.row('20742', '四之力', ('2-1', '3-2', '4-2'))]
        self.primary_rows = [self.row('20742', '四之力', ('2-1',))]
        self.handler = self.healthy
        self.adapter = DataJ(patch='18.3', db=Path(self.temp.name)/'cache.db',
                             transport=httpx.MockTransport(self.response))
        self.prewarms = []

    def tearDown(self):
        for prewarm in self.prewarms:
            prewarm.cancel()
        for prewarm in self.prewarms:
            prewarm.wait(2)
        self.temp.cleanup()

    @staticmethod
    def row(identity, name, stages):
        return {'hexId': identity, 'name': name, 'roundStats': [
            {'round': ('2-1', '3-2', '4-2').index(stage), 'roundLabel': stage,
             'avgPlacement': 4.5, 'sampleCount': 20} for stage in stages]}

    def response(self, request):
        with self.call_lock:
            self.calls.append(request)
        return self.handler(request)

    def healthy(self, request):
        if request.url.path.endswith('/stats/hex'):
            data = self.global_rows
        elif request.url.path.endswith('/hexes'):
            data = {'compId': request.url.path.split('/')[-2], 'hexes': self.primary_rows}
        else:
            data = {'comps': [{'compId': '107', 'name': '固定测试阵容',
                               'avgPlacement': 4.23, 'sampleCount': 13,
                               'heroes': [{'heroName': '不应保留的大对象'}],
                               'traits': [{'name': '不应保留的大对象'}]}],
                    'unused': 'unrelated explorer payload'}
        return httpx.Response(200, json={'success': True, 'code': 200, 'data': data})

    def make_prewarm(self, comp='107', **kwargs):
        self.assertIsNotNone(importlib.util.find_spec('hex_prewarm'),
                             'The per-pin prewarm controller is required')
        prewarm = importlib.import_module('hex_prewarm').HexPrewarm(self.adapter, comp, **kwargs)
        self.prewarms.append(prewarm)
        return prewarm

    def exact_calls(self):
        return [json.loads(request.content)['filter']['rules'][0]
                for request in self.calls if request.method == 'POST']

    def cache_tables(self):
        self.adapter.prefetch_hexes()
        self.adapter.prefetch_hexes('107')
        self.calls.clear()

    def expire_disk(self):
        with closing(sqlite3.connect(self.adapter.db)) as connection:
            connection.execute('UPDATE cache SET fetched=0')
            connection.commit()

    def test_round_hint_skips_passed_stage_and_keeps_exact_filter_literals(self):
        prewarm = self.make_prewarm()
        prewarm.start('2-3')
        self.assertTrue(prewarm.wait(6))
        rules = self.exact_calls()
        self.assertEqual([(rule['targetId'], rule['hexRound'], rule['targetName'])
                          for rule in rules], [('20742', '1', '四之力'),
                                               ('20742', '2', '四之力')])
        self.assertTrue(all(rule['type'] == 'hex' and rule['nameMatch'] is False
                            and rule['enable'] is True for rule in rules))
        self.assertEqual(prewarm.snapshot()['completed'], 2)

    def test_warm_tables_and_compact_exact_result_survive_disk_expiry(self):
        self.global_rows = [self.row('20742', '四之力', ('3-2',))]
        self.primary_rows = []
        self.cache_tables()
        prewarm = self.make_prewarm()
        prewarm.start('3-2')
        self.assertTrue(prewarm.wait(2))
        self.assertEqual(len(self.exact_calls()), 1)
        self.expire_disk()
        self.calls.clear()
        result = lookup_comp_hexes(prewarm, '107', '3-2', [('20742', '四之力')])
        self.assertEqual(stage_stat(result['data'], '20742', '3-2')['avg_placement'], 4.23)
        self.assertEqual(stage_stat(result['data'], '20742', '3-2')['sample_count'], 13)
        exact = list(prewarm.iter_comp_hex_supplements('107', '3-2', [('20742', '四之力')]))[0][1]
        self.assertEqual(exact['data'], {'comps': [{'compId': '107', 'name': '固定测试阵容',
                                                   'avgPlacement': 4.23, 'sampleCount': 13}]})
        self.assertTrue(exact['cached'])
        self.assertEqual(prewarm.hexes()['data'], self.global_rows)
        self.assertEqual(self.calls, [])

    def test_interactive_hold_keeps_next_background_option_queued_until_released(self):
        self.global_rows = [self.row('20742', '四之力', ('3-2',)),
                            self.row('30668', '厨神阿福', ('3-2',))]
        self.primary_rows = []
        self.cache_tables()
        started, unblock, foreground_done = threading.Event(), threading.Event(), threading.Event()
        def response(request):
            rule = json.loads(request.content)['filter']['rules'][0]
            if rule['targetId'] == '20742':
                started.set()
                self.assertTrue(unblock.wait(2))
            else:
                foreground_done.set()
            return self.healthy(request)
        self.handler = response
        prewarm = self.make_prewarm()
        prewarm.start('3-2')
        try:
            self.assertTrue(started.wait(2))
            release = prewarm.begin_interactive()
            foreground = list(prewarm.iter_comp_hex_supplements(
                '107', '3-2', [('30668', '厨神阿福')]))
            self.assertTrue(foreground_done.is_set())
            self.assertEqual(len(foreground), 1)
            unblock.set()
            self.assertFalse(prewarm.wait(.1), 'The worker should stay paused during the foreground group')
            self.assertEqual([rule['targetId'] for rule in self.exact_calls()], ['20742', '30668'])
            release()
            release()
            self.assertTrue(prewarm.wait(2))
            self.assertEqual(len(self.exact_calls()), 2)
        finally:
            unblock.set()

    def test_interactive_cancellation_during_sent_request_keeps_background_spacing(self):
        self.global_rows = [self.row(identity, name, ('3-2',)) for identity, name in
                            [('20742', '四之力'), ('30668', '厨神阿福'), ('20708', '电火花 II')]]
        self.primary_rows = []
        self.cache_tables()
        started, unblock, finished = threading.Event(), threading.Event(), threading.Event()
        first_completion, third_start = [], []
        def response(request):
            rule = json.loads(request.content)['filter']['rules'][0]
            if rule['targetId'] == '20742':
                started.set()
                self.assertTrue(unblock.wait(2))
                first_completion.append(time.monotonic())
                finished.set()
            elif rule['targetId'] == '20708':
                third_start.append(time.monotonic())
            return self.healthy(request)
        self.handler = response
        prewarm = self.make_prewarm()
        returned = threading.Event()
        fetch = self.adapter.prefetch_comp_hex
        def observe_fetch(comp, stage, entity, **kwargs):
            result = fetch(comp, stage, entity, **kwargs)
            if entity[0] == '20742' and result is None:returned.set()
            return result
        with patch.object(self.adapter, 'prefetch_comp_hex', side_effect=observe_fetch):
            prewarm.start('3-2')
            try:
                self.assertTrue(started.wait(2))
                release = prewarm.begin_interactive()
                list(prewarm.iter_comp_hex_supplements('107', '3-2', [('30668', '厨神阿福')]))
                unblock.set()
                self.assertTrue(finished.wait(1))
                self.assertTrue(returned.wait(1), 'The sent background call should yield to the held foreground group')
                release()
                self.assertTrue(prewarm.wait(3))
                self.assertEqual(len(third_start), 1)
                self.assertGreaterEqual(third_start[0] - first_completion[0], .98)
            finally:
                unblock.set()

    def test_unknown_round_keeps_three_stage_order_and_future_hint_drops_queued_work(self):
        self.primary_rows = []
        self.cache_tables()
        prewarm = self.make_prewarm()
        prewarm.start()
        self.assertTrue(prewarm.wait(4))
        self.assertEqual([rule['hexRound'] for rule in self.exact_calls()], ['0', '1', '2'])
        self.expire_disk()
        self.calls.clear()
        prewarm.prioritize('4-3')
        prewarm.start('4-3')
        self.assertTrue(prewarm.wait(1))
        self.assertEqual(self.calls, [])
        self.assertEqual(prewarm.snapshot()['tables'], 2)
        self.assertEqual(prewarm.snapshot()['completed'], 3)

    def test_empty_and_zero_sample_exact_results_are_retained_without_borrowing(self):
        self.primary_rows = []
        self.cache_tables()
        def empty(request):
            rule = json.loads(request.content)['filter']['rules'][0]
            if rule['targetId'] == '20742':
                data = {'comps': [{'compId': '999', 'name': '其他阵容',
                                   'avgPlacement': 1.0, 'sampleCount': 999}]}
            else:
                data = {'comps': [{'compId': '107', 'name': '固定测试阵容',
                                   'avgPlacement': 2.0, 'sampleCount': 0}]}
            return httpx.Response(200, json={'success': True, 'code': 200, 'data': data})
        self.handler = empty
        prewarm = self.make_prewarm()
        entities = [('20742', '四之力'), ('30668', '厨神阿福')]
        first = lookup_comp_hexes(prewarm, '107', '3-2', entities)
        self.assertEqual(first['supplemented_ids'], [])
        self.assertEqual(first['supplement_errors'], {})
        self.assertEqual(len(self.exact_calls()), 2)
        self.expire_disk()
        self.calls.clear()
        repeat = lookup_comp_hexes(prewarm, '107', '3-2', entities)
        self.assertEqual(repeat['supplemented_ids'], [])
        self.assertEqual(repeat['pending_ids'], [])
        self.assertEqual(prewarm.snapshot()['completed'], 2)
        self.assertEqual(self.calls, [])

    def test_primary_zero_sample_stage_is_covered_and_other_stage_is_not_borrowed(self):
        self.global_rows = [self.row('20742', '四之力', ('3-2',))]
        self.primary_rows = [self.row('20742', '四之力', ('2-1', '3-2'))]
        self.primary_rows[0]['roundStats'][1]['sampleCount'] = 0
        self.cache_tables()
        prewarm = self.make_prewarm()
        prewarm.start('3-2')
        self.assertTrue(prewarm.wait(1))
        result = lookup_comp_hexes(prewarm, '107', '3-2', [('20742', '四之力')])
        self.assertEqual(result['supplemented_ids'], [])
        self.assertEqual(stage_stat(result['data'], '20742', '3-2')['status'], 'invalid_stat')
        self.assertEqual(self.calls, [])

    def test_failure_stops_background_and_is_never_a_negative_cache(self):
        self.global_rows = [self.row('20742', '四之力', ('3-2',)),
                            self.row('30668', '厨神阿福', ('3-2',))]
        self.primary_rows = []
        self.cache_tables()
        self.handler = lambda request: httpx.Response(503)
        prewarm = self.make_prewarm()
        prewarm.start('3-2')
        self.assertTrue(prewarm.wait(2))
        self.assertEqual(prewarm.snapshot()['status'], 'failed')
        self.assertEqual(prewarm.snapshot()['completed'], 0)
        self.assertEqual(len(self.exact_calls()), 1)
        failed = list(prewarm.iter_comp_hex_supplements('107', '3-2', [('20742', '四之力')]))
        self.assertIsInstance(failed[0][2], SourceError)
        self.assertEqual(len(self.exact_calls()), 1, 'The source cooldown should stop fresh HTTP')
        self.adapter.next_request = 0
        self.handler = self.healthy
        recovered = list(prewarm.iter_comp_hex_supplements('107', '3-2', [('20742', '四之力')]))
        self.assertIsNone(recovered[0][2])
        self.assertEqual(recovered[0][1]['data']['comps'][0]['sampleCount'], 13)
        self.assertEqual(len(self.exact_calls()), 2)

    def test_cancel_clears_memory_and_late_response_cannot_repopulate_it(self):
        self.global_rows = [self.row('20742', '四之力', ('3-2',))]
        self.primary_rows = []
        self.cache_tables()
        started, unblock = threading.Event(), threading.Event()
        def blocked(request):
            started.set()
            self.assertTrue(unblock.wait(2))
            return self.healthy(request)
        self.handler = blocked
        prewarm = self.make_prewarm()
        prewarm.start('3-2')
        try:
            self.assertTrue(started.wait(2))
            prewarm.cancel()
            self.assertEqual(prewarm.snapshot()['status'], 'cancelled')
            self.assertEqual(prewarm.snapshot()['tables'], 0)
            self.assertEqual(prewarm.snapshot()['completed'], 0)
            self.assertIsNone(prewarm.hexes('107'))
            self.assertEqual(list(prewarm.iter_comp_hex_supplements(
                '107', '3-2', [('20742', '四之力')])), [])
            self.assertFalse(prewarm.wait(.02))
        finally:
            unblock.set()
        self.assertTrue(prewarm.wait(1))
        self.assertEqual(prewarm.snapshot()['tables'], 0)
        self.assertEqual(prewarm.snapshot()['completed'], 0)
        self.handler = self.healthy
        self.expire_disk()
        fresh = self.make_prewarm()
        fresh_result = lookup_comp_hexes(fresh, '107', '3-2', [('20742', '四之力')])
        self.assertEqual(fresh_result['supplemented_ids'], ['20742'])
        self.assertEqual(len(self.exact_calls()), 2, 'A new pin must not inherit the old pin memory')

    def test_pinned_scope_rejects_other_comp_and_mutated_patch_without_http(self):
        prewarm = self.make_prewarm()
        with self.assertRaises(ValueError):prewarm.hexes('108')
        with self.assertRaises(ValueError):
            list(prewarm.iter_comp_hex_supplements('108', '3-2', [('20742', '四之力')]))
        self.adapter.patch = '18.4'
        self.assertIsNone(prewarm.hexes('107'))
        self.assertEqual(list(prewarm.iter_comp_hex_supplements(
            '107', '3-2', [('20742', '四之力')])), [])
        self.assertEqual(self.calls, [])

    def test_new_round_hint_drops_future_work_after_sent_request_completes(self):
        self.global_rows = [self.row('20742', '四之力', ('3-2', '4-2'))]
        self.primary_rows = []
        self.cache_tables()
        started, unblock = threading.Event(), threading.Event()
        def blocked(request):
            started.set()
            self.assertTrue(unblock.wait(2))
            return self.healthy(request)
        self.handler = blocked
        prewarm = self.make_prewarm()
        prewarm.start('3-2')
        try:
            self.assertTrue(started.wait(2))
            prewarm.prioritize('4-3')
            self.assertEqual(prewarm.snapshot()['pending'], 0)
        finally:
            unblock.set()
        self.assertTrue(prewarm.wait(1))
        self.assertEqual([rule['hexRound'] for rule in self.exact_calls()], ['1'])
        self.assertEqual(prewarm.snapshot()['tables'], 2)
        self.assertEqual(prewarm.snapshot()['pending'], 0)

    def test_foreground_joins_same_exact_inflight_background_request(self):
        self.global_rows = [self.row('20742', '四之力', ('3-2',))]
        self.primary_rows = []
        self.cache_tables()
        started, unblock, foreground_entered = threading.Event(), threading.Event(), threading.Event()
        def blocked(request):
            started.set()
            self.assertTrue(unblock.wait(2))
            return self.healthy(request)
        self.handler = blocked
        prewarm = self.make_prewarm()
        prewarm.start('3-2')
        def foreground_current():
            foreground_entered.set()
            return True
        with ThreadPoolExecutor(max_workers=1) as pool:
            try:
                self.assertTrue(started.wait(2))
                foreground = pool.submit(lambda: list(prewarm.iter_comp_hex_supplements(
                    '107', '3-2', [('20742', '四之力')], current=foreground_current)))
                self.assertTrue(foreground_entered.wait(1))
            finally:
                unblock.set()
            result = foreground.result(timeout=2)
        self.assertIsNone(result[0][2])
        self.assertEqual(result[0][1]['data']['comps'][0]['sampleCount'], 13)
        self.assertTrue(prewarm.wait(2))
        self.assertEqual(len(self.exact_calls()), 1)

    def test_foreground_option_runs_before_background_waiting_for_http_capacity(self):
        self.global_rows = [self.row('20742', '四之力', ('3-2',)),
                            self.row('30668', '厨神阿福', ('3-2',))]
        self.primary_rows = []
        self.cache_tables()
        entered = threading.Event()
        fetch = self.adapter.prefetch_comp_hex
        def observe_fetch(*args, **kwargs):
            entered.set()
            return fetch(*args, **kwargs)
        prewarm = self.make_prewarm()
        held = 0
        with patch.object(self.adapter, 'prefetch_comp_hex', side_effect=observe_fetch):
            try:
                for _ in range(3):
                    self.adapter.http_slots.acquire()
                    held += 1
                prewarm.start('3-2')
                self.assertTrue(entered.wait(1))
                release = prewarm.begin_interactive()
                self.adapter.http_slots.release()
                held -= 1
                result = list(prewarm.iter_comp_hex_supplements(
                    '107', '3-2', [('30668', '厨神阿福')]))
                self.assertIsNone(result[0][2])
                self.assertEqual([rule['targetId'] for rule in self.exact_calls()], ['30668'])
                release()
                self.assertTrue(prewarm.wait(3))
                self.assertEqual([rule['targetId'] for rule in self.exact_calls()], ['30668', '20742'])
            finally:
                while held:
                    self.adapter.http_slots.release()
                    held -= 1

    def test_background_uses_global_name_when_primary_name_is_not_confirmed(self):
        self.global_rows = [self.row('20742', '四之力', ('3-2',))]
        self.primary_rows = [self.row('20742', ' ', ('2-1',))]
        self.cache_tables()
        prewarm = self.make_prewarm()
        prewarm.start('3-2')
        self.assertTrue(prewarm.wait(2))
        self.assertEqual([(rule['targetId'], rule['targetName']) for rule in self.exact_calls()],
                         [('20742', '四之力')])


if __name__ == '__main__':
    unittest.main()
