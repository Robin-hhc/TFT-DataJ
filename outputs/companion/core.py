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


def parse_comp_url(value):
    url = urlparse(value.strip())
    if url.scheme != 'https' or url.netloc != 'www.dataj.cc' or url.query or url.fragment:
        raise ValueError('请粘贴 https://www.dataj.cc/comp/数字 形式的阵容地址')
    match = re.fullmatch(r'/comp/([1-9][0-9]*)/?', url.path)
    if not match:
        raise ValueError('阵容地址格式不正确')
    return match[1]
