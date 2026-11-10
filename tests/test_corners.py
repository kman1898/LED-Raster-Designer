"""Corners: a screen bent between two columns or down the middle of a panel
(the Header/Footer tab's Corners, app-corners.js; built by app-stage3d.js
s3dBuild), the owner's rulings of 2026-11-09:

* A corner goes on a seam between two panels or down the middle of one,
  Interior or Exterior. Columns only. Every corner is 90 degrees (owner,
  2026-11-10): there is no angle box, and a corner saved under 90 by a
  1.7.0 beta opens as 90 at the same spot and side.
* The hinge is the panels' front face: the two sides meet there.
* Interior folds the sides toward the audience, Exterior away.
* A corner's seam carries no curve angle: the corner takes its place, and
  the seams beside it keep theirs (tests/test_corner_rulings.py).
* The side at the Curve's build-from point stays put; the middle without a
  Curve (tests/test_corner_rulings.py).
* The 3D tab and Export > OBJ build it: shape, mapping and image, one file
  per physical screen.
* The controls sit under the Curve on the Header/Footer tab: Add corner,
  then where and Interior or Exterior, with a plan from above.
  Each change is one undo step; undo, redo and a reload keep it.
* A show from before corners opens with nothing moved and nothing written.

Run locally:
    python -m pytest tests/test_corners.py -n 4 --dist loadfile -p no:cacheprovider
"""
import json
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from conftest import settled  # noqa: E402

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

CENTRE_BLOCKS = os.path.join(os.path.dirname(__file__), 'data', 'stage3d_centre_blocks.json')


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project as this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1500, 'height': 950})
    context.add_init_script("try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.errors = []
    pg.on('pageerror', lambda err: pg.errors.append(str(err)))
    pg.route('**/api/native-dialog/**', lambda r: r.fulfill(status=503, body='{}'))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app._initialLoadComplete")
    pg.wait_for_timeout(1200)
    yield pg
    context.close()


# Exactly the screens asked for (128 px, 500 mm cabinets), with any extra
# layer fields; history rebased so a test's own edits are the only steps.
RESET_JS = """async (specs) => {
    const app = window.app;
    for (let i = 0; i < 600; i++) {
        if (!(app._inflightLayerPuts && app._inflightLayerPuts.size)) break;
        await new Promise(r => setTimeout(r, 25));
    }
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    let project = await j('GET', '/api/project');
    project.layers = [];
    project.groups = [];
    project.cableUnit = 'ft';
    for (const k of ['stage3dCamera', 'stage3dUnits', 'stage3dGrid', 'stage3dBars', 'riggingTool']) delete project[k];
    await j('PUT', '/api/project', project);
    const ids = [];
    for (const s of specs) {
        const made = await j('POST', '/api/layer/add', {
            cabinet_width: 128, cabinet_height: 128, panel_width_mm: 500, panel_height_mm: 500,
            name: s.name, columns: s.columns, rows: s.rows, offset_x: s.offset_x || 0, offset_y: s.offset_y || 0,
        });
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
        if (s.extra) await j('PUT', `/api/layer/${made.id}`, s.extra);
    }
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('corners_reset');
    if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
    app.resetHistory('Corners Reset');
    app.setSelectedLayersByIds([ids[0]], ids[0]);
    app.updateUI();
    return ids;
}"""

COLUMN = {'name': 'COLUMN', 'columns': 6, 'rows': 2}


def reset(page, specs=(COLUMN,)):
    page.evaluate("""() => { const t = document.querySelector('#view-tabs .view-tab[data-mode="pixel-map"]');
        if (t) t.click(); }""")
    page.wait_for_timeout(150)
    ids = page.evaluate(RESET_JS, [dict(s) for s in specs])
    page.wait_for_timeout(300)
    return ids


def layer(page, layer_id):
    return page.evaluate("(id) => JSON.parse(JSON.stringify(window.app.project.layers.find(l => l.id === id)))", layer_id)


def served(page, layer_id):
    return page.evaluate("""async (id) => { const p = await (await fetch('/api/project')).json();
        return p.layers.find(l => l.id === id); }""", layer_id)


def corners_of(page, layer_id):
    return (layer(page, layer_id) or {}).get('riggingCorners')


def history_len(page):
    return page.evaluate('window.app.history.length')


def open_rigging(page):
    page.click('#view-tabs .view-tab[data-mode="rigging"]')
    page.wait_for_timeout(250)


def row(page, at):
    return f'#rigging-corner-list [data-corner="{at:g}"]'


# Walking the wall left to right along its bottom edge, in plan (x, z): the
# heading of every quad's bottom edge in degrees, quads ordered by column
# and fold half. Positive turns are toward the audience (+Z).
def plan_turns(quads, row_index):
    edges = sorted((q for q in quads if q['row'] == row_index), key=lambda q: (q['col'], q.get('fold', 0)))
    heads = [math.degrees(math.atan2(q['br'][2] - q['bl'][2], q['br'][0] - q['bl'][0])) for q in edges]
    return edges, [round(heads[i + 1] - heads[i], 6) for i in range(len(heads) - 1)]


BUILD_JS = """async () => {
    const m = await import('/static/js/app-stage3d.js');
    const grid = (cols, rows) => {
        const panels = [];
        for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
            panels.push({row: r, col: c, x: c * 128, y: r * 128, width: 128, height: 128});
        }
        return {type: 'screen', columns: cols, rows, cabinet_width: 128, cabinet_height: 128,
                panel_width_mm: 500, panel_height_mm: 500, panels};
    };
    const flat = {x: 0, y: 0, z: 0, pitch: 0, yaw: 0, roll: 0, curveCol: 0, curveRow: 0,
                  jointsCol: {}, jointsRow: {}, pivot: 'bottom'};
    const wall = grid(6, 2);
    const quads = (layer, p) => m.s3dBuild(layer, p || flat).quads.map(q => ({
        row: q.row, col: q.col, fold: q.fold, tl: q.tl, tr: q.tr, br: q.br, bl: q.bl, px: q.px}));
    const at = (list) => ({...wall, riggingCorners: list});
    return {
        plain: quads(wall), empty: quads(at([])),
        seam: quads(at([{at: 3.5, angle: 90, side: 'interior'}])),
        seamOut: quads(at([{at: 3.5, angle: 90, side: 'exterior'}])),
        fold: quads(at([{at: 3, angle: 90, side: 'interior'}])),
        foldOut: quads(at([{at: 3, angle: 90, side: 'exterior'}])),
        added: quads(at([{at: 3.5, angle: 90, side: 'interior'}]), {...flat, jointsCol: {'2': 10}}),
        twoFolds: quads(at([{at: 1, angle: 90}, {at: 6, angle: 90}])),
        // a corner saved under 90 by a 1.7.0 beta builds as 90
        old: quads(at([{at: 3.5, angle: 45, side: 'exterior'}])),
        clean: m.s3dCleanCorners([{at: 0, angle: 90}, {at: 2.25, angle: 90}, {at: 2, angle: 120, side: 'exterior'},
                                  {at: 4.5, angle: -5}, 'junk', null, {at: 3, angle: 12.34},
                                  {at: 3, angle: 45, side: 'sideways'}, {at: '5.5', angle: '30'}, {at: 6}]),
        on: m.s3dCornersOn(at([{at: 6, angle: 90}, {at: 6.5, angle: 90}, {at: 7, angle: 90}]), 6),
        base: [m.s3dBaseOffset(wall, flat), m.s3dBaseOffset(at([{at: 3, angle: 90}]), flat)],
    };
}"""


# ── 1. the shape, pure ───────────────────────────────────────────────────

def test_a_corner_folds_the_wall_at_its_seam_or_down_a_panel_hinged_at_the_front(page):
    out = page.evaluate(BUILD_JS)
    # no corners, or an empty list, builds exactly as before
    assert out['empty'] == out['plain']
    # on a seam: twelve cabinets, the wall turns 90 degrees between panels 3
    # and 4, both wings come toward the audience (Interior)
    seam = out['seam']
    assert len(seam) == 12 and not any('fold' in q and q['fold'] is not None for q in seam)
    edges, turns = plan_turns(seam, 1)
    assert turns == [0, 0, pytest.approx(90), 0, 0]
    # the hinge is the front face: panel 3's right edge is panel 4's left
    p3 = next(q for q in seam if (q['row'], q['col']) == (1, 2))
    p4 = next(q for q in seam if (q['row'], q['col']) == (1, 3))
    assert p3['br'] == pytest.approx(p4['bl'], abs=1e-9) and p3['tr'] == pytest.approx(p4['tl'], abs=1e-9)
    assert edges[0]['bl'][2] > p3['br'][2] and edges[-1]['br'][2] > p3['br'][2]
    _, turns = plan_turns(out['seamOut'], 1)
    assert turns == [0, 0, pytest.approx(-90), 0, 0]
    # down the middle of panel 3: that cabinet is two quads of 250 mm, each
    # with its half of the drawing, hinged at their shared front edge
    fold = out['fold']
    assert len(fold) == 14
    halves = sorted((q for q in fold if (q['row'], q['col']) == (1, 2)), key=lambda q: q['fold'])
    assert [q['fold'] for q in halves] == [0, 1]
    assert [q['px'] for q in halves] == [[256, 128, 64, 128], [320, 128, 64, 128]]
    for q in halves:
        assert math.dist(q['bl'], q['br']) == pytest.approx(250, abs=1e-9)
    assert halves[0]['br'] == pytest.approx(halves[1]['bl'], abs=1e-9)
    _, turns = plan_turns(fold, 1)
    assert turns == [0, 0, pytest.approx(90), 0, 0, 0]
    _, turns = plan_turns(out['foldOut'], 0)
    assert turns == [0, 0, pytest.approx(-90), 0, 0, 0]
    # a curve angle on the same seam is left out: the corner takes its place
    _, turns = plan_turns(out['added'], 1)
    assert turns == [0, 0, pytest.approx(90), 0, 0]
    # a fold in the first or last panel, at their own middles
    _, turns = plan_turns(out['twoFolds'], 0)
    assert turns == [pytest.approx(90)] + [0] * 5 + [pytest.approx(90)]
    # every corner is 90: one saved at 45 folds 90, on its own side
    _, turns = plan_turns(out['old'], 1)
    assert turns == [0, 0, pytest.approx(-90), 0, 0]
    assert out['old'] == out['seamOut']
    # the screen's turning point stays the bottom middle of the wall
    assert out['base'][0] == out['base'][1]


def test_corners_are_kept_to_their_shape_every_one_90(page):
    out = page.evaluate(BUILD_JS)
    # the spot and the side are kept; every angle, however it was saved, is 90
    assert out['clean'] == [
        {'at': 2, 'angle': 90, 'side': 'exterior'},
        {'at': 3, 'angle': 90, 'side': 'interior'},
        {'at': 4.5, 'angle': 90, 'side': 'interior'},
        {'at': 5.5, 'angle': 90, 'side': 'interior'},
        {'at': 6, 'angle': 90, 'side': 'interior'},
    ]
    # a corner past the screen's last column is kept but not built
    assert out['on'] == [{'at': 6, 'angle': 90, 'side': 'interior'}]


# ── 2. the controls on the Header/Footer tab ─────────────────────────────

def test_add_corner_then_pick_the_spot_and_the_side_one_step_each(page):
    ids = reset(page)
    open_rigging(page)
    assert page.is_visible('#rigging-corner-add')
    assert page.locator('#rigging-corner-list [data-corner]').count() == 0
    assert not page.is_visible('#rigging-corner-plan svg')
    n = history_len(page)
    page.click('#rigging-corner-add')
    want = [{'at': 3.5, 'angle': 90, 'side': 'interior'}]
    assert corners_of(page, ids[0]) == want
    assert history_len(page) == n + 1
    assert settled(page, lambda: served(page, ids[0]).get('riggingCorners'), lambda v: v == want) == want
    # the row reads it, and the plan shows the wall from above with its dot
    assert page.input_value(f'{row(page, 3.5)} [data-corner-at]') == '3.5'
    assert page.evaluate(f"document.querySelector('{row(page, 3.5)} [data-corner-side=\"interior\"]').classList.contains('active')")
    assert page.locator('#rigging-corner-plan svg [data-corner-dot]').count() == 1
    labels = page.evaluate(f"[...document.querySelectorAll('{row(page, 3.5)} [data-corner-at] option')].map(o => o.textContent)")
    assert labels[:3] == ['Middle of panel 1', 'Between panels 1 and 2', 'Middle of panel 2'] and len(labels) == 11
    # every corner is 90 degrees: no angle box, nothing that says otherwise
    assert page.locator('#rigging-corners input').count() == 0
    assert page.locator('#rigging-corners [data-corner-angle], #rigging-corner-rule, .rigging-corner-split').count() == 0
    assert 'under 90' not in page.inner_text('#rigging-corners')
    # the row: where, x, and Interior or Exterior
    assert page.locator(f'{row(page, 3.5)} select').count() == 1
    assert page.evaluate(f"[...document.querySelectorAll('{row(page, 3.5)} button')].map(b => b.textContent)") == ['×', 'Interior', 'Exterior']
    # the middle of panel 3, as a person picks it
    page.select_option(f'{row(page, 3.5)} [data-corner-at]', '3')
    assert settled(page, lambda: corners_of(page, ids[0]), lambda v: v[0]['at'] == 3)[0]['at'] == 3
    page.click(f'{row(page, 3)} [data-corner-side="exterior"]')
    final = [{'at': 3, 'angle': 90, 'side': 'exterior'}]
    assert corners_of(page, ids[0]) == final
    assert history_len(page) == n + 3
    assert settled(page, lambda: served(page, ids[0]).get('riggingCorners'), lambda v: v == final) == final
    # undo walks back one change at a time, redo brings them back
    for want_now in ([{'at': 3, 'angle': 90, 'side': 'interior'}], [{'at': 3.5, 'angle': 90, 'side': 'interior'}]):
        page.evaluate('window.app.undo()')
        assert settled(page, lambda: corners_of(page, ids[0]), lambda v: v == want_now) == want_now
    page.evaluate('window.app.undo()')
    assert settled(page, lambda: corners_of(page, ids[0]) or [], lambda v: v == []) == []
    assert page.locator('#rigging-corner-list [data-corner]').count() == 0
    for _ in range(3):
        page.evaluate('window.app.redo()')
        page.wait_for_timeout(150)
    assert settled(page, lambda: corners_of(page, ids[0]), lambda v: v == final) == final
    # a reload keeps it and the tab shows it
    settled(page, lambda: served(page, ids[0]).get('riggingCorners'), lambda v: v == final)
    page.reload(wait_until='domcontentloaded')
    page.wait_for_function("() => window.app && window.app._initialLoadComplete")
    page.wait_for_timeout(1200)
    page.evaluate(f"window.app.setSelectedLayersByIds([{ids[0]}], {ids[0]})")
    open_rigging(page)
    assert corners_of(page, ids[0]) == final
    assert page.evaluate(f"document.querySelector('{row(page, 3)} [data-corner-side=\"exterior\"]').classList.contains('active')")
    # x takes it off, one step
    n = history_len(page)
    page.click(f'{row(page, 3)} [data-corner-remove]')
    assert corners_of(page, ids[0]) == [] and history_len(page) == n + 1
    assert settled(page, lambda: served(page, ids[0]).get('riggingCorners'), lambda v: v == []) == []
    assert page.errors == []


def test_an_old_corner_saved_under_90_opens_as_90_at_the_same_spot_and_side(page):
    """Only a 1.7.0 beta could save a corner under 90 degrees. Such a show
    opens with each one a 90 degree corner where it was, Interior or
    Exterior as it was, and Auto lays its corner bar."""
    ids = reset(page, [dict(COLUMN, extra={'riggingSizes': [1, 2], 'riggingCorners': [
        {'at': 3.5, 'angle': 45, 'side': 'exterior'}]})])
    assert served(page, ids[0])['riggingCorners'] == [{'at': 3.5, 'angle': 45, 'side': 'exterior'}]
    page.reload(wait_until='domcontentloaded')
    page.wait_for_function("() => window.app && window.app._initialLoadComplete")
    page.wait_for_timeout(1200)
    page.evaluate(f"window.app.setSelectedLayersByIds([{ids[0]}], {ids[0]})")
    open_rigging(page)
    got = page.evaluate(f"window.app.riggingCornersOf(window.app.project.layers.find(l => l.id === {ids[0]}))")
    assert got == [{'at': 3.5, 'angle': 90, 'side': 'exterior'}]
    assert page.locator(f'{row(page, 3.5)}').count() == 1
    assert page.evaluate(f"document.querySelector('{row(page, 3.5)} [data-corner-side=\"exterior\"]').classList.contains('active')")
    # it builds as a 90 degree Exterior corner on its seam
    quads = page.evaluate(f"""async () => {{ const m = await import('/static/js/app-stage3d.js');
        const l = window.app.project.layers.find(x => x.id === {ids[0]});
        return m.s3dBuild(l, window.app._s3dPlacementOf(l)).quads.map(q => ({{row: q.row, col: q.col, fold: q.fold,
            tl: q.tl, tr: q.tr, br: q.br, bl: q.bl}})); }}""")
    _, turns = plan_turns(quads, 1)
    assert turns == [0, 0, pytest.approx(-90), 0, 0]
    # and takes its corner bar, as every corner does
    page.click('#rigging-auto-btn')
    lay = settled(page, lambda: layer(page, ids[0]), lambda v: v.get('riggingBars'))
    assert lay['riggingCorners'] == [{'at': 3.5, 'angle': 90, 'side': 'exterior', 'bar': True}]
    assert lay['riggingBars'] == [2, 2] and lay['riggingBarStarts'] == [0, 4]
    assert page.inner_text('#rigging-total-breakdown').split('\n') == ['Double: 2', 'Corner (2 panel): 1']
    assert page.errors == []


def test_a_side_button_keeps_focus_and_a_taken_spot_cannot_be_picked(page):
    ids = reset(page)
    open_rigging(page)
    page.click('#rigging-corner-add')
    page.click('#rigging-corner-add')
    have = corners_of(page, ids[0])
    # the second goes on the free spot nearest the middle whose corner bar
    # would not share a panel with the first's (panels 3 and 4)
    assert [c['at'] for c in have] == [2, 3.5]
    # a spot another corner holds, or too close to it, is grayed out
    opts = page.evaluate(f"[...document.querySelectorAll('{row(page, 2)} [data-corner-at] option')].map(o => [o.value, o.disabled, o.textContent])")
    assert [v for v, off, _ in opts if off] == ['2.5', '3', '3.5', '4', '4.5']
    assert dict((v, t) for v, _, t in opts)['3.5'] == 'Between panels 3 and 4, has a corner'
    assert dict((v, t) for v, _, t in opts)['3'] == 'Middle of panel 3, too close'
    # a side picked on one row: the row is brought up to date in place, so
    # the button keeps its focus
    page.click(f'{row(page, 2)} [data-corner-side="exterior"]')
    assert settled(page, lambda: corners_of(page, ids[0]), lambda v: v[0]['side'] == 'exterior')[0]['side'] == 'exterior'
    page.wait_for_timeout(300)
    assert page.evaluate(f"document.activeElement === document.querySelector('{row(page, 2)} [data-corner-side=\"exterior\"]')")
    assert page.errors == []


def test_two_selected_columns_take_and_edit_their_corners_together(page):
    ids = reset(page, [COLUMN, dict(COLUMN, name='COLUMN 2', offset_x=900)])
    open_rigging(page)
    page.evaluate(f"window.app.setSelectedLayersByIds({ids}, {ids[0]})")
    page.wait_for_timeout(200)
    n = history_len(page)
    page.click('#rigging-corner-add')
    page.click(f'{row(page, 3.5)} [data-corner-side="exterior"]')
    for i in ids:
        assert corners_of(page, i) == [{'at': 3.5, 'angle': 90, 'side': 'exterior'}]
    assert history_len(page) == n + 2
    assert page.errors == []


# ── 3. the 3D tab and the OBJ ────────────────────────────────────────────

def s3d_quads(page, layer_id):
    return page.evaluate(f"window.app._s3dDebugCorners({layer_id})")


def open_3d(page, count):
    page.click('#view-tabs .view-tab[data-mode="3d"]')
    got = settled(page, lambda: page.evaluate('window.app._s3dDebug()'),
                  lambda d: d['loaded'] and len(d['screens']) == count and all(s['tex'] for s in d['screens']), 10000)
    assert got['loaded'], got
    return got


def test_the_3d_tab_builds_the_corner_where_the_pure_build_puts_it(page):
    ids = reset(page)
    open_rigging(page)
    page.click('#rigging-corner-add')
    page.select_option(f'{row(page, 3.5)} [data-corner-at]', '3')
    settled(page, lambda: corners_of(page, ids[0]), lambda v: v[0]['at'] == 3)
    open_3d(page, 1)
    quads = settled(page, lambda: s3d_quads(page, ids[0]), lambda q: q and len(q) == 14)
    assert len(quads) == 14
    want = page.evaluate("""async (id) => {
        const m = await import('/static/js/app-stage3d.js');
        const l = window.app.project.layers.find(x => x.id === id);
        return m.s3dWorldCorners(l, window.app._s3dPlacementOf(l));
    }""", ids[0])
    for a, b in zip(quads, want):
        for p, q in zip(a['corners'], b['corners']):
            assert all(abs(x - y) < 0.01 for x, y in zip(p, q)), (p, q)
    # the two halves of panel 3 stand at right angles
    halves = [q['corners'] for q in quads if (q['row'], q['col']) == (1, 2)]
    a = [halves[0][2][k] - halves[0][3][k] for k in range(3)]
    b = [halves[1][2][k] - halves[1][3][k] for k in range(3)]
    cos = sum(x * y for x, y in zip(a, b)) / (math.hypot(*a) * math.hypot(*b))
    assert cos == pytest.approx(0, abs=1e-6)
    # taking the corner off on the Header/Footer tab straightens it again
    open_rigging(page)
    page.click(f'{row(page, 3)} [data-corner-remove]')
    open_3d(page, 1)
    assert len(settled(page, lambda: s3d_quads(page, ids[0]), lambda q: q and len(q) == 12)) == 12
    assert page.errors == []


def read_obj(text):
    out = {'v': [], 'vt': [], 'objects': []}
    cur = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        tag, *rest = line.split()
        if tag == 'v':
            out['v'].append([float(x) for x in rest])
        elif tag == 'vt':
            out['vt'].append([float(x) for x in rest])
        elif tag == 'o':
            cur = {'name': ' '.join(rest), 'faces': []}
            out['objects'].append(cur)
        elif tag == 'f':
            cur['faces'].append([[int(i) for i in t.split('/')] for t in rest])
    return out


OBJ_FILES_JS = """async (name) => {
    const r = await window.app.objExportFiles(name);
    const out = {};
    for (const f of r.files) out[f.filename] = f.filename.endsWith('.png') ? f.blob.size : await f.blob.text();
    return out;
}"""


def test_the_obj_carries_the_corners_shape_mapping_and_image(page):
    ids = reset(page)
    page.evaluate(f"""() => {{ const a = window.app; const l = a.project.layers.find(x => x.id === {ids[0]});
        l.riggingCorners = [{{at: 3, angle: 90, side: 'interior'}}, {{at: 5.5, angle: 90, side: 'exterior'}}];
        a.updateLayers([l], true, 'Corner'); }}""")
    files = page.evaluate(OBJ_FILES_JS, 'Test Show')
    assert sorted(files) == ['Test_Show_COLUMN.mtl', 'Test_Show_COLUMN.obj', 'Test_Show_Canvas_1_Pixel_Map.png']
    assert files['Test_Show_Canvas_1_Pixel_Map.png'] > 1000
    obj = read_obj(files['Test_Show_COLUMN.obj'])
    faces = obj['objects'][0]['faces']
    assert len(faces) == 14
    # every face flat and its own size: the halves of panel 3 are 0.25 m
    widths = sorted(round(math.dist(obj['v'][f[0][0] - 1], obj['v'][f[1][0] - 1]), 6) for f in faces)
    assert widths == [0.25] * 4 + [0.5] * 10
    # the drawing runs on across the fold: where two faces share a corner
    # in space they share its spot in the canvas raster too
    seen = {}
    for f in faces:
        for vi, ti in ((k[0], k[1]) for k in f):
            key = tuple(round(c, 6) for c in obj['v'][vi - 1])
            uv = tuple(round(c, 9) for c in obj['vt'][ti - 1])
            seen.setdefault(key, set()).add(uv)
    assert all(len(v) == 1 for v in seen.values())
    # the bottom edge, left to right: 90 degrees in panel 3, 90 out at the seam 5|6
    ys = min(v[1] for v in obj['v'])
    bottom = []
    for f in faces:
        bl, br = obj['v'][f[0][0] - 1], obj['v'][f[1][0] - 1]
        if abs(bl[1] - ys) < 1e-6 and abs(br[1] - ys) < 1e-6:
            bottom.append((bl, br))
    order = [bottom[0]]
    rest = bottom[1:]
    while rest:
        nxt = next((e for e in rest if math.dist(e[0], order[-1][1]) < 1e-6), None)
        if nxt is None:
            first = next(e for e in rest if math.dist(e[1], order[0][0]) < 1e-6)
            order.insert(0, first)
            rest.remove(first)
        else:
            order.append(nxt)
            rest.remove(nxt)
    heads = [math.degrees(math.atan2(br[2] - bl[2], br[0] - bl[0])) for bl, br in order]
    turns = [round(heads[i + 1] - heads[i], 3) for i in range(len(heads) - 1)]
    assert turns == [0, 0, 90, 0, 0, -90]
    assert page.errors == []


# ── 4. old shows ─────────────────────────────────────────────────────────

def test_an_old_show_opens_with_nothing_moved_and_nothing_written(page):
    """A show saved before corners (no riggingCorners on any screen; first
    beta 3D blocks that held the centre; a placed screen with a footer)
    opens, is looked at on every tab that builds corners, and is edited
    elsewhere, and nothing about its screens' places or shapes changes."""
    with open(CENTRE_BLOCKS, encoding='utf-8') as fh:
        cases = json.load(fh)['cases']
    specs = []
    for i, c in enumerate(cases):
        specs.append(dict(c['spec'], name=f'Old {i}', offset_x=i * 2000, extra={'stage3d': c['block']}))
    specs.append({'name': 'Footed', 'columns': 4, 'rows': 2, 'offset_x': len(cases) * 2000,
                  'extra': {'riggingFooterBars': [2, 2],
                            'stage3d': {'x': 100, 'y': 152.4, 'z': 0, 'pitch': 0, 'yaw': 0, 'roll': 0, 'pivot': 'bottom'}}})
    ids = reset(page, specs)
    before = {i: served(page, i) for i in ids}
    assert all('riggingCorners' not in l for l in before.values())
    page.reload(wait_until='domcontentloaded')
    page.wait_for_function("() => window.app && window.app._initialLoadComplete")
    page.wait_for_timeout(1200)
    n = history_len(page)
    open_rigging(page)
    for i in ids:
        page.evaluate(f"window.app.setSelectedLayersByIds([{i}], {i})")
        page.wait_for_timeout(60)
    open_3d(page, len(ids))
    # the stage stands the old blocks where the first betas did
    for layer_id, case in zip(ids, cases):
        have = {(q['row'], q['col']): q['corners'] for q in s3d_quads(page, layer_id)}
        for w in case['corners']:
            for a, b in zip(have[(w['row'], w['col'])], w['corners']):
                assert all(abs(x - y) <= 0.01 for x, y in zip(a, b)), (case['name'], a, b)
    # an edit that leaves the footer as it is moves nothing
    foot = ids[-1]
    page.evaluate(f"""() => {{ const a = window.app; const l = a.project.layers.find(x => x.id === {foot});
        l.riggingColor = '#224466'; a.updateLayers([l], true, 'Bar Color'); }}""")
    settled(page, lambda: served(page, foot).get('riggingColor'), lambda v: v == '#224466')
    after = {i: served(page, i) for i in ids}
    # (the server fills its usual defaults on a screen's first PUT; its
    # place, shape and bars are what must not change)
    for i in ids:
        for key in ('stage3d', 'riggingFooterBars', 'riggingBars', 'panels', 'columns', 'rows'):
            assert after[i].get(key) == before[i].get(key), (i, key)
        assert 'riggingCorners' not in after[i]
    assert history_len(page) == n + 1
    assert page.errors == []
