"""Compact, non-interactive item ranks located above each game choice."""
import ctypes as c
import html
from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout
import win_capture as win
from stat_colors import placement_color
from comp_browser import portrait_catalog


# The common selection header starts .48 card-heights above the cards. Leave
# it clear, while anchoring the smaller panel immediately above that boundary.
HEADER_CLEARANCE = .49
OVERLAY_HEIGHT = 96
PORTRAIT_SIZE = 18


def item_overlay_geometry(binding,box,image_size,gap,height=OVERLAY_HEIGHT):
    """Physical client placement shared by native ranks and screenshot QA."""
    left,top,right,bottom=binding.rect
    sx=(right-left)/image_size[0];sy=(bottom-top)/image_size[1];dpi=binding.dpi/96
    width=max(120,min(200,round(gap*sx*.98/dpi)))
    physical_width=round(width*dpi);physical_height=round(height*dpi)
    x=round(left+(box[0][0]+box[1][0])/2*sx-physical_width/2)
    card_height=box[2][1]-box[0][1]
    y=round(top+(box[0][1]-HEADER_CLEARANCE*card_height)*sy-physical_height)
    x=max(left,min(x,right-physical_width));y=max(top,y)
    return x,y,physical_width,physical_height


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
        layout=QVBoxLayout(self);layout.setContentsMargins(5,4,5,4);layout.setSpacing(1)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.title=QLabel();self.title.setWordWrap(True);self.title.setFixedHeight(16)
        self.title.setStyleSheet('font-weight:600;color:#f1e6c8;');layout.addWidget(self.title)
        self.global_line=QLabel();self.comp_line=QLabel()
        self.global_line.setFixedHeight(14);self.comp_line.setFixedHeight(14)
        layout.addWidget(self.global_line);layout.addWidget(self.comp_line)
        self.holder_lines=[];self.urls=['',''];self.portraits=portraits
        self._portrait_keys=[None,None]
        for _ in range(2):
            row=QHBoxLayout();row.setSpacing(3)
            picture=QLabel();picture.setFixedSize(PORTRAIT_SIZE,PORTRAIT_SIZE)
            picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
            picture.setStyleSheet('background:#292834;border-radius:3px;')
            name=QLabel();name.setStyleSheet('font-size:9px;');name.setFixedHeight(PORTRAIT_SIZE)
            row.addWidget(picture);row.addWidget(name,1);layout.addLayout(row)
            self.holder_lines.append((picture,name))
        self.setFixedHeight(OVERLAY_HEIGHT)
        portraits.ready.connect(self.picture_loaded)
        self.handle=int(self.winId())

    def picture_loaded(self,url,pix):
        for index,wanted in enumerate(self.urls):
            if wanted and wanted==url:
                picture=self.holder_lines[index][0]
                key=(url,pix.cacheKey())
                if self._portrait_keys[index]!=key or picture.pixmap().isNull():
                    picture.setPixmap(pix.scaled(QSize(PORTRAIT_SIZE,PORTRAIT_SIZE),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
                    self._portrait_keys[index]=key

    @staticmethod
    def set_text(label,text):
        if label.text()!=text:label.setText(text)

    def update_row(self,row,catalog):
        self.set_text(self.title,html.escape(row['name']))
        self.set_text(self.global_line,'全局 '+metric(row['global']))
        self.set_text(self.comp_line,'本阵容 '+metric(row['comp']))
        comp_visible=row['comp'].get('status')!='unpinned'
        if self.comp_line.isHidden()==comp_visible:self.comp_line.setVisible(comp_visible)
        pictures=portrait_catalog(catalog.get('hero',[]))
        holders=row.get('holders',[])
        for i,(picture,label) in enumerate(self.holder_lines):
            holder_visible=i<len(holders)
            if picture.isHidden()==holder_visible:picture.setVisible(holder_visible)
            url=''
            if holder_visible:
                hero=holders[i];name=hero['name']
                url=pictures.get(hero['id'],pictures.get('name:'+name,{})).get('picture','')
                text=(f'{html.escape(name)} <b style="color:{placement_color(hero["average"])}">{hero["average"]:.2f}</b> '
                      f'<span style="color:#a5a2b3;font-size:8px">{compact_samples(hero["samples"])}局</span>')
            elif i==0:
                text={'pending':'读取持有者…','error':'持有者暂不可用',
                      'missing':'暂无足够样本','unrecognized':'该项未确认'}.get(row.get('holder_status'),'—')
            else:text=''
            self.set_text(label,text)
            if self.urls[i]!=url:
                picture.clear()
                self._portrait_keys[i]=None
                self.urls[i]=url
            if url in self.portraits.images:self.picture_loaded(url,self.portraits.images[url])
            elif url and picture.pixmap().isNull():self.portraits.request(url)

    def place(self,binding,box,image_size,gap):
        x,y,physical_width,physical_height=item_overlay_geometry(binding,box,image_size,gap,self.height())
        width=round(physical_width*96/binding.dpi)
        if self.minimumWidth()!=width or self.maximumWidth()!=width:self.setFixedWidth(width)
        was_visible=self.isVisible()
        if not was_visible:self.show()
        geometry=(x,y,physical_width,physical_height,binding.dpi)
        if not was_visible or geometry!=getattr(self,'_native_geometry',None):
            if win.user.SetWindowPos(self.handle,c.c_void_p(-1),*geometry[:4],0x10|0x40):
                self._native_geometry=geometry
