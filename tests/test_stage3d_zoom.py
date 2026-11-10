"""Pixel level zoom on the 3D tab (the owner, 2026-11-09: "I can only zoom in
so much ... We need pixel level zoom like on other tabs").

The cause was the wheel's own stop, 150 mm short of the point it zooms
toward (app-stage3d-nav.js NEAR_MM): a 3.9 mm pixel never got past about
20 page px. Orthographic stopped at zoom 500, which on a big stage is no
closer. Now the wheel goes to 2 mm off the surface and orthographic until
the view is 4 mm tall; the near plane follows the camera in
(app-stage3d.js _s3dFitNear), so nothing is cut away; a texel seen bigger
than a page pixel is a crisp square; and a screen too big for its everyday
4096 texture is drawn again at one texel per pixel, one at a time, while
the camera is close (_s3dDetailCheck).

Run locally:
    python -m pytest tests/test_stage3d_zoom.py -p no:cacheprovider
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from conftest import settled  # noqa: E402

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

PX_MM = 500 / 128           # one LED pixel of these screens, mm


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project as this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1500, 'height': 900})
    context.add_init_script("try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.errors = []
    pg.on('pageerror', lambda err: pg.errors.append(str(err)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app._initialLoadComplete")
    pg.wait_for_timeout(1200)
    yield pg
    context.close()


RESET_JS = """async (specs) => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    let project = await j('GET', '/api/project');
    project.layers = []; project.groups = [];
    for (const k of ['stage3dCamera', 'stage3dUnits', 'stage3dGrid', 'stage3dBars']) delete project[k];
    await j('PUT', '/api/project', project);
    const ids = [];
    for (const s of specs) {
        const made = await j('POST', '/api/layer/add', Object.assign({
            cabinet_width: 128, cabinet_height: 128, panel_width_mm: 500, panel_height_mm: 500}, s));
        ids.push(made.id);
    }
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('stage3d_zoom_reset');
    app.resetHistory('Stage3D Zoom Reset');
    app.selectLayer(app.project.layers.find(l => l.id === ids[0]));
    app.updateUI();
    if (app._s3d) app._s3d.grid = true;
    return ids;
}"""


def reset(page, specs):
    page.evaluate("""() => { const t = document.querySelector('#view-tabs .view-tab[data-mode="pixel-map"]');
        if (t) t.click(); }""")
    page.wait_for_timeout(150)
    ids = page.evaluate(RESET_JS, specs)
    page.wait_for_timeout(300)
    page.click('#view-tabs .view-tab[data-mode="3d"]')
    d = settled(page, lambda: dbg(page), lambda d: d['loaded'] and len(d['screens']) == len(ids)
                and all(s['tex'] for s in d['screens']), 10000)
    assert d['webgl'], d
    return ids


def dbg(page):
    return page.evaluate('window.app._s3dDebug()')


def screen(page, layer_id):
    return next((s for s in dbg(page)['screens'] if s['id'] == layer_id), None)


def camera(page):
    return page.evaluate('window.app._s3dCameraState()')


def view_from(page, name):
    page.click(f'[data-s3d-view="{name}"]')
    return settled(page, lambda: dbg(page), lambda d: not d['gliding'], 3000)


def probe(page, x, y):
    return page.evaluate(f"window.app._s3dDebugProbe({x}, {y})")


def pixel_span(page, at):
    """Page px across one LED pixel at the point under `at` (the screens
    here face the audience flat, so one pixel is PX_MM along X)."""
    return page.evaluate("""([x, y, mm]) => {
        const a = window.app, p = a._s3dDebugProbe(x, y);
        if (!p) return 0;
        const u = a._s3dDebugWhere(p), v = a._s3dDebugWhere([p[0] + mm, p[1], p[2]]);
        return Math.hypot(u[0] - v[0], u[1] - v[1]);
    }""", [at[0], at[1], PX_MM])


# What the view draws at a page point, read straight off the drawing
# buffer after a render.
PIXEL_JS = """([x, y]) => {
    const st = window.app._s3d, r = st.renderer;
    st.renderer.render(st.scene, st.camera);
    const gl = r.getContext(), c = r.domElement, rect = c.getBoundingClientRect();
    const k = c.width / rect.width;
    const px = new Uint8Array(4);
    gl.readPixels(Math.round((x - rect.left) * k), Math.round(c.height - (y - rect.top) * k), 1, 1,
                  gl.RGBA, gl.UNSIGNED_BYTE, px);
    return Array.from(px);
}"""


def zoom_in_until(page, at, span=50, most=120):
    page.mouse.move(*at)
    n = 0
    while n < most and pixel_span(page, at) < span:
        page.mouse.wheel(0, -100)
        page.wait_for_timeout(40)
        n += 1
    return n


def zoom_out(page, at, n):
    page.mouse.move(*at)
    for _ in range(n):
        page.mouse.wheel(0, 100)
        page.wait_for_timeout(40)


def close_pose(a, b, tol=0.05):
    return a['mode'] == b['mode'] and all(
        abs(x - y) <= tol for k in ('position', 'target') for x, y in zip(a[k], b[k])) \
        and abs(a['zoom'] - b['zoom']) <= tol * max(1, a['zoom'])


@pytest.mark.parametrize('mode', ['perspective', 'ortho'])
def test_the_wheel_zooms_in_until_one_pixel_fills_the_view_and_back(page, mode):
    ids = reset(page, [{'name': 'Wall', 'columns': 8, 'rows': 4}])
    page.click('#s3d-mode-ortho' if mode == 'ortho' else '#s3d-mode-persp')
    page.wait_for_timeout(200)
    view_from(page, 'front')
    s = screen(page, ids[0])
    # whole page px: the wheel event lands on one, and the point under it
    # is what stays put
    at = (round(s['at'][0]) + 17, round(s['at'][1]) + 9)
    grabbed = probe(page, *at)
    assert grabbed
    rect = page.evaluate("(() => { const r = document.getElementById('s3d-canvas').getBoundingClientRect();"
                         " return [r.left, r.top, r.width, r.height]; })()")
    empty = page.evaluate(PIXEL_JS, [rect[0] + 6, rect[1] + 6])     # the sky over the stage
    before = camera(page)
    n = zoom_in_until(page, at)
    span = pixel_span(page, at)
    assert span >= 50, (mode, n, span)
    # still the same point under the cursor, and the screen drawn there:
    # not cut away by the near plane
    assert probe(page, *at) == pytest.approx(grabbed, abs=0.5)
    st = page.evaluate("""(() => { const st = window.app._s3d, c = st.camera;
        return {near: c.near, ortho: !!c.isOrthographicCamera, pos: c.position.toArray()}; })()""")
    if not st['ortho']:
        gap = sum((a - b) ** 2 for a, b in zip(st['pos'], grabbed)) ** 0.5
        assert st['near'] < gap / 2, (st, gap)
    drawn = page.evaluate(PIXEL_JS, list(at))
    assert drawn[:3] != empty[:3], (drawn, empty)
    # and the same number of notches back out puts the view back
    zoom_out(page, at, n)
    assert close_pose(camera(page), before), (camera(page), before)
    assert page.errors == []


def test_f_still_frames_after_zooming_in(page):
    ids = reset(page, [{'name': 'Wall', 'columns': 8, 'rows': 4}])
    page.click('#s3d-mode-persp')
    view_from(page, 'front')
    s = screen(page, ids[0])
    at = (round(s['at'][0]), round(s['at'][1]))
    zoom_in_until(page, at)
    page.evaluate(f"window.app.setSelectedLayersByIds([{ids[0]}], {ids[0]})")
    page.mouse.move(5, 5)
    page.keyboard.press('f')
    cam = settled(page, lambda: camera(page), lambda c: not dbg(page)['gliding'], 3000)
    w = screen(page, ids[0])['world']
    centre = [(w['min'][i] + w['max'][i]) / 2 for i in range(3)]
    assert cam['target'] == pytest.approx(centre, abs=1)
    # the whole wall is back in the view
    assert pixel_span(page, screen(page, ids[0])['at']) < 5
    near = page.evaluate("window.app._s3d.camera.near")
    assert near > 1, near


def test_a_big_screen_is_drawn_pixel_for_pixel_up_close(page):
    """A 5120 x 2560 wall: its everyday texture is 4096 wide; up close it is
    drawn again at one texel per pixel, with crisp texels, and goes back
    once the camera leaves."""
    ids = reset(page, [{'name': 'Big', 'columns': 40, 'rows': 20}])
    page.click('#s3d-mode-persp')
    view_from(page, 'front')
    assert screen(page, ids[0])['tex'] == [4096, 2048]
    s = screen(page, ids[0])
    at = (round(s['at'][0]) + 11, round(s['at'][1]) + 7)
    zoom_in_until(page, at)
    got = settled(page, lambda: screen(page, ids[0])['tex'], lambda t: t == [5120, 2560], 3000)
    assert got == [5120, 2560]
    tex = page.evaluate(f"""(() => {{ const e = window.app._s3d.entries.get({ids[0]});
        return {{mag: e.tex.magFilter, nearest: window.app._s3d.T.NearestFilter, mips: e.tex.generateMipmaps}}; }})()""")
    assert tex['mag'] == tex['nearest'] and tex['mips'] is False
    page.click('#s3d-home')
    got = settled(page, lambda: screen(page, ids[0])['tex'], lambda t: t == [4096, 2048], 3000)
    assert got == [4096, 2048]
    assert page.errors == []
