"""The toolbar's Raster W x H shows the canvas of the screen just selected.

Owner's report, Mac app, 1.6.0 beta.5: "When a screen is selected in the
raster and is in canvas 1, if I select a screen in a different canvas the
raster size still shows the previous canvas."

Diagnosed path by path (2026-11-04, two canvases, 1920x1080 and
3840x2160): a plain click in the Screens list, a click on the canvas in
every view, Ctrl and Shift clicks in the list and Ctrl-click on the canvas
all made the screen's canvas active and the readout followed. Two did not:

- a click on a GROUP's header in the Screens list (setSelectedLayersByIds,
  which never activated a canvas): the whole wall on Canvas 2 was
  selected and the readout stayed on Canvas 1;
- on Pixel Map, a click on a cabinet of another SELECTED screen once a
  cabinet selection is open (canvas-input.js reachGesture keeps the
  selection and skipped the activation).

Both now activate the clicked screen's canvas with preserveSelection, so
the selection stays whole and the readout follows.

Run locally:
    python -m pytest tests/test_raster_follows_selection.py -v -n 4 --dist loadfile
"""

import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'src'))
sys.path.insert(0, HERE)

import app as app_module  # noqa: E402,F401
from conftest import settled  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


def _src(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as fh:
        return fh.read()


def test_both_paths_activate_the_canvas():
    sel = _src('src', 'static', 'js', 'app-selection.js')
    assert "import './app-selection.js';" in _src('src', 'static', 'js', 'main.js')
    body = sel.split('setSelectedLayersByIds(ids, primaryId = null) {', 1)[1].split('\n    }\n', 1)[0]
    assert "this._activateCanvasForLayer(this.currentLayer, { preserveSelection: true });" in body
    assert ("window.app._activateCanvasForLayer(clickedLayer, { preserveSelection: true });"
            in _src('src', 'static', 'js', 'canvas-input.js'))


# Canvas 1 (1920x1080) holds A1 and the group A-G (AG1 + AG2); Canvas 2
# (3840x2160, show 3000x1500) holds B1 and the group B-G (BG1 + BG2).
SEED_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = []; proj.beaches = [];
    delete proj.port_assignments; delete proj.pullSheet;
    proj.canvases = proj.canvases.slice(0, 1);
    Object.assign(proj.canvases[0], {name: 'One', raster_width: 1920, raster_height: 1080,
        show_raster_width: 1920, show_raster_height: 1080});
    const c1 = proj.canvases[0].id;
    proj.active_canvas_id = c1;
    await j('PUT', '/api/project', proj);
    const add = (name, x, cid) => j('POST', '/api/layer/add', {name, columns: 2, rows: 2,
        cabinet_width: 120, cabinet_height: 120, offset_x: x, offset_y: 300, canvas_id: cid});
    await add('A1', 200, c1); await add('AG1', 700, c1); await add('AG2', 1100, c1);
    const c2 = (await j('POST', '/api/canvas', {name: 'Two', raster_width: 3840, raster_height: 2160,
        show_raster_width: 3000, show_raster_height: 1500})).active_canvas_id;
    await add('B1', 200, c2); await add('BG1', 700, c2); await add('BG2', 1100, c2);
    await j('PUT', `/api/canvas/${c1}/active`);
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('raster_follows_seed');
    const by = (n) => app.project.layers.find(l => l.name === n);
    for (const pair of [['AG1', 'AG2'], ['BG1', 'BG2']]) {
        const ids = pair.map(n => by(n).id);
        app.setSelectedLayersByIds(ids, ids[0]);
        await app.groupSelectedLayers();
    }
    await app.setActiveCanvas(c1);
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('raster_follows_seed');
    app.project.active_canvas_id = c1;
    app.selectLayer(by('A1'));
    if (app.pixelMapSelection) app.pixelMapSelection.clear();
    app.syncRasterFromProject();
    app.renderLayers();
    window.canvasRenderer.render();
    window.canvasRenderer.fitToView();
    if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
    const ids = {};
    for (const n of ['A1', 'AG1', 'AG2', 'B1', 'BG1', 'BG2']) ids[n] = by(n).id;
    ids.c1 = c1; ids.c2 = c2;
    ids.groups = Object.fromEntries((app.project.groups || []).map(g =>
        [app.getGroupMembers(g).map(l => l.name).sort().join('+'), g.id]));
    return ids;
}"""

STATE_JS = """() => {
    const app = window.app;
    const name = (id) => (app.project.layers.find(l => l.id === id) || {}).name;
    return {
        active: app.project.active_canvas_id,
        w: document.getElementById('toolbar-raster-width').value,
        h: document.getElementById('toolbar-raster-height').value,
        current: app.currentLayer ? app.currentLayer.name : null,
        selected: [...(app.selectedLayerIds || [])].map(name).sort(),
    };
}"""

SERVER_ACTIVE_JS = """async () => (await (await fetch('/api/project')).json()).active_canvas_id"""

# A client point well inside the FIRST cabinet of the named screen: the
# centroid of every scanned point the renderer's own hit test gives to that
# cabinet. Not the screen's middle, where the current screen's name label
# takes the press (a label drag), and not an outer edge, which can be the
# canvas outline's drag band.
POINT_JS = """(name) => {
    const r = window.canvasRenderer;
    const layer = window.app.project.layers.find(l => l.name === name);
    const rect = r.canvas.getBoundingClientRect();
    const pts = [];
    for (let y = 4; y < rect.height; y += 4) for (let x = 4; x < rect.width; x += 4) {
        const wy = (y - r.panY) / r.zoom;
        const wx = r._unmirrorWorldX((x - r.panX) / r.zoom, wy);
        const hit = r.getPanelAt(wx, wy);
        if (hit && hit.layerId === layer.id && hit.panel && hit.panel.id === layer.panels[0].id) pts.push([x, y]);
    }
    if (!pts.length) return null;
    const cx = pts.reduce((s, p) => s + p[0], 0) / pts.length;
    const cy = pts.reduce((s, p) => s + p[1], 0) / pts.length;
    return {x: rect.left + cx, y: rect.top + cy};
}"""

ONE = ('1920', '1080')
TWO = {'pixel-map': ('3840', '2160'), 'cabinet-id': ('3840', '2160'),
       'show-look': ('3000', '1500'), 'data-flow': ('3000', '1500'), 'power': ('3000', '1500')}


def _cancelled(route):
    route.fulfill(status=200, content_type='application/json',
                  body=json.dumps({'ok': False, 'cancelled': True}))


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 1100})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    # No real Windows dialog may open on the owner's desktop.
    for path in ('save-file', 'open-file', 'select-directory'):
        pg.route(f'**/api/native-dialog/{path}', _cancelled)
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    yield pg, errors
    context.close()


def _seed(pg, view='pixel-map'):
    pg.locator('[data-mode="pixel-map"]').click()
    pg.wait_for_timeout(150)
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(300)
    if view != 'pixel-map':
        pg.locator(f'[data-mode="{view}"]').click()
        pg.wait_for_timeout(200)
        pg.evaluate("() => window.canvasRenderer.fitToView()")
        pg.wait_for_timeout(150)
    s = pg.evaluate(STATE_JS)
    assert (s['active'], s['w'], s['h'], s['current']) == (ids['c1'], *ONE, 'A1'), s
    return ids


def _expect(pg, ids, canvas, size, current, selected):
    want = {'active': ids[canvas], 'w': size[0], 'h': size[1],
            'current': current, 'selected': sorted(selected)}
    got = settled(pg, lambda: pg.evaluate(STATE_JS), lambda v: v == want)
    assert got == want, f'wanted {want}, got {got}'
    srv = settled(pg, lambda: pg.evaluate(SERVER_ACTIVE_JS), lambda v: v == ids[canvas])
    assert srv == ids[canvas], f'the server still has {srv} active'
    # and it stays that way once everything in flight has landed
    pg.wait_for_timeout(400)
    assert pg.evaluate(STATE_JS) == want


def _row(layer_id):
    return f'#layers-list .layer-item[data-layer-id="{layer_id}"] .layer-info'


def _click_screen(pg, name, modifier=None):
    pt = pg.evaluate(POINT_JS, name)
    assert pt, f'{name} is not on screen'
    if modifier:
        pg.keyboard.down(modifier)
    try:
        pg.mouse.click(pt['x'], pt['y'])
    finally:
        if modifier:
            pg.keyboard.up(modifier)


# ── the Screens list ─────────────────────────────────────────────────────

def test_list_click_on_a_screen_on_another_canvas(page):
    pg, _ = page
    ids = _seed(pg)
    pg.locator(_row(ids['B1'])).click()
    _expect(pg, ids, 'c2', TWO['pixel-map'], 'B1', ['B1'])
    # and back again
    pg.locator(_row(ids['A1'])).click()
    _expect(pg, ids, 'c1', ONE, 'A1', ['A1'])


def test_list_click_on_a_group_header_on_another_canvas(page):
    """The broken path: the group's header selected the wall on Canvas 2 and
    left Canvas 1 active, with its raster in the toolbar."""
    pg, _ = page
    ids = _seed(pg)
    gid = ids['groups']['BG1+BG2']
    pg.locator(f'#layers-list .screen-group[data-group-id="{gid}"] .screen-group-info').click()
    _expect(pg, ids, 'c2', TWO['pixel-map'], 'BG1', ['BG1', 'BG2'])
    gid = ids['groups']['AG1+AG2']
    pg.locator(f'#layers-list .screen-group[data-group-id="{gid}"] .screen-group-info').click()
    _expect(pg, ids, 'c1', ONE, 'AG1', ['AG1', 'AG2'])


def test_list_ctrl_click_adds_across_canvases(page):
    pg, _ = page
    ids = _seed(pg)
    pg.locator(_row(ids['B1'])).click(modifiers=['Control'])
    _expect(pg, ids, 'c2', TWO['pixel-map'], 'B1', ['A1', 'B1'])
    pg.locator(_row(ids['A1'])).click(modifiers=['Control'])
    # A1 taken out: B1 is what is left, on Canvas 2
    _expect(pg, ids, 'c2', TWO['pixel-map'], 'B1', ['B1'])


def test_list_shift_click_ranges_across_canvases(page):
    pg, _ = page
    ids = _seed(pg)
    pg.locator(_row(ids['B1'])).click(modifiers=['Shift'])
    got = settled(pg, lambda: pg.evaluate(STATE_JS), lambda v: v['current'] == 'B1')
    assert {'A1', 'B1'} <= set(got['selected']), got
    _expect(pg, ids, 'c2', TWO['pixel-map'], 'B1', got['selected'])


def test_list_click_on_the_one_selected_screen_changes_nothing(page):
    pg, _ = page
    ids = _seed(pg)
    pg.locator(_row(ids['A1'])).click()
    _expect(pg, ids, 'c1', ONE, 'A1', ['A1'])


# ── the canvas, every view ───────────────────────────────────────────────

@pytest.mark.parametrize('view', ['pixel-map', 'cabinet-id', 'show-look', 'data-flow', 'power'])
def test_canvas_click_on_a_screen_on_another_canvas(page, view):
    pg, _ = page
    ids = _seed(pg, view)
    _click_screen(pg, 'B1')
    _expect(pg, ids, 'c2', TWO[view], 'B1', ['B1'])
    _click_screen(pg, 'A1')
    _expect(pg, ids, 'c1', ONE, 'A1', ['A1'])


@pytest.mark.parametrize('view', ['pixel-map', 'show-look', 'data-flow'])
def test_canvas_ctrl_click_adds_across_canvases(page, view):
    pg, _ = page
    ids = _seed(pg, view)
    _click_screen(pg, 'B1', 'Control')
    _expect(pg, ids, 'c2', TWO[view], 'B1', ['A1', 'B1'])


def test_canvas_click_on_a_group_member_on_another_canvas(page):
    pg, _ = page
    ids = _seed(pg)
    _click_screen(pg, 'BG2')
    _expect(pg, ids, 'c2', TWO['pixel-map'], 'BG2', ['BG1', 'BG2'])


# ── Pixel Map: a cabinet on another selected screen ──────────────────────

def _select_both(pg, ids):
    pg.evaluate("(ids) => window.app.setSelectedLayersByIds(ids, ids[0])", [ids['A1'], ids['B1']])
    pg.wait_for_timeout(150)


def test_pixel_map_click_on_another_selected_screen_with_no_cabinets_open(page):
    """No cabinet selection open: the click narrows to that screen."""
    pg, _ = page
    ids = _seed(pg)
    _select_both(pg, ids)
    _expect(pg, ids, 'c1', ONE, 'A1', ['A1', 'B1'])
    _click_screen(pg, 'B1')
    _expect(pg, ids, 'c2', TWO['pixel-map'], 'B1', ['B1'])


@pytest.mark.parametrize('modifier', [None, 'Control'])
def test_pixel_map_cabinet_pick_on_another_selected_screen(page, modifier):
    """The other broken path: with a cabinet of A1 selected, a click on B1's
    cabinet is a cabinet pick (the selection stays A1 + B1), and it left
    Canvas 1 active. Now Canvas 2 is, with nothing dropped."""
    pg, _ = page
    ids = _seed(pg)
    _select_both(pg, ids)
    pg.evaluate("""(id) => { const a = window.app; const l = a.project.layers.find(x => x.id === id);
        a.selectOnlyPixelMapPanel(l.panels[0], l); }""", ids['A1'])
    pg.wait_for_timeout(150)
    assert pg.evaluate("() => window.app.pixelMapSelection.size") == 1
    _click_screen(pg, 'B1', modifier)
    _expect(pg, ids, 'c2', TWO['pixel-map'], 'A1', ['A1', 'B1'])
    keys = pg.evaluate("() => [...window.app.pixelMapSelection]")
    want_n = 2 if modifier else 1
    assert len(keys) == want_n, keys
    assert any(k.startswith(f"{ids['B1']}:") for k in keys), keys
    # and back to a cabinet of A1: Canvas 1 again
    pg.evaluate("() => window.canvasRenderer.render()")
    _click_screen(pg, 'A1')
    _expect(pg, ids, 'c1', ONE, 'A1', ['A1', 'B1'])


def test_no_page_errors(page):
    _, errors = page
    assert errors == [], errors
