import json
from pathlib import Path
import tempfile
import unittest
import httpx
from dataj import DataJ, SourceError


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name)/'cache.db'
        self.calls = []

    def tearDown(self):
        self.temp.cleanup()

    def handle(self, request):
        self.calls.append(request)
        data={'comps':[]} if request.url.path.endswith('/explorer/query') else []
        return httpx.Response(200,json={'code':200,'success':True,'data':data})

    def test_cache_separates_versions_and_comp(self):
        t = httpx.MockTransport(self.handle)
        a = DataJ(db=self.db, transport=t)
        a.request('/stats/hex')
        a.request('/stats/hex')
        b = DataJ(patch='18.1',db=self.db,transport=t)
        b.request('/stats/hex')
        b.next_request=0
        b.request('/comp/112/hexes')
        self.assertEqual(len(self.calls),3)

    def test_explorer_keeps_exactly_one_rule(self):
        a=DataJ(db=self.db,transport=httpx.MockTransport(self.handle))
        a.explore('equip',{'id':'41806','name':'地狱火纹章'})
        body=json.loads(self.calls[0].content)
        self.assertEqual(len(body['filter']['rules']),1)
        self.assertEqual(body['filter']['rules'][0]['targetId'],'41806')

    def test_failure_does_not_return_expired_cache(self):
        a=DataJ(db=self.db,transport=httpx.MockTransport(self.handle))
        a.request('/stats/hex')
        a.next_request=0
        a.transport=httpx.MockTransport(lambda r:httpx.Response(429))
        with self.assertRaises(SourceError):a.request('/stats/hex',ttl=0)
        with self.assertRaises(SourceError):a.request('/comp/112')

    def test_wrong_comp_scope_is_rejected(self):
        a=DataJ(db=self.db,transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'code':200,'success':True,'data':{'compId':'999','hexes':[]}})))
        with self.assertRaises(SourceError):a.hexes('112')


if __name__=='__main__':unittest.main()
