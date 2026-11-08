"""The binder's Screen order "Top to bottom" on a show with canvases and
screen groups (1.7.0 fix, the owner: "this is set to top to bottom for
screens order and is not printing in that order").

The sheets ran in the layer ARRAY's order: the pull list keeps a position
per group and per loose screen in layer order, and the set sorted each
position on its own, so a group between two loose screens split the run
and nothing was ever sorted across it. Under every order each screen on
no beach is now one run:

  * 'layers' is the Screens panel read top to bottom as the Show views
    (Show Look, Data Flow, Power) draw it - each screen dealt to its SHOW
    canvas (show_canvas_id, else canvas_id), the canvases in their order,
    newest on top inside each, a group's rows gathered at its first
    member. The binder's maps are those views' pictures, so the order is
    the same whichever tab is open at export: Pixel Map deals by canvas_id
    and would move a screen with a show override.
  * A group printed as one stands where the group stands in that panel,
    its members' sheets in the panel's member order.
  * 'layers-up' is the same list read bottom to top.
  * The CONTENTS on the overview and the sheet numbers follow the plan.
  * Alphabetical, by port and by circuit sort a group in with the loose
    screens too (the owner, 2026-11-08), its sheets standing where its
    first member sorts.

Run locally:
    python -m pytest tests/test_binder_screen_order.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from conftest import open_app  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# Four canvases - Stage Right, Center, Stage Left, Upstage, in that order -
# and eight 4 x 3 walls added in this order:
#   SR COL     Stage Right, loose
#   US LEFT    Upstage, group UPSTAGE
#   US RIGHT   Upstage, group UPSTAGE
#   SL COL     Stage Left, loose
#   CTR RIGHT  Stage Right, shown on Center, group MIDDLE
#   CTR MAIN   Center, group MIDDLE
#   CTR LEFT   Stage Left, shown on Center, group MIDDLE
#   CTR IMAG   Center, loose
# so the layer array, the Pixel Map panel and the Show panel all differ,
# MIDDLE's members sit on three canvases and share one show canvas, and a
# group sits between two loose screens in the array.
SEED_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    let p = await j('GET', '/api/project');
    p.layers = []; p.groups = []; p.processors = []; p.distros = []; p.beaches = [];
    delete p.port_assignments; delete p.pullSheet; delete p.binder;
    delete p.groupNameDisplay;
    p.groupNameDisplayByView = {power: 'group', 'data-flow': 'screens'};
    p.canvases = p.canvases.slice(0, 1);
    p.canvases[0].name = 'Stage Right';
    p.active_canvas_id = p.canvases[0].id;
    await j('PUT', '/api/project', p);
    for (const name of ['Center', 'Stage Left', 'Upstage']) await j('POST', '/api/canvas', {name});
    const wall = {columns: 4, rows: 3, cabinet_width: 200, cabinet_height: 200,
                  powerVoltage: 208, powerAmperage: 20, panelWatts: 200,
                  powerFlowPattern: 'tl-v', powerOrganized: true, flowPattern: 'tl-h',
                  processorType: 'novastar-armor'};
    const names = ['SR COL', 'US LEFT', 'US RIGHT', 'SL COL', 'CTR RIGHT', 'CTR MAIN', 'CTR LEFT', 'CTR IMAG'];
    for (const name of names) await j('POST', '/api/layer/add', {...wall, name});
    p = await j('GET', '/api/project');
    const C = (n) => p.canvases.find(c => c.name === n).id;
    const L = (n) => p.layers.find(l => l.name === n);
    const put = (n, canvas, x, show) => {
        const l = L(n);
        l.canvas_id = C(canvas); l.offset_x = x; l.offset_y = 0;
        l.showOffsetX = x; l.showOffsetY = 0;
        l.show_canvas_id = show ? C(show) : null;
    };
    put('SR COL', 'Stage Right', 1000);
    put('US LEFT', 'Upstage', 0); put('US RIGHT', 'Upstage', 800);
    put('SL COL', 'Stage Left', 1000);
    put('CTR RIGHT', 'Stage Right', 0, 'Center');
    put('CTR MAIN', 'Center', 0);
    put('CTR LEFT', 'Stage Left', 0, 'Center');
    put('CTR IMAG', 'Center', 0);
    L('CTR IMAG').offset_y = 800; L('CTR IMAG').showOffsetY = 800;
    // MIDDLE shows side by side on Center: LEFT, MAIN, RIGHT
    L('CTR LEFT').showOffsetX = 0;
    L('CTR MAIN').offset_x = 800; L('CTR MAIN').showOffsetX = 800;
    L('CTR RIGHT').showOffsetX = 1600;
    for (const n of ['US LEFT', 'US RIGHT']) L(n).group_id = 'g-up';
    for (const n of ['CTR RIGHT', 'CTR MAIN', 'CTR LEFT']) L(n).group_id = 'g-mid';
    p.groups = [
        {id: 'g-up', name: 'UPSTAGE', layer_ids: [L('US LEFT').id, L('US RIGHT').id]},
        {id: 'g-mid', name: 'MIDDLE', layer_ids: [L('CTR RIGHT').id, L('CTR MAIN').id, L('CTR LEFT').id]},
    ];
    await j('PUT', '/api/project', p);
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('binder_screen_order_seed');
    app.renderLayers();
    window.canvasRenderer.render();
    app.resetHistory('Binder Screen Order Seed');
    return { layers: app.project.layers.map(l => l.name),
             canvases: app.project.canvases.map(c => c.name) };
}"""

# The Screens panel straight off the DOM, top to bottom, in BLOCKS: a group
# block (its header, then its member rows) or a loose screen's own block.
PANEL_JS = """() => {
    const app = window.app;
    const nameOf = new Map(app.project.layers.map(l => [String(l.id), l.name]));
    const groupName = new Map((app.project.groups || []).map(g => [String(g.id), g.name]));
    const blocks = [];
    const walk = (el) => {
        for (const c of el.children) {
            if (c.classList.contains('canvas-group')) {
                blocks.push({ canvas: c.querySelector('.canvas-name-input').value });
                walk(c.querySelector('.canvas-group-body'));
            } else if (c.classList.contains('screen-group')) {
                const body = c.querySelector('.screen-group-body');
                blocks.push({ group: groupName.get(String(c.dataset.groupId)),
                              screens: [...body.querySelectorAll('.layer-item')]
                                  .map(r => nameOf.get(String(r.dataset.layerId))) });
            } else if (c.classList.contains('layer-item')) {
                blocks.push({ group: null, screens: [nameOf.get(String(c.dataset.layerId))] });
            }
        }
    };
    walk(document.getElementById('layers-list'));
    return blocks;
}"""

OPTS = {'sheet': 'tabloid', 'palette': 'colour', 'sides': {'power': True, 'data': True},
        'scope': {'kind': 'show'}, 'cover': True, 'pull': False, 'hardware': False,
        'titleBlock': True}

# The plan under one screen order: every sheet [number, sheetTitle, kind,
# subject], and the overview's texts for its CONTENTS.
PLAN_JS = """([order, opts]) => {
    const app = window.app;
    app.setBinderField('screenOrder', order, 'Set Screen Order');
    const plan = app.planBinder(opts);
    return { plan: plan.map(p => [p.number, p.sheetTitle, p.kind, p.subject]),
             overview: app.renderBinderPage(opts, 0).texts };
}"""


def _subjects(plan):
    """The map sheets' subjects in print order, each named once: a group's
    sheet by the group's name, a screen's by its own."""
    out = []
    for _n, _t, kind, subject in plan:
        if kind in ('power', 'data') and subject not in out:
            out.append(subject)
    return out


def _expected(blocks, groups_as_one, up=False):
    """What the plan should run, from the panel's blocks: a group printed as
    one stands where its block stands, its sheet first, then its members'
    in the panel's order (bottom to top when `up`)."""
    out = []
    rows = [b for b in blocks if 'screens' in b]
    for b in (rows[::-1] if up else rows):
        screens = b['screens'][::-1] if up else b['screens']
        if b['group'] in groups_as_one:
            out.append(b['group'])
        out.extend(screens)
    return out


def _flat(blocks):
    out = []
    for b in blocks:
        if 'canvas' in b:
            out.append(f"[{b['canvas']}]")
        elif b['group']:
            out.append(f"{b['group']}: {', '.join(b['screens'])}")
        else:
            out.extend(b['screens'])
    return out


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    pg.route('**/api/native-dialog**', lambda r: r.fulfill(
        status=200, content_type='application/json', body='{"ok": false, "cancelled": true}'))
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    open_app(pg, e2e_server)
    seed = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(800)
    assert seed['canvases'] == ['Stage Right', 'Center', 'Stage Left', 'Upstage'], seed
    assert seed['layers'] == ['SR COL', 'US LEFT', 'US RIGHT', 'SL COL',
                              'CTR RIGHT', 'CTR MAIN', 'CTR LEFT', 'CTR IMAG'], seed
    yield pg, errors
    context.close()


def test_top_to_bottom_prints_the_screens_panel_order(page):
    pg, errors = page
    seen = {}
    try:
        for mode in ('show-look', 'pixel-map', 'power', 'data-flow'):
            pg.locator(f'[data-mode="{mode}"]').first.click()
            pg.wait_for_timeout(500)
            blocks = pg.evaluate(PANEL_JS)
            down = pg.evaluate(PLAN_JS, ['layers', OPTS])
            up = pg.evaluate(PLAN_JS, ['layers-up', OPTS])
            seen[mode] = (blocks, down, up)
            print(f'\n{mode} panel:', _flat(blocks))
            print(f'{mode} plan, layers:', _subjects(down['plan']))
            print(f'{mode} plan, layers-up:', _subjects(up['plan']))
    finally:
        pg.locator('[data-mode="pixel-map"]').first.click()
        pg.evaluate("() => window.app.setBinderField('screenOrder', 'alpha', 'Set Screen Order')")

    show_blocks = seen['show-look'][0]
    # the premise: the Show panel deals by show canvas and gathers MIDDLE
    # on Center under the loose CTR IMAG; Pixel Map deals by canvas_id and
    # splits MIDDLE over three canvases - the two panels differ
    assert _flat(show_blocks) == [
        '[Stage Right]', 'SR COL',
        '[Center]', 'CTR IMAG', 'MIDDLE: CTR LEFT, CTR MAIN, CTR RIGHT',
        '[Stage Left]', 'SL COL',
        '[Upstage]', 'UPSTAGE: US RIGHT, US LEFT',
    ], _flat(show_blocks)
    assert _flat(seen['pixel-map'][0]) != _flat(show_blocks), _flat(seen['pixel-map'][0])
    # both groups print as one on Power (Names by group), their members'
    # Data sheets by screen
    down = seen['show-look'][1]['plan']
    titles = [t for _n, t, _k, _s in down]
    assert 'MIDDLE · POWER · FRONT VIEW' in titles and 'UPSTAGE · POWER · FRONT VIEW' in titles, titles
    groups_as_one = {'MIDDLE', 'UPSTAGE'}

    want_down = _expected(show_blocks, groups_as_one)
    want_up = _expected(show_blocks, groups_as_one, up=True)
    assert want_down == ['SR COL', 'CTR IMAG', 'MIDDLE', 'CTR LEFT', 'CTR MAIN', 'CTR RIGHT',
                         'SL COL', 'UPSTAGE', 'US RIGHT', 'US LEFT'], want_down
    for mode, (_blocks, d, u) in seen.items():
        # the same in every tab: the Show panel's order, whatever is open
        assert _subjects(d['plan']) == want_down, (mode, _subjects(d['plan']))
        assert _subjects(u['plan']) == want_up, (mode, _subjects(u['plan']))
        # the same sheets either way, only reordered
        assert sorted(t for _n, t, _k, _s in d['plan']) == sorted(t for _n, t, _k, _s in u['plan']), mode
    # the group's sheets in full: Power by group, then each member's Data
    # sheet in the panel's member order
    maps = [t for _n, t, k, _s in down if k in ('power', 'data')]
    assert maps[maps.index('MIDDLE · POWER · FRONT VIEW'):][:4] == [
        'MIDDLE · POWER · FRONT VIEW', 'CTR LEFT · DATA · FRONT VIEW',
        'CTR MAIN · DATA · FRONT VIEW', 'CTR RIGHT · DATA · FRONT VIEW'], maps

    # the numbers run 2.1, 2.2 ... down the new order and the overview's
    # CONTENTS lists the sheets so, either way
    for out in (seen['show-look'][1], seen['show-look'][2]):
        plan = out['plan']
        screens = [n for n, _t, k, _s in plan if k not in ('overview',) and n.startswith('2.')]
        assert screens == [f'2.{i + 1}' for i in range(len(screens))], screens
        ov = out['overview']
        k = ov.index('CONTENTS')
        listed = [(ov[k + 3 + 2 * i], ov[k + 4 + 2 * i]) for i in range(len(plan))]
        assert listed == [(n, t) for n, t, _k, _s in plan], listed
    assert errors == [], errors


def test_the_other_orders_keep_every_sheet_and_each_group_together(page):
    """Alphabetical, by first port and by first circuit print the same
    sheets as Top to bottom, only in their own order, and a group printed
    as one keeps its sheets together: its Power sheet, then its members'
    Data sheets."""
    pg, errors = page
    try:
        base = pg.evaluate(PLAN_JS, ['layers', OPTS])['plan']
        for order in ('alpha', 'data', 'power'):
            plan = pg.evaluate(PLAN_JS, [order, OPTS])['plan']
            got = _subjects(plan)
            print(f'\n{order}:', got)
            assert sorted(t for _n, t, _k, _s in plan) == sorted(t for _n, t, _k, _s in base), order
            for group, members in (('MIDDLE', ['CTR LEFT', 'CTR MAIN', 'CTR RIGHT']),
                                   ('UPSTAGE', ['US LEFT', 'US RIGHT'])):
                at = got.index(group)
                assert sorted(got[at + 1:at + 1 + len(members)]) == members, (order, got)
            if order == 'alpha':
                # a group sorts in with the loose screens at its first
                # member's name (2026-11-08): CTR LEFT after CTR IMAG and
                # before SL COL, US LEFT after SR COL - not a run of its
                # own in array order
                assert got == ['CTR IMAG', 'MIDDLE', 'CTR LEFT', 'CTR MAIN', 'CTR RIGHT', 'SL COL', 'SR COL',
                               'UPSTAGE', 'US LEFT', 'US RIGHT'], got
    finally:
        pg.evaluate("() => window.app.setBinderField('screenOrder', 'alpha', 'Set Screen Order')")
    assert errors == [], errors
