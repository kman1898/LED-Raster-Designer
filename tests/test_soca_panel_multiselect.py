"""Multi-select doctrine on the per-screen power settings.

The app's rule: modify something with several screens selected and the edit
lands on EVERY selected screen (app-screen-info's update path has always
worked this way). The per-screen power knobs - the "Soca Brackets on Map"
checkbox, the breakout-type select and the splitter packing controls - live
in the LEFT sidebar's Power Settings block now (the Power sidebar and its
soca panel are gone): STATIC controls, synced in place per selection by
refreshSocaRuns/refreshSplitterPanel (no rebuild wipe) and wired once by
_wireScreenPowerKnobs. These tests pin the doctrine through the real
controls in the Power view:

* toggling brackets with two screens selected updates BOTH models and both
  server rows; a third, unselected screen is untouched
* changing the breakout type does the same
* the splitter packing knobs (enable + max ways) do the same
* with a single selection the edit still lands only on the shown screen

Per-multi fields (names, home-run lengths, distro assignments) are NOT
swept along: they belong to one screen's own soca plan, and they edit
inline on that multi's hardware dock header.

Run locally:
    python -m pytest tests/test_soca_panel_multiselect.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project exactly as this module found it -
    the page fixture below replaces every server layer with SelA/SelB/Solo
    (see conftest.server_project_guard)."""


# Three 4x4 screens of the default 200W cabinet on the default 15A/110V
# circuit - small enough that each packs a soca plan. SelA is the shown
# screen the Power Settings knobs sync to, SelB rides in the
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
    # The knobs are static markup in the left sidebar's Power Settings now;
    # the evidence the power view wired them up is refreshSocaRuns having
    # filled the breakout picker's options.
    assert pg.evaluate(
        "() => document.querySelectorAll('#power-breakout-type option')"
        ".length > 0"), \
        "refreshSocaRuns never filled the breakout picker"
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
    # Brackets default OFF (user decision) - a fresh screen's field is unset
    # and its checkbox unchecked, so the multi-select edit under test is the
    # tick that turns them ON.
    before = page.evaluate(STATE_JS)
    assert before['a']['brackets'] is not True, "fixture: brackets start off"
    assert page.evaluate(
        "() => !document.getElementById('show-soca-brackets').checked"), \
        "brackets must start unticked on a fresh screen"
    page.locator('#show-soca-brackets').click()  # tick: on

    state = page.evaluate(STATE_JS)
    assert state['a']['brackets'] is True, "shown screen must take the edit"
    assert state['b']['brackets'] is True, (
        "the OTHER selected screen was skipped - multi-select edits must "
        f"apply to every selected screen: {state}")
    assert state['solo']['brackets'] is not True, (
        f"an UNSELECTED screen was swept along: {state}")

    served = _served(page, lambda s: s['a']['brackets'] is True
                     and s['b']['brackets'] is True)
    assert served['a']['brackets'] is True and served['b']['brackets'] is True, (
        f"the edit never reached the server for both screens: {served}")
    assert served['solo']['brackets'] is not True, (
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


def test_splitter_knobs_apply_to_every_selected_screen(page):
    """The splitter packing knobs (the retired Splitters panel's surviving
    scalars) follow the same doctrine from Power Settings: the enable tick
    and the size pick land on every selected screen; Solo is untouched.
    The size row shows only while sharing is on - refreshSplitterPanel
    wears the old panel's present-only-while-enabled rule as visibility on
    the static row. (Manual merge and split are not knobs any more: they
    are the right-click Share / Un-share on the circuit itself.)"""
    page.locator('#power-splitters-enabled').click()  # tick: on
    page.wait_for_timeout(400)
    state = page.evaluate("""() => {
        const app = window.app;
        const byName = (n) => app.project.layers.find(l => l.name === n);
        const on = (l) => app.getPowerSplitters(l).enabled;
        const row = document.getElementById('power-splitters-maxways-row');
        return { a: on(byName('SelA')), b: on(byName('SelB')),
                 solo: on(byName('Solo')),
                 rowShown: !!row && row.style.display !== 'none' };
    }""")
    assert state['a'] is True, "shown screen must take the enable"
    assert state['b'] is True, (
        f"the OTHER selected screen was skipped - multi-select edits must "
        f"apply to every selected screen: {state}")
    assert state['solo'] is False, (
        f"an UNSELECTED screen was swept along: {state}")
    assert state['rowShown'], "the size row must show while sharing is on"

    page.evaluate("""() => {
        const mw = document.getElementById('power-splitters-maxways');
        mw.value = '4';
        mw.dispatchEvent(new Event('change', { bubbles: true }));
    }""")
    page.wait_for_timeout(400)
    ways = page.evaluate("""() => {
        const app = window.app;
        const byName = (n) => app.project.layers.find(l => l.name === n);
        const w = (l) => app.getPowerSplitters(l).maxWays;
        return { a: w(byName('SelA')), b: w(byName('SelB')),
                 solo: w(byName('Solo')) };
    }""")
    assert ways['a'] == 4 and ways['b'] == 4, (
        f"the size pick skipped a selected screen: {ways}")
    assert ways['solo'] == 3, (
        f"an UNSELECTED screen took the size pick: {ways}")


def test_a_multi_name_stays_with_its_own_multi(page):
    """A NAME is per-multi, so it is on the other side of the doctrine from
    the scalar knobs: it edits inline on the multi's hardware dock header
    (key power-soca-name-<layerId>-<idx>, which exists once the multi is
    ON a distro - an unassigned multi has no dock section), and naming the
    shown screen's multi must not name the other selected screen's multi,
    which is a different multi on a different wall."""
    typed = page.evaluate("""() => {
        const app = window.app;
        const a = app.project.layers.find(l => l.name === 'SelA');
        if (!app.project.distros) app.project.distros = [];
        if (!app.project.distros.some(d => d.id === 'dm1')) {
            app.project.distros.push({ id: 'dm1', name: 'DM', ratingA: 400,
                                       voltage: 208, phase: 3 });
        }
        app._circuitTailCache = null;
        app.setSocaDistro(a, 1, 'dm1');
        app._circuitTailCache = null;
        app.renderHardwareDock();
        const inp = document.querySelector(
            `[data-lrd-field="power-soca-name-${a.id}-1"]`);
        if (!inp) return null;
        inp.value = 'HOUSE';
        inp.dispatchEvent(new Event('change', { bubbles: true }));
        return 'HOUSE';
    }""")
    assert typed, "the dock built no multi name field for the shown screen"
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
    # The static checkbox is synced in place per selection (no rebuild
    # wipe, no focus dance): after re-selecting SelA alone it must already
    # show SelA's stored value.
    assert page.evaluate(
        "() => document.getElementById('show-soca-brackets').checked"), \
        "the checkbox did not follow the shown screen after re-selection"
    b_before = page.evaluate(STATE_JS)['b']['brackets']
    page.locator('#show-soca-brackets').click()  # untick (both went on above)

    state = page.evaluate(STATE_JS)
    assert state['a']['brackets'] is False, "single-select edit missed its screen"
    assert state['b']['brackets'] == b_before, (
        f"single-select edit leaked to an unselected screen: {state}")


# ── brackets default OFF, drawn only when ticked ──────────────────────────
#
# "it should be unselected by default". showSocaBrackets used to default ON
# (checked when !== false), so every screen drew brackets nobody asked for.
# Now they draw only when the field is EXACTLY true - the checkbox and the
# canvas gate read the same comparison. A project saved before the flip that
# never touched the field goes from brackets-on to brackets-off, which is
# what was asked for; a stored true still reads as on after a reload.

def test_brackets_draw_only_for_screens_stored_true(page):
    """After the tests above: SelA is false, SelB is true, Solo untouched.
    One render in Power view must call renderSocaBrackets for SelB alone -
    the unset default draws nothing, and false stays false."""
    drawn = page.evaluate("""() => {
        const cr = window.canvasRenderer;
        const seen = [];
        const orig = cr.renderSocaBrackets;
        try {
            cr.renderSocaBrackets = function (layer) { seen.push(layer.name); };
            cr.render();
        } finally { cr.renderSocaBrackets = orig; }
        return seen;
    }""")
    assert drawn == ['SelB'], (
        f"brackets must draw for exactly the screens stored true: {drawn}")


def test_stored_true_survives_a_reload_and_default_stays_off(page):
    """A screen where the user explicitly ticked the box must still read as
    on after reload; a screen that never touched the field must come back
    unticked."""
    page.reload(wait_until='domcontentloaded')
    page.wait_for_timeout(2000)
    page.locator('[data-mode="power"]').click()
    page.wait_for_timeout(500)
    out = page.evaluate("""() => {
        const app = window.app;
        const byName = (n) => app.project.layers.find(l => l.name === n);
        const show = (l) => {
            app.currentLayer = l;
            app.selectedLayerIds = new Set([l.id]);
            app.refreshSocaRuns();
            const cb = document.getElementById('show-soca-brackets');
            return cb ? cb.checked : null;
        };
        return {
            b: { stored: byName('SelB').showSocaBrackets,
                 checked: show(byName('SelB')) },
            solo: { stored: byName('Solo').showSocaBrackets,
                    checked: show(byName('Solo')) },
        };
    }""")
    assert out['b']['stored'] is True and out['b']['checked'] is True, (
        f"an explicitly ticked screen must survive the reload as on: {out}")
    assert out['solo']['stored'] is not True and out['solo']['checked'] is False, (
        f"an untouched screen must come back unticked: {out}")


# ── the dock's issue strip says WHY the plan is empty ─────────────────────
#
# Live repro: a 13-wide screen of 200W panels at 110V/15A in organized row
# mode -> CANNOT FIT COMPLETE ROW -> zero circuits -> empty soca plan -> the
# old panel rendered NOTHING, and the user read the soca feature as broken.
# The panel is gone; the story now rides the hardware dock's issue strip
# (#hw-dock-issues) as a "No circuits on SCREEN — <reason>" row, pushed by
# _dockRenderPower from _socaPlanEmptyReason. Only the ERROR empty state
# gets the row - a non-screen layer or a screen with nothing visible on it
# keeps the strip silent.

ERROR_SCREEN_JS = """() => {
    // The user's shape, in memory only: 13 columns of 200W cabinets on a
    // 110V/15A circuit, organized rows. A full row is 2,600W against a
    // 1,650W circuit.
    const layer = {
        id: 99901, name: 'WideErr', type: 'screen', visible: true,
        columns: 13, rows: 2, group_id: null,
        cabinet_width: 128, cabinet_height: 128,
        panelWatts: 200, powerVoltage: 110, powerAmperage: 15,
        powerFlowPattern: 'tl-h', powerOrganized: true, powerMaximize: false,
        panels: [],
    };
    for (let r = 0; r < 2; r++) for (let c = 0; c < 13; c++) {
        layer.panels.push({ row: r, col: c, x: c * 128, y: r * 128,
                            width: 128, height: 128,
                            hidden: false, blank: false, halfTile: 'none' });
    }
    return layer;
}"""

WITH_LAYER_JS = """(mutate) => {
    const app = window.app;
    const layer = (%s)();
    if (mutate) (new Function('layer', mutate))(layer);
    const savedCurrent = app.currentLayer;
    const savedSel = app.selectedLayerIds;
    app.project.layers.push(layer);
    app.currentLayer = layer;
    app.selectedLayerIds = new Set([layer.id]);
    try {
        layer._powerCircuitsRequired = app.screenCircuitCount(layer);
        app._circuitTailCache = null;
        app.renderHardwareDock();
        const strip = document.getElementById('hw-dock-issues');
        return {
            text: strip.textContent.replace(/\\s+/g, ' ').trim(),
            empty: !strip.querySelector('.hw-dock-issue'),
            fits: strip.scrollWidth <= strip.clientWidth,
        };
    } finally {
        app.project.layers.pop();
        app.currentLayer = savedCurrent;
        app.selectedLayerIds = savedSel;
        app._circuitTailCache = null;
        app.renderHardwareDock();
    }
}""" % ERROR_SCREEN_JS


def test_dock_strip_states_the_power_error_with_the_layers_figures(page):
    out = page.evaluate(WITH_LAYER_JS, None)
    assert not out['empty'], (
        "an error-emptied plan raised no strip row - the exact silence the "
        "user read as the feature being broken")
    for figure in ('No circuits on WideErr', 'a full row is 2,600 W',
                   '110 V / 15 A', 'carries 1,650 W',
                   'higher voltage or amperage', 'column pattern',
                   'custom path'):
        assert figure in out['text'], (
            f"{figure!r} missing - the row must carry the layer's own "
            f"numbers and a way out: {out['text']}")
    assert out['fits'], (
        "the error row overflows the strip sideways - it must wrap inside "
        "the dock like every other row")
    # The retired Circuit Labels list echoed this reason ("No circuits to
    # edit — ..."); with the consolidation the per-circuit editors ARE the
    # dock's circuit chips, and an emptied plan has no chips - the strip
    # row above is the one story (updatePowerLabelEditor is a kept no-op).


def test_column_error_names_the_column_and_the_row_way_out(page):
    out = page.evaluate(WITH_LAYER_JS, """
        layer.powerFlowPattern = 'tl-v';
        layer.columns = 2; layer.rows = 13;
        layer.panels = [];
        for (let c = 0; c < 2; c++) for (let r = 0; r < 13; r++) {
            layer.panels.push({ row: r, col: c, x: c * 128, y: r * 128,
                                width: 128, height: 128,
                                hidden: false, blank: false, halfTile: 'none' });
        }
    """)
    assert 'a full column is 2,600 W' in out['text'], out['text']
    assert 'row pattern' in out['text'], (
        f"a column error suggests the row pattern, not itself: {out['text']}")


def test_legitimately_empty_states_keep_the_strip_silent(page):
    # Every cabinet hidden: nothing visible is not an error, so no row.
    hidden = page.evaluate(WITH_LAYER_JS,
                           "layer.panels.forEach(p => p.hidden = true);")
    assert hidden['empty'], (
        f"a screen with nothing visible claimed an error it does not have: "
        f"{hidden['text']}")
    # No wattage entered yet: an unconfigured screen is not an error either.
    unset = page.evaluate(WITH_LAYER_JS, "layer.panelWatts = 0;")
    assert unset['empty'], (
        f"an unconfigured screen claimed an error it does not have: "
        f"{unset['text']}")


# ── the multi's fields read legibly on its dock header ────────────────────
#
# The multi rows died with the Power sidebar; what they existed for - the
# name and home-run length, legible at a glance - rides the multi's own
# hardware dock header now (one header per box, no static label while
# occupied). The name field shows the DERIVED name as its placeholder while
# unnamed, so following-the-distro (grey) vs named-by-hand (typed) is
# visible at a glance - the same legibility rule as the phasing select's
# deriving state - and the length field wears hw-dock-name-len with the
# "100ft" hint as its caption.

def test_the_multi_header_carries_the_name_and_length_fields(page):
    out = page.evaluate("""() => {
        const app = window.app;
        const byName = (n) => app.project.layers.find(l => l.name === n);
        const b = byName('SelB');
        app.currentLayer = b;
        app.selectedLayerIds = new Set([b.id]);
        if (!app.project.distros) app.project.distros = [];
        if (!app.project.distros.some(d => d.id === 'dm2')) {
            app.project.distros.push({ id: 'dm2', name: 'DL', ratingA: 400,
                                       voltage: 208, phase: 3 });
        }
        app._circuitTailCache = null;
        app.setSocaDistro(b, 1, 'dm2');
        app._circuitTailCache = null;
        app.renderHardwareDock();
        const name = document.querySelector(
            `[data-lrd-field="power-soca-name-${b.id}-1"]`);
        const len = document.querySelector(
            `[data-lrd-field="power-soca-length-${b.id}-1"]`);
        const head = name && name.closest('.hw-dock-head-row');
        const plan = app.getSocaPlan(b);
        return {
            name: !!name, len: !!len,
            sameHead: !!(head && len && head.contains(len)),
            lenClass: !!(len && len.classList.contains('hw-dock-name-len')),
            lenPlaceholder: len ? len.placeholder : null,
            value: name ? name.value : null,
            placeholder: name ? name.placeholder : null,
            planName: plan.length ? plan[0].name : null,
            staticLabel: !!(head
                && head.querySelector('.hw-dock-unit-name')),
            fits: !!(head && head.scrollWidth <= head.clientWidth),
        };
    }""")
    assert out['name'] and out['len'], (
        f"the dock built no name/length fields for the assigned multi: {out}")
    assert out['sameHead'], (
        f"name and length must ride the multi's ONE header: {out}")
    assert out['lenClass'] and out['lenPlaceholder'] == '100ft', out
    assert out['value'] == '', f"SelB's multi is unnamed: {out}"
    assert out['planName'] and out['placeholder'] == out['planName'], (
        "the name field's placeholder is the derived name, so an unnamed "
        f"multi visibly follows its distro: {out}")
    assert not out['staticLabel'], (
        f"an occupied box wears its member's field, not a static label: {out}")
    assert out['fits'], (
        "the header's fields overflow their row - they must fit the dock "
        f"header like every other unit's: {out}")
