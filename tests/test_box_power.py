"""Powering a breakout box from the walls' power circuits, and the XD / XD-T
daisy chain (owner rulings, 2026-11-18; app-box-power.js).

  * A box is powered, per box, from the START of a circuit, its END, or an
    open circuit on a distro by itself: a direct output, or a spare
    circuit of a multi that already runs to a screen. Each is a
    right-click on the Power tab: a circuit's first cabinet (its tag sits
    there; on a shared 2fer / 3fer circuit the first of any run) or last,
    a free chip in the Power tray. Removing it is a right-click too. One
    undo step each; a locked screen refuses.
  * At the start (2026-11-19, 2026-11-20): EVERY box, an XD or XD-T too,
    gets a 2fer at the head of the circuit (behind it, on a shared
    circuit, the circuit's own 2fer), counted on the pull sheet, the
    binder's Shared circuits table and the screens' 2fer totals. A thru
    never feeds panels. A box at the start or end follows its
    panel when any change renumbers its circuit, or loses its power (named
    in gold) when the panel no longer starts or ends a run; and a box at
    the end is wired on the Power Wiring sheet from the run's last panel.
  * Only the XD and XD-T (TRUE1 in and thru) daisy chain. Past the 5 units
    a chain is rated for is warned in gold, never refused; an XD anywhere
    in a chain also past its own thru's 2 A, the draw of the boxes after
    it. The XD-T publishes no amp figure, so no amp warning.
  * Watts: XD-T 50, XD-S 50, CVT10 18, CVT10 Pro 22, CVT4K 21; the
    original XD by the straight line between 0.4 A at 100 V and 0.2 A at
    240 V, held outside them, watts = volts x amps. They count on the
    circuit's amps, the distro legs, the neutral and the totals.
  * The cable follows the inlet, its length from the show's stock; it is on
    the pull sheet, and the binder's power and wiring sheets show the box.

Every expected figure is worked beside it.

Run locally:
    "C:/Users/Blue Iris/.venvs/led-raster/Scripts/python.exe" -m pytest tests/test_box_power.py -n 4 --dist loadfile
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import processor_catalog as catalog  # noqa: E402

QUIET = "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}"


# ---- the server's figures (no browser) ----------------------------------------

def _xd_watts(v):
    """The owner's ruling by hand: amps on the line through (100, 0.4) and
    (240, 0.2), held to the end figure outside, times the volts."""
    at = min(max(v, 100.0), 240.0)
    return v * (0.4 + (0.2 - 0.4) * (at - 100.0) / 140.0)


@pytest.mark.parametrize('volts, watts', [
    (110, 110 * (0.4 - 0.2 * 10 / 140)),     # 0.3857 A, 42.43 W
    (120, 120 * (0.4 - 0.2 * 20 / 140)),     # 0.3714 A, 44.57 W
    (208, 208 * (0.4 - 0.2 * 108 / 140)),    # 0.2457 A, 51.11 W
    (230, 230 * (0.4 - 0.2 * 130 / 140)),    # 0.2143 A, 49.29 W
    (240, 240 * 0.2),                        # 0.2000 A, 48.00 W
    (90, 90 * 0.4),                          # held at 0.4 A below 100 V
    (250, 250 * 0.2),                        # held at 0.2 A past 240 V
])
def test_server_xd_watts_follow_the_voltage(volts, watts):
    xd = catalog.get_device('brompton-xd')
    assert catalog.box_power_watts(xd, volts) == pytest.approx(watts)
    assert catalog.box_power_watts(xd, volts) == pytest.approx(_xd_watts(volts))


@pytest.mark.parametrize('device_id, watts', [
    ('brompton-xd-t', 50), ('brompton-xd-s', 50),
    ('novastar-cvt10', 18), ('novastar-cvt10-m', 18),
    ('novastar-cvt10-pro', 22), ('novastar-cvt10-pro-m', 22),
    ('novastar-cvt4k-s', 21), ('novastar-cvt4k-m', 21),
])
def test_server_published_watts(device_id, watts):
    dev = catalog.get_device(device_id)
    for v in (110, 120, 208, 230, 240):
        assert catalog.box_power_watts(dev, v) == watts


def test_server_catalog_power_blocks():
    """Each powered box says its inlet, its cables and a source; only the XD
    and XD-T have the TRUE1 thru; boxes out of scope have no block."""
    want = {
        'brompton-xd': (['true1'], 'true1'), 'brompton-xd-t': (['true1'], 'true1'),
        'brompton-xd-s': (['true1-iec', 'edison-iec'], None),
        'novastar-cvt10': (['powercon'], None), 'novastar-cvt10-m': (['powercon'], None),
        'novastar-cvt10-pro': (['powercon'], None), 'novastar-cvt10-pro-m': (['powercon'], None),
        'novastar-cvt4k-s': (['powercon', 'true1-iec', 'edison-iec'], None),
        'novastar-cvt4k-m': (['powercon', 'true1-iec', 'edison-iec'], None),
    }
    for dev_id, (cables, thru) in want.items():
        block = catalog.box_power_block(catalog.get_device(dev_id))
        assert block, dev_id
        assert block['cables'] == cables, dev_id
        assert block.get('thru') == thru, dev_id
        assert block['source'].startswith('https://'), dev_id
        assert block['note'], dev_id
    for dev_id in ('novastar-cvt8-5g', 'brompton-qd-s', 'megapixel-rs12'):
        assert catalog.box_power_block(catalog.get_device(dev_id)) is None, dev_id
    # the thru's rating (owner, 2026-11-20): 5 units on both; 2 A on the
    # XD only, the XD-T publishing no amp figure
    xd = catalog.box_power_block(catalog.get_device('brompton-xd'))
    xdt = catalog.box_power_block(catalog.get_device('brompton-xd-t'))
    assert (xd.get('thruUnits'), xd.get('thruAmps')) == (5, 2)
    assert (xdt.get('thruUnits'), xdt.get('thruAmps')) == (5, None)
    for dev_id in want:
        if want[dev_id][1] is None:
            block = catalog.box_power_block(catalog.get_device(dev_id))
            assert 'thruUnits' not in block and 'thruAmps' not in block, dev_id


def test_server_no_figure_is_none():
    assert catalog.box_power_watts({'power': {'inlet': 'iec', 'cables': []}}, 120) is None
    assert catalog.box_power_watts({}, 120) is None


def test_server_screen_delete_drops_its_box_feeds(client_with_layer):
    """DELETE /api/layer drops the feeds on that screen's circuits and the
    chains off them; a feed off a distro, or on another screen, stays."""
    client = client_with_layer
    lid = client.get('/api/project').get_json()['layers'][0]['id']
    other = client.post('/api/layer/add', json={'name': 'B', 'columns': 2, 'rows': 2,
                                                'cabinet_width': 128, 'cabinet_height': 128}).get_json()['id']
    store = {
        'x1': {'cardId': 'c', 'at': {'kind': 'start', 'layerId': lid, 'circuit': 1}},
        'x2': {'cardId': 'c', 'at': {'kind': 'chain', 'from': 'x1'}},
        'x3': {'cardId': 'c', 'at': {'kind': 'chain', 'from': 'x2'}},
        'x4': {'cardId': 'c', 'at': {'kind': 'end', 'layerId': other, 'circuit': 1}},
        'x5': {'cardId': 'c', 'at': {'kind': 'distro', 'distroId': 'd1', 'number': 1, 'tail': 1}},
    }
    client.post('/api/project', json={'boxPower': store})
    after = client.delete(f'/api/layer/{lid}').get_json()['boxPower']
    assert sorted(after) == ['x4', 'x5']


# ---- the page ---------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1800, 'height': 1000})
    context.add_init_script(QUIET)
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    pg.wait_for_timeout(1500)
    pg.evaluate(SEED_JS)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(400)
    yield pg, errors
    context.close()


# Two walls, two SX40s and an MX40 Pro. P1's four boxes become XD-Ts, P2
# keeps three XDs and takes an XD-S, the MX40 Pro takes a CVT10 and a
# CVT4K-S: every model the rulings name.
SEED_JS = """async () => {
    const send = (url, method, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await (await fetch('/api/project')).json();
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.boxPower; delete proj.cableStock;
    await send('/api/project', 'PUT', proj);
    const walls = [];
    for (const [name, cols, rows, oy] of [['WALL A', 6, 2, 0], ['WALL B', 3, 2, 900]]) {
        const r = await send('/api/layer/add', 'POST', {name, columns: cols, rows,
            cabinet_width: 200, cabinet_height: 200, offset_x: 0, offset_y: oy});
        await send(`/api/layer/${r.id}`, 'PUT', {processorType: 'brompton'});
        walls.push(String(r.id));
    }
    const sx = async (name) => {
        const r = await send('/api/processors', 'POST', {deviceId: 'brompton-sx40'});
        return r.resolved[r.resolved.length - 1];
    };
    const p1 = await sx();
    const c1 = p1.slots[0].card;
    for (const b of c1.cvts) await send(`/api/processors/${p1.id}/cvts/${b.id}`, 'DELETE');
    for (let i = 0; i < 4; i++) await send(`/api/processors/${p1.id}/cards/${c1.id}/cvts`, 'POST', {deviceId: 'brompton-xd-t'});
    const p2 = await sx();
    const c2 = p2.slots[0].card;
    await send(`/api/processors/${p2.id}/cvts/${c2.cvts[3].id}`, 'DELETE');
    await send(`/api/processors/${p2.id}/cards/${c2.id}/cvts`, 'POST', {deviceId: 'brompton-xd-s'});
    const m = await send('/api/processors', 'POST', {deviceId: 'novastar-mx40-pro'});
    const p3 = m.resolved[m.resolved.length - 1];
    const c3 = p3.slots[0].card;
    await send(`/api/processors/${p3.id}/cards/${c3.id}/cvts`, 'POST', {deviceId: 'novastar-cvt10'});
    await send(`/api/processors/${p3.id}/cards/${c3.id}/cvts`, 'POST', {deviceId: 'novastar-cvt4k-s'});
    const app = window.app;
    if (!app.__counting) {
        const real = app.saveState;
        app.__saves = 0;
        app.saveState = function (...args) { app.__saves += 1; return real.apply(this, args); };
        const lock = app._showLockedError;
        app.__locked = [];
        app._showLockedError = function (layers, ...rest) {
            app.__locked.push((layers || []).map(l => l.name));
            return lock.call(this, layers, ...rest);
        };
        app.__counting = true;
    }
    app.project = await (await fetch('/api/project')).json();
    app.currentLayer = app.project.layers[0];
    app.selectedLayerIds = new Set([app.project.layers[0].id]);
    await app.refreshProcessors();
    // WALL A's ports on P1, WALL B's on P2: their processors print
    await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
        { layerId: walls[0], cardId: c1.id }, null, 'Place Ports');
    await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
        { layerId: walls[1], cardId: c2.id }, null, 'Place Ports');
    await app.refreshPortAssignment();
    app.renderLayers();
    return true;
}"""

# Both walls at `volts` on 20 A circuits: WALL A of 300 W panels, a
# circuit carrying 120 x 20 x 80% = 1920 W = 6 panels, so its two rows are
# circuits 1 and 2 (1800 W each, 15.0 A at 120 V). WALL B of 100 W panels:
# its six panels are one circuit of 600 W across two rows, 2fer'd into a
# run per row. One 120/208 distro: two Socapex 120V outputs (1, 2) and an
# Edison output (3), 20 A breakers. WALL A's multi is on output 1.
SETUP_JS = """(o) => {
    const app = window.app;
    const walls = app.project.layers.filter(l => (l.type || 'screen') === 'screen');
    walls.forEach((l, i) => {
        Object.assign(l, { powerVoltage: o.volts || 120, powerAmperage: 20,
                           panelWatts: i === 0 ? 300 : 100,
                           powerOrganized: false, powerMaximize: false,
                           powerSocaDistro: {}, powerSocaNumber: {}, powerSocaPhasePos: {},
                           powerSocaLengths: {}, powerSocaSplits: [], powerSocaNames: {},
                           powerCircuitCables: {}, powerLabelOverrides: {},
                           powerBreakoutType: null, locked: false, powerFlowPattern: 'tl-h',
                           powerCustomPaths: {}, powerCustomOverrides: [], lastPowerFlowPattern: null,
                           visible: true });
        delete l.supplyHarmonics;
        l.powerSources = [];
        app.normalizePowerBreakout(l);
    });
    app.project.distros = [{
        id: 'd1', name: 'SL', ratingA: 400, system: '120/208', voltage: 208, phase: 3,
        outputRows: [
            {id: 'r1', connector: 'soca', count: 2, coupling: 'ln', breakerA: 20},
            {id: 'r2', connector: 'edison', count: 1, coupling: 'ln', breakerA: 20},
        ],
    }];
    delete app.project.boxPower;
    delete app.project.supplyHarmonics;
    app._circuitTailCache = null;
    app._distroFaceMemo = null;
    app.getDistros();
    const a = walls[0], b = walls[1];
    app.setSocaDistro(a, 1, 'd1', false);
    app.setSocaNumber(a, 1, 1, false);
    app.currentLayer = a;
    app.selectedLayerIds = new Set([a.id]);
    app.updateLayers(walls);
    app._persistDistros();
    app._persistBoxPower();
    if (o.nfer) app.nferCircuit(b, 1);
    app.saveState('Test setup');
    app.renderHardwareDock();
    const r = window.canvasRenderer;
    r.zoom = 0.3; r.panX = 300; r.panY = 120; r.render();
    return { a: app.screenCircuits(a).map(c => [c.num, c.panels.length]),
             b: app.screenCircuits(b).map(c => [c.num, (c.runIds || []).length]) };
}"""

# The boxes by model, tray order: { model: [id, ...] } and their titles.
BOXES_JS = """() => {
    const app = window.app;
    const out = {};
    for (const { box } of app.boxPowerBoxes()) {
        (out[box.deviceId] = out[box.deviceId] || []).push({ id: box.id, title: app.boxPowerTitle(box) });
    }
    return out;
}"""

# The client point over a cabinet's centre.
CABINET_JS = """(o) => {
    const app = window.app, r = window.canvasRenderer;
    r.render();
    const l = app.project.layers.find(x => x.name === o.name);
    let p = null;
    if (o.circuit != null) {
        const c = app.screenCircuits(l).find(x => x.num === o.circuit);
        p = o.last ? c.panels[c.panels.length - 1] : c.panels[0];
    } else p = l.panels.find(q => q.row === o.row && q.col === o.col);
    const { dx, dy } = r.getLayerRenderOffset(l);
    const { wx, wy } = r._layerCanvasOffset(l);
    const rect = r.canvas.getBoundingClientRect();
    return { x: rect.left + r.panX + (p.x + p.width / 2 + dx + wx) * r.zoom,
             y: rect.top + r.panY + (p.y + p.height / 2 + dy + wy) * r.zoom };
}"""

# The client point over a box's pill on the canvas.
SYMBOL_JS = """(boxId) => {
    const r = window.canvasRenderer;
    r.render();
    const h = (r._boxPowerHits || []).find(x => x.boxId === boxId);
    if (!h) return null;
    const m = h.inv.inverse();
    const p = m.transformPoint(new DOMPoint(h.x + h.w / 2, h.y + h.h / 2));
    const rect = r.canvas.getBoundingClientRect();
    return { x: rect.left + p.x * rect.width / r.canvas.width, y: rect.top + p.y * rect.height / r.canvas.height };
}"""

# The client point over a Power tray chip of output `number`, circuit `tail`.
CHIP_JS = """(o) => {
    const app = window.app;
    app.renderHardwareDock();
    const faces = [...document.querySelectorAll('#hardware-dock [data-hwdock-payload]')];
    const el = faces.find(f => { try { const p = JSON.parse(f.dataset.hwdockPayload);
        return p.type === 'tail' && p.distroId === o.d && Number(p.number) === o.number && Number(p.tail) === o.tail;
    } catch (_) { return false; } });
    if (!el) return null;
    el.scrollIntoView({ block: 'center' });
    const r = el.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
}"""

# What the open menu offers: [{ action, label, disabled, entries? }].
MENU_JS = """() => {
    const menu = document.getElementById('context-menu');
    return [...menu.querySelectorAll('.hw-bp-only.menu-option')].filter(el => el.style.display !== 'none')
        .map(el => ({ action: el.dataset.action,
                      label: (el.querySelector('.menu-label-text') || el).textContent,
                      disabled: el.classList.contains('menu-disabled'),
                      entries: [...el.querySelectorAll('.menu-submenu .menu-option')].map(x => ({
                          action: x.dataset.action, label: x.textContent,
                          disabled: x.classList.contains('menu-disabled') })) }));
}"""

STATE_JS = """() => {
    const app = window.app;
    return { store: JSON.parse(JSON.stringify(app.project.boxPower || {})), saves: app.__saves,
             locked: app.__locked.slice() };
}"""


def _setup(pg, **o):
    out = pg.evaluate(SETUP_JS, o)
    pg.wait_for_timeout(150)
    return out


def _boxes(pg):
    return pg.evaluate(BOXES_JS)


def _right_click(pg, at):
    pg.mouse.click(at['x'], at['y'], button='right')
    pg.wait_for_timeout(120)
    return pg.evaluate(MENU_JS)


def _pick(pg, menu, slot_label_start, entry_label_start):
    """Hover the slot whose label starts so and click its entry."""
    slot = next(s for s in menu if s['label'].startswith(slot_label_start))
    entry = next(e for e in slot['entries'] if e['label'].startswith(entry_label_start))
    assert not entry['disabled'], entry
    pg.hover(f'#context-menu [data-action="{slot["action"]}"]')
    pg.wait_for_timeout(80)
    pg.click(f'#context-menu [data-action="{entry["action"]}"]')
    pg.wait_for_timeout(150)


def _item(pg, menu, label):
    it = next(s for s in menu if s['label'] == label and not s['entries'])
    pg.click(f'#context-menu [data-action="{it["action"]}"]')
    pg.wait_for_timeout(150)


def _state(pg):
    return pg.evaluate(STATE_JS)


def _escape(pg):
    pg.keyboard.press('Escape')
    pg.evaluate("() => window.app.hideContextMenu()")


# ---- the page's figures ----------------------------------------------------------

def test_page_watts_match_the_server(page):
    pg, errors = page
    got = pg.evaluate("""() => {
        const app = window.app, out = {};
        for (const id of ['brompton-xd', 'brompton-xd-t', 'brompton-xd-s', 'novastar-cvt10',
                          'novastar-cvt10-pro', 'novastar-cvt4k-s', 'novastar-cvt4k-m']) {
            const spec = app.boxPowerSpec({ deviceId: id });
            out[id] = [110, 120, 208, 230, 240].map(v => app.boxPowerWattsAt(spec, v));
        }
        out.none = app.boxPowerWattsAt({ inlet: 'iec', cables: [] }, 120);
        return out;
    }""")
    for i, v in enumerate((110, 120, 208, 230, 240)):
        dev = catalog.get_device
        assert got['brompton-xd'][i] == pytest.approx(_xd_watts(v))
        for k in ('brompton-xd-t', 'brompton-xd-s', 'novastar-cvt10', 'novastar-cvt10-pro', 'novastar-cvt4k-s',
                  'novastar-cvt4k-m'):
            assert got[k][i] == pytest.approx(catalog.box_power_watts(dev(k), v))
    assert got['none'] is None
    assert not errors


# ---- (a) the start of a circuit ---------------------------------------------------

def test_start_of_circuit_by_right_click(page):
    """Right-click WALL A's first cabinet: "at the start of" lists the boxes;
    the XD-T lands there, its 50 W on circuit 1 (1800 + 50 = 1850 W, 15.417 A
    at 120 V), on its distro leg and on the neutral. One undo step."""
    pg, errors = page
    _setup(pg)
    before = pg.evaluate("""() => {
        const app = window.app, a = app.project.layers[0];
        const leg = app.getSocaPlan(a)[0].legs[0];
        const L = app.getDistroLoads().find(x => x.id === 'd1');
        return { watts: leg.watts, amps: leg.amps, d: L.watts, x: L.legs.X.amps, n: L.neutral ? L.neutral.amps : null,
                 carried: app.getCarriedPowerLoad(a).watts };
    }""")
    assert before['watts'] == pytest.approx(1800)
    xdt = _boxes(pg)['brompton-xd-t'][0]
    s0 = _state(pg)
    menu = _right_click(pg, pg.evaluate(CABINET_JS, {'name': 'WALL A', 'row': 0, 'col': 0}))
    labels = [m['label'] for m in menu]
    assert any(t.startswith('Power a breakout box at the start of') for t in labels), labels
    assert any(t.startswith('Power a breakout box at the end of') for t in labels), labels
    start = next(m for m in menu if m['label'].startswith('Power a breakout box at the start of'))
    titles = [e['label'] for e in start['entries']]
    # every powerable box of the show, XD-S and the NovaStar boxes too
    assert len(titles) == 4 + 3 + 1 + 2, titles
    _pick(pg, menu, 'Power a breakout box at the start of', xdt['title'])
    s1 = _state(pg)
    assert s1['saves'] == s0['saves'] + 1
    rec = s1['store'][xdt['id']]
    assert rec['at']['kind'] == 'start' and rec['at']['circuit'] == 1
    assert rec['cable'] == 'true1'
    after = pg.evaluate("""() => {
        const app = window.app, a = app.project.layers[0];
        const leg = app.getSocaPlan(a)[0].legs[0];
        const L = app.getDistroLoads().find(x => x.id === 'd1');
        return { watts: leg.watts, amps: leg.amps, boxWatts: leg.boxWatts, d: L.watts, x: L.legs.X.amps,
                 n: L.neutral ? L.neutral.amps : null, carried: app.getCarriedPowerLoad(a).watts };
    }""")
    assert after['watts'] == pytest.approx(1850)
    assert after['boxWatts'] == pytest.approx(50)
    assert after['amps'] == pytest.approx(1850 / 120)
    assert after['d'] == pytest.approx(before['d'] + 50)
    assert after['carried'] == pytest.approx(before['carried'] + 50)
    # circuit 1 of a 120V multi rides leg X: + 50 / 120 A there
    assert after['x'] == pytest.approx(before['x'] + 50 / 120)
    assert after['n'] != pytest.approx(before['n'])
    # undo takes it off, redo puts it back
    pg.evaluate("() => window.app.undo()")
    pg.wait_for_timeout(200)
    assert _state(pg)['store'].get(xdt['id']) is None
    pg.evaluate("() => window.app.redo()")
    pg.wait_for_timeout(200)
    assert _state(pg)['store'][xdt['id']]['at']['kind'] == 'start'
    assert not errors


# ---- (b) the end of a circuit -------------------------------------------------------

def test_end_of_circuit_by_right_click(page):
    """Right-click WALL A's last cabinet of circuit 1 (row 0, col 5): only
    "at the end of"; the XD there draws 120 x 0.3714 = 44.57 W."""
    pg, errors = page
    _setup(pg)
    xd = _boxes(pg)['brompton-xd'][0]
    menu = _right_click(pg, pg.evaluate(CABINET_JS, {'name': 'WALL A', 'row': 0, 'col': 5}))
    labels = [m['label'] for m in menu]
    assert not any(t.startswith('Power a breakout box at the start of') for t in labels), labels
    _pick(pg, menu, 'Power a breakout box at the end of', xd['title'])
    st = _state(pg)
    assert st['store'][xd['id']]['at']['kind'] == 'end'
    leg = pg.evaluate("() => window.app.getSocaPlan(window.app.project.layers[0])[0].legs[0]")
    assert leg['boxWatts'] == pytest.approx(_xd_watts(120))
    assert leg['watts'] == pytest.approx(1800 + _xd_watts(120))
    # its pill is on the canvas, and right-clicking it offers the remove
    at = pg.evaluate(SYMBOL_JS, xd['id'])
    assert at, 'no pill drawn'
    menu = _right_click(pg, at)
    _item(pg, menu, 'Remove breakout box power')
    assert _state(pg)['store'].get(xd['id']) is None
    assert not errors


def test_the_box_list_stays_inside_the_window(page):
    """Every box of the show is one long submenu. Opened low on the window
    it ran off the bottom, its last boxes out of reach (and a click there
    landed on the Power tray). It now opens held inside the window."""
    pg, errors = page
    _setup(pg)
    pg.evaluate("""() => { const r = window.canvasRenderer;
        const rect = r.canvas.getBoundingClientRect();
        r.panY = rect.height - 140; r.render(); }""")
    menu = _right_click(pg, pg.evaluate(CABINET_JS, {'name': 'WALL A', 'circuit': 2, 'last': True}))
    slot = next(m for m in menu if m['label'].startswith('Power a breakout box at the end of'))
    pg.hover(f'#context-menu [data-action="{slot["action"]}"]')
    pg.wait_for_timeout(80)
    box = pg.evaluate(f"""() => {{
        const el = document.querySelector('#context-menu [data-action="{slot["action"]}"] > .menu-submenu');
        const r = el.getBoundingClientRect();
        return {{ top: r.top, bottom: r.bottom, h: window.innerHeight }}; }}""")
    assert box['top'] >= 0 and box['bottom'] <= box['h'], box
    _escape(pg)
    assert not errors


# ---- (c) an open circuit on a distro -----------------------------------------------

def test_open_distro_circuit_by_right_click(page):
    """Right-click output 1's spare circuit 3 in the Power tray (WALL A's
    multi runs from output 1 on circuits 1 and 2): the CVT10 rides it by
    itself, 18 W on d1 (a 120 V circuit: 0.15 A on its leg). Output 2 has
    no multi on it, so its free circuits only say why they are not
    offered (owner, 2026-11-19); the Edison output 3, a direct output, is
    offered."""
    pg, errors = page
    _setup(pg)
    pg.evaluate("() => window.app.setHardwareDockMode ? window.app.setHardwareDockMode('power') : null")
    cvt = _boxes(pg)['novastar-cvt10'][0]
    before = pg.evaluate("() => window.app.getDistroLoads().find(x => x.id === 'd1').watts")
    # an empty output: one greyed line, no submenu of boxes
    empty = pg.evaluate(CHIP_JS, {'d': 'd1', 'number': 2, 'tail': 3})
    assert empty, 'no chip for output 2'
    menu = _right_click(pg, empty)
    bp = [m for m in menu if m['label'].startswith('Power a breakout box from')]
    assert len(bp) == 1 and bp[0]['disabled'] and not bp[0]['entries'], menu
    _escape(pg)
    # a direct output
    direct = pg.evaluate(CHIP_JS, {'d': 'd1', 'number': 3, 'tail': 1})
    assert direct, 'no chip for the Edison output'
    menu = _right_click(pg, direct)
    bp = [m for m in menu if m['label'].startswith('Power a breakout box from')]
    assert len(bp) == 1 and not bp[0]['disabled'] and bp[0]['entries'], menu
    _escape(pg)
    at = pg.evaluate(CHIP_JS, {'d': 'd1', 'number': 1, 'tail': 3})
    assert at, 'no free chip'
    menu = _right_click(pg, at)
    _pick(pg, menu, 'Power a breakout box from', cvt['title'])
    st = _state(pg)
    assert st['store'][cvt['id']]['at'] == {'kind': 'distro', 'distroId': 'd1', 'number': 1, 'tail': 3}
    assert st['store'][cvt['id']]['cable'] == 'powercon'
    L = pg.evaluate("() => window.app.getDistroLoads().find(x => x.id === 'd1')")
    assert L['watts'] == pytest.approx(before + 18)
    assert [b['name'] for b in L['boxes']] == [cvt['title']]
    # the chip names the box, and a screen's chip is never offered
    who = pg.evaluate("""(id) => { window.app.renderHardwareDock();
        const t = document.querySelector(`#hardware-dock [data-lrd-box-power="${id}"]`);
        return t ? t.textContent : null; }""", cvt['id'])
    assert who and cvt['title'] in who
    held = pg.evaluate(CHIP_JS, {'d': 'd1', 'number': 1, 'tail': 1})
    menu = _right_click(pg, held)
    assert not any(m['label'].startswith('Power a breakout box from') for m in menu), menu
    _escape(pg)
    assert not errors


# ---- (d) a circuit shared by a 2fer ----------------------------------------------------

# The first cabinet of each run of WALL B's circuit 1, as client points.
RUN_HEADS_JS = """() => {
    const app = window.app, r = window.canvasRenderer;
    r.render();
    const l = app.project.layers.find(x => x.name === 'WALL B');
    const c = app.screenCircuits(l).find(x => x.num === 1);
    const { dx, dy } = r.getLayerRenderOffset(l);
    const { wx, wy } = r._layerCanvasOffset(l);
    const rect = r.canvas.getBoundingClientRect();
    return c.branches.map(run => { const p = run[0];
        return { x: rect.left + r.panX + (p.x + p.width / 2 + dx + wx) * r.zoom,
                 y: rect.top + r.panY + (p.y + p.height / 2 + dy + wy) * r.zoom }; });
}"""

# WALL B's circuit 1 on the pull sheet: its splitter rows [type, qty, notes]
# (rows of one type and circuit merge, their notes joined).
# (The NovaStar boxes feed no screen here, so their processor is held on
# paper for it: the paper rule has tests of its own.)
SPLITTERS_JS = """() => {
    const app = window.app, b = app.project.layers[1];
    const off = app._pullProcOffPaper, hid = app._pullHiddenOnlyBox;
    app._pullProcOffPaper = () => false;
    app._pullHiddenOnlyBox = () => false;
    try {
        const scr = app.buildPullList().byScreen[b.id];
        return scr.rows.filter(r => /\\d+fer$/.test(r.type)).map(r => [r.type, r.qty, r.notes]);
    } finally { app._pullProcOffPaper = off; app._pullHiddenOnlyBox = hid; }
}"""


def test_a_box_on_a_2fer_circuit_is_at_its_start(page):
    """WALL B's one circuit 2fer'd into a run per row (owner, 2026-11-19).
    A box there is a box at the circuit's START, offered on the first panel
    of either run, never mid-run, and no separate "from the 2fer" pick. The
    CVT4K-S (21 W) takes a TRUE1 2fer of its own ahead of the circuit's
    2fer: two 2fers on the pull sheet. An XD-T the same (2026-11-20: a thru
    never feeds the panels or their 2fer). An older file's 'fanout' record
    reads as the start."""
    pg, errors = page
    shape = _setup(pg, nfer=True)
    assert shape['b'] == [[1, 2]], shape
    b = _boxes(pg)
    k4, xdt = b['novastar-cvt4k-s'][0], b['brompton-xd-t'][0]
    # mid-run: nothing to power a box from
    menu = _right_click(pg, pg.evaluate(CABINET_JS, {'name': 'WALL B', 'row': 0, 'col': 1}))
    assert not any(m['label'].startswith('Power a breakout box at the start of') for m in menu), menu
    _escape(pg)
    heads = pg.evaluate(RUN_HEADS_JS)
    assert len(heads) == 2, heads
    for at in heads:
        menu = _right_click(pg, at)
        labels = [m['label'] for m in menu]
        assert any(t.startswith('Power a breakout box at the start of') for t in labels), labels
        assert not any('2fer of' in t for t in labels), labels
        _escape(pg)
    assert pg.evaluate(SPLITTERS_JS) == [['TRUE1 2fer', 1, '']]
    menu = _right_click(pg, heads[1])
    _pick(pg, menu, 'Power a breakout box at the start of', k4['title'])
    st = _state(pg)
    assert st['store'][k4['id']]['at']['kind'] == 'start'
    leg = pg.evaluate("() => window.app.getSocaPlan(window.app.project.layers[1])[0].legs[0]")
    assert leg['boxWatts'] == pytest.approx(21)
    assert leg['watts'] == pytest.approx(600 + 21)
    # the circuit's own 2fer and the box's: two on the circuit's row
    assert pg.evaluate(SPLITTERS_JS) == [['TRUE1 2fer', 2, f"breakout box {k4['title']}"]]
    words = pg.evaluate("""(id) => { const app = window.app;
        const p = app.boxPowerPlacements().find(x => x.head.box.id === id);
        return { caption: app.boxPowerWiringCaption(p), circuit: app._bBoxPowerOnText(p.layer, 1) }; }""",
                        k4['id'])
    assert words['caption'].endswith(' · on a TRUE1 2fer, other leg to the 2fer'), words
    assert words['circuit'] == f"breakout box {k4['title']} at the start, on a TRUE1 2fer, other leg to the 2fer"
    # the XD-T in its place: its own 2fer too, never its thru
    pg.evaluate("""([k, x]) => { const app = window.app, b = app.project.layers[1];
        app.removeBoxPower(k);
        app.setBoxPower(x, { kind: 'start', layerId: b.id, circuit: 1 }); }""", [k4['id'], xdt['id']])
    assert pg.evaluate(SPLITTERS_JS) == [['TRUE1 2fer', 2, f"breakout box {xdt['title']}"]]
    cap = pg.evaluate("""(id) => { const app = window.app;
        return app.boxPowerWiringCaption(app.boxPowerPlacements().find(x => x.head.box.id === id)); }""",
                      xdt['id'])
    assert cap.endswith(' · on a TRUE1 2fer, other leg to the 2fer'), cap
    assert 'thru' not in cap, cap
    # an older file's fan-out record
    old = pg.evaluate("""([k, x]) => { const app = window.app, b = app.project.layers[1];
        app.removeBoxPower(x);
        app.project.boxPower[k] = { cardId: app.boxPowerBoxes().find(e => e.box.id === k).card.id,
                                    at: { kind: 'fanout', layerId: b.id, circuit: 1 }, cable: 'powercon' };
        app._boxPowerMemo = null; app._boxPowerStandMemo = null; app._boxPowerCircuitIdx = null;
        const e = app.boxPowerOf(k);
        return { kind: e.at.kind, where: app.boxPowerWhereText(e) }; }""", [k4['id'], xdt['id']])
    assert old['kind'] == 'start' and old['where'].startswith('the start of'), old
    assert not errors


def test_every_box_at_a_circuits_start_is_on_a_2fer(page):
    """On WALL A's single-run circuits: an XD-T at the start of circuit 1 and
    a CVT10 at the start of circuit 2 each get a TRUE1 2fer at its head, one
    leg to the box and one to the panels, listed on the pull sheet (owner,
    2026-11-20: an XD or XD-T is never in line, its thru never feeds the
    panels). The canvas pill, the Power Wiring caption and the circuit list
    say so; the watts are the boxes' own figures."""
    pg, errors = page
    _setup(pg)
    b = _boxes(pg)
    xdt, cvt = b['brompton-xd-t'][0], b['novastar-cvt10'][0]
    out = pg.evaluate("""([t, c]) => {
        const app = window.app, a = app.project.layers[0];
        app.setBoxPower(t, { kind: 'start', layerId: a.id, circuit: 1 });
        app.setBoxPower(c, { kind: 'start', layerId: a.id, circuit: 2 });
        const off = app._pullProcOffPaper, hid = app._pullHiddenOnlyBox;
        app._pullProcOffPaper = () => false;
        app._pullHiddenOnlyBox = () => false;
        let rows;
        try { rows = app.buildPullList().byScreen[a.id].rows; }
        finally { app._pullProcOffPaper = off; app._pullHiddenOnlyBox = hid; }
        const place = (id) => app.boxPowerPlacements().find(x => x.head.box.id === id);
        app._boxPowerDrawnLog = null;
        const seen = [];
        const log = app._boxPowerLogDrawn;
        app._boxPowerLogDrawn = function (layerId, drawn) { seen.push(...drawn); return log.apply(this, arguments); };
        try { window.canvasRenderer.render(); } finally { app._boxPowerLogDrawn = log; }
        const legs = app.getSocaPlan(a)[0].legs;
        return { fers: rows.filter(r => /\\d+fer$/.test(r.type)).map(r => [r.type, r.qty, r.label, r.notes]),
                 label1: app.getPowerCircuitLabel(a, 1), label2: app.getPowerCircuitLabel(a, 2),
                 capT: app.boxPowerWiringCaption(place(t)), capC: app.boxPowerWiringCaption(place(c)),
                 on1: app._bBoxPowerOnText(a, 1), on2: app._bBoxPowerOnText(a, 2),
                 drawn: seen.map(d => [d.boxes[0], d.wiring]),
                 watts: legs.map(l => l.boxWatts) };
    }""", [xdt['id'], cvt['id']])
    # one row of the type: both circuits' 2fers, each box named
    assert len(out['fers']) == 1 and out['fers'][0][:2] == ['TRUE1 2fer', 2], out
    for want in (out['label1'], out['label2']):
        assert want in out['fers'][0][2], out
    for box in (xdt, cvt):
        assert f"breakout box {box['title']}" in out['fers'][0][3], out
    for cap in (out['capT'], out['capC']):
        assert cap.endswith(' · on a TRUE1 2fer, other leg to the panels') and 'thru' not in cap, out
    assert out['on1'] == f"breakout box {xdt['title']} at the start, on a TRUE1 2fer, other leg to the panels"
    assert out['on2'] == f"breakout box {cvt['title']} at the start, on a TRUE1 2fer, other leg to the panels"
    assert sorted(out['drawn']) == sorted([[xdt['id'], 'on a TRUE1 2fer'], [cvt['id'], 'on a TRUE1 2fer']]), out
    assert out['watts'] == [pytest.approx(50), pytest.approx(18)], out
    assert not errors


# The FACTS sheet's text, where the binder's power notes (warnings) print.
FACTS_FN = """const FACTS = (app) => {
    const opts = { ...app.readBinderOptions(), mode: 'full', sides: { power: true, data: false } };
    const plan = app.planBinder(opts);
    const i = plan.findIndex(p => p.kind === 'facts');
    if (i < 0) return '';
    // a note wraps at its words: the lines joined, spaces made one
    return (app.renderBinderPage(opts, i).texts || []).map(x => typeof x === 'string' ? x : String(x.text || ''))
        .join(' ').replace(/\\s+/g, ' ');
};"""

# For WALL A's flow patterns: where the panels of a box at the start of
# circuit 1 and a box at the end of circuit 2 land - the circuit whose
# first (or last) panel each is, or null - read straight off the circuits.
FLOW_LANDING_JS = """() => {
    const app = window.app, a = app.project.layers[0];
    const key = (p) => `${p.row}:${p.col}`;
    const keep = a.powerFlowPattern;
    const at = (pat) => {
        a.powerFlowPattern = pat;
        app._circuitTailCache = null;
        const cs = app.screenCircuits(a);
        return { cs: cs.map(c => ({ num: c.num, first: key(c.panels[0]), last: key(c.panels[c.panels.length - 1]) })) };
    };
    const base = at('tl-h').cs;
    const s = base.find(c => c.num === 1).first, e = base.find(c => c.num === 2).last;
    const out = {};
    for (const pat of ['tl-h', 'tr-h', 'bl-h', 'br-h', 'tl-v', 'tr-v', 'bl-v', 'br-v']) {
        const cs = at(pat).cs;
        const hs = cs.find(c => c.first === s), te = cs.find(c => c.last === e);
        out[pat] = { start: hs ? hs.num : null, end: te ? te.num : null };
    }
    a.powerFlowPattern = keep;
    app._circuitTailCache = null;
    return out;
}"""

FOLLOW_JS = """([t, c, pat, how]) => {
    """ + FACTS_FN + """
    const app = window.app, a = app.project.layers[0];
    a.powerFlowPattern = 'tl-h';
    app._circuitTailCache = null;
    app.setBoxPower(t, { kind: 'start', layerId: a.id, circuit: 1 });
    app.setBoxPower(c, { kind: 'end', layerId: a.id, circuit: 2 });
    const toasts = [];
    const toast = app._toast;
    app._toast = function (msg) { toasts.push(String(msg)); return toast.apply(this, arguments); };
    const saves = app.__saves;
    try {
        if (how === 'carry') {
            // the moments a circuit's cable follows its first cabinet
            const carry = app._cableCarryBegin([a]);
            a.powerFlowPattern = pat;
            app._circuitTailCache = null;
            app._cableCarryApply(carry);
            app.saveState('Change Power Pattern');
        } else {
            // any other change: the undo step it takes
            a.powerFlowPattern = pat;
            app._circuitTailCache = null;
            app.saveState('Change Power Pattern');
        }
    } finally { app._toast = toast; }
    const rec = (id) => JSON.parse(JSON.stringify(app.project.boxPower[id] || null));
    app.renderHardwareDock();
    const out = { t: rec(t), c: rec(c), powered: [!!app.boxPowerOf(t), !!app.boxPowerOf(c)], toasts,
                  steps: app.__saves - saves,
                  lost: app.boxPowerLost().map(x => x.text),
                  strip: (app._dockPowerWarnings || []).filter(w => w.boxLost).map(w => [w.mild, w.text]),
                  notes: FACTS(app) };
    app.undo();
    out.undone = [!!app.boxPowerOf(t), !!app.boxPowerOf(c)];
    out.undoneCircuits = [app.project.boxPower[t].at.circuit, app.project.boxPower[c].at.circuit];
    a.powerFlowPattern = 'tl-h';
    app._circuitTailCache = null;
    return out;
}"""


def test_a_box_follows_its_panel_across_a_renumber(page):
    """WALL A's circuits renumbered under their panels (owner, 2026-11-19):
    the box at the start of circuit 1 and the box at the end of circuit 2
    ride whatever circuit their panels now start or end, by the cable carry
    and by any change's own undo step alike; the move is in that one step."""
    pg, errors = page
    _setup(pg)
    b = _boxes(pg)
    xdt, cvt = b['brompton-xd-t'][0], b['novastar-cvt10'][0]
    land = pg.evaluate(FLOW_LANDING_JS)
    moves = [p for p, v in land.items() if v['start'] and v['end'] and (v['start'], v['end']) != (1, 2)]
    assert moves, land
    for how, pat in (('carry', moves[0]), ('step', moves[-1])):
        out = pg.evaluate(FOLLOW_JS, [xdt['id'], cvt['id'], pat, how])
        want = land[pat]
        assert out['t']['at']['circuit'] == want['start'] and not out['t'].get('lost'), (how, pat, out)
        assert out['c']['at']['circuit'] == want['end'] and not out['c'].get('lost'), (how, pat, out)
        assert out['powered'] == [True, True] and out['lost'] == [] and out['toasts'] == [], (how, pat, out)
        assert out['steps'] == 1, out
        # one undo puts the change and the boxes back together
        assert out['undone'] == [True, True] and out['undoneCircuits'] == [1, 2], out
    assert not errors


def test_a_box_whose_panel_stops_starting_a_run_loses_power(page):
    """A change after which the box's panel no longer starts (or ends) a run
    (owner, 2026-11-19): the box loses its power, a toast names it at once,
    the Power tab and the binder's notes keep naming it in gold, and the
    one undo step brings it back powered."""
    pg, errors = page
    _setup(pg)
    b = _boxes(pg)
    xdt, cvt = b['brompton-xd-t'][0], b['novastar-cvt10'][0]
    land = pg.evaluate(FLOW_LANDING_JS)
    # the pattern that leaves the most of the two panels off a run's end,
    # the start box's among them
    gone = sorted((p for p, v in land.items() if not v['start']),
                  key=lambda p: -int(not land[p]['end']))
    assert gone, land
    pat = gone[0]
    out = pg.evaluate(FOLLOW_JS, [xdt['id'], cvt['id'], pat, 'step'])
    lost = [xdt] + ([cvt] if not land[pat]['end'] else [])
    assert out['t'].get('lost'), out
    assert bool(out['c'].get('lost')) == (not land[pat]['end']), (pat, land[pat], out)
    assert out['powered'] == [False, bool(land[pat]['end'])], out
    assert out['steps'] == 1, out
    for box in lost:
        said = [t for t in out['lost'] if box['title'] in t]
        assert said and 'has no power' in said[0], out['lost']
        assert any(box['title'] in t for t in out['toasts']), out['toasts']
        assert any(box['title'] in t for m, t in out['strip'] if m), out['strip']
        assert f"Breakout box {box['title']} has no power" in out['notes'], out['notes']
    assert '—' not in ' '.join(out['lost'])
    assert out['undone'] == [True, True] and out['undoneCircuits'] == [1, 2], out
    # its power can be taken off for good from the tray's box, or given again
    again = pg.evaluate("""([t, c, pat]) => { const app = window.app, a = app.project.layers[0];
        a.powerFlowPattern = pat; app._circuitTailCache = null; app.saveState('Change Power Pattern');
        const items = app._boxPowerBoxItems(t).items.map(i => i.label);
        app.setBoxPower(c, { kind: 'start', layerId: a.id, circuit: 1 });
        const out = { items, repowered: !!app.boxPowerOf(c), lostNow: app.boxPowerLost().map(x => x.boxId) };
        app.removeBoxPower(t);
        out.removed = app.project.boxPower[t] === undefined;
        a.powerFlowPattern = 'tl-h'; app._circuitTailCache = null;
        return out; }""", [xdt['id'], cvt['id'], gone[0]])
    assert again['items'] == ['Remove breakout box power'], again
    assert again['repowered'] and again['lostNow'] == [xdt['id']], again
    assert again['removed'], again
    assert not errors


def test_the_thru_is_for_daisy_chains_only(page):
    """An XD-T or XD at the start of a circuit is on its TRUE1 2fer like any
    box (owner, 2026-11-20): the circuit's panels never go through its thru,
    so WALL A's 1800 W circuits put no warning on either, and the canvas
    pill says "on a TRUE1 2fer"."""
    pg, errors = page
    _setup(pg)
    b = _boxes(pg)
    xdt, xd = b['brompton-xd-t'][0], b['brompton-xd'][0]
    out = pg.evaluate("""([t, x]) => {
        const app = window.app, a = app.project.layers[0];
        app.setBoxPower(t, { kind: 'start', layerId: a.id, circuit: 1 });
        app.setBoxPower(x, { kind: 'start', layerId: a.id, circuit: 2 });
        app.renderHardwareDock();
        const strip = (app._dockPowerWarnings || []).filter(w => w.boxChain).length;
        const seen = [];
        const log = app._boxPowerLogDrawn;
        app._boxPowerDrawnLog = null;
        app._boxPowerLogDrawn = function (l, drawn) { seen.push(...drawn); return log.apply(this, arguments); };
        try { window.canvasRenderer.render(); } finally { app._boxPowerLogDrawn = log; }
        return { checks: app.boxPowerChainChecks().length, strip,
                 drawn: seen.map(d => [d.boxes[0], d.wiring, d.over.length > 0]),
                 words: [t, x].map(id => app.boxPowerStartWiring(
                     app.boxPowerPlacements().find(p => p.head.box.id === id)).words) };
    }""", [xdt['id'], xd['id']])
    assert out['checks'] == 0 and out['strip'] == 0, out
    assert sorted(out['drawn']) == sorted([[xdt['id'], 'on a TRUE1 2fer', False],
                                           [xd['id'], 'on a TRUE1 2fer', False]]), out
    assert out['words'] == ['on a TRUE1 2fer, other leg to the panels'] * 2, out
    assert not errors


def test_a_box_2fer_counts_in_the_shared_circuits_and_screen_counts(page):
    """A box at a circuit's start adds a 2fer (owner, 2026-11-19): it counts everywhere the pull sheet's 2fers do - the
    binder's Shared circuits table on the screen's power sheet and the
    2fer count in the pull pages' table of screens (the binder's 2fer
    totals; the overview sheet prints none). (The boxes' processors are held on paper here:
    the paper rule has tests of its own.)"""
    pg, errors = page
    _setup(pg)
    xs = _boxes(pg)['brompton-xd-s'][0]
    out = pg.evaluate("""(s) => {
        const app = window.app, a = app.project.layers[0];
        const off = app._pullProcOffPaper, hid = app._pullHiddenOnlyBox;
        app._pullProcOffPaper = () => false;
        app._pullHiddenOnlyBox = () => false;
        const join = (r) => (r.texts || []).map(x => typeof x === 'string' ? x : String(x.text || '')).join(' | ');
        const opts = { ...app.readBinderOptions(), mode: 'full', sides: { power: true, data: false } };
        const pages = () => {
            const plan = app.planBinder(opts);
            const at = (pick) => { const i = plan.findIndex(pick); return i < 0 ? '' : join(app.renderBinderPage(opts, i)); };
            const all = (pick) => plan.map((p, i) => (pick(p) ? join(app.renderBinderPage(opts, i)) : ''))
                .filter(Boolean).join(' | ');
            return { pull: all(p => p.kind === 'pull'),
                     power: at(p => p.title === `${a.name} - Power - Front View`) };
        };
        try {
            const before = pages();
            app.setBoxPower(s, { kind: 'start', layerId: a.id, circuit: 2 });
            const after = pages();
            const gangs = app.buildPullList().byScreen[a.id].gangs;
            return { before, after, gangs, label: app.getPowerCircuitLabel(a, 2) };
        } finally { app._pullProcOffPaper = off; app._pullHiddenOnlyBox = hid; }
    }""", xs['id'])
    assert out['gangs']['twofer'] == 1, out['gangs']
    assert '× 2fer' not in out['before']['pull'], out['before']['pull']
    assert '1× 2fer' in out['after']['pull'], out['after']['pull']
    assert 'SHARED CIRCUITS' not in out['before']['power'].upper()
    pw = out['after']['power']
    assert 'SHARED CIRCUITS' in pw.upper(), pw
    assert f"{out['label']} · breakout box {xs['title']}" in pw, pw
    assert not errors


# ---- the daisy chain ----------------------------------------------------------------

def test_daisy_chain_and_its_warnings(page):
    """A powered XD-T chains on by right-clicking its pill. Five boxes are
    within the 5 units a TRUE1 thru chain is rated for; six are past it:
    warned in gold, "XD-T A chain: 6 boxes, rated for 5." Never refused.
    The XD-Ts' thrus publish no amp figure; the one XD in it (fifth) carries
    only the last box (44.57 W, 0.37 A at 120 V) on through its own thru,
    well inside its 2 A, at 110 V too."""
    pg, errors = page
    _setup(pg)
    b = _boxes(pg)
    chain = [x['id'] for x in b['brompton-xd-t']] + [b['brompton-xd'][0]['id'], b['brompton-xd'][1]['id']]
    head = chain[0]
    pg.evaluate("(id) => window.app.setBoxPower(id, { kind: 'end', layerId: window.app.project.layers[0].id, circuit: 2 })",
                head)
    s0 = _state(pg)
    at = pg.evaluate(SYMBOL_JS, head)
    menu = _right_click(pg, at)
    target = next(x for x in b['brompton-xd-t'] if x['id'] == chain[1])
    # an XD-S has no thru, and a CVT none: never offered
    slot = next(m for m in menu if m['label'] == 'Daisy chain to')
    offered = [e['label'] for e in slot['entries']]
    assert not any(t.startswith(b['brompton-xd-s'][0]['title']) for t in offered), offered
    assert not any(t.startswith(b['novastar-cvt10'][0]['title']) for t in offered), offered
    _pick(pg, menu, 'Daisy chain to', target['title'])
    s1 = _state(pg)
    assert s1['saves'] == s0['saves'] + 1
    assert s1['store'][chain[1]]['at'] == {'kind': 'chain', 'from': head}
    assert s1['store'][chain[1]]['cable'] == 'true1'
    # on to five boxes (four XD-Ts, then the XD)
    for up, down in zip(chain[1:4], chain[2:5]):
        assert pg.evaluate("([a, z]) => window.app.chainBoxPower(a, z)", [up, down])
    checks = pg.evaluate("() => window.app.boxPowerChainChecks()")
    assert checks == []
    w = pg.evaluate("() => window.app.getSocaPlan(window.app.project.layers[0])[0].legs[1].boxWatts")
    assert w == pytest.approx(4 * 50 + _xd_watts(120))
    assert pg.evaluate("([a, z]) => window.app.chainBoxPower(a, z)", [chain[4], chain[5]])
    checks = pg.evaluate("""() => window.app.boxPowerChainChecks().map(c => ({ kind: c.kind, box: c.box.box.id,
        count: c.count, units: c.units, text: c.text }))""")
    assert checks == [{'kind': 'units', 'box': head, 'count': 6, 'units': 5,
                       'text': f"{b['brompton-xd-t'][0]['title']} chain: 6 boxes, rated for 5."}], checks
    assert '—' not in checks[0]['text']
    # the tray says it in gold
    strip = pg.evaluate("""() => { window.app.renderHardwareDock();
        return (window.app._dockPowerWarnings || []).filter(w => w.boxChain).map(w => w.mild); }""")
    assert strip == [True]
    # 110 V: the XD's thru carries 42.43 W, 0.39 A: still only the count
    pg.evaluate("""() => { const app = window.app; app.project.layers[0].powerVoltage = 110;
        app._boxPowerMemo = null; }""")
    checks = pg.evaluate("() => window.app.boxPowerChainChecks().map(c => c.kind)")
    assert checks == ['units']
    assert not errors


# A chain of `ids` off the end of WALL A's circuit 1, every box drawing
# `watts` (no model in the catalog draws enough within five boxes to load
# an XD's thru past 2 A, so the figure is given): the warnings, the tray's
# gold lines, the boxes the canvas marks and the FACTS sheet's notes.
XD_THRU_JS = """([ids, watts]) => {
    """ + FACTS_FN + """
    const app = window.app, a = app.project.layers[0];
    app.setBoxPower(ids[0], { kind: 'end', layerId: a.id, circuit: 1 });
    for (let i = 1; i < ids.length; i++) app.chainBoxPower(ids[i - 1], ids[i]);
    const real = app.boxPowerWattsAt;
    if (watts != null) app.boxPowerWattsAt = () => watts;
    try {
        app._boxPowerMemo = null;
        const checks = app.boxPowerChainChecks().map(c => ({ kind: c.kind, box: c.box.box.id, amps: c.amps,
                                                            rated: c.rated, text: c.text }));
        app.renderHardwareDock();
        const strip = (app._dockPowerWarnings || []).filter(w => w.boxChain).map(w => [w.mild, w.text]);
        const seen = [];
        const log = app._boxPowerLogDrawn;
        app._boxPowerDrawnLog = null;
        app._boxPowerLogDrawn = function (l, drawn) { seen.push(...drawn); return log.apply(this, arguments); };
        try { window.canvasRenderer.render(); } finally { app._boxPowerLogDrawn = log; }
        return { checks, strip, drawn: seen.map(d => d.over), notes: FACTS(app) };
    } finally { app.boxPowerWattsAt = real; }
}"""


def test_an_xd_is_warned_past_2_a_through_its_own_thru(page):
    """The 2 A is the XD's OWN thru rating (owner, 2026-11-20): what its
    thru carries on to the boxes after it, never its own draw. An XD
    heading four boxes of 70 W at 120 V passes 280 W, 2.33 A: "XD A thru:
    2.33 A to the boxes after it, rated for 2 A." in gold on the Power tab,
    the XD's pill and the binder's notes. At the catalog's own figures
    (4 x 50 W, 1.67 A) it is not warned. Never refused."""
    pg, errors = page
    _setup(pg)
    b = _boxes(pg)
    xd = b['brompton-xd'][0]
    ids = [xd['id']] + [x['id'] for x in b['brompton-xd-t'][:4]]
    out = pg.evaluate(XD_THRU_JS, [ids, 70])
    assert len(out['checks']) == 1, out
    c = out['checks'][0]
    assert c['kind'] == 'amps' and c['box'] == xd['id'] and c['rated'] == 2, c
    assert c['amps'] == pytest.approx(4 * 70 / 120), c
    assert c['text'] == f"{xd['title']} thru: 2.33 A to the boxes after it, rated for 2 A.", c
    assert out['strip'] == [[True, c['text']]], out
    assert out['drawn'] == [[xd['id']]], out
    assert c['text'] in out['notes'], out['notes']
    real = pg.evaluate("() => window.app.boxPowerChainChecks().length")
    assert real == 0
    assert not errors


def test_an_xd_mid_chain_behind_an_xd_t_is_warned(page):
    """An XD-T heads the chain and an XD stands second in it (owner,
    2026-11-20): the XD-T's thru publishes no amp figure and is never
    checked, but the XD's own thru is, whatever heads the chain. Five boxes
    of 90 W at 120 V: the XD passes the three after it, 270 W, 2.25 A:
    "XD A thru: 2.25 A to the boxes after it, rated for 2 A." Only the XD
    is named and marked; five boxes is no count warning."""
    pg, errors = page
    _setup(pg)
    b = _boxes(pg)
    xdts, xd = b['brompton-xd-t'], b['brompton-xd'][0]
    ids = [xdts[0]['id'], xd['id'], xdts[1]['id'], xdts[2]['id'], xdts[3]['id']]
    out = pg.evaluate(XD_THRU_JS, [ids, 90])
    assert len(out['checks']) == 1, out
    c = out['checks'][0]
    assert c['kind'] == 'amps' and c['box'] == xd['id'] and c['rated'] == 2, c
    assert c['amps'] == pytest.approx(3 * 90 / 120), c
    assert c['text'] == f"{xd['title']} thru: 2.25 A to the boxes after it, rated for 2 A.", c
    assert out['strip'] == [[True, c['text']]], out
    # the XD's pill, not the XD-T heading the chain
    assert out['drawn'] == [[xd['id']]], out
    assert c['text'] in out['notes'], out['notes']
    assert not errors


def test_no_figure_box_adds_nothing_and_is_named(page):
    """A box with no published figure adds nothing and is named."""
    pg, errors = page
    _setup(pg)
    xs = _boxes(pg)['brompton-xd-s'][0]
    out = pg.evaluate("""(id) => {
        const app = window.app, a = app.project.layers[0];
        const dev = app._processorCatalog.devices.find(d => d.id === 'brompton-xd-s');
        const saved = dev.power.watts;
        delete dev.power.watts;
        try {
            app._boxPowerMemo = null;
            app.setBoxPower(id, { kind: 'start', layerId: a.id, circuit: 1 });
            const leg = app.getSocaPlan(a)[0].legs[0];
            return { watts: leg.watts, named: app.boxPowerUnfigured(),
                     warn: app.binderCannotFitWarning(app.readBinderOptions()) };
        } finally { dev.power.watts = saved; app._boxPowerMemo = null; }
    }""", xs['id'])
    assert out['watts'] == pytest.approx(1800)
    assert out['named'] == [xs['title']]
    assert f"no power figure: {xs['title']}" in out['warn']
    assert not errors


# ---- locked, removed, moved -----------------------------------------------------------

def test_locked_screen_refuses(page):
    """A locked WALL A: powering a box on its circuit, chaining onto one
    already there and removing it all refuse with the locked dialog."""
    pg, errors = page
    _setup(pg)
    b = _boxes(pg)
    head, nxt = b['brompton-xd-t'][0]['id'], b['brompton-xd-t'][1]['id']
    pg.evaluate("(id) => window.app.setBoxPower(id, { kind: 'start', layerId: window.app.project.layers[0].id, circuit: 1 })",
                head)
    pg.evaluate("() => { window.app.project.layers[0].locked = true; window.app.__locked.length = 0; }")
    s0 = _state(pg)
    menu = _right_click(pg, pg.evaluate(CABINET_JS, {'name': 'WALL A', 'circuit': 2}))
    _pick(pg, menu, 'Power a breakout box at the start of', b['brompton-xd-t'][2]['title'])
    assert pg.evaluate("([a, z]) => window.app.chainBoxPower(a, z)", [head, nxt]) is False
    assert pg.evaluate("(id) => window.app.removeBoxPower(id)", head) is False
    s1 = _state(pg)
    assert s1['store'] == s0['store'] and s1['saves'] == s0['saves']
    assert s1['locked'] == [['WALL A'], ['WALL A'], ['WALL A']]
    pg.evaluate("() => { window.app.project.layers[0].locked = false; }")
    assert not errors


def test_remove_box_takes_its_feed(page):
    """Removing a powered box from its card takes its feed - and the chain
    after it - in the same undo step."""
    pg, errors = page
    _setup(pg)
    b = _boxes(pg)
    head, nxt = b['brompton-xd'][1]['id'], b['brompton-xd'][2]['id']
    pg.evaluate("(id) => window.app.setBoxPower(id, { kind: 'end', layerId: window.app.project.layers[0].id, circuit: 2 })",
                head)
    assert pg.evaluate("([a, z]) => window.app.chainBoxPower(a, z)", [head, nxt])
    out = pg.evaluate("""async (id) => {
        const app = window.app;
        const hit = app.boxPowerBoxes().find(b => b.box.id === id);
        await app._processorRequest(`/api/processors/${hit.proc.id}/cvts/${id}`, 'DELETE', undefined, 'Remove Breakout Box');
        return JSON.parse(JSON.stringify(app.project.boxPower || {}));
    }""", head)
    assert head not in out and nxt not in out
    pg.evaluate("() => window.app.undo()")
    pg.wait_for_timeout(600)
    back = pg.evaluate("async () => { await window.app.refreshProcessors(); return window.app.project.boxPower || {}; }")
    assert head in back and nxt in back
    assert not errors


def test_copies_never_carry_feeds(page):
    """Duplicate Screen (Cmd+J), Copy and Paste (Cmd+C, Cmd+V) and Duplicate
    Canvas each make a screen with no box on its circuits: the store is
    untouched and the original keeps its box. (No processor or box is ever
    duplicated by the app: a new box has a new id and no feed.)"""
    pg, errors = page
    _setup(pg)
    xd = _boxes(pg)['brompton-xd'][0]['id']
    pg.evaluate("(id) => window.app.setBoxPower(id, { kind: 'start', layerId: window.app.project.layers[0].id, circuit: 1 })", xd)
    store = _state(pg)['store']
    mod = 'Meta' if sys.platform == 'darwin' else 'Control'
    probe = """(ids) => {
        const app = window.app, a = app.project.layers[0];
        const fresh = app.project.layers.filter(l => !ids.includes(l.id) && (l.type || 'screen') === 'screen');
        return { fresh: fresh.length, onCopies: fresh.reduce((t, l) => t + app.screenCircuits(l)
                     .reduce((u, c) => u + app.boxPowerOnCircuit(l, c.num).length, 0), 0),
                 onA: app.boxPowerOnCircuit(a, 1).length,
                 store: JSON.parse(JSON.stringify(app.project.boxPower || {})) };
    }"""
    select = """() => { const app = window.app; app.currentLayer = app.project.layers[0];
        app.selectedLayerIds = new Set([app.currentLayer.id]);
        if (document.activeElement) document.activeElement.blur(); return app.project.layers.map(l => l.id); }"""
    for how, keys in (('Duplicate', [f'{mod}+j']), ('Paste', [f'{mod}+c', f'{mod}+v'])):
        before = pg.evaluate(select)
        for k in keys:
            pg.keyboard.press(k)
            pg.wait_for_timeout(300)
        pg.wait_for_timeout(1200)
        out = pg.evaluate(probe, before)
        assert out['fresh'] >= 1, how
        assert out['onCopies'] == 0 and out['onA'] == 1, (how, out)
        assert out['store'] == store, how
    before = pg.evaluate("() => window.app.project.layers.map(l => l.id)")
    out = pg.evaluate("""async (ids) => {
        const app = window.app;
        const cid = app.project.canvases[0].id;
        await fetch(`/api/canvas/${cid}/duplicate`, { method: 'POST' });
        app.project = await (await fetch('/api/project')).json();
        app._boxPowerMemo = null;
        const fresh = app.project.layers.filter(l => !ids.includes(l.id) && (l.type || 'screen') === 'screen');
        return { fresh: fresh.length, onCopies: fresh.reduce((t, l) => t + app.screenCircuits(l)
                     .reduce((u, c) => u + app.boxPowerOnCircuit(l, c.num).length, 0), 0),
                 store: JSON.parse(JSON.stringify(app.project.boxPower || {})) };
    }""", before)
    assert out['fresh'] >= 1 and out['onCopies'] == 0, out
    assert out['store'] == store
    # the copies go, so the screens the later tests build on stay two
    pg.evaluate("""async (ids) => {
        const app = window.app;
        const p = await (await fetch('/api/project')).json();
        p.layers = p.layers.filter(l => ids.includes(l.id));
        p.canvases = p.canvases.slice(0, 1);
        p.groups = [];
        await fetch('/api/project', { method: 'PUT', headers: {'Content-Type': 'application/json'},
                                      body: JSON.stringify(p) });
        app.project = await (await fetch('/api/project')).json();
        app.currentLayer = app.project.layers[0];
        app.selectedLayerIds = new Set([app.currentLayer.id]);
        app.renderLayers();
    }""", before[:2])
    assert not errors


def test_a_deleted_screen_or_distro_takes_its_box_feeds(page):
    """A screen deleted takes the feeds on its circuits (and the chains off
    them) on the server; a distro removed takes the boxes fed off it. A new
    distro that gets the old id carries nothing; undo puts it all back."""
    pg, errors = page
    _setup(pg)
    b = _boxes(pg)
    head, nxt, cvt = b['brompton-xd-t'][0]['id'], b['brompton-xd-t'][1]['id'], b['novastar-cvt10'][0]['id']
    out = pg.evaluate("""([h, n, c]) => {
        const app = window.app, w = app.project.layers[1];
        app.setBoxPower(h, { kind: 'start', layerId: w.id, circuit: 1 });
        app.chainBoxPower(h, n);
        app.setBoxPower(c, { kind: 'distro', distroId: 'd1', number: 2, tail: 3 });
        app.removeDistro('d1');
        const after = Object.keys(app.project.boxPower || {}).sort();
        const d = app.addDistro({ system: '120/208' });
        return { after, newId: d.id, onNew: app.boxPowerOnDistros().length };
    }""", [head, nxt, cvt])
    assert out['after'] == sorted([head, nxt])
    assert out['onNew'] == 0
    pg.evaluate("() => { window.app.undo(); window.app.undo(); }")
    pg.wait_for_timeout(300)
    assert cvt in _state(pg)['store']
    # the screen goes through the server, which drops the feeds on it
    out = pg.evaluate("""async (h) => {
        const app = window.app, w = app.project.layers[1];
        const p = await (await fetch(`/api/layer/${w.id}`, { method: 'DELETE' })).json();
        return Object.keys(p.boxPower || {});
    }""", head)
    assert head not in out and nxt not in out and cvt in out, out
    pg.evaluate(SEED_JS)
    assert not errors


def test_a_missing_circuit_is_no_feed(page):
    """A box on circuit 2 of WALL A: a repack that leaves WALL A one circuit
    takes its feed everywhere - no load, no pull row, no binder row, and its
    gear reads unpowered - without touching the store, until the change's
    undo step is taken: there the box follows its panel or loses its power
    (test_a_box_follows_its_panel_..., test_a_box_whose_panel_stops_...)."""
    pg, errors = page
    _setup(pg)
    xd = _boxes(pg)['brompton-xd'][0]['id']
    out = pg.evaluate("""(id) => {
        const app = window.app, a = app.project.layers[0];
        app.setBoxPower(id, { kind: 'end', layerId: a.id, circuit: 2 });
        app.setBoxPowerCable(id, { ft: 10 });
        const before = { powered: !!app.boxPowerOf(id), watts: app.boxPowerScreenWatts(a) };
        a.panelWatts = 100;            // 12 x 100 = 1200 W: one circuit
        app._circuitTailCache = null;
        app._boxPowerStandMemo = null;
        const circuits = app.screenCircuits(a).length;
        const pull = app.buildPullList().totals.filter(r => /breakout box power/.test(r.notes || '')).length;
        return { before, circuits, powered: !!app.boxPowerOf(id), watts: app.boxPowerScreenWatts(a),
                 placements: app.boxPowerPlacements().length, pull,
                 rows: app._bBoxPowerRows([a]).length, stored: !!app.project.boxPower[id],
                 load: app.getCarriedPowerLoad(a).watts };
    }""", xd)
    assert out['before']['powered'] and out['before']['watts'] > 0
    assert out['circuits'] == 1
    assert out['powered'] is False and out['watts'] == 0 and out['placements'] == 0
    assert out['pull'] == 0 and out['rows'] == 0
    assert out['load'] == pytest.approx(1200)
    assert out['stored'] is True
    assert not errors


def test_totals_agree(page):
    """A box on WALL A's circuit 1 and one straight off d1: the screen's
    readout, its wall load, the binder's screen Load and the show's totals
    all take them."""
    pg, errors = page
    _setup(pg)
    b = _boxes(pg)
    xdt, cvt = b['brompton-xd-t'][0]['id'], b['novastar-cvt10'][0]['id']
    out = pg.evaluate("""([t, c]) => {
        const app = window.app, a = app.project.layers[0];
        const before = { show: app.getPowerCounts().totalWatts, readout: app._powerReadoutFor(a).amps1,
                         facts: app._bScreenFacts(a).watts, carried: app.getCarriedPowerLoad(a).watts };
        app.setBoxPower(t, { kind: 'start', layerId: a.id, circuit: 1 });
        app.setBoxPower(c, { kind: 'distro', distroId: 'd1', number: 2, tail: 3 });
        return { before, after: { show: app.getPowerCounts().totalWatts, readout: app._powerReadoutFor(a).amps1,
                                   facts: app._bScreenFacts(a).watts, carried: app.getCarriedPowerLoad(a).watts } };
    }""", [xdt, cvt])
    bf, af = out['before'], out['after']
    assert af['carried'] == pytest.approx(bf['carried'] + 50)
    assert af['facts'] == pytest.approx(bf['facts'] + 50)
    assert af['readout'] == pytest.approx(bf['readout'] + 50 / 120)
    assert af['show'] == pytest.approx(bf['show'] + 50 + 18)
    assert af['facts'] == pytest.approx(af['carried'])
    assert not errors


def test_dealing_skips_a_box_output_and_a_clash_is_warned(page):
    """With a CVT10 straight off output 2, WALL B's multi is dealt past it;
    pinned onto output 2 by hand, the distro's checks name the clash."""
    pg, errors = page
    _setup(pg)
    cvt = _boxes(pg)['novastar-cvt10'][0]['id']
    out = pg.evaluate("""(c) => {
        const app = window.app, b = app.project.layers[1];
        app.setBoxPower(c, { kind: 'distro', distroId: 'd1', number: 2, tail: 1 });
        app.setSocaDistro(b, 1, 'd1', false);
        app._circuitTailCache = null;
        const dealt = app._powerNaming(b).socas.get(1).number;
        const d = app.getDistros().find(x => x.id === 'd1');
        const free = app.faceRowFreeBoxes(d, app.distroFace(d).rowInfo.get('r1')).map(x => x.number);
        app.setSocaNumber(b, 1, 2, false);
        app._circuitTailCache = null;
        const checks = app.distroChecks(d).map(w => w.text);
        return { dealt, free, checks };
    }""", cvt)
    assert out['dealt'] != 2, out
    assert 2 not in out['free'], out
    assert any('Breakout box' in t and 'is on that circuit too' in t for t in out['checks']), out['checks']
    assert not errors


def test_three_phase_legs_and_neutral_off_a_distro(page):
    """Boxes alone on distros of their own. An XD-T off a 120 V Socapex
    circuit of a 120/208 distro: one leg 50 / 120 A, and the neutral
    I x sqrt(1 + h^2) at the show's supply harmonics h. An XD off a 208 V
    line-to-line circuit: 51.1 W at 208 V, 51.1 / 208 = 0.2457 A on each
    of its two legs, the third leg nothing, no neutral."""
    pg, errors = page
    _setup(pg)
    b = _boxes(pg)
    xdt, xd = b['brompton-xd-t'][0]['id'], b['brompton-xd'][0]['id']
    out = pg.evaluate("""([t, x]) => {
        const app = window.app;
        app.project.distros.push(
            { id: 'd8', name: 'LN', ratingA: 100, system: '120/208', voltage: 208, phase: 3,
              outputRows: [{ id: 'r1', connector: 'soca', count: 1, coupling: 'ln', breakerA: 20 }] },
            { id: 'd9', name: 'LL', ratingA: 100, system: '120/208', voltage: 208, phase: 3,
              outputRows: [{ id: 'r1', connector: 'soca', count: 1, coupling: 'll', breakerA: 20 }] });
        app._distroFaceMemo = null;
        app.getDistros();
        app.setBoxPower(t, { kind: 'distro', distroId: 'd8', number: 1, tail: 2 });
        app.setBoxPower(x, { kind: 'distro', distroId: 'd9', number: 1, tail: 1 });
        const L = (id) => app.getDistroLoads().find(z => z.id === id);
        const legs = (l) => ['X', 'Y', 'Z'].map(k => l.legs[k].amps);
        return { h: app.supplyTriplenFraction(null), ln: legs(L('d8')), lnN: L('d8').neutral.amps,
                 ll: legs(L('d9')), llN: L('d9').neutral };
    }""", [xdt, xd])
    i = 50 / 120
    assert sorted(out['ln']) == [pytest.approx(0), pytest.approx(0), pytest.approx(i)]
    assert out['lnN'] == pytest.approx(i * (1 + out['h'] ** 2) ** 0.5)
    xd_a = _xd_watts(208) / 208
    assert sorted(out['ll']) == [pytest.approx(0), pytest.approx(xd_a), pytest.approx(xd_a)]
    assert out['llN'] is None
    assert not errors


def test_a_208_v_circuit(page):
    """On 208 V walls the XD at the start of circuit 1 draws 51.1 W, and the
    circuit's amps are its watts over 208."""
    pg, errors = page
    _setup(pg, volts=208)
    xd = _boxes(pg)['brompton-xd'][0]['id']
    leg = pg.evaluate("""(id) => { const app = window.app, a = app.project.layers[0];
        app.setBoxPower(id, { kind: 'start', layerId: a.id, circuit: 1 });
        return app.getSocaPlan(a)[0].legs[0]; }""", xd)
    assert leg['boxWatts'] == pytest.approx(_xd_watts(208))
    assert leg['amps'] == pytest.approx(leg['watts'] / 208)
    assert not errors


def test_box_cable_rounds_to_the_stock_and_powercon_takes_a_coupler(page):
    """With a show stock of 10, 25 and 50 ft, a 30 ft box cable is pulled as
    its stock pieces, and a split powerCON cable adds a powerCON Coupler at
    each join. (The MX40 Pro feeds no screen here, so it is held on paper
    for this test: the paper rule has tests of its own.)"""
    pg, errors = page
    _setup(pg)
    cvt = _boxes(pg)['novastar-cvt10'][0]['id']
    out = pg.evaluate("""(c) => {
        const app = window.app, a = app.project.layers[0];
        app.project.cableStock = { perKind: false, ft: { all: [10, 25, 50] }, m: { all: [3, 10, 15] } };
        app.setBoxPower(c, { kind: 'start', layerId: a.id, circuit: 1 });
        app.setBoxPowerCable(c, { ft: 30 });
        const want = app.cableStockText(30, 'circuit');
        const off = app._pullProcOffPaper;
        app._pullProcOffPaper = () => false;
        let rows;
        try { rows = app.buildPullList().totals; } finally { app._pullProcOffPaper = off; }
        const out = { want, rows: rows.filter(r => /^powerCON/.test(r.type)).map(r => [r.type, r.length, r.qty]),
                      cable: app.boxPowerCable(c).text };
        delete app.project.cableStock;
        return out;
    }""", cvt)
    assert '+' in out['want'], out
    assert out['cable'] == f"{out['want']} powerCON"
    pieces = sorted(p for t, p, q in out['rows'] if t == 'powerCON Power Jump' for _ in range(q))
    assert sorted(out['want'].split('+')) == pieces, out
    assert ['powerCON Coupler', 'EA', len(pieces) - 1] in out['rows'], out
    assert not errors


def test_unreadable_length_says_so(page):
    pg, errors = page
    _setup(pg)
    xd = _boxes(pg)['brompton-xd'][0]['id']
    out = pg.evaluate("""(id) => { const app = window.app, a = app.project.layers[0];
        app.setBoxPower(id, { kind: 'start', layerId: a.id, circuit: 1 });
        app.project.boxPower[id].ft = 'abc';
        app._boxPowerMemo = null; app._boxPowerStandMemo = null;
        return { text: app.boxPowerCable(id).text,
                 notes: app.buildPullList().totals.filter(r => /breakout box power/.test(r.notes || '')).map(r => r.notes) };
    }""", xd)
    assert out['text'] == 'TRUE1, length unreadable'
    assert out['notes'] == ['breakout box power · length unreadable']
    assert not errors


# ---- the paper ---------------------------------------------------------------------------

def test_pull_sheet_lists_box_cables_and_chain_links(page):
    """Each box's cable and each chain link, with its length, on the pull
    sheet; a hidden screen's box is off it."""
    pg, errors = page
    _setup(pg)
    b = _boxes(pg)
    head, nxt, xs = b['brompton-xd-t'][0], b['brompton-xd-t'][1], b['brompton-xd-s'][0]
    rows = pg.evaluate("""([h, n, s]) => {
        const app = window.app, a = app.project.layers[0];
        app.setBoxPower(h, { kind: 'start', layerId: a.id, circuit: 1 });
        app.setBoxPowerCable(h, { ft: '25' });
        app.chainBoxPower(h, n);
        app.setBoxPowerCable(n, { ft: 6 });
        app.setBoxPower(s, { kind: 'distro', distroId: 'd1', number: 3, tail: 1 });
        app.setBoxPowerCable(s, { cable: 'edison-iec', ft: 10 });
        return app.buildPullList().totals.filter(r => /breakout box power|daisy chain/.test(r.notes || ''));
    }""", [head['id'], nxt['id'], xs['id']])
    got = sorted((r['type'], r['length'], r['notes']) for r in rows)
    assert got == sorted([
        ('TRUE1 Power Jump', "25'", 'breakout box power'),
        ('TRUE1 Power Jump', "6'", 'daisy chain'),
        ('Edison \u2192 IEC cable', "10'", 'breakout box power'),
    ]), got
    hidden = pg.evaluate("""() => {
        const app = window.app;
        app.project.layers[0].visible = false;
        try { return app.buildPullList().totals.filter(r => /breakout box power|daisy chain/.test(r.notes || ''))
                  .map(r => r.type); }
        finally { app.project.layers[0].visible = true; }
    }""")
    assert hidden == ['Edison \u2192 IEC cable']
    assert not errors


def test_binder_power_and_wiring_sheets_show_the_box(page):
    """WALL A's power sheet names the box in its circuit list and its
    Breakout box power table; its wiring sheet draws the box's block; the
    distro sheet names a distro-fed box."""
    pg, errors = page
    _setup(pg)
    b = _boxes(pg)
    head, cvt = b['brompton-xd-t'][0], b['novastar-cvt10'][0]
    out = pg.evaluate("""([h, c]) => {
        const app = window.app, a = app.project.layers[0];
        app.setBoxPower(h, { kind: 'start', layerId: a.id, circuit: 1 });
        app.setBoxPowerCable(h, { ft: 10 });
        app.setBoxPower(c, { kind: 'distro', distroId: 'd1', number: 2, tail: 3 });
        const opts = { ...app.readBinderOptions(), sides: { power: true, data: false } };
        const plan = app.planBinder(opts);
        const texts = (title) => {
            const i = plan.findIndex(p => p.title === title);
            if (i < 0) return null;
            const r = app.renderBinderPage(opts, i);
            return { texts: r.texts, wiring: r.wiring };
        };
        return { titles: plan.map(p => p.title), power: texts('WALL A - Power - Front View'),
                 wiring: texts('WALL A - Power Wiring'),
                 distro: plan.filter(p => /SL/.test(p.title)).map(p => texts(p.title)) };
    }""", [head['id'], cvt['id']])
    assert out['power'], out['titles']
    joined = ' '.join(t if isinstance(t, str) else str(t.get('text', '')) for t in out['power']['texts'])
    assert 'BREAKOUT BOX POWER' in joined.upper()
    assert f"breakout box {head['title']} at the start" in joined
    assert "10' TRUE1" in joined
    assert out['wiring'], out['titles']
    wj = ' '.join(t if isinstance(t, str) else str(t.get('text', '')) for t in out['wiring']['texts'])
    assert f"{head['title']} · breakout box at the start · 10' TRUE1" in wj
    dj = ' '.join(t if isinstance(t, str) else str(t.get('text', ''))
                  for d in out['distro'] if d for t in d['texts'])
    assert f"breakout box {cvt['title']}" in dj
    assert not errors


def test_simple_power_page_and_facts_totals_show_the_box(page):
    """The Simple binder's WALL A power sheet (its one POWER WIRING sheet)
    names the box in its circuit list and lists it under Breakout box power; the FACTS sheet's WALL A
    row and its Total take the box on its circuit, and a row of its own
    takes the box straight off a distro."""
    pg, errors = page
    _setup(pg)
    b = _boxes(pg)
    xdt, cvt = b['brompton-xd-t'][0], b['novastar-cvt10'][0]
    out = pg.evaluate("""([t, c]) => {
        const app = window.app, a = app.project.layers[0];
        app.setBoxPower(t, { kind: 'start', layerId: a.id, circuit: 1 });
        app.setBoxPowerCable(t, { ft: 10 });
        app.setBoxPower(c, { kind: 'distro', distroId: 'd1', number: 2, tail: 3 });
        const join = (r) => (r.texts || []).map(x => typeof x === 'string' ? x : String(x.text || '')).join(' | ');
        const page = (opts, pick) => {
            const plan = app.planBinder(opts);
            const i = plan.findIndex(pick);
            return i < 0 ? null : { title: plan[i].title, text: join(app.renderBinderPage(opts, i)) };
        };
        const base = { ...app.readBinderOptions(), sides: { power: true, data: false } };
        // in Simple, a screen's power is one POWER WIRING sheet: drawing and tables
        const simple = page({ ...base, mode: 'simple' }, p => p.sheetTitle === 'WALL A · POWER WIRING · FRONT VIEW');
        const facts = page({ ...base, mode: 'full' }, p => p.kind === 'facts');
        const wallW = app._bScreenFacts(a).watts;
        const wallB = app._bScreenFacts(app.project.layers[1]).watts;
        return { simple, facts, wallW: app._bNum(wallW, 0), total: app._bNum(wallW + wallB + 18, 0),
                 fed: app._bNum(18, 0) };
    }""", [xdt['id'], cvt['id']])
    assert out['simple'], out
    st = out['simple']['text']
    assert f"breakout box {xdt['title']} at the start" in st, st
    assert 'BREAKOUT BOX POWER' in st.upper() and "10' TRUE1" in st, st
    assert out['facts'], out
    ft = out['facts']['text']
    assert out['wallW'] in ft and '1 breakout box on distros' in ft and out['total'] in ft, (out, ft)
    assert not errors


def test_grouped_wall_draws_the_box_on_its_own_member(page):
    """Three screens grouped as one wall: a circuit that starts on the
    second member has its box drawn in that member's pass, and the wall's
    wiring sheet wires it."""
    pg, errors = page
    pg.evaluate(GROUP_JS)
    xd = _boxes(pg)['brompton-xd'][0]['id']
    out = pg.evaluate("""(id) => {
        const app = window.app;
        const owner = app.project.layers.find(l => l.name === 'W1');
        const w2 = app.project.layers.find(l => l.name === 'W2');
        const c = app.screenCircuits(owner).find(c => c.layers && c.layers[0] && c.layers[0].id === w2.id);
        if (!c) return { missing: app.screenCircuits(owner).map(c => (c.layers || []).map(l => l.name)) };
        const opts = { ...app.readBinderOptions(), sides: { power: true, data: false } };
        const runs = () => {
            const plan = app.planBinder(opts);
            const i = plan.findIndex(p => p.kind === 'wiring');
            return i < 0 ? null : app.renderBinderPage(opts, i).wiring.halves[0].runs;
        };
        const before = runs();
        app.setBoxPower(id, { kind: 'start', layerId: owner.id, circuit: c.num });
        window.canvasRenderer.render();
        const log = app._boxPowerDrawnLog || new Map();
        return { before, after: runs(), w2: String(w2.id),
                 drawnOn: [...log.entries()].filter(([k, v]) => v.includes(id)).map(([k]) => k),
                 hit: (window.canvasRenderer._boxPowerHits || []).some(h => h.boxId === id) };
    }""", xd)
    assert 'missing' not in out, out
    assert out['hit'] is True
    assert out['drawnOn'] == [out['w2']], out
    assert len(out['after']) == len(out['before']) + 1, out
    assert not errors


# The wall of tests/test_group_power_draw.py, three members routed as one,
# with this module's processors kept.
GROUP_JS = """async () => {
    const app = window.app;
    const screen = (o) => {
        o = Object.assign({ type: 'screen', visible: true, locked: false, columns: 3, rows: 4,
            cabinet_width: 128, cabinet_height: 128, offset_x: 0, offset_y: 0, panel_weight: 20,
            weight_unit: 'kg', panelWatts: 150, powerVoltage: 208, powerAmperage: 20,
            processorType: 'brompton', bitDepth: 8, frameRate: 60, lowLatency: false,
            flowPattern: 'tl-h', portMappingMode: 'organized', powerFlowPattern: 'tl-v',
            lastPowerFlowPattern: 'tl-v', powerCustomPath: false, powerOrganized: true,
            powerMaximize: false, powerBreakoutType: 'soca-true1',
            powerSplitters: { enabled: true, maxWays: 2, manual: { merge: [], split: [] } },
            powerCustomPaths: {}, powerCustomOverrides: [], powerCustomIndex: 1, group_id: null,
            powerSocaDistro: {}, powerSocaNumber: {}, powerSocaLengths: {}, powerCircuitCables: {},
            powerSocaKeying: 'index' }, o);
        o.panels = [];
        for (let r = 0; r < o.rows; r++) for (let c = 0; c < o.columns; c++) {
            o.panels.push({ row: r, col: c, x: o.offset_x + c * o.cabinet_width, y: o.offset_y + r * o.cabinet_height,
                width: o.cabinet_width, height: o.cabinet_height, hidden: false, blank: false, halfTile: 'none' });
        }
        return o;
    };
    const canvas = (id, x) => ({ id, name: id, color: '#4A90E2', visible: true, raster_width: 3840,
        raster_height: 2160, show_raster_width: 3840, show_raster_height: 2160, workspace_x: x,
        workspace_y: 0, show_workspace_x: x, show_workspace_y: 0, data_flow_perspective: 'front',
        power_perspective: 'front' });
    const p = await (await fetch('/api/project')).json();
    Object.assign(p, {
        canvases: [canvas('c1', 0), canvas('c2', 5000), canvas('c3', 10000)], active_canvas_id: 'c1',
        groups: [{ id: 'g1', name: 'Wall', layer_ids: [1, 2, 3] }],
        layers: [
            screen({ id: 1, name: 'W1', columns: 3, group_id: 'g1', canvas_id: 'c2', show_canvas_id: 'c1',
                     showOffsetX: 0, showOffsetY: 0 }),
            screen({ id: 2, name: 'W2', columns: 6, group_id: 'g1', canvas_id: 'c1', showOffsetX: 384, showOffsetY: 0 }),
            screen({ id: 3, name: 'W3', columns: 3, group_id: 'g1', canvas_id: 'c3', show_canvas_id: 'c1',
                     showOffsetX: 1152, showOffsetY: 0 }),
        ], distros: [] });
    delete p.boxPower;
    await fetch('/api/project', { method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(p) });
    app.project = await (await fetch('/api/project')).json();
    app.dedupeProjectLayers('box_power_group');
    app.selectLayer(app.project.layers[0]);
    app._circuitTailCache = null;
    app._boxPowerMemo = null;
    await app.refreshProcessors();
    app.renderLayers();
    window.canvasRenderer.fitToView();
    window.canvasRenderer.render();
    return true;
}"""


def _segs(run):
    p = run['points']
    return list(zip(p, p[1:]))


def test_wiring_runs_off_a_shared_disc_stand_apart_and_cross_no_note(page):
    """Every box powered from WALL A's circuits, the start and the end in
    turn: a circuit then feeds its multi's breakout AND a breakout box, so
    two runs leave its one disc. They used to leave it the same way, one
    on top of the other for some 64 units, and the box's note naming the
    circuit ("SL1-2" against its socket 1) stood centred on the socket, so
    the box's own run came down through it. Now the second run leaves the
    disc a pen's width off the first, and a note stands beside the run
    into its socket - no run crosses a socket's note."""
    pg, errors = page
    _setup(pg)
    b = _boxes(pg)
    ids = [x['id'] for v in b.values() for x in v]
    out = pg.evaluate("""(ids) => {
        const app = window.app, a = app.project.layers[0];
        const circ = (app.screenCircuits(a) || []).map(c => c.num);
        ids.forEach((id, i) => app.setBoxPower(id, { kind: i % 2 ? 'end' : 'start', layerId: a.id,
                                                     circuit: circ[i % circ.length] }));
        // the full set, whatever the Simple tests left chosen
        const opts = { ...app.readBinderOptions(), mode: 'full', sides: { power: true, data: false } };
        const plan = app.planBinder(opts);
        // (the first wall, whatever an earlier test named it)
        const i = plan.findIndex(p => p.title === `${a.name} - Power Wiring`);
        if (i < 0) return { titles: plan.map(p => p.title) };
        return { halves: (app.renderBinderPage(opts, i).wiring || {}).halves || [] };
    }""", ids)
    assert out.get('halves') and len(out['halves']) == 1, out
    h = out['halves'][0]
    pen = (1.4 + 3.2) * h['scale']
    # a disc that sends two runs - the very case
    by_disc = {}
    for r in h['runs']:
        by_disc.setdefault(r['from'], []).append(r)
    shared = {k: v for k, v in by_disc.items() if len(v) > 1}
    assert shared, sorted(by_disc)
    for name, runs in shared.items():
        for i, r in enumerate(runs):
            for o in runs[i + 1:]:
                for a0, a1 in _segs(r):
                    for b0, b1 in _segs(o):
                        for k in (0, 1):          # 0: verticals at x, 1: horizontals at y
                            if abs(a0[k] - a1[k]) > 0.01 or abs(b0[k] - b1[k]) > 0.01:
                                continue
                            lo = max(min(a0[1 - k], a1[1 - k]), min(b0[1 - k], b1[1 - k]))
                            hi = min(max(a0[1 - k], a1[1 - k]), max(b0[1 - k], b1[1 - k]))
                            assert not (abs(a0[k] - b0[k]) < pen and hi - lo > 0.5), (
                                'two runs off one disc print as one', name, r['device'], o['device'])
    notes = [(blk['title'], s) for blk in h['blocks'] for s in blk['sockets'] if s.get('note')]
    assert notes, 'no socket note on the sheet'
    pad = pen / 2
    for title, s in notes:
        nb = s['noteBox']
        assert nb and nb['w'] > 0, (title, s)
        for r in h['runs']:
            for a, c in _segs(r):
                x0, x1 = sorted((a[0], c[0]))
                y0, y1 = sorted((a[1], c[1]))
                assert not (x1 + pad > nb['x'] and x0 - pad < nb['x'] + nb['w']
                            and y1 + pad > nb['y'] and y0 - pad < nb['y'] + nb['h']), (
                    'a run crosses a socket note', title, s['note'], r['from'])
    assert not errors


# Every line the map strokes AFTER a disc's lettering, checked against the
# lettering's box on the same bitmap (device pixels, so whatever frame the
# disc and the line were drawn in), and the sheet's own runs against the
# discs it logged. Arcs (a disc's own rim) are not lines and are not read.
STROKES_OVER_LABELS_JS = """(ids) => {
    const app = window.app, a = app.project.layers[0], r = window.canvasRenderer;
    const circ = (app.screenCircuits(a) || []).map(c => c.num);
    ids.forEach((id, i) => app.setBoxPower(id, { kind: i % 2 ? 'end' : 'start', layerId: a.id,
                                                 circuit: circ[i % circ.length] }));
    const opts = { ...app.readBinderOptions(), mode: 'full', sides: { power: true, data: false } };
    const plan = app.planBinder(opts);
    const i = plan.findIndex(p => p.title === `${a.name} - Power Wiring`);
    if (i < 0) return { titles: plan.map(p => p.title) };
    const P = CanvasRenderingContext2D.prototype;
    const orig = { beginPath: P.beginPath, moveTo: P.moveTo, lineTo: P.lineTo, stroke: P.stroke };
    const label = r._fillWrappedLabel;
    const boxes = [], over = [];
    let path = [];
    const mine = (c) => c === r.ctx;
    const dev = (c, x, y) => { const m = c.getTransform();
                               return [m.a * x + m.c * y + m.e, m.b * x + m.d * y + m.f]; };
    r._fillWrappedLabel = function (ls, x, y, fontPx) {
        if (Array.isArray(ls) && ls.length && this.ctx) {
            const w = Math.max(...ls.map(t => this.ctx.measureText(t).width));
            const h = (fontPx || 14) * ls.length;
            const c0 = dev(this.ctx, x - w / 2, y - h / 2), c1 = dev(this.ctx, x + w / 2, y + h / 2);
            boxes.push({ text: ls.join(''), canvas: this.ctx.canvas,
                         x0: Math.min(c0[0], c1[0]), x1: Math.max(c0[0], c1[0]),
                         y0: Math.min(c0[1], c1[1]), y1: Math.max(c0[1], c1[1]) });
        }
        return label.apply(this, arguments);
    };
    P.beginPath = function () { if (mine(this)) path = []; return orig.beginPath.apply(this, arguments); };
    P.moveTo = function (x, y) { if (mine(this)) path.push([dev(this, x, y)]); return orig.moveTo.apply(this, arguments); };
    P.lineTo = function (x, y) {
        if (mine(this)) { if (!path.length) path.push([]); path[path.length - 1].push(dev(this, x, y)); }
        return orig.lineTo.apply(this, arguments);
    };
    P.stroke = function () {
        if (mine(this) && !arguments.length) {
            const half = this.lineWidth / 2;
            for (const sub of path) for (let k = 1; k < sub.length; k++) {
                const [p, q] = [sub[k - 1], sub[k]];
                for (const b of boxes) {
                    if (b.canvas !== this.canvas) continue;
                    // the segment's own box against the lettering's (the
                    // map's lines are all square to the wall)
                    if (Math.max(p[0], q[0]) + half > b.x0 && Math.min(p[0], q[0]) - half < b.x1
                        && Math.max(p[1], q[1]) + half > b.y0 && Math.min(p[1], q[1]) - half < b.y1) {
                        over.push({ text: b.text, colour: String(this.strokeStyle), from: p, to: q });
                    }
                }
            }
        }
        return orig.stroke.apply(this, arguments);
    };
    let out;
    try {
        out = (app.renderBinderPage(opts, i).wiring || {}).halves || [];
    } finally {
        Object.assign(P, orig);
        delete r._fillWrappedLabel;
        if (r._fillWrappedLabel !== label) r._fillWrappedLabel = label;
    }
    return { halves: out, over, labels: boxes.length };
}"""


def test_wiring_no_line_crosses_a_disc_label(page):
    """A box powered at the START of a circuit is fed from the circuit's
    first cabinet, where the circuit's own disc stands. The map's feed line
    for it ran from that cabinet's middle - the disc's middle - out to the
    wall's edge, drawn after the disc, so on the Power Wiring sheet a dark
    stroke crossed "SL1-1". The feed is now drawn under the circuits and
    their discs: no line the map strokes after a disc crosses its
    lettering, and no run the sheet draws comes into a disc's lettering."""
    pg, errors = page
    _setup(pg)
    b = _boxes(pg)
    ids = [x['id'] for v in b.values() for x in v]
    out = pg.evaluate(STROKES_OVER_LABELS_JS, ids)
    assert out.get('halves') and len(out['halves']) == 1, out
    assert out['labels'], 'no disc lettering seen on the map'
    assert not out['over'], ('a line drawn over a disc\'s lettering', out['over'][:4])
    h = out['halves'][0]
    assert h['discs'], h
    for d in h['discs']:
        # the lettering sits inside the disc's middle
        q = d['r'] * 0.7
        for r in h['runs']:
            for a, c in _segs(r):
                x0, x1 = sorted((a[0], c[0]))
                y0, y1 = sorted((a[1], c[1]))
                assert not (x1 > d['x'] - q and x0 < d['x'] + q
                            and y1 > d['y'] - q and y0 < d['y'] + q), (
                    'a run comes into a disc\'s lettering', d['text'], r['from'], r['device'])
    assert not errors


END_WIRING_JS = """([x, mode]) => {
    const app = window.app, a = app.project.layers[0];
    app.setBoxPower(x, { kind: 'end', layerId: a.id, circuit: 1 });
    const opts = { ...app.readBinderOptions(), mode, sides: { power: true, data: false } };
    const plan = app.planBinder(opts);
    const i = plan.findIndex(p => mode === 'simple'
        ? p.sheetTitle === `${a.name} · POWER WIRING · FRONT VIEW` : p.title === `${a.name} - Power Wiring`);
    if (i < 0) return { titles: plan.map(p => p.title) };
    const c = app.screenCircuits(a).find(z => z.num === 1);
    const last = c.panels[c.panels.length - 1];
    return { halves: (app.renderBinderPage(opts, i).wiring || {}).halves || [],
             label: app.getPowerCircuitLabel(a, 1), lastCol: last.col, cols: a.columns };
}"""


@pytest.mark.parametrize('mode', ['full', 'simple'])
def test_wiring_a_box_at_the_end_leaves_the_last_panel(page, mode):
    """A box powered at a circuit's END is fed from the run's last panel
    (owner, 2026-11-19): on the Power Wiring sheet, full and Simple, its line
    leaves a dot on that panel, not the circuit's label disc on its first
    panel, which the multi's own run still leaves."""
    pg, errors = page
    _setup(pg)
    xd = _boxes(pg)['brompton-xd'][0]
    out = pg.evaluate(END_WIRING_JS, [xd['id'], mode])
    assert out.get('halves'), out
    h = out['halves'][0]
    ends = [d for d in h['discs'] if d.get('end')]
    label = [d for d in h['discs'] if not d.get('end') and d['text'] == out['label']]
    assert len(ends) == 1 and label, h['discs']
    end, lab = ends[0], label[0]
    # the dot is inside the last panel, a panel's width or more from the label
    pnl = end['panel']
    assert pnl['x'] <= end['x'] <= pnl['x'] + pnl['w'] and pnl['y'] <= end['y'] <= pnl['y'] + pnl['h'], end
    assert abs(end['x'] - lab['x']) >= pnl['w'] * 0.9 or abs(end['y'] - lab['y']) >= pnl['h'] * 0.9, (end, lab)
    assert end['r'] < lab['r'], (end, lab)
    # the box's run starts at the dot
    runs = [r for r in h['runs'] if r['device'].startswith(xd['title'])]
    assert len(runs) == 1, h['runs']
    x0, y0 = runs[0]['points'][0]
    assert ((x0 - end['x']) ** 2 + (y0 - end['y']) ** 2) ** 0.5 <= end['r'] * 2 + 1, (runs[0]['points'][:2], end)
    assert not errors
