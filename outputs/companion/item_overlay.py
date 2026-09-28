"""Compact, non-interactive item ranks located above each game choice."""
import ctypes as c
import html
from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout
import win_capture as win
from stat_colors import placement_color
from comp_browser import portrait_catalog


# Fraction of card height reserved above the card; the header reaches .48.
HEADER_CLEARANCE = .52


def compact_samples(count):
    if count>=10000:return f'{count/10000:.1f}万'
    if count>=1000:return f'{count/1000:.1f}千'
    return str(count)


def metric(value):
    status=value.get('status')
    if status=='ok':
        average=value['average'];n=value['samples']
        return (f'<b style="color:{placement_color(average)}">{average:.2f}</b>'
                f' <span style="color:#a5a2b3">{n:,}局'+(' · 少' if n<50 else '')+'</span>')
    return {'pending':'读取中…','missing':'暂无数据','error':'查询失败','unrecognized':'未识别',
            'unpinned':'未定阵'}.get(status,'—')


class ItemOverlay(QWidget):
    def __init__(self, portraits):
        super().__init__(None,Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|
                         Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.WindowTransparentForInput|
                         Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setObjectName('itemRank')
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet('QWidget#itemRank {background:#191922;border:1px solid #6d5d40;border-radius:6px;}'
                          'QLabel {background:transparent;border:0;color:#e8e8ee;font-size:11px;}')
        layout=QVBoxLayout(self);layout.setContentsMargins(6,6,6,6);layout.setSpacing(2)
        self.title=QLabel();self.title.setWordWrap(True);self.title.setFixedHeight(30)
        self.title.setStyleSheet('font-weight:600;color:#f1e6c8;');layout.addWidget(self.title)
        self.global_line=QLabel();self.comp_line=QLabel()
        layout.addWidget(self.global_line);layout.addWidget(self.comp_line)
        self.holder_lines=[];self.urls=['',''];self.portraits=portraits
        for _ in range(2):
            row=QHBoxLayout();row.setSpacing(3)
            picture=QLabel();picture.setFixedSize(24,24)
            picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
            picture.setStyleSheet('background:#292834;border-radius:3px;')
            name=QLabel();row.addWidget(picture);row.addWidget(name,1);layout.addLayout(row)
            self.holder_lines.append((picture,name))
        self.setFixedHeight(132)
        portraits.ready.connect(self.picture_loaded)
        self.handle=int(self.winId())

    def picture_loaded(self,url,pix):
        for index,wanted in enumerate(self.urls):
            if wanted and wanted==url:
                self.holder_lines[index][0].setPixmap(pix.scaled(QSize(24,24),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))

    def update_row(self,row,catalog):
        self.title.setText(html.escape(row['name']))
        self.global_line.setText('全局 '+metric(row['global']))
        self.comp_line.setText('本阵容 '+metric(row['comp']))
        self.comp_line.setVisible(row['comp'].get('status')!='unpinned')
        pictures=portrait_catalog(catalog.get('hero',[]))
        holders=row.get('holders',[])
        self.urls=['','']
        for i,(picture,label) in enumerate(self.holder_lines):
            picture.clear();label.clear()
            picture.setVisible(i<len(holders))
            if i<len(holders):
                hero=holders[i];name=hero['name']
                self.urls[i]=pictures.get(hero['id'],pictures.get('name:'+name,{})).get('picture','')
                label.setText(f'{html.escape(name)} <b style="color:{placement_color(hero["average"])}">{hero["average"]:.2f}</b> '
                              f'<span style="color:#a5a2b3;font-size:9px">{compact_samples(hero["samples"])}局</span>')
                if self.urls[i] in self.portraits.images:self.picture_loaded(self.urls[i],self.portraits.images[self.urls[i]])
                else:self.portraits.request(self.urls[i])
            elif i==0:
                label.setText({'pending':'读取持有者…','error':'持有者暂不可用',
                               'missing':'暂无足够样本','unrecognized':'该项未确认'}.get(row.get('holder_status'),'—'))

    def place(self,binding,box,image_size,gap):
        left,top,right,bottom=binding.rect
        sx=(right-left)/image_size[0];sy=(bottom-top)/image_size[1];dpi=binding.dpi/96
        # Leave the game's shared selection header and all item names unobstructed.
        width=max(100,min(250,round(gap*sx*.92/dpi)))
        self.setFixedWidth(width)
        x=round(left+(box[0][0]+box[1][0])/2*sx-width*dpi/2)
        card_height=box[2][1]-box[0][1]
        y=round(top+(box[0][1]-HEADER_CLEARANCE*card_height)*sy-self.height()*dpi)
        x=max(left,min(x,right-round(width*dpi)));y=max(top,y)
        if not self.isVisible():self.show()
        win.user.SetWindowPos(self.handle,c.c_void_p(-1),x,y,round(width*dpi),round(self.height()*dpi),0x10|0x40)
