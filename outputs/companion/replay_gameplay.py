"""Reproducible development replay; gold is only used after inference."""
import hashlib
import json
from PIL import Image
from bootstrap import ROOT, STATE_DIR
from vision import Vision, tracked_signature, unchanged
from choice_reader import normalize_name


def main():
    manifest=json.loads((ROOT/'work/s18-video-next/manifest.json').read_text(encoding='utf-8'))
    catalog=json.loads((ROOT/'work/s18-refresh-20260926/catalog.json').read_text(encoding='utf-8'))['data']['hex']
    vision=Vision(); rows=[]; correct=wrong=eligible=rounds=0
    for sample in manifest['samples']:
        if sample.get('category')!='real_gameplay_choice':continue
        path=ROOT/sample['path']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==sample['image_sha256']
        observation=vision.analyze(Image.open(path),catalog)
        stage_ok=observation['round']==sample['stage'];rounds+=stage_ok
        for card,gold in zip(observation['cards'],sample['names']):
            result=card['resolution']
            if result['status']=='resolved':
                right=normalize_name(result['name'])==normalize_name(gold)
                correct+=right;wrong+=not right;eligible+=right and stage_ok
        rows.append({'id':sample['id'],'path':sample['path'],'event_group':sample['event_group'],
                     'round_correct':stage_ok,'gold_names':sample['names'],'observation':observation})
        print(sample['id'],observation['round'],[c['resolution']['status'] for c in observation['cards']],flush=True)
    negative=vision.analyze(Image.open(ROOT/'work/s18-video-next/frame-1020s.png'),catalog)
    guards=[]
    for first,second in [(0,1),(1,2),(4,5),(5,6)]:
        a,b=rows[first],rows[second]
        changed=not unchanged(tracked_signature(Image.open(ROOT/a['path']),a['observation']),
                              tracked_signature(Image.open(ROOT/b['path']),a['observation']))
        guards.append({'from':a['id'],'to':b['id'],'refresh_detected':changed})
    output={'development_only':True,'matches':1,'events':3,'candidate_snapshots':len(rows),'card_slots':len(rows)*3,
            'rounds_correct':rounds,'accepted_correct_names':correct,'accepted_wrong_names':wrong,
            'correct_names_with_correct_stage':eligible,'id_gold_available':False,
            'negative':negative,'refresh_guards':guards,'rows':rows}
    (STATE_DIR/'real-gameplay-eval.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print({k:v for k,v in output.items() if k not in ('rows','negative')})
    assert negative['scene']=='unknown' and all(g['refresh_detected'] for g in guards)


if __name__=='__main__':main()
