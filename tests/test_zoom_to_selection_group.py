"""1:1 (Zoom to Selection) frames a whole grouped wall.

The owner's report (2026-11-16): "1:1 on a group needs to show the whole
group". A click on a grouped screen on the canvas selects the whole group,
but the toolbar's 1:1 button (and Ctrl/Cmd+Shift+2) framed only the one
member that was clicked.

  * Whole group selected (a canvas click): 1:1 frames every member the view
    draws, each at its own canvas's workspace position, so a group whose
    members sit on two canvases is framed whole too.
  * A hidden member is left out, the way the group's label leaves it out.
  * One member picked on its own in the Screens list: 1:1 frames just it.
  * Several separate screens selected: 1:1 frames all of them.

Run locally:
    python -m pytest tests/test_zoom_to_selection_group.py -n 4 --dist loadfile
"""

import json

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


QUIET = "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}"
UNAVAILABLE = json.dumps({'ok': False, 'cancelled': True})

# A, B, C: three 4 x 4 walls of 200 px cabinets standing side by side
# (800 px each), grouped as WALL. LOOSE stands well apart. With opts.split,
# C sits on a second canvas whose workspace starts at x 9000.
SEED_JS = """async (opts) => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    proj.canvases = proj.canvases.slice(0, 1); proj.active_canvas_id = proj.canvases[0].id;
    Object.assign(proj.canvases[0], {workspace_x: 0, workspace_y: 0,
        raster_width: 8000, raster_height: 2000, show_raster_width: 8000, show_raster_height: 2000});
    delete proj.port_assignments; delete proj.pullSheet; delete proj.pullSheetEdits;
    delete proj.binder; delete proj.groupNameDisplay; delete proj.groupNameDisplayByView;
    delete proj.riggingTool;
    await j('PUT', '/api/project', proj);
    const base = {columns: 4, rows: 4, cabinet_width: 200, cabinet_height: 200, panelWatts: 200,
                  flowPattern: 'tl-h', powerVoltage: 208, powerAmperage: 20, powerFlowPattern: 'tl-v',
                  powerOrganized: true, processorType: 'novastar-armor', bitDepth: 8, frameRate: 60};
    const add = (b) => j('POST', '/api/layer/add', {...base, ...b});
    await add({name: 'A', offset_x: 0, offset_y: 0});
    await add({name: 'B', offset_x: 800, offset_y: 0});
    await add({name: 'C', offset_x: 1600, offset_y: 0});
    await add({name: 'LOOSE', offset_x: 6000, offset_y: 1000});
    let p = await j('GET', '/api/project');
    const f = n => p.layers.find(l => l.name === n);
    const A = f('A'), B = f('B'), C = f('C');
    A.group_id = B.group_id = C.group_id = 'gz';
    p.groups = [{id: 'gz', name: 'WALL', layer_ids: [A.id, B.id, C.id],
                 canvas_id: A.canvas_id, routeDataAsOne: false}];
    if (opts.split) {
        p.canvases.push(Object.assign(JSON.parse(JSON.stringify(p.canvases[0])),
            {id: 'c_zoom2', name: 'Second', workspace_x: 9000, workspace_y: 0}));
        C.canvas_id = 'c_zoom2';
        C.offset_x = 0;
    }
    if (opts.hideC) C.visible = false;
    await j('PUT', '/api/project', p);
    p = await j('GET', '/api/project');
    app.project = p;
    app.dedupeProjectLayers('zoom_to_selection_group');
    app.setGroupExpanded('gz', true);
    app.selectLayer(app.project.layers.find(l => l.name === 'LOOSE'));
    app.renderLayers();
    window.canvasRenderer.render();
    app.resetHistory('Zoom Group Seed');
    return Object.fromEntries(app.project.layers.map(l => [l.name, l.id]));
}"""


def _context(pw_browser):
    ctx = pw_browser.new_context(viewport={'width': 1700, 'height': 1000})
    ctx.add_init_script(QUIET)
    for name in ('save-file', 'open-file', 'select-directory'):
        ctx.route(f'**/api/native-dialog/{name}', lambda route: route.fulfill(
            status=200, content_type='application/json', body=UNAVAILABLE))
    return ctx


def _open(e2e_server, pw_browser, **opts):
    ctx = _context(pw_browser)
    page = ctx.new_page()
    page.errors = []
    page.on('pageerror', lambda e: page.errors.append(str(e)))
    page.goto(e2e_server, wait_until='domcontentloaded')
    page.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)
    page.wait_for_timeout(1000)
    page.evaluate("() => { const s = document.querySelector('#start-page'); if (s) s.style.display = 'none'; }")
    page.ids = page.evaluate(SEED_JS, opts)
    page.wait_for_timeout(300)
    return ctx, page


@pytest.fixture()
def pg(e2e_server, pw_browser):
    ctx, page = _open(e2e_server, pw_browser)
    yield page
    ctx.close()
    assert not page.errors, page.errors


@pytest.fixture()
def pg_split(e2e_server, pw_browser):
    ctx, page = _open(e2e_server, pw_browser, split=True)
    yield page
    ctx.close()
    assert not page.errors, page.errors


@pytest.fixture()
def pg_hidden(e2e_server, pw_browser):
    ctx, page = _open(e2e_server, pw_browser, hideC=True)
    yield page
    ctx.close()
    assert not page.errors, page.errors


# ── gestures ─────────────────────────────────────────────────────────────

def fit(p):
    p.evaluate("() => window.canvasRenderer.fitToView()")
    p.wait_for_timeout(100)


def canvas_click(p, name, modifier=None):
    """A plain (or modified) click on the middle of the screen as drawn."""
    fit(p)
    pt = p.evaluate("""(id) => {
        const app = window.app, r = window.canvasRenderer;
        const l = app.project.layers.find(x => x.id === id);
        const c = (app.project.canvases || []).find(x => x.id === l.canvas_id) || {};
        const rect = r.canvas.getBoundingClientRect();
        const x = (c.workspace_x || 0) + l.offset_x + l.columns * l.cabinet_width / 2;
        const y = (c.workspace_y || 0) + l.offset_y + l.rows * l.cabinet_height / 2;
        return {x: rect.left + x * r.zoom + r.panX, y: rect.top + y * r.zoom + r.panY};
    }""", p.ids[name])
    if modifier:
        p.keyboard.down(modifier)
    p.mouse.click(pt['x'], pt['y'])
    if modifier:
        p.keyboard.up(modifier)
    p.wait_for_timeout(250)


def list_pick(p, name):
    """A plain click on the screen's own row in the expanded group."""
    p.evaluate("() => { window.app.setGroupExpanded('gz', true); }")
    p.locator(f'#layers-list .layer-item[data-layer-id="{p.ids[name]}"]').click()
    p.wait_for_timeout(250)


def press_one_to_one(p):
    fit(p)   # start from somewhere else, so the button has to move the view
    p.locator('#btn-zoom-actual').click()
    p.wait_for_timeout(150)


def shortcut_one_to_one(p):
    fit(p)
    p.evaluate("() => document.activeElement && document.activeElement.blur && document.activeElement.blur()")
    p.keyboard.press('Control+Shift+Digit2')
    p.wait_for_timeout(150)


# ── reads ────────────────────────────────────────────────────────────────

def view(p, *names):
    """Each named screen's rectangle in canvas pixels, plus the canvas size."""
    return p.evaluate("""(ids) => {
        const app = window.app, r = window.canvasRenderer;
        const rects = {};
        Object.entries(ids).forEach(([name, id]) => {
            const l = app.project.layers.find(x => x.id === id);
            const c = (app.project.canvases || []).find(x => x.id === l.canvas_id) || {};
            const x = (c.workspace_x || 0) + l.offset_x, y = (c.workspace_y || 0) + l.offset_y;
            const w = l.columns * l.cabinet_width, h = l.rows * l.cabinet_height;
            rects[name] = [x * r.zoom + r.panX, y * r.zoom + r.panY,
                           (x + w) * r.zoom + r.panX, (y + h) * r.zoom + r.panY];
        });
        return {rects, w: r.canvas.width, h: r.canvas.height, zoom: r.zoom,
                selected: [...app.selectedLayerIds].length};
    }""", {n: p.ids[n] for n in names})


def assert_framed(v, names, others=()):
    """Every named rectangle inside the viewport, their union centered and
    filling 90% of the viewport on its tighter axis; every other named
    rectangle not wholly inside."""
    for n in names:
        x1, y1, x2, y2 = v['rects'][n]
        assert x1 >= -0.5 and y1 >= -0.5 and x2 <= v['w'] + 0.5 and y2 <= v['h'] + 0.5, (n, v)
    ux1 = min(v['rects'][n][0] for n in names)
    uy1 = min(v['rects'][n][1] for n in names)
    ux2 = max(v['rects'][n][2] for n in names)
    uy2 = max(v['rects'][n][3] for n in names)
    assert abs((ux1 + ux2) / 2 - v['w'] / 2) < 1, v
    assert abs((uy1 + uy2) / 2 - v['h'] / 2) < 1, v
    fill = max((ux2 - ux1) / v['w'], (uy2 - uy1) / v['h'])
    assert abs(fill - 0.9) < 0.01, (fill, v)
    for n in others:
        x1, y1, x2, y2 = v['rects'][n]
        inside = x1 >= -0.5 and y1 >= -0.5 and x2 <= v['w'] + 0.5 and y2 <= v['h'] + 0.5
        assert not inside, (n, v)


# ── tests ────────────────────────────────────────────────────────────────

def test_canvas_click_on_a_member_then_one_to_one_frames_the_whole_group(pg):
    canvas_click(pg, 'B')
    assert pg.evaluate("() => window.app.selectedLayerIds.size") == 3
    press_one_to_one(pg)
    assert_framed(view(pg, 'A', 'B', 'C', 'LOOSE'), ['A', 'B', 'C'], others=['LOOSE'])


def test_the_shortcut_frames_the_whole_group_too(pg):
    canvas_click(pg, 'C')
    shortcut_one_to_one(pg)
    assert_framed(view(pg, 'A', 'B', 'C', 'LOOSE'), ['A', 'B', 'C'], others=['LOOSE'])


def test_a_member_picked_in_the_screens_list_is_framed_alone(pg):
    canvas_click(pg, 'B')
    list_pick(pg, 'B')
    assert pg.evaluate("() => window.app._listPickedMember() && window.app._listPickedMember().name") == 'B'
    press_one_to_one(pg)
    assert_framed(view(pg, 'A', 'B', 'C'), ['B'], others=['A', 'C'])
    # and a canvas click on the wall afterwards is the whole group again
    canvas_click(pg, 'A')
    press_one_to_one(pg)
    assert_framed(view(pg, 'A', 'B', 'C', 'LOOSE'), ['A', 'B', 'C'], others=['LOOSE'])


def test_a_loose_screen_is_framed_as_before(pg):
    canvas_click(pg, 'LOOSE')
    press_one_to_one(pg)
    assert_framed(view(pg, 'A', 'B', 'C', 'LOOSE'), ['LOOSE'], others=['A', 'B', 'C'])


def test_several_separate_screens_are_framed_together(pg):
    canvas_click(pg, 'LOOSE')
    canvas_click(pg, 'A', modifier='Control')
    assert pg.evaluate("() => window.app.selectedLayerIds.size") == 4
    press_one_to_one(pg)
    assert_framed(view(pg, 'A', 'B', 'C', 'LOOSE'), ['A', 'B', 'C', 'LOOSE'])


def test_a_group_on_two_canvases_is_framed_whole(pg_split):
    canvas_click(pg_split, 'A')
    assert pg_split.evaluate("() => window.app.selectedLayerIds.size") == 3
    press_one_to_one(pg_split)
    assert_framed(view(pg_split, 'A', 'B', 'C'), ['A', 'B', 'C'])


def test_a_hidden_member_is_left_out(pg_hidden):
    canvas_click(pg_hidden, 'A')
    press_one_to_one(pg_hidden)
    assert_framed(view(pg_hidden, 'A', 'B', 'C'), ['A', 'B'])
