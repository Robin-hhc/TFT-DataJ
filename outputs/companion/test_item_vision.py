import json
from pathlib import Path
import unittest
from PIL import Image
from bootstrap import ROOT
from vision import Vision, TextSignature
from item_vision import analyze_items, item_boxes, item_signature, same_item_text


class ItemReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=ROOT/'work/item-choice-samples'
        cls.catalog_file=ROOT/'work/s18-refresh-20260926/catalog.json'
        if not (cls.folder/'user-p3-720p-2232s.png').exists() or not cls.catalog_file.exists():
            raise unittest.SkipTest('Local S18 original video fixtures are not installed')
        cls.catalog=json.loads(cls.catalog_file.read_text(encoding='utf-8'))['data']['equip']
        cls.vision=Vision();cls.vision.prepare()

    def read(self,name):
        with Image.open(self.folder/name) as image:
            return analyze_items(image.convert('RGB'),self.vision,self.catalog)

    def test_real_completed_and_artifact_ids_keep_slot_order(self):
        cases={
            'user-p1-720p-0288s.png':['2028','2038','2023','2007','2006'],
            'user-p2-720p-0753s.png':['2027','2025','2031','2029'],
            'user-p3-720p-2232s.png':['6058','6080','6096','6076'],
            'user-p3-720p-2838s.png':['2025','2029','2001','2038','2011'],
        }
        for filename, expected in cases.items():
            with self.subTest(filename=filename):
                result=self.read(filename)
                self.assertEqual(result['scene'],'item_candidates')
                self.assertEqual([c['resolution'].get('id') for c in result['cards']],expected)

    def test_unreadable_slot_never_gets_guessed_identity(self):
        result=self.read('user-p1-720p-0300s.png')
        self.assertEqual(result['scene'],'item_candidates')
        self.assertNotIn('id',result['cards'][1]['resolution'])
        self.assertEqual([c['resolution'].get('id') for c in result['cards']],
                         ['2012',None,'2038','2006','2005'])

    def test_blessings_and_mixed_rewards_do_not_trigger(self):
        for name in ('user-p1-720p-3045s.png','user-p3-720p-1533s.png','user-p3-720p-2106s.png','next-1485s.png'):
            with self.subTest(filename=name):self.assertEqual(self.read(name)['scene'],'unknown')

    def test_consecutive_video_frames_stay_visible_but_changed_slot_invalidates(self):
        signatures=[]
        for second in (288,289,290,300):
            path=self.folder/f'user-p1-720p-{second:04d}s.png'
            if not path.exists():self.skipTest('Consecutive original video fixtures are not installed')
            with Image.open(path) as frame:
                signatures.append(item_signature(frame,item_boxes(frame)))
        first,second,third,refreshed=signatures
        self.assertTrue(same_item_text(first,second))
        self.assertTrue(same_item_text(first,third))
        self.assertFalse(same_item_text(first,refreshed))
        # Only the second equipment title changes; all other regions stay exact.
        one_change=TextSignature(first.masks[:2]+(refreshed.masks[2],)+first.masks[3:])
        self.assertFalse(same_item_text(first,one_change))


class ItemInputTests(unittest.TestCase):
    def test_blank_or_tiny_frame_has_no_choice_layout(self):
        self.assertEqual(item_boxes(Image.new('RGB',(1920,1080))),[])
        self.assertEqual(item_boxes(Image.new('RGB',(480,360))),[])


if __name__=='__main__':unittest.main()
