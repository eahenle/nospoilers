"""Real-browser regression for mode changes while catalog requests are pending."""
import os
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

from nospoilers.server import Service, make_server
from nospoilers.store import Store


def run():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / 'state.sqlite3')
        for mode in ('real', 'demo'):
            store.ingest({'version': 1, 'mode': mode,
                          'movies': [{'id': 'fixture:shared', 'title': mode + ' title', 'year': 2000}],
                          'history': [{'id': 'fixture:shared', 'rating': 'liked'}] if mode == 'demo' else []})
        server = make_server(Service(store), port=0)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True, executable_path=os.environ.get('CHROMIUM_PATH', '/usr/bin/chromium'))
                try:
                    page = browser.new_page()
                    page.add_init_script("localStorage.setItem('nospoilers-mode', 'demo')")
                    page.goto(f'http://127.0.0.1:{server.server_port}')
                    expect(page.locator('#history-count')).to_have_text('1')
                    page.locator('.nav[data-view="history"]').click()
                    expect(page.locator('#history-list')).to_contain_text('demo title')
                    held = []
                    page.route('**/api/state?mode=real', lambda route: held.append(route))
                    page.locator('#mode').select_option('real')
                    page.wait_for_function("document.querySelector('#mode').value === 'real'")
                    # Pending refresh must never leave a demo reaction button usable in real mode.
                    stale = page.locator('#history-list button')
                    if stale.count():
                        with page.expect_response('**/api/reaction'):
                            stale.click()
                    assert store.history('real') == [], 'A stale demo row wrote into personal history'
                    expect(stale).to_have_count(0)
                    for route in held:
                        route.abort()
                finally:
                    browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    run()
    print('Mode isolation regression passed')
