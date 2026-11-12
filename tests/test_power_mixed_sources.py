"""One screen fed from different kinds of power source, and the L21-30
Edison box (owner rulings, 2026-11-11).

  * "we need a way to combine different cable types and voltages if need
    be": a drop of another type or voltage onto a screen is allowed, where
    it used to be refused;
  * "the circuits after will need redrawing in the same [way] that the
    screen is set to": the circuits it takes over and every one after are
    laid again with the screen's own draw setting, packed to THAT source's
    circuit; the circuits before it are untouched;
  * per-leg math stays real: a 110V circuit is line to neutral on one leg,
    a 208V circuit line to line on a leg pair, mixed loads sum as phasors,
    amps divide by each circuit's own source voltage (the typed 110);
  * the L21-30 Edison box: six 110V Edison circuits, two per leg sharing
    the 30 A leg, 15 A per circuit packed to 12 A; each leg's two circuits
    stay at or under 24 A.

Every expected figure is worked from the formula in the comment beside it.

Run locally:
    python -m pytest tests/test_power_mixed_sources.py -v --browser chromium
"""

import json
import math
import time
import urllib.request
from urllib.parse import urlparse

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

QUIET = "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}"
SQRT3 = math.sqrt(3)


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(QUIET)
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    pg.wait_for_timeout(1500)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(400)
    yield pg, errors
    context.close()


SEED_JS = """async () => {
    const proj = await (await fetch('/api/project')).json();
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments;
    await fetch('/api/project', {method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(proj)});
    await fetch('/api/layer/add', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: 'WALL A', columns: 10, rows: 6,
                              cabinet_width: 200, cabinet_height: 200})});
    const p = await (await fetch('/api/project')).json();
    const app = window.app;
    app.project = p;
    app.currentLayer = p.layers[0];
    app.selectedLayerIds = new Set([p.layers[0].id]);
    app.renderLayers();
    return p.layers[0].id;
}"""

# The wall reshaped in the page, the distros set, every feed cleared.
SETUP_JS = """(o) => {
    const app = window.app;
    const l = app.project.layers[0];
    const want = o.wall || {};
    if (want.columns || want.rows) {
        const cols = want.columns || l.columns, rows = want.rows || l.rows;
        l.columns = cols; l.rows = rows;
        l.panels = [];
        for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
            l.panels.push({ id: `p${r}_${c}`, row: r, col: c, x: c * 200, y: r * 200,
                            width: 200, height: 200, hidden: false, blank: false });
        }
    }
    const fields = Object.assign({}, want);
    delete fields.columns; delete fields.rows;
    Object.assign(l, { powerVoltage: 208, powerAmperage: 20, panelWatts: 400,
                       powerOrganized: false, powerMaximize: false,
                       powerSocaDistro: {}, powerSocaNumber: {}, powerSocaPhasePos: {},
                       powerSocaLengths: {}, powerSocaSplits: [], powerSocaNames: {},
                       powerBreakoutType: null, locked: false, powerFlowPattern: 'tl-h',
                       powerCustomPaths: {}, lastPowerFlowPattern: null }, fields);
    // [] rather than a missing key, so a server echo of an earlier test's
    // save can never bring a source back (a PUT never sends a missing key)
    l.powerSources = want.powerSources || [];
    app.normalizePowerBreakout(l);
    app.project.distros = (o.distros || []).map(d => JSON.parse(JSON.stringify(d)));
    app._circuitTailCache = null;
    app._distroFaceMemo = null;
    app.getDistros();
    app.currentLayer = l;
    app.selectedLayerIds = new Set([l.id]);
    // the server holds the reset too, so no later echo restores a feed
    app.updateLayers([l]);
    return app.screenCircuits(l).length;
}"""

A = "window.app.project.layers[0]"


def setup(pg, **o):
    pg.wait_for_timeout(300)
    n = pg.evaluate(SETUP_JS, o)
    # the reset's own save lands before the test acts
    pg.wait_for_timeout(400)
    return n


def ev(pg, body, arg=None):
    return pg.evaluate(f"(arg) => {{ const app = window.app; const A = {A}; {body} }}", arg)


# A typed spare box dropped on one circuit, as the tray's drag releases it
# (_dockDropSlot, target kind 'run').
BOX_DROP = """
    const num = arg.num;
    const rec = [...app._powerNaming(A).socas.values()].find(r => r.circuits.includes(num));
    const before = app.history.length;
    app._dockDropSlot({ type: 'slot', distroId: arg.distro, number: arg.number,
                        output: arg.output, title: arg.title || 'BOX' },
                      { kind: 'run', layerId: A.id, socaIndex: rec.index, num });
    app._circuitTailCache = null;
    return { steps: app.history.length - before,
             said: (document.getElementById('hw-dock-say') || {}).textContent || '' };
"""

# An OUTPUTS chip dropped on the screen (_dockDropPlug).
PLUG_DROP = """
    const before = app.history.length;
    app._dockDropPlug({ type: 'plug', distroId: arg.distro, output: arg.output,
                        title: arg.title || 'OUT' }, { kind: 'screen', layerId: A.id });
    app._circuitTailCache = null;
    return { steps: app.history.length - before };
"""

CIRCUITS = """
    return app.screenCircuits(A).map(c => ({ num: c.num,
        ids: c.panels.map(p => p.id), n: c.panels.length }));
"""

OLD_DISTRO = {'id': 'd1', 'name': 'SL', 'ratingA': 400, 'voltage': 208, 'phase': 3}


@pytest.fixture(scope="module")
def seeded(page):
    pg, errors = page
    pg.evaluate(SEED_JS)
    pg.wait_for_timeout(800)
    return pg, errors


def _first_box_fed(pg):
    """A 208V TRUE1 wall, 10 x 6 cabinets of 400 W, its first multi on
    SL (an old 120/208 distro). Own circuit: 208 V x 20 A x 80% = 3,328 W,
    so floor(3328 / 400) = 8 cabinets a circuit: 60 cabinets make 7
    circuits of 8 and one of 4 - multis 1-6 and 7-8."""
    n = setup(pg, distros=[OLD_DISTRO],
              wall={'columns': 10, 'rows': 6, 'powerSocaDistro': {'1': 'd1'},
                    'powerSocaNumber': {'1': 1}})
    assert n == 8
    return ev(pg, CIRCUITS)


def test_page_loads_and_the_edison_box_is_a_type(seeded):
    pg, errors = seeded
    out = ev(pg, """
        const t = app.getDistroOutputTypes().find(x => x.id === 'l2130e');
        const c = app.distroConnector('l2130e');
        return { name: t && t.name, size: t && t.boxSize, feed: t && t.feedLegA,
                 conn: c && c.short, circuits: c && c.circuits,
                 old: app.getDistroOutputTypes().find(x => x.id === 'l2130').name };""")
    assert out == {'name': 'L21-30 Edison', 'size': 6, 'feed': 30, 'conn': 'L21-30 Edison',
                   'circuits': 6, 'old': 'L21-30'}, out
    assert not errors, errors


def test_an_edison_box_on_a_208_true1_screen_relays_the_circuits_after_it(seeded):
    """The L21-30 Edison box dropped on circuit 7 of a 208V TRUE1 wall:
    allowed (it used to be refused), and circuits 7 on are laid again at
    the box's circuit: 110 V x 15 A x 80% = 1,320 W, floor(1320 / 400) = 3
    cabinets each. 60 - 6 x 8 = 12 cabinets left -> 4 circuits of 3.
    Circuits 1-6 keep exactly the cabinets they had."""
    pg, _ = seeded
    before = _first_box_fed(pg)
    out = ev(pg, BOX_DROP, {'distro': 'd1', 'number': 2, 'output': 'l2130e', 'num': 7})
    assert out['steps'] == 1, out
    after = ev(pg, CIRCUITS)
    assert [c['n'] for c in after] == [8] * 6 + [3] * 4, after
    assert [c['ids'] for c in after[:6]] == [c['ids'] for c in before[:6]]
    plan = ev(pg, """
        return { src: A.powerSources, plan: app.getSocaPlan(A).map(s => ({ soca: s.soca,
            distro: s.distroId, number: s.number, v: s.voltage || null,
            amps: s.legs.map(g => g.amps) })),
            box: app.distroBoxType(app.getDistros()[0], 2).type.id };""")
    assert plan['src'] == [{'from': 7, 'type': 'l2130e', 'distroId': 'd1',
                            'breakout': 'l2130-edison', 'volts': 110, 'amps': 15}], plan
    assert plan['box'] == 'l2130e'
    s1, s2 = plan['plan']
    # 8 x 400 W = 3,200 W at 208 V = 15.3846 A, on the screen's own circuits
    assert s1['v'] == 208 and s1['distro'] == 'd1'
    assert s1['amps'] == pytest.approx([3200 / 208] * 6)
    # 3 x 400 W = 1,200 W at the typed 110 V = 10.909 A, under the 12 A
    # (15 A x 80%) the box's circuits are held to
    assert s2['v'] == 110 and s2['distro'] == 'd1' and s2['number'] == 2
    assert s2['amps'] == pytest.approx([1200 / 110] * 4)
    assert max(s2['amps']) <= 12


def test_per_leg_amps_on_the_mixed_screen_are_the_phasor_sum(seeded):
    """SL carries the 208V multi (circuits 1-6, 15.3846 A each, line to
    line on paired legs XY XY ZX ZX YZ YZ: each 208V circuit puts its
    current on its first leg at +30 deg and its second at -30 deg) and the
    L21-30 Edison box (circuits 7-10, 10.909 A each, line to neutral on
    X Y Z X at 0 deg).
      X: 2I(+30) from XY + 2I(-30) from ZX = 2I x 2cos30 = 2*sqrt3*I at 0;
         plus circuits 7 and 10 = 2 x 10.909 at 0
         -> 2 x 1.7321 x 15.3846 + 21.8182 = 53.2939 + 21.8182 = 75.1121 A
      Y: 53.2939 + 10.9091 (circuit 8) = 64.2030 A
      Z: 53.2939 + 10.9091 (circuit 9) = 64.2030 A
    The Edison box's own feed: X 21.82, Y 10.91, Z 10.91 A, under 24 A."""
    pg, _ = seeded
    _first_box_fed(pg)
    ev(pg, BOX_DROP, {'distro': 'd1', 'number': 2, 'output': 'l2130e', 'num': 7})
    out = ev(pg, """
        const b = app.getDistroLoads().find(x => x.id === 'd1');
        const s2 = app.getSocaPlan(A)[1];
        const feed = app.boxFeedLegAmps(app.getDistros()[0], [{ layer: A, s: s2 }]);
        return { legs: [b.legs.X.amps, b.legs.Y.amps, b.legs.Z.amps], feed: [feed.X, feed.Y, feed.Z],
                 mixed: b.legs.schemeMixed, limit: app.distroFeedLimit(app.getDistros()[0], 30).limitA };""")
    i208 = 3200 / 208
    i110 = 1200 / 110
    base = 2 * SQRT3 * i208
    assert out['legs'] == pytest.approx([base + 2 * i110, base + i110, base + i110], abs=1e-6), out
    assert out['legs'][0] == pytest.approx(75.1121, abs=1e-3)
    assert out['feed'] == pytest.approx([2 * i110, i110, i110], abs=1e-9)
    assert out['limit'] == pytest.approx(24)       # 30 A x 80%
    assert max(out['feed']) <= out['limit']
    assert out['mixed'] is True


def test_the_mixed_screen_s_neutral_counts_only_its_110v_circuits(seeded):
    """The power in's neutral (app-neutral.js) on the mixed wall: the 208V
    circuits are line to line and put nothing on it; the Edison box's
    110V circuits return on it, X 2 x 10.909, Y 10.909, Z 10.909 A.
      line-to-neutral total = 4 x 10.909 = 43.636 A
      fundamental = |21.818 at 0 + 10.909 at -120 + 10.909 at +120|
                  = 21.818 - 10.909 = 10.909 A
      triplens    = h x 43.636 (h the LED supply's triplen fraction)
      neutral     = sqrt(fundamental^2 + triplens^2)"""
    pg, _ = seeded
    _first_box_fed(pg)
    ev(pg, BOX_DROP, {'distro': 'd1', 'number': 2, 'output': 'l2130e', 'num': 7})
    out = ev(pg, """
        const n = app.getDistroLoads().find(x => x.id === 'd1').neutral;
        return { n, h: app.supplyTriplenFraction(A) };""")
    i110 = 1200 / 110
    n, h = out['n'], out['h']
    assert n['lnA'] == pytest.approx(4 * i110)
    assert n['fundA'] == pytest.approx(i110)
    assert n['triplenA'] == pytest.approx(h * 4 * i110)
    assert n['amps'] == pytest.approx(math.hypot(i110, h * 4 * i110))


def test_organized_screen_relays_by_whole_rows_from_the_source(seeded):
    """The re-lay follows the screen's own draw setting. Organized: a row
    of 10 x 400 W = 4,000 W is over the own circuit (3,328 W) and is cut
    into whole cabinets, 8 + 2; rows 1-3 make circuits 1-6. The Edison box
    on circuit 7 lays rows 4-6 again at 1,320 W: each row cut 3 + 3 + 3 + 1,
    four circuits a row."""
    pg, _ = seeded
    setup(pg, distros=[OLD_DISTRO],
          wall={'columns': 10, 'rows': 6, 'powerOrganized': True,
                'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1}})
    before = ev(pg, CIRCUITS)
    assert [c['n'] for c in before] == [8, 2] * 6
    ev(pg, BOX_DROP, {'distro': 'd1', 'number': 2, 'output': 'l2130e', 'num': 7})
    after = ev(pg, CIRCUITS)
    assert [c['n'] for c in after] == [8, 2] * 3 + [3, 3, 3, 1] * 3, after
    assert [c['ids'] for c in after[:6]] == [c['ids'] for c in before[:6]]
    # every re-laid circuit stays on one row
    rows = ev(pg, "return app.screenCircuits(A).slice(6).map(c => [...new Set(c.panels.map(p => p.row))]);")
    assert all(len(r) == 1 for r in rows), rows


def test_a_hand_drawn_screen_has_its_circuits_after_the_source_redrawn(seeded):
    """A custom (hand-drawn) screen packed full (Max Capacity): its drawn
    circuits 7 on are redrawn at the Edison box's 1,320 W - 3 cabinets
    each, the last 12 cabinets making 4 circuits - and circuits 1-6 keep
    their drawing."""
    pg, _ = seeded
    _first_box_fed(pg)
    paths = ev(pg, """
        const circuits = app.calculatePowerAssignments(A).circuits;
        A.powerCustomPaths = {};
        circuits.forEach((panels, i) => {
            A.powerCustomPaths[i + 1] = panels.map(p => ({ row: p.row, col: p.col }));
        });
        A.lastPowerFlowPattern = 'tl-h';
        A.powerFlowPattern = 'custom';
        A.powerMaximize = true;
        app._circuitTailCache = null;
        return JSON.parse(JSON.stringify(A.powerCustomPaths));""")
    assert len(paths) == 8
    out = ev(pg, BOX_DROP, {'distro': 'd1', 'number': 2, 'output': 'l2130e', 'num': 7})
    assert out['steps'] == 1, out
    got = ev(pg, "return JSON.parse(JSON.stringify(A.powerCustomPaths));")
    assert sorted(int(k) for k in got) == list(range(1, 11)), got.keys()
    for k in range(1, 7):
        assert got[str(k)] == paths[str(k)]
    assert [len(got[str(k)]) for k in range(7, 11)] == [3, 3, 3, 3]
    # the same cabinets, none lost or doubled
    old = sorted((p['row'], p['col']) for k in ('7', '8') for p in paths[k])
    new = sorted((p['row'], p['col']) for k in range(7, 11) for p in got[str(k)])
    assert old == new


def test_undo_takes_the_whole_drop_back_in_one_step(seeded):
    pg, _ = seeded
    before = _first_box_fed(pg)
    ev(pg, "app.resetHistory('Mixed Seed');")
    ev(pg, BOX_DROP, {'distro': 'd1', 'number': 2, 'output': 'l2130e', 'num': 7})
    assert ev(pg, "return app.history.map(h => h.action);") == ['Mixed Seed', 'Feed From Another Source']
    ev(pg, "app.undo();")
    pg.wait_for_timeout(300)
    out = ev(pg, """
        const L = window.app.project.layers[0];
        window.app._circuitTailCache = null;
        return { src: ((L.powerSources || []).length ? L.powerSources : null), n: window.app.screenCircuits(L).map(c => c.panels.length),
                 assign: L.powerSocaDistro };""")
    assert out['src'] is None, out
    assert out['n'] == [c['n'] for c in before]
    assert out['assign'] == {'1': 'd1'}


def test_unplugging_the_box_puts_the_circuits_back(seeded):
    """No source, no different circuits: the box unplugged, its circuits
    are the screen's own again (8 a circuit)."""
    pg, _ = seeded
    before = _first_box_fed(pg)
    ev(pg, BOX_DROP, {'distro': 'd1', 'number': 2, 'output': 'l2130e', 'num': 7})
    out = ev(pg, """
        app.setSocaDistro(A, 2, null);
        app._circuitTailCache = null;
        return { src: ((A.powerSources || []).length ? A.powerSources : null), n: app.screenCircuits(A).map(c => c.panels.length) };""")
    assert out['src'] is None, out
    assert out['n'] == [c['n'] for c in before]


def test_a_save_keeps_a_source_it_cannot_read_yet(seeded):
    """A screen with no watts typed has no circuits to read a source
    against: a save keeps its source as stored, as it keeps a split past
    the end, rather than call it unfed and drop it."""
    pg, _ = seeded
    _first_box_fed(pg)
    ev(pg, BOX_DROP, {'distro': 'd1', 'number': 2, 'output': 'l2130e', 'num': 7})
    out = ev(pg, """
        A.panelWatts = 0;
        app._circuitTailCache = null;
        const n = app.screenCircuits(A).length;
        app.updateLayers([A]);
        return { n, src: (A.powerSources || []).map(r => r.from) };""")
    assert out == {'n': 0, 'src': [7]}, out


def test_a_single_type_screen_is_untouched_and_unlabelled(seeded):
    """Nothing new for a screen of one kind: the same drop of its own
    type is the ordinary drop, no source is written, no label changes."""
    pg, _ = seeded
    _first_box_fed(pg)
    out = ev(pg, BOX_DROP, {'distro': 'd1', 'number': 2, 'output': 'soca208', 'num': 7})
    got = ev(pg, """
        return { src: ((A.powerSources || []).length ? A.powerSources : null), n: app.screenCircuits(A).map(c => c.panels.length),
                 text: app.circuitSourceText(A, 7), mixed: app.isMixedPower(A) };""")
    assert out['steps'] == 1
    assert got == {'src': None, 'n': [8] * 7 + [4], 'text': '', 'mixed': False}, got


def test_the_edison_box_six_circuits_two_per_leg_never_over(seeded):
    """A 110V screen on the L21-30 Edison box alone, cabinets of 220 W:
    the box's circuit is 110 V x 15 A x 80% = 1,320 W = 6 cabinets
    (6 x 220 = 1,320 W = 12.0 A exactly). 6 x 6 cabinets -> six circuits
    of 12 A on tails 1-6 = legs X Y Z X Y Z: two per leg, 24 A a leg,
    exactly the 24 A (30 A x 80%) the feed is held to. Never OVER."""
    pg, _ = seeded
    face = {'id': 'e1', 'name': 'SR', 'system': '120/208', 'voltage': 208, 'phase': 3,
            'input': 'cam400', 'ratingA': 400,
            'outputRows': [{'id': 'r1', 'connector': 'l2130e', 'count': 1, 'coupling': 'ln',
                            'breakerA': 30}]}
    n = setup(pg, distros=[face], wall={'columns': 6, 'rows': 6, 'powerVoltage': 110,
                                        'powerAmperage': 20, 'panelWatts': 220,
                                        'powerBreakoutType': 'l2130-edison'})
    assert n == 6
    ev(pg, PLUG_DROP, {'distro': 'e1', 'output': 'face:r1'})
    out = ev(pg, """
        const d = app.getDistros()[0];
        const s = app.getSocaPlan(A)[0];
        const legs = s.legs.map((g, li) => app.distroCircuitLegs(d, A, s, li,
            app.socaCircuitPositions(A, s.soca, s.legs.length)).legs.join(''));
        const feed = app.boxFeedLegAmps(d, [{ layer: A, s }]);
        return { distro: s.distroId, amps: s.legs.map(g => g.amps), legs,
                 feed: [feed.X, feed.Y, feed.Z], checks: app.distroChecks(d).map(c => c.text),
                 load: app.getDistroLoads()[0].legs.X.amps,
                 src: ((A.powerSources || []).length ? A.powerSources : null) };""")
    assert out['distro'] == 'e1'
    assert out['amps'] == pytest.approx([12.0] * 6)       # 1,320 W / 110 V
    assert out['legs'] == ['X', 'Y', 'Z', 'X', 'Y', 'Z']
    assert out['feed'] == pytest.approx([24.0, 24.0, 24.0])  # two 12 A circuits a leg
    assert not [t for t in out['checks'] if 'OVER' in t or 'over' in t], out['checks']
    assert out['src'] is None


def test_the_edison_box_is_not_held_like_the_208v_l2130_box(seeded):
    """The 208V three-circuit L21-30 is held to its feed limit over root 3
    (24 / 1.732 = 13.86 A a circuit). The Edison box is not: its circuits
    are line to neutral, two a leg, so its own 15 A x 80% = 12 A is the
    hold, and 6 cabinets of 220 W (1,320 W = 12.0 A) still make one
    circuit. Its outlets are 5-20s on their own 20 A breakers, so the
    breaker-over-connector check finds nothing (20 A on 20 A)."""
    pg, _ = seeded
    face = {'id': 'e1', 'name': 'SR', 'system': '120/208', 'voltage': 208, 'phase': 3,
            'input': 'cam400', 'ratingA': 400,
            'outputRows': [{'id': 'r1', 'connector': 'l2130e', 'count': 1, 'coupling': 'ln',
                            'breakerA': 30}]}
    setup(pg, distros=[face], wall={'columns': 6, 'rows': 6, 'powerVoltage': 110,
                                    'powerAmperage': 20, 'panelWatts': 220,
                                    'powerBreakoutType': 'l2130-edison'})
    ev(pg, PLUG_DROP, {'distro': 'e1', 'output': 'face:r1'})
    out = ev(pg, """
        const cap = app.circuitCapacity(A);
        return { amps: cap.amps, held: cap.cap || null, n: app.screenCircuits(A).length,
                 over: app.breakerOverChecks().map(g => g.text) };""")
    assert out['amps'] == pytest.approx(12.0) and out['held'] is None, out
    assert out['n'] == 6
    assert out['over'] == [], out['over']


def test_a_mixed_screen_s_edison_output_follows_its_5_15_or_5_20(seeded):
    """A 208V TRUE1 wall on a Socapex 208, then an Edison output dragged
    on: circuits 7 on ride it at 110V. A 5-20 output packs them to 80% of
    20 A = 16 A: 110 x 16 = 1,760 W, 4 cabinets of 400 W. Picked 5-15, to
    80% of 15 A = 12 A: 1,320 W, 3 cabinets. The Socapex circuits keep
    8 cabinets either way (208 x 20 x 80% = 3,328 W)."""
    pg, _ = seeded
    face = {'id': 'g1', 'name': 'VX', 'system': '120/208', 'voltage': 208, 'phase': 3,
            'input': 'cam400', 'ratingA': 400,
            'outputRows': [{'id': 'r1', 'connector': 'soca', 'count': 2, 'coupling': 'll', 'breakerA': 20},
                           {'id': 'r2', 'connector': 'edison', 'count': 6, 'coupling': 'ln', 'breakerA': 20,
                            'edisonType': '5-20'}]}
    setup(pg, distros=[face], wall={'columns': 10, 'rows': 6, 'powerBreakoutType': 'soca-true1'})
    ev(pg, PLUG_DROP, {'distro': 'g1', 'output': 'face:r1'})
    out = ev(pg, PLUG_DROP, {'distro': 'g1', 'output': 'face:r2'})
    assert out['steps'] == 1
    n20 = ev(pg, "return app.screenCircuits(A).map(c => c.panels.length);")
    assert n20[:6] == [8] * 6 and n20[6] == 4, n20
    ev(pg, """
        const d = app.getDistros()[0];
        d.outputRows = d.outputRows.map(r => r.id === 'r2' ? Object.assign({}, r, { edisonType: '5-15' }) : r);
        app._distroFaceMemo = null; app._circuitTailCache = null; return true;""")
    n15 = ev(pg, "return app.screenCircuits(A).map(c => c.panels.length);")
    assert n15[:6] == [8] * 6 and n15[6] == 3, n15


SHOW_DISTRO = {'id': 'f1', 'name': 'VX', 'system': '120/208', 'voltage': 208, 'phase': 3,
               'input': 'cam400', 'ratingA': 400,
               'outputRows': [
                   {'id': 'r1', 'connector': 'soca', 'count': 4, 'coupling': 'ln', 'breakerA': 20},
                   {'id': 'r2', 'connector': 'l2130e', 'count': 3, 'coupling': 'ln', 'breakerA': 30}]}


def _show_case(pg):
    """The owner's show shape: a 400 A 120/208 distro with 4 Socapex 120V
    and 3 L21-30 outputs, each L21-30 on an Edison box. A 110V Edison
    wall, 10 x 10 cabinets of 400 W. Own circuit 110 V x 20 A x 80% =
    1,760 W = 4 cabinets (1,600 W, 14.545 A). Three Socapex take circuits
    1-18 (72 cabinets); the first Edison box takes over at 19: 1,320 W =
    3 cabinets a circuit, 28 cabinets left -> nine circuits of 3 and one
    of 1 (circuits 19-28); the box takes 19-24, the second box 25-28."""
    setup(pg, distros=[SHOW_DISTRO],
          wall={'columns': 10, 'rows': 10, 'powerVoltage': 110, 'powerAmperage': 20,
                'panelWatts': 400, 'powerBreakoutType': 'soca-edison'})
    for _ in range(3):
        ev(pg, PLUG_DROP, {'distro': 'f1', 'output': 'face:r1'})
    first = ev(pg, PLUG_DROP, {'distro': 'f1', 'output': 'face:r2'})
    second = ev(pg, PLUG_DROP, {'distro': 'f1', 'output': 'face:r2'})
    return first, second


def test_socapex_110_and_l2130_edison_on_one_wall(seeded):
    pg, _ = seeded
    first, second = _show_case(pg)
    assert first['steps'] == 1 and second['steps'] == 1
    out = ev(pg, """
        const d = app.getDistros()[0];
        const plan = app.getSocaPlan(A);
        return { src: A.powerSources, n: app.screenCircuits(A).map(c => c.panels.length),
                 boxes: plan.map(s => [s.number, s.legs.length]),
                 t1: app.circuitSourceText(A, 1), t19: app.circuitSourceText(A, 19),
                 checks: app.distroChecks(d).map(c => c.text),
                 loads: app.getDistroLoads()[0].legs };""")
    assert out['src'] == [{'from': 19, 'type': 'face', 'distroId': 'f1', 'rowId': 'r2',
                           'breakout': 'l2130-edison', 'volts': 110, 'amps': 15}], out['src']
    assert out['n'] == [4] * 18 + [3] * 9 + [1]
    # Socapex 1-3 (six circuits each), Edison box 5 (19-24), box 6 (25-28)
    assert out['boxes'] == [[1, 6], [2, 6], [3, 6], [5, 6], [6, 4]], out['boxes']
    assert out['t1'] == '110V Edison' and out['t19'] == '110V L21-30 Edison'
    assert not [t for t in out['checks'] if 'OVER' in t or 'over' in t], out['checks']
    # every circuit here is line to neutral at 0 deg, so each leg is the
    # plain sum of its circuits' W / 110: the 18 Socapex circuits at
    # 1,600 / 110 and the 10 Edison ones at 1,200 / 110 (the last 400 / 110)
    total = 18 * 1600 / 110 + 9 * 1200 / 110 + 400 / 110
    legs = out['loads']
    assert legs['X']['amps'] + legs['Y']['amps'] + legs['Z']['amps'] == pytest.approx(total)


def test_the_pull_sheet_and_binder_print_the_mixed_screen(seeded):
    pg, _ = seeded
    _show_case(pg)
    out = ev(pg, """
        const list = app.buildPullList();
        const rows = list.positions.flatMap(p => p.rows || []);
        const types = rows.map(r => r.type || r.cable || r[0]);
        return { types: JSON.stringify(rows) };""")
    assert 'L21-30 Edison Breakout' in out['types'], out['types'][:2000]
    assert 'Edison Breakout' in out['types']
    # The binder's power sheet for the wall: every sheet renders, and the
    # power sheet bands the circuits by box, the Edison boxes by name.
    texts = ev(pg, """
        const opts = { sheet: 'tabloid', palette: 'colour', sides: { power: true, data: false },
                       scope: { kind: 'show' }, cover: false, pull: true, hardware: true, wiring: false };
        const plan = app.planBinder(opts);
        const out = [];
        for (let i = 0; i < plan.length; i++) {
            const r = app.renderBinderPage(opts, i);
            out.push({ kind: plan[i].kind, texts: r.record.ops
                .filter(o => o.op === 'text' && String(o.text).trim()).map(o => String(o.text)) });
        }
        return out;""")
    power = [t for p in texts if p['kind'] == 'power' for t in p['texts']]
    joined = ' | '.join(power)
    assert 'L21-30 Edison' in joined, joined[:3000]
    assert 'Socapex 120V' in joined, joined[:3000]


# ── follower page, old show ───────────────────────────────────────────────

def _call(url, method, path, body=None):
    data = None if body is None else json.dumps(body).encode('utf-8')
    req = urllib.request.Request(url + path, data=data, method=method,
                                 headers={'Content-Type': 'application/json'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=10) as reply:
        return json.loads(reply.read().decode('utf-8'))


def _ctx(pw_browser):
    c = pw_browser.new_context(viewport={'width': 1600, 'height': 950})
    c.add_init_script(QUIET)
    return c


def _open(context, url):
    pg = context.new_page()
    pg.goto(url, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)
    pg.wait_for_timeout(1200)
    return pg


def _seed_server(url, with_source=False):
    proj = _call(url, 'GET', '/api/project')
    proj['layers'] = []
    proj['groups'] = []
    proj['processors'] = []
    proj['distros'] = [dict(OLD_DISTRO)]
    proj.pop('port_assignments', None)
    _call(url, 'PUT', '/api/project', proj)
    layer = _call(url, 'POST', '/api/layer/add', {'name': 'WALL A', 'columns': 10, 'rows': 6,
                                                  'cabinet_width': 200, 'cabinet_height': 200})
    fields = {'powerVoltage': 208, 'powerAmperage': 20, 'panelWatts': 400,
              'powerOrganized': False, 'powerMaximize': False,
              'powerBreakoutType': 'soca-true1',
              'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1}}
    _call(url, 'PUT', f"/api/layer/{layer['id']}", fields)
    return layer['id']


def test_a_following_page_writes_nothing(e2e_server, pw_browser):
    """Page A drops the Edison box; page B follows the change and sends no
    write back."""
    _seed_server(e2e_server)
    ca, cb = _ctx(pw_browser), _ctx(pw_browser)
    try:
        a = _open(ca, e2e_server)
        b = _open(cb, e2e_server)
        writes = []

        def request(req):
            if req.method in ('GET', 'HEAD', 'OPTIONS'):
                return
            path = urlparse(req.url).path
            if path.startswith('/api/') and path not in ('/api/log', '/api/port-assignments/resolve',
                                                         '/api/port-assignments/link-check'):
                writes.append(f'{req.method} {path}')
        b.on('request', request)
        a.locator('[data-mode="power"]').click()
        a.wait_for_timeout(300)
        out = a.evaluate(f"(arg) => {{ const app = window.app; const A = app.project.layers[0]; {BOX_DROP} }}",
                         {'distro': 'd1', 'number': 2, 'output': 'l2130e', 'num': 7})
        assert out['steps'] == 1, out
        deadline = time.time() + 10
        while time.time() < deadline:
            srv = _call(e2e_server, 'GET', '/api/project')
            if srv['layers'][0].get('powerSources'):
                break
            time.sleep(0.2)
        assert srv['layers'][0]['powerSources'][0]['from'] == 7
        b.wait_for_function("() => !!(window.app.project.layers[0].powerSources || []).length",
                            timeout=10000)
        b.wait_for_timeout(1500)
        assert writes == [], writes
        n = b.evaluate("() => { const app = window.app; app._circuitTailCache = null; "
                       "return app.screenCircuits(app.project.layers[0]).map(c => c.panels.length); }")
        assert n == [8] * 6 + [3] * 4
    finally:
        ca.close()
        cb.close()


def _wait_server(url, want, timeout=10.0):
    deadline = time.time() + timeout
    srv = None
    while time.time() < deadline:
        srv = _call(url, 'GET', '/api/project')
        if want(srv):
            return srv
        time.sleep(0.2)
    raise AssertionError(f'the server never got there: {srv and srv["layers"][0].get("powerSources")}')


RELOADED_JS = """() => { const app = window.app; app._circuitTailCache = null;
    const l = app.project.layers[0];
    return { src: (l.powerSources || []).length ? l.powerSources : null,
             n: app.screenCircuits(l).map(c => c.panels.length) }; }"""


def test_unplugging_or_removing_the_distro_forgets_the_source_through_a_reload(e2e_server, pw_browser):
    """The gestures that take a source's box away write the cleared source
    to the server in their own save (an empty list, never a dropped key),
    so a reload brings back the screen's own circuits, 8 a circuit:
    Unplug Multi on the Edison box, then (the box dropped again) Remove
    Distro."""
    _seed_server(e2e_server)
    c = _ctx(pw_browser)
    try:
        pg = _open(c, e2e_server)
        pg.locator('[data-mode="power"]').click()
        pg.wait_for_timeout(300)
        drop = f"(arg) => {{ const app = window.app; const A = app.project.layers[0]; {BOX_DROP} }}"
        arg = {'distro': 'd1', 'number': 2, 'output': 'l2130e', 'num': 7}
        assert pg.evaluate(drop, arg)['steps'] == 1
        _wait_server(e2e_server, lambda p: (p['layers'][0].get('powerSources') or [{}])[0].get('from') == 7)
        # Unplug Multi on the Edison box, as the tray's menu runs it
        pg.evaluate("() => { const app = window.app; "
                    "app._clearMultis(app._distroMultiNumbers('d1').get(2), 'Unplug Multi'); }")
        srv = _wait_server(e2e_server, lambda p: p['layers'][0].get('powerSources') == [])
        assert srv['layers'][0]['powerSocaDistro'] == {'1': 'd1'}
        pg.reload(wait_until='domcontentloaded')
        pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)
        pg.wait_for_timeout(1200)
        assert pg.evaluate(RELOADED_JS) == {'src': None, 'n': [8] * 7 + [4]}
        # the box again, then the distro removed
        pg.locator('[data-mode="power"]').click()
        pg.wait_for_timeout(300)
        assert pg.evaluate(drop, arg)['steps'] == 1
        _wait_server(e2e_server, lambda p: (p['layers'][0].get('powerSources') or [{}])[0].get('from') == 7)
        pg.evaluate("() => window.app.removeDistro('d1')")
        _wait_server(e2e_server, lambda p: p['layers'][0].get('powerSources') == [] and not p['distros'])
        pg.reload(wait_until='domcontentloaded')
        pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)
        pg.wait_for_timeout(1200)
        assert pg.evaluate(RELOADED_JS) == {'src': None, 'n': [8] * 7 + [4]}
        # and an undone drop: the show seeded again, the box dropped, Ctrl+Z
        _seed_server(e2e_server)
        pg.reload(wait_until='domcontentloaded')
        pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)
        pg.wait_for_timeout(1200)
        pg.locator('[data-mode="power"]').click()
        pg.wait_for_timeout(300)
        assert pg.evaluate(drop, arg)['steps'] == 1
        _wait_server(e2e_server, lambda p: (p['layers'][0].get('powerSources') or [{}])[0].get('from') == 7)
        pg.wait_for_timeout(400)
        pg.evaluate("() => window.app.undo()")
        _wait_server(e2e_server, lambda p: not (p['layers'][0].get('powerSources') or []))
        pg.reload(wait_until='domcontentloaded')
        pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)
        pg.wait_for_timeout(1200)
        assert pg.evaluate(RELOADED_JS) == {'src': None, 'n': [8] * 7 + [4]}
    finally:
        c.close()


def test_an_old_show_opens_byte_identical(e2e_server, pw_browser):
    """A show with no sources opens and is left exactly as it was: nothing
    written, no source key added, the same circuits."""
    _seed_server(e2e_server)
    before = _call(e2e_server, 'GET', '/api/project')
    c = _ctx(pw_browser)
    try:
        pg = _open(c, e2e_server)
        pg.locator('[data-mode="power"]').click()
        pg.wait_for_timeout(1500)
        n = pg.evaluate("() => window.app.screenCircuits(window.app.project.layers[0]).length")
        assert n == 8
    finally:
        c.close()
    after = _call(e2e_server, 'GET', '/api/project')
    assert 'powerSources' not in after['layers'][0]
    assert json.dumps(after, sort_keys=True) == json.dumps(before, sort_keys=True)
