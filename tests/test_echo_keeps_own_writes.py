"""Another page's change never takes back a save this page has on its way,
and Quick Palettes always shows the screen's colors as the page holds them.

1. Another page's change of a screen (its layer_updated) was taken as the
   server's word on every field, even while this page still had saves of
   that screen on their way: queued, sent and not yet answered, or answered
   while the server's own copy of them had not reached the page yet. The
   other page's copy holds the screen as it was before those saves, so the
   page put back what it had just changed (a Quick Palette's colors, a
   blanked cabinet) while the server went on to keep the new values.
   Now (app-core _layerWritesOutKeys) every write of a screen notes the
   fields it changes, from what the page last knew the server held, and
   until the server's copy of that write reaches the page the other page's
   copy keeps this page's values for those fields. Every other field is
   the other page's: a rename made there shows here at once.

2. Quick Palettes was redrawn when Screen Info filled and when the panel
   itself changed the colors, never when the page's own save came back
   changed: its pressed pair stayed on colors the screen no longer had.
   It is now redrawn with the rest of the page (updateUI), the same
   buttons kept, so a press on one is never lost to a redraw.

The timings are forced here (held requests, held socket copies), so each
test fails the same way every time without the fix.

Run locally:
    python -m pytest tests/test_echo_keeps_own_writes.py -v
"""
import json

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# Page A's holds: `__gate.hold = 'put'` holds the next PUT of a screen (and
# `'hidden'` the next set_hidden POST) before it goes, until
# `__gate.release()`; `__gate.closeSock()` holds every socket layer_updated
# until `__gate.openSock()`, which plays them in order and notes the
# screen's colors and first cabinet after each one.
GATE = """(() => {
    const G = window.__gate = { hold: null, waiting: [], sockOpen: true, sockQ: [], seen: [] };
    const real = window.fetch;
    window.fetch = function (input, init) {
        const url = String(input), method = (init && init.method) || 'GET';
        const held = (G.hold === 'put' && method === 'PUT' && /\\/api\\/layer\\/\\d+\\?/.test(url))
            || (G.hold === 'hidden' && method === 'POST' && url.includes('/panels/set_hidden'));
        if (held) {
            G.hold = null;
            const self = this, args = arguments;
            return new Promise(r => G.waiting.push(() => r(real.apply(self, args))));
        }
        return real.apply(this, arguments);
    };
    G.release = () => G.waiting.splice(0).forEach(f => f());
    G.closeSock = () => { G.sockOpen = false; };
    G.note = () => {
        const app = window.app, l = app && app.project && app.project.layers.find(x => x.id === G.id);
        if (!l) return;
        G.seen.push({ pair: JSON.stringify([l.color1, l.color2].map(c => c && [c.r, c.g, c.b])),
                      name: l.name });
    };
    G.openSock = () => {
        G.sockOpen = true;
        G.sockQ.splice(0).forEach(f => { f(); G.note(); });
    };
    let io;
    Object.defineProperty(window, 'io', {
        configurable: true,
        get() { return io; },
        set(v) {
            io = function (...args) {
                const s = v(...args), on = s.on.bind(s);
                s.on = (ev, h) => on(ev, ev === 'layer_updated'
                    ? (...x) => { if (G.sockOpen) h(...x); else G.sockQ.push(() => h(...x)); } : h);
                return s;
            };
            Object.assign(io, v);
        },
    });
})();"""

PAIR = """(l) => JSON.stringify([l.color1, l.color2].map(c => c && [c.r, c.g, c.b]))"""


def _open(pw_browser, url, init=None):
    ctx = pw_browser.new_context(viewport={'width': 1440, 'height': 900})
    ctx.add_init_script("try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    if init:
        ctx.add_init_script(init)
    pg = ctx.new_page()
    pg.goto(url, wait_until='domcontentloaded')
    pg.wait_for_function(
        "() => !!(window.app && window.app._initialLoadComplete && window.app.socket"
        " && window.app.socket.connected)", timeout=120000)
    pg.wait_for_timeout(600)
    return ctx, pg


def _start(e2e_server):
    """One screen, named START, on the shipped colors, nothing blanked."""
    import urllib.request
    base = e2e_server.rstrip('/')
    proj = json.loads(urllib.request.urlopen(base + '/api/project').read())
    screen = next(l for l in proj['layers'] if (l.get('type') or 'screen') == 'screen')
    for p in screen.get('panels') or []:
        p['hidden'] = False
    body = {'name': 'START', 'color1': {'r': 64, 'g': 70, 'b': 128},
            'color2': {'r': 149, 'g': 156, 'b': 184}, 'panelColorMode': 'checker',
            'transparentFill': False, 'locked': False}
    urllib.request.urlopen(urllib.request.Request(
        f"{base}/api/layer/{screen['id']}", method='PUT', data=json.dumps(body).encode(),
        headers={'Content-Type': 'application/json'})).read()
    hidden = [{'id': p['id'], 'hidden': False} for p in screen.get('panels') or []]
    if hidden:
        urllib.request.urlopen(urllib.request.Request(
            f"{base}/api/layer/{screen['id']}/panels/set_hidden", method='POST',
            data=json.dumps({'panels': hidden}).encode(),
            headers={'Content-Type': 'application/json'})).read()
    return screen['id']


def _select(pg, layer_id):
    pg.evaluate("""(id) => {
        const a = window.app, l = a.project.layers.find(x => x.id === id);
        a.selectLayer(l);
        if (typeof a.loadQuickPalettes === 'function') a.loadQuickPalettes();
        window.__gate && (window.__gate.id = id);
    }""", layer_id)
    pg.wait_for_timeout(200)


# Page A colors the screen with a Quick Palette, a pair other than the one
# it has, and answers the pair it had and the pair it wants.
APPLY_PALETTE = """() => {
    const a = window.app, l = a.currentLayer;
    const pair = """ + PAIR + """;
    const before = pair(l);
    const have = a._qpPairOf(l).join('|');
    const i = a.getQuickPalettes().findIndex(p => p.join('|') !== have);
    a.applyQuickPalette(i);
    return { before, want: pair(l), index: i };
}"""

RENAME_ON_B = """async ([id, name]) => {
    const a = window.app, l = a.project.layers.find(x => x.id === id);
    l.name = name;
    a.updateLayers([l]);
    await a._layerSavesSettled();
}"""

READ_A = """(id) => {
    const a = window.app, l = a.project.layers.find(x => x.id === id);
    const pair = """ + PAIR + """;
    return { pair: pair(l), name: l.name, hidden: l.panels.filter(p => p.hidden).map(p => p.id) };
}"""


def _server(e2e_server, layer_id):
    import urllib.request
    proj = json.loads(urllib.request.urlopen(e2e_server.rstrip('/') + '/api/project').read())
    l = next(x for x in proj['layers'] if x['id'] == layer_id)
    pair = json.dumps([[c['r'], c['g'], c['b']] for c in (l['color1'], l['color2'])], separators=(',', ':'))
    return {'pair': pair, 'name': l['name'],
            'hidden': [p['id'] for p in l.get('panels') or [] if p.get('hidden')]}


def _settle(pg):
    pg.evaluate("() => window.app._layerSavesSettled()")
    pg.wait_for_timeout(700)


# ── 1. another page's change while this page's save is on its way ─────────

def test_another_pages_change_keeps_a_save_still_on_its_way(e2e_server, pw_browser):
    """Page A's Quick Palette save is held before it reaches the server;
    page B renames the screen meanwhile. A takes the new name at once and
    keeps its own colors; once A's save lands both pages and the server
    hold A's colors."""
    layer_id = _start(e2e_server)
    b_ctx, b = _open(pw_browser, e2e_server)
    a_ctx, a = _open(pw_browser, e2e_server, GATE)
    try:
        _select(a, layer_id)
        a.evaluate("() => { window.__gate.hold = 'put'; }")
        out = a.evaluate(APPLY_PALETTE)
        assert out['want'] != out['before'], out
        b.evaluate(RENAME_ON_B, [layer_id, 'FROM B'])
        a.wait_for_function("(id) => window.app.project.layers.find(x => x.id === id).name === 'FROM B'",
                            arg=layer_id, timeout=10000)
        mid = a.evaluate(READ_A, layer_id)
        assert mid['name'] == 'FROM B', (mid, out)
        assert mid['pair'] == out['want'], ('the other page took back the held save', mid, out)
        a.evaluate("() => window.__gate.release()")
        _settle(a)
        end = a.evaluate(READ_A, layer_id)
        server = _server(e2e_server, layer_id)
        assert end['pair'] == out['want'] == server['pair'], (end, server, out)
        assert end['name'] == server['name'], (end, server)
    finally:
        a_ctx.close()
        b_ctx.close()


def test_another_pages_copy_landing_after_the_reply_keeps_the_save(e2e_server, pw_browser):
    """The server takes page B's rename first and A's save after it, but
    A's socket copies arrive only after A's save has been answered: B's
    copy (the screen before A's save) lands with nothing of A's still
    counted as on its way. A's colors never go back."""
    layer_id = _start(e2e_server)
    b_ctx, b = _open(pw_browser, e2e_server)
    a_ctx, a = _open(pw_browser, e2e_server, GATE)
    try:
        _select(a, layer_id)
        a.evaluate("() => { window.__gate.hold = 'put'; window.__gate.closeSock(); }")
        out = a.evaluate(APPLY_PALETTE)
        b.evaluate(RENAME_ON_B, [layer_id, 'FROM B'])
        a.evaluate("() => window.__gate.release()")
        a.evaluate("() => window.app._layerSavesSettled()")
        a.wait_for_function("() => window.__gate.sockQ.length >= 2", timeout=10000)
        a.evaluate("() => window.__gate.openSock()")
        seen = a.evaluate("() => window.__gate.seen")
        assert seen, seen
        assert all(s['pair'] == out['want'] for s in seen), ('a copy put the older colors back', seen, out)
        _settle(a)
        end = a.evaluate(READ_A, layer_id)
        server = _server(e2e_server, layer_id)
        assert end['pair'] == out['want'] == server['pair'], (end, server, out)
        assert end['name'] == server['name'], (end, server)
    finally:
        a_ctx.close()
        b_ctx.close()


def test_another_pages_change_keeps_a_blank_still_on_its_way(e2e_server, pw_browser):
    """Page A blanks a cabinet and its POST is held; page B renames the
    screen. A takes the name and the cabinet stays blank."""
    layer_id = _start(e2e_server)
    b_ctx, b = _open(pw_browser, e2e_server)
    a_ctx, a = _open(pw_browser, e2e_server, GATE)
    try:
        _select(a, layer_id)
        a.evaluate("() => { window.__gate.hold = 'hidden'; }")
        panel = a.evaluate("""(id) => {
            const a = window.app, l = a.project.layers.find(x => x.id === id);
            const p = l.panels.find(q => !q.hidden);
            a.setPanelsBlankBulk([p], true);
            return p.id;
        }""", layer_id)
        b.evaluate(RENAME_ON_B, [layer_id, 'FROM B'])
        a.wait_for_function("(id) => window.app.project.layers.find(x => x.id === id).name === 'FROM B'",
                            arg=layer_id, timeout=10000)
        mid = a.evaluate(READ_A, layer_id)
        assert panel in mid['hidden'], ('the other page took back the held blank', mid, panel)
        a.evaluate("() => window.__gate.release()")
        _settle(a)
        end = a.evaluate(READ_A, layer_id)
        server = _server(e2e_server, layer_id)
        assert panel in end['hidden'] and panel in server['hidden'], (end, server, panel)
    finally:
        a_ctx.close()
        b_ctx.close()


def test_with_nothing_on_its_way_the_other_pages_colors_come_through(e2e_server, pw_browser):
    """Real collaboration still works: with no save of A's on its way, B's
    Quick Palette shows on A, and A's Quick Palettes press it."""
    layer_id = _start(e2e_server)
    a_ctx, a = _open(pw_browser, e2e_server, GATE)
    b_ctx, b = _open(pw_browser, e2e_server)
    try:
        _select(a, layer_id)
        _select(b, layer_id)
        out = b.evaluate(APPLY_PALETTE)
        b.evaluate("() => window.app._layerSavesSettled()")
        a.wait_for_function("([id, want]) => { const l = window.app.project.layers.find(x => x.id === id);"
                            " return JSON.stringify([l.color1, l.color2].map(c => c && [c.r, c.g, c.b])) === want; }",
                            arg=[layer_id, out['want']], timeout=10000)
        pressed = a.evaluate(PRESSED)
        assert pressed['pressed'] == pressed['matching'], pressed
    finally:
        a_ctx.close()
        b_ctx.close()


# ── 2. Quick Palettes follows the screen ──────────────────────────────────

# The swatch the panel shows pressed, and the one the screen's colors match.
PRESSED = """() => {
    const a = window.app;
    const on = [...document.querySelectorAll('#quick-palette-swatches .qp-swatch')]
        .findIndex(b => b.getAttribute('aria-pressed') === 'true');
    const have = a._qpPairOf(a.currentLayer).join('|');
    return { pressed: on, matching: a.getQuickPalettes().findIndex(p => p.join('|') === have), have };
}"""


def test_quick_palettes_follows_the_page_s_own_save_coming_back_changed(e2e_server, pw_browser):
    """The server keeps other colors than the page's save sent (as it does
    when a later write of another page lands first): the save's answer and
    its socket copy bring them back, the screen takes them, and Quick
    Palettes no longer shows the pair the page sent as pressed."""
    layer_id = _start(e2e_server)
    ctx, pg = _open(pw_browser, e2e_server, GATE)
    try:
        _select(pg, layer_id)

        def changed(route, request):
            body = json.loads(request.post_data or '{}')
            if 'color1' in body:
                body['color1'] = {'r': 10, 'g': 200, 'b': 30}
                body['color2'] = {'r': 250, 'g': 240, 'b': 5}
                route.continue_(post_data=json.dumps(body))
            else:
                route.continue_()
        pg.route(f'**/api/layer/{layer_id}?*', changed)
        out = pg.evaluate(APPLY_PALETTE)
        assert pg.evaluate(PRESSED)['pressed'] == out['index']
        pg.wait_for_function("(id) => window.app.project.layers.find(x => x.id === id).color1.g === 200",
                             arg=layer_id, timeout=10000)
        _settle(pg)
        pressed = pg.evaluate(PRESSED)
        assert pressed['matching'] == -1, pressed
        assert pressed['pressed'] == pressed['matching'], ('Quick Palettes still shows the sent pair', pressed, out)
        # the panel redraw keeps its buttons: a press is never lost to it
        same = pg.evaluate("""() => {
            const before = document.getElementById('quick-palette-2');
            window.app.updateUI();
            return before === document.getElementById('quick-palette-2');
        }""")
        assert same is True
    finally:
        ctx.close()
