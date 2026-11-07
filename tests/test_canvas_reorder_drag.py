"""Dragging a canvas to a new place in the Screens list.

Owner's report, Mac app, 1.6.0 beta.5: "I can't drag and reorder
canvases." Two causes, both in app-canvas-ui.js:

- The drop. A canvas dropped on another always went BEFORE it
  (reorderCanvasBeforeTarget), so no canvas could reach the end of the
  list, and with two canvases dragging the first onto the second changed
  nothing at all. Now the upper half of the target's block means before
  and the lower half after, the screen rows' midpoint rule.
- The grip (not provable here). Most of the header is the read-only name
  field, and WebKit may start no ancestor drag from a press on a text
  field, which would leave only the small handle to grab there. The
  read-only name is draggable itself now (the screen rows already were),
  and its dragstart reaches the header's. WebKit cannot run on the
  Windows test PC, so the draggable attributes that decide it are
  asserted directly.

While a canvas name is edited neither the field nor the header is
draggable, so a drag in the field selects text and never moves the
canvas.

Dropped outside every block (1.6.0 QA, beta.6): the space under the last
canvas is most of a short list, and nothing took a drop there, so the canvas
stayed put and nothing was said. Owner: canvases drag to a new place, to the
end too. The list itself takes the drop now, under the last block and in the
gaps between blocks (app-canvas-ui _wireCanvasListDrop).

Run locally:
    python -m pytest tests/test_canvas_reorder_drag.py -v -n 4 --dist loadfile
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


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


def _src(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as fh:
        return fh.read()


def test_the_drop_knows_before_from_after():
    js = _src('src', 'static', 'js', 'app-canvas-ui.js')
    assert "import './app-canvas-ui.js';" in _src('src', 'static', 'js', 'main.js')
    assert "reorderCanvasBeforeTarget(draggedId, targetId, insertAfter = false)" in js
    assert "this.reorderCanvasBeforeTarget(draggedCanvasId, canvas.id, dropsAfter(e));" in js
    assert "nameInput.draggable = true;" in js
    assert "releaseDrag = holdDragOff(nameInput, header);" in js


SEED_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = []; proj.beaches = [];
    delete proj.port_assignments; delete proj.pullSheet;
    proj.canvases = proj.canvases.slice(0, 1);
    proj.canvases[0].name = 'K1';
    proj.active_canvas_id = proj.canvases[0].id;
    await j('PUT', '/api/project', proj);
    const ids = [proj.canvases[0].id];
    for (const name of ['K2', 'K3']) {
        ids.push((await j('POST', '/api/canvas', {name})).active_canvas_id);
    }
    let x = 0;
    for (const cid of ids) {
        await j('POST', '/api/layer/add', {name: 'S-' + cid, columns: 2, rows: 1,
            cabinet_width: 200, cabinet_height: 200, offset_x: x, offset_y: 0, canvas_id: cid});
        x += 400;
    }
    await j('PUT', `/api/canvas/${ids[0]}/active`);
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('canvas_reorder_drag_seed');
    app.selectLayer(app.project.layers[0]);
    app.renderLayers();
    window.canvasRenderer.render();
    if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
    app.resetHistory('Canvas Reorder Seed');
    return ids;
}"""

DRAGSTARTS_JS = """() => {
    window.__dragstarts = [];
    if (!window.__dragstartCounter) {
        window.__dragstartCounter = true;
        document.addEventListener('dragstart', (e) => {
            window.__dragstarts.push(e.target.className || e.target.tagName);
        }, true);
    }
}"""

SERVER_ORDER_JS = """async () => (await (await fetch('/api/project')).json()).canvases.map(c => c.name)"""
CLIENT_ORDER_JS = """() => window.app.project.canvases.map(c => c.name)"""
LIST_ORDER_JS = """() => [...document.querySelectorAll('#layers-list .canvas-group .canvas-name-input')].map(i => i.value)"""


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
    pg.locator('[data-mode="pixel-map"]').click()
    pg.wait_for_timeout(300)
    pg.evaluate(DRAGSTARTS_JS)
    yield pg, errors
    context.close()


@pytest.fixture
def seeded(page):
    pg, errors = page
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(400)
    assert pg.evaluate(SERVER_ORDER_JS) == ['K1', 'K2', 'K3']
    by_name = dict(zip(['K1', 'K2', 'K3'], ids))
    pg.evaluate("() => { window.__dragstarts = []; }")
    return pg, by_name


def _wrap(cid):
    return f'#layers-list .canvas-group[data-canvas-id="{cid}"]'


def _part(cid, part):
    sel = {'name': '.canvas-name-input', 'handle': '.canvas-drag-handle'}[part]
    return f'{_wrap(cid)} .canvas-group-header {sel}'


def _drag(pg, src_sel, target_cid, half):
    """A real mouse drag from src_sel onto the target canvas's block, on its
    upper ('top') or lower ('bottom') half."""
    target = pg.locator(_wrap(target_cid))
    box = target.bounding_box()
    y = box['height'] * (0.2 if half == 'top' else 0.8)
    pg.locator(src_sel).drag_to(target, target_position={'x': box['width'] / 2, 'y': y})
    pg.wait_for_timeout(150)


def _expect_order(pg, want):
    got = settled(pg, lambda: pg.evaluate(SERVER_ORDER_JS), lambda v: v == want)
    assert got == want, f'server order {got}, wanted {want}'
    assert pg.evaluate(CLIENT_ORDER_JS) == want
    lst = settled(pg, lambda: pg.evaluate(LIST_ORDER_JS), lambda v: v == want)
    assert lst == want, f'the list shows {lst}, wanted {want}'


def _undo(pg, want):
    pg.evaluate("() => window.app.undo()")
    _expect_order(pg, want)


def _attrs(pg, cid):
    return pg.evaluate("""(sel) => {
        const w = document.querySelector(sel);
        const h = w.querySelector('.canvas-group-header');
        const n = w.querySelector('.canvas-name-input');
        return {header: h.draggable, name: n.draggable, wrap: w.draggable, readOnly: n.readOnly};
    }""", _wrap(cid))


@pytest.mark.parametrize('src, target, half, want', [
    ('K1', 'K3', 'bottom', ['K2', 'K3', 'K1']),   # first to last
    ('K3', 'K1', 'top', ['K3', 'K1', 'K2']),      # last to first
    ('K2', 'K1', 'top', ['K2', 'K1', 'K3']),      # middle up
    ('K2', 'K3', 'bottom', ['K1', 'K3', 'K2']),   # middle down
    ('K1', 'K2', 'bottom', ['K2', 'K1', 'K3']),   # first past its neighbor
    ('K3', 'K2', 'top', ['K1', 'K3', 'K2']),      # last before its neighbor
])
def test_reorder_in_every_direction_and_undo(seeded, src, target, half, want):
    pg, ids = seeded
    a = _attrs(pg, ids[src])
    assert a == {'header': True, 'name': True, 'wrap': False, 'readOnly': True}, a
    _drag(pg, _part(ids[src], 'name'), ids[target], half)
    _expect_order(pg, want)
    _undo(pg, ['K1', 'K2', 'K3'])


def test_a_drop_that_changes_nothing_sends_nothing(seeded):
    pg, ids = seeded
    # K1 onto K2's upper half: before K2, where it already is.
    _drag(pg, _part(ids['K1'], 'name'), ids['K2'], 'top')
    _expect_order(pg, ['K1', 'K2', 'K3'])
    assert pg.evaluate("() => window.app.historyIndex") == 0


# The header shows the handle and the name (theme.css hides the color
# swatch, so it cannot be grabbed); a drag starts from either.
@pytest.mark.parametrize('part', ['name', 'handle'])
def test_the_drag_starts_from_any_part_of_the_header(seeded, part):
    pg, ids = seeded
    _drag(pg, _part(ids['K1'], part), ids['K3'], 'bottom')
    _expect_order(pg, ['K2', 'K3', 'K1'])
    assert pg.evaluate("() => window.__dragstarts.length") >= 1


def test_the_two_canvas_case_reaches_the_end(page):
    pg, _ = page
    ids = pg.evaluate(SEED_JS)
    pg.evaluate("(id) => window.app.deleteCanvas(id)", ids[2])
    settled(pg, lambda: pg.evaluate(SERVER_ORDER_JS), lambda v: v == ['K1', 'K2'])
    pg.wait_for_timeout(300)
    _drag(pg, _part(ids[0], 'name'), ids[1], 'bottom')
    _expect_order(pg, ['K2', 'K1'])


def test_no_drag_while_the_name_is_edited(seeded):
    pg, ids = seeded
    k1 = ids['K1']
    name = pg.locator(_part(k1, 'name'))
    name.dblclick()
    f = settled(pg, lambda: _attrs(pg, k1), lambda v: not v['readOnly'])
    assert f == {'header': False, 'name': False, 'wrap': False, 'readOnly': False}, f
    pg.evaluate("(s) => { const el = document.querySelector(s); el.value = 'ABCDEFGHIJ'; el.setSelectionRange(0, 0); }",
                _part(k1, 'name'))
    box = name.bounding_box()
    y = box['y'] + box['height'] / 2
    pg.evaluate("() => { window.__dragstarts = []; }")
    pg.mouse.move(box['x'] + 4, y)
    pg.mouse.down()
    for step in range(1, 9):
        pg.mouse.move(box['x'] + 4 + step * (box['width'] - 10) / 8, y)
    pg.mouse.up()
    sel = pg.evaluate("(s) => { const el = document.querySelector(s); return [el.selectionStart, el.selectionEnd, document.activeElement === el]; }",
                      _part(k1, 'name'))
    assert sel[0] != sel[1], f'a drag in the field selected no text: {sel}'
    assert sel[2], 'the field lost the focus'
    assert pg.evaluate("() => window.__dragstarts") == []
    # Even dropped on another canvas, a drag from the open field moves nothing.
    _drag(pg, _part(k1, 'name'), ids['K3'], 'bottom')
    assert pg.evaluate(SERVER_ORDER_JS) == ['K1', 'K2', 'K3']
    pg.keyboard.press('Escape')
    f = settled(pg, lambda: _attrs(pg, k1), lambda v: v['readOnly'])
    assert f == {'header': True, 'name': True, 'wrap': False, 'readOnly': True}, f
    # and once the edit is over the canvas drags again
    _drag(pg, _part(k1, 'name'), ids['K3'], 'bottom')
    _expect_order(pg, ['K2', 'K3', 'K1'])


def test_a_rename_ended_by_enter_restores_the_drag(seeded):
    pg, ids = seeded
    k2 = ids['K2']
    pg.locator(_part(k2, 'name')).dblclick()
    settled(pg, lambda: _attrs(pg, k2), lambda v: not v['readOnly'])
    pg.keyboard.press('Control+A')
    pg.keyboard.type('KAY2')
    pg.keyboard.press('Enter')
    names = settled(pg, lambda: pg.evaluate(SERVER_ORDER_JS), lambda v: v == ['K1', 'KAY2', 'K3'])
    assert names == ['K1', 'KAY2', 'K3'], names
    f = settled(pg, lambda: _attrs(pg, k2), lambda v: v['readOnly'] and v['header'])
    assert f == {'header': True, 'name': True, 'wrap': False, 'readOnly': True}, f


def test_a_rename_ended_by_a_rebuild_leaves_the_header_draggable(seeded):
    pg, ids = seeded
    k3 = ids['K3']
    pg.locator(_part(k3, 'name')).dblclick()
    settled(pg, lambda: _attrs(pg, k3), lambda v: not v['readOnly'])
    pg.evaluate("() => window.app.renderLayers()")
    pg.wait_for_timeout(150)
    for cid in ids.values():
        f = _attrs(pg, cid)
        assert f['header'] and f['name'] and f['readOnly'], (cid, f)
    pg.evaluate("() => document.activeElement && document.activeElement.blur()")


def test_dragging_does_not_activate_the_canvas_mid_drag(seeded):
    """The header's click (setActiveCanvas, which rebuilds the list) never
    fires for a drag, so the dragged header is not replaced under it."""
    pg, ids = seeded
    pg.evaluate("""() => {
        window.__activations = 0;
        const app = window.app;
        if (!app.__wrappedActivate) {
            app.__wrappedActivate = true;
            const orig = app.setActiveCanvas;
            app.setActiveCanvas = function (...a) { window.__activations += 1; return orig.apply(this, a); };
        }
    }""")
    _drag(pg, _part(ids['K2'], 'handle'), ids['K3'], 'bottom')
    _expect_order(pg, ['K1', 'K3', 'K2'])
    assert pg.evaluate("() => window.__activations") == 0


# ── the list outside the blocks ───────────────────────────────────────────

SPACE_JS = """() => {
    const list = document.getElementById('layers-list').getBoundingClientRect();
    const blocks = [...document.querySelectorAll('#layers-list .canvas-group')]
        .map(el => el.getBoundingClientRect());
    const last = blocks[blocks.length - 1];
    return {x: list.left + list.width / 2, below: (last.bottom + list.bottom) / 2,
            room: list.bottom - last.bottom,
            gaps: blocks.slice(1).map((b, i) => (blocks[i].bottom + b.top) / 2)};
}"""

MARKS_JS = """() => [...document.querySelectorAll('#layers-list .canvas-group')]
    .filter(el => el.classList.contains('drag-before') || el.classList.contains('drag-after'))
    .map(el => [el.querySelector('.canvas-name-input').value,
                el.classList.contains('drag-after') ? 'after' : 'before'])"""


def _press_and_carry(pg, src_sel, x, y):
    box = pg.locator(src_sel).bounding_box()
    sx, sy = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2
    pg.mouse.move(sx, sy)
    pg.mouse.down()
    pg.mouse.move(sx, sy + 12, steps=3)
    _carry_to(pg, x, y)


def _carry_to(pg, x, y):
    """Playwright's move onto a new element is a dragenter; only the next
    move there is a dragover, which a held mouse sends by itself."""
    pg.mouse.move(x, y, steps=6)
    pg.mouse.move(x + 1, y)
    pg.wait_for_timeout(100)


def _drag_to_space(pg, src_sel, y=None):
    space = pg.evaluate(SPACE_JS)
    assert space['room'] > 40, f'no room under the last block: {space}'
    _press_and_carry(pg, src_sel, space['x'], space['below'] if y is None else y)
    pg.mouse.up()
    pg.wait_for_timeout(150)


@pytest.mark.parametrize('src, want', [('K1', ['K2', 'K3', 'K1']), ('K2', ['K1', 'K3', 'K2'])])
def test_a_drop_under_the_last_canvas_moves_it_to_the_end(seeded, src, want):
    pg, ids = seeded
    _drag_to_space(pg, _part(ids[src], 'name'))
    _expect_order(pg, want)
    assert pg.evaluate("() => window.app.history[window.app.historyIndex].action") == 'Reorder Canvases'
    # undo, redo, then the server's copy through a reload
    _undo(pg, ['K1', 'K2', 'K3'])
    pg.evaluate("() => window.app.redo()")
    _expect_order(pg, want)
    pg.reload(wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)
    _expect_order(pg, want)
    # a saved file holds the same order
    saved = pg.evaluate("""() => JSON.parse(window.app.serializeProjectForFile(
        JSON.parse(JSON.stringify(window.app.project)))).canvases.map(c => c.name)""")
    assert saved == want
    pg.evaluate(DRAGSTARTS_JS)


def test_the_drop_under_the_last_canvas_shows_where_it_lands(seeded):
    pg, ids = seeded
    space = pg.evaluate(SPACE_JS)
    _press_and_carry(pg, _part(ids['K1'], 'name'), space['x'], space['below'])
    marks = settled(pg, lambda: pg.evaluate(MARKS_JS), lambda v: v == [['K3', 'after']])
    assert marks == [['K3', 'after']]
    # over a block the block marks it alone
    box = pg.locator(_wrap(ids['K2'])).bounding_box()
    _carry_to(pg, box['x'] + box['width'] / 2, box['y'] + box['height'] * 0.2)
    marks = settled(pg, lambda: pg.evaluate(MARKS_JS), lambda v: v == [['K2', 'before']])
    assert marks == [['K2', 'before']]
    _carry_to(pg, space['x'], space['below'])
    settled(pg, lambda: pg.evaluate(MARKS_JS), lambda v: v == [['K3', 'after']])
    pg.mouse.up()
    _expect_order(pg, ['K2', 'K3', 'K1'])
    assert pg.evaluate(MARKS_JS) == []


def test_a_drop_in_the_gap_between_canvases_lands_there(seeded):
    pg, ids = seeded
    gaps = pg.evaluate(SPACE_JS)['gaps']
    _drag_to_space(pg, _part(ids['K3'], 'name'), gaps[0])
    _expect_order(pg, ['K1', 'K3', 'K2'])


def test_the_last_canvas_dropped_under_itself_sends_nothing(seeded):
    pg, ids = seeded
    _drag_to_space(pg, _part(ids['K3'], 'name'))
    _expect_order(pg, ['K1', 'K2', 'K3'])
    assert pg.evaluate("() => window.app.historyIndex") == 0
    assert pg.evaluate(MARKS_JS) == []


def test_a_screen_dropped_under_the_last_canvas_goes_nowhere(seeded):
    pg, ids = seeded
    before = pg.evaluate("""() => window.app.project.layers.map(l => [l.id, l.canvas_id])""")
    row = f'{_wrap(ids["K1"])} .layer-item .layer-info'
    _drag_to_space(pg, row)
    _expect_order(pg, ['K1', 'K2', 'K3'])
    assert pg.evaluate("""() => window.app.project.layers.map(l => [l.id, l.canvas_id])""") == before
    assert pg.evaluate("() => window.app.historyIndex") == 0


def test_no_page_errors(page):
    _, errors = page
    assert errors == [], errors
