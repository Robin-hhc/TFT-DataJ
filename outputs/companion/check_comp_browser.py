import json,time
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt
from app import Companion,QApplication
from bootstrap import ROOT,STATE_DIR
from integration_check import FrozenSource
class Source(FrozenSource):
 def comps(self):return json.loads((ROOT/'work/comp-browser/rank.json').read_text(encoding='utf-8'))
qt=QApplication([])
with patch('app.win.enumerate_mumu',return_value=[]):panel=Companion(offline=True)
panel.timer.stop();panel.adapter=Source()
def wait():
 end=time.monotonic()+15
 while panel.jobs and time.monotonic()<end:qt.processEvents();time.sleep(.01)
 qt.processEvents();assert not panel.jobs
panel.browser.retry();wait()
assert panel.tabs.currentIndex()==1 and len(panel.browser.cards)==8
assert len(panel.browser.rows)>8
panel.resize(1140,860);panel.grab();qt.processEvents();panel.grab().save(str(STATE_DIR/'comp-browser-home.png'))
entity=next(x for x in panel.catalog['equip'] if str(x['id'])=='41806')
panel.run_explore('equip',entity);wait()
assert panel.browser.scope[1]['id']==entity['id'] and len(panel.browser.rows)==35
assert '条件内' in panel.browser.note.text()
panel.grab().save(str(STATE_DIR/'comp-browser-filter.png'))
card=next(c for c in panel.browser.cards if c.comp_id=='112')
card.choose.click();wait()
assert panel.session.target=='112' and panel.comp_detail['name']=='地狱火95'
assert panel.tabs.currentIndex()==2 and panel.copy_button.isEnabled()
with patch('app.QApplication.clipboard') as clip:
 panel.copy_code();clip.return_value.setText.assert_called_once_with(panel.comp_detail['gameCode'])
panel.tabs.setCurrentIndex(1);panel.clear_explorer();wait()
assert panel.session.target=='112' and panel.browser.scope is None
assert '全局' in panel.browser.note.text()
# A late filtered response cannot overwrite a newer all-comps request.
jobs=[];panel.submit=lambda pool,fn,done,failed=None:jobs.append((fn,done,failed))
panel.run_explore('equip',entity);panel.clear_explorer()
old,new=jobs;new[1](new[0]());all_ids=[x['compId'] for x in panel.browser.rows]
old[1](old[0]());assert [x['compId'] for x in panel.browser.rows]==all_ids
# Switching comp clears code immediately and ignores a late prior detail.
jobs.clear();panel.select_comp('104');panel.select_comp('112');a,b=jobs
assert not panel.copy_button.isEnabled() and panel.comp_detail is None
b[1](b[0]());a[2]('late failure');assert panel.session.target=='112' and panel.copy_button.isEnabled()
panel.unpin();assert panel.session.target is None and not panel.copy_button.isEnabled()
jobs.clear();panel.new_game();assert panel.stage.currentIndex()==-1
assert all(p.currentData() is None for p in panel.picks)
panel.manual_stats();assert panel.session.stage is None
from comp_browser import portrait_catalog
from PySide6.QtNetwork import QSslSocket
assert QSslSocket.activeBackend()=='schannel'
portraits=portrait_catalog(panel.catalog['hero'])
assert portraits['name:希维尔']['picture'].endswith('s18_head_sivir.png')
panel.shutdown();print(json.dumps({'comp_browser':'passed','checks':['all comps','single condition','one click pins','copy scope','clear retains target','late query','late comp response','unpin'],'rendered':['comp-browser-home.png','comp-browser-filter.png']}))
