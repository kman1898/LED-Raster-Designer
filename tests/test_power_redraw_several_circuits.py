"""Several power circuits picked on the wall and redrawn as ONE.

The owner's report, 2026-11-12: "I was trying to redraw multiple circuits
using the alt key ... it wouldn't let me do multiple at the same time ...
It was always saying I was trying to overwrite the second one or third
one". His ruling the same day: "Redraw should work just like data", and
"if I select 2 ports to redraw then draw 1 in its place all circuits after
it will be renumbered". Pinned here in a real browser with real mouse and
keyboard events:

* PICK - Alt+drag sweeps circuits (the gesture he reached for), Shift+click
  a run picks it, Shift+drag a box picks every circuit it touches.
* MENU - with 2+ picked, right-click reads "Redraw circuits S1-5 to S2-1 as
  one" (a list where the numbers are not consecutive), and no item names
  one circuit.
* REDRAW - the picked circuits' cabinets are freed and one new path is
  drawn on the first number: no cabinet of the 2nd or 3rd circuit is
  refused as wired; drawing every freed cabinet (or Enter) keeps it.
* NUMBERS - the other picked numbers go and every later circuit closes up,
  on an automatic screen, on a custom one and on a grouped wall; a typed
  circuit name and a circuit's cable stay with their circuit as it moves.
* RULES - picks whose cabinets one circuit cannot carry are refused before
  anything is freed, Esc puts everything back, one undo takes the whole
  thing back, and a locked screen gets the locked error.

The wall is synthetic: 4 x 5 cabinets of 800 W on 208 V x 20 A, cabled
top-down (tl-v), Organized, no splitters, Circuit numbers Across. A column
is 4,000 W, past one circuit's 3,328 W, so each column cuts into its top
four cabinets and a one-cabinet leftover; numbered across, the tops are
circuits 1-4 and the leftovers 5-8 (S1-1 to S1-6, then S2-1 and S2-2).

Run locally:
    python -m pytest tests/test_power_redraw_several_circuits.py -v --browser chromium
"""

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

CAB = 200


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1440, 'height': 900})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_function("() => window.canvasRenderer.viewMode === 'power'")
    yield pg
    context.close()


# `o`: { custom, group, locked, distro, labels: {num: text}, cables: {num: ft} }.
# `distro`: both multis of the wall on one distro, SL.
# A group is two 2 x 5 screens side by side (the same wall, cut in two).
SETUP_JS = """async (o) => {
    const app = window.app, r = window.canvasRenderer;
    const j = (method, url, body) => fetch(url, { method,
        headers: { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body) }).then(x => x.json());
    await app._layerSavesSettled();
    if (app._mergeRedraw) app._mergeRedraw = null;
    await fetch('/api/project/new', { method: 'POST' });
    const specs = o.group ? [['WallA', 2, 0], ['WallB', 2, 400]] : [['Wall', 4, 0]];
    const ids = [];
    for (const [name, columns, x] of specs) {
        const made = await j('POST', '/api/layer/add', { name, columns, rows: 5,
            cabinet_width: 200, cabinet_height: 200, offset_x: x, offset_y: 0 });
        ids.push(made.id);
    }
    const shape = (l) => Object.assign(l, {
        powerFlowPattern: o.custom ? 'custom' : 'tl-v', lastPowerFlowPattern: 'tl-v',
        powerCustomPath: false, powerOrganized: true, powerMaximize: false,
        powerNumberOrder: 'across',
        powerVoltage: 208, powerAmperage: 20, panelWatts: 800,
        powerCustomPaths: {}, powerCustomIndex: 1, powerCustomOverrides: [],
        powerSplitters: { enabled: false, maxWays: 3, manual: { merge: [], split: [] } },
        powerLabelOverrides: {}, powerCircuitCables: {},
        locked: !!o.locked,
    }, o.group ? { group_id: 'gW' } : {},
       o.distro ? { powerSocaDistro: { 1: 'd1', 2: 'd1' }, powerSocaNumber: {} } : {});
    const apply = (layers) => ids.forEach(id => {
        const l = layers.find(x => x.id === id);
        if (l) shape(l);
    });
    const p = await j('GET', '/api/project');
    p.layers = p.layers.filter(l => ids.includes(l.id));
    apply(p.layers);
    p.groups = o.group ? [{ id: 'gW', name: 'WALL', layer_ids: ids }] : [];
    if (o.distro) {
        p.distros = [{ id: 'd1', name: 'SL', ratingA: 400, system: '120/208',
                       voltage: 208, phase: 3 }];
    }
    await j('PUT', '/api/project', p);
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('power_redraw_several');
    apply(app.project.layers);
    const wall = app.project.layers.find(l => l.id === ids[0]);
    app.currentLayer = wall;
    app.selectedLayerIds = new Set([wall.id]);
    app.lastSelectedLayerId = wall.id;
    app._overrideEditing = null;
    app._powerHeld = null;
    app._sweepSelection = null;
    app._portPicks = null;
    if (app.powerCustomSelection) app.powerCustomSelection.clear();
    if (typeof app.hideContextMenu === 'function') app.hideContextMenu();
    app._circuitTailCache = null;
    r.viewMode = 'power'; r.zoom = 0.25; r.panX = 80; r.panY = 80;
    app.renderLayers();
    app.loadLayerToInputs();
    if (o.custom) {
        // The custom wall drawn the way the automatic one walks it.
        const keys = [];
        app.getSelectionScopeLayers(wall).forEach(m => (m.panels || []).forEach(
            pn => keys.push(app.getScopedPanelKey(m.id, pn))));
        app.powerCustomSelection.clear();
        keys.forEach(k => app.powerCustomSelection.add(k));
        app._applyPatternFill('power', 'tl-v', { refill: true });
        app.powerCustomSelection.clear();
    }
    Object.entries(o.labels || {}).forEach(([n, t]) => { wall.powerLabelOverrides[n] = t; });
    Object.entries(o.cables || {}).forEach(([n, ft]) => {
        wall.powerCircuitCables[n] = { ft, connector: null };
    });
    app.resetHistory('Initial State');
    r.render();
    if (!app.__toastsRecorded) {
        const real = app._toast;
        app._toast = function (msg, ...rest) {
            window.__toastsSaid.push({ msg: String(msg), error: !!rest[0] });
            return real.call(this, msg, ...rest);
        };
        app.__toastsRecorded = true;
    }
    window.__toastsSaid = [];
    return ids;
}"""


# The wall as the app reads it: each circuit's number, label and cabinets
# (row, col and the screen), the typed names and cables by number, the
# history and the redraw state.
READ_JS = """(id) => {
    const app = window.app;
    app._circuitTailCache = null;
    const l = app.project.layers.find(x => x.id === id);
    const name = (lid) => (app.project.layers.find(x => x.id === lid) || {}).name;
    return {
        circuits: app.screenCircuits(l).map(c => ({
            num: c.num, label: app.getPowerCircuitLabel(l, c.num),
            cabs: c.panels.map((p, i) => [p.row, p.col,
                name(((c.layers && c.layers[i]) || l).id)]),
        })),
        labels: Object.assign({}, l.powerLabelOverrides || {}),
        cables: Object.fromEntries(Object.entries(l.powerCircuitCables || {})
            .map(([k, v]) => [k, v && v.ft])),
        drawn: Object.keys(l.powerCustomPaths || {})
            .filter(k => (l.powerCustomPaths[k] || []).length).map(Number).sort((a, b) => a - b),
        history: app.history.slice(0, app.historyIndex + 1).map(e => e && e.action),
        merging: !!app._mergeRedraw,
    };
}"""


def setup(pg, **o):
    ids = pg.evaluate(SETUP_JS, o)
    pg.wait_for_timeout(300)
    return ids


def read(pg, lid):
    return pg.evaluate(READ_JS, lid)


def toasts(pg):
    return pg.evaluate("() => (window.__toastsSaid || []).slice()")


def errors(pg):
    return [t['msg'] for t in toasts(pg) if t['error']]


def client_xy(pg, wx, wy):
    return pg.evaluate("""([wx, wy]) => {
        const r = window.canvasRenderer;
        const rect = r.canvas.getBoundingClientRect();
        return [rect.left + wx * r.zoom + r.panX, rect.top + wy * r.zoom + r.panY];
    }""", [wx, wy])


def cab(pg, row, col):
    """The middle of cabinet (row, col), counted across the whole wall: a
    group's second screen sits right of the first, so its columns go on."""
    return client_xy(pg, col * CAB + CAB / 2, row * CAB + CAB / 2)


def drag(pg, a, b, key):
    x0, y0 = cab(pg, *a)
    x1, y1 = cab(pg, *b)
    pg.mouse.move(x0, y0)
    pg.keyboard.down(key)
    pg.mouse.down()
    for i in range(1, 11):
        pg.mouse.move(x0 + (x1 - x0) * i / 10, y0 + (y1 - y0) * i / 10)
    pg.mouse.up()
    pg.keyboard.up(key)
    pg.wait_for_timeout(250)


def shift_click(pg, row, col):
    x, y = cab(pg, row, col)
    pg.mouse.move(x, y)
    pg.keyboard.down('Shift')
    pg.mouse.down()
    pg.mouse.up()
    pg.keyboard.up('Shift')
    pg.wait_for_timeout(200)


def click(pg, row, col):
    x, y = cab(pg, row, col)
    pg.mouse.click(x, y)
    pg.wait_for_timeout(250)


def open_menu(pg, row, col):
    """Right-click a cabinet; the visible menu items' texts."""
    x, y = cab(pg, row, col)
    pg.mouse.click(x, y, button='right')
    pg.wait_for_timeout(300)
    return pg.evaluate("""() => [...document.querySelectorAll('#context-menu .menu-option')]
        .filter(el => el.offsetParent !== null && getComputedStyle(el).display !== 'none'
            && !el.classList.contains('menu-disabled'))
        .map(el => el.textContent.trim())""")


def redraws(items):
    return [t for t in items if t.startswith('Redraw')]


def pick_menu(pg, text):
    pg.locator('#context-menu .menu-option', has_text=text).first.click()
    pg.wait_for_timeout(400)


def label_of(state, num):
    return next(c['label'] for c in state['circuits'] if c['num'] == num)


def cabs_of(state, num):
    return next((c['cabs'] for c in state['circuits'] if c['num'] == num), None)


def test_the_wall_is_what_the_rulings_describe(page):
    (wall,) = setup(page)
    s = read(page, wall)
    assert [c['num'] for c in s['circuits']] == list(range(1, 9))
    assert [c['label'] for c in s['circuits']] == [
        'S1-1', 'S1-2', 'S1-3', 'S1-4', 'S1-5', 'S1-6', 'S2-1', 'S2-2']
    for col in range(4):
        assert cabs_of(s, col + 1) == [[r, col, 'Wall'] for r in range(4)]
        assert cabs_of(s, col + 5) == [[4, col, 'Wall']]


def test_alt_sweep_menu_offers_the_redraw_of_every_swept_circuit(page):
    (wall,) = setup(page)
    drag(page, (4, 0), (4, 2), 'Alt')
    swept = page.evaluate("() => window.app._sweepSelection && window.app._sweepSelection.nums")
    assert swept == [5, 6, 7], swept
    offered = redraws(open_menu(page, 4, 0))
    page.keyboard.press('Escape')
    assert offered == ['Redraw circuits S1-5 to S2-1 as one'], (
        "the menu offers a redraw of the three swept circuits and nothing that "
        f"names one of them, got {offered}")


def test_redraw_as_one_draws_into_the_2nd_and_3rd_and_closes_numbers_up(page):
    (wall,) = setup(page, labels={'8': 'LAST'}, cables={'8': 25})
    drag(page, (4, 0), (4, 2), 'Alt')
    open_menu(page, 4, 0)
    pick_menu(page, 'Redraw circuits S1-5 to S2-1 as one')
    assert read(page, wall)['merging']
    click(page, 4, 0)
    click(page, 4, 1)
    click(page, 4, 2)
    said = errors(page)
    assert not [m for m in said if 'already wired' in m], said
    s = read(page, wall)
    assert not s['merging'], "drawing every freed cabinet keeps the redraw"
    # S1-5 holds the three cabinets; S2-2 closed up to S1-6; 6 circuits.
    assert [c['num'] for c in s['circuits']] == [1, 2, 3, 4, 5, 6]
    assert cabs_of(s, 5) == [[4, 0, 'Wall'], [4, 1, 'Wall'], [4, 2, 'Wall']]
    assert cabs_of(s, 6) == [[4, 3, 'Wall']]
    assert label_of(s, 6) == 'LAST', "the typed name rides its circuit to number 6"
    assert s['cables'] == {'6': 25}, f"the cable rides its circuit, got {s['cables']}"
    assert s['history'][-1] == 'Redraw Circuits As One'
    assert s['history'].count('Redraw Circuits As One') == 1
    ok = [t['msg'] for t in toasts(page) if not t['error']]
    assert any('Circuits S1-5 to S2-1 are now circuit S1-5.' in m for m in ok), ok


def test_one_undo_takes_the_whole_redraw_back(page):
    (wall,) = setup(page, labels={'8': 'LAST'})
    before = read(page, wall)
    drag(page, (4, 0), (4, 2), 'Alt')
    open_menu(page, 4, 0)
    pick_menu(page, 'Redraw circuits')
    for col in range(3):
        click(page, 4, col)
    assert len(read(page, wall)['circuits']) == 6
    page.keyboard.press('Control+z')
    page.wait_for_timeout(400)
    after = read(page, wall)
    assert after['circuits'] == before['circuits']
    assert after['labels'] == before['labels']


def test_esc_puts_every_circuit_back(page):
    (wall,) = setup(page)
    before = read(page, wall)
    drag(page, (4, 0), (4, 2), 'Alt')
    open_menu(page, 4, 0)
    pick_menu(page, 'Redraw circuits')
    click(page, 4, 1)
    page.keyboard.press('Escape')
    page.wait_for_timeout(400)
    after = read(page, wall)
    assert not after['merging']
    assert after['circuits'] == before['circuits']
    assert after['history'] == before['history']


def test_enter_keeps_a_half_drawn_redraw_and_the_walk_takes_the_rest(page):
    (wall,) = setup(page)
    drag(page, (4, 0), (4, 2), 'Alt')
    open_menu(page, 4, 0)
    pick_menu(page, 'Redraw circuits')
    click(page, 4, 0)
    click(page, 4, 1)
    page.keyboard.press('Enter')
    page.wait_for_timeout(400)
    s = read(page, wall)
    assert not s['merging']
    assert cabs_of(s, 5) == [[4, 0, 'Wall'], [4, 1, 'Wall']]
    held = [c for c in s['circuits'] if [4, 2, 'Wall'] in c['cabs']]
    assert held and held[0]['num'] != 5, "the cabinet left undrawn went back to the walk"
    ok = [t['msg'] for t in toasts(page) if not t['error']]
    assert any('1 cabinet left over went to circuit' in m for m in ok), ok


def test_picks_one_circuit_cannot_carry_are_refused_before_anything_is_freed(page):
    (wall,) = setup(page)
    before = read(page, wall)
    drag(page, (1, 0), (1, 2), 'Alt')
    assert redraws(open_menu(page, 1, 0)) == ['Redraw circuits S1-1 to S1-3 as one']
    pick_menu(page, 'Redraw circuits')
    assert errors(page) == [
        'Circuits S1-1 to S1-3 hold 12 panels together, and one circuit takes '
        '4 panels at 208V/20A at 80%. Pick fewer circuits to redraw as one.']
    after = read(page, wall)
    assert not after['merging']
    assert after['circuits'] == before['circuits']
    assert after['history'] == before['history']


def test_shift_click_picks_a_list_and_a_tile_fills_it_on_a_custom_screen(page):
    (wall,) = setup(page, custom=True)
    s0 = read(page, wall)
    assert s0['drawn'] == list(range(1, 9)), s0['drawn']
    shift_click(page, 4, 0)
    shift_click(page, 4, 1)
    shift_click(page, 4, 3)
    shift_click(page, 4, 1)   # un-picks it
    shift_click(page, 4, 2)
    assert redraws(open_menu(page, 4, 0)) == ['Redraw circuits S1-5, S2-1 and S2-2 as one']
    pick_menu(page, 'Redraw circuits')
    # A pattern tile with nothing selected fills the freed cabinets, in
    # the pattern, onto the redraw's one circuit, and keeps it.
    page.locator('.power-flow-pattern-btn[data-pattern="tl-h"]').first.click()
    page.wait_for_timeout(400)
    s = read(page, wall)
    assert not s['merging']
    assert s['drawn'] == [1, 2, 3, 4, 5, 6], "custom numbers close up with no gap"
    assert cabs_of(s, 5) == [[4, 0, 'Wall'], [4, 2, 'Wall'], [4, 3, 'Wall']]
    assert cabs_of(s, 6) == [[4, 1, 'Wall']], "S1-6 (old circuit 6) is number 6 still"
    assert s['history'][-1] == 'Redraw Circuits As One'


def test_shift_drag_box_picks_every_circuit_it_touches(page):
    (wall,) = setup(page)
    drag(page, (4, 1), (4, 3), 'Shift')
    picks = page.evaluate("() => window.app._portPicks")
    assert picks and picks['kind'] == 'power' and sorted(picks['nums']) == [6, 7, 8], picks


def test_a_grouped_wall_redraws_as_one_wall(page):
    a, b = setup(page, group=True)
    s0 = read(page, a)
    names = {c['num']: {x[2] for x in c['cabs']} for c in s0['circuits']}
    left = [n for n, on in names.items() if len(cabs_of(s0, n)) == 1]
    assert len(left) == 4 and names[left[1]] == {'WallA'} and names[left[2]] == {'WallB'}, s0
    # The leftovers of column 2 (WallA) and column 3 (WallB), across the seam.
    shift_click(page, 4, 1)
    shift_click(page, 4, 2)
    open_menu(page, 4, 1)
    pick_menu(page, 'Redraw circuits')
    click(page, 4, 1)
    click(page, 4, 2)
    s = read(page, a)
    assert not s['merging']
    assert cabs_of(s, left[1]) == [[4, 1, 'WallA'], [4, 0, 'WallB']]
    assert len(s['circuits']) == len(s0['circuits']) - 1
    assert not errors(page)


def test_a_locked_screen_is_refused_with_the_locked_error(page):
    (wall,) = setup(page, locked=True)
    before = read(page, wall)
    drag(page, (4, 0), (4, 2), 'Alt')
    open_menu(page, 4, 0)
    pick_menu(page, 'Redraw circuits')
    e = errors(page)
    assert e and 'is locked' in e[-1], e
    after = read(page, wall)
    assert not after['merging']
    assert after['circuits'] == before['circuits']


def test_on_a_distro_a_custom_wall_keeps_every_circuit_on_its_tail(page):
    """The Clear Circuit rule (every other circuit keeps its distro, its
    multi number and its tail): the circuit after the picks closes up to
    number 6 and still reads SL2-2, the new circuit takes the first pick's
    tail, and the freed tail SL1-6 waits empty."""
    (wall,) = setup(page, custom=True, distro=True)
    s0 = read(page, wall)
    assert [c['label'] for c in s0['circuits']] == [
        'SL1-1', 'SL1-2', 'SL1-3', 'SL1-4', 'SL1-5', 'SL1-6', 'SL2-1', 'SL2-2'], s0['circuits']
    drag(page, (4, 0), (4, 2), 'Alt')
    assert redraws(open_menu(page, 4, 0)) == ['Redraw circuits SL1-5 to SL2-1 as one']
    pick_menu(page, 'Redraw circuits')
    for col in range(3):
        click(page, 4, col)
    s = read(page, wall)
    assert not s['merging'] and not errors(page), errors(page)
    assert s['drawn'] == [1, 2, 3, 4, 5, 6]
    assert cabs_of(s, 5) == [[4, 0, 'Wall'], [4, 1, 'Wall'], [4, 2, 'Wall']]
    assert label_of(s, 5) == 'SL1-5'
    assert cabs_of(s, 6) == [[4, 3, 'Wall']] and label_of(s, 6) == 'SL2-2'
