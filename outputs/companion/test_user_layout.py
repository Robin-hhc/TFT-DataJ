import json
import unittest
from bootstrap import ROOT
from choice_reader import read_choice


class UserLayoutTest(unittest.TestCase):
    def setUp(self):
        self.records=json.loads((ROOT/'work/user-game-sample/ocr.json').read_text(encoding='utf-8'))

    def test_headerless_selection(self):
        observed=read_choice(self.records,(3840,2160))
        self.assertEqual(observed['scene'],'choice_candidates')
        self.assertEqual(observed['round'],'2-1')
        self.assertEqual([x['raw_text'] for x in observed['cards']],['黑铁资产','应急护甲I','进攻宣告'])

    def test_titles_alone_are_not_selection(self):
        records=[r for r in self.records if r['text']!='C']
        self.assertNotEqual(read_choice(records,(3840,2160))['scene'],'choice_candidates')

    def test_missing_one_refresh_is_not_selection(self):
        records=list(self.records)
        records.remove(next(r for r in records if r['text']=='C'))
        self.assertNotEqual(read_choice(records,(3840,2160))['scene'],'choice_candidates')


if __name__=='__main__':unittest.main()
