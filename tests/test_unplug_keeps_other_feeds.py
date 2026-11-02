"""Unplugging a multi clears only the circuits it fed.

Owner (2026-11-02): "when i clear a breakout on the power it jumps them to
another breakout. it should just clear the ports."

His log showed the shape pinned here. One screen's eight circuits were fed
by a mix: circuit 1 alone off No. 3 (tail 4), circuits 2-6 off No. 5
(tails 1-5), circuit 7 alone off No. 5 (tail 6) and circuit 8 alone off
No. 4 (tail 4), with No. 3 and No. 4 also feeding two other screens.
Unplugging No. 4 used to forget the cut after circuit 7 as well, so the
No. 5 multi there grew onto the freed circuit and lost its tail. Then
unplugging No. 5 forgot the cut after circuit 1, so circuit 1's No. 3
multi grew over circuits 1-6 and dealt fresh tails: No. 3 now read as
feeding that whole box, on top of the tails another screen already had.

The ruling: an unplug (a multi from the tray, one circuit, or a whole
distro's Clear) takes off the circuits it fed and nothing else. Every
other multi, on every screen, keeps its distro, number, tails and the
cuts that keep it separate. The freed circuits just become unplugged;
cuts between two unplugged multis still go (the 2026-09-04 leftover rule),
so the freed circuits fall back onto the natural box.

Run locally (each session takes its own free port, so it runs beside
any other; LRD_E2E_PORT pins one):
    python -m pytest tests/test_unplug_keeps_other_feeds.py -v --browser chromium
"""

import copy
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


# Real server layers, so undo has something to restore. 110V x 6.25A
# against 100W panels puts a 5-tile tl-v column exactly on a circuit, so
# `columns` IS the circuit count (the test_power_take_rule.py builder).
# Every screen this module makes is named 'UM <name>'; each seed sweeps the
# previous test's screens first, and the module guard puts the server back.
SEED_JS = """async (spec) => {
    const app = window.app, r = window.canvasRenderer;
    await app._layerSavesSettled();
    let project = await (await fetch('/api/project')).json();
    project.layers = (project.layers || [])
        .filter(l => !String(l.name || '').startsWith('UM '));
    project.distros = spec.distros.map(d =>
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
                name: 'UM ' + s.name, columns: s.columns, rows: 5,
                cabinet_width: 128, cabinet_height: 128,
                offset_x: ox, offset_y: 2400,
            }),
        });
        ox += s.columns * 128 + 256;
    }
    project = await (await fetch('/api/project')).json();
    const ids = {};
    for (const s of spec.screens) {
        const l = project.layers.find(x => x.name === 'UM ' + s.name);
        ids[s.name] = l.id;
        Object.assign(l, {
            powerVoltage: '110', powerAmperage: '6.25', panelWatts: '100',
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
        app.dedupeProjectLayers('unplug_seed');
    }
    app._circuitTailCache = null;
    r.viewMode = 'power';
    r.zoom = 0.2; r.panX = 40; r.panY = -400;
    app.renderLayers();
    r.render();
    if (typeof app._flushPendingSaveState === 'function') {
        app._flushPendingSaveState();
    }
    app.resetHistory('Unplug Seed');
    const counts = {};
    for (const s of spec.screens) {
        const l = app.project.layers.find(x => x.id === ids[s.name]);
        counts[s.name] = app.screenCircuits(l).length;
    }
    return { ids, counts };
}"""

# One row per multi as the plan reads it (circuit ordinals, distro,
# number, tails) plus the raw stores.
READ_JS = """(layerId) => {
    const app = window.app;
    const l = app.project.layers.find(x => x.id === layerId);
    app._circuitTailCache = null;
    const circuits = app.screenCircuits(l);
    const ord = new Map(circuits.map((c, i) => [c.num, i + 1]));
    const plan = app.getSocaPlan(l).map(s => ({
        ords: s.legs.map(g => ord.get(g.circuit)),
        tails: s.legs.map(g => g.leg),
        distro: s.distroId || null,
        number: s.distroId ? s.number : null,
    }));
    return {
        plan,
        splits: l.powerSocaSplits || [],
        distro: l.powerSocaDistro || {},
        num: l.powerSocaNumber || {},
        pos: l.powerSocaPhasePos || {},
    };
}"""

HIST_JS = "(n) => window.app.history.map(h => h.action).slice(-n)"
HIST_LEN_JS = "() => window.app.history.length"

MENU_JS = """(payload) => {
    const item = window.app._clearMenuForDock(payload);
    if (!item || item.disabled) throw new Error(JSON.stringify(item));
    item.run();
    return item.label;
}"""


def seed(page, screens, distros):
    st = page.evaluate(SEED_JS, {'screens': screens, 'distros': distros})
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


def menu(page, payload):
    label = page.evaluate(MENU_JS, payload)
    page.wait_for_timeout(600)
    return label


DISTRO = [{'id': 'dum', 'name': 'S'}]

# The owner's shape: the main screen's eight circuits on four multis,
# [1] No. 3 tail 4, [2-6] No. 5 tails 1-5, [7] No. 5 tail 6, [8] No. 4
# tail 4; a left screen on No. 3 tails 1-3, a right screen on No. 4
# tails 1-3.
MAIN_FIELDS = {
    'powerSocaSplits': [1, 7],
    'powerSocaDistro': {'1': 'dum', '2': 'dum', '3': 'dum', '4': 'dum'},
    'powerSocaNumber': {'1': 3, '2': 5, '3': 5, '4': 4},
    'powerSocaPhasePos': {'1': [4], '2': [1, 2, 3, 4, 5], '3': [6],
                          '4': [4]},
}


def side_fields(number):
    return {
        'powerSocaDistro': {'1': 'dum'},
        'powerSocaNumber': {'1': number},
        'powerSocaPhasePos': {'1': [1, 2, 3]},
    }


def seed_show(page, main_fields=None, distros=None):
    return seed(page, [
        {'name': 'MAIN', 'columns': 8,
         'fields': copy.deepcopy(main_fields or MAIN_FIELDS)},
        {'name': 'LEFT', 'columns': 3, 'fields': side_fields(3)},
        {'name': 'RIGHT', 'columns': 3, 'fields': side_fields(4)},
    ], distros or DISTRO)


MAIN_PLAN = [
    {'ords': [1], 'tails': [4], 'distro': 'dum', 'number': 3},
    {'ords': [2, 3, 4, 5, 6], 'tails': [1, 2, 3, 4, 5],
     'distro': 'dum', 'number': 5},
    {'ords': [7], 'tails': [6], 'distro': 'dum', 'number': 5},
    {'ords': [8], 'tails': [4], 'distro': 'dum', 'number': 4},
]
SIDE_TAILS = [1, 2, 3]


def unplugged(ords):
    return {'ords': ords, 'tails': [], 'distro': None, 'number': None}


def plan_view(out):
    """The plan with an unplugged multi's dealt tails blanked: an unplugged
    multi renders placeholder tails nobody holds."""
    return [dict(p, tails=[]) if p['distro'] is None else p
            for p in out['plan']]


def test_the_seed_reads_as_the_owner_saw_it(page):
    ids = seed_show(page)
    out = read(page, ids['MAIN'])
    assert out['plan'] == MAIN_PLAN, out
    assert read(page, ids['LEFT'])['plan'][0]['tails'] == SIDE_TAILS
    assert read(page, ids['RIGHT'])['plan'][0]['tails'] == SIDE_TAILS


def test_unplug_multi_keeps_every_other_feed_step_by_step(page):
    """The owner's two gestures in order: Unplug No. 4, then Unplug No. 5.
    Each takes off only its own circuits; circuit 1 stays on No. 3 tail 4
    and the left screen keeps No. 3 tails 1-3."""
    ids = seed_show(page)
    main, left, right = ids['MAIN'], ids['LEFT'], ids['RIGHT']
    before = read(page, main)
    left_before = read(page, left)

    hist = page.evaluate(HIST_LEN_JS)
    assert menu(page, {'type': 'slot', 'distroId': 'dum', 'number': 4,
                       'title': 'S 4'}) == 'Unplug S 4'
    out = read(page, main)
    assert out['splits'] == [1, 7], (
        f'unplugging No. 4 forgot the cut that keeps No. 5 separate: {out}')
    assert out['distro'] == {'1': 'dum', '2': 'dum', '3': 'dum'}, out
    assert out['num'] == {'1': 3, '2': 5, '3': 5}, out
    assert out['pos'] == {'1': [4], '2': [1, 2, 3, 4, 5], '3': [6]}, out
    assert plan_view(out) == MAIN_PLAN[:3] + [unplugged([8])], out
    assert read(page, right)['distro'] == {}, 'No. 4 still feeds RIGHT'
    assert read(page, left) == left_before
    assert page.evaluate(HIST_LEN_JS) == hist + 1
    assert page.evaluate(HIST_JS, 1) == ['Unplug Multi']

    assert menu(page, {'type': 'slot', 'distroId': 'dum', 'number': 5,
                       'title': 'S 5'}) == 'Unplug S 5'
    out = read(page, main)
    # the cut after 1 keeps circuit 1 on its own; the cut after 7 sat
    # between two unplugged multis, so it goes (the leftover rule)
    assert out['splits'] == [1], (
        f'unplugging No. 5 forgot the cut after circuit 1: {out}')
    assert out['distro'] == {'1': 'dum'} and out['num'] == {'1': 3}, out
    assert out['pos'] == {'1': [4]}, (
        f'circuit 1 lost its tail on No. 3: {out}')
    assert plan_view(out) == [MAIN_PLAN[0], unplugged([2, 3, 4, 5, 6]),
                              unplugged([7, 8])], out
    assert read(page, left) == left_before, 'LEFT moved'

    undo(page)
    undo(page)
    assert read(page, main) == before, 'two undos did not restore the wall'


@pytest.mark.parametrize('number, expect', [
    # No. 3: circuit 1 goes, No. 5's [2-6] keeps its own cut and tails
    (3, {'splits': [1, 7], 'distro': {'2': 'dum', '3': 'dum', '4': 'dum'},
         'num': {'2': 5, '3': 5, '4': 4},
         'pos': {'2': [1, 2, 3, 4, 5], '3': [6], '4': [4]},
         'plan': [unplugged([1])] + MAIN_PLAN[1:]}),
    # No. 4: circuit 8 goes, No. 5's [7] keeps its cut and tail 6
    (4, {'splits': [1, 7], 'distro': {'1': 'dum', '2': 'dum', '3': 'dum'},
         'num': {'1': 3, '2': 5, '3': 5},
         'pos': {'1': [4], '2': [1, 2, 3, 4, 5], '3': [6]},
         'plan': MAIN_PLAN[:3] + [unplugged([8])]}),
    # No. 5: circuits 2-7 go, circuit 1 and circuit 8 keep their feeds
    (5, {'splits': [1, 7], 'distro': {'1': 'dum', '4': 'dum'},
         'num': {'1': 3, '4': 4}, 'pos': {'1': [4], '4': [4]},
         'plan': [MAIN_PLAN[0], unplugged([2, 3, 4, 5, 6]),
                  unplugged([7]), MAIN_PLAN[3]]}),
])
def test_unplug_any_one_multi_leaves_the_rest_alone(page, number, expect):
    ids = seed_show(page)
    main = ids['MAIN']
    before = read(page, main)
    others = {k: read(page, v) for k, v in ids.items() if k != 'MAIN'}
    menu(page, {'type': 'slot', 'distroId': 'dum', 'number': number,
                'title': f'S {number}'})
    out = read(page, main)
    got = {'splits': out['splits'], 'distro': out['distro'],
           'num': out['num'], 'pos': out['pos'], 'plan': plan_view(out)}
    assert got == expect, out
    for name, was in others.items():
        now = read(page, ids[name])
        if was['num'].get('1') == number:
            assert now['distro'] == {} and now['pos'] == {}, (name, now)
        else:
            assert now == was, f'{name} moved: {now}'
    undo(page)
    assert read(page, main) == before


@pytest.mark.parametrize('number, tail, expect', [
    # circuit 1 alone on No. 3 tail 4: the cut after 1 keeps No. 5 [2-6]
    (3, 4, {'splits': [1, 7], 'pos': {'2': [1, 2, 3, 4, 5], '3': [6],
                                      '4': [4]},
            'plan': [unplugged([1])] + MAIN_PLAN[1:]}),
    # circuit 7 alone on No. 5 tail 6: the cut after 7 keeps No. 4 [8]
    (5, 6, {'splits': [1, 7], 'pos': {'1': [4], '2': [1, 2, 3, 4, 5],
                                      '4': [4]},
            'plan': MAIN_PLAN[:2] + [unplugged([7]), MAIN_PLAN[3]]}),
    # circuit 8 alone on No. 4 tail 4: the cut after 7 keeps No. 5 [7]
    (4, 4, {'splits': [1, 7], 'pos': {'1': [4], '2': [1, 2, 3, 4, 5],
                                      '3': [6]},
            'plan': MAIN_PLAN[:3] + [unplugged([8])]}),
])
def test_unplug_one_circuit_leaves_the_rest_alone(page, number, tail, expect):
    ids = seed_show(page)
    main = ids['MAIN']
    before = read(page, main)
    others = {k: read(page, v) for k, v in ids.items() if k != 'MAIN'}
    hist = page.evaluate(HIST_LEN_JS)
    label = menu(page, {'type': 'tail', 'distroId': 'dum', 'number': number,
                        'tail': tail, 'title': f'S {number}-{tail}'})
    assert label.startswith('Unplug circuit'), label
    out = read(page, main)
    got = {'splits': out['splits'], 'pos': out['pos'],
           'plan': plan_view(out)}
    assert got == expect, out
    for name, was in others.items():
        assert read(page, ids[name]) == was, f'{name} moved'
    assert page.evaluate(HIST_LEN_JS) == hist + 1
    assert page.evaluate(HIST_JS, 1) == ['Unplug Circuit']
    undo(page)
    assert read(page, main) == before


def test_clear_distro_leaves_the_other_distros_feeds_alone(page):
    """Circuit 8 on a second distro: Clear on that distro takes circuit 8
    off and leaves the first distro's No. 5 [7] with its cut and tail."""
    fields = copy.deepcopy(MAIN_FIELDS)
    fields['powerSocaDistro']['4'] = 'dum2'
    fields['powerSocaNumber']['4'] = 1
    ids = seed_show(page, fields,
                    DISTRO + [{'id': 'dum2', 'name': 'T'}])
    main = ids['MAIN']
    before = read(page, main)
    others = {k: read(page, v) for k, v in ids.items() if k != 'MAIN'}
    assert menu(page, {'type': 'distro', 'distroId': 'dum2',
                       'title': 'T'}) == 'Clear T'
    out = read(page, main)
    assert out['splits'] == [1, 7], out
    assert out['pos'] == {'1': [4], '2': [1, 2, 3, 4, 5], '3': [6]}, out
    assert plan_view(out) == MAIN_PLAN[:3] + [unplugged([8])], out
    for name, was in others.items():
        assert read(page, ids[name]) == was, f'{name} moved'
    assert page.evaluate(HIST_JS, 1) == ['Clear Distro']
    undo(page)
    assert read(page, main) == before
