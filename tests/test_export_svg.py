"""The SVG export (GitHub #12): a view's elements as separate, editable
layers - vector shapes and real text - for final touches in Illustrator
(every <g id> a named group) or as a smart object in Photoshop.

The export draws the view once through a RECORDING context (app-export-
svg.js): a Context2D stand-in over the export canvas that paints as usual
and writes each op down with the transform, clip chain, style and group in
force. The record is what the SVG is written from, so the recorder's
correctness IS the export's: `test_experts_only_*_replays_pixel_for_pixel`
draws every view of the Experts Only show from its record onto a fresh
canvas and compares it with the render the record was taken from.

Run locally (the Experts Only checks need the user's save, frozen as
tests/fixtures-local/experts-only-fixture.json - git-ignored client data,
so CI skips them; LRD_EXPERTS_JSON points at another copy):
    python3 -m pytest tests/test_export_svg.py -v --browser chromium
"""

import json
import os
import re
import sys
import xml.etree.ElementTree as ET

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from conftest import private_fixture, private_fixture_missing  # noqa: E402

pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS_DIR = os.path.join(ROOT, 'src', 'static', 'js')
INDEX_HTML = os.path.join(ROOT, 'src', 'templates', 'index.html')
SVG_NS = {'svg': 'http://www.w3.org/2000/svg'}

VIEWS = ['pixel-map', 'cabinet-id', 'show-look', 'data-flow', 'power']
VIEW_ELEMENT = {'cabinet-id': 'Cabinet IDs', 'data-flow': 'Data', 'power': 'Power'}

EXPERTS_JSON = private_fixture('experts-only-fixture.json', 'LRD_EXPERTS_JSON')
needs_experts = pytest.mark.skipif(
    bool(private_fixture_missing(EXPERTS_JSON)),
    reason=str(private_fixture_missing(EXPERTS_JSON)))


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it (the
    Experts Only checks PUT the whole show)."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    yield pg, errors
    context.close()


# The export through the real performExport, the two save paths stubbed to
# hand the files back. `transparent` sets the dialog's checkbox the way a
# user would.
EXPORT_JS = """async ([views, transparent]) => {
    const app = window.app;
    const files = [];
    const keep = { one: app.saveBlobWithPicker, many: app.saveMultipleFiles };
    app.saveBlobWithPicker = async (blobOrFn, filename, mime) => {
        const blob = typeof blobOrFn === 'function' ? await blobOrFn() : blobOrFn;
        files.push({ filename, mime, type: blob.type, text: await blob.text(), via: 'one' });
    };
    app.saveMultipleFiles = async (list) => {
        for (const f of list) files.push({ filename: f.filename, type: f.blob.type, text: await f.blob.text(), via: 'many' });
    };
    document.getElementById('export-transparent-bg').checked = !!transparent;
    try {
        const canvasIds = (app.project.canvases || []).map(c => c.id);
        await app.performExport('Show', 'svg', views, canvasIds.length ? canvasIds : [null]);
    } finally {
        app.saveBlobWithPicker = keep.one;
        app.saveMultipleFiles = keep.many;
    }
    return files;
}"""

# The recorder's proof: export every view through performExport, keep each
# view's record and the pixels of the canvas it was recorded from, replay
# the record onto a fresh canvas and count the pixels that differ.
REPLAY_JS = """async (views) => {
    const app = window.app;
    const keep = { one: app.saveBlobWithPicker, many: app.saveMultipleFiles, build: app.buildSvgFromRecording };
    app.saveBlobWithPicker = async () => {};
    app.saveMultipleFiles = async () => {};
    const recs = [];
    app.buildSvgFromRecording = function (rec, w, h, o) {
        const r = window.canvasRenderer;
        const ref = r.ctx.getImageData(0, 0, r.canvas.width, r.canvas.height);
        const svg = keep.build.call(this, rec, w, h, o);
        recs.push({ rec: { ops: rec.ops, images: rec.images, gradients: rec.gradients, clips: rec.clips },
                    unsupported: rec.unsupported.slice(), flattened: rec.flattenedPaths, ref, w, h });
        return svg;
    };
    document.getElementById('export-transparent-bg').checked = true;
    try {
        await app.performExport('Show', 'svg', views, (app.project.canvases || []).map(c => c.id));
    } finally {
        app.saveBlobWithPicker = keep.one;
        app.saveMultipleFiles = keep.many;
        app.buildSvgFromRecording = keep.build;
    }
    const out = [];
    for (let i = 0; i < recs.length; i++) {
        const { rec, ref, w, h } = recs[i];
        const c = document.createElement('canvas'); c.width = w; c.height = h;
        const ctx = c.getContext('2d', { alpha: true });
        await app.replaySvgRecording(rec, ctx);
        const got = ctx.getImageData(0, 0, w, h).data, a = ref.data;
        let bad = 0, worst = 0, first = null;
        for (let p = 0; p < a.length; p += 4) {
            const d = Math.max(Math.abs(a[p] - got[p]), Math.abs(a[p+1] - got[p+1]),
                               Math.abs(a[p+2] - got[p+2]), Math.abs(a[p+3] - got[p+3]));
            if (d > 8) { bad++; if (!first) first = [(p / 4) % w, Math.floor(p / 4 / w), d]; }
            if (d > worst) worst = d;
        }
        const kinds = {};
        rec.ops.forEach(op => { const k = op.op + (op.kind ? ':' + op.kind : ''); kinds[k] = (kinds[k] || 0) + 1; });
        out.push({ view: views[i], w, h, pixels: a.length / 4, bad, worst, first, ops: rec.ops.length, kinds,
                   unsupported: recs[i].unsupported, flattened: recs[i].flattened });
    }
    return out;
}"""


def _export(pg, views, transparent=True):
    return pg.evaluate(EXPORT_JS, [views, transparent])


def _groups(root):
    """{'SR - MAIN': ['Panels', 'Borders', ...], 'Text': ['Text 1'], ...}:
    the top-level <g data-name> groups and the names of the groups inside."""
    out = {}
    for g in root.findall('svg:g', SVG_NS):
        out[g.get('data-name')] = [c.get('data-name') for c in g.findall('svg:g', SVG_NS)]
    return out


# ── the dialog ──────────────────────────────────────────────────────────

def test_the_format_option_is_served(client):
    html = client.get('/').get_data(as_text=True)
    assert ('<option value="svg">SVG (Vector - editable in Illustrator, '
            'smart object in Photoshop)</option>') in html
    assert 'Supported by PNG, SVG and PSD.' in html


def test_the_dialog_offers_svg_hides_the_scale_row_and_previews_svg_names(page):
    pg, errors = page
    pg.locator('#btn-export').click()
    pg.wait_for_timeout(300)
    assert pg.locator('#export-modal').is_visible()
    pg.select_option('#export-format', 'psd')
    pg.wait_for_timeout(100)
    assert pg.locator('#export-scale-row').is_visible(), 'PSD keeps its scale row'
    pg.select_option('#export-format', 'svg')
    pg.wait_for_timeout(200)
    state = pg.evaluate("""() => ({
        scaleRow: getComputedStyle(document.getElementById('export-scale-row')).display,
        options: getComputedStyle(document.getElementById('export-options-section')).display,
        views: getComputedStyle(document.getElementById('export-views-section')).display,
        transparent: !!document.getElementById('export-transparent-bg'),
        preview: document.getElementById('export-preview').textContent,
    })""")
    assert state['scaleRow'] == 'none', 'a vector needs no resolution scale'
    assert state['options'] != 'none' and state['transparent'], 'the transparent background is SVG\'s too'
    assert state['views'] != 'none', 'SVG is one file per view, the views stay on offer'
    assert '.svg' in state['preview'], state['preview']
    pg.select_option('#export-format', 'png')
    pg.locator('#export-cancel').click()
    pg.wait_for_timeout(100)
    assert errors == []


# ── the files ───────────────────────────────────────────────────────────

def test_one_view_saves_one_svg_through_the_save_dialog(page):
    pg, errors = page
    files = _export(pg, ['pixel-map'], transparent=True)
    assert [f['filename'] for f in files] == ['Show_Pixel Map.svg'], files
    assert files[0]['via'] == 'one' and files[0]['mime'] == 'image/svg+xml' and files[0]['type'] == 'image/svg+xml'
    assert errors == []


def test_several_views_save_one_svg_per_view_through_the_folder_path(page):
    pg, errors = page
    files = _export(pg, VIEWS, transparent=True)
    assert [f['filename'] for f in files] == [
        'Show_Pixel Map.svg', 'Show_Cabinet Map.svg', 'Show_Show Look.svg',
        'Show_Data Map.svg', 'Show_Power Map.svg'], files
    assert all(f['via'] == 'many' and f['type'] == 'image/svg+xml' for f in files)
    for f in files:
        ET.fromstring(f['text'])   # well-formed, each
    assert errors == []


def test_the_svg_is_the_raster_with_the_screen_as_shapes_and_its_name_as_text(page):
    pg, errors = page
    raster = pg.evaluate("() => [window.canvasRenderer.rasterWidth, window.canvasRenderer.rasterHeight]")
    screen = pg.evaluate("() => { const l = window.app.project.layers.find(l => (l.type || 'screen') === 'screen'); "
                         "return { name: l.name, panels: l.panels.filter(p => !p.hidden).length, borders: !!l.show_panel_borders }; }")
    text = _export(pg, ['pixel-map'], transparent=True)[0]['text']
    assert text.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg"')
    root = ET.fromstring(text)
    assert root.get('width') == str(raster[0]) and root.get('height') == str(raster[1])
    assert root.get('viewBox') == f'0 0 {raster[0]} {raster[1]}'
    groups = _groups(root)
    assert 'Background' not in groups, 'transparent: no backdrop'
    assert screen['name'] in groups, groups
    inside = groups[screen['name']]
    assert inside[:2] == ['Panels', 'Borders'] and 'Screen name' in inside, inside
    wall = root.find(f".//svg:g[@data-name='{screen['name']}']", SVG_NS)
    panels = wall.find("svg:g[@data-name='Panels']", SVG_NS)
    rects = panels.findall('svg:rect', SVG_NS)
    assert len(rects) == screen['panels'], (len(rects), screen['panels'])
    assert all(r.get('fill', '').startswith('#') for r in rects)
    borders = wall.find("svg:g[@data-name='Borders']", SVG_NS)
    strokes = borders.findall('svg:rect', SVG_NS)
    assert len(strokes) == screen['panels'] and all(r.get('fill') == 'none' and r.get('stroke') for r in strokes)
    names = [t.text for t in wall.find("svg:g[@data-name='Screen name']", SVG_NS).findall('.//svg:text', SVG_NS)]
    assert screen['name'] in names, names
    name_el = [t for t in wall.iter('{http://www.w3.org/2000/svg}text') if t.text == screen['name']][0]
    assert name_el.get('font-family') and name_el.get('font-size'), name_el.attrib
    assert 'clip-path' not in text.split('<g data-name')[0] or root.find('.//svg:clipPath', SVG_NS) is not None
    assert errors == []


def test_the_background_rect_follows_the_transparent_checkbox(page):
    pg, errors = page
    raster = pg.evaluate("() => [window.canvasRenderer.rasterWidth, window.canvasRenderer.rasterHeight]")
    root = ET.fromstring(_export(pg, ['pixel-map'], transparent=False)[0]['text'])
    bg = root.find("svg:g[@data-name='Background']", SVG_NS)
    assert bg is not None, 'a black backdrop when the export is not transparent'
    rect = bg.find('svg:rect', SVG_NS)
    assert (rect.get('x'), rect.get('y'), rect.get('width'), rect.get('height')) == ('0', '0', str(raster[0]), str(raster[1]))
    assert rect.get('fill') == '#000000'
    assert list(root).index(bg) == [i for i, el in enumerate(root) if el.tag.endswith('}g')][0], 'the backdrop is the first group'
    assert errors == []


# ── the recorder on the real show ───────────────────────────────────────

@pytest.fixture(scope="module")
def experts(page):
    """The user's own save loaded into the page the way test_binder does."""
    if private_fixture_missing(EXPERTS_JSON):
        pytest.skip(private_fixture_missing(EXPERTS_JSON))
    pg, errors = page
    with open(EXPERTS_JSON) as fh:
        project = json.load(fh)
    layers = pg.evaluate("""async (project) => {
        const app = window.app;
        const j = (method, url, body) => fetch(url, {method,
            headers: {'Content-Type': 'application/json'},
            body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
        await j('PUT', '/api/project', project);
        app.project = await j('GET', '/api/project');
        app.dedupeProjectLayers('svg_export');
        app.selectLayer(app.project.layers.find(l => (l.type || 'screen') === 'screen'));
        await app.refreshProcessors();
        await app.refreshPortAssignment();
        app.renderLayers();
        return app.project.layers.map(l => ({ name: l.name, type: l.type || 'screen', visible: !!l.visible,
            panels: (l.panels || []).filter(p => !p.hidden).length }));
    }""", project)
    pg.wait_for_timeout(800)
    return pg, errors, layers


@needs_experts
def test_experts_only_every_view_replays_pixel_for_pixel(experts):
    """Every view of the show, drawn back from its record, is the render it
    was recorded from - the tolerance is a handful of anti-aliased pixels
    - and nothing the views drew is beyond the recorder."""
    pg, errors, layers = experts
    results = pg.evaluate(REPLAY_JS, VIEWS)
    assert [r['view'] for r in results] == VIEWS
    for r in results:
        assert r['unsupported'] == [], r
        assert r['flattened'] == 0, r
        assert r['ops'] > 1000, r
        # 0.01 % of the pixels may differ by more than 8 in a channel
        assert r['bad'] <= r['pixels'] * 0.0001, (r['view'], r['bad'], r['first'], r['worst'])
        assert r['kinds'].get('text:fill', 0) > 0, r
    by_view = {r['view']: r for r in results}
    visible_panels = sum(l['panels'] for l in layers if l['type'] == 'screen' and l['visible'])
    assert by_view['cabinet-id']['kinds']['text:fill'] >= visible_panels
    assert by_view['power']['kinds']['text:fill'] > by_view['data-flow']['kinds']['text:fill'] > by_view['pixel-map']['kinds']['text:fill']
    assert errors == []


@needs_experts
def test_experts_only_svgs_carry_a_group_per_screen_and_per_element(experts):
    pg, errors, layers = experts
    files = _export(pg, VIEWS, transparent=True)
    assert len(files) == len(VIEWS)
    screens = [l for l in layers if l['type'] == 'screen' and l['visible']]
    texts = [l for l in layers if l['type'] == 'text' and l['visible']]
    for view, f in zip(VIEWS, files):
        root = ET.fromstring(f['text'])
        assert root.get('viewBox') == '0 0 4096 2160', (view, root.attrib)
        groups = _groups(root)
        for s in screens:
            inside = groups.get(s['name'])
            assert inside, (view, s['name'], list(groups))
            assert inside[:2] == ['Panels', 'Borders'] and inside[-1] == 'Screen name', (view, inside)
            element = VIEW_ELEMENT.get(view)
            if element:
                assert element in inside, (view, inside)
            wall = root.find(f".//svg:g[@data-name='{s['name']}']", SVG_NS)
            assert len(wall.find("svg:g[@data-name='Panels']", SVG_NS)) == s['panels'], (view, s['name'])
            name_texts = [t.text for t in wall.find("svg:g[@data-name='Screen name']", SVG_NS).iter('{http://www.w3.org/2000/svg}text')]
            assert s['name'] in name_texts, (view, name_texts)
            if view == 'cabinet-id':
                ids = wall.find("svg:g[@data-name='Cabinet IDs']", SVG_NS).findall('svg:text', SVG_NS)
                assert len(ids) == s['panels'], (s['name'], len(ids), s['panels'])
        if texts:
            assert groups.get('Text') == [t['name'] for t in texts], (view, groups.get('Text'))
        # the ids Illustrator names the groups by: unique, XML names, the
        # words in data-name
        ids = [g.get('id') for g in root.iter('{http://www.w3.org/2000/svg}g') if g.get('id')]
        assert len(ids) == len(set(ids)), view
        assert all(re.match(r'^[A-Za-z_][A-Za-z0-9_.\-]*$', i) for i in ids), ids
        assert 'SR_x20_-_x20_MAIN' in ids or 'SL_x20_-_x20_MAIN' in ids, ids
        # every op of the Power and Data views is a shape or text, no bitmap
        if view in ('data-flow', 'power'):
            assert root.find('.//svg:image', SVG_NS) is None
            labels = [t.text for t in root.iter('{http://www.w3.org/2000/svg}text')]
            assert len(labels) >= 60 and all(labels), (view, len(labels))
    assert errors == []


# ── the hooks in the renderer ───────────────────────────────────────────

def test_every_stage_of_the_render_names_its_group():
    """The recorder files ops under the group the renderer last named; a
    stage whose hook is dropped files under its neighbour's name."""
    def read(name):
        with open(os.path.join(JS_DIR, name), encoding='utf-8') as fh:
            return fh.read()
    canvas = read('canvas.js')
    assert re.search(r'^\s{4}_svgGroup\(name, layer\) \{', canvas, re.M)
    for group in ('Background', 'Images', 'Text', 'Panels', 'Borders', 'Test pattern',
                  'Cabinet IDs', 'Data', 'Power', 'Screen name', 'Back view'):
        assert f"this._svgGroup('{group}'" in canvas, group
    for name in ('canvas-data.js', 'canvas-power.js'):
        assert read(name).count("this._svgGroup('Borders', layer)") == 2, name
    with open(os.path.join(JS_DIR, 'main.js'), encoding='utf-8') as fh:
        assert "import './app-export-svg.js';" in fh.read()
    for method in ('createSvgRecorder', 'buildSvgFromRecording', 'replaySvgRecording', 'downloadAsSvg'):
        assert re.search(rf'^\s{{4}}(async\s+)?{method}\(', read('app-export-svg.js'), re.M), method
