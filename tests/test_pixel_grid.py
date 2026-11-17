"""The pixel grid covers every screen wherever it is drawn, writing included.

Zoomed to 1000 % and past it, every view draws a line on each LED pixel edge
over every screen (canvas.js renderPixelGrid). The grid was worked out in the
canvas's own coordinates while the screen it lay over could be drawn
somewhere else: a canvas moved off the workspace origin, the Data and Power
tabs' Back view (mirrored), a screen with its own Show Look position, a
rotated screen, or a screen on a canvas other than the active one. In each of
those the cabinets showed and the grid did not, over part or all of the wall.

The owner (2026-11-16): "labels should not cover the grid i need to be able
to see the pixels". The grid is drawn after every screen's writing: name
plates, group names, corner readouts, Cabinet IDs, the data and power runs
with their discs and tags. A screen laid over another still hides the lower
screen's grid where it covers it, as it hides its cabinets. Exports never
draw the grid.

Each test draws one frame at 1200 % with the grid and without it, and walks
the LED pixel edges inside the screen: every one must show a grid line, under
the writing too. A case about one piece of writing centres the frame on it
and also checks enough of the edges walked lie under that writing.

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

# One screen of 4 x 2 cabinets of 128 px at (1000, 600) on an 8192 raster,
# unless `layers` lists the screens (`group` groups them all). `canvas` /
# `extra` change the project's canvases, `at` is the point the frame is
# centred on, in the workspace's coordinates (where the eye sees the screen
# in that view). `find` recentres the frame on the first screen's name plate
# (a grouped wall's own, 'name') or the label disc nearest `at` ('disc').
# `writing` names the renderer method that draws the writing under test.
#
# Frames: A as drawn; G without the grid; N without the grid and the
# writing; NP without those and the cabinets. A pixel is on the screen where
# N and NP differ (the cabinets with no writing on them), under the writing
# where G and the frame without `writing` differ.
GRID_JS = """([mode, spec]) => {
    const gc = window.__gc, r = window.canvasRenderer, app = window.app;
    const layers = (spec.layers || [Object.assign({
        name: 'Grid', columns: 4, rows: 2, offset_x: 1000, offset_y: 600,
    }, spec.layer || {})]).map(o => gc.screen(o));
    const groups = spec.group ? [gc.group(layers)] : [];
    return gc.withProject(layers, groups, mode, () => {
        const c1 = app.project.canvases[0];
        Object.assign(c1, spec.canvas || {});
        (spec.extra || []).forEach(c => app.project.canvases.push(c));
        if (spec.active) app.project.active_canvas_id = spec.active;
        const W = r.canvas.width, H = r.canvas.height;
        const z = spec.zoom;
        const frame = ([wx, wy]) => {
            r.zoom = z;
            r.panX = Math.round(W / 2 - wx * z);
            r.panY = Math.round(H / 2 - wy * z);
        };
        frame(spec.at);
        if (spec.find === 'name') {
            // a grouped wall's one name plate is kept on its first member
            r.render();
            const h = layers[0]._screenNameHitRect;
            if (!h) return { error: 'no name plate' };
            frame([(h.x1 + h.x2) / 2, (h.y1 + h.y2) / 2]);
        } else if (spec.find === 'disc') {
            r.startLabelProbe();
            let reg;
            try { r.render(); } finally { reg = r.endLabelProbe(); }
            const disc = (reg || []).filter(b => b.kind === 'disc')
                .sort((a, b) => Math.hypot(a.x + a.w / 2 - W / 2, a.y + a.h / 2 - H / 2)
                              - Math.hypot(b.x + b.w / 2 - W / 2, b.y + b.h / 2 - H / 2))[0];
            if (!disc) return { error: 'no disc' };
            frame([(disc.x + disc.w / 2 - r.panX) / z, (disc.y + disc.h / 2 - r.panY) / z]);
        }
        const grab = () => r.ctx.getImageData(0, 0, W, H).data;
        const draw = (names) => {
            const kept = names.map(n => [n, Object.prototype.hasOwnProperty.call(r, n), r[n]]);
            names.forEach(n => { r[n] = function () {}; });
            try { r.render(); return grab(); } finally {
                kept.forEach(([n, own, f]) => { if (own) r[n] = f; else delete r[n]; });
            }
        };
        const WRITING = ['_renderLayerWriting', 'renderLayerOffsets', 'renderLayerLabels',
                         '_renderCrossMemberPaths'];
        const A = draw([]);
        const G = draw(['renderPixelGrid']);
        const N = draw(['renderPixelGrid', ...WRITING]);
        const NP = draw(['renderPixelGrid', 'renderPanel', ...WRITING]);
        const M = spec.writing ? draw(['renderPixelGrid', spec.writing]) : G;
        const diff = (X, Y, i) => Math.abs(X[i] - Y[i]) + Math.abs(X[i + 1] - Y[i + 1])
            + Math.abs(X[i + 2] - Y[i + 2]);
        // a pixel already the grid's own grey can't show a line over it
        const grey = (X, i) => [0, 1, 2].every(k => Math.abs(X[i + k] - 80) <= 6);
        const px = ((Math.round(r.panX) % z) + z) % z;
        const py = ((Math.round(r.panY) % z) + z) % z;
        let edges = 0, lined = 0, under = 0;
        const misses = [];
        // a pixel edge at device x straddles columns x - 1 and x
        const look = (x, y, prev) => {
            if (x < 1 || y < 1 || x >= W || y >= H) return;
            const i = (y * W + x) * 4, j = prev(i);
            if (diff(N, NP, i) < 3 || diff(N, NP, j) < 3) return;   // not on the screen
            const ok = diff(A, G, i) >= 3 || diff(A, G, j) >= 3;
            if (!ok && grey(G, i) && grey(G, j)) return;
            edges++;
            if (spec.writing && (diff(G, M, i) >= 3 || diff(G, M, j) >= 3)) under++;
            if (ok) lined++;
            else if (misses.length < 5) misses.push([x, y]);
        };
        for (let x = px; x < W; x += z) for (let y = 1; y < H; y += 3) look(x, y, i => i - 4);
        for (let y = py; y < H; y += z) for (let x = 1; x < W; x += 3) look(x, y, i => i - W * 4);
        return { edges, lined, under, misses };
    });
}"""


def grid(page, mode, spec):
    spec = dict(spec, zoom=ZOOM)
    out = page.evaluate(GRID_JS, [mode, spec])
    assert not page.errors, page.errors
    assert 'error' not in out, out
    return out


def assert_grid_everywhere(out, what, under=0):
    # the frame really is over the screen: 125 x 75 LED pixels, most of them
    # edged on two sides
    assert out['edges'] >= 2000, f'{what}: the frame missed the screen: {out}'
    if under:
        assert out['under'] >= under, (
            f'{what}: too few pixel edges under the writing to judge: {out}')
    assert out['lined'] == out['edges'], (
        f'{what}: {out["edges"] - out["lined"]} of {out["edges"]} pixel edges have no '
        f'grid line (first at {out["misses"]}): {out}')


# ── Where the screen is drawn ───────────────────────────────────────────

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


# ── Over the writing ────────────────────────────────────────────────────

@pytest.mark.parametrize('mode', ['pixel-map', 'cabinet-id', 'data-flow', 'power'])
def test_grid_over_the_name_plate(page, mode):
    """The screen's name plate never hides a pixel edge."""
    spec = {'at': [1256, 728], 'find': 'name', 'writing': 'renderLayerLabels',
            'layer': {'showLabelNameCabinet': True}}
    assert_grid_everywhere(grid(page, mode, spec), f'{mode} name plate', under=200)


@pytest.mark.parametrize('mode', ['pixel-map', 'cabinet-id', 'data-flow', 'power'])
def test_grid_over_the_group_name(page, mode):
    """Two screens grouped into one wall: the wall's name plate, over both
    members, never hides a pixel edge either."""
    left = {'id': 1, 'name': 'Left', 'columns': 2, 'rows': 2, 'offset_x': 1000,
            'offset_y': 600, 'group_id': 'g1', 'showLabelNameCabinet': True}
    right = dict(left, id=2, name='Right', offset_x=1256)
    spec = {'at': [1256, 728], 'find': 'name', 'writing': 'renderLayerLabels',
            'layers': [left, right], 'group': True}
    assert_grid_everywhere(grid(page, mode, spec), f'{mode} group name', under=200)


def test_grid_over_the_cabinet_ids(page):
    """The Cabinet ID tab's numbers, one on each cabinet."""
    spec = {'at': [1064, 664], 'writing': 'renderCabinetIDNumbers'}
    assert_grid_everywhere(grid(page, 'cabinet-id', spec), 'Cabinet ID', under=200)


def test_grid_over_the_corner_readout(page):
    """The Pixel Map's corner X,Y readout, in the screen's top left corner."""
    spec = {'at': [1060, 625], 'writing': 'renderLayerOffsets',
            'layer': {'showOffsetTL': True}}
    assert_grid_everywhere(grid(page, 'pixel-map', spec), 'corner readout', under=200)


@pytest.mark.parametrize('mode,writing', [('data-flow', 'renderDataFlowArrows'),
                                          ('power', 'renderPowerArrows')])
def test_grid_over_the_run_line(page, mode, writing):
    """The data run (and the power circuit) between the first two cabinets'
    centres, (1064, 664) to (1192, 664)."""
    spec = {'at': [1128, 664], 'writing': writing}
    assert_grid_everywhere(grid(page, mode, spec), f'{mode} run line', under=20)


@pytest.mark.parametrize('mode,writing', [('data-flow', 'renderDataFlowArrows'),
                                          ('power', 'renderPowerArrows')])
def test_grid_over_the_port_and_circuit_disc(page, mode, writing):
    """The run's label disc (P1 on Data, the circuit's on Power)."""
    spec = {'at': [1064, 664], 'find': 'disc', 'writing': writing}
    assert_grid_everywhere(grid(page, mode, spec), f'{mode} disc', under=20)


# ── A screen over another ───────────────────────────────────────────────

# Screen A (4 x 2 at 1000, 600) under screen B (2 x 1 at 1100, 650). The
# frame is centred on B's top left corner. F is the frame as drawn, F_A the
# frame with A's grid left out: inside B the two must match (A's grid is
# under B, like A's cabinets), on A outside B they must not (A's grid is
# drawn there). F_B leaves B's grid out: B's own grid shows on B.
OVERLAP_JS = """(mode) => {
    const gc = window.__gc, r = window.canvasRenderer;
    const a = gc.screen({ id: 1, name: 'Under', columns: 4, rows: 2,
                          offset_x: 1000, offset_y: 600 });
    const b = gc.screen({ id: 2, name: 'Over', columns: 2, rows: 1,
                          offset_x: 1100, offset_y: 650,
                          color1: { r: 0, g: 160, b: 0 }, color2: { r: 0, g: 200, b: 0 } });
    return gc.withProject([a, b], [], mode, () => {
        const W = r.canvas.width, H = r.canvas.height, z = 12;
        r.zoom = z;
        r.panX = Math.round(W / 2 - 1100 * z);
        r.panY = Math.round(H / 2 - 650 * z);
        const grab = () => r.ctx.getImageData(0, 0, W, H).data;
        const proto = Object.getPrototypeOf(r).renderPixelGrid;
        const skipping = (id) => {
            r.renderPixelGrid = function (l) { if (l.id !== id) proto.call(this, l); };
            try { r.render(); return grab(); } finally { delete r.renderPixelGrid; }
        };
        r.render();
        const F = grab();
        const FA = skipping(1);
        const FB = skipping(2);
        const diff = (X, Y, i) => Math.abs(X[i] - Y[i]) + Math.abs(X[i + 1] - Y[i + 1])
            + Math.abs(X[i + 2] - Y[i + 2]);
        const bx = 1100 * z + r.panX, by = 650 * z + r.panY;
        const ax = 1000 * z + r.panX, ay = 600 * z + r.panY;
        let aOnB = 0, aOnA = 0, bOnB = 0;
        for (let y = 0; y < H; y++) {
            for (let x = 0; x < W; x++) {
                const i = (y * W + x) * 4;
                const inB = x >= bx + 2 && y >= by + 2;
                const inA = x >= ax + 2 && y >= ay + 2 && (x < bx - 2 || y < by - 2);
                if (inB && diff(F, FA, i) >= 3) aOnB++;
                if (inB && diff(F, FB, i) >= 3) bOnB++;
                if (inA && diff(F, FA, i) >= 3) aOnA++;
            }
        }
        return { aOnB, aOnA, bOnB };
    });
}"""


@pytest.mark.parametrize('mode', ['pixel-map', 'cabinet-id', 'data-flow', 'power'])
def test_a_screen_over_another_hides_the_lower_ones_grid(page, mode):
    """At 1200 %, where screen B lies over screen A only B's grid shows."""
    out = page.evaluate(OVERLAP_JS, mode)
    assert not page.errors, page.errors
    assert out['aOnA'] > 1000, f'{mode}: the lower screen drew no grid of its own: {out}'
    assert out['bOnB'] > 1000, f'{mode}: the upper screen drew no grid of its own: {out}'
    assert out['aOnB'] == 0, f'{mode}: the lower screen\'s grid shows over the upper one: {out}'


# ── Order and exports ───────────────────────────────────────────────────

ORDER_JS = """(mode) => {
    const gc = window.__gc, r = window.canvasRenderer;
    const a = gc.screen({ id: 1, name: 'A', offset_x: 1000, offset_y: 600 });
    return gc.withProject([a], [], mode, () => {
        const order = [];
        const names = ['renderPixelGrid', 'renderLayerLabels', '_renderLayerWriting',
                       'renderLayerOffsets', 'renderPixelMapSelectionOverlay',
                       'renderPixelMapSelectionBadge', 'renderCustomSelectionOverlay',
                       'renderCustomActivePortBadge', 'renderPowerSelectionOverlay',
                       'renderPowerActiveCircuitBadge'];
        names.forEach(k => {
            const f = r[k];
            r[k] = function (...args) { order.push(k); return f.apply(this, args); };
        });
        r.zoom = 12;
        r.panX = Math.round(r.canvas.width / 2 - 1128 * 12);
        r.panY = Math.round(r.canvas.height / 2 - 664 * 12);
        try { r.render(); } finally { names.forEach(k => { delete r[k]; }); }
        return order;
    });
}"""


@pytest.mark.parametrize('mode,tint,badge', [
    ('pixel-map', 'renderPixelMapSelectionOverlay', 'renderPixelMapSelectionBadge'),
    ('data-flow', 'renderCustomSelectionOverlay', 'renderCustomActivePortBadge'),
    ('power', 'renderPowerSelectionOverlay', 'renderPowerActiveCircuitBadge'),
])
def test_the_grid_is_drawn_after_the_writing_and_the_selection_tint(page, mode, tint, badge):
    """The order: every screen's writing and the picked cabinets' tint, then
    the grid, then the badges in the frame's corner."""
    order = page.evaluate(ORDER_JS, mode)
    assert not page.errors, page.errors
    grid_at = [i for i, k in enumerate(order) if k == 'renderPixelGrid']
    writing_at = [i for i, k in enumerate(order)
                  if k in ('renderLayerLabels', '_renderLayerWriting', 'renderLayerOffsets')]
    assert grid_at and writing_at, order
    assert max(writing_at) < min(grid_at), order
    assert order.index(tint) < min(grid_at), order
    assert order.index(badge) > max(grid_at), order


# ── Seen on every colour ────────────────────────────────────────────────

# One screen, every cabinet the one colour `rgb`, nothing written on it. At
# each LED pixel edge (device x / y = e) the grid draws on column / row e and
# e - 1; the best of the two must differ from the bare cell by `delta` in
# luminance. The columns / rows beyond (e + 1, e - 2) must be the bare cell:
# a line is crisp, never smeared over a third pixel.
CONTRAST_JS = """(rgb) => {
    const gc = window.__gc, r = window.canvasRenderer;
    const a = gc.screen({ id: 1, name: 'Plain', columns: 4, rows: 2, offset_x: 1000, offset_y: 600,
                          color1: rgb, color2: rgb, show_panel_borders: false, show_numbers: false,
                          showLabelName: false, showLabelSizePx: false, showLabelSizeMm: false,
                          showLabelInfo: false });
    return gc.withProject([a], [], 'pixel-map', () => {
        const W = r.canvas.width, H = r.canvas.height, z = 12;
        r.zoom = z;
        r.panX = Math.round(W / 2 - 1256 * z);
        r.panY = Math.round(H / 2 - 728 * z);
        const grab = () => r.ctx.getImageData(0, 0, W, H).data;
        r.render();
        const A = grab();
        r.renderPixelGrid = function () {};
        let G;
        try { r.render(); G = grab(); } finally { delete r.renderPixelGrid; }
        const lum = (D, i) => 0.299 * D[i] + 0.587 * D[i + 1] + 0.114 * D[i + 2];
        const bare = (i) => Math.abs(G[i] - rgb.r) + Math.abs(G[i + 1] - rgb.g)
            + Math.abs(G[i + 2] - rgb.b) <= 3;
        const same = (i) => Math.abs(A[i] - G[i]) + Math.abs(A[i + 1] - G[i + 1])
            + Math.abs(A[i + 2] - G[i + 2]) <= 3;
        const px = ((r.panX % z) + z) % z, py = ((r.panY % z) + z) % z;
        let edges = 0, least = Infinity, worst = null, smeared = 0;
        const at = (x, y) => (y * W + x) * 4;
        const look = (line, across, step) => {
            // `line` is the edge pixel e, `step` one pixel across the edge
            const i = line, j = line - step;
            if (!bare(i) || !bare(j)) return;
            const d = Math.max(Math.abs(lum(A, i) - lum(G, i)), Math.abs(lum(A, j) - lum(G, j)));
            edges++;
            if (d < least) { least = d; worst = [A[i], A[i + 1], A[i + 2], A[j], A[j + 1], A[j + 2]]; }
            if (across) {
                const k = line + step, m = line - 2 * step;
                if (bare(k) && !same(k)) smeared++;
                if (bare(m) && !same(m)) smeared++;
            }
        };
        for (let x = px + z; x < W - z; x += z) {
            for (let y = 2; y < H - 2; y += 3) {
                const off = (((y - py) % z) + z) % z;
                look(at(x, y), off >= 3 && off <= z - 4, 4);
            }
        }
        for (let y = py + z; y < H - z; y += z) {
            for (let x = 2; x < W - 2; x += 3) {
                const off = (((x - px) % z) + z) % z;
                look(at(x, y), off >= 3 && off <= z - 4, W * 4);
            }
        }
        return { edges, least: Math.round(least), worst, smeared };
    });
}"""


@pytest.mark.parametrize('name,rgb', [
    ('dark checker', {'r': 64, 'g': 70, 'b': 128}),
    ('light checker', {'r': 149, 'g': 156, 'b': 184}),
    ('white', {'r': 255, 'g': 255, 'b': 255}),
    ('mid grey', {'r': 128, 'g': 128, 'b': 128}),
    ('black', {'r': 0, 'g': 0, 'b': 0}),
])
def test_the_grid_is_crisp_and_clear_on_every_cell_colour(page, name, rgb):
    """The owner (2026-11-16): the grid must be clearly visible on every cell
    colour, each line crisp on whole pixels. Every edge reads at least 40
    luminance off the bare cell, and no line spreads past its pixels."""
    out = page.evaluate(CONTRAST_JS, rgb)
    assert not page.errors, page.errors
    assert out['edges'] >= 2000, f'{name}: the frame missed the screen: {out}'
    assert out['least'] >= 40, f'{name}: a grid line barely shows: {out}'
    assert out['smeared'] == 0, f'{name}: a grid line is blurred onto a third pixel: {out}'


def test_an_export_never_draws_the_grid(page):
    """A drawing for paper or a file (exportMode) has no grid, whatever its
    zoom: a small wall on a binder map can be drawn past 1000 %."""
    out = page.evaluate("""() => {
        const gc = window.__gc, r = window.canvasRenderer;
        const a = gc.screen({ id: 1, name: 'A', offset_x: 1000, offset_y: 600 });
        return gc.withProject([a], [], 'pixel-map', () => {
            let calls = 0;
            r.renderPixelGrid = function () { calls++; };
            r.zoom = 12;
            r.panX = Math.round(r.canvas.width / 2 - 1128 * 12);
            r.panY = Math.round(r.canvas.height / 2 - 664 * 12);
            const keep = r.exportMode;
            let live = 0, exported = 0;
            try {
                r.render(); live = calls; calls = 0;
                r.exportMode = true;
                r.render(); exported = calls;
            } finally { r.exportMode = keep; delete r.renderPixelGrid; }
            return { live, exported };
        });
    }""")
    assert not page.errors, page.errors
    assert out['live'] > 0, out
    assert out['exported'] == 0, out
