"""One-click product flow; no real window activation, capture or network."""
import json
import time
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
from app import Companion,QApplication
from bootstrap import ROOT,STATE_DIR
from integration_check import FrozenSource


def main():
    qt=QApplication([])
    with patch('app.win.enumerate_mumu',return_value=[]):panel=Companion(offline=True)
    panel.timer.stop();panel.adapter=FrozenSource()
    checks=[]
    assert panel.advanced.isHidden() and panel.start_button.isEnabled()
    assert panel.automatic.isChecked()
    panel.automatic.setChecked(False)
    checks.append('default screen hides binding, IDs and technical settings')
    with patch('app.win.enumerate_mumu',return_value=[]):panel.start_or_pause()
    assert panel.activity_code=='no_game' and not panel.automatic.isChecked()
    checks.append('missing game produces an actionable message')
    binding=SimpleNamespace(hwnd=123,pid=456,process='MuMuNxDevice.exe',class_name='game',title='MuMu',rect=(0,0,640,360),dpi=96,minimized=False)
    placed=[]
    for label in panel.overlays:label.place=lambda *args:placed.append(args)
    def wait():
        deadline=time.monotonic()+30
        while panel.jobs and time.monotonic()<deadline:
            qt.processEvents();time.sleep(.01)
        qt.processEvents();assert not panel.jobs
    with patch('app.win.enumerate_mumu',return_value=[binding]),patch('app.win.describe',return_value=binding),patch('app.win.foreground_root',return_value=123),patch('app.win.user.SetForegroundWindow',return_value=True) as focus:
        panel.start_or_pause()
        assert panel.binding is binding and panel.automatic.isChecked() and focus.call_count==1
        checks.append('one click binds unique game, enables OCR and returns to game')
        frame=Image.open(ROOT/'work/user-game-sample/new-round/before.png').convert('RGB')
        panel.captured((frame,binding),False)
        # Simulate the capture stream keeping the same frame fresh during OCR.
        deadline=time.monotonic()+30
        while panel.jobs and time.monotonic()<deadline:
            panel.last_capture=time.monotonic();qt.processEvents();time.sleep(.01)
        wait()
        assert panel.stats_payload and panel.session.stage=='2-1'
        assert len(placed)==3,placed
        assert any('局' in row[1] for row in panel.stats_payload['rows']),panel.stats_payload
        checks.append('real image reaches three overlays with frozen stage statistics')
        panel.start_or_pause()
        assert not panel.automatic.isChecked() and panel.stats_payload is None
        checks.append('pause clears results and disables capture')
        assert focus.call_count==1,'background callbacks must not activate game or panel'
        checks.append('no background focus stealing')
        panel.set_activity('waiting_foreground','paused');panel.automatic.setChecked(True)
        with patch.object(panel,'probe_stage'),patch.object(panel,'request_capture'):
            panel.tick()
        assert panel.activity_code=='watching_stage'
        panel.automatic.setChecked(False)
        checks.append('foreground resume restores visible status')
        scheduled=[];callbacks=[]
        with patch('app.QTimer.singleShot',side_effect=lambda ms,fn:scheduled.append(fn)),patch.object(panel,'submit',side_effect=lambda pool,job,done,failed:callbacks.append(failed)):
            panel.automatic.setChecked(True)
            panel.request_capture()
            panel.start_or_pause()
            callbacks.pop()('late error')
        assert panel.activity_code=='paused'
        checks.append('late capture failure cannot overwrite paused state')
        panel.reopen_shortcut_available=False
        with patch.object(panel,'showMinimized') as minimize:
            panel.return_to_game();assert minimize.call_count==1
        checks.append('unavailable reopen hotkey keeps a taskbar recovery entry')
        with patch('app.win.user.SetForegroundWindow',return_value=False),patch('app.win.foreground_root',return_value=0),patch.object(panel,'showNormal') as show:
            panel.start_or_pause()
            assert panel.activity_code=='return_failed' and not panel.automatic.isChecked() and show.call_count==1
        checks.append('failed focus transfer keeps panel available with an explanation')
    panel.binding=None;panel.shutdown()
    report={'passed':len(checks),'checks':checks,'real_game_operated':False,'network_used':False}
    (STATE_DIR/'simple-flow-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
