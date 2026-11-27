"""A save made before the page replaced its whole show never comes back on it.

1. The server sends every write of a screen back over the socket (its echo,
   layer_updated, stamped with the write's number). The page took the echo
   of its own newest write of a screen as the server's word, even when the
   page had since put a whole show in place: a guide's end putting the
   person's show back, an undo or a redo, a show opened or made new, or the
   show read again from the server. The replace waits for the page's saves
   before it, so the server keeps the replace; but on a slow socket the
   echo of a save made before it came after the replace's own answer, and
   the page put the older screen back over the show it had just put in
   place. Leaving the Pixel Map guide's Quick Palettes step that way left
   the guide's Hue-turned colors on the person's screen while the server
   kept the person's own (CI, test_quick_palettes, once).
   Now (app-core _noteShowReplaced) each replace notes how far the page's
   writes of each screen had got, and the echo of a write from before it is
   dropped (socket_layer_updated_suppressed_replaced). An undo's or a
   guide's restore also waits for every save of a screen still on its way,
   not only the ones it tracked.

2. The single-cabinet blank and hide helpers (togglePanelBlank,
   togglePanelHidden) posted on their own, outside the screen's order of
   writes, and their routes sent an echo with no write number. They are now
   the same verb as Alt+click and Set Blank (setPanelsBlankBulk): in the
   screen's order of writes, one undo step, and every single-cabinet route
   stamps its echo (routes_layers _emit_layer_echo).

The socket copies are held here until after the replace has been answered,
so each browser test fails the same way every time without the fix.

Run locally:
    python -m pytest tests/test_replace_drops_old_echoes.py -v
"""
import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


# Every socket layer_updated is held from __hold.close() until
# __hold.open(), which plays them in the order they came.
HOLD = """(() => {
    const H = window.__hold = { shut: false, queue: [], held: 0 };
    H.close = () => { H.shut = true; };
    H.open = () => { H.shut = false; H.queue.splice(0).forEach(f => f()); };
    let io;
    Object.defineProperty(window, 'io', {
        configurable: true,
        get() { return io; },
        set(v) {
            io = function (...args) {
                const s = v(...args), on = s.on.bind(s);
                s.on = (ev, h) => on(ev, ev === 'layer_updated'
                    ? (...x) => { if (!H.shut) h(...x); else { H.held++; H.queue.push(() => h(...x)); } }
                    : h);
                return s;
            };
            Object.assign(io, v);
        },
    });
})();"""

HEX = """(id) => {
    const a = window.app, l = a.project.layers.find(x => x.id === id);
    const hex = c => a.rgbToHex(c.r, c.g, c.b).toUpperCase();
    return [hex(l.color1), hex(l.color2)];
}"""

MINE = ['#573E78', '#A198B4']


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


def _open(pw_browser, url):
    ctx = pw_browser.new_context(viewport={'width': 1440, 'height': 900})
    ctx.add_init_script("try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    ctx.add_init_script(HOLD)
    pg = ctx.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(url, wait_until='domcontentloaded')
    pg.wait_for_function(
        "() => !!(window.app && window.app._initialLoadComplete && window.app.socket"
        " && window.app.socket.connected && window.QuickStart)", timeout=120000)
    pg.wait_for_timeout(600)
    return ctx, pg, errors


def _mine(pg):
    """The first screen on MINE, selected, its saves landed and echoed, a
    clean history. Returns its id."""
    sid = pg.evaluate("""async (pair) => {
        const a = window.app;
        const l = a.project.layers.find(x => (x.type || 'screen') === 'screen');
        l.locked = false;
        l.color1 = a.hexToRgb(pair[0]);
        l.color2 = a.hexToRgb(pair[1]);
        l.panelColorMode = 'checker';
        l.transparentFill = false;
        a.updateLayers([l]);
        await a._layerSavesSettled();
        a.selectLayer(a.project.layers.find(x => x.id === l.id));
        if (typeof a.loadQuickPalettes === 'function') a.loadQuickPalettes();
        a.resetHistory('Echo Seed');
        return l.id;
    }""", MINE)
    pg.wait_for_timeout(600)
    assert pg.evaluate(HEX, sid) == MINE
    return sid


def _server_pair(pg, sid):
    return pg.evaluate("""async (id) => {
        const a = window.app;
        const l = (await (await fetch('/api/project')).json()).layers.find(x => x.id === id);
        const hex = c => a.rgbToHex(c.r, c.g, c.b).toUpperCase();
        return [hex(l.color1), hex(l.color2)];
    }""", sid)


def _restored(pg):
    pg.wait_for_function("""() => {
        const a = window.app;
        return !a._restorePutPending && !(a._restorePutsInFlight && a._restorePutsInFlight.size);
    }""", timeout=30000)
    pg.wait_for_timeout(300)


def _play_held(pg):
    held = pg.evaluate("() => window.__hold.held")
    pg.evaluate("() => window.__hold.open()")
    pg.wait_for_timeout(600)
    return held


def test_leaving_a_guide_keeps_the_persons_colors_when_its_last_echo_lands_late(e2e_server, pw_browser):
    """The Quick Palettes step on its own, every socket copy held from
    before it starts until after its end has been answered: the guide's
    Hue save's echo lands on the person's show, and is dropped."""
    ctx, pg, errors = _open(pw_browser, e2e_server)
    try:
        sid = _mine(pg)
        pg.evaluate("() => window.__hold.close()")
        pg.evaluate("() => { window.QuickStart.setSpeed(6); window.QuickStart.startSteps(['quickPalettes']); }")
        pg.wait_for_function("""() => {
            const c = document.getElementById('qs-callout');
            return c && c.getAttribute('data-qs-state') === 'done';
        }""", timeout=30000)
        assert pg.evaluate(HEX, sid) != MINE, 'the step changed nothing'
        pg.evaluate("() => window.QuickStart.end()")
        pg.wait_for_function("() => !window.QuickStart.state().running && !window.QuickStart.state().visible")
        _restored(pg)
        assert pg.evaluate(HEX, sid) == MINE
        assert _play_held(pg) > 0, 'nothing was held: the test proves nothing'
        assert pg.evaluate(HEX, sid) == MINE, 'the guide\'s last save came back on the person\'s show'
        assert _server_pair(pg, sid) == MINE
        assert errors == []
    finally:
        ctx.close()


def test_an_undo_keeps_its_colors_when_the_undone_saves_echo_lands_late(e2e_server, pw_browser):
    """A Quick Palette, its save answered, then Undo: the palette's echo,
    held until the undo has been answered, is dropped."""
    ctx, pg, errors = _open(pw_browser, e2e_server)
    try:
        sid = _mine(pg)
        pg.evaluate("() => window.__hold.close()")
        pg.evaluate("""async () => {
            const a = window.app, have = a._qpPairOf(a.currentLayer).join('|');
            a.applyQuickPalette(a.getQuickPalettes().findIndex(p => p.join('|') !== have));
            await a._layerSavesSettled();
        }""")
        assert pg.evaluate(HEX, sid) != MINE, 'the palette changed nothing'
        pg.evaluate("() => window.app.undo()")
        _restored(pg)
        assert pg.evaluate(HEX, sid) == MINE
        assert _play_held(pg) > 0, 'nothing was held: the test proves nothing'
        assert pg.evaluate(HEX, sid) == MINE, 'the undone save came back after the undo'
        assert _server_pair(pg, sid) == MINE
        # a save made after the undo still comes back as the page's own
        pg.evaluate("""async () => {
            const a = window.app, have = a._qpPairOf(a.currentLayer).join('|');
            a.applyQuickPalette(a.getQuickPalettes().findIndex(p => p.join('|') !== have));
            await a._layerSavesSettled();
        }""")
        pg.wait_for_timeout(600)
        after = pg.evaluate(HEX, sid)
        assert after != MINE and _server_pair(pg, sid) == after
        assert errors == []
    finally:
        ctx.close()


def test_a_restore_waits_for_a_save_it_was_not_told_of(e2e_server, pw_browser):
    """A rename's save (a bare _putLayer, outside the tracked batches) still
    on its way when Undo restores the show: the restore goes after it, so
    the server ends on the show the undo put back."""
    ctx, pg, errors = _open(pw_browser, e2e_server)
    try:
        sid = _mine(pg)
        out = pg.evaluate("""async (id) => {
            const a = window.app, real = window.fetch;
            const was = a.project.layers.find(x => x.id === id).name;
            let let_go;
            const gate = new Promise(r => { let_go = r; });
            window.fetch = function (input, init) {
                const url = String(input), method = (init && init.method) || 'GET';
                if (method === 'PUT' && /\\/api\\/layer\\/\\d+\\?/.test(url)) {
                    window.fetch = real;
                    const self = this, args = arguments;
                    return gate.then(() => real.apply(self, args));
                }
                return real.apply(this, arguments);
            };
            a.saveState('Before Rename');
            const l = a.project.layers.find(x => x.id === id);
            l.name = 'RENAMED';
            a._putLayer(id, { name: 'RENAMED' });
            a.saveState('Rename');
            // the rename is sent (and held) before the undo
            await new Promise(r => setTimeout(r, 100));
            a.undo();
            await new Promise(r => setTimeout(r, 400));
            let_go();
            await a._layerSavesSettled();
            await new Promise(r => setTimeout(r, 400));
            const srv = (await (await fetch('/api/project')).json()).layers.find(x => x.id === id);
            return { was, page: a.project.layers.find(x => x.id === id).name, server: srv.name };
        }""", sid)
        assert out['page'] == out['was'], out
        assert out['server'] == out['was'], ('the rename landed after the undo', out)
        assert errors == []
    finally:
        ctx.close()


def test_the_single_cabinet_toggles_go_in_the_screens_order(e2e_server, pw_browser):
    """togglePanelHidden and togglePanelBlank post through the screen's
    order of writes (numbered, so the echo is known for the page's own) and
    take one undo step each, as Alt+click does."""
    ctx, pg, errors = _open(pw_browser, e2e_server)
    try:
        sid = _mine(pg)
        out = pg.evaluate("""async (id) => {
            const a = window.app, real = window.fetch, urls = [];
            window.fetch = function (input, init) {
                const url = String(input), method = (init && init.method) || 'GET';
                if (method === 'POST' && url.includes('/api/layer/')) urls.push(url);
                return real.apply(this, arguments);
            };
            const l = a.project.layers.find(x => x.id === id);
            const [p1, p2] = l.panels.filter(p => !p.hidden);
            const n0 = a.historyIndex;
            await a.togglePanelHidden(id, p1.id);
            await a.togglePanelBlank(id, p2.id);
            await a._layerSavesSettled();
            window.fetch = real;
            const live = a.project.layers.find(x => x.id === id);
            const srv = (await (await fetch('/api/project')).json()).layers.find(x => x.id === id);
            const hid = (layer, pid) => !!layer.panels.find(p => p.id === pid).hidden;
            const out = { urls, steps: a.historyIndex - n0,
                          page: [hid(live, p1.id), hid(live, p2.id)],
                          server: [hid(srv, p1.id), hid(srv, p2.id)] };
            a.undo();
            await new Promise(r => setTimeout(r, 300));
            await a._layerSavesSettled();
            out.undone = [hid(a.project.layers.find(x => x.id === id), p1.id),
                          hid(a.project.layers.find(x => x.id === id), p2.id)];
            a.undo();
            await new Promise(r => setTimeout(r, 300));
            await a._layerSavesSettled();
            return out;
        }""", sid)
        assert len(out['urls']) == 2, out
        assert all('/panels/set_hidden?' in u and 'seq=' in u and 'client=' in u for u in out['urls']), out
        assert out['page'] == [True, True] and out['server'] == [True, True], out
        assert out['steps'] == 2, out
        assert out['undone'] == [True, False], out
        assert errors == []
    finally:
        ctx.close()
