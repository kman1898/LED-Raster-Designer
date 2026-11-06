"""Power and locks after the round 6 audit (the owner's rulings, 2026-10-23).

1. A HALF-LOCKED group is treated as fully LOCKED. Such groups exist only
   in old files: some members locked, some not. Any edit to any member is
   refused with the locked-screen error naming the locked member, until
   the user picks Lock or Unlock for the group (the first lock toggle
   still asks): typed power settings, columns, breakout, shares, Remove
   2fer, delete, adding a screen to the group, multi moves.
   Round 7 (the owner's ruling): hide and show are ALLOWED on a
   half-locked group, as on a locked screen: visibility is not a change
   (test_r7_power_rulings.py).
4. The duplicate-distro suffix counts only distros that print, even with
   stale multi entries: an entry for a multi the screen no longer has
   plugs nothing in.
5. Wording: a screen on an old distro record with no system picked says
   so in the pack-rule tooltip.

(2 and 3, hidden screens keeping their slots and the face-edit crowd
question, are in test_r6_hidden_slots.py.)

The walls are the nfer module's: 5 rows of cabinets on 208 V x 20 A, cabled
top-down. A is unlocked, B locked, and the two are one group (an old
file's shape: the app's own lock verbs lock a group as one).

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_r6_power_rulings.py -v --browser chromium
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_nfer_custom_rulings import (  # noqa: E402,F401 - fixtures
    _guard, page, landed, make, history,
)
from test_power_rulings_1021 import errors_on, errors  # noqa: E402
from test_power_region_rulings import (  # noqa: E402
    SHARING_OFF, _distro, set_distros, capacity,
)
from test_r5_power_rulings import wall, pinned, LABELS_JS  # noqa: E402


# Every field of the screens (the render caches aside), the groups and the
# distros: a refused edit leaves all of it exactly as it was.
SNAP_JS = """(ids) => {
    const app = window.app;
    return JSON.stringify({
        layers: ids.map(id => {
            const l = app.project.layers.find(x => x.id === id);
            return l ? JSON.parse(JSON.stringify(l, (k, v) => k.charAt(0) === '_' ? undefined : v))
                : null;
        }),
        groups: app.project.groups,
        distros: app.project.distros,
    });
}"""


def snap(page, ids):
    """Parsed, so a field put back in another key order still compares
    equal."""
    return json.loads(page.evaluate(SNAP_JS, list(ids)))


def changed(before, after):
    """The keys a refused edit moved, for the assertion message."""
    b, a = before, after
    out = [k for k in ('groups', 'distros') if b[k] != a[k]]
    for i, (x, y) in enumerate(zip(b['layers'], a['layers'])):
        if x is None or y is None:
            out.append(f'layer {i} {"gone" if y is None else "back"}')
            continue
        out += [f'layer {i} {k}: {json.dumps(x.get(k))[:80]} -> {json.dumps(y.get(k))[:80]}'
                for k in sorted(set(x) | set(y)) if x.get(k) != y.get(k)]
    return out


def select(page, lid):
    page.evaluate("""(id) => { const app = window.app, l = window.__nf.layer(id);
        app.currentLayer = l; app.selectedLayerIds = new Set([id]);
        app.lastSelectedLayerId = id; app.loadLayerToInputs(); }""", lid)


def field(page, el_id, value):
    page.evaluate("""([id, v]) => { const el = document.getElementById(id);
        el.value = v;
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true })); }""", [el_id, value])


# Each edit runs on A, the UNLOCKED member, with A selected.
EDITS = {
    'panel watts': lambda pg, a, b: field(pg, 'power-panel-watts', '300'),
    'amperage': lambda pg, a, b: field(pg, 'power-amperage-select', '15'),
    'voltage': lambda pg, a, b: field(pg, 'power-voltage-select', '120'),
    'columns': lambda pg, a, b: field(pg, 'screen-columns', '5'),
    'breakout': lambda pg, a, b: field(pg, 'power-breakout-type', 'soca-powercon'),
    'share': lambda pg, a, b: pg.evaluate(
        "([a]) => window.app.mergeSplitterCircuits(window.__nf.layer(a), [1, 2])", [a]),
    '2fer this screen': lambda pg, a, b: pg.evaluate(
        """([a]) => { const app = window.app, l = window.__nf.layer(a);
        app._circuitTailCache = null;
        return app.batchShareCircuits(l, app.screenCircuits(l).map(c => c.num), 2,
            '2fer Screen', null, { tickSharing: true }); }""", [a]),
    'multi move': lambda pg, a, b: pg.evaluate(
        "([a]) => window.app.setSocaDistro(window.__nf.layer(a), 1, 'sr')", [a]),
    'unplug multi': lambda pg, a, b: pg.evaluate(
        "([a]) => window.app._clearMultis([{ layerId: a, soca: 1 }], 'Unplug Multi')", [a]),
    'delete': lambda pg, a, b: pg.evaluate("([a]) => window.app.deleteLayer(a)", [a]),
    'remove from group': lambda pg, a, b: pg.evaluate(
        "() => window.app.removeSelectedFromGroup()"),
    'a cosmetic field': lambda pg, a, b: field(pg, 'number-size', '41'),
}


@pytest.mark.parametrize('edit', list(EDITS))
def test_every_edit_on_a_half_locked_groups_unlocked_member_is_refused(page, edit):
    a, b = wall(page, pinned(7))
    select(page, a)
    errors_on(page)
    page.evaluate("() => window.app.resetHistory('Initial State')")
    landed(page)
    before, h0 = snap(page, [a, b]), len(history(page))
    EDITS[edit](page, a, b)
    landed(page)
    assert errors(page)['locked'] == [['B']], (edit, errors(page))
    after = snap(page, [a, b])
    assert after == before, (edit, changed(before, after))
    assert len(history(page)) == h0, (edit, history(page))


def test_the_locked_error_names_the_locked_member(page):
    """The real toast: an edit on A names B, the screen that is locked."""
    a, b = wall(page, pinned(7))
    select(page, a)
    page.evaluate("""() => { window.__r6 = []; const app = window.app;
        if (!app.__r6Toast) app.__r6Toast = app._toast.bind(app);
        app._toast = (m, err, ms) => { if (err) window.__r6.push(m); return app.__r6Toast(m, err, ms); };
        delete app._showLockedError; }""")
    field(page, 'power-panel-watts', '300')
    landed(page)
    assert page.evaluate("() => window.__r6") == ['B is locked. Unlock it to change it.']
    page.evaluate("() => { window.__r6.length = 0; }")
    page.evaluate("([a]) => window.app.deleteLayer(a)", [a])
    landed(page)
    assert page.evaluate("() => window.__r6") == ['B is locked. Unlock it to change it.']


def test_adding_a_screen_to_a_half_locked_group_is_refused(page):
    """C (unlocked, ungrouped) joining A + B: refused without asking, B
    named, nothing grouped."""
    a, b, c = make(page, [{'name': 'A', 'columns': 3, 'props': SHARING_OFF},
                          {'name': 'B', 'columns': 3, 'x': 800,
                           'props': dict(SHARING_OFF, locked=True)},
                          {'name': 'C', 'columns': 3, 'x': 1600, 'props': SHARING_OFF}])
    page.evaluate("""([a, b]) => { const app = window.app;
        app.project.groups = [{ id: 'gH', name: 'WALL', layer_ids: [a, b] }];
        window.__nf.layer(a).group_id = 'gH'; window.__nf.layer(b).group_id = 'gH';
        app._circuitTailCache = null; app.resetHistory('Initial State'); }""", [a, b])
    errors_on(page)
    landed(page)
    before, h0 = snap(page, [a, b, c]), len(history(page))
    out = page.evaluate("""async ([c]) => { const app = window.app;
        window.__asked = false;
        app.askGroupLock = () => { window.__asked = true; return Promise.resolve('lock'); };
        app.selectedLayerIds = new Set([c]);
        return await app.addSelectedToGroup('gH'); }""", [c])
    landed(page)
    assert out is False
    assert page.evaluate("() => window.__asked") is False, 'it asked instead of refusing'
    assert errors(page)['locked'] == [['B']], errors(page)
    assert snap(page, [a, b, c]) == before
    assert len(history(page)) == h0
    # grouping A with C (A leaving its half-locked group) is refused too
    out = page.evaluate("""async ([a, c]) => { const app = window.app;
        app.selectedLayerIds = new Set([a, c]);
        return await app.groupSelectedLayers(); }""", [a, c])
    landed(page)
    assert out is None
    assert page.evaluate("() => window.__asked") is False
    assert snap(page, [a, b, c]) == before


def test_the_lock_toggle_still_asks_and_unlock_frees_the_wall(page):
    a, b = wall(page, SHARING_OFF)
    page.evaluate("""() => { const app = window.app;
        window.__asked = null;
        app.askGroupLock = (screens) => { window.__asked = screens.map(l => l.name);
            return Promise.resolve('unlock'); }; }""")
    out = page.evaluate("() => window.app.toggleGroupLock(window.app.project.groups[0].id)")
    landed(page)
    assert out is True
    assert page.evaluate("() => window.__asked") == ['A', 'B']
    assert page.evaluate("(ids) => ids.map(id => !!window.__nf.layer(id).locked)", [a, b]) \
        == [False, False]
    # the wall is unlocked as one now: the edit on A takes
    select(page, a)
    errors_on(page)
    field(page, 'screen-columns', '5')
    landed(page)
    assert page.evaluate("(a) => window.__nf.layer(a).columns", a) == 5
    assert errors(page)['locked'] == []


def test_lock_the_whole_group_keeps_every_member_locked(page):
    a, b = wall(page, SHARING_OFF)
    page.evaluate("() => { window.app.askGroupLock = () => Promise.resolve('lock'); }")
    page.evaluate("() => window.app.toggleGroupLock(window.app.project.groups[0].id)")
    landed(page)
    assert page.evaluate("(ids) => ids.map(id => !!window.__nf.layer(id).locked)", [a, b]) \
        == [True, True]
    select(page, a)
    errors_on(page)
    field(page, 'screen-columns', '5')
    landed(page)
    assert page.evaluate("(a) => window.__nf.layer(a).columns", a) == 7
    assert errors(page)['locked'] == [['A']]


def test_an_unlocked_group_and_a_lone_locked_screen_are_not_held(page):
    """A + B grouped and both unlocked, LK locked on its own: A's edit takes,
    and hiding A is no change to LK."""
    a, b, lk = make(page, [{'name': 'A', 'columns': 3, 'props': SHARING_OFF},
                           {'name': 'B', 'columns': 3, 'x': 800, 'props': SHARING_OFF},
                           {'name': 'LK', 'columns': 3, 'x': 1600,
                            'props': dict(SHARING_OFF, locked=True)}])
    page.evaluate("""([a, b]) => { const app = window.app;
        app.project.groups = [{ id: 'gU', name: 'WALL', layer_ids: [a, b] }];
        window.__nf.layer(a).group_id = 'gU'; window.__nf.layer(b).group_id = 'gU';
        app._circuitTailCache = null; app.resetHistory('Initial State'); }""", [a, b])
    select(page, a)
    errors_on(page)
    field(page, 'screen-columns', '5')
    landed(page)
    assert page.evaluate("(a) => window.__nf.layer(a).columns", a) == 5
    page.evaluate("([a]) => window.app.toggleLayerVisibility(a)", [a])
    landed(page)
    assert page.evaluate("(a) => window.__nf.layer(a).visible", a) is False
    assert errors(page)['locked'] == []
    page.evaluate("([a]) => window.app.toggleLayerVisibility(a)", [a])
    landed(page)


# ── 4. the suffix with stale multi entries ───────────────────────────────

def test_a_stale_multi_entry_does_not_print_its_distro(page):
    """A makes one multi, but its store still says multi 2 is on the second
    SR (typed watts went down). Only the first SR prints, so neither takes a
    suffix, and the binder agrees."""
    (a,) = make(page, [{'name': 'A', 'columns': 2}])
    set_distros(page, [_distro('d1', 'SR'), _distro('d2', 'SR')], {a: {1: 'd1', 2: 'd2'}})
    out = page.evaluate("""(a) => { const app = window.app; app._circuitTailCache = null;
        return { multis: app.getSocaPlan(window.__nf.layer(a)).length,
                 prints: app.getDistros().map(d => app._bDistroPrints(d)) }; }""", a)
    assert out == {'multis': 1, 'prints': [True, False]}, out
    assert page.evaluate(LABELS_JS) == ['SR', 'SR']
    # a real second multi on the second SR prints it, and both take the suffix
    (b,) = make(page, [{'name': 'B', 'columns': 8, 'props': SHARING_OFF}])
    set_distros(page, [_distro('d1', 'SR'), _distro('d2', 'SR')], {b: {1: 'd1'}})
    assert page.evaluate("(b) => window.app.splitSocaAfter(window.__nf.layer(b), 1, 1)", b)
    landed(page)
    set_distros(page, [_distro('d1', 'SR'), _distro('d2', 'SR')], {b: {1: 'd1', 2: 'd2'}})
    assert page.evaluate("(b) => window.app.getSocaPlan(window.__nf.layer(b)).length", b) == 2
    assert page.evaluate(LABELS_JS) == ['SR-1', 'SR-2']


# ── 5. the pack-rule tooltip on an old distro record ─────────────────────

def test_a_screen_on_an_old_distro_record_says_so(page):
    (s,) = make(page, [{'name': 'S', 'columns': 2, 'props': {'powerVoltage': 240}}])
    set_distros(page, [_distro('old', 'OLD', system=None, voltage=240, phase=1)],
                {s: {1: 'old'}})
    cap = capacity(page, s)
    assert cap['pct'] == 1, cap
    want = 'Its distro has no system picked, so a screen above 208 V packs to its breaker.'
    assert want in cap['wattsTip'], cap
    assert page.evaluate("() => document.getElementById('power-amperage-usable').title") == want
    # off the distro it is the no-distro sentence again
    page.evaluate("(id) => { window.__nf.layer(id).powerSocaDistro = {}; }", s)
    tip = page.evaluate("""(id) => { const app = window.app; app._circuitTailCache = null;
        return app.circuitPctReason(window.__nf.layer(id)); }""", s)
    assert tip == 'A screen on no distro above 208 V packs to its breaker.', tip
