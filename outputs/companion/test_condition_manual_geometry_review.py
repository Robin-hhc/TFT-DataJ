"""Public manual-mode side-key flow after a real window geometry change."""
from types import SimpleNamespace
import time
import unittest

from app import QApplication
import test_condition_controller_extra as fixtures


class ManualConditionGeometryReviewTests(unittest.TestCase):
    response = fixtures.ConditionControllerExtraTests.response
    flush = fixtures.ConditionControllerExtraTests.flush
    tearDown = fixtures.ConditionControllerExtraTests.tearDown

    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        fixtures.ConditionControllerExtraTests.setUp(self)

    def test_manual_mode_rebinds_current_geometry_before_side_key_capture_token(self):
        p = self.p
        p.automatic.setChecked(False)
        self.current_binding = SimpleNamespace(**{**vars(self.binding), 'rect':(20,0,1940,1080)})
        self.capture.return_value = self.frame,self.current_binding
        # Idle timer remains active in manual mode; resource guard sees the window.
        p.tick()
        p.conditions.trigger(); self.flush()
        self.assertIsNotNone(p.browser.scope)
        self.assertEqual(p.browser.scope[1]['id'],'20778')
        self.assertEqual(p.binding.rect,self.current_binding.rect)

    def test_manual_side_key_checks_latest_geometry_even_between_throttled_guard_ticks(self):
        p=self.p
        p.automatic.setChecked(False)
        p.last_resource_guard=time.monotonic()
        self.current_binding=SimpleNamespace(**{**vars(self.binding),'rect':(20,0,1940,1080)})
        self.capture.return_value=self.frame,self.current_binding
        # Geometry changes immediately after the 3-second idle guard ran.
        p.tick()
        p.conditions.trigger();self.flush()
        self.assertIsNotNone(p.browser.scope)
        self.assertEqual(p.browser.scope[1]['id'],'20778')


if __name__=='__main__':
    unittest.main()
