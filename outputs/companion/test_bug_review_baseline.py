"""Accepted private evidence must not silently fall back to pending or vanish."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('review_baseline_replay', ROOT / 'tools/validate_bug_cases.py')
replay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay)


class BugReviewBaselineTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.archive = self.root / 'cases'
        self.archive.mkdir()
        self.baseline = self.root / 'accepted.json'
        self.first = self.make_case('a')

    def make_case(self, digit, *, reviewed=True):
        case_dir = self.archive / ('case-' + digit * 64)
        case_dir.mkdir()
        Image.new('RGB', (32, 18), (7, 8, 9)).save(case_dir / 'frame.png')
        digest = hashlib.sha256((case_dir / 'frame.png').read_bytes()).hexdigest()
        manifest = {
            'schema_version': 1, 'case_id': case_dir.name, 'status': 'pending_review',
            'created_at': '2026-10-10T00:00:00Z', 'reason': 'hex_unresolved',
            'context': {'set_id': 18, 'patch': '18.3', 'target': None,
                        'domain': 'hex', 'source': 'bound_game'},
            'observation': {'scene': 'choice_unresolved', 'round': '2-1', 'cards': []},
            'evidence': {'catalog': {'hex': [{'id': '1001', 'name': 'Reviewed title'}]}},
            'image': {'filename': 'frame.png', 'sha256': digest, 'width': 32, 'height': 18},
        }
        (case_dir / 'case.json').write_text(json.dumps(manifest), encoding='utf-8')
        if reviewed:
            expected = {
                'schema_version': 1, 'image_sha256': digest, 'set_id': 18, 'patch': '18.3',
                'scene': 'choice_candidates', 'round': '2-1',
                'cards': [{'slot': 0, 'id': '1001'}, {'slot': 1, 'id': None}, {'slot': 2, 'id': None}],
                'reviewed_by': 'human:test', 'review_note': 'Independent original-image title review.',
            }
            (case_dir / 'expected.json').write_text(json.dumps(expected), encoding='utf-8')
        return case_dir

    def approve(self, case_dir=None):
        return replay.register_reviewed_case(self.archive, self.baseline, (case_dir or self.first).name)

    def verify(self, *, files=True):
        return replay.validate_review_baseline(self.archive, self.baseline, verify_files=files)

    def test_deleted_approved_expected_is_a_failure_not_pending(self):
        self.approve()
        (self.first / 'expected.json').unlink()
        report = self.verify()
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['summary']['failed'], 1)
        self.assertNotEqual(replay.exit_code(report), 0)
        self.assertIn('expected.json', report['cases'][0]['reason'])
        self.assertFalse((self.first / 'expected.json').exists())

    def test_empty_or_missing_archive_fails_all_approved_requirements(self):
        self.approve()
        for filename in ('frame.png', 'case.json', 'expected.json'):
            (self.first / filename).unlink()
        self.first.rmdir()
        for missing in (False, True):
            if missing:
                self.archive.rmdir()
            report = self.verify()
            self.assertEqual(report['status'], 'failed')
            self.assertEqual(report['summary']['required'], 1)
            self.assertEqual(report['summary']['failed'], 1)
            self.assertNotEqual(replay.exit_code(report), 0)

    def test_each_approved_artifact_hash_change_is_a_failure(self):
        self.approve()
        for filename in ('frame.png', 'case.json', 'expected.json'):
            with self.subTest(filename=filename):
                path = self.first / filename
                original = path.read_bytes()
                path.write_bytes(original + b' ')
                report = self.verify()
                self.assertEqual(report['status'], 'failed')
                self.assertIn(filename, report['cases'][0]['reason'])
                path.write_bytes(original)
        self.assertEqual(self.verify()['summary']['verified'], 1)

    def test_each_missing_approved_artifact_fails_without_recreating_it(self):
        self.approve()
        for filename in ('frame.png', 'case.json', 'expected.json'):
            with self.subTest(filename=filename):
                path = self.first / filename
                original = path.read_bytes()
                path.unlink()
                report = self.verify()
                self.assertEqual(report['summary']['failed'], 1)
                self.assertIn(filename, report['cases'][0]['reason'])
                self.assertNotEqual(replay.exit_code(report), 0)
                self.assertFalse(path.exists())
                path.write_bytes(original)
        self.assertEqual(self.verify()['summary']['verified'], 1)

    def test_duplicate_ids_and_invalid_schema_cannot_pass_even_without_private_files(self):
        self.approve()
        original = json.loads(self.baseline.read_text(encoding='utf-8'))
        cases = [
            {**original, 'schema_version': True},
            {**original, 'schema_version': 2},
            {**original, 'extra': 'hidden assertion'},
            {**original, 'cases': original['cases'] * 2},
            {**original, 'cases': [{**original['cases'][0], 'expected_sha256': 'not-a-hash'}]},
            {**original, 'cases': [{**original['cases'][0], 'case_id': '../outside'}]},
            {**original, 'cases': [{**original['cases'][0], 'player_name': 'not public'}]},
        ]
        for payload in cases:
            with self.subTest(payload=payload):
                self.baseline.write_text(json.dumps(payload), encoding='utf-8')
                report = self.verify(files=False)
                self.assertEqual(report['status'], 'invalid')
                self.assertNotEqual(replay.exit_code(report), 0)

    def test_append_registration_preserves_old_hashes_and_does_not_touch_originals(self):
        self.approve()
        first_entry = json.loads(self.baseline.read_text(encoding='utf-8'))['cases'][0]
        originals = {name: (self.first / name).read_bytes()
                     for name in ('frame.png', 'case.json', 'expected.json')}
        second = self.make_case('b')
        self.approve(second)
        baseline = json.loads(self.baseline.read_text(encoding='utf-8'))
        self.assertEqual(baseline['cases'][0], first_entry)
        self.assertEqual([row['case_id'] for row in baseline['cases']], [self.first.name, second.name])
        self.assertEqual(self.verify()['summary']['verified'], 2)
        for name, data in originals.items():
            self.assertEqual((self.first / name).read_bytes(), data)

    def test_same_case_registration_is_byte_preserving_and_changed_approval_is_rejected(self):
        self.approve()
        before = self.baseline.read_bytes()
        self.assertEqual(self.approve()['status'], 'already_registered')
        self.assertEqual(self.baseline.read_bytes(), before)
        expected = self.first / 'expected.json'
        expected.write_bytes(expected.read_bytes() + b'\n')
        with self.assertRaises(replay.InvalidCase):
            self.approve()
        self.assertEqual(self.baseline.read_bytes(), before)

    def test_pending_or_invalid_oracle_cannot_be_registered_or_generated(self):
        pending = self.make_case('b', reviewed=False)
        with patch.object(replay, '_make_runner', side_effect=AssertionError('no observed gold')):
            with self.assertRaises(replay.InvalidCase):
                self.approve(pending)
        self.assertFalse((pending / 'expected.json').exists())
        self.assertFalse(self.baseline.exists())
        oracle = self.first / 'expected.json'
        payload = json.loads(oracle.read_text(encoding='utf-8'))
        payload['image_sha256'] = '0' * 64
        oracle.write_text(json.dumps(payload), encoding='utf-8')
        with self.assertRaises(replay.InvalidCase):
            self.approve()
        self.assertFalse(self.baseline.exists())

    def test_new_unreviewed_case_does_not_join_or_break_the_approved_baseline(self):
        self.approve()
        before = self.baseline.read_bytes()
        self.make_case('b', reviewed=False)
        report = self.verify()
        self.assertEqual(report['status'], 'passed')
        self.assertEqual(report['summary']['required'], 1)
        self.assertEqual(report['summary']['verified'], 1)
        self.assertEqual(self.baseline.read_bytes(), before)

    def test_public_schema_inventory_does_not_read_private_files_or_initialize_ocr(self):
        self.approve()
        with patch.object(replay, '_manifest', side_effect=AssertionError('no private pixels')), \
                patch.object(replay, '_make_runner', side_effect=AssertionError('no OCR')):
            report = self.verify(files=False)
        self.assertEqual(report['status'], 'passed')
        self.assertEqual(report['summary']['verified'], 0)
        self.assertEqual(report['summary']['not_run'], 1)
        self.assertEqual(report['cases'][0]['result'], 'not_run')

    def test_baseline_must_be_outside_archive_and_ids_cannot_traverse(self):
        for destination in (self.first / 'accepted.json', self.archive / 'accepted.json'):
            with self.assertRaises(replay.InvalidCase):
                replay.register_reviewed_case(self.archive, destination, self.first.name)
            self.assertFalse(destination.exists())
        for case_id in ('../case-other', str(self.first), 'case-' + 'a' * 15, 'CASE-' + 'a' * 64):
            with self.assertRaises(replay.InvalidCase):
                replay.register_reviewed_case(self.archive, self.baseline, case_id)
        self.assertFalse(self.baseline.exists())

    def test_linked_baseline_or_artifact_is_rejected_before_access(self):
        self.approve()
        original_stat, original_read = Path.lstat, Path.read_bytes
        for linked in (self.baseline, self.first / 'expected.json', self.archive):
            with self.subTest(linked=linked):
                def checked_stat(path):
                    result = original_stat(path)
                    if path == linked:
                        return SimpleNamespace(st_mode=result.st_mode, st_file_attributes=0x400)
                    return result

                def checked_read(path):
                    if path == linked or path.is_relative_to(linked):
                        self.fail('linked evidence must be rejected before reading')
                    return original_read(path)

                with patch.object(Path, 'lstat', checked_stat), patch.object(Path, 'read_bytes', checked_read):
                    expected = 'invalid' if linked in (self.baseline, self.archive) else 'failed'
                    self.assertEqual(self.verify()['status'], expected)
                    with self.assertRaises(replay.InvalidCase):
                        self.approve()

    def test_missing_baseline_cannot_be_a_successful_public_inventory(self):
        report = self.verify(files=False)
        self.assertEqual(report['status'], 'invalid')
        self.assertNotEqual(replay.exit_code(report), 0)

    def test_cli_enforces_selected_baseline_and_protects_it_from_report_overwrite(self):
        self.approve()
        before = self.baseline.read_bytes()
        args = ['--cases-dir', str(self.archive), '--review-baseline', str(self.baseline)]
        with patch.object(replay, '_make_runner', side_effect=AssertionError('inventory stays offline')):
            self.assertEqual(replay.main(args), 0)
            (self.first / 'expected.json').unlink()
            self.assertNotEqual(replay.main(args), 0)
        with self.assertRaises(SystemExit):
            replay.main(args + ['--report', str(self.baseline)])
        self.assertEqual(self.baseline.read_bytes(), before)

    def test_cli_registration_requires_explicit_baseline_and_only_appends_selected_id(self):
        with self.assertRaises(SystemExit):
            replay.main(['--cases-dir', str(self.archive), '--register-reviewed-case', self.first.name])
        self.assertEqual(replay.main(['--cases-dir', str(self.archive), '--review-baseline', str(self.baseline),
                                     '--register-reviewed-case', self.first.name]), 0)
        self.assertEqual(self.verify()['summary']['verified'], 1)


if __name__ == '__main__':
    unittest.main()
