import unittest
from unittest.mock import patch
from PIL import Image
from bootstrap import ROOT
from scene_gate import may_be_choice
from vision import Vision

class SceneGateTest(unittest.TestCase):
    def test_real_choice_and_disabled_refresh(self):
        for file in ['work/user-game-sample/choice.png','work/user-game-sample/live-failure/frame-2.png','work/s18-video-next/frame-0047s.png']:
            with Image.open(ROOT/file) as image:self.assertTrue(may_be_choice(image),file)

    def test_real_board_does_not_start_ocr(self):
        for file in ['work/user-game-sample/live-failure/frame-0.png','work/s18-video-next/frame-1020s.png']:
            with Image.open(ROOT/file) as image:self.assertFalse(may_be_choice(image),file)

    def test_board_never_initializes_heavy_engine(self):
        with patch('vision.build_engine',side_effect=AssertionError('unexpected OCR initialization')):
            with Image.open(ROOT/'work/user-game-sample/live-failure/frame-0.png') as image:
                result=Vision().analyze(image,[])
                self.assertEqual(result['reason'],'no_refresh_glyphs')

if __name__=='__main__':unittest.main()
