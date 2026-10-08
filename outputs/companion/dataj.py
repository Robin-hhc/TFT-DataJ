"""Small, serialized DataJ adapter. No per-frame network access or stale fallback."""
from __future__ import annotations
import json
import math
from contextlib import closing
import re
import sqlite3
import threading
import time
import httpx
from bootstrap import STATE_DIR

# DataJ's explorer applies this default in its UI, not in /explorer/query.
COMP_MIN_SAMPLE = 50
COMP_MIN_SAMPLE_CHOICES = (1, 10, 50, 100, 300, 500, 1000, 3000, 10000)


class SourceError(RuntimeError):
    pass


class DataJ:
    def __init__(self, set_id=18, patch='18.2a', db=None, transport=None):
        if set_id != 18 or not re.fullmatch(r'18\.\d+(?:\.?[a-z])?', patch):
            raise ValueError('此试用版仅配置了 S18，需明确选择 18.x 统计版本')
        self.set_id, self.patch = set_id, patch
        self.db = db or STATE_DIR/'cache.sqlite'
        self.transport = transport
        self.lock = threading.Lock()
        self.next_request = 0.0
        with closing(sqlite3.connect(self.db, isolation_level=None)) as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, fetched REAL NOT NULL, body TEXT NOT NULL)')

    def request(self, path, body=None, ttl=900, **extra):
        allowed = re.fullmatch(r'/gamedata|/stats/(?:hex|equip)|/stats/equip/[1-9][0-9]*/heroes|/comp/rank|/explorer/query|/comp/[1-9][0-9]*(?:/hexes|/hero-equips|/equips|/equip-heroes)?', path)
        if not allowed:
            raise ValueError('unsupported DataJ endpoint')
        params = {'setId':self.set_id}
        if path != '/gamedata':
            params['gameVersion'] = self.patch
        params.update(extra)
        method = 'POST' if body is not None else 'GET'
        key = json.dumps([method,path,params,body], sort_keys=True, ensure_ascii=False)
        with self.lock:
            with closing(sqlite3.connect(self.db, isolation_level=None)) as conn:
                cached = conn.execute('SELECT fetched, body FROM cache WHERE key=?',(key,)).fetchone()
            if cached and 0 <= time.time()-cached[0] < ttl:
                return {'data':json.loads(cached[1]),'fetched_at':cached[0],'cached':True,'source':'https://www.dataj.cc/api/web'+path}
            delay = self.next_request-time.monotonic()
            if delay > 2:
                raise SourceError('来源暂时不可用，稍后手动重试')
            if delay > 0:
                time.sleep(delay)
            try:
                with httpx.Client(timeout=15, follow_redirects=False, transport=self.transport) as client:
                    response = client.request(method, 'https://www.dataj.cc/api/web'+path,
                                              params=params if body is None else None, json=body)
                self.next_request = time.monotonic()+1
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload,dict) or payload.get('success') is not True or payload.get('code') != 200 or 'data' not in payload:
                    raise SourceError('来源响应结构变化，已停止展示')
                fetched = time.time()
                with closing(sqlite3.connect(self.db, isolation_level=None)) as conn:
                    conn.execute('INSERT OR REPLACE INTO cache VALUES(?,?,?)',(key,fetched,json.dumps(payload['data'],ensure_ascii=False)))
                return {'data':payload['data'],'fetched_at':fetched,'cached':False,'source':str(response.url)}
            except (httpx.HTTPError, ValueError, SourceError) as exc:
                self.next_request = time.monotonic()+60
                raise SourceError('DataJ 请求失败或结构变化；本次不使用旧均排') from exc

    def catalog(self):
        result = self.request('/gamedata', ttl=3600)
        data = result['data']
        if not isinstance(data,dict) or not isinstance(data.get('hex'),list):
            raise SourceError('目录字段变化')
        return result

    @staticmethod
    def parse_versions(page):
        for raw in re.findall(r'self\.__next_f\.push\(\[1,("(?:\\.|[^"\\])*")\]\)',page):
            chunk=json.loads(raw)
            marker='"gameVersions":'
            if marker not in chunk:continue
            rows,_=json.JSONDecoder().raw_decode(chunk.split(marker,1)[1])
            if not isinstance(rows,list):break
            versions=list(dict.fromkeys(row['gameVersion'] for row in rows
                if isinstance(row,dict) and row.get('setId')==18
                and isinstance(row.get('gameVersion'),str)
                and re.fullmatch(r'18\.\d+(?:\.?[a-z])?',row['gameVersion'])))
            if versions:return versions
        raise SourceError('版本列表暂不可用')

    def versions(self):
        with httpx.Client(timeout=15,follow_redirects=False,transport=self.transport) as client:
            response=client.get('https://www.dataj.cc/comp');response.raise_for_status()
        return self.parse_versions(response.text)

    def hexes(self, comp=None):
        if comp is not None and not re.fullmatch(r'[1-9][0-9]*',str(comp)):
            raise ValueError('invalid comp ID')
        result = self.request('/stats/hex' if comp is None else f'/comp/{comp}/hexes')
        if comp is not None and (not isinstance(result['data'],dict) or str(result['data'].get('compId'))!=str(comp)):
            raise SourceError('阵容强化响应对象不匹配')
        rows = result['data'] if comp is None else result['data'].get('hexes')
        if not isinstance(rows,list) or any(not isinstance(r,dict) or 'hexId' not in r or not isinstance(r.get('roundStats'),list) for r in rows):
            raise SourceError('强化统计字段变化')
        seen=set()
        for row in rows:
            identity=str(row['hexId'])
            if not re.fullmatch(r'[1-9][0-9]*',identity) or identity in seen:raise SourceError('强化统计身份异常')
            seen.add(identity);stages=set()
            for part in row['roundStats']:
                if not isinstance(part,dict):raise SourceError('强化阶段字段异常')
                index=part.get('round')
                if (type(index) is not int or index not in (0,1,2) or index in stages
                    or part.get('roundLabel')!=('2-1','3-2','4-2')[index]):raise SourceError('强化阶段口径异常')
                stages.add(index);self.validate_statistics(part,required=True)
        return {**result,'data':rows}

    def comps(self, min_sample=COMP_MIN_SAMPLE):
        if type(min_sample) is not int or min_sample not in COMP_MIN_SAMPLE_CHOICES:
            raise ValueError('unsupported minimum sample')
        result=self.request('/comp/rank', minSample=min_sample)
        self.validate_comps(result['data'])
        return result

    @staticmethod
    def validate_comps(rows):
        if not isinstance(rows,list) or any(not isinstance(row,dict)
                or not re.fullmatch(r'[1-9][0-9]*',str(row.get('compId','')))
                or not isinstance(row.get('name'),str) for row in rows):
            raise SourceError('阵容列表字段变化')
        if len({str(row['compId']) for row in rows})!=len(rows):
            raise SourceError('阵容列表身份重复')
        for row in rows:
            DataJ.validate_statistics(row)
            for key,name in [('heroes','heroName'),('traits','name')]:
                items=row.get(key)
                if items is None:row[key]=[];continue
                if not isinstance(items,list) or any(not isinstance(item,dict) or not isinstance(item.get(name),str) for item in items):
                    raise SourceError('阵容英雄或羁绊字段变化')

    @staticmethod
    def validate_statistics(row, required=False):
        """Reject corrupt values; absent optional metrics remain unavailable."""
        for key,low,high in [('avgPlacement',1,8),('top4Rate',0,100),('topRate',0,100),
                             ('pickRate',0,math.inf)]:
            if key not in row and not (required and key=='avgPlacement'):continue
            value=row.get(key)
            if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:
                raise SourceError('统计数值异常：'+key)
        if 'sampleCount' in row or required:
            count=row.get('sampleCount')
            if type(count) is not int or count<0:raise SourceError('统计样本异常')

    def comp(self, comp):
        result=self.request(f'/comp/{comp}')
        if not isinstance(result['data'],dict) or str(result['data'].get('compId'))!=str(comp) or not isinstance(result['data'].get('heroes'),list):
            raise SourceError('阵容详情字段变化')
        for hero in result['data']['heroes']:
            if (not isinstance(hero,dict)
                or not re.fullmatch(r'[1-9][0-9]*',str(hero.get('heroId','')))
                or not isinstance(hero.get('heroName'),str) or not hero['heroName'].strip()):
                raise SourceError('阵容英雄身份异常')
        return result

    def equipment(self, comp, hero):
        if not str(hero).isdigit():
            raise ValueError('invalid hero ID')
        result=self.request(f'/comp/{comp}/hero-equips', heroId=str(hero))
        data=result['data']
        if not isinstance(data,dict) or str(data.get('compId'))!=str(comp) or str(data.get('heroId'))!=str(hero) or not all(isinstance(data.get(k),list) for k in ('heroEquips','hero3Equips')):
            raise SourceError('英雄出装字段变化')
        for key,size in [('heroEquips',1),('hero3Equips',3)]:
            for row in data[key]:
                if not isinstance(row,dict):raise SourceError('英雄出装行异常')
                self.validate_statistics(row,required=True)
                equips=row.get('equips')
                if (not isinstance(equips,list) or len(equips)!=size or any(not isinstance(e,dict)
                    or not re.fullmatch(r'[1-9][0-9]*',str(e.get('id','')))
                    or not isinstance(e.get('name'),str) for e in equips)):
                    raise SourceError('英雄出装装备身份异常')
        return result

    @staticmethod
    def entity_id(value):
        value = str(value)
        if not re.fullmatch(r'[1-9][0-9]*', value):
            raise ValueError('invalid entity ID')
        return value

    @staticmethod
    def validate_item_rows(rows, identity):
        if not isinstance(rows, list):
            raise SourceError('装备统计列表字段变化')
        seen = set()
        for row in rows:
            if not isinstance(row, dict):
                raise SourceError('装备统计行字段变化')
            key = str(row.get(identity, ''))
            average, count = row.get('avgPlacement'), row.get('sampleCount')
            if (not re.fullmatch(r'[1-9][0-9]*', key) or key in seen
                or type(average) not in (int, float) or not math.isfinite(average)
                or not 1 <= average <= 8 or type(count) is not int or count < 0):
                raise SourceError('装备统计数值或身份异常')
            if identity == 'heroId':
                name = row.get('heroName', row.get('name'))
                if not isinstance(name, str) or not name.strip():
                    raise SourceError('装备持有者名称异常')
            seen.add(key)

    def item_stats(self, comp=None):
        """Direct single-item aggregates; never average holder statistics."""
        comp = self.entity_id(comp) if comp is not None else None
        result = self.request(f'/comp/{comp}/equips' if comp else '/stats/equip')
        data = result['data']
        if comp:
            if not isinstance(data, dict) or str(data.get('compId')) != comp:
                raise SourceError('阵容装备统计范围变化')
            rows = data.get('equips')
        else:
            rows = data
        self.validate_item_rows(rows, 'equipId')
        return result

    def item_holders(self, equip, comp=None):
        equip = self.entity_id(equip)
        comp = self.entity_id(comp) if comp is not None else None
        result = (self.request(f'/comp/{comp}/equip-heroes', equipId=equip) if comp
                  else self.request(f'/stats/equip/{equip}/heroes'))
        data = result['data']
        if comp:
            if (not isinstance(data, dict) or str(data.get('compId')) != comp
                or str(data.get('equipId')) != equip):
                raise SourceError('装备持有者统计范围变化')
            rows = data.get('heroes')
        else:
            rows = data
        self.validate_item_rows(rows, 'heroId')
        return result

    def explore(self, kind, entity, *, hex_stage=None, required_comp=None):
        """Query one condition, optionally requiring exact comp-stage metrics."""
        if kind not in ('hex','hero','equip','trait'):
            raise ValueError('unsupported filter')
        if hex_stage is not None and (kind != 'hex' or hex_stage not in ('2-1','3-2','4-2')):
            raise ValueError('unsupported hex stage')
        if required_comp is not None:
            required_comp = self.entity_id(required_comp)
            if kind != 'hex' or hex_stage is None:
                raise ValueError('required composition needs a hex stage')
        hex_round = str(('2-1','3-2','4-2').index(hex_stage)) if hex_stage is not None else ''
        rule = {'starCount':'','type':kind,'targetId':str(entity['id']),'enable':True,
                'targetName':entity['name'],'hexRound':hex_round,'nameMatch':False,
                'equipCarry':'','equipCount':'','exclude':False}
        if kind == 'trait':
            rule['traitLevel'] = str(entity.get('num',''))
        body = {'version':self.patch,'setId':self.set_id,'filter':{'rules':[rule],'combinator':'and'}}
        result=self.request('/explorer/query', body=body)
        try:
            if not isinstance(result['data'],dict) or not isinstance(result['data'].get('comps'),list):
                raise SourceError('检索结果字段变化')
            self.validate_comps(result['data']['comps'])
            if required_comp is not None:
                for row in result['data']['comps']:
                    if str(row['compId']) == required_comp:
                        self.validate_statistics(row, required=True)
        except SourceError:
            if required_comp is not None:
                key = json.dumps(['POST','/explorer/query',
                    {'setId':self.set_id,'gameVersion':self.patch},body], sort_keys=True, ensure_ascii=False)
                with self.lock:
                    with closing(sqlite3.connect(self.db, isolation_level=None)) as conn:
                        # A concurrent replacement must survive this response's failure.
                        conn.execute('DELETE FROM cache WHERE key=? AND fetched=?', (key,result['fetched_at']))
            raise
        return result
