"""Public Companion/ItemController seams, with only capture/native boundaries mocked."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from app import QApplication
from selection_controller import SelectionController
import test_game_resource_inputs as fixtures
from test_selection_controller import CATALOG, LAYOUT, observation


class SelectionIntegrationReviewTests(unittest.TestCase):
    response = fixtures.GameResourceInputTests.response
    flush = fixtures.GameResourceInputTests.flush
    tearDown = fixtures.GameResourceInputTests.tearDown

    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        fixtures.GameResourceInputTests.setUp(self)
        self.flush()
        self.time = 100.0
        self.binding = SimpleNamespace(hwnd=100, pid=8, process='MuMuNxDevice.exe',
            rect=(0,0,3840,2160), dpi=144, minimized=False)
        self.p.binding = self.binding
        self.stack.enter_context(patch('app.win.describe', return_value=self.binding))
        self.stack.enter_context(patch('app.win.foreground_root', return_value=100))
        self.stack.enter_context(patch.object(self.p, 'panel_open', return_value=False))
        self.p.catalog_loaded({'data': deepcopy(CATALOG)}, offline=True)
        self.flush()
        self.p.selections = SelectionController(self.p.session.session_id, self.p.entity_resolver,
            verified_layouts=(LAYOUT,), win_api=__import__('win_capture'), clock=lambda:self.time,
            on_selected=self.p.selection_confirmed)
        self.p.selection_tracker = self.p.selections.tracker
        self.stack.enter_context(patch.object(self.p, 'query_stats'))
        self.stack.enter_context(patch.object(self.p, 'display_overlays'))
        self.stack.enter_context(patch.object(self.p.items, 'render'))
        self.stack.enter_context(patch.object(self.p.items, 'start_queries'))

    def run_one(self):
        function, done, failed = self.pending.pop(0)
        try: result = function()
        except Exception as exc: failed(str(exc))
        else: done(result)

    def real_format_observation(self, stage='2-1'):
        obs = observation()
        # Vision/choice_reader return a stage string, not a status/value dict.
        obs['round'] = stage
        obs['image_size'] = (3840,2160)
        obs['elapsed_ms'] = 1
        for card in obs['cards']: card['raw_text'] = card['resolution']['name']
        return obs

    def test_actual_app_round_string_is_preserved_and_new_stage_changes_offer_flow(self):
        p = self.p; p.last_capture = self.time
        p.observed(self.real_format_observation(), True)
        first = p.selections.snapshot
        self.assertEqual(first.round, '2-1')
        self.time += .2; p.last_capture = self.time
        p.observed(self.real_format_observation('3-2'), True)
        self.assertNotEqual(first.flow, p.selections.snapshot.flow)

    def test_verified_unchanged_capture_refreshes_offer_without_requiring_extra_ocr(self):
        p = self.p; p.last_capture = self.time
        obs = self.real_format_observation()
        p.observed(obs, True)
        p.session.set_choices('2-1', ('42','43','44'))
        p.stats_payload = {'live':True, 'token':p.session.token(), 'rows':[]}
        p.signature = object()
        self.time += 1.2
        frame = Image.new('RGB',(3840,2160))
        with patch('app.unchanged', return_value=True), patch.object(p.items,'ingest',return_value=False):
            p.accept_frame((frame,self.binding), False, ([],p.signature), self.time)
        self.assertEqual(p.last_capture, self.time)
        self.assertEqual(p.selections.snapshot.frame_time, self.time)

    def test_item_only_probe_passes_its_own_fresh_frame_time_to_selection_controller(self):
        p = self.p
        p.last_capture = 0  # No recent full augment screenshot outside augment stages.
        frame = Image.new('RGB',(3840,2160))
        boxes = [(1184,1604,1572,2000),(1744,1604,2132,2000),(2304,1604,2692,2000)]
        obs = {'scene':'item_candidates', 'image_size':frame.size, 'cards':[]}
        for slot, (box,row) in enumerate(zip(boxes,CATALOG['equip'])):
            left,top,right,bottom=box
            obs['cards'].append({'slot':slot,'box':[[left,top],[right,top],[right,bottom],[left,bottom]],
                'resolution':{'status':'resolved', **row, 'candidates':[dict(row)]}})
        with patch('item_controller.time.monotonic', side_effect=lambda:self.time), \
             patch('item_controller.capture_item_region', return_value=(frame,self.binding)), \
             patch('item_controller.inspect_items', return_value=(boxes,None)), \
             patch('item_controller.analyze_items', return_value=obs):
            p.items.tick()
            self.assertEqual(len(self.pending), 1)
            self.run_one()  # Existing capture queue -> existing OCR queue.
            self.assertEqual(len(self.pending), 1)
            self.run_one()
        self.assertIsNotNone(p.selections.snapshot)
        self.assertEqual(p.selections.snapshot.frame_time, self.time)

    def test_switching_augment_to_items_does_not_scene_exit_the_new_item_offer(self):
        p = self.p
        p.selections = SelectionController(p.session.session_id,p.entity_resolver,
            verified_layouts=(LAYOUT,'s18-items-radiant-3-v1'),
            win_api=__import__('win_capture'),clock=lambda:self.time)
        p.selection_tracker = p.selections.tracker
        p.last_capture=self.time
        p.observed(self.real_format_observation(),True)
        self.assertIsNotNone(p.selection_tracker.offer)
        frame=Image.new('RGB',(3840,2160))
        boxes=[(1184,1604,1572,2000),(1744,1604,2132,2000),(2304,1604,2692,2000)]
        obs={'scene':'item_candidates','image_size':frame.size,'cards':[]}
        for slot,(box,row) in enumerate(zip(boxes,CATALOG['equip'])):
            left,top,right,bottom=box
            obs['cards'].append({'slot':slot,'box':[[left,top],[right,top],[right,bottom],[left,bottom]],
                'resolution':{'status':'resolved',**row,'candidates':[dict(row)]}})
        with patch('item_controller.time.monotonic',side_effect=lambda:self.time),patch('item_controller.analyze_items',return_value=obs):
            p.items.ingest(frame,self.binding,prepared=(boxes,None),frame_time=self.time)
            self.run_one()
        self.assertEqual(p.selections.snapshot.layout_id,'s18-items-radiant-3-v1')
        self.assertIsNotNone(p.selection_tracker.offer)

    def test_side_key_equipment_route_keeps_capture_time_after_slow_scene_read(self):
        p=self.p
        frame=Image.new('RGB',(3840,2160))
        boxes=[(1184,1604,1572,2000),(1744,1604,2132,2000),(2304,1604,2692,2000)]
        obs={'scene':'item_candidates','image_size':frame.size,'cards':[]}
        for slot,(box,row) in enumerate(zip(boxes,CATALOG['equip'])):
            left,top,right,bottom=box
            obs['cards'].append({'slot':slot,'box':[[left,top],[right,top],[right,bottom],[left,bottom]],
                'resolution':{'status':'resolved',**row,'candidates':[dict(row)]}})
        def slow_scene_read(_):
            self.time+=1.5
            return {'route':'equipment_stats','status':'unknown'}
        p.conditions.reader=Mock()
        p.conditions.reader.read.side_effect=slow_scene_read
        with patch('condition_controller.QTimer.singleShot',side_effect=lambda _,fn:fn()), \
             patch('condition_controller.time.monotonic',side_effect=lambda:self.time), \
             patch('condition_controller.capture_image',return_value=(frame,self.binding)), \
             patch('item_controller.inspect_items',return_value=(boxes,None)), \
             patch('item_controller.analyze_items',return_value=obs):
            p.conditions.trigger()
            self.run_one()  # Capture at t=100, no subsequent screenshot.
            self.run_one()  # Scene routing completes at t=101.5.
            self.run_one()  # Existing item OCR consumes that same t=100 frame.
        # Relabeling this old frame as t=101.5 must not satisfy freshness.
        self.assertIsNone(p.selections.snapshot)


if __name__=='__main__':
    unittest.main()
