"""Partial recognition must retry briefly without removing readable results."""
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
from app import Companion, QApplication

qt = QApplication([])
with patch('app.win.enumerate_mumu', return_value=[]):
    panel = Companion(offline=True)
panel.timer.stop()
panel.hide()
panel.binding = SimpleNamespace(hwnd=123)
image = Image.new('RGB', (20, 20))
partial = {'cards': [{'resolution': {'id': 'a'}},
                     {'resolution': {'id': None}},
                     {'resolution': {'id': 'c'}}]}
try:
    for automatic in (False, True):
        panel.invalidate()
        panel.automatic.setChecked(automatic)
        panel.once_active = not automatic
        panel.last_observation = partial
        panel.stats_payload = {'retained': True}
        panel.last_ocr = 0
        panel.next_ocr_allowed = 0
        with patch('app.win.same_target', return_value=True), \
             patch('app.tracked_signature', return_value=None), \
             patch('app.unchanged', return_value=True), \
             patch.object(panel, 'display_overlays'), \
             patch.object(panel, 'hide_overlays') as hide, \
             patch.object(panel, 'analyze') as analyze:
            panel.captured((image, panel.binding), False)
            assert analyze.call_count == 1, 'Partial result never retries an unchanged selection'
            panel.captured((image, panel.binding), False)
            panel.captured((image, panel.binding), False)
            assert analyze.call_count == 2, 'Partial retries must be bounded to two attempts'
            assert panel.stats_payload == {'retained': True} and not hide.called
            panel.partial_retries = 0
            panel.ocr_busy = True
            panel.captured((image, panel.binding), False)
            assert analyze.call_count == 2, 'Busy worker consumes retries'
            panel.ocr_busy = False
            panel.last_ocr = __import__('time').monotonic()
            panel.captured((image, panel.binding), False)
            assert analyze.call_count == 2, 'Retry ignores cooldown'
            panel.last_ocr = 0
            panel.last_observation = {'cards': [{'resolution': {'id': str(i)}} for i in range(3)]}
            panel.captured((image, panel.binding), False)
            assert analyze.call_count == 2, 'Complete result repeats OCR'
finally:
    panel.shutdown()
print('manual and automatic partial retries bounded; results retained; busy/cooldown/full gates passed')
