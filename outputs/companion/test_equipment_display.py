import copy
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import httpx
from app import QApplication, Companion
from dataj import DataJ


class EquipmentDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt=QApplication.instance() or QApplication([])
        cls.fixture=json.loads((Path(__file__).parent/'fixtures/data_display/amumu-equipment.json').read_text(encoding='utf-8'))

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.state=ExitStack()
        for module in ['app','dataj','comp_browser']:self.state.enter_context(patch(module+'.STATE_DIR',Path(self.tmp.name)))
        self.panel=Companion(offline=True,offline_catalog={'hex':[],'hero':[],'trait':[],**self.fixture['catalog']})
        self.panel.timer.stop()
        self.data=copy.deepcopy(self.fixture['data'])
        self.panel.adapter=DataJ(db=Path(self.tmp.name)/'cache.db',transport=httpx.MockTransport(
            lambda r:httpx.Response(200,json={'success':True,'code':200,'data':self.data})))
        self.panel.session.set_target('112')
        self.panel.heroes.addItem('阿木木','4503')

    def tearDown(self):
        self.panel.shutdown();self.panel.deleteLater();self.qt.processEvents()
        self.state.close();self.tmp.cleanup()

    def query(self,form='单件',kind='全部'):
        for combo,value in ((self.panel.equip_form,form),(self.panel.equip_type,kind)):
            combo.blockSignals(True);combo.setCurrentText(value);combo.blockSignals(False)
        self.panel.query_equipment();end=time.monotonic()+5
        while self.panel.jobs and time.monotonic()<end:self.qt.processEvents();time.sleep(.001)
        self.assertFalse(self.panel.jobs)
        t=self.panel.equip_table
        return [[t.item(i,j).text() for j in range(3)] for i in range(t.rowCount())]

    def test_real_single_equipment_matches_site_filtered_rows(self):
        self.assertEqual(self.query(),self.fixture['expected']['heroEquips'])

    def test_real_three_items_match_site_filtered_rows(self):
        self.assertEqual(self.query('三件套'),self.fixture['expected']['hero3Equips'])

    def test_sample_boundary_and_type_filter(self):
        self.data['heroEquips']=[{'equips':[{'id':'2004','name':'朔极之矛'}],
            'avgPlacement':average,'sampleCount':count} for average,count in ((1,49),(4,50),(5,51))]
        self.assertEqual(self.query(kind='成型装备'),[['朔极之矛','4.00','50'],['朔极之矛','5.00','51']])

    def test_empty_qualified_results_are_explained(self):
        self.data['heroEquips']=[{'equips':[{'id':'2004','name':'朔极之矛'}],'avgPlacement':1,'sampleCount':1}]
        self.assertEqual(self.query(),[])
        self.assertIn('50',self.panel.equip_note.text())


if __name__=='__main__':unittest.main()
