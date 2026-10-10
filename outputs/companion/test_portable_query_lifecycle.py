"""Run actual portable diagnostic flows through the source Qt widgets.

Only window discovery, initial background scheduling and state paths are
isolated. Each diagnostic owns its embedded transport and scheduling doubles;
these tests do not replace the diagnosed pin/query/UI behavior.
"""
from contextlib import ExitStack
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from app import QApplication, Companion
import portable_check


class PortableQueryLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.stack = ExitStack()
        self.errors = []
        for module in ('bootstrap', 'app', 'dataj', 'comp_browser'):
            self.stack.enter_context(patch(module + '.STATE_DIR', Path(self.tmp.name)))
        self.stack.enter_context(patch('app.win.enumerate_mumu', return_value=[]))
        self.stack.enter_context(patch.object(Companion, 'submit', return_value=None))
        self.stack.enter_context(patch('sys.excepthook', side_effect=self.record_unhandled))
        self.panel = Companion(offline=True, offline_catalog={
            'hex': [], 'hero': [], 'equip': [], 'trait': []})
        self.panel.timer.stop()
        self.panel.hide()

    def record_unhandled(self, kind, value, traceback):
        self.errors.append((kind.__name__, str(value)))
        sys.__excepthook__(kind, value, traceback)

    def tearDown(self):
        try:
            self.panel.shutdown()
            self.panel.deleteLater()
            self.qt.processEvents()
        finally:
            self.stack.close()
            self.tmp.cleanup()

    def test_actual_pinned_guide_diagnostic_completes_version_and_unpin_checks(self):
        portable_check.check_pinned_guide(self.panel)
        self.assertEqual(self.errors, [], 'A real Qt pin callback raised an unhandled error')
        self.assertIsNone(self.panel.session.target)
        self.assertFalse(self.panel.copy_button.isEnabled())
        self.assertFalse(self.panel.guide_empty.isHidden())
        self.assertTrue(self.panel.guide_version.isHidden())
        self.assertTrue(self.panel.web.isHidden())
        self.assertTrue((Path(self.tmp.name) / 'portable-pinned-guide.png').is_file())

    def test_actual_resource_diagnostic_completes_queries_patch_change_and_new_game(self):
        report = portable_check.check_resource_inputs(self.panel, self.qt)
        self.assertEqual(self.errors, [], 'A real Qt query callback raised an unhandled error')
        self.assertEqual(report['network'], 'httpx.MockTransport only')
        self.assertEqual(report['canonical_hero_id'], '4503')
        self.assertEqual(report['versions'], ['18.2a', '18.3'])
        self.assertEqual(report['confirmed_events'], 5)
        self.assertEqual(report['visible_shortcuts'], 3)
        self.assertEqual(report['overflow_actions'], 2)
        self.assertEqual(report['logical_canvas'], [760, 430])
        posts = [request['body'] for request in report['request_bodies']
                 if request['method'] == 'POST']
        self.assertEqual({body['version'] for body in posts}, {'18.2a', '18.3'})
        self.assertEqual(self.panel.selected_resources.events, ())
        self.assertIsNone(self.panel.session.target)
        self.assertIsNone(self.panel.browser.scope)
        for name in report['screenshots']:
            self.assertTrue((Path(self.tmp.name) / name).is_file(), name)

    def test_diagnostic_dispatcher_cancels_stale_work_without_source_or_error(self):
        events = []

        def source():
            events.append('source')
            return 'stale response'

        portable_check._run_diagnostic_job(None, source,
            lambda result: events.append(('done', result)),
            lambda error: events.append(('failed', error)),
            is_current=lambda: False, cancelled=lambda: events.append('cancelled'))
        self.assertEqual(events, ['cancelled'])

    def test_diagnostic_dispatcher_publishes_current_result_and_exposes_source_failure(self):
        events = []
        portable_check._run_diagnostic_job(None, lambda: 'current response',
            lambda result: events.append(('done', result)),
            is_current=lambda: True, cancelled=lambda: events.append('cancelled'))
        self.assertEqual(events, [('done', 'current response')])

        def failed_source():
            raise RuntimeError('diagnostic source failure')

        with self.assertRaisesRegex(RuntimeError, 'diagnostic source failure'):
            portable_check._run_diagnostic_job(None, failed_source,
                lambda result: events.append(('unexpected done', result)),
                is_current=lambda: True)
        self.assertEqual(events, [('done', 'current response')])


if __name__ == '__main__':
    unittest.main()
