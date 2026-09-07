"""A multi dropped on a circuit takes up to the box's free circuits, and a
clear forgets the cuts at the cleared multis' edges.

User (2026-09-04), on his own show file: "if i add circuits the numbering
is all wrong and when i try and say drag multi 2 onto 6 ports it only lets
me do 1 because of the incorrect numbering. we need to audit this so it
allows me to do up to 6 if i am doing multi/soca. so even if i have 1
circuit taken on multi 1 then i have 5 circuits left and i should only be
able to add 5 more to that multi."

The wall he was looking at: circuit-pip drops (_dockDropTail) cut before
and after their circuit by design, so a run of them left twelve
one-circuit multis S2..S13 behind - and (a) the distro's Clear dropped
every assignment but kept the cuts ("Split boundaries stay"), so the wall
still read S1[1-6] S2[7] S3[8] ... S14[19-22]; (b) a slot dropped on
circuit 7 assigned only the multi under the cursor, the one-circuit S2, so
the box read 1/6 with six free circuits.

Two rulings, pinned here:

  1. A CLEAR FORGETS THE CUTS TOO (extends 2026-08-30: "clearing must not
     remember how i had it programmed"). The split points at a cleared
     multi's edges go with its programming, so the cleared circuits fall
     back onto the natural box grid; multis that were NOT cleared keep
     their name, distro, number and length under their new index
     (_resegmentSocaStores). One history entry; one undo restores the
     cuts. AND every cut left between two multis that are both unassigned
     once the clear has run goes too: on the user's file the twelve
     one-circuit leftovers were already unassigned, so forgetting only the
     cleared S1's edges still read S2[7] S3[8] ... - an unassigned cut is
     programming nobody is using, and a clear must not remember how the
     wall was programmed. A cut with an assigned multi on either side
     stays (that multi keeps its identity), so a run of leftovers flanked
     by fed multis on BOTH sides keeps both cuts - forgetting either would
     weld a multi that was not cleared into another and lose its number.

  3. ONE CIRCUIT COMES OFF ITS BOX ON ITS OWN (2026-09-05: "lets say i
     pair 6 circuits on power but i want to delete the 6th circuit from
     the distro we have no way of doing that. can only clear the whole
     multi."). The circuit chip's clear - and the chip dragged back onto
     the tray - takes THAT circuit off the box and nothing else: it
     becomes its own unassigned one-circuit multi, the head part keeps
     the multi's identity, pin and rendered tails, a tail part after it
     stays on the SAME box holding the tails it showed, so the remaining
     circuits neither move nor renumber. The chip is the circuit, the
     multi header is the box, the distro is everything. ONE 'Clear
     Circuit' entry; one undo puts the cuts, stores and positions back.
     The freed circuit is then a leftover the take rule absorbs.

  2. A MULTI DROPPED ON A CIRCUIT TAKES THE BOX'S FIRST CIRCUITS, UP TO
     ITS FREE ONES. Anchored at the START of the box cell (2026-09-05:
     "data and power when dragged onto a screen in bulk starts say s1-6
     and then as you drag towards 1-1 it fills all 6 circuits. i need it
     to start at 1-1 instead and increase to 1-6 instead. it is backwards
     for how it should work." - "start at the 1st circuit regardless of
     naming. should just be in order."): the span runs from the cell's
     first circuit TO the dropped one - hover the 6th, six light; the
     1st, one - absorbing the unassigned leftovers in between, skipping
     head circuits already on another box (and refusing on a circuit
     that itself is), never crossing the grid line; capped at what the
     box can still hold (its smallest member's box size minus the pinned
     incumbents' legs), the FIRST circuits landing and the rest staying
     as their own unassigned multi ("took N of M"); a full box refuses
     and moves nothing. The plain whole-multi drop and the mid-multi drop
     are ONE rule (takeSocaOnto), ONE history entry ('Assign Multi
     Distro'); the pip drop (_dockDropTail) stays the finest grain.

Run locally (ONE pytest at a time - the browser-test servers use fixed
ports; LRD_E2E_PORT picks another):
    python -m pytest tests/test_power_take_rule.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1500, 'height': 900})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)  # socket connect + app init
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(500)
    yield pg
    context.close()


# Real server layers, so undo has something to restore: 100V x 5A against
# 100W panels puts a 5-tile tl-v column exactly on a circuit, so `columns`
# IS the circuit count (the test_power_shared_socas.py builder's
# arithmetic). Every screen this module makes is named 'TK <name>' and sits
# far below the seed screen; each seed sweeps the previous test's screens
# first, and the module guard puts the server back at the end.
SEED_JS = """async (spec) => {
    const app = window.app, r = window.canvasRenderer;
    let project = await (await fetch('/api/project')).json();
    project.layers = (project.layers || [])
        .filter(l => !String(l.name || '').startsWith('TK '));
    project.distros = (spec.distros || [{ id: 'dtk', name: 'SR' }]).map(d =>
        Object.assign({ ratingA: 400, voltage: 208, phase: 3 }, d));
    await fetch('/api/project', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(project),
    });
    let ox = 0;
    for (const s of spec.screens) {
        await fetch('/api/layer/add', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                name: 'TK ' + s.name, columns: s.columns, rows: 5,
                cabinet_width: 128, cabinet_height: 128,
                offset_x: ox, offset_y: 2400,
            }),
        });
        ox += s.columns * 128 + 256;
    }
    project = await (await fetch('/api/project')).json();
    const ids = {};
    for (const s of spec.screens) {
        const l = project.layers.find(x => x.name === 'TK ' + s.name);
        ids[s.name] = l.id;
        Object.assign(l, {
            powerVoltage: '100', powerAmperage: '5', panelWatts: '100',
            powerOrganized: true, powerMaximize: false,
            powerFlowPattern: 'tl-v',
        }, s.fields || {});
    }
    await fetch('/api/project', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(project),
    });
    app.project = await (await fetch('/api/project')).json();
    if (typeof app.dedupeProjectLayers === 'function') {
        app.dedupeProjectLayers('take_rule_seed');
    }
    app._circuitTailCache = null;
    r.viewMode = 'power';
    r.zoom = 0.2; r.panX = 40; r.panY = -400;
    app.renderLayers();
    r.render();
    if (typeof app._flushPendingSaveState === 'function') {
        app._flushPendingSaveState();
    }
    app.resetHistory('Take Rule Seed');
    const counts = {};
    for (const s of spec.screens) {
        const l = app.project.layers.find(x => x.id === ids[s.name]);
        counts[s.name] = app.screenCircuits(l).length;
    }
    return { ids, counts };
}"""

# The wall as the plan reads it: one row per multi - index, number, name,
# the circuit ordinals it holds (1-based, plan order), its distro and the
# tails it renders - plus the raw stores, so a test can pin both what the
# user sees and what the file says.
READ_JS = """(layerId) => {
    const app = window.app;
    const l = app.project.layers.find(x => x.id === layerId);
    app._circuitTailCache = null;
    const circuits = app.screenCircuits(l);
    const ord = new Map(circuits.map((c, i) => [c.num, i + 1]));
    const plan = app.getSocaPlan(l).map(s => ({
        soca: s.soca, number: s.number, name: s.name,
        ords: s.legs.map(g => ord.get(g.circuit)),
        tails: s.legs.map(g => g.leg),
        distro: s.distroId || null,
    }));
    return {
        plan,
        shape: plan.map(s => s.ords.length),
        splits: l.powerSocaSplits || [],
        distro: l.powerSocaDistro || {},
        num: l.powerSocaNumber || {},
        pos: l.powerSocaPhasePos || {},
        names: l.powerSocaNames || {},
        lengths: l.powerSocaLengths || {},
    };
}"""

HIST_JS = "(n) => window.app.history.map(h => h.action).slice(-n)"
HIST_LEN_JS = "() => window.app.history.length"
SAID_JS = "() => document.getElementById('status-message').textContent"
# A silent drop leaves the last line standing, so a test that asserts
# silence blanks the status bar first.
HUSH_JS = "() => { document.getElementById('status-message').textContent = ''; }"


def seed(page, screens, distros=None):
    spec = {'screens': screens}
    if distros:
        spec['distros'] = distros
    st = page.evaluate(SEED_JS, spec)
    page.wait_for_timeout(600)
    for s in screens:
        # columns IS the circuit count, or every ordinal below is wrong
        assert st['counts'][s['name']] == s['columns'], st
    return st['ids']


def read(page, layer_id):
    return page.evaluate(READ_JS, layer_id)


def undo(page):
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(700)


def circuit_num(page, layer_id, ordinal):
    return page.evaluate("""([id, o]) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === id);
        return app.screenCircuits(l)[o - 1].num;
    }""", [layer_id, ordinal])


def drop_slot(page, layer_id, ordinal, distro_id, number, title):
    """The dock's slot drop, aimed at the circuit at `ordinal`, through the
    same entry the pointer release calls."""
    return page.evaluate("""async ([id, o, d, n, title]) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === id);
        const num = app.screenCircuits(l)[o - 1].num;
        app._circuitTailCache = null;
        const slot = app._powerNaming(l).slots.get(num);
        app._dockDropSlot({ type: 'slot', distroId: d, number: n, title },
                          { kind: 'run', layerId: id, socaIndex: slot.multi,
                            num });
        await new Promise(res => setTimeout(res, 300));
        return true;
    }""", [layer_id, ordinal, distro_id, number, title])


# The user's wall: 22 circuits, cut into S1[1-6], twelve one-circuit multis
# S2..S13 (circuits 7-18) and S14[19-22] - the trail a run of circuit-pip
# drops leaves behind.
CHOPPED = [7, 8, 9, 10, 11, 13, 14, 15, 16, 17]


def chopped_fields(assigned):
    """Stores for the chopped wall: every one of its 14 multis on dtk,
    pinned to its own number, when `assigned`; bare cuts otherwise."""
    f = {'powerSocaSplits': list(CHOPPED)}
    if assigned:
        f['powerSocaDistro'] = {str(i): 'dtk' for i in range(1, 15)}
        f['powerSocaNumber'] = {str(i): i for i in range(1, 15)}
    return f


# ── 1. a clear forgets the cuts ───────────────────────────────────────────

def test_clear_distro_on_a_chopped_wall_restores_the_natural_grid(page):
    """Clear on the distro chip: every assignment goes, and so do the cuts
    at the cleared multis' edges - the wall reads S1[1-6] S2[7-12]
    S3[13-18] S4[19-22] again, not S1[1-6] S2[7] S3[8] ... S14[19-22]. ONE
    'Clear Distro' entry; one undo puts the cuts and the feeds back."""
    ids = seed(page, [{'name': 'SR MAIN', 'columns': 22,
                       'fields': chopped_fields(True)}])
    lid = ids['SR MAIN']
    before = read(page, lid)
    assert before['shape'] == [6] + [1] * 12 + [4], before
    hist = page.evaluate(HIST_LEN_JS)
    page.evaluate("""() => {
        const item = window.app._clearMenuForDock(
            { type: 'distro', distroId: 'dtk', title: 'SR' });
        if (!item || item.disabled) throw new Error(JSON.stringify(item));
        item.run();
    }""")
    page.wait_for_timeout(600)
    out = read(page, lid)
    assert out['splits'] == [], f'the clear kept the cuts: {out}'
    assert out['shape'] == [6, 6, 6, 4], out
    assert [s['name'] for s in out['plan']] == ['S1', 'S2', 'S3', 'S4'], out
    assert out['distro'] == {} and out['num'] == {}, out
    assert page.evaluate(HIST_LEN_JS) == hist + 1, 'not ONE history entry'
    assert page.evaluate(HIST_JS, 1) == ['Clear Distro']
    undo(page)
    assert read(page, lid) == before, 'one undo did not restore the cuts'


def test_uncleared_multis_keep_their_identity_under_the_new_index(page):
    """Clearing the twelve one-circuit multis between S1 and S14: S1 and
    S14 were not cleared, so they keep their typed name, distro, number and
    home-run length - re-keyed from index 14 to index 4 - while circuits
    7-18 fall back onto the grid as two unassigned multis."""
    fields = chopped_fields(True)
    fields['powerSocaNames'] = {'1': 'HEAD BOX', '14': 'TAIL BOX'}
    fields['powerSocaLengths'] = {'1': 25, '14': 50}
    ids = seed(page, [{'name': 'SR MAIN', 'columns': 22, 'fields': fields}])
    lid = ids['SR MAIN']
    before = read(page, lid)
    page.evaluate("""(id) => {
        window.app._clearMultis(
            Array.from({ length: 12 }, (_, i) => ({ layerId: id, soca: i + 2 })),
            'Clear Multi');
    }""", lid)
    page.wait_for_timeout(600)
    out = read(page, lid)
    assert out['splits'] == [], out
    assert out['shape'] == [6, 6, 6, 4], out
    assert out['names'] == {'1': 'HEAD BOX', '4': 'TAIL BOX'}, out
    assert out['lengths'] == {'1': 25, '4': 50}, out
    assert out['distro'] == {'1': 'dtk', '4': 'dtk'}, out
    assert out['num'] == {'1': 1, '4': 14}, out
    assert [(s['name'], s['distro']) for s in out['plan']] == [
        ('HEAD BOX', 'dtk'), ('S2', None), ('S3', None), ('TAIL BOX', 'dtk')], out
    assert page.evaluate(HIST_JS, 1) == ['Clear Multi']
    undo(page)
    assert read(page, lid) == before, 'one undo did not restore everything'


def test_a_cleared_run_welds_onto_its_one_kept_neighbour(page):
    """[1-2] kept on the box, [3-6] cleared: the cut after 2 goes, the kept
    multi holds the whole natural block [1-6] and re-deals its tails on
    its box (the stored set covered two circuits, not six)."""
    ids = seed(page, [{'name': 'W', 'columns': 6, 'fields': {
        'powerSocaSplits': [2],
        'powerSocaDistro': {'1': 'dtk', '2': 'dtk'},
        'powerSocaNumber': {'1': 1, '2': 2},
        'powerSocaPhasePos': {'1': [5, 6], '2': [1, 2, 3, 4]},
    }}])
    lid = ids['W']
    page.evaluate("""(id) => {
        window.app._clearMultis([{ layerId: id, soca: 2 }], 'Clear Multi');
    }""", lid)
    page.wait_for_timeout(600)
    out = read(page, lid)
    assert out['splits'] == [] and out['shape'] == [6], out
    assert out['distro'] == {'1': 'dtk'} and out['num'] == {'1': 1}, out
    assert out['pos'] == {}, (
        f'a multi that grew must shed its stored tail set: {out}')
    assert out['plan'][0]['tails'] == [1, 2, 3, 4, 5, 6], out


def test_a_cleared_run_flanked_by_kept_multis_keeps_both_cuts(page):
    """[1-2] on No. 1, [3] cleared, [4-6] on No. 2: forgetting either cut
    would weld two multis that were not cleared into one and lose the
    second's number - so the cleared circuit stays its own unassigned
    multi between them and both neighbours keep their identity."""
    ids = seed(page, [{'name': 'W', 'columns': 6, 'fields': {
        'powerSocaSplits': [2, 3],
        'powerSocaDistro': {'1': 'dtk', '2': 'dtk', '3': 'dtk'},
        'powerSocaNumber': {'1': 1, '2': 3, '3': 2},
    }}])
    lid = ids['W']
    page.evaluate("""(id) => {
        window.app._clearMultis([{ layerId: id, soca: 2 }], 'Clear Multi');
    }""", lid)
    page.wait_for_timeout(600)
    out = read(page, lid)
    assert out['splits'] == [2, 3] and out['shape'] == [2, 1, 3], out
    assert out['distro'] == {'1': 'dtk', '3': 'dtk'}, out
    assert out['num'] == {'1': 1, '3': 2}, out


def test_clear_circuit_chip_forgets_the_pip_drops_two_cuts(page):
    """The circuit chip's clear on a pip-drop product (S1[1-6] pinned,
    [7] on No. 2 tail 3, [8-12] the unassigned remainder): the two cuts
    around circuit 7 go with its seat, so 7-12 read as one natural multi
    again and the pinned S1 is untouched."""
    ids = seed(page, [{'name': 'W', 'columns': 12, 'fields': {
        'powerSocaSplits': [7],
        'powerSocaDistro': {'1': 'dtk', '2': 'dtk'},
        'powerSocaNumber': {'1': 1, '2': 2},
        'powerSocaPhasePos': {'2': [3]},
        # the remainder's typed name is on file; nothing on file is lost
        # when the cleared circuit welds back onto it
        'powerSocaNames': {'3': 'REST'},
    }}])
    lid = ids['W']
    before = read(page, lid)
    assert before['shape'] == [6, 1, 5], before
    hist = page.evaluate(HIST_LEN_JS)
    num7 = circuit_num(page, lid, 7)
    page.evaluate("""([id, n]) => {
        const l = window.app.project.layers.find(x => x.id === id);
        window.app._clearCircuitChip(l, 2, n);
    }""", [lid, num7])
    page.wait_for_timeout(600)
    out = read(page, lid)
    assert out['splits'] == [] and out['shape'] == [6, 6], out
    assert out['distro'] == {'1': 'dtk'} and out['num'] == {'1': 1}, out
    assert out['pos'] == {}, out
    assert out['names'] == {'2': 'REST'}, (
        f'the welded multi lost the name that was on file: {out}')
    assert page.evaluate(HIST_LEN_JS) == hist + 1
    assert page.evaluate(HIST_JS, 1) == ['Clear Circuit']
    undo(page)
    assert read(page, lid) == before


# ── 1b. a clear welds the unassigned leftovers too ────────────────────────

def test_clear_distro_welds_leftovers_that_were_already_unassigned(page):
    """The user's file as it was (2026-09-04): S1[1-6] on the distro and
    the twelve one-circuit leftovers S2..S13 ALREADY unassigned. A distro
    Clear clears S1 alone, and forgetting only S1's edges would leave the
    wall reading S1[1-6] S2[7] S3[8] ... S14[19-22] - "the numbering is
    all wrong". The clear forgets every cut between unassigned multis on
    the touched layer as well: [6, 6, 6, 4], S1..S4, nothing assigned; one
    'Clear Distro' entry; one undo puts every cut back."""
    fields = chopped_fields(False)
    fields['powerSocaDistro'] = {'1': 'dtk'}
    fields['powerSocaNumber'] = {'1': 1}
    ids = seed(page, [{'name': 'SR MAIN', 'columns': 22, 'fields': fields}])
    lid = ids['SR MAIN']
    before = read(page, lid)
    assert before['shape'] == [6] + [1] * 12 + [4], before
    assert before['distro'] == {'1': 'dtk'}, before
    hist = page.evaluate(HIST_LEN_JS)
    page.evaluate("""() => {
        const item = window.app._clearMenuForDock(
            { type: 'distro', distroId: 'dtk', title: 'SR' });
        if (!item || item.disabled) throw new Error(JSON.stringify(item));
        item.run();
    }""")
    page.wait_for_timeout(600)
    out = read(page, lid)
    assert out['splits'] == [], f'the clear kept the leftover cuts: {out}'
    assert out['shape'] == [6, 6, 6, 4], out
    assert [s['name'] for s in out['plan']] == ['S1', 'S2', 'S3', 'S4'], out
    assert [s['distro'] for s in out['plan']] == [None] * 4, out
    assert out['distro'] == {} and out['num'] == {}, out
    assert page.evaluate(HIST_LEN_JS) == hist + 1, 'not ONE history entry'
    assert page.evaluate(HIST_JS, 1) == ['Clear Distro']
    undo(page)
    assert read(page, lid) == before, 'one undo did not restore every cut'
    # ... and the user's next gesture on the healed wall: SR 2 dropped on
    # circuit 12 takes the whole natural box 7-12.
    page.evaluate("""() => window.app._clearMenuForDock(
        { type: 'distro', distroId: 'dtk', title: 'SR' }).run()""")
    page.wait_for_timeout(600)
    drop_slot(page, lid, 12, 'dtk', 2, 'SR 2')
    out = read(page, lid)
    assert out['shape'] == [6, 6, 6, 4] and out['splits'] == [], out
    assert out['plan'][1]['ords'] == [7, 8, 9, 10, 11, 12], out
    assert out['plan'][1]['name'] == 'SR2' and out['plan'][1]['distro'] == 'dtk', out


def test_leftovers_flanked_by_two_fed_multis_keep_their_cuts(page):
    """Cell one is [1-2] on No. 1, [3] unassigned, [4-6] on No. 2 - a
    leftover between two fed multis - and cell two is [7-8] on No. 3 with
    the leftovers [9] [10] [11-12] behind it. Clearing No. 3 welds cell
    two back onto the grid (its own edge cut AND the cuts between the
    leftovers), while cell one, which the clear never touched, keeps both
    cuts: forgetting either would weld a fed multi into its neighbour."""
    ids = seed(page, [{'name': 'W', 'columns': 12, 'fields': {
        'powerSocaSplits': [2, 3, 8, 9, 10],
        'powerSocaDistro': {'1': 'dtk', '3': 'dtk', '4': 'dtk'},
        'powerSocaNumber': {'1': 1, '3': 2, '4': 3},
    }}])
    lid = ids['W']
    before = read(page, lid)
    assert before['shape'] == [2, 1, 3, 2, 1, 1, 2], before
    page.evaluate("""(id) => {
        window.app._clearMultis([{ layerId: id, soca: 4 }], 'Clear Multi');
    }""", lid)
    page.wait_for_timeout(600)
    out = read(page, lid)
    assert out['splits'] == [2, 3], out
    assert out['shape'] == [2, 1, 3, 6], out
    assert out['distro'] == {'1': 'dtk', '3': 'dtk'}, out
    assert out['num'] == {'1': 1, '3': 2}, out
    assert [s['distro'] for s in out['plan']] == ['dtk', None, 'dtk', None], out
    undo(page)
    assert read(page, lid) == before


def test_a_cut_against_an_assigned_multi_stays(page):
    """[1-6] on No. 1 cleared, [7-9] unassigned, [10-12] on No. 2 named
    'FAR': the cut after 9 has a fed multi on one side, so it stays and
    FAR keeps its name, number and circuits under its new index - only an
    unassigned cut is programming nobody is using."""
    ids = seed(page, [{'name': 'W', 'columns': 12, 'fields': {
        'powerSocaSplits': [9],
        'powerSocaDistro': {'1': 'dtk', '3': 'dtk'},
        'powerSocaNumber': {'1': 1, '3': 2},
        'powerSocaNames': {'3': 'FAR'},
    }}])
    lid = ids['W']
    assert read(page, lid)['shape'] == [6, 3, 3]
    page.evaluate("""(id) => {
        window.app._clearMultis([{ layerId: id, soca: 1 }], 'Clear Multi');
    }""", lid)
    page.wait_for_timeout(600)
    out = read(page, lid)
    assert out['splits'] == [9] and out['shape'] == [6, 3, 3], out
    assert out['distro'] == {'3': 'dtk'} and out['num'] == {'3': 2}, out
    assert out['names'] == {'3': 'FAR'}, out
    assert [(s['name'], s['distro']) for s in out['plan']] == [
        ('S1', None), ('S2', None), ('FAR', 'dtk')], out


def test_clear_circuit_chip_welds_the_neighbouring_leftovers_too(page):
    """S1[1-6] pinned; then the pip-drop trail [7] unassigned, [8] on
    No. 2 tail 3, [9] unassigned, [10-12] unassigned. The chip's clear on
    circuit 8 forgets its own two cuts AND the cut after 9 between the
    two leftovers it now sits among, so 7-12 read as one natural multi;
    S1 is untouched. ONE 'Clear Circuit' entry; one undo restores all
    three cuts."""
    ids = seed(page, [{'name': 'W', 'columns': 12, 'fields': {
        'powerSocaSplits': [7, 8, 9],
        'powerSocaDistro': {'1': 'dtk', '3': 'dtk'},
        'powerSocaNumber': {'1': 1, '3': 2},
        'powerSocaPhasePos': {'3': [3]},
    }}])
    lid = ids['W']
    before = read(page, lid)
    assert before['shape'] == [6, 1, 1, 1, 3], before
    hist = page.evaluate(HIST_LEN_JS)
    num8 = circuit_num(page, lid, 8)
    page.evaluate("""([id, n]) => {
        const l = window.app.project.layers.find(x => x.id === id);
        window.app._clearCircuitChip(l, 3, n);
    }""", [lid, num8])
    page.wait_for_timeout(600)
    out = read(page, lid)
    assert out['splits'] == [] and out['shape'] == [6, 6], out
    assert out['distro'] == {'1': 'dtk'} and out['num'] == {'1': 1}, out
    assert out['pos'] == {}, out
    assert page.evaluate(HIST_LEN_JS) == hist + 1, 'not ONE history entry'
    assert page.evaluate(HIST_JS, 1) == ['Clear Circuit']
    undo(page)
    assert read(page, lid) == before, 'one undo did not restore every cut'


# ── 2. a multi dropped on a circuit takes the box's first circuits ────────
#
# Anchored at the START of the box cell (2026-09-05): the span runs from
# the cell's first circuit to the hovered one, so hovering the 6th of a
# six lights all six and hovering the 1st lights one.

def test_slot_drop_on_the_cells_last_circuit_takes_the_whole_box(page):
    """The user's gesture on his own wall, after the clear that kept the
    cuts: SR 2 dropped on circuit 12 takes 7-12 - anchored at the cell's
    first circuit, the one-circuit leftovers absorbed - as ONE 'Assign
    Multi Distro' entry, and the leftovers past 12 are not touched."""
    ids = seed(page, [{'name': 'SR MAIN', 'columns': 22,
                       'fields': chopped_fields(False)}])
    lid = ids['SR MAIN']
    before = read(page, lid)
    hist = page.evaluate(HIST_LEN_JS)
    drop_slot(page, lid, 12, 'dtk', 2, 'SR 2')
    out = read(page, lid)
    assert out['splits'] == [13, 14, 15, 16, 17], out
    assert out['shape'] == [6, 6, 1, 1, 1, 1, 1, 1, 4], out
    assert out['plan'][1]['ords'] == [7, 8, 9, 10, 11, 12], out
    assert out['plan'][1]['distro'] == 'dtk', out
    assert out['plan'][1]['number'] == 2 and out['plan'][1]['name'] == 'SR2', out
    assert out['plan'][1]['tails'] == [1, 2, 3, 4, 5, 6], out
    assert out['distro'] == {'2': 'dtk'} and out['num'] == {'2': 2}, out
    assert page.evaluate(HIST_LEN_JS) == hist + 1, 'not ONE history entry'
    assert page.evaluate(HIST_JS, 1) == ['Assign Multi Distro']
    assert 'took' not in page.evaluate(SAID_JS), 'no cap, no note'
    undo(page)
    assert read(page, lid) == before, 'one undo did not heal the drop'


def test_slot_drop_on_the_cells_first_circuit_takes_that_one_alone(page):
    """Hover the cell's 1st and that circuit alone: SR 2 dropped on circuit
    7 of the chopped wall takes [7] - the box reads 1/6 - and 8-12 stay
    the leftovers they were."""
    ids = seed(page, [{'name': 'SR MAIN', 'columns': 22,
                       'fields': chopped_fields(False)}])
    lid = ids['SR MAIN']
    drop_slot(page, lid, 7, 'dtk', 2, 'SR 2')
    out = read(page, lid)
    assert out['splits'] == CHOPPED, out
    assert out['plan'][1]['ords'] == [7] and out['plan'][1]['distro'] == 'dtk', out
    assert out['plan'][2]['ords'] == [8] and out['plan'][2]['distro'] is None, out
    assert out['distro'] == {'2': 'dtk'} and out['num'] == {'2': 2}, out
    assert 'took' not in page.evaluate(SAID_JS), 'no cap, no note'


def test_slot_drop_takes_what_the_box_has_free_and_says_so(page):
    """One circuit already pinned on box 2 (another screen's): SR 2 dropped
    on circuit 12 reaches for 7-12 and takes the FIRST five - 7-11 on the
    box's free tails 2-6 - and 12 stays behind as its own unassigned
    multi; the status bar says "took 5 of the 6". The incumbent keeps its
    tail."""
    ids = seed(page, [
        {'name': 'SR MAIN', 'columns': 22, 'fields': chopped_fields(False)},
        {'name': 'DJ', 'columns': 1, 'fields': {
            'powerSocaDistro': {'1': 'dtk'}, 'powerSocaNumber': {'1': 2}}},
    ])
    lid = ids['SR MAIN']
    drop_slot(page, lid, 12, 'dtk', 2, 'SR 2')
    out = read(page, lid)
    assert out['splits'] == [11, 13, 14, 15, 16, 17], out
    assert out['shape'] == [6, 5, 1, 1, 1, 1, 1, 1, 1, 4], out
    assert out['plan'][1]['ords'] == [7, 8, 9, 10, 11], out
    assert out['plan'][1]['tails'] == [2, 3, 4, 5, 6], out
    assert out['plan'][2]['ords'] == [12] and out['plan'][2]['distro'] is None, out
    assert out['distro'] == {'2': 'dtk'} and out['num'] == {'2': 2}, out
    said = page.evaluate(SAID_JS)
    assert 'had 5 free circuits' in said and 'took 5 of the 6 circuits' in said, said
    assert 'tail' not in said.lower(), said
    dj = read(page, ids['DJ'])
    assert dj['plan'][0]['tails'] == [1] and dj['pos'] == {'1': [1]}, (
        f"the incumbent's rendered tail was not held: {dj}")


def test_slot_drop_on_a_full_box_refuses_and_moves_nothing(page):
    """Six circuits pinned on box 2 already: the drop refuses with the
    counts, no cut happens for nothing, no history entry."""
    ids = seed(page, [
        {'name': 'SR MAIN', 'columns': 22, 'fields': chopped_fields(False)},
        {'name': 'FULL', 'columns': 6, 'fields': {
            'powerSocaDistro': {'1': 'dtk'}, 'powerSocaNumber': {'1': 2}}},
    ])
    lid = ids['SR MAIN']
    before = read(page, lid)
    hist = page.evaluate(HIST_LEN_JS)
    drop_slot(page, lid, 12, 'dtk', 2, 'SR 2')
    assert read(page, lid) == before, 'a refused drop mutated the wall'
    assert page.evaluate(HIST_LEN_JS) == hist
    said = page.evaluate(SAID_JS)
    assert 'SR 2 has no free circuits' in said and '6 circuits' in said, said


def test_head_circuits_on_another_box_are_skipped(page):
    """[1-2] pinned on No. 3, [3-6] unassigned: SR 2 dropped on the cell's
    4th circuit takes 3-4 - the head that is somebody's feed is never
    pulled off its box by a drop aimed elsewhere - and [1-2] keeps its
    pin. Dropped on circuit 2 (on No. 3 itself) it refuses: nothing
    lights, nothing moves, the tray says so."""
    ids = seed(page, [{'name': 'W', 'columns': 12, 'fields': {
        'powerSocaSplits': [2],
        'powerSocaDistro': {'1': 'dtk'}, 'powerSocaNumber': {'1': 3},
    }}])
    lid = ids['W']
    assert page.evaluate("""(id) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === id);
        app._circuitTailCache = null;
        const p = app._socaTakePlan(l, 2, 'dtk', 2);
        return { ok: p.ok, why: p.why, nums: p.nums };
    }""", lid) == {'ok': False, 'why': 'other-box', 'nums': []}
    before = read(page, lid)
    hist = page.evaluate(HIST_LEN_JS)
    drop_slot(page, lid, 2, 'dtk', 2, 'SR 2')
    assert read(page, lid) == before, 'a refused drop mutated the wall'
    assert page.evaluate(HIST_LEN_JS) == hist
    said = page.evaluate(SAID_JS)
    assert 'is already on ' in said and 'clear it first' in said and 'breakout' not in said, said

    page.evaluate(HUSH_JS)
    drop_slot(page, lid, 4, 'dtk', 2, 'SR 2')
    out = read(page, lid)
    assert out['splits'] == [2, 4] and out['shape'] == [2, 2, 2, 6], out
    assert out['plan'][1]['ords'] == [3, 4], out
    assert out['distro'] == {'1': 'dtk', '2': 'dtk'}, out
    assert out['num'] == {'1': 3, '2': 2}, out
    assert 'took' not in page.evaluate(SAID_JS)


def test_the_span_never_crosses_a_grid_line(page):
    """A drop in cell two starts at circuit 7, never at 1: SR 2 on circuit
    9 of a 12-circuit screen takes 7-9, and cell one is not touched."""
    ids = seed(page, [{'name': 'W', 'columns': 12}])
    lid = ids['W']
    drop_slot(page, lid, 9, 'dtk', 2, 'SR 2')
    out = read(page, lid)
    assert out['splits'] == [9] and out['shape'] == [6, 3, 3], out
    assert out['plan'][1]['ords'] == [7, 8, 9], out
    assert out['plan'][0]['distro'] is None and out['plan'][2]['distro'] is None, out
    assert out['distro'] == {'2': 'dtk'} and out['num'] == {'2': 2}, out


def test_slot_drop_on_a_whole_multi_takes_what_fits_too(page):
    """The ruling on the plain whole-multi drop: a 6-circuit multi dropped
    on a box with one pinned circuit (the drop on its 6th) takes the first
    five and leaves the sixth - it never lands seven legs on a six-tail
    fan as an overflow clash."""
    ids = seed(page, [
        {'name': 'W', 'columns': 6},
        {'name': 'DJ', 'columns': 1, 'fields': {
            'powerSocaDistro': {'1': 'dtk'}, 'powerSocaNumber': {'1': 2}}},
    ])
    lid = ids['W']
    drop_slot(page, lid, 6, 'dtk', 2, 'SR 2')
    out = read(page, lid)
    assert out['splits'] == [5] and out['shape'] == [5, 1], out
    assert out['distro'] == {'1': 'dtk'} and out['num'] == {'1': 2}, out
    assert out['plan'][0]['tails'] == [2, 3, 4, 5, 6], out
    said = page.evaluate(SAID_JS)
    assert 'took 5 of the 6 circuits' in said, said


def test_a_drop_on_a_later_circuit_takes_the_first_n_as_one_entry(page):
    """The old "from here on" split-drop is gone: SR 2 on the THIRD circuit
    of a 4-circuit multi takes its first three, the fourth stays as its
    own unassigned multi, and the typed name rides the taken part - under
    the one 'Assign Multi Distro' entry; one undo heals the cut and the
    assignment together."""
    ids = seed(page, [{'name': 'W', 'columns': 4, 'fields': {
        'powerSocaNames': {'1': 'HEAD'}}}])
    lid = ids['W']
    before = read(page, lid)
    hist = page.evaluate(HIST_LEN_JS)
    drop_slot(page, lid, 3, 'dtk', 2, 'SR 2')
    out = read(page, lid)
    assert out['splits'] == [3] and out['shape'] == [3, 1], out
    assert out['distro'] == {'1': 'dtk'} and out['num'] == {'1': 2}, out
    assert out['names'] == {'1': 'HEAD'}, out
    assert out['plan'][1]['distro'] is None, out
    assert page.evaluate(HIST_LEN_JS) == hist + 1
    assert page.evaluate(HIST_JS, 1) == ['Assign Multi Distro']
    undo(page)
    assert read(page, lid) == before


def test_a_redrop_onto_its_own_box_counts_at_what_stays(page):
    """[1-6] pinned on No. 2, rendered on tails 1-6; SR 2 dropped again on
    circuit 3 re-takes 1-3 and cuts 4-6 off as their own multi on the SAME
    box holding tails 4-6 - the multi counts at what stays, nothing on the
    fan moves, and the remainder keeps the box it was on."""
    ids = seed(page, [{'name': 'W', 'columns': 6, 'fields': {
        'powerSocaDistro': {'1': 'dtk'}, 'powerSocaNumber': {'1': 2}}}])
    lid = ids['W']
    assert read(page, lid)['plan'][0]['tails'] == [1, 2, 3, 4, 5, 6]
    page.evaluate(HUSH_JS)
    drop_slot(page, lid, 3, 'dtk', 2, 'SR 2')
    out = read(page, lid)
    assert out['splits'] == [3] and out['shape'] == [3, 3], out
    assert out['distro'] == {'1': 'dtk', '2': 'dtk'}, out
    assert out['num'] == {'1': 2, '2': 2}, out
    assert out['plan'][0]['tails'] == [1, 2, 3], out
    assert out['plan'][1]['tails'] == [4, 5, 6], out
    assert 'took' not in page.evaluate(SAID_JS)


def test_shared_box_still_holds_its_incumbents_tails(page):
    """The 2026 NCMF shape through the take rule: OFF's four circuits on
    box 2 (tails 1-4, rendered, unstored) and SR 2 dropped on CEN's
    eighth circuit: CEN [7-8] joins on tails 5-6 and OFF's rendered tails
    are stamped first, so nothing it may have cabled moves."""
    ids = seed(page, [
        {'name': 'OFF', 'columns': 4, 'fields': {
            'powerSocaDistro': {'1': 'dtk'}, 'powerSocaNumber': {'1': 2}}},
        {'name': 'CEN', 'columns': 8},
    ], distros=[{'id': 'dtk', 'name': 'C2'}])
    drop_slot(page, ids['CEN'], 8, 'dtk', 2, 'C2 2')
    cen = read(page, ids['CEN'])
    off = read(page, ids['OFF'])
    assert cen['splits'] == [] and cen['shape'] == [6, 2], cen
    assert cen['plan'][1]['tails'] == [5, 6], cen
    assert cen['distro'] == {'2': 'dtk'} and cen['num'] == {'2': 2}, cen
    assert off['pos'] == {'1': [1, 2, 3, 4]}, (
        f"the incumbent's rendered tails were not held: {off}")
    assert off['plan'][0]['tails'] == [1, 2, 3, 4], off
    labels = page.evaluate("""(id) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === id);
        app._circuitTailCache = null;
        return app.screenCircuits(l).map(c => app.getPowerCircuitLabel(l, c.num));
    }""", ids['CEN'])
    assert labels[6:] == ['C2-2-5', 'C2-2-6'], labels


def test_the_preview_lights_exactly_what_the_drop_takes(page):
    """What lights under the cursor is what lands: the hit-test's reach for
    a slot over the chopped wall's cell 7-12 is anchored at 7 - over
    circuit 12 it is 7-12 with six free, 7-11 with one pinned elsewhere,
    over circuit 7 it is [7], over circuit 10 it is 7-10, and nothing
    where the drop would refuse. Then the drop on 10 lands exactly the
    preview's circuits."""
    ids = seed(page, [
        {'name': 'SR MAIN', 'columns': 22, 'fields': chopped_fields(False)},
        {'name': 'DJ', 'columns': 1, 'fields': {
            'powerSocaDistro': {'1': 'dtk'}, 'powerSocaNumber': {'1': 3}}},
        {'name': 'FULL', 'columns': 6, 'fields': {
            'powerSocaDistro': {'1': 'dtk'}, 'powerSocaNumber': {'1': 4}}},
    ])
    lid = ids['SR MAIN']
    out = page.evaluate("""(id) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === id);
        app._circuitTailCache = null;
        const circuits = app.screenCircuits(l);
        const ord = new Map(circuits.map((c, i) => [c.num, i + 1]));
        const reach = (o, n) => {
            const p = app._socaTakePlan(l, o, 'dtk', n);
            return { ok: p.ok, nums: p.nums.map(x => ord.get(x)) };
        };
        return { free: reach(12, 2), one: reach(12, 3), full: reach(12, 4),
                 first: reach(7, 2), fourth: reach(10, 2) };
    }""", lid)
    assert out['free'] == {'ok': True, 'nums': [7, 8, 9, 10, 11, 12]}, out
    assert out['one'] == {'ok': True, 'nums': [7, 8, 9, 10, 11]}, out
    assert out['full'] == {'ok': False, 'nums': []}, out
    assert out['first'] == {'ok': True, 'nums': [7]}, out
    assert out['fourth'] == {'ok': True, 'nums': [7, 8, 9, 10]}, out
    drop_slot(page, lid, 10, 'dtk', 2, 'SR 2')
    got = read(page, lid)
    assert got['plan'][1]['ords'] == out['fourth']['nums'], (
        f'preview and drop disagree: {got}')
    assert got['plan'][1]['distro'] == 'dtk', got


# ── 3. one circuit comes off its box on its own ───────────────────────────

def chip_clear(page, distro_id, number, tail, title):
    """The circuit chip's right-click clear, through the same menu item the
    context menu arms. Returns the item (label, title) it ran."""
    item = page.evaluate("""([d, n, t, title]) => {
        const item = window.app._clearMenuForDock(
            { type: 'tail', distroId: d, number: n, tail: t, title });
        if (!item || item.disabled) throw new Error(JSON.stringify(item));
        item.run();
        return { label: item.label, title: item.title };
    }""", [distro_id, number, tail, title])
    page.wait_for_timeout(600)
    return item


def labels(page, layer_id):
    return page.evaluate("""(id) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === id);
        app._circuitTailCache = null;
        return app.screenCircuits(l)
            .map(c => app.getPowerCircuitLabel(l, c.num));
    }""", layer_id)


def tail_holder(page, distro_id, number, tail):
    return page.evaluate("""([d, n, t]) => {
        window.app._circuitTailCache = null;
        const h = window.app._dockTailHolder(d, n, t);
        return h ? { layer: h.layer.name, soca: h.rec.index,
                     circuit: h.circuit } : null;
    }""", [distro_id, number, tail])


def test_clear_the_sixth_circuit_leaves_the_other_five_where_they_were(page):
    """The user's own case: six circuits on SR 1, the chip on tail 6
    cleared. The box holds 1-5 on tails 1-5 (held, not re-dealt), circuit
    6 is its own unassigned multi, the menu said "Clear circuit", ONE
    'Clear Circuit' entry, and one undo puts the cut, the pin and the
    positions back."""
    ids = seed(page, [{'name': 'W', 'columns': 6, 'fields': {
        'powerSocaDistro': {'1': 'dtk'}, 'powerSocaNumber': {'1': 1},
        'powerSocaLengths': {'1': 25},
    }}])
    lid = ids['W']
    before = read(page, lid)
    assert before['shape'] == [6] and before['plan'][0]['tails'] == [1, 2, 3, 4, 5, 6]
    assert labels(page, lid) == ['SR1-1', 'SR1-2', 'SR1-3', 'SR1-4', 'SR1-5', 'SR1-6']
    hist = page.evaluate(HIST_LEN_JS)
    item = chip_clear(page, 'dtk', 1, 6, 'SR 1 circuit 6')
    assert item['label'] == 'Clear circuit SR1-6', item
    assert 'other 5 circuits stay where they are' in item['title'], item
    assert 'tail' not in item['title'].lower(), item
    out = read(page, lid)
    assert out['splits'] == [5] and out['shape'] == [5, 1], out
    assert out['distro'] == {'1': 'dtk'} and out['num'] == {'1': 1}, out
    assert out['pos'] == {'1': [1, 2, 3, 4, 5]}, out
    assert out['names'] == {} and out['lengths'] == {'1': 25}, out
    assert out['plan'][0]['tails'] == [1, 2, 3, 4, 5], out
    assert out['plan'][1]['ords'] == [6] and out['plan'][1]['distro'] is None, out
    assert labels(page, lid)[:5] == ['SR1-1', 'SR1-2', 'SR1-3', 'SR1-4', 'SR1-5']
    assert tail_holder(page, 'dtk', 1, 6) is None, 'tail 6 is not free'
    assert page.evaluate(HIST_LEN_JS) == hist + 1, 'not ONE history entry'
    assert page.evaluate(HIST_JS, 1) == ['Clear Circuit']
    undo(page)
    assert read(page, lid) == before, 'one undo did not put it back whole'


def test_clear_a_middle_circuit_keeps_the_tail_part_on_the_box(page):
    """The third of six cleared: head [1-2] keeps the identity on tails 1-2,
    the tail part [4-6] STAYS on the same box on tails 4-6 with its labels
    unchanged - SR1-1 SR1-2 SR1-4 SR1-5 SR1-6 - circuit 3 free as its own
    multi and tail 3 free on the box. The label override on the cleared
    circuit goes; the others' stay."""
    ids = seed(page, [{'name': 'W', 'columns': 6, 'fields': {
        'powerSocaDistro': {'1': 'dtk'}, 'powerSocaNumber': {'1': 1},
    }}])
    lid = ids['W']
    page.evaluate("""(id) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === id);
        const cs = app.screenCircuits(l);
        l.powerLabelOverrides = { [cs[2].num]: 'GONE', [cs[4].num]: 'KEPT' };
        app._circuitTailCache = null;
        app.updateLayers([l], true, 'Name Circuits');
    }""", lid)
    page.wait_for_timeout(400)
    before = read(page, lid)
    hist = page.evaluate(HIST_LEN_JS)
    chip_clear(page, 'dtk', 1, 3, 'SR 1 circuit 3')
    out = read(page, lid)
    assert out['splits'] == [2, 3] and out['shape'] == [2, 1, 3], out
    assert out['distro'] == {'1': 'dtk', '3': 'dtk'}, out
    assert out['num'] == {'1': 1, '3': 1}, out
    assert out['pos'] == {'1': [1, 2], '3': [4, 5, 6]}, out
    assert [s['tails'] for s in out['plan']] == [[1, 2], [1], [4, 5, 6]], out
    assert [s['distro'] for s in out['plan']] == ['dtk', None, 'dtk'], out
    lb = labels(page, lid)
    assert lb[:2] == ['SR1-1', 'SR1-2'] and lb[3:] == ['SR1-4', 'KEPT', 'SR1-6'], lb
    assert tail_holder(page, 'dtk', 1, 3) is None, 'tail 3 is not free'
    assert tail_holder(page, 'dtk', 1, 4)['circuit'] == circuit_num(page, lid, 4)
    overrides = page.evaluate("""(id) => window.app.project.layers
        .find(x => x.id === id).powerLabelOverrides""", lid)
    assert list(overrides.values()) == ['KEPT'], overrides
    assert page.evaluate(HIST_LEN_JS) == hist + 1, 'not ONE history entry'
    assert page.evaluate(HIST_JS, 1) == ['Clear Circuit']
    # ... and the box dropped back on the freed circuit puts it on its old
    # tail: the anchored take (2026-09-05) reaches 1-3 - 1-2 are already
    # on this box and are re-taken, 4-6 stay held - so the wall welds to
    # [1-3] [4-6] on SR 1 and the freed circuit deals into the one free
    # tail, 3.
    drop_slot(page, lid, 3, 'dtk', 1, 'SR 1')
    out = read(page, lid)
    assert out['shape'] == [3, 3] and out['splits'] == [3], out
    assert [s['tails'] for s in out['plan']] == [[1, 2, 3], [4, 5, 6]], out
    assert [s['distro'] for s in out['plan']] == ['dtk'] * 2, out
    assert labels(page, lid) == ['SR1-1', 'SR1-2', 'SR1-3', 'SR1-4', 'KEPT', 'SR1-6']
    assert page.evaluate(HIST_JS, 1) == ['Assign Multi Distro']
    undo(page)
    undo(page)
    assert read(page, lid) == before, 'two undos did not put it back whole'


def test_clear_the_first_circuit_hands_the_identity_to_the_rest(page):
    """The first of six cleared: the multi is the circuits that stay, so
    the part [2-6] keeps the typed name, distro, number and tails 2-6;
    circuit 1 is the leftover in front of it."""
    ids = seed(page, [{'name': 'W', 'columns': 6, 'fields': {
        'powerSocaDistro': {'1': 'dtk'}, 'powerSocaNumber': {'1': 1},
        'powerSocaNames': {'1': 'STAGE LEFT'}, 'powerSocaLengths': {'1': 25},
    }}])
    lid = ids['W']
    before = read(page, lid)
    chip_clear(page, 'dtk', 1, 1, 'SR 1 circuit 1')
    out = read(page, lid)
    assert out['splits'] == [1] and out['shape'] == [1, 5], out
    assert out['distro'] == {'2': 'dtk'} and out['num'] == {'2': 1}, out
    assert out['pos'] == {'2': [2, 3, 4, 5, 6]}, out
    assert out['names'] == {'2': 'STAGE LEFT'} and out['lengths'] == {'2': 25}, out
    assert [s['tails'] for s in out['plan']] == [[1], [2, 3, 4, 5, 6]], out
    assert labels(page, lid)[1:] == [
        'STAGE LEFT-2', 'STAGE LEFT-3', 'STAGE LEFT-4', 'STAGE LEFT-5',
        'STAGE LEFT-6']
    assert page.evaluate(HIST_JS, 1) == ['Clear Circuit']
    undo(page)
    assert read(page, lid) == before


def test_a_typed_name_rides_both_parts_so_no_label_changes(page):
    """The labels derive from the typed multi name, so the tail part
    carries it too: STAGE LEFT-4 must not turn into SR1-4 when circuit 3
    comes off. The home-run length stays with the head alone - one cable,
    counted once."""
    ids = seed(page, [{'name': 'W', 'columns': 6, 'fields': {
        'powerSocaDistro': {'1': 'dtk'}, 'powerSocaNumber': {'1': 1},
        'powerSocaNames': {'1': 'STAGE LEFT'}, 'powerSocaLengths': {'1': 25},
    }}])
    lid = ids['W']
    before = labels(page, lid)
    assert before == ['STAGE LEFT-%d' % i for i in range(1, 7)], before
    chip_clear(page, 'dtk', 1, 3, 'SR 1 circuit 3')
    out = read(page, lid)
    assert out['names'] == {'1': 'STAGE LEFT', '3': 'STAGE LEFT'}, out
    assert out['lengths'] == {'1': 25}, out
    lb = labels(page, lid)
    assert lb[:2] == before[:2] and lb[3:] == before[3:], lb


def test_clear_on_a_shared_box_leaves_the_other_screens_tails_alone(page):
    """OFF's four circuits on box 2 (tails 1-4, rendered, unstored) and
    CEN's two on tails 5-6. OFF's circuit 2 cleared: OFF reads [1] [3-4]
    on tails 1 and 3-4, CEN's rendered 5-6 are stamped first and do not
    move, tail 2 is free on the box."""
    ids = seed(page, [
        {'name': 'OFF', 'columns': 4, 'fields': {
            'powerSocaDistro': {'1': 'dtk'}, 'powerSocaNumber': {'1': 2}}},
        {'name': 'CEN', 'columns': 2, 'fields': {
            'powerSocaDistro': {'1': 'dtk'}, 'powerSocaNumber': {'1': 2}}},
    ])
    cen_before = read(page, ids['CEN'])
    assert cen_before['plan'][0]['tails'] == [5, 6] and cen_before['pos'] == {}
    hist = page.evaluate(HIST_LEN_JS)
    chip_clear(page, 'dtk', 2, 2, 'SR 2 circuit 2')
    off = read(page, ids['OFF'])
    cen = read(page, ids['CEN'])
    assert off['splits'] == [1, 2] and off['shape'] == [1, 1, 2], off
    assert off['distro'] == {'1': 'dtk', '3': 'dtk'}, off
    assert off['num'] == {'1': 2, '3': 2}, off
    assert off['pos'] == {'1': [1], '3': [3, 4]}, off
    assert [s['tails'] for s in off['plan']] == [[1], [1], [3, 4]], off
    assert cen['plan'][0]['tails'] == [5, 6], f"the other screen's tails moved: {cen}"
    assert cen['pos'] == {'1': [5, 6]}, f"the incumbent was not held: {cen}"
    assert tail_holder(page, 'dtk', 2, 2) is None, 'tail 2 is not free'
    assert page.evaluate(HIST_LEN_JS) == hist + 1, 'not ONE history entry'
    undo(page)
    assert read(page, ids['CEN']) == cen_before, 'undo did not release the stamp'


def test_the_chip_dragged_back_onto_the_tray_runs_the_same_clear(page):
    """The drag-back: a circuit chip dropped anywhere inside the tray
    (target kind 'dock') takes its one circuit off the box exactly as the
    right-click does - same result, same 'Clear Circuit' entry - and a
    free chip dropped there does nothing."""
    ids = seed(page, [{'name': 'W', 'columns': 6, 'fields': {
        'powerSocaDistro': {'1': 'dtk'}, 'powerSocaNumber': {'1': 1},
    }}])
    lid = ids['W']
    hist = page.evaluate(HIST_LEN_JS)
    page.evaluate("""() => window.app._dockPerformDrop(
        { type: 'tail', distroId: 'dtk', number: 1, tail: 6,
          title: 'SR 1 circuit 6' }, { kind: 'dock' })""")
    page.wait_for_timeout(600)
    out = read(page, lid)
    assert out['splits'] == [5] and out['shape'] == [5, 1], out
    assert out['pos'] == {'1': [1, 2, 3, 4, 5]}, out
    assert page.evaluate(HIST_LEN_JS) == hist + 1, 'not ONE history entry'
    assert page.evaluate(HIST_JS, 1) == ['Clear Circuit']
    page.evaluate("""() => window.app._dockPerformDrop(
        { type: 'tail', distroId: 'dtk', number: 1, tail: 6,
          title: 'SR 1 circuit 6' }, { kind: 'dock' })""")
    page.wait_for_timeout(400)
    assert read(page, lid) == out, 'a free chip dropped on the tray moved something'
    assert page.evaluate(HIST_LEN_JS) == hist + 1
    # The hit-test agrees: a tail drag over the tray IS the dock target.
    hit = page.evaluate("""() => {
        const dock = document.getElementById('hardware-dock');
        const r = dock.getBoundingClientRect();
        return window.app._dockHitTest(
            { clientX: r.left + r.width / 2, clientY: r.top + r.height / 2 },
            { payload: { type: 'tail', distroId: 'dtk', number: 1, tail: 1 } });
    }""")
    assert hit == {'kind': 'dock'}, hit
