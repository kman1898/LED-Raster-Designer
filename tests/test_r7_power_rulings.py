"""Locks, the balancer and hidden screens after the round 7 audit (the
owner's rulings, 2026-10-23).

2. The Balance dialog's lock wording names the LOCKED screen: a multi on
   the unlocked member of a half-locked group stays where it is because
   its group's locked member holds it, and that member is named.
3. A mixed tray clear treats a half-locked group's unlocked member exactly
   as a locked member, as a group locked as one does: skipped, the locked
   screen named, and the other screens still clear. Both orders.
4. Half-locked groups ALLOW hide and show (visibility is not a change,
   same as fully locked screens): the screen eye and the group eye. Round
   8: unless the hide would re-plan a locked screen (test_r8_power_rulings).
5. The balancer leaves a hidden screen's multis out of the multis it
   searched: it never moves them, so they are held where they sit and
   said as such.

The walls are the nfer module's: 5 rows of cabinets on 208 V x 20 A, cabled
top-down, sharing pinned off (one circuit a column).

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_r7_power_rulings.py -v --browser chromium
"""

import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_nfer_custom_rulings import (  # noqa: E402,F401 - fixtures
    _guard, page, landed, make, history,
)
from test_power_rulings_1021 import errors_on, errors  # noqa: E402
from test_power_region_rulings import _distro, set_distros  # noqa: E402
from test_r5_power_rulings import wall, pinned  # noqa: E402
from test_lock_repack_rulings import state  # noqa: E402


def three(page, a_locked=False, b_locked=True, b_watts=None):
    """A and B one group (A unlocked and B locked: an old file's half-locked
    group, unless told), C in no group; each screen's one multi on SR.
    A and B walk the wall's circuits as one, unless `b_watts` gives B's
    cabinets other watts: then each walks its own."""
    b_props = dict(pinned(2), panelWatts=b_watts) if b_watts else pinned(2)
    a, b, c = make(page, [{'name': 'A', 'columns': 2, 'props': pinned(2)},
                          {'name': 'B', 'columns': 2, 'x': 800, 'props': b_props},
                          {'name': 'C', 'columns': 2, 'x': 1600, 'props': pinned(2)}])
    page.evaluate("""([a, b, c, al, bl]) => { const app = window.app, L = (id) => window.__nf.layer(id);
        app.project.groups = [{ id: 'gH', name: 'WALL', layer_ids: [a, b] }];
        L(a).group_id = 'gH'; L(b).group_id = 'gH';
        L(a).locked = al; L(b).locked = bl;
        app._circuitTailCache = null; }""", [a, b, c, a_locked, b_locked])
    set_distros(page, [_distro('sr', 'SR')], {a: {1: 'sr'}, b: {1: 'sr'}, c: {1: 'sr'}})
    # the server holds the same show, so a one-field layer save adopted
    # back never reads an older lock flag
    page.evaluate("""async () => { const app = window.app;
        await window.__nf.j('PUT', '/api/project', app.project);
        app.project = await window.__nf.j('GET', '/api/project');
        app.dedupeProjectLayers('r7'); app._circuitTailCache = null; }""")
    landed(page)
    errors_on(page)
    page.evaluate("() => window.app.resetHistory('Initial State')")
    return a, b, c


def layers_of(page, ids):
    return json.loads(state(page, ids))['layers']


def fed(layer):
    return (layer.get('powerSocaDistro') or {}).get('1')


# ── 3. the mixed tray clear ──────────────────────────────────────────────

CLEARS = {
    'held member first': lambda a, b, c: [a, c],
    'held member last': lambda a, b, c: [c, a],
    'locked member first': lambda a, b, c: [b, c],
    'locked member last': lambda a, b, c: [c, b],
}


@pytest.mark.parametrize('order', list(CLEARS))
def test_a_mixed_clear_skips_both_half_locked_members_alike(page, order):
    """A (held by B) and B (locked) are each skipped with B named; C, in
    no group, clears; one undo step."""
    a, b, c = three(page)
    ids = CLEARS[order](a, b, c)
    before, h0 = layers_of(page, [a, b, c]), len(history(page))
    page.evaluate("(ids) => window.app._clearMultis(ids.map(id => ({ layerId: id, soca: 1 })),"
                  " 'Unplug Multi')", ids)
    landed(page)
    assert errors(page)['locked'] == [['B']], (order, errors(page))
    after = layers_of(page, [a, b, c])
    assert after[0] == before[0] and after[1] == before[1], (order, 'A or B changed')
    assert fed(before[2]) == 'sr' and fed(after[2]) is None, (order, after[2])
    assert len(history(page)) == h0 + 1, (order, history(page))


def test_a_mixed_clear_on_a_group_locked_as_one_is_the_same_rule(page):
    """The reference: A and B both locked. A is skipped and named, C
    clears - the rule the half-locked group now follows."""
    a, b, c = three(page, a_locked=True)
    before = layers_of(page, [a, b, c])
    page.evaluate("(ids) => window.app._clearMultis(ids.map(id => ({ layerId: id, soca: 1 })),"
                  " 'Unplug Multi')", [a, c])
    landed(page)
    assert errors(page)['locked'] == [['A']], errors(page)
    after = layers_of(page, [a, b, c])
    assert after[0] == before[0] and fed(after[2]) is None, after


def test_a_clear_of_only_half_locked_members_changes_nothing(page):
    a, b, c = three(page)
    before, h0 = layers_of(page, [a, b, c]), len(history(page))
    page.evaluate("(ids) => window.app._clearMultis(ids.map(id => ({ layerId: id, soca: 1 })),"
                  " 'Unplug Multi')", [a, b])
    landed(page)
    assert errors(page)['locked'] == [['B']], errors(page)
    assert layers_of(page, [a, b, c]) == before
    assert len(history(page)) == h0


# ── 4. hide and show on a half-locked group ──────────────────────────────

VISIBLE_JS = "(ids) => ids.map(id => window.__nf.layer(id).visible !== false)"


def test_a_half_locked_group_hides_and_shows(page):
    # A and B walk their own circuits, so hiding one changes nothing on the
    # other (round 8: a hide that would re-plan a locked screen is
    # refused, test_r8_power_rulings.py)
    a, b, c = three(page, b_watts=100)
    page.evaluate("([a]) => window.app.toggleLayerVisibility(a)", [a])
    landed(page)
    assert page.evaluate(VISIBLE_JS, [a, b]) == [False, True]
    page.evaluate("([a]) => window.app.toggleLayerVisibility(a)", [a])
    landed(page)
    assert page.evaluate(VISIBLE_JS, [a, b]) == [True, True]
    # the locked member's own eye
    page.evaluate("([b]) => window.app.toggleLayerVisibility(b)", [b])
    landed(page)
    assert page.evaluate(VISIBLE_JS, [a, b]) == [True, False]
    page.evaluate("([b]) => window.app.toggleLayerVisibility(b)", [b])
    landed(page)
    # the group's eye hides and shows both
    out = page.evaluate("() => window.app.toggleGroupVisibility('gH')")
    landed(page)
    assert out is True
    assert page.evaluate(VISIBLE_JS, [a, b, c]) == [False, False, True]
    out = page.evaluate("() => window.app.toggleGroupVisibility('gH')")
    landed(page)
    assert out is True
    assert page.evaluate(VISIBLE_JS, [a, b, c]) == [True, True, True]
    assert errors(page)['locked'] == [], errors(page)
    # nothing else moved: the lock flags are the file's
    assert page.evaluate("(ids) => ids.map(id => !!window.__nf.layer(id).locked)", [a, b]) \
        == [False, True]
    # and an edit on A is still refused, naming B
    page.evaluate("([a]) => window.app.mergeSplitterCircuits(window.__nf.layer(a), [1, 2])", [a])
    landed(page)
    assert errors(page)['locked'] == [['B']], errors(page)


# ── 2. the Balance dialog names the locked screen ────────────────────────

def dialog_text(page, distro_id):
    return page.evaluate("""(id) => { const app = window.app; app._circuitTailCache = null;
        app.showBalanceDialog(id);
        const m = document.getElementById('balance-modal');
        const t = m ? m.innerText : null;
        if (m) m.remove();
        return t; }""", distro_id)


def test_the_balance_dialog_names_the_locked_member_of_a_half_locked_group(page):
    """A (unlocked) and B (locked) one group; A's seven circuits make a
    full multi on SL and a one-circuit multi on SR. The SR multi stays
    where it is because B holds A: B is named."""
    a, b = wall(page, pinned(7))
    r = page.evaluate("() => { window.app._circuitTailCache = null;"
                      " return window.app.suggestPhaseBalance('sr'); }")
    assert [x['layerName'] for x in r['locked']] == ['A'], r['locked']
    assert [x['layers'] for x in r['locked']] == [['B']], r['locked']
    text = dialog_text(page, 'sr')
    assert re.search(r'\(A\) stays where it is\. B is locked\.', text), text
    assert 'A is locked' not in text, text


# ── 5. the balancer leaves hidden screens' multis out ────────────────────

def test_the_balancer_never_searches_a_hidden_screens_multis(page):
    a, h = make(page, [{'name': 'A', 'columns': 2, 'props': pinned(2)},
                       {'name': 'H', 'columns': 3, 'x': 1000, 'props': pinned(3)}])
    set_distros(page, [_distro('sr', 'SR')], {a: {1: 'sr'}, h: {1: 'sr'}})
    shown = page.evaluate("() => { window.app._circuitTailCache = null;"
                          " return window.app.suggestPhaseBalance('sr'); }")
    assert len(shown['targets']) == 2 and shown['hidden'] == [], shown
    page.evaluate("(h) => { window.__nf.layer(h).visible = false; }", h)
    try:
        hidden = page.evaluate("() => { window.app._circuitTailCache = null;"
                               " return window.app.suggestPhaseBalance('sr'); }")
        assert len(hidden['targets']) == 1 and '(A, 2 circuits)' in hidden['targets'][0], hidden
        assert [x['layerName'] for x in hidden['hidden']] == ['H'], hidden
        assert hidden['searched'] < shown['searched'], (hidden['searched'], shown['searched'])
        assert not [m for m in hidden['moves'] if m['layerId'] == h], hidden['moves']
        text = dialog_text(page, 'sr')
        assert '1 partly-filled multi' in text or 'Nothing on this distro can move' in text, text
        assert re.search(r'\(H\) stays where it is\. H is hidden\.', text), text
    finally:
        page.evaluate("(h) => { window.__nf.layer(h).visible = true; }", h)
