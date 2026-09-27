"""Desktop presentation: DataJ-inspired dark surfaces, gold accents and clear stats."""
from PySide6.QtCore import Qt,QPointF
from PySide6.QtGui import QColor,QPainter,QPen,QPolygonF
from PySide6.QtWidgets import QWidget,QFrame,QLabel,QVBoxLayout,QHBoxLayout,QSizePolicy
import math
from stat_colors import placement_color

STYLE = '''
QWidget { color:#e8e8ee; font-family:"Microsoft YaHei UI"; font-size:13px; }
QWidget#companion { background:#101016; }
QFrame#sidebar { background:#14141e; border-right:1px solid #292935; }
QLabel { background:transparent; }
QLabel#brand { font-size:19px; font-weight:700; color:#f7f1df; }
QLabel#eyebrow { font-size:10px; color:#a6a2b4; letter-spacing:2px; }
QLabel#pageTitle { font-size:24px; font-weight:700; }
QLabel#subtitle, QLabel#muted { color:#a3a1b2; font-size:12px; }
QLabel#section { font-size:14px; font-weight:600; color:#dddbe8; }
QLabel#badge { color:#e5bc60; background:#29241c; border:1px solid #4b3f27; border-radius:6px; padding:5px 10px; }
QLabel#target { color:#c1bccf; padding:11px 14px; background:#1b1a26; border:1px solid #302d3f; border-radius:8px; }
QLabel#status { color:#b4afc2; font-size:11px; padding:6px 0; }
QPushButton { background:#22212d; border:1px solid #363342; border-radius:7px; padding:8px 14px; color:#dedbe8; min-height:18px; }
QPushButton:hover { background:#2d293b; border-color:#726044; }
QPushButton:pressed { background:#393046; }
QPushButton:focus { border:1px solid #e0b85a; }
QPushButton:disabled { color:#6f6b7d; background:#1b1a23; border-color:#2b2935; }
QPushButton#primary { background:#dfb65d; border:1px solid #f2cd7a; color:#211b0e; font-size:15px; font-weight:700; padding:13px 22px; }
QPushButton#primary:hover { background:#f0ca76; }
QPushButton#primary:disabled { background:#484031; color:#aaa087; border-color:#484031; }
QPushButton#nav { text-align:left; background:transparent; border:1px solid transparent; padding:13px 14px; color:#a6a2b6; font-size:14px; }
QPushButton#nav:hover { background:#20202c; color:#eee9de; }
QPushButton#nav:checked { background:#322b20; border:1px solid #4c3e28; color:#efc76f; font-weight:600; }
QPushButton#subtle { background:transparent; border-color:transparent; color:#aba5ba; text-align:left; padding:7px 0; }
QPushButton#subtle:hover { color:#efc76f; }
QFrame#hero { background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #272131,stop:1 #1b1b27); border:1px solid #48404e; border-radius:12px; }
QLabel#activity { font-size:17px; font-weight:600; color:#f3ead7; }
QFrame#resultCard { background:#1b1b27; border:1px solid #34313f; border-top:2px solid #9d8050; border-radius:10px; }
QLabel#cardName { font-size:15px; font-weight:600; color:#efeaf3; }
QLabel#metric { font-family:"Segoe UI"; font-size:34px; font-weight:600; color:#eac474; }
QLabel#cardMeta { color:#a7a1b5; font-size:11px; }
QLabel#compMetric { color:#c9c2dc; font-size:12px; padding-top:10px; border-top:1px solid #34303f; }
QWidget#advanced { background:#191923; border-radius:8px; }
QLineEdit,QComboBox { background:#14141e; border:1px solid #373340; border-radius:7px; padding:8px 10px; selection-background-color:#6b5430; }
QLineEdit:focus,QComboBox:focus { border-color:#bc9650; }
QComboBox::drop-down { border:0; width:23px; }
QComboBox QAbstractItemView { background:#23212e; selection-background-color:#493b2b; color:#e9e2d4; border:1px solid #4c4353; }
QTableWidget,QListWidget { background:#191922; alternate-background-color:#1e1d29; border:1px solid #312e3c; border-radius:8px; gridline-color:#2b2935; outline:0; selection-background-color:#3f3427; selection-color:#f5d99e; }
QTableWidget::item { padding:8px; border-bottom:1px solid #292632; }
QTableWidget::item:selected { background:#3c3327; }
QHeaderView::section { background:#14141d; color:#a9a2b7; padding:10px 8px; border:0; border-bottom:1px solid #36303e; font-weight:500; }
QTableCornerButton::section { background:#14141d; border:0; }
QListWidget::item { padding:9px; border-bottom:1px solid #25222d; }
QListWidget::item:selected { background:#3c3327; color:#edce8c; }
QTabWidget::pane { border:0; background:transparent; }
QScrollArea { border:0; background:transparent; }
QScrollArea > QWidget > QWidget { background:#101016; }
QScrollBar:vertical { background:#14131c; width:7px; margin:0; }
QScrollBar::handle:vertical { background:#494152; border-radius:3px; min-height:26px; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical { background:#14131c; }
QScrollBar:horizontal { background:#14131c; height:7px; }
QScrollBar::handle:horizontal { background:#494152; min-width:25px; }
QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal { width:0; }
QScrollBar::add-page:horizontal,QScrollBar::sub-page:horizontal { background:#14131c; }
QCheckBox { spacing:8px; color:#bbb4c9; }
QCheckBox::indicator { width:15px; height:15px; border:1px solid #71604a; background:#17161f; border-radius:3px; }
QCheckBox::indicator:checked { background:#ddb567; }
QToolTip { background:#282331; color:#eee3ce; border:1px solid #796344; padding:8px; }
'''


def label(text,name='muted'):
    widget=QLabel(text);widget.setObjectName(name);widget.setWordWrap(True)
    return widget


class Rune(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.setFixedSize(42,46)

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor('#dfb65d'),1.6));painter.setBrush(QColor('#33291e'))
        points=[QPointF(21+18*math.cos(math.radians(30+60*i)),23+18*math.sin(math.radians(30+60*i))) for i in range(6)]
        painter.drawPolygon(QPolygonF(points))
        painter.drawLine(QPointF(21,11),QPointF(21,35));painter.drawLine(QPointF(12,18),QPointF(30,28))
        painter.drawLine(QPointF(12,28),QPointF(30,18));painter.end()


class ResultCard(QFrame):
    def __init__(self,number):
        super().__init__();self.setObjectName('resultCard')
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred)
        layout=QVBoxLayout(self);layout.setContentsMargins(18,17,18,17);layout.setSpacing(9)
        top=QHBoxLayout();top.addWidget(label(f'选项 {number:02d}','cardMeta'));top.addStretch()
        top.addWidget(label('强化符文','cardMeta'));layout.addLayout(top)
        self.name=label('等待海克斯','cardName');self.name.setMinimumHeight(42);layout.addWidget(self.name)
        layout.addWidget(label('全局平均排名','cardMeta'))
        self.average_label=label('—','metric');layout.addWidget(self.average_label)
        self.sample=label('出现选择后自动读取','cardMeta');layout.addWidget(self.sample)
        self.comp=label('本局阵容  ·  尚未固定','compMetric');layout.addWidget(self.comp)

    def clear(self,target=False):
        self.name.setText('等待海克斯');self.average_label.setText('—')
        self.average_label.setStyleSheet('')
        self.sample.setText('出现选择后自动读取');self.comp.setText('本局阵容  ·  等待数据' if target else '本局阵容  ·  尚未固定')

    def update_result(self,row):
        name,global_text,comp_text=row
        self.name.setText(name)
        parts=global_text.split(' · ',1)
        numeric=parts[0].replace('.','',1).isdigit()
        self.average_label.setText(parts[0] if numeric else '—')
        color=placement_color(float(parts[0])) if numeric else '#a7a1b5'
        self.average_label.setStyleSheet('color:'+color)
        self.sample.setText('样本 '+parts[1] if numeric and len(parts)>1 else global_text.lstrip('— '))
        self.comp.setText('本局阵容  ·  '+comp_text)
