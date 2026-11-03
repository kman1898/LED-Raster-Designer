"""Crowding is flagged on every surface, and they agree (the owner's
rulings, round 7, 2026-10-23).

1. (a) A hidden screen's multi already too big for its one-circuit output,
       plus a visible screen pinned onto that output: the tray and the
       distro checks say the crowd line too (they said nothing; the pull
       sheet and the distro sheet already flagged it), naming the hidden
       holder.
   (b) A visible screen pinned onto a Socapex a hidden screen fills is
       dealt past the box's six sockets. The distro checks say it, naming
       the hidden holder, the tray says it once in the same words, and the
       pull box and the distro sheet flag it. The same with both screens
       showing (the older behavior).
   (c) Two VISIBLE screens on a one-circuit output: the tray and the
       checks say it (kept, it matches the paperwork).
2. The crowd dialog's lock note names the LOCKED screen: an unlocked
   member of a half-locked group is held by its group's locked member.
5. The crowd dialog says when the screen is hidden, as the tray does.

The show is test_distro_rulings_1018's: WALL A (10 x 6, six circuits, one
multi) before WALL B (6 x 3) in the layer list, on PD: TRUE1 x 3 (outputs
1-3, direct) then Socapex x 2 (outputs 4-5).

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_r7_crowding.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_distro_rulings_1018 import (  # noqa: E402,F401 - fixtures
    _guard, page, seeded, ev, FACE, WALLS, MODAL_JS, RAISE_TRUE1, _state,
)
from test_r6_hidden_slots import setup, HIDDEN  # noqa: E402


# Every surface's word on PD, for output `arg`: the distro checks, the tray
# strip, the pull sheet's box and home-run row, the distro sheet's lines.
SURFACES_JS = """
    app._circuitTailCache = null;
    const d = app.getDistros()[0];
    app.renderHardwareDock();
    const caught = [];
    const orig = app._bKvLines;
    app._bKvLines = function (book, title, pairs) {
        if (title === 'Distro') caught.push(pairs.map(p => p.slice()));
        return orig.apply(this, arguments);
    };
    try {
        app.planBinder(Object.assign(app.readBinderOptions(),
            { scope: { kind: 'show' }, hardware: true, pull: false, cover: false }));
    } finally { app._bKvLines = orig; }
    const list = app.buildPullList();
    const box = (list.byScreen[B.id].boxes || []).find(b => b.number === arg) || {};
    const hw = list.hardware.find(h => h.kind === 'distro') || { rows: [] };
    return {
        checks: app.distroChecks(d).map(w => w.text),
        strip: (app._dockPowerWarnings || []).map(w => w.text),
        crowded: box.crowded || 0,
        overfull: box.overfull || null,
        rows: hw.rows.filter(r => r.label === box.name).map(r => [r.type, r.notes]),
        binder: (caught[0] || []).filter(([k]) => k === 'Crowded' || k === 'Over capacity'),
        planB: app.getSocaPlan(B).map(s => [s.number, s.legs.map(g => g.leg)]),
    };"""


# ── 1(a). a hidden multi too big for its one-circuit output ──────────────

def test_a_hidden_multi_past_its_one_circuit_output_is_said_on_the_tray_and_checks(seeded):
    """WALL A (hidden) has its six-circuit multi pinned on PD1, a TRUE1;
    WALL B's one circuit is pinned onto PD1 too. A's own "on a TRUE1" line
    is never said (a hidden screen's circuits are not on the distro's
    list), so the crowd line is, naming A."""
    pg, errors = seeded
    one = {'powerSocaSplits': [1], 'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1}}
    setup(pg, distros=[FACE], walls={
        'a': dict({'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1}}, **HIDDEN),
        'b': one})
    out = ev(pg, SURFACES_JS, 1)
    said = ('PD1 TRUE1 carries 7 circuits, and it takes one circuit only. '
            'Move one to a multi output. WALL A is hidden and still holds it.')
    assert said in out['checks'], out['checks']
    assert out['strip'].count(said) == 1, out['strip']
    # the paperwork already said it, and still does
    assert out['crowded'] == 7, out
    assert out['binder'] == [['Crowded', 'PD1 TRUE1 carries 7 circuits · a multi on a '
                              'one-circuit output, move it to a multi output']], out['binder']
    assert not errors, errors


def test_a_visible_multi_past_its_output_keeps_its_own_line_only(seeded):
    """The same with WALL A showing: A's own line names it, and the crowd
    line is not said twice over."""
    pg, errors = seeded
    one = {'powerSocaSplits': [1], 'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1}}
    setup(pg, distros=[FACE], walls={
        'a': {'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1}}, 'b': one})
    out = ev(pg, SURFACES_JS, 1)
    own = [t for t in out['checks'] if t.startswith("WALL A's 6 circuits are on PD1")]
    assert len(own) == 1, out['checks']
    assert not [t for t in out['checks'] if 'carries 7 circuits, and it takes' in t], out['checks']
    assert not [t for t in out['checks'] if 'hidden' in t], out['checks']
    assert out['crowded'] == 7, out
    assert not errors, errors


# ── 1(b). a multi box past its six sockets ───────────────────────────────

def test_a_visible_screen_pinned_onto_a_hidden_screens_socapex_is_flagged_everywhere(seeded):
    """WALL A (hidden) fills PD4, a Socapex, with its six circuits; WALL B's
    three-circuit multi is pinned onto PD4 (setSocaNumber). B is dealt
    past the sixth socket, and every surface says so, naming A."""
    pg, errors = seeded
    setup(pg, distros=[FACE], walls={
        'a': dict({'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 4}}, **HIDDEN),
        'b': {'powerSocaSplits': [3], 'powerSocaDistro': {'1': 'd1'},
              'powerSocaLengths': {'1': '60'}}})
    ev(pg, "app.setSocaNumber(B, 1, 4); return null;")
    pg.wait_for_function("() => window.app._layerSavesSettled()")
    out = ev(pg, SURFACES_JS, 4)
    assert out['planB'] == [[4, [7, 8, 9]]], out['planB']
    said = 'PD4 has more circuits than the six a Socapex 208V holds. WALL A is hidden and still holds it.'
    assert said in out['checks'], out['checks']
    assert out['strip'].count(said) == 1, out['strip']
    assert out['overfull'] == {'circuits': 9, 'size': 6}, out
    assert out['crowded'] == 0, 'a multi box is not a crowded direct output'
    assert ['Multi', '9 circuits on a six-circuit output'] in out['rows'], out['rows']
    assert out['binder'] == [['Crowded', 'PD4 Socapex 208V carries 9 circuits · more than the six '
                              'it holds, move a multi to another output']], out['binder']
    assert not errors, errors


def test_two_visible_screens_past_a_socapex_are_flagged_everywhere(seeded):
    """Both showing, both pinned on PD4: the same lines, no hidden clause."""
    pg, errors = seeded
    pin = {'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 4}}
    setup(pg, distros=[FACE], walls={'a': pin, 'b': dict(pin, powerSocaSplits=[3])})
    out = ev(pg, SURFACES_JS, 4)
    said = 'PD4 has more circuits than the six a Socapex 208V holds.'
    assert said in out['checks'], out['checks']
    assert out['strip'].count(said) == 1, out['strip']
    assert out['overfull'] == {'circuits': 9, 'size': 6}, out
    assert out['binder'] == [['Crowded', 'PD4 Socapex 208V carries 9 circuits · more than the six '
                              'it holds, move a multi to another output']], out['binder']
    assert not errors, errors


def test_a_socapex_within_its_six_and_one_only_hidden_screens_fill_are_not_flagged(seeded):
    pg, errors = seeded
    # WALL A's six alone on PD4: full, not past it
    setup(pg, distros=[FACE], walls={'a': {'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 4}},
                                     'b': {'powerSocaSplits': [3], 'powerSocaDistro': {'1': 'd1'},
                                           'powerSocaNumber': {'1': 5}}})
    out = ev(pg, SURFACES_JS, 5)
    assert not [t for t in out['checks'] + out['strip'] if 'more circuits than' in t], out
    assert out['overfull'] is None and out['binder'] == [], out
    # both on PD4 and both hidden: on no paper, so said nowhere
    pin = {'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 4}}
    setup(pg, distros=[FACE], walls={'a': dict(pin, **HIDDEN), 'b': dict(pin, powerSocaSplits=[3], **HIDDEN)})
    out = ev(pg, """app._circuitTailCache = null; const d = app.getDistros()[0];
        app.renderHardwareDock();
        return { ov: app._boxOverflows(d).length, checks: app.distroChecks(d).map(w => w.text),
                 strip: (app._dockPowerWarnings || []).map(w => w.text) };""")
    assert out['ov'] == 0, out
    assert not [t for t in out['checks'] + out['strip'] if 'more circuits than' in t], out
    assert not errors, errors


# ── 1(c). two visible screens on a one-circuit output (kept) ─────────────

def test_two_visible_screens_on_a_one_circuit_output_are_said_on_the_tray_and_checks(seeded):
    pg, errors = seeded
    one = {'powerSocaSplits': [1], 'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1}}
    setup(pg, distros=[FACE], walls={'a': one, 'b': one})
    out = ev(pg, SURFACES_JS, 1)
    said = ('PD1 TRUE1 carries 2 circuits, and it takes one circuit only. '
            'Move one to a multi output.')
    assert said in out['checks'], out['checks']
    assert out['strip'].count(said) == 1, out['strip']
    assert out['crowded'] == 2, out
    assert out['binder'] == [['Crowded', 'PD1 TRUE1 carries 2 circuits · a multi on a '
                              'one-circuit output, move it to a multi output']], out['binder']
    assert not errors, errors


# ── 2. the crowd dialog names the locked screen ──────────────────────────

GROUP_JS = """
    app.project.groups = [{ id: 'gR7', name: 'WALL', layer_ids: [A.id, B.id] }];
    A.group_id = 'gR7'; B.group_id = 'gR7';
    app._circuitTailCache = null;
    return null;"""

UNGROUP_JS = """
    document.getElementById('crowd-modal')?.remove();
    app.project.groups = [];
    delete A.group_id; delete B.group_id;
    A.locked = false; B.locked = false;
    app._circuitTailCache = null;
    return null;"""


def test_the_crowd_dialog_names_the_locked_member_of_a_half_locked_group(seeded):
    """WALL A (unlocked) and WALL B (locked) are one group, an old file's
    half-locked group, so A is held by B. Raising PD4 to a TRUE1 would
    crowd A's six-circuit multi: Cancel only, and the note names B, the
    screen that is locked. (B's cabinets draw other watts, so each screen
    walks its own circuits.)"""
    pg, errors = seeded
    setup(pg, distros=[FACE], walls={'a': WALLS['a'],
                                     'b': dict(WALLS['b'], locked=True, panelWatts=150)})
    try:
        ev(pg, GROUP_JS)
        before = _state(pg)
        ev(pg, RAISE_TRUE1)
        modal = pg.evaluate(MODAL_JS)
        assert modal['buttons'] == ['Cancel the change'], modal
        assert modal['locked'] == ("WALL B is locked, so WALL A's multi cannot come off. "
                                   'Unlock to take it off, or cancel the change.'), modal
        pg.locator('#crowd-modal .crowd-cancel').click()
        pg.wait_for_timeout(200)
        assert _state(pg) == before
        # a screen locked itself keeps the old note
        ev(pg, UNGROUP_JS)
        setup(pg, distros=[FACE], walls={'a': dict(WALLS['a'], locked=True), 'b': WALLS['b']})
        ev(pg, RAISE_TRUE1)
        modal = pg.evaluate(MODAL_JS)
        assert modal['locked'] == ('WALL A is locked, so its multi cannot come off. '
                                   'Unlock to take it off, or cancel the change.'), modal
        pg.locator('#crowd-modal .crowd-cancel').click()
        pg.wait_for_timeout(200)
    finally:
        ev(pg, UNGROUP_JS)
    assert not errors, errors


# ── 5. the crowd dialog says the screen is hidden ────────────────────────

def test_the_crowd_dialog_says_a_visible_screen_is_not_hidden(seeded):
    pg, errors = seeded
    setup(pg, distros=[FACE], walls=WALLS)
    ev(pg, RAISE_TRUE1)
    modal = pg.evaluate(MODAL_JS)
    assert ("WALL A's 6-circuit multi is on PD4. PD4 would become a TRUE1, "
            "which carries one circuit.") in modal['text'], modal['text']
    assert 'hidden' not in modal['text'], modal['text']
    pg.locator('#crowd-modal .crowd-cancel').click()
    pg.wait_for_timeout(200)
    assert not errors, errors
