"""Local alpha: stage stats, conservative OCR, single-filter queries and pinned guide."""
from __future__ import annotations
import argparse
import ctypes as c
from ctypes import wintypes as w
from datetime import datetime
import json
import os
import html
import sys
import time
from pathlib import Path

from bootstrap import ROOT, STATE_DIR
import win_capture as win
from core import Session, parse_comp_url
from dataj import DataJ
from snapshot_stats import stage_stat, STAGES
from vision import Vision, capture_image, capture_stage, tracked_signature, unchanged
from floating_mark import FloatingMark
from mouse_shortcut import MouseShortcut
from stat_colors import placement_color
from ui_theme import STYLE, ResultCard, Rune, label
from diagnostics import record, FrameRecorder
from PySide6.QtCore import Qt, QTimer, QObject, Signal, QRunnable, QThreadPool, QUrl, QAbstractNativeEventFilter, QSettings
from PySide6.QtGui import QDesktopServices,QColor
from PySide6.QtWidgets import (QApplication, QWidget, QLabel, QPushButton, QComboBox, QLineEdit,
    QVBoxLayout, QHBoxLayout, QTabWidget, QTableWidget, QTableWidgetItem, QListWidget,
    QListWidgetItem, QCheckBox, QFileDialog, QHeaderView, QAbstractItemView,QFrame,QScrollArea,QButtonGroup)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile


class Signals(QObject):
    done = Signal(object)
    failed = Signal(str)


class Job(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn, self.signals = fn, Signals()

    def run(self):
        try:
            self.signals.done.emit(self.fn())
        except Exception as exc:
            self.signals.failed.emit(str(exc))


def game_windows():
    return [item for item in win.enumerate_mumu()
            if item.process.lower()=='mumunxdevice.exe' and 'QWindowTool' not in item.class_name]


def button(text, action):
    obj = QPushButton(text)
    obj.clicked.connect(action)
    return obj


def table(headers):
    obj = QTableWidget(0,len(headers))
    obj.setHorizontalHeaderLabels(headers)
    obj.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    obj.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    obj.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    obj.horizontalHeader().setMinimumSectionSize(80)
    for column in range(1,len(headers)):obj.horizontalHeader().setSectionResizeMode(column,QHeaderView.ResizeMode.ResizeToContents)
    obj.verticalHeader().hide();obj.verticalHeader().setDefaultSectionSize(44)
    obj.setAlternatingRowColors(True);obj.setShowGrid(False)
    return obj


def fill_table(widget, rows):
    widget.setRowCount(len(rows))
    for row,values in enumerate(rows):
        for col,value in enumerate(values):
            item=QTableWidgetItem(str(value))
            heading=widget.horizontalHeaderItem(col).text()
            if '均排' in heading or '平均排名' in heading:
                try:
                    average=float(str(value).split(' · ')[0])
                    item.setForeground(QColor(placement_color(average)))
                    if isinstance(value,(int,float)):item.setText(f'{average:.2f}')
                except ValueError:pass
            if col>0:item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            widget.setItem(row,col,item)


def stat_text(row):
    if row['status']=='ok':
        return f"{row['avg_placement']:.2f} · {row['sample_count']}局"
    return '— 无该阶段数据' if row['status']=='no_stage_data' else '— 无数据/未识别'


class CardOverlay(QLabel):
    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|
                         Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.WindowTransparentForInput|
                         Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setStyleSheet('background:#191922;color:#f1e6c8;border:1px solid #b99a59;border-radius:7px;padding:7px;font-size:12px')
        self.handle=int(self.winId())

    def place(self, binding, box, text):
        if self.text()!=text:
            self.setText(text)
            self.adjustSize()
        if not self.isVisible():self.show()
        scale=binding.dpi/96
        left,top,right,bottom=binding.rect
        x=round(left+sum(p[0] for p in box)/4-self.width()*scale/2)
        # Center over the game tier badge, below the augment description.
        y=round(top+(bottom-top)*.596-self.height()*scale/2)
        width,height=round(self.width()*scale),round(self.height()*scale)
        x=max(left,min(x,right-width));y=max(top,min(y,bottom-height))
        win.user.SetWindowPos(self.handle,c.c_void_p(-1),x,y,width,height,0x10|0x40)


class GuidePage(QWebEnginePage):
    def acceptNavigationRequest(self,url,kind,is_main):
        return url.toString()=='about:blank' or (url.scheme()=='https' and url.host()=='www.dataj.cc')

    def chooseFiles(self,mode,old_files,accepted_mime_types):
        return []


class Companion(QWidget):
    def __init__(self, offline=False):
        super().__init__()
        self.setWindowTitle('金铲铲 DataJ Companion · 本机试用版')
        self.setObjectName('companion');self.setStyleSheet(STYLE)
        self.resize(1080,760);self.setMinimumSize(920,660)
        self.session=Session()
        self.offline=offline
        self.frame_recorder=FrameRecorder()
        self.save_diagnostic_frames=os.environ.get('DATAJ_DIAGNOSTIC_FRAMES')=='1'
        self.next_ocr_allowed=0.0
        self.stage_probe_pending=False;self.last_stage_probe=0.0
        self.last_probe_stage=None;self.stage_window_until=0.0
        self.last_overlay_diagnostic=None
        self.adapter=DataJ()
        self.vision=Vision()
        self.network=QThreadPool(self);self.network.setMaxThreadCount(1)
        self.ocr_pool=QThreadPool(self);self.ocr_pool.setMaxThreadCount(1)
        self.capture_pool=QThreadPool(self);self.capture_pool.setMaxThreadCount(1)
        self.jobs=set()
        self.mouse_settings=QSettings(str(STATE_DIR/"input.ini"),QSettings.Format.IniFormat)
        self.last_mouse_trigger=-1.0
        self.stats_inflight_token=None
        self.binding=None
        self.geometry=None
        self.capture_pending=False
        self.ocr_busy=False
        self.ocr_live=False
        self.once_active=False
        self.once_ocr_pending=False
        self.once_deadline=0.0
        self.signature=None
        self.stable=0
        self.last_capture=0.0
        self.last_ocr=0.0
        self.ocr_revision=0
        self.catalog={}
        self.comp_detail=None
        self.stats_payload=None
        self.mark=FloatingMark(self.toggle)
        self.last_observation=None
        self.last_frame=None
        self.was_available=False
        self.activity_code=None
        self.reopen_shortcut_available=True
        self.explorer_generation=0
        self.equip_generation=0
        self.comp_generation=0
        self.recent=[]
        self.overlays=[CardOverlay() for _ in range(3)]
        shell=QHBoxLayout(self);shell.setContentsMargins(0,0,0,0);shell.setSpacing(0)
        sidebar=QFrame();sidebar.setObjectName('sidebar');sidebar.setFixedWidth(188)
        rail=QVBoxLayout(sidebar);rail.setContentsMargins(16,28,16,20);rail.setSpacing(9)
        brand=QHBoxLayout();brand.addWidget(Rune());brand.addWidget(label('金铲铲\n助手','brand'));rail.addLayout(brand)
        rail.addWidget(label('DATAJ COMPANION','eyebrow'));rail.addSpacing(28)
        rail.addWidget(label('本局工具','muted'))
        self.navigation=[]
        self.navigation_group=QButtonGroup(self);self.navigation_group.setExclusive(True)
        for index,title in enumerate(['◇   局内辅助','⌕   条件选阵','▤   阵容攻略','▥   英雄出装']):
            nav=button(title,lambda checked=False,i=index:self.tabs.setCurrentIndex(i))
            nav.setObjectName('nav');nav.setCheckable(True);rail.addWidget(nav);self.navigation.append(nav)
            self.navigation_group.addButton(nav,index)
        rail.addStretch();rail.addWidget(label('S18  自然之力','badge'));rail.addSpacing(8)
        rail.addWidget(label('统计来自 DataJ\n仅作局内查询参考','muted'))
        rail.addSpacing(16);rail.addWidget(button('退出助手',QApplication.instance().quit))
        shell.addWidget(sidebar)
        content=QWidget();root=QVBoxLayout(content);root.setContentsMargins(26,24,26,15);root.setSpacing(15)
        shell.addWidget(content,1)
        header=QHBoxLayout();headings=QVBoxLayout();headings.setSpacing(5)
        self.banner=label('海克斯助手','pageTitle');headings.addWidget(self.banner)
        self.subtitle=label('按快捷键查均排，也可开启低频阶段检查。','subtitle');headings.addWidget(self.subtitle)
        header.addLayout(headings,1)
        self.patch=QLineEdit('18.2a');self.patch.setMaximumWidth(100)
        header.addWidget(button('新的一局',self.new_game));header.addWidget(button('收起为小标记',self.return_to_game))
        root.addLayout(header)
        self.target_label=label('本局阵容：未固定','target')
        root.addWidget(self.target_label)
        self.tabs=QTabWidget();self.tabs.tabBar().hide();root.addWidget(self.tabs,1)
        self.make_choices()
        self.make_explorer()
        self.make_guide()
        self.make_equipment()
        self.tabs.currentChanged.connect(self.navigate);self.navigate(0)
        self.status=label('Ctrl + Alt + F9 随时展开或收起助手。','status')
        self.status.setWordWrap(True);root.addWidget(self.status)
        root.addWidget(label('CTRL + ALT + F10   截图查均排     ·     F9 展开 / 收起     ·     F12 退出（均需 CTRL + ALT）','muted'))
        self.timer=QTimer(self);self.timer.timeout.connect(self.tick);self.timer.start(150)
        self.refresh_windows()
        if offline:
            data=json.loads((ROOT/'work/s18-refresh-20260926/catalog.json').read_text(encoding='utf-8'))['data']
            self.catalog_loaded({'data':data},True)
        else:
            self.load_catalog()

    def navigate(self,index):
        headings=[('海克斯助手','按快捷键查均排，也可开启低频阶段检查。'),
                  ('条件选阵','从一件装备、一个转职或一个海克斯开始。'),
                  ('阵容攻略','确定方向后，攻略和阵容统计一起跟随。'),
                  ('英雄出装','查看本局阵容下的装备表现，寻找替代选择。')]
        self.banner.setText(headings[index][0]);self.subtitle.setText(headings[index][1])
        for i,nav in enumerate(self.navigation):nav.setChecked(i==index)

    def add_page(self,page,title):
        page.layout().setContentsMargins(0,2,6,4);page.layout().setSpacing(14)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(page)
        self.tabs.addTab(scroll,title)

    def submit(self,pool,fn,done,failed=None):
        if len(self.jobs)>=8:
            message='已有多个任务处理中，请等待结果后再查询'
            self.status.setText(message)
            if failed:failed(message)
            return
        job=Job(fn);self.jobs.add(job)
        def finish(value):
            self.jobs.discard(job)
            done(value)
        def error(message):
            self.jobs.discard(job)
            self.status.setText(message)
            if failed:failed(message)
        job.signals.done.connect(finish)
        job.signals.failed.connect(error)
        pool.start(job)

    def make_choices(self):
        page=QWidget();layout=QVBoxLayout(page)
        hero=QFrame();hero.setObjectName('hero');hero_layout=QHBoxLayout(hero)
        hero_layout.setContentsMargins(22,22,22,22);hero_layout.setSpacing(22)
        hero_text=QVBoxLayout();hero_text.setSpacing(9)
        hero_text.addWidget(label('手动触发 · 低负载','eyebrow'))
        self.activity=label('正在准备海克斯数据…','activity');hero_text.addWidget(self.activity)
        hero_text.addWidget(label('鼠标侧键截图查均排 · Ctrl+Alt+F10 仍可使用','muted'))
        hero_layout.addLayout(hero_text,1)
        self.start_button=button('截图查均排',self.start_or_pause)
        self.start_button.setObjectName('primary');self.start_button.setMinimumWidth(150)
        self.start_button.setMinimumHeight(46);self.start_button.setEnabled(False)
        hero_layout.addWidget(self.start_button);layout.addWidget(hero)
        self.trigger_mode=QComboBox();self.trigger_mode.addItems(['手动触发（默认）','阶段触发 · 每 3 秒检查顶部回合'])
        self.trigger_mode.currentIndexChanged.connect(self.trigger_mode_changed);layout.addWidget(self.trigger_mode)
        self.mouse_button=QComboBox()
        for title,value in [('后退侧键查均排（默认）',1),('前进侧键查均排',2),('关闭鼠标侧键',0)]:self.mouse_button.addItem(title,value)
        saved=str(self.mouse_settings.value('mouse_button',1)) if not self.offline else '1'
        self.mouse_button.setCurrentIndex({'1':0,'2':1,'0':2}.get(saved,0))
        self.mouse_button.currentIndexChanged.connect(self.save_mouse_button)
        layout.addWidget(self.mouse_button)
        section=QHBoxLayout();section.addWidget(label('当前海克斯','section'));section.addStretch()
        section.addWidget(label('均排越低越好','muted'));layout.addLayout(section)
        cards=QHBoxLayout();cards.setSpacing(12)
        self.result_cards=[ResultCard(i+1) for i in range(3)]
        for card in self.result_cards:cards.addWidget(card,1)
        layout.addLayout(cards)
        self.choice_note=label('等待当前对局的海克斯选择。','muted');layout.addWidget(self.choice_note)
        self.choice_table=table(['海克斯','全局均排 / 样本','本局阵容均排 / 样本'])
        self.choice_table.setParent(page);self.choice_table.hide()
        self.advanced_toggle=button('手动查询与高级设置 ▸',self.toggle_advanced)
        self.advanced_toggle.setObjectName('subtle')
        layout.addWidget(self.advanced_toggle)
        self.advanced=QWidget();self.advanced.setObjectName('advanced');advanced=QVBoxLayout(self.advanced)
        layout.addWidget(self.advanced);self.advanced.hide()
        layout.addStretch(1)
        row=QHBoxLayout()
        self.windows=QComboBox();row.addWidget(self.windows)
        row.addWidget(button('刷新窗口',self.refresh_windows))
        row.addWidget(button('绑定',self.bind_window));advanced.addLayout(row)
        self.automatic=QCheckBox('阶段触发（试用；每 3 秒检查顶部回合，仅 MuMu 前台）')
        self.automatic.toggled.connect(self.automatic_changed);advanced.addWidget(self.automatic)
        row=QHBoxLayout();row.addWidget(QLabel('统计版本'));row.addWidget(self.patch)
        row.addWidget(button('应用版本',self.change_patch));advanced.addLayout(row)
        row=QHBoxLayout()
        row.addWidget(button('读取本地截图',self.open_image))
        row.addWidget(button('收起并识别一次',self.capture_once))
        row.addWidget(button('更新目录',self.load_catalog));advanced.addLayout(row)
        self.stage=QComboBox();self.stage.addItems(['2-1','3-2','4-2'])
        self.stage.currentIndexChanged.connect(self.clear_choice_result)
        advanced.addWidget(self.stage)
        self.picks=[]
        for _ in range(3):
            combo=QComboBox();combo.setEditable(True);combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            combo.currentIndexChanged.connect(self.clear_choice_result)
            combo.editTextChanged.connect(self.clear_choice_result)
            self.picks.append(combo);advanced.addWidget(combo)
        advanced.addWidget(QLabel('同名条目保留品质与 ID 供纠错；手动查询仅在面板显示。'))
        advanced.addWidget(button('查询手动选择的海克斯',self.manual_stats))
        self.add_page(page,'海克斯')

    def toggle_advanced(self):
        opened=self.advanced.isHidden()
        self.advanced.setVisible(opened)
        self.advanced_toggle.setText('收起高级设置 ▾' if opened else '手动查询与高级设置 ▸')

    def set_activity(self,code,message):
        self.activity.setText(message)
        self.mark.button.setToolTip(message+'\n点击展开 / 收起 · Ctrl+Alt+F10 查均排')
        if self.activity_code==code:return
        self.activity_code=code
        if not self.offline:record('state',code=code,automatic=self.automatic.isChecked(),bound=self.binding is not None)
        # Local status only: no screenshot, OCR text, credentials or game controls.
        payload={'time':datetime.now().isoformat(timespec='seconds'),'state':code,'message':message,
                 'automatic':self.automatic.isChecked(),'bound':self.binding is not None}
        try:(STATE_DIR/('offline-status.json' if self.offline else 'assistant-status.json')).write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
        except OSError:pass

    def start_or_pause(self):
        if self.automatic.isChecked():
            self.automatic.setChecked(False)
            self.set_activity('paused','辅助已暂停');return
        if not self.catalog:
            self.set_activity('catalog_missing','数据尚未准备好，正在重新加载…');self.load_catalog();return
        self.refresh_windows()
        bound_valid=self.binding is not None and win.same_target(self.binding,win.describe(self.binding.hwnd))
        if self.windows.count()!=1 and not bound_valid:
            if self.windows.count()==0:self.set_activity('no_game','没有找到 MuMu。打开游戏后，再点击主按钮。')
            else:
                self.advanced.show()
                self.set_activity('multiple_games','发现多个 MuMu 窗口，请在下方选择要辅助的游戏。')
            return
        if not bound_valid:self.bind_window()
        if self.binding is None:
            self.set_activity('no_game','游戏窗口已变化，请再次点击主按钮。');return
        if self.trigger_mode.currentIndex()==0:
            self.capture_once();return
        self.automatic.setChecked(True)
        self.set_activity('waiting_choice','已连接 MuMu，等待海克斯选择。')
        self.return_to_game()

    def trigger_mode_changed(self,*_):
        self.automatic.setChecked(False);self.invalidate()
        self.stage_window_until=0;self.last_probe_stage=None
        self.start_button.setText('截图查均排' if self.trigger_mode.currentIndex()==0 else '开启阶段触发')

    def make_explorer(self):
        page=QWidget();layout=QVBoxLayout(page);columns=QHBoxLayout();columns.setSpacing(18)
        filters=QWidget();filters.setFixedWidth(225);filter_layout=QVBoxLayout(filters)
        filter_layout.setContentsMargins(0,0,0,0);filter_layout.setSpacing(10)
        filter_layout.addWidget(label('选择查询条件','section'))
        self.kind=QComboBox()
        for kind_label,kind in [('海克斯','hex'),('装备 / 转职','equip'),('英雄','hero'),('羁绊档位','trait')]:self.kind.addItem(kind_label,kind)
        self.search=QLineEdit();self.search.setPlaceholderText('输入名称搜索…')
        self.search.textChanged.connect(self.filter_entities);self.kind.currentIndexChanged.connect(self.filter_entities)
        filter_layout.addWidget(self.kind);filter_layout.addWidget(self.search)
        self.entities=QListWidget();self.entities.setMinimumHeight(130);filter_layout.addWidget(self.entities,1)
        query=button('查询这个条件',self.explore_selected);query.setObjectName('primary');filter_layout.addWidget(query)
        self.resources=QListWidget();self.resources.setFixedHeight(66)
        self.resources.itemDoubleClicked.connect(self.explore_resource)
        filter_layout.addWidget(label('最近使用 · 双击再次查询','muted'));filter_layout.addWidget(self.resources)
        remove=button('移除选中记录',lambda:self.resources.takeItem(self.resources.currentRow()));remove.setObjectName('subtle');filter_layout.addWidget(remove)
        columns.addWidget(filters)
        results=QWidget();result_layout=QVBoxLayout(results);result_layout.setContentsMargins(0,0,0,0);result_layout.setSpacing(12)
        result_layout.addWidget(label('匹配阵容','section'))
        self.explore_note=label('选择一个条件，查看它适合的阵容。','muted');result_layout.addWidget(self.explore_note)
        self.explore_table=table(['阵容','条件内均排','样本','阵容 ID'])
        self.explore_table.cellDoubleClicked.connect(self.browse_result)
        self.explore_table.setMinimumHeight(270);result_layout.addWidget(self.explore_table,1)
        result_layout.addWidget(label('双击阵容打开攻略，再决定是否固定。','muted'))
        row=QHBoxLayout();row.addWidget(button('清空条件',self.clear_explorer))
        row.addWidget(button('原站检索器  ↗',lambda:self.open_guide('https://www.dataj.cc/explorer')));result_layout.addLayout(row)
        columns.addWidget(results,1);layout.addLayout(columns)
        self.explore_table.hideColumn(3)
        self.add_page(page,'单条件检索')

    def make_guide(self):
        page=QWidget();layout=QVBoxLayout(page)
        row=QHBoxLayout();self.comp_url=QLineEdit();self.comp_url.setPlaceholderText('https://www.dataj.cc/comp/112')
        row.addWidget(self.comp_url);row.addWidget(button('浏览攻略',self.browse_comp));layout.addLayout(row)
        row=QHBoxLayout();row.addWidget(button('本局玩这个阵容',self.pin_comp));row.addWidget(button('取消定阵',self.unpin));row.addWidget(button('复制主阵容码',self.copy_code));layout.addLayout(row)
        self.profile=QWebEngineProfile(self)
        self.profile.downloadRequested.connect(lambda item:item.cancel())
        self.web=QWebEngineView()
        self.guide_page=GuidePage(self.profile,self.web)
        self.guide_page.featurePermissionRequested.connect(lambda origin,feature:self.guide_page.setFeaturePermission(origin,feature,QWebEnginePage.PermissionPolicy.PermissionDeniedByUser))
        self.web.setPage(self.guide_page);self.guide_page.setBackgroundColor(QColor('#191922'))
        self.guide_empty=QFrame();self.guide_empty.setObjectName('hero');empty=QVBoxLayout(self.guide_empty)
        empty.setContentsMargins(30,40,30,40);empty.addWidget(label('先找到这局的方向','pageTitle'))
        empty.addWidget(label('在条件选阵中打开一套阵容，或在上方粘贴 DataJ 阵容地址。\n点击「本局玩这个阵容」后，强化和出装统计会跟随它。','muted'))
        empty.addSpacing(16);empty.addWidget(button('去条件选阵  →',lambda:self.tabs.setCurrentIndex(1)))
        layout.addWidget(self.guide_empty)
        self.web.setMinimumHeight(320);layout.addWidget(self.web);self.web.hide()
        self.web.urlChanged.connect(self.guide_url_changed)
        layout.addWidget(label('浏览不会自动更换本局阵容。变体阵容码请在原站复制。','muted'))
        self.add_page(page,'阵容攻略')

    def make_equipment(self):
        page=QWidget();layout=QVBoxLayout(page);row=QHBoxLayout()
        self.heroes=QComboBox();row.addWidget(self.heroes)
        self.equip_form=QComboBox();self.equip_form.addItems(['单件','三件套']);row.addWidget(self.equip_form)
        self.equip_type=QComboBox();self.equip_type.addItems(['全部','成型装备','神器装备','光明武器','转职纹章','特殊装备']);row.addWidget(self.equip_type)
        row.addWidget(button('查询出装',self.query_equipment));layout.addLayout(row)
        self.equip_table=table(['装备（所选英雄在已固定阵容中）','平均排名','样本'])
        layout.addWidget(self.equip_table)
        self.equip_note=label('先在「阵容攻略」中固定阵容，再选择要查询的英雄。','muted');layout.addWidget(self.equip_note)
        self.equip_form.currentIndexChanged.connect(self.clear_equipment)
        self.equip_type.currentIndexChanged.connect(self.clear_equipment)
        self.heroes.currentIndexChanged.connect(self.clear_equipment)
        self.add_page(page,'阵容出装')

    def load_catalog(self):
        adapter=self.adapter
        def failed(_):
            if adapter is not self.adapter:return
            self.start_button.setEnabled(True)
            self.set_activity('catalog_failed','数据准备失败。检查网络后点击主按钮重试。')
        self.submit(self.network,adapter.catalog,lambda r:self.catalog_loaded(r) if adapter is self.adapter else None,failed)

    def catalog_loaded(self,result,offline=False):
        self.catalog=result['data']
        self.invalidate()
        for combo in self.picks:
            combo.blockSignals(True);combo.clear();combo.addItem('未识别 / 请手动选择',None)
            for row in self.catalog['hex']:
                combo.addItem(f"{row['name']} · 品质{row.get('level','?')} · ID {row['id']}",str(row['id']))
                combo.setItemData(combo.count()-1,row.get('descText',''),Qt.ItemDataRole.ToolTipRole)
            combo.blockSignals(False)
            combo.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.filter_entities()
        self.start_button.setEnabled(True)
        self.set_activity('ready','按所选鼠标侧键或 Ctrl+Alt+F10 查均排，空闲时不截图。')
        self.status.setText('离线演示已准备好。' if offline else '目录已准备好，正在后台预热识别与统计；首次查询可能稍慢。')
        if not offline:
            self.submit(self.ocr_pool,self.vision.prepare,lambda _:None)
            self.submit(self.network,self.adapter.hexes,lambda _:None)

    def change_patch(self):
        try:adapter=DataJ(patch=self.patch.text().strip())
        except ValueError as exc:self.status.setText(str(exc));return
        self.adapter=adapter;self.session.patch=adapter.patch;self.catalog={}
        self.new_game();self.clear_explorer();self.load_catalog()
        self.status.setText(f'当前统计版本 {adapter.patch}，请与游戏版本保持一致。')

    def refresh_windows(self):
        if not hasattr(self,'windows'):return
        self.windows.clear()
        for item in game_windows():
            self.windows.addItem(f'{item.title} · {item.rect[2]-item.rect[0]}×{item.rect[3]-item.rect[1]}',item)

    def bind_window(self):
        item=self.windows.currentData()
        if item and win.same_target(item,win.describe(item.hwnd)):
            self.binding=item;self.geometry=(item.rect,item.dpi);self.invalidate();self.status.setText('已绑定 MuMu。默认按 Ctrl+Alt+F10 查询；也可选择阶段触发。')
        else:self.status.setText('没有有效 MuMu 游戏窗口')

    def hide_overlays(self):
        for label in self.overlays:label.hide()

    def invalidate(self):
        self.stats_inflight_token=None
        self.session.invalidate();self.signature=None;self.stable=0;self.stats_payload=None;self.last_observation=None
        self.once_active=False
        self.once_ocr_pending=False
        self.was_available=False
        self.hide_overlays()
        if hasattr(self,'choice_table'):self.choice_table.setRowCount(0)
        if hasattr(self,'choice_table'):self.choice_table.hide()
        for card in getattr(self,'result_cards',[]):card.clear(self.session.target is not None)
        if getattr(self,'activity_code',None) in ('results','partial_results','no_stage_data'):
            self.set_activity('waiting_choice' if self.automatic.isChecked() else 'ready',
                              '等待新的海克斯选择。' if self.automatic.isChecked() else '按所选鼠标侧键或 Ctrl+Alt+F10 查均排，空闲时不截图。')
            self.choice_note.setText('候选已清空，等待下一次识别。')

    def clear_choice_result(self,*_):
        self.invalidate()

    def automatic_changed(self,*_):
        self.invalidate()
        self.start_button.setText('暂停阶段触发' if self.automatic.isChecked() else ('截图查均排' if self.trigger_mode.currentIndex()==0 else '开启阶段触发'))

    def new_game(self):
        self.last_probe_stage=None;self.stage_window_until=0
        self.session.reset();self.comp_detail=None;self.heroes.clear();self.unpin()
        self.resources.clear();self.clear_explorer()

    def return_to_game(self):
        self.invalidate()
        if self.binding and win.same_target(self.binding,win.describe(self.binding.hwnd)):
            switched=win.user.SetForegroundWindow(self.binding.hwnd)
            if not switched and win.foreground_root()!=self.binding.hwnd:
                self.automatic.setChecked(False)
                self.set_activity('return_failed','Windows 未允许切回游戏。请先确认 MuMu 可正常打开，再点击主按钮。')
                self.showNormal()
                return False
        if self.reopen_shortcut_available or not self.offline:self.hide()
        else:self.showMinimized()
        return True

    def toggle(self):
        if self.panel_open():self.return_to_game()
        else:self.invalidate();self.showNormal();self.raise_();self.activateWindow()

    def panel_open(self):
        return self.isVisible() and not self.isMinimized()

    def closeEvent(self,event):
        self.timer.stop();self.hide_overlays()
        event.accept()
        QApplication.instance().quit()

    def open_image(self):
        path,_=QFileDialog.getOpenFileName(self,'读取截图','','图片 (*.png *.jpg *.jpeg)')
        if path:
            from PIL import Image
            self.invalidate()
            with Image.open(path) as opened:image=opened.convert('RGB')
            self.analyze(image,False)

    def save_mouse_button(self):
        if not self.offline:
            self.mouse_settings.setValue('mouse_button',self.mouse_button.currentData())
            self.mouse_settings.sync()

    def mouse_capture(self,button,foreground):
        if button!=self.mouse_button.currentData() or not foreground:return
        if self.capture_pending or self.ocr_busy:return
        now=time.monotonic()
        if now-self.last_mouse_trigger<0.7:return
        # Validate foreground both at release time and when queued work is handled.
        if win.foreground_root()!=foreground:return
        targets=game_windows()
        target=next((item for item in targets if item.hwnd==foreground),None)
        if target is None:return
        valid_binding=self.binding and win.same_target(self.binding,win.describe(self.binding.hwnd))
        if valid_binding and not win.same_target(self.binding,target):return
        if not valid_binding and len(targets)!=1:return
        self.last_mouse_trigger=now
        self.capture_once()

    def capture_once(self):
        if not self.catalog:
            self.set_activity('catalog_missing','数据正在准备，请稍后再按截图快捷键。');return
        if not self.binding or not win.same_target(self.binding,win.describe(self.binding.hwnd)):
            self.refresh_windows()
            if self.windows.count()!=1:
                self.set_activity('no_game','没有找到唯一的 MuMu 游戏窗口，请在面板选择窗口。');return
            self.bind_window()
        if not self.binding:return
        if self.return_to_game() is False:return
        self.once_active=True;self.once_deadline=time.monotonic()+30
        self.once_ocr_pending=True
        QTimer.singleShot(100,lambda:self.request_capture())

    def request_capture(self,once=False):
        if self.capture_pending or not self.binding:return
        self.capture_pending=True
        binding=self.binding;token=self.session.token()
        def done(result):
            self.capture_pending=False
            if self.session.accepts(token):self.captured(result,once)
        def failed(message):
            self.capture_pending=False
            if self.session.accepts(token):self.capture_failed(message)
        def begin():
            self.submit(self.capture_pool,lambda:capture_image(binding),done,failed)
        # Rank windows sit at the tier badges, outside title/round OCR regions.
        # Keep them visible during capture; changed inputs still invalidate results.
        begin()

    def capture_failed(self,message):
        if not self.offline:record('capture_failed')
        self.capture_pending=False;self.invalidate()
        self.set_activity('capture_failed','暂时无法读取游戏画面。请保持 MuMu 在前台；助手会继续尝试。')

    def captured(self,result,once):
        self.capture_pending=False;self.last_capture=time.monotonic()
        image,binding=result
        if not self.offline:record('captured',width=image.width,height=image.height)
        if not self.binding or not win.same_target(self.binding,binding) or self.panel_open():return
        if self.last_observation:
            signature=tracked_signature(image,self.last_observation)
            if not unchanged(signature,self.signature):self.invalidate()
        self.last_frame=image
        if once:self.once_ocr_pending=True
        if self.once_ocr_pending and not self.ocr_busy and self.catalog:
            self.once_ocr_pending=False
            self.analyze(image,True)
        elif (self.automatic.isChecked() and time.monotonic()>=self.next_ocr_allowed
              and time.monotonic()-self.last_ocr>2
              and not (self.last_observation and (self.stats_payload or self.stats_inflight_token==self.session.token()))):
            self.analyze(image,True)
        if self.stats_payload and self.last_observation:
            self.display_overlays()

    def analyze(self,image,live):
        if self.ocr_busy or not self.catalog:return
        self.ocr_busy=True;self.ocr_live=live;self.last_ocr=time.monotonic()
        token=self.session.token();catalog=self.catalog['hex']
        def done(obs):
            self.ocr_busy=False
            self.next_ocr_allowed=time.monotonic()+1.5
            if not self.offline:record('ocr_complete',scene=obs.get('scene'),reason=obs.get('reason'),diagnostic_frame=obs.get('diagnostic_frame'),stage=obs.get('round'),elapsed_ms=obs.get('elapsed_ms'),resolutions=[c.get('resolution',{}).get('status') for c in obs.get('cards',[])],session_valid=self.session.accepts(token))
            if not self.session.accepts(token):return
            if live and (self.panel_open() or not self.binding or win.foreground_root()!=self.binding.hwnd):return
            if live and obs.get('scene')=='choice_candidates' and (self.last_frame is None or not unchanged(tracked_signature(image,obs),tracked_signature(self.last_frame,obs))):
                self.invalidate();self.set_activity('frame_changed','选择画面发生变化，正在重新识别…');return
            if live:self.signature=tracked_signature(self.last_frame,obs)
            self.observed(obs,live)
        def failed(_):
            self.ocr_busy=False
            self.next_ocr_allowed=time.monotonic()+2
            if not self.offline:record('ocr_failed')
            if self.session.accepts(token):self.set_activity('ocr_failed','识别未成功，助手会继续尝试。也可以稍后用截图排查。')
        def recognize():
            observation=self.vision.analyze_fast(image,catalog) if live else self.vision.analyze(image,catalog)
            if live and not self.offline and self.save_diagnostic_frames:
                observation['diagnostic_frame']=self.frame_recorder.save(image,observation)
            return observation
        self.submit(self.ocr_pool,recognize,done,failed)

    def observed(self,obs,live):
        self.last_observation=obs
        for pick in self.picks:
            pick.blockSignals(True);pick.setCurrentIndex(0);pick.blockSignals(False)
        if obs.get('scene')!='choice_candidates' or obs.get('round') not in STAGES:
            self.invalidate();self.choice_note.setText('尚未确认海克斯选择与回合，不显示旧均排。')
            self.set_activity('round_unknown' if obs.get('scene')=='choice_candidates' else 'waiting_choice',
                              '看到了海克斯，但回合暂未识别，正在重试。' if obs.get('scene')=='choice_candidates' else '已连接 MuMu，等待海克斯选择。' if live else '这张图片暂未识别为海克斯选择页。')
            return
        self.stage.blockSignals(True);self.stage.setCurrentText(obs['round']);self.stage.blockSignals(False)
        ids=[];names=[]
        for pick,card in zip(self.picks,obs['cards']):
            resolved=card['resolution'];entity=resolved.get('id')
            ids.append(entity);names.append(resolved.get('name',card['raw_text'])+('（待纠正）' if entity is None else ''))
            pick.blockSignals(True);pick.setCurrentIndex(max(0,pick.findData(entity or resolved.get('suggested_id'))));pick.blockSignals(False)
        self.choice_note.setText(f"{'MuMu' if live else '文件回放（赛季由用户确认，不用于实时浮层）'} · OCR {obs['elapsed_ms']} ms")
        self.query_stats(ids,names,live)

    def manual_stats(self):
        ids=[p.currentData() if p.currentText()==p.itemText(p.currentIndex()) else None for p in self.picks]
        names=[p.currentText().split(' · ')[0] for p in self.picks]
        self.query_stats(ids,names,False)

    def query_stats(self,ids,names,live):
        same_choices=self.session.stage==self.stage.currentText() and self.session.choices==tuple(ids)
        if live and same_choices:
            if self.stats_inflight_token==self.session.token():return
            if self.stats_payload and self.stats_payload['live'] and self.session.accepts(self.stats_payload['token']):
                self.display_overlays();return
        self.session.set_choices(self.stage.currentText(),ids)
        self.set_activity('querying','正在获取海克斯均排…')
        self.hide_overlays();self.choice_table.setRowCount(0)
        for card in self.result_cards:card.clear(self.session.target is not None)
        token=self.session.token();stage=self.session.stage;target=self.session.target;adapter=self.adapter
        self.stats_inflight_token=token
        def fetch():
            global_result=adapter.hexes()
            return global_result,None
        def done(payload,comp_finished=False):
            if self.stats_inflight_token==token:self.stats_inflight_token=None
            if not self.session.accepts(token):return
            if live and (self.panel_open() or not self.binding or win.foreground_root()!=self.binding.hwnd):return
            global_result,comp_result=payload
            rendered=[];available=0
            for entity,name in zip(ids,names):
                global_stat=stage_stat(global_result['data'],entity,stage)
                comp_stat=stage_stat(comp_result['data'],entity,stage) if comp_result else None
                available+=global_stat['status']=='ok' or (comp_stat is not None and comp_stat['status']=='ok')
                comp_text=stat_text(comp_stat) if comp_stat else ('阵容数据暂不可用' if comp_finished else '阵容数据读取中…') if target else '未固定阵容'
                rendered.append([name,stat_text(global_stat),comp_text])
            self.stats_payload={'rows':rendered,'live':live,'created':time.monotonic(),'token':token}
            if not self.offline:record('stats_ready',available=available,live=live)
            fill_table(self.choice_table,rendered)
            for card,row in zip(self.result_cards,rendered):card.update_result(row)
            stamp=datetime.fromtimestamp(global_result['fetched_at']).strftime('%m-%d %H:%M')
            self.choice_note.setText(f'S18 · {adapter.patch} · {stage} · 全局数据获取 {stamp}；全局与阵容分别统计')
            count=sum(entity is not None for entity in ids)
            if available==0:self.set_activity('no_stage_data',f'已确认 {count}/3 个海克斯，但来源暂无对应阶段的均排。')
            else:self.set_activity('results' if count==3 else 'partial_results',
                                  (f'已有 {available} 个选项的均排，返回游戏即可查看。' if live else f'已显示 {available} 个选项的均排，仅在面板查看。') if count==3 else f'已确认 {count}/3 个海克斯；不确定的选项不会猜测。')
            if live:self.display_overlays()
            if target and not comp_finished:
                self.submit(self.network,lambda:(global_result,adapter.hexes(target)),
                            lambda value:done(value,True),lambda _:done((global_result,None),True))
        def failed(_):
            if self.stats_inflight_token==token:self.stats_inflight_token=None
            if self.session.accepts(token):
                self.hide_overlays();self.set_activity('stats_failed','暂时取不到均排，请按正常节奏选择。助手稍后会重试。')
        self.submit(self.network,fetch,done,failed)

    def display_overlays(self):
        payload=self.stats_payload
        reason=('no_live_result' if not payload or not payload['live'] else
                'stale_session' if not self.session.accepts(payload['token']) else
                'panel_open' if self.panel_open() else 'capture_pending' if self.capture_pending else
                'not_foreground' if not self.binding or win.foreground_root()!=self.binding.hwnd else
                'stale_capture' if time.monotonic()-self.last_capture>1.5 else 'shown')
        if not self.offline and reason!=self.last_overlay_diagnostic:
            record('overlay',state=reason);self.last_overlay_diagnostic=reason
        if reason!='shown':return
        for label,card,row in zip(self.overlays,self.last_observation['cards'],payload['rows']):
            def colored(value):
                head=value.split(' · ')[0]
                try:color=placement_color(float(head))
                except ValueError:color='#a7a1b5'
                return f'<span style="color:{color}">{html.escape(value)}</span>'
            label.place(self.binding,card['box'],f"{self.session.stage} · {html.escape(row[0])}<br>全局 {colored(row[1])}<br>阵容 {colored(row[2])}")

    def probe_stage(self):
        if self.stage_probe_pending or self.ocr_busy:return
        self.stage_probe_pending=True;self.last_stage_probe=time.monotonic()
        token=self.session.token();binding=self.binding
        def done(stage):
            self.stage_probe_pending=False
            if not self.session.accepts(token) or not self.automatic.isChecked():return
            if stage and stage!=self.last_probe_stage:
                self.invalidate()
                self.stage_window_until=time.monotonic()+60 if stage in STAGES else 0
                self.last_probe_stage=stage
                if stage in STAGES:self.once_ocr_pending=True
        def failed(_):self.stage_probe_pending=False
        self.submit(self.ocr_pool,lambda:self.vision.read_round_crop(capture_stage(binding)),done,failed)

    def tick(self):
        if not self.automatic.isChecked() and not self.once_active and not self.stats_payload:return
        current=win.describe(self.binding.hwnd) if self.binding else None
        reason=win.capture_block_reason(self.binding,current,win.foreground_root()) if self.binding else 'no_binding'
        if self.panel_open() or reason:
            self.hide_overlays()
            if self.was_available or self.signature is not None or (self.ocr_busy and self.ocr_live) or self.once_active:self.invalidate()
            self.was_available=False
            if self.automatic.isChecked() and not self.panel_open():
                if reason=='target_changed_or_closed':
                    self.automatic.setChecked(False)
                    self.set_activity('game_closed','游戏窗口已关闭或变化。重新打开游戏后点击主按钮。')
                elif reason:self.set_activity('waiting_foreground','已暂停识别；回到 MuMu 后会自动继续。')
            return
        self.was_available=True
        if self.once_active and time.monotonic()>self.once_deadline:
            self.once_active=False
            if not self.automatic.isChecked():self.invalidate()
        geometry=(current.rect,current.dpi)
        if geometry!=self.geometry:self.invalidate();self.geometry=geometry;self.binding=current
        if time.monotonic()-self.last_capture>1.5:self.hide_overlays()
        capture_interval=.5 if self.last_observation else 1.0
        if self.automatic.isChecked() and not self.offline and time.monotonic()-self.last_stage_probe>=3:self.probe_stage()
        stage_active=self.automatic.isChecked() and (self.offline or time.monotonic()<self.stage_window_until)
        if (stage_active or self.once_active) and time.monotonic()-self.last_capture>capture_interval:
            self.request_capture()

    def filter_entities(self,*_):
        if not hasattr(self,'entities'):return
        self.entities.clear();kind=self.kind.currentData();query=self.search.text().strip()
        names={}
        for entity in self.catalog.get(kind,[]):
            key=(entity['name'],entity.get('level'),entity.get('num') if kind=='trait' else None)
            names[key]=names.get(key,0)+1
        for entity in self.catalog.get(kind,[]):
            if kind=='hero' and (entity.get('heroType')!=0 or float(entity.get('price') or 0)<=0):continue
            label=(str(entity.get('num','')) if kind=='trait' else '')+entity['name']
            if query and query not in label:continue
            quality={1:'银色',2:'金色',3:'彩色'}.get(entity.get('level'),'') if kind=='hex' else ''
            key=(entity['name'],entity.get('level'),entity.get('num') if kind=='trait' else None)
            disambiguation=f" · 来源编号 {entity['id']}" if names[key]>1 else ''
            item=QListWidgetItem(label+(f'   ·   {quality}' if quality else '')+disambiguation)
            item.setData(Qt.ItemDataRole.UserRole,(kind,entity));item.setToolTip(str(entity.get('descText') or ''))
            self.entities.addItem(item)

    def explore_selected(self):
        item=self.entities.currentItem()
        if item:self.run_explore(*item.data(Qt.ItemDataRole.UserRole))

    def explore_resource(self,item):
        self.run_explore(*item.data(Qt.ItemDataRole.UserRole))

    def clear_explorer(self):
        self.explorer_generation+=1;self.explore_table.setRowCount(0);self.explore_note.setText('未选择条件')

    def run_explore(self,kind,entity):
        self.clear_explorer();generation=self.explorer_generation;adapter=self.adapter
        self.explore_note.setText('本次仅使用：'+entity['name']+'（查询中）')
        key=(kind,str(entity['id']))
        if not any(self.resources.item(i).data(Qt.ItemDataRole.UserRole)[0]==kind and str(self.resources.item(i).data(Qt.ItemDataRole.UserRole)[1]['id'])==key[1] for i in range(self.resources.count())):
            item=QListWidgetItem(entity['name']);item.setData(Qt.ItemDataRole.UserRole,(kind,entity));self.resources.addItem(item)
        def done(result):
            if generation!=self.explorer_generation or adapter is not self.adapter:return
            rows=result['data'].get('comps')
            if not isinstance(rows,list):self.status.setText('检索结果结构变化');return
            rows=sorted(rows,key=lambda r:r.get('avgPlacement') if isinstance(r.get('avgPlacement'),(int,float)) else 99)
            fill_table(self.explore_table,[[r.get('name','—'),r.get('avgPlacement','—'),r.get('sampleCount','—'),r.get('compId','')] for r in rows])
            self.explore_note.setText(f"仅条件 {entity['name']} · {adapter.patch} · {len(rows)} 个阵容；均排属于该条件内")
        def failed(_):
            if generation==self.explorer_generation:self.explore_note.setText('查询未完成，请稍后重试。')
        self.submit(self.network,lambda:adapter.explore(kind,entity),done,failed)

    def browse_result(self,row,col):
        item=self.explore_table.item(row,3)
        if item:self.comp_url.setText('https://www.dataj.cc/comp/'+item.text());self.browse_comp()

    def browse_comp(self):
        try:parse_comp_url(self.comp_url.text())
        except ValueError as exc:self.status.setText(str(exc));return
        self.open_guide(self.comp_url.text())

    def open_guide(self,url):
        self.guide_empty.hide();self.web.show()
        self.web.setUrl(QUrl(url));self.tabs.setCurrentIndex(2)

    def guide_url_changed(self,url):
        try:parse_comp_url(url.toString())
        except ValueError:return
        self.comp_url.setText(url.toString())

    def pin_comp(self):
        try:comp=parse_comp_url(self.comp_url.text())
        except ValueError as exc:self.status.setText(str(exc));return
        self.session.set_target(comp);self.invalidate();self.clear_equipment();self.comp_detail=None;self.heroes.clear()
        self.comp_generation+=1;generation=self.comp_generation;adapter=self.adapter
        session_id=self.session.session_id
        self.target_label.setText('本局阵容：正在读取 '+comp)
        def done(result):
            if generation!=self.comp_generation or session_id!=self.session.session_id or adapter is not self.adapter:return
            detail=result['data']
            if not isinstance(detail,dict) or str(detail.get('compId'))!=comp:self.status.setText('阵容详情不一致');return
            self.comp_detail=detail;self.target_label.setText('本局阵容：'+detail.get('name',comp))
            for hero in detail.get('heroes',[]):self.heroes.addItem(hero['heroName'],str(hero['heroId']))
        self.submit(self.network,lambda:adapter.comp(comp),done)

    def unpin(self):
        self.comp_generation+=1
        self.session.set_target(None);self.invalidate();self.comp_detail=None;self.target_label.setText('本局阵容：未固定')
        self.heroes.clear();self.clear_equipment()

    def copy_code(self):
        code=self.comp_detail.get('gameCode') if self.comp_detail else None
        if isinstance(code,str) and code.startswith('【阵容码】'):
            QApplication.clipboard().setText(code);self.status.setText('已复制固定阵容的主阵容码；未声明对应网页中正在浏览的变体')
        else:self.status.setText('请先固定一个提供阵容码的阵容')

    def clear_equipment(self,*_):
        self.equip_generation+=1
        if hasattr(self,'equip_table'):self.equip_table.setRowCount(0)

    def query_equipment(self):
        comp=self.session.target;hero=self.heroes.currentData()
        if not comp or not hero:self.status.setText('请先固定阵容并选择英雄');return
        self.clear_equipment();generation=self.equip_generation;adapter=self.adapter
        form=self.equip_form.currentText();kind=self.equip_type.currentText()
        hero_name=self.heroes.currentText();catalog={str(x['id']):x for x in self.catalog.get('equip',[])}
        def done(result):
            if generation!=self.equip_generation or adapter is not self.adapter:return
            data=result['data']
            if str(data.get('compId'))!=comp or str(data.get('heroId'))!=hero:self.status.setText('出装响应对象不匹配');return
            rows=data.get('heroEquips' if form=='单件' else 'hero3Equips',[])
            selected=[]
            for row in rows:
                equips=row.get('equips',[])
                if kind!='全部' and not any(catalog.get(str(e['id']),{}).get('type')==kind for e in equips):continue
                selected.append(['/'.join(e['name'] for e in equips),row.get('avgPlacement','—'),row.get('sampleCount','—')])
            selected.sort(key=lambda r:r[1] if isinstance(r[1],(int,float)) else 99)
            fill_table(self.equip_table,selected)
            self.equip_note.setText(f'{self.target_label.text()} · {hero_name} · {form} · {kind}（三件套按包含筛选） · {adapter.patch}')
        self.submit(self.network,lambda:adapter.equipment(comp,hero),done)

    def shutdown(self):
        self.timer.stop();self.hide_overlays();self.mark.hide()
        for pool in (self.capture_pool,self.ocr_pool,self.network):pool.clear();pool.waitForDone()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--self-test',action='store_true');parser.add_argument('--seconds',type=int,default=0)
    args=parser.parse_args()
    win.enable_dpi()
    app=QApplication(sys.argv[:1]);app.setQuitOnLastWindowClosed(False)
    panel=Companion(offline=args.self_test)
    registered=[]
    mouse=MouseShortcut(panel)
    mouse.released.connect(panel.mouse_capture,Qt.ConnectionType.QueuedConnection)
    class Hotkeys(QAbstractNativeEventFilter):
        def nativeEventFilter(self,event_type,message):
            msg=w.MSG.from_address(int(message))
            if msg.message==0x312:
                action={51:panel.toggle,52:panel.capture_once,53:app.quit}.get(int(msg.wParam))
                if action:action();return True,0
            return False,0
    native=Hotkeys();app.installNativeEventFilter(native)
    if not args.self_test:
        for id_,key in ((51,0x78),(52,0x79),(53,0x7B)):
            if win.user.RegisterHotKey(None,id_,0x4003,key):registered.append(id_)
        panel.reopen_shortcut_available=51 in registered
        if not panel.reopen_shortcut_available:panel.status.setText('展开快捷键被占用。收起后，可点击左上角「铲」标记重新打开。')
        elif len(registered)!=3:panel.status.setText('部分快捷键被占用，可以使用面板按钮。')
        if not mouse.start():panel.status.setText('鼠标侧键监听不可用，请用截图按钮或 Ctrl+Alt+F10。')
        panel.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,True)
        area=app.primaryScreen().availableGeometry()
        panel.move(area.left()+64,area.top()+12);panel.mark.move(area.left()+12,area.top()+12)
        panel.mark.show();panel.show()
    else:
        assert len(panel.catalog['hex'])==263
        assert panel.picks[0].count()==264
        panel.resize(1080,760);panel.grab();app.processEvents()
        panel.grab().save(str(STATE_DIR/'ui-self-test.png'))
        print(json.dumps({'self_test':'widgets and offline catalog passed','catalog_rows':263,'screen_saved':str(STATE_DIR/'ui-self-test.png')}),flush=True)
        QTimer.singleShot(200,app.quit)
    if args.seconds:QTimer.singleShot(args.seconds*1000,app.quit)
    def cleanup():
        mouse.stop()
        for key in registered:win.user.UnregisterHotKey(None,key)
        panel.shutdown()
    app.aboutToQuit.connect(cleanup)
    return app.exec()


if __name__=='__main__':raise SystemExit(main())
