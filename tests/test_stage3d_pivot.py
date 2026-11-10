"""The 3D tab's Y from the bottom edge, its turning point, its own ft | m
switch, and the header and footer bars against the panels (the owner's
rulings, 2026-11-09).

* Y is the height of a screen's bottom edge: a screen on the floor reads 0.
  X and Z are the middle of that edge. Pitch, yaw and roll turn the screen
  about that point, so a screen on the floor stays on it.
* stage3d stores that point, the panels' bottom middle, with `pivot:
  'bottom'`. A block without the marker (the first 1.7.0 betas stored the
  centre) is read as the centre and moved to the bottom middle by the
  screen's own shape and turn: every cabinet stands where it stood. The
  proof is tests/data/stage3d_centre_blocks.json, every cabinet corner as
  those betas stood it, computed with app-stage3d.js at ff788956.
* With a footer, Y measures from the footer's bottom: a footer on the floor
  reads 0 and the panels start 6 in up. The stored point stays the panels'
  edge, so a footer added or taken away leaves the panels where they are.
* Header bars stand 3.5 in tall and footer bars 6 in, against the panels.
* The ft | m switch beside Position sets the 3D panel's units only: X, Y,
  Z, the snap, the figure beside the cursor, the nudges. It is saved with
  the show (stage3dUnits), starts on the show's own unit, is not an undo
  step, and changes nothing else in the show.

Run locally:
    python -m pytest tests/test_stage3d_pivot.py -p no:cacheprovider
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from conftest import settled  # noqa: E402

import app as app_module  # noqa: E402

FT = 304.8
CENTRE_BLOCKS = os.path.join(os.path.dirname(__file__), 'data', 'stage3d_centre_blocks.json')


def _centre_cases():
    with open(CENTRE_BLOCKS, encoding='utf-8') as fh:
        return json.load(fh)['cases']


# ── the server keeps the marker as it came ───────────────────────────────

def test_the_server_keeps_the_bottom_marker_and_never_adds_it():
    marked = app_module.sanitize_stage3d({'x': 1, 'y': 2, 'z': 3, 'pivot': 'bottom'})
    assert marked['pivot'] == 'bottom'
    assert app_module.sanitize_stage3d(marked) == marked
    # an old block stays an old block: only the client knows the shape
    old = app_module.sanitize_stage3d({'x': 1, 'y': 2, 'z': 3})
    assert 'pivot' not in old
    for junk in ('centre', 'BOTTOM', 1, True, None):
        assert 'pivot' not in app_module.sanitize_stage3d({'x': 1, 'pivot': junk})


# ── the browser ──────────────────────────────────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project as this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1500, 'height': 900})
    context.add_init_script("try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.errors = []
    pg.on('pageerror', lambda err: pg.errors.append(str(err)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app._initialLoadComplete")
    pg.wait_for_timeout(1200)
    yield pg
    context.close()


# Exactly the screens asked for (128 px, 500 mm cabinets), each with its
# hidden cabinets, half last column and stage3d block when asked; history
# rebased so a test's own edits are the only steps.
RESET_JS = """async ([specs, cableUnit]) => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    let project = await j('GET', '/api/project');
    project.layers = [];
    project.groups = [];
    project.cableUnit = cableUnit || 'ft';
    for (const k of ['stage3dCamera', 'stage3dUnits', 'stage3dGrid', 'stage3dBars']) delete project[k];
    await j('PUT', '/api/project', project);
    const ids = [];
    for (const s of specs) {
        const made = await j('POST', '/api/layer/add', Object.assign({
            cabinet_width: 128, cabinet_height: 128, panel_width_mm: 500, panel_height_mm: 500,
        }, {name: s.name, columns: s.columns, rows: s.rows, offset_x: s.offset_x || 0, offset_y: s.offset_y || 0}));
        ids.push(made.id);
        const lay = (await j('GET', '/api/project')).layers.find(l => l.id === made.id);
        const pick = (r, c) => lay.panels.find(p => p.row === r && p.col === c).id;
        if (s.hidden && s.hidden.length) {
            await j('POST', `/api/layer/${made.id}/panels/set_hidden`,
                {panels: s.hidden.map(([r, c]) => ({id: pick(r, c), hidden: true}))});
        }
        if (s.halfLastCol) {
            const rows = [...Array(s.rows).keys()];
            await j('POST', `/api/layer/${made.id}/panels/set_half_tile`,
                {panels: rows.map(r => ({id: pick(r, s.columns - 1), halfTile: 'width'}))});
        }
        const extra = {};
        if (s.stage3d) extra.stage3d = s.stage3d;
        if (s.footer) extra.riggingFooterBars = s.footer;
        if (s.header) extra.riggingBars = s.header;
        if (Object.keys(extra).length) await j('PUT', `/api/layer/${made.id}`, extra);
    }
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('stage3d_pivot_reset');
    if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
    app.resetHistory('Stage3D Pivot Reset');
    app.selectLayer(app.project.layers.find(l => l.id === ids[0]));
    app.updateUI();
    return ids;
}"""


def reset(page, specs, cable_unit='ft'):
    page.evaluate("""() => { const t = document.querySelector('#view-tabs .view-tab[data-mode="pixel-map"]');
        if (t) t.click(); }""")
    page.wait_for_timeout(150)
    ids = page.evaluate(RESET_JS, [specs, cable_unit])
    page.wait_for_timeout(300)
    return ids


def dbg(page):
    return page.evaluate('window.app._s3dDebug()')


def screen(page, layer_id):
    return next((s for s in dbg(page)['screens'] if s['id'] == layer_id), None)


def open_3d(page, count):
    page.click('#view-tabs .view-tab[data-mode="3d"]')
    got = settled(page, lambda: dbg(page),
                  lambda d: d['loaded'] and len(d['screens']) == count
                  and all(s['tex'] for s in d['screens']), 10000)
    assert got['loaded'] and len(got['screens']) == count, got
    return got


def view_from(page, name):
    page.click(f'[data-s3d-view="{name}"]')
    return settled(page, lambda: dbg(page), lambda d: not d['gliding'], 3000)


def stored(page, layer_id):
    return page.evaluate("""(id) => { const l = window.app.project.layers.find(x => x.id === id);
        return l ? (l.stage3d || null) : null; }""", layer_id)


def served(page, layer_id):
    return page.evaluate("""async (id) => { const p = await (await fetch('/api/project')).json();
        const l = p.layers.find(x => x.id === id); return l ? (l.stage3d || null) : null; }""", layer_id)


def corners(page, layer_id):
    return page.evaluate(f"window.app._s3dDebugCorners({layer_id})")


def field(page, name):
    return page.input_value(f'#s3d-{name}')


def type_field(page, name, value):
    page.fill(f'#s3d-{name}', value)
    page.press(f'#s3d-{name}', 'Enter')
    page.wait_for_timeout(400)


def history_len(page):
    return page.evaluate('window.app.history.length')


def undo(page):
    page.evaluate('window.app.undo()')
    page.wait_for_timeout(600)


def redo(page):
    page.evaluate('window.app.redo()')
    page.wait_for_timeout(600)


def reload(page):
    page.reload(wait_until='domcontentloaded')
    page.wait_for_function("() => window.app && window.app._initialLoadComplete")
    page.wait_for_timeout(1200)


def handles(page):
    return settled(page, lambda: dbg(page)['handles'], lambda h: h and h['shown'] and h['grips'], 3000)


def drag(page, start, end, keys=(), before_up=None):
    page.mouse.move(*start)
    for k in keys:
        page.keyboard.down(k)
    page.mouse.down()
    steps = 12
    for i in range(1, steps + 1):
        page.mouse.move(start[0] + (end[0] - start[0]) * i / steps, start[1] + (end[1] - start[1]) * i / steps)
        page.wait_for_timeout(16)
    if before_up:
        before_up()
    page.mouse.up()
    for k in keys:
        page.keyboard.up(k)
    page.wait_for_timeout(400)


def grip_drag(page, name, by, keys=(), before_up=None):
    g = handles(page)['grips'][name]
    drag(page, g, (g[0] + by[0], g[1] + by[1]), keys=keys, before_up=before_up)


def close(a, b, tol=0.01):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def bottom_middle(cs):
    """The middle of a flat, unbent screen's bottom edge from its cabinet
    corners: halfway along the bottom row's outer bottom corners."""
    last = max(c['row'] for c in cs)
    row = [c for c in cs if c['row'] == last]
    left = min(row, key=lambda c: c['col'])['corners'][3]
    right = max(row, key=lambda c: c['col'])['corners'][2]
    return [(left[i] + right[i]) / 2 for i in range(3)]


ONE = [{'name': 'Wall', 'columns': 4, 'rows': 2}]


# ── 1. the placement math, pure ───────────────────────────────────────────

def test_old_centre_blocks_resolve_to_the_same_corners(page):
    """Every old block, and the same block once a commit has rounded its
    bottom middle to the stored thousandth of a mm, stands every cabinet
    corner within 0.01 mm of where the first betas stood it."""
    got = page.evaluate("""async (cases) => {
        const m = await import('/static/js/app-stage3d.js');
        return cases.map(c => {
            const r = m.s3dResolve(c.layer, c.block);
            const rounded = {...r, x: Math.round(r.x * 1000) / 1000, y: Math.round(r.y * 1000) / 1000,
                             z: Math.round(r.z * 1000) / 1000};
            return {name: c.name, pivot: r.pivot, raw: m.s3dWorldCorners(c.layer, c.block),
                    rounded: m.s3dWorldCorners(c.layer, rounded),
                    resolved: r, again: m.s3dResolve(c.layer, r)};
        });
    }""", _centre_cases())
    for case, out in zip(_centre_cases(), got):
        assert out['pivot'] == 'bottom', out['name']
        # a block read once is read the same way again
        assert out['again'] == out['resolved'], out['name']
        for key in ('raw', 'rounded'):
            mine = {(q['row'], q['col']): q['corners'] for q in out[key]}
            assert len(mine) == len(case['corners']), (case['name'], key)
            for want in case['corners']:
                have = mine[(want['row'], want['col'])]
                for a, b in zip(have, want['corners']):
                    assert close(a, b), (case['name'], key, want['row'], want['col'], a, b)


def test_the_bottom_middle_and_the_footer_datum(page):
    out = page.evaluate("""async () => {
        const m = await import('/static/js/app-stage3d.js');
        const grid = (cols, rows) => {
            const panels = [];
            for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
                panels.push({row: r, col: c, x: c * 128, y: r * 128, width: 128, height: 128});
            }
            return {type: 'screen', cabinet_width: 128, cabinet_height: 128,
                    panel_width_mm: 500, panel_height_mm: 500, panels};
        };
        const wall = grid(4, 2);
        const flat = {x: 0, y: 0, z: 0, pitch: 0, yaw: 0, roll: 0, curveCol: 0, curveRow: 0, jointsCol: {}, jointsRow: {}};
        const pitched = {...flat, x: 100, y: 200, z: 300, pitch: 25, yaw: -40, roll: 10, pivot: 'bottom'};
        const footed = m.s3dShown(wall, pitched, m.FOOTER_BAR_MM);
        return {
            base: m.s3dBaseOffset(wall, flat),
            bentBase: m.s3dBaseOffset(wall, {...flat, curveRow: 10}),
            curvedAcrossBase: m.s3dBaseOffset(wall, {...flat, curveCol: 12}),
            oldCentre: m.s3dResolve(wall, {...flat, y: 500}),
            footerFlat: m.s3dDatumOffset(wall, flat, m.FOOTER_BAR_MM),
            noFooter: m.s3dDatumOffset(wall, flat, 0),
            footed, back: m.s3dStoredFrom(wall, footed, m.FOOTER_BAR_MM),
            heights: [m.HEADER_BAR_MM, m.FOOTER_BAR_MM],
            footerOf: [m.s3dFooterMm({riggingFooterBars: [2, 2]}), m.s3dFooterMm({riggingBars: [2, 2]}),
                       m.s3dFooterMm({}, [{row: 'footer', bars: [{start: -1, size: 2}]}]),
                       m.s3dFooterMm({riggingFooterBars: [2]}, [])],
        };
    }""")
    # flat: half the height straight down from the centre
    assert out['base'] == pytest.approx([0, -500, 0])
    # a column curve leaves the bottom middle under the middle column
    assert out['curvedAcrossBase'] == pytest.approx([0, -500, 0])
    # a row bend brings the foot of the bottom row forward
    assert out['bentBase'][1] > -500 and out['bentBase'][2] > 0
    # an old centre 500 mm up on a 1000 mm wall stands its bottom edge on 0
    assert (out['oldCentre']['y'], out['oldCentre']['pivot']) == (pytest.approx(0), 'bottom')
    assert out['footerFlat'] == pytest.approx([0, -152.4, 0])
    assert out['noFooter'] == [0, 0, 0]
    back = out['back']
    assert (back['x'], back['y'], back['z']) == pytest.approx((100, 200, 300), abs=1e-9)
    assert out['heights'] == [88.9, 152.4]
    # the footer counts, its own or a group row's part; a header never does
    assert out['footerOf'] == [152.4, 0, 152.4, 0]


def test_lengths_typed_with_their_units(page):
    got = page.evaluate("""async () => {
        const m = await import('/static/js/app-stage3d.js');
        const texts = ['2m', '250 mm', '35cm', `6'6"`, `12' 6"`, `-12' 6"`, `12' 6`, '6 ft 6 in', '18 in',
                       '10', '10+2.5', 'abc', '5mm3'];
        const ev = (t) => { try { return Function('return (' + t + ')')(); } catch (e) { return NaN; } };
        return texts.map(t => [t, m.s3dParseLength(t, 'ft', ev), m.s3dParseLength(t, 'm', ev)]);
    }""")
    want = {
        '2m': 2000, '250 mm': 250, '35cm': 350, "6'6\"": 6 * FT + 6 * 25.4, "12' 6\"": 12 * FT + 6 * 25.4,
        "-12' 6\"": -(12 * FT + 6 * 25.4), "12' 6": 12 * FT + 6 * 25.4, '6 ft 6 in': 6 * FT + 6 * 25.4,
        '18 in': 18 * 25.4,
    }
    for text, ft, m in got:
        if text in want:
            # a figure with its own unit reads the same in either panel unit
            assert ft == pytest.approx(want[text]) and m == pytest.approx(want[text]), text
    rows = {t: (ft, m) for t, ft, m in got}
    assert rows['10'] == (pytest.approx(10 * FT), pytest.approx(10000))
    assert rows['10+2.5'] == (pytest.approx(12.5 * FT), pytest.approx(12500))
    assert rows['abc'] == (None, None) and rows['5mm3'] == (None, None)


# ── 2. old shows ─────────────────────────────────────────────────────────

def test_an_old_show_opens_with_every_screen_where_it_stood(page):
    cases = _centre_cases()
    specs = [dict(c['spec'], name=f'Old {i}', offset_x=i * 2000, stage3d=c['block'])
             for i, c in enumerate(cases)]
    ids = reset(page, specs)
    open_3d(page, len(ids))
    for layer_id, case in zip(ids, cases):
        have = {(q['row'], q['col']): q['corners'] for q in corners(page, layer_id)}
        assert len(have) == len(case['corners']), case['name']
        for want in case['corners']:
            for a, b in zip(have[(want['row'], want['col'])], want['corners']):
                assert close(a, b), (case['name'], want['row'], want['col'], a, b)
        # looking writes nothing: the old block stays as it was saved
        assert 'pivot' not in stored(page, layer_id)
        assert 'pivot' not in served(page, layer_id)
    # the first edit writes the bottom middle, and nothing moves: the
    # screen bent both ways, its column figure typed again as it reads
    first = ids[2]
    before = corners(page, first)
    page.evaluate(f"window.app.selectLayer(window.app.project.layers.find(l => l.id === {first}))")
    page.wait_for_timeout(200)
    assert field(page, 'curve-col') == '-5'
    type_field(page, 'curve-col', '-5.0')       # the same figure, typed afresh
    after_block = settled(page, lambda: served(page, first), lambda v: v and v.get('pivot') == 'bottom')
    assert after_block['pivot'] == 'bottom' and after_block == stored(page, first)
    page.wait_for_timeout(300)
    for a, b in zip(corners(page, first), before):
        for p, q in zip(a['corners'], b['corners']):
            assert close(p, q), (p, q)
    assert page.errors == []


# ── 3. Y from the bottom edge ─────────────────────────────────────────────

def test_a_new_screen_stands_on_the_floor_at_y_0(page):
    ids = reset(page, [{'name': 'Wall', 'columns': 4, 'rows': 2},
                       {'name': 'Upper', 'columns': 2, 'rows': 2, 'offset_x': 0, 'offset_y': -600}])
    open_3d(page, 2)
    wall = screen(page, ids[0])
    assert not wall['stored']
    assert wall['placement']['y'] == pytest.approx(0) and wall['placement']['pivot'] == 'bottom'
    assert wall['world']['min'][1] == pytest.approx(0, abs=0.01)
    assert field(page, 'y') == '0.00'
    # X is the middle of the bottom edge
    assert wall['placement']['x'] == pytest.approx((wall['world']['min'][0] + wall['world']['max'][0]) / 2)
    # a screen Show Look stands higher reads its bottom edge's height
    up = screen(page, ids[1])
    assert up['placement']['y'] == pytest.approx(600 * 500 / 128, abs=0.01)
    assert up['world']['min'][1] == pytest.approx(up['placement']['y'], abs=0.01)
    assert stored(page, ids[0]) is None


def test_typing_y_sets_the_bottom_edge_and_undoes_and_reopens(page):
    ids = reset(page, ONE)
    open_3d(page, 1)
    start = history_len(page)
    type_field(page, 'y', '3')
    got = stored(page, ids[0])
    assert got['y'] == pytest.approx(3 * FT) and got['pivot'] == 'bottom'
    s = settled(page, lambda: screen(page, ids[0]), lambda v: v['world']['min'][1] > 1)
    assert s['world']['min'][1] == pytest.approx(3 * FT, abs=0.01)
    assert history_len(page) == start + 1
    undo(page)
    assert stored(page, ids[0]) is None and field(page, 'y') == '0.00'
    redo(page)
    assert stored(page, ids[0])['y'] == pytest.approx(3 * FT)
    assert field(page, 'y') == '3.00'
    want = settled(page, lambda: served(page, ids[0]), lambda v: v and v['y'] == pytest.approx(3 * FT))
    assert want == stored(page, ids[0])
    reload(page)
    open_3d(page, 1)
    page.evaluate(f"window.app.selectLayer(window.app.project.layers.find(l => l.id === {ids[0]}))")
    page.wait_for_timeout(300)
    assert stored(page, ids[0]) == want
    assert field(page, 'y') == '3.00'


def test_a_typed_pitch_keeps_the_bottom_middle_where_it_is(page):
    ids = reset(page, ONE)
    open_3d(page, 1)
    type_field(page, 'x', '4')
    type_field(page, 'y', '2')
    before = bottom_middle(corners(page, ids[0]))
    for name, deg in (('pitch', '25'), ('yaw', '-40'), ('roll', '15')):
        type_field(page, name, deg)
        settled(page, lambda: screen(page, ids[0])['placement'][name], lambda v: v != 0)
        now = bottom_middle(corners(page, ids[0]))
        assert close(now, before, tol=0.01), (name, now, before)
    p = stored(page, ids[0])
    assert (p['x'], p['y'], p['z']) == pytest.approx((4 * FT, 2 * FT, 0), abs=0.01)
    assert (field(page, 'x'), field(page, 'y'), field(page, 'z')) == ('4.00', '2.00', '0.00')
    # the step buttons turn about the same point
    page.click('[data-s3d-axis="pitch"] [data-s3d-step="15"]')
    page.wait_for_timeout(400)
    assert close(bottom_middle(corners(page, ids[0])), before)


def test_the_rings_turn_about_the_bottom_middle(page):
    ids = reset(page, ONE)
    open_3d(page, 1)
    type_field(page, 'y', '2')
    view_from(page, 'iso')
    page.evaluate(f"window.app.setSelectedLayersByIds([{ids[0]}], {ids[0]})")
    h = handles(page)
    before = bottom_middle(corners(page, ids[0]))
    assert close(h['pivot'], before, tol=0.01), (h['pivot'], before)
    page.mouse.move(5, 5)
    page.keyboard.press('e')
    assert settled(page, lambda: dbg(page)['tool'], lambda t: t == 'rotate') == 'rotate'
    steps = history_len(page)
    for ring in ('pitch', 'yaw', 'roll'):
        grip_drag(page, ring, (0, 60))
    p = stored(page, ids[0])
    assert abs(p['pitch']) > 3 and abs(p['yaw']) > 3 and abs(p['roll']) > 3, p
    assert history_len(page) == steps + 3
    assert close(bottom_middle(corners(page, ids[0])), before, tol=0.01)
    page.keyboard.press('w')


def test_several_screens_turn_about_the_lowest_middle_of_their_bounds(page):
    ids = reset(page, [{'name': 'A', 'columns': 2, 'rows': 2},
                       {'name': 'B', 'columns': 2, 'rows': 4, 'offset_x': 600, 'offset_y': -400}])
    open_3d(page, 2)
    page.evaluate(f"window.app.setSelectedLayersByIds({ids}, {ids[0]})")
    h = settled(page, lambda: dbg(page)['handles'], lambda v: v and v['shown'] and len(v['ids']) == 2, 3000)
    assert sorted(h['ids']) == sorted(ids), h
    worlds = [screen(page, i)['world'] for i in ids]
    lo = [min(w['min'][k] for w in worlds) for k in range(3)]
    hi = [max(w['max'][k] for w in worlds) for k in range(3)]
    assert h['pivot'] == pytest.approx([(lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2], abs=0.01)


# ── 4. the ft | m switch ──────────────────────────────────────────────────

def test_the_units_switch_converts_the_panel_snap_and_readout_and_is_kept(page):
    ids = reset(page, ONE)
    open_3d(page, 1)
    type_field(page, 'y', '2m')                     # a figure with its unit, in feet
    assert stored(page, ids[0])['y'] == pytest.approx(2000)
    assert field(page, 'y') == f'{2000 / FT:.2f}'
    steps = history_len(page)
    page.click('#s3d-units-m')
    page.wait_for_timeout(300)
    assert field(page, 'y') == '2.000'
    assert page.evaluate("[...document.querySelectorAll('[data-s3d-unit]')].map(e => e.textContent)") == ['m'] * 3
    assert page.evaluate("document.getElementById('s3d-units-m').classList.contains('active')")
    assert history_len(page) == steps, 'the switch is view state, not an undo step'
    type_field(page, 'x', "6'6\"")                  # feet typed in a meters panel
    assert stored(page, ids[0])['x'] == pytest.approx(6 * FT + 6 * 25.4)
    assert field(page, 'x') == f'{(6 * FT + 6 * 25.4) / 1000:.3f}'
    # the snap and the figure beside the cursor follow
    view_from(page, 'iso')
    page.evaluate(f"window.app.setSelectedLayersByIds([{ids[0]}], {ids[0]})")
    page.click('#s3d-tool-move')
    seen = {}

    def read():
        seen['text'] = page.evaluate("(() => { const r = document.getElementById('s3d-readout');"
                                     " return r && !r.hidden ? r.textContent : ''; })()")
    x0 = stored(page, ids[0])['x']
    grip_drag(page, 'x', (75, 0), keys=('Control',), before_up=read)
    dx = stored(page, ids[0])['x'] - x0
    assert abs(dx) >= 100 and dx / 100 == pytest.approx(round(dx / 100), abs=1e-6), dx
    assert seen['text'].startswith('X ') and seen['text'].endswith(' m'), seen
    # the nudges: 10 mm a press in meters
    y0 = stored(page, ids[0])['y']
    page.mouse.move(5, 5)
    page.keyboard.press('PageUp')
    got = settled(page, lambda: stored(page, ids[0]), lambda v: v['y'] != y0, 3000)
    assert got['y'] == pytest.approx(y0 + 10, abs=0.01)
    # saved with the show, and the show's own unit untouched
    assert settled(page, lambda: page.evaluate(
        "async () => (await (await fetch('/api/project')).json()).stage3dUnits"), lambda v: v == 'm') == 'm'
    assert page.evaluate("async () => (await (await fetch('/api/project')).json()).cableUnit") == 'ft'
    assert page.evaluate("window.app.cableUnit()") == 'ft'
    reload(page)
    open_3d(page, 1)
    page.evaluate(f"window.app.selectLayer(window.app.project.layers.find(l => l.id === {ids[0]}))")
    page.wait_for_timeout(300)
    assert dbg(page)['units'] == 'm'
    assert field(page, 'y') == f"{got['y'] / 1000:.3f}"
    assert page.evaluate("window.app.cableUnit()") == 'ft'
    page.click('#s3d-units-ft')
    page.wait_for_timeout(300)
    assert field(page, 'y') == f"{got['y'] / FT:.2f}"


def test_a_show_with_no_3d_units_starts_on_its_own_unit(page):
    reset(page, ONE, cable_unit='m')
    open_3d(page, 1)
    assert dbg(page)['units'] == 'm'
    assert field(page, 'y') == '0.000'
    assert page.evaluate("document.querySelector('[data-s3d-unit]').textContent") == 'm'
    reset(page, ONE, cable_unit='ft')
    open_3d(page, 1)
    assert dbg(page)['units'] == 'ft'


# ── 5. header and footer bars ─────────────────────────────────────────────

def test_the_bars_touch_the_panels_at_their_real_heights(page):
    ids = reset(page, [{'name': 'Foot', 'columns': 4, 'rows': 2, 'footer': [2, 2]},
                       {'name': 'Head', 'columns': 4, 'rows': 2, 'offset_x': 700, 'header': [2, 2]}])
    open_3d(page, 2)
    foot = {r['row']: r for r in screen(page, ids[0])['bars']}['footer']
    head = {r['row']: r for r in screen(page, ids[1])['bars']}['header']
    assert foot['heightMm'] == pytest.approx(152.4) and head['heightMm'] == pytest.approx(88.9)
    # in each screen's own frame (origin at the panels' bottom middle): the
    # footer's top edge is the panels' bottom edge, the header's bottom
    # edge is their top - no gap either side
    assert foot['first'][1] == pytest.approx(0, abs=0.001)
    assert head['first'][1] == pytest.approx(1000 + 88.9, abs=0.001)


def test_a_footer_on_the_floor_reads_y_0_with_its_panels_6_in_up(page):
    ids = reset(page, [{'name': 'Foot', 'columns': 4, 'rows': 2, 'footer': [2, 2]}])
    open_3d(page, 1)
    s = screen(page, ids[0])
    assert s['footerMm'] == pytest.approx(152.4)
    assert s['world']['min'][1] == pytest.approx(152.4, abs=0.01)
    assert s['datum'][1] == pytest.approx(0, abs=0.01)
    assert field(page, 'y') == '0.00'
    # typing a height lifts the footer's foot to it
    type_field(page, 'y', '1')
    assert screen(page, ids[0])['datum'][1] == pytest.approx(FT, abs=0.01)
    assert stored(page, ids[0])['y'] == pytest.approx(FT + 152.4, abs=0.01)
    type_field(page, 'y', '0')
    # a turn keeps the footer on the floor
    for name, deg in (('pitch', '20'), ('yaw', '35'), ('roll', '-10')):
        type_field(page, name, deg)
        d = settled(page, lambda: screen(page, ids[0]), lambda v: v['placement'][name] != 0)['datum']
        assert d[1] == pytest.approx(0, abs=0.01), (name, d)
        assert field(page, 'y') == '0.00'
    view_from(page, 'iso')
    page.evaluate(f"window.app.setSelectedLayersByIds([{ids[0]}], {ids[0]})")
    h = handles(page)
    assert close(h['pivot'], screen(page, ids[0])['datum'], tol=0.01)


def test_adding_a_footer_leaves_the_panels_where_they_are(page):
    ids = reset(page, ONE)
    open_3d(page, 1)
    type_field(page, 'x', '2')
    type_field(page, 'pitch', '10')
    before = corners(page, ids[0])
    block = stored(page, ids[0])
    page.evaluate(f"""() => {{ const a = window.app; const l = a.project.layers.find(x => x.id === {ids[0]});
        l.riggingFooterBars = [2, 2]; a.updateLayers([l], true, 'Bars'); }}""")
    s = settled(page, lambda: screen(page, ids[0]), lambda v: v['footerMm'] > 0)
    assert s['footerMm'] == pytest.approx(152.4)
    assert stored(page, ids[0]) == block
    for a, b in zip(corners(page, ids[0]), before):
        for p, q in zip(a['corners'], b['corners']):
            assert close(p, q, tol=0.001)
    # the zero moved instead: Y now reads the footer's foot, 6 in lower
    want = settled(page, lambda: field(page, 'y'), lambda v: v != '0.00')
    assert float(want) == pytest.approx(-152.4 * 0.9848 / FT, abs=0.01)
    assert page.errors == []


# ── 6. Export > OBJ stands every screen where the stage does ─────────────

# Each screen's OBJ faces (app-obj-export.js objFacesOf, in meters) back in
# stage mm, corner order [tl, tr, br, bl] like _s3dDebugCorners.
OBJ_CORNERS_JS = """(id) => {
    const app = window.app;
    const l = app.project.layers.find(x => x.id === id);
    return app.objFacesOf(l, {w: 1920, h: 1080}).map(f => [3, 2, 1, 0].map(k => f.corners[k].map(n => n * 1000)));
}"""


def obj_corners(page, layer_id):
    return page.evaluate(OBJ_CORNERS_JS, layer_id)


def assert_obj_matches_stage(page, layer_id, label):
    stage = corners(page, layer_id)
    faces = obj_corners(page, layer_id)
    assert len(faces) == len(stage), label
    for face, quad in zip(faces, stage):
        for a, b in zip(face, quad['corners']):
            assert close(a, b, tol=0.01), (label, quad['row'], quad['col'], a, b)


def test_the_obj_stands_every_screen_where_the_stage_does(page):
    """Old centre blocks, a turned screen and a footed one: every OBJ corner
    is the stage's own, so the OBJ's floor is the stage's floor (Y 0) and
    its turning point the bottom middle."""
    cases = _centre_cases()
    specs = [dict(c['spec'], name=f'Old {i}', offset_x=i * 2000, stage3d=c['block'])
             for i, c in enumerate(cases)]
    specs.append({'name': 'Floor', 'columns': 4, 'rows': 2, 'offset_x': len(cases) * 2000})
    specs.append({'name': 'Footed', 'columns': 4, 'rows': 2, 'offset_x': len(cases) * 2000 + 700,
                  'footer': [2, 2]})
    ids = reset(page, specs)
    open_3d(page, len(ids))
    for layer_id, case in zip(ids, cases):
        assert_obj_matches_stage(page, layer_id, case['name'])
        # and the stage stands the old block where the first betas did
        want = {(q['row'], q['col']): q['corners'] for q in case['corners']}
        for face, quad in zip(obj_corners(page, layer_id), corners(page, layer_id)):
            for a, b in zip(face, want[(quad['row'], quad['col'])]):
                assert close(a, b), (case['name'], a, b)
    floor_id, foot_id = ids[-2], ids[-1]
    # Y is the panels' bottom edge in the OBJ (the tallest old screen sets
    # the Show Look floor, so this one stands up off it)
    s = screen(page, floor_id)
    ys = [p[1] for f in obj_corners(page, floor_id) for p in f]
    assert min(ys) == pytest.approx(s['placement']['y'], abs=0.001)
    assert max(ys) - min(ys) == pytest.approx(1000, abs=0.001)
    # with a footer, Y is the footer's foot and the panels start 6 in up
    s = screen(page, foot_id)
    ys = [p[1] for f in obj_corners(page, foot_id) for p in f]
    assert min(ys) - s['datum'][1] == pytest.approx(152.4, abs=0.001)
    # alone on the stage, the footer stands on the floor: the OBJ's Y 0
    lone = reset(page, [{'name': 'Footed', 'columns': 4, 'rows': 2, 'footer': [2, 2]},
                        {'name': 'Floor', 'columns': 4, 'rows': 2, 'offset_x': 700}])
    open_3d(page, 2)
    assert screen(page, lone[0])['datum'][1] == pytest.approx(0, abs=0.001)
    ys = [p[1] for f in obj_corners(page, lone[0]) for p in f]
    assert min(ys) == pytest.approx(152.4, abs=0.001)
    ys = [p[1] for f in obj_corners(page, lone[1]) for p in f]
    assert min(ys) == pytest.approx(152.4, abs=0.001)
    floor_id = lone[1]
    # turned all three ways about the bottom middle: still the stage's own
    page.evaluate(f"window.app.selectLayer(window.app.project.layers.find(l => l.id === {floor_id}))")
    page.wait_for_timeout(200)
    x_before = stored(page, floor_id) or screen(page, floor_id)['placement']
    for name, deg in (('pitch', '20'), ('yaw', '35'), ('roll', '-10')):
        type_field(page, name, deg)
    turned = settled(page, lambda: stored(page, floor_id), lambda v: v and v.get('roll') == -10)
    assert turned['pivot'] == 'bottom'
    assert close([turned['x'], turned['y'], turned['z']], [x_before['x'], x_before['y'], x_before['z']], tol=0.001)
    settled(page, lambda: screen(page, floor_id), lambda v: v['placement']['roll'] == -10)
    assert_obj_matches_stage(page, floor_id, 'turned')
    assert page.errors == []
