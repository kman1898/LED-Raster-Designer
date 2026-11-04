"""A pattern tile pressed while ports are being redrawn (QA, 1.6.0).

The owner's log, 2026-11-04: on a custom screen he redrew ports 42 and 43
as one (Redraw Ports As One) and, with no cabinets selected, pressed a
Data pattern tile. The tile took the "no cabinets, the screen selected"
branch and REFILLED the whole screen from port 1: every port re-laid (41
paths became 49), the port he had just merged undone, the half-height row
he had left unwired wired, and the redraw left open, so an undo went back
into an open redraw with ports 42 and 43 empty.

Now a tile pressed with nothing selected while a redraw holds cabinets
fills only those cabinets, in the tile's pattern, into the redraw's port,
and closes the redraw the way a marquee and a tile do: no other port's
cabinets move, nothing outside the redraw is wired, and one undo puts the
screen back as it was before the redraw, on the server too.

The second half pins an intermittent seen once in about nine runs: the
redraw opened over ports 42 and 43 still drawn, and the marquee fill of
the freed cabinets was refused "Cannot apply: 4 panels already wired to
other ports". The menu that opens the redraw is armed on the copy of the
screen the page held when it opened; a save's reply landing while the
menu was open put a fresh copy in its place, and the redraw freed the old
copy's ports. It now acts on the live copy.

The wall is synthetic, the shape of the owner's show and none of its data:
84 x 5 cabinets of 192 x 384 on NovaStar COEX 1G at 8-bit 60 Hz (8 full
cabinets a port), the bottom row half-height and left unwired, drawn by
hand in the cut the show was drawn in: a port of 8 down each stack of
rows 0-3, then the four row-end leftovers of 4 on their own (44 ports),
the first two of those already redrawn as one (P41), leaving 43.

Run locally:
    python -m pytest tests/test_pattern_tile_in_redraw.py -v --browser chromium
"""

import json

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1900, 'height': 1050})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    for ep in ('save-file', 'open-file', 'select-directory'):
        pg.route(f'**/api/native-dialog/{ep}', lambda route: route.fulfill(
            status=200, content_type='application/json',
            body='{"cancelled": true, "path": null}'))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    pg.wait_for_timeout(800)
    pg.evaluate(HELPERS_JS)
    yield pg
    context.close()


HELPERS_JS = r"""
window.__ptr = {
    errs: [], notes: [], logs: [],
    // The owner's state: whole-screen custom, the full-height cabinets
    // drawn in the show's old cut (44 ports), P41-P42 redrawn as one.
    async reset() {
        const app = window.app, r = window.canvasRenderer;
        app._mergeRedraw = null;
        app._portPicks = null;
        app._overrideEditing = null;
        if (app.customSelection) app.customSelection.clear();
        if (typeof app.hideContextMenu === 'function') app.hideContextMenu();
        this.delay = 0;
        await app._layerSavesSettled();
        let project = await (await fetch('/api/project')).json();
        project.layers = [];
        project.groups = [];
        project.port_assignments = { auto: false, autoRetired: true, pins: [] };
        (project.canvases || []).forEach(c => {
            c.raster_width = 16384; c.raster_height = 2160;
            c.show_raster_width = 16384; c.show_raster_height = 2160;
        });
        await fetch('/api/project', { method: 'PUT',
            headers: {'Content-Type': 'application/json'}, body: JSON.stringify(project) });
        const made = await (await fetch('/api/layer/add', { method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ name: 'TileWall', columns: 84, rows: 5,
                cabinet_width: 192, cabinet_height: 384, offset_x: 0, offset_y: 0 }) })).json();
        await fetch('/api/layer/' + made.id, { method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ halfLastRow: true }) });
        app.project = await (await fetch('/api/project')).json();
        app.dedupeProjectLayers('pattern_tile_reset');
        const l = app.project.layers.find(x => x.id === made.id);
        const paths = {};
        let n = 0;
        const put = cells => { n += 1; paths[n] = cells.map(([row, col]) => ({ row, col })); };
        for (let k = 0; k < 10; k++) {
            for (let row = 0; row < 4; row++) put([...Array(8).keys()].map(i => [row, k * 8 + i]));
        }
        put([[0, 80], [0, 81], [0, 82], [0, 83], [1, 83], [1, 82], [1, 81], [1, 80]]);
        put([80, 81, 82, 83].map(c => [2, c]));
        put([80, 81, 82, 83].map(c => [3, c]));
        Object.assign(l, { processorType: 'novastar-coex-1g', bitDepth: 8, frameRate: 60,
            lowLatency: false, portMappingMode: 'organized', portNumberOrder: 'down',
            lastFlowPattern: 'tl-h', flowPattern: 'custom',
            customPortPaths: paths, customPortIndex: 41, customPortOverrides: [] });
        app.currentLayer = l;
        app.selectedLayerIds = new Set([l.id]);
        r.viewMode = 'data-flow';
        app.loadLayerToInputs();
        app.saveClientSideProperties();
        app.updateLayers([l]);
        await app._layerSavesSettled();
        // camera on the right end of the wall: columns 60-83
        const off = app._getLayerWorkspaceOffset(l);
        r.zoom = (r.canvas.width * 0.9) / (24 * 192);
        r.panX = r.canvas.width * 0.05 - (off.wx + 60 * 192) * r.zoom;
        r.panY = 60 - off.wy * r.zoom;
        r.render();
        if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
        app.resetHistory('Tile Test Baseline');
        this.errs = []; this.notes = []; this.logs = [];
        if (!app.__ptrWrapped) {
            app.__ptrWrapped = true;
            const real = app._toast.bind(app);
            app._toast = (m, err, ms) => {
                (err ? window.__ptr.errs : window.__ptr.notes).push(String(m));
                return real(m, err, ms);
            };
            // what reaches the client log, and a PUT reply held back by
            // `delay` ms on its way to the page (a busy machine)
            const beacon = navigator.sendBeacon.bind(navigator);
            navigator.sendBeacon = (url, data) => {
                if (data && typeof data.text === 'function') {
                    data.text().then(t => { try { window.__ptr.logs.push(JSON.parse(t)); } catch (e) {} });
                }
                return beacon(url, data);
            };
            const realFetch = window.fetch.bind(window);
            window.fetch = (url, opts) => {
                const p = realFetch(url, opts);
                const put = opts && opts.method === 'PUT' && /\/api\/layer\//.test(String(url));
                if (!put || !(window.__ptr.delay > 0)) return p;
                const ms = window.__ptr.delay;
                return p.then(res => new Promise(done => setTimeout(() => done(res), ms)));
            };
        }
        return l.id;
    },
    layer(id) { return window.app.project.layers.find(x => x.id === id); },
    paths(id) {
        const l = this.layer(id), out = {};
        Object.keys(l.customPortPaths || {}).forEach(k => {
            const p = l.customPortPaths[k] || [];
            if (p.length) out[k] = p.map(e => [e.row, e.col]);
        });
        return out;
    },
    async serverPaths(id) {
        const l = (await (await fetch('/api/project')).json()).layers.find(x => x.id === id);
        const out = {};
        Object.keys((l && l.customPortPaths) || {}).forEach(k => {
            const p = l.customPortPaths[k] || [];
            if (p.length) out[k] = p.map(e => [e.row, e.col]);
        });
        return out;
    },
    session() {
        const s = window.app._mergeRedraw;
        return s ? { num: s.num, picks: s.picks, ready: !!s.ready, held: s.held.size } : null;
    },
    history() {
        const app = window.app;
        return { index: app.historyIndex, length: app.history.length,
                 action: app.history[app.historyIndex] ? app.history[app.historyIndex].action : null };
    },
    cellXY(id, row, col) {
        const app = window.app, r = window.canvasRenderer, l = this.layer(id);
        const p = app.getPanelByRowCol(l, row, col);
        const off = app._getLayerWorkspaceOffset(l);
        const rect = r.canvas.getBoundingClientRect();
        return { x: rect.left + r.panX + (off.wx + p.x + p.width / 2) * r.zoom,
                 y: rect.top + r.panY + (off.wy + p.y + p.height / 2) * r.zoom };
    },
};
"""

TILE = '.flow-pattern-btn:not(.power-flow-pattern-btn)[data-pattern="{}"]'


def reset(page):
    lid = page.evaluate("() => window.__ptr.reset()")
    page.wait_for_timeout(200)
    return lid


def paths(page, lid):
    return {int(k): v for k, v in page.evaluate("(id) => window.__ptr.paths(id)", lid).items()}


def server_paths(page, lid):
    return {int(k): v for k, v in
            page.evaluate("(id) => window.__ptr.serverPaths(id)", lid).items()}


def xy(page, lid, row, col):
    p = page.evaluate("([id, r, c]) => window.__ptr.cellXY(id, r, c)", [lid, row, col])
    return p['x'], p['y']


def shift_click(page, lid, row, col):
    x, y = xy(page, lid, row, col)
    page.keyboard.down('Shift')
    page.mouse.click(x, y)
    page.keyboard.up('Shift')
    page.wait_for_timeout(120)


def open_menu(page, lid, row, col):
    x, y = xy(page, lid, row, col)
    page.mouse.click(x, y, button='right')
    page.wait_for_timeout(200)
    return page.evaluate("""() => {
        const el = document.querySelector('[data-action="ovr-merge"]');
        return (el && el.style.display !== 'none') ? el.textContent : null;
    }""")


def pick_and_open(page, lid, after_menu=None):
    """Shift+click ports 42 and 43, right-click, Redraw ports P42-P43 as
    one. `after_menu` runs while the menu is open."""
    shift_click(page, lid, 2, 80)
    shift_click(page, lid, 3, 80)
    assert open_menu(page, lid, 2, 80) == 'Redraw ports P42-P43 as one'
    if after_menu:
        after_menu()
    page.click('[data-action="ovr-merge"]')
    page.wait_for_function("() => window.app._mergeRedraw && window.app._mergeRedraw.ready")
    page.wait_for_timeout(150)


ROW2 = [[2, c] for c in range(80, 84)]
ROW3 = [[3, c] for c in range(80, 84)]
SNAKE_23 = ROW2 + [[3, c] for c in range(83, 79, -1)]


def _base_ports():
    out = {}
    n = 0
    for k in range(10):
        for row in range(4):
            n += 1
            out[n] = [[row, k * 8 + i] for i in range(8)]
    out[41] = [[0, 80], [0, 81], [0, 82], [0, 83], [1, 83], [1, 82], [1, 81], [1, 80]]
    out[42] = ROW2
    out[43] = ROW3
    return out


BASE = _base_ports()


def test_the_wall_is_the_owners_state(page):
    lid = reset(page)
    assert paths(page, lid) == BASE
    assert server_paths(page, lid) == BASE


def test_a_tile_during_a_redraw_fills_only_the_redraw_and_closes_it(page):
    lid = reset(page)
    pick_and_open(page, lid)
    s = page.evaluate("() => window.__ptr.session()")
    assert s == {'num': 42, 'picks': [42, 43], 'ready': True, 'held': 8}
    opened = page.evaluate("() => window.__ptr.history()")
    assert 42 not in paths(page, lid) and 43 not in paths(page, lid)
    # nothing selected: the tile
    assert page.evaluate("() => window.app.customSelection.size") == 0
    page.locator(TILE.format('tl-h')).first.click()
    page.wait_for_timeout(500)
    got = paths(page, lid)
    want = {n: BASE[n] for n in range(1, 42)}
    want[42] = SNAKE_23
    # only the redraw's cabinets changed; every other port is as it was,
    # and the half-height row is still unwired
    assert got == want, {k: v for k, v in got.items() if want.get(k) != v}
    assert not any(r == 4 for cells in got.values() for r, _ in cells)
    # the redraw closed, kept as ONE step on top of the state before it
    assert page.evaluate("() => window.__ptr.session()") is None
    h = page.evaluate("() => window.__ptr.history()")
    assert h['action'] == 'Redraw Ports As One'
    assert h['index'] == opened['index']
    errs = page.evaluate("() => window.__ptr.errs")
    assert errs == [], errs
    page.wait_for_timeout(300)
    page.evaluate("() => window.app._layerSavesSettled()")
    assert server_paths(page, lid) == want


def test_one_undo_puts_everything_back_on_the_server_too(page):
    lid = reset(page)
    pick_and_open(page, lid)
    page.locator(TILE.format('tl-h')).first.click()
    page.wait_for_timeout(500)
    page.keyboard.press('Control+z')
    page.wait_for_timeout(800)
    page.evaluate("() => window.app._layerSavesSettled()")
    assert page.evaluate("() => window.__ptr.session()") is None, 'undo went back into an open redraw'
    assert paths(page, lid) == BASE
    assert server_paths(page, lid) == BASE
    assert page.evaluate("() => window.__ptr.history()")['action'] == 'Tile Test Baseline'


def test_the_tile_names_itself_in_the_log(page):
    lid = reset(page)
    pick_and_open(page, lid)
    page.locator(TILE.format('tl-v')).first.click()
    page.wait_for_timeout(600)
    logs = page.evaluate("() => window.__ptr.logs")
    tile = [x['details'] for x in logs if x.get('action') == 'pattern_tile']
    assert tile and tile[-1]['pattern'] == 'tl-v'
    assert tile[-1]['kind'] == 'data' and tile[-1]['view'] == 'data-flow'
    assert tile[-1]['session'] == 'merge' and tile[-1]['sessionNum'] == 42
    assert tile[-1]['layerId'] == lid
    clicks = [x['details'] for x in logs if x.get('action') == 'ui_click']
    assert any(c.get('data') == 'tl-v' and c.get('text') for c in clicks), clicks
    filled = [x['details'] for x in logs if x.get('action') == 'pattern_tile_session_filled']
    assert filled and filled[-1]['ok'] is True and filled[-1]['cabinets'] == 8
    # tl-v laid the redraw's cabinets column by column
    assert paths(page, lid)[42] == [[2, 80], [3, 80], [3, 81], [2, 81],
                                    [2, 82], [3, 82], [3, 83], [2, 83]]


def test_a_tile_with_no_redraw_open_still_refills_the_screen(page):
    """The rule the redraw case was carved out of is unchanged: no redraw,
    nothing selected, the screen selected - the tile re-lays the screen."""
    lid = reset(page)
    page.locator(TILE.format('tl-h')).first.click()
    page.wait_for_timeout(500)
    got = paths(page, lid)
    assert len(got) == 47
    logs = page.evaluate("() => window.__ptr.logs")
    tile = [x['details'] for x in logs if x.get('action') == 'pattern_tile']
    assert tile and tile[-1]['session'] is None


def test_a_tile_during_a_redraw_on_an_automatic_screen_fills_only_the_redraw(page):
    """The same on an automatic screen, a port taken over for redrawing:
    the tile lays the cabinets it holds into it, the walk is left alone,
    and the redraw ends."""
    lid = reset(page)
    page.evaluate("""(id) => { const app = window.app, l = window.__ptr.layer(id);
        l.flowPattern = 'tl-h'; l.customPortPaths = {}; l.customPortIndex = 1;
        app.updateLayers([l]); app.resetHistory('Auto Baseline'); }""", lid)
    page.wait_for_timeout(300)
    before = page.evaluate("""(id) => window.app.calculatePortAssignments(window.__ptr.layer(id))
        .map(a => [a.port, a.panel.row, a.panel.col])""", lid)
    # The automatic wall's leftovers are stacked (P46 rows 0-1, P47 rows
    # 2-3, 8 cabinets each), so no two of its ports fit one: redraw P47.
    page.evaluate("""(id) => { const app = window.app, l = window.__ptr.layer(id);
        app.overrideRun(l, 'data', 47); }""", lid)
    page.wait_for_timeout(300)
    assert page.evaluate("() => window.app._overrideEditing && window.app._overrideEditing.num") == 47
    page.locator(TILE.format('tl-v')).first.click()
    page.wait_for_timeout(500)
    after = page.evaluate("""(id) => window.app.calculatePortAssignments(window.__ptr.layer(id))
        .map(a => [a.port, a.panel.row, a.panel.col])""", lid)
    assert [x for x in after if x[0] != 47] == [x for x in before if x[0] != 47]
    assert [x[1:] for x in after if x[0] == 47] == [[2, 80], [3, 80], [3, 81], [2, 81],
                                                     [2, 82], [3, 82], [3, 83], [2, 83]]
    assert page.evaluate("() => window.app._overrideEditing") is None, 'the redraw stayed open'


# ── the redraw opened over ports still drawn ─────────────────────────────


def test_a_save_landing_while_the_menu_is_open_frees_the_live_screen(page):
    """The intermittent, made certain: a save's reply lands between the
    right-click and the menu click and replaces the page's copy of the
    screen. The redraw frees the live copy's ports, and a marquee and a
    tile fill the freed cabinets instead of refusing them as wired."""
    lid = reset(page)

    def save_lands():
        swapped = page.evaluate("""async (id) => {
            const app = window.app, was = window.__ptr.layer(id);
            app.updateLayers([was]);
            await app._layerSavesSettled();
            await new Promise(r => setTimeout(r, 50));
            return window.__ptr.layer(id) !== was;
        }""", lid)
        assert swapped, 'the reply did not replace the screen copy'
    pick_and_open(page, lid, after_menu=save_lands)
    got = paths(page, lid)
    assert 42 not in got and 43 not in got, 'the redraw opened over ports still drawn'
    # marquee over the freed cabinets, then the tile
    page.evaluate("""(id) => { const app = window.app, l = window.__ptr.layer(id);
        [[2,80],[2,81],[2,82],[2,83],[3,80],[3,81],[3,82],[3,83]].forEach(([r, c]) =>
            app.customSelection.add(app.getScopedPanelKey(l.id, app.getPanelByRowCol(l, r, c)))); }""", lid)
    page.locator(TILE.format('tl-h')).first.click()
    page.wait_for_timeout(500)
    errs = page.evaluate("() => window.__ptr.errs")
    assert not any('already wired' in e for e in errs), errs
    assert paths(page, lid)[42] == SNAKE_23
    assert page.evaluate("() => window.__ptr.session()") is None


# Reply delays (ms) against the wait between the right-click and the menu
# click: before, inside and after the window the menu is open.
STRESS = [(d, w) for d in (0, 120, 250, 400, 550, 700) for w in (0, 150, 350, 600)]


@pytest.mark.parametrize("delay,wait", STRESS, ids=[f'reply{d}-menu{w}' for d, w in STRESS])
def test_stress_the_redraw_always_frees_the_ports_it_opens_on(page, delay, wait):
    """A save still out when the menu opens (its reply held back by
    `delay` ms, a busy machine), the menu clicked `wait` ms after the
    right-click: whatever lands where, the redraw opens on ports 42-43
    freed, and the tile fills them."""
    lid = reset(page)
    page.evaluate("(d) => { window.__ptr.delay = d; }", delay)
    page.evaluate("(id) => window.app.updateLayers([window.__ptr.layer(id)])", lid)
    pick_and_open(page, lid, after_menu=(lambda: page.wait_for_timeout(wait)) if wait else None)
    page.evaluate("() => window.app._layerSavesSettled()")
    page.wait_for_timeout(max(0, delay - wait) + 100)
    got = paths(page, lid)
    s = page.evaluate("() => window.__ptr.session()")
    assert s == {'num': 42, 'picks': [42, 43], 'ready': True, 'held': 8}
    assert 42 not in got and 43 not in got, json.dumps({k: got.get(k) for k in (41, 42, 43)})
    page.locator(TILE.format('tl-h')).first.click()
    page.wait_for_timeout(400)
    page.evaluate("() => { window.__ptr.delay = 0; }")
    errs = page.evaluate("() => window.__ptr.errs")
    assert errs == [], errs
    assert paths(page, lid)[42] == SNAKE_23
    assert page.evaluate("() => window.__ptr.session()") is None
