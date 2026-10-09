"""Keep exact augment statistics for one pinned composition and game."""
from __future__ import annotations

import re
import threading
import time
from copy import deepcopy
from contextlib import contextmanager

from dataj import DataJ, SourceError


STAGES = ('2-1', '3-2', '4-2')


class HexPrewarm:
    def __init__(self, adapter, comp, *, current=lambda: True, interval=1.0):
        self.adapter = adapter
        self.comp = DataJ.entity_id(comp)
        self.set_id, self.patch = adapter.set_id, adapter.patch
        self.current = current
        self.interval = max(1.0, float(interval))
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._cancelled = threading.Event()
        self._worker = None
        self._tables = {}
        self._exact = {}
        self._pending = []
        self._stages = STAGES
        self._next_background = 0.0
        self._status = 'idle'
        self._error = None
        self._interactive = 0

    def _current(self):
        return (not self._cancelled.is_set() and self.current()
                and (self.adapter.set_id, self.adapter.patch) == (self.set_id, self.patch))

    @staticmethod
    def _future_stages(round_hint):
        if not isinstance(round_hint, str) or not re.fullmatch(r'[1-9][0-9]*-[1-9][0-9]*', round_hint):
            return STAGES
        round_number = tuple(map(int, round_hint.split('-')))
        return tuple(stage for stage in STAGES
                     if tuple(map(int, stage.split('-'))) >= round_number)

    def start(self, round_hint=None):
        with self._lock:
            if self._cancelled.is_set():return self
            self._stages = self._future_stages(round_hint)
            if self._worker is not None and self._worker.is_alive():
                self._wake.set()
                return self
            self._status, self._error = 'running', None
            self._worker = threading.Thread(target=self._run, name='hex-prewarm', daemon=True)
            self._worker.start()
        return self

    def prioritize(self, round_hint):
        with self._lock:
            self._stages = self._future_stages(round_hint)
            self._pending = [entry for entry in self._pending if entry[1] in self._stages]
        self._wake.set()

    def cancel(self):
        self._cancelled.set()
        with self._lock:
            self._tables.clear()
            self._exact.clear()
            self._pending.clear()
            self._status = 'cancelled'
        self._wake.set()

    def wait(self, timeout=None):
        with self._lock:
            worker = self._worker
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout)
        return worker is None or not worker.is_alive()

    def snapshot(self):
        with self._lock:
            status = 'paused' if self._status == 'running' and self._interactive else self._status
            return {'status': status, 'tables': len(self._tables),
                    'completed': len(self._exact), 'pending': len(self._pending),
                    'error': self._error}

    def begin_interactive(self):
        """Hold background issuance across a whole foreground query group."""
        with self._lock:
            self._interactive += 1
        self._wake.set()
        released = False
        def release():
            nonlocal released
            with self._lock:
                if released:return
                released = True
                self._interactive -= 1
            self._wake.set()
        return release

    @contextmanager
    def interactive(self):
        release = self.begin_interactive()
        try:yield self
        finally:release()

    def hexes(self, comp=None):
        comp = DataJ.entity_id(comp) if comp is not None else None
        if comp is not None and comp != self.comp:
            raise ValueError('composition outside pinned scope')
        with self.interactive():
            if not self._current():return None
            with self._lock:
                result = self._tables.get(comp)
            if result is not None:
                retained = {**deepcopy(result), 'cached': True}
                return retained if self._current() else None
            result = self.adapter.hexes(comp)
            self._remember_table(comp, result)
            return deepcopy(result) if self._current() else None

    def _compact(self, result):
        keys = ('compId', 'name', 'avgPlacement', 'sampleCount', 'top4Rate', 'topRate', 'pickRate')
        rows = [{key: row[key] for key in keys if key in row}
                for row in result['data']['comps'] if str(row['compId']) == self.comp]
        return {'data': {'comps': rows}, 'source': result['source'],
                'fetched_at': result['fetched_at'], 'cached': result['cached']}

    def _remember_exact(self, identity, stage, result):
        compact = self._compact(result)
        if self._current():
            with self._lock:
                if not self._cancelled.is_set():self._exact[(identity, stage)] = compact
        return compact

    def _canonical_name(self, identity, fallback):
        with self._lock:
            tables = [self._tables.get(self.comp), self._tables.get(None)]
        for result in tables:
            if result is None:continue
            row = next((row for row in result['data'] if str(row['hexId']) == identity), None)
            name = row.get('name') if row else None
            if isinstance(name, str) and name.strip():return name.strip()
        return fallback

    def iter_comp_hex_supplements(self, comp, stage, entities, *, current=lambda: True):
        if DataJ.entity_id(comp) != self.comp:
            raise ValueError('composition outside pinned scope')
        if stage not in STAGES:raise ValueError('unsupported hex stage')
        candidates = {}
        for identity, name in entities:
            identity = DataJ.entity_id(identity)
            if not isinstance(name, str) or not name.strip():raise ValueError('unconfirmed hex name')
            name = name.strip()
            if identity in candidates and candidates[identity] != name:
                raise ValueError('conflicting hex identity')
            candidates[identity] = name
            if len(candidates) > 3:raise ValueError('too many hex candidates')
        with self.interactive():
            def active():return self._current() and current()
            if not active():return
            pending = []
            for identity, name in candidates.items():
                with self._lock:
                    result = self._exact.get((identity, stage))
                if result is not None:
                    if not active():return
                    yield identity, {**deepcopy(result), 'cached': True}, None
                else:
                    pending.append((identity, self._canonical_name(identity, name)))
            for identity, result, error in self.adapter.iter_comp_hex_supplements(
                    self.comp, stage, pending, current=active):
                if not active():return
                if result is not None:
                    result = self._remember_exact(identity, stage, result)
                yield identity, deepcopy(result), error

    def _background_ready(self):
        while self._current():
            with self._lock:
                delay = self._next_background - time.monotonic()
                paused = bool(self._interactive)
            if delay <= 0 and not paused:return True
            self._wake.wait(.05 if paused else min(delay, .05))
            self._wake.clear()
        return False

    def _background_current(self):
        if not self._current():return False
        with self._lock:
            return not self._interactive

    def _remember_table(self, comp, result):
        if result is not None and self._current():
            retained = deepcopy(result)
            with self._lock:
                if not self._cancelled.is_set():self._tables[comp] = retained

    def _paced(self, fetch):
        if not self._background_ready():return None
        result = fetch()
        # A foreground hold can cancel the publication of a request which
        # already reached HTTP. Keep its completion spacing conservatively.
        if result is None or not result['cached']:
            with self._lock:
                self._next_background = time.monotonic() + self.interval
        return result

    def _missing(self):
        with self._lock:
            global_result, primary_result = self._tables.get(None), self._tables.get(self.comp)
            if global_result is None or primary_result is None:
                self._pending = []
                return []
            global_rows = global_result['data']
            primary_rows = primary_result['data']
            covered = {(str(row['hexId']), part['roundLabel'])
                       for row in primary_rows for part in row['roundStats']}
            primary_names = {str(row['hexId']): row.get('name') for row in primary_rows}
            pending = []
            for stage in self._stages:
                for row in global_rows:
                    identity = str(row['hexId'])
                    if ((identity, stage) in covered or (identity, stage) in self._exact
                            or not any(part['roundLabel'] == stage and part['sampleCount'] > 0
                                       for part in row['roundStats'])):
                        continue
                    name = primary_names.get(identity)
                    if not isinstance(name, str) or not name.strip():name = row.get('name')
                    if isinstance(name, str) and name.strip():
                        pending.append((identity, stage, name.strip()))
            self._pending = pending
            return pending

    def _run(self):
        try:
            for comp in (None, self.comp):
                while self._current():
                    with self._lock:
                        already = comp in self._tables
                    if already:break
                    result = self._paced(lambda: self.adapter.prefetch_hexes(
                        comp, current=self._background_current))
                    if result is not None:self._remember_table(comp, result)
                if not self._current():return
            while self._current():
                missing = self._missing()
                if not missing:
                    with self._lock:
                        if not self._cancelled.is_set():self._status = 'complete'
                    return
                if not self._background_ready():return
                missing = self._missing()
                if not missing:continue
                identity, stage, name = missing[0]
                result = self._paced(lambda: self.adapter.prefetch_comp_hex(
                    self.comp, stage, (identity, name), current=self._background_current))
                if result is None:continue
                if self._current():
                    self._remember_exact(identity, stage, result)
        except SourceError as error:
            with self._lock:
                if not self._cancelled.is_set():
                    self._status, self._error = 'failed', str(error)
