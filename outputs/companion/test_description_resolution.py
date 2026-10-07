import unittest
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image, ImageDraw
from core import resolve_description
from vision import Vision, tracked_signature, unchanged


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

    def test_real_same_title_numeric_variants_require_two_matching_stat_terms_in_both_views(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/hex-identity-20261007.json').read_text(encoding='utf-8'))
        candidates=[row for row in fixture['catalog'] if row['name']=='成吨的属性！']
        resolution={'status':'ambiguous','candidates':candidates,'readings':['成吨的属性！']*3}
        for text,identity in [('你的弈子们获得44生命值、4%物理加成、4%法术加成','2705'),
                              ('你的弈子们获得88生命值、8%物理加成、8%法术加成','3705')]:
            self.assertEqual(resolve_description(resolution,[text]*2)['id'],identity)
        for readings in (['44生命值']*2,['144生命值、14%物理加成']*2,
                         ['88生命值、4%物理加成、4%法术加成']*2,
                         ['44生命值、8%物理加成、8%法术加成']*2,
                         ['44生命值、4%物理加成','4护甲、4魔抗'],
                         ['44生命值、4%物理加成','88生命值、8%物理加成'],
                         ['44生命值、4%物理加成',''],
                         ['44生命值、4%物理加成、88生命值、8%物理加成']*2):
            with self.subTest(readings=readings):
                self.assertEqual(resolve_description(resolution,readings)['status'],'ambiguous')
        resolution['readings']=['成吨的属性！']
        self.assertEqual(resolve_description(resolution,['44生命值、4%物理加成']*2)['status'],'ambiguous')

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

    def test_live_numeric_fallback_reads_description_and_tracks_it(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/hex-identity-20261007.json').read_text(encoding='utf-8'))
        candidates=[row for row in fixture['catalog'] if row['name']=='成吨的属性！']
        ambiguous={'status':'ambiguous','candidates':candidates,'readings':['成吨的属性！']*3}
        known={'status':'resolved','id':'1625','name':'别再错过','readings':['别再错过']*3}
        image=Image.new('RGB',(1920,1080),'black')
        ImageDraw.Draw(image).rectangle((820,450,1000,470),fill='white')
        vision=Vision()
        calls=[]
        def engine(*args,**kwargs):
            calls.append(True)
            return SimpleNamespace(txts=['获得44生命值、4%物理加成'],scores=[.98])
        vision.engine=engine
        with patch('vision.may_be_choice',return_value=True),patch.object(vision,'read_round_crop',return_value='4-2'),\
             patch.object(vision,'read_name',side_effect=[known,ambiguous,known]):
            observation=vision.analyze_fast(image,fixture['catalog'])
        self.assertEqual(observation['cards'][1]['resolution']['id'],'2705')
        self.assertEqual(len(calls),2)
        self.assertIn('description_box',observation['cards'][1])
        before=tracked_signature(image,observation)
        ImageDraw.Draw(image).rectangle((1050,450,1070,470),fill='white')
        self.assertFalse(unchanged(before,tracked_signature(image,observation)))


if __name__=='__main__':unittest.main()
