import unittest
from PIL import Image, ImageDraw
from core import resolve_description
from vision import tracked_signature, unchanged


class DescriptionResolutionTests(unittest.TestCase):
    def setUp(self):
        self.ambiguous={'status':'ambiguous','readings':['兽性本能']*3,'candidates':[
            {'id':'a','name':'兽性本能','descText':'获得【蔚】和【奈德丽】'},
            {'id':'b','name':'兽性本能','descText':'获得【蔚】和【希维尔】'}]}

    def test_unique_entity_requires_two_views(self):
        self.assertEqual(resolve_description(self.ambiguous,['获得奈德丽']*2)['id'],'a')
        self.assertEqual(resolve_description(self.ambiguous,['获得希维尔']*2)['id'],'b')
        for readings in (['蔚']*2,['奈德丽',''],['奈德丽','希维尔'],['奈德丽希维尔']*2):
            self.assertEqual(resolve_description(self.ambiguous,readings)['status'],'ambiguous')

    def test_title_evidence_still_required(self):
        self.ambiguous['readings']=['兽性本能']
        self.assertEqual(resolve_description(self.ambiguous,['奈德丽']*2)['status'],'ambiguous')

    def test_description_changes_invalidate_same_title(self):
        image=Image.new('RGB',(640,360),'black')
        draw=ImageDraw.Draw(image)
        draw.rectangle((145,125,160,132),fill='white')
        draw.rectangle((145,150,160,159),fill='white')
        observation={'layout_method':'three_refresh_controls','cards':[{
            'box':[[130,120],[180,120],[180,135],[130,135]],
            'description_box':[[130,145],[200,145],[200,175],[130,175]]}]}
        original=tracked_signature(image,observation)
        self.assertTrue(unchanged(original,tracked_signature(image.copy(),observation)))
        ImageDraw.Draw(image).rectangle((185,150,195,160),fill='white')
        self.assertFalse(unchanged(original,tracked_signature(image,observation)))


if __name__=='__main__':unittest.main()
