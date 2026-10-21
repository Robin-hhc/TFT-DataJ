"""Partial exact-query failures reach the real local evidence archive.

The public fixture supplies independent statistics. Native capture and Qt task
dispatch are controlled; Companion, DataJ, result publication, BugReporter and
BugCaseStore stay on their production paths. This does not exercise live HTTP
or prove OCR, MuMu compositing or packaged EXE behavior.
"""
from copy import deepcopy
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx
from PIL import Image

from bug_cases import BugCaseStore
from bug_reporting import BugReporter
import test_hex_comp_supplement_ui as ui_fixture

FIXTURE = ui_fixture.FIXTURE


class HexFailureDiagnosticsTests(unittest.TestCase):
    IDS = ui_fixture.HexCompSupplementUI.IDS
    NAMES = ui_fixture.HexCompSupplementUI.NAMES
    EXPECTED = ui_fixture.HexCompSupplementUI.EXPECTED
    setUpClass = classmethod(ui_fixture.HexCompSupplementUI.setUpClass.__func__)
    tearDown = ui_fixture.HexCompSupplementUI.tearDown
    query = ui_fixture.HexCompSupplementUI.query
    complete = ui_fixture.HexCompSupplementUI.complete
    explorer_ids = ui_fixture.HexCompSupplementUI.explorer_ids
    assert_global_controls = ui_fixture.HexCompSupplementUI.assert_global_controls

    def setUp(self):
        ui_fixture.HexCompSupplementUI.setUp(self)
        self.stack.enter_context(patch('bug_reporting.record'))
        # Restore the actual reporter suppressed by the UI fixture; write only
        # inside this test's independent temporary archive.
        original = BugReporter.hex_statistics.__get__(self.p.bugs)
        self.report = self.stack.enter_context(patch.object(
            self.p.bugs, 'hex_statistics', wraps=original))
        self.p.bugs.enabled = True
        self.p.bugs.store = BugCaseStore(Path(self.tmp.name) / 'bug-cases')
        self.p.binding = SimpleNamespace(hwnd=7, process='MuMuNxDevice.exe',
                                         rect=(0, 0, 320, 180))
        self.p.last_frame = Image.new('RGB', (320, 180), '#193823')
        self.p.last_observation = {'scene': 'choice_candidates', 'round': '3-2',
            'cards': [{'slot': index, 'raw_text': name,
                       'box': [[index * 100, 20], [index * 100 + 90, 20],
                               [index * 100 + 90, 50], [index * 100, 50]],
                       'resolution': {'status': 'resolved', 'id': identity, 'name': name}}
                      for index, (identity, name) in enumerate(zip(self.IDS, self.NAMES))]}
        self.success_before_failure = {identity: threading.Event() for identity in self.IDS[:2]}
        self.transport_failure = 'timeout'

    def response(self, request):
        if (request.url.path.endswith('/explorer/query')
                and json.loads(request.content)['filter']['rules'][0]['targetId'] == self.IDS[2]):
            self.calls.append(request)
            # Both useful responses must be consumed before this late failure.
            # This tests preservation, rather than accepting a nondeterministic
            # early cooldown that prevents all three requests from being sent.
            for identity, ready in self.success_before_failure.items():
                if not ready.wait(2):
                    raise AssertionError('Successful exact query did not finish: ' + identity)
            if self.transport_failure == 'timeout':
                raise httpx.ReadTimeout('private-token-must-not-appear-in-diagnostics', request=request)
            if self.transport_failure == 'empty':
                return httpx.Response(200, json={'success': True, 'code': 200, 'data': {'comps': []}})
            return httpx.Response(503, json={'private': 'must-not-appear-in-diagnostics'})
        return ui_fixture.HexCompSupplementUI.response(self, request)

    def finish_partial_failure(self, *, expect_failure=True):
        original = self.p.adapter.iter_comp_hex_supplements

        def signal_successes(*args, **kwargs):
            for identity, result, error in original(*args, **kwargs):
                if identity in self.success_before_failure and result is not None and error is None:
                    self.success_before_failure[identity].set()
                yield identity, result, error

        with patch.object(self.p.adapter, 'iter_comp_hex_supplements', side_effect=signal_successes):
            self.query()
            self.complete()  # global response starts the composition worker
            self.assertEqual(self.report.call_count, 0)
            self.p.last_capture = time.monotonic()
            self.complete()  # direct table, individual progress and terminal callback
        self.assert_global_controls()
        self.assertEqual([row[2] for row in self.p.stats_payload['rows']],
                         self.EXPECTED[:2] + ['阵容补查失败' if expect_failure else '— 本阵容暂无统计'])
        self.assertEqual(self.p.stats_payload['retryable'], expect_failure)
        for card, value in zip(self.p.result_cards[:2], self.EXPECTED[:2]):
            self.assertIn(value, card.comp.text())

    def archived_failure(self):
        reports = [call for call in self.report.call_args_list
                   if call.args[0] == 'hex_comp_supplement_failed']
        self.assertEqual(len(reports), 1,
                         'A partial exact-query failure must produce one terminal diagnostic archive')
        self.assertEqual(len(self.pending), 1, 'The archive must use the normal background save worker')
        self.complete()
        manifests = list((Path(self.tmp.name) / 'bug-cases').glob('case-*/case.json'))
        self.assertEqual(len(manifests), 1)
        case = json.loads(manifests[0].read_text(encoding='utf-8'))
        self.assertEqual(case['reason'], 'hex_comp_supplement_failed')
        self.assertEqual(case['context']['target'], '107')
        evidence = case['evidence']
        self.assertEqual(evidence['stage'], '3-2')
        self.assertEqual(evidence['requested_ids'], self.IDS)
        self.assertEqual(evidence['failed_ids'], [self.IDS[2]])
        self.assertEqual(evidence['supplement_errors'], {self.IDS[2]: '阵容阶段补查暂不可用'})
        detail = evidence['supplement_error_details'][self.IDS[2]]
        self.assertEqual(detail['scope'], {'set_id': 18, 'patch': '18.3', 'comp': '107',
                                           'stage': '3-2', 'hex_id': self.IDS[2]})
        actual = next(request for request in self.calls
                      if request.url.path.endswith('/explorer/query')
                      and json.loads(request.content)['filter']['rules'][0]['targetId'] == self.IDS[2])
        self.assertEqual(detail['request'], {'method': 'POST', 'path': '/explorer/query',
                                             'body': json.loads(actual.content)})
        self.assertEqual(evidence['global_statistics'], [row for row in FIXTURE['global']['data']
                         if str(row['hexId']) in self.IDS])
        comp_rows = evidence['comp_statistics']
        self.assertTrue(any(str(row['hexId']) == self.IDS[0] for row in comp_rows))
        self.assertTrue(any(str(row['hexId']) == self.IDS[1] for row in comp_rows))
        serialized = json.dumps(case, ensure_ascii=False)
        self.assertNotIn('private-token-must-not-appear-in-diagnostics', serialized)
        self.assertNotIn('must-not-appear-in-diagnostics', serialized)
        return deepcopy(detail)

    def test_partial_timeout_archives_exact_failure_and_preserves_two_successes(self):
        self.finish_partial_failure()
        detail = self.archived_failure()
        self.assertEqual(detail['reason'], 'timeout')
        self.assertIn('SourceError', detail['exception_types'])
        self.assertIn('ReadTimeout', detail['exception_types'])
        self.assertGreater(detail['retry_after_seconds'], 0)

    def test_partial_http_503_archives_status_without_private_body(self):
        self.transport_failure = 'http503'
        self.finish_partial_failure()
        detail = self.archived_failure()
        self.assertEqual(detail['reason'], 'http_error')
        self.assertEqual(detail['http_status'], 503)
        self.assertIn('HTTPStatusError', detail['exception_types'])
        self.assertGreater(detail['response_bytes'], 0)
        self.assertEqual(len(detail['response_sha256']), 64)

    def test_successful_empty_exact_query_is_no_data_and_produces_no_failure_archive(self):
        self.transport_failure = 'empty'
        self.finish_partial_failure(expect_failure=False)
        self.assertEqual(self.report.call_count, 0)
        self.assertEqual(self.pending, [])
        self.assertEqual(list((Path(self.tmp.name) / 'bug-cases').glob('case-*')), [])

    def test_obsolete_terminal_failure_cannot_archive_against_a_new_target(self):
        self.query()
        self.complete()
        _, done, _ = self.pending.pop(0)
        # Deliver validated direct response and a structured failure exactly as
        # the production worker would, but after a new pin invalidates its token.
        global_result = self.p.adapter.hexes()
        comp_result = self.p.adapter.hexes('107')
        comp_result.update(supplement_errors={self.IDS[2]: '阵容阶段补查暂不可用'},
                           supplement_error_details={self.IDS[2]: {'reason': 'timeout'}})
        payload = (global_result, comp_result)
        self.p.session.set_target('108')
        done(payload)
        self.assertEqual(self.report.call_count, 0)
        self.assertEqual(self.pending, [])
        self.assertEqual(list((Path(self.tmp.name) / 'bug-cases').glob('case-*')), [])

    def test_catalog_missing_title_and_unconfirmed_text_keep_distinct_qt_labels_and_no_ids(self):
        observation = deepcopy(self.p.last_observation)
        observation.update(image_size=(320, 180), elapsed_ms=1)
        observation['cards'][0].update(raw_text='战时补给：女神之泪', resolution={
            'status': 'unrecognized', 'reason': 'catalog_missing_title', 'candidates': [],
            'readings': ['战时补给：女神之泪'] * 3})
        observation['cards'][1].update(raw_text='不完整文字', resolution={
            'status': 'unrecognized', 'reason': 'title_unconfirmed', 'candidates': [],
            'readings': ['不完整文字']})
        self.p.observed(observation, True)
        self.complete()
        self.assertEqual(self.p.session.choices, (None, None, self.IDS[2]))
        self.assertEqual(self.p.choice_table.item(0, 0).text(), '战时补给：女神之泪（目录无精确项）')
        self.assertEqual(self.p.choice_table.item(1, 0).text(), '不完整文字（名称待确认）')
        self.assertEqual(self.p.choice_table.item(0, 1).text(), '— 未识别')
        self.assertEqual(self.p.choice_table.item(1, 1).text(), '— 未识别')
        self.assertEqual(self.explorer_ids(), [], 'Unresolved identities must not be sent as exact queries')


if __name__ == '__main__':
    unittest.main()
