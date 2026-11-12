"""Loopback HTTP application. Exact route and response boundaries, no raw logging."""
import json
import re
import secrets
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from .core import ReferenceSelector, eligible, profile, public_movie, utcnow, validate_decision
from .store import InvalidData

ROOT=Path(__file__).resolve().parent
EXAMPLES=ROOT.parent/'examples'
MESSAGES={'no_acceptable_candidate':'Nothing fits these settings. Try changing your limits or resetting this session.',
          'insufficient_information':'There is not enough compatible information to choose. Add private features or change the settings.',
          'inference_error':'The selector could not complete this pick. Please try again or check setup.'}


class Service:
    def __init__(self,store,selector=None,fallback=False):
        self.store=store; self.selector=selector or ReferenceSelector(); self.fallback=fallback
        self.lock=threading.RLock()
        with store.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS offered(session TEXT, mode TEXT, id TEXT, PRIMARY KEY(session,mode,id))')

    def state(self,mode):
        movies=self.store.movies(mode); history=self.store.history(mode)
        p=profile(movies,history)
        return {'mode':mode,'catalog_count':len(movies),'watched_count':len(history),
                'rated_count':sum(h['rating'] is not None for h in history), 'personalized':p['personalized'],
                'constraints':self.store.settings(mode)}

    def pick(self,session,mode,another_id=None):
        with self.lock:
            if another_id is not None:
                with self.store.db() as db:
                    if not db.execute('SELECT 1 FROM offered WHERE session=? AND mode=? AND id=?',(session,mode,another_id)).fetchone(): raise InvalidData()
                self.store.exclude(session,mode,another_id)
            movies=self.store.movies(mode); history=self.store.history(mode); c=self.store.settings(mode)
            excluded=self.store.exclusions(session,mode); now=utcnow()
            candidates=[m for m in movies if eligible(m,history,excluded,c,now)]
            preference=profile(movies,history)
            selection_input=[{'id':m['id'],'private':{'schema_version':1,'features':m.get('private',{}).get('features',{})}} for m in candidates]
            started=time.perf_counter(); fallback=False; backend=self.selector.name
            try:
                decision=validate_decision(self.selector.select(preference,selection_input,c.get('mood')),{m['id'] for m in candidates})
                if decision.get('abstain')=='inference_error' and self.fallback:
                    raise ValueError('inference_error')
            except Exception:
                if self.fallback:
                    fallback=True
                    decision=ReferenceSelector().select(preference,selection_input,c.get('mood'))
                else:
                    decision={'abstain':'inference_error'}
            code=decision.get('abstain','selected')
            with self.store.db() as db:
                # Reproduction data stays in SQLite, never in viewing APIs or logs.
                db.execute('INSERT INTO decisions(backend,fallback,code,elapsed_ms,schema_version,input) VALUES (?,?,?,?,?,?)',
                    (backend,int(fallback),code,(time.perf_counter()-started)*1000,1,
                     json.dumps({'mode':mode,'preference':preference,'constraints':c,'excluded':excluded,'candidates':selection_input,'decision':decision},allow_nan=False)))
            if 'abstain' in decision:
                return {'code':code,'message':MESSAGES[code]}
            # Recheck against live persisted state after arbitrary external inference.
            current=next((m for m in self.store.movies(mode) if m['id']==decision['id']),None)
            current_constraints=self.store.settings(mode)
            if current is None or not eligible(current,self.store.history(mode),self.store.exclusions(session,mode),current_constraints,utcnow()):
                return {'code':'no_acceptable_candidate','message':MESSAGES['no_acceptable_candidate']}
            with self.store.db() as db:
                db.execute('INSERT OR IGNORE INTO offered VALUES (?,?,?)',(session,mode,current['id']))
            return {'movie':public_movie(current,utcnow(),current_constraints)}

    def diagnostics(self):
        with self.store.db() as db:
            count=db.execute('SELECT count(*) FROM decisions WHERE fallback=1').fetchone()[0]
            row=db.execute('SELECT elapsed_ms,code FROM decisions ORDER BY n DESC LIMIT 1').fetchone()
        return {'backend':self.selector.name,'jev_status':'opt-in adapter available, live API unverified',
                'extraction':'Precomputed features supported; model extraction requires a configured command.',
                'schema_version':1,'fallback_enabled':self.fallback,'fallback_count':count,
                'last_selection_ms':round(row[0],2) if row else None,'last_outcome':row[1] if row else None}


def make_server(service,host='127.0.0.1',port=8000):
    class Handler(BaseHTTPRequestHandler):
        server_version='NoSpoilers'
        def log_message(self,*args): pass
        def send(self,status,data,mime='application/json'):
            raw=json.dumps(data,allow_nan=False).encode() if mime=='application/json' else data
            self.send_response(status)
            self.send_header('Content-Type',mime+'; charset=utf-8')
            self.send_header('Content-Length',str(len(raw)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'none'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if getattr(self,'new_session',False):
                self.send_header('Set-Cookie',f'ns_session={self.session}; HttpOnly; SameSite=Strict; Path=/')
            self.end_headers(); self.wfile.write(raw)
        def setup_request(self):
            host=self.headers.get('Host','')
            if host not in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}:
                self.send(403,{'error':'local_access_only'}); return False
            origin=self.headers.get('Origin')
            if origin and origin != 'http://'+host:
                self.send(403,{'error':'origin_rejected'}); return False
            try:
                cookie=SimpleCookie(self.headers.get('Cookie',''))
                token=cookie['ns_session'].value if 'ns_session' in cookie else ''
            except Exception: token=''
            self.new_session=not bool(re.fullmatch('[0-9a-f]{48}',token))
            self.session=secrets.token_hex(24) if self.new_session else token
            return True
        def do_GET(self):
            if not self.setup_request(): return
            url=urlsplit(self.path); query=parse_qs(url.query)
            try:
                mode=query.get('mode',['real'])[0]
                if mode not in ('real','demo'): raise InvalidData()
                if url.path in ('/','/app.js','/style.css'):
                    file={'/':('index.html','text/html'),'/app.js':('app.js','text/javascript'),'/style.css':('style.css','text/css')}[url.path]
                    return self.send(200,(ROOT/'static'/file[0]).read_bytes(),file[1])
                if url.path=='/api/state': result=service.state(mode)
                elif url.path=='/api/diagnostics': result=service.diagnostics()
                elif url.path=='/api/search':
                    q=query.get('q',[''])[0].casefold()[:200]
                    result={'movies':[{'id':m['id'],'title':m['title'],'year':m['year']} for m in service.store.movies(mode) if q and (q in m['title'].casefold() or q==str(m['year']))][:30]}
                elif url.path=='/api/history':
                    movies={m['id']:m for m in service.store.movies(mode)}
                    result={'history':[{'id':h['id'],'title':movies[h['id']]['title'],'year':movies[h['id']]['year'],
                                        'rating':h['rating'],'notes':h['notes'],'watched':bool(h['watched'])} for h in service.store.history(mode) if h['id'] in movies]}
                else: return self.send(404,{'error':'not_found'})
                self.send(200,result)
            except InvalidData: self.send(400,{'error':'invalid_data'})
            except Exception: self.send(500,{'error':'request_failed'})
        def do_POST(self):
            if not self.setup_request(): return
            if self.headers.get('Content-Type','').split(';')[0]!='application/json': return self.send(415,{'error':'json_required'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=16384: return self.send(413,{'error':'request_size'})
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict): raise InvalidData()
                mode=data.get('mode','real')
                if mode not in ('real','demo'): raise InvalidData()
                routes={'/api/pick':{'mode'},'/api/another':{'mode','id'},'/api/reaction':{'mode','id','rating','notes'},
                        '/api/settings':{'mode','constraints'},'/api/reset':{'mode'},'/api/demo':set(),'/api/demo-history':set()}
                if self.path not in routes: return self.send(404,{'error':'not_found'})
                if set(data)-routes[self.path]: raise InvalidData()
                with service.lock:
                    if self.path in ('/api/pick','/api/another'):
                        if self.path=='/api/another' and not isinstance(data.get('id'),str): raise InvalidData()
                        result=service.pick(self.session,mode,data.get('id') if self.path=='/api/another' else None)
                    elif self.path=='/api/reaction':
                        if not isinstance(data.get('id'),str) or 'rating' not in data: raise InvalidData()
                        service.store.react(mode,data['id'],data['rating'],data.get('notes','')); result={'ok':True}
                    elif self.path=='/api/settings':
                        service.store.save_settings(mode,data.get('constraints')); result={'ok':True}
                    elif self.path=='/api/reset':
                        service.store.reset_session(self.session,mode); result={'ok':True}
                    elif self.path=='/api/demo':
                        service.store.ingest(json.loads((EXAMPLES/'demo.json').read_text())); result={'ok':True}
                    elif self.path=='/api/demo-history':
                        service.store.ingest(json.loads((EXAMPLES/'demo-history.json').read_text())); result={'ok':True}
                self.send(200,result)
            except (InvalidData,ValueError,TypeError): self.send(400,{'error':'invalid_data'})
            except Exception: self.send(500,{'error':'request_failed'})
    return ThreadingHTTPServer((host,port),Handler)
