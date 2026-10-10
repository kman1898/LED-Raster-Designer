"""View > Output to Display: one canvas's raster in its own window, for a
second monitor feeding an LED processor input.

The window (/output) holds pixels only; the designer window renders the
chosen canvas with its own renderer - the export recipe, onto an offscreen
canvas - and hands every frame over. Pinned here:

* the route serves the bare page (no-store, the page script, no app chrome);
* the output shows THE CHOSEN canvas, at its own raster size, in both scale
  modes - Fit sizes it into the window, 1:1 puts one raster pixel on one
  device pixel (CSS size = raster / devicePixelRatio);
* it is live: a local edit, its undo, and a layer edit another client makes
  through the server all reach the picture;
* the dialog lists the open outputs and closes them, Esc in an output with
  no full screen closes it, and closing the designer window closes its
  outputs;
* the canvas right-click menu offers it on the canvas only.

Run locally:
    python -m pytest tests/test_output_display.py -v --browser chromium
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

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project exactly as this module found it
    (see conftest.server_project_guard)."""


def _new_page(pw_browser, url, **context_args):
    context = pw_browser.new_context(**context_args)
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(url, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app.project && window.app.history", timeout=15000)
    pg.wait_for_timeout(800)
    return context, pg


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context, pg = _new_page(pw_browser, e2e_server)
    yield pg
    context.close()


# Two canvases with different rasters and one screen each:
#   c1 1920x1080, "OutA" 4x2 cabinets of 128 at (0, 0)  -> 512 x 256
#   c2  640x360,  "OutB" 2x1 cabinets of 160 at (0, 0)  -> 320 x 160
# c2 sits right of c1 in the workspace, so a render that forgot to pan to
# the canvas's own corner would show nothing of it.
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
    await post('/api/layer/add', {name: 'OutA', columns: 4, rows: 2,
        cabinet_width: 128, cabinet_height: 128, offset_x: 0, offset_y: 0,
        canvas_id: first.id});
    const made = await (await post('/api/canvas', {raster_width: 640, raster_height: 360})).json();
    const c2 = (made.canvases || []).find(c => c.id !== first.id);
    await put('/api/canvas/' + c2.id, {raster_width: 640, raster_height: 360,
        show_raster_width: 640, show_raster_height: 360});
    await post('/api/layer/add', {name: 'OutB', columns: 2, rows: 1,
        cabinet_width: 160, cabinet_height: 160, offset_x: 0, offset_y: 0,
        canvas_id: c2.id});
    await put('/api/canvas/' + first.id + '/active', {});
    window.app.closeAllOutputDisplays();
    window.app.loadProject();
    return {c1: first.id, c2: c2.id};
}"""


def reset_project(page):
    ids = page.evaluate(RESET_JS)
    page.wait_for_function(
        "() => window.app.project && (window.app.project.layers || []).length === 2"
        " && (window.app.project.canvases || []).length === 2", timeout=10000)
    page.wait_for_timeout(600)
    return ids


def pixel(pg, x, y):
    return pg.evaluate("""([x, y]) => {
        const c = document.getElementById('output-canvas');
        if (!c.width || x >= c.width || y >= c.height) return null;
        return Array.from(c.getContext('2d').getImageData(x, y, 1, 1).data.slice(0, 3));
    }""", [x, y])


def lit(px):
    return px is not None and sum(px) > 30


def black(px):
    return px is not None and sum(px) <= 30


def frames(pg):
    return pg.evaluate("() => Number(document.body.dataset.frames || 0)")


def canvas_box(pg):
    return pg.evaluate("""() => {
        const c = document.getElementById('output-canvas');
        return {w: c.width, h: c.height,
                cssW: parseFloat(c.style.width), cssH: parseFloat(c.style.height),
                left: parseFloat(c.style.left), top: parseFloat(c.style.top),
                vw: innerWidth, vh: innerHeight, dpr: devicePixelRatio};
    }""")


def open_from_dialog(page, canvas_id, view='pixel-map', scale='fit'):
    page.evaluate("window.app.handleMenuAction('output-to-display')")
    page.wait_for_selector('#output-display-modal', state='visible')
    page.select_option('#output-display-canvas', canvas_id)
    page.select_option('#output-display-view', view)
    page.check(f'input[name="output-display-scale"][value="{scale}"]')
    with page.expect_popup() as info:
        page.click('#output-display-open')
    out = info.value
    out.wait_for_load_state('domcontentloaded')
    settled(out, lambda: frames(out), lambda n: n >= 1, 8000)
    assert frames(out) >= 1, 'the output never received a frame'
    return out


def close_dialog(page):
    page.evaluate("window.app.closeOutputDisplayDialog()")


# ── the route ─────────────────────────────────────────────────────────────

def test_output_route_serves_the_bare_page(client):
    res = client.get('/output?canvas=c1&view=pixel-map&scale=fit')
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert 'id="output-canvas"' in html
    assert '/static/js/output-display.js' in html
    # No app chrome: no menu bar, no app modules.
    assert 'menu-bar' not in html and 'main.js' not in html
    assert 'no-store' in res.headers.get('Cache-Control', '')
    assert os.path.isfile(os.path.join(ROOT, 'src', 'static', 'js', 'output-display.js'))


# ── the picture ───────────────────────────────────────────────────────────

def test_fit_output_shows_the_chosen_canvas_at_its_raster_size(page):
    ids = reset_project(page)
    out = open_from_dialog(page, ids['c2'], scale='fit')
    try:
        box = canvas_box(out)
        assert (box['w'], box['h']) == (640, 360), box
        # Fit: as large as the window allows, aspect kept, centred.
        s = min(box['vw'] / 640, box['vh'] / 360)
        assert abs(box['cssW'] - 640 * s) < 1 and abs(box['cssH'] - 360 * s) < 1, box
        assert abs(box['left'] - (box['vw'] - box['cssW']) / 2) < 1, box
        assert abs(box['top'] - (box['vh'] - box['cssH']) / 2) < 1, box
        # c2's own screen, drawn from c2's corner - not c1's wider screen.
        assert lit(pixel(out, 80, 80)), pixel(out, 80, 80)
        assert black(pixel(out, 450, 200)), pixel(out, 450, 200)
        assert black(pixel(out, 600, 330)), pixel(out, 600, 330)
        assert out.title().startswith('Canvas 2 · Pixel Map · Fit to display')
    finally:
        close_dialog(page)
        out.close()


def test_one_to_one_output_puts_a_raster_pixel_on_a_device_pixel(e2e_server, pw_browser, page):
    ids = reset_project(page)
    context, pg = _new_page(pw_browser, e2e_server, device_scale_factor=2)
    try:
        with pg.expect_popup() as info:
            pg.evaluate("(id) => { window.app.openOutputDisplay("
                        "{canvasId: id, view: 'pixel-map', scale: '1to1'}); }", ids['c1'])
        out = info.value
        settled(out, lambda: frames(out), lambda n: n >= 1, 8000)
        box = canvas_box(out)
        assert box['dpr'] == 2, box
        assert (box['w'], box['h']) == (1920, 1080), box
        assert (box['cssW'], box['cssH']) == (960, 540), box
        assert (box['left'], box['top']) == (0, 0), box
        assert out.evaluate("getComputedStyle(document.getElementById('output-canvas')).imageRendering") == 'pixelated'
        assert lit(pixel(out, 450, 200)), pixel(out, 450, 200)
        assert black(pixel(out, 700, 600)), pixel(out, 700, 600)
        # Closing the designer window takes its outputs with it.
        with out.expect_event('close', timeout=5000):
            pg.close()
        assert out.is_closed()
    finally:
        context.close()


# ── live ──────────────────────────────────────────────────────────────────

def test_output_follows_local_edits_undo_and_other_clients(page, e2e_server):
    ids = reset_project(page)
    out = open_from_dialog(page, ids['c1'], scale='fit')
    close_dialog(page)
    try:
        before = pixel(out, 450, 200)
        assert lit(before)
        assert black(pixel(out, 1300, 100))
        green = lambda px: px is not None and px[1] > 200 and px[0] < 60 and px[2] < 60  # noqa: E731

        # A local edit: the screen's cabinet colours.
        page.evaluate("""() => {
            const app = window.app;
            const l = app.project.layers.find(x => x.name === 'OutA');
            l.color1 = {r: 0, g: 255, b: 0}; l.color2 = {r: 0, g: 255, b: 0};
            app.saveState('Recolour OutA');
            window.canvasRenderer.render();
        }""")
        got = settled(out, lambda: pixel(out, 450, 200), green)
        assert green(got), got

        # Its undo.
        page.evaluate("window.app.handleMenuAction('undo')")
        got = settled(out, lambda: pixel(out, 450, 200), lambda px: px == before)
        assert got == before, (got, before)

        # Another client's edit, through the server: layer_updated reaches
        # this window and the output follows it.
        layer_id = page.evaluate(
            "() => window.app.project.layers.find(x => x.name === 'OutA').id")
        req = urllib.request.Request(
            f'{e2e_server}/api/layer/{layer_id}',
            data=json.dumps({'offset_y': 700}).encode('utf-8'),
            headers={'Content-Type': 'application/json'}, method='PUT')
        urllib.request.urlopen(req).read()
        got = settled(out, lambda: (pixel(out, 450, 200), pixel(out, 450, 800)),
                      lambda v: black(v[0]) and lit(v[1]))
        assert black(got[0]) and lit(got[1]), got
    finally:
        out.close()


def test_panning_the_designer_does_not_redraw_the_output(page):
    ids = reset_project(page)
    out = open_from_dialog(page, ids['c1'])
    close_dialog(page)
    try:
        page.wait_for_timeout(500)
        before = frames(out)
        page.evaluate("""() => {
            const r = window.canvasRenderer;
            r.panX += 40; r.render(); r.zoom *= 1.1; r.render();
        }""")
        page.wait_for_timeout(600)
        assert frames(out) == before, 'a view-only change re-rendered the output'
    finally:
        out.close()


# ── the dialog's list, closing ────────────────────────────────────────────

def test_dialog_lists_and_closes_outputs(page):
    ids = reset_project(page)
    out = open_from_dialog(page, ids['c2'], view='cabinet-id', scale='1to1')
    rows = page.locator('#output-display-open-list .od-open-row')
    assert rows.count() == 1
    assert rows.first.inner_text().startswith('Canvas 2 · Cabinet ID · 1:1 pixel')
    assert page.evaluate("window.app.listOutputDisplays().length") == 1
    with out.expect_event('close', timeout=5000):
        rows.first.locator('button').click()
    assert out.is_closed()
    assert page.evaluate("window.app.listOutputDisplays().length") == 0
    assert page.locator('#output-display-open-section').is_hidden()
    close_dialog(page)


def test_escape_out_of_full_screen_closes_the_output(page):
    ids = reset_project(page)
    out = open_from_dialog(page, ids['c1'])
    close_dialog(page)
    assert out.locator('#output-hint').inner_text().startswith('Click or press F for full screen')
    # keydown alone: the window is gone before a keyup could reach it.
    with out.expect_event('close', timeout=5000):
        out.keyboard.down('Escape')
    settled(page, lambda: page.evaluate("window.app.listOutputDisplays().length"),
            lambda n: n == 0)
    assert page.evaluate("window.app.listOutputDisplays().length") == 0


def test_a_deleted_canvas_says_so_instead_of_drawing(page):
    ids = reset_project(page)
    out = open_from_dialog(page, ids['c2'])
    close_dialog(page)
    try:
        page.evaluate("""(id) => {
            const app = window.app;
            app.project.canvases = app.project.canvases.filter(c => c.id !== id);
            window.canvasRenderer.render();
        }""", ids['c2'])
        msg = settled(out, lambda: out.evaluate(
            "() => document.getElementById('output-message').hidden ? '' : "
            "document.getElementById('output-message').textContent"), lambda t: bool(t))
        assert 'no longer in the project' in msg
    finally:
        out.close()
        reset_project(page)


# ── the menus ─────────────────────────────────────────────────────────────

def test_view_menu_and_canvas_right_click_offer_it(page):
    ids = reset_project(page)
    assert page.locator('#menu-view [data-action="output-to-display"]').count() == 1
    box = page.locator('#main-canvas').bounding_box()
    page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2, button='right')
    item = page.locator('#context-menu [data-action="output-canvas-to-display"]')
    assert item.is_visible()
    picked = page.evaluate("window.app._outputDisplayMenuCanvasId")
    assert picked in (ids['c1'], ids['c2'])
    item.click()
    page.wait_for_selector('#output-display-modal', state='visible')
    assert page.input_value('#output-display-canvas') == picked
    close_dialog(page)
    # Not offered off the canvas (a Screens panel row).
    page.keyboard.press('Escape')
    row = page.locator('#layers-list .layer-item').first
    if row.count():
        rb = row.bounding_box()
        page.mouse.click(rb['x'] + 10, rb['y'] + rb['height'] / 2, button='right')
        assert not item.is_visible()
    page.evaluate("window.app.hideContextMenu()")
