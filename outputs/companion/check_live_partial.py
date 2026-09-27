import json,time
from unittest.mock import patch
from PIL import Image
from app import Companion,QApplication
from bootstrap import ROOT,STATE_DIR
from integration_check import FrozenSource
qt=QApplication([])
with patch('app.win.enumerate_mumu',return_value=[]):panel=Companion(offline=True)
panel.timer.stop();panel.hide();panel.adapter=FrozenSource();panel.vision.prepare()
obs=panel.vision.analyze_fast(Image.open(ROOT/'work/companion/live-validation/choice-2-1.png').convert('RGB'),panel.catalog['hex'])
# Force one unreadable slot to retain coverage of partial-result rendering.
obs['cards'][0]['resolution']={'status':'unrecognized','readings':[]}
panel.observed(obs,False)
end=time.monotonic()+5
while panel.jobs and time.monotonic()<end:qt.processEvents();time.sleep(.005)
assert panel.stats_payload
assert panel.activity_code=='partial_results',panel.activity_code
rows=panel.stats_payload['rows'];assert len(rows)==3
report={'stage':obs['round'],'scene':obs['scene'],'ocr_ms':obs['elapsed_ms'],'activity':panel.activity_code,'rows':rows,'statistics':'frozen replay, not live validation'}
(STATE_DIR/'live-validation/partial-replay.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False));panel.shutdown()
