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
  host's output window shows it. The highlight is a steady outline round
  the module (owner, 2026-11-18: no blink, no pulse), black at its edge
  and white inside that, both on the module, in the view and on the wall:
  the module's field and mark stay in view in its middle, two frames apart
  are the same pixels, nothing redraws while it stands still, and it leaves
  both when the mouse leaves the panels. It reads on a black field, all
  four sides of a corner module show on a white one, the outline of a
  module picked from the swap list stays off the wall, and the wall's log
  says what it drew once a move, never once a frame. A deleted screen
  takes its highlight with
  it, and the panel never names a module a delete, undo or redo took away,
  even before the view redraws.

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
        pg.evaluate("(id) => { window.app.openOutputDisplay({canvasId: id, view: 'idm'}); }", cid)
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
    # off the canvas the wall shows nothing; the arrows carry on from there
    settled(page, lambda: hl(page), lambda v: v is None)
    assert hl(page) is None
    assert not page.is_disabled('#idm-pad-mark')
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


def steady(out, points, samples=12, gap=80):
    """The output's pixels at `points`, read `samples` times `gap` ms apart:
    every read the same (a blink would change them), that one read."""
    seen = set()
    for _ in range(samples):
        seen.add(tuple(tuple(pixel(out, x, y) or ()) for x, y in points))
        out.wait_for_timeout(gap)
    assert len(seen) == 1, seen
    return [list(px) for px in seen.pop()]


def test_a_tablet_drives_the_highlight_on_the_host_output(page, e2e_server, pw_browser):
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
        # the host has it, and its output window outlines it, steadily:
        # module (1,1) of cabinet (1,0) is x 192..256, y 64..128, a 5 px
        # black band at its left edge (x 192..196) and a white one inside
        # it (x 197..201), the same on the right (black x 251..255 over the
        # cabinet's edge ring, white x 246..250), its middle the white field
        got = settled(page, lambda: hl(page), lambda v: v == ['IdmA', '1,0,1,1'])
        assert got == ['IdmA', '1,0,1,1'], got
        wait_pixel(out, 194, 96, (0, 0, 0))
        assert steady(out, [(194, 96), (199, 96), (253, 96), (248, 96), (224, 96)]) \
            == [[0, 0, 0], [255, 255, 255], [0, 0, 0], [255, 255, 255], [255, 255, 255]]
        # the module beside it is the field (the shade's 85% there), up to
        # its edge: the outline is all on the highlighted module
        assert pixel(out, 160, 96) == [217, 217, 217]
        assert pixel(out, 189, 96) == [217, 217, 217]
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
        # the host's output outlines the new module: x 128..192, y 192..256,
        # its mark (red) in view inside the outline, left as it is
        wait_pixel(out, 160, 224, (255, 26, 26))
        wait_pixel(out, 130, 224, (0, 0, 0))
        assert steady(out, [(125, 224), (130, 224), (135, 224), (160, 224), (140, 210)]) \
            == [[255, 255, 255], [0, 0, 0], [255, 255, 255], [255, 26, 26], [255, 26, 26]]
        # Clear highlight on the tablet: gone from the host and the wall
        tab.tap('#idm-pad-clear')
        got = settled(page, lambda: hl(page), lambda v: v is None)
        assert got is None, got
        wait_pixel(out, 130, 224, (255, 26, 26))     # the marked module, whole again
        assert not tab._errors, tab._errors
    finally:
        context.close()
        out.close()


# One module as the designer's view draws it: a hash of the frame round it,
# and the pixels just outside its left edge, just inside it (`edge`, the
# outline's black band), a little further in (`inner`, its white band) and
# in its middle (the view's canvas pixels, at the view's own zoom).
VIEW_LOOK_JS = """([name, col, row, mx, my]) => {
    const app = window.app, r = window.canvasRenderer;
    const l = app.project.layers.find(x => x.name === name);
    const p = l.panels.find(q => q.col === col && q.row === row);
    const n = r.idmCounts(l);
    const c = r.idmModuleCells(l, p, n.x, n.y, r._idmVisibleLookup(l)).find(q => q.mx === mx && q.my === my);
    const {wx, wy} = r._layerCanvasOffset(l);
    const z = r.zoom, left = Math.round(r.panX) + (c.x + wx) * z, top = Math.round(r.panY) + (c.y + wy) * z;
    const w = c.w * z, h = c.h * z;
    const at = (X, Y) => Array.from(r.ctx.getImageData(Math.round(X), Math.round(Y), 1, 1).data.slice(0, 3));
    const d = r.ctx.getImageData(Math.floor(left) - 10, Math.floor(top) - 10,
                                 Math.ceil(w) + 20, Math.ceil(h) + 20).data;
    let hash = 0;
    for (let i = 0; i < d.length; i++) hash = (Math.imul(hash, 31) + d[i]) | 0;
    return {hash, outside: at(left - 1.5, top + h / 2), edge: at(left + 1.5, top + h / 2),
            inner: at(left + 4.5, top + h / 2), middle: at(left + w / 2, top + h / 2)};
}"""


def view_look(pg, *where):
    return pg.evaluate(VIEW_LOOK_JS, list(where))


def test_the_highlight_is_a_steady_outline_in_the_view_and_on_the_wall(page):
    """Owner, 2026-11-18: no blink and no pulse - the highlighted module is
    outlined, steadily, in the view and on the wall. A black band at the
    module's edge and a white one inside it, so it reads on any field; the
    module's field and its mark (an X here) are left as
    they are in its middle. Two frames apart are the same pixels, nothing
    redraws while it stands still, and it leaves the view and the wall the
    moment the mouse leaves the panels."""
    cid = reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    click_field(page, '#ff0000', 'shade')
    page.evaluate("""() => {
        const app = window.app, a = app.project.layers.find(x => x.name === 'IdmA');
        a.idm.marks = {'1,0,1,1': {style: 'x', color: '#ffff00'}};
        app.updateLayers([a], true, 'Mark');
        window.canvasRenderer.render();
    }""")
    settled(page, lambda: marks_of(page, 'IdmA'), lambda v: '1,0,1,1' in v)
    # the mouse's arrow on the wall would sit on the module: off for this
    page.evaluate("() => window.app._idmSetPointerOn(false)")
    out = open_output(page, cid)
    try:
        # module (1,1) of cabinet (1,0): x 192..256, y 64..128 on the wall,
        # the X's crossing in its middle; beside it the red field's shade
        wait_pixel(out, 224, 96, (255, 255, 0))
        wall = [(189, 96), (194, 96), (199, 96), (224, 96)]
        bare_wall = [pixel(out, x, y) for x, y in wall]
        assert bare_wall == [[217, 0, 0], [255, 0, 0], [255, 0, 0], [255, 255, 0]], bare_wall
        bare_view = view_look(page, 'IdmA', 1, 0, 1, 1)
        pt = point(page, 'IdmA', 1, 0, 1, 1)
        page.mouse.move(pt['x'], pt['y'])
        assert settled(page, lambda: hl(page), lambda v: v == ['IdmA', '1,0,1,1']) == ['IdmA', '1,0,1,1']
        # the wall: black at the edge, white inside it, the module beside
        # it and the mark untouched - and the same at every look
        wait_pixel(out, 194, 96, (0, 0, 0))
        assert steady(out, wall) == [[217, 0, 0], [0, 0, 0], [255, 255, 255], [255, 255, 0]]
        # the view: the same outline, outside and middle as they were
        lit = view_look(page, 'IdmA', 1, 0, 1, 1)
        assert lit['edge'] == [0, 0, 0], lit
        assert lit['inner'] == [255, 255, 255], lit
        assert lit['outside'] == bare_view['outside'], (lit, bare_view)
        assert lit['middle'] == bare_view['middle'], (lit, bare_view)
        assert lit['hash'] != bare_view['hash']
        # two frames apart: the same pixels, waited for and redrawn
        page.wait_for_timeout(600)
        assert view_look(page, 'IdmA', 1, 0, 1, 1) == lit
        page.evaluate("() => window.canvasRenderer.render()")
        assert view_look(page, 'IdmA', 1, 0, 1, 1) == lit
        # nothing runs while it stands still: no redraw of the view, no new
        # frame on the wall, no blink state
        idle = page.evaluate("""async () => {
            const app = window.app, r = window.canvasRenderer;
            const real = r.render, realLay = app._outputDisplayOverlay;
            let renders = 0, lays = 0;
            r.render = function (...a) { renders += 1; return real.apply(this, a); };
            app._outputDisplayOverlay = function (...a) { lays += 1; return realLay.apply(this, a); };
            try {
                await new Promise(res => setTimeout(res, 1200));
            } finally {
                r.render = real;
                app._outputDisplayOverlay = realLay;
            }
            return {renders, lays, blink: Object.keys(app._idmS).filter(k => /blink|pulse/i.test(k))};
        }""")
        assert idle == {'renders': 0, 'lays': 0, 'blink': []}, idle
        frames = out.evaluate("() => Number(document.body.dataset.frames || 0)")
        out.wait_for_timeout(800)
        assert out.evaluate("() => Number(document.body.dataset.frames || 0)") == frames
        # the mouse off the panels: gone from the view and from the wall
        gap = page.evaluate("""() => {
            const r = window.canvasRenderer, rect = r.canvas.getBoundingClientRect();
            return {x: rect.left + Math.round(r.panX) + 480 * r.zoom,
                    y: rect.top + Math.round(r.panY) + 100 * r.zoom};
        }""")
        page.mouse.move(gap['x'], gap['y'])                # between the screens
        assert settled(page, lambda: hl(page), lambda v: v is None) is None
        wait_pixel(out, 194, 96, (255, 0, 0))
        assert [pixel(out, x, y) for x, y in wall] == bare_wall
        assert view_look(page, 'IdmA', 1, 0, 1, 1) == bare_view
        assert not page._errors, page._errors
    finally:
        page.evaluate("() => window.app._idmSetPointerOn(true)")
        out.close()


def set_hl(pg, name, key):
    pg.evaluate("""([name, key]) => {
        const app = window.app, l = app.project.layers.find(x => x.name === name);
        app._idmSetHighlight(l.id, key);
    }""", [name, key])
    assert settled(pg, lambda: hl(pg), lambda v: v == [name, key]) == [name, key]


def test_the_outline_reads_on_a_black_field_on_the_wall(page):
    """On a black field the black band is lost in the field; the white band
    inside it shows on all four sides of the module, and the module's
    middle stays the field."""
    cid = reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    click_field(page, '#000000', 'shade')
    page.evaluate("() => window.app._idmSetPointerOn(false)")
    out = open_output(page, cid)
    try:
        # module (1,1) of cabinet (1,0): x 192..256, y 64..128, black
        wait_pixel(out, 224, 96, (0, 0, 0))
        set_hl(page, 'IdmA', '1,0,1,1')
        # white 5 px in from each edge (left, right, top, bottom), black at
        # each edge, the middle the field
        wait_pixel(out, 199, 96, (255, 255, 255))
        white = [(199, 96), (248, 96), (224, 71), (224, 120)]
        black = [(194, 96), (253, 96), (224, 66), (224, 125)]
        assert steady(out, white + black + [(224, 96)]) \
            == [[255, 255, 255]] * 4 + [[0, 0, 0]] * 4 + [[0, 0, 0]]
        assert not page._errors, page._errors
    finally:
        page.evaluate("() => { window.app._idmSetPointerOn(true); window.app._idmClearHighlight(); }")
        out.close()


# Every idm_output_highlight line the page sends to the log, from now on.
LOG_SPY_JS = """() => {
    window.__hlLogs = [];
    if (window.__hlLogReal) return;
    const real = navigator.sendBeacon.bind(navigator);
    window.__hlLogReal = real;
    navigator.sendBeacon = (url, blob) => {
        try {
            blob.text().then(t => {
                try {
                    const p = JSON.parse(t);
                    if (p.action === 'idm_output_highlight') window.__hlLogs.push(p.details);
                } catch (_) { /* not JSON */ }
            });
        } catch (_) { /* not a blob */ }
        return real(url, blob);
    };
}"""

LOG_SPY_OFF_JS = """() => {
    if (window.__hlLogReal) navigator.sendBeacon = window.__hlLogReal;
    delete window.__hlLogReal;
}"""


def hl_logs(pg):
    return pg.evaluate("() => JSON.parse(JSON.stringify(window.__hlLogs || []))")


def test_a_corner_module_keeps_all_four_sides_on_a_white_field(page):
    """A module in the canvas's corner on a plain white field: the white
    band is lost in the field and the black band sits on the module, so
    none of it falls past the canvas's edge - all four sides show, on the
    wall and in the view. The wall's log says what it drew: one line when
    the output opens, one when the highlight lands, none while it stands
    still."""
    cid = reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    click_field(page, '#ffffff', 'none')
    page.evaluate("() => window.app._idmSetPointerOn(false)")
    page.evaluate(LOG_SPY_JS)
    out = open_output(page, cid)
    try:
        # module (0,0) of cabinet (0,0): x 0..64, y 0..64, the canvas's
        # top-left corner
        wait_pixel(out, 32, 32, (255, 255, 255), tol=0)
        page.wait_for_function("() => window.__hlLogs.length >= 1", timeout=4000)
        set_hl(page, 'IdmA', '0,0,0,0')
        wait_pixel(out, 2, 32, (0, 0, 0))
        # black 5 px on each side (left, right, top, bottom, two corners),
        # white inside it and in the middle, the next module white
        black = [(2, 32), (61, 32), (32, 2), (32, 61), (0, 0), (63, 63)]
        assert steady(out, black + [(7, 32), (32, 32), (66, 32)]) \
            == [[0, 0, 0]] * 6 + [[255, 255, 255]] * 3
        lit = view_look(page, 'IdmA', 0, 0, 0, 0)
        assert lit['edge'] == [0, 0, 0], lit
        assert lit['inner'] == [255, 255, 255], lit
        # the log: the open (no highlight), then the module as drawn ...
        page.wait_for_function("() => window.__hlLogs.length >= 2", timeout=4000)
        # ... and standing still, laid over again: no more lines
        page.evaluate("() => { window.app._outputDisplayOverlay(null); window.app._outputDisplayOverlay(null); }")
        page.wait_for_timeout(1200)
        logs = hl_logs(page)
        assert len(logs) == 2, logs
        assert logs[0]['highlight'] == 'none' and logs[0]['canvasId'] == cid, logs
        a_id = page.evaluate("() => window.app.project.layers.find(x => x.name === 'IdmA').id")
        keys = ('highlight', 'canvasId', 'layerId', 'key', 'x', 'y', 'w', 'h', 'outerPx', 'innerPx')
        got = {k: logs[1].get(k) for k in keys}
        assert got == {'highlight': 'outline', 'canvasId': cid, 'layerId': a_id, 'key': '0,0,0,0',
                       'x': 0, 'y': 0, 'w': 64, 'h': 64, 'outerPx': 5, 'innerPx': 5}, logs
        assert not page._errors, page._errors
    finally:
        page.evaluate(LOG_SPY_OFF_JS)
        page.evaluate("() => { window.app._idmSetPointerOn(true); window.app._idmClearHighlight(); }")
        out.close()


FLASHING_JS = """() => !!window.app._idmFlashFor(
    window.app.project.layers.find(x => x.name === 'IdmA'))"""


def test_the_swap_list_outline_stays_off_the_wall(page):
    """A module picked from the swap list is outlined in the accent in the
    view for a moment; the wall output never shows it, even on a frame
    drawn from scratch while it is up."""
    cid = reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    click_field(page, '#ffffff', 'none')
    page.evaluate("""() => {
        const app = window.app, a = app.project.layers.find(x => x.name === 'IdmA');
        a.idm.marks = {'1,0,1,1': {style: 'x', color: '#ffff00'}};
        app.updateLayers([a], true, 'Mark');
        window.canvasRenderer.render();
    }""")
    settled(page, lambda: marks_of(page, 'IdmA'), lambda v: '1,0,1,1' in v)
    page.evaluate("() => window.app._idmSetPointerOn(false)")
    out = open_output(page, cid)
    try:
        # module (1,1) of cabinet (1,0): x 192..256, y 64..128, the X's
        # crossing in its middle
        wait_pixel(out, 224, 96, (255, 255, 0))
        wall = [(194, 96), (199, 96), (224, 96), (224, 66)]
        bare_wall = [pixel(out, x, y) for x, y in wall]
        bare_view = view_look(page, 'IdmA', 1, 0, 1, 1)
        accent = page.evaluate("""() => {
            const c = document.createElement('canvas').getContext('2d');
            c.fillStyle = getComputedStyle(document.documentElement)
                .getPropertyValue('--ps-accent').trim() || '#e22330';
            c.fillRect(0, 0, 1, 1);
            return Array.from(c.getImageData(0, 0, 1, 1).data.slice(0, 3));
        }""")
        frames = out.evaluate("() => Number(document.body.dataset.frames || 0)")
        # the pick, and a wall frame drawn from scratch while it is up
        page.evaluate("""() => {
            const app = window.app, a = app.project.layers.find(x => x.name === 'IdmA');
            app._idmFlashModule(a.id, '1,0,1,1');
            app._outputDisplayRefresh(true);
        }""")
        assert page.evaluate(FLASHING_JS)
        settled(out, lambda: out.evaluate("() => Number(document.body.dataset.frames || 0)"),
                lambda n: n > frames)
        # the view outlines it in the accent ...
        lit = view_look(page, 'IdmA', 1, 0, 1, 1)
        assert lit['edge'] == [0, 0, 0], lit
        assert all(abs(a - b) <= 3 for a, b in zip(lit['inner'], accent)), (lit, accent)
        assert lit['middle'] == bare_view['middle'], (lit, bare_view)
        # ... the wall shows the module as it was
        assert page.evaluate(FLASHING_JS)
        assert [pixel(out, x, y) for x, y in wall] == bare_wall
        assert not page._errors, page._errors
    finally:
        page.evaluate("() => window.app._idmSetPointerOn(true)")
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


# The panel as the page shows it: readout, where line, status bar, the pad's
# Mark and Clear, the mark list.
PANEL_JS = """() => {
    const q = (id) => document.getElementById(id);
    return {readout: q('idm-hl-readout').textContent, where: q('idm-hl-where').textContent,
            status: q('idm-status-readout').textContent, statusHidden: q('idm-status-readout').hidden,
            markDisabled: q('idm-pad-mark').disabled, clearDisabled: q('idm-pad-clear').disabled,
            list: q('idm-list').textContent,
            hl: window.app._idmHl(), deleting: !!window.app.deletionInProgress};
}"""


def test_the_panel_follows_the_highlight_as_the_delete_reply_lands(page):
    """A delete's reply replaces the project (the highlight on the deleted
    screen gone with it) and the delete's own redraw waits for the next
    request. The panel follows the reply at once: it never names a module
    of the screen that is gone. (1.7.0 CI: the readout still read
    'IdmB · B2 · Module A1' with no highlight left, until the next redraw.)
    The page's request for the project after the DELETE is held, and the
    panel read in the same task as the reply, so the redraw cannot come in
    between."""
    reset_project(page)
    page.evaluate("""() => {
        const app = window.app, b = app.project.layers.find(x => x.name === 'IdmB');
        b.idm = {modulesX: 2, modulesY: 2, marks: {'0,0,0,0': {style: 'color', color: '#ff1a1a'}}};
        app.updateLayers([b], true, 'Set Modules');
        window.canvasRenderer.render();
    }""")
    settled(page, lambda: marks_of(page, 'IdmB'), lambda v: '0,0,0,0' in v)
    page.evaluate("""() => {
        const app = window.app, b = app.project.layers.find(x => x.name === 'IdmB');
        app._idmSetHighlight(b.id, '1,1,0,0');
    }""")
    assert hl(page) == ['IdmB', '1,1,0,0']
    before = page.evaluate(PANEL_JS)
    steps = page.evaluate("() => window.app.history.length")
    assert before['readout'].startswith('IdmB'), before
    assert 'IdmB' in before['list'], before
    page.evaluate("""(PANEL) => {
        const read = eval(PANEL), real = window.fetch;
        let release, deleted = false;
        const gate = new Promise(r => { release = r; });
        window.__idmGet = {release: () => { window.fetch = real; release(); }, panel: null};
        window.fetch = function (url, opts) {
            const method = (opts && opts.method) || 'GET';
            if (method === 'DELETE' && String(url).includes('/api/layer/')) deleted = true;
            else if (deleted && method === 'GET' && String(url).endsWith('/api/project')) {
                deleted = false;
                window.__idmGet.panel = read();
                return gate.then(() => real.call(window, url, opts));
            }
            return real.call(window, url, opts);
        };
        const app = window.app;
        app.selectLayer(app.project.layers.find(x => x.name === 'IdmB'));
        app.deleteCurrentLayer();
    }""", PANEL_JS)
    try:
        page.wait_for_function("() => window.__idmGet.panel !== null", timeout=10000)
        at_reply = page.evaluate("() => window.__idmGet.panel")
    finally:
        page.evaluate("() => window.__idmGet.release()")
    # the reply has landed and the delete is not done
    assert at_reply['deleting'] is True and at_reply['hl'] is None, at_reply
    assert at_reply['readout'] == 'No module highlighted', at_reply
    assert at_reply['where'] == 'Point at a module, tap it, or use the arrows.', at_reply
    assert at_reply['status'] == '' and at_reply['statusHidden'] is True, at_reply
    assert at_reply['markDisabled'] is True and at_reply['clearDisabled'] is True, at_reply
    assert 'IdmB' not in at_reply['list'], at_reply
    page.wait_for_function("(n) => !window.app.deletionInProgress && window.app.history.length === n + 1",
                           arg=steps, timeout=10000)
    end = page.evaluate(PANEL_JS)
    assert {k: end[k] for k in ('readout', 'where', 'status', 'statusHidden', 'markDisabled', 'clearDisabled')} \
        == {k: at_reply[k] for k in ('readout', 'where', 'status', 'statusHidden', 'markDisabled', 'clearDisabled')}
    assert 'IdmB' not in end['list'], end
    assert not page._errors, page._errors


NOTHING_NAMED = {'readout': 'No module highlighted', 'where': 'Point at a module, tap it, or use the arrows.',
                 'status': '', 'statusHidden': True}


def _panel_after(pg, call):
    """window.app[call]() and the panel read in the same task: the restore
    is on its way to the server and nothing has redrawn yet. The highlight
    itself stays until the next look at it drops it, a moment later (a
    highlight is view state, never an undo step), and the pad's Mark and
    Clear go with it."""
    got = pg.evaluate("([PANEL, call]) => { window.app[call](); return eval(PANEL)(); }", [PANEL_JS, call])
    pg.wait_for_function("() => !window.app._restorePutPending", timeout=10000)
    assert got['hl'] is not None, got
    after = settled(pg, lambda: pg.evaluate(PANEL_JS), lambda v: v['hl'] is None)
    assert after['markDisabled'] is True and after['clearDisabled'] is True, after
    assert {k: after[k] for k in NOTHING_NAMED} == NOTHING_NAMED, after
    return {k: got[k] for k in NOTHING_NAMED}


def test_the_panel_follows_an_undo_or_redo_that_takes_the_module_away(page):
    """An undo or redo that takes the highlighted module away (the screen's
    modules across and down put back) leaves the panel naming nothing from
    the moment it is pressed, not from the redraw once the restore lands."""
    reset_project(page)
    set_layout(page, 'IdmB', 2, 2)
    settled(page, lambda: page.evaluate("() => window.app.history.length"), lambda v: v == 2)
    set_layout(page, 'IdmB', 1, 1)
    settled(page, lambda: page.evaluate("() => window.app.history.length"), lambda v: v == 3)
    page.evaluate("() => window.app.undo()")
    page.wait_for_function("() => !window.app._restorePutPending && window.app.historyIndex === 1", timeout=10000)
    # redo to the 1 x 1 layout: module 1,1,1,1 of the 2 x 2 goes
    page.evaluate("() => { const app = window.app; app._idmSetHighlight("
                  "app.project.layers.find(x => x.name === 'IdmB').id, '1,1,1,1'); }")
    assert page.inner_text('#idm-hl-readout') == 'IdmB · B2 · Module B2'
    assert _panel_after(page, 'redo') == NOTHING_NAMED
    page.evaluate("() => window.app.undo()")
    page.wait_for_function("() => !window.app._restorePutPending && window.app.historyIndex === 1", timeout=10000)
    # undo to the screen with no modules set: the same module goes
    page.evaluate("() => { const app = window.app; app._idmSetHighlight("
                  "app.project.layers.find(x => x.name === 'IdmB').id, '1,1,1,1'); }")
    assert page.inner_text('#idm-hl-readout') == 'IdmB · B2 · Module B2'
    assert _panel_after(page, 'undo') == NOTHING_NAMED
    assert page.evaluate("() => window.app.historyIndex") == 0
    assert not page._errors, page._errors


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
    page.screenshot(path=os.path.join(SHOTS, 'idm-field-red-shade-highlight.png'))
    click_field(page, '#ffffff', 'shade')
    with page.expect_popup() as info:
        page.evaluate("(id) => { window.app.openOutputDisplay({canvasId: id, view: 'idm'}); }", cid)
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
