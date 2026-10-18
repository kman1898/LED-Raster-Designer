"""Typed cable lengths go away with the feed they belong to.

The owner's ruling (2026-10-17): "if i delete a distro or clear a multi etc
it needs to delete the lengths for the cable and extensions. same goes for
data tab". Picked, exactly:

Power
- Delete a distro: every multi home run (powerSocaLengths) and every circuit
  cable (powerCircuitCables, the "25' True1" tags) on the screens it fed,
  a direct output's home run on the distro face included.
- Clear a multi: its home run and the cables on its circuits.
- Clear a circuit: that circuit's cable (and, where the circuit IS the
  multi - a one-circuit holder, a direct output - the home run with it).
- Unfeed a screen: off a distro, or onto another, the old feed's lengths go.

Data
- Release a port: its own port cable (socket to screen). Its snake stays.
- Remove a card or processor: every port cable on it, and the snakes that
  lived only on it.
- Remove a breakout box: its port cables and its fiber / copper runs.
- Delete a screen (alone, with a selection, with its group or with its
  canvas): the port cables on the sockets it held, as a release does - a
  socket another screen still claims keeps its cable, the snakes stay
  (owner, 2026-10-17). A pull-sheet edit on a row that went with the
  screen goes too; one on a row another screen still prints stays, and
  free rows are untouched.

Kept: the screen's own V/H jumper lengths (dataJumpV/H, powerJumpV/H).

A length never reappears when a later feed takes the same multi index or
the same socket; undo puts the lengths back; a locked screen keeps its own;
a copy carries none; a shared box clears once; a pull-sheet edit on a row
that went goes with it. Opening a show changes nothing - an orphan length an
older file holds stays stored, and prints nowhere.

Every test checks the browser AND the server's project, waits on real
conditions, and leaves the shared server project as it found it
(conftest.server_project_guard).
"""

import copy
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from conftest import settled  # noqa: E402

CARD = 'novastar-card-h-16xrj45-2xfiber'
MOD = 'Meta' if sys.platform == 'darwin' else 'Control'
JUMPERS = {'dataJumpV': 2, 'dataJumpH': 3, 'powerJumpV': 4, 'powerJumpH': 5}


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
    # the app's own first load lands before the test touches the project
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
# screen's `columns` IS its circuit count. PD is a distro FACE - five True1
# direct outputs (1-5) then two soca multis (6, 7); SR an old-style distro.
#   A  7 wide: multi 1 (circuits 1-6) on PD 6, home run 100', cables on 1
#      and 2; multi 2 (circuit 7) on PD 1 - a direct output - home run 25'.
#   B  3 wide: multi 1 on SR, home run 150', cables on 1 and 3.
#   C, D  3 wide each, both pinned to PD 7 - ONE shared box, its 200' home
#      run written through on both; a cable on C 2 and on D 3.
HELPERS_JS = r"""
window.__fl = {
    screen(o) {
        o = Object.assign({
            type: 'screen', visible: true, locked: false,
            columns: 3, rows: 5, cabinet_width: 128, cabinet_height: 128,
            offset_x: 0, offset_y: 0, panel_weight: 20, weight_unit: 'kg',
            panelWatts: 208, powerVoltage: 208, powerAmperage: 5,
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
    project(opts) {
        opts = opts || {};
        const cab = (ft) => ({ ft, connector: null });
        const s = (id, name, x, extra) => this.screen(Object.assign(
            { id, name, offset_x: x }, extra || {}, (opts.layers || {})[name] || {}));
        return {
            name: 'Feed lengths', cableUnit: 'ft',
            distros: [
                { id: 'd1', name: 'PD', ratingA: 200, system: '120/208',
                  outputRows: [
                      { id: 'r1', connector: 'true1', count: 5, coupling: 'll', breakerA: 20 },
                      { id: 'r2', connector: 'soca', count: 2, coupling: 'll', breakerA: 20 }] },
                { id: 'd2', name: 'SR', ratingA: 400, system: '120/208', voltage: 208, phase: 3 },
            ],
            layers: [
                s(1, 'A', 0, Object.assign({ columns: 7,
                    powerSocaDistro: { 1: 'd1', 2: 'd1' }, powerSocaNumber: { 1: 6, 2: 1 },
                    powerSocaLengths: { 1: '100', 2: '25' },
                    powerCircuitCables: { 1: cab(10), 2: cab(6) } }, %JUMPERS%)),
                s(2, 'B', 1200, { powerSocaDistro: { 1: 'd2' },
                    powerSocaLengths: { 1: '150' },
                    powerCircuitCables: { 1: cab(8), 3: cab(9) } }),
                s(3, 'C', 1800, { powerSocaDistro: { 1: 'd1' }, powerSocaNumber: { 1: 7 },
                    powerSocaLengths: { 1: '200' }, powerCircuitCables: { 2: cab(12) } }),
                s(4, 'D', 2400, { powerSocaDistro: { 1: 'd1' }, powerSocaNumber: { 1: 7 },
                    powerSocaLengths: { 1: '200' }, powerCircuitCables: { 3: cab(14) } }),
            ].concat(opts.extra || []),
        };
    },
    async j(method, url, body) {
        const r = await fetch(url, { method,
            headers: { 'Content-Type': 'application/json' },
            body: body === undefined ? undefined : JSON.stringify(body) });
        const out = await r.json();
        if (!r.ok) throw new Error(url + ': ' + JSON.stringify(out));
        return out;
    },
    // The open path's own steps: the server takes the project, the client
    // adopts the server's copy, history starts over.
    async open(project) {
        const app = window.app;
        await this.j('PUT', '/api/project', project);
        app.project = await this.j('GET', '/api/project');
        app.dedupeProjectLayers('feed_lengths');
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
    stores(name) {
        const l = this.layer(name);
        return { lengths: JSON.parse(JSON.stringify(l.powerSocaLengths || {})),
                 cables: Object.keys(l.powerCircuitCables || {}).map(Number).sort((a, b) => a - b),
                 distro: JSON.parse(JSON.stringify(l.powerSocaDistro || {})) };
    },
    inflight() {
        const s = window.app._inflightLayerPuts;
        return !s || s.size === 0;
    },
    // The pull sheet's rows as [position key, type|length], fresh.
    rows() {
        const app = window.app;
        app._circuitTailCache = null;
        return app.buildPullList().positions.flatMap(p =>
            p.rows.map(r => [app.pullPositionKey(p), app.pullRowKey(r), r.length]));
    },
    // Every text the binder draws, every page.
    binderTexts() {
        const app = window.app;
        app._circuitTailCache = null;
        const opts = { sheet: 'tabloid', palette: 'colour', sides: { power: true, data: true },
                       scope: { kind: 'show' }, cover: true, pull: true, hardware: true,
                       titleBlock: false };
        const plan = app.planBinder(opts);
        const out = [];
        plan.forEach((p, i) => {
            const r = app.renderBinderPage(opts, i);
            out.push(...(r.texts || []), ...(r.mapTexts || []));
        });
        return out;
    },
};
""".replace('%JUMPERS%', json.dumps(JUMPERS))


def _server():
    import app as app_module
    return app_module.current_project


def _srv_layer(name, project=None):
    p = project if project is not None else _server()
    return next((l for l in (p.get('layers') or []) if l.get('name') == name), None)


def _srv_stores(name, project=None):
    l = _srv_layer(name, project) or {}
    return {'lengths': dict(l.get('powerSocaLengths') or {}),
            'cables': sorted(int(k) for k in (l.get('powerCircuitCables') or {})),
            'distro': dict(l.get('powerSocaDistro') or {})}


def _wait_server(pg, ok, timeout_ms=8000):
    """Poll the in-process server project until ok(project) holds; return it."""
    return settled(pg, lambda: copy.deepcopy(_server()), ok, timeout_ms)


def _open(pg, opts=None):
    pg.evaluate("(o) => window.__fl.open(window.__fl.project(o))", opts or {})
    pg.wait_for_function('() => window.__fl.inflight()')


def _stores(pg, name):
    return pg.evaluate("(n) => window.__fl.stores(n)", name)


def _settle(pg):
    pg.wait_for_function('() => window.__fl.inflight()')


FED_A = {'lengths': {'1': '100', '2': '25'}, 'cables': [1, 2], 'distro': {'1': 'd1', '2': 'd1'}}


# ── Power ─────────────────────────────────────────────────────────────────

def test_removing_a_distro_forgets_every_length_it_fed(page):
    """Remove PD: A's multi home run, A's direct-output home run (PD 1),
    A's circuit cables and the shared box's 200' on C and D all go - in
    the browser and on the server. SR's screen B keeps its 150' and its
    cables; A keeps its jumpers."""
    pg = page
    _open(pg)
    assert _stores(pg, 'A') == FED_A
    assert pg.evaluate("() => window.app.removeDistro('d1')") is True
    _settle(pg)
    for name in ('A', 'C', 'D'):
        assert _stores(pg, name)['lengths'] == {}, name
        assert _stores(pg, name)['cables'] == [], name
    assert _stores(pg, 'B') == {'lengths': {'1': '150'}, 'cables': [1, 3], 'distro': {'1': 'd2'}}
    srv = _wait_server(pg, lambda p: _srv_stores('A', p)['lengths'] == {}
                       and _srv_stores('C', p)['lengths'] == {}
                       and _srv_stores('D', p)['lengths'] == {})
    for name in ('A', 'C', 'D'):
        assert _srv_stores(name, srv) == {'lengths': {}, 'cables': [], 'distro': {}}, name
    assert _srv_stores('B', srv) == {'lengths': {'1': '150'}, 'cables': [1, 3], 'distro': {'1': 'd2'}}
    assert {k: _srv_layer('A', srv).get(k) for k in JUMPERS} == JUMPERS


def test_clearing_a_multi_forgets_its_home_run_and_its_circuit_cables(page):
    """Clear Multi on A's multi 1 (the canvas run's right-click): its 100'
    and the cables on circuits 1 and 2 go; multi 2 - still on its direct
    output - keeps its 25'."""
    pg = page
    _open(pg)
    item = pg.evaluate("""() => {
        const app = window.app, A = window.__fl.layer('A');
        const panel = A.panels.find(p => p.row === 0 && p.col === 0);
        const it = app._clearMenuForCircuit({ layerId: A.id, panel });
        if (!it || !it.run) return it ? it.label : null;
        it.run();
        return it.label;
    }""")
    assert item and item.startswith('Clear multi'), item
    _settle(pg)
    assert _stores(pg, 'A') == {'lengths': {'2': '25'}, 'cables': [], 'distro': {'2': 'd1'}}
    srv = _wait_server(pg, lambda p: _srv_stores('A', p)['cables'] == [])
    assert _srv_stores('A', srv) == {'lengths': {'2': '25'}, 'cables': [], 'distro': {'2': 'd1'}}


def test_clearing_a_circuit_forgets_that_circuits_cable(page):
    """Clear Circuit on A 2 (inside the six-circuit multi): only circuit 2's
    cable goes - circuit 1's cable and the multi's 100' stay. Clear Circuit
    on A 7, the direct output's one circuit: the circuit IS the multi, so
    its 25' home run goes with it."""
    pg = page
    _open(pg)
    pg.evaluate("""() => {
        const app = window.app, A = window.__fl.layer('A');
        app._clearCircuitChip(A, 1, 2);
    }""")
    _settle(pg)
    a = _stores(pg, 'A')
    assert a['cables'] == [1], a
    assert '100' in a['lengths'].values(), a
    srv = _wait_server(pg, lambda p: _srv_stores('A', p)['cables'] == [1])
    assert _srv_stores('A', srv)['cables'] == [1]
    # the direct output's circuit
    pg.evaluate("""() => {
        const app = window.app, A = window.__fl.layer('A');
        app._circuitTailCache = null;
        const rec = [...app._powerNaming(A).socas.values()].find(r => r.circuits.includes(7));
        app._clearCircuitChip(A, rec.index, 7);
    }""")
    _settle(pg)
    a = _stores(pg, 'A')
    assert '25' not in a['lengths'].values(), a
    srv = _wait_server(pg, lambda p: '25' not in _srv_stores('A', p)['lengths'].values())
    assert '25' not in _srv_stores('A', srv)['lengths'].values()
    assert '100' in _srv_stores('A', srv)['lengths'].values()


def test_unfeeding_a_screen_forgets_the_old_feeds_lengths(page):
    """B's circuit 1 dragged from SR onto PD's direct output 3: the circuit
    leaves SR, so its cable and the 150' home run it carried go, and the
    circuits cut off behind it (2, 3 - unassigned by the split rule) lose
    their cables too. Then the slot dragged back onto the tray takes C and
    D off PD 7 - their 200' goes. Then a multi taken off its distro by the
    setter itself forgets too."""
    pg = page
    _open(pg)
    pg.evaluate("""() => {
        const app = window.app, B = window.__fl.layer('B');
        app._dockDropTail({ type: 'tail', distroId: 'd1', number: '3', tail: 1, title: 'PD 3' },
                          { kind: 'run', layerId: B.id, num: 1 });
    }""")
    _settle(pg)
    b = _stores(pg, 'B')
    assert b['distro'].get('1') == 'd1', b
    assert b['lengths'] == {} and b['cables'] == [], b
    srv = _wait_server(pg, lambda p: _srv_stores('B', p)['distro'].get('1') == 'd1')
    assert _srv_stores('B', srv)['lengths'] == {} and _srv_stores('B', srv)['cables'] == []
    # the slot back onto the tray
    pg.evaluate("""() => window.app._dockDropSlot(
        { type: 'slot', distroId: 'd1', number: 7, title: 'PD 7' }, { kind: 'dock' })""")
    _settle(pg)
    for name in ('C', 'D'):
        assert _stores(pg, name) == {'lengths': {}, 'cables': [], 'distro': {}}, name
    srv = _wait_server(pg, lambda p: _srv_stores('C', p)['distro'] == {}
                       and _srv_stores('D', p)['distro'] == {})
    for name in ('C', 'D'):
        assert _srv_stores(name, srv) == {'lengths': {}, 'cables': [], 'distro': {}}, name
    # the setter: A's multi 1 off PD
    pg.evaluate("() => window.app.setSocaDistro(window.__fl.layer('A'), 1, null)")
    _settle(pg)
    assert _stores(pg, 'A') == {'lengths': {'2': '25'}, 'cables': [], 'distro': {'2': 'd1'}}
    srv = _wait_server(pg, lambda p: _srv_stores('A', p)['cables'] == [])
    assert _srv_stores('A', srv) == {'lengths': {'2': '25'}, 'cables': [], 'distro': {'2': 'd1'}}


def test_a_new_feed_on_the_same_multi_index_starts_blank(page):
    """The user-visible bug: PD removed, then A's multi 1 fed again from SR
    - its old 100' and its circuits' cables used to come straight back.
    And the direct output cleared at circuit scope, then fed again: its 25'
    used to come back the same way."""
    pg = page
    _open(pg)
    pg.evaluate("() => window.app.removeDistro('d1')")
    _settle(pg)
    took = pg.evaluate("""() => window.app.takeSocaOnto(window.__fl.layer('A'), 1, 'd2', 1,
                                                       'Assign Multi Distro')""")
    assert took['ok'], took
    _settle(pg)
    plan = pg.evaluate("""() => { window.app._circuitTailCache = null;
        return window.app.getSocaPlan(window.__fl.layer('A')).map(s => [s.distroId, s.length]); }""")
    assert plan[0] == ['d2', None], plan
    assert _stores(pg, 'A')['lengths'] == {} and _stores(pg, 'A')['cables'] == []
    srv = _wait_server(pg, lambda p: _srv_stores('A', p)['distro'].get('1') == 'd2')
    assert _srv_stores('A', srv)['lengths'] == {} and _srv_stores('A', srv)['cables'] == []
    # the direct output: cleared at circuit scope, then fed again
    _open(pg)
    pg.evaluate("""() => {
        const app = window.app, A = window.__fl.layer('A');
        app._circuitTailCache = null;
        const rec = [...app._powerNaming(A).socas.values()].find(r => r.circuits.includes(7));
        app._clearCircuitChip(A, rec.index, 7);
    }""")
    _settle(pg)
    took = pg.evaluate("""() => window.app.takeSocaOnto(window.__fl.layer('A'), 7, 'd1', 1,
                                                       'Assign Multi Distro')""")
    assert took['ok'], took
    _settle(pg)
    plan = pg.evaluate("""() => { window.app._circuitTailCache = null;
        return window.app.getSocaPlan(window.__fl.layer('A')).map(s => [s.distroId, s.length]); }""")
    assert plan == [['d1', '100'], ['d1', None]], plan
    srv = _wait_server(pg, lambda p: len(_srv_stores('A', p)['distro']) == 2)
    assert _srv_stores('A', srv)['lengths'] == {'1': '100'}


def test_a_length_an_older_file_left_on_an_unfed_multi_never_rides_a_new_feed(page):
    """An older file holds a 75' home run and a circuit cable on A's
    multi 2 with no distro (an 11' cable on its circuit). Opening it changes nothing (the server's copy
    is what was PUT) and neither prints - not on the pull sheet, not in
    the binder. Feeding that multi later starts it blank."""
    pg = page
    proj = pg.evaluate("""() => {
        const p = window.__fl.project({ layers: { A: {
            powerSocaDistro: { 1: 'd1' }, powerSocaNumber: { 1: 6 },
            powerSocaLengths: { 1: '100', 2: '75' },
            powerCircuitCables: { 1: { ft: 10, connector: null }, 7: { ft: 11, connector: null } } } } });
        return p;
    }""")
    pg.evaluate("(p) => window.__fl.open(p)", proj)
    _settle(pg)
    a = _srv_layer('A')
    assert a['powerSocaLengths'] == {'1': '100', '2': '75'}, 'opening rewrote the stored lengths'
    assert sorted(a['powerCircuitCables']) == ['1', '7'], 'opening rewrote the stored cables'
    assert pg.evaluate("() => window.app.printedCircuitCable(window.__fl.layer('A'), 7)") is None
    assert pg.evaluate("() => window.app.printedCircuitCable(window.__fl.layer('A'), 1).text") == "10' True1"
    lengths = [r[2] for r in pg.evaluate("() => window.__fl.rows()")]
    assert "75'" not in lengths and "11'" not in lengths, lengths
    texts = pg.evaluate("() => window.__fl.binderTexts()")
    assert not [t for t in texts if "75'" in str(t) or "11'" in str(t)], \
        [t for t in texts if "75'" in str(t) or "11'" in str(t)]
    assert any("100'" in str(t) for t in texts), 'the fed home run should print'
    took = pg.evaluate("""() => window.app.takeSocaOnto(window.__fl.layer('A'), 7, 'd1', 2,
                                                       'Assign Multi Distro')""")
    assert took['ok'], took
    _settle(pg)
    srv = _wait_server(pg, lambda p: len(_srv_stores('A', p)['distro']) == 2)
    assert _srv_stores('A', srv)['lengths'] == {'1': '100'}
    assert _srv_stores('A', srv)['cables'] == [1]


def test_undo_puts_the_lengths_back_on_the_server_too(page):
    """Remove PD, then Ctrl+Z: the distro and every length it took come back
    - the browser's copy and the server's."""
    pg = page
    _open(pg)
    pg.evaluate("() => window.app.removeDistro('d1')")
    _settle(pg)
    _wait_server(pg, lambda p: _srv_stores('A', p)['lengths'] == {})
    pg.evaluate("() => window.app.undo()")
    srv = _wait_server(pg, lambda p: _srv_stores('A', p)['lengths'] != {})
    assert _srv_stores('A', srv) == FED_A
    assert _srv_stores('C', srv)['lengths'] == {'1': '200'}
    assert _srv_stores('D', srv)['cables'] == [3]
    assert [d['id'] for d in srv['distros']] == ['d1', 'd2']
    assert _stores(pg, 'A') == FED_A


def test_a_locked_screen_keeps_its_lengths(page):
    """C is locked. Removing PD - which feeds C - is refused whole, as it
    always was: nothing is forgotten anywhere. Clearing the shared box PD 7
    skips C (named) and clears D's copy of the home run."""
    pg = page
    _open(pg, {'layers': {'C': {'locked': True}}})
    assert pg.evaluate("() => window.app.removeDistro('d1')") is False
    assert _stores(pg, 'A') == FED_A
    assert _stores(pg, 'C')['lengths'] == {'1': '200'}
    assert _srv_stores('A') == FED_A
    pg.evaluate("""() => {
        const C = window.__fl.layer('C'), D = window.__fl.layer('D');
        window.app._clearMultis([{ layerId: C.id, soca: 1 }, { layerId: D.id, soca: 1 }], 'Clear Multi');
    }""")
    _settle(pg)
    assert _stores(pg, 'C') == {'lengths': {'1': '200'}, 'cables': [2], 'distro': {'1': 'd1'}}
    assert _stores(pg, 'D') == {'lengths': {}, 'cables': [], 'distro': {}}
    srv = _wait_server(pg, lambda p: _srv_stores('D', p)['distro'] == {})
    assert _srv_stores('C', srv) == {'lengths': {'1': '200'}, 'cables': [2], 'distro': {'1': 'd1'}}
    assert _srv_stores('D', srv) == {'lengths': {}, 'cables': [], 'distro': {}}


def test_a_shared_box_cleared_forgets_its_home_run_on_every_screen_once(page):
    """PD 7 is one box on C and D (the home run written through on both).
    Its right-click Clear takes every member and the 200' goes from both -
    nothing of it is left on either screen to print again."""
    pg = page
    _open(pg)
    item = pg.evaluate("""() => {
        const members = window.app._distroMultiNumbers('d1').get(7) || [];
        window.app._clearMultis(members.map(m => ({ layerId: m.layerId, soca: m.soca })), 'Clear Multi');
        return members.length;
    }""")
    assert item == 2
    _settle(pg)
    for name in ('C', 'D'):
        assert _stores(pg, name) == {'lengths': {}, 'cables': [], 'distro': {}}, name
    srv = _wait_server(pg, lambda p: _srv_stores('C', p)['distro'] == {}
                       and _srv_stores('D', p)['distro'] == {})
    for name in ('C', 'D'):
        assert _srv_stores(name, srv) == {'lengths': {}, 'cables': [], 'distro': {}}, name
    texts = pg.evaluate("() => window.__fl.binderTexts()")
    assert not [t for t in texts if "200'" in str(t)]


def test_the_jumpers_stay_with_the_screen(page):
    """Every clear above on A in a row - a circuit, the multi, the distro -
    and A's four jumper lengths are untouched on both sides."""
    pg = page
    _open(pg)
    pg.evaluate("() => window.app._clearCircuitChip(window.__fl.layer('A'), 1, 2)")
    _settle(pg)
    pg.evaluate("""() => window.app._clearMultis([{ layerId: window.__fl.layer('A').id, soca: 1 }],
                                                  'Clear Multi')""")
    _settle(pg)
    pg.evaluate("() => window.app.removeDistro('d1')")
    _settle(pg)
    srv = _wait_server(pg, lambda p: _srv_stores('A', p)['lengths'] == {})
    assert _srv_stores('A', srv)['lengths'] == {}
    assert {k: _srv_layer('A', srv).get(k) for k in JUMPERS} == JUMPERS
    assert pg.evaluate("(ks) => ks.map(k => window.__fl.layer('A')[k])", list(JUMPERS)) \
        == list(JUMPERS.values())


def test_a_copy_carries_no_circuit_cables(page):
    """Duplicate A (Cmd+J): the copy has no feed, so it has no lengths -
    no home runs (as before) and now no circuit cables either. A keeps
    its own."""
    pg = page
    _open(pg)
    before = pg.evaluate("""() => {
        const app = window.app, A = window.__fl.layer('A');
        app.selectLayer(A);
        app.selectedLayerIds = new Set([A.id]);
        if (document.activeElement) document.activeElement.blur();
        return app.project.layers.map(l => l.id);
    }""")
    pg.keyboard.press(f'{MOD}+j')
    pg.wait_for_function("(n) => window.app.project.layers.length > n", arg=len(before))
    srv = _wait_server(pg, lambda p: len(p['layers']) > len(before))
    copy_layer = next(l for l in srv['layers'] if l['id'] not in before)
    assert not (copy_layer.get('powerCircuitCables') or {}), copy_layer.get('powerCircuitCables')
    assert not (copy_layer.get('powerSocaLengths') or {})
    assert {k: copy_layer.get(k) for k in JUMPERS} == JUMPERS, 'the jumpers are the screen\'s'
    assert _srv_stores('A', srv) == FED_A


def test_a_pull_sheet_edit_goes_with_the_row_its_cable_printed(page):
    """A note typed on A's 100' multi row. Clearing that multi takes the row
    off the sheet, and the saved edit goes with it - not left behind as
    STALE to come back on the next 100' multi there. Undo brings the edit
    back with the cable, on the server too."""
    pg = page
    _open(pg)
    target = pg.evaluate("""() => {
        const app = window.app;
        app._circuitTailCache = null;
        for (const pos of app.buildPullList().positions) {
            for (const r of pos.rows) {
                if (r.length === "100'") {
                    const pk = app.pullPositionKey(pos), key = app.pullRowKey(r);
                    app.setPullSheetRowEdit(pk, key, { notes: 'spare in truck 2' }, r);
                    return [pk, key];
                }
            }
        }
        return null;
    }""")
    assert target, 'no 100\' row on the sheet'
    _wait_server(pg, lambda p: bool(p.get('pullSheetEdits')))
    pg.evaluate("""() => window.app._clearMultis([{ layerId: window.__fl.layer('A').id, soca: 1 }],
                                                  'Clear Multi')""")
    _settle(pg)
    assert pg.evaluate("() => window.app.project.pullSheetEdits || null") is None
    assert pg.evaluate("() => window.app.pullSheetStaleEdits()") == []
    srv = _wait_server(pg, lambda p: not ((p.get('pullSheetEdits') or {}).get('positions')))
    assert not (srv.get('pullSheetEdits') or {}).get('positions'), srv.get('pullSheetEdits')
    pg.evaluate("() => window.app.undo()")
    srv = _wait_server(pg, lambda p: bool((p.get('pullSheetEdits') or {}).get('positions')))
    rows = srv['pullSheetEdits']['positions'][target[0]]['rows']
    assert rows == [{'key': target[1], 'notes': 'spare in truck 2'}], rows
    assert _srv_stores('A', srv) == FED_A


def test_a_grouped_wall_clear_circuit_forgets_the_cable_on_every_member_it_clears(page):
    """Two grouped screens in custom mode; the SECOND owns runs 1 and 2,
    each across the FIRST then its own cabinets, with a cable on each.
    Clear Circuit on the FIRST (run 1) clears the whole run - and its cable
    on the owner; run 2's cable stays. With the owner locked nothing is
    cleared, its cable included."""
    pg = page

    def pair():
        return pg.evaluate(r"""async () => {
            const app = window.app;
            const mk = (id, name, x) => window.__fl.screen({ id, name, columns: 7, rows: 8,
                offset_x: x, powerCustomPath: true, powerFlowPattern: 'custom' });
            await window.__fl.open({ name: 'Group', cableUnit: 'ft', distros: [],
                                     layers: [mk(1, 'E', 0), mk(2, 'F', 1000)] });
            const E = window.__fl.layer('E'), F = window.__fl.layer('F');
            app.selectedLayerIds = new Set([E.id, F.id]);
            app.currentLayer = E;
            await app.groupSelectedLayers();
            for (let i = 0; i < 20 && !window.__fl.layer('F').group_id; i++) {
                await new Promise(r => setTimeout(r, 50));
            }
            const e = window.__fl.layer('E'), f = window.__fl.layer('F');
            const run = (num) => {
                const out = [];
                for (let c = 0; c < 7; c++) out.push({ row: num - 1, col: c, layerId: e.id });
                for (let c = 0; c < 7; c++) out.push({ row: num - 1, col: c });
                return out;
            };
            f.powerCustomPaths = { 1: run(1), 2: run(2) };
            f.powerCustomIndex = 1;
            f.powerCircuitCables = { 1: { ft: 10, connector: null }, 2: { ft: 20, connector: null } };
            await app.updateLayers([e, f]);
            app.selectedLayerIds = new Set([e.id]);
            app.currentLayer = e;
            e.powerCustomIndex = 1;
            app.resetHistory('Initial State');
            return [e.id, f.id];
        }""")

    ids = pair()
    _settle(pg)
    _wait_server(pg, lambda p: sorted((_srv_layer('F', p) or {}).get('powerCircuitCables') or {}) == ['1', '2'])
    pg.evaluate("() => document.getElementById('power-custom-clear-circuit').click()")
    _settle(pg)
    assert pg.evaluate("() => Object.keys(window.__fl.layer('F').powerCircuitCables)") == ['2']
    srv = _wait_server(pg, lambda p: '1' not in ((_srv_layer('F', p) or {}).get('powerCustomPaths') or {}))
    f = _srv_layer('F', srv)
    assert '1' not in f['powerCustomPaths'] and sorted(f['powerCircuitCables']) == ['2'], f['powerCircuitCables']
    # the owner locked: Clear Circuit clears nothing, the cable stays
    ids = pair()
    _settle(pg)
    pg.evaluate("""() => { const F = window.__fl.layer('F'); F.locked = true;
        window.app.updateLayers([F]); window.app.resetHistory('Initial State'); }""")
    _settle(pg)
    assert pg.evaluate("() => window.__fl.layer('F').locked") is True
    pg.evaluate("() => document.getElementById('power-custom-clear-circuit').click()")
    _settle(pg)
    assert sorted(pg.evaluate("() => Object.keys(window.__fl.layer('F').powerCircuitCables)")) == ['1', '2']
    f = _srv_layer('F')
    assert sorted(f['powerCircuitCables']) == ['1', '2'] and '1' in f['powerCustomPaths']
    assert ids


# ── Data ──────────────────────────────────────────────────────────────────

# One 2048 x 1024 screen (W) on an H9's 16-port card: four ports, landed on
# sockets 1-4. Port cables typed on sockets 1-3 and on 9 (nothing there),
# a snake carrying sockets 1-2.
DATA_JS = r"""async (opts) => {
    opts = opts || {};
    const app = window.app, j = window.__fl.j.bind(window.__fl);
    const W = window.__fl.screen({ id: 1, name: 'W', columns: 8, rows: 4,
        cabinet_width: 256, cabinet_height: 256, locked: !!opts.locked });
    await window.__fl.open({ name: 'Data lengths', cableUnit: 'ft', distros: [], layers: [W] });
    const procs = await j('POST', '/api/processors', { deviceId: 'novastar-h9' });
    const pid = procs.resolved[procs.resolved.length - 1].id;
    let st = await j('PUT', `/api/processors/${pid}/slots/0`, { deviceId: opts.card });
    const cardId = st.resolved.find(p => p.id === pid).slots[0].card.id;
    let boxId = null, boxSocket = null, fiberId = null;
    if (opts.box) {
        st = await j('POST', `/api/processors/${pid}/cards/${cardId}/cvts`,
                     { deviceId: 'novastar-cvt10', pair: false });
        const box = st.resolved.find(p => p.id === pid).slots[0].card.cvts.slice(-1)[0];
        boxId = box.id;
        boxSocket = box.ports[0].number;
        await j('PUT', `/api/processors/${pid}/cvts/${boxId}`,
                { portCables: { [boxSocket]: { ft: 15 } } });
        st = await j('POST', '/api/fiber-cables', { kind: 'tac', strands: 12, ft: 300 });
        fiberId = st.fiberCables.slice(-1)[0].id;
        await j('PUT', `/api/processors/${pid}/cvts/${boxId}/fiber-links/p1`, { cable: fiberId });
    }
    const cables = { 1: { ft: 25 }, 2: { ft: 50 }, 3: { ft: 75 }, 9: { ft: 99 } };
    await j('PUT', `/api/processors/${pid}/cards/${cardId}`, { portCables: cables });
    st = await j('POST', '/api/snakes', { ft: 150, members: [
        { kind: 'card', id: cardId, socket: 1 }, { kind: 'card', id: cardId, socket: 2 }] });
    app._applyProcessorState(st);
    if (!opts.box) {
        const w = window.__fl.layer('W');
        const wasLocked = w.locked;
        w.locked = false;
        let refused = null;
        await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
                                     { layerId: String(w.id), cardId },
                                     (d) => { refused = d; return true; }, 'Place');
        if (refused) throw new Error('place-overflow refused: ' + JSON.stringify(refused));
        w.locked = wasLocked;
        if (wasLocked) await app.updateLayers([w]);
    }
    await app.refreshProcessors();
    app.resetHistory('Initial State');
    return { pid, cardId, boxId, boxSocket, fiberId, layerId: window.__fl.layer('W').id };
}"""


def _raw_card(card_id, project=None):
    p = project if project is not None else _server()
    for proc in p.get('processors') or []:
        for slot in proc.get('slots') or []:
            card = (slot or {}).get('card')
            if card and card.get('id') == card_id:
                return card
    return None


def _cables(card_id, project=None):
    return sorted(int(k) for k in ((_raw_card(card_id, project) or {}).get('portCables') or {}))


def _pins(project=None):
    p = project if project is not None else _server()
    return sorted((x['cardId'], x['port']) for x in (p.get('port_assignments') or {}).get('pins') or [])


def test_releasing_a_port_forgets_its_port_cable_and_keeps_its_snake(page):
    """W's port 1 (socket 1) released - the run's Clear port: socket 1's 25'
    goes, on the server and in the browser's tree; sockets 2 and 3 keep
    theirs, and the snake on 1-2 keeps its 150'. A cable on a socket
    nothing is on (9) does not print in the binder. Undo puts socket 1's
    cable back with the pin."""
    pg = page
    ids = pg.evaluate(DATA_JS, {'card': CARD})
    assert _pins() == [(ids['cardId'], n) for n in (1, 2, 3, 4)], _pins()
    texts = pg.evaluate("() => window.__fl.binderTexts()")
    assert any("25'" in str(t) for t in texts)
    assert not [t for t in texts if "99'" in str(t)], 'a cable on an empty socket printed'
    pg.evaluate("""(id) => window.app._assignmentRequest('/api/port-assignments/unpin', 'POST',
        { layerId: String(id), index: 0 }, null, 'Release Port')""", ids['layerId'])
    srv = _wait_server(pg, lambda p: (ids['cardId'], 1) not in _pins(p))
    assert _cables(ids['cardId'], srv) == [2, 3, 9]
    assert [s['ft'] for s in srv.get('snakes') or []] == [150]
    assert pg.evaluate("""(cid) => {
        for (const p of window.app.project.processors || []) for (const s of p.slots || [])
            if (s.card && s.card.id === cid) return Object.keys(s.card.portCables || {}).map(Number);
        return null; }""", ids['cardId']) == [2, 3, 9]
    pg.evaluate("() => window.app.undo()")
    srv = _wait_server(pg, lambda p: (ids['cardId'], 1) in _pins(p))
    assert _cables(ids['cardId'], srv) == [1, 2, 3, 9]


def test_a_locked_screens_port_keeps_its_cable(page):
    """W locked: its port's release is refused (and named), so socket 1's
    cable stays where it is."""
    pg = page
    ids = pg.evaluate(DATA_JS, {'card': CARD, 'locked': True})
    assert (ids['cardId'], 1) in _pins()
    pg.evaluate("""(id) => window.app._assignmentRequest('/api/port-assignments/unpin', 'POST',
        { layerId: String(id), index: 0 }, null, 'Release Port')""", ids['layerId'])
    _settle(pg)
    assert (ids['cardId'], 1) in _pins()
    assert _cables(ids['cardId']) == [1, 2, 3, 9]


def test_removing_a_card_or_a_processor_takes_its_cables_and_snakes(page):
    """The card out of its slot: every port cable it held goes with it, and
    the snake that lived only on it goes too. Then the processor itself,
    on a fresh one: the same."""
    pg = page
    ids = pg.evaluate(DATA_JS, {'card': CARD})
    pg.evaluate("""(pid) => window.app._processorRequest(`/api/processors/${pid}/slots/0`, 'PUT',
        { deviceId: null }, 'Remove Card')""", ids['pid'])
    srv = _wait_server(pg, lambda p: _raw_card(ids['cardId'], p) is None)
    assert _raw_card(ids['cardId'], srv) is None
    assert not srv.get('snakes'), srv.get('snakes')
    assert pg.evaluate("() => (window.app.project.snakes || []).length") == 0
    ids = pg.evaluate(DATA_JS, {'card': CARD})
    pg.evaluate("""(pid) => window.app._processorRequest(`/api/processors/${pid}`, 'DELETE',
        undefined, 'Remove Processor')""", ids['pid'])
    srv = _wait_server(pg, lambda p: not p.get('processors'))
    assert not srv.get('processors') and not srv.get('snakes')


def test_removing_a_box_takes_its_port_cables_and_fiber_runs(page):
    """A CVT10 on the card with a 15' cable on its first socket and a 300'
    TAC on its link. Removing the box takes the box's cable and the TAC."""
    pg = page
    ids = pg.evaluate(DATA_JS, {'card': CARD, 'box': True})
    box = next(b for b in _raw_card(ids['cardId'])['cvts'] if b['id'] == ids['boxId'])
    assert sorted(box.get('portCables') or {}) == [str(ids['boxSocket'])]
    assert [c.get('ft') for c in _server().get('fiberCables') or []] == [300]
    pg.evaluate("""([pid, bid]) => window.app._processorRequest(`/api/processors/${pid}/cvts/${bid}`,
        'DELETE', undefined, 'Remove Box')""", [ids['pid'], ids['boxId']])
    srv = _wait_server(pg, lambda p: not ((_raw_card(ids['cardId'], p) or {}).get('cvts')))
    assert not srv.get('fiberCables'), srv.get('fiberCables')
    assert '15' not in json.dumps(_raw_card(ids['cardId'], srv).get('cvts') or [])
    assert pg.evaluate("() => (window.app.project.fiberCables || []).length") == 0



# ── Deleting a screen ─────────────────────────────────────────────────────

# W (four ports) on sockets 1-4 of the H9's card, as in DATA_JS. V (one
# port) placed on socket 2 on top of W - a shared socket, a hot spare - and
# X (one port) on socket 5. Port cables on 1, 2, 3, 5 and on 9 (nothing
# there); a snake on 1-2. opts.group: W and X are one group (routing off,
# so each cables on its own). opts.canvas: W and X live on a second
# canvas, V on the first.
SHARED_JS = r"""async (opts) => {
    opts = opts || {};
    const app = window.app, fl = window.__fl, j = fl.j.bind(fl);
    const scr = (id, name, x, cols, rows) => fl.screen({ id, name, offset_x: x,
        columns: cols, rows, cabinet_width: 256, cabinet_height: 256 });
    const W = scr(1, 'W', 0, 8, 4), V = scr(2, 'V', 3000, 2, 2), X = scr(3, 'X', 4000, 2, 2);
    W.locked = !!opts.locked;
    const project = { name: 'Delete screen', cableUnit: 'ft', distros: [], layers: [W, V, X] };
    if (opts.beach) {
        project.beaches = [{ id: 'b1', name: 'SL' }];
        W.beachId = X.beachId = 'b1';
    }
    if (opts.group) {
        W.group_id = X.group_id = 'g1';
        project.groups = [{ id: 'g1', name: 'G1', layer_ids: [1, 3], routeDataAsOne: false }];
    }
    await fl.open(project);
    if (opts.canvas) {
        const p = await j('GET', '/api/project');
        const second = Object.assign(JSON.parse(JSON.stringify(p.canvases[0])),
            { id: 'canvas_del', name: 'Second', workspace_x: 6000 });
        p.canvases.push(second);
        p.layers.forEach(l => { if (l.name !== 'V') l.canvas_id = 'canvas_del'; });
        await fl.open(p);
    }
    const procs = await j('POST', '/api/processors', { deviceId: 'novastar-h9' });
    const pid = procs.resolved[procs.resolved.length - 1].id;
    let st = await j('PUT', `/api/processors/${pid}/slots/0`, { deviceId: opts.card });
    const cardId = st.resolved.find(p => p.id === pid).slots[0].card.id;
    await j('PUT', `/api/processors/${pid}/cards/${cardId}`, { portCables:
        { 1: { ft: 25 }, 2: { ft: 50 }, 3: { ft: 75 }, 5: { ft: 40 }, 9: { ft: 99 } } });
    st = await j('POST', '/api/snakes', { ft: 150, members: [
        { kind: 'card', id: cardId, socket: 1 }, { kind: 'card', id: cardId, socket: 2 }] });
    app._applyProcessorState(st);
    const id = (n) => String(fl.layer(n).id);
    const ask = async (url, body) => {
        let refused = null;
        await app._assignmentRequest(url, 'POST', body, (d) => { refused = d; return true; }, 'Place');
        if (refused) throw new Error(url + ' refused: ' + JSON.stringify(refused));
    };
    const w = fl.layer('W');
    w.locked = false;
    await ask('/api/port-assignments/place-overflow', { layerId: id('W'), cardId });
    await ask('/api/port-assignments/place',
              { layerId: id('V'), index: 0, cardId, port: 2, confirm: true });
    await ask('/api/port-assignments/place', { layerId: id('X'), index: 0, cardId, port: 5 });
    if (opts.locked) { w.locked = true; await app.updateLayers([w]); }
    await app.refreshProcessors();
    app.resetHistory('Initial State');
    return { pid, cardId, W: fl.layer('W').id, V: fl.layer('V').id, X: fl.layer('X').id };
}"""

SHARED_ALL = [1, 2, 3, 5, 9]


def _shared(pg, **opts):
    ids = pg.evaluate(SHARED_JS, dict({'card': CARD}, **opts))
    card = ids['cardId']
    assert _pins() == sorted([(card, 1), (card, 2), (card, 2), (card, 3), (card, 4),
                              (card, 5)]), _pins()
    assert _cables(card) == SHARED_ALL
    return ids


def _client_cables(pg, card_id):
    return pg.evaluate("""(cid) => {
        for (const p of window.app.project.processors || []) for (const s of p.slots || [])
            if (s.card && s.card.id === cid) return Object.keys(s.card.portCables || {}).map(Number)
                .sort((a, b) => a - b);
        return null; }""", card_id)


def _top_action(pg, action):
    pg.wait_for_function(
        "(a) => { const h = window.app.history[window.app.historyIndex]; return !!h && h.action === a; }",
        arg=action)


def _assert_kept_after_delete(card, srv, expect):
    assert _cables(card, srv) == expect, _cables(card, srv)
    assert [s['ft'] for s in srv.get('snakes') or []] == [150], 'the snake is the socket\'s loom'
    assert sorted(m['socket'] for m in srv['snakes'][0]['members']) == [1, 2]


def _undo_restores(pg, ids, layer_names):
    card = ids['cardId']
    pg.evaluate("() => window.app.undo()")
    srv = _wait_server(pg, lambda p: _cables(card, p) == SHARED_ALL
                       and all(_srv_layer(n, p) for n in layer_names))
    assert _cables(card, srv) == SHARED_ALL
    assert all(_srv_layer(n, srv) for n in layer_names)
    assert _pins(srv) == sorted([(card, 1), (card, 2), (card, 2), (card, 3), (card, 4),
                                 (card, 5)]), _pins(srv)
    pg.wait_for_function("(cid) => { for (const p of window.app.project.processors || [])"
                         " for (const s of p.slots || []) if (s.card && s.card.id === cid)"
                         " return Object.keys(s.card.portCables || {}).length === 5;"
                         " return false; }", arg=card)
    assert _client_cables(pg, card) == SHARED_ALL


def test_deleting_a_screen_forgets_the_port_cables_on_its_sockets(page):
    """Delete W (the Delete key's path): the cables on sockets only W held
    (1, 3) go - on the server and in the browser's tree. X's socket 5 and
    the empty socket 9 keep theirs, and the snake on 1-2 keeps its 150'."""
    pg = page
    ids = _shared(pg)
    card = ids['cardId']
    pg.evaluate("""(id) => { const app = window.app, W = window.__fl.layer('W');
        app.selectLayer(W); app.selectedLayerIds = new Set([id]); app.deleteCurrentLayer(); }""",
                ids['W'])
    _top_action(pg, 'Delete Layer')
    srv = _wait_server(pg, lambda p: _srv_layer('W', p) is None and 1 not in _cables(card, p))
    assert _srv_layer('W', srv) is None
    _assert_kept_after_delete(card, srv, [2, 5, 9])
    assert _client_cables(pg, card) == [2, 5, 9]
    assert _pins(srv) == [(card, 2), (card, 5)]


def test_a_socket_another_screen_still_claims_keeps_its_cable(page):
    """Socket 2 is W's and V's (V placed on top of W). Deleting W (the
    menu's Delete) leaves V on it, so its 50' stays; deleting V after it
    lets socket 2 go, and the 50' goes then."""
    pg = page
    ids = _shared(pg)
    card = ids['cardId']
    pg.evaluate("(id) => window.app.deleteLayer(id)", ids['W'])
    _top_action(pg, 'Delete Layer')
    srv = _wait_server(pg, lambda p: _srv_layer('W', p) is None and 1 not in _cables(card, p))
    _assert_kept_after_delete(card, srv, [2, 5, 9])
    assert (card, 2) in _pins(srv)
    steps = pg.evaluate("() => window.app.historyIndex")
    pg.evaluate("(id) => window.app.deleteLayer(id)", ids['V'])
    pg.wait_for_function("(n) => window.app.historyIndex > n", arg=steps)
    srv = _wait_server(pg, lambda p: _srv_layer('V', p) is None and 2 not in _cables(card, p))
    _assert_kept_after_delete(card, srv, [5, 9])
    assert _client_cables(pg, card) == [5, 9]


def test_undoing_a_screen_delete_brings_back_the_screen_and_its_cables(page):
    """Delete W, then Ctrl+Z: W, its pins and the cables on 1 and 3 all
    come back - the server's copy and the browser's."""
    pg = page
    ids = _shared(pg)
    card = ids['cardId']
    pg.evaluate("(id) => window.app.deleteLayer(id)", ids['W'])
    _top_action(pg, 'Delete Layer')
    srv = _wait_server(pg, lambda p: _srv_layer('W', p) is None and 1 not in _cables(card, p))
    assert _cables(card, srv) == [2, 5, 9], 'the delete should have taken 1 and 3 first'
    _undo_restores(pg, ids, ['W', 'V', 'X'])


def test_a_multi_select_delete_forgets_every_deleted_screens_cables(page):
    """W and X selected and deleted together: 1, 3 and 5 go; V's shared
    socket 2 and the empty 9 stay. Undo brings both screens and the cables
    back."""
    pg = page
    ids = _shared(pg)
    card = ids['cardId']
    pg.evaluate("""([w, x]) => { const app = window.app;
        app.selectLayer(window.__fl.layer('W'));
        app.selectedLayerIds = new Set([w, x]); app.deleteCurrentLayer(); }""",
                [ids['W'], ids['X']])
    _top_action(pg, 'Delete Layer')
    srv = _wait_server(pg, lambda p: _srv_layer('X', p) is None and 5 not in _cables(card, p))
    assert _srv_layer('W', srv) is None and _srv_layer('X', srv) is None
    _assert_kept_after_delete(card, srv, [2, 9])
    assert _client_cables(pg, card) == [2, 9]
    _undo_restores(pg, ids, ['W', 'V', 'X'])


def test_deleting_a_group_forgets_its_members_cables(page):
    """W and X are one group; Delete Group takes both, and 1, 3 and 5 go
    with them; socket 2 (V still on it) and 9 stay. Undo brings the group
    and the cables back."""
    pg = page
    ids = _shared(pg, group=True)
    card = ids['cardId']
    assert pg.evaluate("() => window.app.deleteGroup('g1')") is True
    _top_action(pg, 'Delete Group')
    srv = _wait_server(pg, lambda p: _srv_layer('W', p) is None and 5 not in _cables(card, p))
    assert not srv.get('groups'), srv.get('groups')
    _assert_kept_after_delete(card, srv, [2, 9])
    assert _client_cables(pg, card) == [2, 9]
    assert 'release_screens_ports' not in srv, 'the marker is never stored'
    # the resolved tree the pull sheet and the binder read catches up
    pg.wait_for_function("() => window.app._processorsRaw"
                         " === JSON.stringify(window.app.project.processors || [])")
    _undo_restores(pg, ids, ['W', 'V', 'X'])
    assert [g['id'] for g in _server().get('groups') or []] == ['g1']


def test_deleting_a_canvas_forgets_its_screens_cables(page):
    """W and X live on a second canvas; deleting it takes them, and 1, 3
    and 5 go; V (on the first canvas) keeps socket 2's cable. Undo brings
    the canvas, the screens and the cables back."""
    pg = page
    ids = _shared(pg, canvas=True)
    card = ids['cardId']
    pg.evaluate("() => window.app.deleteCanvas('canvas_del')")
    _top_action(pg, 'Delete Canvas')
    srv = _wait_server(pg, lambda p: _srv_layer('W', p) is None and 5 not in _cables(card, p))
    assert [c['id'] for c in srv['canvases']] != [] and 'canvas_del' not in [c['id'] for c in srv['canvases']]
    _assert_kept_after_delete(card, srv, [2, 9])
    assert _client_cables(pg, card) == [2, 9]
    _undo_restores(pg, ids, ['W', 'V', 'X'])


def test_a_locked_screen_is_not_deleted_and_keeps_its_cables(page):
    """W locked: Delete is refused (and named), so every cable stays."""
    pg = page
    ids = _shared(pg, locked=True)
    card = ids['cardId']
    pg.evaluate("(id) => window.app.deleteLayer(id)", ids['W'])
    pg.evaluate("""(id) => { const app = window.app; app.selectLayer(window.__fl.layer('W'));
        app.selectedLayerIds = new Set([id]); app.deleteCurrentLayer(); }""", ids['W'])
    _settle(pg)
    assert _srv_layer('W') is not None
    assert _cables(card) == SHARED_ALL
    assert pg.evaluate("() => window.app.history[window.app.historyIndex].action") == 'Initial State'


def test_opening_a_file_whose_pins_name_a_gone_screen_keeps_every_cable(page):
    """A hand-edited file still holds W's pins but not W. Opening it drops
    the dead pins (as it always has) and forgets no cable: the load funnel
    changes nothing it carries."""
    pg = page
    ids = _shared(pg)
    card = ids['cardId']
    pg.evaluate("""async () => {
        const p = await window.__fl.j('GET', '/api/project');
        p.layers = p.layers.filter(l => l.name !== 'W');
        await window.__fl.open(p);
    }""")
    _settle(pg)
    srv = _server()
    assert _srv_layer('W', srv) is None
    assert (card, 1) not in _pins(srv), 'the dead pins go on load, as before'
    assert _cables(card, srv) == SHARED_ALL



# ── Deleting a screen: its pull-sheet edits ──────────────────────────────

def _edit_rows(pg, edits):
    """A note on each (position key, row key), the sheet's own setter, and
    a free row on beach:b1; waits until the server holds them all."""
    pg.evaluate("""(edits) => {
        const app = window.app;
        app._circuitTailCache = null;
        const list = app.buildPullList();
        for (const [pk, key, notes] of edits) {
            const pos = list.positions.find(p => app.pullPositionKey(p) === pk);
            const row = pos && pos.rows.find(r => app.pullRowKey(r) === key);
            if (!row) throw new Error('no row ' + pk + ' ' + key);
            app.setPullSheetRowEdit(pk, key, { notes }, row);
        }
    }""", edits)
    want = sorted((pk, key) for pk, key, _ in edits)
    srv = _wait_server(pg, lambda p: _srv_edits(p) == want)
    assert _srv_edits(srv) == want, _srv_edits(srv)


def _srv_edits(project=None):
    p = project if project is not None else _server()
    out = []
    for pk, pos in ((p.get('pullSheetEdits') or {}).get('positions') or {}).items():
        out.extend((pk, r['key']) for r in (pos or {}).get('rows') or [])
    return sorted(out)


def _srv_added(project=None):
    p = project if project is not None else _server()
    return {pk: [a.get('type') for a in (pos or {}).get('added') or []]
            for pk, pos in ((p.get('pullSheetEdits') or {}).get('positions') or {}).items()
            if (pos or {}).get('added')}


def _client_edits(pg):
    return sorted(tuple(x) for x in pg.evaluate("""() => {
        const out = [];
        const st = (window.app.project.pullSheetEdits || {}).positions || {};
        for (const [pk, pos] of Object.entries(st))
            for (const r of (pos && pos.rows) || []) out.push([pk, r.key]);
        return out; }"""))


# W and X on beach SL, V loose: W's own runs print as SL's 25' and 75'
# Ether-con, and SL's 6' Data Jump is W's AND X's.
W_ROW = ('beach:b1', "Ether-con|25'", 'W run')
SHARED_ROW = ('beach:b1', "Data Jump|6'", 'both walls')
V_ROW = ('layer:2', "Ether-con|50'", 'spare')


def _beach_with_edits(pg):
    ids = _shared(pg, beach=True)
    _edit_rows(pg, [W_ROW, SHARED_ROW, V_ROW])
    pg.evaluate("() => window.app.addPullSheetRow('beach:b1', { type: 'Gaff', length: 'EA', qty: 2 })")
    _wait_server(pg, lambda p: _srv_added(p) == {'beach:b1': ['Gaff']})
    assert _srv_added() == {'beach:b1': ['Gaff']}
    return ids


def test_deleting_a_screen_drops_the_pull_sheet_edits_on_its_rows(page):
    """A note on W's 25' run. Delete W: the row is off the sheet, and the
    note goes with it - in the browser and on the server."""
    pg = page
    ids = _beach_with_edits(pg)
    steps = pg.evaluate("() => window.app.historyIndex")
    pg.evaluate("(id) => window.app.deleteLayer(id)", ids['W'])
    pg.wait_for_function("(n) => window.app.historyIndex > n", arg=steps)
    srv = _wait_server(pg, lambda p: (W_ROW[0], W_ROW[1]) not in _srv_edits(p))
    assert (W_ROW[0], W_ROW[1]) not in _srv_edits(srv), _srv_edits(srv)
    assert (W_ROW[0], W_ROW[1]) not in _client_edits(pg)
    assert pg.evaluate("() => window.app.pullSheetStaleEdits()") == []


def test_an_edit_on_a_row_a_surviving_screen_still_prints_stays(page):
    """SL's 6' Data Jump is W's and X's: deleting W leaves X printing it,
    so its note stays. V's own note and SL's free row are untouched."""
    pg = page
    ids = _beach_with_edits(pg)
    steps = pg.evaluate("() => window.app.historyIndex")
    pg.evaluate("(id) => window.app.deleteLayer(id)", ids['W'])
    pg.wait_for_function("(n) => window.app.historyIndex > n", arg=steps)
    srv = _wait_server(pg, lambda p: (W_ROW[0], W_ROW[1]) not in _srv_edits(p))
    assert _srv_edits(srv) == sorted([(SHARED_ROW[0], SHARED_ROW[1]), (V_ROW[0], V_ROW[1])])
    assert _srv_added(srv) == {'beach:b1': ['Gaff']}
    assert _client_edits(pg) == _srv_edits(srv)


def test_undoing_a_screen_delete_brings_back_its_pull_sheet_edits(page):
    """Delete W, then Ctrl+Z: W's note is back with W, on the server too."""
    pg = page
    ids = _beach_with_edits(pg)
    full = _srv_edits()
    steps = pg.evaluate("() => window.app.historyIndex")
    pg.evaluate("(id) => window.app.deleteLayer(id)", ids['W'])
    pg.wait_for_function("(n) => window.app.historyIndex > n", arg=steps)
    srv = _wait_server(pg, lambda p: (W_ROW[0], W_ROW[1]) not in _srv_edits(p))
    assert (W_ROW[0], W_ROW[1]) not in _srv_edits(srv), 'the delete should have dropped it first'
    pg.evaluate("() => window.app.undo()")
    srv = _wait_server(pg, lambda p: _srv_edits(p) == full and _srv_layer('W', p) is not None)
    assert _srv_edits(srv) == full
    assert _srv_layer('W', srv) is not None
    rows = srv['pullSheetEdits']['positions']['beach:b1']['rows']
    assert {'key': W_ROW[1], 'notes': W_ROW[2]} in rows, rows
    assert _client_edits(pg) == full


@pytest.mark.parametrize('how', ['multi', 'group', 'canvas'])
def test_every_delete_path_drops_the_gone_rows_edits_and_undo_restores_them(page, how):
    """W and X deleted together - selected, as their group, or with their
    canvas: a note on a row only they printed goes, on the server too; V's
    note stays; undo brings the note back."""
    pg = page
    ids = _shared(pg, **({'multi': {}, 'group': {'group': True},
                          'canvas': {'canvas': True}}[how]))
    pk = {'multi': 'layer:1', 'group': 'g1', 'canvas': 'layer:1'}[how]
    _edit_rows(pg, [(pk, "Ether-con|25'", 'W run'), V_ROW])
    full = _srv_edits()
    steps = pg.evaluate("() => window.app.historyIndex")
    if how == 'multi':
        pg.evaluate("""([w, x]) => { const app = window.app;
            app.selectLayer(window.__fl.layer('W'));
            app.selectedLayerIds = new Set([w, x]); app.deleteCurrentLayer(); }""",
                    [ids['W'], ids['X']])
    elif how == 'group':
        assert pg.evaluate("() => window.app.deleteGroup('g1')") is True
    else:
        pg.evaluate("() => window.app.deleteCanvas('canvas_del')")
    pg.wait_for_function("(n) => window.app.historyIndex > n", arg=steps)
    srv = _wait_server(pg, lambda p: _srv_edits(p) == [(V_ROW[0], V_ROW[1])])
    assert _srv_layer('W', srv) is None and _srv_layer('X', srv) is None
    assert _srv_edits(srv) == [(V_ROW[0], V_ROW[1])], _srv_edits(srv)
    assert _client_edits(pg) == [(V_ROW[0], V_ROW[1])]
    pg.evaluate("() => window.app.undo()")
    srv = _wait_server(pg, lambda p: _srv_edits(p) == full and _srv_layer('W', p) is not None)
    assert _srv_edits(srv) == full
    assert _client_edits(pg) == full



# The order CI caught once (2026-10-18). A processor read set off before the
# undo comes back after it, so the page drops it and reads again - but the
# undo's restore PUT has not landed yet, and the server answers that second
# read with the tree being undone. The PUT is held in the page until the
# second read has been answered; every answer is the real server's.
LATE_RESTORE_JS = """async () => {
    const app = window.app, orig = window.fetch;
    let letRead, letPut, readHeld = false, reads = 0;
    const read = new Promise(r => { letRead = r; });
    const put = new Promise(r => { letPut = r; });
    window.fetch = (url, opts) => {
        const method = (opts && opts.method) || 'GET';
        if (url === '/api/processors' && method === 'GET') {
            reads++;
            if (!readHeld) { readHeld = true; return read.then(() => orig(url, opts)); }
        }
        if (url === '/api/project' && method === 'PUT') {
            return put.then(() => orig(url, opts));
        }
        return orig(url, opts);
    };
    try {
        app.refreshProcessors();
        app.undo();
        letRead();
        await new Promise(r => setTimeout(r, 300));
        letPut();
        await new Promise(r => setTimeout(r, 300));
        await app._layerSavesSettled();
    } finally {
        window.fetch = orig;
    }
    return reads;
}"""


def test_an_undo_whose_restore_lands_late_still_brings_the_cables_back(page):
    """The restore PUT an undo sends can land after the processor read the
    same undo sets off. That read describes the server before the restore;
    the page took it and never read again, so the server held all five
    cables and the page three."""
    pg = page
    ids = _shared(pg)
    card = ids['cardId']
    pg.evaluate("(id) => window.app.deleteLayer(id)", ids['W'])
    _top_action(pg, 'Delete Layer')
    _wait_server(pg, lambda p: _srv_layer('W', p) is None and 1 not in _cables(card, p))
    assert pg.evaluate(LATE_RESTORE_JS) >= 2, 'the dropped read should be read again'
    srv = _wait_server(pg, lambda p: _cables(card, p) == SHARED_ALL)
    assert _cables(card, srv) == SHARED_ALL
    pg.wait_for_function("(cid) => { for (const p of window.app.project.processors || [])"
                         " for (const s of p.slots || []) if (s.card && s.card.id === cid)"
                         " return Object.keys(s.card.portCables || {}).length === 5;"
                         " return false; }", arg=card, timeout=5000)
    assert _client_cables(pg, card) == SHARED_ALL
