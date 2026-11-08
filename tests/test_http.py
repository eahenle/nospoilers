import contextlib
import http.cookiejar
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import build_opener, HTTPCookieProcessor, Request
from urllib.error import HTTPError
from nospoilers.server import Service, make_server
from nospoilers.store import Store
from test_core import movie, CANARY

class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.store=Store(Path(self.tmp.name)/'state.db')
        self.store.ingest({'version':1,'mode':'real','movies':[movie('local:a',1),movie('local:b',0),movie('local:seen',1)],'history':[]})
        self.service=Service(self.store)
        self.server=make_server(self.service,port=0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)
        self.client=build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.tmp.cleanup()
    def request(self,path,data=None):
        req=Request(self.url+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
        with self.client.open(req) as r:
            raw=r.read().decode()
            return json.loads(raw) if path.startswith('/api/') else raw
    def test_flow_and_restart_persistence(self):
        state=self.request('/api/state?mode=real')
        self.assertFalse(state['personalized'])
        self.request('/api/reaction',{'mode':'real','id':'local:seen','rating':'liked','notes':''})
        self.assertTrue(self.request('/api/state?mode=real')['personalized'])
        a=self.request('/api/pick',{'mode':'real'})['movie']
        self.assertEqual(a['id'],'local:a')
        b=self.request('/api/another',{'mode':'real','id':a['id']})['movie']
        self.assertNotEqual(a['id'],b['id'])
        self.assertEqual(len(self.store.history('real')),1)
        self.request('/api/reaction',{'mode':'real','id':b['id'],'rating':None,'notes':''})
        reopened=Service(Store(self.store.path))
        self.assertEqual(len(reopened.store.history('real')),2)
        self.assertNotEqual(reopened.pick('new-session','real')['movie']['id'],b['id'])
        self.request('/api/reset',{'mode':'real'})
        self.assertEqual(self.request('/api/pick',{'mode':'real'})['movie']['id'],a['id'])
    def test_disclosure_all_routes_assets_and_logs(self):
        log=io.StringIO()
        with contextlib.redirect_stderr(log),contextlib.redirect_stdout(log):
            for route in ['/','/app.js','/style.css','/api/state?mode=real','/api/search?mode=real&q=Fiction','/api/history?mode=real','/api/diagnostics']:
                self.assertNotIn(CANARY,str(self.request(route)))
            self.assertNotIn(CANARY,json.dumps(self.request('/api/pick',{'mode':'real'})))
        self.assertNotIn(CANARY,log.getvalue())
        with self.assertRaises(HTTPError) as cm: self.request('/api/reaction',{'mode':'real','id':CANARY,'rating':'liked'})
        self.assertNotIn(CANARY,cm.exception.read().decode())
        with self.assertRaises(HTTPError): self.request('/examples/demo.json')
    def test_selector_failure_and_explicit_fallback(self):
        class Bad:
            name='test-invalid'
            def select(self,*args): return {'id':'local:unknown','rationale':CANARY}
        self.service.selector=Bad()
        response=self.request('/api/pick',{'mode':'real'})
        self.assertEqual(response['code'],'inference_error')
        self.assertNotIn('movie',response)
        self.service.fallback=True
        response=self.request('/api/pick',{'mode':'real'})
        self.assertIn('movie',response)
        self.assertEqual(self.request('/api/diagnostics')['fallback_count'],1)
    def test_empty_pool_does_not_relax_and_skip_needs_offered_id(self):
        self.request('/api/settings',{'mode':'real','constraints':{'max_runtime':1}})
        self.assertEqual(self.request('/api/pick',{'mode':'real'})['code'],'no_acceptable_candidate')
        with self.assertRaises(HTTPError): self.request('/api/another',{'mode':'real','id':'local:a'})
    def test_demo_no_synthetic_feedback_without_action(self):
        self.request('/api/demo',{})
        self.assertEqual(self.request('/api/history?mode=demo')['history'],[])
        self.request('/api/demo-history',{})
        self.assertGreater(len(self.request('/api/history?mode=demo')['history']),0)
        self.assertEqual(self.request('/api/history?mode=real')['history'],[])
    def test_selector_and_reproduction_snapshot_receive_no_narratives(self):
        class Inspector:
            name='inspect'
            def select(self,preference,candidates,mood):
                if CANARY in json.dumps(candidates):
                    return {'abstain':'inference_error'}
                return {'id':candidates[0]['id']}
        self.service.selector=Inspector()
        response=self.request('/api/pick',{'mode':'real'})
        self.assertIn('movie',response)
        with self.store.db() as db:
            snapshot=db.execute('SELECT input FROM decisions ORDER BY n DESC LIMIT 1').fetchone()[0]
        self.assertNotIn(CANARY,snapshot)

    def test_rechecks_watched_status_after_selector_runs(self):
        store=self.store
        class Racing:
            name='race-test'
            def select(self,preference,candidates,mood):
                store.react('real',candidates[0]['id'],None,'')
                return {'id':candidates[0]['id']}
        self.service.selector=Racing()
        self.assertEqual(self.request('/api/pick',{'mode':'real'})['code'],'no_acceptable_candidate')

    def test_security_origin_and_unknown_fields(self):
        req=Request(self.url+'/api/demo',data=b'{}',headers={'Content-Type':'application/json','Origin':'https://evil.example'})
        with self.assertRaises(HTTPError) as cm: self.client.open(req)
        self.assertEqual(cm.exception.code,403)
        with self.assertRaises(HTTPError): self.request('/api/pick',{'mode':'real','extra':CANARY})

if __name__=='__main__': unittest.main()
