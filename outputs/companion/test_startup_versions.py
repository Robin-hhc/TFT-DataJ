"""Startup version selection through real Qt callbacks and HTTP requests."""
from contextlib import ExitStack
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

import httpx
from app import QApplication, Companion
from dataj import DataJ


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
        data = {'hex': [], 'hero': [], 'trait': [], 'equip': []} if request.url.path.endswith('/gamedata') else []
        return httpx.Response(200, json={'success': True, 'code': 200, 'data': data})

    def complete(self):
        fn, done, failed = self.pending.pop(0)
        try:
            result = fn()
        except Exception as exc:
            failed(str(exc))
        else:
            done(result)

    def flush(self):
        for _ in range(20):
            if not self.pending:
                return
            self.complete()
        self.fail('startup did not settle')

    def version_calls(self):
        return [r for r in self.calls if r.url.path == '/comp']

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
