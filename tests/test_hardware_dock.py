"""The hardware dock: the tray under the canvas, and drag as THE assignment.

The Data and Power views' hardware sits in a tray between the canvas and the
status bar, and dragging it onto the canvas is how assignments are made. The
dock is the ONE hardware surface: its header bar carries each view's add
cluster and the attachment flag (red with a screen count while anything is
unattached, green when everything is held, rows on demand), the issues strip
under the header carries the warnings with their fix buttons inline, and
every section header names its thing inline beside a ⚙ that opens its
configuration popover.
Every drop goes through the same operations the retired panels' controls
fired (place, move-block, place-overflow, setSocaDistro, setSocaNumber), so
the refusals, the conflict question and the history entries are the ones
those operations always earned.

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
    still drags (deep editor coverage lives in test_port_tiles.py); an
    occupied circuit chip is a tile the same way, holding its label editor
  * the header bar shows each view's own add cluster, wears the attachment
    flag only once there is hardware to attach to, and folds the tray from
    its own chevron through the one stored collapse state
  * the issues strip under the header holds one row per issue with its fix
    buttons inline, and leaves layout entirely (display:none) when empty -
    and it never carries the per-screen overflow rows, which live under
    the attachment flag (red pill, screen count, rows on click, a row
    click centers the canvas on its screen)
  * a header's ⚙ opens the gear popover, which survives the tray's
    wholesale rebuilds while open (its fields keep focus by key), closes on
    outside mousedown, Escape or its anchor vanishing - and a press on a
    header input or button is that control's gesture, never a drag pickup

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
row - the sidebar collapse transposed), and the header bar's own #hw-dock-fold
chevron proxies that same toggle: one mechanism, one stored state
(ledRasterSidebarCollapsed_dock). Its drag-resize lives in
test_sidebar_resize.py with the rest of that system.

Run locally:
    python3 -m pytest tests/test_hardware_dock.py -q --browser chromium
"""

import os
import re
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
        // The MX40 Pro is COEX gear, and since the platform wall
        // (2026-08-28) a screen only lands on gear its Processing setting
        // matches - left unset, selecting a wall would stamp the prefs
        // default (Legacy) onto it and every drop here would refuse.
        await fetch(`/api/layer/${l.id}`, {method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({powerVoltage: 208, powerAmperage: 20,
                                  processorType: 'novastar-coex-1g'})});
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
    """The fold is the sidebar collapse transposed: the header bar's own
    #hw-dock-fold chevron proxies the hanging toggle above the tray's top
    edge (initSidebarToggles' dock row) - one mechanism, one stored state
    under ledRasterSidebarCollapsed_dock - and the canvas backing store
    follows the height the fold frees. The hanging tab is the way back
    once the tray is folded to nothing."""
    page, ids = dock_page
    open_view(page, 'data-flow')
    before = page.evaluate(
        "() => document.getElementById('canvas-wrapper').clientHeight")
    page.locator('#hw-dock-fold').click()
    page.wait_for_timeout(600)
    folded = page.evaluate("""() => ({
        wrapH: document.getElementById('canvas-wrapper').clientHeight,
        canvasH: document.getElementById('main-canvas').height,
        dockH: document.getElementById('hardware-dock')
            .getBoundingClientRect().height,
        collapsed: document.getElementById('hardware-dock')
            .classList.contains('collapsed'),
        stored: localStorage.getItem('ledRasterSidebarCollapsed_dock'),
    })""")
    assert folded['collapsed'] and folded['dockH'] < 2, (
        f'the header chevron did not fold the tray: {folded}')
    assert folded['stored'] == '1', (
        f'the proxied fold missed the one stored state: {folded}')
    assert folded['wrapH'] > before, (
        f'folding the dock gave no room back: {before} -> {folded}')
    assert folded['canvasH'] == folded['wrapH'], (
        f'the canvas backing store missed the fold: {folded}')
    page.locator('#hardware-dock-toggle').click()
    page.wait_for_timeout(600)
    after = page.evaluate("""() => ({
        wrapH: document.getElementById('canvas-wrapper').clientHeight,
        canvasH: document.getElementById('main-canvas').height,
        stored: localStorage.getItem('ledRasterSidebarCollapsed_dock'),
    })""")
    assert after['stored'] == '0', f'unfolding did not store back: {after}'
    assert after['wrapH'] == before and after['canvasH'] == after['wrapH'], (
        f'unfolding did not restore the layout: {before} -> {after}')


# ── the header bar, the issues strip and the gear popover ─────────────────
#
# The tray's chrome, now that the dock is the whole hardware surface: the
# header bar carries each view's add cluster, the attachment flag and the
# fold chevron; the strip under it is the refuse-and-offer surface; every
# section header names its thing inline beside a ⚙ popover. Pinned here:
# what shows in which view, that the strip vanishes when empty, the
# popover's lifecycle across the tray's wholesale rebuilds, and that a
# press on a header control is the control's gesture - never a drag pickup.

HEADBAR_JS = """() => {
    const vis = (id) => {
        const el = document.getElementById(id);
        return !!el && el.offsetParent !== null;
    };
    return {
        data: vis('hw-dock-data-controls'),
        power: vis('hw-dock-power-controls'),
        flag: vis('hw-dock-flag'),
        fold: vis('hw-dock-fold'),
        options: document.querySelectorAll(
            '#processor-add-device option').length,
    };
}"""

STRIP_JS = """() => {
    const strip = document.getElementById('hw-dock-issues');
    return {
        display: getComputedStyle(strip).display,
        rows: Array.from(strip.querySelectorAll('.hw-dock-issue'))
            .map(r => ({
                text: r.querySelector('.hw-dock-issue-msg').textContent,
                mild: r.classList.contains('hw-dock-issue-mild'),
                buttons: Array.from(r.querySelectorAll('button'))
                    .map(b => b.textContent),
            })),
    };
}"""

POP_JS = """(field) => {
    const pop = document.getElementById('hw-gear-popover');
    return {
        shown: !!pop && pop.style.display === 'block',
        hasField: !!(pop && field && pop.querySelector(
            `[data-lrd-field="${field}"]`)),
    };
}"""


def test_the_header_bar_shows_each_views_own_controls(dock_page):
    """Data view offers the processor picker + Add; power view offers
    + Add distro; neither shows the other's cluster. The attachment flag
    shows in both views once there is hardware to attach to (a card with
    a settled capacity, a distro) and hides with the hardware - and the
    retired auto switch stays gone."""
    page, ids = dock_page
    open_view(page, 'data-flow')
    page.wait_for_timeout(300)
    out = page.evaluate(HEADBAR_JS)
    assert out['data'] and not out['power'], out
    assert out['flag'], (
        f'a settled card must raise the attachment flag: {out}')
    assert out['fold'], out
    assert out['options'] > 1, (
        f'the add picker must fill from the processor catalog: {out}')
    assert page.evaluate(
        "() => !document.getElementById('port-assignment-auto')"
        " && !document.getElementById('hw-dock-auto-wrap')"), (
        'the retired auto switch is back in the header')

    # with nothing to attach to - no card with a settled capacity - the
    # flag says nothing: no hardware is the default state of a project,
    # not a problem to nag about (the _overflow_issues gate)
    hid = page.evaluate("""() => {
        const app = window.app;
        const saved = app._assignment;
        app._assignment = { configured: true, auto: true, issues: [],
                            cards: [], screens: [] };
        app.renderHardwareDock();
        const flag = document.getElementById('hw-dock-flag');
        const hidden = flag.classList.contains('view-hidden');
        app._assignment = saved;
        app.renderHardwareDock();
        return { hidden, back: !flag.classList.contains('view-hidden') };
    }""")
    assert hid['hidden'], 'a hardware-less view still waved the flag'
    assert hid['back'], 'restoring the assignment did not restore the flag'

    open_view(page, 'power')
    page.wait_for_timeout(300)
    out = page.evaluate(HEADBAR_JS)
    assert out['power'] and not out['data'], out
    assert out['flag'], (
        f'a distro exists, so the power view wears the flag too: {out}')


def test_the_issues_strip_warns_offers_and_hides_when_empty(dock_page):
    """The refuse-and-offer surface: empty, it leaves layout entirely
    (CSS :empty -> display:none). A project arriving with auto off (the
    endpoint, driven the way a legacy save arrives - the UI carries no
    toggle any more) renders the amber condition row whose inline button
    is the one-click way back; the per-screen "not attached" rows do NOT
    join it, because that story lives under the header's attachment flag.
    A tail claimed twice still renders as a red power row."""
    page, ids = dock_page
    open_view(page, 'data-flow')
    page.evaluate(RESET_DATA_JS, ids)
    page.wait_for_timeout(500)

    st = page.evaluate(STRIP_JS)
    assert st['rows'] == [] and st['display'] == 'none', (
        f'an empty strip must leave layout: {st}')

    # auto lands off at the endpoint; the strip answers with the amber
    # condition and its offer button inline in the row. With auto off
    # every port is unplaced, but the strip stays free of red per-screen
    # rows - the flag wears that count instead.
    page.evaluate(
        "() => window.app._assignmentRequest("
        "'/api/port-assignments', 'PUT', {auto: false})")
    page.wait_for_timeout(700)
    st = page.evaluate(STRIP_JS)
    assert st['display'] != 'none', st
    autoff = [r for r in st['rows'] if 'Auto-numbering is off' in r['text']]
    assert autoff and autoff[0]['mild'], (
        f'auto-off is a condition, so its row is amber: {st}')
    assert autoff[0]['buttons'] == ['Turn auto-numbering on'], st
    assert not any('not attached' in r['text'] for r in st['rows']), (
        f'the overflow rows are back in the strip - they belong under the '
        f'attachment flag: {st}')
    assert all(r['mild'] for r in st['rows']), (
        f'nothing red belongs in the strip here - the unattached story is '
        f'the flag\'s: {st}')

    page.locator(
        '#hw-dock-issues button:has-text("Turn auto-numbering on")').click()
    page.wait_for_timeout(700)
    assert page.evaluate("() => !!window.app._assignment.auto"), (
        'taking the offer did not turn auto back on')
    assert page.evaluate(HIST_JS, 1) == ['Toggle Auto Numbering']
    st = page.evaluate(STRIP_JS)
    assert st['rows'] == [] and st['display'] == 'none', (
        f'taking the offer must clear the strip: {st}')

    # power view: a tail claimed twice is a red question in the same rows.
    # Two STORED tail sets that overlap are the only way a clash exists -
    # an unstored member always deals into the free tails - so both
    # members carry paperwork claiming tail 1.
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
        a.powerSocaPhasePos = { '1': [1, 2, 3] };
        b.powerSocaPhasePos = { '1': [1] };   // WALL A's tail, claimed again
        app.updateLayers([a, b]);
        app._circuitTailCache = null;
        app.renderHardwareDock();
    }""", ids)
    page.wait_for_timeout(600)
    st = page.evaluate(STRIP_JS)
    clash = [r for r in st['rows'] if 'claimed twice' in r['text']]
    assert clash and not clash[0]['mild'], (
        f'the twice-claimed tail must warn red: {st}')
    assert 'PD 1 circuit 1' in clash[0]['text'], st
    assert 'WALL A' in clash[0]['text'] and 'WALL B' in clash[0]['text'], st
    page.evaluate(RESET_POWER_JS, ids)
    page.wait_for_timeout(300)


# ── the attachment flag ───────────────────────────────────────────────────
#
# One pill on the header where the per-screen overflow rows used to stack:
# red with a SCREEN count while any screen has unattached ports (Data) or
# circuits (Power), green when hardware holds everything, hidden while
# there is no hardware to attach to (the header-bar test above pins the
# hidden state). Its rows open on click - closed by default, which is the
# feature - and a row click centers the canvas on the row's screen with a
# transient pulse. All of it is view state: no undo entries, nothing in
# localStorage.

FLAG_JS = """() => {
    const flag = document.getElementById('hw-dock-flag');
    const rows = document.getElementById('hw-dock-attach');
    const strip = document.getElementById('hw-dock-issues');
    const badge = flag && flag.querySelector('.hw-dock-flag-n');
    return {
        shown: !!flag && flag.offsetParent !== null,
        ok: !!flag && flag.classList.contains('hw-dock-flag-ok'),
        text: flag ? flag.textContent : '',
        count: badge ? badge.textContent : null,
        rowsShown: !!rows && getComputedStyle(rows).display !== 'none',
        rows: rows ? Array.from(
            rows.querySelectorAll('.hw-dock-attach-row')).map(r => ({
                name: r.querySelector('.hw-dock-attach-name').textContent,
                cnt: r.querySelector('.hw-dock-attach-cnt').textContent,
                chips: Array.from(
                    r.querySelectorAll('.hw-dock-attach-chip'))
                    .map(c => c.textContent),
            })) : [],
        stripNotAttached: strip ? Array.from(
            strip.querySelectorAll('.hw-dock-issue'))
            .filter(r => r.textContent.includes('not attached')).length : 0,
    };
}"""

# Where the layer's center landed on screen, measured through the
# renderer's own transform (bounds + workspace offset, zoom, pan): dx/dy
# are its distance from the viewport's center in client px.
CENTER_JS = """(layerId) => {
    const r = window.canvasRenderer;
    const l = window.app.project.layers.find(x => x.id === layerId);
    const b = r.getLayerBoundsInActiveView(l);
    const off = r._layerCanvasOffset(l);
    return {
        dx: (b.x + off.wx + b.width / 2) * r.zoom + r.panX
            - r.canvas.width / 2,
        dy: (b.y + off.wy + b.height / 2) * r.zoom + r.panY
            - r.canvas.height / 2,
        pulsing: !!(r._pulse && String(r._pulse.layerId) === String(l.id)),
    };
}"""

SET_AUTO_JS = ("(on) => window.app._assignmentRequest("
               "'/api/port-assignments', 'PUT', {auto: on})")

RESET_PAN_JS = ("() => { const r = window.canvasRenderer; "
                "r.zoom = 0.28; r.panX = 60; r.panY = 40; r.render(); }")


def test_the_flag_counts_screens_and_opens_its_rows_on_demand(dock_page):
    """Data view: auto off leaves every port unattached, so the flag turns
    red counting TWO screens (never six ports), its rows stay closed until
    the pill is clicked, the open rows carry each screen's count and port
    chips (a long run elided), and the strip holds no overflow row while
    the flag speaks. A rebuild mid-look keeps the rows open - session view
    state, no localStorage, no undo entries - and everything attached
    again turns the pill green with nothing left to open."""
    page, ids = dock_page
    open_view(page, 'data-flow')
    page.evaluate(RESET_DATA_JS, ids)
    page.wait_for_timeout(500)

    # everything attached: green, and nothing to open
    st = page.evaluate(FLAG_JS)
    assert st['shown'] and st['ok'], st
    assert 'all attached' in st['text'] and 'not all' not in st['text'], st
    assert st['rows'] == [] and not st['rowsShown'], st

    page.evaluate(SET_AUTO_JS, False)
    page.wait_for_timeout(700)
    st = page.evaluate(FLAG_JS)
    assert st['shown'] and not st['ok'], st
    assert 'not all attached' in st['text'], st
    assert st['count'] == '2', (
        f'the badge counts screens, not ports: {st}')
    assert st['rows'] == [] and not st['rowsShown'], (
        f'the rows must default CLOSED - that is the feature: {st}')
    assert st['stripNotAttached'] == 0, (
        f'the strip must not repeat the flag\'s story: {st}')

    hist = page.evaluate(HIST_LEN_JS)
    page.locator('#hw-dock-flag').click()
    page.wait_for_timeout(400)
    st = page.evaluate(FLAG_JS)
    assert st['rowsShown'], f'the click did not open the rows: {st}'
    got = {r['name']: r for r in st['rows']}
    assert set(got) == {'WALL A', 'WALL B'}, st
    assert got['WALL A']['cnt'] == '5 of 5 ports', st
    assert got['WALL A']['chips'] == ['1', '2', '3', '4', '5'], st
    assert got['WALL B']['cnt'] == '1 of 1 ports', st
    assert got['WALL B']['chips'] == ['1'], st
    assert page.evaluate(HIST_LEN_JS) == hist, (
        'opening the rows is view state - no undo entry')

    # a rebuild mid-look must not slam the rows shut
    page.evaluate("() => window.app.renderHardwareDock()")
    page.wait_for_timeout(300)
    st = page.evaluate(FLAG_JS)
    assert st['rowsShown'] and len(st['rows']) == 2, (
        f'the rebuild slammed the rows shut mid-look: {st}')

    # nothing persisted: the open state lives on the app, not in storage
    assert page.evaluate("""() => Object.keys(localStorage)
        .filter(k => k.toLowerCase().includes('flag')).length""") == 0

    # a long run elides the way a hand says it: 1 2 3 … 9
    chips = page.evaluate("""() => Array.from(window.app._dockBuildFlagRow(
        {layerId: 'x', name: 'X', numbers: [1, 2, 3, 4, 5, 6, 7, 8, 9],
         total: 9}, 'ports')
        .querySelectorAll('.hw-dock-attach-chip'))
        .map(c => c.textContent)""")
    assert chips == ['1', '2', '3', '…', '9'], chips

    # the same click closes them again
    page.locator('#hw-dock-flag').click()
    page.wait_for_timeout(300)
    st = page.evaluate(FLAG_JS)
    assert not st['rowsShown'] and not st['ok'], st

    # recovery through the strip's offer: green, nothing to open
    page.locator(
        '#hw-dock-issues button:has-text("Turn auto-numbering on")').click()
    page.wait_for_timeout(700)
    st = page.evaluate(FLAG_JS)
    assert st['ok'] and st['rows'] == [], st


def test_a_flag_row_click_centers_the_canvas_and_earns_no_undo(dock_page):
    """Clicking a row - the screen's name or one of its chips - pans the
    canvas (zoom untouched) so that screen's bounds sit centered in the
    viewport, arms the ~1.2s landing pulse, and writes NOTHING: no undo
    entry, no project change. Measured through the renderer's own
    transform, never a second implementation of it."""
    page, ids = dock_page
    open_view(page, 'data-flow')
    page.evaluate(RESET_DATA_JS, ids)
    page.evaluate(RESET_PAN_JS)
    page.evaluate(SET_AUTO_JS, False)
    page.wait_for_timeout(700)
    page.locator('#hw-dock-flag').click()
    page.wait_for_timeout(300)

    before = page.evaluate(CENTER_JS, ids['bId'])
    assert abs(before['dx']) > 5 or abs(before['dy']) > 5, (
        f'WALL B is already centered - the assertion would prove '
        f'nothing: {before}')
    zoom = page.evaluate("() => window.canvasRenderer.zoom")
    hist = page.evaluate(HIST_LEN_JS)
    page.locator('.hw-dock-attach-row:has-text("WALL B")').click()
    page.wait_for_timeout(300)
    after = page.evaluate(CENTER_JS, ids['bId'])
    assert abs(after['dx']) < 1 and abs(after['dy']) < 1, (
        f'the row click did not center WALL B: {after}')
    assert page.evaluate("() => window.canvasRenderer.zoom") == zoom, (
        'centering must pan, never zoom')
    assert after['pulsing'], 'the landing pulse never armed'
    assert page.evaluate(HIST_LEN_JS) == hist, (
        'centering is view state - it must not be an undo entry')
    page.wait_for_timeout(1600)
    assert not page.evaluate("() => !!window.canvasRenderer._pulse"), (
        'the pulse must clear itself')

    # a chip is the same gesture aimed at the same screen
    beforeA = page.evaluate(CENTER_JS, ids['aId'])
    assert abs(beforeA['dx']) > 5 or abs(beforeA['dy']) > 5, beforeA
    page.locator('.hw-dock-attach-row:has-text("WALL A") '
                 '.hw-dock-attach-chip').first.click()
    page.wait_for_timeout(300)
    afterA = page.evaluate(CENTER_JS, ids['aId'])
    assert abs(afterA['dx']) < 1 and abs(afterA['dy']) < 1, afterA

    # put the module state back: auto on, flag green, pan re-seeded
    page.locator(
        '#hw-dock-issues button:has-text("Turn auto-numbering on")').click()
    page.wait_for_timeout(700)
    page.evaluate(RESET_PAN_JS)
    st = page.evaluate(FLAG_JS)
    assert st['ok'] and not st['rowsShown'], st


def test_the_flag_reads_circuits_in_the_power_view(dock_page):
    """Power view: the flag counts screens whose circuits' multis are on
    no distro, read off the same soca plan the chips draw from. The rows
    speak circuits, a row click centers the same way, feeding every multi
    turns the pill green, and a screen with no circuits at all never
    counts - nothing to attach is not unattached."""
    page, ids = dock_page
    open_view(page, 'power')
    page.evaluate(RESET_POWER_JS, ids)
    page.wait_for_timeout(500)

    st = page.evaluate(FLAG_JS)
    assert st['shown'] and not st['ok'], st
    assert st['count'] == '2', st
    assert st['rows'] == [] and not st['rowsShown'], (
        f'closed by default here too: {st}')

    page.locator('#hw-dock-flag').click()
    page.wait_for_timeout(400)
    st = page.evaluate(FLAG_JS)
    got = {r['name']: r for r in st['rows']}
    assert set(got) == {'WALL A', 'WALL B'}, st
    assert got['WALL A']['cnt'] == '3 of 3 circuits', st
    assert got['WALL A']['chips'] == ['1', '2', '3'], st
    assert got['WALL B']['cnt'] == '1 of 1 circuits', st

    # a row click centers here too - the same helper, the same rule
    page.evaluate(RESET_PAN_JS)
    hist = page.evaluate(HIST_LEN_JS)
    page.locator('.hw-dock-attach-row:has-text("WALL B")').click()
    page.wait_for_timeout(300)
    after = page.evaluate(CENTER_JS, ids['bId'])
    assert abs(after['dx']) < 1 and abs(after['dy']) < 1, after
    assert page.evaluate(HIST_LEN_JS) == hist

    # every multi fed, through the existing setters: green
    page.evaluate("""(ids) => {
        const app = window.app;
        const a = app.project.layers.find(x => x.id === ids.aId);
        const b = app.project.layers.find(x => x.id === ids.bId);
        app.setSocaDistro(a, 1, ids.distroId);
        app.setSocaDistro(b, 1, ids.distroId);
    }""", ids)
    page.wait_for_timeout(500)
    st = page.evaluate(FLAG_JS)
    assert st['ok'] and st['rows'] == [], st
    assert 'all attached' in st['text'] and 'not all' not in st['text'], st

    page.evaluate(RESET_POWER_JS, ids)
    page.evaluate(RESET_PAN_JS)
    page.wait_for_timeout(300)


def test_the_gear_popover_survives_rebuilds_and_closes_cleanly(dock_page):
    """One popover for every header's ⚙: it opens at the gear with the
    thing's own configuration fields, re-renders in place across the
    tray's wholesale rebuilds while open (its focused field comes back by
    data-lrd-field key), and closes on Escape, on an outside mousedown,
    and when its anchor stops existing."""
    page, ids = dock_page
    open_view(page, 'data-flow')
    page.evaluate(RESET_DATA_JS, ids)
    page.wait_for_timeout(400)
    mode_key = f'processor-card-mode-{ids["cardId"]}'

    page.locator(f'[data-hwpop="card-{ids["cardId"]}"]').click()
    page.wait_for_timeout(300)
    st = page.evaluate(POP_JS, mode_key)
    assert st['shown'] and st['hasField'], (
        f'the card gear did not open its popover: {st}')

    # a focused popover field rides the wholesale rebuild by its key, and
    # the popover itself stays open, re-rendered against fresh state (the
    # restore lands a microtask after the rebuild, so read after a beat)
    page.evaluate("""(key) => {
        document.querySelector(
            `#hw-gear-popover [data-lrd-field="${key}"]`).focus();
        window.app.renderHardwareDock();
    }""", mode_key)
    page.wait_for_timeout(300)
    out = page.evaluate("""() => {
        const el = document.activeElement;
        return {
            shown: document.getElementById('hw-gear-popover')
                .style.display === 'block',
            focusKey: el && el.dataset ? el.dataset.lrdField : null,
        };
    }""")
    assert out['shown'], f'the rebuild closed an open popover: {out}'
    assert out['focusKey'] == mode_key, (
        f'the rebuild lost the popover field focus: {out}')

    page.keyboard.press('Escape')
    page.wait_for_timeout(200)
    assert not page.evaluate(POP_JS, None)['shown'], (
        'Escape did not close the popover')

    page.locator(f'[data-hwpop="card-{ids["cardId"]}"]').click()
    page.wait_for_timeout(300)
    assert page.evaluate(POP_JS, None)['shown']
    corner = page.evaluate("""() => {
        const r = window.canvasRenderer.canvas.getBoundingClientRect();
        return {x: r.left + 15, y: r.top + 15};
    }""")
    page.mouse.click(corner['x'], corner['y'])
    page.wait_for_timeout(200)
    assert not page.evaluate(POP_JS, None)['shown'], (
        'an outside mousedown did not close the popover')

    # an anchor that stops existing takes its popover with it: a distro
    # gear whose distro is removed while the popover is up
    open_view(page, 'power')
    tmp = page.evaluate("""() => {
        const d = window.app.addDistro({ name: 'TMP' });
        window.app.renderHardwareDock();
        return d.id;
    }""")
    page.wait_for_timeout(400)
    page.locator(f'[data-hwpop="distro-{tmp}"]').click()
    page.wait_for_timeout(300)
    st = page.evaluate(POP_JS, f'distro-rating-{tmp}')
    assert st['shown'] and st['hasField'], (
        f'the distro gear did not open its popover: {st}')
    page.evaluate("""(tmp) => {
        window.app.removeDistro(tmp);
        window.app.renderHardwareDock();
    }""", tmp)
    page.wait_for_timeout(300)
    assert not page.evaluate(POP_JS, None)['shown'], (
        'the popover outlived its anchor')


def test_a_press_on_a_header_control_never_arms_a_drag(dock_page):
    """The headers carry live controls now - the inline name field, the
    gear - and a press on one is the control's gesture: no ghost, no drag,
    and the typed name commits as the existing rename. The header keeps
    its grammar around the edit: static text stays the model, the hand
    name lives in the input, the glance keeps its used/capacity count and
    the card header carries no detail text."""
    page, ids = dock_page
    open_view(page, 'data-flow')
    page.evaluate(RESET_DATA_JS, ids)
    page.wait_for_timeout(400)
    key = f'processor-card-name-{ids["cardId"]}'

    box = page.locator(f'[data-lrd-field="{key}"]').bounding_box()
    assert box, 'the card header lost its inline name input'
    cx = box['x'] + box['width'] / 2
    cy = box['y'] + box['height'] / 2
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.move(cx + 30, cy + 6, steps=4)
    mid = page.evaluate("""() => ({
        ghost: !!document.getElementById('hw-dock-ghost'),
        dragLive: !!window.app._dockDrag,
    })""")
    page.mouse.up()
    page.wait_for_timeout(200)
    assert not mid['ghost'] and not mid['dragLive'], (
        f'a press on the name input armed a drag: {mid}')

    try:
        page.locator(f'[data-lrd-field="{key}"]').click()
        page.keyboard.type('SR')
        page.keyboard.press('Tab')
        page.wait_for_timeout(800)
        assert page.evaluate(HIST_JS, 1) == ['Rename Card']
        out = page.evaluate("""(ids) => {
            const head = document.querySelector(
                `[data-hwdock="card-${ids.cardId}"]`);
            const card = window.app._processorsResolved[0].slots
                .map(s => s.card).find(Boolean);
            const use = head.querySelector('.hw-dock-unit-use');
            return {
                name: card.name,
                input: head.querySelector('.hw-dock-name').value,
                model: head.querySelector('.hw-dock-unit-name').textContent,
                use: use && use.textContent,
                info: !!head.querySelector('.hw-dock-unit-info'),
            };
        }""", ids)
        assert out['name'] == 'SR' and out['input'] == 'SR', (
            f'the inline rename did not commit: {out}')
        assert out['model'] and 'SR' not in out['model'], (
            f'the static header text must stay the model name: {out}')
        assert out['use'] and re.fullmatch(r'\d+/\d+', out['use']), (
            f'the card glance must keep its used/capacity count: {out}')
        assert not out['info'], (
            f'the card header carries no detail text: {out}')
    finally:
        page.evaluate("""async (ids) => {
            await fetch(`/api/processors/${ids.procId}/cards/${ids.cardId}`,
                        {method: 'PUT',
                         headers: {'Content-Type': 'application/json'},
                         body: JSON.stringify({name: ''})});
            await window.app.refreshProcessors();
        }""", ids)
        page.evaluate(RESET_DATA_JS, ids)
        page.wait_for_timeout(300)


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
    # 2026-08-29 undo audit: one drag is ONE entry. The drop still drives the
    # two setters, but in record=false mode with a single updateLayers - so
    # one Ctrl+Z takes the whole gesture back and there is no half-state
    # (new distro, pin gone) the user never made.
    assert page.evaluate(HIST_JS, 1) == ['Assign Multi Distro']
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(700)
    out = page.evaluate("""(aId) => {
        const l = window.app.project.layers.find(x => x.id === aId);
        return {distro: l.powerSocaDistro || {}, num: l.powerSocaNumber || {}};
    }""", ids['aId'])
    assert out == {'distro': {}, 'num': {}}, (
        f'one undo did not walk the drop back: {out}')
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
    # 2026-08-29 undo audit: pulling the box off the wall is ONE decision and
    # ONE entry - the same promise the right-click clear (_clearMultis) makes
    # for this very chip - so a single Ctrl+Z puts every feed back at once.
    assert page.evaluate(HIST_JS, 1) == ['Clear Multi']
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(700)
    out = page.evaluate("""(aId) => {
        const l = window.app.project.layers.find(x => x.id === aId);
        return {distro: l.powerSocaDistro || {}, num: l.powerSocaNumber || {}};
    }""", ids['aId'])
    assert out['distro'] == {'1': ids['distroId']} and out['num'] == {'1': 1}, (
        f'one undo did not restore the assignment: {out}')
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
                powerFlowPattern: 'tl-v',
                // Same platform stamp as the module seed: the only card in
                // the project is COEX, and these screens' data ports still
                // have to resolve while the power tests run.
                processorType: 'novastar-coex-1g'})});
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


def test_a_multi_section_wears_six_circuit_chips(dock_page):
    """The data grammar crossed over: a multi renders as a framed SECTION
    (its header the whole-multi drag handle) holding six CIRCUIT CHIPS in
    the port-chip register - tail number, derived circuit label and the
    occupant screen on the face, occupied/clash grounds as the data tiles
    wear them - the incumbent's four tails occupied and named, the two free
    ones dim, and an untouched slot's section shows six free chips."""
    page, ids = dock_page
    open_view(page, 'power')
    st = split_seed(page, ids, off=4, cen=4)
    out = page.evaluate("""(st) => {
        const read = (n) => {
            const head = document.querySelector(
                `[data-hwdock="slot-${st.d2}-${n}"]`);
            const sec = head && head.closest('.hw-dock-multi');
            if (!sec) return null;
            return [1, 2, 3, 4, 5, 6].map(t => {
                const face = sec.querySelector(
                    `[data-hwdock="tail-${st.d2}-${n}-${t}"]`);
                const tile = face && face.closest('.lrd-tile');
                if (!tile) return null;
                return {
                    text: face.textContent,
                    used: tile.classList.contains('lrd-tile-occupied'),
                    clash: tile.classList.contains('lrd-tile-clash'),
                    title: face.title,
                };
            });
        };
        return { occupied: read(2), empty: read(1) };
    }""", st)
    occ = out['occupied']
    assert occ and len(occ) == 6 and all(occ), out
    assert [c['used'] for c in occ] == [True] * 4 + [False] * 2, occ
    assert not any(c['clash'] for c in occ), occ
    # the chip face says tail number + derived label + occupant screen
    assert 'C2-2-1' in occ[0]['text'] and 'OFF SL' in occ[0]['text'], occ
    assert 'OFF SL' in occ[0]['title'] and 'C2-2-1' in occ[0]['title'], occ
    assert 'Circuit 5 - free' in occ[4]['title'], occ
    assert 'free' in occ[4]['text'], occ
    empty = out['empty']
    assert empty and len(empty) == 6 and all(empty), out
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
    # the whole-multi path still drives the two setters - but as ONE entry
    # since the 2026-08-29 undo audit (one drag, one Ctrl+Z).
    assert page.evaluate(HIST_JS, 1) == ['Assign Multi Distro']
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
    assert 'no free circuits' in out['said'], out
    assert page.evaluate(HIST_LEN_JS) == before, (
        'a refusal must write no history entry')
    split_clean(page, ids, st)


# ── the preview lights the drop's whole reach, and a pip drags one circuit ─
#
# Mid-flight, the underlay must light EVERYTHING the release will touch -
# the data tab's rule, where a port drop lights exactly the run it takes.
# A slot chip over a multi's FIRST circuit lights the whole multi; over a
# later circuit it lights the split-off tail and leaves the head dark; a
# distro lights every unassigned multi's circuits and nothing on a screen
# with nothing left to feed. And the slot chip's six tail pips are draggable
# themselves: pip N onto a circuit run puts that ONE circuit on tail N of
# that box (the drop-implied split shrunk to one circuit, the stored tail
# set [N] landing it on the pip), one undo entry, with the clash/occupied
# refusals said in the status bar.

# What the underlay ACTUALLY drew in one render pass: wrap the hook, count
# a run as lit only when the original stroked something, restore, return.
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

POWER_FULL_STATE_JS = """(layerId) => {
    const l = window.app.project.layers.find(x => x.id === layerId);
    return {
        splits: l.powerSocaSplits || [],
        distro: l.powerSocaDistro || {},
        num: l.powerSocaNumber || {},
        pos: l.powerSocaPhasePos || {},
    };
}"""


def drag_probe(page, sx, sy, ex, ey):
    """Drag to (ex, ey), read the DRAWN underlay and the live target
    mid-flight, then end the gesture over the sidebar: no drop target
    there, so nothing mutates and no reset is owed."""
    page.mouse.move(sx, sy)
    page.mouse.down()
    page.mouse.move((sx + ex) / 2, (sy + ey) / 2, steps=5)
    page.mouse.move(ex, ey, steps=5)
    page.wait_for_timeout(250)
    lit = page.evaluate(LIT_RUNS_JS)
    target = page.evaluate("() => window.app._dockDropTarget")
    page.mouse.move(30, 300, steps=3)
    page.mouse.up()
    page.wait_for_timeout(300)
    return sorted(set(map(tuple, lit))), target


def test_the_preview_lights_the_drops_whole_reach(dock_page):
    page, ids = dock_page
    open_view(page, 'power')
    page.evaluate(RESET_POWER_JS, ids)
    page.wait_for_timeout(500)
    before = page.evaluate(HIST_LEN_JS)
    nums = page.evaluate(
        """(aId) => window.app.screenCircuits(
            window.app.project.layers.find(l => l.id === aId))
            .map(c => c.num)""", ids['aId'])
    assert len(nums) == 3, f'WALL A must make three circuits: {nums}'
    whole = sorted((ids['aId'], n) for n in nums)

    # slot over the FIRST circuit: the whole multi lights, all 3 circuits
    sx, sy = dock_tile_center(page, f'slot-{ids["distroId"]}-1')
    tgt = panel_point(page, ids['aId'], {'circuit': 0})
    lit, target = drag_probe(page, sx, sy, tgt['x'], tgt['y'])
    assert lit == whole, (
        f'the whole-multi drop must light every circuit it takes: {lit}')
    assert target and target['nums'] == nums, target

    # slot over a MID circuit: the split-off tail lights, the head stays dark
    sx, sy = dock_tile_center(page, f'slot-{ids["distroId"]}-1')
    tgt = panel_point(page, ids['aId'], {'circuit': 1})
    lit, target = drag_probe(page, sx, sy, tgt['x'], tgt['y'])
    assert lit == sorted((ids['aId'], n) for n in nums[1:]), (
        f'the split drop must light the tail circuits only: {lit}')
    assert target and target['nums'] == nums[1:], target

    # distro over the screen: every unassigned multi's circuits light
    sx, sy = dock_tile_center(page, f'distro-{ids["distroId"]}')
    tgt = panel_point(page, ids['aId'], {'circuit': 1})
    lit, target = drag_probe(page, sx, sy, tgt['x'], tgt['y'])
    assert lit == whole, (
        f'the distro drop must light the unassigned multis: {lit}')
    assert target and target['kind'] == 'screen'
    assert target['nums'] == nums, target

    # ... and on a screen with nothing unassigned, it lights NOTHING -
    # exactly what the drop would feed
    page.evaluate("""(ids) => {
        const app = window.app;
        const a = app.project.layers.find(x => x.id === ids.aId);
        app.setSocaDistro(a, 1, ids.distroId);
        app._restateNaming();
    }""", ids)
    page.wait_for_timeout(600)
    sx, sy = dock_tile_center(page, f'distro-{ids["distroId"]}')
    tgt = panel_point(page, ids['aId'], {'circuit': 1})
    lit, target = drag_probe(page, sx, sy, tgt['x'], tgt['y'])
    assert lit == [], (
        f'a fully-fed screen must light nothing under a distro: {lit}')
    assert target and target['nums'] == [], target

    # the probes ended on dead ground: nothing was dropped, so only the
    # one seeded assignment above may have written history
    assert page.evaluate(HIST_LEN_JS) == before + 1, (
        'a mid-flight preview must never write history')
    page.evaluate(RESET_POWER_JS, ids)
    page.wait_for_timeout(300)


def test_a_tail_pip_drags_one_circuit_onto_its_tail(dock_page):
    """Pip N onto a circuit run: that ONE circuit goes to tail N of that
    box. Mid-multi, the boundary cuts fall out of the drop (one before the
    circuit, one after) - ONE 'Assign Circuit' entry, one undo heals cuts
    and assignment together. A one-circuit multi needs no cut at all. The
    ghost names the pip the whole way."""
    page, ids = dock_page
    open_view(page, 'power')
    page.evaluate(RESET_POWER_JS, ids)
    page.wait_for_timeout(500)
    before = page.evaluate(HIST_LEN_JS)

    # WALL A's middle circuit onto PD 1 tail 3
    sx, sy = dock_tile_center(page, f'tail-{ids["distroId"]}-1-3')
    tgt = panel_point(page, ids['aId'], {'circuit': 1})
    mid = drag(page, sx, sy, tgt['x'], tgt['y'],
               mid_check=lambda p: p.evaluate("""() => ({
                   ghost: (document.getElementById('hw-dock-ghost')
                           || {}).textContent,
                   target: window.app._dockDropTarget})"""))
    assert mid['ghost'] == 'PD 1 circuit 3', mid
    assert mid['target']['kind'] == 'run', mid
    out = page.evaluate(POWER_FULL_STATE_JS, ids['aId'])
    assert out['splits'] == [1, 2], (
        f'the pip drop must isolate the one circuit: {out}')
    assert out['distro'] == {'2': ids['distroId']}, out
    assert out['num'] == {'2': 1}, out
    assert out['pos'] == {'2': [3]}, (
        f'the stored tail set must land the circuit on pip 3: {out}')
    label = page.evaluate("""(aId) => {
        const app = window.app;
        const a = app.project.layers.find(l => l.id === aId);
        app._circuitTailCache = null;
        return app.getPowerCircuitLabel(a, app.screenCircuits(a)[1].num);
    }""", ids['aId'])
    assert label == 'PD1-3', (
        f'the label must derive from the box and the tail: {label}')
    assert page.evaluate(HIST_LEN_JS) == before + 1, (
        'the pip gesture must be ONE history entry')
    assert page.evaluate(HIST_JS, 1) == ['Assign Circuit']
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(900)
    out = page.evaluate(POWER_FULL_STATE_JS, ids['aId'])
    assert out == {'splits': [], 'distro': {}, 'num': {}, 'pos': {}}, (
        f'one undo did not heal the cuts and the assignment together: {out}')

    # WALL B's only circuit is already a multi of its own: no cut stored
    sx, sy = dock_tile_center(page, f'tail-{ids["distroId"]}-1-5')
    tgt = panel_point(page, ids['bId'], {'circuit': 0})
    drag(page, sx, sy, tgt['x'], tgt['y'])
    out = page.evaluate(POWER_FULL_STATE_JS, ids['bId'])
    assert out['splits'] == [], (
        f'a one-circuit multi must take no cut: {out}')
    assert out['distro'] == {'1': ids['distroId']}, out
    assert out['num'] == {'1': 1}, out
    assert out['pos'] == {'1': [5]}, out
    assert page.evaluate(HIST_JS, 1) == ['Assign Circuit']
    page.evaluate(RESET_POWER_JS, ids)
    page.wait_for_timeout(300)


def test_a_held_pip_refuses_and_the_same_seat_is_a_no_op(dock_page):
    """The pips' occupancy conventions, spoken before anything moves: a
    tail a pinned member holds refuses with the holder's name, and the
    circuit's own seat is a no-op said out loud - neither writes history."""
    page, ids = dock_page
    open_view(page, 'power')
    page.evaluate(RESET_POWER_JS, ids)
    page.wait_for_timeout(500)

    # seat WALL B's circuit on PD 1 tail 3 first
    sx, sy = dock_tile_center(page, f'tail-{ids["distroId"]}-1-3')
    tgt = panel_point(page, ids['bId'], {'circuit': 0})
    drag(page, sx, sy, tgt['x'], tgt['y'])
    assert page.evaluate(POWER_FULL_STATE_JS,
                         ids['bId'])['pos'] == {'1': [3]}
    before = page.evaluate(HIST_LEN_JS)

    # the held pip refuses another screen's circuit, naming the holder
    sx, sy = dock_tile_center(page, f'tail-{ids["distroId"]}-1-3')
    tgt = panel_point(page, ids['aId'], {'circuit': 0})
    drag(page, sx, sy, tgt['x'], tgt['y'])
    said = page.evaluate(
        "() => document.getElementById('status-message').textContent")
    assert 'held by WALL B' in said, said
    out = page.evaluate(POWER_FULL_STATE_JS, ids['aId'])
    assert out['distro'] == {} and out['splits'] == [], (
        f'a refused pip drop mutated the wall: {out}')

    # the circuit's own seat: a no-op with a note, never a re-write
    sx, sy = dock_tile_center(page, f'tail-{ids["distroId"]}-1-3')
    tgt = panel_point(page, ids['bId'], {'circuit': 0})
    drag(page, sx, sy, tgt['x'], tgt['y'])
    said = page.evaluate(
        "() => document.getElementById('status-message').textContent")
    assert 'already on PD 1 circuit 3' in said, said
    assert page.evaluate(HIST_LEN_JS) == before, (
        'a refusal and a no-op must write no history entry')
    page.evaluate(RESET_POWER_JS, ids)
    page.wait_for_timeout(300)


def test_the_dock_sections_ports_by_box_with_lettered_headers(dock_page):
    """Within a card, ports group BY BREAKOUT BOX: one bounded section per
    box, headed in the dock's own register - static MODEL text plus an
    inline name INPUT whose placeholder speaks the resolved lettered
    title, lettered by its trunk where nothing else tells four identical
    boxes apart - and its port span; the backup box's section nests under
    its main's. A boxless card keeps its single flat grid.

    The spans read in each box's OWN numbers - all four sections say
    "ports 1-10" - by the 2026-08-27 ruling ("B is 1-10 and D is 1-10",
    "all cvt's are 1-10 or 1-16"): every box's face is silkscreened from
    1 whichever trunk it hangs on, and the card-wide 11-20/21-30/31-40
    this test used to pin are bookkeeping ordinals no hand can find
    beside a socket. The lettered placeholder is what tells the four
    identical 1-10 spans apart."""
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
        await window.app.refreshProcessors();
        const resolved = window.app._processorsResolved
            .find(p => p.id === sxProc.id);
        return { sxId: sxProc.id,
                 sxCvts: resolved.slots[0].card.cvts.map(c => c.id) };
    }""")
    page.wait_for_timeout(1200)
    out = page.evaluate("""([made, cardId]) => {
        const read = (id) => {
            const h = document.querySelector(`[data-hwdock="box-${id}"]`);
            const box = h && h.closest('.hw-dock-box');
            if (!box) return null;
            const inline = h.querySelector('.hw-dock-name');
            return {
                name: h.querySelector('.hw-dock-unit-name').textContent,
                inline: inline && inline.placeholder,
                key: inline && inline.dataset.lrdField,
                detail: h.querySelector('.hw-dock-unit-info').textContent,
                tiles: box.querySelectorAll('.lrd-tile').length,
                backup: box.classList.contains('lrd-red-backup'),
            };
        };
        const flat = document.querySelector(
            `[data-hwdock="card-${cardId}"]`);
        const flatUnit = flat && flat.closest('.hw-dock-unit');
        return {
            boxes: made.sxCvts.map(read),
            flatBoxes: flatUnit
                ? flatUnit.querySelectorAll('.hw-dock-box').length : null,
            flatGrids: flatUnit
                ? flatUnit.querySelectorAll('.lrd-tile-grid').length : null,
        };
    }""", [made, ids['cardId']])
    try:
        assert all(out['boxes']), out
        # The static text is the MODEL (plus the pair tag); the lettered
        # identity - "Tessera XD A" - is the inline name input's
        # placeholder, the resolved displayTitle the server's refusals
        # also speak.
        names = [(b['name'], b['inline'], b['detail'], b['backup'])
                 for b in out['boxes']]
        assert names == [
            ('Tessera XD', 'Tessera XD A', 'ports 1-10', False),
            ('Tessera XD (backup)', 'Tessera XD B', 'ports 1-10', True),
            ('Tessera XD', 'Tessera XD C', 'ports 1-10', False),
            ('Tessera XD (backup)', 'Tessera XD D', 'ports 1-10', True),
        ], f'the sections must be lettered, paired and locally numbered: ' \
           f'{names}'
        assert [b['key'] for b in out['boxes']] == \
            [f'processor-cvt-name-{c}' for c in made['sxCvts']], (
            f'each box name must edit under its own key: {out}')
        assert all(b['tiles'] == 10 for b in out['boxes']), (
            f'each section must hold exactly its own span of chips: {out}')
        assert out['flatBoxes'] == 0 and out['flatGrids'] == 1, (
            f'a boxless card must keep its single flat grid: {out}')
    finally:
        page.evaluate("""async (made) => {
            await fetch(`/api/processors/${made.sxId}`,
                        { method: 'DELETE' });
            await window.app.refreshProcessors();
        }""", made)
        page.wait_for_timeout(600)


# ── the chips wear their load: B's ground meter + C's rack-bar ────────────
#
# Every dock chip carries how full it is, twice (the user's pick of the
# rendered options): the chip's ground fills left-to-right behind the text
# (translucent green, red past capacity) AND a crisp 4px bar rides the
# chip's bottom, with the exact figure on the hover title. Data chips are
# scored by THE authority the canvas badge uses (getPortLoadStats); power
# chips by the soca plan's own leg figures against the screen's
# amps-per-circuit. A free chip shows the empty track and no ground fill;
# a chip with no capacity figure shows NO bar rather than a lying one, and
# says so on hover.

CHIP_FILL_JS = """(key) => {
    const face = document.querySelector(`[data-hwdock="${key}"]`);
    if (!face) return null;
    const tile = face.closest('.lrd-tile');
    const ground = face.querySelector('.hw-dock-fill');
    const bar = face.querySelector('.hw-dock-bar');
    const meat = bar ? bar.querySelector('i') : null;
    const pct = (el) => el ? parseFloat(el.style.width) : null;
    return {
        title: face.title,
        occupied: tile.classList.contains('lrd-tile-occupied'),
        clash: tile.classList.contains('lrd-tile-clash'),
        hasGround: !!ground,
        groundPct: pct(ground),
        groundOver: !!(ground
            && ground.classList.contains('hw-dock-fill-over')),
        hasBar: !!bar,
        barPct: pct(meat),
        barOver: !!(meat && meat.classList.contains('hw-dock-bar-over')),
        // the state ground must stay under the meter, not be replaced by it
        tileBg: getComputedStyle(tile).backgroundColor,
    };
}"""


def test_data_chips_fill_from_the_badges_own_stats(dock_page):
    """The occupied chip's meter and bar both measure exactly what the
    canvas badge measures - getPortLoadStats' load over ITS capacity - and
    the hover carries the figure; a free chip shows the empty track and no
    ground fill; the occupied ground colour survives under the meter."""
    page, ids = dock_page
    open_view(page, 'data-flow')
    page.evaluate(RESET_DATA_JS, ids)
    page.wait_for_timeout(600)

    model = page.evaluate("""(ids) => {
        const app = window.app;
        const r = window.canvasRenderer;
        const a = app.project.layers.find(l => l.id === ids.aId);
        const stats = r.getPortLoadStats(a, app._dockRunPanels(a, 1));
        return stats && { pct: (stats.load / stats.capacity) * 100,
                          state: stats.state };
    }""", ids)
    assert model and 0 < model['pct'] < 100, (
        f'the seed must give port 1 a real partial load: {model}')

    out = page.evaluate(CHIP_FILL_JS, f'port-{ids["cardId"]}-1')
    assert out and out['occupied'], out
    assert out['hasGround'] and out['hasBar'], out
    assert abs(out['groundPct'] - model['pct']) < 0.5, (
        f'the ground meter disagrees with the badge authority: '
        f'{out} vs {model}')
    assert abs(out['barPct'] - model['pct']) < 0.5, out
    assert not out['groundOver'] and not out['barOver'], out
    assert '% ·' in out['title'] and ' px' in out['title'], (
        f'the hover must carry the exact figure: {out["title"]}')
    # the occupied ground is still the occupied ground - the meter layers
    # over it inside the face instead of replacing the tile's state colour
    assert out['tileBg'] == 'rgb(30, 30, 30)', out

    # a free chip: empty track, no ground fill, no figure
    free = page.evaluate(CHIP_FILL_JS, f'port-{ids["cardId"]}-12')
    assert free and not free['occupied'], free
    assert not free['hasGround'], f'a free chip must not fill: {free}'
    assert free['hasBar'] and free['barPct'] == 0, (
        f'a free chip shows the empty track: {free}')


def test_an_over_capacity_port_reddens_both_layers(dock_page):
    """A drawn custom run past the port's capacity - the only way a data
    port goes over, auto keeps itself legal - turns the ground meter and
    the bar red, full-width, with the over figure on hover. The badge's own
    authority decides 'over'; the chip only wears its answer."""
    page, ids = dock_page
    open_view(page, 'data-flow')
    page.evaluate(RESET_DATA_JS, ids)
    page.wait_for_timeout(600)
    try:
        model = page.evaluate("""(ids) => {
            const app = window.app;
            const a = app.project.layers.find(l => l.id === ids.aId);
            // two whole rows on one drawn path: 20 cabinets of 200x200 px,
            // 800k px against the card's ~660k figure
            const path = [];
            for (let row = 0; row < 2; row++) {
                for (let col = 0; col < 10; col++) path.push({ row, col });
            }
            a.flowPattern = 'custom';
            a.customPortPaths = { 1: path };
            app.renderHardwareDock();
            const stats = window.canvasRenderer.getPortLoadStats(
                a, app._dockRunPanels(a, 1));
            return stats && { state: stats.state,
                              pct: (stats.load / stats.capacity) * 100 };
        }""", ids)
        assert model and model['state'] == 'over', (
            f'the seed must overload the port in the model first: {model}')

        out = page.evaluate(CHIP_FILL_JS, f'port-{ids["cardId"]}-1')
        assert out['hasGround'] and out['groundOver'], out
        assert out['groundPct'] == 100, (
            f'an over meter clamps full, the red says the rest: {out}')
        assert out['hasBar'] and out['barOver'] and out['barPct'] == 100, out
        assert '% ·' in out['title'], out
    finally:
        page.evaluate("""(ids) => {
            const a = window.app.project.layers.find(l => l.id === ids.aId);
            a.flowPattern = 'tl-h';
            delete a.customPortPaths;
            window.app.renderHardwareDock();
        }""", ids)
        page.wait_for_timeout(300)


def test_a_port_with_no_capacity_figure_shows_no_bar(dock_page):
    """An unknown processor type has no capacity table, so a bar would be a
    guess drawn as a fact: the chip shows NO track at all and the hover
    says the load was not scored."""
    page, ids = dock_page
    open_view(page, 'data-flow')
    page.evaluate(RESET_DATA_JS, ids)
    page.wait_for_timeout(600)
    try:
        page.evaluate("""(ids) => {
            const a = window.app.project.layers.find(l => l.id === ids.aId);
            a._savedProcessorType = a.processorType;
            a.processorType = 'mystery-brand';
            window.app.renderHardwareDock();
        }""", ids)
        out = page.evaluate(CHIP_FILL_JS, f'port-{ids["cardId"]}-1')
        assert out and out['occupied'], out
        assert not out['hasBar'] and not out['hasGround'], (
            f'no capacity figure must mean no bar: {out}')
        assert 'load not scored' in out['title'], out
    finally:
        page.evaluate("""(ids) => {
            const a = window.app.project.layers.find(l => l.id === ids.aId);
            a.processorType = a._savedProcessorType;
            delete a._savedProcessorType;
            window.app.renderHardwareDock();
        }""", ids)
        page.wait_for_timeout(300)


def test_power_chips_fill_from_the_plans_leg_figures(dock_page):
    """A circuit chip's meter is its leg's amps (getSocaPlan's own figure)
    over the screen's amps-per-circuit, with the exact amps on hover; a
    custom-drawn circuit past the breaker turns both layers red. The free
    chips beside it keep the empty track."""
    page, ids = dock_page
    open_view(page, 'power')
    page.evaluate(RESET_POWER_JS, ids)
    page.wait_for_timeout(500)

    model = page.evaluate("""(ids) => {
        const app = window.app;
        const a = app.project.layers.find(l => l.id === ids.aId);
        a.panelWatts = 200;   // pin the wattage the seed's comment assumes
        app.setSocaDistro(a, 1, ids.distroId);
        app._restateNaming();
        app.renderHardwareDock();
        const s = app.getSocaPlan(a).find(x => x.soca === 1);
        const capA = parseFloat(a.powerAmperage);
        const leg = s.legs.find(l => l.leg === 1);
        return { amps: leg.amps, capA, pct: (leg.amps / capA) * 100 };
    }""", ids)
    assert 0 < model['pct'] < 100, (
        f'the seed must give tail 1 a real partial load: {model}')

    out = page.evaluate(CHIP_FILL_JS, f'tail-{ids["distroId"]}-1-1')
    assert out and out['occupied'], out
    assert out['hasGround'] and out['hasBar'], out
    assert abs(out['groundPct'] - model['pct']) < 0.5, (
        f'the meter disagrees with the plan leg figure: {out} vs {model}')
    assert abs(out['barPct'] - model['pct']) < 0.5, out
    assert not out['groundOver'] and not out['barOver'], out
    assert (f"{model['amps']:.1f} A" in out['title']
            and f"{model['capA']:g} A" in out['title']), (
        f'the hover must say amps over capacity: {out["title"]}')

    # WALL A makes 3 circuits; tails 4-6 are free chips with empty tracks
    free = page.evaluate(CHIP_FILL_JS, f'tail-{ids["distroId"]}-1-5')
    assert free and not free['occupied'], free
    assert not free['hasGround'], free
    assert free['hasBar'] and free['barPct'] == 0, free

    # a custom-drawn circuit of 30 cabinets: 28.8 A on a 20 A circuit
    try:
        over_model = page.evaluate("""(ids) => {
            const app = window.app;
            const a = app.project.layers.find(l => l.id === ids.aId);
            const path = [];
            for (let row = 0; row < 3; row++) {
                for (let col = 0; col < 10; col++) path.push({ row, col });
            }
            a.powerFlowPattern = 'custom';
            a.powerCustomPaths = { 1: path };
            app._circuitTailCache = null;
            app.renderHardwareDock();
            const s = app.getSocaPlan(a).find(x => x.soca === 1);
            const leg = s.legs.find(l => l.leg === 1);
            return { amps: leg.amps, over: leg.amps
                     > parseFloat(a.powerAmperage) };
        }""", ids)
        assert over_model['over'], (
            f'the drawn circuit must overload in the model first: '
            f'{over_model}')
        out = page.evaluate(CHIP_FILL_JS, f'tail-{ids["distroId"]}-1-1')
        assert out['hasGround'] and out['groundOver'], out
        assert out['groundPct'] == 100 and out['barOver'], out
        assert out['barPct'] == 100, out
    finally:
        page.evaluate("""(ids) => {
            const app = window.app;
            const a = app.project.layers.find(l => l.id === ids.aId);
            a.powerFlowPattern = null;
            delete a.powerCustomPaths;
            delete a.panelWatts;
            app._circuitTailCache = null;
            app.renderHardwareDock();
        }""", ids)
        page.evaluate(RESET_POWER_JS, ids)
        page.wait_for_timeout(300)


# ── the sections fold: card, box, distro, multi - one machinery ───────────
#
# Every hardware section folds by the app's one section machinery
# (_wireSectionCollapse: arrow click, header double-click, per-id
# localStorage persistence, re-wired after every rebuild). The folded
# header earns its keep: it keeps being the whole-unit drag handle, and it
# carries a glance readout (count + slim fill line) so a card folded away
# because it is done reads as done. A reveal aimed inside a folded section
# opens it (_expandSectionsFor), and a redundant pair folds as one thing
# under its main while the backup can still fold alone.

FOLD_STATE_JS = """(secId) => {
    const head = document.querySelector(`[data-lrd-sec="${secId}"]`);
    const sec = head && head.parentElement;
    if (!sec) return null;
    const body = sec.querySelector(':scope > .lrd-sec-body');
    return {
        collapsed: sec.classList.contains('lrd-sec-collapsed'),
        bodyHidden: body ? getComputedStyle(body).display === 'none' : null,
        stored: localStorage.getItem(`ledRasterPanelCollapsed_${secId}`),
        hasArrow: !!head.querySelector('.lrd-sec-arrow'),
    };
}"""


def fold_arrow(page, sec_id):
    page.locator(f'[data-lrd-sec="{sec_id}"] .lrd-sec-arrow').click()
    page.wait_for_timeout(250)


def test_every_dock_section_kind_folds_and_persists(dock_page):
    """Card (data), distro and multi (power): arrow folds, the state
    persists per section id and survives the tray's wholesale rebuild,
    and the header's double-click unfolds."""
    page, ids = dock_page
    sections = [
        ('data-flow', f'hwdock-card-{ids["cardId"]}'),
        ('power', f'hwdock-distro-{ids["distroId"]}'),
        ('power', f'hwdock-multi-{ids["distroId"]}-1'),
    ]
    for view, sec in sections:
        open_view(page, view)
        st = page.evaluate(FOLD_STATE_JS, sec)
        assert st and st['hasArrow'] and not st['collapsed'], (
            f'{sec} did not wire as a section: {st}')
        fold_arrow(page, sec)
        st = page.evaluate(FOLD_STATE_JS, sec)
        assert st['collapsed'] and st['bodyHidden'], f'{sec}: {st}'
        assert st['stored'] == '1', f'{sec} did not persist: {st}'
        # the tray rebuilds wholesale on every change; the fold must ride it
        page.evaluate("() => window.app.renderHardwareDock()")
        page.wait_for_timeout(300)
        st = page.evaluate(FOLD_STATE_JS, sec)
        assert st['collapsed'] and st['bodyHidden'], (
            f'{sec} forgot its fold across a rebuild: {st}')
        # double-click on the header is the other unfold gesture - aimed at
        # the grip, because a dblclick landing on a header CONTROL is that
        # control's by design (the name input selects text, it never
        # folds), and a folded section now shrinks to its natural width,
        # which puts the header's center on the name input
        page.locator(f'[data-lrd-sec="{sec}"] .hw-dock-grip').dblclick()
        page.wait_for_timeout(250)
        st = page.evaluate(FOLD_STATE_JS, sec)
        assert not st['collapsed'] and st['stored'] == '0', (
            f'{sec} did not unfold on header double-click: {st}')


def test_a_folded_header_still_drags_its_whole_scope(dock_page):
    """Folding gets a finished unit out of the way without taking its drag
    away: the folded multi header still lands the whole multi on a
    circuit, exactly as the open one does."""
    page, ids = dock_page
    open_view(page, 'power')
    page.evaluate(RESET_POWER_JS, ids)
    page.wait_for_timeout(500)
    sec = f'hwdock-multi-{ids["distroId"]}-1'
    fold_arrow(page, sec)
    assert page.evaluate(FOLD_STATE_JS, sec)['collapsed']
    try:
        sx, sy = dock_tile_center(page, f'slot-{ids["distroId"]}-1')
        tgt = panel_point(page, ids['bId'], {'circuit': 0})
        drag(page, sx, sy, tgt['x'], tgt['y'])
        out = page.evaluate(POWER_STATE_JS, ids['bId'])
        assert out['distro'] == {'1': ids['distroId']}, (
            f'the folded header lost its drop: {out}')
        assert out['num'] == {'1': 1}, out
    finally:
        # unfold (the section id survives the rebuild the drop caused)
        page.evaluate("""(sec) => {
            const head = document.querySelector(`[data-lrd-sec="${sec}"]`);
            if (head) window.app._setSectionCollapsed(
                head.parentElement, false);
        }""", sec)
        page.evaluate(RESET_POWER_JS, ids)
        page.wait_for_timeout(300)


def test_a_reveal_into_a_folded_section_opens_it(dock_page):
    """The _expandSectionsFor doctrine, extended to the tray: a chip the
    app is about to reveal (focus restore, the aim flow) must not stay
    display:none inside a folded section - the fold opens, and the opening
    persists."""
    page, ids = dock_page
    open_view(page, 'data-flow')
    sec = f'hwdock-card-{ids["cardId"]}'
    fold_arrow(page, sec)
    assert page.evaluate(FOLD_STATE_JS, sec)['collapsed']
    out = page.evaluate("""([ids, sec]) => {
        const chip = document.querySelector(
            `[data-hwdock="port-${ids.cardId}-3"]`);
        window.app._expandSectionsFor(chip);
        const head = document.querySelector(`[data-lrd-sec="${sec}"]`);
        return {
            collapsed: head.parentElement.classList
                .contains('lrd-sec-collapsed'),
            stored: localStorage.getItem(`ledRasterPanelCollapsed_${sec}`),
            visible: chip.offsetParent !== null,
        };
    }""", [ids, sec])
    assert not out['collapsed'] and out['stored'] == '0', out
    assert out['visible'], f'the revealed chip is still hidden: {out}'


def test_a_backup_section_folds_with_its_main_and_alone(dock_page):
    """A redundant pair is one thing: folding the MAIN box hides the whole
    nested backup with it (header and all), and unfolding brings it back.
    The backup still folds alone through its own header without touching
    the main - and a reveal aimed inside the hidden backup opens the main
    around it."""
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
        await window.app.refreshProcessors();
        const resolved = window.app._processorsResolved
            .find(p => p.id === sxProc.id);
        const card = resolved.slots[0].card;
        return { sxId: sxProc.id, cardId: card.id,
                 cvtA: card.cvts[0].id, cvtB: card.cvts[1].id };
    }""")
    page.wait_for_timeout(1200)
    try:
        read_pair = """(made) => {
            const headA = document.querySelector(
                `[data-lrd-sec="hwdock-box-${made.cvtA}"]`);
            const headB = document.querySelector(
                `[data-lrd-sec="hwdock-box-${made.cvtB}"]`);
            const boxA = headA && headA.parentElement;
            const boxB = headB && headB.parentElement;
            if (!boxA || !boxB) return null;
            return {
                aCollapsed: boxA.classList.contains('lrd-sec-collapsed'),
                bCollapsed: boxB.classList.contains('lrd-sec-collapsed'),
                bShown: getComputedStyle(boxB).display !== 'none',
                aBodyShown: getComputedStyle(boxA.querySelector(
                    ':scope > .lrd-sec-body')).display !== 'none',
                paired: !!boxB.closest('.lrd-red-pair')
                    && boxB.classList.contains('lrd-red-backup'),
            };
        }"""
        st = page.evaluate(read_pair, made)
        assert st and st['paired'], f'B must nest under A as a pair: {st}'
        assert st['bShown'], st

        # folding the main takes the backup with it, whole
        fold_arrow(page, f'hwdock-box-{made["cvtA"]}')
        st = page.evaluate(read_pair, made)
        assert st['aCollapsed'] and not st['bShown'], (
            f'folding the main must fold the pair: {st}')

        # a reveal aimed inside the hidden backup opens the main around it
        out = page.evaluate("""(made) => {
            const chip = document.querySelector(
                `[data-hwdock="port-${made.cardId}-11"]`);
            window.app._expandSectionsFor(chip);
            return null;
        }""", made)
        st = page.evaluate(read_pair, made)
        assert not st['aCollapsed'] and st['bShown'], (
            f'the reveal did not open the main around the backup: {st}')

        # the backup folds alone, main untouched
        fold_arrow(page, f'hwdock-box-{made["cvtB"]}')
        st = page.evaluate(read_pair, made)
        assert st['bCollapsed'] and not st['aCollapsed'], st
        assert st['bShown'] and st['aBodyShown'], (
            f'the backup folding alone must leave the main open: {st}')
    finally:
        page.evaluate("""async (made) => {
            await fetch(`/api/processors/${made.sxId}`,
                        { method: 'DELETE' });
            await window.app.refreshProcessors();
        }""", made)
        page.wait_for_timeout(600)


def test_the_folded_header_earns_its_keep_with_a_glance(dock_page):
    """The header carries a compact usage readout and a slim fill line -
    the reason folding a finished card is safe: '40/40' and a full green
    line still say everything the open grid said at a squint."""
    page, ids = dock_page
    open_view(page, 'power')
    page.evaluate(RESET_POWER_JS, ids)
    page.evaluate("""(ids) => {
        const app = window.app;
        const b = app.project.layers.find(x => x.id === ids.bId);
        app.setSocaDistro(b, 1, ids.distroId);
        app.setSocaNumber(b, 1, 1);
        app._restateNaming();
        app.renderHardwareDock();
    }""", ids)
    page.wait_for_timeout(500)
    try:
        out = page.evaluate("""(ids) => {
            const head = document.querySelector(
                `[data-hwdock="slot-${ids.distroId}-1"]`);
            const use = head.querySelector('.hw-dock-unit-use');
            const bar = head.querySelector('.hw-dock-headbar > i');
            return {
                use: use && use.textContent,
                barW: bar && parseFloat(bar.style.width),
            };
        }""", ids)
        # WALL B's one circuit sits on tail 1: one of six tails used
        assert out['use'] == '1/6', out
        assert out['barW'] is not None and out['barW'] > 0, (
            f'the glance line must fill with the box load: {out}')

        # the data card header wears the same glance from the assignment's
        # own used/capacity counts
        open_view(page, 'data-flow')
        page.evaluate(RESET_DATA_JS, ids)
        page.wait_for_timeout(500)
        card = page.evaluate("""(ids) => {
            const head = document.querySelector(
                `[data-hwdock="card-${ids.cardId}"]`);
            const bar = head.querySelector('.hw-dock-headbar > i');
            const summary = (window.app._assignment.cards || [])
                .find(c => c.cardId === ids.cardId);
            return {
                barW: bar && parseFloat(bar.style.width),
                expect: summary && summary.capacityKnown
                    ? (summary.used / summary.capacity) * 100 : null,
            };
        }""", ids)
        assert card['expect'] and card['barW'] is not None, card
        assert abs(card['barW'] - card['expect']) < 0.5, (
            f'the card glance disagrees with the assignment summary: {card}')
    finally:
        open_view(page, 'power')
        page.evaluate(RESET_POWER_JS, ids)
        page.wait_for_timeout(300)


# ── the circuit chip speaks for the circuit: click and right-click ────────
#
# The re-pointing that came with the chips: an OCCUPIED circuit chip is a
# tile in the port chips' full grammar - the click that would open a port's
# editor opens the circuit's label override in place, committed to the
# HOLDER's layer only - while a free chip is an un-wired handle with no
# editor to open. And a CIRCUIT chip offers the drawn circuit run's own
# right-click items (clear its multi, merge a split back) from the hardware
# end; the MULTI HEADER keeps the slot's box-wide clear; the DISTRO HEADER
# keeps the distro's. A free chip states its freedom.


def test_an_occupied_circuit_chip_opens_its_label_editor(dock_page):
    """The port chips' grammar crossed over whole: an occupied circuit chip
    is a TILE (ptail-<distro>-<n>-<tail>), a face click opens its label
    override in place (no drag armed), the commit writes the HOLDER's
    layer only under one 'Edit Circuit Label' entry, and a free chip has
    no editor at all - _wireTiles leaves it a plain drag handle."""
    page, ids = dock_page
    open_view(page, 'power')
    page.evaluate(RESET_POWER_JS, ids)
    page.evaluate("""(ids) => {
        const app = window.app;
        const b = app.project.layers.find(x => x.id === ids.bId);
        app.setSocaDistro(b, 1, ids.distroId);
        app.setSocaNumber(b, 1, 1);
        app._restateNaming();
        app.renderHardwareDock();
        app.resetHistory('Dock Seed');
    }""", ids)
    page.wait_for_timeout(600)
    tid = f'ptail-{ids["distroId"]}-1-1'

    # the face click opens the editor in place, no drag armed
    sx, sy = dock_tile_center(page, f'tail-{ids["distroId"]}-1-1')
    page.mouse.click(sx, sy)
    page.wait_for_timeout(300)
    st = page.evaluate(CHIP_STATE_JS, tid)
    assert st and st['open'] and st['editorPainted'], (
        f'the click did not open the circuit chip editor: {st}')
    assert not st['ghost'] and not st['dragLive'], st

    # the label field commits to the holder layer only
    page.locator(
        f'[data-lrd-field="power-label-{ids["bId"]}-1"]').click()
    page.keyboard.type('FOH-1')
    page.keyboard.press('Tab')
    page.wait_for_timeout(800)
    out = page.evaluate("""(ids) => {
        const app = window.app;
        const a = app.project.layers.find(x => x.id === ids.aId);
        const b = app.project.layers.find(x => x.id === ids.bId);
        app._circuitTailCache = null;
        return {
            b: (b.powerLabelOverrides || {})['1'] || null,
            a: a.powerLabelOverrides || null,
            label: app.getPowerCircuitLabel(b, 1),
        };
    }""", ids)
    assert out['b'] == 'FOH-1', f'the override missed the holder: {out}'
    assert not out['a'], f'the commit smeared onto another layer: {out}'
    assert out['label'] == 'FOH-1', (
        f'the typed label must beat the derived one: {out}')
    assert page.evaluate(HIST_JS, 1) == ['Edit Circuit Label']

    # close the open chip, then a FREE chip: no tile wiring, no editor
    sx, sy = dock_tile_center(page, f'tail-{ids["distroId"]}-1-1')
    page.mouse.click(sx, sy)
    page.wait_for_timeout(300)
    sx, sy = dock_tile_center(page, f'tail-{ids["distroId"]}-1-5')
    page.mouse.click(sx, sy)
    page.wait_for_timeout(300)
    free = page.evaluate("""(d) => {
        const face = document.querySelector(
            `[data-hwdock="tail-${d}-1-5"]`);
        const tile = face && face.closest('.lrd-tile');
        if (!tile) return null;
        return {
            open: tile.classList.contains('lrd-tile-open'),
            hasEditor: !!tile.querySelector('.lrd-tile-body'),
            tiled: 'lrdTile' in tile.dataset,
        };
    }""", ids['distroId'])
    assert free and not free['open'] and not free['hasEditor'], (
        f'a free chip opened an editor it does not have: {free}')
    assert not free['tiled'], (
        f'a free chip must stay an un-wired handle: {free}')

    # leave no override and no assignment behind
    page.evaluate("""(ids) => {
        const app = window.app;
        const b = app.project.layers.find(x => x.id === ids.bId);
        if (b.powerLabelOverrides) delete b.powerLabelOverrides['1'];
        app.saveClientSideProperties();
        app.updateLayers([b]);
    }""", ids)
    page.evaluate(RESET_POWER_JS, ids)
    page.wait_for_timeout(300)


def test_a_circuit_chips_menu_is_the_circuit_runs_menu(dock_page):
    page, ids = dock_page
    open_view(page, 'power')
    page.evaluate(RESET_POWER_JS, ids)
    page.evaluate("""(ids) => {
        const app = window.app;
        const b = app.project.layers.find(x => x.id === ids.bId);
        app.setSocaDistro(b, 1, ids.distroId);
        app.setSocaNumber(b, 1, 1);
        app._restateNaming();
        app.renderHardwareDock();
        app.resetHistory('Dock Seed');
    }""", ids)
    page.wait_for_timeout(600)
    before = page.evaluate(HIST_LEN_JS)

    # the chip holding WALL B's circuit - a ONE-circuit multi, so the clear
    # is the circuit-scope clear (2026-08-30: clears forget programming;
    # a chip inside a bigger multi still offers 'Clear multi ...')
    sx, sy = dock_tile_center(page, f'tail-{ids["distroId"]}-1-1')
    item = right_click(page, sx, sy)
    assert item['menuShown'] and item['shown'] and not item['disabled'], item
    assert item['label'].startswith('Clear circuit '), (
        f"the one-circuit chip must offer the circuit-scope clear: {item}")
    state = page.evaluate(MENU_ITEMS_JS)
    assert state['items'] == ['hw-clear'], (
        f'the chip menu carries more than its own actions: {state}')
    take_clear(page)
    out = page.evaluate(POWER_STATE_JS, ids['bId'])
    assert out == {'distro': {}, 'num': {}}, (
        f'the chip clear did not unassign the multi: {out}')
    assert page.evaluate(HIST_JS, 1) == ['Clear Circuit']
    assert page.evaluate(HIST_LEN_JS) == before + 1

    # a free chip: the item is there, disabled, and says why
    sx, sy = dock_tile_center(page, f'tail-{ids["distroId"]}-1-4')
    item = right_click(page, sx, sy)
    assert item['shown'] and item['disabled'], item
    assert 'is free' in item['title'], item
    close_menu(page)
    page.evaluate(RESET_POWER_JS, ids)
    page.wait_for_timeout(300)


def test_a_circuit_chip_offers_the_merge_for_its_split_off_part(dock_page):
    """The chip holding a split-off circuit merges exactly as right-clicking
    that circuit's drawn run does - both surfaces, one boundary."""
    page, ids = dock_page
    open_view(page, 'power')
    st = split_seed(page, ids, off=4, cen=4)
    sx, sy = dock_tile_center(page, f'slot-{st["d2"]}-2')
    tgt = panel_point(page, st['cenId'], {'circuit': 2})
    drag(page, sx, sy, tgt['x'], tgt['y'])
    page.wait_for_timeout(400)

    # CEN SL's split-off circuits joined tails 5-6; the tail-5 chip offers
    # the merge beside the clear - and only those two
    sx, sy = dock_tile_center(page, f'tail-{st["d2"]}-2-5')
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


# ── clears FORGET the stored programming (user ruling, 2026-08-30) ────────
#
# "when i clear a circuit, soca or a distro or sending card i dont want it
# to remember how i had it programmed before with balancing etc". A clear
# used to drop only the assignment and leave the paperwork - the stored
# tail set above all - so re-assigning resurrected the old balance layout.
# Now every clear scope wipes the cleared thing's stored programming in its
# ONE history entry, and one undo restores all of it. Split boundaries stay
# (they define which circuits a multi holds, not how it was programmed);
# the distro's own identity stays; typed PORT names stay on the data side.

POWER_PROGRAMMING_JS = """(layerId) => {
    const l = window.app.project.layers.find(x => x.id === layerId);
    const sp = (l.powerSplitters || {}).manual || {};
    return {
        distro: l.powerSocaDistro || {},
        num: l.powerSocaNumber || {},
        pos: l.powerSocaPhasePos || {},
        names: l.powerSocaNames || {},
        lengths: l.powerSocaLengths || {},
        overrides: l.powerLabelOverrides || {},
        splits: l.powerSocaSplits || [],
        merge: sp.merge || [],
        splitPins: sp.split || [],
    };
}"""

# Wipe the per-test programming seeds these tests add beyond what
# RESET_POWER_JS covers (names, lengths, overrides, splits, splitters).
FULL_POWER_CLEAN_JS = """(ids) => {
    const app = window.app;
    for (const id of [ids.aId, ids.bId]) {
        const l = app.project.layers.find(x => x.id === id);
        if (!l) continue;
        l.powerSocaNames = {};
        l.powerSocaLengths = {};
        l.powerLabelOverrides = {};
        l.powerSocaSplits = [];
        // An explicit empty store, not a delete: an absent key is missing
        // from the update payload and the server keeps whatever it had.
        l.powerSplitters = { enabled: false, maxWays: 3,
                             manual: { merge: [], split: [] } };
        l.powerSocaPhaseOffset = {};
    }
    app._circuitTailCache = null;
    app.updateLayers(app.project.layers.filter(
        l => l.id === ids.aId || l.id === ids.bId));
    return true;
}"""


def test_clear_multi_forgets_programming_and_one_undo_restores_it(dock_page):
    """The multi clear (canvas run right-click) wipes assignment, stored
    tail set, typed name, home-run length, label overrides and manual share
    entries - one 'Clear Multi' entry, one undo restores every store, and
    after the clear the positions deal naturally instead of resurrecting
    the old balance."""
    page, ids = dock_page
    open_view(page, 'power')
    page.evaluate(RESET_POWER_JS, ids)
    page.evaluate(FULL_POWER_CLEAN_JS, ids)
    overridden = page.evaluate("""(ids) => {
        const app = window.app;
        const a = app.project.layers.find(x => x.id === ids.aId);
        app.setSocaDistro(a, 1, ids.distroId, false);
        app.setSocaNumber(a, 1, 1, false);
        a.powerSocaPhasePos = { 1: [2, 3, 5] };
        a.powerSocaNames = { 1: 'STAGE LEFT' };
        a.powerSocaLengths = { 1: '150ft' };
        const c = app.screenCircuits(a)[0].num;
        a.powerLabelOverrides = { [c]: 'HOUSE-1' };
        // A manual share store in the current (auto) id space: the clear
        // must drop the entries covering the multi's circuits.
        a.powerSplitters = { enabled: false, maxWays: 3,
                             manual: { merge: [[1, 2]], split: [3],
                                       space: 'auto' } };
        app._circuitTailCache = null;
        app.updateLayers([a]);
        app._restateNaming();
        app.resetHistory('Dock Seed');
        return c;
    }""", ids)
    page.wait_for_timeout(700)
    before = page.evaluate(HIST_LEN_JS)

    tgt = panel_point(page, ids['aId'], {'circuit': 0})
    item = right_click(page, tgt['x'], tgt['y'])
    assert item['shown'] and not item['disabled'], item
    assert item['label'].startswith('Clear multi '), item
    take_clear(page)
    out = page.evaluate(POWER_PROGRAMMING_JS, ids['aId'])
    assert out['distro'] == {} and out['num'] == {}, out
    assert out['pos'] == {}, (
        f'the stored tail set survived the clear: {out}')
    assert out['names'] == {} and out['lengths'] == {}, (
        f'the typed name / home-run length survived the clear: {out}')
    assert str(overridden) not in out['overrides'], (
        f'the label override survived the clear: {out}')
    assert out['merge'] == [] and out['splitPins'] == [], (
        f'the manual share entries survived the clear: {out}')
    assert page.evaluate(HIST_JS, 1) == ['Clear Multi']
    assert page.evaluate(HIST_LEN_JS) == before + 1, (
        'the multi clear is not ONE history entry')
    # after the clear, positions deal naturally - nothing resurrects
    nat = page.evaluate("""(ids) => {
        const app = window.app;
        const a = app.project.layers.find(x => x.id === ids.aId);
        app._circuitTailCache = null;
        return app.socaCircuitPositions(a, 1, 3);
    }""", ids)
    assert nat == [1, 2, 3], (
        f'a cleared multi must deal naturally, not remember {nat}')

    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(900)
    out = page.evaluate(POWER_PROGRAMMING_JS, ids['aId'])
    assert out['distro'] == {'1': ids['distroId']}, out
    assert out['num'] == {'1': 1}, out
    assert out['pos'] == {'1': [2, 3, 5]}, (
        f'one undo did not restore the stored tail set: {out}')
    assert out['names'] == {'1': 'STAGE LEFT'}, out
    assert out['lengths'] == {'1': '150ft'}, out
    assert out['overrides'].get(str(overridden)) == 'HOUSE-1', out
    assert out['merge'] == [[1, 2]] and out['splitPins'] == [3], out
    page.evaluate(RESET_POWER_JS, ids)
    page.evaluate(FULL_POWER_CLEAN_JS, ids)
    page.wait_for_timeout(300)


def test_clear_circuit_chip_forgets_position_and_override(dock_page):
    """The circuit chip's clear, where its holder is a one-circuit multi
    (the pip drop's product): assignment, stored position and label
    override go in one 'Clear Circuit' entry; the multi's typed name stays
    (identity, not programming); undo restores everything; re-assigning
    deals naturally."""
    page, ids = dock_page
    open_view(page, 'power')
    page.evaluate(RESET_POWER_JS, ids)
    page.evaluate(FULL_POWER_CLEAN_JS, ids)
    page.wait_for_timeout(500)

    # seat WALL B's one circuit on PD 1 circuit 5, then override its label
    sx, sy = dock_tile_center(page, f'tail-{ids["distroId"]}-1-5')
    tgt = panel_point(page, ids['bId'], {'circuit': 0})
    drag(page, sx, sy, tgt['x'], tgt['y'])
    circuit = page.evaluate("""(ids) => {
        const app = window.app;
        const b = app.project.layers.find(x => x.id === ids.bId);
        const c = app.screenCircuits(b)[0].num;
        b.powerLabelOverrides = { [c]: 'DJ-POWER' };
        b.powerSocaNames = { 1: 'B BOX' };
        app._circuitTailCache = null;
        app.updateLayers([b]);
        app._restateNaming();
        app.resetHistory('Dock Seed');
        return c;
    }""", ids)
    page.wait_for_timeout(700)
    before = page.evaluate(HIST_LEN_JS)

    sx, sy = dock_tile_center(page, f'tail-{ids["distroId"]}-1-5')
    item = right_click(page, sx, sy)
    assert item['shown'] and not item['disabled'], item
    assert item['label'].startswith('Clear circuit '), item
    take_clear(page)
    out = page.evaluate(POWER_PROGRAMMING_JS, ids['bId'])
    assert out['distro'] == {} and out['num'] == {}, out
    assert out['pos'] == {}, (
        f'the stored position survived the circuit clear: {out}')
    assert str(circuit) not in out['overrides'], (
        f'the label override survived the circuit clear: {out}')
    assert out['names'] == {'1': 'B BOX'}, (
        f"a circuit clear must keep the multi's typed name: {out}")
    assert page.evaluate(HIST_JS, 1) == ['Clear Circuit']
    assert page.evaluate(HIST_LEN_JS) == before + 1, (
        'the circuit clear is not ONE history entry')

    # re-seating the circuit lands where it is dropped, not where it was
    sx, sy = dock_tile_center(page, f'tail-{ids["distroId"]}-1-2')
    tgt = panel_point(page, ids['bId'], {'circuit': 0})
    drag(page, sx, sy, tgt['x'], tgt['y'])
    out = page.evaluate(POWER_PROGRAMMING_JS, ids['bId'])
    assert out['pos'] == {'1': [2]}, (
        f're-assigning resurrected the old seat: {out}')
    page.evaluate("() => window.app.undo()")   # the re-seat
    page.wait_for_timeout(900)
    page.evaluate("() => window.app.undo()")   # the clear
    page.wait_for_timeout(900)
    out = page.evaluate(POWER_PROGRAMMING_JS, ids['bId'])
    assert out['distro'] == {'1': ids['distroId']}, out
    assert out['num'] == {'1': 1} and out['pos'] == {'1': [5]}, (
        f'undo did not restore the cleared circuit: {out}')
    assert out['overrides'].get(str(circuit)) == 'DJ-POWER', out
    page.evaluate(RESET_POWER_JS, ids)
    page.evaluate(FULL_POWER_CLEAN_JS, ids)
    page.wait_for_timeout(300)


def test_clear_distro_forgets_programming_on_every_member(dock_page):
    """The distro chip's clear wipes every assigned multi's programming in
    its one 'Clear Distro' entry - and the distro itself keeps its name and
    electrical identity."""
    page, ids = dock_page
    open_view(page, 'power')
    page.evaluate(RESET_POWER_JS, ids)
    page.evaluate(FULL_POWER_CLEAN_JS, ids)
    page.evaluate("""(ids) => {
        const app = window.app;
        const a = app.project.layers.find(x => x.id === ids.aId);
        const b = app.project.layers.find(x => x.id === ids.bId);
        app.setSocaDistro(a, 1, ids.distroId, false);
        app.setSocaNumber(a, 1, 1, false);
        app.setSocaDistro(b, 1, ids.distroId, false);
        app.setSocaNumber(b, 1, 2, false);
        a.powerSocaPhasePos = { 1: [2, 4, 6] };
        b.powerSocaPhasePos = { 1: [3] };
        a.powerSocaNames = { 1: 'SL RUN' };
        b.powerSocaLengths = { 1: '75ft' };
        app._circuitTailCache = null;
        app.updateLayers([a, b]);
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
        out = page.evaluate(POWER_PROGRAMMING_JS, lid)
        assert out['distro'] == {} and out['num'] == {}, (lid, out)
        assert out['pos'] == {} and out['names'] == {} \
            and out['lengths'] == {}, (
            f'layer {lid} kept programming past the distro clear: {out}')
    assert page.evaluate(HIST_JS, 1) == ['Clear Distro']
    assert page.evaluate(HIST_LEN_JS) == before + 1
    distro = page.evaluate(
        "(ids) => window.app.getDistros().find(d => d.id === ids.distroId)",
        ids)
    assert distro and distro['name'] == 'PD', (
        f'the distro clear must not touch the distro itself: {distro}')

    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(900)
    a = page.evaluate(POWER_PROGRAMMING_JS, ids['aId'])
    b = page.evaluate(POWER_PROGRAMMING_JS, ids['bId'])
    assert a['pos'] == {'1': [2, 4, 6]} and a['names'] == {'1': 'SL RUN'}, a
    assert b['pos'] == {'1': [3]} and b['lengths'] == {'1': '75ft'}, b
    page.evaluate(RESET_POWER_JS, ids)
    page.evaluate(FULL_POWER_CLEAN_JS, ids)
    page.wait_for_timeout(300)


def test_drag_back_forgets_programming_like_the_clear(dock_page):
    """The slot chip's drag-back wears the same 'Clear Multi' name as the
    right-click clear, so it keeps the same promise: the stored programming
    goes with the assignment."""
    page, ids = dock_page
    open_view(page, 'power')
    page.evaluate(RESET_POWER_JS, ids)
    page.evaluate(FULL_POWER_CLEAN_JS, ids)
    page.evaluate("""(ids) => {
        const app = window.app;
        const a = app.project.layers.find(x => x.id === ids.aId);
        app.setSocaDistro(a, 1, ids.distroId, false);
        app.setSocaNumber(a, 1, 1, false);
        a.powerSocaPhasePos = { 1: [1, 3, 5] };
        a.powerSocaNames = { 1: 'US TRUSS' };
        app._circuitTailCache = null;
        app.updateLayers([a]);
        app._restateNaming();
        app.resetHistory('Dock Seed');
    }""", ids)
    page.wait_for_timeout(700)

    sx, sy = dock_tile_center(page, f'slot-{ids["distroId"]}-1')
    dock_box = page.locator('#hardware-dock-body').bounding_box()
    drag(page, sx, sy, dock_box['x'] + dock_box['width'] * 0.7,
         dock_box['y'] + min(40, dock_box['height'] / 2))
    out = page.evaluate(POWER_PROGRAMMING_JS, ids['aId'])
    assert out['distro'] == {} and out['num'] == {}, out
    assert out['pos'] == {} and out['names'] == {}, (
        f'the drag-back remembered the programming: {out}')
    assert page.evaluate(HIST_JS, 1) == ['Clear Multi']
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(900)
    out = page.evaluate(POWER_PROGRAMMING_JS, ids['aId'])
    assert out['pos'] == {'1': [1, 3, 5]}, (
        f'one undo did not restore the drag-back: {out}')
    assert out['names'] == {'1': 'US TRUSS'}, out
    page.evaluate(RESET_POWER_JS, ids)
    page.evaluate(FULL_POWER_CLEAN_JS, ids)
    page.wait_for_timeout(300)


def test_clear_card_forgets_backup_picks_and_keeps_port_names(dock_page):
    """The data-side card clear: released pins AND the card's per-port
    backup picks go in one entry; typed port names are hardware naming and
    stay. One undo restores the pin and the pick together."""
    page, ids = dock_page
    open_view(page, 'data-flow')
    page.evaluate(RESET_DATA_JS, ids)
    page.wait_for_timeout(500)
    page.evaluate("""async (ids) => {
        const app = window.app;
        const send = (url, body) => fetch(url, { method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body) }).then(r => r.json());
        const base = `/api/processors/${ids.procId}/cards/${ids.cardId}`;
        await send(`${base}/ports/4`, { name: 'HOUSE L' });
        await send(`${base}/ports/4`,
                   { backup: { cardId: ids.cardId, port: 12 } });
        await app.refreshProcessors();
        await app._assignmentRequest('/api/port-assignments/place', 'POST',
            { layerId: String(ids.aId), index: 1, cardId: ids.cardId,
              port: 8, confirm: false }, null, 'Place Port');
        app.resetHistory('Dock Seed');
    }""", ids)
    page.wait_for_timeout(1200)
    assert len(page.evaluate(PINS_JS)) == 5, 'the seed pins did not land'
    before = page.evaluate(HIST_LEN_JS)

    sx, sy = dock_tile_center(page, f'card-{ids["cardId"]}')
    item = right_click(page, sx, sy)
    assert item['shown'] and not item['disabled'], item
    assert 'backup picks' in item['title'], item
    take_clear(page)
    page.wait_for_timeout(1200)
    assert page.evaluate(PINS_JS) == [], 'the pin survived the card clear'
    card = page.evaluate("""(ids) => {
        const found = window.app._dockCardById(ids.cardId);
        return { picks: (found && found.card.backupPorts) || {},
                 names: (found && found.card.portNames) || {} };
    }""", ids)
    assert card['picks'] == {}, (
        f'the backup pick survived the card clear: {card}')
    assert card['names'].get('4') == 'HOUSE L', (
        f'typed port names must stay through the clear: {card}')
    assert page.evaluate(HIST_JS, 1) == ['Clear Card']
    assert page.evaluate(HIST_LEN_JS) == before + 1, (
        'the card clear is not ONE history entry')

    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(1500)
    restored = page.evaluate("""async (ids) => {
        await window.app.refreshProcessors();
        const found = window.app._dockCardById(ids.cardId);
        return { picks: (found && found.card.backupPorts) || {},
                 pins: (window.app.project.port_assignments || {}).pins
                     || [] };
    }""", ids)
    assert (restored['picks'].get('4') or {}).get('port') == 12, (
        f'one undo did not restore the backup pick: {restored}')
    assert len(restored['pins']) == 5, (
        f'one undo did not restore the pins: {restored}')
    # clean: drop the pick and the name, release the pin
    page.evaluate("""async (ids) => {
        const send = (url, body) => fetch(url, { method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body) }).then(r => r.json());
        const base = `/api/processors/${ids.procId}/cards/${ids.cardId}`;
        await send(`${base}/ports/4`, { name: '', backup: null });
        await window.app.refreshProcessors();
    }""", ids)
    page.evaluate(RESET_DATA_JS, ids)
    page.wait_for_timeout(500)


# ── the sweep + the batch verb ("B and then right click", 2026-08-30) ─────
#
# Alt+DRAG across adjacent circuit runs sweeps a contiguous selection (the
# 4px threshold discriminates from the Alt+click takeover); the right-click
# menu then deals the selection as Nfers - "3fer them (1 × 3fer + 1 × 2fer)"
# with the group math in the label - or, with no selection, deals the whole
# screen under the cursor. The remainder RE-DEALS so nothing is orphaned
# (16 @ 3fer -> 3,3,3,3,2,2); a gated screen keeps the entries on the menu
# disabled with the reason. Selection is session view state: no history
# entries, and Esc or a plain click drops it.

BATCH_ITEMS_JS = """() => {
    const menu = document.getElementById('context-menu');
    const vis = el => el && el.style.display !== 'none';
    const grab = a => {
        const el = menu.querySelector(`[data-action="${a}"]`);
        return el && vis(el) ? { label: (el.textContent || '').trim(),
            title: el.title,
            disabled: el.classList.contains('menu-disabled') } : null;
    };
    return { shown: !!menu && menu.style.display === 'block',
             n0: grab('hw-batch-n0'), n1: grab('hw-batch-n1'),
             n2: grab('hw-batch-n2'), unshare: grab('hw-batch-unshare'),
             share: grab('hw-share') };
}"""

SPLITTER_STATE_JS = """(layerId) => {
    const app = window.app;
    const l = app.project.layers.find(x => x.id === layerId);
    const sp = (l.powerSplitters || {}).manual || {};
    app._circuitTailCache = null;
    return {
        merge: sp.merge || [], split: sp.split || [],
        runIds: app.screenCircuits(l).map(c => c.runIds || null),
        sel: app._sweepSelection || null,
    };
}"""

SPLITTERS_ON_JS = """(ids) => {
    const app = window.app;
    const a = app.project.layers.find(x => x.id === ids.aId);
    a.powerSplitters = { enabled: true, maxWays: 3,
                         manual: { merge: [], split: [] } };
    app._circuitTailCache = null;
    app.updateLayers([a]);
    app.resetHistory('Dock Seed');
}"""

SPLITTERS_OFF_JS = """(ids) => {
    const app = window.app;
    const a = app.project.layers.find(x => x.id === ids.aId);
    a.powerSplitters = { enabled: false, maxWays: 3,
                         manual: { merge: [], split: [] } };
    app._circuitTailCache = null;
    app.updateLayers([a]);
    app._sweepSelection = null;
    app.resetHistory('Dock Seed');
}"""


def alt_sweep(page, sx, sy, ex, ey):
    """Alt held, press, drag past the threshold, release - the sweep. The
    hud's mid-flight text comes back for the pill assertions."""
    page.keyboard.down('Alt')
    page.mouse.move(sx, sy)
    page.mouse.down()
    page.mouse.move((sx + ex) / 2, (sy + ey) / 2, steps=5)
    page.mouse.move(ex, ey, steps=5)
    page.wait_for_timeout(150)
    hud = page.evaluate(
        "() => { const h = document.getElementById('power-sweep-hud');"
        " return h ? h.textContent : null; }")
    page.mouse.up()
    page.keyboard.up('Alt')
    page.wait_for_timeout(300)
    return hud


def test_batch_partition_math_and_labels(dock_page):
    """The engine's deal: consecutive groups of n, remainder re-dealt so
    nothing is orphaned - 16 @ 3fer is 3,3,3,3,2,2 (the last full group
    re-deals with the orphan as two 2fers); only '2fer them' over an odd
    count leaves a plain run."""
    page, ids = dock_page
    out = page.evaluate("""() => {
        const app = window.app;
        return {
            g18: app.batchNferGroups(18, 3), g16: app.batchNferGroups(16, 3),
            g8: app.batchNferGroups(8, 3), g7: app.batchNferGroups(7, 2),
            g5: app.batchNferGroups(5, 4), g5n3: app.batchNferGroups(5, 3),
            l18: app.batchNferLabel(18, 3), l16: app.batchNferLabel(16, 3),
            l7: app.batchNferLabel(7, 2), l5: app.batchNferLabel(5, 3),
        };
    }""")
    assert out['g18'] == [3, 3, 3, 3, 3, 3], out
    assert out['g16'] == [3, 3, 3, 3, 2, 2], out
    assert out['g8'] == [3, 3, 2], out
    assert out['g7'] == [2, 2, 2, 1], out
    assert out['g5'] == [3, 2], (
        f'a 5-run 4fer deal must not drop a run: {out}')
    assert out['g5n3'] == [3, 2], out
    assert out['l18'] == '6 × 3fer', out
    assert out['l16'] == '4 × 3fer + 2 × 2fer', out
    assert out['l7'] == '3 × 2fer + 1 plain', out
    assert out['l5'] == '1 × 3fer + 1 × 2fer', out


def test_alt_drag_sweeps_and_alt_click_stays_takeover(dock_page):
    """Alt+drag past 4px sweeps a contiguous selection with the counter
    pill riding the cursor; release keeps it lit, Esc drops it, and no
    history entry is ever written. A plain Alt+click (inside the threshold)
    stays the run takeover it always was."""
    page, ids = dock_page
    open_view(page, 'power')
    page.evaluate(RESET_POWER_JS, ids)
    page.wait_for_timeout(500)
    before = page.evaluate(HIST_LEN_JS)

    p0 = panel_point(page, ids['aId'], {'circuit': 0})
    p2 = panel_point(page, ids['aId'], {'circuit': 2})
    hud = alt_sweep(page, p0['x'], p0['y'], p2['x'], p2['y'])
    assert hud and 'circuit' in hud and ' A' in hud, (
        f'the counter pill did not ride the sweep: {hud!r}')
    out = page.evaluate("""(aId) => ({
        sel: window.app._sweepSelection,
        hud: !!document.getElementById('power-sweep-hud'),
    })""", ids['aId'])
    assert out['sel'] and out['sel']['layerId'] == ids['aId'], out
    assert len(out['sel']['nums']) == 3, (
        f'sweeping across three circuits must select all three: {out}')
    assert not out['hud'], 'the pill must leave with the release'
    assert page.evaluate(HIST_LEN_JS) == before, (
        'a sweep selection is view state, never a history entry')

    page.keyboard.press('Escape')
    page.wait_for_timeout(200)
    assert page.evaluate("() => window.app._sweepSelection") is None, (
        'Esc must drop the selection')

    # inside the threshold the press is still the takeover click
    page.keyboard.down('Alt')
    page.mouse.move(p0['x'], p0['y'])
    page.mouse.down()
    page.mouse.move(p0['x'] + 2, p0['y'] + 1)
    page.mouse.up()
    page.keyboard.up('Alt')
    page.wait_for_timeout(600)
    out = page.evaluate("""(aId) => {
        const app = window.app;
        const a = app.project.layers.find(x => x.id === aId);
        const num = app.screenCircuits(a)[0].num;
        return { over: app.isRunOverridden(a, 'power', num),
                 sel: app._sweepSelection };
    }""", ids['aId'])
    assert out['over'], (
        f'a click inside 4px must stay the takeover: {out}')
    assert not out['sel'], out
    page.evaluate("""() => {
        if (window.app.endOverrideEdit) window.app.endOverrideEdit();
        window.app.undo();
    }""")
    page.wait_for_timeout(700)
    page.evaluate(RESET_POWER_JS, ids)
    page.wait_for_timeout(300)


def test_sweep_right_click_deals_nfers_in_one_entry(dock_page):
    """Sweep three circuits (five packed runs), right-click: the menu
    offers the sizes with the group math, suppresses the single-run share
    item, and '3fer them' deals [1,2,3] + [4,5] as ONE '3fer Selection'
    entry. One undo heals the whole deal."""
    page, ids = dock_page
    open_view(page, 'power')
    page.evaluate(RESET_POWER_JS, ids)
    page.evaluate(SPLITTERS_ON_JS, ids)
    page.wait_for_timeout(600)
    before = page.evaluate(HIST_LEN_JS)

    p0 = panel_point(page, ids['aId'], {'circuit': 0})
    p2 = panel_point(page, ids['aId'], {'circuit': 2})
    alt_sweep(page, p0['x'], p0['y'], p2['x'], p2['y'])
    sel = page.evaluate("() => window.app._sweepSelection")
    assert sel and len(sel['nums']) == 3, sel

    p1 = panel_point(page, ids['aId'], {'circuit': 1})
    page.mouse.click(p1['x'], p1['y'], button='right')
    page.wait_for_timeout(400)
    items = page.evaluate(BATCH_ITEMS_JS)
    assert items['shown'], items
    assert items['n0'] and items['n0']['label'].startswith('2fer them ('), items
    assert items['n1'] and '3fer them (1 × 3fer + 1 × 2fer)' == \
        items['n1']['label'], items
    assert items['n1'] and not items['n1']['disabled'], items
    assert items['share'] is None, (
        f'the single-run share must stand down behind a sweep: {items}')
    # the packed 2fers count as existing gangs, so Un-share all is offered
    assert items['unshare'] and items['unshare']['label'] == 'Un-share all', items

    page.locator('#context-menu [data-action="hw-batch-n1"]').click()
    page.wait_for_timeout(800)
    out = page.evaluate(SPLITTER_STATE_JS, ids['aId'])
    assert out['merge'] == [[1, 2, 3], [4, 5]], (
        f'the 3fer deal must partition the five runs as 3+2: {out}')
    assert out['split'] == [], out
    assert [len(r) for r in out['runIds'] if r] == [3, 2], out
    assert out['sel'] is None, 'the commit must clear the selection'
    assert page.evaluate(HIST_JS, 1) == ['3fer Selection']
    assert page.evaluate(HIST_LEN_JS) == before + 1, (
        'the batch deal is not ONE history entry')

    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(800)
    out = page.evaluate(SPLITTER_STATE_JS, ids['aId'])
    assert out['merge'] == [], f'one undo did not heal the deal: {out}'
    page.evaluate(SPLITTERS_OFF_JS, ids)
    page.evaluate(RESET_POWER_JS, ids)
    page.wait_for_timeout(300)


def test_whole_wall_right_click_batches_and_keeps_single_run_items(dock_page):
    """No selection: right-click a run and the batch entries act on the
    whole screen ('3fer this screen'), beside the single-run share item,
    which keeps working unchanged."""
    page, ids = dock_page
    open_view(page, 'power')
    page.evaluate(RESET_POWER_JS, ids)
    page.evaluate(SPLITTERS_ON_JS, ids)
    page.wait_for_timeout(600)
    before = page.evaluate(HIST_LEN_JS)

    p0 = panel_point(page, ids['aId'], {'circuit': 0})
    page.mouse.click(p0['x'], p0['y'], button='right')
    page.wait_for_timeout(400)
    items = page.evaluate(BATCH_ITEMS_JS)
    assert items['shown'], items
    assert items['n1'] and items['n1']['label'].startswith('3fer this screen ('), items
    assert items['share'] is not None, (
        f'the single-run share must keep working with no sweep: {items}')

    page.locator('#context-menu [data-action="hw-batch-n1"]').click()
    page.wait_for_timeout(800)
    out = page.evaluate(SPLITTER_STATE_JS, ids['aId'])
    assert out['merge'] == [[1, 2, 3], [4, 5]], out
    assert page.evaluate(HIST_JS, 1) == ['3fer Screen']
    assert page.evaluate(HIST_LEN_JS) == before + 1

    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(800)
    page.evaluate(SPLITTERS_OFF_JS, ids)
    page.evaluate(RESET_POWER_JS, ids)
    page.wait_for_timeout(300)


def test_batch_entries_gated_off_with_reason(dock_page):
    """Splitters off and circuits auto: the batch entries stay ON the menu,
    disabled, with the sharing gate as their title - discoverable, never
    rule-breaking - and a click on one changes nothing."""
    page, ids = dock_page
    open_view(page, 'power')
    page.evaluate(RESET_POWER_JS, ids)
    page.evaluate(SPLITTERS_OFF_JS, ids)
    page.wait_for_timeout(500)
    before = page.evaluate(HIST_LEN_JS)

    p0 = panel_point(page, ids['aId'], {'circuit': 0})
    page.mouse.click(p0['x'], p0['y'], button='right')
    page.wait_for_timeout(400)
    items = page.evaluate(BATCH_ITEMS_JS)
    assert items['shown'], items
    assert items['n0'] and items['n0']['disabled'], items
    assert 'Sharing is off' in items['n0']['title'], items
    assert items['n1'] and items['n1']['disabled'], items
    # three plain runs: no 4fer to offer
    assert items['n2'] is None, items

    page.locator('#context-menu [data-action="hw-batch-n0"]').click()
    page.wait_for_timeout(500)
    out = page.evaluate(SPLITTER_STATE_JS, ids['aId'])
    assert out['merge'] == [], f'a disabled entry still dealt: {out}'
    assert page.evaluate(HIST_LEN_JS) == before, (
        'a disabled batch entry earned a history entry')
    close_menu(page)
    page.evaluate(RESET_POWER_JS, ids)
    page.wait_for_timeout(300)
