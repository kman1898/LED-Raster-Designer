"""The distro main's continuous limit (owner rulings, 2026-10-18).

A show load is continuous, so the busiest leg of a distro is read against
the main's continuous limit, not the bare rating:

  * US systems (120/208, 120/240, 120): 80% of the rating per leg, unless
    the distro's new "Main 100% rated" switch (`main100`) is on - then the
    rating. The switch is separate from "100% rated breakers", which keeps
    governing the circuit breakers only.
  * EU systems (230/400, 230): the rating (load at or under the breaker);
    the main switch is not offered.
  * An old record with no system: the US rule on a US nominal voltage,
    else the rating.
  * Over the limit: a red error on the header, the OVER flag and the
    strip. "Accept overload" (`overloadAccepted`) turns it amber and says
    accepted - the figures stay, the binder's Load line notes it, it is
    one undo step, and it stays until somebody unticks it.
  * An old show (no `main100`) is off and opens without a write.
  * Presets carry `main100`; the eleven built-in ones leave it off.

The figures, by hand (120V circuits on 120/208, rotating line-to-neutral,
so a leg carries every third circuit, all in phase):
  * 60 rows x 10 panels: 60 circuits on ten multis, 20 on each leg.
  * 198 W panels: a circuit is 1980 W / 120 V = 16.5 A; a leg 20 x 16.5 =
    330 A - over 320 A (80% of 400 A), under 400 A.
  * 192 W panels: 1920 / 120 = 16.0 A; a leg 20 x 16 = 320 A - at the
    limit, not over it.
  * EU: 230V circuits on 230/400, three multis assigned, six circuits a
    leg; 241.5 W panels make 2415 / 230 = 10.5 A a circuit, 63.0 A a leg -
    at a 63 A rating, not over it.

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_distro_main_limit.py -q --browser chromium
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


def _open(pw_browser, url):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
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


# One wall of 60 rows x 10 panels: one row is one circuit, six circuits a
# multi, so ten multis.
SEED_JS = """async () => {
    const proj = await (await fetch('/api/project')).json();
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments;
    await fetch('/api/project', {method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(proj)});
    await fetch('/api/layer/add', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: 'WALL A', columns: 10, rows: 60,
                              cabinet_width: 200, cabinet_height: 200})});
    const p = await (await fetch('/api/project')).json();
    const app = window.app;
    app.project = p;
    app.currentLayer = p.layers[0];
    app.selectedLayerIds = new Set([p.layers[0].id]);
    app.renderLayers();
    return p.layers[0].id;
}"""

# Reshape in the page: the wall's power fields, the distros (migrated on
# read), and the first `multis` multis assigned to d1. Returns what the
# dock and the roll-up say about d1.
SETUP_JS = """(o) => {
    const app = window.app;
    const l = app.project.layers[0];
    Object.assign(l, { powerVoltage: 120, powerAmperage: 20, panelWatts: 198,
                       powerSocaDistro: {}, powerSocaNumber: {}, powerSocaPhasePos: {},
                       powerSocaLengths: {}, powerSocaSplits: [], powerSocaNames: {},
                       powerBreakoutType: null, locked: false }, o.wall || {});
    app.normalizePowerBreakout(l);
    app.project.distros = (o.distros || []).map(d => JSON.parse(JSON.stringify(d)));
    app._circuitTailCache = null;
    app._distroFaceMemo = null;
    app.getDistros();
    const plan = app.getSocaPlan(l);
    plan.slice(0, o.multis == null ? plan.length : o.multis)
        .forEach(s => { l.powerSocaDistro[s.soca] = 'd1'; });
    app._circuitTailCache = null;
    return plan.length;
}"""

READ_JS = """() => {
    const app = window.app;
    app.renderHardwareDock();
    const b = app.getDistroLoads().find(x => x.id === 'd1');
    const unit = document.querySelector('[data-lrd-distro="d1"]');
    const q = (sel) => unit.querySelector(sel);
    const meat = q('.hw-dock-headbar > i');
    const strip = (app._dockPowerWarnings || []).filter(w => /^D1 /.test(w.text));
    // the binder's Service block for d1, caught as the page builds it
    const caught = [];
    const orig = app._bKvLines;
    app._bKvLines = function (book, title, pairs) {
        if (title === 'Service') caught.push(pairs.map(p => p.slice()));
        return orig.apply(this, arguments);
    };
    try {
        app.planBinder(Object.assign(app.readBinderOptions(),
            { scope: { kind: 'show' }, hardware: true, pull: false, cover: false }));
    } finally { app._bKvLines = orig; }
    const service = caught.find(p => p.some(([k]) => k === 'Rating')) || [];
    const load = (service.find(([k]) => k === 'Load') || [])[1] || null;
    return {
        amps: b.amps, legs: b.legs ? [b.legs.X.amps, b.legs.Y.amps, b.legs.Z.amps] : null,
        ratingA: b.ratingA, limitA: b.limitA, limitPct: b.limitPct, over: b.over,
        accepted: b.overloadAccepted, pct: b.pct,
        use: q('.hw-dock-unit-use').textContent,
        useClass: q('.hw-dock-unit-use').className,
        lim: q('.hw-dock-unit-lim') ? q('.hw-dock-unit-lim').textContent : null,
        flag: q('.hw-dock-unit-flag') ? q('.hw-dock-unit-flag').textContent : null,
        flagClass: q('.hw-dock-unit-flag') ? q('.hw-dock-unit-flag').className : null,
        bar: meat ? meat.className : null,
        legBars: [...unit.querySelectorAll('.hw-dock-legbar > i')].map(i => i.className),
        strip: strip.map(w => ({ text: w.text, mild: !!w.mild,
                                 offer: w.offer ? w.offer.label : null })),
        binderLoad: load,
        serviceKeys: service.map(([k]) => k),
    };
}"""

US400 = {'id': 'd1', 'name': 'D1', 'ratingA': 400, 'system': '120/208'}
EU63 = {'id': 'd1', 'name': 'D1', 'ratingA': 63, 'system': '230/400'}


def setup(pg, **o):
    pg.wait_for_timeout(300)
    return pg.evaluate(SETUP_JS, o)


def read(pg):
    return pg.evaluate(READ_JS)


@pytest.fixture(scope="module")
def seeded(page):
    pg, errors = page
    pg.evaluate(SEED_JS)
    pg.wait_for_timeout(800)
    return pg, errors


def test_the_rule_itself(seeded):
    """distroMainLimit by system, switch and old record."""
    pg, _ = seeded
    out = pg.evaluate("""() => {
        const app = window.app;
        const r = (d) => { const x = app.distroMainLimit(d); return [x.pct, x.limitA, x.us]; };
        return {
            us208: r({ ratingA: 400, system: '120/208' }),
            us240: r({ ratingA: 200, system: '120/240' }),
            us120: r({ ratingA: 100, system: '120' }),
            main100: r({ ratingA: 400, system: '120/208', main100: true }),
            breakersOnly: r({ ratingA: 400, system: '120/208', breakers100: true }),
            eu400: r({ ratingA: 63, system: '230/400' }),
            eu230: r({ ratingA: 32, system: '230', main100: true }),
            old208x1: r({ ratingA: 100, voltage: 208, phase: 1 }),
            old240x3: r({ ratingA: 100, voltage: 240, phase: 3 }),
            old220x3: r({ ratingA: 100, voltage: 220, phase: 3 }),
            old400x1: r({ ratingA: 100, voltage: 400, phase: 1 }),
            note: app.distroMainLimitNote(app.distroMainLimit({ ratingA: 100, system: '120/208' })),
            noteEu: app.distroMainLimitNote(app.distroMainLimit({ ratingA: 63, system: '230/400' })),
        };
    }""")
    assert out['us208'] == [0.8, 320, True]
    assert out['us240'] == [0.8, 160, True]
    assert out['us120'] == [0.8, 80, True]
    assert out['main100'] == [1, 400, True]
    assert out['breakersOnly'] == [0.8, 320, True], 'the breakers switch does not lift the main'
    assert out['eu400'] == [1, 63, False]
    assert out['eu230'] == [1, 32, False], 'main100 means nothing on an EU system'
    # no system: US nominal voltages take the US rule, anything else the rating
    assert out['old208x1'] == [0.8, 80, True]
    assert out['old240x3'] == [0.8, 80, True]
    assert out['old220x3'] == [1, 100, False]
    assert out['old400x1'] == [1, 100, False]
    assert out['note'] == '80% of 100 A' and out['noteEu'] == ''


def test_us_400a_at_330a_is_an_error(seeded):
    pg, errors = seeded
    assert setup(pg, distros=[US400], wall={'panelWatts': 198}) == 10
    out = read(pg)
    # by hand: 20 circuits a leg x 1980 W / 120 V = 330 A on every leg
    assert out['legs'] == pytest.approx([330, 330, 330], abs=1e-6), out
    assert out['amps'] == pytest.approx(330, abs=1e-6)
    assert out['limitA'] == 320 and out['limitPct'] == 0.8 and out['ratingA'] == 400
    assert out['over'] and not out['accepted']
    assert out['pct'] == pytest.approx(82.5, abs=1e-6), 'pct stays a share of the rating'
    assert out['use'] == '330.0/320 A', out
    assert 'hw-dock-unit-use-over' in out['useClass']
    assert out['lim'] == '· 80% of 400 A'
    assert out['flag'] == 'OVER' and 'flag-ok' not in out['flagClass']
    assert out['bar'] == 'hw-dock-bar-over'
    assert out['legBars'] == ['hw-dock-bar-over'] * 3
    assert len(out['strip']) == 1 and not out['strip'][0]['mild'], out['strip']
    assert out['strip'][0]['text'] == \
        'D1 — worst leg X 330.0 A / 320 A (80% of 400 A, continuous) — OVER', out['strip']
    assert out['strip'][0]['offer'] == 'Accept overload'
    # the binder's one Load line: every leg, the three-phase total - by
    # hand 118800 W / (208 V x 1.73) = 330.1 A - the power, the limit and
    # the legs past it
    assert out['binderLoad'] == ('X 330.0 · Y 330.0 · Z 330.0 A · 3φ 330.1 A · 118.8 kW · '
                                 'limit 320 A (80% of 400 A) · OVER on X, Y, Z'), out['binderLoad']
    # the legs live on the Load line: no Legs line of their own
    assert 'Legs' not in out['serviceKeys'] and out['serviceKeys'].count('Load') == 1, out['serviceKeys']
    assert not errors, errors


def test_us_400a_at_320a_is_ok(seeded):
    pg, _ = seeded
    setup(pg, distros=[US400], wall={'panelWatts': 192})
    out = read(pg)
    # by hand: 20 x 1920 / 120 = 320 A - at the limit, not past it
    assert out['amps'] == pytest.approx(320, abs=1e-6), out
    assert not out['over']
    assert out['use'] == '320.0/320 A' and out['lim'] == '· 80% of 400 A'
    assert out['flag'] is None and out['bar'] == ''
    assert 'over' not in out['useClass']
    assert out['strip'] == []
    # 115200 / (208 x 1.73) = 320.1 A
    assert out['binderLoad'] == ('X 320.0 · Y 320.0 · Z 320.0 A · 3φ 320.1 A · 115.2 kW · '
                                 'limit 320 A (80% of 400 A)'), out['binderLoad']


def test_main_100_rated_lifts_the_limit_to_the_rating(seeded):
    pg, _ = seeded
    setup(pg, distros=[dict(US400, main100=True)], wall={'panelWatts': 198})
    out = read(pg)
    assert out['limitA'] == 400 and out['limitPct'] == 1
    assert not out['over'] and out['use'] == '330.0/400 A' and out['lim'] is None
    assert out['strip'] == []
    assert out['binderLoad'] == 'X 330.0 · Y 330.0 · Z 330.0 A · 3φ 330.1 A · 118.8 kW · 100% rated main'
    # the breakers switch alone does not
    setup(pg, distros=[dict(US400, breakers100=True)], wall={'panelWatts': 198})
    assert read(pg)['over']


def test_eu_63a_at_63a_is_ok_and_past_it_is_over(seeded):
    pg, _ = seeded
    setup(pg, distros=[EU63], multis=3,
          wall={'powerVoltage': 230, 'powerAmperage': 16, 'panelWatts': 241.5})
    out = read(pg)
    # by hand: 6 circuits a leg x 2415 W / 230 V = 63.0 A
    assert out['legs'] == pytest.approx([63, 63, 63], abs=1e-6), out
    assert out['limitA'] == 63 and out['limitPct'] == 1
    assert not out['over'] and out['use'] == '63.0/63 A' and out['lim'] is None
    assert out['strip'] == []
    # L1/L2/L3, and the total at 400 V: 43470 / (400 x 1.73) = 62.8 A
    assert out['binderLoad'] == 'L1 63.0 · L2 63.0 · L3 63.0 A · 3φ 62.8 A · 43.5 kW', out['binderLoad']
    # 245 W: 6 x 2450 / 230 = 63.9 A - over the breaker, no 80% and no
    # main switch on an EU distro
    setup(pg, distros=[EU63], multis=3,
          wall={'powerVoltage': 230, 'powerAmperage': 16, 'panelWatts': 245})
    out = read(pg)
    assert out['over'] and out['use'] == '63.9/63 A' and out['lim'] is None
    assert out['strip'][0]['text'] == 'D1 — worst leg L1 63.9 A / 63 A (101%) — OVER', out['strip']


def test_accept_overload_turns_amber_notes_the_binder_and_undoes(seeded):
    pg, _ = seeded
    setup(pg, distros=[US400], wall={'panelWatts': 198})
    pg.evaluate("() => { window.app.saveState('Setup'); window.app.renderHardwareDock(); }")
    before = pg.evaluate("() => window.app.historyIndex")
    # the strip's offer is the tick, one undoable step
    pg.locator('#hw-dock-issues button', has_text='Accept overload').click()
    pg.wait_for_timeout(300)
    hist = pg.evaluate("() => [window.app.historyIndex, window.app.history[window.app.historyIndex].action]")
    assert hist == [before + 1, 'Accept Overload']
    out = read(pg)
    assert out['accepted'] and out['over'], 'accepting never hides the overload'
    assert out['use'] == '330.0/320 A', 'the figures stay'
    assert 'hw-dock-unit-use-accepted' in out['useClass']
    assert out['flag'] == 'OVER · accepted' and 'hw-dock-unit-flag-ok' in out['flagClass']
    assert out['bar'] == 'hw-dock-bar-accepted'
    assert out['legBars'] == ['hw-dock-bar-accepted'] * 3
    assert out['strip'] == [{'text': 'D1 — worst leg X 330.0 A / 320 A (80% of 400 A, continuous)'
                                     ' — over, accepted', 'mild': True, 'offer': None}], out['strip']
    assert out['binderLoad'] == ('X 330.0 · Y 330.0 · Z 330.0 A · 3φ 330.1 A · 118.8 kW · '
                                 'limit 320 A (80% of 400 A) · OVER on X, Y, Z · overload accepted')
    # it does not clear itself when the load changes - under the limit it
    # simply has nothing to say, and back over it is still accepted
    pg.evaluate("() => { const l = window.app.project.layers[0]; l.panelWatts = 150; "
                "window.app._circuitTailCache = null; }")
    out = read(pg)
    assert not out['over'] and out['flag'] is None and out['strip'] == []
    assert out['binderLoad'].endswith('limit 320 A (80% of 400 A)'), out['binderLoad']
    assert pg.evaluate("() => window.app.getDistros()[0].overloadAccepted") is True
    pg.evaluate("() => { const l = window.app.project.layers[0]; l.panelWatts = 198; "
                "window.app._circuitTailCache = null; }")
    assert read(pg)['flag'] == 'OVER · accepted'
    # undo takes the acceptance back; redo brings it again
    pg.evaluate("() => window.app.undo()")
    pg.wait_for_timeout(600)
    pg.evaluate("() => { window.app._circuitTailCache = null; }")
    assert pg.evaluate("() => 'overloadAccepted' in window.app.getDistros()[0]") is False
    out = read(pg)
    assert out['flag'] == 'OVER' and not out['strip'][0]['mild']
    pg.evaluate("() => window.app.redo()")
    pg.wait_for_timeout(600)
    pg.evaluate("() => { window.app._circuitTailCache = null; }")
    assert read(pg)['flag'] == 'OVER · accepted'


def test_the_gear_offers_main_100_beside_the_breakers_and_accept_while_over(seeded):
    pg, _ = seeded
    setup(pg, distros=[US400], wall={'panelWatts': 198})
    gear = """() => {
        const app = window.app;
        app.renderHardwareDock();
        document.querySelector('[data-hwpop="distro-d1"]').click();
        const pop = document.getElementById('hw-gear-popover');
        const f = (k) => pop.querySelector(`[data-lrd-field="distro-${k}-d1"]`);
        const lab = (k) => f(k) ? f(k).closest('label') : null;
        const r = {
            breakers: !!f('breakers100'), main: !!f('main100'),
            sameRow: !!(f('main100') && f('breakers100')
                && f('main100').closest('div') === f('breakers100').closest('div')),
            mainText: lab('main100') ? lab('main100').textContent : null,
            mainTip: lab('main100') ? lab('main100').title : null,
            accept: lab('overload-accepted') ? lab('overload-accepted').textContent : null,
        };
        return r;
    }"""
    out = pg.evaluate(gear)
    assert out['breakers'] and out['main'] and out['sameRow'], out
    assert out['mainText'] == 'Main 100% rated'
    assert '80%' in out['mainTip'] and 'continuous' in out['mainTip']
    assert 'tail' not in out['mainTip'].lower()
    assert out['accept'] == 'Accept overload — busiest leg 330.0 A of 320 A (80% of 400 A)'
    # ticking Main 100% rated lifts the limit, one step, and the accept row goes
    pg.locator('[data-lrd-field="distro-main100-d1"]').check()
    pg.wait_for_timeout(300)
    assert pg.evaluate("() => window.app.getDistros()[0].main100") is True
    out = pg.evaluate(gear)
    assert out['accept'] is None
    assert not read(pg)['over']
    pg.evaluate("() => window.app._hwPopoverClose()")
    # EU: no main switch (and no breakers switch, as before)
    setup(pg, distros=[EU63], multis=3,
          wall={'powerVoltage': 230, 'powerAmperage': 16, 'panelWatts': 241.5})
    out = pg.evaluate(gear)
    assert not out['main'] and not out['breakers'], out
    pg.evaluate("() => window.app._hwPopoverClose()")


def test_a_locked_screen_does_not_block_the_distro_settings(seeded):
    """Distro settings are the project's, not a screen's (the existing
    pattern: updateDistro takes no lock)."""
    pg, _ = seeded
    setup(pg, distros=[US400], wall={'panelWatts': 198, 'locked': True})
    out = pg.evaluate("""() => {
        const app = window.app;
        app.updateDistro('d1', { main100: true });
        app.updateDistro('d1', { overloadAccepted: true });
        const d = app.getDistros()[0];
        return [d.main100, d.overloadAccepted, app.project.layers[0].locked];
    }""")
    assert out == [True, True, True]


def test_the_fields_persist_through_the_server_and_a_reload(e2e_server, pw_browser, seeded):
    pg, _ = seeded
    setup(pg, distros=[US400], wall={'panelWatts': 198})
    pg.evaluate("""async () => {
        const app = window.app;
        await app.updateLayers(app.project.layers);
        app.updateDistro('d1', { main100: true });
        app.updateDistro('d1', { overloadAccepted: true });
        await app._distroPushQueue;
    }""")
    pg.wait_for_timeout(500)
    served = pg.evaluate("async () => (await (await fetch('/api/project')).json()).distros")
    assert served[0]['main100'] is True and served[0]['overloadAccepted'] is True, served
    # unticking forgets the keys, the way an old show never had them
    pg.evaluate("""async () => {
        window.app.updateDistro('d1', { overloadAccepted: false });
        await window.app._distroPushQueue;
    }""")
    served = pg.evaluate("async () => (await (await fetch('/api/project')).json()).distros")
    assert 'overloadAccepted' not in served[0] and served[0]['main100'] is True
    pg.evaluate("""async () => {
        window.app.updateDistro('d1', { overloadAccepted: true });
        await window.app._distroPushQueue;
    }""")
    pg.wait_for_timeout(300)
    # a fresh page reads them back
    context, pg2, errors = _open(pw_browser, e2e_server)
    try:
        out = pg2.evaluate("""() => {
            const app = window.app;
            const d = app.getDistros()[0];
            const b = app.getDistroLoads().find(x => x.id === 'd1');
            return [d.main100, d.overloadAccepted, b.limitA];
        }""")
        assert out == [True, True, 400], out
        assert not errors, errors
    finally:
        context.close()


OLD_SHOW = {
    'id': 'd1', 'name': 'OLD', 'ratingA': 100, 'system': '120/208', 'voltage': 208,
    'phase': 3, 'input': 'cam100', 'breakers100': True,
    'outputRows': [{'id': 'r1', 'connector': 'soca', 'count': 2, 'coupling': 'll',
                    'breakerA': 20, 'pairedWith': None}],
}


def test_an_old_show_opens_unchanged_on_the_server(e2e_server, pw_browser, seeded):
    """No `main100` on the record: off, so the 80% error shows where the
    load is past it - and opening the show, the dock and the gear write
    nothing."""
    pg, _ = seeded
    pg.evaluate("""async (d) => {
        const proj = await (await fetch('/api/project')).json();
        const l = proj.layers[0];
        Object.assign(l, { powerVoltage: 208, powerAmperage: 20, panelWatts: 150,
                           powerSocaDistro: { 1: 'd1', 2: 'd1' }, powerSocaNumber: {},
                           powerSocaPhasePos: {}, powerSocaSplits: [], locked: false });
        proj.distros = [d];
        await fetch('/api/project', {method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(proj)});
    }""", OLD_SHOW)
    pg.wait_for_timeout(500)
    before = pg.evaluate("async () => (await (await fetch('/api/project')).json()).distros")
    assert before == [OLD_SHOW]
    context, pg2, errors = _open(pw_browser, e2e_server)
    try:
        writes = []
        pg2.on('request', lambda r: writes.append(r.url) if (
            r.method in ('POST', 'PUT') and r.url.endswith('/api/project')) else None)
        pg2.locator('[data-mode="power"]').click()
        pg2.wait_for_timeout(400)
        out = pg2.evaluate("""() => {
            const app = window.app;
            app.renderHardwareDock();
            document.querySelector('[data-hwpop="distro-d1"]').click();
            const main = document.querySelector('[data-lrd-field="distro-main100-d1"]');
            const b = app.getDistroLoads().find(x => x.id === 'd1');
            const r = { main: main ? main.checked : null, limitA: b.limitA, amps: b.amps,
                        over: b.over };
            app._hwPopoverClose();
            return r;
        }""")
        pg2.wait_for_timeout(800)
        assert out['main'] is False and out['limitA'] == 80, out
        after = pg2.evaluate("async () => (await (await fetch('/api/project')).json()).distros")
        assert after == [OLD_SHOW], after
        assert writes == [], writes
        assert not errors, errors
    finally:
        context.close()


def test_presets_carry_main_100(seeded):
    pg, _ = seeded
    setup(pg, distros=[dict(US400, id='d1', name='P'), dict(US400, id='d2', name='Q', main100=True)])
    out = pg.evaluate("""async () => {
        const app = window.app;
        const builtIn = app.builtInDistroPresets();
        app.applyDistroPreset('d1', builtIn.find(p => p.id === 'us-400-8soca120-8soca208'));
        app.updateDistro('d1', { main100: true });
        const body = app._distroPresetBody(app.getDistros()[0]);
        await app.saveDistroPreset('d1', 'Main limit test rack');
        const listed = await app.loadCustomDistroPresets(true);
        const saved = listed.find(p => p.name === 'Main limit test rack');
        // a preset with main100 lays it on; a built-in one (none) takes it off
        app.updateDistro('d2', { main100: false });
        app.applyDistroPreset('d2', saved);
        const onD2 = app.getDistros()[1].main100;
        app.applyDistroPreset('d2', builtIn[0]);
        const offD2 = 'main100' in app.getDistros()[1];
        await app.deleteDistroPreset('Main limit test rack');
        return { body: body.main100, saved: saved && saved.distro.main100, onD2, offD2,
                 builtInMain: builtIn.filter(p => 'main100' in p).length,
                 overload: 'overloadAccepted' in body };
    }""")
    assert out == {'body': True, 'saved': True, 'onD2': True, 'offD2': False,
                   'builtInMain': 0, 'overload': False}, out


def test_the_presets_route_validates_main_100(client):
    import routes_distro_presets as rdp
    body = {'system': '120/208', 'input': 'cam400', 'ratingA': 400, 'breakers100': False,
            'main100': True, 'phasing': None, 'directPhasing': None,
            'rows': [{'id': 'r1', 'connector': 'soca', 'count': 8, 'coupling': 'll',
                      'breakerA': 20, 'pairedWith': None}]}
    r = client.put('/api/distro-presets', json={'name': 'Main route test', 'distro': body})
    assert r.status_code == 200
    with open(rdp.DISTRO_PRESETS_FILE, encoding='utf-8') as f:
        stored = [p for p in json.load(f)['presets'] if p['name'] == 'Main route test']
    assert stored[0]['distro']['main100'] is True
    # a preset without it (saved before it existed) is still a preset
    legacy = {k: v for k, v in body.items() if k != 'main100'}
    assert client.put('/api/distro-presets',
                      json={'name': 'Main route test', 'distro': legacy}).status_code == 200
    for bad in ('yes', 1, None):
        r = client.put('/api/distro-presets',
                       json={'name': 'Main route test', 'distro': dict(body, main100=bad)})
        assert r.status_code == 400, bad
    # overloadAccepted is a show's call, never a preset's: dropped on save
    r = client.put('/api/distro-presets', json={'name': 'Main route test',
                                                'distro': dict(body, overloadAccepted=True)})
    saved = [p for p in r.get_json()['presets'] if p['name'] == 'Main route test'][0]
    assert 'overloadAccepted' not in saved['distro']
    client.delete('/api/distro-presets', json={'name': 'Main route test'})


# The binder's one Load line for each kind of system, from a load record
# laid out by hand (the shape getDistroLoads returns), so each case reads
# exactly: 3φ prints every leg and the 3φ total at the line-to-line
# voltage, 120/240 its two legs and no 3φ figure, a single hot one figure;
# OVER names only the legs past the limit.
LOAD_TEXT_JS = """(cases) => {
    const app = window.app;
    return cases.map(([dist, legs, amps, watts, limitA, over, accepted]) => {
        app.project.distros = [Object.assign({ id: 'dx', name: 'DX' }, dist)];
        app._distroFaceMemo = null;
        const d = app.getDistros().find(x => x.id === 'dx');
        const names = legs ? Object.keys(legs) : [];
        const L = legs ? Object.assign({ names }, ...names.map(k => ({ [k]: { amps: legs[k], over: legs[k] > limitA } }))) : null;
        return app._bDistroLoadText(d, { legs: L, amps, watts, limitA, over, overloadAccepted: accepted });
    });
}"""


def test_the_binder_load_line_names_every_leg_and_the_3_phase_total(seeded):
    pg, errors = seeded
    out = pg.evaluate(LOAD_TEXT_JS, [
        # a show's 100 A 120/208 service, its X leg alone past 80 A:
        # 30000 / (208 x 1.73) = 83.4 A
        [{'ratingA': 100, 'system': '120/208'}, {'X': 87.1, 'Y': 79.4, 'Z': 79.4}, 87.1, 30000, 80, True, False],
        # two legs past it, accepted
        [{'ratingA': 100, 'system': '120/208'}, {'X': 87.1, 'Y': 79.4, 'Z': 81.4}, 87.1, 30000, 80, True, True],
        # 230/400: L1/L2/L3, the total at 400 V - 30000 / 692 = 43.4 A -
        # the limit the rating, so no limit is said
        [{'ratingA': 63, 'system': '230/400'}, {'X': 45.0, 'Y': 43.0, 'Z': 42.0}, 45.0, 30000, 63, False, False],
        # 120/240 split phase: two legs, no 3φ figure
        [{'ratingA': 100, 'system': '120/240'}, {'X': 62.5, 'Y': 50.0}, 62.5, 13500, 80, False, False],
        # 120V single hot: one figure
        [{'ratingA': 60, 'system': '120'}, None, 50.0, 6000, 48, True, False],
        # the main 100% rated
        [{'ratingA': 100, 'system': '120/208', 'main100': True}, {'X': 87.1, 'Y': 79.4, 'Z': 79.4},
         87.1, 30000, 100, False, False],
    ])
    assert out == [
        'X 87.1 · Y 79.4 · Z 79.4 A · 3φ 83.4 A · 30.0 kW · limit 80 A (80% of 100 A) · OVER on X',
        'X 87.1 · Y 79.4 · Z 81.4 A · 3φ 83.4 A · 30.0 kW · limit 80 A (80% of 100 A) · OVER on X, Z'
        ' · overload accepted',
        'L1 45.0 · L2 43.0 · L3 42.0 A · 3φ 43.4 A · 30.0 kW',
        'X 62.5 · Y 50.0 A · 13.5 kW · limit 80 A (80% of 100 A)',
        '50.0 A · 6.0 kW · limit 48 A (80% of 60 A) · OVER',
        'X 87.1 · Y 79.4 · Z 79.4 A · 3φ 83.4 A · 30.0 kW · 100% rated main',
    ], out
    # no percentage and no separate Legs line: the Service block's pairs
    assert '%' not in out[0].replace('80% of', '')
    assert not errors, errors
