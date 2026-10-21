"""Public exact-oracle contract for optional external packaged OCR fixtures."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

import portable_check


class PortableRecognitionReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.frame = self.directory / 'original.png'
        Image.new('RGB', (8, 8), '#123456').save(self.frame)
        self.catalog = self.directory / 'catalog.json'
        self.catalog.write_text(json.dumps({'data': {'hex': [
            {'id': '101', 'name': 'First'}, {'id': '202', 'name': 'Second'},
            {'id': '303', 'name': 'Third'}]}}), encoding='utf-8')
        self.expected = {'scene': 'choice_candidates', 'round': '3-2',
                         'ids': ['101', '202', '303']}
        self.manifest = {
            'schema_version': 1,
            'catalog': self.descriptor(self.catalog),
            'cases': [{'id': 'independently-reviewed', 'frame': self.descriptor(self.frame),
                       'expected': self.expected}]}
        self.manifest_path = self.directory / 'manifest.json'
        self.write_manifest()

    def descriptor(self, path):
        return {'path': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

    def write_manifest(self):
        self.manifest_path.write_text(json.dumps(self.manifest), encoding='utf-8')

    def vision(self, **changes):
        result = {'scene': 'choice_candidates', 'round': '3-2', 'cards': [
            {'slot': slot, 'resolution': {'id': identity, 'status': 'resolved'}}
            for slot, identity in enumerate(['101', '202', '303'])]}
        result.update(changes)
        class PublicVisionResult:
            calls = 0
            def analyze_fast(inner, frame, catalog):
                inner.calls += 1
                self.assertEqual(frame.size, (8, 8))
                self.assertEqual([row['id'] for row in catalog], ['101', '202', '303'])
                return deepcopy(result)
        return PublicVisionResult()

    def test_exact_scene_round_and_three_ordered_ids_are_reported(self):
        before = {path.name: path.read_bytes() for path in self.directory.iterdir()}
        report = portable_check.check_recognition_fixture(self.vision(), self.manifest_path)
        self.assertEqual(report['status'], 'passed')
        self.assertEqual({key: report['cases'][0]['actual'][key] for key in self.expected}, self.expected)
        self.assertEqual(report['cases'][0]['expected'], self.expected)
        self.assertEqual(report['cases'][0]['checks'], ['scene', 'round', 'ordered_three_ids',
                                                       'resolved_cards', 'ordered_slots'])
        self.assertEqual(report['cases'][0]['actual']['slots'], [0, 1, 2])
        self.assertEqual(report['cases'][0]['actual']['resolution_statuses'], ['resolved'] * 3)
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.directory.iterdir()})

    def test_wrong_nonempty_or_reordered_ids_fail_exact_oracle(self):
        for identities in (['101', '999', '303'], ['202', '101', '303'], ['101', '202']):
            with self.subTest(ids=identities):
                cards = [{'slot': slot, 'resolution': {'id': identity, 'status': 'resolved'}}
                         for slot, identity in enumerate(identities)]
                report = portable_check.check_recognition_fixture(self.vision(cards=cards), self.manifest_path)
                self.assertEqual(report['status'], 'failed')
                self.assertIn('ids', report['cases'][0]['mismatches'])
                self.assertEqual(report['cases'][0]['actual']['ids'], identities)
                self.assertEqual(report['cases'][0]['expected']['ids'], ['101', '202', '303'])

    def test_expected_ids_with_unresolved_or_confirmation_status_are_rejected(self):
        for status in ('unrecognized', 'needs_confirmation', None):
            with self.subTest(status=status):
                cards = [{'slot': slot, 'resolution': {'id': identity, 'status':
                          status if slot == 1 else 'resolved'}}
                         for slot, identity in enumerate(['101', '202', '303'])]
                report = portable_check.check_recognition_fixture(self.vision(cards=cards), self.manifest_path)
                self.assertEqual(report['status'], 'failed')
                self.assertEqual(report['cases'][0]['actual']['ids'], self.expected['ids'])
                self.assertIn('resolved_cards', report['cases'][0]['mismatches'])

    def test_expected_ids_with_out_of_order_duplicate_or_missing_slots_are_rejected(self):
        for slots in ([1, 0, 2], [0, 0, 2], [None, 1, 2]):
            with self.subTest(slots=slots):
                cards = [{'slot': slot, 'resolution': {'id': identity, 'status': 'resolved'}}
                         for slot, identity in zip(slots, ['101', '202', '303'])]
                report = portable_check.check_recognition_fixture(self.vision(cards=cards), self.manifest_path)
                self.assertEqual(report['status'], 'failed')
                self.assertEqual(report['cases'][0]['actual']['ids'], self.expected['ids'])
                self.assertIn('ordered_slots', report['cases'][0]['mismatches'])

    def test_wrong_round_or_scene_fails_even_when_all_three_ids_match(self):
        for field, value in (('round', '2-1'), ('scene', 'choice_unresolved')):
            with self.subTest(field=field):
                report = portable_check.check_recognition_fixture(self.vision(**{field: value}), self.manifest_path)
                self.assertEqual(report['status'], 'failed')
                self.assertEqual(report['cases'][0]['mismatches'], [field])

    def test_changed_frame_or_catalog_hash_is_rejected_before_ocr(self):
        for path, label in ((self.frame, 'independently-reviewed frame'), (self.catalog, 'catalog')):
            with self.subTest(path=path.name):
                before = path.read_bytes()
                path.write_bytes(before + b' ')
                vision = self.vision()
                report = portable_check.check_recognition_fixture(vision, self.manifest_path)
                self.assertEqual(report['status'], 'failed')
                self.assertIn(label + ' SHA-256 mismatch', report['error'])
                self.assertEqual(vision.calls, 0)
                path.write_bytes(before)

    def test_all_cases_are_reported_including_later_cases_after_mismatch(self):
        self.manifest['cases'].append({**deepcopy(self.manifest['cases'][0]), 'id': 'second-review'})
        self.write_manifest()
        report = portable_check.check_recognition_fixture(self.vision(round='4-2'), self.manifest_path)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual([case['id'] for case in report['cases']], ['independently-reviewed', 'second-review'])
        self.assertTrue(all(case['actual']['round'] == '4-2' for case in report['cases']))

    def test_malformed_or_empty_oracle_never_counts_as_pass(self):
        for broken in ([], [{'id': 'bad', 'frame': self.descriptor(self.frame),
                              'expected': {**self.expected, 'ids': ['101']}}]):
            with self.subTest(cases=broken):
                self.manifest['cases'] = broken
                self.write_manifest()
                report = portable_check.check_recognition_fixture(None, self.manifest_path)
                self.assertEqual(report['status'], 'failed')
                self.assertTrue(report['error'])

    def test_nonobject_manifest_returns_failed_diagnostic_instead_of_raising(self):
        self.manifest_path.write_text('[]', encoding='utf-8')
        report = portable_check.check_recognition_fixture(None, self.manifest_path)
        self.assertEqual(report['status'], 'failed')
        self.assertIn('object', report['error'])

    def test_verifier_copies_hash_bound_inputs_and_keeps_originals_unchanged(self):
        script = Path(__file__).resolve().parents[2] / 'packaging' / 'verify_windows.py'
        spec = importlib.util.spec_from_file_location('recognition_verify_windows', script)
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        sandbox = self.directory / 'sandbox'
        sandbox.mkdir()
        sandbox = sandbox.resolve()
        before = {path.name: path.read_bytes() for path in self.directory.iterdir() if path.is_file()}
        copied = verifier.copy_recognition_fixture(self.manifest_path, sandbox,
                                                   Path(__file__).resolve().parents[2])
        replay = portable_check.check_recognition_fixture(self.vision(), copied)
        self.assertEqual(replay['status'], 'passed')
        copied_json = json.loads(copied.read_text(encoding='utf-8'))
        descriptors = [copied_json['catalog']] + [case['frame'] for case in copied_json['cases']]
        for descriptor in descriptors:
            destination = (copied.parent / descriptor['path']).resolve()
            self.assertTrue(destination.is_relative_to(sandbox))
            self.assertEqual(hashlib.sha256(destination.read_bytes()).hexdigest(), descriptor['sha256'])
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.directory.iterdir() if path.is_file()})

    def test_verifier_keeps_canonical_containment_with_an_equivalent_noncanonical_parent(self):
        parent = self.directory / 'existing-parent'
        parent.mkdir()
        self.directory = parent / '..'
        self.assertNotEqual(self.directory, self.directory.resolve())
        self.assertTrue(self.directory.samefile(self.directory.resolve()))
        self.test_verifier_copies_hash_bound_inputs_and_keeps_originals_unchanged()


if __name__ == '__main__':
    unittest.main()
