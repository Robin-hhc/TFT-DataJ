"""One foreground capture for a side-key request; exclusive scene routing."""
import time
from PySide6.QtCore import QTimer
from vision import capture_image
import win_capture as win
from condition_reader import ConditionReader


def window_context(binding):
    return (binding.hwnd,binding.pid,tuple(binding.rect),binding.dpi)


class ConditionController:
    def __init__(self,panel):
        self.panel=panel;self.reader=None;self.generation=0

    def configure(self):
        self.reader=ConditionReader(self.panel.vision,self.panel.entity_resolver)
        self.generation+=1

    def token(self):
        p=self.panel
        return (self.generation,p.condition_generation,p.explorer_generation,p.session.session_id,
                id(p.adapter),p.browser.input_revision,p.browser.scope,window_context(p.binding) if p.binding else None)

    def accepts(self,token):
        p=self.panel
        if self.token()!=token or not p.binding:return False
        current=win.describe(p.binding.hwnd)
        return bool(current and window_context(current)==token[-1]
                    and win.foreground_root()==p.binding.hwnd)

    def trigger(self):
        p=self.panel
        if not p.versions_ready or not p.catalog or self.reader is None:return
        if p.capture_pending or p.ocr_busy or p.stage_probe_pending:return
        current=win.describe(p.binding.hwnd) if p.binding else None
        if not p.binding or not win.same_target(p.binding,current):
            p.refresh_windows()
            if p.windows.count()!=1:
                p.browser.input_bar.show_note('没有找到唯一的 MuMu 游戏窗口，请在设置中绑定。');return
            p.bind_window()
            current=p.binding
        if not p.binding:return
        if window_context(current)!=window_context(p.binding):p.condition_generation+=1
        p.binding=current;p.geometry=(current.rect,current.dpi)
        p.selections.binding_changed(current)
        needs_return=p.panel_open() or win.foreground_root()!=p.binding.hwnd
        if needs_return and p.return_to_game() is False:return
        token=self.token();binding=p.binding;started=time.monotonic()
        p.capture_pending=True
        def failure_note():
            if self.accepts(token):
                p.browser.input_bar.show_note('未读到清晰详情，请打开名称详情后再按侧键。')
                p.mark.button.setToolTip('未读到详情：打开名称详情后再按侧键')
                p.mark.button.show_feedback('未读到详情')
        def capture_failed(_):
            p.capture_pending=False;failure_note()
        def read_failed(_):
            p.ocr_busy=False;failure_note()
        def read_done(result):
            p.ocr_busy=False
            if not self.accepts(token):return
            route=result.get('route')
            if route=='augment_stats':
                p.once_active=True;p.once_deadline=time.monotonic()+30;p.once_ocr_pending=True
                p.captured((frame[0],binding),True,captured_at=frame[1]);return
            if route=='equipment_stats':
                p.items.ingest(frame[0],binding,force=True,frame_time=frame[1]);return
            bar=p.browser.input_bar
            if route=='detail' and result.get('status')=='resolved':
                entity=result.get('entity') or {}
                resolved=p.entity_resolver.resolve_any(entity.get('name',''))
                kind=entity.get('kind') or resolved.kind
                if not p.browser.set_filter(kind,entity,can_confirm=True):return
                bar.show_note('已读取名称；若这项已选中，可点击「记为本局已选」。')
            elif route=='detail' and result.get('status')=='ambiguous':
                bar.show_alternatives(result.get('candidates',[]))
                bar.show_note('名称对应多个形态或品质，请确认；无法区分的项目不会加入检索。')
            else:
                failure_note()
                return
            p.tabs.setCurrentIndex(1);p.showNormal();p.raise_();p.activateWindow()
            self.last_elapsed_ms=round((time.monotonic()-started)*1000,2)
        frame=[None,None]
        def captured(capture_result):
            result,frame_time=capture_result
            p.capture_pending=False
            if not self.accepts(token) or window_context(result[1])!=token[-1]:return
            frame[0]=result[0];frame[1]=frame_time;p.ocr_busy=True;reader=self.reader
            p.submit(p.ocr_pool,lambda:reader.read(frame[0]),read_done,read_failed)
        def begin():
            if not self.accepts(token):p.capture_pending=False;return
            def capture():
                result=capture_image(binding)
                return result,time.monotonic()
            p.submit(p.capture_pool,capture,captured,capture_failed)
        QTimer.singleShot(100 if needs_return else 0,begin)
