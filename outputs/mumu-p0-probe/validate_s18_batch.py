"""Frozen S18 data audit and explicitly synthetic name-crop OCR stress test."""
from __future__ import annotations

import collections
import hashlib
import importlib.metadata
import io
import json
import time
from pathlib import Path

from choice_reader import exact_catalog_matches, normalize_name
from ocr_baseline import ROOT, PACKAGES, ENGINE_PARAMS, build_engine
from snapshot_stats import STAGES, stage_stat


def data_audit(catalog, stats):
    errors = []
    ids = [str(row['id']) for row in catalog]
    stat_ids = [str(row['hexId']) for row in stats]
    for label, values in [('catalog', ids), ('stats', stat_ids)]:
        if len(values) != len(set(values)):
            errors.append(label + ': duplicate IDs')
    names = collections.defaultdict(list)
    for row in catalog:
        names[normalize_name(row['name'])].append(str(row['id']))
    by_id = {str(row['id']): row for row in catalog}
    stat_by_id = {str(row['hexId']): row for row in stats}
    for row in stats:
        entity = by_id.get(str(row['hexId']))
        if not entity or normalize_name(entity['name']) != normalize_name(row['name']):
            errors.append('stat ID/name mismatch: ' + str(row['hexId']))
        for part in row.get('roundStats', []):
            if part.get('roundLabel') not in STAGES or part.get('round') != STAGES.get(part.get('roundLabel')):
                errors.append('stage label/index mismatch: ' + str(row['hexId']))
    statuses = collections.Counter()
    for entity in catalog:
        for stage in STAGES:
            result = stage_stat(stats, entity['id'], stage)
            statuses[result['status']] += 1
            source = stat_by_id.get(str(entity['id']))
            parts = [x for x in source.get('roundStats', []) if x.get('roundLabel') == stage] if source else []
            if len(parts) > 1:
                errors.append('duplicate stage rows: ' + entity['id'] + '/' + stage)
            elif len(parts) == 1:
                part = parts[0]
                if (result['status'] != 'ok' or result.get('avg_placement') != part.get('avgPlacement')
                        or result.get('sample_count') != part.get('sampleCount')):
                    errors.append('lookup/source mismatch: ' + entity['id'] + '/' + stage)
            elif result['status'] == 'ok':
                errors.append('lookup invented a stage: ' + entity['id'] + '/' + stage)
            if result['status'] == 'invalid_stat':
                errors.append('invalid stat: ' + entity['id'] + '/' + stage)
            if result['status'] != 'ok' and result['avg_placement'] is not None:
                errors.append('missing statistic was filled')
    return {'catalog_rows': len(catalog), 'stat_rows': len(stats),
            'stage_lookups': len(catalog)*len(STAGES), 'lookup_statuses': dict(statuses),
            'duplicate_normalized_names': {k:v for k,v in names.items() if len(v)>1},
            'errors': errors}


def render_crop(name, font, degraded):
    from PIL import Image, ImageDraw, ImageFilter
    box = font.getbbox(name)
    image = Image.new('RGB', (box[2]-box[0]+32, box[3]-box[1]+24), '#182a35')
    ImageDraw.Draw(image).text((16-box[0], 12-box[1]), name, font=font, fill='#f5e7c9')
    if degraded:
        image = image.resize((max(1,image.width//2), max(1,image.height//2)), Image.Resampling.LANCZOS)
        image = image.filter(ImageFilter.GaussianBlur(.35))
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=55)
        buffer.seek(0)
        image = Image.open(buffer).convert('RGB')
    return image


def run():
    from PIL import ImageFont
    import numpy as np
    import cv2
    work = ROOT/'work/s18-batch'
    work.mkdir(parents=True, exist_ok=True)
    frozen = ROOT/'work/s18-refresh-20260926'
    files = {'catalog': frozen/'catalog.json', 'stats': frozen/'hex.json'}
    catalog = json.loads(files['catalog'].read_text(encoding='utf-8'))['data']['hex']
    stats = json.loads(files['stats'].read_text(encoding='utf-8'))['data']
    audit = data_audit(catalog, stats)
    font_path = Path('C:/Windows/Fonts/msyhbd.ttc')
    font = ImageFont.truetype(str(font_path), 32)
    engine, models = build_engine()
    results = []
    for variant in ('clean32', 'halfsize_jpeg55'):
        for row in catalog:
            crop = render_crop(row['name'], font, variant != 'clean32')
            pixels = cv2.cvtColor(np.asarray(crop), cv2.COLOR_RGB2BGR)
            start = time.perf_counter()
            prediction = engine(pixels, use_det=False, use_cls=False)
            elapsed = (time.perf_counter()-start)*1000
            text = prediction.txts[0] if prediction.txts else ''
            matches = exact_catalog_matches(text, catalog)
            correct_text = normalize_name(text) == normalize_name(row['name'])
            correct_id = len(matches)==1 and matches[0]['id']==str(row['id'])
            wrong_id = len(matches)==1 and not correct_id
            case = {'id':str(row['id']), 'variant':variant, 'expected':row['name'],
                    'predicted':text, 'score':float(prediction.scores[0]) if prediction.txts else None,
                    'text_correct':correct_text, 'id_correct':correct_id,
                    'wrong_unique_id':wrong_id, 'matches':matches, 'ms':round(elapsed,2)}
            if not correct_text or not correct_id:
                filename = variant+'-'+str(row['id'])+'.png'
                crop.save(work/filename)
                case['failure_crop']=filename
            results.append(case)
        group = [r for r in results if r['variant']==variant]
        print(json.dumps({'variant':variant,'cases':len(group),'correct_text':sum(r['text_correct'] for r in group)},ensure_ascii=False),flush=True)
    summaries = {}
    for variant in ('clean32', 'halfsize_jpeg55'):
        group = [r for r in results if r['variant']==variant]
        summaries[variant] = {'cases':len(group),'correct_text':sum(r['text_correct'] for r in group),
                              'correct_unique_id':sum(r['id_correct'] for r in group),
                              'wrong_unique_id':sum(r['wrong_unique_id'] for r in group)}
    payload = {'kind':'synthetic-name-crop-development-test', 'real_game_images':0,
               'scope':{'set_id':18,'stats_version':'18.2a','snapshot_date':'2026-09-26'},
               'limitations':['Synthetic text crops, not game UI accuracy.',
                              'Known crop recognition only; no scene/round/card detection.',
                              'Two transforms of each name are correlated, not independent matches.',
                              'All 263 catalog rows included, even those without version statistics.'],
               'input_sha256':{k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in files.items()},
               'font':{'name':font_path.name,'sha256':hashlib.sha256(font_path.read_bytes()).hexdigest(),'size':32},
               'versions':{p:importlib.metadata.version(p) for p in (*PACKAGES, 'Pillow')},
               'engine_params':ENGINE_PARAMS,'models':models,'data_audit':audit,
               'synthetic_summary':summaries,'cases':results}
    target = ROOT/'outputs/S18批量验证结果.json'
    target.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'audit':audit,'synthetic_summary':summaries},ensure_ascii=False),flush=True)


if __name__ == '__main__':
    run()
