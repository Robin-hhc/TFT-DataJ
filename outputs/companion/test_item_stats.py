import json
from pathlib import Path
import tempfile
import unittest
import httpx

from dataj import DataJ, SourceError


class ItemDataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.calls = []
        self.response = []
        self.adapter = DataJ(patch='18.1.c', db=Path(self.tmp.name)/'cache.db',
                             transport=httpx.MockTransport(self.handle))

    def tearDown(self):
        self.tmp.cleanup()

    def handle(self, request):
        self.calls.append(request)
        return httpx.Response(200, json={'code':200, 'success':True, 'data':self.response})

    def test_scopes_and_version_reach_item_endpoints(self):
        cases = [
            (lambda:self.adapter.item_stats(), [], '/stats/equip', {}),
            (lambda:self.adapter.item_stats('112'), {'compId':'112','equips':[]}, '/comp/112/equips', {}),
            (lambda:self.adapter.item_holders('2059'), [], '/stats/equip/2059/heroes', {}),
            (lambda:self.adapter.item_holders('2059','112'),
             {'compId':'112','equipId':'2059','heroes':[]}, '/comp/112/equip-heroes', {'equipId':'2059'}),
        ]
        for fn, payload, path, extra in cases:
            self.response=payload; self.adapter.next_request=0; fn()
            self.assertTrue(self.calls[-1].url.path.endswith(path))
            self.assertEqual(dict(self.calls[-1].url.params),
                             {'setId':'18','gameVersion':'18.1.c',**extra})

    def test_wrong_scope_or_malformed_stat_is_rejected(self):
        for response in [
            {'compId':'113','equips':[]},
            {'compId':'112','equips':[{'equipId':2004,'sampleCount':20,'avgPlacement':9}]},
            {'compId':'112','equips':[{'equipId':2004,'sampleCount':-1,'avgPlacement':4}]},
            {'compId':'112','equips':[{'equipId':2004,'sampleCount':20,'avgPlacement':None}]},
        ]:
            self.response=response; self.adapter.next_request=0
            # Each invalid cached payload must also be rejected.
            with self.assertRaises(SourceError):self.adapter.item_stats('112')
            self.adapter.db.unlink(missing_ok=True)
            self.adapter=DataJ(db=self.adapter.db,transport=httpx.MockTransport(self.handle))

    def test_holder_scope_and_identity_validation(self):
        self.response={'compId':'112','equipId':'2004','heroes':[]}
        with self.assertRaises(SourceError):self.adapter.item_holders('2059','112')
        for value in ('', '../stats/hex', '0', 'one'):
            with self.assertRaises(ValueError):self.adapter.item_holders(value)

    def test_cache_does_not_mix_item_or_comp(self):
        self.adapter.item_holders('2004')
        self.adapter.item_holders('2004')
        self.adapter.next_request=0; self.adapter.item_holders('2059')
        self.response={'compId':'112','equipId':'2004','heroes':[]}
        self.adapter.next_request=0; self.adapter.item_holders('2004','112')
        self.assertEqual(len(self.calls),3)


if __name__ == '__main__':unittest.main()
