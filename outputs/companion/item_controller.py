"""Item-choice lifecycle sharing the application's capture/OCR/network queues."""
from collections import deque
import time
from item_vision import item_boxes, item_signature, same_item_text, analyze_items, capture_item_region
from item_stats import item_stat, fallback_stat, best_holders, query_key
from item_overlay import ItemOverlay
from diagnostics import record
import win_capture as win


def nearby_boxes(current,previous,image_size):
    tolerance=max(4,image_size[0]/240)
    return (len(current)==len(previous) and bool(current)
            and all(max(abs(a-b) for a,b in zip(x,y))<=tolerance for x,y in zip(current,previous)))


def inspect_items(image,reference_boxes=()):
    """Pure pixel work, called on the serialized capture worker in live use."""
    boxes=item_boxes(image)
    # Animated outlines can move without moving the actual title. Keep verified
    # crop coordinates for small box noise; changed title pixels still invalidate.
    signature_boxes=reference_boxes if nearby_boxes(boxes,reference_boxes,image.size) else boxes
    return boxes,item_signature(image,signature_boxes)


class ItemController:
    def __init__(self,panel):
        self.panel=panel
        self.overlays=[ItemOverlay(panel.browser.portraits) for _ in range(5)]
        self.cache={};self.warming=set();self.generation=0
        self.active=False;self.recognizing=False;self.probing=False
        self.observation=None;self.rows=[];self.signature=None;self.boxes=[]
        self.last_probe=float('-inf');self.last_seen=0;self.next_ocr=0
        self.retries=0;self.last_frame=None;self.tasks=deque()
        self.probe_started=None
        self.query_inflight=None

    def token(self):return self.generation,self.panel.session.token(),id(self.panel.adapter)

    def accepts(self,token):return token==self.token()

    def hide(self):
        for overlay in self.overlays:overlay.hide()

    def reset(self):
        self.generation+=1;self.active=False;self.observation=None;self.rows=[]
        self.signature=None;self.boxes=[];self.tasks.clear();self.last_frame=None;self.retries=0
        self.probe_started=None;self.last_seen=0
        self.query_inflight=None
        self.hide()

    def available(self):
        p=self.panel
        return bool(p.binding and not p.panel_open() and win.foreground_root()==p.binding.hwnd)

    def cached(self,key):
        value=self.cache.get(key)
        return value if value and 0<=time.time()-value['fetched_at']<900 else None

    def prewarm(self,comp=None):
        p=self.panel;adapter=p.adapter;key=query_key(adapter,'table',comp)
        if p.offline or key in self.warming or self.cached(key):return
        self.warming.add(key)
        def done(result):
            self.warming.discard(key)
            if adapter is p.adapter:self.cache[key]=result
        p.submit(p.network,lambda:adapter.item_stats(comp),done,lambda _:self.warming.discard(key))

    def tick(self):
        p=self.panel;now=time.monotonic()
        if not self.available():self.hide();return
        if self.active and not self.fresh(now):self.hide()
        interval=.5 if self.active else 2.0
        if (not self.available() or not p.catalog or self.probing or p.capture_pending
            or self.recognizing or p.ocr_busy or p.stage_probe_pending
            or (not p.automatic.isChecked() and not self.active)
            or now-self.last_probe<interval):return
        self.last_probe=now;self.probing=True;self.probe_started=now;p.capture_pending=True
        token=self.token();binding=p.binding;reference_boxes=tuple(self.boxes)
        def done(result):
            self.probing=False;self.probe_started=None;p.capture_pending=False
            if self.accepts(token) and self.available():
                image,current,prepared,frame_time=result
                self.ingest(image,current,prepared=prepared,frame_time=frame_time)
        def failed(_):
            self.probing=False;self.probe_started=None;p.capture_pending=False
            if self.accepts(token):self.reset()
        def capture():
            image,current=capture_item_region(binding)
            frame_time=time.monotonic()
            return image,current,inspect_items(image,reference_boxes),frame_time
        p.submit(p.capture_pool,capture,done,failed)

    def ingest(self,image,binding,force=False,prepared=None,frame_time=None):
        """Return True when this frame belongs to the item scene investigation."""
        p=self.panel
        frame_time=time.monotonic() if frame_time is None else frame_time
        boxes,signature=inspect_items(image,self.boxes) if prepared is None else prepared
        if not boxes:
            if self.active or self.boxes:self.reset()
            return False
        aligned=nearby_boxes(boxes,self.boxes,image.size)
        signature_boxes=list(self.boxes) if aligned else boxes
        same=aligned and same_item_text(signature,self.signature)
        self.last_frame=image
        if same and self.active:
            self.last_seen=max(self.last_seen,frame_time)
            if self.observation is not None and hasattr(p,'selections'):
                p.selections.observe(self.observation,image.size,binding,frame_time)
            if (all(r['id'] for r in self.rows)
                or (not force and (self.retries>=2 or time.monotonic()<self.next_ocr))):
                self.render()
                if force:self.retry_failed_queries()
                return True
        if not same:
            self.reset();self.last_frame=image
        self.boxes=signature_boxes;self.signature=signature
        self.last_seen=max(self.last_seen,frame_time)
        if self.recognizing or p.ocr_busy or p.stage_probe_pending:return True
        if not force and time.monotonic()<self.next_ocr:return True
        self.recognizing=True;p.ocr_busy=True
        token=self.token();catalog=p.catalog.get('equip',[])
        self.next_ocr=time.monotonic()+2
        if same:self.retries+=1
        def done(observation):
            self.recognizing=False;p.ocr_busy=False
            if not self.accepts(token) or not self.available():return
            if observation['scene']!='item_candidates':
                # A retry on freshly verified identical pixels can temporarily
                # fail to read the header. Keep confirmed rows, without retries
                # beyond the existing two-attempt budget or a longer stale age.
                if same and self.active and self.compatible_partial(observation):
                    self.render();return
                self.hide();self.active=False;return
            # Invalidate the augment session once when changing scene; callbacks
            # from old augment queries can no longer paint over item results.
            if p.last_observation or p.stats_payload:
                p.invalidate()
            if hasattr(p,'selections'):
                p.selections.observe(observation,image.size,binding,frame_time)
            self.last_frame=image;self.signature=signature;self.boxes=signature_boxes
            # OCR confirms the captured pixels; returning does not make them new.
            # A later verified frame of the same titles may already be fresher.
            self.last_seen=max(self.last_seen,frame_time)
            ids=[c['resolution'].get('id') for c in observation['cards']]
            if self.active and ids==[r['id'] for r in self.rows]:
                self.observation=observation
                self.render();return
            self.generation+=1;self.tasks.clear()
            self.observation=observation;self.active=True
            p.once_active=False;p.once_ocr_pending=False
            self.rows=[{'id':c['resolution'].get('id'),
                        'name':c['resolution'].get('name') or '未确认装备',
                        'global':{'status':'pending' if c['resolution'].get('id') else 'unrecognized'},
                        'comp':{'status':('pending' if p.session.target else 'unpinned') if c['resolution'].get('id') else 'unrecognized'},
                        'holders':[],'holder_status':'pending' if c['resolution'].get('id') else 'unrecognized'}
                       for c in observation['cards']]
            p.set_activity('item_results',f'已识别 {sum(i is not None for i in ids)}/{len(ids)} 件装备，正在显示均排。')
            if not p.offline:record('item_recognized',ids=ids,elapsed_ms=observation.get('elapsed_ms'))
            self.render();self.start_queries()
        def failed(_):
            self.recognizing=False;p.ocr_busy=False
            if self.accepts(token):self.reset()
        # The main thread initializes the native engine in catalog_loaded.
        p.submit(p.ocr_pool,lambda:analyze_items(image,p.vision,catalog),done,failed)
        return True

    def start_queries(self):
        if self.query_inflight is not None or self.tasks:return
        p=self.panel;target=p.session.target
        self.tasks.append(('table',None))
        if target:self.tasks.append(('table',target))
        self.tasks.append(('details',target))
        self.next_query()

    def retry_failed_queries(self):
        """Manual refresh of verified titles repairs only failed source scopes.

        Ordinary frame checks never generate retries. Respect the shared source
        cooldown and keep already confirmed ranks/portraits visible throughout.
        """
        if self.query_inflight is not None or self.tasks:return
        if self.panel.adapter.next_request-time.monotonic()>2:return
        target=self.panel.session.target
        if any(row['global']['status']=='error' for row in self.rows):
            self.tasks.append(('table',None))
        if target and any(row['comp']['status']=='error' for row in self.rows):
            self.tasks.append(('table',target))
            self.tasks.append(('fallbacks',target))
        for row in self.rows:
            if row['id'] and row['holder_status']=='error':
                row['holder_status']='pending'
                self.tasks.append(('holders',row['id']))
        if self.tasks:self.render();self.next_query()

    def next_query(self):
        if not self.active or not self.tasks or self.query_inflight is not None:return
        p=self.panel;adapter=p.adapter;target=p.session.target
        kind,value=self.tasks.popleft();token=self.token()
        if kind=='details':
            for row in self.rows:
                if row['id']:self.tasks.append(('holders',row['id']))
            self.tasks.append(('fallbacks',target))
            self.next_query();return
        if kind=='fallbacks':
            for row in self.rows:
                if row['id'] and target and row['comp']['status']=='missing':self.tasks.append(('fallback',row['id']))
            self.next_query();return
        key=query_key(adapter,kind,value if kind=='table' else (target,value))
        self.query_inflight=token
        started=time.monotonic()
        def apply(result):
            if not self.accepts(token) or not self.active:return
            self.query_inflight=None
            try:
                if kind=='table':
                    scope='comp' if value else 'global'
                    for row in self.rows:
                        if row['id']:row[scope]=item_stat(result,row['id'],value)
                elif kind=='fallback':
                    for row in self.rows:
                        if row['id']==value:row['comp']=fallback_stat(result,target)
                else:
                    allowed={str(h['heroId']) for h in (p.comp_detail or {}).get('heroes',[])} if target else None
                    for row in self.rows:
                        if row['id']==value:
                            row['holders']=best_holders(result,allowed)
                            row['holder_status']='ok' if row['holders'] else 'missing'
            except Exception:
                fail('invalid item statistics');return
            if not p.offline:record('item_query',kind=kind,item_id=value if kind!='table' else None,
                scope=target if kind!='table' else value,status='ok',
                elapsed_ms=round((time.monotonic()-started)*1000),cached=bool(result.get('cached')))
            self.cache[key]=result
            if len(self.cache)>96:
                fresh=sorted(((k,v) for k,v in self.cache.items() if 0<=time.time()-v['fetched_at']<900),
                             key=lambda item:item[1]['fetched_at'],reverse=True)
                self.cache=dict(fresh[:96])
            self.render();self.next_query()
        def fail(_):
            if not self.accepts(token) or not self.active:return
            self.query_inflight=None
            for row in self.rows:
                if not row['id']:continue
                if kind=='table':row['comp' if value else 'global']={'status':'error'}
                elif row['id']==value:
                    if kind=='fallback':row['comp']={'status':'error'}
                    else:row['holder_status']='error'
            if not p.offline:record('item_query',kind=kind,item_id=value if kind!='table' else None,
                scope=target if kind!='table' else value,status='error',
                elapsed_ms=round((time.monotonic()-started)*1000))
            self.render();self.next_query()
        cached=self.cached(key)
        if cached:
            apply(cached);return
        entity=next((e for e in p.catalog.get('equip',[]) if str(e['id'])==value),None)
        def fetch():
            if not self.accepts(token):return None
            if kind=='table':return adapter.item_stats(value)
            if kind=='fallback':return adapter.explore('equip',entity)
            return adapter.item_holders(value,target)
        p.submit(p.network,fetch,apply,fail)

    def fresh(self,now):
        if now-self.last_seen<=1.5:return True
        return (self.probing and self.probe_started is not None
                and now-self.probe_started<=1.25 and now-self.last_seen<=2.75)

    def compatible_partial(self,observation):
        if observation.get('reason') not in ('item_header_unconfirmed','excluded_or_unconfirmed'):return False
        cards=observation.get('cards',[])
        if cards and len(cards)!=len(self.rows):return False
        for card,row in zip(cards,self.rows):
            resolution=card.get('resolution',{})
            if resolution.get('status')=='excluded':return False
            candidate=resolution.get('id')
            if candidate is not None and row['id'] is not None and str(candidate)!=str(row['id']):return False
        return True

    def render(self):
        if not self.active or not self.available() or not self.fresh(time.monotonic()):
            self.hide();return
        p=self.panel;cards=self.observation['cards'];centers=[(c['box'][0][0]+c['box'][1][0])/2 for c in cards]
        gap=min(b-a for a,b in zip(centers,centers[1:]))
        for i,overlay in enumerate(self.overlays):
            if i>=len(cards):overlay.hide();continue
            overlay.update_row(self.rows[i],p.catalog)
            overlay.place(p.binding,cards[i]['box'],self.observation['image_size'],gap)

    def shutdown(self):
        self.reset()
        for overlay in self.overlays:overlay.close()
