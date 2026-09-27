"""Exercise real-frame transitions through app callbacks, with no game interaction."""
import json
import time
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
from app import Companion, QApplication
from bootstrap import ROOT, STATE_DIR
from vision import tracked_signature


def main():
    qt=QApplication([]);panel=Companion(offline=True);panel.timer.stop()
    records=json.loads((STATE_DIR/'real-gameplay-eval.json').read_text(encoding='utf-8'))['rows']
    panel.binding=SimpleNamespace(hwnd=123);panel.hide()
    pending=[];checks=[]
    # Queue callbacks without running workers, allowing deterministic late delivery.
    panel.submit=lambda pool,job,done,failed=None:pending.append((job,done))
    with patch('app.win.same_target',return_value=True),patch('app.win.foreground_root',return_value=123):
        first=records[0];second=records[1]
        image=Image.open(ROOT/first['path']).convert('RGB')
        fresh=Image.open(ROOT/second['path']).convert('RGB')
        panel.last_frame=image
        panel.analyze(image,True)
        _,old_done=pending.pop()
        panel.last_frame=fresh
        old_done(first['observation'])
        assert panel.stats_payload is None and not pending and panel.last_observation is None
        checks.append('late OCR after real center refresh rejected before data query')
        panel.last_frame=image;panel.analyze(image,True)
        _,before_focus_loss=pending.pop()
        with patch('app.win.describe',return_value=None),patch('app.win.capture_block_reason',return_value='not_foreground'):
            panel.tick()
        before_focus_loss(first['observation'])
        assert panel.last_observation is None and not pending
        checks.append('focus loss invalidates first OCR even before a signature exists')
        panel.invalidate();panel.show();panel.analyze(image,False)
        _,offline_done=pending.pop()
        with patch('app.win.describe',return_value=None),patch('app.win.capture_block_reason',return_value='not_foreground'):
            panel.tick()
        offline_done(first['observation'])
        assert panel.last_observation is not None and len(pending)==1
        pending.clear();panel.hide();panel.invalidate()
        checks.append('visible file replay survives timer ticks and submits statistics')
        binding=SimpleNamespace(hwnd=123,rect=(0,0,640,360),dpi=96)
        panel.binding=binding;panel.geometry=(binding.rect,binding.dpi)
        scheduled=[]
        with patch.object(panel,'return_to_game',side_effect=panel.invalidate),patch('app.QTimer.singleShot',side_effect=lambda ms,callback:scheduled.append(callback)):
            panel.capture_once()
        panel.last_capture=0
        captures=[]
        with patch('app.win.describe',return_value=binding),patch('app.win.capture_block_reason',return_value=None),patch.object(panel,'request_capture',side_effect=lambda:captures.append(True)):
            panel.tick()
        assert captures==[True] and not panel.automatic.isChecked()
        panel.capture_pending=True;scheduled[0]()
        assert panel.once_ocr_pending
        panel.last_ocr=0;panel.captured((image,binding),False)
        assert len(pending)==1 and not panel.once_ocr_pending
        pending.clear();panel.ocr_busy=False
        panel.captured((image,binding),False)
        assert not pending
        checks.append('one-shot survives initial capture race and keeps freshness without repeating OCR')
        panel.invalidate()
        panel.last_frame=image;panel.signature=tracked_signature(image,first['observation'])
        panel.last_observation=first['observation'];panel.stage.setCurrentText('2-1')
        panel.query_stats(['1','2','3'],['a','b','c'],True)
        _,late_stats=pending.pop()
        panel.last_ocr=time.monotonic()
        panel.captured((fresh,panel.binding),False)
        late_stats(({'data':[],'fetched_at':0},None))
        assert panel.stats_payload is None and panel.choice_table.rowCount()==0
        checks.append('real refresh invalidates in-flight statistics response')
        suggestion=dict(first['observation'])
        suggestion['cards']=[dict(c) for c in first['observation']['cards']]
        suggestion['cards'][0]['resolution']={'status':'needs_confirmation','name':'示例 I','suggested_id':'123'}
        requested=[]
        panel.query_stats=lambda ids,names,live:requested.append(ids)
        panel.observed(suggestion,False)
        assert requested[0][0] is None
        checks.append('Roman glyph suggestion never becomes automatic query ID')
    panel.binding=None;panel.shutdown();qt.processEvents()
    report={'game_control':False,'network':False,'passed':len(checks),'checks':checks}
    (STATE_DIR/'lifecycle-result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':main()
