"""Corner bars, the owner's rulings of 2026-11-10 (app-corners.js, the bars
in app-rigging.js and rigging-math.js, the Curve in app-curve.js and
curve-math.js screenCurve):

* A corner down a panel's middle takes a "Header Bar - Corner (1 panel)"
  and one on a seam a "Header Bar - Corner (2 panel)": two parts, each
  its own line on the tab's totals, the pull list, the binder's
  Header/Footer sheet and its pull sheet.
* Every corner is 90 degrees and takes its corner bar; one saved under 90
  by a 1.7.0 beta opens as 90 (tests/test_corners.py too).
* With the Curve on, the corner bars split the screen into sides and the
  Curve's % applies to each side as its own wall: each side's angles are
  curve-math.js's for a wall of that side's width at the same settings,
  its bars run up to the corner bar, and the readouts, Ways to build it,
  Use this and the leftover-stock refusal are each side's, by name. Two
  corners make three sides. The OBJ puts each side's faces on its own
  radius.
* Corners whose pieces would share a panel stay grayed out
  (tests/test_corners.py), and shows without corners are unchanged
  (tests/test_corner_rulings.py).

Run locally:
    python -m pytest tests/test_corner_bars.py -n 4 --dist loadfile -p no:cacheprovider
"""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from conftest import settled  # noqa: E402
from test_corners import COLUMN, OBJ_FILES_JS, RESET_JS, history_len, layer, open_rigging, read_obj  # noqa: E402

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


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


def reset(page, specs=(COLUMN,)):
    page.evaluate("""() => { const t = document.querySelector('#view-tabs .view-tab[data-mode="pixel-map"]');
        if (t) t.click(); }""")
    page.wait_for_timeout(150)
    ids = page.evaluate(RESET_JS, [dict(s) for s in specs])
    page.evaluate("() => { const a = window.app; if (a._riggingToolNow() === 'custom') a.setRiggingTool('auto'); }")
    page.wait_for_timeout(300)
    return ids


def pull_rig(page):
    return sorted(page.evaluate("""() => window.app.buildPullSheet().totals.filter(t => t.side === 'rigging')
        .map(t => [t.type, t.qty])"""))


BINDER = {'sheet': 'tabloid', 'palette': 'colour', 'sides': {'power': False, 'data': False},
          'scope': {'kind': 'show'}, 'cover': False, 'pull': True, 'hardware': False,
          'wiring': False, 'rigging': True, 'titleBlock': True}


def binder_texts(page):
    return page.evaluate("""(o) => { const a = window.app; const plan = a.planBinder(o);
        const i = plan.findIndex(x => x.kind === 'rigging');
        const j = plan.findIndex(x => x.kind === 'pull');
        return { sheet: i < 0 ? [] : a.renderBinderPage(o, i).texts, pull: j < 0 ? [] : a.renderBinderPage(o, j).texts }; }""",
                         BINDER)


def placed(page, layer_id, kind='header'):
    return page.evaluate("""([id, kind]) => { const a = window.app; const l = a.project.layers.find(x => x.id === id);
        return a.riggingPlaced(l, kind).map(b => [b.start, b.size]); }""", [layer_id, kind])


def pieces(page, layer_id):
    return page.evaluate("""(id) => { const a = window.app; const l = a.project.layers.find(x => x.id === id);
        return a.riggingCornerPiecesOf(l).map(p => [p.at, p.start, p.size]); }""", layer_id)


def curve_idle(page):
    return page.evaluate("() => !window.app.riggingCurveBusy()")


# ── 1. Two parts ─────────────────────────────────────────────────────────

def test_1_panel_and_2_panel_corner_bars_are_separate_lines_everywhere(page):
    """One six panel column with a 90 degree corner down the middle of
    panel 2 and one on the seam between panels 4 and 5: Auto lays a 1
    panel and a 2 panel corner bar, and each is its own line."""
    ids = reset(page, [dict(COLUMN, extra={'riggingSizes': [1, 2], 'riggingCorners': [
        {'at': 2, 'angle': 90, 'side': 'interior'}, {'at': 4.5, 'angle': 90, 'side': 'exterior'}]})])
    open_rigging(page)
    page.click('#rigging-auto-btn')
    settled(page, lambda: pieces(page, ids[0]), lambda p: len(p) == 2)
    assert pieces(page, ids[0]) == [[2, 1, 1], [4.5, 3, 2]]
    assert placed(page, ids[0]) == [[0, 1], [2, 1], [5, 1]]
    # the tab's totals: each part its own line, 1 panel first
    assert page.inner_text('#rigging-total-breakdown').split('\n') == [
        'Single: 3', 'Corner (1 panel): 1', 'Corner (2 panel): 1']
    assert page.inner_text('#rigging-total-count') == '5'
    # the pull list
    assert pull_rig(page) == [['Header Bar - Corner (1 panel)', 1], ['Header Bar - Corner (2 panel)', 1],
                              ['Header Bar - Single', 3]]
    # the binder's Header/Footer sheet and its pull sheet
    out = binder_texts(page)
    head = out['sheet'][out['sheet'].index('HEADER BARS'):]
    one = head.index('Header Bar - Corner (1 panel)')
    two = head.index('Header Bar - Corner (2 panel)')
    assert head[one + 1:one + 3] == ['1', '1'], head
    assert head[two + 1:two + 3] == ['2', '1'], head
    assert one < two
    assert head[head.index('Total') + 1:head.index('Total') + 3] in (['', '5'], ['5']), head
    assert 'Header Bar - Corner (1 panel)' in out['pull'] and 'Header Bar - Corner (2 panel)' in out['pull']
    assert 'Header Bar - Corner' not in out['pull'] and 'Header Bar - Corner' not in out['sheet']
    # the footer side has the same two parts
    page.click('#rigging-mode-picker .rigging-mode-btn[data-mode="footer"]')
    settled(page, lambda: pull_rig(page), lambda r: ['Footer Bar - Corner (2 panel)', 1] in r)
    assert pull_rig(page) == [['Footer Bar - Corner (1 panel)', 1], ['Footer Bar - Corner (2 panel)', 1],
                              ['Footer Bar - Single', 3]]
    assert page.errors == []


def test_two_screens_add_up_each_part_on_its_own_line(page):
    ids = reset(page, [
        dict(COLUMN, name='LEFT', extra={'riggingSizes': [2], 'riggingCorners': [{'at': 3.5, 'angle': 90}]}),
        dict(COLUMN, name='RIGHT', offset_x=2000, extra={'riggingSizes': [2], 'riggingCorners': [{'at': 3.5, 'angle': 90}]}),
    ])
    open_rigging(page)
    page.evaluate(f"() => window.app.setSelectedLayersByIds({ids}, {ids[0]})")
    page.click('#rigging-auto-btn')
    settled(page, lambda: [pieces(page, i) for i in ids], lambda p: all(p))
    assert pull_rig(page) == [['Header Bar - Corner (2 panel)', 2], ['Header Bar - Double', 4]]
    assert page.inner_text('#rigging-total-breakdown').split('\n') == ['Double: 4', 'Corner (2 panel): 2']
    assert page.errors == []


# ── 2. Every corner is 90 degrees ────────────────────────────────────────

CURVED = dict(COLUMN, columns=12, extra={'riggingSizes': [1, 2], 'riggingCurve': {'on': True}})


def test_a_corner_saved_under_90_takes_its_corner_bar_with_the_curve_on(page):
    """A 1.7.0 beta could save a corner under 90 degrees, and the Curve
    then split its bars at the corner with no corner bar. Every corner is
    90 now: that corner takes its corner bar and each side is curved."""
    spec = dict(CURVED, extra={**CURVED['extra'], 'riggingCorners': [{'at': 6.5, 'angle': 45, 'side': 'interior'}]})
    ids = reset(page, [spec])
    open_rigging(page)
    assert page.locator('#rigging-corners input').count() == 0
    page.click('#rigging-auto-btn')
    settled(page, lambda: pieces(page, ids[0]), lambda p: p and curve_idle(page), 15000)
    assert pieces(page, ids[0]) == [[6.5, 5, 2]]
    assert layer(page, ids[0])['riggingCorners'] == [{'at': 6.5, 'angle': 90, 'side': 'interior', 'bar': True}]
    assert not any(s < 7 and 5 < s + z for s, z in placed(page, ids[0]))
    assert pull_rig(page)[0] == ['Header Bar - Corner (2 panel)', 1]
    assert page.errors == []


# ── 3. With the Curve on, each side curves as its own wall ───────────────

# The calculator's answer for one wall `panels` wide with the screen's own
# lit sizes and Curve settings, no pick (curve-math.js screenCurve), and
# the joints the screen carries.
SIDES_JS = """async ([id, sides]) => {
    const m = await import('/static/js/curve-math.js');
    const a = window.app;
    const l = a.project.layers.find(x => x.id === id);
    const settings = { ...l.riggingCurve, pick: null, sidePicks: [] };
    const alone = sides.map(([start, panels]) => m.screenCurve({ panels, panelWidthM: 0.5,
        sizes: a._riggingSizesOf(l), settings }));
    const table = (l.stage3d && l.stage3d.jointsCol) || {};
    return { alone: alone.map(o => ({ joints: o.joints, bars: o.bars, errors: o.errors,
                                       radius: o.result ? o.result.achieved.radius_face_m : null })),
             joints: [...Array((Number(l.columns) || 1) - 1).keys()].map(j => table[String(j)]) };
}"""


def side_titles(page):
    return page.evaluate("""() => [...document.querySelectorAll('#rigging-curve-ways [data-side]')]
        .map(b => [b.dataset.side, b.firstElementChild.textContent])""")


def test_with_the_curve_on_each_side_of_a_corner_curves_as_its_own_wall(page):
    ids = reset(page, [CURVED])
    open_rigging(page)
    page.click('#rigging-auto-btn')
    settled(page, lambda: placed(page, ids[0]), lambda b: b and curve_idle(page), 15000)
    n = history_len(page)
    # Add corner: between panels 6 and 7, its corner bar on panels 6 and 7,
    # five panels on each side, laid by the Curve in one step
    page.click('#rigging-corner-add')
    settled(page, lambda: pieces(page, ids[0]), lambda p: p and curve_idle(page), 15000)
    assert pieces(page, ids[0]) == [[6.5, 5, 2]]
    assert history_len(page) == n + 1
    bars = placed(page, ids[0])
    # the Curve's bars run on each side up to the corner bar, never onto it
    assert not any(s < 7 and 5 < s + z for s, z in bars), bars
    covered = sorted(p for s, z in bars for p in range(s, s + z)) + [5, 6]
    assert sorted(covered) == list(range(12))
    # each side's angles are a five panel wall's at the same setting
    got = page.evaluate(SIDES_JS, [ids[0], [[0, 5], [7, 5]]])
    left, right = got['alone']
    assert left['errors'] == [] and any(left['joints'])
    assert got['joints'][0:4] == left['joints']
    assert got['joints'][7:11] == right['joints']
    # the corner bar's joints, inside it and at its ends, are flat
    assert got['joints'][4:7] == [0, 0, 0]
    assert [b for b in bars if b[0] < 5] == [[s, z] for s, z in _run(0, left['bars'])]
    assert [b for b in bars if b[0] >= 7] == [[s, z] for s, z in _run(7, right['bars'])]
    # the tab says each side: its readouts, its headline, its ways to build it
    read = page.inner_text('#rigging-curve-readouts')
    assert 'Left side, 5 panels' in read and 'Right side, 5 panels' in read
    head = page.inner_text('#rigging-curve-head').split('\n')
    assert [h.split(':')[0] for h in head] == ['Left side', 'Right side']
    assert side_titles(page) == [['0', 'Ways to build it, left side'], ['1', 'Ways to build it, right side']]
    assert page.locator('#rigging-curve-sheet [data-corner-bar]').count() == 1
    assert page.locator('#rigging-curve-plan svg [data-datum]').count() == 1
    assert pull_rig(page)[0] == ['Header Bar - Corner (2 panel)', 1]
    assert not page.locator('#rigging-fit-warning').is_visible()
    assert 'stays put' in page.inner_text('#rigging-corner-hold')
    # Use this on the right side builds that side that way, the left side
    # and the corner bar as they were
    use = page.locator('#rigging-curve-ways [data-side="1"] [data-pick]').first
    pick = use.get_attribute('data-pick')
    use.click()
    settled(page, lambda: (layer(page, ids[0])['riggingCurve'].get('sidePicks') or [None, None])[1:],
            lambda p: p and p[0] and curve_idle(page), 15000)
    curve = layer(page, ids[0])['riggingCurve']
    assert curve['sidePicks'][0] is None and curve['sidePicks'][1]['id'] == pick
    assert curve.get('pick') is None
    after = page.evaluate(SIDES_JS, [ids[0], [[0, 5], [7, 5]]])['joints']
    assert after[0:7] == got['joints'][0:7]
    assert pieces(page, ids[0]) == [[6.5, 5, 2]]
    assert 'You picked this one by hand' in page.inner_text('#rigging-curve-ways [data-side="1"]')
    assert 'You picked this one by hand' not in page.inner_text('#rigging-curve-ways [data-side="0"]')
    assert f'{pick}' == page.locator('#rigging-curve-ways [data-side="1"] .rigging-curve-way').filter(
        has_text='in use').first.get_attribute('data-way')
    # undo takes the pick back, then the corner and its corner bar, one step each
    page.evaluate('window.app.undo()')
    settled(page, lambda: layer(page, ids[0])['riggingCurve'].get('sidePicks'), lambda p: not p or not any(p))
    page.evaluate('window.app.undo()')
    lay = settled(page, lambda: layer(page, ids[0]), lambda v: not v.get('riggingCorners'))
    assert not lay.get('riggingCorners')
    assert page.errors == []


def _run(start, sizes):
    out = []
    for z in sizes:
        out.append((start, z))
        start += z
    return out


def test_two_corners_make_three_sides_each_curved_on_its_own(page):
    """Fourteen panels, a corner down the middle of panel 4 and one on the
    seam between panels 10 and 11: sides of 3, 5 and 3 panels."""
    spec = dict(CURVED, columns=14, extra={**CURVED['extra'], 'riggingCorners': [
        {'at': 4, 'angle': 90, 'side': 'interior'}, {'at': 10.5, 'angle': 90, 'side': 'exterior'}]})
    ids = reset(page, [spec])
    open_rigging(page)
    page.click('#rigging-auto-btn')
    settled(page, lambda: pieces(page, ids[0]), lambda p: len(p) == 2 and curve_idle(page), 15000)
    assert pieces(page, ids[0]) == [[4, 3, 1], [10.5, 9, 2]]
    got = page.evaluate(SIDES_JS, [ids[0], [[0, 3], [4, 5], [11, 3]]])
    one, two, three = got['alone']
    assert got['joints'] == one['joints'] + [0, 0] + two['joints'] + [0, 0, 0] + three['joints']
    assert side_titles(page) == [['0', 'Ways to build it, side 1'], ['1', 'Ways to build it, side 2'],
                                 ['2', 'Ways to build it, side 3']]
    read = page.inner_text('#rigging-curve-readouts')
    assert 'Side 1, 3 panels' in read and 'Side 2, 5 panels' in read and 'Side 3, 3 panels' in read
    assert page.errors == []


def test_with_the_curve_on_leftover_stock_is_refused_for_each_side(page):
    """Doubles only on a twelve panel wall with a 1 panel corner bar in the
    middle of panel 6: five panels on its left, six on its right. The
    Curve says which side is left uncovered and lays nothing."""
    spec = dict(CURVED, extra={**CURVED['extra'], 'riggingSizes': [2],
                               'riggingCorners': [{'at': 6, 'angle': 90, 'side': 'interior'}]})
    ids = reset(page, [spec])
    open_rigging(page)
    page.click('#rigging-auto-btn')
    text = settled(page, lambda: page.inner_text('#rigging-curve-errors') if page.locator('#rigging-curve-errors').is_visible() else '',
                   lambda t: 'uncovered' in t, 15000)
    assert text == 'These bar sizes leave 1 panel uncovered on the left side (5 panels). Light another size.'
    assert placed(page, ids[0]) == [] and pieces(page, ids[0]) == []
    # light singles too: each side is covered and the corner bar is laid
    page.click('#rigging-size-picker .rigging-size-btn[data-size="1"]')
    settled(page, lambda: pieces(page, ids[0]), lambda p: p and curve_idle(page), 15000)
    assert pieces(page, ids[0]) == [[6, 5, 1]]
    assert not any(s <= 5 < s + z for s, z in placed(page, ids[0]))
    assert not page.locator('#rigging-curve-errors').is_visible()
    assert page.errors == []


def _bottom_chain(obj):
    """The bottom edges of the OBJ's faces, walked end to end, in plan (x, z)."""
    ys = min(v[1] for v in obj['v'])
    edges = []
    for f in obj['objects'][0]['faces']:
        bl, br = obj['v'][f[0][0] - 1], obj['v'][f[1][0] - 1]
        if abs(bl[1] - ys) < 1e-6 and abs(br[1] - ys) < 1e-6:
            edges.append(((bl[0], bl[2]), (br[0], br[2])))
    order = [edges.pop(0)]
    while edges:
        nxt = next((e for e in edges if math.dist(e[0], order[-1][1]) < 1e-6), None)
        if nxt is None:
            nxt = next(e for e in edges if math.dist(e[1], order[0][0]) < 1e-6)
            order.insert(0, nxt)
        else:
            order.append(nxt)
        edges.remove(nxt)
    return order


def _circumcenter(a, b, c):
    bx, by = b[0] - a[0], b[1] - a[1]
    cx, cy = c[0] - a[0], c[1] - a[1]
    d = 2 * (bx * cy - by * cx)
    return (a[0] + (cy * (bx * bx + by * by) - by * (cx * cx + cy * cy)) / d,
            a[1] + (bx * (cx * cx + cy * cy) - cx * (bx * bx + by * by)) / d)


def test_the_obj_faces_sit_on_each_sides_own_radius(page):
    """Eleven 500 mm panels, 30 degrees of sweep, a corner down the middle
    of panel 5: the left side is four panels at 7.5 degrees a joint, the
    right side six at 5 degrees. In the OBJ every face of each side sits
    with its middle on that side's face radius, from curve-math.js, about
    one centre per side, to 0.1 mm."""
    spec = dict(COLUMN, columns=11, extra={'riggingSizes': [1], 'riggingCorners': [{'at': 5, 'angle': 90, 'side': 'interior'}],
                                            'riggingCurve': {'on': True, 'entry': 'degrees', 'value': 30, 'angles': [5, 7.5]}})
    ids = reset(page, [spec])
    open_rigging(page)
    page.click('#rigging-auto-btn')
    settled(page, lambda: pieces(page, ids[0]), lambda p: p and curve_idle(page), 15000)
    got = page.evaluate(SIDES_JS, [ids[0], [[0, 4], [5, 6]]])
    left, right = got['alone']
    assert left['joints'] == [7.5, 7.5, 7.5] and right['joints'] == [5, 5, 5, 5, 5]
    assert got['joints'] == [7.5, 7.5, 7.5, 0, 0, 5, 5, 5, 5, 5]
    want = page.evaluate("""async () => { const m = await import('/static/js/curve-math.js');
        return { face: [m.faceRadiusForAngle(0.5, 7.5), m.faceRadiusForAngle(0.5, 5)],
                 joints: [m.radiusForAngle(0.5, 7.5), m.radiusForAngle(0.5, 5)] }; }""")
    assert left['radius'] == pytest.approx(want['face'][0], abs=1e-9)
    assert right['radius'] == pytest.approx(want['face'][1], abs=1e-9)
    obj = read_obj(page.evaluate(OBJ_FILES_JS, 'Test Show')['Test_Show_COLUMN.obj'])
    chain = _bottom_chain(obj)
    # four faces, the two halves of panel 5, then six faces
    assert len(chain) == 12
    for k, (edges, face_r, joint_r) in enumerate(((chain[:4], want['face'][0], want['joints'][0]),
                                                   (chain[6:], want['face'][1], want['joints'][1]))):
        pts = [edges[0][0]] + [e[1] for e in edges]
        c = _circumcenter(pts[0], pts[len(pts) // 2], pts[-1])
        for a, b in edges:
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            assert abs(math.dist(mid, c) - face_r) < 1e-4, (k, math.dist(mid, c), face_r)
            assert abs(math.dist(a, c) - joint_r) < 1e-4, (k, math.dist(a, c), joint_r)
    # the two sides have radii of their own
    assert abs(want['face'][0] - want['face'][1]) > 1
    # and the corner folds 90 degrees between them, in the folded panel
    heads = [math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) for a, b in chain]
    assert round((heads[5] - heads[4] + 180) % 360 - 180, 3) == 90
    assert page.errors == []
