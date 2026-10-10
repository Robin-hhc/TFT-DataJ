import json,unittest
from PIL import Image
from bootstrap import ROOT
from vision import Vision

class LiveImageTest(unittest.TestCase):
    def test_real_2_1_names(self):
        catalog=json.loads((ROOT/'work/s18-refresh-20260926/catalog.json').read_text(encoding='utf-8'))['data']['hex']
        result=Vision().analyze_fast(Image.open(ROOT/'work/companion/live-validation/choice-2-1.png').convert('RGB'),catalog)
        self.assertEqual(result['round'],'2-1')
        self.assertEqual(result['scene'],'choice_candidates')
        self.assertEqual([c['resolution'].get('id') for c in result['cards']],['1023','1479','1006'])

if __name__=='__main__':unittest.main()
