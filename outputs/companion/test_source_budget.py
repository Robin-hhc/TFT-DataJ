"""Source request limits survive replacing a statistics-version adapter."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
import time
import unittest

import httpx

from dataj import DataJ, SourceError


class SourceBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.db = Path(self.temporary.name) / 'cache.sqlite'
        self.calls = []

    def tearDown(self):
        self.temporary.cleanup()

    def replacement(self, adapter, *, patch='18.2a', transport=None):
        return DataJ(patch=patch, db=self.db, transport=transport or adapter.transport, budget=adapter.budget)

    def test_patch_replacement_respects_source_failure_cooldown(self):
        def response(request):
            self.calls.append(request)
            if len(self.calls) == 1:
                raise httpx.ConnectError('controlled source outage', request=request)
            return httpx.Response(200, json={'code': 200, 'success': True, 'data': {'hex': []}})

        adapter = DataJ(patch='18.3', db=self.db, transport=httpx.MockTransport(response))
        with self.assertRaises(SourceError):
            adapter.catalog()
        replacement = self.replacement(adapter)
        with self.assertRaises(SourceError):
            replacement.catalog()
        self.assertEqual(len(self.calls), 1, 'Changing patch must preserve the source cooldown')

    def test_patch_replacement_keeps_three_total_http_slots_for_canceled_inflight_requests(self):
        busy, release, canceled, new_started, new_entered = (threading.Event() for _ in range(5))
        arrivals = threading.Barrier(3, action=busy.set, timeout=2)
        lock = threading.Lock()
        active = maximum = 0

        def response(request):
            nonlocal active, maximum
            with lock:
                active += 1
                maximum = max(maximum, active)
            try:
                if request.method == 'POST':
                    arrivals.wait()
                    self.assertTrue(release.wait(2))
                    data = {'comps': [{'compId': '107', 'name': '测试阵容',
                                       'avgPlacement': 4.2, 'sampleCount': 100}]}
                else:
                    new_started.set()
                    data = {'hex': []}
                return httpx.Response(200, json={'code': 200, 'success': True, 'data': data})
            finally:
                with lock:
                    active -= 1

        old = DataJ(patch='18.3', db=self.db, transport=httpx.MockTransport(response))
        new = self.replacement(old)
        def fetch_new():
            new_entered.set()
            return new.catalog()
        with ThreadPoolExecutor(max_workers=2) as pool:
            previous = pool.submit(lambda: list(old.iter_comp_hex_supplements(
                '107', '3-2', [('1', 'A'), ('2', 'B'), ('3', 'C')], current=lambda: not canceled.is_set())))
            try:
                self.assertTrue(busy.wait(1))
                canceled.set()
                current = pool.submit(fetch_new)
                self.assertTrue(new_entered.wait(1))
                self.assertFalse(new_started.wait(.05), 'Canceled issued HTTP still owns source capacity')
            finally:
                release.set()
            previous.result(timeout=2)
            self.assertIsNotNone(current.result(timeout=3))
        self.assertEqual(maximum, 3, 'A replacement adapter cannot create a fourth source request')

    def test_patch_replacement_keeps_one_background_request_active(self):
        started, release, replacement_started, entered = (threading.Event() for _ in range(4))
        def response(request):
            if request.url.params['gameVersion'] == '18.3':
                started.set()
                self.assertTrue(release.wait(2))
            else:
                replacement_started.set()
            return httpx.Response(200, json={'code': 200, 'success': True, 'data': []})

        old = DataJ(patch='18.3', db=self.db, transport=httpx.MockTransport(response))
        new = self.replacement(old)
        def fetch_new():
            entered.set()
            return new.prefetch_hexes()
        with ThreadPoolExecutor(max_workers=2) as pool:
            previous = pool.submit(old.prefetch_hexes)
            try:
                self.assertTrue(started.wait(1))
                current = pool.submit(fetch_new)
                self.assertTrue(entered.wait(1))
                self.assertFalse(replacement_started.wait(.05), 'Background capacity belongs to the source lifetime')
            finally:
                release.set()
            self.assertIsNotNone(previous.result(timeout=2))
            self.assertIsNotNone(current.result(timeout=3))

    def test_patch_replacement_preserves_background_completion_spacing(self):
        trace = []
        def response(request):
            trace.append(time.monotonic())
            return httpx.Response(200, json={'code': 200, 'success': True, 'data': []})

        old = DataJ(patch='18.3', db=self.db, transport=httpx.MockTransport(response))
        old.prefetch_hexes()
        new = self.replacement(old)
        new.prefetch_hexes()
        self.assertEqual(len(trace), 2)
        self.assertGreaterEqual(trace[1] - trace[0], 1.0,
                                'A replacement inherits the last background completion interval')

    def test_ordinary_requests_remain_serialized_across_patch_replacement(self):
        started, release, replacement_started, entered = (threading.Event() for _ in range(4))
        trace = []
        def response(request):
            trace.append((request.url.params['gameVersion'], time.monotonic()))
            if request.url.params['gameVersion'] == '18.3':
                started.set()
                self.assertTrue(release.wait(2))
            else:
                replacement_started.set()
            return httpx.Response(200, json={'code': 200, 'success': True, 'data': []})

        old = DataJ(patch='18.3', db=self.db, transport=httpx.MockTransport(response))
        new = self.replacement(old)
        def fetch_new():
            entered.set()
            return new.item_stats()
        with ThreadPoolExecutor(max_workers=2) as pool:
            previous = pool.submit(old.item_stats)
            try:
                self.assertTrue(started.wait(1))
                current = pool.submit(fetch_new)
                self.assertTrue(entered.wait(1))
                self.assertFalse(replacement_started.wait(.05), 'Ordinary serialization survives replacing the adapter')
            finally:
                release.set()
            self.assertIsNotNone(previous.result(timeout=2))
            self.assertIsNotNone(current.result(timeout=3))
        self.assertEqual([patch for patch, _ in trace], ['18.3', '18.2a'])
        self.assertGreaterEqual(trace[1][1] - trace[0][1], 1.0)

    def test_identical_inflight_request_is_shared_between_adapters(self):
        started, release, duplicate, entered = (threading.Event() for _ in range(4))
        lock = threading.Lock()
        def response(request):
            with lock:
                self.calls.append(request)
                if len(self.calls) > 1:
                    duplicate.set()
            started.set()
            self.assertTrue(release.wait(2))
            return httpx.Response(200, json={'code': 200, 'success': True, 'data': []})

        old = DataJ(patch='18.3', db=self.db, transport=httpx.MockTransport(response))
        new = self.replacement(old, patch='18.3')
        def foreground():
            entered.set()
            return new.hexes()
        with ThreadPoolExecutor(max_workers=2) as pool:
            background = pool.submit(old.prefetch_hexes)
            try:
                self.assertTrue(started.wait(1))
                live = pool.submit(foreground)
                self.assertTrue(entered.wait(1))
                self.assertFalse(duplicate.wait(.05), 'Identical issued work has one source owner')
            finally:
                release.set()
            self.assertEqual(background.result(timeout=2)['data'], live.result(timeout=2)['data'])
        self.assertEqual(len(self.calls), 1)

    def test_default_adapter_keeps_independent_source_cooldown(self):
        def response(request):
            self.calls.append(request)
            if len(self.calls) == 1:
                raise httpx.ConnectError('controlled outage for a separate caller', request=request)
            return httpx.Response(200, json={'code': 200, 'success': True, 'data': {'hex': []}})

        transport = httpx.MockTransport(response)
        separate = DataJ(patch='18.3', db=self.db, transport=transport)
        with self.assertRaises(SourceError):
            separate.catalog()
        independent = DataJ(patch='18.2a', db=self.db, transport=transport)
        self.assertIsNotNone(independent.catalog())
        self.assertEqual(len(self.calls), 2, 'Default callers do not share a global singleton')

    def test_distinct_versions_do_not_share_inflight_results_or_cached_statistics(self):
        started, release, new_started = (threading.Event() for _ in range(3))
        def response(request):
            self.calls.append(request)
            patch = request.url.params['gameVersion']
            if patch == '18.3':
                started.set()
                self.assertTrue(release.wait(2))
            else:
                new_started.set()
            rows = [{'hexId': '1', 'roundStats': [{'round': 1, 'roundLabel': '3-2',
                     'avgPlacement': 4.1 if patch == '18.3' else 4.2, 'sampleCount': 100}]}]
            return httpx.Response(200, json={'code': 200, 'success': True, 'data': rows})

        old = DataJ(patch='18.3', db=self.db, transport=httpx.MockTransport(response))
        new = self.replacement(old)
        with ThreadPoolExecutor(max_workers=2) as pool:
            background = pool.submit(old.prefetch_hexes)
            try:
                self.assertTrue(started.wait(1))
                live = pool.submit(new.hexes)
                self.assertTrue(new_started.wait(1), 'A different statistics version needs its own result')
                new_result = live.result(timeout=1)
            finally:
                release.set()
            old_result = background.result(timeout=2)
        self.assertEqual(old_result['data'][0]['roundStats'][0]['avgPlacement'], 4.1)
        self.assertEqual(new_result['data'][0]['roundStats'][0]['avgPlacement'], 4.2)
        self.assertTrue(old.hexes()['cached'])
        self.assertTrue(new.hexes()['cached'])
        self.assertEqual(len(self.calls), 2)


if __name__ == '__main__':
    unittest.main()
