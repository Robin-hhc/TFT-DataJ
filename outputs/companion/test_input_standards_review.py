"""Review evidence for real job ownership and interleaved capture flags."""
import gc
from types import SimpleNamespace
import time
import unittest
from unittest.mock import patch
import weakref

from PIL import Image
from app import QApplication, Companion
import test_game_resource_inputs as fixtures

REAL_SUBMIT = Companion.submit


class InputStandardsReviewTests(unittest.TestCase):
    response = fixtures.GameResourceInputTests.response
    flush = fixtures.GameResourceInputTests.flush
    tearDown = fixtures.GameResourceInputTests.tearDown

    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        with patch('app.win.enumerate_mumu', return_value=[]):
            fixtures.GameResourceInputTests.setUp(self)
        self.flush()
        self.binding = SimpleNamespace(hwnd=77, pid=3, process='MuMuNxDevice.exe',
                                       rect=(0, 0, 3840, 2160), dpi=96)
        self.p.binding = self.binding
        self.stack.enter_context(patch('condition_controller.win.describe', return_value=self.binding))
        self.stack.enter_context(patch('condition_controller.win.foreground_root', return_value=77))
        self.stack.enter_context(patch('condition_controller.win.same_target', return_value=True))
        self.stack.enter_context(patch('condition_controller.QTimer.singleShot', new=lambda _, fn: fn()))
        self.stack.enter_context(patch.object(self.p, 'panel_open', return_value=False))
        self.references = []

        def capture(_):
            image = Image.new('RGB', (3840, 2160))
            self.references.append(weakref.ref(image))
            return image, self.binding

        self.stack.enter_context(patch('condition_controller.capture_image', side_effect=capture))

    def check_real_condition_job_release(self, fail):
        completed = []

        def read(image):
            completed.append(image.size)
            if fail:
                raise RuntimeError('review synthetic OCR failure')
            return {'route': 'unknown', 'status': 'unknown'}

        # No mock records image call arguments, and no caller owns the image.
        self.p.conditions.reader = SimpleNamespace(read=read)
        self.stack.enter_context(patch.object(self.p, 'submit', REAL_SUBMIT.__get__(self.p)))
        gc_enabled = gc.isenabled()
        gc.disable()
        try:
            self.p.conditions.trigger()
            deadline = time.monotonic() + 4
            while self.p.jobs and time.monotonic() < deadline:
                self.qt.processEvents()
                time.sleep(.001)
            self.p.capture_pool.waitForDone()
            self.p.ocr_pool.waitForDone()
            self.qt.processEvents()
            self.assertEqual(completed, [(3840, 2160)])
            self.assertFalse(self.p.jobs)
            self.assertFalse(self.p.capture_pending)
            self.assertFalse(self.p.ocr_busy)
            self.assertEqual(len(self.references), 1)
            self.assertIsNone(self.references[0](), 'Condition capture closure retains 4K PIL image without cyclic GC')
        finally:
            if gc_enabled:
                gc.enable()

    def test_real_completed_condition_job_releases_4k_frame(self):
        self.check_real_condition_job_release(False)

    def test_real_failed_condition_job_releases_4k_frame(self):
        self.check_real_condition_job_release(True)

    def test_condition_ocr_failure_preserves_background_capture_ownership(self):
        def fail_read(_):
            raise RuntimeError('review synthetic OCR failure')

        self.p.conditions.reader = SimpleNamespace(read=fail_read)
        self.p.conditions.trigger()
        capture, captured, _ = self.pending.pop(0)
        captured(capture())
        self.assertTrue(self.p.ocr_busy)
        self.assertFalse(self.p.capture_pending)
        # The live timer can request a new frame while OCR is in flight.
        self.p.request_capture()
        self.assertTrue(self.p.capture_pending)
        self.assertEqual(len(self.pending), 2)
        read, _, failed = self.pending.pop(0)
        try:
            read()
        except RuntimeError as exc:
            failed(str(exc))
        self.assertFalse(self.p.ocr_busy)
        self.assertTrue(self.p.capture_pending,
                        'A failed condition OCR job cleared another pending capture job\'s busy flag')


if __name__ == '__main__':
    unittest.main()
