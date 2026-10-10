"""Stage statistics and refresh retention, independent of Qt/display wording."""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass

import bootstrap  # Adds the shared stage-stat module in source and packaged layouts.
from snapshot_stats import stage_stat


@dataclass(frozen=True)
class ResultScope:
    set_id: int
    patch: str
    stage: str
    comp: str | None


@dataclass(frozen=True)
class HexStatistic:
    status: str
    average: float | None = None
    samples: int | None = None
    source: dict | None = None
    supplemented: bool = False

    @property
    def ready(self):
        return self.status == 'ok'


@dataclass(frozen=True)
class HexChoice:
    identity: str | None
    name: str
    global_stat: HexStatistic
    comp_stat: HexStatistic


@dataclass(frozen=True)
class HexResults:
    scope: ResultScope
    choices: tuple[HexChoice, ...]
    retryable: bool
    supplement_errors: dict
    pending_ids: tuple[str, ...]

    @property
    def rows(self):
        """Compatibility/display projection; never used as retained facts."""
        return [[choice.name, statistic_text(choice.global_stat),
                 statistic_text(choice.comp_stat, scope='comp')] for choice in self.choices]

    @property
    def available(self):
        return sum(choice.global_stat.ready or choice.comp_stat.ready for choice in self.choices)

    @property
    def comp_available(self):
        return sum(choice.comp_stat.ready for choice in self.choices)

    @property
    def supplemented_ids(self):
        return list(dict.fromkeys(choice.identity for choice in self.choices if choice.comp_stat.supplemented))

    @property
    def supplement_sources(self):
        return {choice.identity: deepcopy(choice.comp_stat.source) for choice in self.choices
                if choice.comp_stat.supplemented and choice.comp_stat.source is not None}


def statistic_text(stat, *, scope='global'):
    if stat.ready:
        return f'{stat.average:.2f} · {stat.samples}局' + (' · 少' if stat.samples < 50 else '')
    return {'unrecognized': '— 未识别', 'unpinned': '未固定阵容',
            'pending': '阵容数据读取中…', 'error': '阵容补查失败',
            'unavailable': '阵容数据暂不可用', 'no_stage_data': '— 无该阶段数据',
            'missing_or_ambiguous_entity': '— 本阵容暂无统计' if scope == 'comp' else '— 暂无全局统计',
            'unsupported_stage': '— 阶段待确认', 'invalid_stat': '— 统计不可用'}.get(stat.status, '— 统计不可用')


def stat_text(row, *, identified=True, scope='global'):
    """Existing stage_stat display interface, also used by offline UI checks."""
    stat = (HexStatistic(row['status'], row.get('avg_placement'), row.get('sample_count'))
            if identified else HexStatistic('unrecognized'))
    return statistic_text(stat, scope=scope)


def build_hex_results(scope, candidates, global_result, comp_result=None, *, comp_finished=False, previous=None):
    candidates = tuple((str(identity) if identity is not None else None, name) for identity, name in candidates)
    errors = dict(comp_result.get('supplement_errors', {})) if comp_result else {}
    pending = tuple(comp_result.get('pending_ids', ())) if comp_result else ()
    supplemented = set(map(str, comp_result.get('supplemented_ids', ()))) if comp_result else set()
    sources = comp_result.get('supplement_sources', {}) if comp_result else {}
    can_retain = (previous is not None and previous.scope == scope and not comp_finished
                  and tuple(choice.identity for choice in previous.choices) == tuple(identity for identity, _ in candidates))

    def read(result, identity, *, comp=False):
        row = stage_stat(result['data'], identity, scope.stage)
        provenance = {key: deepcopy(result[key]) for key in ('source', 'fetched_at', 'cached') if key in result}
        provenance['scope'] = {'set_id': scope.set_id, 'patch': scope.patch, 'stage': scope.stage,
                               'comp': scope.comp if comp else None, 'hex_id': identity}
        is_supplemented = comp and identity in supplemented
        if is_supplemented and identity in sources:
            provenance = deepcopy(sources[identity])
        return HexStatistic(row['status'], row.get('avg_placement'), row.get('sample_count'),
                            provenance, is_supplemented and row['status'] == 'ok')

    choices = []
    for index, (identity, name) in enumerate(candidates):
        global_stat = read(global_result, identity) if identity is not None else HexStatistic('unrecognized')
        comp_stat = read(comp_result, identity, comp=True) if comp_result and identity is not None else None
        if not scope.comp:
            comp_stat = HexStatistic('unpinned')
        elif identity is None:
            comp_stat = HexStatistic('unrecognized')
        elif not (comp_stat and comp_stat.ready):
            if identity in errors:
                comp_stat = HexStatistic('error')
            elif identity in pending:
                comp_stat = HexStatistic('pending')
            elif comp_stat is None:
                comp_stat = HexStatistic('unavailable' if comp_finished else 'pending')
            if can_retain and previous.choices[index].comp_stat.ready:
                comp_stat = previous.choices[index].comp_stat
        choices.append(HexChoice(identity, name, global_stat, comp_stat))
    return HexResults(scope, tuple(choices), bool(scope.comp and comp_finished and (comp_result is None or errors)),
                      errors, pending)
