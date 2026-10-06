"""Compact confirmed-resource shortcuts and explicit input actions."""
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget, QLabel, QPushButton, QHBoxLayout, QVBoxLayout, QMenu


class ConditionInputs(QWidget):
    entitySelected=Signal(str,object)
    readRequested=Signal()
    confirmRequested=Signal()
    clearRequested=Signal()
    alternativeSelected=Signal(str,object)

    def __init__(self,portraits=None,parent=None):
        super().__init__(parent)
        self.portraits=portraits;self.chips=[];self.resources=[];self.condition=None
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(4)
        self.resource_row=QHBoxLayout();self.resource_row.setSpacing(4)
        title=QLabel('本局已选');title.setObjectName('cardMeta');self.resource_row.addWidget(title)
        self.empty=QLabel('读取详情，确认已选后可快捷检索');self.empty.setObjectName('cardMeta')
        self.resource_row.addWidget(self.empty,1)
        self.more=QPushButton('更多 ▾');self.more.setFixedWidth(62);self.more.hide()
        self.menu=QMenu(self.more);self.more.setMenu(self.menu);self.resource_row.addWidget(self.more)
        layout.addLayout(self.resource_row)
        row=QHBoxLayout();row.setSpacing(5)
        self.current=QLabel('检索条件：全部阵容');self.current.setObjectName('filterStatus')
        self.current.setTextFormat(Qt.TextFormat.PlainText);row.addWidget(self.current,1)
        self.clear=QPushButton('×');self.clear.setFixedWidth(26);self.clear.setToolTip('清除当前单条件')
        self.clear.clicked.connect(self.clearRequested);self.clear.hide();row.addWidget(self.clear)
        self.read=QPushButton('从游戏取条件');self.read.setToolTip('在游戏打开名称详情后按侧键；选择页仍补查均排')
        self.read.clicked.connect(self.readRequested);row.addWidget(self.read)
        self.confirm=QPushButton('记为本局已选');self.confirm.clicked.connect(self.confirmRequested)
        self.confirm.hide();row.addWidget(self.confirm);layout.addLayout(row)
        self.note=QLabel('');self.note.setObjectName('cardMeta');self.note.setWordWrap(True)
        self.note.setTextFormat(Qt.TextFormat.PlainText);self.note.hide();layout.addWidget(self.note)
        self.alternatives=QWidget();self.alternative_row=QHBoxLayout(self.alternatives)
        self.alternative_row.setContentsMargins(0,0,0,0);self.alternative_buttons=[]
        self.alternatives.hide();layout.addWidget(self.alternatives)
        if portraits is not None:portraits.ready.connect(self.image_loaded)

    def set_resources(self,resources):
        from entity_identity import display_label
        self.resources=list(resources)
        for chip in self.chips:self.resource_row.removeWidget(chip);chip.hide();chip.deleteLater()
        self.chips=[];self.menu.clear();self.empty.setVisible(not resources)
        for index,item in enumerate(self.resources):
            kind,entity=item['kind'],item['entity']
            name=entity['name'];hint=display_label(kind,entity)
            short=hint if kind=='hero' else name
            if index<3:
                chip=QPushButton(short);chip.setToolTip(hint+'\n点击只检索这一项；记录不代表当前库存数量')
                chip.setMaximumWidth(150);chip.setIconSize(QSize(18,18));chip.setProperty('picture',entity.get('picture',''))
                chip.clicked.connect(lambda checked=False,k=kind,e=entity:self.entitySelected.emit(k,e))
                self.resource_row.insertWidget(index+1,chip);self.chips.append(chip)
                if self.portraits:
                    url=entity.get('picture','')
                    if url in self.portraits.images:self.image_loaded(url,self.portraits.images[url])
                    else:self.portraits.request(url)
            else:
                action=self.menu.addAction(hint)
                action.triggered.connect(lambda checked=False,k=kind,e=entity:self.entitySelected.emit(k,e))
        self.more.setVisible(len(resources)>3)

    def image_loaded(self,url,pix):
        for chip in self.chips:
            if chip.property('picture')==url:chip.setIcon(QIcon(pix))

    def set_condition(self,kind=None,entity=None,can_confirm=False):
        from entity_identity import display_label
        self.condition=(kind,entity) if entity else None
        self.current.setText('仅检索：'+display_label(kind,entity) if entity else '检索条件：全部阵容')
        self.current.setToolTip(self.current.text())
        self.clear.setVisible(entity is not None);self.confirm.setVisible(bool(entity and can_confirm))

    def show_note(self,message):
        self.note.setText(message);self.note.setVisible(bool(message))

    def show_alternatives(self,candidates):
        from entity_identity import display_label
        for item in self.alternative_buttons:self.alternative_row.removeWidget(item);item.hide();item.deleteLater()
        self.alternative_buttons=[]
        for entity in candidates[:4]:
            kind=entity.get('kind')
            if kind not in ('hex','equip','hero'):continue
            item=QPushButton(display_label(kind,entity));item.setMaximumWidth(180)
            item.setToolTip(entity.get('skillDesc') or entity.get('descText') or display_label(kind,entity))
            item.setEnabled(entity.get('identity_selectable') is True)
            item.clicked.connect(lambda checked=False,k=kind,e=entity:self.alternativeSelected.emit(k,e))
            self.alternative_row.addWidget(item);self.alternative_buttons.append(item)
        self.alternatives.setVisible(bool(self.alternative_buttons))
