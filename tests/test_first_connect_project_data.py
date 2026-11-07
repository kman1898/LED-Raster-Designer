"""The project the server sends when the page's socket first connects.

It lands a few ms after the page's own load has finished (measured on every
load), so it is the project as it was before anything the page did since.
The page used to adopt it, and an edit made in that gap fell off the page:
CI, 2026-10-18, a wall seeded right after load weighed 0 kg. The first
connect's copy is now dropped once the load is done; a reconnect's copy
still applies.
"""
import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    yield


# Holds every project_data the page's socket receives for `ms`, the way a
# slow first connect delivers it after the load.
DELAY_PROJECT_DATA = """(() => {
    const ms = %d;
    let real;
    Object.defineProperty(window, 'io', {
        configurable: true,
        get() { return real; },
        set(v) {
            real = function (...args) {
                const s = v(...args), on = s.on.bind(s);
                s.on = (ev, h) => on(ev, ev === 'project_data'
                    ? (...x) => setTimeout(() => { h(...x); window.__projectDataLanded = (window.__projectDataLanded || 0) + 1; }, ms) : h);
                return s;
            };
            Object.assign(real, v);
        },
    });
})();"""


def _open(e2e_server, pw_browser, delay_ms):
    ctx = pw_browser.new_context()
    ctx.add_init_script("try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    ctx.add_init_script(DELAY_PROJECT_DATA % delay_ms)
    pg = ctx.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    return ctx, pg, errors


RENAME_JS = """async (name) => {
    const app = window.app;
    const l = app.project.layers[0];
    l.name = name;
    await app.updateLayers([l]);
    await app._layerSavesSettled();
    return l.id;
}"""


def test_an_edit_made_before_the_first_connect_lands_stays_on_the_page(e2e_server, pw_browser):
    ctx, pg, errors = _open(e2e_server, pw_browser, 400)
    try:
        lid = pg.evaluate(RENAME_JS, 'RENAMED AFTER LOAD')
        pg.wait_for_timeout(700)   # the held project_data has landed by now
        assert pg.evaluate("() => window.__projectDataLanded") == 1
        name = pg.evaluate("(id) => window.app.project.layers.find(l => l.id === id).name", lid)
        assert name == 'RENAMED AFTER LOAD'
        assert errors == []
    finally:
        ctx.close()


def test_a_reconnect_still_takes_the_servers_project(e2e_server, pw_browser):
    ctx, pg, errors = _open(e2e_server, pw_browser, 0)
    try:
        pg.wait_for_function("() => window.__projectDataLanded === 1")
        # the server changes behind the page's back, then the socket reconnects
        pg.evaluate("""async () => {
            const p = await (await fetch('/api/project')).json();
            p.layers[0].name = 'CHANGED ON THE SERVER';
            await fetch('/api/project', { method: 'PUT',
                headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(p) });
            window.app.socket.disconnect();
            window.app.socket.connect();
        }""")
        pg.wait_for_function("() => window.app.project.layers[0].name === 'CHANGED ON THE SERVER'",
                             timeout=10000)
        assert errors == []
    finally:
        ctx.close()


# New Project's raster sync is a POST the page sends on its own. File >
# Open's PUT and an undo's restore wait on _layerSavesSettled before they
# write; the sync was not among the saves it waits on, so landing late it
# put the new show's default raster on the opened one. Held here until the
# check has run.
HELD_NEW_PROJECT_SYNC_JS = """async () => {
    const app = window.app, orig = window.fetch;
    let letGo, held = false;
    const gate = new Promise(r => { letGo = r; });
    window.fetch = (url, opts) => {
        if (url === '/api/project' && opts && opts.method === 'POST' && !held
                && String(opts.body || '').includes('keep_pristine')) {
            held = true;
            return gate.then(() => orig(url, opts));
        }
        return orig(url, opts);
    };
    try {
        app.createNewProject();
        for (let i = 0; i < 200 && !held; i++) await new Promise(r => setTimeout(r, 10));
        let settled = false;
        app._layerSavesSettled().then(() => { settled = true; });
        await new Promise(r => setTimeout(r, 200));
        const waitedWhileHeld = held && !settled;
        letGo();
        await app._layerSavesSettled();
        return { held, waitedWhileHeld };
    } finally {
        window.fetch = orig;
    }
}"""


def test_open_and_undo_wait_for_the_new_project_sync(e2e_server, pw_browser):
    ctx, pg, errors = _open(e2e_server, pw_browser, 0)
    try:
        pg.evaluate("() => { window.confirm = () => true; }")
        out = pg.evaluate(HELD_NEW_PROJECT_SYNC_JS)
        assert out == {'held': True, 'waitedWhileHeld': True}, out
        assert errors == []
    finally:
        ctx.close()
