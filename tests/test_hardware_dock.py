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
    that (distro, number); an occupied slot is the JOIN, not a refusal; a
    drop on a circuit past the multi's FIRST splits the multi there (the
    drop implies the boundary; see the section at the end), and the slot
    chips wear their six tail sockets as pips
  * a whole DISTRO dropped on a screen gives its unassigned multis that
    distro, numbered automatically
  * dragging an occupied port tile / slot chip back onto the dock releases
    the assignment, undoably
  * an invalid target refuses with a reason (status bar), nothing mutates
  * a port chip is ALSO the port's editor (the dock is the one place ports
    appear): a press released without movement opens it in place, a drag -
    past _dockArmDrag's 4px threshold - never opens it, and an open chip
    still drags (deep editor coverage lives in test_port_tiles.py)

And the right-click clears (real button='right' clicks), the other way back:
  * a drawn port run offers "Clear port <label>" - the existing unpin, one
    'Release Port' undo step - and an auto run offers it DISABLED with the
    drag-back reason as its title
  * a dock port chip clears its pinned claimant; free and auto chips are
    disabled with their reasons
  * a dock card clears every pin on the card as ONE undo step
  * a power circuit run offers "Clear multi <name>" - number then distro,
    one 'Clear Multi' undo step - disabled with the reason when unassigned
  * a slot chip clears every member of its (distro, number) box in one step;
    the distro chip clears every multi assigned to it in one step
  * a right-click on nothing clearable keeps the item off the menu entirely,
    and the menu closes on click-away as it always has
  * the menu is SCOPED to what was clicked: a dock chip's menu is exactly its
    own clear (no layer/canvas items over hardware, no cross-domain
    vocabulary), a chip-less tray spot opens no menu at all, and the canvas
    keeps its layer menu with the clear joining it only over a drawn run

The dock folds from the chevron above its top edge (initSidebarToggles' dock
row - the sidebar collapse transposed; its drag-resize lives in
test_sidebar_resize.py with the rest of that system).

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
HIST_LEN_JS = "() => window.app.history.length"

# The context menu's clear item as the user sees it after a right-click:
# whether the menu opened, whether the item is on it, what it says, and the
# reason a disabled one carries in its title.
CLEAR_ITEM_JS = """() => {
    const menu = document.getElementById('context-menu');
    const item = menu ? menu.querySelector('[data-action="hw-clear"]') : null;
    if (!menu || !item) return null;
    const r = menu.getBoundingClientRect();
    return {
        menuShown: menu.style.display === 'block',
        shown: item.style.display !== 'none',
        label: (item.textContent || '').trim(),
        title: item.title,
        disabled: item.classList.contains('menu-disabled'),
        menuX: r.left, menuY: r.top,
    };
}"""

MENU_SHOWN_JS = ("() => document.getElementById('context-menu')"
                 ".style.display === 'block'")

# Everything the open menu offers, in the user's terms: which items (and how
# many dividers) are actually visible. The scoping tests assert on this whole
# list, because "the right item is there" says nothing about what is wrongly
# there beside it.
MENU_ITEMS_JS = """() => {
    const menu = document.getElementById('context-menu');
    const shown = menu && menu.style.display === 'block';
    return {
        menuShown: !!shown,
        items: !shown ? [] : Array.from(
            menu.querySelectorAll('.menu-option'))
            .filter(el => getComputedStyle(el).display !== 'none')
            .map(el => el.dataset.action),
        dividers: !shown ? 0 : Array.from(
            menu.querySelectorAll('.menu-divider'))
            .filter(el => getComputedStyle(el).display !== 'none').length,
    };
}"""

# The layer/canvas actions the menu carries everywhere ON the canvas - and
# which have no business appearing over dock hardware: "Delete Layer" beside
# "Clear port 3" reads as an offer to delete the chip.
LAYER_ITEMS = ['undo', 'redo', 'copy', 'paste', 'duplicate', 'delete',
               'prev-port', 'next-port']

POWER_STATE_JS = """(layerId) => {
    const l = window.app.project.layers.find(x => x.id === layerId);
    return {distro: l.powerSocaDistro || {}, num: l.powerSocaNumber || {}};
}"""


def right_click(page, x, y):
    """A real right-click, and what the clear item looks like once the
    menu is up."""
    page.mouse.click(x, y, button='right')
    page.wait_for_timeout(400)
    return page.evaluate(CLEAR_ITEM_JS)


def take_clear(page):
    page.locator('#context-menu [data-action="hw-clear"]').click()
    page.wait_for_timeout(800)


def close_menu(page):
    """Click-away on an empty canvas corner. NOT (30, 30): that is the menu
    BAR, whose item handler stops propagation, so the document-level click
    that hides the context menu never fires and the menu stays up - covering
    whatever the next right-click aims at."""
    pt = page.evaluate("""() => {
        const r = window.canvasRenderer.canvas.getBoundingClientRect();
        return {x: r.left + 15, y: r.top + 15};
    }""")
    page.mouse.click(pt['x'], pt['y'])
    page.wait_for_timeout(250)
    assert not page.evaluate(MENU_SHOWN_JS), 'click-away did not close it'


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
    # An open chip grows past the dock body's visible area, so the raw
    # bounding box can name a point no click can reach (elementFromPoint
    # returns null there). Scroll it into view first - exactly what a
    # user's eye-then-hand does, and what locator.click() would do.
    page.evaluate(
        """(key) => {
            const el = document.querySelector(`[data-hwdock="${key}"]`);
            if (el) el.scrollIntoView({ block: 'nearest' });
        }""", key)
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
    """The fold is the sidebar collapse transposed: the chevron above the
    tray's top edge (initSidebarToggles' dock row), not the old section
    arrow, and the canvas backing store follows the height it frees."""
    page, ids = dock_page
    open_view(page, 'data-flow')
    before = page.evaluate(
        "() => document.getElementById('canvas-wrapper').clientHeight")
    page.locator('#hardware-dock-toggle').click()
    page.wait_for_timeout(600)
    folded = page.evaluate("""() => ({
        wrapH: document.getElementById('canvas-wrapper').clientHeight,
        canvasH: document.getElementById('main-canvas').height,
        dockH: document.getElementById('hardware-dock')
            .getBoundingClientRect().height,
        collapsed: document.getElementById('hardware-dock')
            .classList.contains('collapsed'),
    })""")
    assert folded['collapsed'] and folded['dockH'] < 2, (
        f'the toggle did not fold the tray: {folded}')
    assert folded['wrapH'] > before, (
        f'folding the dock gave no room back: {before} -> {folded}')
    assert folded['canvasH'] == folded['wrapH'], (
        f'the canvas backing store missed the fold: {folded}')
    page.locator('#hardware-dock-toggle').click()
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


CHIP_STATE_JS = """(tid) => {
    const tile = document.querySelector(`[data-lrd-tile="${tid}"]`);
    if (!tile) return null;
    const vis = (el) => !!el && el.getClientRects().length > 0;
    return {
        open: tile.classList.contains('lrd-tile-open'),
        editorPainted: vis(tile.querySelector(':scope > .lrd-tile-body')),
        ghost: !!document.getElementById('hw-dock-ghost'),
        dragLive: !!window.app._dockDrag,
    };
}"""


def test_a_click_opens_the_chip_and_a_drag_never_does(dock_page):
    """The chip is both drag handle and the port's editor, split by
    _dockArmDrag's 4px threshold - the same latitude every drag on the
    canvas gives. A press released without movement (or inside 4px) is the
    click that opens the editor in place; a press-and-move past 4px is the
    drag, and the drag's synthetic click is swallowed so a drop back on the
    chip never doubles as an open. An open chip still drags."""
    page, ids = dock_page
    open_view(page, 'data-flow')
    page.evaluate(RESET_DATA_JS, ids)
    page.wait_for_timeout(400)
    tid = f'port-{ids["cardId"]}-16'

    # a plain click opens the editor in place; no drag ever armed
    sx, sy = dock_tile_center(page, tid)
    page.mouse.click(sx, sy)
    page.wait_for_timeout(200)
    s = page.evaluate(CHIP_STATE_JS, tid)
    assert s['open'] and s['editorPainted'], (
        f'the click did not open the chip editor: {s}')
    assert not s['ghost'] and not s['dragLive'], (
        f'a plain click armed a drag: {s}')

    # the face closes its own chip (it moved - the open chip spans the row)
    sx, sy = dock_tile_center(page, tid)
    page.mouse.click(sx, sy)
    page.wait_for_timeout(200)
    assert not page.evaluate(CHIP_STATE_JS, tid)['open'], (
        'the second click did not close the editor')

    # a sub-threshold jiggle is still the click: 2px of travel opens
    sx, sy = dock_tile_center(page, tid)
    page.mouse.move(sx, sy)
    page.mouse.down()
    page.mouse.move(sx + 2, sy + 1)
    page.mouse.up()
    page.wait_for_timeout(200)
    assert page.evaluate(CHIP_STATE_JS, tid)['open'], (
        'a 2px jiggle - inside the 4px threshold - did not count as the '
        'click')
    sx, sy = dock_tile_center(page, tid)
    page.mouse.click(sx, sy)   # close again
    page.wait_for_timeout(200)

    # a real drag that ends back ON the same chip: the synthetic click is
    # swallowed, so the drop does not double as an open
    sx, sy = dock_tile_center(page, tid)
    page.mouse.move(sx, sy)
    page.mouse.down()
    page.mouse.move(sx + 30, sy + 8, steps=4)
    mid = page.evaluate(CHIP_STATE_JS, tid)
    page.mouse.move(sx + 2, sy + 1, steps=4)
    page.mouse.up()
    page.wait_for_timeout(300)
    assert mid['ghost'] and mid['dragLive'], (
        f'a 30px press-and-move did not arm the drag: {mid}')
    s = page.evaluate(CHIP_STATE_JS, tid)
    assert not s['open'], (
        f'the drag\'s synthetic click opened the editor: {s}')
    assert not s['ghost'] and not s['dragLive'], f'the drag never ended: {s}'

    # an open chip still drags: press-and-move on the open face arms the
    # drag, and the editor neither closes nor re-opens around the gesture
    sx, sy = dock_tile_center(page, tid)
    page.mouse.click(sx, sy)
    page.wait_for_timeout(200)
    assert page.evaluate(CHIP_STATE_JS, tid)['open']
    sx, sy = dock_tile_center(page, tid)
    page.mouse.move(sx, sy)
    page.mouse.down()
    page.mouse.move(sx + 40, sy + 6, steps=4)
    mid = page.evaluate(CHIP_STATE_JS, tid)
    page.mouse.move(sx + 3, sy, steps=4)
    page.mouse.up()
    page.wait_for_timeout(300)
    assert mid['dragLive'], f'an open chip no longer drags: {mid}'
    s = page.evaluate(CHIP_STATE_JS, tid)
    assert s['open'], f'dragging an open chip closed its editor: {s}'
    sx, sy = dock_tile_center(page, tid)
    page.mouse.click(sx, sy)   # leave it closed
    page.wait_for_timeout(200)


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
    'free' and say what they carry, in the backup gold - the dock is where
    a drag would start, so the claim has to be visible before the refusal
    is needed. Two registers, by whether the main is working: a socket
    whose main carries a screen displays that screen-port's RETURN (the
    mirrored occupancy, derived through the backup link), and one whose
    main is free states the bare role. WALL A's five auto ports sit on the
    odds 1-9 and WALL B on 11, so socket 2 is a working return and socket
    14 (main 13, free) is the bare role."""
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
        const grab = (n) => document.querySelector(
            `[data-hwdock="port-${ids.cardId}-${n}"]`);
        const even = grab(2);
        const idle = grab(14);
        const odd = grab(1);
        return {
            even: even ? even.textContent : null,
            evenTitle: even ? even.title : null,
            evenOccupied: even ? even.closest('.lrd-tile')
                .classList.contains('lrd-tile-occupied') : null,
            idle: idle ? idle.textContent : null,
            idleTitle: idle ? idle.title : null,
            odd: odd ? odd.textContent : null,
        };
    }""", ids)
    try:
        assert out['even'] and 'WALL A p1 return' in out['even'], out
        assert 'WALL A p1 return' in (out['evenTitle'] or ''), out
        assert out['evenOccupied'] is True, (
            f'a working return must wear the occupied ground: {out}')
        assert out['idle'] and 'backs up' in out['idle'], out
        assert 'return end' in (out['idleTitle'] or ''), out
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


def test_a_mirrored_return_refuses_clear_and_drag_back_naming_the_screen(
        dock_page):
    """The mirrored return is display, not a claim of its own: it follows
    the main, so both ways of releasing it are refused AT the backup
    socket, each naming the screen it carries and pointing at the main
    where the clear actually lands. Nothing mutates and nothing joins the
    history - the mirror is derived, so there is nothing to undo."""
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
    try:
        pins_before = page.evaluate(PINS_JS)
        hist_before = page.evaluate(HIST_LEN_JS)
        x, y = dock_tile_center(page, f"port-{ids['cardId']}-2")

        item = right_click(page, x, y)
        assert item and item['shown'], item
        assert item['disabled'], (
            f'the mirrored return offered an enabled clear: {item}')
        assert "carries WALL A p1's return" in item['title'], item
        assert 'clear that port' in item['title'], item
        close_menu(page)

        # The drag-back says the same sentence: a hop that ends anywhere
        # inside the tray is the release gesture for a port tile.
        inside = page.evaluate("""() => {
            const r = document.getElementById('hardware-dock')
                .getBoundingClientRect();
            return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
        }""")
        drag(page, x, y, inside['x'], inside['y'])
        said = page.evaluate(
            "() => document.getElementById('status-message').textContent")
        assert "carries WALL A p1's return" in said, said
        assert page.evaluate(PINS_JS) == pins_before, (
            'a refused release moved a pin')
        assert page.evaluate(HIST_LEN_JS) == hist_before, (
            'a refusal earned a history entry')
    finally:
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


def test_a_redundant_pair_reads_as_one_group_in_the_dock(dock_page):
    """A redundant pair is ONE loom and reads as ONE group: on a redundant
    SX40 box B nests under the A it backs and D under C - two pairs, not
    four sibling strips - and a designated 1:1 backup machine nests whole,
    name strip and all, under its main. Same rule, both levels; the chips
    inside keep their keys either way."""
    page, ids = dock_page
    open_view(page, 'data-flow')
    made = page.evaluate("""async () => {
        const send = (url, method, body) => fetch(url, { method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body) }).then(r => r.json());
        const sx = await send('/api/processors', 'POST',
                              { deviceId: 'brompton-sx40' });
        const sxProc = sx.resolved[sx.resolved.length - 1];
        await send(`/api/processors/${sxProc.id}`, 'PUT',
                   { redundancy: true });
        const m = await send('/api/processors', 'POST',
                             { deviceId: 'novastar-mx20' });
        const mainProc = m.resolved[m.resolved.length - 1];
        const b = await send('/api/processors', 'POST',
                             { deviceId: 'novastar-mx20' });
        const backProc = b.resolved[b.resolved.length - 1];
        const mainCard = mainProc.slots[0].card.id;
        const backCard = backProc.slots[0].card.id;
        await send(`/api/processors/${mainProc.id}`, 'PUT',
                   { redundancy: true });
        await send(`/api/processors/${mainProc.id}/cards/${mainCard}`,
                   'PUT', { backupCardId: backCard });
        await window.app.refreshProcessors();
        const resolvedSx = window.app._processorsResolved
            .find(p => p.id === sxProc.id);
        return {
            sxId: sxProc.id, mainId: mainProc.id, backId: backProc.id,
            mainCard, backCard,
            sxCvts: resolvedSx.slots[0].card.cvts.map(c => c.id),
        };
    }""")
    page.wait_for_timeout(1200)
    out = page.evaluate("""(made) => {
        const boxOf = (id) => {
            const h = document.querySelector(`[data-hwdock="box-${id}"]`);
            return h && h.closest('.hw-dock-box');
        };
        const [a, b, c, d] = made.sxCvts.map(boxOf);
        const backUnit = document.querySelector(
            `[data-hwdock="card-${made.backCard}"]`);
        const backProcEl = backUnit && backUnit.closest('.hw-dock-proc');
        const mainUnit = document.querySelector(
            `[data-hwdock="card-${made.mainCard}"]`);
        const paired = (main, backup) => !!(main && backup
            && main.parentElement.classList.contains('lrd-red-pair')
            && main.parentElement === backup.parentElement);
        return {
            built: !!(a && b && c && d && backUnit && mainUnit),
            bIsBackup: !!(b && b.classList.contains('lrd-red-backup')),
            dIsBackup: !!(d && d.classList.contains('lrd-red-backup')),
            abPaired: paired(a, b),
            cdPaired: paired(c, d),
            pairsDistinct: !!(a && c
                              && a.parentElement !== c.parentElement),
            unitNested: !!(backProcEl
                && backProcEl.classList.contains('lrd-red-backup')),
            unitPairHoldsMain: !!(backProcEl && mainUnit
                && backProcEl.parentElement.classList
                    .contains('lrd-red-pair')
                && backProcEl.parentElement.contains(mainUnit)),
            chipsKeyed: !!document.querySelector(
                `[data-hwdock="port-${made.backCard}-1"]`),
        };
    }""", made)
    try:
        assert out['built'], out
        assert out['bIsBackup'] and out['abPaired'], out
        assert out['dIsBackup'] and out['cdPaired'], out
        assert out['pairsDistinct'], (
            f'A/B and C/D collapsed into one bracket: {out}')
        assert out['unitNested'] and out['unitPairHoldsMain'], out
        assert out['chipsKeyed'], (
            f'nesting cost the backup unit its tiles: {out}')
    finally:
        page.evaluate("""async (made) => {
            const send = (url, method, body) => fetch(url, { method,
                headers: { 'Content-Type': 'application/json' },
                body: body === undefined ? undefined
                    : JSON.stringify(body) }).then(r => r.json());
            for (const id of [made.backId, made.mainId, made.sxId]) {
                await send(`/api/processors/${id}`, 'DELETE');
            }
            await window.app.refreshProcessors();
        }""", made)
        page.wait_for_timeout(600)


# ── right-click: clear from the run or the chip ───────────────────────────
#
# The same releases the drag-back performs, reachable without a drag. Every
# item confirms nothing - clearing is undoable and touches only the
# assignment - and every impossible clear is offered DISABLED with the
# reason as its title, so the rule is read before the gesture, not after.


def test_right_click_on_a_run_clears_its_pin(dock_page):
    page, ids = dock_page
    open_view(page, 'data-flow')
    page.evaluate(RESET_DATA_JS, ids)
    # a pinned run to clear - the same placement the drag-back test uses
    page.evaluate("""async (ids) => {
        const app = window.app;
        await app._assignmentRequest('/api/port-assignments/place', 'POST',
            {layerId: String(ids.aId), index: 1, cardId: ids.cardId,
             port: 8, confirm: false});
        app.resetHistory('Dock Seed');
    }""", ids)
    page.wait_for_timeout(500)
    assert len(page.evaluate(PINS_JS)) == 5

    tgt = panel_point(page, ids['aId'], {'port': 2})
    item = right_click(page, tgt['x'], tgt['y'])
    assert item and item['menuShown'], 'no context menu opened on the run'
    assert item['shown'], 'the clear item is not on the menu over a run'
    assert not item['disabled'], item
    assert item['label'].startswith('Clear port '), item
    # the menu opens where the cursor is (clamped to the window at worst)
    assert abs(item['menuX'] - tgt['x']) < 300, item
    assert abs(item['menuY'] - tgt['y']) < 300, item

    take_clear(page)
    assert not page.evaluate(MENU_SHOWN_JS), 'the menu stayed open'
    pins = page.evaluate(PINS_JS)
    assert not any(p['index'] == 1 and p['layerId'] == str(ids['aId'])
                   for p in pins), f'the pin was not released: {pins}'
    assert page.evaluate(HIST_JS, 1) == ['Release Port']
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(900)
    assert any(p['port'] == 8 for p in page.evaluate(PINS_JS)), (
        'undo did not restore the cleared pin')
    page.evaluate(RESET_DATA_JS, ids)
    page.wait_for_timeout(300)


def test_an_auto_run_offers_the_clear_disabled_with_the_reason(dock_page):
    page, ids = dock_page
    open_view(page, 'data-flow')
    page.evaluate(RESET_DATA_JS, ids)
    page.wait_for_timeout(500)

    tgt = panel_point(page, ids['aId'], {'port': 2})
    item = right_click(page, tgt['x'], tgt['y'])
    assert item['shown'] and item['disabled'], item
    assert 'numbered automatically' in item['title'], item
    assert 'no pin to release' in item['title'], item
    # a click on the disabled item performs NOTHING. The menu itself closes,
    # because this menu closes on every document click - the existing
    # click-away behaviour, which applies to the item too.
    take_clear(page)
    assert not page.evaluate(MENU_SHOWN_JS), (
        'the menu ignored the click-away rule it has everywhere else')
    assert page.evaluate(PINS_JS) == [], 'a disabled clear still cleared'
    assert page.evaluate(HIST_JS, 1) == ['Dock Seed'], (
        'a disabled clear earned a history entry')


def test_a_dock_card_right_click_clears_every_pin_as_one_step(dock_page):
    page, ids = dock_page
    open_view(page, 'data-flow')
    page.evaluate(RESET_DATA_JS, ids)
    page.evaluate("""async (ids) => {
        const app = window.app;
        await app._assignmentRequest('/api/port-assignments/place', 'POST',
            {layerId: String(ids.aId), index: 1, cardId: ids.cardId,
             port: 8, confirm: false});
        app.resetHistory('Dock Seed');
    }""", ids)
    page.wait_for_timeout(500)
    assert len(page.evaluate(PINS_JS)) == 5
    before = page.evaluate(HIST_LEN_JS)

    sx, sy = dock_tile_center(page, f'card-{ids["cardId"]}')
    item = right_click(page, sx, sy)
    assert item['shown'] and not item['disabled'], item
    assert item['label'].startswith('Clear '), item
    take_clear(page)
    assert page.evaluate(PINS_JS) == [], 'the card clear left pins behind'
    assert page.evaluate(HIST_JS, 1) == ['Release Ports']
    assert page.evaluate(HIST_LEN_JS) == before + 1, (
        'the batch clear is not ONE history entry')
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(900)
    assert len(page.evaluate(PINS_JS)) == 5, (
        'one undo did not put every pin back')
    page.evaluate(RESET_DATA_JS, ids)
    page.wait_for_timeout(300)


def test_a_dock_port_chip_clears_only_a_pinned_claimant(dock_page):
    page, ids = dock_page
    open_view(page, 'data-flow')
    page.evaluate(RESET_DATA_JS, ids)
    page.wait_for_timeout(500)

    # an AUTO claimant: nothing to release, and the title says what would
    sx, sy = dock_tile_center(page, f'port-{ids["cardId"]}-3')
    item = right_click(page, sx, sy)
    assert item['shown'] and item['disabled'], item
    assert 'no pin to release' in item['title'], item
    close_menu(page)

    # a FREE socket: nothing on it at all
    sx, sy = dock_tile_center(page, f'port-{ids["cardId"]}-16')
    item = right_click(page, sx, sy)
    assert item['shown'] and item['disabled'], item
    assert 'free' in item['title'], item
    close_menu(page)

    # a PINNED claimant clears, same release as the drag-back
    page.evaluate("""async (ids) => {
        const app = window.app;
        await app._assignmentRequest('/api/port-assignments/place', 'POST',
            {layerId: String(ids.aId), index: 1, cardId: ids.cardId,
             port: 8, confirm: false});
        app.resetHistory('Dock Seed');
    }""", ids)
    page.wait_for_timeout(500)
    sx, sy = dock_tile_center(page, f'port-{ids["cardId"]}-8')
    item = right_click(page, sx, sy)
    assert item['shown'] and not item['disabled'], item
    take_clear(page)
    pins = page.evaluate(PINS_JS)
    assert not any(p['port'] == 8 for p in pins), (
        f'the chip clear did not release the pin: {pins}')
    assert page.evaluate(HIST_JS, 1) == ['Release Port']
    page.evaluate(RESET_DATA_JS, ids)
    page.wait_for_timeout(300)


def test_right_click_on_a_circuit_clears_the_multi_in_one_step(dock_page):
    page, ids = dock_page
    open_view(page, 'power')
    page.evaluate(RESET_POWER_JS, ids)
    page.wait_for_timeout(500)

    # unassigned first: the item is there, disabled, and says why
    tgt = panel_point(page, ids['aId'], {'circuit': 0})
    item = right_click(page, tgt['x'], tgt['y'])
    assert item['shown'] and item['disabled'], item
    assert 'not on a distro' in item['title'], item
    close_menu(page)

    page.evaluate("""(ids) => {
        const app = window.app;
        const a = app.project.layers.find(x => x.id === ids.aId);
        app.setSocaDistro(a, 1, ids.distroId);
        app.setSocaNumber(a, 1, 1);
        app._restateNaming();
        app.resetHistory('Dock Seed');
    }""", ids)
    page.wait_for_timeout(700)
    before = page.evaluate(HIST_LEN_JS)

    tgt = panel_point(page, ids['aId'], {'circuit': 0})
    item = right_click(page, tgt['x'], tgt['y'])
    assert item['shown'] and not item['disabled'], item
    assert item['label'].startswith('Clear multi '), item
    take_clear(page)
    out = page.evaluate(POWER_STATE_JS, ids['aId'])
    assert out == {'distro': {}, 'num': {}}, (
        f'the clear did not unassign the multi: {out}')
    assert page.evaluate(HIST_JS, 1) == ['Clear Multi']
    assert page.evaluate(HIST_LEN_JS) == before + 1, (
        'the multi clear is not ONE history entry')
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(900)
    out = page.evaluate(POWER_STATE_JS, ids['aId'])
    assert out['distro'] == {'1': ids['distroId']} and out['num'] == {'1': 1}, (
        f'one undo did not restore distro AND number: {out}')
    page.evaluate(RESET_POWER_JS, ids)


def test_a_slot_chip_right_click_clears_every_member_in_one_step(dock_page):
    """The chip is the box: two screens joined on one (distro, number) both
    come off it, one undo entry, one undo puts both back."""
    page, ids = dock_page
    open_view(page, 'power')
    page.evaluate(RESET_POWER_JS, ids)
    page.evaluate("""(ids) => {
        const app = window.app;
        const a = app.project.layers.find(x => x.id === ids.aId);
        const b = app.project.layers.find(x => x.id === ids.bId);
        app.setSocaDistro(a, 1, ids.distroId);
        app.setSocaNumber(a, 1, 1);
        app.setSocaDistro(b, 1, ids.distroId);
        app.setSocaNumber(b, 1, 1);
        app._restateNaming();
        app.resetHistory('Dock Seed');
    }""", ids)
    page.wait_for_timeout(700)
    before = page.evaluate(HIST_LEN_JS)

    sx, sy = dock_tile_center(page, f'slot-{ids["distroId"]}-1')
    item = right_click(page, sx, sy)
    assert item['shown'] and not item['disabled'], item
    assert item['label'].startswith('Clear '), item
    take_clear(page)
    for lid in (ids['aId'], ids['bId']):
        out = page.evaluate(POWER_STATE_JS, lid)
        assert out == {'distro': {}, 'num': {}}, (
            f'layer {lid} kept its assignment: {out}')
    assert page.evaluate(HIST_JS, 1) == ['Clear Multi']
    assert page.evaluate(HIST_LEN_JS) == before + 1, (
        'the box clear is not ONE history entry')
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(900)
    for lid in (ids['aId'], ids['bId']):
        out = page.evaluate(POWER_STATE_JS, lid)
        assert out['distro'] == {'1': ids['distroId']}, (
            f'one undo did not restore layer {lid}: {out}')
    page.evaluate(RESET_POWER_JS, ids)


def test_the_distro_chip_right_click_clears_every_multi_on_it(dock_page):
    page, ids = dock_page
    open_view(page, 'power')
    page.evaluate(RESET_POWER_JS, ids)
    page.wait_for_timeout(500)

    # nothing assigned: the item is there, disabled, and says why
    sx, sy = dock_tile_center(page, f'distro-{ids["distroId"]}')
    item = right_click(page, sx, sy)
    assert item['shown'] and item['disabled'], item
    assert 'No multis are assigned' in item['title'], item
    close_menu(page)

    # both screens feeding off it, auto numbers - the clear takes them all
    page.evaluate("""(ids) => {
        const app = window.app;
        const a = app.project.layers.find(x => x.id === ids.aId);
        const b = app.project.layers.find(x => x.id === ids.bId);
        app.setSocaDistro(a, 1, ids.distroId);
        app.setSocaDistro(b, 1, ids.distroId);
        app._restateNaming();
        app.resetHistory('Dock Seed');
    }""", ids)
    page.wait_for_timeout(700)
    before = page.evaluate(HIST_LEN_JS)

    sx, sy = dock_tile_center(page, f'distro-{ids["distroId"]}')
    item = right_click(page, sx, sy)
    assert item['shown'] and not item['disabled'], item
    take_clear(page)
    for lid in (ids['aId'], ids['bId']):
        out = page.evaluate(POWER_STATE_JS, lid)
        assert out['distro'] == {}, f'layer {lid} kept its distro: {out}'
    assert page.evaluate(HIST_JS, 1) == ['Clear Distro']
    assert page.evaluate(HIST_LEN_JS) == before + 1, (
        'the distro clear is not ONE history entry')
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(900)
    for lid in (ids['aId'], ids['bId']):
        out = page.evaluate(POWER_STATE_JS, lid)
        assert out['distro'] == {'1': ids['distroId']}, (
            f'one undo did not restore layer {lid}: {out}')
    page.evaluate(RESET_POWER_JS, ids)


def test_right_click_on_nothing_clearable_keeps_the_item_off_the_menu(dock_page):
    page, ids = dock_page
    open_view(page, 'data-flow')
    page.evaluate(RESET_DATA_JS, ids)
    page.wait_for_timeout(400)
    # a canvas point left of every panel (world x < 0 at this pan/zoom)
    corner = page.evaluate("""() => {
        const rect = window.canvasRenderer.canvas.getBoundingClientRect();
        return {x: rect.left + 15, y: rect.top + 15};
    }""")
    item = right_click(page, corner['x'], corner['y'])
    assert item['menuShown'], 'the ordinary context menu should still open'
    assert not item['shown'], (
        'the clear item is on the menu with nothing clearable under the '
        'cursor')
    # ... and the canvas surface keeps its ordinary layer menu - the dock
    # scoping must not strip the canvas of anything.
    state = page.evaluate(MENU_ITEMS_JS)
    for action in LAYER_ITEMS:
        assert action in state['items'], (
            f'the canvas menu lost its {action} item: {state}')
    close_menu(page)


# ── right-click: the menu is scoped to what was clicked ───────────────────
#
# Reported from user testing: right-clicking dock hardware offered the whole
# layer menu - Copy, Paste, Delete Layer, Previous/Next Port - beside the
# chip's own clear. The rule now pinned: a context menu lists ONLY actions
# applicable to the exact thing under the cursor. A dock chip gets its one
# clear (still disabled-with-reason where the action is impossible); a
# chip-less spot in the tray gets NO menu, because an empty menu teaches
# nothing; and the canvas keeps its layer menu, with the clear joining it
# only over a drawn run.


def test_a_dock_data_chip_menu_offers_only_that_chips_action(dock_page):
    page, ids = dock_page
    open_view(page, 'data-flow')
    page.evaluate(RESET_DATA_JS, ids)
    page.wait_for_timeout(400)

    # a port chip: exactly the port's clear, nothing about layers or multis
    sx, sy = dock_tile_center(page, f'port-{ids["cardId"]}-3')
    item = right_click(page, sx, sy)
    assert item['menuShown'] and item['shown'], item
    state = page.evaluate(MENU_ITEMS_JS)
    assert state['items'] == ['hw-clear'], (
        f'a dock port chip offers more than its own action: {state}')
    assert state['dividers'] == 0, (
        f'a lone item needs no divider above it: {state}')
    assert 'port 3' in item['label'], item
    assert 'multi' not in item['label'] and 'distro' not in item['label'], (
        f'a data chip is wearing power vocabulary: {item}')
    close_menu(page)

    # the whole card: still exactly one action, the card's
    sx, sy = dock_tile_center(page, f'card-{ids["cardId"]}')
    item = right_click(page, sx, sy)
    assert item['menuShown'] and item['shown'], item
    state = page.evaluate(MENU_ITEMS_JS)
    assert state['items'] == ['hw-clear'], (
        f'a dock card offers more than its own action: {state}')
    close_menu(page)


def test_a_dock_power_chip_menu_offers_only_that_chips_action(dock_page):
    page, ids = dock_page
    open_view(page, 'power')
    page.evaluate(RESET_POWER_JS, ids)
    page.wait_for_timeout(500)

    # a multi slot chip: exactly the slot's clear, nothing about layers/ports
    sx, sy = dock_tile_center(page, f'slot-{ids["distroId"]}-1')
    item = right_click(page, sx, sy)
    assert item['menuShown'] and item['shown'], item
    state = page.evaluate(MENU_ITEMS_JS)
    assert state['items'] == ['hw-clear'], (
        f'a dock slot chip offers more than its own action: {state}')
    assert 'PD 1' in item['label'], item
    assert 'port' not in item['label'].lower(), (
        f'a power chip is wearing data vocabulary: {item}')
    close_menu(page)

    # the distro chip: one action, the distro's
    sx, sy = dock_tile_center(page, f'distro-{ids["distroId"]}')
    item = right_click(page, sx, sy)
    assert item['menuShown'] and item['shown'], item
    state = page.evaluate(MENU_ITEMS_JS)
    assert state['items'] == ['hw-clear'], (
        f'the distro chip offers more than its own action: {state}')
    close_menu(page)


def test_a_chipless_dock_spot_opens_no_menu_at_all(dock_page):
    """The tray's header and its empty ground have no actions, and an empty
    menu is worse than none. The no-menu must also CLOSE a menu a previous
    right-click left open, or the stale one reads as this click's answer."""
    page, ids = dock_page
    open_view(page, 'data-flow')
    page.evaluate(RESET_DATA_JS, ids)
    page.wait_for_timeout(400)

    # leave a menu open on a chip first
    sx, sy = dock_tile_center(page, f'port-{ids["cardId"]}-3')
    item = right_click(page, sx, sy)
    assert item['menuShown'], item

    head = page.locator('#hardware-dock .hw-dock-head').bounding_box()
    state_after = right_click(page, head['x'] + head['width'] * 0.8,
                              head['y'] + head['height'] / 2)
    assert state_after is None or not state_after['menuShown'], (
        f'a chip-less dock spot opened a menu: {state_after}')
    assert not page.evaluate(MENU_SHOWN_JS), (
        'the stale chip menu stayed open over a chip-less right-click')


def test_the_canvas_run_menu_keeps_layer_items_beside_the_clear(dock_page):
    """A drawn run sits ON a screen layer, so both the run's clear and the
    layer's actions apply there - the dock scoping takes nothing from the
    canvas, in either hardware view."""
    page, ids = dock_page

    open_view(page, 'data-flow')
    page.evaluate(RESET_DATA_JS, ids)
    page.wait_for_timeout(400)
    tgt = panel_point(page, ids['aId'], {'port': 2})
    item = right_click(page, tgt['x'], tgt['y'])
    assert item['menuShown'] and item['shown'], item
    assert item['label'].startswith('Clear port '), item
    state = page.evaluate(MENU_ITEMS_JS)
    for action in LAYER_ITEMS + ['hw-clear']:
        assert action in state['items'], (
            f'the data run menu lost its {action} item: {state}')
    close_menu(page)

    open_view(page, 'power')
    page.evaluate(RESET_POWER_JS, ids)
    page.wait_for_timeout(500)
    tgt = panel_point(page, ids['aId'], {'circuit': 0})
    item = right_click(page, tgt['x'], tgt['y'])
    assert item['menuShown'] and item['shown'], item
    assert item['label'].startswith('Clear multi '), item
    state = page.evaluate(MENU_ITEMS_JS)
    for action in LAYER_ITEMS + ['hw-clear']:
        assert action in state['items'], (
            f'the circuit menu lost its {action} item: {state}')
    close_menu(page)


# ── multi slot chips carry six tails; the drop implies the boundary ───────
#
# A multi IS a 6-tail box, so its slot chip wears the six tail sockets as
# pips - who holds each one on hover, the clash red where two stored sets
# collide. And WHICH circuit a slot chip is dropped on decides the gesture:
# the first circuit of a multi takes the whole multi (as always), a LATER
# circuit splits the multi there - the boundary the sidebar's Split select
# used to ask for, implied by the drop (splitSocaOnto, one undo entry for
# split and assignment together). The way back is right-click "Merge back
# into <name>" on the circuit run or the chip, offered only where a stored
# boundary exists.
#
# The screens here are purpose-built off to the side of WALL A/B: 100V x 5A
# against 100W panels puts a 5-tile tl-v column exactly on a circuit, so
# `columns` IS the circuit count (the test_power_shared_socas.py builder's
# arithmetic, on the real server). The distro is named C2 and the incumbent
# pinned to No. 2 so the joined labels reproduce the 2026 NCMF file's
# hand-typed strings character for character.

MERGE_ITEM_JS = """() => {
    const menu = document.getElementById('context-menu');
    const item = menu ? menu.querySelector('[data-action="hw-merge"]') : null;
    if (!menu || !item) return null;
    return {
        menuShown: menu.style.display === 'block',
        shown: item.style.display !== 'none',
        label: (item.textContent || '').trim(),
        title: item.title,
    };
}"""

SPLIT_SEED_JS = """async (which) => {
    const app = window.app;
    const mk = async (name, columns, ox) => {
        const r = await fetch('/api/layer/add', {method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name, columns, rows: 5,
                cabinet_width: 128, cabinet_height: 128,
                offset_x: ox, offset_y: 1200})});
        const made = await r.json();
        await fetch('/api/layer/' + made.id, {method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({powerVoltage: '100', powerAmperage: '5',
                panelWatts: '100', powerOrganized: true, powerMaximize: false,
                powerFlowPattern: 'tl-v'})});
        return made.id;
    };
    const offId = await mk('OFF SL', which.off, 2400);
    const cenId = await mk('CEN SL', which.cen,
                           2400 + which.off * 128 + 256);
    app.project = await (await fetch('/api/project')).json();
    const d = app.addDistro({ name: 'C2' });
    const off = app.project.layers.find(l => l.id === offId);
    const cen = app.project.layers.find(l => l.id === cenId);
    app.setSocaDistro(off, 1, d.id);
    app.setSocaNumber(off, 1, 2);
    app._circuitTailCache = null;
    app.renderLayers();
    // Frame the new pair: they sit below WALL A/B on purpose, so the
    // module's stock framing does not show them.
    const r = window.canvasRenderer;
    r.zoom = 0.25; r.panX = -500; r.panY = -240; r.render();
    app._restateNaming();
    app.resetHistory('Split Seed');
    return { offId, cenId, d2: d.id,
             offCirc: app.screenCircuits(off).length,
             cenCirc: app.screenCircuits(cen).length };
}"""

SPLIT_CLEAN_JS = """async (st) => {
    const app = window.app;
    await fetch('/api/layer/' + st.offId, { method: 'DELETE' });
    await fetch('/api/layer/' + st.cenId, { method: 'DELETE' });
    app.removeDistro(st.d2);
    app.project = await (await fetch('/api/project')).json();
    app.currentLayer = app.project.layers.find(l => l.name === 'WALL A');
    app.selectedLayerIds = new Set([app.currentLayer.id]);
    app._circuitTailCache = null;
    app.renderLayers();
    const r = window.canvasRenderer;
    r.zoom = 0.28; r.panX = 60; r.panY = 40; r.render();
    app.renderHardwareDock();
    app.resetHistory('Dock Seed');
    return true;
}"""


def split_seed(page, ids, off, cen):
    page.evaluate(RESET_POWER_JS, ids)
    page.wait_for_timeout(300)
    st = page.evaluate(SPLIT_SEED_JS, {'off': off, 'cen': cen})
    page.wait_for_timeout(800)
    # columns IS the circuit count, or every drop below aims at the wrong run
    assert st['offCirc'] == off and st['cenCirc'] == cen, st
    return st


def split_clean(page, ids, st):
    page.evaluate(SPLIT_CLEAN_JS, st)
    page.wait_for_timeout(500)
    page.evaluate(RESET_POWER_JS, ids)


def test_a_slot_chip_wears_its_six_tail_sockets(dock_page):
    """The chip is the box, so it shows the fan: six pips, the incumbent's
    four tails lit and named (screen + derived circuit label on hover), the
    two free ones dim - and an untouched slot's chip shows six free pips."""
    page, ids = dock_page
    open_view(page, 'power')
    st = split_seed(page, ids, off=4, cen=4)
    out = page.evaluate("""(st) => {
        const read = (key) => {
            const el = document.querySelector(`[data-hwdock="${key}"]`);
            if (!el) return null;
            return [...el.querySelectorAll('.hw-dock-tail')].map(c => ({
                text: c.textContent,
                used: c.classList.contains('hw-dock-tail-used'),
                clash: c.classList.contains('hw-dock-tail-clash'),
                title: c.title,
            }));
        };
        return { occupied: read(`slot-${st.d2}-2`),
                 empty: read(`slot-${st.d2}-1`) };
    }""", st)
    occ = out['occupied']
    assert occ and len(occ) == 6, out
    assert [c['text'] for c in occ] == ['1', '2', '3', '4', '5', '6'], occ
    assert [c['used'] for c in occ] == [True] * 4 + [False] * 2, occ
    assert not any(c['clash'] for c in occ), occ
    assert 'OFF SL' in occ[0]['title'] and 'C2-2-1' in occ[0]['title'], occ
    assert occ[4]['title'].endswith('free'), occ
    empty = out['empty']
    assert empty and len(empty) == 6, out
    assert not any(c['used'] or c['clash'] for c in empty), empty
    split_clean(page, ids, st)


def test_a_drop_past_the_first_circuit_splits_the_multi_there(dock_page):
    """The 2026 NCMF center-beach shape (2+2), by DRAG alone: box C2 No. 2
    holds OFF SL's four circuits on tails 1-4; dropping its chip on CEN SL's
    THIRD circuit splits CEN's multi after 2, the two tail circuits join the
    box on tails 5-6, and their labels derive C2-2-5 and C2-2-6 - the exact
    strings the reference file hand-typed - as ONE undo entry."""
    page, ids = dock_page
    open_view(page, 'power')
    st = split_seed(page, ids, off=4, cen=4)
    before = page.evaluate(HIST_LEN_JS)

    sx, sy = dock_tile_center(page, f'slot-{st["d2"]}-2')
    tgt = panel_point(page, st['cenId'], {'circuit': 2})
    drag(page, sx, sy, tgt['x'], tgt['y'])
    page.wait_for_timeout(400)
    out = page.evaluate("""(st) => {
        const app = window.app;
        const cen = app.project.layers.find(l => l.id === st.cenId);
        app._circuitTailCache = null;
        const share = app.getSocaShare(cen, 2);
        return {
            splits: cen.powerSocaSplits || [],
            distro: cen.powerSocaDistro || {},
            num: cen.powerSocaNumber || {},
            labels: app.screenCircuits(cen).map(c =>
                app.getPowerCircuitLabel(cen, c.num)),
            tails: share && share.members.map(m => m.tails),
            clash: !!(share && (share.clash || share.overflow)),
        };
    }""", st)
    assert out['splits'] == [2], out
    assert out['distro'] == {'2': st['d2']}, out
    assert out['num'] == {'2': 2}, out
    assert out['labels'][2:] == ['C2-2-5', 'C2-2-6'], (
        f'the joined labels must derive character for character: {out}')
    assert out['tails'] == [[1, 2, 3, 4], [5, 6]], out
    assert out['clash'] is False, out
    assert page.evaluate(HIST_LEN_JS) == before + 1, (
        'split + assignment must be ONE history entry')
    assert page.evaluate(HIST_JS, 1) == ['Split Multi']

    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(900)
    out = page.evaluate("""(st) => {
        const cen = window.app.project.layers.find(l => l.id === st.cenId);
        return { splits: cen.powerSocaSplits || [],
                 distro: cen.powerSocaDistro || {},
                 num: cen.powerSocaNumber || {} };
    }""", st)
    assert out == {'splits': [], 'distro': {}, 'num': {}}, (
        f'one undo did not heal the split and the assignment together: {out}')
    split_clean(page, ids, st)


def test_the_six_two_shape_lands_whole_on_the_grid_boundary(dock_page):
    """The NCMF 6+2: on an 8-circuit screen the 6-grid already puts the
    boundary after circuit 6, so a drop on circuit 7 is the FIRST circuit
    of its multi - the whole 2-circuit multi joins the dropped box's free
    tails with no split stored, through the two existing setters exactly
    as before, and the labels still derive character for character."""
    page, ids = dock_page
    open_view(page, 'power')
    st = split_seed(page, ids, off=4, cen=8)

    sx, sy = dock_tile_center(page, f'slot-{st["d2"]}-2')
    tgt = panel_point(page, st['cenId'], {'circuit': 6})
    drag(page, sx, sy, tgt['x'], tgt['y'])
    page.wait_for_timeout(400)
    out = page.evaluate("""(st) => {
        const app = window.app;
        const cen = app.project.layers.find(l => l.id === st.cenId);
        app._circuitTailCache = null;
        const share = app.getSocaShare(cen, 2);
        return {
            splits: cen.powerSocaSplits || [],
            distro: cen.powerSocaDistro || {},
            num: cen.powerSocaNumber || {},
            shape: app.getSocaPlan(cen).map(s => s.legs.length),
            labels: app.screenCircuits(cen).map(c =>
                app.getPowerCircuitLabel(cen, c.num)),
            tails: share && share.members.map(m => m.tails),
        };
    }""", st)
    assert out['splits'] == [], (
        f'a drop on a first circuit must not store a split: {out}')
    assert out['shape'] == [6, 2], out
    assert out['distro'] == {'2': st['d2']}, out
    assert out['num'] == {'2': 2}, out
    assert out['labels'][6:] == ['C2-2-5', 'C2-2-6'], out
    assert out['tails'] == [[1, 2, 3, 4], [5, 6]], out
    # the whole-multi path is untouched: the two setters, their two entries
    assert page.evaluate(HIST_JS, 2) == \
        ['Assign Multi Distro', 'Set Multi Number']
    split_clean(page, ids, st)


def test_right_click_merges_the_split_back_into_its_head(dock_page):
    """The reverse gesture, now that Un-split left the sidebar: the split-off
    circuit run offers "Merge back into <head>" on right-click, the merge
    removes the boundary (the tail's assignment goes with its identity, the
    existing un-split), one 'Un-split Multi' entry, and one undo puts the
    split back. A circuit with no stored boundary keeps the item off the
    menu entirely."""
    page, ids = dock_page
    open_view(page, 'power')
    st = split_seed(page, ids, off=4, cen=4)
    sx, sy = dock_tile_center(page, f'slot-{st["d2"]}-2')
    tgt = panel_point(page, st['cenId'], {'circuit': 2})
    drag(page, sx, sy, tgt['x'], tgt['y'])
    page.wait_for_timeout(400)

    # no boundary under the cursor -> no merge item. OFF SL's first circuit:
    # assigned, so the clear arms, but nothing to merge - and inside the
    # section's reframed viewport, where WALL A no longer is.
    plain = panel_point(page, st['offId'], {'circuit': 0})
    page.mouse.click(plain['x'], plain['y'], button='right')
    page.wait_for_timeout(400)
    mi = page.evaluate(MERGE_ITEM_JS)
    assert mi and mi['menuShown'] and not mi['shown'], (
        f'the merge item is armed with no boundary under the cursor: {mi}')
    close_menu(page)

    # the split-off run offers the merge, named for the surviving head
    tgt = panel_point(page, st['cenId'], {'circuit': 2})
    page.mouse.click(tgt['x'], tgt['y'], button='right')
    page.wait_for_timeout(400)
    mi = page.evaluate(MERGE_ITEM_JS)
    assert mi and mi['menuShown'] and mi['shown'], mi
    assert mi['label'].startswith('Merge back into '), mi
    before = page.evaluate(HIST_LEN_JS)
    page.locator('#context-menu [data-action="hw-merge"]').click()
    page.wait_for_timeout(800)
    out = page.evaluate("""(st) => {
        const cen = window.app.project.layers.find(l => l.id === st.cenId);
        return { splits: cen.powerSocaSplits || [],
                 distro: cen.powerSocaDistro || {},
                 num: cen.powerSocaNumber || {} };
    }""", st)
    assert out == {'splits': [], 'distro': {}, 'num': {}}, (
        f'the merge did not weld the parts back: {out}')
    assert page.evaluate(HIST_JS, 1) == ['Un-split Multi']
    assert page.evaluate(HIST_LEN_JS) == before + 1

    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(900)
    out = page.evaluate("""(st) => {
        const cen = window.app.project.layers.find(l => l.id === st.cenId);
        return { splits: cen.powerSocaSplits || [],
                 distro: cen.powerSocaDistro || {} };
    }""", st)
    assert out['splits'] == [2] and out['distro'] == {'2': st['d2']}, (
        f'one undo did not restore the split and its assignment: {out}')
    split_clean(page, ids, st)


def test_the_slot_chip_offers_the_merge_for_its_split_off_part(dock_page):
    """The chip is the box: holding a split-off part, its right-click menu
    carries the merge beside the clear - and ONLY those two, the chip
    scoping rule - and the merge from the chip welds the same boundary."""
    page, ids = dock_page
    open_view(page, 'power')
    st = split_seed(page, ids, off=4, cen=4)
    sx, sy = dock_tile_center(page, f'slot-{st["d2"]}-2')
    tgt = panel_point(page, st['cenId'], {'circuit': 2})
    drag(page, sx, sy, tgt['x'], tgt['y'])
    page.wait_for_timeout(400)

    sx, sy = dock_tile_center(page, f'slot-{st["d2"]}-2')
    page.mouse.click(sx, sy, button='right')
    page.wait_for_timeout(400)
    mi = page.evaluate(MERGE_ITEM_JS)
    assert mi and mi['menuShown'] and mi['shown'], mi
    assert mi['label'].startswith('Merge back into '), mi
    state = page.evaluate(MENU_ITEMS_JS)
    assert state['items'] == ['hw-clear', 'hw-merge'], (
        f'the chip menu carries more than its own actions: {state}')
    page.locator('#context-menu [data-action="hw-merge"]').click()
    page.wait_for_timeout(800)
    out = page.evaluate("""(st) => {
        const cen = window.app.project.layers.find(l => l.id === st.cenId);
        return { splits: cen.powerSocaSplits || [],
                 distro: cen.powerSocaDistro || {} };
    }""", st)
    assert out == {'splits': [], 'distro': {}}, (
        f'the chip merge did not weld the parts back: {out}')
    split_clean(page, ids, st)


def test_a_drop_on_a_box_with_no_free_tail_refuses_with_the_counts(dock_page):
    """place-overflow's refusal, in tails: a full box takes nothing, the
    split does not happen for nothing, and the status bar says the counts
    instead of the wall changing."""
    page, ids = dock_page
    open_view(page, 'power')
    st = split_seed(page, ids, off=6, cen=4)
    before = page.evaluate(HIST_LEN_JS)

    sx, sy = dock_tile_center(page, f'slot-{st["d2"]}-2')
    tgt = panel_point(page, st['cenId'], {'circuit': 2})
    drag(page, sx, sy, tgt['x'], tgt['y'])
    page.wait_for_timeout(400)
    out = page.evaluate("""(st) => {
        const cen = window.app.project.layers.find(l => l.id === st.cenId);
        return {
            splits: cen.powerSocaSplits || [],
            distro: cen.powerSocaDistro || {},
            said: document.getElementById('status-message').textContent,
        };
    }""", st)
    assert out['splits'] == [] and out['distro'] == {}, (
        f'a refused drop mutated the wall: {out}')
    assert 'no free tails' in out['said'], out
    assert page.evaluate(HIST_LEN_JS) == before, (
        'a refusal must write no history entry')
    split_clean(page, ids, st)
