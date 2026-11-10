"""Corner bars, the owner's rulings of 2026-11-10 (app-corners.js, the bars
in app-rigging.js and rigging-math.js, the Curve in app-curve.js and
curve-math.js screenCurve):

* A corner down a panel's middle takes a "Header Bar - Corner (1 panel)"
  and one on a seam a "Header Bar - Corner (2 panel)": two parts, each
  its own line on the tab's totals, the pull list, the binder's
  Header/Footer sheet and its pull sheet.
* Only a full 90 degree corner takes a corner bar. Under 90 the regular
  bars split at the corner without crossing it; the corner's row and the
  Corners block say so. Taking an angle from 90 to less, or back, lays an
  Auto row again in the same undo step.
* With the Curve on, a 90 degree corner still takes its corner bar and the
  Curve lays its bars on each side up to it, with Ways to build it and
  the leftover-stock refusal for each side.
* Corners whose pieces would share a panel stay grayed out
  (tests/test_corners.py), and shows without corners are unchanged
  (tests/test_corner_rulings.py).

Run locally:
    python -m pytest tests/test_corner_bars.py -n 4 --dist loadfile -p no:cacheprovider
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from conftest import settled  # noqa: E402
from test_corners import COLUMN, RESET_JS, history_len, layer, open_rigging, row, served  # noqa: E402

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


def crosses(bars, edges):
    return [b for b in bars if any(b[0] < e < b[0] + b[1] for e in edges)]


def set_angle(page, at, value):
    sel = f'{row(page, at)} [data-corner-angle]'
    page.fill(sel, str(value))
    page.press(sel, 'Enter')


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


# ── 2. Only a 90 degree corner takes a corner bar ────────────────────────

def test_a_45_degree_corner_takes_no_corner_bar_and_no_bar_crosses_it(page):
    ids = reset(page, [dict(COLUMN, extra={'riggingSizes': [1, 2], 'riggingCorners': [
        {'at': 3.5, 'angle': 45, 'side': 'interior'}]})])
    open_rigging(page)
    page.click('#rigging-auto-btn')
    bars = settled(page, lambda: placed(page, ids[0]), lambda b: b)
    # the seam between panels 3 and 4 is row edge 3: the bars split there
    assert bars == [[0, 1], [1, 2], [3, 1], [4, 2]]
    assert crosses(bars, [3]) == []
    assert pieces(page, ids[0]) == []
    assert all('Corner' not in t for t, _ in pull_rig(page))
    assert pull_rig(page) == [['Header Bar - Double', 2], ['Header Bar - Single', 2]]
    assert not page.locator('#rigging-fit-warning').is_visible()
    # the row and the block say only a 90 degree corner takes a corner bar
    note = page.inner_text(f'{row(page, 3.5)} .rigging-corner-split')
    assert note == 'Only a 90° corner takes a corner bar. Here the bars split at the seam.'
    assert page.locator('#rigging-corner-rule').is_visible()
    assert 'Only a 90° corner takes a corner bar.' in page.inner_text('#rigging-corner-rule')
    # down the middle of panel 3 at 45: the folded panel takes a bar of its own
    page.select_option(f'{row(page, 3.5)} [data-corner-at]', '3')
    bars = settled(page, lambda: placed(page, ids[0]), lambda b: [2, 1] in b)
    assert bars == [[0, 2], [2, 1], [3, 1], [4, 2]]
    assert crosses(bars, [2, 3]) == []
    assert pieces(page, ids[0]) == []
    assert 'folded panel takes a bar of its own' in page.inner_text(f'{row(page, 3)} .rigging-corner-split')
    assert page.errors == []


def test_a_bar_laid_by_hand_across_a_corner_under_90_comes_off(page):
    ids = reset(page, [dict(COLUMN, extra={'riggingBars': [2], 'riggingBarStarts': [2], 'riggingCustom': True})])
    open_rigging(page)
    page.evaluate("() => { const h = document.getElementById('app-toast-host'); if (h) h.innerHTML = ''; }")
    page.click('#rigging-corner-add')
    settled(page, lambda: pieces(page, ids[0]), lambda p: p)
    # at 90 the double on panels 3 and 4 made way for the corner bar
    assert placed(page, ids[0]) == []
    set_angle(page, 3.5, 30)
    lay = settled(page, lambda: layer(page, ids[0]), lambda v: v['riggingCorners'][0]['angle'] == 30)
    assert 'bar' not in lay['riggingCorners'][0]
    # a double laid by hand stops at the corner, never across it
    page.evaluate("() => window.app.setRiggingTool('custom')")
    out = page.evaluate("""(id) => { const a = window.app; a._riggingCustomSize = 2;
        const l = a.project.layers.find(x => x.id === id);
        const d = a.riggingBeginPlace(l, 'header', 2); a.riggingPreviewPlace(d, 2); a.riggingEndDrag(d, true);
        return a.riggingPlaced(a.project.layers.find(x => x.id === id), 'header').map(b => [b.start, b.size]); }""", ids[0])
    assert out == [[1, 2]]
    assert page.errors == []


def test_90_to_45_to_90_lays_the_auto_row_again_one_undo_step_each(page):
    ids = reset(page, [dict(COLUMN, extra={'riggingSizes': [1, 2]})])
    open_rigging(page)
    page.click('#rigging-corner-add')
    lay = settled(page, lambda: layer(page, ids[0]), lambda v: v.get('riggingCorners'))
    page.click('#rigging-auto-btn')
    settled(page, lambda: placed(page, ids[0]), lambda b: b == [[0, 2], [4, 2]])
    assert pieces(page, ids[0]) == [[3.5, 2, 2]]
    n = history_len(page)
    # 90 to 45: the corner bar goes and the bars split at the seam
    set_angle(page, 3.5, 45)
    bars = settled(page, lambda: placed(page, ids[0]), lambda b: b == [[0, 1], [1, 2], [3, 1], [4, 2]])
    assert bars == [[0, 1], [1, 2], [3, 1], [4, 2]]
    assert pieces(page, ids[0]) == []
    assert history_len(page) == n + 1
    assert pull_rig(page) == [['Header Bar - Double', 2], ['Header Bar - Single', 2]]
    # back to 90: the corner bar comes back and the bars run up to it
    set_angle(page, 3.5, 90)
    settled(page, lambda: placed(page, ids[0]), lambda b: b == [[0, 2], [4, 2]])
    assert pieces(page, ids[0]) == [[3.5, 2, 2]]
    assert history_len(page) == n + 2
    # a change that keeps it under 90 lays nothing again
    set_angle(page, 3.5, 60)
    settled(page, lambda: layer(page, ids[0])['riggingCorners'][0]['angle'], lambda a: a == 60)
    set_angle(page, 3.5, 30)
    settled(page, lambda: layer(page, ids[0])['riggingCorners'][0]['angle'], lambda a: a == 30)
    assert placed(page, ids[0]) == [[0, 1], [1, 2], [3, 1], [4, 2]]
    # undo walks back one step at a time: the angle and its bars together
    for want_angle, want_bars, want_pieces in ((60, [[0, 1], [1, 2], [3, 1], [4, 2]], []),
                                               (90, [[0, 2], [4, 2]], [[3.5, 2, 2]]),
                                               (45, [[0, 1], [1, 2], [3, 1], [4, 2]], []),
                                               (90, [[0, 2], [4, 2]], [[3.5, 2, 2]])):
        page.evaluate('window.app.undo()')
        settled(page, lambda: layer(page, ids[0])['riggingCorners'][0]['angle'], lambda a: a == want_angle)
        assert layer(page, ids[0])['riggingCorners'][0]['angle'] == want_angle
        assert placed(page, ids[0]) == want_bars
        assert pieces(page, ids[0]) == want_pieces
    assert history_len(page) == n + 4
    # and the server has the last one
    assert settled(page, lambda: served(page, ids[0])['riggingCorners'][0].get('bar'), lambda v: v is True) is True
    assert page.errors == []


# ── 3. With the Curve on ─────────────────────────────────────────────────

CURVED = dict(COLUMN, columns=12, extra={'riggingSizes': [1, 2], 'riggingCurve': {'on': True}})


def test_with_the_curve_on_a_90_degree_corner_keeps_its_corner_bar(page):
    ids = reset(page, [CURVED])
    open_rigging(page)
    page.click('#rigging-auto-btn')
    settled(page, lambda: placed(page, ids[0]), lambda b: b and curve_idle(page), 15000)
    n = history_len(page)
    # Add corner: between panels 6 and 7, laid around by the Curve in one step
    page.click('#rigging-corner-add')
    settled(page, lambda: pieces(page, ids[0]), lambda p: p and curve_idle(page), 15000)
    assert pieces(page, ids[0]) == [[6.5, 5, 2]]
    bars = placed(page, ids[0])
    # the Curve's bars run on each side up to the corner bar, never onto it
    assert not any(s < 7 and 5 < s + z for s, z in bars), bars
    covered = sorted(p for s, z in bars for p in range(s, s + z)) + [5, 6]
    assert sorted(covered) == list(range(12))
    lay = layer(page, ids[0])
    joints = lay['stage3d']['jointsCol']
    # the corner's seam (joint 5) is inside the corner bar and takes no curve angle
    assert joints['5'] == 0
    assert any(joints[k] for k in joints)
    assert history_len(page) == n + 1
    # the block no longer says a curved screen takes no corner bar
    hold = page.inner_text('#rigging-corner-hold')
    assert 'no corner bar' not in hold and 'stays put' in hold
    # the Curve's strip marks the corner bar, and Ways to build it is there
    assert page.locator('#rigging-curve-sheet [data-corner-bar]').count() == 1
    assert page.locator('#rigging-curve-ways .rigging-curve-way').count() >= 1
    assert pull_rig(page)[0] == ['Header Bar - Corner (2 panel)', 1]
    assert not page.locator('#rigging-fit-warning').is_visible()
    # Use this on another way builds it that way, the corner bar kept
    other = page.locator('#rigging-curve-ways [data-pick]').first
    pick = other.get_attribute('data-pick')
    other.click()
    settled(page, lambda: layer(page, ids[0])['riggingCurve'].get('pick'), lambda p: p and curve_idle(page), 15000)
    assert layer(page, ids[0])['riggingCurve']['pick']['id'] == pick
    assert pieces(page, ids[0]) == [[6.5, 5, 2]]
    assert not any(s < 7 and 5 < s + z for s, z in placed(page, ids[0]))
    # undo takes the pick back, then the corner and its corner bar, one step each
    page.evaluate('window.app.undo()')
    settled(page, lambda: layer(page, ids[0])['riggingCurve'].get('pick'), lambda p: not p)
    page.evaluate('window.app.undo()')
    lay = settled(page, lambda: layer(page, ids[0]), lambda v: not v.get('riggingCorners'))
    assert not lay.get('riggingCorners')
    assert page.errors == []


def test_with_the_curve_on_leftover_stock_is_refused_for_each_side(page):
    """Doubles only on a twelve panel wall with a 1 panel corner bar in the
    middle of panel 6: five panels on its left, six on its right. The
    Curve says what is left uncovered and lays nothing."""
    spec = dict(CURVED, extra={**CURVED['extra'], 'riggingSizes': [2],
                               'riggingCorners': [{'at': 6, 'angle': 90, 'side': 'interior'}]})
    ids = reset(page, [spec])
    open_rigging(page)
    page.click('#rigging-auto-btn')
    text = settled(page, lambda: page.inner_text('#rigging-curve-errors') if page.locator('#rigging-curve-errors').is_visible() else '',
                   lambda t: 'uncovered' in t, 15000)
    assert text == 'These bar sizes leave 1 panel uncovered beside the corners on a 12-panel wall. Light another size.'
    assert placed(page, ids[0]) == [] and pieces(page, ids[0]) == []
    # light singles too: each side is covered and the corner bar is laid
    page.click('#rigging-size-picker .rigging-size-btn[data-size="1"]')
    settled(page, lambda: pieces(page, ids[0]), lambda p: p and curve_idle(page), 15000)
    assert pieces(page, ids[0]) == [[6, 5, 1]]
    assert not any(s <= 5 < s + z for s, z in placed(page, ids[0]))
    assert page.errors == []


def test_with_the_curve_on_a_corner_under_90_splits_the_curves_bars(page):
    spec = dict(CURVED, extra={**CURVED['extra'], 'riggingCorners': [{'at': 6.5, 'angle': 45, 'side': 'interior'}]})
    ids = reset(page, [spec])
    open_rigging(page)
    page.click('#rigging-auto-btn')
    bars = settled(page, lambda: placed(page, ids[0]), lambda b: b and curve_idle(page), 15000)
    assert pieces(page, ids[0]) == []
    assert crosses(bars, [6]) == []
    assert sum(z for _, z in bars) == 12
    assert layer(page, ids[0])['stage3d']['jointsCol']['5'] == 0
    assert page.errors == []
