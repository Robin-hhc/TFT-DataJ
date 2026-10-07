"""Pure archive/oracle checks: no real OCR, capture, game, or network."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('validate_bug_cases', ROOT/'tools/validate_bug_cases.py')
replay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay)


class BugCaseReplayTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)/'bug-cases'
        self.folder.mkdir()
        self.case_dir = self.folder/('case-'+'a'*24)
        self.case_dir.mkdir()
        Image.new('RGB', (32, 18), (7, 8, 9)).save(self.case_dir/'frame.png')
        self.sha = hashlib.sha256((self.case_dir/'frame.png').read_bytes()).hexdigest()
        self.manifest = {
            'schema_version': 1, 'case_id': self.case_dir.name,
            'status': 'pending_review', 'created_at': '2026-10-07T00:00:00Z',
            'reason': 'identity_unresolved',
            'context': {'set_id': 'S18', 'patch': '16.19', 'target': 'ranked',
                        'domain': 'hex', 'source': 'bound_game'},
            'observation': {'scene': 'choice_unresolved', 'round': '2-1', 'cards': []},
            'evidence': {'catalog': {'hex': [{'id': '1625', 'name': 'example'}]}},
            'image': {'filename': 'frame.png', 'sha256': self.sha, 'width': 32, 'height': 18},
        }
        self.expected = {
            'schema_version': 1, 'image_sha256': self.sha,
            'set_id': 'S18', 'patch': '16.19',
            'scene': 'choice_candidates', 'round': '2-1',
            'cards': [{'slot': 0, 'id': '1625'}, {'slot': 1, 'id': None}, {'slot': 2, 'id': None}],
            'reviewed_by': 'human:test', 'review_note': 'Read each original card title.',
        }
        self.write_manifest()

    def write_manifest(self):
        (self.case_dir/'case.json').write_text(json.dumps(self.manifest), encoding='utf-8')

    def write_expected(self):
        (self.case_dir/'expected.json').write_text(json.dumps(self.expected), encoding='utf-8')

    def actual(self, ids=('1625', None, None), scene='choice_candidates', round_value='2-1'):
        return {'scene': scene, 'round': round_value,
                'cards': [{'slot': i, 'resolution': {'status': 'resolved', 'id': value}
                           if value is not None else {'status': 'unrecognized'}}
                          for i, value in enumerate(ids)]}

    def condition_case(self):
        self.manifest['context'].update(domain='condition', set_id=18)
        self.manifest['observation'] = {'scene': 'unknown', 'status': 'unknown',
                                        'entity': None, 'reason': 'detail_header_icon_unconfirmed'}
        self.manifest['evidence']['catalog'] = {
            'hex': [{'id': '1625', 'name': 'example hex'}],
            'equip': [{'id': '1001', 'name': 'example equip'}],
            'hero': [{'id': '11001', 'name': 'example hero'}], 'trait': [],
        }
        self.write_manifest()
        self.expected.pop('round')
        self.expected.update(set_id=18, scene='condition_detail', kind='equip',
                             cards=[{'slot': 0, 'id': '1001'}])

    def condition_actual(self, *, kind='equip', identity='1001', status='resolved', scene='condition_detail'):
        return {'scene': scene, 'status': status, 'route': 'detail', 'reason': 'primary_title',
                'entity': {'kind': kind, 'id': identity}, 'records_selected': False}

    def run_cases(self, actual=None, run_reviewed=True):
        runner = Mock(return_value=self.actual() if actual is None else actual)
        with patch.object(replay, '_make_runner', side_effect=AssertionError('must stay lazy')):
            result = replay.validate_cases(self.folder, run_reviewed=run_reviewed, runner=runner)
        return result, runner

    def assert_invalid_without_runner(self):
        report, runner = self.run_cases()
        self.assertEqual(report['summary']['invalid'], 1)
        self.assertEqual(report['summary']['passed'], 0)
        self.assertEqual(report['cases'][0]['result'], 'invalid')
        self.assertNotEqual(replay.exit_code(report), 0)
        runner.assert_not_called()
        return report

    def test_pending_is_listed_without_initializing_ocr(self):
        with patch.object(replay, '_make_runner', side_effect=AssertionError('must stay lazy')):
            report = replay.validate_cases(self.folder, run_reviewed=True)
        self.assertEqual(report['summary']['pending_review'], 1)
        self.assertEqual(report['summary']['reviewed'], 0)
        self.assertEqual(report['summary']['passed'], 0)
        self.assertEqual(report['status'], 'pending_review')
        self.assertEqual(replay.exit_code(report), 0)
        self.assertFalse((self.case_dir/'expected.json').exists())

    def test_default_inventory_never_runs_even_reviewed_cases(self):
        self.write_expected()
        report, runner = self.run_cases(run_reviewed=False)
        self.assertEqual(report['summary']['reviewed'], 1)
        self.assertEqual(report['summary']['skipped'], 1)
        self.assertEqual(report['summary']['passed'], 0)
        self.assertEqual(report['status'], 'not_run')
        runner.assert_not_called()

    def test_reviewed_identity_pass_uses_original_image_and_recorded_catalog(self):
        self.write_expected()
        before = {p.name: p.read_bytes() for p in self.case_dir.iterdir()}
        report, runner = self.run_cases()
        self.assertEqual(report['status'], 'passed')
        self.assertEqual(report['summary']['passed'], 1)
        image, manifest = runner.call_args.args
        self.assertEqual(image.size, (32, 18))
        self.assertEqual(image.getpixel((0, 0)), (7, 8, 9))
        self.assertEqual(manifest['evidence'], self.manifest['evidence'])
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.case_dir.iterdir()})
        self.assertIn('rankings', ' '.join(report['limits']))

    def test_real_original_frame_hash_mismatch_is_invalid(self):
        self.write_expected()
        Image.new('RGB', (32, 18), 'white').save(self.case_dir/'frame.png')
        self.assert_invalid_without_runner()

    def test_oracle_hash_must_bind_the_same_original(self):
        self.expected['image_sha256'] = 'b'*64
        self.write_expected()
        self.assert_invalid_without_runner()

    def test_oracle_must_be_complete_and_legally_typed(self):
        for field, value in [('cards', []), ('cards', None), ('reviewed_by', ''),
                             ('review_note', ' '), ('round', '2-10'),
                             ('scene', 'something_else'), ('schema_version', True), ('schema_version', 2),
                             ('patch', '16.20'), ('set_id', 'S19')]:
            with self.subTest(field=field, value=value):
                original = self.expected[field]
                self.expected[field] = value
                self.write_expected()
                self.assert_invalid_without_runner()
                self.expected[field] = original

    def test_missing_required_oracle_fields_are_invalid(self):
        for field in list(self.expected):
            with self.subTest(field=field):
                original = self.expected.pop(field)
                self.write_expected()
                self.assert_invalid_without_runner()
                self.expected[field] = original

    def test_duplicate_or_incomplete_oracle_slots_are_invalid(self):
        for cards in [[{'slot': 0, 'id': '1625'}, {'slot': 0, 'id': None}, {'slot': 2, 'id': None}],
                      [{'slot': 0, 'id': '1625'}],
                      [{'slot': True, 'id': '1625'}, {'slot': 1, 'id': None}, {'slot': 2, 'id': None}]]:
            with self.subTest(cards=cards):
                self.expected['cards'] = cards
                self.write_expected()
                self.assert_invalid_without_runner()

    def test_empty_or_malformed_oracle_is_invalid_not_pending(self):
        for text in ['{}', '[]', '', '{broken']:
            with self.subTest(text=text):
                (self.case_dir/'expected.json').write_text(text, encoding='utf-8')
                self.assert_invalid_without_runner()

    def test_unsupported_rank_assertions_cannot_pass_identity_only_replay(self):
        self.expected['statistics'] = {'avgPlacement': 4.2}
        self.write_expected()
        report = self.assert_invalid_without_runner()
        self.assertIn('rankings are not validated', report['cases'][0]['reason'])
        self.expected.pop('statistics')
        self.expected['cards'][0]['avgPlacement'] = 4.2
        self.write_expected()
        report = self.assert_invalid_without_runner()
        self.assertIn('rankings are not validated', report['cases'][0]['reason'])

    def test_identity_scene_round_or_extra_card_mismatch_fails(self):
        self.write_expected()
        for actual in [self.actual(ids=('999', None, None)),
                       self.actual(scene='choice_unresolved'), self.actual(round_value='3-2'),
                       self.actual(ids=('1625', None)), self.actual(ids=('1625', None, None, None))]:
            with self.subTest(actual=actual):
                report, runner = self.run_cases(actual)
                self.assertEqual(report['summary']['failed'], 1)
                self.assertEqual(report['summary']['passed'], 0)
                self.assertEqual(replay.exit_code(report), 1)
                runner.assert_called_once()

    def test_none_requires_rejected_identity(self):
        self.write_expected()
        report, _ = self.run_cases(self.actual(ids=('1625', 'wrong', None)))
        self.assertEqual(report['summary']['failed'], 1)
        report, _ = self.run_cases(self.actual())
        self.assertEqual(report['summary']['passed'], 1)

    def test_unknown_scene_explicit_rejection_can_pass(self):
        self.expected.update(scene='unknown', round=None, cards=[])
        self.write_expected()
        report, _ = self.run_cases(self.actual(ids=(), scene='unknown', round_value=None))
        self.assertEqual(report['summary']['passed'], 1)

    def test_unknown_actual_scene_does_not_pass_as_an_empty_rejection(self):
        self.expected.update(scene='unknown', round=None, cards=[])
        self.write_expected()
        report, _ = self.run_cases(self.actual(ids=(), scene='unrecognised_scene', round_value=None))
        self.assertEqual(report['summary']['failed'], 1)

    def test_invalid_version_manifest_is_never_executed(self):
        for version in [2, '1', True]:
            with self.subTest(version=version):
                self.manifest['schema_version'] = version
                self.write_manifest()
                self.write_expected()
                self.assert_invalid_without_runner()

    def test_missing_artifact_and_wrong_image_dimensions_are_invalid(self):
        self.write_expected()
        self.manifest['image']['width'] = 100
        self.write_manifest()
        self.assert_invalid_without_runner()
        self.manifest['image']['width'] = 32
        self.write_manifest()
        (self.case_dir/'frame.png').unlink()
        self.assert_invalid_without_runner()

    def test_missing_manifest_is_invalid(self):
        (self.case_dir/'case.json').unlink()
        self.assert_invalid_without_runner()

    def test_version_context_cannot_match_by_boolean_integer_coercion(self):
        self.manifest['context']['set_id'] = 1
        self.write_manifest()
        self.expected['set_id'] = True
        self.write_expected()
        self.assert_invalid_without_runner()

    def test_png_decode_failure_is_invalid_even_with_matching_hash(self):
        raw = b'not a PNG'
        (self.case_dir/'frame.png').write_bytes(raw)
        self.manifest['image']['sha256'] = hashlib.sha256(raw).hexdigest()
        self.write_manifest()
        self.assert_invalid_without_runner()

    def test_unsafe_image_dimensions_are_invalid_without_ocr(self):
        with patch.object(replay.Image, 'open', side_effect=Image.DecompressionBombError('unsafe dimensions')):
            self.assert_invalid_without_runner()

    def test_manifest_cannot_select_an_external_image(self):
        for filename in ['../frame.png', str(self.case_dir/'frame.png'), 'other.png']:
            with self.subTest(filename=filename):
                self.manifest['image']['filename'] = filename
                self.write_manifest()
                self.assert_invalid_without_runner()

    def test_case_id_must_match_case_directory_when_present(self):
        self.manifest['case_id'] = 'case-'+'b'*24
        self.write_manifest()
        self.assert_invalid_without_runner()

    def test_malformed_domain_and_catalog_are_invalid_without_crashing(self):
        for domain in [None, [], {}, 'other']:
            with self.subTest(domain=domain):
                self.manifest['context']['domain'] = domain
                self.write_manifest()
                self.assert_invalid_without_runner()
        self.manifest['context']['domain'] = 'hex'
        for catalog in [None, {}, {'hex': None}, {'hex': [1]}]:
            with self.subTest(catalog=catalog):
                self.manifest['evidence']['catalog'] = catalog
                self.write_manifest()
                self.assert_invalid_without_runner()

    def test_reparse_artifact_is_rejected_before_image_bytes_are_read(self):
        original_stat = Path.lstat
        original_read = Path.read_bytes

        def checked_stat(path):
            result = original_stat(path)
            if path == self.case_dir/'frame.png':
                return SimpleNamespace(st_mode=result.st_mode, st_file_attributes=0x400)
            return result

        def checked_read(path):
            if path == self.case_dir/'frame.png':
                self.fail('reparse frame must not be read')
            return original_read(path)

        with patch.object(Path, 'lstat', checked_stat), patch.object(Path, 'read_bytes', checked_read):
            self.assert_invalid_without_runner()

    def test_linked_case_directory_is_rejected_before_any_artifact_is_read(self):
        external = Path(self.temp.name)/'external-case'
        self.assertTrue(external.is_relative_to(Path(self.temp.name)))
        self.case_dir.replace(external)
        if os.name == 'nt':
            subprocess.run(['cmd', '/c', 'mklink', '/J', str(self.case_dir), str(external)],
                           check=True, capture_output=True)
        else:
            self.case_dir.symlink_to(external, target_is_directory=True)
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('linked artifacts must never be read')):
            self.assert_invalid_without_runner()

    def test_item_oracle_and_recorded_catalog_use_same_runner_seam(self):
        self.manifest['context']['domain'] = 'item'
        self.manifest['evidence']['catalog'] = {'equip': [{'id': '1625', 'name': 'example'}]}
        self.write_manifest()
        self.expected.pop('round')
        self.expected.update(scene='item_candidates', cards=[{'slot': i, 'id': '1625'} for i in range(3)])
        self.write_expected()
        report, runner = self.run_cases(self.actual(ids=('1625',)*3, scene='item_candidates'))
        self.assertEqual(report['summary']['passed'], 1)
        self.assertEqual(runner.call_args.args[1]['evidence']['catalog'], self.manifest['evidence']['catalog'])

    def test_engine_error_is_reported_as_failed(self):
        self.write_expected()
        report = replay.validate_cases(self.folder, run_reviewed=True, runner=Mock(side_effect=RuntimeError('engine unavailable')))
        self.assertEqual(report['summary']['failed'], 1)
        self.assertEqual(replay.exit_code(report), 1)

    def test_cli_report_does_not_overwrite_any_sample(self):
        report_path = self.case_dir/'frame.png'
        before = report_path.read_bytes()
        with self.assertRaises(SystemExit) as error:
            replay.main(['--cases-dir', str(self.folder), '--report', str(report_path)])
        self.assertEqual(error.exception.code, 2)
        self.assertEqual(report_path.read_bytes(), before)

    def test_cli_writes_structured_pending_report_without_an_engine(self):
        destination = Path(self.temp.name)/'report.json'
        with patch.object(replay, '_make_runner', side_effect=AssertionError('must stay lazy')):
            code = replay.main(['--cases-dir', str(self.folder), '--report', str(destination)])
        self.assertEqual(code, 0)
        report = json.loads(destination.read_text(encoding='utf-8'))
        self.assertEqual(report['status'], 'pending_review')
        self.assertEqual(report['summary']['passed'], 0)

    def test_external_report_hardlink_cannot_change_archived_image(self):
        destination = Path(self.temp.name)/'report.json'
        destination.hardlink_to(self.case_dir/'frame.png')
        before = (self.case_dir/'frame.png').read_bytes()
        self.assertEqual(replay.validate_report_path(destination, self.folder), destination)
        replay.write_report(replay.validate_cases(self.folder), destination, self.folder)
        self.assertEqual((self.case_dir/'frame.png').read_bytes(), before)
        self.assertEqual(json.loads(destination.read_text(encoding='utf-8'))['status'], 'pending_review')

    def test_shared_report_helper_rejects_an_archive_destination(self):
        destination = self.case_dir/'case.json'
        before = destination.read_bytes()
        with self.assertRaises(replay.InvalidCase):
            replay.validate_report_path(destination, self.folder)
        with self.assertRaises(replay.InvalidCase):
            replay.write_report({'status': 'test'}, destination, self.folder)
        self.assertEqual(destination.read_bytes(), before)

    def test_condition_pending_never_initializes_ocr(self):
        self.condition_case()
        with patch.object(replay, '_make_runner', side_effect=AssertionError('must stay lazy')):
            report = replay.validate_cases(self.folder, run_reviewed=True)
        self.assertEqual(report['status'], 'pending_review')
        self.assertEqual(report['summary']['pending_review'], 1)
        self.assertEqual(report['summary']['passed'], 0)

    def test_condition_reviewed_kind_and_identity_pass_without_changing_originals(self):
        self.condition_case()
        self.write_expected()
        before = {path.name: path.read_bytes() for path in self.case_dir.iterdir()}
        report, runner = self.run_cases(self.condition_actual())
        self.assertEqual(report['summary']['passed'], 1)
        self.assertEqual(report['cases'][0]['actual']['kind'], 'equip')
        self.assertEqual(report['cases'][0]['actual']['cards'], [{'slot': 0, 'id': '1001'}])
        self.assertEqual(report['cases'][0]['actual']['route'], 'detail')
        self.assertEqual(report['cases'][0]['actual']['reason'], 'primary_title')
        self.assertEqual(runner.call_args.args[1]['evidence']['catalog'], self.manifest['evidence']['catalog'])
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.case_dir.iterdir()})

    def test_condition_cross_kind_collision_and_wrong_id_fail(self):
        self.condition_case()
        self.write_expected()
        for actual in [self.condition_actual(kind='hex'), self.condition_actual(kind='hero'),
                       self.condition_actual(identity='1002')]:
            with self.subTest(actual=actual):
                report, runner = self.run_cases(actual)
                self.assertEqual(report['summary']['failed'], 1)
                self.assertEqual(report['summary']['passed'], 0)
                runner.assert_called_once()

    def test_condition_ambiguous_entity_is_not_resolved_even_when_id_matches(self):
        self.condition_case()
        self.write_expected()
        actual = self.condition_actual(status='ambiguous')
        report, _ = self.run_cases(actual)
        self.assertEqual(report['summary']['failed'], 1)
        self.assertIsNone(report['cases'][0]['actual']['kind'])
        self.assertEqual(report['cases'][0]['actual']['cards'], [{'slot': 0, 'id': None}])
        self.expected.update(kind=None, cards=[{'slot': 0, 'id': None}])
        self.write_expected()
        report, _ = self.run_cases(actual)
        self.assertEqual(report['summary']['passed'], 1)

    def test_condition_choice_priority_is_an_explicit_detail_rejection(self):
        self.condition_case()
        for scene, route in [('augment_choice', 'augment_stats'), ('equipment_choice', 'equipment_stats'),
                             ('unknown', 'none')]:
            with self.subTest(scene=scene):
                actual = {'scene': scene, 'status': 'unknown', 'entity': None,
                          'route': route, 'reason': 'priority_or_no_title'}
                self.write_expected()
                report, _ = self.run_cases(actual)
                self.assertEqual(report['summary']['failed'], 1)
                self.expected.update(scene='unknown', kind=None, cards=[])
                self.write_expected()
                report, _ = self.run_cases(actual)
                self.assertEqual(report['summary']['passed'], 1)
                self.assertEqual(report['cases'][0]['actual']['route'], route)
                self.assertEqual(report['cases'][0]['actual']['reason'], 'priority_or_no_title')
                self.expected.update(scene='condition_detail', kind='equip', cards=[{'slot': 0, 'id': '1001'}])

    def test_condition_requires_all_recorded_catalog_domains(self):
        self.condition_case()
        for key in ('hex', 'equip', 'hero', 'trait'):
            with self.subTest(key=key):
                rows = self.manifest['evidence']['catalog'].pop(key)
                self.write_manifest()
                self.assert_invalid_without_runner()
                self.manifest['evidence']['catalog'][key] = rows

    def test_condition_oracle_requires_strict_kind_and_single_identity(self):
        self.condition_case()
        original = json.loads(json.dumps(self.expected))
        variants = [dict(original, kind='trait'), dict(original, kind=[]), dict(original, kind=None),
                    dict(original, cards=[]), dict(original, cards=[{'slot': 1, 'id': '1001'}]),
                    dict(original, cards=[{'slot': 0, 'id': '1001'}, {'slot': 1, 'id': None}]),
                    dict(original, scene='unknown'), dict(original, scene='unknown', kind=None),
                    dict(original, cards=[{'slot': 0, 'id': None}])]
        no_kind = dict(original)
        no_kind.pop('kind')
        variants.append(no_kind)
        for expected in variants:
            with self.subTest(expected=expected):
                self.expected = expected
                self.write_expected()
                self.assert_invalid_without_runner()

    def test_condition_oracle_cannot_hide_extra_rank_or_route_assertions(self):
        self.condition_case()
        for key, value in [('statistics', {'avgPlacement': 4.2}), ('route', 'detail'), ('round', '2-1')]:
            with self.subTest(key=key):
                self.expected[key] = value
                self.write_expected()
                self.assert_invalid_without_runner()
                self.expected.pop(key)
        self.expected['cards'][0]['kind'] = 'equip'
        self.write_expected()
        self.assert_invalid_without_runner()

    def test_condition_unknown_actual_scene_and_malformed_resolved_entity_fail(self):
        self.condition_case()
        self.write_expected()
        for actual in [self.condition_actual(scene='unexpected'), self.condition_actual(kind='trait'),
                       self.condition_actual(identity=None), self.condition_actual(scene='unknown'),
                       {**self.condition_actual(), 'entity': None}]:
            with self.subTest(actual=actual):
                report, _ = self.run_cases(actual)
                self.assertEqual(report['summary']['failed'], 1)

    def test_condition_lazy_runner_builds_resolver_from_frozen_catalog_and_set(self):
        self.condition_case()
        self.write_expected()
        vision = object()
        resolver = object()
        reader = SimpleNamespace(read=Mock(return_value=self.condition_actual()))
        vision_factory = Mock(return_value=vision)
        resolver_factory = Mock(return_value=resolver)
        reader_factory = Mock(return_value=reader)
        modules = {'vision': SimpleNamespace(Vision=vision_factory),
                   'item_vision': SimpleNamespace(analyze_items=Mock(side_effect=AssertionError('wrong domain'))),
                   'entity_identity': SimpleNamespace(EntityResolver=resolver_factory),
                   'condition_reader': SimpleNamespace(ConditionReader=reader_factory)}
        with patch.dict(sys.modules, modules):
            report = replay.validate_cases(self.folder, run_reviewed=True)
        self.assertEqual(report['summary']['passed'], 1)
        vision_factory.assert_called_once_with()
        resolver_factory.assert_called_once_with(self.manifest['evidence']['catalog'], set_id=18)
        reader_factory.assert_called_once_with(vision, resolver)
        reader.read.assert_called_once()
        self.assertEqual(reader.read.call_args.args[0].getpixel((0, 0)), (7, 8, 9))


if __name__ == '__main__':
    unittest.main()
