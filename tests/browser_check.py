"""Optional real-browser acceptance check. PYTHONPATH=. python tests/browser_check.py"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen
from playwright.sync_api import sync_playwright, expect
from nospoilers.store import Store

CANARY='FICTIONAL_BROWSER_SECRET_72831'
ARTIFACTS=Path(os.environ.get('NOSPOILERS_ARTIFACTS','.data/artifacts'))
ARTIFACTS.mkdir(parents=True,exist_ok=True)

def run():
    with tempfile.TemporaryDirectory() as tmp:
        db=Path(tmp)/'browser.sqlite3'; log=Path(tmp)/'server.log'
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
        base=f'http://127.0.0.1:{port}'
        output=log.open('w')
        process=None
        def start():
            p=subprocess.Popen([sys.executable,'-m','nospoilers','--db',str(db),'serve','--port',str(port)],stdout=output,stderr=output)
            for _ in range(100):
                if p.poll() is not None: raise AssertionError('Server exited during readiness')
                try:
                    with urlopen(base+'/api/state',timeout=.5) as r:
                        if json.load(r)['catalog_count']>=0: return p
                except OSError: time.sleep(.05)
            p.terminate();p.wait();raise AssertionError('Server not ready')
        def stop(p):
            p.terminate();p.wait(timeout=10)
        try:
            process=start()
            with sync_playwright() as pw:
                browser=pw.chromium.launch(headless=True,executable_path=os.environ.get('CHROMIUM_PATH','/usr/bin/chromium'))
                context=browser.new_context(viewport={'width':1440,'height':1100})
                page=context.new_page(); delivered=[]; errors=[]; requests=[]
                def capture(response):
                    if response.url.startswith(base):
                        try: delivered.append(response.text())
                        except Exception: pass
                page.on('response',capture);page.on('pageerror',lambda e:errors.append(str(e)))
                page.on('request',lambda r:requests.append(r.url))
                page.goto(base)
                expect(page.locator('#taste-message')).to_contain_text('Unpersonalized')
                page.locator('[data-view="setup"]').click()
                page.locator('#load-demo').click()
                expect(page.locator('#demo-banner')).to_be_visible()
                store=Store(db)
                movies=store.movies('demo')
                for m in movies:
                    m['private']['source_text']=CANARY
                    m['private']['provenance']['canary']=CANARY
                store.ingest({'version':1,'mode':'demo','movies':movies,'history':[]})
                page.locator('.nav[data-view="history"]').click()
                for title,rating in [('The Paper Harbour','liked'),('A Room Above the Rain','disliked'),('The Blue Bicycle Society','neutral')]:
                    page.locator('#search').fill(title)
                    row=page.locator('#search-results .history-item').filter(has_text=title)
                    expect(row).to_be_visible();row.locator('select').select_option(rating)
                    row.get_by_role('button',name='Mark watched').click()
                    expect(page.locator('#history-count')).to_have_text(str(len(store.history('demo'))))
                    expect(page.locator('#notice')).to_contain_text('Reaction saved')
                assert len(store.history('demo'))==3
                page.locator('.nav[data-view="tonight"]').click()
                expect(page.locator('#taste-message')).to_contain_text('3 recorded reactions')
                page.locator('#pick').click();expect(page.locator('#pick-result')).to_be_visible()
                first=page.locator('#movie-title').inner_text()
                page.locator('#another').click();expect(page.locator('#movie-title')).not_to_have_text(first)
                assert len(store.history('demo'))==3, 'Skip must not become feedback'
                watched=page.locator('#movie-title').inner_text()
                page.locator('#feedback-note').fill('A fictional test reaction')
                page.locator('[data-reaction="liked"]').click()
                expect(page.locator('#notice')).to_contain_text('Saved to your watched history')
                assert len(store.history('demo'))==4
                # Real process restart, keeping the same persistent SQLite file.
                stop(process);process=start();page.reload()
                expect(page.locator('#history-count')).to_have_text('4')
                page.locator('.nav[data-view="history"]').click()
                expect(page.locator('#history-list')).to_contain_text(watched)
                expect(page.locator('#history-list input').filter()).to_have_count(4)
                page.locator('.nav[data-view="tonight"]').click()
                page.locator('#pick').click();expect(page.locator('#movie-title')).not_to_have_text(watched)
                # Hard constraint: never silently relax to find something.
                page.locator('#settings-toggle').click();page.locator('#max-runtime').fill('1')
                page.locator('#settings-form button[type="submit"]').click()
                expect(page.locator('#notice')).to_contain_text('Defaults saved')
                page.locator('#pick').click();expect(page.locator('#pick-abstain')).to_be_visible()
                page.locator('#empty-settings').click();page.locator('#max-runtime').fill('')
                page.locator('#settings-form button[type="submit"]').click()
                expect(page.locator('#notice')).to_contain_text('Defaults saved')
                page.locator('#reset').click();expect(page.locator('#notice')).to_contain_text('skips were reset')
                page.locator('#pick').click();expect(page.locator('#pick-result')).to_be_visible()
                # A history update must invalidate the currently presented pick.
                just_picked=page.locator('#movie-title').inner_text()
                page.locator('.nav[data-view="history"]').click()
                page.locator('#search').fill(just_picked)
                row=page.locator('#search-results .history-item').filter(has_text=just_picked)
                expect(row).to_be_visible()
                row.get_by_role('button',name='Mark watched').click()
                expect(page.locator('#notice')).to_contain_text('Reaction saved')
                page.locator('.nav[data-view="tonight"]').click()
                expect(page.locator('#pick-result')).to_be_hidden()
                page.locator('#pick').click();expect(page.locator('#pick-result')).to_be_visible()
                expect(page.locator('#movie-title')).not_to_have_text(just_picked)
                page.screenshot(path=str(ARTIFACTS/'desktop.png'),full_page=True)
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile overflow'
                page.screenshot(path=str(ARTIFACTS/'mobile.png'),full_page=True)
                assert CANARY not in page.content()
                assert CANARY not in ''.join(delivered)
                assert CANARY not in page.evaluate('JSON.stringify(localStorage)')
                assert all(url.startswith(base) for url in requests), 'Unexpected external request'
                assert not errors, 'Browser JavaScript errors'
                context.close();browser.close()
            output.flush()
            assert CANARY not in log.read_text()
            print(json.dumps({'browser':'system Chromium','result':'passed','checks':['empty profile','fictional demo','three ratings','pick','another is not feedback','post-watch reaction','process restart persistence','hard empty state','reset skips','mobile layout','disclosure canary','no external requests','no JavaScript errors','history edits invalidate current pick'],'responses_inspected':len(delivered),'history_count':5,'artifacts':str(ARTIFACTS)},indent=2))
        finally:
            if process and process.poll() is None: stop(process)
            output.close()

if __name__=='__main__':run()
