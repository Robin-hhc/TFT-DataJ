"""Packaged diagnostic rejects broken durable-cache lifecycle implementations."""
import unittest
from unittest.mock import patch

import portable_check
from dataj import DataJ


class PortableCacheRecoveryTests(unittest.TestCase):
    def test_embedded_diagnostic_repairs_legacy_cache_and_preserves_last_good_directory(self):
        self.assertTrue(hasattr(portable_check,'check_cache_recovery'),
                        'The real EXE diagnostic needs the cache recovery check')
        result=portable_check.check_cache_recovery()
        self.assertEqual(result['status'],'passed')
        self.assertEqual(result['scope'],{'set_id':18,'patch':'18.4'})
        self.assertEqual(result['http_request_count'],2)
        self.assertTrue(result['legacy_bad_cache_repaired'])
        self.assertTrue(result['fresh_adapter_hit'])
        self.assertTrue(result['bad_refresh_rejected'])
        self.assertTrue(result['last_good_preserved'])
        self.assertTrue(result['local_fallback_stale'])
        self.assertEqual(result['snapshot_http_request_count'],0)

    def test_diagnostic_rejects_a_cache_reader_that_ignores_its_domain_contract(self):
        original=DataJ._cached_request
        def unchecked(adapter,path,key,ttl,validate=None):
            return original(adapter,path,key,ttl,validate=None)
        with patch.object(DataJ,'_cached_request',unchecked):
            with self.assertRaisesRegex(AssertionError,'Legacy bad directory was reused'):
                portable_check.check_cache_recovery()

    def test_diagnostic_rejects_writing_a_new_response_before_domain_validation(self):
        original=DataJ._send_request
        def unchecked(adapter,client,method,path,params,body,key,validate=None):
            return original(adapter,client,method,path,params,body,key,validate=None)
        with patch.object(DataJ,'_send_request',unchecked):
            with self.assertRaisesRegex(AssertionError,'malformed new HTTP 200 directory was accepted'):
                portable_check.check_cache_recovery()


if __name__=='__main__':unittest.main()
