"""Exercise the actual public validation command's preflight, without recursion."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / 'tools/validate_data.py'
REGISTRY = ROOT / 'docs/testing/regressions.json'
BASELINE = ROOT / 'docs/testing/private-bug-baseline.json'
GUARD = 'TFT_REGRESSION_ENTRYPOINT_CHILD'
PUBLIC_TEST = 'test_title_consensus.TitleConsensusTests.test_two_exact_high_confidence_views_required'
MISSING_TEST = 'test_missing_historical_regression.HistoryTests.test_required_protection'


class RegressionEntrypointTests(unittest.TestCase):
    def setUp(self):
        # A broken preflight must not recursively launch this subprocess suite.
        self.assertNotEqual(os.environ.get(GUARD), '1',
                            'Validation started tests despite a required preflight failure')
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.temp = Path(temporary.name)
        self.manifest = self.temp / 'regressions.json'
        self.report = self.temp / 'report.json'

    def write_registry(self, test_id=MISSING_TEST, *, scope='public'):
        registry = {
            'schema_version': 1, 'fixtures': [],
            'regressions': [{
                'id': 'REG-900', 'title': 'Entrypoint protection experiment',
                'coverage': 'automated' if scope == 'public' else 'partial',
                'verified_scope': 'Preflight only; no live game or rendering assertion',
                'limits': ['This manifest deliberately cannot pass preflight'],
                'origin_commits': [],
                'evidence': ['docs/testing/bug-recording-20261007.md'],
                'tests': [{'id': test_id, 'scope': scope}],
            }],
        }
        self.manifest.write_text(json.dumps(registry), encoding='utf-8')

    def invoke(self, *, registry=None, baseline=None, report=None, base_ref=None):
        command = [sys.executable, '-X', 'utf8', str(TOOL),
                   '--regressions', str(registry or self.manifest),
                   '--bug-review-baseline', str(baseline or BASELINE),
                   '--report', str(report or self.report)]
        if base_ref is not None:
            command.extend(['--regression-base-ref', base_ref])
        environment = os.environ.copy()
        environment[GUARD] = '1'
        return subprocess.run(command, cwd=ROOT, env=environment,
                              capture_output=True, text=True, encoding='utf-8', timeout=30)

    def assert_preflight_failed(self, completed, reason):
        details = completed.stdout + '\n' + completed.stderr
        self.assertEqual(completed.returncode, 1, details)
        self.assertTrue(self.report.is_file(), details)
        report = json.loads(self.report.read_text(encoding='utf-8'))
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['regressions']['status'], 'failed')
        self.assertEqual(report['tests'], 0, 'Preflight failures must not execute the suite')
        self.assertIn(reason, str(report['regressions'].get('reason', '')).lower())
        return report

    def test_actual_tool_rejects_missing_registered_test_before_running_any_tests(self):
        self.write_registry()
        report = self.assert_preflight_failed(self.invoke(), 'missing test')
        self.assertIn(MISSING_TEST, report['regressions']['reason'])

    def test_actual_tool_rejects_public_test_declared_private_before_execution(self):
        self.write_registry(PUBLIC_TEST, scope='private')
        report = self.assert_preflight_failed(self.invoke(), 'scope mismatch')
        self.assertIn(PUBLIC_TEST, report['regressions']['reason'])

    def test_actual_tool_does_not_ignore_a_well_formed_but_unavailable_history_ref(self):
        self.write_registry(PUBLIC_TEST)
        # Full-length hexadecimal shape is valid; this object is unavailable.
        impossible = 'f' * 40
        report = self.assert_preflight_failed(self.invoke(base_ref=impossible), 'baseline')
        self.assertIn(impossible, report['regressions']['reason'])

    def assert_report_collision_rejected(self, destination, *, registry=None, baseline=None):
        original = destination.read_bytes()
        completed = self.invoke(registry=registry, baseline=baseline, report=destination)
        self.assertNotEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(destination.read_bytes(), original,
                         'A validation report must never replace its approved input')
        self.assertRegex((completed.stdout + completed.stderr).lower(),
                         r'report[^\n]*(?:overwrite|replace|collision|collide)',
                         'Rejection must identify the protected report destination, not an unrelated error')

    def test_actual_tool_cannot_write_report_over_the_checked_in_regression_registry(self):
        self.write_registry()
        self.assert_report_collision_rejected(REGISTRY, registry=REGISTRY)

    def test_actual_tool_cannot_write_report_over_the_checked_in_private_hash_baseline(self):
        self.write_registry()
        self.assert_report_collision_rejected(BASELINE)

    def test_actual_tool_cannot_write_report_over_a_custom_registry(self):
        self.write_registry()
        self.assert_report_collision_rejected(self.manifest)

    def test_actual_tool_cannot_write_report_over_a_custom_private_hash_baseline(self):
        self.write_registry()
        baseline = self.temp / 'approved-hashes.json'
        baseline.write_bytes(BASELINE.read_bytes())
        self.assert_report_collision_rejected(baseline, baseline=baseline)


if __name__ == '__main__':
    unittest.main()
