"""Repeatable Windows/Qt manual-trigger replay; never operates the game.

Uses a local real game frame and frozen statistics. Timings are a benchmark,
not a machine-dependent unit-test threshold. No settings or cache are retained.
"""
import argparse
from contextlib import ExitStack
import ctypes as c
from ctypes import wintypes as w
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'outputs/companion'))
from PIL import Image


class Counters(c.Structure):
    _fields_=[('cb',w.DWORD),('PageFaultCount',w.DWORD)]+[(k,c.c_size_t) for k in
        ['PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
         'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage']]


def memory():
    kernel=c.WinDLL('kernel32');kernel.GetCurrentProcess.restype=w.HANDLE
    psapi=c.WinDLL('psapi');psapi.GetProcessMemoryInfo.argtypes=[w.HANDLE,c.POINTER(Counters),w.DWORD]
    value=Counters();value.cb=c.sizeof(value)
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(),c.byref(value),value.cb):raise c.WinError()
    return {name:round(getattr(value,field)/1024**2,2) for name,field in
            [('working_set_mib','WorkingSetSize'),('private_mib','PrivateUsage'),('peak_working_set_mib','PeakWorkingSetSize')]}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',type=Path,default=ROOT/'work/user-game-sample/new-round/before.png')
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--repeat',type=int,default=8)
    parser.add_argument('--fresh',action='store_true',help='Clear choices each iteration to measure new-choice recognition')
    parser.add_argument('--captures',type=int,default=20)
    parser.add_argument('--copy-frames',action='store_true',help='Allocate a fresh full-size image for each simulated screen capture')
    parser.add_argument('--baseline-ref',help='Load the four changed runtime modules from a pinned local Git commit; never changes the checkout')
    args=parser.parse_args()
    revision=subprocess.check_output(['git','rev-parse',args.baseline_ref or 'HEAD'],cwd=ROOT,text=True).strip()
    if args.baseline_ref:
        # Dependencies not in this list are unchanged by this optimization.
        import bootstrap
        for name in ['vision','item_vision','item_controller','app']:
            filename='outputs/companion/'+name+'.py'
            source=subprocess.check_output(['git','show',revision+':'+filename],cwd=ROOT).decode('utf8')
            module=ModuleType(name);module.__file__=str(ROOT/filename);sys.modules[name]=module
            exec(compile(source,module.__file__,'exec'),module.__dict__)
    from app import Companion, QApplication, QTimer
    from integration_check import FrozenSource
    import app
    import item_controller
    qt=QApplication.instance() or QApplication([])
    report={'image_sha256':hashlib.sha256(args.image.read_bytes()).hexdigest(),'repeat':args.repeat,
            'scenario':'new_choice' if args.fresh else 'same_choice_refresh',
            'source_revision':revision,'runtime_source':'pinned Git modules' if args.baseline_ref else 'working tree',
            'fresh_frame_per_capture':args.copy_frames,'watch_captures':args.captures,
            'memory_scope':'Main Python process only; excludes QtWebEngine children and game',
            'limits':'In-memory real screenshot; frozen statistics; native placement replaced. Excludes real screen capture, network and game FPS.',
            'memory':{'imports':memory()}}
    with tempfile.TemporaryDirectory() as tmp,ExitStack() as stack:
        for module in ['app','dataj','comp_browser']:stack.enter_context(patch(module+'.STATE_DIR',Path(tmp)))
        stack.enter_context(patch('app.win.enumerate_mumu',return_value=[]))
        p=Companion(offline=True);p.timer.stop();p.hide();p.adapter=FrozenSource()
        report['memory']['ui']=memory()
        p.vision.prepare();report['memory']['ocr_ready']=memory()
        frame=Image.open(args.image).convert('RGB')
        binding=SimpleNamespace(hwnd=123,pid=123,process='MuMuNxDevice.exe',rect=(0,0,*frame.size),dpi=96)
        p.binding=binding;p.geometry=(binding.rect,96);p.automatic.setChecked(False)
        for target,value in [('app.win.describe',binding),('app.win.same_target',True),('app.win.foreground_root',123),
                             ('app.win.user.SetForegroundWindow',True)]:
            stack.enter_context(patch(target,return_value=value))
        stack.enter_context(patch('app.capture_image',side_effect=lambda _:(frame.copy() if args.copy_frames else frame,binding)))
        placements=[];gaps=[];last=[time.perf_counter()];gui=threading.get_ident();spans={}
        def heartbeat():
            now=time.perf_counter();gaps.append((now-last[0])*1000);last[0]=now
        timer=QTimer();timer.setInterval(5);timer.timeout.connect(heartbeat);timer.start()
        for overlay in p.overlays:overlay.place=lambda *a:placements.append(time.perf_counter())
        def measured(name,fn):
            def call(*a,**kw):
                start=time.perf_counter()
                try:return fn(*a,**kw)
                finally:spans.setdefault(name+('_gui' if threading.get_ident()==gui else '_worker'),[]).append((time.perf_counter()-start)*1000)
            return call
        stack.enter_context(patch('item_controller.item_boxes',measured('item_boxes',item_controller.item_boxes)))
        stack.enter_context(patch('app.tracked_signature',measured('signature',app.tracked_signature)))
        def settle(predicate):
            end=time.perf_counter()+10
            while not predicate() and time.perf_counter()<end:qt.processEvents();time.sleep(.001)
            if not predicate():raise AssertionError('Replay timeout: '+str(p.activity_code))
        cpu=time.process_time();start_all=time.perf_counter();manual=[]
        for _ in range(args.repeat):
            if args.fresh:p.invalidate()
            placements.clear();start=time.perf_counter();p.capture_once()
            settle(lambda:bool(placements) and not p.jobs and not p.once_ocr_pending)
            manual.append((placements[0]-start)*1000)
            assert p.stats_payload and any('局' in r[1] for r in p.stats_payload['rows'])
        report['memory']['after_manual']=memory()
        for _ in range(args.captures):
            p.request_capture();settle(lambda:not p.jobs and not p.capture_pending)
        report['memory']['after_watch']=memory()
        report['process_cpu_seconds']=round(time.process_time()-cpu,3)
        report['wall_seconds']=round(time.perf_counter()-start_all,3)
        timer.stop()
        p.invalidate();report['memory']['invalidated']=memory()
        report['full_frame_retained_after_invalidate']=p.last_frame is not None
        def summary(values):
            return {'count':len(values),'median_ms':round(statistics.median(values),2),'max_ms':round(max(values),2)} if values else {}
        report['manual']=summary(manual);report['manual_samples_ms']=[round(v,2) for v in manual]
        report['gui_heartbeat_gap']=summary(gaps);report['spans']={k:summary(v) for k,v in spans.items()}
        p.shutdown()
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
