"""Automatic reports queue disk work without new screenshots or OCR."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from PySide6.QtCore import QThreadPool
from bug_cases import BugCaseStore
from bug_reporting import BugReporter
from core import Session


class BugReportingTests(unittest.TestCase):
    def setUp(self):
        self.record_patch=patch('bug_reporting.record');self.record_patch.start()
        self.tmp=tempfile.TemporaryDirectory();self.directory=Path(self.tmp.name)/'bugs'
        self.queue=[]
        self.binding=SimpleNamespace(hwnd=123,pid=1,process='MuMuNxDevice.exe',rect=(0,0,1280,720))
        self.p=SimpleNamespace(adapter=SimpleNamespace(set_id=18,patch='18.3'),session=Session(patch='18.3'),
            binding=self.binding,catalog={'hex':[{'id':'1625','name':'别再错过'}],'equip':[]},
            jobs=set(),status=SimpleNamespace(setText=Mock()),last_capture=time.monotonic(),
            last_frame=Image.new('RGB',(1280,720),'#193a20'),last_observation=None,
            capture_pending=False,ocr_busy=False,versions_ready=True,
            capture_pool=QThreadPool(),return_to_game=Mock(return_value=True),
            refresh_windows=Mock(),bind_window=Mock(),windows=SimpleNamespace(count=lambda:1))
        self.p.submit=lambda pool,fn,done,failed=None,**scheduling:self.queue.append((pool,fn,done,failed))
        self.r=BugReporter(self.p,store=BugCaseStore(self.directory))
        self.observation={'scene':'choice_candidates','round':'3-2','cards':[
            {'slot':i,'raw_text':name,'resolution':{'status':'resolved','id':str(i),'name':name,'readings':[name]*3}}
            for i,name in enumerate(['甲','乙','别再错过'])]}
        self.observation['cards'][2]['resolution']={'status':'ambiguous','readings':['别再错过']*3,
            'candidates':[{'id':'1625','name':'别再错过'},{'id':'10784','name':'别再错过'}]}

    def tearDown(self):
        self.queue.clear();self.r.shutdown();self.tmp.cleanup();self.record_patch.stop()

    def flush(self):
        while self.queue:
            _,job,done,failed=self.queue.pop(0)
            try:result=job()
            except Exception as exc:
                if failed:failed(str(exc))
                else:raise
            else:done(result)

    def manifests(self):
        return [json.loads(path.read_text(encoding='utf-8')) for path in self.directory.glob('case-*/case.json')]

    def test_unresolved_auto_uses_existing_frame_and_writes_only_on_worker(self):
        with patch('bug_reporting.capture_image') as screenshot,patch.object(Image.Image,'save',autospec=True) as encode:
            self.assertTrue(self.r.observed_hex(self.observation,self.p.last_frame))
            self.assertEqual(len(self.queue),1)
            self.assertIs(self.queue[0][0],self.r.pool)
            screenshot.assert_not_called();encode.assert_not_called()
        self.flush()
        case=self.manifests()[0]
        self.assertEqual(case['reason'],'hex_unresolved')
        self.assertEqual(case['status'],'pending_review')
        self.assertEqual(case['context']['patch'],'18.3')
        self.assertEqual(case['evidence']['catalog'],{'hex':self.p.catalog['hex']})
        self.assertFalse((self.directory/('case-'+case['case_id'])/'expected.json').exists())

    def test_snapshot_is_frozen_without_cloning_game_image(self):
        self.r.observed_hex(self.observation,self.p.last_frame)
        self.p.catalog['hex'][0]['name']='已改变目录'
        self.observation['cards'][0]['raw_text']='新的选项'
        self.flush();case=self.manifests()[0]
        self.assertEqual(case['evidence']['catalog']['hex'][0]['name'],'别再错过')
        self.assertEqual(case['observation']['cards'][0]['raw_text'],'甲')

    def test_single_pending_and_cooldown_prevent_screenshot_backlog(self):
        self.r.observed_hex(self.observation,self.p.last_frame)
        changed=deepcopy(self.observation);changed['cards'][2]['raw_text']='别的未识别项'
        self.assertFalse(self.r.observed_hex(changed,self.p.last_frame))
        self.flush()
        self.assertFalse(self.r.observed_hex(changed,self.p.last_frame))
        self.r.last_request-=16
        self.assertTrue(self.r.observed_hex(changed,self.p.last_frame));self.flush()
        self.assertEqual(len(self.manifests()),2)

    def test_same_case_keeps_first_image_without_resubmission(self):
        self.r.observed_hex(self.observation,self.p.last_frame);self.flush()
        self.r.last_request-=16
        self.assertFalse(self.r.observed_hex(self.observation,Image.new('RGB',(1280,720),'red')))
        self.assertEqual(self.queue,[])

    def test_success_unknown_non_game_and_wrong_size_are_not_automatically_saved(self):
        known=deepcopy(self.observation);known['cards'][2]['resolution']={'status':'resolved','id':'1625'}
        for observation in (known,{'scene':'unknown','cards':[]},{'scene':'choice_unresolved','cards':[]}):
            self.assertFalse(self.r.observed_hex(observation,self.p.last_frame))
        self.p.binding.process='explorer.exe'
        self.assertFalse(self.r.observed_hex(self.observation,self.p.last_frame))
        self.p.binding.process='MuMuNxDevice.exe'
        self.assertFalse(self.r.observed_hex(self.observation,Image.new('RGB',(320,180))))
        self.assertEqual(self.queue,[])

    def test_demo_instance_stays_disabled_and_no_game_capture_runs(self):
        self.r.enabled=False
        with patch('bug_reporting.capture_image') as screenshot:
            self.r.observed_hex(self.observation,self.p.last_frame);self.r.manual_report()
            self.assertEqual(self.queue,[]);screenshot.assert_not_called()

    def test_query_failures_require_fresh_game_frame_and_store_scope(self):
        self.p.last_observation=self.observation
        with patch('bug_reporting.win.foreground_root',return_value=123):
            self.p.last_capture-=2
            self.assertFalse(self.r.hex_statistics('hex_query_failed'))
            self.p.last_capture=time.monotonic()
            self.assertTrue(self.r.hex_statistics('hex_query_failed',evidence={'requested_ids':['1625']}))
        self.flush();case=self.manifests()[0]
        self.assertEqual(case['evidence']['requested_ids'],['1625'])
        self.assertEqual(case['context']['target'],None)

    def test_item_partial_and_data_failure_preserve_domain_and_padded_scope(self):
        observation=deepcopy(self.observation);observation['scene']='item_candidates'
        self.r.observed_items(observation,self.p.last_frame,frame_scope='item_band');self.flush()
        case=self.manifests()[0]
        self.assertEqual(case['context']['domain'],'item')
        self.assertEqual(case['context']['frame_scope'],'item_band')
        self.assertEqual(case['evidence']['catalog'],{'equip':[]})
        self.p.items=SimpleNamespace(observation=observation,last_frame=self.p.last_frame,active=True,
            available=lambda:True,fresh=lambda now:True,frame_scope='full_game')
        self.r.last_request-=16
        self.r.item_statistics('item_query_failed',evidence={'scope':'global'});self.flush()
        failure=next(case for case in self.manifests() if case['reason']=='item_query_failed')
        self.assertEqual(failure['context']['frame_scope'],'full_game')

    def test_fully_unreadable_items_are_saved_but_basic_components_are_excluded(self):
        unknown=deepcopy(self.observation);unknown['scene']='unknown';unknown['reason']='excluded_or_unconfirmed'
        for card in unknown['cards']:card['resolution']={'status':'unrecognized','readings':[]}
        self.assertTrue(self.r.observed_items(unknown,self.p.last_frame,frame_scope='item_band'));self.flush()
        unknown['cards'][0]['resolution']={'status':'excluded','excluded_id':'1001'}
        self.r.last_request-=16
        self.assertFalse(self.r.observed_items(unknown,self.p.last_frame,frame_scope='item_band'))
        self.assertFalse(self.r.observed_items({'scene':'unknown','reason':'item_header_unconfirmed','cards':[]},
                                              self.p.last_frame,frame_scope='item_band'))

    def test_condition_failure_freezes_complete_result_and_all_catalog_domains(self):
        self.p.catalog={'hex':[{'id':'h1','name':'海克斯'}],
                        'equip':[{'id':'e1','name':'装备'}],
                        'hero':[{'id':'c1','name':'英雄'}],
                        'trait':[{'id':'t1','name':'羁绊'}]}
        result={'scene':'unknown','route':'none','status':'unknown','entity':None,
                'candidates':[],'reason':'primary_title_unconfirmed','records_selected':False,
                'image_size':[1280,720],
                'evidence':{'layout':'s18_floating_icon_title','title_rect':[40,50,300,90],
                            'popup_rect':[10,20,330,180],'readings':['不完整标题','另一读数']}}
        expected_result=deepcopy(result);expected_catalog=deepcopy(self.p.catalog)
        with patch('bug_reporting.capture_image') as screenshot,\
             patch('vision.Vision.read_name') as ocr,\
             patch.object(Image.Image,'save',autospec=True) as encode:
            self.assertTrue(self.r.observed_condition(result,self.p.last_frame))
            self.assertEqual(len(self.queue),1)
            self.assertIs(self.queue[0][0],self.r.pool)
            screenshot.assert_not_called();ocr.assert_not_called();encode.assert_not_called()
        for rows in self.p.catalog.values():rows[0]['name']='已改变目录'
        result['reason']='later_frame';result['evidence']['readings'].append('后来的读数')
        self.flush();case=self.manifests()[0]
        self.assertEqual(case['reason'],'condition_unresolved')
        self.assertEqual(case['context']['domain'],'condition')
        self.assertEqual(case['context']['frame_scope'],'full_game')
        self.assertEqual(case['context']['source'],'bound_game')
        self.assertEqual(case['observation'],expected_result)
        self.assertEqual(case['evidence']['catalog'],expected_catalog)
        self.assertTrue(case['evidence']['user_triggered'])
        self.assertEqual(case['evidence']['trigger'],'take_condition')

    def test_explicit_condition_unknown_without_panel_is_saved(self):
        result={'scene':'unknown','route':'none','status':'unknown',
                'reason':'no_verified_detail_panel','entity':None,'candidates':[],
                'evidence':{},'image_size':[1280,720]}
        self.assertTrue(self.r.observed_condition(result,self.p.last_frame));self.flush()
        case=self.manifests()[0]
        self.assertEqual(case['observation'],result)
        self.assertEqual(set(case['evidence']['catalog']),{'hex','equip','hero','trait'})
        self.assertEqual(case['evidence']['catalog']['hero'],[])
        self.assertEqual(case['evidence']['catalog']['trait'],[])

    def test_condition_success_ambiguity_and_choice_routes_do_not_save(self):
        for result in ({'route':'detail','status':'resolved'},
                       {'route':'detail','status':'ambiguous'},
                       {'route':'none','status':'resolved'},
                       {'route':'none','status':'ambiguous'},
                       {'route':'augment_stats','status':'unknown'},
                       {'route':'equipment_stats','status':'unknown'}):
            with self.subTest(result=result):
                self.assertFalse(self.r.observed_condition(result,self.p.last_frame))
        self.assertEqual(self.queue,[])
        self.assertFalse(self.directory.exists())

    def test_condition_failure_keeps_single_pending_cooldown_and_dedupe(self):
        result={'scene':'unknown','route':'none','status':'unknown','reason':'no_verified_detail_panel'}
        changed={**result,'scene':'condition_detail','reason':'primary_title_unconfirmed'}
        self.assertTrue(self.r.observed_condition(result,self.p.last_frame))
        self.assertFalse(self.r.observed_condition(changed,self.p.last_frame))
        self.flush()
        self.assertFalse(self.r.observed_condition(changed,self.p.last_frame))
        self.r.last_request-=16
        self.assertFalse(self.r.observed_condition(result,self.p.last_frame))
        self.assertTrue(self.r.observed_condition(changed,self.p.last_frame));self.flush()
        self.assertEqual(len(self.manifests()),2)

    def test_condition_failure_retains_game_binding_and_enabled_guards(self):
        result={'scene':'unknown','route':'none','status':'unknown'}
        self.r.enabled=False
        self.assertFalse(self.r.observed_condition(result,self.p.last_frame))
        self.r.enabled=True;self.p.binding.process='explorer.exe'
        self.assertFalse(self.r.observed_condition(result,self.p.last_frame))
        self.p.binding.process='MuMuNxDevice.exe'
        self.assertFalse(self.r.observed_condition(result,Image.new('RGB',(320,180))))
        self.r.shutdown()
        self.assertFalse(self.r.observed_condition(result,self.p.last_frame))
        self.assertEqual(self.queue,[])

    def test_manual_report_gets_bound_game_once_and_accepts_unknown_scene(self):
        with patch('bug_reporting.win.describe',return_value=self.binding),\
             patch('bug_reporting.win.same_target',return_value=True),\
             patch('bug_reporting.win.foreground_root',return_value=123),\
             patch('bug_reporting.QTimer.singleShot',side_effect=lambda ms,fn:fn()),\
             patch('bug_reporting.capture_image',return_value=(self.p.last_frame,self.binding)) as screenshot,\
             patch('item_controller.inspect_items',return_value=([],None)):
            self.r.manual_report()
            self.assertTrue(self.p.capture_pending)
            self.flush()
            screenshot.assert_called_once_with(self.binding)
        case=self.manifests()[0]
        self.assertEqual(case['reason'],'manual_report')
        self.assertEqual(case['observation']['scene'],'unknown')
        self.assertEqual(len(case['observation']['manual_frame_id']),64)
        self.assertFalse(self.r.manual_pending);self.assertFalse(self.p.capture_pending)

    def test_manual_capture_failure_and_late_session_do_not_save_desktop(self):
        with patch('bug_reporting.win.describe',return_value=self.binding),\
             patch('bug_reporting.win.same_target',return_value=True),\
             patch('bug_reporting.QTimer.singleShot',side_effect=lambda ms,fn:fn()),\
             patch('bug_reporting.capture_image',side_effect=RuntimeError('not_foreground')):
            self.r.manual_report();self.flush()
        self.assertEqual(self.manifests(),[])
        self.assertFalse(self.p.capture_pending);self.assertFalse(self.r.manual_pending)
        with patch('bug_reporting.win.describe',return_value=self.binding),\
             patch('bug_reporting.win.same_target',return_value=True),\
             patch('bug_reporting.QTimer.singleShot',side_effect=lambda ms,fn:fn()):
            self.r.manual_report()
            _,_,done,_=self.queue.pop()
            self.p.session.reset()
            done((self.p.last_frame,self.binding,'hex','a'*64))
        self.assertEqual(self.manifests(),[]);self.assertEqual(self.queue,[])

    def test_storage_limit_or_error_does_not_clear_results_and_releases_pending(self):
        self.p.stats_payload={'rows':[['别再错过','4.27','未固定阵容']]}
        for status in ('limit','error'):
            with self.subTest(status=status),patch.object(self.r.store,'save',return_value={'status':status}):
                self.r.last_request-=16
                self.r.capture('hex_unresolved',self.observation,self.p.last_frame)
                self.flush();self.assertFalse(self.r.pending)
                self.assertEqual(self.p.stats_payload['rows'][0][1],'4.27')
        self.assertEqual(self.p.status.setText.call_count,2)

    def test_shutdown_rejects_auto_and_deferred_manual_capture(self):
        deferred=[]
        with patch('bug_reporting.win.describe',return_value=self.binding),\
             patch('bug_reporting.win.same_target',return_value=True),\
             patch('bug_reporting.QTimer.singleShot',side_effect=lambda ms,fn:deferred.append(fn)),\
             patch('bug_reporting.capture_image') as screenshot:
            self.r.manual_report()
            self.assertTrue(self.p.capture_pending)
            self.r.shutdown()
            self.assertFalse(self.p.capture_pending)
            deferred[0]()
            self.r.manual_report()
            self.assertFalse(self.r.observed_hex(self.observation,self.p.last_frame))
            self.assertEqual(self.queue,[]);screenshot.assert_not_called()


if __name__=='__main__':unittest.main()
