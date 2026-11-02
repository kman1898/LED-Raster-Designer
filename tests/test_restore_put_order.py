"""An undo's restore PUT carries the whole project as it was, so the order
those PUTs land in is the order the server's show goes through.

Found 2026-11-01 chasing two loaded-run failures (test_power_take_rule's
seed counting 4 circuits for a 6-wide screen, and an Advanced Guide step
that did not take): a restore PUT was waited on by nothing.

  * _layerSavesSettled - what New, Open, a recent file and the tests'
    seeds wait on - did not count a restore in flight, so landing after
    the next PUT it put the undone show back over the new one;
  * a second restore (two quick undos, or the guide's restore and then a
    jump's) was sent while the first was still on its way, so the server
    could take the older one last and keep the show the page had left.

Both are pinned here by HOLDING the PUTs with a Playwright route, so the
order is forced rather than hoped for.

Run locally:
    python -m pytest tests/test_restore_put_order.py --browser chromium
"""

import re

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app.project && window.canvasRenderer")
    pg.wait_for_timeout(1500)
    yield pg
    context.close()


PROJECT = re.compile(r'.*/api/project(\?.*)?$')

# Three named states of one screen, each its own history entry; returns
# the screen's id.
NAMED_STATES_JS = """async () => {
    const a = window.app;
    await a._layerSavesSettled();
    const layer = await (await fetch('/api/layer/add', { method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: 'RESTORE A', columns: 2, rows: 2,
                               offset_x: 0, offset_y: 6000 }) })).json();
    a.initializeLayerDefaults(layer);
    a.upsertProjectLayer(layer);
    a.saveState('Add Layer');
    for (const n of ['RESTORE B', 'RESTORE C']) {
        a.project.layers.find(l => l.id === layer.id).name = n;
        a.saveState('Rename');
    }
    await a._layerSavesSettled();
    return layer.id;
}"""

SERVER_NAME_JS = """(id) => fetch('/api/project').then(r => r.json())
    .then(p => ((p.layers || []).find(l => l.id === id) || {}).name || null)"""


def _hold_puts(page):
    held, hold = [], {'on': True}

    def handler(route):
        if hold['on'] and route.request.method == 'PUT':
            held.append(route)
            return
        route.continue_()
    page.route(PROJECT, handler)
    return held, hold


def _wait_for(page, cond, tries=100):
    for _ in range(tries):
        if cond():
            return True
        page.wait_for_timeout(50)
    return cond()


def test_two_quick_undos_reach_the_server_in_order(page):
    """Undo twice before the first restore lands: the second PUT waits for
    the first, so the server ends on the show the page shows (RESTORE A),
    not on the one it passed through (RESTORE B)."""
    lid = page.evaluate(NAMED_STATES_JS)
    held, hold = _hold_puts(page)
    try:
        page.evaluate("() => { window.app.undo(); window.app.undo(); }")
        assert _wait_for(page, lambda: len(held) >= 1), 'no restore PUT was sent'
        page.wait_for_timeout(400)
        assert len(held) == 1, 'the second restore went out before the first landed'
        held[0].continue_()
        assert _wait_for(page, lambda: len(held) == 2), 'the second restore was never sent'
        hold['on'] = False
        held[1].continue_()
        page.wait_for_function("""() => !(window.app._restorePutsInFlight
            && window.app._restorePutsInFlight.size)""", timeout=10000)
        shown = page.evaluate("(id) => (window.app.project.layers.find(l => l.id === id) || {}).name", lid)
        assert shown == 'RESTORE A'
        assert page.evaluate(SERVER_NAME_JS, lid) == 'RESTORE A'
    finally:
        hold['on'] = False
        page.unroute_all(behavior='ignoreErrors')


def test_saves_settled_counts_a_restore_in_flight(page):
    """_layerSavesSettled stays open while an undo's restore is on its
    way, so New, Open and a seed after it cannot be overtaken by it."""
    page.evaluate(NAMED_STATES_JS)
    held, hold = _hold_puts(page)
    try:
        page.evaluate("() => { window.app.undo(); }")
        assert _wait_for(page, lambda: len(held) >= 1), 'no restore PUT was sent'
        hold['on'] = False
        page.evaluate("""() => { window.__settled = false;
            window.app._layerSavesSettled().then(() => { window.__settled = true; }); }""")
        page.wait_for_timeout(400)
        assert page.evaluate("() => window.__settled") is False
        for r in held:
            r.continue_()
        page.wait_for_function("() => window.__settled === true", timeout=10000)
    finally:
        hold['on'] = False
        page.unroute_all(behavior='ignoreErrors')
