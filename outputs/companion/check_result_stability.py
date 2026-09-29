"""Deterministic delayed-query and repeated-OCR regression; hidden widgets only."""
import json
import time
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
from app import Companion,QApplication
from bootstrap import ROOT
from integration_check import FrozenSource

qt=QApplication([])
with patch('app.win.enumerate_mumu',return_value=[]):panel=Companion(offline=True)
panel.timer.stop();panel.adapter=FrozenSource();panel.hide()
panel.binding=SimpleNamespace(hwnd=123)
observation=json.loads((ROOT/'work/user-game-sample/new-round/MuMu-20260927-001814-931.png.json').read_text(encoding='utf-8'))
jobs=[];panel.submit=lambda pool,fn,done,failed=None:jobs.append((fn,done))
for overlay in panel.overlays:overlay.place=lambda *args:None
with patch('app.win.foreground_root',return_value=123):
    panel.observed(observation,True)
    token=panel.session.token()
    panel.observed(observation,True)
    assert panel.session.accepts(token),'Repeated OCR cancels the in-flight statistics request'
    assert len(jobs)==1,'Repeated OCR queues duplicate statistics requests'
    fn,done=jobs.pop();panel.last_capture=time.monotonic();done(fn())
    payload=panel.stats_payload
    panel.observed(observation,True)
    assert panel.stats_payload is payload and not jobs,'Same choices clear already available results'
    panel.automatic.setChecked(True)
    panel.last_observation=None;panel.stats_payload=payload;panel.ocr_busy=True;panel.last_ocr=0
    with patch('app.win.same_target',return_value=True),patch.object(panel,'display_overlays') as display:
        # No tracked observation avoids testing image comparison in this unit.
        panel.last_observation=observation
        with patch('app.tracked_signature',return_value=None),patch('app.unchanged',return_value=True):
            panel.captured((Image.new('RGB',(20,20)),panel.binding),False)
            fn,done=jobs.pop();done(fn())
        assert display.called,'A busy OCR worker prevents restoring existing overlays after capture'
panel.shutdown()
print('stable same-choice request, retained result, restore while OCR busy: passed')
