"""Conservative local-pixel quality evidence for a verified augment glyph crop.

The caller owns scene, geometry and freshness checks. Green card backgrounds
and the ornate gold border are shared by every quality. Only a bounded central
glyph with coherent silver, gold or multicolor strokes can supply evidence.
"""
import numpy as np
from PIL import Image


def read_hex_quality(crop):
    """Read one fast-layout glyph ROI; uncertain pixels never assign a level."""
    def unknown(reason, diagnostics=None):
        return {'status': 'unknown', 'level': None, 'reason': reason,
                'diagnostics': diagnostics or {}}

    if (not isinstance(crop, Image.Image) or min(crop.size) < 32
            or not .85 <= crop.width / crop.height <= 1.5):
        return unknown('unsupported_glyph_crop')
    if crop.mode != 'RGB':
        # Converting RGBA/P straight to RGB exposes colors that are invisible
        # on screen. Live MSS glyphs are RGB; only fully opaque RGBA is valid.
        if crop.mode != 'RGBA' or crop.getextrema()[3] != (255, 255):
            return unknown('non_opaque_or_unsupported_color_input')
        crop = crop.convert('RGB')
    scale = min(1, 128 / max(crop.size))
    image = (crop.resize((round(crop.width * scale), round(crop.height * scale)),
                         Image.Resampling.BILINEAR) if scale < 1 else crop)
    pixels = np.asarray(image, dtype=np.int16)
    height, width = pixels.shape[:2]
    # Discard the shared frame/leaf decorations before measuring color. Keep
    # interior shape evidence; no neighboring card or title enters this crop.
    pixels = pixels[round(height * .08):round(height * .93),
                    round(width * .16):round(width * .89)]
    red, green, blue = pixels.transpose(2, 0, 1)
    silver = ((red >= 95) & (green >= 100) & (blue >= 115)
              & (blue * 100 >= red * 104) & (blue * 100 >= green * 98)
              & (blue - red < 100))
    gold = ((red >= 105) & (green >= 80) & (red * 100 >= green * 92)
            & (blue * 100 < np.minimum(red, green) * 60))
    purple = ((red > 120) & (blue > 130)
              & (red - green > 15) & (blue - green > 25))
    cyan = ((green > 140) & (blue > 155)
            & (green - red > 25) & (blue - red > 40))
    spread = (np.maximum(np.maximum(red, green), blue)
              - np.minimum(np.minimum(red, green), blue))
    neutral = ((red > 150) & (green > 150) & (blue > 150) & (spread < 65))
    foreground = silver | gold | purple | cyan | neutral
    yy, xx = np.where(foreground)
    count = len(xx)
    if count < 160:
        return unknown('insufficient_bright_glyph_strokes')
    box_width = int(xx.max() - xx.min() + 1)
    box_height = int(yy.max() - yy.min() + 1)
    fill = count / (box_width * box_height)
    # Solid panels and high-frequency RGB noise are not an augment glyph.
    perimeter = (np.count_nonzero(foreground[1:] != foreground[:-1])
                 + np.count_nonzero(foreground[:, 1:] != foreground[:, :-1])) / count
    diagnostics = {'stroke_pixels': count, 'box_fill': round(fill, 3),
                   'edge_ratio': round(perimeter, 3)}
    if (box_width < width * .35 or box_height < height * .35
            or not .08 <= fill <= .68 or not .10 <= perimeter <= .85
            or count > width * height * .40):
        return unknown('incomplete_or_non_glyph_shape', diagnostics)
    shape = foreground[int(yy.min()):int(yy.max()) + 1,
                       int(xx.min()):int(xx.max()) + 1]
    # Repeated parallel panels can have the same area and edge count as a
    # glyph. Reject shapes whose pixels mostly occupy full-width/height bars.
    for sums, span in ((shape.sum(axis=1), box_width), (shape.sum(axis=0), box_height)):
        bars = sums > span * .90
        if np.count_nonzero(bars) >= 6 and int(sums[bars].sum()) > count * .75:
            return unknown('regular_panel_or_stripe_shape', diagnostics)
    silver_count = int(np.count_nonzero(silver))
    gold_count = int(np.count_nonzero(gold))
    purple_count = int(np.count_nonzero(purple))
    cyan_count = int(np.count_nonzero(cyan))
    neutral_count = int(np.count_nonzero(neutral))
    chromatic = purple_count + cyan_count
    # Prism needs multiple actual hue families and neutral highlights. A
    # plain purple shape, one yellow pixel or border gold cannot authorize it.
    if (purple_count >= 70 and chromatic >= count * .16
            and gold_count >= count * .035 and neutral_count >= count * .15):
        level = 3
    elif silver_count >= count * .90 and gold_count <= count * .02 and chromatic <= count * .02:
        level = 1
    elif gold_count >= count * .90 and silver_count <= count * .02 and chromatic <= count * .02:
        if np.count_nonzero(gold & (red >= 135)) < gold_count * .55:
            return unknown('gold_glyph_too_dim_or_faded', diagnostics)
        level = 2
    else:
        return unknown('mixed_or_insufficient_quality_colors', diagnostics)
    return {'status': 'confirmed', 'level': level, 'reason': 'coherent_glyph_shape_and_color',
            'diagnostics': diagnostics}
