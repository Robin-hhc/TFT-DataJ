"""Replay the labelled S18 source frames; report misses rather than hiding them."""
import json
from pathlib import Path
import time
from PIL import Image
from bootstrap import ROOT
from vision import Vision
from item_vision import analyze_items


def main():
    folder=ROOT/'work/item-choice-samples'
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    catalog=json.loads((ROOT/'work/s18-refresh-20260926/catalog.json').read_text(encoding='utf-8'))['data']['equip']
    vision=Vision();vision.prepare()
    results=[]
    for sample in manifest['samples']:
        if sample['size'][0]<640:continue
        path=Path(sample['path'])
        started=time.monotonic()
        with Image.open(path) as image:observation=analyze_items(image.convert('RGB'),vision,catalog)
        results.append({'file':path.name,'category':sample['category'],
                        'gold':sample.get('item_name_gold'),
                        'scene':observation['scene'],'reason':observation['reason'],
                        'elapsed_ms':round((time.monotonic()-started)*1000,2),
                        'names':[c['resolution'].get('name') if c['resolution']['status']=='resolved' else None
                                 for c in observation['cards']],
                        'ids':[c['resolution'].get('id') for c in observation['cards']]})
    output={'kind':'development_replay_not_live_acceptance','results':results}
    (folder/'replay-results.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(output,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
