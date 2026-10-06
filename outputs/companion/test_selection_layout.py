import unittest
from copy import deepcopy

from selected_resources import SelectionEntity
from selection_layout import augment_geometry, item_geometry


def augment_observation():
    return {'scene': 'choice_candidates', 'layout_method': 'three_refresh_controls',
            'cards': [{'slot': 0, 'box': [[774, 729], [1039, 729], [1039, 816], [774, 816]]},
                      {'slot': 1, 'box': [[1767, 729], [2063, 729], [2063, 814], [1767, 814]]},
                      {'slot': 2, 'box': [[2787, 731], [3052, 731], [3052, 812], [2787, 812]]}]}


class SelectionLayoutTests(unittest.TestCase):
    def test_real_4k_augment_proposal_covers_body_but_excludes_refresh_and_hide(self):
        geometry = augment_geometry(augment_observation(), (3840, 2160))
        self.assertFalse(geometry.layout_verified)
        # Manually read landmarks in the original 4K user screenshot.
        self.assertEqual(geometry.slot_at(907, 772), '0')
        self.assertEqual(geometry.slot_at(1915, 1000), '1')
        self.assertEqual(geometry.slot_at(2920, 600), '2')
        for point in ((907, 1464), (1915, 1464), (2920, 1464), (1915, 1928), (140, 700)):
            with self.subTest(point=point):
                self.assertIsNone(geometry.slot_at(*point))
        self.assertTrue(any(rect.contains(907, 1464) for rect in geometry.exclusions))
        self.assertTrue(any(rect.contains(1915, 1928) for rect in geometry.exclusions))

    def test_real_video_equipment_card_body_and_independent_details_button(self):
        geometry = item_geometry([(228, 501, 324, 600), (368, 501, 466, 602),
                                  (510, 501, 608, 598), (652, 501, 748, 602)],
                                 (960, 720), category='artifact')
        self.assertFalse(geometry.layout_verified)
        self.assertEqual(geometry.slot_at(276, 560), '0')
        self.assertEqual(geometry.slot_at(417, 560), '1')
        self.assertIsNone(geometry.slot_at(276, 620))
        self.assertTrue(any(rect.contains(276, 620) for rect in geometry.exclusions))

    def test_screen_coordinates_translate_and_scale_uniformly_including_negative_monitor(self):
        geometry = augment_geometry(augment_observation(), (3840, 2160),
                                     screen_rect=(-1920, 40, 0, 1120))
        self.assertEqual(geometry.slot_at(-1920 + 907 / 2, 40 + 772 / 2), '0')
        self.assertIsNone(geometry.slot_at(-1920 + 907 / 2, 40 + 1464 / 2))
        self.assertFalse(geometry.layout_verified)

    def test_wrong_capture_canvas_aspect_cannot_project_recording_onto_game(self):
        self.assertIsNone(augment_geometry(augment_observation(), (3840, 2160),
                                          screen_rect=(0, 0, 960, 720)))
        self.assertIsNone(augment_geometry(augment_observation(), (960, 720)))
        self.assertIsNone(item_geometry([(228, 501, 324, 600), (368, 501, 466, 602),
                                        (510, 501, 608, 598), (652, 501, 748, 602)],
                                       (960, 720), category='artifact', screen_rect=(0, 0, 1920, 1080)))

    def test_unknown_scene_unverified_layout_method_and_bad_anchor_refuse_proposal(self):
        for key, value in (('scene', 'unknown'), ('scene', 'normal_board'),
                           ('layout_method', 'choice_header'), ('cards', [])):
            bad = deepcopy(augment_observation()); bad[key] = value
            self.assertIsNone(augment_geometry(bad, (3840, 2160)))
        bad = deepcopy(augment_observation()); bad['cards'][1]['box'] = bad['cards'][0]['box']
        self.assertIsNone(augment_geometry(bad, (3840, 2160)))
        bad = deepcopy(augment_observation()); bad['cards'][1]['slot'] = 2
        self.assertIsNone(augment_geometry(bad, (3840, 2160)))
        bad = deepcopy(augment_observation()); bad['cards'][1]['box'] = None
        self.assertIsNone(augment_geometry(bad, (3840, 2160)))

    def test_cards_include_only_identity_confirmed_slots(self):
        geometry = augment_geometry(augment_observation(), (3840, 2160))
        entities = {0: SelectionEntity('hex', '42', '黑铁资产', identity_confirmed=True),
                    1: SelectionEntity('hex', 'unknown', '应急护甲 I', identity_confirmed=False)}
        cards = geometry.cards(entities)
        self.assertEqual([(card.slot, card.entity.entity_id) for card in cards], [('0', '42')])
        self.assertGreater(cards[0].selectable.right - cards[0].selectable.left, 265)
        self.assertGreater(cards[0].selectable.bottom - cards[0].selectable.top, 87)

    def test_metadata_signature_reuses_identical_identity_but_detects_changed_candidate(self):
        geometry = augment_geometry(augment_observation(), (3840, 2160))
        first = {0: SelectionEntity('hex', '42', '黑铁资产', identity_confirmed=True)}
        second = {0: SelectionEntity('hex', '43', '进攻宣告', identity_confirmed=True)}
        self.assertEqual(geometry.semantic_signature(first), geometry.semantic_signature(dict(first)))
        self.assertNotEqual(geometry.semantic_signature(first), geometry.semantic_signature(second))
        self.assertEqual(len(geometry.semantic_signature(first)), 64)

    def test_three_four_five_cards_keep_buttons_outside_safe_interiors(self):
        for count in (3, 4, 5):
            first = (960 - (count - 1) * 140 - 96) / 2
            boxes = [(first + i * 140, 501, first + 96 + i * 140, 601) for i in range(count)]
            geometry = item_geometry(boxes, (960, 720), category='completed')
            self.assertEqual(len(geometry.regions), count)
            for slot, (left, top, right, bottom) in enumerate(boxes):
                self.assertEqual(geometry.slot_at((left + right) / 2, 560), str(slot))
                self.assertIsNone(geometry.slot_at((left + right) / 2, 621))
                self.assertTrue(any(rect.contains((left + right) / 2, 621) for rect in geometry.exclusions))

    def test_malformed_or_mixed_item_boxes_cannot_propose_game_choice(self):
        for boxes in ([], [(100, 500, 196, 601)], [(100, 500, 196, 601)] * 3,
                      [(100, 500, 196, 601), (240, 200, 336, 301), (380, 500, 476, 601)],
                      [(100, 500, 196, 601), (240, 500, 336, 601), (380, 500, 476, float('nan'))]):
            self.assertIsNone(item_geometry(boxes, (960, 720), category='completed'))
        self.assertIsNone(item_geometry([(100, 500, 196, 601), (240, 500, 336, 601), (380, 500, 476, 601)],
                                       (960, 720), category='mixed_rewards'))

    def test_radiant_proposal_does_not_claim_real_category_click_accepted(self):
        geometry = item_geometry([(292, 500, 388, 601), (432, 500, 528, 601), (572, 500, 668, 601)],
                                 (960, 720), category='radiant')
        self.assertIn('radiant', geometry.layout_id)
        self.assertFalse(geometry.layout_verified)

    def test_geometry_is_frozen_and_never_carries_image_pixels(self):
        geometry = augment_geometry(augment_observation(), (3840, 2160))
        with self.assertRaises(AttributeError):
            geometry.layout_verified = True
        self.assertFalse(hasattr(geometry, 'image'))

    def test_real_native_five_radiant_cards_cannot_be_misread_as_right_three(self):
        # These three rectangles are the actual partial detector result on the
        # 2026-10-06 4K native five-choice frame; its two bright left cards were missed.
        partial = [(1744, 1604, 2132, 2000), (2304, 1604, 2692, 2000),
                   (2864, 1604, 3252, 2000)]
        self.assertIsNone(item_geometry(partial, (3840, 2160), category='radiant'))

    def test_real_native_five_radiant_safe_regions_keep_all_five_details_buttons_out(self):
        full = [(624, 1604, 1012, 2000), (1184, 1604, 1572, 2000),
                (1744, 1604, 2132, 2000), (2304, 1604, 2692, 2000),
                (2864, 1604, 3252, 2000)]
        geometry = item_geometry(full, (3840, 2160), category='radiant')
        for slot, x in enumerate((818, 1378, 1938, 2498, 3058)):
            self.assertEqual(geometry.slot_at(x, 1820), str(slot))
            self.assertIsNone(geometry.slot_at(x, 2075))
            self.assertTrue(any(rect.contains(x, 2075) for rect in geometry.exclusions))
        self.assertFalse(geometry.layout_verified)

    def test_size_and_screen_arguments_are_defensively_validated(self):
        for size in (None, (100, 100), (float('nan'), 2160), (3840,)):
            self.assertIsNone(augment_geometry(augment_observation(), size))
        for rect in ((0, 0, 0, 1080), (0, 0, 1920), (0, 0, float('inf'), 1080)):
            self.assertIsNone(augment_geometry(augment_observation(), (3840, 2160), screen_rect=rect))


if __name__ == '__main__':
    unittest.main()
