"""Frozen public comp rows through online-mode Qt callbacks, without live I/O.

Global and comp 107's direct/explorer values are preserved from the public
fixture. This replay is not a real-time capture or an OCR acceptance test.
"""
from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx
from app import QApplication, CardOverlay, Companion
from dataj import DataJ


FIXTURE = json.loads((Path(__file__).parent / 'fixtures/hex-comp-107-stage-20261008.json').read_text(encoding='utf-8'))


class HexCompSupplementUI(unittest.TestCase):
    IDS = ['20742', '30668', '20708']
    NAMES = ['四之力', '厨神阿福', '电火花 II']
    EXPECTED = ['4.23 · 13局 · 少', '4.54 · 13局 · 少', '4.75 · 8局 · 少']

    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.stack = ExitStack()
        self.pending = []
        self.calls = []
        self.fail_ids = set()
        self.empty_ids = set()
        self.responses = {
            (item['request']['filter']['rules'][0]['targetId'],
             item['request']['filter']['rules'][0]['hexRound']): deepcopy(item['data'])
            for item in FIXTURE['explorer']}
        for module in ['app', 'dataj', 'comp_browser']:
            self.stack.enter_context(patch(module + '.STATE_DIR', Path(self.tmp.name)))
        self.stack.enter_context(patch('app.win.enumerate_mumu', return_value=[]))
        self.stack.enter_context(patch('app.record'))
        self.p = Companion(offline=True, offline_catalog={
            'hex': [], 'hero': [], 'trait': [], 'equip': []})
        self.p.timer.stop()
        # Exercise the production supplement branch without installing global
        # mouse hooks, native capture, catalog fetching or a real HTTP client.
        self.p.offline = False
        self.stack.enter_context(patch.object(self.p.bugs, 'hex_statistics'))
        self.p.binding = SimpleNamespace(hwnd=7)
        self.p.last_capture = time.monotonic()
        self.p.last_observation = {'cards': [
            {'resolution': {'id': identity}, 'box': [[0, 0], [100, 0], [100, 100], [0, 100]]}
            for identity in self.IDS]}
        self.stack.enter_context(patch.object(self.p, 'panel_open', return_value=False))
        self.stack.enter_context(patch('app.win.foreground_root', return_value=7))

        def retain_hidden_text(overlay, binding, box, text):
            overlay.setText(text)
            overlay.adjustSize()

        self.place = self.stack.enter_context(patch.object(CardOverlay, 'place', autospec=True,
                                                          side_effect=retain_hidden_text))
        self.stack.enter_context(patch.object(self.p, 'submit',
            side_effect=lambda pool, fn, done, failed=lambda _: None:
                self.pending.append((fn, done, failed))))
        transport = httpx.MockTransport(self.response)

        class Source(DataJ):
            def request(self, *args, **kwargs):
                # Omit only normal one-second pacing. Preserve a failure's
                # long cooldown so one failed item cannot silently poison
                # the remaining two candidates without this test noticing.
                if 0 < self.next_request - time.monotonic() <= 2:
                    self.next_request = 0
                return super().request(*args, **kwargs)

        self.p.adapter = Source(patch=FIXTURE['patch'], db=Path(self.tmp.name) / 'cache.db', transport=transport)
        self.p.session.patch = FIXTURE['patch']
        self.p.session.set_target(FIXTURE['comp_id'])
        self.p.stage.blockSignals(True)
        self.p.stage.setCurrentText('3-2')
        self.p.stage.blockSignals(False)

    def tearDown(self):
        self.p.offline = True
        self.p.shutdown()
        self.p.deleteLater()
        self.qt.processEvents()
        self.stack.close()
        self.tmp.cleanup()

    def response(self, request):
        self.calls.append(request)
        if request.url.path.endswith('/stats/hex'):
            data = deepcopy(FIXTURE['global']['data'])
        elif request.url.path.endswith('/comp/107/hexes'):
            data = deepcopy(FIXTURE['direct']['data'])
        else:
            self.assertTrue(request.url.path.endswith('/explorer/query'), str(request.url))
            body = json.loads(request.content)
            self.assertEqual(body['setId'], 18)
            self.assertEqual(body['version'], '18.3')
            self.assertEqual(len(body['filter']['rules']), 1)
            rule = body['filter']['rules'][0]
            self.assertEqual(rule['type'], 'hex')
            self.assertEqual(rule['hexRound'], '1')
            identity = rule['targetId']
            self.assertIn(identity, self.IDS)
            if identity in self.fail_ids:
                raise httpx.ConnectError('single supplement failure', request=request)
            data = {'comps': []} if identity in self.empty_ids else self.responses[(identity, '1')]
        return httpx.Response(200, json={'success': True, 'code': 200, 'data': data})

    def query(self, ids=None, **kwargs):
        self.p.query_stats(self.IDS if ids is None else ids, self.NAMES, True, **kwargs)

    def complete(self):
        fn, done, failed = self.pending.pop(0)
        try:
            value = fn()
        except Exception as exc:
            failed(str(exc))
        else:
            done(value)

    def explorer_ids(self):
        return [json.loads(request.content)['filter']['rules'][0]['targetId']
                for request in self.calls if request.url.path.endswith('/explorer/query')]

    def assert_global_controls(self):
        self.assertEqual([row[1] for row in self.p.stats_payload['rows']],
                         ['4.91 · 1852局', '4.53 · 2311局', '4.45 · 283局'])

    def test_global_results_show_before_exact_comp_supplements_complete(self):
        self.query()
        self.complete()
        self.assert_global_controls()
        self.assertEqual(self.explorer_ids(), [])
        self.assertEqual(self.place.call_count, 3)
        self.assertEqual([row[2] for row in self.p.stats_payload['rows']], ['阵容数据读取中…'] * 3)
        self.complete()
        self.assert_global_controls()
        self.assertEqual([row[2] for row in self.p.stats_payload['rows']], self.EXPECTED)
        self.assertCountEqual(self.explorer_ids(), self.IDS)
        self.assertFalse(self.p.stats_payload['retryable'])
        self.assertEqual(self.p.stats_payload['comp_supplemented_ids'], self.IDS)
        for identity, samples in zip(self.IDS, [13, 13, 8]):
            source = self.p.stats_payload['comp_supplement_sources'][identity]
            self.assertEqual(source['sample_count'], samples)
            self.assertEqual(source['scope'], {'set_id': 18, 'patch': '18.3', 'comp': '107',
                                               'stage': '3-2', 'hex_id': identity})
        for card, overlay, expected in zip(self.p.result_cards, self.p.overlays, self.EXPECTED):
            self.assertIn(expected, card.comp.text())
            self.assertIn(expected, overlay.text())
            self.assertNotIn('未识别', card.comp.text())

    def test_same_confirmed_choices_reuse_supplemented_values_without_requests(self):
        self.query()
        self.complete()
        self.complete()
        self.assertEqual([row[2] for row in self.p.stats_payload['rows']], self.EXPECTED)
        calls = len(self.calls)
        self.query()
        self.assertEqual(len(self.calls), calls)
        self.assertEqual(len(self.pending), 0)
        self.assertCountEqual(self.explorer_ids(), self.IDS)

    def test_successful_empty_exact_query_is_missing_comp_data_not_unrecognized(self):
        self.empty_ids.add(self.IDS[0])
        self.query()
        self.complete()
        self.complete()
        rows = self.p.stats_payload['rows']
        self.assertEqual(rows[0][2], '— 本阵容暂无统计')
        self.assertNotIn('未识别', rows[0][2])
        self.assertEqual([row[2] for row in rows[1:]], self.EXPECTED[1:])
        self.assertFalse(self.p.stats_payload['retryable'])
        self.assert_global_controls()

    def test_last_failed_supplement_keeps_other_two_and_global_values_then_recovers(self):
        self.fail_ids.add(self.IDS[2])
        self.query()
        self.complete()
        self.complete()
        rows = self.p.stats_payload['rows']
        self.assertEqual(rows[0][2], self.EXPECTED[0])
        self.assertEqual(rows[1][2], self.EXPECTED[1])
        self.assertEqual(rows[2][2], '阵容补查失败')
        self.assertTrue(self.p.stats_payload['retryable'])
        self.assert_global_controls()
        retained_sources = deepcopy(self.p.stats_payload['comp_supplement_sources'])
        calls = len(self.calls)
        self.fail_ids.clear()
        # Recovery is a later user-triggered retry, after source cooldown.
        self.p.adapter.next_request = 0
        self.query(refresh=True)
        self.complete()
        self.assertEqual([row[2] for row in self.p.stats_payload['rows'][:2]], self.EXPECTED[:2],
                         'Retrying one missing item must not replace confirmed comp values with pending text')
        for identity in self.IDS[:2]:
            self.assertEqual(self.p.stats_payload['comp_supplement_sources'][identity], retained_sources[identity])
        self.complete()
        self.assertEqual([row[2] for row in self.p.stats_payload['rows']], self.EXPECTED)
        self.assertFalse(self.p.stats_payload['retryable'])
        self.assert_global_controls()
        self.assertEqual(len(self.calls), calls + 1, 'Only the failed exact query should miss the valid cache')
        self.assertEqual(self.explorer_ids()[-1], self.IDS[2])

    def test_first_failure_keeps_source_cooldown_and_marks_remaining_candidates_retryable(self):
        self.fail_ids.add(self.IDS[0])
        self.query()
        self.complete()
        self.complete()
        self.assertIn(self.IDS[0], self.explorer_ids())
        self.assertLessEqual(len(self.explorer_ids()), 3, 'At most the current three candidates may be in flight')
        rows = self.p.stats_payload['rows']
        self.assertEqual(rows[0][2], '阵容补查失败')
        for index in (1,2):
            expected = self.EXPECTED[index] if self.IDS[index] in self.explorer_ids() else '阵容补查失败'
            self.assertEqual(rows[index][2], expected)
        self.assertTrue(self.p.stats_payload['retryable'])
        self.assert_global_controls()
        self.assertGreater(self.p.adapter.next_request - time.monotonic(), 2)
        calls = len(self.calls)
        self.query(refresh=True)
        self.complete()
        self.complete()
        self.assertEqual(len(self.calls), calls, 'A later retry must respect the shared failure cooldown')

    def test_unrecognized_candidate_never_creates_an_explorer_rule(self):
        self.query([self.IDS[0], None, self.IDS[2]])
        self.complete()
        self.complete()
        self.assertCountEqual(self.explorer_ids(), [self.IDS[0], self.IDS[2]])
        rows = self.p.stats_payload['rows']
        self.assertEqual(rows[1][1:], ['— 未识别', '— 未识别'])
        self.assertEqual(rows[0][2], self.EXPECTED[0])
        self.assertEqual(rows[2][2], self.EXPECTED[2])


if __name__ == '__main__':
    unittest.main()
