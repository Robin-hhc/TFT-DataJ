"""Malformed source identities fail through the real panel and item queue."""
from copy import deepcopy
from pathlib import Path
import time
import unittest

import httpx
from app import QApplication
from display_audit import ReplayDataJ, plain
import test_display_lifecycle as fixtures


class IdentityFailureDisplay(unittest.TestCase):
    setUp = fixtures.DisplayLifecycle.setUp
    tearDown = fixtures.DisplayLifecycle.tearDown
    set_version = fixtures.DisplayLifecycle.set_version
    complete = fixtures.DisplayLifecycle.complete
    flush = fixtures.DisplayLifecycle.flush

    @classmethod
    def setUpClass(cls):
        cls.qt=QApplication.instance() or QApplication([])

    def response(self,request):
        response=fixtures.DisplayLifecycle.response(self,request)
        payload=response.json()
        path=request.url.path.removeprefix('/api/web')
        if path=='/comp/112':
            payload['data']=deepcopy(self.detail)
        elif path.endswith('/heroes') or path.endswith('/equip-heroes'):
            equip=request.url.params.get('equipId') if path.endswith('/equip-heroes') else path.split('/')[-2]
            rows=payload['data']['heroes'] if isinstance(payload['data'],dict) else payload['data']
            field='heroName' if path.endswith('/equip-heroes') else 'name'
            if field=='name':
                rows[0].pop('heroName')
                rows[0]['name']='阿木木'
            if equip=='2004':rows[0][field]=None
        return httpx.Response(200,json=payload)

    def test_malformed_holder_shows_failure_and_remaining_item_query_completes(self):
        for comp in (None,'112'):
            with self.subTest(comp=comp):
                p=self.p;p.session.set_target(comp)
                p.comp_detail={'heroes':[{'heroId':'4503','heroName':'阿木木'}]} if comp else None
                ctrl=p.items;ctrl.reset();ctrl.active=True;ctrl.last_seen=time.monotonic()
                ctrl.observation={'image_size':[1000,1000],'cards':[
                    {'box':[[i*200,500],[i*200+180,500],[i*200+180,900],[i*200,900]]} for i in range(2)]}
                ctrl.rows=[{'id':identity,'name':name,'global':{'status':'pending'},
                    'comp':{'status':'pending' if comp else 'unpinned'},'holders':[],
                    'holder_status':'pending'} for identity,name in [('2004','朔极之矛'),('2027','棘刺背心')]]
                ctrl.start_queries();self.flush()
                self.assertEqual(plain(ctrl.overlays[0].global_line.text()),'全局 3.25 51局')
                self.assertEqual(ctrl.rows[0]['holder_status'],'error')
                self.assertEqual(ctrl.overlays[0].holder_lines[0][1].text(),'持有者暂不可用')
                self.assertEqual(ctrl.rows[1]['holder_status'],'ok')
                self.assertEqual(plain(ctrl.overlays[1].holder_lines[0][1].text()),'阿木木 3.25 51局')
                endpoint='/comp/112/equip-heroes' if comp else '/stats/equip/2027/heroes'
                self.assertTrue(any(r.url.path.endswith(endpoint) and
                    (not comp or r.url.params['equipId']=='2027') for r in self.calls))

    def test_malformed_comp_hero_shows_load_failure_without_fixed_ui(self):
        for index,hero in enumerate([{'heroId':'4503'},
                {'heroId':'4503','heroName':None},{'heroId':'4503','heroName':''}]):
            with self.subTest(hero=hero):
                self.detail={'compId':'112','name':'测试阵容','heroes':[hero]}
                self.p.adapter=ReplayDataJ(db=Path(self.tmp.name)/f'detail-{index}.db',
                    transport=httpx.MockTransport(self.response))
                self.p.comp_url.setText('https://www.dataj.cc/comp/112')
                self.p.pin_comp();self.flush()
                self.assertIsNone(self.p.comp_detail)
                self.assertIn('加载失败',self.p.target_label.text())
                self.assertNotIn('已固定',self.p.target_label.text())
                self.assertEqual(self.p.heroes.count(),0)
                self.assertFalse(self.p.heroes.signalsBlocked())
                self.assertFalse(self.p.copy_button.isEnabled())
                self.assertFalse(self.p.guide_retry.isHidden())


if __name__=='__main__':unittest.main()
