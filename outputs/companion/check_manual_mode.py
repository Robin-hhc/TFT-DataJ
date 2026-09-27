"""Hidden end-to-end manual trigger benchmark and idle mode contracts."""
import json,time
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
from app import Companion,QApplication
from bootstrap import ROOT,STATE_DIR
from integration_check import FrozenSource

qt=QApplication([])
with patch('app.win.enumerate_mumu',return_value=[]):panel=Companion(offline=True)
panel.timer.stop();panel.hide();panel.adapter=FrozenSource();panel.vision.prepare()
frame=Image.open(ROOT/'work/user-game-sample/new-round/before.png').convert('RGB')
binding=SimpleNamespace(hwnd=123,pid=456,process='MuMuNxDevice.exe',rect=(0,0,3840,2160),dpi=192)
panel.binding=binding;panel.geometry=(binding.rect,binding.dpi)
assert panel.trigger_mode.currentIndex()==0 and not panel.automatic.isChecked()
with patch('app.win.describe',side_effect=AssertionError('manual idle must not poll windows')):
    panel.tick()
assert panel.mark.size().width()==44 and panel.mark.size().height()==44
assert not panel.mark.isModal() and not panel.isModal()
placements=[]
for overlay in panel.overlays:overlay.place=lambda *args:placements.append(time.monotonic())
with patch('app.win.describe',return_value=binding),patch('app.win.same_target',return_value=True), \
     patch('app.win.foreground_root',return_value=123),patch('app.win.user.SetForegroundWindow',return_value=True), \
     patch('app.capture_image',return_value=(frame,binding)):
    start=time.monotonic();panel.capture_once()
    deadline=start+8
    while not placements and time.monotonic()<deadline:qt.processEvents();time.sleep(.005)
    assert len(placements)==3,panel.activity_code
    elapsed=round((placements[0]-start)*1000)
    assert all('局' in row[1] for row in panel.stats_payload['rows'])
    assert not panel.automatic.isChecked()
report={'warm_manual_ms':elapsed,'ocr_ms':panel.last_observation['elapsed_ms'],
        'capture':'in-memory user frame','statistics':'frozen','game_operated':False,
        'manual_idle_no_capture':True,'mark_size':[44,44]}
panel.shutdown();(STATE_DIR/'manual-result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
