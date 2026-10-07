"""Single-condition comp browsing and selection, independent of game capture."""
from collections import deque
from functools import lru_cache
import math
from urllib.parse import urlparse
from PySide6.QtCore import Qt,QObject,Signal,QUrl,QSize,QEvent,QModelIndex
from PySide6.QtGui import QPixmap,QStandardItem,QStandardItemModel
from PySide6.QtNetwork import QNetworkAccessManager,QNetworkRequest,QNetworkDiskCache,QSslSocket
from PySide6.QtWidgets import (QWidget,QFrame,QLabel,QPushButton,QLineEdit,QComboBox,
    QVBoxLayout,QHBoxLayout,QGridLayout,QScrollArea,QCompleter,QButtonGroup,QSizePolicy)
from bootstrap import STATE_DIR,RESOURCE_DIR
from dataj import COMP_MIN_SAMPLE,COMP_MIN_SAMPLE_CHOICES
from stat_colors import placement_color
from condition_inputs import ConditionInputs
from entity_identity import EntityResolver, display_label


def text_label(text,kind='muted'):
    label=QLabel(str(text));label.setObjectName(kind);label.setTextFormat(Qt.TextFormat.PlainText)
    return label


def numeric(value,default=99):
    return float(value) if type(value) in (int,float) and math.isfinite(value) else default


def sufficient_comp_samples(row,minimum=COMP_MIN_SAMPLE):
    count=row.get('sampleCount')
    return type(count) is int and count>=minimum


class SearchCompleter(QCompleter):
    """Typing filters comps. Only a click or deliberate arrow choice sets an entity."""
    def __init__(self,model,parent):
        super().__init__(model,parent);self.choice_armed=False
        self.setFilterMode(Qt.MatchFlag.MatchContains)
        self.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.setMaxVisibleItems(9)

    def eventFilter(self,obj,event):
        if event.type()==QEvent.Type.KeyPress:
            key=event.key()
            if key in (Qt.Key.Key_Down,Qt.Key.Key_Up):self.choice_armed=True
            elif key in (Qt.Key.Key_Return,Qt.Key.Key_Enter) and not self.choice_armed:
                self.popup().hide()
                return obj is self.popup()
            elif key not in (Qt.Key.Key_Return,Qt.Key.Key_Enter,Qt.Key.Key_Control,Qt.Key.Key_Shift):
                self.choice_armed=False
        return super().eventFilter(obj,event)


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


@lru_cache(maxsize=4)
def canonical_portrait_aliases(snapshot):
    """Cache the shared catalog star-family mapping, keeping form IDs separate."""
    keys=('id','name','picture','heroType','price','setId')
    catalog=[dict(zip(keys,values)) for values in snapshot]
    entries=EntityResolver({'hero':catalog}).entries('hero')
    return tuple((row['id'],row.get('picture','')) for row in entries)


def portrait_catalog(rows):
    """IDs differ across endpoints. Name fallback is images-only and unanimous."""
    result={str(row['id']):row for row in rows};pictures={}
    snapshot=tuple((str(row['id']),row['name'],row.get('picture',''),
                    str(row.get('heroType',0)),row.get('price'),
                    str(row.get('setId',18))) for row in rows)
    for identity,picture in canonical_portrait_aliases(snapshot):
        result.setdefault(identity,{'picture':picture})
    for row in rows:pictures.setdefault(row['name'],set()).add(row.get('picture',''))
    for name,urls in pictures.items():
        if len(urls)==1:result['name:'+name]={'picture':next(iter(urls))}
    return result


class HeroPortrait(QWidget):
    def __init__(self,hero,catalog,store,parent=None):
        super().__init__(parent);self.setFixedWidth(54)
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(3)
        name=hero.get('heroName','?');self.setToolTip(name+(' · 主C' if hero.get('isCarry') else ''))
        self.picture=text_label(name[:1],'portrait');self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter);self.picture.setFixedSize(36,36)
        colors={1:'#787887',2:'#5ba884',3:'#609ae6',4:'#bc86e8',5:'#e4bc64'}
        self.picture.setStyleSheet('border:2px solid '+colors.get(hero.get('price'),'#787887')+';border-radius:6px;background:#262535;font-size:18px')
        layout.addWidget(self.picture,0,Qt.AlignmentFlag.AlignHCenter)
        caption=text_label(('★ ' if hero.get('isCarry') else '')+name,'cardMeta');caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        caption.setWordWrap(True);caption.setMinimumHeight(28);layout.addWidget(caption)
        self.url=catalog.get(str(hero.get('heroId')),catalog.get('name:'+name,{})).get('picture','')
        store.ready.connect(self.loaded)
        if self.url in store.images:self.loaded(self.url,store.images[self.url])
        else:store.request(self.url)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def loaded(self,url,pix):
        if url==self.url:self.picture.setPixmap(pix.scaled(QSize(34,34),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))


class CompCard(QFrame):
    selected=Signal(str)
    def __init__(self,row,catalog,portraits,scope,pinned=False):
        super().__init__();self.comp_id=str(row['compId']);self.setObjectName('compCard');self.setProperty('pinned',pinned)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus);self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Maximum)
        self.setAccessibleName('固定阵容 '+row['name']);layout=QVBoxLayout(self);layout.setContentsMargins(10,7,10,7);layout.setSpacing(4)
        header=QHBoxLayout();header.setSpacing(7)
        tier=row.get('tier')
        if tier:
            badge=text_label(str(tier),'badge');badge.setFixedWidth(26);badge.setAlignment(Qt.AlignmentFlag.AlignCenter);header.addWidget(badge)
        title=text_label(row['name'],'cardName');title.setToolTip(row['name']);title.setMinimumWidth(0)
        title.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred);header.addWidget(title,1)
        self.choose=QPushButton('已固定 · 查看' if pinned else '固定');self.choose.setObjectName('chooseComp')
        self.choose.setToolTip('打开本局阵容攻略' if pinned else '固定为本局阵容并查看攻略')
        self.choose.clicked.connect(lambda:self.selected.emit(self.comp_id));header.addWidget(self.choose);layout.addLayout(header)
        heroes=row.get('heroes') or []
        ordered=sorted(heroes,key=lambda h:(not h.get('isCarry'),not h.get('isSubCarry'),not h.get('isCore')))
        lineup=QGridLayout();lineup.setHorizontalSpacing(1);lineup.setVerticalSpacing(3)
        for i,hero in enumerate(ordered):lineup.addWidget(HeroPortrait(hero,catalog,portraits),i//10,i%10)
        if not ordered:lineup.addWidget(text_label('英雄资料暂不可用'),0,0)
        lineup.setColumnStretch(10,1);layout.addLayout(lineup)
        traits=' · '.join(t.get('name','') for t in (row.get('traits') or []))
        if traits:
            trait=text_label(traits,'cardMeta');trait.setWordWrap(True);layout.addWidget(trait)
        footer=QHBoxLayout();footer.setSpacing(5)
        for caption,key,percent in [('条件均排' if scope else '平均排名','avgPlacement',False),('前四率','top4Rate',True),('登顶率','topRate',True)]:
            value=row.get(key);valid=type(value) in (int,float) and math.isfinite(value)
            footer.addWidget(text_label(caption,'cardMeta'))
            formatted=(f'{value:.1f}%' if percent else f'{value:.2f}') if valid else '—'
            number=text_label(formatted,'compAverage')
            number.setStyleSheet('font-size:14px;font-weight:600;color:'+(placement_color(value) if valid and not percent else '#e8e8ee'))
            footer.addWidget(number);footer.addSpacing(7)
        pick=row.get('pickRate');pick_valid=type(pick) in (int,float) and math.isfinite(pick) and pick>=0
        footer.addWidget(text_label('出场','cardMeta'))
        rate=text_label(f'{pick:.2f}' if pick_valid else '—','compPickRate');footer.addWidget(rate)
        rate.setToolTip('DataJ 出场率原始口径，与当前筛选范围一致。')
        footer.addStretch()
        footer.addWidget(text_label(f"{row.get('sampleCount','—'):,} 局" if isinstance(row.get('sampleCount'),int) else '样本 —','cardMeta'))
        layout.addLayout(footer)

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
        self.portraits=Portraits(self,not offline)
        self.resolver=EntityResolver({});self.input_revision=0
        self.sort_mode='avg';self.min_sample=COMP_MIN_SAMPLE;self.failed=False;self.loading=False
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(5)
        self.input_bar=ConditionInputs(self.portraits)
        self.input_bar.entitySelected.connect(self.set_filter)
        self.input_bar.alternativeSelected.connect(lambda k,e:self.set_filter(k,e,can_confirm=True))
        self.input_bar.clearRequested.connect(self.clear_filter)
        search_row=QHBoxLayout();search_row.setSpacing(6)
        self.search=QLineEdit();self.search.setObjectName('compSearch');self.search.setClearButtonEnabled(True)
        self.search.setPlaceholderText('搜索阵容、英雄、海克斯、装备…')
        self.search.setToolTip('输入文字查找当前阵容；选择下拉条件，按该英雄、海克斯、装备或羁绊检索。')
        self.search.setAccessibleName('搜索阵容或选择检索条件')
        self.suggestions=QStandardItemModel(self)
        self.completer=SearchCompleter(self.suggestions,self)
        # QLineEdit.setCompleter also installs automatic string insertion on
        # highlight/activation. We own identity selection, so attach only the
        # completer's popup/event filter and keep the one input's text intact.
        self.completer.setWidget(self.search);self.search.textEdited.connect(self.show_suggestions)
        self.completer.popup().setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.completer.popup().setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.completer.popup().setStyleSheet('QListView { background:#201e2b; color:#e8e2ee; border:1px solid #77613e; padding:3px; font-size:12px; } QListView::item { padding:7px; } QListView::item:selected { background:#463927; color:#f4d594; } QScrollBar:vertical { background:#201e2b; width:6px; } QScrollBar::handle:vertical { background:#63566e; min-height:20px; } QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }')
        self.completer.activated[QModelIndex].connect(self.choose_suggestion)
        search_row.addWidget(self.search,1);search_row.addWidget(self.input_bar.read)
        layout.addLayout(search_row);layout.addWidget(self.input_bar)
        toolbar=QHBoxLayout();toolbar.setSpacing(5);self.sort_group=QButtonGroup(self)
        self.avg_sort=QPushButton('平均排名');self.pick_sort=QPushButton('出场率')
        for mode,button in [('avg',self.avg_sort),('pick',self.pick_sort)]:
            button.setCheckable(True);button.setObjectName('compSort');self.sort_group.addButton(button);toolbar.addWidget(button)
            button.clicked.connect(lambda checked,m=mode:self.set_sort(m))
        self.avg_sort.setChecked(True)
        self.avg_sort.setToolTip('平均排名从低到高');self.pick_sort.setToolTip('按 DataJ 出场率从高到低，同值保持原站顺序')
        toolbar.addStretch();toolbar.addWidget(text_label('最小样本','cardMeta'))
        self.sample=QComboBox();self.sample.setObjectName('compSample');self.sample.setAccessibleName('最小样本')
        for count in COMP_MIN_SAMPLE_CHOICES:self.sample.addItem(f'{count:,} 局',count)
        self.sample.setCurrentIndex(self.sample.findData(self.min_sample));self.sample.setMinimumWidth(88)
        self.sample.setStyleSheet('QComboBox::down-arrow {image:url("'+(RESOURCE_DIR/'chevron-down.svg').as_posix()+'");width:12px;height:8px;}')
        self.sample.setToolTip('按当前检索范围的对局数筛选，与 DataJ 样本档位一致。')
        self.sample.currentIndexChanged.connect(lambda _:self.set_min_sample(self.sample.currentData()))
        toolbar.addWidget(self.sample);layout.addLayout(toolbar)
        self.note=text_label('正在读取阵容…');self.note.setWordWrap(True);layout.addWidget(self.note);self.note.hide()
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        content=QWidget();self.card_layout=QVBoxLayout(content);self.card_layout.setContentsMargins(0,0,4,0);self.card_layout.setSpacing(6);self.card_layout.addStretch()
        self.scroll.setWidget(content);layout.addWidget(self.scroll,1)
        self.more=QPushButton('显示更多阵容');self.more.clicked.connect(self.show_more);self.card_layout.insertWidget(0,self.more);self.more.hide()
        self.empty_box=QWidget();empty_layout=QVBoxLayout(self.empty_box);empty_layout.addStretch()
        self.empty=text_label('','emptyComps');self.empty.setWordWrap(True);self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter);empty_layout.addWidget(self.empty)
        self.retry_button=QPushButton('重试');self.retry_button.clicked.connect(self.retry);empty_layout.addWidget(self.retry_button,0,Qt.AlignmentFlag.AlignCenter)
        empty_layout.addStretch();layout.addWidget(self.empty_box,1);self.empty_box.hide();self.retry_button.hide()
        self.search.textChanged.connect(self.search_changed);self.rebuild_suggestions()

    def set_catalog(self,catalog):
        self.catalog=catalog;self.resolver=EntityResolver(catalog);self.rebuild_suggestions();self.render()

    def rebuild_suggestions(self):
        self.suggestions.clear()
        for row in self.rows:
            if not sufficient_comp_samples(row,self.min_sample):continue
            item=QStandardItem('阵容 · '+row['name']);item.setData(('comp',str(row['compId'])),Qt.ItemDataRole.UserRole)
            self.suggestions.appendRow(item)
        for caption,kind in [('海克斯','hex'),('装备 / 转职','equip'),('英雄','hero'),('羁绊','trait')]:
            for entity in self.resolver.entries(kind):
                item=QStandardItem(caption+' · '+display_label(kind,entity));item.setData((kind,entity),Qt.ItemDataRole.UserRole)
                item.setToolTip(entity.get('descText') or entity.get('skillDesc') or entity.get('identity_detail',''))
                self.suggestions.appendRow(item)

    def choose_suggestion(self,index):
        choice=index.data(Qt.ItemDataRole.UserRole)
        if not choice:return
        kind,entity=choice;self.completer.choice_armed=False;self.completer.popup().hide();self.search.clear()
        if kind=='comp':self.compSelected.emit(entity)
        else:self.set_filter(kind,entity,can_confirm=True)

    def set_sort(self,mode):
        if mode not in ('avg','pick'):raise ValueError('Unknown comp sort')
        self.sort_mode=mode;self.avg_sort.setChecked(mode=='avg');self.pick_sort.setChecked(mode=='pick');self.reset_page()

    def set_min_sample(self,minimum):
        if type(minimum) is not int or minimum not in COMP_MIN_SAMPLE_CHOICES:raise ValueError('Invalid minimum sample')
        if minimum==self.min_sample:return
        self.min_sample=minimum;self.sample.blockSignals(True);self.sample.setCurrentIndex(self.sample.findData(minimum));self.sample.blockSignals(False)
        self.rebuild_suggestions();self.reset_page();self.retry()

    def set_filter(self,kind,entity,can_confirm=False):
        resolved=self.resolver.resolve_selection(kind,entity)
        if not resolved.confirmed:
            self.input_bar.show_note(resolved.reason or '条件身份尚未确认，当前检索未改变。');return False
        entity=resolved.entity
        self.input_revision+=1
        self.scope=(kind,entity)
        self.input_bar.set_condition(kind,entity,can_confirm=can_confirm and kind!='trait')
        self.input_bar.show_alternatives([])
        self.input_bar.show_note('');self.search.clear();self.retry();return True

    def clear_filter(self,*_):
        self.input_revision+=1
        self.scope=None;self.search.clear();self.retry()
        self.input_bar.set_condition();self.input_bar.show_note('')
        self.input_bar.show_alternatives([])

    def retry(self,*_):
        self.queryRequested.emit(*(self.scope if self.scope else ('',None)))

    def set_loading(self):
        self.failed=False;self.loading=True;self.rows=[];self.rebuild_suggestions();self.render()
        self.note.setText('正在读取条件匹配阵容…' if self.scope else '正在读取全部阵容…')

    def set_result(self,rows,version):
        self.failed=False;self.loading=False;self.rows=rows;self.limit=8;self.rebuild_suggestions();self.render()
        count=sum(sufficient_comp_samples(row,self.min_sample) for row in rows)
        self.note.setText(f"S18 · {version} · {count} 套阵容 · "+('条件内统计' if self.scope else '全局统计')+f' · 样本≥{self.min_sample}局 · 点击卡片即可固定')

    def set_error(self):
        self.failed=True;self.loading=False;self.rows=[];self.rebuild_suggestions();self.render();self.note.setText('阵容读取失败')

    def set_pinned(self,comp):self.pinned=comp;self.render()

    def reset_page(self,*_):self.limit=8;self.render()

    def search_changed(self,*_):
        self.completer.choice_armed=False;self.reset_page()

    def show_suggestions(self,text):
        if not text.strip():self.completer.popup().hide();return
        self.completer.setCompletionPrefix(text)
        if self.completer.completionCount():self.completer.complete()
        else:self.completer.popup().hide()

    def show_more(self):self.limit+=8;self.render()

    def render(self):
        for card in self.cards:self.card_layout.removeWidget(card);card.hide();card.deleteLater()
        self.cards=[];query=self.search.text().strip().lower()
        # Filter before sorting/pagination, including cached explorer responses.
        # Keep the shared API rows intact for direct equipment-stat lookups.
        rows=[row for row in self.rows if sufficient_comp_samples(row,self.min_sample)
              and (not query or query in (row['name']+' '+ ' '.join(h.get('heroName','') for h in row.get('heroes',[]))).lower())]
        rows.sort(key=(lambda row:-numeric(row.get('pickRate'),float('-inf'))) if self.sort_mode=='pick' else lambda row:numeric(row.get('avgPlacement')))
        heroes=portrait_catalog(self.catalog.get('hero',[]))
        for row in rows[:self.limit]:
            card=CompCard(row,heroes,self.portraits,self.scope,str(row['compId'])==self.pinned)
            card.selected.connect(self.compSelected)
            self.card_layout.insertWidget(self.card_layout.count()-2,card);self.cards.append(card)
        self.more.setVisible(len(rows)>self.limit)
        message=('正在读取阵容…' if self.loading else '阵容读取失败，请重试。' if self.failed else
                 f'没有匹配且样本≥{self.min_sample}局的阵容。可清除搜索文字、检索条件或调整最小样本。')
        self.empty.setText(message);self.empty.setVisible(not rows);self.empty_box.setVisible(not rows)
        self.retry_button.setVisible(self.failed);self.scroll.setVisible(bool(rows))
