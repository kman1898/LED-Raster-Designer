"""The 3D tab (app-stage3d.js) and the placement it stores on each screen.

The tab stands every screen Show Look shows on the stage, built from its own
cabinets with its Pixel Map drawing on the front. Each screen's place lives
on the layer as `stage3d` (mm and degrees, joint bends held to +/-15); the
camera, units and grid are the view's own, saved with the project.

What this file pins:

* The server's shape rule (app.sanitize_stage3d): clamps, junk dropped,
  idempotent, applied by the layer PUT, the add route and both project
  funnels; the view-state route keeps a bad camera out.
* The tab: it opens, the stage builds one quad per cabinet, blanked
  cabinets are left out and half cabinets are half size.
* A screen with no 3D place stands upright at its Show Look position, the
  lowest screen's bottom edge on the floor.
* Edits from the panel (typed lengths in feet, feet-and-inches, degrees,
  curves, a joint picked by clicking its seam) land on the layer and the
  server, survive a reload, and undo / redo as one step each.
* A group moves and turns as one wall; the curve stays each member's own.
* Copies are nudged, not stacked; old files load; no WebGL is survivable.

Run locally:
    python -m pytest tests/test_stage3d.py -v -p no:cacheprovider --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from conftest import settled  # noqa: E402

import app as app_module  # noqa: E402

MM_PER_PX = 500 / 128           # every screen here: 128 px, 500 mm cabinets
FT = 304.8


# ── 1. The server's shape rule (no browser) ──────────────────────────────

def test_sanitize_clamps_joints_and_drops_junk():
    raw = {
        'x': '1200.5', 'y': None, 'z': float('nan'), 'pitch': 10, 'yaw': True, 'roll': -5,
        'curveCol': 40, 'curveRow': -99,
        'jointsCol': {'2': 30, '03': -4, 'x': 3, '-1': 5, '4': 'bad'},
        'jointsRow': [1, 2],
        'stray': 'dropped',
    }
    out = app_module.sanitize_stage3d(raw)
    assert out == {
        'x': 1200.5, 'y': 0.0, 'z': 0.0, 'pitch': 10.0, 'yaw': 0.0, 'roll': -5.0,
        'curveCol': 15.0, 'curveRow': -15.0,
        'jointsCol': {'2': 15.0, '3': -4.0},
        'jointsRow': {},
    }, out
    # idempotent: what the funnels store is what they would store again
    assert app_module.sanitize_stage3d(out) == out
    assert app_module.sanitize_stage3d(None) is None
    assert app_module.sanitize_stage3d([1, 2]) is None


def test_normalize_stage3d_runs_over_the_project():
    project = {'layers': [
        {'id': 1, 'stage3d': {'curveCol': 20}},
        {'id': 2, 'stage3d': None},
        {'id': 3},
    ]}
    changed = app_module.normalize_stage3d(project)
    assert changed == [1, 2]
    assert project['layers'][0]['stage3d']['curveCol'] == 15.0
    assert 'stage3d' not in project['layers'][1]
    assert 'stage3d' not in project['layers'][2]
    assert app_module.normalize_stage3d(project) == []


def test_camera_sanitize():
    ok = app_module.sanitize_stage3d_camera(
        {'mode': 'ortho', 'position': [1, 2, 3], 'target': ['4', 5, 6], 'zoom': 0})
    assert ok == {'mode': 'ortho', 'position': [1.0, 2.0, 3.0],
                  'target': [4.0, 5.0, 6.0], 'zoom': 1.0}
    assert app_module.sanitize_stage3d_camera({'position': [1, 2], 'target': [0, 0, 0]}) is None
    assert app_module.sanitize_stage3d_camera('x') is None
    assert app_module.sanitize_stage3d_camera(
        {'mode': 'odd', 'position': [0, 0, 1], 'target': [0, 0, 0]})['mode'] == 'perspective'


def test_layer_put_clamps_and_null_removes(client_with_layer):
    client = client_with_layer
    layer_id = app_module.current_project['layers'][0]['id']
    resp = client.put(f'/api/layer/{layer_id}', json={'stage3d': {
        'x': 100, 'curveCol': 25, 'jointsRow': {'1': -40}}})
    assert resp.status_code == 200
    placed = resp.get_json()['stage3d']
    assert placed['curveCol'] == 15 and placed['jointsRow'] == {'1': -15} and placed['x'] == 100
    resp = client.put(f'/api/layer/{layer_id}', json={'stage3d': None})
    assert 'stage3d' not in resp.get_json()
    assert 'stage3d' not in app_module.current_project['layers'][0]


def test_add_route_and_restore_funnel_hold_the_shape(client):
    resp = client.post('/api/layer/add', json={
        'name': 'Copy', 'columns': 2, 'rows': 2,
        'stage3d': {'x': 5, 'curveRow': 50}})
    assert resp.get_json()['stage3d']['curveRow'] == 15
    project = client.get('/api/project').get_json()
    project['layers'][0]['stage3d'] = {'jointsCol': {'0': 99}}
    restored = client.put('/api/project', json=project).get_json()
    assert restored['layers'][0]['stage3d']['jointsCol'] == {'0': 15}
    # a file without the key loads without it
    del project['layers'][0]['stage3d']
    restored = client.put('/api/project', json=project).get_json()
    assert 'stage3d' not in restored['layers'][0]


def test_view_state_route(client):
    resp = client.put('/api/project/stage3d', json={
        'camera': {'mode': 'perspective', 'position': [0, 1000, 9000], 'target': [0, 1000, 0]},
        'units': 'm', 'grid': False})
    body = resp.get_json()
    assert body['stage3dUnits'] == 'm' and body['stage3dGrid'] is False
    assert body['stage3dCamera']['position'] == [0, 1000, 9000]
    assert app_module.current_project['stage3dCamera']['target'] == [0, 1000, 0]
    # a camera that does not hold its shape is refused; the old one stays
    body = client.put('/api/project/stage3d', json={
        'camera': {'position': 'nope'}, 'units': 'yards'}).get_json()
    assert body['stage3dCamera']['position'] == [0, 1000, 9000]
    assert body['stage3dUnits'] == 'm'


# ── 2. The tab in a browser ───────────────────────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project exactly as this module found it
    (see conftest.server_project_guard)."""


def _context(pw_browser, init=None):
    context = pw_browser.new_context(viewport={'width': 1500, 'height': 900})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    if init:
        context.add_init_script(init)
    return context


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = _context(pw_browser)
    pg = context.new_page()
    pg.errors = []
    pg.on('pageerror', lambda err: pg.errors.append(str(err)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    yield pg
    context.close()


# Exactly the screens asked for, through the real add route, every one with
# 128 px / 500 mm cabinets; history rebased so each test's edits are the
# only steps in it.
RESET_JS = """async (specs) => {
    const app = window.app;
    let project = await (await fetch('/api/project')).json();
    project.layers = [];
    project.groups = [];
    delete project.stage3dCamera;
    delete project.stage3dUnits;
    delete project.stage3dGrid;
    await fetch('/api/project', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(project),
    });
    const ids = [];
    for (const s of specs) {
        const made = await (await fetch('/api/layer/add', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(Object.assign({
                cabinet_width: 128, cabinet_height: 128,
                panel_width_mm: 500, panel_height_mm: 500,
            }, s)),
        })).json();
        ids.push(made.id);
    }
    app.project = await (await fetch('/api/project')).json();
    app.dedupeProjectLayers('stage3d_test_reset');
    if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
    app.resetHistory('Stage3D Test Reset');
    app.selectLayer(app.project.layers.find(l => l.id === ids[0]));
    app.updateUI();
    return ids;
}"""

TWO = [
    {'name': 'Upper', 'columns': 4, 'rows': 2, 'offset_x': 0, 'offset_y': 0},
    {'name': 'Lower', 'columns': 2, 'rows': 2, 'offset_x': 0, 'offset_y': 600},
]


def reset(page, specs=TWO):
    ids = page.evaluate(RESET_JS, specs)
    page.wait_for_timeout(300)
    return ids


def dbg(page):
    return page.evaluate('window.app._s3dDebug()')


def screen(page, layer_id):
    return next((s for s in dbg(page)['screens'] if s['id'] == layer_id), None)


def open_tab(page, mode):
    page.click(f'#view-tabs .view-tab[data-mode="{mode}"]')
    page.wait_for_timeout(150)


def open_3d(page, count):
    open_tab(page, '3d')
    got = settled(page, lambda: dbg(page),
                  lambda d: d['loaded'] and len(d['screens']) == count
                  and all(s['tex'] for s in d['screens']), 10000)
    assert got['loaded'], got
    assert len(got['screens']) == count, got
    return got


def stored(page, layer_id):
    return page.evaluate("""(id) => {
        const l = window.app.project.layers.find(x => x.id === id);
        return l ? (l.stage3d || null) : null;
    }""", layer_id)


def served(page, layer_id):
    return page.evaluate("""async (id) => {
        const p = await (await fetch('/api/project')).json();
        const l = p.layers.find(x => x.id === id);
        return l ? (l.stage3d || null) : null;
    }""", layer_id)


def type_field(page, field, value):
    page.fill(f'#{field}', value)
    page.press(f'#{field}', 'Enter')
    page.wait_for_timeout(400)


def history_len(page):
    return page.evaluate('window.app.history.length')


def undo(page):
    page.evaluate('window.app.undo()')
    page.wait_for_timeout(600)


def redo(page):
    page.evaluate('window.app.redo()')
    page.wait_for_timeout(600)


def test_the_tab_opens_and_builds_one_quad_per_cabinet(page):
    ids = reset(page)
    d = open_3d(page, 2)
    assert d['active'] and d['webgl'], d
    upper, lower = screen(page, ids[0]), screen(page, ids[1])
    assert (upper['quads'], upper['cols'], upper['rows']) == (8, 4, 2)
    assert (lower['quads'], lower['cols'], lower['rows']) == (4, 2, 2)
    assert upper['widthMm'] == 2000 and upper['heightMm'] == 1000
    # the front is the screen's own Pixel Map drawing, capped and scaled up
    # to at least 1024 on its long side
    assert max(upper['tex']) == 1024 and upper['tex'][0] == 2 * upper['tex'][1]
    assert page.evaluate("!!document.querySelector('#s3d-view canvas')")
    assert page.evaluate("getComputedStyle(document.getElementById('s3d-view')).display") != 'none'
    assert page.evaluate("getComputedStyle(document.getElementById('s3d-toolbar')).display") != 'none'
    # the 2D controls step aside; the grid and its origin mark are drawn
    assert page.evaluate("getComputedStyle(document.getElementById('btn-fit')).display") == 'none'
    assert d['gridLines'] >= 3
    assert page.errors == []


def test_leaving_the_tab_puts_the_canvas_back(page):
    reset(page)
    open_3d(page, 2)
    # while 3D is open the 2D canvas draws nothing (its redraws only nudge
    # the stage), so its frame counter stands still
    passes = page.evaluate("window.canvasRenderer._renderPass || 0")
    page.evaluate("window.canvasRenderer.render()")
    assert page.evaluate("window.canvasRenderer._renderPass || 0") == passes
    open_tab(page, 'pixel-map')
    assert page.evaluate("document.getElementById('s3d-view').hidden")
    assert page.evaluate("getComputedStyle(document.getElementById('btn-fit')).display") != 'none'
    assert page.evaluate("window.canvasRenderer.viewMode") == 'pixel-map'
    assert page.evaluate("window.canvasRenderer._renderPass || 0") > passes
    assert page.errors == []


def test_blanked_cabinets_are_left_out_and_half_cabinets_are_half_size(page):
    ids = reset(page, [{'name': 'Wall', 'columns': 4, 'rows': 3, 'offset_x': 0, 'offset_y': 0}])
    page.evaluate("""async (id) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === id);
        const pick = (r, c) => l.panels.find(p => p.row === r && p.col === c).id;
        await fetch(`/api/layer/${id}/panels/set_hidden`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({panels: [{id: pick(0, 0), hidden: true}, {id: pick(1, 2), hidden: true}]}),
        });
        // the whole last column half width
        await fetch(`/api/layer/${id}/panels/set_half_tile`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({panels: [0, 1, 2].map(r => ({id: pick(r, 3), halfTile: 'width'}))}),
        });
        app.project = await (await fetch('/api/project')).json();
        app.selectLayer(app.project.layers.find(x => x.id === id));
        app.updateUI();
    }""", ids[0])
    open_3d(page, 1)
    s = settled(page, lambda: screen(page, ids[0]), lambda v: v and v['quads'] == 10)
    assert s['quads'] == 12 - 2, s
    # three full columns of 500 mm and one half column
    assert s['widthMm'] == pytest.approx(3 * 500 + 250), s
    assert s['heightMm'] == pytest.approx(1500), s


def test_a_screen_with_no_3d_place_stands_at_its_show_look_position(page):
    ids = reset(page)
    open_3d(page, 2)
    upper, lower = screen(page, ids[0]), screen(page, ids[1])
    for s in (upper, lower):
        p = s['placement']
        assert not s['stored']
        assert (p['z'], p['pitch'], p['yaw'], p['roll'], p['curveCol'], p['curveRow']) == (0, 0, 0, 0, 0, 0)
    # the lowest screen's bottom edge is on the floor
    assert lower['world']['min'][1] == pytest.approx(0, abs=0.01)
    # Show Look's 600 px down is 600 x 500/128 mm down; up is up
    assert upper['placement']['y'] - lower['placement']['y'] == pytest.approx(
        600 * MM_PER_PX, abs=0.01)
    assert upper['placement']['x'] - lower['placement']['x'] == pytest.approx(1000 - 500, abs=0.01)
    # facing the audience: the front is at +Z, flat
    assert upper['world']['min'][2] == pytest.approx(0, abs=0.01)
    assert upper['world']['max'][2] == pytest.approx(0, abs=0.01)
    # nothing was written by looking
    assert stored(page, ids[0]) is None and served(page, ids[0]) is None


def test_typed_position_rotation_and_curve_persist_and_undo(page):
    ids = reset(page)
    open_3d(page, 2)
    upper = ids[0]
    start = history_len(page)

    type_field(page, 's3d-x', '10')
    assert stored(page, upper)['x'] == pytest.approx(10 * FT)
    type_field(page, 's3d-z', "-12' 6\"")
    assert stored(page, upper)['z'] == pytest.approx(-(12 * FT + 6 * 25.4))
    type_field(page, 's3d-yaw', '20+10')
    type_field(page, 's3d-curve-col', '7')
    page.click('[data-s3d-axis="pitch"] [data-s3d-step="-15"]')
    page.wait_for_timeout(400)
    want = stored(page, upper)
    assert want['yaw'] == 30 and want['curveCol'] == 7 and want['pitch'] == -15, want
    assert history_len(page) == start + 5, page.evaluate('window.app.history.map(h => h.action)')
    got = settled(page, lambda: served(page, upper), lambda v: v == want)
    assert got == want

    # the stage follows: the curve bends the ends forward
    s = settled(page, lambda: screen(page, upper), lambda v: v['placement'] == want)
    assert s['placement'] == want

    undo(page)
    assert stored(page, upper)['pitch'] == 0
    undo(page)
    assert stored(page, upper)['curveCol'] == 0
    assert settled(page, lambda: served(page, upper), lambda v: v and v['curveCol'] == 0)['curveCol'] == 0
    redo(page)
    redo(page)
    assert stored(page, upper) == want
    assert settled(page, lambda: served(page, upper), lambda v: v == want) == want

    # a reload reads it back from the server
    page.reload(wait_until='domcontentloaded')
    page.wait_for_timeout(2500)
    assert stored(page, upper) == want
    open_3d(page, 2)
    assert screen(page, upper)['placement'] == want
    assert screen(page, upper)['stored']


def test_metres_are_offered_and_kept_with_the_project(page):
    ids = reset(page)
    open_3d(page, 2)
    page.click('#s3d-units-m')
    page.wait_for_timeout(300)
    assert page.evaluate("document.querySelector('[data-s3d-unit]').textContent") == 'm'
    type_field(page, 's3d-y', '2.5')
    assert stored(page, ids[0])['y'] == pytest.approx(2500)
    units = settled(page, lambda: page.evaluate(
        "async () => (await (await fetch('/api/project')).json()).stage3dUnits"),
        lambda v: v == 'm')
    assert units == 'm'
    page.click('#s3d-units-ft')
    page.wait_for_timeout(300)
    assert page.evaluate("document.getElementById('s3d-y').value") == f'{2500 / FT:.2f}'


def test_curves_and_joints_clamp_and_a_seam_click_picks_its_joint(page):
    ids = reset(page, [{'name': 'Wall', 'columns': 6, 'rows': 3, 'offset_x': 0, 'offset_y': 0}])
    wall = ids[0]
    open_3d(page, 1)
    type_field(page, 's3d-curve-col', '40')
    assert stored(page, wall)['curveCol'] == 15
    assert page.evaluate("document.getElementById('s3d-curve-col').value") == '15'
    type_field(page, 's3d-curve-row', '-99')
    assert stored(page, wall)['curveRow'] == -15
    assert '5 joints, 75° in all' in page.evaluate("document.getElementById('s3d-arc-col').textContent")

    # the joint field waits for a seam
    assert page.evaluate("document.getElementById('s3d-joint-angle').disabled")
    page.click('[data-s3d-view="front"]')
    page.wait_for_timeout(500)
    at = page.evaluate(f"window.app._s3dDebugSeam({wall}, 'col', 2)")
    assert at, 'the seam is not on the page'
    page.mouse.click(at[0], at[1])
    page.wait_for_timeout(300)
    assert dbg(page)['joint'] == {'layerId': wall, 'axis': 'col', 'index': 2}
    assert not page.evaluate("document.getElementById('s3d-joint-angle').disabled")
    assert 'columns 3 and 4' in page.evaluate("document.getElementById('s3d-joint-label').textContent")
    type_field(page, 's3d-joint-angle', '30')
    assert stored(page, wall)['jointsCol'] == {'2': 15}
    type_field(page, 's3d-joint-angle', '-4')
    assert stored(page, wall)['jointsCol'] == {'2': -4}
    assert '(1 set alone)' in page.evaluate("document.getElementById('s3d-arc-col').textContent")
    assert settled(page, lambda: served(page, wall),
                   lambda v: v and v['jointsCol'] == {'2': -4})['jointsCol'] == {'2': -4}

    # the server holds the line too, whatever a client sends
    resp = page.evaluate("""async (id) => {
        const r = await fetch(`/api/layer/${id}`, {method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({stage3d: {curveCol: 80, jointsRow: {'0': -60}}})});
        return (await r.json()).stage3d;
    }""", wall)
    assert resp['curveCol'] == 15 and resp['jointsRow'] == {'0': -15}

    # clearing the joint goes back to the screen's own figure
    page.click('#s3d-joint-clear')
    page.wait_for_timeout(300)
    assert stored(page, wall)['jointsCol'] == {}


def test_click_selects_and_selection_follows_the_screens_list(page):
    ids = reset(page)
    open_3d(page, 2)
    page.click('[data-s3d-view="front"]')
    page.wait_for_timeout(500)
    at = screen(page, ids[1])['at']
    page.mouse.click(at[0], at[1])
    page.wait_for_timeout(400)
    assert page.evaluate('window.app.currentLayer.id') == ids[1]
    assert page.evaluate("document.getElementById('s3d-screen-name').textContent") == 'Lower'
    # and the other way: the Screens list's selection reaches the panel
    page.evaluate(f"window.app.setSelectedLayersByIds([{ids[0]}], {ids[0]})")
    got = settled(page, lambda: page.evaluate("document.getElementById('s3d-screen-name').textContent"),
                  lambda v: v == 'Upper')
    assert got == 'Upper'


def test_dragging_a_selected_screen_moves_it_in_one_step(page):
    ids = reset(page)
    open_3d(page, 2)
    page.click('[data-s3d-view="top"]')
    page.wait_for_timeout(500)
    before = screen(page, ids[0])['placement']
    camera = dbg(page)['camera']
    start = history_len(page)
    at = screen(page, ids[0])['at']
    page.mouse.move(at[0], at[1])
    page.mouse.down()
    for step in range(1, 9):
        page.mouse.move(at[0] + step * 10, at[1])
        page.wait_for_timeout(20)
    page.mouse.up()
    page.wait_for_timeout(500)
    after = stored(page, ids[0])
    assert after, 'the drag stored no placement'
    assert after['x'] > before['x'] + 50, (before, after)
    assert after['y'] == pytest.approx(before['y'], abs=0.01)
    assert history_len(page) == start + 1
    # the press moved the screen, not the camera
    assert dbg(page)['camera'] == camera
    undo(page)
    assert stored(page, ids[0]) is None


def test_a_group_moves_and_turns_as_one_wall(page):
    ids = reset(page, [
        {'name': 'Left', 'columns': 2, 'rows': 2, 'offset_x': 0, 'offset_y': 0},
        {'name': 'Right', 'columns': 2, 'rows': 2, 'offset_x': 256, 'offset_y': 0},
    ])
    # Matching processing settings, so grouping needs no settings dialog
    # (the way tests/test_screen_groups_ui.py builds its walls).
    page.evaluate("""(ids) => window.app.project.layers.filter(l => ids.includes(l.id))
        .forEach(l => { l.processorType = 'brompton'; l.bitDepth = 10; l.frameRate = 60; })""", ids)
    page.evaluate(f"window.app.setSelectedLayersByIds({ids}, {ids[0]})")
    # not awaited: a settings dialog would hold the promise open
    page.evaluate("() => { window.app.groupSelectedLayers(); }")
    grouped = settled(page, lambda: page.evaluate(
        f"window.app.project.layers.find(l => l.id === {ids[1]}).group_id"), bool)
    assert grouped, 'the two screens did not group'
    assert not page.evaluate("""() => { const m = document.getElementById('group-settings-modal');
        return !!m && getComputedStyle(m).display !== 'none'; }""")
    page.evaluate(f"window.app.selectLayer(window.app.project.layers.find(l => l.id === {ids[0]}))")
    open_3d(page, 2)
    a0, b0 = screen(page, ids[0])['placement'], screen(page, ids[1])['placement']
    gap = b0['x'] - a0['x']
    assert gap == pytest.approx(1000)

    type_field(page, 's3d-z', '5')
    a, b = stored(page, ids[0]), stored(page, ids[1])
    assert a['z'] == pytest.approx(5 * FT) and b['z'] == pytest.approx(5 * FT)
    assert b['x'] - a['x'] == pytest.approx(gap)

    start = history_len(page)
    page.click('[data-s3d-axis="yaw"] [data-s3d-step="90"]')
    page.wait_for_timeout(500)
    assert history_len(page) == start + 1
    a, b = stored(page, ids[0]), stored(page, ids[1])
    assert a['yaw'] == 90 and b['yaw'] == pytest.approx(90)
    # turned about the edited screen's centre: the peer went from +X to -Z
    assert b['x'] == pytest.approx(a['x'], abs=0.01)
    assert b['z'] - a['z'] == pytest.approx(-gap, abs=0.01)

    # the curve is each member's own
    type_field(page, 's3d-curve-col', '6')
    assert stored(page, ids[0])['curveCol'] == 6
    assert stored(page, ids[1])['curveCol'] == 0
    assert settled(page, lambda: served(page, ids[1]),
                   lambda v: v and v['yaw'] == pytest.approx(90))['yaw'] == pytest.approx(90)


def test_a_duplicate_is_nudged_not_stacked(page):
    ids = reset(page, [{'name': 'Wall', 'columns': 2, 'rows': 2, 'offset_x': 0, 'offset_y': 0}])
    open_3d(page, 1)
    type_field(page, 's3d-x', '3')
    src = stored(page, ids[0])
    page.evaluate("window.app.duplicateLayer(window.app.currentLayer)")
    page.wait_for_timeout(1200)
    copy_layer = page.evaluate(f"""() => window.app.project.layers.find(l => l.id !== {ids[0]})""")
    assert copy_layer, 'no copy was made'
    placed = copy_layer['stage3d']
    assert placed['x'] == pytest.approx(src['x'] + 50 * MM_PER_PX, abs=0.01)
    assert placed['y'] == pytest.approx(src['y'] - 50 * MM_PER_PX, abs=0.01)
    assert settled(page, lambda: served(page, copy_layer['id']), lambda v: v == placed) == placed


def test_reset_puts_the_screen_back_at_its_show_look_place(page):
    ids = reset(page)
    open_3d(page, 2)
    type_field(page, 's3d-x', '20')
    assert stored(page, ids[0])
    page.click('#s3d-reset')
    page.wait_for_timeout(500)
    assert not stored(page, ids[0])
    assert settled(page, lambda: served(page, ids[0]), lambda v: v is None) is None
    s = settled(page, lambda: screen(page, ids[0]), lambda v: not v['stored'])
    assert not s['stored']


def test_an_old_project_without_3d_data_loads(page):
    ids = reset(page)
    page.evaluate("""async () => {
        const app = window.app;
        const p = await (await fetch('/api/project')).json();
        p.layers.forEach(l => { delete l.stage3d; });
        p.layers[1].stage3d = {curveCol: 'oops', jointsCol: {'1': 77}};
        delete p.stage3dCamera;
        const r = await fetch('/api/project', {method: 'PUT',
            headers: {'Content-Type': 'application/json'}, body: JSON.stringify(p)});
        app.project = await r.json();
        app.dedupeProjectLayers('stage3d_old_file');
        app.resetHistory('Old file');
        app.selectLayer(app.project.layers[0]);
        app.updateUI();
    }""")
    d = open_3d(page, 2)
    assert d['failed'] == '' and page.errors == []
    assert not screen(page, ids[0])['stored']
    healed = served(page, ids[1])
    assert healed['curveCol'] == 0 and healed['jointsCol'] == {'1': 15}


def test_the_camera_is_saved_with_the_project(page):
    reset(page)
    open_3d(page, 2)
    steps = history_len(page)
    page.click('#s3d-mode-ortho')
    page.click('[data-s3d-view="top"]')
    page.wait_for_timeout(900)
    cam = dbg(page)['camera']
    assert cam['mode'] == 'ortho'
    saved = settled(page, lambda: page.evaluate(
        "async () => (await (await fetch('/api/project')).json()).stage3dCamera"),
        lambda v: v and v['mode'] == 'ortho' and v['position'] == cam['position'])
    assert saved['position'] == cam['position'] and saved['target'] == cam['target']
    # the camera is view state: no undo step for it
    assert history_len(page) == steps
    page.reload(wait_until='domcontentloaded')
    page.wait_for_timeout(2500)
    open_3d(page, 2)
    back = settled(page, lambda: dbg(page)['camera'], lambda v: v and v['mode'] == 'ortho')
    assert back['mode'] == 'ortho'
    assert back['position'] == pytest.approx(cam['position'], abs=0.05)
    assert page.evaluate("document.getElementById('s3d-mode-ortho').classList.contains('active')")


def test_no_webgl_says_so_and_the_panel_still_places(e2e_server, pw_browser):
    no_gl = """(() => {
        const real = HTMLCanvasElement.prototype.getContext;
        HTMLCanvasElement.prototype.getContext = function (kind, ...rest) {
            if (/webgl/i.test(String(kind))) return null;
            return real.call(this, kind, ...rest);
        };
    })();"""
    context = _context(pw_browser, no_gl)
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda err: errors.append(str(err)))
    try:
        pg.goto(e2e_server, wait_until='domcontentloaded')
        pg.wait_for_timeout(2000)
        ids = pg.evaluate(RESET_JS, TWO)
        pg.click('#view-tabs .view-tab[data-mode="3d"]')
        d = settled(pg, lambda: pg.evaluate('window.app._s3dDebug()'),
                    lambda v: v['loaded'] and len(v['screens']) == 2, 10000)
        assert d['loaded'] and not d['webgl'], d
        assert 'WebGL' in d['message'], d
        pg.fill('#s3d-x', '4')
        pg.press('#s3d-x', 'Enter')
        pg.wait_for_timeout(400)
        assert pg.evaluate(f"window.app.project.layers.find(l => l.id === {ids[0]}).stage3d.x") \
            == pytest.approx(4 * FT)
        # and the rest of the app carries on
        pg.click('#view-tabs .view-tab[data-mode="pixel-map"]')
        pg.wait_for_timeout(200)
        assert errors == []
    finally:
        context.close()


def test_switching_through_every_tab_raises_nothing(page):
    reset(page)
    for mode in ['pixel-map', 'cabinet-id', 'show-look', 'data-flow', 'power', '3d', 'pixel-map', '3d']:
        open_tab(page, mode)
        page.wait_for_timeout(150)
    assert page.errors == []
    page.wait_for_timeout(300)
    assert dbg(page)['active']
