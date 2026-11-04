"""Power fixes from the 1.6.0-beta.4 hand-test pass.

- Unplug multi on the map takes the whole multi: after an Unplug circuit
  has left it in parts on one box (1-2 and 4-5 with 3 taken off), the
  right-click on a circuit unplugged only the clicked part, and the typed
  home run went with it while 4-5 stayed plugged in.
- A home run stays with the circuits still on the box: the part that
  carried it leaving the box hands it to the part that stays.
- Clear Circuit on a custom screen takes that circuit off its multi and
  leaves every other circuit where it was: the next circuit, unplugged,
  used to slide onto the freed slot (DISTRO 1-2-1 by itself).
- Grouping screens on different breakers asks, like voltage does, and
  Power Settings reads "-" for a figure the selected screens disagree on.
- A distro powered thru another is not counted in the service's ratings.
- A box is named the way its multi is ("SR1", "DISTRO 1-1"), a direct
  output's menu names its connector, the info line counts boxes, and the
  custom run readout says "over" for a run past its limit.

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
            name: 'Unplug rulings', cableUnit: 'ft',
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
        app.dedupeProjectLayers('unplug_rulings');
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


# ── Unplug multi on the map ───────────────────────────────────────────────

def test_unplug_multi_on_the_map_takes_every_part_of_its_box(page):
    """W1's five circuits on SR 1 with a 75' home run; Unplug circuit 3
    leaves 1-2 and 4-5 on the box, the 75' on 1-2. The map's right-click
    on circuit 1 says Unplug multi SR1 and takes BOTH parts off - before,
    4-5 stayed plugged in and the 75' went - in the browser and on the
    server. One undo puts it all back."""
    pg = page
    _open(pg, [{'powerSocaDistro': {'1': 'd2'}, 'powerSocaLengths': {'1': '75'}}])
    _unplug_circuit(pg, 'W1', 3)
    parts = [s for s in _socas(pg, 'W1') if s['distro']]
    assert [s['circuits'] for s in parts] == [[1, 2], [4, 5]], parts
    assert {s['number'] for s in parts} == {1}, parts
    item = pg.evaluate("""() => {
        const app = window.app, l = window.__pu.layer('W1');
        const panel = l.panels.find(p => p.row === 0 && p.col === 0);
        const it = app._clearMenuForCircuit({ layerId: l.id, panel });
        if (it && it.run) it.run();
        return it ? it.label : null;
    }""")
    assert item == 'Unplug multi SR1', item
    _settle(pg)
    assert all(s['distro'] is None for s in _socas(pg, 'W1')), _socas(pg, 'W1')
    srv = _wait_server(pg, lambda p: not (_srv_layer('W1', p).get('powerSocaDistro') or {}))
    assert (_srv_layer('W1', srv).get('powerSocaDistro') or {}) == {}
    assert (_srv_layer('W1', srv).get('powerSocaLengths') or {}) == {}
    pg.evaluate("() => window.app.undo()")
    _settle(pg)
    back = [s for s in _socas(pg, 'W1') if s['distro']]
    assert [s['circuits'] for s in back] == [[1, 2], [4, 5]], back
    assert '75' in [s['length'] for s in back], back


def test_a_home_run_stays_with_the_parts_left_on_the_box(page):
    """Unplug circuit 3, then 1, then 2: the part carrying the 75' leaves
    the box, and 4-5 - still on it - keep the 75' (it used to be
    forgotten with the last circuit of the first part)."""
    pg = page
    _open(pg, [{'powerSocaDistro': {'1': 'd2'}, 'powerSocaLengths': {'1': '75'}}])
    for c in (3, 1, 2):
        _unplug_circuit(pg, 'W1', c)
    fed = [s for s in _socas(pg, 'W1') if s['distro']]
    assert [(s['circuits'], s['length']) for s in fed] == [([4, 5], '75')], fed
    srv = _wait_server(pg, lambda p: '75' in (_srv_layer('W1', p).get('powerSocaLengths') or {}).values()
                       and len(_srv_layer('W1', p).get('powerSocaDistro') or {}) == 1)
    assert list((_srv_layer('W1', srv).get('powerSocaLengths') or {}).values()) == ['75']


def test_a_direct_output_menu_names_its_connector(page):
    """A circuit on PD's TRUE1 direct output: the map's right-click says
    Unplug TRUE1 PD1, never Unplug multi; the info line counts the box the
    multi is on, not the direct output nor the multi's parts."""
    pg = page
    _open(pg, [{'columns': 7, 'powerSocaDistro': {'1': 'd1', '2': 'd1'},
                'powerSocaNumber': {'1': 6, '2': 1}}])
    out = pg.evaluate("""() => {
        const app = window.app, l = window.__pu.layer('W1');
        const at = (col) => app._clearMenuForCircuit({ layerId: l.id,
            panel: l.panels.find(p => p.row === 0 && p.col === col) }).label;
        return { direct: at(6), multi: at(0), info: app.infoMultiCount(l),
                 segs: app.socaCountFor(l, app.screenCircuits(l).length) };
    }""")
    assert out['direct'] == 'Unplug TRUE1 PD1', out
    assert out['multi'] == 'Unplug multi PD6', out
    assert out['segs'] == 2 and out['info'] == 1, out
    # Unplug circuit 3 of the multi on PD 6: two parts, one box, one multi.
    _unplug_circuit(pg, 'W1', 3)
    info = pg.evaluate("() => window.app.infoMultiCount(window.__pu.layer('W1'))")
    # the two parts on PD 6, and circuit 3 on no box yet
    assert info == 2, info


# ── Clear Circuit on a custom screen ──────────────────────────────────────

def test_clear_circuit_on_a_custom_screen_keeps_the_other_feeds(page):
    """Custom circuits 1, 2, 3 (one column each): 1 on SR 1, 2 on SR 2, 3
    unplugged. Clear Circuit with 2 active: circuit 2 goes, 1 stays on
    SR 1, and 3 stays unplugged - it used to slide onto SR 2 and read
    SR2-1 by itself. One undo puts circuit 2 back on SR 2."""
    pg = page
    col = lambda c: [{'row': r, 'col': c} for r in range(5)]  # noqa: E731
    _open(pg, [{'columns': 3, 'powerFlowPattern': 'custom', 'powerCustomIndex': 2,
                'powerCustomPaths': {'1': col(0), '2': col(1), '3': col(2)},
                'powerSocaSplits': [1, 2],
                'powerSocaDistro': {'1': 'd2', '2': 'd2'}, 'powerSocaNumber': {'1': 1, '2': 2}}])
    before = _socas(pg, 'W1')
    assert [(s['circuits'], s['distro'], s['number']) for s in before] == [
        ([1], 'd2', 1), ([2], 'd2', 2), ([3], None, None)], before
    btn = pg.locator('#power-custom-clear-circuit')
    btn.scroll_into_view_if_needed()
    btn.click()
    _settle(pg)
    after = _socas(pg, 'W1')
    assert [(s['circuits'], s['distro'], s['number']) for s in after] == [
        ([1], 'd2', 1), ([3], None, None)], after
    labels = pg.evaluate("() => [1, 3].map(n => window.app.getPowerCircuitLabel(window.__pu.layer('W1'), n))")
    assert labels[0] == 'SR1-1' and not labels[1].startswith('SR'), labels
    srv = _wait_server(pg, lambda p: '2' not in (_srv_layer('W1', p).get('powerCustomPaths') or {}))
    assert _srv_layer('W1', srv)['powerSocaDistro'] == {'1': 'd2'}, _srv_layer('W1', srv)['powerSocaDistro']
    pg.evaluate("() => window.app.undo()")
    _settle(pg)
    assert [(s['circuits'], s['distro'], s['number']) for s in _socas(pg, 'W1')] == [
        ([1], 'd2', 1), ([2], 'd2', 2), ([3], None, None)]


# ── Grouping on different breakers, mixed figures ─────────────────────────

def test_grouping_screens_on_different_breakers_asks(page):
    """A 20 A screen and a 15 A one disagree on a setting a group shares:
    the check lists the amperage and the dialog offers both, and the
    answer lands on every member. Absent reads as the 15 A a new screen
    has. The server's copy of the check agrees."""
    pg = page
    _open(pg, [{'powerAmperage': 20}, {'powerAmperage': 15}])
    out = pg.evaluate("""async () => {
        const app = window.app, a = window.__pu.layer('W1'), b = window.__pu.layer('W2');
        const check = app.validateGroupSettings([a, b]);
        const absent = Object.assign({}, a);
        delete absent.powerAmperage;
        const agreeAbsent = app.validateGroupSettings([absent, b]).ok;
        const pending = app._resolveGroupSettings([a, b], 'create');
        const rows = [...document.querySelectorAll('#group-settings-conflicts .group-settings-row')]
            .map(r => r.dataset.field + ':' + [...r.querySelectorAll('option')].map(o => o.textContent).join('/'));
        app._confirmGroupSettingsDialog();
        const chosen = await pending;
        app._writeGroupSettings([a, b], chosen);
        return { conflicts: check.conflicts, rows, chosen,
                 amps: [a.powerAmperage, b.powerAmperage], agreeAbsent };
    }""")
    assert out['conflicts'] == {'powerAmperage': [20, 15]}, out
    assert out['rows'] == ['powerAmperage:20A/15A'], out
    assert out['chosen'] == {'powerAmperage': 20} and out['amps'] == [20, 20], out
    assert out['agreeAbsent'] is True, out
    import app as app_module
    assert app_module.validate_group_settings([{'powerAmperage': 20}, {'powerAmperage': '15'}]) == {
        'ok': False, 'conflicts': {'powerAmperage': [20, 15]}}
    assert app_module.validate_group_settings([{'powerAmperage': 15}, {}])['ok'] is True


def test_power_settings_read_a_dash_for_figures_the_selection_disagrees_on(page):
    """W1 at 20 A and W2 at 15 A picked together in the Screens list: the
    Amperage select reads "-", the per-circuit figures read "-", and the
    voltage they share reads 208V. Picking 20A writes both."""
    pg = page
    _open(pg, [{'powerAmperage': 20}, {'powerAmperage': 15}])
    pg.evaluate("() => window.app.renderLayers()")
    rows = pg.locator('#layers-list .layer-item')
    rows.nth(0).click()
    rows.nth(1).click(modifiers=['Control'])
    pg.wait_for_function("() => window.app.getSelectedLayers().length === 2")
    read = """() => {
        const s = (id) => { const el = document.getElementById(id); return el.options[el.selectedIndex].text; };
        return { amps: s('power-amperage-select'), volts: s('power-voltage-select'),
                 watts: document.getElementById('power-watts-per-circuit').textContent,
                 panels: document.getElementById('power-panels-per-circuit').textContent,
                 usable: document.getElementById('power-amperage-usable').textContent };
    }"""
    out = pg.evaluate(read)
    assert out == {'amps': '-', 'volts': '208V', 'watts': '-', 'panels': '-', 'usable': ''}, out
    pg.select_option('#power-amperage-select', '20')
    _settle(pg)
    amps = pg.evaluate("() => window.app.getSelectedLayers().map(l => l.powerAmperage)")
    assert amps == [20, 20], amps
    out = pg.evaluate(read)
    assert out['amps'] == '20A' and out['watts'] != '-', out
    assert pg.evaluate("() => !document.querySelector('#power-amperage-select option[data-mixed]')")


# ── Names and readouts ────────────────────────────────────────────────────

def test_a_box_is_named_the_way_its_multi_is(page):
    """The tray names SR's boxes SR1, SR2 and DISTRO 1's DISTRO 1-1, the
    way the multis on them read - never "SR 1" or "DISTRO 1 1"."""
    pg = page
    _open(pg, [{'powerSocaDistro': {'1': 'd2'}}])
    out = pg.evaluate("""() => {
        const app = window.app;
        const sr = app.getDistros().find(d => d.id === 'd2');
        app.renderHardwareDock();
        const titles = [...document.querySelectorAll('[data-hwdock-payload]')]
            .map(e => JSON.parse(e.getAttribute('data-hwdock-payload')))
            .filter(p => p.distroId === 'd2' && (p.type === 'slot' || p.type === 'tail'))
            .map(p => p.title);
        return { titles, numbered: app.distroBoxName({ id: 'x', name: 'DISTRO 1' }, 1),
                 sr: app.distroBoxName(sr, 2) };
    }""")
    assert 'SR1' in out['titles'] and 'SR1 circuit 1' in out['titles'], out
    assert not any(t.startswith('SR 1') for t in out['titles']), out
    assert out['numbered'] == 'DISTRO 1-1' and out['sr'] == 'SR2', out


def test_a_run_past_its_limit_reads_over_not_full(page):
    """The custom run readout beside Fit: 14 on an 11-cabinet circuit says
    over, in its own colour; a run at its limit still says full."""
    pg = page
    out = pg.evaluate("""() => {
        const r = window.canvasRenderer;
        r._drawActiveBadge('Circuit 1', 14, 0, '#0f0',
            { known: true, full: true, over: true, used: 14, count: 11, text: '14/11' }, 'circuit');
        const over = { pill: r._lastActiveBadge.pill,
                       cls: document.getElementById('custom-run-readout').className };
        r._drawActiveBadge('Circuit 1', 11, 0, '#0f0',
            { known: true, full: true, over: false, used: 11, count: 11, text: '11/11' }, 'circuit');
        const full = { pill: r._lastActiveBadge.pill,
                       cls: document.getElementById('custom-run-readout').className };
        r._syncCustomRunReadout(null);
        return { over, full };
    }""")
    assert out['over']['pill'] == '14/11 on circuit · over', out
    assert 'cr-over' in out['over']['cls'] and 'cr-full' not in out['over']['cls'], out
    assert out['full']['pill'] == '11/11 on circuit · full', out
    assert 'cr-full' in out['full']['cls'] and 'cr-over' not in out['full']['cls'], out


def test_power_selects_show_their_whole_text(page):
    """Custom in the Voltage and Amperage selects, every Breakout option:
    the text fits its select at the default window size (the selects read
    "Custor" and "Multi → Edison (1" before)."""
    pg = page
    _open(pg, [{}])
    out = pg.evaluate("""() => {
        const c = document.createElement('canvas').getContext('2d');
        const out = [];
        ['power-voltage-select', 'power-amperage-select', 'power-breakout-type'].forEach(id => {
            const s = document.getElementById(id);
            const cs = getComputedStyle(s);
            c.font = `${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
            const room = s.getBoundingClientRect().width
                - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
            [...s.options].forEach(o => {
                const need = c.measureText(o.text).width;
                if (need > room) out.push([id, o.text, Math.round(need), Math.round(room)]);
            });
        });
        return out;
    }""")
    assert out == [], out
