"""Exercise the real browser with a reduced, captured explorer response."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import httpx
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from comp_browser import CompBrowser
from dataj import DataJ


class CompBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])
        cls.fixture = json.loads((Path(__file__).parent/'fixtures/explorer-dark-ritual.json').read_text(encoding='utf-8'))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        settings = QSettings(str(Path(self.tmp.name)/'settings.ini'), QSettings.Format.IniFormat)
        self.browser = CompBrowser(settings, offline=True)
        self.browser.set_catalog({'hex':[self.fixture['entity']]})
        self.browser.set_filter('hex', self.fixture['entity'])

    def tearDown(self):
        self.browser.close()
        self.browser.deleteLater()
        self.qt.processEvents()
        self.tmp.cleanup()

    def ids(self):
        return [card.comp_id for card in self.browser.cards]

    def test_dark_ritual_live_response_and_cached_response_match_site(self):
        calls = []
        def handle(request):
            calls.append(request)
            return httpx.Response(200, json={'code':200,'success':True,'data':{'comps':self.fixture['comps']}})
        adapter = DataJ(db=Path(self.tmp.name)/'cache.db', transport=httpx.MockTransport(handle))
        for expected_cached in (False, True):
            result = adapter.explore('hex', self.fixture['entity'])
            self.assertEqual(result['cached'], expected_cached)
            self.browser.set_result(result['data']['comps'], adapter.patch)
            self.assertEqual(self.ids(), ['120', '100'])
            # The shared raw response must remain intact for equipment statistics.
            self.assertTrue(any(r['compId']=='116' for r in result['data']['comps']))
        self.assertEqual(len(calls), 1)
        body = json.loads(calls[0].content)
        self.assertEqual(body['filter']['rules'][0]['targetId'], '20778')
        self.assertEqual(body['version'], '18.2a')

    def test_sample_threshold_applies_before_sort_search_favorites_and_pagination(self):
        self.browser.set_result(copy.deepcopy(self.fixture['comps']), '18.2a')
        self.browser.sort.setCurrentIndex(1)
        self.assertEqual(self.ids(), ['120', '100'])
        self.browser.search.setText('裁决螳螂')
        self.assertEqual(self.ids(), [])
        self.browser.search.clear()
        self.browser.favorite_changed('116', True)
        self.browser.only_favs.setChecked(True)
        self.assertEqual(self.ids(), [])
        self.browser.only_favs.setChecked(False)
        self.browser.show_more()
        self.assertEqual(self.ids(), ['120', '100'])

    def test_threshold_boundary_and_empty_results_never_fall_back_to_global(self):
        # Synthetic counts cover the exact boundary independently of live values.
        rows = [{'compId':'1','name':'49局','avgPlacement':1,'sampleCount':49},
                {'compId':'2','name':'50局','avgPlacement':5,'sampleCount':50}]
        self.browser.set_result(rows, '18.2a')
        self.assertEqual(self.ids(), ['2'])
        self.browser.set_result(rows[:1], '18.2a')
        self.assertEqual(self.ids(), [])
        self.assertFalse(self.browser.empty.isHidden())
        self.assertIn('50', self.browser.empty.text())
        self.assertEqual(self.browser.scope[1]['id'], '20778')


if __name__ == '__main__':
    unittest.main()
