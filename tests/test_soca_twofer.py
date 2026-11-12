"""The Soca two-fer: one Socapex output split into two paired legs (owner
rulings, 2026-11-12).

  * "Can do 12 ports across 20A for two circuits each": PAIRED ONLY, both
    legs carry all six circuits of the output, so breaker N feeds circuit
    N of leg A and circuit N of leg B;
  * the two circuits on one breaker stay within 80% of it together - 16 A
    on the output's 20 A breaker - else OVER, the way a breaker past its
    limit reads;
  * right-click the output in the Power tray to add it; the output then
    shows its legs A and B as one pair, and each leg drags onto a screen
    like a multi; right-click to remove it, which unplugs both legs as
    Unplug multi does and forgets their lengths;
  * three lengths: the home run to the splitter, and each leg's own;
  * the pull sheet and the binder say the splitter once, its home run and
    each leg's Socapex and breakout;
  * Socapex outputs only; copies carry no leg; an old show is unchanged;
    every gesture is one undo step; a locked screen is never changed.

Every expected figure is worked from the formula in the comment beside it.

Run locally:
    python -m pytest tests/test_soca_twofer.py -v --browser chromium
"""

import json
import sys
import time
import urllib.request

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

QUIET = "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}"
MOD = 'Meta' if sys.platform == 'darwin' else 'Control'

# 208V circuits on a 120/208 distro whose breakers are 20 A and not 100%
# rated: each circuit, and each pair on a two-fer breaker, is held to
# 20 A x 80% = 16 A.
LIMIT_A = 20 * 0.8


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1800, 'height': 1000})
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
    for (const name of ['WALL A', 'WALL B']) {
        await fetch('/api/layer/add', {method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name, columns: 6, rows: 2,
                                  cabinet_width: 200, cabinet_height: 200})});
    }
    const p = await (await fetch('/api/project')).json();
    const app = window.app;
    // Every history entry counted: the stack itself stops growing at its
    // cap, so its length cannot count steps in a long module.
    if (!app.__counting) {
        const real = app.saveState;
        app.__saves = 0;
        app.saveState = function (...args) { app.__saves += 1; return real.apply(this, args); };
        app.__counting = true;
    }
    app.project = p;
    app.currentLayer = p.layers[0];
    app.selectedLayerIds = new Set([p.layers[0].id]);
    app.renderLayers();
    return p.layers.map(l => l.id);
}"""

# Both walls 6 x 2 cabinets of 100 W at 208V: a circuit carries 208 V x
# 20 A x 80% = 3,328 W, floor(3328 / 100) = 33 cabinets, so each wall is
# ONE circuit of 12 x 100 = 1,200 W = 1200 / 208 = 5.769 A. `watts`
# overrides WALL B's cabinet watts.
SETUP_JS = """(o) => {
    const app = window.app;
    const walls = app.project.layers.filter(l => (l.type || 'screen') === 'screen');
    walls.forEach((l, i) => {
        Object.assign(l, { powerVoltage: 208, powerAmperage: 20,
                           panelWatts: i === 1 && o.watts ? o.watts : 100,
                           powerOrganized: false, powerMaximize: false,
                           powerSocaDistro: {}, powerSocaNumber: {}, powerSocaPhasePos: {},
                           powerSocaLengths: {}, powerSocaSplits: [], powerSocaNames: {},
                           powerCircuitCables: {}, powerLabelOverrides: {},
                           powerBreakoutType: null, locked: false, powerFlowPattern: 'tl-h',
                           powerCustomPaths: {}, lastPowerFlowPattern: null });
        l.powerSources = [];
        app.normalizePowerBreakout(l);
    });
    app.project.distros = (o.distros || []).map(d => JSON.parse(JSON.stringify(d)));
    app._circuitTailCache = null;
    app._distroFaceMemo = null;
    app.getDistros();
    app.currentLayer = walls[0];
    app.selectedLayerIds = new Set([walls[0].id]);
    app.updateLayers(walls);
    app._persistDistros();
    // a history entry of its own, so an undo in a test stops here
    app.saveState('Test setup');
    app.renderHardwareDock();
    return walls.map(l => app.screenCircuits(l).length);
}"""

# A 120/208 distro with a face: two Socapex 208V outputs (1, 2), an L21-30
# (3), an Edison (4) and an L6-20 (5), every breaker 20 A.
FACE_DISTRO = {
    'id': 'd1', 'name': 'SL', 'ratingA': 400, 'system': '120/208', 'voltage': 208, 'phase': 3,
    'outputRows': [
        {'id': 'r1', 'connector': 'soca', 'count': 2, 'coupling': 'll', 'breakerA': 20},
        {'id': 'r2', 'connector': 'l2130', 'count': 1, 'coupling': 'll', 'breakerA': 20},
        {'id': 'r3', 'connector': 'edison', 'count': 1, 'coupling': 'ln', 'breakerA': 20},
        {'id': 'r4', 'connector': 'l620', 'count': 1, 'coupling': 'll', 'breakerA': 20},
    ],
}

# The same distro from before output rows: its boxes come and go with
# what is on them.
OLD_DISTRO = {'id': 'd1', 'name': 'SL', 'ratingA': 400, 'voltage': 208, 'phase': 3}


def setup(pg, **o):
    pg.wait_for_timeout(300)
    n = pg.evaluate(SETUP_JS, o)
    pg.wait_for_timeout(500)
    return n


def ev(pg, body, arg=None):
    return pg.evaluate(f"(arg) => {{ const app = window.app; "
                       f"const walls = app.project.layers.filter(l => (l.type || 'screen') === 'screen'); "
                       f"const A = walls[0], B = walls[1]; {body} }}", arg)


# Right-click the tray element `sel` the way a user does: the app's own
# context menu opens at it, and the two-fer item says what it offers.
# `click` presses it.
MENU_JS = """(o) => {
    const app = window.app;
    app.renderHardwareDock();
    const el = document.querySelector(o.sel);
    if (!el) return { missing: true };
    el.scrollIntoView({ block: 'center' });
    const r = el.getBoundingClientRect();
    app.showContextMenu(r.left + 3, r.top + Math.min(8, r.height / 2));
    const item = document.querySelector('#context-menu [data-action="hw-twofer"]');
    const out = { shown: item.style.display !== 'none', label: item.textContent,
                  disabled: item.classList.contains('menu-disabled'), title: item.title,
                  steps: app.__saves };
    if (o.click && out.shown) item.click();
    else app.hideContextMenu();
    out.after = app.__saves;
    return out;
}"""


def menu(pg, sel, click=False):
    out = pg.evaluate(MENU_JS, {'sel': sel, 'click': click})
    pg.wait_for_timeout(300)
    return out


# A tray box's own payload dropped on circuit `num` of wall `wall` (0 or
# 1): what the tray's drag hands _dockPerformDrop on release.
DROP_JS = """(o) => {
    const app = window.app;
    app.renderHardwareDock();
    const head = document.querySelector(o.sel);
    if (!head) return { missing: true };
    const payload = JSON.parse(head.dataset.hwdockPayload);
    const walls = app.project.layers.filter(l => (l.type || 'screen') === 'screen');
    const L = walls[o.wall];
    const num = app.screenCircuits(L)[o.ordinal - 1].num;
    const rec = [...app._powerNaming(L).socas.values()].find(r => r.circuits.includes(num));
    const before = app.__saves;
    app._dockPerformDrop(payload, { kind: 'run', layerId: L.id, socaIndex: rec.index, num });
    app._circuitTailCache = null;
    return { steps: app.__saves - before, payload,
             said: (document.getElementById('hw-dock-say') || {}).textContent || '' };
}"""


def drop(pg, sel, wall, ordinal=1):
    out = pg.evaluate(DROP_JS, {'sel': sel, 'wall': wall, 'ordinal': ordinal})
    pg.wait_for_timeout(300)
    return out


LABELS = """
    const lab = (L) => app.screenCircuits(L).map(c => app.getPowerCircuitLabel(L, c.num));
    return { a: lab(A), b: lab(B),
             aNum: { ...(A.powerSocaNumber || {}) }, bNum: { ...(B.powerSocaNumber || {}) },
             twofers: JSON.parse(JSON.stringify(app.getDistros()[0].twofers || null)) };
"""

TOASTS = "return (document.getElementById('app-toast-host') || {}).textContent || '';"


@pytest.fixture(scope="module")
def seeded(page):
    pg, errors = page
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(800)
    return pg, errors, ids


def _with_twofer(pg, watts=None):
    """WALL A on leg A and WALL B on leg B of SL's output 1, through the
    tray: right-click the output, Add Soca two-fer, drag each leg."""
    n = setup(pg, distros=[FACE_DISTRO], **({'watts': watts} if watts else {}))
    assert n == [1, 1], n
    m = menu(pg, '[data-hwdock="slot-d1-1"]', click=True)
    assert m['shown'] and m['label'] == 'Add Soca two-fer' and not m['disabled'], m
    a = drop(pg, '[data-hwdock="slot-d1-1"]', 0)
    b = drop(pg, '[data-hwdock="slot-d1-1001"]', 1)
    assert a['steps'] == 1 and b['steps'] == 1, (a, b)
    return a, b


# ── adding it ──────────────────────────────────────────────────────────────

def test_right_click_adds_a_twofer_as_one_pair_of_legs(seeded):
    pg, errors, _ = seeded
    setup(pg, distros=[FACE_DISTRO])
    m = menu(pg, '[data-hwdock="slot-d1-1"]', click=True)
    assert m['shown'] and m['label'] == 'Add Soca two-fer' and not m['disabled'], m
    assert m['after'] - m['steps'] == 1, 'adding the two-fer is one undo step'
    out = ev(pg, """
        app.renderHardwareDock();
        const strip = document.querySelector('[data-lrd-twofer="d1-1"]');
        const rows = strip ? [...strip.querySelectorAll(':scope > .lrd-sec-body > .hw-dock-loop-row')] : [];
        const head = strip && strip.querySelector(':scope > .hw-dock-head-row');
        return { strip: !!strip, rows: rows.map(r => r.querySelector('[data-hwdock]').dataset.hwdock),
                 far: rows.map(r => r.classList.contains('hw-dock-loop-far')),
                 head: head ? head.textContent : '',
                 tag: strip ? strip.querySelector('.hw-dock-looptag').textContent : '',
                 chips: rows.map(r => r.querySelectorAll('.hw-dock-tile').length),
                 lone: !!document.querySelector('[data-hwdock="slot-d1-2"]'),
                 stored: JSON.parse(JSON.stringify(app.getDistros()[0].twofers)) };""")
    assert out['strip'], 'the output shows as one two-fer strip'
    # leg A is the output's own number, leg B is 1000 + the output
    assert out['rows'] == ['slot-d1-1', 'slot-d1-1001'], out
    assert out['far'] == [False, True], 'leg B sits under the rule, like a backup box'
    assert out['tag'] == 'two-fer'
    assert 'SL1A + SL1B' in out['head'] and '0/12' in out['head'], out['head']
    # six circuits on each leg: twelve chips on the output's six breakers
    assert out['chips'] == [6, 6]
    assert out['lone'], 'output 2 is still a plain Socapex'
    assert out['stored'] == {'1': {'homeRun': ''}}, out['stored']
    assert not errors, errors


def test_legs_drag_onto_two_screens_and_name_their_circuits(seeded):
    pg, errors, ids = seeded
    a, b = _with_twofer(pg)
    # the empty legs drag as the output's Socapex row, each to its number
    assert a['payload']['number'] == 1 and b['payload']['number'] == 1001, (a, b)
    out = ev(pg, LABELS)
    # Naming pick: the output's name with the leg letter, then the
    # breaker: SL1A-1 on leg A, SL1B-1 on leg B.
    assert out['a'] == ['SL1A-1'] and out['b'] == ['SL1B-1'], out
    assert out['aNum'] == {'1': 1} and out['bNum'] == {'1': 1001}, out
    # both circuits are on breaker 1 of output 1: the same legs X-Y on
    # the 208V Socapex
    legs = ev(pg, """
        const d = app.getDistros()[0];
        const of = (L) => { const s = app.getSocaPlan(L)[0];
            return app.distroCircuitLegs(d, L, s, 0, app.socaCircuitPositions(L, s.soca, 1)); };
        return [of(A).legs, of(B).legs];""")
    assert legs[0] == legs[1] == ['X', 'Y'], legs
    assert not errors, errors


# ── the load on each breaker ──────────────────────────────────────────────

def test_a_pair_within_16_a_is_ok(seeded):
    pg, errors, _ = seeded
    _with_twofer(pg)
    out = ev(pg, """
        app.renderHardwareDock();
        const d = app.getDistros()[0];
        return { pairs: app.twoferPairs(d).map(r => ({ tail: r.tail, amps: r.amps, limit: r.limitA,
                                                       over: r.over, n: r.holders.length })),
                 checks: app.distroChecks(d).map(w => w.text),
                 overChips: document.querySelectorAll('[data-lrd-twofer-over]').length };""")
    # breaker 1: 1200 / 208 + 1200 / 208 = 11.538 A, within 16 A
    assert len(out['pairs']) == 1, out
    p = out['pairs'][0]
    assert p['tail'] == 1 and p['n'] == 2 and not p['over']
    assert p['amps'] == pytest.approx(2 * 1200 / 208)
    assert p['limit'] == pytest.approx(LIMIT_A)
    assert not [t for t in out['checks'] if 'two-fer' in t], out['checks']
    assert out['overChips'] == 0
    assert not errors, errors


def test_a_pair_over_16_a_flags_over(seeded):
    pg, errors, _ = seeded
    # WALL B at 250 W a cabinet: floor(3328 / 250) = 13 cabinets a
    # circuit, so its 12 are still one circuit of 3,000 W. Breaker 1 then
    # carries 1200 / 208 + 3000 / 208 = 4200 / 208 = 20.19 A, past 16 A,
    # though each circuit alone (5.77 A, 14.42 A) is within it.
    _with_twofer(pg, watts=250)
    out = ev(pg, """
        app.renderHardwareDock();
        const d = app.getDistros()[0];
        const say = app._dockPowerWarnings.map(w => w.text);
        const chips = [...document.querySelectorAll('.hw-dock-tile[data-lrd-twofer-over]')]
            .map(t => t.dataset.lrdTile);
        const head = document.querySelector('[data-lrd-twofer-over="d1-1"]');
        const distroFlag = document.querySelector('[data-lrd-twofer-over="d1"]')
            || [...document.querySelectorAll('[data-lrd-distro="d1"] .hw-dock-unit-flag')]
                .find(f => f.textContent === 'OVER');
        return { pair: app.twoferPairs(d)[0], say, chips, head: head && head.textContent,
                 distroFlag: distroFlag ? distroFlag.textContent : null,
                 each: [A, B].map(L => app.getSocaPlan(L)[0].legs[0].amps) };""")
    p = out['pair']
    assert p['amps'] == pytest.approx(4200 / 208) and p['over'], p
    assert out['each'][0] == pytest.approx(1200 / 208) and out['each'][1] == pytest.approx(3000 / 208)
    assert all(a < LIMIT_A for a in out['each']), 'each circuit alone is within its limit'
    line = [t for t in out['say'] if 'two-fer' in t]
    assert line == ["SL1A-1 + SL1B-1 share SL1's 20 A breaker 1 on the Soca two-fer: 20.2 A, "
                    "over the 80% continuous limit (16 A)."], out['say']
    # both chips on breaker 1 wear OVER, as does the two-fer and its distro
    assert sorted(out['chips']) == ['ptail-d1-1-1', 'ptail-d1-1001-1'], out['chips']
    assert out['head'] == 'OVER' and out['distroFlag'] == 'OVER', out
    assert not errors, errors


# ── the three lengths ──────────────────────────────────────────────────────

def test_three_lengths_are_stored(seeded):
    pg, errors, _ = seeded
    _with_twofer(pg)
    out = ev(pg, """
        app.renderHardwareDock();
        const before = app.__saves;
        const field = document.querySelector('[data-lrd-field="twofer-home-run-d1-1"]');
        field.value = '100'; field.dispatchEvent(new Event('change'));
        const setA = document.querySelector(`[data-lrd-field="power-soca-length-${A.id}-1"]`);
        setA.value = '25'; setA.dispatchEvent(new Event('change'));
        app.renderHardwareDock();
        const setB = document.querySelector(`[data-lrd-field="power-soca-length-${B.id}-1"]`);
        setB.value = '50'; setB.dispatchEvent(new Event('change'));
        return { steps: app.__saves - before,
                 home: app.getDistros()[0].twofers['1'].homeRun,
                 a: A.powerSocaLengths['1'], b: B.powerSocaLengths['1'] };""")
    pg.wait_for_timeout(600)
    # one entry each: the home run, leg A's length, leg B's length
    assert out == {'steps': 3, 'home': '100', 'a': '25', 'b': '50'}, out
    server = ev(pg, """return fetch('/api/project').then(r => r.json()).then(p => ({
        home: p.distros[0].twofers['1'].homeRun,
        legs: p.layers.filter(l => (l.type || 'screen') === 'screen').map(l => l.powerSocaLengths['1']) }));""")
    assert server == {'home': '100', 'legs': ['25', '50']}, server
    assert not errors, errors


# ── the paperwork ──────────────────────────────────────────────────────────

def _lengths(pg):
    ev(pg, """
        app.getDistros()[0].twofers['1'].homeRun = '100';
        A.powerSocaLengths = { 1: '25' }; B.powerSocaLengths = { 1: '50' };
        app._circuitTailCache = null;""")


def test_the_pull_sheet_says_the_splitter_its_home_run_and_each_leg(seeded):
    pg, errors, _ = seeded
    _with_twofer(pg)
    _lengths(pg)
    rows = ev(pg, """
        const list = app.buildPullList();
        return list.positions.flatMap(p => p.rows)
            .filter(r => /Multi|two-fer|Breakout/.test(r.type))
            .map(r => [r.type, r.length, r.qty, r.label, r.notes]).sort();""")
    # one Soca two-fer per splitter, its home run under its name; each leg
    # its own Multi length and breakout under the leg's name
    # (each wall is a position of its own; the splitter is pulled with the
    # first leg met)
    assert rows == sorted([
        ['Multi', "100'", 1, 'SL1', ''],
        ['Multi', "25'", 1, 'SL1A', ''],
        ['Multi', "50'", 1, 'SL1B', ''],
        ['Soca two-fer', 'EA', 1, 'SL1', ''],
        ['TRUE1 Breakout', 'EA', 1, 'SL1A', ''],
        ['TRUE1 Breakout', 'EA', 1, 'SL1B', ''],
    ]), rows
    assert not errors, errors


def test_cable_stock_counts_the_legs_and_the_home_run(seeded):
    pg, errors, _ = seeded
    _with_twofer(pg)
    # 125' typed on the home run with 25 / 50 / 100 multi stock is
    # 100' + 25' (least extra, then fewest pieces); the legs' 25' and 50'
    # are a piece each.
    out = ev(pg, """
        app.project.cableStock = { perKind: false, ft: { all: [25, 50, 100] }, m: { all: [10, 20, 30] } };
        app.getDistros()[0].twofers['1'].homeRun = '125';
        A.powerSocaLengths = { 1: '25' }; B.powerSocaLengths = { 1: '50' };
        app._circuitTailCache = null;
        const list = app.buildPullList();
        const multis = list.totals.filter(r => r.type === 'Multi').map(r => [r.length, r.qty]);
        delete app.project.cableStock;
        return multis.sort();""")
    # Multi 25' x 2 (leg A and the home run's 25'), 50' x 1 (leg B),
    # 100' x 1 (the home run's 100')
    assert out == sorted([["25'", 2], ["50'", 1], ["100'", 1]]), out
    assert not errors, errors


def test_the_binder_prints_the_splitter_and_each_leg(seeded):
    pg, errors, _ = seeded
    _with_twofer(pg)
    _lengths(pg)
    out = ev(pg, """
        const book = app._binderBook(app.readBinderOptions(), { dry: true });
        const scr = book.list.byScreen[String(B.id)];
        const band = app._bBoxBand(book, B, scr.boxes[0]);
        // the distro sheet's table rows, as _bDistroGroup hands them over
        let rows = null;
        const real = app._bDistroBlocks;
        app._bDistroBlocks = function (bk, d, load, boxes, ...rest) {
            rows = boxes.map(b => b.cells);
            return real.call(this, bk, d, load, boxes, ...rest);
        };
        try { app._bDistroGroup(book, app.getDistros()[0]); } finally { app._bDistroBlocks = real; }
        return { band, rows };""")
    assert out['band'] == ("SL1B · Socapex 208V TRUE1 breakout · 50' · 1 circuit · "
                           "leg B of Soca two-fer SL1 · 100' home run"), out['band']
    # the distro sheet: the splitter's own line, then its legs - name,
    # type, home run, screens, circuits, amps (1200 / 208 = 5.8 A each)
    assert out['rows'] == [
        ['SL1', 'Soca two-fer', "100'", '', '', ''],
        ['SL1A', 'Socapex 208V', "25'", 'WALL A', '1', '5.8'],
        ['SL1B', 'Socapex 208V', "50'", 'WALL B', '1', '5.8'],
    ], out['rows']
    assert not errors, errors


# ── removing it ────────────────────────────────────────────────────────────

def test_removing_it_clears_the_legs_and_their_lengths_in_one_step(seeded):
    pg, errors, _ = seeded
    _with_twofer(pg)
    _lengths(pg)
    m = menu(pg, '[data-lrd-twofer="d1-1"] > .hw-dock-head-row', click=True)
    assert m['shown'] and m['label'] == 'Remove Soca two-fer' and not m['disabled'], m
    assert m['after'] - m['steps'] == 1, 'removing it is one undo step'
    out = ev(pg, """
        app.renderHardwareDock();
        return { d: app.getSocaPlan(A).map(s => s.distroId).concat(app.getSocaPlan(B).map(s => s.distroId)),
                 lengths: [A.powerSocaLengths, B.powerSocaLengths], nums: [A.powerSocaNumber, B.powerSocaNumber],
                 twofers: JSON.parse(JSON.stringify(app.getDistros()[0].twofers)),
                 strip: !!document.querySelector('[data-lrd-twofer]'),
                 lone: !!document.querySelector('[data-hwdock="slot-d1-1"]'),
                 rows: app.buildPullList().positions.flatMap(p => p.rows).map(r => r.type) };""")
    assert out['d'] == [None, None], 'both legs are unplugged'
    # the legs' lengths go with the feed; the stores stay, emptied
    assert out['lengths'] == [{}, {}] and out['nums'] == [{}, {}], out
    # an explicit empty map, never a deleted key
    assert out['twofers'] == {}, out['twofers']
    assert not out['strip'] and out['lone'], 'output 1 is a plain Socapex again'
    assert 'Soca two-fer' not in out['rows'] and 'Multi' not in out['rows'], out['rows']
    # the server holds the same, sent as explicit empty values
    pg.wait_for_timeout(600)
    server = ev(pg, """return fetch('/api/project').then(r => r.json()).then(p => ({
        twofers: p.distros[0].twofers,
        legs: p.layers.filter(l => (l.type || 'screen') === 'screen')
            .map(l => [l.powerSocaDistro, l.powerSocaLengths]) }));""")
    assert server == {'twofers': {}, 'legs': [[{}, {}], [{}, {}]]}, server
    assert not errors, errors


def test_one_undo_brings_the_twofer_and_its_legs_back(seeded):
    pg, errors, _ = seeded
    _with_twofer(pg)
    _lengths(pg)
    ev(pg, "app.saveState('Set lengths');")
    menu(pg, '[data-lrd-twofer="d1-1"] > .hw-dock-head-row', click=True)
    pg.evaluate("() => window.app.undo()")
    pg.wait_for_timeout(1200)
    out = ev(pg, LABELS)
    assert out['a'] == ['SL1A-1'] and out['b'] == ['SL1B-1'], out
    assert out['twofers'] == {'1': {'homeRun': '100'}}, out
    lens = ev(pg, "return [A.powerSocaLengths, B.powerSocaLengths];")
    assert lens == [{'1': '25'}, {'1': '50'}], lens
    # and undoing the add itself is one step back to a plain output
    setup(pg, distros=[FACE_DISTRO])
    menu(pg, '[data-hwdock="slot-d1-1"]', click=True)
    pg.evaluate("() => window.app.undo()")
    pg.wait_for_timeout(1200)
    after = ev(pg, "return JSON.parse(JSON.stringify(app.getDistros()[0].twofers || null));")
    assert not after, after
    assert not errors, errors


# ── the rules every power gesture keeps ────────────────────────────────────

def test_copies_carry_no_legs(seeded):
    pg, errors, _ = seeded
    _with_twofer(pg)
    before = ev(pg, """
        app.currentLayer = B;
        app.selectedLayerIds = new Set([B.id]);
        if (document.activeElement) document.activeElement.blur();
        return app.project.layers.map(l => l.id);""")
    pg.keyboard.press(f'{MOD}+j')
    pg.wait_for_timeout(1500)
    out = ev(pg, """
        const copy = app.project.layers.find(l => !arg.includes(l.id));
        if (!copy) return { missing: true };
        const legB = app._distroMultiNumbers('d1').get(1001) || [];
        return { feeds: [copy.powerSocaDistro, copy.powerSocaNumber, copy.powerSocaLengths],
                 onLegB: legB.map(m => m.layerName), plan: app.getSocaPlan(copy).map(s => s.distroId) };""",
             before)
    assert not out.get('missing'), out
    assert all(not f for f in out['feeds']), f'the copy carries a leg: {out}'
    assert out['onLegB'] == ['WALL B'], out
    assert set(out['plan']) == {None}
    # tidy up: the copy goes
    ev(pg, """
        const copy = app.project.layers.find(l => !arg.includes(l.id));
        return fetch(`/api/layer/${copy.id}`, { method: 'DELETE' }).then(() => {
            app.project.layers = app.project.layers.filter(l => l !== copy); });""", before)
    pg.wait_for_timeout(500)
    assert not errors, errors


def test_a_locked_screen_says_why_and_stays(seeded):
    pg, errors, _ = seeded
    _with_twofer(pg)
    ev(pg, "A.locked = true; app.updateLayers([A]);")
    pg.wait_for_timeout(300)
    m = menu(pg, '[data-lrd-twofer="d1-1"] > .hw-dock-head-row', click=True)
    out = ev(pg, LABELS)
    toast = ev(pg, TOASTS)
    assert m['after'] == m['steps'], 'nothing is recorded'
    assert out['a'] == ['SL1A-1'] and out['twofers'] == {'1': {'homeRun': ''}}, out
    assert 'WALL A is locked. Unlock it to change it.' in toast, toast
    # a leg dragged onto the locked screen is refused the same way
    ev(pg, "(document.getElementById('app-toast-host') || { innerHTML: '' }).innerHTML = '';")
    setup(pg, distros=[FACE_DISTRO])
    menu(pg, '[data-hwdock="slot-d1-1"]', click=True)
    ev(pg, "A.locked = true; app.updateLayers([A]);")
    pg.wait_for_timeout(300)
    d = drop(pg, '[data-hwdock="slot-d1-1001"]', 0)
    assert d['steps'] == 0, d
    assert ev(pg, "return app.getSocaPlan(A).map(s => s.distroId);") == [None]
    assert 'WALL A is locked' in ev(pg, TOASTS)
    # and an output a locked screen is on keeps its name: no two-fer added
    ev(pg, """A.locked = false; app.updateLayers([A]);""")
    pg.wait_for_timeout(300)
    setup(pg, distros=[FACE_DISTRO])
    drop(pg, '[data-hwdock="slot-d1-2"]', 0)
    ev(pg, "A.locked = true; app.updateLayers([A]);")
    pg.wait_for_timeout(300)
    m2 = menu(pg, '[data-hwdock="slot-d1-2"]', click=True)
    assert m2['after'] == m2['steps']
    assert ev(pg, LABELS)['a'] == ['SL2-1']
    ev(pg, "A.locked = false; app.updateLayers([A]);")
    pg.wait_for_timeout(300)
    assert not errors, errors


def test_not_offered_on_outputs_that_are_not_socapex(seeded):
    pg, errors, _ = seeded
    setup(pg, distros=[FACE_DISTRO])
    # the L21-30 box (3), the Edison (4) and L6-20 (5) outputs' chips,
    # and the direct row's own header
    for sel in ['[data-hwdock="slot-d1-3"]', '[data-hwdock="tail-d1-4-1"]',
                '[data-hwdock="tail-d1-5-1"]']:
        m = menu(pg, sel)
        assert not m.get('missing'), sel
        assert not m['shown'], f'{sel} offers {m["label"]}'
    # asked directly, it refuses and says why, and nothing is stored
    out = ev(pg, """
        const r = [3, 4, 5].map(n => app.addTwofer('d1', n));
        return { r, twofers: app.getDistros()[0].twofers || null,
                 why: app.twoferEligible(app.getDistros()[0], 3).why };""")
    assert out['r'] == [False, False, False] and not out['twofers'], out
    assert out['why'] == 'A two-fer splits a Socapex output, and SL3 is an L21-30.', out['why']
    assert not errors, errors


def test_a_120v_socapex_output_takes_one_too(seeded):
    pg, errors, _ = seeded
    soca120 = json.loads(json.dumps(FACE_DISTRO))
    soca120['outputRows'][0]['coupling'] = 'ln'
    setup(pg, distros=[soca120])
    m = menu(pg, '[data-hwdock="slot-d1-1"]', click=True)
    assert m['shown'] and not m['disabled'], m
    out = ev(pg, """
        const d = app.getDistros()[0];
        return { tw: !!app.twoferOf(d, 1001), type: app.distroBoxType(d, 1001).type.name };""")
    assert out == {'tw': True, 'type': 'Socapex 120V'}, out
    assert not errors, errors


def test_an_old_distro_without_output_rows(seeded):
    """A distro saved before output rows: its Socapex box takes a two-fer
    too. No output carries a breaker there, so the pair is held to what its
    screens pack a circuit to: 208 V screens at 20 A, 80%, 16 A."""
    pg, errors, _ = seeded
    setup(pg, distros=[OLD_DISTRO], watts=250)
    drop(pg, '[data-hwdock="slot-d1-1"]', 0)
    m = menu(pg, '[data-hwdock="slot-d1-1"]', click=True)
    assert m['shown'] and m['label'] == 'Add Soca two-fer', m
    drop(pg, '[data-hwdock="slot-d1-1001"]', 1)
    out = ev(pg, """
        app.renderHardwareDock();
        const d = app.getDistros()[0];
        return { labels: [app.getPowerCircuitLabel(A, 1), app.getPowerCircuitLabel(B, 1)],
                 pair: app.twoferPairs(d).map(r => ({ amps: r.amps, limit: r.limitA, over: r.over })),
                 spare: !!document.querySelector('[data-hwdock="slot-d1-2"]'),
                 types: d.boxTypes };""")
    assert out['labels'] == ['SL1A-1', 'SL1B-1'], out
    # 1200 / 208 + 3000 / 208 = 20.19 A on a 16 A pair
    assert out['pair'] == [{'amps': pytest.approx(4200 / 208), 'limit': pytest.approx(LIMIT_A), 'over': True}]
    assert out['spare'], 'the next spare box still shows'
    assert out['types'] == {'1': 'soca208'}, out['types']
    assert not errors, errors


def test_an_old_show_opens_unchanged(seeded):
    """A show from before the two-fer: no key is added to its distro, its
    names and its paperwork read as they always did, and the tray shows
    no pair."""
    pg, errors, _ = seeded
    setup(pg, distros=[FACE_DISTRO])
    drop(pg, '[data-hwdock="slot-d1-1"]', 0)
    pg.wait_for_timeout(500)
    pg.reload(wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    pg.wait_for_timeout(1500)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(400)
    out = ev(pg, """
        app.renderHardwareDock();
        const d = app.getDistros()[0];
        return { keys: Object.keys(d).sort(), label: app.getPowerCircuitLabel(A, 1),
                 strip: !!document.querySelector('[data-lrd-twofer]'),
                 rows: app.buildPullList().positions.flatMap(p => p.rows).map(r => r.type) };""")
    assert 'twofers' not in out['keys'], out['keys']
    assert out['label'] == 'SL1-1'
    assert not out['strip']
    assert 'Soca two-fer' not in out['rows']
    assert not errors, errors
