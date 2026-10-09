"""Latency and safety of three independent fixed-composition augment queries."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import httpx

from dataj import DataJ, SourceError


class CompHexBatchTests(unittest.TestCase):
    ENTITIES = [('20742', '四之力'), ('30668', '厨神阿福'), ('20708', '电火花 II')]

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.calls = []
        self.call_lock = threading.Lock()
        self.adapter = DataJ(patch='18.3', db=Path(self.temp.name)/'cache.db',
                             transport=httpx.MockTransport(self.response))
        self.handler = self.healthy

    def tearDown(self):
        self.temp.cleanup()

    def response(self, request):
        with self.call_lock:
            self.calls.append(request)
        return self.handler(request)

    def healthy(self, request):
        rule = json.loads(request.content)['filter']['rules'][0]
        identity = rule['targetId']
        return httpx.Response(200, json={'success': True, 'code': 200, 'data': {
            'comps': [{'compId': '107', 'name': '测试阵容', 'avgPlacement': 4.23,
                       'sampleCount': 13, 'heroes': [], 'traits': [], 'hexId': identity}]}})

    def batch(self, entities=None, stage='3-2', comp='107', current=lambda: True, adapter=None):
        self.assertTrue(callable(getattr(adapter or self.adapter, 'iter_comp_hex_supplements', None)),
                        'A bounded exact-stage supplementation seam is required')
        return list((adapter or self.adapter).iter_comp_hex_supplements(
            comp, stage, self.ENTITIES if entities is None else entities, current=current))

    def test_three_independent_queries_overlap_and_do_not_wait_for_scalar_spacing(self):
        barrier = threading.Barrier(3, timeout=2)
        def response(request):
            barrier.wait()
            time.sleep(.1)
            return self.healthy(request)
        self.handler = response
        self.adapter.next_request = time.monotonic()+1
        started = time.monotonic()
        results = self.batch()
        self.assertLess(time.monotonic()-started, .8, 'No one-second pause per option is permitted')
        self.assertEqual({identity for identity, result, error in results}, {i for i, _ in self.ENTITIES})
        self.assertTrue(all(result and error is None for _, result, error in results))
        self.assertEqual(len(self.calls), 3)

    def test_request_scope_is_exact_and_valid_cache_is_available_during_cooldown(self):
        self.batch()
        for request in self.calls:
            body = json.loads(request.content)
            self.assertEqual(request.url.path, '/api/web/explorer/query')
            self.assertEqual((body['version'], body['setId']), ('18.3', 18))
            self.assertEqual(body['filter']['combinator'], 'and')
            self.assertEqual(len(body['filter']['rules']), 1)
            rule = body['filter']['rules'][0]
            self.assertEqual((rule['type'], rule['hexRound'], rule['enable']), ('hex', '1', True))
            self.assertIn((rule['targetId'], rule['targetName']), self.ENTITIES)
        self.adapter.next_request = time.monotonic()+60
        results = self.batch()
        self.assertTrue(all(result['cached'] and error is None for _, result, error in results))
        self.assertEqual(len(self.calls), 3)
        different_stage = self.batch([self.ENTITIES[0]], stage='4-2')
        self.assertIsNone(different_stage[0][1])
        self.assertIsInstance(different_stage[0][2], SourceError)
        self.assertEqual(len(self.calls), 3)

    def test_late_success_does_not_erase_failure_cooldown(self):
        barrier = threading.Barrier(3, timeout=2)
        failed = threading.Event()
        def response(request):
            barrier.wait()
            identity = json.loads(request.content)['filter']['rules'][0]['targetId']
            if identity == self.ENTITIES[0][0]:
                failed.set()
                raise httpx.ConnectError('source unavailable', request=request)
            self.assertTrue(failed.wait(2))
            time.sleep(.15)
            return self.healthy(request)
        self.handler = response
        results = self.batch()
        self.assertEqual(sum(error is not None for _, _, error in results), 1)
        self.assertEqual(sum(result is not None for _, result, _ in results), 2)
        self.assertGreater(self.adapter.next_request-time.monotonic(), 58)
        before = len(self.calls)
        self.handler = self.healthy
        blocked = self.batch([('10616', '拥抱 II')])
        self.assertIsInstance(blocked[0][2], SourceError)
        self.assertEqual(len(self.calls), before)
        with self.assertRaises(SourceError):
            self.adapter.request('/stats/hex')
        self.assertEqual(len(self.calls), before)

    def test_scope_validation_fails_before_any_http(self):
        for comp, stage, entities in [
                ('0', '3-2', self.ENTITIES), ('107', '5-1', self.ENTITIES),
                ('107', '3-2', [(None, '未识别')]),
                ('107', '3-2', [('20742', '')]),
                ('107', '3-2', [('20742', '四之力'), ('20742', '错误名称')]),
                ('107', '3-2', self.ENTITIES+[('10616', '拥抱 II')])]:
            with self.subTest(comp=comp, stage=stage, entities=entities), self.assertRaises(ValueError):
                self.batch(entities, stage=stage, comp=comp)
        self.assertEqual(self.calls, [])

    def test_each_finished_result_is_yielded_without_waiting_for_a_slow_option(self):
        release = threading.Event()
        slow_started = threading.Event()
        def response(request):
            identity = json.loads(request.content)['filter']['rules'][0]['targetId']
            if identity == self.ENTITIES[0][0]:
                slow_started.set()
                self.assertTrue(release.wait(2))
            return self.healthy(request)
        self.handler = response
        iterator = self.adapter.iter_comp_hex_supplements('107', '3-2', self.ENTITIES)
        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(next, iterator)
            try:
                self.assertTrue(slow_started.wait(1))
                completed = first.result(timeout=1)
                self.assertIn(completed[0], {i for i, _ in self.ENTITIES[1:]})
                self.assertIsNone(completed[2])
            finally:
                release.set()
            remaining = list(iterator)
        self.assertEqual(len(remaining), 2)

    def test_global_http_bound_includes_ordinary_requests_and_cancelled_queued_groups(self):
        first_started = threading.Event()
        release = threading.Event()
        second_entered = threading.Event()
        cancel = threading.Event()
        active, peak = [0], [0]
        def response(request):
            with self.call_lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
                if active[0] == 3:first_started.set()
            try:
                self.assertTrue(release.wait(2))
                if request.method == 'GET':
                    return httpx.Response(200, json={'success': True, 'code': 200, 'data': []})
                return self.healthy(request)
            finally:
                with self.call_lock:active[0] -= 1
        self.handler = response
        def second_current():
            second_entered.set()
            return not cancel.is_set()
        with ThreadPoolExecutor(max_workers=3) as pool:
            first = pool.submit(self.batch)
            try:
                self.assertTrue(first_started.wait(1))
                second = pool.submit(self.batch, [('4001', '甲'), ('4002', '乙'), ('4003', '丙')],
                                     current=second_current)
                self.assertTrue(second_entered.wait(1))
                ordinary = pool.submit(self.adapter.request, '/stats/hex')
                cancel.set()
            finally:
                release.set()
            self.assertEqual(len(first.result(timeout=2)), 3)
            self.assertEqual(second.result(timeout=2), [])
            self.assertEqual(ordinary.result(timeout=2)['data'], [])
        self.assertEqual(peak[0], 3)
        self.assertEqual(len(self.calls), 4, 'Cancelled queued requests cannot consume HTTP slots later')

    def test_overlapping_groups_share_identical_inflight_query(self):
        started = threading.Event()
        release = threading.Event()
        second_entered = threading.Event()
        def response(request):
            started.set()
            self.assertTrue(release.wait(2))
            return self.healthy(request)
        self.handler = response
        def current():
            second_entered.set()
            return True
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.batch, [self.ENTITIES[0]])
            try:
                self.assertTrue(started.wait(1))
                second = pool.submit(self.batch, [self.ENTITIES[0]], current=current)
                self.assertTrue(second_entered.wait(1))
                time.sleep(.1)
            finally:
                release.set()
            self.assertIsNone(first.result(timeout=2)[0][2])
            self.assertIsNone(second.result(timeout=2)[0][2])
        self.assertEqual(len(self.calls), 1, 'A refreshed group must reuse its still-running shared option')

    def test_cancelled_sent_request_still_populates_exact_cache_for_a_new_group(self):
        self.assertEqual(self.batch(current=lambda: False), [])
        self.assertEqual(self.calls, [])
        started = threading.Event()
        release = threading.Event()
        cancel = threading.Event()
        next_entered = threading.Event()
        def response(request):
            started.set()
            self.assertTrue(release.wait(2))
            return self.healthy(request)
        self.handler = response
        def new_current():
            next_entered.set()
            return True
        with ThreadPoolExecutor(max_workers=2) as pool:
            old = pool.submit(self.batch, [self.ENTITIES[0]], current=lambda: not cancel.is_set())
            try:
                self.assertTrue(started.wait(1))
                cancel.set()
                new = pool.submit(self.batch, [self.ENTITIES[0]], current=new_current)
                self.assertTrue(next_entered.wait(1))
            finally:
                release.set()
            self.assertEqual(old.result(timeout=2), [])
            self.assertIsNone(new.result(timeout=2)[0][2])
        self.assertTrue(self.batch([self.ENTITIES[0]])[0][1]['cached'])
        self.assertEqual(len(self.calls), 1)

    def test_cached_live_statistics_are_not_blocked_behind_a_slow_ordinary_request(self):
        started = threading.Event()
        release = threading.Event()
        def response(request):
            if request.url.path.endswith('/comp/rank'):
                started.set()
                self.assertTrue(release.wait(2))
            return httpx.Response(200, json={'success': True, 'code': 200, 'data': []})
        self.handler = response
        self.adapter.hexes()
        with ThreadPoolExecutor(max_workers=1) as pool:
            slow = pool.submit(self.adapter.comps)
            try:
                self.assertTrue(started.wait(2))
                before = time.monotonic()
                self.assertTrue(self.adapter.hexes()['cached'])
                self.assertLess(time.monotonic()-before, .25)
            finally:
                release.set()
            self.assertEqual(slow.result(timeout=2)['data'], [])
        self.assertEqual(len(self.calls), 2)

    def test_batch_reuses_explorer_validation_and_evicts_invalid_cached_responses(self):
        for index, corruption in enumerate(('missing', 'invalid', 'duplicate')):
            entity = [self.ENTITIES[index]]
            def response(request):
                payload = self.healthy(request).json()
                row = payload['data']['comps'][0]
                if corruption == 'missing':del row['avgPlacement']
                elif corruption == 'invalid':row['sampleCount'] = -1
                else:payload['data']['comps'].append(dict(row))
                return httpx.Response(200, json=payload)
            self.handler = response
            with self.subTest(corruption=corruption):
                broken = self.batch(entity)
                self.assertIsNone(broken[0][1])
                self.assertIsInstance(broken[0][2], SourceError)
                self.handler = self.healthy
                fixed = self.batch(entity)
                self.assertIsNone(fixed[0][2])
                self.assertFalse(fixed[0][1]['cached'], 'Rejected response must not block recovery')
                self.assertTrue(self.batch(entity)[0][1]['cached'])
        self.assertEqual(len(self.calls), 6)

    def test_one_client_is_reused_with_short_timeouts_only_in_batch(self):
        constructor = httpx.Client
        clients = []
        def client(**kwargs):
            clients.append(kwargs)
            return constructor(**kwargs)
        with patch('dataj.httpx.Client', side_effect=client):
            self.batch()
        self.assertEqual(len(clients), 1)
        for request in self.calls:
            timeout = request.extensions['timeout']
            self.assertEqual((timeout['connect'], timeout['read']), (2, 4))

    def test_ordinary_spacing_remains_and_late_ordinary_success_keeps_batch_cooldown(self):
        clock = [1000.0]
        at = []
        def healthy_scalar(request):
            at.append(clock[0])
            return httpx.Response(200, json={'success': True, 'code': 200, 'data': []})
        self.handler = healthy_scalar
        with patch('dataj.time.monotonic', side_effect=lambda: clock[0]), patch(
                'dataj.time.sleep', side_effect=lambda delay: clock.__setitem__(0, clock[0]+delay)):
            self.adapter.request('/stats/hex')
            self.adapter.request('/comp/107/hexes')
            self.adapter.request('/stats/hex')
        self.assertEqual(at, [1000.0, 1001.0], 'Default callers retain the original one-second pacing')
        self.adapter.next_request = 0
        started = threading.Event()
        release = threading.Event()
        def response(request):
            if request.method == 'GET':
                started.set()
                self.assertTrue(release.wait(2))
                return healthy_scalar(request)
            raise httpx.ConnectError('source unavailable', request=request)
        self.handler = response
        with ThreadPoolExecutor(max_workers=1) as pool:
            ordinary = pool.submit(self.adapter.request, '/stats/equip')
            try:
                self.assertTrue(started.wait(1))
                self.assertIsInstance(self.batch([self.ENTITIES[0]])[0][2], SourceError)
            finally:
                release.set()
            self.assertEqual(ordinary.result(timeout=2)['data'], [])
        self.assertGreater(self.adapter.next_request-time.monotonic(), 58)


if __name__ == '__main__':
    unittest.main()
