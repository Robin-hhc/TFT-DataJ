"""Real Qt application callbacks route accepted failures to a private archive."""
from contextlib import ExitStack
from copy import deepcopy
import gc
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import weakref

from PIL import Image
from app import Companion, QApplication
from bug_cases import BugCaseStore


class BugCaptureIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.qt=QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.stack=ExitStack();self.pending=[]
        for module in ('app','dataj','comp_browser'):
            self.stack.enter_context(patch(module+'.STATE_DIR',Path(self.tmp.name)))
        self.stack.enter_context(patch('app.win.enumerate_mumu',return_value=[]))
        self.stack.enter_context(patch('bug_reporting.record'))
        self.p=Companion(offline=True,offline_catalog={'hex':[{'id':'1625','name':'别再错过'}],
                                                    'equip':[],'hero':[],'trait':[]})
        self.p.timer.stop();self.p.hide()
        self.directory=Path(self.tmp.name)/'bug-cases'
        self.p.bugs.store=BugCaseStore(self.directory);self.p.bugs.enabled=True
        self.binding=SimpleNamespace(hwnd=123,pid=123,process='MuMuNxDevice.exe',
            rect=(-5000,-4000,-3720,-3280),dpi=96)
        self.p.binding=self.binding
        self.p.last_frame=Image.new('RGB',(1280,720),'#193a20');self.p.last_capture=time.monotonic()
        self.p.adapter.hexes=lambda comp=None:{'data':[],'fetched_at':time.time()}
        self.stack.enter_context(patch('app.win.foreground_root',return_value=123))
        self.stack.enter_context(patch('app.win.describe',return_value=self.binding))
        self.stack.enter_context(patch('app.win.same_target',return_value=True))
        for overlay in self.p.overlays+self.p.items.overlays:overlay.move(-5000,-4000)
        self.stack.enter_context(patch.object(self.p,'display_overlays'))
        self.stack.enter_context(patch.object(self.p.items,'render'))
        self.stack.enter_context(patch.object(self.p,'submit',
            lambda pool,fn,done,failed=None:self.pending.append((pool,fn,done,failed))))
        self.observation={'scene':'choice_candidates','round':'3-2','image_size':[1280,720],
            'elapsed_ms':200,'cards':[{'slot':i,'raw_text':name,
            'box':[[100+i*350,260],[300+i*350,260],[300+i*350,300],[100+i*350,300]],
            'resolution':{'status':'resolved','id':str(i+1),'name':name,'readings':[name]*3}}
            for i,name in enumerate(['甲','乙','别再错过'])]}
        self.observation['cards'][2]['resolution']={'status':'ambiguous','readings':['别再错过']*3,
            'candidates':[{'id':'1625','name':'别再错过'},{'id':'10784','name':'别再错过'}]}

    def tearDown(self):
        self.pending.clear();self.p.shutdown();self.p.deleteLater();self.qt.processEvents()
        self.stack.close();self.tmp.cleanup()

    def run_job(self,pool):
        index=next(i for i,item in enumerate(self.pending) if item[0] is pool)
        _,job,done,failed=self.pending.pop(index)
        try:result=job()
        except Exception as exc:
            if failed:failed(str(exc))
            else:raise
        else:done(result)

    def saved(self):
        return [json.loads(path.read_text(encoding='utf-8')) for path in self.directory.glob('case-*/case.json')]

    def test_accepted_live_ocr_routes_exact_captured_frame_and_catalog_to_archive(self):
        with patch.object(self.p.vision,'analyze_fast',return_value=self.observation),\
             patch('bug_reporting.capture_image') as extra_capture:
            self.p.analyze(self.p.last_frame,True);self.run_job(self.p.ocr_pool)
            extra_capture.assert_not_called()
        self.assertTrue(any(pool is self.p.bugs.pool for pool,*_ in self.pending))
        self.run_job(self.p.bugs.pool)
        self.assertEqual(self.saved()[0]['reason'],'hex_unresolved')
        self.assertEqual(self.saved()[0]['observation']['cards'][2]['raw_text'],'别再错过')

    def test_late_ocr_and_file_replay_do_not_create_live_bug_cases(self):
        image=self.p.last_frame
        with patch.object(self.p.vision,'analyze_fast',return_value=self.observation):
            self.p.analyze(image,True);self.p.invalidate();self.run_job(self.p.ocr_pool)
        self.assertEqual(self.saved(),[])
        self.assertFalse(any(pool is self.p.bugs.pool for pool,*_ in self.pending))
        with patch.object(self.p.vision,'analyze',return_value=self.observation):
            self.p.analyze(image,False);self.run_job(self.p.ocr_pool)
        self.assertFalse(any(pool is self.p.bugs.pool for pool,*_ in self.pending))

    def test_actual_query_failure_callback_keeps_original_game_evidence(self):
        self.p.last_observation=self.observation
        self.p.adapter.hexes=lambda comp=None:(_ for _ in ()).throw(RuntimeError('source offline'))
        self.p.query_stats(['1','2','1625'],['甲','乙','别再错过'],True)
        self.run_job(self.p.hex_network);self.run_job(self.p.bugs.pool)
        case=self.saved()[0]
        self.assertEqual(case['reason'],'hex_query_failed')
        self.assertEqual(case['evidence']['requested_ids'],['1','2','1625'])
        self.assertIsNone(self.p.stats_payload)

    def test_item_callback_saves_unconfirmed_slots_without_extra_capture(self):
        observation=deepcopy(self.observation);observation['scene']='item_candidates'
        boxes=[(100+i*350,500,300+i*350,650) for i in range(3)]
        with patch('item_controller.analyze_items',return_value=observation):
            self.p.items.ingest(self.p.last_frame,self.binding,prepared=(boxes,None),frame_scope='item_band')
            self.run_job(self.p.ocr_pool)
        self.run_job(self.p.bugs.pool)
        self.assertEqual(self.saved()[0]['reason'],'item_unresolved')
        self.assertEqual(self.saved()[0]['context']['frame_scope'],'item_band')

    def test_real_qt_background_save_releases_frame_after_task_completion(self):
        self.stack.enter_context(patch.object(self.p,'submit',Companion.submit.__get__(self.p)))
        thread_ids=[];save=self.p.bugs.store.save
        def writer(*args,**kwargs):
            thread_ids.append(threading.get_ident())
            return save(*args,**kwargs)
        image=Image.new('RGB',(1280,720),'#193a20');reference=weakref.ref(image)
        with patch.object(self.p.bugs.store,'save',side_effect=writer):
            self.p.bugs.observed_hex(self.observation,image)
            del image
            deadline=time.monotonic()+5
            while self.p.jobs and time.monotonic()<deadline:self.qt.processEvents();time.sleep(.001)
        self.assertFalse(self.p.jobs);self.assertFalse(self.p.bugs.pending)
        self.assertEqual(len(thread_ids),1)
        self.assertNotEqual(thread_ids[0],threading.get_ident())
        gc.collect();self.assertIsNone(reference())


if __name__=='__main__':unittest.main()
