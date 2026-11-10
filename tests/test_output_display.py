"""View > Output to Display: one canvas's raster in its own window, for a
second monitor feeding an LED processor input.

The window (/output) holds pixels only; the designer window renders the
chosen canvas with its own renderer - the export recipe, onto an offscreen
canvas - and hands every frame over. Pinned here:

* the route serves the bare page (no-store, the page script, no app chrome);
* the output shows THE CHOSEN canvas, at its own raster size, always 1:1 -
  one canvas pixel per display pixel at the resolution the OS shows for the
  display, from the top-left corner (Matt, 2026-11-09: "a 1920 canvas on a
  4K display would fill the top left quadrant"). On a Mac that is one per
  CSS pixel (a point: macOS shows "looks like" resolutions); on Windows one
  per device pixel (CSS size = raster / devicePixelRatio, Windows shows the
  display's pixels). What the canvas leaves unused, and everything past it,
  is black. A canvas bigger than the display is not shown: the output says
  so. There is no scale to pick: the dialog has no scale control, and a
  'fit' left on an output's address or passed by old code opens 1:1 all the
  same;
* in the desktop app (a native host registered with the server) the dialog
  lists the app's displays, warns when the canvas is bigger than the chosen
  one, and Open asks the app for a native window there; that window is fed
  through the server (/output?feed=), closes on Esc, from the dialog's list
  and with the designer;
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

pw_api = pytest.importorskip("playwright.sync_api", reason="playwright not installed")


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


def open_from_dialog(page, canvas_id, view='pixel-map'):
    page.evaluate("window.app.handleMenuAction('output-to-display')")
    page.wait_for_selector('#output-display-modal', state='visible')
    page.select_option('#output-display-canvas', canvas_id)
    page.select_option('#output-display-view', view)
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
    res = client.get('/output?canvas=c1&view=pixel-map')
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert 'id="output-canvas"' in html
    assert '/static/js/output-display.js' in html
    # No app chrome: no menu bar, no app modules.
    assert 'menu-bar' not in html and 'main.js' not in html
    assert 'no-store' in res.headers.get('Cache-Control', '')
    assert os.path.isfile(os.path.join(ROOT, 'src', 'static', 'js', 'output-display.js'))


# ── the picture ───────────────────────────────────────────────────────────

def test_the_dialog_has_no_scale_control_and_says_1_to_1(page):
    ids = reset_project(page)
    page.evaluate("window.app.handleMenuAction('output-to-display')")
    page.wait_for_selector('#output-display-modal', state='visible')
    try:
        page.select_option('#output-display-canvas', ids['c2'])
        modal = page.locator('#output-display-modal')
        assert modal.locator('input[name="output-display-scale"]').count() == 0
        assert modal.locator('input[type="radio"]').count() == 0
        text = modal.inner_text()
        assert 'Scale' not in text and 'Fit to display' not in text, text
        note = page.inner_text('#output-display-note')
        assert note.startswith('Canvas 640 × 360 at 1:1: one canvas pixel per display pixel, '
                               "at the display's resolution, from the top-left corner."), note
        tip = page.get_attribute('#output-display-open', 'data-tooltip')
        assert 'scale' not in tip and 'one canvas pixel per display pixel' in tip, tip
    finally:
        close_dialog(page)


def test_output_shows_the_chosen_canvas_at_exactly_its_raster_size(page):
    ids = reset_project(page)
    out = open_from_dialog(page, ids['c2'])
    try:
        box = canvas_box(out)
        assert (box['w'], box['h']) == (640, 360), box
        # 1:1 from the top-left corner, whatever the window's size (a
        # display at devicePixelRatio 1: the same on every OS).
        assert box['dpr'] == 1, box
        assert (box['cssW'], box['cssH']) == (640, 360), box
        assert (box['left'], box['top']) == (0, 0), box
        assert 'scale' not in out.url, out.url
        # c2's own screen, drawn from c2's corner - not c1's wider screen.
        assert lit(pixel(out, 80, 80)), pixel(out, 80, 80)
        assert black(pixel(out, 450, 200)), pixel(out, 450, 200)
        assert black(pixel(out, 600, 330)), pixel(out, 600, 330)
        assert out.title().startswith('Canvas 2 · Pixel Map · Output'), out.title()
    finally:
        close_dialog(page)
        out.close()


def test_a_saved_fit_opens_as_1_to_1(page):
    """'fit' from before the ruling, by either road it could come back: a
    call that still passes it, and an output window whose address still
    carries ?scale=fit (taken back by _outputDisplayAttach)."""
    ids = reset_project(page)
    with page.expect_popup() as info:
        page.evaluate("(id) => { window.app.openOutputDisplay("
                      "{canvasId: id, view: 'pixel-map', scale: 'fit'}); }", ids['c2'])
    out = info.value
    try:
        settled(out, lambda: frames(out), lambda n: n >= 1, 8000)
        box = canvas_box(out)
        assert (box['w'], box['h']) == (640, 360), box
        assert (box['cssW'], box['cssH']) == (640, 360), box
        assert (box['left'], box['top']) == (0, 0), box
        assert 'scale' not in out.url, out.url
    finally:
        out.close()
    with page.expect_popup() as info:
        page.evaluate("(id) => { window.open('/output?canvas=' + id + '&view=pixel-map&scale=fit',"
                      " 'lrd-output-old', 'popup=yes,width=900,height=600'); }", ids['c2'])
    out = info.value
    try:
        settled(out, lambda: frames(out), lambda n: n >= 1, 8000)
        box = canvas_box(out)
        assert (box['w'], box['h']) == (640, 360), box
        assert (box['cssW'], box['cssH']) == (640, 360), box
        assert (box['left'], box['top']) == (0, 0), box
        assert out.evaluate("window.lrdOutput.params") == {'canvas': ids['c2'], 'view': 'pixel-map'}
        listed = page.evaluate("window.app.listOutputDisplays()")
        assert len(listed) == 1 and 'scale' not in listed[0], listed
        assert listed[0]['label'] == 'Canvas 2 · Pixel Map', listed
    finally:
        out.close()


def test_closing_the_designer_closes_its_browser_outputs(e2e_server, pw_browser, page):
    ids = reset_project(page)
    context, pg = _new_page(pw_browser, e2e_server)
    try:
        with pg.expect_popup() as info:
            pg.evaluate("(id) => { window.app.openOutputDisplay({canvasId: id, view: 'pixel-map'}); }", ids['c2'])
        out = info.value
        settled(out, lambda: frames(out), lambda n: n >= 1, 8000)
        with out.expect_event('close', timeout=5000):
            pg.close()
        assert out.is_closed()
    finally:
        context.close()


class _FakeNativeHost:
    """What the launcher registers (output_native.NativeOutputHost), minus
    the windows: the test opens the output's address itself."""

    def __init__(self, displays):
        self._displays = displays
        self.opened = []
        self.closed = []
        self._open = set()
        self.on_closed = None

    def displays(self):
        return self._displays

    def open(self, output_id, display, path, title):
        self.opened.append({'id': output_id, 'display': display, 'path': path, 'title': title})
        self._open.add(output_id)
        return self._displays[display]

    def close(self, output_id):
        self.closed.append(output_id)
        self._open.discard(output_id)
        return True

    def open_ids(self):
        return list(self._open)


NATIVE_DISPLAYS = [
    {'index': 0, 'name': 'Built-in Retina Display', 'x': 0, 'y': 0, 'width': 1512, 'height': 982, 'scale': 2.0, 'main': True},
    {'index': 1, 'name': 'LED Processor', 'x': 1512, 'y': 0, 'width': 1920, 'height': 1080, 'scale': 1.0, 'main': False},
    {'index': 2, 'name': 'Small', 'x': 3432, 'y': 0, 'width': 640, 'height': 360, 'scale': 1.0, 'main': False},
]


@pytest.fixture
def native_host():
    import routes_output
    host = _FakeNativeHost(NATIVE_DISPLAYS)
    routes_output.set_native_host(host)
    yield host
    routes_output.set_native_host(None)


def _wait_opened(pg, host, n):
    settled(pg, lambda: len(host.opened), lambda k: k >= n, 8000)
    assert len(host.opened) >= n, 'the app was never asked for the window'
    return host.opened[n - 1]


def _platform_script(platform):
    return ("Object.defineProperty(Navigator.prototype, 'platform', "
            "{get: () => '%s', configurable: true});" % platform)


def _output_in(pw_browser, e2e_server, host, canvas_id, platform, dpr, screen, viewport=None):
    """A designer page and one output of `canvas_id`, as `platform` would
    show it on a display the browser reports as `screen` (CSS pixels) at
    devicePixelRatio `dpr`. The output is a native one (the app's window
    stood in for by a page of this context, at the address the app was
    given): a browser popup reports its own window size as the screen."""
    viewport = viewport or screen
    context = pw_browser.new_context(device_scale_factor=dpr, screen=screen, viewport=viewport)
    context.add_init_script(_platform_script(platform))
    context.add_init_script("try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app.project && window.app.history", timeout=15000)
    pg.wait_for_timeout(500)
    n = len(host.opened)
    pg.evaluate("(id) => { window.app.openOutputDisplay({canvasId: id, view: 'pixel-map',"
                " screen: {native: true, index: 1, label: 'LED Processor'}}); }", canvas_id)
    opened = _wait_opened(pg, host, n + 1)
    out = context.new_page()
    out.goto(e2e_server + opened['path'], wait_until='domcontentloaded')
    settled(out, lambda: frames(out), lambda k: k >= 1, 8000)
    assert frames(out) >= 1, 'the output never received a frame'
    out.wait_for_timeout(100)
    return context, pg, out


def _shot_pixel(out, x, y):
    """The colour the window shows at CSS (x, y): a screenshot, so it sees
    what is on screen, not what the canvas holds."""
    from io import BytesIO
    from PIL import Image
    img = Image.open(BytesIO(out.screenshot())).convert('RGB')
    k = img.width / out.evaluate("innerWidth")
    return list(img.getpixel((int(x * k), int(y * k))))


def _too_big(out):
    return out.evaluate("""() => ({
        flag: document.body.dataset.tooBig,
        visible: getComputedStyle(document.getElementById('output-canvas')).visibility,
        message: document.getElementById('output-message').hidden ? ''
            : document.getElementById('output-message').textContent})""")


def test_mac_one_to_one_is_one_canvas_pixel_per_point(e2e_server, pw_browser, page, native_host):
    """A Mac display macOS runs "looks like 1920 x 1080" at 2x (Matt's,
    2026-11-09): a 1920 x 1080 canvas fills it, point for point. The build
    before drew it at 960 x 540 points, a quarter of the display."""
    ids = reset_project(page)
    context, pg, out = _output_in(pw_browser, e2e_server, native_host, ids['c1'], 'MacIntel', 2,
                                  {'width': 1920, 'height': 1080})
    try:
        box = canvas_box(out)
        assert box['dpr'] == 2, box
        assert (box['w'], box['h']) == (1920, 1080), box
        assert (box['cssW'], box['cssH']) == (1920, 1080), box
        assert (box['left'], box['top']) == (0, 0), box
        assert out.evaluate("getComputedStyle(document.getElementById('output-canvas')).imageRendering") == 'pixelated'
        assert _too_big(out)['flag'] == '0'
        rect = out.evaluate("(() => { const r = document.getElementById('output-canvas')"
                            ".getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; })()")
        assert rect == [0, 0, 1920, 1080], rect
        # OutA (512 x 256 at 0, 0) on screen at its own place; past it black.
        assert lit(_shot_pixel(out, 450, 200)), _shot_pixel(out, 450, 200)
        assert black(_shot_pixel(out, 700, 600)), _shot_pixel(out, 700, 600)
    finally:
        context.close()


def test_mac_1920_canvas_on_a_4k_display_fills_the_top_left_quarter(e2e_server, pw_browser, page, native_host):
    ids = reset_project(page)
    context, pg, out = _output_in(pw_browser, e2e_server, native_host, ids['c1'], 'MacIntel', 1,
                                  {'width': 3840, 'height': 2160}, {'width': 1600, 'height': 900})
    try:
        box = canvas_box(out)
        assert (box['cssW'], box['cssH']) == (1920, 1080), box
        assert out.evaluate("[screen.width / 2, screen.height / 2]") == [1920, 1080]
        assert _too_big(out)['flag'] == '0'
    finally:
        context.close()


def test_windows_one_to_one_is_one_canvas_pixel_per_display_pixel(e2e_server, pw_browser, page, native_host):
    """Windows shows a display's own pixels (3840 x 2160 at 200% scale reads
    as 1920 x 1080 CSS pixels): a 1920 x 1080 canvas fills its top-left
    quarter, 960 x 540 CSS pixels."""
    ids = reset_project(page)
    context, pg, out = _output_in(pw_browser, e2e_server, native_host, ids['c1'], 'Win32', 2,
                                  {'width': 1920, 'height': 1080}, {'width': 1600, 'height': 900})
    try:
        box = canvas_box(out)
        assert box['dpr'] == 2 and (box['w'], box['h']) == (1920, 1080), box
        assert (box['cssW'], box['cssH']) == (960, 540), box
        assert _too_big(out)['flag'] == '0'
        assert lit(_shot_pixel(out, 225, 100)), _shot_pixel(out, 225, 100)
        assert black(_shot_pixel(out, 300, 200)), _shot_pixel(out, 300, 200)
        assert black(_shot_pixel(out, 1200, 700)), _shot_pixel(out, 1200, 700)
    finally:
        context.close()


def test_a_canvas_bigger_than_the_display_is_not_shown_and_says_why(e2e_server, pw_browser, page, native_host):
    ids = reset_project(page)
    context, pg, out = _output_in(pw_browser, e2e_server, native_host, ids['c1'], 'MacIntel', 1,
                                  {'width': 1280, 'height': 720})
    try:
        state = _too_big(out)
        assert state['flag'] == '1' and state['visible'] == 'hidden', state
        assert state['message'] == ('This canvas is 1920 × 1080; this display is 1280 × 720. '
                                    'Set the display to the canvas size, or use a smaller canvas.'), state
        # Nothing of the canvas on screen: no corner of it, cropped or shrunk.
        assert black(_shot_pixel(out, 100, 100)), _shot_pixel(out, 100, 100)
        assert black(_shot_pixel(out, 450, 200)), _shot_pixel(out, 450, 200)
    finally:
        context.close()


def test_unused_canvas_and_everything_past_it_is_black(e2e_server, pw_browser, page, native_host):
    ids = reset_project(page)
    context, pg, out = _output_in(pw_browser, e2e_server, native_host, ids['c2'], 'Win32', 1,
                                  {'width': 1280, 'height': 720})
    try:
        assert _too_big(out)['flag'] == '0'
        assert lit(_shot_pixel(out, 80, 80)), _shot_pixel(out, 80, 80)        # OutB
        assert black(_shot_pixel(out, 450, 200)), _shot_pixel(out, 450, 200)  # canvas, unused
        assert black(_shot_pixel(out, 900, 500)), _shot_pixel(out, 900, 500)  # past the canvas
        assert black(_shot_pixel(out, 1270, 710)), _shot_pixel(out, 1270, 710)
    finally:
        context.close()


def test_every_layout_is_logged_for_a_report_from_the_field(page):
    """dpr, display, window, canvas and CSS sizes and full screen go to the
    app log on every open and layout, so a report from a Mac can be read
    from its log."""
    import routes_logs
    seen = []
    real = routes_logs.log_event

    def spy(action, details=None, source='server'):
        if action == 'output_display_layout':
            seen.append(details)
        return real(action, details, source=source)

    routes_logs.log_event = spy
    try:
        ids = reset_project(page)
        out = open_from_dialog(page, ids['c2'])
        close_dialog(page)
        settled(out, lambda: len(seen), lambda n: n >= 1, 5000)
        out.close()
    finally:
        routes_logs.log_event = real
    assert seen, 'no output_display_layout in the log'
    d = seen[-1]
    for k in ('dpr', 'screen', 'display', 'window', 'canvas', 'css', 'fullscreen', 'native', 'tooBig'):
        assert k in d, (k, d)
    assert d['canvas'] == [640, 360] and d['css'] == [640, 360] and d['native'] is False, d


# ── the desktop app: native windows fed through the server ───────────────

def test_the_app_lists_its_displays_and_opens_full_screen_there(e2e_server, pw_browser, page, native_host):
    ids = reset_project(page)
    context, pg = _new_page(pw_browser, e2e_server)
    try:
        pg.evaluate("window.app.handleMenuAction('output-to-display')")
        pg.wait_for_selector('#output-display-modal', state='visible')
        settled(pg, lambda: pg.evaluate("document.querySelectorAll('#output-display-screen option').length"),
                lambda n: n == 3)
        options = pg.evaluate("[...document.querySelectorAll('#output-display-screen option')].map(o => o.textContent)")
        assert options == [
            'Built-in Retina Display: 1512 × 982 at 0, 0 (main)',
            'LED Processor: 1920 × 1080 at 1512, 0',
            'Small: 640 × 360 at 3432, 0',
        ], options
        # Not the main display, where the designer most likely is.
        assert pg.input_value('#output-display-screen') == '1'
        assert pg.is_visible('#output-display-screen-row')
        assert not pg.is_visible('#output-display-find-screens')
        assert not pg.is_visible('#output-display-place-note')

        # The dialog warns before opening on a display smaller than the canvas.
        pg.select_option('#output-display-canvas', ids['c1'])
        pg.select_option('#output-display-screen', '2')
        note = pg.inner_text('#output-display-note')
        assert note.startswith('This canvas is 1920 × 1080; Small is 640 × 360. '
                               'Set the display to the canvas size, or use a smaller canvas.'), note
        assert 'od-warn' in pg.get_attribute('#output-display-note', 'class')
        pg.select_option('#output-display-screen', '1')
        assert 'od-warn' not in pg.get_attribute('#output-display-note', 'class')

        # Open: no browser window, the app's own window on display 1.
        popups = []
        pg.on('popup', lambda p: popups.append(p))
        pg.click('#output-display-open')
        opened = _wait_opened(pg, native_host, 1)
        assert opened['display'] == 1 and popups == []
        assert 'feed=' in opened['path'] and f"canvas={ids['c1']}" in opened['path']
        assert opened['title'] == 'Canvas 1 · Pixel Map · on LED Processor · Output'
        rows = pg.locator('#output-display-open-list .od-open-row')
        settled(pg, lambda: rows.count(), lambda n: n == 1)
        assert rows.first.inner_text().startswith('Canvas 1 · Pixel Map · on LED Processor')
        assert 'has an output' in pg.inner_text('#output-display-screen option[value="1"]')

        # The window (here a page at the address the app was given) gets
        # the frames through the server, 1:1, and follows edits.
        out = context.new_page()
        out.goto(e2e_server + opened['path'], wait_until='domcontentloaded')
        settled(out, lambda: frames(out), lambda n: n >= 1, 8000)
        assert frames(out) >= 1, 'the native output never got a frame'
        assert out.evaluate("document.body.dataset.native") == '1'
        assert out.inner_text('#output-hint') == 'Esc to close'
        box = canvas_box(out)
        assert (box['w'], box['h']) == (1920, 1080) and (box['cssW'], box['cssH']) == (1920, 1080), box
        assert lit(pixel(out, 450, 200)) and black(pixel(out, 1300, 100))
        assert out.title() == 'Canvas 1 · Pixel Map · on LED Processor · Output'
        green = lambda px: px is not None and px[1] > 200 and px[0] < 60 and px[2] < 60  # noqa: E731
        pg.evaluate("""() => {
            const app = window.app;
            const l = app.project.layers.find(x => x.name === 'OutA');
            l.color1 = {r: 0, g: 255, b: 0}; l.color2 = {r: 0, g: 255, b: 0};
            app.saveState('Recolour OutA');
            window.canvasRenderer.render();
        }""")
        got = settled(out, lambda: pixel(out, 450, 200), green, 8000)
        assert green(got), got

        # Esc in the window asks the app to close it; the dialog drops it.
        feed = opened['id']
        out.keyboard.press('Escape')
        settled(pg, lambda: list(native_host.closed), lambda c: feed in c, 5000)
        assert feed in native_host.closed
        settled(pg, lambda: pg.evaluate("window.app.listOutputDisplays().length"), lambda n: n == 0, 5000)
        assert pg.evaluate("window.app.listOutputDisplays().length") == 0
        settled(out, lambda: out.evaluate("document.getElementById('output-message').textContent"),
                lambda t: t == 'This output was closed.', 5000)
        out.close()

        # Close from the dialog's list.
        pg.click('#output-display-open')
        second = _wait_opened(pg, native_host, 2)
        settled(pg, lambda: rows.count(), lambda n: n == 1)
        rows.first.locator('button').click()
        settled(pg, lambda: list(native_host.closed), lambda c: second['id'] in c, 5000)
        assert second['id'] in native_host.closed
        assert pg.evaluate("window.app.listOutputDisplays().length") == 0

        # The designer leaving closes what it still has open.
        pg.click('#output-display-open')
        third = _wait_opened(pg, native_host, 3)
        settled(pg, lambda: pg.evaluate("window.app.listOutputDisplays().filter(e => e.id).length"),
                lambda n: n == 1)
        pg.wait_for_timeout(300)
        pg.close()
        settled(page, lambda: list(native_host.closed), lambda c: third['id'] in c, 5000)
        assert third['id'] in native_host.closed
    finally:
        context.close()


def test_a_native_idm_output_gets_the_highlight_without_a_render(e2e_server, pw_browser, page, native_host):
    """The IDM Locator's blink and mouse are laid over the last frame and
    sent as a new frame; the designer never renders for them."""
    ids = reset_project(page)
    context, pg = _new_page(pw_browser, e2e_server)
    try:
        cid = ids['c1']
        pg.evaluate("window.app.handleMenuAction('output-to-display')")
        pg.wait_for_selector('#output-display-modal', state='visible')
        settled(pg, lambda: pg.evaluate("document.querySelectorAll('#output-display-screen option').length"),
                lambda n: n == 3)
        pg.select_option('#output-display-canvas', cid)
        pg.select_option('#output-display-view', 'idm')
        pg.click('#output-display-open')
        opened = _wait_opened(pg, native_host, 1)
        out = context.new_page()
        out.goto(e2e_server + opened['path'], wait_until='domcontentloaded')
        settled(out, lambda: frames(out), lambda n: n >= 1, 8000)
        before = frames(out)
        renders = pg.evaluate("""() => {
            const r = window.canvasRenderer; window.__renders = 0;
            const real = r.render.bind(r);
            r.render = (...a) => { window.__renders += 1; return real(...a); };
            window.app._outputDisplayBlink(null);
            window.app._outputDisplayBlink(null);
            return window.__renders;
        }""")
        assert renders == 0
        settled(out, lambda: frames(out), lambda n: n > before, 5000)
        assert frames(out) > before
        out.close()
    finally:
        context.close()


# ── live ──────────────────────────────────────────────────────────────────

def test_output_follows_local_edits_undo_and_other_clients(page, e2e_server):
    ids = reset_project(page)
    out = open_from_dialog(page, ids['c1'])
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


def test_header_footer_goes_out_at_the_show_raster(page):
    """Header/Footer is a Show Look tab like Data and Power: the dialog
    offers it, between Power and the IDM Locator, and its note gives the
    Show Look raster."""
    ids = reset_project(page)
    page.evaluate("""(id) => { const c = window.app.project.canvases.find(x => x.id === id);
        c.show_raster_width = 2222; c.show_raster_height = 1111; }""", ids['c1'])
    page.evaluate("window.app.handleMenuAction('output-to-display')")
    page.wait_for_selector('#output-display-modal', state='visible')
    views = page.evaluate("[...document.querySelectorAll('#output-display-view option')].map(o => o.value)")
    assert views == ['pixel-map', 'cabinet-id', 'show-look', 'data-flow', 'power', 'rigging', 'idm']
    assert page.evaluate(f"window.app._outputDisplayRasterSize('{ids['c1']}', 'rigging')") == \
        {'width': 2222, 'height': 1111}
    close_dialog(page)
    out = open_from_dialog(page, ids['c1'], view='rigging')
    assert 'Header/Footer' in out.title()
    assert ' - ' not in out.title()
    out.close()
    close_dialog(page)


# ── the dialog's list, closing ────────────────────────────────────────────

def test_dialog_lists_and_closes_outputs(page):
    ids = reset_project(page)
    out = open_from_dialog(page, ids['c2'], view='cabinet-id')
    rows = page.locator('#output-display-open-list .od-open-row')
    assert rows.count() == 1
    assert rows.first.inner_text().startswith('Canvas 2 · Cabinet ID')
    assert '1:1 pixel' not in rows.first.inner_text() and 'Fit' not in rows.first.inner_text()
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
    # keydown alone: the window is gone before a keyup could reach it, and
    # it can go before the browser answers the key press itself. The close
    # event is what this test asks for, so that answer is not waited on.
    with out.expect_event('close', timeout=5000):
        try:
            out.keyboard.down('Escape')
        except pw_api.Error as gone:
            assert 'closed' in str(gone), gone
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
