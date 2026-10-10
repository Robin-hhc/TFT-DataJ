"""Real Qt workers must discard stale source work before invoking its callable.

The pool is held by an event rather than a timing assumption. No HTTP, game,
screen capture, widget, clipboard or private sample is used by these tests.
"""
import gc
import threading
import time
import unittest
import weakref

from PySide6.QtCore import QObject, QThreadPool, Qt, Slot
from PySide6.QtWidgets import QApplication

from background_jobs import Job


class TerminalRecorder(QObject):
    def __init__(self):
        super().__init__()
        self.events = []

    @Slot(object)
    def done(self, value):
        self.events.append(('done', value, threading.get_ident()))

    @Slot(str)
    def failed(self, message):
        self.events.append(('failed', message, threading.get_ident()))

    @Slot()
    def cancelled(self):
        self.events.append(('cancelled', None, threading.get_ident()))


class Payload:
    pass


class BackgroundJobsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        self.gui_thread = threading.get_ident()
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(1)
        self.recorders = []
        self.unblock = threading.Event()

    def tearDown(self):
        self.unblock.set()
        self.assertTrue(self.pool.waitForDone(3000), 'Qt worker did not terminate')
        self.qt.processEvents()
        for recorder in self.recorders:
            recorder.deleteLater()
        self.qt.processEvents()

    def start(self, fn, *, is_current=None):
        job = Job(fn, is_current=is_current)
        recorder = TerminalRecorder()
        self.recorders.append(recorder)
        connection = Qt.ConnectionType.QueuedConnection
        job.signals.done.connect(recorder.done, connection)
        job.signals.failed.connect(recorder.failed, connection)
        job.signals.cancelled.connect(recorder.cancelled, connection)
        self.pool.start(job)
        return job, recorder

    def finish(self, recorder, count=1):
        self.assertTrue(self.pool.waitForDone(3000), 'Qt worker did not terminate')
        deadline = time.monotonic() + 1
        while len(recorder.events) < count and time.monotonic() < deadline:
            self.qt.processEvents()
            time.sleep(.001)
        self.qt.processEvents()
        self.assertEqual(len(recorder.events), count)
        self.assertTrue(all(event[2] == self.gui_thread for event in recorder.events),
                        'A terminal callback ran outside the receiving Qt thread')

    def hold_pool(self):
        entered = threading.Event()

        def occupied():
            entered.set()
            if not self.unblock.wait(3):
                raise RuntimeError('Test did not release the occupied worker')

        self.start(occupied)
        self.assertTrue(entered.wait(1), 'The worker was not occupied before enqueueing')

    def test_obsolete_queued_query_never_invokes_source_and_current_query_runs(self):
        self.hold_pool()
        revision = [0]
        calls = []
        _, old = self.start(lambda: calls.append('obsolete') or 'old response',
                            is_current=lambda: revision[0] == 0)
        revision[0] = 1
        _, current = self.start(lambda: calls.append('current') or 'new response',
                                is_current=lambda: revision[0] == 1)
        self.unblock.set()
        self.finish(old)
        self.finish(current)
        self.assertEqual(calls, ['current'], 'An obsolete queued source request still executed')
        self.assertEqual(old.events[0][:2], ('cancelled', None))
        self.assertEqual(current.events[0][:2], ('done', 'new response'))

    def test_rapid_pin_or_filter_revisions_execute_only_latest_queued_request(self):
        self.hold_pool()
        revision = [0]
        calls = []
        pending = []
        for request in range(5):
            revision[0] = request
            _, recorder = self.start(lambda request=request: calls.append(request) or request,
                                    is_current=lambda request=request: revision[0] == request)
            pending.append(recorder)
        self.unblock.set()
        for recorder in pending:
            self.finish(recorder)
        self.assertEqual(calls, [4], 'Earlier pin/filter requests reached their source callable')
        self.assertEqual([r.events[0][0] for r in pending], ['cancelled'] * 4 + ['done'])

    def test_guard_and_callable_run_on_worker_and_completion_is_queued(self):
        threads = []

        def current():
            threads.append(('guard', threading.get_ident()))
            return True

        def fetch():
            threads.append(('fetch', threading.get_ident()))
            return {'scope': 'current'}

        job, recorder = self.start(fetch, is_current=current)
        self.finish(recorder)
        self.assertEqual([kind for kind, _ in threads], ['guard', 'fetch'])
        self.assertEqual(threads[0][1], threads[1][1])
        self.assertNotEqual(threads[0][1], self.gui_thread)
        self.assertEqual(recorder.events[0][:2], ('done', {'scope': 'current'}))
        self.assertIsNone(job.fn)
        self.assertIsNone(job.is_current)

    def test_unguarded_job_keeps_existing_success_contract(self):
        job, recorder = self.start(lambda: 'unchanged caller')
        self.finish(recorder)
        self.assertEqual(recorder.events[0][:2], ('done', 'unchanged caller'))
        self.assertIsNone(job.fn)

    def test_guard_failure_is_reported_without_invoking_source(self):
        calls = []

        def failed_guard():
            raise ValueError('invalid currentness predicate')

        job, recorder = self.start(lambda: calls.append('source'), is_current=failed_guard)
        self.finish(recorder)
        self.assertEqual(calls, [])
        self.assertEqual(recorder.events[0][:2], ('failed', 'invalid currentness predicate'))
        self.assertIsNone(job.fn)
        self.assertIsNone(job.is_current)

    def test_callable_failure_has_one_queued_error_and_releases_references(self):
        def failed_fetch():
            raise RuntimeError('controlled source failure')

        job, recorder = self.start(failed_fetch, is_current=lambda: True)
        self.finish(recorder)
        self.assertEqual(recorder.events[0][:2], ('failed', 'controlled source failure'))
        self.assertIsNone(job.fn)
        self.assertIsNone(job.is_current)

    def test_cancelled_job_releases_callable_and_predicate_payload_without_gc(self):
        self.hold_pool()
        payload = Payload()
        reference = weakref.ref(payload)

        def fetch(frame=payload):
            raise AssertionError('Cancelled source callable executed')

        def current(frame=payload):
            return False

        gc_enabled = gc.isenabled()
        gc.disable()
        try:
            job, recorder = self.start(fetch, is_current=current)
            del payload, fetch, current
            self.assertIsNotNone(reference())
            self.unblock.set()
            self.finish(recorder)
            self.assertEqual(recorder.events[0][:2], ('cancelled', None))
            self.assertIsNone(job.fn)
            self.assertIsNone(job.is_current)
            self.assertIsNone(reference(), 'Cancelled worker retained its captured payload')
        finally:
            if gc_enabled:
                gc.enable()

    def test_currentness_change_does_not_hard_cancel_already_running_callable(self):
        entered = threading.Event()
        revision = [0]

        def fetch():
            entered.set()
            if not self.unblock.wait(3):
                raise RuntimeError('Test did not release the running source')
            return 'completed in-flight response'

        _, recorder = self.start(fetch, is_current=lambda: revision[0] == 0)
        self.assertTrue(entered.wait(1), 'Source did not begin before invalidation')
        revision[0] = 1
        self.unblock.set()
        self.finish(recorder)
        self.assertEqual(recorder.events[0][:2], ('done', 'completed in-flight response'))


if __name__ == '__main__':
    unittest.main()
