import json
import unittest
from bootstrap import ROOT
from choice_reader import read_choice

class LiveFailureTest(unittest.TestCase):
    def test_disabled_refresh_counter_overlap(self):
        rows=json.loads((ROOT/'work/user-game-sample/live-failure/ocr.json').read_text(encoding='utf-8'))
        result=read_choice(rows,(3840,2160))
        self.assertEqual(result['scene'],'choice_candidates')
        self.assertEqual(result['round'],'4-2')
        self.assertEqual(len(result['cards']),3)

if __name__=='__main__':unittest.main()
