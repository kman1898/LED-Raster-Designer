"""The pixel grid covers every screen wherever it is drawn.

Zoomed to 1000 % and past it, every view draws a line on each LED pixel edge
over every screen (canvas.js renderPixelGrid). The grid was worked out in the
canvas's own coordinates while the screen it lay over could be drawn
somewhere else: a canvas moved off the workspace origin, the Data and Power
tabs' Back view (mirrored), a screen with its own Show Look position, a
rotated screen, or a screen on a canvas other than the active one. In each of
those the cabinets showed and the grid did not, over part or all of the wall.

Each test draws one frame at 1200 % twice, with the grid and without it, and
walks the LED pixel edges inside the screen (every 12 screen pixels): each
one the screen's writing (name plate, Cabinet ID, data and power runs) does
not cover must show a grid line. Whether the writing itself covers the grid
is the label pass's business (test_labels_on_top).

Run locally:
    python -m pytest tests/test_pixel_grid.py -v -p no:cacheprovider --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from test_screen_groups_canvas import HELPERS_JS  # noqa: E402

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1500, 'height': 900})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.errors = []
    pg.on('pageerror', lambda err: pg.errors.append(str(err)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.evaluate(HELPERS_JS)
    yield pg
    context.close()


ZOOM = 12

# One screen of 4 x 2 cabinets of 128 px at (1000, 600) on an 8192 raster.
# `canvas` / `extra` change the project's canvases, `at` is the point the
# frame is centred on, in the workspace's coordinates (where the eye sees
# the screen in that view).
GRID_JS = """([mode, spec]) => {
    const gc = window.__gc, r = window.canvasRenderer, app = window.app;
    const layer = gc.screen(Object.assign({
        name: 'Grid', columns: 4, rows: 2, offset_x: 1000, offset_y: 600,
    }, spec.layer || {}));
    return gc.withProject([layer], [], mode, () => {
        const c1 = app.project.canvases[0];
        Object.assign(c1, spec.canvas || {});
        (spec.extra || []).forEach(c => app.project.canvases.push(c));
        if (spec.active) app.project.active_canvas_id = spec.active;
        const W = r.canvas.width, H = r.canvas.height;
        r.zoom = spec.zoom;
        r.panX = Math.round(W / 2 - spec.at[0] * spec.zoom);
        r.panY = Math.round(H / 2 - spec.at[1] * spec.zoom);
        const grab = () => r.ctx.getImageData(0, 0, W, H).data;
        const without = (names, fn) => {
            const kept = names.map(n => [n, r[n]]);
            names.forEach(n => { r[n] = function () {}; });
            try { return fn(); } finally { kept.forEach(([n, f]) => { r[n] = f; }); }
        };
        r.render();
        const A = grab();
        const G = without(['renderPixelGrid'], () => { r.render(); return grab(); });
        const N = without(['renderPixelGrid', '_renderLayerWriting', 'renderLayerOffsets'],
            () => { r.render(); return grab(); });
        const P = without(['renderPixelGrid', 'renderPanel'], () => { r.render(); return grab(); });
        const diff = (X, Y, i) => Math.abs(X[i] - Y[i]) + Math.abs(X[i + 1] - Y[i + 1])
            + Math.abs(X[i + 2] - Y[i + 2]);
        const z = spec.zoom;
        const px = ((Math.round(r.panX) % z) + z) % z;
        const py = ((Math.round(r.panY) % z) + z) % z;
        let edges = 0, lined = 0;
        const misses = [];
        // a pixel edge at device x straddles columns x - 1 and x
        const look = (x, y, prev) => {
            if (x < 1 || y < 1 || x >= W || y >= H) return;
            const i = (y * W + x) * 4, j = prev(i);
            if (diff(G, P, i) < 3 || diff(G, P, j) < 3) return;     // not on the screen
            if (diff(G, N, i) >= 3 || diff(G, N, j) >= 3) return;   // under the writing
            edges++;
            if (diff(A, G, i) >= 3 || diff(A, G, j) >= 3) lined++;
            else if (misses.length < 5) misses.push([x, y]);
        };
        for (let x = px; x < W; x += z) for (let y = 5; y < H; y += 17) look(x, y, i => i - 4);
        for (let y = py; y < H; y += z) for (let x = 5; x < W; x += 17) look(x, y, i => i - W * 4);
        return { edges, lined, misses };
    });
}"""


def grid(page, mode, spec):
    spec = dict(spec, zoom=ZOOM)
    out = page.evaluate(GRID_JS, [mode, spec])
    assert not page.errors, page.errors
    return out


def assert_grid_everywhere(out, what):
    # the frame really is over the screen: 81 x 57 LED pixels, most of them
    # edged on two sides
    assert out['edges'] >= 400, f'{what}: the frame missed the screen: {out}'
    assert out['lined'] == out['edges'], (
        f'{what}: {out["edges"] - out["lined"]} of {out["edges"]} pixel edges have no '
        f'grid line (first at {out["misses"]}): {out}')


@pytest.mark.parametrize('mode', ['pixel-map', 'data-flow'])
def test_grid_on_a_screen_at_the_origin_canvas(page, mode):
    """The plain case: one canvas at the workspace origin."""
    assert_grid_everywhere(grid(page, mode, {'at': [1200, 664]}), mode)


@pytest.mark.parametrize('mode', ['pixel-map', 'cabinet-id', 'data-flow', 'power'])
def test_grid_on_a_canvas_moved_off_the_origin(page, mode):
    """A canvas placed at 3000, 1000 on the workspace: the grid follows it."""
    spec = {'at': [4200, 1664],
            'canvas': {'workspace_x': 3000, 'workspace_y': 1000,
                       'show_workspace_x': 3000, 'show_workspace_y': 1000}}
    assert_grid_everywhere(grid(page, mode, spec), mode)


@pytest.mark.parametrize('mode,key', [('data-flow', 'data_flow_perspective'),
                                      ('power', 'power_perspective')])
def test_grid_in_the_back_view(page, mode, key):
    """Back view mirrors the canvas about its raster: the screen at 1000..1512
    is seen at 8192 - 1512 .. 8192 - 1000, and so is its grid."""
    spec = {'at': [8192 - 1200, 664], 'canvas': {key: 'back'}}
    assert_grid_everywhere(grid(page, mode, spec), mode)


@pytest.mark.parametrize('mode', ['show-look', 'data-flow', 'power'])
def test_grid_at_the_show_look_position(page, mode):
    """A screen with its own Show Look position: the views that draw it there
    draw its grid there too."""
    spec = {'at': [4200, 2664], 'layer': {'showOffsetX': 4000, 'showOffsetY': 2600}}
    assert_grid_everywhere(grid(page, mode, spec), mode)


@pytest.mark.parametrize('mode', ['pixel-map', 'cabinet-id'])
def test_grid_on_a_rotated_screen(page, mode):
    """Turned 90 degrees about its centre (1256, 728), the 512 x 256 screen
    stands 256 x 512 from 472 to 984 down: the frame looks below where the
    unturned screen would end."""
    spec = {'at': [1256, 920], 'layer': {'rotation': 90}}
    assert_grid_everywhere(grid(page, mode, spec), mode)


@pytest.mark.parametrize('mode', ['pixel-map', 'data-flow'])
def test_grid_on_a_canvas_that_is_not_the_active_one(page, mode):
    """The grid is bounded by the screen's own canvas's raster, not by the
    raster of whichever canvas is active (here a small one further down)."""
    small = {'id': 'c2', 'name': 'Canvas 2', 'visible': True,
             'workspace_x': 0, 'workspace_y': 9000,
             'show_workspace_x': 0, 'show_workspace_y': 9000,
             'raster_width': 640, 'raster_height': 360,
             'show_raster_width': 640, 'show_raster_height': 360,
             'color': '#00ff00'}
    spec = {'at': [1200, 664], 'extra': [small], 'active': 'c2'}
    assert_grid_everywhere(grid(page, mode, spec), mode)
