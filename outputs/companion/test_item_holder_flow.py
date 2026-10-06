"""Holder recovery and first-result scheduling through the real Qt item display.

Only native capture/OCR and HTTP transport are controlled. Statistics retain
their source scope; synthetic portrait pixels verify identity, not image CDN IO.
"""
from copy import deepcopy
from pathlib import Path
import time
import unittest
from unittest.mock import patch

import httpx
from PIL import Image
from PySide6.QtGui import QColor, QPixmap
from app import QApplication
from display_audit import ReplayDataJ, plain
import test_runtime_stability as fixtures


class ItemHolderFlow(unittest.TestCase):
    tearDown = fixtures.RuntimeStability.tearDown

    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        fixtures.RuntimeStability.setUp(self)
        self.clock = 100.0
        self.stack.enter_context(patch('item_controller.time.monotonic',side_effect=lambda:self.clock))
        self.stack.enter_context(patch('item_controller.win.user.SetWindowPos',return_value=True))
        self.calls = []
        self.failures = set()
        self.empty_holders = set()
        self.missing_comp = set()
        self.p.adapter = ReplayDataJ(patch='18.3',db=Path(self.tmp.name)/'items.sqlite',
            transport=httpx.MockTransport(self.response))
        self.ids = ['2027','6002','2070']
        self.p.catalog['equip'] = [
            {'id':'2027','name':'棘刺背心','type':'成型装备'},
            {'id':'6002','name':'无尽之力','type':'神器装备'},
            {'id':'2070','name':'光明版棘刺背心','type':'光明武器'}]
        self.p.catalog['hero'] = [
            {'id':'14503','name':'阿木木','picture':'https://img.dataj.cc/test/amumu.png'},
            {'id':'15450','name':'茂凯','picture':'https://img.dataj.cc/test/maokai.png'}]
        for row,color in zip(self.p.catalog['hero'],['#287941','#f0b020']):
            pix = QPixmap(32,32);pix.fill(QColor(color))
            self.p.browser.portraits.images[row['picture']] = pix
        self.frame = Image.new('RGB',(1920,1080))
        self.boxes = [(400+i*360,750,600+i*360,950) for i in range(3)]
        self.signature = object()
        self.observation = {'scene':'item_candidates','image_size':self.frame.size,'cards':[]}
        for slot,(box,row) in enumerate(zip(self.boxes,self.p.catalog['equip'])):
            left,top,right,bottom = box
            self.observation['cards'].append({'slot':slot,
                'box':[[left,top],[right,top],[right,bottom],[left,bottom]],
                'resolution':{'status':'resolved',**row,'candidates':[dict(row)]}})
        self.stack.enter_context(patch('item_controller.analyze_items',return_value=deepcopy(self.observation)))
        self.stack.enter_context(patch('item_controller.same_item_text',side_effect=lambda a,b:a is b))

    def response(self,request):
        path = request.url.path.removeprefix('/api/web')
        self.calls.append(path)
        if path in self.failures:
            raise httpx.ConnectError('controlled transport failure',request=request)
        if path == '/stats/equip':
            data = [{'equipId':id_,'avgPlacement':4.1,'sampleCount':101} for id_ in self.ids]
        elif path.endswith('/equips'):
            data = {'compId':'112','equips':[{'equipId':id_,'avgPlacement':3.9,'sampleCount':80}
                for id_ in self.ids if id_ not in self.missing_comp]}
        elif path.endswith('/heroes') or path.endswith('/equip-heroes'):
            id_ = request.url.params.get('equipId') if path.endswith('/equip-heroes') else path.split('/')[-2]
            data = [] if id_ in self.empty_holders else [
                {'heroId':'4503','heroName':'阿木木','avgPlacement':3.4,'sampleCount':150},
                {'heroId':'5450','heroName':'茂凯','avgPlacement':3.2,'sampleCount':49}]
            if path.endswith('/equip-heroes'):
                data = {'compId':'112','equipId':id_,'heroes':data}
        else:
            self.assertEqual(path,'/explorer/query')
            data = {'comps':[{'compId':'112','name':'测试阵容','avgPlacement':3.8,'sampleCount':60}]}
        return httpx.Response(200,json={'code':200,'success':True,'data':data})

    def complete(self):
        work,done,failed = self.jobs.pop(0)
        try:result = work()
        except Exception as exc:
            if failed:failed(str(exc))
            else:raise
        else:done(result)
        self.qt.processEvents()

    def flush(self):
        budget = 30
        while self.jobs:
            self.complete();budget -= 1
            self.assertGreater(budget,0)

    def ingest(self,force=False):
        return self.p.items.ingest(self.frame,self.binding,force=force,
            prepared=(self.boxes,self.signature),frame_time=self.clock)

    def seed(self,pinned=False):
        if pinned:
            self.p.session.set_target('112')
            self.p.comp_detail = {'compId':'112','heroes':[{'heroId':'4503','heroName':'阿木木'}]}
        self.ingest();self.flush()

    def test_completed_artifact_radiant_render_matching_hero_and_portrait(self):
        self.seed()
        for index,id_ in enumerate(self.ids):
            with self.subTest(item=id_):
                row = self.p.items.rows[index]
                overlay = self.p.items.overlays[index]
                self.assertEqual(row['holders'],[{'id':'4503','name':'阿木木','average':3.4,'samples':150}])
                self.assertIn('阿木木',plain(overlay.holder_lines[0][1].text()))
                self.assertIn('3.40',plain(overlay.holder_lines[0][1].text()))
                self.assertFalse(overlay.holder_lines[0][0].pixmap().isNull())
                self.assertFalse(overlay.holder_lines[0][0].isHidden())
                self.assertNotIn('茂凯',plain(overlay.holder_lines[0][1].text()))

    def test_pinned_holders_remain_in_comp_scope(self):
        self.seed(pinned=True)
        self.assertIn('/comp/112/equip-heroes',self.calls)
        self.assertFalse(any(path.startswith('/stats/equip/') for path in self.calls))
        self.assertTrue(all(row['holders'][0]['id']=='4503' for row in self.p.items.rows))

    def test_each_category_missing_or_failed_holder_has_visible_status(self):
        self.empty_holders.update(self.ids[:2])
        self.failures.add('/stats/equip/2070/heroes')
        self.seed()
        for index,status,text in [(0,'missing','暂无足够样本'),(1,'missing','暂无足够样本'),(2,'error','持有者暂不可用')]:
            with self.subTest(item=self.ids[index]):
                self.assertEqual(self.p.items.rows[index]['holder_status'],status)
                self.assertEqual(self.p.items.overlays[index].holder_lines[0][1].text(),text)
                self.assertTrue(self.p.items.overlays[index].holder_lines[0][0].pixmap().isNull())

    def test_manual_same_offer_retries_failed_holder_without_ocr_or_blank(self):
        self.failures.add('/stats/equip/2027/heroes');self.seed()
        self.assertEqual(self.p.items.rows[0]['holder_status'],'error')
        self.failures.clear();self.clock += .7
        generation = self.p.items.generation
        with patch('item_controller.analyze_items') as ocr:
            self.ingest(force=True)
            self.assertEqual(len(self.jobs),1,'A manual refresh silently leaves failed holders permanently empty')
            self.assertTrue(self.p.items.overlays[0].isVisible())
            self.assertEqual(self.p.items.rows[0]['global']['status'],'ok')
            self.flush();self.assertFalse(ocr.called)
        self.assertEqual(self.p.items.generation,generation)
        self.assertEqual(self.p.items.rows[0]['holder_status'],'ok')
        self.assertEqual(self.calls.count('/stats/equip/2027/heroes'),2)
        self.assertEqual(self.calls.count('/stats/equip/6002/heroes'),1)
        self.assertFalse(self.p.items.overlays[0].holder_lines[0][0].pixmap().isNull())

    def test_automatic_same_offer_does_not_retry_errors_or_empty_results(self):
        self.failures.add('/stats/equip/2027/heroes');self.empty_holders.add('6002');self.seed()
        before = list(self.calls)
        for _ in range(8):
            self.clock += .6;self.ingest()
        self.assertEqual(self.jobs,[])
        self.assertEqual(self.calls,before)

    def test_manual_global_failure_retry_keeps_already_loaded_hero(self):
        self.failures.add('/stats/equip');self.seed()
        overlay=self.p.items.overlays[0]
        portrait_key=overlay.holder_lines[0][0].pixmap().cacheKey()
        self.assertEqual(self.p.items.rows[0]['global']['status'],'error')
        self.failures.clear();self.clock += .7
        with patch('item_controller.analyze_items') as ocr:
            self.ingest(force=True)
            self.assertEqual(len(self.jobs),1,'A same-offer manual request cannot repair the failed global table')
            self.assertEqual(overlay.holder_lines[0][0].pixmap().cacheKey(),portrait_key)
            self.flush();self.assertFalse(ocr.called)
        self.assertEqual(self.p.items.rows[0]['global']['status'],'ok')
        self.assertEqual(self.calls.count('/stats/equip/2027/heroes'),1)
        self.assertIn('阿木木',plain(overlay.holder_lines[0][1].text()))

    def test_manual_retry_respects_source_backoff_then_recovers(self):
        self.failures.add('/stats/equip/2027/heroes');self.seed();self.failures.clear()
        self.p.adapter.next_request = self.clock+60
        self.clock += .7;self.ingest(force=True)
        self.assertEqual(self.jobs,[],'Manual retry must not defeat the adapter network cooldown')
        self.clock += 60;self.ingest(force=True)
        self.assertEqual(len(self.jobs),1,'The same offer cannot recover even after source cooldown expires')
        self.flush();self.assertEqual(self.p.items.rows[0]['holder_status'],'ok')

    def test_duplicate_manual_retry_does_not_duplicate_pending_network(self):
        self.failures.add('/stats/equip/2027/heroes');self.seed();self.failures.clear()
        self.clock += .7;self.ingest(force=True)
        self.assertEqual(len(self.jobs),1)
        self.ingest(force=True);self.ingest(force=True)
        self.assertEqual(len(self.jobs),1)
        self.flush();self.assertEqual(self.calls.count('/stats/equip/2027/heroes'),2)

    def test_missing_comp_item_fallback_does_not_block_first_hero(self):
        self.missing_comp.update(self.ids)
        self.p.session.set_target('112')
        self.p.comp_detail = {'compId':'112','heroes':[{'heroId':'4503','heroName':'阿木木'}]}
        self.ingest();self.complete()  # OCR
        self.complete();self.complete()  # global and comp tables
        self.complete()  # first detail query, leaving all later queries held
        self.assertEqual(self.p.items.rows[0]['holder_status'],'ok',
            'Every slow comp fallback executes before even the first valid hero is displayed')
        self.assertIn('阿木木',plain(self.p.items.overlays[0].holder_lines[0][1].text()))
        self.assertNotIn('/explorer/query',self.calls)
        self.flush()
        self.assertTrue(all(row['comp']['average']==3.8 for row in self.p.items.rows))


if __name__=='__main__':unittest.main()
