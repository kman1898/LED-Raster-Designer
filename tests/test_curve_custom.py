"""Custom on a curved wall (app-curve.js), in the real app.

Owner's request (2026-11-18): "i need to be able to do custom curve just
like header", ruled both. With Curve on, the Header/Footer tab's Custom
lays bars by hand with the same click and drag as a plain header, and the
Curve fits the angles to those bars (bending only where no bar runs
across, from the panel's lock positions); a click on a joint of the build
sheet strip sets its angle by hand, and the Curve fills in the rest.

What this file pins:

* A Custom drag on a curved screen keeps its bars as laid and the angles
  are fitted to them: no bend under a bar, one undo step, no refusal.
* A joint picked on the strip and set by hand keeps its angle, is drawn as
  set by hand, saves with the show and comes back on a reload; Auto on the
  pick hands that joint back; Auto on the tab hands the row back to the
  Curve, the hand choices cleared, one undo step.
* Refused in plain words, nothing changed: a joint under a bar set to
  bend, and a bar laid across a joint set by hand to bend.
* A grouped wall takes Custom as one wall: a bar across a seam holds the
  seam straight, a seam set by hand bends there in 3D, and the pull list
  counts the bars once.
* Remove Bar on a curved row takes the bar off and the angles follow.
* Curve ticked on over bars laid by hand on a plain header lays the
  Curve's own bars, as it always did.

Run locally:
    python -m pytest tests/test_curve_custom.py -n 4 --dist loadfile
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from conftest import settled  # noqa: E402
from test_curve_obj import (  # noqa: E402
    act, group_two, history_len, idle, joints_of, layer, open_rigging, reset, served, singles_only, toast_says,
)
from test_curve_group import joined, own_joints, three, turns, wall_edges  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project as this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1500, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.errors = []
    pg.on('pageerror', lambda err: pg.errors.append(str(err)))
    pg.route('**/api/native-dialog/**', lambda r: r.fulfill(status=503, body='{}'))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    yield pg
    context.close()


def select(page, ids, primary=None):
    page.evaluate(f"window.app.setSelectedLayersByIds({list(ids)}, {primary if primary is not None else ids[0]})")
    page.evaluate("window.app.refreshRiggingPanel()")


def light(page, sizes):
    """Light exactly `sizes` for the screen the tab shows."""
    lit = page.evaluate("() => window.app._riggingSizesOf(window.app.currentLayer)")
    for s in (1, 2):
        if (s in sizes) != (s in lit):
            page.click(f'#rigging-size-picker .rigging-size-btn[data-size="{s}"]')
            idle(page)


def tool(page, which):
    page.click(f'#rigging-tool-picker [data-tool="{which}"]')
    page.wait_for_timeout(100)


def lay_bars(page, layer_id, size, frm, to):
    """One Custom press on panel `frm` of the screen, dragged to `to`, with
    `size` picked: the gesture app-rigging.js runs for a click and drag."""
    out = page.evaluate("""([id, size, frm, to]) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === id);
        app._riggingCustomSize = size;
        const d = app.riggingBeginPlace(l, 'header', frm);
        if (!d) return null;
        app.riggingPreviewPlace(d, d.from + (to - frm));
        return app.riggingEndDrag(d, true);
    }""", [layer_id, size, frm, to])
    idle(page)
    return out


def placed(lay):
    """A screen's header bars as [start, size]."""
    bars = lay.get('riggingBars') or []
    starts = lay.get('riggingBarStarts')
    out, at = [], 0
    for i, n in enumerate(bars):
        s = starts[i] if starts else at
        out.append([s, n])
        at = s + n
    return out


def solve(page, layer_id):
    return page.evaluate("""(id) => {
        const out = window.app.riggingCurveSolve(window.app.project.layers.find(x => x.id === id));
        return { bars: out.bars, starts: out.starts || null, joints: out.joints, errors: out.errors, hand: !!out.hand };
    }""", layer_id)


def pick_joint(page, j, value):
    """A click on joint `j` of the strip, then on `value` below it."""
    page.locator(f'#rigging-curve-sheet rect[data-joint="{j}"]').click()
    page.wait_for_selector('#rigging-curve-joint [data-joint-angle]')
    act(page, lambda: page.locator(f'#rigging-curve-joint [data-joint-angle="{value}"]').click())


def curved_singles(page, specs=None):
    ids = reset(page) if specs is None else reset(page, specs)
    open_rigging(page)
    singles_only(page)
    act(page, lambda: page.check('#rigging-curve-on'))
    return ids


# ── bars laid by hand ────────────────────────────────────────────────────

def test_a_custom_drag_on_a_curved_screen_keeps_its_bars_and_fits_the_angles(page):
    ids = curved_singles(page)
    wid = ids[0]
    light(page, [1, 2])
    act(page, lambda: page.click('#rigging-tool-picker [data-tool="auto"]'))
    tool(page, 'custom')
    assert 'Custom does not' not in page.inner_text('#rigging-curve-note')
    n = history_len(page)
    before = layer(page, wid)
    assert lay_bars(page, wid, 2, 0, 5) is True
    lay = layer(page, wid)
    # the three doubles as laid, the rest as they were, the row laid by hand
    assert placed(lay)[:3] == [[0, 2], [2, 2], [4, 2]], placed(lay)
    assert lay['riggingCustom'] is True and lay['riggingCurve']['on']
    joints = joints_of(lay)
    assert joints[0] == 0 and joints[2] == 0 and joints[4] == 0, joints
    assert any(joints), joints
    # the calculator's answer for the bars as laid is the one laid
    want = solve(page, wid)
    assert want['errors'] == [] and want['hand'] is True
    assert want['joints'] == joints
    assert history_len(page) == n + 1
    assert 'Laid by hand' in page.inner_text('#rigging-curve-note')
    assert page.locator('#rigging-curve-sheet rect[data-hand-bar]').count() == len(placed(lay))
    assert not page.evaluate("() => (document.querySelector('#app-toast-host') || {}).innerText || ''").count('laid by the Curve')
    # one undo takes the gesture and its angles back
    page.evaluate('window.app.undo()')
    back = settled(page, lambda: layer(page, wid), lambda l: l.get('riggingCustom') is not True)
    assert placed(back) == placed(before) and joints_of(back) == joints_of(before)
    assert page.errors == []


def test_a_joint_set_by_hand_keeps_its_angle_saves_and_auto_hands_it_back(page, e2e_server):
    ids = curved_singles(page)
    wid = ids[0]
    lay = layer(page, wid)
    bars = placed(lay)
    j = next(k for k, a in enumerate(joints_of(lay)) if a == 0)
    n = history_len(page)
    pick_joint(page, j, '10')
    lay = layer(page, wid)
    assert joints_of(lay)[j] == 10
    assert lay['riggingCurve']['handJoints'] == {str(j): 10}
    assert lay['riggingCustom'] is True
    assert placed(lay) == bars
    assert history_len(page) == n + 1
    assert page.locator(f'#rigging-curve-sheet [data-hand-angle="{j}"]').count() == 1
    assert 'set by hand' in page.inner_text('#rigging-curve-joint')
    # the other joints are the Curve's, fitted around it
    assert solve(page, wid)['joints'] == joints_of(lay)
    # saved with the show, and back after a reload
    settled(page, lambda: served(page, wid),
            lambda l: (l.get('riggingCurve') or {}).get('handJoints') == {str(j): 10} and joints_of(l) == joints_of(lay))
    page.reload(wait_until='domcontentloaded')
    page.wait_for_timeout(2000)
    page.evaluate("(id) => { window.app.selectLayer(window.app.project.layers.find(l => l.id === id)); window.app.updateUI(); }", wid)
    open_rigging(page)
    idle(page)
    again = layer(page, wid)
    assert again['riggingCurve']['handJoints'] == {str(j): 10} and joints_of(again) == joints_of(lay)
    assert page.locator(f'#rigging-curve-sheet [data-hand-angle="{j}"]').count() == 1
    # Auto on the pick hands the joint back; the bars stay laid by hand
    pick_joint(page, j, 'auto')
    after = layer(page, wid)
    assert 'handJoints' not in after['riggingCurve']
    assert after['riggingCustom'] is True and placed(after) == bars
    # Auto on the tab hands the row back to the Curve
    pick_joint(page, j, '10')
    n = history_len(page)
    act(page, lambda: page.click('#rigging-tool-picker [data-tool="auto"]'))
    done = layer(page, wid)
    assert 'handJoints' not in done['riggingCurve'] and done.get('riggingCustom') is False
    own = solve(page, wid)
    assert own['hand'] is False and joints_of(done) == own['joints']
    assert history_len(page) == n + 1
    assert page.locator('#rigging-curve-sheet [data-hand-angle]').count() == 0
    assert page.errors == []


def test_a_bend_under_a_bar_is_refused_either_way(page):
    ids = curved_singles(page)
    wid = ids[0]
    tool(page, 'custom')
    assert lay_bars(page, wid, 2, 0, 1) is True
    lay = layer(page, wid)
    n = history_len(page)
    # a joint under the double, set to bend: refused, nothing changed
    assert page.evaluate("() => window.app.setRiggingCurveJoint(0, 5)") is False
    assert toast_says(page, 'holds it straight')
    assert layer(page, wid) == lay and history_len(page) == n
    # an angle the panel does not lock at: refused
    assert page.evaluate("() => window.app.setRiggingCurveJoint(4, 6)") is False
    assert toast_says(page, 'does not lock at')
    assert history_len(page) == n
    # flat under the bar is fine
    act(page, lambda: page.evaluate("() => window.app.setRiggingCurveJoint(0, 0)"))
    assert layer(page, wid)['riggingCurve']['handJoints'] == {'0': 0}
    # a joint set by hand to bend, then a bar laid across it: refused
    act(page, lambda: page.evaluate("() => window.app.setRiggingCurveJoint(4, 5)"))
    lay = layer(page, wid)
    n = history_len(page)
    assert lay_bars(page, wid, 2, 4, 4) is False
    assert toast_says(page, 'set by hand to 5')
    assert layer(page, wid) == lay and history_len(page) == n
    assert page.errors == []


def test_remove_bar_on_a_curved_row_takes_it_off_and_the_angles_follow(page):
    ids = curved_singles(page)
    wid = ids[0]
    tool(page, 'custom')
    assert lay_bars(page, wid, 2, 2, 3) is True
    was = placed(layer(page, wid))
    n = history_len(page)
    page.evaluate("(id) => window.app.pickRiggingBar({ layerId: id, row: 'header', start: 2, span: 2 })", wid)
    assert page.evaluate('window.app.removePickedRiggingBar()') is True
    idle(page)
    lay = layer(page, wid)
    # the bar is gone and the rest stand where they stood, a gap left
    assert placed(lay) == [b for b in was if b != [2, 2]], (placed(lay), was)
    want = solve(page, wid)
    assert want['starts'] == [s for s, _ in placed(lay)]
    assert want['joints'] == joints_of(lay)
    assert history_len(page) == n + 1
    assert page.errors == []


def test_curve_on_over_bars_laid_by_hand_lays_its_own(page):
    ids = reset(page)
    wid = ids[0]
    open_rigging(page)
    singles_only(page)
    tool(page, 'custom')
    assert lay_bars(page, wid, 2, 0, 3) is True
    assert layer(page, wid)['riggingCustom'] is True
    act(page, lambda: page.check('#rigging-curve-on'))
    lay = layer(page, wid)
    assert lay['riggingCustom'] is False
    own = solve(page, wid)
    assert own['hand'] is False and [n for _, n in placed(lay)] == own['bars']
    assert page.errors == []


# ── a grouped wall ───────────────────────────────────────────────────────

def test_a_group_takes_custom_as_one_wall(page):
    ids = reset(page, three())
    group_two(page, ids)
    open_rigging(page)
    select(page, [ids[1]])
    singles_only(page)
    act(page, lambda: page.check('#rigging-curve-on'))
    tool(page, 'custom')
    n = history_len(page)
    # a double across the seam between the first two screens
    assert lay_bars(page, ids[0], 2, 3, 3) is True
    lays = [layer(page, i) for i in ids]
    assert [3, 2] in placed(lays[0])
    assert all(l['riggingCustom'] is True and l['riggingCurve']['on'] for l in lays)
    pts = joined(wall_edges(page, ids))
    got = turns(pts)
    assert abs(got[3]) < 1e-3, got
    assert history_len(page) == n + 1
    # the seam between the second and third screens set by hand
    select(page, [ids[1]])
    pick_joint(page, 7, '10')
    lays = [layer(page, i) for i in ids]
    assert all(l['riggingCurve'].get('handJoints') == {'7': 10} for l in lays), [l['riggingCurve'] for l in lays]
    got = turns(joined(wall_edges(page, ids)))
    assert abs(got[7] - 10) < 1e-3, got
    # each member's own joints are its part of the answer
    want = page.evaluate("(id) => window.app.riggingCurveSolve(window.app.project.layers.find(x => x.id === id)).joints", ids[0])
    for k, l in enumerate(lays):
        assert own_joints(l) == want[k * 4:k * 4 + 3], (k, own_joints(l))
    # the pull list counts every bar once
    rows = page.evaluate(f"""() => {ids}.flatMap(id => window.app.riggingPullRows(
        window.app.project.layers.find(l => l.id === id)))""")
    assert sum(r['qty'] for r in rows) == sum(len(placed(l)) for l in lays)
    assert page.errors == []


# ── Curve off gives back the bars laid by hand ───────────────────────────
#
# Owner's ruling (2026-11-18): Curve on over a wall laid by hand lays the
# Curve's own bars, as ever; Curve off puts the wall back to the bars it had
# laid by hand before the Curve went on. They save with the show, survive a
# reload and follow undo and redo; Auto or a lit size while curved keeps
# them; Clear forgets them. A wall on Auto before still gets Auto's bars.

def tool_mode_auto(page):
    """Back to Auto as a way of working only: picked with nothing selected,
    so nothing is laid; then the selection as it was."""
    page.evaluate("""() => { const a = window.app; window.__sel = [...a.selectedLayerIds];
        a.setSelectedLayersByIds([], null); a.refreshRiggingPanel(); }""")
    page.click('#rigging-tool-picker [data-tool="auto"]')
    page.evaluate("""() => { const a = window.app; a.setSelectedLayersByIds(window.__sel, window.__sel[0]);
        a.refreshRiggingPanel(); }""")


def hand_laid(page, specs=None):
    """A wall with bars laid by hand on its plain header, Curve off: a run
    of doubles over panels 1 to 4, the rest Auto's singles."""
    ids = reset(page) if specs is None else reset(page, specs)
    open_rigging(page)
    singles_only(page)
    act(page, lambda: page.click('#rigging-tool-picker [data-tool="auto"]'))
    tool(page, 'custom')
    assert lay_bars(page, ids[0], 2, 0, 3) is True
    tool_mode_auto(page)
    return ids


def laid_as_solved(page, layer_id):
    """The screen carries exactly the Curve's own answer, not one laid by hand."""
    return page.evaluate("""(id) => { const a = window.app; const l = a.project.layers.find(x => x.id === id);
        const out = a.riggingCurveSolve(l); return !out.hand && !out.errors.length && a._curveLaidMatches(l, out); }""", layer_id)


def test_curve_off_gives_back_the_bars_laid_by_hand_one_step_each_way(page):
    ids = hand_laid(page)
    wid = ids[0]
    mine = layer(page, wid)
    hand = placed(mine)
    assert mine['riggingCustom'] is True and hand[:2] == [[0, 2], [2, 2]]
    n = history_len(page)
    act(page, lambda: page.check('#rigging-curve-on'))
    on = layer(page, wid)
    assert on['riggingCurve']['on'] and on['riggingCustom'] is False
    assert placed(on) != hand and laid_as_solved(page, wid)
    assert on['riggingCustomSaved']['bars'] == [b for _, b in hand]
    assert history_len(page) == n + 1
    act(page, lambda: page.uncheck('#rigging-curve-on'))
    off = layer(page, wid)
    assert placed(off) == hand and off['riggingCustom'] is True
    assert not off.get('riggingCustomSaved')
    assert not any(joints_of(off))
    assert history_len(page) == n + 2
    # undo: curved again, its bars and the kept ones; undo again: as laid
    page.evaluate('window.app.undo()')
    back = settled(page, lambda: layer(page, wid), lambda l: (l.get('riggingCurve') or {}).get('on'))
    assert placed(back) == placed(on) and back['riggingCustomSaved'] == on['riggingCustomSaved']
    page.evaluate('window.app.undo()')
    first = settled(page, lambda: layer(page, wid), lambda l: not (l.get('riggingCurve') or {}).get('on'))
    assert placed(first) == hand and first['riggingCustom'] is True
    page.evaluate('window.app.redo()')
    settled(page, lambda: layer(page, wid), lambda l: (l.get('riggingCurve') or {}).get('on'))
    page.evaluate('window.app.redo()')
    again = settled(page, lambda: layer(page, wid), lambda l: not (l.get('riggingCurve') or {}).get('on'))
    assert placed(again) == hand and not again.get('riggingCustomSaved')
    assert page.errors == []


def test_the_kept_bars_survive_a_reload_auto_and_a_lit_size(page):
    ids = hand_laid(page)
    wid = ids[0]
    hand = placed(layer(page, wid))
    act(page, lambda: page.check('#rigging-curve-on'))
    kept = layer(page, wid)['riggingCustomSaved']
    settled(page, lambda: served(page, wid), lambda l: l.get('riggingCustomSaved') == kept)
    page.reload(wait_until='domcontentloaded')
    page.wait_for_timeout(2000)
    page.evaluate("(id) => { window.app.selectLayer(window.app.project.layers.find(l => l.id === id)); window.app.updateUI(); }", wid)
    open_rigging(page)
    idle(page)
    assert layer(page, wid)['riggingCustomSaved'] == kept
    # Auto, and a lit size, lay the Curve again and keep them
    act(page, lambda: page.click('#rigging-tool-picker [data-tool="auto"]'))
    page.click('#rigging-size-picker .rigging-size-btn[data-size="2"]')
    idle(page)
    assert layer(page, wid)['riggingCustomSaved'] == kept
    act(page, lambda: page.uncheck('#rigging-curve-on'))
    assert placed(layer(page, wid)) == hand
    assert page.errors == []


def test_clear_forgets_the_kept_bars_and_a_later_curve_off_lays_auto(page):
    ids = hand_laid(page)
    wid = ids[0]
    act(page, lambda: page.check('#rigging-curve-on'))
    assert layer(page, wid)['riggingCustomSaved']
    page.click('#rigging-clear-btn')
    cleared = settled(page, lambda: layer(page, wid), lambda l: not l.get('riggingBars'))
    assert not cleared.get('riggingCustomSaved') and not cleared['riggingCurve']['on']
    act(page, lambda: page.check('#rigging-curve-on'))
    act(page, lambda: page.uncheck('#rigging-curve-on'))
    assert layer(page, wid)['riggingBars'] == [1] * 16
    assert page.errors == []


def test_a_wall_on_auto_keeps_nothing_and_gets_auto_bars_back(page):
    ids = reset(page)
    wid = ids[0]
    open_rigging(page)
    light(page, [1, 2])
    act(page, lambda: page.click('#rigging-tool-picker [data-tool="auto"]'))
    auto = placed(layer(page, wid))
    act(page, lambda: page.check('#rigging-curve-on'))
    assert not layer(page, wid).get('riggingCustomSaved')
    act(page, lambda: page.uncheck('#rigging-curve-on'))
    off = layer(page, wid)
    assert placed(off) == auto and off['riggingCustom'] is False
    assert page.errors == []


def test_edits_after_curve_off_are_what_the_next_curve_keeps(page):
    ids = hand_laid(page)
    wid = ids[0]
    act(page, lambda: page.check('#rigging-curve-on'))
    act(page, lambda: page.uncheck('#rigging-curve-on'))
    tool(page, 'custom')
    assert lay_bars(page, wid, 2, 6, 9) is True
    tool_mode_auto(page)
    edited = placed(layer(page, wid))
    assert [6, 2] in edited and [8, 2] in edited
    act(page, lambda: page.check('#rigging-curve-on'))
    act(page, lambda: page.uncheck('#rigging-curve-on'))
    assert placed(layer(page, wid)) == edited
    assert page.errors == []


def test_a_group_laid_by_hand_gets_each_screens_bars_back(page):
    ids = reset(page, three())
    group_two(page, ids)
    open_rigging(page)
    select(page, [ids[1]])
    singles_only(page)
    act(page, lambda: page.click('#rigging-tool-picker [data-tool="auto"]'))
    tool(page, 'custom')
    # a double across the seam between the first two screens
    assert lay_bars(page, ids[0], 2, 3, 3) is True
    tool_mode_auto(page)
    hand = [placed(layer(page, i)) for i in ids]
    assert [3, 2] in hand[0]
    act(page, lambda: page.check('#rigging-curve-on'))
    assert all(layer(page, i)['riggingCustomSaved'] for i in ids)
    act(page, lambda: page.uncheck('#rigging-curve-on'))
    assert [placed(layer(page, i)) for i in ids] == hand
    assert all(layer(page, i)['riggingCustom'] is True for i in ids)
    assert page.errors == []


def test_a_corner_on_a_curve_laid_by_hand_lays_the_full_curve_again(page):
    """Owner's ruling (2026-11-18): adding or taking off a corner on a
    curved wall laid by hand makes it a full Curve again."""
    ids = curved_singles(page)
    wid = ids[0]
    tool(page, 'custom')
    assert lay_bars(page, wid, 2, 0, 1) is True
    act(page, lambda: page.evaluate("() => window.app.setRiggingCurveJoint(4, 5)"))
    lay = layer(page, wid)
    assert lay['riggingCustom'] is True and lay['riggingCurve']['handJoints'] == {'4': 5}
    act(page, lambda: page.click('#rigging-corner-add'))
    added = layer(page, wid)
    assert len(added.get('riggingCorners') or []) == 1
    assert added['riggingCustom'] is False and 'handJoints' not in added['riggingCurve']
    assert laid_as_solved(page, wid)
    # laid by hand again, then the corner taken off: the full Curve again too
    assert lay_bars(page, wid, 2, 0, 1) is True
    assert layer(page, wid)['riggingCustom'] is True
    act(page, lambda: page.click('#rigging-corner-list [data-corner-remove]'))
    gone = layer(page, wid)
    assert not (gone.get('riggingCorners') or [])
    assert gone['riggingCustom'] is False and laid_as_solved(page, wid)
    assert page.errors == []
