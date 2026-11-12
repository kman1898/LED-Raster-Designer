"""The owner's power rulings of 2026-11-12.

1. Edison follows the screen's Amperage: "if I choose 20 amps, then it
   should be 5-20. If I choose 15, it should be 5-15." A Multi -> Edison
   screen's outlet is a 5-15 (12 A continuous, 80% of 15 A) under 20 A and
   a 5-20 (16 A, 80% of 20 A) at 20 A or more; the Amperage select offers
   only 15 A and 20 A on it, and the name shows on the sidebar, the
   circuit cables, the pull sheet and the binder. An old show maps from
   the Amperage it was saved with.
2. Breaker source: "the side panel amperage for the screen is without the
   distro attached, but it should be what a real one would be plugged
   into." Circuits plugged into a distro output pack and check against
   that output's breaker (an Edison output held to its 5-15 or 5-20, the
   L21-30 Edison box at 15 A a circuit); the Amperage box counts only on
   no distro, and the power info line says where the output wins.
3. A screen on no distro packs by ONE rule at every voltage: 80% of its
   breaker, 240 V the same as 208 V and 110 V.
4. Unplugging a source in the middle of a screen leaves a hole (the
   circuits after it do not shift), and "Reset these circuits" closes it
   in one undo step, refused on a locked screen.

Every expected figure is worked from the formula in the comment beside it.

Run locally:
    "C:/Users/Blue Iris/.venvs/led-raster/Scripts/python.exe" -m pytest tests/test_power_rulings_1112.py -n 4 --dist loadfile
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_power_mixed_sources import (  # noqa: E402,F401 - fixtures
    _guard, page, seeded, setup, ev, PLUG_DROP, CIRCUITS,
)

# A 110 V Edison wall: 10 x 6 cabinets of 300 W.
EDISON = {'columns': 10, 'rows': 6, 'powerVoltage': 110, 'panelWatts': 300,
          'powerBreakoutType': 'soca-edison'}

CAP = """
    app._circuitTailCache = null;
    const c = app.circuitCapacity(A);
    const et = app.screenEdisonType(A);
    app.selectLayer(A);
    app.loadLayerToInputs && app.loadLayerToInputs();
    app.updatePowerCapacityDisplay();
    const sel = document.getElementById('power-amperage-select');
    const src = document.getElementById('power-amperage-source');
    return { breakerA: c.breakerA, amps: c.amps, pct: c.pct, watts: c.watts,
             edison: et ? et.id : null,
             n: app.screenCircuits(A).map(x => x.panels.length),
             usable: document.getElementById('power-amperage-usable').textContent,
             offered: [...sel.options].filter(o => !o.hidden && !o.dataset.mixed).map(o => o.value),
             value: sel.value,
             source: src.style.display === 'none' ? '' : src.textContent,
             why: app.circuitPctReason(A) };
"""


def soca120(rows=4, breaker=20, extra=None):
    """A 120/208 face distro with Socapex 120V rows (line to neutral)."""
    out = [{'id': 'r1', 'connector': 'soca', 'count': rows, 'coupling': 'ln', 'breakerA': breaker}]
    out += extra or []
    return {'id': 'g1', 'name': 'VX', 'system': '120/208', 'voltage': 208, 'phase': 3,
            'input': 'cam400', 'ratingA': 400, 'outputRows': out}


# ── 1. Edison follows the screen's Amperage ─────────────────────────────

def test_an_edison_15a_screen_packs_to_12a_and_reads_5_15(seeded):
    """15 A: a 5-15 outlet, 80% of 15 A = 12 A, 110 x 12 = 1,320 W a
    circuit, floor(1320 / 300) = 4 cabinets: 60 cabinets make 15
    circuits."""
    pg, errors = seeded
    setup(pg, wall=dict(EDISON, powerAmperage=15))
    out = ev(pg, CAP)
    assert out['edison'] == '5-15'
    assert out['amps'] == pytest.approx(12) and out['watts'] == pytest.approx(1320)
    assert out['n'] == [4] * 15, out['n']
    assert out['usable'] == '15 A breaker · 12 A usable · Edison 5-15'
    # an Edison outlet comes in 15 A and 20 A only
    assert out['offered'] == ['15', '20'] and out['value'] == '15', out
    assert out['source'] == ''
    assert not errors, errors


def test_an_edison_20a_screen_packs_to_16a_and_reads_5_20(seeded):
    """20 A: a 5-20 outlet, 80% of 20 A = 16 A, 110 x 16 = 1,760 W,
    floor(1760 / 300) = 5 cabinets: 60 cabinets make 12 circuits."""
    pg, errors = seeded
    setup(pg, wall=dict(EDISON, powerAmperage=20))
    out = ev(pg, CAP)
    assert out['edison'] == '5-20'
    assert out['amps'] == pytest.approx(16) and out['watts'] == pytest.approx(1760)
    assert out['n'] == [5] * 12, out['n']
    assert out['usable'] == '20 A breaker · 16 A usable · Edison 5-20'
    assert out['offered'] == ['15', '20'] and out['value'] == '20', out
    assert not errors, errors


def test_the_edison_name_on_cables_the_pull_sheet_and_the_binder(seeded):
    """A 15 A Edison wall, its first multi on VX's Socapex 120V output 1.
    The circuit's cable reads "10' Edison 5-15", the pull sheet's breakout
    and adapter rows say 5-15, and the binder's box reads it too."""
    pg, errors = seeded
    setup(pg, distros=[soca120()], wall=dict(EDISON, powerAmperage=15))
    assert ev(pg, PLUG_DROP, {'distro': 'g1', 'output': 'face:r1'})['steps'] == 1
    out = ev(pg, """
        app.setCircuitCable(A, 1, { ft: 10 });
        app._circuitTailCache = null;
        const list = app.buildPullList();
        const rows = list.positions.flatMap(p => p.rows || []);
        return { cable: app.powerCircuitCable(A, 1).text,
                 types: rows.map(r => r.type),
                 cableRows: rows.filter(r => r.type === 'Edison 5-15').map(r => r.length) };""")
    assert out['cable'] == "10' Edison 5-15", out
    assert 'Edison 5-15 Breakout' in out['types'], out['types']
    assert 'Edison 5-15 → TRUE1 cable' in out['types'], out['types']
    assert "10'" in out['cableRows'], out
    assert not [t for t in out['types'] if t in ('Edison Breakout', 'Edison → TRUE1 cable')], out['types']
    texts = ev(pg, """
        const opts = { sheet: 'tabloid', palette: 'colour', sides: { power: true, data: false },
                       scope: { kind: 'show' }, cover: false, pull: true, hardware: true, wiring: false };
        const plan = app.planBinder(opts);
        const out = [];
        for (let i = 0; i < plan.length; i++) {
            const r = app.renderBinderPage(opts, i);
            r.record.ops.filter(o => o.op === 'text').forEach(o => out.push(String(o.text)));
        }
        return out.join(' | ');""")
    assert 'Edison 5-15' in texts, texts[:3000]
    assert not errors, errors


def test_an_old_show_maps_from_its_saved_amperage(seeded):
    """Nothing is written on open; the outlet is read from the Amperage:
      16 A: under 20 A, a 5-15. 80% of 16 A = 12.8 A, held to the 5-15's
            12 A: 1,320 W, 4 cabinets a circuit, 15 circuits.
      20 A: a 5-20, 16 A (the 20 A test above).
      30 A: a 5-20 behind a 30 A breaker. 80% of 30 A = 24 A, held to the
            5-20's 16 A: 1,760 W, 5 cabinets, 12 circuits (it packed 24 A
            = 2,640 W, 8 cabinets, before). The breaker is past the
            outlet's 20 A: OVER on the Amperage. The select keeps Custom
            (30) until somebody picks 15 or 20."""
    pg, errors = seeded
    setup(pg, wall=dict(EDISON, powerAmperage=16))
    out = ev(pg, CAP)
    assert out['edison'] == '5-15' and out['amps'] == pytest.approx(12), out
    assert out['n'] == [4] * 15
    assert ev(pg, "return A.powerAmperage;") == 16, 'nothing written'
    setup(pg, wall=dict(EDISON, powerAmperage=30))
    out = ev(pg, CAP)
    assert out['edison'] == '5-20' and out['breakerA'] == 30, out
    assert out['amps'] == pytest.approx(16), out
    assert out['n'] == [5] * 12, out['n']
    assert out['offered'] == ['15', '20', 'custom'] and out['value'] == 'custom', out
    over = ev(pg, """
        const hit = app.breakerOverChecks(A);
        return { item: hit.length ? hit[0].item : null, rating: hit.length ? hit[0].ratingA : null,
                 shown: document.getElementById('power-amperage-over').textContent };""")
    assert over['item'] == 'Edison 5-20' and over['rating'] == 20, over
    assert over['shown'] == 'OVER: 30 A breaker on Edison 5-20 (20 A)', over
    assert ev(pg, "return A.powerAmperage;") == 30
    assert not errors, errors


# ── 2. the breaker the circuits are plugged into ─────────────────────────

def test_a_20a_screen_on_a_5_15_output_packs_to_12a_and_says_so(seeded):
    """A 20 A Edison wall (a 5-20 at the screen, 16 A, 5 cabinets a
    circuit) with its first circuit plugged into VX output 5, an Edison
    output picked 5-15 on a 20 A breaker. The output wins: 5-15 is 15 A,
    80% = 12 A, 1,320 W, 4 cabinets a circuit, 15 circuits."""
    pg, errors = seeded
    face = soca120(extra=[{'id': 'r2', 'connector': 'edison', 'count': 6, 'coupling': 'ln',
                           'breakerA': 20, 'edisonType': '5-15'}])
    setup(pg, distros=[face], wall=dict(EDISON, powerAmperage=20))
    assert ev(pg, CAP)['n'] == [5] * 12
    # circuit 1 on its own multi, pinned to output 5 (the first Edison)
    out = ev(pg, """
        A.powerSocaSplits = [1];
        A.powerSocaDistro = { 1: 'g1' };
        A.powerSocaNumber = { 1: 5 };
        app._circuitTailCache = null;
    """ + CAP)
    assert out['breakerA'] == 15 and out['amps'] == pytest.approx(12), out
    assert out['n'] == [4] * 15, out['n']
    assert out['source'] == ('Circuit 1 uses VX output 5 (Edison 5-15, 15 A). Its circuits are on '
                             '15 A breakers, not the 20 A Amperage, which counts only on no distro.'), out
    assert not errors, errors


def test_a_15a_screen_on_20a_socapex_packs_to_16a(seeded):
    """A 110 V TRUE1 wall typed 15 A (12 A, 1,320 W, 4 cabinets of 300 W)
    plugged into VX's 20 A Socapex: the circuits are on 20 A breakers, 80%
    = 16 A, 1,760 W, 5 cabinets a circuit, 12 circuits. Unplugged, back
    to the Amperage: 15 circuits of 4."""
    pg, errors = seeded
    setup(pg, distros=[soca120()], wall=dict(EDISON, powerAmperage=15, powerBreakoutType='soca-true1'))
    assert ev(pg, CAP)['n'] == [4] * 15
    ev(pg, PLUG_DROP, {'distro': 'g1', 'output': 'face:r1'})
    out = ev(pg, CAP)
    assert out['breakerA'] == 20 and out['amps'] == pytest.approx(16), out
    assert out['n'] == [5] * 12, out['n']
    assert out['usable'] == '20 A breaker · 16 A usable'
    assert out['source'].startswith('Circuits 1 to 6 use VX output 1 (Socapex, 20 A).'), out
    # the breaker check reads the same breaker: a full circuit, 5 x 300 =
    # 1,500 W / 110 = 13.64 A, is under 16 A, so nothing is OVER
    checks = ev(pg, "return app.distroChecks(app.getDistros()[0]).map(c => c.text);")
    assert not [t for t in checks if 'breaker' in t], checks
    out = ev(pg, "app.setSocaDistro(A, 1, null); app._circuitTailCache = null;" + CAP)
    assert out['breakerA'] == 15 and out['n'] == [4] * 15, out
    assert out['source'] == ''
    assert not errors, errors


def test_a_row_breaker_change_never_repacks_a_locked_screen(seeded):
    """The output's breaker moves what a plugged screen packs to, so a
    locked screen on it holds the change back (owner, 2026-10-16: a locked
    screen stays unchanged until unlocked, and says why). The wall of the
    test above, locked, on VX's 20 A Socapex (16 A, 12 circuits of 5): VX's
    row taken to 15 A is refused whole, the screen named, and the wall
    keeps its 12 circuits. Unlocked, the same change repacks it to 15 A,
    12 A, 1,320 W, 4 cabinets a circuit, 15 circuits."""
    pg, errors = seeded
    setup(pg, distros=[soca120()], wall=dict(EDISON, powerAmperage=15, powerBreakoutType='soca-true1'))
    ev(pg, PLUG_DROP, {'distro': 'g1', 'output': 'face:r1'})
    out = ev(pg, """
        const toasts = [];
        const real = app._toast.bind(app);
        app._toast = (m, err, ms) => { if (err) toasts.push(m); return real(m, err, ms); };
        A.locked = true;
        const d = app.getDistros()[0];
        const rows = d.outputRows.map(r => Object.assign({}, r, { breakerA: 15 }));
        let res;
        try { res = app.updateDistro('g1', { outputRows: rows }); } finally { app._toast = real; }
        app._circuitTailCache = null;
        return { res: res === null, toasts, breaker: app.getDistros()[0].outputRows[0].breakerA,
                 n: app.screenCircuits(A).map(c => c.panels.length) };""")
    assert out['res'] and out['breaker'] == 20, out
    assert out['toasts'] == ['WALL A is locked, and this would repack its circuits. Unlock it to change it.'], out
    assert out['n'] == [5] * 12
    out = ev(pg, """
        A.locked = false;
        const d = app.getDistros()[0];
        app.updateDistro('g1', { outputRows: d.outputRows.map(r => Object.assign({}, r, { breakerA: 15 })) });
        app._circuitTailCache = null;
        return app.screenCircuits(A).map(c => c.panels.length);""")
    assert out == [4] * 15, out
    assert not errors, errors


def test_a_mixed_source_on_the_l2130_edison_box_packs_to_12a(seeded):
    """A 208 V TRUE1 wall at 20 A, 10 x 6 cabinets of 400 W, its first
    multi on a Socapex 208V output: 208 x 20 x 80% = 3,328 W, 8 cabinets a
    circuit. The L21-30 Edison box (output row breaker 30 A) dropped on
    next: its circuits are 15 A each, whatever the row's 30 A and the
    screen's 20 A say - 110 x 15 x 80% = 1,320 W, 3 cabinets, 1,200 / 110
    = 10.909 A a circuit, never past 12 A."""
    pg, errors = seeded
    face = {'id': 'g1', 'name': 'VX', 'system': '120/208', 'voltage': 208, 'phase': 3,
            'input': 'cam400', 'ratingA': 400,
            'outputRows': [{'id': 'r1', 'connector': 'soca', 'count': 2, 'coupling': 'll', 'breakerA': 20},
                           {'id': 'r2', 'connector': 'l2130e', 'count': 2, 'coupling': 'ln', 'breakerA': 30}]}
    setup(pg, distros=[face], wall={'columns': 10, 'rows': 6, 'powerBreakoutType': 'soca-true1'})
    ev(pg, PLUG_DROP, {'distro': 'g1', 'output': 'face:r1'})
    assert ev(pg, PLUG_DROP, {'distro': 'g1', 'output': 'face:r2'})['steps'] == 1
    out = ev(pg, """
        app._circuitTailCache = null;
        const plan = app.getSocaPlan(A);
        const spec = app.powerSpecAt(A, 7);
        return { n: app.screenCircuits(A).map(c => c.panels.length),
                 breakerA: spec.breakerA, usable: app.specUsableA(spec, app.circuitCapacity(A).pct),
                 amps: plan.slice(1).flatMap(s => s.legs.map(l => l.amps)) };""")
    assert out['n'] == [8] * 6 + [3] * 4, out['n']
    assert out['breakerA'] == 15 and out['usable'] == pytest.approx(12), out
    assert out['amps'] == pytest.approx([1200 / 110] * 4)
    assert max(out['amps']) <= 12
    assert not errors, errors


# ── 3. one rule on no distro ─────────────────────────────────────────────

def test_240_208_and_110_on_no_distro_pack_the_same(seeded):
    """No distro, 20 A, in a show whose only distro is UK/EU (the case
    that differed: 240 V packed to 100% there, 20 x 240 = 4,800 W):
      110 V: 80% of 20 = 16 A, 110 x 16 = 1,760 W
      208 V: 16 A, 208 x 16 = 3,328 W
      240 V: 16 A, 240 x 16 = 3,840 W
    One sentence says the rule at every voltage."""
    pg, errors = seeded
    eu = {'id': 'e1', 'name': 'EU', 'system': '230/400', 'ratingA': 63}
    got = {}
    for volts, watts in ((110, 1760), (208, 3328), (240, 3840)):
        setup(pg, distros=[eu], wall={'powerVoltage': volts, 'powerAmperage': 20,
                                      'powerBreakoutType': 'soca-true1'})
        out = ev(pg, CAP)
        assert out['pct'] == 0.8 and out['watts'] == pytest.approx(watts), (volts, out)
        got[volts] = out['why']
    rule = ('A screen on no distro packs to 80% of its breaker, whatever its voltage, as a US '
            'circuit carries a continuous load. Only 220 and 230 V, the UK/EU figures, pack to the '
            "breaker, unless the show's distros are US.")
    assert got == {110: rule, 208: rule, 240: rule}, got
    tip = ev(pg, "return document.getElementById('power-amperage-usable').title;")
    assert tip == rule
    assert not errors, errors


# ── 4. a hole, and Reset ─────────────────────────────────────────────────

HOLE_FACE = {'id': 'g1', 'name': 'VX', 'system': '120/208', 'voltage': 208, 'phase': 3,
             'input': 'cam400', 'ratingA': 400,
             'outputRows': [{'id': 'r1', 'connector': 'soca', 'count': 4, 'coupling': 'll', 'breakerA': 20},
                            {'id': 'r2', 'connector': 'l2130e', 'count': 2, 'coupling': 'ln', 'breakerA': 30}]}

STATE = """
    app._circuitTailCache = null;
    return { n: app.screenCircuits(A).map(c => c.panels.length),
             src: (A.powerSources || []).map(r => [r.from, r.own ? 'own' : r.breakout]),
             distro: A.powerSocaDistro, number: A.powerSocaNumber,
             holes: app.powerSourceHoles(A).map(h => [h.start, h.end]) };
"""


def _holed(pg):
    """A 208 V TRUE1 wall, 10 x 10 cabinets of 400 W, 20 A: 208 x 20 x 80%
    = 3,328 W, 8 cabinets a circuit.
      Socapex output 1 takes multi 1, circuits 1-6 (48 cabinets).
      The L21-30 Edison box (output 5) takes over at circuit 7: 110 x 15
      x 80% = 1,320 W, 3 cabinets a circuit, its box circuits 7-12 (18
      cabinets).
      Socapex output 2 takes over at circuit 13, the screen's own again:
      100 - 48 - 18 = 34 cabinets, 8 + 8 + 8 + 8 + 2, circuits 13-17.
    Then the Edison box is unplugged."""
    setup(pg, distros=[HOLE_FACE], wall={'columns': 10, 'rows': 10, 'powerBreakoutType': 'soca-true1'})
    # a fresh history: an earlier test's undo leaves a redo step, and the
    # next step would replace it rather than add one
    ev(pg, "app.resetHistory('Seed');")
    for out in ('face:r1', 'face:r2', 'face:r1'):
        assert ev(pg, PLUG_DROP, {'distro': 'g1', 'output': out})['steps'] == 1, out
    before = ev(pg, STATE)
    assert before['n'] == [8] * 6 + [3] * 6 + [8, 8, 8, 8, 2], before
    assert before['src'] == [[7, 'l2130-edison'], [13, 'own']], before
    assert before['distro'] == {'1': 'g1', '2': 'g1', '3': 'g1'}, before
    assert before['holes'] == []
    ev(pg, "app.setSocaDistro(A, 2, null);")
    pg.wait_for_timeout(300)
    return before


def test_unplugging_a_middle_source_leaves_a_hole(seeded):
    """The box's circuits 7-12 stay where they were, on no distro, and
    the circuits after them do not shift: 13-17 keep 8, 8, 8, 8, 2 on
    Socapex output 2."""
    pg, errors = seeded
    before = _holed(pg)
    after = ev(pg, STATE)
    assert after['n'] == before['n'], after
    assert after['src'] == before['src'], after
    assert after['distro'] == {'1': 'g1', '3': 'g1'}, after
    assert after['holes'] == [[7, 12]], after
    # the right-click on a hole circuit offers the reset; elsewhere none
    menu = ev(pg, """
        const nums = app.screenCircuits(A).map(c => c.num);
        const on = app._resetHoleMenuFor(A, nums[8]);
        return { on: on && on.label, off: app._resetHoleMenuFor(A, nums[13]), first: app._resetHoleMenuFor(A, nums[0]) };""")
    assert menu == {'on': 'Reset these circuits', 'off': None, 'first': None}, menu
    assert not errors, errors


def test_reset_closes_the_hole_and_one_undo_restores_it(seeded):
    """Reset lays circuits 7 on again with the next source's setting, the
    screen's own: 100 - 48 = 52 cabinets at 8 = 8 x 6 + 4, circuits 7-13.
    Socapex output 2's multi moves down from index 3 to 2 and feeds 7-12;
    13 is on no distro. No source is left. One undo puts the hole back."""
    pg, errors = seeded
    before = _holed(pg)
    holed = ev(pg, STATE)
    out = ev(pg, """
        app.resetHistory('Holed');
        const ok = app.resetPowerHole(A, 7);
        app._circuitTailCache = null;
        return { ok, actions: app.history.map(h => h.action) };""")
    assert out == {'ok': True, 'actions': ['Holed', 'Reset Circuits']}, out
    after = ev(pg, STATE)
    assert after['n'] == [8] * 12 + [4], after
    assert after['src'] == [], after
    assert after['distro'] == {'1': 'g1', '2': 'g1'}, after
    assert after['number'] == {'1': 1, '2': 2}, after
    assert after['holes'] == []
    ev(pg, "app.undo();")
    pg.wait_for_timeout(400)
    # (ev reads the screen afresh: undo puts a new layer object in place)
    undone = ev(pg, STATE)
    assert undone == holed, (undone, holed)
    assert undone['n'] == before['n']
    assert not errors, errors


def test_reset_on_a_locked_screen_says_why_and_changes_nothing(seeded):
    pg, errors = seeded
    _holed(pg)
    holed = ev(pg, STATE)
    out = ev(pg, """
        const toasts = [];
        const real = app._toast.bind(app);
        app._toast = (m, err, ms) => { if (err) toasts.push(m); return real(m, err, ms); };
        A.locked = true;
        const before = app.history.length;
        let ok;
        try { ok = app.resetPowerHole(A, 7); } finally { app._toast = real; }
        return { ok, toasts, steps: app.history.length - before };""")
    assert out['ok'] is False and out['steps'] == 0, out
    assert out['toasts'] == ['WALL A is locked. Unlock it to change it.'], out
    assert ev(pg, "A.locked = false;" + STATE) == holed
    assert not errors, errors
