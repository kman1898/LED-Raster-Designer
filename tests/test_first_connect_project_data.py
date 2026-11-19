"""The project the server sends when the page's socket first connects.

It lands a few ms after the page's own load has finished (measured on every
load), so it is the project as it was before anything the page did since.
The page used to adopt it, and an edit made in that gap fell off the page:
CI, 2026-10-18, a wall seeded right after load weighed 0 kg. The first
connect's copy is now dropped once the load is done, when it is the show the
load read; a first connect that completes only after another page changed
the show reads the show again and follows it. A reconnect's copy still
applies.
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


# ── A first connect that completes after another page changed the show ──
#
# The page's socket is made with its connect held back, so the page loads
# from its own read and only then connects: the way a slow join, or a drop
# in the middle of the handshake, lands. Whatever another page changed in
# between, this page never heard of; the first connect's copy is the only
# news of it.
HOLD_FIRST_CONNECT = """(() => {
    let real;
    Object.defineProperty(window, 'io', {
        configurable: true,
        get() { return real; },
        set(v) {
            real = function (...args) {
                if (typeof args[0] === 'string') args[1] = Object.assign({}, args[1], { autoConnect: false });
                else args = [Object.assign({}, args[0], { autoConnect: false })];
                const s = v(...args);
                window.__letConnect = () => s.connect();
                return s;
            };
            Object.assign(real, v);
        },
    });
})();"""


@pytest.fixture()
def page_log(monkeypatch):
    """The page's own log lines, as the server takes them (action, details)."""
    import routes_logs
    lines = []
    real = routes_logs.log_event

    def keep(action, details=None, source='server'):
        if source == 'client':
            lines.append((action, dict(details or {}) if isinstance(details, dict) else {}))
        return real(action, details, source=source)
    monkeypatch.setattr(routes_logs, 'log_event', keep)
    return lines


def _open_held(e2e_server, pw_browser):
    ctx = pw_browser.new_context()
    ctx.add_init_script("try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    ctx.add_init_script(HOLD_FIRST_CONNECT)
    pg = ctx.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    assert pg.evaluate("() => !!window.app.socket && !window.app.socket.connected")
    return ctx, pg, errors


def _another_page_renames(e2e_server, layer_id, name):
    """Another device renames a screen: one layer_updated to every page
    connected then, and nothing to a page still joining."""
    import json as _json
    import urllib.request
    req = urllib.request.Request(
        e2e_server.rstrip('/') + f'/api/layer/{layer_id}?edited=1',
        data=_json.dumps({'name': name}).encode('utf-8'), method='PUT',
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=10) as res:
        assert res.status == 200


def _actions(page_log):
    return [a for a, _ in page_log]


def test_a_first_connect_after_another_page_changed_the_show_takes_the_change(
        e2e_server, pw_browser, page_log):
    ctx, pg, errors = _open_held(e2e_server, pw_browser)
    try:
        lid = pg.evaluate("() => window.app.project.layers[0].id")
        before = pg.evaluate("() => window.app.project.layers[0].name")
        _another_page_renames(e2e_server, lid, 'RENAMED ON ANOTHER PAGE')
        pg.wait_for_timeout(300)
        # the page heard nothing: its socket has not connected
        assert pg.evaluate("(id) => window.app.project.layers.find(l => l.id === id).name", lid) == before
        pg.evaluate("() => window.__letConnect()")
        pg.wait_for_function(
            "(id) => window.app.project.layers.find(l => l.id === id).name === 'RENAMED ON ANOTHER PAGE'",
            arg=lid, timeout=10000)
        # and the Screens list says so
        pg.wait_for_function(
            "() => [...document.querySelectorAll('#layers-list input.layer-name-input')]"
            ".some(e => e.value === 'RENAMED ON ANOTHER PAGE')",
            timeout=5000)
        assert pg.evaluate("() => window.app._socketConnects") == 1
        # the page's log lines go by beacon: they land a moment later
        from conftest import settled
        acts = settled(pg, lambda: _actions(page_log),
                       lambda a: {'socket_project_data_first_differs', 'first_connect_reread'} <= set(a))
        assert 'socket_project_data_first_differs' in acts, acts
        assert 'first_connect_reread' in acts, acts
        assert 'socket_project_data_skipped' not in acts, acts
        assert errors == []
    finally:
        ctx.close()


def test_a_first_connect_with_nothing_changed_is_dropped_as_before(
        e2e_server, pw_browser, page_log):
    ctx, pg, errors = _open_held(e2e_server, pw_browser)
    try:
        pg.evaluate("() => window.__letConnect()")
        pg.wait_for_function("() => window.app._firstProjectDataSeen === true", timeout=10000)
        from conftest import settled
        skipped = settled(pg, lambda: [d for a, d in page_log if a == 'socket_project_data_skipped'],
                          lambda found: bool(found))
        assert [d.get('reason') for d in skipped] == ['first_connect_after_load'], _actions(page_log)
        assert 'socket_project_data_first_differs' not in _actions(page_log)
        assert errors == []
    finally:
        ctx.close()
