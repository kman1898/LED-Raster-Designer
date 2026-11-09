"""A wide, short wall's sheets give the room beside and under the wall to
the wall (2026-11-08, on a 16 x 5 wall of 500 x 1000 mm panels printed on
Letter with the title block off: "why on this export are the margins so
large? we can fit so much more here i feel like?" / "there is just a ton
of room in the margins top and bottom and the sides too").

Two causes, two fixes:

- THE TABLES WERE STRETCHED TO 3.5 IN whatever they held (COL_W). Under a
  wide wall only two such columns fit across a Letter sheet, so the four
  power tables stood two by two, the taller pair setting the height the
  wall lost, and a third of the sheet's width sat empty beside the wall -
  too narrow for one more 3.5 in column. _bMapLayout now also tries the
  tables at their own width (_bNaturalColW: every cell, band and heading
  on one line) and takes that set where its wall is NARROW_GAIN (3 per
  cent) larger: here three columns under the wall and the wall about a
  quarter larger, on the Power sheet and the Data sheet alike (a screen's
  Power and Data walls the same size where possible).
- WITH THE TITLE BLOCK OFF the drawing kept the border's inset though no
  border is drawn: 0.4 in of blank paper all round. It now runs to the
  quarter inch (PAD), the ink's edge with the block on as well.

Run locally:
    python -m pytest tests/test_binder_wide_wall_room.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from conftest import open_app  # noqa: E402

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

# Letter landscape in page units (200 px/in); the border's quarter inch.
LETTER_W, LETTER_H, PAD = 2200, 1700, 50
DA_PAD, TB_W = 30, 480
MAP_GUTTER = {'left': 200, 'right': 180, 'top': 74, 'bottom': 16}

# One screen, WALL-A: 16 x 5 of 500 x 1000 mm panels (192 x 384 px), 208 V
# circuits ganged through 3fers on one Socapex multi at 100', its ports on
# one H9 card - a wall 1.6 times as wide as it is tall, with four power
# tables (Circuits, Cables, Facts, Shared circuits) and three data tables.
SEED_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    // a raster that holds the whole wall (3072 x 1920): the renderer draws
    // nothing past the raster
    proj.raster_width = proj.show_raster_width = 3840; proj.raster_height = proj.show_raster_height = 2160;
    for (const c of proj.canvases || []) { c.raster_width = c.show_raster_width = 3840; c.raster_height = c.show_raster_height = 2160; }
    delete proj.port_assignments; delete proj.pullSheet; delete proj.binder;
    await j('PUT', '/api/project', proj);
    await j('POST', '/api/layer/add', {name: 'WALL-A', columns: 16, rows: 5,
        cabinet_width: 192, cabinet_height: 384, panel_width_mm: 500, panel_height_mm: 1000,
        powerVoltage: 208, powerAmperage: 20, panelWatts: 150,
        powerFlowPattern: 'tl-v', powerOrganized: true, flowPattern: 'tl-v',
        powerSplitters: {enabled: true, maxWays: 3, manual: {merge: [], split: []}},
        processorType: 'novastar-armor'});
    let st = await j('POST', '/api/processors', {deviceId: 'novastar-h9'});
    const pid = st.processors[0].id;
    st = await j('PUT', `/api/processors/${pid}/slots/0`, {deviceId: 'novastar-card-h-16xrj45-2xfiber'});
    const cardId = st.processors[0].slots[0].card.id;
    const p = await j('GET', '/api/project');
    app.project = p;
    app.dedupeProjectLayers('binder_wide_wall');
    const a = app.project.layers.find(l => l.name === 'WALL-A');
    app.selectLayer(a);
    const d = app.addDistro({name: 'S1'});
    app.setSocaDistro(a, 1, d.id); app.setSocaNumber(a, 1, 1); app.setSocaLength(a, 1, '100');
    await Promise.all([...(app._inflightLayerPuts || [])]);
    await app.refreshProcessors();
    await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
                                 {layerId: String(a.id), cardId});
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    window.canvasRenderer.render();
    app.resetHistory('Binder Wide Wall Seed');
    return { circuits: app.screenCircuits(a).length };
}"""

LETTER_PLAIN = {'sheet': 'letter', 'palette': 'printer', 'sides': {'power': True, 'data': True},
                'scope': {'kind': 'show'}, 'cover': False, 'pull': False, 'hardware': False,
                'wiring': False, 'fiber': False, 'rigging': False, 'titleBlock': False, 'view': 'rear'}
LETTER_BLOCK = {**LETTER_PLAIN, 'titleBlock': True}

PLAN_JS = """(opts) => {
    const app = window.app;
    const plan = app.planBinder(opts);
    return plan.map((p, i) => {
        if (!['power', 'data'].includes(p.kind)) return { kind: p.kind, title: p.title };
        const r = app.renderBinderPage(opts, i);
        const ops = (r.record && r.record.ops) || [];
        return { kind: p.kind, title: p.title, layout: p.layout, cols: p.cols, scale: p.scale,
                 map: r.map, bubble: r.bubble,
                 images: ops.filter(o => o.op === 'image').map(o => ({ x: o.x, y: o.y, w: o.w, h: o.h })),
                 texts: ops.filter(o => o.op === 'text').map(o => ({ t: o.text, x: o.x, y: o.y, size: o.size })) };
    });
}"""


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    open_app(pg, e2e_server)
    out = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(600)
    assert out['circuits'] >= 5, f'fixture: WALL-A should run on several circuits: {out}'
    yield pg, errors
    context.close()


def _sheets(pg, opts):
    return {s['kind']: s for s in pg.evaluate(PLAN_JS, opts) if s['kind'] in ('power', 'data')}


def test_the_power_tables_stand_three_across_and_the_wall_takes_the_room(page):
    """Letter, block off: the Power sheet lays its four tables three across
    under the wall at their own width (two 3.5 in columns before), and the
    wall draws about a quarter larger than it did: at least 1390 page units
    wide (1114 before the change, 1401 measured), the Data wall likewise
    (1279 before, 1576 measured). The Power wall keeps at least the share
    of the Data wall it had (0.87): the two stay the size they were
    against each other while both grow."""
    pg, errors = page
    s = _sheets(pg, LETTER_PLAIN)
    power, data = s['power'], s['data']
    assert power['layout'] == 'stack' and power['cols'] == 3, (power['layout'], power['cols'])
    m = power['map']
    assert m['w'] >= 1390 and abs(m['w'] / m['h'] - 1.6) < 0.01, m
    assert data['map']['w'] >= 1560, data['map']
    assert power['map']['w'] >= data['map']['w'] * 0.87, (power['map'], data['map'])
    # the tables never smaller than the base type
    assert power['scale'] >= 1 and data['scale'] >= 1, (power['scale'], data['scale'])
    assert not errors, errors


def test_the_tables_sit_under_the_wall_whole_and_at_full_size(page):
    """Nothing overlaps and nothing shrinks: every table text stands below
    the map's image, inside the quarter-inch margin, the tables in three
    columns that do not run into one another, and no cell or heading is
    set smaller than the base type at the sheet's scale (a narrower column
    never squeezes a cell: it is never under the table's own width)."""
    pg, _ = page
    for kind, sheet in _sheets(pg, LETTER_PLAIN).items():
        img = sheet['images'][0]
        foot = img['y'] + img['h']
        below = [t for t in sheet['texts'] if t['y'] > foot + 1]
        assert below, (kind, 'no table text under the map')
        for t in below:
            assert PAD <= t['x'] <= LETTER_W - PAD and t['y'] <= LETTER_H - PAD, (kind, t)
            # the heading row's 21 px is the smallest table type
            assert t['size'] >= 21 * sheet['scale'] - 0.05, (kind, t, sheet['scale'])
        heads = [t for t in below if t['t'] in ('CIRCUITS', 'CABLES THIS SCREEN', 'FACTS', 'SHARED CIRCUITS', 'PORTS')]
        xs = sorted({round(t['x']) for t in heads})
        assert len(xs) == 3 and xs[1] - xs[0] > 500 and xs[2] - xs[1] > 500, (kind, heads)


def test_with_the_title_block_off_the_drawing_runs_to_the_quarter_inch(page):
    """No border, no inset: the map's image starts at the quarter inch from
    the top and the left (0.4 in before), on every map sheet. With the
    block on, the border is the ink at the quarter inch and the drawing
    keeps its small inset inside it."""
    pg, _ = page
    for s in _sheets(pg, LETTER_PLAIN).values():
        img = s['images'][0]
        assert abs(img['y'] - PAD) < 0.5, (s['title'], img)
        assert img['x'] >= PAD - 0.5 and img['x'] + img['w'] <= LETTER_W - PAD + 0.5, (s['title'], img)
    for s in _sheets(pg, LETTER_BLOCK).values():
        img = s['images'][0]
        assert abs(img['y'] - (PAD + DA_PAD)) < 0.5, (s['title'], img)
        assert img['x'] + img['w'] <= LETTER_W - PAD - TB_W - DA_PAD + 0.5, (s['title'], img)


def test_a_sheet_the_narrow_tables_would_not_help_keeps_its_layout(page):
    """With the title block on, the drawing is 2.4 in narrower and three
    columns of these tables no longer fit under the wall: the tables at
    their own width give the wall nothing, so both sheets keep the layout
    and the wall they always had (two columns under the wall; 1114 and
    1180 page units wide)."""
    pg, _ = page
    s = _sheets(pg, LETTER_BLOCK)
    for kind, want in (('power', 1114), ('data', 1180)):
        sheet = s[kind]
        assert sheet['layout'] == 'stack' and sheet['cols'] == 2, (kind, sheet['layout'], sheet['cols'])
        assert abs(sheet['map']['w'] - want) < 2, (kind, sheet['map'])
