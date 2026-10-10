"""A first manual request survives a real blocked automatic probe.

Hidden native Qt widgets and actual Companion.submit/worker pools are used.
Only capture pixels, OCR output, Win32 identity and HTTP transport are controlled;
this does not claim game OCR, physical side-button or MuMu composition coverage.
"""
from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import ANY, Mock, patch

import httpx
from PIL import Image
from app import QApplication, Companion
from dataj import DataJ
from test_game_resource_inputs import CATALOG


class _FixtureDataJClock:
    """Advance only mocked source pacing; Qt and condition deadlines stay real."""
    def __init__(self):
        self._lock = threading.Lock()
        self._offset = 0.0
        self._sleeps = []

    def monotonic(self):
        with self._lock:
            return time.monotonic() + self._offset

    def time(self):
        return time.time()

    def sleep(self, seconds):
        if seconds < 0:
            raise ValueError('sleep length must be non-negative')
        with self._lock:
            self._offset += seconds
            self._sleeps.append(seconds)

    @property
    def sleeps(self):
        with self._lock:
            return list(self._sleeps)


class ConditionTriggerPriorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        self.stack = ExitStack()
        self.tmp = tempfile.TemporaryDirectory()
        self.release_probe = threading.Event()
        self.probe_entered = threading.Event()
        self.capture_entered = threading.Event()
        self.capture_calls = []
        self.http_calls = []
        self.transport_attempts = []
        self.non_mock_attempts = []
        self.pacing_clock = _FixtureDataJClock()
        self.stack.enter_context(patch('dataj.time', self.pacing_clock))
        send = httpx.Client.send

        def mock_only_send(client, request, *args, **kwargs):
            transport = client._transport_for_url(request.url)
            attempt = {'method': request.method, 'url': str(request.url),
                       'mock': isinstance(transport, httpx.MockTransport)}
            self.transport_attempts.append(attempt)
            if not attempt['mock']:
                self.non_mock_attempts.append(attempt)
                raise AssertionError('Condition fixture blocks non-Mock HTTPX transport')
            return send(client, request, *args, **kwargs)

        self.stack.enter_context(patch.object(httpx.Client, 'send', mock_only_send))
        self.gui_thread = threading.get_ident()
        self.now = [10.0]
        self.binding = SimpleNamespace(hwnd=7, pid=1, process='MuMuNxDevice.exe',
                                       rect=(0, 0, 1920, 1080), dpi=96)
        self.current_binding = self.binding
        self.foreground = 7
        self.image = Image.new('RGB', (1920, 1080), (13, 31, 53))
        for module in ('app', 'dataj', 'comp_browser'):
            self.stack.enter_context(patch(module + '.STATE_DIR', Path(self.tmp.name)))
        db = Path(self.tmp.name) / 'cache.sqlite'
        transport = httpx.MockTransport(self.response)
        class Source(DataJ):
            def __init__(adapter, patch='18.2a', *, budget=None):
                super().__init__(patch=patch, db=db, transport=transport, budget=budget)
        self.stack.enter_context(patch('app.DataJ', Source))
        self.stack.enter_context(patch('app.Vision.prepare'))
        self.stack.enter_context(patch('app.game_windows', return_value=[]))
        self.p = Companion(offline=True, offline_catalog=deepcopy(CATALOG))
        self.p.timer.stop()
        self.wait(lambda: not self.p.jobs)
        self.p.binding = self.binding
        self.p.geometry = (self.binding.rect, self.binding.dpi)
        self.stack.enter_context(patch('condition_controller.win.describe', side_effect=lambda _: self.current_binding))
        self.stack.enter_context(patch('condition_controller.win.foreground_root', side_effect=lambda: self.foreground))
        self.stack.enter_context(patch.object(self.p, 'showNormal'))
        self.stack.enter_context(patch.object(self.p, 'raise_'))
        self.stack.enter_context(patch.object(self.p, 'activateWindow'))
        self.reader = Mock()
        self.reader.read.return_value = {'route': 'detail', 'status': 'resolved',
                                        'entity': deepcopy(CATALOG['equip'][0]), 'candidates': []}
        self.p.conditions.reader = self.reader
        self.stack.enter_context(patch('condition_controller.capture_image', side_effect=self.condition_capture))
        self.stack.enter_context(patch('item_controller.capture_item_region', side_effect=self.blocked_probe))
        self.stack.enter_context(patch('item_controller.inspect_items', return_value=([], ())))

    def response(self, request):
        self.http_calls.append(request)
        data = ({'comps': []} if request.method == 'POST' else deepcopy(CATALOG)
                if request.url.path.endswith('/gamedata') else [])
        return httpx.Response(200, json={'success': True, 'code': 200, 'data': data})

    def wait(self, predicate, timeout=1.5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.qt.processEvents()
            if predicate():return
            time.sleep(.001)
        self.assertTrue(predicate(), 'Expected condition was not reached before the bounded Qt wait')

    def settled(self):
        return not (self.p.jobs or self.p.capture_pending or self.p.ocr_busy or self.p.stage_probe_pending)

    def blocked_probe(self, binding):
        self.assertNotEqual(threading.get_ident(), self.gui_thread)
        self.probe_entered.set()
        if not self.release_probe.wait(3):
            raise RuntimeError('Test did not release automatic probe')
        return self.image, binding

    def condition_capture(self, binding):
        self.capture_calls.append((binding, threading.get_ident()))
        self.capture_entered.set()
        return self.image, binding

    def start_item_probe(self):
        self.p.items.tick()
        self.assertTrue(self.probe_entered.wait(1), 'Actual item capture worker did not start')
        self.assertTrue(self.p.items.probing and self.p.capture_pending)

    def start_stage_probe(self, stage=None):
        def captured(binding):
            self.blocked_probe(binding)
            return self.image
        self.stack.enter_context(patch('app.capture_stage', side_effect=captured))
        self.stack.enter_context(patch.object(self.p.vision, 'read_round_crop', return_value=stage))
        self.p.probe_stage()
        self.assertTrue(self.probe_entered.wait(1), 'Actual stage capture worker did not start')
        self.assertTrue(self.p.stage_probe_pending)

    def tearDown(self):
        self.release_probe.set()
        self.p.conditions.cancel_pending()
        self.wait(self.settled, timeout=3)
        for pool in (self.p.capture_pool, self.p.ocr_pool, self.p.network, self.p.hex_network):
            self.assertTrue(pool.waitForDone(3000), 'Actual Companion worker did not terminate')
        self.qt.processEvents()
        self.p.shutdown()
        self.p.deleteLater()
        self.qt.processEvents()
        self.stack.close()
        self.tmp.cleanup()
        self.image.close()
        self.assertEqual(self.non_mock_attempts, [], 'Every fixture HTTPX request must use MockTransport')

    def test_first_condition_request_during_automatic_item_probe_is_not_lost(self):
        self.start_item_probe()
        self.p.browser.input_bar.read.click()
        self.assertEqual(self.capture_calls, [])
        self.release_probe.set()
        self.wait(self.capture_entered.is_set)
        self.wait(lambda: not self.p.jobs and not self.p.ocr_busy)
        self.assertEqual(len(self.capture_calls), 1, 'The first explicit request must capture exactly once')
        self.assertNotEqual(self.capture_calls[0][1], self.gui_thread)
        self.assertEqual((self.p.browser.scope[0], self.p.browser.scope[1]['id']), ('equip', '41806'))
        self.assertEqual(self.p.selected_resources.events, ())
        self.reader.read.assert_called_once_with(self.image)
        body = json.loads(next(call.content for call in self.http_calls if call.method == 'POST'))
        self.assertEqual((body['setId'], body['version']), (18, '18.2a'))
        self.assertEqual(body['filter']['rules'][0]['targetId'], '41806')
        self.assertFalse(body['filter']['rules'][0]['nameMatch'])

    def test_first_condition_request_during_automatic_stage_probe_is_not_lost(self):
        self.start_stage_probe()
        self.p.browser.input_bar.read.click()
        self.release_probe.set()
        self.wait(self.capture_entered.is_set)
        self.wait(lambda: not self.p.jobs and not self.p.ocr_busy)
        self.assertEqual(len(self.capture_calls), 1)
        self.assertEqual((self.p.browser.scope[0], self.p.browser.scope[1]['id']), ('equip', '41806'))
        self.assertEqual(self.p.selected_resources.events, ())

    def test_configured_side_button_during_item_probe_keeps_foreground_guards_and_runs_once(self):
        self.stack.enter_context(patch('app.game_windows', return_value=[self.binding]))
        self.start_item_probe()
        configured = self.p.mouse_button.currentData()
        self.p.mouse_capture('not-the-configured-button', 7)
        self.p.mouse_capture(configured, 99)
        self.p.mouse_capture(configured, 7)
        self.release_probe.set()
        self.wait(self.capture_entered.is_set)
        self.wait(lambda: not self.p.jobs and not self.p.ocr_busy)
        self.assertEqual(len(self.capture_calls), 1)
        self.assertEqual(self.p.browser.scope[1]['id'], '41806')
        self.assertEqual(self.p.selected_resources.events, ())

    def test_repeated_requests_during_probe_are_coalesced_into_one_capture(self):
        self.start_item_probe()
        for _ in range(6):
            self.p.browser.input_bar.read.click()
        self.assertIn('等待', self.p.browser.input_bar.note.text())
        self.release_probe.set()
        self.wait(self.capture_entered.is_set)
        self.wait(lambda: not self.p.jobs and not self.p.ocr_busy)
        self.assertEqual(len(self.capture_calls), 1)
        self.reader.read.assert_called_once_with(self.image)
        self.assertEqual(self.p.selected_resources.events, ())

    def test_new_explicit_request_after_filter_change_replaces_stale_waiting_request(self):
        self.start_item_probe()
        self.p.browser.input_bar.read.click()
        self.p.browser.set_filter('hex', CATALOG['hex'][0])
        # No Qt event pumping between the changed input and the new click: the
        # explicit intent must survive even before the 25 ms pending timer runs.
        self.p.browser.input_bar.read.click()
        self.release_probe.set()
        self.wait(self.capture_entered.is_set)
        self.wait(self.settled)
        self.assertEqual(len(self.capture_calls), 1)
        self.reader.read.assert_called_once_with(self.image)
        self.assertEqual((self.p.browser.scope[0], self.p.browser.scope[1]['id']), ('equip', '41806'))
        self.assertEqual(self.p.selected_resources.events, ())

    def test_explicit_request_after_expired_waiting_deadline_starts_a_new_wait(self):
        self.stack.enter_context(patch('condition_controller.time', SimpleNamespace(monotonic=lambda: self.now[0])))
        self.start_item_probe()
        self.p.browser.input_bar.read.click()
        self.now[0] = 12.01
        # This click is a new intent after expiry, before the timer observes it.
        self.p.browser.input_bar.read.click()
        self.now[0] = 13.9
        self.qt.processEvents()
        self.assertIn('等待', self.p.browser.input_bar.note.text())
        self.release_probe.set()
        self.wait(self.capture_entered.is_set)
        self.wait(self.settled)
        self.assertEqual(len(self.capture_calls), 1)
        self.reader.read.assert_called_once_with(self.image)
        self.assertEqual(self.p.browser.scope[1]['id'], '41806')
        self.assertEqual(self.p.selected_resources.events, ())

    def test_waiting_augment_and_equipment_routes_reuse_one_frame_exclusively(self):
        # Observe the exclusive public dispatch boundary; subsequent ranking
        # and scene recognition are covered by their own existing suites.
        with patch.object(self.p, 'captured') as augment, patch.object(self.p.items, 'ingest') as equipment:
            for route in ('augment_stats', 'equipment_stats'):
                with self.subTest(route=route):
                    self.release_probe.clear();self.probe_entered.clear();self.capture_entered.clear()
                    self.capture_calls.clear();self.reader.reset_mock()
                    augment.reset_mock();equipment.reset_mock()
                    self.p.items.last_probe = float('-inf')
                    self.p.once_active=False;self.p.once_ocr_pending=False
                    self.reader.read.return_value={'route': route, 'status': 'unknown'}
                    self.start_item_probe()
                    self.p.browser.input_bar.read.click()
                    self.assertEqual(self.capture_calls, [])
                    self.release_probe.set()
                    self.wait(self.capture_entered.is_set)
                    self.wait(self.settled)
                    self.assertEqual(len(self.capture_calls), 1)
                    self.reader.read.assert_called_once_with(self.image)
                    if route=='augment_stats':
                        augment.assert_called_once_with((self.image,self.binding),True,captured_at=ANY)
                        equipment.assert_not_called()
                    else:
                        equipment.assert_called_once_with(self.image,self.binding,force=True,frame_time=ANY)
                        augment.assert_not_called()
                    self.assertIsNone(self.p.browser.scope)
                    self.assertEqual(self.p.selected_resources.events, ())
                    self.p.showNormal.assert_not_called()
                    self.p.raise_.assert_not_called()
                    self.p.activateWindow.assert_not_called()

    def test_repeated_requests_do_not_extend_timeout_or_clear_background_busy_flags(self):
        self.p.browser.set_filter('hex', CATALOG['hex'][0])
        self.wait(lambda: not self.p.jobs)
        before = deepcopy(self.p.browser.scope)
        self.stack.enter_context(patch('condition_controller.time', SimpleNamespace(monotonic=lambda: self.now[0])))
        self.start_item_probe()
        self.p.browser.input_bar.read.click()
        self.now[0] = 11.9
        for _ in range(6):
            self.p.browser.input_bar.read.click()
        self.now[0] = 12.01
        self.wait(lambda: '超时' in self.p.mark.button.accessibleName())
        self.assertIn('原检索条件已保留', self.p.browser.input_bar.note.text())
        self.assertEqual(self.p.browser.scope, before)
        self.assertTrue(self.p.items.probing and self.p.capture_pending)
        self.release_probe.set()
        self.wait(lambda: not self.p.jobs)
        self.assertEqual(self.capture_calls, [])
        self.reader.read.assert_not_called()

    def test_context_changes_cancel_waiting_request_before_any_condition_capture(self):
        for change in ('foreground', 'geometry', 'dpi', 'closed', 'input', 'new_game', 'patch', 'reader'):
            with self.subTest(change=change):
                self.release_probe.clear();self.probe_entered.clear()
                self.foreground = 7;self.current_binding = self.binding
                self.p.binding = self.binding
                self.p.conditions.reader = self.reader
                self.p.items.last_probe = float('-inf')
                self.start_item_probe()
                self.p.browser.input_bar.read.click()
                self.assertIn('等待', self.p.browser.input_bar.note.text())
                if change == 'foreground': self.foreground = 99
                elif change == 'geometry':
                    self.current_binding = SimpleNamespace(**{**vars(self.binding), 'rect': (20, 0, 1940, 1080)})
                elif change == 'dpi': self.current_binding = SimpleNamespace(**{**vars(self.binding), 'dpi': 120})
                elif change == 'closed': self.current_binding = None
                elif change == 'input': self.p.browser.clear_filter()
                elif change == 'new_game': self.p.new_game()
                elif change == 'patch':
                    self.p.patch.addItem('18.3');self.p.patch.setCurrentText('18.3')
                    self.p.change_patch()
                else: self.p.conditions.configure()
                self.release_probe.set()
                self.wait(lambda: not self.p.jobs, timeout=3 if change == 'patch' else 1.5)
                self.assertEqual(self.capture_calls, [], 'A stale request must not take a new screenshot')
                self.reader.read.assert_not_called()
                self.assertEqual(self.p.selected_resources.events, ())

    def test_patch_reload_with_delayed_mock_rank_keeps_stale_request_cancelled(self):
        import condition_controller
        import dataj

        self.p.browser.clear_filter()
        self.wait(lambda: not self.p.jobs)
        previous = self.p.adapter
        delayed = threading.Event()
        handler = previous.transport.handler

        def delayed_response(request):
            if (request.url.path.endswith('/comp/rank')
                and request.url.params.get('gameVersion') == '18.3'):
                delayed.set()
                time.sleep(.25)
            return handler(request)

        self.stack.enter_context(patch.object(previous.transport, 'handler', delayed_response))
        self.start_item_probe()
        self.p.browser.input_bar.read.click()
        self.assertIn('等待', self.p.browser.input_bar.note.text())
        self.p.patch.addItem('18.3');self.p.patch.setCurrentText('18.3')
        started = time.monotonic()
        self.p.change_patch()
        self.release_probe.set()
        self.wait(lambda: not self.p.jobs, timeout=3)
        elapsed = time.monotonic() - started

        self.assertTrue(delayed.is_set(), 'The actual replacement rank request must reach the delayed Mock response')
        self.assertEqual(self.p.adapter.patch, '18.3')
        self.assertIsNot(self.p.adapter, previous)
        self.assertIs(self.p.adapter.budget, previous.budget)
        self.assertIs(self.p.adapter.transport, previous.transport)
        self.assertIsInstance(self.p.adapter.transport, httpx.MockTransport)
        paths = [(request.url.path, request.url.params.get('gameVersion')) for request in self.http_calls]
        self.assertIn(('/api/web/gamedata', None), paths)
        self.assertIn(('/api/web/stats/hex', '18.3'), paths)
        self.assertIn(('/api/web/comp/rank', '18.3'), paths)
        self.assertEqual(self.capture_calls, [], 'The canceled request must not capture after patch reload')
        self.reader.read.assert_not_called()
        self.assertIsNone(self.p.conditions.pending)
        self.assertEqual(self.p.selected_resources.events, ())
        self.assertIs(dataj.time, self.pacing_clock)
        self.assertGreater(sum(self.pacing_clock.sleeps), 1.5)
        self.assertIs(condition_controller.time, time)
        self.assertIs(self.wait.__func__.__globals__['time'], time)
        self.assertGreaterEqual(elapsed, .25, 'Mock response and Qt waits must still use the real clock')
        self.assertTrue(self.transport_attempts, 'The fixture transport guard must observe actual HTTPX sends')
        self.assertTrue(all(attempt['mock'] for attempt in self.transport_attempts))
        self.assertEqual(self.non_mock_attempts, [])

    def test_ordinary_session_invalidation_does_not_discard_waiting_detail(self):
        self.start_item_probe()
        self.p.browser.input_bar.read.click()
        self.p.invalidate()
        self.release_probe.set()
        self.wait(self.capture_entered.is_set)
        self.wait(lambda: not self.p.jobs and not self.p.ocr_busy)
        self.assertEqual(len(self.capture_calls), 1)
        self.assertEqual(self.p.browser.scope[1]['id'], '41806')
        self.assertEqual(self.p.selected_resources.events, ())

    def test_failed_background_item_and_stage_probe_still_release_one_manual_request(self):
        for kind in ('item', 'stage'):
            with self.subTest(kind=kind):
                self.release_probe.clear();self.probe_entered.clear();self.capture_entered.clear()
                self.capture_calls.clear();self.reader.reset_mock()
                self.p.items.last_probe = float('-inf')
                def failed(binding):
                    self.blocked_probe(binding)
                    raise RuntimeError('Independent background capture failure')
                if kind == 'item':
                    with patch('item_controller.capture_item_region', side_effect=failed):
                        self.start_item_probe()
                        self.p.browser.input_bar.read.click()
                        self.release_probe.set()
                        self.wait(self.capture_entered.is_set)
                        self.wait(lambda: not self.p.jobs and not self.p.ocr_busy)
                else:
                    with patch('app.capture_stage', side_effect=failed):
                        self.p.probe_stage()
                        self.assertTrue(self.probe_entered.wait(1))
                        self.p.browser.input_bar.read.click()
                        self.release_probe.set()
                        self.wait(self.capture_entered.is_set)
                        self.wait(lambda: not self.p.jobs and not self.p.ocr_busy)
                self.assertEqual(len(self.capture_calls), 1)
                self.reader.read.assert_called_once_with(self.image)
                self.assertEqual(self.p.selected_resources.events, ())

    def test_repeated_manual_capture_and_ocr_do_not_queue_another_request(self):
        for phase in ('capture', 'ocr'):
            with self.subTest(phase=phase):
                entered, released = threading.Event(), threading.Event()
                self.capture_calls.clear();self.reader.reset_mock()
                original_capture = self.condition_capture
                def held_capture(binding):
                    value = original_capture(binding)
                    if phase == 'capture':
                        entered.set()
                        if not released.wait(3): raise RuntimeError('Manual capture was not released')
                    return value
                def held_read(image):
                    if phase == 'ocr':
                        entered.set()
                        if not released.wait(3): raise RuntimeError('Manual OCR was not released')
                    return self.reader.read.return_value
                self.reader.read.side_effect = held_read
                try:
                    with patch('condition_controller.capture_image', side_effect=held_capture):
                        self.p.browser.input_bar.read.click()
                        self.wait(entered.is_set)
                        for _ in range(6): self.p.browser.input_bar.read.click()
                        released.set()
                        self.wait(lambda: not self.p.jobs and not self.p.ocr_busy)
                    self.assertEqual(len(self.capture_calls), 1)
                    self.reader.read.assert_called_once_with(self.image)
                finally:
                    released.set();self.reader.read.side_effect = None

    def test_stage_two_one_boundary_cancels_waiting_request_and_preserves_uncertain_guard(self):
        self.p.browser.set_filter('hex', CATALOG['hex'][0], can_confirm=True)
        self.wait(lambda: not self.p.jobs)
        self.p.browser.input_bar.confirm.click()
        self.p.last_probe_stage = '4-1'
        self.start_stage_probe('2-1')
        self.p.browser.input_bar.read.click()
        self.assertIn('等待', self.p.browser.input_bar.note.text())
        self.release_probe.set()
        self.wait(lambda: not self.p.jobs)
        self.assertTrue(self.p.resources_uncertain)
        self.assertEqual(self.capture_calls, [])
        self.reader.read.assert_not_called()
        self.assertEqual([(event.kind, event.entity_id) for event in self.p.selected_resources.events], [('hex', '20778')])

    def test_wrong_side_button_foreground_or_target_does_not_create_a_waiting_request(self):
        self.start_item_probe()
        configured = self.p.mouse_button.currentData()
        self.stack.enter_context(patch('app.game_windows', return_value=[self.binding]))
        self.p.mouse_capture('wrong', 7)
        self.p.mouse_capture(configured, 99)
        self.foreground = 99
        self.p.mouse_capture(configured, 7)
        self.foreground = 7
        other = SimpleNamespace(**{**vars(self.binding), 'hwnd': 88, 'pid': 99})
        with patch('app.game_windows', return_value=[other]): self.p.mouse_capture(configured, 7)
        self.release_probe.set()
        self.wait(lambda: not self.p.jobs)
        self.assertEqual(self.capture_calls, [])
        self.reader.read.assert_not_called()

    def test_shutdown_cancels_waiting_request_before_background_completion(self):
        self.start_item_probe()
        self.p.browser.input_bar.read.click()
        self.release_probe.set()
        self.p.shutdown()
        self.qt.processEvents()
        self.assertEqual(self.capture_calls, [])
        self.reader.read.assert_not_called()

    def test_geometry_change_while_resuming_does_not_rebind_waiting_request(self):
        self.start_item_probe()
        self.p.browser.input_bar.read.click()
        moved = SimpleNamespace(**{**vars(self.binding), 'rect': (20, 0, 1940, 1080)})
        def moved_after_describe(_):
            current = self.current_binding
            self.current_binding = moved
            return current
        with patch('condition_controller.win.describe', side_effect=moved_after_describe):
            self.release_probe.set()
            self.assertTrue(self.p.capture_pool.waitForDone(1000))
            self.wait(self.settled)
        self.assertEqual(self.capture_calls, [], 'A waiting request must keep its original geometry token')
        self.reader.read.assert_not_called()

    def start_ordinary_automatic_capture(self, failure=None, legacy_once=False):
        self.binding.minimized=False
        self.release_probe.clear();self.probe_entered.clear();self.capture_entered.clear()
        self.automatic_capture_calls=[]
        self.automatic_read=Mock(return_value={'scene':'unknown','cards':[],'round':None})
        def capture(binding):
            self.automatic_capture_calls.append(threading.get_ident())
            result=self.blocked_probe(binding)
            if failure=='capture':raise RuntimeError('Independent ordinary automatic capture failure')
            return result
        self.stack.enter_context(patch('app.capture_image',side_effect=capture))
        self.stack.enter_context(patch('app.may_be_choice',return_value=False))
        self.stack.enter_context(patch('app.inspect_items',side_effect=RuntimeError('Independent automatic frame inspection failure') if failure=='inspect' else None,return_value=([],())))
        self.stack.enter_context(patch.object(self.p.vision,'analyze_fast',self.automatic_read))
        self.p.last_capture=0;self.p.last_ocr=0;self.p.next_ocr_allowed=0
        if legacy_once:
            self.p.capture_once();self.wait(self.probe_entered.is_set)
        else:
            self.p.tick()
            self.assertTrue(self.probe_entered.wait(1),'Ordinary automatic capture worker did not start')
        self.assertTrue(self.p.capture_pending and self.p.rank_capture_started is not None)
        self.assertFalse(self.p.items.probing or self.p.stage_probe_pending or self.p.conditions.active)
        self.assertEqual(self.p.once_active,legacy_once)

    def start_automatic_live_ocr(self, legacy_once=False, file_read=False, automatic=True):
        self.binding.minimized=False
        self.release_probe.clear();self.probe_entered.clear();self.capture_entered.clear()
        self.automatic_capture_calls=[]
        def capture(binding):
            self.automatic_capture_calls.append(threading.get_ident())
            return self.image,binding
        def recognize(image,catalog):
            self.assertNotEqual(threading.get_ident(),self.gui_thread)
            self.probe_entered.set()
            if not self.release_probe.wait(3):raise RuntimeError('Automatic OCR was not released')
            return {'scene':'unknown','cards':[],'round':None}
        self.stack.enter_context(patch('app.capture_image',side_effect=capture))
        self.stack.enter_context(patch('app.may_be_choice',return_value=False))
        self.stack.enter_context(patch('app.inspect_items',return_value=([],())))
        self.stack.enter_context(patch.object(self.p.vision,'analyze_fast',side_effect=recognize))
        self.stack.enter_context(patch.object(self.p.vision,'analyze',side_effect=recognize))
        self.p.automatic.setChecked(automatic)
        self.p.last_capture=0;self.p.last_ocr=0;self.p.next_ocr_allowed=0
        if file_read or not automatic:self.p.analyze(self.image,not file_read)
        elif legacy_once:self.p.capture_once()
        else:self.p.tick()
        self.wait(self.probe_entered.is_set)
        self.assertTrue(self.p.ocr_busy)
        self.assertEqual(self.p.ocr_live,not file_read)
        self.assertFalse(self.p.capture_pending or self.p.conditions.active or self.p.items.recognizing or self.p.stage_probe_pending)
        self.assertEqual(self.p.once_active,legacy_once)

    def assert_one_condition_after_background(self):
        self.release_probe.set()
        self.wait(self.capture_entered.is_set)
        self.wait(self.settled)
        self.assertEqual(len(self.capture_calls),1,'First explicit request must get one fresh manual capture')
        self.assertNotEqual(self.capture_calls[0][1],self.gui_thread)
        self.reader.read.assert_called_once_with(self.image)
        self.assertEqual((self.p.browser.scope[0],self.p.browser.scope[1]['id']),('equip','41806'))
        self.assertEqual(self.p.selected_resources.events,())

    def test_first_condition_request_during_ordinary_automatic_capture_is_not_lost(self):
        self.start_ordinary_automatic_capture()
        self.p.browser.input_bar.read.click()
        self.assert_one_condition_after_background()
        self.assertEqual(len(self.automatic_capture_calls),1)
        self.automatic_read.assert_not_called()

    def test_repeated_requests_during_ordinary_automatic_capture_are_coalesced(self):
        self.start_ordinary_automatic_capture()
        for _ in range(6):self.p.browser.input_bar.read.click()
        self.assert_one_condition_after_background()
        self.automatic_read.assert_not_called()

    def test_configured_side_button_during_ordinary_automatic_capture_keeps_foreground_guards(self):
        self.start_ordinary_automatic_capture()
        configured=self.p.mouse_button.currentData()
        self.stack.enter_context(patch('app.game_windows',return_value=[self.binding]))
        self.p.mouse_capture('wrong',7);self.p.mouse_capture(configured,99)
        self.foreground=99;self.p.mouse_capture(configured,7);self.foreground=7
        other=SimpleNamespace(**{**vars(self.binding),'hwnd':88,'pid':99})
        with patch('app.game_windows',return_value=[other]):self.p.mouse_capture(configured,7)
        self.assertIsNone(self.p.conditions.pending)
        self.p.mouse_capture(configured,7)
        self.assert_one_condition_after_background()
        self.automatic_read.assert_not_called()

    def test_failed_ordinary_automatic_capture_or_inspection_releases_one_condition_request(self):
        for phase in ('capture','inspect'):
            with self.subTest(phase=phase):
                self.capture_calls.clear();self.reader.reset_mock()
                self.start_ordinary_automatic_capture(failure=phase)
                self.p.browser.input_bar.read.click()
                self.assert_one_condition_after_background()
                self.automatic_read.assert_not_called()

    def test_legacy_one_shot_capture_and_ocr_do_not_queue_condition_request(self):
        for phase in ('capture','ocr'):
            with self.subTest(phase=phase):
                self.capture_calls.clear();self.reader.reset_mock()
                if phase=='capture':self.start_ordinary_automatic_capture(legacy_once=True)
                else:self.start_automatic_live_ocr(legacy_once=True)
                for _ in range(6):self.p.browser.input_bar.read.click()
                self.assertIsNone(self.p.conditions.pending)
                self.release_probe.set();self.wait(self.settled)
                self.assertEqual(self.capture_calls,[]);self.reader.read.assert_not_called()

    def test_first_condition_request_during_automatic_live_ocr_is_not_lost(self):
        self.start_automatic_live_ocr()
        self.p.browser.input_bar.read.click()
        self.assert_one_condition_after_background()
        self.assertEqual(len(self.automatic_capture_calls),1)

    def test_repeated_requests_during_automatic_live_ocr_are_coalesced(self):
        self.start_automatic_live_ocr()
        for _ in range(6):self.p.browser.input_bar.read.click()
        self.assert_one_condition_after_background()

    def test_pending_condition_after_automatic_ocr_precedes_another_automatic_capture(self):
        self.start_automatic_live_ocr()
        self.p.browser.input_bar.read.click()
        self.p.conditions.pending_timer.stop()
        self.release_probe.set();self.wait(lambda:not self.p.ocr_busy)
        self.p.last_capture=0
        self.p.tick()
        self.wait(self.capture_entered.is_set);self.wait(self.settled)
        self.assertEqual(len(self.automatic_capture_calls),1,'Pending manual request must preempt scheduled automatic capture')
        self.assertEqual(len(self.capture_calls),1);self.reader.read.assert_called_once_with(self.image)

    def test_nonautomatic_or_file_ocr_does_not_queue_condition_request(self):
        for file_read,automatic in ((False,False),(True,True)):
            with self.subTest(file_read=file_read,automatic=automatic):
                self.capture_calls.clear();self.reader.reset_mock()
                self.start_automatic_live_ocr(file_read=file_read,automatic=automatic)
                self.p.browser.input_bar.read.click()
                self.assertIsNone(self.p.conditions.pending)
                self.release_probe.set();self.wait(self.settled)
                self.assertEqual(self.capture_calls,[]);self.reader.read.assert_not_called()

    def test_context_change_during_automatic_capture_or_ocr_cancels_waiting_request(self):
        for phase in ('capture','ocr'):
            with self.subTest(phase=phase):
                self.capture_calls.clear();self.reader.reset_mock()
                if phase=='capture':self.start_ordinary_automatic_capture()
                else:self.start_automatic_live_ocr()
                self.p.browser.input_bar.read.click()
                self.assertIsNotNone(self.p.conditions.pending)
                self.p.browser.set_filter('hex',CATALOG['hex'][0])
                self.release_probe.set();self.wait(self.settled)
                self.p.conditions.resume_pending()
                self.assertIsNone(self.p.conditions.pending)
                self.assertEqual(self.capture_calls,[]);self.reader.read.assert_not_called()

    def test_automatic_capture_or_ocr_waiting_deadline_is_not_extended(self):
        self.stack.enter_context(patch('condition_controller.time',SimpleNamespace(monotonic=lambda:self.now[0])))
        for phase in ('capture','ocr'):
            with self.subTest(phase=phase):
                self.capture_calls.clear();self.reader.reset_mock();self.now[0]=10.0
                if phase=='capture':self.start_ordinary_automatic_capture()
                else:self.start_automatic_live_ocr()
                self.p.browser.input_bar.read.click()
                self.assertIsNotNone(self.p.conditions.pending)
                original_deadline=self.p.conditions.pending[2]
                self.now[0]=11.5
                for _ in range(6):self.p.browser.input_bar.read.click()
                self.assertEqual(self.p.conditions.pending[2],original_deadline)
                self.now[0]=12.01
                self.release_probe.set();self.wait(self.settled)
                self.p.conditions.resume_pending()
                self.assertIsNone(self.p.conditions.pending)
                self.assertEqual(self.capture_calls,[]);self.reader.read.assert_not_called()


if __name__ == '__main__':
    unittest.main()
