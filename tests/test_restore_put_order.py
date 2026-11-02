"""An undo's restore PUT carries the whole project as it was, so whatever
replaces the project after an undo must wait for it to land.

Found 2026-11-01 chasing a loaded-run failure: test_power_take_rule's seed
counted 4 circuits for a 6-wide screen. The test before it ended on an
Undo; its restore PUT, still on its way, landed after the seed had made a
new screen under the same id and put the old 4-wide one back. Held with a
route, it does so every time. _layerSavesSettled - what New, Open, a recent
file and the tests' seeds wait on - did not count a restore in flight.

Pinned here by HOLDING the PUT with a Playwright route, so the order is
forced rather than hoped for.

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

# Two named states of one screen, each its own history entry.
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
    a.project.layers.find(l => l.id === layer.id).name = 'RESTORE B';
    a.saveState('Rename');
    await a._layerSavesSettled();
    return layer.id;
}"""


def _wait_for(page, cond, tries=100):
    for _ in range(tries):
        if cond():
            return True
        page.wait_for_timeout(50)
    return cond()


def test_saves_settled_counts_a_restore_in_flight(page):
    """_layerSavesSettled stays open while an undo's restore is on its
    way, so New, Open and a seed after it cannot be overtaken by it."""
    page.evaluate(NAMED_STATES_JS)
    held, hold = [], {'on': True}

    def handler(route):
        if hold['on'] and route.request.method == 'PUT':
            held.append(route)
            return
        route.continue_()
    page.route(PROJECT, handler)
    try:
        page.evaluate("() => { window.app.undo(); }")
        assert _wait_for(page, lambda: len(held) >= 1), 'no restore PUT was sent'
        hold['on'] = False
        page.evaluate("""() => { window.__settled = false;
            window.app._layerSavesSettled().then(() => { window.__settled = true; }); }""")
        page.wait_for_timeout(400)
        assert page.evaluate("() => window.__settled") is False, \
            'settled while the restore PUT was still on its way'
        for r in held:
            r.continue_()
        page.wait_for_function("() => window.__settled === true", timeout=10000)
    finally:
        hold['on'] = False
        page.unroute_all(behavior='ignoreErrors')
