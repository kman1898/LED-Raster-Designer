"""The last rulings for 1.5 (owner, 2026-10-18).

1. Every column of every binder table stands centred - headings and
   values, names and labels included. A wrapped list centres each line; a
   strand list centres each line, its swatch with it; a strand's tinted
   cell centres its swatch and name together; an outlined fiber group
   centres in its cell; the tick box centres in its column; the group
   headings (PRIMARY / BACKUP) centre over their halves. The title block's
   revisions log centres its four columns too. A band over a run of rows
   still reads from the table's left edge - it is a heading across the
   table, not a column.
2. "LEN" is "LENGTH" wherever it is a heading: the binder's Cables this
   screen, the pull sheet and the pull lists. The column takes the room
   from CABLE and QTY's spare, so no other cell changes; the Excel export
   and the pull-sheet editor already said "Length".
3. An L21-30 box's 30 A per-leg feed is held to the 80% continuous rule -
   24 A on a US system - unless the distro's main is 100% rated, when it
   stays 30 A. The strip says the limit the way the main's does.
4. A half tile weighs what the panel library lists for its model's
   matching half-size variant, where one matches perfectly (same
   manufacturer and series, exactly half on the halved axis and equal on
   the other, the same pitch); otherwise 0.65 of the full cabinet, as
   before. The weight totals, the canvas weight label and the group totals
   read it.
5. A custom run past its port's limit says by how much, in red: "over by
   26,232 px (576,000 / 549,768 px)" where "· full" stood; at or under the
   limit it reads as before.

The figures, by hand:
  * Table 1: four columns at fractions 0.5 / 1 / 0.5 / 1 of 900, each
    holding its content, so 150 / 300 / 150 / 300 wide - middles 75, 300,
    525 and 750; the tick box (24) at 75 - 12 = 63.
  * Table 2: two halves of 450 - PRIMARY's middle 225, BACKUP's 675.
  * L21-30: 5 x 600 W cabinets a circuit at 208 V is 3000 / 208 =
    14.423 A; two circuits on one box share a feed leg at 14.423 x sqrt(3)
    = 24.98 A - over 24 A (80% of 30 A), under 30 A.
  * Half weight: a 500 x 1000 mm, 128 x 256 px, 13 kg cabinet whose
    library half (500 x 500 mm, 128 x 128 px, same pitch) weighs 7.5 kg: a
    2 x 2 wall with its top row halved weighs 2 x 13 + 2 x 7.5 = 41 kg
    (it was 2 x 13 + 2 x 0.65 x 13 = 42.9 kg). Without the half in the
    library: 42.9 kg.
  * Armor readout: NovaStar Armor pays for the rectangle round the run; an
    L along the top row and down the left side of a 28 x 6 wall of 128 px
    cabinets pays for all 168 cabinets, 168 x 16,384 = 2,752,512 px.

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_rulings_1018_final.py -q --browser chromium
"""

import json
import math
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

ROOT = os.path.join(os.path.dirname(__file__), '..', 'src')


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    pg.wait_for_timeout(1200)
    yield pg, errors
    context.close()


# ── 1. every column of every table stands centred ────────────────────────

# A table drawn line by line into a context that writes down every text it
# fills (with the alignment in force), every rect it strokes and fills.
TABLE_JS = """(spec) => {
    const app = window.app;
    const real = document.createElement('canvas').getContext('2d');
    const calls = [];
    const ctx = new Proxy(real, {
        get(t, k) {
            if (k === 'fillText') return (s, x, y) => {
                calls.push({ op: 'text', t: String(s), x, y, align: t.textAlign, font: t.font });
                return t.fillText(s, x, y); };
            if (k === 'strokeRect') return (x, y, w, h) => {
                calls.push({ op: 'stroke', x, y, w, h }); return t.strokeRect(x, y, w, h); };
            if (k === 'fillRect') return (x, y, w, h) => {
                calls.push({ op: 'fill', x, y, w, h, c: t.fillStyle }); return t.fillRect(x, y, w, h); };
            const v = t[k];
            return typeof v === 'function' ? v.bind(t) : v;
        },
        set(t, k, v) { t[k] = v; return true; },
    });
    const book = { ctx, measureCtx: real, meta: { palette: 'colour' }, page: { painting: true },
                   log: { texts: [], textInfo: [], mapTexts: [], dashes: [] } };
    const lines = app._bTableLines(book, spec);
    let y = 0;
    for (const l of lines) { l.draw(ctx, 0, y, spec.width); y += l.h; }
    const measure = (t, font) => { real.font = font; return real.measureText(t).width; };
    return { calls, widths: calls.filter(c => c.op === 'text').map(c => measure(c.t, c.font)) };
}"""


def _table(pg, spec):
    out = pg.evaluate(TABLE_JS, spec)
    texts = [c for c in out['calls'] if c['op'] == 'text']
    for t, w in zip(texts, out['widths']):
        t['w'] = w
    return texts, out['calls']


def test_every_column_heading_and_cell_stands_on_its_middle(page):
    """NAME, QTY (right-aligned before) and LABEL - headings and cells - on
    their columns' middles, 300, 525 and 750; the wrapped label list on
    several lines, each centred; the tick box in its column's middle."""
    pg, errors = page
    labels = ', '.join(f'S1-{n}' for n in range(1, 31))
    texts, calls = _table(pg, {
        'title': 'Cables', 'width': 900,
        'cols': [{'title': '', 'w': 0.5, 'tick': True}, {'title': 'name', 'w': 1},
                 {'title': 'qty', 'w': 0.5, 'align': 'right'}, {'title': 'label', 'w': 1, 'list': True}],
        'rows': [{'cells': ['', 'Data Cable', '12', labels]}, {'cells': ['', 'Power', '3', 'A']}]})
    mid = {'NAME': 300, 'QTY': 525, 'LABEL': 750}
    for head, x in mid.items():
        h = next(t for t in texts if t['t'] == head)
        assert h['align'] == 'center' and abs(h['x'] - x) < 0.01, h
    cells = [t for t in texts if t['t'] not in mid and t['t'] != 'CABLES']
    assert cells, texts
    for t in cells:
        assert t['align'] == 'center', t
        assert min(abs(t['x'] - x) for x in mid.values()) < 0.01, t
    # the long label list wrapped onto lines of its own, every one centred
    listed = [t for t in cells if t['t'].startswith('S1-')]
    assert len(listed) >= 2 and all(abs(t['x'] - 750) < 0.01 for t in listed), listed
    # the title stays at the table's left edge
    assert next(t for t in texts if t['t'] == 'CABLES')['align'] == 'left'
    # the tick box: 24 square, centred on 75
    ticks = [c for c in calls if c['op'] == 'stroke' and c['w'] == 24 and c['h'] == 24]
    assert len(ticks) == 2 and all(abs(c['x'] + 12 - 75) < 0.01 for c in ticks), ticks
    assert errors == []


def test_the_group_headings_centre_over_their_halves_and_a_band_reads_from_the_left(page):
    pg, _ = page
    texts, _calls = _table(pg, {
        'title': 'Ports', 'width': 900,
        'groups': [{'title': 'primary', 'from': 0, 'to': 0}, {'title': 'backup', 'from': 1, 'to': 1}],
        'cols': [{'title': 'port', 'w': 1}, {'title': 'port', 'w': 1, 'rule': True}],
        'rows': [{'band': 'XD A · OPT 1-2'}, {'cells': ['SR A-1', 'SR B-1']}]})
    at = {t['t']: t for t in texts}
    assert at['PRIMARY']['align'] == 'center' and abs(at['PRIMARY']['x'] - 225) < 0.01, at['PRIMARY']
    assert at['BACKUP']['align'] == 'center' and abs(at['BACKUP']['x'] - 675) < 0.01, at['BACKUP']
    assert at['XD A · OPT 1-2']['align'] == 'left' and abs(at['XD A · OPT 1-2']['x'] - 12) < 0.01
    assert abs(at['SR A-1']['x'] - 225) < 0.01 and abs(at['SR B-1']['x'] - 675) < 0.01


BLUE, ORANGE = '#1f5fd6', '#f08a24'


def test_strands_swatches_and_fiber_groups_centre_in_their_cells(page):
    """Three 300 wide columns: a strand list (one strand a line), a
    strand's tinted cell, and an outlined fiber group - each line's swatch
    and name, the tinted cell's swatch and name, and the group's outline
    all centred on 150, 450 and 750."""
    pg, _ = page
    sw = lambda c: {'base': c}  # noqa: E731
    texts, calls = _table(pg, {
        'title': 'Fiber', 'width': 900,
        'cols': [{'title': 'at the processor', 'w': 1, 'list': 3, 'parts': True},
                 {'title': 'strand', 'w': 1, 'swatch': True},
                 {'title': 'fiber', 'w': 1, 'inputs': True}],
        'rows': [{'cells': ['1 Blue 2 Orange', '1 Blue', 'X1'],
                  'parts': {'0': [{'text': '1 Blue', 'swatch': sw(BLUE)},
                                  {'text': '2 Orange', 'swatch': sw(ORANGE), 'brk': True}]},
                  'swatch': sw(BLUE),
                  'inputs': {'2': [{'head': 'X1', 'sub': 'TAC A',
                                    'strands': [{'text': '3 Green', 'swatch': sw('#2e9e44')},
                                                {'text': '4 Brown', 'swatch': sw('#8a5a2b')}]},
                                   {'head': 'X2', 'sub': 'TAC A',
                                    'strands': [{'text': '5 Slate', 'swatch': sw('#777777')},
                                                {'text': '6 White', 'swatch': sw('#ffffff')}]}]}}]})
    swatches = [c for c in calls if c['op'] == 'fill' and c['w'] == 24 and c['h'] == 24]

    def centre(t):
        # the swatch just left of the text on its line, then the name
        s = next(c for c in swatches if 0 < t['x'] - c['x'] <= 34 and c['y'] <= t['y'] <= c['y'] + 30)
        return (s['x'] + t['x'] + t['w']) / 2

    in_col = lambda t, lo, hi: lo <= t['x'] < hi  # noqa: E731
    parts = [t for t in texts if t['t'] in ('1 Blue', '2 Orange') and in_col(t, 0, 300)]
    assert len(parts) == 2 and parts[0]['y'] < parts[1]['y'], parts
    for t in parts:
        assert abs(centre(t) - 150) < 0.6, (t, centre(t))
    tinted = next(t for t in texts if t['t'] == '1 Blue' and in_col(t, 300, 600))
    assert abs(centre(tinted) - 450) < 0.6, tinted
    # two groups of different widths: one outline width, one under the
    # other, the pair centred
    outline = [c for c in calls if c['op'] == 'stroke' and c['w'] > 30 and c['x'] >= 600]
    assert len(outline) == 2, outline
    assert abs(outline[0]['x'] - outline[1]['x']) < 0.01 and abs(outline[0]['w'] - outline[1]['w']) < 0.01
    assert all(abs(c['x'] + c['w'] / 2 - 750) < 0.6 for c in outline), outline
    # the strands keep one column inside them, the labels another
    strands = [next(t for t in texts if t['t'] == n) for n in ('3 Green', '4 Brown', '5 Slate', '6 White')]
    assert max(t['x'] for t in strands) - min(t['x'] for t in strands) < 0.01, strands
    x1, x2 = (next(t for t in texts if t['t'] == n) for n in ('X1', 'X2'))
    assert abs(x1['x'] - x2['x']) < 0.01


SEED_JS = """async (o) => {
    const app = window.app;
    const proj = await (await fetch('/api/project')).json();
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments;
    proj.binder = Object.assign({}, proj.binder || {}, { revisions: o.revisions || [] });
    await fetch('/api/project', {method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(proj)});
    await fetch('/api/layer/add', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: 'WALL', columns: 6, rows: 3, cabinet_width: 200, cabinet_height: 200})});
    app.project = await (await fetch('/api/project')).json();
    app.dedupeProjectLayers('rulings_1018');
    const l = app.project.layers.find(x => (x.type || 'screen') === 'screen');
    Object.assign(l, { powerVoltage: 208, powerAmperage: 20, panelWatts: 200 });
    app.currentLayer = l;
    app.selectedLayerIds = new Set([l.id]);
    app.renderLayers();
    const opts = { sheet: 'tabloid', palette: 'colour', sides: { power: true, data: true },
                   scope: { kind: 'show' }, cover: true, pull: true, hardware: true, wiring: false };
    const plan = app.planBinder(opts);
    const pages = [];
    for (let i = 0; i < plan.length; i++) {
        const r = app.renderBinderPage(opts, i);
        pages.push({ title: plan[i].title, kind: plan[i].kind,
                     texts: r.record.ops.filter(o => o.op === 'text' && String(o.text).trim())
                        .map(o => ({ t: o.text, x: o.x, y: o.y, size: o.size, weight: o.weight, align: o.align })) });
    }
    return pages;
}"""


def test_the_revisions_log_centres_its_columns(page):
    """The title block's revisions: No., Date, By and Description each
    centred over its column, and the logged revision's figures each
    centred under its heading."""
    pg, errors = page
    pages = pg.evaluate(SEED_JS, {'revisions': [
        {'no': 1, 'rev': '1.0', 'date': '10/18/26', 'by': 'MK', 'description': 'First issue'}]})
    texts = pages[0]['texts']
    heads = {t['t']: t for t in texts if t['t'] in ('No.', 'Date', 'By', 'Description')}
    assert len(heads) == 4, [t['t'] for t in texts]
    for want, head in (('1', 'No.'), ('10/18/26', 'Date'), ('MK', 'By'), ('First issue', 'Description')):
        h = heads[head]
        cell = next(t for t in texts if t['t'] == want and t['y'] > h['y'])
        assert h['align'] == 'center' and cell['align'] == 'center', (h, cell)
        assert abs(cell['x'] - h['x']) < 0.01, (h, cell)
    xs = [heads[k]['x'] for k in ('No.', 'Date', 'By', 'Description')]
    assert xs == sorted(xs), xs
    assert errors == []


# ── 2. LEN is LENGTH ─────────────────────────────────────────────────────

def test_length_is_the_heading_everywhere_and_never_cut(page):
    """No sheet prints "LEN": the Cables this screen table, the pull sheet's
    cable tables and the pull list say "LENGTH" - whole, at the size of
    the headings beside it where the table has the room."""
    pg, errors = page
    pages = pg.evaluate(SEED_JS, {})
    texts = [t for p in pages for t in p['texts']]
    assert not [t for t in texts if t['t'] in ('LEN', 'Len') or t['t'].startswith('LEN…')], texts
    kinds = {p['kind'] for p in pages if any(t['t'] == 'LENGTH' for t in p['texts'])}
    assert {'power', 'pull'} <= kinds, kinds
    pull_list = [p for p in pages if any(t['t'] == 'PULL LIST' for t in p['texts'])]
    assert pull_list and any(t['t'] == 'LENGTH' for t in pull_list[0]['texts'])
    for p in pages:
        for t in p['texts']:
            if t['t'] != 'LENGTH':
                continue
            cable = next(c for c in p['texts'] if c['t'] == 'CABLE' and abs(c['y'] - t['y']) < 0.5)
            assert t['size'] == cable['size'] and t['align'] == 'center', (p['title'], t, cable)
    assert errors == []


def test_the_spreadsheet_and_the_editor_say_length():
    import pull_sheet
    assert pull_sheet.HEADERS[:2] == ['Cable Type', 'Length']
    src = open(os.path.join(ROOT, 'static', 'js', 'app-pull-sheet-editor.js'), encoding='utf-8').read()
    assert '<th>Length</th>' in src and '>Len<' not in src
    import openpyxl
    wb = openpyxl.load_workbook(os.path.join(ROOT, 'static', 'templates', 'pull-sheet-template.xlsx'))
    heads = [c.value for ws in wb for row in ws.iter_rows(max_row=8) for c in row if isinstance(c.value, str)]
    assert 'Length' in heads and not [h for h in heads if h.strip().lower() in ('len', 'len.')], heads


# ── 3. the L21-30 feed at 80% ────────────────────────────────────────────

L2130_JS = """(o) => {
    const app = window.app;
    const S = { id: 98, name: 'L21', type: 'screen', visible: true, columns: 2, rows: 5,
                cabinet_width: 128, cabinet_height: 128, offset_x: 0, offset_y: 0,
                panel_weight: 20, weight_unit: 'kg', panelWatts: 600, powerVoltage: 208,
                powerAmperage: 15, processorType: 'brompton', bitDepth: 8, frameRate: 60,
                flowPattern: 'tl-h', portMappingMode: 'organized', powerFlowPattern: 'tl-v',
                powerOrganized: true, powerMaximize: false, group_id: null,
                powerBreakoutType: 'l2130-powercon', powerSocaDistro: { 1: 'dq' } };
    S.panels = [];
    for (let r = 0; r < 5; r++) for (let c = 0; c < 2; c++) {
        S.panels.push({ row: r, col: c, x: c * 128, y: r * 128, width: 128, height: 128,
                        hidden: false, blank: false, halfTile: 'none' });
    }
    const d = Object.assign({ id: 'dq', name: 'Q', ratingA: 400, voltage: 208, phase: 3 }, o.distro || {});
    const saved = { project: app.project, currentLayer: app.currentLayer };
    app.project = { layers: [S], groups: [], canvases: [], rack: [], distros: [d] };
    try {
        app.currentLayer = S;
        app._circuitTailCache = null;
        app.refreshDistroPanel();
        const feed = app.boxFeedLegAmps(app.getDistros()[0], [{ layer: S, s: app.getSocaPlan(S)[0] }]);
        const sec = document.querySelector('#hardware-dock-body [data-lrd-sec="hwdock-multi-dq-1"]');
        const box = sec && sec.closest('.hw-dock-multi');
        return { circuits: app.getSocaPlan(S)[0].legs.length,
                 worst: Math.max(feed.X, feed.Y, feed.Z),
                 warnings: (app._dockPowerWarnings || []).map(w => w.text),
                 clash: !!(box && box.classList.contains('hw-dock-multi-clash')),
                 rule: app.distroFeedLimit(app.getDistros()[0], 30) };
    } finally {
        app.project = saved.project;
        app.currentLayer = saved.currentLayer;
        app._circuitTailCache = null;
        app.refreshDistroPanel();
    }
}"""


def test_an_l2130_feed_is_held_to_24_a_unless_the_main_is_100_percent_rated(page):
    pg, errors = page
    # the dock - and its strip - draws in the power view
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(600)
    i = 3000 / 208
    out = pg.evaluate(L2130_JS, {})
    assert out['circuits'] == 2, out
    assert out['worst'] == pytest.approx(i * math.sqrt(3), abs=1e-6)       # 24.98 A
    assert 24 < out['worst'] < 30
    assert out['rule']['limitA'] == pytest.approx(24) and out['rule']['pct'] == 0.8, out['rule']
    want = f"Q 1 — feed leg at {out['worst']:.2f} A / 24 A (80% of 30 A) — OVER"
    assert want == 'Q 1 — feed leg at 24.98 A / 24 A (80% of 30 A) — OVER'
    assert want in out['warnings'], out['warnings']
    assert out['clash'] is True
    # Main 100% rated: the feed keeps its 30 A, and 24.98 A is inside it
    rated = pg.evaluate(L2130_JS, {'distro': {'main100': True}})
    assert rated['rule']['limitA'] == pytest.approx(30), rated['rule']
    assert not [w for w in rated['warnings'] if 'feed leg' in w], rated['warnings']
    assert rated['clash'] is False
    assert errors == []


# ── 4. a half tile's weight from the panel library ───────────────────────

CATALOG = {
    'ACME': [
        {'name': 'Foo 3.9 Full Tile', 'width_mm': 500, 'height_mm': 1000, 'pixels_w': 128, 'pixels_h': 256,
         'pitch_mm': 3.9, 'weight_kg': 13.0},
        {'name': 'Foo 3.9 Half Tile', 'width_mm': 500, 'height_mm': 500, 'pixels_w': 128, 'pixels_h': 128,
         'pitch_mm': 3.9, 'weight_kg': 7.5},
        # a near miss on every rule: another series, another pitch, not
        # quite half
        {'name': 'Bar 3.9 Full Tile', 'width_mm': 500, 'height_mm': 1000, 'pixels_w': 128, 'pixels_h': 256,
         'pitch_mm': 3.9, 'weight_kg': 14.0},
        {'name': 'Baz 3.9 Half Tile', 'width_mm': 500, 'height_mm': 500, 'pixels_w': 128, 'pixels_h': 128,
         'pitch_mm': 3.9, 'weight_kg': 6.0},
        {'name': 'Qux 3.9 Full Tile', 'width_mm': 500, 'height_mm': 1000, 'pixels_w': 128, 'pixels_h': 256,
         'pitch_mm': 3.9, 'weight_kg': 15.0},
        {'name': 'Qux 3.9 Half Tile', 'width_mm': 500, 'height_mm': 500, 'pixels_w': 128, 'pixels_h': 128,
         'pitch_mm': 3.91, 'weight_kg': 8.0},
        {'name': 'Zed 3.9 (500x1000)', 'width_mm': 500, 'height_mm': 1000, 'pixels_w': 128, 'pixels_h': 256,
         'pitch_mm': 3.9, 'weight_kg': 16.0},
        {'name': 'Zed 3.9 (500x499)', 'width_mm': 500, 'height_mm': 499, 'pixels_w': 128, 'pixels_h': 128,
         'pitch_mm': 3.9, 'weight_kg': 9.0},
    ],
    # the same cabinet as Foo from someone else, with a half of another
    # weight: a 12 kg screen matches both, so neither answers
    'OTHER': [
        {'name': 'Twin Full Tile', 'width_mm': 500, 'height_mm': 1000, 'pixels_w': 128, 'pixels_h': 256,
         'pitch_mm': 3.9, 'weight_kg': 12.0},
        {'name': 'Twin Half Tile', 'width_mm': 500, 'height_mm': 500, 'pixels_w': 128, 'pixels_h': 128,
         'pitch_mm': 3.9, 'weight_kg': 7.0},
        {'name': 'Twain Full Tile', 'width_mm': 500, 'height_mm': 1000, 'pixels_w': 128, 'pixels_h': 256,
         'pitch_mm': 3.9, 'weight_kg': 12.0},
        {'name': 'Twain Half Tile', 'width_mm': 500, 'height_mm': 500, 'pixels_w': 128, 'pixels_h': 128,
         'pitch_mm': 3.9, 'weight_kg': 6.5},
    ],
}

HALF_JS = """([catalog, cases]) => {
    const app = window.app;
    const r = window.canvasRenderer;
    const keep = { catalog: app._panelCatalog, flat: app._panelCatalogFlat, cache: app._halfWeightCache,
                   project: app.project, currentLayer: app.currentLayer, selected: app.selectedLayerIds,
                   viewMode: r.viewMode, zoom: r.zoom, panX: r.panX, panY: r.panY,
                   updateLayers: app.updateLayers, renderLayers: app.renderLayers,
                   loadLayerToInputs: app.loadLayerToInputs };
    const screen = (s) => {
        const l = Object.assign({ id: 1, name: 'S', type: 'screen', visible: true, canvas_id: 'c1',
            columns: 2, rows: 2, cabinet_width: 128, cabinet_height: 256,
            panel_width_mm: 500, panel_height_mm: 1000, offset_x: 0, offset_y: 0,
            panel_weight: 13, weight_unit: 'kg', panelWatts: 200, powerVoltage: 208, powerAmperage: 20,
            processorType: 'brompton', bitDepth: 8, frameRate: 60, flowPattern: 'tl-h',
            portMappingMode: 'organized', powerFlowPattern: 'tl-h', color1: { r: 64, g: 70, b: 128 },
            color2: { r: 149, g: 156, b: 184 }, show_numbers: false, rotation: 0,
            showLabelName: false, showLabelSizePx: false, showLabelSizeM: false, showLabelSizeFt: false,
            showLabelWeight: true, showLabelInfo: false, group_id: null }, s);
        l.panels = [];
        for (let y = 0; y < l.rows; y++) for (let x = 0; x < l.columns; x++) {
            const half = y === 0 ? (l.halve || 'none') : 'none';
            l.panels.push({ id: y * l.columns + x + 1, number: y * l.columns + x + 1, row: y, col: x,
                x: l.offset_x + x * l.cabinet_width, y: l.offset_y + y * l.cabinet_height,
                width: half === 'width' ? l.cabinet_width / 2 : l.cabinet_width,
                height: half === 'height' ? l.cabinet_height / 2 : l.cabinet_height,
                hidden: false, blank: false, halfTile: half, is_color1: (x + y) % 2 === 0 });
        }
        return l;
    };
    const out = [];
    app.updateLayers = () => {}; app.renderLayers = () => {}; app.loadLayerToInputs = () => {};
    try {
        app._ingestCatalog(catalog);
        for (const c of cases) {
            const l = screen(c);
            app.project = { layers: [l], groups: [{ id: 'g1', name: 'G', layer_ids: [l.id] }],
                active_canvas_id: 'c1', cableUnit: 'ft',
                canvases: [{ id: 'c1', name: 'Canvas 1', workspace_x: 0, workspace_y: 0, show_workspace_x: 0,
                    show_workspace_y: 0, raster_width: 8192, raster_height: 8192, show_raster_width: 8192,
                    show_raster_height: 8192, color: '#ff0000', visible: true }] };
            l.group_id = c.grouped ? 'g1' : null;
            if (!c.grouped) app.project.groups = [];
            app.currentLayer = null; app.selectedLayerIds = new Set();
            r.viewMode = 'pixel-map'; r.zoom = 1; r.panX = 0; r.panY = 0;
            const texts = [];
            const ctx = r.ctx, fill = ctx.fillText;
            ctx.fillText = function (t, x, y, w) { texts.push(String(t)); return fill.call(ctx, t, x, y, w); };
            try { r.render(); } finally { ctx.fillText = fill; }
            const half = l.panels.find(p => p.halfTile !== 'none');
            // the label's line, rejoined where a narrow wall wraps it
            const at = texts.findIndex(t => t.startsWith('Weight '));
            const label = at < 0 ? null
                : (texts[at].endsWith('/') ? `${texts[at]} ${texts[at + 1]}` : texts[at]);
            out.push({ half: half ? app.getPanelWeightKg(l, half) : null,
                       layerKg: app.getLayerWeightKg(l),
                       group: c.grouped ? app.getGroupTotals(app.project.groups[0]).weightKg : null,
                       label });
        }
    } finally {
        app._panelCatalog = keep.catalog; app._panelCatalogFlat = keep.flat; app._halfWeightCache = keep.cache;
        Object.assign(app, { project: keep.project, currentLayer: keep.currentLayer, selectedLayerIds: keep.selected,
            updateLayers: keep.updateLayers, renderLayers: keep.renderLayers, loadLayerToInputs: keep.loadLayerToInputs });
        Object.assign(r, { viewMode: keep.viewMode, zoom: keep.zoom, panX: keep.panX, panY: keep.panY });
        r.render();
    }
    return out;
}"""


def _label(kg):
    return f'Weight {kg:,.1f} kg / {kg * 2.20462:,.1f} lb'


def test_a_half_tile_weighs_its_librarys_half_where_one_matches_perfectly(page):
    pg, errors = page
    cases = [
        {'halve': 'height'},                                   # Foo: 7.5 kg
        {'halve': 'height', 'panel_weight': 28.66, 'weight_unit': 'lb'},   # Foo in lb (13 kg)
        {'halve': 'height', 'grouped': True},                  # the group's totals too
        {'halve': 'width'},                                    # no 250 x 1000 half
        {'halve': 'height', 'panel_weight': 14},               # Bar: Baz is another series
        {'halve': 'height', 'panel_weight': 15},               # Qux: its half's pitch differs
        {'halve': 'height', 'panel_weight': 16},               # Zed: 499 is not half of 1000
        {'halve': 'height', 'panel_weight': 12},               # Twin / Twain: two halves disagree
        {'halve': 'height', 'panel_weight': 13.5},             # typed by hand: no model
        {'halve': 'height', 'cabinet_width': 192},             # 13 kg but not Foo's pixels
    ]
    out = pg.evaluate(HALF_JS, [CATALOG, cases])
    foo, foo_lb, grouped, width, bar, qux, zed, twin, typed, pixels = out
    assert foo['half'] == pytest.approx(7.5)
    assert foo['layerKg'] == pytest.approx(41.0)                       # 2 x 13 + 2 x 7.5
    assert foo['label'] == _label(41.0), foo
    assert foo_lb['half'] == pytest.approx(7.5) and foo_lb['layerKg'] == pytest.approx(2 * 28.66 / 2.20462 + 15)
    assert grouped['group'] == pytest.approx(41.0) and grouped['label'] == _label(41.0), grouped
    assert width['half'] == pytest.approx(0.65 * 13) and width['layerKg'] == pytest.approx(42.9)
    assert width['label'] == _label(42.9), width
    for c, full in ((bar, 14), (qux, 15), (zed, 16), (twin, 12), (typed, 13.5), (pixels, 13)):
        assert c['half'] == pytest.approx(0.65 * full), (full, c)
        assert c['layerKg'] == pytest.approx(2 * full + 2 * 0.65 * full), (full, c)
    assert errors == []


COUNT_JS = """async () => {
    const app = window.app;
    const keep = { catalog: app._panelCatalog, flat: app._panelCatalogFlat, cache: app._halfWeightCache };
    try {
        app._ingestCatalog(await (await fetch('/static/data/panel_catalog.json')).json());
        const pairs = [];
        for (const mfr of Object.keys(app._panelCatalog)) {
            for (const F of app._panelCatalog[mfr]) {
                for (const axis of ['height', 'width']) {
                    const kg = app._catalogHalfOf(mfr, F, axis);
                    if (kg !== null) pairs.push({ mfr, full: F, axis, kg });
                }
            }
        }
        return { pairs, catalog: app._panelCatalog };
    } finally {
        app._panelCatalog = keep.catalog; app._panelCatalogFlat = keep.flat; app._halfWeightCache = keep.cache;
    }
}"""


def test_the_shipped_library_pairs_only_true_halves(page):
    """The library as shipped: every pair the rule finds is the same
    manufacturer's, exactly half on the halved axis and equal on the
    other in mm and pixels, the same pitch, and named as one series; and
    there are plenty of them (262 full models in October 2026)."""
    pg, _ = page
    out = pg.evaluate(COUNT_JS)
    assert len(out['pairs']) > 100, len(out['pairs'])
    size = re.compile(r'\(?\b(full|half)\s*-?\s*(tile|panel|size)?\b\)?|\(?\b\d+(\.\d+)?\s*[x×]\s*\d+(\.\d+)?\)?', re.I)
    for p in out['pairs']:
        F = p['full']
        halves = [H for H in out['catalog'][p['mfr']] if H.get('weight_kg') == p['kg'] and H is not F
                  and H['pitch_mm'] == F['pitch_mm']]
        ok = False
        for H in halves:
            if p['axis'] == 'height':
                dims = (H['width_mm'] == F['width_mm'] and H['height_mm'] * 2 == F['height_mm']
                        and H['pixels_w'] == F['pixels_w'] and H['pixels_h'] * 2 == F['pixels_h'])
            else:
                dims = (H['height_mm'] == F['height_mm'] and H['width_mm'] * 2 == F['width_mm']
                        and H['pixels_h'] == F['pixels_h'] and H['pixels_w'] * 2 == F['pixels_w'])
            series = lambda n: re.sub(r'\s+', ' ', size.sub(' ', n)).strip().lower()  # noqa: E731
            ok = ok or (dims and series(H['name']) == series(F['name']))
        assert ok, p


# ── 5. a custom run over its limit says by how much ──────────────────────

READOUT_JS = """async (o) => {
    const app = window.app, r = window.canvasRenderer;
    await Promise.all([...(app._inflightLayerPuts || [])]);
    let project = await (await fetch('/api/project')).json();
    project.layers = []; project.groups = [];
    await fetch('/api/project', { method: 'PUT', headers: {'Content-Type': 'application/json'},
                                  body: JSON.stringify(project) });
    await fetch('/api/layer/add', { method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ name: 'Wide', columns: 28, rows: 6, cabinet_width: 128, cabinet_height: 128 }) });
    app.project = await (await fetch('/api/project')).json();
    app.dedupeProjectLayers('rulings_1018_readout');
    const l = app.project.layers.find(x => (x.type || 'screen') === 'screen');
    Object.assign(l, { flowPattern: 'custom', processorType: o.processor, bitDepth: 8, frameRate: 60,
                       lowLatency: false, customPortIndex: 1, customPortOverrides: [] });
    l.customPortPaths = { 1: o.cells.map(([row, col]) => ({ row, col })) };
    app.currentLayer = l;
    app.selectedLayerIds = new Set([l.id]);
    if (app.customSelection) app.customSelection.clear();
    r.viewMode = 'data-flow';
    app.loadLayerToInputs();
    app._syncCustomFillReadout('data');
    const el = document.getElementById('custom-fill-readout');
    const fill = app.customRunFill(l, 'data', 1);
    return { text: el.textContent, color: el.style.color, load: fill.load, limit: fill.limit,
             full: fill.full, over: fill.over, cab: app.getFullPanelPixels(l) };
}"""


def test_an_armor_run_over_its_port_says_by_how_much_in_red(page):
    pg, errors = page
    # the L: the top row, then down the left side - the rectangle round it
    # is the whole 28 x 6 wall
    cells = [(0, c) for c in range(28)] + [(r, 0) for r in range(1, 6)]
    out = pg.evaluate(READOUT_JS, {'processor': 'novastar-armor', 'cells': cells})
    assert out['cab'] == 128 * 128
    assert out['load'] == 168 * 128 * 128 == 2752512, out
    assert out['load'] > out['limit'] and out['over'] is True, out
    by = round(out['load']) - round(out['limit'])
    want = (f"over by {by:,} px ({round(out['load']):,} / {round(out['limit']):,} px)")
    assert out['text'].endswith(want) and out['text'].startswith('Port '), out['text']
    assert '· full' not in out['text'], out['text']
    assert out['color'] in ('rgb(255, 107, 107)', '#ff6b6b'), out['color']
    # at or under the limit it reads as it always did: a short run is not
    # full, a run that cannot grow is "· full" in amber
    short = pg.evaluate(READOUT_JS, {'processor': 'novastar-armor', 'cells': [(0, 0), (0, 1)]})
    assert short['over'] is False and 'over by' not in short['text'] and '· full' not in short['text'], short
    assert re.fullmatch(r'Port \S+: 2/\d+ panels \(.+ px/port\)', short['text']), short['text']
    assert errors == []


def test_a_run_at_its_limit_still_reads_full(page):
    """A Brompton run (the sum of its cabinets) filled to its limit is
    "· full", amber - not over."""
    pg, _ = page
    probe = pg.evaluate(READOUT_JS, {'processor': 'brompton', 'cells': [(0, 0)]})
    n = int(probe['limit'] // probe['cab'])
    cells = [(r, c) for r in range(6) for c in range(28)][:n]
    out = pg.evaluate(READOUT_JS, {'processor': 'brompton', 'cells': cells})
    assert out['over'] is False and out['full'] is True, out
    assert out['text'].endswith(')') and '· full (' in out['text'] and 'over by' not in out['text'], out['text']
    assert out['color'] in ('rgb(255, 204, 0)', '#ffcc00'), out['color']
