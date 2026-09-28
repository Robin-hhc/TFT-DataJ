"""Public, frozen matrix; no MuMu, personal screenshots or live requests."""
from pathlib import Path
from collections import Counter
import gzip
import json
import unittest
from display_audit import run

FIXTURE=Path(__file__).parent/'fixtures/data_display/matrix.json.gz'
REPORTS=[]


class RealDisplayReplay(unittest.TestCase):
    def test_required_public_matrix_is_complete(self):
        data=json.loads(gzip.decompress(FIXTURE.read_bytes()))
        matrix=data['matrix'];self.assertEqual(len(matrix['versions']),2)
        self.assertEqual(Counter(c['kind'] for c in matrix['conditions']),{'equip':8,'hex':4,'hero':4,'trait':4})
        self.assertEqual(Counter(c['entity']['type'] for c in matrix['conditions'] if c['kind']=='equip'),{'成型装备':4,'转职纹章':4})
        self.assertEqual(Counter(h['level'] for h in matrix['hexes']),{1:3,2:3,3:3})
        self.assertEqual(Counter(e['type'] for e in matrix['items']),{'成型装备':3,'神器装备':3,'光明武器':3})
        self.assertEqual(set(matrix['comps']),{v+':'+c for v in matrix['versions'] for c in ['112','120','100']})
        self.assertFalse(data['gaps'],'Mandatory real capture matrix incomplete')
        from display_audit import request_key
        def key(r):return request_key(r['method'],r['path'],r.get('params'),r.get('body'))
        required={key(r) for r in matrix['requests']};present={key(r['request']) for r in data['records']}
        self.assertGreaterEqual(len(required),150);self.assertFalse(required-present,'Required responses removed from fixture')

    def verify(self,domain):
        self.assertTrue(FIXTURE.is_file(),'Required public fixture missing')
        report=run(FIXTURE,{domain});REPORTS.append(report)
        self.assertEqual(report['failed'],0,[r for r in report['cases'] if r['status']=='mismatch'])
        self.assertEqual(report['not_verified'],0,[r for r in report['cases'] if r['status'] not in ('pass','mismatch')])
        self.assertGreater(report['passed'],0)

    def test_explorer(self):self.verify('explorer')
    def test_hero_equipment(self):self.verify('hero')
    def test_hex_stages(self):self.verify('hex')
    def test_item_overlays(self):self.verify('items')


if __name__=='__main__':unittest.main()
