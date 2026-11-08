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
