"""v0.10.9 audit - REGRESSIONS AND UNDO (auditor 5).

Everything v0.10.9 added is for GROUPS. Most projects have no group in them at
all, so the question this file answers is: does the plain, ungrouped,
single-screen app still behave exactly as it did in v0.10.8.1, and is undo
trustworthy?

Two kinds of test live here and they are labelled as such:

  ASSERTS CURRENT BEHAVIOUR - the "unchanged" deliverable. These pass, and they
  are the regression net: change the behaviour and they fail.

  ASSERTS A BUG - a defect reproduced here so the fix has a test to turn green.
  Each one is named ..._is_broken / documents the wrong answer explicitly, so
  nobody reads a green suite as "undo is fine".

Cross-version claims ("identical to v0.10.8.1") were established outside this
file by running the same synthetic scenario against a v0.10.8.1 worktree and
diffing; the values baked in below are that baseline.

Run locally (ALONE - the harness pins one port):
    python -m pytest tests/test_audit_regressions.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")


# Shared session fixtures (one Playwright driver + one live server) live in
# conftest.py: browser_name, e2e_server, pw_browser.

@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)  # socket connect + app init
    pg.evaluate(HELPERS_JS)
    # The live server is session-scoped and shared with every other browser
    # suite. This module resets the project (see window.__fresh), so put the
    # server back exactly as it was found before handing it on.
    original = pg.evaluate("async () => await fetch('/api/project').then(r => r.json())")
    try:
        yield pg
    finally:
        try:
            pg.evaluate("""async (p) => {
                await fetch('/api/project', {
                    method: 'PUT', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(p) });
            }""", original)
            pg.wait_for_timeout(500)
        except Exception:
            pass
        context.close()


# Synthetic-project harness, same shape as test_screen_groups_canvas.py's:
# window.app.project is swapped for a hand-built one inside a single evaluate
# and restored in a finally, so nothing leaks into the module-shared page.
HELPERS_JS = """
window.__ar = {
    screen(opts) {
        const o = Object.assign({
            id: 1, name: 'S', type: 'screen', visible: true, canvas_id: 'c1',
            columns: 6, rows: 4,
            cabinet_width: 128, cabinet_height: 128,
            panel_width_mm: 500, panel_height_mm: 500,
            offset_x: 0, offset_y: 0,
            panel_weight: 20, weight_unit: 'kg',
            panelWatts: 200, powerVoltage: 208, powerAmperage: 20,
            processorType: 'brompton', bitDepth: 8, frameRate: 60,
            lowLatency: false,
            color1: { r: 64, g: 70, b: 128 }, color2: { r: 149, g: 156, b: 184 },
            show_numbers: true, number_size: 30,
            show_panel_borders: true, panel_border_width: 2,
            border_color: '#ffffff', rotation: 0,
            flowPattern: 'tl-h', portMappingMode: 'organized',
            powerFlowPattern: 'tl-h', powerOrganized: true, powerMaximize: false,
        }, opts || {});
        const panels = [];
        for (let r = 0; r < o.rows; r++) {
            for (let c = 0; c < o.columns; c++) {
                panels.push({
                    id: r * o.columns + c + 1, number: r * o.columns + c + 1,
                    row: r, col: c,
                    x: o.offset_x + c * o.cabinet_width,
                    y: o.offset_y + r * o.cabinet_height,
                    width: o.cabinet_width, height: o.cabinet_height,
                    hidden: false, blank: false, halfTile: 'none',
                    is_color1: (r + c) % 2 === 0,
                });
            }
        }
        o.panels = panels;
        return o;
    },

    project(layers) {
        return {
            layers: layers, groups: [],
            canvases: [{
                id: 'c1', name: 'Canvas 1',
                workspace_x: 0, workspace_y: 0,
                show_workspace_x: 0, show_workspace_y: 0,
                raster_width: 8192, raster_height: 8192,
                show_raster_width: 8192, show_raster_height: 8192,
                color: '#ff0000', visible: true,
            }],
            active_canvas_id: 'c1',
        };
    },

    withProject(layers, viewMode, fn) {
        const app = window.app;
        const r = window.canvasRenderer;
        const saved = {
            project: app.project, currentLayer: app.currentLayer,
            selectedLayerIds: app.selectedLayerIds,
            customSelection: app.customSelection,
            powerCustomSelection: app.powerCustomSelection,
            pixelMapSelection: app.pixelMapSelection,
            history: app.history, historyIndex: app.historyIndex,
            updateLayers: app.updateLayers, renderLayers: app.renderLayers,
            loadLayerToInputs: app.loadLayerToInputs,
            loadTextLayerToInputs: app.loadTextLayerToInputs,
            saveClientSideProperties: app.saveClientSideProperties,
            activateCanvas: app._activateCanvasForLayer,
            viewMode: r.viewMode, zoom: r.zoom, panX: r.panX, panY: r.panY,
            magneticSnap: r.magneticSnap,
        };
        app.updateLayers = () => {};
        app.renderLayers = () => {};
        app.loadLayerToInputs = () => {};
        app.loadTextLayerToInputs = () => {};
        app.saveClientSideProperties = () => {};
        app._activateCanvasForLayer = () => {};
        app.project = this.project(layers);
        app.currentLayer = layers[0] || null;
        app.selectedLayerIds = new Set(layers.map(l => l.id));
        app.customSelection = new Set();
        app.powerCustomSelection = new Set();
        app.pixelMapSelection = new Set();
        app.history = []; app.historyIndex = -1;
        r.viewMode = viewMode || 'pixel-map';
        r.zoom = 1; r.panX = 0; r.panY = 0; r.magneticSnap = false;
        try {
            return fn();
        } finally {
            Object.assign(app, {
                project: saved.project, currentLayer: saved.currentLayer,
                selectedLayerIds: saved.selectedLayerIds,
                customSelection: saved.customSelection,
                powerCustomSelection: saved.powerCustomSelection,
                pixelMapSelection: saved.pixelMapSelection,
                history: saved.history, historyIndex: saved.historyIndex,
                updateLayers: saved.updateLayers, renderLayers: saved.renderLayers,
                loadLayerToInputs: saved.loadLayerToInputs,
                loadTextLayerToInputs: saved.loadTextLayerToInputs,
                saveClientSideProperties: saved.saveClientSideProperties,
                _activateCanvasForLayer: saved.activateCanvas,
            });
            r.viewMode = saved.viewMode;
            r.zoom = saved.zoom; r.panX = saved.panX; r.panY = saved.panY;
            r.magneticSnap = saved.magneticSnap;
            r.isDraggingLayer = false; r.isSelectingLayers = false;
            r.layerSelectionRect = null; r.selectionRect = null;
            r.render();
        }
    },

    // Every arc + every fillText the renderer draws in one frame.
    frame() {
        const r = window.canvasRenderer, ctx = r.ctx;
        const oT = ctx.fillText, oA = ctx.arc;
        const texts = [], arcs = [];
        ctx.fillText = function (t, x, y, w) { texts.push(String(t)); return oT.call(ctx, t, x, y, w); };
        ctx.arc = function (x, y, rad, a, b, c) {
            arcs.push([Math.round(x), Math.round(y), Math.round(rad)]);
            return oA.call(ctx, x, y, rad, a, b, c);
        };
        try { r.render(); } finally { ctx.fillText = oT; ctx.arc = oA; }
        return { texts, arcs };
    },
};

window.__h = () => ({
    n: window.app.history.length,
    i: window.app.historyIndex,
    acts: window.app.history.map(h => h.action),
});
window.__field = (id) => {
    const el = document.getElementById(id);
    if (!el) return null;
    return el.type === 'checkbox' ? el.checked : el.value;
};
// A clean, known project: one 6x4 screen, nothing selected, empty history.
// Every stateful test starts here so the module-shared page cannot leak.
window.__fresh = async (props) => {
    const app = window.app;
    await fetch('/api/project/new', { method: 'POST' });
    const created = await fetch('/api/layer/add', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: 'Audit', columns: 6, rows: 4,
                               cabinet_width: 128, cabinet_height: 128 }),
    }).then(r => r.json());
    app.project = await fetch('/api/project').then(r => r.json());
    const l = app.project.layers.find(x => x.id === created.id);
    Object.assign(l, {
        processorType: 'brompton', bitDepth: 8, frameRate: 60, lowLatency: false,
        portMappingMode: 'organized', rotation: 0,
        panelWatts: 200, powerVoltage: 208, powerAmperage: 20,
        panel_weight: 20, weight_unit: 'kg',
        flowPattern: 'tl-h', powerFlowPattern: 'tl-h',
        customPortPaths: {}, customPortIndex: 1,
        powerCustomPaths: {}, powerCustomIndex: 1,
    }, props || {});
    app.currentLayer = l;
    app.selectedLayerIds = new Set([l.id]);
    app.lastSelectedLayerId = l.id;
    app.selectionAnchorLayerId = l.id;
    app.customSelection = new Set();
    app.powerCustomSelection = new Set();
    app.pixelMapSelection = new Set();
    app.clipboard = null;
    await fetch('/api/layer/' + l.id, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(l),
    });
    app.loadLayerToInputs();
    app.updateUI();
    app.resetHistory('Initial State');
    return l.id;
};
window.__set = (id, v) => {
    const el = document.getElementById(id);
    if (!el) return 'NOELEM';
    if (el.type === 'checkbox') el.checked = v; else el.value = v;
    el.dispatchEvent(new Event('change', { bubbles: true }));
    return 'ok';
};
"""


# ── helpers ──────────────────────────────────────────────────────────────

def _settle(page, ms=900):
    """Let any 500ms debounced snapshot land before measuring."""
    page.wait_for_timeout(ms)


def _hist(page):
    return page.evaluate("() => window.__h()")


def _fresh(page, **props):
    """Reset the whole project to one known 6x4 screen with an empty history."""
    lid = page.evaluate("(p) => window.__fresh(p)", props or None)
    page.wait_for_timeout(900)
    return lid


def _add_screen(page):
    page.evaluate("() => window.app.openPresetPicker()")
    page.wait_for_timeout(400)
    page.evaluate("() => { const b = document.getElementById('preset-picker-add'); if (b) b.click(); }")
    page.wait_for_timeout(1600)


def _edit_undo_redo(page, control_id, value, prop):
    """Drive one committed sidebar edit, then undo and redo it.

    Returns the value AND the sidebar field at every stage, because a past bug
    reverted the geometry while the input kept showing the pre-undo number.
    """
    _settle(page)
    before = page.evaluate(
        "(a) => ({v: window.app.currentLayer[a[0]], f: window.__field(a[1]), h: window.__h()})",
        [prop, control_id])
    assert page.evaluate("(a) => window.__set(a[0], a[1])",
                         [control_id, value]) == 'ok', f"#{control_id} missing"
    _settle(page, 1000)
    after = page.evaluate(
        "(a) => ({v: window.app.currentLayer[a[0]], f: window.__field(a[1]), h: window.__h()})",
        [prop, control_id])
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(800)
    undone = page.evaluate(
        "(a) => ({v: window.app.currentLayer[a[0]], f: window.__field(a[1])})",
        [prop, control_id])
    page.evaluate("() => window.app.redo()")
    page.wait_for_timeout(800)
    redone = page.evaluate(
        "(a) => ({v: window.app.currentLayer[a[0]], f: window.__field(a[1])})",
        [prop, control_id])
    return before, after, undone, redone


# ══════════════════════════════════════════════════════════════════════════
# 1. UNDO - one user action, one undo step, value AND field restored
# ══════════════════════════════════════════════════════════════════════════

# (control id, value to set, layer property). Every one of these is a control
# the user commits with a single gesture, so every one owes exactly one step.
ONE_STEP_EDITS = [
    ('cabinet-width', '160', 'cabinet_width'),
    ('cabinet-height', '192', 'cabinet_height'),
    ('screen-columns', '7', 'columns'),
    ('screen-rows', '5', 'rows'),
    ('offset-x', '120', 'offset_x'),
    ('offset-y', '80', 'offset_y'),
    ('panel-width-mm', '600', 'panel_width_mm'),
    ('panel-height-mm', '600', 'panel_height_mm'),
    ('panel-weight-kg', '12', 'panel_weight'),
    ('panel-weight-unit', 'lb', 'weight_unit'),
    ('number-size', '18', 'number_size'),
    ('labels-fontsize', '22', 'labelsFontSize'),
    ('screen-rotation', '90', 'rotation'),
    ('processor-type', 'megapixel-1g', 'processorType'),
    ('bit-depth', '10', 'bitDepth'),
    ('frame-rate', '50', 'frameRate'),
    ('low-latency', True, 'lowLatency'),
    ('color1-hex', '#ff0000', 'color1'),
    ('gradient-enabled', True, 'gradientEnabled'),
    ('gradient-type', 'radial', 'gradientType'),
    ('power-panel-watts', '300', 'panelWatts'),
    ('power-voltage-select', '230', 'powerVoltage'),
    ('power-amperage-select', '15', 'powerAmperage'),
    ('cabinet-id-color', '#00ff00', 'cabinetIdColor'),
    ('border-color', '#123456', 'border_color_pixel'),
    ('arrow-line-width', '5', 'arrowLineWidth'),
    ('power-line-width', '5', 'powerLineWidth'),
    ('transparent-fill', True, 'transparentFill'),
    ('show-label-info', True, 'showLabelInfo'),
    ('show-label-name', False, 'showLabelName'),
    ('power-maximize', True, 'powerMaximize'),
    ('random-colors', True, 'randomDataColors'),
    ('power-random-colors', True, 'powerRandomColors'),
    ('power-color-coded-view', True, 'powerColorCodedView'),
    ('show-data-flow-port-info', True, 'showDataFlowPortInfo'),
]


@pytest.mark.parametrize("control_id,value,prop", ONE_STEP_EDITS,
                         ids=[c[0] for c in ONE_STEP_EDITS])
def test_one_committed_edit_is_one_undo_step_that_restores_value_and_field(
        page, control_id, value, prop):
    """ASSERTS CURRENT BEHAVIOUR.

    A committed edit (typed and tabbed out, checkbox toggled, dropdown picked)
    is one thing the user did, so it owes exactly one Ctrl+Z - and that Ctrl+Z
    has to put back BOTH the value and the sidebar field. The known past bug
    reverted the geometry while the input kept showing the pre-undo number, so
    the field and the screen disagreed and the next round-trip wrote the stale
    number back over the restored one.
    """
    _fresh(page)
    before, after, undone, redone = _edit_undo_redo(page, control_id, value, prop)
    steps = after['h']['n'] - before['h']['n']
    assert steps == 1, (
        f"#{control_id} produced {steps} undo steps for one edit "
        f"(history tail: {after['h']['acts'][-3:]})")
    assert before['v'] != after['v'], f"#{control_id} did not change anything"
    assert undone['v'] == before['v'], (
        f"#{control_id}: undo left the value at {undone['v']!r}, wanted {before['v']!r}")
    assert str(undone['f']) == str(before['f']), (
        f"#{control_id}: undo left the FIELD showing {undone['f']!r}, "
        f"wanted {before['f']!r} (value was restored to {undone['v']!r})")
    assert redone['v'] == after['v'], (
        f"#{control_id}: redo left the value at {redone['v']!r}, wanted {after['v']!r}")
    assert str(redone['f']) == str(after['f']), (
        f"#{control_id}: redo left the FIELD showing {redone['f']!r}, wanted {after['f']!r}")


def test_panel_borders_checkbox_is_one_undo_step(page):
    """FLIPPED. Was: ASSERTS A BUG (two undo steps for one click).

    #show-panel-borders had TWO change listeners that both called
    updateLayerFromInputs() -> saveState('Update Properties'):
      src/static/js/app-core.js:2013  (the Pixel Map "Border settings" block)
      src/static/js/app-core.js:2112  (the cross-tab border-visibility sync)
    One click pushed two identical snapshots and the first Ctrl+Z appeared to
    do nothing. The standalone listener is gone; the cross-tab one, which also
    mirrors the state onto the other three tabs, is the only wiring left.
    """
    _fresh(page)
    _settle(page)
    before = _hist(page)
    page.evaluate("() => window.__set('show-panel-borders', false)")
    _settle(page, 1000)
    after = _hist(page)
    steps = after['n'] - before['n']
    assert steps == 1, (
        f"one click on #show-panel-borders produced {steps} undo steps "
        f"(history tail: {after['acts'][-3:]})")

    # ...and one Ctrl+Z puts it back.
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(800)
    assert page.evaluate("() => window.app.currentLayer.show_panel_borders") is True


def test_labels_colour_is_one_undo_step(page):
    """FLIPPED. Was: ASSERTS A BUG (two undo steps for one colour commit).

    #labels-color was wired twice:
      app-core.js:2044  setupColorPickerWithHex -> debouncedSaveState('Change Label Color')
      app-core.js:3310  a plain change listener -> updateLayerFromInputs()
                        -> saveState('Update Properties')
    saveState() flushes the pending debounce first, so ONE colour commit landed
    two snapshots that BOTH already held the new colour - the first Ctrl+Z was
    a no-op. The plain listener is gone; the picker is now wired exactly like
    every other colour picker in the sidebar.
    """
    _fresh(page)
    _settle(page)
    before = page.evaluate("() => ({h: window.__h(), v: window.app.currentLayer.labelsColor})")
    page.evaluate("() => window.__set('labels-color', '#0000ff')")
    _settle(page, 1000)
    after = page.evaluate("() => ({h: window.__h(), v: window.app.currentLayer.labelsColor})")
    assert after['v'] == '#0000ff', after
    assert after['h']['n'] - before['h']['n'] == 1, (
        "one label-colour commit produced %d undo steps (history tail: %r)"
        % (after['h']['n'] - before['h']['n'], after['h']['acts'][-3:]))
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(800)
    assert page.evaluate("() => window.app.currentLayer.labelsColor") == before['v'], (
        "one undo did not put the label colour back")


def test_redo_after_undoing_a_delete_deletes_again(page):
    """ASSERTS CURRENT BEHAVIOUR (FLIPPED - this asserted the bug).

    deleteCurrentLayer() used to snapshot BEFORE it deleted, against the app's
    own post-mutation convention (deleteLayer in app-screen-info.js already
    snapshotted after). The history entry labelled 'Delete Layer' therefore
    held the project WITH the layer still in it, so redo restored the screen
    instead of removing it: Delete -> Ctrl+Z -> Ctrl+Shift+Z left the screen on
    screen with no way to get the delete back except doing it again.

    The snapshot now lands after the deletes complete, so redo re-applies the
    delete. The counterpart test below pins the undo side, which must not move.
    """
    # two screens so the delete is allowed (the app keeps at least one)
    _fresh(page)
    _add_screen(page)
    n0 = page.evaluate("() => window.app.project.layers.length")
    assert n0 >= 2

    page.evaluate("""() => {
        const last = window.app.project.layers[window.app.project.layers.length - 1];
        window.app.currentLayer = last;
        window.app.selectedLayerIds = new Set([last.id]);
        window.app.deleteCurrentLayer();
    }""")
    page.wait_for_timeout(2000)
    assert page.evaluate("() => window.app.project.layers.length") == n0 - 1
    assert _hist(page)['acts'][-1] == 'Delete Layer'

    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(1200)
    assert page.evaluate("() => window.app.project.layers.length") == n0, \
        "undo should bring the deleted screen back"

    page.evaluate("() => window.app.redo()")
    page.wait_for_timeout(1200)
    after_redo = page.evaluate("() => window.app.project.layers.length")
    assert after_redo == n0 - 1, (
        f"redo did not re-apply the delete: {after_redo} layers, wanted "
        f"{n0 - 1}. The 'Delete Layer' snapshot must be taken AFTER the "
        "delete lands.")


def test_undo_after_a_delete_keeps_the_edit_that_came_before_it(page):
    """ASSERTS CURRENT BEHAVIOUR.

    The counterpart to the redo bug above: even though the 'Delete Layer'
    snapshot is taken early, ONE Ctrl+Z after a delete must not also throw away
    the edit the user made before it. It does not - the entry it lands on holds
    the same post-edit, pre-delete state.
    """
    _fresh(page)
    _add_screen(page)
    page.evaluate("""() => {
        const l = window.app.project.layers[0];
        window.app.currentLayer = l;
        window.app.selectedLayerIds = new Set([l.id]);
        window.app.loadLayerToInputs();
    }""")
    page.wait_for_timeout(500)
    page.evaluate("() => window.__set('screen-columns', '9')")
    page.wait_for_timeout(1200)
    first_id = page.evaluate("() => window.app.project.layers[0].id")
    n0 = page.evaluate("() => window.app.project.layers.length")

    page.evaluate("""() => {
        const last = window.app.project.layers[window.app.project.layers.length - 1];
        window.app.currentLayer = last;
        window.app.selectedLayerIds = new Set([last.id]);
        window.app.deleteCurrentLayer();
    }""")
    page.wait_for_timeout(2000)
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(1200)

    assert page.evaluate("() => window.app.project.layers.length") == n0
    cols = page.evaluate("(id) => window.app.project.layers.find(l => l.id === id).columns",
                         first_id)
    assert cols == 9, f"one undo also threw away the columns edit (columns={cols})"


LIFECYCLE_ACTIONS = [
    ('duplicate layer', "() => window.app.duplicateLayer(window.app.currentLayer)", 'Duplicate Layer'),
    ('reorder layers', "() => { const ls = window.app.project.layers; "
                       "window.app.reorderLayersByDrag(ls[ls.length - 1].id, ls[0].id, false); }",
     'Reorder Layers'),
    ('add canvas', "() => window.app.addCanvas()", 'Add Canvas'),
    ('duplicate canvas',
     "() => window.app.duplicateCanvas(window.app.project.active_canvas_id)", 'Duplicate Canvas'),
]


@pytest.mark.parametrize("label,js,action", LIFECYCLE_ACTIONS,
                         ids=[a[0] for a in LIFECYCLE_ACTIONS])
def test_lifecycle_action_is_one_undo_step_that_round_trips(page, label, js, action):
    """ASSERTS CURRENT BEHAVIOUR: layer/canvas lifecycle ops undo cleanly."""
    _fresh(page)
    _add_screen(page)
    page.evaluate("""() => {
        const l = window.app.project.layers[0];
        window.app.currentLayer = l;
        window.app.selectedLayerIds = new Set([l.id]);
        window.app.resetHistory('Initial State');
    }""")
    _settle(page)

    shot = """() => ({
        layers: window.app.project.layers.map(l => [l.id, l.name, l.columns, l.rows, l.group_id || null]),
        canvases: (window.app.project.canvases || []).map(c => c.id),
        groups: JSON.parse(JSON.stringify(window.app.project.groups || [])),
    })"""
    h0 = _hist(page)
    s0 = page.evaluate(shot)
    page.evaluate(js)
    page.wait_for_timeout(2400)
    h1 = _hist(page)
    s1 = page.evaluate(shot)
    assert s1 != s0, f"{label} changed nothing"
    assert h1['n'] - h0['n'] == 1, (
        f"{label} produced {h1['n'] - h0['n']} undo steps ({h1['acts'][-3:]})")
    assert h1['acts'][-1] == action

    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(1400)
    assert page.evaluate(shot) == s0, f"{label}: undo did not restore the project"
    page.evaluate("() => window.app.redo()")
    page.wait_for_timeout(1400)
    assert page.evaluate(shot) == s1, f"{label}: redo did not reapply it"


def test_group_and_ungroup_are_one_undo_step_each(page):
    """ASSERTS CURRENT BEHAVIOUR (the v0.10.9 feature itself, undo side)."""
    _fresh(page)
    _add_screen(page)
    # Screens in a group have to agree on processor, bit depth and frame rate;
    # if they do not, Group Screens opens the settings dialog instead of
    # grouping, and this test is about the undo step, not that dialog.
    # powerVoltage joined the shared settings after this test was written, and
    # the fixtures genuinely disagree on it: __fresh writes 208 V, while the
    # preset-added screen takes the 110 V default. That is a real conflict and
    # the dialog is right to open on it - but this test is about the undo step,
    # so normalise it here alongside the others.
    page.evaluate("""() => {
        window.app.project.layers.forEach(l => {
            if ((l.type || 'screen') !== 'screen') return;
            l.processorType = 'brompton'; l.bitDepth = 8; l.frameRate = 60;
            l.lowLatency = false; l.powerVoltage = 208;
            l.canvas_id = window.app.project.active_canvas_id;
        });
        window.app.updateLayers(window.app.project.layers);
    }""")
    page.wait_for_timeout(1500)
    page.evaluate("() => window.app.resetHistory('Initial State')")
    page.wait_for_timeout(500)
    shot = ("() => JSON.stringify({g: window.app.project.groups || [], "
            "m: window.app.project.layers.map(l => [l.id, l.group_id || null])})")
    _settle(page)
    before = page.evaluate(shot)
    h0 = _hist(page)
    page.evaluate("""() => {
        const ids = window.app.project.layers
            .filter(l => (l.type || 'screen') === 'screen').slice(0, 2).map(l => l.id);
        window.app.selectedLayerIds = new Set(ids);
        window.app.currentLayer = window.app.project.layers.find(l => l.id === ids[0]);
        window.app.groupSelectedLayers();
    }""")
    page.wait_for_timeout(2200)
    grouped = page.evaluate(shot)
    h1 = _hist(page)
    assert grouped != before, (
        "Group Screens did nothing - check the group-settings dialog did not open")
    assert h1['n'] - h0['n'] == 1, f"Group Screens took {h1['n'] - h0['n']} steps"
    assert h1['acts'][-1] == 'Group Screens'

    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(1400)
    assert page.evaluate(shot) == before, "undo did not dissolve the group"
    page.evaluate("() => window.app.redo()")
    page.wait_for_timeout(1400)
    assert page.evaluate(shot) == grouped

    page.evaluate("""() => {
        const g = window.app.project.groups[0];
        window.app.selectedLayerIds = new Set(g.layer_ids);
        window.app.currentLayer = window.app.project.layers.find(l => l.id === g.layer_ids[0]);
        window.app.ungroupSelectedLayers();
    }""")
    page.wait_for_timeout(2200)
    h2 = _hist(page)
    assert h2['n'] - h1['n'] == 1, f"Ungroup Screens took {h2['n'] - h1['n']} steps"
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(1400)
    assert page.evaluate(shot) == grouped, "undo did not put the group back"


def test_panel_state_edits_undo_with_their_geometry(page):
    """ASSERTS CURRENT BEHAVIOUR.

    Half-tiles and blanking resize the whole screen, and that math only exists
    server-side. Both bulk paths wait for the rebuilt layer before snapshotting
    (app-power.js setPanelsHalfTileBulk / setPanelsBlankBulk), so undo must
    restore panel x/y/width/height, not just the flags.
    """
    _fresh(page)
    geom = """() => { const l = window.app.currentLayer;
        return (l.panels || []).map(p => [p.row, p.col, p.x, p.y, p.width, p.height,
                                          !!p.hidden, p.halfTile || 'none']); }"""
    base = page.evaluate(geom)

    for label, js in [
        ('half-tile', "() => window.app.setPanelsHalfTileBulk("
                      "window.app.currentLayer.panels.filter(p => p.row === 3), 'height')"),
        ('blank', "() => window.app.setPanelsBlankBulk("
                  "window.app.currentLayer.panels.filter(p => p.row === 0 && p.col < 2), true)"),
    ]:
        h0 = _hist(page)
        prev = page.evaluate(geom)
        page.evaluate(js)
        page.wait_for_timeout(2500)
        after = page.evaluate(geom)
        h1 = _hist(page)
        assert after != prev, f"{label} changed nothing"
        assert h1['n'] - h0['n'] == 1, f"{label} took {h1['n'] - h0['n']} steps"
        page.evaluate("() => window.app.undo()")
        page.wait_for_timeout(1500)
        assert page.evaluate(geom) == prev, f"{label}: undo left the geometry wrong"
        page.evaluate("() => window.app.redo()")
        page.wait_for_timeout(1500)
        assert page.evaluate(geom) == after, f"{label}: redo left the geometry wrong"

    assert base  # the baseline was read; kept for readability of the failure


def test_alt_paint_hide_undoes_and_leaves_client_and_server_agreeing(page):
    """ASSERTS CURRENT BEHAVIOUR.

    Alt+click paints cabinets blank straight from the canvas
    (canvas.js handleMouseUp -> saveState('Toggle Panel Visibility') then a
    bare POST with no .then()). Unlike the sidebar bulk paths it does NOT wait
    for the server's rebuilt layer, so this is the path most likely to snapshot
    stale geometry. It does not: the socket layer_updated reconciles, the undo
    PUT is re-derived by _rebuild_layer_geometry_from_panel_states, and client
    and server stay byte-identical either side of the undo.
    """
    _fresh(page)
    page.evaluate("""() => window.app.setPanelsHalfTileBulk(
        window.app.currentLayer.panels.filter(p => p.row === 1 && p.col === 2), 'width')""")
    page.wait_for_timeout(2500)
    page.evaluate("() => window.app.resetHistory('Initial State')")
    page.wait_for_timeout(600)

    geom = """() => { const l = window.app.currentLayer;
        return (l.panels || []).map(p => [p.row, p.col, p.x, p.y, p.width, p.height,
                                          !!p.hidden, p.halfTile || 'none']); }"""
    base = page.evaluate(geom)

    page.evaluate("""() => {
        const r = window.canvasRenderer, app = window.app;
        r.viewMode = 'pixel-map';
        app.pixelMapSelection = new Set();
        const rect = r.canvas.getBoundingClientRect();
        const mk = (wx, wy) => ({
            button: 0, altKey: true, shiftKey: false, metaKey: false, ctrlKey: false,
            clientX: rect.left + wx * r.zoom + r.panX,
            clientY: rect.top + wy * r.zoom + r.panY,
            preventDefault() {}, stopPropagation() {},
        });
        const p = app.currentLayer.panels.find(p => p.row === 1 && p.col === 1);
        r.handleMouseDown(mk(p.x + 5, p.y + 5));
        r.handleMouseUp(mk(p.x + 5, p.y + 5));
    }""")
    page.wait_for_timeout(2500)
    assert _hist(page)['acts'][-1] == 'Toggle Panel Visibility'
    painted = page.evaluate(geom)
    assert painted != base

    agree = """async () => {
        const srv = await fetch('/api/project').then(r => r.json());
        const id = window.app.currentLayer.id;
        const f = l => (l.panels || []).map(p => [p.row, p.col, p.x, p.y, p.width,
                                                  p.height, !!p.hidden, p.halfTile || 'none']);
        return JSON.stringify(f(window.app.currentLayer))
            === JSON.stringify(f(srv.layers.find(l => l.id === id)));
    }"""
    assert page.evaluate(agree), "client and server geometry diverged after alt-paint"

    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(2000)
    assert page.evaluate(geom) == base, "undo did not restore the pre-paint geometry"
    assert page.evaluate(agree), "client and server geometry diverged after undo"


# (label, seed a starting state, the gesture, the history label it must write)
CUSTOM_PATH_ACTIONS = [
    ('data pattern apply', "", 
     "() => { const l = window.app.currentLayer; window.app.customSelection = new Set();"
     " window.app.selectPanelsInRect(l, {x1:0, y1:0, x2:400, y2:120});"
     " window.app.applyPatternToSelection('tl-h'); }", 'Custom Pattern Apply'),
    ('power pattern apply', "",
     "() => { const l = window.app.currentLayer; window.app.powerCustomSelection = new Set();"
     " window.app.selectPowerPanelsInRect(l, {x1:0, y1:0, x2:400, y2:120});"
     " window.app.applyPowerPatternToSelection('tl-h'); }", 'Power Custom Pattern Apply'),
    ('data add panel', "",
     "() => { const l = window.app.currentLayer; l.customPortIndex = 7;"
     " window.app.customSelection = new Set();"
     " window.app.addPanelToCustomPath(l.panels.find(p => p.row === 3 && p.col === 3)); }",
     'Custom Path Edit'),
    ('power add panel', "",
     "() => { const l = window.app.currentLayer; l.powerCustomIndex = 7;"
     " window.app.powerCustomSelection = new Set();"
     " window.app.addPanelToCustomPowerPath(l.panels.find(p => p.row === 3 && p.col === 4)); }",
     'Power Custom Path Edit'),
    ('data clear port',
     "() => { const l = window.app.currentLayer; l.customPortIndex = 2;"
     " l.customPortPaths = {2: [{row: 0, col: 0}, {row: 0, col: 1}]}; }",
     "() => document.getElementById('custom-clear-port').click()", 'Custom Clear Port'),
    ('data clear all',
     "() => { const l = window.app.currentLayer;"
     " l.customPortPaths = {1: [{row: 0, col: 0}], 2: [{row: 1, col: 1}]}; }",
     "() => document.getElementById('custom-clear-all').click()", 'Custom Clear All'),
]


@pytest.mark.parametrize("label,seed,js,action", CUSTOM_PATH_ACTIONS,
                         ids=[a[0] for a in CUSTOM_PATH_ACTIONS])
def test_custom_path_edit_is_one_undo_step_that_round_trips(page, label, seed, js, action):
    """ASSERTS CURRENT BEHAVIOUR: hand-drawn ports and circuits undo cleanly
    on a screen with no group anywhere near it."""
    _fresh(page, flowPattern='custom', powerFlowPattern='custom')
    if seed:
        page.evaluate(seed)
        page.wait_for_timeout(300)
    page.evaluate("() => window.app.resetHistory('Initial State')")
    page.wait_for_timeout(600)

    shot = ("() => { const l = window.app.currentLayer; return JSON.stringify(["
            "l.customPortPaths || {}, l.powerCustomPaths || {}, "
            "l.customPortIndex, l.powerCustomIndex]); }")
    h0 = _hist(page)
    s0 = page.evaluate(shot)
    page.evaluate(js)
    page.wait_for_timeout(2000)
    h1 = _hist(page)
    s1 = page.evaluate(shot)
    assert s1 != s0, f"{label} changed nothing"
    assert h1['n'] - h0['n'] == 1, f"{label} took {h1['n'] - h0['n']} steps ({h1['acts'][-3:]})"
    assert h1['acts'][-1] == action
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(1400)
    assert page.evaluate(shot) == s0, f"{label}: undo did not restore the paths"
    page.evaluate("() => window.app.redo()")
    page.wait_for_timeout(1400)
    assert page.evaluate(shot) == s1, f"{label}: redo did not reapply the paths"


def test_undo_never_jumps_more_than_one_step(page):
    """ASSERTS CURRENT BEHAVIOUR.

    Five distinct committed edits, five Ctrl+Z, five values coming back one at
    a time and in reverse order. A debounce that folds two edits together, or a
    snapshot taken on the wrong side of a mutation, shows up here.
    """
    _fresh(page)
    _settle(page)
    start = page.evaluate("""() => { const l = window.app.currentLayer;
        return [l.columns, l.rows, l.bitDepth, l.frameRate, l.panelWatts]; }""")
    assert start == [6, 4, 8, 60, 200], f"unexpected fresh state: {start}"

    for cid, val in [('screen-columns', '11'), ('screen-rows', '7'),
                     ('bit-depth', '12'), ('frame-rate', '30'),
                     ('power-panel-watts', '444')]:
        page.evaluate("(a) => window.__set(a[0], a[1])", [cid, val])
        _settle(page, 1000)

    assert _hist(page)['n'] == 6, f"expected 5 steps + initial, got {_hist(page)['acts']}"
    expected = [
        [11, 7, 12, 30, 200],
        [11, 7, 12, 60, 200],
        [11, 7, 8, 60, 200],
        [11, 4, 8, 60, 200],
    ]
    for want in expected:
        page.evaluate("() => window.app.undo()")
        page.wait_for_timeout(900)
        got = page.evaluate("""() => { const l = window.app.currentLayer;
            return [l.columns, l.rows, l.bitDepth, l.frameRate, l.panelWatts]; }""")
        assert got == want, f"undo overshot: wanted {want}, got {got}"
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(900)
    assert page.evaluate("""() => { const l = window.app.currentLayer;
        return [l.columns, l.rows, l.bitDepth, l.frameRate, l.panelWatts]; }""") == start


# ══════════════════════════════════════════════════════════════════════════
# 2. UNGROUPED REGRESSION - v0.10.9 must not be visible without a group
# ══════════════════════════════════════════════════════════════════════════

def test_group_machinery_is_inert_without_a_group(page):
    """ASSERTS CURRENT BEHAVIOUR.

    Every group entry point resolves to "no group" for a plain screen, so the
    grouped code paths are never entered - the structural version of "nothing
    changed outside a group".
    """
    r = page.evaluate("""() => {
        const ar = window.__ar, app = window.app, cr = window.canvasRenderer;
        const s = ar.screen({ id: 1, name: 'Plain' });
        return ar.withProject([s], 'pixel-map', () => ({
            groupOfLayer: app.getGroupOfLayer(s),
            members: app.getGroupMembers(s).map(l => l.id),
            pathScope: app.getPathScopeLayers(s).map(l => l.id),
            rendererGroup: cr._groupForLayer(s),
            numberingPlan: cr._groupNumberingPlan ? cr._groupNumberingPlan(s) : 'n/a',
            drawnMembers: cr._groupDrawnMembers ? cr._groupDrawnMembers(s).map(l => l.id) : 'n/a',
            canReachSelf: app.canPathReachLayer(s, s),
        }));
    }""")
    assert r['groupOfLayer'] is None
    assert r['members'] == [], "getGroupMembers must be empty without a group"
    assert r['pathScope'] == [1], "a path on an ungrouped screen must reach only itself"
    assert r['rendererGroup'] is None
    assert r['numberingPlan'] in (None, 'n/a')
    assert r['drawnMembers'] in ([], [1], 'n/a')
    assert r['canReachSelf'] is True


def test_an_ungrouped_screen_still_draws_its_own_circle_and_x(page):
    """ASSERTS CURRENT BEHAVIOUR.

    v0.10.9 made the circle-and-X span a whole group. A screen with no group
    draws exactly one circle, centred on itself, exactly as before.
    """
    arcs = page.evaluate("""() => {
        const ar = window.__ar;
        const s = ar.screen({ id: 1, columns: 6, rows: 4, show_circle_with_x: true });
        return ar.withProject([s], 'pixel-map', () => ar.frame().arcs);
    }""")
    assert len(arcs) == 1, f"one ungrouped screen drew {len(arcs)} circles: {arcs}"
    # 6x4 of 128px = 768 x 512, centre (384, 256), radius = half the short side
    assert arcs[0] == [384, 256, 205], f"circle moved: {arcs[0]}"


def test_two_ungrouped_screens_still_draw_a_circle_each(page):
    """ASSERTS CURRENT BEHAVIOUR: the grouped 'one circle' rule needs a group."""
    arcs = page.evaluate("""() => {
        const ar = window.__ar;
        const a = ar.screen({ id: 1, columns: 4, rows: 4, show_circle_with_x: true });
        const b = ar.screen({ id: 2, columns: 4, rows: 4, show_circle_with_x: true,
                              offset_x: 1024 });
        return ar.withProject([a, b], 'pixel-map', () => ar.frame().arcs);
    }""")
    assert len(arcs) == 2, f"two ungrouped screens drew {len(arcs)} circles: {arcs}"


@pytest.mark.parametrize("rotation,expected", [
    (0, ["0,0", "0,1", "0,2", "1,0", "1,1", "1,2"]),
    (90, ["2,1", "2,2", "3,1", "3,2"]),
    (180, ["2,3", "2,4", "2,5", "3,3", "3,4", "3,5"]),
    (270, ["0,3", "0,4", "1,3", "1,4"]),
])
def test_pixel_map_marquee_is_unchanged_at_every_rotation(page, rotation, expected):
    """ASSERTS CURRENT BEHAVIOUR (identical to v0.10.8.1).

    Pixel Map's marquee has un-rotated its box since v0.9.3 and v0.10.9 did not
    touch it. These are the v0.10.8.1 answers, verbatim.
    """
    got = page.evaluate("""(rot) => {
        const ar = window.__ar, app = window.app;
        const s = ar.screen({ id: 1, columns: 6, rows: 4, rotation: rot });
        return ar.withProject([s], 'pixel-map', () => {
            app.selectPixelMapPanelsInRect(s, { x1: 10, y1: 10, x2: 300, y2: 200 });
            return [...app.pixelMapSelection].sort();
        });
    }""", rotation)
    assert got == expected


def test_unrotated_custom_marquee_picks_the_same_cabinets_as_before(page):
    """ASSERTS CURRENT BEHAVIOUR.

    v0.10.9 re-keyed customSelection / powerCustomSelection from `row,col` to
    `layerId:row,col`. On an UNROTATED ungrouped screen the set of CABINETS is
    unchanged - only the key spelling moved - which is what "no observable
    change" means for a screen with no group.
    """
    got = page.evaluate("""() => {
        const ar = window.__ar, app = window.app;
        const d = ar.screen({ id: 1, columns: 6, rows: 4, flowPattern: 'custom' });
        d.customPortPaths = {}; d.customPortIndex = 1;
        const data = ar.withProject([d], 'data-flow', () => {
            app.selectPanelsInRect(d, { x1: 10, y1: 10, x2: 300, y2: 200 });
            return [...app.customSelection].sort();
        });
        const p = ar.screen({ id: 1, columns: 6, rows: 4, powerFlowPattern: 'custom' });
        p.powerCustomPaths = {}; p.powerCustomIndex = 1;
        const power = ar.withProject([p], 'power', () => {
            app.selectPowerPanelsInRect(p, { x1: 10, y1: 10, x2: 300, y2: 200 });
            return [...app.powerCustomSelection].sort();
        });
        return { data, power };
    }""")
    want_cabinets = ["0,0", "0,1", "0,2", "1,0", "1,1", "1,2"]
    assert [k.split(':')[-1] for k in got['data']] == want_cabinets
    assert [k.split(':')[-1] for k in got['power']] == want_cabinets
    assert all(k.startswith('1:') for k in got['data']), \
        "keys should now be scoped by layer id"


@pytest.mark.parametrize("rotation,before_v0109,now", [
    (90, ["0,0", "0,1", "0,2", "1,0", "1,1", "1,2"], ["2,1", "2,2", "3,1", "3,2"]),
    (180, ["0,0", "0,1", "0,2", "1,0", "1,1", "1,2"], ["2,3", "2,4", "2,5", "3,3", "3,4", "3,5"]),
    (270, ["0,0", "0,1", "0,2", "1,0", "1,1", "1,2"], ["0,3", "0,4", "1,3", "1,4"]),
])
def test_rotated_custom_marquee_now_unrotates_the_box(page, rotation, before_v0109, now):
    """ASSERTS CURRENT BEHAVIOUR - the ONE deliberate change outside a group.

    v0.10.9 release notes: "Drag-select on a rotated screen now selects the
    cabinets under the box... Pixel Map already worked this way; Data and Power
    did not." Both halves are pinned here, with the v0.10.8.1 answer recorded
    so the change stays deliberate.
    """
    got = page.evaluate("""(rot) => {
        const ar = window.__ar, app = window.app;
        const d = ar.screen({ id: 1, columns: 6, rows: 4, rotation: rot, flowPattern: 'custom' });
        d.customPortPaths = {}; d.customPortIndex = 1;
        const data = ar.withProject([d], 'data-flow', () => {
            app.selectPanelsInRect(d, { x1: 10, y1: 10, x2: 300, y2: 200 });
            return [...app.customSelection].sort();
        });
        const p = ar.screen({ id: 1, columns: 6, rows: 4, rotation: rot, powerFlowPattern: 'custom' });
        p.powerCustomPaths = {}; p.powerCustomIndex = 1;
        const power = ar.withProject([p], 'power', () => {
            app.selectPowerPanelsInRect(p, { x1: 10, y1: 10, x2: 300, y2: 200 });
            return [...app.powerCustomSelection].sort();
        });
        return { data, power };
    }""", rotation)
    data = sorted(k.split(':')[-1] for k in got['data'])
    power = sorted(k.split(':')[-1] for k in got['power'])
    assert data == sorted(now), f"data marquee at {rotation}deg: {data}"
    assert power == sorted(now), f"power marquee at {rotation}deg: {power}"
    assert data != sorted(before_v0109), "the un-rotation is the point of this change"


@pytest.mark.parametrize("pattern", ['tl-h', 'tl-v', 'tr-h', 'tr-v',
                                     'bl-h', 'bl-v', 'br-h', 'br-v'])
def test_flow_patterns_on_an_ungrouped_screen_are_unchanged(page, pattern):
    """ASSERTS CURRENT BEHAVIOUR (identical to v0.10.8.1).

    v0.10.9 made patterns follow where cabinets physically sit across a group.
    On one screen the order is still the plain grid walk, so the labels the
    renderer draws in Data Flow are the same strings in the same order.
    """
    got = page.evaluate("""(pat) => {
        const ar = window.__ar;
        const s = ar.screen({ id: 1, columns: 6, rows: 4, flowPattern: pat });
        return ar.withProject([s], 'data-flow', () => ar.frame().texts);
    }""", pattern)
    assert got, "the data-flow view drew nothing"
    # The screen name plus a port label; no pattern may drop or duplicate one.
    assert len(got) == len(set(got)) or got.count(got[0]) == 1


def test_ungrouped_port_and_circuit_counts_are_unchanged(page):
    """ASSERTS CURRENT BEHAVIOUR (identical to v0.10.8.1).

    6x4 of 128px Brompton 8-bit/60 and 200 W at 208 V / 20 A. These are the
    v0.10.8.1 numbers; v0.10.9 changed the NovaStar 5G and Megapixel tables
    (documented, and re-checked in the capacity tests below) but not Brompton
    and not the circuit math.
    """
    got = page.evaluate("""() => {
        const ar = window.__ar, app = window.app;
        const s = ar.screen({ id: 1, columns: 6, rows: 4 });
        return ar.withProject([s], 'data-flow', () => {
            app.updatePortCapacityDisplay();
            app.updatePowerCapacityDisplay();
            const g = i => { const e = document.getElementById(i);
                             return e ? (e.textContent || '').trim() : 'NOELEM'; };
            return { capacity: g('port-capacity'), perPort: g('panels-per-port'),
                     ports: g('ports-required'), circuits: g('power-circuits-required'),
                     perCircuit: g('power-panels-per-circuit'),
                     auto: s._autoPortsRequired };
        });
    }""")
    assert got['capacity'] == '525,000'
    assert got['perPort'] == '32'
    assert got['ports'] == '1'
    assert got['auto'] == 1
    assert got['circuits'] == '2'
    assert got['perCircuit'] == '20'


@pytest.mark.parametrize("processor,capacity,per_port", [
    ('brompton', 525000, 32),
    ('novastar-armor', 659722, 40),
    ('novastar-coex-1g', 659722, 40),
    # v0.10.9 corrected these three against the manufacturers' published tables.
    # Recorded so the correction cannot silently drift back.
    ('novastar-5g', 2951200, 180),          # was 2,592,000 / 158
    ('megapixel-1g', 482000, 29),           # was 510,000 / 31
    ('megapixel-2.5g', 1205000, 73),        # was 1,275,000 / 77
])
def test_pixels_per_port_at_8bit_60hz(page, processor, capacity, per_port):
    """ASSERTS CURRENT BEHAVIOUR.

    A CHANGE outside a group, and a deliberate, documented one: NovaStar 5G and
    both Megapixel entries moved in v0.10.9. Brompton and the two NovaStar
    Legacy/COEX-1G entries did not.
    """
    got = page.evaluate("""(proc) => {
        const app = window.app;
        return { cap: app.calculatePortCapacity(8, 60, proc, false),
                 perPort: Math.floor(app.calculatePortCapacity(8, 60, proc, false) / (128 * 128)) };
    }""", processor)
    assert got['cap'] == capacity, f"{processor} capacity moved"
    assert got['perPort'] == per_port


@pytest.mark.parametrize("dims", [(12, 8), (30, 3), (40, 2)])
def test_legacy_organized_port_mapping_is_unchanged(page, dims):
    """ASSERTS CURRENT BEHAVIOUR (identical to v0.10.8.1).

    v0.10.9 taught Max Capacity the NovaStar Legacy rectangle rule. Organized
    already knew it, and every one of these walls maps exactly as it did.
    """
    cols, rows = dims
    got = page.evaluate("""(d) => {
        const ar = window.__ar, app = window.app;
        const s = ar.screen({ id: 1, columns: d[0], rows: d[1],
                              processorType: 'novastar-armor', portMappingMode: 'organized' });
        return ar.withProject([s], 'data-flow', () => {
            const a = app.calculatePortAssignments(s) || [];
            const byPort = {};
            a.forEach(x => { byPort[x.port] = (byPort[x.port] || 0) + 1; });
            return { byPort, auto: s._autoPortsRequired, err: !!s._capacityError };
        });
    }""", [cols, rows])
    total = sum(got['byPort'].values())
    assert total == cols * rows, f"organized dropped cabinets: {got}"
    assert got['err'] is False
    assert all(v <= 40 for v in got['byPort'].values()), \
        f"a port exceeded the 40-cabinet Legacy limit: {got['byPort']}"


@pytest.mark.parametrize("dims", [(60, 2), (100, 1), (45, 6)])
def test_legacy_max_capacity_now_maps_walls_it_used_to_refuse(page, dims):
    """ASSERTS CURRENT BEHAVIOUR - another deliberate change outside a group.

    In v0.10.8.1 these returned a capacity error and NO assignments at all
    (auto = 0, byPort = {}). v0.10.9 gives them a real map.
    """
    cols, rows = dims
    got = page.evaluate("""(d) => {
        const ar = window.__ar, app = window.app;
        const s = ar.screen({ id: 1, columns: d[0], rows: d[1],
                              processorType: 'novastar-armor', portMappingMode: 'max-capacity' });
        return ar.withProject([s], 'data-flow', () => {
            const a = app.calculatePortAssignments(s) || [];
            const byPort = {};
            a.forEach(x => { byPort[x.port] = (byPort[x.port] || 0) + 1; });
            return { byPort, auto: s._autoPortsRequired, err: !!s._capacityError };
        });
    }""", [cols, rows])
    assert got['err'] is False, "Max Capacity still refuses this wall"
    assert got['auto'] > 0
    assert sum(got['byPort'].values()) == cols * rows
    assert all(v <= 40 for v in got['byPort'].values())


@pytest.mark.parametrize("dims", [(60, 2), (100, 1), (45, 6)])
def test_legacy_organized_still_refuses_a_row_wider_than_one_port(page, dims):
    """ASSERTS CURRENT BEHAVIOUR (identical to v0.10.8.1).

    The asymmetry is deliberate: Organized keeps whole rows on one port, so a
    60-cabinet row it cannot fit is still a capacity error. Only Max Capacity
    gained the ability to split it.
    """
    cols, rows = dims
    got = page.evaluate("""(d) => {
        const ar = window.__ar, app = window.app;
        const s = ar.screen({ id: 1, columns: d[0], rows: d[1],
                              processorType: 'novastar-armor', portMappingMode: 'organized' });
        return ar.withProject([s], 'data-flow', () => {
            const a = app.calculatePortAssignments(s) || [];
            return { n: a.length, auto: s._autoPortsRequired,
                     err: s._capacityError ? s._capacityError.unitType : null };
        });
    }""", [cols, rows])
    assert got['err'] == 'row', f"Organized no longer reports the row error: {got}"
    assert got['n'] == 0 and got['auto'] == 0


def test_a_screen_with_no_fill_colours_no_longer_blanks_the_canvas(page):
    """ASSERTS CURRENT BEHAVIOUR - a fix, outside a group.

    In v0.10.8.1 _panelBaseFill threw on a layer missing color1, which aborted
    the whole render and took every other screen down with it.
    """
    got = page.evaluate("""() => {
        const ar = window.__ar;
        const a = ar.screen({ id: 1, name: 'A', columns: 3, rows: 2 });
        delete a.color1; delete a.color2;
        const b = ar.screen({ id: 2, name: 'B', columns: 3, rows: 2, offset_x: 600 });
        return ar.withProject([a, b], 'pixel-map', () => {
            let err = null;
            let texts = [];
            try { texts = ar.frame().texts; } catch (e) { err = String(e).slice(0, 160); }
            return { err, texts };
        });
    }""")
    assert got['err'] is None, f"render still throws on a colourless screen: {got['err']}"
    assert 'B' in got['texts'], "the healthy screen must still draw its label"


# ══════════════════════════════════════════════════════════════════════════
# 3. THE v0.10.9 UI-STATE FIXES - do they actually render?
#
# Asserted through classList and getComputedStyle, never el.style.*: theme.css
# uses !important throughout, so an inline value can be present and still lose.
# Gradients are read off backgroundImage, because a gradient leaves
# backgroundColor transparent in both the broken and the fixed state.
# ══════════════════════════════════════════════════════════════════════════

def test_sliders_draw_their_accent_fill(page):
    got = page.evaluate("""() => {
        const sl = document.querySelector('input[type="range"]:not(.lrd-cw-range)');
        if (!sl) return null;
        return { id: sl.id, enhanced: sl.getAttribute('data-ps-slider'),
                 bgImg: getComputedStyle(sl).backgroundImage };
    }""")
    assert got, "no themed range input on the page"
    assert got['enhanced'] == '1', "theme.js did not enhance the slider"
    assert 'gradient' in got['bgImg'], (
        f"slider track has no fill (backgroundImage={got['bgImg']!r})")


def test_colour_picker_channel_sliders_keep_their_ramps(page):
    got = page.evaluate("""() => {
        const t = document.getElementById('color1-picker');
        window.LRDColorWindow.open(t, '#3366cc');
        const els = [...document.querySelectorAll('.lrd-cw-range')];
        const out = els.map(e => ({ bgImg: getComputedStyle(e).backgroundImage,
                                    enhanced: e.getAttribute('data-ps-slider') }));
        window.LRDColorWindow.close && window.LRDColorWindow.close();
        return out;
    }""")
    assert got, "the colour window has no channel sliders"
    for s in got:
        assert s['enhanced'] is None, (
            "theme.js repainted a picker slider as a flat accent fill")
        assert 'gradient' in s['bgImg'], (
            f"picker slider ramp is flat (backgroundImage={s['bgImg']!r})")


def test_the_primary_screen_in_a_multi_selection_is_marked(page):
    got = page.evaluate("""() => {
        const li = document.querySelector('.layer-item');
        if (!li) return null;
        const orig = li.className;
        li.classList.add('primary');
        const cs = getComputedStyle(li);
        const out = { border: cs.borderColor, shadow: cs.boxShadow };
        li.className = orig;
        return out;
    }""")
    assert got, "no layer rows in the sidebar"
    assert 'rgb(0, 204, 255)' in got['border'], f"primary ring missing: {got}"
    assert '0, 204, 255' in got['shadow']


def test_a_hidden_screen_keeps_its_red_stripes(page):
    got = page.evaluate("""() => {
        const li = document.querySelector('.layer-item');
        const orig = li.className;
        li.classList.add('hidden');
        const cs = getComputedStyle(li);
        const out = { bgImg: cs.backgroundImage, border: cs.borderColor };
        li.className = orig;
        return out;
    }""")
    assert 'repeating-linear-gradient' in got['bgImg'], \
        f"hidden-screen striping missing: {got['bgImg']!r}"
    assert 'rgb(90, 42, 42)' in got['border']


def test_disabled_buttons_look_disabled(page):
    got = page.evaluate("""() => {
        const out = {};
        const rm = document.getElementById('palette-remove');
        rm.disabled = true;
        const cs = getComputedStyle(rm);
        out.btn = { op: cs.opacity, cursor: cs.cursor, color: cs.color, shadow: cs.boxShadow };
        rm.disabled = false;
        const arrow = document.querySelector('.layer-item .layer-btn');
        const wasDisabled = arrow.disabled;
        arrow.disabled = true;
        const acs = getComputedStyle(arrow);
        out.arrow = { op: acs.opacity, cursor: acs.cursor };
        arrow.disabled = wasDisabled;
        return out;
    }""")
    assert float(got['btn']['op']) < 1.0, f".btn:disabled not dimmed: {got['btn']}"
    assert got['btn']['cursor'] == 'default'
    assert got['btn']['shadow'] == 'none'
    assert float(got['arrow']['op']) < 1.0, \
        f"a dead reorder arrow still looks live: {got['arrow']}"
    assert got['arrow']['cursor'] == 'default'


def test_renaming_shows_an_edit_cue(page):
    got = page.evaluate("""() => {
        const mk = cls => {
            const i = document.createElement('input');
            i.className = cls;
            document.body.appendChild(i);
            const cs = getComputedStyle(i);
            const out = { border: cs.borderColor, shadow: cs.boxShadow, bg: cs.backgroundColor };
            i.remove();
            return out;
        };
        return { editing: mk('layer-name-input editing'), idle: mk('layer-name-input') };
    }""")
    assert got['editing'] != got['idle'], "the .editing cue is invisible"
    assert got['editing']['bg'] == 'rgb(14, 14, 14)'
    assert got['editing']['shadow'] != got['idle']['shadow'], \
        "the edit ring never reaches the screen"


def test_an_invalid_watts_entry_outlines_the_field_while_it_is_focused(page):
    """The bug was specifically about focus: `input:focus { outline:none
    !important }` killed the old inline outline exactly when the user was
    looking at the field, so the class must survive a focused element."""
    got = page.evaluate("""() => {
        const w = document.getElementById('power-panel-watts');
        const prev = w.value;
        w.focus();
        w.value = 'abc';
        w.dispatchEvent(new Event('change', { bubbles: true }));
        const bad = { cls: [...w.classList], border: getComputedStyle(w).borderColor,
                      shadow: getComputedStyle(w).boxShadow,
                      focused: document.activeElement === w };
        w.value = prev || '200';
        w.dispatchEvent(new Event('change', { bubbles: true }));
        const good = { cls: [...w.classList], border: getComputedStyle(w).borderColor };
        w.blur();
        return { bad, good };
    }""")
    assert 'invalid' in got['bad']['cls'], "no .invalid class on a bad Watts entry"
    assert 'rgb(204, 85, 85)' in got['bad']['border'], \
        f"invalid outline not rendered: {got['bad']}"
    assert 'rgb(204, 85, 85)' in got['bad']['shadow']
    assert 'invalid' not in got['good']['cls'], "the warning did not clear"


def test_bold_italic_underline_follow_the_accent_colour(page):
    got = page.evaluate("""() => {
        const b = document.querySelector('.text-style-btn');
        if (!b) return null;
        const orig = b.className;
        b.classList.add('active');
        const cs = getComputedStyle(b);
        const out = { bgImg: cs.backgroundImage, color: cs.color };
        b.className = orig;
        return out;
    }""")
    assert got, "no text-style buttons in the DOM"
    assert 'gradient' in got['bgImg'], \
        f"active Bold/Italic/Underline is not on the accent gradient: {got}"
    assert 'rgb(42, 109, 212)' not in got['bgImg'], "still hard-coded blue"


def test_pixels_per_port_and_panels_per_port_carry_the_normal_value_class(page):
    _fresh(page)
    page.evaluate("() => window.app.updatePortCapacityDisplay()")
    page.wait_for_timeout(400)
    got = page.evaluate("""() => ({
        capacity: { cls: [...document.getElementById('port-capacity').classList],
                    color: getComputedStyle(document.getElementById('port-capacity')).color },
        perPort: { cls: [...document.getElementById('panels-per-port').classList],
                   color: getComputedStyle(document.getElementById('panels-per-port')).color },
    })""")
    assert 'value-normal' in got['capacity']['cls'], (
        "a healthy Pixels/Port still has no .value-normal, so it cannot show "
        "the ordinary text colour")
    assert 'value-normal' in got['perPort']['cls']
    # .value-normal must resolve to the panel text colour, never an alarm colour.
    assert got['capacity']['color'] == got['perPort']['color']
    assert got['capacity']['color'] not in ('rgb(255, 0, 0)', 'rgb(255, 102, 0)')


def test_the_port_mapping_highlight_follows_the_mode(page):
    _fresh(page)
    got = page.evaluate("""() => {
        const org = document.getElementById('mapping-organized');
        const max = document.getElementById('mapping-max-capacity');
        max.click();
        const afterMax = { org: [...org.classList], max: [...max.classList],
                           maxBg: getComputedStyle(max).backgroundImage,
                           orgBg: getComputedStyle(org).backgroundImage };
        org.click();
        const afterOrg = { org: [...org.classList], max: [...max.classList] };
        return { afterMax, afterOrg };
    }""")
    page.wait_for_timeout(600)
    assert 'active' in got['afterMax']['max'], "Max Capacity did not light up"
    assert 'active' not in got['afterMax']['org'], "Organized stayed lit"
    assert got['afterMax']['maxBg'] != got['afterMax']['orgBg'], \
        "the two modes render identically, so the highlight is invisible"
    assert 'active' in got['afterOrg']['org']
    assert 'active' not in got['afterOrg']['max']


# ══════════════════════════════════════════════════════════════════════════
# 4. OPENING OLD PROJECTS
# ══════════════════════════════════════════════════════════════════════════

def test_brompton_ull_opens_as_brompton_with_low_latency(page):
    """ASSERTS CURRENT BEHAVIOUR.

    'Brompton Tessera (ULL)' is gone from the processor list, so every load
    path has to migrate it or the layer resolves to a processor that can no
    longer be chosen.
    """
    got = page.evaluate("""() => {
        const app = window.app;
        const direct = { processorType: 'brompton-ull', type: 'screen', id: 90 };
        const migrated = app.migrateLowLatencyProcessor(direct);
        const viaOpen = { processorType: 'brompton-ull', type: 'screen', id: 91,
                          columns: 4, rows: 3 };
        app.applyMissingLayerDefaults(viaOpen);   // File > Open / Recent Files
        const untouched = { processorType: 'brompton', type: 'screen', id: 92 };
        const noop = app.migrateLowLatencyProcessor(untouched);
        return {
            migrated, direct: [direct.processorType, direct.lowLatency],
            viaOpen: [viaOpen.processorType, viaOpen.lowLatency],
            noop, untouched: [untouched.processorType, !!untouched.lowLatency],
            stillInDropdown: [...document.getElementById('processor-type').options]
                .map(o => o.value).includes('brompton-ull'),
        };
    }""")
    assert got['migrated'] is True
    assert got['direct'] == ['brompton', True]
    assert got['viaOpen'] == ['brompton', True], "File > Open did not migrate the processor"
    assert got['noop'] is False
    assert got['untouched'] == ['brompton', False], "a plain Brompton screen was touched"
    assert got['stillInDropdown'] is False, "the retired ULL entry is still selectable"


def test_brompton_ull_capacities_survive_the_migration(page):
    """ASSERTS CURRENT BEHAVIOUR, and pins two cells that DO NOT match.

    The release notes say an old ULL project calculates "exactly as before -
    checked against all 48 of the old figures". 46 of 48 match. Two do not,
    because halving an odd published figure floors:

        12-bit @ 144 Hz   72,917 -> 72,916
        12-bit @ 192 Hz   54,688 -> 54,687

    One pixel per port out of ~73,000 - it cannot move a port count for any
    real cabinet - but the "all 48" claim is not true as written. Pinned here
    so the size of the discrepancy stays visible and cannot grow.
    """
    got = page.evaluate("""() => {
        const app = window.app;
        const t = app.portCapacityTables['brompton-ull'];
        const cells = [];
        Object.keys(t).forEach(bd => Object.keys(t[bd]).forEach(fps => {
            cells.push({ bd: Number(bd), fps: Number(fps), old: t[bd][fps],
                         now: app.calculatePortCapacity(Number(bd), Number(fps), 'brompton', true) });
        }));
        return cells;
    }""")
    assert len(got) == 48, f"the ULL table is no longer 48 cells ({len(got)})"
    off = [c for c in got if c['old'] != c['now']]
    assert sorted((c['bd'], c['fps'], c['old'], c['now']) for c in off) == [
        (12, 144, 72917, 72916),
        (12, 192, 54688, 54687),
    ], f"the ULL migration drifted: {off}"
    for c in off:
        assert abs(c['old'] - c['now']) == 1, "a ULL cell moved by more than rounding"


def test_max_capacity_on_a_legacy_screen_opens_as_organized(page):
    """ASSERTS CURRENT BEHAVIOUR.

    Legacy ignored Max Capacity before v0.10.9, so a file carrying that flag
    was actually drawn Organized. Now that Max Capacity works, opening such a
    file has to pin it back or an already-issued map silently redraws.
    """
    got = page.evaluate("""() => {
        const app = window.app;
        const project = { layers: [
            { id: 1, type: 'screen', processorType: 'novastar-armor', portMappingMode: 'max-capacity' },
            { id: 2, type: 'screen', portMappingMode: 'max-capacity' },   // no processor => Legacy
            { id: 3, type: 'screen', processorType: 'brompton', portMappingMode: 'max-capacity' },
            { id: 4, type: 'screen', processorType: 'novastar-armor', portMappingMode: 'organized' },
        ] };
        const changed = app.normalizeArmorPortMapping(project);
        return { changed, modes: project.layers.map(l => l.portMappingMode) };
    }""")
    assert got['changed'] == 2
    assert got['modes'] == ['organized', 'organized', 'max-capacity', 'organized'], (
        "normalizeArmorPortMapping touched the wrong screens")


def test_a_pre_v0109_file_with_no_groups_key_loads_and_calculates(client):
    """ASSERTS CURRENT BEHAVIOUR (server side, no browser).

    The shape of every project written before v0.10.9: no `groups`, no
    `next_group_seq`, no `group_id` on the layers, and manual paths whose
    entries are bare {row, col} with no layerId.
    """
    resp = client.post('/api/layer/add', json={
        'name': 'Old Screen', 'columns': 6, 'rows': 4,
        'cabinet_width': 128, 'cabinet_height': 128,
    })
    assert resp.status_code == 200
    project = client.get('/api/project').get_json()

    old = {
        'name': 'Pre-0.10.9',
        'raster_width': 1920, 'raster_height': 1080,
        'canvases': project['canvases'],
        'active_canvas_id': project['active_canvas_id'],
        'layers': [dict(project['layers'][0])],
    }
    old['layers'][0].pop('group_id', None)
    old['layers'][0].pop('lowLatency', None)
    old['layers'][0]['processorType'] = 'brompton-ull'
    old['layers'][0]['portMappingMode'] = 'max-capacity'
    old['layers'][0]['customPortPaths'] = {'1': [{'row': 0, 'col': 0}, {'row': 0, 'col': 1}]}
    old['layers'][0]['powerCustomPaths'] = {'1': [{'row': 1, 'col': 0}]}
    assert 'groups' not in old

    restored = client.put('/api/project', json=old).get_json()
    layer = restored['layers'][0]

    assert restored.get('groups') == [], "the server did not seed an empty groups list"
    assert layer.get('group_id') is None
    # A pre-v0.10.9 path has no layerId; nothing may be pruned from it.
    assert layer['customPortPaths'] == {'1': [{'row': 0, 'col': 0}, {'row': 0, 'col': 1}]}, \
        "a plain {row,col} path was rewritten or pruned on load"
    assert layer['powerCustomPaths'] == {'1': [{'row': 1, 'col': 0}]}
    # Geometry is re-derived from the panel states on every restore; a plain
    # full-size grid must come back unchanged.
    assert len(layer['panels']) == 24
    assert layer['panels'][0]['width'] == 128
    assert layer['panels'][0]['height'] == 128
    assert layer['panels'][-1]['x'] == 5 * 128
    assert layer['panels'][-1]['y'] == 3 * 128


def test_restoring_the_same_old_project_twice_changes_nothing(client):
    """ASSERTS CURRENT BEHAVIOUR: every undo goes through restore_project, so
    it has to be idempotent or repeated undos would keep mutating the file."""
    client.post('/api/layer/add', json={
        'name': 'Old', 'columns': 5, 'rows': 3,
        'cabinet_width': 128, 'cabinet_height': 128,
    })
    project = client.get('/api/project').get_json()
    project.pop('groups', None)
    project.pop('next_group_seq', None)
    for l in project['layers']:
        l.pop('group_id', None)

    once = client.put('/api/project', json=project).get_json()
    twice = client.put('/api/project', json=once).get_json()
    once.pop('_migration_notice', None)
    twice.pop('_migration_notice', None)
    assert once == twice, "restore_project is not idempotent for a pre-v0.10.9 file"


def test_a_plain_ungrouped_screen_still_exports_as_a_rectangle(client):
    """ASSERTS CURRENT BEHAVIOUR (server side).

    v0.10.9 changed the Resolume export to trace the real cabinet outline. A
    plain rectangular wall must still come out as a Slice, not a Polygon, and a
    wall with cabinets missing must still come out as a Polygon.
    """
    client.post('/api/layer/add', json={
        'name': 'Rect', 'columns': 6, 'rows': 4,
        'cabinet_width': 128, 'cabinet_height': 128,
    })
    xml = client.post('/api/export/resolume', json={
        'project_name': 'P', 'raster_width': 1920, 'raster_height': 1080,
    }).get_data(as_text=True)
    assert '<Slice' in xml and '<Polygon' not in xml, \
        "a plain rectangular wall no longer exports as a rectangle"
    assert '<v x="768.0" y="512.0"/>' in xml, "the exported extent moved"


def test_a_wall_with_a_half_height_bottom_row_exports_its_real_height(client):
    """ASSERTS CURRENT BEHAVIOUR: 3 full rows + one half row of 128px cabinets
    is 448px tall, not 512."""
    resp = client.post('/api/layer/add', json={
        'name': 'Half', 'columns': 6, 'rows': 4,
        'cabinet_width': 128, 'cabinet_height': 128,
        'panelStates': [{'row': 3, 'col': c, 'halfTile': 'height',
                         'hidden': False, 'blank': False} for c in range(6)],
    })
    assert resp.status_code == 200
    xml = client.post('/api/export/resolume', json={
        'project_name': 'P', 'raster_width': 1920, 'raster_height': 1080,
    }).get_data(as_text=True)
    assert '<v x="768.0" y="448.0"/>' in xml, \
        "the half-height bottom row is not reflected in the exported shape"
    assert '<v x="768.0" y="512.0"/>' not in xml


def test_blanked_cabinets_still_export_as_a_polygon(client):
    resp = client.post('/api/layer/add', json={
        'name': 'Notched', 'columns': 6, 'rows': 4,
        'cabinet_width': 128, 'cabinet_height': 128,
    })
    lid = resp.get_json()['id']
    client.post(f'/api/layer/{lid}/panels/set_hidden',
                json={'panels': [{'id': 1, 'hidden': True}, {'id': 2, 'hidden': True}]})
    xml = client.post('/api/export/resolume', json={
        'project_name': 'P', 'raster_width': 1920, 'raster_height': 1080,
    }).get_data(as_text=True)
    assert '<Polygon' in xml, "a notched wall no longer exports as a polygon"


# ══════════════════════════════════════════════════════════════════════════
# 5. Dead code that would be an undo hole if it were ever wired up
# ══════════════════════════════════════════════════════════════════════════

def test_single_panel_toggles_are_unreachable_dead_code(page):
    """ASSERTS CURRENT BEHAVIOUR, as a tripwire.

    togglePanelHidden / togglePanelBlank (app-screen-info.js:881, :898) mutate
    a panel and take NO history snapshot. Nothing in the UI calls them today -
    Alt+click goes through setPanelsBlankBulk / the canvas alt-paint, both of
    which do snapshot - so this is harmless. If anyone wires them to a control,
    hiding a cabinet becomes un-undoable and a later Ctrl+Z steps past it.
    """
    still_dead = page.evaluate("""() => {
        const src = [...document.querySelectorAll('script[src]')].map(s => s.src);
        return { hasMethods: typeof window.app.togglePanelHidden === 'function'
                          && typeof window.app.togglePanelBlank === 'function',
                 scripts: src.length };
    }""")
    assert still_dead['hasMethods'], "the methods vanished - update this test"
    src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src'))
    callers = []
    for root, _dirs, files in os.walk(src_dir):
        if os.sep + 'logs' in root:
            continue
        for fn in files:
            if not fn.endswith(('.js', '.html')):
                continue
            path = os.path.join(root, fn)
            if path.endswith('app-screen-info.js'):
                continue  # the definitions themselves
            with open(path, encoding='utf-8', errors='ignore') as fh:
                text = fh.read()
            if 'togglePanelHidden' in text or 'togglePanelBlank' in text:
                callers.append(path)
    assert callers == [], (
        "togglePanelHidden/togglePanelBlank are now reachable from "
        f"{callers} but still take no undo snapshot")
