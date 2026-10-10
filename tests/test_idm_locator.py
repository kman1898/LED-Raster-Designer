"""The IDM Locator tab (app-idm-locator.js, canvas-idm.js) and the module
marks it stores on each screen.

A cabinet is built from modules; the crew marks the bad one in this tab and
Output to Display puts the marks on a second monitor so the module can be
found on the real wall. Each screen keeps

    idm: {modulesX, modulesY, marks: {"col,row,mx,my": {style, color}}}

What this file pins:

* The server's shape rule (app.sanitize_idm): module counts 1..64, marks
  only on modules that exist (not off the cabinet grid, not off the module
  grid, not on a blanked cabinet), style and colour held, idempotent;
  applied by the layer PUT (after a column change), the panel routes, the
  add route and both project funnels; server-side copies keep the layout
  and drop the marks.
* The module geometry: cabinet px / modules with the remainder spread (no
  fractional pixel), a half cabinet keeps the modules inside it laid from
  the side that meets the wall, a blanked cabinet has none - the browser
  and the server agree cell for cell.
* The tab: it is the seventh, draws the Pixel Map raster, the module
  fields edit the selection (mixed shows '-'), a click toggles a mark, a
  drag paints or clears (the first module decides) as one undo step,
  colour and X marks survive the server, a reload, a load and undo/redo,
  a module change on a marked screen asks first and clears, a column
  shrink drops the marks that fall off, copies keep the layout but no
  marks, a locked screen cannot be marked, the locator list names the
  Cabinet ID view's own IDs, and an Output to Display of the view shows a
  mark the moment it is made.

Run locally:
    python -m pytest tests/test_idm_locator.py -v -p no:cacheprovider --browser chromium
"""

import json
import os
import sys
import urllib.request

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'src'))
sys.path.insert(0, HERE)

from conftest import settled  # noqa: E402

import app as app_module  # noqa: E402

MOD = 'Meta' if sys.platform == 'darwin' else 'Control'


# ── 1. The server's shape rule (no browser) ──────────────────────────────

def _layer(client, **extra):
    body = {'name': 'Wall', 'columns': 3, 'rows': 2,
            'cabinet_width': 128, 'cabinet_height': 128}
    body.update(extra)
    resp = client.post('/api/layer/add', json=body)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()


def _served(client, layer_id):
    return next(l for l in client.get('/api/project').get_json()['layers']
                if l['id'] == layer_id)


def test_sanitize_holds_counts_styles_colours_and_keys(client):
    layer = _layer(client)
    raw = {
        'modulesX': '2', 'modulesY': 2.9, 'stray': 1,
        'marks': {
            '0,0,1,1': {'style': 'x', 'color': '#ABC'},
            ' 2 , 1 , 0 , 0 ': {'style': 'odd', 'color': 'red'},
            '0,0,2,0': {'style': 'x'},           # off the module grid
            '3,0,0,0': {'style': 'x'},           # off the cabinet grid
            '0,2,0,0': {},                       # off the cabinet grid
            'a,b,c,d': {},
            '0,0,0': {},
            '1,1,0,0': 'not a mark',
        },
    }
    out = app_module.sanitize_idm(raw, layer)
    assert out == {
        'modulesX': 2, 'modulesY': 2,
        'marks': {
            '0,0,1,1': {'style': 'x', 'color': '#aabbcc'},
            '2,1,0,0': {'style': 'color', 'color': app_module.IDM_DEFAULT_COLOR},
        },
    }, out
    # idempotent: what the funnels store is what they would store again
    assert app_module.sanitize_idm(out, layer) == out
    # counts are clamped to 1..64; junk is 1
    assert app_module.sanitize_idm({'modulesX': 500, 'modulesY': -3}, layer)['modulesX'] == 64
    assert app_module.sanitize_idm({'modulesX': True, 'modulesY': 'x'}, layer) == \
        {'modulesX': 1, 'modulesY': 1, 'marks': {}}
    assert app_module.sanitize_idm({'modulesX': float('nan')}, layer)['modulesX'] == 1
    # not a block, or not a screen: removed
    assert app_module.sanitize_idm(None, layer) is None
    assert app_module.sanitize_idm([1], layer) is None
    assert app_module.sanitize_idm({'modulesX': 2}, dict(layer, type='image')) is None
    assert app_module.idm_color('#12AbCd') == '#12abcd'
    assert app_module.idm_color('12abcd') == '#12abcd'
    assert app_module.idm_color('#12abc') is None
    assert app_module.idm_color(None) is None


def test_module_edges_spread_the_remainder_and_never_split_a_pixel(client):
    layer = _layer(client, columns=1, rows=1, cabinet_width=100, cabinet_height=160)
    cells = app_module.idm_module_cells(layer, layer['panels'][0], 3, 3)
    widths = [c[4] for c in cells if c[1] == 0]
    heights = [c[5] for c in cells if c[0] == 0]
    assert widths == [33, 33, 34], widths
    assert heights == [53, 53, 54], heights
    assert all(float(v).is_integer() for c in cells for v in c[2:]), cells
    # one module is the whole cabinet
    assert app_module.idm_module_cells(layer, layer['panels'][0], 1, 1) == [(0, 0, 0.0, 0.0, 100.0, 160.0)]


def test_half_cabinets_keep_the_modules_inside_them(client):
    layer = _layer(client, columns=3, rows=1)
    ids = {p['col']: p['id'] for p in layer['panels']}
    # The last column half wide: it meets the wall on its left, so the full
    # cabinet is laid from the left and the cut is on the free (right) edge.
    # The first column half wide: it meets the wall on its right, the cut
    # is on its left.
    resp = client.post(f"/api/layer/{layer['id']}/panels/set_half_tile",
                       json={'panels': [{'id': ids[2], 'halfTile': 'width'},
                                        {'id': ids[0], 'halfTile': 'width'}]})
    layer = resp.get_json()['layer']
    panels = {p['col']: p for p in layer['panels']}
    keys = app_module.idm_module_keys(layer, 3, 1)

    def cells(col):
        p = panels[col]
        shown = {(q['row'], q['col']) for q in layer['panels'] if not q.get('hidden')}
        return app_module.idm_module_cells(layer, p, 3, 1, lambda r, c: (r, c) in shown)

    # 128 px in three: edges 0, 42, 85, 128. Half = 64 px.
    right = cells(2)
    assert [(c[0], c[4]) for c in right] == [(0, 42.0), (1, 22.0)], right
    left = cells(0)
    assert [(c[0], c[4]) for c in left] == [(1, 21.0), (2, 43.0)], left
    assert '2,0,2,0' not in keys and '0,0,0,0' not in keys
    assert {'2,0,0,0', '2,0,1,0', '0,0,1,0', '0,0,2,0'} <= keys


def test_blanked_cabinets_have_no_modules_and_lose_their_marks(client):
    layer = _layer(client)
    lid = layer['id']
    resp = client.put(f'/api/layer/{lid}', json={'idm': {
        'modulesX': 2, 'modulesY': 2,
        'marks': {'1,0,0,0': {'style': 'color', 'color': '#00ff00'},
                  '0,0,1,1': {'style': 'x', 'color': '#0000ff'}}}})
    assert len(resp.get_json()['idm']['marks']) == 2
    target = next(p for p in resp.get_json()['panels'] if p['col'] == 1 and p['row'] == 0)
    resp = client.post(f'/api/layer/{lid}/panels/set_hidden',
                       json={'panels': [{'id': target['id'], 'hidden': True}]})
    assert resp.get_json()['layer']['idm']['marks'] == {
        '0,0,1,1': {'style': 'x', 'color': '#0000ff'}}
    assert '1,0,0,0' not in app_module.idm_module_keys(_served(client, lid), 2, 2)
    # a mark sent onto the blanked cabinet is refused
    resp = client.put(f'/api/layer/{lid}', json={'idm': {
        'modulesX': 2, 'modulesY': 2, 'marks': {'1,0,1,1': {'style': 'x'}}}})
    assert resp.get_json()['idm']['marks'] == {}


def test_layer_put_drops_marks_a_column_or_module_change_leaves_on_nothing(client):
    layer = _layer(client)
    lid = layer['id']
    marks = {'0,0,0,0': {'style': 'color', 'color': '#ff0000'},
             '2,1,1,1': {'style': 'x', 'color': '#00ff00'},
             '1,0,1,0': {'style': 'color', 'color': '#0000ff'}}
    client.put(f'/api/layer/{lid}', json={'idm': {'modulesX': 2, 'modulesY': 2, 'marks': marks}})
    # Two columns: the third column's mark falls off with it.
    resp = client.put(f'/api/layer/{lid}', json={'columns': 2})
    assert set(resp.get_json()['idm']['marks']) == {'0,0,0,0', '1,0,1,0'}
    # One module across: module column 1 is gone.
    resp = client.put(f'/api/layer/{lid}', json={'idm': {
        'modulesX': 1, 'modulesY': 2, 'marks': resp.get_json()['idm']['marks']}})
    assert set(resp.get_json()['idm']['marks']) == {'0,0,0,0'}
    # null removes the block; a PUT without the key leaves it alone
    resp = client.put(f'/api/layer/{lid}', json={'name': 'Renamed'})
    assert resp.get_json()['idm']['modulesY'] == 2
    resp = client.put(f'/api/layer/{lid}', json={'idm': None})
    assert 'idm' not in resp.get_json()


def test_add_route_and_project_funnels_hold_the_shape(client):
    added = _layer(client, idm={'modulesX': 2, 'modulesY': 1,
                                'marks': {'0,0,0,0': {'style': 'x', 'color': '#00FF00'},
                                          '0,0,0,1': {'style': 'x'}}})
    assert added['idm'] == {'modulesX': 2, 'modulesY': 1,
                            'marks': {'0,0,0,0': {'style': 'x', 'color': '#00ff00'}}}
    project = client.get('/api/project').get_json()
    project['layers'][0]['idm'] = {'modulesX': 99, 'modulesY': 2,
                                   'marks': {'5,5,0,0': {}, '1,1,1,1': {'style': 'color', 'color': '#123456'}}}
    restored = client.put('/api/project', json=project).get_json()
    assert restored['layers'][0]['idm'] == {
        'modulesX': 64, 'modulesY': 2,
        'marks': {'1,1,1,1': {'style': 'color', 'color': '#123456'}}}
    # The save funnel does the same.
    project['layers'][0]['idm'] = {'modulesX': 2, 'modulesY': 2, 'marks': {'9,9,9,9': {}}}
    assert client.post('/api/project', json=project).status_code == 200
    assert app_module.current_project['layers'][0]['idm']['marks'] == {}
    # An older file without the key loads without it.
    del project['layers'][0]['idm']
    restored = client.put('/api/project', json=project).get_json()
    assert 'idm' not in restored['layers'][0]
    assert app_module.normalize_idm(restored) == []


def test_server_copies_keep_the_layout_and_drop_the_marks(client):
    layer = _layer(client)
    lid = layer['id']
    client.put(f'/api/layer/{lid}', json={'idm': {
        'modulesX': 2, 'modulesY': 2, 'marks': {'0,0,0,0': {'style': 'x', 'color': '#00ff00'}}}})
    # Duplicate Canvas
    assert client.post('/api/canvas/c1/duplicate').status_code == 200
    project = client.get('/api/project').get_json()
    copies = [l for l in project['layers'] if l['id'] != lid]
    assert len(copies) == 1
    assert copies[0]['idm'] == {'modulesX': 2, 'modulesY': 2, 'marks': {}}
    # Duplicate to another canvas
    resp = client.put(f'/api/layer/{lid}/canvas', json={'canvas_id': 'c2', 'mode': 'duplicate'})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    project = client.get('/api/project').get_json()
    copies = [l for l in project['layers'] if l['id'] != lid]
    assert len(copies) == 2 and all(c['idm']['marks'] == {} for c in copies)
    assert all((c['idm']['modulesX'], c['idm']['modulesY']) == (2, 2) for c in copies)
    # the original keeps its mark
    assert _served(client, lid)['idm']['marks'] == {'0,0,0,0': {'style': 'x', 'color': '#00ff00'}}
    # the helper: screens only
    image = {'type': 'image', 'idm': {'marks': {'x': 1}}}
    app_module.strip_copied_idm_marks(image)
    assert image['idm'] == {'marks': {'x': 1}}


# ── 2. The tab in a browser ───────────────────────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project exactly as this module found it
    (see conftest.server_project_guard)."""


def _new_page(pw_browser, url, **context_args):
    context = pw_browser.new_context(viewport={'width': 1500, 'height': 950}, **context_args)
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(url, wait_until='domcontentloaded')
    # This viewer's last mark style and colour start at the defaults.
    pg.evaluate("() => { localStorage.removeItem('lrdIdmMarkStyle'); localStorage.removeItem('lrdIdmMarkColor'); }")
    pg.reload(wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app.project && window.app.history", timeout=15000)
    pg.wait_for_timeout(800)
    return context, pg


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context, pg = _new_page(pw_browser, e2e_server)
    pg._errors = []
    pg.on('pageerror', lambda err: pg._errors.append(str(err)))
    yield pg
    context.close()


# One canvas 1920x1080 and two screens:
#   IdmA 3 x 2 cabinets of 128 at (0, 0)       -> 384 x 256
#   IdmB 2 x 2 cabinets of 160 at (600, 0)     -> 320 x 320
RESET_JS = """async () => {
    const put = (url, body) => fetch(url, {method: 'PUT',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    const post = (url, body) => fetch(url, {method: 'POST',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    let project = await (await fetch('/api/project')).json();
    const first = Object.assign({}, project.canvases[0], {
        raster_width: 1920, raster_height: 1080,
        show_raster_width: 1920, show_raster_height: 1080,
        workspace_x: 0, workspace_y: 0, visible: true});
    delete first.show_workspace_x; delete first.show_workspace_y;
    project.layers = []; project.groups = [];
    project.canvases = [first];
    project.active_canvas_id = first.id;
    await put('/api/project', project);
    await post('/api/layer/add', {name: 'IdmA', columns: 3, rows: 2,
        cabinet_width: 128, cabinet_height: 128, offset_x: 0, offset_y: 0, canvas_id: first.id});
    await post('/api/layer/add', {name: 'IdmB', columns: 2, rows: 2,
        cabinet_width: 160, cabinet_height: 160, offset_x: 600, offset_y: 0, canvas_id: first.id});
    window.app.closeAllOutputDisplays();
    window.app.loadProject();
    return first.id;
}"""


def reset_project(page):
    cid = page.evaluate(RESET_JS)
    page.wait_for_function(
        "() => window.app.project && (window.app.project.layers || []).length === 2"
        " && window.app.history && window.app.history.length === 1", timeout=10000)
    page.wait_for_timeout(500)
    open_tab(page)
    return cid


def open_tab(page):
    page.click('.view-tab[data-mode="idm"]')
    page.wait_for_function("() => window.canvasRenderer.viewMode === 'idm'")
    page.evaluate("() => { window.canvasRenderer.fitToView(); window.canvasRenderer.render(); }")
    page.wait_for_timeout(250)


def layer_of(page, name):
    return page.evaluate("""(name) => {
        const l = window.app.project.layers.find(x => x.name === name);
        return l ? JSON.parse(JSON.stringify(Object.assign({}, l, {panels: undefined}))) : null;
    }""", name)


def served_layer(page, name):
    return page.evaluate("""async (name) => {
        const p = await (await fetch('/api/project')).json();
        const l = p.layers.find(x => x.name === name);
        return l ? Object.assign({}, l, {panels: undefined}) : null;
    }""", name)


def idm_of(layer):
    return (layer or {}).get('idm')


def marks_of(layer):
    return (idm_of(layer) or {}).get('marks') or {}


def set_layout(page, name, mx, my):
    """The layout straight onto the layer through the app's own path."""
    page.evaluate("""([name, mx, my]) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.name === name);
        l.idm = {modulesX: mx, modulesY: my, marks: {}};
        app.updateLayers([l], true, 'Set Modules');
        window.canvasRenderer.render();
    }""", [name, mx, my])
    settled(page, lambda: idm_of(served_layer(page, name)),
            lambda v: v and v['modulesX'] == mx and v['modulesY'] == my)


# The client point at the centre of one module (no rotation on these).
POINT_JS = """([name, col, row, mx, my]) => {
    const app = window.app, r = window.canvasRenderer;
    const l = app.project.layers.find(x => x.name === name);
    const p = l.panels.find(q => q.col === col && q.row === row);
    const n = r.idmCounts(l);
    const c = r.idmModuleCells(l, p, n.x, n.y, r._idmVisibleLookup(l)).find(q => q.mx === mx && q.my === my);
    if (!c) return null;
    const {dx, dy} = r.getLayerRenderOffset(l);
    const {wx, wy} = r._layerCanvasOffset(l);
    const X = c.x + c.w / 2 + dx + wx, Y = c.y + c.h / 2 + dy + wy;
    const rect = r.canvas.getBoundingClientRect();
    return {x: rect.left + Math.round(r.panX) + X * r.zoom, y: rect.top + Math.round(r.panY) + Y * r.zoom};
}"""


def point(page, name, col, row, mx, my):
    pt = page.evaluate(POINT_JS, [name, col, row, mx, my])
    assert pt, f'no module {name} {col},{row},{mx},{my}'
    return pt


def click_module(page, name, col, row, mx, my):
    pt = point(page, name, col, row, mx, my)
    page.mouse.click(pt['x'], pt['y'])
    page.wait_for_timeout(150)


def history_len(page):
    return page.evaluate("() => window.app.historyIndex")


def wait_served_marks(page, name, keys):
    want = set(keys)
    got = settled(page, lambda: set(marks_of(served_layer(page, name))), lambda v: v == want)
    assert got == want, (got, want)


def test_the_seventh_tab_opens_with_its_panel_and_tools(page):
    reset_project(page)
    tabs = page.locator('.view-tab[data-mode]')
    assert tabs.count() == 7
    assert tabs.nth(6).get_attribute('data-mode') == 'idm'
    assert tabs.nth(6).inner_text().strip() == 'IDM Locator'
    assert page.is_visible('#idm-toolbar')
    assert page.is_visible('.tab-panel[data-tab="idm"]')
    # the Pixel Map's raster: the processor raster the output feeds
    assert page.evaluate("() => window.canvasRenderer.rasterWidth") == 1920
    assert page.evaluate("() => window.canvasRenderer.isShowLookView()") is False
    # Output to Display offers the view; the Export dialog does not
    page.evaluate("window.app.handleMenuAction('output-to-display')")
    page.wait_for_selector('#output-display-modal', state='visible')
    views = page.eval_on_selector_all('#output-display-view option', 'els => els.map(e => [e.value, e.textContent])')
    assert ['idm', 'IDM Locator'] in views, views
    page.evaluate("window.app.closeOutputDisplayDialog()")
    assert page.locator('#export-idm').count() == 0
    # leaving the tab hides the tools
    page.click('.view-tab[data-mode="pixel-map"]')
    assert not page.is_visible('#idm-toolbar')
    open_tab(page)
    assert not page._errors, page._errors


def test_the_module_fields_set_the_layout_and_show_a_mixed_selection(page):
    reset_project(page)
    page.evaluate("() => window.app.selectLayer(window.app.project.layers.find(x => x.name === 'IdmA'))")
    page.wait_for_timeout(150)
    assert page.input_value('#idm-modules-x') == '1'
    page.fill('#idm-modules-x', '2')
    page.keyboard.press('Tab')
    page.fill('#idm-modules-y', '2')
    page.keyboard.press('Enter')
    got = settled(page, lambda: idm_of(served_layer(page, 'IdmA')),
                  lambda v: v == {'modulesX': 2, 'modulesY': 2, 'marks': {}})
    assert got == {'modulesX': 2, 'modulesY': 2, 'marks': {}}, got
    assert idm_of(layer_of(page, 'IdmA')) == got
    assert 'Each module: 64 × 64 px' in page.inner_text('#idm-module-size')
    # Both screens: the across figure differs, so it shows '-'
    page.evaluate("""() => {
        const app = window.app;
        const ids = app.project.layers.map(l => l.id);
        app.selectLayer(app.project.layers[0]);
        app.selectedLayerIds = new Set(ids);
        window.canvasRenderer.render();
    }""")
    page.wait_for_timeout(200)
    assert page.input_value('#idm-modules-x') == ''
    assert page.get_attribute('#idm-modules-x', 'placeholder') == '-'
    assert page.inner_text('#idm-screen-name') == '2 screens'
    page.fill('#idm-modules-x', '4')
    page.keyboard.press('Enter')
    settled(page, lambda: idm_of(served_layer(page, 'IdmB')), lambda v: v and v['modulesX'] == 4)
    assert idm_of(served_layer(page, 'IdmA'))['modulesX'] == 4
    assert idm_of(served_layer(page, 'IdmA'))['modulesY'] == 2   # the empty field kept each its own
    assert idm_of(served_layer(page, 'IdmB'))['modulesY'] == 1


def test_browser_and_server_agree_on_every_module(page):
    reset_project(page)
    # IdmB in 3 x 3 (160 px: 53, 53, 54), its top-right cabinet half
    # height, its bottom-left one blanked; IdmA rotated 90.
    page.evaluate("""async () => {
        const app = window.app;
        const b = app.project.layers.find(x => x.name === 'IdmB');
        const p = (c, r) => b.panels.find(q => q.col === c && q.row === r).id;
        await fetch(`/api/layer/${b.id}/panels/set_half_tile`, {method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({panels: [{id: p(1, 0), halfTile: 'height'}]})});
        await fetch(`/api/layer/${b.id}/panels/set_hidden`, {method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({panels: [{id: p(0, 1), hidden: true}]})});
        app.loadProject();
    }""")
    page.wait_for_timeout(1200)
    set_layout(page, 'IdmB', 3, 3)
    page.wait_for_timeout(300)
    js = page.evaluate("""() => {
        const r = window.canvasRenderer;
        const b = window.app.project.layers.find(x => x.name === 'IdmB');
        const out = {};
        r.idmLayerCells(b).forEach(({panel, cells}) => {
            out[`${panel.col},${panel.row}`] = cells.map(c => [c.mx, c.my, c.x, c.y, c.w, c.h]);
        });
        return out;
    }""")
    server = next(l for l in app_module.current_project['layers'] if l['name'] == 'IdmB')
    shown = {(q['row'], q['col']) for q in server['panels'] if not q.get('hidden')}
    py = {f"{p['col']},{p['row']}": [list(c) for c in app_module.idm_module_cells(
        server, p, 3, 3, lambda r, c: (r, c) in shown)] for p in server['panels']}
    assert js == py, (js, py)
    assert js['0,1'] == []                                   # blanked
    assert [c[4] for c in js['0,0'] if c[1] == 0] == [53, 53, 54]
    # the half-height cabinet: 80 px of 53 + 53 + 54 -> one whole row and
    # one cut at the free (top) edge... it meets the wall below, so the
    # full cabinet is laid from the bottom and the cut is on top.
    assert sorted({c[1] for c in js['1,0']}) == [1, 2], js['1,0']
    assert {c[5] for c in js['1,0'] if c[1] == 2} == {54}
    assert {c[5] for c in js['1,0'] if c[1] == 1} == {26}
    # Pixel Map rotation is respected: with IdmA turned 180, the module
    # under the screen's top-left corner is the last module of its
    # bottom-right cabinet.
    page.evaluate("""() => {
        const a = window.app.project.layers.find(x => x.name === 'IdmA');
        a.rotation = 180;
        a.idm = {modulesX: 2, modulesY: 2, marks: {}};
        window.canvasRenderer.render();
    }""")
    hit = page.evaluate("""() => {
        const r = window.canvasRenderer;
        const a = window.app.project.layers.find(x => x.name === 'IdmA');
        const h = r.idmHitAt(3, 3);
        return h && h.layer === a ? [h.panel.col, h.panel.row, h.cell.mx, h.cell.my] : null;
    }""")
    assert hit == [2, 1, 1, 1], hit
    page.evaluate("""() => {
        const a = window.app.project.layers.find(x => x.name === 'IdmA');
        a.rotation = 0; delete a.idm;
        window.canvasRenderer.render();
    }""")


def test_a_click_marks_a_module_and_a_second_click_clears_it(page):
    reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    before = history_len(page)
    click_module(page, 'IdmA', 1, 0, 1, 1)
    wait_served_marks(page, 'IdmA', ['1,0,1,1'])
    mark = marks_of(layer_of(page, 'IdmA'))['1,0,1,1']
    assert mark == {'style': 'color', 'color': '#ff1a1a'}, mark
    assert history_len(page) == before + 1
    click_module(page, 'IdmA', 1, 0, 1, 1)
    wait_served_marks(page, 'IdmA', [])
    assert history_len(page) == before + 2
    # the view selected the screen it was marking on
    assert page.evaluate("() => window.app.currentLayer.name") == 'IdmA'


def test_a_drag_paints_then_clears_as_one_step_each(page):
    reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    before = history_len(page)
    a = point(page, 'IdmA', 0, 0, 0, 0)
    b = point(page, 'IdmA', 2, 0, 1, 0)
    page.mouse.move(a['x'], a['y'])
    page.mouse.down()
    page.mouse.move(b['x'], b['y'], steps=24)
    page.mouse.up()
    painted = ['0,0,0,0', '0,0,1,0', '1,0,0,0', '1,0,1,0', '2,0,0,0', '2,0,1,0']
    wait_served_marks(page, 'IdmA', painted)
    assert history_len(page) == before + 1
    # Start on a marked module: the stroke clears - and passes over the
    # unmarked row below without marking it.
    c = point(page, 'IdmA', 0, 0, 1, 0)
    d = point(page, 'IdmA', 1, 0, 1, 0)
    e = point(page, 'IdmA', 1, 1, 1, 1)
    page.mouse.move(c['x'], c['y'])
    page.mouse.down()
    page.mouse.move(d['x'], d['y'], steps=12)
    page.mouse.move(e['x'], e['y'], steps=12)
    page.mouse.up()
    wait_served_marks(page, 'IdmA', ['0,0,0,0', '2,0,0,0', '2,0,1,0'])
    assert history_len(page) == before + 2
    # one undo puts the whole cleared stroke back
    page.evaluate("() => window.app.undo()")
    got = settled(page, lambda: set(marks_of(layer_of(page, 'IdmA'))), lambda v: v == set(painted))
    assert got == set(painted)
    wait_served_marks(page, 'IdmA', painted)


def test_colour_and_x_marks_survive_the_server_a_reload_a_load_and_undo(page):
    reset_project(page)
    set_layout(page, 'IdmB', 2, 2)
    # an X in green
    page.click('#idm-style-x')
    page.evaluate("""() => { const c = document.getElementById('idm-color');
        c.value = '#00ff00'; c.dispatchEvent(new Event('input', {bubbles: true}));
        c.dispatchEvent(new Event('change', {bubbles: true})); }""")
    click_module(page, 'IdmB', 0, 0, 0, 0)
    # a fill in blue
    page.click('#idm-style-color')
    page.evaluate("""() => { const c = document.getElementById('idm-color');
        c.value = '#0000ff'; c.dispatchEvent(new Event('input', {bubbles: true})); }""")
    click_module(page, 'IdmB', 1, 1, 1, 1)
    want = {'0,0,0,0': {'style': 'x', 'color': '#00ff00'},
            '1,1,1,1': {'style': 'color', 'color': '#0000ff'}}
    got = settled(page, lambda: marks_of(served_layer(page, 'IdmB')), lambda v: v == want)
    assert got == want, got
    assert marks_of(layer_of(page, 'IdmB')) == want
    # the pixels: the fill is blue, the X's diagonal is green
    rgb = page.evaluate("""([x, y]) => {
        const r = window.canvasRenderer, rect = r.canvas.getBoundingClientRect();
        const dpr = r.canvas.width / rect.width;
        return Array.from(r.ctx.getImageData(Math.round((x - rect.left) * dpr), Math.round((y - rect.top) * dpr), 1, 1).data.slice(0, 3));
    }""", [point(page, 'IdmB', 1, 1, 1, 1)['x'], point(page, 'IdmB', 1, 1, 1, 1)['y']])
    assert rgb[2] > 200 and rgb[0] < 60 and rgb[1] < 60, rgb
    # undo / redo
    page.evaluate("() => window.app.undo()")
    settled(page, lambda: marks_of(layer_of(page, 'IdmB')), lambda v: '1,1,1,1' not in v)
    assert set(marks_of(layer_of(page, 'IdmB'))) == {'0,0,0,0'}
    page.evaluate("() => window.app.redo()")
    got = settled(page, lambda: marks_of(layer_of(page, 'IdmB')), lambda v: v == want)
    assert got == want
    got = settled(page, lambda: marks_of(served_layer(page, 'IdmB')), lambda v: v == want)
    assert got == want
    # a load: the project as a file holds it, back through the load funnel
    page.evaluate("""async () => {
        const p = await (await fetch('/api/project')).json();
        const text = JSON.stringify(p);
        await fetch('/api/project', {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: text});
        window.app.loadProject();
    }""")
    page.wait_for_timeout(1000)
    assert marks_of(layer_of(page, 'IdmB')) == want
    # a reload
    page.reload(wait_until='domcontentloaded')
    page.wait_for_function("() => window.app && window.app.project && window.app.history", timeout=15000)
    page.wait_for_timeout(800)
    assert marks_of(layer_of(page, 'IdmB')) == want
    open_tab(page)
    # the tools remember this viewer's last style and colour
    assert page.evaluate("() => document.getElementById('idm-style-color').classList.contains('active')")
    assert page.input_value('#idm-color') == '#0000ff'
    page.evaluate("""() => { const c = document.getElementById('idm-color');
        c.value = '#ff1a1a'; c.dispatchEvent(new Event('input', {bubbles: true})); }""")


def test_a_module_change_on_a_marked_screen_asks_then_clears(page):
    reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    click_module(page, 'IdmA', 0, 0, 0, 0)
    click_module(page, 'IdmA', 2, 1, 1, 1)
    wait_served_marks(page, 'IdmA', ['0,0,0,0', '2,1,1,1'])
    page.evaluate("() => window.app.selectLayer(window.app.project.layers.find(x => x.name === 'IdmA'))")
    page.wait_for_timeout(150)
    messages = []

    def dismiss(d):
        messages.append(d.message)
        d.dismiss()
    page.once('dialog', dismiss)
    page.fill('#idm-modules-x', '3')
    page.keyboard.press('Enter')
    page.wait_for_timeout(400)
    assert messages and 'clears its 2 marks' in messages[0], messages
    assert page.input_value('#idm-modules-x') == '2'     # put back
    assert idm_of(layer_of(page, 'IdmA'))['modulesX'] == 2
    assert len(marks_of(layer_of(page, 'IdmA'))) == 2
    before = history_len(page)
    page.once('dialog', lambda d: d.accept())
    page.fill('#idm-modules-x', '3')
    page.keyboard.press('Enter')
    got = settled(page, lambda: idm_of(served_layer(page, 'IdmA')),
                  lambda v: v == {'modulesX': 3, 'modulesY': 2, 'marks': {}})
    assert got == {'modulesX': 3, 'modulesY': 2, 'marks': {}}, got
    assert history_len(page) == before + 1
    # and the undo brings the layout and both marks back
    page.evaluate("() => window.app.undo()")
    got = settled(page, lambda: idm_of(layer_of(page, 'IdmA')), lambda v: v and v['modulesX'] == 2)
    assert set(got['marks']) == {'0,0,0,0', '2,1,1,1'}


def test_shrinking_the_columns_drops_the_marks_that_fall_off(page):
    reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    click_module(page, 'IdmA', 0, 0, 0, 0)
    click_module(page, 'IdmA', 2, 0, 1, 0)
    wait_served_marks(page, 'IdmA', ['0,0,0,0', '2,0,1,0'])
    page.evaluate("""() => {
        const app = window.app;
        const l = app.project.layers.find(x => x.name === 'IdmA');
        app.selectLayer(l);
        l.columns = 2;
        app.updateLayers([l], true, 'Columns');
    }""")
    wait_served_marks(page, 'IdmA', ['0,0,0,0'])
    got = settled(page, lambda: set(marks_of(layer_of(page, 'IdmA'))), lambda v: v == {'0,0,0,0'})
    assert got == {'0,0,0,0'}, got


def test_copies_keep_the_layout_but_start_with_no_marks(page):
    reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    click_module(page, 'IdmA', 0, 0, 0, 0)
    wait_served_marks(page, 'IdmA', ['0,0,0,0'])
    blank = {'modulesX': 2, 'modulesY': 2, 'marks': {}}

    def newest(before):
        fresh = page.evaluate("""(before) => window.app.project.layers
            .filter(l => !before.includes(l.id)).map(l => ({id: l.id, idm: l.idm}))""", before)
        assert len(fresh) == 1, fresh
        server = settled(page, lambda: page.evaluate("""async (id) => {
            const p = await (await fetch('/api/project')).json();
            const l = p.layers.find(x => x.id === id);
            return l ? (l.idm || null) : 'missing';
        }""", fresh[0]['id']), lambda v: v == blank)
        return fresh[0]['idm'], server

    def select_a():
        page.evaluate("""() => {
            const app = window.app;
            app.selectLayer(app.project.layers.find(x => x.name === 'IdmA'));
            if (document.activeElement) document.activeElement.blur();
        }""")
        return page.evaluate("() => window.app.project.layers.map(x => x.id)")

    # Duplicate (Cmd/Ctrl+J)
    before = select_a()
    page.keyboard.press(f'{MOD}+j')
    page.wait_for_timeout(1200)
    assert newest(before) == (blank, blank)
    # Copy, Paste
    before = select_a()
    page.keyboard.press(f'{MOD}+c')
    page.wait_for_timeout(200)
    page.keyboard.press(f'{MOD}+v')
    page.wait_for_timeout(1200)
    assert newest(before) == (blank, blank)
    # Duplicate Group: IdmA grouped with one of its copies
    out = page.evaluate("""async () => {
        const app = window.app;
        const a = app.project.layers.find(x => x.name === 'IdmA');
        const other = app.project.layers.find(x => x.id !== a.id && x.columns === a.columns
            && x.name !== 'IdmB');
        app.selectLayer(a);
        app.selectedLayerIds = new Set([a.id, other.id]);
        const gid = await app.groupSelectedLayers();
        await new Promise(r => setTimeout(r, 600));
        const before = app.project.layers.map(l => l.id);
        const newGid = await app.duplicateGroup(gid);
        await new Promise(r => setTimeout(r, 1200));
        const fresh = app.project.layers.filter(l => !before.includes(l.id));
        const p = await (await fetch('/api/project')).json();
        return {gid, newGid,
                browser: fresh.map(l => l.idm || null),
                server: p.layers.filter(l => !before.includes(l.id)).map(l => l.idm || null)};
    }""")
    assert out['gid'] and out['newGid'], out
    assert len(out['browser']) == 2 and all(i == blank for i in out['browser']), out
    assert len(out['server']) == 2 and all(i == blank for i in out['server']), out
    # the original keeps its mark
    assert set(marks_of(served_layer(page, 'IdmA'))) == {'0,0,0,0'}


def test_a_locked_screen_cannot_be_marked(page):
    reset_project(page)
    set_layout(page, 'IdmB', 2, 2)
    page.evaluate("""() => {
        const app = window.app;
        const l = app.project.layers.find(x => x.name === 'IdmB');
        l.locked = true;
        app.updateLayers([l], true, 'Lock');
    }""")
    settled(page, lambda: served_layer(page, 'IdmB')['locked'], lambda v: v is True)
    before = history_len(page)
    click_module(page, 'IdmB', 0, 0, 0, 0)
    page.wait_for_timeout(400)
    assert marks_of(layer_of(page, 'IdmB')) == {}
    assert marks_of(served_layer(page, 'IdmB')) == {}
    assert history_len(page) == before
    assert 'locked' in page.inner_text('#app-toast-host')


def test_the_locator_list_names_the_cabinet_ids_and_finds_the_module(page):
    reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    click_module(page, 'IdmA', 1, 0, 1, 0)
    click_module(page, 'IdmA', 0, 1, 0, 1)
    wait_served_marks(page, 'IdmA', ['1,0,1,0', '0,1,0,1'])
    page.wait_for_timeout(200)
    rows = page.eval_on_selector_all('#idm-list .idm-row', 'els => els.map(e => e.textContent.trim())')
    # Cabinet ID view's default numbering: column letter + row number,
    # reading order top row first.
    assert rows == ['IdmA · B1 · Module 2 (row 1, col 2)',
                    'IdmA · A2 · Module 3 (row 2, col 1)'], rows
    assert page.inner_text('#idm-count') == '(2)'
    assert 'IdmA · 2 marks' in page.inner_text('#idm-list')
    # the Cabinet ID view's own label for the same cabinet, whatever style
    page.evaluate("""() => {
        const app = window.app;
        const l = app.project.layers.find(x => x.name === 'IdmA');
        l.cabinetIdStyle = 'row-col';
        app.updateLayers([l], true, 'Style');
        window.canvasRenderer.render();
    }""")
    page.wait_for_timeout(400)
    rows = page.eval_on_selector_all('#idm-list .idm-row', 'els => els.map(e => e.textContent.trim())')
    labels = page.evaluate("""() => {
        const r = window.canvasRenderer;
        const l = window.app.project.layers.find(x => x.name === 'IdmA');
        const of = r.cabinetIdLabeler(l);
        return [of(l.panels.find(p => p.col === 1 && p.row === 0)), of(l.panels.find(p => p.col === 0 && p.row === 1))];
    }""")
    assert labels == ['1,2', '2,1'], labels
    assert rows == ['IdmA · 1,2 · Module 2 (row 1, col 2)',
                    'IdmA · 2,1 · Module 3 (row 2, col 1)'], rows
    # a row selects its screen and makes the module blink
    page.evaluate("() => window.app.selectLayer(window.app.project.layers.find(x => x.name === 'IdmB'))")
    page.click('#idm-list .idm-row >> nth=1')
    assert page.evaluate("() => window.app.currentLayer.name") == 'IdmA'
    flash = page.evaluate("""() => window.app._idmFlashFor(
        window.app.project.layers.find(x => x.name === 'IdmA'))""")
    assert flash and flash['key'] == '0,1,0,1', flash
    page.wait_for_selector('#idm-list .idm-row.active')


def test_the_output_window_shows_a_mark_as_it_is_made(page, e2e_server):
    cid = reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    with page.expect_popup() as info:
        page.evaluate("(id) => { window.app.openOutputDisplay({canvasId: id, view: 'idm', scale: '1to1'}); }", cid)
    out = info.value
    out.wait_for_load_state('domcontentloaded')

    def frames():
        return out.evaluate("() => Number(document.body.dataset.frames || 0)")

    def pixel(x, y):
        return out.evaluate("""([x, y]) => {
            const c = document.getElementById('output-canvas');
            if (!c.width || x >= c.width || y >= c.height) return null;
            return Array.from(c.getContext('2d').getImageData(x, y, 1, 1).data.slice(0, 3));
        }""", [x, y])
    try:
        settled(out, frames, lambda n: n >= 1, 8000)
        assert out.evaluate("() => [document.getElementById('output-canvas').width,"
                            " document.getElementById('output-canvas').height]") == [1920, 1080]
        # IdmA's cabinet (1, 0) module (1, 1): x 128+64..256, y 64..128
        before = pixel(224, 96)
        green = lambda px: px is not None and px[1] > 200 and px[0] < 60 and px[2] < 60  # noqa: E731
        assert not green(before), before
        # the module grid is drawn: the line between the two modules of
        # cabinet (0, 0) at x = 64 is lighter than the module beside it
        line, beside = pixel(64, 30), pixel(40, 30)
        assert sum(line) != sum(beside), (line, beside)
        page.evaluate("""() => { const c = document.getElementById('idm-color');
            c.value = '#00ff00'; c.dispatchEvent(new Event('input', {bubbles: true})); }""")
        click_module(page, 'IdmA', 1, 0, 1, 1)
        got = settled(out, lambda: pixel(224, 96), green, 6000)
        assert green(got), got
        # and an X on another module, another colour, from another machine
        layer_id = page.evaluate("() => window.app.project.layers.find(x => x.name === 'IdmA').id")
        marks = dict(marks_of(served_layer(page, 'IdmA')))
        marks['0,1,0,0'] = {'style': 'x', 'color': '#0000ff'}
        req = urllib.request.Request(
            f'{e2e_server}/api/layer/{layer_id}',
            data=json.dumps({'idm': {'modulesX': 2, 'modulesY': 2, 'marks': marks}}).encode('utf-8'),
            headers={'Content-Type': 'application/json'}, method='PUT')
        urllib.request.urlopen(req).read()
        # module (0, 0) of cabinet (0, 1): x 0..64, y 128..192 - its
        # diagonal passes through (32, 160)
        blue = lambda px: px is not None and px[2] > 200 and px[0] < 60 and px[1] < 60  # noqa: E731
        got = settled(out, lambda: pixel(32, 160), blue, 6000)
        assert blue(got), got
        # the X leaves the module's corners-to-edge-centre space unfilled
        assert not blue(pixel(32, 132)), pixel(32, 132)
    finally:
        out.close()
    page.evaluate("""() => { const c = document.getElementById('idm-color');
        c.value = '#ff1a1a'; c.dispatchEvent(new Event('input', {bubbles: true})); }""")


def test_presets_keep_the_layout_and_never_the_marks(page):
    reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    click_module(page, 'IdmA', 0, 0, 0, 0)
    wait_served_marks(page, 'IdmA', ['0,0,0,0'])
    out = page.evaluate("""() => {
        const app = window.app;
        const a = app.project.layers.find(x => x.name === 'IdmA');
        const b = app.project.layers.find(x => x.name === 'IdmB');
        const preset = app.serializeLayerAsPreset(a);
        const target = JSON.parse(JSON.stringify(b));
        target.idm = {modulesX: 2, modulesY: 2, marks: {'0,0,0,0': {style: 'x', color: '#00ff00'}}};
        const keep = JSON.parse(JSON.stringify(target));
        app.applyPresetClientProps(keep, {idm: {modulesX: 2, modulesY: 2, marks: {'1,1,1,1': {style: 'x'}}}});
        app.applyPresetClientProps(target, preset);
        const other = JSON.parse(JSON.stringify(b));
        app.applyPresetClientProps(other, {idm: {modulesX: 4, modulesY: 1}});
        return {preset: preset.idm, kept: keep.idm, applied: target.idm, other: other.idm};
    }""")
    assert out['preset'] == {'modulesX': 2, 'modulesY': 2}, out
    # same layout: the screen keeps its own marks, the preset's never land
    assert out['kept'] == {'modulesX': 2, 'modulesY': 2,
                           'marks': {'0,0,0,0': {'style': 'x', 'color': '#00ff00'}}}, out
    assert out['other'] == {'modulesX': 4, 'modulesY': 1, 'marks': {}}, out


def test_an_older_project_loads_and_draws_unchanged(page):
    reset_project(page)
    page._errors.clear()
    out = page.evaluate("""async () => {
        const p = await (await fetch('/api/project')).json();
        p.layers.forEach(l => { delete l.idm; });
        const back = await (await fetch('/api/project', {method: 'PUT',
            headers: {'Content-Type': 'application/json'}, body: JSON.stringify(p)})).json();
        window.app.loadProject();
        await new Promise(r => setTimeout(r, 800));
        window.canvasRenderer.setViewMode('idm');
        const r = window.canvasRenderer;
        const a = window.app.project.layers.find(x => x.name === 'IdmA');
        return {served: back.layers.map(l => 'idm' in l), counts: r.idmCounts(a),
                cells: r.idmLayerCells(a).map(e => e.cells.length)};
    }""")
    assert out['served'] == [False, False], out
    assert out['counts'] == {'x': 1, 'y': 1}
    assert out['cells'] == [1, 1, 1, 1, 1, 1]
    open_tab(page)
    assert page.inner_text('#idm-list').strip().startswith('No marks')
    assert not page._errors, page._errors


# ── 3. Pictures for the record ────────────────────────────────────────────

SHOTS = os.environ.get('LRD_IDM_SHOTS')


@pytest.mark.skipif(not SHOTS, reason='set LRD_IDM_SHOTS to a folder to save the screenshots')
def test_screenshots(page):
    cid = reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    set_layout(page, 'IdmB', 4, 4)
    click_module(page, 'IdmA', 0, 0, 1, 0)
    click_module(page, 'IdmA', 2, 1, 0, 1)
    page.click('#idm-style-x')
    page.evaluate("""() => { const c = document.getElementById('idm-color');
        c.value = '#ffd400'; c.dispatchEvent(new Event('input', {bubbles: true})); }""")
    click_module(page, 'IdmB', 0, 1, 2, 1)
    click_module(page, 'IdmB', 1, 0, 3, 3)
    page.click('#idm-style-color')
    page.evaluate("""() => { const c = document.getElementById('idm-color');
        c.value = '#00c8ff'; c.dispatchEvent(new Event('input', {bubbles: true})); }""")
    click_module(page, 'IdmB', 1, 1, 0, 0)
    page.evaluate("() => window.app.selectLayer(window.app.project.layers.find(x => x.name === 'IdmB'))")
    page.wait_for_timeout(500)
    page.screenshot(path=os.path.join(SHOTS, 'idm-locator-tab.png'))
    with page.expect_popup() as info:
        page.evaluate("(id) => { window.app.openOutputDisplay({canvasId: id, view: 'idm', scale: 'fit'}); }", cid)
    out = info.value
    out.set_viewport_size({'width': 1280, 'height': 720})
    settled(out, lambda: out.evaluate("() => Number(document.body.dataset.frames || 0)"), lambda n: n >= 1, 8000)
    out.wait_for_timeout(5000)
    out.screenshot(path=os.path.join(SHOTS, 'idm-locator-output.png'))
    out.close()
    page.evaluate("""() => { const c = document.getElementById('idm-color');
        c.value = '#ff1a1a'; c.dispatchEvent(new Event('input', {bubbles: true})); }""")
    page.click('#idm-style-color')
