import unittest
import numpy as np
from vision import unchanged, tracked_signature, TextSignature, _text_strokes
from PIL import Image, ImageDraw


class FrameGuardTests(unittest.TestCase):
    def test_roi_sampling_preserves_full_frame_stroke_masks(self):
        # Independent oracle: legacy whole-frame normalization, including a
        # non-integral scale and small Roman strokes. Extraction has separate
        # real-pixel and background-negative tests below.
        source=Image.new('RGB',(640,360),'#46403b');draw=ImageDraw.Draw(source)
        for x in range(60,250,7):
            draw.rectangle((x,120,x+2,134),fill=(190+x%40,)*3)
        for width,height in [(1280,720),(1920,1080),(3840,2160),(1366,768)]:
            with self.subTest(size=(width,height)):
                image=source.resize((width,height),Image.Resampling.BICUBIC)
                box=[[width*.18,height*.33],[width*.36,height*.33],
                     [width*.36,height*.39],[width*.18,height*.39]]
                obs={'layout_method':'three_refresh_controls','cards':[{'box':box}]}
                actual=tracked_signature(image,obs).masks[0]
                half=max(width*.09,(box[1][0]-box[0][0])/2+2);center=width*.27;s=640/width
                normalized=image.convert('RGB').resize((640,round(height*s)),Image.Resampling.LANCZOS)
                region=normalized.crop((round((center-half)*s),round((height*.33-1)*s),
                                        round((center+half)*s),round((height*.39+1)*s)))
                expected=_text_strokes(region)
                np.testing.assert_array_equal(actual,expected)

    def test_flat_lighting_smooth_gradients_and_dense_texture_are_not_text(self):
        samples=[Image.new('RGB',(116,20),color) for color in ('black','white','#999999')]
        gradient=np.tile(np.linspace(30,240,116,dtype=np.uint8),(20,1))
        samples.append(Image.fromarray(gradient).convert('RGB'))
        checker=(np.indices((20,116)).sum(axis=0)%2*255).astype(np.uint8)
        samples.append(Image.fromarray(checker).convert('RGB'))
        for image in samples:
            with self.subTest(sample=np.asarray(image)[0,0].tolist()):
                self.assertEqual(np.count_nonzero(_text_strokes(image)),0)

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
