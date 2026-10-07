"""Synthetic races through the actual screen callbacks and adapter.

The dispatcher holds completions to deterministically reverse them. Data
transforms, widgets, errors and cache logic are never mocked.
"""
from contextlib import ExitStack, closing
from pathlib import Path
import json
import sqlite3
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import httpx
from PIL import Image
from PySide6.QtWidgets import QLabel
from app import QApplication, Companion
from display_audit import ReplayDataJ, plain, table_rows
from item_overlay import ItemOverlay


class DisplayLifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.qt=QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.stack=ExitStack();self.pending=[];self.calls=[];self.failure=None
        for module in ['app','dataj','comp_browser']:
            self.stack.enter_context(patch(module+'.STATE_DIR',Path(self.tmp.name)))
        self.p=Companion(offline=True,offline_catalog={'hex':[],'hero':[],'trait':[],
            'equip':[{'id':'2004','name':'朔极之矛','type':'成型装备'}]})
        self.p.timer.stop();self.p.binding=SimpleNamespace(hwnd=7)
        self.stack.enter_context(patch.object(self.p,'panel_open',return_value=False))
        self.stack.enter_context(patch('app.win.foreground_root',return_value=7))
        self.stack.enter_context(patch.object(ItemOverlay,'place',lambda *a:None))
        self.stack.enter_context(patch.object(self.p,'submit',lambda pool,fn,done,failed=lambda _:None:self.pending.append((fn,done,failed))))
        self.set_version('18.2a')

    def tearDown(self):
        self.p.shutdown();self.p.deleteLater();self.qt.processEvents();self.stack.close();self.tmp.cleanup()

    def set_version(self,version):
        self.p.invalidate();self.p.clear_equipment();self.p.session.patch=version
        self.p.adapter=ReplayDataJ(patch=version,db=Path(self.tmp.name)/'cache.db',transport=httpx.MockTransport(self.response))

    def response(self,r):
        self.calls.append(r);path=r.url.path.removeprefix('/api/web')
        if self.failure and self.failure[0] in path:
            if self.failure[1]=='network':raise httpx.ConnectError('offline',request=r)
            if self.failure[1]=='schema':return httpx.Response(200,json={'success':True,'code':200,'data':{}})
            return httpx.Response(429)
        body=json.loads(r.content) if r.method=='POST' else None
        version=body['version'] if body else r.url.params.get('gameVersion')
        avg=3.25 if version=='18.2a' else 6.25
        comp=path.split('/')[2] if path.startswith('/comp/') and not path.endswith('/rank') else None
        if '/hex' in path:
            data=[{'hexId':'1023','roundStats':[{'round':i,'roundLabel':stage,'avgPlacement':avg+i*.1-(.5 if comp else 0),'sampleCount':51+i} for i,stage in enumerate(['2-1','3-2','4-2'])]}]
            if comp:data={'compId':comp,'hexes':data}
        elif path.endswith('/hero-equips'):
            data={'compId':comp,'heroId':r.url.params['heroId'],'heroEquips':[{'equips':[{'id':2004,'name':'朔极之矛'}],'avgPlacement':avg,'sampleCount':51}],'hero3Equips':[]}
        elif path.endswith('/heroes') or path.endswith('/equip-heroes'):
            data=[{'heroId':'4503','heroName':'阿木木','avgPlacement':avg,'sampleCount':51}]
            if comp:data={'compId':comp,'equipId':r.url.params['equipId'],'heroes':data}
        elif path.endswith('/equips') or path=='/stats/equip':
            data=[{'equipId':2004,'avgPlacement':avg-(.5 if comp else 0),'sampleCount':51}]
            if comp:data={'compId':comp,'equips':data}
        elif path.endswith('/rank') or body:
            data=[{'compId':'112','name':'测试阵容','avgPlacement':avg,'sampleCount':51,'top4Rate':50,'topRate':10}]
            if body:data={'comps':data}
        elif path=='/gamedata':data={'hex':[],'hero':[],'equip':[],'trait':[]}
        else:data={'compId':comp,'name':'测试阵容'+str(comp),'heroes':[],'gameCode':'【阵容码】'+str(comp)}
        return httpx.Response(200,json={'success':True,'code':200,'data':data})

    def complete(self,index=0):
        fn,done,failed=self.pending.pop(index)
        try:value=fn()
        except Exception as exc:failed(str(exc));return
        done(value)

    def flush(self):
        budget=30
        while self.pending:
            self.complete();budget-=1
            self.assertGreater(budget,0)

    def hex(self,stage='2-1',live=False):
        self.p.stage.blockSignals(True);self.p.stage.setCurrentText(stage);self.p.stage.blockSignals(False)
        self.p.query_stats(['1023',None,None],['应急护甲 I','未确认','未确认'],live)

    def test_manual_same_choice_retry_recovers_failed_comp_scope(self):
        p=self.p;p.session.set_target('112');self.failure=('/comp/','network')
        p.stage.blockSignals(True);p.stage.setCurrentText('2-1');p.stage.blockSignals(False)
        p.last_observation={'cards':[{'resolution':{'id':'1023'}}]*3}
        with patch.object(p,'display_overlays'),patch('app.win.same_target',return_value=True),patch('app.unchanged',return_value=True):
            p.query_stats(['1023']*3,['应急护甲 I']*3,True);self.flush()
            self.assertTrue(p.stats_payload['retryable'])
            self.assertEqual(p.stats_payload['rows'][0][2],'阵容数据暂不可用')
            global_text=p.stats_payload['rows'][0][1]
            self.failure=None;p.once_active=True;p.once_ocr_pending=True
            with patch.object(p,'hide_overlays') as hide,patch.object(p,'analyze') as ocr:
                p.accept_frame((Image.new('RGB',(1280,720)),p.binding),False,(([],None),None),time.monotonic())
            self.assertFalse(hide.called);self.assertFalse(ocr.called)
            self.assertEqual(p.stats_payload['rows'][0][1],global_text)
            self.flush()
            self.assertFalse(p.stats_payload['retryable'])
            self.assertTrue(p.stats_payload['rows'][0][2].startswith('2.75 · '))

    def hero(self):
        self.p.session.set_target('112');self.p.heroes.blockSignals(True);self.p.heroes.clear()
        self.p.heroes.addItem('阿木木','4503');self.p.heroes.blockSignals(False);self.p.query_equipment()

    def item(self):
        c=self.p.items;c.reset();c.active=True;c.last_seen=time.monotonic()
        self.p.comp_detail={'heroes':[{'heroId':'4503'}]}
        c.observation={'image_size':[1000,1000],'cards':[{'box':[[i*200,500],[i*200+180,500],[i*200+180,900],[i*200,900]]} for i in range(2)]}
        c.rows=[{'id':'2004','name':'朔极之矛','global':{'status':'pending'},'comp':{'status':'pending' if self.p.session.target else 'unpinned'},'holders':[],'holder_status':'pending'} for _ in range(2)]
        c.start_queries()

    def test_all_screens_version_a_b_a_and_cache(self):
        for version,mean in [('18.2a','3.25'),('18.2','6.25'),('18.2a','3.25')]:
            self.set_version(version);self.p.load_comps();self.flush()
            metrics=self.p.browser.cards[0].findChildren(QLabel,'compAverage')
            self.assertEqual(metrics[0].text(),mean)
            self.p.session.set_target(None);self.hex();self.flush();self.assertTrue(self.p.choice_table.item(0,1).text().startswith(mean))
            self.hero();self.flush();self.assertEqual(table_rows(self.p.equip_table),[['朔极之矛',mean,'51']])
            self.item();self.flush();self.assertEqual(plain(self.p.items.overlays[0].global_line.text()),f'全局 {mean} 51局')
        keys=[(r.method,str(r.url),r.content) for r in self.calls]
        self.assertEqual(len(keys),len(set(keys)),'returning to A must reuse only matching fresh cache')

    def test_late_explorer_and_hero_responses_cannot_restore_old_version(self):
        self.p.load_comps();self.hero()
        self.set_version('18.2');self.p.load_comps();self.hero()
        self.complete(2);self.complete(2);self.flush()
        self.assertEqual(self.p.browser.cards[0].findChild(QLabel,'compAverage').text(),'6.25')
        self.assertEqual(table_rows(self.p.equip_table),[['朔极之矛','6.25','51']])

    def test_hex_stage_choice_target_and_new_game_discard_old_callbacks(self):
        self.hex('2-1');self.hex('4-2');self.complete(1);self.complete()
        self.assertEqual(self.p.choice_table.item(0,1).text(),'3.45 · 53局')
        self.hex();self.p.query_stats([None,None,None],['A','B','C'],False);self.complete(1);self.complete()
        self.assertEqual(self.p.choice_table.item(0,0).text(),'A')
        self.hex();self.p.session.set_target('120');self.p.invalidate();self.flush()
        self.assertEqual(self.p.choice_table.rowCount(),0)
        self.hex();self.hero();self.item();self.p.new_game();self.flush()
        self.assertEqual(self.p.choice_table.rowCount(),0);self.assertEqual(self.p.equip_table.rowCount(),0)
        self.assertFalse(self.p.items.active);self.assertIsNone(self.p.session.target)

    def test_late_comp_detail_does_not_replace_pinned_comp(self):
        self.p.comp_url.setText('https://www.dataj.cc/comp/112');self.p.pin_comp()
        self.p.comp_url.setText('https://www.dataj.cc/comp/120');self.p.pin_comp()
        self.complete(1);self.complete()
        self.assertEqual(self.p.comp_detail['compId'],'120')
        self.assertEqual(self.p.comp_detail['gameCode'],'【阵容码】120')

    def test_pinned_guide_never_returns_to_choose_comp_prompt(self):
        p=self.p
        for version in ['18.2a','18.2']:
            with self.subTest(version=version):
                p.unpin();self.set_version(version);p.versions_loaded(['18.2a','18.2'])
                # Exercise the online guide branch, stubbing only browser I/O.
                with patch.object(p.web,'setUrl'),patch.object(p,'offline',False):
                    p.select_comp('112');self.flush()
                self.assertEqual(p.session.target,'112')
                self.assertIn('已固定',p.target_label.text())
                self.assertTrue(p.copy_button.isEnabled())
                self.assertTrue(p.guide_empty.isHidden(),'a pinned comp must not show the choose-comp prompt')

    def test_historical_guide_opt_in_preserves_statistics_and_unpin_clears_it(self):
        p=self.p;self.set_version('18.2');p.versions_loaded(['18.2a','18.2'])
        with patch.object(p.web,'setUrl') as navigate,patch.object(p,'offline',False):
            p.select_comp('112');self.flush()
            self.assertEqual([args[0][0].toString() for args in navigate.call_args_list],['about:blank'])
            self.assertFalse(p.guide_version.isHidden());self.assertTrue(p.web.isHidden())
            self.assertIn('测试阵容112',p.guide_version_title.text())
            p.guide_latest.click()
            self.assertEqual(navigate.call_args[0][0].toString(),'https://www.dataj.cc/comp/112')
            self.assertTrue(p.guide_version.isHidden());self.assertFalse(p.web.isHidden())
            self.assertFalse(p.guide_notice.isHidden(),'Historical statistics and latest guide need a visible version label')
            self.assertIn('原站攻略：18.2a',p.guide_notice.text())
            self.assertIn('统计：18.2',p.guide_notice.text())
            self.assertEqual((p.adapter.patch,p.session.patch,p.session.target),('18.2','18.2','112'))
            with patch('app.QApplication.clipboard') as clipboard:
                p.copy_code();clipboard.return_value.setText.assert_called_once_with('【阵容码】112')
            p.unpin()
            self.assertTrue(p.guide_version.isHidden());self.assertTrue(p.web.isHidden())
            self.assertFalse(p.guide_empty.isHidden());self.assertIsNone(p.guide_requested_url)
            self.assertFalse(p.copy_button.isEnabled())

    def test_explicit_guide_retry_reloads_same_url_but_version_refresh_does_not(self):
        from PySide6.QtCore import QUrl
        p=self.p;p.versions_loaded(['18.2a','18.2'])
        url='https://www.dataj.cc/comp/112'
        # Qt retains the requested URL after loadFinished(False) or stop().
        with patch.object(p.web,'url',return_value=QUrl(url)),patch.object(p.web,'setUrl') as navigate,patch.object(p,'offline',False):
            p.select_comp('112');self.flush();navigate.reset_mock()
            p.comp_url.setText(url);p.browse_comp()
            navigate.assert_called_once_with(QUrl(url));navigate.reset_mock()
            p.versions_loaded(['18.2a','18.2'])
            navigate.assert_not_called()
            p.select_comp('112')
            navigate.assert_called_once_with(QUrl(url));navigate.reset_mock()
            p.versions_loaded(['18.3','18.2a'])
            self.assertTrue(p.web.isHidden())
            p.guide_latest.click()
            navigate.assert_called_once_with(QUrl(url));navigate.reset_mock()
            p.versions_loaded(['18.3','18.2a'])
            navigate.assert_not_called()

    def test_delayed_versions_refresh_guide_without_changing_active_tab(self):
        p=self.p
        p.select_comp('112');self.flush()
        self.assertTrue(p.guide_empty.isHidden());self.assertFalse(p.guide_version.isHidden())
        p.tabs.setCurrentIndex(3)
        p.versions_loaded(['18.2a','18.2'])
        self.assertTrue(p.guide_version.isHidden());self.assertFalse(p.web.isHidden())
        self.assertEqual(p.tabs.currentIndex(),3)
        p.versions_loaded(['18.3','18.2a','18.2'])
        self.assertFalse(p.guide_version.isHidden());self.assertTrue(p.web.isHidden())
        self.assertTrue(p.guide_empty.isHidden());self.assertEqual(p.tabs.currentIndex(),3)

    def test_switch_comp_failure_and_retry_do_not_reuse_old_guide_consent(self):
        p=self.p;p.versions_loaded(['18.3','18.2a'])
        p.select_comp('112');self.flush();p.guide_latest.click()
        self.failure=('/comp/120','network');p.select_comp('120')
        self.assertTrue(p.guide_version.isHidden());self.assertTrue(p.web.isHidden())
        self.assertTrue(p.guide_empty.isHidden());self.assertFalse(p.copy_button.isEnabled())
        self.flush();self.assertFalse(p.guide_retry.isHidden());self.assertIsNone(p.comp_detail)
        self.failure=None;p.guide_retry.click();self.flush()
        self.assertIn('测试阵容120',p.guide_version_title.text())
        self.assertTrue(p.guide_empty.isHidden());self.assertFalse(p.guide_version.isHidden())
        self.assertTrue(p.web.isHidden());self.assertFalse(p.guide_allow_latest)
        self.assertTrue(p.guide_retry.isHidden());self.assertTrue(p.copy_button.isEnabled())

    def test_item_reset_version_and_focus_drop_late_results(self):
        self.item();self.set_version('18.2');self.item();self.complete(1);self.flush()
        self.assertIn('6.25',plain(self.p.items.overlays[0].global_line.text()))
        self.item();self.p.invalidate();self.flush();self.assertFalse(self.p.items.active)
        self.hex(live=True)
        with patch('app.win.foreground_root',return_value=99):self.flush()
        self.assertEqual(self.p.choice_table.rowCount(),0)

    def test_partial_hex_failure_preserves_global_without_global_as_comp(self):
        self.p.session.set_target('112');self.failure=('/comp/112/hexes',429);self.hex();self.flush()
        self.assertEqual(self.p.choice_table.item(0,1).text(),'3.25 · 51局')
        self.assertEqual(self.p.choice_table.item(0,2).text(),'阵容数据暂不可用')

    def test_each_display_handles_network_429_and_invalid_response(self):
        for mode in ['network',429,'schema']:
            for domain,path,trigger in [('explorer','/comp/rank',self.p.load_comps),('hex','/stats/hex',self.hex),
                 ('hero','/hero-equips',self.hero),('items','/stats/equip',self.item)]:
                with self.subTest(domain=domain,mode=mode):
                    self.p.invalidate();self.p.clear_equipment();self.p.items.cache.clear()
                    self.failure=(path,mode);trigger();self.flush()
                    if domain=='explorer':self.assertEqual(self.p.browser.cards,[])
                    elif domain=='hex':self.assertEqual(self.p.choice_table.rowCount(),0)
                    elif domain=='hero':self.assertEqual(self.p.equip_table.rowCount(),0);self.assertIn('失败',self.p.equip_note.text())
                    else:self.assertEqual(plain(self.p.items.overlays[0].global_line.text()),'全局 查询失败')

    def test_expired_cache_is_not_used_for_any_endpoint_on_failure(self):
        a=self.p.adapter
        calls=[lambda:a.comps(),lambda:a.explore('hex',{'id':'1023','name':'应急护甲 I'}),lambda:a.hexes(),lambda:a.hexes('112'),
               lambda:a.equipment('112','4503'),lambda:a.item_stats(),lambda:a.item_stats('112'),
               lambda:a.item_holders('2004'),lambda:a.item_holders('2004','112')]
        for fn in calls:fn()
        with closing(sqlite3.connect(a.db,isolation_level=None)) as conn:conn.execute('UPDATE cache SET fetched=?',(time.time()-901,))
        self.failure=('',429)
        from dataj import SourceError
        for fn in calls:
            with self.assertRaises(SourceError):fn()

    def test_real_version_and_stage_ui_events_clear_stale_displays(self):
        p=self.p;self.hex();self.flush();self.hero();self.flush()
        p.patch.addItem('18.2');p.patch.setCurrentText('18.2')
        factory=lambda **kw:ReplayDataJ(db=Path(self.tmp.name)/'cache.db',transport=httpx.MockTransport(self.response),**kw)
        # Substitute only the adapter factory so the actual UI event stays offline.
        # Avoid native OCR preparation; this test concerns catalog reload/display.
        with patch('app.DataJ',side_effect=factory) as cls,patch.object(p.vision,'prepare'):
            cls.validate_comps=ReplayDataJ.validate_comps
            p.patch.activated.emit(p.patch.currentIndex());self.flush()
        self.assertEqual(p.adapter.patch,'18.2');self.assertEqual(p.session.patch,'18.2')
        # Changing statistics patch retains the game plan, while old rows clear.
        self.assertEqual(p.session.target,'112');self.assertEqual(p.equip_table.rowCount(),0)
        self.assertEqual(p.result_cards[0].average_label.text(),'—')
        self.hex();self.flush();self.assertEqual(p.result_cards[0].average_label.text(),'6.25')
        p.stage.setCurrentText('4-2')
        self.assertEqual(p.result_cards[0].average_label.text(),'—');self.assertIsNone(p.stats_payload)
        self.hex('4-2');self.flush();self.assertEqual(p.result_cards[0].average_label.text(),'6.45')


if __name__=='__main__':unittest.main()
