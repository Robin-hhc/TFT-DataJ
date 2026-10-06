"""Public, frozen matrix; no MuMu, personal screenshots or live requests."""
from pathlib import Path
from collections import Counter
import gzip
import json
import unittest
from display_audit import run

FIXTURE=Path(__file__).parent/'fixtures/data_display/matrix.json.gz'
REPORTS=[]
# Accepted public baseline dimensions. A new baseline requires an explicit
# review of these IDs and counts; editing its own request manifest is not proof
# that the previously accepted coverage is still present.
VERSIONS=('18.2a','18.2')
COMPS=('112','120','100')
CONDITION_IDS={'equip':('2004','2045','2018','2013','41806','41813','41804','41805'),
               'hex':('20778','1023','30668','2189'),
               'hero':('14503','38702','42503','33513'),
               'trait':('83710101','83710102','85200101','83900101')}
HEX_IDS={1:('1023','20771','10707'),2:('20778','30668','20578'),3:('3137','30665','30757')}
ITEM_IDS={'成型装备':('2004','2023','2048'),'神器装备':('6052','6083','6065'),
          '光明武器':('2059','2077','2070')}
HERO_IDS={'112':('4510','4503'),'120':('2504','3500'),'100':('2510','3500')}
DISPLAY_GROUPS={'explorer':116,'hero':144,'hex':72,'items':24}


def request_identity(request):
    return json.dumps(request,sort_keys=True,ensure_ascii=False)


def reviewed_requests(matrix):
    """Rebuild request dimensions only; never generate statistical answers."""
    requests=[]
    def get(path,version=None,**params):
        requests.append({'method':'GET','path':path,'params':{'setId':18,
                         **({'gameVersion':version} if version else {}),**params}})
    def explore(version,kind,entity):
        rule={'starCount':'','type':kind,'targetId':str(entity['id']),'enable':True,
              'targetName':entity['name'],'hexRound':'','nameMatch':False,
              'equipCarry':'','equipCount':'','exclude':False}
        if kind=='trait':rule['traitLevel']=str(entity['num'])
        requests.append({'method':'POST','path':'/explorer/query','body':{
            'version':version,'setId':18,'filter':{'rules':[rule],'combinator':'and'}}})
    for version in VERSIONS:
        get('/comp/rank',version,minSample=50)
        for condition in matrix['conditions']:explore(version,condition['kind'],condition['entity'])
        for comp in (None,*COMPS):
            get(f'/comp/{comp}/hexes' if comp else '/stats/hex',version)
            get(f'/comp/{comp}/equips' if comp else '/stats/equip',version)
            if comp:
                for hero in HERO_IDS[comp]:get(f'/comp/{comp}/hero-equips',version,heroId=hero)
            for item in matrix['items']:
                if comp:get(f'/comp/{comp}/equip-heroes',version,equipId=str(item['id']))
                else:get(f'/stats/equip/{item["id"]}/heroes',version)
        for item in matrix['items']:explore(version,'equip',item)
    # Spear of Shojin appears in both the conditions and the item fallback
    # matrix, and intentionally shares one real request per version.
    return {request_identity(request) for request in requests}


class RealDisplayReplay(unittest.TestCase):
    def test_required_public_matrix_is_complete(self):
        data=json.loads(gzip.decompress(FIXTURE.read_bytes()))
        matrix=data['matrix'];self.assertEqual(matrix['versions'],list(VERSIONS))
        self.assertEqual(Counter(c['kind'] for c in matrix['conditions']),{'equip':8,'hex':4,'hero':4,'trait':4})
        self.assertEqual(Counter(c['entity']['type'] for c in matrix['conditions'] if c['kind']=='equip'),{'成型装备':4,'转职纹章':4})
        self.assertEqual(Counter(h['level'] for h in matrix['hexes']),{1:3,2:3,3:3})
        self.assertEqual(Counter(e['type'] for e in matrix['items']),{'成型装备':3,'神器装备':3,'光明武器':3})
        self.assertEqual(Counter((c['kind'],str(c['entity']['id'])) for c in matrix['conditions']),
                         Counter((kind,id_) for kind,ids in CONDITION_IDS.items() for id_ in ids))
        self.assertEqual(Counter((h['level'],str(h['id'])) for h in matrix['hexes']),
                         Counter((level,id_) for level,ids in HEX_IDS.items() for id_ in ids))
        self.assertEqual(Counter((e['type'],str(e['id'])) for e in matrix['items']),
                         Counter((kind,id_) for kind,ids in ITEM_IDS.items() for id_ in ids))
        self.assertEqual(set(matrix['comps']),{v+':'+c for v in VERSIONS for c in COMPS})
        for version in VERSIONS:
            for comp in COMPS:
                members={str(hero['heroId']) for hero in matrix['comps'][version+':'+comp]['heroes']}
                self.assertTrue(set(HERO_IDS[comp])<=members,'Reviewed carry/frontline missing from comp detail')
        self.assertFalse(data['gaps'],'Mandatory real capture matrix incomplete')
        required=reviewed_requests(matrix)
        self.assertEqual(len(required),158,'Reviewed request dimensions changed')
        manifest=[request_identity(request) for request in matrix['requests']]
        self.assertEqual(len(manifest),len(set(manifest)),'Duplicate request in frozen manifest')
        self.assertSetEqual(set(manifest),required,'Frozen manifest lost reviewed request coverage')
        bootstrap={request_identity({'method':'GET','path':'/gamedata','params':{'setId':18}})}
        for version in VERSIONS:
            for comp in COMPS:
                bootstrap.add(request_identity({'method':'GET','path':f'/comp/{comp}',
                    'params':{'setId':18,'gameVersion':version}}))
        present=[request_identity(record['request']) for record in data['records']]
        self.assertEqual(len(present),len(set(present)),'Duplicate frozen response identity')
        self.assertSetEqual(set(present),required|bootstrap,'Frozen responses differ from reviewed matrix')
        self.assertEqual(len(present),165)

    def verify(self,domain):
        self.assertTrue(FIXTURE.is_file(),'Required public fixture missing')
        report=run(FIXTURE,{domain});REPORTS.append(report)
        self.assertEqual(report['failed'],0,[r for r in report['cases'] if r['status']=='mismatch'])
        self.assertEqual(report['not_verified'],0,[r for r in report['cases'] if r['status'] not in ('pass','mismatch')])
        self.assertEqual(report['passed'],DISPLAY_GROUPS[domain],'Real display coverage shrank')
        self.assertEqual(Counter(case['domain'] for case in report['cases']),
                         Counter({domain:DISPLAY_GROUPS[domain]}),'Display report omitted reviewed groups')

    def test_explorer(self):self.verify('explorer')
    def test_hero_equipment(self):self.verify('hero')
    def test_hex_stages(self):self.verify('hex')
    def test_item_overlays(self):self.verify('items')


if __name__=='__main__':unittest.main()
