"""Preserve full hero portraits, Qt resampling and warm consumer reads.

The proposed cache rewrite was rejected; these checks protect existing behavior.
"""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPixmap
from PySide6.QtNetwork import QNetworkReply
from PySide6.QtWidgets import QApplication, QWidget

import comp_browser
from comp_browser import HeroPortrait, Portraits
from condition_inputs import ConditionInputs
from item_overlay import ItemOverlay


URL='https://img.dataj.cc/tests/hero-original.png'
HERO={'id':'14503','name':'阿木木','heroType':0,'picture':URL}
CARD_HERO={'heroId':'4503','heroName':'阿木木'}


def original_picture():
    image=QImage(96,96,QImage.Format.Format_ARGB32)
    for y in range(96):
        for x in range(96):
            image.setPixelColor(x,y,QColor((x*13+y*3)%256,(x*5+y*17)%256,(x*7+y*11)%256))
    return QPixmap.fromImage(image)


def picture_bytes(picture):
    body=QByteArray();buffer=QBuffer(body)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert picture.save(buffer,'PNG')
    return body


class Reply:
    NetworkError=QNetworkReply.NetworkError

    def __init__(self,body):self.body=body
    def error(self):return self.NetworkError.NoError
    def readAll(self):return self.body
    def deleteLater(self):pass


class PortraitCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.qt=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.parent=QWidget();self.addCleanup(self.parent.close)
        with patch.object(comp_browser,'STATE_DIR',Path(self.temp.name)):
            self.store=Portraits(self.parent,enabled=False)
        self.original=original_picture()

    def receive(self,url,body=None):
        self.store.active+=1
        self.store.finished(Reply(picture_bytes(self.original) if body is None else body),url)

    def widget(self,widget):
        self.addCleanup(widget.close)
        return widget

    def test_received_portrait_retains_original_pixels_dimensions_and_depth(self):
        received=[];self.store.ready.connect(lambda url,pix:received.append((url,pix)))
        self.receive(URL)
        self.assertEqual(len(received),1)
        self.assertEqual(received[0][0],URL)
        for pix in (received[0][1],self.store.images[URL]):
            self.assertEqual(pix.size(),QSize(96,96))
            self.assertEqual(pix.depth(),32)
            self.assertEqual(pix.devicePixelRatio(),1.)
            self.assertEqual(pix.toImage(),self.original.toImage())

    def test_all_consumers_preserve_existing_34_18_16px_pixels_and_high_dpi_icons(self):
        self.receive(URL)
        hero=self.widget(HeroPortrait(CARD_HERO,{'4503':HERO},self.store))
        item=self.widget(ItemOverlay(self.store))
        row={'id':'2004','name':'朔极之矛','global':{'status':'missing'},
             'comp':{'status':'unpinned'},'holder_status':'ok',
             'holders':[{'id':'4503','name':'阿木木','average':3.91,'samples':254}]}
        item.update_row(row,{'hero':[HERO]})
        inputs=self.widget(ConditionInputs(self.store))
        inputs.set_resources([{'kind':'hero','entity':HERO}])
        for label,size in ((hero.picture,34),(item.holder_lines[0][0],18)):
            expected=self.original.scaled(QSize(size,size),Qt.KeepAspectRatio,Qt.SmoothTransformation)
            self.assertFalse(label.pixmap().isNull())
            self.assertEqual(label.pixmap().toImage(),expected.toImage())
        for dpr in (1.,1.25,1.5,2.,3.,4.):
            with self.subTest(dpr=dpr):
                actual=inputs.chips[0].icon().pixmap(QSize(16,16),dpr)
                expected=QIcon(self.original).pixmap(QSize(16,16),dpr)
                self.assertEqual(actual.size(),QSize(round(16*dpr),round(16*dpr)))
                self.assertEqual(actual.devicePixelRatio(),dpr)
                self.assertEqual(actual.toImage(),expected.toImage())
        self.assertEqual(self.store.images[URL].size(),QSize(96,96))

    def test_warm_64_originals_recreate_80_visible_hero_slots_without_new_request(self):
        urls=[f'https://img.dataj.cc/tests/warm-{i}.png' for i in range(64)]
        body=picture_bytes(self.original)
        for url in urls:self.receive(url,body)
        keys={url:self.store.images[url].cacheKey() for url in urls}
        self.store.enabled=True
        with patch.object(self.store,'request',side_effect=AssertionError('Warm UI requested a portrait')):
            with patch.object(self.store.manager,'get',side_effect=AssertionError('Warm UI read disk/network')):
                for i in range(80):
                    widget=self.widget(HeroPortrait(CARD_HERO,{'4503':dict(HERO,picture=urls[i%64])},self.store))
                    self.assertFalse(widget.picture.pixmap().isNull())
                    self.assertEqual(widget.picture.pixmap().size(),QSize(34,34))
        self.assertEqual(len(self.store.images),64)
        self.assertEqual({url:self.store.images[url].cacheKey() for url in urls},keys)
        self.assertEqual(sum(pix.toImage().sizeInBytes() for pix in self.store.images.values()),64*96*96*4)
        self.assertFalse(self.store.pending)

    def test_source_device_pixel_ratio_is_preserved_when_consumer_reads_original(self):
        for dpr in (1.,2.,3.,4.):
            with self.subTest(dpr=dpr):
                original=QPixmap(self.original);original.setDevicePixelRatio(dpr)
                self.store.images[URL]=original
                widget=self.widget(HeroPortrait(CARD_HERO,{'4503':HERO},self.store))
                self.assertEqual(self.store.images[URL].devicePixelRatio(),dpr)
                self.assertEqual(self.store.images[URL].size(),QSize(96,96))
                self.assertEqual(widget.picture.pixmap().devicePixelRatio(),dpr)
                self.assertEqual(widget.picture.pixmap().toImage(),
                                 original.scaled(QSize(34,34),Qt.KeepAspectRatio,Qt.SmoothTransformation).toImage())


if __name__=='__main__':unittest.main()
