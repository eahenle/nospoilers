"""SQLite persistence and transactional, validated import boundary."""
import json
import math
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from .core import FEATURES, SCHEMA_VERSION, MOODS

class InvalidData(ValueError):
    def __init__(self):
        super().__init__('invalid_data')


def text(value, limit=200, empty=False):
    return isinstance(value, str) and (empty or bool(value.strip())) and len(value) <= limit and not any(ord(c)<32 and c not in '\n\t' for c in value)


def features_valid(p):
    return (isinstance(p, dict) and set(p) == set(FEATURES)
            and all(v is None or (type(v) in (int,float) and 0 <= v <= 1 and math.isfinite(v)) for v in p.values()))


def validate_movie(m):
    if not isinstance(m, dict) or set(m)-{'id','title','year','runtime','availability','source_ids','private'}:
        raise InvalidData()
    if (not isinstance(m.get('id'),str) or not re.fullmatch(r'[a-z][a-z0-9_-]*:[A-Za-z0-9_.-]{1,100}',m['id'])
        or not text(m.get('title')) or type(m.get('year')) is not int or not 1880 <= m['year'] <= 2200
        or (m.get('runtime') is not None and (type(m['runtime']) is not int or not 1 <= m['runtime'] <= 1000))):
        raise InvalidData()
    ids = m.get('source_ids',{})
    if not isinstance(ids,dict) or len(ids)>20 or not all(text(k,50) and text(v,100) for k,v in ids.items()):
        raise InvalidData()
    p = m.get('private')
    if 'private' in m:
        if (not isinstance(p,dict) or set(p)-{'schema_version','features','source_text','source_refs','provenance','missing'}
            or type(p.get('schema_version')) is not int or p['schema_version'] != SCHEMA_VERSION
            or not features_valid(p.get('features')) or not isinstance(p.get('provenance'),dict)
            or not text(p.get('source_text',''),100000,True)
            or not isinstance(p.get('source_refs',[]),list) or not isinstance(p.get('missing',[]),list)):
            raise InvalidData()
    offers=m.get('availability',[])
    if not isinstance(offers,list) or len(offers)>100:
        raise InvalidData()
    for o in offers:
        if (not isinstance(o,dict) or set(o)-{'region','provider','access_type','source','checked_at','url'}
            or not re.fullmatch('[A-Z]{2}',str(o.get('region','')))
            or not text(o.get('provider'),100) or o.get('access_type') not in ('included','rent','buy','free','ads')
            or not text(o.get('source'),100) or not text(o.get('checked_at'),100)
            or not text(o.get('url',''),2000,True)):
            raise InvalidData()
        from datetime import datetime
        try:
            if datetime.fromisoformat(o['checked_at'].replace('Z','+00:00')).tzinfo is None:
                raise InvalidData()
        except ValueError:
            raise InvalidData() from None
    return m


def validate_constraints(c):
    if not isinstance(c,dict) or set(c)-{'max_runtime','providers','region','access_types','mood','show_runtime','show_availability'}:
        raise InvalidData()
    if c.get('max_runtime') is not None and (type(c['max_runtime']) is not int or not 1 <= c['max_runtime'] <= 1000):
        raise InvalidData()
    if not re.fullmatch('[A-Z]{2}',str(c.get('region','US'))):
        raise InvalidData()
    if (not isinstance(c.get('providers',[]),list) or len(c.get('providers',[]))>30
        or not all(text(p,100) for p in c.get('providers',[]))):
        raise InvalidData()
    if (not isinstance(c.get('access_types',['included']),list) or not c.get('access_types',['included'])
        or any(a not in ('included','rent','buy','free','ads') for a in c.get('access_types',['included']))):
        raise InvalidData()
    if c.get('mood') is not None and c['mood'] not in MOODS:
        raise InvalidData()
    if any(k in c and type(c[k]) is not bool for k in ('show_runtime','show_availability')):
        raise InvalidData()
    return c


class Store:
    def __init__(self,path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS movies(mode TEXT, id TEXT, data TEXT NOT NULL, PRIMARY KEY(mode,id));
            CREATE TABLE IF NOT EXISTS history(mode TEXT, id TEXT, rating TEXT, notes TEXT, watched INTEGER NOT NULL DEFAULT 1, PRIMARY KEY(mode,id));
            CREATE TABLE IF NOT EXISTS settings(mode TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS exclusions(session TEXT, mode TEXT, id TEXT, PRIMARY KEY(session,mode,id));
            CREATE TABLE IF NOT EXISTS extraction(cache_key TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS decisions(n INTEGER PRIMARY KEY, backend TEXT, fallback INTEGER, code TEXT, elapsed_ms REAL, schema_version INTEGER, input TEXT);
            ''')
        self.path.chmod(0o600)

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=10)
        db.row_factory=sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def movies(self,mode):
        with self.db() as db:
            return [json.loads(r[0]) for r in db.execute('SELECT data FROM movies WHERE mode=? ORDER BY id',(mode,))]

    def history(self,mode):
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT id,rating,notes,watched FROM history WHERE mode=? ORDER BY id',(mode,))]

    def ingest(self,data):
        if (not isinstance(data,dict) or set(data)-{'version','mode','movies','history'} or type(data.get('version')) is not int
            or data['version'] != 1 or data.get('mode') not in ('real','demo')
            or not isinstance(data.get('movies'),list) or len(data['movies'])>10000
            or not isinstance(data.get('history',[]),list)):
            raise InvalidData()
        mode=data['mode']
        movies=[validate_movie(m) for m in data['movies']]
        ids=[m['id'] for m in movies]
        if len(set(ids))!=len(ids): raise InvalidData()
        known=set(ids)|{m['id'] for m in self.movies(mode)}
        seen=set()
        for h in data.get('history',[]):
            if (not isinstance(h,dict) or set(h)-{'id','rating','notes','watched'} or not isinstance(h.get('id'),str) or h.get('id') not in known
                or h['id'] in seen or h.get('rating') not in ('liked','neutral','disliked',None)
                or not text(h.get('notes',''),2000,True) or type(h.get('watched',True)) is not bool
                or h.get('watched',True) is not True):
                raise InvalidData()
            seen.add(h['id'])
        with self.db() as db:
            for m in movies:
                db.execute('INSERT INTO movies VALUES (?,?,?) ON CONFLICT(mode,id) DO UPDATE SET data=excluded.data',(mode,m['id'],json.dumps(m,allow_nan=False)))
            for h in data.get('history',[]):
                db.execute('INSERT INTO history VALUES (?,?,?,?,1) ON CONFLICT(mode,id) DO UPDATE SET rating=excluded.rating,notes=excluded.notes,watched=1',(mode,h['id'],h.get('rating'),h.get('notes','')))
        return len(movies)

    def save_extraction(self,mode,updates):
        """Commit a batch only if its source movie snapshots are still current."""
        if mode not in ('real','demo'): raise InvalidData()
        for old,new in updates:
            validate_movie(new)
            if old['id'] != new['id']: raise InvalidData()
        with self.db() as db:
            # Reserve the writer before comparing; other imports must not slip
            # between the snapshot check and its replacement.
            db.execute('BEGIN IMMEDIATE')
            for old,new in updates:
                row=db.execute('SELECT data FROM movies WHERE mode=? AND id=?',(mode,old['id'])).fetchone()
                if row is None or json.loads(row[0]) != old: raise InvalidData()
                db.execute('UPDATE movies SET data=? WHERE mode=? AND id=?',
                           (json.dumps(new,allow_nan=False),mode,new['id']))

    def react(self,mode,id,rating,notes=''):
        if rating not in ('liked','neutral','disliked',None) or not text(notes,2000,True): raise InvalidData()
        with self.db() as db:
            if not db.execute('SELECT 1 FROM movies WHERE mode=? AND id=?',(mode,id)).fetchone(): raise InvalidData()
            db.execute('INSERT INTO history VALUES (?,?,?,?,1) ON CONFLICT(mode,id) DO UPDATE SET rating=excluded.rating,notes=excluded.notes,watched=1',(mode,id,rating,notes))

    def settings(self,mode):
        with self.db() as db:
            row=db.execute('SELECT data FROM settings WHERE mode=?',(mode,)).fetchone()
            return json.loads(row[0]) if row else {'region':'US','providers':[],'access_types':['included'],'show_runtime':True,'show_availability':True}

    def save_settings(self,mode,data):
        validate_constraints(data)
        with self.db() as db:
            db.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(mode) DO UPDATE SET data=excluded.data',(mode,json.dumps(data)))

    def exclude(self,session,mode,id):
        with self.db() as db:
            db.execute('INSERT OR IGNORE INTO exclusions VALUES (?,?,?)',(session,mode,id))

    def exclusions(self,session,mode):
        with self.db() as db:
            return [r[0] for r in db.execute('SELECT id FROM exclusions WHERE session=? AND mode=?',(session,mode))]

    def reset_session(self,session,mode):
        with self.db() as db:
            db.execute('DELETE FROM exclusions WHERE session=? AND mode=?',(session,mode))
