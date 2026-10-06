"""Public rendered text regressions for brightness changes and true replacement."""
import unittest
from PIL import Image, ImageDraw, ImageFont
from item_vision import item_signature, same_item_text


BOXES = [(152+i*140, 500, 248+i*140, 600) for i in range(5)]


def offer(header_color=(242, 242, 242), changed_slot=None, header_text='CHOOSE ONE'):
    image = Image.new('RGB', (960, 720), (12, 30, 32))
    draw = ImageDraw.Draw(image)
    draw.text((411, 459), header_text, font=ImageFont.load_default(size=22), fill=header_color)
    for slot, (left, top, right, bottom) in enumerate(BOXES):
        draw.text((left+8, top+44), 'ARMOR' if slot == changed_slot else 'BLADE',
                  font=ImageFont.load_default(size=16), fill=(242, 242, 242))
    return image


class ItemSignatureStabilityTests(unittest.TestCase):
    def test_same_text_with_warm_and_bright_header_stays_the_same_offer(self):
        bright = item_signature(offer(), BOXES)
        warm = item_signature(offer((211, 205, 172)), BOXES)
        self.assertTrue(same_item_text(bright, warm),
                        'The same header under different game lighting became a new offer')
        self.assertTrue(same_item_text(warm, bright))

    def test_disappeared_shared_header_cannot_keep_old_equipment_ranks(self):
        self.assertFalse(same_item_text(item_signature(offer(), BOXES),
                                       item_signature(offer((12, 30, 32)), BOXES)))

    def test_changed_shared_header_is_rejected_even_with_identical_item_titles(self):
        original = item_signature(offer(), BOXES)
        for text in ('CHOOSE TWO', 'CHOOSE ONF'):
            with self.subTest(header=text):
                changed = item_signature(offer((211, 205, 172), header_text=text), BOXES)
                self.assertFalse(same_item_text(original, changed))
                self.assertFalse(same_item_text(changed, original))

    def test_faint_support_without_confirmed_core_text_is_not_a_match(self):
        self.assertFalse(same_item_text(item_signature(offer(), BOXES),
                                       item_signature(offer((160, 150, 120)), BOXES)))

    def test_changed_single_title_is_rejected_at_each_slot_under_warm_lighting(self):
        original = item_signature(offer(), BOXES)
        for slot in range(5):
            with self.subTest(slot=slot):
                self.assertFalse(same_item_text(original,
                    item_signature(offer((211, 205, 172), changed_slot=slot), BOXES)))


if __name__ == '__main__':
    unittest.main()
