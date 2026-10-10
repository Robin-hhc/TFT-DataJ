"""Executable inventory of protections for previously reported failures."""
import hashlib
from pathlib import Path
import re
import unittest


class RegistryError(ValueError):
    pass


def validate_registry(registry, root, inventory, baseline=None):
    """Check collection, scope, evidence and immutable public fixture bytes."""
    _require(isinstance(registry, dict) and registry.get('schema_version') == 1, 'invalid registry schema')
    root = Path(root).resolve()
    _require(isinstance(registry.get('regressions'), list), 'invalid regressions list')
    rows = {}
    for row in registry['regressions']:
        _require(isinstance(row, dict), 'invalid regression entry')
        identity = row.get('id')
        _require(isinstance(identity, str) and re.fullmatch(r'REG-\d{3,}', identity), 'invalid regression ID')
        _require(identity not in rows, f'duplicate regression: {identity}')
        rows[identity] = row
        _require(row.get('coverage') in ('automated', 'partial', 'manual'), f'invalid coverage: {identity}')
        for field in ('title', 'verified_scope'):
            _require(isinstance(row.get(field), str) and row[field].strip(), f'missing {field}: {identity}')
        _require(isinstance(row.get('limits'), list) and all(isinstance(x, str) and x.strip() for x in row['limits']),
                 f'invalid limits: {identity}')
        _require(isinstance(row.get('tests'), list), f'invalid tests: {identity}')
        tests = set()
        for test in row['tests']:
            _require(isinstance(test, dict) and isinstance(test.get('id'), str), f'invalid test: {identity}')
            name = test['id']
            _require(name not in tests, f'duplicate test: {identity}: {name}')
            tests.add(name)
            _require(test.get('scope') in ('public', 'private'), f'invalid test scope: {name}')
            _require(name in inventory, f'missing test: {identity}: {name}')
            _require(test['scope'] == inventory[name], f'scope mismatch: {identity}: {name}')
        _require(row['coverage'] != 'automated' or any(t['scope'] == 'public' for t in row['tests']),
                 f'automated coverage requires a public test: {identity}')
        _require(isinstance(row.get('evidence'), list) and row['evidence'], f'missing evidence: {identity}')
        for path in row['evidence']:
            _file(root, path)
    _require(isinstance(registry.get('fixtures'), list), 'invalid fixtures list')
    fixture_paths = set()
    for fixture in registry['fixtures']:
        _require(isinstance(fixture, dict), 'invalid fixture entry')
        path = fixture.get('path')
        _require(path not in fixture_paths, f'duplicate fixture: {path}')
        fixture_paths.add(path)
        _require(isinstance(fixture.get('sha256'), str) and re.fullmatch(r'[0-9a-f]{64}', fixture['sha256']),
                 f'invalid fixture hash: {path}')
        _require(fixture.get('format') in ('bytes', 'utf8-lf'), f'invalid fixture format: {path}')
        data = _file(root, path).read_bytes()
        if fixture['format'] == 'utf8-lf':
            try:
                data = data.decode('utf-8').replace('\r\n', '\n').encode('utf-8')
            except UnicodeError as error:
                raise RegistryError(f'invalid UTF-8 fixture: {path}') from error
        _require(hashlib.sha256(data).hexdigest() == fixture['sha256'], f'fixture hash mismatch: {path}')
    if baseline is not None:
        _compare_history(registry, baseline)
    return {'registered': len(rows), 'test_references': sum(len(r['tests']) for r in rows.values()),
            'fixtures': len(fixture_paths)}


def _require(condition, message):
    if not condition:
        raise RegistryError(message)


def _file(root, relative):
    _require(isinstance(relative, str) and relative and '\\' not in relative,
             f'invalid relative file: {relative}')
    path = (root / relative).resolve()
    _require(not Path(relative).is_absolute() and path.is_relative_to(root), f'file outside repository: {relative}')
    _require(path.is_file(), f'missing file: {relative}')
    return path


def _compare_history(current, previous):
    _require(previous.get('schema_version') == 1, 'invalid previous registry schema')
    rows = {r['id']: r for r in current['regressions']}
    for old in previous['regressions']:
        identity = old['id']
        _require(identity in rows, f'removed regression: {identity}')
        row = rows[identity]
        old_tests = {t['id']: t['scope'] for t in old['tests']}
        new_tests = {t['id']: t['scope'] for t in row['tests']}
        downgrade = ({'automated': 2, 'partial': 1, 'manual': 0}[row['coverage']] <
                     {'automated': 2, 'partial': 1, 'manual': 0}[old['coverage']])
        protection_changed = any(new_tests.get(name) != scope for name, scope in old_tests.items())
        _require(not (downgrade or protection_changed) or
                 isinstance(row.get('coverage_change_note'), str) and bool(row['coverage_change_note'].strip()) and
                 row['coverage_change_note'] != old.get('coverage_change_note'),
                 f'coverage downgrade or protection removed without review reason: {identity}')
    current_fixtures = {f['path']: f for f in current['fixtures']}
    for old in previous['fixtures']:
        _require(current_fixtures.get(old['path']) == old, f'changed or removed approved fixture: {old["path"]}')


def compare_review_baselines(current, previous):
    """An approved screenshot/oracle index is append only across revisions."""
    rows = {c['case_id']: c for c in current['cases']}
    for old in previous['cases']:
        identity = old['case_id']
        _require(identity in rows, f'removed approved case: {identity}')
        _require(rows[identity] == old, f'changed approved case: {identity}')


def evaluate_regressions(registry, outcomes, *, include_private=False):
    cases = []
    failed = False
    for row in registry['regressions']:
        tests = []
        omitted_private = False
        for test in row['tests']:
            if test['scope'] == 'private' and not include_private:
                outcome = 'not_run_private'
                omitted_private = True
            else:
                outcome = outcomes.get(test['id'], 'not_run')
            tests.append({**test, 'result': outcome})
        required = [t for t in tests if t['result'] != 'not_run_private']
        broken = any(t['result'] != 'passed' for t in required)
        failed |= broken
        cases.append({'id': row['id'], 'title': row['title'], 'coverage': row['coverage'],
                      'status': 'failed' if broken else ('passed' if required else 'not_automated'),
                      'execution': 'public_only' if omitted_private else ('all_registered' if required else 'not_automated'),
                      'verified_scope': row['verified_scope'], 'limits': row['limits'], 'tests': tests})
    return {'status': 'failed' if failed else 'passed', 'cases': cases}


class RecordingResult(unittest.TextTestResult):
    """Keep parent outcomes even when a unittest subTest fails."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.outcomes = {}

    def addSuccess(self, test):
        super().addSuccess(test)
        self.outcomes.setdefault(test.id(), 'passed')

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.outcomes[test.id()] = 'failed'

    def addError(self, test, err):
        super().addError(test, err)
        self.outcomes[test.id()] = 'error'

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        parent = getattr(test, 'test_case', test)
        self.outcomes.setdefault(parent.id(), 'skipped')

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self.outcomes[test.id()] = 'expected_failure'

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self.outcomes[test.id()] = 'unexpected_success'

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            self.outcomes[test.id()] = 'failed'
