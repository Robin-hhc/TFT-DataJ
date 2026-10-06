"""Profile the real Qt side-key condition path with local images and frozen HTTP.

No game is captured or controlled. Capture returns a fresh copy of a labelled
original image; HTTP is an httpx.MockTransport. Timings exclude real capture,
network latency, native mouse-hook delivery, and game FPS.
"""
import argparse
from contextlib import ExitStack
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch
import weakref

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'outputs/companion'))
from PIL import Image
import httpx


def summary(values):
    if not values:
        return {'count': 0}
    ordered = sorted(values)
    return {'count': len(values), 'median_ms': round(statistics.median(values), 2),
            'p95_ms': round(ordered[min(len(ordered)-1, int(len(ordered)*.95))], 2),
            'max_ms': round(max(values), 2)}


def process_tree_memory():
    """One numeric PID snapshot; do not return private process command lines."""
    command = (
        "$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[Text.UTF8Encoding]::new(); "
        "$rows=Get-CimInstance Win32_Process | Select-Object "
        "@{n='pid';e={[long]$_.ProcessId}},@{n='parent_pid';e={[long]$_.ParentProcessId}},"
        "@{n='working_set_bytes';e={[long]$_.WorkingSetSize}},"
        "@{n='private_page_count_bytes';e={[long]$_.PrivatePageCount}},Name; "
        "ConvertTo-Json -InputObject @($rows) -Compress"
    )
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                            check=True, capture_output=True, encoding='utf-8', timeout=20)
    rows = json.loads(result.stdout)
    tree = {os.getpid()}
    while True:
        descendants = {row['pid'] for row in rows if row['parent_pid'] in tree}
        if descendants <= tree:
            break
        tree.update(descendants)
    # The snapshot helper itself is a child; include only the application and
    # its QtWebEngine descendants, not PowerShell's own measurement footprint.
    members = [row for row in rows if row['pid'] in tree and
               (row['pid'] == os.getpid() or row['Name'].lower() == 'qtwebengineprocess.exe')]
    children = [row for row in members if row['pid'] != os.getpid()]
    if not children:
        raise AssertionError('Local WebEngine warm-up did not create a measurable child process')
    return {'scope': 'Main Python process plus all descendant QtWebEngineProcess.exe instances',
            'sampling': 'One after-warm Get-CimInstance Win32_Process numeric PID/parent snapshot',
            'working_set_limit': 'Working sets are summed; shared pages can be counted more than once',
            'processes': members,
            'working_set_sum_mib': round(sum(row['working_set_bytes'] for row in members)/1024**2, 2),
            'private_page_count_sum_mib': round(sum(row['private_page_count_bytes'] for row in members)/1024**2, 2)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalogue', type=Path, default=ROOT/'work/s18-refresh-20260926/catalog.json')
    parser.add_argument('--inventory-image', type=Path,
                        default=ROOT/'work/input-experiments/match-20261006/selected-book-native.png')
    parser.add_argument('--hero-image', type=Path, default=ROOT/'work/condition-input-experiment/next-507s.png')
    parser.add_argument('--repeat', type=int, default=8)
    parser.add_argument('--idle-seconds', type=float, default=10)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if not 5 <= args.repeat <= 10:
        parser.error('--repeat must be between 5 and 10')
    if args.idle_seconds < 10:
        parser.error('--idle-seconds must be at least 10')
    catalog = json.loads(args.catalogue.read_text(encoding='utf-8'))
    catalog = catalog.get('data', catalog)
    report = {
        'claim': 'Actual Companion.mouse_capture -> ConditionController -> real Qt capture/OCR pools -> real widgets and single-condition DataJ HTTP body',
        'limits': ['Capture is replaced by a fresh copy of each local original screenshot; real screen capture latency is excluded.',
                   'HTTP is frozen with httpx.MockTransport; no real network latency, game FPS, native mouse hook or complete end-to-end P95 guarantee.',
                   'Native window show/activation is replaced; the timing endpoint is an accepted real widget condition, not pixels painted on screen.',
                   'Idle test uses manual-trigger mode with automatic game watching paused and no active choice; it is not the automatic stage watcher.',
                   'WebEngine memory is warmed with a local HTML fixture on the existing profile, not a full online DataJ guide page.',
                   'Development screenshot replays do not measure recognition generalisation.'],
        'revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'source_sha256': {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
                          ['outputs/companion/app.py', 'outputs/companion/condition_controller.py',
                           'outputs/companion/condition_reader.py', 'outputs/companion/entity_identity.py']},
        'catalogue_sha256': hashlib.sha256(args.catalogue.read_bytes()).hexdigest(),
        'logical_cpu_count': os.cpu_count(), 'repeat_per_image': args.repeat,
    }
    with tempfile.TemporaryDirectory(prefix='tft-condition-profile-') as temporary, ExitStack() as stack:
        import bootstrap
        stack.enter_context(patch.object(bootstrap, 'STATE_DIR', Path(temporary)))
        import app
        from app import Companion, QApplication, QTimer, QUrl, Qt
        from PySide6.QtCore import QEventLoop
        from PySide6.QtWebEngineCore import QWebEnginePage
        from dataj import DataJ
        for module in ['app', 'dataj', 'comp_browser']:
            stack.enter_context(patch(module+'.STATE_DIR', Path(temporary)))
        requests = []

        def response(request):
            body = json.loads(request.content) if request.method == 'POST' else None
            requests.append({'path': request.url.path, 'body': body})
            data = {'comps': []} if body else []
            return httpx.Response(200, json={'success': True, 'code': 200, 'data': data})

        class FrozenDataJ(DataJ):
            def __init__(self, patch='18.2a'):
                super().__init__(patch=patch, db=Path(temporary)/'frozen.sqlite', transport=httpx.MockTransport(response))

            def request(self, path, body=None, ttl=900, **extra):
                self.next_request = 0
                return super().request(path, body=body, ttl=0, **extra)

        stack.enter_context(patch('app.DataJ', FrozenDataJ))
        stack.enter_context(patch('app.win.enumerate_mumu', return_value=[]))
        qt = QApplication.instance() or QApplication([])
        p = Companion(offline=True, offline_catalog=catalog)
        p.timer.stop();p.hide();p.automatic.setChecked(False)
        frames = []
        for name, path, kind, identity in [('inventory_4k_gold_pan', args.inventory_image, 'equip', '1010'),
                                         ('hero_original_karma', args.hero_image, 'hero', '1510')]:
            with Image.open(path) as image:
                frames.append({'name': name, 'path': path, 'kind': kind, 'id': identity,
                               'image': image.convert('RGB')})
        current = {'frame': frames[0]}
        binding = lambda: SimpleNamespace(hwnd=707, pid=707, process='MuMuNxDevice.exe',
                                          rect=(0, 0, *current['frame']['image'].size), dpi=96)
        p.binding = binding();p.geometry = (p.binding.rect, p.binding.dpi)
        stack.enter_context(patch('app.win.describe', new=lambda _: binding()))
        stack.enter_context(patch('app.win.same_target', new=lambda *_: True))
        stack.enter_context(patch('app.win.foreground_root', new=lambda: 707))
        stack.enter_context(patch('app.game_windows', new=lambda: [binding()]))
        stack.enter_context(patch.object(p, 'panel_open', new=lambda: False))
        for name in ['showNormal', 'raise_', 'activateWindow']:
            stack.enter_context(patch.object(p, name, new=lambda: None))
        counters = {'capture_jobs': 0, 'ocr_jobs': 0, 'network_jobs': 0, 'capture_copies': 0,
                    'reader_calls': 0, 'native_ocr_engine_calls': 0}
        spans = {};references = [];accepted = [];gaps = [];reader_results = []
        gui_thread = threading.get_ident();original_submit = p.submit

        def submit(pool, fn, done, failed=None):
            counters['capture_jobs' if pool is p.capture_pool else 'ocr_jobs' if pool is p.ocr_pool else 'network_jobs'] += 1
            return original_submit(pool, fn, done, failed)

        stack.enter_context(patch.object(p, 'submit', new=submit))

        def capture(_):
            counters['capture_copies'] += 1
            started = time.perf_counter()
            image = current['frame']['image'].copy()
            references.append(weakref.ref(image))
            spans.setdefault('replacement_capture_copy_worker_ms', []).append((time.perf_counter()-started)*1000)
            return image, binding()

        stack.enter_context(patch('condition_controller.capture_image', new=capture))
        prepare_started = time.perf_counter();p.vision.prepare()
        report['ocr_prepare_ms'] = round((time.perf_counter()-prepare_started)*1000, 2)
        engine = p.vision.engine

        def engine_call(*a, **kw):
            counters['native_ocr_engine_calls'] += 1
            return engine(*a, **kw)

        stack.enter_context(patch.object(p.vision, 'engine', new=engine_call))
        original_read = p.conditions.reader.read

        def read(image):
            counters['reader_calls'] += 1
            started = time.perf_counter()
            result = original_read(image)
            spans.setdefault('reader_worker_ms', []).append((time.perf_counter()-started)*1000)
            reader_results.append({'status': result['status'], 'route': result['route'],
                                   'entity_id': (result.get('entity') or {}).get('id'),
                                   'readings': result['evidence'].get('readings'),
                                   'thread_is_gui': threading.get_ident() == gui_thread})
            return result

        stack.enter_context(patch.object(p.conditions.reader, 'read', new=read))
        original_filter = p.browser.set_filter

        def set_filter(*a, **kw):
            started = time.perf_counter()
            result = original_filter(*a, **kw)
            spans.setdefault('set_filter_gui_ms', []).append((time.perf_counter()-started)*1000)
            if result:
                accepted.append(time.perf_counter())
            return result

        stack.enter_context(patch.object(p.browser, 'set_filter', new=set_filter))

        def settle(predicate, timeout=10):
            deadline = time.perf_counter()+timeout
            while not predicate() and time.perf_counter() < deadline:
                qt.processEvents();time.sleep(.001)
            if not predicate():
                raise AssertionError('Real Qt job replay did not settle: '+p.browser.input_bar.note.text())

        # Warm the actual WebEngine renderer with a completely local document.
        # GuidePage deliberately rejects setHtml's data: navigation. A plain
        # local diagnostic page keeps the same real application profile/view.
        local_page = QWebEnginePage(p.profile, p.web)
        p.web.setPage(local_page)
        web_loaded = []
        p.web.loadFinished.connect(lambda ok: web_loaded.append(bool(ok)))
        p.web.setHtml('<!doctype html><meta charset="utf-8"><p>Local condition profiler</p>', QUrl('about:blank'))
        settle(lambda: bool(web_loaded))
        if not web_loaded[-1]:
            raise AssertionError('Local WebEngine page warm-up failed')
        last_beat = [time.perf_counter()]

        def heartbeat():
            now = time.perf_counter();gaps.append((now-last_beat[0])*1000);last_beat[0] = now

        heartbeat_timer = QTimer();heartbeat_timer.setInterval(5)
        heartbeat_timer.timeout.connect(heartbeat);heartbeat_timer.start()
        cases = []
        gc_enabled = gc.isenabled();gc.disable()
        profile_cpu = time.process_time();profile_wall = time.perf_counter()
        try:
            for case in frames:
                current['frame'] = case;p.binding = binding();p.geometry = (p.binding.rect, p.binding.dpi)
                latencies = [];bodies = [];first_ms = None
                for iteration in range(args.repeat+1):
                    # Exercise the real side-key slot's debounce without bypassing it.
                    settle(lambda: time.monotonic()-p.last_mouse_trigger >= .72)
                    old_accepted = len(accepted);old_requests = len(requests);started = time.perf_counter()
                    p.mouse_capture(p.mouse_button.currentData(), 707)
                    settle(lambda: len(accepted) > old_accepted and not p.jobs and not p.capture_pending and not p.ocr_busy)
                    elapsed = (accepted[-1]-started)*1000
                    if iteration == 0:
                        first_ms = round(elapsed, 2)
                    else:
                        latencies.append(elapsed)
                    new_requests = requests[old_requests:]
                    if len(new_requests) != 1 or not new_requests[0]['path'].endswith('/explorer/query'):
                        raise AssertionError('Expected one frozen single-condition HTTP request per trigger')
                    body = new_requests[0]['body'];rules = body['filter']['rules']
                    if (body['version'] != p.adapter.patch or len(rules) != 1 or
                        rules[0]['targetId'] != case['id'] or rules[0]['type'] != case['kind'] or
                        rules[0]['starCount'] != '' or body['filter']['combinator'] != 'and'):
                        raise AssertionError('Incorrect versioned canonical condition body: '+repr(body))
                    bodies.append(body)
                    if p.browser.scope[0] != case['kind'] or str(p.browser.scope[1]['id']) != case['id']:
                        raise AssertionError('Widget scope differs from validated HTTP condition')
                    if any(reference() is not None for reference in references):
                        raise AssertionError('Completed real condition job retains a capture copy without cyclic GC')
                cases.append({'name': case['name'], 'path': str(case['path']), 'image_size': case['image'].size,
                              'sha256': hashlib.sha256(case['path'].read_bytes()).hexdigest(),
                              'expected_kind': case['kind'], 'expected_id': case['id'], 'first_trigger_ms': first_ms,
                              'warm_trigger_to_condition': summary(latencies),
                              'warm_samples_ms': [round(value, 2) for value in latencies],
                              'frozen_request_bodies': bodies})
            trigger_cpu = time.process_time()-profile_cpu
            trigger_wall = time.perf_counter()-profile_wall
            report['cpu_scope'] = 'Main Python process and its OCR threads only; WebEngine/game CPU excluded. Trigger phase includes debounce waits, frozen HTTP processing and the event-pump harness.'
            report['trigger_main_process_cpu_seconds'] = round(trigger_cpu, 3)
            report['trigger_wall_seconds'] = round(trigger_wall, 3)
            report['trigger_cpu_one_logical_core_percent'] = round(trigger_cpu/trigger_wall*100, 2)
            report['trigger_gui_heartbeat_gap'] = summary(gaps)
            report['cases'] = cases;report['spans'] = {name: summary(values) for name, values in spans.items()}
            report['reader_results'] = reader_results
            report['after_trigger_counters'] = dict(counters)
            # Exclude synchronous CIM helper startup/sampling from CPU and GUI
            # timing. The idle clock and heartbeat baseline restart afterwards.
            report['memory_after_warm'] = process_tree_memory()
            idle_before = dict(counters);gaps.clear();last_beat[0] = time.perf_counter()
            idle_cpu = time.process_time();idle_started = time.perf_counter();p.timer.start()
            idle_loop = QEventLoop()
            idle_finish = QTimer();idle_finish.setSingleShot(True)
            idle_finish.setTimerType(Qt.TimerType.PreciseTimer)
            def finish_idle():
                # Windows/Qt and perf_counter have different clock rounding.
                # Re-arm a short remainder instead of silently observing <10s.
                remaining = args.idle_seconds-(time.perf_counter()-idle_started)
                if remaining > 0:
                    idle_finish.start(max(1, math.ceil(remaining*1000)+1))
                else:
                    idle_loop.quit()
            idle_finish.timeout.connect(finish_idle)
            idle_finish.start(round(args.idle_seconds*1000))
            idle_loop.exec()
            p.timer.stop()
            if time.perf_counter()-idle_started < args.idle_seconds:
                raise AssertionError('Idle observation ended before the requested complete duration')
            idle_delta = {name: counters[name]-idle_before[name] for name in counters}
            report['idle'] = {'mode': 'automatic paused; no active offer; actual Companion timer running',
                              'wall_seconds': round(time.perf_counter()-idle_started, 3),
                              'main_process_cpu_seconds': round(time.process_time()-idle_cpu, 3),
                              'main_process_cpu_one_logical_core_percent': round(
                                  (time.process_time()-idle_cpu)/(time.perf_counter()-idle_started)*100, 2),
                              'counter_delta': idle_delta, 'gui_heartbeat_gap': summary(gaps)}
            if any(idle_delta[name] for name in ['capture_jobs', 'ocr_jobs', 'capture_copies', 'reader_calls', 'native_ocr_engine_calls']):
                raise AssertionError('Manual idle mode unexpectedly started capture/OCR work')
            report['capture_copy_release'] = {'created': len(references),
                                             'alive_after_jobs_and_idle': sum(reference() is not None for reference in references),
                                             'cyclic_gc_disabled': True}
            report['passed'] = True
        finally:
            heartbeat_timer.stop();p.shutdown();qt.processEvents()
            if gc_enabled:
                gc.enable()
            for case in frames:
                case['image'].close()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'cases': [{key: case[key] for key in
                     ['name', 'expected_id', 'warm_trigger_to_condition']} for case in report['cases']],
                     'memory_after_warm': report['memory_after_warm'], 'idle': report['idle'],
                     'capture_copy_release': report['capture_copy_release'], 'report': str(args.report)},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
