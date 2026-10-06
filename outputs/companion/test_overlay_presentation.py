"""Idempotent rank presentation on real Qt widgets and owned Win32 windows.

The owned test windows stay outside the desktop. No game window or input is used.
"""
from copy import deepcopy
import ctypes
from ctypes import wintypes
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PySide6.QtCore import QObject, Signal, QEvent
from PySide6.QtGui import QPixmap, QColor
from app import QApplication, CardOverlay
from item_overlay import ItemOverlay
import win_capture as win


URL_A = 'https://img.dataj.cc/tests/hero-amumu.png'
URL_B = 'https://img.dataj.cc/tests/hero-akali.png'
CATALOG = {'hero': [
    {'id': '14503', 'name': '阿木木', 'picture': URL_A},
    {'id': '11513', 'name': '阿卡丽', 'picture': URL_B}]}
ROW = {'id': '2004', 'name': '朔极之矛',
       'global': {'status': 'ok', 'average': 4.20, 'samples': 301},
       'comp': {'status': 'unpinned'},
       'holders': [{'id': '4503', 'name': '阿木木', 'average': 3.91, 'samples': 254}],
       'holder_status': 'ok'}
BOX = [[550, 720], [700, 720], [700, 900], [550, 900]]


class LocalPortraits(QObject):
    ready = Signal(str, QPixmap)

    def __init__(self):
        super().__init__()
        self.images = {}
        self.requests = []

    def request(self, url):
        self.requests.append(url)


class PresentationEvents(QObject):
    def __init__(self):
        super().__init__()
        self.paints = self.resizes = 0

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Paint:self.paints += 1
        if event.type() == QEvent.Type.Resize:self.resizes += 1
        return False


class OverlayPresentation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        self.widgets = []
        self.portraits = LocalPortraits()
        for url, color in ((URL_A, '#3155b7'), (URL_B, '#bb452f')):
            picture = QPixmap(48, 48)
            picture.fill(QColor(color))
            self.portraits.images[url] = picture
        dpi = round(self.qt.primaryScreen().devicePixelRatio()*96)
        self.binding = SimpleNamespace(hwnd=999, pid=999,
            rect=(-5000, -4000, -3080, -2920), dpi=dpi)

    def card(self):
        widget = CardOverlay()
        widget.move(-5000, -4000)
        self.widgets.append(widget)
        return widget

    def item(self):
        widget = ItemOverlay(self.portraits)
        widget.move(-5000, -4000)
        self.widgets.append(widget)
        return widget

    def tearDown(self):
        for widget in self.widgets:
            widget.close()
            widget.deleteLater()
        self.qt.processEvents()

    def native_calls(self):
        # Observe the actual public Win32 operation on our own handles.
        return patch('item_overlay.win.user.SetWindowPos', wraps=win.user.SetWindowPos)

    def test_identical_augment_updates_do_not_repeat_native_window_position(self):
        widget = self.card()
        text = '2-1 · 应急护甲 I<br>全局 4.20<br>阵容 3.80'
        with self.native_calls() as position:
            widget.place(self.binding, BOX, text)
            self.qt.processEvents()
            first_size = widget.size()
            for _ in range(40):
                widget.place(self.binding, deepcopy(BOX), text)
                self.qt.processEvents()
            self.assertEqual(widget.size(), first_size)
            self.assertEqual(position.call_count, 1,
                'Identical ranks repeatedly reposition/show the native overlay')
            self.assertEqual(int(position.call_args.args[0]), widget.handle)

    def test_identical_item_updates_do_not_repeat_width_or_native_position(self):
        widget = self.item()
        widget.update_row(deepcopy(ROW), deepcopy(CATALOG))
        with self.native_calls() as position, patch.object(widget, 'setFixedWidth', wraps=widget.setFixedWidth) as width:
            widget.place(self.binding, BOX, (1920, 1080), 360)
            self.qt.processEvents()
            for _ in range(40):
                widget.place(self.binding, deepcopy(BOX), (1920, 1080), 360)
                self.qt.processEvents()
            self.assertEqual(position.call_count, 1)
            self.assertEqual(width.call_count, 1)

    def test_identical_item_content_preserves_loaded_portrait_and_text_widgets(self):
        widget = self.item()
        widget.update_row(deepcopy(ROW), deepcopy(CATALOG))
        picture, name = widget.holder_lines[0]
        first_key = picture.pixmap().cacheKey()
        with patch.object(picture, 'clear', wraps=picture.clear) as picture_clear, \
             patch.object(name, 'clear', wraps=name.clear) as name_clear, \
             patch.object(widget.global_line, 'setText', wraps=widget.global_line.setText) as global_text:
            for _ in range(40):
                widget.update_row(deepcopy(ROW), deepcopy(CATALOG))
            self.assertEqual(picture.pixmap().cacheKey(), first_key)
            self.assertEqual(picture_clear.call_count, 0)
            self.assertEqual(name_clear.call_count, 0)
            self.assertEqual(global_text.call_count, 0)

    def test_loaded_portrait_survives_shared_image_cache_eviction(self):
        widget = self.item()
        widget.update_row(deepcopy(ROW), deepcopy(CATALOG))
        picture, _ = widget.holder_lines[0]
        first_key = picture.pixmap().cacheKey()
        self.portraits.images.clear()
        widget.update_row(deepcopy(ROW), deepcopy(CATALOG))
        self.assertFalse(picture.pixmap().isNull(), 'Stable portrait was blanked after cache eviction')
        self.assertEqual(picture.pixmap().cacheKey(), first_key)

    def test_changed_item_content_updates_metrics_and_holder_identity(self):
        widget = self.item()
        widget.update_row(deepcopy(ROW), deepcopy(CATALOG))
        first_key = widget.holder_lines[0][0].pixmap().cacheKey()
        row = deepcopy(ROW)
        row['global']['average'] = 3.33
        row['holders'] = [{'id': '1513', 'name': '阿卡丽', 'average': 3.25, 'samples': 100}]
        widget.update_row(row, deepcopy(CATALOG))
        self.assertIn('3.33', widget.global_line.text())
        self.assertIn('阿卡丽', widget.holder_lines[0][1].text())
        self.assertEqual(widget.urls[0], URL_B)
        self.assertNotEqual(widget.holder_lines[0][0].pixmap().cacheKey(), first_key)
        before = widget.holder_lines[0][0].pixmap().cacheKey()
        self.portraits.ready.emit(URL_A, self.portraits.images[URL_A])
        self.assertEqual(widget.holder_lines[0][0].pixmap().cacheKey(), before)

    def test_repeated_rows_preserve_actual_client_pixels_without_paint_or_resize(self):
        # Public QWidget rendering of our off-desktop native windows. This
        # verifies client pixels, not the game's compositor presentation.
        for make in (self.card, self.item):
            widget = make()
            events = PresentationEvents()
            widget.installEventFilter(events)
            text = '2-1 · 应急护甲 I<br>全局 4.20<br>阵容 3.80'
            def present():
                if isinstance(widget, ItemOverlay):
                    widget.update_row(deepcopy(ROW), deepcopy(CATALOG))
                    widget.place(self.binding, BOX, (1920, 1080), 360)
                else:widget.place(self.binding, deepcopy(BOX), text)
            with self.native_calls() as position:
                present()
                self.qt.processEvents()
                before = widget.grab().toImage()
                # Drain the initial show/grab's deferred native paint; the
                # following events must come from the repeated presentation.
                for _ in range(3):self.qt.processEvents()
                events.paints = events.resizes = 0
                for _ in range(40):
                    present()
                    self.qt.processEvents()
                self.assertEqual(events.paints, 0, type(widget).__name__)
                self.assertEqual(events.resizes, 0, type(widget).__name__)
                self.assertEqual(position.call_count, 1)
                after = widget.grab().toImage()
            self.assertFalse(before.isNull())
            self.assertEqual(after, before)

    def test_changed_augment_text_renders_new_pixels_and_resizes_native_window(self):
        widget = self.card()
        with self.native_calls() as position:
            widget.place(self.binding, BOX, '2-1 · 黑铁资产<br>全局 4.20')
            self.qt.processEvents()
            before = widget.grab().toImage()
            widget.place(self.binding, BOX, '2-1 · 应急护甲 I<br>全局 3.20<br>本阵容 3.01')
            self.qt.processEvents()
            after = widget.grab().toImage()
            self.assertIn('3.01', widget.text())
            self.assertNotEqual(after, before)
            self.assertEqual(position.call_count, 2)
            widget.place(self.binding, BOX, widget.text())
            self.assertEqual(position.call_count, 2)

    def test_changed_metric_updates_pixels_without_resetting_same_holder(self):
        widget = self.item()
        with self.native_calls() as position:
            widget.update_row(deepcopy(ROW), deepcopy(CATALOG))
            widget.place(self.binding, BOX, (1920, 1080), 360)
            self.qt.processEvents()
            before = widget.grab().toImage()
            picture = widget.holder_lines[0][0]
            key = picture.pixmap().cacheKey()
            row = deepcopy(ROW)
            row['global']['average'] = 3.01
            row['holders'][0]['average'] = 3.02
            widget.update_row(row, deepcopy(CATALOG))
            widget.place(self.binding, BOX, (1920, 1080), 360)
            self.qt.processEvents()
            self.assertNotEqual(widget.grab().toImage(), before)
            self.assertEqual(picture.pixmap().cacheKey(), key)
            self.assertIn('3.01', widget.global_line.text())
            self.assertIn('3.02', widget.holder_lines[0][1].text())
            self.assertEqual(position.call_count, 1)

    def test_holder_removal_ignores_late_portrait_and_reappearance_loads_it(self):
        widget = self.item()
        widget.update_row(deepcopy(ROW), deepcopy(CATALOG))
        row = deepcopy(ROW)
        row['holders'] = []
        row['holder_status'] = 'missing'
        widget.update_row(row, deepcopy(CATALOG))
        picture, name = widget.holder_lines[0]
        self.assertTrue(picture.pixmap().isNull())
        self.assertTrue(picture.isHidden())
        self.assertEqual(name.text(), '暂无足够样本')
        self.portraits.ready.emit(URL_A, self.portraits.images[URL_A])
        self.assertTrue(picture.pixmap().isNull())
        widget.update_row(deepcopy(ROW), deepcopy(CATALOG))
        self.assertFalse(picture.pixmap().isNull())
        self.assertFalse(picture.isHidden())

    def test_same_url_new_portrait_and_catalog_url_changes_still_render(self):
        widget = self.item()
        widget.update_row(deepcopy(ROW), deepcopy(CATALOG))
        picture = widget.holder_lines[0][0]
        before = picture.pixmap().toImage()
        pix = QPixmap(48, 48)
        pix.fill(QColor('#31b756'))
        self.portraits.ready.emit(URL_A, pix)
        self.assertNotEqual(picture.pixmap().toImage(), before)
        key = picture.pixmap().cacheKey()
        self.portraits.ready.emit(URL_A, pix)
        self.assertEqual(picture.pixmap().cacheKey(), key)
        catalog = deepcopy(CATALOG)
        catalog['hero'][0]['picture'] = URL_B
        widget.update_row(deepcopy(ROW), catalog)
        self.assertEqual(widget.urls[0], URL_B)
        self.assertEqual(picture.pixmap().toImage().pixelColor(0, 0), QColor('#bb452f'))

    def test_real_native_rect_moves_when_game_geometry_changes(self):
        for make in (self.card, self.item):
            widget = make()
            def place(binding):
                if isinstance(widget, ItemOverlay):widget.place(binding, BOX, (1920, 1080), 360)
                else:widget.place(binding, BOX, '全局 4.20')
            with self.native_calls() as position:
                place(self.binding)
                before = wintypes.RECT()
                self.assertTrue(win.user.GetWindowRect(widget.handle, ctypes.byref(before)))
                moved = SimpleNamespace(**vars(self.binding))
                moved.rect = tuple(value+100 for value in self.binding.rect)
                place(moved)
                after = wintypes.RECT()
                self.assertTrue(win.user.GetWindowRect(widget.handle, ctypes.byref(after)))
                self.assertEqual(after.left-before.left, 100)
                self.assertEqual(after.top-before.top, 100)
                self.assertEqual(position.call_count, 2)

    def test_failed_native_position_is_retried_until_success(self):
        for make in (self.card, self.item):
            widget = make()
            def place():
                if isinstance(widget, ItemOverlay):widget.place(self.binding, BOX, (1920, 1080), 360)
                else:widget.place(self.binding, BOX, '全局 4.20')
            with patch('item_overlay.win.user.SetWindowPos', side_effect=[False, True]) as position:
                place()
                place()
                place()
                self.assertEqual(position.call_count, 2)

    def test_changed_content_geometry_dpi_and_reshow_still_update_native_window(self):
        # Real Qt state, observed native boundary: an artificial DPI does not
        # move the test window between real monitors.
        for make in (self.card, self.item):
            widget = make()
            if isinstance(widget, ItemOverlay):
                widget.update_row(deepcopy(ROW), deepcopy(CATALOG))
                place = lambda binding, box: widget.place(binding, box, (1920, 1080), 360)
            else:
                place = lambda binding, box: widget.place(binding, box, '原始均排')
            with patch('item_overlay.win.user.SetWindowPos', return_value=True) as position:
                place(self.binding, BOX)
                initial = position.call_args.args[2:6]
                moved = SimpleNamespace(**vars(self.binding))
                moved.rect = tuple(value+100 for value in self.binding.rect)
                place(moved, BOX)
                self.assertNotEqual(position.call_args.args[2:6], initial)
                changed_dpi = SimpleNamespace(**vars(moved))
                changed_dpi.dpi += 48
                place(changed_dpi, BOX)
                self.assertEqual(position.call_count, 3)
                widget.hide()
                place(changed_dpi, BOX)
                self.assertTrue(widget.isVisible())
                self.assertEqual(position.call_count, 4)


if __name__ == '__main__':
    unittest.main()
