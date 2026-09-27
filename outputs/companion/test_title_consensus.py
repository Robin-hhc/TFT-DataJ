import unittest
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image, ImageDraw
from vision import Vision


class TitleConsensusTests(unittest.TestCase):
    def recognize(self, outputs):
        image=Image.new('RGB',(160,45),'black')
        ImageDraw.Draw(image).rectangle((20,10,110,32),fill='white')
        stream=iter(outputs)
        vision=Vision()
        def engine(*args,**kwargs):
            text,score=next(stream)
            return SimpleNamespace(txts=[text],scores=[score])
        vision.engine=engine
        catalog=[{'id':'1','name':'护甲 I'},{'id':'2','name':'护甲 II'}]
        with patch('vision.roman_evidence',return_value=None):
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


if __name__=='__main__':unittest.main()
