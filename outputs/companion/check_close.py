"""Close our hidden widget without activating any game or desktop window."""
from unittest.mock import patch
from PySide6.QtGui import QCloseEvent
from app import Companion, QApplication

app = QApplication([])
with patch('app.win.enumerate_mumu', return_value=[]):
    panel = Companion(offline=True)
panel.timer.stop()
event = QCloseEvent()
with patch.object(panel, 'return_to_game') as focus, patch.object(app, 'quit') as quit_app:
    panel.closeEvent(event)
    assert event.isAccepted(), 'Close button hides instead of closing'
    assert quit_app.call_count == 1, 'Close button must quit the application'
    assert focus.call_count == 0, 'Closing must not activate the game'
panel.shutdown()
print('close: accepted; application quit requested; no game activation')
