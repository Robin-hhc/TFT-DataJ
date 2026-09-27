"""Render our own hidden widgets with frozen data; never activates the desktop."""
import json,time
from unittest.mock import patch
from app import Companion,QApplication
from integration_check import FrozenSource
from bootstrap import ROOT,STATE_DIR


def main():
    app=QApplication([])
    with patch('app.win.enumerate_mumu',return_value=[]):panel=Companion(offline=True)
    panel.timer.stop();panel.adapter=FrozenSource()
    for index,nav in enumerate(panel.navigation):
        for _ in range(2):
            nav.click()
            assert panel.tabs.currentIndex()==index
            assert [button.isChecked() for button in panel.navigation]==[i==index for i in range(4)]
    panel.kind.setCurrentIndex(panel.kind.findData('hex'));panel.search.setText('别再错过')
    labels=[panel.entities.item(i).text() for i in range(panel.entities.count())]
    assert len(labels)>1 and len(set(labels))==len(labels),labels
    panel.search.clear()
    output=ROOT/'outputs/ui-preview';output.mkdir(exist_ok=True)
    def settle():
        deadline=time.monotonic()+15
        while panel.jobs and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
        assert not panel.jobs
        panel.grab();app.processEvents()
    def save(name,index=0,size=(1080,760)):
        panel.tabs.setCurrentIndex(index);panel.resize(*size);settle()
        assert panel.tabs.widget(index).horizontalScrollBar().maximum()==0,(name,'horizontal overflow')
        panel.grab().save(str(output/(name+'.png')))
    save('01-home')
    save('02-compact-home',size=(920,660))
    obs=json.loads((STATE_DIR/'real-gameplay-eval.json').read_text(encoding='utf-8'))['rows'][0]['observation']
    panel.observed(obs,False);settle()
    assert panel.result_cards[0].name.text()=='银汤匙'
    assert panel.result_cards[0].average_label.text()!='—'
    panel.choice_note.setText('离线样例 · 2-1 · 来自已标注 S18 录像与冻结统计；非当前对局')
    save('03-results')
    panel.invalidate()
    assert all(card.average_label.text()=='—' for card in panel.result_cards)
    equip=next(x for x in panel.catalog['equip'] if str(x['id'])=='41806')
    panel.kind.setCurrentIndex(panel.kind.findData('equip'));panel.search.setText('地狱火')
    panel.run_explore('equip',equip);settle();save('04-explorer',1)
    save('05-guide',2)
    panel.comp_url.setText('https://www.dataj.cc/comp/112');panel.pin_comp();settle()
    panel.heroes.setCurrentIndex(panel.heroes.findData('4503'));panel.query_equipment();settle()
    save('06-equipment',3)
    panel.tabs.setCurrentIndex(0);panel.toggle_advanced();save('07-advanced')
    panel.toggle_advanced();panel.resize(1080,760)
    panel.result_cards[0].update_result(['连败连胜才能连鸡（待纠正）','— 无数据/未识别','— 无该阶段数据'])
    assert panel.result_cards[0].average_label.text()=='—'
    save('08-uncertain')
    panel.shutdown()
    print(json.dumps({'preview_dir':str(output),'screens':8,'live_game':False,'network':False},ensure_ascii=False))


if __name__=='__main__':main()
