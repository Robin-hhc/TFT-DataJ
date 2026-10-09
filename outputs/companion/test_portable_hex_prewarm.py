"""The actual EXE diagnostic must exercise its bundled pinned prewarm module."""
import unittest

import portable_check


class PortableHexPrewarmTests(unittest.TestCase):
    def test_packaged_prewarm_retains_exact_ranks_and_empty_queries_beyond_disk_ttl(self):
        check = getattr(portable_check, 'check_hex_prewarm', None)
        self.assertTrue(callable(check), 'Portable diagnostic lacks the full pinned prewarm check')
        report = check()
        self.assertEqual(report['scope'], {'set_id': 18, 'patch': '18.3', 'comp': '107', 'stage': '3-2'})
        self.assertTrue(report['retained_after_disk_expiry'])
        self.assertTrue(report['empty_result_retained'])
        self.assertEqual(report['foreground_http_count'], 0)
        self.assertEqual(report['statistics'], [
            {'hex_id': '20742', 'average': 4.23, 'samples': 13},
            {'hex_id': '30668', 'average': 4.54, 'samples': 13},
            {'hex_id': '20708', 'average': 4.75, 'samples': 8}])


if __name__ == '__main__':unittest.main()
