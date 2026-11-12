import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from nospoilers.store import Store

class CLITests(unittest.TestCase):
    def test_invalid_ingestion_is_bounded_and_atomic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=root/'bad.json'; db=root/'test.sqlite3'
            source.write_text(json.dumps({'version':1,'mode':'real','movies':[],'history':[{'id':['PRIVATE_INGEST_CANARY'],'rating':'liked'}]}))
            r=subprocess.run([sys.executable,'-m','nospoilers','--db',str(db),'import',str(source)],capture_output=True,text=True)
            self.assertEqual(r.returncode,1)
            self.assertEqual(r.stderr,'')
            self.assertNotIn('PRIVATE_INGEST_CANARY',r.stdout)
            self.assertIn('Operation failed',r.stdout)
            self.assertEqual(Store(db).movies('real'),[])
    def test_extraction_does_not_overwrite_a_concurrent_import(self):
        from test_core import movie
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/'test.sqlite3'; store=Store(db)
            first=movie('local:a'); second=movie('local:b')
            store.ingest({'version':1,'mode':'real','movies':[first,second]})
            # Real extractor subprocess changes the catalog through a separate
            # connection while the CLI holds its original extraction snapshot.
            code="""import json,sys
from nospoilers.store import Store
r=json.load(sys.stdin)
s=Store(sys.argv[1]); movies=s.movies('real')
movies[1]['title']='New import title'
movies[1]['private']['source_text']='NEW_PRIVATE_SOURCE'
s.ingest({'version':1,'mode':'real','movies':[movies[1]]})
print(json.dumps({'schema_version':1,'features':{k:0.5 for k in r['feature_names']}}))
"""
            command=json.dumps([sys.executable,'-c',code,str(db)])
            r=subprocess.run([sys.executable,'-m','nospoilers','--db',str(db),'extract','--command',command,'--version','race-v1'],capture_output=True,text=True)
            current=store.movies('real')
            self.assertEqual(current[1]['title'],'New import title')
            self.assertEqual(current[1]['private']['source_text'],'NEW_PRIVATE_SOURCE')
            self.assertEqual(current[0],first)  # Batch rollback, not partial enrichment.
            self.assertEqual(r.returncode,1)
            self.assertEqual(r.stderr,'')
            self.assertNotIn('NEW_PRIVATE_SOURCE',r.stdout)

    def test_fixture_cache_repeated_and_selection_does_not_extract(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/'test.sqlite3'
            for args in [('import','examples/demo.json'),('extract','--mode','demo','--fixture'),('extract','--mode','demo','--fixture')]:
                r=subprocess.run([sys.executable,'-m','nospoilers','--db',str(db),*args],capture_output=True,text=True)
                self.assertEqual(r.returncode,0,r.stdout)
            store=Store(db)
            with store.db() as conn: before=conn.execute('SELECT count(*) FROM extraction').fetchone()[0]
            self.assertEqual(before,12)
            from nospoilers.server import Service
            from unittest.mock import patch
            with patch('nospoilers.adapters.CachedExtractor.extract',side_effect=AssertionError('pick must not extract')):
                self.assertIn('movie',Service(store).pick('test','demo'))
            with store.db() as conn: after=conn.execute('SELECT count(*) FROM extraction').fetchone()[0]
            self.assertEqual(before,after)

if __name__=='__main__':unittest.main()
