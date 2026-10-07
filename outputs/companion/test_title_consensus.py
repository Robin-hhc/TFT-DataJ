import unittest
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image, ImageDraw
from vision import Vision


class TitleConsensusTests(unittest.TestCase):
    def recognize(self, outputs, catalog=None, glyph=None):
        image=Image.new('RGB',(160,45),'black')
        ImageDraw.Draw(image).rectangle((20,10,110,32),fill='white')
        stream=iter(outputs)
        vision=Vision()
        def engine(*args,**kwargs):
            text,score=next(stream)
            return SimpleNamespace(txts=[text],scores=[score])
        vision.engine=engine
        if catalog is None:catalog=[{'id':'1','name':'护甲 I'},{'id':'2','name':'护甲 II'}]
        with patch('vision.roman_evidence',return_value=glyph):
            return vision.read_name(image,catalog)

    def test_two_exact_high_confidence_views_required(self):
        initial=[('',0)]*5
        self.assertEqual(self.recognize(initial+[('护甲 I',.95)]*2)['id'],'1')
        self.assertEqual(self.recognize(initial+[('护甲 I',.95),('护甲 I',.89)])['status'],'unrecognized')

    def test_numeric_suffix_not_rewritten(self):
        self.assertEqual(self.recognize([('护甲1',.99)]*7)['status'],'unrecognized')

    def test_disagreement_rejected(self):
        self.assertEqual(self.recognize([('',0)]*5+[('护甲 I',.99),('护甲 II',.99)])['status'],'conflict')
        self.assertEqual(self.recognize([('护甲 II',.99)]+[('',0)]*4+[('护甲 I',.99)]*2)['status'],'conflict')

    def celestial_catalog(self):
        return [{'id':'2022','name':'星界赐福 II','level':2},
                {'id':'3022','name':'星界赐福 III','level':3}]

    def test_real_quality_names_still_require_complete_exact_consensus(self):
        catalog=self.celestial_catalog()
        for text,identity in [('星界赐福Ⅱ','2022'),('星界赐福Ⅲ','3022')]:
            with self.subTest(text=text):
                self.assertEqual(self.recognize([(text,.99)]*3,catalog)['id'],identity)
        for text in ('星界喝福Ⅲ','星界赐福111','星界赐福lll','星界赐福II1',
                     '星界赐福IIl','星界赐福IIII','星界赐福'):
            with self.subTest(text=text):
                self.assertNotEqual(self.recognize([(text,.99)]*7,catalog)['status'],'resolved')

    def test_real_quality_conflict_cannot_be_outvoted_by_retry_views(self):
        output=[('星界赐福Ⅱ',.99)]+[('',0)]*4+[('星界赐福Ⅲ',.99)]*2
        self.assertEqual(self.recognize(output,self.celestial_catalog())['status'],'conflict')

    def test_one_or_low_confidence_quality_read_is_not_confirmation(self):
        for output in ([('',0)]*5+[('星界赐福Ⅲ',.99),('',0)],
                       [('',0)]*5+[('星界赐福Ⅲ',.99),('星界赐福Ⅲ',.899)]):
            with self.subTest(output=output):
                self.assertEqual(self.recognize(output,self.celestial_catalog())['status'],'unrecognized')

    def test_duplicate_exact_quality_name_remains_ambiguous(self):
        catalog=self.celestial_catalog()+[{'id':'other','name':'星界赐福 III','level':3}]
        self.assertEqual(self.recognize([('星界赐福Ⅲ',.99)]*3,catalog)['status'],'ambiguous')

    def test_roman_pixel_suggestion_does_not_authorize_automatic_identity(self):
        output=[('星界赐福IIl',.99)]*7+[('星界赐福',.99)]*2
        glyph={'roman':'III','prefix_right':110,'suffix_left':120}
        result=self.recognize(output,self.celestial_catalog(),glyph)
        self.assertEqual(result['status'],'needs_confirmation')
        self.assertEqual(result['suggested_id'],'3022')
        self.assertNotIn('id',result)


if __name__=='__main__':unittest.main()
