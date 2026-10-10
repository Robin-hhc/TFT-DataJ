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
        self.active=False;self.pending=None
        self.pending_timer=QTimer(panel)
        self.pending_timer.setInterval(25)
        self.pending_timer.timeout.connect(self.resume_pending)

    def background_probe_busy(self):
        p=self.panel
        return not self.active and not p.ocr_busy and (p.items.probing or p.stage_probe_pending)

    def cancel_pending(self):
        self.pending=None;self.pending_timer.stop()

    def feedback(self,message,caption):
        p=self.panel
        p.browser.input_bar.show_note(message)
        p.mark.button.setToolTip(message)
        p.mark.button.show_feedback(caption)

    def resume_pending(self):
        if self.pending is None:return False
        token,binding,deadline=self.pending
        if not self.accepts(token):
            self.cancel_pending()
            self.feedback('取条件请求已取消，请在当前画面重新触发。','取条件已取消')
            return False
        if time.monotonic()>=deadline:
            self.cancel_pending()
            self.feedback('后台截图等待超时，请再次取条件；原检索条件已保留。','取条件超时')
            return False
        p=self.panel
        if p.capture_pending or p.ocr_busy or p.stage_probe_pending:return False
        self.cancel_pending()
        self.start_capture(binding,token,time.monotonic(),False)
        return self.active

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
        if self.pending is not None:
            self.resume_pending()
            if self.pending is not None or self.active:return
        busy=p.capture_pending or p.ocr_busy or p.stage_probe_pending
        if busy and not self.background_probe_busy():return
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
        if busy:
            self.pending=(token,binding,started+2.0);self.pending_timer.start()
            self.feedback('正在等待后台截图，随后读取当前详情。','等待取条件')
            return
        self.start_capture(binding,token,started,needs_return)

    def start_capture(self,binding,token,started,needs_return):
        p=self.panel
        self.active=True
        p.capture_pending=True
        def failure_note(result=None):
            if self.accepts(token):
                reason=(result or {}).get('reason')
                message={
                    'no_verified_detail_panel':'未找到详情窗口，请在游戏点开装备或英雄详情后按侧键。',
                    'detail_header_icon_unconfirmed':'详情图标区域未读清，请重新打开详情后按侧键。',
                    'title_touches_boundary':'详情名称未完整显示，请重新打开详情后按侧键。',
                    'primary_title_unconfirmed':'未读清详情名称，请保持详情可见后按侧键。',
                }.get(reason,'未读到清晰详情，请打开名称详情后再按侧键。')
                p.browser.input_bar.show_note(message+' 原检索条件已保留。')
                p.mark.button.setToolTip('未读到详情：打开名称详情后再按侧键')
                p.mark.button.show_feedback('未读到详情')
        def capture_failed(_):
            self.active=False;p.capture_pending=False;failure_note()
        def read_failed(_):
            self.active=False;p.ocr_busy=False
            if self.accepts(token):
                p.bugs.observed_condition({'scene':'unknown','route':'none','status':'error',
                    'reason':'condition_ocr_failed','evidence':{}},frame[0])
            failure_note()
        def read_done(result):
            self.active=False;p.ocr_busy=False
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
                bar.show_note('已读取名称并按此条件检索；若本局已选中此项，可点击「记为已选」。')
            elif route=='detail' and result.get('status')=='ambiguous':
                bar.show_alternatives(result.get('candidates',[]))
                bar.show_note('名称对应多个形态或品质，请确认；无法区分的项目不会加入检索。')
            else:
                p.bugs.observed_condition(result,frame[0])
                failure_note(result)
                return
            p.tabs.setCurrentIndex(1);p.showNormal();p.raise_();p.activateWindow()
            self.last_elapsed_ms=round((time.monotonic()-started)*1000,2)
        frame=[None,None]
        def captured(capture_result):
            result,frame_time=capture_result
            p.capture_pending=False
            if not self.accepts(token) or window_context(result[1])!=token[-1]:
                self.active=False;return
            frame[0]=result[0];frame[1]=frame_time;p.ocr_busy=True;reader=self.reader
            p.submit(p.ocr_pool,lambda:reader.read(frame[0]),read_done,read_failed)
        def begin():
            if not self.accepts(token):self.active=False;p.capture_pending=False;return
            def capture():
                result=capture_image(binding)
                return result,time.monotonic()
            p.submit(p.capture_pool,capture,captured,capture_failed)
        QTimer.singleShot(100 if needs_return else 0,begin)
