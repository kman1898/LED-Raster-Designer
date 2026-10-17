"""A locked screen stays unchanged; picking it is not a change (1.5 audit).

The owner's ruling (2026-10-16): "If it's locked it stays locked and
unchanged until unlocked. If you try to change it shows an error dialog and
tells why it can't change." The lock guards EVERYTHING, not only position:
every action that would modify a locked screen leaves it alone and shows the
one locked error naming it ("<name> is locked - unlock it to change it."),
the unlocked screens of the same action still take it, and an action that
would change nothing says nothing. SELECTING a locked screen or its cabinets
is not a change, so it is never an error.

Also pinned here, from the same audit, on Pixel Map selection:
* a click is measured in screen pixels (4 px, the dock's threshold), not
  world units, so a 1 px jitter at low zoom is still a click;
* a hidden current screen is out of the cabinet scope unless it is the only
  screen in play;
* cabinet lookups by row/col are indexed, not a linear search per key;
* the render path only reads the cabinet selection; it is pruned on a real
  selection change.

And from the re-audit: a live control (typing, a slider drag) over a mixed
selection writes the unlocked screens, says the error once per attempt and
never repaints the field mid-edit; Clear card keeps a locked screen's ports
with one undo step; a canvas move never takes a member out of a wall that has
a locked member.

Driven through real mouse and keyboard gestures wherever the gesture itself
is under test.

Run locally:
    python -m pytest tests/test_lock_guards_and_select.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from conftest import settled  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project exactly as this module found it."""


FIT_COUNTER_JS = """
    window.__fits = 0;
    let cr = null;
    Object.defineProperty(window, 'canvasRenderer', {
        configurable: true,
        get() { return cr; },
        set(v) {
            cr = v;
            if (v && typeof v.fitToView === 'function' && !v.__fitCounted) {
                const fit = v.fitToView.bind(v);
                v.fitToView = function () { window.__fits++; return fit(...arguments); };
                v.__fitCounted = true;
            }
        },
    });
"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 1000})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
    )
    # Count the renderer's fits: the app fits the view a moment after it
    # loads, and a fit landing between two clicks of a test moves the wall
    # under the pointer. The page is ready once that first fit has run.
    context.add_init_script(FIT_COUNTER_JS)
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app.project"
                         " && window.app._initialLoadComplete === true"
                         " && window.canvasRenderer && window.__fits > 0"
                         " && window.canvasRenderer.zoom > 0", timeout=20000)
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


def locked_msg(*names):
    if len(names) == 1:
        return f'{names[0]} is locked - unlock it to change it.'
    return (', '.join(names[:-1]) + ' and ' + names[-1]
            + ' are locked - unlock them to change them.')


# Three ungrouped 2x2 screens of 128 px cabinets, side by side and apart.
TRIO = [
    dict(name='Lock A', columns=2, rows=2, cabinet_width=128,
         cabinet_height=128, offset_x=0, offset_y=0),
    dict(name='Lock B', columns=2, rows=2, cabinet_width=128,
         cabinet_height=128, offset_x=600, offset_y=0),
    dict(name='Lock C', columns=2, rows=2, cabinet_width=128,
         cabinet_height=128, offset_x=1200, offset_y=0),
]

RESET_JS = """async ([specs, opts]) => {
    const app = window.app, r = window.canvasRenderer;
    await app._layerSavesSettled();
    let project = await (await fetch('/api/project')).json();
    project.layers = [];
    project.groups = [];
    project.distros = [];
    // One canvas, active: a test that adds a second one must not leave the
    // next test's screens landing on it.
    if (Array.isArray(project.canvases) && project.canvases.length) {
        project.canvases = project.canvases.slice(0, 1);
        project.active_canvas_id = project.canvases[0].id;
    }
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
    app.dedupeProjectLayers('lock_guard_test_reset');
    const screens = app.project.layers.filter(
        l => (l.type || 'screen') === 'screen').slice(0, specs.length);
    const ids = screens.map(l => l.id);
    if (opts.group) {
        const members = opts.group.map(i => screens[i]);
        app.project.groups = [{ id: 'g_lk', name: 'Lock Wall',
                                layer_ids: members.map(l => l.id) }];
        members.forEach(l => { l.group_id = 'g_lk'; });
        await fetch('/api/project', {
            method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(app.project),
        });
    }
    (opts.locked || []).forEach(i => { screens[i].locked = true; });
    (opts.hidden || []).forEach(i => { screens[i].visible = false; });
    // Each layer PUT is echoed back over the socket (layer_updated) and
    // merged into the page. Wait for every echo before the page state is
    // set up, so a late one cannot land on top of the test.
    const want = [...new Set([...(opts.locked || []), ...(opts.hidden || [])])]
        .map(i => screens[i].id);
    const echoed = new Set();
    const onEcho = (l) => { if (l) echoed.add(l.id); };
    if (app.socket && want.length) app.socket.on('layer_updated', onEcho);
    for (const id of want) {
        const l = screens.find(x => x.id === id);
        await fetch(`/api/layer/${id}`, {
            method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ locked: !!l.locked, visible: l.visible !== false }),
        });
    }
    if (app.socket && want.length) {
        const t0 = Date.now();
        while (!want.every(id => echoed.has(id)) && Date.now() - t0 < 5000) {
            await new Promise(r => setTimeout(r, 20));
        }
        app.socket.off('layer_updated', onEcho);
    }
    // The echo merges onto the project; re-read the screens it settled on.
    screens.forEach((l, i) => {
        screens[i] = app.project.layers.find(x => x.id === l.id) || l;
    });
    const cur = screens[opts.current || 0];
    app.currentLayer = cur;
    app.selectedLayerIds = new Set((opts.selected || [opts.current || 0]).map(i => ids[i]));
    app.lastSelectedLayerId = cur.id;
    app.selectionAnchorLayerId = cur.id;
    if (app.customSelection) app.customSelection.clear();
    if (app.powerCustomSelection) app.powerCustomSelection.clear();
    if (app.pixelMapSelection) app.pixelMapSelection.clear();
    app._overrideEditing = null;
    if (typeof app.setViewMode === 'function' && opts.view && opts.view !== r.viewMode) {
        app.setViewMode(opts.view);
    }
    r.viewMode = opts.view || 'pixel-map';
    r.zoom = opts.zoom || 0.5; r.panX = 60; r.panY = 60;
    if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
    app.renderLayers();
    app.loadLayerToInputs();
    app.updatePixelMapBulkActionUI();
    app.resetHistory('Lock guard test reset');
    app._lastLockedEditReport = null;   // a new test is a new attempt
    app._lockedRepaintPending = false;
    if (app._lockedRepaintTimer) { clearTimeout(app._lockedRepaintTimer); app._lockedRepaintTimer = null; }
    if (document.activeElement && document.activeElement !== document.body) document.activeElement.blur();
    window.__toasts = [];
    // The last test's toasts stack up the middle of the window for five
    // seconds; they must not sit over the canvas this test presses on.
    const host = document.getElementById('app-toast-host');
    if (host) host.innerHTML = '';
    r.render();
    return ids;
}"""


def reset(page, specs=TRIO, **opts):
    ids = page.evaluate(RESET_JS, [specs, opts])
    assert len(ids) == len(specs), ids
    return ids


def saves_settled(page):
    page.evaluate("async () => { await window.app._layerSavesSettled(); }")


def toasts(page):
    return page.evaluate("() => window.__toasts.slice()")


def layer(page, lid):
    """The layer as the page holds it, less the render caches."""
    return page.evaluate("""(id) => {
        const l = window.app.project.layers.find(x => x.id === id);
        if (!l) return null;
        return JSON.parse(JSON.stringify(l, (k, v) => k.charAt(0) === '_' ? undefined : v));
    }""", lid)


def server_layer(page, lid):
    return page.evaluate("""async (id) => {
        const p = await (await fetch('/api/project')).json();
        return p.layers.find(l => l.id === id) || null;
    }""", lid)


def history_len(page):
    return page.evaluate("() => window.app.history.length")


def to_client(page, wx, wy):
    pt = page.evaluate("""([wx, wy]) => {
        const r = window.canvasRenderer;
        const rect = r.canvas.getBoundingClientRect();
        return { x: rect.left + wx * r.zoom + r.panX,
                 y: rect.top + wy * r.zoom + r.panY };
    }""", [wx, wy])
    return pt['x'], pt['y']


def click(page, at, modifier=None, jitter=0):
    x, y = to_client(page, *at)
    if modifier:
        page.keyboard.down(modifier)
    try:
        page.mouse.move(x, y)
        page.mouse.down()
        if jitter:
            page.mouse.move(x + jitter, y + jitter)
        page.mouse.up()
    finally:
        if modifier:
            page.keyboard.up(modifier)


def drag(page, start, end, modifier=None, steps=8):
    sx, sy = to_client(page, *start)
    ex, ey = to_client(page, *end)
    if modifier:
        page.keyboard.down(modifier)
    try:
        page.mouse.move(sx, sy)
        page.mouse.down()
        page.mouse.move(ex, ey, steps=steps)
        page.mouse.up()
    finally:
        if modifier:
            page.keyboard.up(modifier)


def sel_state(page):
    return page.evaluate("""() => {
        const app = window.app;
        return {
            keys: [...app.pixelMapSelection].sort(),
            selected: [...app.selectedLayerIds].sort((a, b) => a - b),
            current: app.currentLayer ? app.currentLayer.id : null,
        };
    }""")


def keys(lid, cells):
    return sorted(f'{lid}:{r},{c}' for r, c in cells)


# ═════════════════════════════════════════════════════════════════════════
# Selection is not a change (C7, S1)
# ═════════════════════════════════════════════════════════════════════════

def test_plain_click_on_a_locked_screen_picks_it_and_its_cabinet_quietly(page):
    a, b, c = reset(page, locked=[1], selected=[0], current=0)
    # The lower row: the screen's name label sits over the middle and a
    # press on it is the label's own gesture.
    click(page, (664, 220))                   # B's R1C0, B unselected
    got = sel_state(page)
    assert got['current'] == b and got['selected'] == [b], got
    assert got['keys'] == keys(b, [(1, 0)]), got
    click(page, (664 + 128, 220))             # B is current now: R1C1
    got = sel_state(page)
    assert got['keys'] == keys(b, [(1, 1)]), got
    assert toasts(page) == [], 'picking a locked screen is not a change'


def test_marquee_cmd_click_and_select_all_pick_locked_cabinets_quietly(page):
    a, b, c = reset(page, locked=[1], selected=[0, 1], current=0)
    drag(page, (200, 60), (700, 200))
    assert sel_state(page)['keys'] == sorted(keys(a, [(0, 1), (1, 1)])
                                             + keys(b, [(0, 0), (1, 0)]))
    click(page, (664 + 128, 64), modifier=MODIFIER)
    assert keys(b, [(0, 1)])[0] in sel_state(page)['keys']
    page.keyboard.press(f'{MODIFIER}+a')
    got = sel_state(page)
    assert len(got['keys']) == 8, got
    assert toasts(page) == []


def test_set_blank_refuses_the_locked_cabinets_and_names_the_screen(page):
    a, b, c = reset(page, locked=[1], selected=[0, 1], current=0)
    drag(page, (200, 60), (700, 200))
    h0 = history_len(page)
    page.click('#bulk-set-blank')
    settled(page, lambda: history_len(page), lambda n: n > h0)
    saves_settled(page)
    assert [p['hidden'] for p in server_layer(page, b)['panels']] == [False] * 4
    hidden_a = sorted((p['row'], p['col']) for p in server_layer(page, a)['panels'] if p['hidden'])
    assert hidden_a == [(0, 1), (1, 1)]
    assert toasts(page) == [locked_msg('Lock B')]
    # Restore on cabinets that are not blank would change nothing on B:
    # it says nothing about B.
    page.evaluate("() => { window.__toasts = []; }")
    page.evaluate("""(b) => {
        const app = window.app;
        app.pixelMapSelection.clear();
        app.project.layers.find(l => l.id === b).panels
            .forEach(p => app.pixelMapSelection.add(app.getScopedPanelKey(b, p)));
        app.updatePixelMapBulkActionUI();
    }""", b)
    page.click('#bulk-unset-blank')
    saves_settled(page)
    assert toasts(page) == []


def test_custom_click_that_picks_a_locked_screen_adds_nothing_and_says_nothing(page):
    a, b, c = reset(page, locked=[1], selected=[0], current=0, view='data-flow')
    page.evaluate("""(ids) => {
        const app = window.app;
        ids.forEach(id => {
            const l = app.project.layers.find(x => x.id === id);
            l.flowPattern = 'custom';
        });
        window.canvasRenderer.render();
    }""", [a, b])
    before = layer(page, b)
    click(page, (664, 64))
    assert sel_state(page)['current'] == b
    # (selectLayer fills the absent defaults - `{}` reads as no paths)
    assert (layer(page, b).get('customPortPaths') or {}) == (before.get('customPortPaths') or {})
    assert toasts(page) == []
    # Already current: the click is the draw verb, and it names the lock.
    click(page, (664 + 128, 64))
    assert (layer(page, b).get('customPortPaths') or {}) == (before.get('customPortPaths') or {})
    assert toasts(page) == [locked_msg('Lock B')]


# ═════════════════════════════════════════════════════════════════════════
# Stepping the active port / circuit (C1, C7)
# ═════════════════════════════════════════════════════════════════════════

def _custom_paths(page, lid, kind='data'):
    page.evaluate("""([id, kind]) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === id);
        if (kind === 'power') {
            l.powerFlowPattern = 'custom';
            l.powerCustomPaths = { 1: [{ row: 0, col: 0 }], 2: [{ row: 0, col: 1 }] };
            l.powerCustomIndex = 1;
        } else {
            l.flowPattern = 'custom';
            l.customPortPaths = { 1: [{ row: 0, col: 0 }], 2: [{ row: 0, col: 1 }] };
            l.customPortIndex = 1;
        }
        app.loadLayerToInputs();
        window.canvasRenderer.render();
    }""", [lid, kind])


def test_alt_click_on_a_run_of_a_locked_screen_keeps_the_active_port(page):
    a, b, c = reset(page, locked=[0], selected=[0], current=0, view='data-flow')
    _custom_paths(page, a)
    h0 = history_len(page)
    click(page, (64 + 128, 64), modifier='Alt')     # run 2
    got = layer(page, a)
    assert got['customPortIndex'] == 1, got['customPortIndex']
    assert history_len(page) == h0
    assert toasts(page) == [locked_msg('Lock A')]
    # Alt+click on the run that is already active changes nothing.
    page.evaluate("() => { window.__toasts = []; }")
    click(page, (64, 64), modifier='Alt')
    assert toasts(page) == []


@pytest.mark.parametrize('kind', ['data', 'power'])
def test_prev_at_one_on_a_locked_screen_says_nothing_next_is_refused(page, kind):
    view = 'power' if kind == 'power' else 'data-flow'
    a, b, c = reset(page, locked=[0], selected=[0], current=0, view=view)
    page.evaluate("""([id, kind]) => {
        const l = window.app.project.layers.find(x => x.id === id);
        if (kind === 'power') { l.powerFlowPattern = 'custom'; delete l.powerCustomPaths; delete l.powerCustomIndex; }
        else { l.flowPattern = 'custom'; delete l.customPortPaths; delete l.customPortIndex; }
    }""", [a, kind])
    before = layer(page, a)
    prev_id = '#power-custom-prev' if kind == 'power' else '#custom-prev-port'
    page.evaluate("(sel) => document.querySelector(sel).click()", prev_id)
    assert layer(page, a) == before, 'Prev at 1 wrote the locked screen'
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    page.keyboard.press('Shift+Tab')
    assert layer(page, a) == before
    assert toasts(page) == []
    page.keyboard.press('Tab')
    assert layer(page, a) == before
    assert toasts(page) == [locked_msg('Lock A')]


# ═════════════════════════════════════════════════════════════════════════
# Sidebar and Screen Info edits (C2)
# ═════════════════════════════════════════════════════════════════════════

def test_screen_info_edit_skips_the_locked_screen_and_snaps_back(page):
    a, b, c = reset(page, locked=[0], selected=[0, 1], current=0)
    before_a = layer(page, a)
    page.evaluate("""() => {
        const el = document.getElementById('number-size');
        el.value = '33';
        el.dispatchEvent(new Event('change', { bubbles: true }));
    }""")
    saves_settled(page)
    repaint_settled(page)
    assert layer(page, b)['number_size'] == 33
    assert server_layer(page, b)['number_size'] == 33
    assert layer(page, a) == before_a, 'the locked screen changed'
    assert server_layer(page, a)['number_size'] == before_a['number_size']
    assert toasts(page) == [locked_msg('Lock A')]
    # The field shows the selection as it really is: mixed.
    assert page.evaluate("() => document.getElementById('number-size').value") == ''


def test_a_sidebar_funnel_edit_on_only_locked_screens_changes_nothing(page):
    a, b, c = reset(page, locked=[0], selected=[0], current=0)
    before = layer(page, a)
    # Settle the history on the state as it stands (the reset's own
    # normalizing writes), so the step count below is the edit's alone.
    page.evaluate("() => window.app.saveState('Baseline')")
    h0 = history_len(page)
    page.evaluate("""() => {
        const el = document.getElementById('screen-rotation');
        el.value = '90';
        el.dispatchEvent(new Event('change', { bubbles: true }));
    }""")
    saves_settled(page)
    repaint_settled(page)
    assert layer(page, a) == before
    assert history_len(page) == h0
    assert toasts(page) == [locked_msg('Lock A')]
    assert page.evaluate("() => document.getElementById('screen-rotation').value") == \
        str(before.get('rotation') or 0)
    # Setting the value it already holds is no change and says nothing.
    page.evaluate("() => { window.__toasts = []; }")
    page.evaluate("""() => {
        const el = document.getElementById('screen-rotation');
        el.dispatchEvent(new Event('change', { bubbles: true }));
    }""")
    assert toasts(page) == []


def test_a_group_edit_leaves_a_locked_peer_alone_and_names_it(page):
    a, b, c = reset(page, locked=[1], group=[0, 1], selected=[0], current=0)
    before_b = layer(page, b)
    page.evaluate("""() => {
        const el = document.getElementById('number-size');
        el.value = '41';
        el.dispatchEvent(new Event('change', { bubbles: true }));
    }""")
    saves_settled(page)
    assert layer(page, a)['number_size'] == 41
    assert layer(page, b) == before_b
    assert server_layer(page, b)['number_size'] == before_b['number_size']
    assert toasts(page) == [locked_msg('Lock B')]


def test_the_lock_toggle_still_unlocks(page):
    a, b, c = reset(page, locked=[0], selected=[0], current=0)
    page.evaluate("() => document.getElementById('toggle-lock-selected').click()")
    saves_settled(page)
    assert layer(page, a)['locked'] is False
    assert server_layer(page, a)['locked'] is False
    assert toasts(page) == []


def test_rename_in_the_screens_list_is_refused_on_a_locked_screen(page):
    a, b, c = reset(page, locked=[0], selected=[0], current=0)
    page.locator(f'input.layer-name-input[data-layer-id="{a}"]').first.dblclick()
    page.keyboard.press(f'{MODIFIER}+a')
    page.keyboard.type('Renamed')
    page.keyboard.press('Enter')
    saves_settled(page)
    assert layer(page, a)['name'] == 'Lock A'
    assert server_layer(page, a)['name'] == 'Lock A'
    assert toasts(page) == [locked_msg('Lock A')]


def test_jumper_field_writes_the_unlocked_screen_only(page):
    a, b, c = reset(page, locked=[0], selected=[0, 1], current=0, view='power')
    before_a = layer(page, a).get('powerJumpV')
    page.evaluate("""() => {
        const el = document.getElementById('power-jump-v');
        el.value = '12';
        el.dispatchEvent(new Event('change', { bubbles: true }));
    }""")
    saves_settled(page)
    assert layer(page, a).get('powerJumpV') == before_a
    assert layer(page, b)['powerJumpV'] == 12
    assert toasts(page) == [locked_msg('Lock A')]


def test_change_cabinet_and_route_as_one_refuse_locked_screens(page):
    a, b, c = reset(page, locked=[0], group=[0, 1], selected=[0, 1], current=1)
    before = layer(page, a)
    page.evaluate("""(ids) => window.app.changeCabinetForLayers(ids,
        { cabinet_width: 64, cabinet_height: 64 })""", [a, b])
    saves_settled(page)
    assert layer(page, b)['cabinet_width'] == 64
    assert layer(page, a)['cabinet_width'] == before['cabinet_width']
    assert toasts(page) == [locked_msg('Lock A')]
    page.evaluate("() => { window.__toasts = []; }")
    route = page.evaluate("""() => {
        const box = document.getElementById('route-group-as-one');
        const g = window.app.project.groups[0];
        const was = g.routeDataAsOne;
        box.checked = !box.checked;
        box.dispatchEvent(new Event('change', { bubbles: true }));
        return { was, now: g.routeDataAsOne };
    }""")
    assert route['was'] == route['now'], route
    assert toasts(page) == [locked_msg('Lock A')]


def test_power_setters_refuse_a_locked_screen(page):
    a, b, c = reset(page, locked=[0], selected=[0], current=0, view='power')
    before = layer(page, a)
    page.evaluate("""(id) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === id);
        app.setCircuitCable(l, 1, { ft: 50, connector: null });
        app.setSocaLength(l, 0, '100ft');
    }""", a)
    assert layer(page, a) == before
    assert toasts(page) == [locked_msg('Lock A')]


def test_dock_drops_refuse_a_locked_screen(page):
    a, b, c = reset(page, locked=[0], selected=[0], current=0, view='power')
    page.evaluate("() => window.app.addDistro({ name: 'LK' })")
    before = layer(page, a)
    page.evaluate("""(id) => {
        const app = window.app;
        const d = app.getDistros()[0];
        app._dockDropDistro({ type: 'distro', distroId: d.id }, { kind: 'screen', layerId: id });
    }""", a)
    assert layer(page, a) == before
    assert toasts(page) == [locked_msg('Lock A')]
    # A second drop is its own attempt: counted, so a duplicate inside one
    # drop cannot hide behind a set.
    page.evaluate("() => { window.__toasts = []; }")
    page.evaluate("""(id) => {
        const app = window.app;
        const d = app.getDistros()[0];
        app._dockDropPlug({ type: 'plug', distroId: d.id, output: 'soca208', title: 'LK' },
                          { kind: 'screen', layerId: id });
    }""", a)
    assert layer(page, a) == before
    assert toasts(page) == [locked_msg('Lock A')]


# ═════════════════════════════════════════════════════════════════════════
# Delete and move (C3, C4)
# ═════════════════════════════════════════════════════════════════════════

def test_delete_key_on_a_locked_screen_is_refused(page):
    a, b, c = reset(page, locked=[0], selected=[0], current=0)
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    page.keyboard.press('Delete')
    saves_settled(page)
    assert layer(page, a) is not None
    assert server_layer(page, a) is not None
    assert toasts(page) == [locked_msg('Lock A')]


def test_multi_delete_removes_the_unlocked_and_names_the_locked(page):
    a, b, c = reset(page, locked=[0], selected=[0, 1], current=0)
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    page.keyboard.press('Backspace')
    settled(page, lambda: page.evaluate("() => window.app.deletionInProgress"),
            lambda v: not v)
    ids = page.evaluate("() => window.app.project.layers.map(l => l.id)")
    assert a in ids and b not in ids and c in ids, ids
    assert toasts(page) == [locked_msg('Lock A')]


def test_dragging_a_locked_screen_says_so_once_per_gesture(page):
    a, b, c = reset(page, locked=[0], selected=[0], current=0)
    before = layer(page, a)
    drag(page, (100, 100), (400, 300), modifier='Shift', steps=20)
    assert layer(page, a)['offset_x'] == before['offset_x']
    assert toasts(page) == [locked_msg('Lock A')]
    # A shift-click that never moves says nothing.
    page.evaluate("() => { window.__toasts = []; }")
    click(page, (100, 100), modifier='Shift')
    assert toasts(page) == []


def test_a_mixed_drag_moves_the_unlocked_and_names_the_locked(page):
    a, b, c = reset(page, locked=[0], selected=[0, 1], current=1)
    ax = layer(page, a)['offset_x']
    bx = layer(page, b)['offset_x']
    drag(page, (700, 100), (900, 100), modifier='Shift', steps=12)
    saves_settled(page)
    assert layer(page, a)['offset_x'] == ax
    assert layer(page, b)['offset_x'] != bx
    assert toasts(page) == [locked_msg('Lock A')]


def test_center_on_canvas_names_a_locked_screen(page):
    a, b, c = reset(page, locked=[0], selected=[0], current=0)
    before = layer(page, a)
    x, y = to_client(page, 100, 100)
    page.mouse.click(x, y, button='right')
    page.locator('#context-menu [data-action="center-both"]').click()
    assert layer(page, a)['offset_x'] == before['offset_x']
    assert layer(page, a)['offset_y'] == before['offset_y']
    assert toasts(page) == [locked_msg('Lock A')]


# ═════════════════════════════════════════════════════════════════════════
# Pixel Map selection mechanics (S2, S3, S4, S5)
# ═════════════════════════════════════════════════════════════════════════

def test_a_one_pixel_jitter_at_low_zoom_is_still_a_click(page):
    a, b, c = reset(page, selected=[0, 1], current=0, zoom=1)
    click(page, (664, 64), jitter=1)
    got = sel_state(page)
    assert got['current'] == b and got['selected'] == [b], got
    assert got['keys'] == keys(b, [(0, 0)]), got


def test_a_jittered_cmd_click_toggles_the_screen_out(page):
    a, b, c = reset(page, selected=[0, 1], current=0, zoom=1)
    click(page, (664, 64), modifier=MODIFIER, jitter=1)
    assert sel_state(page)['selected'] == [a]


def test_a_hidden_current_screen_is_out_of_the_marquee(page):
    a, b, c = reset(page, hidden=[0], selected=[0, 1], current=0)
    scope = page.evaluate("() => window.app.getPixelMapScopeLayers().map(l => l.id)")
    assert scope == [b], scope
    page.evaluate("(sel) => window.app.selectPixelMapPanelsInRect(null, sel)",
                  {'x1': -10, 'y1': -10, 'x2': 900, 'y2': 300})
    got = sel_state(page)
    assert all(k.startswith(f'{b}:') for k in got['keys']), got
    assert len(got['keys']) == 4
    # The only screen in play keeps its hidden cabinets reachable.
    page.evaluate("(a) => { window.app.selectedLayerIds = new Set([a]); }", a)
    assert page.evaluate("() => window.app.getPixelMapScopeLayers().map(l => l.id)") == [a]


def test_the_render_path_reads_the_selection_without_pruning(page):
    a, b, c = reset(page, selected=[0, 1], current=0)
    page.evaluate("""([a, b]) => {
        const app = window.app;
        app.pixelMapSelection.add(`${a}:0,0`);
        app.pixelMapSelection.add(`${b}:0,0`);
        // Mid-update: the selection names one screen for a moment.
        app.selectedLayerIds = new Set([a]);
        window.canvasRenderer.render();
        app.renderLayers();
        app.updatePixelMapBulkActionUI();
        app.selectedLayerIds = new Set([a, b]);
    }""", [a, b])
    assert sel_state(page)['keys'] == sorted([f'{a}:0,0', f'{b}:0,0'])
    # A real selection change prunes what left the scope.
    page.evaluate("(b) => window.app.toggleLayerSelection("
                  "window.app.project.layers.find(l => l.id === b))", b)
    assert sel_state(page)['keys'] == [f'{a}:0,0']


def test_row_col_lookup_is_indexed_and_follows_a_rebuild(page):
    a, b, c = reset(page, selected=[0], current=0)
    out = page.evaluate("""(id) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === id);
        const first = app.getPanelByRowCol(l, 1, 1);
        const old = l.panels;
        l.panels = old.map(p => Object.assign({}, p));   // a rebuild: new array
        const second = app.getPanelByRowCol(l, 1, 1);
        const res = { same: first === old.find(p => p.row === 1 && p.col === 1),
                      rebuilt: second === l.panels.find(p => p.row === 1 && p.col === 1),
                      miss: app.getPanelByRowCol(l, 9, 9) };
        l.panels = old;
        return res;
    }""", a)
    assert out == {'same': True, 'rebuilt': True, 'miss': None}, out


def test_cross_screen_marquee_is_fast_on_six_large_screens(page):
    big = [dict(name=f'Big {i}', columns=80, rows=40, cabinet_width=16,
                cabinet_height=16, offset_x=(i % 3) * 1400, offset_y=(i // 3) * 700)
           for i in range(6)]
    reset(page, big, selected=list(range(6)), current=0, zoom=0.25)
    timing = page.evaluate("""() => {
        const app = window.app, r = window.canvasRenderer;
        const rect = { x1: -10, y1: -10, x2: 4300, y2: 1400 };
        const move = () => {
            const t0 = performance.now();
            app.selectPixelMapPanelsInRect(app.currentLayer, rect);
            r.render();
            return performance.now() - t0;
        };
        move();
        const after = Math.min(move(), move(), move());
        const count = app.pixelMapSelection.size;
        // The same move with the linear lookup this replaced.
        const proto = Object.getPrototypeOf(app);
        const indexed = proto.getPanelByRowCol;
        proto.getPanelByRowCol = function (layer, row, col) {
            if (!layer || !layer.panels) return null;
            return layer.panels.find(p => p.row === row && p.col === col) || null;
        };
        let before;
        try { before = Math.min(move(), move()); }
        finally { proto.getPanelByRowCol = indexed; }
        app.pixelMapSelection.clear();
        return { before, after, count };
    }""")
    print(f"\n6 x 80x40 cross-screen marquee move: linear {timing['before']:.1f} ms, "
          f"indexed {timing['after']:.1f} ms ({timing['count']} cabinets)")
    assert timing['count'] == 6 * 80 * 40
    assert timing['after'] < timing['before'], timing


# ═════════════════════════════════════════════════════════════════════════
# Live controls with a locked screen in the selection (re-audit item 1)
#
# A keystroke or a slider move is LIVE: the unlocked screens take it, the
# locked one is held, the error is said once - and the fields are NOT
# repainted mid-edit (the repaint rewrote the very field being typed in).
# The snap-back waits for the commit and never lands in the focused field.
# ═════════════════════════════════════════════════════════════════════════

def repaint_settled(page):
    """The held-back edit's snap-back repaint has run (it waits for the
    commit's own event sequence - a Tab's change, blur and focus)."""
    page.wait_for_function(
        "() => !(window.app._lockedRepaintBusy && window.app._lockedRepaintBusy())")


def lock(page, lock_ids, selected, current):
    """Lock screens through the app's own lock verb (so a test can dress a
    screen first and lock it after), then set the selection under test."""
    page.evaluate("""async ([lockIds, sel, cur]) => {
        const app = window.app;
        const find = (id) => app.project.layers.find(l => l.id === id);
        await app._layerSavesSettled();
        app.selectedLayerIds = new Set(lockIds);
        app.currentLayer = find(lockIds[0]);
        app.setLockOnSelected(true);
        await app._layerSavesSettled();
        app.selectedLayerIds = new Set(sel);
        app.currentLayer = find(cur);
        app.lastSelectedLayerId = cur;
        app.loadLayerToInputs();
        app.resetHistory('Lock guard test lock');
        app._lastLockedEditReport = null;
        window.__toasts = [];
    }""", [lock_ids, selected, current])


def type_into(page, field_id, text, commit='Tab'):
    page.evaluate("""(id) => {
        const el = document.getElementById(id);
        el.scrollIntoView({ block: 'center' });
    }""", field_id)
    page.locator(f'#{field_id}').click()
    page.keyboard.press(f'{MODIFIER}+a')
    page.keyboard.type(text, delay=40)
    typed = page.evaluate("(id) => document.getElementById(id).value", field_id)
    page.keyboard.press(commit)
    saves_settled(page)
    repaint_settled(page)
    saves_settled(page)
    return typed


def test_typing_a_label_size_over_a_locked_screen_writes_the_unlocked_one(page):
    a, b, c = reset(page, locked=[0], selected=[0, 1], current=0)
    before_a = server_layer(page, a)
    typed = type_into(page, 'info-label-size', '22')
    assert typed == '22', f'the field was rewritten mid-typing: {typed!r}'
    assert layer(page, b)['infoLabelSize'] == 22
    assert server_layer(page, b)['infoLabelSize'] == 22
    assert server_layer(page, a).get('infoLabelSize') == before_a.get('infoLabelSize')
    assert layer(page, a).get('infoLabelSize') == before_a.get('infoLabelSize')
    assert toasts(page) == [locked_msg('Lock A')], 'one attempt, one error (Tab too)'
    # A second attempt over the first, committed with Enter: its own error,
    # once, and B takes the new value.
    page.evaluate("() => { window.__toasts = []; }")
    typed = type_into(page, 'info-label-size', '30', commit='Enter')
    assert typed == '30', typed
    assert server_layer(page, b)['infoLabelSize'] == 30
    assert server_layer(page, a).get('infoLabelSize') == before_a.get('infoLabelSize')
    assert toasts(page) == [locked_msg('Lock A')]


def _drag_range(page, sel, frac_from, frac_to, steps=10):
    """A real mouse drag on a range input, from one fraction of its track to
    another. Returns the slider's value read mid-drag (just before the
    release) - a snap-back during the drag shows up there."""
    page.evaluate("(sel) => document.querySelector(sel).scrollIntoView({ block: 'center' })", sel)
    box = page.locator(sel).bounding_box()
    y = box['y'] + box['height'] / 2
    x0 = box['x'] + 6 + (box['width'] - 12) * frac_from
    x1 = box['x'] + 6 + (box['width'] - 12) * frac_to
    page.mouse.move(x0, y)
    page.mouse.down()
    page.mouse.move(x1, y, steps=steps)
    mid = page.evaluate("(sel) => document.querySelector(sel).value", sel)
    page.mouse.up()
    return mid


def test_dragging_the_gradient_opacity_over_a_locked_screen_saves_the_unlocked_one(page):
    a, b, c = reset(page, selected=[0, 1], current=0)
    page.evaluate("""() => {
        const app = window.app;
        app.applyToSelectedLayers(l => {
            app._ensureGradientDefaults(l);
            l.gradientEnabled = true;
            l.gradientOpacity = 0.2;
        });
        app.updateLayers(app.getSelectedLayers());
    }""")
    lock(page, [a], [a, b], a)
    page.evaluate("""() => {
        const sec = document.getElementById('gradient-controls');
        if (sec) sec.style.display = 'block';
        window.app.loadGradientEditor();
    }""")
    before_a = server_layer(page, a)['gradientOpacity']
    mid = _drag_range(page, '#gradient-opacity', 0.2, 0.9)
    saves_settled(page)
    repaint_settled(page)
    saves_settled(page)
    assert int(mid) > 60, f'the slider snapped back under the pointer: {mid}'
    final = int(page.evaluate("() => document.getElementById('gradient-opacity').value"))
    assert final > 60, final
    got_b = server_layer(page, b)['gradientOpacity']
    assert got_b == pytest.approx(final / 100), (got_b, final)
    assert layer(page, b)['gradientOpacity'] == pytest.approx(final / 100)
    assert server_layer(page, a)['gradientOpacity'] == before_a
    assert layer(page, a)['gradientOpacity'] == before_a
    assert toasts(page) == [locked_msg('Lock A')]


IMAGES_JS = """async () => {
    const app = window.app, r = window.canvasRenderer;
    await app._layerSavesSettled();
    let project = await (await fetch('/api/project')).json();
    project.layers = []; project.groups = []; project.distros = [];
    if (Array.isArray(project.canvases) && project.canvases.length) {
        project.canvases = project.canvases.slice(0, 1);
        project.active_canvas_id = project.canvases[0].id;
    }
    await fetch('/api/project', { method: 'PUT',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify(project) });
    const src = document.createElement('canvas');
    src.width = 40; src.height = 40;
    const ctx = src.getContext('2d');
    ctx.fillStyle = '#ff0000'; ctx.fillRect(0, 0, 40, 40);
    const ids = [];
    for (const [name, x] of [['Lock Img A', 0], ['Lock Img B', 300]]) {
        const res = await fetch('/api/layer/add-image', { method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ name, imageData: src.toDataURL('image/png'),
                imageWidth: 40, imageHeight: 40, offset_x: x, offset_y: 0,
                imageShadowEnabled: true, imageShadowDistance: 10 }) });
        ids.push((await res.json()).id);
    }
    app.project = await (await fetch('/api/project')).json();
    app.dedupeProjectLayers('lock_guard_images');
    app.currentLayer = app.project.layers.find(l => l.id === ids[1]);
    app.selectedLayerIds = new Set([ids[1]]);
    r.viewMode = 'pixel-map';
    r.zoom = 0.5; r.panX = 60; r.panY = 60;
    app.renderLayers();
    app.loadLayerToInputs();
    app.resetHistory('Lock guard images');
    window.__toasts = [];
    r.render();
    return ids;
}"""


def test_dragging_image_opacity_and_typing_a_shadow_over_a_locked_image(page):
    a, b = page.evaluate(IMAGES_JS)
    lock(page, [a], [a, b], a)
    before_a = server_layer(page, a)
    mid = _drag_range(page, '#image-opacity-range', 0.95, 0.3)
    saves_settled(page)
    repaint_settled(page)
    saves_settled(page)
    assert int(mid) < 50, f'the slider snapped back under the pointer: {mid}'
    final = int(page.evaluate("() => document.getElementById('image-opacity-range').value"))
    assert server_layer(page, b)['imageOpacity'] == final
    assert server_layer(page, a).get('imageOpacity') == before_a.get('imageOpacity')
    assert toasts(page) == [locked_msg('Lock Img A')]
    page.evaluate("() => { window.__toasts = []; }")
    typed = type_into(page, 'image-shadow-distance', '40')
    assert typed == '40', f'the shadow field was blanked mid-typing: {typed!r}'
    assert server_layer(page, b)['imageShadowDistance'] == 40
    assert server_layer(page, a)['imageShadowDistance'] == before_a['imageShadowDistance']
    assert toasts(page) == [locked_msg('Lock Img A')]


def test_image_scale_on_a_locked_image_errors_only_on_a_change(page):
    a, b = page.evaluate(IMAGES_JS)
    lock(page, [a], [a], a)
    type_into(page, 'image-scale', '100')
    assert toasts(page) == [], 'the value it already has is no change'
    typed = type_into(page, 'image-scale', '150')
    assert typed == '150'
    assert toasts(page) == [locked_msg('Lock Img A')]
    assert layer(page, a)['imageScale'] == 1
    assert server_layer(page, a)['imageScale'] == 1
    # The commit snapped the field back to what the locked image holds.
    assert page.evaluate("() => document.getElementById('image-scale').value") == '100'


# ═════════════════════════════════════════════════════════════════════════
# Errors only when something would change (re-audit item 5)
# ═════════════════════════════════════════════════════════════════════════

def test_change_cabinet_to_the_cabinet_a_locked_screen_has_says_nothing(page):
    a, b, c = reset(page, locked=[0], selected=[0, 1], current=1)
    page.evaluate("""(ids) => window.app.changeCabinetForLayers(ids,
        { cabinet_width: 128, cabinet_height: 128 })""", [a, b])
    saves_settled(page)
    assert toasts(page) == []


def test_power_setters_on_a_locked_screen_say_nothing_for_the_same_value(page):
    a, b, c = reset(page, selected=[0], current=0, view='power')
    page.evaluate("""async (id) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === id);
        app.setCircuitCable(l, 1, { ft: 50, connector: null });
        app.setSocaLength(l, 0, '100ft');
        await app._layerSavesSettled();
    }""", a)
    lock(page, [a], [a], a)
    before = layer(page, a)
    page.evaluate("""(id) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === id);
        app.setCircuitCable(l, 1, { ft: 50, connector: null });
        app.setSocaLength(l, 0, '100ft');
    }""", a)
    assert layer(page, a) == before
    assert toasts(page) == []


# ═════════════════════════════════════════════════════════════════════════
# Clear card over mixed locked and unlocked screens (re-audit item 2)
# ═════════════════════════════════════════════════════════════════════════

CARD_SPECS = [
    dict(name='Lock A', columns=4, rows=4, cabinet_width=200, cabinet_height=200),
    dict(name='Lock B', columns=10, rows=5, cabinet_width=200, cabinet_height=200,
         offset_x=2400),
    dict(name='Lock C', columns=2, rows=2, cabinet_width=200, cabinet_height=200,
         offset_x=5000),
]

CARD_SEED_JS = """async (ids) => {
    const app = window.app;
    for (const id of ids) {
        await fetch(`/api/layer/${id}`, { method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ processorType: 'novastar-coex-1g' }) });
    }
    const p0 = await (await fetch('/api/project')).json();
    p0.processors = [];
    delete p0.port_assignments;
    await fetch('/api/project', { method: 'PUT',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify(p0) });
    await fetch('/api/processors', { method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ deviceId: 'novastar-mx40-pro' }) });
    app.project = await (await fetch('/api/project')).json();
    app.dedupeProjectLayers('lock_guard_card_seed');
    await app.refreshProcessors();
    const proc = app._processorsResolved[0];
    const cardId = proc.slots.map(s => s.card).find(Boolean).id;
    for (const id of ids.slice(0, 2)) {
        await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
                                     { layerId: String(id), cardId });
    }
    return cardId;
}"""


def pins(page):
    return page.evaluate("""async () => {
        const p = await (await fetch('/api/project')).json();
        return ((p.port_assignments || {}).pins || []).map(x => String(x.layerId));
    }""")


def test_clear_card_keeps_a_locked_screens_ports_and_records_one_step(page):
    a, b, c = reset(page, CARD_SPECS, selected=[0], current=0, view='data-flow')
    card_id = page.evaluate(CARD_SEED_JS, [a, b, c])
    seeded = pins(page)
    assert seeded.count(str(a)) == 1 and seeded.count(str(b)) >= 2, seeded
    # B - the screen whose pins come LAST, several of them - is locked.
    lock(page, [b], [a], a)
    page.evaluate("() => window.app.saveState('Baseline')")
    h0 = history_len(page)
    page.evaluate("""async (cardId) => {
        const item = window.app._clearMenuForDock(
            { type: 'card', cardId, title: 'the card' });
        await item.run();
    }""", card_id)
    saves_settled(page)
    after = pins(page)
    assert str(a) not in after, after
    assert after.count(str(b)) == seeded.count(str(b)), after
    assert history_len(page) == h0 + 1, 'the release lost its undo step'
    assert page.evaluate("() => window.app.history.map(h => h.action).slice(-1)") == ['Release Ports']
    assert toasts(page) == [locked_msg('Lock B')]
    # One Undo puts A's port back.
    page.evaluate("() => window.app.undo()")
    restored = settled(page, lambda: pins(page), lambda v: str(a) in v)
    assert str(a) in restored, restored


def test_the_locked_error_is_said_once_across_a_chained_action(page):
    a, b, c = reset(page, locked=[0], selected=[0], current=0)
    page.evaluate("""async () => {
        const app = window.app;
        const A = app.project.layers.find(l => l.name === 'Lock A');
        const end = app._beginLockedAction();
        try {
            app._showLockedError([A]);
            await new Promise(r => setTimeout(r, 0));
            await fetch('/api/project');
            app._showLockedError([A]);
        } finally { end(); }
        // A later action says it again.
        await new Promise(r => setTimeout(r, 0));
        app._showLockedError([A]);
    }""")
    assert toasts(page) == [locked_msg('Lock A')] * 2


# ═════════════════════════════════════════════════════════════════════════
# Canvas moves (re-audit items 3 and 4)
# ═════════════════════════════════════════════════════════════════════════

SECOND_CANVAS_JS = """async () => {
    const app = window.app;
    const r = await (await fetch('/api/canvas', { method: 'POST',
        headers: {'Content-Type': 'application/json'}, body: '{}' })).json();
    const id = r.active_canvas_id;
    await fetch(`/api/canvas/${id}`, { method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ workspace_x: 3000, workspace_y: 0 }) });
    const p = await (await fetch('/api/project')).json();
    app.project.canvases = p.canvases;
    app.project.active_canvas_id = p.canvases[0].id;
    window.canvasRenderer.render();
    return id;
}"""


def test_a_cross_canvas_drag_with_a_locked_current_screen_moves_the_unlocked(page):
    a, b, c = reset(page, locked=[0], selected=[0, 1], current=0, zoom=0.25)
    cid = page.evaluate(SECOND_CANVAS_JS)
    home = server_layer(page, a)['canvas_id']
    drag(page, (700, 100), (3200, 100), modifier='Shift', steps=15)
    got = settled(page, lambda: server_layer(page, b)['canvas_id'], lambda v: v == cid)
    saves_settled(page)
    assert got == cid, 'the unlocked screen did not cross'
    assert server_layer(page, a)['canvas_id'] == home
    assert layer(page, a)['canvas_id'] == home
    assert toasts(page) == [locked_msg('Lock A')]


def _dress_locked_group(page):
    """A wall of Lock A (locked) and Lock B, with a hand-drawn data path on A
    that steps onto B - the step a move of B out of the wall would cut."""
    a, b, c = reset(page, group=[0, 1], selected=[1], current=1)
    page.evaluate("""async ([a, b]) => {
        const app = window.app;
        const A = app.project.layers.find(l => l.id === a);
        A.flowPattern = 'custom';
        A.customPortPaths = { 1: [{ row: 0, col: 0 }, { row: 0, col: 0, layerId: b }] };
        app.updateLayers([A]);
        await app._layerSavesSettled();
    }""", [a, b])
    lock(page, [a], [b], b)
    cid = page.evaluate(SECOND_CANVAS_JS)
    return a, b, c, cid, server_layer(page, a), server_layer(page, b)


def _assert_wall_untouched(page, a, b, before_a, before_b):
    after_a = server_layer(page, a)
    assert after_a['group_id'] == before_a['group_id'] == 'g_lk'
    assert after_a.get('customPortPaths') == before_a.get('customPortPaths')
    after_b = server_layer(page, b)
    assert after_b['canvas_id'] == before_b['canvas_id']
    assert after_b['group_id'] == 'g_lk'
    assert after_b['offset_x'] == before_b['offset_x']
    assert toasts(page) == [locked_msg('Lock A')]


def test_moving_a_member_of_a_wall_with_a_locked_member_is_refused(page):
    a, b, c, cid, before_a, before_b = _dress_locked_group(page)
    page.evaluate("async ([b, cid]) => { await window.app.moveLayersCrossCanvas([b], cid, 'move'); }",
                  [b, cid])
    saves_settled(page)
    _assert_wall_untouched(page, a, b, before_a, before_b)


def test_move_to_canvas_menu_refuses_a_member_of_a_locked_wall(page):
    a, b, c, cid, before_a, before_b = _dress_locked_group(page)
    page.evaluate("() => window.app.openMoveToCanvasMenu()")
    page.locator(f'[data-canvas-id="{cid}"]').first.click()
    saves_settled(page)
    _assert_wall_untouched(page, a, b, before_a, before_b)


def test_dragging_a_member_of_a_locked_wall_to_another_canvas_is_refused(page):
    a, b, c, cid, before_a, before_b = _dress_locked_group(page)
    page.evaluate("() => { window.canvasRenderer.zoom = 0.25; window.canvasRenderer.render(); }")
    drag(page, (700, 100), (3200, 100), modifier='Shift', steps=15)
    saves_settled(page)
    _assert_wall_untouched(page, a, b, before_a, before_b)
    assert layer(page, b)['offset_x'] == before_b['offset_x'], 'B was left where it was dropped'


# ═════════════════════════════════════════════════════════════════════════
# The group headline, Alt-click and selection mechanics (items 6-10)
# ═════════════════════════════════════════════════════════════════════════

def test_the_group_headline_drags_with_a_locked_member(page):
    a, b, c = reset(page, group=[0, 1], locked=[1], selected=[0, 1], current=0, zoom=1)
    rect = page.evaluate("""() => {
        const app = window.app, r = window.canvasRenderer;
        delete app.project.groupNameDisplayByView;
        app.project.groupNameDisplay = 'both';
        r.render();
        const plan = r._groupLabelPlan(app.currentLayer);
        return plan && plan.cfg._groupNameHitRect;
    }""")
    assert rect, 'the headline drew no hit rect'
    before_b = layer(page, b)
    cx, cy = (rect['x1'] + rect['x2']) / 2, (rect['y1'] + rect['y2']) / 2
    drag(page, (cx, cy), (cx + 100, cy + 50), steps=10)
    group = page.evaluate("() => window.app.project.groups[0]")
    assert group.get('screenNameOffsetXPixelMap', 0) == pytest.approx(100, abs=2), group
    assert layer(page, b) == before_b
    assert toasts(page) == []


def test_alt_click_reads_the_toggle_direction_off_the_unlocked_cabinets(page):
    a, b, c = reset(page, selected=[0, 1], current=0)
    page.evaluate("""async (b) => {
        const app = window.app;
        const B = app.project.layers.find(l => l.id === b);
        await app.setPanelsBlankBulk(B.panels.slice(), true);
        await app._layerSavesSettled();
    }""", b)
    settled(page, lambda: [p['hidden'] for p in server_layer(page, b)['panels']],
            lambda v: all(v))
    lock(page, [a], [a, b], a)
    page.evaluate("""() => {
        const app = window.app;
        app.pixelMapSelection.clear();
        app.getPixelMapScopeLayers().forEach(l => l.panels.forEach(p =>
            app.pixelMapSelection.add(app.getScopedPanelKey(l.id, p))));
        app.updatePixelMapBulkActionUI();
    }""")
    click(page, (664, 64), modifier='Alt')
    got = settled(page, lambda: [p['hidden'] for p in server_layer(page, b)['panels']],
                  lambda v: not any(v))
    assert not any(got), 'the unlocked blanks were not shown'
    assert not any(p['hidden'] for p in server_layer(page, a)['panels'])
    assert toasts(page) == [], 'showing visible cabinets changes nothing on the locked screen'


def test_row_col_lookup_follows_a_panel_replaced_in_place(page):
    a, b, c = reset(page, selected=[0], current=0)
    out = page.evaluate("""(id) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === id);
        app.getPanelByRowCol(l, 1, 1);                    // build the index
        const i = l.panels.findIndex(p => p.row === 1 && p.col === 1);
        const old = l.panels[i];
        const fresh = Object.assign({}, old);
        l.panels[i] = fresh;                              // same array, new object
        const same = app.getPanelByRowCol(l, 1, 1) === fresh;
        // A swap of two slots in place: each address still finds its panel.
        const j = l.panels.findIndex(p => p.row === 0 && p.col === 0);
        const pj = l.panels[j];
        l.panels[j] = fresh; l.panels[i] = pj;
        const swapped = app.getPanelByRowCol(l, 1, 1) === fresh
            && app.getPanelByRowCol(l, 0, 0) === pj;
        l.panels[i] = old; l.panels[j] = pj;
        return { same, swapped };
    }""", a)
    assert out == {'same': True, 'swapped': True}, out


def test_a_group_verb_prunes_the_cabinets_of_screens_it_drops(page):
    a, b, c = reset(page, group=[1, 2], selected=[0, 1, 2], current=0)
    page.evaluate("""([a, b]) => {
        const app = window.app;
        app.pixelMapSelection.add(`${a}:0,0`);
        app.pixelMapSelection.add(`${b}:0,0`);
    }""", [a, b])
    page.evaluate("async () => { await window.app.toggleGroupVisibility('g_lk'); }")
    assert sel_state(page)['keys'] == [f'{a}:0,0']
    # Shown again and picked again: its old cabinets do not come back.
    page.evaluate("async () => { await window.app.toggleGroupVisibility('g_lk'); }")
    page.evaluate("(b) => window.app.toggleLayerSelection("
                  "window.app.project.layers.find(l => l.id === b))", b)
    assert sel_state(page)['keys'] == [f'{a}:0,0']


def test_a_release_past_the_threshold_applies_the_marquee(page):
    a, b, c = reset(page, selected=[0, 1], current=0, zoom=1)
    sx, sy = to_client(page, 20, 20)
    ex, ey = to_client(page, 230, 230)
    page.mouse.move(sx, sy)
    page.mouse.down()
    page.mouse.move(sx + 2, sy + 2)          # inside the click threshold
    # The release lands far away with no move event between.
    page.evaluate("""([x, y]) => window.dispatchEvent(new MouseEvent('mouseup',
        { clientX: x, clientY: y, button: 0, bubbles: true }))""", [ex, ey])
    page.mouse.up()
    assert sel_state(page)['keys'] == keys(a, [(0, 0), (0, 1), (1, 0), (1, 1)])
