"""Public, pixel-generated geometry regressions; no user images required."""
import unittest

from PIL import Image, ImageDraw
from item_vision import item_boxes


def cards(count, *, bright_left=0, pitch=140, width=96, top=500):
    frame = Image.new('RGB', (960, 720), (12, 30, 32))
    draw = ImageDraw.Draw(frame)
    left = round((960 - ((count - 1) * pitch + width)) / 2)
    for slot in range(count):
        x = left + slot * pitch
        fill = (180, 150, 30) if slot < bright_left else (105, 80, 20)
        draw.rectangle((x, top, x + width - 1, top + 99), fill=fill, outline=(245, 200, 100), width=2)
    return frame


class ItemLayoutGeometryTests(unittest.TestCase):
    def test_bright_two_cards_cannot_turn_five_choices_into_three(self):
        boxes = item_boxes(cards(5, bright_left=2))
        self.assertEqual(len(boxes), 5, boxes)
        self.assertEqual([round((left + right) / 2) for left, _, right, _ in boxes], [200, 340, 480, 620, 760])

    def test_separated_three_four_five_cards_keep_the_full_row(self):
        for count in (3, 4, 5):
            with self.subTest(count=count):
                self.assertEqual(len(item_boxes(cards(count))), count)

    def test_tightly_packed_shop_grid_is_not_a_choice_row(self):
        self.assertEqual(item_boxes(cards(5, pitch=100, width=96, top=590)), [])

    def test_off_center_partial_card_row_does_not_renumber_slots(self):
        frame = cards(5, bright_left=2)
        # Remove the first two cards altogether, as in a clipped or obscured row.
        ImageDraw.Draw(frame).rectangle((120, 480, 420, 620), fill=(12, 30, 32))
        self.assertEqual(item_boxes(frame), [])


if __name__ == '__main__':
    unittest.main()
