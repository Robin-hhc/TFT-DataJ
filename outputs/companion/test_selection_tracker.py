import unittest
from dataclasses import replace

from selected_resources import SelectionEntity
from selection_tracker import (CardSnapshot, CompletionEvidence, MouseNotice,
                               OfferSnapshot, Rect, SelectionTracker)


def offer(offer_id='choice-a', revision=1, frame_time=10, entity_id='42'):
    entities = [SelectionEntity('hex', entity_id, '黑铁资产', 'silver', identity_confirmed=True),
                SelectionEntity('hex', '43', '应急护甲 I', 'silver', identity_confirmed=True),
                SelectionEntity('hex', '44', '进攻宣告', 'silver', identity_confirmed=True)]
    return OfferSnapshot('game-a', offer_id, revision, ('mumu', 7), 7, 'geometry-1',
                         frame_time, 's18-augments',
                         tuple(CardSnapshot(str(i), e, Rect(100 + i * 300, 100, 250 + i * 300, 600))
                               for i, e in enumerate(entities)),
                         exclusions=(Rect(100, 500, 250, 540),), fingerprint='cards-a',
                         round='2-1', layout_verified=True)


def click(action, x=160, y=200, at=10.1, foreground=7):
    return MouseNotice(action, x, y, at, foreground)


def completion(snapshot, at=10.3, slot='0', kind='selected_animation', reference='frame-11'):
    return CompletionEvidence(snapshot.session_id, snapshot.offer_id, snapshot.revision,
                              snapshot.window_identity, snapshot.geometry_revision,
                              snapshot.layout_id, slot, at, kind, reference)


class SelectionTrackerTests(unittest.TestCase):
    def test_same_card_click_and_verified_completion_publish_only_selected_entity(self):
        selected = []
        tracker = SelectionTracker('game-a', on_selected=selected.append,
                                   accepted_layouts=('s18-augments',))
        snapshot = offer()
        tracker.observe_offer(snapshot, now=10)
        tracker.mouse(click('down'))
        tracker.mouse(click('up', at=10.2))
        self.assertEqual(selected, [])
        event = tracker.evidence(completion(snapshot))
        self.assertEqual((event.entity_id, event.name, event.source),
                         ('42', '黑铁资产', 'automatic_verified'))
        self.assertEqual(selected, [event])
        tracker.evidence(completion(snapshot, at=10.4))
        self.assertEqual(len(selected), 1)

    def setUp(self):
        self.selected = []
        self.tracker = SelectionTracker('game-a', on_selected=self.selected.append,
                                        accepted_layouts=('s18-augments',))
        self.snapshot = offer()
        self.tracker.observe_offer(self.snapshot, now=10)

    def paired(self):
        self.tracker.mouse(click('down'))
        self.tracker.mouse(click('up', at=10.2))

    def test_default_automatic_disabled_but_explicit_user_can_confirm_unique_click(self):
        self.tracker = SelectionTracker('game-a', on_selected=self.selected.append)
        self.tracker.observe_offer(self.snapshot, now=10)
        self.paired()
        self.assertIsNone(self.tracker.evidence(completion(self.snapshot)))
        proposal = self.tracker.pending_confirmation
        result = self.tracker.manual_confirm(proposal.selection_event_id, now=10.4)
        self.assertEqual(result.source, 'manual_confirmation')
        self.assertEqual(len(self.selected), 1)

    def test_completion_during_down_up_animation_is_retained(self):
        self.tracker.mouse(click('down'))
        self.tracker.evidence(completion(self.snapshot, at=10.15))
        self.tracker.scene_left(now=10.16)
        self.assertEqual(self.selected, [])
        event = self.tracker.mouse(click('up', at=10.2))
        self.assertEqual(event.entity_id, '42')
        self.assertEqual(len(self.selected), 1)

    def test_unknown_normal_exit_query_or_overlay_is_never_completion(self):
        self.paired()
        for kind in ('unknown', 'normal_board', 'offer_disappeared', 'overlay_hidden', 'statistics_ready'):
            self.assertIsNone(self.tracker.evidence(completion(self.snapshot, at=10.3, kind=kind)))
        self.tracker.scene_left(now=10.4)
        self.tracker.tick(12.2)
        self.assertEqual(self.selected, [])
        self.assertIsNone(self.tracker.pending_confirmation)

    def test_repeated_same_offer_read_does_not_restart_or_extend_transaction(self):
        self.paired()
        event_id = self.tracker.pending_confirmation.selection_event_id
        self.tracker.observe_offer(replace(self.snapshot, frame_time=10.4), now=10.4)
        self.assertEqual(self.tracker.pending_confirmation.selection_event_id, event_id)
        self.assertEqual(self.tracker.pending_confirmation.snapshot.frame_time, 10)
        self.tracker.tick(12.2)
        self.assertEqual(self.selected, [])
        self.assertIsNone(self.tracker.pending_confirmation)

    def test_card_change_or_refresh_invalidates_old_click_and_completion(self):
        for replacement in (replace(self.snapshot, revision=2, frame_time=10.3),
                            replace(self.snapshot, fingerprint='new-cards', frame_time=10.3),
                            offer(frame_time=10.3, entity_id='99')):
            with self.subTest(replacement=replacement):
                self.setUp()
                self.paired()
                self.tracker.observe_offer(replacement, now=10.3)
                self.assertIsNone(self.tracker.evidence(completion(self.snapshot, at=10.4)))
                self.assertEqual(self.selected, [])

    def test_early_or_stale_clicks_never_adopt_later_ocr_identity(self):
        self.tracker.scene_left(now=10)
        self.tracker.mouse(click('down', at=10.1))
        self.tracker.observe_offer(replace(self.snapshot, frame_time=10.2), now=10.2)
        self.tracker.mouse(click('up', at=10.3))
        self.assertIsNone(self.tracker.pending_confirmation)
        self.tracker.mouse(click('down', at=11.3))
        self.tracker.mouse(click('up', at=11.4))
        self.assertIsNone(self.tracker.evidence(completion(self.snapshot, at=11.5)))
        self.assertEqual(self.selected, [])

    def test_exclusion_buttons_outside_and_overlapping_cards_never_start_intent(self):
        for x, y in ((160, 520), (50, 200), (250, 200), (160, 600)):
            self.tracker.mouse(click('down', x=x, y=y))
            self.tracker.mouse(click('up', x=x, y=y, at=10.2))
            self.assertIsNone(self.tracker.pending_confirmation)
        overlapping = replace(self.snapshot, cards=(self.snapshot.cards[0],
                          replace(self.snapshot.cards[1], selectable=Rect(100, 100, 250, 600))))
        self.tracker.observe_offer(overlapping, now=10)
        self.paired()
        self.assertIsNone(self.tracker.pending_confirmation)

    def test_exclusion_or_different_card_click_cancels_pending_and_does_not_take_last(self):
        for x, y in ((160, 520), (460, 200), (50, 200)):
            with self.subTest(x=x, y=y):
                self.setUp()
                self.paired()
                self.tracker.mouse(click('down', x=x, y=y, at=10.3))
                self.tracker.mouse(click('up', x=x, y=y, at=10.4))
                self.tracker.observe_offer(replace(self.snapshot, frame_time=10.4), now=10.4)
                self.assertIsNone(self.tracker.evidence(completion(self.snapshot, at=10.5)))
                self.assertEqual(self.selected, [])

    def test_different_card_up_drag_or_missing_up_never_commits(self):
        for action, x, y, at in (('up', 460, 200, 10.2), ('move', 170, 200, 10.2),
                                 ('up', 160, 200, 12.2)):
            with self.subTest(action=action, x=x, at=at):
                self.setUp()
                self.tracker.mouse(click('down'))
                self.tracker.mouse(click(action, x=x, y=y, at=at))
                self.assertIsNone(self.tracker.evidence(completion(self.snapshot, at=max(10.3, at))))
                self.assertEqual(self.selected, [])
        self.setUp()
        self.tracker.mouse(click('down'))
        self.tracker.evidence(completion(self.snapshot))
        self.tracker.tick(12.2)
        self.assertEqual(self.selected, [])

    def test_same_card_double_click_commits_once(self):
        self.paired()
        event_id = self.tracker.pending_confirmation.selection_event_id
        self.tracker.mouse(click('down', at=10.21))
        self.tracker.mouse(click('up', at=10.22))
        self.assertEqual(self.tracker.pending_confirmation.selection_event_id, event_id)
        self.tracker.evidence(completion(self.snapshot))
        self.tracker.observe_offer(replace(self.snapshot, frame_time=10.4), now=10.4)
        self.paired()
        self.tracker.evidence(completion(self.snapshot, at=10.5))
        self.assertEqual(len(self.selected), 1)

    def test_window_geometry_dpi_minimize_foreground_changes_cancel(self):
        for window, geometry, foreground in ((('mumu', 8), 'geometry-1', 7),
                                             (('mumu', 7), 'dpi-changed', 7),
                                             (('mumu', 7), 'geometry-1', 0),
                                             (('mumu', 7), 'geometry-1', 8)):
            with self.subTest(window=window, geometry=geometry, foreground=foreground):
                self.setUp()
                self.paired()
                self.assertFalse(self.tracker.guard(window_identity=window,
                                geometry_revision=geometry, foreground=foreground))
                self.assertIsNone(self.tracker.evidence(completion(self.snapshot)))
                self.assertEqual(self.selected, [])

    def test_hook_injected_or_foreign_clicks_cannot_select(self):
        self.tracker.mouse(replace(click('down'), injected=True))
        self.tracker.mouse(click('up', at=10.2))
        self.assertIsNone(self.tracker.pending_confirmation)
        self.paired()
        self.tracker.mouse(click('up', at=10.3, foreground=9))
        self.assertIsNone(self.tracker.evidence(completion(self.snapshot, at=10.4)))

    def test_completion_is_bound_to_full_frozen_context_and_slot(self):
        self.paired()
        valid = completion(self.snapshot)
        for bad in (replace(valid, session_id='game-b'), replace(valid, offer_id='other'),
                    replace(valid, revision=2), replace(valid, window_identity=('mumu', 8)),
                    replace(valid, geometry_revision='dpi-changed'), replace(valid, layout_id='untested'),
                    replace(valid, slot='1'), replace(valid, reference=''), replace(valid, at=10.05)):
            with self.subTest(bad=bad):
                self.assertIsNone(self.tracker.evidence(bad, now=10.4))
        self.assertEqual(self.selected, [])
        self.assertIsNotNone(self.tracker.evidence(valid, now=10.4))

    def test_same_equipment_in_new_independent_offer_creates_second_event(self):
        first = replace(self.snapshot, layout_id='s18-items',
                        cards=(replace(self.snapshot.cards[0], entity=SelectionEntity(
                            'equip', '158', '无尽之刃', 'normal', identity_confirmed=True)),))
        self.tracker = SelectionTracker('game-a', on_selected=self.selected.append,
                                        accepted_layouts=('s18-items',))
        for snapshot, offset in ((first, 0), (replace(first, offer_id='second', frame_time=20), 10)):
            self.tracker.observe_offer(snapshot, now=10 + offset)
            self.tracker.mouse(click('down', at=10.1 + offset))
            self.tracker.mouse(click('up', at=10.2 + offset))
            self.tracker.evidence(completion(snapshot, at=10.3 + offset))
        self.assertEqual([event.entity_id for event in self.selected], ['158', '158'])
        self.assertNotEqual(self.selected[0].selection_event_id, self.selected[1].selection_event_id)

    def test_manual_confirmation_requires_paired_unique_fresh_proposal(self):
        self.assertIsNone(self.tracker.manual_confirm('invented', now=10))
        self.tracker.mouse(click('down'))
        pressed_id = self.tracker.proposal.selection_event_id
        self.assertIsNone(self.tracker.manual_confirm(pressed_id, now=10.15))
        self.tracker.mouse(click('up', at=10.2))
        self.assertIsNone(self.tracker.manual_confirm('wrong-id', now=10.3))
        self.assertIsNone(self.tracker.manual_confirm(pressed_id, now=12.2))
        self.assertEqual(self.selected, [])

    def test_ambiguous_entity_or_uncalibrated_layout_cannot_establish_offer(self):
        for bad in (replace(self.snapshot, layout_verified=False),
                    replace(self.snapshot, cards=(replace(self.snapshot.cards[0],
                        entity=replace(self.snapshot.cards[0].entity, identity_confirmed=False)),)),
                    replace(self.snapshot, cards=()), replace(self.snapshot, session_id='game-b')):
            with self.subTest(bad=bad):
                tracker = SelectionTracker('game-a')
                self.assertFalse(tracker.observe_offer(bad, now=10))
                tracker.mouse(click('down'))
                tracker.mouse(click('up', at=10.2))
                self.assertIsNone(tracker.pending_confirmation)

    def test_new_game_rejects_late_completion_and_old_offer(self):
        self.paired()
        self.tracker.reset('game-b')
        self.assertIsNone(self.tracker.evidence(completion(self.snapshot)))
        self.assertFalse(self.tracker.observe_offer(self.snapshot, now=10))
        self.assertEqual(self.selected, [])

    def test_changed_candidates_require_a_new_flow_revision_before_another_click(self):
        self.paired()
        changed = offer(frame_time=10.3, entity_id='99')
        self.assertFalse(self.tracker.observe_offer(changed, now=10.3))
        self.tracker.mouse(click('down', at=10.31))
        self.tracker.mouse(click('up', at=10.32))
        self.assertIsNone(self.tracker.evidence(completion(self.snapshot, at=10.4)))
        self.assertEqual(self.selected, [])
        new_flow = replace(changed, revision=2, frame_time=10.5)
        self.assertTrue(self.tracker.observe_offer(new_flow, now=10.5))
        self.tracker.mouse(click('down', at=10.6))
        self.tracker.mouse(click('up', at=10.7))
        self.assertIsNotNone(self.tracker.evidence(completion(new_flow, at=10.8)))
        self.assertEqual([event.entity_id for event in self.selected], ['99'])

    def test_malformed_context_never_raises_or_establishes_a_choice(self):
        for malformed in (None, {}, replace(self.snapshot, cards=(CardSnapshot('0', None, Rect(0, 0, 10, 10)),)),
                          replace(self.snapshot, exclusions=(None,)), replace(self.snapshot, revision=True),
                          replace(self.snapshot, window_hwnd=0), replace(self.snapshot, frame_time=float('nan'))):
            with self.subTest(malformed=malformed):
                tracker = SelectionTracker('game-a')
                self.assertFalse(tracker.observe_offer(malformed, now=10))

    def test_old_revision_arriving_late_cannot_clear_new_offer_or_transaction(self):
        newer = replace(self.snapshot, revision=2, frame_time=10.3)
        self.tracker.observe_offer(newer, now=10.3)
        self.tracker.mouse(click('down', at=10.4))
        self.tracker.mouse(click('up', at=10.5))
        self.assertFalse(self.tracker.observe_offer(self.snapshot, now=10.6))
        self.assertIsNotNone(self.tracker.evidence(completion(newer, at=10.7)))
        self.assertEqual(len(self.selected), 1)


if __name__ == '__main__':
    unittest.main()
