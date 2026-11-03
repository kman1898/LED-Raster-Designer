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
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
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
# screen's `columns` IS its circuit count. PD is a distro FACE - five TRUE1
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
                      { id: 'r1', connector: 'true1', count: 5, coupling: 'll', breakerA: 20 },
                      { id: 'r2', connector: 'soca', count: 2, coupling: 'll', breakerA: 20 }] },
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
    The server keeps the tails; the label the field predicts is the one
    drawn; undo takes the newcomer back off, a cabinet a step."""
    pg = page
    _open(pg, [{'columns': 8, 'powerFlowPattern': 'custom', 'powerCustomIndex': 2,
                'powerCustomPaths': {str(i + 1): _col(i) for i in range(4)},
                'powerSocaDistro': {'1': 'd2'}, 'powerSocaNumber': {'1': 9}}])
    _clear_circuit(pg)
    assert _labels(pg, 'W1') == [[1, 'SR9-1'], [3, 'SR9-3'], [4, 'SR9-4']]
    _type_active(pg, 4)  # the place after the last circuit: run 5
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


# ── An L6-20 breakout plugs into a line-to-line multi ─────────────────────

def _cab_point(pg, name, row, col):
    return pg.evaluate("""([n, r, c]) => {
        const R = window.canvasRenderer, L = window.__pu.layer(n);
        const cv = R.canvas.getBoundingClientRect();
        return [cv.x + R.panX + (L.offset_x + (c + 0.5) * L.cabinet_width) * R.zoom,
                cv.y + R.panY + (L.offset_y + (r + 0.5) * L.cabinet_height) * R.zoom];
    }""", [name, row, col])


def _menu_add_from(pg, name, distro_label):
    """Right-click a cabinet of `name`, Add … from…, pick `distro_label`."""
    x, y = _cab_point(pg, name, 0, 0)
    pg.mouse.click(x, y, button='right')
    item = pg.locator('.context-menu .menu-option:visible').filter(has_text='from…').first
    item.wait_for()
    label = item.inner_text().strip()
    item.hover()
    pick = pg.locator('.context-menu .menu-option:visible').filter(has_text=distro_label).last
    pick.wait_for()
    pick.click()
    _settle(pg)
    return label


def test_an_l6_20_screen_plugs_into_a_line_to_line_multi(page):
    """A 208V screen on Multi → L6-20: its breakout is a six-circuit multi
    box whose outlets are line-to-line, so the Socapex 208V rows of a
    face distro and a Multi 208 feed it like TRUE1. Every drop used to
    be refused, and the screen had no Add … from… item at all."""
    pg = page
    _open(pg, [{'powerBreakoutType': 'soca-l620', 'powerPanelInput': 'true1'},
               {'powerBreakoutType': 'soca-l620', 'powerPanelInput': 'powercon'}])
    pg.evaluate("() => window.canvasRenderer.fitToView()")
    gates = pg.evaluate("""() => {
        const app = window.app;
        return ['W1', 'W2'].map(n => { const l = window.__pu.layer(n);
            return app._distroDropRefusal({ distroId: 'd1' }, l, app.getSocaPlan(l)[0]); });
    }""")
    assert gates == [None, None], gates
    assert _menu_add_from(pg, 'W1', 'PD').startswith('Add ')
    assert _menu_add_from(pg, 'W2', 'SR') == 'Add Multi 208 from…'
    got = {n: [(s['distro'], s['circuits']) for s in _socas(pg, n)] for n in ('W1', 'W2')}
    assert got == {'W1': [('d1', [1, 2, 3, 4, 5])], 'W2': [('d2', [1, 2, 3, 4, 5])]}, got
    srv = _wait_server(pg, lambda p: (_srv_layer('W2', p).get('powerSocaDistro') or {}) == {'1': 'd2'}
                       and (_srv_layer('W1', p).get('powerSocaDistro') or {}) == {'1': 'd1'})
    assert _srv_layer('W1', srv)['powerBreakoutType'] == 'soca-l620'
    # the pull list carries the L6-20 breakout box and its cables
    rows = pg.evaluate("() => JSON.stringify(window.app.buildPullList())")
    assert 'L6-20 Breakout' in rows and 'L6-20 → TRUE1 cable' in rows \
        and 'L6-20 → powerCON cable' in rows


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
