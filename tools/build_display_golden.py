"""Explicit golden proposal from captured responses and documented site rules.

No application imports. Review this output before accepting it into fixtures.
This is not invoked by tests or the collector; changed upstream data never
silently rewrites expectations. Evidence level: API plus verified display rules.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
from collect_display_fixtures import key


def metric(row):
    if row is None or row['sampleCount']==0:return '暂无数据'
    return f"{row['avgPlacement']:.2f} {row['sampleCount']:,}局"+(' · 少' if row['sampleCount']<50 else '')


def propose(folder):
    matrix=json.loads((folder/'matrix.json').read_text(encoding='utf8'))
    records=[json.loads(f.read_text(encoding='utf8')) for f in sorted(folder.glob('response-*.json'))]
    required={key(r) for r in matrix['requests']}
    records=[r for r in records if key(r['request']) in required or r['request']['path']=='/gamedata'
             or (r['request']['path'].startswith('/comp/') and r['request']['path'].count('/')==2)]
    catalog=next(r['data'] for r in records if r['request']['path']=='/gamedata')
    types={str(r['id']):r['type'] for r in catalog['equip']}
    for record in records:
        req=record['request'];path=req['path'];data=record['data'];expected={}
        version=req.get('params',{}).get('gameVersion') or req.get('body',{}).get('version')
        if path in ['/explorer/query','/comp/rank']:
            rows=data['comps'] if isinstance(data,dict) else data
            expected['item_by_comp']={str(r['compId']):metric(r) for r in rows}
            rows=[r for r in rows if r['sampleCount']>=50]
            for order in ['average','samples']:
                ordered=sorted(rows,key=lambda r:r['avgPlacement'] if order=='average' else -r['sampleCount'])
                expected[order]=[{'id':str(r['compId']),'name':r['name'],
                    'metrics':[f"{r['avgPlacement']:.2f}",f"{r['top4Rate']:.1f}%",f"{r['topRate']:.1f}%"],
                    'samples':f"{r['sampleCount']:,} 局"} for r in ordered]
        elif path.endswith('/hexes') or path=='/stats/hex':
            rows=data['hexes'] if isinstance(data,dict) else data
            for rune in matrix['hexes']:
                entity=str(rune['id']);matches=[r for r in rows if str(r['hexId'])==entity]
                expected[entity]={}
                for index,stage in enumerate(['2-1','3-2','4-2']):
                    candidates=[r for r in matches[0]['roundStats'] if r['round']==index and r['roundLabel']==stage] if len(matches)==1 else []
                    expected[entity][stage]=(f"{candidates[0]['avgPlacement']:.2f} · {candidates[0]['sampleCount']}局"+(' · 少' if candidates[0]['sampleCount']<50 else '')
                        if len(candidates)==1 and candidates[0]['sampleCount']>0 else '— 无该阶段数据' if len(matches)==1 else '— 无数据/未识别')
        elif path.endswith('/hero-equips'):
            for form in ['heroEquips','hero3Equips']:
                expected[form]={}
                for kind in ['全部','成型装备','神器装备','光明武器','转职纹章','特殊装备']:
                    rows=[r for r in data[form] if r['sampleCount']>=50 and (kind=='全部' or any(types.get(str(e['id']))==kind for e in r['equips']))]
                    rows=sorted(rows,key=lambda r:r['avgPlacement'])
                    expected[form][kind]=[['/'.join(e['name'] for e in r['equips']),f"{r['avgPlacement']:.2f}",str(r['sampleCount'])] for r in rows]
        elif path.endswith('/equip-heroes') or path.endswith('/heroes'):
            rows=data['heroes'] if isinstance(data,dict) else data
            allowed=None
            if isinstance(data,dict):allowed={str(h['heroId']) for h in matrix['comps'][version+':'+str(data['compId'])]['heroes']}
            rows=sorted([r for r in rows if r['sampleCount']>=50 and (allowed is None or str(r['heroId']) in allowed)],
                        key=lambda r:(r['avgPlacement'],-r['sampleCount'],str(r['heroId'])))[:2]
            expected={'holders':[{'id':str(r['heroId']),'name':r.get('heroName',r.get('name','?')),'average':r['avgPlacement'],'samples':r['sampleCount']} for r in rows]}
        elif path.endswith('/equips') or path=='/stats/equip':
            rows=data['equips'] if isinstance(data,dict) else data
            expected={str(item['id']):metric(next((r for r in rows if str(r['equipId'])==str(item['id'])),None)) for item in matrix['items']}
        record['expected']=expected
    # Keep only public fields used by the actual UI, reducing catalog weight.
    fields={'id','name','level','heroType','picture','price','type','num','descText','icon'}
    for record in records:
        if record['request']['path']=='/gamedata':
            record['data']={k:[{f:v for f,v in r.items() if f in fields} for r in catalog[k]] for k in ['hex','hero','equip','trait']}
        elif record['request']['path']=='/explorer/query':record['data']={'comps':record['data']['comps']}
        record['projected_sha256']=hashlib.sha256(json.dumps(record['data'],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    present={key(r['request']) for r in records}
    missing=[{'request':r,'status':'source_unavailable' if (folder/f'unavailable-{key(r)}.json').exists() else 'not_run'}
             for r in matrix['requests'] if key(r) not in present]
    return {'schema':1,'reference':'DataJ API + front-end minimum sample 50, stage roundLabel/round, direct aggregate scopes; not website DOM comparison',
            'matrix':matrix,'records':records,'gaps':missing}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--capture',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():p.error('Refusing to overwrite a golden proposal; choose a new path')
    result=propose(args.capture)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes(gzip.compress(json.dumps(result,ensure_ascii=False).encode(),mtime=0))
    print(json.dumps({'records':len(result['records']),'gaps':len(result['gaps']),'bytes':args.output.stat().st_size}))
