"""Clear multis is a reset; a circuit's cable stays with its cabinets.

The owner, 2026-11-04: "when clearing multi on distros it doesnt reset the
naming on the screens". Asked what the names should become, "so default
they are 1-say 10. they just go back to their original numbers". And: "when
using balance, let's say I have an extension on circuit six, but then after
balancing it goes to circuit five. The extension needs to follow that
move".

Pinned here:

- Clear Distro puts every screen it cleared back on its own label template
  (S1-1 ... from S1-#), on the canvas labels and on the pull sheet, and
  forgets every circuit cable those screens have that no fed circuit
  carries afterwards. That includes a cable left under a circuit number
  the screen no longer has: the owner's log showed Clear Distro leave one
  behind on two screens, where it would come back on the next circuit to
  take that number. A screen on another distro keeps its names, its
  numbers and its cables. One undo puts everything back.
- Balance and its reset move a circuit to other sockets of its multi, so
  its label changes (SL1-6 becomes SL1-5). Its cable is stored by the
  circuit, which is the same cabinets, so the cable moves with it on the
  canvas, the tray and the pull sheet. One undo puts it back.

Every test checks the browser AND the server's project, waits on real
conditions, and leaves the shared server project as it found it
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
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_function("() => window.canvasRenderer && window.canvasRenderer.viewMode === 'power'")
    yield pg
    assert errors == [], errors
    context.close()


# 208V x 6.25A (80% packing: 5A) / 208W = five cabinets a circuit, tl-v
# organized, five rows: a screen's `columns` IS its circuit count.
#   A  7 wide on SL: multi 1 (circuits 1-6) is SL1, multi 2 (circuit 7) SL2.
#      A 10' cable on circuit 2, and a 25' one left under circuit 9, a
#      number A has no circuit for.
#   B  3 wide on SL: SL3.
#   C  3 wide on SR: SR1, a 10' cable on circuit 1.
HELPERS_JS = r"""
window.__cm = {
    screen(o) {
        o = Object.assign({
            type: 'screen', visible: true, locked: false,
            columns: 3, rows: 5, cabinet_width: 128, cabinet_height: 128,
            offset_x: 0, offset_y: 0, panel_weight: 20, weight_unit: 'kg',
            panelWatts: 208, powerVoltage: 208, powerAmperage: 6.25,
            processorType: 'novastar-armor', bitDepth: 8, frameRate: 60, lowLatency: false,
            flowPattern: 'tl-h', portMappingMode: 'organized',
            powerFlowPattern: 'tl-v', powerOrganized: true, powerMaximize: false,
            powerLabelTemplate: 'S1-#',
            group_id: null, powerSocaDistro: {}, powerSocaNumber: {},
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
    clearProject() {
        const cab = (ft) => ({ ft, connector: null });
        return {
            name: 'Clear multis', cableUnit: 'ft',
            distros: [
                { id: 'd1', name: 'SL', ratingA: 400, system: '120/208', voltage: 208, phase: 3 },
                { id: 'd2', name: 'SR', ratingA: 400, system: '120/208', voltage: 208, phase: 3 },
            ],
            layers: [
                this.screen({ id: 1, name: 'A', columns: 7, offset_x: 0,
                    powerSocaDistro: { 1: 'd1', 2: 'd1' },
                    powerSocaLengths: { 1: '100' },
                    powerCircuitCables: { 2: cab(10), 9: cab(25) } }),
                this.screen({ id: 2, name: 'B', offset_x: 1200,
                    powerSocaDistro: { 1: 'd1' } }),
                this.screen({ id: 3, name: 'C', offset_x: 1800,
                    powerSocaDistro: { 1: 'd2' }, powerSocaLengths: { 1: '150' },
                    powerCircuitCables: { 1: cab(10) } }),
            ],
        };
    },
    // One five-circuit multi on SL, its circuits on sockets 1-4 and 6, so
    // circuit 5 reads SL1-6 and carries a 25' cable (the owner's "circuit
    // six"). B sits on the same distro with five circuits on 1-5, so the
    // legs are uneven and Balance has something to do.
    balanceProject() {
        return {
            name: 'Balance cables', cableUnit: 'ft',
            distros: [
                { id: 'd1', name: 'SL', ratingA: 400, system: '120/208', voltage: 208, phase: 3 },
            ],
            layers: [
                this.screen({ id: 1, name: 'A', columns: 5, offset_x: 0,
                    powerSocaDistro: { 1: 'd1' },
                    powerSocaPhasePos: { 1: [1, 2, 3, 4, 6] },
                    powerCircuitCables: { 5: { ft: 25, connector: null } } }),
                this.screen({ id: 2, name: 'B', columns: 5, offset_x: 1200,
                    powerSocaDistro: { 1: 'd1' },
                    powerCircuitCables: { 1: { ft: 10, connector: null } } }),
            ],
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
        app.dedupeProjectLayers('clear_multis_reset');
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
    inflight() {
        const s = window.app._inflightLayerPuts;
        return !s || s.size === 0;
    },
    // Every circuit of a screen as the canvas names it: number, label,
    // first cabinet (row,col) and the cable tag the canvas draws on it.
    circuits(name) {
        const app = window.app;
        app._circuitTailCache = null;
        const l = this.layer(name);
        return app.screenCircuits(l).map(c => {
            const head = c.panels && c.panels[0];
            const tag = app.printedCircuitCable(l, c.num);
            return { num: c.num, label: app.getPowerCircuitLabel(l, c.num),
                     head: head ? `${head.row},${head.col}` : null,
                     cable: tag ? tag.text : null };
        });
    },
    stores(name) {
        const l = this.layer(name);
        const pick = (k) => JSON.parse(JSON.stringify(l[k] || {}));
        return { distro: pick('powerSocaDistro'), number: pick('powerSocaNumber'),
                 names: pick('powerSocaNames'), lengths: pick('powerSocaLengths'),
                 pos: pick('powerSocaPhasePos'), cables: pick('powerCircuitCables'),
                 overrides: pick('powerLabelOverrides') };
    },
    // The pull sheet's circuit cable rows: [position, type, length, label].
    cableRows() {
        const app = window.app;
        app._circuitTailCache = null;
        return app.buildPullList().positions.flatMap(p => p.rows
            .filter(r => r.type === 'TRUE1' && r.length)
            .map(r => [p.name, r.type, r.length, r.label]));
    },
    // Every multi label the pull sheet prints (Multi and breakout rows).
    multiRows() {
        const app = window.app;
        app._circuitTailCache = null;
        return app.buildPullList().positions.flatMap(p => p.rows
            .filter(r => r.type === 'Multi')
            .map(r => [p.name, r.label]));
    },
    // The labels the canvas really draws, read off its own calls.
    drawnLabels() {
        const app = window.app;
        const seen = [];
        const orig = app.getPowerCircuitLabel;
        app.getPowerCircuitLabel = function (layer, num) {
            const out = orig.call(this, layer, num);
            seen.push(`${layer.name}:${out}`);
            return out;
        };
        try {
            app._circuitTailCache = null;
            window.canvasRenderer.render();
        } finally {
            app.getPowerCircuitLabel = orig;
        }
        return [...new Set(seen)].sort();
    },
    distroMembers(distroId) {
        const app = window.app;
        app._circuitTailCache = null;
        const members = [];
        for (const l of app.project.layers) {
            if ((l.type || 'screen') !== 'screen') continue;
            for (const rec of app._powerNaming(l).socas.values()) {
                if (rec.distroId === distroId) members.push({ layerId: l.id, soca: rec.index });
            }
        }
        return members;
    },
};
"""


def _server():
    import app as app_module
    return app_module.current_project


def _srv_layer(name, project):
    return next((l for l in (project.get('layers') or []) if l.get('name') == name), None)


def _wait_server(pg, ok, timeout_ms=8000):
    return settled(pg, lambda: copy.deepcopy(_server()), ok, timeout_ms)


def _settle(pg):
    pg.wait_for_function('() => window.__cm.inflight()')


def _open(pg, which):
    pg.evaluate(f"() => window.__cm.open(window.__cm.{which}())")
    _settle(pg)


def _labels(pg, name):
    return [c['label'] for c in pg.evaluate("(n) => window.__cm.circuits(n)", name)]


def _circuits(pg, name):
    return pg.evaluate("(n) => window.__cm.circuits(n)", name)


def _stores(pg, name):
    return pg.evaluate("(n) => window.__cm.stores(n)", name)


def _undo(pg):
    pg.evaluate("() => window.app.undo()")
    _settle(pg)


# ── Clear multis is a reset ───────────────────────────────────────────────

def _clear_distro_from_tray(pg, distro_id, title):
    """Right-click the distro's header in the tray and pick Clear <name>."""
    # The tray rebuilds itself a macrotask after an open, so the header is
    # found and right-clicked in one tick of the page, on the live element.
    pg.wait_for_function(
        "(id) => !!document.querySelector(`[data-lrd-distro=\"${id}\"] .hw-dock-distro-head`)",
        arg=distro_id)
    pg.evaluate("""(id) => {
        const head = document.querySelector(`[data-lrd-distro="${id}"] .hw-dock-distro-head`);
        head.scrollIntoView({ block: 'center' });
        const r = head.getBoundingClientRect();
        head.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true,
            button: 2, clientX: r.left + 20, clientY: r.top + r.height / 2 }));
    }""", distro_id)
    item = pg.get_by_text(f'Clear {title}', exact=True)
    item.first.wait_for(state='visible')
    item.first.click()
    _settle(pg)


def test_clear_distro_puts_names_back_on_each_screens_template(page):
    """Clear SL from the tray: A and B read S1-1 ... on their own template
    again, on the canvas and the pull sheet; C on SR is untouched."""
    pg = page
    _open(pg, 'clearProject')
    before = {n: _labels(pg, n) for n in ('A', 'B', 'C')}
    assert before == {
        'A': ['SL1-1', 'SL1-2', 'SL1-3', 'SL1-4', 'SL1-5', 'SL1-6', 'SL2-1'],
        'B': ['SL3-1', 'SL3-2', 'SL3-3'],
        'C': ['SR1-1', 'SR1-2', 'SR1-3'],
    }, before
    c_before = _stores(pg, 'C')

    _clear_distro_from_tray(pg, 'd1', 'SL')

    after = {n: _labels(pg, n) for n in ('A', 'B', 'C')}
    assert after == {
        'A': ['S1-1', 'S1-2', 'S1-3', 'S1-4', 'S1-5', 'S1-6', 'S2-1'],
        'B': ['S1-1', 'S1-2', 'S1-3'],
        'C': ['SR1-1', 'SR1-2', 'SR1-3'],
    }, after
    drawn = pg.evaluate("() => window.__cm.drawnLabels()")
    assert not any(t.startswith(('A:SL', 'B:SL')) for t in drawn), drawn
    assert 'C:SR1-1' in drawn, drawn
    # the pull sheet: no SL multi anywhere, C's SR1 still listed
    multis = pg.evaluate("() => window.__cm.multiRows()")
    assert all('SL' not in str(label) for _, label in multis), multis
    assert any('SR1' in str(label) for _, label in multis), multis
    for name in ('A', 'B'):
        s = _stores(pg, name)
        assert s['distro'] == {} and s['number'] == {} and s['names'] == {}, (name, s)
    assert _stores(pg, 'C') == c_before
    # SL holds no number for anybody: the next multi deals from 1
    assert pg.evaluate("() => window.app.getDistros().find(d => d.id === 'd1').multiNumbers || null") is None
    srv = _wait_server(pg, lambda p: (_srv_layer('A', p) or {}).get('powerSocaDistro') == {}
                       and (_srv_layer('B', p) or {}).get('powerSocaDistro') == {})
    assert (_srv_layer('C', srv) or {}).get('powerSocaDistro') == {'1': 'd2'}


def test_clear_distro_forgets_every_unfed_cable_and_undo_restores(page):
    """A's cable on circuit 2 goes with its multi, and so does the one left
    under circuit 9, a number A has no circuit for. C's cable on SR stays.
    One Ctrl+Z puts the names, the numbers and both cables back, in the
    browser and on the server."""
    pg = page
    _open(pg, 'clearProject')
    a_before = _stores(pg, 'A')
    b_before = _stores(pg, 'B')
    labels_before = {n: _labels(pg, n) for n in ('A', 'B', 'C')}
    rows_before = pg.evaluate("() => window.__cm.cableRows()")
    assert sorted(a_before['cables']) == ['2', '9'], a_before
    assert ['A', 'TRUE1', "10'", 'SL1-2'] in rows_before, rows_before

    members = pg.evaluate("() => window.__cm.distroMembers('d1')")
    assert len(members) == 3, members
    pg.evaluate("(m) => window.app._clearMultis(m, 'Clear Distro')", members)
    _settle(pg)

    assert _stores(pg, 'A')['cables'] == {}
    assert _stores(pg, 'A')['lengths'] == {}
    assert _stores(pg, 'C')['cables'] == {'1': {'ft': 10, 'connector': None}}
    rows = pg.evaluate("() => window.__cm.cableRows()")
    assert all(r[0] != 'A' for r in rows), rows
    assert ['C', 'TRUE1', "10'", 'SR1-1'] in rows, rows
    srv = _wait_server(pg, lambda p: (_srv_layer('A', p) or {}).get('powerCircuitCables') == {})
    assert (_srv_layer('A', srv) or {}).get('powerCircuitCables') == {}
    assert (_srv_layer('C', srv) or {}).get('powerCircuitCables') == {'1': {'ft': 10, 'connector': None}}
    hist =pg.evaluate("() => window.app.history.map(h => h.action).slice(-1)")
    assert hist == ['Clear Distro'], hist

    _undo(pg)
    assert _stores(pg, 'A') == a_before
    assert _stores(pg, 'B') == b_before
    assert {n: _labels(pg, n) for n in ('A', 'B', 'C')} == labels_before
    assert pg.evaluate("() => window.__cm.cableRows()") == rows_before
    srv = _wait_server(pg, lambda p: sorted(((_srv_layer('A', p) or {}).get('powerCircuitCables') or {})) == ['2', '9'])
    assert (_srv_layer('A', srv) or {}).get('powerSocaDistro') == {'1': 'd1', '2': 'd1'}


def test_clear_on_one_distro_leaves_the_other_distro_alone(page):
    """Clearing SR resets only C; A and B keep SL1, SL2, SL3 and A keeps
    its cable on circuit 2 (its unfed 9 is not this clear's business: A
    was not cleared)."""
    pg = page
    _open(pg, 'clearProject')
    a_before = _stores(pg, 'A')
    _clear_distro_from_tray(pg, 'd2', 'SR')
    assert _labels(pg, 'C') == ['S1-1', 'S1-2', 'S1-3']
    assert _stores(pg, 'C')['cables'] == {}
    assert _labels(pg, 'A') == ['SL1-1', 'SL1-2', 'SL1-3', 'SL1-4', 'SL1-5', 'SL1-6', 'SL2-1']
    assert _labels(pg, 'B') == ['SL3-1', 'SL3-2', 'SL3-3']
    assert _stores(pg, 'A') == a_before
    _undo(pg)
    assert _labels(pg, 'C') == ['SR1-1', 'SR1-2', 'SR1-3']
    assert _stores(pg, 'C')['cables'] == {'1': {'ft': 10, 'connector': None}}


# ── A circuit's cable follows its circuit through Balance ─────────────────

def _cable_by_head(circuits):
    return {c['head']: (c['label'], c['cable']) for c in circuits}


def test_balance_reset_carries_the_cable_from_socket_6_to_5(page):
    """A's circuit 5 sits on socket 6 (SL1-6) with a 25' cable. The Balance
    dialog's Reset puts it on socket 5: it reads SL1-5, and the cable is on
    SL1-5 on the canvas, the tray's cable sheet and the pull sheet. Undo
    puts it back on SL1-6 with its cable."""
    pg = page
    _open(pg, 'balanceProject')
    before = _circuits(pg, 'A')
    assert [c['label'] for c in before] == ['SL1-1', 'SL1-2', 'SL1-3', 'SL1-4', 'SL1-6']
    assert before[4]['cable'] == "25' TRUE1"
    assert ['A', 'TRUE1', "25'", 'SL1-6'] in pg.evaluate("() => window.__cm.cableRows()")

    pg.evaluate("() => window.app.clearPhaseBalance('d1')")
    _settle(pg)
    after = _circuits(pg, 'A')
    assert [c['label'] for c in after] == ['SL1-1', 'SL1-2', 'SL1-3', 'SL1-4', 'SL1-5']
    # the same cabinets, the same cable, the new name
    assert after[4]['head'] == before[4]['head']
    assert after[4]['cable'] == "25' TRUE1"
    assert [c['cable'] for c in after[:4]] == [None] * 4
    rows = pg.evaluate("() => window.__cm.cableRows()")
    assert ['A', 'TRUE1', "25'", 'SL1-5'] in rows, rows
    assert not any(r[3] == 'SL1-6' for r in rows), rows
    # the tray's cable sheet: socket 5 holds A's circuit 5 with its 25'
    sheet = pg.evaluate("""() => {
        const app = window.app;
        app._circuitTailCache = null;
        const n = app._powerNaming(window.__cm.layer('A')).socas.get(1).number;
        app._setCableSheetOpen('d1', n, true);
        app.renderHardwareDock();
        const inp = document.querySelector('[data-lrd-field="power-cable-ft-1-5"]');
        if (!inp) return null;
        const tr = inp.closest('tr');
        return [tr.children[0].textContent, tr.children[1].textContent, inp.value];
    }""")
    assert sheet == ['5', 'SL1-5', '25'], sheet
    pg.evaluate("""() => {
        const app = window.app;
        app._circuitTailCache = null;
        const n = app._powerNaming(window.__cm.layer('A')).socas.get(1).number;
        app._setCableSheetOpen('d1', n, false);
        app.renderHardwareDock();
    }""")
    srv = _wait_server(pg, lambda p: ((_srv_layer('A', p) or {}).get('powerSocaPhasePos') or {}) == {})
    assert (_srv_layer('A', srv) or {}).get('powerCircuitCables') == {'5': {'ft': 25, 'connector': None}}

    _undo(pg)
    back = _circuits(pg, 'A')
    assert back == before
    assert ['A', 'TRUE1', "25'", 'SL1-6'] in pg.evaluate("() => window.__cm.cableRows()")


def test_balance_apply_keeps_each_cable_on_its_cabinets(page):
    """Apply what Balance offers: every circuit it moves takes its new
    socket name, and every cable is still on the same cabinets and prints
    under the new name. Undo puts every name and cable back."""
    pg = page
    _open(pg, 'balanceProject')
    pg.evaluate("() => window.app.clearPhaseBalance('d1')")
    _settle(pg)
    before = {n: _circuits(pg, n) for n in ('A', 'B')}
    moves = pg.evaluate("""() => {
        const s = window.app.suggestPhaseBalance('d1');
        window.__cmMoves = s.moves;
        return s.moves.map(m => [m.layerName, m.from, m.to]);
    }""")
    assert moves, 'Balance offered nothing to move on uneven legs'
    pg.evaluate("() => window.app.applyPhaseBalance(window.__cmMoves)")
    _settle(pg)
    after = {n: _circuits(pg, n) for n in ('A', 'B')}
    renamed = 0
    for n in ('A', 'B'):
        b = _cable_by_head(before[n])
        a = _cable_by_head(after[n])
        assert set(a) == set(b), n
        for head, (label, cable) in b.items():
            assert a[head][1] == cable, (n, head, b[head], a[head])
            if a[head][0] != label:
                renamed += 1
    assert renamed, (before, after)
    rows = pg.evaluate("() => window.__cm.cableRows()")
    want = sorted([n, 'TRUE1', c['cable'].split(' ')[0], c['label']]
                  for n in ('A', 'B') for c in after[n] if c['cable'])
    assert sorted(r for r in rows if r[0] in ('A', 'B')) == want, rows

    _undo(pg)
    assert {n: _circuits(pg, n) for n in ('A', 'B')} == before
