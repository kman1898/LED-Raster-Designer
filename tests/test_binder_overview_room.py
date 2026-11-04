"""The binder's Overview (sheet 1.1): tables across the top, the drawing
under them.

"we have a ton of wasted space on page 1", "always prefer a bigger
drawing", then "Tables across the top" and "can also split the page
content into two columns" (owner, 2026-11-02). On a Tabloid sheet of a
real show the CONTENTS ran 30-odd rows down the right of the POSITIONS and
SHOW TOTALS tables, and the drawing stood under it, small at the sheet's
foot, with the room under the two short tables empty.

  * POSITIONS, SHOW TOTALS and CONTENTS share one band across the top,
    the CONTENTS split, in order, into as many columns of balanced height
    as draw the map largest ("CONTENTS 1", "CONTENTS 2"); where more
    columns gain the map nothing, the fewest. Nothing in the band is cut
    and every sheet is listed, at the table's type size.
  * The drawing takes the whole width under the band, as large as it
    fits, centered; the "1 OVERVIEW" bubble just under it.
  * Every table is measured in the column it is painted in. Measured in
    the narrower COL_W, CONTENTS titles that print on one line were given
    a second line's height they never used.

The show here is synthetic, the real show's shape: six screens on three
canvases (Center: two 18 x 4; Outboards: two 9 x 4; Upstage: two 11 x 4,
grouped) of 192 x 384 cabinets, a processor per screen, one distro on a
service - a 30-sheet binder.

Run locally:
    "/c/Users/Blue Iris/.venvs/led-raster/Scripts/python.exe" -m pytest tests/test_binder_overview_room.py -p no:cacheprovider --browser chromium
"""

import math
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# The sheet (app-binder.js): Tabloid at 200 px/in, the border PAD in, the
# title block TB_W wide inside it, the drawing area DA_PAD in from both.
W, H = 3400, 2200
PAD, TB_W, DA_PAD = 50, 480, 30
COL_W, COL_GAP, BUBBLE_H = 700, 30, 96
H4_H, TH_H, ROW_H, LIST_H = 46, 40, 38, 30
SZ_CELL = 24
MAP_ZOOM_CAP = 3
SHEETS = {'tabloid': (3400, 2200), 'letter': (2200, 1700), 'a3': (3308, 2338), 'archd': (7200, 4800)}

# The drawing on dev/draft b4ee7cb, before this change, for this very show
# on Tabloid: under the CONTENTS across the width, 1499 x 598 page px.
BEFORE = (1499, 598)


def _da(w, h, block=True):
    return {'x': PAD + DA_PAD, 'y': PAD + DA_PAD,
            'w': w - PAD * 2 - (TB_W if block else 0) - DA_PAD * 2,
            'h': h - PAD * 2 - DA_PAD * 2}


SEED_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method, headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.binder; delete proj.services;
    await j('PUT', '/api/project', proj);
    const add = (name, columns, offset_x) => j('POST', '/api/layer/add', {name, columns, rows: 4,
        cabinet_width: 192, cabinet_height: 384, powerVoltage: 208, powerAmperage: 20, panelWatts: 300,
        powerFlowPattern: 'tl-h', powerOrganized: true, flowPattern: 'tl-h', processorType: 'novastar-armor',
        offset_x});
    const specs = [['Left Column', 9, 0, 'c2'], ['Right Column', 9, 1728, 'c2'],
                   ['Center Left', 18, 0, 'c1'], ['Center Right', 18, 3456, 'c1'],
                   ['Upstage Left', 11, 0, 'c3'], ['Upstage Right', 11, 2112, 'c3']];
    for (const [n, c, x] of specs) await add(n, c, x);
    const p = await j('GET', '/api/project');
    const cv = (id, name, w, x, y) => ({ id, name, color: '#4A90E2', raster_width: w, raster_height: 1344,
        show_raster_width: w, show_raster_height: 1344, workspace_x: x, workspace_y: y, visible: true,
        data_flow_perspective: 'front', power_perspective: 'front' });
    // the Center canvas over the Outboards and the Upstage, side by side
    p.canvases = [cv('c1', 'Center', 6912, 8091, -1344), cv('c2', 'Outboards', 3456, 7680, 0),
                  cv('c3', 'Upstage', 4224, 11136, 0)];
    p.active_canvas_id = 'c1';
    for (const [n, , , cid] of specs) p.layers.find(l => l.name === n).canvas_id = cid;
    const ul = p.layers.find(l => l.name === 'Upstage Left'), ur = p.layers.find(l => l.name === 'Upstage Right');
    p.groups = [{ id: 'g1', name: 'Upstage', layer_ids: [ul.id, ur.id], routeDataAsOne: false }];
    await j('PUT', '/api/project', p);
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('overview_room');
    const L = (n) => app.project.layers.find(l => l.name === n);
    // a processor per screen, each with one card
    for (const [name] of specs) {
        let st = await j('POST', '/api/processors', {deviceId: 'novastar-h9'});
        const proc = st.processors[st.processors.length - 1];
        st = await j('PUT', `/api/processors/${proc.id}/slots/0`, {deviceId: 'novastar-card-h-16xrj45-2xfiber'});
        const cardId = st.processors.find(q => q.id === proc.id).slots[0].card.id;
        await j('PUT', `/api/processors/${proc.id}`, {name: name.toUpperCase()});
        await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
                                     {layerId: String(L(name).id), cardId});
    }
    // one distro, every screen's first multi on it, on one service
    app.selectLayer(L('Left Column'));
    const d = app.addDistro({name: 'S'});
    let n = 1;
    for (const l of app.project.layers) {
        app.setSocaDistro(l, 1, d.id); app.setSocaNumber(l, 1, n++); app.setSocaLength(l, 1, '100');
    }
    await Promise.all([...(app._inflightLayerPuts || [])]);
    app.project.services = [{ id: 's1', name: 'VX', ratingA: 400, system: d.system,
                              voltage: d.voltage, phase: d.phase }];
    d.serviceId = 's1';
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    window.canvasRenderer.render();
    return app.project.layers.length;
}"""

OPTS = {'sheet': 'tabloid', 'palette': 'colour', 'sides': {'power': True, 'data': True},
        'scope': {'kind': 'show'}, 'cover': True, 'pull': True, 'hardware': True, 'titleBlock': True}

OVERVIEW_JS = """(opts) => {
    const app = window.app;
    const plan = app.planBinder(opts);
    const r = app.renderBinderPage(opts, 0);
    return { plan: plan.map(p => [p.number, p.sheetTitle]), page: plan[0], map: r.map, bubble: r.bubble,
             titleBlock: r.titleBlock, texts: r.texts,
             ops: r.record.ops.filter(o => o.op === 'text' || o.op === 'image') };
}"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    pg.wait_for_function("() => window.app && window.app.project && window.canvasRenderer")
    assert pg.evaluate(SEED_JS) == 6
    yield pg, errors
    context.close()


def _overview(pg, **over):
    out = pg.evaluate(OVERVIEW_JS, {**OPTS, **over})
    assert out['page']['kind'] == 'overview' and out['map'], out['page']
    return out


def _disjoint(a, b):
    return (a['x'] + a['w'] <= b['x'] or b['x'] + b['w'] <= a['x']
            or a['y'] + a['h'] <= b['y'] or b['y'] + b['h'] <= a['y'])


def test_the_tables_share_a_band_and_the_drawing_takes_the_width(page):
    """On this 30-sheet binder the CONTENTS splits into two columns, beside
    POSITIONS over SHOW TOTALS: the band is as short as the two halves,
    and the drawing under it is the sheet's whole width (its height to
    spare: it is stopped by the width), centered, the bubble just under
    it - about 3.4 x the area it had before (1499 x 598 page px)."""
    pg, errors = page
    out = _overview(pg)
    m, da = out['map'], _da(W, H)
    band = m['band']
    assert len(out['plan']) >= 30, len(out['plan'])
    assert band['contentsCols'] == 2 and band['layout'] == 'stacked', band
    # the band: POSITIONS over SHOW TOTALS in the first column, the two
    # CONTENTS columns beside them, each ending above the drawing
    heads = [o for o in out['ops'] if o['op'] == 'text' and o['weight'] == 700
             and o['text'] in ('POSITIONS', 'SHOW TOTALS', 'CONTENTS 1', 'CONTENTS 2')]
    at = {o['text']: (o['x'], o['y']) for o in heads}
    assert at['POSITIONS'][0] == at['SHOW TOTALS'][0] < at['CONTENTS 1'][0] < at['CONTENTS 2'][0], at
    assert at['POSITIONS'][1] == at['CONTENTS 1'][1] == at['CONTENTS 2'][1] < at['SHOW TOTALS'][1], at
    assert band['h'] == max(t['h'] for t in m['tables']), (band, m['tables'])
    # the halves balanced: the CONTENTS columns within two rows of each other
    assert abs(m['tables'][1]['h'] - m['tables'][2]['h']) <= 2 * ROW_H, m['tables']
    area = m['area']
    assert area == {'x': da['x'], 'y': da['y'] + band['h'] + COL_GAP, 'w': da['w'],
                    'h': da['y'] + da['h'] - BUBBLE_H - (da['y'] + band['h'] + COL_GAP)}, area
    # the whole width, centered in the height it leaves
    assert m['x'] == da['x'] and m['w'] == da['w'], m
    assert m['h'] <= area['h'] and abs((m['y'] - area['y']) - (area['y'] + area['h'] - m['y'] - m['h'])) <= 1, m
    assert m['zoom'] < MAP_ZOOM_CAP
    # the gain over the drawing before this change
    assert m['w'] * m['h'] >= 2.5 * BEFORE[0] * BEFORE[1], (m, BEFORE)
    b = out['bubble']
    assert 0 <= (b['y'] - b['r']) - (m['y'] + m['h']) <= 20, (b, m)
    assert errors == []


def _contents_rows(out):
    """The CONTENTS rows as painted, column after column: each row's sheet
    number, its height and the lines of its title, read off the sheet's
    text ops."""
    ops = [o for o in out['ops'] if o['op'] == 'text']
    heads = [o for o in ops if o['weight'] == 700 and re.fullmatch(r'CONTENTS( \d+)?', o['text'])]
    names = [o['text'] for o in heads]
    assert names == (['CONTENTS'] if len(heads) == 1 else [f'CONTENTS {i + 1}' for i in range(len(heads))]), names
    numbers = {n for n, _t in out['plan']}
    rows = []
    for head in heads:
        col = next((t for t in out['map']['tables'] if t['x'] - 0.5 <= head['x'] < t['x'] + t['w']), None)
        assert col, (head, out['map']['tables'], out['map']['band'])
        inside = [o for o in ops if col['x'] - 0.5 <= o['x'] < col['x'] + col['w'] and o['y'] > head['y']
                  and o['y'] < col['y'] + col['h'] and o['text'] not in ('SHEET', 'TITLE')]
        nums = sorted((o for o in inside if o['text'] in numbers and re.fullmatch(r'\d+\.\d+', o['text'])),
                      key=lambda o: o['y'])
        titles = [o for o in inside if o not in nums]
        for i, o in enumerate(nums):
            top = o['y'] - 27
            bottom = nums[i + 1]['y'] - 27 if i + 1 < len(nums) else col['y'] + col['h']
            lines = sorted((t for t in titles if top <= t['y'] < bottom), key=lambda t: t['y'])
            rows.append({'number': o['text'], 'h': bottom - top, 'lines': lines})
    return rows


def _check_contents(out, where):
    """Every sheet of the plan listed, in order, column after column; each
    title whole, at the table's type size, its row exactly as tall as the
    lines it prints."""
    rows = _contents_rows(out)
    assert [r['number'] for r in rows] == [n for n, _t in out['plan']], (where, [r['number'] for r in rows])
    for r, (_n, title) in zip(rows, out['plan']):
        assert r['lines'], (where, r)
        assert ' '.join(t['text'] for t in r['lines']) == title, (where, r['number'], r['lines'], title)
        assert all(abs(t['size'] - SZ_CELL) < 0.01 for t in r['lines']), (where, r['number'], r['lines'])
        assert math.isclose(r['h'], ROW_H + (len(r['lines']) - 1) * LIST_H, abs_tol=0.5), \
            (where, r['number'], r['h'], [t['text'] for t in r['lines']])
    return rows


def _check_sheet(out, da, tb_x, where):
    """Nothing on the overview overlaps: the band of tables at the top, the
    drawing under it across the drawing area's whole width, as large as it
    fits and clear of the title block; the bubble just under the drawing,
    inside the area; every screen inside the drawing."""
    m = out['map']
    tables = m['tables']
    band = m['band']
    area = m['area']
    draw = {'x': m['x'], 'y': m['y'], 'w': m['w'], 'h': m['h']}
    assert area['x'] == da['x'] and area['w'] == da['w'], (where, area, da)
    for t in tables:
        assert t['y'] == da['y'] and t['h'] <= band['h'], (where, t, band)
        assert t['y'] + t['h'] + COL_GAP <= area['y'] <= draw['y'], (where, t, area, draw)
        assert _disjoint(draw, t), (where, draw, t)
        assert t['x'] + t['w'] <= tb_x, (where, t, tb_x)
    assert draw['x'] >= da['x'] - 0.5 and draw['x'] + draw['w'] <= da['x'] + da['w'] + 0.5, (where, draw, da)
    assert draw['y'] + draw['h'] <= da['y'] + da['h'] - BUBBLE_H + 1, (where, draw, da)
    assert draw['x'] + draw['w'] <= tb_x, (where, draw, tb_x)
    # as large as it fits its room
    assert (m['zoom'] >= MAP_ZOOM_CAP - 1e-6 or abs(draw['w'] - area['w']) <= 1
            or abs(draw['h'] - area['h']) <= 1), (where, draw, area)
    for sc in m['screens']:
        assert draw['x'] - 0.01 <= sc['x'] and sc['x'] + sc['w'] <= draw['x'] + draw['w'] + 0.01, (where, sc, draw)
        assert draw['y'] - 0.01 <= sc['y'] and sc['y'] + sc['h'] <= draw['y'] + draw['h'] + 0.01, (where, sc, draw)
    b = out['bubble']
    assert b['number'] == 1 and b['name'] == 'OVERVIEW', (where, b)
    circle = {'x': b['x'] - b['r'], 'y': b['y'] - b['r'], 'w': 2 * b['r'], 'h': 2 * b['r']}
    assert 0 <= circle['y'] - (draw['y'] + draw['h']) <= 20, (where, b, draw)
    assert circle['y'] + circle['h'] <= da['y'] + da['h'] + 1 and circle['x'] >= da['x'], (where, b, da)
    images = [o for o in out['ops'] if o['op'] == 'image']
    for im in images:
        assert abs(im['x'] - draw['x']) < 1 and abs(im['y'] - draw['y']) < 1, (where, im, draw)


def test_nothing_on_the_overview_overlaps_or_is_cut_on_any_sheet(page):
    """On Tabloid, Letter, A3 and ARCH D, with the title block on and
    off: the band above the drawing, nothing overlapping, every sheet in
    the CONTENTS, nothing cut or shrunk."""
    pg, errors = page
    for sheet, (w, h) in SHEETS.items():
        for block in (True, False):
            where = (sheet, block)
            out = _overview(pg, sheet=sheet, titleBlock=block)
            da = _da(w, h, block)
            tb_x = w - PAD - (TB_W if block else 0)
            assert out['page']['layout'] == 'overview', (where, out['page'])
            _check_sheet(out, da, tb_x, where)
            _check_contents(out, where)
    assert errors == []


def test_every_contents_row_is_as_tall_as_its_title(page):
    """A CONTENTS row is one line's height unless its title really wraps
    where it is painted: the table is measured in the column it is drawn
    in. Most titles print on one line; POSITIONS' "Upstage Left, Upstage
    Right" fits its column."""
    pg, errors = page
    out = _overview(pg)
    rows = _check_contents(out, 'tabloid')
    assert sum(1 for r in rows if len(r['lines']) == 1) >= len(rows) - 3, rows
    p = out['texts'].index('POSITIONS')
    assert 'Upstage Left, Upstage Right' in out['texts'][p:], out['texts'][p:p + 30]
    assert errors == []
