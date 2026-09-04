"""The ports and circuits render as tiles, and the tile is where they edit.

Both tile families live on the HARDWARE DOCK - the one place hardware
appears at all, now that the Signal and Power sidebars are retired. In
data view each port chip is the dense cell a glance can sweep - number,
resolved label, and who is on it - and clicking the chip (a press released
without movement; press-and-move is the drag) opens that port's own
controls IN the chip. In power view an OCCUPIED circuit chip wears the
identical shape: tail number, derived label, the holder screen, and a
click opens the circuit's label override in place. A free tail has no
circuit to label, so its chip stays a plain drag handle. One open editor
per box; Escape or the face closes it; the same fields, handlers and
history actions as the panel rows they replace, because the tiles are
presentation over the same state. The multis themselves are dock sections
now: a multi ON a distro gets a box whose header carries its name and
home-run length inline, layer-qualified, since the dock shows every
screen.

What is pinned here:
  * the chip states its number, its label and its state, and idle vs
    occupied read apart at a squint - in both families
  * a click opens exactly one editor; opening another closes the first;
    a free circuit chip's face opens nothing at all
  * edits through the open editor land under the SAME history actions the
    panel rows used, and walk back through undo
  * Escape closes and hands focus back to the face; the whole cycle works
    from the keyboard alone
  * the dock grid reflows to the window, open editor included - never a
    sideways scroll (the dock spans the canvas column; the sidebar width
    knobs died with the sidebars)
  * a focus restore into a closed chip opens the chip, and one aiming into
    a collapsed dock reopens the dock first (the fold rule, transposed)
  * the dock is the ONE port surface: the retired panels are gone from the
    DOM, no port field exists outside the dock, and the editor offers no
    set/place control - assignment stays the chip's own drag
  * a multi earns its dock section by landing on a distro, and its header
    fields write through the same setters and actions the soca rows did
  * collapsing the dock hides the chips; expanding hands them back as left

Run locally:
    python3 -m pytest tests/test_port_tiles.py -q --browser chromium
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


# One MX20 named SR: an all-in-one whose six ports give the grid something
# to be a grid about, with the shared screen sitting on its first port so
# occupied and free both exist to tell apart.
#
# The screen's NAME is normalized to Screen1 here rather than trusted: the
# shared server's screen is Screen1 only until some earlier module's Flask
# `client` fixture rebuilds the project (conftest's inter-suite hazard), so
# a module-order change used to swap TestScreen under these assertions. The
# occupant names on the chips come from the resolution, which reads the
# CLIENT layer names (_assignmentScreens), so an in-memory rename before
# the refresh is enough - and the module guard hands the server back as
# found either way.
SEED_JS = """async () => {
    const screen = window.app.project.layers.find(
        l => (l.type || 'screen') === 'screen');
    if (screen) {
        screen.name = 'Screen1';
        // The MX20 is COEX gear, and since the platform wall (2026-08-28)
        // a screen only lands on gear its Processing setting matches -
        // without the stamp the occupied tile this module tells apart
        // from the free ones would never be occupied.
        screen.processorType = 'novastar-coex-1g';
        await fetch(`/api/layer/${screen.id}`, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ processorType: 'novastar-coex-1g' }),
        });
    }
    const state = await (await fetch('/api/processors')).json();
    for (const p of (state.processors || [])) {
        await fetch(`/api/processors/${p.id}`, { method: 'DELETE' });
    }
    const add = await (await fetch('/api/processors', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ deviceId: 'novastar-mx20' }),
    })).json();
    const proc = add.resolved[0];
    const card = proc.slots.map(s => s.card).find(Boolean);
    await fetch(`/api/processors/${proc.id}/cards/${card.id}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: 'SR' }),
    });
    await window.app.refreshProcessors();
    window.app.saveState('Seed Tiles');
    return { procId: proc.id, cardId: card.id };
}"""

TILE_STATE_JS = """(tileId) => {
    const tile = document.querySelector(`[data-lrd-tile="${tileId}"]`);
    if (!tile) return null;
    const face = tile.querySelector(':scope > .lrd-tile-face');
    const body = tile.querySelector(':scope > .lrd-tile-body');
    const vis = (el) => !!el && el.getClientRects().length > 0;
    return {
        open: tile.classList.contains('lrd-tile-open'),
        occupied: tile.classList.contains('lrd-tile-occupied'),
        clash: tile.classList.contains('lrd-tile-clash'),
        facePainted: vis(face),
        faceText: face ? face.textContent.replace(/\\s+/g, ' ').trim() : null,
        ariaExpanded: face ? face.getAttribute('aria-expanded') : null,
        tabIndex: face ? face.tabIndex : null,
        bodyPainted: vis(body),
        bodyInDom: !!body && body.isConnected,
        background: getComputedStyle(tile).backgroundColor,
    };
}"""

CLICK_FACE_JS = """(tileId) => {
    const tile = document.querySelector(`[data-lrd-tile="${tileId}"]`);
    if (!tile) return false;
    tile.querySelector(':scope > .lrd-tile-face').click();
    return true;
}"""


@pytest.fixture(scope="module")
def panel_page(e2e_server, pw_browser):
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)  # socket connect + app init
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(400)
    yield pg
    context.close()


def seed(panel_page):
    ids = panel_page.evaluate(SEED_JS)
    panel_page.wait_for_timeout(600)
    return ids


def tile_state(page, tile_id):
    return page.evaluate(TILE_STATE_JS, tile_id)


# ── the tile states number, label and state ───────────────────────────────

def test_a_tile_states_its_number_label_and_occupant(panel_page):
    """The face is the glance line: port number, the label the assignment
    resolved (never re-derived), and who sits on it - the same states the
    editor prints, worn as the tile's ground."""
    ids = seed(panel_page)
    occupied = tile_state(panel_page, f"port-{ids['cardId']}-1")
    free = tile_state(panel_page, f"port-{ids['cardId']}-6")
    assert occupied and free, 'the card built no tiles'
    assert occupied['faceText'].startswith('1 SR-1'), (
        f'the face does not lead with number and resolved label: {occupied}')
    assert 'Screen1' in occupied['faceText'], (
        f'the occupant is not on the face: {occupied}')
    assert free['faceText'].startswith('6 SR-6'), free
    assert 'free' in free['faceText'], (
        f'an idle port does not say so: {free}')


def test_idle_and_occupied_read_apart_at_a_squint(panel_page):
    """Not just different words: the occupied tile is the lit one, so the
    difference survives being too small to read."""
    ids = seed(panel_page)
    occupied = tile_state(panel_page, f"port-{ids['cardId']}-1")
    free = tile_state(panel_page, f"port-{ids['cardId']}-6")
    assert occupied['occupied'] and not free['occupied'], (occupied, free)
    assert occupied['background'] != free['background'], (
        f'idle and occupied tiles paint the same ground: '
        f"{occupied['background']} vs {free['background']}")


def test_a_contested_port_wears_the_clash_state(panel_page):
    """Two screens on one port is a state the app supports and reports; the
    tile carries the same red ground the issue rows use."""
    ids = seed(panel_page)
    snapshot = panel_page.evaluate(
        "async () => await (await fetch('/api/project')).json()")
    try:
        out = panel_page.evaluate("""async (args) => {
            const app = window.app;
            // a second screen, pinned onto Screen1's port with the same
            // confirmed placement a person would send - the clash the
            // occupancy already knows how to report
            await fetch('/api/layer/add', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: 'WallB', columns: 2, rows: 2,
                                       cabinet_width: 128,
                                       cabinet_height: 128 }),
            });
            app.project = await (await fetch('/api/project')).json();
            await app.refreshPortAssignment();
            // Screen1's port is auto-numbered and would politely re-pack out
            // of the way; a clash needs it HELD where it is first.
            const screen1 = app.project.layers.find(l => l.name === 'Screen1');
            await app._assignmentRequest('/api/port-assignments/pin', 'POST',
                                         { layerId: String(screen1.id),
                                           index: 0, cardId: args.cardId,
                                           port: 1 });
            const wallB = app.project.layers.find(l => l.name === 'WallB');
            await app._placePort({ layerId: String(wallB.id), index: 0,
                                   cardId: args.cardId, port: 1 }, true);
            await new Promise(r => setTimeout(r, 300));
            const tile = document.querySelector(
                `[data-lrd-tile="port-${args.cardId}-1"]`);
            const face = tile.querySelector(':scope > .lrd-tile-face');
            return {
                clash: tile.classList.contains('lrd-tile-clash'),
                faceText: face.textContent.replace(/\\s+/g, ' ').trim(),
            };
        }""", {'cardId': ids['cardId']})
        assert out['clash'], (
            f'a contested port does not wear the clash state: {out}')
        assert 'clash' in out['faceText'], out
    finally:
        # WallB and its pin would haunt every later seed's occupancy
        panel_page.evaluate("""async (project) => {
            await fetch('/api/project', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(project),
            });
            window.app.project = await (await fetch('/api/project')).json();
            await window.app.refreshPortAssignment();
        }""", snapshot)
        panel_page.wait_for_timeout(400)


# ── click opens one editor, in place ──────────────────────────────────────

def test_a_click_opens_the_editor_in_the_tile_and_only_one_at_a_time(panel_page):
    ids = seed(panel_page)
    t1 = f"port-{ids['cardId']}-1"
    t2 = f"port-{ids['cardId']}-2"

    s = tile_state(panel_page, t1)
    assert not s['open'] and not s['bodyPainted'], (
        f'a tile arrived with its editor already open: {s}')
    assert s['bodyInDom'], (
        'a closed tile detached its editor - the focus keys must keep '
        'resolving into it')

    assert panel_page.evaluate(CLICK_FACE_JS, t1)
    s = tile_state(panel_page, t1)
    assert s['open'] and s['bodyPainted'], f'the click did not open the editor: {s}'
    assert s['ariaExpanded'] == 'true', s

    # opening another closes the first - one open editor per box
    assert panel_page.evaluate(CLICK_FACE_JS, t2)
    s1 = tile_state(panel_page, t1)
    s2 = tile_state(panel_page, t2)
    assert s2['open'] and s2['bodyPainted'], s2
    assert not s1['open'] and not s1['bodyPainted'], (
        f'two editors open in one box: {s1}')

    # the face closes its own tile
    assert panel_page.evaluate(CLICK_FACE_JS, t2)
    s2 = tile_state(panel_page, t2)
    assert not s2['open'] and s2['ariaExpanded'] == 'false', s2


def test_the_open_editor_holds_the_naming_controls_and_no_assigner(panel_page):
    """Same naming fields, same keys: Name, Return and the occupancy detail.
    The set/place control is deliberately GONE - assignment is the hardware
    dock's drag now, and a second control would be a second set of rules."""
    ids = seed(panel_page)
    assert panel_page.evaluate(CLICK_FACE_JS, f"port-{ids['cardId']}-1")
    out = panel_page.evaluate("""(args) => {
        const tile = document.querySelector(
            `[data-lrd-tile="port-${args.cardId}-1"]`);
        const vis = (el) => !!el && el.getClientRects().length > 0;
        const field = (kind) => tile.querySelector(
            `[data-lrd-field="processor-port-${kind}-${args.cardId}-1"]`);
        const setBtn = [...tile.querySelectorAll('button')]
            .find(b => b.textContent === 'set' || b.textContent === 'close');
        return {
            name: vis(field('name')),
            ret: vis(field('return')),
            set: !!setBtn,
            picker: !!document.querySelector(
                `[data-lrd-field^="processor-port-assign-"]`),
            namePlaceholder: field('name') ? field('name').placeholder : null,
            retPlaceholder: field('return') ? field('return').placeholder : null,
        };
    }""", {'cardId': ids['cardId']})
    assert out['name'] and out['ret'], (
        f'the open editor is missing the naming fields: {out}')
    assert not out['set'] and not out['picker'], (
        f'a stripped assignment control is still around: {out}')
    assert out['namePlaceholder'] == 'SR-1', out
    # SR has no leading P to swap for an R, so its return keeps the R after
    # it - the half of the rule a drawing already issued was printed with.
    assert out['retPlaceholder'] == 'SR-1R', out


RENAME_CARD_JS = """async (args) => {
    await fetch(`/api/processors/${args.procId}/cards/${args.cardId}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: args.name }),
    });
    await window.app.refreshProcessors();
}"""


def test_a_card_named_p1_shows_r1_everywhere_the_return_is_advertised(panel_page):
    """P is primary and R is redundant, so P1-1 goes out and R1-1 comes
    back - never P1-1R. Every surface that states the return for an untyped
    port is read after the rename: the port chip's Return placeholder (the
    server's derivation), the card's Return template placeholder (the
    client's copy, rendered off the real name - behind the card's own gear
    since the Processors panel retired), and what the drawing prints,
    asked of getPortLabelText the way the canvas asks. The per-port label
    list and its note died with the Signal sidebar, so the drawing's answer
    is pinned at the API the canvas reads instead of a retired row's title.
    """
    ids = seed(panel_page)
    panel_page.evaluate(RENAME_CARD_JS, dict(ids, name='P1'))
    panel_page.wait_for_timeout(600)
    assert panel_page.evaluate(CLICK_FACE_JS, f"port-{ids['cardId']}-1")
    # the template fields live behind the card's ⚙ popover now
    panel_page.locator(f'[data-hwpop="card-{ids["cardId"]}"]').click()
    panel_page.wait_for_timeout(200)
    try:
        out = panel_page.evaluate("""(args) => {
            const tile = document.querySelector(
                `[data-lrd-tile="port-${args.cardId}-1"]`);
            const field = (kind) => tile.querySelector(
                `[data-lrd-field="processor-port-${kind}-${args.cardId}-1"]`);
            const template = document.querySelector(
                `#hw-gear-popover [data-lrd-field=`
                + `"processor-card-return-template-${args.cardId}"]`);
            const app = window.app;
            const screen = app.project.layers.find(
                l => (l.type || 'screen') === 'screen');
            return {
                namePlaceholder: field('name') ? field('name').placeholder : null,
                retPlaceholder: field('return') ? field('return').placeholder : null,
                templatePlaceholder: template ? template.placeholder : null,
                onProcessor: app.getProcessorPortLabel(screen, 1),
                printsPrimary: app.getPortLabelText(screen, 1),
                printsReturn: app.getPortLabelText(screen, 1, 'return'),
            };
        }""", {'cardId': ids['cardId']})
        assert out['namePlaceholder'] == 'P1-1', out
        assert out['retPlaceholder'] == 'R1-1', (
            f'the port tile still advertises the old <primary>R return: {out}')
        assert out['templatePlaceholder'] == 'R1-#', (
            f'the Return template placeholder still advertises {{name}}-#R: '
            f'{out}')
        # The seeded screen sits on port 1, so the processor owns its label
        # and the drawing prints the derived return.
        assert out['onProcessor'] == 'P1-1', out
        assert out['printsPrimary'] == 'P1-1', out
        assert out['printsReturn'] == 'R1-1', (
            f'the drawing does not print R1-1 for the return: {out}')
    finally:
        panel_page.keyboard.press('Escape')   # close the gear popover
        panel_page.wait_for_timeout(100)


def test_edits_through_the_open_editor_round_trip_with_the_same_actions(panel_page):
    """Typed through the visible field the way a user types: the rename and
    the return land on the server under the actions the rows always earned,
    and undo walks the rename back."""
    ids = seed(panel_page)
    assert panel_page.evaluate(CLICK_FACE_JS, f"port-{ids['cardId']}-1")

    def commit(kind, value):
        field = panel_page.locator(
            f'[data-lrd-field="processor-port-{kind}-{ids["cardId"]}-1"]')
        field.click()
        field.fill('')
        panel_page.keyboard.type(value)
        panel_page.keyboard.press('Tab')
        panel_page.wait_for_timeout(800)

    def stored():
        state = panel_page.evaluate(
            "async () => await (await fetch('/api/processors')).json()")
        card = next(s['card'] for s in state['processors'][0]['slots']
                    if s.get('card'))
        return ((card.get('portNames') or {}).get('1'),
                (card.get('returnPortNames') or {}).get('1'))

    commit('name', 'HL')
    commit('return', 'BU-1')
    assert stored() == ('HL', 'BU-1'), 'the edits never reached the server'
    actions = panel_page.evaluate(
        "() => window.app.history.map(h => h.action).slice(-2)")
    assert actions == ['Rename Processor Port', 'Rename Processor Port Return'], (
        f'the tile editor changed the history actions: {actions}')

    panel_page.evaluate("() => window.app.undo()")
    panel_page.wait_for_timeout(1000)
    assert stored() == ('HL', None), 'undo did not walk the return back'
    panel_page.evaluate("() => window.app.undo()")
    panel_page.wait_for_timeout(1000)
    assert stored() == (None, None), 'undo did not walk the rename back'
    panel_page.evaluate("() => window.app.redo()")
    panel_page.wait_for_timeout(1000)
    assert stored() == ('HL', None), 'redo did not bring the rename back'

    # the tile the user was standing in is still the open one after all
    # those wholesale rebuilds
    assert tile_state(panel_page, f"port-{ids['cardId']}-1")['open'], (
        'the rebuilds closed the tile mid-edit')


# ── Escape, and the keyboard path ─────────────────────────────────────────

def test_escape_closes_the_editor_and_returns_focus_to_the_face(panel_page):
    ids = seed(panel_page)
    tid = f"port-{ids['cardId']}-1"
    assert panel_page.evaluate(CLICK_FACE_JS, tid)
    panel_page.locator(
        f'[data-lrd-field="processor-port-name-{ids["cardId"]}-1"]').click()
    panel_page.keyboard.press('Escape')
    panel_page.wait_for_timeout(100)
    s = tile_state(panel_page, tid)
    assert not s['open'], f'Escape did not close the tile: {s}'
    focused = panel_page.evaluate("""(tileId) => {
        const tile = document.querySelector(`[data-lrd-tile="${tileId}"]`);
        return document.activeElement
            === tile.querySelector(':scope > .lrd-tile-face');
    }""", tid)
    assert focused, 'closing did not hand focus back to the face'


def test_the_whole_cycle_works_from_the_keyboard(panel_page):
    """The rows were keyboard-reachable through their inputs; the tile keeps
    that access: the face is a tab stop, Enter opens, Tab walks into the
    editor's fields, Escape closes back onto the face."""
    ids = seed(panel_page)
    tid = f"port-{ids['cardId']}-3"
    s = tile_state(panel_page, tid)
    assert s['tabIndex'] == 0, f'the face is not a tab stop: {s}'

    panel_page.evaluate("""(tileId) => {
        document.querySelector(`[data-lrd-tile="${tileId}"]`)
            .querySelector(':scope > .lrd-tile-face').focus();
    }""", tid)
    panel_page.keyboard.press('Enter')
    panel_page.wait_for_timeout(100)
    assert tile_state(panel_page, tid)['open'], 'Enter did not open the tile'

    panel_page.keyboard.press('Tab')
    key = panel_page.evaluate(
        "() => document.activeElement.dataset.lrdField || null")
    assert key == f'processor-port-name-{ids["cardId"]}-3', (
        f'Tab from the face did not walk into the editor: {key}')
    panel_page.keyboard.press('Tab')
    key = panel_page.evaluate(
        "() => document.activeElement.dataset.lrdField || null")
    assert key == f'processor-port-return-{ids["cardId"]}-3', (
        f'Tab did not walk to the next field of the editor: {key}')

    panel_page.keyboard.press('Escape')
    panel_page.wait_for_timeout(100)
    assert not tile_state(panel_page, tid)['open'], (
        'Escape from a field did not close the tile')
    face_focused = panel_page.evaluate("""(tileId) => {
        const tile = document.querySelector(`[data-lrd-tile="${tileId}"]`);
        return document.activeElement
            === tile.querySelector(':scope > .lrd-tile-face');
    }""", tid)
    assert face_focused, 'the keyboard close did not land back on the face'


# ── the reflow ────────────────────────────────────────────────────────────
#
# The dock spans the canvas column, so its clamp is the WINDOW: the tray is
# wide on a wide monitor and narrow on the default one, and the grid must
# reflow its columns to whatever width it has rather than scroll sideways.
# (The retired sidebars' width knobs - --lrd-data-w, --lrd-power-w - died
# with the sidebars; the window is the only width driver left.) The
# comparison grows from the fixture's 1280 rather than shrinking below it,
# because the canvas element's backing store pins the column's min-content
# at its load-time size - a window smaller than that clips the layout
# instead of narrowing the tray, which is the app's standing behaviour and
# not this feature's to change.

GRID_FIT_JS = """() => {
    const body = document.getElementById('hardware-dock-body');
    const grids = [...body.querySelectorAll('.lrd-tile-grid')];
    const limit = body.getBoundingClientRect().right;
    const strays = [];
    body.querySelectorAll('.lrd-tile, .lrd-tile *').forEach(el => {
        const r = el.getBoundingClientRect();
        if (r.width === 0 && r.height === 0) return;
        if (r.right > limit + 0.5) {
            strays.push({ tag: el.tagName,
                          key: el.getAttribute('data-lrd-field')
                              || el.className || null,
                          over: Math.round(r.right - limit) });
        }
    });
    const grid = grids[0];
    const cols = grid ? getComputedStyle(grid).gridTemplateColumns
        .split(' ').length : 0;
    return {
        clipped: body.scrollWidth > body.clientWidth,
        gridClipped: grids.some(g => g.scrollWidth > g.clientWidth),
        columns: cols,
        strays,
    };
}"""


@pytest.mark.parametrize('width', [1280, 1700])
def test_the_tile_grid_fits_closed_and_open(panel_page, width):
    """At the default window and at a wide one: the grid reflows, no chip
    clips past the tray, and the open editor wraps inside the chip the way
    its captioned fields are built to wrap - never a sideways scroll."""
    ids = seed(panel_page)
    panel_page.set_viewport_size({'width': width, 'height': 720})
    panel_page.wait_for_timeout(400)
    try:
        closed = panel_page.evaluate(GRID_FIT_JS)
        assert not closed['clipped'] and not closed['gridClipped'], closed
        assert not closed['strays'], (
            f'chips hang past the tray at {width}px: {closed["strays"]}')
        assert closed['columns'] >= 1, closed

        assert panel_page.evaluate(CLICK_FACE_JS, f"port-{ids['cardId']}-1")
        panel_page.wait_for_timeout(100)
        opened = panel_page.evaluate(GRID_FIT_JS)
        assert not opened['clipped'] and not opened['gridClipped'], opened
        assert not opened['strays'], (
            f'the open editor hangs past the tray at {width}px: '
            f'{opened["strays"]}')
    finally:
        panel_page.evaluate(CLICK_FACE_JS, f"port-{ids['cardId']}-1")
        panel_page.set_viewport_size({'width': 1280, 'height': 720})
        panel_page.wait_for_timeout(300)


def test_a_wider_tray_reflows_to_more_columns(panel_page):
    seed(panel_page)
    narrow = panel_page.evaluate(GRID_FIT_JS)
    panel_page.set_viewport_size({'width': 1700, 'height': 720})
    panel_page.wait_for_timeout(500)
    try:
        wide = panel_page.evaluate(GRID_FIT_JS)
        assert wide['columns'] > narrow['columns'], (
            f'the grid did not reflow: {narrow["columns"]} columns at 1280, '
            f'{wide["columns"]} at 1700')
        assert not wide['clipped'] and not wide['strays'], wide
    finally:
        panel_page.set_viewport_size({'width': 1280, 'height': 720})
        panel_page.wait_for_timeout(300)


# ── focus restore, set/place, and the fold ────────────────────────────────

def test_a_focus_restore_into_a_closed_tile_opens_it(panel_page):
    """The fold rule one register down: a field the app is putting the caret
    back into must not be display:none, so the restore opens the chip - and
    records the opening, or the next rebuild would close the editor around
    the caret."""
    ids = seed(panel_page)
    tid = f"port-{ids['cardId']}-1"
    assert panel_page.evaluate(CLICK_FACE_JS, tid)
    out = panel_page.evaluate("""async (args) => {
        const app = window.app;
        const el = document.querySelector(
            `[data-lrd-field="processor-port-name-${args.cardId}-1"]`);
        el.focus();
        app._preserveEditorFocus();          // captures key + schedules restore
        const tile = document.querySelector(
            `[data-lrd-tile="port-${args.cardId}-1"]`);
        app._setTileOpen(tile, false);       // close before the restore lands
        if (document.activeElement) document.activeElement.blur();
        await new Promise(r => setTimeout(r, 20));
        const reopened = tile.classList.contains('lrd-tile-open');
        const focusedBack = document.activeElement === el;
        // and the opening is recorded, so a rebuild keeps it
        app.renderHardwareDock();
        const rebuilt = document.querySelector(
            `[data-lrd-tile="port-${args.cardId}-1"]`);
        return { reopened, focusedBack,
                 survives: rebuilt.classList.contains('lrd-tile-open') };
    }""", {'cardId': ids['cardId']})
    assert out['reopened'], f'the restore left the chip closed: {out}'
    assert out['focusedBack'], f'focus was not restored into the field: {out}'
    assert out['survives'], f'the auto-opening did not survive a rebuild: {out}'


def test_a_focus_restore_into_a_collapsed_dock_reopens_the_dock(panel_page):
    """The same rule at the tray's own register: the dock folds by the
    SIDEBAR machinery, so a restore aiming into a collapsed tray reopens it
    through its own toggle - persisting the state, the way the section
    auto-expand persists its - then opens the chip and lands the caret."""
    ids = seed(panel_page)
    tid = f"port-{ids['cardId']}-1"
    assert panel_page.evaluate(CLICK_FACE_JS, tid)
    out = panel_page.evaluate("""async (args) => {
        const app = window.app;
        const el = document.querySelector(
            `[data-lrd-field="processor-port-name-${args.cardId}-1"]`);
        el.focus();
        app._preserveEditorFocus();          // captures key + schedules restore
        const tile = document.querySelector(
            `[data-lrd-tile="port-${args.cardId}-1"]`);
        app._setTileOpen(tile, false);       // close before the restore lands
        // collapse the tray through its own toggle, the way a user would
        document.getElementById('hardware-dock-toggle').click();
        if (document.activeElement) document.activeElement.blur();
        await new Promise(r => setTimeout(r, 50));
        const dock = document.getElementById('hardware-dock');
        return {
            dockReopened: !dock.classList.contains('collapsed'),
            stored: localStorage.getItem('ledRasterSidebarCollapsed_dock'),
            tileReopened: tile.classList.contains('lrd-tile-open'),
            focusedBack: document.activeElement === el,
        };
    }""", {'cardId': ids['cardId']})
    assert out['dockReopened'], f'the restore left the dock collapsed: {out}'
    assert out['stored'] == '0', f'the reopening did not persist: {out}'
    assert out['tileReopened'], f'the restore left the chip closed: {out}'
    assert out['focusedBack'], f'focus was not restored into the field: {out}'


def test_the_dock_is_the_one_port_surface(panel_page):
    """The Signal sidebar and its Processors panel are gone from the DOM
    entirely - the dock is the one place ports appear, editors included -
    and no assignment field of the old set/place flow survives anywhere.
    The dock chips stay focusable, one per port."""
    ids = seed(panel_page)
    out = panel_page.evaluate("""(args) => {
        const dockTile = document.querySelector(
            `[data-hwdock="port-${args.cardId}-5"]`);
        return {
            // the retired homes must not linger as empty husks
            retiredIds: ['data-sidebar', 'data-sidebar-toggle',
                         'power-sidebar', 'power-sidebar-toggle',
                         'processor-list', 'port-label-list',
                         'power-soca-runs', 'power-label-list']
                .filter(id => document.getElementById(id)),
            pickerAnywhere: !!document.querySelector(
                '[data-lrd-field^="processor-port-assign-"]'),
            setButtons: [...document.querySelectorAll('button')]
                .filter(b => b.textContent === 'set').length,
            portFieldsOutsideDock: [...document.querySelectorAll(
                '[data-lrd-field^="processor-port-"]')]
                .filter(el => !el.closest('#hardware-dock')).length,
            dockTile: !!dockTile,
            dockTileFocusable: dockTile ? dockTile.tabIndex === 0 : null,
            dockTiles: document.querySelectorAll(
                `#hardware-dock [data-hwdock^="port-${args.cardId}-"]`).length,
            // the one-id rule: each port field key resolves exactly once,
            // and it resolves into the dock
            fieldCount: document.querySelectorAll(
                `[data-lrd-field="processor-port-name-${args.cardId}-1"]`)
                .length,
            fieldInDock: !!document.querySelector(
                `#hardware-dock [data-lrd-field="processor-port-name-`
                + `${args.cardId}-1"]`),
        };
    }""", {'cardId': ids['cardId']})
    assert out['retiredIds'] == [], (
        f'a retired panel still stands in the DOM: {out}')
    assert not out['pickerAnywhere'], f'the old chooser survives: {out}'
    assert out['setButtons'] == 0, f'a set button survives: {out}'
    assert out['portFieldsOutsideDock'] == 0, (
        f'port fields survive outside the dock: {out}')
    assert out['dockTile'], f'the dock has no chip for port 5: {out}'
    assert out['dockTileFocusable'], (
        f'the dock chip fell out of the tab ring: {out}')
    # the MX20's six ports all appear, once each, editors in the dock
    assert out['dockTiles'] == 6, out
    assert out['fieldCount'] == 1 and out['fieldInDock'], (
        f'the one-id rule broke - a port field exists twice or outside '
        f'the dock: {out}')


def test_a_collapsed_dock_hides_its_chips_and_hands_them_back(panel_page):
    """Fold interplay at the tray's register: collapsing the dock hides
    every chip, expanding restores them, and the open chip rides the
    tray's wholesale rebuild by id - the same way the fold state itself
    does."""
    ids = seed(panel_page)
    tid = f"port-{ids['cardId']}-1"
    assert panel_page.evaluate(CLICK_FACE_JS, tid)
    assert tile_state(panel_page, tid)['open']

    panel_page.locator('#hardware-dock-toggle').click()
    panel_page.wait_for_timeout(500)
    # The collapse folds the tray to nothing and clips its content
    # (height 0 + overflow hidden - the sidebar collapse transposed), so
    # the proof is the tray's height, not display:none on each chip.
    folded = panel_page.evaluate("""() => {
        const dock = document.getElementById('hardware-dock');
        return {
            collapsed: dock.classList.contains('collapsed'),
            dockH: dock.getBoundingClientRect().height,
        };
    }""")
    assert folded['collapsed'] and folded['dockH'] < 2, (
        f'the toggle did not fold the tray away: {folded}')
    assert tile_state(panel_page, tid)['bodyInDom'], (
        'the collapse detached the chips')

    panel_page.locator('#hardware-dock-toggle').click()
    panel_page.wait_for_timeout(500)
    s = tile_state(panel_page, tid)
    assert s['facePainted'], 'expanding did not hand the chips back'
    assert s['open'] and s['bodyPainted'], (
        f'expanding lost the open chip: {s}')

    # a bare wholesale rebuild: the open chip comes back by id
    panel_page.evaluate("() => window.app.renderHardwareDock()")
    panel_page.wait_for_timeout(100)
    s = tile_state(panel_page, tid)
    assert s['open'] and s['bodyPainted'], (
        f'the rebuild closed the open chip: {s}')


# ── the circuits wear the same shape, on the dock ─────────────────────────
#
# The soca tiles died with the Power sidebar. What replaced them is TWO
# dock surfaces: the multi's own section (header carries the name and
# home-run length inline, layer-qualified - the dock shows every screen)
# and, inside it, six circuit chips in the port-chip register, where an
# OCCUPIED tail is a tile whose editor holds the circuit's label override.
# A multi has a dock section only ON a distro, so the seed assigns one.

POWER_SEED_JS = """() => {
    const app = window.app;
    const layer = app.project.layers.find(
        l => (l.type || 'screen') === 'screen');
    // Same name normalization as SEED_JS, for the same module-order reason:
    // the chips print the HOLDER's layer name straight off l.name.
    layer.name = 'Screen1';
    app.selectLayer(layer);
    // In-memory power shape: enough watts against the circuit for the 4x3
    // screen to need TWO circuits, so multi 1 holds two tails and four
    // stay free - occupied and free chips both exist to tell apart.
    layer.panelWatts = 400;
    layer.powerVoltage = 208;
    layer.powerAmperage = 20;
    const d = app.getDistros()[0] || app.addDistro();
    // every test starts from closed chips and derived names - which chip
    // is open is module state on the app, and a previous test's open
    // editor or hand-typed name must not leak in
    app._openTiles = {};
    app._circuitTailCache = null;
    let plan = app.getSocaPlan(layer);
    if (!plan.length) return { socas: 0 };
    const idx = plan[0].soca;
    if (layer.powerSocaNames) delete layer.powerSocaNames[idx];
    if (layer.powerSocaLengths) delete layer.powerSocaLengths[idx];
    // a multi earns its dock section by sitting ON a distro
    if ((layer.powerSocaDistro || {})[idx] !== d.id) {
        app.setSocaDistro(layer, idx, d.id);
    }
    app._restateNaming();
    app.renderHardwareDock();
    plan = app.getSocaPlan(layer);
    const s = plan.find(x => x.soca === idx);
    return {
        layerId: layer.id, distroId: d.id, socaIdx: s.soca,
        number: s.number, name: s.name, socas: plan.length,
        legs: s.legs.map(g => ({ tail: g.leg, circuit: g.circuit,
                                 label: g.label })),
    };
}"""


@pytest.fixture()
def power_page(panel_page):
    panel_page.locator('[data-mode="power"]').click()
    panel_page.wait_for_timeout(400)
    seeded = panel_page.evaluate(POWER_SEED_JS)
    panel_page.wait_for_timeout(400)
    assert seeded['socas'] > 0, f'the plan built no multis: {seeded}'
    assert len(seeded['legs']) >= 2, (
        f'the seed shape must occupy at least two tails so one-per-box '
        f'has two chips to play against: {seeded}')
    yield panel_page, seeded
    panel_page.locator('[data-mode="data-flow"]').click()
    panel_page.wait_for_timeout(300)


def chip_id(seeded, i):
    leg = seeded['legs'][i]
    return f"ptail-{seeded['distroId']}-{seeded['number']}-{leg['tail']}"


def test_a_multi_earns_its_dock_section_by_landing_on_a_distro(power_page):
    """No distro, no box: an unassigned multi has no dock section, hence no
    name or length editor - the assignment (the dock's drop; its setter
    here) is what builds the box, under the action the drop has always
    earned."""
    page, seeded = power_page
    key = f"power-soca-name-{seeded['layerId']}-{seeded['socaIdx']}"
    out = page.evaluate("""(a) => {
        const app = window.app;
        const layer = app.project.layers.find(l => l.id === a.layerId);
        app.setSocaDistro(layer, a.socaIdx, null);
        app.renderHardwareDock();
        const gone = !document.querySelector(`[data-lrd-field="${a.key}"]`);
        app.setSocaDistro(layer, a.socaIdx, a.distroId);
        app.renderHardwareDock();
        return {
            gone,
            back: !!document.querySelector(
                `#hardware-dock [data-lrd-field="${a.key}"]`),
            action: app.history[app.history.length - 1].action,
        };
    }""", {'layerId': seeded['layerId'], 'socaIdx': seeded['socaIdx'],
           'distroId': seeded['distroId'], 'key': key})
    page.wait_for_timeout(400)
    assert out['gone'], (
        'an unassigned multi still has a name editor somewhere - the dock '
        'section must exist only on a distro')
    assert out['back'], 'assigning did not build the dock section back'
    assert out['action'] == 'Assign Multi Distro', out


def test_the_multi_header_carries_the_inline_name_and_length(power_page):
    """The retired soca tile's fields, re-hosted onto the multi's own dock
    header with layer-qualified keys: the name (placeholder = the derived
    name, so an unnamed box still reads as its identity) and the home-run
    length. The header also states the box's data - tails and amps in the
    detail, used-of-six in the glance - while a FREE spare keeps its static
    label. Assigning stays the drag: the old Distro and No. selects exist
    nowhere. The per-screen knobs live in the left sidebar's Power
    Settings, never in the dock."""
    page, seeded = power_page
    out = page.evaluate("""(a) => {
        const head = document.querySelector(
            `#hardware-dock [data-hwdock="slot-${a.distroId}-${a.number}"]`);
        if (!head) return null;
        const vis = (el) => !!el && el.getClientRects().length > 0;
        const name = head.querySelector(
            `[data-lrd-field="power-soca-name-${a.layerId}-${a.socaIdx}"]`);
        const len = head.querySelector(
            `[data-lrd-field="power-soca-length-${a.layerId}-${a.socaIdx}"]`);
        const info = head.querySelector('.hw-dock-unit-info');
        const use = head.querySelector('.hw-dock-unit-use');
        const spare = document.querySelector(
            `#hardware-dock [data-hwdock=`
            + `"slot-${a.distroId}-${a.number + 1}"]`);
        return {
            name: vis(name), nameClass: name ? name.className : null,
            namePlaceholder: name ? name.placeholder : null,
            length: vis(len),
            lenClass: len ? len.className : null,
            lenPlaceholder: len ? len.placeholder : null,
            staticLabel: !!head.querySelector('.hw-dock-unit-name'),
            detail: info ? info.textContent : null,
            glance: use ? use.textContent : null,
            spareDetail: spare ? spare.querySelector(
                '.hw-dock-unit-info').textContent : null,
            spareStatic: spare ? !!spare.querySelector(
                '.hw-dock-unit-name') : null,
            spareFields: spare ? spare.querySelectorAll('input').length : null,
            // the retired tile selects must exist nowhere
            oldSelects: document.querySelectorAll(
                '.power-soca-distro, .power-soca-number, .power-soca-row')
                .length,
        };
    }""", {'layerId': seeded['layerId'], 'socaIdx': seeded['socaIdx'],
           'distroId': seeded['distroId'], 'number': seeded['number']})
    assert out, 'multi 1 built no dock section'
    assert out['name'] and out['length'], (
        f'the header is missing the inline fields: {out}')
    assert out['namePlaceholder'] == seeded['name'], (
        f'the name placeholder is not the derived multi name: {out}')
    assert out['lenPlaceholder'] == '100ft', out
    assert 'hw-dock-name-len' in (out['lenClass'] or ''), out
    assert not out['staticLabel'], (
        f'an occupied multi still draws a static label beside its name '
        f'field: {out}')
    assert re.match(r'^\d+ circuits? · [\d.]+ A$', out['detail'] or ''), (
        f'the detail is not "<legs> circuits · <amps> A": {out}')
    assert out['glance'] == f"{len(seeded['legs'])}/6", out
    # the demand-driven spare after the occupied box: static label, free
    assert out['spareDetail'] == 'free' and out['spareStatic'], out
    assert out['spareFields'] == 0, (
        f'a free multi grew editors before anything sits on it: {out}')
    assert out['oldSelects'] == 0, (
        f'the retired soca tile controls survive: {out}')

    # the per-screen knobs stay per-screen, in the left sidebar
    for panel_ctrl in ('#power-breakout-type', '#show-soca-brackets'):
        assert page.evaluate(
            """(sel) => {
                const el = document.querySelector(sel);
                return !!el && !el.closest('#hardware-dock')
                    && el.getClientRects().length > 0;
            }""", panel_ctrl), (
            f'{panel_ctrl} moved into the dock or went unpainted')


def test_multi_edits_round_trip_with_the_same_actions(power_page):
    """Name and length through the header's inline fields: same setters,
    same history actions as the retired soca rows - and the length walks
    back through undo."""
    page, seeded = power_page
    name_key = f"power-soca-name-{seeded['layerId']}-{seeded['socaIdx']}"
    len_key = f"power-soca-length-{seeded['layerId']}-{seeded['socaIdx']}"

    name = page.locator(f'[data-lrd-field="{name_key}"]')
    name.click()
    name.fill('')
    page.keyboard.type('HOUSE')
    page.keyboard.press('Tab')
    page.wait_for_timeout(600)
    assert page.evaluate(
        "() => window.app.history[window.app.history.length - 1].action") \
        == 'Rename Multi'
    assert page.evaluate(
        """(a) => (window.app.project.layers.find(
            l => l.id === a.layerId).powerSocaNames || {})[a.socaIdx]""",
        seeded) == 'HOUSE'

    length = page.locator(f'[data-lrd-field="{len_key}"]')
    length.click()
    length.fill('')
    page.keyboard.type('125ft')
    page.keyboard.press('Tab')
    page.wait_for_timeout(600)
    assert page.evaluate(
        "() => window.app.history[window.app.history.length - 1].action") \
        == 'Set Multi Home Run'
    assert page.evaluate(
        """(a) => (window.app.project.layers.find(
            l => l.id === a.layerId).powerSocaLengths || {})[a.socaIdx]""",
        seeded) == '125ft'

    # undo hands the length back, one step, same as the rows did
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(800)
    assert page.evaluate(
        """(a) => (window.app.project.layers.find(
            l => l.id === a.layerId).powerSocaLengths || {})[a.socaIdx]
            || null""",
        seeded) is None
    page.evaluate("() => window.app.redo()")
    page.wait_for_timeout(800)
    assert page.evaluate(
        """(a) => (window.app.project.layers.find(
            l => l.id === a.layerId).powerSocaLengths || {})[a.socaIdx]""",
        seeded) == '125ft'


def test_an_occupied_circuit_chip_opens_and_a_free_tail_stays_a_handle(power_page):
    """The port-chip grammar on the power side: an occupied tail is a tile
    that states its number, label and holder and opens its editor in place
    - one per box - while a FREE tail has no circuit to label, so its face
    is a plain drag handle that opens nothing."""
    page, seeded = power_page
    t1 = chip_id(seeded, 0)
    t2 = chip_id(seeded, 1)

    s = tile_state(page, t1)
    assert s, 'the occupied tail built no tile'
    assert s['occupied'] and not s['open'], s
    assert s['bodyInDom'], 'a closed circuit chip detached its editor'
    leg = seeded['legs'][0]
    assert s['faceText'].startswith(str(leg['tail'])), (
        f'the face does not lead with the tail number: {s}')
    assert leg['label'] in s['faceText'], (
        f'the derived circuit label is not on the face: {s}')
    assert 'Screen1' in s['faceText'], (
        f'the holder screen is not on the face: {s}')

    # a free tail: no tile id, no editor, and its face opens nothing
    free = page.evaluate("""(a) => {
        const used = a.tails;
        const t = [1, 2, 3, 4, 5, 6].find(x => !used.includes(x));
        const face = document.querySelector(
            `[data-hwdock="tail-${a.distroId}-${a.number}-${t}"]`);
        if (!face) return null;
        const tile = face.closest('.lrd-tile');
        face.click();
        return {
            hasTileId: 'lrdTile' in tile.dataset,
            wired: 'lrdTileWired' in tile.dataset,
            body: !!tile.querySelector(':scope > .lrd-tile-body'),
            opened: tile.classList.contains('lrd-tile-open'),
            openAnywhere: !!document.querySelector(
                '#hardware-dock .lrd-tile-open'),
        };
    }""", {'distroId': seeded['distroId'], 'number': seeded['number'],
           'tails': [g['tail'] for g in seeded['legs']]})
    assert free, 'the free tail built no chip at all'
    assert not free['hasTileId'] and not free['body'], (
        f'a free chip grew an editor with nothing to edit: {free}')
    assert not free['wired'] and not free['opened'] \
        and not free['openAnywhere'], (
        f'a free chip face click opened something: {free}')

    # occupied chips: one open editor per box, the port chips' rule
    assert page.evaluate(CLICK_FACE_JS, t1)
    s = tile_state(page, t1)
    assert s['open'] and s['bodyPainted'], (
        f'the click did not open the circuit editor: {s}')
    assert page.evaluate(CLICK_FACE_JS, t2)
    s1 = tile_state(page, t1)
    s2 = tile_state(page, t2)
    assert s2['open'] and not s1['open'], (
        f'two circuit editors open in one box: {(s1, s2)}')
    assert page.evaluate(CLICK_FACE_JS, t2)   # leave it closed


def test_a_circuit_label_edits_on_its_chip_under_the_old_action(power_page):
    """The retired Circuit Labels list's row, now on the chip it names: the
    derived label is the placeholder, typed text writes the HOLDER layer's
    powerLabelOverrides under the same action, the face reprints it across
    the deferred rebuild, and undo walks it back."""
    page, seeded = power_page
    leg = seeded['legs'][0]
    tid = chip_id(seeded, 0)
    key = f"power-label-{seeded['layerId']}-{leg['circuit']}"
    assert page.evaluate(CLICK_FACE_JS, tid)

    placeholder = page.evaluate(
        """(key) => document.querySelector(
               `[data-lrd-field="${key}"]`).placeholder""", key)
    assert placeholder == leg['label'], (
        f'the derived label is not the placeholder: {placeholder}')

    field = page.locator(f'[data-lrd-field="{key}"]')
    field.click()
    field.fill('')
    page.keyboard.type('FOH-A')
    page.keyboard.press('Tab')
    page.wait_for_timeout(800)   # commit + the deferred dock rebuild

    assert page.evaluate(
        """(a) => (window.app.project.layers.find(
            l => l.id === a.layerId).powerLabelOverrides
            || {})[a.circuit]""",
        {'layerId': seeded['layerId'], 'circuit': leg['circuit']}) \
        == 'FOH-A', 'the override never landed on the holder layer'
    assert page.evaluate(
        "() => window.app.history[window.app.history.length - 1].action") \
        == 'Edit Circuit Label'
    s = tile_state(page, tid)
    assert 'FOH-A' in s['faceText'], (
        f'the face does not reprint the typed label: {s}')
    assert s['open'], 'the rebuild closed the chip mid-edit'

    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(800)
    assert page.evaluate(
        """(a) => ((window.app.project.layers.find(
            l => l.id === a.layerId).powerLabelOverrides
            || {})[a.circuit]) || null""",
        {'layerId': seeded['layerId'], 'circuit': leg['circuit']}) is None, (
        'undo did not walk the circuit label back')


def test_a_circuit_chip_escape_closes_and_the_rebuild_keeps_the_open_chip(power_page):
    """The shared tile machinery, proved on the second family: the dock's
    wholesale rebuild brings the open circuit chip back by id, and Escape
    from its field closes onto the face."""
    page, seeded = power_page
    tid = chip_id(seeded, 0)
    leg = seeded['legs'][0]
    assert page.evaluate(CLICK_FACE_JS, tid)
    assert tile_state(page, tid)['open']

    page.evaluate("() => window.app.renderHardwareDock()")
    page.wait_for_timeout(100)
    assert tile_state(page, tid)['open'], (
        'the rebuild closed the open circuit chip')

    page.locator(
        f'[data-lrd-field="power-label-{seeded["layerId"]}'
        f'-{leg["circuit"]}"]').click()
    page.keyboard.press('Escape')
    page.wait_for_timeout(100)
    s = tile_state(page, tid)
    assert not s['open'], f'Escape did not close the circuit chip: {s}'
    focused = page.evaluate("""(tileId) => {
        const tile = document.querySelector(`[data-lrd-tile="${tileId}"]`);
        return document.activeElement
            === tile.querySelector(':scope > .lrd-tile-face');
    }""", tid)
    assert focused, 'closing did not hand focus back to the face'


def test_the_power_dock_fits_its_width_open_editor_included(power_page):
    """The power tray obeys the same clamp as the data tray: the dock spans
    the canvas column, and its grids reflow rather than scroll sideways -
    open circuit editor included. (The old per-sidebar width knob
    --lrd-power-w died with the Power sidebar; the window is the driver,
    and the fit is asserted on the dock body itself.)"""
    page, seeded = power_page
    tid = chip_id(seeded, 0)
    assert page.evaluate(CLICK_FACE_JS, tid)
    page.wait_for_timeout(100)
    m = page.evaluate(GRID_FIT_JS)
    assert not m['clipped'] and not m['gridClipped'], (
        f'the power dock scrolls sideways with an editor open: {m}')
    assert not m['strays'], (
        f'circuit chip controls hang past the tray: {m["strays"]}')
    page.evaluate(CLICK_FACE_JS, tid)   # leave it closed


def test_a_backing_tile_carries_the_mirrored_return_occupant(panel_page):
    """Sequential redundancy on the seeded SR: socket 2 is Screen1 port
    1's return end, and its tile says so in the occupant register the
    tiles already use - screen, the screen's own port, the role - on the
    occupied ground, instead of sitting free-but-role-claimed. Derived
    display: nothing was placed on socket 2, so nothing joins the history
    for it."""
    ids = seed(panel_page)
    hist = panel_page.evaluate(
        "() => window.app.history.length")
    panel_page.evaluate("""async (ids) => {
        const send = (url, method, body) => fetch(url, { method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body) }).then(r => r.json());
        await send(`/api/processors/${ids.procId}`, 'PUT',
                   { redundancy: true });
        await send(`/api/processors/${ids.procId}/cards/${ids.cardId}`,
                   'PUT', { redundancyMode: 'sequential' });
        await window.app.refreshProcessors();
    }""", ids)
    panel_page.wait_for_timeout(1200)
    try:
        back = tile_state(panel_page, f"port-{ids['cardId']}-2")
        main = tile_state(panel_page, f"port-{ids['cardId']}-1")
        assert back, 'socket 2 lost its tile'
        assert 'Screen1 p1 return' in back['faceText'], back
        assert back['occupied'], (
            f'a working return must wear the occupied ground: {back}')
        assert 'Screen1' in main['faceText'], main
        assert panel_page.evaluate(
            "() => window.app.history.length") == hist, (
            'derived occupancy earned a history entry')
    finally:
        panel_page.evaluate("""async (ids) => {
            const send = (url, method, body) => fetch(url, { method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body) }).then(r => r.json());
            await send(`/api/processors/${ids.procId}/cards/${ids.cardId}`,
                       'PUT', { redundancyMode: '1to1' });
            await send(`/api/processors/${ids.procId}`, 'PUT',
                       { redundancy: false });
            await window.app.refreshProcessors();
        }""", ids)
        panel_page.wait_for_timeout(600)
