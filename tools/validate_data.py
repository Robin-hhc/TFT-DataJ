"""One offline entrypoint for source, display replay and accumulated regressions."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = {'test_user_layout', 'test_live_failure', 'test_scene_gate', 'test_live_choice',
           'test_item_vision', 'test_item_live_layout', 'test_condition_reader_local'}
REGISTRY = ROOT / 'docs/testing/regressions.json'


def test_leaves(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from test_leaves(test)
        else:
            yield test


def collect_tests(include_private):
    suite = unittest.TestSuite()
    inventory = {}
    excluded = []
    loader = unittest.TestLoader()
    for folder in ['outputs/companion', 'outputs/mumu-p0-probe']:
        for file in sorted((ROOT / folder).glob('test_*.py')):
            tests = loader.loadTestsFromName(file.stem)
            scope = 'private' if file.stem in PRIVATE else 'public'
            for test in test_leaves(tests):
                inventory[test.id()] = scope
            if scope == 'private' and not include_private:
                excluded.append({'suite': file.stem, 'status': 'not_run',
                                 'reason': 'Private screenshot/OCR extension; use --include-private'})
            else:
                suite.addTests(tests)
    if loader.errors:
        raise ValueError('Test collection failed: ' + '\n'.join(loader.errors))
    return suite, inventory, excluded


def previous_json(path, base_ref):
    """Read only from a verified commit; missing new indexes are explicit."""
    if base_ref and not re.fullmatch(r'[0-9a-fA-F]{7,40}', base_ref):
        raise ValueError('Invalid regression base SHA')
    ref = base_ref or 'HEAD'
    # A first GitHub push has no predecessor. Still check the committed HEAD.
    if base_ref and not base_ref.strip('0'):
        ref = 'HEAD'
    checked = subprocess.run(['git', 'rev-parse', '--verify', ref + '^{commit}'],
                             cwd=ROOT, capture_output=True, text=True)
    if checked.returncode:
        raise ValueError('Unavailable regression baseline commit: ' + ref)
    commit = checked.stdout.strip()
    relative = path.resolve().relative_to(ROOT).as_posix()
    listed = subprocess.run(['git', 'ls-tree', '--name-only', commit, '--', relative],
                            cwd=ROOT, capture_output=True, text=True, check=True)
    if not listed.stdout.strip():
        return None
    content = subprocess.check_output(['git', 'show', commit + ':' + relative], cwd=ROOT)
    return json.loads(content.decode('utf-8'))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--include-private', action='store_true', help='Run local screenshot/OCR checks; absent approved files fail')
    parser.add_argument('--release-gate', action='store_true', help='Also reject live capture coverage gaps')
    parser.add_argument('--bug-cases-dir', type=Path, help='Local reviewed screenshot archive, used with --include-private')
    parser.add_argument('--regressions', type=Path, default=REGISTRY, help='History registry (default: versioned project registry)')
    parser.add_argument('--regression-base-ref', help='Previous commit SHA to enforce accumulated protection; default: HEAD')
    parser.add_argument('--bug-review-baseline', type=Path, help='Explicit alternative private archive approval index')
    parser.add_argument('--report', type=Path, default=ROOT / 'work/data-validation/offline.json')
    args = parser.parse_args(argv)
    for path in ['outputs/mumu-p0-probe', 'outputs/companion']:
        sys.path.insert(0, str(ROOT / path))
    from bootstrap import STATE_DIR
    from validate_bug_cases import (validate_cases, exit_code, validate_report_path, write_report,
                                    validate_review_baseline, InvalidCase)
    from regression_registry import validate_registry, compare_review_baselines, evaluate_regressions, RecordingResult
    case_archive = args.bug_cases_dir or STATE_DIR / 'bug-cases'
    try:
        validate_report_path(args.report, case_archive)
        protected = {args.regressions.resolve(), REGISTRY.resolve(),
                     (ROOT / 'docs/testing/private-bug-baseline.json').resolve()}
        if args.bug_review_baseline:
            protected.add(args.bug_review_baseline.resolve())
        if args.report.resolve() in protected:
            raise InvalidCase('report must not overwrite regression registry or approved review baseline')
    except (OSError, InvalidCase) as error:
        parser.error(str(error))
    try:
        registry = json.loads(args.regressions.read_text(encoding='utf-8'))
        review_path = (ROOT / registry.get('private_review_baseline', 'docs/testing/private-bug-baseline.json')).resolve()
        if not review_path.is_relative_to(ROOT) or not review_path.is_file():
            raise ValueError('Missing or invalid project private review baseline')
        if args.report.resolve() == review_path:
            raise ValueError('report must not overwrite approved review baseline')
        suite, inventory, excluded = collect_tests(args.include_private)
        # Always compare the canonical versioned history, even for a custom registry.
        old_registry = previous_json(REGISTRY, args.regression_base_ref)
        current_project = json.loads(REGISTRY.read_text(encoding='utf-8'))
        validate_registry(current_project, ROOT, inventory, baseline=old_registry)
        registered = validate_registry(registry, ROOT, inventory,
                                       baseline=old_registry if args.regressions.resolve() == REGISTRY.resolve() else None)
        review_check = validate_review_baseline(case_archive, review_path, verify_files=False)
        if review_check['status'] != 'passed':
            raise ValueError(review_check.get('reason', 'Invalid private review baseline schema'))
        review = json.loads(review_path.read_text(encoding='utf-8'))
        old_review = previous_json(ROOT / 'docs/testing/private-bug-baseline.json', args.regression_base_ref)
        if old_review is not None:
            compare_review_baselines(review, old_review)
    except (ValueError, OSError, TypeError, KeyError, subprocess.SubprocessError) as error:
        report = {'status': 'failed', 'tests': 0,
                  'regressions': {'status': 'failed', 'phase': 'preflight', 'reason': str(error)}}
        # Collision failures must never overwrite inputs, including custom baseline paths.
        if 'overwrite' not in str(error):
            write_report(report, args.report, case_archive)
        print('Regression preflight failed:', error)
        return 1
    result = unittest.TextTestRunner(verbosity=1, resultclass=RecordingResult).run(suite)
    from test_display_replay import REPORTS
    cases = [case for replay in REPORTS for case in replay['cases']]
    gaps = REPORTS[0]['gaps'] if REPORTS else [{'status': 'missing_fixture'}]
    regressions = evaluate_regressions(registry, result.outcomes, include_private=args.include_private)
    regressions.update(registry=str(args.regressions.resolve()), inventory=registered,
                       compared_base=args.regression_base_ref or 'HEAD')
    failed = (not result.wasSuccessful() or bool(result.skipped) or not REPORTS or
              (args.release_gate and bool(gaps)) or regressions['status'] != 'passed')
    baseline_path = args.bug_review_baseline or review_path
    review_check = validate_review_baseline(case_archive, baseline_path, verify_files=args.include_private)
    failed |= review_check['status'] != 'passed'
    bug_cases = {'status': 'not_run', 'reason': 'Private local bug screenshots; use --include-private'}
    if args.include_private:
        bug_cases = validate_cases(case_archive, run_reviewed=True)
        failed |= bool(exit_code(bug_cases))
    report = {'status': 'failed' if failed else 'passed', 'tests': result.testsRun,
              'errors': len(result.errors), 'failures': len(result.failures),
              'test_outcomes': result.outcomes, 'regressions': regressions,
              'skipped': [{'test': str(t), 'reason': reason} for t, reason in result.skipped],
              'extensions': excluded, 'display_cases': cases,
              'display_summary': dict(Counter(r['domain'] + ':' + r['status'] for r in cases)),
              'source_gaps': gaps, 'reference': 'API + verified website display rules; not website DOM comparison',
              'bug_cases': bug_cases, 'review_baseline': review_check,
              'source_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'source_tree_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT))}
    write_report(report, args.report, case_archive)
    print(json.dumps({k: report[k] for k in ['status', 'tests', 'display_summary']}, ensure_ascii=False))
    print('Regressions:', regressions['status'], registered, 'Approved originals:', review_check['summary'])
    print('Report:', args.report)
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
