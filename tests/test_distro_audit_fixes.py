"""Distro fixes from the 1.5 audit, each pinned to its repro.

  * a multi left on a one-circuit direct output (the rows changed under
    it) is said in the strip, keeps its circuits apart (no false pairing
    with the next output, no summed breaker line) and its labels apart
  * a single-phase distro's header and legs read its circuits' own amps,
    so an old 110V show keeps its 1.4.1 figure; three-phase is unchanged
  * an L21-30 box on an old 208V 1φ distro keeps its 30 A/leg feed check
  * an EU distro's phasing select reads L1/L2/L3
  * a distro carrying its system but no voltage takes it from the system
  * Preferences pick a new distro's SYSTEM, and the old voltage + phase
    pair reads as the system it maps to

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_distro_audit_fixes.py -q --browser chromium
"""

import math

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project and preferences as this module
    found them."""


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
    pg.wait_for_function("() => window.app && window.app.project "
                         "&& typeof window.app.distroFace === 'function'")
    pg.locator('[data-mode="power"]').click()
    yield pg, errors
    context.close()


# WALL A 10 wide x 6 rows (six circuits, one per row), WALL B 6 x 3.
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
    return p.layers.length;
}"""

# Reshape the show in the page; every assignment cleared first.
SETUP_JS = """(o) => {
    const app = window.app;
    for (const l of app.project.layers) {
        const key = l.name === 'WALL A' ? 'a' : 'b';
        Object.assign(l, { powerVoltage: 208, powerAmperage: 20, panelWatts: 200,
                           powerSocaDistro: {}, powerSocaNumber: {}, powerSocaPhasePos: {},
                           powerSocaLengths: {}, powerSocaSplits: [], powerSocaNames: {},
                           powerLabelOverrides: {}, powerBreakoutType: null, locked: false },
                      (o.walls || {})[key] || {});
        app.normalizePowerBreakout(l);
    }
    app.project.distros = (o.distros || []).map(d => JSON.parse(JSON.stringify(d)));
    app.project.cableUnit = 'ft';
    app._circuitTailCache = null;
    app._distroFaceMemo = null;
    app.getDistros();
    return app.project.layers.map(l => app.screenCircuits(l).length);
}"""

A = "window.app.project.layers.find(l => l.name === 'WALL A')"
B = "window.app.project.layers.find(l => l.name === 'WALL B')"


def setup(pg, **o):
    # Nothing of this module's own may still be in flight to the server.
    pg.wait_for_function("() => window.app._layerSavesSettled()")
    return pg.evaluate(SETUP_JS, o)


def ev(pg, body, arg=None):
    return pg.evaluate(
        f"(arg) => {{ const app = window.app; const A = {A}; const B = {B}; {body} }}", arg)


@pytest.fixture(scope="module")
def seeded(page):
    pg, errors = page
    assert pg.evaluate(SEED_JS) == 2
    pg.wait_for_function("() => window.app.project.layers.length === 2")
    return pg, errors


def test_the_page_loads_without_errors(seeded):
    _, errors = seeded
    assert not errors, errors


# ── a multi on a one-circuit direct output ─────────────────────────────────

FACE = {'id': 'd1', 'name': 'PD', 'ratingA': 200, 'system': '120/208',
        'outputRows': [{'id': 'r1', 'connector': 'true1', 'count': 3, 'coupling': 'll',
                        'breakerA': 20},
                       {'id': 'r2', 'connector': 'soca', 'count': 2, 'coupling': 'll',
                        'breakerA': 20}]}

# WALL A's six-circuit multi pinned on output 4 (a Socapex), WALL B's
# first circuit cut off on its own and pinned on output 5 (the other one).
# At 10 A a circuit is one row of ten cabinets (9.6 A at 208V), so WALL A
# makes six circuits and every circuit sits inside its 80% breaker figure.
WALLS = {'a': {'powerAmperage': 10, 'powerSocaDistro': {'1': 'd1'},
               'powerSocaNumber': {'1': 4}},
         'b': {'powerAmperage': 10, 'powerSocaSplits': [1], 'powerSocaDistro': {'1': 'd1'},
               'powerSocaNumber': {'1': 5}}}

READ_FACE = """
    const d = app.getDistros()[0];
    app._circuitTailCache = null;
    app.renderHardwareDock();
    const face = app.distroFace(d);
    const sa = app.getSocaPlan(A)[0], sb = app.getSocaPlan(B)[0];
    const pa = app.socaCircuitPositions(A, sa.soca, sa.legs.length);
    const keyOf = (s, t) => app._facePhysical(face, app.faceBox(d, s.number), t).key;
    return {
        kinds: [4, 5].map(n => face.byNumber.get(n).kind),
        aCircuits: sa.legs.length, bCircuits: sb.legs.length,
        aLabels: sa.legs.map(g => g.label),
        aKeys: pa.map(t => keyOf(sa, t)), bKey: keyOf(sb, 1),
        aLegs: sa.legs.map((g, i) => app.distroCircuitLegs(d, A, sa, i, pa).legs.join('')),
        checks: app.distroChecks(d).map(w => w.text),
        strip: (app._dockPowerWarnings || []).map(w => w.text),
        watts: app.getDistroLoads()[0].watts,
        wattsA: sa.watts + sb.watts,
    };"""


def test_a_multi_left_on_a_direct_output_is_said_and_kept_apart(seeded):
    """Rows True1 x3 + Socapex x2: a six-circuit multi on output 4 and a
    one-circuit screen on output 5. Raising True1 3 -> 5 leaves both on
    True1s. The six circuits used to read PD4 on one leg pair, with their
    tails 2-6 aliasing outputs 5-9 - a false "paired" line for PD4 + PD5
    and a breaker line summing both screens."""
    pg, _ = seeded
    assert setup(pg, distros=[FACE], walls=WALLS) == [6, 3]
    before = ev(pg, READ_FACE)
    assert before['kinds'] == ['multi', 'multi']
    assert not [c for c in before['checks'] if 'one circuit only' in c or 'paired' in c], before

    ev(pg, """
        const rows = app.getDistros()[0].outputRows.map(r => ({ ...r }));
        rows[0].count = 5;
        app.updateDistro('d1', { outputRows: rows });
        return true;""")
    out = ev(pg, READ_FACE)
    assert out['kinds'] == ['direct', 'direct'], out
    assert out['aCircuits'] == 6 and out['bCircuits'] == 1
    name_a = 'PD4'
    want = (f"WALL A's 6 circuits are on {name_a}, a True1 — one circuit only. "
            'Move it to a multi output.')
    assert want in out['checks'], out['checks']
    assert want in out['strip'], 'the dock strip carries the check'
    assert out['checks'].count(want) == 1
    # WALL B's one circuit on its True1 is fine.
    assert not [c for c in out['checks'] if c.startswith('WALL B')], out['checks']
    # Never a pairing that is not there, never a breaker line summing the two.
    assert not [c for c in out['checks'] if 'paired' in c], out['checks']
    assert not [c for c in out['checks'] if ' + ' in c], out['checks']
    # Keys: A's circuits never share B's (or each other's).
    assert out['bKey'] not in out['aKeys'], out
    assert len(set(out['aKeys'])) == 6, out
    # Legs: the output's own pair (True1 #4 of a rotating LL face: XY),
    # each circuit booked once - nothing dropped, nothing doubled.
    assert out['aLegs'] == ['XY'] * 6, out
    assert out['watts'] == pytest.approx(out['wattsA'])
    # Labels stay apart: six circuits, six names.
    assert len(set(out['aLabels'])) == 6, out['aLabels']
    assert out['aLabels'][0] == 'PD4-1', out['aLabels']


def test_a_socapex_row_turned_true1_under_a_multi_is_said(seeded):
    """The other way in: the Socapex row's connector changed to True1
    while the multi sits on it."""
    pg, _ = seeded
    setup(pg, distros=[FACE], walls=WALLS)
    ev(pg, """
        const rows = app.getDistros()[0].outputRows.map(r => ({ ...r }));
        rows[1].connector = 'true1';
        app.updateDistro('d1', { outputRows: rows });
        return true;""")
    out = ev(pg, READ_FACE)
    assert out['kinds'] == ['direct', 'direct'], out
    assert ("WALL A's 6 circuits are on PD4, a True1 — one circuit only. "
            'Move it to a multi output.') in out['checks'], out['checks']
    assert not [c for c in out['checks'] if 'paired' in c], out['checks']


def test_a_legal_direct_output_keeps_its_plain_label(seeded):
    """One circuit on one direct output still reads as the output - "PD5",
    no tail."""
    pg, _ = seeded
    setup(pg, distros=[dict(FACE, outputRows=[dict(FACE['outputRows'][0], count=5),
                                              FACE['outputRows'][1]])],
          walls={'b': WALLS['b']})
    out = ev(pg, """
        const sb = app.getSocaPlan(B)[0];
        return { label: sb.legs[0].label, n: sb.legs.length,
                 checks: app.distroChecks(app.getDistros()[0]).map(w => w.text) };""")
    assert out['n'] == 1 and out['label'] == 'PD5', out
    assert not out['checks'], out


# ── single-phase header amps ──────────────────────────────────────────────

READ_LOAD = """
    const b = app.getDistroLoads().find(x => x.id === 'd1');
    const plan = app.getSocaPlan(A);
    return { amps: b.amps, balanced: b.balancedAmps, watts: b.watts,
             legs: b.legs ? b.legs.names.map(k => b.legs[k].amps) : null,
             circuits: plan.reduce((t, s) => t + s.legs.reduce((u, g) => u + g.amps, 0), 0),
             system: app.getDistros()[0].system, voltage: app.getDistros()[0].voltage };"""


@pytest.mark.parametrize('old_v,screen_v,system', [(110, 110, '120'), (220, 220, '230')])
def test_an_old_single_phase_show_keeps_its_header_amps(seeded, old_v, screen_v, system):
    """An old 110V 1φ distro is a 120V system now; its 110V circuits still
    draw at 110V, and the header sums them - W / 110, the 1.4.1 figure -
    where it read W / 120, 8% low. 220V 1φ -> 230V the same way."""
    pg, _ = seeded
    setup(pg, distros=[{'id': 'd1', 'name': 'OLD', 'ratingA': 400, 'voltage': old_v, 'phase': 1}],
          walls={'a': {'powerVoltage': screen_v, 'powerSocaDistro': {'1': 'd1'}}})
    out = ev(pg, READ_LOAD)
    assert out['system'] == system, out
    assert out['amps'] == pytest.approx(out['watts'] / screen_v, abs=1e-9), out
    assert out['amps'] == pytest.approx(out['circuits'], abs=1e-9), \
        'the header agrees with its circuits'
    assert out['balanced'] == pytest.approx(out['amps'], abs=1e-9)


def test_a_120_240_split_reads_its_240v_circuits_at_their_own_voltage(seeded):
    """Split-phase line-to-line: each leg carries the circuit's amps at the
    circuit's own voltage (a 230V screen on 120/240 reads W / 230 on X and
    Y, the figure its circuit lines print)."""
    pg, _ = seeded
    for screen_v in (240, 230):
        setup(pg, distros=[{'id': 'd1', 'name': 'SPLIT', 'ratingA': 200, 'system': '120/240'}],
              walls={'a': {'powerVoltage': screen_v, 'powerSocaDistro': {'1': 'd1'}}})
        out = ev(pg, READ_LOAD)
        assert out['legs'] == pytest.approx([out['watts'] / screen_v] * 2, abs=1e-9), out
        assert out['amps'] == pytest.approx(out['circuits'], abs=1e-9), out


def test_three_phase_and_odd_old_records_are_unchanged(seeded):
    """120/208 keeps its line-to-line figure; an odd old 208V 1φ record
    (no system) keeps W / V."""
    pg, _ = seeded
    setup(pg, distros=[{'id': 'd1', 'name': 'SL', 'ratingA': 400, 'voltage': 208, 'phase': 3}],
          walls={'a': {'powerSocaDistro': {'1': 'd1'}}})
    three = ev(pg, READ_LOAD)
    assert three['balanced'] == pytest.approx(three['watts'] / (208 * 1.73), abs=1e-9)
    setup(pg, distros=[{'id': 'd1', 'name': 'ODD', 'ratingA': 400, 'voltage': 208, 'phase': 1}],
          walls={'a': {'powerVoltage': 120, 'powerSocaDistro': {'1': 'd1'}}})
    odd = ev(pg, READ_LOAD)
    assert odd['system'] is None
    assert odd['amps'] == pytest.approx(odd['watts'] / 208, abs=1e-9), odd


# ── L21-30 feed on an old 208V 1φ record ────────────────────────────────────

def test_an_l2130_box_on_an_old_208v_single_phase_distro_keeps_its_feed_check(seeded):
    """1.4.1 read every L21-30 box as three feed legs; 1.5 returned 0/0/0
    on any 1φ distro, so the 30 A/leg check never fired. Three full 208V
    circuits load each feed leg at I x sqrt(3)."""
    pg, _ = seeded
    setup(pg, distros=[{'id': 'd1', 'name': 'ODD', 'ratingA': 400, 'voltage': 208, 'phase': 1}],
          walls={'a': {'powerBreakoutType': 'l2130-true1', 'panelWatts': 400,
                       'powerSocaDistro': {'1': 'd1'}}})
    out = ev(pg, """
        const d = app.getDistros()[0];
        const s = app.getSocaPlan(A)[0];
        const fl = app.boxFeedLegAmps(d, [{ layer: A, s }]);
        app.renderHardwareDock();
        return { fl: [fl.X, fl.Y, fl.Z], circuits: s.legs.length,
                 amps: s.legs.map(g => g.watts / 208), system: d.system,
                 strip: (app._dockPowerWarnings || []).map(w => w.text) };""")
    assert out['system'] is None and out['circuits'] == 3, out
    i = out['amps'][0]
    assert out['fl'] == pytest.approx([i * math.sqrt(3)] * 3, abs=1e-6), out
    worst = max(out['fl'])
    assert worst > 30
    assert any(f'feed leg at {worst:.1f} A of 30 A — OVER' in w for w in out['strip']), out['strip']


# ── EU phasing select ─────────────────────────────────────────────────────

def test_the_eu_phasing_select_reads_l1_l2_l3(seeded):
    pg, _ = seeded
    setup(pg, distros=[{'id': 'd1', 'name': 'UK', 'ratingA': 63, 'system': '230/400'},
                       {'id': 'd2', 'name': 'US', 'ratingA': 200, 'system': '120/208'}],
          walls={'a': {'powerVoltage': 230, 'powerAmperage': 16, 'powerSocaDistro': {'1': 'd1'}},
                 'b': {'powerVoltage': 120, 'powerSocaDistro': {'1': 'd2'}}})
    out = ev(pg, """
        const opts = (id) => {
            const wrap = app._buildDistroGearContent(app.getDistros().find(d => d.id === id));
            const sel = wrap.querySelector(`[data-lrd-field="distro-phasing-${id}"]`);
            return [...sel.options].map(o => o.textContent);
        };
        return { eu: opts('d1'), us: opts('d2') };""")
    eu = ' | '.join(out['eu'])
    assert '(L1 L2 L3 L1 L2 L3)' in eu and '(L1 L1 L2 L2 L3 L3)' in eu, out['eu']
    assert not any(k in eu for k in ('X Y Z', 'X X Y Y')), out['eu']
    us = ' | '.join(out['us'])
    assert '(X Y Z X Y Z)' in us and '(X X Y Y Z Z)' in us, out['us']


# ── a system with no voltage ──────────────────────────────────────────────

def test_a_distro_with_a_system_and_no_voltage_takes_it_from_the_system(seeded):
    pg, _ = seeded
    setup(pg, distros=[{'id': 'd1', 'name': 'UK', 'ratingA': 63, 'system': '230/400'}],
          walls={'a': {'powerVoltage': 230, 'powerAmperage': 16,
                       'powerSocaDistro': {'1': 'd1'}}})
    out = ev(pg, """
        const d = app.getDistros()[0];
        const b = app.getDistroLoads()[0];
        return { v: d.voltage, ph: d.phase, amps: b.amps, balanced: b.balancedAmps,
                 watts: b.watts };""")
    assert out['v'] == 400 and out['ph'] == 3, out
    assert out['amps'] > 0
    assert out['balanced'] == pytest.approx(out['watts'] / (400 * 1.73), abs=1e-9)


# ── Preferences: the system picker ──────────────────────────────────────────

def test_old_preference_pairs_map_to_a_system(seeded):
    pg, _ = seeded
    pairs = {
        (120, 3): '120/208', (110, 3): '120/208', (208, 3): '120/208',
        (120, 1): '120', (110, 1): '120',
        (240, 1): '120/240',
        (230, 3): '230/400', (400, 3): '230/400', (415, 3): '230/400',
        (230, 1): '230', (220, 1): '230',
        (208, 1): '120/208', (240, 3): '120/208', (220, 3): '120/208', (999, 1): '120/208',
    }
    got = ev(pg, """return arg.map(([v, ph]) =>
        app.preferenceDistroSystem({ distroVoltage: v, distroPhase: ph }));""",
             [list(k) for k in pairs])
    assert got == list(pairs.values()), got
    assert ev(pg, "return app.preferenceDistroSystem({});") == '120/208'
    assert ev(pg, "return app.preferenceDistroSystem({ distroSystem: '230' });") == '230'


def test_a_new_distro_takes_the_preference_system(seeded):
    """The stored system wins; an old record's pair reads through the
    mapping; the Preferences select lists the distro's own five systems."""
    pg, _ = seeded
    setup(pg)
    out = ev(pg, """
        const saved = app._serverPreferences;
        try {
            app._serverPreferences = { distroVoltage: 240, distroPhase: 1, distroRatingA: 100 };
            const old = app.getPreferences().distroSystem;
            const d1 = app._distroPreferenceDefaults();
            app._serverPreferences = { distroSystem: '230', distroRatingA: 63 };
            const d2 = app._distroPreferenceDefaults();
            app._fillPreferenceCatalogs();
            const sel = document.getElementById('pref-distro-system');
            return { old, d1, d2,
                     options: [...sel.options].map(o => [o.value, o.textContent]),
                     gone: !document.getElementById('pref-distro-voltage')
                        && !document.getElementById('pref-distro-phase') };
        } finally {
            app._serverPreferences = saved;
        }""")
    assert out['old'] == '120/240', out
    assert out['d1'] == {'ratingA': 100, 'system': '120/240'}, out
    assert out['d2'] == {'ratingA': 63, 'system': '230'}, out
    assert [v for v, _ in out['options']] == ['120/208', '120/240', '120', '230/400', '230'], out
    assert out['gone']
    made = ev(pg, """
        const saved = app._serverPreferences;
        try {
            app._serverPreferences = { distroSystem: '230/400', distroRatingA: 63 };
            const d = app.addDistro({ name: 'NEW' });
            return { system: d.system, voltage: d.voltage, phase: d.phase, ratingA: d.ratingA };
        } finally {
            app._serverPreferences = saved;
        }""")
    assert made == {'system': '230/400', 'voltage': 400, 'phase': 3, 'ratingA': 63}, made
    pg.wait_for_function("() => window.app._layerSavesSettled()")
