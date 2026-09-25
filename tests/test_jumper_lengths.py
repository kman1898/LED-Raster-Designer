"""The jumper between two cabinets of a run (app-jumpers.js).

Owner rulings, 2026-09-25, from a show of vertical-flow walls of
500 x 1000 mm cabinets whose binder listed 205 "Data Jump 6'" and 205
"Tru-1 Power Jump 6'" per screen while the real links are about a foot.
Every link between two consecutive cabinets of a data run or a power run
is one of:

  VERTICAL    the cabinet directly above / below (same screen, same
              column, row +-1) - a jumper at the screen's vertical length;
  HORIZONTAL  the cabinet directly beside (same row, column +-1) - at the
              screen's horizontal length;
  LONG        anything else (a jump back across the wall, a skip, a hop to
              another group member) - |dx| + |dy| between the cabinets'
              centers in real-world units, + 1 ft of slack, rounded UP to
              3, 6, 10, 15, 25 ft, then the next 5 ft past 25.

The short lengths are per screen (dataJumpV / dataJumpH / powerJumpV /
powerJumpH, feet or null = no cable), seeded from Preferences for a new
screen and read from Preferences for a file saved before them. The pull
list prints each length as its own row; the maps tag a long jump with its
length when the screen's cable tags are on.

Run locally (each session takes its own free port, so it runs beside
any other):
    python3 -m pytest tests/test_jumper_lengths.py -v --browser chromium
"""

import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
JS_DIR = os.path.join(HERE, '..', 'src', 'static', 'js')

FIELDS = ('dataJumpV', 'dataJumpH', 'powerJumpV', 'powerJumpH')


# ── the server: the fields ride the layer routes, a new screen is seeded ──

def test_a_new_screen_is_seeded_from_the_preferences(client):
    """create_layer takes the four lengths from the server's preferences:
    *JumpLength is the vertical link, *JumpLengthH the horizontal one, a
    record with no horizontal key reads its vertical figure, a blank (None)
    is no cable - and a record that says nothing is the shipped 6' / 6'."""
    import app as app_module
    keep = app_module.server_preferences
    try:
        _seeded_from_the_preferences(client, app_module)
    finally:
        app_module.server_preferences = keep


def _seeded_from_the_preferences(client, app_module):
    app_module.server_preferences = {}
    r = client.post('/api/layer/add', json={'name': 'S', 'columns': 2, 'rows': 2,
                                            'cabinet_width': 100, 'cabinet_height': 100})
    assert {k: r.get_json()[k] for k in FIELDS} == {
        'dataJumpV': 6, 'dataJumpH': 6, 'powerJumpV': 6, 'powerJumpH': 6}
    app_module.server_preferences = {'dataJumpLength': 1, 'dataJumpLengthH': 2.5,
                                     'powerJumpLength': None}
    r = client.post('/api/layer/add', json={'name': 'T', 'columns': 2, 'rows': 2,
                                            'cabinet_width': 100, 'cabinet_height': 100})
    assert {k: r.get_json()[k] for k in FIELDS} == {
        'dataJumpV': 1, 'dataJumpH': 2.5, 'powerJumpV': None, 'powerJumpH': None}
    # the one literal both sides fall back to
    import app as app_mod
    js = open(os.path.join(JS_DIR, 'app-jumpers.js'), encoding='utf-8').read()
    assert int(re.search(r'const JUMPER_SHIPPED_FT = (\d+);', js).group(1)) == app_mod.JUMPER_SHIPPED_FT
    prefs_js = open(os.path.join(JS_DIR, 'app-preferences.js'), encoding='utf-8').read()
    for key in ('powerJumpLength', 'powerJumpLengthH', 'dataJumpLength', 'dataJumpLengthH'):
        assert re.search(rf'\b{key}: {app_mod.JUMPER_SHIPPED_FT},', prefs_js), key


def test_the_fields_ride_put_and_add(client):
    """PUT /api/layer/<id> stores the four (null included - a blank is a
    decision) and GET serves them; /api/layer/add - the duplicate / paste
    route - takes them from its body."""
    r = client.post('/api/layer/add', json={'name': 'S', 'columns': 2, 'rows': 2,
                                            'cabinet_width': 100, 'cabinet_height': 100,
                                            'dataJumpV': 1, 'dataJumpH': None,
                                            'powerJumpV': 1.5, 'powerJumpH': 10})
    layer = r.get_json()
    assert {k: layer[k] for k in FIELDS} == {'dataJumpV': 1, 'dataJumpH': None,
                                             'powerJumpV': 1.5, 'powerJumpH': 10}
    r = client.put(f"/api/layer/{layer['id']}", json={'dataJumpV': 2, 'dataJumpH': 3,
                                                      'powerJumpV': None, 'powerJumpH': 0.5})
    assert r.status_code == 200
    served = next(l for l in client.get('/api/project').get_json()['layers'] if l['id'] == layer['id'])
    assert {k: served[k] for k in FIELDS} == {'dataJumpV': 2, 'dataJumpH': 3,
                                              'powerJumpV': None, 'powerJumpH': 0.5}


# ── the browser ──────────────────────────────────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


J = """const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());"""

# A fresh project of screens made through the real add route. Each entry
# is the add body; the answer is {name: id}.
RESET_JS = """async (bodies) => {
    """ + J + """
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.pullSheetEdits;
    await j('PUT', '/api/project', proj);
    for (const b of bodies) await j('POST', '/api/layer/add', b);
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('jumper_seed');
    // the client-side keys the add route does not store (the data flow)
    for (const b of bodies) {
        const l = app.project.layers.find(x => x.name === b.name);
        for (const k of ['flowPattern', 'processorType']) if (b[k] !== undefined) l[k] = b[k];
    }
    app.selectLayer(app.project.layers[0]);
    app.resetHistory('Jumper Seed');
    app._circuitTailCache = null;
    return Object.fromEntries(app.project.layers.map(l => [l.name, l.id]));
}"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    yield pg, errors
    context.close()


def _reset(pg, bodies):
    ids = pg.evaluate(RESET_JS, bodies)
    pg.wait_for_timeout(300)
    return ids


def _screen(name, cols, rows, w=60, h=60, **extra):
    body = {'name': name, 'columns': cols, 'rows': rows, 'cabinet_width': w, 'cabinet_height': h,
            'processorType': 'novastar-armor'}
    body.update(extra)
    return body


# ── the rule ─────────────────────────────────────────────────────────────

def test_the_stock_ladder(page):
    """Raw feet (slack already in) round UP to 3, 6, 10, 15, 25; past 25 to
    the next 5 ft."""
    pg, _ = page
    table = [(0.5, 3), (2.1, 3), (3, 3), (3.01, 6), (6.0, 6), (7, 10), (10, 10), (10.2, 15),
             (15, 15), (15.5, 25), (25, 25), (26, 30), (30, 30), (31, 35), (48.57, 50)]
    got = pg.evaluate("(xs) => xs.map(x => window.app.jumperStockLength(x))", [x for x, _ in table])
    assert got == [want for _, want in table], list(zip(table, got))


LINK_JS = """(args) => {
    const app = window.app;
    const L = (name) => app.project.layers.find(l => l.name === name);
    const P = (layer, r, c) => layer.panels.find(p => p.row === r && p.col === c);
    return args.map(([la, ra, ca, lb, rb, cb, side]) => {
        const A = L(la), B = L(lb);
        const k = app.jumperLink(P(A, ra, ca), A, P(B, rb, cb), B, side || 'data');
        return [k.kind, k.ft, k.rawFt == null ? null : Math.round(k.rawFt * 1000) / 1000];
    });
}"""


def test_each_link_is_vertical_horizontal_or_long(page):
    """On one screen of 500 x 1000 mm cabinets (60 x 120 px) at 1' / 2':
    the cabinet below is VERTICAL at the vertical length, the one beside
    HORIZONTAL at the horizontal length - on either side of the wall, each
    with its own pair; a skip over a cabinet, a diagonal and a jump back
    across the wall are LONG, measured center to center along the panels
    in real-world units + 1 ft and rounded up the ladder."""
    pg, _ = page
    _reset(pg, [_screen('W', 28, 3, 60, 120, panel_width_mm=500, panel_height_mm=1000,
                        dataJumpV=1, dataJumpH=2, powerJumpV=3, powerJumpH=None)])
    got = pg.evaluate(LINK_JS, [
        ['W', 0, 0, 'W', 1, 0, 'data'],      # below
        ['W', 1, 0, 'W', 0, 0, 'data'],      # above
        ['W', 0, 4, 'W', 0, 5, 'data'],      # beside
        ['W', 0, 5, 'W', 0, 4, 'data'],      # beside, going back
        ['W', 0, 0, 'W', 1, 0, 'power'],     # below, the power pair
        ['W', 0, 4, 'W', 0, 5, 'power'],     # beside: no power cable (blank)
        ['W', 0, 0, 'W', 0, 2, 'data'],      # a skip: 1000 mm + 1 ft
        ['W', 0, 0, 'W', 1, 1, 'data'],      # diagonal: 500 + 1000 mm
        ['W', 0, 27, 'W', 1, 0, 'data'],     # back across: 27 x 500 + 1000
        ['W', 0, 0, 'W', 2, 0, 'power'],     # two rows down: 2000 mm
    ])
    ft = lambda mm: round(mm / 304.8 + 1, 3)
    assert got == [
        ['vertical', 1, None], ['vertical', 1, None],
        ['horizontal', 2, None], ['horizontal', 2, None],
        ['vertical', 3, None], ['horizontal', None, None],
        ['long', 6, ft(1000)],       # 4.28 -> 6
        ['long', 6, ft(1500)],       # 5.92 -> 6
        ['long', 50, ft(14500)],     # 48.57 -> past 25, the next 5: 50
        ['long', 10, ft(2000)],      # 7.56 -> 10
    ], got


def test_half_tiles_are_measured_where_the_cabinet_really_is(page):
    """A half-width first column puts its cabinet's center a quarter
    cabinet further in: 6 x 1 of 560 mm cabinets, a jump from column 0 to
    column 5 is 2800 mm on a full wall (10.19 ft -> 15') and 2660 mm with
    column 0 half (9.73 ft -> 10'). The cabinet beside a half tile is still
    HORIZONTAL."""
    pg, _ = page
    ids = _reset(pg, [_screen('FULL', 6, 1, 60, 60, panel_width_mm=560, panel_height_mm=560),
                      _screen('HALF', 6, 1, 60, 60, panel_width_mm=560, panel_height_mm=560)])
    pg.evaluate("""async (id) => {
        """ + J + """
        const layer = app.project.layers.find(l => l.id === id);
        const p = layer.panels.find(x => x.row === 0 && x.col === 0);
        const res = await j('POST', `/api/layer/${id}/panel/${p.id}/set_half_tile`, {halfTile: 'width'});
        app.applyServerLayer(res);
    }""", ids['HALF'])
    widths = pg.evaluate("() => window.app.project.layers.find(l => l.name === 'HALF').panels.map(p => p.width)")
    assert widths == [30, 60, 60, 60, 60, 60], widths
    got = pg.evaluate(LINK_JS, [['FULL', 0, 0, 'FULL', 0, 5], ['HALF', 0, 0, 'HALF', 0, 5],
                                ['HALF', 0, 0, 'HALF', 0, 1]])
    assert got == [['long', 15, round(2800 / 304.8 + 1, 3)],
                   ['long', 10, round(2660 / 304.8 + 1, 3)],
                   ['horizontal', 6, None]], got


def test_a_group_seam_is_short_where_the_cabinets_touch_and_long_where_they_do_not(page):
    """Across two group members the rule is where the cabinets SIT (each
    member has its own grid), read in the measuring frame - Show Look
    pixels, each axis in mm by the mean of the two members' pitches:
    cabinets that touch edge to edge (a gap within 5 mm, a shared edge
    longer than that) are beside (HORIZONTAL) or above / below (VERTICAL),
    at the SOURCE cabinet's screen's length - A's 1' / 2', never B's 7' /
    8'. Two screens side by side are one wall, so a run over their seam is
    a short link. Members that sit apart, or meet only at a corner, are
    LONG and measured center to center + 1 ft: 60 px of air at 500 mm /
    60 px puts the centers 1000 mm apart (4.28 ft -> 6'); a 1000 mm / 60 px
    member 120 px off reads 180 px at the mean 12.5 mm/px = 2250 mm
    (8.38 ft -> 10', where A's pitch alone would say 6')."""
    pg, _ = page
    a = dict(panel_width_mm=500, panel_height_mm=500, dataJumpV=1, dataJumpH=2,
             powerJumpV=3, powerJumpH=4)
    b = dict(panel_width_mm=500, panel_height_mm=500, dataJumpV=7, dataJumpH=8)
    big = dict(panel_width_mm=1000, panel_height_mm=1000, dataJumpV=7, dataJumpH=8)
    _reset(pg, [
        _screen('A', 4, 1, 60, 60, showOffsetX=0, showOffsetY=0, **a),
        _screen('BESIDE', 4, 1, 60, 60, showOffsetX=240, showOffsetY=0, **b),
        _screen('BIG', 4, 1, 60, 60, showOffsetX=240, showOffsetY=0, **big),
        _screen('BELOW', 4, 1, 60, 60, showOffsetX=0, showOffsetY=60, **b),
        # 0.4 px = 3.3 mm of gap: a seam; 1 px = 8.3 mm: apart
        _screen('NEAR', 4, 1, 60, 60, showOffsetX=240.4, showOffsetY=0, **b),
        _screen('OFF', 4, 1, 60, 60, showOffsetX=241, showOffsetY=0, **b),
        _screen('APART', 4, 1, 60, 60, showOffsetX=300, showOffsetY=0, **b),
        _screen('BIGAPART', 4, 1, 60, 60, showOffsetX=360, showOffsetY=0, **big),
        _screen('CORNER', 4, 1, 60, 60, showOffsetX=240, showOffsetY=60, **b),
    ])
    got = pg.evaluate(LINK_JS, [
        ['A', 0, 3, 'BESIDE', 0, 0],            # edge to edge beside
        ['BESIDE', 0, 0, 'A', 0, 3],            # the other way: BESIDE's own 8'
        ['A', 0, 3, 'BESIDE', 0, 0, 'power'],   # A's power pair
        ['A', 0, 3, 'BIG', 0, 0],               # a different pitch, still touching
        ['A', 0, 2, 'BELOW', 0, 2],             # directly under
        ['A', 0, 3, 'NEAR', 0, 0],              # within the tolerance
        ['A', 0, 3, 'OFF', 0, 0],               # past it
        ['A', 0, 3, 'APART', 0, 0],             # 60 px of air
        ['A', 0, 3, 'BIGAPART', 0, 0],          # 120 px, mixed pitch
        ['A', 0, 3, 'CORNER', 0, 0],            # corners only
        ['A', 0, 0, 'BESIDE', 0, 0],            # not the neighbour: across A
    ])
    ft = lambda mm: round(mm / 304.8 + 1, 3)
    assert got == [
        ['horizontal', 2, None],
        ['horizontal', 8, None],
        ['horizontal', 4, None],
        ['horizontal', 2, None],
        ['vertical', 1, None],
        ['horizontal', 2, None],
        ['long', 3, ft(61 * 500 / 60)],         # 2.67 ft -> 3'
        ['long', 6, ft(1000)],
        ['long', 10, ft(2250)],
        ['long', 6, ft(500 + 500)],             # 60 px across, 60 down
        ['long', 10, ft(240 * 500 / 60)],       # 2000 mm: 7.56 -> 10'
    ], got


def test_a_run_over_a_group_seam_counts_short_jumpers(page):
    """Two grouped screens side by side, data routed as one wall: the
    pull list counts the run's step over the seam as a 1' jumper like
    every other link beside, not as a measured long jump."""
    pg, _ = page
    ids = _reset(pg, [
        _screen('L', 3, 2, 60, 60, showOffsetX=0, showOffsetY=0, flowPattern='tl-h',
                dataJumpV=1, dataJumpH=1, powerJumpV=1, powerJumpH=1),
        _screen('R', 3, 2, 60, 60, showOffsetX=180, showOffsetY=0, flowPattern='tl-h',
                dataJumpV=1, dataJumpH=1, powerJumpV=1, powerJumpH=1),
    ])
    out = pg.evaluate("""async (ids) => {
        """ + J + """
        const p = await j('GET', '/api/project');
        p.groups = [{id: 'g1', name: 'WALL', layer_ids: [ids.L, ids.R], routeDataAsOne: false}];
        await j('PUT', '/api/project', p);
        app.project = await j('GET', '/api/project');
        app.dedupeProjectLayers('jumper_seam');
        const L = app.project.layers.find(l => l.id === ids.L);
        const R = app.project.layers.find(l => l.id === ids.R);
        // one hand-drawn run along the top row of both members
        L.flowPattern = 'custom';
        L.customPortPaths = {1: [{row: 0, col: 0}, {row: 0, col: 1}, {row: 0, col: 2},
                                 {row: 0, col: 0, layerId: R.id}, {row: 0, col: 1, layerId: R.id},
                                 {row: 0, col: 2, layerId: R.id}]};
        app._circuitTailCache = null;
        const runs = app.screenJumperRuns(L, 'data');
        const links = runs.flatMap(r => app.jumperLinksOfRun(r.panels, r.layers, L, 'data'))
            .map(k => [k.kind, k.ft, k.la === k.lb]);
        return {links, lengths: app.buildPullList().byScreen[String(ids.L)].jumperLengths.data};
    }""", ids)
    assert out['links'] == [['horizontal', 1, True], ['horizontal', 1, True],
                            ['horizontal', 1, False],
                            ['horizontal', 1, True], ['horizontal', 1, True]], out
    assert out['lengths'] == {'1': 5}, out


# ── the NYL shape: a vertical-flow wall of 500 x 1000 mm cabinets ───────

NYL_JS = """(name) => {
    const app = window.app;
    app._circuitTailCache = null;
    const layer = app.project.layers.find(l => l.name === name);
    const list = app.buildPullList();
    const scr = list.byScreen[String(layer.id)];
    const runs = {data: app.screenJumperRuns(layer, 'data'), power: app.screenJumperRuns(layer, 'power')};
    const links = {};
    for (const side of ['data', 'power']) {
        links[side] = runs[side].flatMap(r => app.jumperLinksOfRun(r.panels, r.layers, layer, side))
            .map(k => ({kind: k.kind, ft: k.ft, a: [k.a.row, k.a.col], b: [k.b.row, k.b.col]}));
    }
    return {jumpers: scr.jumpers, lengths: scr.jumperLengths,
            rows: scr.rows.filter(r => /Jump/.test(r.type)).map(r => [r.type, r.length, r.qty]),
            panels: layer.panels.filter(p => !p.hidden).length,
            runs: {data: runs.data.length, power: runs.power.length}, links};
}"""


def test_a_vertical_flow_wall_of_tall_cabinets_counts_one_foot_links(page):
    """21 x 6 of 500 x 1000 mm cabinets, vertical-first on both sides, at
    1' / 1': every link of every run is a cabinet above / below or beside,
    so the whole wall is 1' jumpers - one per link, visible cabinets less
    runs - where the one-per-row-step rule printed a 6' for every step
    down a column. Hiding one cabinet mid-column makes the one real
    non-touching jump: the run steps over it, two cabinets down (2000 mm
    + 1 ft = 7.56 ft -> 10'), and nothing else changes."""
    pg, _ = page
    _reset(pg, [_screen('NYL', 21, 6, 104, 208, panel_width_mm=500, panel_height_mm=1000,
                        flowPattern='tl-v', powerFlowPattern='tl-v', powerOrganized=True,
                        powerVoltage=208, powerAmperage=20, panelWatts=150,
                        dataJumpV=1, dataJumpH=1, powerJumpV=1, powerJumpH=1)])
    out = pg.evaluate(NYL_JS, 'NYL')
    assert out['panels'] == 126
    for side in ('data', 'power'):
        n = out['panels'] - out['runs'][side]
        assert out['runs'][side] >= 1
        assert {x['kind'] for x in out['links'][side]} <= {'vertical', 'horizontal'}, out['links'][side]
        assert out['jumpers'][side] == n and out['lengths'][side] == {'1': n}, (side, out)
    assert out['rows'] == [['Data Jump', "1'", out['panels'] - out['runs']['data']],
                           ['Tru-1 Power Jump', "1'", out['panels'] - out['runs']['power']]], out['rows']
    # most links run down a column: a 6-high column has 5 of them
    assert sum(1 for x in out['links']['data'] if x['kind'] == 'vertical') >= 21 * 5 - out['runs']['data']
    # hide row 2 of column 10: the run walks over it
    pg.evaluate("""async () => {
        """ + J + """
        const layer = app.project.layers.find(l => l.name === 'NYL');
        const p = layer.panels.find(x => x.row === 2 && x.col === 10);
        const res = await j('POST', `/api/layer/${layer.id}/panels/set_hidden`,
                            {panels: [{id: p.id, hidden: true}]});
        app.applyServerLayer(res.layer);
    }""")
    out = pg.evaluate(NYL_JS, 'NYL')
    assert out['panels'] == 125
    for side in ('data', 'power'):
        longs = [x for x in out['links'][side] if x['kind'] == 'long']
        assert longs == [{'kind': 'long', 'ft': 10, 'a': [1, 10], 'b': [3, 10]}] or \
            longs == [{'kind': 'long', 'ft': 10, 'a': [3, 10], 'b': [1, 10]}], (side, longs)
        ones = out['panels'] - out['runs'][side] - 1
        assert out['lengths'][side] == {'1': ones, '10': 1}, (side, out['lengths'])
    assert out['rows'] == [['Data Jump', "1'", out['lengths']['data']['1']], ['Data Jump', "10'", 1],
                           ['Tru-1 Power Jump', "1'", out['lengths']['power']['1']],
                           ['Tru-1 Power Jump', "10'", 1]], out['rows']


def test_blank_counts_no_cable_and_the_pull_sheet_sums_per_length(page):
    """Two screens on one beach: A at 1' down / blank beside (panels that
    link themselves), B at 1' / 2'. The position's rows add up per length
    across both screens, each length its own row; A's links beside count
    nothing, a long jump always counts. The totals are the same sums."""
    pg, _ = page
    ids = _reset(pg, [_screen('A', 3, 2, 60, 60, flowPattern='tl-h', dataJumpV=1, dataJumpH=None,
                              powerJumpV=1, powerJumpH=None),
                      _screen('B', 3, 2, 60, 60, flowPattern='tl-h', dataJumpV=1, dataJumpH=2,
                              powerJumpV=1, powerJumpH=2)])
    out = pg.evaluate("""async (ids) => {
        """ + J + """
        await app.createBeach('SR', null);
        const beach = app.getBeaches()[0].id;
        for (const id of Object.values(ids)) {
            const l = app.project.layers.find(x => x.id === id);
            l.beachId = beach;
        }
        // B's port hand-drawn with one jump back across its top row
        const b = app.project.layers.find(x => x.id === ids.B);
        b.flowPattern = 'custom';
        b.customPortPaths = {1: [{row: 0, col: 0}, {row: 0, col: 1}, {row: 0, col: 2},
                                 {row: 1, col: 0}, {row: 1, col: 1}, {row: 1, col: 2}]};
        app._circuitTailCache = null;
        const list = app.buildPullList();
        const rows = (rs) => rs.filter(r => r.type === 'Data Jump').map(r => [r.length, r.qty, r.label]);
        return {pos: list.positions.map(p => [p.name, rows(p.rows)]), totals: rows(list.totals),
                a: list.byScreen[String(ids.A)].jumperLengths.data,
                b: list.byScreen[String(ids.B)].jumperLengths.data};
    }""", ids)
    # A: serpentine 3 x 2 - 4 beside (blank: none), 1 down at 1'
    assert out['a'] == {'1': 1}
    # B: 4 beside at 2', and (0,2) -> (1,0): 2 x 500 + 500 mm = 1500 mm
    # + 1 ft = 5.92 ft -> 6'
    assert out['b'] == {'2': 4, '6': 1}
    assert out['pos'] == [['SR', [["1'", 1, 'A'], ["2'", 4, 'B'], ["6'", 1, 'B']]]], out['pos']
    assert out['totals'] == [["1'", 1, 'A'], ["2'", 4, 'B'], ["6'", 1, 'B']], out['totals']


# ── the fields: presets, copies, older files, the sidebar ──────────────

def test_a_preset_carries_the_four_and_applies_them(page):
    """serializeLayerAsPreset writes the four lengths (null included; a
    screen from an older file writes the preferences' figures it reads)
    and applyPresetClientProps lays them on a new screen."""
    pg, _ = page
    _reset(pg, [_screen('P', 2, 2, dataJumpV=1.5, dataJumpH=None, powerJumpV=2, powerJumpH=3),
                _screen('Q', 2, 2)])
    out = pg.evaluate("""() => {
        const app = window.app;
        const P = app.project.layers.find(l => l.name === 'P');
        const Q = app.project.layers.find(l => l.name === 'Q');
        const preset = app.serializeLayerAsPreset(P);
        const pick = (o) => ({dataJumpV: o.dataJumpV, dataJumpH: o.dataJumpH,
                              powerJumpV: o.powerJumpV, powerJumpH: o.powerJumpH});
        const fresh = {id: 999, type: 'screen', columns: 2, rows: 2, panels: []};
        app.initializeLayerDefaults(fresh);
        const seeded = pick(fresh);
        app.applyPresetClientProps(fresh, JSON.parse(JSON.stringify(preset)));
        // an older file's screen: no fields at all
        for (const k of ['dataJumpV', 'dataJumpH', 'powerJumpV', 'powerJumpH']) delete Q[k];
        return {preset: pick(preset), seeded, applied: pick(fresh),
                old: pick(app.serializeLayerAsPreset(Q)), prefs: app.jumperDefaults()};
    }""")
    want = {'dataJumpV': 1.5, 'dataJumpH': None, 'powerJumpV': 2, 'powerJumpH': 3}
    assert out['preset'] == want and out['applied'] == want, out
    assert out['seeded'] == out['prefs'] == out['old'], out


def test_duplicate_and_paste_keep_the_screens_lengths(page):
    """A copy is the same cabinets: Duplicate and Copy / Paste carry the
    four lengths to the new screen, on the server too."""
    pg, _ = page
    _reset(pg, [_screen('D', 2, 2, dataJumpV=1, dataJumpH=None, powerJumpV=2.5, powerJumpH=4)])
    out = pg.evaluate("""async () => {
        """ + J + """
        const D = app.project.layers.find(l => l.name === 'D');
        app.selectLayer(D);
        app.duplicateLayer(D);
        await new Promise(r => setTimeout(r, 900));
        app.selectLayer(D);
        app.copyLayer();
        app.pasteLayer();
        await new Promise(r => setTimeout(r, 900));
        const pick = (o) => [o.dataJumpV, o.dataJumpH, o.powerJumpV, o.powerJumpH];
        const served = (await j('GET', '/api/project')).layers;
        return {client: app.project.layers.map(l => [l.name, pick(l)]),
                server: served.map(l => [l.name, pick(l)])};
    }""")
    assert len(out['client']) == 3, out
    for name, vals in out['client'] + out['server']:
        assert vals == [1, None, 2.5, 4], (name, vals, out)


def test_an_older_file_reads_the_preferences_and_is_not_rewritten(page):
    """A screen saved before the fields existed opens reading the
    preferences' figures (stamped in memory at load); the server's copy
    stays without them until an edit writes the layer."""
    pg, errors = page
    ids = _reset(pg, [_screen('OLD', 3, 1, 60, 60, flowPattern='tl-h')])
    pg.evaluate("""async () => {
        """ + J + """
        const proj = await j('GET', '/api/project');
        for (const l of proj.layers) {
            for (const k of ['dataJumpV', 'dataJumpH', 'powerJumpV', 'powerJumpH']) delete l[k];
        }
        await j('PUT', '/api/project', proj);
    }""")
    pg.reload(wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    out = pg.evaluate("""async (id) => {
        """ + J + """
        const l = app.project.layers.find(x => x.id === id);
        const served = (await j('GET', '/api/project')).layers.find(x => x.id === id);
        return {client: [l.dataJumpV, l.dataJumpH, l.powerJumpV, l.powerJumpH],
                prefs: app.jumperDefaults(),
                served: ['dataJumpV', 'dataJumpH', 'powerJumpV', 'powerJumpH'].filter(k => k in served),
                lengths: app.buildPullList().byScreen[String(id)].jumperLengths.data};
    }""", ids['OLD'])
    p = out['prefs']
    assert out['client'] == [p['dataJumpV'], p['dataJumpH'], p['powerJumpV'], p['powerJumpH']], out
    assert out['served'] == [], 'the file was rewritten at load'
    assert out['lengths'] == {str(p['dataJumpH']): 2}, out
    assert errors == [], errors


SIDEBAR_JS = """() => {
    const v = id => { const el = document.getElementById(id); return [el.value, el.placeholder]; };
    return {dv: v('data-jump-v'), dh: v('data-jump-h'), pv: v('power-jump-v'), ph: v('power-jump-h')};
}"""


def test_the_sidebar_jumpers_rows_commit_once_and_know_a_mixed_selection(page):
    """Data sidebar: Vertical / Horizontal beside Show Cable Tags. A typed
    figure commits to every selected screen - one history entry, on the
    server - blank is null, an entry that is not a length is refused; two
    screens that disagree show a blank with "-". The Power sidebar's pair
    writes the power fields."""
    pg, errors = page
    ids = _reset(pg, [_screen('S1', 2, 2, dataJumpV=1, dataJumpH=2, powerJumpV=3, powerJumpH=None),
                      _screen('S2', 2, 2, dataJumpV=1, dataJumpH=5, powerJumpV=3, powerJumpH=None)])
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(400)
    pg.evaluate("(ids) => { const app = window.app; app.setSelectedLayersByIds([ids.S1, ids.S2], ids.S1); app.updateUI(); }", ids)
    pg.wait_for_timeout(300)
    assert pg.locator('#data-jump-v').is_visible() and pg.locator('#data-jump-h').is_visible()
    assert pg.evaluate(SIDEBAR_JS) == {'dv': ['1', 'none'], 'dh': ['', '-'],
                                       'pv': ['3', 'none'], 'ph': ['', 'none']}
    hist = "() => ({n: window.app.history.length, last: window.app.history[window.app.historyIndex].action})"
    before = pg.evaluate(hist)
    pg.locator('#data-jump-h').fill('1.5')
    pg.locator('#data-jump-h').press('Enter')
    pg.wait_for_timeout(700)
    after = pg.evaluate(hist)
    assert after == {'n': before['n'] + 1, 'last': 'Set Data Jumper Horizontal'}, (before, after)
    read = """async (ids) => {
        """ + J + """
        const served = (await j('GET', '/api/project')).layers;
        const pick = (o) => [o.dataJumpV, o.dataJumpH, o.powerJumpV, o.powerJumpH];
        return {client: [ids.S1, ids.S2].map(id => pick(app.project.layers.find(l => l.id === id))),
                server: [ids.S1, ids.S2].map(id => pick(served.find(l => l.id === id)))};
    }"""
    out = pg.evaluate(read, ids)
    assert out['client'] == out['server'] == [[1, 1.5, 3, None], [1, 1.5, 3, None]], out
    # blank is null: no cable
    pg.locator('#data-jump-v').fill('')
    pg.locator('#data-jump-v').press('Enter')
    pg.wait_for_timeout(700)
    out = pg.evaluate(read, ids)
    assert out['client'] == out['server'] == [[None, 1.5, 3, None], [None, 1.5, 3, None]], out
    assert pg.evaluate(hist)['n'] == before['n'] + 2
    # undo takes the last one back, and only that
    pg.evaluate("() => window.app.undo()")
    pg.wait_for_timeout(700)
    assert pg.evaluate(read, ids)['client'] == [[1, 1.5, 3, None], [1, 1.5, 3, None]]
    # the Power sidebar's pair
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(400)
    pg.evaluate("(ids) => { const app = window.app; app.setSelectedLayersByIds([ids.S1, ids.S2], ids.S1); app.updateUI(); }", ids)
    pg.wait_for_timeout(300)
    assert pg.locator('#power-jump-h').is_visible()
    pg.locator('#power-jump-h').fill('2')
    pg.locator('#power-jump-h').press('Enter')
    pg.wait_for_timeout(700)
    out = pg.evaluate(read, ids)
    assert out['client'] == out['server'] == [[1, 1.5, 3, 2], [1, 1.5, 3, 2]], out
    assert pg.evaluate(hist)['last'] == 'Set Power Jumper Horizontal'
    # not a length: refused, flagged, nothing written
    n = pg.evaluate(hist)['n']
    pg.locator('#power-jump-v').fill('-4')
    pg.locator('#power-jump-v').press('Enter')
    pg.wait_for_timeout(500)
    assert pg.evaluate(hist)['n'] == n
    assert 'invalid' in pg.locator('#power-jump-v').get_attribute('class')
    assert pg.evaluate(read, ids)['client'] == [[1, 1.5, 3, 2], [1, 1.5, 3, 2]]
    assert errors == [], errors


# ── the maps: a long jump's tag ─────────────────────────────────────────

TAGS_JS = """(mode) => {
    const app = window.app, r = window.canvasRenderer;
    app._circuitTailCache = null;
    const l = app.project.layers.find(x => x.name === 'T');
    l._powerCircuits = null;
    r.startLabelProbe();
    try { r.render(); } finally { var boxes = r.endLabelProbe(); }
    return boxes.filter(b => b.kind === 'jump').map(b => b.text);
}"""


def test_a_long_jump_wears_its_length_only_with_the_cable_tags_on(page):
    """A hand-drawn run with one jump back across the wall - (0,3) to
    (1,0) on 4 x 2 of 500 mm cabinets: 3 x 500 + 500 = 2000 mm + 1 ft ->
    10' - draws a "10'" tag at the jump's midpoint when the screen's Show
    Cable Tags is on, and nothing when it is off; the short links never
    wear one. Data and power alike, each on its own switch."""
    pg, errors = page
    _reset(pg, [_screen('T', 4, 2, 60, 60, panel_width_mm=500, panel_height_mm=500,
                        dataJumpV=1, dataJumpH=1, powerJumpV=1, powerJumpH=1,
                        powerVoltage=208, powerAmperage=20, panelWatts=100)])
    path = [{'row': 0, 'col': c} for c in range(4)] + [{'row': 1, 'col': c} for c in range(4)]
    pg.evaluate("""(path) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.name === 'T');
        l.flowPattern = 'custom'; l.customPortPaths = {1: path}; l.customPortIndex = 2;
        l.powerFlowPattern = 'custom'; l.powerCustomPaths = {1: path}; l.powerCustomIndex = 2;
        l.showDataCableTags = false; l.showPowerCableTags = false;
        app.selectLayer(l);
    }""", path)
    for mode, flag in (('data-flow', 'showDataCableTags'), ('power', 'showPowerCableTags')):
        pg.locator(f'[data-mode="{mode}"]').click()
        pg.wait_for_timeout(400)
        assert pg.evaluate(TAGS_JS, mode) == [], mode
        # the switch, as a user flips it
        box = '#show-data-cable-tags' if mode == 'data-flow' else '#show-power-cable-tags'
        pg.locator(box).check()
        pg.wait_for_timeout(500)
        assert pg.evaluate(f"() => window.app.project.layers.find(x => x.name === 'T').{flag}") is True
        assert pg.evaluate(TAGS_JS, mode) == ["10'"], mode
        pg.locator(box).uncheck()
        pg.wait_for_timeout(500)
        assert pg.evaluate(TAGS_JS, mode) == [], mode
    # the pill is centred on the jump's midpoint (in the layer's frame,
    # where the segment is drawn): read off the drawer's own call
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(300)
    pg.locator('#show-data-cable-tags').check()
    pg.wait_for_timeout(500)
    where = pg.evaluate("""() => {
        const app = window.app, r = window.canvasRenderer;
        const l = app.project.layers.find(x => x.name === 'T');
        const P = (row, col) => l.panels.find(p => p.row === row && p.col === col);
        const calls = [];
        const orig = r.drawCableTag;
        r.drawCableTag = function (text, x, y, size, colors, opts, kind) {
            if (kind === 'jump') {
                const rc = this.cableTagRect(text, x, y, size, opts);
                calls.push({text, cx: rc.x + rc.w / 2, cy: rc.y + rc.h / 2});
            }
            return orig.apply(this, arguments);
        };
        try { r.render(); } finally { r.drawCableTag = orig; }
        const c = (p) => [p.x + p.width / 2, p.y + p.height / 2];
        const a = c(P(0, 3)), b = c(P(1, 0));
        return {calls, mid: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]};
    }""")
    assert len(where['calls']) == 1 and where['calls'][0]['text'] == "10'", where
    call = where['calls'][0]
    assert abs(call['cx'] - where['mid'][0]) < 1 and abs(call['cy'] - where['mid'][1]) < 1, where
    assert errors == [], errors
