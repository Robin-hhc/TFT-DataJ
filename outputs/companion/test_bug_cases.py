import copy
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image

from bug_cases import BugCaseStore


class BugCaseStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.directory = self.root / 'cases'
        self.store = BugCaseStore(self.directory)
        self.image = Image.new('RGB', (37, 19), (20, 80, 150))
        self.observation = {
            'scene': 'choice_unresolved', 'round': '2-1', 'elapsed_ms': 21.3,
            'cards': [{'slot': 0, 'raw_text': '成吨的属性！', 'box': [[1, 2], [3, 4]],
                       'resolution': {'status': 'ambiguous', 'readings': ['成吨的属性！'] * 3,
                                      'candidates': [{'id': '20', 'name': '成吨的属性！'},
                                                     {'id': '10', 'name': '成吨的属性！'}]}}],
        }
        self.context = {'set_id': 's16', 'patch': '18.3', 'target': '123',
                        'domain': 'hex', 'source': 'bound_game', 'frame_scope': 'game',
                        'session_id': 'game-1', 'average_rank': 4.1}

    def save(self, store=None, **kwargs):
        return (store or self.store).save(
            kwargs.pop('image', self.image), kwargs.pop('observation', self.observation),
            reason=kwargs.pop('reason', 'ambiguous_identity'),
            context=kwargs.pop('context', self.context), **kwargs)

    def fingerprint(self, observation=None, context=None, reason='ambiguous_identity'):
        return self.store.fingerprint(observation or self.observation, reason,
                                      context or self.context)

    def test_real_png_hash_and_complete_review_metadata(self):
        before = copy.deepcopy(self.observation)
        evidence = {'catalog': {'domain': 'hex', 'rows': [{'id': '10', 'desc': '原始说明'}]},
                    'capture': {'source': 'bound_game'}}
        saved = self.save(evidence=evidence)
        self.assertEqual(saved['status'], 'saved')
        self.assertRegex(saved['case_id'], r'^[0-9a-f]{64}$')
        directory = Path(saved['path'])
        self.assertEqual(directory.name, 'case-' + saved['case_id'])
        self.assertEqual(set(path.name for path in directory.iterdir()), {'frame.png', 'case.json'})
        image_bytes = (directory / 'frame.png').read_bytes()
        with Image.open(directory / 'frame.png') as image:
            self.assertEqual(image.format, 'PNG')
            self.assertEqual(image.size, (37, 19))
            self.assertEqual(image.getpixel((0, 0)), (20, 80, 150))
        metadata = json.loads((directory / 'case.json').read_text(encoding='utf-8'))
        self.assertEqual(metadata['schema_version'], 1)
        self.assertEqual(metadata['case_id'], saved['case_id'])
        self.assertEqual(metadata['status'], 'pending_review')
        self.assertTrue(metadata['created_at'].endswith('+00:00'))
        self.assertEqual(metadata['reason'], 'ambiguous_identity')
        self.assertEqual(metadata['context'], self.context)
        self.assertEqual(metadata['observation'], self.observation)
        self.assertEqual(metadata['evidence'], evidence)
        self.assertEqual(metadata['image'], {'filename': 'frame.png', 'width': 37, 'height': 19,
                                            'sha256': hashlib.sha256(image_bytes).hexdigest()})
        self.assertNotEqual(saved['case_id'], metadata['image']['sha256'])
        self.assertEqual(self.observation, before)

    def test_restart_deduplicates_volatile_metadata_without_overwriting(self):
        first = self.save(evidence={'first': True})
        directory = Path(first['path'])
        originals = {path.name: path.read_bytes() for path in directory.iterdir()}
        observation = copy.deepcopy(self.observation)
        observation.update(elapsed_ms=999, timestamp='tomorrow', average_rank=8)
        observation['cards'][0]['resolution']['readings'] = ['different OCR view']
        observation['cards'][0]['resolution']['candidates'].reverse()
        context = {**self.context, 'session_id': 'game-2', 'average_rank': 7.9,
                   'timestamp': 'later', 'capture_time': 150}
        second = self.save(BugCaseStore(self.directory), image=Image.new('RGB', (8, 8)),
                           observation=observation, context=context, evidence={'second': True})
        self.assertEqual(second, {**first, 'status': 'duplicate'})
        self.assertEqual(originals, {path.name: path.read_bytes() for path in directory.iterdir()})
        self.assertEqual(len(list(self.directory.iterdir())), 1)

    def test_identity_changes_for_context_reason_and_slots(self):
        original = self.fingerprint()
        for key in ('set_id', 'patch', 'target', 'domain', 'source', 'frame_scope'):
            with self.subTest(context=key):
                self.assertNotEqual(original, self.fingerprint(context={**self.context, key: 'other'}))
        self.assertNotEqual(original, self.fingerprint(reason='unrecognized_identity'))
        for key, value in (('scene', 'choice_candidates'), ('round', '3-2')):
            with self.subTest(observation=key):
                self.assertNotEqual(original, self.fingerprint({**self.observation, key: value}))
        for field, value in (('status', 'resolved'), ('id', '10'), ('suggested_id', '10'),
                             ('candidates', [{'id': '30'}])):
            observation = copy.deepcopy(self.observation)
            observation['cards'][0]['resolution'][field] = value
            with self.subTest(resolution=field):
                self.assertNotEqual(original, self.fingerprint(observation))
        for field, value in (('slot', 1), ('raw_text', '其他选项')):
            observation = copy.deepcopy(self.observation)
            observation['cards'][0][field] = value
            self.assertNotEqual(original, self.fingerprint(observation))

    def test_ocr_normalization_preserves_punctuation_plus_and_numeric_suffixes(self):
        def identity(text):
            observation = copy.deepcopy(self.observation)
            observation['cards'][0]['raw_text'] = text
            return self.fingerprint(observation)
        self.assertEqual(identity(' 护甲 Ⅰ\n'), identity('护甲 I'))
        self.assertNotEqual(identity('护甲 I'), identity('护甲 1'))
        self.assertNotEqual(identity('选项A'), identity('选项A+'))
        self.assertNotEqual(identity('属性！'), identity('属性'))

    def test_readings_fallback_deduplicates_order_and_repeated_views(self):
        observation = copy.deepcopy(self.observation)
        observation['cards'][0].pop('raw_text')
        resolution = observation['cards'][0]['resolution']
        resolution['readings'] = ['护甲 Ⅰ', '其他', '护甲 Ⅰ']
        first = self.fingerprint(observation)
        resolution['readings'] = ['其 他', '护甲 I']
        self.assertEqual(first, self.fingerprint(observation))
        resolution['readings'].append('全新读数')
        self.assertNotEqual(first, self.fingerprint(observation))

    def test_unknown_scene_without_cards_has_stable_fingerprint(self):
        first = self.store.fingerprint({'scene': 'unknown', 'round': None, 'cards': []},
                                       'no_refresh_glyphs', self.context)
        second = self.store.fingerprint({'scene': 'unknown', 'elapsed_ms': 30},
                                        'no_refresh_glyphs', {**self.context, 'session_id': 'new'})
        self.assertRegex(first, r'^[0-9a-f]{64}$')
        self.assertEqual(first, second)
        self.assertNotEqual(first, self.store.fingerprint({'scene': 'unknown'},
                                                         'unsupported_layout', self.context))
        self.assertEqual(self.save(observation={'scene': 'unknown'})['status'], 'saved')

    def test_manual_unknown_frames_use_explicit_pixel_identity_across_restarts(self):
        observation = {'scene': 'unknown', 'cards': [], 'round': None,
                       'manual_frame_id': hashlib.sha256(b'first pixels').hexdigest()}
        first = self.save(observation=observation, reason='manual_report')
        self.assertEqual(first['status'], 'saved')
        same = self.save(BugCaseStore(self.directory), observation=observation,
                         reason='manual_report', context={**self.context, 'session_id': 'new'})
        self.assertEqual(same, {**first, 'status': 'duplicate'})
        other = {**observation, 'manual_frame_id': hashlib.sha256(b'other pixels').hexdigest()}
        second = self.save(observation=other, reason='manual_report',
                           image=Image.new('RGB', (37, 19), 'white'))
        self.assertEqual(second['status'], 'saved')
        self.assertNotEqual(first['case_id'], second['case_id'])
        self.assertEqual(len(list(self.directory.iterdir())), 2)
        self.assertEqual(self.fingerprint(observation), self.fingerprint(other))

    def condition_result(self):
        return {'scene': 'unknown', 'route': 'none', 'status': 'unknown',
                'reason': 'primary_title_unconfirmed',
                'evidence': {'readings': ['护甲 Ⅰ', '其他+'],
                             'title_rect': [40, 50, 300, 90],
                             'popup_rect': [10, 20, 330, 180]},
                'candidates': [{'kind': 'hex', 'id': '10', 'name': '护甲 I'},
                               {'kind': 'equip', 'id': '20', 'name': '其他+'}]}

    def condition_fingerprint(self, result):
        return self.fingerprint(result, {**self.context, 'domain': 'condition'},
                                reason='condition_unresolved')

    def test_condition_identity_separates_reason_status_route_title_and_candidates(self):
        result = self.condition_result()
        original = self.condition_fingerprint(result)
        for key, value in (('reason', 'no_verified_detail_panel'), ('status', 'unrecognized'),
                           ('route', 'detail')):
            with self.subTest(field=key):
                self.assertNotEqual(original, self.condition_fingerprint({**result, key: value}))
        for key, value in (('readings', ['全新标题']), ('title_rect', [48, 56, 308, 96]),
                           ('popup_rect', [18, 28, 338, 188])):
            changed = copy.deepcopy(result)
            changed['evidence'][key] = value
            with self.subTest(evidence=key):
                self.assertNotEqual(original, self.condition_fingerprint(changed))
        for key, value in (('kind', 'hero'), ('id', '30')):
            changed = copy.deepcopy(result)
            changed['candidates'][0][key] = value
            with self.subTest(candidate=key):
                self.assertNotEqual(original, self.condition_fingerprint(changed))

    def test_condition_identity_normalizes_repeated_readings_and_candidate_order(self):
        result = self.condition_result()
        original = self.condition_fingerprint(result)
        changed = copy.deepcopy(result)
        changed['evidence']['readings'] = [' 其 他+ ', '护甲 I', '护甲 I']
        changed['evidence']['title_rect'] = tuple(result['evidence']['title_rect'])
        changed['evidence']['ocr_ms'] = 500
        changed['candidates'].reverse()
        changed['candidates'].append(copy.deepcopy(changed['candidates'][0]))
        for candidate in changed['candidates']:
            candidate.update(name='changed metadata', average_rank=8)
        self.assertEqual(original, self.condition_fingerprint(changed))

    def test_condition_readings_preserve_plus_punctuation_and_numeric_suffix(self):
        def identity(text):
            result = self.condition_result()
            result['evidence']['readings'] = [text]
            return self.condition_fingerprint(result)
        self.assertEqual(identity('护甲 Ⅰ'), identity('护甲 I'))
        self.assertNotEqual(identity('护甲 I'), identity('护甲 1'))
        self.assertNotEqual(identity('标题A'), identity('标题A+'))
        self.assertNotEqual(identity('属性！'), identity('属性'))

    def test_condition_unknown_without_panel_ignores_volatile_data(self):
        result = {'scene': 'unknown', 'route': 'none', 'status': 'unknown',
                  'reason': 'no_verified_detail_panel', 'evidence': {}, 'candidates': []}
        context = {**self.context, 'domain': 'condition'}
        first = self.fingerprint(result, context, reason='condition_unresolved')
        other = {**result, 'elapsed_ms': 250, 'timestamp': 'later', 'image_sha256': 'other',
                 'evidence': {'readings': [], 'title_rect': None, 'popup_rect': None}}
        self.assertEqual(first, self.fingerprint(other, {**context, 'session_id': 'new'},
                                                reason='condition_unresolved'))

    def test_condition_fields_do_not_change_hex_or_item_fingerprints(self):
        result = self.condition_result()
        other = {**result, 'status': 'other', 'route': 'other', 'reason': 'other',
                 'candidates': [{'kind': 'hero', 'id': '99'}],
                 'evidence': {'readings': ['new title'], 'title_rect': [1, 2, 3, 4]}}
        for domain in ('hex', 'item'):
            context = {**self.context, 'domain': domain}
            with self.subTest(domain=domain):
                self.assertEqual(self.fingerprint(result, context), self.fingerprint(other, context))

    def test_condition_failures_save_distinct_titles_and_dedupe_across_restart(self):
        result = self.condition_result()
        context = {**self.context, 'domain': 'condition'}
        first = self.save(observation=result, context=context, reason='condition_unresolved')
        self.assertEqual(first['status'], 'saved')
        duplicate = self.save(BugCaseStore(self.directory), observation=copy.deepcopy(result),
                              context={**context, 'session_id': 'new'}, reason='condition_unresolved')
        self.assertEqual(duplicate, {**first, 'status': 'duplicate'})
        result['evidence']['readings'] = ['新的未读到标题']
        second = self.save(observation=result, context=context, reason='condition_unresolved')
        self.assertEqual(second['status'], 'saved')
        self.assertNotEqual(first['case_id'], second['case_id'])
        self.assertEqual(len(list(self.directory.iterdir())), 2)
        metadata = json.loads((Path(second['path']) / 'case.json').read_text(encoding='utf-8'))
        self.assertEqual(metadata['observation'], result)

    def test_case_limit_preserves_samples_and_checks_before_encoding(self):
        first = self.save(BugCaseStore(self.directory, max_cases=1))
        files = {str(path): path.read_bytes() for path in Path(first['path']).iterdir()}
        with patch.object(self.image, 'save', side_effect=AssertionError('must not encode')):
            result = self.save(BugCaseStore(self.directory, max_cases=1), reason='other')
        self.assertEqual(result['status'], 'limit')
        self.assertIsNone(result['path'])
        self.assertEqual(files, {str(path): path.read_bytes() for path in Path(first['path']).iterdir()})
        self.assertEqual(self.save(BugCaseStore(self.directory, max_cases=1))['status'], 'duplicate')
        self.assertEqual(len(list(self.directory.iterdir())), 1)

    def test_bytes_limit_before_and_after_encoding_cleans_only_own_temp(self):
        self.directory.mkdir()
        abandoned = self.directory / '.pending-from-old-run'
        abandoned.mkdir()
        (abandoned / 'frame.png').write_bytes(b'preserve')
        result = self.save(BugCaseStore(self.directory, max_bytes=8))
        self.assertEqual(result['status'], 'limit')
        self.assertEqual(list(self.directory.iterdir()), [abandoned])
        self.assertEqual((abandoned / 'frame.png').read_bytes(), b'preserve')
        with patch.object(self.image, 'save', side_effect=AssertionError('must not encode')):
            self.assertEqual(self.save(BugCaseStore(self.directory, max_bytes=8))['status'], 'limit')

    def test_new_case_exceeding_byte_limit_leaves_no_partial_directory(self):
        result = self.save(BugCaseStore(self.directory, max_bytes=1))
        self.assertEqual(result['status'], 'limit')
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_usage_rechecked_after_encoding(self):
        self.directory.mkdir()
        original_save = self.image.save

        def encode_and_fill(stream, **kwargs):
            original_save(stream, **kwargs)
            (self.directory / 'other-writer.bin').write_bytes(b'x' * 2048)

        with patch.object(self.image, 'save', side_effect=encode_and_fill):
            result = self.save(BugCaseStore(self.directory, max_bytes=2048))
        self.assertEqual(result['status'], 'limit')
        self.assertEqual([path.name for path in self.directory.iterdir()], ['other-writer.bin'])

    def test_partial_image_write_failure_is_swallowed_and_cleaned(self):
        def failed_encode(stream, **kwargs):
            stream.write(b'partial PNG')
            raise OSError('disk full')

        with patch.object(self.image, 'save', side_effect=failed_encode):
            result = self.save()
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['error'], 'OSError')
        self.assertEqual(list(self.directory.iterdir()), [])
        self.assertEqual(self.save()['status'], 'saved')

    def test_metadata_and_publish_failures_are_swallowed_and_cleaned(self):
        for operation in ('bug_cases.json.dump', 'bug_cases.os.rename'):
            with self.subTest(operation=operation):
                with patch(operation, side_effect=OSError('disk failed')):
                    result = self.save()
                self.assertEqual(result['status'], 'error')
                self.assertEqual(list(self.directory.iterdir()), [])

    def test_unserializable_metadata_does_not_discard_valid_fields(self):
        class Unsupported:
            def __repr__(self):
                raise ValueError('no repr')

        @dataclass
        class Evidence:
            field: str

        cycle = {'good': 'keep'}
        cycle['self'] = cycle
        observation = {**self.observation, 'unsupported': Unsupported(), 'cycle': cycle}
        context = {**self.context, 'extra': {'unsupported': Unsupported(), 'good': [1, 'two']},
                   'path': Path('relative/file'), 'bytes': b'\x00\xff', 'not_finite': float('nan')}
        saved = self.save(observation=observation, context=context,
                          evidence={'details': Evidence('keep'), 'values': {3, 1}})
        self.assertEqual(saved['status'], 'saved')
        metadata = json.loads((Path(saved['path']) / 'case.json').read_text(encoding='utf-8'))
        self.assertEqual(metadata['observation']['cards'], self.observation['cards'])
        self.assertEqual(metadata['observation']['cycle']['good'], 'keep')
        self.assertEqual(metadata['observation']['cycle']['self']['reason'], 'circular_reference')
        self.assertIn('unserializable_type', metadata['context']['extra']['unsupported'])
        self.assertEqual(metadata['context']['extra']['good'], [1, 'two'])
        self.assertEqual(metadata['context']['bytes'], {'encoding': 'base64', 'data': 'AP8='})
        self.assertEqual(metadata['evidence'], {'details': {'field': 'keep'}, 'values': [1, 3]})

    def test_damaged_existing_case_is_never_overwritten(self):
        first = self.save()
        metadata = Path(first['path']) / 'case.json'
        metadata.write_bytes(b'broken metadata')
        original_image = (metadata.parent / 'frame.png').read_bytes()
        result = self.save(BugCaseStore(self.directory))
        self.assertEqual(result['status'], 'error')
        self.assertEqual(metadata.read_bytes(), b'broken metadata')
        self.assertEqual((metadata.parent / 'frame.png').read_bytes(), original_image)
        self.assertEqual(len(list(self.directory.iterdir())), 1)

    def test_corrupted_png_is_not_treated_as_successful_duplicate(self):
        first = self.save()
        image = Path(first['path']) / 'frame.png'
        image.write_bytes(b'corrupt')
        result = self.save(BugCaseStore(self.directory))
        self.assertEqual(result['status'], 'error')
        self.assertEqual(image.read_bytes(), b'corrupt')

    def test_unrecognized_case_entries_consume_limits_and_are_preserved(self):
        self.directory.mkdir()
        malformed = self.directory / 'case-broken'
        malformed.write_bytes(b'damaged sample')
        result = self.save(BugCaseStore(self.directory, max_cases=1))
        self.assertEqual(result['status'], 'limit')
        self.assertEqual(malformed.read_bytes(), b'damaged sample')
        self.assertEqual(list(self.directory.iterdir()), [malformed])

    def test_existing_file_at_case_path_is_preserved(self):
        self.directory.mkdir()
        existing = self.directory / ('case-' + self.fingerprint())
        existing.write_bytes(b'never replace')
        self.assertEqual(self.save()['status'], 'error')
        self.assertEqual(existing.read_bytes(), b'never replace')

    def make_directory_link(self, link, target):
        try:
            os.symlink(target, link, target_is_directory=True)
        except OSError:
            if os.name != 'nt':
                self.skipTest('Directory symlinks unavailable')
            result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)],
                                    capture_output=True, text=True)
            if result.returncode:
                self.skipTest('Directory symlinks and junctions unavailable')

    def test_directory_link_and_link_ancestor_never_write_to_target(self):
        target = self.root / 'outside'
        target.mkdir()
        link = self.root / 'linked'
        self.make_directory_link(link, target)
        for directory in (link, link / 'new-child'):
            with self.subTest(directory=directory):
                self.assertEqual(self.save(BugCaseStore(directory))['status'], 'error')
                self.assertEqual(list(target.iterdir()), [])

    def test_link_inside_store_blocks_saving_without_traversal(self):
        self.directory.mkdir()
        target = self.root / 'outside'
        target.mkdir()
        (target / 'keep.txt').write_bytes(b'keep')
        self.make_directory_link(self.directory / 'external', target)
        self.assertEqual(self.save()['status'], 'error')
        self.assertEqual((target / 'keep.txt').read_bytes(), b'keep')
        self.assertEqual([path.name for path in self.directory.iterdir()], ['external'])

    def test_default_directory_uses_application_state(self):
        with patch.dict(sys.modules, {'bootstrap': SimpleNamespace(STATE_DIR=self.root)}):
            store = BugCaseStore()
        self.assertEqual(store.directory, self.root / 'bug-cases')
        self.assertEqual(self.save(store)['status'], 'saved')


if __name__ == '__main__':
    unittest.main()
