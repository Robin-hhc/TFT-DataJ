"""The visible sample control sends its own request and ignores older replies."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import httpx
from app import QApplication
import test_game_resource_inputs as fixtures


class CompactSampleLifecycleTests(unittest.TestCase):
    flush = fixtures.GameResourceInputTests.flush
    tearDown = fixtures.GameResourceInputTests.tearDown

    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        with patch('app.win.enumerate_mumu', return_value=[]):
            fixtures.GameResourceInputTests.setUp(self)
        self.p.browser.retry()
        self.flush()

    def response(self, request):
        self.calls.append(request)
        path = request.url.path
        if path.endswith('/comp/rank'):
            minimum = int(request.url.params['minSample'])
            data = [{'compId': '112', 'name': f'样本 {minimum}', 'avgPlacement': 4.44,
                     'sampleCount': 2000, 'heroes': [], 'traits': []}]
        elif path.endswith('/explorer/query'):
            data = {'comps': []}
        elif path.endswith('/gamedata'):
            data = deepcopy(fixtures.CATALOG)
        else:
            data = []
        return httpx.Response(200, json={'success': True, 'code': 200, 'data': data})

    def choose_minimum(self, minimum):
        index = self.p.browser.sample.findData(minimum)
        self.assertGreaterEqual(index, 0)
        self.p.browser.sample.setCurrentIndex(index)

    def test_fast_threshold_changes_capture_each_request_and_reject_late_reply(self):
        self.choose_minimum(500)
        old_fetch, old_done, _ = self.pending.pop(0)
        self.choose_minimum(1000)
        new_fetch, new_done, _ = self.pending.pop(0)
        # Requests may start after the next UI change; their captured threshold
        # must not be read from the later live combo-box value.
        old_result = old_fetch()
        new_done(new_fetch())
        old_done(old_result)
        sent = [int(r.url.params['minSample']) for r in self.calls
                if r.url.path.endswith('/comp/rank')]
        self.assertEqual(sent, [50, 500, 1000])
        self.assertEqual(self.p.browser.rows[0]['name'], '样本 1000')
        self.assertEqual([card.comp_id for card in self.p.browser.cards], ['112'])


if __name__ == '__main__':
    unittest.main()
