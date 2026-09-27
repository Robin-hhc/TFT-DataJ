"""Repeated background capture must not blank an unchanged rank overlay."""
from unittest.mock import patch
from types import SimpleNamespace
from app import Companion,QApplication
qt=QApplication([])
with patch('app.win.enumerate_mumu',return_value=[]): panel=Companion(offline=True)
panel.timer.stop();panel.hide();panel.binding=SimpleNamespace(hwnd=123)
jobs=[];panel.submit=lambda *args:jobs.append(args)
with patch.object(panel,'hide_overlays') as hide,patch('app.QTimer.singleShot',side_effect=lambda delay,fn:fn()):
    panel.request_capture()
    assert not hide.called,'Every capture hides visible ranks and causes flashing'
    assert len(jobs)==1
panel.shutdown()
print('background capture preserves visible ranks: passed')
