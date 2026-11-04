"""Typed circuit labels do what typed data port labels do when numbers move.

The owner, 2026-11-04: typed power labels "should match how we do data for
now". A typed data port name (portLabelOverridesPrimary, keyed by number)
stays on its NUMBER when the ports renumber (Organized / Max Capacity, the
Port numbers switch, a flow pattern, a redraw cut back, Return to
automatic), with one exception: a redraw that ends with nothing drawn on
its port hands the number back to the walk, and then the names follow the
cabinets they rode when the redraw opened (_repairEmptyOverrides,
_portMovesByCabinet). A port goes where most of its cabinets went; two
landing on one number leave it to the one that already had it, and the
other name goes.

Power had the same hand-back (_dropUnchangedRedraw: nothing drawn on a
taken-over circuit, so it goes back to automatic) but left the labels on
their numbers, so the circuits that closed up in behind it took the wrong
labels. Now the labels follow the cabinets there, by the data rule, in the
gesture's own undo step, server included. On every other renumber both
sides keep a label on its number; those are pinned here too, side by side.

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
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
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
    yield pg
    assert errors == [], errors
    context.close()


# Power: 208 W cabinets on 208 V x 5 A carry four to a circuit, cabled
# top-down, so an 8 x 4 wall is one column a circuit.
# Data: 256 px cabinets on the Armor take ten to a port, cabled top-down,
# so an 8 x 5 wall is two columns a port.
HELPERS_JS = r"""
window.__pl = {
    screen(o) {
        o = Object.assign({
            type: 'screen', visible: true, locked: false, id: 1, name: 'A',
            columns: 8, rows: 4, cabinet_width: 128, cabinet_height: 128,
            offset_x: 0, offset_y: 0, panel_weight: 20, weight_unit: 'kg',
            panelWatts: 208, powerVoltage: 208, powerAmperage: 5,
            processorType: 'novastar-armor', bitDepth: 8, frameRate: 60, lowLatency: false,
            flowPattern: 'tl-v', portMappingMode: 'organized',
            powerFlowPattern: 'tl-v', powerOrganized: true, powerMaximize: false,
            powerLabelTemplate: 'S1-#', powerLabelOverrides: {},
            portLabelOverridesPrimary: {}, portLabelOverridesReturn: {},
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
        await this.j('PUT', '/api/project', { name: 'Labels like data', layers: [this.screen(layer)] });
        app.project = await this.j('GET', '/api/project');
        app.dedupeProjectLayers('labels_like_data');
        app.selectLayer(app.project.layers[0]);
        app.selectedLayerIds = new Set([app.project.layers[0].id]);
        app._circuitTailCache = null;
        app._overrideEditing = null;
        app._overrideHeld = null;
        app._powerHeld = null;
        await app.refreshProcessors();
        app.resetHistory('Initial State');
        app.renderLayers();
        this.toasts = [];
        if (!app.__plToast) {
            const real = app._toast;
            app._toast = function (msg, ...rest) {
                window.__pl.toasts.push(String(msg));
                return real.call(this, msg, ...rest);
            };
            app.__plToast = true;
        }
        return true;
    },
    layer() { return window.app.project.layers[0]; },
    inflight() {
        const s = window.app._inflightLayerPuts;
        return !s || s.size === 0;
    },
    // number -> its cabinets ("row.col", walk order)
    plan(kind) {
        const app = window.app, l = this.layer(), out = {};
        if (kind === 'power') {
            app._circuitTailCache = null;
            app.screenCircuits(l).forEach(c => { out[c.num] = c.panels.map(p => `${p.row}.${p.col}`); });
            return out;
        }
        app._portCabinetKeys(l).forEach((keys, n) => {
            out[n] = [...keys].map(k => k.split(':')[1].replace(',', '.'));
        });
        return out;
    },
    labels(kind) {
        const l = this.layer();
        return JSON.parse(JSON.stringify(
            (kind === 'power' ? l.powerLabelOverrides : l.portLabelOverridesPrimary) || {}));
    },
    setLabels(kind, map) {
        const app = window.app, l = this.layer();
        if (kind === 'power') l.powerLabelOverrides = Object.assign({}, map);
        else l.portLabelOverridesPrimary = Object.assign({}, map);
        app.saveClientSideProperties();
        app.updateLayers([l], true, 'Set Labels');
    },
    // Take run `num` over and cut its path to its first `keep` cabinets,
    // then close the redraw: a redrawn run sitting short.
    redrawShort(kind, num, keep) {
        const a = window.app, l = this.layer();
        const key = kind === 'power' ? 'powerCustomPaths' : 'customPortPaths';
        a.overrideRun(l, kind, num);
        l[key][num] = l[key][num].slice(0, keep);
        a.saveState('Custom Path Edit');
        a.updateLayers([l]);
        a.endOverrideEdit();
    },
    // Open run `num` (already taken over) and clear what is drawn on it.
    reopenAndClear(kind, num) {
        const a = window.app, l = this.layer();
        const key = kind === 'power' ? 'powerCustomPaths' : 'customPortPaths';
        a.beginOverrideEdit(l, kind, num);
        l[key][num] = [];
        a.saveState('Custom Path Edit');
        a.updateLayers([l]);
    },
    action() { return window.app.history[window.app.historyIndex].action; },
};
"""

POWER = {'columns': 8, 'rows': 4}
DATA = {'columns': 8, 'rows': 5, 'cabinet_width': 256, 'cabinet_height': 256}
KEY = {'power': 'powerLabelOverrides', 'data': 'portLabelOverridesPrimary'}


def _settle(pg):
    pg.wait_for_function('() => window.__pl.inflight()')
    pg.wait_for_function("() => !window.app._saveStateTimer")
    pg.wait_for_function('() => window.__pl.inflight()')


def _server_labels(kind):
    import app as app_module
    layer = (copy.deepcopy(app_module.current_project).get('layers') or [{}])[0]
    return layer.get(KEY[kind]) or {}


def _wait_server(pg, kind, want):
    got = settled(pg, lambda: _server_labels(kind), lambda v: v == want, 8000)
    assert got == want, got


def _open(pg, layer):
    pg.evaluate("(l) => window.__pl.open(l)", layer)
    _settle(pg)


def _set_labels(pg, kind, labels):
    pg.evaluate("([k, m]) => window.__pl.setLabels(k, m)", [kind, labels])
    _settle(pg)


def _plan(pg, kind):
    return pg.evaluate("(k) => window.__pl.plan(k)", kind)


def _labels(pg, kind):
    return pg.evaluate("(k) => window.__pl.labels(k)", kind)


def _esc(pg):
    pg.locator('#main-canvas').hover()
    pg.keyboard.press('Escape')
    _settle(pg)


def _short_then_cleared(pg, kind, num, keep, labels):
    """Run `num` redrawn short (so the rest of its cabinets are the next
    number), the labels typed, then `num` reopened and cleared."""
    pg.evaluate("([k, n, keep]) => window.__pl.redrawShort(k, n, keep)", [kind, num, keep])
    _settle(pg)
    _set_labels(pg, kind, labels)
    before = (_plan(pg, kind), _labels(pg, kind))
    pg.evaluate("([k, n]) => window.__pl.reopenAndClear(k, n)", [kind, num])
    _settle(pg)
    return before


# ── The hand-back: the labels follow the cabinets ────────────────────────

def test_data_names_follow_the_cabinets_when_a_cleared_port_is_handed_back(page):
    """The data rule, as it stands. P2 redrawn on the top two cabinets of
    column 2 leaves the rest of that column pair as P3, so P4 and P5 are
    one number up. P2 reopened, cleared, Esc: P2 goes back to automatic,
    the pair is P2 again and the ports after close up. TWO stays (P2 had
    that number); THREE's cabinets landed on P2 too and lost it, so THREE
    goes; FOUR and FIVE follow their cabinets down a number."""
    pg = page
    _open(pg, DATA)
    p0, l0 = _short_then_cleared(pg, 'data', 2, 2,
                                 {'2': 'TWO', '3': 'THREE', '4': 'FOUR', '5': 'FIVE'})
    assert p0['3'][0] == '2.2' and p0['4'][0] == '0.4' and p0['5'][0] == '0.6', p0
    _esc(pg)
    p1 = _plan(pg, 'data')
    assert p1['3'][0] == '0.4' and p1['4'][0] == '0.6' and '5' not in p1, p1
    assert _labels(pg, 'data') == {'2': 'TWO', '3': 'FOUR', '4': 'FIVE'}
    assert pg.evaluate("() => window.__pl.action()") == 'Return Port To Auto'
    _wait_server(pg, 'data', {'2': 'TWO', '3': 'FOUR', '4': 'FIVE'})


def test_power_labels_follow_the_cabinets_when_a_cleared_circuit_is_handed_back(page):
    """The same gesture on power. Circuit 3 redrawn on the top half of
    column 2 leaves its bottom half as 4, so column 3 is 5 and column 7 is
    9. Circuit 3 reopened, cleared, Esc: it goes back to automatic, column
    2 is 3 again and the circuits after close up. THREE stays, FOUR (the
    bottom half, now inside 3) goes, FIVE moves to 4 and NINE to 8, each
    still on its column. One undo puts every label back, server included."""
    pg = page
    _open(pg, POWER)
    p0, l0 = _short_then_cleared(pg, 'power', 3, 2,
                                 {'3': 'THREE', '4': 'FOUR', '5': 'FIVE', '9': 'NINE'})
    assert p0['4'][0] == '2.2' and p0['5'][0] == '0.3' and p0['9'][0] == '0.7', p0
    _esc(pg)
    p1 = _plan(pg, 'power')
    assert pg.evaluate("() => window.__pl.layer().powerCustomOverrides") == []
    assert p1['3'][0] == '0.2' and p1['4'][0] == '0.3' and p1['8'][0] == '0.7', p1
    want = {'3': 'THREE', '4': 'FIVE', '8': 'NINE'}
    assert _labels(pg, 'power') == want
    assert pg.evaluate("() => window.__pl.action()") == 'Return Circuit To Auto'
    _wait_server(pg, 'power', want)
    shown = pg.evaluate("""() => [4, 8].map(n =>
        window.app.getPowerCircuitLabel(window.__pl.layer(), n))""")
    assert shown == ['FIVE', 'NINE'], shown
    said = ' '.join(pg.evaluate("() => window.__pl.toasts.slice()"))
    assert 'nothing was drawn on circuit THREE, so it went back to automatic' in said, said
    # One undo: the redraw is open again and every label is back.
    pg.evaluate("() => window.app.undo()")
    _settle(pg)
    assert _labels(pg, 'power') == l0
    _wait_server(pg, 'power', l0)
    pg.evaluate("() => window.app.redo()")
    _settle(pg)
    assert _labels(pg, 'power') == want
    _wait_server(pg, 'power', want)


def test_power_labels_follow_when_another_circuit_ends_the_cleared_redraw(page):
    """The cleared redraw ended by picking up another circuit instead of
    Esc: the hand-back happens there, and the labels follow the same way."""
    pg = page
    _open(pg, POWER)
    _short_then_cleared(pg, 'power', 3, 2, {'5': 'FIVE', '9': 'NINE'})
    pg.evaluate("() => window.app.overrideRun(window.__pl.layer(), 'power', 7)")
    _settle(pg)
    p1 = _plan(pg, 'power')
    assert 3 not in pg.evaluate("() => window.__pl.layer().powerCustomOverrides")
    head = {cells[0]: n for n, cells in p1.items()}
    labels = _labels(pg, 'power')
    assert labels.get(head['0.3']) == 'FIVE', (p1, labels)
    assert labels.get(head['0.7']) == 'NINE', (p1, labels)
    _wait_server(pg, 'power', labels)
    if pg.evaluate("() => !!window.app._overrideEditing"):
        _esc(pg)


def test_a_screen_locked_mid_redraw_keeps_its_labels(page):
    """Locked screens stay unchanged: locked while the cleared redraw is
    open, Esc hands nothing back and no label moves."""
    pg = page
    _open(pg, POWER)
    _, l0 = _short_then_cleared(pg, 'power', 3, 2, {'5': 'FIVE', '9': 'NINE'})
    pg.evaluate("() => { window.__pl.layer().locked = true; }")
    _esc(pg)
    assert _labels(pg, 'power') == l0
    assert pg.evaluate("() => window.__pl.layer().powerCustomOverrides") == [3]
    pg.evaluate("() => { const l = window.__pl.layer(); l.locked = false; window.app.updateLayers([l]); }")
    _settle(pg)


# ── Every other renumber: the label stays on its number, on both sides ───

def test_a_redraw_cut_back_keeps_each_label_on_its_number_like_data(page):
    """A redraw that ends with its run cut short (the cabinets it let go
    slide into the walk and the runs after move up a number) moves no typed
    label on either side."""
    pg = page
    for kind, layer, num, labels in (
            ('data', DATA, 2, {'2': 'TWO', '3': 'THREE', '4': 'FOUR'}),
            ('power', POWER, 3, {'3': 'THREE', '4': 'FOUR', '8': 'EIGHT'})):
        _open(pg, layer)
        _set_labels(pg, kind, labels)
        p0 = _plan(pg, kind)
        pg.evaluate("([k, n]) => window.__pl.redrawShort(k, n, 2)", [kind, num])
        _settle(pg)
        assert _plan(pg, kind) != p0, kind
        assert _labels(pg, kind) == labels, kind
        _wait_server(pg, kind, labels)


def test_return_to_automatic_keeps_each_label_on_its_number_like_data(page):
    pg = page
    for kind, layer, num, labels in (
            ('data', DATA, 2, {'2': 'TWO', '3': 'THREE', '5': 'FIVE'}),
            ('power', POWER, 3, {'3': 'THREE', '4': 'FOUR', '9': 'NINE'})):
        _open(pg, layer)
        pg.evaluate("([k, n]) => window.__pl.redrawShort(k, n, 2)", [kind, num])
        _settle(pg)
        _set_labels(pg, kind, labels)
        p0 = _plan(pg, kind)
        pg.evaluate("([k, n]) => window.app.returnRunToAuto(window.__pl.layer(), k, n)",
                    [kind, num])
        _settle(pg)
        assert _plan(pg, kind) != p0, kind
        assert _labels(pg, kind) == labels, kind
        _wait_server(pg, kind, labels)


def test_organized_to_max_capacity_keeps_each_label_on_its_number_like_data(page):
    """Max Capacity packs fewer runs; the labels stay on their numbers on
    both sides, the last one on a number no run has now."""
    pg = page
    cases = (
        # Brompton takes eight 256 px cabinets a port: Organized two
        # columns (six) a port, Max eight.
        ('data', {'columns': 5, 'rows': 3, 'cabinet_width': 256, 'cabinet_height': 256,
                  'processorType': 'brompton'},
         "() => document.getElementById('mapping-max-capacity').click()"),
        # 208 W on 208 V x 6.25 A: five cabinets a circuit. Organized one
        # column (four) a circuit, Max five.
        ('power', {'columns': 6, 'rows': 4, 'powerAmperage': 6.25},
         "() => { const el = document.getElementById('power-maximize');"
         " el.checked = true; el.dispatchEvent(new Event('change', { bubbles: true })); }"),
    )
    for kind, layer, click in cases:
        _open(pg, layer)
        p0 = _plan(pg, kind)
        labels = {str(n): f'L{n}' for n in p0}
        _set_labels(pg, kind, labels)
        pg.evaluate(click)
        _settle(pg)
        p1 = _plan(pg, kind)
        assert len(p1) < len(p0), (kind, p0, p1)
        assert _labels(pg, kind) == labels, kind
        _wait_server(pg, kind, labels)
