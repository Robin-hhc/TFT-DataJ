"""Real user images through freshness and late-response guards, no visible UI."""
import json,time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
from app import Companion,QApplication
from bootstrap import ROOT
from vision import tracked_signature,unchanged
from integration_check import FrozenSource

qt=QApplication([])
with patch('app.win.enumerate_mumu',return_value=[]):panel=Companion(offline=True)
panel.timer.stop();panel.hide();panel.adapter=FrozenSource();panel.binding=SimpleNamespace(hwnd=123)
base=Path('D:/Documents/MuMu共享文件夹/Screenshots')
before=Image.open(base/'MuMu-20260927-001814-931.png').convert('RGB')
after=Image.open(base/'MuMu-20260927-001829-927.png').convert('RGB')
board=Image.open(base/'MuMu-20260927-001909-839.png').convert('RGB')
folder=ROOT/'work/user-game-sample/new-round'
old=json.loads((folder/'MuMu-20260927-001814-931.png.json').read_text(encoding='utf-8'))
new=json.loads((folder/'MuMu-20260927-001829-927.png.json').read_text(encoding='utf-8'))
assert not unchanged(tracked_signature(before,old),tracked_signature(after,old))
assert not unchanged(tracked_signature(after,new),tracked_signature(board,new))
jobs=[];panel.submit=lambda pool,fn,done,failed=None:jobs.append((fn,done))
for label in panel.overlays:label.place=lambda *args:None
with patch('app.win.foreground_root',return_value=123),patch('app.win.same_target',return_value=True):
    panel.last_frame=before;panel.signature=tracked_signature(before,old)
    panel.observed(old,True)
    fn,late=jobs.pop()
    panel.captured((after,panel.binding),False)
    inspect,accept=jobs.pop();accept(inspect())
    late(fn())
    assert panel.stats_payload is None,'Old statistics returned after a real refresh'
    panel.signature=tracked_signature(after,new);panel.observed(new,True)
    fn,done=jobs.pop();done(fn())
    assert panel.stats_payload and panel.stats_payload['rows'][2][1].startswith('—')
    assert '白银命运' in panel.stats_payload['rows'][2][0]
    panel.captured((board,panel.binding),False)
    inspect,accept=jobs.pop();accept(inspect())
    assert panel.stats_payload is None,'Leaving selection must clear all old results'
panel.shutdown()
print('user refresh invalidates old response; missing catalog entry stays blank; board clears results: passed')
