"""Power fixes from the 1.6.0-beta.4 QA pass, round 3.

- A circuit drawn after a Clear Circuit keeps every plugged circuit on its
  tail: the freed tail stays free, the newcomer takes the next one (it used
  to re-pack the multi onto the freed tail, 1, 3, 4 on tails 1, 3, 4 read
  1, 3, 4, 5 on tails 1-4).

Every test checks the browser (and the server's project where a change is
written), waits on real conditions, and leaves the shared server project as
it found it (conftest.server_project_guard).
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
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
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


# 208V x 5A / 208W = five cabinets a circuit, tl-v organized, five rows: a
# screen's `columns` IS its circuit count. The distros' outputs are on the
# screens' own 6.25 A breakers, since plugged-in circuits pack to the
# output's breaker (owner, 2026-11-12). PD is a distro FACE - five TRUE1
# direct outputs (1-5) then two soca multis (6, 7); SR an old-style distro.
HELPERS_JS = r"""
window.__pu = {
    screen(o) {
        o = Object.assign({
            type: 'screen', visible: true, locked: false,
            columns: 5, rows: 5, cabinet_width: 128, cabinet_height: 128,
            offset_x: 0, offset_y: 0, panel_weight: 20, weight_unit: 'kg',
            panelWatts: 208, powerVoltage: 208, powerAmperage: 6.25,
            processorType: 'novastar-armor', bitDepth: 8, frameRate: 60, lowLatency: false,
            flowPattern: 'tl-h', portMappingMode: 'organized',
            powerFlowPattern: 'tl-v', powerOrganized: true, powerMaximize: false,
            group_id: null, powerSocaDistro: {}, powerSocaNumber: {},
            powerSocaLengths: {}, powerCircuitCables: {}, powerSocaKeying: 'index',
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
    project(layers, extra) {
        return Object.assign({
            name: 'Power round 3', cableUnit: 'ft',
            distros: [
                { id: 'd1', name: 'PD', ratingA: 200, system: '120/208',
                  outputRows: [
                      { id: 'r1', connector: 'true1', count: 5, coupling: 'll', breakerA: 6.25 },
                      { id: 'r2', connector: 'soca', count: 2, coupling: 'll', breakerA: 6.25 }] },
                { id: 'd2', name: 'SR', ratingA: 400, system: '120/208', voltage: 208, phase: 3 },
            ],
            layers: layers.map((l, i) => this.screen(Object.assign(
                { id: i + 1, name: `W${i + 1}`, offset_x: i * 900 }, l))),
        }, extra || {});
    },
    async j(method, url, body) {
        const r = await fetch(url, { method,
            headers: { 'Content-Type': 'application/json' },
            body: body === undefined ? undefined : JSON.stringify(body) });
        const out = await r.json();
        if (!r.ok) throw new Error(url + ': ' + JSON.stringify(out));
        return out;
    },
    async open(project) {
        const app = window.app;
        await this.j('PUT', '/api/project', project);
        app.project = await this.j('GET', '/api/project');
        app.dedupeProjectLayers('power_r3');
        app.selectedLayerIds = new Set();
        app.selectLayer(app.project.layers[0]);
        app._circuitTailCache = null;
        app._distroFaceMemo = null;
        app._assignment = null;
        await app.refreshProcessors();
        app.resetHistory('Initial State');
        app.renderLayers();
        return true;
    },
    layer(name) {
        return window.app.project.layers.find(l => l.name === name);
    },
    // Every multi of a screen as the naming reads it.
    socas(name) {
        const app = window.app;
        app._circuitTailCache = null;
        const l = this.layer(name);
        return [...app._powerNaming(l).socas.values()].map(r => ({
            index: r.index, circuits: r.circuits.slice(), distro: r.distroId || null,
            number: r.distroId ? Number(r.number) : null,
            length: (l.powerSocaLengths || {})[r.index] || null }));
    },
    inflight() {
        const s = window.app._inflightLayerPuts;
        return !s || s.size === 0;
    },
};
"""


def _server():
    import app as app_module
    return app_module.current_project


def _srv_layer(name, project=None):
    p = project if project is not None else _server()
    return next((l for l in (p.get('layers') or []) if l.get('name') == name), None)


def _wait_server(pg, ok, timeout_ms=8000):
    return settled(pg, lambda: copy.deepcopy(_server()), ok, timeout_ms)


def _open(pg, layers, extra=None):
    pg.evaluate("([l, e]) => window.__pu.open(window.__pu.project(l, e))", [layers, extra])
    pg.wait_for_function('() => window.__pu.inflight()')


def _settle(pg):
    pg.wait_for_function('() => window.__pu.inflight()')


def _socas(pg, name):
    return pg.evaluate("(n) => window.__pu.socas(n)", name)


def _unplug_circuit(pg, name, circuit):
    """The tray chip's Unplug circuit, on the multi holding `circuit`."""
    pg.evaluate("""([n, c]) => {
        const app = window.app, l = window.__pu.layer(n);
        app._circuitTailCache = null;
        const rec = [...app._powerNaming(l).socas.values()].find(r => r.circuits.includes(c));
        app._clearCircuitChip(l, rec.index, c);
    }""", [name, circuit])
    _settle(pg)


# ── A circuit drawn after a Clear Circuit ─────────────────────────────────

def _col(c, rows=5):
    return [{'row': r, 'col': c} for r in range(rows)]


def _labels(pg, name):
    return pg.evaluate("""(n) => { const app = window.app, l = window.__pu.layer(n);
        app._circuitTailCache = null;
        return app.screenCircuits(l).map(c => [c.num, app.getPowerCircuitLabel(l, c.num)]); }""", name)


def _draw(pg, name, col):
    pg.evaluate("""([n, c]) => { const app = window.app, l = window.__pu.layer(n);
        l.panels.filter(p => p.col === c).sort((a, b) => a.row - b.row)
            .forEach(p => app.addPanelToCustomPowerPath(p, l)); }""", [name, col])
    _settle(pg)


def _type_active(pg, value):
    f = pg.locator('#power-custom-active')
    f.scroll_into_view_if_needed()
    f.fill(str(value))
    f.press('Enter')
    _settle(pg)


def _clear_circuit(pg):
    btn = pg.locator('#power-custom-clear-circuit')
    btn.scroll_into_view_if_needed()
    btn.click()
    _settle(pg)


def test_a_circuit_drawn_after_a_clear_leaves_the_freed_tail_free(page):
    """Custom circuits 1-4 on SR 9. Clear Circuit 2, then draw the next
    circuit: 1, 3 and 4 stay on SR9-1, -3, -4 and the newcomer takes
    SR9-5 - it used to re-pack the multi, 3 reading SR9-2 and 5 SR9-4.
    The Active Circuit field counts the held gap, so it agrees with the
    labels (it read 2 over SR9-3). The server keeps the tails; the label the field predicts is the one
    drawn; undo takes the newcomer back off, a cabinet a step."""
    pg = page
    _open(pg, [{'columns': 8, 'powerFlowPattern': 'custom', 'powerCustomIndex': 2,
                'powerCustomPaths': {str(i + 1): _col(i) for i in range(4)},
                'powerSocaDistro': {'1': 'd2'}, 'powerSocaNumber': {'1': 9}}])
    _clear_circuit(pg)
    assert _labels(pg, 'W1') == [[1, 'SR9-1'], [3, 'SR9-3'], [4, 'SR9-4']]
    # the field reads the held gap as place 2 and circuit 3 as 3, the
    # number its label prints (it read 2 over SR9-3)
    assert pg.locator('#power-custom-active').input_value() == '2'
    pg.locator('#power-custom-next').click()
    _settle(pg)
    assert pg.locator('#power-custom-active').input_value() == '3'
    assert pg.evaluate("() => window.__pu.layer('W1').powerCustomIndex") == 3
    _type_active(pg, 5)  # the place after the last circuit: run 5
    assert pg.evaluate("() => window.__pu.layer('W1').powerCustomIndex") == 5
    predicted = pg.evaluate("() => window.app.getPowerCircuitLabel(window.__pu.layer('W1'), 5)")
    assert predicted == 'SR9-5', predicted
    _draw(pg, 'W1', 4)
    assert _labels(pg, 'W1') == [[1, 'SR9-1'], [3, 'SR9-3'], [4, 'SR9-4'], [5, 'SR9-5']]
    srv = _wait_server(pg, lambda p: '5' in (_srv_layer('W1', p).get('powerCustomPaths') or {}))
    assert _srv_layer('W1', srv).get('powerSocaPhasePos') == {'1': [1, 3, 4, 5]}
    pg.evaluate("() => { for (let i = 0; i < 5; i++) window.app.undo(); }")
    _settle(pg)
    assert _labels(pg, 'W1') == [[1, 'SR9-1'], [3, 'SR9-3'], [4, 'SR9-4']]
    # the undo's layer writes land before the next test opens its project
    _wait_server(pg, lambda p: '5' not in (_srv_layer('W1', p).get('powerCustomPaths') or {}))
    pg.wait_for_timeout(300)
    _settle(pg)


def test_a_cleared_circuit_drawn_again_takes_its_own_tail_back(page):
    """Two full multis, SR 1 and SR 2. Clear circuit 3, draw circuit 13
    past the end, then draw 3 again: 13 opens a multi of its own (it used
    to read SR2-7, a seventh tail on a six-way box), and 3 goes back to
    SR1-3 with every other circuit where it was (it used to slide 4-12
    down a tail and 13 onto SR2)."""
    pg = page
    _open(pg, [{'columns': 14, 'powerFlowPattern': 'custom', 'powerCustomIndex': 3,
                'powerCustomPaths': {str(i + 1): _col(i) for i in range(12)},
                'powerSocaDistro': {'1': 'd2', '2': 'd2'}, 'powerSocaNumber': {'1': 1, '2': 2}}])
    want = [[i, f'SR{1 if i <= 6 else 2}-{(i - 1) % 6 + 1}'] for i in range(1, 13)]
    _clear_circuit(pg)
    assert _labels(pg, 'W1') == [w for w in want if w[0] != 3]
    pg.evaluate("() => { window.__pu.layer('W1').powerCustomIndex = 13; window.app.updateCustomPowerUI(); }")
    _draw(pg, 'W1', 12)
    got = _labels(pg, 'W1')
    assert got[:-1] == [w for w in want if w[0] != 3], got
    assert got[-1][0] == 13 and not got[-1][1].startswith('SR'), got
    pg.evaluate("() => { window.__pu.layer('W1').powerCustomIndex = 3; window.app.updateCustomPowerUI(); }")
    _draw(pg, 'W1', 2)
    got = _labels(pg, 'W1')
    assert got[:-1] == want, got
    assert not got[-1][1].startswith('SR'), got


# ── An L6-20 breakout plugs into an L6-20 output, and only that ─────────

def _cab_point(pg, name, row, col):
    return pg.evaluate("""([n, r, c]) => {
        const R = window.canvasRenderer, L = window.__pu.layer(n);
        const cv = R.canvas.getBoundingClientRect();
        return [cv.x + R.panX + (L.offset_x + (c + 0.5) * L.cabinet_width) * R.zoom,
                cv.y + R.panY + (L.offset_y + (r + 0.5) * L.cabinet_height) * R.zoom];
    }""", [name, row, col])


L620_DISTROS = {'distros': [
    {'id': 'd1', 'name': 'PD', 'ratingA': 200, 'system': '120/208',
     'outputRows': [{'id': 'r1', 'connector': 'true1', 'count': 2, 'coupling': 'll', 'breakerA': 6.25},
                    {'id': 'r2', 'connector': 'soca', 'count': 1, 'coupling': 'll', 'breakerA': 6.25},
                    {'id': 'r3', 'connector': 'l620', 'count': 6, 'coupling': 'll', 'breakerA': 6.25}]},
    {'id': 'd2', 'name': 'SR', 'ratingA': 400, 'system': '120/208', 'voltage': 208, 'phase': 3}]}


def test_an_l6_20_screen_takes_only_a_distros_l6_20_outputs(page):
    """The owner's ruling, 2026-11-03: "L620 breakout should only be
    connected to an L620 cable, which would come off of the distro at
    L620". A 208V screen on Multi → L6-20: a Multi 208, a Socapex 208V
    and a TRUE1 output all refuse it, saying where it plugs in; each
    circuit dropped on the distro's L6-20 outputs lands on one, and the
    pull list carries one L6-20 cable per circuit."""
    pg = page
    _open(pg, [{'columns': 3, 'powerBreakoutType': 'soca-l620', 'powerPanelInput': 'true1'}],
          L620_DISTROS)
    out = pg.evaluate("""() => { const app = window.app, l = window.__pu.layer('W1');
        const s = app.getSocaPlan(l)[0];
        const gate = (row) => app._plugGate({ distroId: 'd1', output: 'face:' + row }, l);
        return { sr: app._distroDropRefusal({ distroId: 'd2' }, l, s),
                 pd: app._distroDropRefusal({ distroId: 'd1' }, l, s),
                 true1: gate('r1').message || null, soca: gate('r2').message || null,
                 l620: gate('r3').ok }; }""")
    said = "W1 is set to Multi → L6-20: its circuits take an L6-20 cable off a distro's L6-20 output"
    assert all(out[k].startswith(said) for k in ('sr', 'pd', 'true1', 'soca')), out
    assert out['l620'] is True, out
    for _ in range(3):
        pg.evaluate("""() => { const app = window.app, l = window.__pu.layer('W1');
            app._dockDropPlug({ type: 'plug', distroId: 'd1', output: 'face:r3', title: 'PD L6-20' },
                              { kind: 'screen', layerId: l.id }); }""")
        _settle(pg)
    got = [(s['distro'], s['number'], s['circuits']) for s in _socas(pg, 'W1')]
    assert got == [('d1', 4, [1]), ('d1', 5, [2]), ('d1', 6, [3])], got
    srv = _wait_server(pg, lambda p: len(_srv_layer('W1', p).get('powerSocaDistro') or {}) == 3)
    assert set((_srv_layer('W1', srv).get('powerSocaDistro') or {}).values()) == {'d1'}
    rows = pg.evaluate("""() => window.app.buildPullList().positions
        .flatMap(p => p.rows).map(r => [r.type, r.qty])""")
    assert ['L6-20 → TRUE1', 3] in rows, rows
    assert not any(t.startswith('Multi') for t, _ in rows), rows


# ── Sharing a free tail never renumbers the box's own multi ──────────────

def test_sharing_a_free_tail_keeps_the_owner_on_its_number(page):
    """W1's two automatic multis hold SR 3 and SR 4 (SR 2 is free); W2
    sits on SR 1. Dragging SR4's free tail 5 onto W2's circuit 3 shares
    the box: W1 stays SR4-1 to SR4-4 and W2's circuit reads SR4-5. It
    used to move W1's four circuits to SR2 without a word - the pin the
    share writes outvoted the number W1 held. One undo puts both back;
    the server keeps W1 on SR 4."""
    pg = page
    _open(pg, [{'columns': 10, 'powerSocaDistro': {'1': 'd2', '2': 'd2'}},
               {'columns': 5, 'offset_x': 1500, 'powerSocaDistro': {'1': 'd2'}}])
    pg.evaluate("""() => { const app = window.app;
        const d = app.project.distros.find(x => x.id === 'd2');
        d.multiNumbers = { '1:1': 3, '1:2': 4, '2:1': 1 };
        app._circuitTailCache = null; app._resetMultiBaseline(); app.resetHistory('seed'); }""")
    w1 = [[i, f'SR{3 if i <= 6 else 4}-{(i - 1) % 6 + 1}'] for i in range(1, 11)]
    assert _labels(pg, 'W1') == w1
    pg.evaluate("""() => { const app = window.app, l = window.__pu.layer('W2');
        app._dockDropTail({ type: 'tail', distroId: 'd2', number: '4', tail: 5, title: 'SR 4' },
                          { kind: 'run', layerId: l.id, num: 3 }); }""")
    _settle(pg)
    assert _labels(pg, 'W1') == w1, _labels(pg, 'W1')
    assert _labels(pg, 'W2')[2] == [3, 'SR4-5'], _labels(pg, 'W2')
    srv = _wait_server(pg, lambda p: (_srv_layer('W2', p).get('powerSocaNumber') or {}).get('2') == 4)
    assert (_srv_layer('W1', srv).get('powerSocaNumber') or {}).get('2') == 4
    pg.evaluate("() => window.app.undo()")
    _settle(pg)
    assert _labels(pg, 'W1') == w1
    assert [lab for _, lab in _labels(pg, 'W2')] == [f'SR1-{i}' for i in range(1, 6)]


def test_sharing_a_locked_screens_box_is_still_refused(page):
    """The same share with W1 locked: W1 cannot be written to hold its
    number, so the drop is refused whole and W1 named, as before."""
    pg = page
    _open(pg, [{'columns': 10, 'locked': True, 'powerSocaDistro': {'1': 'd2', '2': 'd2'}},
               {'columns': 5, 'offset_x': 1500, 'powerSocaDistro': {'1': 'd2'}}])
    pg.evaluate("""() => { const app = window.app;
        const d = app.project.distros.find(x => x.id === 'd2');
        d.multiNumbers = { '1:1': 3, '1:2': 4, '2:1': 1 };
        app._circuitTailCache = null; app._resetMultiBaseline(); app.resetHistory('seed'); }""")
    n = pg.evaluate("() => window.app.history.length")
    pg.evaluate("""() => { const app = window.app, l = window.__pu.layer('W2');
        app._dockDropTail({ type: 'tail', distroId: 'd2', number: '4', tail: 5, title: 'SR 4' },
                          { kind: 'run', layerId: l.id, num: 3 }); }""")
    _settle(pg)
    assert [lab for _, lab in _labels(pg, 'W2')] == [f'SR1-{i}' for i in range(1, 6)]
    assert _labels(pg, 'W1')[6] == [7, 'SR4-1']
    assert pg.evaluate("() => window.app.history.length") == n
    assert pg.evaluate("() => window.__pu.layer('W1').powerSocaNumber") in ({}, None)


# ── A group's Power readout ───────────────────────────────────────────────

READOUT_JS = """(names) => {
    const app = window.app;
    const ls = names.map(n => window.__pu.layer(n));
    app.selectLayer(ls[ls.length - 1]);
    app.selectedLayerIds = new Set(ls.map(l => l.id));
    app.updatePowerCapacityDisplay();
    return ['power-circuits-required', 'power-total-amps-1ph', 'power-total-amps-3ph']
        .map(id => document.getElementById(id).textContent);
}"""


def test_a_group_reads_the_walls_figures_whichever_member_is_current(page):
    """W1 and W2 grouped: W1 carries the wall's five circuits across both.
    With W2 current the box read 0 circuits and W2's own 36.54 A; it now
    reads the wall's 5 and 73.08 A, the same as with W1 current or both
    selected. W1 at 208V and W3 at 110V selected together read "-" for
    the circuit count and both amps, never one screen's numbers."""
    pg = page
    wall = dict(columns=8, rows=5, panelWatts=190, powerAmperage=20,
                powerFlowPattern='tl-h', group_id='g1')
    _open(pg, [dict(wall), dict(wall, offset_x=1024),
               {'columns': 4, 'offset_x': 2500, 'powerVoltage': 110, 'powerAmperage': 20}],
          {'groups': [{'id': 'g1', 'name': 'Wall', 'layer_ids': [1, 2]}]})
    lead = pg.evaluate(READOUT_JS, ['W1'])
    assert lead == ['5', '73.08 A', '42.24 A'], lead
    assert pg.evaluate(READOUT_JS, ['W2']) == lead
    assert pg.evaluate(READOUT_JS, ['W1', 'W2']) == lead
    assert pg.evaluate(READOUT_JS, ['W1', 'W3']) == ['-', '-', '-']
    assert pg.evaluate(READOUT_JS, ['W3']) != ['-', '-', '-']


# ── Custom on leaves no phantom load ──────────────────────────────────────

def test_custom_on_takes_the_emptied_multis_off_their_distro(page):
    """W1's multi on SR 9 with a 150' home run. Custom circuits on wipes
    the circuits, and the multi with them: SR used to keep W1's automatic
    load (17.3 A) with nothing drawn. One undo puts it all back."""
    pg = page
    _open(pg, [{'columns': 6, 'powerSocaDistro': {'1': 'd2'}, 'powerSocaNumber': {'1': 9},
                'powerSocaLengths': {'1': '150'}}])
    load = "() => { window.app._circuitTailCache = null; return (window.app.getDistroLoads() || []).filter(d => d.id === 'd2').map(d => +d.amps.toFixed(1)); }"
    assert pg.evaluate(load) == [17.3]
    cb = pg.locator('#power-custom-toggle')
    cb.scroll_into_view_if_needed()
    cb.click()
    _settle(pg)
    assert pg.evaluate(load) == [0.0]
    srv = _wait_server(pg, lambda p: not (_srv_layer('W1', p).get('powerSocaDistro') or {}))
    assert (_srv_layer('W1', srv).get('powerSocaLengths') or {}) == {}
    pg.evaluate("() => window.app.undo()")
    _settle(pg)
    assert pg.evaluate(load) == [17.3]
    assert [(s['distro'], s['number'], s['length']) for s in _socas(pg, 'W1')] == [('d2', 9, '150')]


# ── Menus and words ───────────────────────────────────────────────────────

FACE = {'distros': [
    {'id': 'd1', 'name': 'DISTRO 1', 'ratingA': 200, 'system': '120/208',
     'outputRows': [{'id': 'r1', 'connector': 'true1', 'count': 5, 'coupling': 'll', 'breakerA': 6.25},
                    {'id': 'r2', 'connector': 'soca', 'count': 2, 'coupling': 'll', 'breakerA': 6.25}]},
    {'id': 'd2', 'name': 'DISTRO 2', 'ratingA': 400, 'system': '120/208', 'voltage': 208, 'phase': 3},
    {'id': 'd3', 'name': 'DISTRO 3', 'ratingA': 30, 'system': '120/208',
     'outputRows': [{'id': 'r1', 'connector': 'true1', 'count': 3, 'coupling': 'll', 'breakerA': 6.25}]}]}


def test_menus_offer_only_what_they_can_do(page):
    """W1's circuit 1 on DISTRO 1's TRUE1 direct output, 2-6 split off it
    onto the Socapex 6: no "Merge back into DISTRO 1-1" (it piled five
    circuits onto one connector, then flagged its own result OVER). W2 is
    on no distro: no "Unplug multi" (offered greyed, it did nothing). The
    Add … from… entry for a distro that cannot take the screen names the
    distro once ("DISTRO 3: DISTRO 3 has no multi outputs")."""
    pg = page
    _open(pg, [{'columns': 7, 'powerSocaDistro': {'1': 'd1', '2': 'd1'},
                'powerSocaNumber': {'1': 1, '2': 6}, 'powerSocaSplits': [1]},
               {'columns': 3, 'offset_x': 1200}], FACE)
    out = pg.evaluate("""() => { const app = window.app, l = window.__pu.layer('W1');
        const W2 = window.__pu.layer('W2');
        const m = app._mergeMenuForMulti(l, 2, false);
        const un = app._clearMenuForCircuit({ layerId: W2.id, panel: W2.panels[0] });
        const plugged = app._clearMenuForCircuit({ layerId: l.id, panel: l.panels.find(p => p.col === 2) });
        return { merge: m ? m.label : null, unplug: un ? un.label : null,
                 plugged: plugged ? plugged.label : null,
                 labels: app.screenCircuits(l).map(c => app.getPowerCircuitLabel(l, c.num)) }; }""")
    assert out['labels'][:2] == ['DISTRO 1-1', 'DISTRO 1-6-1'], out
    assert out['merge'] is None and out['unplug'] is None, out
    assert out['plugged'] == 'Unplug multi DISTRO 1-6', out
    pg.evaluate("() => window.canvasRenderer.fitToView()")
    x, y = _cab_point(pg, 'W2', 0, 0)
    pg.mouse.click(x, y, button='right')
    item = pg.locator('.context-menu .menu-option:visible').filter(has_text='from…').first
    item.hover()
    entry = pg.locator('.context-menu .menu-option:visible').filter(has_text='DISTRO 3').last
    entry.wait_for()
    assert entry.inner_text().strip().startswith('DISTRO 3 has no multi outputs'), entry.inner_text()
    pg.keyboard.press('Escape')


def test_names_and_messages_read_plainly(page):
    """Two distros on one pull row read "DISTRO 1, DISTRO 2", never the
    multi's name "DISTRO 1-2"; SR1, SR2 still fold to "SR 1-2". The
    service's OVER says "service" once with the default name."""
    pg = page
    _open(pg, [{'columns': 3, 'powerSocaDistro': {'1': 'd2'}}], dict(FACE, services=[
        {'id': 's1', 'name': 'SERVICE 1', 'ratingA': 5, 'system': '120/208'}]))
    pg.evaluate("""() => { const app = window.app;
        app.project.distros.forEach(d => { d.serviceId = 's1'; }); app.renderHardwareDock(); }""")
    folds = pg.evaluate("""() => [['DISTRO 1', 'DISTRO 2'], ['DISTRO 1', 'DISTRO 2', 'DISTRO 3'], ['SR1', 'SR2']]
        .map(n => window.app._pullCompressNames(n))""")
    assert folds == ['DISTRO 1, DISTRO 2', 'DISTRO 1 … 3', 'SR 1-2'], folds
    warn = pg.evaluate("""() => { const app = window.app; app._dockPowerWarnings = [];
        const s = app.getServices()[0]; app._dockServiceWarnings(s, app.getServiceLoads().find(x => x.id === s.id));
        return app._dockPowerWarnings.map(w => w.text); }""")
    assert warn and warn[0].startswith('SERVICE 1: ') and warn[0].endswith('OVER'), warn
    assert not any('service service' in w.lower() or 'SERVICE 1 service' in w for w in warn), warn


def test_the_pull_sheet_tiles_hold_their_tables(page):
    """A long gear name (a distro's type, "63A 3φ: 3 × Socapex, one per
    phase + 1 TRUE1") wraps in its tile: the tables were wider than their
    tiles (636 px in 558) and the LABEL and NOTES columns and the × were
    cut off."""
    pg = page
    face = {'distros': [dict(FACE['distros'][0], typeName='63A 3φ: 3 × Socapex, one per phase + 1 TRUE1')]
            + FACE['distros'][1:]}
    _open(pg, [{'columns': 7, 'powerSocaDistro': {'1': 'd1', '2': 'd1'},
                'powerSocaNumber': {'1': 1, '2': 6}, 'powerSocaSplits': [1]}], face)
    pg.evaluate("() => { document.getElementById('export-modal').style.display = 'none'; }")
    pg.locator('[data-menu="file"]').click()
    pg.locator('[data-action="pull-sheet"]').click()
    pg.wait_for_function("() => window.app.isPullSheetEditorOpen()")
    pg.wait_for_timeout(300)
    fit = pg.evaluate("""() => Array.from(document.querySelectorAll('#pull-sheet-modal .pull-pos'))
        .map(p => { const t = p.querySelector('table'); return t ? [t.getBoundingClientRect().width, p.clientWidth] : null; })
        .filter(Boolean)""")
    assert fit and all(tw <= cw + 1 for tw, cw in fit), fit
    longest = pg.evaluate("""() => Math.max(...Array.from(document.querySelectorAll('#pull-sheet-modal td.pull-type'))
        .map(td => td.textContent.length))""")
    assert longest > 30, longest
    pg.locator('#pull-sheet-close').click()


# ── A map pill never sits on a run line ──────────────────────────────────

PLACE_JS = """([prefer, run, segs, discs]) => {
    const r = window.canvasRenderer;
    const own = { x: 100, y: 100, r: 20 };
    const all = [own].concat(discs.map(([x, y]) => ({ x, y, r: 20 })));
    const bounds = { left: 0, top: 0, right: 600, bottom: 400 };
    const t = r.placeCableTag("150'", own.x, own.y, own.r, 20, bounds, all, own, [],
                              { prefer, run, line: { x: 100, y: 100 }, segs });
    return { side: t.opts.side, rect: { x: t.rect.x, y: t.rect.y, w: t.rect.w, h: t.rect.h }, clear: t.clear };
}"""


def test_a_tag_beside_its_disc_stands_off_its_run_line(page):
    """Port 2's disc with discs right over and under it (its 2R return and
    the port above): its "150'" hangs beside it, on the side its run
    leaves by - and sat on that run's line and arrow. It now stands just
    above the line, still beside its disc."""
    pg = page
    line = [[100, 100, 500, 100]]
    out = pg.evaluate(PLACE_JS, ['above', 'right', line, [[100, 50], [100, 150]]])
    assert out['side'] == 'right' and out['clear'], out
    r = out['rect']
    assert r['y'] + r['h'] < 100 and r['y'] > 60, out
    assert r['x'] < 100 + 20 + 20, out          # still tight to the disc

