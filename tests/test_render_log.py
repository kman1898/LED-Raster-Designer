"""What the app draws, in the app log (2026-11-19 logging audit, phase 2;
the owner, 2026-11-18: render paths log their output, not just the saved
data). A 3D texture once drew blue with a red corner while the screen's
saved colours were blue, and the log said nothing.

What this file pins (render-log.js, canvas.js, app-stage3d.js,
app-output-display.js, app-export-io.js):

* RenderLog's pure parts: colour parsing, the 3 x 3 grid, the line
  throttle (first at once, then folded with its `n`; nothing when the
  signature did not change).
* A view switch writes one render_view line once the view is quiet: the
  view, the canvas, the screens drawn and the selected screen's cabinets
  read back against their own colours. A picture that is not those colours
  makes it a warning with `mismatch`.
* Entering 3D writes render_3d_sync (the stage's screens) and
  render_3d_paint (what each texture drew and why); a texture painted with
  a wrong corner makes render_3d_paint a warning naming the corner
  ("mismatch": ["bl"]).
* An output frame writes output_frame (its size and colour grid), and the
  frames that follow within 2 s fold into the next line's `n`.
* An export writes export_rendered: each file's view, size, bytes and
  colour grid, never the picture.

Run locally:
    python -m pytest tests/test_render_log.py -p no:cacheprovider
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from conftest import settled  # noqa: E402

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_stage3d import _context, open_3d, open_tab, reset  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), '..')

ONE = [{'name': 'Wall', 'columns': 6, 'rows': 2, 'offset_x': 0, 'offset_y': 0}]

# Every line the page sends to the log, as the page sent it.
CLIENT_LOG = (
    "window.__clog = [];"
    "(function () { const send = navigator.sendBeacon && navigator.sendBeacon.bind(navigator);"
    " navigator.sendBeacon = (u, b) => { try { b.text().then(t => { const j = JSON.parse(t);"
    " window.__clog.push({ action: j.action, details: j.details }); }); } catch (e) {}"
    " return send ? send(u, b) : true; }; })();"
)


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project exactly as this module found it
    (see conftest.server_project_guard)."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = _context(pw_browser, CLIENT_LOG)
    pg = context.new_page()
    pg.errors = []
    pg.on('pageerror', lambda err: pg.errors.append(str(err)))
    pg.route('**/api/native-dialog/**', lambda route: route.fulfill(
        status=200, content_type='application/json', body='{"ok": false, "cancelled": true}'))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app.project && window.RenderLog", timeout=15000)
    pg.wait_for_timeout(1000)
    yield pg
    context.close()


def logged(pg, action, since=0):
    return [e['details'] for e in pg.evaluate("() => window.__clog")[since:] if e['action'] == action]


def log_len(pg):
    return pg.evaluate("() => window.__clog.length")


def test_the_file_is_loaded_before_the_renderer_mixins():
    """render-log.js runs after canvas.js and before the mixins and main.js."""
    with open(os.path.join(ROOT, 'src', 'templates', 'index.html'), encoding='utf-8') as fh:
        html = fh.read()
    at = html.index('/static/js/render-log.js')
    assert html.index('/static/js/canvas.js"') < at < html.index('/static/js/canvas-data.js')
    assert at < html.index('/static/js/main.js')


def test_the_pure_parts(page):
    out = page.evaluate("""async () => {
        const RL = window.RenderLog;
        const c = document.createElement('canvas');
        c.width = 60; c.height = 30;
        const ctx = c.getContext('2d');
        ctx.fillStyle = '#0000ff'; ctx.fillRect(0, 0, 60, 30);
        ctx.fillStyle = '#ff0000'; ctx.fillRect(0, 20, 20, 10);
        const lines = [];
        const w = RL.watcher({ leading: true, gapMs: 200, emit: (info, n) => lines.push([info, n]) });
        w.seen('a'); w.seen('b'); w.seen('c');
        const first = lines.slice();
        await new Promise(r => setTimeout(r, 350));
        const sigLines = [];
        const s = RL.watcher({ quietMs: 50, gapMs: 0, sig: (x) => x, emit: (info, n) => sigLines.push([info, n]) });
        s.seen('x'); s.seen('x');
        await new Promise(r => setTimeout(r, 120));
        s.seen('x');
        await new Promise(r => setTimeout(r, 120));
        s.seen('y');
        await new Promise(r => setTimeout(r, 120));
        return {
            parse: [RL.parse('rgb(1, 2, 3)'), RL.parse('#0a0B0c'), RL.parse('#fff'), RL.parse('nope')],
            hex: RL.hex([255, 0, 16]), near: [RL.near([0, 0, 0], [6, 6, 6]), RL.near([0, 0, 0], [7, 0, 0])],
            grid: RL.grid(c), empty: RL.grid(Object.assign(document.createElement('canvas'), { width: 0 })),
            first, lines, sigLines,
            skip: [RL.skipWhy(null, { gradientEnabled: true }), RL.skipWhy({ printerMode: true }, {}),
                   RL.skipWhy(null, { show_circle_with_x: true }), RL.skipWhy(null, {}),
                   RL.skipWhy(null, { show_circle_with_x: true }, 'cabinet-id')],
            names: RL.names([1, 2, 3].map(i => ({ id: i, name: 'S' + i })), 2),
        };
    }""")
    assert out['parse'] == [[1, 2, 3], [10, 11, 12], [255, 255, 255], None]
    assert out['hex'] == '#FF0010' and out['near'] == [True, False]
    assert out['grid']['tl'] == '#0000FF' and out['grid']['bl'] == '#FF0000' and out['grid']['br'] == '#0000FF'
    assert sorted(out['grid']) == sorted(['tl', 't', 'tr', 'l', 'c', 'r', 'bl', 'b', 'br'])
    assert out['empty'] is None
    # the first at once, the two after it folded into one line with n = 2
    assert out['first'] == [['a', 1]]
    assert out['lines'] == [['a', 1], ['c', 2]]
    # the same signature writes nothing more; a new one writes its line
    assert [x[0] for x in out['sigLines']] == ['x', 'y'], out['sigLines']
    assert out['skip'] == ['gradient', 'printer palette', 'test pattern', None, None]
    assert out['names'] == ['S1 (#1)', 'S2 (#2)', '+1 more']


def _fit(pg):
    """The wall big on the page, so its cabinets can be read."""
    pg.evaluate("""() => { const r = window.canvasRenderer; r.zoom = 0.5; r.panX = 40; r.panY = 40; r.render(); }""")


def test_a_view_switch_logs_what_it_drew_and_a_wrong_colour(page):
    pg = page
    ids = reset(pg, ONE)
    wall = ids[0]
    open_tab(pg, 'pixel-map')
    _fit(pg)
    pg.wait_for_timeout(1200)
    start = log_len(pg)
    open_tab(pg, 'cabinet-id')
    _fit(pg)
    got = settled(pg, lambda: [d for d in logged(pg, 'render_view', start) if d['view'] == 'cabinet-id'],
                  lambda v: len(v) >= 1, 4000)
    assert len(got) == 1, got
    line = got[0]
    assert line['_area'] == 'render' and line['_lvl'] == 'info', line
    assert line['screens']['n'] == 1 and line['screens']['names'] == [f'Wall (#{wall})']
    assert line['n'] >= 1 and line['ms'] >= 0
    colours = line['colours']
    assert colours['screen'] == f'Wall (#{wall})' and colours.get('mismatch') == [], colours
    assert len(colours['drew']) == 2 and sorted(colours['drew']) == sorted(colours['expect']), colours
    assert line['_msg'].startswith('Cabinet ID drew 1 screen'), line['_msg']
    # zoom and pan alone write nothing
    pg.wait_for_timeout(1100)
    start = log_len(pg)
    pg.evaluate("() => { const r = window.canvasRenderer; r.panX += 30; r.render(); r.panX -= 30; r.render(); }")
    pg.wait_for_timeout(1300)
    assert logged(pg, 'render_view', start) == []
    # a picture that is not the screen's colours: a warning naming the cabinets
    start = log_len(pg)
    pg.evaluate(f"""() => {{
        const a = window.app, r = window.canvasRenderer;
        const l = a.project.layers.find(x => x.id === {wall});
        l.name = 'Wall B';
        r.render();
        const c = r.ctx;
        c.save(); c.setTransform(1, 0, 0, 1, 0, 0); c.fillStyle = '#ff0000';
        c.fillRect(0, 0, r.canvas.width, r.canvas.height); c.restore();
    }}""")
    bad = settled(pg, lambda: logged(pg, 'render_view', start), lambda v: len(v) >= 1, 4000)[0]
    assert bad['_lvl'] == 'warn' and len(bad['colours']['mismatch']) == 2, bad
    assert all(v == '#FF0000' for v in bad['colours']['drew'].values()), bad
    assert 'in the wrong colour' in bad['_msg'] and 'drew #FF0000' in bad['_msg'], bad['_msg']
    pg.evaluate(f"""() => {{ const l = window.app.project.layers.find(x => x.id === {wall});
        l.name = 'Wall'; window.canvasRenderer.render(); }}""")
    open_tab(pg, 'pixel-map')
    assert pg.errors == []


def test_an_error_overlay_logs_when_its_set_changes(page):
    pg = page
    ids = reset(pg, ONE)
    wall = ids[0]
    open_tab(pg, 'data-flow')
    pg.wait_for_timeout(1200)
    start = log_len(pg)
    pg.evaluate(f"""() => {{ const l = window.app.project.layers.find(x => x.id === {wall});
        l._capacityError = {{ unitType: 'panel', portCapacity: 650000, panelPixels: 655360 }};
        const draw = window.canvasRenderer.renderDataFlowArrows;
        window.canvasRenderer.renderDataFlowArrows = function (layer) {{
            draw.call(this, layer);
            if (layer.id === {wall}) layer._capacityError = {{ unitType: 'panel', portCapacity: 650000, panelPixels: 655360 }};
        }};
        window.canvasRenderer.render(); }}""")
    over = settled(pg, lambda: logged(pg, 'render_overlay', start), lambda v: len(v) >= 1, 3000)[0]
    assert over['_lvl'] == 'warn' and over['n'] == 1 and over['errors'][0]['key'] == f'capacity:{wall}', over
    assert 'one panel is bigger than a port' in over['_msg'] and '650,000' in over['_msg'], over['_msg']
    # the same set again writes nothing more
    pg.wait_for_timeout(1100)
    start = log_len(pg)
    pg.evaluate("() => window.canvasRenderer.render()")
    pg.wait_for_timeout(800)
    assert logged(pg, 'render_overlay', start) == []
    pg.evaluate("() => { delete window.canvasRenderer.renderDataFlowArrows; }")
    pg.evaluate(f"""() => {{ const l = window.app.project.layers.find(x => x.id === {wall});
        l._capacityError = null; window.canvasRenderer.render(); }}""")
    cleared = settled(pg, lambda: logged(pg, 'render_overlay', start), lambda v: len(v) >= 1, 3000)[0]
    assert cleared['_lvl'] == 'info' and cleared['n'] == 0 and 'cleared' in cleared['_msg'], cleared
    open_tab(pg, 'pixel-map')
    assert pg.errors == []


def test_3d_logs_its_stage_and_each_paint_and_a_wrong_corner(page):
    pg = page
    ids = reset(pg, ONE)
    wall = ids[0]
    start = log_len(pg)
    open_3d(pg, 1)
    sync = settled(pg, lambda: logged(pg, 'render_3d_sync', start), lambda v: len(v) >= 1)[0]
    assert sync['screens'] == 1 and sync['webgl'] is True and sync['maxTextureSize'] > 0, sync
    assert sync['_msg'].startswith('3D: 1 screen'), sync['_msg']
    paints = settled(pg, lambda: logged(pg, 'render_3d_paint', start), lambda v: len(v) >= 1, 5000)
    assert len(paints) == 1, paints
    p = paints[0]
    assert p['_lvl'] == 'info' and p['mismatch'] == [], p
    s = p['screens'][0]
    assert s['id'] == wall and s['mismatch'] == [] and s['size'][0] > 0 and s['labels'] is True, s
    assert sorted(s['sample']) == ['bl', 'br', 'c', 'tl', 'tr'] and s['mesh']['quads'] == 12, s
    assert p['_msg'].startswith(f'3D painted Wall (#{wall}) '), p['_msg']
    # an edit names the fields it changed
    pg.wait_for_timeout(1100)
    start = log_len(pg)
    pg.evaluate(f"""() => {{ const a = window.app; const l = a.project.layers.find(x => x.id === {wall});
        l.color1 = {{r: 20, g: 20, b: 200}}; l.color2 = {{r: 30, g: 30, b: 210}};
        a.updateLayers([l], true, 'Test Colours'); }}""")
    p = settled(pg, lambda: logged(pg, 'render_3d_paint', start), lambda v: len(v) >= 1, 5000)[0]
    assert p['_lvl'] == 'info' and {'color1', 'color2'} <= set(p['screens'][0]['reason']), p
    assert 'color1' in p['_msg'] and 'changed)' in p['_msg'], p['_msg']
    # a texture painted with a red corner: the line says which corner
    pg.wait_for_timeout(1100)
    start = log_len(pg)
    pg.evaluate(f"""() => {{
        const a = window.app;
        const paint = Object.getPrototypeOf(a)._s3dPaint;
        a._s3dPaint = function (e, layer, why) {{
            paint.call(this, e, layer, why);
            const c = e.canvas.getContext('2d');
            c.fillStyle = '#ff0000';
            c.fillRect(0, e.canvas.height / 2, e.canvas.width / 2, e.canvas.height / 2);
        }};
        const l = a.project.layers.find(x => x.id === {wall});
        l.color1 = {{r: 20, g: 20, b: 220}};
        a.updateLayers([l], true, 'Test Colours');
    }}""")
    try:
        bad = settled(pg, lambda: logged(pg, 'render_3d_paint', start), lambda v: len(v) >= 1, 5000)[0]
    finally:
        pg.evaluate("() => { delete window.app._s3dPaint; }")
    assert bad['_lvl'] == 'warn' and bad['mismatch'] == [{'id': wall, 'at': ['bl']}], bad
    assert bad['screens'][0]['drew'] == '#FF0000', bad
    assert bad['_msg'].startswith(f'3D paint of Wall (#{wall}) does not match its colours at bl: drew #FF0000'), bad['_msg']
    open_tab(pg, 'pixel-map')
    assert pg.errors == []


def test_an_output_frame_logs_its_size_and_colours_and_folds_the_next(page):
    pg = page
    reset(pg, ONE)
    out = pg.evaluate("""async () => {
        const a = window.app;
        const off = document.createElement('canvas');
        off.width = 64; off.height = 32;
        const offCtx = off.getContext('2d');
        offCtx.fillStyle = '#0000ff'; offCtx.fillRect(0, 0, 64, 32);
        const cv = a.project.canvases[0];
        const entry = { id: 77, canvasId: cv.id, view: 'pixel-map', native: false, offscreen: off, offCtx };
        const n0 = window.__clog.length;
        a._outputDisplayLogFrame(entry, { canvas: cv });
        await new Promise(r => setTimeout(r, 200));
        const first = window.__clog.slice(n0).filter(e => e.action === 'output_frame').map(e => e.details);
        a._outputDisplayLogFrame(entry, { canvas: cv });
        a._outputDisplayLogFrame(entry, { canvas: cv });
        await new Promise(r => setTimeout(r, 300));
        const held = window.__clog.slice(n0).filter(e => e.action === 'output_frame').length;
        await new Promise(r => setTimeout(r, 2000));
        const all = window.__clog.slice(n0).filter(e => e.action === 'output_frame').map(e => e.details);
        a._outputDisplayLogFrame(entry, { missing: 'canvas no longer in the project' });
        await new Promise(r => setTimeout(r, 2300));
        const gone = window.__clog.slice(n0).filter(e => e.action === 'output_frame').map(e => e.details);
        return { first, held, all, gone, name: cv.name };
    }""")
    assert len(out['first']) == 1, out
    f = out['first'][0]
    assert f['raster'] == [64, 32] and f['grid']['c'] == '#0000FF' and f['seq'] == 1 and f['n'] == 1, f
    assert f['_area'] == 'output' and f['_msg'].startswith(f"Output 77 showed Pixel Map of {out['name']} 64x32"), f
    assert out['held'] == 1, out
    assert len(out['all']) == 2 and out['all'][1]['n'] == 2 and out['all'][1]['seq'] == 3, out['all']
    last = out['gone'][-1]
    assert last['missing'] and last['_lvl'] == 'warn', out['gone']
    assert pg.errors == []


def test_an_export_logs_each_file_it_drew(page):
    pg = page
    reset(pg, ONE)
    out = pg.evaluate("""async () => {
        const a = window.app;
        const n0 = window.__clog.length;
        const cid = a.project.canvases[0].id;
        await a.performExport('Logged', 'obj', ['pixel-map'], [cid]);
        await new Promise(r => setTimeout(r, 300));
        return window.__clog.slice(n0).filter(e => e.action === 'export_rendered').map(e => e.details);
    }""")
    assert len(out) == 1, out
    line = out[0]
    assert line['format'] == 'obj' and line['_area'] == 'export' and line['more'] == 0, line
    f = line['files'][0]
    assert f['view'] == 'pixel-map' and f['size'][0] > 0 and f['bytes'] > 0, f
    assert sorted(f['grid']) == sorted(['tl', 't', 'tr', 'l', 'c', 'r', 'bl', 'b', 'br']), f
    # never the picture
    assert 'data:image' not in str(line)
    assert line['_msg'].startswith('OBJ export drew Pixel Map'), line['_msg']
    assert pg.errors == []
