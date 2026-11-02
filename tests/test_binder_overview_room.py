"""The binder's Overview (sheet 1.1): the drawing takes the free room.

"we have a ton of wasted space on page 1" - and, asked how to use it,
"always prefer a bigger drawing" (owner, 2026-11-02). On a Tabloid sheet
of a real show the CONTENTS ran 30-odd rows down the right of the
POSITIONS and SHOW TOTALS tables, and the overview's drawing stood under
the CONTENTS, across the whole width, small at the sheet's foot: the
room under the two short tables, half the sheet, stayed empty.

  * The drawing stands in whichever room the tables leave draws it
    largest: a run of side-by-side columns from below its tallest table
    to the bubble's room at the foot. Under the short tables, left of the
    CONTENTS, wins on a long binder; under every table, across the whole
    width, wins on a short one (test_binder.py's overview tests). Centered
    in its room, at its own proportions. The tables keep their size and
    their place.
  * Every table is measured in the column it is painted in. Measured in
    the narrower COL_W, two CONTENTS titles that print on one line were
    given a second line's height they never used, and on that real show
    the taller column then lost its last two sheets to the half-height
    cap.

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
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
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


def _rooms(da, tables):
    """Every room the tables leave, the way the sheet lays its columns:
    each run of side-by-side columns, from below its tallest table to
    the bubble's room at the foot."""
    across = max(1, (da['w'] + COL_GAP) // (COL_W + COL_GAP))
    wide = (da['w'] - (across - 1) * COL_GAP) / across
    col_x = [da['x'] + i * (wide + COL_GAP) for i in range(across)]
    heights = [0] * across
    for t in tables:
        i = min(range(across), key=lambda k: abs(col_x[k] - t['x']))
        heights[i] = t['h']
    rooms = []
    for i in range(across):
        for j in range(i, across):
            top = max(heights[i:j + 1])
            y = da['y'] + top + (COL_GAP if top else 0)
            rooms.append({'x': col_x[i], 'y': y, 'w': col_x[j] + wide - col_x[i],
                          'h': da['y'] + da['h'] - BUBBLE_H - y, 'from': i, 'to': j})
    return rooms


def _fit_area(room, aspect):
    """The area a drawing of this aspect (w / h) takes, as large as fits."""
    if room['h'] <= 0:
        return 0
    w = min(room['w'], room['h'] * aspect)
    return w * w / aspect


def test_the_overview_drawing_takes_the_larger_free_room(page):
    """On this 30-sheet binder the CONTENTS runs most of the way down the
    right of the tables: the room under POSITIONS and SHOW TOTALS, left of
    the CONTENTS, draws the show larger than the room under the CONTENTS,
    and the drawing stands there - as large as it fits, centered. It is
    about 1.5 x the area it had before (1499 x 598 page px); the drawing's
    own proportions (about 2.5 : 1) stop it at the room's width, so the
    gain is not more."""
    pg, errors = page
    out = _overview(pg)
    m, da = out['map'], _da(W, H)
    tables = m['tables']
    assert len(tables) == 3 and len(out['plan']) >= 30, (tables, len(out['plan']))
    # the CONTENTS is the tall column, the two short tables beside it
    assert tables[2]['h'] > 2 * max(tables[0]['h'], tables[1]['h']), tables
    assert m['placement'] == {'from': 0, 'to': 1, 'fullWidth': False}, m['placement']
    area = m['area']
    assert area['x'] == da['x'] and area['w'] == tables[1]['x'] + tables[1]['w'] - da['x'], area
    assert area['y'] == da['y'] + max(tables[0]['h'], tables[1]['h']) + COL_GAP, area
    assert area['y'] + area['h'] == da['y'] + da['h'] - BUBBLE_H, area
    # the largest of the rooms, and larger than the old one (under every
    # table, across the width)
    aspect = m['w'] / m['h']
    rooms = _rooms(da, tables)
    best = max(_fit_area(r, aspect) for r in rooms)
    full = next(r for r in rooms if r['from'] == 0 and r['to'] == 2)
    assert m['w'] * m['h'] >= best * 0.99, (m, best)
    assert m['w'] * m['h'] > _fit_area(full, aspect) * 1.03, (m, full)
    # as large as it fits: stopped by the room's width, centered in it
    assert m['zoom'] < MAP_ZOOM_CAP
    assert abs(m['w'] - area['w']) <= 1 or abs(m['h'] - area['h']) <= 1, (m, area)
    assert abs((m['x'] - area['x']) - (area['x'] + area['w'] - m['x'] - m['w'])) <= 1, (m, area)
    assert abs((m['y'] - area['y']) - (area['y'] + area['h'] - m['y'] - m['h'])) <= 1, (m, area)
    # the gain over the drawing before this change
    assert m['w'] * m['h'] >= 1.25 * BEFORE[0] * BEFORE[1], (m, BEFORE)
    assert errors == []


def _check_sheet(out, da, tb_x):
    """Nothing on the overview overlaps: the drawing in the drawing area,
    clear of every table and of the title block; the bubble under the
    drawing, inside the area, clear of the tables; every screen inside the
    drawing; every table at the top of its column, as it always was."""
    m = out['map']
    tables = m['tables']
    draw = {'x': m['x'], 'y': m['y'], 'w': m['w'], 'h': m['h']}
    assert draw['x'] >= da['x'] - 0.5 and draw['x'] + draw['w'] <= da['x'] + da['w'] + 0.5, (draw, da)
    assert draw['y'] >= da['y'] and draw['y'] + draw['h'] <= da['y'] + da['h'] - BUBBLE_H + 1, (draw, da)
    assert draw['x'] + draw['w'] <= tb_x, (draw, tb_x)
    for t in tables:
        assert t['y'] == da['y'], t
        assert _disjoint(draw, t), (draw, t)
    for sc in m['screens']:
        assert draw['x'] - 0.01 <= sc['x'] and sc['x'] + sc['w'] <= draw['x'] + draw['w'] + 0.01, (sc, draw)
        assert draw['y'] - 0.01 <= sc['y'] and sc['y'] + sc['h'] <= draw['y'] + draw['h'] + 0.01, (sc, draw)
    b = out['bubble']
    assert b['number'] == 1 and b['name'] == 'OVERVIEW', b
    circle = {'x': b['x'] - b['r'], 'y': b['y'] - b['r'], 'w': 2 * b['r'], 'h': 2 * b['r']}
    assert circle['y'] >= draw['y'] + draw['h'], (b, draw)
    assert circle['y'] + circle['h'] <= da['y'] + da['h'] + 1, (b, da)
    assert circle['x'] >= da['x'], (b, da)
    # the bubble's line: the circle and its name, about 340 px wide
    line = {'x': circle['x'], 'y': circle['y'], 'w': 340, 'h': circle['h']}
    for t in tables:
        assert _disjoint(line, t), (b, t)
    # the image op is the drawing
    images = [o for o in out['ops'] if o['op'] == 'image']
    for im in images:
        assert abs(im['x'] - draw['x']) < 1 and abs(im['y'] - draw['y']) < 1, (im, draw)


def test_nothing_on_the_overview_overlaps_on_any_sheet(page):
    """The drawing and its bubble keep clear of every table and of the
    title block, on every sheet size and with the title block off, and
    always stand in the largest room."""
    pg, errors = page
    for sheet, (w, h) in SHEETS.items():
        for block in (True, False):
            out = _overview(pg, sheet=sheet, titleBlock=block)
            da = _da(w, h, block)
            tb_x = w - PAD - (TB_W if block else 0)
            assert out['page']['layout'] == 'overview', (sheet, out['page'])
            _check_sheet(out, da, tb_x)
            m = out['map']
            if m['zoom'] < MAP_ZOOM_CAP - 1e-6:
                best = max(_fit_area(r, m['w'] / m['h']) for r in _rooms(da, m['tables']))
                assert m['w'] * m['h'] >= best * 0.99, (sheet, block, m, best)
    assert errors == []


def _contents_rows(out):
    """The CONTENTS rows as painted: each row's top, its height, its sheet
    number and the lines of its title, read off the sheet's text ops."""
    ops = [o for o in out['ops'] if o['op'] == 'text']
    head = next(o for o in ops if o['text'] == 'CONTENTS')
    col = next(t for t in out['map']['tables'] if t['x'] <= head['x'] < t['x'] + t['w'])
    numbers = {n for n, _t in out['plan']}
    inside = [o for o in ops if col['x'] <= o['x'] < col['x'] + col['w'] and o['y'] > head['y']
              and o['text'] not in ('SHEET', 'TITLE')]
    nums = sorted((o for o in inside if o['text'] in numbers and re.fullmatch(r'\d+\.\d+', o['text'])),
                  key=lambda o: o['y'])
    titles = [o for o in inside if o not in nums]
    rows = []
    for i, o in enumerate(nums):
        top = o['y'] - 27
        bottom = nums[i + 1]['y'] - 27 if i + 1 < len(nums) else col['y'] + col['h']
        lines = sorted((t for t in titles if top <= t['y'] < bottom), key=lambda t: t['y'])
        rows.append({'number': o['text'], 'top': top, 'h': bottom - top, 'lines': lines})
    return rows


def test_every_contents_row_is_as_tall_as_its_title(page):
    """A CONTENTS row is one line's height unless its title really wraps
    where it is painted: the table is measured in the column it is drawn
    in. Every sheet of the plan is listed, in order, its title whole and
    at the table's type size - nothing cut, nothing shrunk."""
    pg, errors = page
    out = _overview(pg)
    rows = _contents_rows(out)
    assert [r['number'] for r in rows] == [n for n, _t in out['plan']], rows
    for r, (_n, title) in zip(rows, out['plan']):
        assert r['lines'], r
        assert ' '.join(t['text'] for t in r['lines']) == title, (r['number'], r['lines'], title)
        assert all(abs(t['size'] - SZ_CELL) < 0.01 for t in r['lines']), (r['number'], r['lines'])
        assert math.isclose(r['h'], ROW_H + (len(r['lines']) - 1) * LIST_H, abs_tol=0.5), \
            (r['number'], r['h'], [t['text'] for t in r['lines']])
    # most titles print on one line
    assert sum(1 for r in rows if len(r['lines']) == 1) >= len(rows) - 3, rows
    # the POSITIONS rows: one line each - "Upstage Left, Upstage Right"
    # fits its column
    p = out['texts'].index('POSITIONS')
    assert 'Upstage Left, Upstage Right' in out['texts'][p:], out['texts'][p:p + 30]
    assert errors == []
