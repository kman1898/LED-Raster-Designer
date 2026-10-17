"""Multi numbers do not shift (owner's ruling, 2026-10-16).

"They should not shift unless being balanced. If they are already
numbered, then they will definitely not be shifting unless the numbers are
cleared, phase balance or reset." And for a screen that leaves a distro:
"Leave the gap" - S1, S2, S4 stay, and the next multi to land on the
distro takes the lowest free number (S3).

An auto multi's number (the SL1, SL2 a distro deals out, one number per
multi box) used to be dealt fresh on every rebuild, per distro in layer
order, so a screen joining a shared distro, leaving it, or moving in the
layer list renumbered the multis on screens already cabled. Now a number,
once dealt, is held: the distro record carries `multiNumbers`
({'<layerId>:<socaIndex>': number}), written only where the plain
layer-order deal would no longer reproduce what the show prints - an
untouched show opens, prints and saves exactly as before. The Balance
dialog's reset is the one gesture that deals them again.

Every test checks the browser AND the server's project, waits on real
conditions (never a fixed sleep for state), and leaves the shared server
project as it found it (conftest.server_project_guard).
"""

import copy
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")

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
    pg.wait_for_function(
        '() => window.app && Array.isArray(window.app.history) && window.app.history.length > 0',
        timeout=60000)
    pg.evaluate(HELPERS_JS)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_function("() => window.canvasRenderer && window.canvasRenderer.viewMode === 'power'")
    yield pg
    assert errors == [], errors
    context.close()


# 110V x 5A / 100W = five cabinets a circuit, tl-v organized, five rows: a
# screen's `columns` IS its circuit count, so a 3-wide screen is one
# 3-circuit multi and a 7-wide one is two multis (6 + 1).
HELPERS_JS = r"""
window.__sm = {
    screen(o) {
        o = Object.assign({
            type: 'screen', visible: true, locked: false,
            columns: 3, rows: 5, cabinet_width: 128, cabinet_height: 128,
            offset_x: 0, offset_y: 0, panel_weight: 20, weight_unit: 'kg',
            panelWatts: 100, powerVoltage: 110, powerAmperage: 5,
            processorType: 'brompton', bitDepth: 8, frameRate: 60, lowLatency: false,
            flowPattern: 'tl-h', portMappingMode: 'organized',
            powerFlowPattern: 'tl-v', powerOrganized: true, powerMaximize: false,
            group_id: null, powerSocaDistro: {}, powerSocaNumber: {},
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
    // Project layer order IS the numbering order (bottom up in the list):
    // D first, unfed, so the day it joins the distro it lands AHEAD of
    // every screen already numbered - the shape that used to renumber
    // them all.
    project(opts) {
        opts = opts || {};
        const s = (id, name, x, extra) => this.screen(Object.assign(
            { id, name, offset_x: x }, extra || {}));
        const fed = { powerSocaDistro: { 1: 'd1' } };
        return {
            name: 'Sticky multis',
            distros: [Object.assign({ id: 'd1', name: 'SL', ratingA: 400,
                                      system: '120/208', voltage: 208, phase: 3 },
                                    opts.distro || {})].concat(opts.more || []),
            layers: [
                s(1, 'D', 0, opts.D),
                s(2, 'A', 600, Object.assign({}, fed, opts.A || {})),
                s(3, 'B', 1200, Object.assign({}, fed, opts.B || {})),
                s(4, 'C', 1800, Object.assign({}, fed, opts.C || {})),
            ],
        };
    },
    async j(method, url, body) {
        const r = await fetch(url, { method,
            headers: { 'Content-Type': 'application/json' },
            body: body === undefined ? undefined : JSON.stringify(body) });
        return r.json();
    },
    // The open path's own steps: the server takes the project, the client
    // adopts the server's copy, history starts over.
    async open(project) {
        const app = window.app;
        await this.j('PUT', '/api/project', project);
        app.project = await this.j('GET', '/api/project');
        app.dedupeProjectLayers('sticky_multis');
        app.selectLayer(app.project.layers[0]);
        app.resetHistory('Initial State');
        app.renderLayers();
        return true;
    },
    layer(name) {
        return window.app.project.layers.find(l => l.name === name);
    },
    select(name) {
        const app = window.app;
        const l = this.layer(name);
        app.selectLayer(l);
        app.selectedLayerIds = new Set([l.id]);
        return l.id;
    },
    // name -> the multi names its plan prints, null for a multi on no
    // distro - fresh, never a cached frame.
    names() {
        const app = window.app;
        app._circuitTailCache = null;
        const out = {};
        for (const l of app.project.layers) {
            if ((l.type || 'screen') !== 'screen') continue;
            out[l.name] = app.getSocaPlan(l).map(s => s.distroId ? s.name : null);
        }
        return out;
    },
    labels(name) {
        const app = window.app;
        app._circuitTailCache = null;
        const l = this.layer(name);
        return app.getSocaPlan(l).flatMap(s => s.legs.map(g => g.label));
    },
    inflight() {
        const s = window.app._inflightLayerPuts;
        return !s || s.size === 0;
    },
    // Every project write the page sends from here on: [method, url, keys].
    spy() {
        if (!window.__smFetch) {
            window.__smFetch = window.fetch;
            window.fetch = (url, opts) => {
                const m = ((opts && opts.method) || 'GET').toUpperCase();
                if (m !== 'GET' && window.__smLog) {
                    let keys = null;
                    try { keys = Object.keys(JSON.parse(opts.body)); } catch (e) {}
                    window.__smLog.push([m, String(url), keys]);
                }
                return window.__smFetch(url, opts);
            };
        }
        window.__smLog = [];
        return true;
    },
};
"""


def _server():
    import app as app_module
    return app_module.current_project


def _server_store(distro_id='d1'):
    d = next((d for d in (_server().get('distros') or []) if d.get('id') == distro_id), None)
    return None if d is None else d.get('multiNumbers')


def _server_layer(name):
    return next((l for l in (_server().get('layers') or []) if l.get('name') == name), None)


def _wait_server(pg, ok, timeout_ms=8000):
    """Poll the in-process server project until ok(project) holds; return it."""
    return settled(pg, lambda: copy.deepcopy(_server()), ok, timeout_ms)


def _open(pg, opts_js='{}'):
    pg.evaluate("(o) => window.__sm.open(window.__sm.project(o))", json.loads(opts_js))
    pg.wait_for_function('() => window.__sm.inflight()')


def _names(pg):
    return pg.evaluate('() => window.__sm.names()')


def _ids(pg):
    return pg.evaluate("() => Object.fromEntries(window.app.project.layers.map(l => [l.name, l.id]))")


def _assign(pg, name, soca=1, distro='d1'):
    pg.evaluate("([n, s, d]) => window.app.setSocaDistro(window.__sm.layer(n), s, d)",
                [name, soca, distro])
    pg.wait_for_function('() => window.__sm.inflight()')


BEFORE = {'D': [None], 'A': ['SL1'], 'B': ['SL2'], 'C': ['SL3']}


def test_opening_a_show_holds_nothing_and_prints_what_it_always_printed(page):
    """The first numbering a show sees is its own derived numbering, and
    opening writes nothing: no distro push, no store, and the server's
    project is byte for byte what the PUT left there."""
    pg = page
    proj = pg.evaluate("(o) => window.__sm.project(o)", {})
    pg.evaluate("""async (p) => {
        await window.__sm.j('PUT', '/api/project', p);
        window.__smPut = await (await fetch('/api/project')).text();
        window.__sm.spy();
        const app = window.app;
        app.project = JSON.parse(window.__smPut);
        app.dedupeProjectLayers('sticky_multis');
        app.selectLayer(app.project.layers[0]);
        app.resetHistory('Initial State');
        app.renderLayers();
    }""", proj)
    pg.wait_for_function('() => window.__sm.inflight()')
    assert _names(pg) == BEFORE
    assert pg.evaluate("() => window.app.project.distros[0].multiNumbers") is None
    writes = pg.evaluate("() => window.__smLog.filter(w => (w[2] || []).includes('distros'))")
    assert writes == []
    assert pg.evaluate("async () => (await (await fetch('/api/project')).text()) === window.__smPut")
    assert 'multiNumbers' not in _server()['distros'][0]
    # an edit that renumbers nothing writes nothing either
    pg.evaluate("() => { const l = window.__sm.layer('A'); l.name = 'A'; window.app.updateLayers([l], true, 'Rename'); }")
    assert pg.evaluate("() => window.app.project.distros[0].multiNumbers") is None


def test_a_screen_joining_a_shared_distro_does_not_renumber_the_others(page):
    """D sits first in layer order. Joining SL used to deal it SL1 and push
    A, B and C on to SL2..SL4 - a wall already cabled renumbered. Now the
    three keep SL1..SL3 and D takes the lowest free number, SL4; the server
    distro carries the numbers the plain deal would not reproduce."""
    pg = page
    _open(pg)
    ids = _ids(pg)
    _assign(pg, 'D')
    assert _names(pg) == {'D': ['SL4'], 'A': ['SL1'], 'B': ['SL2'], 'C': ['SL3']}
    want = {f"{ids['D']}:1": 4, f"{ids['A']}:1": 1, f"{ids['B']}:1": 2, f"{ids['C']}:1": 3}
    proj = _wait_server(pg, lambda p: (p['distros'][0].get('multiNumbers') or {}) == want)
    assert proj['distros'][0].get('multiNumbers') == want
    # the client holds the same store the server does
    assert pg.evaluate("() => window.app.project.distros[0].multiNumbers") == want


def test_a_screen_leaving_leaves_its_gap_and_the_next_screen_fills_it(page):
    """B is deleted: A and C stay SL1 and SL3 - the gap stays. D then joins
    and takes SL2, the lowest number free, not SL4."""
    pg = page
    _open(pg)
    ids = _ids(pg)
    pg.evaluate("() => { window.__sm.select('B'); window.app.deleteCurrentLayer(); }")
    pg.wait_for_function("() => !window.app.deletionInProgress && !window.__sm.layer('B')")
    pg.wait_for_function('() => window.__sm.inflight()')
    assert _names(pg) == {'D': [None], 'A': ['SL1'], 'C': ['SL3']}
    _wait_server(pg, lambda p: (p['distros'][0].get('multiNumbers') or {}).get(f"{ids['C']}:1") == 3
                 and _server_layer('B') is None)
    assert _server_layer('B') is None
    assert _server_store().get(f"{ids['C']}:1") == 3
    _assign(pg, 'D')
    assert _names(pg) == {'D': ['SL2'], 'A': ['SL1'], 'C': ['SL3']}
    proj = _wait_server(pg, lambda p: (p['distros'][0].get('multiNumbers') or {}).get(f"{ids['D']}:1") == 2)
    store = proj['distros'][0]['multiNumbers']
    assert store[f"{ids['D']}:1"] == 2 and store[f"{ids['C']}:1"] == 3
    # nothing stored for the screen that is gone
    assert not [k for k in store if k.startswith(f"{ids['B']}:")]


def test_unassigning_a_multi_leaves_a_gap_too(page):
    """Taking A off the distro (the drag back to the tray) is a leave: B and
    C stay SL2 and SL3, and A coming back takes SL1 - the lowest free."""
    pg = page
    _open(pg)
    _assign(pg, 'A', distro=None)
    assert _names(pg) == {'D': [None], 'A': [None], 'B': ['SL2'], 'C': ['SL3']}
    _assign(pg, 'D')
    assert _names(pg) == {'D': ['SL1'], 'A': [None], 'B': ['SL2'], 'C': ['SL3']}
    _assign(pg, 'A')
    assert _names(pg) == {'D': ['SL1'], 'A': ['SL4'], 'B': ['SL2'], 'C': ['SL3']}


def test_reordering_screens_does_not_renumber(page):
    """The layer list turned upside down: every multi keeps its number, and
    the server holds both the new order and the numbers."""
    pg = page
    _open(pg)
    _assign(pg, 'D')
    before = _names(pg)
    pg.evaluate("""() => {
        const app = window.app;
        const display = app.project.layers.map(l => l.id);   // reversed list
        app.applyDisplayOrder(display, 'Reorder Layers');
    }""")
    order = pg.evaluate("() => window.app.project.layers.map(l => l.name)")
    assert order == ['C', 'B', 'A', 'D']
    assert _names(pg) == before == {'D': ['SL4'], 'A': ['SL1'], 'B': ['SL2'], 'C': ['SL3']}
    proj = _wait_server(pg, lambda p: [l['name'] for l in p['layers']] == ['C', 'B', 'A', 'D'])
    assert [l['name'] for l in proj['layers']] == ['C', 'B', 'A', 'D']
    store = proj['distros'][0]['multiNumbers']
    ids = _ids(pg)
    assert {n: store[f'{ids[n]}:1'] for n in 'ABCD'} == {'A': 1, 'B': 2, 'C': 3, 'D': 4}


def test_reset_renumbers_in_screen_order_and_clears_the_store(page):
    """The Balance dialog's reset is the one gesture that moves numbers: with
    the gap B left, reset deals SL again in screen order - C closes up to
    SL2 - and the distro's store is cleared, server side too."""
    pg = page
    _open(pg)
    pg.evaluate("() => { window.__sm.select('B'); window.app.deleteCurrentLayer(); }")
    pg.wait_for_function("() => !window.app.deletionInProgress && !window.__sm.layer('B')")
    pg.wait_for_function('() => window.__sm.inflight()')
    assert _names(pg)['C'] == ['SL3']
    _wait_server(pg, lambda p: bool(p['distros'][0].get('multiNumbers')))
    pg.evaluate("() => window.app.clearPhaseBalance('d1')")
    pg.wait_for_function('() => window.__sm.inflight()')
    assert _names(pg) == {'D': [None], 'A': ['SL1'], 'C': ['SL2']}
    assert pg.evaluate("() => window.app.project.distros[0].multiNumbers") is None
    _wait_server(pg, lambda p: 'multiNumbers' not in p['distros'][0])
    assert 'multiNumbers' not in _server()['distros'][0]
    # and what reset dealt is what holds from here: D joins after it
    _assign(pg, 'D')
    assert _names(pg) == {'D': ['SL3'], 'A': ['SL1'], 'C': ['SL2']}


def test_phase_balance_renumbers_circuits_and_what_it_dealt_then_holds(page):
    """Balance moves circuits onto other tails of their multi (one-circuit
    multis all on tail 1 - every one on leg X - spread across the fan): the
    circuit labels renumber. A screen joining afterwards renumbers neither
    the multis nor the balanced circuits."""
    pg = page
    one = {'columns': 1}
    _open(pg, json.dumps({'A': one, 'B': one, 'C': one}))
    assert [pg.evaluate("(n) => window.__sm.labels(n)", n) for n in 'ABC'] == [
        ['SL1-1'], ['SL2-1'], ['SL3-1']]
    moves = pg.evaluate("""() => {
        const r = window.app.suggestPhaseBalance('d1');
        window.app.applyPhaseBalance(r.moves);
        return r.moves.length;
    }""")
    assert moves > 0
    pg.wait_for_function('() => window.__sm.inflight()')
    balanced = [pg.evaluate("(n) => window.__sm.labels(n)", n) for n in 'ABC']
    assert balanced != [['SL1-1'], ['SL2-1'], ['SL3-1']]
    assert sorted(lbl[0].split('-')[1] for lbl in balanced) == ['1', '2', '3']
    # the server holds the balanced tails
    ids = _ids(pg)
    _wait_server(pg, lambda p: all(
        (next(l for l in p['layers'] if l['id'] == ids[n]).get('powerSocaPhasePos') or {})
        == (pg.evaluate("(n) => window.__sm.layer(n).powerSocaPhasePos || {}", n))
        for n in 'ABC'))
    _assign(pg, 'D')
    assert [pg.evaluate("(n) => window.__sm.labels(n)", n) for n in 'ABC'] == balanced
    assert _names(pg) == {'D': ['SL4'], 'A': ['SL1'], 'B': ['SL2'], 'C': ['SL3']}


def test_undo_and_redo_carry_the_held_numbers(page):
    """Undo the join: D is off the distro, nothing is held, and the server
    is back to the opened state. Redo: D is SL4 again and A, B, C keep
    SL1..SL3, server side too."""
    pg = page
    _open(pg)
    ids = _ids(pg)
    _assign(pg, 'D')
    joined = _names(pg)
    pg.evaluate('() => window.app.undo()')
    assert _names(pg) == BEFORE
    assert pg.evaluate("() => window.app.project.distros[0].multiNumbers") is None
    proj = _wait_server(pg, lambda p: 'multiNumbers' not in p['distros'][0]
                        and not (_server_layer('D') or {}).get('powerSocaDistro'))
    assert 'multiNumbers' not in proj['distros'][0]
    pg.evaluate('() => window.app.redo()')
    assert _names(pg) == joined == {'D': ['SL4'], 'A': ['SL1'], 'B': ['SL2'], 'C': ['SL3']}
    want = {f"{ids['D']}:1": 4, f"{ids['A']}:1": 1, f"{ids['B']}:1": 2, f"{ids['C']}:1": 3}
    proj = _wait_server(pg, lambda p: p['distros'][0].get('multiNumbers') == want)
    assert proj['distros'][0]['multiNumbers'] == want
    # an edit after the redo still holds them (the baseline followed)
    pg.evaluate("() => window.app.setSocaDistro(window.__sm.layer('B'), 1, null)")
    assert _names(pg) == {'D': ['SL4'], 'A': ['SL1'], 'B': [None], 'C': ['SL3']}


def test_save_and_reload_round_trip_the_held_numbers(page):
    """The saved file carries the store on its distro; opened again, the
    show prints exactly what it printed when saved."""
    pg = page
    _open(pg)
    _assign(pg, 'D')
    pg.evaluate("() => { window.__sm.select('B'); window.app.deleteCurrentLayer(); }")
    pg.wait_for_function("() => !window.app.deletionInProgress && !window.__sm.layer('B')")
    pg.wait_for_function('() => window.__sm.inflight()')
    saved_names = _names(pg)
    assert saved_names == {'D': ['SL4'], 'A': ['SL1'], 'C': ['SL3']}
    # exactly the text Save writes to disk
    data = json.loads(pg.evaluate("() => window.app.serializeProjectForFile()"))
    assert data['distros'][0]['multiNumbers']
    pg.evaluate("(p) => window.__sm.open(p)", data)
    pg.wait_for_function('() => window.__sm.inflight()')
    assert _names(pg) == saved_names
    proj = _wait_server(pg, lambda p: p['distros'][0].get('multiNumbers') == data['distros'][0]['multiNumbers'])
    assert proj['distros'][0]['multiNumbers'] == data['distros'][0]['multiNumbers']
    # and the next screen to land still fills the gap B left
    pg.evaluate("""() => {
        const app = window.app;
        const l = window.__sm.layer('D');
        app.setSocaDistro(l, 1, null);
    }""")
    assert _names(pg) == {'D': [None], 'A': ['SL1'], 'C': ['SL3']}
    _assign(pg, 'D')
    assert _names(pg) == {'D': ['SL2'], 'A': ['SL1'], 'C': ['SL3']}


def test_a_copy_never_inherits_numbers(page):
    """Copies never carry feeds: a pasted or duplicated screen starts on no
    distro, holds no number, and the numbers already dealt stay put."""
    pg = page
    _open(pg)
    _assign(pg, 'D')
    before = _names(pg)
    n0 = pg.evaluate("() => window.app.project.layers.length")
    pg.evaluate("() => { window.__sm.select('B'); window.app.copyLayer(); window.app.pasteLayer(); }")
    pg.wait_for_function("(n) => window.app.project.layers.length === n + 1", arg=n0)
    pg.evaluate("() => window.app.duplicateLayer(window.__sm.layer('C'))")
    pg.wait_for_function("(n) => window.app.project.layers.length === n + 2", arg=n0)
    pg.wait_for_function('() => window.__sm.inflight()')
    names = _names(pg)
    copies = {k: v for k, v in names.items() if k not in before}
    assert len(copies) == 2 and all(v == [None] for v in copies.values()), names
    assert {k: names[k] for k in before} == before
    ids = _ids(pg)
    copy_ids = {ids[k] for k in copies}
    proj = _wait_server(pg, lambda p: len(p['layers']) == n0 + 2)
    store = proj['distros'][0].get('multiNumbers') or {}
    assert not [k for k in store if int(k.split(':')[0]) in copy_ids]
    for l in proj['layers']:
        if l['id'] in copy_ids:
            assert not any((l.get('powerSocaDistro') or {}).values())


def test_a_locked_screen_is_never_written(page):
    """C is locked. D joining ahead of it, B leaving and the reset all
    happen around it: C prints SL3 throughout, and its layer record - on
    the client and on the server - never changes. Its held number lives on
    the distro record, not on the screen."""
    pg = page
    _open(pg)
    ids = _ids(pg)
    pg.evaluate("() => { window.__sm.select('C'); window.app.setLockOnSelected(true); }")
    _wait_server(pg, lambda p: (_server_layer('C') or {}).get('locked') is True)
    pg.wait_for_function('() => window.__sm.inflight()')
    server_c = json.dumps(_server_layer('C'), sort_keys=True)
    # the client's copy is re-adopted from the server by the delete; what
    # must not move on it is every per-multi store
    power_c = """() => { const l = window.__sm.layer('C');
        return JSON.stringify(Object.fromEntries(Object.keys(l).sort()
            .filter(k => k.startsWith('powerSoca') || k === 'powerLabelOverrides' || k === 'locked').map(k => [k, l[k]]))); }"""
    client_c = pg.evaluate(power_c)
    _assign(pg, 'D')
    assert _names(pg)['C'] == ['SL3']
    pg.evaluate("() => { window.__sm.select('B'); window.app.deleteCurrentLayer(); }")
    pg.wait_for_function("() => !window.app.deletionInProgress && !window.__sm.layer('B')")
    pg.wait_for_function('() => window.__sm.inflight()')
    assert _names(pg) == {'D': ['SL4'], 'A': ['SL1'], 'C': ['SL3']}
    pg.evaluate("() => window.app.clearPhaseBalance('d1')")
    pg.wait_for_function('() => window.__sm.inflight()')
    # the reset deals D and A again in screen order - around the locked SL3
    assert _names(pg) == {'D': ['SL1'], 'A': ['SL2'], 'C': ['SL3']}
    proj = _wait_server(pg, lambda p: (p['distros'][0].get('multiNumbers') or {}) == {f"{ids['C']}:1": 3})
    assert proj['distros'][0]['multiNumbers'] == {f"{ids['C']}:1": 3}
    assert json.dumps(_server_layer('C'), sort_keys=True) == server_c
    assert pg.evaluate(power_c) == client_c


def test_a_split_carries_the_held_numbers_with_their_multis(page):
    """A has three multis, SL1..SL3. A's first comes off the distro (SL1 is
    free now). Splitting A's second multi inserts a new multi after it, so
    A's third moves to index 4 - and its SL3 moves with it, rather than
    dealing afresh into the free SL1. The new part, fed, takes SL1."""
    pg = page
    _open(pg, json.dumps({'A': {'columns': 13,
                                'powerSocaDistro': {'1': 'd1', '2': 'd1', '3': 'd1'}}}))
    assert _names(pg) == {'D': [None], 'A': ['SL1', 'SL2', 'SL3'], 'B': ['SL4'], 'C': ['SL5']}
    _assign(pg, 'A', soca=1, distro=None)
    assert _names(pg) == {'D': [None], 'A': [None, 'SL2', 'SL3'], 'B': ['SL4'], 'C': ['SL5']}
    assert pg.evaluate("() => window.app.splitSocaAfter(window.__sm.layer('A'), 2, 3)") is True
    pg.wait_for_function('() => window.__sm.inflight()')
    assert _names(pg)['A'] == [None, 'SL2', None, 'SL3']
    _assign(pg, 'A', soca=3)
    assert _names(pg) == {'D': [None], 'A': [None, 'SL2', 'SL1', 'SL3'], 'B': ['SL4'], 'C': ['SL5']}
    ids = _ids(pg)
    proj = _wait_server(pg, lambda p: (p['distros'][0].get('multiNumbers') or {}).get(f"{ids['A']}:4") == 3)
    store = proj['distros'][0]['multiNumbers']
    assert store[f"{ids['A']}:4"] == 3
    # nothing left behind under the index the multi moved off
    assert f"{ids['A']}:3" not in store or store[f"{ids['A']}:3"] == 1


FACE = {'distro': {'name': 'FD', 'outputRows': [
    {'id': 'r1', 'connector': 'soca', 'count': 6, 'coupling': 'ln', 'breakerA': 20}]}}


def test_a_distro_with_outputs_holds_its_numbers_too(page):
    """On a distro with a face (its own numbered outputs, 1.5) an auto multi
    takes the first free output it can land on. D joining ahead of A, B, C
    used to take output 1 and push the rest along; now they keep 1..3 and
    D takes output 4."""
    pg = page
    _open(pg, json.dumps(FACE))
    assert _names(pg) == {'D': [None], 'A': ['FD1'], 'B': ['FD2'], 'C': ['FD3']}
    _assign(pg, 'D')
    assert _names(pg) == {'D': ['FD4'], 'A': ['FD1'], 'B': ['FD2'], 'C': ['FD3']}
    _wait_server(pg, lambda p: bool(p['distros'][0].get('multiNumbers')))
    _assign(pg, 'B', distro=None)
    _assign(pg, 'B')
    # B left and came back: its old output 2 was free again, the lowest
    assert _names(pg) == {'D': ['FD4'], 'A': ['FD1'], 'B': ['FD2'], 'C': ['FD3']}


def test_the_rest_of_a_multi_a_drop_cut_through_keeps_its_number(page):
    """B is deleted, leaving SL2 free. C's first circuit is dropped onto
    box SL5: the rest of C's multi stays on its box as SL3 - the same
    cable, already numbered - rather than dealing into the free SL2."""
    pg = page
    _open(pg)
    pg.evaluate("() => { window.__sm.select('B'); window.app.deleteCurrentLayer(); }")
    pg.wait_for_function("() => !window.app.deletionInProgress && !window.__sm.layer('B')")
    pg.wait_for_function('() => window.__sm.inflight()')
    assert _names(pg) == {'D': [None], 'A': ['SL1'], 'C': ['SL3']}
    r = pg.evaluate("() => window.app.takeSocaOnto(window.__sm.layer('C'), 1, 'd1', 5)")
    assert r['ok'] is True and r['took'] == 1, r
    pg.wait_for_function('() => window.__sm.inflight()')
    assert _names(pg) == {'D': [None], 'A': ['SL1'], 'C': ['SL5', 'SL3']}
    ids = _ids(pg)
    proj = _wait_server(pg, lambda p: (p['distros'][0].get('multiNumbers') or {}).get(f"{ids['C']}:2") == 3)
    assert proj['distros'][0]['multiNumbers'][f"{ids['C']}:2"] == 3
    # and undo puts the whole multi back as SL3
    pg.evaluate('() => window.app.undo()')
    assert _names(pg) == {'D': [None], 'A': ['SL1'], 'C': ['SL3']}
