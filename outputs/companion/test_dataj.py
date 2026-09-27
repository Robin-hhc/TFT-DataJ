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

    def test_comp_list_scope_and_malformed_response(self):
        a=DataJ(db=self.db,transport=httpx.MockTransport(self.handle))
        self.assertEqual(a.comps()['data'],[])
        self.assertEqual(dict(self.calls[0].url.params),{'setId':'18','gameVersion':'18.2a','minSample':'50'})
        with self.assertRaises(SourceError):DataJ.validate_comps([{'compId':'invalid','name':'x'}])
        with self.assertRaises(SourceError):DataJ.validate_comps({'comps':[]})
        for fields in [{'heroes':[None]},{'heroes':[{'heroName':42}]},{'traits':'invalid'}]:
            with self.assertRaises(SourceError):DataJ.validate_comps([{'compId':112,'name':'x',**fields}])
        rows=[{'compId':112,'name':'x','heroes':None}];DataJ.validate_comps(rows)
        self.assertEqual(rows[0]['heroes'],[])

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

    def test_version_list_uses_site_values_including_dotted_patch(self):
        chunk='16:'+json.dumps({'gameVersions':[{'setId':18,'gameVersion':'18.2a'},
            {'setId':18,'gameVersion':'18.1.c'},{'setId':19,'gameVersion':'19.1'}]},separators=(',',':'))
        html='<script>self.__next_f.push([1,'+json.dumps(chunk)+'])</script>'
        self.assertEqual(DataJ.parse_versions(html),['18.2a','18.1.c'])
        with self.assertRaises(SourceError):DataJ.parse_versions('<html>error</html>')

    def test_selected_version_reaches_every_statistics_endpoint(self):
        a=DataJ(patch='18.1.c',db=self.db,transport=httpx.MockTransport(self.handle))
        for endpoint in ('/comp/rank','/stats/hex','/comp/112','/comp/112/hexes','/comp/112/hero-equips'):
            a.next_request=0;a.request(endpoint)
            self.assertEqual(self.calls[-1].url.params['gameVersion'],'18.1.c')
        a.next_request=0;a.explore('hex',{'id':'1023','name':'应急护甲 I'})
        self.assertEqual(json.loads(self.calls[-1].content)['version'],'18.1.c')

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
