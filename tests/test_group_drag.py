"""Dragging a group in the Screens list (1.7.0).

Owner's report: "Also can't click and drag groups into other canvases or
change group layer order in side panel."

What was there: a group's row carried ▲▼ buttons (moveGroupWithinCanvas),
and those worked in every view, but the row itself could not be dragged at
all, so a group could neither be dropped on another canvas nor dragged up
and down its canvas. One real fault in the buttons: the canvas they stepped
in was read off the group's newest member, so once a Show Look move had put
that member on a later canvas than the row, the arrows stepped (and greyed
out) against the other canvas's rows.

Now (app-screen-groups.js, app-canvas-ui.js, app-layers-panel.js):
- The group's row drags. Dropped on another canvas's block it moves the
  whole group there (moveGroupToCanvas), through the same routes a screen
  takes, so Show Look / Data / Power move the Show Look canvas and Pixel Map
  / Cabinet ID the canvas. Alt/Option copies it where a screen copies. One
  undo step; the group stays a group.
- Dropped on a row of its own canvas it lands above or below that row (the
  midpoint rule), in the same units the arrows step through. One undo step.
- A loose screen dropped on a group's row lands above or below the group.
- A locked group stays put and says why, as a locked screen does.
- Nothing changes for a drop on the group's own canvas header.

Real mouse drags (Playwright's drag runs the HTML drag events in Chromium).

Run locally:
    python -m pytest tests/test_group_drag.py -v -n 3 --dist loadfile
"""

import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'src'))
sys.path.insert(0, HERE)

import app as app_module  # noqa: E402,F401
from conftest import settled  # noqa: E402

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


def _src(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as fh:
        return fh.read()


def test_the_wiring_is_loaded():
    main_js = _src('src', 'static', 'js', 'main.js')
    for name in ('app-screen-groups.js', 'app-canvas-ui.js', 'app-layers-panel.js'):
        assert f"import './{name}';" in main_js, name
    groups = _src('src', 'static', 'js', 'app-screen-groups.js')
    assert "releaseDrag = holdDragOff(nameInput, row);" in groups
    assert "this.moveGroupToCanvas(groupId, canvas.id, mode);" in _src(
        'src', 'static', 'js', 'app-canvas-ui.js')
    assert "this._groupDragOverRow(e, layer, layerDiv);" in _src(
        'src', 'static', 'js', 'app-layers-panel.js')


# Canvas C1 holds, top to bottom: L2, the group G (B over A), L1. C2 holds M.
SEED_JS = """async (opts) => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = []; proj.beaches = [];
    delete proj.port_assignments; delete proj.pullSheet;
    proj.canvases = proj.canvases.slice(0, 1);
    proj.canvases[0].name = 'C1';
    proj.active_canvas_id = proj.canvases[0].id;
    await j('PUT', '/api/project', proj);
    const c1 = proj.canvases[0].id;
    const c2 = (await j('POST', '/api/canvas', {name: 'C2'})).active_canvas_id;
    const add = async (name, cid, x) => (await j('POST', '/api/layer/add', {name, columns: 2, rows: 1,
        cabinet_width: 100, cabinet_height: 100, offset_x: x, offset_y: 0, canvas_id: cid})).id;
    const ids = {};
    ids.L1 = await add('L1', c1, 0);
    ids.A = await add('A', c1, 300);
    ids.B = await add('B', c1, 600);
    ids.L2 = await add('L2', c1, 900);
    ids.M = await add('M', c2, 0);
    await j('PUT', `/api/canvas/${c1}/active`);
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('group_drag_seed');
    app.setSelectedLayersByIds([ids.A, ids.B], ids.A);
    await app.groupSelectedLayers();
    const gid = app.project.groups[0].id;
    if (opts && opts.expand) app.setGroupExpanded(gid, true);
    if (opts && opts.lock) await app.toggleGroupLock(gid);
    app.selectLayer(app.project.layers.find(l => l.id === ids.L1));
    app.renderLayers();
    window.canvasRenderer.render();
    if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
    app.resetHistory('Group Drag Seed');
    window.__toasts = [];
    if (!app.__toastSpy) {
        app.__toastSpy = true;
        const orig = app._toast;
        app._toast = function (msg, isError, ms) {
            window.__toasts.push(String(msg));
            return orig.call(this, msg, isError, ms);
        };
    }
    return {ids, gid, c1, c2};
}"""

# The list as drawn: [canvas, [row, ...]] with a group as G[members].
LIST_JS = """() => [...document.querySelectorAll('#layers-list .canvas-group')].map(cg => [
    cg.querySelector('.canvas-name-input').value,
    [...cg.querySelector('.canvas-group-body').children].map(el =>
        el.classList.contains('screen-group')
            ? 'G[' + [...el.querySelectorAll('.layer-item .layer-name-input')].map(i => i.value).join(',') + ']'
            : el.querySelector('.layer-name-input').value)])"""

# Every screen's canvases and group, on the server and in the client.
STATE_JS = """async () => {
    const pick = (p) => ({
        layers: Object.fromEntries((p.layers || []).map(l => [l.name,
            [l.canvas_id, l.show_canvas_id || null, l.group_id || null]])),
        groups: (p.groups || []).map(g => [g.id, g.name, [...g.layer_ids]]),
        order: (p.layers || []).map(l => l.name),
    });
    const server = await (await fetch('/api/project')).json();
    return {server: pick(server), client: pick(window.app.project)};
}"""


def _cancelled(route):
    route.fulfill(status=200, content_type='application/json',
                  body=json.dumps({'ok': False, 'cancelled': True}))


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 1100})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    # No real Windows dialog may open on the owner's desktop.
    for path in ('save-file', 'open-file', 'select-directory'):
        pg.route(f'**/api/native-dialog/{path}', _cancelled)
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    yield pg, errors
    context.close()


def _seed(pg, mode='pixel-map', **opts):
    pg.locator(f'.view-tab[data-mode="{mode}"]').first.click()
    pg.wait_for_timeout(250)
    seed = pg.evaluate(SEED_JS, opts)
    want = [['C1', ['L2', 'G[B,A]', 'L1']], ['C2', ['M']]]
    got = settled(pg, lambda: pg.evaluate(LIST_JS), lambda v: v == want)
    assert got == want, got
    return seed


def _group_row(gid):
    return f'#layers-list .screen-group[data-group-id="{gid}"] .screen-group-row'


def _group_name(gid):
    return f'#layers-list .screen-group[data-group-id="{gid}"] .screen-group-name-input'


def _layer_row(lid):
    return f'#layers-list .layer-item[data-layer-id="{lid}"]'


def _canvas_header(cid):
    return f'#layers-list .canvas-group[data-canvas-id="{cid}"] .canvas-group-header'


def _drag(pg, src, dst, half='middle'):
    target = pg.locator(dst)
    box = target.bounding_box()
    y = box['height'] * {'top': 0.2, 'bottom': 0.8, 'middle': 0.5}[half]
    pg.locator(src).drag_to(target, target_position={'x': box['width'] / 2, 'y': y})
    pg.wait_for_timeout(150)


def _history(pg):
    return pg.evaluate("() => window.app.history.map(h => h.action)")


def _expect_list(pg, want):
    got = settled(pg, lambda: pg.evaluate(LIST_JS), lambda v: v == want)
    assert got == want, f'the list shows {got}, wanted {want}'


def _undo(pg):
    pg.evaluate("() => window.app.undo()")
    pg.wait_for_timeout(300)


SEEDED = [['C1', ['L2', 'G[B,A]', 'L1']], ['C2', ['M']]]


# ── the arrows ────────────────────────────────────────────────────────────

@pytest.mark.parametrize('mode', ['pixel-map', 'show-look', 'cabinet-id', 'data-flow', 'power'])
def test_the_arrows_move_the_group_in_every_view(page, mode):
    pg, errors = page
    seed = _seed(pg, mode)
    gid = seed['gid']
    up = pg.locator(f'#layers-list .screen-group[data-group-id="{gid}"] .screen-group-move-up')
    assert up.is_enabled()
    up.click()
    _expect_list(pg, [['C1', ['G[B,A]', 'L2', 'L1']], ['C2', ['M']]])
    assert _history(pg) == ['Group Drag Seed', 'Reorder Group']
    assert pg.locator(f'#layers-list .screen-group[data-group-id="{gid}"] .screen-group-move-up').is_disabled()
    pg.locator(f'#layers-list .screen-group[data-group-id="{gid}"] .screen-group-move-down').click()
    _expect_list(pg, SEEDED)
    pg.locator(f'#layers-list .screen-group[data-group-id="{gid}"] .screen-group-move-down').click()
    _expect_list(pg, [['C1', ['L2', 'L1', 'G[B,A]']], ['C2', ['M']]])
    assert pg.locator(f'#layers-list .screen-group[data-group-id="{gid}"] .screen-group-move-down').is_disabled()
    _undo(pg)
    _expect_list(pg, SEEDED)
    assert errors == []


def test_the_arrows_step_in_the_canvas_the_row_is_drawn_in(page):
    """Show Look: B, the group's newest member, alone on C2. The row stays on
    C1 with A, and its arrows step among C1's rows; they used to step (and
    grey out) against C2's."""
    pg, errors = page
    seed = _seed(pg, 'show-look')
    ids, gid = seed['ids'], seed['gid']
    pg.evaluate("([lid, cid]) => window.app.moveLayerShowCanvas(lid, cid)", [ids['B'], seed['c2']])
    _expect_list(pg, [['C1', ['L2', 'G[A]', 'L1']], ['C2', ['M', 'B']]])
    down = pg.locator(f'#layers-list .screen-group[data-group-id="{gid}"] .screen-group-move-down')
    assert down.is_enabled(), 'the row has L1 under it on its own canvas'
    down.click()
    got = settled(pg, lambda: pg.evaluate(LIST_JS)[0], lambda v: v == ['C1', ['L2', 'L1', 'G[A]']])
    assert got == ['C1', ['L2', 'L1', 'G[A]']], got
    assert errors == []


# ── onto another canvas ───────────────────────────────────────────────────

def test_a_group_dragged_onto_another_canvas_moves_whole_pixel_map(page):
    pg, errors = page
    seed = _seed(pg, 'pixel-map')
    gid, c1, c2 = seed['gid'], seed['c1'], seed['c2']
    before = pg.evaluate(STATE_JS)
    _drag(pg, _group_row(gid), _canvas_header(c2))
    _expect_list(pg, [['C1', ['L2', 'L1']], ['C2', ['M', 'G[B,A]']]])
    after = settled(pg, lambda: pg.evaluate(STATE_JS),
                    lambda v: v['server']['layers']['A'][0] == c2 and v['server']['layers']['B'][0] == c2)
    for side in ('server', 'client'):
        lay = after[side]['layers']
        assert lay['A'][0] == c2 and lay['B'][0] == c2, (side, lay)
        assert lay['A'][2] == gid and lay['B'][2] == gid, (side, lay)
        assert lay['L1'][0] == c1 and lay['L2'][0] == c1 and lay['M'][0] == c2, (side, lay)
        assert after[side]['groups'] == before[side]['groups'], (side, after[side]['groups'])
    assert _history(pg) == ['Group Drag Seed', 'Move 2 Layers to Canvas']
    _undo(pg)
    _expect_list(pg, SEEDED)
    back = settled(pg, lambda: pg.evaluate(STATE_JS), lambda v: v['server'] == before['server'])
    assert back['server'] == before['server']
    assert back['client'] == before['client']
    assert errors == []


@pytest.mark.parametrize('mode', ['show-look', 'power'])
def test_a_group_dragged_onto_another_canvas_moves_whole_show_look(page, mode):
    pg, errors = page
    seed = _seed(pg, mode)
    gid, c1, c2 = seed['gid'], seed['c1'], seed['c2']
    before = pg.evaluate(STATE_JS)
    _drag(pg, _group_row(gid), _canvas_header(c2))
    _expect_list(pg, [['C1', ['L2', 'L1']], ['C2', ['M', 'G[B,A]']]])
    after = settled(pg, lambda: pg.evaluate(STATE_JS),
                    lambda v: v['server']['layers']['B'][1] == c2)
    for side in ('server', 'client'):
        lay = after[side]['layers']
        # The Show Look canvas moved; the Pixel Map canvas did not.
        assert lay['A'][:3] == [c1, c2, gid] and lay['B'][:3] == [c1, c2, gid], (side, lay)
        assert after[side]['groups'] == before[side]['groups'], (side, after[side]['groups'])
    assert _history(pg) == ['Group Drag Seed', 'Move 2 Layers (Show Look) to Canvas']
    _undo(pg)
    _expect_list(pg, SEEDED)
    back = settled(pg, lambda: pg.evaluate(STATE_JS), lambda v: v['server'] == before['server'])
    assert back['server'] == before['server']
    assert errors == []


def test_a_group_dropped_on_a_row_of_another_canvas_moves_there(page):
    pg, errors = page
    seed = _seed(pg, 'pixel-map')
    _drag(pg, _group_row(seed['gid']), _layer_row(seed['ids']['M']))
    _expect_list(pg, [['C1', ['L2', 'L1']], ['C2', ['M', 'G[B,A]']]])
    assert _history(pg) == ['Group Drag Seed', 'Move 2 Layers to Canvas']
    assert errors == []


def test_alt_drag_copies_the_group_on_pixel_map(page):
    pg, errors = page
    seed = _seed(pg, 'pixel-map')
    gid, c2 = seed['gid'], seed['c2']
    src = pg.locator(_group_row(gid)).bounding_box()
    dst = pg.locator(_canvas_header(c2)).bounding_box()
    pg.mouse.move(src['x'] + src['width'] / 2, src['y'] + src['height'] / 2)
    pg.mouse.down()
    pg.mouse.move(src['x'] + src['width'] / 2, src['y'] + src['height'] / 2 + 8)
    pg.keyboard.down('Alt')
    pg.mouse.move(dst['x'] + dst['width'] / 2, dst['y'] + dst['height'] / 2, steps=6)
    pg.mouse.up()
    pg.keyboard.up('Alt')
    _expect_list(pg, [['C1', ['L2', 'G[B,A]', 'L1']], ['C2', ['G[B,A]', 'M']]])
    st = settled(pg, lambda: pg.evaluate(STATE_JS), lambda v: len(v['server']['groups']) == 2)
    assert len(st['server']['groups']) == 2, st['server']['groups']
    copy = [g for g in st['server']['groups'] if g[0] != gid][0]
    assert len(copy[2]) == 2 and not set(copy[2]) & {seed['ids']['A'], seed['ids']['B']}, copy
    assert _history(pg) == ['Group Drag Seed', 'Duplicate 2 Layers to Canvas']
    _undo(pg)
    _expect_list(pg, SEEDED)
    assert errors == []


def test_a_drop_on_its_own_canvas_header_changes_nothing(page):
    pg, errors = page
    seed = _seed(pg, 'pixel-map')
    _drag(pg, _group_row(seed['gid']), _canvas_header(seed['c1']))
    pg.wait_for_timeout(300)
    assert pg.evaluate(LIST_JS) == SEEDED
    assert _history(pg) == ['Group Drag Seed']
    assert pg.evaluate("() => document.querySelectorAll('#layers-list .drag-target, #layers-list .dragging, "
                       "#layers-list .drag-over-top, #layers-list .drag-over-bottom').length") == 0
    assert errors == []


@pytest.mark.parametrize('mode', ['pixel-map', 'show-look'])
def test_a_locked_group_stays_and_says_why(page, mode):
    pg, errors = page
    seed = _seed(pg, mode, lock=True)
    before = pg.evaluate(STATE_JS)
    _drag(pg, _group_row(seed['gid']), _canvas_header(seed['c2']))
    toasts = settled(pg, lambda: pg.evaluate("() => window.__toasts"), lambda v: len(v) > 0)
    assert toasts == ['A and B are locked. Unlock them to change them.'], toasts
    pg.wait_for_timeout(400)
    assert pg.evaluate(LIST_JS) == SEEDED
    assert pg.evaluate(STATE_JS) == before
    assert _history(pg) == ['Group Drag Seed']
    assert errors == []


# ── up and down its canvas ────────────────────────────────────────────────

@pytest.mark.parametrize('mode', ['pixel-map', 'show-look'])
@pytest.mark.parametrize('target, half, want', [
    ('L2', 'top', ['G[B,A]', 'L2', 'L1']),
    ('L1', 'bottom', ['L2', 'L1', 'G[B,A]']),
    ('L1', 'top', ['L2', 'G[B,A]', 'L1']),     # where it already is: no step
])
def test_a_group_dragged_up_and_down_reorders(page, mode, target, half, want):
    pg, errors = page
    seed = _seed(pg, mode)
    before = pg.evaluate(STATE_JS)
    _drag(pg, _group_row(seed['gid']), _layer_row(seed['ids'][target]), half)
    _expect_list(pg, [['C1', want], ['C2', ['M']]])
    if want == SEEDED[0][1]:
        assert _history(pg) == ['Group Drag Seed']
        return
    assert _history(pg) == ['Group Drag Seed', 'Reorder Group']
    st = settled(pg, lambda: pg.evaluate(STATE_JS), lambda v: v['server']['order'] != before['server']['order'])
    # The members stay together and in their order, and on their canvas.
    order = st['server']['order']
    assert order.index('B') == order.index('A') + 1, order
    assert st['server']['layers'] == before['server']['layers']
    assert st['server']['groups'] == before['server']['groups']
    _undo(pg)
    _expect_list(pg, SEEDED)
    assert errors == []


def test_a_group_dropped_on_a_member_of_another_group_goes_beside_that_group(page):
    """Two groups on C1, both open. The top group dragged onto the lower half
    of the other group's last member lands under that WHOLE group."""
    pg, errors = page
    seed = _seed(pg, 'pixel-map', expand=True)
    ids = seed['ids']
    # A second group, G2 = L2 over L1, written straight into the model (the
    # grouping gesture itself is test_screen_groups_ui's).
    g2 = pg.evaluate("""async ([a, b]) => {
        const app = window.app;
        const g = {id: 'g_drag_2', name: 'Second', layer_ids: [a, b], powerPerMember: false};
        app.project.groups.push(g);
        app.project.layers.forEach(l => { if (l.id === a || l.id === b) l.group_id = g.id; });
        app._reflowGroupBlocks();
        app.setGroupExpanded(g.id, true);
        await app._commitGroupChange('Two Groups');
        app.resetHistory('Two Groups');
        return g.id;
    }""", [ids['L1'], ids['L2']])
    start = settled(pg, lambda: pg.evaluate(LIST_JS)[0][1], lambda v: len(v) == 2)
    assert sorted(start) == ['G[B,A]', 'G[L2,L1]'], start
    top = seed['gid'] if start[0] == 'G[B,A]' else g2
    last_member = ids['L1'] if top == seed['gid'] else ids['A']
    _drag(pg, _group_row(top), _layer_row(last_member), 'bottom')
    _expect_list(pg, [['C1', [start[1], start[0]]], ['C2', ['M']]])
    assert _history(pg) == ['Two Groups', 'Reorder Group']
    _undo(pg)
    _expect_list(pg, [['C1', start], ['C2', ['M']]])
    assert errors == []


def test_a_loose_screen_dropped_on_a_group_row_goes_beside_the_group(page):
    pg, errors = page
    seed = _seed(pg, 'pixel-map')
    _drag(pg, _layer_row(seed['ids']['L1']), _group_row(seed['gid']), 'top')
    _expect_list(pg, [['C1', ['L2', 'L1', 'G[B,A]']], ['C2', ['M']]])
    assert _history(pg) == ['Group Drag Seed', 'Reorder Layers']
    _undo(pg)
    _expect_list(pg, SEEDED)
    # and a loose screen from another canvas dropped on the row still moves
    # to the group's canvas, as a drop on the canvas block always did
    _drag(pg, _layer_row(seed['ids']['M']), _group_row(seed['gid']))
    got = settled(pg, lambda: pg.evaluate(LIST_JS), lambda v: v[1] == ['C2', []])
    assert got[1] == ['C2', []] and 'M' in got[0][1], got
    assert errors == []


def test_the_drop_line_shows_where_the_group_lands(page):
    """Hovering a group over a row draws the insertion line on that row;
    over a canvas it does not belong to, the canvas is outlined."""
    pg, errors = page
    seed = _seed(pg, 'pixel-map')
    src = pg.locator(_group_row(seed['gid'])).bounding_box()
    l2 = pg.locator(_layer_row(seed['ids']['L2'])).bounding_box()
    m = pg.locator(_canvas_header(seed['c2'])).bounding_box()
    marks = """() => ({
        top: [...document.querySelectorAll('#layers-list .drag-over-top')].map(e => e.dataset.layerId || e.dataset.groupId),
        bottom: [...document.querySelectorAll('#layers-list .drag-over-bottom')].map(e => e.dataset.layerId || e.dataset.groupId),
        target: [...document.querySelectorAll('#layers-list .canvas-group.drag-target')].map(e => e.dataset.canvasId),
        dragging: [...document.querySelectorAll('#layers-list .screen-group.dragging')].map(e => e.dataset.groupId),
    })"""
    pg.mouse.move(src['x'] + src['width'] / 2, src['y'] + src['height'] / 2)
    pg.mouse.down()
    pg.mouse.move(src['x'] + src['width'] / 2, src['y'] + src['height'] / 2 + 6)
    pg.mouse.move(l2['x'] + l2['width'] / 2, l2['y'] + l2['height'] * 0.2, steps=5)
    pg.mouse.move(l2['x'] + l2['width'] / 2 + 1, l2['y'] + l2['height'] * 0.2)
    pg.mouse.move(l2['x'] + l2['width'] / 2 + 2, l2['y'] + l2['height'] * 0.2)
    got = pg.evaluate(marks)
    assert got['top'] == [str(seed['ids']['L2'])] and got['dragging'] == [seed['gid']], got
    pg.mouse.move(m['x'] + m['width'] / 2, m['y'] + m['height'] / 2, steps=5)
    # Chromium sends the dragover on the moves after the one that entered.
    pg.mouse.move(m['x'] + m['width'] / 2 + 1, m['y'] + m['height'] / 2)
    pg.mouse.move(m['x'] + m['width'] / 2 + 2, m['y'] + m['height'] / 2)
    got = pg.evaluate(marks)
    assert got['top'] == [] and got['target'] == [seed['c2']], got
    pg.keyboard.press('Escape')
    pg.mouse.up()
    pg.wait_for_timeout(200)
    assert errors == []


# ── the grip ──────────────────────────────────────────────────────────────

def test_the_row_and_name_drag_and_not_while_renaming(page):
    pg, errors = page
    seed = _seed(pg, 'pixel-map')
    gid = seed['gid']
    attrs = lambda: pg.evaluate("""(s) => { const n = document.querySelector(s);
        const row = n.closest('.screen-group-row');
        return {row: row.draggable, name: n.draggable, readOnly: n.readOnly}; }""", _group_name(gid))
    assert attrs() == {'row': True, 'name': True, 'readOnly': True}
    # A drag from the name moves the group like a drag from the row.
    _drag(pg, _group_name(gid), _layer_row(seed['ids']['L2']), 'top')
    _expect_list(pg, [['C1', ['G[B,A]', 'L2', 'L1']], ['C2', ['M']]])
    pg.locator(_group_name(gid)).dblclick()
    got = settled(pg, attrs, lambda v: not v['readOnly'])
    assert got == {'row': False, 'name': False, 'readOnly': False}, got
    pg.keyboard.press('Escape')
    got = settled(pg, attrs, lambda v: v['readOnly'])
    assert got == {'row': True, 'name': True, 'readOnly': True}, got
    assert errors == []


# ── the guide ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize('run', range(3))
def test_the_guide_step_plays_on_its_own(page, run):
    """The Advanced Guide's step, played alone as What's New's Show me plays
    it, from its own entry snapshot: + Add Canvas, the group's row onto the
    new canvas and back, the canvas removed. Three times: a guide step
    passes first try, every time."""
    pg, errors = page
    pg.evaluate("""() => {
        const q = window.QuickStart, keys = q.tours().advanced
            .map(s => Object.keys(q.steps()).find(k => q.steps()[k] === s));
        if (keys[keys.indexOf('groupNames') + 1] !== 'groupDrag') throw new Error('out of place');
        if (q.steps().groupDrag.since !== '1.7.0') throw new Error('since');
    }""")
    body = pg.evaluate("() => window.QuickStart.steps().groupDrag.body")
    assert len(body) <= 220 and body.count('. ') <= 1, body
    pg.evaluate("() => { window.QuickStart.setSpeed(6); window.QuickStart.startSteps(['groupDrag']); }")
    pg.wait_for_function("""() => {
        const c = document.getElementById('qs-callout');
        return c && c.getAttribute('data-qs-state') === 'done';
    }""", timeout=60000)
    note = pg.locator('#qs-callout .qs-result').text_content()
    assert 'came back as one group' in note, note
    pg.evaluate("() => window.QuickStart.end()")
    pg.wait_for_function("() => !window.QuickStart.state().running && !window.QuickStart.state().visible")
    pg.wait_for_timeout(300)
    assert errors == []
