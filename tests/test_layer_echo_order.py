"""An older copy of a screen never comes back over a newer edit.

The server echoes (layer_updated) and answers each PUT with the screen as
that PUT left it. Two quick edits to one screen on a slow machine let the
first one's echo land after the second edit, and the page showed the older
copy until the next echo: a renamed screen flicked back to its old name,
and the Advanced Guide read a 3fer as unshared (CI, 2026-10-19). Echoes are
held back here so they always land late.
"""
import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    yield


DELAY_LAYER_UPDATED = """(() => {
    let real;
    Object.defineProperty(window, 'io', {
        configurable: true,
        get() { return real; },
        set(v) {
            real = function (...args) {
                const s = v(...args), on = s.on.bind(s);
                s.on = (ev, h) => on(ev, ev === 'layer_updated'
                    ? (...x) => setTimeout(() => h(...x), 400) : h);
                return s;
            };
            Object.assign(real, v);
        },
    });
})();"""


TWO_EDITS_JS = """async () => {
    const app = window.app, l = app.project.layers[0];
    l.name = 'FIRST'; app.updateLayers([l]);
    await new Promise(r => setTimeout(r, 50));
    l.name = 'SECOND'; app.updateLayers([l]);
    const seen = [];
    for (let i = 0; i < 24; i++) {
        await new Promise(r => setTimeout(r, 50));
        seen.push(app.project.layers[0].name);
    }
    await app._layerSavesSettled();
    const server = (await (await fetch('/api/project')).json()).layers[0].name;
    return { seen, server };
}"""


def test_a_late_echo_never_puts_an_older_copy_back(e2e_server, pw_browser):
    ctx = pw_browser.new_context()
    ctx.add_init_script("try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    ctx.add_init_script(DELAY_LAYER_UPDATED)
    pg = ctx.new_page()
    try:
        pg.goto(e2e_server, wait_until='domcontentloaded')
        pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
        out = pg.evaluate(TWO_EDITS_JS)
        assert 'FIRST' not in out['seen'], out
        assert out['seen'][-1] == 'SECOND' and out['server'] == 'SECOND', out
    finally:
        ctx.close()


# The test above failed once on a slow CI runner (2026-11-10): 50 ms after
# SECOND the page still read FIRST. Its own echoes were not the cause (the
# page let both go, as its own); the first PUT's REPLY was. It landed
# before the second edit and put a new screen object in the project's
# place, so SECOND went into the object the page had just let go of, and
# the page showed the reply's FIRST until the second PUT's reply came
# back, which on that runner took over 50 ms. Here the first reply always
# lands before the second edit and the second reply is held back.
HELD_REPLY_JS = """async () => {
    const app = window.app, l = app.project.layers[0];
    l.name = 'FIRST'; app.updateLayers([l]);
    await app._layerSavesSettled();
    const keptAfterReply = app.project.layers[0] === l;
    l.name = 'SECOND'; app.updateLayers([l]);
    const seen = [];
    for (let i = 0; i < 6; i++) {
        await new Promise(r => setTimeout(r, 40));
        seen.push(app.project.layers[0].name);
    }
    await app._layerSavesSettled();
    const server = (await (await fetch('/api/project')).json()).layers[0].name;
    return { keptAfterReply, seen, server, name: app.project.layers[0].name,
             foreign: app.history.filter(h => h.action === 'Changes From Another Page').length };
}"""


def _hold_second_reply(page, seconds=0.4):
    import time

    def handle(route, request):
        if request.method == 'PUT' and '"name":"SECOND"' in (request.post_data or ''):
            response = route.fetch()
            time.sleep(seconds)
            route.fulfill(response=response)
        else:
            route.continue_()
    page.route('**/api/layer/1?*', handle)


def test_an_edit_made_after_a_reply_stays_while_its_save_is_out(e2e_server, pw_browser):
    ctx = pw_browser.new_context()
    ctx.add_init_script("try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    ctx.add_init_script(DELAY_LAYER_UPDATED)
    pg = ctx.new_page()
    try:
        pg.goto(e2e_server, wait_until='domcontentloaded')
        pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
        _hold_second_reply(pg)
        out = pg.evaluate(HELD_REPLY_JS)
        assert out['keptAfterReply'] is True, out
        assert out['seen'] == ['SECOND'] * 6, out
        assert out['name'] == 'SECOND' and out['server'] == 'SECOND', out
        assert out['foreign'] == 0, out
    finally:
        ctx.close()


# On that run another page was open on the same server, and the log's
# six socket_layer_updated + foreign_step lines were its: the page that
# made the edits knows its own echoes by the id its PUTs carry, socket or
# no socket, and records no step from another page for them.
def test_only_the_other_page_takes_the_edits_as_from_another_page(e2e_server, pw_browser):
    other_ctx = pw_browser.new_context()
    other_ctx.add_init_script("try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    other = other_ctx.new_page()
    ctx = pw_browser.new_context()
    ctx.add_init_script("try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    ctx.add_init_script(DELAY_LAYER_UPDATED)
    pg = ctx.new_page()
    try:
        other.goto(e2e_server, wait_until='domcontentloaded')
        other.wait_for_function(
            "() => !!(window.app && window.app._initialLoadComplete && window.app.socket"
            " && window.app.socket.connected)")
        pg.goto(e2e_server, wait_until='domcontentloaded')
        pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
        _hold_second_reply(pg)
        out = pg.evaluate(HELD_REPLY_JS)
        assert out['foreign'] == 0, out
        other.wait_for_function("() => window.app.project.layers[0].name === 'SECOND'")
        theirs = other.evaluate(
            "() => ({ name: window.app.project.layers[0].name,"
            " foreign: window.app.history.filter(h => h.action === 'Changes From Another Page').length })")
        assert theirs == {'name': 'SECOND', 'foreign': 1}, theirs
        assert out['seen'] == ['SECOND'] * 6, out
    finally:
        ctx.close()
        other_ctx.close()


# The page's own newest echo says nothing its PUT's reply did not, yet it
# rebuilt the whole hardware tray at whatever moment it landed: under load
# that was mid-drag, and a drag back to the tray missed its drop. Echoes
# are held back here so they land after the reply.
OWN_ECHO_JS = """async () => {
    const app = window.app;
    document.querySelector('[data-mode="power"]').click();
    if (!(app.project.distros || []).length) app.addDistro();
    await app._layerSavesSettled();
    await new Promise(r => setTimeout(r, 600));
    const l = app.project.layers[0];
    let echoes = 0;
    app.socket.on('layer_updated', () => { echoes++; });
    let renders = 0;
    const orig = app.renderHardwareDock;
    app.renderHardwareDock = function () { renders++; return orig.apply(this, arguments); };
    l.name = 'OWN EDIT'; app.updateLayers([l]);
    await app._layerSavesSettled();
    await new Promise(r => setTimeout(r, 50));
    const afterReply = renders;
    for (let i = 0; i < 60 && !echoes; i++) await new Promise(r => setTimeout(r, 25));
    await new Promise(r => setTimeout(r, 100));
    app.renderHardwareDock = orig;
    return { echoes, rendersAfterEcho: renders - afterReply, name: app.project.layers[0].name };
}"""


def test_the_pages_own_echo_does_not_rebuild_the_tray(e2e_server, pw_browser):
    ctx = pw_browser.new_context()
    ctx.add_init_script("try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    ctx.add_init_script(DELAY_LAYER_UPDATED)
    pg = ctx.new_page()
    try:
        pg.goto(e2e_server, wait_until='domcontentloaded')
        pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
        out = pg.evaluate(OWN_ECHO_JS)
        assert out['echoes'] >= 1, out
        assert out['rendersAfterEcho'] == 0, out
        assert out['name'] == 'OWN EDIT', out
    finally:
        ctx.close()
