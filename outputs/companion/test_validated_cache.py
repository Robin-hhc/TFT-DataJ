"""Public DataJ/cache lifecycle contracts; all sources and databases are isolated."""
import json
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import httpx
from dataj import DataJ, SourceError


class ValidatedCacheTests(unittest.TestCase):
    @staticmethod
    def seed(db, path, data, *, params=None, body=None, fetched=None, serialized=None):
        # This is the existing on-disk format, constructed independently of
        # DataJ's private identity helpers to model a pre-upgrade database.
        key = json.dumps(['POST' if body is not None else 'GET', path,
                          params or {'setId': 18}, body], sort_keys=True, ensure_ascii=False)
        with closing(sqlite3.connect(db, isolation_level=None)) as connection:
            connection.execute('INSERT OR REPLACE INTO cache VALUES(?,?,?)',
                (key, time.time() if fetched is None else fetched,
                 json.dumps(data, ensure_ascii=False) if serialized is None else serialized))
        return key

    def assert_recovers(self, call, invalid, valid):
        with tempfile.TemporaryDirectory() as temporary:
            db = Path(temporary) / 'cache.sqlite'
            responses = [invalid, valid]
            calls = []
            def respond(request):
                calls.append(request)
                return httpx.Response(200, json={
                    'success': True, 'code': 200, 'data': responses.pop(0)})
            transport = httpx.MockTransport(respond)
            adapter = DataJ(patch='18.4', db=db, transport=transport)
            with self.assertRaises(SourceError):
                call(adapter)
            # A fresh instance is the real persistence/restart seam, not a
            # replacement in-memory return value.
            restarted = DataJ(patch='18.4', db=db, transport=transport)
            repaired = call(restarted)
            self.assertEqual(repaired['data'], valid)
            self.assertFalse(repaired['cached'])
            self.assertEqual(len(calls), 2)
            self.assertTrue(call(restarted)['cached'])
            self.assertEqual(len(calls), 2, 'A healthy hit must not add HTTP')
            return calls

    def test_catalog_rejects_bad_source_then_recovers_after_restart(self):
        calls = self.assert_recovers(lambda adapter: adapter.catalog(),
                                    {'hex': 'invalid'}, {'hex': []})
        self.assertEqual(dict(calls[1].url.params), {'setId': '18'})

    def test_composition_ranks_recover_with_exact_minimum_and_patch(self):
        calls = self.assert_recovers(lambda adapter: adapter.comps(min_sample=100), {}, [])
        self.assertEqual(dict(calls[1].url.params),
                         {'setId': '18', 'gameVersion': '18.4', 'minSample': '100'})

    def test_composition_details_recover_without_reusing_wrong_identity(self):
        calls = self.assert_recovers(lambda adapter: adapter.comp('107'),
            {'compId': '999', 'heroes': []}, {'compId': '107', 'heroes': []})
        self.assertTrue(calls[1].url.path.endswith('/comp/107'))

    def test_hero_equipment_recovers_with_exact_hero_query(self):
        valid = {'compId': '107', 'heroId': '4503', 'heroEquips': [], 'hero3Equips': []}
        calls = self.assert_recovers(lambda adapter: adapter.equipment('107', '4503'),
                                    {**valid, 'heroId': '999'}, valid)
        self.assertEqual(dict(calls[1].url.params),
                         {'setId': '18', 'gameVersion': '18.4', 'heroId': '4503'})

    def test_item_statistics_recover_in_global_and_pinned_scopes(self):
        for comp in (None, '107'):
            with self.subTest(comp=comp):
                valid = [] if comp is None else {'compId': '107', 'equips': []}
                self.assert_recovers(lambda adapter: adapter.item_stats(comp), {}, valid)

    def test_item_holders_recover_with_exact_equipment_and_composition(self):
        for comp in (None, '107'):
            with self.subTest(comp=comp):
                valid = [] if comp is None else {'compId': '107', 'equipId': '2004', 'heroes': []}
                calls = self.assert_recovers(lambda adapter: adapter.item_holders('2004', comp), {}, valid)
                if comp is not None:
                    self.assertEqual(calls[1].url.params['equipId'], '2004')

    def test_explorer_recovers_with_exact_body_and_acquisition_stage(self):
        calls = self.assert_recovers(lambda adapter: adapter.explore('hex',
            {'id': '1023', 'name': '应急护甲 I'}, hex_stage='3-2'), {}, {'comps': []})
        body = json.loads(calls[1].content)
        self.assertEqual((body['setId'], body['version']), (18, '18.4'))
        self.assertEqual(body['filter']['rules'], [{
            'starCount': '', 'type': 'hex', 'targetId': '1023', 'enable': True,
            'targetName': '应急护甲 I', 'hexRound': '1', 'nameMatch': False,
            'equipCarry': '', 'equipCount': '', 'exclude': False}])

    def test_invalid_hex_refresh_cannot_replace_last_good_statistics(self):
        with tempfile.TemporaryDirectory() as temporary:
            calls = []
            good = [{'hexId': '1023', 'roundStats': []}]
            def respond(request):
                calls.append(request)
                return httpx.Response(200, json={'success': True, 'code': 200,
                    'data': good if len(calls) == 1 else {}})
            transport = httpx.MockTransport(respond)
            adapter = DataJ(db=Path(temporary) / 'cache.sqlite', transport=transport)
            self.assertEqual(adapter.hexes()['data'], good)
            adapter.next_request = 0
            def refresh(path, **kwargs):
                return adapter.request(path, ttl=0, **kwargs)
            with self.assertRaises(SourceError):
                adapter.hexes(_request=refresh)
            restarted = DataJ(db=adapter.db, transport=transport)
            last_good = restarted.hexes()
            self.assertEqual(last_good['data'], good)
            self.assertTrue(last_good['cached'])
            self.assertEqual(len(calls), 2)

    def test_catalog_snapshot_keeps_expired_good_data_after_bad_refresh(self):
        with tempfile.TemporaryDirectory() as temporary:
            calls = []
            good = {'hex': [{'id': 1023, 'name': '应急护甲 I'}]}
            def respond(request):
                calls.append(request)
                return httpx.Response(200, json={'success': True, 'code': 200,
                    'data': good if len(calls) == 1 else {'hex': 'invalid'}})
            adapter = DataJ(db=Path(temporary) / 'cache.sqlite',
                            transport=httpx.MockTransport(respond))
            original = adapter.catalog()
            adapter.next_request = 0
            with patch('dataj.time.time', return_value=original['fetched_at'] + 7200):
                local = adapter.catalog_snapshot()
                self.assertEqual(local['data'], good)
                self.assertTrue(local['cached'])
                self.assertTrue(local['stale'])
                self.assertEqual(len(calls), 1, 'Local snapshot cannot issue HTTP')
                with self.assertRaises(SourceError):adapter.catalog()
                local = adapter.catalog_snapshot()
                self.assertEqual(local['data'], good)
                self.assertEqual(local['fetched_at'], original['fetched_at'])
                self.assertTrue(local['stale'])
                self.assertEqual(len(calls), 2)

    def test_legacy_bad_entries_are_repaired_for_each_public_query(self):
        params = {'setId': 18, 'gameVersion': '18.4'}
        entity = {'id': '1023', 'name': '应急护甲 I'}
        body = {'version': '18.4', 'setId': 18, 'filter': {'combinator': 'and', 'rules': [{
            'starCount': '', 'type': 'hex', 'targetId': '1023', 'enable': True,
            'targetName': '应急护甲 I', 'hexRound': '1', 'nameMatch': False,
            'equipCarry': '', 'equipCount': '', 'exclude': False}]}}
        cases = [
            ('catalog', lambda a: a.catalog(), '/gamedata', {'setId': 18}, None, {'hex': []}, {'hex': []}),
            ('ranks', lambda a: a.comps(100), '/comp/rank', {**params, 'minSample': 100}, None, [], []),
            ('details', lambda a: a.comp('107'), '/comp/107', params, None, {'compId': '107', 'heroes': []}, {'compId': '107', 'heroes': []}),
            ('equipment', lambda a: a.equipment('107', '4503'), '/comp/107/hero-equips', {**params, 'heroId': '4503'}, None,
             {'compId': '107', 'heroId': '4503', 'heroEquips': [], 'hero3Equips': []},
             {'compId': '107', 'heroId': '4503', 'heroEquips': [], 'hero3Equips': []}),
            ('items-global', lambda a: a.item_stats(), '/stats/equip', params, None, [], []),
            ('items-comp', lambda a: a.item_stats('107'), '/comp/107/equips', params, None, {'compId': '107', 'equips': []}, {'compId': '107', 'equips': []}),
            ('holders-global', lambda a: a.item_holders('2004'), '/stats/equip/2004/heroes', params, None, [], []),
            ('holders-comp', lambda a: a.item_holders('2004', '107'), '/comp/107/equip-heroes', {**params, 'equipId': '2004'}, None,
             {'compId': '107', 'equipId': '2004', 'heroes': []}, {'compId': '107', 'equipId': '2004', 'heroes': []}),
            ('hex-global', lambda a: a.hexes(), '/stats/hex', params, None, [], []),
            ('hex-comp', lambda a: a.hexes('107'), '/comp/107/hexes', params, None, {'compId': '107', 'hexes': []}, []),
            ('explorer', lambda a: a.explore('hex', entity, hex_stage='3-2'), '/explorer/query', params, body, {'comps': []}, {'comps': []}),
            ('exact-explorer', lambda a: a.explore('hex', entity, hex_stage='3-2', required_comp='107'), '/explorer/query', params, body, {'comps': []}, {'comps': []}),
        ]
        for name, call, path, query, request_body, good, expected in cases:
            with self.subTest(endpoint=name), tempfile.TemporaryDirectory() as temporary:
                calls = []
                def respond(request):
                    calls.append(request)
                    return httpx.Response(200, json={'success': True, 'code': 200, 'data': good})
                adapter = DataJ(patch='18.4', db=Path(temporary) / 'cache.sqlite',
                                transport=httpx.MockTransport(respond))
                self.seed(adapter.db, path, {'legacy': 'invalid'}, params=query, body=request_body)
                repaired = call(adapter)
                self.assertEqual(repaired['data'], expected)
                self.assertFalse(repaired['cached'])
                self.assertTrue(call(adapter)['cached'])
                self.assertEqual(len(calls), 1)

    def test_invalid_persisted_json_does_not_break_local_snapshot_or_recovery(self):
        with tempfile.TemporaryDirectory() as temporary:
            calls = []
            def respond(request):
                calls.append(request)
                return httpx.Response(200, json={'success': True, 'code': 200, 'data': {'hex': []}})
            adapter = DataJ(db=Path(temporary) / 'cache.sqlite', transport=httpx.MockTransport(respond))
            self.seed(adapter.db, '/gamedata', None, serialized='{broken')
            self.assertIsNone(adapter.catalog_snapshot())
            self.assertEqual(calls, [])
            self.assertEqual(adapter.catalog()['data'], {'hex': []})
            self.assertEqual(len(calls), 1)

    def test_local_snapshot_does_not_borrow_another_set_or_bad_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            def unexpected(request):
                self.fail('catalog_snapshot must never access HTTP')
            adapter = DataJ(db=Path(temporary) / 'cache.sqlite', transport=httpx.MockTransport(unexpected))
            self.seed(adapter.db, '/gamedata', {'hex': []}, params={'setId': 19})
            self.assertIsNone(adapter.catalog_snapshot())
            self.seed(adapter.db, '/gamedata', {'hex': 'invalid'})
            self.assertIsNone(adapter.catalog_snapshot())
            self.seed(adapter.db, '/gamedata', {'hex': []})
            self.assertFalse(adapter.catalog_snapshot()['stale'])

    def test_expired_statistics_are_not_returned_as_last_good_during_outage(self):
        with tempfile.TemporaryDirectory() as temporary:
            calls = []
            def unavailable(request):
                calls.append(request)
                return httpx.Response(503)
            adapter = DataJ(patch='18.4', db=Path(temporary) / 'cache.sqlite',
                            transport=httpx.MockTransport(unavailable))
            self.seed(adapter.db, '/gamedata', {'hex': []}, fetched=time.time()-7200)
            self.seed(adapter.db, '/stats/hex', [],
                      params={'setId': 18, 'gameVersion': '18.4'}, fetched=time.time()-1800)
            with self.assertRaises(SourceError):adapter.hexes()
            self.assertTrue(adapter.catalog_snapshot()['stale'])
            with self.assertRaises(SourceError):adapter.hexes()
            self.assertEqual(len(calls), 1, 'Snapshot lookup must not bypass source cooldown')

    def test_legacy_repair_does_not_delete_concurrent_good_row_even_at_same_timestamp(self):
        for replacement_time in (1000.0, 1001.0):
            with self.subTest(replacement_time=replacement_time), tempfile.TemporaryDirectory() as temporary:
                calls = []
                def unexpected(request):
                    calls.append(request)
                    return httpx.Response(200, json={'success': True, 'code': 200, 'data': {'hex': []}})
                adapter = DataJ(db=Path(temporary) / 'cache.sqlite', transport=httpx.MockTransport(unexpected))
                key = self.seed(adapter.db, '/gamedata', {'hex': 'invalid'}, fetched=1000.0)
                original_connect = sqlite3.connect
                replaced = []
                def observed_connect(*args, **kwargs):
                    connection = original_connect(*args, **kwargs)
                    def before_delete(action, table, *_):
                        if action == sqlite3.SQLITE_DELETE and table == 'cache' and not replaced:
                            replaced.append(True)
                            with closing(original_connect(adapter.db, isolation_level=None)) as writer:
                                writer.execute('UPDATE cache SET fetched=?, body=? WHERE key=?',
                                    (replacement_time, '{"hex": []}', key))
                        return sqlite3.SQLITE_OK
                    connection.set_authorizer(before_delete)
                    return connection
                with patch('dataj.sqlite3.connect', side_effect=observed_connect), patch('dataj.time.time', return_value=1002.0):
                    repaired = adapter.catalog()
                self.assertEqual(replaced, [True], 'The concurrent replacement must actually occur')
                self.assertEqual(repaired['data'], {'hex': []})
                self.assertTrue(repaired['cached'])
                self.assertEqual(calls, [], 'The newer good row must survive exact invalidation')

    def test_shared_stricter_consumer_rejects_owner_data_before_it_can_persist_as_usable(self):
        with tempfile.TemporaryDirectory() as temporary:
            entered, release, joining_read = (threading.Event() for _ in range(3))
            calls = []
            incomplete = {'comps': [{'compId': '107', 'name': '测试阵容',
                                    'heroes': None, 'traits': None, 'sampleCount': 13}]}
            complete = {'comps': [{'compId': '107', 'name': '测试阵容',
                                  'heroes': [], 'traits': [], 'sampleCount': 13, 'avgPlacement': 4.2}]}
            def respond(request):
                calls.append(request)
                if len(calls) == 1:
                    entered.set()
                    self.assertTrue(release.wait(2))
                return httpx.Response(200, json={'success': True, 'code': 200,
                    'data': incomplete if len(calls) == 1 else complete})
            transport = httpx.MockTransport(respond)
            adapter = DataJ(patch='18.4', db=Path(temporary) / 'cache.sqlite', transport=transport)
            entity = {'id': '1023', 'name': '应急护甲 I'}
            body = {'version': '18.4', 'setId': 18, 'filter': {'combinator': 'and', 'rules': [{
                'starCount': '', 'type': 'hex', 'targetId': '1023', 'enable': True,
                'targetName': '应急护甲 I', 'hexRound': '1', 'nameMatch': False,
                'equipCarry': '', 'equipCount': '', 'exclude': False}]}}
            original_connect = sqlite3.connect
            def observed_connect(*args, **kwargs):
                connection = original_connect(*args, **kwargs)
                def trace(statement):
                    if statement.startswith('SELECT fetched, body FROM cache'):
                        joining_read.set()
                connection.set_trace_callback(trace)
                return connection
            with ThreadPoolExecutor(max_workers=2) as pool:
                owner = pool.submit(adapter.request, '/explorer/query', body=body)
                try:
                    self.assertTrue(entered.wait(1))
                    with patch('dataj.sqlite3.connect', side_effect=observed_connect):
                        waiter = pool.submit(adapter.explore, 'hex', entity,
                                             hex_stage='3-2', required_comp='107')
                        self.assertTrue(joining_read.wait(1))
                        release.set()
                        self.assertFalse(owner.result(timeout=2)['cached'])
                        with self.assertRaises(SourceError):waiter.result(timeout=2)
                finally:release.set()
            self.assertEqual(len(calls), 1, 'A stricter joiner must reuse issued HTTP')
            restarted = DataJ(patch='18.4', db=adapter.db, transport=transport)
            repaired = restarted.explore('hex', entity, hex_stage='3-2', required_comp='107')
            self.assertEqual(repaired['data'], complete)
            self.assertFalse(repaired['cached'])
            self.assertEqual(len(calls), 2)

    def test_repair_preserves_other_hero_sample_patch_and_stage_cache_keys(self):
        query = {'setId': 18, 'gameVersion': '18.4'}
        def rule_body(stage):
            return {'version': '18.4', 'setId': 18, 'filter': {'combinator': 'and', 'rules': [{
                'starCount': '', 'type': 'hex', 'targetId': '1023', 'enable': True,
                'targetName': '应急护甲 I', 'hexRound': stage, 'nameMatch': False,
                'equipCarry': '', 'equipCount': '', 'exclude': False}]}}
        cases = [
            ('hero', '/comp/107/hero-equips', {**query, 'heroId': '4503'}, None,
             {**query, 'heroId': '4504'}, None,
             {'compId': '107', 'heroId': '4504', 'heroEquips': [], 'hero3Equips': []},
             {'compId': '107', 'heroId': '4503', 'heroEquips': [], 'hero3Equips': []},
             lambda a: a.equipment('107', '4503'), lambda a: a.equipment('107', '4504')),
            ('minimum', '/comp/rank', {**query, 'minSample': 100}, None,
             {**query, 'minSample': 50}, None, [], [], lambda a: a.comps(100), lambda a: a.comps(50)),
            ('patch', '/stats/hex', query, None,
             {**query, 'gameVersion': '18.3'}, None, [], [], lambda a: a.hexes(),
             lambda a: DataJ(patch='18.3', db=a.db, transport=a.transport).hexes()),
            ('stage', '/explorer/query', query, rule_body('1'), query, rule_body('2'),
             {'comps': []}, {'comps': []},
             lambda a: a.explore('hex', {'id': '1023', 'name': '应急护甲 I'}, hex_stage='3-2'),
             lambda a: a.explore('hex', {'id': '1023', 'name': '应急护甲 I'}, hex_stage='4-2')),
        ]
        for name, path, broken_query, broken_body, good_query, good_body, retained, fetched, repair, read_good in cases:
            with self.subTest(identity=name), tempfile.TemporaryDirectory() as temporary:
                calls = []
                def respond(request):
                    calls.append(request)
                    return httpx.Response(200, json={'success': True, 'code': 200, 'data': fetched})
                adapter = DataJ(patch='18.4', db=Path(temporary) / 'cache.sqlite',
                                transport=httpx.MockTransport(respond))
                self.seed(adapter.db, path, {'invalid': 'legacy'}, params=broken_query, body=broken_body)
                self.seed(adapter.db, path, retained, params=good_query, body=good_body)
                self.assertFalse(repair(adapter)['cached'])
                self.assertTrue(read_good(adapter)['cached'])
                self.assertEqual(len(calls), 1, 'Repair must invalidate only the rejected request identity')

    def test_bad_legacy_cache_cannot_bypass_an_existing_source_cooldown(self):
        with tempfile.TemporaryDirectory() as temporary:
            calls = []
            def unavailable(request):
                calls.append(request)
                return httpx.Response(503)
            adapter = DataJ(db=Path(temporary) / 'cache.sqlite', transport=httpx.MockTransport(unavailable))
            with self.assertRaises(SourceError):adapter.hexes()
            self.seed(adapter.db, '/gamedata', {'hex': 'invalid'})
            with self.assertRaises(SourceError) as failure:adapter.catalog()
            self.assertEqual(failure.exception.reason, 'source_cooldown')
            self.assertEqual(len(calls), 1)
            self.assertIsNone(adapter.catalog_snapshot())

    def test_malformed_catalog_rows_cannot_replace_a_consumable_directory(self):
        hex_row = {'id': '1023', 'name': '应急护甲 I', 'setId': '18', 'descText': '独立目录条目'}
        good = {'hex': [hex_row], 'hero': [{'id': '4503', 'name': '阿木木', 'picture': 'https://img.dataj.cc/hero.png'}]}
        malformed = [{'hex': [None]}, {'hex': [{}]}, {'hex': [{'id': '1023'}]},
                     {'hex': [{**hex_row, 'id': True}]}, {'hex': [{**hex_row, 'name': ' \t'}]},
                     {'hex': [{**hex_row, 'setId': '19'}]}, {'hex': [hex_row], 'setId': 19},
                     {'hex': [{**hex_row, 'icon': []}]}, {'hex': [{**hex_row, 'descText': None}]},
                     {'hex': [{**hex_row, 'descText': 42}]}]
        malformed.extend({'hex': [{**hex_row, 'setId': value}]}
                         for value in (None, 18.0, True, ' 18', '18\n'))
        malformed.extend({'hex': [{**hex_row, 'id': value}]}
                         for value in ('', '0', '01', '1\n', '１', '١', '²', 0, 1.0))
        for category in ('hero', 'trait', 'equip'):
            malformed.extend([{'hex': [hex_row], category: {}},
                              {'hex': [hex_row], category: [None]},
                              {'hex': [hex_row], category: [{'id': '1', 'name': '条目', 'picture': {}}]},
                              {'hex': [hex_row], category: [{'id': '1', 'name': '条目', 'descText': []}]}])
        for index, invalid in enumerate(malformed):
            with self.subTest(case=index), tempfile.TemporaryDirectory() as temporary:
                calls = []
                def respond(request):
                    calls.append(request)
                    return httpx.Response(200, json={'success': True, 'code': 200,
                        'data': good if len(calls) == 1 else invalid})
                adapter = DataJ(db=Path(temporary) / 'cache.sqlite', transport=httpx.MockTransport(respond))
                original = adapter.catalog()
                adapter.next_request = 0
                with patch('dataj.time.time', return_value=original['fetched_at'] + 4000):
                    with self.assertRaises(SourceError):adapter.catalog()
                    self.assertEqual(adapter.catalog_snapshot()['data'], good)
                    self.assertEqual(len(calls), 2)

    def test_catalog_accepts_known_nullable_optional_text_and_unknown_fields(self):
        good = {'hex': [{'id': '1023', 'name': '应急护甲 I', 'descText': '说明', 'futureField': {'a': True}}],
                'hero': [{'id': '4503', 'name': '阿木木', 'skillDesc': None, 'skillName': None, 'tag': None}],
                'trait': [{'id': '12', 'name': '羁绊', 'realDesc': None}],
                'equip': [{'id': '2004', 'name': '装备', 'descText': None, 'basicDesc': None}]}
        with tempfile.TemporaryDirectory() as temporary:
            adapter = DataJ(db=Path(temporary) / 'cache.sqlite', transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={'success': True, 'code': 200, 'data': good})))
            self.assertEqual(adapter.catalog()['data'], good)
            self.assertEqual(adapter.catalog_snapshot()['data'], good)

    def test_network_repair_rechecks_a_concurrent_good_row_after_bad_decode(self):
        for replacement_time in (1000.0, 1001.0):
            with self.subTest(replacement_time=replacement_time), tempfile.TemporaryDirectory() as temporary:
                calls = []
                def unexpected(request):
                    calls.append(request)
                    self.fail('The concurrent good row must avoid HTTP')
                adapter = DataJ(db=Path(temporary) / 'cache.sqlite', transport=httpx.MockTransport(unexpected))
                key = self.seed(adapter.db, '/gamedata', {'hex': 'invalid'}, fetched=1000.0)
                original_loads = json.loads
                replaced = []
                good = {'hex': [{'id': '1023', 'name': '应急护甲 I'}]}
                def after_decode(serialized, *args, **kwargs):
                    data = original_loads(serialized, *args, **kwargs)
                    if data == {'hex': 'invalid'} and not replaced:
                        replaced.append(True)
                        with closing(sqlite3.connect(adapter.db, isolation_level=None)) as writer:
                            writer.execute('UPDATE cache SET fetched=?, body=? WHERE key=?',
                                (replacement_time, json.dumps(good, ensure_ascii=False), key))
                    return data
                with patch('dataj.json.loads', side_effect=after_decode), patch('dataj.time.time', return_value=1002.0):
                    repaired = adapter.catalog()
                self.assertEqual(replaced, [True], 'A good row must replace the decoded bad observation')
                self.assertEqual(repaired['data'], good)
                self.assertTrue(repaired['cached'])
                self.assertEqual(calls, [])

    def test_network_bad_json_recovers_after_failed_source_and_restart(self):
        with tempfile.TemporaryDirectory() as temporary:
            calls = []
            def respond(request):
                calls.append(request)
                if len(calls) == 1:return httpx.Response(503)
                return httpx.Response(200, json={'success': True, 'code': 200, 'data': {'hex': []}})
            transport = httpx.MockTransport(respond)
            adapter = DataJ(db=Path(temporary) / 'cache.sqlite', transport=transport)
            self.seed(adapter.db, '/gamedata', None, serialized='{broken')
            with self.assertRaises(SourceError):adapter.catalog()
            with self.assertRaises(SourceError):adapter.catalog()
            self.assertEqual(len(calls), 1, 'Bad JSON must not bypass an active source cooldown')
            restarted = DataJ(db=adapter.db, transport=transport)
            repaired = restarted.catalog()
            self.assertEqual(repaired['data'], {'hex': []})
            self.assertFalse(repaired['cached'])
            self.assertTrue(restarted.catalog()['cached'])
            self.assertEqual(len(calls), 2)


if __name__ == '__main__':
    unittest.main()
