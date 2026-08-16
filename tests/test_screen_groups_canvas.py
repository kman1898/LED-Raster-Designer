"""Screen groups (v0.11.0) - how a group DRAWS, SELECTS and MOVES.

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

    // Every circle the renderer draws, rounded. The circle-with-X test
    // pattern is the only arc in pixel-map view, so this counts patterns.
    arcs() {
        const r = window.canvasRenderer;
        const ctx = r.ctx;
        const original = ctx.arc;
        const out = [];
        ctx.arc = function (x, y, radius, a, b, c) {
            out.push({ x: Math.round(x), y: Math.round(y), r: Math.round(radius) });
            return original.call(ctx, x, y, radius, a, b, c);
        };
        try { r.render(); } finally { ctx.arc = original; }
        return out;
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


# ── One test pattern for the wall, not one per section ────────────────────
#
# The circle-and-X exists so you can look at the wall and see it is whole and
# square. A group IS one wall, so three sections must not show three circles.
#
# The mixed wall is 2560 x 1152 (JP5) stacked on 2560 x 128 (half panels):
#   union            2560 x 1280, centre (1280, 640)
#   radius           min(2560, 1280) * 0.40 = 512
# Ungrouped, each section gets its own:
#   JP5              centre (1280, 576),  r = min(2560, 1152) * 0.40 = 461
#   half panels      centre (1280, 1216), r = min(2560, 128)  * 0.40 = 51

_CIRCLE_ON = "jp5.show_circle_with_x = true; half.show_circle_with_x = true;"


def test_a_grouped_wall_draws_one_circle_across_the_whole_group(page):
    arcs = _grouped_wall(page, _CIRCLE_ON + " return gc.arcs();")
    assert len(arcs) == 1, f'expected one pattern for the wall, got {arcs}'
    assert arcs[0] == {'x': 1280, 'y': 640, 'r': 512}, arcs


def test_an_ungrouped_pair_still_draws_a_circle_each(page):
    """The regression guard: nothing changes for screens that are not a wall."""
    arcs = _ungrouped_wall(page, _CIRCLE_ON + " return gc.arcs();")
    assert len(arcs) == 2, f'expected one pattern per screen, got {arcs}'
    by_y = sorted(arcs, key=lambda a: a['y'])
    assert by_y[0] == {'x': 1280, 'y': 576, 'r': 461}, arcs
    assert by_y[1] == {'x': 1280, 'y': 1216, 'r': 51}, arcs


def test_the_grouped_x_spans_the_whole_wall_corner_to_corner(page):
    """The X is the other half of the pattern and must reach the wall's
    corners, not each section's."""
    segs = _grouped_wall(page, _CIRCLE_ON + """
        const r = window.canvasRenderer, ctx = r.ctx;
        const oM = ctx.moveTo, oL = ctx.lineTo, oA = ctx.arc;
        const out = []; let cur = null, seen = false;
        ctx.arc = function (...a) { seen = true; return oA.apply(ctx, a); };
        ctx.moveTo = function (x, y) { cur = {x, y}; return oM.call(ctx, x, y); };
        ctx.lineTo = function (x, y) {
            if (cur && seen) out.push([Math.round(cur.x), Math.round(cur.y),
                                       Math.round(x), Math.round(y)]);
            cur = {x, y}; return oL.call(ctx, x, y);
        };
        try { r.render(); } finally { ctx.moveTo = oM; ctx.lineTo = oL; ctx.arc = oA; }
        return out.filter(s => Math.abs(s[0] - s[2]) > 2000);
    """)
    assert sorted(segs) == sorted([[0, 0, 2560, 1280], [2560, 0, 0, 1280]]), segs


def test_a_hidden_member_does_not_stretch_the_pattern(page):
    """_groupDrawnMembers already skips hidden members, so the pattern covers
    what is actually on the wall - and a group down to one drawn member falls
    back to that member's own pattern."""
    arcs = _grouped_wall(page, _CIRCLE_ON + " half.visible = false; return gc.arcs();")
    assert len(arcs) == 1, arcs
    assert arcs[0] == {'x': 1280, 'y': 576, 'r': 461}, arcs


# ── The NAMES switch: Screens / Group / Both ──────────────────────────────
#
# project.groupNameDisplay chooses what a grouped wall is CALLED on the
# drawing. 'group' is the default and the behaviour above: one name, the
# group's. 'screens' hands every member its own name back (exactly the
# ungrouped path); 'both' draws the group's headline AND the member names.
# The combined figures stay consolidated on the group's single label in all
# three - the switch moves names, never numbers. Ungrouped screens are
# untouched by every mode.

def test_the_name_display_defaults_to_group_byte_for_byte(page):
    """An absent field and an explicit 'group' draw the same frame, call for
    call - the regression bar for every project saved before the switch."""
    result = _grouped_wall(page, """
            const r = window.canvasRenderer;
            const record = () => {
                const ctx = r.ctx;
                const original = ctx.fillText;
                const calls = [];
                ctx.fillText = function (t, x, y, w) {
                    calls.push([String(t), Math.round(x * 100) / 100,
                                Math.round(y * 100) / 100]);
                    return original.call(ctx, t, x, y, w);
                };
                try { r.render(); } finally { ctx.fillText = original; }
                return JSON.stringify(calls);
            };
            delete window.app.project.groupNameDisplay;
            const absent = record();
            window.app.project.groupNameDisplay = 'group';
            const explicit = record();
            return { absent: absent, explicit: explicit };
    """)
    assert result['absent'] == result['explicit']
    assert '"Main Wall"' in result['absent']
    assert '"JP5"' not in result['absent']


def test_screens_display_gives_each_member_its_own_name_back(page):
    """'screens': the members' names, no group name - and the combined info
    bar still consolidates, because the switch moves names, not figures."""
    texts = _grouped_wall(page, """
            window.app.project.groupNameDisplay = 'screens';
            return gc.drawn();
    """)
    assert texts.count('JP5') == 1, texts
    assert texts.count('Half Panels') == 1, texts
    assert 'Main Wall' not in texts
    info = [t for t in texts if 'Cabinets Total' in t]
    assert len(info) == 1, info
    assert '260 Cabinets Total' in info[0], info[0]
    assert '2 Screens' in info[0], info[0]


def test_both_display_draws_the_headline_and_every_member_name(page):
    texts = _grouped_wall(page, """
            window.app.project.groupNameDisplay = 'both';
            return gc.drawn();
    """)
    assert texts.count('Main Wall') == 1, texts
    assert texts.count('JP5') == 1, texts
    assert texts.count('Half Panels') == 1, texts
    info = [t for t in texts if 'Cabinets Total' in t]
    assert len(info) == 1 and '260 Cabinets Total' in info[0], info


def test_ungrouped_screens_ignore_the_name_display(page):
    """The switch is about groups; a lone screen reads the same in all
    three modes."""
    result = page.evaluate("""() => {
        const gc = window.__gc;
        %s
        return gc.withProject([jp5, half], [], 'pixel-map', () => {
            const out = {};
            ['group', 'screens', 'both'].forEach(mode => {
                window.app.project.groupNameDisplay = mode;
                out[mode] = gc.drawn();
            });
            return out;
        });
    }""" % MIXED_WALL_JS)
    for mode in ('group', 'screens', 'both'):
        assert result[mode].count('JP5') == 1, (mode, result[mode])
        assert result[mode].count('Half Panels') == 1, (mode, result[mode])
    assert result['group'] == result['screens'] == result['both']


# The dodge: 'both' puts the group's headline where the main member's own
# name already sits (a wall's main section centres about where the wall
# does). Resolved the way the label stack resolves its own collisions - the
# headline keeps its place, the member name steps below it with the stack's
# 5px gap. A member clear of the headline never moves.
#
# The pair is built so the collision is real: a 4x4 of 128px (centre y=256)
# under a 64px strip (union 0..576, centre 288). Name boxes are 46px tall
# (30px font + 4 + 2x6 padding), |288 - 256| = 32 < 46 -> they collide.

DODGE_PAIR_JS = """
    const a = gc.screen({
        id: 1, name: 'Main Section', columns: 4, rows: 4,
        cabinet_width: 128, cabinet_height: 128,
    });
    const b = gc.screen({
        id: 2, name: 'Under Strip', columns: 8, rows: 1,
        cabinet_width: 64, cabinet_height: 64,
        offset_y: 512,
    });
    a.group_id = 'g1';
    b.group_id = 'g1';
    const group = gc.group([a, b], { name: 'Dodge Wall' });
"""


def _dodge_hits(page, extra=""):
    """Name-label centres by text, in 'both' display."""
    return page.evaluate("""() => {
        const gc = window.__gc;
        %s
        return gc.withProject([a, b], [group], 'pixel-map', () => {
            window.app.project.groupNameDisplay = 'both';
            %s
            const r = window.canvasRenderer;
            const ctx = r.ctx;
            const original = ctx.fillText;
            const hits = {};
            ctx.fillText = function (t, x, y, w) {
                hits[String(t)] = { x: x, y: y };
                return original.call(ctx, t, x, y, w);
            };
            try { r.render(); } finally { ctx.fillText = original; }
            return hits;
        });
    }""" % (DODGE_PAIR_JS, extra))


def test_the_headline_dodge_steps_the_colliding_member_name_below(page):
    """Main Section's name would sit under the headline; it steps to just
    below the headline's box (bottom 311) + 5px gap + half its own height
    (23) = 339. The strip's name never moves from its own centre (544)."""
    hits = _dodge_hits(page)
    assert 'Dodge Wall' in hits and 'Main Section' in hits, hits
    assert hits['Dodge Wall']['y'] == pytest.approx(288, abs=1)
    assert hits['Main Section']['y'] == pytest.approx(339, abs=2), hits
    assert hits['Under Strip']['y'] == pytest.approx(544, abs=1), hits


def test_the_dodge_is_never_healed_into_the_stored_offsets(page):
    """The step is a draw-time dodge. The offset self-heal must keep writing
    the member's REAL offset (0), not the dodged position - or leaving
    'both' would strand every main section's name below centre."""
    offsets = _dodge_hits(page, """
            window.canvasRenderer.render();
    """)
    stored = page.evaluate("""() => {
        const gc = window.__gc;
        %s
        return gc.withProject([a, b], [group], 'pixel-map', () => {
            window.app.project.groupNameDisplay = 'both';
            const r = window.canvasRenderer;
            r.render();
            r.render();   // heal runs on every non-drag render
            return {
                x: a.screenNameOffsetXPixelMap || 0,
                y: a.screenNameOffsetYPixelMap || 0,
            };
        });
    }""" % DODGE_PAIR_JS)
    assert stored == {'x': 0, 'y': 0}, stored
    assert offsets['Main Section']['y'] == pytest.approx(339, abs=2)


def test_the_group_headline_drags_on_the_groups_own_fields(page):
    """In 'both' the headline is its own draggable label: dragging it writes
    the GROUP's per-view offsets, leaves every member's fields alone, and
    records one 'Move Group Name' undo entry."""
    result = page.evaluate("""() => {
        const gc = window.__gc;
        %s
        return gc.withProject([a, b], [group], 'pixel-map', () => {
            const app = window.app;
            const r = window.canvasRenderer;
            const savedSaveProject = app.saveProject;
            app.saveProject = () => {};
            try {
                app.project.groupNameDisplay = 'both';
                app.selectLayer(app.project.layers[0]);
                r._extendSelectionToGroups();
                app.saveState('Setup');
                r.render();
                const g = app.project.groups[0];
                const rect = app.project.layers[0]._groupNameHitRect;
                if (!rect) return { rect: null };
                const cx = (rect.x1 + rect.x2) / 2;
                const cy = (rect.y1 + rect.y2) / 2;
                r.handleMouseDown(gc.ev(cx, cy));
                const started = r.isDraggingGroupName;
                r.handleMouseMove(gc.ev(cx + 100, cy + 50));
                r.handleMouseUp(gc.ev(cx + 100, cy + 50));
                return {
                    rect: rect,
                    started: started,
                    group: { x: g.screenNameOffsetXPixelMap,
                             y: g.screenNameOffsetYPixelMap },
                    memberA: { x: a.screenNameOffsetXPixelMap || 0,
                               y: a.screenNameOffsetYPixelMap || 0 },
                    memberB: { x: b.screenNameOffsetXPixelMap || 0,
                               y: b.screenNameOffsetYPixelMap || 0 },
                    actions: app.history.map(h => h.action),
                    undoSnapshot: app.history[app.historyIndex - 1]
                        .project.groups[0].screenNameOffsetXPixelMap,
                };
            } finally {
                app.saveProject = savedSaveProject;
            }
        });
    }""" % DODGE_PAIR_JS)
    assert result['rect'], 'the headline cached no hit rect'
    assert result['started'], 'mousedown on the headline did not start its drag'
    assert result['group']['x'] == pytest.approx(100, abs=1)
    assert result['group']['y'] == pytest.approx(50, abs=1)
    assert result['memberA'] == {'x': 0, 'y': 0}
    assert result['memberB'] == {'x': 0, 'y': 0}
    assert result['actions'] == ['Setup', 'Move Group Name']
    # The entry one Undo lands on has the headline back where it started.
    assert not result.get('undoSnapshot')


def test_a_member_name_drags_only_itself_in_screens_display(page):
    """'screens' hands the members the exact pre-group drag: their own hit
    rect, their own per-view fields, nobody else's."""
    result = page.evaluate("""() => {
        const gc = window.__gc;
        %s
        return gc.withProject([a, b], [group], 'pixel-map', () => {
            const app = window.app;
            const r = window.canvasRenderer;
            app.project.groupNameDisplay = 'screens';
            app.selectLayer(app.project.layers[0]);
            r._extendSelectionToGroups();
            r.render();
            const rect = a._screenNameHitRect;
            if (!rect) return { rect: null };
            const cx = (rect.x1 + rect.x2) / 2;
            const cy = (rect.y1 + rect.y2) / 2;
            r.handleMouseDown(gc.ev(cx, cy));
            const started = r.isDraggingScreenName;
            r.handleMouseMove(gc.ev(cx - 80, cy + 30));
            r.handleMouseUp(gc.ev(cx - 80, cy + 30));
            const g = app.project.groups[0];
            return {
                rect: rect,
                started: started,
                memberA: { x: a.screenNameOffsetXPixelMap,
                           y: a.screenNameOffsetYPixelMap },
                memberB: { x: b.screenNameOffsetXPixelMap || 0,
                           y: b.screenNameOffsetYPixelMap || 0 },
                group: { x: g.screenNameOffsetXPixelMap || 0,
                         y: g.screenNameOffsetYPixelMap || 0 },
            };
        });
    }""" % DODGE_PAIR_JS)
    assert result['rect'], 'the member cached no hit rect of its own'
    assert result['started']
    assert result['memberA']['x'] == pytest.approx(-80, abs=1)
    assert result['memberA']['y'] == pytest.approx(30, abs=1)
    assert result['memberB'] == {'x': 0, 'y': 0}
    assert result['group'] == {'x': 0, 'y': 0}


def test_member_names_honor_their_own_per_view_sizes(page):
    """Cabinet ID view, 'screens': each member's name draws at that member's
    own screenNameSizeCabinet; in 'both' the headline stays on the FIRST
    member's size, the same rule every group label setting follows."""
    result = page.evaluate("""() => {
        const gc = window.__gc;
        %s
        a.screenNameSizeCabinet = 40;
        b.screenNameSizeCabinet = 18;
        return gc.withProject([a, b], [group], 'cabinet-id', () => {
            const r = window.canvasRenderer;
            const record = () => {
                const ctx = r.ctx;
                const original = ctx.fillText;
                const fonts = {};
                ctx.fillText = function (t, x, y, w) {
                    fonts[String(t)] = ctx.font;
                    return original.call(ctx, t, x, y, w);
                };
                try { r.render(); } finally { ctx.fillText = original; }
                return fonts;
            };
            window.app.project.groupNameDisplay = 'screens';
            const screens = record();
            window.app.project.groupNameDisplay = 'both';
            const both = record();
            return { screens: screens, both: both };
        });
    }""" % DODGE_PAIR_JS)
    assert '40px' in result['screens']['Main Section'], result['screens']
    assert '18px' in result['screens']['Under Strip'], result['screens']
    assert '40px' in result['both']['Dodge Wall'], result['both']
    assert '40px' in result['both']['Main Section'], result['both']
    assert '18px' in result['both']['Under Strip'], result['both']


def test_the_display_choice_rides_the_undo_snapshot(page):
    """Undo restores a history entry's project wholesale, so 'rides undo'
    is exactly: the snapshot before the change still holds the old mode,
    the snapshot of the change holds the new one."""
    result = _grouped_wall(page, """
            const app = window.app;
            app.saveState('Setup');
            app.project.groupNameDisplay = 'both';
            app.saveState('Change Name Display');
            return {
                actions: app.history.map(h => h.action),
                before: app.history[app.historyIndex - 1].project.groupNameDisplay || null,
                after: app.history[app.historyIndex].project.groupNameDisplay,
            };
    """)
    assert result['actions'] == ['Setup', 'Change Name Display']
    assert result['before'] is None
    assert result['after'] == 'both'


def test_export_mode_bakes_the_display_choice(page):
    """The PDF/PNG exports draw through this very renderer with exportMode
    on, so the choice must hold there - all names in 'both', and no hit
    rects cached into the export pass."""
    result = _grouped_wall(page, """
            const r = window.canvasRenderer;
            window.app.project.groupNameDisplay = 'both';
            const jp5L = window.app.project.layers[0];
            jp5L._screenNameHitRect = null;
            jp5L._groupNameHitRect = null;
            r.exportMode = true;
            let texts;
            try { texts = gc.drawn(); } finally { r.exportMode = false; }
            return {
                texts: texts,
                cachedName: !!jp5L._screenNameHitRect,
                cachedGroup: !!jp5L._groupNameHitRect,
            };
    """)
    texts = result['texts']
    assert texts.count('Main Wall') == 1, texts
    assert texts.count('JP5') == 1, texts
    assert texts.count('Half Panels') == 1, texts
    assert not result['cachedName']
    assert not result['cachedGroup']
