"""The shipped EXE must exercise persistent-failure retry limits."""
import unittest
from unittest.mock import patch

import portable_check


class PortableRetryLimitsTests(unittest.TestCase):
    def test_embedded_diagnostic_stops_http_and_invalid_200_after_three_failures(self):
        self.assertTrue(hasattr(portable_check, 'check_retry_limits'),
                        'The shipped EXE needs a persistent-failure diagnostic')
        result = portable_check.check_retry_limits()
        self.assertEqual(result['status'], 'passed')
        self.assertEqual([case['fault'] for case in result['cases']], ['http_503', 'invalid_200'])
        for case in result['cases']:
            self.assertEqual(case['http_request_count'], 3)
            self.assertEqual(case['scheduled_wakes'], 2)
            self.assertTrue(case['late_callbacks_and_restarts_stopped'])
            self.assertGreaterEqual(case['minimum_retry_seconds'], 60)

    def test_diagnostic_rejects_a_runtime_that_keeps_retrying_after_three_failures(self):
        self.assertTrue(hasattr(portable_check, 'check_retry_limits'),
                        'The shipped EXE needs a persistent-failure diagnostic')
        with patch('hex_prewarm.FAILURE_LIMIT', 4):
            with self.assertRaisesRegex(AssertionError, 'continued scheduling after three failures'):
                portable_check.check_retry_limits()


if __name__ == '__main__':
    unittest.main()
