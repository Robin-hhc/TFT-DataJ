"""Bounded local events and recent game-only diagnostic frames; never uploads."""
import json
import time
from datetime import datetime
from bootstrap import STATE_DIR


class FrameRecorder:
    """Keep at most six frames from the already captured, bound game window."""
    def __init__(self, directory=None):
        self.directory=directory or STATE_DIR/'diagnostic-frames'
        self.index=0
        self.last_saved=float('-inf')
        self.last_scene=None

    def save(self,image,observation):
        now=time.monotonic()
        scene=observation.get('scene')
        if scene==self.last_scene and now-self.last_saved<15:return None
        try:
            self.directory.mkdir(parents=True,exist_ok=True)
            stem=self.directory/f'frame-{self.index%6}'
            image.save(stem.with_suffix('.png'),compress_level=1)
            stem.with_suffix('.json').write_text(json.dumps({
                'time':datetime.now().isoformat(timespec='milliseconds'),
                'size':image.size,'scene':scene,'reason':observation.get('reason'),
                'stage':observation.get('round'),'elapsed_ms':observation.get('elapsed_ms')
            },ensure_ascii=False,indent=2),encoding='utf-8')
            self.index+=1;self.last_saved=now;self.last_scene=scene
            return stem.name
        except OSError:return None


def record(event, **values):
    path = STATE_DIR / 'pipeline.jsonl'
    try:
        if path.exists() and path.stat().st_size > 2_000_000:
            path.replace(STATE_DIR / 'pipeline.previous.jsonl')
        with path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'time': datetime.now().isoformat(timespec='milliseconds'),
                                     'event': event, **values}, ensure_ascii=False) + '\n')
    except OSError:
        pass
