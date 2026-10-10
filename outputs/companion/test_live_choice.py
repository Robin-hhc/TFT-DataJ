import json,unittest
from pathlib import Path
from PIL import Image
from bootstrap import ROOT
from vision import Vision
from snapshot_stats import stage_stat

class LiveImageTest(unittest.TestCase):
    def test_real_2_1_names(self):
        catalog=json.loads((ROOT/'work/s18-refresh-20260926/catalog.json').read_text(encoding='utf-8'))['data']['hex']
        result=Vision().analyze_fast(Image.open(ROOT/'work/companion/live-validation/choice-2-1.png').convert('RGB'),catalog)
        self.assertEqual(result['round'],'2-1')
        self.assertEqual(result['scene'],'choice_candidates')
        self.assertEqual([c['resolution'].get('id') for c in result['cards']],['1023','1479','1006'])

    def test_real_arcane_two_plus_title_preserves_exact_roman_and_plus_suffix(self):
        fixtures=Path(__file__).parent/'fixtures'
        expected=json.loads((fixtures/'hex-arcane-title-20261010.json').read_text(encoding='utf-8'))
        with Image.open(fixtures/'hex-arcane-title-20261010.png') as image:
            result=Vision().read_name(image,expected['catalog'])
        self.assertEqual(result['status'],'resolved')
        self.assertEqual(result['id'],'30679')
        self.assertEqual(result['name'],'秘法帮派 II++')
        self.assertEqual(stage_stat(expected['statistics'],result['id'],'4-2'),
                         {'status':'ok','avg_placement':4.53,'sample_count':376,'stage':'4-2'})
        self.assertEqual(stage_stat(expected['statistics'],result['id'],'3-2')['status'],
                         'no_stage_data')

if __name__=='__main__':unittest.main()
