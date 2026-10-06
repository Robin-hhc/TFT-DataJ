"""Reject a frozen reference that silently loses real requests or UI cases."""
import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_display_replay as replay


class DisplayMatrixIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture=json.loads(gzip.decompress(replay.FIXTURE.read_bytes()))

    def assert_removed_request_rejected(self,predicate):
        data=copy.deepcopy(self.fixture)
        removed=next(r['request'] for r in data['records'] if predicate(r['request']))
        data['records']=[r for r in data['records'] if r['request']!=removed]
        data['matrix']['requests']=[r for r in data['matrix']['requests'] if r!=removed]
        # This mutation retains every metadata dimension and would satisfy the
        # old >=150 requests/present-records check. It only loses real coverage.
        self.assertEqual(len(data['matrix']['requests']),157)
        self.assertEqual(data['matrix']['conditions'],self.fixture['matrix']['conditions'])
        self.assertFalse(data['gaps'])
        with tempfile.TemporaryDirectory() as tmp:
            fixture=Path(tmp)/'reduced-matrix.json.gz'
            fixture.write_bytes(gzip.compress(json.dumps(data,ensure_ascii=False).encode(),mtime=0))
            case=replay.RealDisplayReplay('test_required_public_matrix_is_complete')
            with patch.object(replay,'FIXTURE',fixture),self.assertRaises(AssertionError):
                case.test_required_public_matrix_is_complete()

    def test_removed_hero_response_and_request_are_rejected(self):
        self.assert_removed_request_rejected(lambda req:req['path'].endswith('/hero-equips'))

    def test_removed_condition_response_and_request_are_rejected(self):
        self.assert_removed_request_rejected(lambda req:req['path']=='/explorer/query')

    def test_fewer_passing_display_groups_are_rejected(self):
        for domain,count in [('explorer',116),('hero',144),('hex',72),('items',24)]:
            with self.subTest(domain=domain):
                report={'failed':0,'not_verified':0,'passed':count-1,
                        'cases':[{'domain':domain,'status':'pass'} for _ in range(count-1)]}
                case=replay.RealDisplayReplay('test_explorer')
                with patch.object(replay,'run',return_value=report),patch.object(replay,'REPORTS',[]),self.assertRaises(AssertionError):
                    case.verify(domain)


if __name__=='__main__':unittest.main()
