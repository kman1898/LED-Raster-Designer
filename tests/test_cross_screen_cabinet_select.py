"""Cabinet selection across screens (1.5).

The owner's ruling (2026-10-16): "when i group screens i cant select panels
across screens for setting blanks or halfs etc. it would be nice if i could" -
for ANY selected screens, grouped or not - and "this type of selection needs
to work on custom for data and power groups too".

Pinned here, with real mouse gestures on the live canvas wherever the gesture
itself is under test:

* PIXEL MAP. With several screens selected, a marquee selects cabinets on
  every selected screen it touches - wherever it starts. pixelMapSelection is
  keyed `${layerId}:${row},${col}`. The bulk bar counts every screen, the
  highlight lands on every screen, and Set Blank / Restore / the half tiles
  write every screen as ONE undo step.
* Once cabinets are selected, a plain click on a cabinet of any selected
  screen selects just that cabinet and Cmd/Ctrl-click toggles it - the
  screen selection is left alone.
* LOCKED screens stay unchanged, but SELECTING is not changing (the
  owner's ruling, 2026-10-16): a marquee or click selects a locked screen's
  cabinets without a word, and the verb that would change them leaves them
  alone and names the screen ("<name> is locked - unlock it to change
  it."). The other screens still go.
* CUSTOM DATA / POWER on a group: a marquee selects cabinets on every member
  it touches, whichever member it starts on and whichever member is current -
  on a wall shaped like the owner's report (20x4 cabinets of 192x384 over 20x1
  of 192x192), and with a member driven from another processor canvas.
* ONE SCREEN behaves exactly as before.

Run locally:
    python -m pytest tests/test_cross_screen_cabinet_select.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project exactly as this module found it
    (see conftest.server_project_guard)."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 1000})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    # Every toast the app raises, in order, for the locked-screen errors.
    pg.evaluate("""() => {
        const app = window.app;
        window.__toasts = [];
        const orig = app._toast;
        app._toast = function (msg) {
            window.__toasts.push(String(msg));
            return orig.apply(this, arguments);
        };
    }""")
    yield pg
    context.close()


MODIFIER = "Meta" if sys.platform == "darwin" else "Control"

# Two ungrouped 2x2 screens of 128px cabinets, 256x256 each, well apart.
PAIR = [
    dict(name='Pair Left', columns=2, rows=2, cabinet_width=128,
         cabinet_height=128, offset_x=0, offset_y=0),
    dict(name='Pair Right', columns=2, rows=2, cabinet_width=128,
         cabinet_height=128, offset_x=600, offset_y=0),
]

# The owner's report, synthetic: 20x4 cabinets of 192x384 over 20x1 of
# 192x192, grouped. Both are 3840 wide; the lower one starts at y 1536.
WALL = [
    dict(name='Wall Upper', columns=20, rows=4, cabinet_width=192,
         cabinet_height=384, offset_x=0, offset_y=0),
    dict(name='Wall Lower', columns=20, rows=1, cabinet_width=192,
         cabinet_height=192, offset_x=0, offset_y=1536),
]

RESET_JS = """async ([specs, opts]) => {
    const app = window.app, r = window.canvasRenderer;
    let project = await (await fetch('/api/project')).json();
    project.layers = [];
    project.groups = [];
    await fetch('/api/project', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(project),
    });
    for (const spec of specs) {
        await fetch('/api/layer/add', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(spec),
        });
    }
    app.project = await (await fetch('/api/project')).json();
    app.dedupeProjectLayers('cross_screen_select_test_reset');
    const screens = app.project.layers.filter(
        l => (l.type || 'screen') === 'screen').slice(0, specs.length);
    const ids = screens.map(l => l.id);
    if (opts.group) {
        app.project.groups = [{ id: 'g_xs', name: 'Cross Wall', layer_ids: ids }];
        screens.forEach(l => { l.group_id = 'g_xs'; });
        await fetch('/api/project', {
            method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(app.project),
        });
    }
    if (opts.custom) {
        screens.forEach(l => {
            l.flowPattern = 'custom';
            l.powerFlowPattern = 'custom';
            app.ensureCustomFlowState(l);
            app.ensureCustomPowerState(l);
        });
    }
    const cur = screens[opts.current || 0];
    app.currentLayer = cur;
    const sel = (opts.selected || [0]).map(i => ids[i]);
    app.selectedLayerIds = new Set(sel);
    app.lastSelectedLayerId = cur.id;
    app.selectionAnchorLayerId = cur.id;
    if (app.customSelection) app.customSelection.clear();
    if (app.powerCustomSelection) app.powerCustomSelection.clear();
    if (app.pixelMapSelection) app.pixelMapSelection.clear();
    r.viewMode = opts.view || 'pixel-map';
    r.zoom = opts.zoom || 0.5; r.panX = 60; r.panY = 60;
    if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
    app.renderLayers();
    app.resetHistory('Cross-screen test reset');
    window.__toasts = [];
    r.render();
    return ids;
}"""


def reset(page, specs, **opts):
    ids = page.evaluate(RESET_JS, [specs, opts])
    page.wait_for_timeout(300)
    assert len(ids) == len(specs), ids
    return ids


def to_client(page, wx, wy):
    pt = page.evaluate("""([wx, wy]) => {
        const r = window.canvasRenderer;
        const rect = r.canvas.getBoundingClientRect();
        const cx = rect.left + wx * r.zoom + r.panX;
        const cy = rect.top + wy * r.zoom + r.panY;
        return { x: cx, y: cy,
                 inside: cx > rect.left && cx < rect.right
                     && cy > rect.top && cy < rect.bottom };
    }""", [wx, wy])
    assert pt['inside'], f'world ({wx}, {wy}) is off the canvas element'
    return pt['x'], pt['y']


def drag(page, start, end, modifier=None):
    sx, sy = to_client(page, *start)
    ex, ey = to_client(page, *end)
    if modifier:
        page.keyboard.down(modifier)
    try:
        page.mouse.move(sx, sy)
        page.mouse.down()
        page.mouse.move((sx + ex) / 2, (sy + ey) / 2, steps=4)
        page.mouse.move(ex, ey, steps=4)
        page.mouse.up()
    finally:
        if modifier:
            page.keyboard.up(modifier)
    page.wait_for_timeout(150)


def click(page, at, modifier=None):
    x, y = to_client(page, *at)
    if modifier:
        page.keyboard.down(modifier)
    try:
        page.mouse.click(x, y)
    finally:
        if modifier:
            page.keyboard.up(modifier)
    page.wait_for_timeout(150)


def state(page, field='pixelMapSelection'):
    return page.evaluate("""(field) => {
        const app = window.app;
        const countEl = document.getElementById('pixel-map-bulk-count');
        return {
            keys: [...(app[field] || [])].sort(),
            selected: [...app.selectedLayerIds].sort((a, b) => a - b),
            current: app.currentLayer ? app.currentLayer.id : null,
            count: countEl ? countEl.textContent : null,
            toasts: window.__toasts.slice(),
        };
    }""", field)


def keys(layer_id, cells):
    return sorted(f'{layer_id}:{r},{c}' for r, c in cells)


def server_panels(page, layer_id):
    return page.evaluate("""async (id) => {
        const p = await (await fetch('/api/project')).json();
        const l = p.layers.find(x => x.id === id);
        return l.panels.map(q => ({ row: q.row, col: q.col,
            hidden: !!q.hidden, halfTile: q.halfTile || 'none' }));
    }""", layer_id)


def local_panels(page, layer_id):
    return page.evaluate("""(id) => {
        const l = window.app.project.layers.find(x => x.id === id);
        return l.panels.map(q => ({ row: q.row, col: q.col,
            hidden: !!q.hidden, halfTile: q.halfTile || 'none' }));
    }""", layer_id)


def cells_where(panels, pred):
    return sorted((p['row'], p['col']) for p in panels if pred(p))


# ═════════════════════════════════════════════════════════════════════════
# Pixel Map: the marquee
# ═════════════════════════════════════════════════════════════════════════

def test_marquee_from_the_other_selected_screen_reaches_both(page):
    """Two ungrouped selected screens; the drag STARTS on the one that is not
    current. It used to need the current screen and stay on it."""
    a, b = reset(page, PAIR, selected=[0, 1], current=0)
    drag(page, (700, 60), (200, 200))
    got = state(page)
    assert got['keys'] == sorted(keys(a, [(0, 1), (1, 1)]) + keys(b, [(0, 0), (1, 0)])), got
    assert got['selected'] == sorted([a, b]), 'the drag changed the screen selection'
    assert got['current'] == a, 'the drag moved currentLayer'
    assert got['count'] == '4', 'the bulk bar does not count both screens'


def test_highlight_lands_on_both_screens(page):
    a, b = reset(page, PAIR, selected=[0, 1], current=0)
    fills = page.evaluate("""([a, b]) => {
        const app = window.app, r = window.canvasRenderer;
        app.pixelMapSelection = new Set([a + ':0,0', b + ':1,1']);
        // Inside a real frame: the transform at the overlay's entry is the
        // world transform, so its inverse maps each fill back to world.
        const ctx = r.ctx, orig = ctx.fillRect, method = r.renderPixelMapSelectionOverlay;
        const out = [];
        let world = null;
        r.renderPixelMapSelectionOverlay = function () {
            world = ctx.getTransform().inverse();
            try { return method.apply(r, arguments); } finally { world = null; }
        };
        ctx.fillRect = function (x, y, w, h) {
            if (world) {
                const p = world.transformPoint(ctx.getTransform().transformPoint(new DOMPoint(x, y)));
                out.push(Math.round(p.x) + ',' + Math.round(p.y));
            }
            return orig.apply(ctx, arguments);
        };
        try { r.render(); } finally { ctx.fillRect = orig; delete r.renderPixelMapSelectionOverlay; }
        return out.sort();
    }""", [a, b])
    assert fills == sorted(['0,0', '728,128']), fills


def test_marquee_across_a_mixed_size_group(page):
    """The owner's wall: the drag starts on the LOWER member (not current) and
    runs up into the upper one. Both members' cabinets are selected."""
    up, low = reset(page, WALL, group=True, selected=[0, 1], current=0, zoom=0.15)
    drag(page, (100, 1600), (500, 1400))
    got = state(page)
    assert got['keys'] == sorted(keys(up, [(3, 0), (3, 1), (3, 2)])
                                 + keys(low, [(0, 0), (0, 1), (0, 2)])), got
    assert got['current'] == up, got
    assert got['count'] == '6', got


def test_an_unselected_screen_is_not_reached(page):
    """Single-screen guard: only the selected screens are in reach."""
    a, b = reset(page, PAIR, selected=[0], current=0)
    drag(page, (60, 60), (700, 200))
    got = state(page)
    assert got['keys'] == keys(a, [(0, 0), (0, 1), (1, 0), (1, 1)]), got
    assert got['selected'] == [a], got


# ═════════════════════════════════════════════════════════════════════════
# Pixel Map: clicks
# ═════════════════════════════════════════════════════════════════════════

def test_click_and_cmd_click_on_the_other_selected_screen(page):
    a, b = reset(page, PAIR, selected=[0, 1], current=0)
    page.evaluate("(a) => window.app.selectOnlyPixelMapPanel("
                  "window.app.getPanelByRowCol(window.app.currentLayer, 0, 0))", a)
    click(page, (664, 64))                          # B R0C0, plain
    got = state(page)
    assert got['keys'] == keys(b, [(0, 0)]), got
    assert got['selected'] == sorted([a, b]), 'a cabinet click narrowed the screens'
    assert got['current'] == a, got

    click(page, (792, 192), modifier=MODIFIER)      # B R1C1 in
    assert state(page)['keys'] == keys(b, [(0, 0), (1, 1)])
    click(page, (64, 192), modifier=MODIFIER)       # A R1C0 in
    assert state(page)['keys'] == sorted(keys(b, [(0, 0), (1, 1)]) + keys(a, [(1, 0)]))
    click(page, (792, 192), modifier=MODIFIER)      # B R1C1 out
    got = state(page)
    assert got['keys'] == sorted(keys(b, [(0, 0)]) + keys(a, [(1, 0)])), got
    assert got['selected'] == sorted([a, b]), got
    assert got['count'] == '2', got


def test_dropping_a_screen_from_the_selection_drops_its_cabinets(page):
    a, b = reset(page, PAIR, selected=[0, 1], current=0)
    got = page.evaluate("""([a, b]) => {
        const app = window.app;
        app.pixelMapSelection = new Set([a + ':0,0', b + ':0,0', b + ':1,1']);
        app.toggleLayerSelection(app.project.layers.find(l => l.id === b));
        return { panels: app.getPixelMapSelectedPanels().length,
                 count: document.getElementById('pixel-map-bulk-count').textContent };
    }""", [a, b])
    assert got == {'panels': 1, 'count': '1'}, got


# ═════════════════════════════════════════════════════════════════════════
# Pixel Map: the bulk verbs, one undo step
# ═════════════════════════════════════════════════════════════════════════

SELECT_BOTH_JS = """([a, b]) => {
    const app = window.app;
    app.pixelMapSelection = new Set([a + ':0,1', a + ':1,1', b + ':0,0', b + ':1,0']);
    return app.getPixelMapSelectedPanels().length;
}"""


def history(page):
    return page.evaluate("() => [window.app.history.length, window.app.historyIndex]")


def test_set_blank_and_restore_across_screens_are_one_undo_step_each(page):
    a, b = reset(page, PAIR, selected=[0, 1], current=0)
    assert page.evaluate(SELECT_BOTH_JS, [a, b]) == 4
    h0 = history(page)
    page.evaluate("async () => { const app = window.app;"
                  " await app.setPanelsBlankBulk(app.getPixelMapSelectedPanels(), true); }")
    page.wait_for_timeout(300)
    assert history(page) == [h0[0] + 1, h0[1] + 1], 'Set Blank is not ONE undo step'
    hidden = lambda p: p['hidden']
    assert cells_where(server_panels(page, a), hidden) == [(0, 1), (1, 1)]
    assert cells_where(server_panels(page, b), hidden) == [(0, 0), (1, 0)]

    page.evaluate("async () => { const app = window.app;"
                  " await app.setPanelsBlankBulk(app.getPixelMapSelectedPanels(), false); }")
    page.wait_for_timeout(300)
    assert history(page) == [h0[0] + 2, h0[1] + 2], 'Restore is not ONE undo step'
    assert cells_where(server_panels(page, a), hidden) == []
    assert cells_where(server_panels(page, b), hidden) == []

    page.evaluate("() => window.app.undo()")        # back to blank, both screens
    page.wait_for_timeout(500)
    assert cells_where(local_panels(page, a), hidden) == [(0, 1), (1, 1)]
    assert cells_where(local_panels(page, b), hidden) == [(0, 0), (1, 0)]
    page.evaluate("() => window.app.undo()")        # one more: both full again
    page.wait_for_timeout(500)
    assert cells_where(local_panels(page, a), hidden) == []
    assert cells_where(local_panels(page, b), hidden) == []
    assert cells_where(server_panels(page, b), hidden) == []


def test_half_tile_across_screens_is_one_undo_step(page):
    a, b = reset(page, PAIR, selected=[0, 1], current=0)
    page.evaluate(SELECT_BOTH_JS, [a, b])
    h0 = history(page)
    page.evaluate("async () => { const app = window.app;"
                  " await app.setPanelsHalfTileBulk(app.getPixelMapSelectedPanels(), 'width'); }")
    page.wait_for_timeout(300)
    assert history(page) == [h0[0] + 1, h0[1] + 1]
    half = lambda p: p['halfTile'] == 'width'
    assert cells_where(server_panels(page, a), half) == [(0, 1), (1, 1)]
    assert cells_where(server_panels(page, b), half) == [(0, 0), (1, 0)]
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(500)
    assert cells_where(local_panels(page, a), half) == []
    assert cells_where(local_panels(page, b), half) == []


# ═════════════════════════════════════════════════════════════════════════
# Locked screens
# ═════════════════════════════════════════════════════════════════════════

def lock(page, layer_id):
    page.evaluate("(id) => { window.app.project.layers.find(l => l.id === id).locked = true; }",
                  layer_id)


def test_a_locked_screen_is_selected_by_the_marquee_without_an_error(page):
    # Selecting is not changing: the locked screen's cabinets join the
    # selection quietly; Set Blank is what names it.
    a, b = reset(page, PAIR, selected=[0, 1], current=0)
    lock(page, b)
    drag(page, (200, 60), (700, 200))
    got = state(page)
    assert got['keys'] == sorted(keys(a, [(0, 1), (1, 1)]) + keys(b, [(0, 0), (1, 0)])), got
    assert got['toasts'] == [], got


def test_a_bulk_verb_skips_a_locked_screen_and_names_it(page):
    a, b = reset(page, PAIR, selected=[0, 1], current=0)
    panels_js = """([a, b]) => {
        const app = window.app;
        const A = app.project.layers.find(l => l.id === a);
        const B = app.project.layers.find(l => l.id === b);
        window.__bulk = [A.panels[0], B.panels[0]];
    }"""
    page.evaluate(panels_js, [a, b])
    lock(page, b)
    h0 = history(page)
    page.evaluate("async () => { await window.app.setPanelsBlankBulk(window.__bulk, true); }")
    page.wait_for_timeout(300)
    hidden = lambda p: p['hidden']
    assert cells_where(server_panels(page, a), hidden) == [(0, 0)]
    assert cells_where(server_panels(page, b), hidden) == [], 'the locked screen changed'
    assert cells_where(local_panels(page, b), hidden) == []
    assert history(page)[0] == h0[0] + 1
    assert state(page)['toasts'] == ['Pair Right is locked - unlock it to change it.']


def test_a_click_on_a_locked_cabinet_selects_it_quietly(page):
    a, b = reset(page, PAIR, selected=[0, 1], current=0)
    page.evaluate("() => window.app.selectOnlyPixelMapPanel("
                  "window.app.getPanelByRowCol(window.app.currentLayer, 0, 0))")
    lock(page, b)
    click(page, (664, 64))
    got = state(page)
    assert got['keys'] == keys(b, [(0, 0)]), got
    assert got['toasts'] == [], got


def test_custom_marquee_selects_a_locked_member_quietly(page):
    up, low = reset(page, WALL, group=True, custom=True, selected=[0, 1],
                    current=0, view='data-flow', zoom=0.15)
    lock(page, low)
    drag(page, (100, 1300), (500, 1650))
    got = state(page, 'customSelection')
    assert got['keys'] == sorted(keys(up, [(3, 0), (3, 1), (3, 2)])
                              + keys(low, [(0, 0), (0, 1), (0, 2)])), got
    assert got['toasts'] == [], got


# ═════════════════════════════════════════════════════════════════════════
# Custom data and power on a group
# ═════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize('view,field', [('data-flow', 'customSelection'),
                                        ('power', 'powerCustomSelection')])
@pytest.mark.parametrize('current,start,end', [
    (0, (100, 1600), (500, 1400)),     # upper current, drag starts on the lower
    (1, (500, 1400), (100, 1600)),     # lower current, drag starts on the upper
])
def test_custom_marquee_starting_on_the_other_member(page, view, field, current, start, end):
    up, low = reset(page, WALL, group=True, custom=True, selected=[0, 1],
                    current=current, view=view, zoom=0.15)
    drag(page, start, end)
    got = state(page, field)
    assert got['keys'] == sorted(keys(up, [(3, 0), (3, 1), (3, 2)])
                                 + keys(low, [(0, 0), (0, 1), (0, 2)])), got
    assert got['current'] == (up, low)[current], 'the drag moved the path owner'


def test_custom_marquee_on_a_member_driven_from_another_canvas(page):
    """The lower member is driven from a second processor canvas but shown on
    the same show canvas, so a run can reach it. Pressing on it used to
    activate its processor canvas, which culled the owner from the selection
    and handed the path to the member."""
    up, low = reset(page, WALL, group=True, custom=True, selected=[0, 1],
                    current=0, view='data-flow', zoom=0.15)
    page.evaluate("""(low) => {
        const app = window.app;
        const c1 = app.project.canvases[0];
        app.project.canvases.push(Object.assign({}, c1,
            { id: 'c_xs2', name: 'Second', workspace_x: 9000, workspace_y: 0 }));
        const L = app.project.layers.find(l => l.id === low);
        L.show_canvas_id = c1.id;
        L.canvas_id = 'c_xs2';
        window.canvasRenderer.render();
    }""", low)
    assert page.evaluate("(id) => window.app.canPathReachLayer(window.app.currentLayer,"
                         " window.app.project.layers.find(l => l.id === id))", low)
    drag(page, (100, 1600), (500, 1400))
    got = state(page, 'customSelection')
    assert got['current'] == up, got
    assert got['selected'] == sorted([up, low]), got
    assert got['keys'] == sorted(keys(up, [(3, 0), (3, 1), (3, 2)])
                                 + keys(low, [(0, 0), (0, 1), (0, 2)])), got


def test_custom_runs_still_do_not_cross_ungrouped_screens(page):
    a, b = reset(page, PAIR, custom=True, selected=[0, 1], current=0, view='data-flow')
    drag(page, (60, 60), (700, 200))
    got = state(page, 'customSelection')
    assert got['keys'] == keys(a, [(0, 0), (0, 1), (1, 0), (1, 1)]), got


# ═════════════════════════════════════════════════════════════════════════
# One screen: exactly as before
# ═════════════════════════════════════════════════════════════════════════

def test_single_screen_marquee_click_and_toggle_are_unchanged(page):
    (a,) = reset(page, PAIR[:1], selected=[0], current=0)
    drag(page, (60, 60), (200, 200))
    assert state(page)['keys'] == keys(a, [(0, 0), (0, 1), (1, 0), (1, 1)])
    click(page, (64, 64))
    got = state(page)
    assert got['keys'] == keys(a, [(0, 0)]) and got['count'] == '1', got
    click(page, (192, 192), modifier=MODIFIER)
    assert state(page)['keys'] == keys(a, [(0, 0), (1, 1)])
    click(page, (64, 64), modifier=MODIFIER)
    assert state(page)['keys'] == keys(a, [(1, 1)])
    h0 = history(page)
    page.evaluate("async () => { const app = window.app;"
                  " await app.setPanelsBlankBulk(app.getPixelMapSelectedPanels(), true); }")
    page.wait_for_timeout(300)
    assert history(page)[0] == h0[0] + 1
    assert cells_where(server_panels(page, a), lambda p: p['hidden']) == [(1, 1)]
    assert state(page)['toasts'] == []


# ═════════════════════════════════════════════════════════════════════════
# Alt-paint (no selection) and locked screens
# ═════════════════════════════════════════════════════════════════════════

def test_alt_paint_leaves_a_locked_screen_unchanged(page):
    """Alt+press/drag with no cabinet selection paints blanks on one screen.
    On a locked screen it paints nothing and names the screen."""
    a, b = reset(page, PAIR, selected=[0, 1], current=0)
    lock(page, b)
    h0 = history(page)
    sx, sy = to_client(page, 664, 64)
    ex, ey = to_client(page, 792, 192)
    page.keyboard.down('Alt')
    try:
        page.mouse.move(sx, sy)
        page.mouse.down()
        page.mouse.move(ex, ey, steps=4)
        page.mouse.up()
    finally:
        page.keyboard.up('Alt')
    page.wait_for_timeout(300)
    hidden = lambda p: p['hidden']
    assert cells_where(local_panels(page, b), hidden) == []
    assert cells_where(server_panels(page, b), hidden) == []
    assert history(page)[0] == h0[0]
    assert state(page)['toasts'] == ['Pair Right is locked - unlock it to change it.']

    # The unlocked screen still paints.
    sx, sy = to_client(page, 64, 64)
    page.keyboard.down('Alt')
    try:
        page.mouse.click(sx, sy)
    finally:
        page.keyboard.up('Alt')
    page.wait_for_timeout(300)
    assert cells_where(server_panels(page, a), hidden) == [(0, 0)]
