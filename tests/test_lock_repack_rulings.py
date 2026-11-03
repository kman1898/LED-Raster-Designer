"""A locked screen is never repacked (the owner's ruling, 2026-10-22).

Any distro or multi action that would change a LOCKED screen's packing %
(circuitCapacity, through the distros its multis are on) is refused with
the locked-screen error naming it, and nothing changes: no store, no
history entry. That includes a locked screen reached through an unlocked
member of its group, since a wall packs as one. Screens that are not
locked, and locked screens the action does not repack, are unaffected.

Round 6 (the owner's ruling): a group with some members locked and some
not (an old file's) is treated as fully locked until the user picks Lock
or Unlock, so every action on its unlocked member A is refused with the
plain error naming B, whether it would repack B or not. The repack checks
stay for the cases still possible: a distro change that repacks a locked
screen it feeds, and grouping.

The walls are the nfer module's (208 V x 20 A). A is unlocked, B is
locked and fed by nothing, and the two are one group: B packs at the % of
the distros A's multis are on. SL is a US distro with 100% rated breakers
(packs at the breaker), SR a plain US distro (80%), and a screen on no
distro at 208 V packs at 80% - so A on SL puts B at 100%, and taking A
off SL, or onto SR alongside it, moves B to 80%.

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_lock_repack_rulings.py -v --browser chromium
"""

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


STATE_JS = """(ids) => {
    const app = window.app;
    return JSON.stringify({
        distros: app.project.distros,
        layers: ids.map(id => {
            const l = window.__nf.layer(id), o = {};
            Object.keys(l).filter(k => k.startsWith('power')).sort()
                .forEach(k => { o[k] = l[k]; });
            return o;
        }),
    });
}"""


def walls(page, feeds=None, b_locked=True, columns=4):
    """A (unlocked) and B (locked unless told) grouped, SL (100% rated)
    and SR (80%) on the show, A's multis fed by `feeds`."""
    a, b = make(page, [{'name': 'A', 'columns': columns, 'props': SHARING_OFF},
                       {'name': 'B', 'columns': 4, 'x': 800,
                        'props': dict(SHARING_OFF, locked=b_locked)}], group=True)
    set_distros(page, [_distro('sl', 'SL', breakers100=True), _distro('sr', 'SR')],
                {a: feeds} if feeds else None)
    errors_on(page)
    return a, b


def state(page, ids):
    return page.evaluate(STATE_JS, ids)


def assert_refused(page, ids, before, h0, names=('B',)):
    landed(page)
    assert errors(page)['locked'] == [list(names)], errors(page)
    assert state(page, ids) == before, 'a refused action changed a store'
    assert len(history(page)) == h0, history(page)


def run(page, js, ids):
    out = page.evaluate(js, ids)
    landed(page)
    return out


# ── each action, refused through an unlocked group member ────────────────

def test_removing_the_distro_refuses_a_locked_group_member_it_repacks(page):
    a, b = walls(page, {1: 'sl'})
    assert capacity(page, b)['pct'] == 1
    before, h0 = state(page, [a, b]), len(history(page))
    out = run(page, "([a]) => window.app.removeDistro('sl')", [a])
    assert out is False
    assert_refused(page, [a, b], before, h0)
    assert capacity(page, b)['pct'] == 1


def test_the_gear_remove_button_keeps_the_distro_when_refused(page):
    a, b = walls(page, {1: 'sl'})
    before, h0 = state(page, [a, b]), len(history(page))
    page.evaluate("""() => {
        const app = window.app;
        localStorage.setItem('ledRasterPanelCollapsed_hwdock-distro-sl', '1');
        const wrap = app._buildDistroGearContent(app.getDistros()[0]);
        document.body.appendChild(wrap);
        wrap.querySelector('[data-lrd-field="distro-del-sl"]').click();
        wrap.remove();
    }""")
    assert_refused(page, [a, b], before, h0)
    assert page.evaluate(
        "() => localStorage.getItem('ledRasterPanelCollapsed_hwdock-distro-sl')") == '1'


def test_unassigning_a_multi_refuses_a_locked_group_member_it_repacks(page):
    a, b = walls(page, {1: 'sl'})
    before, h0 = state(page, [a, b]), len(history(page))
    out = run(page, """([a]) => window.app.setSocaDistro(window.__nf.layer(a), 1, null)
        .map(l => l.name)""", [a])
    assert out == []
    assert_refused(page, [a, b], before, h0)


def test_moving_a_multi_to_another_distro_refuses_a_locked_group_member(page):
    a, b = walls(page, {1: 'sl'})
    before, h0 = state(page, [a, b]), len(history(page))
    out = run(page, """([a]) => window.app.setSocaDistro(window.__nf.layer(a), 1, 'sr')
        .map(l => l.name)""", [a])
    assert out == []
    assert_refused(page, [a, b], before, h0)


def test_assigning_a_multi_refuses_a_locked_group_member_it_repacks(page):
    a, b = walls(page)
    assert capacity(page, b)['pct'] == 0.8
    before, h0 = state(page, [a, b]), len(history(page))
    out = run(page, """([a]) => window.app.setSocaDistro(window.__nf.layer(a), 1, 'sl')
        .map(l => l.name)""", [a])
    assert out == []
    assert_refused(page, [a, b], before, h0)
    assert capacity(page, b)['pct'] == 0.8


def test_a_take_onto_a_box_refuses_a_locked_group_member_it_repacks(page):
    a, b = walls(page)
    before, h0 = state(page, [a, b]), len(history(page))
    out = run(page, """([a]) => window.app.takeSocaOnto(window.__nf.layer(a), 1, 'sl', 1,
        'Assign Multi Distro')""", [a])
    assert out['ok'] is False and out['locked'] is True, out
    assert_refused(page, [a, b], before, h0)


def test_the_whole_distro_drop_refuses_a_locked_group_member(page):
    a, b = walls(page)
    before, h0 = state(page, [a, b]), len(history(page))
    run(page, """([a]) => window.app._dockDropDistro({ type: 'distro', distroId: 'sl' },
        { kind: 'screen', layerId: a })""", [a])
    assert_refused(page, [a, b], before, h0)


def test_the_plug_drop_refuses_a_locked_group_member(page):
    a, b = walls(page)
    before, h0 = state(page, [a, b]), len(history(page))
    run(page, """([a]) => window.app._dockDropPlug(
        { type: 'plug', distroId: 'sl', output: 'face:r1', title: 'SL Socapex' },
        { kind: 'screen', layerId: a })""", [a])
    assert_refused(page, [a, b], before, h0)


def test_the_slot_drop_refuses_a_locked_group_member(page):
    a, b = walls(page)
    before, h0 = state(page, [a, b]), len(history(page))
    run(page, """([a]) => {
        const app = window.app, l = window.__nf.layer(a);
        const rec = app._powerNaming(l).socas.get(1);
        app._dockDropSlot({ type: 'slot', distroId: 'sl', number: 1, title: 'SL 1' },
            { kind: 'run', layerId: a, socaIndex: 1, num: rec.circuits[0] });
    }""", [a])
    assert_refused(page, [a, b], before, h0)


def test_the_circuit_pip_drop_refuses_a_locked_group_member(page):
    a, b = walls(page)
    before, h0 = state(page, [a, b]), len(history(page))
    run(page, """([a]) => {
        const app = window.app, l = window.__nf.layer(a);
        const rec = app._powerNaming(l).socas.get(1);
        app._dockDropTail({ type: 'tail', distroId: 'sl', number: '1', tail: 1, title: 'SL 1' },
            { kind: 'run', layerId: a, num: rec.circuits[0] });
    }""", [a])
    assert_refused(page, [a, b], before, h0)


def test_the_tray_unplug_and_clear_refuse_a_locked_group_member(page):
    """The tray's Unplug multi / Clear distro (_clearMultis), the slot
    dragged back onto the tray, and the circuit chip's clear. A is one
    column, so its one multi is one circuit and each clear takes it off SL."""
    a, b = walls(page, {1: 'sl'}, columns=1)
    assert page.evaluate("""([a]) => { const app = window.app; app._circuitTailCache = null;
        return app._powerNaming(window.__nf.layer(a)).socas.get(1).circuits.length; }""", [a]) == 1
    before, h0 = state(page, [a, b]), len(history(page))
    run(page, """([a]) => window.app._clearMultis([{ layerId: a, soca: 1 }], 'Unplug Multi')""", [a])
    assert_refused(page, [a, b], before, h0)
    errors_on(page)
    run(page, """() => window.app._dockDropSlot(
        { type: 'slot', distroId: 'sl', number: 1, title: 'SL 1' }, { kind: 'dock' })""", [a])
    assert_refused(page, [a, b], before, h0)
    errors_on(page)
    run(page, """([a]) => {
        const app = window.app, l = window.__nf.layer(a);
        const rec = app._powerNaming(l).socas.get(1);
        app._clearCircuitChip(l, 1, rec.circuits[0]);
    }""", [a])
    assert_refused(page, [a, b], before, h0)


def test_a_circuit_off_a_multi_that_stays_on_the_distro_is_refused_too(page):
    """A's multi has two circuits: clearing one leaves the rest on SL, so
    B's packing would not move. Round 6: A is a member of a half-locked
    group, so it is locked as well, and the clear is refused, B named."""
    a, b = walls(page, {1: 'sl'})
    before, h0 = state(page, [a, b]), len(history(page))
    out = run(page, """([a]) => {
        const app = window.app, l = window.__nf.layer(a);
        app._circuitTailCache = null;
        const rec = app._powerNaming(l).socas.get(1);
        app._clearCircuitChip(l, 1, rec.circuits[rec.circuits.length - 1]);
        return rec.circuits.length;
    }""", [a])
    assert out >= 2, out
    assert_refused(page, [a, b], before, h0)
    assert capacity(page, b)['pct'] == 1


def test_merging_a_split_back_refuses_a_locked_group_member(page):
    """A's multi split in two: the head on SL, the split-off part on SR, so
    B packs at 80%. Merging back keeps the head's identity and drops SR,
    which would put B at 100%: refused."""
    a, b = walls(page, columns=8)
    # A is held by the half-locked group, so Split Multi itself refuses it:
    # the split is laid on as a file would carry it (the split's own store
    # moves, _splitSocaApply).
    out = run(page, """([a]) => {
        const app = window.app, l = window.__nf.layer(a);
        const done = !!app._splitSocaApply(l, 1, 1);
        app.updateLayers([l]);
        return done;
    }""", [a])
    assert out, 'the split under test did not happen'
    page.evaluate("""([a]) => {
        const app = window.app;
        window.__nf.layer(a).powerSocaDistro = { 1: 'sl', 2: 'sr' };
        app._circuitTailCache = null;
    }""", [a])
    assert capacity(page, b)['pct'] == 0.8
    errors_on(page)
    before, h0 = state(page, [a, b]), len(history(page))
    out = run(page, "([a]) => window.app.unsplitSocaAfter(window.__nf.layer(a), 1)", [a])
    assert out is False
    assert_refused(page, [a, b], before, h0)


def test_a_distro_system_change_by_voltage_refuses_a_locked_group_member(page):
    """An old caller's voltage / phase patch moving the distro to a UK/EU
    system is checked as the system patch is."""
    a, b = walls(page, {1: 'sr'})
    assert capacity(page, b)['pct'] == 0.8
    before, h0 = state(page, [a, b]), len(history(page))
    out = run(page, "() => window.app.updateDistro('sr', { voltage: 230, phase: 3 })", [a])
    assert out is None
    assert_refused(page, [a, b], before, h0)


# ── the locked screen itself ─────────────────────────────────────────────

def test_actions_on_a_locked_screen_itself_are_refused(page):
    (lk,) = make(page, [{'name': 'LK', 'columns': 4,
                         'props': dict(SHARING_OFF, locked=True)}])
    set_distros(page, [_distro('sl', 'SL', breakers100=True), _distro('sr', 'SR')],
                {lk: {1: 'sl'}})
    errors_on(page)
    before, h0 = state(page, [lk]), len(history(page))
    assert run(page, "() => window.app.removeDistro('sl')", [lk]) is False
    assert_refused(page, [lk], before, h0, names=('LK',))
    errors_on(page)
    assert run(page, """([id]) => window.app.setSocaDistro(window.__nf.layer(id), 1, 'sr')
        .length""", [lk]) == 0
    assert_refused(page, [lk], before, h0, names=('LK',))


# ── unlocked screens are unaffected ──────────────────────────────────────

def test_the_same_actions_take_when_the_group_member_is_unlocked(page):
    a, b = walls(page, {1: 'sl'}, b_locked=False)
    h0 = len(history(page))
    out = run(page, """([a]) => window.app.setSocaDistro(window.__nf.layer(a), 1, 'sr')
        .map(l => l.name)""", [a])
    assert out == ['A'], out
    assert capacity(page, b)['pct'] == 0.8
    assert run(page, "() => window.app.removeDistro('sr')", [a]) is True
    assert page.evaluate("([a]) => window.__nf.layer(a).powerSocaDistro", [a]) == {}
    assert len(history(page)) == h0 + 2, history(page)
    assert errors(page)['locked'] == [], errors(page)


def test_a_locked_screen_the_action_does_not_repack_does_not_block_it(page):
    """C is locked on SR, in no group with A: moving A's multi off SL, or
    removing SL, leaves C's packing as it was, so both take."""
    a, c = make(page, [{'name': 'A', 'columns': 4, 'props': SHARING_OFF},
                       {'name': 'C', 'columns': 4, 'x': 1000,
                        'props': dict(SHARING_OFF, locked=True)}])
    set_distros(page, [_distro('sl', 'SL', breakers100=True), _distro('sr', 'SR')],
                {a: {1: 'sl'}, c: {1: 'sr'}})
    errors_on(page)
    h0 = len(history(page))
    out = run(page, """([a]) => window.app.setSocaDistro(window.__nf.layer(a), 1, null)
        .map(l => l.name)""", [a])
    assert out == ['A'], out
    assert run(page, "() => window.app.removeDistro('sl')", [a]) is True
    assert len(history(page)) == h0 + 2, history(page)
    assert errors(page)['locked'] == [], errors(page)


def test_a_move_that_keeps_the_locked_members_packing_is_refused_too(page):
    """A from SL onto another 100% rated distro would leave B at 100%.
    Round 6: A is a member of a half-locked group, so it is locked as
    well, and the move is refused, B named."""
    a, b = make(page, [{'name': 'A', 'columns': 4, 'props': SHARING_OFF},
                       {'name': 'B', 'columns': 4, 'x': 800,
                        'props': dict(SHARING_OFF, locked=True)}], group=True)
    set_distros(page, [_distro('sl', 'SL', breakers100=True),
                       _distro('eu', 'EU', '230/400')], {a: {1: 'sl'}})
    errors_on(page)
    before, h0 = state(page, [a, b]), len(history(page))
    out = run(page, """([a]) => window.app.setSocaDistro(window.__nf.layer(a), 1, 'eu')
        .map(l => l.name)""", [a])
    assert out == [], out
    assert_refused(page, [a, b], before, h0)
    assert capacity(page, b)['pct'] == 1
