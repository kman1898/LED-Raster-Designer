"""Multi-select doctrine on the soca panel's per-screen settings.

The app's rule: modify something with several screens selected and the edit
lands on EVERY selected screen (app-screen-info's update path has always
worked this way). The soca panel's per-screen scalar settings - the
"Soca Brackets on Map" checkbox and the breakout-type select - bypassed
that and wrote only to the screen the panel happened to show. These tests
pin the fixed behaviour, through the real checkbox/select in the Power view:

* toggling brackets with two screens selected updates BOTH models and both
  server rows; a third, unselected screen is untouched
* changing the breakout type does the same
* with a single selection the edit still lands only on the shown screen

Per-multi fields (home-run lengths, distro assignments) are NOT swept along:
they belong to one screen's own soca plan.

Run locally:
    python -m pytest tests/test_soca_panel_multiselect.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


# Three 4x4 screens of the default 200W cabinet on the default 15A/110V
# circuit - small enough that each renders a soca plan (and therefore the
# brackets checkbox). SelA is shown in the panel, SelB rides in the
# multi-selection, Solo stays out of it as the control.
RESET_JS = """async () => {
    const app = window.app;
    let project = await (await fetch('/api/project')).json();
    project.layers = [];
    project.groups = [];
    await fetch('/api/project', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(project),
    });
    for (const name of ['SelA', 'SelB', 'Solo']) {
        await fetch('/api/layer/add', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                name, columns: 4, rows: 4,
                cabinet_width: 128, cabinet_height: 128,
            }),
        });
    }
    app.project = await (await fetch('/api/project')).json();
    app.dedupeProjectLayers('soca_multiselect_test_reset');
    const byName = (n) => app.project.layers.find(l => l.name === n);
    const a = byName('SelA'), b = byName('SelB');
    app.currentLayer = a;
    app.selectedLayerIds = new Set([a.id, b.id]);
    app.lastSelectedLayerId = a.id;
    app.renderLayers();
    app.loadLayerToInputs(a);
    app.updatePortCapacityDisplay();
    app.updatePowerCapacityDisplay();
    if (window.canvasRenderer) window.canvasRenderer.render();
    return { a: a.id, b: b.id, solo: byName('Solo').id };
}"""

STATE_JS = """() => {
    const byName = (n) => window.app.project.layers.find(l => l.name === n);
    const pick = (l) => l ? { brackets: l.showSocaBrackets,
                              breakout: l.powerBreakoutType } : null;
    return { a: pick(byName('SelA')), b: pick(byName('SelB')),
             solo: pick(byName('Solo')) };
}"""

SERVED_JS = """async () => {
    const p = await (await fetch('/api/project')).json();
    const byName = (n) => (p.layers || []).find(l => l.name === n);
    const pick = (l) => l ? { brackets: l.showSocaBrackets,
                              breakout: l.powerBreakoutType } : null;
    return { a: pick(byName('SelA')), b: pick(byName('SelB')),
             solo: pick(byName('Solo')) };
}"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    ids = pg.evaluate(RESET_JS)
    assert ids and ids.get('a') and ids.get('b') and ids.get('solo'), \
        "test screens were not created"
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(500)
    assert pg.evaluate(
        "() => !!document.querySelector('#show-soca-brackets')"), \
        "the soca panel never rendered its brackets checkbox"
    yield pg
    context.close()


def _served(page, want):
    """Poll the server until the persisted rows satisfy `want(state)`."""
    served = None
    for _ in range(16):
        served = page.evaluate(SERVED_JS)
        if want(served):
            return served
        page.wait_for_timeout(250)
    return served


def test_brackets_toggle_applies_to_every_selected_screen(page):
    before = page.evaluate(STATE_JS)
    assert before['a']['brackets'] is not False, "fixture: brackets start on"
    page.locator('#show-soca-brackets').click()  # uncheck

    state = page.evaluate(STATE_JS)
    assert state['a']['brackets'] is False, "shown screen must take the edit"
    assert state['b']['brackets'] is False, (
        "the OTHER selected screen was skipped - multi-select edits must "
        f"apply to every selected screen: {state}")
    assert state['solo']['brackets'] is not False, (
        f"an UNSELECTED screen was swept along: {state}")

    served = _served(page, lambda s: s['a']['brackets'] is False
                     and s['b']['brackets'] is False)
    assert served['a']['brackets'] is False and served['b']['brackets'] is False, (
        f"the edit never reached the server for both screens: {served}")
    assert served['solo']['brackets'] is not False, (
        f"the unselected screen changed on the server: {served}")


def test_breakout_select_applies_to_every_selected_screen(page):
    choice = page.evaluate("""() => {
        const sel = document.querySelector('#power-breakout-type');
        if (!sel || sel.options.length < 2) return null;
        const v = Array.from(sel.options).map(o => o.value)
            .find(x => x !== sel.value);
        sel.value = v;
        sel.dispatchEvent(new Event('change', { bubbles: true }));
        return v;
    }""")
    assert choice, "no alternate breakout type to pick"

    state = page.evaluate(STATE_JS)
    assert state['a']['breakout'] == choice
    assert state['b']['breakout'] == choice, (
        f"breakout type skipped the other selected screen: {state}")
    assert state['solo']['breakout'] != choice, (
        f"an UNSELECTED screen took the breakout edit: {state}")

    served = _served(page, lambda s: s['a']['breakout'] == choice
                     and s['b']['breakout'] == choice)
    assert served['a']['breakout'] == choice and served['b']['breakout'] == choice, (
        f"breakout never persisted for both screens: {served}")


def test_a_multi_name_stays_with_its_own_multi(page):
    """A NAME is per-multi, so it is on the other side of the doctrine from
    the brackets toggle and the breakout select: naming the shown screen's
    multi must not name the other selected screen's multi, which is a
    different multi on a different wall."""
    typed = page.evaluate("""() => {
        const inp = document.querySelector('[data-lrd-field="power-soca-name-1"]');
        if (!inp) return null;
        inp.value = 'HOUSE';
        inp.dispatchEvent(new Event('change', { bubbles: true }));
        return 'HOUSE';
    }""")
    assert typed, "the soca panel built no multi name field"
    page.wait_for_timeout(300)
    state = page.evaluate("""() => {
        const byName = (n) => window.app.project.layers.find(l => l.name === n);
        const pick = (l) => (l && l.powerSocaNames) || {};
        return { a: pick(byName('SelA')), b: pick(byName('SelB')),
                 solo: pick(byName('Solo')),
                 label: window.app.getPowerCircuitLabel(byName('SelA'), 1) };
    }""")
    assert state['a'].get('1') == 'HOUSE', "the shown screen's multi was not named"
    assert state['b'] == {}, (
        f"the name swept onto the other selected screen's multi: {state}")
    assert state['solo'] == {}, f"an unselected screen was named: {state}"
    assert state['label'] == 'HOUSE-1', (
        f"the circuit did not take its multi's name: {state['label']}")


def test_single_select_still_edits_only_the_shown_screen(page):
    page.evaluate("""() => {
        const app = window.app;
        const a = app.project.layers.find(l => l.name === 'SelA');
        app.currentLayer = a;
        app.selectedLayerIds = new Set([a.id]);
        app.renderLayers();
        app.updatePowerCapacityDisplay();
    }""")
    page.wait_for_timeout(300)
    b_before = page.evaluate(STATE_JS)['b']['brackets']
    page.locator('#show-soca-brackets').click()  # re-check (back on)

    state = page.evaluate(STATE_JS)
    assert state['a']['brackets'] is True, "single-select edit missed its screen"
    assert state['b']['brackets'] == b_before, (
        f"single-select edit leaked to an unselected screen: {state}")
