"""Condition input is authorised by a bounded title, never description text."""
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

from condition_reader import ConditionReader
from entity_identity import EntityResolver


CATALOG = {
    'hero': [{'id': '14503', 'name': '阿木木', 'setId': '18'},
             {'id': '24503', 'name': '阿木木', 'setId': '18'},
             {'id': '11506', 'name': '阿卡丽', 'setId': '18', 'tag': 'AD'},
             {'id': '11513', 'name': '阿卡丽', 'setId': '18', 'tag': 'AP'}],
    'equip': [{'id': '2010', 'name': '巨人杀手', 'type': '成型装备'},
              {'id': '1010', 'name': '金锅锅', 'type': '基础装备'},
              {'id': '41803', 'name': '魔女纹章', 'type': '转职纹章'}],
    'hex': [{'id': '1', 'name': '应急护甲 I', 'level': 1},
            {'id': '2', 'name': '应急护甲 II', 'level': 2}],
}


class FakeVision:
    def __init__(self, readings):
        self.readings = readings
        self.calls = []

    def read_name(self, crop, catalogue):
        self.calls.append((crop.size, list(catalogue)))
        return {'status': 'unrecognized', 'readings': list(self.readings), 'candidates': []}


def title_scene(rect=(240, 125, 500, 185)):
    # A synthetic text region verifies boundary behavior only, not OCR accuracy.
    image = Image.new('RGB', (1280, 720), '#775f66')
    ImageDraw.Draw(image).rectangle((rect[0]+12, rect[1]+12, rect[0]+140, rect[1]+28), fill='white')
    return image


class ConditionReaderTests(unittest.TestCase):
    def reader(self, readings):
        vision = FakeVision(readings)
        return ConditionReader(vision, EntityResolver(CATALOG)), vision

    @patch('condition_reader.may_be_choice', return_value=False)
    @patch('condition_reader.item_boxes', return_value=[])
    def test_explicit_primary_title_maps_hero_to_basic_id_without_star(self, *_):
        reader, vision = self.reader(['阿木木', '阿木木', '阿木木'])
        result = reader.read(title_scene(), title_rect=(240, 125, 500, 185), kind='hero')
        self.assertEqual(result['status'], 'resolved')
        self.assertEqual(result['entity']['id'], '4503')
        self.assertNotIn('num', result['entity'])
        self.assertEqual(result['route'], 'detail')
        self.assertEqual(vision.calls[0][0], (260, 60))
        self.assertEqual(result['evidence']['layout'], 'explicit_primary_title')
        self.assertFalse(result['records_selected'])

    @patch('condition_reader.may_be_choice', return_value=False)
    @patch('condition_reader.item_boxes', return_value=[])
    def test_two_direct_views_required_and_conflicting_suffix_never_queries(self, *_):
        for readings in (['巨人杀手', '', ''], ['应急护甲 I', '应急护甲 II', '应急护甲 I']):
            with self.subTest(readings=readings):
                reader, _ = self.reader(readings)
                result = reader.read(title_scene(), title_rect=(240, 125, 500, 185))
                self.assertEqual(result['status'], 'unknown')
                self.assertIsNone(result['entity'])

    @patch('condition_reader.may_be_choice', return_value=False)
    @patch('condition_reader.item_boxes', return_value=[])
    def test_same_named_hero_forms_remain_ambiguous(self, *_):
        reader, _ = self.reader(['阿卡丽', '阿卡丽', '阿卡丽'])
        result = reader.read(title_scene(), title_rect=(240, 125, 500, 185), kind='hero')
        self.assertEqual(result['status'], 'ambiguous')
        self.assertIsNone(result['entity'])
        self.assertEqual({row['id'] for row in result['candidates']}, {'1506', '1513'})

    @patch('condition_reader.may_be_choice', return_value=True)
    def test_choice_page_routes_to_augment_stats_even_when_names_unresolved(self, *_):
        reader, vision = self.reader(['巨人杀手']*3)
        result = reader.read(title_scene(), title_rect=(240, 125, 500, 185))
        self.assertEqual(result['route'], 'augment_stats')
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(vision.calls, [])

    @patch('condition_reader.may_be_choice', return_value=False)
    @patch('condition_reader.item_boxes', return_value=[(240, 550, 380, 680), (500, 550, 640, 680), (760, 550, 900, 680)])
    def test_verified_equipment_header_is_mutually_exclusive(self, *_):
        reader, vision = self.reader(['选择一件']*3)
        result = reader.read(title_scene())
        self.assertEqual(result['route'], 'equipment_stats')
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(len(vision.calls), 1)

    @patch('condition_reader.may_be_choice', return_value=False)
    @patch('condition_reader.item_boxes', return_value=[(240, 550, 380, 680), (500, 550, 640, 680), (760, 550, 900, 680)])
    def test_unconfirmed_choice_header_never_falls_through_to_detail(self, *_):
        reader, vision = self.reader(['巨人杀手']*3)
        result = reader.read(title_scene(), title_rect=(240, 125, 500, 185))
        self.assertEqual(result['route'], 'equipment_stats')
        self.assertEqual(result['reason'], 'equipment_choice_header_unconfirmed')
        self.assertIsNone(result['entity'])
        self.assertEqual(len(vision.calls), 1)

    @patch('condition_reader.may_be_choice', return_value=False)
    @patch('condition_reader.item_boxes', return_value=[(180, 600, 315, 710), (318, 600, 453, 710), (456, 600, 591, 710)])
    def test_contiguous_shop_proposal_does_not_steal_a_detail_trigger(self, *_):
        reader, vision = self.reader(['巨人杀手']*3)
        result = reader.read(title_scene(), title_rect=(240, 125, 500, 185))
        self.assertEqual(result['route'], 'detail')
        self.assertEqual(result['entity']['id'], '2010')
        self.assertEqual(len(vision.calls), 1)

    @patch('condition_reader.may_be_choice', return_value=False)
    @patch('condition_reader.item_boxes', return_value=[])
    def test_equipment_emblem_and_augment_suffix_keep_exact_identity(self, *_):
        for name, kind, identity in (('巨人杀手', 'equip', '2010'), ('魔女纹章', 'equip', '41803'),
                                      ('应急护甲 I', 'hex', '1'), ('应急护甲 II', 'hex', '2')):
            with self.subTest(name=name):
                reader, _ = self.reader([name]*3)
                result = reader.read(title_scene(), title_rect=(240, 125, 500, 185), kind=kind)
                self.assertEqual(result['status'], 'resolved')
                self.assertEqual(result['entity']['id'], identity)
                self.assertEqual(result['entity']['kind'], kind)
                self.assertFalse(result['records_selected'])

    @patch('condition_reader.may_be_choice', return_value=False)
    @patch('condition_reader.item_boxes', return_value=[])
    @patch('condition_reader.detail_boxes', return_value=[(200, 120, 460, 360)])
    def test_flat_body_region_without_header_icon_does_not_read_a_name(self, *_):
        reader, vision = self.reader(['巨人杀手']*3)
        result = reader.read(title_scene())
        self.assertEqual(result['reason'], 'detail_header_icon_unconfirmed')
        self.assertEqual(vision.calls, [])

    @patch('condition_reader.may_be_choice', return_value=False)
    @patch('condition_reader.item_boxes', return_value=[])
    @patch('condition_reader.detail_boxes', return_value=[(200, 120, 460, 360)])
    @patch('condition_reader._header_icon_visible', side_effect=[False, True])
    def test_large_icon_layout_reads_only_the_first_header_title(self, *_):
        image=Image.new('RGB',(1280,720),'#1d2630')
        draw=ImageDraw.Draw(image)
        draw.rectangle((310,144,380,155),fill='white')
        draw.rectangle((310,260,400,275),fill='white')  # wearer/body excluded
        reader,vision=self.reader(['巨人杀手']*3)
        result=reader.read(image)
        self.assertEqual(result['entity']['id'],'2010')
        self.assertEqual(result['evidence']['layout'],'s18_floating_large_icon_title')
        self.assertLess(result['evidence']['title_rect'][3],180)
        self.assertEqual(len(vision.calls),1)

    @patch('condition_reader.may_be_choice', return_value=False)
    @patch('condition_reader.item_boxes', return_value=[])
    @patch('condition_reader.detail_boxes', return_value=[(200, 120, 460, 360)])
    @patch('condition_reader._header_icon_visible', side_effect=[False, True])
    def test_large_icon_title_does_not_fall_back_to_a_known_wearer_name(self, *_):
        image=Image.new('RGB',(1280,720),'#1d2630')
        draw=ImageDraw.Draw(image)
        draw.rectangle((310,144,380,155),fill='white')
        draw.rectangle((310,260,400,275),fill='white')
        reader,vision=self.reader(['未列入目录的标题']*3)
        result=reader.read(image)
        self.assertEqual(result['status'],'unknown')
        self.assertIsNone(result['entity']);self.assertEqual(len(vision.calls),1)

    @patch('condition_reader.may_be_choice', return_value=False)
    @patch('condition_reader.item_boxes', return_value=[])
    def test_missing_panel_unsupported_size_or_bad_rectangle_has_no_ocr(self, *_):
        reader, vision = self.reader(['巨人杀手']*3)
        for image, rect in ((Image.new('RGB', (1280, 720), '#775f66'), None),
                            (Image.new('RGB', (400, 300)), None),
                            (title_scene(), (-1, 20, 300, 100)),
                            (title_scene(), (0, 0, 1280, 720))):
            with self.subTest(size=image.size, rect=rect):
                self.assertEqual(reader.read(image, title_rect=rect)['status'], 'unknown')
        self.assertEqual(vision.calls, [])

    @patch('condition_reader.may_be_choice', return_value=False)
    @patch('condition_reader.item_boxes', return_value=[])
    def test_clipped_title_cannot_authorise_identity(self, *_):
        reader, vision = self.reader(['巨人杀手']*3)
        image = title_scene()
        ImageDraw.Draw(image).rectangle((240, 137, 280, 152), fill='white')
        result = reader.read(image, title_rect=(240, 125, 500, 185))
        self.assertEqual(result['reason'], 'title_touches_boundary')
        self.assertEqual(vision.calls, [])

    @patch('condition_reader.may_be_choice', return_value=False)
    @patch('condition_reader.item_boxes', return_value=[])
    def test_body_text_is_never_passed_to_ocr(self, *_):
        reader, vision = self.reader(['未列入目录的标题']*3)
        result = reader.read(title_scene(), title_rect=(240, 125, 500, 185))
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(len(vision.calls), 1)
        self.assertEqual(vision.calls[0][0], (260, 60))

    @patch('condition_reader.may_be_choice', return_value=False)
    @patch('condition_reader.item_boxes', return_value=[])
    @patch('condition_reader.detail_boxes', return_value=[(200, 120, 460, 360), (600, 120, 860, 360)])
    def test_multiple_panels_require_point_inside_one_panel(self, *_):
        reader, vision = self.reader(['巨人杀手']*3)
        result = reader.read(title_scene(), trigger_point=(1100, 600))
        self.assertEqual(result['reason'], 'multiple_detail_panels')
        self.assertEqual(vision.calls, [])

    @patch('condition_reader.may_be_choice', return_value=False)
    @patch('condition_reader.item_boxes', return_value=[])
    def test_inventory_recipe_layout_reads_header_only(self, *_):
        # Pure proposal/crop test. These blocks are not real OCR evidence.
        image = Image.new('RGB', (1280, 720), '#775f66')
        draw = ImageDraw.Draw(image)
        draw.rectangle((90, 10, 390, 600), fill='#1d2630', outline='#7c673d', width=3)
        draw.rectangle((112, 31, 168, 86), fill='#dfaa29')
        draw.rectangle((122, 38, 156, 75), fill='#294eb5')
        draw.rectangle((185, 35, 280, 50), fill='white')
        for y in (190, 280, 370):
            draw.rectangle((185, y, 350, y+16), fill='white')
        reader, vision = self.reader(['金锅锅']*3)
        result = reader.read(image)
        self.assertEqual(result['status'], 'resolved', result)
        self.assertEqual(result['entity']['id'], '1010')
        self.assertEqual(result['evidence']['layout'], 's18_left_inventory_detail')
        self.assertLess(result['evidence']['title_rect'][3], 100)
        self.assertEqual(len(vision.calls), 1)
        self.assertFalse(result['records_selected'])

    @patch('condition_reader.may_be_choice', return_value=False)
    @patch('condition_reader.item_boxes', return_value=[])
    def test_inventory_recipe_body_without_complete_header_is_not_a_title(self, *_):
        image = Image.new('RGB', (1280, 720), '#775f66')
        draw = ImageDraw.Draw(image)
        # No complete top/bottom border and no header icon. Body text exists.
        draw.rectangle((90, 0, 390, 600), fill='#1d2630')
        draw.rectangle((90, 0, 92, 600), fill='#7c673d')
        draw.rectangle((388, 0, 390, 600), fill='#7c673d')
        draw.rectangle((185, 200, 350, 216), fill='white')
        reader, vision = self.reader(['魔女纹章']*3)
        result = reader.read(image)
        self.assertEqual(result['status'], 'unknown')
        self.assertIsNone(result['entity'])
        self.assertEqual(vision.calls, [])


if __name__ == '__main__':
    unittest.main()
