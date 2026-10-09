"""Pinned full prewarm through real Qt workers and validated DataJ responses.

The transport supplies deterministic source rows and event-controlled HTTP
responses. Native window placement and embedded-guide navigation are the only
UI boundaries replaced; no emulator, OCR runtime or live endpoint is needed.
"""
from contextlib import ExitStack
import json
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


class HexPrewarmUI(unittest.TestCase):
    IDS = ['1023', '1479', '1006']
    NAMES = ['应急护甲 I', '黑铁资产', '进攻宣告']
    STAGES = ['2-1', '3-2', '4-2']

    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.stack = ExitStack()
        self.calls = []
        self.call_lock = threading.Lock()
        self.detail_entered = threading.Event()
        self.detail_release = threading.Event()
        self.exact_entered = threading.Event()
        self.exact_release = threading.Event()
        self.detail_release.set()
        self.exact_release.set()
        self.block_exact = None
        self.exact_empty = set()
        self.direct_ids = set(self.IDS[1:])
        self.global_stages = [0]
        self.invalid_catalog = False
        for module in ['app', 'dataj', 'comp_browser']:
            self.stack.enter_context(patch(module + '.STATE_DIR', Path(self.tmp.name)))
        self.stack.enter_context(patch('app.win.enumerate_mumu', return_value=[]))
        self.stack.enter_context(patch('app.record'))
        self.p = Companion(offline=True, offline_catalog={
            'hex': [], 'hero': [], 'trait': [], 'equip': []})
        self.p.timer.stop()
        self.p.offline = False
        self.stack.enter_context(patch.object(self.p.bugs, 'hex_statistics'))
        self.stack.enter_context(patch.object(self.p, 'open_guide'))
        self.stack.enter_context(patch.object(self.p, 'panel_open', return_value=False))
        self.stack.enter_context(patch('app.win.foreground_root', return_value=7))

        def retain_hidden_text(overlay, binding, box, text):
            overlay.setText(text)

        self.place = self.stack.enter_context(patch.object(
            CardOverlay, 'place', autospec=True, side_effect=retain_hidden_text))

        class Source(DataJ):
            def request(self, *args, **kwargs):
                # Delivery and lifecycle are under test. Keep source cooldown
                # and validation while omitting only ordinary one-second pacing.
                if 0 < self.next_request - time.monotonic() <= 2:
                    self.next_request = 0
                return super().request(*args, **kwargs)

        self.source_type = Source
        self.p.adapter = self.make_source('18.2a')
        self.p.session.patch = '18.2a'
        self.p.catalog = {'hex': [
            {'id': identity, 'name': name, 'setId': 18}
            for identity, name in zip(self.IDS, self.NAMES)]}
        self.p.stage.blockSignals(True)
        self.p.stage.setCurrentIndex(-1)
        self.p.stage.blockSignals(False)

    def make_source(self, version):
        return self.source_type(patch=version,
            db=Path(self.tmp.name) / ('cache-' + version + '.db'),
            transport=httpx.MockTransport(self.response))

    def tearDown(self):
        self.detail_release.set()
        self.exact_release.set()
        self.p.offline = True
        self.p.shutdown()
        self.qt.processEvents()
        self.p.deleteLater()
        self.qt.processEvents()
        self.stack.close()
        self.tmp.cleanup()

    def response(self, request):
        with self.call_lock:
            self.calls.append(request)
        path = request.url.path
        if path.endswith('/stats/hex'):
            data = [self.hex_row(identity, index, comp=False)
                    for index, identity in enumerate(self.IDS)]
        elif path.endswith('/hexes'):
            comp = path.split('/')[-2]
            data = {'compId': comp, 'hexes': [
                self.hex_row(identity, index, comp=True)
                for index, identity in enumerate(self.IDS)
                if identity in self.direct_ids]}
        elif path.endswith('/explorer/query'):
            body = json.loads(request.content)
            rule = body['filter']['rules'][0]
            key = (rule['targetId'], rule['hexRound'])
            self.exact_entered.set()
            if key == self.block_exact:
                if not self.exact_release.wait(6):
                    raise AssertionError('Exact HTTP response was not released')
            index = self.IDS.index(key[0])
            data = {'comps': [] if key in self.exact_empty else [
                {'compId': '112', 'name': 'Controlled fixture comp',
                 'avgPlacement': 2.75 + index * .1 + int(key[1]) * .2,
                 'sampleCount': 51 + index},
                {'compId': '120', 'name': 'Replacement fixture comp',
                 'avgPlacement': 6.25 + index * .1 + int(key[1]) * .2,
                 'sampleCount': 71 + index}]}
        elif path.endswith('/equips'):
            data = {'compId': path.split('/')[-2], 'equips': []}
        elif path.split('/')[-2] == 'comp':
            self.detail_entered.set()
            if not self.detail_release.wait(6):
                raise AssertionError('Composition detail HTTP was not released')
            data = {'compId': path.split('/')[-1],
                    'name': 'Controlled fixture comp', 'heroes': []}
        elif path.endswith('/gamedata'):
            data = {'hex': None} if self.invalid_catalog else self.p.catalog
        else:
            raise AssertionError('Unexpected HTTP: ' + str(request.url))
        return httpx.Response(200, json={
            'success': True, 'code': 200, 'data': data})

    def hex_row(self, identity, index, *, comp):
        return {'hexId': identity, 'name': self.NAMES[index], 'roundStats': [
            {'round': stage, 'roundLabel': self.STAGES[stage],
             'avgPlacement': 3.25 + index * .1 + stage * .2 - (.5 if comp else 0),
             'sampleCount': 51 + index}
            for stage in self.global_stages]}

    def pump_until(self, predicate, timeout=3.5):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            self.qt.processEvents()
            threading.Event().wait(.001)
        self.qt.processEvents()
        return predicate()

    def pin(self, comp='112'):
        self.p.comp_url.setText('https://www.dataj.cc/comp/' + comp)
        self.p.pin_comp()

    def exact_requests(self):
        with self.call_lock:
            requests = list(self.calls)
        return [request for request in requests
                if request.url.path.endswith('/explorer/query')]

    def exact_keys(self):
        return [(rule['targetId'], rule['hexRound'])
                for request in self.exact_requests()
                for rule in json.loads(request.content)['filter']['rules']]

    def wait_prewarm(self, timeout=8):
        warm = self.p.hex_prewarm
        self.assertIsNotNone(warm, 'Pinning must own a cancellable session prewarm')
        self.assertTrue(self.pump_until(lambda: warm.wait(0), timeout),
                        'Controlled full prewarm did not complete')
        return warm

    def foreground(self, ids=None, stage='2-1'):
        ids = self.IDS if ids is None else ids
        names = [self.NAMES[self.IDS.index(identity)] for identity in ids]
        self.p.binding = SimpleNamespace(hwnd=7)
        self.p.last_capture = time.monotonic()
        self.p.last_observation = {'cards': [
            {'resolution': {'id': identity},
             'box': [[0, 0], [100, 0], [100, 100], [0, 100]]}
            for identity in ids]}
        self.p.stage.blockSignals(True)
        self.p.stage.setCurrentText(stage)
        self.p.stage.blockSignals(False)
        self.p.query_stats(ids, names, True)

    def comp_texts(self):
        return [row[2] for row in self.p.stats_payload['rows']]

    def test_pin_starts_missing_stage_prefetch_while_detail_http_is_blocked(self):
        self.detail_release.clear()
        self.pin()
        self.assertTrue(self.pump_until(self.detail_entered.is_set),
                        'Fixture detail request did not reach its controlled block')
        self.assertTrue(self.pump_until(self.exact_entered.is_set),
                        'Pinned missing-stage prefetch waited for composition details')
        self.assertFalse(self.detail_release.is_set())
        self.assertIsNone(self.p.comp_detail)
        request = self.exact_requests()[0]
        body = json.loads(request.content)
        self.assertEqual(body['version'], '18.2a')
        self.assertEqual(body['setId'], 18)
        self.assertEqual(body['filter']['rules'][0]['targetId'], '1023')
        self.assertEqual(body['filter']['rules'][0]['hexRound'], '0')

    def test_same_pin_reuses_positive_negative_and_tables_after_900_seconds(self):
        self.direct_ids = {self.IDS[2]}
        self.exact_empty = {(self.IDS[1], '0')}
        self.pin()
        self.wait_prewarm()
        self.assertCountEqual(self.exact_keys(), [('1023', '0'), ('1479', '0')])
        self.assertTrue(self.pump_until(lambda: not self.p.jobs))
        calls = len(self.calls)
        # Move wall time, including the real adapter's TTL check, forward by
        # more than fifteen minutes. The event pump keeps its real monotonic
        # clock, so this is a retention check without an elapsed-time sleep.
        later = time.time() + 901
        with patch('dataj.time.time', return_value=later):
            self.p.invalidate()
            self.foreground()
            expected = ['2.75 · 51局', '— 本阵容暂无统计', '2.95 · 53局']
            self.assertTrue(self.pump_until(
                lambda: self.p.stats_payload and self.comp_texts() == expected))
            self.assertFalse(self.p.stats_payload['retryable'])
            self.assertEqual([row[1] for row in self.p.stats_payload['rows']],
                             ['3.25 · 51局', '3.35 · 52局', '3.45 · 53局'])
            self.assertEqual(len(self.calls), calls,
                             'A pinned session must retain expired disk tables and empty exact results')
            self.p.query_stats(self.IDS, self.NAMES, True, refresh=True)
            self.assertTrue(self.pump_until(lambda: not self.p.jobs))
            self.assertEqual(self.comp_texts(), expected)
            self.assertEqual(len(self.calls), calls,
                             'Refreshing choices must not send an already-empty exact request again')

    def test_known_3_2_round_prefetches_only_current_and_future_missing_stages(self):
        self.global_stages = [0, 1, 2]
        self.p.last_probe_stage = '3-2'
        self.pin()
        self.wait_prewarm()
        self.assertEqual(self.exact_keys(), [('1023', '1'), ('1023', '2')],
                         'Known 3-2 must prioritize 3-2, then 4-2, and skip passed 2-1')

    def test_partial_cached_ranks_keep_candidate_slots_and_exact_source_scope(self):
        self.direct_ids.clear()
        self.block_exact = ('1006', '0')
        self.exact_release.clear()
        self.pin()
        self.assertTrue(self.pump_until(
            lambda: self.block_exact in self.exact_keys(), 5))
        warm = self.p.hex_prewarm
        ids = ['1006', '1023', '1479']
        self.foreground(ids)
        self.assertTrue(self.pump_until(lambda: self.p.stats_payload
            and self.comp_texts()[1:] == ['2.75 · 51局', '2.85 · 52局']))
        self.assertFalse(self.exact_release.is_set())
        for slot, identity, text in [(1, '1023', '2.75 · 51局'),
                                     (2, '1479', '2.85 · 52局')]:
            self.assertIn(text, self.p.result_cards[slot].comp.text())
            self.assertIn(text, self.p.overlays[slot].text())
            self.assertEqual(self.p.stats_payload['rows'][slot][0],
                             self.NAMES[self.IDS.index(identity)])
            source = self.p.stats_payload['comp_supplement_sources'][identity]
            self.assertEqual(source['scope'], {'set_id': 18, 'patch': '18.2a',
                'comp': '112', 'stage': '2-1', 'hex_id': identity})
        self.assertIs(self.p.hex_prewarm, warm,
                      'A new selection revision must retain the pin prewarm')
        self.exact_release.set()
        self.assertTrue(self.pump_until(lambda: self.comp_texts() == [
            '2.95 · 53局', '2.75 · 51局', '2.85 · 52局']))
        self.wait_prewarm()
        self.assertEqual(self.exact_keys().count(('1006', '0')), 1,
                         'Foreground must share the prewarm exact request already in flight')

    def assert_lifecycle_cancels(self, action):
        self.direct_ids.clear()
        self.block_exact = ('1023', '0')
        self.exact_release.clear()
        self.pin()
        self.assertTrue(self.pump_until(self.exact_entered.is_set))
        warm = self.p.hex_prewarm
        count = len(self.exact_requests())
        action()
        self.exact_release.set()
        self.assertTrue(self.pump_until(lambda: warm.wait(0)))
        self.assertIsNone(self.p.hex_prewarm)
        self.assertEqual(len(self.exact_requests()), count,
                         'Canceled context must not start its queued exact requests')
        self.assertIsNone(self.p.stats_payload,
                          'A finished obsolete HTTP response must not paint another context')

    def test_unpin_cancels_queued_missing_stages_and_late_publication(self):
        self.assert_lifecycle_cancels(self.p.unpin)
        self.assertIsNone(self.p.session.target)

    def test_new_game_cancels_queued_missing_stages_and_late_publication(self):
        previous_session = self.p.session.session_id
        self.assert_lifecycle_cancels(self.p.new_game)
        self.assertNotEqual(self.p.session.session_id, previous_session)
        self.assertIsNone(self.p.session.target)

    def test_changing_statistics_version_cancels_old_missing_stages(self):
        old_adapter = self.p.adapter
        # The new version's catalog fails at the genuine HTTP/schema boundary,
        # so the test needs no OCR setup and cannot auto-repin from a callback.
        self.invalid_catalog = True
        def change_version():
            self.p.patch.addItem('18.3')
            self.p.patch.setCurrentText('18.3')
            with patch('app.DataJ', side_effect=lambda **kw:
                       self.make_source(kw['patch'])):
                self.p.change_patch()
        self.assert_lifecycle_cancels(change_version)
        self.assertIsNot(self.p.adapter, old_adapter)
        self.assertEqual(self.p.adapter.patch, '18.3')
        self.assertEqual(self.p.session.patch, '18.3')

    def test_changing_composition_cannot_reuse_old_target_rank(self):
        self.direct_ids.clear()
        self.block_exact = ('1023', '0')
        self.exact_release.clear()
        self.pin()
        self.assertTrue(self.pump_until(self.exact_entered.is_set))
        old = self.p.hex_prewarm
        self.pin('120')
        replacement = self.p.hex_prewarm
        self.assertIsNot(replacement, old)
        self.exact_release.set()
        self.assertTrue(self.pump_until(lambda: old.wait(0)))
        self.wait_prewarm()
        self.foreground()
        self.assertTrue(self.pump_until(lambda: self.p.stats_payload
            and self.comp_texts() == ['6.25 · 71局', '6.35 · 72局', '6.45 · 73局']))
        self.assertEqual(self.p.session.target, '120')
        for source in self.p.stats_payload['comp_supplement_sources'].values():
            self.assertEqual(source['scope']['comp'], '120')

    def test_shutdown_cancels_queued_missing_stages(self):
        self.direct_ids.clear()
        self.block_exact = ('1023', '0')
        self.exact_release.clear()
        self.pin()
        self.assertTrue(self.pump_until(self.exact_entered.is_set))
        count = len(self.exact_requests())
        # Shutdown waits for worker completion. Releasing on a separate thread
        # after the public cancel signal avoids an unbounded Qt-thread wait.
        warm = self.p.hex_prewarm
        released = threading.Event()
        def release_after_cancel():
            while not released.is_set():
                if warm.hexes() is None:
                    self.exact_release.set()
                    return
                released.wait(.001)
        helper = threading.Thread(target=release_after_cancel, daemon=True)
        helper.start()
        try:
            self.p.shutdown()
        finally:
            released.set()
            self.exact_release.set()
            helper.join(1)
        self.assertTrue(warm.wait(0))
        self.assertEqual(len(self.exact_requests()), count)



if __name__ == '__main__':
    unittest.main()
