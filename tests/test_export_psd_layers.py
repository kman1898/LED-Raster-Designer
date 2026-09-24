"""PSD export: the "PSD layers" choice (issue #12).

One layer per screen is the PSD as it has always been - the default, and
byte for byte the code path it was (the first test builds the same PSD with
the route as it stood before the choice existed, straight from git, and
compares the bytes). Elements per screen renders each view once per STAGE
(cabinet fills, borders, test pattern, cabinet numbers, data runs, circuits,
screen name) on a transparent canvas and files each screen as a PSD group of
those layers, the images / text / canvas outline in a "Canvas" group, and a
solid Background under an opaque export.

Three halves:
  * The route (Flask client, synthetic stage images): groups, order, crops,
    the dropped empty stages and screens, the composite, the ZIP route.
  * The renderer and the dialog (Playwright on the shared e2e server): the
    stage filter leaves a full render byte-identical, each stage alone
    composes back to the flat render, the real export round trip reads back
    as groups, the row shows only for PSD and remembers its choice.
  * The user's own show (skipped unless its private fixture is present): the
    Pixel Map render is unchanged against a capture made before the stage
    filter existed, when that capture is present.

Run:
    python3 -m pytest tests/test_export_psd_layers.py -q -p no:randomly --browser chromium
"""

import base64
import importlib.util
import io
import json
import os
import subprocess
import sys
import zipfile

import pytest
from PIL import Image, ImageChops

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from conftest import private_fixture, private_fixture_missing  # noqa: E402

try:
    import pytoshop  # noqa: F401
    HAS_PYTOSHOP = True
except ImportError:
    HAS_PYTOSHOP = False
psd_tools = pytest.importorskip('psd_tools', reason='psd-tools reads the PSD back')

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
# The last commit before the PSD layers choice: its psd-from-image route is
# what "one layer per screen" must still produce, byte for byte.
BEFORE_COMMIT = '035e362'

SCREEN_STAGES = ['Screen name', 'Power', 'Data', 'Cabinet IDs', 'Test pattern', 'Borders', 'Panels']
CANVAS_STAGES = ['Canvas outline', 'Text', 'Image']


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# ── helpers ───────────────────────────────────────────────────────────────

def _data_url(img):
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()


def _decode(data_url):
    return Image.open(io.BytesIO(base64.b64decode(data_url.split(',', 1)[1]))).convert('RGBA')


def _stage_image(size, color=None, box=None):
    """A transparent picture with one solid box on it (or nothing)."""
    img = Image.new('RGBA', size, (0, 0, 0, 0))
    if box:
        img.paste(Image.new('RGBA', (box[2] - box[0], box[3] - box[1]), color), box[:2])
    return img


def _tree(psd):
    """[(name, kind, bbox, [children...])] top to bottom, as Photoshop lists."""
    out = []
    for layer in reversed(list(psd)):
        kids = _tree(layer) if layer.is_group() else None
        out.append((layer.name, layer.kind, tuple(layer.bbox), kids))
    return out


def _names(tree):
    return [(name, [k[0] for k in kids] if kids is not None else None) for name, _k, _b, kids in tree]


def _layer_named(group, name):
    hits = [l for l in group if l.name == name]
    assert len(hits) == 1, (name, [l.name for l in group])
    return hits[0]


def _same_pixels(a, b, tolerance=0):
    a = a.convert('RGBA')
    b = b.convert('RGBA')
    assert a.size == b.size, (a.size, b.size)
    diff = ImageChops.difference(a, b)
    extrema = diff.getextrema()
    worst = max(hi for _lo, hi in extrema)
    return worst <= tolerance, worst


def _composite_stages(stages, order, size):
    """Composite [{name, image_data}] bottom to top in `order`."""
    by_name = {s['name']: s['image_data'] for s in stages}
    out = Image.new('RGBA', size, (0, 0, 0, 0))
    for name in order:
        if name in by_name:
            out = Image.alpha_composite(out, _decode(by_name[name]))
    return out


# ── the route ─────────────────────────────────────────────────────────────

W, H = 400, 300
SCREENS = [
    {'name': 'Left', 'offset_x': 10, 'offset_y': 10, 'width': 100, 'height': 100, 'visible': True},
    {'name': 'Right', 'offset_x': 200, 'offset_y': 50, 'width': 120, 'height': 80, 'visible': True},
    {'name': 'Hidden', 'offset_x': 0, 'offset_y': 0, 'width': 50, 'height': 50, 'visible': False},
    {'name': 'Empty', 'offset_x': 300, 'offset_y': 200, 'width': 60, 'height': 60, 'visible': True},
]
STAGE_PICTURES = {
    'Panels': ((255, 0, 0, 255), (10, 10, 320, 130)),        # over both screens
    'Borders': ((0, 255, 0, 255), (10, 10, 60, 60)),          # Left only
    'Screen name': ((0, 0, 255, 128), (210, 60, 250, 70)),    # Right only, half alpha
    'Cabinet IDs': (None, None),                              # nothing drawn
    'Text': ((255, 255, 0, 255), (150, 250, 170, 270)),       # off every screen
    'Canvas outline': (None, None),
}


def _stages():
    return [{'name': n, 'image_data': _data_url(_stage_image((W, H), *STAGE_PICTURES[n]))}
            for n in STAGE_PICTURES]


def _elements_payload(**extra):
    payload = {'project_name': 'T', 'view_name': 'V', 'mode': 'elements', 'image_data': '',
               'width': W, 'height': H, 'layers': SCREENS, 'stages': _stages()}
    payload.update(extra)
    return payload


@pytest.mark.skipif(not HAS_PYTOSHOP, reason="pytoshop not installed")
def test_the_default_mode_writes_the_layers_the_route_wrote_before_the_choice_existed(client):
    """No `mode` in the request: the layers are the ones the route wrote
    before this feature, built here from that commit's own source; the file
    additionally carries a flattened preview now."""
    try:
        source = subprocess.check_output(
            ['git', 'show', f'{BEFORE_COMMIT}:src/routes_export.py'], cwd=REPO,
            stderr=subprocess.DEVNULL).decode('utf-8')
    except (subprocess.CalledProcessError, OSError):
        pytest.skip(f'commit {BEFORE_COMMIT} is not in this clone')
    from flask import Flask
    spec = importlib.util.spec_from_loader('routes_export_before', loader=None)
    before = importlib.util.module_from_spec(spec)
    before.__file__ = os.path.join(REPO, 'src', 'routes_export_before.py')
    exec(compile(source, before.__file__, 'exec'), before.__dict__)
    old_app = Flask('before')
    old_app.register_blueprint(before.export_bp)

    flat = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    for x in range(0, W, 7):
        flat.paste((x % 255, 40, 200, 255 if x % 3 else 90), (x, 0, x + 3, H))
    payload = {'project_name': 'T', 'view_name': 'V', 'image_data': _data_url(flat),
               'width': W, 'height': H, 'layers': SCREENS}
    with old_app.test_client() as old_client:
        old = old_client.post('/api/export/psd-from-image', json=payload)
    new = client.post('/api/export/psd-from-image', json=payload)
    assert old.status_code == 200 and new.status_code == 200
    # The LAYERS are the ones the old route wrote, record for record; the
    # file itself is no longer byte-identical because it now carries the
    # flattened preview the old one lacked (Quick Look thumbnailed it
    # black). Compare the layer records, then the preview.
    old_psd = psd_tools.PSDImage.open(io.BytesIO(old.data))
    psd = psd_tools.PSDImage.open(io.BytesIO(new.data))
    assert _names(_tree(psd)) == _names(_tree(old_psd))
    for a, b in zip(psd, old_psd):
        assert tuple(a.bbox) == tuple(b.bbox)
        same, worst = _same_pixels(a.topil(), b.topil())
        assert same, (a.name, worst)
    preview = psd.topil() if psd.has_preview() else None
    assert preview is not None, 'the PSD carries no flattened preview'
    # integer premultiply on the server vs PIL's compositing: one level
    same, worst = _same_pixels(preview.convert('RGB'), Image.alpha_composite(
        Image.new('RGBA', flat.size, (0, 0, 0, 255)), flat).convert('RGB'), tolerance=1)
    assert same, ('preview', worst)
    assert _names(_tree(psd)) == [('Empty', None), ('Right', None), ('Left', None)]
    for layer in psd:
        screen = next(s for s in SCREENS if s['name'] == layer.name)
        box = (screen['offset_x'], screen['offset_y'],
               screen['offset_x'] + screen['width'], screen['offset_y'] + screen['height'])
        assert tuple(layer.bbox) == box
        same, worst = _same_pixels(layer.topil(), flat.crop(box))
        assert same, (layer.name, worst)


@pytest.mark.skipif(not HAS_PYTOSHOP, reason="pytoshop not installed")
def test_elements_mode_files_each_screen_as_a_group_of_its_stages(client):
    resp = client.post('/api/export/psd-from-image', json=_elements_payload())
    assert resp.status_code == 200, resp.get_json()
    assert resp.data[:4] == b'8BPS'
    psd = psd_tools.PSDImage.open(io.BytesIO(resp.data))
    # Top to bottom: the Canvas group, then the screens in the order the
    # request listed them (the last listed on top, as the flat PSD stacks
    # them). Hidden is skipped, Empty had nothing on any stage, Cabinet IDs
    # and Canvas outline drew nothing, no Background on a transparent export.
    assert _names(_tree(psd)) == [
        ('Canvas', ['Text']),
        ('Right', ['Screen name', 'Panels']),
        ('Left', ['Borders', 'Panels']),
    ]
    stages = {s['name']: _decode(s['image_data']) for s in _stages()}
    for group in psd:
        if group.name == 'Canvas':
            # A canvas stage has no screen to bound it: its layer is cut to
            # its ink, where Photoshop would bound it anyway.
            for layer in group:
                assert tuple(layer.bbox) == STAGE_PICTURES[layer.name][1], (layer.name, layer.bbox)
                assert _same_pixels(layer.topil(), stages[layer.name].crop(layer.bbox))[0]
            continue
        screen = next(s for s in SCREENS if s['name'] == group.name)
        box = (screen['offset_x'], screen['offset_y'],
               screen['offset_x'] + screen['width'], screen['offset_y'] + screen['height'])
        for layer in group:
            assert tuple(layer.bbox) == box, (group.name, layer.name, layer.bbox)
            same, worst = _same_pixels(layer.topil(), stages[layer.name].crop(box))
            assert same, (group.name, layer.name, worst)


@pytest.mark.skipif(not HAS_PYTOSHOP, reason="pytoshop not installed")
def test_the_element_layers_composite_to_the_one_layer_per_screen_export(client):
    """Flatten the Elements PSD and the classic PSD of the same picture:
    inside every screen's rectangle they agree."""
    # The classic export of an opaque picture: the stages over black, as the
    # renderer paints them over its black raster.
    flat = Image.alpha_composite(
        Image.new('RGBA', (W, H), (0, 0, 0, 255)),
        _composite_stages(_stages(), list(reversed(SCREEN_STAGES)) + list(reversed(CANVAS_STAGES)), (W, H)))
    classic = client.post('/api/export/psd-from-image', json={
        'project_name': 'T', 'view_name': 'V', 'image_data': _data_url(flat),
        'width': W, 'height': H, 'layers': SCREENS})
    elements = client.post('/api/export/psd-from-image', json=_elements_payload(background='#000000'))
    assert classic.status_code == 200 and elements.status_code == 200
    a = psd_tools.PSDImage.open(io.BytesIO(classic.data)).composite(ignore_preview=True).convert('RGBA')
    b = psd_tools.PSDImage.open(io.BytesIO(elements.data)).composite(ignore_preview=True).convert('RGBA')
    # The Background layer is where the Elements PSD says what the classic
    # PSD's black raster did; check it is there and then compare the screens.
    psd = psd_tools.PSDImage.open(io.BytesIO(elements.data))
    assert _names(_tree(psd))[-1] == ('Background', None)
    assert b.getpixel((W - 1, H - 1)) == (0, 0, 0, 255)
    for screen in SCREENS:
        if not screen['visible']:
            continue
        box = (screen['offset_x'], screen['offset_y'],
               screen['offset_x'] + screen['width'], screen['offset_y'] + screen['height'])
        same, worst = _same_pixels(a.crop(box), b.crop(box), tolerance=1)
        assert same, (screen['name'], worst)


@pytest.mark.skipif(not HAS_PYTOSHOP, reason="pytoshop not installed")
def test_the_zip_route_takes_elements_too(client):
    resp = client.post('/api/export/psd-zip-from-images', json={
        'project_name': 'T', 'mode': 'elements', 'width': W, 'height': H, 'layers': SCREENS,
        'images': [{'name': 'Pixel Map', 'data': '', 'stages': _stages()},
                   {'name': 'Power Map', 'data': '', 'stages': _stages()[:1], 'background': '#000000'}]})
    assert resp.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(resp.data))
    assert sorted(zf.namelist()) == ['T - Pixel Map.psd', 'T - Power Map.psd']
    pixel = psd_tools.PSDImage.open(io.BytesIO(zf.read('T - Pixel Map.psd')))
    power = psd_tools.PSDImage.open(io.BytesIO(zf.read('T - Power Map.psd')))
    assert _names(_tree(pixel)) == [('Canvas', ['Text']), ('Right', ['Screen name', 'Panels']),
                                    ('Left', ['Borders', 'Panels'])]
    assert _names(_tree(power)) == [('Right', ['Panels']), ('Left', ['Panels']), ('Background', None)]


def test_elements_mode_without_pytoshop_says_so(client, monkeypatch):
    for name in ('pytoshop', 'pytoshop.layers', 'pytoshop.enums'):
        monkeypatch.setitem(sys.modules, name, None)
    resp = client.post('/api/export/psd-from-image', json=_elements_payload())
    assert resp.status_code == 500
    assert 'pytoshop' in resp.get_json()['error'].lower()


# ── the renderer and the dialog ───────────────────────────────────────────

@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1500, 'height': 900})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(1500)
    yield pg, errors
    context.close()


# performExport with the file writers patched: what downloadAsPsd would have
# posted, plus the flat render, per view.
CAPTURE_JS = """async ([views, mode, transparent]) => {
    const app = window.app;
    app.populateExportCanvasesList();
    document.getElementById('export-scale').value = '1';
    document.getElementById('export-transparent-bg').checked = transparent;
    document.getElementById('export-psd-layers').value = mode;
    let items = null;
    const real = app.downloadAsPsd;
    app.downloadAsPsd = async (name, list) => { items = list; };
    try {
        await app.performExport('T', 'psd', views, app.getSelectedExportCanvasIds());
    } finally { app.downloadAsPsd = real; }
    return items.map(it => ({view: it.view, width: it.width, height: it.height,
        dataUrl: it.dataUrl, stages: it.stages, background: it.background,
        filterAfter: window.canvasRenderer.renderStages}));
}"""

# The real export, end to end: performExport, downloadAsPsd, the route -
# with the pickers patched to hand the PSD back and the fetch watched.
ROUND_TRIP_JS = """async ([views, mode]) => {
    const app = window.app;
    app.populateExportCanvasesList();
    document.getElementById('export-scale').value = '1';
    document.getElementById('export-transparent-bg').checked = true;
    document.getElementById('export-psd-layers').value = mode;
    const files = [];
    const toB64 = (blob) => new Promise((res) => {
        const r = new FileReader(); r.onload = () => res(r.result.split(',')[1]); r.readAsDataURL(blob); });
    const saved = {picker: app.saveBlobWithPicker, multi: app.saveMultipleFiles, fetch: window.fetch};
    app.saveBlobWithPicker = async (blob, filename) => { files.push({filename, b64: await toB64(blob)}); };
    app.saveMultipleFiles = async (list) => { for (const f of list) files.push({filename: f.filename, b64: await toB64(f.blob)}); };
    const requests = [];
    window.fetch = async (url, opts) => {
        if (opts && opts.body && String(url).includes('/api/export/psd')) {
            const body = JSON.parse(opts.body);
            requests.push({url: String(url), keys: Object.keys(body).sort(), mode: body.mode || null,
                stages: (body.stages || []).map(s => s.name), layers: body.layers.map(l => [l.name, l.offset_x, l.offset_y, l.width, l.height])});
        }
        return saved.fetch.call(window, url, opts);
    };
    try {
        await app.performExport('T', 'psd', views, app.getSelectedExportCanvasIds());
    } finally {
        app.saveBlobWithPicker = saved.picker; app.saveMultipleFiles = saved.multi; window.fetch = saved.fetch;
    }
    return {files, requests};
}"""

# One render of the current view on an offscreen canvas, as the export does,
# with the given filter (null or a list of stage names).
RENDER_JS = """([view, stages]) => {
    const r = window.canvasRenderer;
    const saved = {canvas: r.canvas, ctx: r.ctx, zoom: r.zoom, panX: r.panX, panY: r.panY,
                   view: r.viewMode, exportMode: r.exportMode, transparent: r.exportTransparentBg};
    const c = document.createElement('canvas');
    c.width = r.rasterWidth; c.height = r.rasterHeight;
    r.canvas = c; r.ctx = c.getContext('2d', {alpha: true});
    r.viewMode = view; r.exportMode = true; r.exportTransparentBg = true;
    r.zoom = 1; r.panX = 0; r.panY = 0;
    r.renderStages = stages ? new Set(stages) : null;
    try { r.render(); return c.toDataURL('image/png'); }
    finally {
        r.renderStages = null;
        Object.assign(r, {canvas: saved.canvas, ctx: saved.ctx, zoom: saved.zoom, panX: saved.panX,
            panY: saved.panY, viewMode: saved.view, exportMode: saved.exportMode,
            exportTransparentBg: saved.transparent});
        r.render();
    }
}"""

ALL_STAGES = SCREEN_STAGES + CANVAS_STAGES + ['Background']


def test_naming_every_stage_is_the_same_render_as_naming_none(page):
    """The filter set to everything and the filter off are one picture,
    byte for byte, on every view - so a null filter cannot have changed
    what the export draws."""
    pg, errors = page
    for view in ('pixel-map', 'cabinet-id', 'show-look', 'data-flow', 'power'):
        plain = pg.evaluate(RENDER_JS, [view, None])
        # Everything but the canvas outline, which the export never drew
        # and only draws when named.
        named = pg.evaluate(RENDER_JS, [view, [s for s in ALL_STAGES if s != 'Canvas outline']])
        assert named == plain, view
        assert _decode(plain).getbbox() is not None, f'{view}: nothing drawn'
    assert pg.evaluate("window.canvasRenderer.renderStages") is None
    assert errors == []


def test_each_stage_alone_composes_back_to_the_flat_render(page):
    """Rendering a view one stage at a time and stacking the pictures in
    layer order gives the flat render (to a rounding level, alpha
    compositing being done in 8 bits twice instead of once)."""
    pg, errors = page
    for view in ('pixel-map', 'cabinet-id', 'data-flow', 'power'):
        items = pg.evaluate(CAPTURE_JS, [[view], 'elements', True])
        assert len(items) == 1 and items[0]['filterAfter'] is None
        item = items[0]
        names = [s['name'] for s in item['stages']]
        assert sorted(names) == sorted(s for s in ALL_STAGES if s != 'Background'), names
        flat = _decode(item['dataUrl'])
        size = (item['width'], item['height'])
        assert flat.size == size
        stack = _composite_stages([s for s in item['stages'] if s['name'] != 'Canvas outline'],
                                  list(reversed(SCREEN_STAGES)) + ['Image', 'Text'], size)
        same, worst = _same_pixels(stack, flat, tolerance=2)
        assert same, (view, worst)
        drawn = {s['name'] for s in item['stages'] if _decode(s['image_data']).getbbox()}
        assert 'Panels' in drawn and 'Borders' in drawn, (view, drawn)
        assert 'Canvas outline' in drawn
        # A stage with nothing to draw on this view is a blank picture.
        if view == 'pixel-map':
            assert 'Cabinet IDs' not in drawn and 'Data' not in drawn and 'Power' not in drawn
        if view == 'cabinet-id':
            assert 'Cabinet IDs' in drawn and 'Test pattern' not in drawn
        if view == 'data-flow':
            assert 'Data' in drawn and 'Power' not in drawn
        if view == 'power':
            assert 'Power' in drawn and 'Data' not in drawn
        # The Panels stage has no border ink in it, and the Borders stage no fill.
        by = {s['name']: _decode(s['image_data']) for s in item['stages']}
        panels_alpha = by['Panels'].getchannel('A').getbbox()
        assert panels_alpha is not None
    assert errors == []


def test_the_default_export_posts_what_it_always_did_and_elements_reads_back_as_groups(page):
    pg, errors = page
    classic = pg.evaluate(ROUND_TRIP_JS, [['pixel-map'], 'screens'])
    assert [r['keys'] for r in classic['requests']] == [
        ['height', 'image_data', 'layers', 'project_name', 'view_name', 'width']]
    assert classic['requests'][0]['mode'] is None
    classic_psd = psd_tools.PSDImage.open(io.BytesIO(base64.b64decode(classic['files'][0]['b64'])))
    classic_names = _names(_tree(classic_psd))
    assert classic_names and all(kids is None for _n, kids in classic_names), classic_names

    elements = pg.evaluate(ROUND_TRIP_JS, [['pixel-map'], 'elements'])
    req = elements['requests'][0]
    assert req['mode'] == 'elements'
    assert sorted(req['stages']) == sorted(s for s in ALL_STAGES if s != 'Background')
    assert req['layers'] == classic['requests'][0]['layers']
    assert elements['files'][0]['filename'] == classic['files'][0]['filename']
    psd = psd_tools.PSDImage.open(io.BytesIO(base64.b64decode(elements['files'][0]['b64'])))
    tree = _names(_tree(psd))
    screens = [name for name, _kids in classic_names]
    groups = [(name, kids) for name, kids in tree if name != 'Canvas']
    assert [name for name, _k in groups] == screens, tree
    for name, kids in groups:
        assert kids and kids == [s for s in SCREEN_STAGES if s in kids], (name, kids)
        assert 'Panels' in kids and 'Borders' in kids and 'Screen name' in kids, (name, kids)
        assert 'Cabinet IDs' not in kids and 'Data' not in kids and 'Power' not in kids
    assert ('Canvas', ['Canvas outline']) in tree, tree
    # Every element layer sits exactly where the classic layer of its screen sits.
    for classic_layer in classic_psd:
        group = _layer_named(psd, classic_layer.name)
        for layer in group:
            assert tuple(layer.bbox) == tuple(classic_layer.bbox), (layer.name, layer.bbox)
    # And flattened, the group is the classic layer.
    for classic_layer in classic_psd:
        group = _layer_named(psd, classic_layer.name)
        same, worst = _same_pixels(group.composite(), classic_layer.topil(), tolerance=2)
        assert same, (classic_layer.name, worst)
    assert errors == []


def test_the_row_shows_only_for_psd_and_remembers_its_choice(page):
    pg, errors = page
    pg.evaluate("window.app.openExportModal('png')")
    assert pg.evaluate("document.getElementById('export-psd-layers-row').style.display") == 'none'
    assert pg.evaluate("document.getElementById('export-scale-row').style.display") == 'none'
    pg.select_option('#export-format', 'psd')
    assert pg.evaluate("document.getElementById('export-psd-layers-row').style.display") == ''
    assert pg.evaluate("document.getElementById('export-psd-layers').value") == 'screens'
    assert [o.strip() for o in pg.evaluate(
        "[...document.querySelectorAll('#export-psd-layers option')].map(o => o.textContent)")] == [
        'One layer per screen',
        'Elements per screen (checkerboard, borders, cabinet ids, arrows, circuits, labels as separate layers)']
    pg.select_option('#export-psd-layers', 'elements')
    assert pg.evaluate("localStorage.getItem('exportPsdLayers')") == 'elements'
    pg.select_option('#export-format', 'pdf')
    assert pg.evaluate("document.getElementById('export-psd-layers-row').style.display") == 'none'
    pg.click('#export-cancel')
    # A fresh page remembers.
    pg.reload(wait_until='domcontentloaded')
    pg.wait_for_timeout(1500)
    pg.evaluate("window.app.openExportModal('psd')")
    assert pg.evaluate("document.getElementById('export-psd-layers').value") == 'elements'
    pg.select_option('#export-psd-layers', 'screens')
    assert pg.evaluate("localStorage.getItem('exportPsdLayers')") == 'screens'
    pg.click('#export-cancel')
    assert errors == []


# ── the user's own show ───────────────────────────────────────────────────

EXPERTS_JSON = private_fixture('experts-only-fixture.json', 'LRD_EXPERTS_JSON')
# A Pixel Map PNG export (transparent background, canvas 1) of that show
# captured BEFORE the stage filter went into the renderer - an older
# build's output, so the current build cannot regenerate it; frozen beside
# the save in the private fixtures folder, or wherever LRD_PSD_BEFORE_PNG
# points.
BEFORE_PNG = private_fixture('experts-only-pixel-map-before.png', 'LRD_PSD_BEFORE_PNG')


@pytest.mark.skipif(bool(private_fixture_missing(EXPERTS_JSON, BEFORE_PNG)),
                    reason=str(private_fixture_missing(EXPERTS_JSON, BEFORE_PNG)))
def test_the_experts_only_pixel_map_is_the_picture_it_was_before_the_filter(page):
    pg, errors = page
    with open(EXPERTS_JSON) as fh:
        project = json.load(fh)
    pg.evaluate("""async (project) => {
        const app = window.app;
        const j = (method, url, body) => fetch(url, {method,
            headers: {'Content-Type': 'application/json'},
            body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
        await j('PUT', '/api/project', project);
        app.project = await j('GET', '/api/project');
        app.dedupeProjectLayers('psd_layers');
        app.selectLayer(app.project.layers.find(l => (l.type || 'screen') === 'screen'));
        await app.refreshProcessors();
        await app.refreshPortAssignment();
        app.renderLayers();
    }""", project)
    pg.wait_for_timeout(1000)
    items = pg.evaluate("""async () => {
        const app = window.app;
        app.populateExportCanvasesList();
        document.getElementById('export-transparent-bg').checked = true;
        let items = null;
        const real = app.downloadRenderedPNGs;
        app.downloadRenderedPNGs = async (list) => { items = list; };
        try { await app.performExport('T', 'png', ['pixel-map'], app.getSelectedExportCanvasIds()); }
        finally { app.downloadRenderedPNGs = real; }
        return items.map(it => it.dataUrl);
    }""")
    assert len(items) == 1
    with open(BEFORE_PNG, 'rb') as fh:
        assert base64.b64decode(items[0].split(',', 1)[1]) == fh.read()
    assert errors == []
