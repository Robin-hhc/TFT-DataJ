"""Read fixed-composition augment stages, supplementing exact missing records.

DataJ's composition table omits some low-sample augments that its explorer
still returns. Each supplement is one exact augment and acquisition stage;
overall statistics and other compositions never stand in for that scope.
"""
from copy import deepcopy

from dataj import DataJ, SourceError
from snapshot_stats import STAGES, stage_stat


def lookup_comp_hexes(adapter, comp, stage, entities, *, on_progress=None, current=lambda:True):
    comp = DataJ.entity_id(comp)
    if stage not in STAGES:
        raise ValueError('unsupported hex stage')
    candidates = {}
    for identity, name in entities:
        if identity is None:
            continue
        identity = DataJ.entity_id(identity)
        if not isinstance(name, str) or not name.strip():
            raise ValueError('unconfirmed hex name')
        name = name.strip()
        if identity in candidates and candidates[identity] != name:
            raise ValueError('conflicting hex identity')
        candidates[identity] = name
        if len(candidates) > 3:
            raise ValueError('too many hex candidates')
    if not current():
        return None
    primary = adapter.hexes(comp)
    if not current():
        return None
    rows = deepcopy(primary['data'])
    supplemented, errors, sources = [], {}, {}
    pending = {identity:name for identity,name in candidates.items()
               if stage_stat(rows, identity, stage)['status'] in (
                   'missing_or_ambiguous_entity', 'no_stage_data')}

    def snapshot():
        # Every queued UI update owns its rows: later completions cannot mutate
        # a snapshot that the GUI thread has not consumed yet.
        return {**primary, 'data':deepcopy(rows),
                'supplemented_ids':[identity for identity in candidates if identity in supplemented],
                'supplement_errors':dict(errors), 'supplement_sources':deepcopy(sources),
                'pending_ids':list(pending)}

    if pending and on_progress:
        on_progress(snapshot())
    for identity, result, error in adapter.iter_comp_hex_supplements(
            comp, stage, list(pending.items()), current=current):
        if not current():
            return None
        name = candidates[identity]
        pending.pop(identity, None)
        try:
            if error:
                raise error
            matches = [row for row in result['data']['comps'] if str(row.get('compId')) == str(comp)]
            if not matches:
                if on_progress:on_progress(snapshot())
                continue
            if len(matches) != 1:
                raise SourceError('阵容补查身份重复')
            selected = matches[0]
            if selected['sampleCount'] == 0:
                if on_progress:on_progress(snapshot())
                continue
            part = {'round':STAGES[stage], 'roundLabel':stage,
                    'avgPlacement':selected['avgPlacement'], 'sampleCount':selected['sampleCount']}
            row = next((row for row in rows if str(row['hexId']) == identity), None)
            if row is None:
                row = {'hexId':identity, 'name':name, 'roundStats':[]}
                rows.append(row)
            row['roundStats'].append(part)
            row['rounds'] = list(dict.fromkeys(part['roundLabel'] for part in row['roundStats']))
            supplemented.append(identity)
            sources[identity] = {'source':result['source'], 'fetched_at':result['fetched_at'],
                                 'cached':result['cached'], 'sample_count':selected['sampleCount'],
                                 'scope':{'set_id':adapter.set_id, 'patch':adapter.patch,
                                          'comp':str(comp), 'stage':stage, 'hex_id':identity}}
        except SourceError:
            errors[identity] = '阵容阶段补查暂不可用'
        if on_progress:on_progress(snapshot())
    return snapshot() if current() else None
