"""Real-frame application flow with frozen source data; no live input or network."""
import json
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import httpx
from PIL import Image
from app import Companion,QApplication
from dataj import DataJ
from bootstrap import ROOT


def main():
    qt=QApplication([])
    with patch('app.win.enumerate_mumu',return_value=[]):panel=Companion(offline=True)
    panel.timer.stop();panel.hide();panel.vision.prepare()
    binding=SimpleNamespace(hwnd=123,rect=(0,0,1920,1440),dpi=96)
    panel.binding=binding;panel.geometry=(binding.rect,binding.dpi)
    panel.items.available=lambda:True
    panel.items.render=lambda:None
    folder=ROOT/'work/item-choice-probe'
    raw=lambda name:json.loads((folder/name).read_text(encoding='utf-8'))['payload']['data']
    calls=[]
    def handle(request):
        calls.append(str(request.url));path=request.url.path
        if path.endswith('/stats/equip'):data=raw('global.json')
        elif path.endswith('/equips'):data=raw('comp.json')
        elif path.endswith('/equip-heroes'):
            data={'compId':'112','equipId':request.url.params['equipId'],
                  'heroes':[{'heroId':'4510','heroName':'希维尔','sampleCount':100,'avgPlacement':3.5}]}
        elif path.endswith('/explorer/query'):data=raw('radiant-explorer.json')
        else:data=[]
        return httpx.Response(200,json={'code':200,'success':True,'data':data})
    with tempfile.TemporaryDirectory() as directory:
        panel.adapter=DataJ(db=Path(directory)/'cache.sqlite',transport=httpx.MockTransport(handle))
        jobs=[]
        panel.submit=lambda pool,fn,done,failed=None:jobs.append((fn,done,failed))
        def drain():
            while jobs:
                fn,done,failed=jobs.pop(0)
                panel.adapter.next_request=0
                try:result=fn()
                except Exception as error:
                    if failed:failed(str(error))
                    else:raise
                else:done(result)
        image=Image.open(ROOT/'work/item-choice-samples/user-p2-720p-0753s.png').convert('RGB')
        panel.session.set_target('112')
        panel.comp_detail={'name':'地狱火95','heroes':[{'heroId':'4510','heroName':'希维尔'}]}
        assert panel.items.ingest(image,binding,force=True)
        drain()
        assert panel.items.active
        assert [r['id'] for r in panel.items.rows]==['2027','2025','2031','2029']
        assert all(r['global']['status']=='ok' and r['comp']['status']=='ok' for r in panel.items.rows)
        assert all(r['holders'][0]['id']=='4510' for r in panel.items.rows)
        # Stable frames keep results and issue no new requests.
        count=len(calls);generation=panel.items.generation
        for _ in range(4):panel.items.ingest(image,binding)
        assert not jobs and len(calls)==count and panel.items.generation==generation
        # Different real video frames include moving effects and compression.
        # These are one event, not additional independent recognition samples.
        sequence=ROOT/'work/item-choice-samples'
        panel.items.next_ocr=0
        panel.items.ingest(Image.open(sequence/'user-p1-720p-0288s.png').convert('RGB'),binding,force=True)
        drain();assert panel.items.active
        count=len(calls);generation=panel.items.generation
        for second in (289,290):
            panel.items.ingest(Image.open(sequence/f'user-p1-720p-{second:04d}s.png').convert('RGB'),binding)
        assert not jobs and len(calls)==count and panel.items.generation==generation
        panel.items.ingest(Image.open(sequence/'user-p1-720p-0300s.png').convert('RGB'),binding)
        assert not panel.items.active and not panel.items.rows
        panel.items.reset();drain()
        # A disappeared scene clears all results, even if auto mode is paused.
        panel.automatic.setChecked(False)
        panel.items.ingest(Image.new('RGB',image.size),binding)
        assert not panel.items.active and not panel.items.rows
        # Data callbacks from a previous pinned-comp/version cannot revive overlays.
        panel.items.cache.clear();panel.items.next_ocr=0
        panel.items.ingest(image,binding,force=True)
        fn,done,_=jobs.pop(0);done(fn())  # OCR, leaving table fetch queued.
        assert jobs
        panel.session.set_target('113');panel.invalidate()
        drain();assert not panel.items.active and not panel.items.rows
        # An OCR completion after focus loss is similarly discarded.
        panel.items.ingest(image,binding,force=True)
        panel.items.reset();drain();assert not panel.items.active
        # Idle probing is bounded to every two seconds, and captures only the
        # lower region through the shared capture pool.
        panel.automatic.setChecked(True);jobs.clear();panel.items.last_probe=0
        with patch('item_controller.time.monotonic',return_value=100) as clock:
            panel.items.tick();assert len(jobs)==1
            fn,done,_=jobs.pop(0)
            with patch('item_controller.capture_item_region',return_value=(Image.new('RGB',image.size),binding)):
                done(fn())
            clock.return_value=101.9;panel.items.tick();assert not jobs
            clock.return_value=102;panel.items.tick();assert len(jobs)==1
        jobs.clear();panel.capture_pending=False;panel.items.probing=False
        assert all('gameVersion=18.2a' in url for url in calls)
        print(json.dumps({'item_flow':'passed','source':'frozen real item tables + synthetic holder fixtures',
                          'consecutive_video_frames_stable':True,
                          'stable_no_requery':True,'stale_response_rejected':True,'idle_probe_seconds':2}))
    panel.shutdown();qt.processEvents()


if __name__=='__main__':main()
