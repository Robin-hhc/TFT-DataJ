"""Actual Companion workers discard queued revisions before issuing HTTP."""
import threading
import time
import unittest
from unittest.mock import patch

import httpx

from app import Companion
import test_comp_clipboard as fixture

REAL_SUBMIT = Companion.submit


class QueryArchitectureTests(unittest.TestCase):
    setUpClass = classmethod(fixture.CompClipboardTests.setUpClass.__func__)
    setUp = fixture.CompClipboardTests.setUp
    tearDown = fixture.CompClipboardTests.tearDown
    flush = fixture.CompClipboardTests.flush
    complete = fixture.CompClipboardTests.complete
    prepare_completion = fixture.CompClipboardTests.prepare_completion

    def response(self, request):
        if request.url.path.endswith('/hero-equips'):
            self.requests.append(request)
            data = {'compId': '112', 'heroId': request.url.params['heroId'],
                    'heroEquips': [{'equips': [{'id': '2004', 'name': '测试装备'}],
                                   'avgPlacement': 3.5, 'sampleCount': 50}], 'hero3Equips': []}
            return httpx.Response(200, json={'code': 200, 'success': True, 'data': data})
        return fixture.CompClipboardTests.response(self, request)

    def run_queued_revisions(self, enqueue):
        started, release = threading.Event(), threading.Event()
        with patch.object(self.p, 'submit', REAL_SUBMIT.__get__(self.p)):
            def blocker():
                started.set()
                if not release.wait(3):
                    raise RuntimeError('test did not release queue')
            self.p.submit(self.p.network, blocker, lambda _: None)
            self.assertTrue(started.wait(2))
            try:
                enqueue()
                self.assertEqual(self.requests, [], 'Queued queries ran before the worker was available')
            finally:
                release.set()
            deadline = time.monotonic() + 3
            while self.p.jobs and time.monotonic() < deadline:
                self.qt.processEvents()
                time.sleep(.001)
            self.assertFalse(self.p.jobs, 'Cancellation or completion retained a job')

    def test_rapid_pin_executes_only_latest_queued_detail_request(self):
        self.run_queued_revisions(lambda: [self.p.select_comp(comp) for comp in ('112', '113', '114')])
        self.assertEqual([request.url.path for request in self.requests], ['/api/web/comp/114'])
        self.assertEqual(self.p.comp_detail['compId'], '114')
        self.assertEqual(self.p.session.target, '114')

    def test_rapid_list_refresh_executes_only_latest_queued_source_request(self):
        def enqueue():
            for minimum in (50, 1000, 3000):
                self.p.browser.min_sample = minimum
                self.p.load_comps()
        self.run_queued_revisions(enqueue)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0].url.path, '/api/web/comp/rank')
        self.assertEqual(self.requests[0].url.params['minSample'], '3000')

    def test_versioned_catalog_queue_fetches_only_current_adapter_and_publishes(self):
        def enqueue():
            for version in ('18.2a', '18.1', '18.3'):
                self.p.adapter = type(self.p.adapter)(patch=version, budget=self.p.adapter.budget)
                self.p.load_catalog()
        with patch.object(self.p.browser, 'retry'), patch.object(self.p.items, 'prewarm'):
            self.run_queued_revisions(enqueue)
        self.assertEqual([request.url.path for request in self.requests],
                         ['/api/web/gamedata', '/api/web/stats/hex'])
        self.assertEqual(self.requests[0].url.params['setId'], '18')
        self.assertNotIn('gameVersion', self.requests[0].url.params)  # Catalog is set-wide.
        self.assertEqual(self.requests[1].url.params['gameVersion'], '18.3')
        self.assertEqual(self.p.adapter.patch, '18.3')
        self.assertEqual(self.p.catalog, fixture.CATALOG)
        self.assertTrue(self.p.start_button.isEnabled())

    def test_hero_equipment_queue_executes_only_latest_identity_and_publishes(self):
        self.p.session.set_target('112')
        self.p.heroes.blockSignals(True)
        for hero in ('4503', '4504', '4505'):
            self.p.heroes.addItem('测试英雄'+hero, hero)
        self.p.heroes.blockSignals(False)
        def enqueue():
            for hero in ('4503', '4504', '4505'):
                self.p.heroes.blockSignals(True)
                self.p.heroes.setCurrentIndex(self.p.heroes.findData(hero))
                self.p.heroes.blockSignals(False)
                self.p.query_equipment()
        self.run_queued_revisions(enqueue)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0].url.params['heroId'], '4505')
        self.assertEqual(self.p.equip_table.item(0, 0).text(), '测试装备')
        self.assertEqual(self.p.equip_table.item(0, 1).text(), '3.50')

    def test_version_change_reuses_budget_without_merging_cache_identity(self):
        budget = self.p.adapter.budget
        budget.next_request = time.monotonic() + 60
        self.p.patch.blockSignals(True)
        self.p.patch.addItem('18.3')
        self.p.patch.setCurrentText('18.3')
        self.p.patch.blockSignals(False)
        self.p.change_patch()
        self.assertIs(self.p.adapter.budget, budget)
        self.assertGreater(self.p.adapter.next_request, time.monotonic() + 55)
        self.assertEqual(self.p.adapter.patch, '18.3')


if __name__ == '__main__':
    unittest.main()
