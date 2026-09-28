import unittest
from types import SimpleNamespace
from item_stats import item_stat, fallback_stat, best_holders, query_key


def envelope(data):return {'data':data,'source':'test','fetched_at':10}


class ItemValueTests(unittest.TestCase):
    def test_patch_switch_and_return_use_explicit_source_keys(self):
        adapter=SimpleNamespace(set_id=18,patch='18.2a')
        original=query_key(adapter,'table','112')
        cache={original:'18.2a values'}
        for patch in ('18.1','18.2','18.1.c'):
            adapter.patch=patch
            self.assertNotIn(query_key(adapter,'table','112'),cache)
        adapter.patch='18.2a'
        self.assertEqual(cache[query_key(adapter,'table','112')],'18.2a values')
        self.assertNotIn(query_key(adapter,'holders',('112','2004')),cache)

    def test_missing_radiant_uses_matching_comp_row_without_averaging(self):
        self.assertEqual(item_stat(envelope({'equips':[]}),2059,112)['status'],'missing')
        result=envelope({'comps':[{'compId':113,'avgPlacement':2.1,'sampleCount':900},
                                   {'compId':112,'avgPlacement':3.61,'sampleCount':185}]})
        self.assertEqual(fallback_stat(result,'112')['average'],3.61)
        self.assertEqual(fallback_stat(result,'112')['samples'],185)
        self.assertEqual(fallback_stat(result,'114')['status'],'missing')

    def test_holders_filter_by_id_and_samples_without_mixing_global(self):
        rows=[{'heroId':1,'name':'同名','avgPlacement':1.1,'sampleCount':2},
              {'heroId':2,'name':'同名','avgPlacement':3.5,'sampleCount':500},
              {'heroId':3,'name':'其他','avgPlacement':2.5,'sampleCount':900},
              {'heroId':4,'name':'本阵容','avgPlacement':3.5,'sampleCount':800}]
        self.assertEqual([r['id'] for r in best_holders(envelope(rows),{'1','2','4'})],['4','2'])
        self.assertEqual(best_holders(envelope(rows),set()),[])
        self.assertEqual([r['id'] for r in best_holders(envelope(rows))],['3','4'])


if __name__=='__main__':unittest.main()
