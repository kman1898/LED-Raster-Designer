"""The neutral of a distro's power in, with LED supply harmonics
(owner's decision, 2026-11-11: "Estimate and warn").

The model (app-neutral.js):
  * A line-to-neutral circuit's current is the figure the app shows for it,
    watts over the circuit's own voltage. Line-to-line circuits put nothing
    on the neutral.
  * Fundamental: the phasor sum of the legs' line-to-neutral currents, the
    legs 120 degrees apart on a wye (X 0, Y -120, Z +120).
  * Triplens: in phase on every leg, so they add: sum of h x I_leg, with h
    the LED supply's effective triplen fraction of the fundamental.
  * I_N = sqrt(I_N1^2 + I_N3^2).
  * Split-phase: the legs are 180 degrees apart for the fundamental and the
    triplens alike, so I_N = sqrt((X1 - Y1)^2 + (hX1 - hY1)^2), never past
    the busier leg; shown, never warned.
  * The neutral is rated at the distro's rating per leg, twice it on a 200%
    neutral. Red past the rating (an unbreakered neutral may carry 100% of
    a continuous load, NEC 215.2(A)(1)); amber past 80% of it on a US
    system whose main is not 100% rated, the way the legs' limit reads.
  * h: Active PFC (low) 33%, No PFC (high) 87%, or a Custom percent; the
    show sets it, a screen may set its own. A show with none reads Active
    PFC (owner, 2026-11-12: he measures very little neutral current on his
    real shows); a pick, the show's or a screen's, is kept.

The walls, by hand. Every wall is 10 cabinets a row, one row a circuit:
  * US: 144 W panels at 120 V on a 25 A breaker (80% = 20 A = 2400 W): a
    row is 1440 W, two rows 2880 W do not fit, so one row is one circuit of
    1440 / 120 = 12.0 A. Rotating line to neutral lands circuits X Y Z X Y Z.
  * The 208 V wall: 144 W panels on a 10 A breaker (80% = 8 A = 1664 W), a
    row of 1440 W a circuit, line to line at 1440 / 208 = 6.923 A.
  * EU: 200 W panels at 230 V on a 16 A breaker (EU: the whole breaker,
    3680 W): a row of 2000 W a circuit, 2000 / 230 = 8.6957 A.

Run locally:
    "C:/Users/Blue Iris/.venvs/led-raster/Scripts/python.exe" -m pytest tests/test_power_neutral.py -n 4 --dist loadfile
"""

import json
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


PFC = 0.33
NOPFC = 0.87


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


def _open(pw_browser, url):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(url, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    pg.wait_for_timeout(1500)
    return context, pg, errors


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context, pg, errors = _open(pw_browser, e2e_server)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(400)
    yield pg, errors
    context.close()


# Four walls, 10 cabinets a row: W6 (6 rows, one full multi), W4 (4 rows),
# W3 (3 rows) and WLL (6 rows, the 208 V wall).
SEED_JS = """async () => {
    const proj = await (await fetch('/api/project')).json();
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments;
    delete proj.supplyHarmonics;
    await fetch('/api/project', {method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(proj)});
    for (const [name, rows] of [['W6', 6], ['W4', 4], ['W3', 3], ['WLL', 6]]) {
        await fetch('/api/layer/add', {method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name, columns: 10, rows,
                                  cabinet_width: 200, cabinet_height: 200,
                                  offset_x: 0, offset_y: 0})});
    }
    const p = await (await fetch('/api/project')).json();
    const app = window.app;
    app.project = p;
    app.currentLayer = p.layers[0];
    app.selectedLayerIds = new Set([p.layers[0].id]);
    app.renderLayers();
    return p.layers.map(l => l.name);
}"""

# Reshape in the page. `walls` names the walls in use, each with its power
# fields; every other wall is hidden and on no distro. All multis of a wall
# in use go on d1. `show` is the show's supply setting (absent: none).
SETUP_JS = """(o) => {
    const app = window.app;
    const base = { powerVoltage: 120, powerAmperage: 25, panelWatts: 144,
                   powerSocaDistro: {}, powerSocaNumber: {}, powerSocaPhasePos: {},
                   powerSocaLengths: {}, powerSocaSplits: [], powerSocaNames: {},
                   powerBreakoutType: null, locked: false, visible: false };
    app.project.layers.forEach(l => {
        Object.assign(l, base);
        delete l.supplyHarmonics;
        const own = (o.walls || {})[l.name];
        if (own) Object.assign(l, { visible: true }, own);
        app.normalizePowerBreakout(l);
    });
    if (o.show === undefined) delete app.project.supplyHarmonics;
    else app.project.supplyHarmonics = o.show;
    app.project.distros = (o.distros || []).map(d => JSON.parse(JSON.stringify(d)));
    app._circuitTailCache = null;
    app._distroFaceMemo = null;
    app.getDistros();
    const plans = {};
    app.project.layers.forEach(l => {
        if (!(o.walls || {})[l.name]) return;
        const plan = app.getSocaPlan(l);
        plan.forEach(s => { l.powerSocaDistro[s.soca] = 'd1'; });
        plans[l.name] = plan.map(s => s.legs.map(c => c.watts));
    });
    app._circuitTailCache = null;
    return plans;
}"""

READ_JS = """() => {
    const app = window.app;
    app._circuitTailCache = null;
    app.renderHardwareDock();
    const b = app.getDistroLoads().find(x => x.id === 'd1');
    const unit = document.querySelector('[data-lrd-distro="d1"]');
    const chip = unit && unit.querySelector('[data-lrd-neutral="d1"]');
    const strip = (app._dockPowerWarnings || []).filter(w => /neutral/.test(w.text))
        .map(w => ({ text: w.text, mild: !!w.mild }));
    return {
        neutral: b.neutral,
        legs: b.legs ? b.legs.names.map(k => b.legs[k].amps) : null,
        chip: chip ? chip.textContent : null,
        chipClass: chip ? chip.className : null,
        strip,
    };
}"""

BINDER_JS = """() => {
    const app = window.app;
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
    const service = caught.find(p => p.some(([k]) => k === 'Rating')) || [];
    return service;
}"""


def us(rating=400, **kw):
    return dict({'id': 'd1', 'name': 'D1', 'ratingA': rating, 'system': '120/208'}, **kw)


def setup(pg, **o):
    pg.wait_for_timeout(200)
    return pg.evaluate(SETUP_JS, o)


def read(pg):
    return pg.evaluate(READ_JS)


@pytest.fixture(scope="module")
def seeded(page):
    pg, errors = page
    assert pg.evaluate(SEED_JS) == ['W6', 'W4', 'W3', 'WLL']
    pg.wait_for_timeout(800)
    return pg, errors


def test_the_formula_on_its_own(seeded):
    """distroNeutral straight from a leg store, every shape of it."""
    pg, errors = seeded
    out = pg.evaluate("""() => {
        const app = window.app;
        const d = { id: 'dx', ratingA: 100, system: '120/208' };
        const run = (legs, h, dd = d) => {
            const s = app._neutralStore();
            for (const [k, a] of Object.entries(legs)) app._bookNeutral(s, k, a, h);
            const n = app.distroNeutral(dd, s);
            return n ? [n.amps, n.fundA, n.triplenA, n.checked] : null;
        };
        return {
            balanced: run({ X: 30, Y: 30, Z: 30 }, 0.33),
            allOnX: run({ X: 30 }, 0.33),
            allOnXClean: run({ X: 30 }, 0),
            twoLegs: run({ X: 30, Y: 30 }, 0),
            split: run({ X: 24, Y: 12 }, 0.33, { id: 'ds', ratingA: 100, system: '120/240' }),
            none: run({}, 0.33),
            singleHot: run({ X: 30 }, 0.33, { id: 'dh', ratingA: 100, system: '120' }),
        };
    }""")
    # balanced 30 A a leg: the fundamentals cancel to 0, the triplens add,
    # 0.33 x (30 + 30 + 30) = 29.7 A
    assert out['balanced'][1] == 0
    assert out['balanced'][0] == pytest.approx(29.7, abs=1e-9)
    # all on X: I_N1 = 30, I_N3 = 0.33 x 30 = 9.9, I_N = sqrt(900 + 98.01)
    # = 31.5913 A, the whole of X's current harmonics and all
    assert out['allOnX'][:3] == pytest.approx([math.sqrt(900 + 98.01), 30, 9.9], abs=1e-9)
    assert out['allOnX'][0] == pytest.approx(31.5913, abs=1e-4)
    # with no harmonics the neutral is exactly the one leg's current
    assert out['allOnXClean'][0] == pytest.approx(30, abs=1e-9)
    # two legs of a wye at 30 A, 120 degrees apart: |30 + 30<-120| = 30 A
    assert out['twoLegs'][0] == pytest.approx(30, abs=1e-9)
    # split-phase: |24 - 12| = 12, |0.33 x 24 - 0.33 x 12| = 3.96,
    # sqrt(144 + 15.6816) = 12.6365 A, shown and never checked
    assert out['split'][0] == pytest.approx(math.sqrt(144 + 3.96 ** 2), abs=1e-9)
    assert out['split'][3] is False
    assert out['none'] is None, 'nothing line to neutral, no neutral figure'
    assert out['singleHot'] is None, 'a single hot returns its line current: the line check covers it'
    assert not errors, errors


def test_balanced_120v_multi_is_the_harmonic_part_only(seeded):
    pg, errors = seeded
    plans = setup(pg, distros=[us(400)], walls={'W6': {}}, show='pfc')
    # one multi of six 1440 W circuits, X Y Z X Y Z
    assert plans == {'W6': [[1440] * 6]}, plans
    out = read(pg)
    # 2 circuits a leg x 12.0 A = 24.0 A on every leg
    assert out['legs'] == pytest.approx([24, 24, 24], abs=1e-9)
    N = out['neutral']
    # I_N1 = 0 (balanced), I_N3 = 0.33 x (24 + 24 + 24) = 23.76 A
    assert N['fundA'] == 0
    assert N['triplenA'] == pytest.approx(0.33 * 72, abs=1e-9)
    assert N['amps'] == pytest.approx(23.76, abs=1e-9)
    assert N['lnA'] == pytest.approx(72, abs=1e-9)
    assert N['ratingA'] == 400 and N['size'] == 100 and N['limitA'] == 320
    assert N['checked'] and not N['over'] and not N['pastLimit']
    assert out['chip'] == 'N 24A' and out['chipClass'] == 'hw-dock-legs-n'
    assert out['strip'] == []
    # No PFC: 0.87 x 72 = 62.64 A, the neutral now carries 2.61 times a leg
    setup(pg, distros=[us(400)], walls={'W6': {}}, show='nopfc')
    assert read(pg)['neutral']['amps'] == pytest.approx(62.64, abs=1e-9)
    assert not errors, errors


def test_a_show_with_no_setting_reads_active_pfc(seeded):
    pg, _ = seeded
    setup(pg, distros=[us(400)], walls={'W6': {}})
    out = pg.evaluate("() => window.app.showSupplyHarmonics()")
    assert out == {'id': 'pfc', 'name': 'Active PFC (low)', 'pct': 33}
    # balanced: I_N1 = 0, I_N3 = 0.33 x (24 + 24 + 24) = 23.76 A
    assert read(pg)['neutral']['amps'] == pytest.approx(23.76, abs=1e-9)
    assert pg.evaluate("() => 'supplyHarmonics' in window.app.project") is False, \
        'reading the default writes nothing'
    # a show that picked No PFC keeps its pick: 0.87 x 72 = 62.64 A
    setup(pg, distros=[us(400)], walls={'W6': {}}, show='nopfc')
    assert read(pg)['neutral']['amps'] == pytest.approx(62.64, abs=1e-9)
    # a screen that picked No PFC keeps its pick on a show with none:
    # 0.87 x 72 = 62.64 A
    setup(pg, distros=[us(400)], walls={'W6': {'supplyHarmonics': 'nopfc'}})
    assert pg.evaluate("() => 'supplyHarmonics' in window.app.project") is False
    assert read(pg)['neutral']['amps'] == pytest.approx(62.64, abs=1e-9)


def test_a_screen_sets_its_own_panels_apart(seeded):
    pg, _ = seeded
    # the show is No PFC; this screen's panels have active PFC
    setup(pg, distros=[us(400)], walls={'W6': {'supplyHarmonics': 'pfc'}}, show='nopfc')
    # 0.33 x 72 = 23.76 A
    assert read(pg)['neutral']['amps'] == pytest.approx(23.76, abs=1e-9)
    # a Custom 50%: 0.50 x 72 = 36.0 A
    setup(pg, distros=[us(400)], walls={'W6': {'supplyHarmonics': 50}}, show='nopfc')
    assert read(pg)['neutral']['amps'] == pytest.approx(36.0, abs=1e-9)
    # a Custom show of 10%: 0.10 x 72 = 7.2 A
    setup(pg, distros=[us(400)], walls={'W6': {}}, show=10)
    assert read(pg)['neutral']['amps'] == pytest.approx(7.2, abs=1e-9)


def test_partly_filled_multi_mixed_with_208v_circuits(seeded):
    pg, errors = seeded
    plans = setup(pg, distros=[us(400)], walls={'W4': {}}, show='pfc')
    assert plans == {'W4': [[1440] * 4]}, plans
    alone = read(pg)
    # four circuits X Y Z X: X 24.0, Y 12.0, Z 12.0 A
    assert alone['legs'] == pytest.approx([24, 12, 12], abs=1e-9)
    # I_N1 = |24 + 12<-120 + 12<+120| = 24 - 12 = 12.0 A
    # I_N3 = 0.33 x (24 + 12 + 12) = 15.84 A
    # I_N = sqrt(12^2 + 15.84^2) = sqrt(394.9056) = 19.8722 A
    N = alone['neutral']
    assert N['fundA'] == pytest.approx(12, abs=1e-9)
    assert N['triplenA'] == pytest.approx(15.84, abs=1e-9)
    assert N['amps'] == pytest.approx(math.sqrt(394.9056), abs=1e-9)
    assert N['amps'] == pytest.approx(19.8722, abs=1e-4)
    # The 208 V wall beside it: six line-to-line circuits of 1440 / 208 =
    # 6.923 A. They load the legs and put nothing on the neutral.
    plans = setup(pg, distros=[us(400)], show='pfc',
                  walls={'W4': {}, 'WLL': {'powerVoltage': 208, 'powerAmperage': 10}})
    assert plans['WLL'] == [[1440] * 6], plans
    mixed = read(pg)
    assert mixed['legs'] != alone['legs'], 'the 208 V circuits load the legs'
    assert mixed['neutral']['amps'] == pytest.approx(math.sqrt(394.9056), abs=1e-9)
    assert mixed['neutral']['lnA'] == pytest.approx(48, abs=1e-9)
    # the 208 V wall alone: line to line only, no neutral figure and no chip
    setup(pg, distros=[us(400)], show='pfc',
          walls={'WLL': {'powerVoltage': 208, 'powerAmperage': 10}})
    ll = read(pg)
    assert ll['neutral'] is None and ll['chip'] is None and ll['strip'] == []
    assert not errors, errors


# The balanced wall at No PFC: I_N = 0.87 x 72 = 62.64 A, about 63 A.
@pytest.mark.parametrize('rating, n200, main100, want', [
    # 100% of 50 A: 62.64 > 50, red
    (50, False, False, 'over'),
    # 200% of 50 A = 100 A, 80% of it 80 A: 62.64 under both, nothing
    (50, True, False, None),
    # 100% of 70 A: under 70, past 80% (56 A): amber
    (70, False, False, 'past'),
    # the same with the main 100% rated: the rating is the limit, nothing
    (70, False, True, None),
    # 200% of 35 A = 70 A, 80% of it 56 A: amber
    (35, True, False, 'past'),
    # 200% of 30 A = 60 A: 62.64 > 60, red
    (30, True, False, 'over'),
])
def test_100_and_200_percent_thresholds(seeded, rating, n200, main100, want):
    pg, errors = seeded
    d = us(rating)
    if n200:
        d['neutral200'] = True
    if main100:
        d['main100'] = True
    setup(pg, distros=[d], walls={'W6': {}}, show='nopfc')
    out = read(pg)
    N = out['neutral']
    assert N['amps'] == pytest.approx(62.64, abs=1e-9)
    assert N['ratingA'] == rating * (2 if n200 else 1)
    assert N['over'] == (want == 'over') and N['pastLimit'] == (want == 'past'), N
    if want == 'over':
        fix = ('Move 120V circuits to 208V, or spread the load over more distros.' if n200
               else 'Use a power in with a 200% neutral, or move 120V circuits to 208V.')
        assert out['strip'] == [{
            'text': f"D1's power in neutral carries about 63 A with LED supply harmonics, "
                    f"over its {200 if n200 else 100}% neutral ({rating * (2 if n200 else 1)} A). {fix}",
            'mild': False}], out['strip']
        assert out['chipClass'] == 'hw-dock-legs-n hw-dock-legs-n-over'
    elif want == 'past':
        r = rating * (2 if n200 else 1)
        assert out['strip'] == [{
            'text': f"D1's power in neutral carries about 63 A with LED supply harmonics, "
                    f"past 80% of its {200 if n200 else 100}% neutral ({+round(r * 0.8, 1):g} A of {r} A).",
            'mild': True}], out['strip']
        assert out['chipClass'] == 'hw-dock-legs-n hw-dock-legs-n-warn'
    else:
        assert out['strip'] == [] and out['chipClass'] == 'hw-dock-legs-n'
    assert out['chip'] == 'N 63A'
    assert not errors, errors


def test_eu_all_on_l1_and_balanced(seeded):
    pg, errors = seeded
    eu = {'id': 'd1', 'name': 'D1', 'ratingA': 63, 'system': '230/400', 'phasing': 'whole-ln'}
    wall = {'powerVoltage': 230, 'powerAmperage': 16, 'panelWatts': 200}
    plans = setup(pg, distros=[eu], walls={'W6': wall}, show='nopfc')
    assert plans == {'W6': [[2000] * 6]}, plans
    out = read(pg)
    # whole multi on one leg: six circuits of 2000 / 230 = 8.6957 A on L1,
    # 6 x 2000 / 230 = 52.174 A
    x = 6 * 2000 / 230
    assert out['legs'] == pytest.approx([x, 0, 0], abs=1e-9)
    # I_N1 = 52.174, I_N3 = 0.87 x 52.174 = 45.391,
    # I_N = 52.174 x sqrt(1 + 0.7569) = 52.174 x 1.32548 = 69.155 A
    N = out['neutral']
    assert N['fundA'] == pytest.approx(x, abs=1e-9)
    assert N['amps'] == pytest.approx(x * math.sqrt(1 + 0.87 ** 2), abs=1e-9)
    assert N['amps'] == pytest.approx(69.155, abs=1e-3)
    # EU: the rating is the limit, no 80%; past 63 A is red, with the EU fix
    assert N['limitA'] == 63 and N['over'] and not N['pastLimit']
    assert out['strip'] == [{
        'text': "D1's power in neutral carries about 69 A with LED supply harmonics, "
                "over its 100% neutral (63 A). Use a power in with a 200% neutral, "
                "or spread the load over more distros.", 'mild': False}], out['strip']
    # Active PFC: 52.174 x sqrt(1 + 0.1089) = 52.174 x 1.05304 = 54.941 A,
    # under 63 A and no amber on an EU distro
    setup(pg, distros=[eu], walls={'W6': wall}, show='pfc')
    out = read(pg)
    assert out['neutral']['amps'] == pytest.approx(x * math.sqrt(1 + 0.33 ** 2), abs=1e-9)
    assert out['neutral']['amps'] == pytest.approx(54.941, abs=1e-3)
    assert out['strip'] == [] and out['chip'] == 'N 55A'
    # Rotating L1 L2 L3 instead: two circuits a leg, 17.391 A each, balanced:
    # I_N = 0.33 x 3 x 17.391 = 17.217 A
    setup(pg, distros=[dict(eu, phasing=None)], walls={'W6': wall}, show='pfc')
    out = read(pg)
    leg = 2 * 2000 / 230
    assert out['legs'] == pytest.approx([leg] * 3, abs=1e-9)
    assert out['neutral']['fundA'] == 0
    assert out['neutral']['amps'] == pytest.approx(0.33 * 3 * leg, abs=1e-9)
    assert not errors, errors


def test_split_phase_shows_the_difference_and_never_warns(seeded):
    pg, errors = seeded
    sp = {'id': 'd1', 'name': 'D1', 'ratingA': 20, 'system': '120/240'}
    plans = setup(pg, distros=[sp], walls={'W3': {}}, show='nopfc')
    assert plans == {'W3': [[1440] * 3]}, plans
    out = read(pg)
    # three 12.0 A circuits on two legs: 24.0 on one, 12.0 on the other
    assert sorted(out['legs']) == pytest.approx([12, 24], abs=1e-9)
    # I_N = sqrt((24 - 12)^2 + (0.87 x 24 - 0.87 x 12)^2)
    #     = 12 x sqrt(1 + 0.7569) = 15.906 A, under the busier leg
    N = out['neutral']
    assert N['amps'] == pytest.approx(12 * math.sqrt(1 + 0.87 ** 2), abs=1e-9)
    assert not N['checked'] and not N['over'] and not N['pastLimit']
    assert out['strip'] == [] and out['chip'] == 'N 16A'
    # no Neutral setting in its gear: only a three-phase distro has one
    assert pg.evaluate("""() => {
        const app = window.app;
        const el = app._buildDistroGearContent(app.getDistros()[0]);
        return !!el.querySelector('[data-lrd-field="distro-neutral-d1"]');
    }""") is False
    assert not errors, errors


def test_the_binder_prints_the_neutral(seeded):
    pg, errors = seeded
    setup(pg, distros=[us(50)], walls={'W6': {}}, show='nopfc')
    pairs = pg.evaluate(BINDER_JS)
    keys = [k for k, _ in pairs]
    assert keys.index('Neutral') == keys.index('Imbalance') + 1, keys
    # 0.87 x 72 = 62.64 A
    assert dict(pairs)['Neutral'] == \
        '62.6 A with LED supply harmonics (No PFC, 87%) · 100% neutral 50 A · OVER'
    setup(pg, distros=[us(35, neutral200=True)], walls={'W6': {}}, show='pfc')
    # 0.33 x 72 = 23.76 A against 70 A
    assert dict(pg.evaluate(BINDER_JS))['Neutral'] == \
        '23.8 A with LED supply harmonics (Active PFC, 33%) · 200% neutral 70 A'
    setup(pg, distros=[us(35, neutral200=True)], walls={'W6': {}}, show='nopfc')
    # 62.64 A, past 80% of 70 A = 56 A
    assert dict(pg.evaluate(BINDER_JS))['Neutral'] == \
        '62.6 A with LED supply harmonics (No PFC, 87%) · 200% neutral 70 A · past 80% (56 A)'
    # line to line only: no Neutral line
    setup(pg, distros=[us(400)], show='pfc', walls={'WLL': {'powerVoltage': 208, 'powerAmperage': 10}})
    assert 'Neutral' not in [k for k, _ in pg.evaluate(BINDER_JS)]
    assert not errors, errors


def test_the_balance_dialog_reads_the_neutral(seeded):
    pg, errors = seeded
    setup(pg, distros=[us(50)], walls={'W6': {}}, show='nopfc')
    text = pg.evaluate("""() => {
        window.app.showBalanceDialog('d1');
        const el = document.querySelector('#balance-modal .balance-neutral');
        const t = el ? el.textContent : null;
        document.getElementById('balance-modal').remove();
        return t;
    }""")
    # a full multi: nothing to move, the neutral as it stands, 62.64 A
    assert text == ("Neutral on the power in: about 62.6 A of 50 A (100% neutral). Even legs "
                    "cancel on the neutral, but the LED supplies' third harmonics add up on it "
                    "wherever the circuits land."), text
    assert not errors, errors


def test_the_gear_sets_100_or_200_and_undoes(seeded):
    pg, errors = seeded
    setup(pg, distros=[us(50)], walls={'W6': {}}, show='nopfc')
    pg.evaluate("() => { window.app.saveState('Setup'); window.app.renderHardwareDock(); }")
    out = pg.evaluate("""() => {
        const app = window.app;
        const el = app._buildDistroGearContent(app.getDistros()[0]);
        const sel = el.querySelector('[data-lrd-field="distro-neutral-d1"]');
        const reads = el.querySelector('[data-lrd-neutral-reads="d1"]');
        const before = [sel.value, [...sel.options].map(o => o.textContent), reads.textContent];
        sel.value = '200';
        sel.dispatchEvent(new Event('change', { bubbles: true }));
        const d = app.getDistros()[0];
        return { before, after: d.neutral200 === true,
                 action: app.history[app.historyIndex].action };
    }""")
    # 62.64 A on a 100% neutral of 50 A
    assert out['before'] == ['100', ['100%', '200%'], '50 A, carrying about 63 A'], out
    assert out['after'] and out['action'] == 'Edit Distro'
    assert read(pg)['neutral']['ratingA'] == 100
    pg.evaluate("() => window.app.undo()")
    pg.wait_for_timeout(600)
    assert pg.evaluate("() => 'neutral200' in window.app.getDistros()[0]") is False
    assert not errors, errors


def test_the_show_setting_from_the_sidebar_persists_and_undoes(seeded):
    pg, errors = seeded
    setup(pg, distros=[us(400)], walls={'W6': {}})
    pg.evaluate("""() => {
        const app = window.app;
        app.selectLayer(app.project.layers[0]);
        app.saveState('Setup');
        app.syncSupplyHarmonicsControls();
    }""")
    sel = pg.locator('#power-harmonics-show')
    # a show with none reads the default, Active PFC
    assert sel.input_value() == 'pfc'
    sel.select_option('nopfc')
    pg.wait_for_timeout(500)
    assert pg.evaluate("() => window.app.project.supplyHarmonics") == 'nopfc'
    sel.select_option('pfc')
    pg.wait_for_timeout(500)
    assert pg.evaluate("() => window.app.project.supplyHarmonics") == 'pfc'
    served = pg.evaluate("async () => (await (await fetch('/api/project')).json()).supplyHarmonics")
    assert served == 'pfc'
    assert pg.evaluate("() => window.app.history[window.app.historyIndex].action") == \
        'Set LED Supply Harmonics'
    # 0.33 x 72 = 23.76 A
    assert read(pg)['neutral']['amps'] == pytest.approx(23.76, abs=1e-9)
    # Custom opens its percent box at the figure in force, stored as a number
    sel.select_option('custom')
    pg.wait_for_timeout(300)
    assert pg.evaluate("() => window.app.project.supplyHarmonics") == 33
    box = pg.locator('#power-harmonics-show-pct')
    assert box.is_visible() and box.input_value() == '33'
    box.fill('20')
    box.press('Enter')
    pg.wait_for_timeout(300)
    assert pg.evaluate("() => window.app.project.supplyHarmonics") == 20
    # 0.20 x 72 = 14.4 A
    assert read(pg)['neutral']['amps'] == pytest.approx(14.4, abs=1e-9)
    # the screen's own: Same as show names the show's figure
    follow = pg.evaluate(
        "() => document.querySelector('#power-harmonics-screen option[value=\"\"]').textContent")
    assert follow == 'Same as show (20%)'
    pg.locator('#power-harmonics-screen').select_option('nopfc')
    pg.wait_for_timeout(400)
    assert pg.evaluate("() => window.app.project.layers[0].supplyHarmonics") == 'nopfc'
    # 0.87 x 72 = 62.64 A
    assert read(pg)['neutral']['amps'] == pytest.approx(62.64, abs=1e-9)
    # undo, one step at a time: the screen, then the show back to 33,
    # 'pfc', 'nopfc' and none
    for want in (20, 33, 'pfc', 'nopfc', None):
        pg.evaluate("() => window.app.undo()")
        pg.wait_for_timeout(500)
    assert pg.evaluate("() => window.app.project.supplyHarmonics === undefined "
                       "|| window.app.project.supplyHarmonics === null")
    assert not errors, errors


def test_an_old_show_opens_with_no_setting_and_nothing_moved(seeded):
    """A show saved before the neutral: no supplyHarmonics, no neutral200.
    It opens on the defaults (Active PFC, a 100% neutral) and
    nothing is written for it - not to the show, the distro, or a screen -
    and the legs read what they always read."""
    pg, errors = seeded
    setup(pg, distros=[us(400)], walls={'W4': {}})
    out = pg.evaluate("""async () => {
        const app = window.app;
        // the legs the way the roll-up has always computed them, store and all
        app._circuitTailCache = null;
        const b = app.getDistroLoads().find(x => x.id === 'd1');
        const legs = ['X', 'Y', 'Z'].map(k => b.legs[k].amps);
        // save it, read it back the way a file opens
        await fetch('/api/project', { method: 'PUT', headers: { 'Content-Type': 'application/json' },
                                      body: JSON.stringify(app.project) });
        const p = await (await fetch('/api/project')).json();
        app.project = p;
        app._circuitTailCache = null;
        app.renderHardwareDock();
        app._buildDistroGearContent(app.getDistros()[0]);
        app.syncSupplyHarmonicsControls();
        const b2 = app.getDistroLoads().find(x => x.id === 'd1');
        return {
            legs, legs2: ['X', 'Y', 'Z'].map(k => b2.legs[k].amps),
            showKey: 'supplyHarmonics' in app.project,
            distroKey: 'neutral200' in app.getDistros()[0],
            layerKeys: app.project.layers.filter(l => l.supplyHarmonics != null).length,
            show: app.showSupplyHarmonics(),
            size: b2.neutral.size,
            served: await (await fetch('/api/project')).json(),
        };
    }""")
    assert out['legs2'] == out['legs'] == pytest.approx([24, 12, 12], abs=1e-9)
    assert not out['showKey'] and not out['distroKey'] and out['layerKeys'] == 0
    assert out['show'] == {'id': 'pfc', 'name': 'Active PFC (low)', 'pct': 33}
    assert out['size'] == 100
    assert 'supplyHarmonics' not in out['served']
    assert all('neutral200' not in d for d in out['served'].get('distros', []))
    assert not errors, errors


def test_presets_carry_the_neutral(seeded):
    pg, errors = seeded
    setup(pg, distros=[us(200, neutral200=True)], walls={'W6': {}})
    out = pg.evaluate("""() => {
        const app = window.app;
        const body = app._distroPresetBody(app.getDistros()[0]);
        app.applyDistroPreset('d1', { name: 'P', distro: Object.assign({}, body, { neutral200: false }) });
        const off = 'neutral200' in app.getDistros()[0];
        app.applyDistroPreset('d1', { name: 'P', distro: body });
        return { body: body.neutral200, off, on: app.getDistros()[0].neutral200 === true };
    }""")
    assert out == {'body': True, 'off': False, 'on': True}
    assert not errors, errors
