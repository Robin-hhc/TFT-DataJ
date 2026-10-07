"""Compact confirmed-resource shortcuts and explicit input actions."""
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget, QLabel, QPushButton, QHBoxLayout, QVBoxLayout, QMenu, QSizePolicy


class ConditionInputs(QWidget):
    entitySelected=Signal(str,object)
    readRequested=Signal()
    confirmRequested=Signal()
    clearRequested=Signal()
    alternativeSelected=Signal(str,object)

    def __init__(self,portraits=None,parent=None):
        super().__init__(parent)
        self.portraits=portraits;self.chips=[];self.resources=[];self.condition=None
        self.setStyleSheet('QPushButton { font-size:11px; padding:3px 6px; min-height:16px; }')
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(3)
        self.resource_container=QWidget();self.resource_container.setObjectName('resource_container')
        self.resource_row=QHBoxLayout(self.resource_container)
        self.resource_row.setContentsMargins(0,0,0,0);self.resource_row.setSpacing(3)
        title=QLabel('本局已选');title.setObjectName('cardMeta');title.setFixedWidth(title.sizeHint().width());self.resource_row.addWidget(title)
        self.empty=QLabel('');self.empty.setObjectName('cardMeta')
        self.resource_row.addWidget(self.empty,1)
        self.resource_row.addStretch(1)
        self.more=QPushButton('更多 ▾');self.more.setFixedWidth(54);self.more.hide()
        self.menu=QMenu(self.more);self.more.setMenu(self.menu);self.resource_row.addWidget(self.more)
        layout.addWidget(self.resource_container)
        self.condition_container=QWidget();self.condition_container.setObjectName('condition_container')
        condition_layout=QVBoxLayout(self.condition_container)
        condition_layout.setContentsMargins(0,0,0,0);condition_layout.setSpacing(3)
        self.condition_row=QHBoxLayout();self.condition_row.setSpacing(3)
        row=self.condition_row
        self.current=QLabel('');self.current.setObjectName('filterStatus')
        self.current.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        self.current.setTextFormat(Qt.TextFormat.PlainText);row.addWidget(self.current,1)
        self.clear=QPushButton('×');self.clear.setFixedWidth(24);self.clear.setToolTip('清除检索条件')
        self.clear.clicked.connect(self.clearRequested);self.clear.hide();row.addWidget(self.clear)
        self.read=QPushButton('从游戏取条件');self.read.setToolTip('读取游戏中已打开的名称详情；也可直接在游戏按鼠标侧键。选择页仍补查均排。')
        self.read.clicked.connect(self.readRequested);row.addWidget(self.read)
        self.confirm=QPushButton('记为已选');self.confirm.clicked.connect(self.confirmRequested)
        self.confirm.setToolTip('确认这是你本局已经选中的内容，再记录为本局已选；不会自动记录其他候选项')
        self.confirm.hide();row.addWidget(self.confirm);condition_layout.addLayout(row)
        self.note=QLabel('');self.note.setObjectName('cardMeta');self.note.setWordWrap(True)
        self.note.setTextFormat(Qt.TextFormat.PlainText);self.note.hide();condition_layout.addWidget(self.note)
        self.alternatives=QWidget();self.alternative_row=QHBoxLayout(self.alternatives)
        self.alternative_row.setContentsMargins(0,0,0,0);self.alternative_row.setSpacing(3)
        self.alternative_buttons=[]
        self.alternatives.hide();condition_layout.addWidget(self.alternatives)
        layout.addWidget(self.condition_container)
        self.set_condition()
        self.resource_container.hide()
        if portraits is not None:portraits.ready.connect(self.image_loaded)

    def _update_visibility(self):
        self.resource_container.setVisible(bool(self.resources))
        self.condition_container.setVisible(bool(self.condition or self.note.text() or self.alternative_buttons))

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
                chip.setMinimumWidth(32);chip.setMaximumWidth(112)
                chip.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
                chip.setIconSize(QSize(16,16));chip.setProperty('picture',entity.get('picture',''))
                chip.clicked.connect(lambda checked=False,k=kind,e=entity:self.entitySelected.emit(k,e))
                self.resource_row.insertWidget(index+1,chip,1);self.chips.append(chip)
                if self.portraits:
                    url=entity.get('picture','')
                    if url in self.portraits.images:self.image_loaded(url,self.portraits.images[url])
                    else:self.portraits.request(url)
            else:
                action=self.menu.addAction(hint)
                action.triggered.connect(lambda checked=False,k=kind,e=entity:self.entitySelected.emit(k,e))
        self.more.setVisible(len(resources)>3)
        self._update_visibility()

    def image_loaded(self,url,pix):
        for chip in self.chips:
            if chip.property('picture')==url:chip.setIcon(QIcon(pix))

    def set_condition(self,kind=None,entity=None,can_confirm=False):
        from entity_identity import display_label
        self.condition=(kind,entity) if entity else None
        self.current.setText('条件 · '+display_label(kind,entity) if entity else '')
        self.current.setToolTip(self.current.text())
        self.current.setVisible(entity is not None)
        self.clear.setVisible(entity is not None);self.confirm.setVisible(bool(entity and can_confirm))
        self._update_visibility()

    def show_note(self,message):
        self.note.setText(message);self.note.setVisible(bool(message))
        self._update_visibility()

    def show_alternatives(self,candidates):
        from entity_identity import display_label
        for item in self.alternative_buttons:self.alternative_row.removeWidget(item);item.hide();item.deleteLater()
        self.alternative_buttons=[]
        for entity in candidates[:4]:
            kind=entity.get('kind')
            if kind not in ('hex','equip','hero'):continue
            item=QPushButton(display_label(kind,entity));item.setMinimumWidth(32);item.setMaximumWidth(140)
            item.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
            item.setToolTip(entity.get('skillDesc') or entity.get('descText') or display_label(kind,entity))
            item.setEnabled(entity.get('identity_selectable') is True)
            item.clicked.connect(lambda checked=False,k=kind,e=entity:self.alternativeSelected.emit(k,e))
            self.alternative_row.addWidget(item,1);self.alternative_buttons.append(item)
        self.alternatives.setVisible(bool(self.alternative_buttons))
        self._update_visibility()
