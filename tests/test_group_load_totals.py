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
  * the screen carrying a wall's circuits reads the wall's load in the
    sidebar; the wall's Power sheets follow the Power tab's Names switch
    (2026-10-01: "It should depend if it is set to group vs screens"): on
    Group ONE sheet titled by the group, its Load the group's panels beside
    a "Wall load" row; on Screens a sheet per member, each Load the
    member's own beside the Wall load of the circuits on its cabinets;
  * the overview's SHOW TOTALS counts every panel once, at the voltage of
    the circuits that feed it - no member dropped, none doubled where a
    member also has circuits of its own;
  * an ungrouped show reads exactly what it read before (pinned figures);
  * a long SHOW TOTALS key ("Load @ 208 V") never runs into its value.

Run locally:
    python3 -m pytest tests/test_group_load_totals.py -v --browser chromium
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

LOAD_LINE = re.compile(r'^(\d+\.\d) A 1φ · (\d+\.\d) A 3φ · (\d+\.\d) kW$')
WALL_LINE = re.compile(r'^(\d+\.\d) A 1φ · (\d+\.\d) A 3φ · (\d+\.\d) kW · (.+)$')


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
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
        const plan = app.planBinder(opts);
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


def _facts(sheet):
    """The power sheet's FACTS pairs, from its rendered text ops: a key
    stands at the block's left edge, its value to the right of it - and a
    value the column wraps is drawn a line at a time, each further line at
    the value's x, so the lines are joined back into one value."""
    ops = sheet['ops']
    s = next(i for i, o in enumerate(ops) if o['text'] == 'FACTS')
    left = ops[s]['x']
    keys = ('Screen', 'Load', 'Wall load', 'Circuits', 'Fed by')
    out = []
    for o in ops[s + 1:]:
        if abs(o['x'] - left) < 0.5:
            if o['text'] not in keys:
                break
            out.append([o['text'], None])
        elif out:
            out[-1][1] = o['text'] if out[-1][1] is None else out[-1][1] + ' ' + o['text']
        else:
            break
    return [(k, v) for k, v in out]


def _fmt(a1, a3, w):
    return '%.1f A 1φ · %.1f A 3φ · %.1f kW' % (a1, a3, w / 1000)


L_POWER = 'WALL-L - Power - Front View'
LONE_POWER = 'LONE - Power - Front View'


def test_the_walls_load_is_both_members_and_its_circuits_sum_to_it(page):
    """The wall's first member carries every circuit: the load its circuits
    carry is WALL-L's panels plus WALL-R's, each counted once; WALL-R's own
    circuits carry nothing; the circuit amps sum to the carried amps; the
    sidebar of the carrying screen reads the wall's amps while its cached
    own figure stays its own."""
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
    # the peer reads its own panels; the lone screen its own
    assert side['WALL-R']['amps1'] == '%.2f A' % orr['amps1'], side
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


def test_the_power_sheet_prints_the_screens_load_and_the_walls(page):
    """Names on Group (the default): the wall prints ONE Power sheet, titled
    WALL - no WALL-L or WALL-R sheet. Its Load is the group's panels, every
    member's, and a Wall load row names both members and carries the amps
    the table's circuits sum to."""
    pg, ids, _e = page
    out = _run(pg, ids, what=[GROUP_POWER])
    assert GROUP_POWER in out['plan'], out['plan']
    assert L_POWER not in out['plan'] and R_POWER not in out['plan'], out['plan']
    facts = dict(_facts(out[GROUP_POWER]))
    ol, orr, _ = out['own']
    assert facts['Load'] == _fmt(ol['amps1'] + orr['amps1'], ol['amps3'] + orr['amps3'],
                                 ol['watts'] + orr['watts']), facts
    m = WALL_LINE.match(facts['Wall load'])
    assert m and m.group(4) == 'WALL-L + WALL-R', facts
    assert abs(float(m.group(1)) - out['legAmps'][0]) <= 0.05, (m.group(1), out['legAmps'])
    assert abs(float(m.group(1)) - (ol['amps1'] + orr['amps1'])) <= 0.05
    assert m.group(3) == '%.1f' % ((ol['watts'] + orr['watts']) / 1000)
    keys = [k for k, _v in _facts(out[GROUP_POWER])]
    assert keys[:3] == ['Screen', 'Load', 'Wall load'], keys
    assert facts['Screen'].startswith('4 × 3 + 4 × 3 · 24 panels'), facts


def test_screens_on_power_prints_each_member_with_its_own_load(page):
    """Names on Screens: WALL-L and WALL-R each get a Power sheet - WALL-R
    too, which carries no circuit of its own (the 2026-10-01 bug). Each
    reads its own Load and the Wall load of the circuits on its cabinets."""
    pg, ids, _e = page
    out = _run(pg, ids, SCREENS_ON_POWER, what=[L_POWER, R_POWER])
    assert L_POWER in out['plan'] and R_POWER in out['plan'], out['plan']
    assert GROUP_POWER not in out['plan'], out['plan']
    ol, orr, _ = out['own']
    lf, rf = dict(_facts(out[L_POWER])), dict(_facts(out[R_POWER]))
    assert lf['Load'] == _fmt(ol['amps1'], ol['amps3'], ol['watts']), lf
    assert rf['Load'] == _fmt(orr['amps1'], orr['amps3'], orr['watts']), rf
    for f in (lf, rf):
        m = WALL_LINE.match(f['Wall load'])
        assert m and m.group(4) == 'WALL-L + WALL-R', f


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
    # group's ONE Power sheet (2026-10-01) carries a single Wall load row -
    # WALL-L's circuit, 13 cabinets; WALL-R's own circuit carries only it.
    assert L_POWER not in out['plan'] and R_POWER not in out['plan'], out['plan']
    pairs = _facts(out[GROUP_POWER])
    walls = [v for k, v in pairs if k == 'Wall load']
    assert len(walls) == 1, pairs
    m = WALL_LINE.match(walls[0])
    assert m and abs(float(m.group(1)) - 13 * 200 / 208) <= 0.05, pairs


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
    out = _run(pg, ids, _chain(setup, SCREENS_ON_POWER), what=[L_POWER, R_POWER])
    l_texts, r_texts = out[L_POWER]['texts'], out[R_POWER]['texts']
    assert any('also on WALL-R' in t for t in l_texts), l_texts
    assert any('also on WALL-L' in t for t in r_texts), r_texts
    # WALL-R lists two circuits: WALL-L's crossing one and its own
    assert dict(_facts(out[R_POWER]))['Circuits'].startswith('2 at 208'), _facts(out[R_POWER])


def test_members_each_on_their_own_circuits_read_as_before(page):
    """WALL-R at 250 W is no longer the same panel load, so the group does
    not route as one: each member carries its own circuits, no Wall load
    row prints and the show's Load is the plain sum."""
    pg, ids, _e = page
    setup = """
        const was = R.panelWatts; R.panelWatts = 250;
        return () => { R.panelWatts = was; };
    """
    out = _run(pg, ids, setup, what=['Overview', L_POWER])
    cl, cr, _ = out['carried']
    assert cl['peerIds'] == [] and cr['peerIds'] == [] and cr['circuits'] > 0, out['carried']
    assert 'Wall load' not in dict(_facts(out[L_POWER]))
    own = out['own']
    totals = _show_totals(out['Overview']['texts'])
    watts = sum(f['watts'] for f in own)
    assert [(k, v) for k, v in totals if k.startswith('Load')] == [
        ('Load', _fmt(watts / 208, watts / (208 * 1.73), watts))], totals
    assert watts == pytest.approx(12 * 200 + 12 * 250 + 6 * 150)


def test_an_ungrouped_show_is_unchanged(page):
    """No group at all: today's figures, pinned - the show's Load, each
    sheet's Load and the sidebar - and no Wall load row anywhere."""
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
    lf = dict(_facts(out[L_POWER]))
    assert lf['Load'] == '11.5 A 1φ · 6.7 A 3φ · 2.4 kW' and 'Wall load' not in lf, lf
    nf = dict(_facts(out[LONE_POWER]))
    assert nf['Load'] == '4.3 A 1φ · 2.5 A 3φ · 0.9 kW' and 'Wall load' not in nf, nf
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
    assert per['Load @ 110 V'] == _fmt(w110 / 110, w110 / (110 * 1.73), w110), per
