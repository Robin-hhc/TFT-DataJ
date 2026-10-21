"""A transient source outage must not disable this game's remaining prewarm.

The HTTP contract and shared cooldown are production DataJ. Only the delayed
wakeup and monotonic clock are controlled, so a minute-long recovery is fast.
"""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import httpx

from dataj import DataJ
from hex_prewarm import HexPrewarm
from hex_stats import lookup_comp_hexes
from snapshot_stats import stage_stat


class ControlledTimer:
    def __init__(self, interval, function, args=None, kwargs=None):
        self.interval, self.function = interval, function
        self.args, self.kwargs = args or (), kwargs or {}
        self.cancelled = False
        self.daemon = False

    def start(self):
        pass

    def cancel(self):
        self.cancelled = True

    def fire(self):
        # Deliberately deliver even a cancelled callback: cancellation and
        # session checks in the controller must reject an already queued wake.
        self.function(*self.args, **self.kwargs)


class HexPrewarmRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.now = 1000.0
        actual_monotonic = time.monotonic
        started = actual_monotonic()
        self.timers, self.calls = [], []
        self.fail = True
        self.fail_table = self.corrupt_table = False
        self.active = True
        self.global_rows = [
            {'hexId': identity, 'name': name, 'roundStats': [
                {'round': 1, 'roundLabel': '3-2', 'avgPlacement': 4.5, 'sampleCount': 20}]}
            for identity, name in [('20742', '四之力'), ('30668', '厨神阿福')]]
        self.adapter = DataJ(patch='18.3', db=Path(self.temp.name)/'cache.db',
                             transport=httpx.MockTransport(self.response))
        self.clock_patch = patch('hex_prewarm.time.monotonic',
                                 side_effect=lambda: self.now + actual_monotonic()-started)
        self.timer_patch = patch('hex_prewarm.threading.Timer', side_effect=self.timer)
        self.clock_patch.start()
        self.timer_patch.start()
        # Warm the two real primary tables before the exact-stage outage.
        self.adapter.prefetch_hexes()
        self.now += 2
        self.adapter.prefetch_hexes('107')
        self.now += 2
        self.calls.clear()
        self.prewarm = HexPrewarm(self.adapter, '107', current=lambda: self.active)

    def tearDown(self):
        self.prewarm.cancel()
        self.prewarm.wait(2)
        self.timer_patch.stop()
        self.clock_patch.stop()
        self.temp.cleanup()

    def timer(self, *args, **kwargs):
        timer = ControlledTimer(*args, **kwargs)
        self.timers.append(timer)
        return timer

    def response(self, request):
        self.calls.append(request)
        if request.url.path.endswith('/stats/hex'):
            if self.fail_table:return httpx.Response(503)
            data = deepcopy(self.global_rows)
            if self.corrupt_table:data[0]['roundStats'][0]['avgPlacement'] = None
        elif request.url.path.endswith('/hexes'):
            data = {'compId': '107', 'hexes': []}
        else:
            if self.fail:
                return httpx.Response(503)
            identity = json.loads(request.content)['filter']['rules'][0]['targetId']
            data = {'comps': [{'compId': '107', 'name': '固定测试阵容',
                               'avgPlacement': 4.23 if identity == '20742' else 4.54,
                               'sampleCount': 13}]}
            # Move only the controlled clock across normal completion pacing.
            self.now += 2
        return httpx.Response(200, json={'success': True, 'code': 200, 'data': data})

    def fresh_table_source(self):
        self.adapter = DataJ(patch='18.3', db=Path(self.temp.name)/'fresh.db',
                             transport=httpx.MockTransport(self.response))
        self.prewarm = HexPrewarm(self.adapter, '107', current=lambda: self.active)

    def advance_background_wait(self, timeout):
        self.now += timeout
        return False

    def start_failed(self):
        self.prewarm.start('3-2')
        self.assertTrue(self.prewarm.wait(2))
        self.assertEqual(self.prewarm.snapshot()['status'], 'failed')
        self.assertEqual(self.prewarm.snapshot()['completed'], 0)
        self.assertEqual(len(self.calls), 1)
        self.assertGreaterEqual(self.adapter.next_request - self.now, 59)

    def test_transient_http_failure_automatically_resumes_pending_exact_stages_after_cooldown(self):
        self.start_failed()
        self.fail = False
        self.now = self.adapter.next_request + 1
        for timer in list(self.timers):
            timer.fire()
        self.assertTrue(self.prewarm.wait(2))
        self.assertEqual(self.prewarm.snapshot()['completed'], 2,
                         'Source recovery must resume the retained queue without a new pin or manual lookup')
        self.assertEqual(self.prewarm.snapshot()['status'], 'complete')
        self.assertEqual(len(self.calls), 3)
        before = len(self.calls)
        result = lookup_comp_hexes(self.prewarm, '107', '3-2',
                                   [('20742', '四之力'), ('30668', '厨神阿福')])
        self.assertEqual(stage_stat(result['data'], '20742', '3-2')['avg_placement'], 4.23)
        self.assertEqual(stage_stat(result['data'], '30668', '3-2')['avg_placement'], 4.54)
        self.assertEqual(len(self.calls), before, 'Recovered prewarm must supply the actual selection seam')

    def test_early_wake_obeys_extended_shared_source_cooldown_without_http_or_retry_storm(self):
        self.start_failed()
        self.assertEqual(len(self.timers), 1)
        first = self.timers[0]
        self.assertGreaterEqual(first.interval, 59)
        self.now += 61
        self.adapter.next_request = self.now + 60  # Another source request failed later.
        first.fire()
        self.assertTrue(self.prewarm.wait(2))
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(self.timers), 2)
        self.assertGreaterEqual(self.timers[-1].interval, 59)
        self.assertEqual(self.prewarm.snapshot()['completed'], 0)

    def test_cancelled_or_obsolete_context_rejects_a_late_retry_callback(self):
        self.start_failed()
        self.assertEqual(len(self.timers), 1)
        first = self.timers[0]
        self.prewarm.cancel()
        self.assertTrue(first.cancelled)
        self.now += 61
        self.fail = False
        first.fire()
        self.assertTrue(self.prewarm.wait(2))
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.prewarm.snapshot()['status'], 'cancelled')
        self.assertEqual(self.prewarm.snapshot()['tables'], 0)
        self.assertEqual(self.prewarm.snapshot()['completed'], 0)

    def test_patch_change_rejects_retry_without_using_old_tables_or_issuing_http(self):
        self.start_failed()
        self.assertEqual(len(self.timers), 1)
        self.adapter.patch = '18.4'
        self.now += 61
        self.fail = False
        self.timers[0].fire()
        self.assertTrue(self.prewarm.wait(2))
        self.assertEqual(len(self.calls), 1)
        self.assertIsNone(self.prewarm.hexes())
        self.assertEqual(list(self.prewarm.iter_comp_hex_supplements(
            '107', '3-2', [('20742', '四之力')])), [])

    def test_new_session_rejects_retry_and_old_cached_tables_without_http(self):
        self.start_failed()
        self.assertEqual(len(self.timers), 1)
        self.active = False
        self.now += 61
        self.fail = False
        self.timers[0].fire()
        self.assertTrue(self.prewarm.wait(2))
        self.assertEqual(len(self.calls), 1)
        self.assertIsNone(self.prewarm.hexes('107'))
        self.assertFalse(self.prewarm.snapshot()['retry_pending'])

    def test_round_advance_drops_passed_stage_while_recovery_is_delayed(self):
        self.start_failed()
        self.prewarm.prioritize('4-3')
        self.assertEqual(self.prewarm.snapshot()['pending'], 0)
        self.now += 61
        self.fail = False
        self.timers[0].fire()
        self.assertTrue(self.prewarm.wait(2))
        self.assertEqual(self.prewarm.snapshot()['status'], 'complete')
        self.assertEqual(self.prewarm.snapshot()['completed'], 0)
        self.assertEqual(len(self.calls), 1)

    def test_transient_main_table_http_failure_resumes_without_discarding_future_exact_jobs(self):
        self.fresh_table_source()
        self.fail_table = True
        self.start_failed()
        self.fail_table = self.fail = False
        self.now = self.adapter.next_request + 1
        with patch.object(self.prewarm._wake, 'wait', side_effect=self.advance_background_wait):
            self.timers[0].fire()
            self.assertTrue(self.prewarm.wait(2))
        self.assertEqual(self.prewarm.snapshot()['status'], 'complete')
        self.assertEqual(self.prewarm.snapshot()['tables'], 2)
        self.assertEqual(self.prewarm.snapshot()['completed'], 2)
        self.assertEqual(len(self.calls), 5)

    def test_invalid_successful_main_table_is_evicted_before_recovery_refetches_same_scope(self):
        self.fresh_table_source()
        self.corrupt_table = True
        self.prewarm.start('3-2')
        self.assertTrue(self.prewarm.wait(2))
        self.assertEqual(self.prewarm.snapshot()['status'], 'failed')
        self.assertEqual(self.prewarm.snapshot()['tables'], 0)
        self.assertEqual(len(self.calls), 1)
        self.corrupt_table = self.fail = False
        self.now += 61
        with patch.object(self.prewarm._wake, 'wait', side_effect=self.advance_background_wait):
            self.timers[0].fire()
            self.assertTrue(self.prewarm.wait(2))
        self.assertEqual(self.prewarm.snapshot()['completed'], 2,
                         'A corrected source must be fetched rather than replaying the invalid cached 200 table')
        self.assertEqual(self.prewarm.snapshot()['status'], 'complete')
        self.assertEqual(len(self.calls), 5)


if __name__ == '__main__':
    unittest.main()
