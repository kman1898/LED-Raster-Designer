"""Labels are drawn over every border, grid line and outline, on every view.

Matt's ruling (2026-11-09): "on any screen or canvas, including 3D we need
to have screen labels and stuff to be overtop of borders etc."

canvas.js render() draws every screen's cabinets first, then the lines that
go with them - the canvas outlines, the selection boxes, the Pixel Map's
cabinet selection, the pixel grid - and only then each screen's writing (the
label pass): name plates and sizes, corner readouts, Cabinet IDs, the IDM
Locator's module IDs, the data and power runs with their discs and tags. A
screen drawn later that lies OVER another still covers it. The 3D tab paints
a screen's writing onto a sheet of its own laid 5 mm proud of the face, over
the seam lines, depth tested so a screen truly in front still hides it.

Each test draws the same frame twice: as it is, and with the one line that
could cover the label switched off. Where the second frame has label ink (the
text's own colour), the first must have it too: a line drawn over the text
changes those pixels, a line drawn under it does not.

The 2D tests run against SYNTHETIC projects (test_screen_groups_canvas's
helpers): the project is swapped in and put back inside one evaluate.

Run locally:
    python -m pytest tests/test_labels_on_top.py -v -p no:cacheprovider --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from conftest import settled  # noqa: E402
from test_screen_groups_canvas import HELPERS_JS  # noqa: E402

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it (the 3D
    tests put their own screens on it)."""


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


# ── 2D ──────────────────────────────────────────────────────────────────

# One frame, drawn twice: `cover` names the renderer method that draws the
# line under test, no-op'd for the second drawing. `kind` says where the
# label is: the target screen's name plate ('name', black text), its first
# label disc in the Data / Power view ('disc', black text), or one IDM module
# ID ('module', in the label colour the field is given). The frame is zoomed
# to `zoom` and centred on the label. Returns how many pixels of the second
# drawing are label ink and how many of those the first drawing changed.
INK_JS = """([mode, spec]) => {
    const gc = window.__gc, r = window.canvasRenderer, app = window.app;
    const layers = spec.layers.map(o => gc.screen(o));
    const groups = spec.group ? [gc.group(layers)] : [];
    return gc.withProject(layers, groups, mode, () => {
        if (spec.names) app.project.groupNameDisplay = spec.names;
        if (spec.idmField) app.project.idmField = spec.idmField;
        const target = layers[spec.target || 0];
        const keep = { sel: app.pixelMapSelection };
        if (spec.select) {
            app.currentLayer = target;
            app.selectedLayerIds = new Set([target.id]);
            app.pixelMapSelection = new Set(spec.select.map(k => target.id + ':' + k));
        }
        try {
            const W = r.canvas.width, H = r.canvas.height;
            const frame = (wx, wy) => {
                r.zoom = spec.zoom;
                r.panX = Math.round(W / 2 - wx * spec.zoom);
                r.panY = Math.round(H / 2 - wy * spec.zoom);
            };
            const toPx = (b) => ({
                x: b.x * r.zoom + Math.round(r.panX), y: b.y * r.zoom + Math.round(r.panY),
                w: b.w * r.zoom, h: b.h * r.zoom,
            });
            let box = null, ink = [0, 0, 0];
            if (spec.kind === 'name') {
                r.zoom = 1; r.panX = 0; r.panY = 0;
                r.render();
                let h = target._screenNameHitRect;
                if (!h) return { error: 'no name plate' };
                frame((h.x1 + h.x2) / 2, (h.y1 + h.y2) / 2);
                r.render();
                h = target._screenNameHitRect;
                box = toPx({ x: h.x1, y: h.y1, w: h.x2 - h.x1, h: h.y2 - h.y1 });
            } else if (spec.kind === 'disc') {
                frame(spec.at[0], spec.at[1]);
                r.startLabelProbe();
                try { r.render(); } finally { var reg = r.endLabelProbe(); }
                const disc = (reg || []).filter(b => b.kind === 'disc')
                    .sort((a, b) => Math.hypot(a.x + a.w / 2 - W / 2, a.y + a.h / 2 - H / 2)
                                  - Math.hypot(b.x + b.w / 2 - W / 2, b.y + b.h / 2 - H / 2))[0];
                if (!disc) return { error: 'no disc' };
                box = { x: disc.x, y: disc.y, w: disc.w, h: disc.h };
            } else if (spec.kind === 'module') {
                r.zoom = spec.zoom;
                const L = r.idmModuleLabels(target, { scale: spec.zoom });
                const s = L.sites[0];
                if (!s) return { error: 'no module ids' };
                frame(s.x + s.w / 2, s.y + s.h / 2);
                box = toPx({ x: s.x, y: s.y, w: s.w, h: s.h });
                const m = /rgb\\((\\d+), *(\\d+), *(\\d+)\\)/.exec(s.color) || [];
                ink = m.length ? [+m[1], +m[2], +m[3]]
                    : [parseInt(s.color.slice(1, 3), 16), parseInt(s.color.slice(3, 5), 16), parseInt(s.color.slice(5, 7), 16)];
            }
            const x0 = Math.max(0, Math.floor(box.x)), y0 = Math.max(0, Math.floor(box.y));
            const x1 = Math.min(W, Math.ceil(box.x + box.w)), y1 = Math.min(H, Math.ceil(box.y + box.h));
            if (x1 - x0 < 4 || y1 - y0 < 4) return { error: 'label off the frame', box };
            const grab = () => r.ctx.getImageData(0, 0, W, H).data;
            r.render();
            const A = grab();
            r[spec.cover] = function () {};
            let B;
            try { r.render(); B = grab(); } finally { delete r[spec.cover]; }
            r.render();
            let inked = 0, changed = 0, coverSeen = 0;
            for (let i = 0; i < B.length; i += 4) {
                if (Math.abs(A[i] - B[i]) + Math.abs(A[i + 1] - B[i + 1]) + Math.abs(A[i + 2] - B[i + 2]) > 24) coverSeen++;
            }
            for (let y = y0; y < y1; y++) {
                for (let x = x0; x < x1; x++) {
                    const i = (y * W + x) * 4;
                    const near = (d, k) => Math.abs(d[i + k] - ink[k]) <= 8;
                    if (!(near(B, 0) && near(B, 1) && near(B, 2))) continue;
                    inked++;
                    if (Math.abs(A[i] - B[i]) > 8 || Math.abs(A[i + 1] - B[i + 1]) > 8 || Math.abs(A[i + 2] - B[i + 2]) > 8) changed++;
                }
            }
            return { inked, changed, coverSeen, box: [x0, y0, x1 - x0, y1 - y0] };
        } finally {
            app.pixelMapSelection = keep.sel;
        }
    });
}"""


def ink(page, mode, spec):
    out = page.evaluate(INK_JS, [mode, spec])
    assert 'error' not in out, out
    return out


def assert_label_wins(out, what):
    assert out['inked'] >= 40, f'{what}: too little label ink in the frame to judge: {out}'
    # the covering line really is drawn in the frame, only never on the ink
    assert out['coverSeen'] > 0, f'{what}: the line under test was never drawn: {out}'
    assert out['changed'] == 0, f'{what}: a line was drawn over the label text: {out}'


NAMED = {'name': 'MMMMMMM', 'columns': 2, 'rows': 2}

GRID_VIEWS = ['pixel-map', 'cabinet-id', 'show-look', 'data-flow', 'power', 'rigging']


@pytest.mark.parametrize('mode', GRID_VIEWS)
def test_the_name_plate_is_over_the_pixel_grid(page, mode):
    """Zoomed to 1200 %, every view draws the LED pixel grid over the
    cabinets; the screen's name plate is drawn over the grid."""
    spec = {'layers': [dict(NAMED)], 'kind': 'name', 'zoom': 12, 'cover': 'renderPixelGrid'}
    if mode == 'cabinet-id':
        spec['layers'][0]['showLabelNameCabinet'] = True
    assert_label_wins(ink(page, mode, spec), f'{mode} name plate')


@pytest.mark.parametrize('mode', ['data-flow', 'power'])
def test_the_port_and_circuit_discs_are_over_the_pixel_grid(page, mode):
    """The run's label disc (P1, S1-1) is drawn over the grid too: the runs
    and their discs go in the label pass with the name plate."""
    spec = {'layers': [dict(NAMED)], 'kind': 'disc', 'at': [64, 64], 'zoom': 12,
            'cover': 'renderPixelGrid'}
    assert_label_wins(ink(page, mode, spec), f'{mode} disc')


def test_the_idm_module_ids_are_over_the_pixel_grid(page):
    """The IDM Locator's module IDs are drawn over the grid."""
    spec = {'layers': [dict(NAMED)], 'kind': 'module', 'zoom': 12, 'cover': 'renderPixelGrid',
            'idmField': {'color': '#ffffff', 'border': 'lines', 'moduleIds': True,
                         'labelColor': '#ff00ff'}}
    assert_label_wins(ink(page, 'idm', spec), 'IDM module ID')


def test_the_name_plate_is_over_the_cabinet_selection(page):
    """The Pixel Map's cabinet selection (a tint and an outline on every
    picked cabinet, its edges crossing the plate) goes under the name."""
    spec = {'layers': [dict(NAMED)], 'kind': 'name', 'zoom': 1,
            'select': ['0,0', '0,1', '1,0', '1,1'], 'cover': 'renderPixelMapSelectionOverlay'}
    assert_label_wins(ink(page, 'pixel-map', spec), 'selected cabinets')


def test_a_member_name_is_over_its_groups_circle_and_x(page):
    """A group draws ONE circle-and-X across its members, in its last
    member's pass; the first member's own name plate, at that circle's left
    edge, is drawn over it."""
    spec = {'layers': [dict(NAMED, id=1, group_id='g1', show_circle_with_x=True),
                       {'id': 2, 'name': 'Right', 'columns': 2, 'rows': 2, 'offset_x': 256,
                        'group_id': 'g1', 'show_circle_with_x': True}],
            'group': True, 'names': 'screens', 'target': 0, 'kind': 'name', 'zoom': 2,
            'cover': 'renderCircleWithX'}
    assert_label_wins(ink(page, 'pixel-map', spec), 'group member name')


def test_a_screen_drawn_over_another_still_covers_its_name(page):
    """The label pass never lifts writing over a SCREEN: where a later
    screen lies over this one, its name plate stays under it."""
    out = page.evaluate("""() => {
        const gc = window.__gc, r = window.canvasRenderer;
        const under = gc.screen({ id: 1, name: 'MMMMMMM', columns: 2, rows: 2 });
        const over = gc.screen({ id: 2, name: 'Top', columns: 2, rows: 2, offset_x: 64, offset_y: 64,
                                 color1: { r: 0, g: 255, b: 0 }, color2: { r: 0, g: 255, b: 0 },
                                 show_panel_borders: false, show_circle_with_x: false,
                                 showLabelName: false, showLabelSizePx: false });
        return gc.withProject([under, over], [], 'pixel-map', () => {
            r.zoom = 1; r.panX = 0; r.panY = 0;
            r.render();
            const h = under._screenNameHitRect;
            // the middle of the under screen's plate lies inside the top screen
            const px = r.ctx.getImageData(Math.round((h.x1 + h.x2) / 2), Math.round((h.y1 + h.y2) / 2), 1, 1).data;
            return [px[0], px[1], px[2]];
        });
    }""")
    assert out == [0, 255, 0], out


def test_the_writing_is_drawn_once_after_every_screen(page):
    """The order itself: every screen's cabinets, then the lines, then the
    writing - one name per screen, in the screens' order, never twice."""
    out = page.evaluate("""() => {
        const gc = window.__gc, r = window.canvasRenderer;
        const a = gc.screen({ id: 1, name: 'A' });
        const b = gc.screen({ id: 2, name: 'B', offset_x: 400 });
        return gc.withProject([a, b], [], 'pixel-map', () => {
            const order = [];
            const keep = {};
            ['renderPanel', 'renderPixelGrid', 'renderLayerLabels'].forEach(k => {
                keep[k] = r[k];
                r[k] = function (...args) { order.push(k + ':' + args[args.length === 2 && k === 'renderPanel' ? 1 : 0].name); return keep[k].apply(this, args); };
            });
            r.zoom = 12;
            try { r.render(); } finally { Object.keys(keep).forEach(k => { delete r[k]; }); }
            return order.filter((v, i, all) => all.indexOf(v) === i);
        });
    }""")
    labels = [o for o in out if o.startswith('renderLayerLabels')]
    assert labels == ['renderLayerLabels:A', 'renderLayerLabels:B'], out
    last_line = max(i for i, o in enumerate(out) if not o.startswith('renderLayerLabels'))
    assert out.index('renderLayerLabels:A') > last_line, out


# ── 3D ──────────────────────────────────────────────────────────────────

RESET_JS = """async (specs) => {
    const app = window.app;
    let project = await (await fetch('/api/project')).json();
    project.layers = [];
    project.groups = [];
    delete project.stage3dCamera;
    if (app._s3d) app._s3d.bars = true;
    await fetch('/api/project', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(project),
    });
    const ids = [];
    for (const s of specs) {
        const made = await (await fetch('/api/layer/add', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(Object.assign({
                cabinet_width: 128, cabinet_height: 128,
                panel_width_mm: 500, panel_height_mm: 500,
            }, s)),
        })).json();
        ids.push(made.id);
    }
    app.project = await (await fetch('/api/project')).json();
    app.dedupeProjectLayers('labels_on_top_reset');
    if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
    app.resetHistory('Labels On Top Reset');
    app.selectLayer(app.project.layers.find(l => l.id === ids[0]));
    app.updateUI();
    return ids;
}"""


def dbg(page):
    return page.evaluate('window.app._s3dDebug()')


def open_3d(page, count):
    page.click('#view-tabs .view-tab[data-mode="3d"]')
    got = settled(page, lambda: dbg(page),
                  lambda d: d['loaded'] and len(d['screens']) == count
                  and all(s['tex'] for s in d['screens']), 10000)
    assert got['loaded'] and got['webgl'], got
    page.click('[data-s3d-view="front"]')
    settled(page, lambda: dbg(page), lambda d: not d['gliding'], 3000)
    return got


# The 3D frame, drawn twice: as it is, and with every screen's seam lines
# put away. Nothing selected (no move handles), the seams in their plain
# dark. In a box round the screen's centre - its name plate and size
# readout sit there, across the middle seam - the pixels that are light in
# the second frame (the plates' white, the readout's white text) must stay
# light in the first. `light` is the count of those pixels, `changed` how
# many a seam darkened, `seamSeen` how many pixels of the whole frame the
# seams change (the plates are see-through, so a seam may tint one a
# shade, never darken it).
SEAM_JS = """(id) => {
    const app = window.app, st = app._s3dState();
    app.selectedLayerIds = new Set();
    app.currentLayer = null;
    app._s3dHighlight(app._s3dTokens());
    if (st.handles) st.handles.group.visible = false;
    const gl = st.renderer.domElement;
    const e = st.entries.get(id);
    const T = st.T;
    e.obj.updateMatrixWorld(true);
    const c = new T.Box3().setFromObject(e.front).getCenter(new T.Vector3()).project(st.camera);
    const cx = Math.round((c.x + 1) / 2 * gl.width), cy = Math.round((1 - c.y) / 2 * gl.height);
    const half = Math.round(gl.width * 0.06);
    const W = gl.width, H = gl.height;
    const grab = () => {
        st.renderer.render(st.scene, st.camera);
        const cv = document.createElement('canvas');
        cv.width = W; cv.height = H;
        const g = cv.getContext('2d');
        g.drawImage(gl, 0, 0);
        return g.getImageData(0, 0, W, H).data;
    };
    const A = grab();
    const shown = [...st.entries.values()].map(x => [x, x.lines.visible]);
    shown.forEach(([x]) => { x.lines.visible = false; });
    let B;
    try { B = grab(); } finally { shown.forEach(([x, v]) => { x.lines.visible = v; }); }
    st.renderer.render(st.scene, st.camera);
    let light = 0, changed = 0, seamSeen = 0;
    const diff = (i) => Math.abs(A[i] - B[i]) + Math.abs(A[i + 1] - B[i + 1]) + Math.abs(A[i + 2] - B[i + 2]);
    for (let i = 0; i < B.length; i += 4) if (diff(i) > 24) seamSeen++;
    for (let y = Math.max(0, cy - half); y < Math.min(H, cy + half); y++) {
        for (let x = Math.max(0, cx - half); x < Math.min(W, cx + half); x++) {
            const i = (y * W + x) * 4;
            if (!(B[i] >= 225 && B[i + 1] >= 225 && B[i + 2] >= 225)) continue;
            light++;
            if (diff(i) > 90) changed++;
        }
    }
    return { light, changed, seamSeen, centre: [cx, cy], half };
}"""


def test_3d_labels_are_over_the_seams(page):
    """The 3D tab: a screen's name plate and size readout sit across its
    middle seam, and the seam line does not cross them."""
    ids = page.evaluate(RESET_JS, [
        # no white test pattern or borders on the face: only the writing
        # is white in the box
        {'name': 'MMMMMMMMMMM', 'columns': 4, 'rows': 2, 'showLabelSizePx': True,
         'show_circle_with_x': False, 'show_panel_borders': False,
         'stage3d': {'x': 0, 'y': 500, 'z': 0}},
    ])
    page.wait_for_timeout(300)
    open_3d(page, 1)
    out = page.evaluate(SEAM_JS, ids[0])
    assert out['light'] >= 200, out
    assert out['seamSeen'] > 0, out
    assert out['changed'] == 0, f'a seam line was drawn over the label: {out}'
    # the writing is its own sheet, over the face, and never picked
    info = page.evaluate("""(id) => {
        const st = window.app._s3dState(), e = st.entries.get(id);
        return { sheet: !!e.labels && e.labels.visible && e.labels.parent === e.obj,
                 order: e.labels.renderOrder > e.lines.renderOrder,
                 depthTest: e.labelMat.depthTest, depthWrite: e.labelMat.depthWrite,
                 map: !!e.labelMat.map };
    }""", ids[0])
    assert info == {'sheet': True, 'order': True, 'depthTest': True, 'depthWrite': False,
                    'map': True}, info
    assert not page.errors, page.errors


def test_3d_labels_still_hide_behind_a_screen_in_front(page):
    """A screen standing in front of another hides that screen's labels:
    the writing's sheet is depth tested."""
    green = {'r': 0, 'g': 255, 'b': 0}
    ids = page.evaluate(RESET_JS, [
        {'name': 'MMMMMMMMMMM', 'columns': 4, 'rows': 2, 'showLabelSizePx': True,
         'stage3d': {'x': 0, 'y': 500, 'z': 0}},
        {'name': 'Front', 'columns': 4, 'rows': 2, 'offset_x': 0, 'offset_y': 600,
         'color1': green, 'color2': green, 'show_panel_borders': False,
         'show_circle_with_x': False, 'showLabelName': False, 'showLabelSizePx': False,
         'stage3d': {'x': 0, 'y': 500, 'z': 1500}},
    ])
    page.wait_for_timeout(300)
    open_3d(page, 2)
    out = page.evaluate("""(id) => {
        const app = window.app, st = app._s3dState();
        app.selectedLayerIds = new Set();
        app.currentLayer = null;
        app._s3dHighlight(app._s3dTokens());
        if (st.handles) st.handles.group.visible = false;
        const gl = st.renderer.domElement, T = st.T;
        const e = st.entries.get(id);
        e.obj.updateMatrixWorld(true);
        const c = new T.Box3().setFromObject(e.front).getCenter(new T.Vector3()).project(st.camera);
        const cx = Math.round((c.x + 1) / 2 * gl.width), cy = Math.round((1 - c.y) / 2 * gl.height);
        st.renderer.render(st.scene, st.camera);
        const cv = document.createElement('canvas');
        cv.width = gl.width; cv.height = gl.height;
        const g = cv.getContext('2d');
        g.drawImage(gl, 0, 0);
        const half = Math.round(gl.width * 0.04);
        const d = g.getImageData(cx - half, cy - half, half * 2, half * 2).data;
        let light = 0, green = 0;
        for (let i = 0; i < d.length; i += 4) {
            if (d[i] >= 225 && d[i + 1] >= 225 && d[i + 2] >= 225) light++;
            if (d[i] < 60 && d[i + 1] > 200 && d[i + 2] < 60) green++;
        }
        return { light, green, total: d.length / 4 };
    }""", ids[0])
    assert out['green'] > out['total'] * 0.9, out
    assert out['light'] == 0, f"the back screen's label showed through the front screen: {out}"
    assert not page.errors, page.errors
