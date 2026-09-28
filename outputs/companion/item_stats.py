"""Single-item scope and holder ranking; no averaging across overlapping samples."""
from dataj import DataJ, SourceError


def query_key(adapter,kind,scope):
    # Object addresses are reusable after patch switches; use source dimensions.
    return adapter.set_id,adapter.patch,kind,scope


def item_stat(result, equip, comp=None):
    data=result['data']
    rows=data.get('equips',[]) if comp else data
    row=next((r for r in rows if str(r['equipId'])==str(equip)),None)
    return stat_value(row,result)


def stat_value(row,result):
    if not row or row.get('sampleCount',0)==0:
        return {'status':'missing'}
    DataJ.validate_item_rows([{**row,'equipId':1}],'equipId')
    return {'status':'ok','average':row['avgPlacement'],'samples':row['sampleCount'],
            'source':result['source'],'fetched_at':result['fetched_at']}


def fallback_stat(result, comp):
    rows=[r for r in result['data']['comps'] if str(r['compId'])==str(comp)]
    if len(rows)>1:raise SourceError('阵容检索结果重复')
    return stat_value(rows[0] if rows else None,result)


def best_holders(result, hero_ids=None, minimum=50):
    rows=result['data']['heroes'] if isinstance(result['data'],dict) else result['data']
    DataJ.validate_item_rows(rows,'heroId')
    allowed=None if hero_ids is None else {str(i) for i in hero_ids}
    rows=[r for r in rows if r['sampleCount']>=minimum
          and (allowed is None or str(r['heroId']) in allowed)]
    rows=sorted(rows,key=lambda r:(r['avgPlacement'],-r['sampleCount'],str(r['heroId'])))[:2]
    return [{'id':str(r['heroId']),'name':r.get('heroName',r.get('name','?')),
             'average':r['avgPlacement'],'samples':r['sampleCount']} for r in rows]
