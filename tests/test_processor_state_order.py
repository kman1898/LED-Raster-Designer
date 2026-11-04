"""An older answer never puts an older processor tree back (2026-10-30).

A refresh of the processor tree sent before a rename and answered after the
rename's own reply put the old name back on the page while the server held
the new one (seen as a binder test reading "SX40 S3" after a rename to
"SX40 MAIN" on a loaded machine). Every reply that carries the tree is now
numbered by the server before it reads the tree (app.processor_state_stamp),
and the page drops an answer older than the newest it has applied.

Run locally (each session takes its own free port):
    python3 -m pytest tests/test_processor_state_order.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


SEED_JS = """async () => {
    const j = (m, u, b) => fetch(u, {method: m, headers: {'Content-Type': 'application/json'},
                                      body: b === undefined ? undefined : JSON.stringify(b)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.processors = []; await j('PUT', '/api/project', proj);
    const st = await j('POST', '/api/processors', {deviceId: 'brompton-sx40', name: 'OLD'});
    window.app.project = await j('GET', '/api/project');
    await window.app.refreshProcessors();
    return st.processors[0].id;
}"""

RENAME_JS = """async (pid) => {
    const r = await fetch(`/api/processors/${pid}`, {method: 'PUT',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name: 'NEW'})});
    window.app._applyProcessorState(await r.json());
}"""


@pytest.fixture()
def page(e2e_server, pw_browser):
    ctx = pw_browser.new_context()
    ctx.add_init_script("try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = ctx.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    yield pg, errors
    ctx.close()


def _hold_first_read(pg):
    """Answer the first GET /api/processors from the server's state as it is
    now, but hand it to the page only when the test says so."""
    held = []

    def handler(route):
        if not held and route.request.method == 'GET':
            held.append((route, route.fetch()))
            return
        route.continue_()
    pg.route("**/api/processors", handler)
    return held


def test_a_read_answered_after_a_rename_never_puts_the_old_name_back(page):
    pg, errors = page
    pid = pg.evaluate(SEED_JS)
    held = _hold_first_read(pg)
    pg.evaluate("() => { window.__stale = window.app.refreshProcessors(); }")
    pg.wait_for_function("() => true")
    for _ in range(50):
        if held:
            break
        pg.wait_for_timeout(50)
    assert held, 'the first read never went out'
    pg.evaluate(RENAME_JS, pid)
    assert pg.evaluate("() => window.app.project.processors[0].name") == 'NEW'
    route, resp = held[0]
    route.fulfill(response=resp)
    pg.evaluate("() => window.__stale")
    pg.wait_for_timeout(200)
    assert pg.evaluate("() => window.app.project.processors[0].name") == 'NEW'
    assert errors == []


def test_a_newer_read_still_lands():
    """The stamp only ever goes up within one server, and a restarted
    server's stamps are told apart by their boot id."""
    import app
    a, b = app.processor_state_stamp(), app.processor_state_stamp()
    assert a['boot'] == b['boot'] and b['n'] > a['n']
