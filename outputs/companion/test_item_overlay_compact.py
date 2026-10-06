"""Real widget checks for compact item ranks; no private screenshot dependency."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import bootstrap
from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtGui import QColor, QPixmap, QTextDocument
from PySide6.QtWidgets import QApplication
from item_overlay import ItemOverlay


class Portraits(QObject):
    ready = Signal(str, QPixmap)

    def __init__(self):
        super().__init__()
        self.images = {}
        for name, color in [('amumu', '#3155b7'), ('taric', '#bb452f')]:
            pixmap = QPixmap(48, 48)
            pixmap.fill(QColor(color))
            self.images[name] = pixmap

    def request(self, url):
        raise AssertionError('All compact-layout portraits must be local')


CATALOG = {'hero': [{'id': '14503', 'name': '阿木木', 'picture': 'amumu'},
                    {'id': '15451', 'name': '塔里克', 'picture': 'taric'},
                    {'id': '19999', 'name': '苍蓝雕纹魔像', 'picture': 'taric'}]}
ROW = {'name': '光明版强袭者的链枷',
       'global': {'status': 'ok', 'average': 3.98, 'samples': 1120000},
       'comp': {'status': 'ok', 'average': 3.42, 'samples': 90000},
       'holders': [{'id': '9999', 'name': '苍蓝雕纹魔像', 'average': 3.61, 'samples': 43000},
                   {'id': '5451', 'name': '塔里克', 'average': 3.28, 'samples': 90000}],
       'holder_status': 'ok'}


class ItemOverlayCompactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        self.portraits = Portraits()
        self.widgets = []

    def tearDown(self):
        for widget in self.widgets:
            widget.close()
            widget.deleteLater()
        self.qt.processEvents()

    def item(self):
        widget = ItemOverlay(self.portraits)
        widget.move(-5000, -4000)
        self.widgets.append(widget)
        widget.update_row(deepcopy(ROW), deepcopy(CATALOG))
        return widget

    def test_native_four_k_frame_is_smaller_and_lower(self):
        widget = self.item()
        box = [[624, 1604], [1012, 1604], [1012, 2000], [624, 2000]]
        binding = SimpleNamespace(rect=(-5000, -4000, -1160, -1840), dpi=192)
        with patch('item_overlay.win.user.SetWindowPos', return_value=True) as move:
            widget.place(binding, box, (3840, 2160), 560)
        x, y, width, height = move.call_args.args[2:6]
        self.assertLessEqual(width, 400)
        self.assertLessEqual(height, 200)
        self.assertGreaterEqual(y-binding.rect[1], 1200)
        # The common selection header begins above the item cards. Compact
        # ranks must end before it; card icons, names and buttons stay clear.
        self.assertLessEqual(y+height-binding.rect[1], 1414)
        self.assertTrue(widget.windowFlags() & Qt.WindowType.WindowTransparentForInput)
        self.assertTrue(widget.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating))

    def test_two_portraits_and_every_text_line_fit_three_to_five_columns(self):
        for count in (3, 4, 5):
            for dpi in (96, 144, 192):
                with self.subTest(columns=count, dpi=dpi):
                    widget = self.item()
                    # A centered 3/4/5 choice row, matching the recorded S18
                    # card widths and 142-pixel pitch at 720p.
                    frame = (round(960 * dpi/96), round(720 * dpi/96))
                    center = (960 - (count-1)*142)/2*dpi/96
                    box = [[center-48*dpi/96, 500*dpi/96],
                           [center+48*dpi/96, 500*dpi/96],
                           [center+48*dpi/96, 600*dpi/96],
                           [center-48*dpi/96, 600*dpi/96]]
                    binding = SimpleNamespace(rect=(-5000, -4000, -5000+frame[0], -4000+frame[1]), dpi=dpi)
                    with patch('item_overlay.win.user.SetWindowPos', return_value=True), patch.object(widget, 'show'):
                        widget.place(binding, box, frame, 142*dpi/96)
                    widget.layout().activate()
                    self.qt.processEvents()
                    self.assertLessEqual(widget.height(), 100)
                    self.assertLessEqual(widget.width(), 200)
                    image = widget.grab().toImage()
                    self.assertFalse(image.isNull())
                    labels = [widget.title, widget.global_line, widget.comp_line]
                    for picture, name in widget.holder_lines:
                        self.assertFalse(picture.pixmap().isNull())
                        self.assertFalse(picture.isHidden())
                        self.assertGreaterEqual(picture.width(), 18)
                        self.assertGreaterEqual(picture.height(), 18)
                        labels.extend((picture, name))
                    for label in labels:
                        self.assertTrue(widget.rect().contains(label.geometry()),
                                        f'{label.text()} outside compact frame')
                        if not label.text():
                            continue
                        document = QTextDocument()
                        document.setDefaultFont(label.font())
                        document.setDocumentMargin(0)
                        document.setHtml(label.text())
                        document.setTextWidth(label.width())
                        self.assertLessEqual(document.size().height(), label.height()+1,
                                             f'{label.text()} clipped at {label.size()}')

    def test_pending_unpinned_and_query_failure_keep_statuses_inside_frame(self):
        for status in ('pending', 'missing', 'error'):
            with self.subTest(status=status):
                widget = self.item()
                row = deepcopy(ROW)
                row['global'] = {'status': status}
                row['comp'] = {'status': 'unpinned'}
                row['holders'] = []
                row['holder_status'] = status
                widget.update_row(row, CATALOG)
                widget.setFixedWidth(128)
                widget.layout().activate()
                self.qt.processEvents()
                self.assertTrue(widget.comp_line.isHidden())
                self.assertFalse(widget.holder_lines[0][1].text() == '')
                for label in [widget.title, widget.global_line, widget.holder_lines[0][1]]:
                    self.assertTrue(widget.rect().contains(label.geometry()))
                self.assertFalse(widget.grab().toImage().isNull())


if __name__ == '__main__':
    unittest.main()
