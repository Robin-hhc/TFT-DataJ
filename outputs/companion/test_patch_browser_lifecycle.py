"""Version control must retire visible ranks before the new catalog returns."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import httpx
from PySide6.QtWidgets import QLabel
from app import QApplication
import test_game_resource_inputs as fixtures


OLD_COMP = {'compId': '112', 'name': '旧版阵容', 'sampleCount': 200,
            'avgPlacement': 2.22, 'top4Rate': 70.0, 'topRate': 20.0,
            'heroes': [], 'traits': []}
NEW_COMP = {**OLD_COMP, 'name': '新版阵容', 'avgPlacement': 4.44}


class PatchBrowserLifecycleTests(unittest.TestCase):
    flush = fixtures.GameResourceInputTests.flush
    tearDown = fixtures.GameResourceInputTests.tearDown

    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        self.fail_catalog = False
        with patch('app.win.enumerate_mumu', return_value=[]):
            fixtures.GameResourceInputTests.setUp(self)
        self.stack.enter_context(patch('app.Vision.prepare'))
        self.p.versions_loaded(['18.3', '18.2a'])
        self.p.browser.set_filter('hex', fixtures.CATALOG['hex'][0], can_confirm=True)
        self.flush()
        self.p.browser.input_bar.confirm.click()
        self.p.browser.cards[0].choose.click()
        self.flush()
        self.p.tabs.setCurrentIndex(1)
        self.p.show()
        self.qt.processEvents()
        self.assertEqual(len(self.p.browser.cards), 1)
        self.assertTrue(self.p.browser.cards[0].isVisible())
        self.assertIn('2.22', self.visible_labels())
        self.scope = self.p.browser.scope
        self.history = self.p.selected_resources.events
        self.session_id = self.p.session.session_id

    def response(self, request):
        self.calls.append(request)
        path = request.url.path
        if path.endswith('/gamedata'):
            if self.fail_catalog:
                raise httpx.ConnectError('controlled catalog failure', request=request)
            data = deepcopy(fixtures.CATALOG)
        elif path.endswith('/explorer/query'):
            version = json.loads(request.content)['version']
            data = {'comps': [deepcopy(OLD_COMP if version == '18.2a' else NEW_COMP)]}
        elif path.endswith('/112'):
            data = {**deepcopy(NEW_COMP), 'gameCode': '【阵容码】112'}
        else:
            data = []
        return httpx.Response(200, json={'success': True, 'code': 200, 'data': data})

    def visible_labels(self):
        return [label.text() for label in self.p.browser.findChildren(QLabel) if label.isVisible()]

    def change_version(self):
        self.p.patch.setCurrentText('18.3')
        self.p.patch.activated.emit(self.p.patch.currentIndex())
        self.qt.processEvents()

    def assert_context_preserved(self):
        self.assertEqual(self.p.browser.scope, self.scope)
        self.assertEqual(self.p.selected_resources.events, self.history)
        self.assertEqual(self.p.session.session_id, self.session_id)
        self.assertEqual(self.p.session.target, '112')

    def assert_no_old_cards(self):
        self.assertEqual(self.p.browser.cards, [], 'Old-version cards remain after version activation')
        self.assertNotIn('2.22', self.visible_labels())
        self.assert_context_preserved()

    def hold_old_browser_result(self):
        self.p.browser.retry()
        function, done, _ = self.pending.pop(0)
        return function(), done

    def test_new_catalog_loading_and_failure_remove_previous_version_cards(self):
        self.change_version()
        self.assert_no_old_cards()
        self.fail_catalog = True
        self.flush()
        self.qt.processEvents()
        self.assert_no_old_cards()

    def test_late_old_result_after_catalog_failure_cannot_restore_old_cards(self):
        result, old_done = self.hold_old_browser_result()
        self.change_version()
        self.fail_catalog = True
        self.flush()
        old_done(result)
        self.qt.processEvents()
        self.assert_no_old_cards()

    def test_success_renders_only_new_ranks_and_ignores_late_old_result(self):
        result, old_done = self.hold_old_browser_result()
        self.change_version()
        self.assert_no_old_cards()
        self.flush()
        old_done(result)
        self.p.tabs.setCurrentIndex(1)
        self.qt.processEvents()
        self.assert_context_preserved()
        self.assertEqual(len(self.p.browser.cards), 1)
        self.assertIn('4.44', self.visible_labels())
        self.assertNotIn('2.22', self.visible_labels())
        self.assertEqual(self.p.comp_detail['compId'], '112')
        self.assertTrue(self.p.copy_button.isEnabled())
        bodies = [json.loads(request.content) for request in self.calls if request.method == 'POST']
        self.assertEqual(bodies[-1]['version'], '18.3')
        self.assertEqual(bodies[-1]['filter']['rules'][0]['targetId'], '20778')


if __name__ == '__main__':
    unittest.main()
