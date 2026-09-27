"""Single-condition comp browsing and selection, independent of game capture."""
from collections import deque
import json
import math
from urllib.parse import urlparse
from PySide6.QtCore import Qt,QObject,Signal,QUrl,QSize
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager,QNetworkRequest,QNetworkDiskCache,QSslSocket
from PySide6.QtWidgets import (QWidget,QFrame,QLabel,QPushButton,QLineEdit,QComboBox,
    QVBoxLayout,QHBoxLayout,QScrollArea,QCompleter)
from bootstrap import STATE_DIR
from stat_colors import placement_color


def text_label(text,kind='muted'):
    label=QLabel(str(text));label.setObjectName(kind);label.setTextFormat(Qt.TextFormat.PlainText)
    return label


def numeric(value,default=99):
    return float(value) if isinstance(value,(int,float)) and math.isfinite(value) else default


class Portraits(QObject):
    ready=Signal(str,QPixmap)
    def __init__(self,parent,enabled=True):
        super().__init__(parent);self.enabled=enabled;self.images={};self.pending=set();self.queue=deque();self.active=0
        # Windows native TLS avoids loading incompatible OpenSSL DLLs from PATH.
        # Disable optional portraits if native TLS is unavailable; never bypass TLS.
        if not QSslSocket.setActiveBackend('schannel'):self.enabled=False
        self.manager=QNetworkAccessManager(self)
        cache=QNetworkDiskCache(self);cache.setCacheDirectory(str(STATE_DIR/'portraits'));cache.setMaximumCacheSize(30*1024*1024)
        self.manager.setCache(cache)

    def request(self,url):
        if not self.enabled or not isinstance(url,str):return
        parsed=urlparse(url)
        if parsed.scheme!='https' or parsed.netloc!='img.dataj.cc':return
        if url in self.images or url in self.pending:return
        self.pending.add(url);self.queue.append(url);self.pump()

    def pump(self):
        while self.active<4 and self.queue:
            url=self.queue.popleft();request=QNetworkRequest(QUrl(url));request.setTransferTimeout(8000)
            request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
            request.setAttribute(QNetworkRequest.Attribute.CacheLoadControlAttribute,QNetworkRequest.CacheLoadControl.PreferCache)
            reply=self.manager.get(request);self.active+=1
            reply.downloadProgress.connect(lambda received,total,r=reply:r.abort() if max(received,total)>2*1024*1024 else None)
            reply.finished.connect(lambda r=reply,u=url:self.finished(r,u))

    def finished(self,reply,url):
        if reply.error()==reply.NetworkError.NoError:
            body=reply.readAll();pix=QPixmap()
            if len(body)<2*1024*1024 and pix.loadFromData(body):
                if len(self.images)>256:self.images.clear()
                self.images[url]=pix;self.ready.emit(url,pix)
        self.pending.discard(url);reply.deleteLater();self.active-=1;self.pump()


def portrait_catalog(rows):
    """IDs differ across endpoints. Name fallback is images-only and unanimous."""
    result={str(row['id']):row for row in rows};pictures={}
    for row in rows:pictures.setdefault(row['name'],set()).add(row.get('picture',''))
    for name,urls in pictures.items():
        if len(urls)==1:result['name:'+name]={'picture':next(iter(urls))}
    return result


class HeroPortrait(QWidget):
    def __init__(self,hero,catalog,store,parent=None):
        super().__init__(parent);self.setFixedWidth(62)
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(3)
        name=hero.get('heroName','?');self.setToolTip(name+(' · 主C' if hero.get('isCarry') else ''))
        self.picture=text_label(name[:1],'portrait');self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter);self.picture.setFixedSize(36,36)
        colors={1:'#787887',2:'#5ba884',3:'#609ae6',4:'#bc86e8',5:'#e4bc64'}
        self.picture.setStyleSheet('border:2px solid '+colors.get(hero.get('price'),'#787887')+';border-radius:6px;background:#262535;font-size:18px')
        layout.addWidget(self.picture,0,Qt.AlignmentFlag.AlignHCenter)
        caption=text_label(name,'cardMeta');caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        caption.setWordWrap(True);caption.setMinimumHeight(30);layout.addWidget(caption)
        self.url=catalog.get(str(hero.get('heroId')),catalog.get('name:'+name,{})).get('picture','')
        store.ready.connect(self.loaded)
        if self.url in store.images:self.loaded(self.url,store.images[self.url])
        else:store.request(self.url)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def loaded(self,url,pix):
        if url==self.url:self.picture.setPixmap(pix.scaled(QSize(34,34),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))


class CompCard(QFrame):
    selected=Signal(str)
    starred=Signal(str,bool)
    def __init__(self,row,catalog,portraits,scope,favorite=False,pinned=False):
        super().__init__();self.comp_id=str(row['compId']);self.setObjectName('compCard');self.setProperty('pinned',pinned)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus);self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName('选择阵容 '+row['name']);layout=QVBoxLayout(self);layout.setContentsMargins(14,10,14,10);layout.setSpacing(7)
        header=QHBoxLayout();header.setSpacing(10)
        tier=row.get('tier');title=text_label(row['name'],'cardName');header.addWidget(title)
        if tier:header.addWidget(text_label(str(tier),'badge'))
        header.addStretch()
        average=row.get('avgPlacement');metric=text_label(f'{average:.2f}' if numeric(average)!=99 else '—','compAverage')
        metric.setStyleSheet('font-size:22px;font-weight:600;color:'+ (placement_color(average) if numeric(average)!=99 else '#a7a1b5'))
        header.addWidget(text_label('条件内均排' if scope else '全局均排','cardMeta'));header.addWidget(metric)
        header.addWidget(text_label(f"{row.get('sampleCount','—')} 局",'cardMeta'))
        self.star=QPushButton('★' if favorite else '☆');self.star.setCheckable(True);self.star.setChecked(favorite);self.star.setFixedSize(32,28)
        self.star.setToolTip('收藏阵容，不改变本局目标');self.star.setStyleSheet('padding:0;color:#dfb65d')
        self.star.clicked.connect(lambda checked:self.starred.emit(self.comp_id,checked));header.addWidget(self.star);layout.addLayout(header)
        footer=QHBoxLayout();heroes=row.get('heroes') or []
        ordered=sorted(heroes,key=lambda h:(not h.get('isCarry'),not h.get('isSubCarry'),not h.get('isCore')))
        for hero in ordered[:6]:footer.addWidget(HeroPortrait(hero,catalog,portraits))
        if not ordered:footer.addWidget(text_label('英雄资料暂不可用'))
        footer.addStretch()
        traits=' · '.join(t.get('name','') for t in (row.get('traits') or [])[:3])
        side=QVBoxLayout();side.setSpacing(4)
        if traits:
            trait=text_label(traits,'cardMeta');trait.setWordWrap(True);trait.setMaximumWidth(200);side.addWidget(trait)
        self.choose=QPushButton('已固定 · 查看' if pinned else '选这套  →');self.choose.setObjectName('chooseComp')
        self.choose.clicked.connect(lambda:self.selected.emit(self.comp_id));side.addWidget(self.choose);footer.addLayout(side);layout.addLayout(footer)

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.selected.emit(self.comp_id)
        super().mouseReleaseEvent(event)

    def keyPressEvent(self,event):
        if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter,Qt.Key.Key_Space):self.selected.emit(self.comp_id)
        else:super().keyPressEvent(event)


class CompBrowser(QWidget):
    queryRequested=Signal(str,object)
    compSelected=Signal(str)
    def __init__(self,settings,offline=False):
        super().__init__();self.settings=settings;self.catalog={};self.rows=[];self.scope=None;self.pinned=None;self.limit=8;self.cards=[]
        try:self.favorites=set(json.loads(settings.value('favorite_comps','[]')))
        except (ValueError,TypeError):self.favorites=set()
        self.portraits=Portraits(self,not offline)
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(12)
        filter_box=QFrame();filter_box.setObjectName('filterBox');filters=QVBoxLayout(filter_box);filters.setContentsMargins(14,12,14,12);filters.setSpacing(8)
        caption=QHBoxLayout();caption.addWidget(text_label('检索器','section'));caption.addWidget(text_label('选择一个条件，筛选适合的阵容'));caption.addStretch();filters.addLayout(caption)
        row=QHBoxLayout();self.kind=QComboBox()
        for name,key in [('装备 / 转职','equip'),('海克斯','hex'),('英雄','hero'),('羁绊档位','trait')]:self.kind.addItem(name,key)
        self.kind.setMinimumWidth(125);row.addWidget(self.kind)
        self.entity=QComboBox();self.entity.setEditable(True);self.entity.setInsertPolicy(QComboBox.InsertPolicy.NoInsert);self.entity.setMinimumWidth(230)
        self.entity.lineEdit().setPlaceholderText('输入名称，选择一个条件…');row.addWidget(self.entity,1)
        self.apply=QPushButton('筛选');self.apply.clicked.connect(self.apply_filter);row.addWidget(self.apply)
        self.clear=QPushButton('清除');self.clear.clicked.connect(self.clear_filter);row.addWidget(self.clear);filters.addLayout(row)
        self.condition=text_label('未添加条件 · 显示全部阵容','filterStatus');self.condition.setWordWrap(True);filters.addWidget(self.condition)
        layout.addWidget(filter_box)
        toolbar=QHBoxLayout();self.search=QLineEdit();self.search.setPlaceholderText('搜索阵容或核心英雄…');toolbar.addWidget(self.search,1)
        self.sort=QComboBox();self.sort.addItems(['均排优先','样本优先']);toolbar.addWidget(self.sort)
        self.only_favs=QPushButton('☆ 收藏');self.only_favs.setCheckable(True);toolbar.addWidget(self.only_favs)
        self.refresh=QPushButton('刷新');toolbar.addWidget(self.refresh);layout.addLayout(toolbar)
        self.note=text_label('正在读取阵容…');self.note.setWordWrap(True);layout.addWidget(self.note)
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        content=QWidget();self.card_layout=QVBoxLayout(content);self.card_layout.setContentsMargins(0,0,4,0);self.card_layout.setSpacing(10);self.card_layout.addStretch()
        self.scroll.setWidget(content);layout.addWidget(self.scroll,1)
        self.more=QPushButton('显示更多阵容');self.more.clicked.connect(self.show_more);layout.addWidget(self.more);self.more.hide()
        self.empty=text_label('','emptyComps');self.empty.setWordWrap(True);self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter);layout.addWidget(self.empty);self.empty.hide()
        self.kind.currentIndexChanged.connect(self.populate_entities)
        self.entity.activated.connect(self.apply_filter)
        self.search.textChanged.connect(self.reset_page);self.sort.currentIndexChanged.connect(self.reset_page);self.only_favs.toggled.connect(self.reset_page)
        self.refresh.clicked.connect(self.retry);self.populate_entities()

    def set_catalog(self,catalog):
        self.catalog=catalog;self.populate_entities();self.render()

    def populate_entities(self,*_):
        self.entity.blockSignals(True);self.entity.clear();self.entity.addItem('选择一个条件…',None)
        kind=self.kind.currentData()
        names={}
        for row in self.catalog.get(kind,[]):names[row['name']]=names.get(row['name'],0)+1
        for row in self.catalog.get(kind,[]):
            if kind=='hero' and (row.get('heroType')!=0 or numeric(row.get('price'),0)<=0):continue
            suffix=(f" · {row.get('num','')}级" if kind=='trait' else f" · 品质{row.get('level','')}" if kind=='hex' else '')
            if kind!='trait' and names[row['name']]>1:suffix+=f" · ID {row['id']}"
            self.entity.addItem(row['name']+suffix,row)
        self.entity.setCurrentIndex(0);self.entity.blockSignals(False)
        self.entity.completer().setFilterMode(Qt.MatchFlag.MatchContains);self.entity.completer().setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.entity.completer().setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

    def apply_filter(self,*_):
        item=self.entity.currentData()
        if item is None or self.entity.currentText()!=self.entity.itemText(self.entity.currentIndex()):
            active=('当前条件：'+self.scope[1]['name']) if self.scope else '当前显示全部阵容'
            self.condition.setText(active+' · 请从搜索结果选择完整条件后筛选');return
        self.scope=(self.kind.currentData(),item);self.condition.setText('仅使用：'+self.entity.currentText());self.search.clear();self.retry()

    def set_filter(self,kind,entity):
        self.kind.setCurrentIndex(max(0,self.kind.findData(kind)))
        for i in range(self.entity.count()):
            row=self.entity.itemData(i)
            if row and str(row['id'])==str(entity['id']) and (kind!='trait' or row.get('num')==entity.get('num')):
                self.entity.setCurrentIndex(i);break
        self.scope=(kind,entity);self.condition.setText('仅使用：'+entity['name']);self.retry()

    def clear_filter(self,*_):
        self.scope=None;self.entity.setCurrentIndex(0);self.search.clear();self.condition.setText('未添加条件 · 显示全部阵容');self.retry()

    def retry(self,*_):
        self.queryRequested.emit(*(self.scope if self.scope else ('',None)))

    def set_loading(self):
        self.rows=[];self.render();self.note.setText('正在读取条件匹配阵容…' if self.scope else '正在读取全部阵容…');self.empty.hide()

    def set_result(self,rows,version):
        self.rows=rows;self.limit=8;self.render();self.note.setText(f"S18 · {version} · {len(rows)} 套阵容 · "+('条件内统计' if self.scope else '全局统计')+' · 点击卡片即可固定')

    def set_error(self):
        self.rows=[];self.render();self.note.setText('阵容读取失败');self.empty.setText('暂时无法取得阵容。请点击「刷新」重试。');self.empty.show()

    def set_pinned(self,comp):self.pinned=comp;self.render()

    def reset_page(self,*_):self.limit=8;self.render()

    def show_more(self):self.limit+=8;self.render()

    def favorite_changed(self,comp,checked):
        if checked:self.favorites.add(comp)
        else:self.favorites.discard(comp)
        self.settings.setValue('favorite_comps',json.dumps(sorted(self.favorites)));self.settings.sync()
        self.render()

    def render(self):
        for card in self.cards:self.card_layout.removeWidget(card);card.hide();card.deleteLater()
        self.cards=[];query=self.search.text().strip().lower()
        rows=[row for row in self.rows if (not self.only_favs.isChecked() or str(row['compId']) in self.favorites)
              and (not query or query in (row['name']+' '+ ' '.join(h.get('heroName','') for h in row.get('heroes',[]))).lower())]
        rows.sort(key=(lambda row:-numeric(row.get('sampleCount'),0)) if self.sort.currentIndex() else lambda row:numeric(row.get('avgPlacement')))
        heroes=portrait_catalog(self.catalog.get('hero',[]))
        for row in rows[:self.limit]:
            card=CompCard(row,heroes,self.portraits,self.scope,str(row['compId']) in self.favorites,str(row['compId'])==self.pinned)
            card.selected.connect(self.compSelected);card.starred.connect(self.favorite_changed)
            self.card_layout.insertWidget(self.card_layout.count()-1,card);self.cards.append(card)
        self.more.setVisible(len(rows)>self.limit)
        self.empty.setText('没有匹配阵容。试试清除条件、搜索文字或收藏筛选。');self.empty.setVisible(not rows)
