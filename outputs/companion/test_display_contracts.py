"""Synthetic boundary cases; these are not counted as live data samples."""
import copy
from pathlib import Path
import tempfile
import unittest
import httpx
from dataj import DataJ, SourceError


class DisplayContracts(unittest.TestCase):
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
