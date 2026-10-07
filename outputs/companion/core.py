"""Session identity and conservative, season-local candidate resolution."""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass, field
import re
from urllib.parse import urlparse
from uuid import uuid4
import bootstrap
from choice_reader import normalize_name


@dataclass
class Session:
    set_id: int = 18
    patch: str = '18.2a'
    session_id: str = field(default_factory=lambda: uuid4().hex)
    revision: int = 0
    stage: str | None = None
    choices: tuple = ()
    target: str | None = None

    def token(self):
        return self.session_id, self.revision, self.set_id, self.patch, self.target

    def accepts(self, token):
        return token == self.token()

    def invalidate(self):
        self.revision += 1
        self.choices = ()
        self.stage = None

    def set_choices(self, stage, ids):
        self.invalidate()
        self.stage, self.choices = stage, tuple(ids)

    def set_target(self, comp_id):
        self.invalidate()
        self.target = comp_id

    def reset(self):
        self.session_id = uuid4().hex
        self.target = None
        self.invalidate()


def resolve_name(readings, catalog):
    """Views are OCR outputs, not fuzzy substitutions or aliases inferred from stats."""
    counts = Counter(normalize_name(x) for x in readings if x)
    valid = {name: [r for r in catalog if normalize_name(r['name']) == name]
             for name in counts}
    valid = {name:rows for name,rows in valid.items() if rows}
    if len(valid) > 1:
        return {'status':'conflict','candidates':[r for rows in valid.values() for r in rows]}
    if not valid:
        return {'status':'unrecognized','candidates':[]}
    name, matches = next(iter(valid.items()))
    if len(matches) != 1:
        return {'status':'ambiguous','candidates':matches}
    if counts[name] < 2:
        return {'status':'unrecognized','candidates':matches}
    return {'status':'resolved','id':str(matches[0]['id']),'name':matches[0]['name'], 'candidates':matches}


def _unique_terms(terms):
    return [own-set().union(*(other for j,other in enumerate(terms) if j!=i))
            for i,own in enumerate(terms)]


def _description_evidence(candidates):
    descriptions=[normalize_name(row.get('descText','')) for row in candidates]
    entities=_unique_terms([set(re.findall(r'【([^【】]{2,20})】',text)) for text in descriptions])
    numbers=_unique_terms([set(re.findall(r'(?<![\d.])\d+(?:\.\d+)?%?[\u4e00-\u9fff]{2,8}',text))
                           for text in descriptions])
    return entities,numbers


def description_terms(candidates):
    """Distinct entities or complete number/unit phrases, never isolated digits."""
    entities,numbers=_description_evidence(candidates)
    return [words|values for words,values in zip(entities,numbers)]


def _description_hits(text,entities,numbers):
    evidence={}
    for i,(words,values) in enumerate(zip(entities,numbers)):
        named={word for word in words if word in text}
        counted={value for value in values if re.search(r'(?<![\d.])'+re.escape(value),text)}
        if named or counted:evidence[i]=(named,counted)
    return evidence


def resolve_description(resolution, readings):
    candidates=resolution.get('candidates',[])
    if resolution.get('status')!='ambiguous' or len(readings)!=2:return resolution
    entities,numbers=_description_evidence(candidates)
    matches=[_description_hits(text,entities,numbers)
             for text in map(normalize_name,readings)]
    # Even one opposing term vetoes the identity. The same discriminating
    # entity or two complete numeric phrases must be reproduced in both views.
    if len(matches[0])!=1 or set(matches[0])!=set(matches[1]):return resolution
    index=next(iter(matches[0]))
    left_named,left_numbers=matches[0][index];right_named,right_numbers=matches[1][index]
    if not (left_named&right_named) and len(left_numbers&right_numbers)<2:return resolution
    candidate=candidates[index]
    title=resolve_name(resolution.get('readings',[]),[candidate])
    if title['status']!='resolved':return resolution
    return {**title,'method':'name_and_description_two_views',
            'readings':resolution['readings'],'description_readings':readings}


def parse_comp_url(value):
    url = urlparse(value.strip())
    if url.scheme != 'https' or url.netloc != 'www.dataj.cc' or url.query or url.fragment:
        raise ValueError('请粘贴 https://www.dataj.cc/comp/数字 形式的阵容地址')
    match = re.fullmatch(r'/comp/([1-9][0-9]*)/?', url.path)
    if not match:
        raise ValueError('阵容地址格式不正确')
    return match[1]
