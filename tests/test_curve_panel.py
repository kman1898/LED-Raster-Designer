"""The Header/Footer tab's Curve panel as it reads (app-curve.js), in the
real app.

The owner picked "Ask in order" (2026-11-24): off, the Curve is only its
switch; on, it asks three plain questions in order (Concave or Convex,
how much, where the build starts), then gives the answer as an
instruction to the crew, with the other builds, the lock positions, the
fit rule and Close enough under More.

What this file pins:

* Curve off shows only the switch. A panel with no lock positions shows
  the reason and its lock positions under the switch, so they can be set.
* Curve on shows the three questions and the answer card; More is shut
  and holds Ways to build it, the lock positions, the fit rule and Close
  enough.
* One box, its unit from a list: switching the unit says the same curve
  the other way and the wall does not change; the line under the box says
  the same curve in the other two units; a typed radius lays the same wall
  as the % it stands for.
* The selected button of every Curve button row lights up like the app's
  other button rows (it used to stay grey).
* The answer reads as an instruction: "Lock 9 joints at 7.5°, 6 stay flat".
* A joint set by hand: "1 joint set by you (blue)", the joint's own App
  sets it, and Undo mine hands it back in one undo step.
* A group says it curves as one wall across its screens.
* Ways to build it marks exactly one build "in use" after a joint is set
  by hand (it marked two).

Set LRD_CURVE_SHOTS to a folder to save the panel in the four states of
the owner's mockup (off, on, by hand with More open, a group).

Run locally:
    python -m pytest tests/test_curve_panel.py -n 4 --dist loadfile
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from conftest import settled  # noqa: E402
from test_curve_obj import (  # noqa: E402
    act, group_two, history_len, idle, layer, open_rigging, reset, singles_only,
)


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project as this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1500, 'height': 1100})
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


SHOTS = os.environ.get('LRD_CURVE_SHOTS')


def shot(page, name):
    """The Header/Footer Bars panel, saved when LRD_CURVE_SHOTS is set."""
    if not SHOTS:
        return
    os.makedirs(SHOTS, exist_ok=True)
    size = page.viewport_size
    # tall enough that the side panel shows whole, not scrolled
    page.set_viewport_size({'width': size['width'], 'height': 2400})
    page.wait_for_timeout(400)
    panel = page.locator('#rigging-curve').locator('xpath=ancestor::div[contains(concat(" ", @class, " "), " panel ")][1]')
    panel.screenshot(path=os.path.join(SHOTS, f'{name}.png'))
    page.set_viewport_size(size)
    page.wait_for_timeout(200)


def visible(page, sel):
    return page.is_visible(sel)


def curved(page):
    """The test wall, singles lit, the Curve on."""
    ids = reset(page)
    open_rigging(page)
    singles_only(page)
    act(page, lambda: page.check('#rigging-curve-on'))
    return ids


def more(page, open_it=True):
    page.evaluate("(o) => { const d = document.getElementById('rigging-curve-more'); if (d.open !== o) d.querySelector('summary').click(); }", open_it)
    page.wait_for_timeout(100)


# ── off: only the switch ─────────────────────────────────────────────────

def test_curve_off_shows_only_the_switch(page):
    reset(page)
    open_rigging(page)
    assert visible(page, '#rigging-curve-switch')
    assert page.inner_text('#rigging-curve-switch').strip() == 'Curve this wall'
    assert not page.is_checked('#rigging-curve-on')
    assert not visible(page, '#rigging-curve-fields')
    assert not visible(page, '#rigging-curve-note')
    assert not visible(page, '#rigging-curve-locks')
    # nothing of the Curve but its switch takes room
    kids = page.evaluate("""() => [...document.getElementById('rigging-curve').children]
        .filter(e => e.offsetHeight > 0).map(e => e.id)""")
    assert kids == ['rigging-curve-switch'], kids
    shot(page, '1_curve_off')
    assert page.errors == []


def test_a_panel_with_no_lock_positions_shows_them_under_the_switch(page):
    ids = reset(page, locks=None)
    open_rigging(page)
    assert page.is_disabled('#rigging-curve-on')
    assert 'no curve lock positions' in page.inner_text('#rigging-curve-note')
    assert visible(page, '#rigging-curve-locks-off #rigging-curve-locks')
    assert not visible(page, '#rigging-curve-fields')
    # set them there, and the switch can go on; the row stays where they
    # were set (nothing vanishes under the crew) and the reason goes
    page.click('#rigging-curve-lock-edit')
    page.fill('#rigging-curve-lock-input', '-5, 5')
    page.click('#rigging-curve-lock-save')
    idle(page)
    assert not page.is_disabled('#rigging-curve-on')
    assert not visible(page, '#rigging-curve-note')
    assert visible(page, '#rigging-curve-locks-off #rigging-curve-locks')
    assert page.inner_text('#rigging-curve-lock-source') == 'Set by you'
    # on, the row goes under More with the rest
    act(page, lambda: page.check('#rigging-curve-on'))
    assert layer(page, ids[0])['riggingCurve']['on'] is True
    assert page.evaluate("document.querySelector('#rigging-curve-more #rigging-curve-locks') !== null")
    assert not visible(page, '#rigging-curve-locks')
    # off again, only the switch: the panel has its positions now
    act(page, lambda: page.uncheck('#rigging-curve-on'))
    assert not visible(page, '#rigging-curve-locks')
    assert page.errors == []


# ── on: three questions, the answer, More ────────────────────────────────

def test_curve_on_asks_three_questions_and_more_holds_the_rest(page):
    curved(page)
    assert visible(page, '#rigging-curve-fields')
    qs = page.evaluate("[...document.querySelectorAll('#rigging-curve-fields > .rigging-curve-q')].map(e => e.textContent)")
    assert qs == ['Which way does it bend?', 'How much?', 'Where does the build start?'], qs
    assert [t.strip() for t in page.locator('#rigging-curve-bend button').all_inner_texts()] == ['Concave', 'Convex']
    assert page.locator('#rigging-curve-bend svg').count() == 2
    assert visible(page, '#rigging-curve-value') and visible(page, '#rigging-curve-unit')
    assert page.locator('#rigging-curve-unit option').all_inner_texts() == ['degrees of arc', '% of a circle', 'radius, ft']
    assert page.locator('#rigging-curve-from button').all_inner_texts() == ['Left end', 'Center', 'Right end']
    assert visible(page, '#rigging-curve-result')
    # the answer as an instruction
    assert page.inner_text('#rigging-curve-head') == 'Lock 9 joints at 7.5°, 6 stay flat'
    keys = page.evaluate("[...document.querySelectorAll('#rigging-curve-readouts > div')].map(r => r.children[0].textContent)")
    assert keys == ['Builds', 'Radius', 'Width, depth', 'Off the drawing'], keys
    assert 'Click a joint on the strip' in page.inner_text('#rigging-curve-hint')
    # More is shut and holds the rest
    assert not page.evaluate("document.getElementById('rigging-curve-more').open")
    assert page.inner_text('#rigging-curve-more-title') == 'More: other builds, lock positions, fit'
    for sel in ('#rigging-curve-ways', '#rigging-curve-locks', '#rigging-curve-goal', '#rigging-curve-tol'):
        assert page.evaluate(f"!!document.querySelector('#rigging-curve-more {sel}')"), sel
        assert not visible(page, sel), sel
    shot(page, '2_curve_on')
    more(page)
    assert page.inner_text('#rigging-curve-more-title') == 'More'
    for sel in ('#rigging-curve-ways', '#rigging-curve-locks', '#rigging-curve-goal', '#rigging-curve-tol'):
        assert visible(page, sel), sel
    assert page.locator('#rigging-curve-goal button').all_inner_texts() == ['Fewest angles', 'Same spacing', 'Closest']
    # the positions the curve bends to are ringed
    on = page.evaluate("[...document.querySelectorAll('#rigging-curve-lock-chips .rigging-curve-lock.on')].map(c => c.dataset.lock)")
    assert on == ['2.5', '5', '7.5', '10'], on
    more(page, False)
    assert page.errors == []


def test_the_selected_button_lights_up_in_every_curve_row(page):
    curved(page)
    more(page)
    page.click('#rigging-curve-from [data-value="left"]')
    idle(page)
    got = page.evaluate("""() => {
        const look = (b) => { const c = getComputedStyle(b); return c.backgroundImage + '|' + c.color; };
        const lit = document.querySelector('#rigging-mode-picker .rigging-mode-btn.active');
        return ['#rigging-curve-bend', '#rigging-curve-goal', '#rigging-curve-from'].map(sel => {
            const on = document.querySelector(sel + ' .rigging-curve-btn.active');
            const off = document.querySelector(sel + ' .rigging-curve-btn:not(.active)');
            return { sel, active: !!on, on: on && look(on), off: off && look(off), app: look(lit) };
        });
    }""")
    for row in got:
        assert row['active'], row
        assert row['on'] != row['off'], row
        # lit the way the app's other rows light (the Header/Footer picker)
        assert row['on'] == row['app'], row
    more(page, False)
    assert page.errors == []


# ── how much: one box, three units, in step ──────────────────────────────

def test_the_units_stay_in_step_and_the_wall_does_not_change(page):
    """On a feet and inches show (the test show's unit): a radius reads as a
    tape does, in the box and in the line under it."""
    ids = curved(page)
    wid = ids[0]
    joints = layer(page, wid)['stage3d']['jointsCol']
    assert page.input_value('#rigging-curve-unit') == 'percent'
    assert page.input_value('#rigging-curve-value') == '20'
    same = page.inner_text('#rigging-curve-same')
    # sixteen 500 mm panels at 72 degrees: a 6.363 m face radius
    assert same == 'Same as 72 degrees of arc, or a 20\' 10 1/2" radius', same
    # degrees of arc: the same curve the other way, the wall as it was
    act(page, lambda: page.select_option('#rigging-curve-unit', 'degrees'))
    assert page.input_value('#rigging-curve-value') == '72'
    assert page.inner_text('#rigging-curve-same') == 'Same as 20% of a circle, or a 20\' 10 1/2" radius'
    assert layer(page, wid)['stage3d']['jointsCol'] == joints
    # the radius: the box says it, the line says the other two
    act(page, lambda: page.select_option('#rigging-curve-unit', 'radius'))
    assert page.input_value('#rigging-curve-value') == '20\' 10 1/2"'
    assert page.inner_text('#rigging-curve-same') == 'Same as 72 degrees of arc, or 20% of a circle'
    lay = layer(page, wid)
    assert lay['stage3d']['jointsCol'] == joints
    assert lay['riggingCurve']['entry'] == 'radius' and abs(lay['riggingCurve']['value'] - 6.3629) < 0.0005
    # a radius typed lays the wall it stands for: a wider radius, a gentler wall
    act(page, lambda: (page.fill('#rigging-curve-value', '40'), page.press('#rigging-curve-value', 'Enter')))
    lay = layer(page, wid)
    assert abs(lay['riggingCurve']['value'] - 40 * 0.3048) < 1e-6
    assert page.input_value('#rigging-curve-value') == '40\' 0"'
    pct = float(page.inner_text('#rigging-curve-same').split('or ')[1].split('%')[0])
    assert 9 < pct < 12, pct
    assert sum(abs(a) for a in lay['stage3d']['jointsCol'].values()) < sum(abs(a) for a in joints.values())
    # feet and inches typed as a tape reads
    act(page, lambda: (page.fill('#rigging-curve-value', '30\' 6 1/2"'), page.press('#rigging-curve-value', 'Enter')))
    assert abs(layer(page, wid)['riggingCurve']['value'] - (30 * 12 + 6.5) * 0.0254) < 1e-6
    # and back to % keeps the wall again
    now = layer(page, wid)['stage3d']['jointsCol']
    act(page, lambda: page.select_option('#rigging-curve-unit', 'percent'))
    assert layer(page, wid)['stage3d']['jointsCol'] == now
    # a radius of 0, or words, is refused and the curve stays
    act(page, lambda: page.select_option('#rigging-curve-unit', 'radius'))
    kept = layer(page, wid)['riggingCurve']['value']
    for typed in ('0', 'wide'):
        act(page, lambda t=typed: (page.fill('#rigging-curve-value', t), page.press('#rigging-curve-value', 'Enter')))
        assert layer(page, wid)['riggingCurve']['value'] == kept
    # on a meter show the radius is in meters
    unit = page.evaluate("window.app.project.cableUnit || null")
    page.evaluate("() => { window.app.project.cableUnit = 'm'; window.app.refreshRiggingPanel(); }")
    try:
        assert page.locator('#rigging-curve-unit option[value="radius"]').inner_text() == 'radius, m'
        act(page, lambda: page.select_option('#rigging-curve-unit', 'percent'))
        act(page, lambda: (page.fill('#rigging-curve-value', '20'), page.press('#rigging-curve-value', 'Enter')))
        assert page.inner_text('#rigging-curve-same') == 'Same as 72 degrees of arc, or a 6.36 m radius'
        act(page, lambda: page.select_option('#rigging-curve-unit', 'radius'))
        assert page.input_value('#rigging-curve-value') == '6.36'
        assert layer(page, wid)['stage3d']['jointsCol'] == joints
    finally:
        page.evaluate("(u) => { window.app.project.cableUnit = u; window.app.refreshRiggingPanel(); }", unit)
    assert page.errors == []


# ── by hand ──────────────────────────────────────────────────────────────

def pick_joint(page, j, value):
    page.locator(f'#rigging-curve-sheet rect[data-joint="{j}"]').click()
    page.wait_for_selector('#rigging-curve-joint [data-joint-angle]')
    act(page, lambda: page.locator(f'#rigging-curve-joint [data-joint-angle="{value}"]').click())


def test_a_joint_set_by_hand_is_counted_and_undo_mine_hands_it_back(page):
    ids = reset(page, locks=[-5, -2.5, 0, 2.5, 5])
    wid = ids[0]
    open_rigging(page)
    singles_only(page)
    act(page, lambda: page.check('#rigging-curve-on'))
    before = layer(page, wid)['stage3d']['jointsCol']
    assert not visible(page, '#rigging-curve-hand')
    page.locator('#rigging-curve-sheet rect[data-joint="3"]').click()
    page.wait_for_selector('#rigging-curve-joint [data-joint-angle]')
    assert page.inner_text('#rigging-curve-joint [data-joint-angle="auto"]') == 'App sets it'
    act(page, lambda: page.locator('#rigging-curve-joint [data-joint-angle="2.5"]').click())
    lay = layer(page, wid)
    assert lay['riggingCurve']['handJoints'] == {'3': 2.5}
    assert visible(page, '#rigging-curve-hand')
    assert page.inner_text('#rigging-curve-hand-count') == '1 joint set by you (blue)'
    more(page)
    shot(page, '3_by_hand_more_open')
    # exactly one build is in use (it said "in use" on two)
    tops = page.evaluate("[...document.querySelectorAll('#rigging-curve-ways [data-way]')].map(r => r.firstElementChild.firstElementChild.textContent)")
    assert sum(t.endswith(', in use') for t in tops) == 1, tops
    ids_ = page.evaluate("[...document.querySelectorAll('#rigging-curve-ways [data-way]')].map(r => r.dataset.way)")
    assert len(set(ids_)) == len(ids_), ids_
    # two builds of the same angles say how many joints take each, so no
    # two rows read alike
    assert len(set(tops)) == len(tops), tops
    assert any(' at ' in t for t in tops), tops
    more(page, False)
    n = history_len(page)
    act(page, lambda: page.click('#rigging-curve-undo-mine'))
    lay = layer(page, wid)
    assert 'handJoints' not in lay['riggingCurve']
    assert lay.get('riggingCustom') is False
    assert lay['stage3d']['jointsCol'] == before
    assert not visible(page, '#rigging-curve-hand')
    assert history_len(page) == n + 1
    # one undo brings the joint back
    act(page, lambda: page.evaluate('window.app.undo()'))
    assert layer(page, wid)['riggingCurve']['handJoints'] == {'3': 2.5}
    assert page.errors == []


# ── a group ──────────────────────────────────────────────────────────────

def test_a_group_says_it_curves_as_one_wall(page):
    ids = reset(page, [{'name': f'M{i + 1}', 'columns': 6, 'rows': 2, 'offset_x': i * 6 * 128, 'offset_y': 0}
                       for i in range(3)])
    group_two(page, ids)
    open_rigging(page)
    page.evaluate(f"window.app.setSelectedLayersByIds([{ids[1]}], {ids[1]}); window.app.refreshRiggingPanel();")
    singles_only(page)
    assert not visible(page, '#rigging-curve-group')
    act(page, lambda: page.check('#rigging-curve-on'))
    assert all(layer(page, i)['riggingCurve']['on'] for i in ids)
    assert page.inner_text('#rigging-curve-group') == 'Group 1 curves as one wall across its 3 screens. A change here sets all three.'
    shot(page, '4_group')
    # a question answered on one screen sets all three
    act(page, lambda: page.click('#rigging-curve-bend [data-value="convex"]'))
    assert all(layer(page, i)['riggingCurve']['bend'] == 'convex' for i in ids)
    assert settled(page, lambda: page.inner_text('#rigging-curve-head'), lambda t: t.startswith('Lock '))
    assert page.errors == []
