"""Local alpha: stage stats, conservative OCR, single-filter queries and pinned guide."""
from __future__ import annotations
import argparse
import ctypes as c
from ctypes import wintypes as w
from datetime import datetime
import json
import os
import html
import re
import sys
import time
from pathlib import Path

from bootstrap import ROOT, STATE_DIR, RESOURCE_DIR
import win_capture as win
from core import Session, parse_comp_url
from dataj import DataJ, COMP_MIN_SAMPLE
from snapshot_stats import stage_stat, STAGES
from vision import Vision, capture_image, capture_stage, tracked_signature, unchanged
from scene_gate import may_be_choice
from floating_mark import FloatingMark
from comp_browser import CompBrowser,HeroPortrait,portrait_catalog
from mouse_shortcut import MouseShortcut
from stat_colors import placement_color
from ui_theme import STYLE, ResultCard, Rune, label
from diagnostics import record, FrameRecorder
from item_controller import ItemController, inspect_items
from entity_identity import EntityResolver
from selected_resources import SelectedResources, SelectionEntity
from selection_controller import SelectionController
from condition_controller import ConditionController
from PySide6.QtCore import Qt, QTimer, QObject, Signal, QRunnable, QThreadPool, QUrl, QAbstractNativeEventFilter, QSettings
from PySide6.QtGui import QDesktopServices,QColor
from PySide6.QtWidgets import (QApplication, QWidget, QLabel, QPushButton, QComboBox, QLineEdit,
    QVBoxLayout, QHBoxLayout, QTabWidget, QTableWidget, QTableWidgetItem, QListWidget,
    QListWidgetItem, QCheckBox, QFileDialog, QHeaderView, QAbstractItemView,QFrame,QScrollArea,QButtonGroup,QSizeGrip)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile,QWebEngineSettings


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
        finally:
            self.fn=None


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
                    item.setForeground(QColor(*map(int,re.findall(r'\d+',placement_color(average)))))
                    if isinstance(value,(int,float)):item.setText(f'{average:.2f}')
                except ValueError:pass
            if col>0:item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            widget.setItem(row,col,item)


def stat_text(row):
    if row['status']=='ok':
        return f"{row['avg_placement']:.2f} · {row['sample_count']}局"+(' · 少' if row['sample_count']<50 else '')
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
        was_visible=self.isVisible()
        if self.text()!=text:
            self.setText(text)
            self.adjustSize()
        if not was_visible:self.show()
        scale=binding.dpi/96
        left,top,right,bottom=binding.rect
        x=round(left+sum(p[0] for p in box)/4-self.width()*scale/2)
        # Center over the game tier badge, below the augment description.
        y=round(top+(bottom-top)*.596-self.height()*scale/2)
        width,height=round(self.width()*scale),round(self.height()*scale)
        x=max(left,min(x,right-width));y=max(top,min(y,bottom-height))
        geometry=(x,y,width,height,binding.dpi)
        if not was_visible or geometry!=getattr(self,'_native_geometry',None):
            if win.user.SetWindowPos(self.handle,c.c_void_p(-1),x,y,width,height,0x10|0x40):
                self._native_geometry=geometry


class GuidePage(QWebEnginePage):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        # DataJ's button uses navigator.clipboard.writeText after a user click.
        # Enable sanitized copy, not clipboard reads or unrestricted paste.
        self.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard,True)
        self.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanPaste,False)

    def acceptNavigationRequest(self,url,kind,is_main):
        return url.toString()=='about:blank' or (url.scheme()=='https' and url.host()=='www.dataj.cc')

    def chooseFiles(self,mode,old_files,accepted_mime_types):
        return []


class Companion(QWidget):
    def __init__(self, offline=False, offline_catalog=None):
        super().__init__()
        self.setWindowTitle('DataJ 阵容助手')
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint,True)
        self.setObjectName('companion');self.setStyleSheet(STYLE)
        self.resize(760,430);self.setMinimumSize(760,430)
        self.session=Session()
        self.selected_resources=SelectedResources(self.session.session_id)
        self.entity_resolver=EntityResolver({})
        self.selections=SelectionController(self.session.session_id,self.entity_resolver,
            on_selected=self.selection_confirmed,on_context_reset=self.game_context_changed,win_api=win)
        self.selection_tracker=self.selections.tracker
        self.condition_generation=0
        self.last_resource_guard=float('-inf')
        self.resources_uncertain=False
        self.offline=offline
        self.versions_ready=offline
        self.versions_pending=False
        self.frame_recorder=FrameRecorder()
        self.save_diagnostic_frames=os.environ.get('DATAJ_DIAGNOSTIC_FRAMES')=='1'
        self.next_ocr_allowed=0.0
        self.last_binding_probe=float('-inf')
        self.partial_retries=0
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
        self.rank_capture_started=None
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
        sidebar=QFrame();sidebar.setObjectName('sidebar');sidebar.setFixedWidth(120)
        rail=QVBoxLayout(sidebar);rail.setContentsMargins(8,10,8,8);rail.setSpacing(4)
        brand=QHBoxLayout();brand.addWidget(label('阵容助手','brand'));rail.addLayout(brand)
        rail.addSpacing(4)

        self.navigation={}
        self.navigation_group=QButtonGroup(self);self.navigation_group.setExclusive(True)
        for index,title in [(1,'⌕   选阵容'),(2,'▤   本局攻略'),(3,'▥   英雄出装'),(0,'◇   识别 / 设置')]:
            nav=button(title,lambda checked=False,i=index:self.tabs.setCurrentIndex(i))
            nav.setObjectName('nav');nav.setCheckable(True);rail.addWidget(nav);self.navigation[index]=nav
            self.navigation_group.addButton(nav,index)
        rail.addStretch();rail.addWidget(label('统计版本','muted'))
        self.patch=QComboBox();self.patch.addItem(self.adapter.patch if offline else '读取版本…');self.patch.setEnabled(offline)
        self.patch.setToolTip('启动时读取网页版本列表，默认使用最新版本；可手动切换历史版本')
        self.patch.setStyleSheet('QComboBox::down-arrow {image:url("'+(RESOURCE_DIR/'chevron-down.svg').as_posix()+'");width:12px;height:8px;}')
        self.patch.activated.connect(self.change_patch);rail.addWidget(self.patch);rail.addSpacing(8)
        self.version_retry=button('重试版本列表',self.load_versions);self.version_retry.hide();rail.addWidget(self.version_retry)

        rail.addSpacing(4);rail.addWidget(button('退出助手',QApplication.instance().quit))
        shell.addWidget(sidebar)
        content=QWidget();root=QVBoxLayout(content);root.setContentsMargins(10,8,10,6);root.setSpacing(5)
        shell.addWidget(content,1)
        header=QHBoxLayout();headings=QVBoxLayout();headings.setSpacing(5)
        self.banner=label('局内识别','pageTitle');headings.addWidget(self.banner)
        self.subtitle=label('','subtitle');self.subtitle.hide()
        header.addLayout(headings,1)
        self.banner.setToolTip('按住标题拖动窗口')
        self.banner.mousePressEvent=self.drag_window
        header.addWidget(button('新的一局',self.new_game));header.addWidget(button('收起 ‹',self.return_to_game))
        close_button=button('×',QApplication.instance().quit);close_button.setFixedWidth(32);close_button.setStyleSheet('padding:0;font-size:20px');close_button.setToolTip('退出助手');header.addWidget(close_button)
        root.addLayout(header)
        self.target_label=label('本局阵容：未固定','target')
        target_row=QHBoxLayout();target_row.addWidget(self.target_label,1)
        self.copy_button=button('复制主阵容码',self.copy_code);self.copy_button.setEnabled(False);target_row.addWidget(self.copy_button)
        target_row.addWidget(button('换阵容',lambda:self.tabs.setCurrentIndex(1)))
        root.addLayout(target_row)
        self.tabs=QTabWidget();self.tabs.tabBar().hide();root.addWidget(self.tabs,1)
        self.make_choices()
        self.make_explorer()
        self.make_guide()
        self.make_equipment()
        self.items=ItemController(self)
        self.conditions=ConditionController(self)
        self.browser.input_bar.readRequested.connect(self.conditions.trigger)
        self.tabs.currentChanged.connect(self.navigate);self.tabs.setCurrentIndex(1);self.navigate(1)
        self.apply_display_preferences()
        self.status=label('Ctrl + Alt + F9 随时展开或收起助手。','status')
        self.status.setWordWrap(True)
        bottom=QHBoxLayout();bottom.addWidget(self.status,1);bottom.addWidget(QSizeGrip(self));root.addLayout(bottom)
        self.status.setToolTip('Ctrl+Alt+F10 查均排 · Ctrl+Alt+F9 展开/收起 · Ctrl+Alt+F12 退出')
        self.timer=QTimer(self);self.timer.timeout.connect(self.tick);self.timer.start(150)
        self.refresh_windows()
        if offline:
            data=offline_catalog if offline_catalog is not None else json.loads((ROOT/'work/s18-refresh-20260926/catalog.json').read_text(encoding='utf-8'))['data']
            self.catalog_loaded({'data':data},True)
        else:
            self.load_versions()

    def drag_window(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.windowHandle():self.windowHandle().startSystemMove()

    def load_versions(self,*_):
        # One startup request, with explicit retries only after failure. No
        # catalog/statistics or game recognition can run until it succeeds.
        if self.offline or self.versions_ready or self.versions_pending:return
        self.versions_pending=True
        self.version_retry.hide();self.patch.setEnabled(False);self.tabs.setEnabled(False)
        self.patch.clear();self.patch.addItem('读取版本…')
        self.status.setText('正在读取 DataJ 版本列表，随后加载最新版本统计…')
        self.browser.note.setText('正在确认最新统计版本…')
        self.set_activity('versions_loading','正在读取最新统计版本，请稍候。')
        self.submit(self.network,self.adapter.versions,self.startup_versions_loaded,self.versions_failed)

    def startup_versions_loaded(self,versions):
        if self.versions_ready:return
        if (not isinstance(versions,list) or not versions
            or any(not isinstance(v,str) or not re.fullmatch(r'18\.\d+(?:\.?[a-z])?',v) for v in versions)):
            self.versions_failed('invalid versions');return
        try:
            # Preserve an already-correct adapter (also used by frozen OCR
            # checks); otherwise select the first entry in the site's order.
            adapter=self.adapter if self.adapter.patch==versions[0] else DataJ(patch=versions[0])
        except Exception as exc:
            self.versions_failed(str(exc));return
        self.adapter=adapter;self.session.patch=adapter.patch
        self.versions_loaded(versions)
        self.versions_pending=False;self.versions_ready=True
        self.patch.setEnabled(True);self.tabs.setEnabled(True);self.version_retry.hide()
        self.patch.setToolTip('默认使用启动时的网页最新版本；切换后重新加载该版本的统计')
        self.status.setText(f'已选择网页最新版本 {adapter.patch}，正在准备统计…')
        self.load_catalog()

    def versions_failed(self,_):
        if self.versions_ready:return
        self.versions_pending=False
        self.patch.clear();self.patch.addItem('版本读取失败');self.patch.setEnabled(False)
        self.patch.setToolTip('未确认网页最新版本，暂停统计；点击下方按钮重试')
        self.version_retry.show()
        self.status.setText('版本列表读取失败，请点击「重试版本列表」。')
        self.browser.note.setText('最新版本尚未确认，暂不加载统计。')
        self.set_activity('versions_failed','版本列表读取失败，请重试；暂不加载旧版统计。')

    def versions_loaded(self,versions):
        selected=self.adapter.patch
        self.patch.blockSignals(True);self.patch.clear();self.patch.addItems(versions)
        if selected not in versions:self.patch.addItem(selected)
        self.patch.setCurrentText(selected);self.patch.blockSignals(False)
        self.latest_patch=versions[0]
        if self.guide_requested_url:
            tab=self.tabs.currentIndex()
            self.open_guide(self.guide_requested_url,allow_latest=self.guide_allow_latest,reload=False)
            self.tabs.setCurrentIndex(tab)

    def navigate(self,index):
        headings=[('局内识别','自动检查海克斯与装备选择，侧键随时补查。'),
                  ('选阵容','先选一个检索条件，再点击适合这局的阵容。'),
                  ('本局攻略','阵容已固定，攻略、出装和强化查询一起跟随。'),
                  ('英雄出装','查看本局阵容下的装备表现，寻找替代选择。')]
        self.banner.setText(headings[index][0]);self.subtitle.setText(headings[index][1])
        for i,nav in self.navigation.items():nav.setChecked(i==index)

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
        def release():
            # QObject connections own these closures, which own the job and
            # often a 4K image. Break that cycle on both completion paths.
            self.jobs.discard(job)
            job.signals.done.disconnect()
            job.signals.failed.disconnect()
        def finish(value):
            release()
            done(value)
        def error(message):
            release()
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
        hero_text.addWidget(label('自动识别海克斯 / 装备 · 侧键随时补查','eyebrow'))
        self.activity=label('正在准备局内数据…','activity');hero_text.addWidget(self.activity)
        hero_text.addWidget(label('鼠标侧键截图查均排 · Ctrl+Alt+F10 仍可使用','muted'))
        hero_layout.addLayout(hero_text,1)
        self.start_button=button('暂停自动识别',self.start_or_pause)
        self.start_button.setObjectName('primary');self.start_button.setMinimumWidth(150)
        self.start_button.setMinimumHeight(46);self.start_button.setEnabled(False)
        hero_layout.addWidget(self.start_button);layout.addWidget(hero)
        layout.addWidget(label('海克斯：每 3 秒检查阶段；装备：每 2 秒检查底部选择。侧键随时补查。','muted'))
        layout.addWidget(button('立即补查一次',self.capture_once))
        self.mouse_button=QComboBox()
        for title,value in [('后退侧键：读详情 / 查均排（默认）',1),('前进侧键：读详情 / 查均排',2),('关闭鼠标侧键',0)]:self.mouse_button.addItem(title,value)
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
        self.automatic=QCheckBox('自动阶段识别（默认开启，仅 MuMu 前台）')
        self.automatic.setChecked(True)
        self.automatic.toggled.connect(self.automatic_changed);advanced.addWidget(self.automatic)

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
        appearance=QHBoxLayout();appearance.addWidget(QLabel('界面大小'))
        self.panel_size=QComboBox();self.panel_size.addItems(['紧凑','标准','宽屏']);self.panel_size.setCurrentIndex(0)
        self.panel_size.activated.connect(self.resize_panel);appearance.addWidget(self.panel_size)
        self.text_size=QComboBox();self.text_size.addItems(['标准字体','大字体']);self.text_size.activated.connect(self.change_text_size)
        appearance.addWidget(self.text_size);appearance.addWidget(button('回到左上角',self.reset_position));advanced.addLayout(appearance)
        self.add_page(page,'海克斯')

    def resize_panel(self,index):
        self.resize(*[(760,430),(960,600),(1140,760)][index])

    def change_text_size(self,index):
        scale=1.12 if index else 1.0
        self.setStyleSheet(re.sub(r'font-size:(\d+)px',lambda m:f'font-size:{round(int(m[1])*scale)}px',STYLE))
        self.setMinimumWidth(760)
        if not self.offline:self.mouse_settings.setValue('large_text',index)

    def apply_display_preferences(self):
        if self.offline:return
        saved=self.mouse_settings.value('panel_geometry')
        if saved is not None:self.restoreGeometry(saved)
        if str(self.mouse_settings.value('compact_dimensions',0))!='1':
            self.resize(760,430);self.mouse_settings.setValue('compact_dimensions',1)
        index=1 if str(self.mouse_settings.value('large_text',0))=='1' else 0
        self.text_size.setCurrentIndex(index);self.change_text_size(index)

    def reset_position(self):
        area=QApplication.primaryScreen().availableGeometry()
        self.move(area.left()+64,area.top()+12);self.mark.move(area.left()+12,area.top()+12)

    def toggle_advanced(self):
        opened=self.advanced.isHidden()
        self.advanced.setVisible(opened)
        self.advanced_toggle.setText('收起高级设置 ▾' if opened else '手动查询与高级设置 ▸')

    def set_activity(self,code,message):
        self.activity.setText(message)
        self.mark.button.setToolTip(message+'\n点击展开 / 收起 · 按住拖动位置 · Ctrl+Alt+F10 查均排')
        if self.activity_code==code:return
        self.activity_code=code
        if not self.offline:record('state',code=code,automatic=self.automatic.isChecked(),bound=self.binding is not None)
        # Local status only: no screenshot, OCR text, credentials or game controls.
        payload={'time':datetime.now().isoformat(timespec='seconds'),'state':code,'message':message,
                 'automatic':self.automatic.isChecked(),'bound':self.binding is not None}
        try:(STATE_DIR/('offline-status.json' if self.offline else 'assistant-status.json')).write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
        except OSError:pass

    def start_or_pause(self):
        if not self.versions_ready:self.load_versions();return
        if self.automatic.isChecked():
            self.automatic.setChecked(False)
            self.set_activity('paused','自动识别已暂停，鼠标侧键仍可补查。');return
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
        self.automatic.setChecked(True)
        self.set_activity('waiting_choice','已连接 MuMu，等待海克斯选择。')
        self.return_to_game()

    def make_explorer(self):
        self.browser=CompBrowser(self.mouse_settings,self.offline)
        self.browser.queryRequested.connect(self.load_comps)
        self.browser.compSelected.connect(self.select_comp)
        self.browser.input_bar.confirmRequested.connect(self.confirm_condition)
        self.tabs.addTab(self.browser,'选阵容')

    def refresh_selected_resources(self):
        shortcuts=[]
        for event in self.selected_resources.shortcuts:
            row=next((r for r in self.entity_resolver.entries(event.kind) if str(r['id'])==event.entity_id),None)
            if row:shortcuts.append({'kind':event.kind,'entity':row})
        self.browser.input_bar.set_resources(shortcuts)
        if self.resources_uncertain:
            for chip in self.browser.input_bar.chips:chip.setEnabled(False)
            self.browser.input_bar.more.setEnabled(False)
            self.browser.input_bar.confirm.setEnabled(False)
        else:
            self.browser.input_bar.more.setEnabled(True);self.browser.input_bar.confirm.setEnabled(True)

    def selection_confirmed(self,event):
        if self.resources_uncertain:return
        accepted=self.selected_resources.confirm(event.entity,selection_event_id=event.selection_event_id,
            session_id=event.session_id,selected_at=event.selected_at,source=event.source,
            round=event.round,evidence_reference=event.evidence_reference)
        if accepted:self.refresh_selected_resources()

    def confirm_condition(self):
        if not self.browser.scope or self.resources_uncertain or self.browser.input_bar.confirm.isHidden():return
        kind,row=self.browser.scope
        if kind not in ('hex','equip','hero'):return
        resolution=self.entity_resolver.resolve_selection(kind,row)
        if not resolution.confirmed:
            self.browser.input_bar.show_note('名称身份未确认，不能记为本局已选。');return
        entity=resolution.entity
        selected=SelectionEntity(kind,str(entity['id']),entity['name'],
            entity.get('category',entity.get('type','')),entity.get('picture',''),True)
        event_id=f'manual:{self.session.session_id}:{self.browser.input_revision}:{kind}:{entity["id"]}'
        accepted=self.selected_resources.confirm(selected,selection_event_id=event_id,
            session_id=self.session.session_id,selected_at=time.monotonic(),source='manual_confirmation',round=self.session.stage)
        if accepted:
            self.refresh_selected_resources();self.browser.input_bar.confirm.hide()
            self.browser.input_bar.show_note('已记入本局选过的资源，点击条目即可单项检索。')

    def make_guide(self):
        page=QWidget();layout=QVBoxLayout(page);layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        row=QHBoxLayout()
        row.addWidget(button('攻略',lambda:self.tabs.setCurrentIndex(2)))
        row.addWidget(button('出装',lambda:self.tabs.setCurrentIndex(3)))
        row.addWidget(button('强化',lambda:self.tabs.setCurrentIndex(0)))
        row.addStretch();row.addWidget(button('取消定阵',self.unpin));layout.addLayout(row)
        self.guide_notice=label('先在阵容列表选择一套阵容。','muted');self.guide_notice.setWordWrap(True);layout.addWidget(self.guide_notice)
        self.guide_retry=button('重试加载本局阵容',self.retry_comp);self.guide_retry.hide();layout.addWidget(self.guide_retry)
        self.comp_url=QLineEdit();self.comp_url.setPlaceholderText('DataJ 阵容地址')
        self.address_box=QWidget();address=QHBoxLayout(self.address_box);address.setContentsMargins(0,0,0,0)
        address.addWidget(self.comp_url);address.addWidget(button('选择此阵容',self.pin_comp));address.addWidget(button('只浏览',self.browse_comp))
        toggle=button('其他阵容地址 ▸',lambda:self.address_box.setVisible(not self.address_box.isVisible()));toggle.setObjectName('subtle')
        layout.addWidget(toggle);layout.addWidget(self.address_box);self.address_box.hide()
        self.profile=QWebEngineProfile(self)
        self.profile.downloadRequested.connect(lambda item:item.cancel())
        self.web=QWebEngineView()
        self.guide_page=GuidePage(self.profile,self.web)
        self.guide_page.featurePermissionRequested.connect(lambda origin,feature:self.guide_page.setFeaturePermission(origin,feature,QWebEnginePage.PermissionPolicy.PermissionDeniedByUser))
        self.web.setPage(self.guide_page);self.guide_page.setBackgroundColor(QColor('#191922'))
        self.web.setZoomFactor(0.75)
        self.guide_empty=QFrame();self.guide_empty.setObjectName('hero');empty=QVBoxLayout(self.guide_empty)
        empty.setContentsMargins(30,40,30,40);empty.addWidget(label('先找到这局的方向','pageTitle'))
        empty.addWidget(label('从阵容列表点击一套，立刻固定为本局目标。\n之后可以复制阵容码，并查看攻略、出装与强化统计。','muted'))
        empty.addSpacing(16);empty.addWidget(button('去选阵容  →',lambda:self.tabs.setCurrentIndex(1)))
        layout.addWidget(self.guide_empty)
        self.guide_requested_url=None;self.guide_allow_latest=False
        self.guide_version=QFrame();self.guide_version.setObjectName('hero');version=QVBoxLayout(self.guide_version)
        version.setContentsMargins(16,20,16,20)
        self.guide_version_title=label('','pageTitle');self.guide_version_title.setWordWrap(True);version.addWidget(self.guide_version_title)
        self.guide_version_note=label('','muted');self.guide_version_note.setWordWrap(True);version.addWidget(self.guide_version_note)
        self.guide_latest=button('查看原站最新攻略',self.open_latest_guide);version.addWidget(self.guide_latest)
        version.addWidget(button('查看本局英雄出装',lambda:self.tabs.setCurrentIndex(3)))
        layout.addWidget(self.guide_version);self.guide_version.hide()
        self.web.setMinimumHeight(320);layout.addWidget(self.web);self.web.hide()
        self.web.urlChanged.connect(self.guide_url_changed)
        layout.addWidget(label('浏览不会自动更换本局阵容。变体阵容码请在原站复制。','muted'))
        self.add_page(page,'阵容攻略')

    def make_equipment(self):
        page=QWidget();layout=QVBoxLayout(page)
        self.hero_buttons=[];hero_scroll=QScrollArea();hero_scroll.setWidgetResizable(True);hero_scroll.setFixedHeight(108)
        hero_content=QWidget();self.hero_layout=QHBoxLayout(hero_content);self.hero_layout.setContentsMargins(0,0,0,0);self.hero_layout.addStretch()
        hero_scroll.setWidget(hero_content);layout.addWidget(hero_scroll)
        row=QHBoxLayout();self.heroes=QComboBox();self.heroes.hide()
        self.equip_form=QComboBox();self.equip_form.addItems(['单件','三件套']);row.addWidget(self.equip_form)
        self.equip_type=QComboBox();self.equip_type.addItems(['全部','成型装备','神器装备','光明武器','转职纹章','特殊装备']);row.addWidget(self.equip_type)
        row.addWidget(button('查询出装',self.query_equipment));layout.addLayout(row)
        self.equip_table=table(['装备（所选英雄在已固定阵容中）','平均排名','样本'])
        layout.addWidget(self.equip_table)
        self.equip_note=label('先选一套阵容，再点击英雄头像查看出装。','muted');layout.addWidget(self.equip_note)
        self.equip_form.currentIndexChanged.connect(self.query_equipment)
        self.equip_type.currentIndexChanged.connect(self.query_equipment)
        self.heroes.currentIndexChanged.connect(self.clear_equipment)
        self.heroes.activated.connect(self.query_equipment)
        self.add_page(page,'阵容出装')

    def populate_hero_buttons(self):
        for item in self.hero_buttons:self.hero_layout.removeWidget(item);item.deleteLater()
        self.hero_buttons=[]
        heroes=(self.comp_detail or {}).get('heroes',[])
        catalog=portrait_catalog(self.catalog.get('hero',[]))
        for hero in heroes:
            item=QPushButton();item.setCheckable(True);item.setFixedSize(78,84)
            item.setToolTip(hero['heroName']);box=QVBoxLayout(item);box.setContentsMargins(4,3,4,3)
            box.addWidget(HeroPortrait(hero,catalog,self.browser.portraits),0,Qt.AlignmentFlag.AlignCenter)
            item.clicked.connect(lambda checked=False,id_=str(hero['heroId']):self.select_hero(id_))
            self.hero_layout.insertWidget(len(self.hero_buttons),item);self.hero_buttons.append(item)

    def select_hero(self,hero):
        index=self.heroes.findData(hero);self.heroes.setCurrentIndex(index)
        for i,item in enumerate(self.hero_buttons):item.setChecked(i==index)
        self.query_equipment()

    def load_catalog(self):
        if not self.versions_ready:return
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
        self.browser.set_catalog(self.catalog)
        self.entity_resolver=self.browser.resolver
        self.selections.resolver=self.entity_resolver
        self.conditions.configure()
        self.refresh_selected_resources()
        self.start_button.setEnabled(True)
        self.set_activity('ready','收起面板后自动检查海克斯与装备选择，侧键可随时补查。' if self.automatic.isChecked() else '自动识别已暂停，鼠标侧键可随时补查。')
        self.status.setText('离线演示已准备好。' if offline else '目录已准备好，正在后台预热识别与统计；首次查询可能稍慢。')
        if not offline:
            # Native OCR runtime initialization on a Qt worker crashes on first
            # inference in this Windows runtime. Initialize on the GUI thread;
            # subsequent recognition stays on the serialized OCR worker.
            try:
                self.vision.prepare()
            except Exception:
                self.set_activity('ocr_failed','OCR 初始化失败，请检查本机模型与运行环境。')
                return
            self.submit(self.network,self.adapter.hexes,lambda _:None)
            self.browser.retry()
            self.items.prewarm()
        if self.session.target and self.comp_detail is None:
            self.comp_url.setText('https://www.dataj.cc/comp/'+self.session.target)
            self.pin_comp()

    def change_patch(self,*_):
        if not self.versions_ready:return
        try:adapter=DataJ(patch=self.patch.currentText().strip())
        except ValueError as exc:self.status.setText(str(exc));return
        if adapter.patch==self.adapter.patch:return
        self.adapter=adapter;self.session.patch=adapter.patch;self.catalog={}
        self.condition_generation+=1;self.invalidate();self.clear_equipment()
        self.explorer_generation+=1;self.comp_generation+=1
        self.comp_detail=None;self.copy_button.setEnabled(False)
        self.heroes.blockSignals(True);self.heroes.clear();self.heroes.blockSignals(False);self.populate_hero_buttons()
        self.web.stop();self.web.hide();self.guide_empty.setVisible(self.session.target is None)
        self.guide_version.hide();self.guide_retry.hide()
        if self.session.target:self.guide_notice.setText('正在重新读取所选版本的固定阵容…')
        self.load_catalog()
        self.status.setText(f'当前统计版本 {adapter.patch}，请与游戏版本保持一致。')

    def refresh_windows(self):
        if not hasattr(self,'windows'):return
        self.windows.clear()
        for item in game_windows():
            self.windows.addItem(f'{item.title} · {item.rect[2]-item.rect[0]}×{item.rect[3]-item.rect[1]}',item)

    def bind_window(self):
        item=self.windows.currentData()
        if item and win.same_target(item,win.describe(item.hwnd)):
            self.selections.binding_changed(item)
            self.binding=item;self.geometry=(item.rect,item.dpi);self.invalidate();self.status.setText('已绑定 MuMu。自动检查海克斯与装备选择，侧键可随时补查。')
        else:self.status.setText('没有有效 MuMu 游戏窗口')

    def hide_overlays(self):
        for label in self.overlays:label.hide()
        if hasattr(self,'items'):self.items.hide()

    def invalidate(self):
        if hasattr(self,'selections'):self.selections.scene_left()
        if hasattr(self,'items'):self.items.reset()
        self.partial_retries=0
        self.stats_inflight_token=None
        self.session.invalidate();self.signature=None;self.stable=0;self.stats_payload=None;self.last_observation=None
        self.last_frame=None
        self.once_active=False
        self.once_ocr_pending=False
        self.was_available=False
        self.hide_overlays()
        if hasattr(self,'choice_table'):self.choice_table.setRowCount(0)
        if hasattr(self,'choice_table'):self.choice_table.hide()
        for card in getattr(self,'result_cards',[]):card.clear(self.session.target is not None)
        if getattr(self,'activity_code',None) in ('results','partial_results','no_stage_data'):
            self.set_activity('waiting_choice' if self.automatic.isChecked() else 'ready',
                              '等待海克斯或装备选择。' if self.automatic.isChecked() else '按所选鼠标侧键或 Ctrl+Alt+F10 查均排，空闲时不截图。')
            self.choice_note.setText('候选已清空，等待下一次识别。')

    def clear_choice_result(self,*_):
        self.invalidate()

    def automatic_changed(self,*_):
        self.invalidate()
        self.stage_window_until=0;self.last_probe_stage=None;self.last_binding_probe=float('-inf')
        self.start_button.setText('暂停自动识别' if self.automatic.isChecked() else '恢复自动识别')

    def new_game(self):
        self.last_probe_stage=None;self.stage_window_until=0
        self.resources_uncertain=False
        self.session.reset();self.comp_detail=None;self.heroes.clear();self.unpin()
        self.condition_generation+=1
        self.selected_resources.reset(self.session.session_id);self.selections.new_game(self.session.session_id)
        self.refresh_selected_resources()
        self.stage.setCurrentIndex(-1)
        for pick in self.picks:pick.setCurrentIndex(0)
        self.browser.clear_filter();self.tabs.setCurrentIndex(1)

    def game_context_changed(self,reason,identity):
        self.new_game()
        self.browser.input_bar.show_note('游戏窗口已变化，上一局的已选记录已清除。')

    def resource_context_guard(self):
        # A handle/PID check only: no new screenshot or OCR while idle.
        now=time.monotonic()
        if not self.binding or now-self.last_resource_guard<3:return
        self.last_resource_guard=now
        current=win.describe(self.binding.hwnd)
        if not current or not win.same_target(self.binding,current):
            self.selections.window_closed();self.binding=None;self.geometry=None
        else:
            if (current.rect,current.dpi)!=(self.binding.rect,self.binding.dpi):
                self.condition_generation+=1
            self.selections.binding_changed(current)
            self.binding=current;self.geometry=(current.rect,current.dpi)

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

    def showEvent(self,event):
        super().showEvent(event)
        self.mark.set_panel_open(True)

    def hideEvent(self,event):
        super().hideEvent(event)
        self.mark.set_panel_open(False)

    def changeEvent(self,event):
        super().changeEvent(event)
        if hasattr(self,'mark'):self.mark.set_panel_open(self.panel_open())

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
        if hasattr(self,'conditions'):self.conditions.trigger()
        else:self.capture_once()

    def capture_once(self):
        if not self.versions_ready:return
        if self.capture_pending or self.ocr_busy or (self.once_active and self.once_ocr_pending):return
        if not self.catalog:
            self.set_activity('catalog_missing','数据正在准备，请稍后再按截图快捷键。');return
        if not self.binding or not win.same_target(self.binding,win.describe(self.binding.hwnd)):
            self.refresh_windows()
            if self.windows.count()!=1:
                self.set_activity('no_game','没有找到唯一的 MuMu 游戏窗口，请在面板选择窗口。');return
            self.bind_window()
        if not self.binding:return
        # A refresh from the game must retain confirmed ranks until the new
        # frame proves that the choices changed. Opening the panel still resets.
        needs_return=self.panel_open() or win.foreground_root()!=self.binding.hwnd
        if needs_return:
            if self.return_to_game() is False:return
        self.once_active=True;self.once_deadline=time.monotonic()+30
        self.once_ocr_pending=True;self.next_ocr_allowed=0
        QTimer.singleShot(100 if needs_return else 0,lambda:self.request_capture())

    def request_capture(self,once=False):
        if self.capture_pending or not self.binding:return
        self.capture_pending=True
        self.rank_capture_started=time.monotonic()
        binding=self.binding;token=self.session.token()
        def done(captured):
            result,captured_at=captured
            self.capture_pending=False
            if self.session.accepts(token):self.captured(result,once,captured_at)
            else:self.rank_capture_started=None
        def failed(message):
            self.capture_pending=False
            if self.session.accepts(token):self.capture_failed(message)
        def begin():
            def capture():
                result=capture_image(binding)
                return result,time.monotonic()
            self.submit(self.capture_pool,capture,done,failed)
        # Rank windows sit at the tier badges, outside title/round OCR regions.
        # Keep them visible during capture; changed inputs still invalidate results.
        begin()

    def capture_failed(self,message):
        if not self.offline:record('capture_failed')
        self.rank_capture_started=None
        self.capture_pending=False;self.invalidate()
        self.set_activity('capture_failed','暂时无法读取游戏画面。请保持 MuMu 在前台；助手会继续尝试。')

    def choices_changed(self,once=False):
        """Discard old ranks while keeping a bounded re-recognition request."""
        manual=self.once_active
        deadline=max(self.once_deadline,time.monotonic()+30) if manual else self.once_deadline
        retry=once or self.once_ocr_pending or manual or self.automatic.isChecked()
        self.invalidate()
        self.once_active=manual;self.once_deadline=deadline;self.once_ocr_pending=retry
        if self.automatic.isChecked():self.stage_window_until=max(self.stage_window_until,time.monotonic()+15)

    def captured(self,result,once,captured_at=None):
        image,binding=result
        self.capture_pending=True
        token=self.session.token();observation=self.last_observation
        item_reference_boxes=tuple(self.items.boxes)
        captured_at=time.monotonic() if captured_at is None else captured_at
        def inspect():
            # Three refresh controls identify the augment scene; board shapes
            # below it must not hijack recognition as an item-card proposal.
            items=([],None) if may_be_choice(image) else inspect_items(image,item_reference_boxes)
            signature=tracked_signature(image,observation) if observation else None
            return items,signature
        def done(prepared):
            self.capture_pending=False
            self.rank_capture_started=None
            if self.session.accepts(token):self.accept_frame(result,once,prepared,captured_at)
        def failed(message):
            self.capture_pending=False
            self.rank_capture_started=None
            if self.session.accepts(token):self.capture_failed(message)
        self.submit(self.capture_pool,inspect,done,failed)

    def accept_frame(self,result,once,prepared,captured_at):
        """Qt state changes only; pixel inspection has finished on the worker."""
        image,binding=result
        if not self.offline:record('captured',width=image.width,height=image.height)
        if (not self.binding or not win.same_target(self.binding,binding) or self.panel_open()
            or win.foreground_root()!=binding.hwnd):return
        self.last_capture=captured_at
        items,signature=prepared
        if self.last_observation:
            if not unchanged(signature,self.signature):
                # Keep a manual request armed when it actually discovers new cards.
                self.choices_changed(once)
            elif (self.stats_payload and self.stats_payload['live']
                  and self.session.accepts(self.stats_payload['token'])
                  and all(c.get('resolution',{}).get('id') for c in self.last_observation['cards'])):
                # The same text already has confirmed statistics; a side-button
                # refresh needs a fresh frame check, not another OCR pass.
                retry_stats=(once or self.once_ocr_pending) and self.stats_payload.get('retryable',False)
                self.once_ocr_pending=False;once=False
                self.selections.observe(self.last_observation,image.size,binding,captured_at)
                if retry_stats:
                    self.query_stats(list(self.session.choices),[r[0] for r in self.stats_payload['rows']],True,refresh=True)
        # All accepted frames supersede in-flight OCR, including item proposals
        # which return before the shared augment path can start another read.
        self.last_frame=image
        if self.items.ingest(image,binding,force=once or self.once_ocr_pending,prepared=items,frame_time=captured_at):
            self.once_ocr_pending=False
            return
        if once:self.once_ocr_pending=True
        # Retry a transient unreadable title twice, using already scheduled captures.
        # Keep existing ranks visible; normal session checks still reject changed cards.
        partial_retry=(self.last_observation is not None
                       and any(not c.get('resolution',{}).get('id') for c in self.last_observation.get('cards',[]))
                       and self.partial_retries<2
                       and (self.automatic.isChecked() or self.once_active)
                       and not self.ocr_busy and self.catalog
                       and time.monotonic()>=self.next_ocr_allowed
                       and time.monotonic()-self.last_ocr>2)
        if self.once_ocr_pending and not self.ocr_busy and self.catalog and time.monotonic()>=self.next_ocr_allowed:
            self.once_ocr_pending=False
            self.partial_retries=0
            self.analyze(image,True)
        elif partial_retry:
            self.partial_retries+=1
            self.analyze(image,True,retain_confirmed=True)
        elif (self.automatic.isChecked() and time.monotonic()>=self.next_ocr_allowed
              and time.monotonic()-self.last_ocr>2
              and not (self.last_observation and (self.stats_payload or self.stats_inflight_token==self.session.token()))):
            self.analyze(image,True)
        if self.stats_payload and self.last_observation:
            self.display_overlays()

    def analyze(self,image,live,retain_confirmed=False):
        if self.ocr_busy or not self.catalog:return
        self.ocr_busy=True;self.ocr_live=live;self.last_ocr=time.monotonic()
        token=self.session.token();catalog=self.catalog['hex']
        retained_observation=self.last_observation if retain_confirmed else None
        retained_payload=self.stats_payload if retain_confirmed else None
        def finish(obs,signature):
            self.ocr_busy=False
            if not self.session.accepts(token):return
            if live and (self.panel_open() or not self.binding or win.foreground_root()!=self.binding.hwnd):return
            # accept_frame verified unchanged title/round pixels before this
            # bounded partial retry. An OCR miss cannot erase confirmed slots;
            # a changed frame/session or loss of the choice scene still clears.
            if (live and retained_observation is not None and retained_payload is not None
                and self.last_observation is retained_observation and self.stats_payload is retained_payload
                and retained_payload.get('live') and self.session.accepts(retained_payload['token'])
                and obs.get('scene')=='choice_unresolved'
                and obs.get('round') in (None,retained_observation.get('round'))
                and time.monotonic()-self.last_capture<=1.5):
                if not self.offline:record('ocr_partial_retained')
                self.display_overlays();return
            if live:self.signature=signature
            self.observed(obs,live)
        def done(result):
            obs,signature=result
            self.next_ocr_allowed=time.monotonic()+1.5
            if not self.offline:record('ocr_complete',scene=obs.get('scene'),reason=obs.get('reason'),diagnostic_frame=obs.get('diagnostic_frame'),stage=obs.get('round'),elapsed_ms=obs.get('elapsed_ms'),resolutions=[c.get('resolution',{}).get('status') for c in obs.get('cards',[])],unresolved=[{'slot':c.get('slot'),'readings':c.get('resolution',{}).get('readings',[])} for c in obs.get('cards',[]) if not c.get('resolution',{}).get('id')],session_valid=self.session.accepts(token))
            if not self.session.accepts(token):self.ocr_busy=False;return
            latest=self.last_frame
            if live and obs.get('scene')=='choice_candidates' and latest is not image:
                def check_latest(frame,remaining=2):
                    def checked(current):
                        if not self.session.accepts(token):self.ocr_busy=False;return
                        if frame is not self.last_frame:
                            # A new screenshot object is not evidence of new
                            # choices. Check its pixels before clearing ranks.
                            if remaining and self.last_frame is not None:
                                check_latest(self.last_frame,remaining-1);return
                            self.ocr_busy=False
                            if not self.offline:record('ocr_verification_superseded')
                            return
                        if not unchanged(signature,current):
                            self.ocr_busy=False
                            self.choices_changed()
                            self.set_activity('frame_changed','选择画面发生变化，正在重新识别…');return
                        finish(obs,current)
                    self.submit(self.capture_pool,lambda:tracked_signature(frame,obs) if frame else None,checked,failed)
                check_latest(latest)
            else:finish(obs,signature)
        def failed(_):
            self.ocr_busy=False
            self.next_ocr_allowed=time.monotonic()+2
            if not self.offline:record('ocr_failed')
            if self.session.accepts(token):self.set_activity('ocr_failed','识别未成功，助手会继续尝试。也可以稍后用截图排查。')
        def recognize():
            observation=self.vision.analyze_fast(image,catalog) if live else self.vision.analyze(image,catalog)
            if live and not self.offline and self.save_diagnostic_frames:
                observation['diagnostic_frame']=self.frame_recorder.save(image,observation)
            return observation,tracked_signature(image,observation) if live and observation.get('scene')=='choice_candidates' else None
        self.submit(self.ocr_pool,recognize,done,failed)

    def observed(self,obs,live):
        self.last_observation=obs
        if live and self.binding:
            self.selections.observe(obs,obs.get('image_size',self.binding.rect[2:]),self.binding,self.last_capture)
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
        if self.stage.currentText() not in STAGES or not any(p.currentData() for p in self.picks):
            self.status.setText('请先确认阶段并选择海克斯。');return
        ids=[p.currentData() if p.currentText()==p.itemText(p.currentIndex()) else None for p in self.picks]
        names=[p.currentText().split(' · ')[0] for p in self.picks]
        self.query_stats(ids,names,False)

    def query_stats(self,ids,names,live,refresh=False):
        if not self.versions_ready:return
        same_choices=self.session.stage==self.stage.currentText() and self.session.choices==tuple(ids)
        if live and same_choices:
            if self.stats_inflight_token==self.session.token():return
            if not refresh and self.stats_payload and self.stats_payload['live'] and self.session.accepts(self.stats_payload['token']):
                self.display_overlays();return
        retained=(self.stats_payload if refresh and live and same_choices and self.stats_payload
                  and self.stats_payload['live'] and self.session.accepts(self.stats_payload['token']) else None)
        self.session.set_choices(self.stage.currentText(),ids)
        self.set_activity('querying','正在获取海克斯均排…')
        if retained:retained['token']=self.session.token()
        else:
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
            self.stats_payload={'rows':rendered,'live':live,'created':time.monotonic(),'token':token,
                                'retryable':bool(target and comp_finished and comp_result is None)}
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
                self.stats_payload=None
                self.choice_table.setRowCount(0)
                for card in self.result_cards:card.clear(self.session.target is not None)
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
        if self.stage_probe_pending or self.ocr_busy or self.capture_pending or self.items.active:return
        self.stage_probe_pending=True;self.last_stage_probe=time.monotonic()
        token=self.session.token();binding=self.binding
        def done(stage):
            self.stage_probe_pending=False
            if not self.session.accepts(token) or not self.automatic.isChecked():return
            # A side-button request already owns the next full frame. A late
            # background probe must not cancel it before that frame is examined.
            if self.once_active and self.once_ocr_pending:return
            if stage=='2-1' and self.last_probe_stage and self.last_probe_stage[0] in '3456789' and self.selected_resources.events:
                self.resources_uncertain=True;self.condition_generation+=1
                self.selections.cancel('game_boundary_uncertain')
                self.refresh_selected_resources()
                self.browser.input_bar.show_note('阶段回到 2-1，本局边界待确认；请点击「新的一局」清除上一局资源。')
            if stage and stage!=self.last_probe_stage:
                same_choice=self.last_observation is not None and self.session.stage==stage
                if not same_choice:self.invalidate()
                self.stage_window_until=time.monotonic()+60 if stage in STAGES else 0
                self.last_probe_stage=stage
                if stage in STAGES and not same_choice:self.once_ocr_pending=True
        def failed(_):self.stage_probe_pending=False
        self.submit(self.ocr_pool,lambda:self.vision.read_round_crop(capture_stage(binding)),done,failed)

    def tick(self):
        self.resource_context_guard();self.selections.tick()
        if not self.versions_ready:return
        if not self.automatic.isChecked() and not self.once_active and not self.stats_payload and not self.items.active:return
        if self.automatic.isChecked() and not self.binding and not self.panel_open():
            if time.monotonic()-self.last_binding_probe<3:return
            self.last_binding_probe=time.monotonic()
            targets=game_windows();foreground=win.foreground_root()
            if len(targets)!=1 or targets[0].hwnd!=foreground:return
            self.binding=targets[0];self.geometry=(self.binding.rect,self.binding.dpi)
            self.selections.binding_changed(self.binding)
            self.set_activity('watching_stage','自动识别已就绪；检查海克斯阶段与装备选择，侧键可随时补查。')
        current=win.describe(self.binding.hwnd) if self.binding else None
        reason=win.capture_block_reason(self.binding,current,win.foreground_root()) if self.binding else 'no_binding'
        if self.panel_open() or reason:
            self.hide_overlays()
            if self.was_available or self.signature is not None or (self.ocr_busy and self.ocr_live) or self.once_active or self.items.active or self.items.recognizing:self.invalidate()
            self.was_available=False
            if self.automatic.isChecked() and not self.panel_open():
                if reason=='target_changed_or_closed':
                    self.selections.window_closed()
                    self.binding=None;self.geometry=None
                    self.set_activity('game_closed','等待 MuMu；回到游戏后自动连接，侧键可随时补查。')
                elif reason:self.set_activity('waiting_foreground','已暂停识别；回到 MuMu 后会自动继续。')
            return
        self.was_available=True
        if self.automatic.isChecked() and self.activity_code=='waiting_foreground':
            self.set_activity('watching_stage','已回到 MuMu，继续检查海克斯与装备选择。')
        if self.once_active and time.monotonic()>self.once_deadline and self.last_observation is None:
            self.once_active=False
            if not self.automatic.isChecked():self.invalidate()
        geometry=(current.rect,current.dpi)
        if geometry!=self.geometry:self.invalidate();self.geometry=geometry;self.binding=current
        if self.automatic.isChecked() and not self.offline and time.monotonic()-self.last_stage_probe>=3:self.probe_stage()
        if not self.once_ocr_pending and not self.offline:self.items.tick()
        if self.items.active or self.items.recognizing:return
        now=time.monotonic()
        # Keep already-visible ranks while a short verification capture finishes.
        # This never paints an old result, and a stalled worker still expires.
        checking=(self.capture_pending and self.rank_capture_started is not None
                  and now-self.rank_capture_started<=1.25 and now-self.last_capture<=2.75)
        if now-self.last_capture>1.5 and not checking:self.hide_overlays()
        capture_interval=.5 if self.last_observation else 1.0
        stage_active=self.automatic.isChecked() and (self.offline or self.last_observation is not None or time.monotonic()<self.stage_window_until)
        if (stage_active or self.once_active) and time.monotonic()-self.last_capture>capture_interval:
            self.request_capture()

    def load_comps(self,kind='',entity=None):
        if not self.versions_ready:return
        self.explorer_generation+=1;generation=self.explorer_generation;adapter=self.adapter
        self.browser.set_loading()
        def done(result):
            if generation!=self.explorer_generation or adapter is not self.adapter:return
            try:
                rows=result['data']['comps'] if kind else result['data']
                DataJ.validate_comps(rows)
                self.browser.set_result(rows,adapter.patch)
            except Exception:self.browser.set_error();return
        def failed(_):
            if generation==self.explorer_generation and adapter is self.adapter:self.browser.set_error()
        self.submit(self.network,lambda:adapter.explore(kind,entity) if kind else adapter.comps(),done,failed)

    def clear_explorer(self):self.browser.clear_filter()

    def run_explore(self,kind,entity):self.browser.set_filter(kind,entity)

    def select_comp(self,comp):
        if self.session.target==str(comp) and self.comp_detail:
            self.open_guide('https://www.dataj.cc/comp/'+str(comp));return
        self.comp_url.setText('https://www.dataj.cc/comp/'+str(comp));self.pin_comp()
        self.tabs.setCurrentIndex(2)

    def retry_comp(self):
        if self.session.target:self.select_comp(self.session.target)

    def browse_comp(self):
        try:parse_comp_url(self.comp_url.text())
        except ValueError as exc:self.status.setText(str(exc));return
        self.open_guide(self.comp_url.text())

    def open_latest_guide(self):
        if self.guide_requested_url:self.open_guide(self.guide_requested_url,allow_latest=True)

    def open_guide(self,url,*,allow_latest=False,reload=True):
        self.guide_requested_url=url;self.guide_allow_latest=allow_latest
        self.guide_empty.hide();self.guide_version.hide()
        latest=getattr(self,'latest_patch',None)
        if self.adapter.patch!=latest and not allow_latest:
            self.web.stop();self.web.hide();self.guide_version.show()
            pinned=self.comp_detail and str(self.comp_detail.get('compId'))==self.session.target
            self.guide_version_title.setText('已固定 · '+self.comp_detail.get('name',self.session.target) if pinned else '攻略版本说明')
            source=f'原站攻略为最新 {latest} 版本' if latest else '原站攻略使用最新版本，版本列表尚未确认'
            self.guide_version_note.setText(f'{source}，当前助手统计为 {self.adapter.patch}。\n可继续复制阵容码、查询出装和强化；查看最新攻略不会改变所选统计版本。')
            self.guide_latest.setText(f'查看原站最新攻略（{latest}）' if latest else '查看原站最新攻略')
            self.guide_notice.setText(('阵容已固定。' if pinned else '')+f'当前统计版本 {self.adapter.patch}，攻略版本需单独确认。')
            self.tabs.setCurrentIndex(2);return
        self.guide_notice.setText(f'原站攻略：{latest or "最新版本"} · 助手阵容码、强化与出装统计：{self.adapter.patch}。'+('网页内统计也属于原站最新版本。' if latest!=self.adapter.patch else ''))
        should_load=reload or self.web.isHidden() or self.web.url().toString()!=url
        self.web.show()
        if not self.offline and should_load:self.web.setUrl(QUrl(url))
        self.tabs.setCurrentIndex(2)

    def guide_url_changed(self,url):
        try:parse_comp_url(url.toString())
        except ValueError:return
        self.comp_url.setText(url.toString())

    def pin_comp(self):
        if not self.versions_ready:return
        try:comp=parse_comp_url(self.comp_url.text())
        except ValueError as exc:self.status.setText(str(exc));return
        self.session.set_target(comp);self.invalidate();self.clear_equipment();self.comp_detail=None
        self.heroes.blockSignals(True);self.heroes.clear();self.heroes.blockSignals(False)
        self.populate_hero_buttons()
        self.copy_button.setEnabled(False);self.web.stop();self.web.hide();self.web.setUrl(QUrl('about:blank'))
        self.guide_requested_url=None;self.guide_allow_latest=False
        self.guide_empty.hide();self.guide_version.hide();self.guide_retry.hide();self.guide_notice.setText('已选择阵容，正在读取攻略和阵容码…')
        self.browser.set_pinned(comp)
        self.comp_generation+=1;generation=self.comp_generation;adapter=self.adapter;session_id=self.session.session_id
        name=next((row['name'] for row in self.browser.rows if str(row['compId'])==comp),comp)
        self.target_label.setText('本局阵容：'+name+' · 正在读取')
        def current():
            return generation==self.comp_generation and session_id==self.session.session_id and adapter is self.adapter
        def failed(_):
            if not current():return
            self.guide_notice.setText('阵容详情暂时无法读取。请重试；旧阵容码与攻略已清除。');self.guide_retry.show()
            self.target_label.setText('本局阵容：'+name+' · 加载失败')
        def done(result):
            if not current():return
            detail=result['data']
            if not isinstance(detail,dict) or str(detail.get('compId'))!=comp:failed('scope');return
            self.comp_detail=detail;self.target_label.setText('本局阵容：'+detail.get('name',comp)+' · 已固定')
            self.heroes.blockSignals(True)
            for hero in detail.get('heroes',[]):self.heroes.addItem(hero['heroName'],str(hero['heroId']))
            self.heroes.blockSignals(False)
            self.populate_hero_buttons()
            code=detail.get('gameCode');self.copy_button.setEnabled(isinstance(code,str) and code.startswith('【阵容码】'))
            self.guide_notice.setText('已固定 · 强化与出装查询会跟随本阵容。'+('复制按钮对应主阵容。' if self.copy_button.isEnabled() else '来源暂无主阵容码。'))
            self.open_guide('https://www.dataj.cc/comp/'+comp)
            self.status.setText('已固定 '+detail.get('name',comp))
            self.items.prewarm(comp)
        self.submit(self.network,lambda:adapter.comp(comp),done,failed)

    def unpin(self):
        self.comp_generation+=1
        self.session.set_target(None);self.invalidate();self.comp_detail=None;self.target_label.setText('本局阵容：未固定')
        self.copy_button.setEnabled(False);self.browser.set_pinned(None)
        self.heroes.blockSignals(True);self.heroes.clear();self.heroes.blockSignals(False);self.clear_equipment()
        self.populate_hero_buttons()
        self.equip_note.setText('先选一套阵容，再点击英雄头像查看出装。')
        self.guide_requested_url=None;self.guide_allow_latest=False
        self.web.stop();self.web.setUrl(QUrl('about:blank'));self.web.hide();self.guide_empty.show();self.guide_version.hide();self.guide_retry.hide()
        self.guide_notice.setText('先在阵容列表选择一套阵容。')

    def copy_code(self):
        code=self.comp_detail.get('gameCode') if self.comp_detail else None
        if isinstance(code,str) and code.startswith('【阵容码】'):
            QApplication.clipboard().setText(code);self.status.setText('已复制固定阵容的主阵容码；未声明对应网页中正在浏览的变体')
        else:self.status.setText('请先固定一个提供阵容码的阵容')

    def clear_equipment(self,*_):
        self.equip_generation+=1
        if hasattr(self,'equip_table'):self.equip_table.setRowCount(0)
        if hasattr(self,'equip_note'):self.equip_note.setText('点击本局阵容的英雄头像查看出装。' if self.session.target else '先选一套阵容，再点击英雄头像查看出装。')

    def query_equipment(self,*_):
        if not self.versions_ready:return
        comp=self.session.target;hero=self.heroes.currentData()
        if not comp or not hero:self.status.setText('请先固定阵容并选择英雄');return
        self.clear_equipment();generation=self.equip_generation;adapter=self.adapter
        self.equip_note.setText('正在读取本局阵容下 '+self.heroes.currentText()+' 的装备统计…')
        form=self.equip_form.currentText();kind=self.equip_type.currentText()
        hero_name=self.heroes.currentText();catalog={str(x['id']):x for x in self.catalog.get('equip',[])}
        def done(result):
            if generation!=self.equip_generation or adapter is not self.adapter:return
            data=result['data']
            if str(data.get('compId'))!=comp or str(data.get('heroId'))!=hero:self.status.setText('出装响应对象不匹配');return
            rows=data.get('heroEquips' if form=='单件' else 'hero3Equips',[])
            selected=[]
            for row in rows:
                count=row.get('sampleCount')
                if type(count) is not int or count<COMP_MIN_SAMPLE:continue
                equips=row.get('equips',[])
                if kind!='全部' and not any(catalog.get(str(e['id']),{}).get('type')==kind for e in equips):continue
                selected.append(['/'.join(e['name'] for e in equips),row.get('avgPlacement','—'),row.get('sampleCount','—')])
            selected.sort(key=lambda r:r[1] if isinstance(r[1],(int,float)) else 99)
            fill_table(self.equip_table,selected)
            self.equip_note.setText(f'{self.target_label.text()} · {hero_name} · {form} · {kind}（三件套按包含筛选） · 样本≥{COMP_MIN_SAMPLE}局' + (' · 暂无达标数据' if not selected else ''))
        self.submit(self.network,lambda:adapter.equipment(comp,hero),done,lambda _:self.equip_note.setText('出装读取失败，请重试。') if generation==self.equip_generation else None)

    def shutdown(self):
        if not self.offline:
            self.mouse_settings.setValue('panel_geometry',self.saveGeometry())
            self.mouse_settings.setValue('mark_position',self.mark.pos());self.mouse_settings.sync()
        self.timer.stop();self.hide_overlays();self.mark.hide()
        self.items.shutdown()
        for pool in (self.capture_pool,self.ocr_pool,self.network):pool.clear();pool.waitForDone()


def main():
    from contextlib import nullcontext
    from single_instance import SingleInstance
    parser=argparse.ArgumentParser();parser.add_argument('--self-test',action='store_true');parser.add_argument('--seconds',type=int,default=0)
    parser.add_argument('--start-collapsed',action='store_true',help='启动时只显示左上角展开标记')
    args=parser.parse_args()
    # Diagnostic widgets remain runnable while the ordinary companion is active.
    with (nullcontext(True) if args.self_test else SingleInstance()) as acquired:
        if not acquired:
            print('助手已运行，跳过重复启动。',flush=True)
            return 0
        win.enable_dpi()
        app=QApplication(sys.argv[:1]);app.setQuitOnLastWindowClosed(False)
        panel=Companion(offline=args.self_test)
        registered=[]
        mouse=MouseShortcut(panel)
        mouse.released.connect(panel.mouse_capture,Qt.ConnectionType.QueuedConnection)
        mouse.left_event.connect(panel.selections.on_mouse,Qt.ConnectionType.QueuedConnection)
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
            if not panel.reopen_shortcut_available:panel.status.setText('展开快捷键被占用。收起后，可点击左上角「阵容助手 · 展开」重新打开。')
            elif len(registered)!=3:panel.status.setText('部分快捷键被占用，可以使用面板按钮。')
            if not mouse.start():panel.status.setText('鼠标侧键监听不可用，请用截图按钮或 Ctrl+Alt+F10。')
            panel.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,True)
            area=app.primaryScreen().availableGeometry()
            if panel.mouse_settings.value('panel_geometry') is None:panel.move(area.left()+64,area.top()+12)
            saved_mark=panel.mouse_settings.value('mark_position')
            if saved_mark is not None and area.contains(saved_mark):panel.mark.move(saved_mark)
            else:panel.mark.move(area.left()+12,area.top()+12)
            panel.mark.show()
            if not args.start_collapsed:panel.show()
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
