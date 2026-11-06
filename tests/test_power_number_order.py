"""Organized power cuts a row (or column) too big for one circuit, the
Circuit numbers switch, and the eight Z flow patterns.

The owner's rulings, 2026-11-01:

  1. Power Organized splits a too-long row "same as data": each circuit
     takes as many whole cabinets as fit along the row, read from the
     pattern's start side, the next starts where it stopped in the SAME
     row, and the last takes the remainder. A circuit never wraps onto the
     next row. Rows that fit keep their old circuits exactly. One cabinet
     over a circuit is still the error.
  2. The short leftover is a circuit like any other: with splitters on,
     the leftovers share through 2fers / 3fers.
  3. The same for a column too tall for one circuit (vertical first).
  4. Circuit numbers: Across | Down (layer.powerNumberOrder; missing
     follows the flow: Across on horizontal first, Down on vertical
     first). The circuits stay the same runs; only the numbers move.
     Across numbers along each line first, Down down the stacks, then the
     next stack back at the first line. Vertical first keeps the words'
     meaning on the wall: Across numbers along the top band of runs,
     Down down each column. The start corner decides where the first line
     and the first run are.

  Z patterns ('tl-h-z' ... 'br-v-z'): the snake's twin with the same corner
  and first direction, where every row (or column) starts again from the
  same side as the first. The picker shows the eight snakes on top and the
  eight Z twins under them, each row TL, TR, BL, BR horizontal first, then
  TL, TR, BL, BR vertical first.

The repro: 90 x 5 cabinets of 192 x 384 at 150 W on 208V / 20A. A US
circuit packs to 80% (3,328 W), so a circuit carries 22 cabinets and a
row (13,500 W) is 22 + 22 + 22 + 22 + 2. Before this change Organized
tl-h returned CANNOT FIT COMPLETE ROW with no circuits.

Run locally:
    python -m pytest tests/test_power_number_order.py --browser chromium
"""

import json
import os
import sys
import urllib.request

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app.project && window.canvasRenderer")
    pg.wait_for_timeout(1500)
    pg.evaluate(HELPERS_JS)
    yield pg
    context.close()


HELPERS_JS = """
window.__pn = {
    screen(opts) {
        const o = Object.assign({
            id: 901, name: 'S', type: 'screen', visible: true,
            columns: 4, rows: 3,
            cabinet_width: 128, cabinet_height: 128,
            offset_x: 0, offset_y: 0,
            panel_weight: 20, weight_unit: 'kg',
            panelWatts: 150, powerVoltage: 208, powerAmperage: 20,
            processorType: 'brompton', bitDepth: 8, frameRate: 60,
            lowLatency: false,
            flowPattern: 'tl-h', portMappingMode: 'organized',
            powerFlowPattern: 'tl-h', powerOrganized: true, powerMaximize: false,
            group_id: null,
        }, opts || {});
        // `halfRow` / `halfCol`: one row of half-height (or one column of
        // half-width) cabinets, the rows below (columns right) moved up.
        // A half cabinet draws half the watts (getPanelLoadFactor).
        const halfRow = o.halfRow, halfCol = o.halfCol;
        delete o.halfRow;
        delete o.halfCol;
        const h = r => (r === halfRow ? o.cabinet_height / 2 : o.cabinet_height);
        const w = c => (c === halfCol ? o.cabinet_width / 2 : o.cabinet_width);
        const panels = [];
        let y = o.offset_y;
        for (let r = 0; r < o.rows; r++) {
            let x = o.offset_x;
            for (let c = 0; c < o.columns; c++) {
                panels.push({
                    row: r, col: c, x, y,
                    width: w(c), height: h(r),
                    hidden: false, blank: false,
                    halfTile: r === halfRow ? 'height' : (c === halfCol ? 'width' : 'none'),
                });
                x += w(c);
            }
            y += h(r);
        }
        o.panels = panels;
        return o;
    },
    // the owner's repro: 90 x 5 of 192 x 384, 150 W, 208V / 20A
    repro(extra) {
        return this.screen(Object.assign({
            name: 'Repro', columns: 90, rows: 5,
            cabinet_width: 192, cabinet_height: 384,
        }, extra || {}));
    },
    withProject(project, fn) {
        const saved = window.app.project;
        window.app.project = Object.assign(
            { layers: [], groups: [], canvases: [], rack: [] }, project);
        window.app._circuitTailCache = null;
        try { return fn(); } finally {
            window.app.project = saved;
            window.app._circuitTailCache = null;
        }
    },
    // calculatePowerAssignments as plain [[row, col], ...] per circuit
    cells(S) {
        return this.withProject({ layers: [S] }, () => {
            const a = window.app.calculatePowerAssignments(S);
            return {
                error: a.error ? a.error.message : null,
                cut: !!a.cut,
                keys: Object.keys(a).sort(),
                runs: a.runs || null,
                circuits: (a.circuits || []).map(c => c.map(p => [p.row, p.col])),
            };
        });
    },
};
"""


def cells(page, js_screen):
    return page.evaluate("() => window.__pn.cells(" + js_screen + ")")


def run(row, cols):
    return [[row, c] for c in cols]


def col_run(col, rows):
    return [[r, col] for r in rows]


# ── 1. the long-row split ────────────────────────────────────────────────

def test_repro_90x5_splits_each_row_into_22_22_22_22_2(page):
    out = cells(page, "window.__pn.repro()")
    assert out['error'] is None, out['error']
    assert out['cut'] is True
    circuits = out['circuits']
    assert len(circuits) == 25, len(circuits)
    assert [len(c) for c in circuits] == [22, 22, 22, 22, 2] * 5
    # Across (the default): along row 1 first, then row 2, ...; every
    # circuit inside one row, read left to right from the start side
    expect = []
    for r in range(5):
        for start, end in ((0, 22), (22, 44), (44, 66), (66, 88), (88, 90)):
            expect.append(run(r, range(start, end)))
    assert circuits == expect


def test_repro_vertical_first_and_maximize_are_what_they_were(page):
    """The finding's other figures: Organized tl-v fits columns (23 circuits
    of 4 columns and 1 of 2), Maximize packs 21 circuits."""
    v = cells(page, "window.__pn.repro({ powerFlowPattern: 'tl-v' })")
    assert v['error'] is None and v['cut'] is False
    assert [len(c) for c in v['circuits']] == [20] * 22 + [10]
    m = cells(page, "window.__pn.repro({ powerMaximize: true, powerOrganized: false })")
    assert m['error'] is None and len(m['circuits']) == 21


def test_one_cabinet_over_a_circuit_is_still_the_error(page):
    out = cells(page, "window.__pn.repro({ panelWatts: 4000 })")
    assert out['error'] == 'PANEL WATTS EXCEED CIRCUIT CAPACITY'
    assert out['circuits'] == []


def test_leftovers_share_through_2fers_and_3fers(page):
    """Splitters on, maxWays 3: the 22-cabinet runs are each a circuit of
    their own, and the five 2-cabinet leftovers at the far end share: a
    3fer of rows 1-3 and a 2fer of rows 4-5."""
    out = cells(page, """window.__pn.repro({ powerSplitters: { enabled: true, maxWays: 3,
        manual: { merge: [], split: [] } } })""")
    assert out['error'] is None and out['cut'] is True
    circuits = out['circuits']
    assert len(circuits) == 22, len(circuits)
    shared = [i for i, r in enumerate(out['runs']) if len(r) > 1]
    assert [out['runs'][i] for i in shared] == [[2, 2, 2], [2, 2]]
    assert circuits[shared[0]] == run(0, [88, 89]) + run(1, [88, 89]) + run(2, [88, 89])
    assert circuits[shared[1]] == run(3, [88, 89]) + run(4, [88, 89])
    # Across: row 1's four runs, then the 3fer that starts on row 1
    assert shared[0] == 4
    assert all(len(c) == 22 for i, c in enumerate(circuits) if i not in shared)


def test_sharing_screen_numbers_down_with_the_same_circuits(page):
    base = """window.__pn.repro({ powerSplitters: { enabled: true, maxWays: 3,
        manual: { merge: [], split: [] } }%s })"""
    across = cells(page, base % '')
    down = cells(page, base % ", powerNumberOrder: 'down'")
    assert sorted(map(json.dumps, across['circuits'])) == sorted(map(json.dumps, down['circuits']))
    # Down: the first stack is every row's first run, top to bottom
    assert [c[0] for c in down['circuits'][:5]] == [[r, 0] for r in range(5)]
    assert down['runs'][-2:] == [[2, 2, 2], [2, 2]]


def test_column_too_tall_splits_down_the_column(page):
    """Vertical first: a 30-tall column of 150 W cabinets (4,500 W) is
    22 + 8, read from the top on tl-v and from the bottom on bl-v."""
    tl = cells(page, "window.__pn.screen({ columns: 3, rows: 30, powerFlowPattern: 'tl-v' })")
    assert tl['error'] is None and tl['cut'] is True
    # No saved order follows the flow: Down on a vertical-first pattern,
    # down each column first - the walk's own order
    down_each_column = [
        col_run(0, range(0, 22)), col_run(0, range(22, 30)),
        col_run(1, range(0, 22)), col_run(1, range(22, 30)),
        col_run(2, range(0, 22)), col_run(2, range(22, 30)),
    ]
    assert tl['circuits'] == down_each_column
    tld = cells(page, """window.__pn.screen({ columns: 3, rows: 30, powerFlowPattern: 'tl-v',
        powerNumberOrder: 'down' })""")
    assert tld['circuits'] == down_each_column
    # Across: along the top band first, then back for the next band
    tla = cells(page, """window.__pn.screen({ columns: 3, rows: 30, powerFlowPattern: 'tl-v',
        powerNumberOrder: 'across' })""")
    assert tla['circuits'] == [
        col_run(0, range(0, 22)), col_run(1, range(0, 22)), col_run(2, range(0, 22)),
        col_run(0, range(22, 30)), col_run(1, range(22, 30)), col_run(2, range(22, 30)),
    ]
    bl = cells(page, """window.__pn.screen({ columns: 2, rows: 30, powerFlowPattern: 'bl-v',
        powerNumberOrder: 'down' })""")
    assert bl['circuits'] == [
        col_run(0, range(29, 7, -1)), col_run(0, range(7, -1, -1)),
        col_run(1, range(29, 7, -1)), col_run(1, range(7, -1, -1)),
    ]


def test_a_screen_that_fits_keeps_its_circuits(page):
    """6 x 7 at 150 W: a row is 900 W, so three rows share a circuit
    (2,700 W) and the walk snakes inside it - the circuits every show
    had. The result's shape gains no key."""
    out = cells(page, "window.__pn.screen({ columns: 6, rows: 7 })")
    assert out['error'] is None and out['cut'] is False
    assert out['keys'] == ['circuits', 'error']
    fwd, back = list(range(6)), list(range(5, -1, -1))
    assert out['circuits'] == [
        run(0, fwd) + run(1, back) + run(2, fwd),
        run(3, fwd) + run(4, back) + run(5, fwd),
        run(6, fwd),
    ]
    # the switch does nothing where nothing is cut
    down = cells(page, "window.__pn.screen({ columns: 6, rows: 7, powerNumberOrder: 'down' })")
    assert down['circuits'] == out['circuits']
    shared = cells(page, """window.__pn.screen({ columns: 6, rows: 7,
        powerSplitters: { enabled: true, maxWays: 3, manual: { merge: [], split: [] } } })""")
    assert shared['keys'] == ['circuits', 'error', 'runIds', 'runs']
    assert shared['runs'] == [[6, 6, 6], [6, 6, 6], [6]]


def test_rows_that_fit_beside_a_cut_row_keep_their_places(page):
    """Hidden cabinets make rows 1-2 short enough to share a circuit; row 3
    is cut. The short rows are one circuit as before, the cut row's pieces
    follow, and Down only renumbers inside the cut stretch."""
    js = """(() => { const S = window.__pn.screen({ columns: 30, rows: 4%s });
        S.panels.forEach(p => { if (p.row < 2 && p.col >= 5) p.hidden = true; });
        return S; })()"""
    across = cells(page, js % '')
    assert across['circuits'][0] == run(0, range(5)) + run(1, range(4, -1, -1))
    assert across['circuits'][1:] == [run(2, range(22)), run(2, range(22, 30)),
                                      run(3, range(22)), run(3, range(22, 30))]
    down = cells(page, js % ", powerNumberOrder: 'down'")
    assert down['circuits'] == [across['circuits'][0], run(2, range(22)), run(3, range(22)),
                                run(2, range(22, 30)), run(3, range(22, 30))]


# ── 2. Down numbering ────────────────────────────────────────────────────

def test_down_numbers_the_90x5_down_the_stacks(page):
    across = cells(page, "window.__pn.repro()")
    down = cells(page, "window.__pn.repro({ powerNumberOrder: 'down' })")
    assert sorted(map(json.dumps, across['circuits'])) == sorted(map(json.dumps, down['circuits']))
    expect = []
    for start, end in ((0, 22), (22, 44), (44, 66), (66, 88), (88, 90)):
        for r in range(5):
            expect.append(run(r, range(start, end)))
    assert down['circuits'] == expect


# 5 x 3 at 1,500 W: a circuit carries 2 cabinets, a row is 2 + 2 + 1
SMALL = "window.__pn.screen({ columns: 5, rows: 3, panelWatts: 1500, powerFlowPattern: '%s'%s })"


def small(page, pattern, order=None):
    extra = ", powerNumberOrder: '%s'" % order if order else ''
    return cells(page, SMALL % (pattern, extra))['circuits']


def test_down_on_a_small_wall(page):
    assert small(page, 'tl-h') == [
        run(0, [0, 1]), run(0, [2, 3]), run(0, [4]),
        run(1, [0, 1]), run(1, [2, 3]), run(1, [4]),
        run(2, [0, 1]), run(2, [2, 3]), run(2, [4]),
    ]
    assert small(page, 'tl-h', 'down') == [
        run(0, [0, 1]), run(1, [0, 1]), run(2, [0, 1]),
        run(0, [2, 3]), run(1, [2, 3]), run(2, [2, 3]),
        run(0, [4]), run(1, [4]), run(2, [4]),
    ]


def test_down_bottom_start_climbs_each_stack(page):
    assert small(page, 'bl-h', 'down') == [
        run(2, [0, 1]), run(1, [0, 1]), run(0, [0, 1]),
        run(2, [2, 3]), run(1, [2, 3]), run(0, [2, 3]),
        run(2, [4]), run(1, [4]), run(0, [4]),
    ]


def test_down_right_start_steps_the_stacks_right_to_left(page):
    assert small(page, 'tr-h', 'down') == [
        run(0, [4, 3]), run(1, [4, 3]), run(2, [4, 3]),
        run(0, [2, 1]), run(1, [2, 1]), run(2, [2, 1]),
        run(0, [0]), run(1, [0]), run(2, [0]),
    ]
    assert small(page, 'br-h', 'down')[:3] == [run(2, [4, 3]), run(1, [4, 3]), run(0, [4, 3])]


def test_vertical_first_is_the_mirror_image(page):
    """3 x 5 at 1,500 W, tl-v: each column is 2 + 2 + 1 down. Across numbers
    along the top band of runs first; Down numbers down each column."""
    S = "window.__pn.screen({ columns: 3, rows: 5, panelWatts: 1500, powerFlowPattern: '%s'%s })"
    across = cells(page, S % ('tl-v', ", powerNumberOrder: 'across'"))['circuits']
    assert across == [
        col_run(0, [0, 1]), col_run(1, [0, 1]), col_run(2, [0, 1]),
        col_run(0, [2, 3]), col_run(1, [2, 3]), col_run(2, [2, 3]),
        col_run(0, [4]), col_run(1, [4]), col_run(2, [4]),
    ]
    down = cells(page, S % ('tl-v', ", powerNumberOrder: 'down'"))['circuits']
    assert down == [
        col_run(0, [0, 1]), col_run(0, [2, 3]), col_run(0, [4]),
        col_run(1, [0, 1]), col_run(1, [2, 3]), col_run(1, [4]),
        col_run(2, [0, 1]), col_run(2, [2, 3]), col_run(2, [4]),
    ]
    # no saved order on a vertical-first screen follows the flow: Down
    assert cells(page, S % ('tl-v', ''))['circuits'] == down
    # a right-start vertical pattern steps its band right to left
    tr = cells(page, S % ('tr-v', ", powerNumberOrder: 'across'"))['circuits']
    assert tr[:3] == [col_run(2, [0, 1]), col_run(1, [0, 1]), col_run(0, [0, 1])]


def test_down_with_a_z_pattern(page):
    """A cut row's runs read from the start side on a snake already, so a Z
    pattern cuts and numbers the same runs."""
    assert small(page, 'tl-h-z', 'down') == small(page, 'tl-h', 'down')
    assert small(page, 'br-h-z', 'down') == small(page, 'br-h', 'down')
    assert small(page, 'tl-h-z') == small(page, 'tl-h')


def test_split_with_z_on_the_90x5(page):
    z = cells(page, "window.__pn.repro({ powerFlowPattern: 'tl-h-z' })")
    assert z['error'] is None and z['cut'] is True
    assert z['circuits'] == cells(page, "window.__pn.repro()")['circuits']
    zr = cells(page, "window.__pn.repro({ powerFlowPattern: 'tr-h-z' })")
    assert [len(c) for c in zr['circuits']] == [22, 22, 22, 22, 2] * 5
    assert zr['circuits'][0] == run(0, range(89, 67, -1))
    assert zr['circuits'][4] == run(0, [1, 0])
    assert zr['circuits'][5][0] == [1, 89], 'row 2 starts again at the right'


def test_a_show_without_the_field_follows_the_flow(page):
    """No saved order follows the flow (the owner, 2026-11-01, as on the
    data side): Across on a horizontal-first pattern, Down on a
    vertical-first one - the walk's own order either way."""
    out = page.evaluate("""() => {
        const pn = window.__pn, app = window.app;
        const same = (S, order) => JSON.stringify(pn.cells(S).circuits)
            === JSON.stringify(pn.cells(Object.assign({}, S, { powerNumberOrder: order })).circuits);
        const H = pn.repro();
        delete H.powerNumberOrder;
        const V = pn.screen({ columns: 3, rows: 30, powerFlowPattern: 'bl-v-z' });
        // a custom screen reads the pattern it remembers
        const C = pn.screen({ powerFlowPattern: 'custom', lastPowerFlowPattern: 'tr-v' });
        return { h: app.powerNumberOrder(H), hSame: same(H, 'across'),
                 v: app.powerNumberOrder(V), vSame: same(V, 'down'),
                 c: app.powerNumberOrder(C),
                 saved: app.powerNumberOrder(Object.assign({}, V, { powerNumberOrder: 'across' })) };
    }""")
    assert out == {'h': 'across', 'hSame': True, 'v': 'down', 'vSame': True,
                   'c': 'down', 'saved': 'across'}


# ── 3. the switch in Power Settings ──────────────────────────────────────

def _api(base, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode() or 'null')


def test_switch_shows_only_where_a_row_is_cut_and_saves_down(page, e2e_server):
    out = page.evaluate("""async () => {
        const a = window.app;
        const post = (body) => fetch('/api/layer/add', { method: 'POST',
            headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(r => r.json());
        const add = async (name, cols, rows = 5, pattern = 'tl-h') => {
            const layer = await post({ name, columns: cols, rows, cabinet_width: 192, cabinet_height: 384,
                                       offset_x: 0, offset_y: 4000 + cols * 10 + rows * 1000 });
            a.initializeLayerDefaults(layer);
            a.setScreenVoltage(layer, 208);
            layer.powerAmperage = 20; layer.powerAmperageCustom = 20;
            layer.panelWatts = 150; layer.powerOrganized = true; layer.powerMaximize = false;
            layer.powerFlowPattern = pattern;
            a.upsertProjectLayer(layer);
            a.updateLayers([layer]);
            return a.project.layers.find(l => l.id === layer.id);
        };
        const wide = await add('PN WIDE', 90);
        const narrow = await add('PN NARROW', 10);
        // vertical first, columns of 30 cut 22 + 8, no saved order
        const tall = await add('PN TALL', 3, 30, 'tl-v');
        const row = document.getElementById('power-number-order-row');
        // the live layer objects: a server echo can replace them in the project
        const live = (l) => a.project.layers.find(x => x.id === l.id);
        const shown = (l) => { a.selectLayer(live(l)); a.loadLayerToInputs(); return row.style.display !== 'none'; };
        const lit = () => ['across', 'down'].filter(o =>
            document.getElementById('power-number-' + o).classList.contains('active'));
        const res = { field: wide.powerNumberOrder === undefined ? null : wide.powerNumberOrder };
        res.tallShown = shown(tall);
        res.tallLit = lit();
        res.tallField = live(tall).powerNumberOrder === undefined ? null : live(tall).powerNumberOrder;
        res.tallSecond = a.calculatePowerAssignments(live(tall)).circuits[1].map(p => [p.row, p.col])[0];
        res.narrowShown = shown(narrow);
        res.wideShown = shown(wide);
        res.acrossLit = document.getElementById('power-number-across').classList.contains('active');
        res.downLit = document.getElementById('power-number-down').classList.contains('active');
        document.getElementById('power-number-down').click();
        res.after = live(wide).powerNumberOrder;
        res.downLitAfter = document.getElementById('power-number-down').classList.contains('active');
        res.first2 = a.calculatePowerAssignments(live(wide)).circuits[1][0].row;
        res.id = wide.id;
        return res;
    }""")
    assert out['field'] is None, 'a new screen stores no Circuit numbers until it is set'
    # vertical first with no saved order follows the flow: Down is lit and
    # circuit 2 is column 1's second run, down the column
    assert out['tallShown'] is True and out['tallField'] is None
    assert out['tallLit'] == ['down'], out['tallLit']
    assert out['tallSecond'] == [22, 0], out['tallSecond']
    assert out['narrowShown'] is False, 'nothing is cut on a 10-wide row'
    assert out['wideShown'] is True
    assert out['acrossLit'] is True and out['downLit'] is False
    assert out['after'] == 'down' and out['downLitAfter'] is True, out
    assert out['first2'] == 1, 'circuit 2 starts row 2 under Down'
    # the PUT carried the field to the server
    page.wait_for_function("""(id) => fetch('/api/project').then(r => r.json()).then(p =>
        (p.layers || []).some(l => l.id === id && l.powerNumberOrder === 'down'))""", arg=out['id'],
        timeout=10000)
    proj = _api(e2e_server, 'GET', '/api/project')
    layer = next(l for l in proj['layers'] if l['id'] == out['id'])
    assert layer['powerNumberOrder'] == 'down'


# ── 4. the Z patterns ────────────────────────────────────────────────────

ORDER = ['tl-h', 'tr-h', 'bl-h', 'br-h', 'tl-v', 'tr-v', 'bl-v', 'br-v']


def walk(code, rows, cols):
    """The cabinet order a pattern walks, worked out here independently:
    lines from the start corner, every line in the first direction for a Z,
    every second line back for a snake."""
    corner, d = code.split('-')[:2]
    z = code.endswith('-z')
    top, left = corner[0] == 't', corner[1] == 'l'
    rs = list(range(rows)) if top else list(range(rows - 1, -1, -1))
    cs = list(range(cols)) if left else list(range(cols - 1, -1, -1))
    out = []
    if d == 'h':
        for i, r in enumerate(rs):
            line = cs if (z or i % 2 == 0) else cs[::-1]
            out.extend([r, c] for c in line)
    else:
        for i, c in enumerate(cs):
            line = rs if (z or i % 2 == 0) else rs[::-1]
            out.extend([r, c] for r in line)
    return out


@pytest.mark.parametrize('code', ORDER)
def test_each_z_pattern_walks_every_line_from_the_start_side(page, code):
    """4 x 3 at 150 W: one circuit carries the whole wall, so the circuit IS
    the walk - Organized and Maximize both - and the Z twin differs from
    its snake only in never running a line back."""
    for mode in ("powerOrganized: true, powerMaximize: false",
                 "powerOrganized: false, powerMaximize: true"):
        snake = cells(page, "window.__pn.screen({ powerFlowPattern: '%s', %s })" % (code, mode))
        zig = cells(page, "window.__pn.screen({ powerFlowPattern: '%s-z', %s })" % (code, mode))
        assert len(snake['circuits']) == 1 and len(zig['circuits']) == 1
        assert snake['circuits'][0] == walk(code, 3, 4), (code, mode)
        assert zig['circuits'][0] == walk(code + '-z', 3, 4), (code, mode)
        assert zig['circuits'][0][0] == snake['circuits'][0][0], 'same start corner'
        assert zig['circuits'][0] != snake['circuits'][0]


def test_z_circuits_of_two_rows_restart_at_the_start_side(page):
    """6 x 7 at 150 W shares three rows a circuit: on tl-h-z each of them
    runs left to right."""
    out = cells(page, "window.__pn.screen({ columns: 6, rows: 7, powerFlowPattern: 'tl-h-z' })")
    fwd = list(range(6))
    assert out['circuits'] == [run(0, fwd) + run(1, fwd) + run(2, fwd),
                               run(3, fwd) + run(4, fwd) + run(5, fwd), run(6, fwd)]


def test_unknown_pattern_codes_fall_back_as_before(page):
    """An odd code from an older show is no Z (helpers.js isZFlowPattern):
    its power walk is the snake it always was."""
    out = page.evaluate("""async () => {
        const { isZFlowPattern } = await import('/static/js/helpers.js');
        return ['tl-h-x', 'xx-h-z', 'tl-q-z', '', null, 'custom'].map(p => isZFlowPattern(p));
    }""")
    assert out == [False] * 6
    snake = cells(page, "window.__pn.screen({ powerFlowPattern: 'tl-h' })")['circuits']
    for odd in ('tl-h-x', 'tl-h-zz'):
        assert cells(page, "window.__pn.screen({ powerFlowPattern: '%s' })" % odd)['circuits'] == snake


def test_drawn_power_path_follows_the_z_order(page):
    """The daisy lines renderPowerArrows strokes for a Z screen run cabinet
    to cabinet in the walk's order: a diagonal return from each row's end
    to the next row's start, and never a snake turn down the side."""
    out = page.evaluate("""() => {
        const pn = window.__pn, cr = window.canvasRenderer;
        const ctxp = CanvasRenderingContext2D.prototype;
        const oBegin = ctxp.beginPath, oMove = ctxp.moveTo, oLine = ctxp.lineTo, oStroke = ctxp.stroke;
        const segs = [];
        let path = [];
        try {
            ctxp.beginPath = function () { path = []; return oBegin.call(this); };
            ctxp.moveTo = function (x, y) { path.push(['M', x, y]); return oMove.call(this, x, y); };
            ctxp.lineTo = function (x, y) { path.push(['L', x, y]); return oLine.call(this, x, y); };
            ctxp.stroke = function (...a) {
                if (path.length === 2 && path[0][0] === 'M' && path[1][0] === 'L') {
                    segs.push([path[0][1], path[0][2], path[1][1], path[1][2]]);
                }
                return oStroke.apply(this, a);
            };
            const S = pn.screen({ columns: 4, rows: 3, powerFlowPattern: 'tl-h-z' });
            pn.withProject({ layers: [S] }, () => cr.renderPowerArrows(S));
            return segs;
        } finally {
            ctxp.beginPath = oBegin; ctxp.moveTo = oMove; ctxp.lineTo = oLine; ctxp.stroke = oStroke;
        }
    }""")
    center = lambda rc: (rc[1] * 128 + 64, rc[0] * 128 + 64)
    order = walk('tl-h-z', 3, 4)
    expect = [center(a) + center(b) for a, b in zip(order, order[1:])]
    got = [tuple(s) for s in out]
    assert got == expect, got
    # the two returns are diagonals; no step runs straight down a side
    assert (448, 64, 64, 192) in got and (448, 192, 64, 320) in got
    assert not any(s[0] == s[2] for s in got), 'a vertical step is a snake turn'


def test_picker_has_sixteen_buttons_in_two_rows(page):
    out = page.evaluate("""() => {
        const btns = [...document.querySelectorAll('#power-flow-pattern-grid .power-flow-pattern-btn')];
        const grid = document.getElementById('power-flow-pattern-grid');
        return {
            codes: btns.map(b => b.getAttribute('data-pattern')),
            titles: btns.map(b => b.getAttribute('title')),
            tracks: grid.style.gridTemplateColumns,
            all: document.querySelectorAll('.power-flow-pattern-btn').length,
        };
    }""")
    assert out['codes'] == ORDER + [c + '-z' for c in ORDER]
    assert out['all'] == 16
    assert out['tracks'].startswith('repeat(8,'), out['tracks']
    assert out['titles'][8] == 'Top-left, horizontal first, every row starts at the left'
    assert out['titles'][9] == 'Top-right, horizontal first, every row starts at the right'
    assert out['titles'][14] == 'Bottom-left, vertical first, every column starts at the bottom'
    assert out['titles'][:2] == ['Top-left, horizontal first', 'Top-right, horizontal first']


def test_preferences_power_grid_offers_the_z_patterns(page):
    out = page.evaluate("""() => {
        const a = window.app;
        const grid = document.getElementById('pref-power-flow-pattern-grid');
        if (grid && !grid.children.length) a.setupPreferences && a.setupPreferences();
        return [...document.querySelectorAll('.pref-power-flow-pattern-btn')].map(b => b.getAttribute('data-pattern'));
    }""")
    assert out == ORDER + [c + '-z' for c in ORDER]


def test_custom_apply_pattern_follows_the_z_order(page):
    """The custom fill reads its lines the same way: a Z pattern never runs
    a line back (getPatternOrderForGrid and the per-run cut)."""
    out = page.evaluate("""() => {
        const a = window.app;
        const grid = [[{ id: 'a' }, { id: 'b' }, { id: 'c' }], [{ id: 'd' }, { id: 'e' }, { id: 'f' }]];
        const ids = (p) => a.getPatternOrderForGrid(p, grid).map(x => x.id).join('');
        return { snake: ids('tl-h'), z: ids('tl-h-z'), zv: ids('br-v-z'), v: ids('br-v') };
    }""")
    assert out == {'snake': 'abcfed', 'z': 'abcdef', 'zv': 'fcebda', 'v': 'fcbeda'}


# ── 5. a line cut differently from the stacks ───────────────────────────
#
# The owner's rulings, 2026-11-02: "Power will be the same" as the data
# side's Port numbers, and "columns always supersede row". On the owner's
# 85 x 5 shape with a bottom row of half-height cabinets, a full row of
# 150 W cabinets is cut 22 + 22 + 22 + 19 a circuit (3,328 W), the half
# row (75 W a cabinet) 44 + 41. Down numbers each stack's own rows, and a
# circuit of the half row takes the number right after the stack its
# FIRST cabinet sits under: 1-4 the first stack, 5 the half row's first
# circuit, 6-9, 10-13, then 14 the half row's second circuit (it starts
# at column 45, under the third stack), then 15-18. Every start corner
# counts from where the wall is cabled: a right start numbers from the
# right edge and walks left.

HALF_BOTTOM = "window.__pn.repro({ columns: 85, halfRow: %s, powerFlowPattern: '%s'%s })"
HALF_RIGHT = """window.__pn.repro({ columns: 5, rows: 85, cabinet_width: 384,
    cabinet_height: 192, halfCol: 4, powerFlowPattern: '%s', powerNumberOrder: '%s' })"""


def half(page, pattern='tl-h', order='down', half_row=4):
    return cells(page, HALF_BOTTOM % (half_row, pattern, ", powerNumberOrder: '%s'" % order))


def expect_by_stacks(pattern, lines, length, by_stack=True):
    """The order worked out here on its own. `lines` in walk order, each
    (line, cabinets a circuit). Every line is cut from the pattern's start
    side; a circuit's stack is the stack of the most finely cut lines its
    first cabinet sits in. By stacks: stack, then walk order; otherwise
    walk order."""
    vertical = '-v' in pattern
    forward = pattern.startswith('t') if vertical else 'l-' in pattern
    along = list(range(length)) if forward else list(range(length - 1, -1, -1))
    stack_len = min(per for _, per in lines)
    keyed = []
    for walk_at, (line, per) in enumerate(lines):
        for seg, start in enumerate(range(0, length, per)):
            span = along[start:start + per]
            got = col_run(line, span) if vertical else run(line, span)
            keyed.append(((start // stack_len) if by_stack else walk_at, walk_at, seg, got))
    keyed.sort(key=lambda k: k[:3])
    return [k[3] for k in keyed]


def bottom_lines(pattern, half_row=4, rows=5):
    order = list(range(rows)) if pattern.startswith('t') else list(range(rows - 1, -1, -1))
    return [(r, 44 if r == half_row else 22) for r in order]


def test_down_puts_a_half_row_circuit_under_the_stack_it_starts_in(page):
    out = half(page)
    assert out['error'] is None and out['cut'] is True
    got = out['circuits']
    assert len(got) == 4 * 4 + 2
    assert got[:5] == [run(r, range(22)) for r in range(4)] + [run(4, range(44))]
    assert got[5:9] == [run(r, range(22, 44)) for r in range(4)]
    assert got[9:13] == [run(r, range(44, 66)) for r in range(4)]
    assert got[13] == run(4, range(44, 85)), 'circuit 14 starts under the third stack'
    assert got[14:] == [run(r, range(66, 85)) for r in range(4)]
    # the same circuits as Across; only the numbers moved
    across = half(page, order='across')['circuits']
    assert sorted(map(json.dumps, got)) == sorted(map(json.dumps, across))


@pytest.mark.parametrize('pattern', ['tl-h', 'tr-h', 'bl-h', 'br-h',
                                     'tl-h-z', 'tr-h-z', 'bl-h-z', 'br-h-z'])
def test_a_half_row_follows_the_start_corner(page, pattern):
    """Every corner: a right start counts the stacks from the right edge
    and walks left, a bottom start climbs, and the half row (the first
    line on a bottom start) numbers first in each stack it starts under."""
    got = half(page, pattern)['circuits']
    assert got == expect_by_stacks(pattern, bottom_lines(pattern), 85)
    assert got[0][0] == [0 if pattern.startswith('t') else 4, 0 if 'l-' in pattern else 84]


def test_a_differently_cut_top_row_comes_first_in_its_stack(page):
    got = half(page, half_row=0)['circuits']
    assert got[:5] == [run(0, range(44))] + [run(r, range(22)) for r in range(1, 5)]
    assert got[5:9] == [run(r, range(22, 44)) for r in range(1, 5)]
    assert got[9] == run(0, range(44, 85))
    assert got[10:14] == [run(r, range(44, 66)) for r in range(1, 5)]


@pytest.mark.parametrize('pattern', ['tl-h', 'tr-h', 'bl-h', 'br-h'])
def test_across_with_a_half_row_numbers_along_the_rows_from_the_start(page, pattern):
    got = half(page, pattern, order='across')['circuits']
    assert got == expect_by_stacks(pattern, bottom_lines(pattern), 85, by_stack=False)
    assert got[0][0] == [0 if pattern.startswith('t') else 4, 0 if 'l-' in pattern else 84]


@pytest.mark.parametrize('pattern', ['tl-v', 'tr-v', 'bl-v', 'br-v'])
def test_vertical_half_column_numbers_from_the_start_corner(page, pattern):
    """The vertical mirror: 5 columns of 85, the last half-width. Across
    numbers each band of the full columns, and a half column's circuit
    joins the band its first cabinet sits in; Down numbers down each
    column. A right start steps the columns right to left, a bottom start
    counts each column up from the bottom."""
    cols = list(range(5)) if 'l-' in pattern else list(range(4, -1, -1))
    lines = [(c, 44 if c == 4 else 22) for c in cols]
    across = cells(page, HALF_RIGHT % (pattern, 'across'))['circuits']
    assert across == expect_by_stacks(pattern, lines, 85)
    down = cells(page, HALF_RIGHT % (pattern, 'down'))['circuits']
    assert down == expect_by_stacks(pattern, lines, 85, by_stack=False)
    assert across[0][0] == down[0][0] == [0 if pattern.startswith('t') else 84,
                                          0 if 'l-' in pattern else 4]


def test_a_half_row_shares_as_before_and_numbers_by_its_stack(page):
    """Splitters on, 90 wide: the half row is cut 44 + 44 + 2. Its
    2-cabinet leftover at columns 88-89 is the circuit of its own it
    always was (the packing reads every piece by its place along its row,
    so no cabinet changes circuit); Down numbers it with the stack it
    sits under, the last, after the leftovers above it."""
    S = """window.__pn.repro({ halfRow: 4, powerNumberOrder: '%s',
        powerSplitters: { enabled: true, maxWays: 3, manual: { merge: [], split: [] } } })"""
    down = cells(page, S % 'down')
    across = cells(page, S % 'across')
    assert down['error'] is None and down['cut'] is True
    assert sorted(map(json.dumps, down['circuits'])) == sorted(map(json.dumps, across['circuits']))
    assert down['circuits'][-1] == run(4, [88, 89])
    assert [c[0] for c in down['circuits'][:5]] == [[r, 0] for r in range(5)]
    # the half row's second circuit starts at column 44, under the third stack
    assert [c[0] for c in down['circuits'][9:14]] == [[r, 44] for r in range(5)]


# ── 6. custom power follows the switch ──────────────────────────────────
#
# The owner's ruling, 2026-11-02: custom power follows Down like data. A
# custom power screen shows the Circuit numbers switch wherever Apply
# Pattern would cut a line, and Apply Pattern numbers the circuits it cuts
# by stacks when Down is picked (Across on a vertical pattern), through
# the same _stackSplitRuns the data fill and the automatic walk use. Which
# cabinets share a 2fer or 3fer never changes, only the numbers, and the
# circuits already drawn keep theirs, as on the data side.

CUSTOM_JS = """
window.__pn.withApp = function (S, fn) {
    const app = window.app, r = window.canvasRenderer;
    const keys = ['project', 'currentLayer', 'selectedLayerIds', 'powerCustomSelection',
        'history', 'historyIndex', 'updateLayers', 'renderLayers', 'loadLayerToInputs',
        'saveClientSideProperties', '_toast', '_overrideEditing', '_circuitTailCache'];
    const saved = {};
    keys.forEach(k => { saved[k] = app[k]; });
    const view = r.viewMode;
    app.updateLayers = () => {};
    app.renderLayers = () => {};
    app.loadLayerToInputs = () => {};
    app.saveClientSideProperties = () => {};
    app._toast = () => {};
    S.canvas_id = 'c1';
    app.project = {
        layers: [S], groups: [], rack: [],
        canvases: [{ id: 'c1', name: 'Canvas 1', workspace_x: 0, workspace_y: 0,
            show_workspace_x: 0, show_workspace_y: 0,
            raster_width: 32768, raster_height: 32768,
            show_raster_width: 32768, show_raster_height: 32768,
            color: '#ff0000', visible: true }],
        active_canvas_id: 'c1',
    };
    app.currentLayer = S;
    app.selectedLayerIds = new Set([S.id]);
    app.powerCustomSelection = new Set();
    app.history = []; app.historyIndex = -1;
    app._overrideEditing = null;
    app._circuitTailCache = null;
    r.viewMode = 'power';
    try { return fn(app); } finally {
        keys.forEach(k => { app[k] = saved[k]; });
        r.viewMode = view;
        r.render();
    }
};
// Custom Apply Pattern on S: every cabinet `pick` keeps (all by default)
// selected, then `pattern` pressed. The drawn circuits by number, the
// shares the fill wrote, and the circuit left active.
window.__pn.fill = function (S, pattern, pick) {
    S.powerFlowPattern = 'custom';
    S.powerCustomPaths = {};
    S.powerCustomIndex = 1;
    S.powerCustomOverrides = [];
    return this.withApp(S, app => {
        S.panels.forEach(p => {
            if (!pick || pick(p)) app.powerCustomSelection.add(app.getScopedPanelKey(S.id, p));
        });
        app.applyPowerPatternToSelection(pattern);
        const paths = S.powerCustomPaths || {};
        const nums = Object.keys(paths).map(Number).sort((a, b) => a - b);
        const manual = S.powerSplitters && S.powerSplitters.manual;
        return {
            nums,
            drawn: nums.map(n => paths[n].map(e => [e.row, e.col])),
            merges: manual ? manual.merge : [],
            active: S.powerCustomIndex,
        };
    });
};
// (a string that ends on a function would be called by page.evaluate)
true;
"""


def custom_fill(page, screen_js, pattern, pick='null'):
    page.evaluate(CUSTOM_JS)
    return page.evaluate("() => window.__pn.fill(%s, '%s', %s)" % (screen_js, pattern, pick))


@pytest.mark.parametrize('pattern', ['tl-h', 'tr-h', 'bl-h', 'br-h'])
def test_custom_down_numbers_a_half_row_by_its_stack(page, pattern):
    """Apply Pattern over the owner's 85 x 5 shape on Down: circuits 1-4
    the first stack, 5 the half row's first circuit, 6-9, 10-13, 14 the
    half row's second circuit, 15-18; the automatic walk's own Down map."""
    screen = HALF_BOTTOM % (4, pattern, ", powerNumberOrder: 'down'")
    out = custom_fill(page, screen, pattern)
    assert out['nums'] == list(range(1, 19)), out['nums']
    assert out['active'] == 18
    got = out['drawn']
    assert got == expect_by_stacks(pattern, bottom_lines(pattern), 85)
    assert got == half(page, pattern)['circuits'], 'the automatic Down map'
    if pattern == 'tl-h':
        assert got[:5] == [run(r, range(22)) for r in range(4)] + [run(4, range(44))]
        assert got[5:9] == [run(r, range(22, 44)) for r in range(4)]
        assert got[13] == run(4, range(44, 85)), 'circuit 14 starts under the third stack'
        assert got[14:] == [run(r, range(66, 85)) for r in range(4)]


@pytest.mark.parametrize('pattern', ['tl-h', 'br-h'])
def test_custom_across_and_a_screen_never_switched_number_along_the_rows(page, pattern):
    expect = expect_by_stacks(pattern, bottom_lines(pattern), 85, by_stack=False)
    across = custom_fill(page, HALF_BOTTOM % (4, pattern, ", powerNumberOrder: 'across'"), pattern)
    assert across['drawn'] == expect
    assert across['drawn'] == half(page, pattern, order='across')['circuits']
    unset = custom_fill(page, HALF_BOTTOM % (4, pattern, ''), pattern)
    assert unset['drawn'] == expect, 'a horizontal fill on a screen never switched is Across'


@pytest.mark.parametrize('pattern', ['tl-v', 'br-v'])
def test_custom_vertical_fill_follows_across_and_down(page, pattern):
    """The vertical mirror: Across stacks a half column's circuit into the
    band it starts in, Down numbers down each column."""
    cols = list(range(5)) if 'l-' in pattern else list(range(4, -1, -1))
    lines = [(c, 44 if c == 4 else 22) for c in cols]
    across = custom_fill(page, HALF_RIGHT % (pattern, 'across'), pattern)['drawn']
    assert across == expect_by_stacks(pattern, lines, 85)
    assert across == cells(page, HALF_RIGHT % (pattern, 'across'))['circuits']
    down = custom_fill(page, HALF_RIGHT % (pattern, 'down'), pattern)['drawn']
    assert down == expect_by_stacks(pattern, lines, 85, by_stack=False)


def test_custom_sharing_fill_keeps_its_2fers_and_numbers_down(page):
    """Splitters on, maxWays 3: rows 1-3 selected whole (85 wide, cut
    22 + 22 + 22 + 19, pieces that never share) and rows 4-5 ten wide
    (1,500 W each, one 2fer). Down numbers the cut pieces down the stacks;
    the 2fer is the same two runs on the same two numbers either way."""
    screen = """window.__pn.repro({ columns: 85, powerNumberOrder: '%s',
        powerSplitters: { enabled: true, maxWays: 3, manual: { merge: [], split: [] } } })"""
    pick = "(p => p.row < 3 || p.col < 10)"
    down = custom_fill(page, screen % 'down', 'tl-h', pick)
    across = custom_fill(page, screen % 'across', 'tl-h', pick)
    for out in (down, across):
        assert out['nums'] == list(range(1, 15)), out['nums']
        assert out['merges'] == [[13, 14]], out['merges']
        assert out['drawn'][12:] == [run(3, range(10)), run(4, range(10))]
    assert sorted(map(json.dumps, down['drawn'])) == sorted(map(json.dumps, across['drawn']))
    assert across['drawn'][:4] == [run(0, range(s, min(s + 22, 85))) for s in (0, 22, 44, 66)]
    assert down['drawn'][:3] == [run(r, range(22)) for r in range(3)]
    assert down['drawn'][3:6] == [run(r, range(22, 44)) for r in range(3)]
    assert down['drawn'][9:12] == [run(r, range(66, 85)) for r in range(3)]


def test_switch_shows_on_custom_power_screens(page):
    page.evaluate(CUSTOM_JS)
    out = page.evaluate("""() => {
        const pn = window.__pn;
        const drawn = { 1: [{ row: 0, col: 0 }, { row: 0, col: 1 }] };
        const cases = {
            drawn: { powerCustomPaths: drawn },
            drawnDown: { powerCustomPaths: drawn, powerNumberOrder: 'down' },
            remembersVertical: { powerCustomPaths: drawn, lastPowerFlowPattern: 'tl-v' },
            empty: {},
            maximize: { powerCustomPaths: drawn, powerMaximize: true, powerOrganized: false },
            narrow: { powerCustomPaths: drawn, columns: 10 },
        };
        const res = {};
        Object.keys(cases).forEach(k => {
            const S = pn.repro(Object.assign({ columns: 85, halfRow: 4 }, cases[k],
                { powerFlowPattern: 'custom', powerCustomIndex: 1 }));
            res[k] = pn.withApp(S, app => {
                const before = JSON.stringify(S);
                app.syncPowerNumberOrder(S);
                const row = document.getElementById('power-number-order-row');
                return {
                    shown: row.style.display !== 'none',
                    lit: ['across', 'down'].filter(o =>
                        document.getElementById('power-number-' + o).classList.contains('active')),
                    untouched: JSON.stringify(S) === before,
                };
            });
        });
        return res;
    }""")
    for k in ('drawn', 'drawnDown', 'remembersVertical', 'empty'):
        assert out[k]['shown'] is True, (k, out[k])
    assert out['drawn']['lit'] == ['across']
    assert out['drawnDown']['lit'] == ['down']
    assert out['remembersVertical']['lit'] == ['down'], 'unset follows the remembered flow'
    assert out['maximize']['shown'] is False
    assert out['narrow']['shown'] is False, 'nothing is cut on a 10-wide wall'
    assert all(v['untouched'] for v in out.values()), out


def test_switching_keeps_the_circuits_already_drawn(page):
    """Like the data side, the switch decides how the NEXT Apply Pattern
    numbers; circuits drawn by hand or by an earlier fill keep theirs."""
    page.evaluate(CUSTOM_JS)
    out = page.evaluate("""() => {
        const pn = window.__pn;
        const S = pn.repro({ columns: 85, halfRow: 4, powerNumberOrder: 'down' });
        const first = pn.fill(S, 'tl-h');
        S.powerNumberOrder = 'across';
        return pn.withApp(S, app => {
            const after = Object.keys(S.powerCustomPaths).map(Number).sort((a, b) => a - b)
                .map(n => S.powerCustomPaths[n].map(e => [e.row, e.col]));
            return { first: first.drawn, after,
                     circuits: app.screenCircuits(S).map(c => c.panels.map(p => [p.row, p.col])) };
        });
    }""")
    assert out['after'] == out['first']
    assert out['circuits'] == out['first']
