import unittest
from unittest.mock import patch
from PIL import Image
from vision import Vision

class PartialChoiceTest(unittest.TestCase):
    def test_one_confirmed_card_is_not_hidden(self):
        vision=Vision()
        known={'status':'resolved','id':'1006','name':'装备百宝袋 I','readings':['装备百宝袋I']}
        unknown={'status':'unrecognized','readings':[]}
        with patch('vision.may_be_choice',return_value=True), patch.object(vision,'read_round_crop',return_value='2-1'), patch.object(vision,'read_name',side_effect=[unknown,unknown,known]):
            result=vision.analyze_fast(Image.new('RGB',(1920,1080)),[])
        self.assertEqual(result['scene'],'choice_candidates')
        self.assertEqual([c['resolution'].get('id') for c in result['cards']],[None,None,'1006'])

if __name__=='__main__':unittest.main()
