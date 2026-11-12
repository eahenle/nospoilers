"""Local server and private ingestion tools. Never print source content."""
import argparse
import copy
import json
import os
from pathlib import Path
from .store import Store, InvalidData
from .adapters import CachedExtractor, FixtureExtractor, CommandExtractor, CommandSelector, TMDB, IntegrationError
from .core import FEATURES
from .server import Service, make_server


def main():
    parser=argparse.ArgumentParser(prog='python -m nospoilers')
    parser.add_argument('--db',default='.data/nospoilers.sqlite3')
    sub=parser.add_subparsers(dest='action')
    serve=sub.add_parser('serve'); serve.add_argument('--port',type=int,default=8000)
    serve.add_argument('--selector-command',help='JSON argv for an optional selector subprocess')
    serve.add_argument('--candidate-limit',type=int)
    serve.add_argument('--reference-fallback',action='store_true')
    imp=sub.add_parser('import'); imp.add_argument('file',type=Path)
    tmdb=sub.add_parser('tmdb'); tmdb.add_argument('--pages',type=int,default=1); tmdb.add_argument('--ids',default='')
    extract=sub.add_parser('extract'); extract.add_argument('--mode',choices=['real','demo'],default='real')
    extract.add_argument('--fixture',action='store_true'); extract.add_argument('--command',help='JSON argv for private extractor')
    extract.add_argument('--version',default='')
    args=parser.parse_args()
    try:
        store=Store(args.db)
        if args.action=='import':
            if args.file.stat().st_size>20000000: raise InvalidData()
            count=store.ingest(json.loads(args.file.read_text()))
            print(f'Imported {count} movie records. History merged by stable ID.')
        elif args.action=='tmdb':
            token=os.environ.get('TMDB_READ_ACCESS_TOKEN')
            if not token:
                print('TMDB_READ_ACCESS_TOKEN is required. Set it securely in your environment.'); return 2
            data=TMDB(token).collect([i for i in args.ids.split(',') if i],args.pages)
            print(f'Imported {store.ingest(data)} TMDB records. Private features are unknown until enriched.')
        elif args.action=='extract':
            if args.fixture and args.mode!='demo':
                print('Fixture extraction is restricted to demo mode.'); return 2
            if args.fixture: extractor=FixtureExtractor({k:.5 for k in FEATURES})
            elif args.command and args.version: extractor=CommandExtractor(json.loads(args.command),args.version)
            else:
                print('Choose --fixture --mode demo, or supply --command and an immutable --version.'); return 2
            cache=CachedExtractor(store,extractor); movies=store.movies(args.mode); updates=[]
            for m in movies:
                old=m.get('private',{}); source=old.get('source_text','')
                if source:
                    original=copy.deepcopy(m)
                    p=cache.extract(source); p['source_text']=source
                    p['source_refs']=old.get('source_refs',[]); m['private']=p
                    updates.append((original,m))
            store.save_extraction(args.mode,updates)
            print('Extraction completed; compatible content/version cache entries reused.')
        else:
            selector=None
            if getattr(args,'selector_command',None):
                if args.candidate_limit is None: raise InvalidData()
                selector=CommandSelector(json.loads(args.selector_command),args.candidate_limit)
            server=make_server(Service(store,selector,getattr(args,'reference_fallback',False)),port=getattr(args,'port',8000))
            print(f'NoSpoilers listening on local port {server.server_port}.',flush=True)
            try: server.serve_forever()
            except KeyboardInterrupt: pass
            finally: server.server_close()
        return 0
    except (InvalidData,IntegrationError,ValueError,OSError):
        print('Operation failed (invalid_data_or_integration). No source content logged.')
        return 1

if __name__=='__main__': raise SystemExit(main())
