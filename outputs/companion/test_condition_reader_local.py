"""Private original S18 screenshot evidence, excluded from clean public CI."""
import json
import unittest
from PIL import Image
from bootstrap import ROOT
from condition_reader import ConditionReader
from entity_identity import EntityResolver
from vision import Vision


class LocalConditionScreenshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = ROOT/'work/condition-input-experiment'
        catalog_path = ROOT/'work/s18-refresh-20260926/catalog.json'
        if not (cls.folder/'next-507s.png').exists() or not catalog_path.exists():
            raise unittest.SkipTest('Local S18 detail screenshots are not installed')
        catalog = json.loads(catalog_path.read_text(encoding='utf-8'))['data']
        cls.vision = Vision()
        cls.vision.prepare()
        cls.reader = ConditionReader(cls.vision, EntityResolver(catalog))

    def read(self, name, **options):
        with Image.open(self.folder/name) as image:
            return self.reader.read(image.convert('RGB'), **options)

    def test_original_16_9_s18_hero_details_keep_basic_ids(self):
        for name, identity in (('next-507s.png', '1510'), ('next-1242s.png', '5456'),
                               ('next-1500s.png', '1500'), ('next-2046s.png', '4509')):
            with self.subTest(name=name):
                result = self.read(name)
                self.assertEqual(result['status'], 'resolved')
                self.assertEqual(result['entity']['id'], identity)
                self.assertEqual(result['evidence']['layout'], 's18_right_hero_detail')
                self.assertFalse(result['records_selected'])

    def test_same_named_hero_forms_and_actual_noncondition_panels_are_not_guessed(self):
        ambiguous = self.read('next-1050s.png')
        self.assertEqual(ambiguous['status'], 'ambiguous')
        self.assertEqual({row['id'] for row in ambiguous['candidates']}, {'4507', '4515'})
        for name in ('next-400s.png', 'next-1240s.png', 'next-645s.png'):
            with self.subTest(name=name):
                self.assertIsNone(self.read(name)['entity'])

    def test_real_choice_scene_cannot_fall_through_to_tooltip(self):
        result = self.read('next-45s.png')
        self.assertEqual(result['route'], 'augment_stats')
        self.assertIsNone(result['entity'])

    def test_native_4k_inventory_recipe_panel_reads_only_the_gold_pan_title(self):
        path = ROOT/'work/input-experiments/match-20261006/selected-book-native.png'
        if not path.exists():
            self.skipTest('Native 4K inventory detail is not installed')
        with Image.open(path) as image:
            result = self.reader.read(image.convert('RGB'))
            self.assertEqual(result['status'], 'resolved', result)
            self.assertEqual(result['entity']['id'], '1010')
            self.assertEqual(result['entity']['type'], '基础装备')
            self.assertEqual(result['evidence']['layout'], 's18_left_inventory_detail')
            self.assertLess(result['evidence']['title_rect'][3], image.height*.15)
            self.assertEqual({value for value in result['evidence']['readings'] if value}, {'金锅锅'})
            self.assertFalse(result['records_selected'])


if __name__ == '__main__':
    unittest.main()
