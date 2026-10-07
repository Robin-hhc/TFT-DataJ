"""Exercise the real browser with a reduced, captured explorer response."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import httpx
from PySide6.QtCore import QSettings,Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QLineEdit,QLabel
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

    def test_sample_threshold_applies_before_sort_search_and_pagination(self):
        self.browser.set_result(copy.deepcopy(self.fixture['comps']), '18.2a')
        self.browser.set_sort('pick')
        self.assertEqual(self.ids(), ['120', '100'])
        self.browser.search.setText('裁决螳螂')
        self.assertEqual(self.ids(), [])
        self.browser.search.clear()
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

    def test_pick_rate_is_not_sample_count_and_ties_keep_source_order(self):
        self.browser.set_result([
            {'compId':'a','name':'A','sampleCount':999,'avgPlacement':4,'pickRate':1},
            {'compId':'b','name':'B','sampleCount':51,'avgPlacement':5,'pickRate':2},
            {'compId':'c','name':'C','sampleCount':1000,'avgPlacement':3,'pickRate':2},
            {'compId':'d','name':'D','sampleCount':2000,'avgPlacement':2},
        ],'18.2a')
        self.assertEqual(self.ids(),['d','c','a','b'])
        self.browser.pick_sort.click()
        self.assertEqual(self.ids(),['b','c','a','d'])
        self.assertFalse(self.browser.avg_sort.isChecked())
        self.assertEqual(self.browser.cards[-1].findChild(QLabel,'compPickRate').text(),'—')

    def test_lower_minimum_uses_current_condition_and_never_changes_pin(self):
        requests=[];self.browser.queryRequested.connect(lambda *args:requests.append(args))
        self.browser.set_pinned('120')
        self.browser.set_result(copy.deepcopy(self.fixture['comps']),'18.2a')
        self.browser.sample.setCurrentIndex(self.browser.sample.findData(10))
        self.assertEqual(self.browser.min_sample,10)
        self.assertEqual(len(requests),1)
        self.assertEqual(requests[0][0:1],('hex',))
        self.assertEqual(requests[0][1]['id'],'20778')
        self.assertEqual(self.browser.pinned,'120')
        self.assertTrue(all(row['sampleCount']>=10 for row in self.browser.rows if str(row['compId']) in self.ids()))
        self.browser.set_min_sample(50)
        self.assertEqual(self.ids(),['120','100'])

    def test_unified_search_plain_enter_does_not_guess_entity(self):
        requests=[];self.browser.queryRequested.connect(lambda *args:requests.append(args))
        self.browser.clear_filter();requests.clear()
        self.browser.set_result(copy.deepcopy(self.fixture['comps']),'18.2a')
        self.browser.show();self.qt.processEvents()
        self.assertEqual(len(self.browser.findChildren(QLineEdit)),1)
        self.browser.search.setFocus();self.browser.search.setText('黑暗仪式')
        self.browser.completer.setCompletionPrefix('黑暗仪式');self.browser.completer.complete()
        self.qt.processEvents();QTest.keyClick(self.browser.search,Qt.Key.Key_Return);self.qt.processEvents()
        self.assertIsNone(self.browser.scope)
        self.assertEqual(requests,[])

    def test_unified_search_explicit_suggestion_preserves_entity_identity(self):
        requests=[];self.browser.queryRequested.connect(lambda *args:requests.append(args))
        hero_a={'id':'15461','name':'拉克丝','price':5,'heroType':0,'skillName':'黑荆棘'}
        hero_b={'id':'15462','name':'拉克丝','price':5,'heroType':0,'skillName':'灵魂莲华'}
        self.browser.set_catalog({'hero':[hero_a,hero_b]})
        labels=[self.browser.suggestions.item(i).text() for i in range(self.browser.suggestions.rowCount())]
        choices=[i for i,label in enumerate(labels) if '灵魂莲华' in label]
        self.assertEqual(len(choices),1,labels)
        self.browser.choose_suggestion(self.browser.suggestions.index(choices[0],0))
        self.assertEqual(self.browser.scope[0],'hero')
        self.assertEqual(self.browser.scope[1]['id'],'5462')
        self.assertTrue(self.browser.search.text()=='')
        self.assertEqual(len(requests),1)
        self.assertFalse(self.browser.input_bar.confirm.isHidden())

    def test_real_completion_mouse_click_cannot_refill_as_local_filter(self):
        self.browser.clear_filter();self.browser.set_result(copy.deepcopy(self.fixture['comps']),'18.2a')
        self.browser.show();self.qt.processEvents();self.browser.search.setFocus()
        self.browser.search.setText('黑暗仪式');self.browser.completer.setCompletionPrefix('黑暗仪式')
        self.browser.completer.complete();self.qt.processEvents()
        popup=self.browser.completer.popup();model=self.browser.completer.completionModel()
        index=next(model.index(i,0) for i in range(model.rowCount()) if model.index(i,0).data(Qt.ItemDataRole.UserRole)[0]=='hex')
        QTest.mouseClick(popup.viewport(),Qt.MouseButton.LeftButton,pos=popup.visualRect(index).center());self.qt.processEvents()
        self.assertEqual(self.browser.scope[1]['id'],'20778')
        self.assertEqual(self.browser.search.text(),'')
        self.assertEqual(self.ids(),['120','100'])

    def test_real_completion_arrow_enter_selects_but_next_plain_enter_does_not(self):
        self.browser.clear_filter();self.browser.show();self.qt.processEvents();self.browser.search.setFocus()
        self.browser.search.setText('黑暗仪式');self.browser.completer.setCompletionPrefix('黑暗仪式')
        self.browser.completer.complete();self.qt.processEvents()
        # A real popup owns the native keyboard grab while QLineEdit remains
        # focusWidget; send to that recipient, not directly to the line edit.
        popup=self.browser.completer.popup()
        QTest.keyClick(popup,Qt.Key.Key_Down);QTest.keyClick(popup,Qt.Key.Key_Return);self.qt.processEvents()
        self.assertEqual(self.browser.scope[1]['id'],'20778')
        self.assertEqual(self.browser.search.text(),'')
        before=self.browser.input_revision
        self.browser.search.setText('黑暗仪式');self.browser.completer.setCompletionPrefix('黑暗仪式')
        self.browser.completer.complete();self.qt.processEvents()
        QTest.keyClick(self.browser.completer.popup(),Qt.Key.Key_Return);self.qt.processEvents()
        self.assertEqual(self.browser.input_revision,before)

    def test_search_suggestions_cannot_bypass_current_sample_threshold(self):
        self.browser.set_result(copy.deepcopy(self.fixture['comps']),'18.2a')
        ids=[self.browser.suggestions.item(i).data(Qt.ItemDataRole.UserRole)[1]
             for i in range(self.browser.suggestions.rowCount())
             if self.browser.suggestions.item(i).data(Qt.ItemDataRole.UserRole)[0]=='comp']
        self.assertEqual(set(ids),{'120','100'})

    def test_actual_typing_opens_popup_and_escape_keeps_local_text(self):
        self.browser.clear_filter()
        self.browser.set_catalog({'hex':[{'id':'20778','name':'Dark Ritual','level':2}]})
        self.browser.show();self.qt.processEvents();self.browser.search.setFocus()
        requests=[];self.browser.queryRequested.connect(lambda *args:requests.append(args))
        QTest.keyClicks(self.browser.search,'D');self.qt.processEvents()
        popup=self.browser.completer.popup();self.assertTrue(popup.isVisible())
        QTest.keyClicks(popup,'ark Ritual');self.qt.processEvents()
        self.assertEqual(self.browser.search.text(),'Dark Ritual')
        QTest.keyClick(popup,Qt.Key.Key_Down);QTest.keyClick(popup,Qt.Key.Key_Escape);self.qt.processEvents()
        self.assertEqual(self.browser.search.text(),'Dark Ritual')
        self.assertIsNone(self.browser.scope);self.assertEqual(requests,[])

    def test_error_has_local_retry_and_no_removed_controls(self):
        self.browser.set_error();requests=[]
        self.browser.queryRequested.connect(lambda *args:requests.append(args))
        self.assertFalse(self.browser.retry_button.isHidden())
        self.browser.retry_button.click();self.assertEqual(len(requests),1)
        self.browser.set_result(copy.deepcopy(self.fixture['comps']),'18.2a')
        self.assertTrue(self.browser.retry_button.isHidden())
        for removed in ('refresh','only_favs','manual_toggle','entity','kind'):
            self.assertFalse(hasattr(self.browser,removed),removed)


if __name__ == '__main__':
    unittest.main()
