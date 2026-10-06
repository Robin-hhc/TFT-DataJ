"""Synthetic boundary cases; these are not counted as live data samples."""
import copy
from pathlib import Path
import tempfile
import unittest
import httpx
from dataj import DataJ, SourceError


class DisplayContracts(unittest.TestCase):
    def test_valid_holder_names_and_empty_comp_heroes_remain_available(self):
        hero={'heroId':4503,'avgPlacement':3.5,'sampleCount':50}
        with tempfile.TemporaryDirectory() as tmp:
            cases=[(lambda a:a.item_holders('2004'),[{**hero,'name':'阿木木'}]),
                (lambda a:a.item_holders('2004','112'),{'compId':'112','equipId':'2004','heroes':[{**hero,'heroName':'阿木木'}]}),
                (lambda a:a.comp('112'),{'compId':'112','heroes':[]}),
                (lambda a:a.comp('112'),{'compId':'112','heroes':[{'heroId':4503,'heroName':'阿木木'}]})]
            for index,(call,data) in enumerate(cases):
                adapter=DataJ(db=Path(tmp)/f'{index}.db',transport=httpx.MockTransport(
                    lambda request,payload=data:httpx.Response(200,json={'success':True,'code':200,'data':payload})))
                for cached in (False,True):
                    with self.subTest(data=data,cached=cached):
                        result=call(adapter)
                        self.assertEqual(result['data'],data)
                        self.assertEqual(result['cached'],cached)

    def test_comp_details_reject_malformed_hero_identity_before_display(self):
        hero={'heroId':'4503','heroName':'阿木木'}
        cases=[None,[],{'heroId':'4503'},{'heroName':'阿木木'}]
        cases.extend({**hero,'heroName':name} for name in [None,42,'',' \t'])
        cases.extend({**hero,'heroId':identity} for identity in [None,True,0,-1,1.5,'','one'])
        with tempfile.TemporaryDirectory() as tmp:
            for index,invalid in enumerate(cases):
                data={'compId':'112','name':'测试阵容','heroes':[invalid]}
                adapter=DataJ(db=Path(tmp)/f'{index}.db',transport=httpx.MockTransport(
                    lambda request,payload=data:httpx.Response(200,json={'success':True,'code':200,'data':payload})))
                for cached in (False,True):
                    with self.subTest(hero=invalid,cached=cached),self.assertRaises(SourceError):
                        adapter.comp('112')

    def test_holder_endpoints_reject_missing_or_invalid_display_names(self):
        row={'heroId':'4503','avgPlacement':3.5,'sampleCount':50}
        with tempfile.TemporaryDirectory() as tmp:
            for scope,field in [(None,'name'),('112','heroName')]:
                for index,fields in enumerate([{}, {field:None}, {field:42},
                        {field:''}, {field:' \t'}, {'name':'阿木木','heroName':None}]):
                    rows=[{**row,**fields}]
                    data=rows if scope is None else {'compId':scope,'equipId':'2004','heroes':rows}
                    adapter=DataJ(db=Path(tmp)/f'{scope}-{index}.db',transport=httpx.MockTransport(
                        lambda request,payload=data:httpx.Response(200,json={'success':True,'code':200,'data':payload})))
                    for cached in (False,True):
                        with self.subTest(scope=scope,fields=fields,cached=cached),self.assertRaises(SourceError):
                            adapter.item_holders('2004',scope)

    def test_comp_rejects_invalid_numeric_statistics_and_duplicate_ids(self):
        row={'compId':112,'name':'test','avgPlacement':4.2,'sampleCount':50,'top4Rate':50,'topRate':10}
        for key,values in [('avgPlacement',[True,'4.2',0,9,float('nan'),float('inf')]),
                           ('sampleCount',[True,'50',-1,1.5]),('top4Rate',[-1,101,True,'50']),('topRate',[101])]:
            for value in values:
                with self.subTest(key=key,value=value),self.assertRaises(SourceError):
                    DataJ.validate_comps([{**row,key:value}])
        with self.assertRaises(SourceError):DataJ.validate_comps([row,{**row,'compId':'112'}])
        for count in [0,1,49,50,51]:DataJ.validate_comps([{**row,'sampleCount':count}])
        for avg in [1,8]:DataJ.validate_comps([{**row,'avgPlacement':avg,'top4Rate':0,'topRate':100}])

    def test_hero_equipment_rejects_invalid_values_before_display(self):
        row={'equips':[{'id':2004,'name':'朔极之矛'}],'avgPlacement':4.2,'sampleCount':50}
        with tempfile.TemporaryDirectory() as tmp:
            for index,(key,value) in enumerate([('avgPlacement',True),('avgPlacement',9),('avgPlacement',None),
                 ('sampleCount',-1),('sampleCount','50'),('equips',[]),('equips',[{'id':True,'name':'x'}])]):
                data={'compId':'112','heroId':'4503','heroEquips':[{**copy.deepcopy(row),key:value}],'hero3Equips':[]}
                adapter=DataJ(db=Path(tmp)/f'{index}.db',transport=httpx.MockTransport(
                    lambda r:httpx.Response(200,json={'success':True,'code':200,'data':data})))
                with self.subTest(key=key,value=value),self.assertRaises(SourceError):adapter.equipment('112','4503')

    def test_malformed_hex_parts_are_rejected_before_qt_callback(self):
        part={'round':1,'roundLabel':'3-2','avgPlacement':4.2,'sampleCount':50}
        cases=[[None],[{**part,'round':True}],[{**part,'avgPlacement':None}],[part,part]]
        with tempfile.TemporaryDirectory() as tmp:
            for index,parts in enumerate(cases):
                adapter=DataJ(db=Path(tmp)/f'{index}.db',transport=httpx.MockTransport(
                    lambda r:httpx.Response(200,json={'success':True,'code':200,'data':[{'hexId':1023,'roundStats':parts}]})))
                with self.subTest(parts=parts),self.assertRaises(SourceError):adapter.hexes()


if __name__=='__main__':unittest.main()
