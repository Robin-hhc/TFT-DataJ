"""Small, serialized DataJ adapter. No per-frame network access or stale fallback."""
from __future__ import annotations
import json
from contextlib import closing
import re
import sqlite3
import threading
import time
import httpx
from bootstrap import STATE_DIR


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
        allowed = re.fullmatch(r'/gamedata|/stats/hex|/comp/rank|/explorer/query|/comp/[1-9][0-9]*(?:/hexes|/hero-equips)?', path)
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
        return {**result,'data':rows}

    def comps(self):
        result=self.request('/comp/rank', minSample=50)
        self.validate_comps(result['data'])
        return result

    @staticmethod
    def validate_comps(rows):
        if not isinstance(rows,list) or any(not isinstance(row,dict)
                or not re.fullmatch(r'[1-9][0-9]*',str(row.get('compId','')))
                or not isinstance(row.get('name'),str) for row in rows):
            raise SourceError('阵容列表字段变化')
        for row in rows:
            for key,name in [('heroes','heroName'),('traits','name')]:
                items=row.get(key)
                if items is None:row[key]=[];continue
                if not isinstance(items,list) or any(not isinstance(item,dict) or not isinstance(item.get(name),str) for item in items):
                    raise SourceError('阵容英雄或羁绊字段变化')

    def comp(self, comp):
        result=self.request(f'/comp/{comp}')
        if not isinstance(result['data'],dict) or str(result['data'].get('compId'))!=str(comp) or not isinstance(result['data'].get('heroes'),list):
            raise SourceError('阵容详情字段变化')
        return result

    def equipment(self, comp, hero):
        if not str(hero).isdigit():
            raise ValueError('invalid hero ID')
        result=self.request(f'/comp/{comp}/hero-equips', heroId=str(hero))
        data=result['data']
        if not isinstance(data,dict) or str(data.get('compId'))!=str(comp) or str(data.get('heroId'))!=str(hero) or not all(isinstance(data.get(k),list) for k in ('heroEquips','hero3Equips')):
            raise SourceError('英雄出装字段变化')
        return result

    def explore(self, kind, entity):
        if kind not in ('hex','hero','equip','trait'):
            raise ValueError('unsupported filter')
        rule = {'starCount':'','type':kind,'targetId':str(entity['id']),'enable':True,
                'targetName':entity['name'],'hexRound':'','nameMatch':False,
                'equipCarry':'','equipCount':'','exclude':False}
        if kind == 'trait':
            rule['traitLevel'] = str(entity.get('num',''))
        body = {'version':self.patch,'setId':self.set_id,'filter':{'rules':[rule],'combinator':'and'}}
        result=self.request('/explorer/query', body=body)
        if not isinstance(result['data'],dict) or not isinstance(result['data'].get('comps'),list):
            raise SourceError('检索结果字段变化')
        self.validate_comps(result['data']['comps'])
        return result
