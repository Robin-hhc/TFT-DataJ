"""Check same-choice animation and actual refresh with fixed development frames."""
import json
from PIL import Image
from bootstrap import ROOT,STATE_DIR
from vision import tracked_signature,unchanged


def main():
    records=json.loads((STATE_DIR/'real-gameplay-eval.json').read_text(encoding='utf-8'))['rows']
    pairs=[(0,'0049',True),(5,'1009',True),(0,'0063',False),(1,'0065',False),
           (4,'1007',False),(5,'1015',False),(6,'1020',False)]
    results=[]
    for index,second,expected in pairs:
        record=records[index];obs=record['observation']
        first=Image.open(ROOT/record['path'])
        next_frame=Image.open(ROOT/f'work/s18-video-next/frame-{second}s.png')
        actual=unchanged(tracked_signature(first,obs),tracked_signature(next_frame,obs))
        results.append({'first':record['id'],'second':second,'expected_unchanged':expected,'actual_unchanged':actual})
    (STATE_DIR/'animation-result.json').write_text(json.dumps({'development_only':True,'pairs':results},indent=2),encoding='utf-8')
    print(json.dumps(results))
    assert all(r['expected_unchanged']==r['actual_unchanged'] for r in results)


if __name__=='__main__':main()
