import unittest
import numpy as np
from vision import unchanged, tracked_signature, TextSignature
from PIL import Image, ImageDraw


class FrameGuardTests(unittest.TestCase):
    def test_small_title_change_is_not_diluted(self):
        previous=np.zeros((360,640),dtype=np.int16)
        changed=previous.copy();changed[150:155,100:110]=180
        self.assertFalse(unchanged(previous,changed))
        self.assertTrue(unchanged(previous,previous.copy()))

    def test_missing_or_resized_is_changed(self):
        self.assertFalse(unchanged(None,None))
        self.assertFalse(unchanged(np.zeros((2,2)),np.zeros((3,3))))

    def test_board_animation_ignored_but_title_band_watched(self):
        image=Image.new('RGB',(640,360),'black')
        draw=ImageDraw.Draw(image)
        for rect in [(240,24,250,30),(226,3,231,12),(150,151,155,159)]:draw.rectangle(rect,fill='white')
        obs={'header_box':[[220,22],[420,22],[420,34],[220,34]],
             'round_box':[[222,1],[248,1],[248,15],[222,15]],
             'cards':[{'box':[[150,150],[170,150],[170,160],[150,160]]}]}
        baseline=tracked_signature(image,obs)
        board=image.copy();ImageDraw.Draw(board).rectangle((0,250,640,360),fill='white')
        self.assertTrue(unchanged(baseline,tracked_signature(board,obs)))
        title=image.copy();ImageDraw.Draw(title).rectangle((190,150,210,160),fill='white')
        self.assertFalse(unchanged(baseline,tracked_signature(title,obs)))
        header=image.copy();ImageDraw.Draw(header).rectangle((240,24,280,30),fill='white')
        self.assertFalse(unchanged(baseline,tracked_signature(header,obs)))

    def test_empty_strokes_rejected_and_new_suffix_invalidates(self):
        blank=np.zeros((20,100),dtype=bool)
        self.assertFalse(unchanged(TextSignature((blank,)),TextSignature((blank.copy(),))))
        ink=blank.copy();ink[4:16,10:14]=True
        suffix=ink.copy();suffix[4:16,70:73]=True
        self.assertFalse(unchanged(TextSignature((ink,)),TextSignature((suffix,))))
        jitter=np.roll(ink,1,axis=1)
        self.assertTrue(unchanged(TextSignature((ink,)),TextSignature((jitter,))))


if __name__=='__main__':unittest.main()
