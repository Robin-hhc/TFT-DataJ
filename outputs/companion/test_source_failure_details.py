"""Failure classification preserves causes without recording private strings."""
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx

from dataj import DataJ, SourceError
from hex_prewarm import HexPrewarm
from hex_stats import lookup_comp_hexes
from source_failures import source_failure_details


SCOPE = {'set_id': 18, 'patch': '18.3', 'comp': '107', 'stage': '3-2', 'hex_id': '20708'}
REQUEST = {'method': 'POST', 'path': '/explorer/query', 'body': {
    'setId': 18, 'version': '18.3', 'filter': {'rules': [], 'combinator': 'and'}}}


class SourceFailureDetailsTests(unittest.TestCase):
    def adapter(self):
        return SimpleNamespace(lock=threading.RLock(), next_request=time.monotonic() + 60)

    def details(self, error, adapter=None):
        return source_failure_details(error, adapter or self.adapter(), scope=SCOPE, request=REQUEST)

    def test_invalid_response_during_an_unrelated_cooldown_remains_invalid_response(self):
        details = self.details(SourceError('统计字段异常 private-credential-sentinel'))
        self.assertEqual(details['reason'], 'invalid_response',
                         'The shared cooldown does not identify the failing operation')
        self.assertEqual(details['exception_types'], ['SourceError'])
        self.assertGreater(details['retry_after_seconds'], 0)
        self.assertNotIn('private-credential-sentinel', str(details))

    def test_actual_dataj_cooldown_is_distinct_and_sends_no_http(self):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            adapter = DataJ(patch='18.3', db=Path(directory) / 'cache.db',
                            transport=httpx.MockTransport(lambda request: calls.append(request)))
            adapter.next_request = time.monotonic() + 60
            with self.assertRaises(SourceError) as caught:
                adapter.request('/stats/hex')
            details = self.details(caught.exception, adapter)
        self.assertEqual(details['reason'], 'source_cooldown')
        self.assertEqual(calls, [])

    def test_wrapped_timeout_keeps_cause_types_without_request_secrets(self):
        request = httpx.Request('POST', 'https://user:private-credential-sentinel@www.dataj.cc/api/web/explorer/query',
                                headers={'Authorization': 'private-header-sentinel'})
        try:
            try:
                raise httpx.ReadTimeout('private-message-sentinel', request=request)
            except httpx.ReadTimeout as cause:
                raise SourceError('private-wrapper-sentinel') from cause
        except SourceError as error:
            details = self.details(error)
        self.assertEqual(details['reason'], 'timeout')
        self.assertEqual(details['exception_types'], ['SourceError', 'ReadTimeout'])
        self.assertEqual(details['scope'], SCOPE)
        self.assertEqual(details['request'], REQUEST)
        for secret in ('private-credential-sentinel', 'private-header-sentinel',
                       'private-message-sentinel', 'private-wrapper-sentinel'):
            self.assertNotIn(secret, str(details))

    def test_http_status_keeps_only_status_and_body_digest_without_private_body(self):
        request = httpx.Request('POST', 'https://www.dataj.cc/api/web/explorer/query',
                                headers={'Authorization': 'private-header-sentinel'})
        response = httpx.Response(503, request=request, content=b'private-response-sentinel')
        try:
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as cause:
                raise SourceError('private-wrapper-sentinel') from cause
        except SourceError as error:
            details = self.details(error)
        self.assertEqual(details['reason'], 'http_error')
        self.assertEqual(details['http_status'], 503)
        self.assertEqual(details['exception_types'], ['SourceError', 'HTTPStatusError'])
        self.assertEqual(details['response_bytes'], 25)
        self.assertEqual(details['response_sha256'],
                         'c252c1a9a36f29c93ed5b87998286e92fde4d2f6cbd8d680845d63983ca73946')
        self.assertNotIn('private-response-sentinel', str(details))
        self.assertNotIn('private-header-sentinel', str(details))
        self.assertNotIn('private-wrapper-sentinel', str(details))

    def test_prewarm_failure_records_the_canonical_body_that_actually_reached_http(self):
        import json
        calls = []

        def response(request):
            calls.append(request)
            if request.url.path.endswith('/stats/hex'):
                data = [{'hexId': '20742', 'name': '四之力', 'roundStats': [
                    {'round': 1, 'roundLabel': '3-2', 'avgPlacement': 4.91, 'sampleCount': 1852}]}]
            elif request.url.path.endswith('/comp/107/hexes'):
                data = {'compId': '107', 'hexes': []}
            else:
                raise httpx.ReadTimeout('private-message-sentinel', request=request)
            return httpx.Response(200, json={'success': True, 'code': 200, 'data': data})

        class Source(DataJ):
            def request(self, *args, **kwargs):
                if 0 < self.next_request - time.monotonic() <= 2:
                    self.next_request = 0
                return super().request(*args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            adapter = Source(patch='18.3', db=Path(directory) / 'cache.db',
                             transport=httpx.MockTransport(response))
            prewarm = HexPrewarm(adapter, '107')
            try:
                prewarm.hexes()  # validated global row supplies the canonical name
                result = lookup_comp_hexes(prewarm, '107', '3-2', [('20742', 'caller alias')])
            finally:
                prewarm.cancel()
        issued = next(request for request in calls if request.url.path.endswith('/explorer/query'))
        actual_body = json.loads(issued.content)
        self.assertEqual(actual_body['filter']['rules'][0]['targetName'], '四之力')
        detail = result['supplement_error_details']['20742']
        self.assertEqual(detail['request'], {'method': 'POST', 'path': '/explorer/query', 'body': actual_body},
                         'A diagnostic must record the request that was sent, including prewarm canonicalization')
        self.assertNotIn('private-message-sentinel', str(detail))

    def test_exact_query_cooldown_retains_the_actual_prior_http_failure_origin(self):
        calls = []

        def response(request):
            calls.append(request)
            return httpx.Response(503, content=b'private-response-sentinel')

        with tempfile.TemporaryDirectory() as directory:
            adapter = DataJ(patch='18.3', db=Path(directory) / 'cache.db',
                            transport=httpx.MockTransport(response))
            before = time.time()
            with self.assertRaises(SourceError):
                adapter.hexes()
            with self.assertRaises(SourceError) as caught:
                adapter.explore('hex', {'id': '20708', 'name': '电火花 II'},
                                hex_stage='3-2', required_comp='107')
            details = self.details(caught.exception, adapter)
            after = time.time()
        self.assertEqual(len(calls), 1, 'An exact query must respect the actual shared source cooldown')
        self.assertEqual(details['reason'], 'source_cooldown')
        self.assertIn('cooldown_origin', details,
                      'The later blocked query needs the actual earlier failure to remain diagnosable')
        origin = details['cooldown_origin']
        self.assertEqual(origin['reason'], 'http_error')
        self.assertEqual(origin['http_status'], 503)
        self.assertEqual(origin['request'], {'method': 'GET', 'path': '/stats/hex',
                                             'params': {'setId': 18, 'gameVersion': '18.3'}})
        self.assertEqual(origin['scope'], {'set_id': 18, 'patch': '18.3'})
        self.assertIsInstance(origin['occurred_at'], float)
        self.assertGreaterEqual(origin['occurred_at'], before)
        self.assertLessEqual(origin['occurred_at'], after)
        self.assertNotIn('private-response-sentinel', str(details))

    def test_failure_cooldown_and_its_origin_are_published_atomically(self):
        preparing, release = threading.Event(), threading.Event()
        captured = []
        original = source_failure_details

        def prepare(*args, **kwargs):
            preparing.set()
            if not release.wait(2):
                raise AssertionError('Test did not release the diagnostic builder')
            return original(*args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            adapter = DataJ(patch='18.3', db=Path(directory) / 'cache.db',
                transport=httpx.MockTransport(lambda request: httpx.Response(503)))

            def query():
                try:
                    adapter.hexes()
                except BaseException as error:
                    captured.append(error)

            with patch('dataj.source_failure_details', side_effect=prepare):
                worker = threading.Thread(target=query)
                worker.start()
                try:
                    self.assertTrue(preparing.wait(2), 'The real HTTP failure did not reach diagnostic preparation')
                    # A different caller can take this same budget lock now.
                    # It must see either no failure cooldown or its full cause.
                    with adapter.lock:
                        if adapter.next_request > time.monotonic() + 2:
                            self.assertIsNotNone(adapter.budget.last_failure,
                                'An active source cooldown was visible before its failure origin')
                            self.assertEqual(adapter.budget.last_failure['reason'], 'http_error')
                            self.assertEqual(adapter.budget.last_failure['http_status'], 503)
                finally:
                    release.set()
                    worker.join(2)
                self.assertFalse(worker.is_alive())
            self.assertEqual(len(captured), 1)
            self.assertIsInstance(captured[0], SourceError)
            with adapter.lock:
                self.assertGreater(adapter.next_request, time.monotonic() + 2)
                self.assertEqual(adapter.budget.last_failure['http_status'], 503)
                self.assertEqual(adapter.budget.last_failure['request'], {
                    'method': 'GET', 'path': '/stats/hex',
                    'params': {'setId': 18, 'gameVersion': '18.3'}})


if __name__ == '__main__':
    unittest.main()
