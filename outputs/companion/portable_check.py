"""Hidden packaged-app diagnostic. No game input and no network by default."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import time
import traceback


def load_recognition_fixture(path):
    """Read a hash-bound external oracle without modifying any of its inputs.

    Relative asset paths are resolved beside the manifest. This optional input
    is supplied separately from the portable archive, never bundled as data.
    """
    path=Path(path).resolve()
    fixture=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(fixture,dict):
        raise ValueError('Recognition fixture must be an object')
    if fixture.get('schema_version')!=1:
        raise ValueError('Recognition fixture schema_version must be 1')
    def asset(descriptor,label):
        if not isinstance(descriptor,dict) or not isinstance(descriptor.get('path'),str) or not descriptor['path']:
            raise ValueError(label+' requires a path')
        digest=descriptor.get('sha256')
        if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError(label+' requires a lowercase SHA-256')
        source=(path.parent/descriptor['path']).resolve()
        content=source.read_bytes()
        if hashlib.sha256(content).hexdigest()!=digest:
            raise ValueError(label+' SHA-256 mismatch')
        return {'path':source,'sha256':digest,'content':content}
    catalog=asset(fixture.get('catalog'),'catalog')
    data=json.loads(catalog['content'].decode('utf-8'))
    if not isinstance(data,dict) or not isinstance(data.get('data'),dict) or not isinstance(data['data'].get('hex'),list):
        raise ValueError('Recognition catalog requires data.hex list')
    cases=fixture.get('cases')
    if not isinstance(cases,list) or not cases:
        raise ValueError('Recognition fixture requires nonempty cases')
    reviewed=[];identities=set()
    for case in cases:
        if not isinstance(case,dict) or not isinstance(case.get('id'),str) or not case['id'] or case['id'] in identities:
            raise ValueError('Recognition case IDs must be nonempty and unique')
        identities.add(case['id'])
        expected=case.get('expected')
        if not isinstance(expected,dict) or set(expected)!= {'scene','round','ids'}:
            raise ValueError(case['id']+' requires exact expected scene, round and ids')
        if any(not isinstance(expected[key],str) or not expected[key] for key in ('scene','round')):
            raise ValueError(case['id']+' requires nonempty expected scene and round')
        if not isinstance(expected['ids'],list) or len(expected['ids'])!=3 or any(
                not isinstance(identity,str) or not identity for identity in expected['ids']):
            raise ValueError(case['id']+' requires exactly three expected string IDs')
        reviewed.append({'id':case['id'],'frame':asset(case.get('frame'),case['id']+' frame'),
                         'expected':expected})
    return {'catalog':catalog,'hexes':data['data']['hex'],'cases':reviewed}


def check_recognition_fixture(vision,path):
    """Replay real full frames against independently frozen exact expectations."""
    from PIL import Image
    report={'status':'failed','cases':[]}
    try:
        fixture=load_recognition_fixture(path)
    except (OSError,ValueError,TypeError) as error:
        report['error']=str(error)
        return report
    report['catalog_sha256']=fixture['catalog']['sha256']
    for case in fixture['cases']:
        outcome={'id':case['id'],'frame_sha256':case['frame']['sha256'],
                 'expected':case['expected'],'checks':[],'status':'failed'}
        report['cases'].append(outcome)
        try:
            with Image.open(io.BytesIO(case['frame']['content'])) as frame:
                result=vision.analyze_fast(frame.convert('RGB'),fixture['hexes'])
            actual={'scene':result.get('scene'),'round':result.get('round'),
                    'ids':[card.get('resolution',{}).get('id') for card in result.get('cards',[])],
                    'slots':[card.get('slot') for card in result.get('cards',[])],
                    'resolution_statuses':[card.get('resolution',{}).get('status') for card in result.get('cards',[])]}
            outcome['actual']=actual
            outcome['mismatches']=[key for key in ('scene','round','ids') if actual[key]!=case['expected'][key]]
            if actual['resolution_statuses']!=['resolved']*3:outcome['mismatches'].append('resolved_cards')
            if actual['slots']!=[0,1,2]:outcome['mismatches'].append('ordered_slots')
            outcome['checks']=[name for key,name in (('scene','scene'),('round','round'),('ids','ordered_three_ids'),
                                                    ('resolved_cards','resolved_cards'),('ordered_slots','ordered_slots'))
                               if key not in outcome['mismatches']]
            outcome['status']='failed' if outcome['mismatches'] else 'passed'
        except Exception as error:
            outcome['error']=str(error)
    if all(case['status']=='passed' for case in report['cases']):report['status']='passed'
    return report


def _run_diagnostic_job(pool,fn,done,failed=None,*,is_current=None,cancelled=None):
    """Run diagnostic work synchronously with the submit cancellation contract.

    Unexpected source/callback errors still propagate to the diagnostic's
    existing failure report rather than being concealed by this test double.
    """
    if is_current is not None and not is_current():
        if cancelled:cancelled()
        return
    done(fn())


def check_pinned_guide(panel):
    """Drive real pinned-guide widgets with a bounded offline detail response."""
    from unittest.mock import patch
    from PySide6.QtCore import QUrl
    pending=[]
    detail={'compId':'116','name':'验证阵容','heroes':[],'gameCode':'【阵容码】便携验证'}
    def queue_job(pool,fn,done,failed=None,*,is_current=None,cancelled=None):
        pending.append(lambda:_run_diagnostic_job(pool,fn,done,failed,
            is_current=is_current,cancelled=cancelled))
    with patch.object(panel,'submit',side_effect=queue_job), \
         patch.object(panel.adapter,'comp',return_value={'data':detail}):
        panel.versions_loaded(['18.3','18.2a'])
        panel.select_comp('116')
        assert len(pending)==1,'Expected one comp detail request'
        pending.pop()()
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
        panel.select_comp('116');pending.pop()()
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
    with patch('app.DataJ',OfflineDataJ),patch.object(panel,'submit',side_effect=_run_diagnostic_job), \
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
            'repeat_lookup_fully_cached':True,'current_group_bounded_parallel_supplements':True,
            'elapsed_seconds':round(time.monotonic()-started,3),
            'statistics':[{'hex_id':identity,'name':name,'average':average,'samples':samples}
                          for identity,(name,average,samples) in reviewed.items()],
            'request_bodies':requests}


def check_hex_prewarm():
    """Exercise full prewarm and pin-lifetime caching using synthetic HTTP only."""
    import sqlite3
    import tempfile
    from contextlib import closing
    import httpx
    from dataj import DataJ
    from hex_prewarm import HexPrewarm
    from hex_stats import lookup_comp_hexes
    from snapshot_stats import stage_stat

    reviewed={'20742':('四之力',4.23,13),'30668':('厨神阿福',4.54,13),
              '20708':('电火花 II',4.75,8)}
    empty=('10616','拥抱 II')
    requests=[]
    def transport(request):
        requests.append(request)
        if request.url.path.endswith('/stats/hex'):
            data=[{'hexId':identity,'name':name,'roundStats':[{
                'round':1,'roundLabel':'3-2','avgPlacement':4.5,'sampleCount':100}]}
                for identity,name in [(identity,row[0]) for identity,row in reviewed.items()]+[empty]]
        elif request.url.path.endswith('/comp/107/hexes'):
            data={'compId':'107','hexes':[]}
        else:
            assert request.url.path=='/api/web/explorer/query',request.url
            body=json.loads(request.content);rule=body['filter']['rules'][0]
            assert (body['setId'],body['version'],rule['hexRound'])==(18,'18.3','1'),body
            identity=rule['targetId']
            if identity==empty[0]:data={'comps':[]}
            else:
                name,average,samples=reviewed[identity]
                assert rule['targetName']==name,rule
                data={'comps':[{'compId':'107','name':'便携预读测试阵容',
                                'avgPlacement':average,'sampleCount':samples}]}
        return httpx.Response(200,json={'code':200,'success':True,'data':data})

    with tempfile.TemporaryDirectory(prefix='TFT-DataJ-prewarm-diagnostic-') as directory:
        adapter=DataJ(patch='18.3',db=Path(directory)/'cache.sqlite',
                      transport=httpx.MockTransport(transport))
        warm=HexPrewarm(adapter,'107')
        try:
            warm.start('3-2')
            assert warm.wait(15),'Pinned background prewarm did not finish'
            assert warm.snapshot()['status']=='complete',warm.snapshot()
            assert len(requests)==6,'Expected two main tables and four exact candidate queries'
            with closing(sqlite3.connect(adapter.db,isolation_level=None)) as connection:
                connection.execute('UPDATE cache SET fetched=0')
            before=len(requests)
            assert warm.hexes()['cached'] and warm.hexes('107')['cached']
            result=lookup_comp_hexes(warm,'107','3-2',[(identity,row[0]) for identity,row in reviewed.items()])
            statistics=[]
            for identity,(_,average,samples) in reviewed.items():
                actual=stage_stat(result['data'],identity,'3-2')
                assert actual=={'status':'ok','avg_placement':average,'sample_count':samples,'stage':'3-2'},actual
                assert result['supplement_sources'][identity]['cached']
                statistics.append({'hex_id':identity,'average':average,'samples':samples})
            for _ in range(2):
                negative=lookup_comp_hexes(warm,'107','3-2',[empty])
                assert not negative['supplement_errors'] and not negative['pending_ids'],negative
                assert stage_stat(negative['data'],empty[0],'3-2')['status']=='missing_or_ambiguous_entity'
            assert len(requests)==before,'Pin-lifetime result unexpectedly queried expired disk cache'
            return {'evidence':'synthetic MockTransport; no live API or game operation',
                    'scope':{'set_id':18,'patch':'18.3','comp':'107','stage':'3-2'},
                    'retained_after_disk_expiry':True,'empty_result_retained':True,
                    'foreground_http_count':len(requests)-before,'background_http_count':before,
                    'statistics':statistics}
        finally:
            warm.cancel();assert warm.wait(5),'Background worker did not stop'


def check_retry_limits():
    """Prove persistent failures stop in the frozen EXE without live HTTP."""
    import tempfile
    from unittest.mock import patch
    import httpx
    from dataj import DataJ
    from hex_prewarm import HexPrewarm

    class DelayedWake:
        def __init__(self, interval, function):
            self.interval, self.function = interval, function
            self.daemon = False

        def start(self):
            pass

        def cancel(self):
            pass

        def fire(self):
            # Deliver even obsolete/cancelled callbacks, as the OS may do.
            self.function()

    cases = []
    for fault in ('http_503', 'invalid_200'):
        clock, wakes, requests = [1000.0], [], []

        def timer(interval, function):
            wake = DelayedWake(interval, function)
            wakes.append(wake)
            return wake

        def response(request):
            requests.append(request)
            return (httpx.Response(503) if fault == 'http_503' else
                    httpx.Response(200, json={'success': True, 'code': 200, 'data': {}}))

        with tempfile.TemporaryDirectory(prefix='TFT-DataJ-retry-diagnostic-') as directory:
            adapter = DataJ(patch='18.3', db=Path(directory)/'cache.sqlite',
                            transport=httpx.MockTransport(response))
            with patch('hex_prewarm.time.monotonic', side_effect=lambda: clock[0]), \
                    patch('hex_prewarm.threading.Timer', side_effect=timer):
                warm = HexPrewarm(adapter, '107')
                try:
                    warm.start('3-2')
                    for attempt in range(3):
                        assert warm.wait(2), 'Retry diagnostic worker did not finish'
                        assert len(requests) == attempt+1, 'Unexpected persistent-failure request count'
                        if attempt < 2:
                            assert len(wakes) == attempt+1, 'Missing bounded delayed wake'
                            assert wakes[-1].interval >= 60, 'Retry bypassed the source delay'
                            clock[0] += wakes[-1].interval+1
                            wakes[-1].fire()
                    state = warm.snapshot()
                    assert len(wakes) == 2 and not state['retry_pending'], \
                        'Persistent source continued scheduling after three failures'
                    assert state['retry_exhausted'] and state['failure_count'] == 3, state
                    before = len(requests)
                    clock[0] += 10000
                    for wake in wakes:
                        wake.fire()
                    for _ in range(3):
                        warm.start('3-2')
                        warm.prioritize('4-2')
                        assert warm.wait(2), 'Repeated start did not settle'
                    assert len(requests) == before and len(wakes) == 2, \
                        'Old callbacks or ordinary start bypassed exhausted retries'
                    cases.append({'fault': fault, 'http_request_count': len(requests),
                                  'scheduled_wakes': len(wakes),
                                  'minimum_retry_seconds': min(w.interval for w in wakes),
                                  'late_callbacks_and_restarts_stopped': True})
                finally:
                    warm.cancel()
                    assert warm.wait(2), 'Retry diagnostic worker did not stop'
    return {'status': 'passed',
            'evidence': 'temporary SQLite, MockTransport and controlled delayed wakes; no live outage or minute-long waiting',
            'cases': cases}


def check_cache_recovery():
    """Prove durable bad-cache recovery using temporary SQLite and synthetic HTTP."""
    from contextlib import closing
    import sqlite3
    import tempfile
    import httpx
    from dataj import DataJ,SourceError

    good={'hex':[{'id':'1023','name':'应急护甲 I','setId':'18','level':1,
                   'descText':'便携缓存离线诊断'}],'hero':[],'equip':[],'trait':[]}
    requests=[]
    def respond(request):
        assert request.method=='GET' and request.url.path=='/api/web/gamedata',request.url
        assert dict(request.url.params)=={'setId':'18'},request.url
        requests.append(request)
        assert len(requests)<=2,'Cache diagnostic issued unexpected HTTP'
        data=good if len(requests)==1 else {'hex':[None]}
        return httpx.Response(200,json={'success':True,'code':200,'data':data})

    with tempfile.TemporaryDirectory(prefix='TFT-DataJ-cache-diagnostic-') as directory:
        db=Path(directory)/'cache.sqlite';transport=httpx.MockTransport(respond)
        adapter=DataJ(patch='18.4',db=db,transport=transport)
        # Existing durable format, constructed independently of private helpers.
        key=json.dumps(['GET','/gamedata',{'setId':18},None],sort_keys=True,ensure_ascii=False)
        with closing(sqlite3.connect(db,isolation_level=None)) as connection:
            connection.execute('INSERT INTO cache VALUES(?,?,?)',
                               (key,time.time(),json.dumps({'hex':'legacy-invalid'})))
        repaired=adapter.catalog()
        assert repaired['data']==good and repaired['cached'] is False,'Legacy bad directory was reused'
        assert len(requests)==1,'Expected one real adapter source recovery'
        restarted=DataJ(patch='18.4',db=db,transport=transport)
        hit=restarted.catalog()
        assert hit['data']==good and hit['cached'] is True,'Fresh adapter did not reuse good durable data'
        assert len(requests)==1,'Fresh adapter unexpectedly sent HTTP'
        expired=repaired['fetched_at']-7200
        with closing(sqlite3.connect(db,isolation_level=None)) as connection:
            connection.execute('UPDATE cache SET fetched=? WHERE key=?',(expired,key))
        try:restarted.catalog()
        except SourceError:pass
        else:raise AssertionError('A malformed new HTTP 200 directory was accepted')
        assert len(requests)==2,'Expected exactly one failed source refresh'
        # A further adapter proves last-good persistence rather than an object cache.
        final=DataJ(patch='18.4',db=db,transport=transport)
        before=len(requests);fallback=final.catalog_snapshot()
        assert fallback and fallback['data']==good,'Bad refresh replaced the last good directory'
        assert fallback['cached'] is True and fallback['stale'] is True,'Expired directory not labelled local/stale'
        assert fallback['fetched_at']==expired,'Failed refresh changed last-good timestamp'
        assert len(requests)==before,'Local directory fallback issued HTTP'
        return {'status':'passed','evidence':'synthetic MockTransport and temporary SQLite only; no live API/user cache',
                'scope':{'set_id':18,'patch':'18.4'},'http_request_count':len(requests),
                'legacy_bad_cache_repaired':True,'fresh_adapter_hit':True,
                'bad_refresh_rejected':True,'last_good_preserved':True,
                'local_fallback_stale':True,'snapshot_http_request_count':len(requests)-before}


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
    parser.add_argument('--recognition-fixture',type=Path,help='External hash-bound exact scene/round/three-ID replay manifest')
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
        from app_version import APP_VERSION
        assert panel.app_version.text()==f'v{APP_VERSION}','Application version label disagrees with release identity'
        assert not panel.app_version.isHidden(),'Application version label hidden'
        assert panel.app_version.geometry().top()>panel.patch.geometry().bottom(),'Application version overlaps statistics selector'
        assert panel.app_version.fontMetrics().horizontalAdvance(panel.app_version.text())<=panel.app_version.contentsRect().width(),'Application version clipped'
        if FROZEN:
            manifest=json.loads((Path(sys.executable).parent/'manifest.json').read_text(encoding='utf-8'))
            assert manifest['version']==APP_VERSION,'Package version disagrees with application version'
        report['app_version']=APP_VERSION
        report['checks'].append('visible application version below statistics selector matches release and package identity')
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
        report['hex_prewarm']=check_hex_prewarm()
        report['retry_limits']=check_retry_limits()
        report['checks'].append('packaged persistent HTTP/invalid-data failures stop after three prewarm failures')
        report['checks'].append('packaged full pinned hex prewarm and positive/empty session cache beyond disk expiry')
        report['cache_recovery']=check_cache_recovery()
        report['checks'].append('packaged durable bad-cache recovery, fresh-adapter hit and last-good directory preservation')
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
        if args.recognition_fixture:
            report['recognition_replay']=check_recognition_fixture(panel.vision,args.recognition_fixture)
            assert report['recognition_replay']['status']=='passed',report['recognition_replay']
            report['checks'].append('external reviewed exact scene, round and ordered three-ID recognition replay')
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
