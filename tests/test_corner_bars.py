"""Corner bars, the owner's rulings of 2026-11-10 (app-corners.js, the bars
in app-rigging.js and rigging-math.js, the Curve in app-curve.js and
curve-math.js screenCurve):

* A corner down a panel's middle takes a "Header Bar - Corner (1 panel)"
  and one on a seam a "Header Bar - Corner (2 panel)": two parts, each
  its own line on the tab's totals, the pull list, the binder's
  Header/Footer sheet and its pull sheet.
* Every corner is 90 degrees and takes its corner bar; one saved under 90
  by a 1.7.0 beta opens as 90 (tests/test_corners.py too).
* With the Curve on, the corners split the screen into sides and the
  Curve's % applies to each side as its own wall. "the corner itself is
  flat due to the edge the opposite side of the 90 is curvable": only the
  fold takes no curve angle. Each side runs right up to the fold, its
  corner bar's arm included (a panel for a seam corner, half a panel for
  one down a panel's middle), so the joint where the arm meets the next
  bar takes the side's angle. Each side's angles are curve-math.js's for a
  wall of that side's width at the same settings, its stock bars run up
  to the corner bar, and the readouts, Ways to build it, Use this and the
  leftover-stock refusal are each side's, by name. Two corners make three
  sides. The OBJ puts each side's faces, the arm's too, on its own radius.
  A show saved before opens with its bars and angles as they were.
* Corners whose pieces would share a panel stay grayed out
  (tests/test_corners.py), and shows without corners are unchanged
  (tests/test_corner_rulings.py).

Run locally:
    python -m pytest tests/test_corner_bars.py -n 4 --dist loadfile -p no:cacheprovider
"""
import json
import math
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from conftest import settled  # noqa: E402
from test_corners import COLUMN, OBJ_FILES_JS, RESET_JS, history_len, layer, open_rigging, read_obj, served  # noqa: E402

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

# curve-math.js's own answer for one wall `panels` wide, its corner bars'
# arms `armL` and `armR` fixed bars at its ends (half panels worked in
# halves), with the screen's own lit sizes and Curve settings, no pick,
# built straight from the calculator (solveCurve): its joints at its seams,
# its stock bars as [start, size] in panels from its left end, and its face
# radius. And the joints the screen carries.
SIDES_JS = """async ([id, sides]) => {
    const m = await import('/static/js/curve-math.js');
    const a = window.app;
    const l = a.project.layers.find(x => x.id === id);
    const s = m.cleanCurve({ ...l.riggingCurve, pick: null, sidePicks: [] });
    const sizes = a._riggingSizesOf(l);
    const alone = sides.map(([panels, armL, armR, from]) => {
        const unit = Number.isInteger(armL) && Number.isInteger(armR) ? 1 : 0.5;
        const n = Math.round(panels / unit);
        const c = m.makeCurve('Side');
        c.panel.count = n;
        c.panel.width_m = 0.5 * unit;
        c.hardware.footer_widths_m = sizes.map(k => k * 0.5);
        c.hardware.detents_deg = [...s.angles];
        c.target = { mode: s.entry === 'degrees' ? 'sweep_deg' : 'percent_circle', value: s.value, radius_ref: 'face' };
        c.direction = s.bend;
        c.build_from = from || s.from;
        c.fit_goal = s.goal;
        c.tolerance_m = s.toleranceMm / 1000;
        const fixed = [...(armL ? [{ start: 0, size: armL / unit }] : []),
                       ...(armR ? [{ start: n - armR / unit, size: armR / unit }] : [])];
        c.layout_constraints = { pieces: fixed };
        const seams = [...Array(n - 1).keys()].filter(j => Number.isInteger((j + 1) * unit + (armL === 0.5 ? 0.5 : 0)));
        if (unit < 1) c.seam_joints = seams;
        const r = m.solveCurve(c);
        const sign = s.bend === 'concave' ? 1 : -1;
        const signed = r.joints.map(j => (j.angle_deg ? sign * j.angle_deg : 0));
        const bars = r.footers.filter(f => !fixed.some(p => p.start === f.from - 1 && p.size === f.panels))
            .map(f => [(f.from - 1) * unit, f.panels * unit]);
        return { joints: unit < 1 ? seams.map(j => signed[j]) : signed, bars, errors: r.errors,
                 radius: r.achieved.radius_face_m };
    });
    const table = (l.stage3d && l.stage3d.jointsCol) || {};
    return { alone, joints: [...Array((Number(l.columns) || 1) - 1).keys()].map(j => table[String(j)]) };
}"""


def side_titles(page):
    return page.evaluate("""() => [...document.querySelectorAll('#rigging-curve-ways [data-side]')]
        .map(b => [b.dataset.side, b.firstElementChild.textContent])""")


def _shift(start, bars):
    return [[start + s, z] for s, z in bars]


def test_with_the_curve_on_each_side_of_a_corner_curves_as_its_own_wall(page):
    ids = reset(page, [CURVED])
    open_rigging(page)
    page.click('#rigging-auto-btn')
    settled(page, lambda: placed(page, ids[0]), lambda b: b and curve_idle(page), 15000)
    n = history_len(page)
    # Add corner: between panels 6 and 7, its corner bar on panels 6 and 7,
    # each side six panels up to the seam, laid by the Curve in one step
    page.click('#rigging-corner-add')
    settled(page, lambda: pieces(page, ids[0]), lambda p: p and curve_idle(page), 15000)
    assert pieces(page, ids[0]) == [[6.5, 5, 2]]
    assert history_len(page) == n + 1
    bars = placed(page, ids[0])
    # the Curve's bars run on each side up to the corner bar, never onto it
    assert not any(s < 7 and 5 < s + z for s, z in bars), bars
    covered = sorted(p for s, z in bars for p in range(s, s + z)) + [5, 6]
    assert sorted(covered) == list(range(12))
    # each side's angles are a six panel wall's at the same setting, the
    # corner bar's arm its last (or first) panel
    got = page.evaluate(SIDES_JS, [ids[0], [[6, 0, 1], [6, 1, 0]]])
    left, right = got['alone']
    assert left['errors'] == [] and any(left['joints'])
    assert got['joints'][0:5] == left['joints']
    assert got['joints'][6:11] == right['joints']
    # the corner's own seam, 6|7, takes no curve angle; the far joints of
    # its corner bar, 5|6 and 7|8, take their side's
    assert got['joints'][5] == 0
    assert got['joints'][4] and got['joints'][6]
    assert [b for b in bars if b[0] < 5] == left['bars']
    assert [b for b in bars if b[0] >= 7] == _shift(6, right['bars'])
    # the tab says each side: its readouts, its headline, its ways to build it
    read = page.inner_text('#rigging-curve-readouts')
    assert 'Left side, 6 panels' in read and 'Right side, 6 panels' in read
    head = page.inner_text('#rigging-curve-head').split('\n')
    assert [h.split(':')[0] for h in head] == ['Left side', 'Right side']
    assert side_titles(page) == [['0', 'Ways to build it, left side'], ['1', 'Ways to build it, right side']]
    # the strip: the corner bar, the corner on its seam, and an angle on
    # each of its far joints
    assert page.locator('#rigging-curve-sheet [data-corner-bar]').count() == 1
    assert page.locator('#rigging-curve-sheet [data-corner-seam="5"]').count() == 1
    assert page.locator('#rigging-curve-sheet [data-angle="4"]').count() == 1
    assert page.locator('#rigging-curve-sheet [data-angle="6"]').count() == 1
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
    after = page.evaluate(SIDES_JS, [ids[0], [[6, 0, 1], [6, 1, 0]]])['joints']
    assert after[0:6] == got['joints'][0:6]
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


def test_a_corner_down_a_panels_middle_curves_both_its_seams(page):
    """Twelve panels, a corner down the middle of panel 3: the left side is
    panels 1, 2 and the left half of 3, the right side the right half of 3
    onward. The fold is the 90; the panel's own seams, 2|3 and 3|4, are on
    their sides' arcs, each side as curve-math works a wall that wide."""
    spec = dict(CURVED, extra={**CURVED['extra'], 'riggingSizes': [1],
                               'riggingCurve': {'on': True, 'entry': 'degrees', 'value': 12.5,
                                                'angles': [3.75, 5], 'goal': 'tightest'},
                               'riggingCorners': [{'at': 3, 'angle': 90, 'side': 'interior'}]})
    ids = reset(page, [spec])
    open_rigging(page)
    page.click('#rigging-auto-btn')
    settled(page, lambda: pieces(page, ids[0]), lambda p: p and curve_idle(page), 15000)
    assert pieces(page, ids[0]) == [[3, 2, 1]]
    got = page.evaluate(SIDES_JS, [ids[0], [[2.5, 0, 0.5], [9.5, 0.5, 0]]])
    left, right = got['alone']
    assert left['errors'] == [] and right['errors'] == []
    assert got['joints'][0:2] == left['joints']
    assert got['joints'][2:] == right['joints']
    assert got['joints'][1] and got['joints'][2]
    assert placed(page, ids[0]) == [[0, 1], [1, 1]] + [[p, 1] for p in range(3, 12)]
    read = page.inner_text('#rigging-curve-readouts')
    assert 'Left side, 2.5 panels' in read and 'Right side, 9.5 panels' in read
    # Ways to build it counts each side's seams: two on the left
    rows = page.inner_text('#rigging-curve-ways [data-side="0"]')
    assert all(int(b) + int(f) == 2 for b, f in
               re.findall(r'(\d+) bent, (\d+) flat', rows)), rows
    assert page.locator('#rigging-curve-sheet [data-angle="1"]').count() == 1
    assert page.locator('#rigging-curve-sheet [data-angle="2"]').count() == 1
    assert page.errors == []


def test_two_corners_make_three_sides_each_curved_on_its_own(page):
    """Fourteen panels, a corner down the middle of panel 4 and one on the
    seam between panels 10 and 11: sides of 3.5, 6.5 and 4 panels, each up
    to its folds."""
    spec = dict(CURVED, columns=14, extra={**CURVED['extra'], 'riggingCorners': [
        {'at': 4, 'angle': 90, 'side': 'interior'}, {'at': 10.5, 'angle': 90, 'side': 'exterior'}]})
    ids = reset(page, [spec])
    open_rigging(page)
    page.click('#rigging-auto-btn')
    settled(page, lambda: pieces(page, ids[0]), lambda p: len(p) == 2 and curve_idle(page), 15000)
    assert pieces(page, ids[0]) == [[4, 3, 1], [10.5, 9, 2]]
    got = page.evaluate(SIDES_JS, [ids[0], [[3.5, 0, 0.5], [6.5, 0.5, 1], [4, 1, 0]]])
    one, two, three = got['alone']
    # the seam corner's own seam, 10|11, is the only flat one
    assert got['joints'] == one['joints'] + two['joints'] + [0] + three['joints']
    assert side_titles(page) == [['0', 'Ways to build it, side 1'], ['1', 'Ways to build it, side 2'],
                                 ['2', 'Ways to build it, side 3']]
    read = page.inner_text('#rigging-curve-readouts')
    assert 'Side 1, 3.5 panels' in read and 'Side 2, 6.5 panels' in read and 'Side 3, 4 panels' in read
    assert page.errors == []


def test_with_the_curve_on_leftover_stock_is_refused_for_each_side(page):
    """Doubles only on a twelve panel wall with a 1 panel corner bar in the
    middle of panel 6: five panels between the left end and the corner
    bar, six on its right. The Curve says which side is left uncovered
    and lays nothing."""
    spec = dict(CURVED, extra={**CURVED['extra'], 'riggingSizes': [2],
                               'riggingCorners': [{'at': 6, 'angle': 90, 'side': 'interior'}]})
    ids = reset(page, [spec])
    open_rigging(page)
    page.click('#rigging-auto-btn')
    text = settled(page, lambda: page.inner_text('#rigging-curve-errors') if page.locator('#rigging-curve-errors').is_visible() else '',
                   lambda t: 'uncovered' in t, 15000)
    assert text == 'These bar sizes leave 1 panel uncovered on the left side (5.5 panels). Light another size.'
    assert placed(page, ids[0]) == [] and pieces(page, ids[0]) == []
    # light singles too: each side is covered and the corner bar is laid
    page.click('#rigging-size-picker .rigging-size-btn[data-size="1"]')
    settled(page, lambda: pieces(page, ids[0]), lambda p: p and curve_idle(page), 15000)
    assert pieces(page, ids[0]) == [[6, 5, 1]]
    assert not any(s <= 5 < s + z for s, z in placed(page, ids[0]))
    assert not page.locator('#rigging-curve-errors').is_visible()
    assert page.errors == []


def test_a_show_saved_before_opens_with_its_bars_and_angles_as_they_were(page):
    """A curved screen with a seam corner saved when each side stopped at
    the corner bar: its arms' far joints flat, and a pick for the right
    side under the key of then. It opens with every stored bar, angle and
    setting as saved; the tab says the curve is not laid yet, and Auto
    lays it with the arms' far joints bent and the old pick dropped."""
    old_key = json.dumps([5, 0.5, [1, 2], 'percent', 20, 'concave', 'simplest', 25, [2.5, 5, 7.5, 10],
                          ['side', 1, 2, 7]], separators=(',', ':'))
    joints = {str(j): (0 if 4 <= j <= 6 else 10) for j in range(11)}
    curve = {'on': True, 'sidePicks': [None, {'id': '10', 'key': old_key}]}
    spec = dict(CURVED, extra={**CURVED['extra'], 'riggingCurve': curve,
                               'riggingCorners': [{'at': 6.5, 'angle': 90, 'side': 'interior', 'bar': True}],
                               'riggingBars': [1, 1, 1, 1, 1, 1, 1, 1, 1, 1], 'riggingBarStarts': [0, 1, 2, 3, 4, 7, 8, 9, 10, 11],
                               'stage3d': {'x': 0, 'y': 0, 'z': 0, 'pitch': 0, 'yaw': 0, 'roll': 0,
                                           'jointsCol': joints, 'pivot': 'bottom'}})
    ids = reset(page, [spec])
    before = served(page, ids[0])
    open_rigging(page)
    settled(page, lambda: page.inner_text('#rigging-curve-note'), lambda t: 'not this curve' in t, 15000)
    page.wait_for_timeout(300)
    after = served(page, ids[0])
    for key in ('stage3d', 'riggingBars', 'riggingBarStarts', 'riggingCurve', 'riggingCorners', 'panels'):
        assert after.get(key) == before.get(key), key
    assert layer(page, ids[0])['stage3d']['jointsCol'] == joints
    # the old pick no longer matches a side: the right side is the app's pick
    assert 'You picked this one by hand' not in page.inner_text('#rigging-curve-ways')
    page.click('#rigging-auto-btn')
    got = settled(page, lambda: page.evaluate(SIDES_JS, [ids[0], [[6, 0, 1], [6, 1, 0]]]),
                  lambda g: g['joints'][4] and curve_idle(page), 15000)
    assert got['joints'][0:5] == got['alone'][0]['joints']
    assert got['joints'][6:11] == got['alone'][1]['joints']
    assert got['joints'][5] == 0 and got['joints'][4] and got['joints'][6]
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


def _on_one_circle(edges, joint_r, face_r):
    """Every edge's ends on one circle of radius joint_r, its middle at
    face_r[i] from the same centre (face_r one per edge), to 0.1 mm."""
    pts = [edges[0][0]] + [e[1] for e in edges]
    c = _circumcenter(pts[0], pts[len(pts) // 2], pts[-1])
    for (a, b), want in zip(edges, face_r):
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        assert abs(math.dist(mid, c) - want) < 1e-4, (math.dist(mid, c), want)
        assert abs(math.dist(a, c) - joint_r) < 1e-4, (math.dist(a, c), joint_r)
        assert abs(math.dist(b, c) - joint_r) < 1e-4, (math.dist(b, c), joint_r)


def test_the_obj_faces_sit_on_each_sides_own_radius_arms_included(page):
    """Ten 500 mm panels, 30 degrees of sweep, a corner on the seam between
    panels 4 and 5: the left side is panels 1 to 4 at 7.5 degrees a joint,
    the right side panels 5 to 10 at 5 degrees, the corner bar's arms (4
    and 5) on them. In the OBJ every face of each side, the arm's too,
    sits on that side's radius from curve-math.js, to 0.1 mm."""
    spec = dict(COLUMN, columns=10, extra={'riggingSizes': [1], 'riggingCorners': [{'at': 4.5, 'angle': 90, 'side': 'interior'}],
                                            'riggingCurve': {'on': True, 'entry': 'degrees', 'value': 30, 'angles': [5, 7.5]}})
    ids = reset(page, [spec])
    open_rigging(page)
    page.click('#rigging-auto-btn')
    settled(page, lambda: pieces(page, ids[0]), lambda p: p and curve_idle(page), 15000)
    got = page.evaluate(SIDES_JS, [ids[0], [[4, 0, 1], [6, 1, 0]]])
    left, right = got['alone']
    assert left['joints'] == [7.5, 7.5, 7.5] and right['joints'] == [5, 5, 5, 5, 5]
    # the arms' far joints, 3|4 and 5|6, bend; the corner's seam does not
    assert got['joints'] == [7.5, 7.5, 7.5, 0, 5, 5, 5, 5, 5]
    want = page.evaluate("""async () => { const m = await import('/static/js/curve-math.js');
        return { face: [m.faceRadiusForAngle(0.5, 7.5), m.faceRadiusForAngle(0.5, 5)],
                 joints: [m.radiusForAngle(0.5, 7.5), m.radiusForAngle(0.5, 5)] }; }""")
    assert left['radius'] == pytest.approx(want['face'][0], abs=1e-9)
    assert right['radius'] == pytest.approx(want['face'][1], abs=1e-9)
    obj = read_obj(page.evaluate(OBJ_FILES_JS, 'Test Show')['Test_Show_COLUMN.obj'])
    chain = _bottom_chain(obj)
    assert len(chain) == 10
    _on_one_circle(chain[:4], want['joints'][0], [want['face'][0]] * 4)
    _on_one_circle(chain[4:], want['joints'][1], [want['face'][1]] * 6)
    # the two sides have radii of their own
    assert abs(want['face'][0] - want['face'][1]) > 1
    # and the corner folds 90 degrees between them, on the seam
    heads = [math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) for a, b in chain]
    assert round((heads[4] - heads[3] + 180) % 360 - 180, 3) == 90
    assert page.errors == []


def test_the_obj_puts_a_folded_panels_halves_on_their_sides_radius(page):
    """Eleven 500 mm panels, a corner down the middle of panel 5, built
    from the fold: 4.5 panels on the left and 6.5 on the right, 23.4
    degrees of sweep each, 2.6 and 1.8 degrees a half panel. A whole panel
    takes twice that at its joints and the half panel's far joint one and
    a half times (true to a thousandth of a degree), so each side is a
    true arc: in the OBJ every face, the folded panel's halves too, has its
    ends on its side's circle and its middle where a chord that wide sits
    inside it, to 0.1 mm."""
    spec = dict(COLUMN, columns=11, extra={'riggingSizes': [1], 'riggingCorners': [{'at': 5, 'angle': 90, 'side': 'interior'}],
                                            'riggingCurve': {'on': True, 'entry': 'degrees', 'value': 23.4, 'from': 5,
                                                             'goal': 'tightest', 'angles': [2.7, 3.6, 3.9, 5.2]}})
    ids = reset(page, [spec])
    open_rigging(page)
    page.click('#rigging-auto-btn')
    settled(page, lambda: pieces(page, ids[0]), lambda p: p and curve_idle(page), 15000)
    got = page.evaluate(SIDES_JS, [ids[0], [[4.5, 0, 0.5, 'right'], [6.5, 0.5, 0, 'left']]])
    left, right = got['alone']
    assert left['joints'] == [5.2, 5.2, 5.2, 3.9] and right['joints'] == [2.7, 3.6, 3.6, 3.6, 3.6, 3.6]
    assert got['joints'] == left['joints'] + right['joints']
    want = page.evaluate("""async () => { const m = await import('/static/js/curve-math.js');
        const r = [m.radiusForAngle(0.5, 5.2), m.radiusForAngle(0.5, 3.6)];
        return { joints: r, face: [m.faceRadiusForAngle(0.5, 5.2), m.faceRadiusForAngle(0.5, 3.6)],
                 half: r.map(R => Math.sqrt(R * R - 0.125 * 0.125)) }; }""")
    obj = read_obj(page.evaluate(OBJ_FILES_JS, 'Test Show')['Test_Show_COLUMN.obj'])
    chain = _bottom_chain(obj)
    # four faces, the two halves of panel 5, then six faces
    assert len(chain) == 12
    _on_one_circle(chain[:5], want['joints'][0], [want['face'][0]] * 4 + [want['half'][0]])
    _on_one_circle(chain[5:], want['joints'][1], [want['half'][1]] + [want['face'][1]] * 6)
    heads = [math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) for a, b in chain]
    assert round((heads[5] - heads[4] + 180) % 360 - 180, 3) == 90
    assert page.errors == []
