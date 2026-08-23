"""The hardware dock: the tray under the canvas, and drag as THE assignment.

The Data and Power views' hardware sits in a tray between the canvas and the
status bar, and dragging it onto the canvas is how assignments are made - the
panels name and inspect, the dock aims. Every drop goes through the same
operations the panels' controls used to fire (place, move-block,
place-overflow, setSocaDistro, setSocaNumber), so the refusals, the conflict
question and the history entries are the ones those operations always earned.

What is pinned here, with real pointer drags (mouse down/move/up):
  * the dock exists only in the Data and Power views, and the canvas backing
    store matches its wrapper with the dock present, folded, and absent
  * a single PORT tile dropped on a specific port run places that screen-port
    on that processor port, one 'Place Port' undo step, undo/redo walk it
  * mid-flight, the run under the cursor is the live drop target
  * dropping onto an occupied socket asks the existing question - dismiss
    changes nothing, confirm places - never a silent displacement
  * a whole CARD dropped on a screen fills its ports in order from the first
    unassigned (place-overflow) or moves the whole block when nothing is
    unassigned (move-block)
  * a whole BREAKOUT BOX fills only its own span of card ports, dealing
    around sockets already claimed inside the span
  * a single multi SLOT dropped on a circuit lands that circuit's multi on
    that (distro, number); an occupied slot is the JOIN, not a refusal
  * a whole DISTRO dropped on a screen gives its unassigned multis that
    distro, numbered automatically
  * dragging an occupied port tile / slot chip back onto the dock releases
    the assignment, undoably
  * an invalid target refuses with a reason (status bar), nothing mutates

Run locally:
    python3 -m pytest tests/test_hardware_dock.py -q --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# Two walls and one machine: WALL A big enough to need five ports and three
# circuits, WALL B one port and one circuit, far enough right that a drop on
# one can never smear onto the other. Power settings give whole rows per
# circuit (a 10-wide row of 200 W panels does not fit the 110 V default).
SEED_JS = """async () => {
    const proj = await (await fetch('/api/project')).json();
    proj.layers = [];
    proj.groups = [];
    proj.processors = [];
    proj.distros = [];
    delete proj.port_assignments;
    await fetch('/api/project', {method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(proj)});
    await fetch('/api/layer/add', {method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: 'WALL A', columns: 10, rows: 5,
                              cabinet_width: 200, cabinet_height: 200})});
    await fetch('/api/layer/add', {method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: 'WALL B', columns: 4, rows: 4,
                              cabinet_width: 200, cabinet_height: 200,
                              offset_x: 2400})});
    await fetch('/api/processors', {method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({deviceId: 'novastar-mx40-pro'})});
    const app = window.app;
    const p1 = await (await fetch('/api/project')).json();
    for (const l of p1.layers) {
        await fetch(`/api/layer/${l.id}`, {method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({powerVoltage: 208, powerAmperage: 20})});
    }
    const p = await (await fetch('/api/project')).json();
    app.project = p;
    app.currentLayer = p.layers[0];
    app.selectedLayerIds = new Set([p.layers[0].id]);
    app.addDistro({name: 'PD'});
    await app.refreshProcessors();
    app.renderLayers();
    const r = window.canvasRenderer;
    r.zoom = 0.28; r.panX = 60; r.panY = 40; r.render();
    app.resetHistory('Dock Seed');
    const proc = app._processorsResolved[0];
    return {
        aId: p.layers.find(l => l.name === 'WALL A').id,
        bId: p.layers.find(l => l.name === 'WALL B').id,
        procId: proc.id,
        cardId: proc.slots.map(s => s.card).find(Boolean).id,
        distroId: app.getDistros()[0].id,
    };
}"""

# Put the data-side assignment state back to virgin: no pins, auto on.
RESET_DATA_JS = """async (ids) => {
    const app = window.app;
    await app._assignmentRequest('/api/port-assignments/unpin', 'POST',
                                 {layerId: String(ids.aId)});
    await app._assignmentRequest('/api/port-assignments/unpin', 'POST',
                                 {layerId: String(ids.bId)});
    await app._assignmentRequest('/api/port-assignments', 'PUT', {auto: true});
    app.resetHistory('Dock Seed');
    return (app.project.port_assignments || {}).pins || [];
}"""

# Put the power-side assignment state back to virgin: no distro, no pin.
RESET_POWER_JS = """(ids) => {
    const app = window.app;
    const touched = [];
    for (const id of [ids.aId, ids.bId]) {
        const l = app.project.layers.find(x => x.id === id);
        if (!l) continue;
        for (const k of ['powerSocaDistro', 'powerSocaNumber',
                         'powerSocaPhasePos']) {
            if (l[k] && Object.keys(l[k]).length) { l[k] = {}; touched.push(l); }
        }
    }
    if (touched.length) app.updateLayers([...new Set(touched)]);
    app._circuitTailCache = null;
    app.refreshSocaRuns();
    app.renderHardwareDock();
    app.resetHistory('Dock Seed');
    return true;
}"""

# The client point of a panel: the same world-to-client walk the canvas
# gestures use, so the drop lands where a user aiming at the drawing lands.
PANEL_POINT_JS = """([layerId, which]) => {
    const app = window.app;
    const r = window.canvasRenderer;
    const layer = app.project.layers.find(l => l.id === layerId);
    let p;
    if (which.port !== undefined) {
        const items = app.calculatePortAssignments(layer);
        p = items.find(i => i.port === which.port).panel;
    } else if (which.circuit !== undefined) {
        p = app.screenCircuits(layer)[which.circuit].panels[0];
    } else {
        p = layer.panels[0];
    }
    const {dx, dy} = r.getLayerRenderOffset(layer);
    const off = r._layerCanvasOffset(layer);
    const wx = p.x + p.width / 2 + dx + off.wx;
    const wy = p.y + p.height / 2 + dy + off.wy;
    const rect = r.canvas.getBoundingClientRect();
    return {x: rect.left + wx * r.zoom + r.panX,
            y: rect.top + wy * r.zoom + r.panY};
}"""

PINS_JS = "() => (window.app.project.port_assignments || {}).pins || []"
HIST_JS = "(n) => window.app.history.map(h => h.action).slice(-n)"


@pytest.fixture(scope="module")
def dock_page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)  # socket connect + app init
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(1200)
    yield pg, ids
    context.close()


def open_view(page, mode):
    page.locator(f'[data-mode="{mode}"]').click()
    page.wait_for_timeout(500)


def panel_point(page, layer_id, which):
    return page.evaluate(PANEL_POINT_JS, [layer_id, which])


def drag(page, sx, sy, ex, ey, mid_check=None):
    """A real pointer drag, stepped the way every drag test here steps: a
    single synthetic jump would exercise a code path no user can produce."""
    page.mouse.move(sx, sy)
    page.mouse.down()
    page.mouse.move((sx + ex) / 2, (sy + ey) / 2, steps=5)
    page.mouse.move(ex, ey, steps=5)
    mid = mid_check(page) if mid_check else None
    page.mouse.up()
    page.wait_for_timeout(700)
    return mid


def dock_tile_center(page, key):
    box = page.locator(f'[data-hwdock="{key}"]').bounding_box()
    assert box, f'no dock tile {key}'
    return box['x'] + box['width'] / 2, box['y'] + box['height'] / 2


# ── the dock lives only in its views, and the canvas keeps up ─────────────

ALL_VIEWS = ['pixel-map', 'cabinet-id', 'show-look', 'data-flow', 'power']


def test_the_dock_lives_only_in_the_hardware_views(dock_page):
    page, ids = dock_page
    for mode in ALL_VIEWS:
        open_view(page, mode)
        out = page.evaluate("""() => {
            const dock = document.getElementById('hardware-dock');
            return {
                display: getComputedStyle(dock).display,
                canvasH: document.getElementById('main-canvas').height,
                wrapH: document.getElementById('canvas-wrapper').clientHeight,
                canvasW: document.getElementById('main-canvas').width,
                wrapW: document.getElementById('canvas-wrapper').clientWidth,
            };
        }""")
        expected = mode in ('data-flow', 'power')
        assert (out['display'] != 'none') == expected, (
            f'the dock is {out["display"]} in {mode}')
        assert out['canvasH'] == out['wrapH'], (
            f'the canvas backing store lags the wrapper in {mode}: {out}')
        assert out['canvasW'] == out['wrapW'], out


def test_folding_the_dock_hands_the_room_back_to_the_canvas(dock_page):
    page, ids = dock_page
    open_view(page, 'data-flow')
    before = page.evaluate(
        "() => document.getElementById('canvas-wrapper').clientHeight")
    page.locator('#hardware-dock .lrd-sec-arrow').click()
    page.wait_for_timeout(600)
    folded = page.evaluate("""() => ({
        wrapH: document.getElementById('canvas-wrapper').clientHeight,
        canvasH: document.getElementById('main-canvas').height,
        bodyShown: document.getElementById('hardware-dock-body')
            .getClientRects().length > 0,
    })""")
    assert not folded['bodyShown'], 'the fold left the tray body painted'
    assert folded['wrapH'] > before, (
        f'folding the dock gave no room back: {before} -> {folded}')
    assert folded['canvasH'] == folded['wrapH'], (
        f'the canvas backing store missed the fold: {folded}')
    page.locator('#hardware-dock .lrd-sec-arrow').click()
    page.wait_for_timeout(600)
    after = page.evaluate("""() => ({
        wrapH: document.getElementById('canvas-wrapper').clientHeight,
        canvasH: document.getElementById('main-canvas').height,
    })""")
    assert after['wrapH'] == before and after['canvasH'] == after['wrapH'], (
        f'unfolding did not restore the layout: {before} -> {after}')


# ── data view: port, card, box ────────────────────────────────────────────

def test_a_port_tile_lands_on_the_run_it_is_dropped_on(dock_page):
    page, ids = dock_page
    open_view(page, 'data-flow')
    page.evaluate(RESET_DATA_JS, ids)
    page.wait_for_timeout(400)

    sx, sy = dock_tile_center(page, f'port-{ids["cardId"]}-8')
    tgt = panel_point(page, ids['aId'], {'port': 2})
    mid = drag(page, sx, sy, tgt['x'], tgt['y'],
               mid_check=lambda p: p.evaluate("""() => ({
                   target: window.app._dockDropTarget,
                   ghost: !!document.getElementById('hw-dock-ghost')})"""))
    # mid-flight: the run under the cursor is the live target, ghost along
    assert mid['ghost'], 'no ghost followed the drag'
    assert mid['target'] == {'kind': 'run', 'layerId': ids['aId'], 'num': 2}, (
        f'the live target is not the run under the cursor: {mid}')

    pins = page.evaluate(PINS_JS)
    mine = [p for p in pins if p['layerId'] == str(ids['aId'])]
    placed = next(p for p in mine if p['index'] == 1)
    assert placed['cardId'] == ids['cardId'] and placed['port'] == 8, pins
    # the placement holds the screen's other ports where they were, the
    # existing place semantics - only the dropped one moved
    assert len(mine) == 5, f'the hold did not pin the rest of the run: {pins}'
    assert page.evaluate(HIST_JS, 1) == ['Place Port']

    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(900)
    assert page.evaluate(PINS_JS) == [], 'one undo did not clear the drop'
    page.evaluate("() => window.app.redo()")
    page.wait_for_timeout(900)
    assert len(page.evaluate(PINS_JS)) == 5, 'redo did not re-apply the drop'
    page.evaluate(RESET_DATA_JS, ids)
    page.wait_for_timeout(300)


def test_dropping_on_an_occupied_socket_asks_first(dock_page):
    """The existing question, word for word the place flow's: dismiss and
    nothing has moved, confirm and it lands - never a silent displacement."""
    page, ids = dock_page
    open_view(page, 'data-flow')
    page.evaluate(RESET_DATA_JS, ids)
    page.wait_for_timeout(400)

    # card port 1 is WALL A p1's auto seat; aiming it at run 3 is a conflict
    seen = []
    page.once('dialog', lambda d: (seen.append(d.message), d.dismiss()))
    sx, sy = dock_tile_center(page, f'port-{ids["cardId"]}-1')
    tgt = panel_point(page, ids['aId'], {'port': 3})
    drag(page, sx, sy, tgt['x'], tgt['y'])
    assert seen and 'already on' in seen[0], (
        f'no conflict question was asked: {seen}')
    assert page.evaluate(PINS_JS) == [], (
        'declining the question still moved something')

    page.once('dialog', lambda d: d.accept())
    drag(page, sx, sy, tgt['x'], tgt['y'])
    pins = page.evaluate(PINS_JS)
    placed = [p for p in pins if p['index'] == 2
              and p['layerId'] == str(ids['aId'])]
    assert placed and placed[0]['port'] == 1, (
        f'confirming did not place the port: {pins}')
    assert page.evaluate(HIST_JS, 1) == ['Place Port']
    page.evaluate(RESET_DATA_JS, ids)
    page.wait_for_timeout(300)


def test_a_whole_card_fills_in_order_from_the_first_unassigned(dock_page):
    page, ids = dock_page
    open_view(page, 'data-flow')
    page.evaluate(RESET_DATA_JS, ids)
    # auto off: every port of every screen is unassigned, the fill's home case
    page.evaluate("""async () => {
        await window.app._assignmentRequest('/api/port-assignments', 'PUT',
                                            {auto: false});
        window.app.resetHistory('Dock Seed');
    }""")
    page.wait_for_timeout(400)

    sx, sy = dock_tile_center(page, f'card-{ids["cardId"]}')
    tgt = panel_point(page, ids['aId'], {})
    drag(page, sx, sy, tgt['x'], tgt['y'])
    pins = page.evaluate(PINS_JS)
    mine = sorted((p for p in pins if p['layerId'] == str(ids['aId'])),
                  key=lambda p: p['index'])
    assert [(p['index'], p['port']) for p in mine] == \
        [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5)], (
        f'the card fill is not in order from the first unassigned: {pins}')
    assert page.evaluate(HIST_JS, 1) == ['Fill Ports In Order']
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(900)
    assert page.evaluate(PINS_JS) == [], 'undo did not clear the card fill'
    page.evaluate("""async () => {
        await window.app._assignmentRequest('/api/port-assignments', 'PUT',
                                            {auto: true});
    }""")
    page.evaluate(RESET_DATA_JS, ids)
    page.wait_for_timeout(300)


def test_a_whole_card_moves_the_block_when_nothing_is_unassigned(dock_page):
    page, ids = dock_page
    open_view(page, 'data-flow')
    page.evaluate(RESET_DATA_JS, ids)
    page.wait_for_timeout(400)

    # everything auto-assigned; the drop means "this screen goes here"
    sx, sy = dock_tile_center(page, f'card-{ids["cardId"]}')
    tgt = panel_point(page, ids['bId'], {})
    drag(page, sx, sy, tgt['x'], tgt['y'])
    pins = page.evaluate(PINS_JS)
    mine = [p for p in pins if p['layerId'] == str(ids['bId'])]
    assert mine, f'the block move pinned nothing: {pins}'
    assert page.evaluate(HIST_JS, 1) == ['Move Port Block']
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(900)
    assert page.evaluate(PINS_JS) == [], 'undo did not clear the block move'
    page.evaluate(RESET_DATA_JS, ids)
    page.wait_for_timeout(300)


def test_a_breakout_box_fills_only_its_own_span(dock_page):
    """The box is a span of card ports; the fill deals around a socket
    already claimed inside the span and never leaves it. A copy/backup box
    lists the same card ports as its primary, so dropping it lands on the
    same sockets - they ARE the same sockets."""
    page, ids = dock_page
    open_view(page, 'data-flow')
    page.evaluate(RESET_DATA_JS, ids)
    box = page.evaluate("""async (ids) => {
        const app = window.app;
        await fetch(`/api/processors/${ids.procId}/cards/${ids.cardId}/cvts`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({deviceId: 'novastar-cvt4k-s'})});
        await app.refreshProcessors();
        const card = app._processorsResolved[0].slots
            .map(s => s.card).find(Boolean);
        const cvt = card.cvts[0];
        const nums = cvt.ports.map(p => p.number);
        return {id: cvt.id, first: Math.min(...nums),
                last: Math.max(...nums), copy: !!cvt.duplicateOf};
    }""", ids)
    page.wait_for_timeout(600)
    # auto off, and a blocker pinned INSIDE the box's span
    page.evaluate("""async (args) => {
        const app = window.app;
        await app._assignmentRequest('/api/port-assignments', 'PUT',
                                     {auto: false});
        await app._assignmentRequest('/api/port-assignments/place', 'POST',
            {layerId: String(args.ids.bId), index: 0,
             cardId: args.ids.cardId, port: args.box.first + 2,
             confirm: false});
        app.resetHistory('Dock Seed');
    }""", {'ids': ids, 'box': box})
    page.wait_for_timeout(400)

    sx, sy = dock_tile_center(page, f'box-{box["id"]}')
    tgt = panel_point(page, ids['aId'], {'port': 1})
    drag(page, sx, sy, tgt['x'], tgt['y'])
    pins = page.evaluate(PINS_JS)
    mine = sorted((p for p in pins if p['layerId'] == str(ids['aId'])),
                  key=lambda p: p['index'])
    f = box['first']
    assert [(p['index'], p['port']) for p in mine] == \
        [(0, f), (1, f + 1), (2, f + 3), (3, f + 4), (4, f + 5)], (
        f'the box fill did not deal around the blocker inside its span '
        f'(first={f}): {pins}')
    assert all(f <= p['port'] <= box['last'] for p in mine), (
        f'the box fill left the span {f}-{box["last"]}: {pins}')
    assert page.evaluate(HIST_JS, 1) == ['Fill Ports In Order']
    # leave the module's processor as seeded
    page.evaluate("""async (args) => {
        const app = window.app;
        await fetch(`/api/processors/${args.ids.procId}/cvts/${args.box.id}`,
                    {method: 'DELETE'});
        await app.refreshProcessors();
        await app._assignmentRequest('/api/port-assignments', 'PUT',
                                     {auto: true});
    }""", {'ids': ids, 'box': box})
    page.evaluate(RESET_DATA_JS, ids)
    page.wait_for_timeout(400)


def test_an_invalid_target_refuses_with_a_reason(dock_page):
    """A screen that needs no ports refuses the card with the existing
    sentence, on the status bar - and nothing mutates."""
    page, ids = dock_page
    open_view(page, 'data-flow')
    page.evaluate(RESET_DATA_JS, ids)
    img = page.evaluate("""async () => {
        // one transparent pixel: a layer with no ports to its name
        const resp = await fetch('/api/layer/add-image', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name: 'LOGO', offset_x: 200, offset_y: 1400,
                imageData: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
                imageWidth: 600, imageHeight: 600})});
        const made = await resp.json();
        window.app.project = await (await fetch('/api/project')).json();
        window.canvasRenderer.render();
        return made.id;
    }""")
    page.wait_for_timeout(500)
    sx, sy = dock_tile_center(page, f'card-{ids["cardId"]}')
    # an image layer has no panels; aim at the middle of its footprint
    tgt = page.evaluate("""(id) => {
        const r = window.canvasRenderer;
        const layer = window.app.project.layers.find(l => l.id === id);
        const b = r.getLayerFootprintInActiveView(layer);
        const off = r._layerCanvasOffset(layer);
        const wx = b.x + off.wx + b.width / 2;
        const wy = b.y + off.wy + b.height / 2;
        const rect = r.canvas.getBoundingClientRect();
        return {x: rect.left + wx * r.zoom + r.panX,
                y: rect.top + wy * r.zoom + r.panY};
    }""", img)
    drag(page, sx, sy, tgt['x'], tgt['y'])
    out = page.evaluate("""() => ({
        status: document.getElementById('status-message').textContent,
        pins: (window.app.project.port_assignments || {}).pins || []})""")
    assert out['status'] == 'That screen needs no ports.', out
    assert out['pins'] == [], f'the refusal still mutated something: {out}'
    page.evaluate("""async (id) => {
        await fetch(`/api/layer/${id}`, {method: 'DELETE'});
        window.app.project = await (await fetch('/api/project')).json();
        window.app.renderLayers();
        window.canvasRenderer.render();
    }""", img)
    page.wait_for_timeout(400)


def test_drag_back_to_the_dock_releases_the_port(dock_page):
    page, ids = dock_page
    open_view(page, 'data-flow')
    page.evaluate(RESET_DATA_JS, ids)
    # a pinned occupant to release
    page.evaluate("""async (ids) => {
        const app = window.app;
        await app._assignmentRequest('/api/port-assignments/place', 'POST',
            {layerId: String(ids.aId), index: 1, cardId: ids.cardId,
             port: 8, confirm: false});
        app.resetHistory('Dock Seed');
    }""", ids)
    page.wait_for_timeout(500)
    assert len(page.evaluate(PINS_JS)) == 5

    sx, sy = dock_tile_center(page, f'port-{ids["cardId"]}-8')
    dock_box = page.locator('#hardware-dock-body').bounding_box()
    drag(page, sx, sy, dock_box['x'] + dock_box['width'] * 0.7,
         dock_box['y'] + min(40, dock_box['height'] / 2))
    pins = page.evaluate(PINS_JS)
    assert not any(p['port'] == 8 for p in pins), (
        f'the drag-back did not release the pin: {pins}')
    assert page.evaluate(HIST_JS, 1) == ['Release Port']
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(900)
    assert any(p['port'] == 8 for p in page.evaluate(PINS_JS)), (
        'undo did not restore the released pin')
    page.evaluate(RESET_DATA_JS, ids)
    page.wait_for_timeout(300)


# ── power view: slot, join, distro, drag-back ─────────────────────────────

def test_a_slot_chip_lands_on_the_circuit_it_is_dropped_on(dock_page):
    page, ids = dock_page
    open_view(page, 'power')
    page.evaluate(RESET_POWER_JS, ids)
    page.wait_for_timeout(500)

    sx, sy = dock_tile_center(page, f'slot-{ids["distroId"]}-1')
    tgt = panel_point(page, ids['aId'], {'circuit': 0})
    drag(page, sx, sy, tgt['x'], tgt['y'])
    out = page.evaluate("""(aId) => {
        const l = window.app.project.layers.find(x => x.id === aId);
        return {distro: l.powerSocaDistro, num: l.powerSocaNumber};
    }""", ids['aId'])
    assert out['distro'] == {'1': ids['distroId']}, out
    assert out['num'] == {'1': 1}, out
    # the two existing setters, the two existing entries, in their order
    assert page.evaluate(HIST_JS, 2) == \
        ['Assign Multi Distro', 'Set Multi Number']
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(700)
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(700)
    out = page.evaluate("""(aId) => {
        const l = window.app.project.layers.find(x => x.id === aId);
        return {distro: l.powerSocaDistro || {}, num: l.powerSocaNumber || {}};
    }""", ids['aId'])
    assert out == {'distro': {}, 'num': {}}, (
        f'two undos did not walk the drop back: {out}')
    page.evaluate(RESET_POWER_JS, ids)


def test_an_occupied_slot_is_the_join_not_a_refusal(dock_page):
    """Dropping a slot another screen's multi holds is the shared-box join
    the number pick always was: no dialog, both multis on one box."""
    page, ids = dock_page
    open_view(page, 'power')
    page.evaluate(RESET_POWER_JS, ids)
    page.evaluate("""(ids) => {
        const app = window.app;
        const a = app.project.layers.find(x => x.id === ids.aId);
        app.setSocaDistro(a, 1, ids.distroId);
        app.setSocaNumber(a, 1, 1);
        app._restateNaming();
    }""", ids)
    page.wait_for_timeout(700)

    sx, sy = dock_tile_center(page, f'slot-{ids["distroId"]}-1')
    tgt = panel_point(page, ids['bId'], {'circuit': 0})
    drag(page, sx, sy, tgt['x'], tgt['y'])
    out = page.evaluate("""(ids) => {
        const app = window.app;
        const a = app.project.layers.find(x => x.id === ids.aId);
        const b = app.project.layers.find(x => x.id === ids.bId);
        app._circuitTailCache = null;
        return {
            aNum: a.powerSocaNumber, bNum: b.powerSocaNumber,
            bDistro: b.powerSocaDistro,
            members: (app._distroMultiNumbers(ids.distroId).get(1) || [])
                .map(m => m.layerId).sort(),
            share: !!app.getSocaShare(b, 1),
        };
    }""", ids)
    assert out['aNum'] == {'1': 1} and out['bNum'] == {'1': 1}, out
    assert out['bDistro'] == {'1': ids['distroId']}, out
    assert out['members'] == sorted([ids['aId'], ids['bId']]), (
        f'the join did not put both multis on one box: {out}')
    assert out['share'], f'the joined multi reports no share: {out}'
    page.evaluate(RESET_POWER_JS, ids)


def test_a_distro_fills_the_screens_unassigned_multis(dock_page):
    page, ids = dock_page
    open_view(page, 'power')
    page.evaluate(RESET_POWER_JS, ids)
    page.wait_for_timeout(400)

    sx, sy = dock_tile_center(page, f'distro-{ids["distroId"]}')
    tgt = panel_point(page, ids['aId'], {})
    drag(page, sx, sy, tgt['x'], tgt['y'])
    out = page.evaluate("""(ids) => {
        const app = window.app;
        const a = app.project.layers.find(x => x.id === ids.aId);
        app._circuitTailCache = null;
        return {
            distro: a.powerSocaDistro,
            num: a.powerSocaNumber || {},
            plan: app.getSocaPlan(a).map(s => [s.soca, s.distroId, s.number]),
        };
    }""", ids)
    assert out['distro'], f'the distro drop assigned nothing: {out}'
    assert all(d == ids['distroId'] for d in out['distro'].values()), out
    assert out['num'] == {}, (
        f'the distro drop pinned numbers instead of leaving auto: {out}')
    assert [row[1] for row in out['plan']] == \
        [ids['distroId']] * len(out['plan']), out
    assert page.evaluate(HIST_JS, 1) == ['Assign Multi Distro']
    page.evaluate(RESET_POWER_JS, ids)


def test_drag_back_to_the_dock_unassigns_the_multi(dock_page):
    page, ids = dock_page
    open_view(page, 'power')
    page.evaluate(RESET_POWER_JS, ids)
    page.evaluate("""(ids) => {
        const app = window.app;
        const a = app.project.layers.find(x => x.id === ids.aId);
        app.setSocaDistro(a, 1, ids.distroId);
        app.setSocaNumber(a, 1, 1);
        app._restateNaming();
    }""", ids)
    page.wait_for_timeout(700)

    sx, sy = dock_tile_center(page, f'slot-{ids["distroId"]}-1')
    dock_box = page.locator('#hardware-dock-body').bounding_box()
    drag(page, sx, sy, dock_box['x'] + dock_box['width'] * 0.7,
         dock_box['y'] + min(40, dock_box['height'] / 2))
    out = page.evaluate("""(aId) => {
        const l = window.app.project.layers.find(x => x.id === aId);
        return {distro: l.powerSocaDistro || {}, num: l.powerSocaNumber || {}};
    }""", ids['aId'])
    assert out == {'distro': {}, 'num': {}}, (
        f'the drag-back did not unassign the multi: {out}')
    # the two existing setters again, so undo walks it back the same way
    assert page.evaluate(HIST_JS, 2) == \
        ['Set Multi Number', 'Assign Multi Distro']
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(700)
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(700)
    out = page.evaluate("""(aId) => {
        const l = window.app.project.layers.find(x => x.id === aId);
        return {distro: l.powerSocaDistro || {}, num: l.powerSocaNumber || {}};
    }""", ids['aId'])
    assert out['distro'] == {'1': ids['distroId']} and out['num'] == {'1': 1}, (
        f'two undos did not restore the assignment: {out}')
    page.evaluate(RESET_POWER_JS, ids)


# ── Backing ports in the tray ─────────────────────────────────────────────

def test_a_backing_port_wears_its_role_in_the_dock(dock_page):
    """Sequential redundancy on the seeded card: the even tiles stop saying
    'free' and say whose return they carry, in the backup gold - the dock is
    where a drag would start, so the claim has to be visible before the
    refusal is needed."""
    page, ids = dock_page
    open_view(page, 'data-flow')
    page.evaluate("""async (ids) => {
        const send = (url, method, body) => fetch(url, { method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body) }).then(r => r.json());
        await send(`/api/processors/${ids.procId}`, 'PUT',
                   { redundancy: true });
        await send(`/api/processors/${ids.procId}/cards/${ids.cardId}`,
                   'PUT', { redundancyMode: 'sequential' });
        await window.app.refreshProcessors();
    }""", ids)
    page.wait_for_timeout(1200)
    out = page.evaluate("""(ids) => {
        const even = document.querySelector(
            `[data-hwdock="port-${ids.cardId}-2"]`);
        const odd = document.querySelector(
            `[data-hwdock="port-${ids.cardId}-1"]`);
        return {
            even: even ? even.textContent : null,
            evenTitle: even ? even.title : null,
            odd: odd ? odd.textContent : null,
        };
    }""", ids)
    try:
        assert out['even'] and 'backs up' in out['even'], out
        assert 'return end' in (out['evenTitle'] or ''), out
        assert out['odd'] and 'backs up' not in out['odd'], out
    finally:
        # Leave the module's shared server the way this test found it.
        page.evaluate("""async (ids) => {
            const send = (url, method, body) => fetch(url, { method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body) }).then(r => r.json());
            await send(`/api/processors/${ids.procId}/cards/${ids.cardId}`,
                       'PUT', { redundancyMode: '1to1' });
            await send(`/api/processors/${ids.procId}`, 'PUT',
                       { redundancy: false });
            await window.app.refreshProcessors();
        }""", ids)
        page.wait_for_timeout(600)
