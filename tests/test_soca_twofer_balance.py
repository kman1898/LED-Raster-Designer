"""Balance and the Soca two-fer (owner ruling, 2026-11-14).

Circuit N of a two-fer's leg A and circuit N of its leg B share breaker N
of the output, and the two together stay within 80% of it (16 A on a 20 A
US breaker). Balance moves partly-filled multis to other sockets of their
fan, so it treats the pair as one output with shared breakers:

  * whatever it moves, every shared breaker stays within its limit, and it
    never makes an OVER that was not there;
  * a pair that already reads OVER is never made worse, and is fixed when
    an arrangement of the multis can fix it;
  * leg A and leg B on the same breaker is no double patch: the pair is
    legal while it is within its limit;
  * a distro without a two-fer balances exactly as before;
  * a locked screen is never changed.

Every show is built here; no client files. Every figure is worked from the
formula beside it.

Run locally:
    python -m pytest tests/test_soca_twofer_balance.py -v --browser chromium
"""

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

QUIET = "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}"

# 208V circuits on a 120/208 distro whose breakers are 20 A and not 100%
# rated: each pair on a two-fer breaker is held to 20 A x 80% = 16 A.
LIMIT_A = 20 * 0.8

# A circuit packs 208 V x 20 A x 80% = 3,328 W.
#   150 W cabinets: floor(3328 / 150) = 22 a circuit, so a 6 x 4 wall of 24
#   is two circuits, 22 x 150 = 3,300 W = 15.87 A and 2 x 150 = 300 W =
#   1.44 A.
#   250 W cabinets: floor(3328 / 250) = 13 a circuit, so a 6 x 4 wall is
#   13 x 250 = 3,250 W = 15.63 A and 11 x 250 = 2,750 W = 13.22 A.
HEAVY = 3300 / 208
LIGHT = 300 / 208


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


# A 120/208 distro with three Socapex 208V outputs, every breaker 20 A.
FACE_DISTRO = {
    'id': 'd1', 'name': 'SL', 'ratingA': 400, 'system': '120/208', 'voltage': 208, 'phase': 3,
    'outputRows': [{'id': 'r1', 'connector': 'soca', 'count': 3, 'coupling': 'll', 'breakerA': 20}],
}

# The same distro from before output rows: no output carries a breaker, so
# a pair is held to what its screens pack a circuit to (16 A here too).
OLD_DISTRO = {'id': 'd1', 'name': 'SL', 'ratingA': 400, 'voltage': 208, 'phase': 3}

# The walls, every one a 6-column screen of 200 mm cabinets: [name, rows,
# watts a cabinet].
WALLS = [['WALL A', 4, 150], ['WALL B', 4, 150], ['WALL C', 4, 250]]

SEED_JS = """async (walls) => {
    const proj = await (await fetch('/api/project')).json();
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments;
    await fetch('/api/project', {method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(proj)});
    for (const [name, rows] of walls) {
        await fetch('/api/layer/add', {method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name, columns: 6, rows, cabinet_width: 200, cabinet_height: 200})});
    }
    const p = await (await fetch('/api/project')).json();
    window.app.project = p;
    return p.layers.map(l => l.id);
}"""

# o.distro: the distro; o.twofer: make output 1 a two-fer; o.feeds: per
# wall [box number, stored sockets or null] (box 1001 is output 1's leg B);
# o.watts: per wall; o.locked: wall indexes locked. Returns each wall's
# circuit amps.
SETUP_JS = """(o) => {
    const app = window.app;
    const walls = app.project.layers.filter(l => (l.type || 'screen') === 'screen');
    walls.forEach((l, i) => {
        Object.assign(l, { powerVoltage: 208, powerAmperage: 20, panelWatts: o.watts[i],
                           powerOrganized: false, powerMaximize: false,
                           powerSocaDistro: {}, powerSocaNumber: {}, powerSocaPhasePos: {},
                           powerSocaPhaseOffset: {},
                           powerSocaLengths: {}, powerSocaSplits: [], powerSocaNames: {},
                           powerCircuitCables: {}, powerLabelOverrides: {},
                           powerBreakoutType: null, locked: false, powerFlowPattern: 'tl-h',
                           powerCustomPaths: {}, lastPowerFlowPattern: null, visible: true });
        l.powerSources = [];
        app.normalizePowerBreakout(l);
    });
    app.project.distros = [JSON.parse(JSON.stringify(o.distro))];
    if (o.twofer) app.project.distros[0].twofers = { 1: { homeRun: '' } };
    app._circuitTailCache = null;
    app._distroFaceMemo = null;
    app.getDistros();
    walls.forEach((l, i) => {
        const [number, pos] = o.feeds[i] || [null, null];
        if (number === null) return;
        l.powerSocaDistro = { 1: 'd1' };
        l.powerSocaNumber = { 1: number };
        // where an earlier Balance left the multi
        if (pos) l.powerSocaPhasePos = { 1: pos };
    });
    (o.locked || []).forEach(i => { walls[i].locked = true; });
    app._circuitTailCache = null;
    app.currentLayer = walls[0];
    app.selectedLayerIds = new Set([walls[0].id]);
    app.updateLayers(walls);
    app._persistDistros();
    app.saveState('Test setup');
    return walls.map(l => app.getSocaPlan(l).flatMap(s => s.legs.map(g => g.amps)));
}"""

# The distro as it reads now: each wall's sockets, the two-fer breakers
# (output, breaker, amps, over), the imbalance and the busiest leg.
STATE_JS = """() => {
    const app = window.app;
    app._circuitTailCache = null;
    const walls = app.project.layers.filter(l => (l.type || 'screen') === 'screen');
    const d = app.getDistros()[0];
    const L = app.getDistroLoads().find(b => b.id === 'd1');
    return {
        sockets: walls.map(l => app.getSocaPlan(l).flatMap(s => s.legs.map(g => g.leg))),
        labels: walls.map(l => app.getSocaPlan(l).flatMap(s => s.legs.map(g => g.label))),
        pairs: app.twoferPairs(d).map(r => ({ output: r.output, tail: r.tail, amps: r.amps,
                                              limit: r.limitA, over: r.over })),
        imb: L.imbalancePct, busiest: L.legs.worstAmps,
        stores: walls.map(l => JSON.parse(JSON.stringify(l.powerSocaPhasePos || {}))),
        numbers: walls.map(l => JSON.parse(JSON.stringify(l.powerSocaNumber || {}))),
    };
}"""

# Balance's own dialog for the distro, then Apply in it.
DIALOG_JS = """(apply) => {
    const app = window.app;
    app.showBalanceDialog('d1');
    const el = document.getElementById('balance-modal');
    const out = { text: el.textContent.replace(/\\s+/g, ' '),
                  apply: !!el.querySelector('.balance-apply') };
    if (apply && out.apply) el.querySelector('.balance-apply').click();
    else el.remove();
    return out;
}"""

SUGGEST_JS = """() => {
    const r = window.app.suggestPhaseBalance('d1');
    return { before: r.before, after: r.after, beforeBusiest: r.beforeBusiest,
             afterBusiest: r.afterBusiest, searched: r.searched, total: r.total,
             moves: r.moves.map(m => ({ name: m.name, layerName: m.layerName,
                                        from: m.from, to: m.to })) };
}"""


@pytest.fixture(scope="module")
def seeded(page):
    pg, errors = page
    pg.evaluate(SEED_JS, WALLS)
    pg.wait_for_timeout(800)
    return pg, errors


def setup(pg, feeds, watts=(150, 150, 250), distro=FACE_DISTRO, twofer=True, locked=()):
    pg.wait_for_timeout(200)
    amps = pg.evaluate(SETUP_JS, {'distro': distro, 'twofer': twofer, 'feeds': feeds,
                                  'watts': list(watts), 'locked': list(locked)})
    pg.wait_for_timeout(300)
    return amps


def state(pg):
    return pg.evaluate(STATE_JS)


def excess(pairs):
    """Amps past the limit on each two-fer breaker, by (output, breaker)."""
    return {(p['output'], p['tail']): max(0.0, p['amps'] - p['limit']) for p in pairs}


def assert_within(pairs):
    for p in pairs:
        assert p['amps'] <= p['limit'] + 1e-9 and not p['over'], pairs


# ── a pair within its limit stays within it ────────────────────────────────

# WALL A on leg A, sockets 1 and 3: 15.87 A on breaker 1, 1.44 A on 3.
# WALL B on leg B, sockets 2 and 3: 15.87 A on breaker 2, 1.44 A on 3.
# Breaker 3 carries 1.44 + 1.44 = 2.88 A, the others 15.87 A: within 16 A.
# WALL C fills sockets 1 and 2 of output 2 with 15.63 A and 13.22 A, all of
# it on legs X, Y and Z unevenly, so Balance has something to fix.
WITHIN = [[1, [1, 3]], [1001, [2, 3]], [2, None]]


def test_balance_keeps_every_shared_breaker_within_its_limit(seeded):
    pg, errors = seeded
    amps = setup(pg, WITHIN)
    assert amps[0] == pytest.approx([HEAVY, LIGHT]) and amps[1] == pytest.approx([HEAVY, LIGHT]), amps
    before = state(pg)
    assert before['sockets'][:2] == [[1, 3], [2, 3]], before
    assert_within(before['pairs'])
    s = pg.evaluate(SUGGEST_JS)
    assert s['moves'], 'Balance has a better arrangement to offer'
    # The two heavy circuits must never meet: 15.87 + 15.87 = 31.7 A, and
    # one heavy with one light is 15.87 + 1.44 = 17.31 A, both past 16 A.
    # So a heavy circuit on a leg only ever shares its breaker with nothing.
    dlg = pg.evaluate(DIALOG_JS, True)
    assert dlg['apply'], dlg
    assert 'Soca two-fer SL1 stays within its breakers.' in dlg['text'], dlg['text']
    pg.wait_for_timeout(300)
    after = state(pg)
    assert_within(after['pairs'])
    heavy = {(o, t) for o, t in [(1, after['sockets'][0][0]), (1, after['sockets'][1][0])]}
    light = {(1, after['sockets'][0][1]), (1, after['sockets'][1][1])}
    assert len(heavy) == 2 and not heavy & light, after['sockets']
    # and the balance still improves the legs, the busiest no heavier
    assert after['imb'] < before['imb'] - 1, (before['imb'], after['imb'])
    assert after['busiest'] <= before['busiest'] + 1e-6
    assert after['imb'] == pytest.approx(s['after'])
    # the multi numbers never move under Balance
    assert after['numbers'] == before['numbers'], after['numbers']
    assert not errors, errors


def test_leg_a_and_leg_b_may_share_a_breaker_within_its_limit(seeded):
    """Two light circuits on one breaker is the two-fer working as built,
    never a double patch: Balance may put them together."""
    pg, errors = seeded
    # WALL A locked on leg A, sockets 1 and 3 (15.87 A, 1.44 A); WALL B on
    # leg B, sockets 2 and 4: no breaker shared yet.
    setup(pg, [[1, [1, 3]], [1001, [2, 4]], [2, None]], locked=[0])
    out = pg.evaluate("""() => {
        const app = window.app;
        const res = app._balanceSolve('d1');
        const j = res.targets.findIndex(t => t.name === 'SL1B');
        return { names: res.targets.map(t => t.name),
                 b: res.options[j].map(o => o.tails.join(',')) };
    }""")
    assert 'SL1A' not in out['names'], 'the locked leg is held where it is'
    # Leg B's light circuit on breaker 3 beside leg A's light one is
    # 1.44 + 1.44 = 2.88 A, within 16 A: offered.
    assert '2,3' in out['b'], out
    # Never offered: leg B's heavy circuit on breaker 1 (15.87 + 15.87 =
    # 31.73 A) or on breaker 3 (15.87 + 1.44 = 17.31 A), nor its light one
    # on breaker 1 (1.44 + 15.87 = 17.31 A). Its heavy circuit takes the
    # lower socket, wall order.
    for o in out['b']:
        heavy, light = (int(x) for x in o.split(','))
        assert heavy not in (1, 3) and light != 1, out
    pg.evaluate("() => { const w = window.app.project.layers.filter(l => (l.type || 'screen') === 'screen'); "
                "w[0].locked = false; window.app.updateLayers(w); }")
    pg.wait_for_timeout(300)
    assert not errors, errors


# ── a pair already OVER ────────────────────────────────────────────────────

def test_balance_fixes_a_pair_already_over(seeded):
    pg, errors = seeded
    # Both legs on sockets 1 and 2: breaker 1 carries 15.87 + 15.87 =
    # 31.73 A, OVER; breaker 2, 1.44 + 1.44 = 2.88 A.
    setup(pg, [[1, None], [1001, None], [2, None]])
    before = state(pg)
    ex = excess(before['pairs'])
    assert ex[(1, 1)] == pytest.approx(2 * HEAVY - LIMIT_A), before['pairs']
    dlg = pg.evaluate(DIALOG_JS, True)
    assert dlg['apply'], dlg
    assert 'Soca two-fer SL1 is back within its breakers.' in dlg['text'], dlg['text']
    pg.wait_for_timeout(300)
    after = state(pg)
    assert_within(after['pairs'])
    assert after['busiest'] <= before['busiest'] + 1e-6
    assert not errors, errors


# WALL A full on leg A: six circuits of 15.87 A (6 columns x 22 rows =
# 132 cabinets at 150 W, 22 a circuit). WALL B's two circuits on leg B
# meet 15.87 A wherever they go: 31.73 A and 17.31 A, OVER on any breaker,
# so no arrangement fixes it.
def test_balance_never_makes_an_over_pair_worse(seeded):
    pg, errors = seeded
    pg.evaluate(SEED_JS, [['WALL A', 22, 150], ['WALL B', 4, 150], ['WALL C', 4, 250]])
    pg.wait_for_timeout(500)
    try:
        amps = setup(pg, [[1, None], [1001, [3, 4]], [2, None]])
        assert amps[0] == pytest.approx([HEAVY] * 6), amps
        before = state(pg)
        bex = excess(before['pairs'])
        assert any(v > 0 for v in bex.values()), before['pairs']
        dlg = pg.evaluate(DIALOG_JS, True)
        assert 'Soca two-fer SL1 is still over a breaker. Balance found no arrangement '\
               'that brings it within.' in dlg['text'], dlg['text']
        pg.wait_for_timeout(300)
        after = state(pg)
        aex = excess(after['pairs'])
        # no breaker further over than it was, none newly over
        for k, v in aex.items():
            assert v <= bex.get(k, 0.0) + 1e-6, (k, before['pairs'], after['pairs'])
        assert sum(aex.values()) <= sum(bex.values()) + 1e-6
    finally:
        pg.evaluate(SEED_JS, WALLS)
        pg.wait_for_timeout(500)
    assert not errors, errors


# ── a distro with no output rows ───────────────────────────────────────────

def test_an_old_distro_without_output_rows_keeps_its_pairs_within(seeded):
    pg, errors = seeded
    setup(pg, WITHIN, distro=OLD_DISTRO)
    before = state(pg)
    assert_within(before['pairs'])
    assert all(p['limit'] == pytest.approx(LIMIT_A) for p in before['pairs']), before['pairs']
    s = pg.evaluate(SUGGEST_JS)
    pg.evaluate("() => { const app = window.app; app.applyPhaseBalance(app.suggestPhaseBalance('d1').moves); }")
    pg.wait_for_timeout(300)
    after = state(pg)
    assert_within(after['pairs'])
    if s['moves']:
        assert after['imb'] < before['imb'], (before['imb'], after['imb'])
    assert not errors, errors


# ── a locked screen ────────────────────────────────────────────────────────

def test_a_locked_leg_stays_and_the_other_leg_works_around_it(seeded):
    pg, errors = seeded
    setup(pg, WITHIN, locked=[0])
    before = state(pg)
    pg.evaluate("() => { const app = window.app; app.applyPhaseBalance(app.suggestPhaseBalance('d1').moves); }")
    pg.wait_for_timeout(300)
    after = state(pg)
    assert after['sockets'][0] == before['sockets'][0] == [1, 3], after
    assert after['stores'][0] == before['stores'][0], after
    assert_within(after['pairs'])
    pg.evaluate("() => { const w = window.app.project.layers.filter(l => (l.type || 'screen') === 'screen'); "
                "w[0].locked = false; window.app.updateLayers(w); }")
    pg.wait_for_timeout(300)
    assert not errors, errors


# ── no two-fer: Balance as it always was ──────────────────────────────────

def test_without_a_twofer_balance_is_unchanged(seeded):
    """The same three walls with no two-fer: WALL A on output 1, sockets 1
    and 3; WALL B on output 3, sockets 2 and 3; WALL C on output 2. The
    offer and the result are the ones Balance gave before the two-fer
    learned its breakers, figure for figure."""
    pg, errors = seeded
    setup(pg, [[1, [1, 3]], [3, [2, 3]], [2, None]], twofer=False)
    s = pg.evaluate(SUGGEST_JS)
    assert s == UNCHANGED_SUGGEST, s
    dlg = pg.evaluate(DIALOG_JS, True)
    assert 'two-fer' not in dlg['text'], dlg['text']
    pg.wait_for_timeout(300)
    after = state(pg)
    assert after['sockets'] == UNCHANGED_SOCKETS, after['sockets']
    assert after['pairs'] == []
    assert not errors, errors


# Read off Balance before it learned the two-fer's breakers (b409cff3), on
# the show above: WALL B to sockets 3 and 4, WALL C to 5 and 6.
UNCHANGED_SUGGEST = {
    'before': pytest.approx(93.10621130500019, rel=1e-9),
    'after': pytest.approx(18.739826927761534, rel=1e-9),
    'beforeBusiest': pytest.approx(62.06952343658658, rel=1e-9),
    'afterBusiest': pytest.approx(41.5274424487153, rel=1e-9),
    'searched': 3375, 'total': 3375,
    'moves': [{'name': 'SL3', 'layerName': 'WALL B', 'from': [2, 3], 'to': [3, 4]},
              {'name': 'SL2', 'layerName': 'WALL C', 'from': [1, 2], 'to': [5, 6]}],
}
UNCHANGED_SOCKETS = [[1, 3], [3, 4], [5, 6]]
