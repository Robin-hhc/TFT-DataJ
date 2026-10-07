"""Project indistinguishable DataJ aliases onto one version's data identity.

Statistics identify the row only after the complete same-title group is proven
equivalent. They never choose among different qualities or descriptions.
"""
from collections import defaultdict
from urllib.parse import urlsplit

import bootstrap
from choice_reader import normalize_name
from snapshot_stats import STAGES, stage_stat


def canonical_hex_catalog(catalog, statistics, *, set_id):
    groups = defaultdict(list)
    for row in catalog:
        groups[normalize_name(row['name'])].append(row)
    projected = []
    for rows in groups.values():
        first = rows[0]
        fields = ('name', 'level', 'icon', 'descText', 'setId')
        equivalent = (len(rows) > 1 and str(first.get('level')) in ('1', '2', '3')
                      and str(first.get('setId')) == str(set_id)
                      and all(isinstance(first.get(key), str) and first[key].strip()
                              for key in ('name', 'icon', 'descText'))
                      and all(all(row.get(key) == first.get(key) for key in fields) for row in rows))
        if equivalent:
            ids = {str(row['id']) for row in rows}
            active = [stat for stat in statistics if str(stat.get('hexId')) in ids]
            if (len(active) == 1 and len(ids) == len(rows)
                    and active[0].get('name') == first['name']
                    # Catalog/stats use DataJ and Tencent CDNs respectively.
                    and urlsplit(active[0].get('icon', '')).path.rsplit('/', 1)[-1]
                        == urlsplit(first['icon']).path.rsplit('/', 1)[-1]
                    and any(stage_stat(active, active[0]['hexId'], stage)['status'] == 'ok' for stage in STAGES)):
                chosen = next(row for row in rows if str(row['id']) == str(active[0]['hexId']))
                projected.append({**chosen, 'catalog_alias_ids': sorted(ids)})
                continue
        projected.extend(rows)
    return projected
