"""Hidden packaged-app diagnostic. No game input and no network by default."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import traceback


def check_pinned_guide(panel):
    """Drive real pinned-guide widgets with a bounded offline detail response."""
    from unittest.mock import patch
    from PySide6.QtCore import QUrl
    pending=[]
    detail={'compId':'116','name':'验证阵容','heroes':[],'gameCode':'【阵容码】便携验证'}
    with patch.object(panel,'submit',side_effect=lambda pool,fn,done,failed=lambda _:None:pending.append((fn,done,failed))), \
         patch.object(panel.adapter,'comp',return_value={'data':detail}):
        panel.versions_loaded(['18.3','18.2a'])
        panel.select_comp('116')
        assert len(pending)==1,'Expected one comp detail request'
        fn,done,_=pending.pop();done(fn())
        assert panel.session.target=='116' and panel.copy_button.isEnabled(),'Pinned comp missing'
        assert panel.guide_empty.isHidden(),'Pinned guide incorrectly shows choose-comp prompt'
        assert not panel.guide_version.isHidden() and panel.web.isHidden(),'Historical guide state missing'
        assert '验证阵容' in panel.guide_version_title.text(),'Pinned name missing'
        panel.tabs.setCurrentIndex(3)
        panel.versions_loaded(['18.3','18.2a'])
        assert panel.tabs.currentIndex()==3,'Version response changed active tab'
        panel.tabs.setCurrentIndex(2)
        from bootstrap import STATE_DIR
        assert panel.grab().save(str(STATE_DIR/'portable-pinned-guide.png'))
        panel.guide_latest.click()
        assert panel.guide_version.isHidden() and not panel.web.isHidden(),'Latest guide entry failed'
        assert '18.3' in panel.guide_notice.text() and '18.2a' in panel.guide_notice.text(),'Guide version labels missing'
        assert not panel.guide_notice.isHidden(),'Cross-version guide explanation hidden'
        assert panel.adapter.patch==panel.session.patch=='18.2a' and panel.session.target=='116','Guide changed statistics scope'
        panel.versions_loaded(['18.2a','18.2'])
        url=QUrl('https://www.dataj.cc/comp/116')
        with patch.object(panel,'offline',False),patch.object(panel.web,'url',return_value=url),patch.object(panel.web,'setUrl') as navigate:
            panel.browse_comp();navigate.assert_called_once_with(url);navigate.reset_mock()
            panel.versions_loaded(['18.2a','18.2']);navigate.assert_not_called()
            panel.select_comp('116');navigate.assert_called_once_with(url)
        panel.unpin()
        assert not panel.guide_empty.isHidden() and panel.guide_version.isHidden() and panel.web.isHidden(),'Unpin left old guide visible'
        assert not panel.copy_button.isEnabled() and panel.guide_requested_url is None,'Unpin left old code or URL'
        panel.versions_loaded(['18.2a','18.2'])
        panel.select_comp('116');fn,done,_=pending.pop();done(fn())
        assert panel.guide_empty.isHidden() and panel.guide_version.isHidden() and not panel.web.isHidden(),'Matching-version guide failed'
        panel.unpin()


def check_resource_inputs(panel, qt):
    """Exercise actual condition widgets and DataJ bodies with local transport.

    The compact fixture is embedded so a packaged app needs no repository tests,
    private screenshots or work directory. It is an offline diagnostic scenario,
    not evidence of game OCR or automatic selection confirmation.
    """
    from unittest.mock import patch
    from copy import deepcopy
    import httpx
    from PySide6.QtCore import QPoint, QRect, Qt
    from dataj import DataJ
    from bootstrap import STATE_DIR
    catalog={
        'hero':[
            {'id':'14503','name':'阿木木','heroType':0,'price':4,'setId':'18'},
            {'id':'24503','name':'阿木木','heroType':0,'price':4,'setId':'18'},
        ],
        'hex':[{'id':'20778','name':'黑暗仪式','level':2,'descText':'【魔女】不再提供战利品！','setId':'18'}],
        'equip':[
            {'id':'2085','name':'光明版狂徒铠甲','type':'光明武器','descText':'获得36%最大生命值。','setId':'18'},
            {'id':'2091','name':'光明版强袭者的链枷','type':'光明武器','descText':'暴击提供持续5秒的10%伤害增幅，可叠加至多4次。','setId':'18'},
            {'id':'2078','name':'光明版适应性头盔','type':'光明武器','descText':'从所有来源中获得额外的30%法力值。','setId':'18'},
            {'id':'2092','name':'光明版秘法手套','type':'光明武器','descText':'每一回合：装备2件随机光明武器。','setId':'18'},
        ],
        'trait':[],
    }
    comp={'compId':'116','name':'便携验证阵容','sampleCount':200,'avgPlacement':4.0,'pickRate':1.12,
          'top4Rate':55.0,'topRate':15.0,'heroes':[],'traits':[]}
    detail={**comp,'gameCode':'【阵容码】便携免打字验证'}
    requests=[]

    def transport(request):
        path=request.url.path
        body=json.loads(request.content) if request.method=='POST' else None
        requests.append({'method':request.method,'path':path,'body':body,
                         'params':dict(request.url.params)})
        if path.endswith('/gamedata'):data=deepcopy(catalog)
        elif path.endswith('/explorer/query'):data={'comps':[deepcopy(comp)]}
        elif path.endswith('/comp/rank'):data=[deepcopy(comp)]
        elif path.endswith('/comp/116'):data=deepcopy(detail)
        elif path.endswith('/stats/hex'):data=[]
        else:raise AssertionError('Unplanned diagnostic endpoint: '+path)
        return httpx.Response(200,json={'code':200,'success':True,'data':data})

    class OfflineDataJ(DataJ):
        def __init__(self,*args,**kwargs):
            kwargs['db']=STATE_DIR/'portable-resource-cache.sqlite'
            kwargs['transport']=httpx.MockTransport(transport)
            super().__init__(*args,**kwargs)

        def request(self,path,body=None,ttl=900,**extra):
            # Still run the real serializer/validator, but do not let cache/rate
            # limits conceal the repeated chip HTTP body in this diagnostic.
            self.next_request=0
            return super().request(path,body=body,ttl=0,**extra)

    def run_job(pool,fn,done,failed=lambda _:None):
        done(fn())

    def last_rule(expected_kind,expected_id,version):
        posts=[r['body'] for r in requests if r['method']=='POST']
        assert posts,'No DataJ Explorer body produced'
        body=posts[-1]
        assert body['setId']==18 and body['version']==version,body
        assert body['filter']['combinator']=='and' and len(body['filter']['rules'])==1,body
        rule=body['filter']['rules'][0]
        assert rule['type']==expected_kind and rule['targetId']==expected_id,rule
        expected_name='阿木木' if expected_kind=='hero' and expected_id=='4503' else next(
            row['name'] for row in catalog[expected_kind] if row['id']==expected_id)
        assert rule['targetName']==expected_name,rule
        assert {key:rule[key] for key in ('starCount','hexRound','equipCarry','equipCount')}=={
            'starCount':'','hexRound':'','equipCarry':'','equipCount':''},rule
        assert rule['exclude'] is False and rule['enable'] is True and rule['nameMatch'] is False,rule
        return deepcopy(body)

    def bounds_and_screenshot(name):
        panel.tabs.setCurrentIndex(1);panel.resize(760,430)
        panel.ensurePolished();panel.layout().activate();qt.processEvents()
        shot=panel.grab()
        assert panel.width()==760 and panel.height()==430,('Compact panel grew',panel.size())
        ratio=shot.devicePixelRatio()
        assert abs(shot.width()/ratio-760)<1 and abs(shot.height()/ratio-430)<1,('Wrong screenshot canvas',shot.size(),ratio)
        bar=panel.browser.input_bar
        controls=[('read',bar.read),('search',panel.browser.search),('average_sort',panel.browser.avg_sort),
                  ('pick_rate_sort',panel.browser.pick_sort),('minimum_sample',panel.browser.sample),
                  ('target',panel.target_label),('copy_code',panel.copy_button),
                  ('close',panel.close_button),('collapse',panel.collapse_button),
                  ('overflow',bar.more),*((f'chip_{i}',chip) for i,chip in enumerate(bar.chips))]
        if not bar.current.isHidden():controls.append(('current_condition',bar.current))
        if not bar.clear.isHidden():controls.append(('clear_condition',bar.clear))
        if not bar.confirm.isHidden():controls.append(('confirm',bar.confirm))
        rectangles={}
        for label,widget in controls:
            assert not widget.isHidden(),label+' unexpectedly hidden'
            rect=QRect(widget.mapTo(panel,QPoint(0,0)),widget.size())
            assert panel.rect().contains(rect),(label,'outside compact panel',rect,panel.rect())
            assert rect.width()>0 and rect.height()>0,(label,'empty control',rect)
            rectangles[label]=[rect.x(),rect.y(),rect.width(),rect.height()]
        row=[QRect(*values) for values in rectangles.values()]
        assert all(not first.intersects(second) for index,first in enumerate(row) for second in row[index+1:]),'Compact controls overlap'
        assert panel.browser.scroll.horizontalScrollBar().maximum()==0,'Comp cards overflow horizontally'
        # Windows may render the 760x430 logical panel at 200% DPI. Preserve
        # native pixels and also save the requested logical-size QA preview.
        native=Path(name).with_stem(Path(name).stem+'-native')
        assert shot.save(str(STATE_DIR/native)),'Could not save native condition-input screenshot'
        preview=shot.scaled(760,430,Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.SmoothTransformation)
        assert preview.save(str(STATE_DIR/name)),'Could not save condition-input preview'
        return rectangles

    original_loaded=panel.catalog_loaded
    with patch('app.DataJ',OfflineDataJ),patch.object(panel,'submit',side_effect=run_job), \
         patch.object(panel,'catalog_loaded',side_effect=lambda result,offline=False:original_loaded(result,True)):
        panel.adapter=OfflineDataJ(patch='18.2a');panel.session.patch='18.2a'
        panel.versions_loaded(['18.3','18.2a'])
        original_loaded({'data':deepcopy(catalog)},True)
        bar=panel.browser.input_bar
        assert panel.browser.set_filter('hero',catalog['hero'][1],can_confirm=True)
        manual_body=last_rule('hero','4503','18.2a')
        assert not panel.selected_resources.events and not bar.chips,'A search was recorded as selected'
        assert not bar.confirm.isHidden(),'Explicit confirmation is unavailable'
        bar.confirm.click()
        assert len(panel.selected_resources.events)==len(bar.chips)==1,'Confirmation did not create one shortcut'
        bar.chips[0].click()
        assert last_rule('hero','4503','18.2a')==manual_body,'Chip changed the single-condition rule'
        assert len(panel.selected_resources.events)==1,'Chip click duplicated selected history'
        for entity in catalog['equip']:
            assert panel.browser.set_filter('equip',entity,can_confirm=True)
            assert last_rule('equip',entity['id'],'18.2a')
            bar.confirm.click()
        history=panel.selected_resources.events;game_id=panel.session.session_id
        assert len(history)==5 and len(bar.chips)==3 and len(bar.menu.actions())==2,'Shortcut overflow lost resources'
        # The overflow is another actual input surface, not a separate ID path.
        bar.menu.actions()[-1].trigger();last_rule('hero','4503','18.2a')
        assert panel.selected_resources.events==history,'Overflow query modified selected history'
        panel.select_comp('116')
        assert panel.session.target=='116' and panel.copy_button.isEnabled(),'Could not pin fixture comp'
        assert panel.selected_resources.events==history,'Pinning cleared selected history'
        panel.patch.setCurrentText('18.3');panel.change_patch()
        assert panel.adapter.patch==panel.session.patch=='18.3' and panel.session.target=='116','Version changed pinned scope'
        assert panel.session.session_id==game_id and panel.selected_resources.events==history,'Version change lost game resources'
        assert panel.comp_detail and panel.comp_detail['compId']=='116' and panel.copy_button.isEnabled(),'Version change did not restore fixed comp details'
        bar.chips[0].click();last_rule('equip','2092','18.3')
        panel.browser.set_filter('equip',catalog['equip'][1],can_confirm=True)
        rectangles_active=bounds_and_screenshot('portable-resource-inputs.png')
        # The one real input must carry exact candidate identity, with no old
        # second text box, apply button or guessed first completion.
        browser=panel.browser
        browser.search.setText('黑暗仪式')
        choices=[browser.suggestions.index(i,0) for i in range(browser.suggestions.rowCount())
                 if browser.suggestions.item(i).data(Qt.ItemDataRole.UserRole)[0]=='hex']
        assert len(choices)==1,'Unified entity suggestion missing or ambiguous'
        browser.choose_suggestion(choices[0]);last_rule('hex','20778','18.3')
        assert panel.selected_resources.events==history,'Searching a candidate changed selected history'
        assert not bar.confirm.isHidden(),'Manual suggestion lost explicit selected confirmation'
        rectangles_search=bounds_and_screenshot('portable-resource-inputs-search.png')
        panel.new_game()
        assert panel.session.session_id!=game_id and panel.session.target is None,'New game did not isolate pinned scope'
        assert not panel.selected_resources.events and not bar.chips and not bar.menu.actions(),'New game retained old resources'
        assert panel.browser.scope is None and bar.condition is None,'New game retained old input'
        assert bar.more.isHidden() and bar.resource_container.isHidden() and bar.condition_container.isHidden(),'New game retained resource or condition rows'
    return {'catalog_source':'embedded S18 identity fixture','network':'httpx.MockTransport only',
            'canonical_hero_id':'4503','versions':['18.2a','18.3'],'confirmed_events':len(history),
            'visible_shortcuts':3,'overflow_actions':2,'request_bodies':requests,
            'active_control_bounds':rectangles_active,'unified_search_control_bounds':rectangles_search,
            'logical_canvas':[760,430],'device_pixel_ratio':panel.devicePixelRatioF(),
            'screenshots':['portable-resource-inputs.png','portable-resource-inputs-search.png',
                           'portable-resource-inputs-native.png','portable-resource-inputs-search-native.png']}


def check_comp_hex_supplements():
    """Run the real adapter and stage supplement using embedded mock responses.

    No fixture or repository work files are required by this packaged check.
    These are synthetic transport responses containing reviewed stage values,
    not evidence of a live API request, game OCR or interaction. The normal
    adapter cache, request pacing and failure cooldown remain unchanged.
    """
    import tempfile
    import httpx
    from dataj import DataJ
    from hex_stats import lookup_comp_hexes
    from snapshot_stats import stage_stat

    reviewed={
        '20742':('四之力',4.23,13),
        '30668':('厨神阿福',4.54,13),
        '20708':('电火花 II',4.75,8),
    }
    entities=[(identity,row[0]) for identity,row in reviewed.items()]
    requests=[]

    def transport(request):
        path=request.url.path
        body=json.loads(request.content) if request.method=='POST' else None
        requests.append({'method':request.method,'path':path,'body':body,
                         'params':dict(request.url.params)})
        assert request.url.scheme=='https' and request.url.host=='www.dataj.cc',request.url
        if request.method=='GET' and path=='/api/web/comp/107/hexes':
            assert dict(request.url.params)=={'setId':'18','gameVersion':'18.3'},request.url
            data={'compId':'107','hexes':[]}
        else:
            assert request.method=='POST' and path=='/api/web/explorer/query',(request.method,path)
            assert body['version']=='18.3' and body['setId']==18,body
            assert body['filter']['combinator']=='and' and len(body['filter']['rules'])==1,body
            rule=body['filter']['rules'][0]
            identity=rule['targetId']
            assert identity in reviewed and rule['type']=='hex' and rule['hexRound']=='1',rule
            name,average,samples=reviewed[identity]
            assert rule['targetName']==name,rule
            assert rule['enable'] is True and rule['nameMatch'] is False and rule['exclude'] is False,rule
            assert {key:rule[key] for key in ('starCount','equipCarry','equipCount')}=={
                'starCount':'','equipCarry':'','equipCount':''},rule
            data={'comps':[{'compId':'107','name':'便携补查验证阵容',
                            'avgPlacement':average,'sampleCount':samples}]}
        return httpx.Response(200,json={'code':200,'success':True,'data':data})

    started=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='TFT-DataJ-hex-diagnostic-') as directory:
        adapter=DataJ(set_id=18,patch='18.3',db=Path(directory)/'cache.sqlite',
                      transport=httpx.MockTransport(transport))
        first=lookup_comp_hexes(adapter,'107','3-2',entities)
        assert len(requests)==4,'Expected one primary request and three exact stage supplements'
        second=lookup_comp_hexes(adapter,'107','3-2',entities)
        assert len(requests)==4,'Repeated supplement lookup bypassed the production cache'
        for result,cached in ((first,False),(second,True)):
            assert result['cached'] is cached and result['supplement_errors']=={},result
            assert result['supplemented_ids']==list(reviewed),result
            assert result['source'].split('?')[0]=='https://www.dataj.cc/api/web/comp/107/hexes',result
            assert set(result['supplement_sources'])==set(reviewed),result
            for identity,(_,average,samples) in reviewed.items():
                statistic=stage_stat(result['data'],identity,'3-2')
                assert statistic=={'status':'ok','avg_placement':average,
                                  'sample_count':samples,'stage':'3-2'},statistic
                source=result['supplement_sources'][identity]
                assert source['source']=='https://www.dataj.cc/api/web/explorer/query',source
                assert source['cached'] is cached and source['sample_count']==samples,source
                assert source['scope']=={'set_id':18,'patch':'18.3','comp':'107',
                                         'stage':'3-2','hex_id':identity},source
                assert source['fetched_at']==first['supplement_sources'][identity]['fetched_at'],source
    return {'evidence':'synthetic MockTransport diagnostic only; not live API, OCR or game validation',
            'scope':{'set_id':18,'patch':'18.3','comp':'107','stage':'3-2'},
            'primary_table_empty':True,'http_request_count':len(requests),
            'repeat_lookup_fully_cached':True,'normal_request_pacing_preserved':True,
            'elapsed_seconds':round(time.monotonic()-started,3),
            'statistics':[{'hex_id':identity,'name':name,'average':average,'samples':samples}
                          for identity,(name,average,samples) in reviewed.items()],
            'request_bodies':requests}


def check_identity_and_bug_archive():
    """Exercise new packaged modules with bounded synthetic evidence, offline."""
    import hashlib
    from PIL import Image
    from bootstrap import STATE_DIR
    from bug_cases import BugCaseStore
    from core import resolve_name
    from hex_catalog import canonical_hex_catalog
    common={'name':'别再错过','level':1,'setId':'18',
            'icon':'https://img.dataj.cc/images/hex/missedconnections1.png',
            'descText':'获得每个1费弈子各1个。'}
    aliases=[{**common,'id':'1625'},{**common,'id':'10784'}]
    stats=[{'hexId':1625,'name':common['name'],'icon':common['icon'],
            'roundStats':[{'round':1,'roundLabel':'3-2','sampleCount':100,'avgPlacement':4.27}]}]
    projected=canonical_hex_catalog(aliases,stats,set_id=18)
    identity=resolve_name([common['name']]*3,projected)
    assert identity['status']=='resolved' and identity['id']=='1625',identity
    different=[aliases[0],{**aliases[1],'level':2,'descText':'另一种效果。'}]
    assert len(canonical_hex_catalog(different,stats,set_id=18))==2,'Different variants merged'
    # Use a distinct diagnostic directory. Never write a simulated failure to
    # the user's production archive or manufacture an expected.json oracle.
    directory=STATE_DIR/'portable-bug-cases'
    store=BugCaseStore(directory)
    image=Image.new('RGB',(1280,720),'#193a20')
    observation={'scene':'choice_unresolved','round':'3-2','cards':[
        {'slot':i,'resolution':{'status':'unrecognized','readings':['待核对']}}
        for i in range(3)]}
    context={'set_id':18,'patch':'18.3','domain':'hex','source':'diagnostic',
             'frame_scope':'full_game','target':None}
    saved=store.save(image,observation,reason='hex_unresolved',context=context,
                     evidence={'failure_simulated':True,'catalog':{'hex':aliases}})
    assert saved['status'] in ('saved','duplicate'),saved
    path=Path(saved['path']);before=(path/'frame.png').read_bytes()
    metadata=json.loads((path/'case.json').read_text(encoding='utf-8'))
    assert metadata['status']=='pending_review' and not (path/'expected.json').exists(),metadata
    assert metadata['image']['sha256']==hashlib.sha256(before).hexdigest()
    with Image.open(path/'frame.png') as restored:
        assert restored.size==image.size and restored.convert('RGB').tobytes()==image.tobytes()
    duplicate=store.save(Image.new('RGB',image.size,'red'),observation,
                         reason='hex_unresolved',context=context)
    assert duplicate['status']=='duplicate' and (path/'frame.png').read_bytes()==before,duplicate
    return {'canonical_hex_id':identity['id'],'different_variants_preserved':True,
            'archive_status':metadata['status'],'duplicate_preserves_first_frame':True,
            'evidence':'synthetic diagnostic only; no game screenshot or upload'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--diagnose',action='store_true')
    parser.add_argument('--online',action='store_true')
    parser.add_argument('--image',type=Path)
    parser.add_argument('--catalog',type=Path)
    parser.add_argument('--condition-image',type=Path,help='Optional original 4K giant-belt detail regression')
    parser.add_argument('--explorer-fixture',type=Path)
    parser.add_argument('--data-fixture',type=Path)
    parser.add_argument('--forbid-path',type=Path)
    parser.add_argument('--output',type=Path,help='Use an isolated diagnostic state/output directory')
    args=parser.parse_args()
    if args.output:
        import bootstrap
        bootstrap.STATE_DIR=args.output.resolve()
        bootstrap.STATE_DIR.mkdir(parents=True,exist_ok=True)
    from bootstrap import FROZEN,RESOURCE_DIR,STATE_DIR
    report={'frozen':FROZEN,'resource_dir':str(RESOURCE_DIR),'state_dir':str(STATE_DIR),'checks':[]}
    qt=panel=None
    errors=[]
    def unhandled(kind,value,tb):
        errors.append(str(value));sys.__excepthook__(kind,value,tb)
    sys.excepthook=unhandled
    try:
        from app import QApplication,Companion
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QIcon
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtNetwork import QSslSocket
        from PIL import Image,ImageDraw,ImageFont
        from ocr_baseline import build_engine
        qt=QApplication([]);qt.setQuitOnLastWindowClosed(False)
        icon=QIcon(str(RESOURCE_DIR/'assets/app-icon.ico'))
        assert not icon.isNull(),'Bundled application icon missing'
        sizes=sorted((size.width(),size.height()) for size in icon.availableSizes())
        assert {(16,16),(32,32),(48,48),(256,256)}.issubset(sizes),'Application icon sizes missing'
        qt.setWindowIcon(icon)
        report['app_icon']={'sizes':sizes,'bundled':True}
        panel=Companion(offline=True,offline_catalog={'hex':[],'hero':[],'equip':[],'trait':[]})
        panel.timer.stop();panel.hide()
        assert panel.grab().save(str(STATE_DIR/'portable-ui.png'))
        assert (RESOURCE_DIR/'assets/refresh-glyph.png').is_file()
        assert not QIcon(str(RESOURCE_DIR/'assets/collapse-panel.svg')).isNull(),'Collapse icon missing'
        assert (RESOURCE_DIR/'chevron-down.svg').is_file()
        report['checks'].append('application widgets and bundled UI assets')
        report['checks'].append('multi-size application icon and Qt window icon')
        check_pinned_guide(panel)
        report['checks'].append('pinned guide versions, latest entry, retry, scope and unpin regression')
        report['resource_inputs']=check_resource_inputs(panel,qt)
        report['checks'].append('packaged canonical single-condition inputs, explicit selection, chips, overflow, pinned version switch and new game')
        report['comp_hex_supplements']=check_comp_hex_supplements()
        report['checks'].append('packaged exact-stage comp hex supplements and repeated lookup cache via embedded mock transport')
        report['identity_and_bug_archive']=check_identity_and_bug_archive()
        report['checks'].append('packaged hex alias identity, variant rejection and lossless pending bug archive deduplication')
        if args.explorer_fixture:
            fixture=json.loads(args.explorer_fixture.read_text(encoding='utf-8'))
            browser=panel.browser
            # Feed captured data through the packaged UI without issuing a query.
            browser.blockSignals(True)
            browser.set_catalog({'hex':[fixture['entity']]})
            browser.set_filter('hex',fixture['entity'])
            browser.blockSignals(False)
            browser.set_result(fixture['comps'],fixture['version'])
            actual=[card.comp_id for card in browser.cards]
            assert actual==['120','100'],f'Explorer minimum sample regression: {actual}'
            report['explorer']={'entity':fixture['entity']['name'],'comp_ids':actual}
            panel.tabs.setCurrentIndex(1)
            assert panel.grab().save(str(STATE_DIR/'portable-explorer.png'))
            report['checks'].append('dark ritual explorer excludes samples below 50')
        if args.data_fixture:
            from display_audit import run
            result=run(args.data_fixture)
            (STATE_DIR/'display-replay.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
            report['data_display']={k:result[k] for k in ['passed','failed','gaps']}
            assert result['failed']==0 and result['not_verified']==0 and not result['gaps'],report['data_display']
            assert {r['domain'] for r in result['cases'] if r['status']=='pass'}=={'explorer','hero','hex','items'},'Missing display domain'
            report['checks'].append('packaged explorer, hex, item overlays and hero equipment replay')
        panel.vision.engine,report['models']=build_engine()
        test_image=Image.new('RGB',(200,64),'black')
        font=ImageFont.truetype(str(Path(os.environ['WINDIR'])/'Fonts/arialbd.ttf'),42)
        ImageDraw.Draw(test_image).text((20,2),'2-1',font=font,fill='white')
        stage=panel.vision.read_round_crop(test_image)
        assert stage=='2-1',f'Bundled OCR stage: {stage}'
        report['checks'].append('bundled OCR models and ONNX CPU inference')
        page=QWebEngineView();loaded=[];page.loadFinished.connect(loaded.append)
        page.setHtml('<html><body>Companion browser diagnostic</body></html>',QUrl('about:blank'))
        end=time.monotonic()+15
        while not loaded and time.monotonic()<end:qt.processEvents();time.sleep(.01)
        assert loaded==[True],f'WebEngine load failed: {loaded}'
        report['checks'].append('WebEngine helper and local page')
        assert QSslSocket.activeBackend()=='schannel',QSslSocket.availableBackends()
        report['checks'].append('Windows native TLS backend')
        if args.online:
            from dataj import DataJ
            from comp_browser import Portraits
            catalog=DataJ().catalog()['data']
            assert catalog.get('hex') and catalog.get('equip')
            store=Portraits(qt)
            url='https://img.dataj.cc/images/s18/hero/s18_head_sivir.png'
            store.request(url);end=time.monotonic()+12
            while store.pending and time.monotonic()<end:qt.processEvents();time.sleep(.01)
            assert url in store.images,'Portrait HTTPS failed'
            report['checks'].append('DataJ HTTPS and real hero portrait')
        if args.image:
            if not args.catalog:parser.error('--image requires --catalog')
            catalog=json.loads(args.catalog.read_text(encoding='utf-8'))['data']
            with Image.open(args.image) as frame:
                result=panel.vision.analyze_fast(frame.convert('RGB'),catalog['hex'])
            report['real_frame']={'stage':result['round'],'ids':[c['resolution'].get('id') for c in result['cards']]}
            assert result['scene']=='choice_candidates' and all(report['real_frame']['ids']),report['real_frame']
            report['checks'].append('external real game frame recognition')
        if args.condition_image:
            if not args.catalog:parser.error('--condition-image requires --catalog')
            from condition_reader import ConditionReader
            from entity_identity import EntityResolver
            catalog=json.loads(args.catalog.read_text(encoding='utf-8'))['data']
            with Image.open(args.condition_image) as frame:
                result=ConditionReader(panel.vision,EntityResolver(catalog)).read(frame.convert('RGB'))
            entity=result.get('entity') or {}
            assert result['status']=='resolved' and entity.get('kind')=='equip' and entity.get('id')=='1007',result
            assert entity.get('name')=='巨人腰带' and result['records_selected'] is False,result
            report['real_condition']={'kind':entity['kind'],'id':entity['id'],'name':entity['name'],
                                      'layout':result['evidence']['layout']}
            report['checks'].append('external original 4K equipment primary-title recognition, not wearer')
        if args.forbid_path:
            forbidden=args.forbid_path.resolve()
            dependencies=[Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,'__file__',None)]
            assert not any(p.is_relative_to(forbidden) for p in dependencies),'Source workspace imported'
            assert not any(Path(p).resolve().is_relative_to(forbidden) for p in sys.path),'Source workspace on search path'
            report['checks'].append('no source workspace modules or search paths')
        assert not errors,errors
        page.close();page.deleteLater();qt.processEvents()
        report['status']='passed'
    except Exception:
        report['status']='failed';report['error']=traceback.format_exc()
        traceback.print_exc()
    finally:
        if panel:panel.shutdown()
        if qt:qt.processEvents()
        (STATE_DIR/'portable-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False),flush=True)
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
