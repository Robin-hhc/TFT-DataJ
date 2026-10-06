"""Controller seams use real identity mapping and mocked native boundaries."""
from copy import deepcopy
from types import SimpleNamespace
import unittest

from entity_identity import EntityResolver
from selection_tracker import CompletionEvidence, MouseNotice
from selection_controller import SelectionController
from test_selection_layout import augment_observation


CATALOG = {'hex': [{'id': '42', 'name': '黑铁资产', 'level': 1},
                   {'id': '43', 'name': '应急护甲 I', 'level': 1},
                   {'id': '44', 'name': '进攻宣告', 'level': 1}],
           'equip': [{'id': '2085', 'name': '光明版狂徒铠甲', 'type': '光明武器'},
                     {'id': '2091', 'name': '光明版强袭者的链枷', 'type': '光明武器'},
                     {'id': '2078', 'name': '光明版适应性头盔', 'type': '光明武器'}]}
LAYOUT = 's18-mumu-green-augments-3-v1'


class Native:
    def __init__(self):
        self.binding = SimpleNamespace(hwnd=100, pid=8, process='MuMu.exe',
            rect=(0, 0, 3840, 2160), dpi=144, minimized=False)
        self.foreground = 100
        self.calls = []

    def describe(self, hwnd):
        self.calls.append(('describe', hwnd))
        return self.binding

    def foreground_root(self):
        self.calls.append(('foreground',))
        return self.foreground


def observation():
    obs = augment_observation()
    obs['round'] = {'status': 'resolved', 'value': '2-1'}
    for card, row in zip(obs['cards'], CATALOG['hex']):
        card['resolution'] = {'status': 'resolved', **row, 'candidates': [dict(row)]}
    return obs


class SelectionControllerTests(unittest.TestCase):
    def setUp(self):
        self.time = 10.0
        self.native = Native()
        self.events = []
        self.resets = []
        self.resolver = EntityResolver(CATALOG)

    def controller(self, verified=()):
        return SelectionController('game', self.resolver, on_selected=self.events.append,
            verified_layouts=verified, win_api=self.native, clock=lambda: self.time,
            on_context_reset=lambda reason, identity: self.resets.append((reason, identity)))

    def observe(self, controller, obs=None, at=None):
        return controller.observe(obs or observation(), (3840, 2160),
                                  self.native.binding, self.time if at is None else at)

    def click(self, controller, slot='0'):
        card = next(c for c in controller.snapshot.cards if c.slot == slot)
        x = (card.selectable.left + card.selectable.right) / 2
        y = (card.selectable.top + card.selectable.bottom) / 2
        self.time += .05
        controller.on_mouse(MouseNotice('down', x, y, self.time, 100))
        self.time += .05
        controller.on_mouse(MouseNotice('up', x, y, self.time, 100))

    def receipt(self, controller, kind='selected_result'):
        p = controller.tracker.proposal
        s = p.snapshot
        return CompletionEvidence(s.session_id, s.offer_id, s.revision, s.window_identity,
            s.geometry_revision, s.layout_id, p.card.slot, self.time, kind, 'receipt:test')

    def test_default_empty_calibration_keeps_metadata_without_mouse_tracking(self):
        c = self.controller()
        snapshot = self.observe(c)
        self.assertFalse(snapshot.layout_verified)
        self.assertEqual(len(snapshot.cards), 3)
        self.click(c)
        self.assertIsNone(c.tracker.proposal)
        self.assertIsNone(c.next_receipt_probe())
        self.assertEqual(self.events, [])
        self.assertFalse(hasattr(c.snapshot, 'image'))

    def test_test_injected_calibration_requires_paired_click_and_independent_receipt(self):
        c = self.controller((LAYOUT,))
        self.observe(c)
        self.click(c, '1')
        self.assertEqual(self.events, [])
        c.invalidate()
        self.assertIsNotNone(c.tracker.pending_confirmation)
        event = c.accept_evidence(self.receipt(c))
        self.assertEqual(event.entity_id, '43')
        self.assertEqual(event.source, 'automatic_verified')
        self.assertEqual(len(self.events), 1)

    def test_duplicate_ocr_updates_freshness_without_changing_flow_or_frozen_regions(self):
        c = self.controller((LAYOUT,))
        first = self.observe(c)
        self.click(c)
        obs = observation()
        for card in obs['cards']:
            card['box'] = [[x + 2, y] for x, y in card['box']]
        self.time += .1
        second = self.observe(c, obs)
        self.assertEqual(first.flow, second.flow)
        self.assertEqual(first.cards, second.cards)
        self.assertEqual(c.tracker.proposal.snapshot.frame_time, first.frame_time)

    def test_changed_candidate_and_explicit_refresh_never_reuse_receipt_flow(self):
        c = self.controller((LAYOUT,))
        first = self.observe(c)
        self.click(c)
        old = self.receipt(c)
        obs = observation()
        obs['cards'][0]['resolution'] = obs['cards'][2]['resolution']
        self.time += .1
        changed = self.observe(c, obs)
        self.assertNotEqual(first.flow, changed.flow)
        self.assertIsNone(c.accept_evidence(old))
        c.start_new_offer('refresh')
        third = self.observe(c, obs)
        self.assertNotEqual(changed.flow, third.flow)
        self.assertEqual(self.events, [])

    def test_unknown_and_board_frames_do_not_commit_or_destroy_bounded_pending(self):
        c = self.controller((LAYOUT,))
        self.observe(c); self.click(c)
        for scene in ('unknown', 'normal_board'):
            self.time += .1
            self.assertIsNone(self.observe(c, {'scene': scene}))
            self.assertIsNotNone(c.tracker.proposal)
        for kind in ('unknown', 'choice_disappeared', 'board'):
            self.assertIsNone(c.accept_evidence(self.receipt(c, kind)))
        self.time += 3
        c.tick()
        self.assertIsNone(c.tracker.proposal)
        self.assertEqual(self.events, [])

    def test_late_observations_never_overwrite_newer_offer_or_scene(self):
        c = self.controller((LAYOUT,))
        first = self.observe(c)
        self.time += .3
        second = self.observe(c)
        self.assertIsNone(self.observe(c, {'scene': 'unknown'}, at=10.0))
        self.assertEqual(c.snapshot.frame_time, second.frame_time)
        self.assertEqual(c.tracker.offer.flow, first.flow)
        self.assertIsNone(self.observe(c, at=self.time + 1))

    def test_live_window_foreground_and_geometry_guard_are_rechecked_on_queued_mouse(self):
        for change in ('foreground', 'rect', 'dpi', 'minimized', 'closed', 'pid'):
            with self.subTest(change=change):
                self.setUp(); c = self.controller((LAYOUT,)); self.observe(c)
                b = self.native.binding
                if change == 'foreground': self.native.foreground = 99
                elif change == 'closed': self.native.binding = None
                else:
                    values = dict(vars(b)); values[change] = {'rect': (1, 0, 3841, 2160),
                        'dpi': 192, 'minimized': True, 'pid': 9}[change]
                    self.native.binding = SimpleNamespace(**values)
                c.on_mouse(MouseNotice('down', 907, 772, self.time, 100))
                self.assertIsNone(c.tracker.proposal)
                self.assertEqual(self.events, [])
                self.assertIn(('describe', 100), self.native.calls)

    def test_receipt_probe_budget_is_bounded_and_only_after_valid_pair(self):
        c = self.controller((LAYOUT,))
        self.assertIsNone(c.next_receipt_probe())
        self.observe(c); self.assertIsNone(c.next_receipt_probe()); self.click(c)
        probes = []
        for _ in range(3):
            self.time += .25
            probes.append(c.next_receipt_probe())
        self.assertEqual([p.attempt for p in probes], [1, 2, 3])
        self.assertTrue(all(p.selection_event_id == probes[0].selection_event_id for p in probes))
        self.assertIsNone(c.next_receipt_probe())
        c.cancel('refresh')
        self.assertFalse(c.probe_current(probes[0]))
        self.assertEqual(self.events, [])

    def test_manual_detail_confirmation_is_explicit_unique_and_game_scoped(self):
        c = self.controller()
        row = CATALOG['hex'][0]
        args = dict(selection_event_id='manual:1', session_id='game')
        self.assertIsNone(c.confirm_detail('hex', row, **args))
        event = c.confirm_detail('hex', row, explicitly_confirmed=True, **args)
        self.assertEqual(event.source, 'manual_confirmation')
        self.assertEqual(event.entity_id, '42')
        self.assertIsNone(c.confirm_detail('hex', row, explicitly_confirmed=True, **args))
        self.assertIsNone(c.confirm_detail('hex', {'id':'42','name':'wrong'},
            explicitly_confirmed=True, selection_event_id='manual:2', session_id='game'))
        c.new_game('new')
        self.assertIsNone(c.confirm_detail('hex', row, explicitly_confirmed=True, **args))

    def test_indistinguishable_rows_and_unresolved_cards_cannot_be_manually_forged(self):
        catalog = deepcopy(CATALOG)
        catalog['hex'].append({'id': '99', 'name': '黑铁资产', 'level': 1})
        c = self.controller()
        c.resolver = EntityResolver(catalog)
        snap = self.observe(c)
        self.assertNotIn('0', [card.slot for card in snap.cards])
        self.assertIsNone(c.confirm_detail('hex', CATALOG['hex'][0], explicitly_confirmed=True,
            selection_event_id='manual:1', session_id='game'))

    def test_item_observations_use_full_card_geometry_and_supported_category(self):
        obs = {'scene':'item_candidates', 'cards': []}
        for slot, (left, row) in enumerate(zip((1184, 1744, 2304), CATALOG['equip'])):
            obs['cards'].append({'slot': slot,
                'box': [[left,1604],[left+388,1604],[left+388,2000],[left,2000]],
                'resolution': {'status':'resolved', **row, 'candidates':[dict(row)]}})
        c = self.controller()
        snap = self.observe(c, obs)
        self.assertEqual(snap.layout_id, 's18-items-radiant-3-v1')
        self.assertEqual(len(snap.cards), 3)
        self.assertIsNone(snap.card_at(1378, 2075))

    def test_close_new_game_and_binding_changes_clear_pending_but_scene_exit_does_not(self):
        c = self.controller((LAYOUT,))
        self.observe(c); self.click(c)
        c.scene_left(); self.assertIsNotNone(c.tracker.proposal)
        c.window_closed(); self.assertIsNone(c.tracker.proposal)
        self.assertIsNone(c.snapshot); self.assertEqual(self.resets[-1][0], 'window_closed')
        self.observe(c); self.click(c)
        other = SimpleNamespace(**{**vars(self.native.binding), 'pid': 9})
        c.binding_changed(other)
        self.assertIsNone(c.tracker.proposal)
        self.assertEqual(self.resets[-1][0], 'binding_changed')
        c.new_game('next')
        self.assertEqual(c.tracker.session_id, 'next')

    def test_new_game_rejects_even_fresh_callback_captured_before_reset(self):
        c = self.controller((LAYOUT,))
        self.observe(c)
        old_frame = self.time
        self.time += .2
        c.new_game('next')
        self.assertIsNone(self.observe(c, at=old_frame))
        self.assertIsNone(c.snapshot)
        self.assertEqual(self.observe(c).session_id, 'next')

    def test_capture_canvas_change_cancels_click_even_with_identical_entities(self):
        c = self.controller((LAYOUT,))
        first = self.observe(c); self.click(c)
        self.time += .1
        obs = observation()
        for card in obs['cards']:
            card['box'] = [[x / 2, y / 2] for x, y in card['box']]
        second = c.observe(obs, (1920, 1080), self.native.binding, self.time)
        self.assertNotEqual(first.flow, second.flow)
        self.assertIsNone(c.tracker.proposal)

    def test_malformed_item_slot_order_refuses_mapping_entity_to_wrong_card(self):
        obs = {'scene':'item_candidates', 'cards': []}
        for slot, (left, row) in enumerate(zip((1184, 1744, 2304), CATALOG['equip']), 1):
            obs['cards'].append({'slot': slot,
                'box': [[left,1604],[left+388,1604],[left+388,2000],[left,2000]],
                'resolution': {'status':'resolved', **row, 'candidates':[dict(row)]}})
        self.assertIsNone(self.observe(self.controller(), obs))

    def test_repeat_same_item_in_separate_explicit_offer_emits_two_events(self):
        c = self.controller((LAYOUT,))
        for _ in range(2):
            self.observe(c); self.click(c); c.accept_evidence(self.receipt(c))
            c.start_new_offer('independently_confirmed_new_reward')
            self.time += .1
        self.assertEqual([e.entity_id for e in self.events], ['42', '42'])
        self.assertNotEqual(self.events[0].selection_event_id, self.events[1].selection_event_id)

    def test_completion_before_mouse_up_is_retained_across_normal_close(self):
        c = self.controller((LAYOUT,))
        self.observe(c)
        self.time += .1
        c.on_mouse(MouseNotice('down', 907, 772, self.time, 100))
        self.time += .05
        self.assertIsNone(c.accept_evidence(self.receipt(c)))
        c.scene_left()
        self.time += .05
        self.assertIsNotNone(c.on_mouse(MouseNotice('up', 907, 772, self.time, 100)))
        self.assertEqual(len(self.events), 1)

    def test_large_card_shift_is_not_treated_as_harmless_ocr_box_jitter(self):
        c = self.controller((LAYOUT,))
        first = self.observe(c); self.click(c)
        obs = observation()
        for card in obs['cards']:
            card['box'] = [[x + 40, y] for x, y in card['box']]
        self.time += .1
        changed = self.observe(c, obs)
        self.assertNotEqual(changed.flow, first.flow)
        self.assertIsNone(c.tracker.proposal)

    def test_missing_slot_is_a_refused_observation_not_an_exception(self):
        c = self.controller((LAYOUT,))
        obs = observation()
        del obs['cards'][0]['slot']
        self.assertIsNone(self.observe(c, obs))

    def test_same_candidates_with_temporarily_unknown_round_keep_frozen_flow(self):
        c = self.controller((LAYOUT,))
        first = self.observe(c); self.click(c)
        obs = observation(); obs['round'] = {'status':'unrecognized'}
        self.time += .1
        same = self.observe(c, obs)
        self.assertEqual(same.flow, first.flow)
        self.assertEqual(same.round, '2-1')
        self.assertIsNotNone(c.tracker.proposal)

    def test_real_reader_round_strings_change_flow_for_same_candidate_set(self):
        c = self.controller((LAYOUT,))
        obs = observation(); obs['round'] = '2-1'
        first = self.observe(c, obs)
        self.assertEqual(first.round, '2-1')
        self.time += .1
        obs['round'] = '3-2'
        second = self.observe(c, obs)
        self.assertEqual(second.round, '3-2')
        self.assertNotEqual(first.flow, second.flow)

    def test_invalid_round_metadata_cannot_enter_history_as_boolean_or_mapping(self):
        for stage in (True, {'status':'resolved','value':True}, {'status':'resolved','value':{}},
                      '03-2', 'unknown', '3-2 extra'):
            with self.subTest(stage=stage):
                c = self.controller()
                obs = observation(); obs['round'] = stage
                self.assertIsNone(self.observe(c, obs).round)


if __name__ == '__main__':
    unittest.main()
