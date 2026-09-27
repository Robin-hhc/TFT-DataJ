"""Exercise the real timer/capture/OCR/query path with frozen video and data.

Only the OS screenshot and overlay placement are replaced. Never shows a window.
"""
import json
import argparse
import time
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
from app import Companion, QApplication
from bootstrap import ROOT, STATE_DIR
from integration_check import FrozenSource


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--image',default='work/user-game-sample/new-round/before.png')
    args=parser.parse_args()
    qt = QApplication([])
    with patch('app.win.enumerate_mumu', return_value=[]):
        panel = Companion(offline=True)
    panel.timer.stop()
    panel.adapter = FrozenSource()
    panel.hide()
    image = Image.open(ROOT/args.image).convert('RGB')
    binding = SimpleNamespace(hwnd=123, rect=(0, 0, image.width, image.height), dpi=96)
    panel.binding = binding
    panel.geometry = (binding.rect, binding.dpi)
    panel.automatic.setChecked(True)
    placed = []
    captures = []
    ocr_calls=[]
    real_analyze=panel.vision.analyze_fast
    def counted_analyze(*args):
        ocr_calls.append(time.monotonic())
        return real_analyze(*args)
    panel.vision.analyze_fast=counted_analyze
    for overlay in panel.overlays:
        overlay.place = lambda *args: placed.append(time.monotonic())
    def capture(_):
        captures.append(time.monotonic())
        return image.copy(), binding
    start = time.monotonic()
    cpu_start=time.process_time()
    with patch('app.win.describe', return_value=binding), patch('app.win.foreground_root', return_value=123), \
         patch('app.win.capture_block_reason', return_value=None), patch('app.win.same_target', return_value=True), \
         patch('app.capture_image', side_effect=capture):
        panel.timer.start()
        while time.monotonic()-start < 16:
            qt.processEvents()
            time.sleep(.01)
        panel.timer.stop()
        # Allow already scheduled captures and workers to settle before shutdown.
        deadline=time.monotonic()+10
        while (panel.jobs or panel.capture_pending) and time.monotonic()<deadline:
            qt.processEvents();time.sleep(.01)
        report={'captures':len(captures),'overlay_placements':len(placed),
                'ocr_calls':len(ocr_calls),'process_cpu_seconds':round(time.process_time()-cpu_start,2),
                'input':args.image,'rows':panel.stats_payload['rows'] if panel.stats_payload else [],
                'first_result_seconds':round(placed[0]-start,2) if placed else None,
                'last_state':panel.activity_code,'real_game_operated':False,
                'limits':'same frozen frame, frozen statistics, simulated window; not real game acceptance'}
        panel.shutdown()
    (STATE_DIR/'continuous-result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))
    assert len(captures)>10, report
    assert placed and placed[-1]-start>10, report
    assert len(ocr_calls)<=2, 'Unchanged choices must not run repeated OCR: '+str(report)


if __name__=='__main__':main()
