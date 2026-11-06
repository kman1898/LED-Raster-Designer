"""Hiding a screen never re-plans a locked one, and the Balance dialog's
hidden wording, after the round 8 audit (the owner's rulings,
2026-10-23).

1. Hiding or showing a screen is REFUSED when it would change a LOCKED
   screen's circuits (a group wall re-planned without the hidden member):
   the locked screen is named, nothing changes and no history entry is
   made. A hide that changes nothing locked still works, on a fully
   locked or half-locked group too. The screen eye and the group eye.
4. The Balance dialog: a shared box only hidden screens fill says "WALL A
   and WALL B are hidden".

The crowding words (items 2, 3, 5 and 6) are test_r8_crowding.py's.

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_r8_power_rulings.py -v --browser chromium
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_nfer_custom_rulings import (  # noqa: E402,F401 - fixtures
    _guard, page, landed, make, history,
)
from test_power_rulings_1021 import errors  # noqa: E402
from test_power_region_rulings import _distro, set_distros  # noqa: E402
from test_r5_power_rulings import pinned  # noqa: E402
from test_r7_power_rulings import three, layers_of, dialog_text  # noqa: E402

# ── 1. hiding never re-plans a locked screen ─────────────────────────────

PLAN_JS = """(ids) => { const app = window.app; app._circuitTailCache = null;
    return ids.map(id => { const l = window.__nf.layer(id);
        return [app.getSocaPlan(l).map(s => [s.number, s.name, s.legs.map(g => g.label)]),
                app.circuitCapacity(l).pct]; }); }"""
VISIBLE_JS = "(ids) => ids.map(id => window.__nf.layer(id).visible !== false)"
HIDE_JS = "([id]) => window.app.toggleLayerVisibility(id)"


def plans(page, ids):
    return page.evaluate(PLAN_JS, ids)


def apart(page, a_locked):
    """three(), with B's cabinets drawing other watts, so A and B each walk
    their own circuits and hiding one changes nothing on the other."""
    return three(page, a_locked=a_locked, b_watts=100)


def assert_refused(page, ids, before, h0, names):
    landed(page)
    assert errors(page)['locked'] == [names], errors(page)
    assert layers_of(page, ids) == before, 'a screen changed'
    assert len(history(page)) == h0, history(page)


@pytest.mark.parametrize('a_locked', [False, True], ids=['half locked', 'locked as one'])
def test_hiding_a_member_that_would_re_plan_the_locked_member_is_refused(page, a_locked):
    """A and B one wall: hiding A would give B a multi of its own (SR3 with
    two circuits). Refused, B named, nothing changes, no history entry."""
    a, b, c = three(page, a_locked=a_locked)
    p0 = plans(page, [a, b, c])
    assert p0[1][0] == [], 'B rides the wall and has no multi of its own'
    before, h0 = layers_of(page, [a, b, c]), len(history(page))
    page.evaluate(HIDE_JS, [a])
    assert_refused(page, [a, b, c], before, h0, ['B'])
    assert page.evaluate(VISIBLE_JS, [a, b, c]) == [True, True, True]
    assert plans(page, [a, b, c]) == p0


def test_the_refusal_says_the_hide_would_repack_the_locked_screen(page):
    a, b, c = three(page)
    # the real error, not three()'s recorder
    page.evaluate("""() => { const app = window.app; window.__r8 = [];
        delete app._showLockedError; delete app._toast;
        app._toast = (m, err) => { if (err) window.__r8.push(m); }; }""")
    page.evaluate(HIDE_JS, [a])
    landed(page)
    assert page.evaluate("() => window.__r8") == [
        'B is locked, and this would repack its circuits. Unlock it to change it.']


def test_hiding_the_locked_member_that_would_re_plan_its_wall_is_refused(page):
    """Locked as one: hiding B re-plans A, which is locked too."""
    a, b, c = three(page, a_locked=True)
    before, h0 = layers_of(page, [a, b, c]), len(history(page))
    page.evaluate(HIDE_JS, [b])
    assert_refused(page, [a, b, c], before, h0, ['A'])
    assert page.evaluate(VISIBLE_JS, [a, b]) == [True, True]


def test_showing_a_member_that_would_re_plan_the_locked_member_is_refused(page):
    """A file saved with A hidden: B has its own multi. Showing A would
    fold B back into the wall, so it is refused too."""
    a, b, c = three(page)
    page.evaluate("""async ([a]) => { const app = window.app;
        window.__nf.layer(a).visible = false;
        await window.__nf.j('PUT', '/api/project', app.project);
        app.project = await window.__nf.j('GET', '/api/project');
        app.dedupeProjectLayers('r8'); app._circuitTailCache = null;
        app.resetHistory('Initial State'); }""", [a])
    landed(page)
    p0 = plans(page, [b])
    assert p0[0][0], 'hidden A leaves B a multi of its own'
    before, h0 = layers_of(page, [a, b, c]), len(history(page))
    page.evaluate(HIDE_JS, [a])
    assert_refused(page, [a, b, c], before, h0, ['B'])
    assert page.evaluate(VISIBLE_JS, [a, b]) == [False, True]
    assert plans(page, [b]) == p0


@pytest.mark.parametrize('a_locked', [False, True], ids=['half locked', 'locked as one'])
def test_the_group_eye_hides_and_shows_the_whole_locked_wall(page, a_locked):
    """The group's eye takes every member: no locked screen outside it is
    re-planned, so it hides and shows, one history entry each."""
    a, b, c = three(page, a_locked=a_locked)
    p0 = plans(page, [a, b, c])
    h0 = len(history(page))
    assert page.evaluate("() => window.app.toggleGroupVisibility('gH')") is True
    landed(page)
    assert page.evaluate(VISIBLE_JS, [a, b, c]) == [False, False, True]
    assert page.evaluate("() => window.app.toggleGroupVisibility('gH')") is True
    landed(page)
    assert page.evaluate(VISIBLE_JS, [a, b, c]) == [True, True, True]
    assert errors(page)['locked'] == [], errors(page)
    assert history(page)[h0:] == ['Hide Group', 'Show Group'], history(page)
    assert plans(page, [a, b, c]) == p0


@pytest.mark.parametrize('a_locked', [False, True], ids=['half locked', 'locked as one'])
def test_a_hide_that_changes_nothing_locked_still_works(page, a_locked):
    """A and B walk their own circuits: hiding either member changes nothing
    on the other, so the screen eye hides and shows on a locked or a
    half-locked group, and the lock flags stay the file's."""
    a, b, c = apart(page, a_locked)
    p0 = plans(page, [a, b, c])
    h0 = len(history(page))
    for who in (a, b):
        page.evaluate(HIDE_JS, [who])
        landed(page)
        assert page.evaluate(VISIBLE_JS, [who]) == [False]
        page.evaluate(HIDE_JS, [who])
        landed(page)
        assert page.evaluate(VISIBLE_JS, [who]) == [True]
    assert errors(page)['locked'] == [], errors(page)
    assert history(page)[h0:] == ['Hide Layer', 'Show Layer'] * 2, history(page)
    assert plans(page, [a, b, c]) == p0
    assert page.evaluate("(ids) => ids.map(id => !!window.__nf.layer(id).locked)", [a, b]) \
        == [a_locked, True]
    # an edit on A is still refused when its group holds it
    page.evaluate("([a]) => window.app.mergeSplitterCircuits(window.__nf.layer(a), [1, 2])", [a])
    landed(page)
    assert errors(page)['locked'] == [['A' if a_locked else 'B']], errors(page)


def test_an_unlocked_screen_and_a_lone_locked_screen_hide_freely(page):
    """C is in no group and unlocked; a lone locked screen's own eye works
    as before (round 7)."""
    a, b, c = three(page)
    h0 = len(history(page))
    page.evaluate(HIDE_JS, [c])
    landed(page)
    page.evaluate("([c]) => { window.__nf.layer(c).locked = true; }", [c])
    page.evaluate(HIDE_JS, [c])
    landed(page)
    assert page.evaluate(VISIBLE_JS, [c]) == [True]
    assert errors(page)['locked'] == [], errors(page)
    assert history(page)[h0:] == ['Hide Layer', 'Show Layer'], history(page)


# ── 4. the Balance dialog: a shared box only hidden screens fill ─────────

def test_a_shared_box_only_hidden_screens_fill_says_they_are_hidden(page):
    a, b, c = make(page, [{'name': 'WALL A', 'columns': 2, 'props': pinned(2)},
                          {'name': 'WALL B', 'columns': 2, 'x': 800, 'props': pinned(2)},
                          {'name': 'C', 'columns': 2, 'x': 1600, 'props': pinned(2)}])
    set_distros(page, [_distro('sr', 'SR')], {a: {1: 'sr'}, b: {1: 'sr'}, c: {1: 'sr'}})
    page.evaluate("""([a, b]) => { const L = (id) => window.__nf.layer(id);
        L(a).powerSocaNumber = { 1: 1 }; L(b).powerSocaNumber = { 1: 1 };
        L(a).visible = false; L(b).visible = false;
        window.app._circuitTailCache = null; }""", [a, b])
    r = page.evaluate("() => { window.app._circuitTailCache = null;"
                      " return window.app.suggestPhaseBalance('sr'); }")
    assert [x['layers'] for x in r['hidden']] == [['WALL A', 'WALL B']], r['hidden']
    text = dialog_text(page, 'sr')
    assert re.search(r'\(WALL A \+ WALL B\) stays where it is\. WALL A and WALL B are hidden\.', text), text
    assert 'WALL B is hidden' not in text, text
