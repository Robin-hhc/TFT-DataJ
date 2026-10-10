"""History gates must fail when known regression protection disappears."""
from copy import deepcopy
import hashlib
import io
from pathlib import Path
import tempfile
import unittest


class RegressionRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'evidence.md').write_text('independent source', encoding='utf-8')
        (self.root / 'fixture.txt').write_bytes(b'line\n')
        self.identity = 'test_feature.FeatureTests.test_known_failure'
        self.inventory = {self.identity: 'public'}
        self.registry = {
            'schema_version': 1,
            'fixtures': [{'path': 'fixture.txt', 'sha256': hashlib.sha256(b'line\n').hexdigest(),
                          'format': 'utf8-lf'}],
            'regressions': [{
                'id': 'REG-001', 'title': 'Known failure', 'coverage': 'automated',
                'verified_scope': 'Exact public result', 'limits': ['No real game FPS claim'],
                'origin_commits': ['b76b4ce'], 'evidence': ['evidence.md'],
                'tests': [{'id': self.identity, 'scope': 'public'}]}]}

    def validate(self, registry=None, **kwargs):
        from regression_registry import validate_registry
        return validate_registry(registry or self.registry, self.root, self.inventory, **kwargs)

    def test_missing_registered_test_cannot_be_hidden_by_remaining_green_tests(self):
        from regression_registry import RegistryError, validate_registry
        with self.assertRaisesRegex(RegistryError, 'missing test'):
            validate_registry(self.registry, self.root, {}, baseline=None)

    def test_moving_public_regression_to_private_requires_explicit_scope_change(self):
        from regression_registry import RegistryError, validate_registry
        with self.assertRaisesRegex(RegistryError, 'scope mismatch'):
            validate_registry(self.registry, self.root, {self.identity: 'private'}, baseline=None)

    def test_duplicate_history_id_or_test_reference_is_rejected(self):
        from regression_registry import RegistryError
        duplicate = deepcopy(self.registry)
        duplicate['regressions'].append(deepcopy(duplicate['regressions'][0]))
        with self.assertRaisesRegex(RegistryError, 'duplicate regression'):
            self.validate(duplicate)
        duplicate = deepcopy(self.registry)
        duplicate['regressions'][0]['tests'] *= 2
        with self.assertRaisesRegex(RegistryError, 'duplicate test'):
            self.validate(duplicate)

    def test_removed_fixture_or_changed_pixels_fail_without_rewriting_gold(self):
        from regression_registry import RegistryError
        (self.root / 'fixture.txt').write_bytes(b'changed pixels')
        with self.assertRaisesRegex(RegistryError, 'fixture hash'):
            self.validate()
        (self.root / 'fixture.txt').unlink()
        with self.assertRaisesRegex(RegistryError, 'missing file'):
            self.validate()

    def test_text_fixture_hash_is_stable_across_windows_line_endings(self):
        (self.root / 'fixture.txt').write_bytes(b'line\r\n')
        self.validate()

    def test_skipped_or_unexecuted_registered_test_is_a_failure(self):
        from regression_registry import evaluate_regressions
        for outcomes in ({}, {self.identity: 'skipped'}, {self.identity: 'failed'}):
            with self.subTest(outcomes=outcomes):
                report = evaluate_regressions(self.registry, outcomes, include_private=False)
                self.assertEqual(report['status'], 'failed')
                self.assertEqual(report['cases'][0]['tests'][0]['result'],
                                 outcomes.get(self.identity, 'not_run'))

    def test_declared_partial_and_unrun_private_scope_are_never_called_complete(self):
        from regression_registry import evaluate_regressions
        row = self.registry['regressions'][0]
        row['coverage'] = 'partial'
        row['tests'].append({'id': 'test_local.LocalTests.test_pixels', 'scope': 'private'})
        report = evaluate_regressions(self.registry, {self.identity: 'passed'}, include_private=False)
        self.assertEqual(report['status'], 'passed')
        case = report['cases'][0]
        self.assertEqual(case['coverage'], 'partial')
        self.assertEqual(case['execution'], 'public_only')
        self.assertEqual(case['tests'][1]['result'], 'not_run_private')
        strict = evaluate_regressions(self.registry, {self.identity: 'passed'}, include_private=True)
        self.assertEqual(strict['status'], 'failed')

    def test_history_entries_cannot_be_deleted_in_a_later_revision(self):
        from regression_registry import RegistryError
        changed = deepcopy(self.registry)
        changed['regressions'] = []
        with self.assertRaisesRegex(RegistryError, 'removed regression'):
            self.validate(changed, baseline=self.registry)

    def test_scope_or_coverage_downgrade_requires_a_recorded_review_reason(self):
        from regression_registry import RegistryError
        changed = deepcopy(self.registry)
        changed['regressions'][0]['coverage'] = 'partial'
        with self.assertRaisesRegex(RegistryError, 'coverage downgrade'):
            self.validate(changed, baseline=self.registry)
        changed['regressions'][0]['coverage_change_note'] = 'Independent review found missing game FPS evidence.'
        self.validate(changed, baseline=self.registry)

    def test_old_review_reason_cannot_authorize_a_new_protection_loss(self):
        from regression_registry import RegistryError
        previous = deepcopy(self.registry)
        previous['regressions'][0]['coverage_change_note'] = 'Earlier review of a different gap.'
        changed = deepcopy(previous)
        changed['regressions'][0]['coverage'] = 'partial'
        with self.assertRaisesRegex(RegistryError, 'coverage downgrade'):
            self.validate(changed, baseline=previous)

    def test_accepted_fixture_cannot_be_replaced_by_updating_its_hash(self):
        from regression_registry import RegistryError
        changed = deepcopy(self.registry)
        (self.root / 'fixture.txt').write_bytes(b'regenerated answer')
        changed['fixtures'][0]['sha256'] = hashlib.sha256(b'regenerated answer').hexdigest()
        with self.assertRaisesRegex(RegistryError, 'approved fixture'):
            self.validate(changed, baseline=self.registry)

    def test_actual_unittest_subtest_failure_is_not_recorded_as_passed(self):
        from regression_registry import RecordingResult
        class Broken(unittest.TestCase):
            def runTest(self):
                with self.subTest(stage='4-2'):
                    self.assertEqual('wrong ID', 'expected ID')
        test = Broken()
        result = unittest.TextTestRunner(stream=io.StringIO(), resultclass=RecordingResult).run(test)
        self.assertFalse(result.wasSuccessful())
        self.assertEqual(result.outcomes[test.id()], 'failed')

    def test_skipped_subtest_is_not_recorded_as_a_passed_parent(self):
        from regression_registry import RecordingResult
        class Incomplete(unittest.TestCase):
            def runTest(self):
                with self.subTest(stage='4-2'):
                    self.skipTest('Independent golden image unavailable')
        test = Incomplete()
        result = unittest.TextTestRunner(stream=io.StringIO(), resultclass=RecordingResult).run(test)
        self.assertEqual(result.outcomes[test.id()], 'skipped')

    def test_independent_approved_cases_cannot_be_removed_or_replaced(self):
        from regression_registry import RegistryError, compare_review_baselines
        case = {'case_id': 'case-' + 'a' * 24, 'image_sha256': '1' * 64,
                'case_sha256': '2' * 64, 'expected_sha256': '3' * 64}
        old = {'schema_version': 1, 'cases': [case]}
        with self.assertRaisesRegex(RegistryError, 'removed approved'):
            compare_review_baselines({'schema_version': 1, 'cases': []}, old)
        replacement = deepcopy(old)
        replacement['cases'][0]['expected_sha256'] = '4' * 64
        with self.assertRaisesRegex(RegistryError, 'changed approved'):
            compare_review_baselines(replacement, old)


if __name__ == '__main__':
    unittest.main()
