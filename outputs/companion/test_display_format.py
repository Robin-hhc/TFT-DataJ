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

    def test_identified_hex_without_statistics_is_not_an_ocr_failure(self):
        missing={'status':'missing_or_ambiguous_entity','avg_placement':None}
        self.assertEqual(stat_text(missing,identified=True,scope='global'),'— 暂无全局统计')
        self.assertEqual(stat_text(missing,identified=True,scope='comp'),'— 本阵容暂无统计')
        self.assertEqual(stat_text(missing,identified=False,scope='global'),'— 未识别')
        self.assertEqual(stat_text(missing,identified=False,scope='comp'),'— 未识别')
        # An unresolved current entity cannot display a valid older row either.
        self.assertEqual(stat_text({'status':'ok','avg_placement':3.5,'sample_count':100},
            identified=False,scope='comp'),'— 未识别')

    def test_hex_missing_stage_invalid_value_and_unknown_stage_have_distinct_labels(self):
        for status,expected in [('no_stage_data','— 无该阶段数据'),
                                ('invalid_stat','— 统计不可用'),
                                ('unsupported_stage','— 阶段待确认')]:
            for scope in ('global','comp'):
                with self.subTest(status=status,scope=scope):
                    self.assertEqual(stat_text({'status':status,'avg_placement':None},
                        identified=True,scope=scope),expected)

    def test_zero_sample_hex_cannot_display_stage_or_overall_average(self):
        from snapshot_stats import stage_stat
        rows=[{'hexId':1023,'avgPlacement':4.6,'sampleCount':500,
               'roundStats':[{'round':0,'roundLabel':'2-1','avgPlacement':1.2,'sampleCount':0}]}]
        rune=ResultCard(1)
        try:
            value=stat_text(stage_stat(rows,'1023','2-1'))
            rune.update_result(['应急护甲 I',value,'未固定阵容'])
            self.assertEqual(rune.average_label.text(),'—')
            self.assertEqual(rune.sample.text(),'统计不可用')
            self.assertNotIn('1.20',rune.average_label.text())
            self.assertNotIn('4.60',rune.average_label.text())
        finally:rune.close();rune.deleteLater();self.qt.processEvents()

    def test_zero_sample_item_and_holders_display_missing_state(self):
        from item_stats import item_stat,best_holders
        pictures=Pictures();item=ItemOverlay(pictures)
        try:
            result={'data':[{'equipId':2027,'avgPlacement':1.2,'sampleCount':0}],
                    'source':'offline','fetched_at':1}
            holders=best_holders({'data':[{'heroId':4503,'name':'阿木木','avgPlacement':1.2,'sampleCount':0}]})
            item.update_row({'name':'棘刺背心','global':item_stat(result,'2027'),
                'comp':{'status':'unpinned'},'holders':holders,'holder_status':'missing'}, {})
            self.assertEqual(plain(item.global_line.text()),'全局 暂无数据')
            self.assertEqual(plain(item.holder_lines[0][1].text()),'暂无足够样本')
            self.assertTrue(item.comp_line.isHidden())
            self.assertEqual(item.urls,['',''])
        finally:item.close();item.deleteLater();self.qt.processEvents()


if __name__=='__main__':unittest.main()
