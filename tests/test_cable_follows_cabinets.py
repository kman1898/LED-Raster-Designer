"""A circuit's cable stays with its cabinets when the circuits renumber.

The owner, 2026-11-04: "I have an extension on circuit six, but then after
balancing it goes to circuit five. The extension needs to follow that
move." Ruled the same day: when the automatic plan renumbers, a circuit's
cable (its length and its connector pick) FOLLOWS THE CABINETS. It stays
with the circuit's first cabinet, the one it plugs into:

- that cabinet still starts a circuit: the cable is on that circuit;
- it no longer starts one: the cable goes to the circuit that now holds
  it, and a toast names the screen and the circuit;
- two cables land on one circuit: the one plugged into that circuit's own
  first cabinet stays (else the one whose cabinet comes first on the
  circuit), the other is removed, and a toast names the screen and the
  circuit.

Covered here, each through the app's own gesture: Organized to Max
Capacity, 2fer packing on and off, the Circuit numbers switch, Return to
automatic, a redraw that ends with its circuit cut back (the cabinets it
held slide into the walk), a redraw that ends with nothing drawn, and a
redraw ended by redrawing another circuit. One undo puts every cable back,
in the browser and on the server. The Organized, Max, Organized round trip
does not bring a cable back to its old number; the ruling accepts that.

Every test leaves the shared server project as it found it
(conftest.server_project_guard).
"""

import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from conftest import settled  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    # A real Windows dialog must never open on the desktop running the tests.
    for kind in ('save-file', 'open-file', 'select-directory'):
        pg.route(f'**/api/native-dialog/{kind}',
                 lambda r: r.fulfill(status=200, content_type='application/json',
                                     body='{"cancelled": true}'))
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    pg.wait_for_function(
        '() => window.app && Array.isArray(window.app.history) && window.app.history.length > 0',
        timeout=60000)
    pg.evaluate(HELPERS_JS)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_function("() => window.canvasRenderer && window.canvasRenderer.viewMode === 'power'")
    yield pg
    assert errors == [], errors
    context.close()


# 208 W cabinets on 208 V: a circuit carries 0.8 x amps cabinets (US 80%).
HELPERS_JS = r"""
window.__cf = {
    screen(o) {
        o = Object.assign({
            type: 'screen', visible: true, locked: false, id: 1, name: 'A',
            columns: 6, rows: 4, cabinet_width: 128, cabinet_height: 128,
            offset_x: 0, offset_y: 0, panel_weight: 20, weight_unit: 'kg',
            panelWatts: 208, powerVoltage: 208, powerAmperage: 5,
            processorType: 'novastar-armor', bitDepth: 8, frameRate: 60, lowLatency: false,
            flowPattern: 'tl-h', portMappingMode: 'organized',
            powerFlowPattern: 'tl-v', powerOrganized: true, powerMaximize: false,
            powerLabelTemplate: 'S1-#',
            group_id: null, powerSocaDistro: { 1: 'd1', 2: 'd1' }, powerSocaNumber: {},
            powerSocaLengths: {}, powerCircuitCables: {}, powerSocaKeying: 'index',
            showPowerCableTags: true,
        }, o || {});
        o.panels = [];
        for (let r = 0; r < o.rows; r++) for (let c = 0; c < o.columns; c++) {
            o.panels.push({ row: r, col: c,
                x: o.offset_x + c * o.cabinet_width, y: o.offset_y + r * o.cabinet_height,
                width: o.cabinet_width, height: o.cabinet_height,
                hidden: false, blank: false, halfTile: 'none' });
        }
        return o;
    },
    project(layer) {
        return { name: 'Cables follow', cableUnit: 'ft',
            distros: [{ id: 'd1', name: 'SL', ratingA: 400, system: '120/208',
                        voltage: 208, phase: 3 }],
            layers: [this.screen(layer)] };
    },
    async j(method, url, body) {
        const r = await fetch(url, { method,
            headers: { 'Content-Type': 'application/json' },
            body: body === undefined ? undefined : JSON.stringify(body) });
        const out = await r.json();
        if (!r.ok) throw new Error(url + ': ' + JSON.stringify(out));
        return out;
    },
    async open(layer) {
        const app = window.app;
        if (app._overrideEditing) app.endOverrideEdit();
        await this.j('PUT', '/api/project', this.project(layer));
        app.project = await this.j('GET', '/api/project');
        app.dedupeProjectLayers('cable_follows');
        app.selectLayer(app.project.layers[0]);
        app.selectedLayerIds = new Set([app.project.layers[0].id]);
        app._circuitTailCache = null;
        app._distroFaceMemo = null;
        app._overrideEditing = null;
        app._powerHeld = null;
        await app.refreshProcessors();
        app.resetHistory('Initial State');
        app.renderLayers();
        this.toasts = [];
        if (!app.__cfToast) {
            const real = app._toast;
            app._toast = function (msg, ...rest) {
                window.__cf.toasts.push(String(msg));
                return real.call(this, msg, ...rest);
            };
            app.__cfToast = true;
        }
        return true;
    },
    layer() { return window.app.project.layers[0]; },
    inflight() {
        const s = window.app._inflightLayerPuts;
        return !s || s.size === 0;
    },
    // circuit number -> its cabinets ("row.col", walk order)
    plan() {
        const app = window.app;
        app._circuitTailCache = null;
        const out = {};
        app.screenCircuits(this.layer()).forEach(c => {
            out[c.num] = c.panels.map(p => `${p.row}.${p.col}`);
        });
        return out;
    },
    // circuit number -> feet, as stored
    cables() {
        const out = {};
        const s = this.layer().powerCircuitCables || {};
        Object.keys(s).forEach(k => { out[k] = s[k].ft; });
        return out;
    },
    // first cabinet -> feet, for the cables on real circuits
    byHead() {
        const plan = this.plan();
        const out = {};
        Object.entries(this.cables()).forEach(([k, ft]) => {
            if (plan[k]) out[plan[k][0]] = ft;
        });
        return out;
    },
    setCables(map) {
        const app = window.app;
        const l = this.layer();
        Object.entries(map).forEach(([num, ft]) => app.setCircuitCable(l, Number(num), { ft, connector: null }, false));
        app.saveClientSideProperties();
        app.updateLayers([l], true, 'Set Circuit Cable');
    },
    change(id, checked) {
        const el = document.getElementById(id);
        el.checked = checked;
        el.dispatchEvent(new Event('change', { bubbles: true }));
    },
};
"""


def _server():
    import app as app_module
    return app_module.current_project


def _srv_cables(project):
    layer = (project.get('layers') or [{}])[0]
    return {k: v.get('ft') for k, v in (layer.get('powerCircuitCables') or {}).items()}


def _settle(pg):
    pg.wait_for_function('() => window.__cf.inflight()')


def _wait_server(pg, want):
    got = settled(pg, lambda: _srv_cables(copy.deepcopy(_server())), lambda v: v == want, 8000)
    assert got == want, got


def _open(pg, layer, cables=None):
    pg.evaluate("(l) => window.__cf.open(l)", layer)
    _settle(pg)
    if cables:
        pg.evaluate("(m) => window.__cf.setCables(m)", {str(k): v for k, v in cables.items()})
        _settle(pg)


def _plan(pg):
    return pg.evaluate("() => window.__cf.plan()")


def _cables(pg):
    return pg.evaluate("() => window.__cf.cables()")


def _toasts(pg):
    return pg.evaluate("() => window.__cf.toasts.slice()")


def _expected(before_plan, before_cables, after_plan):
    """The ruling, worked by hand: each cable to the circuit its first
    cabinet starts, else the one holding it; on a tie the one that starts
    the circuit, then the earlier cabinet, then the lower old number."""
    starts = {cells[0]: int(n) for n, cells in after_plan.items()}
    holds = {}
    for n, cells in after_plan.items():
        for i, cell in enumerate(cells):
            holds.setdefault(cell, (int(n), i))
    claims = {}
    for old, ft in before_cables.items():
        head = before_plan[str(old)][0]
        if head in starts:
            claims.setdefault(starts[head], []).append((0, 0, int(old), ft))
        elif head in holds:
            num, at = holds[head]
            claims.setdefault(num, []).append((1, at, int(old), ft))
    return {str(n): sorted(c)[0][3] for n, c in claims.items()}


def _undo_restores(pg, plan, cables):
    pg.evaluate("() => window.app.undo()")
    _settle(pg)
    assert _plan(pg) == plan
    assert _cables(pg) == cables
    _wait_server(pg, cables)


# ── Organized and Max Capacity ────────────────────────────────────────────

def test_organized_to_max_carries_each_cable_to_its_first_cabinet(page):
    """6 x 4 at four cabinets a circuit: Organized gives one column a
    circuit. Max Capacity packs five. Circuit 1 keeps its cable; 2's first
    cabinet is now inside circuit 2 (toast); 4 keeps its own; 5's first
    cabinet is inside circuit 4, where 4's cable is plugged in, so 5's is
    removed (toast); 6's first cabinet is inside circuit 5, so its cable
    moves to 5 (toast)."""
    pg = page
    _open(pg, {'powerAmperage': 6.25}, {1: 10, 2: 15, 4: 25, 5: 30, 6: 50})
    before_plan, before = _plan(pg), _cables(pg)
    assert list(before_plan) == ['1', '2', '3', '4', '5', '6']
    pg.evaluate("() => window.__cf.change('power-maximize', true)")
    _settle(pg)
    after_plan = _plan(pg)
    assert len(after_plan) == 5, after_plan
    want = _expected(before_plan, before, after_plan)
    assert want == {'1': 10, '2': 15, '4': 25, '5': 50}, want
    assert _cables(pg) == want
    _wait_server(pg, {k: v for k, v in want.items()})
    said = ' '.join(_toasts(pg))
    assert 'A: two cables landed on circuit SL1-4' in said, said
    assert "30' TRUE1 from SL1-5 was removed" in said, said
    assert 'moved to circuit SL1-5' in said, said
    assert pg.evaluate("() => window.app.history.slice(-1)[0].action") == 'Change Power Mode'
    _undo_restores(pg, before_plan, before)


def test_max_back_to_organized_follows_the_cabinets_not_the_old_numbers(page):
    """The round trip: Max then Organized. Each cable follows its first
    cabinet both ways, so it does not come back to its old number (the
    ruling accepts that); undo takes one step back at a time."""
    pg = page
    _open(pg, {'powerAmperage': 6.25}, {3: 12, 6: 50})
    p0, c0 = _plan(pg), _cables(pg)
    pg.evaluate("() => window.__cf.change('power-maximize', true)")
    _settle(pg)
    p1, c1 = _plan(pg), _cables(pg)
    assert c1 == _expected(p0, c0, p1)
    pg.evaluate("() => window.__cf.change('power-organized', true)")
    _settle(pg)
    p2, c2 = _plan(pg), _cables(pg)
    assert p2 == p0
    assert c2 == _expected(p1, c1, p2)
    _undo_restores(pg, p1, c1)
    _undo_restores(pg, p0, c0)


# ── 2fer packing ──────────────────────────────────────────────────────────

def test_2fer_packing_on_and_off_carries_the_cables(page):
    """6 x 3 at ten cabinets a circuit: Organized daisies three columns a
    circuit (two circuits); 2fers share two columns (three circuits).
    Turning 2fers on: circuit 2's first cabinet (column 4) is inside the
    new circuit 2 (toast). Turning them off again: the cables on 2 and 3
    land inside circuits 1 and 2, where 1's own cable stays (toast)."""
    pg = page
    _open(pg, {'rows': 3, 'powerAmperage': 12.5,
                'powerSplitters': {'enabled': False, 'maxWays': 2,
                                   'manual': {'merge': [], 'split': [], 'space': None}}},
          {1: 10, 2: 20})
    p0, c0 = _plan(pg), _cables(pg)
    assert len(p0) == 2, p0
    pg.evaluate("() => window.__cf.change('power-splitters-enabled', true)")
    _settle(pg)
    p1, c1 = _plan(pg), _cables(pg)
    assert len(p1) == 3, p1
    assert c1 == _expected(p0, c0, p1) == {'1': 10, '2': 20}
    assert 'A: the 20\' TRUE1 on circuit SL1-2 moved to circuit SL1-2' in ' '.join(_toasts(pg))
    assert pg.evaluate("() => window.app.history.slice(-1)[0].action") == 'Change Splitter Packing'
    # a cable on the third 2fer, then packing off
    pg.evaluate("() => window.__cf.setCables({3: 30})")
    _settle(pg)
    p1, c1 = _plan(pg), _cables(pg)
    pg.evaluate("() => window.__cf.change('power-splitters-enabled', false)")
    _settle(pg)
    p2, c2 = _plan(pg), _cables(pg)
    assert p2 == p0
    assert c2 == _expected(p1, c1, p2) == {'1': 10, '2': 30}, c2
    said = ' '.join(_toasts(pg))
    assert 'A: two cables landed on circuit SL1-1' in said, said
    _wait_server(pg, {'1': 10, '2': 30})
    _undo_restores(pg, p1, c1)


# ── The Circuit numbers switch ────────────────────────────────────────────

def test_the_circuit_numbers_switch_keeps_each_cable_on_its_cabinets(page):
    """6 x 6 at four cabinets a circuit cuts each column in two. Along the
    walk the top and bottom of a column are 1 and 2; Across numbers every
    top first. The cables stay on the same cabinets under the new
    numbers."""
    pg = page
    _open(pg, {'rows': 6, 'powerAmperage': 5}, {2: 10, 3: 20, 12: 30})
    p0, c0 = _plan(pg), _cables(pg)
    by_head = pg.evaluate("() => window.__cf.byHead()")
    pg.evaluate("""() => {
        const across = document.querySelector('#power-number-order-row [data-order="across"]');
        const down = document.querySelector('#power-number-order-row [data-order="down"]');
        const cur = window.app.powerNumberOrder(window.__cf.layer(), false);
        (cur === 'across' ? down : across).click();
    }""")
    _settle(pg)
    p1 = _plan(pg)
    assert p1 != p0, 'the switch did not renumber'
    assert sorted(map(tuple, p1.values())) == sorted(map(tuple, p0.values()))
    assert pg.evaluate("() => window.__cf.byHead()") == by_head
    assert _cables(pg) != c0
    _undo_restores(pg, p0, c0)


# ── Redraws ───────────────────────────────────────────────────────────────
#
# 8 x 4 at four cabinets a circuit: one column a circuit. Circuit 3 taken
# over and drawn on the top half of column 2 leaves its bottom half as
# circuit 4, so every circuit after it is one number up: column 3 is 5,
# column 7 is 9.

REDRAWN = {'columns': 8, 'rows': 4, 'powerAmperage': 5,
           'powerCustomOverrides': [3],
           'powerCustomPaths': {'3': [{'row': 0, 'col': 2}, {'row': 1, 'col': 2}]},
           'powerCustomIndex': 3}


def test_return_to_automatic_moves_each_cable_down_a_number(page):
    """Return circuit 3 to automatic: column 2 is one circuit again and
    every circuit after it is a number lower. 5's cable (column 3) goes to
    4 and 9's (column 7) to 8. The bottom half's own cable is inside the
    new circuit 3, where 3's is plugged in: 3's stays, the other goes
    (toast). One undo puts them all back."""
    pg = page
    _open(pg, REDRAWN, {3: 6, 4: 8, 5: 25, 9: 50})
    p0, c0 = _plan(pg), _cables(pg)
    assert p0['5'][0] == '0.3' and p0['9'][0] == '0.7', p0
    pg.evaluate("() => window.app.returnRunToAuto(window.__cf.layer(), 'power', 3)")
    _settle(pg)
    p1 = _plan(pg)
    assert list(p1) == [str(n) for n in range(1, 9)], p1
    assert _cables(pg) == _expected(p0, c0, p1) == {'3': 6, '4': 25, '8': 50}
    assert 'A: two cables landed on circuit SL1-3' in ' '.join(_toasts(pg))
    _wait_server(pg, {'3': 6, '4': 25, '8': 50})
    assert pg.evaluate("() => window.app.history.slice(-1)[0].action") == 'Return Circuit To Auto'
    _undo_restores(pg, p0, c0)


def test_a_redraw_cut_back_slides_the_circuits_after_it_with_their_cables(page):
    """Redraw circuit 3 (the whole of column 2) and cut it to the top half,
    then Esc. The bottom half it held goes back to the walk as circuit 4,
    and every circuit after slides a number up: 4's cable (column 3) goes
    to 5, 8's (column 7) to 9. One undo puts them back."""
    pg = page
    _open(pg, {'columns': 8, 'rows': 4, 'powerAmperage': 5}, {4: 25, 8: 50})
    p0, c0 = _plan(pg), _cables(pg)
    pg.evaluate("""() => { const a = window.app, l = window.__cf.layer();
        a.overrideRun(l, 'power', 3);
        l.powerCustomPaths[3] = l.powerCustomPaths[3].slice(0, 2);
        a.saveState('Power Custom Path Edit');
        a.updateLayers([l]); }""")
    _settle(pg)
    # still open: the cut-off cabinets are held, nothing renumbered yet
    assert _cables(pg) == c0
    p_open = _plan(pg)
    pg.locator('#main-canvas').hover()
    pg.keyboard.press('Escape')
    _settle(pg)
    assert pg.evaluate("() => window.app._overrideEditing") is None
    p1 = _plan(pg)
    assert p1['5'][0] == '0.3' and p1['9'][0] == '0.7', p1
    assert _cables(pg) == {'5': 25, '9': 50}
    _wait_server(pg, {'5': 25, '9': 50})
    assert pg.evaluate("() => window.app.history.slice(-1)[0].action") == 'End Circuit Redraw'
    # Undo walks back one step at a time: the cables, the cut, the takeover.
    assert p_open
    for _ in range(3):
        pg.evaluate("() => window.app.undo()")
        _settle(pg)
    assert _plan(pg) == p0
    assert _cables(pg) == c0
    _wait_server(pg, c0)


def test_a_redraw_left_with_nothing_drawn_hands_the_cables_back(page):
    """The redrawn circuit 3 (top of column 2) is opened, its path cleared,
    and Esc: nothing was drawn, so it goes back to automatic and the
    circuits after it close up, each cable with its cabinets."""
    pg = page
    _open(pg, REDRAWN, {5: 25, 9: 50})
    pg.evaluate("""() => { const a = window.app, l = window.__cf.layer();
        a.beginOverrideEdit(l, 'power', 3);
        l.powerCustomPaths[3] = [];
        a.saveState('Power Custom Path Edit');
        a.updateLayers([l]); }""")
    _settle(pg)
    pg.locator('#main-canvas').hover()
    pg.keyboard.press('Escape')
    _settle(pg)
    p1 = _plan(pg)
    assert pg.evaluate("() => window.__cf.layer().powerCustomOverrides") == []
    assert p1['4'][0] == '0.3' and p1['8'][0] == '0.7', p1
    assert _cables(pg) == {'4': 25, '8': 50}
    _wait_server(pg, {'4': 25, '8': 50})


def test_redrawing_another_circuit_ends_the_first_and_carries_the_cables(page):
    """Redraw circuit 3 cut to the top half, then take over circuit 6
    (column 5) without pressing Esc: circuit 3's redraw ends there, the
    circuits after it slide a number up and 4's cable (column 3) is on 5."""
    pg = page
    _open(pg, {'columns': 8, 'rows': 4, 'powerAmperage': 5}, {4: 25})
    pg.evaluate("""() => { const a = window.app, l = window.__cf.layer();
        a.overrideRun(l, 'power', 3);
        l.powerCustomPaths[3] = l.powerCustomPaths[3].slice(0, 2);
        a.saveState('Power Custom Path Edit');
        a.updateLayers([l]); }""")
    _settle(pg)
    pg.evaluate("""() => { const a = window.app, l = window.__cf.layer();
        a.overrideRun(l, 'power', 6); }""")
    _settle(pg)
    p1 = _plan(pg)
    assert p1['5'][0] == '0.3', p1
    assert _cables(pg) == {'5': 25}
    _wait_server(pg, {'5': 25})
