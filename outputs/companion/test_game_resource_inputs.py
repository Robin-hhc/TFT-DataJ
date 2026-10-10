"""Confirmed history, actual widgets, and final versioned HTTP conditions."""
from contextlib import ExitStack
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
import httpx
from app import QApplication, Companion
from dataj import DataJ


CATALOG={'hex':[{'id':'20778','name':'黑暗仪式','level':2}],
         'equip':[{'id':'41806','name':'地狱火纹章','type':'转职纹章'}],
         'hero':[{'id':'14503','name':'阿木木','heroType':0,'price':1}], 'trait':[]}


class GameResourceInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.qt=QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.stack=ExitStack();self.pending=[];self.calls=[]
        for module in ['app','dataj','comp_browser']:
            self.stack.enter_context(patch(module+'.STATE_DIR',Path(self.tmp.name)))
        db=Path(self.tmp.name)/'cache.db';transport=httpx.MockTransport(self.response)
        class Source(DataJ):
            def __init__(self,patch='18.2a',*,budget=None):super().__init__(patch=patch,db=db,transport=transport,budget=budget)
            def request(self,*args,**kwargs):self.next_request=0;return super().request(*args,**kwargs)
        self.stack.enter_context(patch('app.DataJ',Source))
        self.stack.enter_context(patch.object(Companion,'submit',lambda p,pool,fn,done,failed=lambda _:None,**scheduling:self.pending.append((fn,done,failed))))
        self.p=Companion(offline=True,offline_catalog=CATALOG);self.p.timer.stop()

    def response(self,r):
        self.calls.append(r)
        path=r.url.path
        data={'comps':[]} if r.method=='POST' else {'compId':'112','name':'测试阵容','heroes':[],'gameCode':'【阵容码】112'} if path.endswith('/112') else CATALOG if path.endswith('/gamedata') else []
        return httpx.Response(200,json={'success':True,'code':200,'data':data})

    def flush(self):
        while self.pending:
            fn,done,failed=self.pending.pop(0)
            try:r=fn()
            except Exception as exc:failed(str(exc))
            else:done(r)

    def tearDown(self):
        self.p.shutdown();self.p.deleteLater();self.qt.processEvents();self.stack.close();self.tmp.cleanup()

    def test_search_is_not_selected_until_explicit_confirmation(self):
        p=self.p
        p.browser.set_filter('hex',CATALOG['hex'][0],can_confirm=True);self.flush()
        self.assertEqual(len(p.selected_resources.events),0)
        p.browser.input_bar.confirm.click()
        self.assertEqual([(e.kind,e.entity_id) for e in p.selected_resources.events],[('hex','20778')])
        self.assertEqual(len(p.browser.input_bar.chips),1)
        p.browser.input_bar.chips[0].click();self.flush()
        body=json.loads(self.calls[-1].content)
        self.assertEqual(body['filter']['rules'][0]['targetId'],'20778')
        self.assertEqual(len(body['filter']['rules']),1)

    def test_successful_condition_retry_clears_previous_source_error(self):
        self.flush()
        self.p.status.setText('来源暂时不可用，稍后手动重试')
        self.p.browser.set_filter('equip',CATALOG['equip'][0])
        self.flush()
        self.assertFalse(self.p.browser.failed)
        self.assertEqual(self.p.status.text(),'已按「地狱火纹章」检索阵容。')
        self.assertEqual(self.p.selected_resources.events,())

    def test_late_query_success_does_not_clear_current_query_status(self):
        self.flush()
        self.p.browser.set_filter('equip',CATALOG['equip'][0])
        _,old_done,_=self.pending.pop(0)
        self.p.browser.set_filter('hex',CATALOG['hex'][0])
        self.p.status.setText('当前查询尚未完成')
        old_done({'data':{'comps':[]}})
        self.assertEqual(self.p.status.text(),'当前查询尚未完成')
        self.flush()
        self.assertEqual(self.p.status.text(),'已按「黑暗仪式」检索阵容。')

    def test_patch_change_keeps_pin_resources_and_single_condition_but_clears_old_data(self):
        p=self.p;p.select_comp('112');self.flush()
        p.browser.set_filter('hex',CATALOG['hex'][0],can_confirm=True);self.flush()
        p.confirm_condition()
        session_id=p.session.session_id
        p.patch.addItem('18.3');p.patch.setCurrentText('18.3')
        with patch('app.Vision.prepare'):p.change_patch();self.flush()
        self.assertEqual(p.session.session_id,session_id)
        self.assertEqual(p.session.target,'112')
        self.assertEqual([(e.kind,e.entity_id) for e in p.selected_resources.events],[('hex','20778')])
        self.assertEqual(p.browser.scope[1]['id'],'20778')
        self.assertEqual(p.adapter.patch,'18.3')
        self.assertEqual(p.comp_detail['compId'],'112')
        self.assertTrue(p.copy_button.isEnabled())
        posts=[r for r in self.calls if r.method=='POST']
        self.assertEqual(json.loads(posts[-1].content)['version'],'18.3')
        p.new_game();self.flush()
        self.assertEqual(p.selected_resources.events,())
        self.assertIsNone(p.session.target)
        self.assertIsNone(p.browser.scope)

    def test_search_failure_unknown_and_duplicate_confirm_do_not_add_resources(self):
        p=self.p
        p.browser.set_filter('equip',CATALOG['equip'][0],can_confirm=True)
        p.confirm_condition();p.confirm_condition()
        self.assertEqual(len(p.selected_resources.events),1)
        p.invalidate();p.unpin()
        self.assertEqual(len(p.selected_resources.events),1)
        before=p.browser.scope
        self.assertFalse(p.browser.set_filter('hero',{'id':'123456','name':'阿木木'},can_confirm=True))
        self.assertEqual(p.browser.scope,before)
        self.assertEqual(len(p.selected_resources.events),1)
        p.browser.input_bar.chips[0].click();self.flush()
        body=json.loads(self.calls[-1].content)
        self.assertEqual(body['filter']['rules'][0]['targetId'],'41806')
        self.assertEqual(len(body['filter']['rules']),1)


if __name__=='__main__':unittest.main()
