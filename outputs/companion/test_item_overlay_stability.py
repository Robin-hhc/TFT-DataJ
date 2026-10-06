"""Real Qt item-window lifecycle, with capture/OCR/native boundaries controlled."""
from copy import deepcopy
import time
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw
from app import QApplication
from item_vision import item_signature
from PySide6.QtCore import QObject, QEvent
import test_runtime_stability as fixtures


class ItemOverlayStabilityTests(unittest.TestCase):
    tearDown = fixtures.RuntimeStability.tearDown

    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        fixtures.RuntimeStability.setUp(self)
        self.clock = 100.0
        self.stack.enter_context(patch('item_controller.time.monotonic', side_effect=lambda:self.clock))
        self.stack.enter_context(patch('item_controller.win.user.SetWindowPos', return_value=True))
        self.frame = Image.new('RGB', (1920,1080))
        self.boxes = [(240+i*300,750,440+i*300,950) for i in range(5)]
        draw = ImageDraw.Draw(self.frame)
        draw.rectangle((820,690,1100,700),fill='white')
        for left,top,right,bottom in self.boxes:
            draw.rectangle((left+20,top+100,right-20,top+115),fill='white')
        self.signature = item_signature(self.frame,self.boxes)
        self.ids = ['2007','2040','2016','2006','2017']
        self.p.catalog['equip'] = [{'id':id_,'name':'测试装备'+id_,'type':'成型装备'} for id_ in self.ids]
        self.observation = {'scene':'item_candidates','image_size':self.frame.size,'cards':[],'elapsed_ms':1}
        for slot,(box,row) in enumerate(zip(self.boxes,self.p.catalog['equip'])):
            left,top,right,bottom = box
            self.observation['cards'].append({'slot':slot,'box':[[left,top],[right,top],[right,bottom],[left,bottom]],
                'resolution':{'status':'resolved',**row,'candidates':[dict(row)]}})
        self.stack.enter_context(patch('item_controller.analyze_items', return_value=deepcopy(self.observation)))
        table = {'data':[{'equipId':id_,'sampleCount':100,'avgPlacement':4.1} for id_ in self.ids],
                 'source':'test fixture','fetched_at':time.time()}
        self.stack.enter_context(patch.object(self.p.adapter,'item_stats',return_value=table))
        self.stack.enter_context(patch.object(self.p.adapter,'item_holders',return_value={**table,'data':[]}))
        self.p.items.ingest(self.frame,self.binding,prepared=(self.boxes,self.signature),frame_time=self.clock)
        while self.jobs:
            self.run_one()
        self.qt.processEvents()
        self.assertTrue(self.visible())

    def run_one(self):
        work,done,failed = self.jobs.pop(0)
        try: result = work()
        except Exception as exc:
            if failed:failed(str(exc))
            else:raise
        else:done(result)

    def visible(self):
        self.qt.processEvents()
        return all(overlay.isVisible() for overlay in self.p.items.overlays)

    def test_delayed_same_offer_capture_does_not_hide_then_show(self):
        self.clock = 100.6
        self.p.items.tick()
        self.assertEqual(len(self.jobs),1)
        self.clock = 101.6
        self.p.items.tick()
        self.assertTrue(self.visible(), 'Same item offer hid while its verification capture was in flight')
        _,done,_ = self.jobs.pop(0)
        done((self.frame,self.binding,(self.boxes,self.signature),self.clock))
        self.assertTrue(self.visible())
        self.assertEqual(self.jobs,[], 'Unchanged resolved items must not repeat OCR/network requests')

    def test_stalled_capture_eventually_hides_old_equipment(self):
        self.clock = 100.6
        self.p.items.tick()
        self.clock = 101.6
        self.p.items.tick()
        self.assertTrue(self.visible())
        self.clock = 101.851
        self.p.items.tick()
        self.assertFalse(self.visible(), 'An equipment capture stall must have a finite display grace')

    def test_capture_grace_cannot_extend_absolute_old_frame_age(self):
        self.clock = 102.0
        self.p.items.tick()
        self.clock = 102.751
        self.p.items.tick()
        self.assertFalse(self.visible())

    def test_focus_loss_hides_without_waiting_for_capture_age(self):
        self.clock = 100.6
        self.p.items.tick()
        self.clock = 100.7
        with patch('item_controller.win.foreground_root',return_value=99):
            self.p.items.tick()
            self.assertFalse(self.visible())
            _,done,_ = self.jobs.pop(0)
            done((self.frame,self.binding,(self.boxes,self.signature),self.clock))
            self.assertFalse(self.visible(), 'The held capture callback must not repaint off focus')

    def test_same_title_capture_with_box_noise_does_not_restart_recognition(self):
        shifted = [tuple(v+6 for v in box) for box in self.boxes]
        self.clock = 100.6
        with patch('item_controller.capture_item_region',return_value=(self.frame,self.binding)), \
                patch('item_controller.item_boxes',return_value=shifted):
            self.p.items.tick()
            self.run_one()
        self.assertTrue(self.visible(), 'Detector-box noise cleared unchanged equipment ranks')
        self.assertEqual(self.jobs,[], 'Detector-box noise repeated OCR for the same titles')
        self.assertEqual([row['id'] for row in self.p.items.rows],self.ids)

    def test_manual_full_frame_same_offer_with_box_noise_keeps_ranks_without_ocr(self):
        shifted = [tuple(v+6 for v in box) for box in self.boxes]
        self.clock = 102.1
        with patch('app.may_be_choice',return_value=False), \
                patch('item_controller.item_boxes',return_value=shifted):
            self.p.captured((self.frame,self.binding),True,captured_at=self.clock)
            self.assertEqual(len(self.jobs),1)
            self.run_one()
        self.assertTrue(self.visible(), 'Manual full-frame inspection hid the same item offer')
        self.assertEqual(self.jobs,[], 'Manual refresh of confirmed unchanged item titles repeated OCR')

    def test_partial_retry_crop_reference_stays_consistent_across_outline_jitter(self):
        self.p.items.rows[-1]['id'] = None
        unknown = {'scene':'unknown','reason':'item_header_unconfirmed','cards':[],'image_size':self.frame.size}
        with patch('item_controller.analyze_items',return_value=unknown):
            for delta in (6,-6,6):
                shifted = [tuple(v+delta for v in box) for box in self.boxes]
                self.clock += 2.1
                with patch('item_controller.capture_item_region',return_value=(self.frame,self.binding)), \
                        patch('item_controller.item_boxes',return_value=shifted):
                    self.p.items.tick()
                    self.run_one()
                    while self.jobs:self.run_one()
                self.assertTrue(self.visible(), 'Partial retry changed the crop reference and hid stable titles')

    def test_unreadable_partial_retry_retains_fresh_same_title_ranks(self):
        self.p.items.rows[-1]['id'] = None
        self.p.items.rows[-1]['global'] = {'status':'unrecognized'}
        self.p.items.observation['cards'][-1]['resolution'] = {'status':'unrecognized'}
        self.clock = 102.1
        unknown = {'scene':'unknown','reason':'item_header_unconfirmed','cards':[],
                   'image_size':self.frame.size}
        with patch('item_controller.analyze_items',return_value=unknown):
            self.p.items.ingest(self.frame,self.binding,prepared=(self.boxes,self.signature),frame_time=self.clock)
            self.assertEqual(len(self.jobs),1)
            self.run_one()
        self.assertTrue(self.visible(), 'An OCR header dropout erased already-confirmed unchanged ranks')
        self.assertTrue(self.p.items.active)
        self.assertEqual([row['id'] for row in self.p.items.rows[:4]],self.ids[:4])

    def test_true_title_change_hides_before_pending_new_ocr(self):
        changed = self.frame.copy()
        draw = ImageDraw.Draw(changed)
        draw.rectangle((260,850,420,865),fill='black')
        draw.rectangle((310,838,320,884),fill='white')
        self.clock = 102.1
        self.p.items.ingest(changed,self.binding,prepared=(self.boxes,item_signature(changed,self.boxes)),frame_time=self.clock)
        self.assertFalse(self.visible())
        self.assertEqual(len(self.jobs),1)
        self.assertEqual(self.p.items.rows,[])

    def test_confirmed_excluded_entity_cannot_keep_cached_item_ranks(self):
        self.p.items.rows[-1]['id'] = None
        self.clock = 102.1
        unknown = {'scene':'unknown','reason':'excluded_or_unconfirmed','cards':deepcopy(self.observation['cards'])}
        unknown['cards'][0]['resolution'] = {'status':'excluded','excluded_id':'1001'}
        with patch('item_controller.analyze_items',return_value=unknown):
            self.p.items.ingest(self.frame,self.binding,prepared=(self.boxes,self.signature),frame_time=self.clock)
            self.run_one()
        self.assertFalse(self.visible())

    def test_conflicting_resolved_title_cannot_keep_cached_ranks(self):
        self.p.items.rows[-1]['id'] = None
        self.clock = 102.1
        unknown = {'scene':'unknown','reason':'excluded_or_unconfirmed','cards':deepcopy(self.observation['cards'])}
        unknown['cards'][0]['resolution'] = {'status':'resolved','id':'2059'}
        with patch('item_controller.analyze_items',return_value=unknown):
            self.p.items.ingest(self.frame,self.binding,prepared=(self.boxes,self.signature),frame_time=self.clock)
            self.run_one()
        self.assertFalse(self.visible())
        self.assertFalse(self.p.items.active)

    def test_unreadable_same_title_retries_stop_after_two_ocr_attempts(self):
        self.p.items.rows[-1]['id'] = None
        unknown = {'scene':'unknown','reason':'item_header_unconfirmed','cards':[],'image_size':self.frame.size}
        with patch('item_controller.analyze_items',return_value=unknown) as ocr:
            for index in range(3):
                self.clock += 2.1
                self.p.items.ingest(self.frame,self.binding,prepared=(self.boxes,self.signature),frame_time=self.clock)
                self.assertEqual(len(self.jobs),1 if index<2 else 0)
                while self.jobs:self.run_one()
                self.assertTrue(self.visible())
            self.assertEqual(ocr.call_count,2)

    def test_capture_failure_hides_and_late_old_capture_cannot_restore(self):
        self.clock = 100.6
        self.p.items.tick()
        _,done,failed = self.jobs.pop(0)
        failed('capture failed')
        self.assertFalse(self.visible())
        self.assertFalse(self.p.capture_pending)
        done((self.frame,self.binding,(self.boxes,self.signature),self.clock))
        self.assertFalse(self.visible())
        self.assertEqual(self.jobs,[])

    def test_late_successful_capture_cannot_make_old_pixels_fresh_again(self):
        self.clock = 100.6
        self.p.items.tick()
        _,done,_ = self.jobs.pop(0)
        captured_at = self.clock
        self.clock = 104.0
        self.p.items.tick()
        self.assertFalse(self.visible())
        done((self.frame,self.binding,(self.boxes,self.signature),captured_at))
        self.assertFalse(self.visible(), 'Late successful capture relabeled old pixels as freshly verified')
        self.assertEqual(self.p.items.last_seen,captured_at)

    def test_late_ocr_success_cannot_refresh_its_old_frame_age(self):
        self.p.items.rows[-1]['id'] = None
        self.clock = 100.6
        captured_at = self.clock
        self.p.items.ingest(self.frame,self.binding,force=True,prepared=(self.boxes,self.signature),frame_time=captured_at)
        self.assertEqual(len(self.jobs),1)
        self.clock = 104.0
        self.p.items.tick()
        self.assertFalse(self.visible())
        self.run_one()
        self.assertFalse(self.visible(), 'Late OCR callback made its stale source frame look new')
        self.assertEqual(self.p.items.last_seen,captured_at)

    def test_late_ocr_preserves_newer_verified_same_title_frame_time(self):
        self.p.items.rows[-1]['id'] = None
        self.clock = 100.6
        self.p.items.ingest(self.frame,self.binding,force=True,prepared=(self.boxes,self.signature),frame_time=self.clock)
        self.assertEqual(len(self.jobs),1)
        self.clock = 102.6
        verified_at = self.clock
        self.p.items.ingest(self.frame,self.binding,prepared=(self.boxes,self.signature),frame_time=verified_at)
        self.assertEqual(len(self.jobs),1, 'A new identical frame must reuse the OCR already running')
        self.clock = 104.0
        self.run_one()
        self.assertTrue(self.visible(), 'Newer verified same-title pixels were lost when old OCR returned')
        self.assertEqual(self.p.items.last_seen,verified_at, 'OCR may neither advance nor rewind a verified frame time')

    def test_title_change_with_outline_noise_still_clears_cached_data(self):
        shifted = [tuple(v+6 for v in box) for box in self.boxes]
        changed = self.frame.copy()
        draw = ImageDraw.Draw(changed)
        draw.rectangle((260,850,420,865),fill='black')
        draw.rectangle((310,838,320,884),fill='white')
        self.clock = 102.1
        with patch('item_controller.capture_item_region',return_value=(changed,self.binding)), \
                patch('item_controller.item_boxes',return_value=shifted):
            self.p.items.tick()
            self.run_one()
        self.assertFalse(self.visible())
        self.assertEqual(self.p.items.rows,[])
        self.assertEqual(len(self.jobs),1)

    def test_late_old_statistics_cannot_repaint_after_changed_offer(self):
        self.p.items.cache.clear()
        self.p.items.start_queries()
        self.assertEqual(len(self.jobs),1)
        work,late_done,_ = self.jobs.pop(0)
        old_result = work()
        changed = self.frame.copy()
        draw = ImageDraw.Draw(changed)
        draw.rectangle((260,850,420,865),fill='black')
        self.clock = 102.1
        self.p.items.ingest(changed,self.binding,prepared=(self.boxes,item_signature(changed,self.boxes)),frame_time=self.clock)
        late_done(old_result)
        self.assertFalse(self.visible())
        self.assertEqual(self.p.items.rows,[])

    def test_idle_with_automatic_checks_disabled_does_not_capture_or_ocr(self):
        self.p.items.reset()
        self.p.automatic.setChecked(False)
        self.clock = 110.0
        self.p.items.tick()
        self.assertEqual(self.jobs,[])

    def test_ordinary_board_without_choice_boxes_clears_immediately(self):
        self.clock = 100.6
        self.assertFalse(self.p.items.ingest(self.frame,self.binding,prepared=([],None),frame_time=self.clock))
        self.assertFalse(self.visible())
        self.assertFalse(self.p.items.active)

    def test_forty_unchanged_frames_do_not_hide_show_or_repeat_ocr(self):
        events = []
        class Observer(QObject):
            def eventFilter(self,widget,event):
                if event.type() in (QEvent.Type.Hide,QEvent.Type.Show):events.append(event.type())
                return False
        observer = Observer()
        for overlay in self.p.items.overlays:overlay.installEventFilter(observer)
        try:
            for _ in range(40):
                self.clock += .6
                self.p.items.tick()
                self.assertEqual(len(self.jobs),1)
                self.clock += .9
                self.p.items.tick()
                self.assertTrue(self.visible())
                _,done,_ = self.jobs.pop(0)
                done((self.frame,self.binding,(self.boxes,self.signature),self.clock))
                self.assertTrue(self.visible())
                self.assertEqual(self.jobs,[])
            self.assertEqual(events,[], 'Steady item choices generated actual Qt Hide/Show events')
        finally:
            for overlay in self.p.items.overlays:overlay.removeEventFilter(observer)


if __name__ == '__main__':
    unittest.main()
