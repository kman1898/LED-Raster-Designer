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
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
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
        const panels = [];
        for (let r = 0; r < o.rows; r++) {
            for (let c = 0; c < o.columns; c++) {
                panels.push({
                    row: r, col: c,
                    x: o.offset_x + c * o.cabinet_width,
                    y: o.offset_y + r * o.cabinet_height,
                    width: o.cabinet_width, height: o.cabinet_height,
                    hidden: false, blank: false, halfTile: 'none',
                });
            }
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
