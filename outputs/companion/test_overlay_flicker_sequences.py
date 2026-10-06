"""Visible Qt rank-window sequences, without game input or native positioning."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
from app import QApplication
from PySide6.QtCore import QObject, QEvent
from vision import TextSignature
import test_runtime_stability as fixtures


class OverlayFlickerSequences(unittest.TestCase):
    tearDown = fixtures.RuntimeStability.tearDown
    seed_results = fixtures.RuntimeStability.seed_results

    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        fixtures.RuntimeStability.setUp(self)
        self.clock = 100.0
        self.stack.enter_context(patch('app.time.monotonic', side_effect=lambda: self.clock))
        self.stack.enter_context(patch('app.win.user.SetWindowPos', return_value=True))
        self.stack.enter_context(patch.object(self.p.items, 'tick'))
        self.p.automatic.setChecked(True)
        self.payload = self.seed_results()
        self.p.last_stage_probe = self.clock
        self.p.last_resource_guard = self.clock
        self.frame = Image.new('RGB', (1920, 1080))
        self.signature = TextSignature((np.ones((8, 20), dtype=bool),))
        self.p.signature = self.signature
        self.p.last_frame = self.frame
        self.p.display_overlays()
        self.qt.processEvents()
        self.assertTrue(self.p.overlays[0].isVisible())

    def visible(self):
        self.qt.processEvents()
        return self.p.overlays[0].isVisible()

    def test_delayed_unchanged_background_capture_does_not_hide_then_show(self):
        p = self.p
        visibility = [self.visible()]
        self.clock = 100.6
        p.tick()  # one capture is queued, with the known ranks still visible
        self.assertTrue(p.capture_pending)
        self.clock = 101.6
        p.tick()  # the previous last_capture crosses the separate 1.5s timer
        visibility.append(self.visible())
        _, capture_done, _ = self.jobs.pop(0)
        capture_done(((self.frame, self.binding), self.clock))
        _, inspect_done, _ = self.jobs.pop(0)
        inspect_done((([], None), self.signature))
        visibility.append(self.visible())
        self.assertEqual(visibility, [True, True, True],
                         'An unchanged capture produced visible -> hidden -> visible')

    def prepare_partial(self):
        p = self.p
        p.last_observation['cards'] = [deepcopy(card) for card in p.last_observation['cards']]
        p.last_observation['cards'][2]['resolution'] = {'id': None}
        p.session.set_choices('2-1', ['1023', '1023', None])
        self.payload['token'] = p.session.token()
        self.payload['rows'] = [list(row) for row in self.payload['rows']]
        self.payload['rows'][2] = ['未确认', '— 无数据/未识别', '未固定阵容']
        self.assertEqual([card['resolution'].get('id') for card in p.last_observation['cards']],
                         ['1023', '1023', None])
        p.last_ocr = 97.0
        p.next_ocr_allowed = 0
        return p

    def deliver_partial(self, observation, before_delivery=None):
        p = self.prepare_partial()
        with patch.object(p.vision, 'analyze_fast', return_value=observation):
            p.accept_frame((self.frame, self.binding), False,
                           (([], None), self.signature), self.clock)
            self.assertEqual(len(self.jobs), 1)
            work, done, _ = self.jobs.pop(0)
            result = work()
            if before_delivery:
                before_delivery()
            done(result)

    def unresolved(self, scene='choice_unresolved', stage=None):
        return {'scene': scene, 'round': stage, 'cards': [],
                'elapsed_ms': 1, 'image_size': self.frame.size}

    def test_unreadable_partial_retry_does_not_erase_fresh_unchanged_known_ranks(self):
        p = self.p
        unknown = {'scene': 'choice_unresolved', 'round': None, 'cards': [],
                   'elapsed_ms': 1, 'image_size': self.frame.size}
        self.deliver_partial(unknown)
        self.assertTrue(self.visible(), 'One partial OCR retry hid already-confirmed ranks')
        self.assertIs(p.stats_payload, self.payload)

    def test_capture_that_stalls_beyond_bounded_grace_hides_existing_ranks(self):
        self.clock = 100.6
        self.p.tick()
        self.clock = 101.6
        self.p.tick()
        self.assertTrue(self.visible())
        self.clock = 101.851
        self.p.tick()
        self.assertFalse(self.visible(), 'A stalled capture kept old ranks indefinitely')

    def test_capture_grace_does_not_extend_absolute_old_frame_age(self):
        # The worker itself is recent, but no verified frame exists for >2.75s.
        self.clock = 102.0
        self.p.request_capture()
        self.clock = 102.751
        self.p.tick()
        self.assertFalse(self.visible())

    def test_late_capture_success_uses_pixel_time_and_cannot_restore_expired_ranks(self):
        self.clock = 100.6
        self.p.request_capture()
        capture, captured, _ = self.jobs.pop(0)
        with patch('app.capture_image', return_value=(self.frame, self.binding)):
            result = capture()
        self.clock = 104.0
        self.p.tick()
        self.assertFalse(self.visible())
        captured(result)
        _, inspected, _ = self.jobs.pop(0)
        inspected((([], None), self.signature))
        self.assertFalse(self.visible(), 'An old successful capture was presented as fresh pixels')
        self.assertEqual(self.p.last_capture, 100.6)

    def test_foreground_loss_hides_even_inside_capture_grace(self):
        self.clock = 100.6
        self.p.tick()
        self.clock = 101.6
        with patch('app.win.foreground_root', return_value=99), \
             patch('app.win.capture_block_reason', return_value='not_foreground'):
            self.p.tick()
        self.assertFalse(self.visible())
        self.assertIsNone(self.p.stats_payload)
        _, capture_done, _ = self.jobs.pop(0)
        capture_done(((self.frame, self.binding), self.clock))
        self.assertFalse(self.visible(), 'A stale callback repainted after focus loss')

    def test_changed_signature_clears_old_ranks_before_late_statistics(self):
        p = self.p
        p.stage.blockSignals(True)
        p.stage.setCurrentText('2-1')
        p.stage.blockSignals(False)
        p.query_stats(['1023']*3, ['应急护甲 I']*3, True, refresh=True)
        _, late_stats, _ = self.jobs.pop(0)
        changed = TextSignature((np.zeros((8, 20), dtype=bool),))
        p.accept_frame((self.frame, self.binding), False,
                       (([], None), changed), self.clock)
        self.assertFalse(self.visible())
        self.assertIsNone(p.stats_payload)
        late_stats(({'data': [], 'fetched_at': 0}, None))
        self.assertFalse(self.visible())
        self.assertIsNone(p.stats_payload)

    def test_loss_of_actual_choice_scene_clears_partial_ranks(self):
        self.deliver_partial(self.unresolved(scene='unknown'))
        self.assertFalse(self.visible())
        self.assertIsNone(self.p.stats_payload)

    def test_conflicting_round_cannot_retain_partial_ranks(self):
        self.deliver_partial(self.unresolved(stage='3-2'))
        self.assertFalse(self.visible())
        self.assertIsNone(self.p.stats_payload)

    def test_invalidated_partial_retry_token_cannot_restore_ranks(self):
        self.deliver_partial(self.unresolved(), before_delivery=self.p.invalidate)
        self.assertFalse(self.visible())
        self.assertIsNone(self.p.stats_payload)

    def test_stale_partial_retry_cannot_retain_ranks(self):
        self.deliver_partial(self.unresolved(),
                             before_delivery=lambda: setattr(self, 'clock', 101.501))
        self.assertFalse(self.visible())
        self.assertIsNone(self.p.stats_payload)

    def start_late_ocr_check(self):
        # OCR completes after another verified frame has been accepted. Hold
        # its pixel callback so a further normal capture can overtake it too.
        observation = deepcopy(self.p.last_observation)
        observation.update(elapsed_ms=1, image_size=self.frame.size)
        for card in observation['cards']:
            card['raw_text'] = '应急护甲 I'
            card['resolution']['name'] = '应急护甲 I'
        with patch.object(self.p.vision, 'analyze_fast', return_value=observation), \
             patch('app.tracked_signature', return_value=self.signature):
            self.p.analyze(self.frame, True)
            work, ocr_done, _ = self.jobs.pop(0)
            recognized = work()
        newer = Image.new('RGB', self.frame.size)
        self.p.accept_frame((newer, self.binding), False,
                            (([], None), self.signature), self.clock)
        ocr_done(recognized)
        self.assertEqual(len(self.jobs), 1)

    def test_new_same_frame_during_ocr_pixel_check_does_not_clear_ranks(self):
        self.start_late_ocr_check()
        _, checked, _ = self.jobs.pop(0)
        self.clock += .1
        newest = Image.new('RGB', self.frame.size)
        self.p.accept_frame((newest, self.binding), False,
                            (([], None), self.signature), self.clock)
        checked(self.signature)
        self.assertTrue(self.visible(), 'A newer identical frame cleared confirmed ranks')
        self.assertIs(self.p.stats_payload, self.payload)
        self.assertEqual(len(self.jobs), 1, 'The newest frame must be checked before publishing OCR')
        _, newest_checked, _ = self.jobs.pop(0)
        newest_checked(self.signature)
        self.assertTrue(self.visible())
        self.assertIs(self.p.stats_payload, self.payload)
        self.assertFalse(self.p.ocr_busy)

    def test_newest_changed_frame_rejects_overtaken_ocr(self):
        self.start_late_ocr_check()
        _, checked, _ = self.jobs.pop(0)
        # No established observation is available to validate the newest image
        # in this scenario; the OCR continuation must inspect it itself.
        self.p.last_frame = Image.new('RGB', self.frame.size)
        checked(self.signature)
        self.assertEqual(len(self.jobs), 1)
        _, newest_checked, _ = self.jobs.pop(0)
        newest_checked(TextSignature((np.zeros((8, 20), dtype=bool),)))
        self.assertFalse(self.visible())
        self.assertIsNone(self.p.stats_payload)

    def test_overtaking_item_frame_cannot_publish_old_augment_ocr(self):
        # The first augment OCR has no established observation yet. A newer
        # item proposal must be checked even though the item branch cannot
        # start its own OCR until the shared engine becomes available.
        observation=deepcopy(self.p.last_observation)
        observation.update(elapsed_ms=1,image_size=self.frame.size)
        for card in observation['cards']:
            card['raw_text']='应急护甲 I'
            card['resolution']['name']='应急护甲 I'
        self.p.invalidate()
        self.p.last_frame=self.frame
        newest=Image.new('RGB',self.frame.size,'red')
        boxes=[(240+i*300,750,440+i*300,950) for i in range(5)]
        from item_vision import item_signature
        changed=TextSignature((np.zeros((8,20),dtype=bool),))
        with patch.object(self.p.vision,'analyze_fast',return_value=observation), \
             patch('app.tracked_signature',side_effect=lambda frame,obs:self.signature if frame is self.frame else changed), \
             patch.object(self.p,'query_stats') as query:
            self.p.analyze(self.frame,True)
            work,ocr_done,_=self.jobs.pop(0)
            recognized=work()
            self.clock+=.1
            self.p.accept_frame((newest,self.binding),False,
                ((boxes,item_signature(newest,boxes)),None),self.clock)
            self.assertTrue(self.p.ocr_busy)
            self.assertEqual(self.jobs,[])
            ocr_done(recognized)
            self.assertEqual(query.call_count,0,'Old augment OCR queried ranks over a newer item frame')
            self.assertEqual(len(self.jobs),1,'The newer item frame must be verified before publishing OCR')
            work,checked,_=self.jobs.pop(0)
            checked(work())
            self.assertEqual(query.call_count,0)
            self.assertIsNone(self.p.stats_payload)
            self.assertFalse(self.visible())
            self.assertFalse(self.p.ocr_busy)

    def test_continuously_overtaken_checks_are_bounded_without_erasing_ranks(self):
        self.start_late_ocr_check()
        for _ in range(3):
            self.assertEqual(len(self.jobs), 1)
            _, checked, _ = self.jobs.pop(0)
            newest = Image.new('RGB', self.frame.size)
            self.p.accept_frame((newest, self.binding), False,
                                (([], None), self.signature), self.clock)
            checked(self.signature)
        self.assertEqual(self.jobs, [], 'Pixel rechecks must have a finite retry budget')
        self.assertFalse(self.p.ocr_busy)
        self.assertTrue(self.visible())
        self.assertIs(self.p.stats_payload, self.payload)

    def test_forty_same_frames_with_held_callbacks_have_no_qt_hide_show_events(self):
        events = []

        class VisibilityObserver(QObject):
            def eventFilter(self, widget, event):
                if event.type() in (QEvent.Type.Show, QEvent.Type.Hide):
                    events.append((widget, event.type()))
                return False

        observer = VisibilityObserver()
        for label in self.p.overlays:
            label.installEventFilter(observer)
        try:
            for _ in range(40):
                self.clock += .6
                self.p.tick()
                self.assertEqual(len(self.jobs), 1)
                self.clock += 1.0
                self.p.tick()
                self.assertTrue(self.visible())
                _, capture_done, _ = self.jobs.pop(0)
                capture_done(((self.frame, self.binding), self.clock))
                _, inspect_done, _ = self.jobs.pop(0)
                inspect_done((([], None), self.signature))
                self.assertTrue(self.visible())
                self.assertEqual(self.jobs, [])
                self.assertIsNone(self.p.rank_capture_started)
            self.assertEqual(events, [], 'Unchanged frames generated Qt show/hide transitions')
        finally:
            for label in self.p.overlays:
                label.removeEventFilter(observer)


if __name__ == '__main__':
    unittest.main()
