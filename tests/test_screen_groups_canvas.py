"""Screen groups (v0.10.9) - how a group DRAWS, SELECTS and MOVES.

Step 1 gave groups a data model, step 2 the combined totals. This is the canvas
half: a wall built from 1m JP5 cabinets AND 0.5m standard cabinets has to be two
layers (the per-layer grid is uniform), and up to now it also read and behaved
as two screens - two names, two info bars, two things to drag. Here it becomes
one: ONE label carrying the group's name and the group's combined figures,
positioned over the group's bounding box, and one drag that moves every member
together in one undo step.

Everything runs against SYNTHETIC projects: window.app.project is swapped for a
hand-built one inside a single page.evaluate and restored in a finally, so
nothing leaks into the session-shared page. The methods that would reach the
server or rebuild the sidebar DOM for layer ids that do not exist server-side
(updateLayers, renderLayers, loadLayerToInputs, saveClientSideProperties) are
stubbed for the duration and restored with the project - a late .then() from one
of those would otherwise land on the REAL project after the swap-back.

Labels are asserted by recording every string the renderer draws (ctx.fillText
is wrapped for the duration of one render), and positions by reading the layers'
own geometry back - never by inspecting style.

Run locally:
    python -m pytest tests/test_screen_groups_canvas.py -v --browser chromium
"""

import sys
import os

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
    return pg


HELPERS_JS = """
window.__gc = {
    // A screen the way create_layer builds one, with a full grid of panels.
    // Callers override only the fields the test is about.
    screen(opts) {
        const o = Object.assign({
            id: 1, name: 'S', type: 'screen', visible: true,
            canvas_id: 'c1',
            columns: 2, rows: 2,
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

    project(layers, groups) {
        return {
            layers: layers,
            groups: groups || [],
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

    group(layers, opts) {
        return Object.assign({
            id: 'g1', name: 'Main Wall', layer_ids: layers.map(l => l.id),
        }, opts || {});
    },

    // Swap in a synthetic project (plus a clean selection, history and view),
    // run fn, and put everything back no matter what fn does.
    withProject(layers, groups, viewMode, fn) {
        const app = window.app;
        const r = window.canvasRenderer;
        const saved = {
            project: app.project,
            currentLayer: app.currentLayer,
            selectedLayerIds: app.selectedLayerIds,
            history: app.history,
            historyIndex: app.historyIndex,
            updateLayers: app.updateLayers,
            renderLayers: app.renderLayers,
            loadLayerToInputs: app.loadLayerToInputs,
            loadTextLayerToInputs: app.loadTextLayerToInputs,
            saveClientSideProperties: app.saveClientSideProperties,
            activateCanvas: app._activateCanvasForLayer,
            viewMode: r.viewMode,
            zoom: r.zoom, panX: r.panX, panY: r.panY,
            magneticSnap: r.magneticSnap,
        };
        app.updateLayers = () => {};
        app.renderLayers = () => {};
        app.loadLayerToInputs = () => {};
        app.loadTextLayerToInputs = () => {};
        app.saveClientSideProperties = () => {};
        app._activateCanvasForLayer = () => {};
        app.project = this.project(layers, groups);
        app.currentLayer = null;
        app.selectedLayerIds = new Set();
        app.history = [];
        app.historyIndex = -1;
        r.viewMode = viewMode || 'pixel-map';
        r.zoom = 1; r.panX = 0; r.panY = 0;
        r.magneticSnap = false;   // deterministic drag deltas
        try {
            return fn();
        } finally {
            app.project = saved.project;
            app.currentLayer = saved.currentLayer;
            app.selectedLayerIds = saved.selectedLayerIds;
            app.history = saved.history;
            app.historyIndex = saved.historyIndex;
            app.updateLayers = saved.updateLayers;
            app.renderLayers = saved.renderLayers;
            app.loadLayerToInputs = saved.loadLayerToInputs;
            app.loadTextLayerToInputs = saved.loadTextLayerToInputs;
            app.saveClientSideProperties = saved.saveClientSideProperties;
            app._activateCanvasForLayer = saved.activateCanvas;
            r.viewMode = saved.viewMode;
            r.zoom = saved.zoom; r.panX = saved.panX; r.panY = saved.panY;
            r.magneticSnap = saved.magneticSnap;
            r.isDraggingLayer = false;
            r.isSelectingLayers = false;
            r.layerSelectionRect = null;
            r.render();
        }
    },

    // Every string the renderer draws during one frame, in draw order.
    drawn() {
        const r = window.canvasRenderer;
        const ctx = r.ctx;
        const original = ctx.fillText;
        const texts = [];
        ctx.fillText = function (t, x, y, w) {
            texts.push(String(t));
            return original.call(ctx, t, x, y, w);
        };
        try { r.render(); } finally { ctx.fillText = original; }
        return texts;
    },

    // A mouse event as the canvas handlers read one. World coords in, because
    // that is what the tests reason about.
    ev(worldX, worldY, opts) {
        const r = window.canvasRenderer;
        const rect = r.canvas.getBoundingClientRect();
        return Object.assign({
            button: 0, shiftKey: false, altKey: false,
            metaKey: false, ctrlKey: false,
            clientX: rect.left + worldX * r.zoom + r.panX,
            clientY: rect.top + worldY * r.zoom + r.panY,
            preventDefault() {},
            stopPropagation() {},
        }, opts || {});
    },

    // Shift+drag from one world point to another (the app's move-a-screen
    // gesture), driven through the real canvas handlers.
    shiftDrag(fromX, fromY, toX, toY) {
        const r = window.canvasRenderer;
        r.handleMouseDown(this.ev(fromX, fromY, { shiftKey: true }));
        r.handleMouseMove(this.ev(toX, toY, { shiftKey: true }));
        r.handleMouseUp(this.ev(toX, toY, { shiftKey: true }));
    },

    // Where every layer sits, keyed by id - the thing a drag must move.
    positions() {
        const out = {};
        window.app.project.layers.forEach(l => {
            out[l.id] = {
                x: l.offset_x, y: l.offset_y,
                p0x: l.panels[0].x, p0y: l.panels[0].y,
            };
        });
        return out;
    },
};
"""


# ── The mixed wall this feature exists for ────────────────────────────────
# 20x9 of 1m JP5 (128 px cabinets) with a 40x2 strip of 0.5m panels (64 px)
# hung underneath. 2560 x 1152 + 2560 x 128 = one 2560 x 1280 wall.

MIXED_WALL_JS = """
    const jp5 = gc.screen({
        id: 1, name: 'JP5', columns: 20, rows: 9,
        cabinet_width: 128, cabinet_height: 128,
        panel_weight: 20, panelWatts: 300,
        showLabelInfo: true,
    });
    const half = gc.screen({
        id: 2, name: 'Half Panels', columns: 40, rows: 2,
        cabinet_width: 64, cabinet_height: 64,
        panel_weight: 6, panelWatts: 90,
        offset_y: 1152,
        // deliberately DISAGREES with the first member: the group's label
        // follows the first member's toggles, so the info bar still draws.
        showLabelInfo: false,
    });
"""


def _grouped_wall(page, body):
    """Run `body` (JS, has `gc`, `jp5`, `half`, `group` in scope) grouped."""
    return page.evaluate("""() => {
        const gc = window.__gc;
        %s
        jp5.group_id = 'g1';
        half.group_id = 'g1';
        const group = gc.group([jp5, half]);
        return gc.withProject([jp5, half], [group], 'pixel-map', () => {
            %s
        });
    }""" % (MIXED_WALL_JS, body))


def _ungrouped_wall(page, body):
    """The same two screens, with no group at all."""
    return page.evaluate("""() => {
        const gc = window.__gc;
        %s
        return gc.withProject([jp5, half], [], 'pixel-map', () => {
            %s
        });
    }""" % (MIXED_WALL_JS, body))


# ── One label, not one per member ─────────────────────────────────────────

def test_a_grouped_pair_draws_one_name_label(page):
    """Two layers, one screen, one name on the drawing."""
    texts = _grouped_wall(page, "return gc.drawn();")
    assert texts.count('Main Wall') == 1, texts
    assert 'JP5' not in texts, 'a member drew its own name over the group label'
    assert 'Half Panels' not in texts


def test_an_ungrouped_pair_still_draws_two_labels(page):
    """The same two screens ungrouped are still two screens."""
    texts = _ungrouped_wall(page, "return gc.drawn();")
    assert texts.count('JP5') == 1, texts
    assert texts.count('Half Panels') == 1, texts
    assert 'Main Wall' not in texts


def test_the_group_label_shows_combined_figures_not_one_members(page):
    """Cabinets and weight are the WALL's, from the step-2 roll-up.

    Cabinets: 20 x 9 = 180  +  40 x 2 = 80              -> 260
    Weight:   180 x 20 kg = 3600  +  80 x 6 kg = 480    -> 4080.0 kg
    Size:     2560 x 1152 stacked on 2560 x 128         -> 2560 x 1280
    """
    texts = _grouped_wall(page, "return gc.drawn();")
    info = [t for t in texts if 'Cabinets Total' in t]
    assert len(info) == 1, f'expected one info bar, got {info}'
    line = info[0]
    assert '260 Cabinets Total' in line, line
    assert '4080.0 kg' in line, line
    assert '3600.0 kg' not in line, 'the group quoted one member\'s weight'
    assert '180 Cabinets' not in line
    assert 'Resolution: 2560 X 1280' in line, line
    # A group has no single Columns X Rows - that is why it is two layers.
    assert '2 Screens' in line, line
    assert 'Columns X' not in line, line


def test_the_group_label_sits_on_the_groups_bounding_box(page):
    """Positioned against the union of the members' bounds, not one member's.

    The name is centred on the whole wall (y = 640 of 0..1280), which is well
    below the first member's own centre (y = 576) and nowhere near the second
    member's (y = 1216).
    """
    result = page.evaluate("""() => {
        const gc = window.__gc;
        %s
        jp5.group_id = 'g1';
        half.group_id = 'g1';
        const group = gc.group([jp5, half]);
        return gc.withProject([jp5, half], [group], 'pixel-map', () => {
            const r = window.canvasRenderer;
            const ctx = r.ctx;
            const original = ctx.fillText;
            const hits = [];
            ctx.fillText = function (t, x, y, w) {
                if (String(t) === 'Main Wall') hits.push({ x: x, y: y });
                return original.call(ctx, t, x, y, w);
            };
            try { r.render(); } finally { ctx.fillText = original; }
            return hits;
        });
    }""" % MIXED_WALL_JS)
    assert len(result) == 1, result
    # The name sits at the top of the centred label stack, so allow the stack's
    # own height - what matters is that it tracks the UNION's centre (640) and
    # not either member's (576 / 1216).
    assert result[0]['x'] == pytest.approx(1280, abs=1)
    assert 600 < result[0]['y'] < 680, result


# ── Mismatched voltages ───────────────────────────────────────────────────

POWER_PAIR_JS = """
    const a = gc.screen({
        id: 1, name: 'A', columns: 2, rows: 2,
        cabinet_width: 128, cabinet_height: 128,
        panelWatts: 300, powerVoltage: 208,
        showPowerCircuitInfo: true, showLabelNamePower: false,
    });
    const b = gc.screen({
        id: 2, name: 'B', columns: 2, rows: 2,
        cabinet_width: 64, cabinet_height: 64,
        panelWatts: 90, powerVoltage: %s,
        offset_y: 256,
        showPowerCircuitInfo: true, showLabelNamePower: false,
    });
"""


def _power_pair(page, voltage_b):
    return page.evaluate("""() => {
        const gc = window.__gc;
        %s
        a.group_id = 'g1';
        b.group_id = 'g1';
        const group = gc.group([a, b]);
        return gc.withProject([a, b], [group], 'power', () => gc.drawn());
    }""" % (POWER_PAIR_JS % voltage_b))


def test_a_matched_voltage_group_shows_the_combined_amps(page):
    """4 x 300 W + 4 x 90 W = 1560 W at 208 V -> 7.50 A single phase."""
    texts = _power_pair(page, 208)
    line = [t for t in texts if 'Circuits |' in t]
    assert len(line) == 1, f'expected one power info line, got {line}'
    assert '7.50A 1φ' in line[0], line[0]
    assert '4.34A 3φ' in line[0], line[0]      # 1560 / (208 x 1.73)


def test_a_mixed_voltage_group_never_shows_one_amps_figure(page):
    """200 A at 110 V and 200 A at 208 V are not the same load.

    The roll-up hands back null amps for a mixed-voltage group, and the label
    has to say so rather than print a blended number nobody can act on.
    """
    texts = _power_pair(page, 110)
    line = [t for t in texts if 'Circuits |' in t]
    assert len(line) == 1, f'expected one power info line, got {line}'
    assert 'Mixed voltage' in line[0], line[0]
    assert '208' in line[0] and '110' in line[0], line[0]
    joined = ' | '.join(texts)
    assert '1φ' not in joined, f'a single-phase amps figure was drawn: {joined}'
    assert '3φ' not in joined, f'a three-phase amps figure was drawn: {joined}'


# ── Move as one ───────────────────────────────────────────────────────────

def test_dragging_one_member_moves_the_whole_group(page):
    """Grab the JP5 half, the 0.5m strip comes with it - offsets preserved."""
    result = _grouped_wall(page, """
            const gc2 = window.__gc;
            const before = gc2.positions();
            // Click a JP5 cabinet to select (which now selects the group),
            // then shift+drag from that same point by +300, +200.
            window.app.selectLayer(window.app.project.layers[0]);
            window.canvasRenderer._extendSelectionToGroups();
            gc2.shiftDrag(100, 100, 400, 300);
            return { before: before, after: gc2.positions(),
                     selected: [...window.app.selectedLayerIds] };
    """)
    before, after = result['before'], result['after']
    assert sorted(result['selected']) == [1, 2]
    for lid in ('1', '2'):
        assert after[lid]['x'] - before[lid]['x'] == 300, (lid, before, after)
        assert after[lid]['y'] - before[lid]['y'] == 200, (lid, before, after)
        # panels travel with their layer (they live in processor coords)
        assert after[lid]['p0x'] - before[lid]['p0x'] == 300
        assert after[lid]['p0y'] - before[lid]['p0y'] == 200
    # Relative offset between the two members is exactly what it was.
    assert (after['2']['y'] - after['1']['y']) == (before['2']['y'] - before['1']['y'])


def test_a_group_drag_is_one_undo_step_that_restores_both(page):
    """One snapshot for the whole group move, holding both members' positions.

    Undo steps BACK one history entry and restores that project wholesale, so
    "one undo restores both" is exactly: the drag added one entry, and the
    entry before it carries both members at their pre-drag positions.
    """
    result = _grouped_wall(page, """
            const gc2 = window.__gc;
            const app = window.app;
            app.saveState('Setup');
            const before = gc2.positions();
            app.selectLayer(app.project.layers[1]);   // grab the SECOND member
            window.canvasRenderer._extendSelectionToGroups();
            gc2.shiftDrag(100, 1200, 250, 1200);
            return {
                before: before,
                after: gc2.positions(),
                actions: app.history.map(h => h.action),
                previous: app.history[app.historyIndex - 1].project.layers
                    .map(l => ({ id: l.id, x: l.offset_x, y: l.offset_y })),
                latest: app.history[app.historyIndex].project.layers
                    .map(l => ({ id: l.id, x: l.offset_x, y: l.offset_y })),
            };
    """)
    assert result['actions'] == ['Setup', 'Move Layers'], result['actions']
    before, after = result['before'], result['after']
    for lid in ('1', '2'):
        assert after[lid]['x'] - before[lid]['x'] == 150, (lid, before, after)
    # The entry one Undo lands on has BOTH members back where they started.
    restored = {row['id']: row for row in result['previous']}
    assert restored[1]['x'] == before['1']['x'] and restored[1]['y'] == before['1']['y']
    assert restored[2]['x'] == before['2']['x'] and restored[2]['y'] == before['2']['y']
    # ...and the snapshot the drag wrote has both members moved.
    moved = {row['id']: row for row in result['latest']}
    assert moved[1]['x'] == after['1']['x']
    assert moved[2]['x'] == after['2']['x']


def test_clicking_one_member_selects_the_group(page):
    """The selection affordance the drag rides on."""
    selected = _grouped_wall(page, """
            const r = window.canvasRenderer;
            r._selectLayerFromCanvas(window.app.project.layers[1]);
            return {
                ids: [...window.app.selectedLayerIds].sort(),
                current: window.app.currentLayer.id,
            };
    """)
    assert selected['ids'] == [1, 2]
    assert selected['current'] == 2, 'the clicked member is still the primary'


# ── Ungrouped layers are completely unaffected ────────────────────────────

def test_an_ungrouped_neighbour_is_untouched_by_a_group_drag(page):
    """Pin a lone screen's label and position across a group drag beside it."""
    result = page.evaluate("""() => {
        const gc = window.__gc;
        %s
        jp5.group_id = 'g1';
        half.group_id = 'g1';
        const solo = gc.screen({
            id: 3, name: 'Solo', columns: 4, rows: 3,
            cabinet_width: 128, cabinet_height: 128,
            offset_x: 3000, panel_weight: 20, showLabelInfo: true,
        });
        const group = gc.group([jp5, half]);
        return gc.withProject([jp5, half, solo], [group], 'pixel-map', () => {
            const gc2 = window.__gc;
            const textsBefore = gc2.drawn();
            const before = gc2.positions();
            window.app.selectLayer(window.app.project.layers[0]);
            window.canvasRenderer._extendSelectionToGroups();
            gc2.shiftDrag(100, 100, 500, 100);
            const after = gc2.positions();
            const selectedDuring = [...window.app.selectedLayerIds].sort();
            const textsAfter = gc2.drawn();
            // ...and the lone screen still drags on its own.
            window.app.selectLayer(window.app.project.layers[2]);
            window.canvasRenderer._extendSelectionToGroups();
            gc2.shiftDrag(3050, 100, 3050, 400);
            return {
                textsBefore: textsBefore, textsAfter: textsAfter,
                before: before, after: after, soloAfter: gc2.positions(),
                selectedDuring: selectedDuring,
                selectedSolo: [...window.app.selectedLayerIds].sort(),
            };
        });
    }""" % MIXED_WALL_JS)

    # The group drag never touched the lone screen, and never selected it.
    assert result['selectedDuring'] == [1, 2]
    assert result['after']['3'] == result['before']['3']
    # Its label is byte-for-byte what it was: name and its OWN info bar.
    solo_before = [t for t in result['textsBefore'] if 'Columns X' in t]
    solo_after = [t for t in result['textsAfter'] if 'Columns X' in t]
    assert len(solo_before) == 1 and solo_before == solo_after, (solo_before, solo_after)
    assert '4 Columns X 3 Rows' in solo_before[0]
    assert '12 Cabinets Total' in solo_before[0]
    assert result['textsBefore'].count('Solo') == 1
    assert result['textsAfter'].count('Solo') == 1

    # Selecting and dragging it moves it, and only it.
    assert result['selectedSolo'] == [3]
    assert result['soloAfter']['3']['y'] - result['after']['3']['y'] == 300
    assert result['soloAfter']['1'] == result['after']['1']
    assert result['soloAfter']['2'] == result['after']['2']


def test_a_group_of_one_keeps_its_own_label(page):
    """Nothing to consolidate: a one-member group draws that member's label."""
    texts = page.evaluate("""() => {
        const gc = window.__gc;
        const only = gc.screen({
            id: 1, name: 'Lonely', columns: 4, rows: 3, showLabelInfo: true,
            group_id: 'g1',
        });
        const group = gc.group([only]);
        return gc.withProject([only], [group], 'pixel-map', () => gc.drawn());
    }""")
    assert texts.count('Lonely') == 1, texts
    assert 'Main Wall' not in texts
    info = [t for t in texts if 'Cabinets Total' in t]
    assert len(info) == 1 and '4 Columns X 3 Rows' in info[0], info
