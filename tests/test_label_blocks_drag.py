"""A screen's size lines and info bar drag on their own, like its name.

The owner (2026-11-27): "We also need to be able to move the labels like
resolution etc with click and drag, not just screen name." His rulings:

  Each block on its own   Two blocks drag besides the name: the lines under
                          the name (sizes and weight on Pixel Map, the size
                          on Show Look, the port or circuit line on Data and
                          Power) and Pixel Map's info bar. A drag moves its
                          block and nothing else.
  Per tab, Reset          Each tab keeps its own place for each block, the
                          way the name's offsets are kept per tab, and a
                          right-click on a moved piece (a block or the name)
                          offers Reset position.

And the rules every drag here keeps: one undo step per drag, saved with the
show and back after a reload, a click with no movement does what a click
there always did, a locked screen refuses and says why, and the binder and
the exports draw a moved block where it was moved.

A block never dragged follows the name exactly as before (canvas-labels.js
_placeLabelBlock), so a show drawn before this draws the same.

Run locally:
    python -m pytest tests/test_label_blocks_drag.py -n 2 --dist loadfile
"""

import json

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# A 12 x 6 wall A with its size line, weight, info bar and the Data and
# Power lines on, a wall B beside it, and two 4 x 3 walls grouped as WALL.
# A (2400 x 1200) hangs past the 1920 x 1080 canvas, so its info bar is
# drawn slid up onto the canvas: a drag starts from where it is drawn and
# moves it by exactly the mouse's travel, never jumping by the slide.
SEED_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    proj.canvases = proj.canvases.slice(0, 1); proj.active_canvas_id = proj.canvases[0].id;
    delete proj.port_assignments; delete proj.pullSheet; delete proj.pullSheetEdits;
    delete proj.binder; delete proj.groupNameDisplay; delete proj.groupNameDisplayByView;
    await j('PUT', '/api/project', proj);
    const wall = {columns: 12, rows: 6, cabinet_width: 200, cabinet_height: 200, panelWatts: 200,
                  flowPattern: 'tl-h', powerVoltage: 208, powerAmperage: 20,
                  powerFlowPattern: 'tl-v', powerOrganized: true, processorType: 'novastar-armor'};
    await j('POST', '/api/layer/add', {...wall, name: 'A'});
    await j('POST', '/api/layer/add', {...wall, name: 'B', offset_x: 2800});
    await j('POST', '/api/layer/add', {...wall, columns: 4, rows: 3, name: 'L', offset_x: 5600});
    await j('POST', '/api/layer/add', {...wall, columns: 4, rows: 3, name: 'R', offset_x: 6400});
    let p = await j('GET', '/api/project');
    const f = n => p.layers.find(l => l.name === n);
    p.layers.forEach(l => Object.assign(l, {showLabelSizePx: true, showLabelWeight: true,
        showLabelInfo: true, showDataFlowPortInfo: true, showPowerCircuitInfo: true}));
    f('L').group_id = 'g1'; f('R').group_id = 'g1';
    p.groups = [{id: 'g1', name: 'WALL', layer_ids: [f('L').id, f('R').id], routeDataAsOne: false}];
    await j('PUT', '/api/project', p);
    p = await j('GET', '/api/project');
    app.project = p;
    app.dedupeProjectLayers('label_blocks_setup');
    app.renderLayers();
    window.canvasRenderer.render();
    app.resetHistory('Label Blocks Seed');
    return Object.fromEntries(app.project.layers.map(l => [l.name, l.id]));
}"""

FIELDS = ['labelLinesOffsetXPixelMap', 'labelLinesOffsetYPixelMap',
          'labelLinesOffsetXShowLook', 'labelLinesOffsetYShowLook',
          'labelLinesOffsetXDataFlow', 'labelLinesOffsetYDataFlow',
          'labelLinesOffsetXPower', 'labelLinesOffsetYPower',
          'labelInfoOffsetXPixelMap', 'labelInfoOffsetYPixelMap']
NAME_PM = ['screenNameOffsetXPixelMap', 'screenNameOffsetYPixelMap']
LOCK_MSG = 'locked. Unlock'

RECT_KEY = {'name': '_screenNameHitRect', 'lines': '_labelLinesHitRect', 'info': '_labelInfoHitRect'}


def _open(e2e_server, pw_browser):
    ctx = pw_browser.new_context(viewport={'width': 1600, 'height': 1000})
    ctx.add_init_script("try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    page = ctx.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    for kind in ('save-file', 'open-file', 'select-directory'):
        page.route('**/api/native-dialog/' + kind, lambda r: r.fulfill(json={'path': None}))
    page.goto(e2e_server, wait_until='domcontentloaded')
    page.wait_for_function("() => window.app && window.app._initialLoadComplete")
    page.wait_for_timeout(1000)
    page.evaluate("() => { const s = document.querySelector('#start-page'); if (s) s.style.display = 'none'; }")
    page.errors = errors
    return ctx, page


@pytest.fixture(scope="module")
def browser_page(e2e_server, pw_browser):
    ctx, page = _open(e2e_server, pw_browser)
    yield page
    ctx.close()


@pytest.fixture()
def pg(browser_page):
    p = browser_page
    tab(p, 'pixel-map')
    p.ids = p.evaluate(SEED_JS)
    p.wait_for_timeout(300)
    p.errors.clear()
    yield p
    assert not p.errors, p.errors


def tab(p, mode):
    p.locator(f'.view-tab[data-mode="{mode}"]').click()
    p.wait_for_timeout(300)


def sel(p, name):
    p.evaluate("(id) => { const a = window.app; a.setSelectedLayersByIds([id], id); }", p.ids[name])
    p.wait_for_timeout(150)


def frame(p, *names):
    """Zoom so the named screens fill about 60% of the canvas, centred."""
    p.evaluate("""(ids) => {
        const r = window.canvasRenderer, a = window.app;
        const ls = ids.map(id => a.project.layers.find(l => l.id === id));
        let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
        ls.forEach(l => { const b = r.getLayerBoundsInActiveView(l), w = r._layerCanvasOffset(l);
            x0 = Math.min(x0, b.x + w.wx); y0 = Math.min(y0, b.y + w.wy);
            x1 = Math.max(x1, b.x + w.wx + b.width); y1 = Math.max(y1, b.y + w.wy + b.height); });
        r.zoom = Math.min(r.canvas.width * 0.6 / (x1 - x0), r.canvas.height * 0.6 / (y1 - y0));
        r.panX = r.canvas.width / 2 - (x0 + x1) / 2 * r.zoom;
        r.panY = r.canvas.height / 2 - (y0 + y1) / 2 * r.zoom;
        r.render(); }""", [p.ids[n] for n in names])


def rects(p, owner='A'):
    """Where the name, the lines and the info bar are drawn (world units),
    with the client point at each one's centre, or None where not drawn."""
    return p.evaluate("""([id, keys]) => {
        const r = window.canvasRenderer, l = window.app.project.layers.find(x => x.id === id);
        r.render();
        const b = r.canvas.getBoundingClientRect(), out = {};
        for (const [k, key] of Object.entries(keys)) {
            const h = l[key];
            out[k] = h && h.viewMode === r.viewMode ? {
                x1: h.x1, y1: h.y1, x2: h.x2, y2: h.y2,
                cx: b.left + (h.x1 + h.x2) / 2 * r.zoom + r.panX,
                cy: b.top + (h.y1 + h.y2) / 2 * r.zoom + r.panY, zoom: r.zoom } : null;
        }
        return out; }""", [p.ids[owner], RECT_KEY])


def lay(p, name, *fields):
    return p.evaluate("""([id, f]) => { const l = window.app.project.layers.find(x => x.id === id);
        return Object.fromEntries(f.map(k => [k, l[k] === undefined ? null : l[k]])); }""",
                      [p.ids[name], list(fields)])


def server_lay(p, name, *fields):
    return p.evaluate("""([id, f]) => fetch('/api/project').then(r => r.json()).then(j => {
        const l = j.layers.find(x => x.id === id);
        return Object.fromEntries(f.map(k => [k, l[k] === undefined ? null : l[k]])); })""",
                      [p.ids[name], list(fields)])


def steps(p):
    return p.evaluate("() => window.app.historyIndex")


def drag(p, pt, dx, dy):
    p.mouse.move(pt['cx'], pt['cy'])
    p.mouse.down()
    p.mouse.move(pt['cx'] + dx / 2, pt['cy'] + dy / 2, steps=4)
    p.mouse.move(pt['cx'] + dx, pt['cy'] + dy, steps=4)
    p.mouse.up()
    p.wait_for_timeout(400)


def toasts(p):
    return p.evaluate("() => [...document.querySelectorAll('#app-toast-host > div')].map(e => e.textContent)")


def clear_toasts(p):
    p.evaluate("() => { const h = document.getElementById('app-toast-host'); if (h) h.innerHTML = ''; }")


def moved_by(before, after, dx, dy):
    """`after` sits (dx, dy) screen pixels from `before` (to a pixel)."""
    z = before['zoom']
    return (abs((after['x1'] - before['x1']) * z - dx) < 1.5
            and abs((after['y1'] - before['y1']) * z - dy) < 1.5)


def same(a, b):
    return all(abs(a[k] - b[k]) < 0.01 for k in ('x1', 'y1', 'x2', 'y2'))


def menu_items(p):
    return p.evaluate("""() => [...document.querySelectorAll('#context-menu > .menu-option')]
        .filter(e => e.style.display !== 'none').map(e => e.dataset.action)""")


def right_click(p, pt):
    p.mouse.click(pt['cx'], pt['cy'], button='right')
    p.wait_for_timeout(250)


# ── each block drags on its own ─────────────────────────────────────────

@pytest.mark.parametrize('block', ['info', 'lines'])
def test_a_pixel_map_block_drags_alone(pg, block):
    p = pg
    sel(p, 'A')
    frame(p, 'A')
    before = rects(p)
    assert before['name'] and before['lines'] and before['info'], before
    n = steps(p)
    drag(p, before[block], 90, -70)
    after = rects(p)
    assert moved_by(before[block], after[block], 90, -70), (before[block], after[block])
    other = 'lines' if block == 'info' else 'info'
    assert same(before['name'], after['name']) and same(before[other], after[other]), (before, after)
    got = lay(p, 'A', *FIELDS, *NAME_PM, 'offset_x', 'offset_y')
    key = 'labelInfoOffset' if block == 'info' else 'labelLinesOffset'
    assert got[key + 'XPixelMap'] and got[key + 'YPixelMap'], got
    assert [k for k in FIELDS if got[k] is not None] == [key + 'XPixelMap', key + 'YPixelMap'], got
    assert not got[NAME_PM[0]] and not got[NAME_PM[1]], got
    assert (got['offset_x'], got['offset_y']) == (0, 0), got
    # one undo step, the screen still selected and no cabinet picked
    assert steps(p) == n + 1
    assert p.evaluate("() => window.app.currentLayer.id") == p.ids['A']
    assert p.evaluate("() => window.app.pixelMapSelection.size") == 0


def test_the_cursor_says_a_block_can_be_moved(pg):
    p = pg
    sel(p, 'A')
    frame(p, 'A')
    r = rects(p)
    for k in ('name', 'lines', 'info'):
        p.mouse.move(r[k]['cx'] + 3, r[k]['cy'])
        p.mouse.move(r[k]['cx'], r[k]['cy'])
        assert p.evaluate("() => window.canvasRenderer.canvas.style.cursor") == 'move', k


def test_the_power_tab_keeps_its_own_place_and_pixel_map_keeps_its(pg):
    p = pg
    tab(p, 'power')
    sel(p, 'A')
    frame(p, 'A')
    before = rects(p)
    assert before['lines'] and before['name'] and not before['info'], before
    drag(p, before['lines'], 60, 80)
    after = rects(p)
    assert moved_by(before['lines'], after['lines'], 60, 80), (before['lines'], after['lines'])
    assert same(before['name'], after['name'])
    got = lay(p, 'A', *FIELDS)
    assert [k for k in FIELDS if got[k] is not None] == ['labelLinesOffsetXPower', 'labelLinesOffsetYPower'], got
    # Pixel Map's lines are where they always were, and Data's too.
    for mode in ('pixel-map', 'data-flow'):
        tab(p, mode)
        frame(p, 'A')
        r = rects(p)
        home = p.evaluate("""() => { const r = window.canvasRenderer;
            const l = window.app.currentLayer, b = r.getLayerBounds(l);
            return { cx: b.x + b.width / 2 }; }""")
        assert abs((r['lines']['x1'] + r['lines']['x2']) / 2 - home['cx']) < 1, (mode, r['lines'], home)
    tab(p, 'power')
    frame(p, 'A')
    assert same(rects(p)['lines'], after['lines'])


def test_a_name_drag_leaves_a_dragged_block_and_carries_one_never_dragged(pg):
    p = pg
    sel(p, 'A')
    frame(p, 'A')
    r0 = rects(p)
    drag(p, r0['info'], -80, -60)
    r1 = rects(p)
    drag(p, r1['name'], 120, -90)
    r2 = rects(p)
    assert moved_by(r1['name'], r2['name'], 120, -90), (r1['name'], r2['name'])
    # the dragged info bar stays put; the lines, never dragged, follow the name
    assert same(r1['info'], r2['info']), (r1['info'], r2['info'])
    assert moved_by(r1['lines'], r2['lines'], 120, -90), (r1['lines'], r2['lines'])
    assert lay(p, 'A', 'labelLinesOffsetXPixelMap')['labelLinesOffsetXPixelMap'] is None


def test_a_click_on_a_block_does_what_it_did_and_a_drag_selects_nothing(pg):
    p = pg
    sel(p, 'A')
    frame(p, 'A')
    r = rects(p)
    n = steps(p)
    # a click: the cabinet under the info bar is picked, as before
    p.mouse.click(r['info']['cx'], r['info']['cy'])
    p.wait_for_timeout(250)
    assert p.evaluate("() => window.app.pixelMapSelection.size") == 1
    assert lay(p, 'A', *FIELDS) == {k: None for k in FIELDS}
    assert steps(p) == n
    # a drag from the same spot picks no cabinet and keeps the selection
    p.evaluate("() => window.app.clearPixelMapSelection()")
    drag(p, rects(p)['lines'], 50, 40)
    assert p.evaluate("() => window.app.pixelMapSelection.size") == 0
    assert p.evaluate("() => [...window.app.selectedLayerIds]") == [p.ids['A']]


# ── one undo step, saved, and back after a reload ───────────────────────

def test_undo_and_redo_step_a_block_drag_as_one(pg):
    p = pg
    sel(p, 'A')
    frame(p, 'A')
    r0 = rects(p)
    drag(p, r0['lines'], 70, 50)
    r1 = rects(p)
    moved = lay(p, 'A', 'labelLinesOffsetXPixelMap', 'labelLinesOffsetYPixelMap')
    p.evaluate("() => window.app.undo()")
    p.wait_for_timeout(500)
    assert lay(p, 'A', 'labelLinesOffsetXPixelMap', 'labelLinesOffsetYPixelMap') == {
        'labelLinesOffsetXPixelMap': None, 'labelLinesOffsetYPixelMap': None}
    assert same(rects(p)['lines'], r0['lines'])
    p.evaluate("() => window.app.redo()")
    p.wait_for_timeout(500)
    assert lay(p, 'A', 'labelLinesOffsetXPixelMap', 'labelLinesOffsetYPixelMap') == moved
    assert same(rects(p)['lines'], r1['lines'])


def test_a_dragged_block_is_saved_with_the_show_and_back_after_a_reload(pg, e2e_server, pw_browser):
    p = pg
    sel(p, 'A')
    frame(p, 'A')
    drag(p, rects(p)['info'], 100, -120)
    tab(p, 'power')
    frame(p, 'A')
    drag(p, rects(p)['lines'], -60, 70)
    p.wait_for_timeout(600)
    keys = ['labelInfoOffsetXPixelMap', 'labelInfoOffsetYPixelMap', 'labelLinesOffsetXPower', 'labelLinesOffsetYPower']
    here = lay(p, 'A', *keys)
    assert all(here[k] for k in keys), here
    assert server_lay(p, 'A', *keys) == here
    # the show file is the project as the page holds it
    in_file = p.evaluate("""(id) => { const j = JSON.parse(JSON.stringify(window.app.project));
        return j.layers.find(l => l.id === id); }""", p.ids['A'])
    assert all(in_file[k] == here[k] for k in keys), in_file
    # a fresh page on the same show draws them where they were left
    ctx, q = _open(e2e_server, pw_browser)
    try:
        q.ids = p.ids
        assert lay(q, 'A', *keys) == here
        sel(q, 'A')
        tab(q, 'power')
        frame(q, 'A')
        tab(p, 'power')
        frame(p, 'A')
        assert same(rects(q)['lines'], rects(p)['lines'])
        assert not q.errors, q.errors
    finally:
        ctx.close()


# ── right-click Reset position ──────────────────────────────────────────

def test_reset_position_puts_a_block_back_on_its_tab_only(pg):
    p = pg
    sel(p, 'A')
    frame(p, 'A')
    r0 = rects(p)
    # a block never moved: nothing to reset, not offered
    right_click(p, r0['info'])
    assert 'label-reset' not in menu_items(p)
    p.keyboard.press('Escape')
    drag(p, r0['info'], 80, -100)
    tab(p, 'power')
    frame(p, 'A')
    drag(p, rects(p)['lines'], 40, 60)
    power = lay(p, 'A', 'labelLinesOffsetXPower', 'labelLinesOffsetYPower')
    tab(p, 'pixel-map')
    frame(p, 'A')
    n = steps(p)
    right_click(p, rects(p)['info'])
    assert menu_items(p)[0] == 'label-reset', menu_items(p)
    assert p.locator('#context-menu [data-action="label-reset"]').text_content() == 'Reset position'
    p.locator('#context-menu [data-action="label-reset"]').click()
    p.wait_for_timeout(400)
    assert lay(p, 'A', 'labelInfoOffsetXPixelMap', 'labelInfoOffsetYPixelMap') == {
        'labelInfoOffsetXPixelMap': None, 'labelInfoOffsetYPixelMap': None}
    assert same(rects(p)['info'], r0['info'])
    assert steps(p) == n + 1
    p.wait_for_timeout(300)
    assert server_lay(p, 'A', 'labelInfoOffsetXPixelMap')['labelInfoOffsetXPixelMap'] is None
    # Power's place is its own and stays
    assert lay(p, 'A', 'labelLinesOffsetXPower', 'labelLinesOffsetYPower') == power


def test_reset_position_puts_the_name_back_too(pg):
    p = pg
    sel(p, 'A')
    frame(p, 'A')
    r0 = rects(p)
    drag(p, r0['name'], 100, 80)
    assert lay(p, 'A', NAME_PM[0])[NAME_PM[0]]
    right_click(p, rects(p)['name'])
    p.locator('#context-menu [data-action="label-reset"]').click()
    p.wait_for_timeout(400)
    assert lay(p, 'A', *NAME_PM) == {NAME_PM[0]: 0, NAME_PM[1]: 0}
    assert same(rects(p)['name'], r0['name'])


# ── a locked screen refuses ─────────────────────────────────────────────

def test_a_locked_screen_refuses_a_block_drag_and_its_reset_and_says_why(pg):
    p = pg
    sel(p, 'A')
    frame(p, 'A')
    drag(p, rects(p)['lines'], 60, 60)
    p.evaluate("() => window.app.setLockOnSelected(true)")
    p.wait_for_timeout(200)
    before = lay(p, 'A', *FIELDS)
    r = rects(p)
    n = steps(p)
    p.mouse.move(r['info']['cx'], r['info']['cy'])
    assert p.evaluate("() => window.canvasRenderer.canvas.style.cursor") == 'not-allowed'
    clear_toasts(p)
    drag(p, r['info'], 70, -80)
    assert any(LOCK_MSG in t for t in toasts(p)), toasts(p)
    assert lay(p, 'A', *FIELDS) == before
    assert same(rects(p)['info'], r['info'])
    assert steps(p) == n
    clear_toasts(p)
    right_click(p, rects(p)['lines'])
    p.locator('#context-menu [data-action="label-reset"]').click()
    p.wait_for_timeout(300)
    assert any(LOCK_MSG in t for t in toasts(p)), toasts(p)
    assert lay(p, 'A', *FIELDS) == before
    assert steps(p) == n
    p.evaluate("() => window.app.setLockOnSelected(false)")


# ── a group's label ─────────────────────────────────────────────────────

def test_a_groups_info_bar_drags_on_the_first_members_fields(pg):
    p = pg
    sel(p, 'L')
    frame(p, 'L', 'R')
    owner = p.evaluate("""(id) => { const r = window.canvasRenderer;
        const l = window.app.project.layers.find(x => x.id === id);
        return r._labelBlockOwner(l).name; }""", p.ids['R'])
    before = rects(p, owner)
    assert before['info'], before
    drag(p, before['info'], 60, -50)
    after = rects(p, owner)
    assert moved_by(before['info'], after['info'], 60, -50), (before['info'], after['info'])
    other = 'R' if owner == 'L' else 'L'
    assert lay(p, owner, 'labelInfoOffsetXPixelMap')['labelInfoOffsetXPixelMap']
    assert lay(p, other, 'labelInfoOffsetXPixelMap')['labelInfoOffsetXPixelMap'] is None


# ── the exports and the binder draw it where it was moved ───────────────

# Where the renderer writes the line `pattern` matches: each fillText of it
# on the canvas the render paints, in that canvas's own pixels. `mode`:
# 'export' renders the view as the PNG/PSD/PDF exports do (exportMode),
# 'binder' renders the binder page `title`.
TEXT_AT_JS = """([mode, pattern, title, opts]) => {
    const app = window.app, r = window.canvasRenderer, re = new RegExp(pattern);
    const had = Object.prototype.hasOwnProperty.call(r, '_fillText');
    const fill = r._fillText;
    const hits = [];
    r._fillText = function (t, x, y, ...rest) {
        const target = mode === 'binder' ? app._binderMapCanvas : r.canvas;
        if (re.test(String(t)) && this.ctx && this.ctx.canvas === target) {
            const m = this.ctx.getTransform();
            hits.push({ x: m.a * x + m.c * y + m.e, y: m.b * x + m.d * y + m.f, s: m.d });
        }
        return fill.call(this, t, x, y, ...rest);
    };
    try {
        if (mode === 'binder') {
            const idx = app.planBinder(opts).findIndex(p => p.title === title);
            if (idx < 0) return { missing: title, titles: app.planBinder(opts).map(p => p.title) };
            app.renderBinderPage(opts, idx);
        } else {
            r.exportMode = true;
            try { r.render(); } finally { r.exportMode = false; }
        }
    } finally {
        if (had) r._fillText = fill; else delete r._fillText;
        r.render();
    }
    return { hits };
}"""

BINDER_OPTS = {'sheet': 'tabloid', 'palette': 'colour', 'sides': {'power': True, 'data': True},
               'scope': {'kind': 'show'}, 'cover': False, 'pull': False, 'hardware': False,
               'titleBlock': False}


def test_an_export_draws_a_moved_info_bar_where_it_was_moved(pg):
    p = pg
    sel(p, 'A')
    frame(p, 'A')
    base = p.evaluate(TEXT_AT_JS, ['export', '^A$', None, None])
    info0 = p.evaluate(TEXT_AT_JS, ['export', 'Resolution:', None, None])
    assert len(info0['hits']) >= 1 and base['hits'], (info0, base)
    drag(p, rects(p)['info'], 0, -150)
    info1 = p.evaluate(TEXT_AT_JS, ['export', 'Resolution:', None, None])
    moved = p.evaluate(TEXT_AT_JS, ['export', '^A$', None, None])
    # the canvas pixels the drag moved A's bar by, the export moves it by
    # too; B's and the group's bars stay where they were
    by = [b['y'] - a['y'] for a, b in zip(info0['hits'], info1['hits'])]
    assert len(by) == 3 and abs(by[0] + 150) < 2 and all(abs(d) < 0.01 for d in by[1:]), (info0, info1)
    assert [h['y'] for h in moved['hits']] == [h['y'] for h in base['hits']]


def test_the_binder_power_sheet_draws_moved_lines_where_they_were_moved(pg):
    p = pg
    tab(p, 'power')
    sel(p, 'A')
    frame(p, 'A')
    title = 'A - Power - Front View'
    pattern = r'Circuits \|'
    before = p.evaluate(TEXT_AT_JS, ['binder', pattern, title, BINDER_OPTS])
    assert 'missing' not in before, before
    assert len(before['hits']) == 1, before
    name0 = p.evaluate(TEXT_AT_JS, ['binder', '^A$', title, BINDER_OPTS])
    r = rects(p)
    drag(p, r['lines'], 0, 100)
    dy_world = lay(p, 'A', 'labelLinesOffsetYPower')['labelLinesOffsetYPower']
    assert dy_world and abs(dy_world - 100 / r['lines']['zoom']) < 1, dy_world
    after = p.evaluate(TEXT_AT_JS, ['binder', pattern, title, BINDER_OPTS])
    name1 = p.evaluate(TEXT_AT_JS, ['binder', '^A$', title, BINDER_OPTS])
    b, a = before['hits'][0], after['hits'][0]
    assert abs((a['y'] - b['y']) - dy_world * b['s']) < 2, (b, a, dy_world)
    # the name on the sheet stays where it was
    assert [h['y'] for h in name1['hits']] == [h['y'] for h in name0['hits']], (name0, name1)
    assert json.dumps(after)  # plain data
