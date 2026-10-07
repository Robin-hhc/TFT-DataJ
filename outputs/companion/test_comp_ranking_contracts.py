"""Website ranking controls and frozen-response oracles, with no live I/O."""
import gzip
import json
from pathlib import Path
import tempfile
import unittest

import httpx
from dataj import DataJ, SourceError


class CompRankingContracts(unittest.TestCase):
    def test_frozen_pick_rate_oracle_keeps_website_ties_not_sample_order(self):
        from display_audit import ranked_comp_expectation
        fixture = Path(__file__).parent/'fixtures/data_display/matrix.json.gz'
        records = json.loads(gzip.decompress(fixture.read_bytes()))['records']
        record = next(row for row in records if row['request']['path'] == '/comp/rank'
                      and row['request']['params']['gameVersion'] == '18.2a')
        raw = {row['compId']: row for row in record['data']}
        self.assertEqual((raw['105']['pickRate'], raw['107']['pickRate']), (0.19, 0.19))
        self.assertEqual((raw['105']['sampleCount'], raw['107']['sampleCount']), (7582, 7601))
        expected = ranked_comp_expectation(record, 1)
        ids = [row['id'] for row in expected]
        self.assertEqual(ids[:13], ['112', '95', '99', '117', '116', '104', '84',
                                   '89', '119', '88', '106', '105', '107'])
        self.assertNotEqual(ids, [row['id'] for row in record['expected']['samples']])
        self.assertEqual(expected[11], {'id': '105', 'name': '森林月男',
                                      'metrics': ['4.47', '51.2%', '10.5%'], 'samples': '7,582 局'})
        self.assertEqual(ranked_comp_expectation(record, 0), record['expected']['average'])

    def test_bad_pick_rates_are_rejected_before_display_but_missing_is_allowed(self):
        base = {'compId': '112', 'name': '测试阵容', 'sampleCount': 50,
                'avgPlacement': 4.2}
        for value in (None, True, False, '0.23', -0.01, float('nan'),
                      float('inf'), float('-inf'), [], {}):
            with self.subTest(value=value), self.assertRaises(SourceError):
                DataJ.validate_comps([{**base, 'pickRate': value}])
        for value in (0, 0.23, 1.24, 8):
            row = {**base, 'pickRate': value}
            DataJ.validate_comps([row])
            self.assertEqual(row['pickRate'], value)
        DataJ.validate_comps([base])
        self.assertNotIn('pickRate', base, 'Missing rate cannot become a synthetic zero')

    def test_only_website_minimum_sample_choices_are_allowed(self):
        calls = []
        def transport(request):
            calls.append(request)
            return httpx.Response(200, json={'success': True, 'code': 200, 'data': []})
        with tempfile.TemporaryDirectory() as tmp:
            adapter = DataJ(db=Path(tmp)/'cache.db', transport=httpx.MockTransport(transport))
            for value in (None, True, False, 0, -1, 25, 50.0, '50', 10001):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    adapter.comps(min_sample=value)
            self.assertEqual(calls, [], 'Invalid controls must not make network requests')
            for minimum in (1, 10, 50, 100, 300, 500, 1000, 3000, 10000):
                adapter.next_request = 0
                adapter.comps(min_sample=minimum)
                self.assertEqual(calls[-1].url.params['minSample'], str(minimum))

    def test_selected_minimum_reaches_request_and_separates_cached_responses(self):
        calls = []
        def transport(request):
            calls.append(request)
            minimum = request.url.params['minSample']
            return httpx.Response(200, json={'success': True, 'code': 200, 'data': [
                {'compId': '112', 'name': 'threshold ' + minimum,
                 'avgPlacement': 4.2, 'sampleCount': 100}]})
        with tempfile.TemporaryDirectory() as tmp:
            adapter = DataJ(db=Path(tmp)/'cache.db', transport=httpx.MockTransport(transport))
            original = adapter.comps()
            self.assertFalse(original['cached'])
            for minimum in (10, 1):
                adapter.next_request = 0
                result = adapter.comps(min_sample=minimum)
                self.assertFalse(result['cached'])
                self.assertEqual(result['data'][0]['name'], 'threshold ' + str(minimum))
            restored = adapter.comps()
            self.assertTrue(restored['cached'])
            self.assertEqual(restored['data'][0]['name'], 'threshold 50')
            self.assertEqual([dict(call.url.params) for call in calls], [
                {'setId': '18', 'gameVersion': '18.2a', 'minSample': str(minimum)}
                for minimum in (50, 10, 1)])


class CompRankingDisplayContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        from PySide6.QtCore import QSettings
        from comp_browser import CompBrowser
        self.tmp = tempfile.TemporaryDirectory()
        settings = QSettings(str(Path(self.tmp.name)/'ui.ini'), QSettings.Format.IniFormat)
        self.browser = CompBrowser(settings, offline=True)

    def tearDown(self):
        self.browser.close()
        self.browser.deleteLater()
        self.qt.processEvents()
        self.tmp.cleanup()

    def test_real_pick_rates_keep_two_decimals_without_percent_or_sample_tiebreak(self):
        from PySide6.QtWidgets import QLabel
        fixture = Path(__file__).parent/'fixtures/data_display/matrix.json.gz'
        records = json.loads(gzip.decompress(fixture.read_bytes()))['records']
        record = next(row for row in records if row['request']['path'] == '/comp/rank'
                      and row['request']['params']['gameVersion'] == '18.2a')
        self.browser.set_sort('pick')
        self.browser.set_result(record['data'], '18.2a')
        self.browser.show_more()
        self.assertEqual([card.comp_id for card in self.browser.cards[:13]],
                         ['112', '95', '99', '117', '116', '104', '84',
                          '89', '119', '88', '106', '105', '107'])
        cards = {card.comp_id: card for card in self.browser.cards}
        for identity, expected in [('112', '1.24'), ('95', '1.13'), ('105', '0.19'), ('107', '0.19')]:
            self.assertEqual(cards[identity].findChild(QLabel, 'compPickRate').text(), expected)
        self.assertEqual([label.text() for label in cards['105'].findChildren(QLabel, 'compAverage')],
                         ['4.47', '51.2%', '10.5%'])

    def test_missing_pick_rate_stays_unavailable_and_sorts_after_real_zero(self):
        from PySide6.QtWidgets import QLabel
        rows = [{'compId': '1', 'name': 'missing', 'avgPlacement': 1.1, 'sampleCount': 999},
                {'compId': '2', 'name': 'zero', 'avgPlacement': 5.1, 'sampleCount': 50, 'pickRate': 0},
                {'compId': '3', 'name': 'present', 'avgPlacement': 6.1, 'sampleCount': 51, 'pickRate': 0.01}]
        self.browser.set_sort('pick')
        self.browser.set_result(rows, '18.2a')
        self.assertEqual([card.comp_id for card in self.browser.cards], ['3', '2', '1'])
        self.assertEqual([card.findChild(QLabel, 'compPickRate').text() for card in self.browser.cards],
                         ['0.01', '0.00', '—'])
        self.assertNotIn('pickRate', rows[0])


if __name__ == '__main__':
    unittest.main()
