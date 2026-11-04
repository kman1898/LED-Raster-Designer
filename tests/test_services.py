"""The SERVICE: the house power several distros are fed from (owner
rulings, 2026-10-20).

  * A Service card sits in the Hardware tray's Power view above the
    distros: a name, an amps-per-leg rating, a system (the systems a distro
    offers) and its own "100% rated" switch. Stored on the project
    (project['services'], distro['serviceId']), saved, loaded and undoable;
    a show with no services reads and saves exactly as it always did.
  * A distro goes on a service by dragging its header bar onto the card, or
    by picking the service behind its gear; it comes off by picking None
    there, or from the card's gear. Only a distro of the SAME system goes on
    - anything else is refused with the reason. Every change is one history
    entry.
  * The checks, on the card and in the binder: each leg's load (its
    distros' leg loads added) against the service, at 80% of the rating on a
    US system unless the service is 100% rated, and the imbalance across all
    its distros together. The ratings of the distros connected to it, added
    up, are a plain fact beside the service's own (2026-11-03).
  * The binder: a distro on a service names it in its SERVICE block ("Fed
    from"); a Service sheet lists each service's distros with their ratings,
    the leg totals, the limit, the imbalance and any OVER or ratings
    warning. House power is not pulled: no pull sheet rows.

The figures, by hand (120V circuits on 120/208, rotating line-to-neutral,
so a full multi puts two circuits on each leg):
  * WALL A, 10 panels x 60 rows: 60 circuits on ten multis. 198 W panels
    make a circuit 1980 W / 120 V = 16.5 A, so five multis put 10 circuits,
    165 A, on each leg of their distro.
  * Two distros of five multis each on one 400 A service: 330 A a leg -
    over 320 A (80% of 400 A), under 400 A (100% rated). At 192 W a leg is
    320 A: at the limit, not over it.
  * WALL B, 10 panels x 4 rows: one multi of four circuits, legs X X Y Z -
    X 33 A, Y 16.5 A, Z 16.5 A: alone 50% imbalance (max deviation 11 from
    an average of 22). Beside five full multis on the same service the legs
    are X 198, Y 181.5, Z 181.5 A: 5.9% (11 from 187).

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_services.py -q --browser chromium
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


def _open(pw_browser, url, viewport=None):
    context = pw_browser.new_context(viewport=viewport or {'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(url, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    pg.wait_for_timeout(1500)
    return context, pg, errors


# WALL A (10 x 60, ten multis) and WALL B (10 x 4, one multi of four).
SEED_JS = """async () => {
    const proj = await (await fetch('/api/project')).json();
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.services;
    delete proj.port_assignments;
    await fetch('/api/project', {method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(proj)});
    for (const [name, rows, x] of [['WALL A', 60, 0], ['WALL B', 4, 2400]]) {
        await fetch('/api/layer/add', {method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name, columns: 10, rows, cabinet_width: 200, cabinet_height: 200,
                                  offset_x: x, offset_y: 0})});
    }
    const p = await (await fetch('/api/project')).json();
    const app = window.app;
    app.project = p;
    app.currentLayer = p.layers[0];
    app.selectedLayerIds = new Set([p.layers[0].id]);
    app.renderLayers();
    return p.layers.map(l => l.name);
}"""

# The show reshaped in the page: both walls' power, the distros and the
# services given, and `assign` = [[wall, first multi, last multi, distro]]
# (multis counted from 0 in plan order). History starts here.
SETUP_JS = """(o) => {
    const app = window.app;
    for (const l of app.project.layers) {
        // A US circuit packs to 80 percent of its breaker (2026-10-22): the amps here are x 1.25, so a circuit carries what this wall was laid out for.
        Object.assign(l, { powerVoltage: 120, powerAmperage: 25, panelWatts: o.watts || 198,
                           powerSocaDistro: {}, powerSocaNumber: {}, powerSocaPhasePos: {},
                           powerSocaLengths: {}, powerSocaSplits: [], powerSocaNames: {},
                           powerBreakoutType: null, locked: false });
        app.normalizePowerBreakout(l);
    }
    app.project.distros = (o.distros || []).map(d => JSON.parse(JSON.stringify(d)));
    if (o.services) app.project.services = o.services.map(s => JSON.parse(JSON.stringify(s)));
    else delete app.project.services;
    app._circuitTailCache = null;
    app._distroFaceMemo = null;
    app.getDistros();
    for (const [wall, a, b, id] of (o.assign || [])) {
        const l = app.project.layers.find(x => x.name === wall);
        const plan = app.getSocaPlan(l);
        plan.slice(a, b + 1).forEach(s => { l.powerSocaDistro[s.soca] = id; });
    }
    app._circuitTailCache = null;
    app.updateLayers(app.project.layers);
    app._persistDistros();
    app._restateNaming();
    app.renderHardwareDock();
    app.resetHistory('Service Seed');
    return app.project.layers.map(l => app.getSocaPlan(l).length);
}"""

# What the roll-ups, the card and the strip say.
READ_JS = """() => {
    const app = window.app;
    app._circuitTailCache = null;
    app.renderHardwareDock();
    const legs = (L) => L && L.legs ? L.legs.names.map(k => +L.legs[k].amps.toFixed(3)) : null;
    const distros = {};
    for (const L of app.getDistroLoads()) if (L.id) distros[L.id] = { legs: legs(L), amps: L.amps };
    const services = {};
    for (const S of app.getServiceLoads()) {
        const card = document.querySelector(`[data-lrd-service="${S.id}"]`);
        const q = (sel) => card && card.querySelector(sel);
        services[S.id] = {
            legs: legs(S), amps: S.amps, limitA: S.limitA, over: S.over,
            legOver: S.legs ? S.legs.names.map(k => S.legs[k].over) : null,
            imbalance: +S.imbalancePct.toFixed(3), ratingSum: S.ratingSum,
            ratingsOver: S.ratingsOver, distros: S.distros.map(r => r.distro.id),
            card: !!card,
            size: q('.hw-dock-svc-size') ? q('.hw-dock-svc-size').textContent : null,
            name: q('.hw-dock-name') ? q('.hw-dock-name').value : null,
            use: q('.hw-dock-unit-use') ? q('.hw-dock-unit-use').textContent : null,
            useOver: !!(q('.hw-dock-unit-use') && q('.hw-dock-unit-use').classList.contains('hw-dock-unit-use-over')),
            lim: q('.hw-dock-unit-lim') ? q('.hw-dock-unit-lim').textContent : null,
            flag: q('.hw-dock-unit-flag') ? q('.hw-dock-unit-flag').textContent : null,
            legsLine: q('.hw-dock-legs') ? q('.hw-dock-legs').textContent : null,
            legBars: card ? [...card.querySelectorAll('.hw-dock-legbar > i')].map(i => i.className) : [],
            chips: card ? [...card.querySelectorAll('.hw-dock-svc-chip')].map(c => c.textContent) : [],
            sum: q('.hw-dock-svc-sum') ? q('.hw-dock-svc-sum').textContent : null,
            sumOver: !!(q('.hw-dock-svc-sum') && q('.hw-dock-svc-sum').classList.contains('hw-dock-svc-sum-over')),
            empty: q('.hw-dock-svc-empty') ? q('.hw-dock-svc-empty').textContent : null,
        };
    }
    return {
        distros, services,
        strip: (app._dockPowerWarnings || []).map(w => ({ text: w.text, mild: !!w.mild })),
        serviceIds: Object.fromEntries(app.getDistros().map(d => [d.id, d.serviceId || null])),
        stored: app.project.services ? app.project.services.map(s => Object.assign({}, s)) : null,
    };
}"""

HIST_JS = "() => window.app.history.slice(0, window.app.historyIndex + 1).map(h => h.action)"
STATUS_JS = "() => document.getElementById('status-message').textContent"
TOASTS_JS = "() => [...document.querySelectorAll('#app-toast-host > div')].map(t => t.textContent)"

US = lambda i, name, rating=400, system='120/208': {  # noqa: E731
    'id': i, 'name': name, 'ratingA': rating, 'system': system}
SVC = lambda i='s1', name='HOUSE', rating=400, system='120/208', **kw: dict(  # noqa: E731
    {'id': i, 'name': name, 'ratingA': rating, 'system': system,
     'voltage': {'120/208': 208, '120/240': 240, '230/400': 400}.get(system, 120),
     'phase': 3 if system in ('120/208', '230/400') else 1}, **kw)


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context, pg, errors = _open(pw_browser, e2e_server)
    pg.evaluate(SEED_JS)
    pg.wait_for_timeout(800)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(500)
    yield pg, errors
    context.close()


def setup(pg, **o):
    # The previous gesture's server echo lands first, so it cannot replace
    # what this setup writes.
    pg.wait_for_timeout(400)
    pg.evaluate("() => { const h = document.getElementById('app-toast-host'); if (h) h.innerHTML = '';"
                " window.app._hwPopoverClose && window.app._hwPopoverClose(); }")
    n = pg.evaluate(SETUP_JS, o)
    # and this setup's own echo has landed before the test edits locally (a
    # fixed wait was too short on a busy CI runner)
    pg.evaluate("async () => { await window.app._layerSavesSettled(); }")
    pg.wait_for_timeout(300)
    return n


def read(pg):
    return pg.evaluate(READ_JS)


def center(pg, selector):
    pg.evaluate("(s) => document.querySelector(s).scrollIntoView({block: 'center'})", selector)
    box = pg.locator(selector).first.bounding_box()
    assert box, f'nothing at {selector}'
    return box['x'] + box['width'] / 2, box['y'] + box['height'] / 2


def drag(pg, sx, sy, ex, ey, mid=None):
    pg.mouse.move(sx, sy)
    pg.mouse.down()
    pg.mouse.move((sx + ex) / 2, (sy + ey) / 2, steps=5)
    pg.mouse.move(ex, ey, steps=5)
    pg.wait_for_timeout(150)
    seen = mid() if mid else None
    pg.mouse.up()
    pg.wait_for_timeout(500)
    return seen


def drag_distro_onto_service(pg, distro_id, service_id, mid=None):
    """A real pointer drag: the distro's header bar (its empty stretch)
    onto the Service card's middle."""
    sx, sy = center(pg, f'[data-lrd-distro="{distro_id}"] .hw-dock-dragcue')
    pg.evaluate("(s) => document.querySelector(s).scrollIntoView({block: 'center'})",
                f'[data-lrd-service="{service_id}"]')
    sx, sy = (lambda b: (b['x'] + b['width'] / 2, b['y'] + b['height'] / 2))(
        pg.locator(f'[data-lrd-distro="{distro_id}"] .hw-dock-dragcue').bounding_box())
    box = pg.locator(f'[data-lrd-service="{service_id}"]').bounding_box()
    return drag(pg, sx, sy, box['x'] + box['width'] / 2, box['y'] + box['height'] / 2, mid)


def open_gear(pg, pop_id):
    pg.evaluate("() => window.app._hwPopoverClose && window.app._hwPopoverClose()")
    x, y = center(pg, f'[data-hwpop="{pop_id}"]')
    pg.mouse.click(x, y)
    pg.wait_for_timeout(250)
    assert pg.evaluate("() => document.getElementById('hw-gear-popover').style.display") == 'block'


def pick(pg, field, value):
    pg.locator(f'#hw-gear-popover [data-lrd-field="{field}"]').select_option(value)
    pg.wait_for_timeout(300)


def undo(pg):
    pg.evaluate("() => window.app.undo()")
    pg.wait_for_timeout(500)


# ── add a service ─────────────────────────────────────────────────────────

def test_add_service_puts_a_card_above_the_distros(page):
    pg, errors = page
    setup(pg, distros=[US('d1', 'SL')], assign=[['WALL A', 0, 4, 'd1']])
    assert read(pg)['stored'] is None, 'a show with no services carries no key'
    assert pg.locator('[data-lrd-service]').count() == 0
    x, y = center(pg, '#power-service-add')
    pg.mouse.click(x, y)
    pg.wait_for_timeout(400)
    out = read(pg)
    assert out['stored'] == [{'id': 's1', 'name': 'SERVICE 1', 'ratingA': 400, 'system': '120/208',
                              'voltage': 208, 'phase': 3}], out['stored']
    s = out['services']['s1']
    assert s['card'] and s['name'] == 'SERVICE 1' and s['size'] == '400 A · 120/208V 3φ', s
    assert s['empty'] == "Drag a distro's header bar here.", s
    assert s['use'] == '0.0/320 A' and s['lim'] == '· 80% of 400 A', s
    # The strip sits above the distro columns, spanning the tray.
    geo = pg.evaluate("""() => {
        const strip = document.querySelector('#hardware-dock-body > .hw-dock-services');
        const col = document.querySelector('#hardware-dock-body > .hw-dock-col');
        const body = document.getElementById('hardware-dock-body');
        const r = strip.getBoundingClientRect(), c = col.getBoundingClientRect();
        return { above: r.bottom <= c.top + 1, first: body.firstElementChild === strip,
                 wide: r.width > body.clientWidth * 0.8 };
    }""")
    assert geo == {'above': True, 'first': True, 'wide': True}, geo
    assert pg.evaluate(HIST_JS)[-1] == 'Add Service'
    undo(pg)
    out = read(pg)
    assert out['stored'] is None and not out['services'], out['stored']
    assert pg.locator('[data-lrd-service]').count() == 0
    assert not errors, errors


# ── putting a distro on, taking it off ────────────────────────────────────

def test_drag_a_distro_s_header_bar_onto_the_service_card(page):
    pg, errors = page
    # nothing assigned: two short distros side by side, so the reorder
    # below has one nearest gap
    setup(pg, distros=[US('d1', 'SL'), US('d2', 'SR', 200)], services=[SVC()])
    lit = drag_distro_onto_service(pg, 'd1', 's1', mid=lambda: pg.evaluate(
        "() => document.querySelector('[data-lrd-service=\"s1\"]').className"))
    assert 'hw-dock-svc-drop' in lit and 'hw-dock-svc-drop-no' not in lit, lit
    out = read(pg)
    assert out['serviceIds'] == {'d1': 's1', 'd2': None}, out['serviceIds']
    assert out['services']['s1']['chips'] == ['SL 400 A · nothing connected'], out['services']['s1']
    assert pg.evaluate(HIST_JS)[-1] == 'Put Distro on Service'
    assert pg.evaluate(STATUS_JS) == 'SL is on HOUSE · 400 A · 120/208V 3φ.'
    assert 'hw-dock-svc-drop' not in pg.evaluate(
        "() => document.querySelector('[data-lrd-service=\"s1\"]').className"), 'the light stayed on'
    # The same drag again is no change: said, and no entry.
    n = len(pg.evaluate(HIST_JS))
    drag_distro_onto_service(pg, 'd1', 's1')
    assert pg.evaluate(STATUS_JS) == 'SL is already on HOUSE.'
    assert len(pg.evaluate(HIST_JS)) == n
    # Along the tray, off the card, the header still reorders.
    sx, sy = center(pg, '[data-lrd-distro="d2"] .hw-dock-dragcue')
    unit = pg.locator('[data-lrd-distro="d1"]').bounding_box()
    drag(pg, sx, sy, unit['x'] + 6, unit['y'] + 12)
    assert [d['id'] for d in pg.evaluate("() => window.app.getDistros()")] == ['d2', 'd1']
    assert pg.evaluate(HIST_JS)[-1] == 'Reorder Distros'
    undo(pg)
    undo(pg)
    assert read(pg)['serviceIds'] == {'d1': None, 'd2': None}
    assert not errors, errors


def test_pick_the_service_in_the_distro_gear_and_none_takes_it_off(page):
    pg, errors = page
    setup(pg, distros=[US('d1', 'SL'), US('d2', 'SR', 200)], services=[SVC()])
    open_gear(pg, 'distro-d2')
    opts = pg.evaluate("""() => [...document.querySelectorAll(
        '#hw-gear-popover [data-lrd-field="distro-service-d2"] option')].map(o => [o.value, o.textContent])""")
    assert opts == [['', 'None'], ['s1', 'HOUSE · 400 A · 120/208V 3φ']], opts
    pick(pg, 'distro-service-d2', 's1')
    assert read(pg)['serviceIds']['d2'] == 's1'
    assert pg.evaluate(HIST_JS)[-1] == 'Put Distro on Service'
    assert pg.locator('#hw-gear-popover [data-lrd-field="distro-service-d2"]').input_value() == 's1'
    pick(pg, 'distro-service-d2', '')
    assert read(pg)['serviceIds']['d2'] is None
    assert pg.evaluate(HIST_JS)[-1] == 'Take Distro off Service'
    undo(pg)
    assert read(pg)['serviceIds']['d2'] == 's1', 'undo did not put it back on'
    undo(pg)
    assert read(pg)['serviceIds']['d2'] is None
    pg.evaluate("() => window.app._hwPopoverClose()")
    assert not errors, errors


def test_take_a_distro_off_from_the_service_card_s_gear(page):
    pg, errors = page
    setup(pg, distros=[dict(US('d1', 'SL'), serviceId='s1'), dict(US('d2', 'SR', 200), serviceId='s1')],
          services=[SVC()])
    open_gear(pg, 'service-s1')
    rows = pg.evaluate("() => [...document.querySelectorAll('#hw-gear-popover .hw-pop-svc-name')].map(e => e.textContent)")
    assert rows == ['SL · 400 A', 'SR · 200 A'], rows
    pg.locator('#hw-gear-popover [data-lrd-field="service-off-s1-d1"]').click()
    pg.wait_for_timeout(300)
    assert read(pg)['serviceIds'] == {'d1': None, 'd2': 's1'}
    assert pg.evaluate(HIST_JS)[-1] == 'Take Distro off Service'
    rows = pg.evaluate("() => [...document.querySelectorAll('#hw-gear-popover .hw-pop-svc-name')].map(e => e.textContent)")
    assert rows == ['SR · 200 A'], 'the open menu did not follow'
    undo(pg)
    assert read(pg)['serviceIds'] == {'d1': 's1', 'd2': 's1'}
    pg.evaluate("() => window.app._hwPopoverClose()")
    assert not errors, errors


def test_a_distro_of_another_system_is_refused_with_the_reason(page):
    pg, errors = page
    setup(pg, distros=[US('d1', 'SL'), US('d3', 'GEN', 100, '120/240')], services=[SVC()])
    n = len(pg.evaluate(HIST_JS))
    lit = drag_distro_onto_service(pg, 'd3', 's1', mid=lambda: pg.evaluate(
        "() => document.querySelector('[data-lrd-service=\"s1\"]').className"))
    assert 'hw-dock-svc-drop-no' in lit, lit
    why = ('GEN is 120/240V 1φ split-phase and HOUSE is 120/208V 3φ. '
           'A distro goes only on a service of the same system.')
    assert why in pg.evaluate(TOASTS_JS), pg.evaluate(TOASTS_JS)
    assert pg.evaluate(STATUS_JS) == why
    assert read(pg)['serviceIds']['d3'] is None
    # the gear's pick is refused the same way, and shows where it still is
    open_gear(pg, 'distro-d3')
    pick(pg, 'distro-service-d3', 's1')
    assert read(pg)['serviceIds']['d3'] is None
    assert pg.locator('#hw-gear-popover [data-lrd-field="distro-service-d3"]').input_value() == ''
    assert len(pg.evaluate(HIST_JS)) == n, 'a refusal took a history entry'
    pg.evaluate("() => window.app._hwPopoverClose()")
    # a distro on a service keeps its system, and the service keeps its own
    pg.evaluate("() => window.app.setDistroService('d1', 's1')")
    n = len(pg.evaluate(HIST_JS))
    pg.evaluate("() => window.app.updateDistro('d1', { system: '120/240' })")
    assert pg.evaluate(STATUS_JS) == ('SL is on HOUSE (120/208V 3φ). '
                                      'Take it off the service before changing its system.')
    pg.evaluate("() => window.app.updateService('s1', { system: '230/400' })")
    assert pg.evaluate(STATUS_JS) == 'HOUSE powers SL. Take them off before changing its system.'
    out = read(pg)
    assert out['stored'][0]['system'] == '120/208'
    assert pg.evaluate("() => window.app.getDistros()[0].system") == '120/208'
    assert len(pg.evaluate(HIST_JS)) == n
    assert not errors, errors


# ── the checks ────────────────────────────────────────────────────────────

def test_leg_totals_against_the_80_percent_rule_and_100_percent_rated(page):
    """Two distros of five full multis each on a 400 A service: 330 A a leg,
    the two distros' 165 A added, over 320 A (80% of 400 A); ticked 100%
    rated, under 400 A."""
    pg, errors = page
    setup(pg, distros=[dict(US('d1', 'SL'), serviceId='s1'), dict(US('d2', 'SR'), serviceId='s1')],
          services=[SVC(rating=400)],
          assign=[['WALL A', 0, 4, 'd1'], ['WALL A', 5, 9, 'd2']])
    out = read(pg)
    assert out['distros']['d1']['legs'] == [165, 165, 165], out['distros']
    assert out['distros']['d2']['legs'] == [165, 165, 165], out['distros']
    s = out['services']['s1']
    assert s['legs'] == [330, 330, 330] and s['limitA'] == 320, s
    assert s['over'] and s['legOver'] == [True, True, True], s
    assert s['use'] == '330.0/320 A' and s['useOver'], s
    assert s['lim'] == '· 80% of 400 A' and s['flag'] == 'OVER', s
    assert s['legBars'] == ['hw-dock-bar-over'] * 3, s
    assert s['legsLine'].startswith('LEGSX 330AY 330AZ 330A'), s['legsLine']
    assert {'text': 'HOUSE service: worst leg X 330.0 A / 320 A (80% of 400 A, continuous), OVER',
            'mild': False} in out['strip'], out['strip']
    # 100% rated, from the card's gear: the full rating, no OVER
    open_gear(pg, 'service-s1')
    pg.locator('#hw-gear-popover [data-lrd-field="service-main100-s1"]').check()
    pg.wait_for_timeout(300)
    assert pg.evaluate(HIST_JS)[-1] == 'Set Service 100% Rated'
    s = read(pg)['services']['s1']
    assert s['limitA'] == 400 and not s['over'], s
    assert s['use'] == '330.0/400 A' and not s['useOver'] and s['lim'] is None and s['flag'] is None, s
    assert not any('HOUSE service' in w['text'] and 'OVER' in w['text'] for w in read(pg)['strip'])
    undo(pg)
    assert read(pg)['services']['s1']['over'], 'undo did not take 100% rated off'
    pg.evaluate("() => window.app._hwPopoverClose()")
    # At 192 W a leg is 320 A: at the limit, not over it.
    setup(pg, watts=192, distros=[dict(US('d1', 'SL'), serviceId='s1'), dict(US('d2', 'SR'), serviceId='s1')],
          services=[SVC(rating=400)],
          assign=[['WALL A', 0, 4, 'd1'], ['WALL A', 5, 9, 'd2']])
    s = read(pg)['services']['s1']
    assert s['legs'] == [320, 320, 320] and not s['over'] and s['flag'] is None, s
    assert not errors, errors


def test_the_ratings_added_up_are_a_fact_not_a_warning(page):
    """The owner, 2026-11-03: "We should be skipping distros, but anything
    that is connected should be accounted for. But also a 400 and 200 amp
    distro connected to a 400 amp service that are only using 300 amps
    isn't a big deal since it's still under the 400 amp at 80% amount."
    SL 400, SR 200 and FOH 200 on a 600 A service, a circuit on each: the
    card reads "ratings 800 A on 600 A" as a plain fact - not amber - and
    the strip says nothing about it (it used to warn "HOUSE service (600
    A): its distros are rated 800 A together ..."). FOH with nothing on it
    is skipped: 600 A on 600 A, as the binder's Service sheet reads."""
    pg, errors = page
    d = [dict(US('d1', 'SL', 400), serviceId='s1'), dict(US('d2', 'SR', 200), serviceId='s1'),
         dict(US('d3', 'FOH', 200), serviceId='s1')]
    setup(pg, distros=d, services=[SVC(rating=600)],
          assign=[['WALL A', 0, 0, 'd1'], ['WALL A', 1, 1, 'd2'], ['WALL A', 2, 2, 'd3']])
    out = read(pg)
    s = out['services']['s1']
    assert s['ratingSum'] == 800, s
    assert s['chips'] == ['SL 400 A', 'SR 200 A', 'FOH 200 A'], s
    assert s['sum'] == 'ratings 800 A on 600 A' and not s['sumOver'], s
    assert not any('rated' in w['text'] for w in out['strip']), out['strip']
    assert not s['over'], 'the load is under the limit'
    # FOH with nothing connected: skipped, as the binder skips it
    setup(pg, distros=d, services=[SVC(rating=600)],
          assign=[['WALL A', 0, 0, 'd1'], ['WALL A', 1, 1, 'd2']])
    s = read(pg)['services']['s1']
    assert s['ratingSum'] == 600 and s['sum'] == 'ratings 600 A on 600 A', s
    assert not errors, errors


def test_imbalance_across_every_distro_on_the_service(page):
    """WALL B's four circuits alone on SR are X 33, Y 16.5, Z 16.5 A - 50%;
    beside SL's five full multis on the same service the legs read X 198,
    Y 181.5, Z 181.5 A - 5.9%."""
    pg, errors = page
    setup(pg, distros=[dict(US('d1', 'SL'), serviceId='s1'), dict(US('d2', 'SR', 200), serviceId='s1')],
          services=[SVC(rating=400)],
          assign=[['WALL A', 0, 4, 'd1'], ['WALL B', 0, 0, 'd2']])
    out = read(pg)
    assert out['distros']['d2']['legs'] == [33, 16.5, 16.5], out['distros']['d2']
    s = out['services']['s1']
    assert s['legs'] == [198, 181.5, 181.5], s
    assert abs(s['imbalance'] - 11 / 187 * 100) < 1e-3, s
    assert s['legsLine'].endswith('±6%'), s['legsLine']
    # SR alone on the service: its own imbalance
    pg.evaluate("() => window.app.setDistroService('d1', null)")
    s = read(pg)['services']['s1']
    assert s['legs'] == [33, 16.5, 16.5] and abs(s['imbalance'] - 50) < 1e-3, s
    tone = pg.evaluate("() => document.querySelector('[data-lrd-service=\"s1\"] .hw-dock-legs').className")
    assert 'hw-dock-legs-bad' in tone, tone
    assert not errors, errors


# ── one history entry per change ──────────────────────────────────────────

def test_every_service_change_is_one_undo_step(page):
    pg, errors = page
    setup(pg, distros=[US('d1', 'SL')], services=[SVC(rating=400)])
    steps = [
        ('Rename Service', lambda: (pg.locator('[data-lrd-field="service-name-s1"]').fill('MAIN'),
                                    pg.locator('[data-lrd-field="service-name-s1"]').dispatch_event('change')),
         lambda o: o['stored'][0]['name'] == 'MAIN'),
        ('Set Service Rating', lambda: (open_gear(pg, 'service-s1'),
                                        pg.locator('#hw-gear-popover [data-lrd-field="service-rating-s1"]').fill('800'),
                                        pg.locator('#hw-gear-popover [data-lrd-field="service-rating-s1"]').dispatch_event('change')),
         lambda o: o['stored'][0]['ratingA'] == 800),
        ('Set Service System', lambda: (open_gear(pg, 'service-s1'), pick(pg, 'service-system-s1', '230/400')),
         lambda o: o['stored'][0]['system'] == '230/400' and o['stored'][0]['voltage'] == 400),
        ('Set Service System', lambda: (open_gear(pg, 'service-s1'), pick(pg, 'service-system-s1', '120/208')),
         lambda o: o['stored'][0]['system'] == '120/208'),
        ('Set Service 100% Rated', lambda: (open_gear(pg, 'service-s1'),
                                            pg.locator('#hw-gear-popover [data-lrd-field="service-main100-s1"]').check()),
         lambda o: o['stored'][0].get('main100') is True),
        ('Put Distro on Service', lambda: drag_distro_onto_service(pg, 'd1', 's1'),
         lambda o: o['serviceIds']['d1'] == 's1'),
        ('Remove Service', lambda: (open_gear(pg, 'service-s1'),
                                    pg.locator('#hw-gear-popover [data-lrd-field="service-del-s1"]').click()),
         lambda o: o['stored'] == [] and o['serviceIds']['d1'] is None),
    ]
    for action, do, done in steps:
        before = read(pg)
        n = len(pg.evaluate(HIST_JS))
        do()
        pg.wait_for_timeout(350)
        pg.evaluate("() => window.app._hwPopoverClose()")
        after = read(pg)
        assert done(after), (action, after['stored'], after['serviceIds'])
        hist = pg.evaluate(HIST_JS)
        assert len(hist) == n + 1 and hist[-1] == action, (action, hist[n - 1:])
        undo(pg)
        back = read(pg)
        assert (back['stored'], back['serviceIds']) == (before['stored'], before['serviceIds']), action
        pg.evaluate("() => window.app.redo()")
        pg.wait_for_timeout(400)
        again = read(pg)
        assert (again['stored'], again['serviceIds']) == (after['stored'], after['serviceIds']), action
    # Undo of the removal brings the service back WITH its distro on it.
    undo(pg)
    out = read(pg)
    assert out['serviceIds']['d1'] == 's1' and out['services']['s1']['chips'] == ['SL 400 A · nothing connected'], out
    assert not errors, errors


# ── saved, loaded, and a show with none ───────────────────────────────────

SERVER_JS = "async () => await (await fetch('/api/project')).json()"


def _load_file(pg, path, name):
    with pg.expect_file_chooser() as chooser:
        pg.evaluate("window.app.loadProjectFromFile()")
    chooser.value.set_files(str(path))
    pg.wait_for_function("(n) => window.app.project && window.app.project.name === n"
                         " && document.getElementById('status-message').textContent === 'Project loaded'",
                         arg=name, timeout=10000)
    pg.wait_for_timeout(800)


def test_a_service_saves_and_loads_back(page, e2e_server, pw_browser, tmp_path):
    pg, errors = page
    setup(pg, distros=[dict(US('d1', 'SL'), serviceId='s1'), dict(US('d2', 'SR', 200), serviceId='s1'),
                       US('d3', 'GEN', 100, '120/240')],
          services=[SVC(rating=400, main100=True), SVC('s2', 'GENERATOR', 200, '120/240')],
          assign=[['WALL A', 0, 4, 'd1'], ['WALL A', 5, 9, 'd2']])
    pg.evaluate("() => window.app.setDistroService('d3', 's2')")
    pg.wait_for_timeout(500)
    before = read(pg)
    text = pg.evaluate("""() => {
        const app = window.app;
        const copy = JSON.parse(JSON.stringify(app.project));
        copy.name = 'SERVICE ROUND TRIP';
        return app.serializeProjectForFile(copy);
    }""")
    saved = json.loads(text)
    assert [s['id'] for s in saved['services']] == ['s1', 's2']
    assert {d['id']: d.get('serviceId') for d in saved['distros']} == {'d1': 's1', 'd2': 's1', 'd3': 's2'}
    # the server holds what the tray pushed
    server = pg.evaluate(SERVER_JS)
    assert server['services'] == before['stored'], server.get('services')
    assert {d['id']: d.get('serviceId') for d in server['distros']} == before['serviceIds']
    # a fresh show, then the file opened back
    setup(pg, distros=[US('d1', 'SL')])
    path = tmp_path / 'service_round_trip.json'
    path.write_text(text, encoding='utf-8')
    _load_file(pg, path, 'SERVICE ROUND TRIP')
    after = read(pg)
    assert after['stored'] == before['stored'], after['stored']
    assert after['serviceIds'] == before['serviceIds'], after['serviceIds']
    assert after['services'] == before['services'], (after['services'], before['services'])
    assert pg.evaluate(SERVER_JS)['services'] == before['stored']
    # and a reload reads the server's copy back onto the card
    context, pg2, errors2 = _open(pw_browser, e2e_server)
    try:
        pg2.locator('[data-mode="power"]').click()
        pg2.wait_for_timeout(600)
        again = read(pg2)
        assert again['stored'] == before['stored'], again['stored']
        assert again['services']['s1']['chips'] == ['SL 400 A', 'SR 200 A'], again['services']['s1']
        assert again['services']['s1']['use'] == '330.0/400 A', again['services']['s1']
        assert again['services']['s2']['chips'] == ['GEN 100 A · nothing connected'], again['services']['s2']
        assert not errors2, errors2
    finally:
        context.close()
    assert not errors, errors


def test_an_old_file_with_no_services_opens_and_saves_unchanged(page, tmp_path):
    pg, errors = page
    setup(pg, distros=[US('d1', 'SL'), US('d2', 'SR', 200)],
          assign=[['WALL A', 0, 4, 'd1'], ['WALL A', 5, 9, 'd2']])
    text = pg.evaluate("""() => {
        const copy = JSON.parse(JSON.stringify(window.app.project));
        copy.name = 'NO SERVICES';
        delete copy.services;
        return window.app.serializeProjectForFile(copy);
    }""")
    assert '"services"' not in text and 'serviceId' not in text
    before = read(pg)['distros']
    path = tmp_path / 'no_services.json'
    path.write_text(text, encoding='utf-8')
    _load_file(pg, path, 'NO SERVICES')
    out = read(pg)
    assert out['stored'] is None and out['services'] == {}, out['stored']
    assert out['distros'] == before, 'the distros read differently'
    assert pg.locator('#hardware-dock-body .hw-dock-services').count() == 0
    assert not any('service' in w['text'] for w in out['strip']), out['strip']
    open_gear(pg, 'distro-d1')
    assert pg.locator('#hw-gear-popover [data-lrd-field="distro-service-d1"]').count() == 0, \
        'a show with no services grew a Service row'
    pg.evaluate("() => window.app._hwPopoverClose()")
    # an edit pushes the distros - and still no services key, anywhere
    pg.evaluate("() => window.app.updateDistro('d1', { ratingA: 300 })")
    pg.wait_for_timeout(600)
    server = pg.evaluate(SERVER_JS)
    assert 'services' not in server, server.get('services')
    assert all('serviceId' not in d for d in server['distros'])
    again = pg.evaluate("() => window.app.serializeProjectForFile(JSON.parse(JSON.stringify(window.app.project)))")
    assert '"services"' not in again and 'serviceId' not in again
    assert not errors, errors


# ── the binder ────────────────────────────────────────────────────────────

BINDER_JS = """() => {
    const app = window.app;
    app._circuitTailCache = null;
    const caught = [];
    const orig = app._bKvLines;
    app._bKvLines = function (book, title, pairs) {
        // the distro's block is DISTRO (2026-10-22), the service's SERVICE
        if (title === 'Service' || title === 'Distro') caught.push(pairs.map(p => p.slice()));
        return orig.apply(this, arguments);
    };
    const opts = Object.assign(app.readBinderOptions(),
        { scope: { kind: 'show' }, hardware: true, pull: true, cover: false });
    let pages = [];
    let plan;
    try { plan = app.planBinder(opts); } finally { app._bKvLines = orig; }
    {
        for (let i = 0; i < plan.length; i++) {
            const r = app.renderBinderPage(opts, i);
            pages.push({ title: plan[i].title, kind: plan[i].kind,
                         texts: r.record.ops.filter(o => o.op === 'text' && String(o.text).trim())
                                  .map(o => String(o.text)) });
        }
    }
    return { pages, caught };
}"""


def test_the_binder_names_the_service_and_prints_a_service_sheet(page):
    pg, errors = page
    setup(pg, distros=[dict(US('d1', 'SL'), serviceId='s1'), dict(US('d2', 'SR', 200), serviceId='s1'),
                       US('d3', 'FOH', 200)],
          services=[SVC(rating=400)],
          assign=[['WALL A', 0, 4, 'd1'], ['WALL A', 5, 9, 'd2'], ['WALL B', 0, 0, 'd3']])
    pull_with = pg.evaluate("() => JSON.stringify(window.app.buildPullSheet())")
    out = pg.evaluate(BINDER_JS)
    blocks = out['caught']
    distro = [dict(p) for p in blocks if any(k == 'Circuits' for k, _ in p)]
    service = [dict(p) for p in blocks if any(k == 'Distros' for k, _ in p)]
    # Fed from on the distros on it ("HOUSE · 400 A · ...", read the way
    # FACTS reads it) - and every rating line by its service size first,
    # an old-style distro's too (2026-10-21)
    fed = [d.get('Powered from') for d in distro]
    assert fed == ['HOUSE · 400 A · 120/208V 3φ', 'HOUSE · 400 A · 120/208V 3φ', None], distro
    assert [d['Rating'] for d in distro] == ['400 A service · 120/208V 3φ', '200 A service · 120/208V 3φ',
                                             '200 A service · 120/208V 3φ']
    assert list(distro[0])[:2] == ['Rating', 'Powered from'], list(distro[0])
    # the Service block
    assert len(service) == 1, service
    s = service[0]
    assert s['Rating'] == '400 A · 120/208V 3φ', s
    assert s['Distros'] == 'ratings 600 A on 400 A', s
    assert s['Load'].startswith('X 330.0 · Y 330.0 · Z 330.0 A · 3φ '), s['Load']
    assert s['Load'].endswith('· limit 320 A (80% of 400 A) · OVER on X, Y, Z'), s['Load']
    assert s['Imbalance'] == '0.0%', s
    # its sheet, ahead of the distros', listing the distros and the totals
    kinds = [p['kind'] for p in out['pages']]
    sheet = next(p for p in out['pages'] if p['kind'] == 'service')
    assert sheet['title'] == 'Service - HOUSE', sheet['title']
    assert kinds.index('service') < kinds.index('distro'), kinds
    assert 'SERVICE · HOUSE' in sheet['texts'], sheet['texts']
    for want in ('2 DISTROS', 'DISTRO', 'RATING', 'X', 'Y', 'Z', 'SL', '400 A', 'SR', '200 A', 'total', '600 A',
                 '165.0', '330.0', 'Imbalance', '0.0%'):
        assert want in sheet['texts'], (want, sheet['texts'])
    assert 'FOH' not in sheet['texts'], 'a distro on no service printed on the Service sheet'
    # house power is not pulled: no pull row, no pull page, names it
    for p in out['pages']:
        if p['kind'] in ('pull', 'totals'):
            assert not any('HOUSE' in t for t in p['texts']), p['title']
    pg.evaluate("() => { delete window.app.project.services; window.app._persistDistros(); }")
    assert pg.evaluate("() => JSON.stringify(window.app.buildPullSheet())") == pull_with, \
        'the service changed the pull sheet'
    assert not errors, errors


def test_a_single_hot_service_adds_its_distros_amps(page):
    """No legs on 120V 1φ: the service reads its distros' amps added."""
    pg, errors = page
    setup(pg, distros=[dict(US('d1', 'A', 100, '120'), serviceId='s1'),
                       dict(US('d2', 'B', 100, '120'), serviceId='s1')],
          services=[SVC(rating=100, system='120')],
          assign=[['WALL B', 0, 0, 'd1']])
    out = read(pg)
    s = out['services']['s1']
    a = out['distros']['d1']['amps'] + out['distros']['d2']['amps']
    assert s['legs'] is None and abs(s['amps'] - a) < 1e-9 and abs(a - 66) < 1e-9, (s, out['distros'])
    assert s['use'] == '66.0/80 A' and s['legsLine'] is None, s
    assert not errors, errors


# ── the server's funnel ───────────────────────────────────────────────────

def test_the_server_keeps_the_service_model_whole():
    import app
    p = {'distros': [{'id': 'd1', 'system': '120/208', 'serviceId': 's1'},
                     {'id': 'd2', 'system': '120/240', 'serviceId': 's1'},
                     {'id': 'd3', 'system': '120/208', 'serviceId': 's9'},
                     {'id': 'd4', 'system': '120/208', 'serviceId': ['x']},
                     {'id': 'd5', 'system': '120/208'}],
         'services': [{'id': 's1', 'system': '120/208'}, {'id': 's1', 'system': '120'},
                      'junk', {'name': 'no id'}]}
    app._normalize_services(p)
    assert p['services'] == [{'id': 's1', 'system': '120/208'}]
    assert [d.get('serviceId') for d in p['distros']] == ['s1', None, None, None, None]
    assert 'serviceId' not in p['distros'][4]
    once = json.dumps(p, sort_keys=True)
    app._normalize_services(p)
    assert json.dumps(p, sort_keys=True) == once, 'not idempotent'
    old = {'distros': [{'id': 'd1', 'system': '120/208'}]}
    app._normalize_services(old)
    assert old == {'distros': [{'id': 'd1', 'system': '120/208'}]}, 'a show with none grew a key'
    stray = {'distros': [{'id': 'd1', 'system': '120/208', 'serviceId': 's1'}]}
    app._normalize_services(stray)
    assert 'serviceId' not in stray['distros'][0] and 'services' not in stray
