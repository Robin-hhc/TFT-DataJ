import unittest
from types import SimpleNamespace
from vision import confident_round, Vision
import numpy as np
from PIL import Image


class RoundReaderTests(unittest.TestCase):
    def result(self, text, scores, words=None):
        return SimpleNamespace(txts=[text], word_results=[SimpleNamespace(
            words=words or [list(text)], confs=scores)])

    def test_icon_score_does_not_hide_confident_digits(self):
        result=self.result('¿2-1',[.2,.99,.96,.99])
        self.assertEqual(confident_round(result)['value'],'2-1')

    def test_uncertain_digit_rejected(self):
        self.assertIsNone(confident_round(self.result('急4-2',[.1,.53,.95,.99])))

    def test_ambiguous_or_misaligned_evidence_rejected(self):
        self.assertIsNone(confident_round(self.result('2-1 4-2',[.99]*7)))
        self.assertIsNone(confident_round(self.result('2-1',[.99]*2)))
        self.assertIsNone(confident_round(self.result('2-1',[.99]*3,[['3','-','1']])))
        self.assertIsNone(confident_round(self.result('12-1',[.99]*4)))

    def test_conflicting_top_boxes_are_not_overwritten(self):
        vision=Vision()
        full=SimpleNamespace(txts=['请选择一个强化符文','2-1','4-2'],scores=[.99,.8,.8],
            boxes=np.array([[[200,22],[440,22],[440,34],[200,34]],
                            [[220,1],[250,1],[250,15],[220,15]],
                            [[300,1],[330,1],[330,15],[300,15]]]))
        results=iter([full,self.result('2-1',[.99]*3),self.result('2-1',[.99]*3),
                      self.result('4-2',[.99]*3),self.result('4-2',[.99]*3)])
        vision.engine=lambda *args,**kwargs:next(results)
        self.assertIsNone(vision.analyze(Image.new('RGB',(640,360)),[])['round'])


if __name__=='__main__':unittest.main()
