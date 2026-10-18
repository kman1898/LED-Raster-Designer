"""Custom distro outputs (1.5) - owner rulings, 2026-10-16.

A distro is a SYSTEM (120/208V 3φ, 120/240V split-phase, 120V 1φ,
230/400V 3φ, 230V 1φ) with an input, a rating per leg and OUTPUT ROWS on
its face: multi rows (Socapex 19-pin, Harting 16E - six circuits; L21-30 -
three 208V circuits) that break out at the screen, and direct rows (True1,
powerCON 20A, powerCON XX, Edison 5-20, L5-20, L6-20, stage pin 20A, CEE
16A/32A blue, Schuko) - one circuit per connector with its own cable.

Pinned here:
  * migration of old {voltage, phase} distros - 208/120 3φ -> 120/208,
    230/400 3φ -> 230/400, 120 1φ -> 120, 230 1φ -> 230; ambiguous pairs stay
    on the old arithmetic - with today's results unchanged except the
    230/400 fix (230V circuits LN, one leg each)
  * the header, OVER and binder Load read the WORST LEG (a whole Socapex on
    one leg flags OVER where the balanced figure would not)
  * the screen's 3φ readout divides by the service's line-to-line voltage
  * a screen voltage the system does not have is refused, saying why
  * coupling from the system plus the connector; stage pin refused at 208V
    (ANSI E1.24); powerCON XX at 208V warned (US-listed to 127V)
  * the US 80% breaker check and the 100%-rated switch; EU at the breaker
  * paired rows count once, and a circuit is patched to one connector only
  * direct outputs rotate X Y Z; "whole multi on one leg" is EU only
  * the eleven presets, and saving one
  * direct-output cables on the pull sheet in the show's unit (metric too)

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_custom_distros.py -q --browser chromium
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    # the app's own first load lands before the test touches the project
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    pg.wait_for_timeout(2000)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(400)
    yield pg, errors
    context.close()


# Two walls made through the server, then reshaped in the page per test:
# WALL A 10 wide x 6 rows, WALL B 6 x 3 off to the right. One row is one
# circuit at the voltages and amps the tests set.
SEED_JS = """async () => {
    const proj = await (await fetch('/api/project')).json();
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments;
    await fetch('/api/project', {method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(proj)});
    await fetch('/api/layer/add', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: 'WALL A', columns: 10, rows: 6,
                              cabinet_width: 200, cabinet_height: 200})});
    await fetch('/api/layer/add', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: 'WALL B', columns: 6, rows: 3,
                              cabinet_width: 200, cabinet_height: 200, offset_x: 2600})});
    const p = await (await fetch('/api/project')).json();
    const app = window.app;
    app.project = p;
    app.currentLayer = p.layers[0];
    app.selectedLayerIds = new Set([p.layers[0].id]);
    app.renderLayers();
    return { a: p.layers[0].id, b: p.layers[1].id };
}"""

# Reshape the show in the page: `walls` {a: {...}, b: {...}} layer fields,
# `distros` the records (migrated on read), every assignment cleared.
SETUP_JS = """(o) => {
    const app = window.app;
    for (const l of app.project.layers) {
        const key = l.name === 'WALL A' ? 'a' : 'b';
        Object.assign(l, { powerVoltage: 208, powerAmperage: 20, panelWatts: 200,
                           powerSocaDistro: {}, powerSocaNumber: {}, powerSocaPhasePos: {},
                           powerSocaLengths: {}, powerSocaSplits: [], powerSocaNames: {},
                           powerBreakoutType: null, locked: false },
                      (o.walls || {})[key] || {});
        app.normalizePowerBreakout(l);
    }
    app.project.distros = (o.distros || []).map(d => JSON.parse(JSON.stringify(d)));
    app.project.cableUnit = o.cableUnit || 'ft';
    app._circuitTailCache = null;
    app._distroFaceMemo = null;
    app.getDistros();
    return app.project.layers.map(l => ({ id: l.id, circuits: app.screenCircuits(l).length }));
}"""

A = "window.app.project.layers.find(l => l.name === 'WALL A')"
B = "window.app.project.layers.find(l => l.name === 'WALL B')"


def setup(pg, **o):
    # The previous gesture's server echo lands first, so it cannot replace
    # the layers this setup writes.
    pg.wait_for_timeout(400)
    return pg.evaluate(SETUP_JS, o)


def ev(pg, body, arg=None):
    return pg.evaluate(f"(arg) => {{ const app = window.app; const A = {A}; const B = {B}; {body} }}", arg)


@pytest.fixture(scope="module")
def seeded(page):
    pg, errors = page
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(800)
    return pg, errors, ids


def test_the_page_loads_without_errors(page):
    pg, errors = page
    assert pg.evaluate("() => typeof window.app.distroFace === 'function'")
    assert not errors, errors


# ── migration (ruling 1) ──────────────────────────────────────────────────

def test_old_distros_migrate_to_their_system(seeded):
    """208 or 120 3φ -> 120/208; 230 or 400 3φ -> 230/400 (a 230V 3φ
    distro is 230/400 - bug fix 1); 120 1φ -> 120; 230 1φ -> 230. 110 and
    415 go to the nearest system; a pair naming no system unambiguously
    (208 1φ, 240 1φ, 220 3φ, 240 3φ) keeps the old arithmetic until picked."""
    pg, _, _ = seeded
    pairs = [[208, 3], [120, 3], [230, 3], [400, 3], [120, 1], [230, 1],
             [110, 3], [110, 1], [415, 3], [220, 1],
             [208, 1], [240, 1], [220, 3], [240, 3], [400, 1]]
    out = ev(pg, """
        return arg.map(([v, ph], i) => {
            const d = { id: 'm' + i, name: 'M', ratingA: 400, voltage: v, phase: ph };
            app._ensureDistroSystem(d);
            return [d.system, d.voltage, d.phase];
        });""", pairs)
    assert out == [
        ['120/208', 208, 3], ['120/208', 208, 3], ['230/400', 400, 3], ['230/400', 400, 3],
        ['120', 120, 1], ['230', 230, 1],
        ['120/208', 208, 3], ['120', 120, 1], ['230/400', 400, 3], ['230', 230, 1],
        [None, 208, 1], [None, 240, 1], [None, 220, 3], [None, 240, 3], [None, 400, 1],
    ], out


def test_a_migrated_208_show_computes_exactly_as_before(seeded):
    """A 208V 3φ distro feeding 208V screens: the same legs, the same
    line-to-line pairs, the same phasor amps it always had - only the header
    reads the worst leg now (bug fix 2)."""
    pg, _, _ = seeded
    setup(pg, distros=[{'id': 'd1', 'name': 'SL', 'ratingA': 400, 'voltage': 208, 'phase': 3}],
          walls={'a': {'powerSocaDistro': {'1': 'd1'}}})
    out = ev(pg, """
        const b = app.getDistroLoads().find(x => x.id === 'd1');
        const s = app.getSocaPlan(A)[0];
        // the pre-1.5 arithmetic, by hand: paired-ll, +-30 deg
        const ph = { X: {re: 0, im: 0}, Y: {re: 0, im: 0}, Z: {re: 0, im: 0} };
        const add = (k, a, deg) => { const r = deg * Math.PI / 180; ph[k].re += a * Math.cos(r); ph[k].im += a * Math.sin(r); };
        s.legs.forEach((g, i) => {
            const legs = app._circuitLegs(i + 1, 'paired-ll', 0, 6);
            const [f, t] = app._cyclicPair(legs[0], legs[1]);
            add(f, g.watts / 208, 30); add(t, g.watts / 208, -30);
        });
        const mag = (p) => Math.hypot(p.re, p.im);
        return { legs: [b.legs.X.amps, b.legs.Y.amps, b.legs.Z.amps],
                 hand: [mag(ph.X), mag(ph.Y), mag(ph.Z)], amps: b.amps,
                 balanced: b.balancedAmps, watts: b.watts, scheme: b.legs.schemeId,
                 system: app.getDistros()[0].system };""")
    assert out['system'] == '120/208'
    assert out['scheme'] == 'paired-ll'
    assert out['legs'] == pytest.approx(out['hand'], abs=1e-9), out
    assert out['amps'] == pytest.approx(max(out['legs']), abs=1e-9)
    assert out['balanced'] == pytest.approx(out['watts'] / (208 * 1.73), abs=1e-9)


def test_230v_circuits_on_230_400_are_line_to_neutral_one_leg_each(seeded):
    """Bug fix 1: a "230V 3φ" distro with 230V screens was booked
    phase-to-phase. A UK user means 230/400: every 230V circuit is one leg
    and the neutral, I = W / 230 on that leg alone."""
    pg, _, _ = seeded
    setup(pg, distros=[{'id': 'd1', 'name': 'UK', 'ratingA': 63, 'voltage': 230, 'phase': 3}],
          walls={'a': {'powerVoltage': 230, 'powerAmperage': 16, 'powerSocaDistro': {'1': 'd1'}}})
    out = ev(pg, """
        const d = app.getDistros()[0];
        const s = app.getSocaPlan(A)[0];
        const pos = app.socaCircuitPositions(A, s.soca, s.legs.length);
        const b = app.getDistroLoads()[0];
        return { system: d.system, voltage: d.voltage,
                 legs: s.legs.map((g, i) => app.distroCircuitLegs(d, A, s, i, pos).legs),
                 amps: s.legs.map(g => g.watts / 230),
                 load: [b.legs.X.amps, b.legs.Y.amps, b.legs.Z.amps], scheme: b.legs.schemeId };""")
    assert out['system'] == '230/400' and out['voltage'] == 400
    assert out['legs'] == [['X'], ['Y'], ['Z'], ['X'], ['Y'], ['Z']], out
    assert out['scheme'] == 'rotating-ln'
    a = out['amps']
    assert out['load'] == pytest.approx([a[0] + a[3], a[1] + a[4], a[2] + a[5]], abs=1e-9)


# ── the worst leg (bug fix 2) ───────────────────────────────────────────

WHOLE_SOCA_EU = {'id': 'd1', 'name': 'UK', 'system': '230/400', 'voltage': 400, 'phase': 3,
                 'ratingA': 63, 'phasing': 'whole-ln',
                 'outputRows': [{'id': 'r1', 'connector': 'soca', 'count': 3,
                                 'coupling': 'ln', 'breakerA': 16}]}


def test_a_whole_socapex_on_one_leg_flags_over_where_the_balanced_figure_would_not(seeded):
    """Six 2.5 kW circuits, a whole Socapex on L1 of a 63 A/leg 230/400
    distro: L1 carries 65 A - OVER - while W / (400 x 1.73) reads 21.7 A.
    The header, the OVER flag, the strip and the binder all read the leg."""
    pg, _, _ = seeded
    setup(pg, distros=[WHOLE_SOCA_EU],
          walls={'a': {'powerVoltage': 230, 'powerAmperage': 16, 'panelWatts': 250,
                       'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1}}})
    out = ev(pg, """
        app.renderHardwareDock();
        const b = app.getDistroLoads()[0];
        const unit = document.querySelector('[data-lrd-distro="d1"]');
        const legs = unit && unit.querySelector('.hw-dock-legs');
        return { amps: b.amps, balanced: b.balancedAmps, over: b.over, worst: b.worstLeg,
                 legs: [b.legs.X.amps, b.legs.Y.amps, b.legs.Z.amps],
                 head: unit.querySelector('.hw-dock-unit-use').textContent,
                 info: unit.querySelector('.hw-dock-unit-info').textContent,
                 legsLine: legs ? legs.textContent : null,
                 warn: (app._dockPowerWarnings || []).map(w => w.text) };""")
    assert out['legs'][1] == pytest.approx(0) and out['legs'][2] == pytest.approx(0), out
    assert out['amps'] == pytest.approx(15000 / 230, abs=1e-6), out
    assert out['over'] and out['worst'] == 'X'
    assert out['balanced'] == pytest.approx(15000 / (400 * 1.73), abs=1e-6)
    assert out['balanced'] < 63
    assert out['head'] == '65.2/63 A', out
    assert out['info'] == '230/400V·3φ'
    assert out['legsLine'].startswith('LEGSL1 65A'), out
    assert any('worst leg L1 65.2 A / 63 A' in w and 'OVER' in w for w in out['warn']), out


def test_the_screens_3_phase_readout_uses_the_services_line_voltage(seeded):
    """Bug fix 3: "Total Amps (3φ)" divided by the screen voltage as if it
    were line-to-line. A 120V screen rides 120/208: W / (208 x 1.73)."""
    pg, _, _ = seeded
    setup(pg, walls={'a': {'powerVoltage': 120, 'powerAmperage': 20}})
    out = ev(pg, """
        const saved = app.currentLayer;
        app.currentLayer = A;
        try { app.updatePowerCapacityDisplay(); } finally { app.currentLayer = saved; }
        const w = A.panels.filter(p => !p.blank && !p.hidden).length * 200;
        return { a3: A._powerTotalAmps3, w,
                 el: document.getElementById('power-total-amps-3ph').textContent };""")
    assert out['a3'] == pytest.approx(out['w'] / (208 * 1.73), abs=1e-9), out


# ── a voltage the system does not have (bug fix 4) ──────────────────────

def test_a_screen_voltage_the_system_lacks_is_refused_with_the_reason(seeded):
    pg, _, ids = seeded
    setup(pg, distros=[{'id': 'd1', 'name': 'SL', 'ratingA': 400, 'voltage': 208, 'phase': 3}],
          walls={'b': {'powerVoltage': 230, 'powerAmperage': 16}})
    out = ev(pg, """
        const d = app.getDistros()[0];
        const plan = app._plugDropPlan({ type: 'plug', distroId: 'd1', output: 'soca208',
                                         title: 'SL · Multi 208' }, B);
        app._dockDropTail({ distroId: 'd1', number: 1, tail: 1, title: 'SL 1 circuit 1' },
                          { kind: 'run', layerId: B.id, num: app.screenCircuits(B)[0].num });
        return { why: app.distroVoltageRefusal(d, B), plan,
                 assigned: Object.keys(B.powerSocaDistro || {}).length,
                 status: document.getElementById('status-message').textContent };""")
    want = 'WALL B runs at 230V — SL gives 120V or 208V. Set the screen to 208V.'
    assert out['why'] == want
    assert out['plan']['ok'] is False and out['plan']['message'] == want
    assert out['assigned'] == 0, out


# ── coupling (ruling 5) ───────────────────────────────────────────────────

def test_coupling_comes_from_the_system_and_the_connector(seeded):
    pg, _, _ = seeded
    out = ev(pg, """
        const sys = (id) => app.distroSystemById(id);
        const c = (conn, s) => app.connectorCouplings(app.distroConnector(conn), sys(s))
            .map(o => `${o.coupling}${o.volts}`);
        const out = {};
        for (const s of ['120/208', '120/240', '120', '230/400', '230']) {
            out[s] = {};
            for (const k of ['soca', 'harting', 'l2130', 'true1', 'powercon20', 'powerconxx',
                             'edison', 'l520', 'l620', 'stagepin', 'cee16', 'cee32', 'schuko']) {
                out[s][k] = c(k, s);
            }
        }
        return out;""")
    us = out['120/208']
    assert us['stagepin'] == ['ln120'] and us['edison'] == ['ln120'] and us['l520'] == ['ln120']
    assert us['l620'] == ['ll208']
    assert us['true1'] == ['ln120', 'll208'] and us['powercon20'] == ['ln120', 'll208']
    assert us['soca'] == ['ln120', 'll208']
    assert us['l2130'] == ['ll208']
    assert us['schuko'] == [] and us['cee16'] == [] and us['harting'] == []
    assert out['120']['l620'] == [] and out['120']['true1'] == ['ln120']
    assert out['120/240']['l2130'] == []
    eu = out['230/400']
    for k in ('soca', 'harting', 'true1', 'powercon20', 'powerconxx', 'cee16', 'cee32', 'schuko'):
        assert eu[k] == ['ln230'], (k, eu[k])
    for k in ('edison', 'l520', 'l620', 'stagepin', 'l2130'):
        assert eu[k] == [], (k, eu[k])
    assert out['230'] == eu


def test_stage_pin_is_refused_at_208v(seeded):
    """ANSI E1.24: stage pin is never 208V. A stage pin row is 120V
    line-to-neutral only, and a 208V screen is refused on it, naming the
    standard."""
    pg, _, _ = seeded
    setup(pg, distros=[{'id': 'd1', 'name': 'SL', 'ratingA': 200, 'system': '120/208',
                        'outputRows': [{'connector': 'stagepin', 'count': 6, 'coupling': 'll'}]}])
    out = ev(pg, """
        const d = app.getDistros()[0];
        const rows = app.distroRows(d);
        const plan = app._plugDropPlan({ type: 'plug', distroId: 'd1', output: 'face:r1', title: 'x' }, A);
        return { coupling: rows[0].coupling, plan };""")
    assert out['coupling'] == 'ln', 'a stage pin row cannot be stored line-to-line'
    assert out['plan']['ok'] is False
    assert out['plan']['message'] == 'WALL A runs at 208V — stage pin is never 208V (ANSI E1.24)'


def test_powercon_xx_at_208v_warns(seeded):
    pg, _, _ = seeded
    setup(pg, distros=[{'id': 'd1', 'name': 'SL', 'ratingA': 200, 'system': '120/208',
                        'outputRows': [{'connector': 'powerconxx', 'count': 3, 'coupling': 'll'}]}])
    warn = ev(pg, "return app.distroChecks(app.getDistros()[0]).map(w => w.text);")
    assert "powerCON XX is only US-listed to 127V — SL's 3 powerCON XX outputs run at 208V." in warn
    setup(pg, distros=[{'id': 'd1', 'name': 'SL', 'ratingA': 200, 'system': '120/208',
                        'outputRows': [{'connector': 'powerconxx', 'count': 3, 'coupling': 'ln'}]}])
    warn = ev(pg, "return app.distroChecks(app.getDistros()[0]).map(w => w.text);")
    assert not [w for w in warn if 'XX' in w], warn


# ── breakers by region (ruling 6) ─────────────────────────────────────────

def _direct_load(pg, distro, volts, watts, amps=20):
    # WALL B's first circuit pinned onto output 1 (a direct output).
    setup(pg, distros=[distro],
          walls={'b': {'powerVoltage': volts, 'powerAmperage': amps, 'panelWatts': watts,
                       'powerSocaSplits': [1],
                       'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1}}})
    return ev(pg, """
        const d = app.getDistros()[0];
        const s = app.getSocaPlan(B)[0];
        return { amps: s.legs[0].amps, legs: s.legs.length,
                 label: s.legs[0].label,
                 warn: app.distroChecks(d).map(w => w.text) };""")


def test_us_circuits_are_checked_at_80_percent_unless_breakers_are_100_rated(seeded):
    pg, _, _ = seeded
    dist = {'id': 'd1', 'name': 'SL', 'ratingA': 30, 'system': '120/208',
            'outputRows': [{'connector': 'true1', 'count': 3, 'coupling': 'll', 'breakerA': 20}]}
    # 6 x 600 W = 3600 W at 208 = 17.3 A: over 16 A (80% of 20), under 20.
    out = _direct_load(pg, dist, 208, 600)
    assert out['legs'] == 1 and out['amps'] == pytest.approx(3600 / 208)
    assert out['label'] == 'SL1', 'a direct output names its circuit with no tail'
    assert [w for w in out['warn'] if 'over the 80% continuous limit (16 A)' in w], out
    out = _direct_load(pg, dict(dist, breakers100=True), 208, 600)
    assert not [w for w in out['warn'] if 'breaker' in w], out
    # 6 x 700 W = 4200 W at 208 = 20.2 A: over even a 100%-rated 20 A.
    out = _direct_load(pg, dict(dist, breakers100=True), 208, 700, amps=25)
    assert [w for w in out['warn'] if 'on a 20 A breaker — OVER' in w], out


def test_eu_circuits_are_checked_at_the_breaker_and_true1_at_16a(seeded):
    pg, _, _ = seeded
    dist = {'id': 'd1', 'name': 'UK', 'ratingA': 63, 'system': '230/400',
            'outputRows': [{'connector': 'true1', 'count': 3, 'coupling': 'ln', 'breakerA': 16}]}
    # 6 x 580 W = 3480 W at 230 = 15.1 A: under the 16 A breaker, no 80%.
    out = _direct_load(pg, dist, 230, 580)
    assert not [w for w in out['warn'] if 'breaker' in w or 'rated' in w], out
    # 6 x 650 W = 3900 W = 17.0 A: over the breaker and over a True1's 16 A.
    out = _direct_load(pg, dist, 230, 650)
    assert [w for w in out['warn'] if 'on a 16 A breaker — OVER' in w], out
    assert [w for w in out['warn'] if 'a True1 is rated 16 A here' in w], out


# ── legs (ruling 4) ─────────────────────────────────────────────────────

def test_direct_outputs_rotate_x_y_z(seeded):
    """'6 True1 at 110, each on its own leg': direct outputs take the legs
    X Y Z X Y Z in face order; paired order is X X Y Y Z Z."""
    pg, _, _ = seeded
    dist = {'id': 'd1', 'name': 'SL', 'ratingA': 200, 'system': '120/208',
            'outputRows': [{'connector': 'true1', 'count': 6, 'coupling': 'ln'}]}
    rot = ev(pg, """
        app.project.distros = [arg]; app._distroFaceMemo = null;
        const d = app.getDistros()[0];
        const face = app.distroFace(d);
        const one = () => face.boxes.map(b => app._faceCircuitLegs(d, b, 1).legs.join(''));
        const r = one();
        d.directPhasing = 'paired';
        const p = app.faceBox(d, 1) && app.distroFace(d).boxes.map(b => app._faceCircuitLegs(d, b, 1).legs.join(''));
        return { r, p };""", dist)
    assert rot['r'] == ['X', 'Y', 'Z', 'X', 'Y', 'Z'], rot
    assert rot['p'] == ['X', 'X', 'Y', 'Y', 'Z', 'Z'], rot


def test_whole_multi_on_one_leg_is_offered_on_eu_distros_only(seeded):
    pg, _, _ = seeded
    out = ev(pg, """
        app.project.distros = [
            { id: 'us', name: 'US', ratingA: 400, system: '120/208', voltage: 208, phase: 3 },
            { id: 'eu', name: 'EU', ratingA: 63, system: '230/400', voltage: 400, phase: 3 }];
        const [us, eu] = app.getDistros();
        const opts = (d, v) => app._distroPhasingOptions(
            app.distroPhasingState(Object.assign(d, {})), d).map(s => s.id);
        const before = { us: opts(us), eu: opts(eu) };
        app.updateDistro('us', { phasing: 'whole-ln' });
        app.updateDistro('eu', { phasing: 'whole-ln' });
        const legs = [1, 2, 3, 4].map(n => app.distroCircuitLegs(eu, A, { number: n }, 0, [1]).legs[0]);
        return { before, us: app.getDistros()[0].phasing, eu: app.getDistros()[1].phasing, legs };""")
    assert 'whole-ln' not in out['before']['us'], out
    assert 'whole-ln' in out['before']['eu'], out
    assert out['us'] is None, 'a US distro cannot keep whole multi on one leg'
    assert out['eu'] == 'whole-ln'
    assert out['legs'] == ['X', 'Y', 'Z', 'X'], out


# ── paired rows (ruling 7) ────────────────────────────────────────────────

PAIRED = {'id': 'd1', 'name': 'UK', 'ratingA': 63, 'system': '230/400',
          'outputRows': [{'id': 'r1', 'connector': 'soca', 'count': 2, 'coupling': 'ln', 'breakerA': 16},
                         {'id': 'r2', 'connector': 'harting', 'count': 2, 'coupling': 'ln',
                          'pairedWith': 'r1'},
                         {'id': 'r3', 'connector': 'schuko', 'count': 9, 'coupling': 'ln'}]}


def test_paired_rows_count_once_and_take_their_partners_legs(seeded):
    pg, _, _ = seeded
    walls = {'a': {'powerVoltage': 230, 'powerAmperage': 16, 'powerSocaDistro': {'1': 'd1'},
                   'powerSocaNumber': {'1': 3}}}
    setup(pg, distros=[PAIRED], walls=walls)
    on_harting = ev(pg, """
        const b = app.getDistroLoads()[0];
        const face = app.distroFace(app.getDistros()[0]);
        return { legs: [b.legs.X.amps, b.legs.Y.amps, b.legs.Z.amps], watts: b.watts,
                 boxes: face.boxes.length, n3: face.byNumber.get(3).conn.id,
                 breaker: face.byNumber.get(3).breakerA,
                 checks: app.distroChecks(app.getDistros()[0]).map(w => w.text) };""")
    walls['a']['powerSocaNumber'] = {'1': 1}
    setup(pg, distros=[PAIRED], walls=walls)
    on_soca = ev(pg, """
        const b = app.getDistroLoads()[0];
        return { legs: [b.legs.X.amps, b.legs.Y.amps, b.legs.Z.amps], watts: b.watts };""")
    assert on_harting['boxes'] == 13 and on_harting['n3'] == 'harting'
    assert on_harting['breaker'] == 16, 'a paired row shares its partner\'s breakers'
    assert on_harting['legs'] == pytest.approx(on_soca['legs'], abs=1e-9)
    assert on_harting['watts'] == on_soca['watts']
    assert not [w for w in on_harting['checks'] if 'paired' in w], on_harting


def test_a_circuit_is_patched_to_one_connector_not_both(seeded):
    pg, _, _ = seeded
    # WALL A on Harting 3 (circuits of Socapex 1); WALL B tries Socapex 1.
    setup(pg, distros=[PAIRED],
          walls={'a': {'powerVoltage': 230, 'powerAmperage': 16, 'powerSocaDistro': {'1': 'd1'},
                       'powerSocaNumber': {'1': 3}},
                 'b': {'powerVoltage': 230, 'powerAmperage': 16}})
    out = ev(pg, """
        const plan = app._socaTakePlan(B, 1, 'd1', 1);
        const text = app._takeRefusalText({ title: 'UK 1' }, plan, 'S1-3', B);
        // and when a file already has both, the strip says so
        B.powerSocaDistro = { 1: 'd1' }; B.powerSocaNumber = { 1: 1 };
        app._circuitTailCache = null;
        const checks = app.distroChecks(app.getDistros()[0]).map(w => w.text);
        return { ok: plan.ok, why: plan.why, text, checks };""")
    assert out['ok'] is False and out['why'] == 'paired', out
    assert 'shares its circuits with UK3-1 (paired)' in out['text'], out
    assert [w for w in out['checks'] if 'one circuit on two connectors (paired)' in w], out


# ── faces, numbering, drops ─────────────────────────────────────────────

def test_auto_multis_land_on_the_face_box_that_fits(seeded):
    """On a face of 8 Socapex 120V then 8 Socapex 208V, a 208V screen's
    multis take 9 and 10 and a 120V screen's take 1 - never a 120V Socapex
    for a 208V screen, never a direct output."""
    pg, _, _ = seeded
    pre = ev(pg, "return app.builtInDistroPresets().find(p => p.id === 'us-400-8soca120-8soca208');")
    dist = {'id': 'd1', 'name': 'PR', 'ratingA': 400, 'system': pre['system'],
            'outputRows': pre['rows']}
    setup(pg, distros=[dist],
          walls={'a': {'powerVoltage': 208, 'powerSocaDistro': {'1': 'd1'}},
                 'b': {'powerVoltage': 120, 'powerSocaDistro': {'1': 'd1'}}})
    out = ev(pg, """return { a: app.getSocaPlan(A).map(s => [s.number, s.name]),
                             b: app.getSocaPlan(B).map(s => [s.number, s.name]) };""")
    assert out['a'][0] == [9, 'PR9'], out
    assert out['b'][0] == [1, 'PR1'], out


def test_a_direct_row_drop_takes_one_circuit_pinned(seeded):
    pg, _, _ = seeded
    dist = {'id': 'd1', 'name': 'SL', 'ratingA': 30, 'system': '120/208',
            'outputRows': [{'connector': 'true1', 'count': 3, 'coupling': 'll'}]}
    setup(pg, distros=[dist], walls={'b': {'powerAmperage': 6}})
    out = ev(pg, """
        const payload = { type: 'plug', distroId: 'd1', output: 'face:r1', title: 'SL · True1 208V' };
        const plan = app._plugDropPlan(payload, B);
        app._dockDropPlug(payload, { kind: 'screen', layerId: B.id });
        app._dockDropPlug(payload, { kind: 'screen', layerId: B.id });
        app._circuitTailCache = null;
        return { plan: plan.text, ok: plan.ok,
                 plan2: app.getSocaPlan(B).map(s => [s.legs.map(g => g.circuit), s.distroId, s.number, s.name]),
                 labels: app.screenCircuits(B).map(c => app.getPowerCircuitLabel(B, c.num)) };""")
    assert out['ok'] and out['plan'].startswith('SL 1 → circuit 1'), out
    assert out['plan2'][0] == [[1], 'd1', 1, 'SL1'], out
    assert out['plan2'][1] == [[2], 'd1', 2, 'SL2'], out
    assert out['labels'][:2] == ['SL1', 'SL2'], out


def test_a_locked_screen_refuses_a_face_drop(seeded):
    pg, _, _ = seeded
    dist = {'id': 'd1', 'name': 'SL', 'ratingA': 30, 'system': '120/208',
            'outputRows': [{'connector': 'true1', 'count': 3, 'coupling': 'll'}]}
    setup(pg, distros=[dist], walls={'b': {'locked': True}})
    out = ev(pg, """
        app._dockDropPlug({ type: 'plug', distroId: 'd1', output: 'face:r1', title: 'x' },
                          { kind: 'screen', layerId: B.id });
        return { assigned: Object.keys(B.powerSocaDistro).length,
                 toast: document.body.innerText.includes('WALL B is locked - unlock it to change it.') };""")
    assert out['assigned'] == 0
    assert out['toast'], 'the locked screen was not named'
    setup(pg)


def test_the_dock_shows_the_face(seeded):
    pg, _, _ = seeded
    p = ev(pg, "return app.builtInDistroPresets().find(p => p.id === 'us-200-4soca-3dup');")
    setup(pg, distros=[{'id': 'd1', 'name': 'SL', 'ratingA': 200, 'system': p['system'],
                        'input': p['input'], 'outputRows': p['rows']}],
          walls={'a': {'powerSocaDistro': {'1': 'd1'}}})
    out = ev(pg, """
        app.renderHardwareDock();
        const unit = document.querySelector('[data-lrd-distro="d1"]');
        return {
            plugs: [...unit.querySelectorAll('.hw-dock-outputs .hw-dock-plug')].map(e => e.textContent),
            multis: unit.querySelectorAll('.hw-dock-multi:not(.hw-dock-direct)').length,
            direct: [...unit.querySelectorAll('.hw-dock-direct .lrd-tile')].length,
            directHead: (unit.querySelector('.hw-dock-direct .hw-dock-unit-name') || {}).textContent,
            type: (unit.querySelector('.hw-dock-typechip b') || {}).textContent,
        };""")
    assert out['plugs'] == ['Socapex 208V× 4', 'Edison× 6'], out
    assert out['multis'] == 4 and out['direct'] == 6, out
    assert out['directHead'] == 'Edison × 6'
    assert out['type'] == 'Socapex 208V'


def test_the_gear_builds_rows_and_presets(seeded):
    pg, _, _ = seeded
    setup(pg, distros=[{'id': 'd1', 'name': 'SL', 'ratingA': 400, 'voltage': 208, 'phase': 3}])
    out = ev(pg, """
        app.renderHardwareDock();
        document.querySelector('[data-hwpop="distro-d1"]').click();
        const pop = document.getElementById('hw-gear-popover');
        const sys = pop.querySelector('[data-lrd-field="distro-system-d1"]');
        const presets = pop.querySelector('[data-lrd-field="distro-preset-d1"]');
        const r = { system: sys.value, systems: [...sys.options].map(o => o.textContent),
                    presets: [...presets.querySelectorAll('optgroup')[0].children].map(o => o.textContent),
                    legacy: !!pop.querySelector('[data-lrd-field="distro-out-soca208-d1"]') };
        pop.querySelector('[data-lrd-field="distro-row-add-d1"]').click();
        r.rows = app.getDistros()[0].outputRows;
        app._hwPopoverClose();
        return r;""")
    assert out['system'] == '120/208'
    assert out['systems'] == ['120/208V 3φ', '120/240V 1φ split-phase', '120V 1φ',
                              '230/400V 3φ', '230V 1φ']
    assert len(out['presets']) == 11
    assert out['legacy'], 'a distro with no rows keeps the old type checklist'
    assert out['rows'] == [{'id': 'r1', 'connector': 'soca', 'count': 1, 'coupling': 'll',
                            'breakerA': 20, 'connectorA': None, 'pairedWith': None}], out


# ── presets (ruling 8) ────────────────────────────────────────────────────

# Named plainly (ruling 8): what the face is - the service or input, then
# its outputs - never who builds or rents it.
PLAIN_NAME = re.compile(r'^(\d+A 3φ|L21-30 spider): [0-9 ×+,()/A-Za-z-]+$')


def test_the_eleven_presets_apply_cleanly_and_are_named_plainly(seeded):
    pg, _, _ = seeded
    setup(pg, distros=[{'id': 'd1', 'name': 'P', 'ratingA': 400, 'voltage': 208, 'phase': 3}])
    out = ev(pg, """
        return app.builtInDistroPresets().map(p => {
            app.applyDistroPreset('d1', p);
            const d = app.getDistros()[0];
            const face = app.distroFace(d);
            return { id: p.id, name: p.name, system: d.system, rating: d.ratingA, input: d.input,
                     rows: app.distroRows(d).length, want: p.rows.length,
                     paired: app.distroRows(d).filter(r => r.pairedWith).length,
                     wantPaired: p.rows.filter(r => r.pairedWith).length,
                     boxes: face.boxes.length, phasing: d.phasing || null };
        });""")
    assert len(out) == 11
    for p in out:
        assert p['rows'] == p['want'] and p['paired'] == p['wantPaired'], p
        assert p['input'] and p['rating'] > 0, p
        assert PLAIN_NAME.match(p['name']), p['name']
    by = {p['id']: p for p in out}
    assert by['us-200-4soca-3dup']['boxes'] == 10
    assert by['eu-63-3soca-true1']['phasing'] == 'whole-ln'
    assert by['eu-400-6soca']['phasing'] == 'whole-ln'
    assert by['us-l2130-3true1']['rating'] == 30


def test_a_distro_saves_as_a_preset_and_comes_back(seeded):
    pg, _, _ = seeded
    setup(pg, distros=[{'id': 'd1', 'name': 'P', 'ratingA': 400, 'voltage': 208, 'phase': 3},
                       {'id': 'd2', 'name': 'Q', 'ratingA': 400, 'voltage': 208, 'phase': 3}])
    out = pg.evaluate("""async () => {
        const app = window.app;
        app.applyDistroPreset('d1', app.builtInDistroPresets().find(p => p.id === 'eu-63-2soca-9schuko'));
        app.updateDistro('d1', { ratingA: 50 });
        const saved = await app.saveDistroPreset('d1', 'Our  UK rack');
        const listed = await app.loadCustomDistroPresets(true);
        app.applyDistroPreset('d2', listed.find(p => p.name === 'Our UK rack'));
        const [d1, d2] = app.getDistros();
        const r = { names: saved.map(p => p.name), same: JSON.stringify(app.distroRows(d1)) === JSON.stringify(app.distroRows(d2)),
                    rating: d2.ratingA, system: d2.system };
        const left = await app.deleteDistroPreset('Our UK rack');
        r.after = left.map(p => p.name);
        return r;
    }""")
    assert 'Our UK rack' in out['names'], out
    assert out['same'] and out['rating'] == 50 and out['system'] == '230/400', out
    assert 'Our UK rack' not in out['after']


# ── paperwork ─────────────────────────────────────────────────────────────

def test_a_direct_output_cable_is_on_the_pull_sheet_in_the_shows_unit(seeded):
    pg, _, _ = seeded
    dist = {'id': 'd1', 'name': 'SL', 'ratingA': 63, 'system': '230/400',
            'outputRows': [{'connector': 'schuko', 'count': 4, 'coupling': 'ln'}]}
    for unit, want in (('m', '8 m'), ('ft', "8'")):
        setup(pg, distros=[dist], cableUnit=unit,
              walls={'b': {'powerVoltage': 230, 'powerAmperage': 16, 'powerSocaSplits': [1],
                           'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 2},
                           'powerSocaLengths': {'1': '8'}}})
        out = ev(pg, """
            const list = app.buildPullList();
            const rows = list.positions.flatMap(p => p.rows);
            const hw = (list.hardware.find(h => h.kind === 'distro') || { rows: [] }).rows;
            B.showPowerCableTags = true;
            const tag = app.directOutputCable(B, app.screenCircuits(B)[0].num);
            return { rows: rows.map(r => [r.type, r.length, r.qty, r.label, r.notes]),
                     hw: hw.map(r => [r.type, r.length, r.label, r.notes]), tag: tag && tag.text };""")
        assert ['Schuko', want, 1, 'SL 2', ''] in out['rows'], out
        assert not [r for r in out['rows'] if 'Breakout' in r[0] or r[0] == 'Multi'], out
        assert ['Distro', 'EA', 'SL', '1 direct output'] in out['hw'], out
        assert out['tag'] == f'{want} Schuko', out


def test_the_binder_prints_the_face_once_with_paired_rows_together(seeded):
    pg, _, _ = seeded
    setup(pg, distros=[dict(PAIRED, input='cee63')],
          walls={'a': {'powerVoltage': 230, 'powerAmperage': 16, 'powerSocaDistro': {'1': 'd1'},
                       'powerSocaNumber': {'1': 1}}})
    out = ev(pg, """
        const d = app.getDistros()[0];
        return { rating: app._bDistroRatingText(d), lines: app._bDistroFaceLines(d),
                 legacy: app._bDistroRatingText({ ratingA: 400, voltage: 208, phase: 3 }) };""")
    assert out['rating'] == '63 A per leg · 230/400V 3φ · CEE 63 A red', out
    assert out['lines'] == [
        '2 × Socapex 230V / 2 × Harting 16E 230V (paired) · 12 circuits · 16 A',
        '9 × Schuko · 9 direct circuits · 16 A'], out
    assert out['legacy'] == '400 A 208 V 3φ'


def test_every_binder_sheet_draws_a_face_distro_and_its_direct_output(seeded):
    """The binder's distro sheet lists the face; the power and wiring sheets
    name a direct output by its connector, with its cable length - one
    socket, no breakout."""
    pg, _, _ = seeded
    dist = {'id': 'd1', 'name': 'SL', 'ratingA': 63, 'system': '230/400', 'input': 'cee63',
            'outputRows': [{'connector': 'soca', 'count': 2, 'coupling': 'ln'},
                           {'connector': 'schuko', 'count': 4, 'coupling': 'ln'}]}
    setup(pg, distros=[dist], cableUnit='m',
          walls={'a': {'powerVoltage': 230, 'powerAmperage': 16, 'powerSocaDistro': {'1': 'd1'}},
                 'b': {'powerVoltage': 230, 'powerAmperage': 6, 'powerSocaSplits': [1],
                       'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 4},
                       'powerSocaLengths': {'1': '8'}}})
    out = ev(pg, """
        const opts = app.readBinderOptions();
        const plan = app.planBinder(opts);
        const texts = [];
        let wiring = null;
        for (let i = 0; i < plan.length; i++) {
            const pg = app.renderBinderPage(opts, i);
            texts.push(...pg.texts);
            if (pg.wiring && !wiring) wiring = pg.wiring;
        }
        const facts = app._bwPowerFacts({ list: app.buildPullSheet() }, B,
            app.buildPullSheet().byScreen[B.id]);
        return { texts, devices: facts.devices.map(d => [d.title, d.n]) };""")
    t = out['texts']
    assert '63 A per leg · 230/400V 3φ · CEE 63 A red' in t, [x for x in t if 'per leg' in x]
    assert '4 × Schuko · 4 direct circuits · 16 A' in t, [x for x in t if 'Schuko' in x]
    assert ['SL4 · Schuko · 8 m', 1] in out['devices'], out['devices']
