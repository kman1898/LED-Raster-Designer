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
