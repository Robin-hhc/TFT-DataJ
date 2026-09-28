"""Fixed website color anchors and explicit UI status/format expectations."""
import unittest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject,Signal
from PySide6.QtGui import QPixmap
from app import table,fill_table,stat_text
from comp_browser import CompCard
from item_overlay import ItemOverlay
from display_audit import plain
from ui_theme import ResultCard


class Pictures(QObject):
    ready=Signal(str,QPixmap)
    images={}
    def request(self,url):pass


class DisplayFormatting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.qt=QApplication.instance() or QApplication([])

    def test_fixed_colors_across_table_comp_hex_and_item_widgets(self):
        from PySide6.QtWidgets import QLabel
        pictures=Pictures()
        for avg,color,rgb in [(1.,'rgb(191,254,127)',(191,254,127)),(4.,'rgb(191,254,127)',(191,254,127)),
                               (4.5,'rgb(255,189,121)',(255,189,121)),(8.,'rgb(255,90,100)',(255,90,100))]:
            t=table(['平均排名']);fill_table(t,[[avg]])
            self.assertEqual(t.item(0,0).text(),f'{avg:.2f}');self.assertEqual(t.item(0,0).foreground().color().getRgb()[:3],rgb)
            comp=CompCard({'compId':'1','name':'测试','avgPlacement':avg,'top4Rate':0,'topRate':100,'sampleCount':10001},{},pictures,None)
            values=comp.findChildren(QLabel,'compAverage');self.assertEqual([w.text() for w in values],[f'{avg:.2f}','0.0%','100.0%'])
            self.assertIn(color,values[0].styleSheet())
            rune=ResultCard(1);rune.update_result(['A',f'{avg:.2f} · 49局','— 无该阶段数据'])
            self.assertIn(color,rune.average_label.styleSheet());self.assertEqual(rune.sample.text(),'样本 49局')
            item=ItemOverlay(pictures);item.update_row({'name':'测试','global':{'status':'ok','average':avg,'samples':49},'comp':{'status':'missing'},'holders':[]}, {})
            self.assertEqual(plain(item.global_line.text()),f'全局 {avg:.2f} 49局 · 少');self.assertIn(color,item.global_line.text())
            for w in [t,comp,rune,item]:w.close();w.deleteLater()
        self.qt.processEvents()

    def test_distinct_item_statuses_and_no_stale_portrait(self):
        pictures=Pictures();item=ItemOverlay(pictures)
        for status,expected in [('pending','读取中…'),('missing','暂无数据'),('error','查询失败'),('unrecognized','未识别'),('unpinned','未定阵')]:
            item.update_row({'name':'A','global':{'status':status},'comp':{'status':status},'holders':[],'holder_status':'missing'}, {})
            self.assertEqual(plain(item.global_line.text()),'全局 '+expected)
            self.assertEqual(item.comp_line.isHidden(),status=='unpinned')
            self.assertEqual(item.urls,['',''])
            self.assertTrue(item.holder_lines[0][0].pixmap().isNull())
        item.close();item.deleteLater();self.qt.processEvents()

    def test_low_sample_hex_keeps_value_with_explicit_hint(self):
        self.assertEqual(stat_text({'status':'ok','avg_placement':3.5,'sample_count':49}),'3.50 · 49局 · 少')
        self.assertEqual(stat_text({'status':'ok','avg_placement':3.5,'sample_count':50}),'3.50 · 50局')


if __name__=='__main__':unittest.main()
