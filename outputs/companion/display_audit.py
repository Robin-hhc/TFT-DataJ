"""Frozen public responses -> real adapter -> real Qt display.

Also imported by the packaged diagnostic. No capture/OCR/game input or external
network is used. Only transport and native window placement are substituted.
"""
from contextlib import ExitStack
import copy
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch
import httpx
from PySide6.QtGui import QTextDocument, QPixmap, QColor
from PySide6.QtWidgets import QApplication, QLabel
from app import Companion, CardOverlay
from dataj import DataJ
from item_overlay import ItemOverlay


class MissingFixture(LookupError):
    pass


def request_key(method,path,params=None,body=None):
    return json.dumps([method,path,{str(k):str(v) for k,v in (params or {}).items()},body],sort_keys=True,ensure_ascii=False)


def plain(value):
    doc=QTextDocument();doc.setHtml(value);return doc.toPlainText()


def table_rows(table):
    return [[table.item(i,j).text() for j in range(table.columnCount())] for i in range(table.rowCount())]


def wait_jobs(panel,qt):
    end=time.monotonic()+10
    while panel.jobs and time.monotonic()<end:qt.processEvents();time.sleep(.001)
    qt.processEvents()
    assert not panel.jobs,'UI response timeout'


class ReplayDataJ(DataJ):
    def request(self,*args,**kwargs):
        # Rate limiting belongs to live capture, not a zero-I/O replay.
        self.next_request=0
        return super().request(*args,**kwargs)


class DisplayReplay:
    def __init__(self,path):
        self.fixture=json.loads(gzip.decompress(Path(path).read_bytes()))
        self.records=self.fixture['records'];self.matrix=self.fixture['matrix']
        self.lookup={request_key(r['request']['method'],r['request']['path'],r['request'].get('params'),r['request'].get('body')):r for r in self.records}
        assert len(self.lookup)==len(self.records),'Duplicate fixture request identity'
        self.gaps=[]
        reasons={request_key(r['request']['method'],r['request']['path'],r['request'].get('params'),r['request'].get('body')):r['status'] for r in self.fixture['gaps']}
        for req in self.matrix['requests']:
            identity=request_key(req['method'],req['path'],req.get('params'),req.get('body'))
            if identity not in self.lookup:self.gaps.append({'request':req,'status':reasons.get(identity,'missing_fixture')})
        self.gap_keys={request_key(r['request']['method'],r['request']['path'],r['request'].get('params'),r['request'].get('body')):r['status'] for r in self.gaps}
        for r in self.records:
            digest=hashlib.sha256(json.dumps(r['data'],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            assert digest==r['projected_sha256'],'Fixture content hash mismatch'
        self.catalog=next(r['data'] for r in self.records if r['request']['path']=='/gamedata')
        self.qt=QApplication.instance() or QApplication([])
        self.tmp=tempfile.TemporaryDirectory();self.stack=ExitStack();self.calls=[]
        for module in ['app','dataj','comp_browser']:
            self.stack.enter_context(patch(module+'.STATE_DIR',Path(self.tmp.name)))
        self.panel=Companion(offline=True,offline_catalog=self.catalog);self.panel.timer.stop()
        self.stack.enter_context(patch.object(ItemOverlay,'place',lambda *a:None))
        self.stack.enter_context(patch.object(CardOverlay,'place',lambda widget,binding,box,text:widget.setText(text)))
        self.stack.enter_context(patch('app.win.foreground_root',return_value=7))
        self.panel.binding=SimpleNamespace(hwnd=7)
        self.stack.enter_context(patch.object(self.panel,'panel_open',return_value=False))
        self.unmatched=[];self.errors=[]
        import sys
        def unhandled(kind,value,tb):self.errors.append(str(value))
        self.stack.enter_context(patch.object(sys,'excepthook',unhandled))

    def close(self):
        self.panel.shutdown();self.panel.deleteLater();self.qt.processEvents();self.stack.close();self.tmp.cleanup()

    def transport(self,request):
        path=request.url.path.removeprefix('/api/web')
        body=json.loads(request.content) if request.method=='POST' else None
        key=request_key(request.method,path,dict(request.url.params),body)
        self.calls.append(key)
        if key not in self.lookup:
            self.unmatched.append(key)
            return httpx.Response(503)
        return httpx.Response(200,json={'success':True,'code':200,'data':copy.deepcopy(self.lookup[key]['data'])})

    def version(self,value):
        self.panel.invalidate()
        self.panel.adapter=ReplayDataJ(patch=value,db=Path(self.tmp.name)/'replay.db',transport=httpx.MockTransport(self.transport))

    def record(self,path,version,**extra):
        identity=request_key('GET',path,{'setId':18,'gameVersion':version,**extra})
        if identity not in self.lookup:raise MissingFixture(identity)
        return self.lookup[identity]

    def explorer(self,record,order):
        p=self.panel;req=record['request'];v=req.get('params',{}).get('gameVersion') or req['body']['version'];self.version(v)
        p.browser.search.clear();p.browser.only_favs.setChecked(False);p.browser.sort.setCurrentIndex(order)
        if req['method']=='POST':
            rule=req['body']['filter']['rules'][0];kind=rule['type']
            entity={'id':rule['targetId'],'name':rule['targetName'],'num':rule.get('traitLevel')}
            p.browser.scope=(kind,entity);p.load_comps(kind,entity)
        else:p.browser.scope=None;p.load_comps()
        wait_jobs(p,self.qt)
        expected=record['expected']['samples' if order else 'average']
        assert [c.comp_id for c in p.browser.cards]==[r['id'] for r in expected[:8]],'first page identity/order'
        while len(p.browser.cards)<len(expected):
            old=len(p.browser.cards);p.browser.show_more()
            assert len(p.browser.cards)>old,'pagination did not advance'
        actual=[]
        for card in p.browser.cards:
            labels=card.findChildren(QLabel)
            actual.append({'id':card.comp_id,'name':card.findChild(QLabel,'cardName').text(),
                'metrics':[w.text() for w in labels if w.objectName()=='compAverage'],
                'samples':next(w.text() for w in labels if w.text().endswith(' 局'))})
        assert actual==expected,{'expected':expected,'actual':actual}
        if not expected:assert not p.browser.empty.isHidden(),'empty state missing'

    def hero(self,record,form,kind):
        p=self.panel;req=record['request'];self.version(req['params']['gameVersion']);data=record['data']
        p.session.set_target(str(data['compId']))
        p.heroes.blockSignals(True);p.heroes.clear();p.heroes.addItem(str(data['heroId']),str(data['heroId']));p.heroes.blockSignals(False)
        for combo,value in [(p.equip_form,'单件' if form=='heroEquips' else '三件套'),(p.equip_type,kind)]:
            combo.blockSignals(True);combo.setCurrentText(value);combo.blockSignals(False)
        p.query_equipment();wait_jobs(p,self.qt)
        actual=table_rows(p.equip_table);expected=record['expected'][form][kind]
        assert actual==expected,{'expected':expected,'actual':actual}
        assert '50' in p.equip_note.text()

    def hex(self,version,comp,stage,runes):
        p=self.panel;self.version(version);p.session.set_target(comp)
        p.stage.blockSignals(True);p.stage.setCurrentText(stage);p.stage.blockSignals(False)
        p.last_capture=time.monotonic()
        p.last_observation={'cards':[{'box':[[0,0],[100,0],[100,50],[0,50]]}]*3}
        ids=[str(r['id']) for r in runes];names=[r['name'] for r in runes]
        p.query_stats(ids,names,True);wait_jobs(p,self.qt)
        global_record=self.record('/stats/hex',version)
        comp_record=self.record(f'/comp/{comp}/hexes',version) if comp else None
        expected=[[name,global_record['expected'][id_][stage],comp_record['expected'][id_][stage] if comp else '未固定阵容'] for name,id_ in zip(names,ids)]
        actual=table_rows(p.choice_table)
        assert actual==expected,{'expected':expected,'actual':actual}
        for index,row in enumerate(expected):
            assert plain(p.overlays[index].text())==f'{stage} · {row[0]}\n全局 {row[1]}\n阵容 {row[2]}','augment overlay slot/text mismatch'
            card=p.result_cards[index];parts=row[1].split(' · ',1)
            numeric=parts[0][0].isdigit()
            assert [card.name.text(),card.average_label.text(),card.sample.text(),card.comp.text()]==[
                row[0],parts[0] if numeric else '—','样本 '+parts[1] if numeric else row[1].removeprefix('— '),
                '本局阵容  ·  '+row[2]],'visible augment panel slot/text mismatch'

    def items(self,version,comp,items):
        p=self.panel;self.version(version);p.session.set_target(comp)
        p.comp_detail=self.matrix['comps'].get(version+':'+str(comp))
        ctrl=p.items;ctrl.reset();ctrl.active=True;ctrl.last_seen=time.monotonic()
        ctrl.observation={'image_size':[1920,1080],'cards':[{'box':[[i*200,500],[i*200+180,500],[i*200+180,900],[i*200,900]]} for i in range(len(items))]}
        ctrl.rows=[{'id':str(item['id']),'name':item['name'],'global':{'status':'pending'},
                   'comp':{'status':'pending' if comp else 'unpinned'},'holders':[],'holder_status':'pending'} for item in items]
        ctrl.start_queries();wait_jobs(p,self.qt);ctrl.last_seen=time.monotonic();ctrl.render()
        for index,item in enumerate(items):
            id_=str(item['id']);overlay=ctrl.overlays[index]
            assert plain(overlay.title.text())==item['name'],'item identity/slot'
            expected=self.record('/stats/equip',version)['expected'][id_]
            assert plain(overlay.global_line.text())=='全局 '+expected,('global item',id_,expected,plain(overlay.global_line.text()))
            if comp:
                row=self.record(f'/comp/{comp}/equips',version)
                expected=row['expected'][id_]
                if expected=='暂无数据':
                    fallback=next((r for r in self.records if r['request'].get('body',{}).get('version')==version
                        and r['request'].get('body',{}).get('filter',{}).get('rules',[{}])[0].get('type')=='equip'
                        and r['request']['body']['filter']['rules'][0]['targetId']==id_),None)
                    if fallback is None:raise MissingFixture(f'fallback {version} {id_}')
                    expected=fallback['expected']['item_by_comp'].get(comp,'暂无数据')
                assert plain(overlay.comp_line.text())=='本阵容 '+expected,('comp item',id_,expected,plain(overlay.comp_line.text()))
            else:assert overlay.comp_line.isHidden()
            holder=self.record(f'/comp/{comp}/equip-heroes',version,equipId=id_) if comp else self.record(f'/stats/equip/{id_}/heroes',version)
            expected=holder['expected']['holders']
            assert ctrl.rows[index]['holders']==expected,'holder identity/stat mismatch'
            for i,hero in enumerate(expected):
                count=hero['samples'];sample=f'{count/10000:.1f}万' if count>=10000 else f'{count/1000:.1f}千' if count>=1000 else str(count)
                assert plain(overlay.holder_lines[i][1].text())==f"{hero['name']} {hero['average']:.2f} {sample}局"
                candidates=[r for r in self.catalog['hero'] if str(r['id'])==hero['id']]
                if not candidates:candidates=[r for r in self.catalog['hero'] if r['name']==hero['name']]
                urls={r.get('picture','') for r in candidates};url=next(iter(urls)) if len(urls)==1 else ''
                assert overlay.urls[i]==url,'holder portrait identity mismatch'
                if url:
                    pix=QPixmap(24,24);pix.fill(QColor('#123456'));overlay.picture_loaded(url,pix)
                    assert overlay.holder_lines[i][0].pixmap().toImage().pixelColor(0,0).name()=='#123456'
            if not expected:assert plain(overlay.holder_lines[0][1].text())=='暂无足够样本'

    def run(self,domains=None):
        reports=[];domains=domains or {'explorer','hero','hex','items'}
        def check(domain,identity,fn):
            self.unmatched.clear();self.errors.clear()
            try:
                fn();assert not self.unmatched,self.unmatched;assert not self.errors,self.errors
                reports.append({'domain':domain,'case':identity,'status':'pass'})
            except Exception as exc:
                missing=[self.gap_keys[k] for k in self.unmatched if k in self.gap_keys]
                status=('source_unavailable' if 'source_unavailable' in missing else 'missing_fixture') if missing or isinstance(exc,MissingFixture) else 'mismatch'
                reports.append({'domain':domain,'case':identity,'status':status,'detail':str(exc)})
        for r in self.records:
            req=r['request'];path=req['path']
            if 'explorer' in domains and path in ['/comp/rank','/explorer/query']:
                for order in [0,1]:check('explorer',{'request':req,'order':order},lambda r=r,o=order:self.explorer(r,o))
            if 'hero' in domains and path.endswith('/hero-equips'):
                for form in ['heroEquips','hero3Equips']:
                    for kind in ['全部','成型装备','神器装备','光明武器','转职纹章','特殊装备']:
                        check('hero',{'request':req,'form':form,'kind':kind},lambda r=r,f=form,k=kind:self.hero(r,f,k))
        for v in self.matrix['versions']:
            for comp in [None,'112','120','100']:
                if 'hex' in domains:
                    for stage in ['2-1','3-2','4-2']:
                        for offset in range(0,9,3):check('hex',{'version':v,'comp':comp,'stage':stage,'offset':offset},lambda:self.hex(v,comp,stage,self.matrix['hexes'][offset:offset+3]))
                if 'items' in domains:
                    for offset in range(0,9,3):check('items',{'version':v,'comp':comp,'offset':offset},lambda:self.items(v,comp,self.matrix['items'][offset:offset+3]))
        return {'reference':self.fixture['reference'],'cases':reports,'gaps':self.gaps,
                'passed':sum(r['status']=='pass' for r in reports),'failed':sum(r['status']=='mismatch' for r in reports),
                'not_verified':sum(r['status'] not in ('pass','mismatch') for r in reports)}


def run(path,domains=None):
    replay=DisplayReplay(path)
    try:return replay.run(domains)
    finally:replay.close()
