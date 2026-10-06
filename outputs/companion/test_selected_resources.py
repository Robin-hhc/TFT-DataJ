import unittest
from dataclasses import replace

from selected_resources import SelectedResources, SelectionEntity


class SelectedResourcesTests(unittest.TestCase):
    def test_explicit_confirmation_adds_only_the_named_entity_once(self):
        resources = SelectedResources('game-a')
        entity = SelectionEntity('hex', '42', '黑铁资产', category='silver', identity_confirmed=True)
        event = resources.confirm(entity, selection_event_id='choice-1', session_id='game-a',
                                  selected_at=10, source='manual_confirmation', round='2-1')
        self.assertEqual((event.kind, event.entity_id, event.name, event.round),
                         ('hex', '42', '黑铁资产', '2-1'))
        resources.confirm(entity, selection_event_id='choice-1', session_id='game-a',
                          selected_at=11, source='manual_confirmation')
        self.assertEqual(len(resources.events), 1)

    def setUp(self):
        self.resources = SelectedResources('game-a')
        self.entity = SelectionEntity('equip', '158', '无尽之刃', 'normal',
                                      'https://img.dataj.cc/item.png', True)

    def confirm(self, **changes):
        values = dict(selection_event_id='first', session_id='game-a', selected_at=10,
                      source='manual_confirmation')
        values.update(changes)
        return self.resources.confirm(self.entity, **values)

    def test_two_independent_same_equipment_choices_preserve_events_but_one_shortcut(self):
        self.confirm()
        self.confirm(selection_event_id='second', selected_at=11)
        self.assertEqual([event.selection_event_id for event in self.resources.events], ['first', 'second'])
        self.assertEqual([event.selection_event_id for event in self.resources.shortcuts], ['second'])
        self.assertEqual(self.resources.shortcuts[0].entity, self.entity)

    def test_recent_shortcuts_are_entity_specific_not_name_specific(self):
        self.confirm()
        radiant = replace(self.entity, entity_id='2158', category='radiant')
        self.resources.confirm(radiant, selection_event_id='radiant', session_id='game-a',
                               selected_at=11, source='manual_confirmation')
        self.assertEqual([event.entity_id for event in self.resources.shortcuts], ['2158', '158'])

    def test_unknown_identity_cannot_be_confirmed_even_manually(self):
        for entity in (replace(self.entity, identity_confirmed=False),
                       replace(self.entity, entity_id=''), replace(self.entity, kind='unknown')):
            with self.subTest(entity=entity):
                self.assertIsNone(self.resources.confirm(entity, selection_event_id='first', session_id='game-a',
                                                        selected_at=10, source='manual_confirmation'))
        self.assertEqual(self.resources.events, ())

    def test_unsupported_sources_rejected_and_automatic_sources_need_evidence(self):
        for source in ('candidate', 'unknown', 'statistics_ready', 'tooltip_title'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.confirm(source=source)
        for source in ('automatic_verified', 'direct_selected_detail'):
            with self.subTest(source=source):
                self.assertIsNone(self.confirm(source=source))
                self.assertIsNotNone(self.confirm(source=source, evidence_reference='verified-frame',
                                                 selection_event_id=source))

    def test_stale_game_and_event_identity_collision_cannot_mutate_history(self):
        self.assertIsNone(self.confirm(session_id='previous-game'))
        first = self.confirm()
        self.assertIsNone(self.resources.confirm(replace(self.entity, entity_id='other'),
                                                selection_event_id='first', session_id='game-a',
                                                selected_at=11, source='manual_confirmation'))
        self.assertEqual(self.resources.events, (first,))

    def test_new_game_and_changed_window_isolate_old_events(self):
        self.resources.bind_window(('mumu', 7))
        self.confirm()
        self.resources.bind_window(('mumu', 7))
        self.assertEqual(len(self.resources.events), 1)
        self.resources.bind_window(('mumu', 8), session_id='game-b')
        self.assertEqual(self.resources.events, ())
        self.assertIsNone(self.confirm())
        self.resources.reset('game-c')
        self.assertEqual(self.resources.session_id, 'game-c')

    def test_history_limit_does_not_evict_deduplication_keys(self):
        self.resources = SelectedResources('game-a', max_events=1)
        first = self.confirm()
        self.assertIsNone(self.confirm(selection_event_id='second'))
        self.assertEqual(self.confirm(), first)
        self.assertEqual(self.resources.events, (first,))

    def test_invalid_event_time_does_not_create_metadata(self):
        for at in (float('nan'), float('inf'), None, True):
            with self.subTest(at=at):
                self.assertIsNone(self.confirm(selected_at=at))
        self.assertEqual(self.resources.events, ())


if __name__ == '__main__':
    unittest.main()
