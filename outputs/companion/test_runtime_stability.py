"""Synthetic scheduling regressions for manual capture and visible ranks."""
from contextlib import ExitStack
from pathlib import Path
import tempfile
import time
import gc
import weakref
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from PIL import Image
from app import QApplication, Companion
import cv2


class RuntimeStability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.qt=QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.stack=ExitStack();self.jobs=[]
        for module in ['app','dataj','comp_browser']:self.stack.enter_context(patch(module+'.STATE_DIR',Path(self.tmp.name)))
        self.stack.enter_context(patch('app.win.enumerate_mumu',return_value=[]))
        self.p=Companion(offline=True,offline_catalog={'hex':[{'id':'1023','name':'应急护甲 I'}],'hero':[],'equip':[],'trait':[]})
        self.p.timer.stop();self.p.hide()
        # Lifecycle tests own real visible Qt widgets, but must never overlay
        # the user's game with synthetic ranks while their callbacks are held.
        self.binding=SimpleNamespace(hwnd=123,pid=123,process='MuMuNxDevice.exe',rect=(-5000,-4000,-3080,-2920),dpi=96)
        for overlay in self.p.overlays+self.p.items.overlays:overlay.move(-5000,-4000)
        self.p.binding=self.binding;self.p.geometry=(self.binding.rect,96)
        self.stack.enter_context(patch('app.win.describe',return_value=self.binding))
        self.stack.enter_context(patch('app.win.foreground_root',return_value=123))
        self.stack.enter_context(patch('app.win.same_target',return_value=True))
        self.stack.enter_context(patch('app.win.capture_block_reason',return_value=None))
        self.stack.enter_context(patch.object(self.p,'submit',lambda pool,fn,done,failed=None,**scheduling:self.jobs.append((fn,done,failed))))
        self.stack.enter_context(patch('app.QTimer.singleShot',side_effect=lambda ms,fn:fn()))
        self.stack.enter_context(patch('app.win.user.SetForegroundWindow',return_value=True))

    def tearDown(self):
        self.p.shutdown();self.p.deleteLater();self.qt.processEvents();self.stack.close();self.tmp.cleanup()

    def seed_results(self):
        p=self.p;p.session.set_choices('2-1',['1023']*3)
        p.last_capture=time.monotonic()
        p.last_observation={'scene':'choice_candidates','round':'2-1','cards':[{'resolution':{'id':'1023'},'box':[[0,0],[100,0],[100,40],[0,40]]}]*3}
        p.stats_payload={'live':True,'token':p.session.token(),'rows':[['应急护甲 I','4.76 · 301局','未固定阵容']]*3}
        return p.stats_payload

    def test_same_stage_probe_keeps_manual_results(self):
        payload=self.seed_results();self.p.last_probe_stage=None
        self.p.probe_stage();_,done,_=self.jobs.pop();done('2-1')
        self.assertIs(self.p.stats_payload,payload,'First routine probe erases already confirmed manual results')

    def test_manual_trigger_does_not_blank_confirmed_results_before_capture(self):
        payload=self.seed_results()
        with patch.object(self.p,'hide_overlays') as hide:
            self.p.capture_once()
            self.assertFalse(hide.called,'Manual refresh hides results before any changed frame is observed')
        self.assertIs(self.p.stats_payload,payload)
        self.assertTrue(self.p.once_ocr_pending)

    def test_results_keep_being_checked_after_the_initial_stage_window(self):
        self.seed_results();self.p.stage_window_until=0;self.p.once_active=False
        self.p.last_capture=time.monotonic()-.6;self.p.last_stage_probe=time.monotonic()
        with patch.object(self.p,'request_capture') as capture,patch.object(self.p.items,'tick'):
            # Production mode matters: offline mode used to bypass this deadline.
            self.p.offline=False
            try:self.p.tick()
            finally:self.p.offline=True
        self.assertEqual(capture.call_count,1,'Visible results stop getting frames after 60s, then blink on timeout')

    def test_capture_processing_is_not_run_on_gui_callback(self):
        self.p.automatic.setChecked(False)
        with patch('item_controller.item_boxes',return_value=[]) as detect:
            self.p.captured((Image.new('RGB',(1280,720)),self.binding),False)
        self.assertFalse(detect.called,'Expensive image detection runs on the Qt callback')

    def test_invalidate_releases_last_full_frame(self):
        self.p.last_frame=Image.new('RGB',(1920,1080))
        self.p.invalidate()
        self.assertIsNone(self.p.last_frame,'Idle helper retains the previous full game frame')

    def accept(self,signature=None,items=([],None)):
        self.p.accept_frame((Image.new('RGB',(1280,720)),self.binding),False,(items,signature),time.monotonic())

    def test_manual_refresh_of_identical_choices_does_not_repeat_ocr(self):
        payload=self.seed_results();self.p.once_active=True;self.p.once_ocr_pending=True
        with patch('app.unchanged',return_value=True),patch.object(self.p,'analyze') as ocr,patch.object(self.p,'display_overlays') as display:
            self.accept()
        self.assertFalse(ocr.called);self.assertTrue(display.called)
        self.assertIs(self.p.stats_payload,payload);self.assertFalse(self.p.once_ocr_pending)

    def test_changed_cards_cancel_old_data_and_keep_manual_recognition_armed(self):
        self.p.automatic.setChecked(False);self.seed_results()
        token=self.p.session.token();self.p.once_active=True;self.p.once_ocr_pending=True;self.p.once_deadline=time.monotonic()+30
        with patch('app.unchanged',return_value=False),patch.object(self.p,'analyze') as ocr:
            self.accept()
        self.assertFalse(self.p.session.accepts(token));self.assertIsNone(self.p.stats_payload)
        self.assertTrue(self.p.once_active);self.assertEqual(ocr.call_count,1)

    def test_manual_refresh_after_old_deadline_keeps_the_new_ocr_request(self):
        self.p.automatic.setChecked(False);self.seed_results()
        self.p.once_active=True;self.p.once_deadline=0
        with patch('app.unchanged',return_value=False),patch.object(self.p,'analyze') as ocr:
            self.accept()
        token=self.p.session.token()
        with patch.object(self.p,'request_capture'):self.p.tick()
        self.assertEqual(ocr.call_count,1);self.assertTrue(self.p.session.accepts(token))
        self.assertTrue(self.p.once_active);self.assertGreater(self.p.once_deadline,time.monotonic())

    def test_changed_cards_after_stage_window_do_not_wait_for_previous_group_cooldown(self):
        self.seed_results();self.p.stage_window_until=0;self.p.last_probe_stage='2-1'
        self.p.next_ocr_allowed=time.monotonic()+2
        with patch('app.unchanged',return_value=False),patch.object(self.p,'analyze') as ocr:
            self.accept()
            ocr.assert_called_once()
            self.assertEqual(self.p.next_ocr_allowed,0)
            self.p.last_capture=time.monotonic()-.6
            self.p.last_stage_probe=time.monotonic()
            with patch.object(self.p,'request_capture') as capture,patch.object(self.p.items,'tick'):
                self.p.offline=False
                try:self.p.tick()
                finally:self.p.offline=True
            self.assertEqual(capture.call_count,1)

    def test_manual_refresh_retries_failed_comp_statistics_without_repeating_ocr(self):
        payload=self.seed_results();payload['retryable']=True
        payload['rows'][0][2]='阵容数据暂不可用'
        self.p.once_active=True;self.p.once_ocr_pending=True
        with patch('app.unchanged',return_value=True),patch.object(self.p,'analyze') as ocr,patch.object(self.p,'query_stats') as query,patch.object(self.p,'display_overlays'):
            self.accept()
        self.assertFalse(ocr.called);self.assertEqual(query.call_count,1)

    def test_failed_global_refresh_cannot_restore_retained_old_ranks(self):
        self.seed_results()
        self.p.stage.blockSignals(True);self.p.stage.setCurrentText('2-1');self.p.stage.blockSignals(False)
        self.p.query_stats(['1023']*3,['应急护甲 I']*3,True,refresh=True)
        _,_,failed=self.jobs.pop();failed('synthetic offline source')
        self.assertIsNone(self.p.stats_payload)
        with patch.object(self.p.overlays[0],'place') as place:self.p.display_overlays()
        self.assertFalse(place.called)

    def test_item_proposal_cannot_keep_stale_augment_results(self):
        self.seed_results();token=self.p.session.token()
        with patch('app.unchanged',return_value=False),patch.object(self.p.items,'ingest',return_value=True):
            self.accept(items=([(100,400,200,500)]*3,None))
        self.assertIsNone(self.p.stats_payload);self.assertFalse(self.p.session.accepts(token))

    def test_augment_refresh_controls_take_priority_over_board_item_shapes(self):
        with patch('app.may_be_choice',return_value=True),patch('app.inspect_items') as detect:
            self.p.captured((Image.new('RGB',(1280,720)),self.binding),False)
            work,_,_=self.jobs.pop();prepared=work()
        self.assertFalse(detect.called);self.assertEqual(prepared[0],([],None))

    def test_late_frame_cannot_restore_invalidated_results(self):
        self.seed_results();self.p.captured((Image.new('RGB',(1280,720)),self.binding),False)
        _,done,_=self.jobs.pop();self.p.invalidate()
        with patch.object(self.p,'accept_frame') as accept:done((([],None),None))
        self.assertFalse(accept.called);self.assertFalse(self.p.capture_pending)

    def test_foreground_loss_discards_capture(self):
        with patch('app.win.foreground_root',return_value=0),patch.object(self.p.items,'ingest') as ingest:
            self.accept()
        self.assertFalse(ingest.called);self.assertIsNone(self.p.last_frame)

    def test_manual_results_keep_being_checked_after_thirty_seconds(self):
        self.p.automatic.setChecked(False);payload=self.seed_results()
        self.p.once_active=True;self.p.once_deadline=0;self.p.last_capture=time.monotonic()-.6
        with patch.object(self.p,'request_capture') as capture:self.p.tick()
        self.assertEqual(capture.call_count,1);self.assertIs(self.p.stats_payload,payload)

    def test_changed_stage_still_invalidates_results(self):
        self.seed_results();token=self.p.session.token();self.p.last_probe_stage='2-1'
        self.p.probe_stage();_,done,_=self.jobs.pop();done('2-2')
        self.assertFalse(self.p.session.accepts(token));self.assertIsNone(self.p.stats_payload)
        self.assertEqual(self.p.stage_window_until,0)

    def test_late_stage_probe_cannot_cancel_manual_capture(self):
        self.p.probe_stage();_,done,_=self.jobs.pop()
        self.p.capture_once();token=self.p.session.token();done('2-1')
        self.assertTrue(self.p.session.accepts(token));self.assertTrue(self.p.once_ocr_pending)
        self.assertTrue(self.p.capture_pending)

    def test_repeated_shortcuts_keep_one_capture_in_flight(self):
        for _ in range(30):self.p.capture_once()
        self.assertEqual(len(self.jobs),1)
        self.assertTrue(self.p.capture_pending)

    def test_foreground_shortcut_does_not_wait_for_a_panel_animation(self):
        with patch('app.QTimer.singleShot') as timer:self.p.capture_once()
        self.assertEqual(timer.call_args.args[0],0)

    def test_panel_trigger_waits_until_the_panel_has_hidden(self):
        with patch.object(self.p,'panel_open',return_value=True),patch.object(self.p,'return_to_game',return_value=True),patch('app.QTimer.singleShot') as timer:
            self.p.capture_once()
        self.assertEqual(timer.call_args.args[0],100)

    def test_stale_capture_does_not_paint_results(self):
        self.seed_results();self.p.last_capture=time.monotonic()-2
        with patch.object(self.p.overlays[0],'place') as place:self.p.display_overlays()
        self.assertFalse(place.called)

    def test_opencv_does_not_use_all_game_cpu_cores(self):
        self.assertLessEqual(cv2.getNumThreads(),1)

    def check_job_release(self,fail):
        completed=[];frame=Image.new('RGB',(1280,720));reference=weakref.ref(frame)
        def work(image=frame):
            if fail:raise RuntimeError('synthetic worker failure')
            return image.size
        def done(result,image=frame):completed.append(result)
        def failed(message,image=frame):completed.append(message)
        gc_enabled=gc.isenabled();gc.disable()
        try:
            # Run the real Qt worker; the other scheduling tests deliberately
            # use a controllable queue. No forced collection may be necessary.
            Companion.submit(self.p,self.p.capture_pool,work,done,failed)
            del frame,work,done,failed
            deadline=time.monotonic()+3
            while self.p.jobs and time.monotonic()<deadline:self.qt.processEvents();time.sleep(.001)
            self.p.capture_pool.waitForDone();self.qt.processEvents()
            self.assertTrue(completed);self.assertFalse(self.p.jobs)
            self.assertIsNone(reference(),'Completed worker callbacks retain a full game frame until cyclic GC')
        finally:
            if gc_enabled:gc.enable()

    def test_completed_capture_releases_frame_without_cyclic_gc(self):self.check_job_release(False)

    def test_failed_capture_releases_frame_without_cyclic_gc(self):self.check_job_release(True)


if __name__=='__main__':unittest.main()
