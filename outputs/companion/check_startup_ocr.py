"""Cold-start OCR regression: hidden Qt app, local real frame, frozen data.

Run in a fresh process: native heap corruption cannot be caught as a Python error.
Requires the local work/ fixtures documented in README.
"""
import json
import threading
import time
from unittest.mock import patch
from PIL import Image
from app import QApplication,Companion
from bootstrap import ROOT
from integration_check import FrozenSource

class Source(FrozenSource):
    def versions(self):return ['18.2a']
    def catalog(self):
        return {'data':json.loads((ROOT/'work/s18-refresh-20260926/catalog.json').read_text(encoding='utf-8'))['data']}

qt=QApplication([])
with patch('app.DataJ',Source),patch('app.win.enumerate_mumu',return_value=[]):
    panel=Companion()
panel.timer.stop();panel.hide()
def settle():
    deadline=time.monotonic()+15
    while panel.jobs and time.monotonic()<deadline:
        qt.processEvents();time.sleep(.005)
    qt.processEvents()
    assert not panel.jobs,'background work did not finish'
try:
    settle()
    assert panel.vision.engine is not None,'startup did not initialize OCR'
    # Use the live crop recognizer, but keep all output in hidden local widgets.
    panel.vision.analyze=panel.vision.analyze_fast
    frame=Image.open(ROOT/'work/companion/live-validation/choice-2-1.png').convert('RGB')
    for _ in range(3):
        panel.analyze(frame,False);settle()
        assert panel.last_observation['round']=='2-1'
        assert panel.activity_code=='results',panel.activity_code
        assert panel.session.choices==('1023','1479','1006')
    print(json.dumps({'cold_start':'passed','recognitions':3,'UI':'hidden','statistics':'frozen'}),flush=True)
finally:
    panel.shutdown()
