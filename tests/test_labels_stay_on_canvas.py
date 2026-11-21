"""A label is never cut by the canvas edge (2026-11-20, from #124).

A screen may hang past the edge of its canvas, on Pixel Map and on Show
Look. Its labels used to be centred on the whole screen and cut at the
canvas edge ("512 X H 256" printed for W 512 X H 256). The rule:

  * When a screen hangs past the canvas, every label drawn for it (the
    name, the lines under it, the info bar, the corner and Show Look
    coordinate readouts) slides inward until it is whole on the canvas,
    inside the part of the screen on the canvas.
  * When that part is narrower (or shorter) than the label, the label
    stays whole, from the canvas edge the screen hangs past, rather than
    being cut.
  * A screen wholly on the canvas draws exactly as before, pixel for
    pixel.

Checked on the canvas and in the export, on Pixel Map and Show Look, for
screens hanging off the left, top, right and bottom, and for slivers.

Run locally:
    python -m pytest tests/test_labels_stay_on_canvas.py -v -n 4 --dist loadfile
"""

import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'src'))
sys.path.insert(0, HERE)

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


def _cancelled(route):
    route.fulfill(status=200, content_type='application/json',
                  body=json.dumps({'ok': False, 'cancelled': True}))


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 1000})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    # No real Windows dialog may open on the owner's desktop.
    for path in ('save-file', 'open-file', 'select-directory'):
        pg.route(f'**/api/native-dialog/{path}', _cancelled)
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app.project"
                         " && window.app._initialLoadComplete === true"
                         " && window.canvasRenderer"
                         " && window.canvasRenderer.zoom > 0", timeout=20000)
    pg.wait_for_timeout(500)
    yield pg, errors
    context.close()


# One canvas, 1920 x 1080 on Pixel Map and Show Look. Each screen is 4 x 2
# cabinets of 128 (512 x 256) and hangs past a different edge on each tab;
# the slivers have less of themselves on the canvas than a label is wide
# (or tall). ON CANVAS is wholly on the canvas on both.
SCREENS = [
    # name, Pixel Map x, y, Show Look x, y
    ('LEFT EDGE', -300, 300, 400, -150),       # Show Look: off the top
    ('TOP EDGE', 700, -200, 1650, 300),        # Show Look: off the right
    ('RIGHT EDGE', 1700, 450, -250, 600),      # Show Look: off the left
    ('BOTTOM EDGE', 900, 950, 800, 900),       # both: off the bottom
    ('SIDE SLIVER', -490, 700, 1900, 780),     # 22 px on / 20 px on
    ('TOP SLIVER', 100, -240, 100, 1060),      # 16 px on / 20 px on
    ('ON CANVAS', 1100, 150, 1100, 150),
]
HANGING = [s[0] for s in SCREENS if s[0] != 'ON CANVAS']

SEED_JS = """async (specs) => {
    const app = window.app, r = window.canvasRenderer;
    await app._layerSavesSettled();
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(x => x.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = []; proj.beaches = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.fiberCables;
    delete proj.pullSheetEdits;
    const base = proj.canvases[0];
    proj.canvases = [Object.assign({}, base, {id: 'c1', name: 'Main', workspace_x: 0, workspace_y: 0,
        raster_width: 1920, raster_height: 1080, show_raster_width: 1920, show_raster_height: 1080})];
    proj.active_canvas_id = 'c1';
    await j('PUT', '/api/project', proj);
    const ids = {};
    for (const [name, x, y, sx, sy] of specs) {
        const l = await j('POST', '/api/layer/add', {name, offset_x: x, offset_y: y,
            columns: 4, rows: 2, cabinet_width: 128, cabinet_height: 128, canvas_id: 'c1'});
        // Every label there is, on both tabs.
        await j('PUT', `/api/layer/${l.id}`, {showOffsetX: sx, showOffsetY: sy,
            showLabelName: true, showLabelSizePx: true, showLabelSizeM: true,
            showLabelInfo: true,
            showOffsetTL: true, showOffsetTR: true, showOffsetBL: true, showOffsetBR: true,
            showLabelSizePxShowLook: true, showOffsetTLShowLook: true});
        ids[name] = l.id;
    }
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('labels_on_canvas_seed');
    app.project.active_canvas_id = 'c1';
    app.selectLayer(app.project.layers[0]);
    app.syncRasterFromProject();
    app.renderLayers();
    app.updateUI();
    app.resetHistory('Labels On Canvas Seed');
    r.fitToView();
    r.render();
    return ids;
}"""

# Every fillText while window.__ftLog is an array: its text box and the box
# of the canvas the screen is drawn on (the frame's raster, Show Look shift
# taken off), both in the drawing surface's own pixels.
SPY_JS = """() => {
    if (window.__ftBoxSpy) return;
    const orig = CanvasRenderingContext2D.prototype.fillText;
    CanvasRenderingContext2D.prototype.fillText = function (t, x, y, ...rest) {
        if (window.__ftLog) {
            const r = window.canvasRenderer;
            const m = this.getTransform();
            const fs = parseFloat((/(\\d+(?:\\.\\d+)?)px/.exec(this.font) || [])[1]) || 0;
            const w = this.measureText(String(t)).width;
            const al = this.textAlign, bl = this.textBaseline;
            const x1 = al === 'center' ? x - w / 2 : (al === 'right' || al === 'end') ? x - w : x;
            const y1 = bl === 'middle' ? y - fs / 2
                : (bl === 'bottom' || bl === 'alphabetic' || bl === 'ideographic') ? y - fs : y;
            const a = m.transformPoint(new DOMPoint(x1, y1));
            const b = m.transformPoint(new DOMPoint(x1 + w, y1 + fs));
            const dx = r._renderDx || 0, dy = r._renderDy || 0;
            const c1 = m.transformPoint(new DOMPoint(-dx, -dy));
            const c2 = m.transformPoint(new DOMPoint(r.rasterWidth - dx, r.rasterHeight - dy));
            window.__ftLog.push({t: String(t), w: this.canvas.width,
                box: [Math.min(a.x, b.x), Math.min(a.y, b.y), Math.max(a.x, b.x), Math.max(a.y, b.y)],
                canvas: [Math.min(c1.x, c2.x), Math.min(c1.y, c2.y), Math.max(c1.x, c2.x), Math.max(c1.y, c2.y)]});
        }
        return orig.call(this, t, x, y, ...rest);
    };
    window.__ftBoxSpy = true;
}"""

LABEL_WORDS = ('W ', 'X ', 'Columns', 'Cabinets', 'Resolution', 'Aspect', 'Weight')


def _is_label(t, names):
    return t.startswith(LABEL_WORDS) or '(m)' in t or any(n in t for n in names)


CANVAS_JS = """(view) => {
    const r = window.canvasRenderer;
    r.viewMode = view;
    r.fitToView();
    window.__ftLog = [];
    r.render();
    const log = window.__ftLog; window.__ftLog = null;
    return log;
}"""

EXPORT_JS = """async ([format, views, stubHang]) => {
    const app = window.app, r = window.canvasRenderer;
    const keep = app.downloadRenderedPNGs;
    const keepHang = r._labelHangFrame;
    let items = null;
    app.downloadRenderedPNGs = async (it) => { items = it; };
    if (stubHang) r._labelHangFrame = () => null;
    window.__ftLog = [];
    try {
        await app.performExport('Edges', format, views, ['c1']);
    } finally {
        app.downloadRenderedPNGs = keep;
        if (stubHang) r._labelHangFrame = keepHang;
    }
    const log = window.__ftLog; window.__ftLog = null;
    return {items: (items || []).map(i => ({view: i.view, dataUrl: i.dataUrl})), log};
}"""


def _seed(pg):
    pg.evaluate(SPY_JS)
    return pg.evaluate(SEED_JS, SCREENS)


def _outside(log, names):
    bad = []
    for e in log:
        if not _is_label(e['t'], names):
            continue
        x1, y1, x2, y2 = e['box']
        c1, d1, c2, d2 = e['canvas']
        if x1 < c1 - 1.5 or y1 < d1 - 1.5 or x2 > c2 + 1.5 or y2 > d2 + 1.5:
            bad.append((e['t'], [round(v) for v in e['box']], [round(v) for v in e['canvas']]))
    return bad


def _drawn(log, names):
    return [e['t'] for e in log if _is_label(e['t'], names)]


@pytest.mark.parametrize('view', ['pixel-map', 'show-look'])
def test_every_label_is_whole_on_the_canvas_on_screen(page, view):
    pg, errors = page
    _seed(pg)
    names = [s[0] for s in SCREENS]
    log = pg.evaluate(CANVAS_JS, view)
    texts = _drawn(log, names)
    # Every screen is labelled: a hanging screen keeps its name.
    for n in names:
        assert n in texts, (n, texts)
    assert 'W 512 X H 256' in texts
    assert _outside(log, names) == []
    assert errors == []


def test_every_label_is_whole_on_the_canvas_in_the_export(page):
    pg, errors = page
    _seed(pg)
    names = [s[0] for s in SCREENS]
    out = pg.evaluate(EXPORT_JS, ['png', ['pixel-map', 'show-look'], False])
    assert [i['view'] for i in out['items']] == ['pixel-map', 'show-look']
    log = [e for e in out['log'] if e['w'] == 1920]
    texts = _drawn(log, names)
    for n in names:
        assert texts.count(n) == 2, (n, texts)
    # The size line every screen carries, whole: twice per screen (one per
    # view), never "512 X H 256".
    assert texts.count('W 512 X H 256') == 2 * len(names), texts
    # Show Look's coordinates still read the true figures.
    for want in ('X 400, Y -150', 'X -250, Y 600', 'X 1650, Y 300', 'X 100, Y 1060'):
        assert want in texts, (want, texts)
    assert _outside(log, names) == []
    assert errors == []


def test_a_sliver_keeps_its_labels_whole_from_the_canvas_edge(page):
    """SIDE SLIVER has 22 px on the canvas on Pixel Map: its name and size
    are wider, so they stand whole from the canvas's left edge."""
    pg, errors = page
    _seed(pg)
    log = pg.evaluate(CANVAS_JS, 'pixel-map')
    name = [e for e in log if e['t'] == 'SIDE SLIVER']
    assert len(name) == 1, name
    x1, _, x2, _ = name[0]['box']
    c1 = name[0]['canvas'][0]
    assert x1 >= c1 - 1.5 and x2 - c1 > 22, name
    assert errors == []


def test_a_screen_wholly_on_the_canvas_draws_exactly_as_before(page):
    """The slide never touches a screen wholly on the canvas: with every
    hanging screen hidden, the export is pixel for pixel the one drawn with
    the slide switched off, and no label of ON CANVAS moved."""
    pg, errors = page
    ids = _seed(pg)
    pg.evaluate("""async (ids) => {
        const a = window.app;
        const ls = a.project.layers.filter(l => ids.includes(l.id));
        ls.forEach(l => { l.visible = false; });
        a.updateLayers(ls, false);
        await a._layerSavesSettled();
    }""", [ids[n] for n in HANGING])
    on = pg.evaluate(EXPORT_JS, ['png', ['pixel-map', 'show-look'], False])
    off = pg.evaluate(EXPORT_JS, ['png', ['pixel-map', 'show-look'], True])
    assert len(on['items']) == 2 and len(off['items']) == 2
    for a, b in zip(on['items'], off['items']):
        assert a['view'] == b['view']
        assert a['dataUrl'] == b['dataUrl'], f"{a['view']}: a wholly-on screen drew differently"
    assert [(e['t'], e['box']) for e in on['log']] == [(e['t'], e['box']) for e in off['log']]
    assert pg.evaluate("() => window.canvasRenderer._labelHangFrame("
                       "{x: 1100, y: 150, width: 512, height: 256})") is None
    assert errors == []
