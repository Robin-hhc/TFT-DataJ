"""Reviewed set-18 Roman families, explicitly gated by trusted quality context."""
import re
from collections import Counter, defaultdict
from copy import deepcopy
from types import MappingProxyType

import bootstrap
from choice_reader import normalize_name


# Independent reviewed set-18 catalog, canonical SHA256:
# 6554f11c481fc39904f42b7e24a1461f7a51d05e8f63a774bca427467b12ce46.
_REVIEWED_FAMILIES = {'值得等待': (('20021', '值得等待', 2, 'https://img.dataj.cc/images/hex/worththewait2.png'),
          ('30021', '值得等待II', 3, 'https://img.dataj.cc/images/hex/worththewait3.png')),
 '嘀个痛快!': (('1134', '嘀个痛快!I', 1, 'https://img.dataj.cc/images/hex/rollingfordays1.png'),),
 '好事成双': (('2133', '好事成双II', 2, 'https://img.dataj.cc/images/hex/doubletrouble2.png'),),
 '并肩作战': (('1019', '并肩作战I', 1, 'https://img.dataj.cc/images/hex/standunited1.png'),),
 '应急护甲': (('1023', '应急护甲I', 1, 'https://img.dataj.cc/images/hex/makeshift1.png'),
          ('2023', '应急护甲II', 2, 'https://img.dataj.cc/images/hex/makeshift2.png')),
 '投资策略': (('20217', '投资策略I', 2, 'https://img.dataj.cc/images/hex/investmentstrategy2.png'),
          ('30217', '投资策略II', 3, 'https://img.dataj.cc/images/hex/investmentstrategy3.png')),
 '拥抱': (('10615', '拥抱I', 1, 'https://img.dataj.cc/images/hex/grouphugi1.png'),
        ('10616', '拥抱II', 2, 'https://img.dataj.cc/images/hex/grouphugii2.png')),
 '星界赐福': (('2022', '星界赐福II', 2, 'https://img.dataj.cc/images/hex/celestialblessing2.png'),
          ('3022', '星界赐福III', 3, 'https://img.dataj.cc/images/hex/celestialblessing3.png')),
 '有用之材': (('1789', '有用之材I', 1, 'https://img.dataj.cc/images/hex/goodforsomething1.png'),),
 '治疗法球': (('1634', '治疗法球I', 1, 'https://img.dataj.cc/images/hex/healingorbs1.png'),
          ('2634', '治疗法球II', 2, 'https://img.dataj.cc/images/hex/healingorbs2.png')),
 '潘朵拉的装备': (('1007', '潘朵拉的装备I', 1, 'https://img.dataj.cc/images/hex/pandora1.png'),
            ('2007', '潘朵拉的装备II', 2, 'https://img.dataj.cc/images/hex/pandora2.png'),
            ('3007', '潘朵拉的装备III', 3, 'https://img.dataj.cc/images/hex/pandora3.png')),
 '玻璃大炮': (('10253', '玻璃大炮I', 1, 'https://img.dataj.cc/images/hex/glasscannon1.png'),
          ('20253', '玻璃大炮II', 2, 'https://img.dataj.cc/images/hex/glasscannon2.png')),
 '珍藏财宝': (('3486', '珍藏财宝III', 3, 'https://img.dataj.cc/images/hex/buriedtreasureslegend3.png'),),
 '珠光莲花': (('2128', '珠光莲花I', 2, 'https://img.dataj.cc/images/hex/jeweledlotus2.png'),
          ('3128', '珠光莲花II', 3, 'https://img.dataj.cc/images/hex/jeweledlotus3.png')),
 '电火花': (('10708', '电火花I', 1, 'https://img.dataj.cc/images/hex/electrocharging1.png'),
         ('20708', '电火花II', 2, 'https://img.dataj.cc/images/hex/electrocharging2.png')),
 '纵深': (('10750', '纵深I', 1, 'https://img.dataj.cc/images/hex/verticality1.png'),
        ('20750', '纵深II', 2, 'https://img.dataj.cc/images/hex/verticality2.png'),
        ('30750', '纵深III', 3, 'https://img.dataj.cc/images/hex/verticality3.png')),
 '终身黄铜': (('10242', '终身黄铜I', 2, 'https://img.dataj.cc/images/hex/bronzeforlifei2.png'),
          ('20242', '终身黄铜II', 3, 'https://img.dataj.cc/images/hex/bronzeforlifei3.png')),
 '装备百宝袋': (('1006', '装备百宝袋I', 1, 'https://img.dataj.cc/images/hex/itemgrabbag1.png'),),
 '资本利得': (('10755', '资本利得I', 1, 'https://img.dataj.cc/images/hex/capitalgains1.png'),
          ('20755', '资本利得II', 2, 'https://img.dataj.cc/images/hex/capitalgains2.png'))}


def _base_read(text, base):
    # These symbols supply no tier information. Quality is a separate input;
    # a complete legal title is checked independently below and always vetoes.
    return text.startswith(base) and re.fullmatch(r'[IiLl123!|]*', text[len(base):]) is not None


_SCALAR_TYPES = frozenset((str, int, float, bool, bytes, type(None)))
_FAMILY_ROUTE = re.compile(r'(?:' + '|'.join(re.escape(base) for base in _REVIEWED_FAMILIES)
                           + r')[IiLl123!|]*')


def _snapshot_row(original):
    # JSON catalogue values are almost entirely immutable scalars. Copy the
    # dictionary once and deeply copy only mutable/unknown values; preserve
    # snapshot isolation without thousands of deepcopy calls for strings.
    row = dict(original)
    for key, value in row.items():
        if type(value) not in _SCALAR_TYPES:
            row[key] = deepcopy(value)
    return MappingProxyType(row)


class FamilyNameResolver:
    """A private catalogue snapshot for one frame or call, never a global cache.

    Caller edits and returned candidates cannot mutate the copied rows. Names,
    title indexes and ID counts are computed once; each observed family is
    validated lazily against that same snapshot, including invalid competitors.
    """

    @staticmethod
    def has_family_readings(readings):
        """Cheap routing only; this never validates a catalogue or assigns ID."""
        return any(isinstance(text, str) and _FAMILY_ROUTE.fullmatch(normalize_name(text))
                   for text in readings)

    def __init__(self, catalog):
        self._valid = False
        self._family_cache = {}
        if (not isinstance(catalog, list)
                or any(not isinstance(row, dict) or not isinstance(row.get('name'), str)
                       for row in catalog)):
            return
        entries = []
        by_title = defaultdict(list)
        id_counts = Counter()
        for index, original in enumerate(catalog):
            row = _snapshot_row(original)
            title = normalize_name(row['name'])
            if not title:
                return
            entries.append((row, title))
            by_title[title].append((index, row))
            id_counts[str(row.get('id'))] += 1
        self._entries = tuple(entries)
        self._by_title = MappingProxyType({title: tuple(rows) for title, rows in by_title.items()})
        self._id_counts = MappingProxyType(dict(id_counts))
        self._valid = True

    def _family_rows(self, base, expected):
        if base in self._family_cache:
            return self._family_cache[base]
        # Include every literal-base prefix: extra Chinese, an unknown tier or
        # future plus variant must not be discarded to manufacture uniqueness.
        entries = [(row, title) for row, title in self._entries if title.startswith(base)]
        rows = None
        if len(entries) == len(expected):
            signatures = []
            for row, title in entries:
                if (type(row.get('setId')) not in (int, str) or str(row['setId']) != '18'
                        or type(row.get('level')) is not int or row['level'] not in (1, 2, 3)
                        or type(row.get('id')) not in (int, str)
                        or row.get('catalog_alias_ids') not in (None, [])):
                    break
                signatures.append((str(row['id']), title, row['level'], row.get('icon')))
            else:
                if (sorted(signatures) == sorted(expected)
                        and all(self._id_counts.get(identity) == 1
                                for identity, name, level, icon in expected)):
                    rows = tuple(row for row, title in entries)
        self._family_cache[base] = rows
        return rows

    @staticmethod
    def _public_rows(rows):
        return [deepcopy(dict(row)) for row in rows]

    def _conflict(self, reason, rows):
        return {'status': 'conflict', 'reason': reason, 'candidates': self._public_rows(rows)}

    def resolve(self, readings, quality, *, observed_readings=None):
        """Resolve trusted distinct-pixel votes; all observed titles may veto."""
        if type(quality) is not int or quality not in (1, 2, 3):
            return None
        if (not self._valid or not isinstance(readings, (list, tuple))
                or observed_readings is not None and not isinstance(observed_readings, (list, tuple))):
            return None
        texts = [normalize_name(text) for text in readings if isinstance(text, str) and text]
        observed = texts + [normalize_name(text) for text in (observed_readings or [])
                            if isinstance(text, str) and text]
        families = []
        for base, expected in _REVIEWED_FAMILIES.items():
            if not any(_base_read(text, base) for text in observed):
                continue
            rows = self._family_rows(base, expected)
            if rows is None:
                return None
            count = sum(_base_read(text, base) for text in texts)
            families.append((base, rows, count))
        if not families:
            return None
        exact_titles = set(observed).intersection(self._by_title)
        indexed = [entry for title in exact_titles for entry in self._by_title[title]]
        exact = [row for index, row in sorted(indexed, key=lambda entry: entry[0])]
        if len(exact_titles) > 1:
            return self._conflict('title_conflict', exact)
        if any(type(row.get('level')) is not int or row['level'] != quality for row in exact):
            return self._conflict('quality_conflict', exact)
        supported = [(base, rows, count) for base, rows, count in families if count >= 2]
        if len(supported) > 1:
            return self._conflict('family_base_conflict',
                                  [row for base, rows, count in supported for row in rows])
        if not supported:
            return None
        base, rows, count = supported[0]
        matches = [row for row in rows if row['level'] == quality]
        if len(matches) != 1:
            return None
        row = matches[0]
        if any(str(candidate.get('id')) != str(row['id']) for candidate in exact):
            return self._conflict('title_conflict', exact)
        return {'status': 'resolved', 'id': str(row['id']), 'name': row['name'],
                'candidates': self._public_rows(matches), 'method': 'reviewed_family_base_and_quality',
                'family_base': base, 'quality': quality, 'prefix_read_count': count}


def resolve_family_name(readings, catalog, quality, *, observed_readings=None):
    """Fresh-snapshot compatibility entry point for trusted prefix + quality.

    The caller supplies at most one vote per distinct pixel input in ``readings``.
    ``observed_readings`` may contain every trusted OCR output, including repeat
    inputs: complete catalogue titles can veto but cannot add prefix votes.
    Missing evidence or catalogue drift returns None; conflicts never carry ID.
    """
    if type(quality) is not int or quality not in (1, 2, 3):
        return None
    return FamilyNameResolver(catalog).resolve(readings, quality, observed_readings=observed_readings)
