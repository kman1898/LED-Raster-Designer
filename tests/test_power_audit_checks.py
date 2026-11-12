"""Power checks from the engineering audit (owner rulings, 2026-11-11).

  * A distro powered THRU another: the distro it is fed thru counts its own
    load plus every distro fed thru it, per leg with the same phasor sum,
    red past 80% of its rating. Said on the distro card ("Feeds D2: 99.9 A
    per leg on an 80 A limit"), on the service card and in the binder.
  * A BREAKER LARGER THAN WHAT IT FEEDS: the screen's Amperage box, a
    Socapex or L21-30 row's breaker, or a row's typed rating past the
    connector's own. A red OVER on the circuit and the distro and a strip
    line naming the connector and its rating, never dismissed.
  * EDISON OUTPUTS are 5-15 or 5-20, 5-15 by default: 12 A or 16 A
    continuous, and packing follows a picked type. A row from before the
    choice reads 5-15 on its checks, keeps the circuits as they were laid
    out, and flags anything past 12 A with a Repack at 5-15 offer.
  * Bugs: a US 240 V or 277 V screen on no distro packed to 100% of its
    breaker (now 80%, NEC 210.20(A)); an auto-packed L21-30 came out OVER
    (the packer now holds a circuit to the feed limit over the square root
    of 3); "Total Amps (1φ)" is hidden on a 3-phase distro.

Every expected figure is worked by hand beside its assert.

Run locally:
    "C:/Users/Blue Iris/.venvs/led-raster/Scripts/python.exe" -m pytest tests/test_power_audit_checks.py -n 4 --dist loadfile
"""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

SQRT3 = math.sqrt(3)


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
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


# Walls by [name, columns, rows] - 200 px cabinets, every one a panel.
SEED_JS = """async (walls) => {
    const proj = await (await fetch('/api/project')).json();
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.services;
    delete proj.port_assignments;
    await fetch('/api/project', {method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(proj)});
    for (const [name, columns, rows] of walls) {
        await fetch('/api/layer/add', {method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name, columns, rows, cabinet_width: 200, cabinet_height: 200})});
    }
    const p = await (await fetch('/api/project')).json();
    const app = window.app;
    app.project = p;
    app.currentLayer = p.layers[0];
    app.selectedLayerIds = new Set([p.layers[0].id]);
    app.renderLayers();
    return p.layers.map(l => l.id);
}"""

# The power fields of each wall (o.walls[i]), the distros and services,
# and the stores each wall's multis are on: o.assign[i] = { distro, pins }
# puts every multi of wall i on `distro`, pinned to its own index when
# `pins` is set; o.stores[i] writes the stores outright.
SETUP_JS = """(o) => {
    const app = window.app;
    app.project.distros = (o.distros || []).map(d => JSON.parse(JSON.stringify(d)));
    if (o.services) app.project.services = JSON.parse(JSON.stringify(o.services));
    else delete app.project.services;
    app.project.layers.forEach((l, i) => {
        Object.assign(l, { powerVoltage: 208, powerAmperage: 20, panelWatts: 150,
                           powerSocaDistro: {}, powerSocaNumber: {}, powerSocaPhasePos: {},
                           powerSocaLengths: {}, powerSocaSplits: [], powerSocaNames: {},
                           powerBreakoutType: null, visible: true, locked: false },
                      (o.walls || [])[i] || {});
        app.normalizePowerBreakout(l);
        Object.assign(l, ((o.stores || [])[i]) || {});
    });
    app._circuitTailCache = null;
    app._distroFaceMemo = null;
    app.getDistros();
    (o.assign || []).forEach((a, i) => {
        if (!a) return;
        const l = app.project.layers[i];
        app._circuitTailCache = null;
        app.getSocaPlan(l).forEach(s => {
            l.powerSocaDistro[s.soca] = a.distro;
            if (a.pins) l.powerSocaNumber[s.soca] = s.soca;
        });
    });
    app._circuitTailCache = null;
    app.currentLayer = app.project.layers[0];
    app.selectedLayerIds = new Set([app.project.layers[0].id]);
    app.updatePowerCapacityDisplay();
    app.renderHardwareDock();
    return app.project.layers.map(l => app.getSocaPlan(l).length);
}"""

# The binder's KV blocks, caught as planBinder builds them: [title, pairs].
BINDER_JS = """() => {
    const app = window.app;
    const caught = [];
    const orig = app._bKvLines;
    app._bKvLines = function (book, title, pairs) {
        caught.push([title, pairs.map(p => p.slice())]);
        return orig.apply(this, arguments);
    };
    try {
        app.planBinder(Object.assign(app.readBinderOptions(),
            { scope: { kind: 'show' }, hardware: true, pull: false, cover: false }));
    } finally { app._bKvLines = orig; }
    return caught;
}"""

STRIP_JS = """() => { window.app.renderHardwareDock();
    return (window.app._dockPowerWarnings || []).map(w => ({ text: w.text, mild: !!w.mild,
        offer: w.offer ? w.offer.label : null })); }"""


def seed(pg, walls):
    pg.evaluate(SEED_JS, walls)
    pg.wait_for_timeout(500)


def setup(pg, **o):
    pg.wait_for_timeout(200)
    return pg.evaluate(SETUP_JS, o)


def strip(pg):
    return pg.evaluate(STRIP_JS)


def binder_pairs(pg, key):
    """Every value printed under KEY in any binder KV block."""
    return [v for _, pairs in pg.evaluate(BINDER_JS) for k, v in pairs if k == key]


def distro(i, name, rating, system='120/208', **kw):
    return dict(id=i, name=name, ratingA=rating, system=system, **kw)


# ── 1. a distro powered thru another ─────────────────────────────────────
#
# A and B are 100 A cam-input 120/208 distros, B powered thru A. Each
# carries one wall of 10 x 12 panels at 150 W = 18,000 W at 208 V on a
# 20 A breaker: a circuit holds 16 A x 208 V = 3,328 W, 22 panels, so two
# rows of ten (3,000 W, 14.42 A) - six circuits, one multi, every leg pair
# once. Per leg, balanced: 18,000 / (208 x sqrt 3) = 49.96 A. A's power in
# carries both: 2 x 49.96 = 99.93 A per leg, against 80 A (80% of 100 A).
OWN_LEG = 18000 / (208 * SQRT3)          # 49.96 A
THRU_LEG = 2 * OWN_LEG                   # 99.93 A


def _thru_show(pg, services=None, **a_kw):
    seed(pg, [['WALL A', 10, 12], ['WALL B', 10, 12]])
    return setup(pg, distros=[distro('d1', 'D1', 100, input='cam100', **a_kw),
                              distro('d2', 'D2', 100, input='cam100', feeder={'from': 'd1'},
                                     **({'serviceId': 's1'} if services else {}))],
                 services=services,
                 assign=[{'distro': 'd1'}, {'distro': 'd2'}])


def test_fed_thru_distro_counts_both_loads_and_goes_red(page):
    pg, errors = page
    assert _thru_show(pg) == [1, 1]
    out = pg.evaluate("""() => {
        const L = window.app.getDistroLoads();
        const a = L.find(x => x.id === 'd1'), b = L.find(x => x.id === 'd2');
        const card = document.querySelector('[data-lrd-thru="d1"]');
        const head = document.querySelector('[data-lrd-distro="d1"] .hw-dock-unit-use');
        return { aOwn: a.amps, bOwn: b.amps, thru: a.thru ? a.thru.amps : null,
                 legs: a.thru && a.thru.legs ? [a.thru.legs.X, a.thru.legs.Y, a.thru.legs.Z] : null,
                 over: a.over, aLimit: a.limitA, bThru: !!b.thru, bOver: b.over,
                 card: card ? card.textContent : null,
                 cardOver: card ? card.dataset.lrdThruOver || null : null,
                 head: head ? head.textContent : null };
    }""")
    assert out['aOwn'] == pytest.approx(OWN_LEG, abs=0.01)
    assert out['bOwn'] == pytest.approx(OWN_LEG, abs=0.01)
    assert out['thru'] == pytest.approx(THRU_LEG, abs=0.01)
    assert out['legs'] == pytest.approx([THRU_LEG] * 3, abs=0.01)
    assert out['aLimit'] == 80                # 80% of 100 A
    assert out['over'] is True and out['bOver'] is False and not out['bThru']
    assert out['card'] == 'Feeds D2: 99.9 A per leg on an 80 A limit'
    assert out['cardOver'] == '1'
    assert out['head'] == '99.9/80 A'
    lines = [w for w in strip(pg) if w['text'].startswith('D1 with D2 thru it')]
    assert lines and 'OVER' in lines[0]['text'] and not lines[0]['mild'], lines
    assert lines[0]['offer'] == 'Accept overload'
    thru = binder_pairs(pg, 'Thru load')
    assert thru == ['Feeds D2: 99.9 A per leg on an 80 A limit · OVER'], thru
    assert errors == []


def test_fed_thru_under_the_limit_is_not_red(page):
    """Main 100% rated: 99.93 A against 100 A is under it."""
    pg, errors = page
    _thru_show(pg, main100=True)
    out = pg.evaluate("""() => {
        const a = window.app.getDistroLoads().find(x => x.id === 'd1');
        return { thru: a.thru.amps, over: a.over, limit: a.limitA };
    }""")
    assert out['limit'] == 100 and out['over'] is False
    assert out['thru'] == pytest.approx(THRU_LEG, abs=0.01)
    assert errors == []


def test_fed_thru_reads_on_the_service_card(page):
    """A on a 400 A service, B thru A: the service still counts each distro
    once - 99.93 A of 320 A - and A's chip says what its power in carries."""
    pg, errors = page
    _thru_show(pg, services=[{'id': 's1', 'name': 'HOUSE', 'ratingA': 400, 'system': '120/208',
                              'voltage': 208, 'phase': 3}], serviceId='s1')
    out = pg.evaluate("""() => {
        const s = window.app.getServiceLoads()[0];
        const chip = document.querySelector('[data-lrd-svc-thru-total="d1"]');
        return { amps: s.amps, over: s.over, chip: chip ? chip.textContent : null,
                 red: chip ? chip.classList.contains('hw-dock-thru-over') : null };
    }""")
    assert out['amps'] == pytest.approx(THRU_LEG, abs=0.01)
    assert out['over'] is False
    assert out['chip'] and out['chip'].endswith('Feeds D2: 99.9 A per leg on an 80 A limit'), out
    assert out['red'] is True
    assert errors == []


# ── 2. a breaker larger than what it feeds ───────────────────────────────

def test_30a_breaker_on_true1_is_over(page):
    """A 208 V screen on no distro, Amperage typed 30, Multi to TRUE1: a
    circuit holds 30 x 0.8 = 24 A, 24 x 208 = 4,992 W, 33 panels - three
    rows of ten, 4,500 W - so 120 panels make four circuits. TRUE1 is
    rated 20 A (UL), so all four are on a breaker past their connector."""
    pg, errors = page
    seed(pg, [['WALL A', 10, 12]])
    assert setup(pg, walls=[{'powerAmperage': 30, 'powerBreakoutType': 'soca-true1'}]) == [1]
    checks = pg.evaluate("() => window.app.breakerOverChecks().map(g => ({ item: g.item, "
                         "rating: g.ratingA, breaker: g.breakerA, circuits: g.circuits, text: g.text }))")
    assert checks == [{'item': 'TRUE1', 'rating': 20, 'breaker': 30, 'circuits': [1, 2, 3, 4],
                       'text': 'WALL A circuits 1-4: 30 A breaker on TRUE1 (20 A). '
                               'Use a 20 A breaker or a connector rated for 30 A.'}]
    lines = [w for w in strip(pg) if 'breaker on TRUE1' in w['text']]
    assert len(lines) == 1 and not lines[0]['mild'] and lines[0]['offer'] is None
    side = pg.evaluate("""() => { const el = document.getElementById('power-amperage-over');
        return [el.textContent, el.style.display]; }""")
    assert side == ['OVER: 30 A breaker on TRUE1 (20 A)', '']
    # 20 A on the same screen: nothing to say
    setup(pg, walls=[{'powerAmperage': 20, 'powerBreakoutType': 'soca-true1'}])
    assert pg.evaluate("() => window.app.breakerOverChecks().length") == 0
    assert pg.evaluate("() => document.getElementById('power-amperage-over').style.display") == 'none'
    assert errors == []


SOCA30 = distro('d1', 'D1', 200, input='cam200',
                outputRows=[{'id': 'r1', 'connector': 'soca', 'count': 4, 'coupling': 'll', 'breakerA': 30}])


def test_30a_breaker_on_socapex_is_over(page):
    """A Socapex 208V row with 30 A breakers feeding a wall on TRUE1: the
    screen's own box says 20 A (16 A usable, two rows of ten, six circuits,
    one multi), but the circuits are really on the row's 30 A breakers -
    past the TRUE1 tails' 20 A."""
    pg, errors = page
    seed(pg, [['WALL A', 10, 12]])
    assert setup(pg, distros=[SOCA30], walls=[{'powerBreakoutType': 'soca-true1'}],
                 assign=[{'distro': 'd1', 'pins': True}]) == [1]
    text = ('WALL A circuits 1-6: 30 A breaker on TRUE1 (20 A). '
            'Use a 20 A breaker or a connector rated for 30 A.')
    assert pg.evaluate("() => window.app.breakerOverChecks().map(g => g.text)") == [text]
    out = pg.evaluate("""() => ({
        chips: document.querySelectorAll('[data-lrd-distro="d1"] .lrd-tile[data-lrd-breaker-over="1"]').length,
        flag: !!document.querySelector('[data-lrd-distro="d1"] [data-lrd-breaker-over="d1"]'),
        flagText: (document.querySelector('[data-lrd-distro="d1"] [data-lrd-breaker-over="d1"]') || {}).textContent,
    })""")
    assert out == {'chips': 6, 'flag': True, 'flagText': 'OVER'}
    assert [w for w in strip(pg) if w['text'] == text] == [{'text': text, 'mild': False, 'offer': None}]
    assert binder_pairs(pg, 'Breaker over').count(text) >= 2   # the distro's sheet and the screen's
    # the row at 20 A clears it
    setup(pg, distros=[dict(SOCA30, outputRows=[dict(SOCA30['outputRows'][0], breakerA=20)])],
          walls=[{'powerBreakoutType': 'soca-true1'}], assign=[{'distro': 'd1', 'pins': True}])
    assert pg.evaluate("() => window.app.breakerOverChecks().length") == 0
    assert errors == []


def test_l2130_row_with_30a_breakers_is_over(page):
    """An L21-30 row whose circuits sit on 30 A (a box with no breakers of
    its own): its TRUE1 tails are 20 A."""
    pg, errors = page
    seed(pg, [['WALL A', 10, 2]])
    setup(pg, distros=[distro('d1', 'D1', 200, input='cam200', outputRows=[
              {'id': 'r1', 'connector': 'l2130', 'count': 2, 'coupling': 'll', 'breakerA': 30}])],
          walls=[{'powerBreakoutType': 'l2130-true1'}], assign=[{'distro': 'd1', 'pins': True}])
    items = pg.evaluate("() => window.app.breakerOverChecks().map(g => [g.item, g.ratingA, g.breakerA])")
    assert items == [['TRUE1', 20, 30]]
    assert errors == []


def test_a_typed_rating_never_raises_true1(page):
    """A TRUE1 direct row typed "rated 30": the checks keep the maker's 20 A,
    and the strip says it was typed past it."""
    pg, errors = page
    seed(pg, [['WALL A', 2, 1]])
    setup(pg, distros=[distro('d1', 'D1', 200, input='cam200', outputRows=[
        {'id': 'r1', 'connector': 'true1', 'count': 6, 'coupling': 'll', 'breakerA': 30, 'connectorA': 30}])])
    out = pg.evaluate("""() => {
        const app = window.app, d = app.getDistros()[0], box = app.faceBox(d, 1);
        return { rating: app.faceConnectorRatingA(d, box), raised: app.faceRatingRaised(d, box),
                 checks: app.distroChecks(d).map(w => [w.text, !!w.mild]) };
    }""")
    assert out['rating'] == 20
    assert out['raised'] == {'typed': 30, 'maker': 20}
    assert ["D1's TRUE1 row is typed 30 A, past the TRUE1's own 20 A. The checks use 20 A.", True] \
        in out['checks']
    # typed lower is kept as typed
    assert pg.evaluate("""() => { const app = window.app, d = app.getDistros()[0];
        d.outputRows[0].connectorA = 16; app._distroFaceMemo = null;
        return app.faceConnectorRatingA(d, app.faceBox(d, 1)); }""") == 16
    assert errors == []


# ── 3. Edison outputs: 5-15 or 5-20 ──────────────────────────────────────

def _edison(edison_type=None, count=6):
    r = {'id': 'r1', 'connector': 'edison', 'count': count, 'coupling': 'ln', 'breakerA': 20}
    if edison_type:
        r['edisonType'] = edison_type
    return distro('d1', 'D1', 200, input='cam200', outputRows=[r])


# One row of twelve 150 W panels at 120 V, its first multi on Edison
# output 1 (stored and pinned the way a drop leaves it).
EDISON_WALL = {'powerVoltage': 120, 'powerAmperage': 20, 'powerBreakoutType': 'soca-edison'}
EDISON_STORES = {'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1}}


def test_edison_5_15_packs_to_12a_and_5_20_to_16a(page):
    """5-15: 80% of 15 A = 12 A, 12 x 120 = 1,440 W - nine 150 W panels.
    5-20: 80% of 20 A = 16 A, 1,920 W - twelve panels."""
    pg, errors = page
    seed(pg, [['WALL A', 12, 1]])
    setup(pg, distros=[_edison('5-15')], walls=[EDISON_WALL], stores=[EDISON_STORES])
    cap = pg.evaluate("() => { const c = window.app.circuitCapacity(window.app.project.layers[0]); "
                      "return [c.amps, c.watts, window.app.getSocaPlan(window.app.project.layers[0])"
                      ".reduce((n, s) => n + s.legs.length, 0)]; }")
    assert cap == [pytest.approx(12), pytest.approx(1440), 2]     # 12 panels: 9 + 3
    sel = pg.evaluate("() => { window.app.renderHardwareDock(); return 0; }")
    setup(pg, distros=[_edison('5-20')], walls=[EDISON_WALL], stores=[EDISON_STORES])
    cap = pg.evaluate("() => { const c = window.app.circuitCapacity(window.app.project.layers[0]); "
                      "return [c.amps, c.watts, window.app.getSocaPlan(window.app.project.layers[0])"
                      ".reduce((n, s) => n + s.legs.length, 0)]; }")
    assert cap == [pytest.approx(16), pytest.approx(1920), 1]     # all twelve on one circuit
    assert sel == 0
    # the binder's Outputs line says which
    assert any('Edison 5-20' in v for v in binder_pairs(pg, 'Outputs'))
    assert errors == []


def test_edison_row_offers_5_15_and_5_20(page):
    pg, errors = page
    seed(pg, [['WALL A', 12, 1]])
    setup(pg, distros=[_edison('5-15')], walls=[EDISON_WALL], stores=[EDISON_STORES])
    out = pg.evaluate("""async () => {
        const app = window.app;
        const btn = document.querySelector('[data-hwpop="distro-d1"]');
        btn.click();
        await new Promise(r => setTimeout(r, 300));
        const sel = document.querySelector('[data-lrd-field="distro-row-edison-d1-r1"]');
        const got = sel ? [...sel.options].map(o => o.value) : null;
        const value = sel ? sel.value : null;
        if (sel) { sel.value = '5-20'; sel.dispatchEvent(new Event('change', { bubbles: true })); }
        await new Promise(r => setTimeout(r, 300));
        if (app._hwPopoverClose) app._hwPopoverClose();
        return { got, value, after: app.getDistros()[0].outputRows[0].edisonType };
    }""")
    assert out == {'got': ['5-15', '5-20'], 'value': '5-15', 'after': '5-20'}
    assert errors == []


def test_old_show_edison_reads_5_15_and_flags_over_12a(page):
    """A row saved before the choice: no type stored. It reads 5-15 on the
    checks but packs as laid out - 16 A, twelve panels, 1,800 W = 15.0 A
    on one circuit - so that circuit is past 12 A and flagged, with an
    offer to repack. Repacking marks the row 5-15: 9 + 3 panels."""
    pg, errors = page
    seed(pg, [['WALL A', 12, 1]])
    setup(pg, distros=[_edison(None)], walls=[EDISON_WALL], stores=[EDISON_STORES])
    out = pg.evaluate("""() => {
        const app = window.app, l = app.project.layers[0], d = app.getDistros()[0];
        return { amps: app.circuitCapacity(l).amps, type: app.edisonRowType(app.distroRows(d)[0]),
                 circuits: app.getSocaPlan(l).reduce((n, s) => n + s.legs.length, 0),
                 stored: 'edisonType' in d.outputRows[0] };
    }""")
    assert out['amps'] == pytest.approx(16)     # packs as it was laid out
    assert out['type']['id'] == '5-15' and out['type']['picked'] is False
    assert out['circuits'] == 1 and out['stored'] is False
    lines = [w for w in strip(pg) if 'Edison 5-15' in w['text']]
    # 1,800 W / 120 V = 15.0 A against 12 A
    assert len(lines) == 1 and '15.0 A' in lines[0]['text'] and '(12 A continuous): OVER' in lines[0]['text']
    assert lines[0]['offer'] == 'Repack at 5-15' and not lines[0]['mild']
    pg.evaluate("() => window.app.setDistroEdisonType('d1', null, '5-15')")
    pg.wait_for_timeout(200)
    out = pg.evaluate("""() => { const app = window.app, l = app.project.layers[0];
        app._circuitTailCache = null;
        return [app.circuitCapacity(l).amps, app.getDistros()[0].outputRows[0].edisonType]; }""")
    assert out == [pytest.approx(12), '5-15']
    assert errors == []


# ── 4. a US 240 V screen on no distro packs to 80% ───────────────────────

def test_us_240v_on_no_distro_packs_to_80(page):
    """240 V, 20 A, no distro: 80% is 16 A, 16 x 240 = 3,840 W (100% was
    4,800 W). 277 V: 16 x 277 = 4,432 W. A show whose distros are all EU
    reads 240 V as a UK figure: 20 x 240 = 4,800 W. 230 V on no distro
    stays at its breaker: 20 x 230 = 4,600 W."""
    pg, errors = page
    seed(pg, [['WALL A', 10, 12]])
    cap = "() => { const c = window.app.circuitCapacity(window.app.project.layers[0]); return [c.pct, c.watts, c.us]; }"
    setup(pg, walls=[{'powerVoltage': 240}])
    assert pg.evaluate(cap) == [0.8, pytest.approx(3840), True]
    setup(pg, walls=[{'powerVoltage': 277}])
    assert pg.evaluate(cap) == [0.8, pytest.approx(4432), True]
    # a US distro elsewhere in the show, the screen on none
    setup(pg, walls=[{'powerVoltage': 240}], distros=[distro('d9', 'US', 200, system='120/240')])
    assert pg.evaluate(cap) == [0.8, pytest.approx(3840), True]
    # every distro in the show EU: 240 V is a UK figure
    setup(pg, walls=[{'powerVoltage': 240}], distros=[distro('d9', 'EU', 63, system='230/400')])
    assert pg.evaluate(cap) == [1, pytest.approx(4800), False]
    setup(pg, walls=[{'powerVoltage': 230}])
    assert pg.evaluate(cap) == [1, pytest.approx(4600), False]
    assert errors == []


# ── 5. an auto-packed L21-30 is never OVER ───────────────────────────────

L2130_JS = """() => {
    const app = window.app, l = app.project.layers[0], d = app.getDistros()[0];
    app._circuitTailCache = null;
    const plan = app.getSocaPlan(l);
    const legs = plan.map(s => { const f = app.boxFeedLegAmps(d, [{ layer: l, s }]); return Math.max(f.X, f.Y, f.Z); });
    return { amps: app.circuitCapacity(l).amps, worst: Math.max(...legs),
             circuitMax: Math.max(...plan.flatMap(s => s.legs.map(x => x.amps))),
             strip: (app.renderHardwareDock(), (app._dockPowerWarnings || []).map(w => w.text)
                .filter(t => /L21-30 leg/.test(t))) };
}"""


@pytest.mark.parametrize('watts', [100, 137, 150, 200, 288])
def test_auto_packed_l2130_is_never_over(page, watts):
    """The feed is 24 A per leg (80% of 30 A); three 208 V circuits load a
    leg the square root of 3 times one circuit, so a circuit is held to
    24 / 1.7320508 = 13.856 A (2,882 W). At 150 W the old packer made two
    rows of ten, 3,000 W = 14.42 A, and 14.42 x 1.732 = 25.0 A per leg."""
    pg, errors = page
    seed(pg, [['WALL A', 10, 12]])
    setup(pg, distros=[distro('d1', 'D1', 200, input='cam200')],
          walls=[{'powerBreakoutType': 'l2130-true1', 'panelWatts': watts}],
          assign=[{'distro': 'd1'}])
    out = pg.evaluate(L2130_JS)
    assert out['amps'] == pytest.approx(24 / SQRT3)
    assert out['circuitMax'] <= 24 / SQRT3 + 1e-9
    assert out['worst'] <= 24 + 1e-9, out
    assert out['strip'] == []
    assert errors == []


def test_l2130_with_a_100_percent_main_holds_30a(page):
    """Main 100% rated: the feed limit is the full 30 A, 30 / 1.732 =
    17.32 A - past the 16 A the 20 A breaker gives, so the breaker decides."""
    pg, errors = page
    seed(pg, [['WALL A', 10, 12]])
    setup(pg, distros=[distro('d1', 'D1', 200, input='cam200', main100=True)],
          walls=[{'powerBreakoutType': 'l2130-true1'}], assign=[{'distro': 'd1'}])
    assert pg.evaluate("() => window.app.circuitCapacity(window.app.project.layers[0]).amps") \
        == pytest.approx(16)
    assert errors == []


# ── 6. the 1φ figure on 3-phase ──────────────────────────────────────────

ONE_PH_JS = """() => {
    const app = window.app, l = app.project.layers[0];
    app.updatePowerCapacityDisplay();
    const row = document.getElementById('power-total-amps-1ph-row');
    return { hidden: row.style.display === 'none', three: app.screenOnThreePhase(l) };
}"""


def test_one_phase_figure_hidden_on_3_phase(page):
    """On a 120/208 distro the 1φ line is hidden in the sidebar and the
    binder's Load prints 3φ only: 18,000 / (208 x 1.73) = 50.0 A 3φ."""
    pg, errors = page
    seed(pg, [['WALL A', 10, 12]])
    setup(pg, distros=[distro('d1', 'D1', 400, input='cam400')], assign=[{'distro': 'd1'}])
    assert pg.evaluate(ONE_PH_JS) == {'hidden': True, 'three': True}
    loads = binder_pairs(pg, 'Load')
    facts = [v for v in loads if v.endswith('kW') and '3φ' in v]
    assert facts and all('1φ' not in v for v in facts), loads
    assert any(v.startswith('50.0 A 3φ') for v in facts), facts   # 18000/(208*1.73) = 50.02
    # on no distro the line is there, and the sheet prints both
    setup(pg)
    assert pg.evaluate(ONE_PH_JS) == {'hidden': False, 'three': False}
    loads = binder_pairs(pg, 'Load')
    # 18,000 / 208 = 86.5 A 1φ
    assert any(v.startswith('86.5 A 1φ · 50.0 A 3φ') for v in loads), loads
    assert errors == []


def test_voltage_tooltip_says_208_saves_circuits_not_amps(page):
    pg, errors = page
    tip = pg.evaluate("() => document.getElementById('power-voltage-select')"
                      ".closest('.info-row').getAttribute('data-tooltip')")
    assert '208V saves circuits and cable, not distro amps' in tip
    assert errors == []
