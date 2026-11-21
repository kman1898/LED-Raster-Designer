"""Show Look's Screen Size and Coordinates (#124).

A Show Look export is handed to content designers as a template, so the
Show Look tab has two boxes of its own:

  * Screen Size draws each screen's size in pixels, "W 512 X H 256", the
    Pixel Map's size line, under the name.
  * Coordinates draws the X, Y of each screen's top-left WHERE IT STANDS IN
    THE SHOW LOOK (showOffsetX/Y), "X -200, Y 100", the Pixel Map's corner
    readout. A screen hanging off the canvas's top or left still reads its
    true figure; the plate pins to the part of it on the canvas. A screen
    wholly off the canvas reads nothing.
  * Both draw on the Show Look canvas and in every Show Look export, and
    nowhere else (the Pixel Map's own label switches are untouched).
  * A grouped wall follows its Names choice on Show Look, as the Pixel Map
    readouts do: Screens, each member its own; Group, the wall's; Both,
    each member's coordinates plus the wall's size.
  * Each box is per screen, kept by the server across a reload, written
    alone (no other field moves), and one click is one undo step.

Run locally:
    python -m pytest tests/test_show_look_labels.py -v -n 4 --dist loadfile
"""

import base64
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


BOOT_JS = ("() => window.app && window.app.project"
           " && window.app._initialLoadComplete === true"
           " && window.canvasRenderer && window.canvasRenderer.zoom > 0")


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
    pg.wait_for_function(BOOT_JS, timeout=20000)
    pg.wait_for_timeout(500)
    yield pg, errors
    context.close()


# One canvas, 1920 x 1080 on both Pixel Map and Show Look. LEFT hangs off
# the Show Look's left edge, MID stands inside it, OFF is wholly off it,
# and G1 + G2 are one grouped wall side by side.
SCREENS = [
    # name, pixel map x, y, columns, rows, show look x, y, group
    ('LEFT', 0, 0, 4, 2, -200, 100, None),
    ('MID', 600, 0, 3, 2, 700, 400, None),
    ('OFF', 1200, 0, 2, 1, -3000, 0, None),
    ('G1', 0, 600, 2, 2, 1000, 700, 'WALL'),
    ('G2', 256, 600, 2, 2, 1256, 700, 'WALL'),
]

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
    for (const [name, x, y, cols, rows, sx, sy] of specs) {
        const l = await j('POST', '/api/layer/add', {name, offset_x: x, offset_y: y,
            columns: cols, rows, cabinet_width: 128, cabinet_height: 128, canvas_id: 'c1'});
        await j('PUT', `/api/layer/${l.id}`, {showOffsetX: sx, showOffsetY: sy});
        ids[name] = l.id;
    }
    const now = await j('GET', '/api/project');
    const members = specs.filter(s => s[7]).map(s => ids[s[0]]);
    now.groups = [{id: 'g1', name: 'WALL', layer_ids: members}];
    now.layers.forEach(l => { if (members.includes(l.id)) l.group_id = 'g1'; });
    await j('PUT', '/api/project', now);
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('show_look_labels_seed');
    app.project.active_canvas_id = 'c1';
    app.selectLayer(app.project.layers.find(l => l.id === ids.LEFT));
    app.syncRasterFromProject();
    app.renderLayers();
    app.updateUI();
    app.resetHistory('Show Look Labels Seed');
    r.render();
    return ids;
}"""

# Every fillText the page makes while `window.__ftLog` is an array, with
# where it landed on its canvas (the transform applied) and that canvas's
# size: the real drawing, on screen and in an export alike.
SPY_JS = """() => {
    if (window.__ftSpy) return;
    const orig = CanvasRenderingContext2D.prototype.fillText;
    CanvasRenderingContext2D.prototype.fillText = function (t, x, y, ...rest) {
        if (window.__ftLog) {
            const p = this.getTransform().transformPoint(new DOMPoint(x, y));
            window.__ftLog.push({t: String(t), x: p.x, y: p.y,
                                 w: this.canvas.width, h: this.canvas.height});
        }
        return orig.call(this, t, x, y, ...rest);
    };
    window.__ftSpy = true;
}"""

DRAWN_JS = """() => {
    window.__ftLog = [];
    window.canvasRenderer.render();
    const texts = window.__ftLog.map(e => e.t);
    window.__ftLog = null;
    const rec = (window.canvasRenderer.showLookLabelsDrawn || []).map(d => [d.kind, d.text]);
    return {texts, rec};
}"""


def _seed(pg):
    pg.evaluate(SPY_JS)
    ids = pg.evaluate(SEED_JS, SCREENS)
    _view(pg, 'pixel-map')
    return ids


def _view(pg, mode):
    pg.locator(f'.view-tab[data-mode="{mode}"]').click()
    pg.wait_for_function("(m) => window.canvasRenderer.viewMode === m", arg=mode)


def _select(pg, lid):
    pg.evaluate("(id) => { const a = window.app;"
                " a.selectLayer(a.project.layers.find(l => l.id === id)); }", lid)


def _drawn(pg):
    return pg.evaluate(DRAWN_JS)


def _settle(pg):
    pg.evaluate("() => window.app._layerSavesSettled()")


def _server_layers(pg):
    return pg.evaluate("""async () => Object.fromEntries((await (await fetch('/api/project')).json())
        .layers.map(l => [l.name, l]))""")


# Every screen as the page holds it, less its cabinets and client scratch:
# what an edit wrote, field by field.
CLIENT_JS = """() => Object.fromEntries(window.app.project.layers.map(l => [l.name,
    JSON.parse(JSON.stringify(Object.fromEntries(Object.entries(l)
        .filter(([k]) => k !== 'panels' && k.charAt(0) !== '_'))))]))"""


def _client_layers(pg):
    return pg.evaluate(CLIENT_JS)


def _flags(layer):
    return (layer.get('showLabelSizePxShowLook'), layer.get('showOffsetTLShowLook'))


def _sizes(d):
    return sorted(t for k, t in d['rec'] if k == 'size')


def _coords(d):
    return sorted(t for k, t in d['rec'] if k == 'coords')


def _names(pg, mode):
    pg.locator(f'.name-display-btn[data-name-view="show-look"][data-name-display="{mode}"]').click()
    pg.wait_for_function("(m) => window.app.groupNameDisplayFor('show-look',"
                         " window.app.resolveGroup('g1')) === m", arg=mode)


def test_the_boxes_sit_on_the_show_look_tab_and_start_off(page):
    pg, errors = page
    ids = _seed(pg)
    _view(pg, 'show-look')
    panel = pg.locator('.tab-panel[data-tab="show-look"]')
    for box, label in (('#show-label-size-show-look', 'Screen Size'),
                       ('#show-offset-show-look', 'Coordinates')):
        assert panel.locator(box).is_visible()
        assert not panel.locator(box).is_checked()
        assert panel.locator(f'label[for="{box[1:]}"]').text_content().strip() == label
    srv = _server_layers(pg)
    assert all(not any(_flags(srv[n])) for n in ids), {n: _flags(srv[n]) for n in ids}
    d = _drawn(pg)
    assert d['rec'] == [], d['rec']
    assert not [t for t in d['texts'] if t.startswith('X ') or t.startswith('W ')], d['texts']
    assert errors == []


def test_each_box_draws_the_show_look_figures_and_writes_only_its_field(page):
    pg, errors = page
    ids = _seed(pg)
    _view(pg, 'show-look')
    _select(pg, ids['LEFT'])
    before = _client_layers(pg)
    pg.locator('#show-label-size-show-look').check()
    _settle(pg)
    d = _drawn(pg)
    assert _sizes(d) == ['W 512 X H 256'], d['rec']
    assert 'W 512 X H 256' in d['texts']
    assert _coords(d) == []
    pg.locator('#show-offset-show-look').check()
    _settle(pg)
    d = _drawn(pg)
    # LEFT stands 200 px past the canvas's left edge: its true figure.
    assert _coords(d) == ['X -200, Y 100'], d['rec']
    assert 'X -200, Y 100' in d['texts']
    after = _client_layers(pg)
    # The two fields moved on LEFT and nothing else did, on any screen,
    # and the server holds them.
    for name in ids:
        changed = sorted(k for k in set(before[name]) | set(after[name])
                         if before[name].get(k) != after[name].get(k))
        want = ['showLabelSizePxShowLook', 'showOffsetTLShowLook'] if name == 'LEFT' else []
        assert changed == want, (name, changed)
    assert _flags(_server_layers(pg)['LEFT']) == (True, True)
    # MID takes its own: inside the canvas, at its Show Look place, not
    # its Pixel Map one (600, 0).
    _select(pg, ids['MID'])
    assert not pg.locator('#show-offset-show-look').is_checked()
    pg.locator('#show-label-size-show-look').check()
    pg.locator('#show-offset-show-look').check()
    _settle(pg)
    d = _drawn(pg)
    assert _sizes(d) == ['W 384 X H 256', 'W 512 X H 256'], d['rec']
    assert _coords(d) == ['X -200, Y 100', 'X 700, Y 400'], d['rec']
    assert 'X 600, Y 0' not in d['texts']
    # A screen wholly off the canvas reads nothing.
    _select(pg, ids['OFF'])
    pg.locator('#show-offset-show-look').check()
    _settle(pg)
    assert _coords(_drawn(pg)) == ['X -200, Y 100', 'X 700, Y 400']
    # The Pixel Map draws none of it: its own switches are its own (its
    # Screen Size (px), on by default, still draws its own size line).
    _view(pg, 'pixel-map')
    d = _drawn(pg)
    assert d['rec'] == []
    assert not [t for t in d['texts'] if t in ('X -200, Y 100', 'X 700, Y 400')], d['texts']
    assert errors == []


def test_one_click_is_one_undo_step(page):
    pg, errors = page
    ids = _seed(pg)
    _view(pg, 'show-look')
    _select(pg, ids['MID'])
    at = pg.evaluate("() => window.app.historyIndex")
    pg.locator('#show-offset-show-look').check()
    _settle(pg)
    assert pg.evaluate("() => window.app.historyIndex") == at + 1
    assert _flags(_server_layers(pg)['MID']) == (False, True)
    pg.evaluate("() => window.app.undo()")
    _settle(pg)
    pg.wait_for_function("(id) => !window.app.project.layers.find(l => l.id === id).showOffsetTLShowLook",
                         arg=ids['MID'])
    assert pg.evaluate("() => window.app.historyIndex") == at
    assert not _flags(_server_layers(pg)['MID'])[1]
    assert _coords(_drawn(pg)) == []
    assert not pg.locator('#show-offset-show-look').is_checked()
    pg.evaluate("() => window.app.redo()")
    _settle(pg)
    pg.wait_for_function("(id) => window.app.project.layers.find(l => l.id === id).showOffsetTLShowLook === true",
                         arg=ids['MID'])
    assert _coords(_drawn(pg)) == ['X 700, Y 400']
    assert errors == []


def test_a_grouped_wall_follows_its_names_choice(page):
    pg, errors = page
    ids = _seed(pg)
    _view(pg, 'show-look')
    _select(pg, ids['G1'])
    pg.locator('#show-label-size-show-look').check()
    pg.locator('#show-offset-show-look').check()
    _settle(pg)
    srv = _server_layers(pg)
    # One tick reaches the whole wall, and only the wall.
    assert _flags(srv['G1']) == (True, True) and _flags(srv['G2']) == (True, True)
    assert not any(_flags(srv['LEFT'])) and not any(_flags(srv['MID']))
    _names(pg, 'screens')
    d = _drawn(pg)
    assert _sizes(d) == ['W 256 X H 256', 'W 256 X H 256'], d['rec']
    assert _coords(d) == ['X 1000, Y 700', 'X 1256, Y 700'], d['rec']
    _names(pg, 'group')
    d = _drawn(pg)
    assert _sizes(d) == ['W 512 X H 256'], d['rec']
    assert _coords(d) == ['X 1000, Y 700'], d['rec']
    _names(pg, 'both')
    d = _drawn(pg)
    assert _sizes(d) == ['W 512 X H 256'], d['rec']
    # The wall's top-left is G1's, read once.
    assert _coords(d) == ['X 1000, Y 700', 'X 1256, Y 700'], d['rec']
    # Moved on the Show Look, every figure follows.
    pg.evaluate("""async (ids) => {
        const a = window.app;
        a.project.layers.filter(l => ids.includes(l.id)).forEach(l => { l.showOffsetY -= 750; });
        a.updateLayers(a.project.layers.filter(l => ids.includes(l.id)), true, 'Move');
    }""", [ids['G1'], ids['G2']])
    _settle(pg)
    _names(pg, 'screens')
    assert _coords(_drawn(pg)) == ['X 1000, Y -50', 'X 1256, Y -50']
    assert errors == []


def test_the_boxes_survive_a_reload(page):
    pg, errors = page
    ids = _seed(pg)
    _view(pg, 'show-look')
    _select(pg, ids['LEFT'])
    pg.locator('#show-offset-show-look').check()
    _select(pg, ids['MID'])
    pg.locator('#show-label-size-show-look').check()
    _settle(pg)
    pg.reload(wait_until='domcontentloaded')
    pg.wait_for_function(BOOT_JS, timeout=20000)
    pg.wait_for_timeout(500)
    pg.evaluate(SPY_JS)
    _view(pg, 'show-look')
    _select(pg, ids['LEFT'])
    assert pg.locator('#show-offset-show-look').is_checked()
    assert not pg.locator('#show-label-size-show-look').is_checked()
    _select(pg, ids['MID'])
    assert pg.locator('#show-label-size-show-look').is_checked()
    assert not pg.locator('#show-offset-show-look').is_checked()
    d = _drawn(pg)
    assert _coords(d) == ['X -200, Y 100'] and _sizes(d) == ['W 384 X H 256'], d['rec']
    assert errors == []


# performExport with the writers stubbed: the rendered items come back
# instead of going to disk, with every fillText the export made.
EXPORT_JS = """async ([format, views]) => {
    const app = window.app;
    const keep = {png: app.downloadRenderedPNGs, pdf: app.downloadAsPdf, svg: app.downloadAsSvg};
    let items = null;
    app.downloadRenderedPNGs = async (it) => { items = it; };
    app.downloadAsPdf = async (name, it) => { items = it; };
    app.downloadAsSvg = async (name, it) => { items = it; };
    window.__ftLog = [];
    try {
        await app.performExport('Template', format, views, ['c1']);
    } finally {
        app.downloadRenderedPNGs = keep.png; app.downloadAsPdf = keep.pdf; app.downloadAsSvg = keep.svg;
    }
    const log = window.__ftLog; window.__ftLog = null;
    return {
        items: (items || []).map(i => ({view: i.view, width: i.width, height: i.height,
                                        dataUrl: i.dataUrl, svg: i.svg || null})),
        texts: log.filter(e => e.w === 1920 && e.h === 1080),
    };
}"""


def _export(pg, fmt, views):
    return pg.evaluate(EXPORT_JS, [fmt, views])


def _shot_dir():
    return os.environ.get('LRD_SHOW_LOOK_SHOTS')


def test_every_show_look_export_carries_them(page):
    pg, errors = page
    ids = _seed(pg)
    _view(pg, 'show-look')
    for name in ('LEFT', 'MID', 'OFF', 'G1'):
        _select(pg, ids[name])
        pg.locator('#show-label-size-show-look').check()
        pg.locator('#show-offset-show-look').check()
    _names(pg, 'screens')
    _settle(pg)
    want_coords = {'X -200, Y 100', 'X 700, Y 400', 'X 1000, Y 700', 'X 1256, Y 700'}
    want_sizes = {'W 512 X H 256', 'W 384 X H 256', 'W 256 X H 256'}
    out = _export(pg, 'png', ['show-look', 'pixel-map'])
    views = {i['view']: i for i in out['items']}
    assert set(views) == {'show-look', 'pixel-map'}
    assert (views['show-look']['width'], views['show-look']['height']) == (1920, 1080)
    texts = [e['t'] for e in out['texts']]
    assert want_coords <= set(texts), texts
    assert want_sizes <= set(texts), texts
    assert 'X -3000, Y 0' not in texts
    # Each figure once in the export's Show Look pass, and the Pixel Map
    # pass carries none of them.
    for t in want_coords:
        assert texts.count(t) == 1, (t, texts)
    # LEFT's plate is pinned on the canvas: its true figure, drawn on the
    # part of LEFT inside the canvas (x 0 to 312, y 100 to 356).
    left = [e for e in out['texts'] if e['t'] == 'X -200, Y 100'][0]
    assert 0 <= left['x'] < 312 and 100 <= left['y'] < 356, left
    for e in out['texts']:
        if e['t'] in want_coords:
            assert 0 <= e['x'] < 1920 and 0 <= e['y'] < 1080, e
    pdf = _export(pg, 'pdf', ['show-look'])
    assert [i['view'] for i in pdf['items']] == ['show-look']
    assert want_coords <= {e['t'] for e in pdf['texts']}
    svg = _export(pg, 'svg', ['show-look'])
    doc = svg['items'][0]['svg'] or ''
    for t in want_coords | want_sizes:
        assert t in doc, t
    shots = _shot_dir()
    if shots:
        os.makedirs(shots, exist_ok=True)
        data = views['show-look']['dataUrl'].split(',', 1)[1]
        with open(os.path.join(shots, 'show_look_export.png'), 'wb') as f:
            f.write(base64.b64decode(data))
        _view(pg, 'show-look')
        pg.evaluate("() => { window.canvasRenderer.fitToView(); window.canvasRenderer.render(); }")
        pg.locator('#main-canvas').screenshot(path=os.path.join(shots, 'show_look_canvas.png'))
    assert errors == []
