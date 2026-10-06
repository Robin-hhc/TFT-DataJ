"""Map observed or manually selected names to DataJ's query identities.

The website combines raw hero stars by /^([1-4])(.+)$/ and traits by
checkId. Canonical IDs are never normalized a second time. Different
visible variants remain separate; a bare catalog ID cannot authorize an
indistinguishable same-name entry.
"""
from copy import deepcopy
from dataclasses import dataclass
import re
import unicodedata


KINDS = ('equip', 'hex', 'hero', 'trait')
_CATEGORY_ALIASES = {
    '成装': '成型装备', '成型': '成型装备',
    '神器': '神器装备', '奥恩': '神器装备', '奥恩装备': '神器装备',
    '光明': '光明武器', '光明装备': '光明武器',
    '纹章': '转职纹章', '转职': '转职纹章',
    '散件': '基础装备', '基础': '基础装备', '特殊': '特殊装备',
}
_LEVEL_LABELS = {1: '银色', 2: '金色', 3: '彩色'}


def _text(value):
    if not isinstance(value, str):
        return ''
    return ''.join(unicodedata.normalize('NFKC', value).split()).casefold()


def _category(value):
    if not isinstance(value, str):
        return ''
    value = value.strip()
    return _CATEGORY_ALIASES.get(value, value)


def _integer(value):
    if isinstance(value, bool):
        return None
    try:
        text = str(value).strip()
        return int(text) if re.fullmatch(r'[0-9]+', text) else None
    except (ValueError, TypeError):
        return None


def _observable_key(kind, row):
    name = _text(row.get('name'))
    if kind == 'hero':
        return name, _text(row.get('tag')), _text(row.get('skillName')), _text(row.get('skillDesc'))
    if kind == 'hex':
        return name, _integer(row.get('level')), _text(row.get('descText'))
    if kind == 'equip':
        return name, _category(row.get('type')), _text(row.get('descText')), _text(row.get('basicDesc'))
    return name, _integer(row.get('num')), _text(row.get('realDesc'))


@dataclass(frozen=True)
class Resolution:
    status: str
    kind: str | None = None
    entity: dict | None = None
    candidates: tuple = ()
    reason: str = ''

    @property
    def confirmed(self):
        return self.status == 'resolved' and self.entity is not None


def display_label(kind, row):
    """Readable observed distinctions, never an arbitrary ID disambiguator."""
    parts = [row.get('name', '')]
    if kind == 'hero' and row.get('tag'):
        parts.append(str(row['tag']))
    elif kind == 'hex' and _integer(row.get('level')) in _LEVEL_LABELS:
        parts.append(_LEVEL_LABELS[_integer(row['level'])])
    elif kind == 'equip' and row.get('category', row.get('type')):
        parts.append(str(row.get('category', row.get('type'))))
    elif kind == 'trait' and row.get('num') is not None:
        parts.append(f"{row['num']}人")
    if row.get('identity_selectable') is False:
        parts.append('身份待确认')
    elif row.get('identity_detail'):
        parts.append(row['identity_detail'])
    return ' · '.join(parts)


class EntityResolver:
    def __init__(self, catalog, set_id=18):
        data = catalog.get('data', catalog) if isinstance(catalog, dict) else {}
        data = data if isinstance(data, dict) else {}
        self.set_id = str(set_id)
        self.catalog = {}
        self._names = {}
        self._ids = {}
        for kind in KINDS:
            rows = []
            supplied_rows = data.get(kind, [])
            for raw in supplied_rows if isinstance(supplied_rows, list) else []:
                if not isinstance(raw, dict) or not isinstance(raw.get('name'), str) or not raw['name'].strip():
                    continue
                identity = str(raw.get('id', ''))
                if not re.fullmatch(r'[1-9][0-9]*', identity):
                    continue
                if raw.get('setId') is not None and str(raw['setId']) != self.set_id:
                    continue
                row = deepcopy(raw)
                row['id'] = identity
                row['name'] = row['name'].strip()
                row['kind'] = kind
                row['source_ids'] = [identity]
                if kind == 'hero':
                    if str(row.get('heroType', 0)) != '0':
                        continue
                    if row.get('price') is not None and (_integer(row['price']) or 0) <= 0:
                        continue
                    match = re.fullmatch(r'([1-4])(.+)', identity)
                    row['id'] = match[2] if match else identity
                    row['_source_tier'] = int(match[1]) if match else 0
                elif kind == 'equip':
                    row['category'] = _category(row.get('type'))
                elif kind == 'trait':
                    check_id = str(row.get('checkId', identity)).strip()
                    if not re.fullmatch(r'[1-9][0-9]*', check_id) or _integer(row.get('num')) is None:
                        continue
                    row['id'] = check_id
                    row['num'] = _integer(row['num'])
                rows.append(row)
            if kind == 'hero':
                rows = self._combine_heroes(rows)
            elif kind == 'trait':
                rows = self._combine_traits(rows)
            self.catalog[kind] = rows
            names, identities, visible = {}, {}, {}
            for row in rows:
                names.setdefault(_text(row['name']), []).append(row)
                visible.setdefault(_observable_key(kind, row), []).append(row)
                for identity in dict.fromkeys([row['id'], *row['source_ids']]):
                    identities.setdefault(identity, []).append(row)
            self._names[kind] = names
            self._ids[kind] = identities
            for row in rows:
                peers = visible[_observable_key(kind, row)]
                same_name = names[_text(row['name'])]
                missing_form = kind == 'hero' and len(same_name) > 1 and not any(
                    row.get(field) for field in ('tag', 'skillName', 'skillDesc'))
                row['identity_selectable'] = len(peers) == 1 and not missing_form
                row['identity_detail'] = self._description_label(kind, row, same_name)

    def entries(self, kind):
        return deepcopy(self.catalog.get(kind, []))

    @staticmethod
    def _combine_heroes(rows):
        groups = {}
        for row in rows:
            groups.setdefault(row['id'], []).append(row)
        result = []
        for variants in groups.values():
            variants.sort(key=lambda row: row['_source_tier'])
            first = next((row for row in variants if row['_source_tier'] == 1), variants[0])
            row = deepcopy(first)
            row.pop('_source_tier', None)
            row['source_ids'] = list(dict.fromkeys(source for variant in variants for source in variant['source_ids']))
            result.append(row)
        return result

    @staticmethod
    def _combine_traits(rows):
        result = {}
        for row in rows:
            key = row['id'], row['num']
            if key in result:
                result[key]['source_ids'].extend(row['source_ids'])
            else:
                result[key] = row
        return list(result.values())

    @staticmethod
    def _description_label(kind, row, rows):
        if kind not in ('hex', 'equip', 'hero'):
            return ''
        same_context = [other for other in rows if other is not row and _text(other['name']) == _text(row['name'])
                        and (kind != 'hex' or _integer(other.get('level')) == _integer(row.get('level')))
                        and (kind != 'equip' or other.get('category') == row.get('category'))
                        and (kind != 'hero' or _text(other.get('tag')) == _text(row.get('tag')))]
        if not same_context or any(_observable_key(kind, row) == _observable_key(kind, other) for other in same_context):
            return ''
        if kind=='hero' and row.get('skillName') and all(row['skillName']!=other.get('skillName') for other in same_context):
            return row['skillName']
        field = 'skillDesc' if kind == 'hero' else 'descText'
        description = row.get(field) or ''
        for term in re.findall(r'【([^】]+)】', description):
            if all(term not in (other.get(field) or '') for other in same_context):
                return term
        # The complete description remains available for tooltip/dialog review.
        return '描述不同'

    def _identified_rows(self, kind, entity_id):
        return self._ids.get(kind, {}).get(str(entity_id), [])

    @staticmethod
    def _result(status, kind, rows=(), reason=''):
        candidates = tuple(deepcopy(rows))
        entity = deepcopy(rows[0]) if status == 'resolved' and len(rows) == 1 else None
        return Resolution(status, kind, entity, candidates, reason)

    def resolve(self, kind, name, *, level=None, category=None, description=None,
                tag=None, num=None, entity_id=None):
        """Resolve one complete title plus explicit, already observed context.

        No spelling guess, ranking preference, star rule or acquisition-stage
        rule is added. Description fragments only narrow exact-title matches.
        ``entity_id`` is for reviewed catalog choices, not OCR of a screen ID.
        """
        if kind not in KINDS:
            return self._result('unknown', kind, reason='不支持的条件类型')
        title = _text(name)
        if not title:
            return self._result('unknown', kind, reason='名称未确认')
        rows = self._names[kind].get(title, [])
        if not rows:
            return self._result('unknown', kind, reason='目录中未找到完整名称')
        if level is not None:
            rows = [row for row in rows if kind == 'hex' and _integer(level) is not None
                    and _integer(row.get('level')) == _integer(level)]
        if category is not None:
            rows = [row for row in rows if kind == 'equip' and row.get('category') == _category(category)]
        if tag is not None:
            rows = [row for row in rows if kind == 'hero' and _text(row.get('tag')) == _text(tag)]
        if num is not None:
            rows = [row for row in rows if kind == 'trait' and _integer(num) is not None
                    and row.get('num') == _integer(num)]
        if description is not None:
            evidence = _text(description)
            if evidence:
                field = 'skillDesc' if kind == 'hero' else 'realDesc' if kind == 'trait' else 'descText'
                rows = [row for row in rows if evidence in _text(row.get(field))]
        if not rows:
            return self._result('unknown', kind, reason='名称与品质、类别、形态或描述证据不一致')
        if entity_id is not None:
            identified = self._identified_rows(kind, entity_id)
            chosen = [row for row in rows if any(row is known for known in identified)]
            if not chosen:
                return self._result('unknown', kind, reason='目录身份未确认或与名称上下文冲突')
            # ID choice is allowed only if its visible identity is different.
            indistinguishable = [row for row in rows if any(_observable_key(kind, row) == _observable_key(kind, candidate)
                                                         for candidate in chosen)]
            if len(indistinguishable) > len(chosen):
                return self._result('ambiguous', kind, indistinguishable, '同名目录项无法用可见信息区分，暂不查询')
            if any(row['identity_selectable'] is False for row in chosen):
                return self._result('ambiguous', kind, rows, '同名形态缺少可核实信息，无法区分')
            rows = chosen
        if len(rows) > 1:
            identical = len({_observable_key(kind, row) for row in rows}) == 1
            reason = '同名目录项无法用可见信息区分，暂不查询' if identical else '需要确认品质、类别、形态或描述差异'
            return self._result('ambiguous', kind, rows, reason)
        return self._result('resolved', kind, rows, '已确认唯一目录身份')

    def resolve_selection(self, kind, row):
        """Validate a manually picked catalog row; never trust supplied IDs alone."""
        if not isinstance(row, dict) or row.get('id') is None or not isinstance(row.get('name'), str):
            return self._result('unknown', kind, reason='目录选择不完整')
        if row.get('setId') is not None and str(row['setId']) != self.set_id:
            return self._result('unknown', kind, reason='目录选择不属于当前赛季')
        context = {}
        if kind == 'hex' and row.get('level') is not None:
            context['level'] = row['level']
        if kind == 'hero' and row.get('tag') is not None:
            context['tag'] = row['tag']
        if kind == 'equip':
            category = row.get('category', row.get('type'))
            if row.get('category') is not None and row.get('type') is not None and _category(row['category']) != _category(row['type']):
                return self._result('unknown', kind, reason='装备类别信息冲突')
            if category is not None:
                context['category'] = category
        if kind == 'trait' and row.get('num') is not None:
            context['num'] = row['num']
        if kind in ('hex', 'equip') and row.get('descText'):
            context['description'] = row['descText']
        return self.resolve(kind, row['name'], entity_id=row['id'], **context)

    def resolve_any(self, name, *, level=None, category=None, description=None,
                    tag=None, num=None, entity_id=None):
        """Resolve a tooltip title whose supported type may still be unknown."""
        allowed = set(KINDS)
        for value, kind in ((level, 'hex'), (category, 'equip'), (tag, 'hero'), (num, 'trait')):
            if value is not None:
                allowed &= {kind}
        results = [self.resolve(kind, name, level=level, category=category, description=description,
                                tag=tag, num=num, entity_id=entity_id)
                   for kind in KINDS if kind in allowed]
        matches = [result for result in results if result.status != 'unknown']
        if len(matches) == 1:
            return matches[0]
        if not matches:
            return self._result('unknown', None, reason='名称或详情类型未确认')
        candidates = tuple(row for result in matches for row in result.candidates)
        return self._result('ambiguous', None, candidates, '不同类型存在同名条件，需要确认详情类型')
