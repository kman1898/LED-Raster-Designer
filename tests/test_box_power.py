"""Powering a breakout box from the walls' power circuits, and the XD / XD-T
daisy chain (owner rulings, 2026-11-18; app-box-power.js).

  * A box is powered, per box, from the START of a circuit, its END, an
    OPEN circuit or output on a distro (by itself), or a spare leg of a
    fan-out (a shared 2fer / 3fer circuit). Each is a right-click on the
    Power tab: a circuit's first cabinet (its tag sits there) or last, a
    free chip in the Power tray, a shared circuit. Removing it is a
    right-click too. One undo step each; a locked screen refuses.
  * Only the XD and XD-T (TRUE1 in and thru) daisy chain. Past 5 boxes in
    one chain, or past 2 A through the first box's thru, is warned in gold,
    never refused.
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


# ---- (c) an open circuit on a distro -----------------------------------------------

def test_open_distro_circuit_by_right_click(page):
    """Right-click output 2's free circuit 3 in the Power tray: the CVT10
    rides it by itself, 18 W on d1 (a 120 V circuit: 0.15 A on its leg)."""
    pg, errors = page
    _setup(pg)
    pg.evaluate("() => window.app.setHardwareDockMode ? window.app.setHardwareDockMode('power') : null")
    cvt = _boxes(pg)['novastar-cvt10'][0]
    before = pg.evaluate("() => window.app.getDistroLoads().find(x => x.id === 'd1').watts")
    at = pg.evaluate(CHIP_JS, {'d': 'd1', 'number': 2, 'tail': 3})
    assert at, 'no free chip'
    menu = _right_click(pg, at)
    _pick(pg, menu, 'Power a breakout box from', cvt['title'])
    st = _state(pg)
    assert st['store'][cvt['id']]['at'] == {'kind': 'distro', 'distroId': 'd1', 'number': 2, 'tail': 3}
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


# ---- (d) a spare leg on a fan-out ----------------------------------------------------

def test_fanout_by_right_click(page):
    """WALL B's one circuit 2fer'd into a run per row: right-click it, "from
    the 2fer of", and the CVT4K-S (21 W) rides it."""
    pg, errors = page
    shape = _setup(pg, nfer=True)
    assert shape['b'] == [[1, 2]], shape
    k4 = _boxes(pg)['novastar-cvt4k-s'][0]
    menu = _right_click(pg, pg.evaluate(CABINET_JS, {'name': 'WALL B', 'row': 1, 'col': 1}))
    _pick(pg, menu, 'Power a breakout box from the 2fer of', k4['title'])
    st = _state(pg)
    assert st['store'][k4['id']]['at']['kind'] == 'fanout'
    leg = pg.evaluate("() => window.app.getSocaPlan(window.app.project.layers[1])[0].legs[0]")
    assert leg['boxWatts'] == pytest.approx(21)
    assert leg['watts'] == pytest.approx(600 + 21)
    assert not errors


# ---- the daisy chain ----------------------------------------------------------------

def test_daisy_chain_and_its_warnings(page):
    """A powered XD-T chains on by right-clicking its pill. Five XD-Ts at
    120 V: the head's thru carries 4 x 50 / 120 = 1.67 A, no warning. Six
    boxes is past 5: warned. At 110 V six XD-Ts put 5 x 50 / 110 = 2.27 A
    through the thru: past 2 A, warned too. Never refused."""
    pg, errors = page
    _setup(pg)
    b = _boxes(pg)
    chain = [x['id'] for x in b['brompton-xd-t']] + [b['brompton-xd'][0]['id'], b['brompton-xd'][1]['id']]
    head = chain[0]
    pg.evaluate("(id) => window.app.setBoxPower(id, { kind: 'start', layerId: window.app.project.layers[0].id, circuit: 2 })",
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
    # on to five XD-Ts... (four of them, then the XD)
    for up, down in zip(chain[1:4], chain[2:5]):
        assert pg.evaluate("([a, z]) => window.app.chainBoxPower(a, z)", [up, down])
    checks = pg.evaluate("() => window.app.boxPowerChainChecks()")
    assert checks == []
    w = pg.evaluate("() => window.app.getSocaPlan(window.app.project.layers[0])[0].legs[1].boxWatts")
    assert w == pytest.approx(4 * 50 + _xd_watts(120))
    assert pg.evaluate("([a, z]) => window.app.chainBoxPower(a, z)", [chain[4], chain[5]])
    checks = pg.evaluate("""() => window.app.boxPowerChainChecks().map(c => ({ count: c.count, amps: c.amps,
        over: c.over, text: c.text }))""")
    assert len(checks) == 1
    assert checks[0]['count'] == 6 and checks[0]['over'] == {'boxes': True, 'amps': False}
    # 3 XD-T + 2 XD after the head: (150 + 2 x 44.57) / 120 = 1.99 A
    assert checks[0]['amps'] == pytest.approx((3 * 50 + 2 * _xd_watts(120)) / 120)
    assert 'has 6 boxes' in checks[0]['text'] and '\u2014' not in checks[0]['text']
    # the tray says it in gold
    strip = pg.evaluate("""() => { window.app.renderHardwareDock();
        return (window.app._dockPowerWarnings || []).filter(w => w.boxChain).map(w => w.mild); }""")
    assert strip == [True]
    # 110 V: past 2 A as well
    pg.evaluate("""() => { const app = window.app; app.project.layers[0].powerVoltage = 110;
        app._boxPowerMemo = null; }""")
    checks = pg.evaluate("() => window.app.boxPowerChainChecks().map(c => ({ over: c.over, amps: c.amps }))")
    assert checks[0]['over'] == {'boxes': True, 'amps': True}
    assert checks[0]['amps'] == pytest.approx((3 * 50 + 2 * _xd_watts(110)) / 110)
    assert not errors


def test_chain_amps_warning_alone(page):
    """The 2 A reading on its own (a chain of five, the thru past 2 A):
    warned for the amps, not the count. No model on the catalog draws that
    much in five, so the figures are given."""
    pg, errors = page
    _setup(pg)
    b = _boxes(pg)
    ids = [x['id'] for x in b['brompton-xd-t']] + [b['brompton-xd'][0]['id']]
    pg.evaluate("(id) => window.app.setBoxPower(id, { kind: 'end', layerId: window.app.project.layers[0].id, circuit: 1 })",
                ids[0])
    for up, down in zip(ids, ids[1:]):
        assert pg.evaluate("([a, z]) => window.app.chainBoxPower(a, z)", [up, down])
    out = pg.evaluate("""() => {
        const app = window.app;
        const real = app.boxPowerWattsAt;
        app.boxPowerWattsAt = () => 70;      // 4 x 70 / 120 = 2.33 A after the head
        try { return app.boxPowerChainChecks().map(c => ({ over: c.over, amps: c.amps })); }
        finally { app.boxPowerWattsAt = real; }
    }""")
    assert out == [{'over': {'boxes': False, 'amps': True}, 'amps': pytest.approx(4 * 70 / 120)}]
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
    gear reads unpowered - without touching the store."""
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
