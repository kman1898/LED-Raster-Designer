"""Hidden screens keep their slots (the owner's rulings, round 6, 2026-10-23).

2. A hidden screen's multi numbers and distro outputs stay reserved: a
   visible screen is never dealt onto a hidden screen's outputs or positions,
   it takes the next free one. A visible screen the user pins onto an
   output a hidden screen holds is crowded, and every surface says so: the
   tray, the distro checks, the pull sheet and the distro sheet. Loads
   still leave the hidden screen out (round 5), and a visible screen's own
   direct cable still prints wherever its output is not crowded.
3. The face-edit crowd question still sees hidden screens' multis ("Yes,
   still ask for hidden screens"): the dialog opens, and nothing changes
   until it is answered (the v1.5.3 behavior; round 5 had silenced it).

The show is test_distro_rulings_1018's: WALL A (10 x 6, six circuits, one
multi) before WALL B (6 x 3) in the layer list, on PD: TRUE1 x 3 (outputs
1-3, direct) then Socapex x 2 (outputs 4-5).

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_r6_hidden_slots.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_distro_rulings_1018 import (  # noqa: E402,F401 - fixtures
    _guard, page, seeded, ev, FACE, WALLS, MODAL_JS, RAISE_TRUE1, _state,
)
from test_distro_rulings_1018 import setup as _setup  # noqa: E402


HIDDEN = {'visible': False}


def setup(pg, **o):
    """The module's setup, every screen shown first (it leaves `visible`
    as it found it)."""
    pg.evaluate("() => window.app.project.layers.forEach(l => { l.visible = true; })")
    return _setup(pg, **o)


def plan(pg, who):
    return ev(pg, f"""app._circuitTailCache = null;
        return app.getSocaPlan({who}).map(s => ({{ number: s.number, name: s.name,
            pos: s.legs.map(g => g.leg) }}));""")


# ── 2. a hidden screen keeps its output ──────────────────────────────────

def test_an_auto_multi_is_never_dealt_onto_a_hidden_screens_output(seeded):
    pg, errors = seeded
    feeds = {'powerSocaDistro': {'1': 'd1'}}
    setup(pg, distros=[FACE], walls={'a': dict(feeds, **HIDDEN), 'b': feeds})
    assert plan(pg, 'A')[0]['number'] == 4
    assert plan(pg, 'B')[0]['number'] == 5, 'B was dealt onto hidden WALL A\'s output'
    # an old distro with no face deals numbers: the hidden screen keeps SR1
    old = {'id': 'd2', 'name': 'SR', 'ratingA': 200, 'system': '120/208'}
    feeds = {'powerSocaDistro': {'1': 'd2'}}
    setup(pg, distros=[old], walls={'a': dict(feeds, **HIDDEN), 'b': feeds})
    assert [p['number'] for p in plan(pg, 'A')] == [1]
    assert [p['number'] for p in plan(pg, 'B')][0] == 2
    assert not errors, errors


def test_a_visible_copy_pinned_with_a_hidden_screen_never_takes_its_positions(seeded):
    """WALL A hidden and WALL B both pinned to PD4, a Socapex: A's six
    circuits keep positions 1-6, so B is crowded past them and the tray says
    the box holds more than six."""
    pg, errors = seeded
    pin = {'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 4}}
    setup(pg, distros=[FACE], walls={'a': dict(pin, **HIDDEN), 'b': pin})
    a, b = plan(pg, 'A')[0], plan(pg, 'B')[0]
    assert a['pos'] == [1, 2, 3, 4, 5, 6], a
    assert not set(a['pos']) & set(b['pos']), (a, b)
    strip = ev(pg, "app.renderHardwareDock(); return (app._dockPowerWarnings || []).map(w => w.text);")
    # round 7: the line names the hidden screen that still holds the box
    said = 'PD4 has more circuits than the six a Socapex 208V holds. WALL A is hidden and still holds it.'
    assert strip.count(said) == 1, strip
    assert not errors, errors


CROWD_JS = """
    app._circuitTailCache = null;
    const d = app.getDistros()[0];
    const c = app.getSocaPlan(B)[0].legs[0].circuit;
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
    const box = app.buildPullList().byScreen[B.id].boxes[0];
    const cable = app.directCircuitCable(B, c);
    return {
        crowding: app._faceCrowding(d).map(r => r.number),
        holders: (app._distroMultiNumbers('d1').get(arg) || []).map(m => m.layerName),
        checks: app.distroChecks(d).map(w => w.text),
        strip: (app._dockPowerWarnings || []).map(w => w.text),
        count: app.directOutputCircuitCount(B, c),
        pull: box.crowded || 0,
        binder: (caught[0] || []).filter(([k]) => k === 'Crowded' || k === 'Over capacity'),
        cable: cable ? cable.text : null,
        loads: app.getDistroLoads().filter(l => l.id === 'd1')
            .flatMap(l => l.socas.map(s => s.layer)),
    };"""


def test_a_visible_screen_pinned_onto_a_hidden_screens_output_is_crowded_everywhere(seeded):
    """WALL A (hidden) holds PD1, a TRUE1, with a one-circuit multi; WALL B
    is pinned onto PD1 too. Every surface says PD1 is crowded."""
    pg, errors = seeded
    one = {'powerSocaSplits': [1], 'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1}}
    setup(pg, distros=[FACE], walls={'a': dict(one, **HIDDEN),
                                     'b': dict(one, powerSocaLengths={'1': '50'})})
    out = ev(pg, CROWD_JS, 1)
    said = ('PD1 TRUE1 carries 2 circuits, and it takes one circuit only. '
            'Move one to a multi output. WALL A is hidden and still holds it.')
    assert out['crowding'] == [1], out
    assert out['holders'] == ['WALL A', 'WALL B'], out
    assert said in out['checks'], out['checks']
    assert said in out['strip'], out['strip']
    assert out['count'] == 2 and out['pull'] == 2, out
    assert out['binder'] == [['Crowded', 'PD1 TRUE1 carries 2 circuits · a multi on a '
                              'one-circuit output, move it to a multi output']], out['binder']
    # crowded: no circuit's cable stands in for the output's one cable
    assert out['cable'] is None, out
    # the load still leaves the hidden screen out
    assert out['loads'] == ['WALL B'], out
    assert not errors, errors


def test_a_visible_screen_beside_a_hidden_one_prints_its_own_direct_cable(seeded):
    """WALL B on PD2, WALL A (hidden) on PD1: nothing is crowded, and B's
    own direct cable prints."""
    pg, errors = seeded
    one = {'powerSocaSplits': [1], 'powerSocaDistro': {'1': 'd1'}}
    setup(pg, distros=[FACE], walls={
        'a': dict(one, powerSocaNumber={'1': 1}, **HIDDEN),
        'b': dict(one, powerSocaNumber={'1': 2}, powerSocaLengths={'1': '50'})})
    out = ev(pg, CROWD_JS, 2)
    assert out['crowding'] == [] and out['count'] == 1 and out['pull'] == 0, out
    assert out['binder'] == [], out
    assert out['cable'] and out['cable'].startswith("50'"), out
    assert not [t for t in out['checks'] if 'carries' in t], out['checks']
    assert not errors, errors


def test_an_output_only_a_hidden_screen_crowds_is_on_no_paper(seeded):
    """WALL A (hidden) alone on PD1 with its six-circuit multi: no visible
    screen is on it, so the checks and the distro sheet leave it out."""
    pg, errors = seeded
    setup(pg, distros=[FACE], walls={'a': dict(
        {'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1}}, **HIDDEN)})
    out = ev(pg, """const d = app.getDistros()[0]; app._circuitTailCache = null;
        return { shown: app._faceCrowding(d).map(r => r.number),
                 all: app._faceCrowding(d, { includeHidden: true }).map(r => r.number),
                 checks: app.distroChecks(d).map(w => w.text) };""")
    assert out['shown'] == [] and out['all'] == [1], out
    assert not [t for t in out['checks'] if 'PD1' in t], out['checks']
    assert not errors, errors


# ── 3. the face-edit crowd question sees hidden screens ──────────────────

def test_a_row_edit_that_would_crowd_a_hidden_screen_still_asks(seeded):
    pg, errors = seeded
    setup(pg, distros=[FACE], walls={'a': dict(WALLS['a'], **HIDDEN), 'b': WALLS['b']})
    pg.evaluate("() => window.app.saveState('Setup')")
    before = _state(pg)
    assert ev(pg, RAISE_TRUE1) is None, 'nothing applied while it asks'
    modal = pg.evaluate(MODAL_JS)
    assert modal, 'the dialog did not open for the hidden screen'
    # round 7: the dialog says the screen is hidden, as the tray line does
    assert ("WALL A's 6-circuit multi is on PD4. WALL A is hidden and still holds it. "
            "PD4 would become a TRUE1, which carries one circuit.") in modal['text'], modal['text']
    assert _state(pg) == before, 'nothing changes while it asks'
    pg.locator('#crowd-modal .crowd-cancel').click()
    pg.wait_for_timeout(300)
    assert pg.evaluate(MODAL_JS) is None
    assert _state(pg) == before, 'cancel leaves everything as it was'
    # taking it off applies the change, as for a visible screen
    ev(pg, RAISE_TRUE1)
    pg.locator('#crowd-modal .crowd-take').click()
    pg.wait_for_timeout(400)
    after = _state(pg)
    assert after['rows'] == [['true1', 4], ['soca', 2]], after
    assert after['pinA'] is None, after
    assert not errors, errors
