"""The IDM Locator's field colour and live highlight (app-idm-locator.js,
canvas-idm.js, app-output-display.js).

The crew puts one solid colour on the real wall to spot dead pixels and bad
modules, and needs to see live on the wall which module they are pointing
at. What this file pins:

* The field: project.idmField = {color, border} held to its shape by the
  server (app.sanitize_idm_field) on its own route and in both project
  funnels; the route broadcasts it and leaves a pristine project pristine.
  In the browser the quick colours and the border styles change the pixels
  the output window shows (white, the shade checker at 85% with the cabinet
  ring at 65%, lines and corner ticks in the field's own hue at 70% / 50% -
  never black - a uniform field with none,
  the lifted levels on black), the designer's on-screen grid never reaches
  the output, a mark the colour of the field is drawn in the contrasting
  colour (its stored colour unchanged), the field reaches a second client,
  is never an undo step, and survives save and load; an older project draws
  white with shaded borders.
* The live highlight: the server relays it to every other client
  (app.sanitize_idm_highlight) and keeps it on the project only when it
  names a module that exists (the rest of what keeping it means is pinned
  by tests/test_idm_module_ids.py). Hover highlights a module and the
  pad and status bar name it the locator list's way; the arrows step one
  module across cabinet edges and onto the next screen, Shift a whole
  cabinet; Space marks it (one undo step), Esc clears it; a text field
  keeps its arrows. From a tablet (a touch, mobile-sized page) a tap moves
  the highlight without marking, the pad's arrows and Mark drive it, and the
  host's output window shows it blinking white / the field's inverse. A
  deleted screen takes its highlight with it.

Run locally:
    python -m pytest tests/test_idm_field_highlight.py -v -p no:cacheprovider --browser chromium
"""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'src'))
sys.path.insert(0, HERE)

from conftest import settled  # noqa: E402

import app as app_module  # noqa: E402
from app import app as flask_app, socketio  # noqa: E402


# ── 1. The server (no browser) ────────────────────────────────────────────

def test_the_field_sanitizer_holds_colour_and_border():
    s = app_module.sanitize_idm_field
    assert s({'color': '#FF0000', 'border': 'lines'}) == {'color': '#ff0000', 'border': 'lines', 'moduleIds': False}
    assert s({'color': 'abc', 'border': 'ticks', 'stray': 1}) == {'color': '#aabbcc', 'border': 'ticks', 'moduleIds': False}
    # unusable parts take the defaults: white, shade
    assert s({}) == {'color': '#ffffff', 'border': 'shade', 'moduleIds': False}
    assert s({'color': 'red', 'border': 'dots'}) == {'color': '#ffffff', 'border': 'shade', 'moduleIds': False}
    assert s({'color': None, 'border': None}) == app_module.IDM_FIELD_DEFAULT
    # not a block: removed
    assert s(None) is None and s('white') is None and s([1]) is None
    clean = s({'color': '#00FF00', 'border': 'none'})
    assert s(clean) == clean   # idempotent


def test_the_field_route_stores_broadcasts_and_keeps_a_pristine_project(client):
    app_module.current_project['is_pristine'] = True
    sock = socketio.test_client(flask_app, flask_test_client=client)
    try:
        sock.get_received()
        resp = client.put('/api/project/idm-field',
                          json={'field': {'color': '#0000FF', 'border': 'ticks'}, 'origin': 'tab1'})
        assert resp.status_code == 200
        assert resp.get_json() == {'idmField': {'color': '#0000ff', 'border': 'ticks', 'moduleIds': False}}
        assert app_module.current_project['idmField'] == {'color': '#0000ff', 'border': 'ticks', 'moduleIds': False}
        # view state, not an edit: the pristine startup project stays so
        assert app_module.current_project['is_pristine'] is True
        got = [r for r in sock.get_received() if r['name'] == 'idm_field_updated']
        assert got and got[0]['args'][0] == {
            'field': {'color': '#0000ff', 'border': 'ticks', 'moduleIds': False}, 'origin': 'tab1'}, got
        # junk is refused and the stored field kept
        assert client.put('/api/project/idm-field', json={'field': 'red'}).status_code == 400
        assert client.put('/api/project/idm-field', json=[1]).status_code == 400
        assert app_module.current_project['idmField']['color'] == '#0000ff'
    finally:
        sock.disconnect()


def test_the_project_funnels_hold_the_field_and_an_old_file_loads_without_it(client):
    project = client.get('/api/project').get_json()
    project['idmField'] = {'color': '#F0F', 'border': 'bogus'}
    restored = client.put('/api/project', json=project).get_json()
    assert restored['idmField'] == {'color': '#ff00ff', 'border': 'shade', 'moduleIds': False}
    project['idmField'] = 'not a block'
    restored = client.put('/api/project', json=project).get_json()
    assert 'idmField' not in restored
    # the save funnel too
    project['idmField'] = {'color': '#123', 'border': 'none'}
    assert client.post('/api/project', json=project).status_code == 200
    assert app_module.current_project['idmField'] == {'color': '#112233', 'border': 'none', 'moduleIds': False}
    # an older file has no key and gets none
    del project['idmField']
    restored = client.put('/api/project', json=project).get_json()
    assert 'idmField' not in restored
    assert app_module.normalize_idm_field(restored) is False


def test_the_highlight_sanitizer():
    s = app_module.sanitize_idm_highlight
    assert s({'layerId': 3, 'key': ' 1, 0 ,2,3', 'origin': 'x'}) == {'layerId': 3, 'key': '1,0,2,3', 'origin': 'x'}
    assert s({'layerId': None, 'key': None}) == {'layerId': None, 'key': None, 'origin': ''}
    assert s({'layerId': 3, 'key': '1,0,2'}) is None
    assert s({'layerId': 3, 'key': 'a,b,c,d'}) is None
    assert s({'layerId': '3', 'key': '1,0,0,0'}) is None
    assert s({'layerId': True, 'key': '1,0,0,0'}) is None
    assert s({'layerId': 3, 'key': None}) is None
    assert s('1,0,0,0') is None
    assert len(s({'layerId': 1, 'key': '0,0,0,0', 'origin': 'o' * 500})['origin']) == 64


def test_the_server_relays_the_highlight_to_the_others(client):
    a = socketio.test_client(flask_app, flask_test_client=client)
    b = socketio.test_client(flask_app, flask_test_client=client)
    try:
        a.get_received()
        b.get_received()
        before = dict(app_module.current_project)
        before.pop('idmHighlight', None)
        a.emit('idm_highlight', {'layerId': 7, 'key': '2,1,0,1', 'origin': 'tablet'})
        got_b = [r['args'][0] for r in b.get_received() if r['name'] == 'idm_highlight']
        got_a = [r for r in a.get_received() if r['name'] == 'idm_highlight']
        assert got_b == [{'layerId': 7, 'key': '2,1,0,1', 'origin': 'tablet'}], got_b
        assert got_a == []          # never back to the sender
        # a clear is relayed too; junk is not
        a.emit('idm_highlight', {'layerId': None, 'key': None, 'origin': 'tablet'})
        a.emit('idm_highlight', {'layerId': 7, 'key': 'nope'})
        a.emit('idm_highlight', 'nope')
        got_b = [r['args'][0] for r in b.get_received() if r['name'] == 'idm_highlight']
        assert got_b == [{'layerId': None, 'key': None, 'origin': 'tablet'}], got_b
        # the last mover wins: whoever sends next is what the others get
        b.emit('idm_highlight', {'layerId': 7, 'key': '0,0,0,0', 'origin': 'host'})
        got_a = [r['args'][0]['key'] for r in a.get_received() if r['name'] == 'idm_highlight']
        assert got_a == ['0,0,0,0']
        # screen 7 is not in the project: relayed, but nothing kept - the
        # project is otherwise untouched
        after = dict(app_module.current_project)
        assert after.pop('idmHighlight', None) is None
        assert after == before
    finally:
        a.disconnect()
        b.disconnect()


# ── 2. In the browser ─────────────────────────────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project exactly as this module found it
    (see conftest.server_project_guard)."""


def _new_page(pw_browser, url, viewport=(1500, 950), **context_args):
    context = pw_browser.new_context(
        viewport={'width': viewport[0], 'height': viewport[1]}, **context_args)
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');"
        "localStorage.removeItem('lrdIdmMarkStyle');localStorage.removeItem('lrdIdmMarkColor');}catch(e){}")
    pg = context.new_page()
    pg._errors = []
    pg.on('pageerror', lambda err: pg._errors.append(str(err)))
    pg.goto(url, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app.project && window.app.history"
                         " && window.app.socket && window.app.socket.connected", timeout=15000)
    pg.wait_for_timeout(800)
    return context, pg


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context, pg = _new_page(pw_browser, e2e_server)
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
    delete project.idmField;
    await put('/api/project', project);
    await post('/api/layer/add', {name: 'IdmA', columns: 3, rows: 2,
        cabinet_width: 128, cabinet_height: 128, offset_x: 0, offset_y: 0, canvas_id: first.id});
    await post('/api/layer/add', {name: 'IdmB', columns: 2, rows: 2,
        cabinet_width: 160, cabinet_height: 160, offset_x: 600, offset_y: 0, canvas_id: first.id});
    window.app.closeAllOutputDisplays();
    window.app._idmClearHighlight();
    window.app.loadProject();
    return first.id;
}"""


def open_tab(pg):
    pg.click('.view-tab[data-mode="idm"]')
    pg.wait_for_function("() => window.canvasRenderer.viewMode === 'idm'")
    pg.wait_for_timeout(150)
    pg.evaluate("() => { window.canvasRenderer.fitToView(); window.canvasRenderer.render(); }")
    pg.wait_for_timeout(200)


def reset_project(pg):
    cid = pg.evaluate(RESET_JS)
    pg.wait_for_function(
        "() => window.app.project && (window.app.project.layers || []).length === 2"
        " && window.app.history && window.app.history.length === 1", timeout=10000)
    pg.wait_for_timeout(400)
    open_tab(pg)
    # the pointer parked off the canvas, so no hover moves the highlight
    pg.mouse.move(5, 5)
    pg.evaluate("() => window.app._idmClearHighlight()")
    return cid


def wait_layers(pg, n=2):
    pg.wait_for_function(
        f"() => window.app.project && (window.app.project.layers || []).length === {n}", timeout=10000)


def set_layout(pg, name, mx, my):
    pg.evaluate("""([name, mx, my]) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.name === name);
        l.idm = {modulesX: mx, modulesY: my, marks: {}};
        app.updateLayers([l], true, 'Set Modules');
        window.canvasRenderer.render();
    }""", [name, mx, my])
    settled(pg, lambda: served_idm(pg, name),
            lambda v: v and v['modulesX'] == mx and v['modulesY'] == my)


def served_idm(pg, name):
    return pg.evaluate("""async (name) => {
        const p = await (await fetch('/api/project')).json();
        const l = p.layers.find(x => x.name === name);
        return l ? (l.idm || null) : null;
    }""", name)


def served_field(pg):
    return pg.evaluate("async () => (await (await fetch('/api/project')).json()).idmField || null")


def marks_of(pg, name):
    return pg.evaluate("""(name) => {
        const l = window.app.project.layers.find(x => x.name === name);
        return (l && l.idm && l.idm.marks) ? JSON.parse(JSON.stringify(l.idm.marks)) : {};
    }""", name)


def hl(pg):
    return pg.evaluate("""() => {
        const h = window.app._idmHl();
        if (!h) return null;
        const l = window.app.project.layers.find(x => x.id === h.layerId);
        return [l ? l.name : null, h.key];
    }""")


# The client point at the centre of one module (no rotation on these).
POINT_JS = """([name, col, row, mx, my]) => {
    const app = window.app, r = window.canvasRenderer;
    const l = app.project.layers.find(x => x.name === name);
    const p = l.panels.find(q => q.col === col && q.row === row);
    const n = r.idmCounts(l);
    const c = r.idmModuleCells(l, p, n.x, n.y, r._idmVisibleLookup(l)).find(q => q.mx === mx && q.my === my);
    if (!c) return null;
    const {wx, wy} = r._layerCanvasOffset(l);
    const X = c.x + c.w / 2 + wx, Y = c.y + c.h / 2 + wy;
    const rect = r.canvas.getBoundingClientRect();
    return {x: rect.left + Math.round(r.panX) + X * r.zoom, y: rect.top + Math.round(r.panY) + Y * r.zoom};
}"""


def point(pg, name, col, row, mx, my):
    pt = pg.evaluate(POINT_JS, [name, col, row, mx, my])
    assert pt, f'no module {name} {col},{row},{mx},{my}'
    return pt


def open_output(pg, cid):
    with pg.expect_popup() as info:
        pg.evaluate("(id) => { window.app.openOutputDisplay({canvasId: id, view: 'idm', scale: '1to1'}); }", cid)
    out = info.value
    out.wait_for_load_state('domcontentloaded')
    settled(out, lambda: out.evaluate("() => Number(document.body.dataset.frames || 0)"), lambda n: n >= 1, 8000)
    return out


def pixel(out, x, y):
    return out.evaluate("""([x, y]) => {
        const c = document.getElementById('output-canvas');
        if (!c.width || x >= c.width || y >= c.height) return null;
        return Array.from(c.getContext('2d').getImageData(x, y, 1, 1).data.slice(0, 3));
    }""", [x, y])


def wait_pixel(out, x, y, want, tol=3, timeout=6000):
    ok = lambda px: px is not None and all(abs(a - b) <= tol for a, b in zip(px, want))  # noqa: E731
    got = settled(out, lambda: pixel(out, x, y), ok, timeout)
    assert ok(got), (x, y, got, want)
    return got


def click_field(pg, colour=None, border=None):
    if colour:
        pg.click(f'[data-idm-field="{colour}"]')
    if border:
        pg.click(f'[data-idm-border="{border}"]')
    pg.wait_for_timeout(100)


def test_the_field_buttons_change_the_output_pixels(page):
    cid = reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    out = open_output(page, cid)
    try:
        # IdmA cabinet (0, 0): x 0..128, modules at 0..64 and 64..128.
        # White, shade (the defaults): module (0,0) full, (1,0) at 85%, the
        # cabinet's outer pixel ring at 65%; outside the screens black.
        wait_pixel(out, 32, 32, (255, 255, 255))
        wait_pixel(out, 96, 32, (217, 217, 217))
        wait_pixel(out, 32, 96, (217, 217, 217))
        wait_pixel(out, 96, 96, (255, 255, 255))
        wait_pixel(out, 0, 32, (166, 166, 166))       # cabinet ring, left
        wait_pixel(out, 127, 32, (166, 166, 166))     # and right
        wait_pixel(out, 128, 32, (166, 166, 166))     # the next cabinet's ring
        wait_pixel(out, 160, 32, (255, 255, 255))     # the checker runs on across the wall
        wait_pixel(out, 224, 32, (217, 217, 217))
        wait_pixel(out, 500, 32, (0, 0, 0))           # no screen there
        assert page.get_attribute('[data-idm-field="#ffffff"]', 'aria-pressed') == 'true'
        assert page.get_attribute('[data-idm-border="shade"]', 'aria-pressed') == 'true'
        # Red: pure 255.
        click_field(page, '#ff0000')
        wait_pixel(out, 32, 32, (255, 0, 0))
        wait_pixel(out, 96, 32, (217, 0, 0))
        wait_pixel(out, 0, 32, (166, 0, 0))
        # Green, Blue: pure.
        click_field(page, '#00ff00')
        wait_pixel(out, 32, 32, (0, 255, 0))
        click_field(page, '#0000ff')
        wait_pixel(out, 32, 32, (0, 0, 255))
        # Black: the levels go up - very dark grey modules, a lighter ring.
        click_field(page, '#000000')
        wait_pixel(out, 32, 32, (0, 0, 0))
        wait_pixel(out, 96, 32, (26, 26, 26))
        wait_pixel(out, 0, 32, (52, 52, 52))
        # Lines on white: never black - module edges the field at 70%,
        # cabinet edges at 50%, the modules themselves white.
        click_field(page, '#ffffff', 'lines')
        wait_pixel(out, 64, 32, (179, 179, 179))
        wait_pixel(out, 32, 64, (179, 179, 179))
        wait_pixel(out, 0, 32, (128, 128, 128))
        wait_pixel(out, 127, 32, (128, 128, 128))
        wait_pixel(out, 32, 32, (255, 255, 255))
        wait_pixel(out, 96, 96, (255, 255, 255))
        # ... the field's own hue on a colour field ...
        click_field(page, '#0000ff')
        wait_pixel(out, 0, 32, (0, 0, 128))
        wait_pixel(out, 64, 32, (0, 0, 179))
        click_field(page, '#ff0000')
        wait_pixel(out, 0, 32, (128, 0, 0))
        # ... and lit greys on black.
        click_field(page, '#000000')
        wait_pixel(out, 0, 32, (102, 102, 102))
        wait_pixel(out, 64, 32, (51, 51, 51))
        # Ticks on white: an L in each module corner (10 px for a 64 px
        # module) at 70%, the middle of an edge left alone, the cabinet's
        # corners at 50%.
        click_field(page, '#ffffff', 'ticks')
        wait_pixel(out, 66, 0, (179, 179, 179))   # module (1,0)'s top-left tick
        wait_pixel(out, 64, 3, (179, 179, 179))
        wait_pixel(out, 66, 3, (255, 255, 255))
        wait_pixel(out, 96, 0, (255, 255, 255))   # mid-edge: no line
        wait_pixel(out, 1, 1, (128, 128, 128))    # the cabinet corner, 2 px thick
        # None: one uniform field across every module and cabinet edge.
        click_field(page, None, 'none')
        for x, y in [(0, 0), (32, 32), (63, 32), (64, 32), (96, 96), (127, 127), (128, 128), (383, 255)]:
            wait_pixel(out, x, y, (255, 255, 255), tol=0)
        # The designer still draws its module grid on screen - and that
        # grid is not in the output (above: x 63/64 are pure field).
        dark = page.evaluate("""() => {
            const r = window.canvasRenderer, app = window.app;
            const l = app.project.layers.find(x => x.name === 'IdmA');
            const X = Math.round(r.panX) + 64 * r.zoom, Y = Math.round(r.panY) + 32 * r.zoom;
            const d = r.ctx.getImageData(Math.round(X) - 3, Math.round(Y), 7, 1).data;
            let min = 255;
            for (let i = 0; i < d.length; i += 4) min = Math.min(min, d[i], d[i + 1], d[i + 2]);
            return min;
        }""")
        assert dark < 200, dark
        assert served_field(page) == {'color': '#ffffff', 'border': 'none', 'moduleIds': False}
    finally:
        out.close()
    assert not page._errors, page._errors


def test_a_mark_the_colour_of_the_field_is_drawn_to_contrast(page):
    cid = reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    out = open_output(page, cid)
    try:
        click_field(page, '#ff0000', 'none')
        # the default red mark (#ff1a1a), clicked on cabinet (0,0) module (0,0)
        pt = point(page, 'IdmA', 0, 0, 0, 0)
        page.mouse.click(pt['x'], pt['y'])
        settled(page, lambda: served_idm(page, 'IdmA'), lambda v: v and '0,0,0,0' in v['marks'])
        page.mouse.move(5, 5)
        page.evaluate("() => window.app._idmClearHighlight()")
        # red on red would vanish: drawn white (the contrast of red)
        wait_pixel(out, 32, 32, (255, 255, 255))
        # the stored colour is the mark's own
        assert marks_of(page, 'IdmA')['0,0,0,0'] == {'style': 'color', 'color': '#ff1a1a'}
        assert served_idm(page, 'IdmA')['marks']['0,0,0,0']['color'] == '#ff1a1a'
        # on a white field it is red again
        click_field(page, '#ffffff')
        wait_pixel(out, 32, 32, (255, 26, 26))
        # and on green, a green X mark turns black (the contrast of green)
        page.evaluate("""() => {
            const app = window.app, l = app.project.layers.find(x => x.name === 'IdmA');
            l.idm = {modulesX: 2, modulesY: 2, marks: {'0,0,0,0': {style: 'color', color: '#00ff10'}}};
            app.updateLayers([l], true, 'Mark');
            window.canvasRenderer.render();
        }""")
        click_field(page, '#00ff00')
        wait_pixel(out, 32, 32, (0, 0, 0))
        # the list chip keeps the stored colour
        chip = page.evaluate("() => getComputedStyle(document.querySelector('#idm-list .idm-chip')).backgroundColor")
        assert chip == 'rgb(0, 255, 16)', chip
    finally:
        out.close()


def test_the_field_reaches_a_second_client_and_is_never_an_undo_step(page, e2e_server, pw_browser):
    reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    context, other = _new_page(pw_browser, e2e_server)
    try:
        wait_layers(other)
        before = page.evaluate("() => window.app.historyIndex")
        click_field(page, '#00ff00', 'lines')
        got = settled(other, lambda: other.evaluate("() => window.app.project.idmField || null"),
                      lambda v: v == {'color': '#00ff00', 'border': 'lines', 'moduleIds': False})
        assert got == {'color': '#00ff00', 'border': 'lines', 'moduleIds': False}, got
        # the other client's tab follows when it is opened
        open_tab(other)
        assert other.get_attribute('[data-idm-field="#00ff00"]', 'aria-pressed') == 'true'
        assert other.get_attribute('[data-idm-border="lines"]', 'aria-pressed') == 'true'
        # and the other way round
        other.click('[data-idm-field="#0000ff"]')
        got = settled(page, lambda: page.evaluate("() => window.app.project.idmField"),
                      lambda v: v == {'color': '#0000ff', 'border': 'lines', 'moduleIds': False})
        assert got == {'color': '#0000ff', 'border': 'lines', 'moduleIds': False}, got
        assert page.get_attribute('[data-idm-field="#0000ff"]', 'aria-pressed') == 'true'
        # never an undo step
        assert page.evaluate("() => window.app.historyIndex") == before
        # a mark (one step), then a field change, then undo: the mark goes,
        # the field stays where it was put last
        pt = point(page, 'IdmA', 0, 0, 0, 0)
        page.mouse.click(pt['x'], pt['y'])
        settled(page, lambda: served_idm(page, 'IdmA'), lambda v: v and '0,0,0,0' in v['marks'])
        assert page.evaluate("() => window.app.historyIndex") == before + 1
        click_field(page, '#ff0000', 'ticks')
        assert page.evaluate("() => window.app.historyIndex") == before + 1
        page.evaluate("() => window.app.undo()")
        settled(page, lambda: marks_of(page, 'IdmA'), lambda v: v == {})
        assert marks_of(page, 'IdmA') == {}
        assert page.evaluate("() => window.app.project.idmField") == {'color': '#ff0000', 'border': 'ticks', 'moduleIds': False}
        page.wait_for_timeout(400)
        assert served_field(page) == {'color': '#ff0000', 'border': 'ticks', 'moduleIds': False}
        page.evaluate("() => window.app.redo()")
        settled(page, lambda: marks_of(page, 'IdmA'), lambda v: '0,0,0,0' in v)
        assert page.evaluate("() => window.app.project.idmField") == {'color': '#ff0000', 'border': 'ticks', 'moduleIds': False}
        assert not other._errors, other._errors
    finally:
        context.close()


def test_the_field_survives_save_and_load_and_an_older_project_is_white_shade(page):
    reset_project(page)
    # an older project: no key anywhere, drawn white with shaded borders
    assert page.evaluate("() => 'idmField' in window.app.project") is False
    assert served_field(page) is None
    assert page.evaluate("() => window.canvasRenderer.idmFieldSpec()") == {
        'color': '#ffffff', 'border': 'shade', 'rgb': [255, 255, 255], 'moduleIds': False,
        # the Colours, all Auto (tests/test_idm_colours.py)
        'labelColor': None, 'moduleEdgeColor': None, 'cabinetEdgeColor': None, 'shade': None}
    assert page.get_attribute('[data-idm-field="#ffffff"]', 'aria-pressed') == 'true'
    assert page.get_attribute('[data-idm-border="shade"]', 'aria-pressed') == 'true'
    # a custom colour through the swatch (the app's colour picker writes
    # the input and fires its events)
    page.evaluate("""() => { const c = document.getElementById('idm-field-custom');
        c.value = '#336699'; c.dispatchEvent(new Event('input', {bubbles: true}));
        c.dispatchEvent(new Event('change', {bubbles: true})); }""")
    click_field(page, None, 'ticks')
    want = {'color': '#336699', 'border': 'ticks', 'moduleIds': False}
    got = settled(page, lambda: served_field(page), lambda v: v == want)
    assert got == want, got
    assert page.evaluate("() => document.querySelector('.idm-swatch-custom').classList.contains('active')")
    # the show as a file: saved, then loaded back through the load funnel
    page.evaluate("""async () => {
        const p = await (await fetch('/api/project')).json();
        await fetch('/api/project', {method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(p)});
        const text = JSON.stringify(p);
        await fetch('/api/project', {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: text});
        window.app.loadProject();
    }""")
    page.wait_for_timeout(800)
    assert page.evaluate("() => window.app.project.idmField") == want
    # a reload
    page.reload(wait_until='domcontentloaded')
    page.wait_for_function("() => window.app && window.app.project && window.app.history", timeout=15000)
    page.wait_for_timeout(800)
    assert page.evaluate("() => window.app.project.idmField") == want
    open_tab(page)
    assert page.input_value('#idm-field-custom') == '#336699'
    assert page.get_attribute('[data-idm-border="ticks"]', 'aria-pressed') == 'true'


def test_hover_arrows_shift_space_and_esc_drive_the_highlight(page):
    reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    # hover
    pt = point(page, 'IdmA', 0, 0, 0, 0)
    page.mouse.move(pt['x'], pt['y'])
    got = settled(page, lambda: hl(page), lambda v: v == ['IdmA', '0,0,0,0'])
    assert got == ['IdmA', '0,0,0,0'], got
    assert page.inner_text('#idm-hl-readout') == 'IdmA · A1 · Module A1'
    assert page.is_visible('#idm-status-readout')
    assert page.inner_text('#idm-status-readout') == 'IdmA · A1 · Module A1'
    assert 'Row 1, col 1' in page.inner_text('#idm-hl-where')
    page.mouse.move(5, 5)
    assert hl(page) == ['IdmA', '0,0,0,0']        # off the canvas it stays
    # one module at a time, across the cabinet edge
    page.keyboard.press('ArrowRight')
    assert hl(page) == ['IdmA', '0,0,1,0']
    assert page.inner_text('#idm-hl-readout') == 'IdmA · A1 · Module B1'
    page.keyboard.press('ArrowRight')
    assert hl(page) == ['IdmA', '1,0,0,0']
    assert page.inner_text('#idm-hl-readout') == 'IdmA · B1 · Module A1'
    page.keyboard.press('ArrowDown')
    assert hl(page) == ['IdmA', '1,0,0,1']
    page.keyboard.press('ArrowDown')
    assert hl(page) == ['IdmA', '1,1,0,0']
    page.keyboard.press('ArrowDown')
    assert hl(page) == ['IdmA', '1,1,0,1']
    page.keyboard.press('ArrowDown')                # the bottom edge: stops
    assert hl(page) == ['IdmA', '1,1,0,1']
    page.keyboard.press('ArrowUp')
    assert hl(page) == ['IdmA', '1,1,0,0']
    # Shift: a whole cabinet, the same module in it
    page.keyboard.press('Shift+ArrowUp')
    assert hl(page) == ['IdmA', '1,0,0,0']
    page.keyboard.press('Shift+ArrowRight')
    assert hl(page) == ['IdmA', '2,0,0,0']
    page.keyboard.press('Shift+ArrowLeft')
    page.keyboard.press('Shift+ArrowLeft')
    assert hl(page) == ['IdmA', '0,0,0,0']
    page.keyboard.press('Shift+ArrowLeft')         # the left edge: stops
    assert hl(page) == ['IdmA', '0,0,0,0']
    # past the last module of a row: on to the next screen in that row
    for _ in range(5):
        page.keyboard.press('ArrowRight')
    assert hl(page) == ['IdmA', '2,0,1,0']
    page.keyboard.press('ArrowRight')
    assert hl(page) == ['IdmB', '0,0,0,0']
    assert page.inner_text('#idm-hl-readout') == 'IdmB · A1 · Module A1'
    page.keyboard.press('ArrowRight')
    page.keyboard.press('ArrowRight')
    assert hl(page) == ['IdmB', '1,0,0,0']        # IdmB's right edge
    # Space marks it - the click's rules, one undo step - and Space again
    # clears it
    before = page.evaluate("() => window.app.historyIndex")
    page.keyboard.press('Space')
    settled(page, lambda: served_idm(page, 'IdmB'), lambda v: v and '1,0,0,0' in v['marks'])
    assert marks_of(page, 'IdmB') == {'1,0,0,0': {'style': 'color', 'color': '#ff1a1a'}}
    assert page.evaluate("() => window.app.historyIndex") == before + 1
    assert 'marked' in page.inner_text('#idm-hl-where')
    page.keyboard.press('Space')
    settled(page, lambda: served_idm(page, 'IdmB'), lambda v: v and v['marks'] == {})
    assert page.evaluate("() => window.app.historyIndex") == before + 2
    # a text field keeps its arrows and its Space
    page.evaluate("() => window.app.selectLayer(window.app.project.layers.find(x => x.name === 'IdmA'))")
    page.click('#idm-modules-x')
    page.keyboard.press('ArrowLeft')
    page.keyboard.press('Space')
    assert hl(page) == ['IdmB', '1,0,0,0']
    assert marks_of(page, 'IdmB') == {}
    page.evaluate("() => document.activeElement.blur()")
    page.evaluate("() => window.app._idmRevertFields()")
    # Esc clears it
    page.keyboard.press('Escape')
    assert hl(page) is None
    assert page.inner_text('#idm-hl-readout') == 'No module highlighted'
    assert not page.is_visible('#idm-status-readout')
    assert page.is_disabled('#idm-pad-mark')
    # with nothing highlighted an arrow starts on the selected screen
    page.keyboard.press('ArrowRight')
    assert hl(page) == ['IdmA', '0,0,0,0']
    # leaving the tab hides the status readout and keeps the highlight
    page.click('.view-tab[data-mode="pixel-map"]')
    assert not page.is_visible('#idm-status-readout')
    assert hl(page) == ['IdmA', '0,0,0,0']
    open_tab(page)
    assert page.inner_text('#idm-status-readout') == 'IdmA · A1 · Module A1'
    assert not page._errors, page._errors


def test_a_tablet_drives_the_highlight_on_the_host_output_and_it_blinks(page, e2e_server, pw_browser):
    cid = reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    out = open_output(page, cid)
    context, tab = _new_page(pw_browser, e2e_server, viewport=(820, 1180),
                             has_touch=True, is_mobile=True)
    try:
        wait_layers(tab)
        open_tab(tab)
        tab.wait_for_timeout(300)
        # the tablet layout: the Screens panel steps aside, the pad is there
        assert tab.evaluate("() => document.body.classList.contains('idm-tab')")
        assert not tab.is_visible('#right-sidebar')
        assert tab.is_visible('#idm-pad-mark') and tab.is_visible('[data-idm-step="up"]')
        assert tab.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")
        # a tap highlights - it never marks
        pt = point(tab, 'IdmA', 1, 0, 1, 1)
        tab.touchscreen.tap(pt['x'], pt['y'])
        got = settled(tab, lambda: hl(tab), lambda v: v == ['IdmA', '1,0,1,1'])
        assert got == ['IdmA', '1,0,1,1'], got
        tab.wait_for_timeout(300)
        assert marks_of(tab, 'IdmA') == {}
        assert served_idm(page, 'IdmA')['marks'] == {}
        # the host has it, and its output window shows it blinking: module
        # (1,1) of cabinet (1,0) is x 192..256, y 64..128 - white, then the
        # inverse of the white field (black)
        got = settled(page, lambda: hl(page), lambda v: v == ['IdmA', '1,0,1,1'])
        assert got == ['IdmA', '1,0,1,1'], got
        seen = set()
        for _ in range(30):
            px = pixel(out, 224, 96)
            seen.add(tuple(px) if px else None)
            out.wait_for_timeout(60)
        assert (255, 255, 255) in seen and (0, 0, 0) in seen, seen
        # the module beside it is the field (the shade's 85% there)
        assert pixel(out, 160, 96) in ([255, 255, 255], [217, 217, 217])
        # the pad: an arrow, the cabinet jump, Mark
        tab.tap('[data-idm-step="left"]')
        got = settled(page, lambda: hl(page), lambda v: v == ['IdmA', '1,0,0,1'])
        assert got == ['IdmA', '1,0,0,1'], got
        tab.tap('#idm-pad-cabinet')
        assert tab.get_attribute('#idm-pad-cabinet', 'aria-pressed') == 'true'
        tab.tap('[data-idm-step="down"]')
        got = settled(page, lambda: hl(page), lambda v: v == ['IdmA', '1,1,0,1'])
        assert got == ['IdmA', '1,1,0,1'], got
        tab.tap('#idm-pad-cabinet')
        tab.tap('#idm-pad-mark')
        got = settled(page, lambda: served_idm(page, 'IdmA'), lambda v: v and '1,1,0,1' in v['marks'])
        assert '1,1,0,1' in got['marks'], got
        settled(page, lambda: marks_of(page, 'IdmA'), lambda v: '1,1,0,1' in v)
        assert tab.inner_text('#idm-hl-readout') == 'IdmA · B2 · Module A2'
        # the host's output shows the highlight on the new module: x 128..192,
        # y 192..256, its mark (red) in the middle
        seen = set()
        for _ in range(30):
            px = pixel(out, 140, 200)
            seen.add(tuple(px) if px else None)
            out.wait_for_timeout(60)
        assert (255, 255, 255) in seen and (0, 0, 0) in seen, seen
        wait_pixel(out, 160, 224, (255, 26, 26))
        # Clear highlight on the tablet: gone from the host and the wall
        tab.tap('#idm-pad-clear')
        got = settled(page, lambda: hl(page), lambda v: v is None)
        assert got is None, got
        wait_pixel(out, 140, 200, (255, 26, 26))     # the marked module, whole again
        assert not tab._errors, tab._errors
    finally:
        context.close()
        out.close()


def test_a_deleted_screen_takes_its_highlight_with_it(page):
    reset_project(page)
    page.evaluate("""() => {
        const app = window.app, b = app.project.layers.find(x => x.name === 'IdmB');
        app._idmSetHighlight(b.id, '1,1,0,0');
    }""")
    assert hl(page) == ['IdmB', '1,1,0,0']
    page.evaluate("""() => {
        const app = window.app;
        app.selectLayer(app.project.layers.find(x => x.name === 'IdmB'));
        app.deleteCurrentLayer();
    }""")
    wait_layers(page, 1)
    got = settled(page, lambda: page.evaluate("() => window.app._idmHl()"), lambda v: v is None)
    assert got is None, got
    assert page.inner_text('#idm-hl-readout') == 'No module highlighted'


# ── 3. Pictures for the record ────────────────────────────────────────────

SHOTS = os.environ.get('LRD_IDM_SHOTS')


@pytest.mark.skipif(not SHOTS, reason='set LRD_IDM_SHOTS to a folder to save the screenshots')
def test_screenshots(page, e2e_server, pw_browser):
    cid = reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    set_layout(page, 'IdmB', 4, 4)
    page.evaluate("""() => {
        const app = window.app;
        const a = app.project.layers.find(x => x.name === 'IdmA');
        const b = app.project.layers.find(x => x.name === 'IdmB');
        a.idm.marks = {'0,0,1,0': {style: 'color', color: '#ff1a1a'}, '2,1,0,1': {style: 'x', color: '#ffd400'}};
        b.idm.marks = {'1,1,0,0': {style: 'color', color: '#00c8ff'}};
        app.updateLayers([a, b], true, 'Marks');
        window.canvasRenderer.render();
    }""")
    click_field(page, '#ff0000', 'shade')
    pt = point(page, 'IdmB', 0, 1, 2, 1)
    page.mouse.move(pt['x'], pt['y'])
    page.wait_for_timeout(450)
    page.evaluate("() => { window.app._idmS.blinkOn = true; window.canvasRenderer.render(); }")
    page.screenshot(path=os.path.join(SHOTS, 'idm-field-red-shade-highlight.png'))
    click_field(page, '#ffffff', 'shade')
    with page.expect_popup() as info:
        page.evaluate("(id) => { window.app.openOutputDisplay({canvasId: id, view: 'idm', scale: 'fit'}); }", cid)
    out = info.value
    out.set_viewport_size({'width': 1280, 'height': 720})
    settled(out, lambda: out.evaluate("() => Number(document.body.dataset.frames || 0)"), lambda n: n >= 1, 8000)
    out.wait_for_timeout(4500)
    out.screenshot(path=os.path.join(SHOTS, 'idm-field-output-white.png'))
    out.close()
    context, tab = _new_page(pw_browser, e2e_server, viewport=(820, 1180), has_touch=True, is_mobile=True)
    try:
        wait_layers(tab)
        open_tab(tab)
        tab.wait_for_timeout(400)
        tab.screenshot(path=os.path.join(SHOTS, 'idm-tablet-pad.png'))
    finally:
        context.close()
