"""Power after the round 5 audit (the owner's rulings, 2026-10-23).

1. Grouping never repacks a locked screen: under "Lock the whole group" a
   grouping that would move a locked screen's packing % or re-walk its
   circuits into the wall is refused whole, the screen named, nothing
   changed and no history entry.
2. Circuit actions are refused the same way when they would repack a
   locked screen through an unlocked member of its group: Share with next
   run, the batch "2fer this screen", Remove 3fer, Nfer it, and a power
   setting written onto the unlocked member (its panel watts).
3. That refusal says why: "B is locked, and this would repack its
   circuits. Unlock it to change it." An action on the locked screen itself
   keeps the plain wording.

   Round 6 (the owner's ruling): a group with some members locked and some
   not (an old file's) is treated as fully locked, so every action on its
   unlocked member A is refused with the plain error naming B, whether it
   would repack B or not (test_r6_power_rulings.py). The repack wording
   stays for a grouping or a distro change that repacks a locked screen.
4. A hidden screen is left out of every distro and service load: the tray's
   distro load, the distro checks, the service card and the phase balance.
5. The duplicate-distro suffix counts only distros that print: an unused
   duplicate never forces SR-1 / SR-2 on the one that prints.
6. Wording: a screen on no distro above 208 V packs to its breaker, and a
   multi name used on two boxes names them the way they print.

The walls are the nfer module's: 5 rows of cabinets on 208 V x 20 A, cabled
top-down. SL is a US distro with 100% rated breakers (packs at the
breaker), SR a plain US distro (80%). A screen packs at the lowest % of
the distros its group's multis are on.

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_r5_power_rulings.py -v --browser chromium
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
from test_lock_repack_rulings import state  # noqa: E402


def pinned(columns):
    """Sharing on, every run pinned out of packing: one circuit a column."""
    return {'powerSplitters': {'enabled': True, 'maxWays': 3, 'manual': {
        'merge': [], 'split': list(range(1, columns + 1))}}}


def count(page, layer_id):
    return page.evaluate("""(id) => { const app = window.app; app._circuitTailCache = null;
        return app.screenCircuits(window.__nf.layer(id)).length; }""", layer_id)


def assert_refused(page, ids, before, h0, names=('B',)):
    landed(page)
    assert errors(page)['locked'] == [list(names)], errors(page)
    assert state(page, ids) == before, 'a refused action changed a store'
    assert len(history(page)) == h0, history(page)


def toasts_on(page):
    """The real error toasts, the locked error unhooked."""
    page.evaluate("""() => {
        window.__r5 = [];
        const app = window.app;
        if (!app.__r5Toast) app.__r5Toast = app._toast.bind(app);
        app._toast = (m, err, ms) => { if (err) window.__r5.push(m); return app.__r5Toast(m, err, ms); };
        delete app._showLockedError;
    }""")


def toasts(page):
    return page.evaluate("() => window.__r5")


def wall(page, a_props, a_columns=7, b_watts=100):
    """A (unlocked) and B (locked, 4 columns, fed by nothing) grouped, A's
    multi 1 on SL and multi 2 on SR, so B packs at 80%. B's cabinets draw
    other watts, so each screen walks its own circuits."""
    a, b = make(page, [{'name': 'A', 'columns': a_columns, 'props': a_props},
                       {'name': 'B', 'columns': 4, 'x': 2000,
                        'props': dict(SHARING_OFF, locked=True, panelWatts=b_watts)}],
                group=True)
    set_distros(page, [_distro('sl', 'SL', breakers100=True), _distro('sr', 'SR')],
                {a: {1: 'sl', 2: 'sr'}})
    errors_on(page)
    # the distros are part of the state the history holds from here
    page.evaluate("() => window.app.resetHistory('Initial State')")
    return a, b


# ── 1. grouping ──────────────────────────────────────────────────────────

GROUP_JS = """async ([ids, gid]) => { const app = window.app;
    app.askGroupLock = () => Promise.resolve('lock');
    app.selectedLayerIds = new Set(ids);
    const out = gid ? await app.addSelectedToGroup(gid) : await app.groupSelectedLayers();
    return { out, groups: (app.project.groups || []).map(g => g.layer_ids),
             locked: app.project.layers.filter(l => /^[A-Z]$/.test(l.name))
                 .map(l => [l.name, !!l.locked]) }; }"""


def test_grouping_that_repacks_a_locked_screen_is_refused(page):
    """B locked on SL (100% rated), C unlocked on SR. Grouped under Lock the
    whole group, B would pack at 80% and its circuits re-walk into the wall."""
    b, c = make(page, [{'name': 'B', 'columns': 6, 'props': dict(SHARING_OFF, locked=True)},
                       {'name': 'C', 'columns': 6, 'x': 1600, 'props': SHARING_OFF}])
    set_distros(page, [_distro('sl', 'SL', breakers100=True), _distro('sr', 'SR')],
                {b: {1: 'sl', 2: 'sl'}, c: {1: 'sr', 2: 'sr'}})
    errors_on(page)
    assert capacity(page, b)['pct'] == 1
    before, h0 = state(page, [b, c]), len(history(page))
    out = page.evaluate(GROUP_JS, [[b, c], None])
    landed(page)
    assert out['out'] is None, out
    assert out['groups'] == [] and out['locked'] == [['B', True], ['C', False]], out
    assert_refused(page, [b, c], before, h0)
    assert page.evaluate("(id) => window.__nf.layer(id).group_id || null", b) is None
    assert capacity(page, b)['pct'] == 1


def test_adding_to_a_group_that_repacks_a_locked_screen_is_refused(page):
    b, d = make(page, [{'name': 'B', 'columns': 6, 'props': dict(SHARING_OFF, locked=True)},
                       {'name': 'D', 'columns': 6, 'x': 1600,
                        'props': dict(SHARING_OFF, locked=True)}], group=True)
    (c,) = page.evaluate("""async () => {
        const made = await window.__nf.j('POST', '/api/layer/add', { name: 'C', columns: 6,
            rows: 5, cabinet_width: 200, cabinet_height: 200, offset_x: 3200, offset_y: 0 });
        const app = window.app;
        app.project = await window.__nf.j('GET', '/api/project');
        app.dedupeProjectLayers('r5');
        const l = app.project.layers.find(x => x.id === made.id);
        Object.assign(l, { powerFlowPattern: 'tl-v', powerVoltage: 208, powerAmperage: 20,
            panelWatts: 150, powerOrganized: true,
            powerSplitters: { enabled: false, maxWays: 3, manual: { merge: [], split: [] } } });
        app._circuitTailCache = null; app.resetHistory('Initial State');
        return [made.id]; }""")
    landed(page)
    set_distros(page, [_distro('sl', 'SL', breakers100=True), _distro('sr', 'SR')],
                {b: {1: 'sl', 2: 'sl'}, d: {1: 'sl'}, c: {1: 'sr', 2: 'sr'}})
    errors_on(page)
    gid = page.evaluate("(id) => window.__nf.layer(id).group_id", b)
    before, h0 = state(page, [b, d, c]), len(history(page))
    out = page.evaluate(GROUP_JS, [[c], gid])
    landed(page)
    assert out['out'] is False, out
    assert out['groups'] == [[b, d]], out
    # B owns the wall's walk, so its circuits would take in C's columns;
    # D's multi is stale either way and its packing stays
    assert_refused(page, [b, d, c], before, h0)


def test_grouping_that_re_walks_a_locked_screens_circuits_is_refused(page):
    """Two matching walls on no distro pack at the same %, but grouped they
    walk their circuits as one wall: B's circuits would be re-walked into
    A's, so Lock the whole group is refused and B named."""
    a, b = make(page, [{'name': 'A', 'columns': 3, 'props': SHARING_OFF},
                       {'name': 'B', 'columns': 3, 'x': 800,
                        'props': dict(SHARING_OFF, locked=True)}])
    errors_on(page)
    before, h0 = state(page, [a, b]), len(history(page))
    runs_b = count(page, b)
    out = page.evaluate(GROUP_JS, [[a, b], None])
    landed(page)
    assert out['out'] is None and out['groups'] == [], out
    assert_refused(page, [a, b], before, h0)
    assert count(page, b) == runs_b


def test_grouping_that_leaves_the_locked_screen_as_it_is_takes(page):
    """C's cabinets draw other watts, so the wall does not walk as one, and
    C is on a 100% rated distro too: B packs and reads as it did."""
    b, c = make(page, [{'name': 'B', 'columns': 6, 'props': dict(SHARING_OFF, locked=True)},
                       {'name': 'C', 'columns': 6, 'x': 1600,
                        'props': dict(SHARING_OFF, panelWatts=100)}])
    set_distros(page, [_distro('sl', 'SL', breakers100=True),
                       _distro('s2', 'S2', breakers100=True)],
                {b: {1: 'sl', 2: 'sl'}, c: {1: 's2'}})
    errors_on(page)
    h0 = len(history(page))
    out = page.evaluate(GROUP_JS, [[b, c], None])
    landed(page)
    assert out['out'], out
    assert out['locked'] == [['B', True], ['C', True]], out
    assert errors(page)['locked'] == [], errors(page)
    assert len(history(page)) == h0 + 1, history(page)
    assert capacity(page, b)['pct'] == 1


def test_the_grouping_refusal_says_why(page):
    b, c = make(page, [{'name': 'B', 'columns': 6, 'props': dict(SHARING_OFF, locked=True)},
                       {'name': 'C', 'columns': 6, 'x': 1600, 'props': SHARING_OFF}])
    set_distros(page, [_distro('sl', 'SL', breakers100=True), _distro('sr', 'SR')],
                {b: {1: 'sl'}, c: {1: 'sr'}})
    toasts_on(page)
    page.evaluate(GROUP_JS, [[b, c], None])
    landed(page)
    assert toasts(page) == [
        'B is locked, and this would repack its circuits. Unlock it to change it.'], toasts(page)


# ── 2. circuit actions ───────────────────────────────────────────────────

def test_share_with_next_run_refuses_a_locked_group_member_it_repacks(page):
    """A's seven pinned runs are seven circuits, two multis. Sharing two
    leaves six, one multi: SR drops out and B would pack at 100%."""
    a, b = wall(page, pinned(7))
    assert count(page, a) == 7 and capacity(page, b)['pct'] == 0.8
    before, h0 = state(page, [a, b]), len(history(page))
    out = page.evaluate("([a]) => window.app.mergeSplitterCircuits(window.__nf.layer(a), [1, 2])", [a])
    assert out is False
    assert_refused(page, [a, b], before, h0)
    assert capacity(page, b)['pct'] == 0.8


def test_2fer_this_screen_refuses_a_locked_group_member_it_repacks(page):
    a, b = wall(page, pinned(7))
    before, h0 = state(page, [a, b]), len(history(page))
    out = page.evaluate("""([a]) => { const app = window.app, l = window.__nf.layer(a);
        app._circuitTailCache = null;
        return app.batchShareCircuits(l, app.screenCircuits(l).map(c => c.num), 2,
            '2fer Screen', null, { tickSharing: true }); }""", [a])
    assert out is False
    assert_refused(page, [a, b], before, h0)


def test_remove_2fer_refuses_a_locked_group_member_it_repacks(page):
    """Six circuits, the first two shared: Remove 2fer makes seven, two
    multis, so the stale SR entry comes alive and B would pack at 80%."""
    props = pinned(7)
    props['powerSplitters']['manual'] = {'merge': [[1, 2]], 'split': [3, 4, 5, 6, 7]}
    a, b = wall(page, props)
    assert count(page, a) == 6 and capacity(page, b)['pct'] == 1
    before, h0 = state(page, [a, b]), len(history(page))
    page.evaluate("([a]) => window.app.splitSplitterCircuits(window.__nf.layer(a), [1])", [a])
    assert_refused(page, [a, b], before, h0)
    assert capacity(page, b)['pct'] == 1


def test_a_share_that_keeps_the_locked_members_packing_is_refused_too(page):
    """A's two multis both on SL: sharing two runs drops multi 2, and B
    would still pack at 100%. Round 6: A is a member of a half-locked
    group, so it is locked as well, and the share is refused, B named."""
    a, b = wall(page, pinned(7))
    set_distros(page, [_distro('sl', 'SL', breakers100=True), _distro('sr', 'SR')],
                {a: {1: 'sl', 2: 'sl'}})
    errors_on(page)
    page.evaluate("() => window.app.resetHistory('Initial State')")
    before, h0 = state(page, [a, b]), len(history(page))
    out = page.evaluate("([a]) => window.app.mergeSplitterCircuits(window.__nf.layer(a), [1, 2])", [a])
    assert out is False
    assert_refused(page, [a, b], before, h0)
    assert count(page, a) == 7


def test_nfer_it_refuses_a_locked_group_member_it_repacks(page):
    """A and C draw custom circuits on one wall, A the owner; B (locked,
    automatic) is in the group too. C's one circuit runs down two columns on
    its own multi on SR. Nfer it moves the circuit into A's numbering and C's
    multi lets go of SR, so B would pack at 100%: refused whole."""
    custom = dict(SHARING_OFF, powerFlowPattern='custom', powerCustomPath=True)
    a, c, b = make(page, [{'name': 'A', 'columns': 2, 'props': custom},
                          {'name': 'C', 'columns': 3, 'x': 800, 'props': custom},
                          {'name': 'B', 'columns': 4, 'x': 2000,
                           'props': dict(SHARING_OFF, locked=True, panelWatts=100)}],
                   group=True)
    page.evaluate("""([a, c]) => { const app = window.app;
        const col = (l, k) => [0, 1, 2, 3, 4].map(r => app.makePathEntry(l, l,
            app.getPanelByRowCol(l, r, k)));
        const A = window.__nf.layer(a), C = window.__nf.layer(c);
        A.powerCustomPaths = { 1: col(A, 0), 2: col(A, 1) };
        C.powerCustomPaths = { 1: col(C, 0).concat(col(C, 1).reverse()) };
        app._circuitTailCache = null; }""", [a, c])
    set_distros(page, [_distro('sl', 'SL', breakers100=True), _distro('sr', 'SR')],
                {a: {1: 'sl'}, c: {1: 'sr'}})
    errors_on(page)
    page.evaluate("() => window.app.resetHistory('Initial State')")
    assert count(page, c) == 1 and capacity(page, b)['pct'] == 0.8
    plan = page.evaluate("""([c]) => { const p = window.app.nferCircuitPlan(window.__nf.layer(c), 1);
        return p && { ways: p.ways, reason: p.reason, mode: p.mode }; }""", [c])
    assert plan == {'ways': 2, 'reason': None, 'mode': 'custom'}, plan
    before, h0 = state(page, [a, c, b]), len(history(page))
    out = page.evaluate("([c]) => window.app.nferCircuit(window.__nf.layer(c), 1)", [c])
    assert out is False
    assert_refused(page, [a, c, b], before, h0)
    assert capacity(page, b)['pct'] == 0.8
    # with B unlocked it takes, one entry
    page.evaluate("(b) => { window.__nf.layer(b).locked = false; }", b)
    out = page.evaluate("([c]) => window.app.nferCircuit(window.__nf.layer(c), 1)", [c])
    landed(page)
    assert out is True
    assert history(page)[h0:] == ['2fer Circuit'], history(page)


def test_panel_watts_on_an_unlocked_member_refuse_a_locked_screen_it_repacks(page):
    """A's 600 W cabinets make a circuit a column: seven circuits, two
    multis. 300 W makes it two columns a circuit, four circuits: SR drops
    out and B would pack at 100%. The Power Settings box puts it back."""
    a, b = wall(page, dict(SHARING_OFF, panelWatts=600))
    assert count(page, a) == 7 and capacity(page, b)['pct'] == 0.8
    before, h0 = state(page, [a, b]), len(history(page))
    out = page.evaluate("""([a]) => { const app = window.app, l = window.__nf.layer(a);
        app.currentLayer = l; app.selectedLayerIds = new Set([a]);
        app.loadLayerToInputs();
        const el = document.getElementById('power-panel-watts');
        el.value = '300'; el.dispatchEvent(new Event('change', { bubbles: true }));
        return l.panelWatts; }""", [a])
    landed(page)
    assert out == 600
    assert_refused(page, [a, b], before, h0)
    assert capacity(page, b)['pct'] == 0.8
    # with B unlocked the same edit takes
    page.evaluate("(b) => { window.__nf.layer(b).locked = false; }", b)
    page.evaluate("""([a]) => { const el = document.getElementById('power-panel-watts');
        el.value = '300'; el.dispatchEvent(new Event('change', { bubbles: true })); }""", [a])
    landed(page)
    assert page.evaluate("(a) => window.__nf.layer(a).panelWatts", a) == 300
    assert capacity(page, b)['pct'] == 1


def test_a_mixed_tray_clear_touching_a_half_locked_group_member_skips_it(page):
    """Unplug multi on A's multi 2 (SR) and C's multi (no group). Round 5
    refused it whole (B would repack). Since round 6 A, the unlocked member
    of a half-locked group, is locked itself, and round 7 has it behave
    exactly as a locked member: A is skipped and B named, nothing of A or B
    changes, and C, in no group, still clears (test_r7_power_rulings.py
    has both orders and the truly locked member)."""
    a, b = wall(page, dict(SHARING_OFF, panelWatts=600))
    (c,) = page.evaluate("""async () => {
        const made = await window.__nf.j('POST', '/api/layer/add', { name: 'C', columns: 2,
            rows: 5, cabinet_width: 200, cabinet_height: 200, offset_x: 4000, offset_y: 0 });
        const app = window.app;
        app.project = await window.__nf.j('GET', '/api/project');
        app.dedupeProjectLayers('r5');
        return [made.id]; }""")
    landed(page)
    # make() state was re-read from the server: put the walls back
    page.evaluate("""([a, b, c]) => { const app = window.app, L = (id) => window.__nf.layer(id);
        const base = { powerFlowPattern: 'tl-v', powerOrganized: true, powerMaximize: false,
            powerVoltage: 208, powerAmperage: 20, powerCustomPath: false,
            powerSplitters: { enabled: false, maxWays: 3, manual: { merge: [], split: [] } } };
        Object.assign(L(a), base, { panelWatts: 600, group_id: 'gN', locked: false });
        Object.assign(L(b), base, { panelWatts: 100, group_id: 'gN', locked: true });
        Object.assign(L(c), base, { panelWatts: 150, locked: false });
        app.project.groups = [{ id: 'gN', name: 'WALL', layer_ids: [a, b] }];
        app._circuitTailCache = null; app.resetHistory('Initial State'); }""", [a, b, c])
    set_distros(page, [_distro('sl', 'SL', breakers100=True), _distro('sr', 'SR')],
                {a: {1: 'sl', 2: 'sr'}, c: {1: 'sr'}})
    errors_on(page)
    assert capacity(page, b)['pct'] == 0.8
    before, h0 = state(page, [a, b, c]), len(history(page))
    page.evaluate("""([a, c]) => window.app._clearMultis(
        [{ layerId: a, soca: 2 }, { layerId: c, soca: 1 }], 'Unplug Multi')""", [a, c])
    landed(page)
    assert errors(page)['locked'] == [['B']], errors(page)
    was, now = json.loads(before)['layers'], json.loads(state(page, [a, b, c]))['layers']
    assert now[0] == was[0] and now[1] == was[1], 'A or B changed'
    assert (now[2].get('powerSocaDistro') or {}).get('1') is None, now[2]
    assert (was[2].get('powerSocaDistro') or {}).get('1') == 'sr', was[2]
    assert len(history(page)) == h0 + 1, history(page)
    assert capacity(page, b)['pct'] == 0.8


# ── 3. the wording of the refusal ────────────────────────────────────────

def test_the_repack_refusal_says_why_and_the_locked_screen_itself_does_not(page):
    # Round 6: A is a member of a half-locked group, so it is locked too,
    # and its own actions say the plain error naming B.
    a, b = wall(page, pinned(7))
    toasts_on(page)
    page.evaluate("([a]) => window.app.mergeSplitterCircuits(window.__nf.layer(a), [1, 2])", [a])
    landed(page)
    assert toasts(page) == ['B is locked. Unlock it to change it.'], toasts(page)
    page.evaluate("() => { window.__r5.length = 0; }")
    page.evaluate("([b]) => window.app.setSocaDistro(window.__nf.layer(b), 1, 'sr')", [b])
    landed(page)
    assert toasts(page) == ['B is locked. Unlock it to change it.'], toasts(page)
    page.evaluate("() => { window.__r5.length = 0; }")
    page.evaluate("() => window.app.removeDistro('sr')")
    landed(page)
    assert toasts(page) == ['B is locked. Unlock it to change it.'], toasts(page)
    # A distro change that repacks a locked screen it feeds says why: LK
    # (locked, in no group) on SR packs at 80%, and ticking SR's 100%
    # rated breakers would pack it at the breaker.
    (lk,) = make(page, [{'name': 'LK', 'columns': 4, 'props': dict(SHARING_OFF, locked=True)}])
    set_distros(page, [_distro('sr', 'SR')], {lk: {1: 'sr'}})
    toasts_on(page)
    assert capacity(page, lk)['pct'] == 0.8
    out = page.evaluate("() => window.app.updateDistro('sr', { breakers100: true })")
    landed(page)
    assert out is None
    assert toasts(page) == [
        'LK is locked, and this would repack its circuits. Unlock it to change it.'], toasts(page)
    assert capacity(page, lk)['pct'] == 0.8


def test_two_repacked_screens_are_named_together(page):
    msg = page.evaluate("""() => { const app = window.app, out = [];
        const real = app._toast; app._toast = (m) => out.push(m);
        try { delete app._showLockedError;
              app._lockedErrorThisTurn = null;
              app._showLockedError([{ id: 901, name: 'B' }, { id: 902, name: 'D' }], 'repack'); }
        finally { app._toast = real; }
        return out; }""")
    assert msg == ['B and D are locked, and this would repack their circuits. '
                   'Unlock them to change them.'], msg


# ── 4. hidden screens leave the loads ────────────────────────────────────

LOADS_JS = """() => { const app = window.app; app._circuitTailCache = null;
    return app.getDistroLoads().map(l => ({ id: l.id, watts: Math.round(l.watts),
        socas: l.socas.map(s => s.layer), imbalance: Math.round(l.imbalancePct) })); }"""


def test_a_hidden_screen_leaves_the_distro_load_checks_service_and_balance(page):
    a, h = make(page, [{'name': 'A', 'columns': 2, 'props': SHARING_OFF},
                       {'name': 'H', 'columns': 28, 'x': 1000, 'props': SHARING_OFF}])
    set_distros(page, [_distro('d1', 'SR'), _distro('d2', 'SL')], {a: {1: 'd1'}, h: {1: 'd1', 2: 'd2'}})
    page.evaluate("""() => { const app = window.app;
        app.project.services = [{ id: 'svc1', name: 'House', ratingA: 400, system: '120/208',
                                  voltage: 208, phase: 3 }];
        app.getDistros().forEach(d => { d.serviceId = 'svc1'; });
        app._circuitTailCache = null; }""")
    shown = page.evaluate(LOADS_JS)
    assert shown[0]['socas'] == ['A', 'H'] and shown[1]['socas'] == ['H'], shown
    service_shown = page.evaluate("""() => { const s = window.app.getServiceLoads();
        return s.length ? Math.round(s[0].watts) : null; }""")
    page.evaluate("(h) => { window.__nf.layer(h).visible = false; }", h)
    hidden = page.evaluate(LOADS_JS)
    assert hidden[0]['socas'] == ['A'] and hidden[0]['watts'] == 1500, hidden
    # a distro whose screens are all hidden reads empty
    assert hidden[1]['socas'] == [] and hidden[1]['watts'] == 0, hidden
    out = page.evaluate("""() => { const app = window.app; app._circuitTailCache = null;
        const d2 = app.getDistros().find(d => d.id === 'd2');
        const s = app.getServiceLoads();
        return { circuits: app._distroCircuitsOn(d2).length,
                 service: s.length ? Math.round(s[0].watts) : null,
                 phasor: app._balanceCircuitPhasor(d2, { layer: window.__nf.layer(%d),
                     s: app.getSocaPlan(window.__nf.layer(%d))[0],
                     leg: app.getSocaPlan(window.__nf.layer(%d))[0].legs[0] }, 1) }; }"""
                        % (h, h, h))
    assert out['circuits'] == 0, out
    assert service_shown is not None and out['service'] == 1500 < service_shown, (service_shown, out)
    assert out['phasor'] == [0, 0, 0, 0, 0, 0], out
    page.evaluate("(h) => { window.__nf.layer(h).visible = true; }", h)


def test_the_tray_distro_load_leaves_a_hidden_screen_out(page):
    a, h = make(page, [{'name': 'A', 'columns': 2, 'props': SHARING_OFF},
                       {'name': 'H', 'columns': 2, 'x': 1000, 'props': SHARING_OFF}])
    set_distros(page, [_distro('d1', 'SR')], {a: {1: 'd1'}, h: {1: 'd1'}})
    tray = """() => { const app = window.app; app._circuitTailCache = null;
        app.renderHardwareDock();
        const el = document.querySelector('.hw-dock-unit-use');
        return el ? el.textContent : null; }"""
    both = page.evaluate(tray)
    page.evaluate("(h) => { window.__nf.layer(h).visible = false; }", h)
    one = page.evaluate(tray)
    page.evaluate("(h) => { window.__nf.layer(h).visible = true; }", h)
    assert both and one and both != one, (both, one)
    amps = lambda t: float(t.split('/')[0])  # noqa: E731
    assert abs(amps(one) * 2 - amps(both)) < 0.2, (both, one)


# ── 5. the duplicate-distro suffix ───────────────────────────────────────

LABELS_JS = """() => { const app = window.app; app._circuitTailCache = null;
    return app.getDistros().map(d => app.distroLabel(d)); }"""


def test_an_unused_duplicate_does_not_suffix_the_distro_that_prints(page):
    (a,) = make(page, [{'name': 'A', 'columns': 2}])
    set_distros(page, [_distro('d1', 'SR'), _distro('d2', 'SR')], {a: {1: 'd1'}})
    assert page.evaluate(LABELS_JS) == ['SR', 'SR'], 'the unused SR is not counted'
    # a feeder prints it, and then both count
    page.evaluate("() => { window.app.getDistros()[1].feeder = { ft: 50 }; }")
    assert page.evaluate(LABELS_JS) == ['SR-1', 'SR-2']
    # so does a screen plugged into it
    page.evaluate("() => { delete window.app.getDistros()[1].feeder; }")
    assert page.evaluate(LABELS_JS) == ['SR', 'SR']


def test_two_used_duplicates_still_take_the_suffix(page):
    a, b = make(page, [{'name': 'A', 'columns': 2}, {'name': 'B', 'columns': 2, 'x': 1000}])
    set_distros(page, [_distro('d1', 'SR'), _distro('d2', 'SR')], {a: {1: 'd1'}, b: {1: 'd2'}})
    assert page.evaluate(LABELS_JS) == ['SR-1', 'SR-2']


# ── 6. wording ───────────────────────────────────────────────────────────

def test_a_screen_on_no_distro_above_208v_says_it_packs_to_its_breaker(page):
    (s,) = make(page, [{'name': 'S', 'columns': 2, 'props': {'powerVoltage': 240}}])
    set_distros(page, [_distro('eu', 'EU', '230/400')])
    cap = capacity(page, s)
    assert cap['pct'] == 1
    assert 'A screen on no distro above 208 V packs to its breaker.' in cap['wattsTip'], cap
    tip = page.evaluate("() => document.getElementById('power-amperage-usable').title")
    assert tip == 'A screen on no distro above 208 V packs to its breaker.', tip
    # on a UK/EU distro it says so
    page.evaluate("(id) => { window.__nf.layer(id).powerSocaDistro = { 1: 'eu' }; }", s)
    tip = page.evaluate("""(id) => { const app = window.app; app._circuitTailCache = null;
        return app.circuitPctReason(window.__nf.layer(id)); }""", s)
    assert tip == 'A UK/EU circuit packs to its breaker.', tip


def test_a_name_used_on_two_boxes_names_them_the_way_they_print(page):
    """SL's box 1 typed SR1, the name distro SR's box 1 wears on its own."""
    a, b = make(page, [{'name': 'A', 'columns': 2}, {'name': 'B', 'columns': 2, 'x': 1000}])
    set_distros(page, [_distro('d1', 'SR'), _distro('d2', 'SL')], {a: {1: 'd1'}, b: {1: 'd2'}})
    page.evaluate("(b) => { window.__nf.layer(b).powerSocaNames = { 1: 'SR1' }; }", b)
    warn = page.evaluate("""() => { const app = window.app; app._circuitTailCache = null;
        return app._typedMultiNameDuplicates().map(d => app._typedMultiNameText(d)); }""")
    assert warn == ['SR1 is used on 2 boxes, SR1 and SL1. '
                    'Rename one so each box reads its own name.'], warn


def test_no_page_errors(page):
    assert page._nf_errors == [], page._nf_errors
