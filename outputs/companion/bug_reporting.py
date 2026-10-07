"""Bounded background bug evidence from already authorized game captures."""
from copy import deepcopy
import hashlib
import time

from PySide6.QtCore import QThreadPool, QTimer, QUrl
from PySide6.QtGui import QDesktopServices

from bootstrap import STATE_DIR
from bug_cases import BugCaseStore
from diagnostics import record
from snapshot_stats import STAGES
from vision import capture_image
import win_capture as win


class BugReporter:
    def __init__(self, panel, *, store=None, enabled=True):
        self.panel=panel
        self.enabled=enabled
        self.store=store if store is not None else BugCaseStore(STATE_DIR/'bug-cases')
        self.pool=QThreadPool();self.pool.setMaxThreadCount(1)
        self.pending=False;self.manual_pending=False
        self.last_request=float('-inf')
        self.seen=set()
        self.last_status=None
        self.closed=False

    def context(self, domain, frame_scope):
        p=self.panel
        return {'set_id':p.adapter.set_id,'patch':p.adapter.patch,'target':p.session.target,
                'session_id':p.session.session_id,'domain':domain,'source':'bound_game',
                'frame_scope':frame_scope}

    def capture(self, reason, observation, image, *, domain='hex', frame_scope='full_game',
                evidence=None, manual=False):
        p=self.panel
        if not self.enabled or self.closed or image is None or not p.binding:return False
        if str(getattr(p.binding,'process','')).lower()!='mumunxdevice.exe':return False
        if tuple(image.size)!=(p.binding.rect[2]-p.binding.rect[0],p.binding.rect[3]-p.binding.rect[1]):return False
        context=self.context(domain,frame_scope)
        key=self.store.fingerprint(observation,reason,context)
        now=time.monotonic()
        if key in self.seen or self.pending or (not manual and now-self.last_request<15):return False
        if len(p.jobs)>=8:return False
        kinds=('hex','equip','hero','trait') if domain=='condition' else ('equip' if domain=='item' else 'hex',)
        details={'catalog':{kind:p.catalog.get(kind,[]) for kind in kinds},**(evidence or {})}
        observation,context,details=deepcopy((observation,context,details))
        self.pending=True;self.last_request=now
        def done(result):
            self.pending=False
            status=result.get('status','error')
            if status in ('saved','duplicate'):
                self.seen.add(key)
                if len(self.seen)>256:self.seen={key}
            record('bug_case',status=status,reason=reason,case_id=result.get('case_id'))
            if manual or (status in ('limit','error') and status!=self.last_status):
                message={'saved':'问题画面已保存在本机，核对后可加入原图回归验证。',
                         'duplicate':'同类问题已有原图记录，已保留之前的样本。',
                         'limit':'问题记录已达容量上限；旧样本已保留，请在问题记录文件夹整理。',
                         'error':'问题画面保存失败，正常识别不受影响；请检查磁盘空间。'}
                p.status.setText(message.get(status,message['error']))
            self.last_status=status
        def failed(_):done({'status':'error'})
        p.submit(self.pool,lambda:self.store.save(image,observation,reason=reason,context=context,evidence=details),done,failed)
        return True

    def observed_hex(self, observation, image):
        if observation.get('scene') not in ('choice_candidates','choice_unresolved'):return False
        if len(observation.get('cards',[]))!=3:return False
        if any(not c.get('resolution',{}).get('id') for c in observation['cards']):
            return self.capture('hex_unresolved',observation,image)
        if observation.get('round') not in STAGES:
            return self.capture('hex_stage_unconfirmed',observation,image)
        return False

    def hex_statistics(self, reason, *, evidence=None):
        p=self.panel
        if (not p.last_observation or p.last_frame is None or not p.binding
            or time.monotonic()-p.last_capture>1.5 or win.foreground_root()!=p.binding.hwnd):return False
        return self.capture(reason,p.last_observation,p.last_frame,evidence=evidence)

    def observed_items(self, observation, image, *, frame_scope):
        cards=observation.get('cards',[])
        confirmed_header=(observation.get('scene')=='item_candidates'
                          or observation.get('reason')=='excluded_or_unconfirmed')
        if (not confirmed_header or len(cards) not in (3,4,5)
            or any(c.get('resolution',{}).get('status')=='excluded' for c in cards)
            or not any(not c.get('resolution',{}).get('id') for c in cards)):return False
        return self.capture('item_unresolved',observation,image,domain='item',frame_scope=frame_scope)

    def item_statistics(self, reason, *, evidence=None):
        p=self.panel;items=p.items
        if (not items.observation or items.last_frame is None or not items.active
            or not items.available() or not items.fresh(time.monotonic())):return False
        return self.capture(reason,items.observation,items.last_frame,domain='item',
                            frame_scope=items.frame_scope,evidence=evidence)

    def observed_condition(self, result, image):
        """Report a failed explicit take-condition request after caller token checks."""
        if (result.get('route') in ('augment_stats','equipment_stats')
            or result.get('status') in ('resolved','ambiguous')):return False
        return self.capture('condition_unresolved',result,image,domain='condition',
                            frame_scope='full_game',
                            evidence={'user_triggered':True,'trigger':'take_condition'})

    def open_folder(self):
        directory=STATE_DIR/'bug-cases'
        try:
            directory.mkdir(parents=True,exist_ok=True)
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory))):
                self.panel.status.setText('无法打开问题记录文件夹，请检查本机文件管理器。')
        except OSError:self.panel.status.setText('无法创建问题记录文件夹，请检查磁盘空间与写入权限。')

    def manual_report(self):
        p=self.panel
        if self.closed:return
        if not self.enabled:
            p.status.setText('演示或测试模式不会保存游戏问题样本。');return
        if self.pending or self.manual_pending or p.capture_pending or p.ocr_busy:
            p.status.setText('当前任务尚未完成，请稍后再记录问题。');return
        if not p.versions_ready or not p.catalog:
            p.status.setText('正在准备数据，请稍后再记录问题。');return
        if not p.binding or not win.same_target(p.binding,win.describe(p.binding.hwnd)):
            p.refresh_windows()
            if p.windows.count()!=1:
                p.status.setText('没有找到唯一的 MuMu 游戏窗口，未保存其他画面。');return
            p.bind_window()
        if not p.binding:return
        if p.return_to_game() is False:return
        token=p.session.token();binding=p.binding
        self.manual_pending=True;p.capture_pending=True
        def done(result):
            self.manual_pending=False;p.capture_pending=False
            if not p.session.accepts(token) or win.foreground_root()!=binding.hwnd:return
            image,current,domain,frame_id=result
            if not win.same_target(binding,current):return
            observation={'scene':'unknown','round':None,'cards':[],
                         'image_size':list(image.size),'reason':'manual_report'}
            observation['manual_frame_id']=frame_id
            self.capture('manual_report',observation,image,domain=domain,manual=True,
                         evidence={'user_reported':True,'automatic_scene_confirmed':False})
        def failed(_):
            self.manual_pending=False;p.capture_pending=False
            p.status.setText('未能读取 MuMu 游戏画面，没有保存桌面或其他窗口。')
        def capture():
            from item_controller import inspect_items
            image,current=capture_image(binding)
            domain='item' if inspect_items(image)[0] else 'hex'
            frame_id=hashlib.sha256(image.tobytes()).hexdigest()
            return image,current,domain,frame_id
        def begin():
            if self.closed:
                self.manual_pending=False;p.capture_pending=False;return
            p.submit(p.capture_pool,capture,done,failed)
        QTimer.singleShot(100,begin)

    def shutdown(self):
        self.closed=True
        if self.manual_pending:self.manual_pending=False;self.panel.capture_pending=False
        self.pool.clear();self.pool.waitForDone()
