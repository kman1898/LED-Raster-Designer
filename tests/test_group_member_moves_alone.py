"""One screen of a group, picked in the Screens list, moves on its own (#125).

A user's report: with screens in a group, expanding the group in the Screens
list lets you select one of its screens, but the offset fields on Pixel Map
and Show Look only showed and edited the GROUP's position. Ungrouping to
move it and grouping again lost the custom Data and Power runs.

The owner's ruling (2026-11-11), amending "grouped screens only move as a
group" (2026-09-22): "these offsets should be allowed if they manually
select the screen via the side tab specifically."

  * ONE member picked by hand in the Screens list: its own X / Y (Pixel Map
    Offset X / Y, Show Look Show Offset X / Y) show and edit that screen
    alone, and a note under the fields says so.
  * Everything else still moves the whole group as one: the group's own
    row, a member picked on the canvas, a canvas drag, the 3D arrow keys.

Each case is proved here through the gestures that follow it: the custom
runs across the members stay, bars that no longer fit after the move are
flagged, one undo puts it back, and a second page follows without writing.

Run locally:
    python -m pytest tests/test_group_member_moves_alone.py -n 4 --dist loadfile
"""

import json
import time
from urllib.parse import urlparse

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


QUIET = "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}"
UNAVAILABLE = json.dumps({'ok': False, 'cancelled': True})

# WALL: L and R, two 11 x 4 walls of 200 px cabinets standing edge to edge
# (R starts where L ends, 2200 px), grouped. LOOSE stands apart. L carries a
# hand-drawn data port and a hand-drawn circuit that each run off L onto R.
SEED_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    proj.canvases = proj.canvases.slice(0, 1); proj.active_canvas_id = proj.canvases[0].id;
    Object.assign(proj.canvases[0], {raster_width: 7000, raster_height: 1600, show_raster_width: 7000, show_raster_height: 1600});
    delete proj.port_assignments; delete proj.pullSheet; delete proj.pullSheetEdits;
    delete proj.binder; delete proj.groupNameDisplay; delete proj.groupNameDisplayByView;
    delete proj.riggingTool;
    await j('PUT', '/api/project', proj);
    const base = {columns: 11, rows: 4, cabinet_width: 200, cabinet_height: 200, panelWatts: 200,
                  flowPattern: 'tl-h', powerVoltage: 208, powerAmperage: 20, powerFlowPattern: 'tl-v',
                  powerOrganized: true, processorType: 'novastar-armor', bitDepth: 8, frameRate: 60};
    const add = (b) => j('POST', '/api/layer/add', {...base, ...b});
    await add({name: 'L', offset_x: 0, offset_y: 0});
    await add({name: 'R', offset_x: 2200, offset_y: 0});
    await add({name: 'LOOSE', columns: 4, rows: 4, offset_x: 6000, offset_y: 0});
    let p = await j('GET', '/api/project');
    const f = n => p.layers.find(l => l.name === n);
    const L = f('L'), R = f('R');
    L.group_id = 'gw'; R.group_id = 'gw';
    p.groups = [{id: 'gw', name: 'WALL', layer_ids: [L.id, R.id], canvas_id: L.canvas_id, routeDataAsOne: false}];
    L.portMappingMode = 'custom';
    L.customPortPaths = {'1': [{row: 3, col: 9}, {row: 3, col: 10}, {row: 3, col: 0, layerId: R.id}, {row: 3, col: 1, layerId: R.id}]};
    L.powerCustomPaths = {'1': [{row: 0, col: 10}, {row: 0, col: 0, layerId: R.id}]};
    await j('PUT', '/api/project', p);
    p = await j('GET', '/api/project');
    app.project = p;
    app.dedupeProjectLayers('group_member_moves_alone');
    app.setGroupExpanded('gw', true);
    app.selectLayer(app.project.layers.find(l => l.name === 'LOOSE'));
    app.renderLayers();
    window.canvasRenderer.render();
    app.resetHistory('Group Member Seed');
    return Object.fromEntries(app.project.layers.map(l => [l.name, l.id]));
}"""


def _context(pw_browser):
    ctx = pw_browser.new_context(viewport={'width': 1700, 'height': 1000})
    ctx.add_init_script(QUIET)
    for name in ('save-file', 'open-file', 'select-directory'):
        ctx.route(f'**/api/native-dialog/{name}', lambda route: route.fulfill(
            status=200, content_type='application/json', body=UNAVAILABLE))
    return ctx


def _open(ctx, url):
    page = ctx.new_page()
    page.errors = []
    page.on('pageerror', lambda e: page.errors.append(str(e)))
    page.goto(url, wait_until='domcontentloaded')
    page.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)
    page.wait_for_timeout(1000)
    page.evaluate("() => { const s = document.querySelector('#start-page'); if (s) s.style.display = 'none'; }")
    return page


@pytest.fixture()
def pg(e2e_server, pw_browser):
    ctx = _context(pw_browser)
    page = _open(ctx, e2e_server)
    page.ids = page.evaluate(SEED_JS)
    page.e2e_server = e2e_server
    page.wait_for_timeout(300)
    yield page
    ctx.close()
    assert not page.errors, page.errors


# ── gestures ─────────────────────────────────────────────────────────────

def tab(p, mode):
    p.locator(f'#view-tabs .view-tab[data-mode="{mode}"]').click()
    p.wait_for_timeout(300)
    # every screen in sight, so a press lands where the test aims
    p.evaluate("() => window.canvasRenderer.fitToView()")
    p.wait_for_timeout(100)


def list_pick(p, name):
    """A plain click on the screen's own row in the expanded group."""
    p.evaluate("() => { window.app.setGroupExpanded('gw', true); }")
    p.locator(f'#layers-list .layer-item[data-layer-id="{p.ids[name]}"]').click()
    p.wait_for_timeout(250)


def group_pick(p):
    p.locator('#layers-list .screen-group[data-group-id="gw"] .screen-group-row').click(position={'x': 30, 'y': 8})
    p.wait_for_timeout(250)


def type_field(p, field, value):
    p.fill(f'#{field}', str(value))
    p.press(f'#{field}', 'Enter')
    p.wait_for_timeout(500)


def to_client(p, name, fx=0.5, fy=0.5):
    """A point on the screen as the active view draws it, in page pixels."""
    pt = p.evaluate("""([id, fx, fy]) => {
        const app = window.app, r = window.canvasRenderer;
        const l = app.project.layers.find(x => x.id === id);
        const b = r.getLayerBoundsInActiveView(l);
        const c = (app.project.canvases || []).find(x => x.id === l.canvas_id) || {};
        const rect = r.canvas.getBoundingClientRect();
        const x = (c.workspace_x || 0) + b.x + b.width * fx, y = (c.workspace_y || 0) + b.y + b.height * fy;
        return {x: rect.left + x * r.zoom + r.panX, y: rect.top + y * r.zoom + r.panY};
    }""", [p.ids[name], fx, fy])
    return pt['x'], pt['y']


# ── reads ────────────────────────────────────────────────────────────────

POS_JS = """(names) => Object.fromEntries(window.app.project.layers.filter(l => names.includes(l.name))
    .map(l => [l.name, [l.offset_x, l.offset_y, l.showOffsetX ?? l.offset_x, l.showOffsetY ?? l.offset_y]]))"""

SERVER_POS_JS = """async (names) => { const p = await fetch('/api/project').then(r => r.json());
    return Object.fromEntries(p.layers.filter(l => names.includes(l.name))
        .map(l => [l.name, [l.offset_x, l.offset_y, l.showOffsetX ?? l.offset_x, l.showOffsetY ?? l.offset_y]])); }"""


def pos(p, *names):
    return p.evaluate(POS_JS, list(names))


def server_pos(p, *names, want=None, timeout=6.0):
    deadline = time.time() + timeout
    got = None
    while time.time() < deadline:
        got = p.evaluate(SERVER_POS_JS, list(names))
        if want is None or got == want:
            return got
        time.sleep(0.2)
    return got


def fields(p, *ids):
    return p.evaluate("(ids) => ids.map(id => document.getElementById(id).value)", list(ids))


def note(p, which):
    """(text, shown, kind) of the note under a tab's offset fields."""
    return p.evaluate("""(id) => { const el = document.getElementById(id);
        return [el.textContent, !el.hidden && el.offsetParent !== null, el.dataset.groupMove || '']; }""", which)


def selected(p):
    return p.evaluate("() => [...window.app.selectedLayerIds].sort((a, b) => a - b)")


def steps(p):
    return p.evaluate("() => window.app.history.length")


def undo(p):
    p.evaluate("() => window.app.undo()")
    p.wait_for_timeout(600)


# ── the list pick moves one screen ───────────────────────────────────────

def test_a_list_picked_member_moves_alone_on_pixel_map(pg):
    p = pg
    tab(p, 'pixel-map')
    list_pick(p, 'R')
    assert selected(p) == [p.ids['R']]
    # its own place, not the group's
    assert fields(p, 'offset-x', 'offset-y') == ['2200', '0']
    assert note(p, 'group-move-note') == ['Moves only R in its group', True, 'one']
    before = steps(p)
    type_field(p, 'offset-x', 2600)
    want = {'L': [0, 0, 0, 0], 'R': [2600, 0, 2600, 0], 'LOOSE': [6000, 0, 6000, 0]}
    assert pos(p, 'L', 'R', 'LOOSE') == want
    assert server_pos(p, 'L', 'R', 'LOOSE', want=want) == want
    assert steps(p) == before + 1
    # still picked after the edit landed: the next value moves it alone too
    assert fields(p, 'offset-x') == ['2600']
    assert note(p, 'group-move-note')[0] == 'Moves only R in its group'
    type_field(p, 'offset-y', 300)
    want = {'L': [0, 0, 0, 0], 'R': [2600, 300, 2600, 300]}
    assert pos(p, 'L', 'R') == want
    assert server_pos(p, 'L', 'R', want=want) == want
    assert steps(p) == before + 2


def test_a_list_picked_member_moves_alone_on_show_look(pg):
    p = pg
    tab(p, 'show-look')
    list_pick(p, 'R')
    assert fields(p, 'show-offset-x', 'show-offset-y') == ['2200', '0']
    assert note(p, 'group-move-note-show') == ['Moves only R in its group', True, 'one']
    type_field(p, 'show-offset-y', 450)
    # Show Look only: the Pixel Map place stays
    want = {'L': [0, 0, 0, 0], 'R': [2200, 0, 2200, 450]}
    assert pos(p, 'L', 'R') == want
    assert server_pos(p, 'L', 'R', want=want) == want


def test_the_group_row_still_moves_the_whole_group(pg):
    p = pg
    tab(p, 'pixel-map')
    list_pick(p, 'R')
    group_pick(p)
    assert selected(p) == sorted([p.ids['L'], p.ids['R']])
    assert fields(p, 'offset-x', 'offset-y') == ['0', '0']
    assert note(p, 'group-move-note') == ['Moves the whole group', True, 'group']
    type_field(p, 'offset-x', 100)
    want = {'L': [100, 0, 100, 0], 'R': [2300, 0, 2300, 0]}
    assert pos(p, 'L', 'R') == want
    assert server_pos(p, 'L', 'R', want=want) == want


def test_a_member_picked_on_the_canvas_moves_the_whole_group(pg):
    p = pg
    tab(p, 'show-look')
    list_pick(p, 'R')
    # a click on R on the canvas, after the list pick, is a canvas pick
    p.mouse.click(*to_client(p, 'R'))
    p.wait_for_timeout(300)
    assert selected(p) == sorted([p.ids['L'], p.ids['R']])
    assert fields(p, 'show-offset-x', 'show-offset-y') == ['0', '0']
    assert note(p, 'group-move-note-show') == ['Moves the whole group', True, 'group']
    type_field(p, 'show-offset-y', 80)
    want = {'L': [0, 0, 0, 80], 'R': [2200, 0, 2200, 80]}
    assert pos(p, 'L', 'R') == want
    assert server_pos(p, 'L', 'R', want=want) == want


def test_a_loose_screen_has_no_note(pg):
    p = pg
    tab(p, 'pixel-map')
    p.locator(f'#layers-list .layer-item[data-layer-id="{p.ids["LOOSE"]}"]').click()
    p.wait_for_timeout(250)
    assert note(p, 'group-move-note') == ['', False, '']
    type_field(p, 'offset-x', 6100)
    assert pos(p, 'LOOSE', 'L') == {'LOOSE': [6100, 0, 6100, 0], 'L': [0, 0, 0, 0]}


def test_a_canvas_drag_after_a_list_pick_moves_the_whole_group(pg):
    p = pg
    tab(p, 'pixel-map')
    list_pick(p, 'R')
    zoom = p.evaluate("() => window.canvasRenderer.zoom")
    sx, sy = to_client(p, 'R')
    p.mouse.move(sx, sy)
    p.keyboard.down('Shift')
    p.mouse.down()
    p.mouse.move(sx + 10, sy + 10, steps=3)
    p.mouse.move(sx + 100, sy + 50, steps=6)
    p.mouse.up()
    p.keyboard.up('Shift')
    p.wait_for_timeout(600)
    got = pos(p, 'L', 'R')
    dx, dy = got['L'][0], got['L'][1]
    assert dx > 0 and dy > 0, (got, zoom)
    assert got['R'][:2] == [2200 + dx, dy], got
    assert selected(p) == sorted([p.ids['L'], p.ids['R']])
    assert note(p, 'group-move-note')[0] == 'Moves the whole group'


def test_the_3d_arrow_keys_after_a_list_pick_move_the_whole_group(pg):
    p = pg
    tab(p, '3d')
    p.wait_for_function("() => { const d = window.app._s3dDebug(); return d.loaded && d.screens.length === 3; }",
                        timeout=10000)
    list_pick(p, 'R')
    assert selected(p) == [p.ids['R']]
    ids = [p.ids['L'], p.ids['R']]
    before = p.evaluate("""(ids) => ids.map(id => window.app._s3dDebug().screens.find(s => s.id === id).placement)""",
                        ids)
    p.mouse.move(5, 5)
    p.keyboard.press('ArrowRight')
    p.wait_for_function("""(ids) => ids.every(id => {
        const l = window.app.project.layers.find(x => x.id === id); return !!(l && l.stage3d); })""",
                        arg=ids, timeout=5000)
    after = p.evaluate("(ids) => ids.map(id => window.app.project.layers.find(x => x.id === id).stage3d)", ids)
    # both moved, by the same step: the wall keeps its shape
    moved = [[after[i][k] - before[i][k] for k in 'xyz'] for i in range(2)]
    assert max(abs(v) for v in moved[0]) == pytest.approx(25.4, abs=0.01), (before, after)
    assert moved[1] == pytest.approx(moved[0], abs=0.01), (before, after)
    tab(p, 'pixel-map')


# ── what follows the move ────────────────────────────────────────────────

def test_one_undo_puts_a_list_picked_member_back(pg):
    p = pg
    tab(p, 'pixel-map')
    list_pick(p, 'R')
    before = steps(p)
    type_field(p, 'offset-y', 500)
    assert pos(p, 'L', 'R') == {'L': [0, 0, 0, 0], 'R': [2200, 500, 2200, 500]}
    assert steps(p) == before + 1
    undo(p)
    want = {'L': [0, 0, 0, 0], 'R': [2200, 0, 2200, 0]}
    assert pos(p, 'L', 'R') == want
    assert server_pos(p, 'L', 'R', want=want) == want
    # the fields read the screen put back, and it is still the one picked
    assert fields(p, 'offset-x', 'offset-y') == ['2200', '0']
    assert note(p, 'group-move-note')[0] == 'Moves only R in its group'


PATHS_JS = """(ids) => { const a = window.app;
    const L = a.project.layers.find(x => x.id === ids[0]);
    return {
        data: (L.customPortPaths || {})['1'] || [],
        power: (L.powerCustomPaths || {})['1'] || [],
        dataResolved: a.getResolvedPathPanels(L, (L.customPortPaths || {})['1'] || [], 'data').map(r => r.layer.name),
        powerResolved: a.getResolvedPathPanels(L, (L.powerCustomPaths || {})['1'] || []).map(r => r.layer.name),
    }; }"""

SERVER_PATHS_JS = """async (id) => { const p = await fetch('/api/project').then(r => r.json());
    const L = p.layers.find(x => x.id === id);
    return {data: (L.customPortPaths || {})['1'] || [], power: (L.powerCustomPaths || {})['1'] || []}; }"""


def test_the_custom_runs_across_the_members_survive_the_move(pg):
    p = pg
    ids = [p.ids['L'], p.ids['R']]
    before = p.evaluate(PATHS_JS, ids)
    assert before['dataResolved'] == ['L', 'L', 'R', 'R'], before
    assert before['powerResolved'] == ['L', 'R'], before
    tab(p, 'pixel-map')
    list_pick(p, 'R')
    type_field(p, 'offset-x', 3000)
    tab(p, 'show-look')
    list_pick(p, 'R')
    type_field(p, 'show-offset-y', 600)
    assert pos(p, 'L', 'R') == {'L': [0, 0, 0, 0], 'R': [3000, 0, 3000, 600]}
    p.wait_for_timeout(800)
    after = p.evaluate(PATHS_JS, ids)
    assert after == before, after
    served = p.evaluate(SERVER_PATHS_JS, p.ids['L'])
    assert served == {'data': before['data'], 'power': before['power']}, served
    # and the Data and Power tabs still draw them
    for mode in ('data-flow', 'power'):
        tab(p, mode)
        assert p.evaluate(PATHS_JS, ids) == before


def test_bars_that_no_longer_fit_are_flagged_after_the_move(pg):
    p = pg
    tab(p, 'rigging')
    group_pick(p)
    p.evaluate("""() => { const a = window.app;
        a._riggingWithGroups(a._riggingScreens()).forEach(l => { l.riggingSizes = [2]; });
        a.refreshRiggingPanel(); }""")
    p.locator('#rigging-auto-btn').click()
    p.wait_for_timeout(400)
    # one row across the pair: 22 panels, 11 doubles, nothing wrong
    assert p.evaluate("() => window.app.riggingShownMisfits().length") == 0
    assert p.evaluate("() => document.getElementById('rigging-total-count').textContent") == '11'
    p.evaluate("() => { const h = document.getElementById('app-toast-host'); if (h) h.innerHTML = ''; }")
    tab(p, 'show-look')
    list_pick(p, 'R')
    type_field(p, 'show-offset-y', 200)
    # R steps down out of L's row: the bar over the seam no longer fits
    misfits = p.evaluate("() => window.app.riggingShownMisfits().map(m => m.layers.map(l => l.name))")
    assert misfits, misfits
    toasts = p.evaluate("() => [...document.querySelectorAll('#app-toast-host > div')].map(e => e.textContent)")
    assert any('no longer fit' in t for t in toasts), toasts
    # the bars themselves are left as they were, for Auto to fit again
    tab(p, 'rigging')
    assert p.locator('#rigging-fit-warning').is_visible()


# ── a second page follows ────────────────────────────────────────────────

NOT_WRITES = {'/api/log', '/api/port-assignments/resolve', '/api/port-assignments/link-check'}


def test_a_second_page_follows_the_move_and_writes_nothing(pg, pw_browser):
    a = pg
    ctx_b = _context(pw_browser)
    try:
        b = _open(ctx_b, a.e2e_server)
        b.wait_for_function("(id) => !!window.app.project.layers.find(l => l.id === id)", arg=a.ids['R'],
                            timeout=10000)
        writes = []

        def request(req):
            if req.method in ('GET', 'HEAD', 'OPTIONS'):
                return
            at = urlparse(req.url)
            if at.path.startswith('/api/') and at.path not in NOT_WRITES:
                writes.append(f'{req.method} {at.path}')
        b.on('request', request)
        tab(a, 'pixel-map')
        list_pick(a, 'R')
        type_field(a, 'offset-x', 2700)
        b.wait_for_function("(id) => window.app.project.layers.find(l => l.id === id).offset_x === 2700",
                            arg=a.ids['R'], timeout=10000)
        b.wait_for_timeout(1500)
        assert pos(b, 'L', 'R') == {'L': [0, 0, 0, 0], 'R': [2700, 0, 2700, 0]}
        assert writes == [], writes
        assert b.errors == [], b.errors
    finally:
        ctx_b.close()


# ── the guide ────────────────────────────────────────────────────────────

@pytest.mark.parametrize('run', range(3))
def test_the_guide_step_plays_on_its_own(pg, run):
    """The Advanced Guide's step, played alone as What's New's Show me plays
    it, from its own entry snapshot: the group opens in the list, its second
    screen is clicked and moved down and back on its own. Three times: a
    guide step passes first try, every time."""
    p = pg
    p.evaluate("""() => {
        const q = window.QuickStart, keys = q.tours().advanced
            .map(s => Object.keys(q.steps()).find(k => q.steps()[k] === s));
        if (keys[keys.indexOf('groupDrag') + 1] !== 'groupMove') throw new Error('out of place');
        if (q.steps().groupMove.since !== '1.7.0') throw new Error('since');
    }""")
    body = p.evaluate("() => window.QuickStart.steps().groupMove.body")
    assert len(body) <= 220 and body.count('. ') <= 1, body
    p.evaluate("() => { window.QuickStart.setSpeed(6); window.QuickStart.startSteps(['groupMove']); }")
    p.wait_for_function("""() => {
        const c = document.getElementById('qs-callout');
        return c && ['done', 'failed'].includes(c.getAttribute('data-qs-state'));
    }""", timeout=60000)
    state = p.evaluate("() => document.getElementById('qs-callout').getAttribute('data-qs-state')")
    note = p.locator('#qs-callout .qs-result').text_content()
    assert state == 'done', note
    assert 'moved down and back on its own' in note, note
    p.evaluate("() => window.QuickStart.end()")
    p.wait_for_function("() => !window.QuickStart.state().running && !window.QuickStart.state().visible")
    p.wait_for_timeout(300)
