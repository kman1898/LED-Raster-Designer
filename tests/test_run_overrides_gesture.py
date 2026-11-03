"""Per-run overrides - the GESTURE (held Alt, click, right-click, Esc, undo).

The user's own words for the affordance: "when we hold a certain key it will
highlight whatever your mouse goes over". The key is Alt (Option) - Space
pans, Shift multi-selects, and Alt's only canvas meaning is Pixel Map's
blank-painting, which does not exist in Data Flow / Power.

Pinned here, in a real browser with real mouse and keyboard events:

* HOLD ALT, HOVER A RUN - the run lights (the same underlay the dock drag
  paints); release Alt, or move off every run, and it goes out.
* ALT+CLICK an automatic run - it becomes overridden, seeded with exactly
  the cabinets it already carried (nothing on the canvas moves), and the
  path-editing session opens on that port: the custom controls show, the
  active port is the clicked one.
* A PLAIN CLICK while editing extends the drawn path - the existing tools
  ARE the editing mode.
* ESC closes the editing session; the override and its path stay.
* RIGHT-CLICK a run arms "Redraw <run>", and on an overridden run also
  "<run> back to auto"; back-to-auto re-flows the screen to its automatic
  baseline. Only what applies is offered.
* UNDO walks each transition back one named step at a time.

Run locally:
    python -m pytest tests/test_run_overrides_gesture.py -v --browser chromium
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
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.evaluate(HELPERS_JS)
    yield pg
    context.close()


# One 4x6 screen of 256px cabinets on COEX 1G - three organized data ports of
# two rows each (see test_run_overrides_engine.py for the arithmetic), so a
# hover in row 0 and a hover in row 2 land on DIFFERENT runs.
HELPERS_JS = """
window.__ovrg = {
    async reset(view) {
        const app = window.app, r = window.canvasRenderer;
        let project = await (await fetch('/api/project')).json();
        project.layers = [];
        project.groups = [];
        await fetch('/api/project', {
            method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(project),
        });
        await fetch('/api/layer/add', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                name: 'OvrGesture',
                columns: 4, rows: 6, cabinet_width: 256, cabinet_height: 256,
                offset_x: 0, offset_y: 0,
            }),
        });
        app.project = await (await fetch('/api/project')).json();
        app.dedupeProjectLayers('run_override_gesture_reset');
        const layer = app.project.layers.filter(
            l => (l.type || 'screen') === 'screen')[0];
        layer.flowPattern = 'tl-h';
        layer.powerFlowPattern = 'tl-h';
        layer.powerOrganized = false;
        layer.powerMaximize = false;
        layer.powerVoltage = 208;
        layer.powerAmperage = 20;
        layer.panelWatts = 1000;
        layer.processorType = 'novastar-coex-1g';
        layer.bitDepth = 8;
        layer.frameRate = 60;
        layer.customPortPaths = {};
        layer.customPortOverrides = [];
        layer.powerCustomPaths = {};
        layer.powerCustomOverrides = [];
        app.currentLayer = layer;
        app.selectedLayerIds = new Set([layer.id]);
        app._overrideEditing = null;
        app._overrideHover = null;
        if (app.customSelection) app.customSelection.clear();
        if (app.powerCustomSelection) app.powerCustomSelection.clear();
        // A context menu left open by the previous test sits OVER the canvas
        // and would swallow this test's clicks.
        if (typeof app.hideContextMenu === 'function') app.hideContextMenu();
        // Deterministic camera: the 1024x1536 world fits the canvas at 0.25.
        r.viewMode = view;
        r.zoom = 0.25; r.panX = 60; r.panY = 60;
        r.render();
        if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
        app.resetHistory('Gesture Test Baseline');
        return { id: layer.id };
    },

    layer(id) {
        return window.app.project.layers.find(l => l.id === id);
    },

    dataMap(id) {
        const app = window.app, layer = this.layer(id);
        return (app.calculatePortAssignments(layer) || []).map(it => ({
            port: it.port, row: it.panel.row, col: it.panel.col,
        }));
    },

    state(id) {
        const app = window.app, layer = this.layer(id);
        const controls = document.getElementById('custom-flow-controls');
        return {
            hover: app._overrideHover || null,
            editing: app._overrideEditing || null,
            overrides: app.getOverrideNums(layer, 'data'),
            powerOverrides: app.getOverrideNums(layer, 'power'),
            activePort: layer.customPortIndex || 1,
            path: ((layer.customPortPaths || {})[layer.customPortIndex] || [])
                .map(e => [e.row, e.col]),
            controlsShown: !!(controls && controls.style.display !== 'none'),
            historyAction: (app.history && app.history[app.historyIndex])
                ? app.history[app.historyIndex].action : null,
        };
    },
};
"""


def reset(page, view='data-flow'):
    state = page.evaluate("(v) => window.__ovrg.reset(v)", view)
    page.wait_for_timeout(400)
    return state['id']


def world_to_client(page, wx, wy):
    pt = page.evaluate("""([wx, wy]) => {
        const r = window.canvasRenderer;
        const rect = r.canvas.getBoundingClientRect();
        return { x: rect.left + wx * r.zoom + r.panX,
                 y: rect.top + wy * r.zoom + r.panY };
    }""", [wx, wy])
    return pt['x'], pt['y']


def cabinet_center(row, col):
    return col * 256 + 128, row * 256 + 128


def app_state(page, layer_id):
    return page.evaluate("(id) => window.__ovrg.state(id)", layer_id)


def data_map(page, layer_id):
    return page.evaluate("(id) => window.__ovrg.dataMap(id)", layer_id)


def _refill(page, layer_id, port, pattern):
    """Select the port's own cabinets and apply `pattern` - the redraw a
    taken-over run may make on an automatic screen."""
    n = page.evaluate("""([id, port]) => { const app = window.app, l = window.__ovrg.layer(id);
        app.customSelection.clear();
        (app.calculatePortAssignments(l) || []).filter(it => it.port === port)
            .forEach(it => app.customSelection.add(app.getScopedPanelKey(l.id, it.panel)));
        return app.customSelection.size; }""", [layer_id, port])
    assert n > 0
    assert page.evaluate("(p) => window.app._applyPatternFill('data', p)", pattern)
    page.wait_for_timeout(300)


def port_of_cabinet(base, row, col):
    return next(r['port'] for r in base if r['row'] == row and r['col'] == col)


# ── the highlight ─────────────────────────────────────────────────────────

def test_held_alt_lights_the_run_under_the_cursor(page):
    lid = reset(page)
    base = data_map(page, lid)
    x, y = world_to_client(page, *cabinet_center(0, 1))
    page.mouse.move(x, y)
    assert app_state(page, lid)['hover'] is None, "lit without the key held"
    page.keyboard.down('Alt')
    page.wait_for_timeout(100)
    hover = app_state(page, lid)['hover']
    assert hover == {'layerId': lid, 'num': port_of_cabinet(base, 0, 1),
                     'kind': 'data'}
    # moving to a cabinet of ANOTHER run moves the light with it
    x2, y2 = world_to_client(page, *cabinet_center(4, 1))
    page.mouse.move(x2, y2)
    page.wait_for_timeout(100)
    hover = app_state(page, lid)['hover']
    assert hover['num'] == port_of_cabinet(base, 4, 1)
    assert hover['num'] != port_of_cabinet(base, 0, 1)
    # and the renderer agrees this is the lit run - same test the underlay
    # paint makes
    lit = page.evaluate("""([id, num]) => window.canvasRenderer._runUnderlayLit(
        window.__ovrg.layer(id), num)""", [lid, hover['num']])
    assert lit is True
    page.keyboard.up('Alt')
    page.wait_for_timeout(100)
    assert app_state(page, lid)['hover'] is None, "the light outlived the key"


def test_the_light_goes_out_off_the_wall(page):
    lid = reset(page)
    page.keyboard.down('Alt')
    x, y = world_to_client(page, *cabinet_center(0, 0))
    page.mouse.move(x, y)
    page.wait_for_timeout(100)
    assert app_state(page, lid)['hover'] is not None
    # empty canvas to the RIGHT of the wall - negative world coords would
    # leave the canvas element and no mousemove would fire at all
    ex, ey = world_to_client(page, 1600, 200)
    page.mouse.move(ex, ey)
    page.wait_for_timeout(100)
    assert app_state(page, lid)['hover'] is None
    page.keyboard.up('Alt')


# ── alt+click: take the run over ──────────────────────────────────────────

def test_alt_click_overrides_the_run_and_opens_editing(page):
    lid = reset(page)
    base = data_map(page, lid)
    target = port_of_cabinet(base, 2, 1)
    x, y = world_to_client(page, *cabinet_center(2, 1))
    page.keyboard.down('Alt')
    page.mouse.click(x, y)
    page.keyboard.up('Alt')
    page.wait_for_timeout(300)
    st = app_state(page, lid)
    assert st['overrides'] == [target]
    assert st['editing'] == {'layerId': lid, 'kind': 'data', 'num': target}
    assert st['activePort'] == target
    assert st['controlsShown'] is True, "the editing tools did not open"
    assert st['historyAction'] == 'Override Port'
    # seeded with the run's own cabinets: the drawing has not moved
    assert data_map(page, lid) == base
    seeded = st['path']
    walked = [[r['row'], r['col']] for r in base if r['port'] == target]
    assert seeded == walked


def test_a_plain_click_on_another_ports_cabinet_is_refused(page):
    """The owner, 2026-10-20: a redraw may not put wiring on a cabinet that
    already has cabling - "this is an error" - and "we need the same
    redraws for data too". A cabinet the next automatic port carries is
    refused, named, and nothing moves. (It used to be pulled onto the
    override while the walk re-flowed around it.)"""
    lid = reset(page)
    base = data_map(page, lid)
    x, y = world_to_client(page, *cabinet_center(2, 1))
    page.keyboard.down('Alt')
    page.mouse.click(x, y)
    page.keyboard.up('Alt')
    page.wait_for_timeout(300)
    before = app_state(page, lid)
    page.evaluate("""() => { window.__errs = [];
        const real = window.app._toast.bind(window.app);
        window.app._toast = (m, err, ms) => { if (err) window.__errs.push(m); return real(m, err, ms); }; }""")
    tx, ty = world_to_client(page, *cabinet_center(4, 0))
    page.mouse.click(tx, ty)
    page.wait_for_timeout(300)
    st = app_state(page, lid)
    assert st['path'] == before['path'], st
    assert st['historyAction'] == before['historyAction'], st
    assert data_map(page, lid) == base
    errs = page.evaluate("() => window.__errs")
    assert errs and 'already wired' in errs[0], errs


def test_esc_closes_editing_and_keeps_the_override(page):
    lid = reset(page)
    base = data_map(page, lid)
    x, y = world_to_client(page, *cabinet_center(0, 0))
    page.keyboard.down('Alt')
    page.mouse.click(x, y)
    page.keyboard.up('Alt')
    page.wait_for_timeout(300)
    assert app_state(page, lid)['editing'] is not None
    page.keyboard.press('Escape')
    page.wait_for_timeout(200)
    st = app_state(page, lid)
    assert st['editing'] is None
    assert st['overrides'] == [port_of_cabinet(base, 0, 0)]
    assert st['controlsShown'] is False
    assert data_map(page, lid) == base


# ── right-click: only what applies ───────────────────────────────────────

def test_right_click_offers_redraw_and_scoped_back_to_auto(page):
    lid = reset(page)
    base = data_map(page, lid)
    x, y = world_to_client(page, *cabinet_center(0, 1))
    # on an AUTOMATIC run: redraw is offered, back-to-auto is not
    offers = page.evaluate("""([x, y]) => {
        const m = window.app._prepareOverrideMenu(x, y);
        return m ? { redraw: !!m.redraw, back: !!m.backToAuto,
                     label: m.redraw && m.redraw.label } : null;
    }""", [x, y])
    assert offers == {'redraw': True, 'back': False,
                      'label': f"Redraw port P{port_of_cabinet(base, 0, 1)}"}
    # the real menu shows the same story
    page.mouse.click(x, y, button='right')
    page.wait_for_timeout(200)
    shown = page.evaluate("""() => {
        const q = (sel) => {
            const el = document.querySelector(sel);
            return !!(el && el.style.display !== 'none');
        };
        return {
            redraw: q('[data-action="ovr-redraw"]'),
            back: q('[data-action="ovr-auto"]'),
        };
    }""")
    assert shown == {'redraw': True, 'back': False}
    page.keyboard.press('Escape')
    # take the run over, then the SAME right-click offers the way back
    page.evaluate("""([id, num]) => window.app.overrideRun(
        window.__ovrg.layer(id), 'data', num)""",
        [lid, port_of_cabinet(base, 0, 1)])
    page.wait_for_timeout(200)
    offers = page.evaluate("""([x, y]) => {
        const m = window.app._prepareOverrideMenu(x, y);
        return m ? { redraw: !!m.redraw, back: !!m.backToAuto } : null;
    }""", [x, y])
    assert offers == {'redraw': True, 'back': True}
    # empty canvas offers neither
    ex, ey = world_to_client(page, 1600, 200)
    assert page.evaluate(
        "([x, y]) => window.app._prepareOverrideMenu(x, y)", [ex, ey]) is None


def test_back_to_auto_reflows_to_the_baseline(page):
    lid = reset(page)
    base = data_map(page, lid)
    target = port_of_cabinet(base, 2, 1)
    x, y = world_to_client(page, *cabinet_center(2, 1))
    page.keyboard.down('Alt')
    page.mouse.click(x, y)
    page.keyboard.up('Alt')
    page.wait_for_timeout(300)
    # redraw it so back-to-auto has something real to undo: its own
    # cabinets walked the other way (a redraw may not take another port's)
    _refill(page, lid, target, 'tl-v')
    assert data_map(page, lid) != base
    page.evaluate("""([x, y]) => {
        const m = window.app._prepareOverrideMenu(x, y);
        m.backToAuto.run();
    }""", [x, y])
    page.wait_for_timeout(300)
    st = app_state(page, lid)
    assert st['overrides'] == []
    assert st['historyAction'] == 'Return Port To Auto'
    assert data_map(page, lid) == base


# ── undo walks each step back ────────────────────────────────────────────

def test_undo_walks_the_transitions_back_one_named_step_at_a_time(page):
    lid = reset(page)
    base = data_map(page, lid)
    target = port_of_cabinet(base, 2, 1)
    x, y = world_to_client(page, *cabinet_center(2, 1))
    page.keyboard.down('Alt')
    page.mouse.click(x, y)
    page.keyboard.up('Alt')
    page.wait_for_timeout(300)
    _refill(page, lid, target, 'tl-v')
    assert data_map(page, lid) != base
    assert app_state(page, lid)['historyAction'] == 'Custom Pattern Apply'
    # one undo: the redraw comes off, the override stays
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(300)
    st = app_state(page, lid)
    assert st['overrides'] == [target]
    assert data_map(page, lid) == base
    # second undo: the override itself comes off
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(300)
    st = app_state(page, lid)
    assert st['overrides'] == []
    assert data_map(page, lid) == base


# ── power view speaks the same gesture ───────────────────────────────────

def test_alt_click_in_power_view_overrides_the_circuit(page):
    lid = reset(page, view='power')
    x, y = world_to_client(page, *cabinet_center(0, 0))
    page.keyboard.down('Alt')
    page.mouse.move(x, y)
    page.wait_for_timeout(150)
    hover = app_state(page, lid)['hover']
    assert hover is not None and hover['kind'] == 'power'
    page.mouse.click(x, y)
    page.keyboard.up('Alt')
    page.wait_for_timeout(300)
    st = app_state(page, lid)
    assert st['powerOverrides'] == [hover['num']]
    assert st['editing'] == {'layerId': lid, 'kind': 'power',
                             'num': hover['num']}
    assert st['historyAction'] == 'Override Circuit'


def test_an_old_custom_drawing_does_not_block_a_data_redraw(page):
    """A screen switched back from custom keeps its old port drawing,
    unused: a redraw's fill over the taken-over port's own cabinets lands
    with no "already wired" refusal (2026-10-20, the data twin of the power
    fix)."""
    lid = reset(page)
    base = data_map(page, lid)
    target = port_of_cabinet(base, 2, 1)
    # the dormant drawing: every cabinet on some other port number
    page.evaluate("""(id) => { const l = window.__ovrg.layer(id);
        l.customPortPaths = { 9: l.panels.map(p => ({ row: p.row, col: p.col })) }; }""", lid)
    x, y = world_to_client(page, *cabinet_center(2, 1))
    page.keyboard.down('Alt')
    page.mouse.click(x, y)
    page.keyboard.up('Alt')
    page.wait_for_timeout(300)
    page.evaluate("""() => { window.__errs = [];
        const real = window.app._toast.bind(window.app);
        window.app._toast = (m, err, ms) => { if (err) window.__errs.push(m); return real(m, err, ms); }; }""")
    picked = page.evaluate("""([id, port]) => { const app = window.app, l = window.__ovrg.layer(id);
        app.customSelection.clear();
        (app.calculatePortAssignments(l) || []).filter(it => it.port === port)
            .forEach(it => app.customSelection.add(app.getScopedPanelKey(l.id, it.panel)));
        return app.customSelection.size; }""", [lid, target])
    assert picked > 0
    ok = page.evaluate("() => window.app._applyPatternFill('data', 'tl-h')")
    page.wait_for_timeout(300)
    assert ok, page.evaluate("() => window.__errs")
    assert page.evaluate("() => window.__errs") == []


# ── a single redraw holds its cabinets (QA, 1.6.0) ────────────────────────
#
# Taken over on an automatic screen, a port kept its cabinets but every
# other cabinet was the walk's: a click on another port's was refused, a
# click on its own did nothing, and Clear Port gave its cabinets straight
# back to the walk. The port now holds what it carried while it is open,
# a click on one of its steps cuts the path back to it, and the cabinets
# cut off are drawn again in any order.

def _alt_click(page, row, col):
    x, y = world_to_client(page, *cabinet_center(row, col))
    page.keyboard.down('Alt')
    page.mouse.click(x, y)
    page.keyboard.up('Alt')
    page.wait_for_timeout(300)


def _click(page, row, col):
    x, y = world_to_client(page, *cabinet_center(row, col))
    page.mouse.click(x, y)
    page.wait_for_timeout(150)


def _watch_toasts(page):
    page.evaluate("""() => { window.__errs = []; window.__notes = [];
        if (window.app.__ovrgToastWrapped) return;
        const real = window.app._toast.bind(window.app);
        window.app._toast = (m, err, ms) => {
            (err ? window.__errs : window.__notes).push(m); return real(m, err, ms); };
        window.app.__ovrgToastWrapped = true; }""")


def _wired(page, layer_id):
    return {(r['row'], r['col']): r['port'] for r in data_map(page, layer_id)}


def test_a_click_on_its_own_step_cuts_back_and_the_cabinets_stay_free(page):
    lid = reset(page)
    base = data_map(page, lid)
    target = port_of_cabinet(base, 2, 1)
    _alt_click(page, 2, 1)
    _watch_toasts(page)
    seeded = [tuple(c) for c in app_state(page, lid)['path']]
    assert len(seeded) == 8
    _click(page, *seeded[0])
    st = app_state(page, lid)
    assert st['path'] == [list(seeded[0])]
    assert st['historyAction'] == 'Custom Path Edit'
    # the cabinets cut off are the port's still: not re-walked, ringed
    wired = _wired(page, lid)
    assert all(c not in wired for c in seeded[1:]), wired
    others = {(r['row'], r['col']): r['port'] for r in base if r['port'] != target}
    assert {c: p for c, p in wired.items() if c not in seeded} == others
    ringed = page.evaluate("""(id) => window.app.mergeFreedPanels(window.__ovrg.layer(id))
        .map(p => [p.row, p.col]).sort()""", lid)
    assert sorted(tuple(c) for c in ringed) == sorted(seeded[1:])
    # drawn again in a new order, every click accepted
    redrawn = [seeded[0]] + list(reversed(seeded[1:]))
    for c in redrawn[1:]:
        _click(page, *c)
    st = app_state(page, lid)
    assert [tuple(c) for c in st['path']] == redrawn
    assert page.evaluate("() => window.__errs") == []
    page.keyboard.press('Escape')
    page.wait_for_timeout(200)
    st = app_state(page, lid)
    assert st['editing'] is None and st['overrides'] == [target]
    wired = _wired(page, lid)
    assert {c: p for c, p in wired.items() if c not in seeded} == others
    assert all(wired[c] == target for c in seeded)
    # another port's cabinet is still refused while a redraw is open
    _alt_click(page, 2, 1)
    _click(page, 4, 0)
    assert page.evaluate("() => window.__errs") and 'already wired' in page.evaluate(
        "() => window.__errs")[-1]
    page.keyboard.press('Escape')


def test_clear_port_keeps_the_cabinets_and_esc_says_where_leftovers_went(page):
    lid = reset(page)
    base = data_map(page, lid)
    target = port_of_cabinet(base, 2, 1)
    _alt_click(page, 2, 1)
    _watch_toasts(page)
    seeded = [tuple(c) for c in app_state(page, lid)['path']]
    # the Clear Port button of the custom controls (the panel may sit
    # below the fold of this viewport)
    page.evaluate("() => document.getElementById('custom-clear-port').click()")
    page.wait_for_timeout(300)
    assert app_state(page, lid)['path'] == []
    assert all(c not in _wired(page, lid) for c in seeded), 'the walk took them back'
    for c in seeded[:3]:
        _click(page, *c)
    assert [tuple(c) for c in app_state(page, lid)['path']] == seeded[:3]
    assert page.evaluate("() => window.__errs") == []
    page.keyboard.press('Escape')
    page.wait_for_timeout(300)
    wired = _wired(page, lid)
    went = sorted({wired[c] for c in seeded[3:]})
    assert all(wired[c] == target for c in seeded[:3])
    if len(went) == 1:
        where = 'port P%d' % went[0]
    elif went == list(range(went[0], went[-1] + 1)):
        where = 'ports P%d-P%d' % (went[0], went[-1])
    else:
        where = 'ports ' + ', '.join('P%d' % n for n in went)
    assert page.evaluate("() => window.__notes")[-1] == \
        '5 cabinets left over went to %s.' % where, page.evaluate("() => window.__notes")


def test_esc_ends_the_redraw_with_a_side_panel_field_focused(page):
    lid = reset(page)
    _alt_click(page, 2, 1)
    assert app_state(page, lid)['editing'] is not None
    page.locator('#screen-name-size').click()
    assert page.evaluate("() => document.activeElement.id") == 'screen-name-size'
    page.keyboard.press('Escape')
    page.wait_for_timeout(200)
    assert app_state(page, lid)['editing'] is None


def test_redraw_on_a_mirror_screen_is_refused_out_loud(page):
    lid = reset(page)
    mid = page.evaluate("""async (src) => {
        const app = window.app;
        const res = await fetch('/api/layer/add', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ name: 'OvrMirror', columns: 4, rows: 6,
                cabinet_width: 256, cabinet_height: 256, offset_x: 0, offset_y: 1700 }),
        });
        const id = (await res.json()).id;
        app.project = await (await fetch('/api/project')).json();
        app.dedupeProjectLayers('run_override_gesture_mirror');
        const m = window.__ovrg.layer(id);
        m.processorType = 'novastar-coex-1g';
        m.dataMirrorOf = src;
        return id;
    }""", lid)
    _watch_toasts(page)
    page.evaluate("(id) => window.app.overrideRun(window.__ovrg.layer(id), 'data', 1)", mid)
    errs = page.evaluate("() => window.__errs")
    assert errs and 'OvrGesture' in errs[-1], errs
    assert page.evaluate("(id) => window.app.getOverrideNums(window.__ovrg.layer(id), 'data')", mid) == []
    assert page.evaluate("() => window.app._overrideEditing") is None


def test_the_fill_readout_ignores_an_unused_old_drawing(page):
    """On a rectangle processor "full" means no free cabinet would still be
    accepted. A drawing an automatic screen kept from an earlier custom
    spell is not in use, and counting its cabinets as taken read "full" on
    a port with room to spare."""
    lid = reset(page)
    grows = page.evaluate("""(id) => {
        const app = window.app, l = window.__ovrg.layer(id);
        l.processorType = 'novastar-armor';
        l.customPortPaths = { 9: l.panels.map(p => ({ row: p.row, col: p.col })) };
        const hits = [{ layer: l, panel: l.panels.find(p => p.row === 0 && p.col === 0) }];
        return app._customRunCanGrow(l, 'data', hits);
    }""", lid)
    assert grows is True
