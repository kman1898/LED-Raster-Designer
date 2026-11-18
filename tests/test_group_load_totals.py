"""A grouped wall's LOAD is the sum of its members' panels, counted once.

A group routed as one wall hands every circuit to its first member: that
member's circuits carry the peers' panels and the peers carry none. The
load figures used to read each member's OWN panels only, so the wall's
power sheet printed half the load its own circuit table summed to, and the
show's "Load @ <V>" line - which only counted screens with circuits of
their own - dropped the peer outright while the kW line beside it kept it.

The rule (the house rule for groups: per-cabinet figures never cross
between members, TOTALS combine):
  * the load a screen's circuits carry (getCarriedPowerLoad) is the sum
    the circuit table is built from - the sheet's circuit amps add up to it;
  * a wall's members read the wall's load in the sidebar, the screen
    carrying its circuits or not; the wall's Power sheets follow the Power tab's Names switch
    (2026-10-01: "It should depend if it is set to group vs screens"): on
    Group ONE sheet titled by the group; on Screens a sheet per member.
    The FACTS sheet (owner, 2026-11-18: one for the set, none on the
    screens' sheets) follows the same switch: on Group ONE row for the
    wall, its load every member's panels; on Screens a row per member, its
    own; its TOTAL every panel once;
  * the overview's SHOW TOTALS counts every panel once, at the voltage of
    the circuits that feed it - no member dropped, none doubled where a
    member also has circuits of its own;
  * an ungrouped show reads exactly what it read before (pinned figures);
  * a long SHOW TOTALS key ("Load @ 208 V") never runs into its value.

Run locally:
    python3 -m pytest tests/test_group_load_totals.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# Two 4 x 3 walls of 200 px cabinets at 200 W, 208 V / 20 A, side by side
# and grouped - the same panel and the same wattage, so the group routes
# as ONE wall and WALL-L (the first member) carries every circuit - and an
# ungrouped 3 x 2 LONE at 150 W. Power sheets and the overview only.
SEED_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.binder;
    await j('PUT', '/api/project', proj);
    const add = (body) => j('POST', '/api/layer/add', body);
    const wall = {columns: 4, rows: 3, cabinet_width: 200, cabinet_height: 200,
                  powerVoltage: 208, powerAmperage: 20, panelWatts: 200,
                  powerFlowPattern: 'tl-v', powerOrganized: true, flowPattern: 'tl-h',
                  processorType: 'novastar-armor'};
    await add({...wall, name: 'WALL-L'});
    await add({...wall, name: 'WALL-R', offset_x: 800});
    await add({name: 'LONE', columns: 3, rows: 2, cabinet_width: 128, cabinet_height: 128,
               powerVoltage: 208, powerAmperage: 20, panelWatts: 150,
               powerFlowPattern: 'tl-v', powerOrganized: true, flowPattern: 'tl-h',
               processorType: 'novastar-armor', offset_x: 2000});
    let p = await j('GET', '/api/project');
    const L = p.layers.find(l => l.name === 'WALL-L');
    const R = p.layers.find(l => l.name === 'WALL-R');
    L.group_id = 'g1'; R.group_id = 'g1';
    p.groups = [{id: 'g1', name: 'WALL', layer_ids: [L.id, R.id]}];
    await j('PUT', '/api/project', p);
    p = await j('GET', '/api/project');
    app.project = p;
    app.dedupeProjectLayers('group_load_setup');
    const l = app.project.layers.find(x => x.name === 'WALL-L');
    const r = app.project.layers.find(x => x.name === 'WALL-R');
    const lone = app.project.layers.find(x => x.name === 'LONE');
    app.renderLayers();
    window.canvasRenderer.render();
    app.resetHistory('Group Load Seed');
    const plan = app.getAutoRoutePlan(l, 'power');
    return { l: l.id, r: r.id, lone: lone.id,
             owner: plan && plan.isOwner, peer: app.isServedByPeerRouting(r, 'power'),
             lCircuits: app.screenCircuits(l).length, rCircuits: app.screenCircuits(r).length };
}"""

OPTS = {'sheet': 'tabloid', 'palette': 'colour', 'sides': {'power': True, 'data': False},
        'scope': {'kind': 'show'}, 'cover': True, 'pull': False, 'hardware': False, 'titleBlock': True}


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(500)
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(800)
    # the fixture's premise: one wall, its first member carrying it all
    assert ids['owner'] is True and ids['peer'] is True, ids
    assert ids['lCircuits'] >= 2 and ids['rCircuits'] == 0, ids
    yield pg, ids, errors
    context.close()


# In-page mutations for one render, undone in a finally. `setup` is a JS
# function body run against (app, L, R, lone) that may return an undo fn.
RUN_JS = """([ids, opts, setupSrc, what]) => {
    const app = window.app;
    const byId = (id) => app.project.layers.find(l => l.id === id);
    const L = byId(ids.l), R = byId(ids.r), lone = byId(ids.lone);
    const setup = setupSrc ? new Function('app', 'L', 'R', 'lone', setupSrc) : null;
    const undo = setup ? setup(app, L, R, lone) : null;
    try {
        const own = (l) => { const f = app._bScreenFacts(l);
            return { name: l.name, watts: f.watts, amps1: f.amps1, amps3: f.amps3, voltage: f.voltage }; };
        const out = { own: [L, R, lone].map(own),
                      carried: [L, R, lone].map(l => { const c = app.getCarriedPowerLoad(l);
                          return { watts: c.watts, amps1: c.amps1, amps3: c.amps3, circuits: c.circuits,
                                   peerIds: c.peerIds }; }),
                      legAmps: [L, R, lone].map(l => app.getSocaPlan(l)
                          .reduce((s, x) => s + x.legs.reduce((a, g) => a + g.amps, 0), 0)) };
        // the FACTS sheet's table, as the binder builds it
        const spied = [];
        const origT = app._bTableLines;
        app._bTableLines = function (book, spec) {
            if (/^\d+ screens?$/.test(spec.title)) {
                spied.push(spec.rows.filter(r => r.cells).map(r => r.cells.slice()));
            }
            return origT.apply(this, arguments);
        };
        let plan;
        try { plan = app.planBinder(opts); } finally { app._bTableLines = origT; }
        out.facts = spied.length ? spied[spied.length - 1] : null;
        const render = (title) => {
            const idx = plan.findIndex(p => p.title === title);
            if (idx < 0) return null;
            const r = app.renderBinderPage(opts, idx);
            return { texts: r.texts, ops: r.record.ops.filter(o => o.op === 'text') };
        };
        out.plan = plan.map(p => p.title);
        for (const t of (what || [])) out[t] = render(t);
        // the sidebar readout for each screen, as the user would select it
        const saved = app.currentLayer;
        out.sidebar = {};
        try {
            for (const l of [L, R, lone]) {
                app.currentLayer = l;
                app.updatePowerCapacityDisplay();
                out.sidebar[l.name] = {
                    amps1: document.getElementById('power-total-amps-1ph').textContent,
                    amps3: document.getElementById('power-total-amps-3ph').textContent,
                    cached1: l._powerTotalAmps1, cached3: l._powerTotalAmps3 };
            }
        } finally {
            app.currentLayer = saved;
            if (saved) app.updatePowerCapacityDisplay();
        }
        // text widths for the overlap check, in the binder's own font
        const ctx = document.createElement('canvas').getContext('2d');
        for (const k of Object.keys(out)) {
            const r = out[k];
            if (!r || !r.ops) continue;
            r.ops.forEach(o => {
                ctx.font = `${o.weight || 400} ${o.size}px Helvetica, Arial, sans-serif`;
                o.w = ctx.measureText(o.text).width;
            });
        }
        return out;
    } finally {
        if (typeof undo === 'function') undo();
    }
}"""


def _run(pg, ids, setup=None, what=()):
    return pg.evaluate(RUN_JS, [ids, OPTS, setup, list(what)])


def _show_totals(texts):
    s = texts.index('SHOW TOTALS')
    c = texts.index('CONTENTS')
    body = texts[s + 1:c]
    return [(body[i], body[i + 1]) for i in range(0, len(body) - 1, 2)]


FACTS_COLS = ('screen', 'size', 'panels', 'resolution', 'watts', 'amps1', 'amps3', 'circuits', 'ports')


def _facts(out):
    """The FACTS sheet's rows by their first cell: each a dict of its
    columns."""
    assert out['facts'], 'no FACTS sheet'
    return {r[0]: dict(zip(FACTS_COLS, r)) for r in out['facts']}


def _row(watts, a1, a3):
    """A row's watts and amps as the sheet prints them."""
    return ('{:,}'.format(round(watts)), '%.1f' % a1, '%.1f' % a3)


def _figures(row):
    return (row['watts'], row['amps1'], row['amps3'])


SCREENS_ON_BOTH = """
    const had = Object.prototype.hasOwnProperty.call(app.project, 'groupNameDisplayByView');
    const was = app.project.groupNameDisplayByView;
    app.project.groupNameDisplayByView = { ...(was || {}), power: 'screens', 'data-flow': 'screens' };
    return () => { if (had) app.project.groupNameDisplayByView = was;
                   else delete app.project.groupNameDisplayByView; };
"""


def _no_facts_block(sheet):
    """A screen's sheet carries no FACTS block of its own any more."""
    assert 'FACTS' not in sheet['texts'], sheet['texts']


def _fmt(a1, a3, w):
    return '%.1f A 1φ · %.1f A 3φ · %.1f kW' % (a1, a3, w / 1000)


L_POWER = 'WALL-L - Power - Front View'
LONE_POWER = 'LONE - Power - Front View'


def test_the_walls_load_is_both_members_and_its_circuits_sum_to_it(page):
    """The wall's first member carries every circuit: the load its circuits
    carry is WALL-L's panels plus WALL-R's, each counted once; WALL-R's own
    circuits carry nothing; the circuit amps sum to the carried amps; the
    sidebar reads the wall's amps on either member while each cached own
    figure stays its own."""
    pg, ids, errors = page
    out = _run(pg, ids)
    (ol, orr, olone), (cl, cr, clone) = out['own'], out['carried']
    assert cl['peerIds'] == [ids['r']] and cr['circuits'] == 0 and cr['watts'] == 0, out['carried']
    assert cl['watts'] == pytest.approx(ol['watts'] + orr['watts']), (cl, ol, orr)
    assert cl['watts'] == pytest.approx(24 * 200)
    assert out['legAmps'][0] == pytest.approx(cl['amps1']), (out['legAmps'], cl)
    assert cl['amps3'] == pytest.approx(cl['watts'] / (208 * 1.73))
    side = out['sidebar']
    assert side['WALL-L']['amps1'] == '%.2f A' % cl['amps1'], side
    assert side['WALL-L']['amps3'] == '%.2f A' % cl['amps3'], side
    assert side['WALL-L']['cached1'] == pytest.approx(ol['amps1'])
    # the peer reads the wall's load too, whichever member is current
    # (QA 1.6.0-beta.4); its cached own figure stays its own; the lone
    # screen reads its own
    assert side['WALL-R']['amps1'] == '%.2f A' % cl['amps1'], side
    assert side['WALL-R']['amps3'] == '%.2f A' % cl['amps3'], side
    assert side['WALL-R']['cached1'] == pytest.approx(orr['amps1'])
    assert side['LONE']['amps1'] == '%.2f A' % olone['amps1'], side
    assert not errors, errors


# The Power tab's Names switch decides the wall's Power sheets (owner,
# 2026-10-01: "It should depend if it is set to group vs screens"). Absent,
# it is Group: ONE sheet, titled by the group.
GROUP_POWER = 'WALL - Power - Front View'
R_POWER = 'WALL-R - Power - Front View'
SCREENS_ON_POWER = """
    const had = Object.prototype.hasOwnProperty.call(app.project, 'groupNameDisplayByView');
    const was = app.project.groupNameDisplayByView;
    app.project.groupNameDisplayByView = { ...(was || {}), power: 'screens' };
    return () => { if (had) app.project.groupNameDisplayByView = was;
                   else delete app.project.groupNameDisplayByView; };
"""


def _chain(*setups):
    """Several setups as one, undone in reverse."""
    body = ['const undos = [];']
    for s in setups:
        body.append('undos.push((() => {' + s + '})());')
    body.append('return () => undos.reverse().forEach(u => typeof u === "function" && u());')
    return '\n'.join(body)


def test_the_facts_sheet_prints_the_wall_as_one_row(page):
    """Names on Group (the default): the wall prints ONE Power sheet, titled
    WALL - no WALL-L or WALL-R sheet - with no FACTS block on it, and ONE
    row on the FACTS sheet: the group's panels, every member's, the load
    the wall's circuits sum to."""
    pg, ids, _e = page
    out = _run(pg, ids, what=[GROUP_POWER])
    assert GROUP_POWER in out['plan'], out['plan']
    assert L_POWER not in out['plan'] and R_POWER not in out['plan'], out['plan']
    _no_facts_block(out[GROUP_POWER])
    facts = _facts(out)
    assert 'WALL-L' not in facts and 'WALL-R' not in facts, facts
    ol, orr, _ = out['own']
    wall = facts['WALL']
    assert _figures(wall) == _row(ol['watts'] + orr['watts'], ol['amps1'] + orr['amps1'],
                                  ol['amps3'] + orr['amps3']), wall
    assert abs(float(wall['amps1']) - out['legAmps'][0]) <= 0.05, (wall, out['legAmps'])
    assert wall['size'] == '4 × 3 + 4 × 3' and wall['panels'] == '24', wall


def test_screens_on_power_prints_each_member_with_its_own_load(page):
    """Names on Screens: WALL-L and WALL-R each get a Power sheet - WALL-R
    too, which carries no circuit of its own (the 2026-10-01 bug) - and,
    with Data on Screens too, a row each on the FACTS sheet, each its own
    load; no WALL row. (Either tab on Group prints the wall as one row.)"""
    pg, ids, _e = page
    out = _run(pg, ids, SCREENS_ON_BOTH, what=[L_POWER, R_POWER])
    assert L_POWER in out['plan'] and R_POWER in out['plan'], out['plan']
    assert GROUP_POWER not in out['plan'], out['plan']
    _no_facts_block(out[L_POWER])
    _no_facts_block(out[R_POWER])
    ol, orr, _ = out['own']
    facts = _facts(out)
    assert 'WALL' not in facts, facts
    assert _figures(facts['WALL-L']) == _row(ol['watts'], ol['amps1'], ol['amps3']), facts
    assert _figures(facts['WALL-R']) == _row(orr['watts'], orr['amps1'], orr['amps3']), facts


def test_the_show_totals_count_every_screen_once(page):
    """All three screens at 208 V: SHOW TOTALS prints one Load line whose
    amps and kW are every screen's own summed - the peer with no circuits
    of its own included - and no "Load @" line."""
    pg, ids, _e = page
    out = _run(pg, ids, what=['Overview'])
    totals = _show_totals(out['Overview']['texts'])
    loads = [(k, v) for k, v in totals if k.startswith('Load')]
    own = out['own']
    watts = sum(f['watts'] for f in own)
    assert loads == [('Load', _fmt(sum(f['amps1'] for f in own), sum(f['amps3'] for f in own), watts))], totals
    assert loads[0][1] == '27.4 A 1φ · 15.8 A 3φ · 5.7 kW', loads


def test_a_member_with_circuits_of_its_own_is_not_counted_twice(page):
    """Hand-drawn circuits: WALL-L's one circuit carries all of WALL-L and
    WALL-R's first cabinet, WALL-R's own circuit the other eleven. WALL-L's
    wall load is 13 cabinets, WALL-R's 11, and SHOW TOTALS still reads the
    show's 30 panels once."""
    pg, ids, _e = page
    setup = """
        const keep = [L, R].map(l => ({ l, p: l.powerFlowPattern, c: l.powerCustomPaths }));
        L.powerFlowPattern = 'custom'; R.powerFlowPattern = 'custom';
        const mine = L.panels.map(p => ({row: p.row, col: p.col}));
        const first = R.panels.find(p => p.row === 0 && p.col === 0);
        L.powerCustomPaths = {1: [...mine, {row: 0, col: 0, layerId: R.id}]};
        R.powerCustomPaths = {1: R.panels.filter(p => p !== first).map(p => ({row: p.row, col: p.col}))};
        return () => keep.forEach(k => { k.l.powerFlowPattern = k.p; k.l.powerCustomPaths = k.c; });
    """
    out = _run(pg, ids, setup, what=['Overview', GROUP_POWER])
    cl, cr, _ = out['carried']
    assert cl['peerIds'] == [ids['r']] and cl['watts'] == pytest.approx(13 * 200), cl
    assert cr['peerIds'] == [] and cr['watts'] == pytest.approx(11 * 200), cr
    own = out['own']
    watts = sum(f['watts'] for f in own)
    totals = _show_totals(out['Overview']['texts'])
    loads = [(k, v) for k, v in totals if k.startswith('Load')]
    assert loads == [('Load', _fmt(watts / 208, watts / (208 * 1.73), watts))], totals
    # A hand-drawn circuit crossing onto WALL-R is a wall routed as one: the
    # group's ONE Power sheet (2026-10-01) and ONE FACTS row, its panels
    # counted once, and the TOTAL the show's 30 panels once.
    assert L_POWER not in out['plan'] and R_POWER not in out['plan'], out['plan']
    facts = _facts(out)
    ol, orr, _olone = own
    both = ol['watts'] + orr['watts']
    assert _figures(facts['WALL']) == _row(both, both / 208, both / (208 * 1.73)), facts
    assert facts['Total']['panels'] == '30', facts
    assert _figures(facts['Total']) == _row(watts, watts / 208, watts / (208 * 1.73)), facts


def test_a_crossing_circuit_is_listed_on_each_member_it_touches(page):
    """Names on Screens with WALL-L's circuit stepping onto WALL-R's first
    cabinet: WALL-R's sheet lists that circuit too, saying where the rest of
    it is ("also on WALL-L"), beside WALL-R's own; WALL-L's lists it saying
    "also on WALL-R"."""
    pg, ids, _e = page
    setup = """
        const keep = [L, R].map(l => ({ l, p: l.powerFlowPattern, c: l.powerCustomPaths }));
        L.powerFlowPattern = 'custom'; R.powerFlowPattern = 'custom';
        const mine = L.panels.map(p => ({row: p.row, col: p.col}));
        const first = R.panels.find(p => p.row === 0 && p.col === 0);
        L.powerCustomPaths = {1: [...mine, {row: 0, col: 0, layerId: R.id}]};
        R.powerCustomPaths = {1: R.panels.filter(p => p !== first).map(p => ({row: p.row, col: p.col}))};
        return () => keep.forEach(k => { k.l.powerFlowPattern = k.p; k.l.powerCustomPaths = k.c; });
    """
    out = _run(pg, ids, _chain(setup, SCREENS_ON_BOTH), what=[L_POWER, R_POWER])
    l_texts, r_texts = out[L_POWER]['texts'], out[R_POWER]['texts']
    assert any('also on WALL-R' in t for t in l_texts), l_texts
    assert any('also on WALL-L' in t for t in r_texts), r_texts
    # the FACTS sheet counts each circuit once, on the screen it starts on
    facts = _facts(out)
    assert facts['WALL-L']['circuits'] == '1' and facts['WALL-R']['circuits'] == '1', facts


def test_members_each_on_their_own_circuits_read_as_before(page):
    """WALL-R at 250 W is no longer the same panel load, so the group does
    not route as one: each member carries its own circuits, the FACTS sheet
    prints a row per member and the show's Load is the plain sum."""
    pg, ids, _e = page
    setup = """
        const was = R.panelWatts; R.panelWatts = 250;
        return () => { R.panelWatts = was; };
    """
    out = _run(pg, ids, setup, what=['Overview', L_POWER])
    cl, cr, _ = out['carried']
    assert cl['peerIds'] == [] and cr['peerIds'] == [] and cr['circuits'] > 0, out['carried']
    # the data side still routes the wall as one (its Names on Group), so
    # the FACTS sheet prints the wall as one row, every member's watts in it
    facts = _facts(out)
    assert 'WALL-L' not in facts and 'WALL-R' not in facts, facts
    assert facts['WALL']['watts'] == '{:,}'.format(round(out['own'][0]['watts'] + out['own'][1]['watts'])), facts
    own = out['own']
    totals = _show_totals(out['Overview']['texts'])
    watts = sum(f['watts'] for f in own)
    assert [(k, v) for k, v in totals if k.startswith('Load')] == [
        ('Load', _fmt(watts / 208, watts / (208 * 1.73), watts))], totals
    assert watts == pytest.approx(12 * 200 + 12 * 250 + 6 * 150)


def test_an_ungrouped_show_is_unchanged(page):
    """No group at all: today's figures, pinned - the show's Load, each
    screen's FACTS row and the sidebar."""
    pg, ids, _e = page
    setup = """
        const g = app.project.groups; const gl = L.group_id, gr = R.group_id;
        app.project.groups = []; delete L.group_id; delete R.group_id;
        return () => { app.project.groups = g; L.group_id = gl; R.group_id = gr; };
    """
    out = _run(pg, ids, setup, what=['Overview', L_POWER, LONE_POWER])
    assert [c['peerIds'] for c in out['carried']] == [[], [], []]
    totals = dict(_show_totals(out['Overview']['texts']))
    assert totals['Load'] == '27.4 A 1φ · 15.8 A 3φ · 5.7 kW', totals
    assert totals['Panels'] == '30' and totals['Screens'] == '3', totals
    facts = _facts(out)
    assert _figures(facts['WALL-L']) == ('2,400', '11.5', '6.7'), facts
    assert _figures(facts['LONE']) == ('900', '4.3', '2.5'), facts
    assert _figures(facts['Total']) == ('5,700', '27.4', '15.8'), facts
    assert facts['Total']['panels'] == '30', facts
    _no_facts_block(out[L_POWER])
    _no_facts_block(out[LONE_POWER])
    side = out['sidebar']
    assert side['WALL-L']['amps1'] == '11.54 A' and side['WALL-L']['amps3'] == '6.67 A', side
    assert side['LONE']['amps1'] == '4.33 A' and side['LONE']['amps3'] == '2.50 A', side


def test_a_long_show_totals_key_never_runs_into_its_value(page):
    """LONE on 110 V puts the show on two voltages, so SHOW TOTALS prints
    "Load @ 208 V" and "Load @ 110 V": each key, measured in the bold it is
    drawn in, ends before its value begins, every value in the block
    starts at one x, and the wall's amps are all at 208 V."""
    pg, ids, _e = page
    setup = """
        const was = lone.powerVoltage; lone.powerVoltage = 110;
        return () => { lone.powerVoltage = was; };
    """
    out = _run(pg, ids, setup, what=['Overview'])
    ops = out['Overview']['ops']
    texts = [o['text'] for o in ops]
    s, c = texts.index('SHOW TOTALS'), texts.index('CONTENTS')
    body = ops[s + 1:c]
    pairs = [(body[i], body[i + 1]) for i in range(0, len(body) - 1, 2)]
    keys = [k['text'] for k, _v in pairs]
    assert 'Load @ 208 V' in keys and 'Load @ 110 V' in keys, keys
    for k, v in pairs:
        assert abs(k['y'] - v['y']) < 0.5, (k, v)
        assert k['x'] + k['w'] + 4 <= v['x'], ('the key runs into its value', k, v)
    assert len({round(v['x'], 1) for _k, v in pairs}) == 1, pairs
    per = {k['text']: v['text'] for k, v in pairs}
    own = out['own']
    at208 = own[0]['watts'] + own[1]['watts']
    assert per['Load @ 208 V'] == _fmt(at208 / 208, at208 / (208 * 1.73), at208), per
    w110 = own[2]['watts']
    # 1.5, bug fix 3 (2026-10-16, "It must use the service's V_LL"): the
    # 3φ figure of a 110V screen divides by its 120/208 service's 208V.
    assert per['Load @ 110 V'] == _fmt(w110 / 110, w110 / (208 * 1.73), w110), per
    # The FACTS sheet the same way: amps never blend across voltages - a
    # TOTAL row per voltage, the TOTAL row's amps blank, its watts the
    # show's.
    rows = [r[0] for r in out['facts']]
    assert rows[-3:] == ['Total @ 208 V', 'Total @ 110 V', 'Total'], rows
    facts = _facts(out)
    assert _figures(facts['Total @ 208 V']) == _row(at208, at208 / 208, at208 / (208 * 1.73)), facts
    assert _figures(facts['Total @ 110 V']) == _row(w110, w110 / 110, w110 / (208 * 1.73)), facts
    assert _figures(facts['Total']) == ('{:,}'.format(round(at208 + w110)), '', ''), facts
