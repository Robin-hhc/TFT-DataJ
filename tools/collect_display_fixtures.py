"""Explicit, bounded public DataJ capture. Never updates accepted golden files.

Run again with the same output directory to resume the next <=20 requests.
Raw response hashes refer to response bytes, not JSON reserialization.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import time
import httpx

ROOT=Path(__file__).resolve().parents[1]
BASE='https://www.dataj.cc/api/web'

class BatchLimit(Exception):
    pass

class CaptureStopped(Exception):
    pass


def query(path, version, **params):
    return {'method':'GET','path':path,'params':{'setId':18,**({'gameVersion':version} if version else {}),**params}}


def explorer(version, kind, entity):
    rule={'starCount':'','type':kind,'targetId':str(entity['id']),'enable':True,
          'targetName':entity['name'],'hexRound':'','nameMatch':False,
          'equipCarry':'','equipCount':'','exclude':False}
    if kind=='trait':rule['traitLevel']=str(entity['num'])
    return {'method':'POST','path':'/explorer/query','body':{'version':version,'setId':18,
            'filter':{'rules':[rule],'combinator':'and'}}}


def key(request):
    return hashlib.sha256(json.dumps(request,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:20]


def validate_shape(req,data):
    path=req['path']
    if path=='/gamedata':
        assert isinstance(data,dict) and all(isinstance(data.get(k),list) for k in ['hex','hero','equip','trait'])
    elif path=='/explorer/query':assert isinstance(data,dict) and isinstance(data.get('comps'),list)
    elif path.startswith('/stats/') or path=='/comp/rank':assert isinstance(data,list)
    else:
        assert isinstance(data,dict) and str(data.get('compId'))==path.split('/')[2]
        field={'hexes':'hexes','equips':'equips','equip-heroes':'heroes','hero-equips':'heroEquips'}.get(path.split('/')[-1],'heroes')
        assert isinstance(data.get(field),list)
        if path.endswith('/hero-equips'):
            assert isinstance(data.get('hero3Equips'),list) and str(data.get('heroId'))==req['params']['heroId']
        if path.endswith('/equip-heroes'):assert str(data.get('equipId'))==req['params']['equipId']


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--versions',nargs=2,default=['18.2a','18.2'])
    p.add_argument('--limit',type=int,default=20)
    p.add_argument('--retry-unavailable',action='store_true')
    args=p.parse_args()
    if not 1<=args.limit<=20:p.error('--limit must be 1..20')
    accepted=(ROOT/'outputs/companion/fixtures').resolve()
    if args.output.resolve().is_relative_to(accepted):p.error('Capture into work/, never accepted fixtures')
    args.output.mkdir(parents=True,exist_ok=True)
    records={}
    for f in args.output.glob('response-*.json'):
        row=json.loads(f.read_text(encoding='utf8'));records[key(row['request'])]=row
    calls=0;last=0
    def fetch(req):
        nonlocal calls,last
        ident=key(req)
        if ident in records:return records[ident]['data']
        if calls>=args.limit:raise BatchLimit()
        time.sleep(max(0,1-(time.monotonic()-last)))
        calls+=1
        try:
            with httpx.Client(timeout=25,follow_redirects=False) as c:
                r=c.request(req['method'],BASE+req['path'],params=req.get('params'),json=req.get('body'))
            last=time.monotonic();r.raise_for_status();payload=r.json()
            if payload.get('success') is not True or payload.get('code')!=200 or 'data' not in payload:
                raise ValueError('source schema changed')
            validate_shape(req,payload['data'])
            row={'request':req,'source':str(r.url),'captured_at':datetime.now(timezone.utc).isoformat(),
                 'sha256':hashlib.sha256(r.content).hexdigest(),'data':payload['data']}
            (args.output/f'raw-{ident}.json').write_bytes(r.content)
            (args.output/f'response-{ident}.json').write_text(json.dumps(row,ensure_ascii=False),encoding='utf8')
            records[ident]=row
            print(f'{calls}/{args.limit} {req["path"]}',flush=True)
            return row['data']
        except Exception as exc:
            failure={'status':'source_unavailable','request':req,'error':str(exc),'captured_at':datetime.now(timezone.utc).isoformat()}
            (args.output/f'unavailable-{ident}.json').write_text(json.dumps(failure,ensure_ascii=False,indent=2),encoding='utf8')
            (args.output/'batch-status.json').write_text(json.dumps(failure,ensure_ascii=False,indent=2),encoding='utf8')
            raise CaptureStopped(str(exc)) from exc
    try:
        catalog=fetch(query('/gamedata',None));rng=random.Random(180928)
        def pick(kind,predicate,count,seeds=()):
            pool=[r for r in catalog[kind] if predicate(r)]
            chosen=[next(r for r in pool if str(r['id'])==str(i)) for i in seeds]
            rest=[r for r in pool if str(r['id']) not in {str(x['id']) for x in chosen}]
            return chosen+rng.sample(rest,count-len(chosen))
        conditions=[]
        ordinary=pick('equip',lambda r:r['type']=='成型装备',4,['2004'])
        emblems=pick('equip',lambda r:r['type']=='转职纹章',4,['41806'])
        hexes=pick('hex',lambda r:True,4,['20778','1023','30668'])
        heroes=pick('hero',lambda r:r.get('heroType')==0 and r.get('price',0)>0,4,['14503'])
        # Include different breakpoints of one trait as well as other identities.
        traits=catalog['trait'][:2]+rng.sample(catalog['trait'][2:],2)
        for kind,rows in [('equip',ordinary),('equip',emblems),('hex',hexes),('hero',heroes),('trait',traits)]:
            conditions += [{'kind':kind,'entity':r} for r in rows]
        choices=[]
        for kind,seed in [('成型装备','2004'),('神器装备','6052'),('光明武器','2059')]:
            choices+=pick('equip',lambda r:r['type']==kind,3,[seed])
        runes=[]
        for level,seeds in [(1,['1023']),(2,['20778','30668']),(3,[])]:
            runes+=pick('hex',lambda r:r['level']==level,3,seeds)
        matrix={'seed':180928,'versions':args.versions,'conditions':conditions,'items':choices,'hexes':runes,'comps':{}}
        requests=[]
        for v in args.versions:
            requests.append(query('/comp/rank',v,minSample=50))
            for cond in conditions:requests.append(explorer(v,cond['kind'],cond['entity']))
            for comp in [None,'112','120','100']:
                requests.append(query(f'/comp/{comp}/hexes' if comp else '/stats/hex',v))
                requests.append(query(f'/comp/{comp}/equips' if comp else '/stats/equip',v))
                if comp:
                    detail=fetch(query(f'/comp/{comp}',v));matrix['comps'][v+':'+comp]=detail
                    members=detail['heroes']
                    carry=next(h for h in members if h.get('isCarry'))
                    tank=next(h for h in members if str(h['heroId'])=={'112':'4503','120':'3500','100':'3500'}[comp])
                    for hero in [carry,tank]:requests.append(query(f'/comp/{comp}/hero-equips',v,heroId=str(hero['heroId'])))
                for index,item in enumerate(choices):
                    requests.append(query(f'/comp/{comp}/equip-heroes' if comp else f'/stats/equip/{item["id"]}/heroes',v,**({'equipId':str(item['id'])} if comp else {})))
            for item in choices:requests.append(explorer(v,'equip',item))
        matrix['requests']=sorted({key(r):r for r in requests}.values(),key=lambda r:r['method']=='POST')
        (args.output/'matrix.json').write_text(json.dumps(matrix,ensure_ascii=False),encoding='utf8')
        for req in matrix['requests']:
            if (args.output/f'unavailable-{key(req)}.json').exists() and not args.retry_unavailable:continue
            fetch(req)
        missing=[r for r in matrix['requests'] if key(r) not in records]
        status='source_unavailable' if missing else 'complete'
    except BatchLimit:status='batch_limit'
    except CaptureStopped:status='source_unavailable'
    (args.output/'batch-status.json').write_text(json.dumps({'status':status,'requests_this_batch':calls,'captured':len(records)},indent=2),encoding='utf8')
    print(status,len(records),flush=True)
    return 2 if status=='source_unavailable' else 0


if __name__=='__main__':raise SystemExit(main())
