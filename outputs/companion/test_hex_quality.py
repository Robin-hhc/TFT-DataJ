"""Independent original glyph colors and rejection of background impostors."""
import hashlib
import json
from pathlib import Path
import unittest

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance

from hex_quality import read_hex_quality


FIXTURES = Path(__file__).parent / 'fixtures'


def reviewed_glyph(name):
    stem = FIXTURES / ('hex-quality-' + name + '-20261021')
    metadata = json.loads(stem.with_suffix('.json').read_text(encoding='utf-8'))
    png = stem.with_suffix('.png')
    if hashlib.sha256(png.read_bytes()).hexdigest() != metadata['crop_sha256']:
        raise AssertionError('Reviewed glyph pixels changed')
    with Image.open(png) as image:
        return image.convert('RGB'), metadata


class HexQualityTests(unittest.TestCase):
    def assert_quality(self, name, level):
        crop, evidence = reviewed_glyph(name)
        self.assertEqual(evidence['expected'], {'status': 'confirmed', 'level': level})
        result = read_hex_quality(crop)
        self.assertEqual((result['status'], result['level']), ('confirmed', level), result)
        self.assertTrue(result['reason'])

    def assert_unknown(self, crop):
        result = read_hex_quality(crop)
        self.assertEqual((result['status'], result['level']), ('unknown', None), result)
        self.assertTrue(result['reason'])

    def test_original_silver_hug_i_glyph_is_level_one(self):
        self.assert_quality('silver-hug-i', 1)

    def test_original_dim_gold_hug_ii_glyph_is_level_two(self):
        self.assert_quality('gold-dim-hug-ii', 2)

    def test_original_silver_rolling_i_glyph_is_level_one(self):
        self.assert_quality('silver-rolling-i', 1)

    def test_original_gold_bronze_i_uses_color_not_roman_one(self):
        self.assert_quality('gold-bronze-i', 2)

    def test_original_prismatic_arcane_two_plus_uses_multicolor_glyph(self):
        self.assert_quality('prismatic-arcane-two-plus', 3)

    def test_flat_colors_and_green_backgrounds_are_unknown(self):
        for color in ((0, 0, 0), (255, 255, 255), (220, 190, 0),
                      (150, 160, 180), (50, 90, 40), (220, 30, 220)):
            with self.subTest(color=color):
                self.assert_unknown(Image.new('RGB', (422, 367), color))

    def test_ornate_gold_border_without_central_glyph_is_unknown(self):
        image = Image.new('RGB', (422, 367), (35, 80, 30))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 421, 366), outline=(220, 180, 25), width=32)
        draw.line((0, 55, 420, 0), fill=(240, 205, 35), width=12)
        self.assert_unknown(image)

    def test_plain_yellow_or_silver_panel_is_not_an_icon(self):
        for color in ((220, 190, 0), (160, 170, 190)):
            with self.subTest(color=color):
                image = Image.new('RGB', (422, 367), (35, 80, 30))
                ImageDraw.Draw(image).rectangle((85, 65, 335, 310), fill=color)
                self.assert_unknown(image)

    def test_conflicting_gold_and_silver_icon_halves_are_unknown(self):
        silver, _ = reviewed_glyph('silver-hug-i')
        gold, _ = reviewed_glyph('gold-dim-hug-ii')
        mixed = silver.copy()
        mixed.paste(gold.crop((gold.width // 2, 0, gold.width, gold.height)),
                    (mixed.width // 2, 0))
        self.assert_unknown(mixed)

    def test_too_dark_and_transparent_original_glyphs_are_unknown(self):
        for name in ('silver-hug-i', 'gold-bronze-i', 'prismatic-arcane-two-plus'):
            crop, _ = reviewed_glyph(name)
            with self.subTest(name=name, mode='dark'):
                self.assert_unknown(ImageEnhance.Brightness(crop).enhance(.25))
            with self.subTest(name=name, mode='transparent'):
                background = Image.new('RGB', crop.size, (35, 80, 30))
                self.assert_unknown(Image.blend(background, crop, .15))

    def test_unstructured_mixed_color_noise_is_unknown(self):
        random = np.random.default_rng(20261021)
        self.assert_unknown(Image.fromarray(random.integers(0, 256, (367, 422, 3), dtype=np.uint8)))

    def test_half_covered_glyph_requires_unknown(self):
        crop, _ = reviewed_glyph('prismatic-arcane-two-plus')
        ImageDraw.Draw(crop).rectangle((0, 0, crop.width, crop.height // 2), fill=(20, 20, 20))
        self.assert_unknown(crop)

    def test_faded_gold_strokes_are_not_automatic_quality_evidence(self):
        crop, _ = reviewed_glyph('gold-bronze-i')
        self.assert_unknown(ImageEnhance.Brightness(crop).enhance(.55))

    def test_transparent_and_partly_transparent_rgba_glyphs_are_unknown(self):
        for alpha in (0, 30, 254):
            with self.subTest(alpha=alpha):
                crop, _ = reviewed_glyph('silver-hug-i')
                crop = crop.convert('RGBA')
                crop.putalpha(alpha)
                self.assert_unknown(crop)

    def test_palette_transparency_cannot_reveal_an_invisible_glyph(self):
        crop, _ = reviewed_glyph('silver-hug-i')
        crop = crop.quantize(colors=128)
        crop.info['transparency'] = bytes([0] * 256)
        self.assert_unknown(crop)

    def test_regular_silver_or_gold_stripes_are_not_glyphs(self):
        for color in ((160, 170, 190), (220, 190, 0)):
            for direction in ('horizontal', 'vertical'):
                with self.subTest(color=color, direction=direction):
                    image = Image.new('RGB', (422, 367), (35, 80, 30))
                    draw = ImageDraw.Draw(image)
                    for offset in range(85, 320, 30):
                        box = ((85, offset, 335, offset + 12) if direction == 'horizontal'
                               else (offset, 65, offset + 12, 310))
                        draw.rectangle(box, fill=color)
                    self.assert_unknown(image)


if __name__ == '__main__':
    unittest.main()
