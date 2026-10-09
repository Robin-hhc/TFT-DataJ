"""A slow exact supplement must not hold back already-known composition ranks.

Real Qt workers, query_stats, DataJ validation and rendering are exercised.
Only HTTP responses, native placement and screen/window boundaries are faked;
events hold one response until the assertion has inspected the visible ranks.
"""
from contextlib import ExitStack, closing
import json
import sqlite3
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx
from app import QApplication, CardOverlay, Companion
from dataj import DataJ


class HexCompLatency(unittest.TestCase):
    IDS = ['1023', '1479', '1006']
    NAMES = ['应急护甲 I', '黑铁资产', '进攻宣告']
    EXPECTED = ['2.75 · 51局', '2.85 · 52局', '2.95 · 53局']

    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.stack = ExitStack()
        self.blocked = threading.Event()
        self.release = threading.Event()
        self.calls = []
        self.block_id = self.IDS[0]
        self.direct_ids = set(self.IDS[1:])
        for module in ['app', 'dataj', 'comp_browser']:
            self.stack.enter_context(patch(module + '.STATE_DIR', Path(self.tmp.name)))
        self.stack.enter_context(patch('app.win.enumerate_mumu', return_value=[]))
        self.stack.enter_context(patch('app.record'))
        self.p = Companion(offline=True, offline_catalog={
            'hex': [], 'hero': [], 'trait': [], 'equip': []})
        self.p.timer.stop()
        self.p.offline = False
        self.stack.enter_context(patch.object(self.p.bugs, 'hex_statistics'))
        self.p.binding = SimpleNamespace(hwnd=7)
        self.p.last_capture = time.monotonic()
        self.p.last_observation = {'cards': [
            {'resolution': {'id': identity},
             'box': [[0, 0], [100, 0], [100, 100], [0, 100]]}
            for identity in self.IDS]}
        self.stack.enter_context(patch.object(self.p, 'panel_open', return_value=False))
        self.stack.enter_context(patch('app.win.foreground_root', return_value=7))

        def retain_hidden_text(overlay, binding, box, text):
            overlay.setText(text)

        self.place = self.stack.enter_context(patch.object(
            CardOverlay, 'place', autospec=True, side_effect=retain_hidden_text))

        class Source(DataJ):
            def request(self, *args, **kwargs):
                # These tests isolate delivery order, not production pacing.
                # Preserve validation, cache identities and error handling.
                if 0 < self.next_request - time.monotonic() <= 2:
                    self.next_request = 0
                return super().request(*args, **kwargs)

        self.p.adapter = Source(patch='18.2a', db=Path(self.tmp.name) / 'cache.db',
                                transport=httpx.MockTransport(self.response))
        self.p.session.patch = '18.2a'
        self.p.session.set_target('112')
        self.p.stage.blockSignals(True)
        self.p.stage.setCurrentText('2-1')
        self.p.stage.blockSignals(False)

    def tearDown(self):
        # Always release a blocked transport before waiting for workers, even
        # when an early visibility assertion fails on the unfixed code.
        self.release.set()
        self.p.hex_network.waitForDone(1500)
        self.qt.processEvents()
        self.p.offline = True
        self.p.shutdown()
        self.p.deleteLater()
        self.qt.processEvents()
        self.stack.close()
        self.tmp.cleanup()

    def response(self, request):
        self.calls.append(request)
        if request.url.path.endswith('/stats/hex'):
            data = [self.hex_row(identity, index, comp=False)
                    for index, identity in enumerate(self.IDS)]
        elif request.url.path.endswith('/comp/112/hexes'):
            data = {'compId': '112', 'hexes': [
                self.hex_row(identity, index, comp=True)
                for index, identity in enumerate(self.IDS) if identity in self.direct_ids]}
        else:
            if not request.url.path.endswith('/explorer/query'):
                raise AssertionError('Unexpected URL: ' + str(request.url))
            body = json.loads(request.content)
            rule = body['filter']['rules'][0]
            if body['version'] != '18.2a' or rule['hexRound'] != '0':
                raise AssertionError('Supplement changed patch or acquisition stage')
            identity = rule['targetId']
            index = self.IDS.index(identity)
            if identity == self.block_id:
                self.blocked.set()
                if not self.release.wait(1.5):
                    raise AssertionError('Test did not release the blocked HTTP response')
            data = {'comps': [{'compId': '112', 'name': 'Controlled fixture comp',
                               'avgPlacement': 2.75 + index * .1,
                               'sampleCount': 51 + index}]}
        return httpx.Response(200, json={'success': True, 'code': 200, 'data': data})

    @staticmethod
    def hex_row(identity, index, *, comp):
        return {'hexId': identity, 'roundStats': [
            {'round': 0, 'roundLabel': '2-1',
             'avgPlacement': 3.25 + index * .1 - (.5 if comp else 0),
             'sampleCount': 51 + index}]}

    def pump_until(self, predicate, timeout=.7):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            self.qt.processEvents()
            time.sleep(.001)
        self.qt.processEvents()
        return predicate()

    def start_blocked_query(self):
        self.p.query_stats(self.IDS, self.NAMES, True)
        self.assertTrue(self.pump_until(self.blocked.is_set),
                        'The exact supplement did not reach its controlled HTTP block')
        self.assertFalse(self.release.is_set())
        self.assertEqual([row[1] for row in self.p.stats_payload['rows']],
                         ['3.25 · 51局', '3.35 · 52局', '3.45 · 53局'])

    def comp_texts(self):
        return [row[2] for row in self.p.stats_payload['rows']]

    def assert_visible(self, index):
        expected = self.EXPECTED[index]
        self.assertEqual(self.comp_texts()[index], expected)
        self.assertIn(expected, self.p.result_cards[index].comp.text())
        self.assertIn(expected, self.p.overlays[index].text())

    def finish(self):
        self.release.set()
        self.assertTrue(self.pump_until(lambda: self.comp_texts() == self.EXPECTED))
        self.assertFalse(self.p.stats_payload['retryable'])

    def test_direct_ranks_are_visible_while_first_missing_rank_is_blocked(self):
        self.start_blocked_query()
        visible = self.pump_until(lambda: self.comp_texts()[1:] == self.EXPECTED[1:], .12)
        self.assertTrue(visible, 'Known direct composition ranks were held behind an unrelated slow supplement')
        self.assert_visible(1)
        self.assert_visible(2)
        self.assertNotEqual(self.comp_texts()[0], self.EXPECTED[0])
        self.assertFalse(self.release.is_set())
        self.finish()

    def test_completed_supplement_is_visible_while_later_supplement_is_blocked(self):
        self.direct_ids.clear()
        self.block_id = self.IDS[2]
        self.start_blocked_query()
        visible = self.pump_until(lambda: self.comp_texts()[0] == self.EXPECTED[0], .12)
        self.assertTrue(visible, 'A finished exact supplement was held until all remaining supplements completed')
        self.assert_visible(0)
        self.assertNotEqual(self.comp_texts()[2], self.EXPECTED[2])
        self.assertFalse(self.release.is_set())
        self.finish()

    def test_late_supplement_after_choice_token_changes_cannot_publish(self):
        self.start_blocked_query()
        old_token = self.p.session.token()
        self.p.session.set_choices('2-1', list(reversed(self.IDS)))
        self.p.stats_payload = None
        self.place.reset_mock()
        self.release.set()
        self.assertTrue(self.pump_until(lambda: not self.p.jobs))
        self.assertFalse(self.p.session.accepts(old_token))
        self.assertIsNone(self.p.stats_payload)
        self.place.assert_not_called()

    def test_repeated_same_choices_do_not_queue_duplicate_network_jobs(self):
        self.start_blocked_query()
        first_calls = len(self.calls)
        for _ in range(20):
            self.p.query_stats(self.IDS, self.NAMES, True, refresh=True)
            self.qt.processEvents()
        self.assertEqual(len(self.calls), first_calls)
        self.assertLessEqual(len(self.p.jobs), 1)
        self.release.set()
        self.assertTrue(self.pump_until(lambda: self.comp_texts() == self.EXPECTED))
        exact_ids = [json.loads(request.content)['filter']['rules'][0]['targetId']
                     for request in self.calls if request.url.path.endswith('/explorer/query')]
        self.assertEqual(exact_ids, [self.IDS[0]])

    def test_obsolete_queued_global_job_does_not_send_http(self):
        pending=[]
        with patch.object(self.p,'submit',side_effect=lambda pool,fn,done,failed=None:
                          pending.append((fn,done))):
            self.p.query_stats(self.IDS,self.NAMES,True)
            old=pending.pop(0)
            self.p.session.set_target('120')
            old[1](old[0]())
        self.assertEqual(self.calls,[])
        self.assertIsNone(self.p.stats_payload)

    def test_source_worker_pool_is_independent_from_guide_queue(self):
        self.p.network.setMaxThreadCount(1)
        busy=threading.Event()
        unblock=threading.Event()
        def slow_guide():
            busy.set()
            unblock.wait(1.5)
        try:
            self.p.submit(self.p.network,slow_guide,lambda _:None)
            self.assertTrue(self.pump_until(busy.is_set))
            self.start_blocked_query()
            self.assertTrue(self.pump_until(lambda:self.comp_texts()[1:]==self.EXPECTED[1:]))
            self.assertFalse(unblock.is_set())
        finally:
            unblock.set()
            self.release.set()
            self.p.network.waitForDone(1500)

    def test_partial_snapshot_keeps_known_rank_until_other_candidates_finish(self):
        self.direct_ids.clear()
        self.block_id=self.IDS[2]
        self.start_blocked_query()
        self.assertTrue(self.pump_until(lambda:self.comp_texts()[0]==self.EXPECTED[0]))
        old=self.p.stats_payload
        self.p.query_stats(self.IDS,self.NAMES,True,refresh=True)
        self.assertIs(self.p.stats_payload,old)
        self.assert_visible(0)
        self.finish()

    def test_refresh_progress_keeps_new_source_metadata_with_newly_finished_ranks(self):
        self.start_blocked_query()
        self.finish()
        self.assertEqual(self.p.stats_payload['comp_supplemented_ids'],[self.IDS[0]])
        self.direct_ids.clear()
        self.block_id=self.IDS[2]
        self.blocked.clear()
        self.release.clear()
        with closing(sqlite3.connect(self.p.adapter.db)) as connection:
            connection.execute('UPDATE cache SET fetched=0')
            connection.commit()
        self.p.query_stats(self.IDS,self.NAMES,True,refresh=True)
        self.assertTrue(self.pump_until(self.blocked.is_set))
        self.assertTrue(self.pump_until(
            lambda:self.IDS[1] in self.p.stats_payload['comp_supplement_sources'],.25),
            'Fresh completed ranks must carry their own source metadata during refresh')
        self.assertIn(self.IDS[1],self.p.stats_payload['comp_supplemented_ids'])
        self.assert_visible(1)
        self.finish()


if __name__ == '__main__':
    unittest.main()
