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
