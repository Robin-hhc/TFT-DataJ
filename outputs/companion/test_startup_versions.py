"""Startup version selection through real Qt callbacks and HTTP requests."""
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

import httpx
from app import QApplication, Companion
from core import resolve_name
from dataj import DataJ


HEX_FIXTURE = json.loads((Path(__file__).parent / 'fixtures/hex-identity-20261007.json').read_text(encoding='utf-8'))


class StartupVersions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.stack = ExitStack()
        self.pending = []
        self.calls = []
        self.versions = ['18.3', '18.2a', '18.1.c']
        self.failure = None
        self.catalog = {'hex': [], 'hero': [], 'trait': [], 'equip': []}
        self.statistics = {}
        self.statistics_failures = {}
        for module in ['app', 'dataj', 'comp_browser']:
            self.stack.enter_context(patch(module + '.STATE_DIR', Path(self.tmp.name)))
        transport = httpx.MockTransport(self.response)
        db = Path(self.tmp.name) / 'cache.db'

        class Source(DataJ):
            def __init__(self, patch='18.2a'):
                super().__init__(patch=patch, db=db, transport=transport)

            def request(self, *args, **kwargs):
                self.next_request = 0
                return super().request(*args, **kwargs)

        self.stack.enter_context(patch('app.DataJ', Source))
        self.stack.enter_context(patch('app.Vision.prepare'))
        self.stack.enter_context(patch('app.win.enumerate_mumu', return_value=[]))
        self.stack.enter_context(patch.object(Companion, 'submit',
            lambda panel, pool, fn, done, failed=lambda _: None:
                self.pending.append((fn, done, failed))))
        self.p = Companion()
        self.p.timer.stop()

    def tearDown(self):
        self.p.shutdown()
        self.p.deleteLater()
        self.qt.processEvents()
        self.stack.close()
        self.tmp.cleanup()

    def response(self, request):
        self.calls.append(request)
        if request.url.path == '/comp':
            if self.failure == 'network':
                raise httpx.ConnectError('offline', request=request)
            if self.failure == 'malformed':
                return httpx.Response(200, text='<html>changed</html>')
            rows = [{'setId': 18, 'gameVersion': v} for v in self.versions]
            chunk = json.dumps({'gameVersions': rows}, separators=(',', ':'))
            return httpx.Response(200, text='self.__next_f.push([1,' + json.dumps(chunk) + '])')
        if request.url.path.endswith('/gamedata'):
            data = self.catalog
        elif request.url.path.endswith('/stats/hex'):
            version = request.url.params['gameVersion']
            failure = self.statistics_failures.get(version)
            if failure == 'network':
                raise httpx.ConnectError('hex statistics offline', request=request)
            data = {} if failure == 'malformed' else self.statistics.get(version, [])
        else:
            data = []
        return httpx.Response(200, json={'success': True, 'code': 200, 'data': data})

    def prepare_completion(self, index=0):
        """Run real requests now, retaining their Qt callback for a later race."""
        fn, done, failed = self.pending.pop(index)
        try:
            result = fn()
        except Exception as exc:
            return failed, str(exc)
        return done, result

    def complete(self, index=0):
        callback, result = self.prepare_completion(index)
        callback(result)

    def flush(self):
        for _ in range(20):
            if not self.pending:
                return
            self.complete()
        self.fail('startup did not settle')

    def version_calls(self):
        return [r for r in self.calls if r.url.path == '/comp']

    def use_hex_fixture(self):
        self.catalog['hex'] = deepcopy(HEX_FIXTURE['catalog'])
        self.statistics[HEX_FIXTURE['patch']] = deepcopy(HEX_FIXTURE['statistics'])

    def observe_titles(self, titles, stage):
        cards = [{'slot': slot, 'raw_text': title,
                  'resolution': {**resolve_name([title] * 3, self.p.catalog['hex']),
                                 'readings': [title] * 3}}
                 for slot, title in enumerate(titles)]
        self.p.observed({'scene': 'choice_candidates', 'round': stage,
                         'cards': cards, 'elapsed_ms': 1}, False)
        self.flush()

    def choice_rows(self):
        table = self.p.choice_table
        return [[table.item(row, col).text() for col in range(table.columnCount())]
                for row in range(table.rowCount())]

    def assert_duplicate_hex_titles_retained(self):
        for title, ids in [('别再错过', {'1625', '10784'}),
                           ('自然庇护所', {'20768', '30768'})]:
            rows = [row for row in self.p.catalog['hex'] if row['name'] == title]
            self.assertEqual({str(row['id']) for row in rows}, ids)
            self.assertTrue(all('catalog_alias_ids' not in row for row in rows))
            self.assertEqual(resolve_name([title] * 3, self.p.catalog['hex'])['status'], 'ambiguous')
            self.assertFalse(self.p.browser.resolver.resolve_selection('hex', rows[0]).confirmed)

    def test_waits_for_versions_before_catalog_statistics_or_game_capture(self):
        self.assertEqual([fn.__name__ for fn, _, _ in self.pending], ['versions'])
        self.assertFalse(self.p.patch.isEnabled())
        self.assertNotEqual(self.p.patch.currentText(), '18.2a')
        self.p.load_catalog()
        self.p.browser.retry()
        self.p.new_game()
        self.p.comp_url.setText('https://www.dataj.cc/comp/112')
        self.p.pin_comp()
        self.p.query_stats(['1023'] * 3, ['test'] * 3, False)
        self.p.capture_once()
        self.p.tick()
        self.assertEqual(len(self.pending), 1)
        self.assertEqual(self.calls, [])
        self.assertIsNone(self.p.session.target)

    def test_latest_is_used_for_first_statistics_and_all_prewarming(self):
        self.complete()
        self.assertEqual((self.p.patch.currentText(), self.p.adapter.patch, self.p.session.patch), ('18.3',) * 3)
        self.assertEqual([self.p.patch.itemText(i) for i in range(self.p.patch.count())], self.versions)
        self.assertEqual([r.url.path for r in self.calls], ['/comp'])
        self.flush()
        stats = [r for r in self.calls if r.url.path.startswith('/api/web/') and not r.url.path.endswith('/gamedata')]
        self.assertTrue(stats)
        self.assertTrue(all(r.url.params['gameVersion'] == '18.3' for r in stats))
        self.assertTrue(self.p.patch.isEnabled())
        self.assertTrue(self.p.version_retry.isHidden())

    def test_uses_site_order_instead_of_sorting_version_strings(self):
        self.versions = ['18.10', '18.9', '18.2a']
        self.flush()
        self.assertEqual(self.p.patch.currentText(), '18.10')

    def test_manual_historical_version_and_runtime_do_not_refetch_list(self):
        self.flush()
        self.p.patch.setCurrentText('18.1.c')
        self.p.patch.activated.emit(self.p.patch.currentIndex())
        self.flush()
        self.assertEqual((self.p.adapter.patch, self.p.session.patch), ('18.1.c',) * 2)
        self.assertEqual(self.p.latest_patch, '18.3')
        self.p.load_versions()
        self.p.browser.retry()
        for _ in range(5):
            self.p.tick()
        self.flush()
        self.assertEqual(len(self.version_calls()), 1)
        self.assertEqual(self.p.patch.currentText(), '18.1.c')

    def test_current_catalog_projects_real_aliases_through_observed_to_statistics(self):
        self.use_hex_fixture()
        self.flush()
        for title, identity, stage, expected_stat, companion in [
                ('别再错过', '1625', '3-2', '4.27 · 3573局', '并肩作战 I'),
                ('自然庇护所', '20768', '2-1', '4.29 · 877局', '拥抱 I')]:
            with self.subTest(title=title):
                rows = [row for row in self.p.catalog['hex'] if row['name'] == title]
                self.assertEqual(len(rows), 1)
                self.assertEqual(str(rows[0]['id']), identity)
                self.assertEqual(self.p.browser.resolver.resolve_selection('hex', rows[0]).entity['id'], identity)
                self.observe_titles([title, '成吨的属性！', companion], stage)
                rendered = self.choice_rows()
                self.assertEqual(rendered[0][:2], [title, expected_stat])
                self.assertNotIn('待确认', rendered[0][0])
                self.assertEqual(self.p.picks[0].currentData(), identity)
                self.assertEqual(self.p.session.choices[0], identity)
                self.assertIsNone(self.p.session.choices[1])
                self.assertEqual(rendered[1][0], '成吨的属性！（品质待确认）')
        global_calls = [r for r in self.calls if r.url.path.endswith('/stats/hex')]
        self.assertEqual(len(global_calls), 1)
        self.assertEqual(global_calls[0].url.params['gameVersion'], '18.3')

    def test_historical_patch_without_statistics_retains_real_duplicate_titles(self):
        self.use_hex_fixture()
        self.flush()
        self.p.patch.setCurrentText('18.1.c')
        self.p.patch.activated.emit(self.p.patch.currentIndex())
        self.flush()
        self.assertEqual(self.p.adapter.patch, '18.1.c')
        self.assert_duplicate_hex_titles_retained()
        self.observe_titles(['别再错过', '自然庇护所', '拥抱 I'], '2-1')
        self.assertEqual(self.p.session.choices[:2], (None, None))
        self.assertEqual([row[0] for row in self.choice_rows()[:2]],
                         ['别再错过（身份待确认）', '自然庇护所（身份待确认）'])
        global_versions = [r.url.params['gameVersion'] for r in self.calls
                           if r.url.path.endswith('/stats/hex')]
        self.assertEqual(global_versions, ['18.3', '18.1.c'])

    def test_old_adapter_catalog_completion_cannot_replace_historical_catalog(self):
        self.use_hex_fixture()
        self.complete()  # version list schedules the latest catalog request
        previous_adapter = self.p.adapter
        late_callback, late_result = self.prepare_completion()
        self.p.patch.setCurrentText('18.1.c')
        self.p.patch.activated.emit(self.p.patch.currentIndex())
        self.flush()
        self.assertIsNot(self.p.adapter, previous_adapter)
        self.assert_duplicate_hex_titles_retained()
        current_resolver = self.p.browser.resolver
        current_revision = self.p.session.revision
        late_callback(late_result)
        self.assert_duplicate_hex_titles_retained()
        self.assertIs(self.p.browser.resolver, current_resolver)
        self.assertEqual(self.p.session.revision, current_revision)
        self.assertEqual(self.pending, [])

    def test_same_adapter_previous_catalog_generation_cannot_clear_results(self):
        self.use_hex_fixture()
        self.complete()
        adapter = self.p.adapter
        late_callback, late_result = self.prepare_completion()
        self.p.load_catalog()
        self.flush()
        self.assertIs(self.p.adapter, adapter)
        self.observe_titles(['别再错过', '成吨的属性！', '并肩作战 I'], '3-2')
        self.assertEqual(self.choice_rows()[0][:2], ['别再错过', '4.27 · 3573局'])
        current_rows = self.choice_rows()
        current_payload = self.p.stats_payload
        current_resolver = self.p.browser.resolver
        current_revision = self.p.session.revision
        late_callback(late_result)
        self.assertEqual(self.choice_rows(), current_rows)
        self.assertIs(self.p.stats_payload, current_payload)
        self.assertIs(self.p.browser.resolver, current_resolver)
        self.assertEqual(self.p.session.revision, current_revision)
        self.assertEqual(self.pending, [])

    def test_failed_hex_statistics_leave_real_aliases_unconfirmed(self):
        self.use_hex_fixture()
        for failure in ('network', 'malformed'):
            with self.subTest(failure=failure):
                self.statistics_failures['18.3'] = failure
                if failure == 'network':
                    self.flush()
                else:
                    self.p.load_catalog()
                    self.flush()
                self.assertTrue(self.p.versions_ready)
                self.assertTrue(self.p.start_button.isEnabled())
                self.assert_duplicate_hex_titles_retained()
                self.observe_titles(['别再错过', '自然庇护所', '拥抱 I'], '2-1')
                self.assertEqual(self.p.session.choices, (None, None, '10615'))
                self.assertEqual([pick.currentData() for pick in self.p.picks[:2]], [None, None])
                self.assertEqual(self.choice_rows(), [])
                self.assertIsNone(self.p.stats_payload)

    def assert_failed_then_retry(self):
        self.complete()
        self.assertFalse(self.p.versions_ready)
        self.assertFalse(self.p.patch.isEnabled())
        self.assertFalse(self.p.version_retry.isHidden())
        self.assertIn('重试', self.p.status.text())
        self.p.load_catalog()
        self.p.browser.retry()
        self.assertEqual(self.pending, [])
        self.failure = None
        self.versions = ['18.3', '18.2a']
        self.p.version_retry.click()
        self.p.load_versions()  # duplicate clicks must not enqueue another request
        self.assertEqual(len(self.pending), 1)
        self.flush()
        self.assertTrue(self.p.versions_ready)
        self.assertEqual(self.p.patch.currentText(), '18.3')
        self.assertEqual(len(self.version_calls()), 2)

    def test_network_failure_has_explicit_retry_without_old_statistics(self):
        self.failure = 'network'
        self.assert_failed_then_retry()

    def test_empty_version_list_has_explicit_retry(self):
        self.versions = []
        self.assert_failed_then_retry()

    def test_changed_page_has_explicit_retry(self):
        self.failure = 'malformed'
        self.assert_failed_then_retry()


if __name__ == '__main__':
    unittest.main()
