"""Two Power view fixes for 1.6.0, pinned in a real browser.

* A FOLDED DISTRO CARD hides its OUTPUTS row (owner, 2026-10-30: "When you
  minimize distro, we do not need to see the multi and l2130 stuff that you
  can drag since it is minimized"). The header and the LEGS line stay: the
  LEGS line was put outside the fold so a folded distro still reads its
  balance at a glance. The plug chips are hidden, not detached, so none of
  them can be dragged or tabbed to while folded; unfolded they come back,
  and the fold survives a tray rebuild.
* ESCAPE CANCELS AN ALT+CLICK REDRAW (owner, 2026-10-30: "when I use alt +
  click to redraw we need a way to deselect like the escape key").

Run locally:
    "C:/Users/Blue Iris/.venvs/led-raster/Scripts/python.exe" -m pytest \
        tests/test_distro_collapse_and_alt_escape.py -q --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# WALL A: 8 wide x 18 rows of 200 W cabinets at 208 V / 10 A - one row per
# circuit, 18 circuits, three multis of six.
SEED_JS = """async () => {
    const proj = await (await fetch('/api/project')).json();
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments;
    await fetch('/api/project', {method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(proj)});
    await fetch('/api/layer/add', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: 'WALL A', columns: 8, rows: 18,
                              cabinet_width: 200, cabinet_height: 200})});
    const p1 = await (await fetch('/api/project')).json();
    for (const l of p1.layers) {
        await fetch(`/api/layer/${l.id}`, {method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({powerVoltage: 208, powerAmperage: 10, panelWatts: 200})});
    }
    const p = await (await fetch('/api/project')).json();
    const app = window.app;
    app.project = p;
    app.currentLayer = p.layers[0];
    app.selectedLayerIds = new Set([p.layers[0].id]);
    app.renderLayers();
    const r = window.canvasRenderer;
    r.zoom = 0.22; r.panX = 60; r.panY = 60; r.render();
    return p.layers[0].id;
}"""

# The show reshaped in the page: the distros given, nothing assigned, no
# take-over, no fold remembered.
SETUP_JS = """(distros) => {
    const app = window.app;
    const L = app.project.layers.find(l => l.name === 'WALL A');
    Object.assign(L, { powerVoltage: 208, powerAmperage: 10, panelWatts: 200,
                       powerSocaDistro: {}, powerSocaNumber: {}, powerSocaPhasePos: {},
                       powerSocaLengths: {}, powerSocaSplits: [], powerSocaNames: {},
                       powerBreakoutType: null, locked: false,
                       powerFlowPattern: 'tl-h', powerOrganized: false,
                       powerMaximize: false, powerCustomPaths: {},
                       powerCustomOverrides: [], powerCustomIndex: 1 });
    app.normalizePowerBreakout(L);
    // no field left focused by the previous test
    if (document.activeElement && document.activeElement !== document.body
            && document.activeElement.blur) document.activeElement.blur();
    app.currentLayer = L;
    app.selectedLayerIds = new Set([L.id]);
    app._overrideEditing = null;
    app._overrideHover = null;
    app._sweepSelection = null;
    if (app.powerCustomSelection) app.powerCustomSelection.clear();
    if (typeof app.hideContextMenu === 'function') app.hideContextMenu();
    app.updateLayers([L]);
    app.project.distros = distros.map(d => JSON.parse(JSON.stringify(d)));
    for (const d of app.project.distros) {
        try { localStorage.removeItem(`ledRasterPanelCollapsed_hwdock-distro-${d.id}`); } catch (e) {}
    }
    app._circuitTailCache = null;
    app._distroFaceMemo = null;
    app._persistDistros();
    app._restateNaming();
    app.renderHardwareDock();
    window.canvasRenderer.render();
    if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
    app.resetHistory('Card Seed');
    return app.getSocaPlan(L).length;
}"""

ROW = lambda rid, conn, count, coupling='ll', paired=None: {  # noqa: E731
    'id': rid, 'connector': conn, 'count': count, 'coupling': coupling,
    'breakerA': 20, 'pairedWith': paired}

# A face with the three kinds the owner named: a 208 multi, a 120 multi
# and an L21-30.
VX = {'id': 'd1', 'name': 'VX', 'ratingA': 200, 'system': '120/208',
      'outputRows': [ROW('r1', 'soca', 1), ROW('r2', 'soca', 1, coupling='ln'),
                     ROW('r3', 'l2130', 1)]}

UNIT = '[data-lrd-distro="d1"]'
ARROW = f'{UNIT} > .hw-dock-head-row .lrd-sec-arrow'

# What the card shows: every plug chip with whether it is rendered, can be
# reached by Tab, and is what a press at its centre would land on.
CARD_JS = """() => {
    const unit = document.querySelector('[data-lrd-distro="d1"]');
    if (!unit) return null;
    const shown = (el) => !!el && el.getClientRects().length > 0
        && getComputedStyle(el).visibility !== 'hidden';
    const row = unit.querySelector(':scope > .hw-dock-outputs');
    const legs = unit.querySelector(':scope > .hw-dock-legs');
    const head = unit.querySelector(':scope > .hw-dock-head-row');
    const plugs = [...unit.querySelectorAll('[data-hwdock^="plug-"]')].map(c => {
        const r = c.getBoundingClientRect();
        const hit = shown(c) ? document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2) : null;
        return { key: c.dataset.hwdock, shown: shown(c),
                 reachable: !!hit && (hit === c || c.contains(hit)) };
    });
    // Tab order: walk every focusable element the browser would stop on.
    const tabbable = [...document.querySelectorAll('[tabindex], a[href], button, input, select, textarea')]
        .filter(el => el.tabIndex >= 0 && !el.disabled && shown(el));
    return {
        folded: unit.classList.contains('lrd-sec-collapsed'),
        outputsRow: !!row,
        outputsShown: shown(row),
        legsShown: shown(legs),
        headShown: shown(head),
        plugs,
        tabbablePlugs: tabbable.filter(el => (el.dataset.hwdock || '').startsWith('plug-')
            && unit.contains(el)).length,
    };
}"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    pg.wait_for_timeout(1500)
    pg.evaluate(SEED_JS)
    pg.wait_for_timeout(800)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(500)
    yield pg, errors
    context.close()


def setup(pg, *distros):
    # The previous gesture's server echo lands first, so it cannot replace
    # the layer this setup writes.
    pg.wait_for_timeout(400)
    n = pg.evaluate(SETUP_JS, list(distros))
    pg.wait_for_timeout(300)
    return n


def click_arrow(pg):
    pg.evaluate("(s) => document.querySelector(s).scrollIntoView({block: 'center'})", ARROW)
    box = pg.locator(ARROW).first.bounding_box()
    assert box, 'no fold arrow on the distro card'
    pg.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
    pg.wait_for_timeout(250)


# ── a folded distro card hides its outputs ───────────────────────────────

def test_a_folded_distro_card_hides_its_output_chips(page):
    pg, errors = page
    setup(pg, VX)
    open_card = pg.evaluate(CARD_JS)
    assert open_card and not open_card['folded'], open_card
    assert open_card['outputsShown'] and open_card['legsShown'], open_card
    keys = [p['key'] for p in open_card['plugs']]
    assert len(keys) == 3, open_card
    assert all(p['shown'] and p['reachable'] for p in open_card['plugs']), open_card
    assert open_card['tabbablePlugs'] == 3, open_card

    click_arrow(pg)
    folded = pg.evaluate(CARD_JS)
    assert folded['folded'], 'the arrow did not fold the card'
    # the header and the LEGS line stay; the OUTPUTS row goes
    assert folded['headShown'] and folded['legsShown'], folded
    assert folded['outputsRow'], 'the row was detached instead of hidden'
    assert not folded['outputsShown'], folded
    assert [p['key'] for p in folded['plugs']] == keys
    assert not any(p['shown'] or p['reachable'] for p in folded['plugs']), folded
    assert folded['tabbablePlugs'] == 0, folded

    # the fold survives a rebuild of the tray, and the row stays hidden
    pg.evaluate("() => window.app.renderHardwareDock()")
    pg.wait_for_timeout(200)
    again = pg.evaluate(CARD_JS)
    assert again['folded'] and not again['outputsShown'], again
    assert again['tabbablePlugs'] == 0, again
    assert pg.evaluate("() => localStorage.getItem('ledRasterPanelCollapsed_hwdock-distro-d1')") == '1'

    # unfolded, everything is back as it was
    click_arrow(pg)
    back = pg.evaluate(CARD_JS)
    assert not back['folded'], back
    assert back['outputsShown'] and back['legsShown'], back
    assert [p['key'] for p in back['plugs']] == keys
    assert all(p['shown'] and p['reachable'] for p in back['plugs']), back
    assert back['tabbablePlugs'] == 3, back
    assert not errors, errors


def test_a_guide_reaching_a_plug_chip_unfolds_the_card(page):
    """The reveal helpers know the row folds with its card: a chip inside
    a folded card counts as hidden by the fold, so a focus restore or a
    guide aiming at it opens the card (and a header control does not)."""
    pg, errors = page
    setup(pg, VX)
    click_arrow(pg)
    res = pg.evaluate("""() => {
        const app = window.app;
        const unit = document.querySelector('[data-lrd-distro="d1"]');
        const chip = unit.querySelector('[data-hwdock^="plug-"]');
        const gear = unit.querySelector('[data-hwpop="distro-d1"]');
        const legs = unit.querySelector(':scope > .hw-dock-legs');
        const out = { chip: app._sectionFoldHides(unit, chip),
                      gear: app._sectionFoldHides(unit, gear),
                      legs: legs ? app._sectionFoldHides(unit, legs) : null };
        app._dockRevealSections(chip);
        out.openAfter = !unit.classList.contains('lrd-sec-collapsed');
        return out;
    }""")
    assert res == {'chip': True, 'gear': False, 'legs': False, 'openAfter': True}, res
    assert pg.evaluate(CARD_JS)['outputsShown']
    assert not errors, errors


# ── Escape ends an Alt+click redraw and drops an Alt-sweep ────────────────
#
# The owner's report: Escape did nothing after an Alt+click. Escape always
# ended the redraw from the canvas, but an Alt+press keeps the browser from
# moving focus (it calls preventDefault), so a select or text box in the
# rail that still had focus took the Escape as its own. The Alt+press now
# lets go of the field the way any press on the canvas does.

POINT_JS = """([row, col]) => {
    const app = window.app, r = window.canvasRenderer;
    const layer = app.project.layers.find(l => l.name === 'WALL A');
    const p = layer.panels.find(q => q.row === row && q.col === col);
    const {dx, dy} = r.getLayerRenderOffset(layer);
    const off = r._layerCanvasOffset(layer);
    const rect = r.canvas.getBoundingClientRect();
    return {x: rect.left + (p.x + p.width / 2 + dx + off.wx) * r.zoom + r.panX,
            y: rect.top + (p.y + p.height / 2 + dy + off.wy) * r.zoom + r.panY};
}"""

# The circuits as the screen carries them, the take-over state, what is
# lit, the history and where the focus is.
POWER_JS = """() => {
    const app = window.app, r = window.canvasRenderer;
    const L = app.project.layers.find(l => l.name === 'WALL A');
    const res = app.calculatePowerAssignments(L) || { circuits: [] };
    const nums = res.nums || res.circuits.map((_, i) => i + 1);
    const circuits = res.circuits.map((c, i) => [nums[i], c.map(p => p.id)]);
    const lit = [];
    for (const [num] of circuits) if (r._runUnderlayLit(L, num)) lit.push(num);
    const ae = document.activeElement;
    return {
        circuits,
        overrides: app.getOverrideNums(L, 'power'),
        paths: JSON.parse(JSON.stringify(L.powerCustomPaths || {})),
        editing: app._overrideEditing || null,
        sweep: app._sweepSelection ? app._sweepSelection.nums : null,
        lit,
        history: app.history.map(h => h.action),
        historyIndex: app.historyIndex,
        focus: ae && ae !== document.body ? (ae.id || ae.tagName) : null,
    };
}"""

FIELDS = [None, '#power-amperage-select', '#power-panel-watts']


def focus_field(pg, sel):
    if sel:
        pg.evaluate("(s) => { const el = document.querySelector(s);"
                    " el.scrollIntoView({block: 'center'}); el.focus(); }", sel)
        assert pg.evaluate("() => document.activeElement.id") == sel[1:]


def alt_click(pg, row, col):
    pt = pg.evaluate(POINT_JS, [row, col])
    pg.mouse.move(pt['x'], pt['y'])
    pg.keyboard.down('Alt')
    pg.wait_for_timeout(100)
    pg.mouse.click(pt['x'], pt['y'])
    pg.keyboard.up('Alt')
    pg.wait_for_timeout(300)


@pytest.mark.parametrize('field', FIELDS)
def test_escape_ends_an_alt_click_redraw(page, field):
    """Alt+click a circuit, then Escape: nothing is open or lit any more,
    and no circuit changed. The take-over the Alt+click made keeps its own
    one step; ended with nothing redrawn it goes back to automatic (the
    owner, 2026-11-03: an unchanged redraw never stays a frozen override),
    one more step."""
    pg, errors = page
    setup(pg, VX)
    base = pg.evaluate(POWER_JS)
    assert base['editing'] is None and base['lit'] == [], base
    focus_field(pg, field)
    alt_click(pg, 2, 3)
    taken = pg.evaluate(POWER_JS)
    assert taken['editing'] and taken['editing']['kind'] == 'power', taken
    num = taken['editing']['num']
    assert taken['lit'] == [num], taken
    assert taken['overrides'] == [num], taken
    assert taken['history'][-1] == 'Override Circuit', taken
    # the take-over seeds the run with the cabinets it had: nothing moved
    assert taken['circuits'] == base['circuits']
    # the Alt+press let go of the field, as a plain press would
    if field:
        assert taken['focus'] != field[1:], taken

    pg.keyboard.press('Escape')
    pg.wait_for_timeout(250)
    done = pg.evaluate(POWER_JS)
    assert done['editing'] is None, done
    assert done['lit'] == [], done
    assert done['sweep'] is None, done
    # Escape changed nothing on the screen's circuits; the unchanged
    # take-over went back to automatic as its own step
    assert done['circuits'] == taken['circuits'] == base['circuits']
    assert done['overrides'] == [], done
    assert done['history'] == taken['history'] + ['Return Circuit To Auto'], done['history']
    assert not errors, errors


@pytest.mark.parametrize('field', FIELDS)
def test_escape_drops_an_alt_sweep(page, field):
    """Alt-sweep across circuits, then Escape: the selection goes, and
    nothing on the screen or in the history changed."""
    pg, errors = page
    setup(pg, VX)
    base = pg.evaluate(POWER_JS)
    focus_field(pg, field)
    a = pg.evaluate(POINT_JS, [1, 3])
    b = pg.evaluate(POINT_JS, [4, 3])
    pg.mouse.move(a['x'], a['y'])
    pg.keyboard.down('Alt')
    pg.mouse.down()
    pg.mouse.move(b['x'], b['y'], steps=8)
    pg.mouse.up()
    pg.keyboard.up('Alt')
    pg.wait_for_timeout(200)
    swept = pg.evaluate(POWER_JS)
    assert swept['sweep'] and len(swept['sweep']) == 4, swept
    assert swept['lit'] == swept['sweep'], swept
    assert swept['editing'] is None, swept

    pg.keyboard.press('Escape')
    pg.wait_for_timeout(200)
    done = pg.evaluate(POWER_JS)
    assert done['sweep'] is None and done['lit'] == [], done
    assert done['circuits'] == base['circuits']
    assert done['overrides'] == base['overrides'] == []
    assert done['history'] == base['history'] == ['Card Seed'], done['history']
    assert not errors, errors


def test_escape_without_an_alt_selection_is_unchanged(page):
    """With no redraw open and no sweep, Escape still does what it did in
    the Power view: it closes the tray's open gear popover. And a field
    the person is typing in keeps its own Escape: a press there leaves the
    field focused and changes nothing."""
    pg, errors = page
    setup(pg, VX)
    base = pg.evaluate(POWER_JS)
    pg.evaluate("(s) => document.querySelector(s).scrollIntoView({block: 'center'})",
                '[data-hwpop="distro-d1"]')
    pg.locator('[data-hwpop="distro-d1"]').first.click()
    pg.wait_for_timeout(250)
    assert pg.evaluate("() => document.getElementById('hw-gear-popover').style.display") == 'block'
    pg.keyboard.press('Escape')
    pg.wait_for_timeout(200)
    assert pg.evaluate("() => document.getElementById('hw-gear-popover').style.display") != 'block'

    focus_field(pg, '#power-panel-watts')
    pg.keyboard.press('Escape')
    pg.wait_for_timeout(200)
    after = pg.evaluate(POWER_JS)
    assert after['focus'] == 'power-panel-watts', after
    assert after['circuits'] == base['circuits']
    assert after['history'] == base['history'], after['history']
    pg.evaluate("() => document.activeElement && document.activeElement.blur()")
    assert not errors, errors
