"""A blanked cabinet's save never puts an older copy of the screen back.

Blanking a cabinet (Alt+click, or Set Blank) is a POST of its own
(/api/layer/<id>/panels/set_hidden): the server rebuilds the screen around
the hidden flag, answers with it and sends it to every page. Sent as a bare
fetch, outside the screen's order of writes, both copies held the screen as
it stood when the POST went: on a busy machine they landed after the next
edit and put the screen's older colors back. Its socket copy was taken as
"Screen #1 changed on another page", which also redrew the Quick Palettes
with no pair pressed. The Data guide's demo show, built from its prep steps,
stopped at Quick Palettes ("did not take") right after Blank a cabinet
(2026-11-25, under CPU load).

Now (app-core.js _postLayerPanels): the POST is a write of the screen in
its one order of writes: numbered like a PUT, so its echo is known for the
page's own and an older one is dropped; sent after the saves before it and
before the ones after it; and its reply keeps every field the page changed
since it went. The guide's wait for the app (_layerSavesSettled) covers it.

The timings are forced here, so each test fails the same way every time
without the fix.

Run locally:
    python -m pytest tests/test_panel_write_order.py -v
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from test_tour_anchors import _wait_step, _end  # noqa: E402

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project exactly as this module found it."""


def _page(pw_browser, url, init):
    ctx = pw_browser.new_context(viewport={'width': 1600, 'height': 950})
    ctx.add_init_script("try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    ctx.add_init_script(init)
    pg = ctx.new_page()
    pg.goto(url, wait_until='domcontentloaded')
    pg.wait_for_function(
        "() => !!(window.app && window.app._initialLoadComplete && window.canvasRenderer && window.QuickStart)",
        timeout=120000)
    pg.wait_for_timeout(1000)
    return ctx, pg


# The answer to the first set_hidden POST after __holdReply() is held for
# 800 ms (the request itself goes out at once).
HOLD_REPLY = """(() => {
    const real = window.fetch;
    let armed = false;
    window.__holdReply = () => { armed = true; };
    window.fetch = function (input, init) {
        const url = String(input), method = (init && init.method) || 'GET';
        const p = real.apply(this, arguments);
        if (armed && method === 'POST' && url.includes('/panels/set_hidden')) {
            armed = false;
            return p.then(res => new Promise(r => setTimeout(() => r(res), 800)));
        }
        return p;
    };
})();"""

BLANK_THEN_PALETTE_JS = """async () => {
    const app = window.app, sleep = ms => new Promise(r => setTimeout(r, ms));
    const l = app.project.layers.find(x => (x.type || 'screen') === 'screen');
    app.selectLayer(l);
    await sleep(300);
    const panel = l.panels.find(p => !p.hidden);
    const pair = x => JSON.stringify([x.color1 && [x.color1.r, x.color1.g, x.color1.b],
                                      x.color2 && [x.color2.r, x.color2.g, x.color2.b]]);
    const before = pair(l);
    window.__holdReply();
    app.setPanelsBlankBulk([panel], true);
    await sleep(50);
    app.applyQuickPalette(3);
    const want = pair(app.project.layers.find(x => x.id === l.id));
    await sleep(1500);
    await app._layerSavesSettled();
    await sleep(500);
    const live = app.project.layers.find(x => x.id === l.id);
    const server = (await (await fetch('/api/project')).json()).layers.find(x => x.id === l.id);
    return { before, want, page: pair(live), server: pair(server),
             hidden: !!live.panels.find(p => p.id === panel.id).hidden,
             serverHidden: !!server.panels.find(p => p.id === panel.id).hidden };
}"""


def test_a_late_blank_reply_never_takes_back_a_newer_edit(e2e_server, pw_browser):
    ctx, pg = _page(pw_browser, e2e_server, HOLD_REPLY)
    try:
        out = pg.evaluate(BLANK_THEN_PALETTE_JS)
        assert out['want'] != out['before'], out
        assert out['page'] == out['want'], out
        assert out['server'] == out['want'], out
        assert out['hidden'] and out['serverHidden'], out
    finally:
        ctx.close()


# The Data guide's demo show built from its prep, with the moment that
# stopped it forced: every socket layer_updated that arrives after Blank a
# cabinet's POST is held until Quick Palettes sends its second save (the
# Hue turn; at most 3 s), and that save's answer waits 300 ms more, so the
# step's check runs after the held copies have landed.
HOLD_SOCKET = """(() => {
    const H = window.__sock = { armed: true, open: true, puts: 0, queue: [], released: null };
    const release = (why) => {
        if (H.open) return;
        H.open = true;
        H.released = why;
        H.queue.splice(0).forEach(f => setTimeout(f, 0));
    };
    let io;
    Object.defineProperty(window, 'io', {
        configurable: true,
        get() { return io; },
        set(v) {
            io = function (...args) {
                const s = v(...args), on = s.on.bind(s);
                s.on = (ev, h) => on(ev, ev === 'layer_updated'
                    ? (...x) => { if (H.open) h(...x); else H.queue.push(() => h(...x)); } : h);
                return s;
            };
            Object.assign(io, v);
        },
    });
    const real = window.fetch;
    window.fetch = function (input, init) {
        const url = String(input), method = (init && init.method) || 'GET';
        if (H.armed && method === 'POST' && url.includes('/panels/set_hidden')) {
            H.armed = false;
            H.open = false;
            setTimeout(() => release('timeout'), 3000);
        } else if (!H.open && method === 'PUT' && /\\/api\\/layer\\/\\d+\\?/.test(url) && ++H.puts === 2) {
            release('second save');
            return real.apply(this, arguments).then(res => new Promise(r => setTimeout(() => r(res), 300)));
        }
        return real.apply(this, arguments);
    };
})();"""


def test_the_data_demo_show_builds_with_the_blank_echo_landing_late(e2e_server, pw_browser):
    ctx, pg = _page(pw_browser, e2e_server, HOLD_SOCKET)
    # no shipped snapshot: the demo show is built from the prep steps
    pg.route('**/static/data/tour_snapshots.json', lambda r: r.fulfill(status=404, body=''))
    try:
        prep = pg.evaluate("() => window.QuickStart.prepOf('data')")
        assert prep.index('blankCabinet') + 1 == prep.index('quickPalettes'), prep
        pg.evaluate("() => window.QuickStart.setSpeed(3)")
        pg.evaluate("() => { window.QuickStart.startTour('data'); }")
        st = _wait_step(pg, 0, timeout=600)
        qs = pg.evaluate("() => window.QuickStart.state()")
        sock = pg.evaluate("() => ({armed: window.__sock.armed, released: window.__sock.released})")
        assert sock['armed'] is False and sock['released'], sock
        assert qs['startedVia'] == 'apply', (qs.get('startError'), sock)
        assert st['qs']['index'] == 0 and st['state'] == 'idle', st
    finally:
        try:
            _end(pg)
        except Exception:
            pass
        ctx.close()
