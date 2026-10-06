"""Actual item widgets map statistical hero IDs to exact catalog forms."""
import unittest
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap, QColor
from comp_browser import portrait_catalog
from item_overlay import ItemOverlay
import test_overlay_presentation as fixtures


FIRE = 'https://img.dataj.cc/tests/lux-fire.png'
ICE = 'https://img.dataj.cc/tests/lux-ice.png'
HEROES = [
    {'id': '15466', 'name': '拉克丝', 'tag': '火', 'heroType': 0, 'picture': FIRE},
    {'id': '25466', 'name': '拉克丝', 'tag': '火', 'heroType': 0, 'picture': FIRE},
    {'id': '15463', 'name': '拉克丝', 'tag': '冰', 'heroType': 0, 'picture': ICE},
    {'id': '25463', 'name': '拉克丝', 'tag': '冰', 'heroType': 0, 'picture': ICE},
]


class ItemPortraitIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def test_ordinary_item_holders_show_exact_form_portraits_from_statistical_ids(self):
        store = fixtures.LocalPortraits()
        for url, color in ((FIRE, '#c54224'), (ICE, '#285dc7')):
            picture = QPixmap(48, 48)
            picture.fill(QColor(color))
            store.images[url] = picture
        widget = ItemOverlay(store)
        self.addCleanup(widget.close)
        row = {'id': '2016', 'name': '珠光护手',
               'global': {'status': 'ok', 'average': 4.11, 'samples': 150},
               'comp': {'status': 'unpinned'}, 'holder_status': 'ok',
               'holders': [{'id': '5466', 'name': '拉克丝', 'average': 3.20, 'samples': 100},
                           {'id': '5463', 'name': '拉克丝', 'average': 3.40, 'samples': 90}]}
        widget.update_row(row, {'hero': HEROES})
        self.assertEqual(widget.urls, [FIRE, ICE], 'Different Lux forms lost their exact portraits')
        for (picture, label), expected in zip(widget.holder_lines, (QColor('#c54224'), QColor('#285dc7'))):
            self.assertFalse(picture.pixmap().isNull())
            self.assertEqual(picture.pixmap().toImage().pixelColor(0, 0), expected)
            self.assertIn('拉克丝', label.text())
        self.assertEqual([holder['id'] for holder in row['holders']], ['5466', '5463'])
        self.assertEqual([holder['average'] for holder in row['holders']], [3.20, 3.40])

    def test_same_name_forms_have_no_ambiguous_name_portrait_fallback(self):
        pictures = portrait_catalog(HEROES)
        self.assertNotIn('name:拉克丝', pictures)
        self.assertNotIn('5461', pictures)
        self.assertEqual(pictures['5466']['picture'], FIRE)
        self.assertEqual(pictures['5463']['picture'], ICE)

    def test_refreshed_catalog_uses_new_portrait_instead_of_cached_old_alias(self):
        portrait_catalog(HEROES)
        refreshed = [dict(row) for row in HEROES]
        url = 'https://img.dataj.cc/tests/lux-fire-new.png'
        for row in refreshed:
            if row['id'].endswith('5466'):
                row['picture'] = url
        self.assertEqual(portrait_catalog(refreshed)['5466']['picture'], url)
        self.assertEqual(portrait_catalog(refreshed)['5463']['picture'], ICE)


if __name__ == '__main__':
    unittest.main()
