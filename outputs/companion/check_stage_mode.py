"""Stage polling cadence and trigger window; no OS capture or visible widget."""
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
from app import Companion,QApplication

qt=QApplication([])
with patch('app.win.enumerate_mumu',return_value=[]):panel=Companion(offline=True)
panel.timer.stop();panel.hide();assert panel.automatic.isChecked()
# Isolate the augment stage scheduler; item cadence and shared-pool behavior
# have their own check_item_flow coverage.
panel.items.tick=lambda:None
binding=SimpleNamespace(hwnd=123,rect=(0,0,3840,2160),dpi=192)
panel.binding=binding;panel.geometry=(binding.rect,binding.dpi);panel.offline=False
pending=[];captures=[];panel.submit=lambda pool,fn,done,failed=None:pending.append((fn,done))
with patch('app.win.describe',return_value=binding),patch('app.win.foreground_root',return_value=123), \
     patch('app.win.capture_block_reason',return_value=None),patch.object(panel,'request_capture',side_effect=lambda:captures.append(True)), \
     patch('app.capture_stage',return_value=Image.new('RGB',(116,76))),patch.object(panel,'set_activity'), \
     patch('app.time.monotonic',return_value=100) as clock:
    panel.tick();assert len(pending)==1 and not captures
    _,done=pending.pop();done('2-2')
    clock.return_value=102.9;panel.tick();assert not pending and not captures
    clock.return_value=103;panel.tick();assert len(pending)==1 and not captures
    _,done=pending.pop();done('3-2')
    panel.tick();assert captures and panel.stage_window_until==163
    captures.clear();clock.return_value=106;panel.tick()
    _,done=pending.pop();done('3-3');captures.clear()
    panel.tick();assert not captures and panel.stage_window_until==0
    # Default automation can bind a unique foreground game without stealing focus.
    panel.binding=None;panel.geometry=None;panel.last_binding_probe=0
    clock.return_value=110
    with patch('app.game_windows',return_value=[binding]),patch('app.win.user.SetForegroundWindow') as focus:
        panel.tick()
        assert panel.binding is binding and not focus.called
    pending.clear();captures.clear()
    # A manual fallback must work outside a stage window and leave automation on.
    with patch('app.win.same_target',return_value=True),patch.object(panel,'return_to_game',return_value=True),patch('app.QTimer.singleShot'):
        panel.capture_once()
    assert panel.automatic.isChecked() and panel.once_active and panel.once_ocr_pending
    panel.tick();assert captures
    # Closing MuMu should wait for reconnection, not turn the default off.
    with patch('app.win.capture_block_reason',return_value='target_changed_or_closed'):
        panel.tick()
    assert panel.binding is None and panel.automatic.isChecked()
panel.offline=True;panel.shutdown()
print('3-second stage-only polling, target stage arms capture, leaving stage disarms: passed')
