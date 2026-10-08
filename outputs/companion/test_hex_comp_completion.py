"""Statistics completions survive brief focus changes without painting overlays.

Only worker completion order, HTTP transport and native overlay placement are
controlled. The real adapter, session tokens and Companion callbacks are used.
"""
from contextlib import ExitStack
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx
from app import QApplication, CardOverlay, Companion
from dataj import DataJ


class HexCompCompletion(unittest.TestCase):
    IDS = ['1023', '1479', '1006']
    NAMES = ['应急护甲 I', '黑铁资产', '进攻宣告']

    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.stack = ExitStack()
        self.pending = []
        self.calls = []
        self.comp_fails = False
        self.foreground = 7
        self.panel_is_open = False
        for module in ['app', 'dataj', 'comp_browser']:
            self.stack.enter_context(patch(module + '.STATE_DIR', Path(self.tmp.name)))
        self.stack.enter_context(patch('app.win.enumerate_mumu', return_value=[]))
        self.p = Companion(offline=True, offline_catalog={
            'hex': [], 'hero': [], 'trait': [], 'equip': []})
        self.p.timer.stop()
        self.p.binding = SimpleNamespace(hwnd=7)
        self.p.last_capture = time.monotonic()
        self.p.last_observation = {'cards': [
            {'resolution': {'id': identity}, 'box': [[0, 0], [100, 0], [100, 100], [0, 100]]}
            for identity in self.IDS]}
        self.stack.enter_context(patch.object(self.p, 'panel_open', side_effect=lambda: self.panel_is_open))
        self.stack.enter_context(patch('app.win.foreground_root', side_effect=lambda: self.foreground))
        self.place = self.stack.enter_context(patch.object(CardOverlay, 'place'))
        self.stack.enter_context(patch.object(self.p, 'submit',
            side_effect=lambda pool, fn, done, failed=lambda _: None:
                self.pending.append((fn, done, failed))))
        transport = httpx.MockTransport(self.response)

        class Source(DataJ):
            def request(self, *args, **kwargs):
                # Keep production cache/validation; omit unrelated wall-clock
                # rate-limit waits when replaying a failed request's recovery.
                self.next_request = 0
                return super().request(*args, **kwargs)

        self.p.adapter = Source(patch='18.2a', db=Path(self.tmp.name) / 'cache.db', transport=transport)
        self.p.session.patch = '18.2a'
        self.p.session.set_target('112')
        self.p.stage.blockSignals(True)
        self.p.stage.setCurrentText('2-1')
        self.p.stage.blockSignals(False)

    def tearDown(self):
        self.p.shutdown()
        self.p.deleteLater()
        self.qt.processEvents()
        self.stack.close()
        self.tmp.cleanup()

    def response(self, request):
        self.calls.append(request)
        comp = request.url.path.endswith('/comp/112/hexes')
        if comp and self.comp_fails:
            raise httpx.ConnectError('temporary comp failure', request=request)
        rows = [{'hexId': identity, 'roundStats': [
            {'round': 0, 'roundLabel': '2-1', 'avgPlacement': 3.25 + index * .1 - (.5 if comp else 0),
             'sampleCount': 51 + index}]}
            for index, identity in enumerate(self.IDS)]
        data = {'compId': '112', 'hexes': rows} if comp else rows
        return httpx.Response(200, json={'success': True, 'code': 200, 'data': data})

    def query(self, **kwargs):
        self.p.query_stats(self.IDS, self.NAMES, True, **kwargs)

    def complete(self):
        fn, done, failed = self.pending.pop(0)
        try:
            value = fn()
        except Exception as exc:
            failed(str(exc))
        else:
            done(value)

    def assert_comp_values(self):
        self.assertEqual([row[2] for row in self.p.stats_payload['rows']],
                         ['2.75 · 51局', '2.85 · 52局', '2.95 · 53局'])
        self.assertFalse(self.p.stats_payload['retryable'])

    def test_comp_success_while_briefly_unfocused_is_retained_and_not_refetched(self):
        self.query()
        self.complete()
        self.assertEqual(self.p.stats_payload['rows'][0][1], '3.25 · 51局')
        self.assertEqual(len(self.pending), 1)
        self.place.reset_mock()
        self.foreground = 99
        self.complete()
        self.assert_comp_values()
        self.place.assert_not_called()
        self.foreground = 7
        self.query()
        self.assert_comp_values()
        self.assertEqual(len(self.pending), 0)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.place.call_count, 3)

    def test_global_success_while_briefly_unfocused_still_starts_comp_query(self):
        self.query()
        self.foreground = 99
        self.complete()
        self.assertIsNotNone(self.p.stats_payload)
        self.assertEqual(self.p.stats_payload['rows'][0][1], '3.25 · 51局')
        self.assertEqual(len(self.pending), 1, 'Global completion must still schedule the comp response')
        self.place.assert_not_called()
        self.foreground = 7
        self.complete()
        self.assert_comp_values()
        self.assertEqual(len(self.calls), 2)

    def test_comp_failure_while_briefly_unfocused_remains_retryable(self):
        self.query()
        self.complete()
        self.place.reset_mock()
        self.foreground = 99
        self.comp_fails = True
        self.complete()
        self.assertTrue(self.p.stats_payload['retryable'])
        self.assertEqual(self.p.stats_payload['rows'][0][1], '3.25 · 51局')
        self.assertEqual(self.p.stats_payload['rows'][0][2], '阵容数据暂不可用')
        self.place.assert_not_called()
        self.foreground = 7
        self.comp_fails = False
        self.query(refresh=True)
        self.complete()
        self.complete()
        self.assert_comp_values()
        self.assertEqual(len(self.calls), 3, 'Retry should reuse fresh global data and request only comp data')

    def test_open_panel_accepts_current_completions_without_painting_overlays(self):
        self.query()
        self.panel_is_open = True
        self.complete()
        self.assertIsNotNone(self.p.stats_payload)
        self.assertEqual(len(self.pending), 1)
        self.complete()
        self.assert_comp_values()
        self.place.assert_not_called()
        self.panel_is_open = False
        self.query()
        self.assertEqual(self.place.call_count, 3)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(len(self.pending), 0)

    def test_token_changes_still_discard_comp_completion(self):
        for kind in ['target', 'patch', 'stage', 'new_game']:
            with self.subTest(kind=kind):
                self.p.session.patch = '18.2a'
                self.p.session.set_target('112')
                self.query()
                self.complete()
                token = self.p.session.token()
                retained = self.p.stats_payload
                if kind == 'target':
                    self.p.session.set_target('120')
                elif kind == 'patch':
                    self.p.session.patch = '18.3'
                elif kind == 'stage':
                    self.p.session.set_choices('3-2', self.IDS)
                else:
                    self.p.session.reset()
                self.assertFalse(self.p.session.accepts(token))
                self.place.reset_mock()
                self.complete()
                self.assertIs(self.p.stats_payload, retained, 'Old completion must not publish a replacement payload')
                self.assertEqual(self.p.stats_payload['rows'][0][2], '阵容数据读取中…')
                self.place.assert_not_called()
                self.assertEqual(len(self.pending), 0)


if __name__ == '__main__':
    unittest.main()
