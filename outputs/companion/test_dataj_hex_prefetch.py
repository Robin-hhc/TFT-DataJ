"""Background hex prefetch stays bounded and shares live source evidence."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import httpx

from dataj import DataJ, SourceError


class HexPrefetchTests(unittest.TestCase):
    ENTITIES = [('20742', '四之力'), ('30668', '厨神阿福'), ('20708', '电火花 II')]

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.calls = []
        self.call_lock = threading.Lock()
        self.handler = self.healthy
        self.adapter = DataJ(patch='18.3', db=Path(self.temp.name)/'cache.db',
                             transport=httpx.MockTransport(self.response))

    def tearDown(self):
        self.temp.cleanup()

    def response(self, request):
        with self.call_lock:
            self.calls.append(request)
        return self.handler(request)

    def healthy(self, request):
        if request.method == 'POST':
            data = {'comps': [{'compId': '107', 'name': '测试阵容',
                              'avgPlacement': 4.23, 'sampleCount': 13}]}
        else:
            rows = [{'hexId': '20742', 'roundStats': [
                {'round': 1, 'roundLabel': '3-2', 'avgPlacement': 4.23,
                 'sampleCount': 13}]}]
            data = ({'compId': '107', 'hexes': rows}
                    if '/comp/' in request.url.path else rows)
        return httpx.Response(200, json={'success': True, 'code': 200, 'data': data})

    def test_background_exact_query_uses_pinned_patch_stage_and_short_timeout(self):
        self.assertTrue(callable(getattr(self.adapter, 'prefetch_comp_hex', None)),
                        'A cancellable background exact-stage query is required')
        result = self.adapter.prefetch_comp_hex('107', '3-2', self.ENTITIES[0])
        self.assertEqual(result['data']['comps'][0]['avgPlacement'], 4.23)
        self.assertFalse(result['cached'])
        self.assertEqual(len(self.calls), 1)
        request = self.calls[0]
        self.assertEqual(request.url.path, '/api/web/explorer/query')
        self.assertEqual(json.loads(request.content), {
            'version': '18.3', 'setId': 18,
            'filter': {'combinator': 'and', 'rules': [{
                'starCount': '', 'type': 'hex', 'targetId': '20742',
                'enable': True, 'targetName': '四之力', 'hexRound': '1',
                'nameMatch': False, 'equipCarry': '', 'equipCount': '',
                'exclude': False}]}})
        timeout = request.extensions['timeout']
        self.assertEqual((timeout['connect'], timeout['read']), (2, 4))

    def test_primary_prefetch_reuses_validated_global_and_pinned_cache(self):
        self.assertTrue(callable(getattr(self.adapter, 'prefetch_hexes', None)),
                        'Main tables need the same low-priority prefetch seam')
        global_result = self.adapter.prefetch_hexes()
        pinned_result = self.adapter.prefetch_hexes('107')
        self.assertEqual(global_result['data'][0]['hexId'], '20742')
        self.assertEqual(pinned_result['data'], global_result['data'])
        self.assertTrue(self.adapter.hexes()['cached'])
        self.assertTrue(self.adapter.hexes('107')['cached'])
        self.assertEqual([request.url.path for request in self.calls],
                         ['/api/web/stats/hex', '/api/web/comp/107/hexes'])
        for request in self.calls:
            self.assertEqual(dict(request.url.params), {'setId': '18', 'gameVersion': '18.3'})
            self.assertEqual((request.extensions['timeout']['connect'],
                              request.extensions['timeout']['read']), (2, 4))

    def test_new_controller_inherits_adapter_background_completion_spacing(self):
        from hex_prewarm import HexPrewarm
        trace = []
        def response(request):
            data = ([] if request.url.path.endswith('/stats/hex') else
                    {'compId': request.url.path.split('/')[-2], 'hexes': []})
            trace.append((request.url.path, time.monotonic()))
            return httpx.Response(200, json={'success': True, 'code': 200, 'data': data})
        self.handler = response
        old, new = HexPrewarm(self.adapter, '107'), HexPrewarm(self.adapter, '108')
        try:
            old.start()
            self.assertTrue(old.wait(4))
            old.cancel()
            new.start()
            self.assertTrue(new.wait(3))
            self.assertEqual([path for path, _ in trace], [
                '/api/web/stats/hex', '/api/web/comp/107/hexes', '/api/web/comp/108/hexes'])
            gaps = [trace[index][1]-trace[index-1][1] for index in (1, 2)]
            print('Cross-controller HTTP gaps: ' + ', '.join(f'{gap:.6f}s' for gap in gaps))
            self.assertGreaterEqual(gaps[1], 1.0,
                                    'A new controller must inherit its adapter\'s last background completion')
            self.assertLess(gaps[0], 1.5, 'Controller and adapter intervals must overlap')
            self.assertLess(gaps[1], 1.5, 'Switching controllers must not double the interval')
        finally:
            old.cancel()
            new.cancel()
            old.wait(2)
            new.wait(2)

    def test_issued_canceled_background_completion_delays_next_background_http(self):
        started, release, cancel = (threading.Event() for _ in range(3))
        trace = []
        def response(request):
            if request.url.path.endswith('/stats/hex'):
                started.set()
                self.assertTrue(release.wait(2))
            trace.append((request.url.path, time.monotonic()))
            return self.healthy(request)
        self.handler = response
        with ThreadPoolExecutor(max_workers=2) as pool:
            old = pool.submit(self.adapter.prefetch_hexes, current=lambda: not cancel.is_set())
            try:
                self.assertTrue(started.wait(1))
                cancel.set()
                new = pool.submit(self.adapter.prefetch_hexes, '107')
            finally:
                release.set()
            self.assertIsNone(old.result(timeout=2))
            self.assertIsNotNone(new.result(timeout=3))
        gap = trace[1][1] - trace[0][1]
        print(f'Issued-canceled background HTTP gap: {gap:.6f}s')
        self.assertGreaterEqual(gap, 1.0, 'Already-issued canceled work must retain completion spacing')
        self.assertLess(gap, 1.5, 'Completion spacing must be applied once')

    def test_background_interval_wait_reserves_no_http_capacity_and_can_cancel(self):
        self.adapter.prefetch_hexes()
        waiting, cancel = threading.Event(), threading.Event()
        live_arrivals = threading.Barrier(3, timeout=1)
        def response(request):
            if request.method == 'POST':live_arrivals.wait()
            return self.healthy(request)
        self.handler = response
        def current():
            waiting.set()
            return not cancel.is_set()
        with ThreadPoolExecutor(max_workers=2) as pool:
            background = pool.submit(self.adapter.prefetch_hexes, '107', current=current)
            try:
                self.assertTrue(waiting.wait(1))
                with self.assertRaises(FutureTimeout):background.result(timeout=.05)
                before = time.monotonic()
                self.assertTrue(self.adapter.prefetch_hexes()['cached'])
                self.assertLess(time.monotonic()-before, .1, 'Cached reads must bypass the interval')
                live = pool.submit(lambda: list(self.adapter.iter_comp_hex_supplements(
                    '107', '3-2', self.ENTITIES)))
                self.assertTrue(all(result is not None and error is None
                                    for _, result, error in live.result(timeout=.3)),
                                'A background interval wait must leave all three HTTP slots free')
                cancel.set()
                self.assertIsNone(background.result(timeout=.3))
            finally:
                cancel.set()
        self.assertEqual(len(self.calls), 4, 'Canceled pacing waits must not issue HTTP')

    def test_new_live_future_bypasses_an_already_waiting_background_interval(self):
        self.adapter.prefetch_hexes()
        waiting, live_started, release = (threading.Event() for _ in range(3))
        def response(request):
            live_started.set()
            self.assertTrue(release.wait(2))
            return self.healthy(request)
        self.handler = response
        def current():
            waiting.set()
            return True
        with ThreadPoolExecutor(max_workers=2) as pool:
            background = pool.submit(self.adapter.prefetch_comp_hex, '107', '3-2',
                                     self.ENTITIES[0], current=current)
            try:
                self.assertTrue(waiting.wait(1))
                with self.assertRaises(FutureTimeout):background.result(timeout=.05)
                live = pool.submit(lambda: list(self.adapter.iter_comp_hex_supplements(
                    '107', '3-2', [self.ENTITIES[0]])))
                self.assertTrue(live_started.wait(.3))
            finally:
                release.set()
            self.assertIsNotNone(live.result(timeout=.3)[0][1])
            self.assertIsNotNone(background.result(timeout=.3),
                                 'A newly issued live request must bypass background pacing')
        self.assertEqual(len(self.calls), 2)

    def test_issued_primary_prefetch_and_foreground_share_one_http_request(self):
        started, release, entered, duplicate = (threading.Event() for _ in range(4))
        def response(request):
            with self.call_lock:
                if len(self.calls) > 1:duplicate.set()
            started.set()
            self.assertTrue(release.wait(2))
            return self.healthy(request)
        self.handler = response
        def foreground():
            entered.set()
            return self.adapter.hexes()
        with ThreadPoolExecutor(max_workers=2) as pool:
            background = pool.submit(self.adapter.prefetch_hexes)
            try:
                self.assertTrue(started.wait(1))
                live = pool.submit(foreground)
                self.assertTrue(entered.wait(1))
                self.assertFalse(duplicate.wait(.05))
            finally:
                release.set()
            self.assertEqual(background.result(timeout=2)['data'], live.result(timeout=2)['data'])
        self.assertEqual(len(self.calls), 1, 'Issued primary prefetch must serve the identical live query')

    def test_background_uses_one_slot_while_two_live_options_and_ordinary_query_progress(self):
        blocked, release, queued, cancel = (threading.Event() for _ in range(4))
        both_live = threading.Barrier(2, timeout=1)
        def response(request):
            if request.url.path.endswith('/stats/hex'):
                blocked.set()
                self.assertTrue(release.wait(2))
            elif request.method == 'POST':
                both_live.wait()
            return self.healthy(request)
        self.handler = response
        def current():
            queued.set()
            return not cancel.is_set()
        with ThreadPoolExecutor(max_workers=4) as pool:
            background = pool.submit(self.adapter.prefetch_hexes)
            try:
                self.assertTrue(blocked.wait(1))
                pending = pool.submit(self.adapter.prefetch_hexes, '107', current=current)
                self.assertTrue(queued.wait(1))
                # Main-table background I/O must not hold request_lock.
                ordinary = pool.submit(self.adapter.request, '/stats/equip')
                self.assertIsNotNone(ordinary.result(timeout=.3))
                live = pool.submit(lambda: list(self.adapter.iter_comp_hex_supplements(
                    '107', '3-2', self.ENTITIES[:2])))
                self.assertEqual(len(live.result(timeout=.3)), 2,
                                 'One blocked prefetch must leave two HTTP slots for live choices')
                self.assertFalse(release.is_set())
                cancel.set()
                self.assertIsNone(pending.result(timeout=.3))
                self.assertFalse(any('/comp/107/hexes' in str(request.url) for request in self.calls))
            finally:
                cancel.set()
                release.set()
            self.assertIsNotNone(background.result(timeout=2))
        self.assertEqual(len(self.calls), 4)

    def test_canceled_queued_exact_prefetch_does_not_block_foreground_ownership(self):
        blocked, release, queued, cancel = (threading.Event() for _ in range(4))
        def response(request):
            if request.method == 'GET':
                blocked.set()
                self.assertTrue(release.wait(2))
            return self.healthy(request)
        self.handler = response
        def current():
            queued.set()
            return not cancel.is_set()
        with ThreadPoolExecutor(max_workers=3) as pool:
            background = pool.submit(self.adapter.prefetch_hexes)
            try:
                self.assertTrue(blocked.wait(1))
                old = pool.submit(self.adapter.prefetch_comp_hex, '107', '3-2',
                                  self.ENTITIES[0], current=current)
                self.assertTrue(queued.wait(1))
                cancel.set()
                live = pool.submit(lambda: list(self.adapter.iter_comp_hex_supplements(
                    '107', '3-2', [self.ENTITIES[0]])))
                self.assertIsNone(old.result(timeout=.3))
                self.assertIsNotNone(live.result(timeout=.3)[0][1])
                self.assertFalse(release.is_set())
            finally:
                cancel.set()
                release.set()
            self.assertIsNotNone(background.result(timeout=2))
        self.assertEqual(len(self.calls), 2)

    def test_cancel_while_waiting_for_total_http_capacity_is_interruptible(self):
        busy, release, waiting, cancel = (threading.Event() for _ in range(4))
        arrivals = threading.Barrier(3, action=busy.set, timeout=1)
        def response(request):
            arrivals.wait()
            self.assertTrue(release.wait(2))
            return self.healthy(request)
        self.handler = response
        def current():
            waiting.set()
            return not cancel.is_set()
        with ThreadPoolExecutor(max_workers=2) as pool:
            live = pool.submit(lambda: list(self.adapter.iter_comp_hex_supplements(
                '107', '3-2', self.ENTITIES)))
            try:
                self.assertTrue(busy.wait(1))
                background = pool.submit(self.adapter.prefetch_hexes, current=current)
                self.assertTrue(waiting.wait(1))
                cancel.set()
                self.assertIsNone(background.result(timeout=.3))
                self.assertEqual(len(self.calls), 3)
                self.assertFalse(release.is_set())
            finally:
                cancel.set()
                release.set()
            self.assertEqual(len(live.result(timeout=2)), 3)
        self.handler = self.healthy
        self.assertIsNotNone(self.adapter.prefetch_hexes(), 'Canceled waits must release both slots')

    def test_issued_canceled_prefetch_shares_exact_live_query_and_keeps_cache(self):
        started, release, cancel, joined = (threading.Event() for _ in range(4))
        def response(request):
            started.set()
            self.assertTrue(release.wait(2))
            return self.healthy(request)
        self.handler = response
        def live_current():
            joined.set()
            return True
        with ThreadPoolExecutor(max_workers=2) as pool:
            old = pool.submit(self.adapter.prefetch_comp_hex, '107', '3-2',
                              self.ENTITIES[0], current=lambda: not cancel.is_set())
            try:
                self.assertTrue(started.wait(1))
                cancel.set()
                live = pool.submit(lambda: list(self.adapter.iter_comp_hex_supplements(
                    '107', '3-2', [self.ENTITIES[0]], current=live_current)))
                self.assertTrue(joined.wait(1))
                with self.assertRaises(FutureTimeout):live.result(timeout=.05)
            finally:
                release.set()
            self.assertIsNone(old.result(timeout=2))
            self.assertEqual(live.result(timeout=2)[0][1]['data']['comps'][0]['sampleCount'], 13)
        self.assertTrue(self.adapter.prefetch_comp_hex('107', '3-2', self.ENTITIES[0])['cached'])
        self.assertEqual(len(self.calls), 1)

    def test_background_can_join_an_already_issued_live_exact_query(self):
        started, release, joined = (threading.Event() for _ in range(3))
        def response(request):
            started.set()
            self.assertTrue(release.wait(2))
            return self.healthy(request)
        self.handler = response
        def current():
            joined.set()
            return True
        with ThreadPoolExecutor(max_workers=2) as pool:
            live = pool.submit(lambda: list(self.adapter.iter_comp_hex_supplements(
                '107', '4-2', [self.ENTITIES[1]])))
            try:
                self.assertTrue(started.wait(1))
                background = pool.submit(self.adapter.prefetch_comp_hex, '107', '4-2',
                                         self.ENTITIES[1], current=current)
                self.assertTrue(joined.wait(1))
                with self.assertRaises(FutureTimeout):background.result(timeout=.05)
            finally:
                release.set()
            self.assertEqual(background.result(timeout=2)['data'], live.result(timeout=2)[0][1]['data'])
        self.assertEqual(len(self.calls), 1)

    def test_joining_live_future_does_not_consume_an_extra_http_slot(self):
        started, release, joined, two_live_entered = (threading.Event() for _ in range(4))
        remaining = threading.Barrier(2, action=two_live_entered.set, timeout=1)
        def response(request):
            identity = json.loads(request.content)['filter']['rules'][0]['targetId']
            if identity == self.ENTITIES[0][0]:
                started.set()
                self.assertTrue(release.wait(2))
            else:remaining.wait()
            return self.healthy(request)
        self.handler = response
        with ThreadPoolExecutor(max_workers=3) as pool:
            first = pool.submit(lambda: list(self.adapter.iter_comp_hex_supplements(
                '107', '3-2', [self.ENTITIES[0]])))
            try:
                self.assertTrue(started.wait(1))
                with self.adapter.lock:
                    self.assertEqual(len(self.adapter._hex_inflight), 1)
                    shared = next(iter(self.adapter._hex_inflight.values()))
                result = shared.result
                def observed_join(timeout=None):
                    joined.set()
                    return result(timeout=timeout)
                with patch.object(shared, 'result', side_effect=observed_join):
                    background = pool.submit(self.adapter.prefetch_comp_hex, '107', '3-2',
                                             self.ENTITIES[0])
                    self.assertTrue(joined.wait(1))
                    with self.assertRaises(FutureTimeout):background.result(timeout=.05)
                    two_live = pool.submit(lambda: list(self.adapter.iter_comp_hex_supplements(
                        '107', '3-2', self.ENTITIES[1:])))
                    self.assertTrue(two_live_entered.wait(1),
                                    'Both independent HTTP requests must arrive while the shared owner is blocked')
                    self.assertFalse(release.is_set())
                    self.assertFalse(first.done())
                    self.assertFalse(background.done())
            finally:
                release.set()
            self.assertIsNotNone(first.result(timeout=2)[0][1])
            self.assertIsNotNone(background.result(timeout=2))
            self.assertTrue(all(result is not None and error is None
                                for _, result, error in two_live.result(timeout=2)))
        self.assertEqual(len(self.calls), 3)

        self.assertEqual({json.loads(request.content)['filter']['rules'][0]['targetId']
                          for request in self.calls},
                         {identity for identity, _ in self.ENTITIES})

    def test_cooldown_is_shared_but_cached_prefetch_and_live_results_remain_available(self):
        self.adapter.prefetch_hexes()
        def failed(request):
            raise httpx.ConnectError('controlled outage', request=request)
        self.handler = failed
        with self.assertRaises(SourceError):
            self.adapter.prefetch_comp_hex('107', '3-2', self.ENTITIES[0])
        self.assertTrue(self.adapter.prefetch_hexes()['cached'])
        self.assertTrue(self.adapter.hexes()['cached'])
        with self.assertRaises(SourceError):self.adapter.prefetch_hexes('107')
        with self.assertRaises(SourceError):
            self.adapter.prefetch_comp_hex('107', '4-2', self.ENTITIES[0])
        live = list(self.adapter.iter_comp_hex_supplements('107', '3-2', [self.ENTITIES[1]]))
        self.assertIsInstance(live[0][2], SourceError)
        self.assertEqual(len(self.calls), 2, 'Cooldown must reject new HTTP across both request lanes')
        real_monotonic = time.monotonic
        self.handler = self.healthy
        with patch('dataj.time.monotonic', side_effect=lambda: real_monotonic()+61):
            self.assertIsNotNone(self.adapter.prefetch_hexes('107'))
            self.assertIsNotNone(self.adapter.prefetch_comp_hex('107', '4-2', self.ENTITIES[0]))
        self.assertEqual(len(self.calls), 4, 'Failure must release the shared future and background slot')

    def test_success_and_failure_races_preserve_cooldown_in_both_lanes(self):
        for background_fails in (False, True):
            with self.subTest(background_fails=background_fails):
                adapter = DataJ(patch='18.3', db=Path(self.temp.name)/f'race-{background_fails}.db',
                                transport=httpx.MockTransport(self.response))
                started, release = threading.Event(), threading.Event()
                def response(request):
                    if request.method == 'GET':
                        started.set()
                        self.assertTrue(release.wait(2))
                    if (request.method == 'GET') == background_fails:
                        raise httpx.ConnectError('controlled failure', request=request)
                    return self.healthy(request)
                self.handler = response
                with ThreadPoolExecutor(max_workers=1) as pool:
                    background = pool.submit(adapter.prefetch_hexes)
                    try:
                        self.assertTrue(started.wait(1))
                        live = list(adapter.iter_comp_hex_supplements('107', '3-2', [self.ENTITIES[0]]))
                        if background_fails:self.assertIsNotNone(live[0][1])
                        else:self.assertIsInstance(live[0][2], SourceError)
                    finally:
                        release.set()
                    if background_fails:
                        with self.assertRaises(SourceError):background.result(timeout=2)
                    else:self.assertIsNotNone(background.result(timeout=2))
                before = len(self.calls)
                with self.assertRaises(SourceError):adapter.prefetch_hexes('107')
                self.assertEqual(len(self.calls), before,
                                 'A success racing with failure must not shorten the 60-second cooldown')

    def test_scope_and_cancellation_reject_work_before_http(self):
        self.assertIsNone(self.adapter.prefetch_hexes(current=lambda: False))
        self.assertIsNone(self.adapter.prefetch_comp_hex(
            '107', '3-2', self.ENTITIES[0], current=lambda: False))
        for comp, stage, entity in [('0', '3-2', self.ENTITIES[0]),
                                    ('107', '5-1', self.ENTITIES[0]),
                                    ('107', '3-2', ('0', '错误身份')),
                                    ('107', '3-2', ('20742', ' '))]:
            with self.subTest(comp=comp, stage=stage, entity=entity), self.assertRaises(ValueError):
                self.adapter.prefetch_comp_hex(comp, stage, entity)
        self.assertEqual(self.calls, [])

    def test_cancellation_during_client_setup_releases_registered_future_without_http(self):
        cancel = threading.Event()
        constructor = httpx.Client
        def client(**kwargs):
            cancel.set()
            return constructor(**kwargs)
        with patch('dataj.httpx.Client', side_effect=client):
            result = self.adapter.prefetch_comp_hex(
                '107', '3-2', self.ENTITIES[0], current=lambda: not cancel.is_set())
        self.assertIsNone(result)
        self.assertEqual(self.calls, [], 'Cancellation before request I/O must not issue the registered work')
        before = time.monotonic()
        resumed = self.adapter.prefetch_comp_hex('107', '3-2', self.ENTITIES[0])
        self.assertLess(time.monotonic()-before, .2, 'Unissued cancellations must not start an interval')
        self.assertFalse(resumed['cached'])
        self.assertEqual(len(self.calls), 1)

    def test_prefetch_runs_primary_and_exact_response_validation(self):
        def malformed(request):
            data = ({'compId': '999', 'hexes': []} if request.method == 'GET' else
                    {'comps': [{'compId': '107', 'name': '测试阵容', 'sampleCount': 13}]})
            return httpx.Response(200, json={'success': True, 'code': 200, 'data': data})
        self.handler = malformed
        with self.assertRaises(SourceError):self.adapter.prefetch_hexes('107')
        with self.assertRaises(SourceError):
            self.adapter.prefetch_comp_hex('107', '3-2', self.ENTITIES[0])
        self.handler = self.healthy
        repaired = self.adapter.prefetch_comp_hex('107', '3-2', self.ENTITIES[0])
        self.assertFalse(repaired['cached'], 'Invalid exact metrics must be evicted before recovery')


if __name__ == '__main__':
    unittest.main()
