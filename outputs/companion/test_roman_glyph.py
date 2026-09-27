import unittest
from PIL import Image, ImageDraw, ImageFont
from roman_glyph import roman_evidence


class GlyphTests(unittest.TestCase):
    def render(self, suffix):
        font=ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc',32)
        image=Image.new('RGB',(300,65),'#182a35')
        ImageDraw.Draw(image).text((10,8),'护甲 '+suffix,font=font,fill='#f5e7c9')
        return image

    def test_separated_strokes(self):
        for suffix in ('I','II','III'):
            self.assertEqual(roman_evidence(self.render(suffix))['roman'],suffix)

    def test_punctuation_and_numeric_are_not_roman(self):
        for suffix in ('!','1','+','IV'):
            self.assertIsNone(roman_evidence(self.render(suffix)),suffix)

    def test_four_strokes_and_blank_rejected(self):
        self.assertIsNone(roman_evidence(self.render('IIII')))
        self.assertIsNone(roman_evidence(Image.new('RGB',(150,50),'black')))


if __name__=='__main__':unittest.main()
