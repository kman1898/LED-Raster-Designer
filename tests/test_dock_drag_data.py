"""A card, a box or a whole processor dragged onto a screen on the Data tab
takes the screen's UNPLACED ports from the first up to the port under the
cursor - the Power tab's multi rule, by owner ruling (2026-09-24).

  * mid-flight the drop target carries `nums`, the ports the release will
    land: the unplaced ports up to the hovered one, capped at the unit's
    free sockets (a box: the free sockets inside its own span). Exactly
    those light on the canvas; the cursor pill says the count ("3 ports",
    "2 of 6 ports" where the unit runs out of free sockets)
  * the drop lands exactly those - client state and GET /api/project agree
    - as one 'Fill Ports In Order' step; the rest stay unplaced
  * a port already on ANY processor is never lit and never moved: a second
    drag over port 6 with 1-3 placed lights 4-6 only ("We should not be
    able to highlight anything that is already added to a processor")
  * a screen with every port placed lights nothing, and the drop refuses in
    plain words and moves nothing ("if the whole card is already set then
    it cant be set again. it would need to be cleared") - the whole-block
    move that used to run here is gone
  * a single PORT chip still drops one port; a whole PROCESSOR chip behaves
    as its first card; a custom-flow screen counts its drawn ports the same
    way; the platform wall's refusal is the server's own sentence, unchanged

Real pointer drags (mouse down/move/up) against the live app; the seed is
an H9 with one 16-port card and a Legacy-programmed wall that needs six.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


CARD = 'novastar-card-h-16xrj45-2xfiber'

# WALL: 12x6 of 200 px cabinets programmed Legacy - a row is 480k px, one
# port each on the H card's figure, six ports. BROMP: a Brompton wall the
# H card must refuse. CUST: a small Legacy wall the custom-flow test redraws
# as three ports. FILLER: a Legacy wall whose fourteen rows fill the card
# down to two free sockets when a test needs the cap.
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
    const send = (url, method, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body)}).then(r => r.json());
    const walls = [
        ['WALL', 12, 6, 0, 0, 'novastar-armor'],
        ['BROMP', 4, 4, 2700, 0, 'brompton'],
        ['CUST', 4, 3, 2700, 1000, 'novastar-armor'],
        ['FILLER', 12, 14, 0, 1500, 'novastar-armor'],
    ];
    const made = {};
    for (const [name, cols, rows, ox, oy, platform] of walls) {
        const r = await send('/api/layer/add', 'POST', {name, columns: cols,
            rows, cabinet_width: 200, cabinet_height: 200,
            offset_x: ox, offset_y: oy});
        await send(`/api/layer/${r.id}`, 'PUT', {processorType: platform});
        made[name] = r.id;
    }
    const added = await send('/api/processors', 'POST',
                             {deviceId: 'novastar-h9'});
    const procId = added.resolved[0].id;
    const st = await send(`/api/processors/${procId}/slots/0`, 'PUT',
                          {deviceId: '%s'});
    const cardId = st.resolved[0].slots[0].card.id;
    const app = window.app;
    const p = await (await fetch('/api/project')).json();
    app.project = p;
    app.currentLayer = p.layers[0];
    app.selectedLayerIds = new Set([p.layers[0].id]);
    await app.refreshProcessors();
    app.renderLayers();
    const r = window.canvasRenderer;
    r.zoom = 0.25; r.panX = 60; r.panY = 40; r.render();
    await app.refreshPortAssignment();
    app.resetHistory('Dock Seed');
    const need = {};
    for (const l of app.project.layers) need[l.name] = app.getLayerPortsRequired(l);
    return {wall: made.WALL, bromp: made.BROMP, cust: made.CUST,
            filler: made.FILLER, procId, cardId, need};
}""" % CARD

# Every pin off every screen; history back to the seed.
RESET_JS = """async (ids) => {
    const app = window.app;
    for (const id of [ids.wall, ids.bromp, ids.cust, ids.filler]) {
        await app._assignmentRequest('/api/port-assignments/unpin', 'POST',
                                     {layerId: String(id)});
    }
    app.resetHistory('Dock Seed');
    return (app.project.port_assignments || {}).pins || [];
}"""

# The client point of a screen's port: the first panel on that run, by the
# same world-to-client walk the canvas gestures use. A custom-flow layer's
# run is its drawn path.
PORT_POINT_JS = """([layerId, port]) => {
    const app = window.app;
    const r = window.canvasRenderer;
    const layer = app.project.layers.find(l => l.id === layerId);
    let p;
    if ((layer.flowPattern || 'tl-h') === 'custom') {
        const pos = layer.customPortPaths[port][0];
        p = layer.panels.find(x => x.row === pos.row && x.col === pos.col);
    } else if (port == null) {
        p = layer.panels[0];
    } else {
        p = app.calculatePortAssignments(layer)
            .find(i => i.port === port).panel;
    }
    const {dx, dy} = r.getLayerRenderOffset(layer);
    const off = r._layerCanvasOffset(layer);
    const wx = p.x + p.width / 2 + dx + off.wx;
    const wy = p.y + p.height / 2 + dy + off.wy;
    const rect = r.canvas.getBoundingClientRect();
    return {x: rect.left + wx * r.zoom + r.panX,
            y: rect.top + wy * r.zoom + r.panY};
}"""

# The runs the canvas DRAWS the drop underlay on, read off the real render.
LIT_RUNS_JS = """() => {
    const r = window.canvasRenderer;
    const lit = [];
    const orig = r._dockRunUnderlay;
    r._dockRunUnderlay = function (panels, layer, num) {
        const st = this.ctx.stroke;
        let drew = false;
        this.ctx.stroke = function () {
            drew = true;
            return st.apply(this, arguments);
        };
        try { orig.call(this, panels, layer, num); }
        finally { this.ctx.stroke = st; }
        if (drew) lit.push([layer.id, num]);
    };
    try { r.render(); } finally { r._dockRunUnderlay = orig; }
    return lit;
}"""

# The cursor pill as the user sees it.
PILL_JS = """() => {
    const el = document.getElementById('hw-dock-pill');
    if (!el || el.style.display === 'none') return null;
    return {text: el.textContent, bad: el.classList.contains('hw-dock-pill-bad')};
}"""

PINS_JS = "() => (window.app.project.port_assignments || {}).pins || []"
SERVER_PINS_JS = """async () => {
    const p = await (await fetch('/api/project')).json();
    return (p.port_assignments || {}).pins || [];
}"""
HIST_JS = "(n) => window.app.history.map(h => h.action).slice(-n)"
HIST_LEN_JS = "() => window.app.history.length"
STATUS_JS = "() => document.getElementById('status-message').textContent"


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
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(600)
    assert ids['need']['WALL'] == 6, (
        f'the seed must make WALL a six-port screen: {ids["need"]}')
    assert ids['need']['FILLER'] == 14, (
        f'the seed must make FILLER a fourteen-port screen: {ids["need"]}')
    yield pg, ids
    context.close()


def port_point(page, layer_id, port):
    return page.evaluate(PORT_POINT_JS, [layer_id, port])


def dock_tile_center(page, key):
    page.evaluate(
        """(key) => {
            const el = document.querySelector(`[data-hwdock="${key}"]`);
            if (el) el.scrollIntoView({ block: 'nearest' });
        }""", key)
    box = page.locator(f'[data-hwdock="{key}"]').bounding_box()
    assert box, f'no dock tile {key}'
    return box['x'] + box['width'] / 2, box['y'] + box['height'] / 2


def dock_grip_center(page, key):
    """The ⋮⋮ grip of a header strip: the processor's strip carries live
    controls (the name field, the ⚙) that a press leaves alone, so the
    drag starts on the grip, where a user's hand goes."""
    page.evaluate(
        """(key) => {
            const el = document.querySelector(`[data-hwdock="${key}"]`);
            if (el) el.scrollIntoView({ block: 'nearest' });
        }""", key)
    box = page.locator(f'[data-hwdock="{key}"] .hw-dock-grip').bounding_box()
    assert box, f'no grip on dock tile {key}'
    return box['x'] + box['width'] / 2, box['y'] + box['height'] / 2


def drag(page, sx, sy, ex, ey):
    """A real pointer drag, stepped: mid-flight the drawn underlay, the
    live target and the pill are read, then the release lands."""
    page.mouse.move(sx, sy)
    page.mouse.down()
    page.mouse.move((sx + ex) / 2, (sy + ey) / 2, steps=5)
    page.mouse.move(ex, ey, steps=5)
    page.wait_for_timeout(250)
    mid = {
        'lit': sorted(set(map(tuple, page.evaluate(LIT_RUNS_JS)))),
        'target': page.evaluate("() => window.app._dockDropTarget"),
        'pill': page.evaluate(PILL_JS),
        'ghost': page.evaluate("() => !!document.getElementById('hw-dock-ghost')"),
        'at': (ex, ey),
    }
    assert mid['ghost'], f'no ghost followed the drag: {mid}'
    page.mouse.up()
    page.wait_for_timeout(700)
    return mid


def drag_probe(page, sx, sy, ex, ey):
    """The same drag, ended over the sidebar: no target there, so nothing
    mutates."""
    page.mouse.move(sx, sy)
    page.mouse.down()
    page.mouse.move((sx + ex) / 2, (sy + ey) / 2, steps=5)
    page.mouse.move(ex, ey, steps=5)
    page.wait_for_timeout(250)
    mid = {
        'lit': sorted(set(map(tuple, page.evaluate(LIT_RUNS_JS)))),
        'target': page.evaluate("() => window.app._dockDropTarget"),
        'pill': page.evaluate(PILL_JS),
    }
    page.mouse.move(30, 300, steps=3)
    page.mouse.up()
    page.wait_for_timeout(300)
    return mid


def wall_pins(page, layer_id, from_server=False):
    pins = page.evaluate(SERVER_PINS_JS if from_server else PINS_JS)
    mine = sorted((p for p in pins if p['layerId'] == str(layer_id)),
                  key=lambda p: p['index'])
    return [(p['index'], p['port']) for p in mine]


def unplaced(page, layer_id):
    return page.evaluate("""(id) => (window.app._assignment.screens
        .find(s => s.layerId === String(id)) || {unplaced: null}).unplaced""",
                         layer_id)


# ── the card: first unplaced to the cursor ────────────────────────────────

def test_a_card_lights_and_lands_the_unplaced_ports_up_to_the_cursor(
        dock_page):
    page, ids = dock_page
    page.evaluate(RESET_JS, ids)
    page.wait_for_timeout(400)
    assert page.evaluate(PINS_JS) == []
    wall, card = ids['wall'], ids['cardId']

    # over port 3 of a six-port wall with nothing placed: 1-3 light, the
    # pill counts them, and the drop pins exactly those
    sx, sy = dock_grip_center(page, f'card-{card}')
    tgt = port_point(page, wall, 3)
    mid = drag(page, sx, sy, tgt['x'], tgt['y'])
    assert mid['target']['kind'] == 'screen', mid
    assert mid['target']['layerId'] == wall, mid
    assert mid['target']['nums'] == [1, 2, 3], (
        f'the target must carry the unplaced ports up to the cursor: {mid}')
    assert mid['lit'] == [(wall, 1), (wall, 2), (wall, 3)], (
        f'the preview must light exactly the ports the drop lands: {mid}')
    assert mid['pill'] == {'text': '3 ports', 'bad': False}, mid
    assert wall_pins(page, wall) == [(0, 1), (1, 2), (2, 3)], (
        f'the drop must pin exactly the lit ports: {page.evaluate(PINS_JS)}')
    assert wall_pins(page, wall, from_server=True) == [(0, 1), (1, 2), (2, 3)]
    assert unplaced(page, wall) == [3, 4, 5]
    assert page.evaluate(HIST_JS, 1) == ['Fill Ports In Order']

    # over port 6 with 1-3 placed: only 4-6 light - a port already on a
    # processor is never highlighted - and the drop lands only those
    sx, sy = dock_grip_center(page, f'card-{card}')
    tgt = port_point(page, wall, 6)
    mid = drag(page, sx, sy, tgt['x'], tgt['y'])
    assert mid['target']['nums'] == [4, 5, 6], mid
    assert mid['lit'] == [(wall, 4), (wall, 5), (wall, 6)], (
        f'placed ports lit under the drag: {mid}')
    assert mid['pill'] == {'text': '3 ports', 'bad': False}, mid
    assert wall_pins(page, wall) == [(i, i + 1) for i in range(6)], (
        page.evaluate(PINS_JS))
    assert wall_pins(page, wall, from_server=True) == \
        [(i, i + 1) for i in range(6)]
    assert unplaced(page, wall) == []

    # one undo walks the second drop back, leaving the first
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(900)
    assert wall_pins(page, wall) == [(0, 1), (1, 2), (2, 3)], (
        f'undo did not walk back the second drop alone: '
        f'{page.evaluate(PINS_JS)}')
    page.evaluate(RESET_JS, ids)
    page.wait_for_timeout(300)


def test_a_cursor_on_a_placed_port_lights_nothing_and_lands_nothing(
        dock_page):
    """Ports 1-3 placed and the cursor on port 2: nothing unplaced sits up
    to there, so nothing lights and the drop refuses naming the port."""
    page, ids = dock_page
    page.evaluate(RESET_JS, ids)
    page.wait_for_timeout(400)
    wall, card = ids['wall'], ids['cardId']
    page.evaluate("""async (ids) => {
        await window.app._assignmentRequest(
            '/api/port-assignments/place-overflow', 'POST',
            {layerId: String(ids.wall), cardId: ids.cardId, lastIndex: 2});
        window.app.resetHistory('Dock Seed');
    }""", ids)
    page.wait_for_timeout(400)
    assert wall_pins(page, wall) == [(0, 1), (1, 2), (2, 3)]
    before = page.evaluate(HIST_LEN_JS)

    sx, sy = dock_grip_center(page, f'card-{card}')
    tgt = port_point(page, wall, 2)
    mid = drag(page, sx, sy, tgt['x'], tgt['y'])
    assert mid['target']['nums'] == [] and mid['lit'] == [], mid
    assert mid['pill'] == {
        'text': 'Port 2 of WALL is already on a processor', 'bad': True}, mid
    assert page.evaluate(STATUS_JS) == \
        'Port 2 of WALL is already on a processor'
    assert wall_pins(page, wall) == [(0, 1), (1, 2), (2, 3)]
    assert page.evaluate(HIST_LEN_JS) == before
    page.evaluate(RESET_JS, ids)
    page.wait_for_timeout(300)


def test_a_card_short_of_sockets_caps_the_take_and_says_so(dock_page):
    """FILLER on 1-14 leaves two free sockets: the card over port 6 lights
    ports 1-2 only, the pill reads "2 of 6 ports", and the drop lands the
    two with the server's note saying what was left."""
    page, ids = dock_page
    page.evaluate(RESET_JS, ids)
    page.wait_for_timeout(400)
    wall, card = ids['wall'], ids['cardId']
    page.evaluate("""async (ids) => {
        await window.app._assignmentRequest(
            '/api/port-assignments/place-overflow', 'POST',
            {layerId: String(ids.filler), cardId: ids.cardId});
        window.app.resetHistory('Dock Seed');
    }""", ids)
    page.wait_for_timeout(400)
    assert len(wall_pins(page, ids['filler'])) == 14, page.evaluate(PINS_JS)
    free = page.evaluate("""(card) => window.app._assignment.cards
        .find(c => c.cardId === card).free""", card)
    assert free == 2, f'the seed must leave two free sockets: {free}'

    sx, sy = dock_grip_center(page, f'card-{card}')
    tgt = port_point(page, wall, 6)
    mid = drag(page, sx, sy, tgt['x'], tgt['y'])
    assert mid['target']['nums'] == [1, 2], mid
    assert mid['lit'] == [(wall, 1), (wall, 2)], (
        f'the preview must cap at the card\'s free sockets: {mid}')
    assert mid['pill'] == {'text': '2 of 6 ports', 'bad': False}, mid
    assert wall_pins(page, wall) == [(0, 15), (1, 16)], page.evaluate(PINS_JS)
    assert unplaced(page, wall) == [2, 3, 4, 5]
    note = page.evaluate("() => window.app._assignmentNote")
    assert note == 'H9 slot 1 took 2 of 6 ports. 4 still have nowhere to go.', (
        note)

    # the card is full now: the drag lights nothing and the drop is refused
    # with the server's fact
    sx, sy = dock_grip_center(page, f'card-{card}')
    tgt = port_point(page, wall, 6)
    mid = drag(page, sx, sy, tgt['x'], tgt['y'])
    assert mid['target']['nums'] == [] and mid['lit'] == [], mid
    assert mid['pill']['bad'] and 'no free ports' in mid['pill']['text'], mid
    assert wall_pins(page, wall) == [(0, 15), (1, 16)]
    page.evaluate(RESET_JS, ids)
    page.wait_for_timeout(300)


def test_a_fully_placed_screen_lights_nothing_and_refuses_the_drop(dock_page):
    page, ids = dock_page
    page.evaluate(RESET_JS, ids)
    page.wait_for_timeout(400)
    wall, card = ids['wall'], ids['cardId']
    page.evaluate("""async (ids) => {
        await window.app._assignmentRequest(
            '/api/port-assignments/place-overflow', 'POST',
            {layerId: String(ids.wall), cardId: ids.cardId});
        window.app.resetHistory('Dock Seed');
    }""", ids)
    page.wait_for_timeout(400)
    placed = wall_pins(page, wall)
    assert placed == [(i, i + 1) for i in range(6)], placed
    before = page.evaluate(HIST_LEN_JS)

    sx, sy = dock_grip_center(page, f'card-{card}')
    tgt = port_point(page, wall, 3)
    mid = drag(page, sx, sy, tgt['x'], tgt['y'])
    assert mid['target']['nums'] == [], mid
    assert mid['lit'] == [], f'a fully placed screen lit under the drag: {mid}'
    assert mid['pill'] == {
        'text': 'Every port of WALL is already on a processor - clear it first',
        'bad': True}, mid
    assert page.evaluate(STATUS_JS) == (
        'Every port of WALL is already on a processor - clear it first')
    assert wall_pins(page, wall) == placed, 'the refusal moved something'
    assert wall_pins(page, wall, from_server=True) == placed
    assert page.evaluate(HIST_LEN_JS) == before, (
        'a refused drop must not write history')
    page.evaluate(RESET_JS, ids)
    page.wait_for_timeout(300)


# ── the other chips ───────────────────────────────────────────────────────

def test_a_single_port_chip_still_drops_one_port(dock_page):
    page, ids = dock_page
    page.evaluate(RESET_JS, ids)
    page.wait_for_timeout(400)
    wall, card = ids['wall'], ids['cardId']

    sx, sy = dock_tile_center(page, f'port-{card}-9')
    tgt = port_point(page, wall, 2)
    mid = drag(page, sx, sy, tgt['x'], tgt['y'])
    assert mid['target'] == {'kind': 'run', 'layerId': wall, 'num': 2}, mid
    assert mid['lit'] == [(wall, 2)], mid
    assert mid['pill'] is None, f'a port chip wears no count pill: {mid}'
    assert wall_pins(page, wall) == [(1, 9)], page.evaluate(PINS_JS)
    assert page.evaluate(HIST_JS, 1) == ['Place Port']
    page.evaluate(RESET_JS, ids)
    page.wait_for_timeout(300)


def test_a_processor_chip_behaves_as_its_first_card(dock_page):
    page, ids = dock_page
    page.evaluate(RESET_JS, ids)
    page.wait_for_timeout(400)
    wall = ids['wall']

    sx, sy = dock_grip_center(page, f'processor-{ids["procId"]}')
    tgt = port_point(page, wall, 2)
    mid = drag(page, sx, sy, tgt['x'], tgt['y'])
    assert mid['target']['nums'] == [1, 2], mid
    assert mid['lit'] == [(wall, 1), (wall, 2)], mid
    assert mid['pill'] == {'text': '2 ports', 'bad': False}, mid
    assert wall_pins(page, wall) == [(0, 1), (1, 2)], page.evaluate(PINS_JS)
    assert all(p['cardId'] == ids['cardId']
               for p in page.evaluate(PINS_JS)), page.evaluate(PINS_JS)
    assert page.evaluate(HIST_JS, 1) == ['Fill Ports In Order']
    page.evaluate(RESET_JS, ids)
    page.wait_for_timeout(300)


def test_a_box_lights_only_the_free_sockets_inside_its_span(dock_page):
    """A CVT10 on the card's first trunk delivers sockets 1-8 (eight ports
    a trunk on this card). With 3-8 taken, the box has two free: the box
    over port 6 lights ports 1-2 only and the drop lands them on sockets 1
    and 2 - never on the card's free sockets past 8."""
    page, ids = dock_page
    page.evaluate(RESET_JS, ids)
    wall, card = ids['wall'], ids['cardId']
    box = page.evaluate("""async (ids) => {
        const app = window.app;
        await fetch(`/api/processors/${ids.procId}/cards/${ids.cardId}/cvts`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({deviceId: 'novastar-cvt10'})});
        await app.refreshProcessors();
        const c = app._processorsResolved[0].slots
            .map(s => s.card).find(Boolean);
        const cvt = c.cvts[0];
        const nums = cvt.ports.map(p => p.number);
        return {id: cvt.id, first: Math.min(...nums), last: Math.max(...nums)};
    }""", ids)
    page.wait_for_timeout(600)
    assert (box['first'], box['last']) == (1, 8), box
    try:
        # FILLER's first six ports on sockets 3-8, by hand
        page.evaluate("""async (ids) => {
            const app = window.app;
            for (let i = 0; i < 6; i++) {
                await app._assignmentRequest('/api/port-assignments/place',
                    'POST', {layerId: String(ids.filler), index: i,
                             cardId: ids.cardId, port: 3 + i, confirm: false});
            }
            app.resetHistory('Dock Seed');
        }""", ids)
        page.wait_for_timeout(400)
        assert wall_pins(page, ids['filler']) == [(i, 3 + i) for i in range(6)]

        sx, sy = dock_grip_center(page, f'box-{box["id"]}')
        tgt = port_point(page, wall, 6)
        mid = drag(page, sx, sy, tgt['x'], tgt['y'])
        assert mid['target']['nums'] == [1, 2], mid
        assert mid['lit'] == [(wall, 1), (wall, 2)], (
            f'the box must cap at the free sockets inside its span: {mid}')
        assert mid['pill'] == {'text': '2 of 6 ports', 'bad': False}, mid
        assert wall_pins(page, wall) == [(0, 1), (1, 2)], page.evaluate(PINS_JS)
        assert unplaced(page, wall) == [2, 3, 4, 5]
        assert page.evaluate(HIST_JS, 1) == ['Fill Ports In Order']
    finally:
        page.evaluate("""async (args) => {
            await fetch(`/api/processors/${args.ids.procId}/cvts/${args.box.id}`,
                        {method: 'DELETE'});
            await window.app.refreshProcessors();
        }""", {'ids': ids, 'box': box})
        page.evaluate(RESET_JS, ids)
        page.wait_for_timeout(400)


def test_a_custom_flow_screen_counts_its_drawn_ports_the_same_way(dock_page):
    page, ids = dock_page
    page.evaluate(RESET_JS, ids)
    cust, card = ids['cust'], ids['cardId']
    try:
        need = page.evaluate("""async (id) => {
            const app = window.app;
            const l = app.project.layers.find(x => x.id === id);
            const row = r => [0, 1, 2, 3].map(col => ({row: r, col}));
            l.flowPattern = 'custom';
            l.customPortPaths = {1: row(0), 2: row(1), 3: row(2)};
            app.renderHardwareDock();
            window.canvasRenderer.render();
            await app.refreshPortAssignment();
            app.resetHistory('Dock Seed');
            return app.getLayerPortsRequired(l);
        }""", cust)
        page.wait_for_timeout(500)
        assert need == 3, need
        assert unplaced(page, cust) == [0, 1, 2]

        sx, sy = dock_grip_center(page, f'card-{card}')
        tgt = port_point(page, cust, 2)
        mid = drag(page, sx, sy, tgt['x'], tgt['y'])
        assert mid['target']['nums'] == [1, 2], mid
        assert mid['lit'] == [(cust, 1), (cust, 2)], mid
        assert mid['pill'] == {'text': '2 ports', 'bad': False}, mid
        assert wall_pins(page, cust) == [(0, 1), (1, 2)], page.evaluate(PINS_JS)
        assert unplaced(page, cust) == [2]
    finally:
        page.evaluate("""async (id) => {
            const app = window.app;
            const l = app.project.layers.find(x => x.id === id);
            l.flowPattern = 'tl-h';
            delete l.customPortPaths;
            app.renderHardwareDock();
            await app.refreshPortAssignment();
        }""", cust)
        page.evaluate(RESET_JS, ids)
        page.wait_for_timeout(300)


def test_the_platform_refusal_is_the_servers_sentence_unchanged(dock_page):
    """A Brompton wall over the H card: nothing lights, no count pill, and
    the drop comes back refused in the server's own words, moving nothing."""
    page, ids = dock_page
    page.evaluate(RESET_JS, ids)
    page.wait_for_timeout(400)
    bromp, card = ids['bromp'], ids['cardId']
    before = page.evaluate(HIST_LEN_JS)

    sx, sy = dock_grip_center(page, f'card-{card}')
    tgt = port_point(page, bromp, 1)
    mid = drag(page, sx, sy, tgt['x'], tgt['y'])
    assert mid['target']['kind'] == 'screen' and mid['target']['nums'] == [], (
        mid)
    assert mid['lit'] == [], f'the wall lit under a card it cannot use: {mid}'
    assert mid['pill'] is None, mid
    err = page.evaluate("() => window.app._assignmentError")
    assert err == ('BROMP is programmed Brompton Tessera; '
                   'H9 slot 1 is NovaStar legacy gear.'), err
    assert page.evaluate(PINS_JS) == [], 'the refused drop pinned something'
    assert page.evaluate(SERVER_PINS_JS) == []
    assert page.evaluate(HIST_LEN_JS) == before
    page.evaluate(RESET_JS, ids)
    page.wait_for_timeout(300)
