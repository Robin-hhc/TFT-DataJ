"""Exercise our own Qt widgets and async handlers with frozen, labeled responses."""
import json
import time
from pathlib import Path
from app import Companion, QApplication
from bootstrap import ROOT,STATE_DIR


class FrozenSource:
    patch='18.2a'
    set_id=18

    def item_stats(self,comp=None):
        name='comp.json' if comp else 'global.json'
        payload=json.loads((ROOT/'work/item-choice-probe'/name).read_text(encoding='utf-8'))
        return {'data':payload['payload']['data'],'source':'frozen item table','fetched_at':0,'cached':True}

    def read(self,name):
        file=ROOT/'work/dataj-p0'/name
        return {'data':json.loads(file.read_text(encoding='utf-8'))['data'],'fetched_at':0,'cached':True}

    def hexes(self,comp=None):
        result=self.read('comp112-hex.json' if comp else 'global-hex.json')
        if comp:result['data']=result['data']['hexes']
        return result

    def comp(self,comp):
        return {'data':json.loads((ROOT/'work/mvp-contracts-comp112.json').read_text(encoding='utf-8'))['data']}

    def equipment(self,comp,hero):
        assert comp=='112' and hero=='4503'
        return self.read('comp112-amumu-items.json')

    def explore(self,kind,entity):
        assert kind=='equip' and str(entity['id'])=='41806'
        return self.read('explorer-inferno.json')

    def comps(self,min_sample=50):
        assert min_sample==50,'This frozen source only captures the default sample scope'
        return json.loads((ROOT/'work/comp-browser/rank.json').read_text(encoding='utf-8'))


def main():
    app=QApplication([])
    panel=Companion(offline=True);panel.timer.stop();panel.adapter=FrozenSource()
    def wait():
        deadline=time.monotonic()+10
        while panel.jobs and time.monotonic()<deadline:
            app.processEvents();time.sleep(.01)
        app.processEvents()
        assert not panel.jobs,'async job timed out'
    checks=[]
    panel.comp_url.setText('https://www.dataj.cc/comp/112');panel.pin_comp();panel.return_to_game();wait()
    assert panel.comp_detail['name']=='地狱火95'
    checks.append('pin comp detail survives panel hide and OCR invalidation')
    for combo in panel.picks:combo.setCurrentIndex(combo.findData('30668'))
    panel.manual_stats();wait()
    assert panel.choice_table.item(0,1).text().startswith('3.65')
    assert panel.choice_table.item(0,2).text().startswith('3.52')
    checks.append('global versus comp stage values')
    panel.stage.setCurrentText('3-2')
    assert panel.choice_table.rowCount()==0
    checks.append('changed input clears displayed stats')
    panel.observed({'scene':'choice_candidates','round':'3-1','cards':[]},False)
    assert panel.choice_table.rowCount()==0 and not panel.jobs
    checks.append('unsupported observed round rejected instead of stale dropdown stage')
    from PySide6.QtCore import QUrl
    panel.guide_url_changed(QUrl('https://www.dataj.cc/comp/113'))
    assert panel.comp_url.text().endswith('/113') and panel.session.target=='112'
    checks.append('guide navigation updates browse address without repinning')
    equip=next(r for r in panel.catalog['equip'] if str(r['id'])=='41806')
    panel.run_explore('equip',equip);wait()
    assert len(panel.browser.rows)==35
    assert panel.session.target=='112'
    checks.append('single condition explorer without changing pinned comp')
    panel.heroes.setCurrentIndex(panel.heroes.findData('4503'))
    panel.query_equipment();wait()
    assert panel.equip_table.rowCount()==36
    assert [panel.equip_table.item(0,j).text() for j in range(3)]==['光明版狂徒铠甲','3.12','104']
    assert all(int(panel.equip_table.item(i,2).text())>=50 for i in range(panel.equip_table.rowCount()))
    assert panel.equip_table.item(0,1).foreground().color().getRgb()[:3]==(191,254,127)
    checks.append('hero ID equipment table')
    panel.run_explore('equip',equip);panel.clear_explorer();wait()
    assert panel.browser.scope is None and len(panel.browser.rows)>0
    checks.append('late explorer result discarded')
    panel.manual_stats();panel.new_game();wait()
    assert panel.session.target is None and panel.choice_table.rowCount()==0 and panel.browser.scope is None
    assert panel.stage.currentIndex()==-1 and all(p.currentData() is None for p in panel.picks)
    panel.manual_stats();assert panel.session.stage is None
    checks.append('new game invalidates late stats and clears resources')
    panel.shutdown()
    (STATE_DIR/'integration-result.json').write_text(json.dumps({'fixture_only':True,'checks':checks},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':len(checks),'checks':checks},ensure_ascii=False))


if __name__=='__main__':main()
