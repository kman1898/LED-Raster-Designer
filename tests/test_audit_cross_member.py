"""ADVERSARIAL AUDIT of v0.11.0 cross-member wiring and selection.

Written to BREAK the feature, not to document it. Everything asserted here is
either exact model state (the two scoped Sets, the stored path entries) or
recorded ctx calls mapped through the live transform. Nothing reads
``el.style.*`` - theme.css uses ``!important`` throughout, so an inline style
that never renders reads back as a false pass.

SEVEN TESTS IN HERE FAILED ON PURPOSE. They are the findings, pinned as
executable repros. A, B and C have since been FIXED; the tests that always
asserted the correct behaviour pass unchanged, and the two that pinned the
WRONG behaviour by asserting it are marked FLIPPED in their own docstrings.
The findings, most severe first:

  A. HIDDEN MEMBER LEAK - FIXED. getPathScopeLayers (app-power.js) deliberately
     keeps hidden members so already-drawn paths survive a hide. The SELECTION
     side reused the same scope, so a marquee, an arrow handoff and Apply
     Pattern all reached a screen that is not drawn and cannot be clicked:
       test_marquee_does_not_select_cabinets_of_a_hidden_member
       test_arrow_key_does_not_hand_off_onto_a_hidden_member
       test_selection_overlay_does_not_highlight_a_hidden_member
       test_hidden_member_selection_wires_cabinets_nobody_can_see
     Selection now goes through getSelectionScopeLayers - the path scope less
     the members the user cannot see, owner always kept - so the marquee, the
     arrow handoff and the panels an Apply Pattern commits all stop where
     click-to-add already stopped. RESOLVING a path is untouched: a cable drawn
     onto a member before it was hidden survives, and comes back on unhide.
     The DRAWING half is fixed in canvas.js: a crossing cable stops at the last
     cabinet that is actually drawn (_crossMemberDrawPanels) and the drag-select
     highlight skips a peer this view does not draw
     (_renderScopedSelectionOverlay).

  B. SELECTION SURVIVES A SCREEN SWITCH - FIXED. selectLayer
     (app-screen-info.js) cleared none of the three Sets, so a live marquee
     re-targeted whichever member was current when Apply Pattern was pressed,
     with an identical highlight either side of the switch:
       test_selection_survives_a_switch_to_the_peer_and_fills_the_peers_port
       test_pixelmap_selection_survives_a_layer_switch
     All three Sets are now cleared when the current layer's id actually
     changes (not on the re-selection that follows undo/redo, load and layer
     updates, where the "new" layer is the same screen rebuilt). Cleared rather
     than re-anchored: the keys name cabinets on screens the new layer may not
     even reach, and "the same cabinets, now feeding a different port" is not
     what picking a different screen in the list means to anyone.

  C. ROTATED MEMBER - FIXED. getPositionLattice (canvas.js) ranked in
     UNROTATED screen space, so a pattern applied over a rotated member snaked
     in an order that existed nowhere on site. The marquee, the arrow handoff
     and the highlight all got the same rotation right, so this was the lattice
     alone. It now ranks each cabinet's slot origin through that member's own
     draw frame (_layerDrawFrame / _drawnPanelRect), which is the same mapping
     the other three use:
       test_pattern_order_on_a_rotated_member_matches_where_it_draws

Run ALONE (conftest hardcodes port 15789):
    python -m pytest tests/test_audit_cross_member.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project exactly as this module found it.
    This module looks purely client-side, but app.undo()/redo() PUT the
    whole client project - synthetic grouped layers included - to the
    shared server (see conftest.server_project_guard)."""


HELPERS_JS = r"""
window.__ax = {
    screen(opts) {
        const o = Object.assign({
            id: 1, name: 'S', type: 'screen', visible: true,
            canvas_id: 'c1', show_canvas_id: null,
            columns: 2, rows: 2,
            cabinet_width: 128, cabinet_height: 128,
            panel_width_mm: 500, panel_height_mm: 500,
            offset_x: 0, offset_y: 0,
            panel_weight: 20, weight_unit: 'kg',
            panelWatts: 200, powerVoltage: 208, powerAmperage: 20,
            processorType: 'brompton', bitDepth: 8, frameRate: 60,
            lowLatency: false,
            color1: { r: 64, g: 70, b: 128 }, color2: { r: 149, g: 156, b: 184 },
            show_numbers: false, number_size: 30,
            show_panel_borders: true, panel_border_width: 2,
            border_color: '#ffffff', rotation: 0,
            flowPattern: 'custom', portMappingMode: 'organized',
            powerFlowPattern: 'custom', powerOrganized: true, powerMaximize: false,
        }, opts || {});
        if (o.showOffsetX === undefined) o.showOffsetX = o.offset_x;
        if (o.showOffsetY === undefined) o.showOffsetY = o.offset_y;
        o.customPortPaths = o.customPortPaths || {};
        o.customPortIndex = o.customPortIndex || 1;
        o.powerCustomPaths = o.powerCustomPaths || {};
        o.powerCustomIndex = o.powerCustomIndex || 1;
        const panels = [];
        for (let r = 0; r < o.rows; r++) {
            for (let c = 0; c < o.columns; c++) {
                panels.push({
                    id: o.id * 1000 + r * o.columns + c + 1,
                    number: r * o.columns + c + 1,
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

    withProject(layers, groups, viewMode, fn) {
        const app = window.app;
        const r = window.canvasRenderer;
        if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
        const saved = {
            project: app.project,
            currentLayer: app.currentLayer,
            selectedLayerIds: app.selectedLayerIds,
            history: app.history,
            historyIndex: app.historyIndex,
            customSelection: app.customSelection,
            powerCustomSelection: app.powerCustomSelection,
            pixelMapSelection: app.pixelMapSelection,
            updateLayers: app.updateLayers,
            renderLayers: app.renderLayers,
            loadLayerToInputs: app.loadLayerToInputs,
            loadTextLayerToInputs: app.loadTextLayerToInputs,
            saveClientSideProperties: app.saveClientSideProperties,
            updatePortLabelEditor: app.updatePortLabelEditor,
            updatePixelMapBulkActionUI: app.updatePixelMapBulkActionUI,
            activateCanvas: app._activateCanvasForLayer,
            toast: app._toast,
            viewMode: r.viewMode,
            zoom: r.zoom, panX: r.panX, panY: r.panY,
        };
        app.updateLayers = () => {};
        app.renderLayers = () => {};
        app.loadLayerToInputs = () => {};
        app.loadTextLayerToInputs = () => {};
        app.saveClientSideProperties = () => {};
        app.updatePortLabelEditor = () => {};
        app.updatePixelMapBulkActionUI = () => {};
        app._activateCanvasForLayer = () => {};
        this.toasts = [];
        app._toast = (msg, isError) => { window.__ax.toasts.push(String(msg)); };
        app.project = this.project(layers, groups);
        app.currentLayer = layers[0];
        app.selectedLayerIds = new Set([layers[0].id]);
        app.customSelection = new Set();
        app.powerCustomSelection = new Set();
        app.pixelMapSelection = new Set();
        app.history = [];
        app.historyIndex = -1;
        r.viewMode = viewMode || 'data-flow';
        r.zoom = 1; r.panX = 0; r.panY = 0;
        try {
            return fn();
        } finally {
            app.project = saved.project;
            app.currentLayer = saved.currentLayer;
            app.selectedLayerIds = saved.selectedLayerIds;
            app.customSelection = saved.customSelection;
            app.powerCustomSelection = saved.powerCustomSelection;
            app.pixelMapSelection = saved.pixelMapSelection;
            app.history = saved.history;
            app.historyIndex = saved.historyIndex;
            app.updateLayers = saved.updateLayers;
            app.renderLayers = saved.renderLayers;
            app.loadLayerToInputs = saved.loadLayerToInputs;
            app.loadTextLayerToInputs = saved.loadTextLayerToInputs;
            app.saveClientSideProperties = saved.saveClientSideProperties;
            app.updatePortLabelEditor = saved.updatePortLabelEditor;
            app.updatePixelMapBulkActionUI = saved.updatePixelMapBulkActionUI;
            app._activateCanvasForLayer = saved.activateCanvas;
            app._toast = saved.toast;
            r.viewMode = saved.viewMode;
            r.zoom = saved.zoom; r.panX = saved.panX; r.panY = saved.panY;
            r.render();
        }
    },

    rect(x1, y1, x2, y2) { return { x1: x1, y1: y1, x2: x2, y2: y2 }; },

    // A stored path as comparable `${layerId}:${row},${col}` strings, with the
    // owner filled in for the plain {row,col} form. This is the address of ONE
    // cabinet on the wall - the thing every assertion below is really about.
    pathKeys(owner, portNum) {
        return (owner.customPortPaths[portNum] || []).map(e =>
            `${(e.layerId === undefined || e.layerId === null) ? owner.id : e.layerId}:${e.row},${e.col}`);
    },

    powerPathKeys(owner, circuitNum) {
        return (owner.powerCustomPaths[circuitNum] || []).map(e =>
            `${(e.layerId === undefined || e.layerId === null) ? owner.id : e.layerId}:${e.row},${e.col}`);
    },

    // Raw entry shapes, so "did it write a layerId at all" is answerable.
    rawPath(owner, portNum) {
        return (owner.customPortPaths[portNum] || []).map(e => ({
            row: e.row, col: e.col,
            hasLayerId: Object.prototype.hasOwnProperty.call(e, 'layerId'),
            layerId: e.layerId === undefined ? null : e.layerId,
        }));
    },

    key(e) { return { code: e, preventDefault() {}, stopPropagation() {} }; },

    // Every fillRect one overlay method issues during a real frame, in WORLD
    // coords. Scoped to the method so the port badge (same rgba) cannot be
    // mistaken for a selection highlight.
    overlayFills(method) {
        const r = window.canvasRenderer;
        const ctx = r.ctx;
        const origFill = ctx.fillRect;
        const origMethod = r[method];
        const out = [];
        let inside = false;
        r[method] = function () {
            inside = true;
            try { return origMethod.apply(r, arguments); } finally { inside = false; }
        };
        ctx.fillRect = function (x, y, w, h) {
            if (inside) {
                const m = ctx.getTransform();
                out.push({
                    x: Math.round(m.a * x + m.c * y + m.e),
                    y: Math.round(m.b * x + m.d * y + m.f),
                    w: Math.round(Math.abs(m.a * w + m.c * h)),
                    h: Math.round(Math.abs(m.b * w + m.d * h)),
                });
            }
            return origFill.call(ctx, x, y, w, h);
        };
        try { r.render(); } finally { ctx.fillRect = origFill; delete r[method]; }
        return out.map(f => `${f.x},${f.y}`).sort();
    },
};
"""


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


# ── Walls ────────────────────────────────────────────────────────────────
#
# MIXED   A id1 3x2 @128 at x0..384  y0..256   | B id2 3x4 @64 at x384..576 y0..256
#         lattice cols 0 1 2 | 3 4 5, lattice rows A{0,2} B{0,1,2,3}
#
# ABOVE   B id2 sits directly ABOVE A id1, same columns.
# STACKED A 3x2 @128 at x0, B 2x4 @128 at x384 (different row counts)
# HALFLAP A 2x2 @128 at (0,0), B 2x2 @128 at (256,64) - rows half-overlap
# ROT     A 2x2 @128 at (0,0), B 2x2 @128 at (256,0) rotated 90

MIXED = """
    const a = ax.screen({ id: 1, name: 'JP5', columns: 3, rows: 2,
        cabinet_width: 128, cabinet_height: 128 });
    const b = ax.screen({ id: 2, name: 'Half Panels', columns: 3, rows: 4,
        cabinet_width: 64, cabinet_height: 64, offset_x: 384 });
"""

ABOVE = """
    const a = ax.screen({ id: 1, name: 'Lower', columns: 3, rows: 2 });
    const b = ax.screen({ id: 2, name: 'Upper', columns: 3, rows: 2,
        offset_y: -256 });
"""

STACKED = """
    const a = ax.screen({ id: 1, name: 'Left', columns: 3, rows: 2 });
    const b = ax.screen({ id: 2, name: 'Right Tall', columns: 2, rows: 4,
        offset_x: 384 });
"""

HALFLAP = """
    const a = ax.screen({ id: 1, name: 'Left', columns: 2, rows: 2 });
    const b = ax.screen({ id: 2, name: 'Right', columns: 2, rows: 2,
        offset_x: 256, offset_y: 64 });
"""

ROT = """
    const a = ax.screen({ id: 1, name: 'Flat', columns: 2, rows: 2 });
    const b = ax.screen({ id: 2, name: 'Turned', columns: 2, rows: 2,
        offset_x: 256, rotation: 90 });
"""


def _run(page, wall, body, view='data-flow', grouped=True, extra=''):
    return page.evaluate("""() => {
        const ax = window.__ax;
        %s
        %s
        if (%s) { a.group_id = 'g1'; b.group_id = 'g1'; }
        const groups = (%s) ? [ax.group([a, b])] : [];
        return ax.withProject([a, b], groups, '%s', () => {
            %s
        });
    }""" % (wall, extra, str(grouped).lower(), str(grouped).lower(), view, body))


# ═════════════════════════════════════════════════════════════════════════
# 1. WRONG-CABINET / key-format hunting
# ═════════════════════════════════════════════════════════════════════════

def test_no_scoped_key_ever_reaches_pixelmap_selection(page):
    """A scoped key in pixelMapSelection would parse as parseInt("2:0") === 2."""
    result = _run(page, MIXED, """
        const app = window.app;
        app.selectPanelsInRect(app.currentLayer, ax.rect(0, 0, 576, 256));
        const custom = [...app.customSelection];
        app.selectPixelMapPanelsInRect(app.currentLayer, ax.rect(0, 0, 576, 256));
        return {
            customScoped: custom.every(k => k.indexOf(':') > 0),
            pixel: [...app.pixelMapSelection],
        };
    """)
    assert result['customScoped'] is True, result
    assert all(':' not in k for k in result['pixel']), result


def test_pixelmap_marquee_never_crosses_members(page):
    """The primary single-screen guard: pixel-map stays on currentLayer."""
    result = _run(page, MIXED, """
        const app = window.app;
        app.selectPixelMapPanelsInRect(app.currentLayer, ax.rect(0, 0, 576, 256));
        return {
            size: app.pixelMapSelection.size,
            panels: app.getPixelMapSelectedPanels().length,
        };
    """)
    assert result['size'] == 6, result   # A only, 3x2
    assert result['panels'] == 6, result


def test_selection_overlay_fills_the_peers_real_cabinets(page):
    """The highlight has to land on B's grid, not on A's cell of the same r,c.

    Recorded ctx.fillRect calls mapped through the live transform. If any
    consumer parsed the scoped key with the old ``split(',')`` the fills would
    land on A's 128px lattice instead of B's 64px one.
    """
    fills = _run(page, MIXED, """
        const app = window.app;
        // Peer-only selection: B's entire top row.
        app.customSelection.add('2:0,0');
        app.customSelection.add('2:0,1');
        app.customSelection.add('2:0,2');
        return ax.overlayFills('renderCustomSelectionOverlay');
    """)
    assert fills == sorted(['384,0', '448,0', '512,0']), fills


def test_selection_overlay_ignores_a_key_naming_an_unreachable_layer(page):
    """A key for a layer that is not a reachable peer must draw nothing."""
    fills = _run(page, MIXED, """
        const app = window.app;
        app.customSelection.add('999:0,0');   // no such layer
        app.customSelection.add('1:0,0');     // owner, legitimate
        return ax.overlayFills('renderCustomSelectionOverlay');
    """)
    assert fills == ['0,0'], fills


def test_ungrouped_marquee_cannot_reach_the_neighbouring_screen(page):
    """Regression guard: no group, no cross-member anything."""
    result = _run(page, MIXED, """
        const app = window.app;
        app.selectPanelsInRect(app.currentLayer, ax.rect(0, 0, 576, 256));
        return { keys: [...app.customSelection].sort() };
    """, grouped=False)
    assert all(k.startswith('1:') for k in result['keys']), result
    assert len(result['keys']) == 6, result


# ═════════════════════════════════════════════════════════════════════════
# 2. PATTERN ORDERING - exact orders on walls where index != position
# ═════════════════════════════════════════════════════════════════════════

ALL_PATTERNS = ['tl-h', 'tr-h', 'bl-h', 'br-h', 'tl-v', 'tr-v', 'bl-v', 'br-v']

# Hand-derived from the PHYSICAL wall, not from the code.
#   A(r,c) is 128px, top-left (128c, 128r)
#   B(r,c) is  64px, top-left (384 + 64c, 64r)
MIXED_EXPECTED = {
    'tl-h': ['1:0,0', '1:0,1', '1:0,2', '2:0,0', '2:0,1', '2:0,2',
             '2:1,2', '2:1,1', '2:1,0',
             '1:1,0', '1:1,1', '1:1,2', '2:2,0', '2:2,1', '2:2,2',
             '2:3,2', '2:3,1', '2:3,0'],
    'tr-h': ['2:0,2', '2:0,1', '2:0,0', '1:0,2', '1:0,1', '1:0,0',
             '2:1,0', '2:1,1', '2:1,2',
             '2:2,2', '2:2,1', '2:2,0', '1:1,2', '1:1,1', '1:1,0',
             '2:3,0', '2:3,1', '2:3,2'],
    'bl-h': ['2:3,0', '2:3,1', '2:3,2',
             '2:2,2', '2:2,1', '2:2,0', '1:1,2', '1:1,1', '1:1,0',
             '2:1,0', '2:1,1', '2:1,2',
             '2:0,2', '2:0,1', '2:0,0', '1:0,2', '1:0,1', '1:0,0'],
    'br-h': ['2:3,2', '2:3,1', '2:3,0',
             '1:1,0', '1:1,1', '1:1,2', '2:2,0', '2:2,1', '2:2,2',
             '2:1,2', '2:1,1', '2:1,0',
             '1:0,0', '1:0,1', '1:0,2', '2:0,0', '2:0,1', '2:0,2'],
    'tl-v': ['1:0,0', '1:1,0',
             '1:1,1', '1:0,1',
             '1:0,2', '1:1,2',
             '2:3,0', '2:2,0', '2:1,0', '2:0,0',
             '2:0,1', '2:1,1', '2:2,1', '2:3,1',
             '2:3,2', '2:2,2', '2:1,2', '2:0,2'],
    'tr-v': ['2:0,2', '2:1,2', '2:2,2', '2:3,2',
             '2:3,1', '2:2,1', '2:1,1', '2:0,1',
             '2:0,0', '2:1,0', '2:2,0', '2:3,0',
             '1:1,2', '1:0,2',
             '1:0,1', '1:1,1',
             '1:1,0', '1:0,0'],
    'bl-v': ['1:1,0', '1:0,0',
             '1:0,1', '1:1,1',
             '1:1,2', '1:0,2',
             '2:0,0', '2:1,0', '2:2,0', '2:3,0',
             '2:3,1', '2:2,1', '2:1,1', '2:0,1',
             '2:0,2', '2:1,2', '2:2,2', '2:3,2'],
    'br-v': ['2:3,2', '2:2,2', '2:1,2', '2:0,2',
             '2:0,1', '2:1,1', '2:2,1', '2:3,1',
             '2:3,0', '2:2,0', '2:1,0', '2:0,0',
             '1:0,2', '1:1,2',
             '1:1,1', '1:0,1',
             '1:0,0', '1:1,0'],
}


@pytest.mark.parametrize('pattern', ALL_PATTERNS)
def test_mixed_size_wall_pattern_is_in_physical_order(page, pattern):
    order = _run(page, MIXED, """
        const app = window.app;
        app.selectPanelsInRect(app.currentLayer, ax.rect(0, 0, 576, 256));
        app.applyPatternToSelection('%s');
        return ax.pathKeys(a, 1);
    """ % pattern)
    assert order == MIXED_EXPECTED[pattern], (pattern, order)


def test_member_above_the_owner_is_wired_first(page):
    """B sits ABOVE A. A top-left serpentine has to start on B, not on A."""
    order = _run(page, ABOVE, """
        const app = window.app;
        app.selectPanelsInRect(app.currentLayer, ax.rect(0, -256, 384, 256));
        app.applyPatternToSelection('tl-h');
        return ax.pathKeys(a, 1);
    """)
    assert order == [
        '2:0,0', '2:0,1', '2:0,2',
        '2:1,2', '2:1,1', '2:1,0',
        '1:0,0', '1:0,1', '1:0,2',
        '1:1,2', '1:1,1', '1:1,0',
    ], order


def test_side_by_side_members_with_different_row_counts(page):
    order = _run(page, STACKED, """
        const app = window.app;
        app.selectPanelsInRect(app.currentLayer, ax.rect(0, 0, 640, 512));
        app.applyPatternToSelection('tl-h');
        return ax.pathKeys(a, 1);
    """)
    assert order == [
        '1:0,0', '1:0,1', '1:0,2', '2:0,0', '2:0,1',
        '2:1,1', '2:1,0', '1:1,2', '1:1,1', '1:1,0',
        '2:2,0', '2:2,1',
        '2:3,1', '2:3,0',
    ], order


def test_half_overlapping_rows_split_into_their_own_lattice_bands(page):
    """B is offset half a cabinet down. Records the ACTUAL behaviour.

    Every member gets its own lattice row band, so the serpentine reverses
    after only A's two cabinets and jumps to the far right of the wall.
    """
    order = _run(page, HALFLAP, """
        const app = window.app;
        app.selectPanelsInRect(app.currentLayer, ax.rect(0, 0, 512, 320));
        app.applyPatternToSelection('tl-h');
        return ax.pathKeys(a, 1);
    """)
    assert order == [
        '1:0,0', '1:0,1',
        '2:0,1', '2:0,0',
        '1:1,0', '1:1,1',
        '2:1,1', '2:1,0',
    ], order


def test_pattern_order_on_a_rotated_member_matches_where_it_draws(page):
    """B is rotated 90. Its DRAWN top-left cabinet is R1C0, not R0C0.

    The marquee gets rotation right (asserted alongside), so this is purely
    about whether the pattern lattice ranks by where the cabinets DRAW.
    """
    result = _run(page, ROT, """
        const app = window.app;
        const r = window.canvasRenderer;
        // Where each of B's cabinets actually draws, top-left corner.
        const drawn = {};
        b.panels.forEach(p => {
            const s = r._crossMemberPanelShim(b, p);
            drawn[`${p.row},${p.col}`] = [Math.round(s.x), Math.round(s.y)];
        });
        // Marquee over the DRAWN top-left quadrant of B only.
        app.selectPanelsInRect(app.currentLayer, ax.rect(260, 4, 380, 124));
        const quadrant = [...app.customSelection].sort();
        app.customSelection.clear();
        app.selectPanelsInRect(app.currentLayer, ax.rect(0, 0, 512, 256));
        app.applyPatternToSelection('tl-h');
        return { drawn, quadrant, order: ax.pathKeys(a, 1) };
    """)
    # The marquee is rotation-correct: the drawn top-left quadrant is R1C0.
    assert result['quadrant'] == ['2:1,0'], result
    assert result['drawn']['1,0'] == [256, 0], result
    assert result['drawn']['0,0'] == [384, 0], result
    # ... so a top-left serpentine must reach B's DRAWN top-left first.
    assert result['order'] == [
        '1:0,0', '1:0,1', '2:1,0', '2:0,0',
        '2:0,1', '2:1,1', '1:1,1', '1:1,0',
    ], result['order']


def test_ungrouped_pattern_order_is_the_plain_grid_order(page):
    """Regression guard: an ungrouped screen orders exactly as it always did."""
    order = _run(page, MIXED, """
        const app = window.app;
        app.selectPanelsInRect(app.currentLayer, ax.rect(0, 0, 576, 256));
        app.applyPatternToSelection('tl-h');
        return ax.pathKeys(a, 1);
    """, grouped=False)
    assert order == ['1:0,0', '1:0,1', '1:0,2', '1:1,2', '1:1,1', '1:1,0'], order


def test_ungrouped_path_entries_carry_no_layerid(page):
    """A pre-group project's file shape must be byte-for-byte unchanged."""
    raw = _run(page, MIXED, """
        const app = window.app;
        app.selectPanelsInRect(app.currentLayer, ax.rect(0, 0, 576, 256));
        app.applyPatternToSelection('tl-h');
        return ax.rawPath(a, 1);
    """, grouped=False)
    assert all(e['hasLayerId'] is False for e in raw), raw


def test_power_pattern_uses_the_same_lattice_as_data(page):
    order = _run(page, MIXED, """
        const app = window.app;
        app.selectPowerPanelsInRect(app.currentLayer, ax.rect(0, 0, 576, 256));
        app.applyPowerPatternToSelection('tl-h');
        return ax.powerPathKeys(a, 1);
    """, view='power')
    assert order == MIXED_EXPECTED['tl-h'], order


# ═════════════════════════════════════════════════════════════════════════
# 3. CONFLICT DETECTION - one cabinet, two ports
# ═════════════════════════════════════════════════════════════════════════

def test_peer_cabinet_cannot_be_claimed_by_two_ports_of_the_owner(page):
    result = _run(page, MIXED, """
        const app = window.app;
        app.addPanelToCustomPath(b.panels[0], b);      // port 1 <- B R0C0
        a.customPortIndex = 2;
        app.addPanelToCustomPath(b.panels[0], b);      // port 2 <- same cabinet
        return { p1: ax.pathKeys(a, 1), p2: ax.pathKeys(a, 2),
                 toasts: window.__ax.toasts };
    """)
    assert result['p1'] == ['2:0,0'], result
    assert result['p2'] == [], result
    assert len(result['toasts']) == 1, result
    assert 'Half Panels' in result['toasts'][0], result['toasts']
    assert 'port 1' in result['toasts'][0], result['toasts']


def test_conflict_across_members_names_the_owning_screen(page):
    """A's port 1 owns B's R0C0. Drawing B's own port 1 must be refused and
    must say the claim lives on JP5, not just "port 1"."""
    result = _run(page, MIXED, """
        const app = window.app;
        app.addPanelToCustomPath(b.panels[0], b);   // A port 1 <- B R0C0
        app.currentLayer = b;                        // now draw FROM B
        app.selectedLayerIds = new Set([b.id]);
        app.addPanelToCustomPath(b.panels[0], b);   // B port 1 <- its own R0C0
        return { aPort1: ax.pathKeys(a, 1),
                 bPort1: (b.customPortPaths[1] || []).length,
                 toasts: window.__ax.toasts };
    """)
    assert result['aPort1'] == ['2:0,0'], result
    assert result['bPort1'] == 0, result
    assert 'port 1 on JP5' in result['toasts'][-1], result['toasts']


def test_pattern_apply_is_rejected_wholesale_on_a_cross_member_conflict(page):
    result = _run(page, MIXED, """
        const app = window.app;
        app.addPanelToCustomPath(b.panels[0], b);   // port 1 <- B R0C0
        a.customPortIndex = 2;
        app.selectPanelsInRect(app.currentLayer, ax.rect(0, 0, 576, 256));
        app.applyPatternToSelection('tl-h');
        return { p1: ax.pathKeys(a, 1), p2: ax.pathKeys(a, 2),
                 toasts: window.__ax.toasts };
    """)
    assert result['p1'] == ['2:0,0'], result
    assert result['p2'] == [], result          # nothing partially applied
    assert 'Cannot apply' in result['toasts'][-1], result['toasts']
    assert 'Half Panels' in result['toasts'][-1], result['toasts']


def test_pattern_apply_sees_a_claim_made_by_a_peers_own_port(page):
    """The peer B owns a port containing one of ITS cabinets; A's pattern
    apply over the whole wall must be refused."""
    result = _run(page, MIXED, """
        const app = window.app;
        b.customPortPaths = { 3: [{ row: 2, col: 1 }] };
        app.selectPanelsInRect(app.currentLayer, ax.rect(0, 0, 576, 256));
        app.applyPatternToSelection('tl-h');
        return { p1: ax.pathKeys(a, 1), toasts: window.__ax.toasts };
    """)
    assert result['p1'] == [], result
    assert 'port 3 on Half Panels' in result['toasts'][-1], result['toasts']


def test_same_cabinet_cannot_be_added_twice_to_one_port(page):
    result = _run(page, MIXED, """
        const app = window.app;
        app.addPanelToCustomPath(b.panels[0], b);
        app.addPanelToCustomPath(b.panels[0], b);
        return ax.pathKeys(a, 1);
    """)
    assert result == ['2:0,0'], result


def test_owners_r0c0_and_peers_r0c0_are_two_different_cabinets(page):
    """The collision the whole scoped-key change exists for."""
    result = _run(page, MIXED, """
        const app = window.app;
        app.addPanelToCustomPath(a.panels[0], a);   // A R0C0
        app.addPanelToCustomPath(b.panels[0], b);   // B R0C0
        return { keys: ax.pathKeys(a, 1), raw: ax.rawPath(a, 1) };
    """)
    assert result['keys'] == ['1:0,0', '2:0,0'], result
    assert result['raw'][0]['hasLayerId'] is False, result
    assert result['raw'][1]['hasLayerId'] is True, result


def test_power_circuit_and_data_port_do_not_conflict_with_each_other(page):
    result = _run(page, MIXED, """
        const app = window.app;
        app.addPanelToCustomPath(b.panels[0], b);
        app.addPanelToCustomPowerPath(b.panels[0], b);
        return { port: ax.pathKeys(a, 1), circuit: ax.powerPathKeys(a, 1),
                 toasts: window.__ax.toasts };
    """)
    assert result['port'] == ['2:0,0'], result
    assert result['circuit'] == ['2:0,0'], result
    assert result['toasts'] == [], result


def test_ungrouped_conflict_message_names_no_screen(page):
    result = _run(page, MIXED, """
        const app = window.app;
        app.addPanelToCustomPath(a.panels[0], a);
        a.customPortIndex = 2;
        app.addPanelToCustomPath(a.panels[0], a);
        return window.__ax.toasts;
    """, grouped=False)
    assert len(result) == 1, result
    assert ' on ' not in result[0].split('already wired to')[1], result


# ═════════════════════════════════════════════════════════════════════════
# 4. ARROW-KEY HANDOFF
# ═════════════════════════════════════════════════════════════════════════

def test_arrow_right_hands_off_to_the_physically_adjacent_peer_cabinet(page):
    """A's cabinets are 128px, B's are 64px. Stepping right off A R0C2 must
    land inside B, not on some index-arithmetic guess."""
    result = _run(page, MIXED, """
        const app = window.app;
        app.addPanelToCustomPath(a.panels[2], a);       // A R0C2
        app.handleCustomArrowKey(ax.key('ArrowRight'));
        return ax.pathKeys(a, 1);
    """)
    # A R0C2 spans y 0..128; its vertical centre y=64 is exactly B's row
    # boundary, and the inclusive hit-test resolves to the upper cabinet.
    assert result == ['1:0,2', '2:0,0'], result


def test_arrow_left_hands_back_from_the_peer_onto_the_owner(page):
    result = _run(page, MIXED, """
        const app = window.app;
        app.addPanelToCustomPath(b.panels[0], b);       // B R0C0
        app.handleCustomArrowKey(ax.key('ArrowLeft'));
        return ax.pathKeys(a, 1);
    """)
    # B R0C0 spans y 0..64; centre y=32 lands in A's R0C2 (y 0..128).
    assert result == ['2:0,0', '1:0,2'], result


def test_arrow_up_crosses_onto_the_member_above(page):
    result = _run(page, ABOVE, """
        const app = window.app;
        app.addPanelToCustomPath(a.panels[1], a);       // A R0C1
        app.handleCustomArrowKey(ax.key('ArrowUp'));
        return ax.pathKeys(a, 1);
    """)
    assert result == ['1:0,1', '2:1,1'], result


def test_arrow_at_the_outer_edge_of_the_wall_is_swallowed(page):
    result = _run(page, MIXED, """
        const app = window.app;
        app.addPanelToCustomPath(b.panels[2], b);       // B R0C2, wall's right edge
        const handled = app.handleCustomArrowKey(ax.key('ArrowRight'));
        return { handled, path: ax.pathKeys(a, 1) };
    """)
    assert result['handled'] is True, result
    assert result['path'] == ['2:0,2'], result


def test_arrow_will_not_cross_a_gap_between_members(page):
    """Members separated by 8px of air. The probe only reaches 1px past the
    edge, so the handoff finds nothing."""
    result = _run(page, """
    const a = ax.screen({ id: 1, name: 'Left', columns: 2, rows: 2 });
    const b = ax.screen({ id: 2, name: 'Right', columns: 2, rows: 2,
        offset_x: 264 });
    """, """
        const app = window.app;
        app.addPanelToCustomPath(a.panels[1], a);       // A R0C1, right edge of A
        const handled = app.handleCustomArrowKey(ax.key('ArrowRight'));
        return { handled, path: ax.pathKeys(a, 1) };
    """)
    assert result['handled'] is True, result
    assert result['path'] == ['1:0,1'], result   # nothing added


def test_arrow_stops_at_a_hidden_cabinet_in_the_peer(page):
    result = _run(page, MIXED, """
        const app = window.app;
        b.panels.find(p => p.row === 0 && p.col === 0).hidden = true;
        app.addPanelToCustomPath(a.panels[2], a);
        app.handleCustomArrowKey(ax.key('ArrowRight'));
        return ax.pathKeys(a, 1);
    """)
    assert result == ['1:0,2'], result


def test_arrow_into_a_rotated_member_lands_where_it_draws(page):
    """A is flat, B is rotated 90 and sits to its right. Stepping right off
    A R0C1 must land on the cabinet DRAWN immediately to its right, which
    under the 90 rotation is B R1C0."""
    result = _run(page, ROT, """
        const app = window.app;
        app.addPanelToCustomPath(a.panels[1], a);       // A R0C1
        app.handleCustomArrowKey(ax.key('ArrowRight'));
        return ax.pathKeys(a, 1);
    """)
    assert result == ['1:0,1', '2:1,0'], result


def test_arrow_on_an_ungrouped_screen_never_leaves_it(page):
    result = _run(page, MIXED, """
        const app = window.app;
        app.addPanelToCustomPath(a.panels[2], a);
        const handled = app.handleCustomArrowKey(ax.key('ArrowRight'));
        return { handled, path: ax.pathKeys(a, 1) };
    """, grouped=False)
    assert result['handled'] is True, result
    assert result['path'] == ['1:0,2'], result


def test_power_arrow_handoff_uses_the_power_path(page):
    result = _run(page, MIXED, """
        const app = window.app;
        app.addPanelToCustomPowerPath(a.panels[2], a);
        app.handleCustomArrowKey(ax.key('ArrowRight'));
        return { circuit: ax.powerPathKeys(a, 1), port: ax.pathKeys(a, 1) };
    """, view='power')
    assert result['circuit'] == ['1:0,2', '2:0,0'], result
    assert result['port'] == [], result


# ═════════════════════════════════════════════════════════════════════════
# 5. HIDDEN MEMBERS - selection reaching a screen nobody can see
# ═════════════════════════════════════════════════════════════════════════

def test_marquee_does_not_select_cabinets_of_a_hidden_member(page):
    """A hidden member is not drawn (canvas.js _groupDrawnMembers filters
    visible !== false) and cannot be clicked (getPanelAt skips it), so a
    marquee must not silently pick it up either."""
    result = _run(page, MIXED, """
        const app = window.app;
        b.visible = false;
        app.selectPanelsInRect(app.currentLayer, ax.rect(0, 0, 576, 256));
        return { keys: [...app.customSelection].sort() };
    """)
    assert all(k.startswith('1:') for k in result['keys']), result


def test_click_to_add_cannot_reach_a_hidden_member(page):
    """The reference behaviour the marquee is being measured against."""
    result = _run(page, MIXED, """
        const r = window.canvasRenderer;
        b.visible = false;
        const hit = r.getPanelAt(400, 32);   // inside B's R0C0
        return hit ? hit.layerId : null;
    """)
    assert result is None, result


def test_arrow_key_does_not_hand_off_onto_a_hidden_member(page):
    result = _run(page, MIXED, """
        const app = window.app;
        b.visible = false;
        app.addPanelToCustomPath(a.panels[2], a);
        app.handleCustomArrowKey(ax.key('ArrowRight'));
        return ax.pathKeys(a, 1);
    """)
    assert result == ['1:0,2'], result


def test_selection_overlay_does_not_highlight_a_hidden_member(page):
    fills = _run(page, MIXED, """
        const app = window.app;
        b.visible = false;
        app.customSelection.add('2:0,0');
        return ax.overlayFills('renderCustomSelectionOverlay');
    """)
    assert fills == [], fills


def test_hiding_a_member_preserves_wiring_already_drawn_onto_it(page):
    """The other half of the rule: hiding must not DELETE anything."""
    result = _run(page, MIXED, """
        const app = window.app;
        app.addPanelToCustomPath(b.panels[0], b);
        b.visible = false;
        const dropped = app.sanitizeCrossLayerPaths(a);
        b.visible = true;
        return { dropped, path: ax.pathKeys(a, 1) };
    """)
    assert result['dropped'] == 0, result
    assert result['path'] == ['2:0,0'], result


# ═════════════════════════════════════════════════════════════════════════
# 6. PERSISTENCE - undo / redo / prune
# ═════════════════════════════════════════════════════════════════════════

def test_undo_redo_round_trips_a_cross_member_path(page):
    result = _run(page, MIXED, """
        const app = window.app;
        app.saveState('base');
        app.selectPanelsInRect(app.currentLayer, ax.rect(0, 0, 576, 256));
        app.applyPatternToSelection('tl-h');
        app._flushPendingSaveState && app._flushPendingSaveState();
        const after = ax.pathKeys(app.project.layers[0], 1);
        app.undo();
        const undone = ax.pathKeys(app.project.layers[0], 1);
        app.redo();
        const redone = ax.pathKeys(app.project.layers[0], 1);
        return { after, undone, redone };
    """)
    assert result['after'] == MIXED_EXPECTED['tl-h'], result
    assert result['undone'] == [], result
    assert result['redone'] == MIXED_EXPECTED['tl-h'], result


def test_ungrouping_prunes_the_cross_member_entries(page):
    result = _run(page, MIXED, """
        const app = window.app;
        app.addPanelToCustomPath(a.panels[0], a);
        app.addPanelToCustomPath(b.panels[0], b);
        a.group_id = null; b.group_id = null;
        app.project.groups = [];
        const dropped = app.sanitizeCrossLayerPaths(a);
        return { dropped, path: ax.pathKeys(a, 1) };
    """)
    assert result['dropped'] == 1, result
    assert result['path'] == ['1:0,0'], result


def test_pattern_apply_persists_the_owner_even_when_it_is_unselected(page):
    """A marquee that ended on the peer can leave currentLayer out of the
    layer selection; the PUT still has to carry the owner."""
    result = page.evaluate("""() => {
        const ax = window.__ax;
        %s
        a.group_id = 'g1'; b.group_id = 'g1';
        return ax.withProject([a, b], [ax.group([a, b])], 'data-flow', () => {
            const app = window.app;
            const sent = [];
            app.updateLayers = (layers) => { (layers || []).forEach(l => sent.push(l.id)); };
            app.selectedLayerIds = new Set([b.id]);   // owner NOT selected
            app.selectPanelsInRect(a, ax.rect(386, 0, 576, 256));
            app.applyPatternToSelection('tl-h');
            return { sent: sent.sort(), path: ax.pathKeys(a, 1).length };
        });
    }""" % MIXED)
    assert 1 in result['sent'], result
    assert result['path'] == 12, result


def test_clear_all_wipes_cross_member_entries_and_the_selection(page):
    result = _run(page, MIXED, """
        const app = window.app;
        app.selectPanelsInRect(app.currentLayer, ax.rect(0, 0, 576, 256));
        app.applyPatternToSelection('tl-h');
        a.customPortPaths = {};
        app.customSelection.clear();
        return { paths: Object.keys(a.customPortPaths).length,
                 sel: app.customSelection.size };
    """)
    assert result == {'paths': 0, 'sel': 0}, result


# ═════════════════════════════════════════════════════════════════════════
# 7. Further adversarial probes
# ═════════════════════════════════════════════════════════════════════════

def test_rotated_peer_highlight_draws_where_the_cabinet_draws(page):
    """Positive control for the rotated-lattice failure above: the OVERLAY
    gets rotation right, so only the pattern lattice is wrong."""
    fills = _run(page, ROT, """
        const app = window.app;
        app.customSelection.add('2:1,0');   // draws at the top-LEFT of B
        return ax.overlayFills('renderCustomSelectionOverlay');
    """)
    assert fills == ['256,0'], fills


def test_hidden_member_selection_wires_cabinets_nobody_can_see(page):
    """Consequence of the hidden-member marquee leak: a pattern apply commits
    12 cabinets on an invisible screen into the visible screen's port 1."""
    result = _run(page, MIXED, """
        const app = window.app;
        b.visible = false;
        app.selectPanelsInRect(app.currentLayer, ax.rect(0, 0, 576, 256));
        app.applyPatternToSelection('tl-h');
        const keys = ax.pathKeys(a, 1);
        return { total: keys.length, onHidden: keys.filter(k => k.startsWith('2:')).length };
    """)
    assert result['onHidden'] == 0, result


def test_marquee_honours_a_peers_own_show_look_offset(page):
    """Members can carry different Show Look offsets. The marquee has to
    hit-test the peer where the SHOW view draws it, exactly like getPanelAt."""
    result = _run(page, MIXED, """
        const app = window.app;
        const r = window.canvasRenderer;
        b.showOffsetX = b.offset_x + 200;        // B draws 200px further right
        app.selectPanelsInRect(app.currentLayer, ax.rect(586, 0, 776, 256));
        const atShow = [...app.customSelection].filter(k => k.startsWith('2:')).length;
        app.customSelection.clear();
        app.selectPanelsInRect(app.currentLayer, ax.rect(386, 0, 576, 256));
        const atProcessor = [...app.customSelection].filter(k => k.startsWith('2:')).length;
        const hit = r.getPanelAt(600, 32);
        return { atShow, atProcessor, hitLayer: hit ? hit.layerId : null };
    """)
    assert result['hitLayer'] == 2, result
    assert result['atShow'] == 12, result
    assert result['atProcessor'] == 0, result


def test_pattern_lattice_ranks_by_show_position_not_processor_position(page):
    """B is dragged 512px right in the Show view, past nothing; A stays put.
    A top-left serpentine must still read A first, then B, at the SHOW gap."""
    order = _run(page, ABOVE, """
        const app = window.app;
        // Move the UPPER member below the lower one in the Show view.
        b.showOffsetY = 256;
        app.selectPanelsInRect(app.currentLayer, ax.rect(0, 0, 384, 512));
        app.applyPatternToSelection('tl-h');
        return ax.pathKeys(a, 1);
    """)
    assert order == [
        '1:0,0', '1:0,1', '1:0,2',
        '1:1,2', '1:1,1', '1:1,0',
        '2:0,0', '2:0,1', '2:0,2',
        '2:1,2', '2:1,1', '2:1,0',
    ], order


def test_member_on_another_canvas_is_out_of_reach(page):
    result = _run(page, MIXED, """
        const app = window.app;
        b.canvas_id = 'c2'; b.show_canvas_id = 'c2';
        app.selectPanelsInRect(app.currentLayer, ax.rect(0, 0, 576, 256));
        const marquee = [...app.customSelection].filter(k => k.startsWith('2:')).length;
        app.addPanelToCustomPath(b.panels[0], b);
        return { marquee, path: ax.pathKeys(a, 1) };
    """)
    assert result['marquee'] == 0, result
    assert result['path'] == [], result


def test_three_member_group_conflict_is_found_on_the_third_member(page):
    result = page.evaluate("""() => {
        const ax = window.__ax;
        const a = ax.screen({ id: 1, name: 'A', columns: 2, rows: 2 });
        const b = ax.screen({ id: 2, name: 'B', columns: 2, rows: 2, offset_x: 256 });
        const c = ax.screen({ id: 3, name: 'C', columns: 2, rows: 2, offset_x: 512 });
        [a, b, c].forEach(l => { l.group_id = 'g1'; });
        const g = { id: 'g1', name: 'Wall', layer_ids: [1, 2, 3] };
        return ax.withProject([a, b, c], [g], 'data-flow', () => {
            const app = window.app;
            // C's own port 4 already owns B's R1C1.
            c.customPortPaths = { 4: [{ row: 1, col: 1, layerId: 2 }] };
            app.addPanelToCustomPath(b.panels[3], b);   // A tries to take it
            return { path: ax.pathKeys(a, 1), toasts: window.__ax.toasts };
        });
    }""")
    assert result['path'] == [], result
    assert 'port 4 on C' in result['toasts'][-1], result['toasts']
    assert 'R2C2 on B' in result['toasts'][-1], result['toasts']


def test_exactly_coincident_members_lose_no_cabinet_from_the_pattern(page):
    """Two members stacked on the same origin land in the same lattice cells;
    the bucket has to emit both, not drop one."""
    result = _run(page, """
    const a = ax.screen({ id: 1, name: 'Front', columns: 2, rows: 2 });
    const b = ax.screen({ id: 2, name: 'Behind', columns: 2, rows: 2 });
    """, """
        const app = window.app;
        app.selectPanelsInRect(app.currentLayer, ax.rect(0, 0, 256, 256));
        const sel = app.customSelection.size;
        app.applyPatternToSelection('tl-h');
        const keys = ax.pathKeys(a, 1);
        return { sel, count: keys.length, unique: [...new Set(keys)].length };
    """)
    assert result['sel'] == 8, result
    assert result['count'] == 8, result
    assert result['unique'] == 8, result


def test_undo_restores_a_single_cross_member_click(page):
    result = _run(page, MIXED, """
        const app = window.app;
        app.saveState('base');
        app.addPanelToCustomPath(b.panels[0], b);
        app._flushPendingSaveState && app._flushPendingSaveState();
        app.undo();
        return ax.pathKeys(app.project.layers[0], 1);
    """)
    assert result == [], result


def test_a_marquee_on_the_shared_seam_takes_both_members_edge_cabinets(page):
    result = _run(page, MIXED, """
        const app = window.app;
        app.selectPanelsInRect(app.currentLayer, ax.rect(383, 0, 385, 256));
        return [...app.customSelection].sort();
    """)
    assert result == ['1:0,2', '1:1,2', '2:0,0', '2:1,0', '2:2,0', '2:3,0'], result


def test_selection_survives_a_switch_to_the_peer_and_fills_the_peers_port(page):
    """selectLayer clears nothing. A marquee made while A was current is still
    live after switching to B, and Apply Pattern then fills B's port 1."""
    result = _run(page, MIXED, """
        const app = window.app;
        app.selectPanelsInRect(app.currentLayer, ax.rect(0, 0, 576, 256));
        const before = app.customSelection.size;
        app.selectLayer(b);
        const after = app.customSelection.size;
        app.applyPatternToSelection('tl-h');
        return { before, after,
                 aPort: ax.pathKeys(a, 1).length, bPort: ax.pathKeys(b, 1).length };
    """)
    assert result['before'] == 18, result
    assert result['after'] == 0, result
    assert result['bPort'] == 0, result


def test_pixelmap_selection_survives_a_layer_switch(page):
    """pixelMapSelection is unscoped by design. If it outlives a switch to a
    peer, its keys silently re-address the peer's grid."""
    result = _run(page, MIXED, """
        const app = window.app;
        app.selectPixelMapPanelsInRect(app.currentLayer, ax.rect(0, 0, 384, 256));
        const onA = app.getPixelMapSelectedPanels().map(p => p.id).sort();
        app.selectLayer(b);
        const onB = app.getPixelMapSelectedPanels().map(p => p.id).sort();
        return { onA, onB, size: app.pixelMapSelection.size };
    """, view='pixel-map')
    assert result['onB'] == [], result


def test_double_claim_via_the_layer_switch_route_is_still_refused(page):
    """FLIPPED on the toast only. selectLayer now clears the selection Sets, so
    the second apply has nothing to apply and never reaches conflict detection
    - the double claim is stopped one step earlier than it used to be, and
    stopped silently, because the user asked for nothing.

    A's 18 cabinets stay exactly where they were either way, which is the part
    that matters: switching screens must not move a port."""
    result = _run(page, MIXED, """
        const app = window.app;
        app.selectPanelsInRect(app.currentLayer, ax.rect(0, 0, 576, 256));
        app.applyPatternToSelection('tl-h');          // A port 1 <- whole wall
        app.selectPanelsInRect(a, ax.rect(0, 0, 576, 256));
        app.selectLayer(b);
        app.applyPatternToSelection('tl-h');          // now as B
        return { aPort: ax.pathKeys(a, 1).length, bPort: ax.pathKeys(b, 1).length,
                 sel: app.customSelection.size, toasts: window.__ax.toasts };
    """)
    assert result['aPort'] == 18, result
    assert result['bPort'] == 0, result
    assert result['sel'] == 0, result
    assert result['toasts'] == [], result


def test_the_highlight_clears_when_the_owner_changes(page):
    """FLIPPED. The overlay used to paint the same 18 cabinets either side of
    the switch, so nothing on screen said the port target had moved - the only
    signal was the sidebar's port field. Now selectLayer clears the selection,
    and the highlight going out IS the cue."""
    result = _run(page, MIXED, """
        const app = window.app;
        app.selectPanelsInRect(app.currentLayer, ax.rect(0, 0, 576, 256));
        const before = ax.overlayFills('renderCustomSelectionOverlay');
        app.selectLayer(b);
        const after = ax.overlayFills('renderCustomSelectionOverlay');
        return { before, after };
    """)
    assert len(result['before']) == 18, result
    assert result['after'] == [], result


def test_a_path_onto_a_hidden_member_still_resolves_for_drawing(page):
    """Documents the downstream half of the hidden-member leak: the resolver
    does not filter on visibility either, so the cable is drawn across a
    screen that is not on the canvas."""
    result = _run(page, MIXED, """
        const app = window.app;
        app.addPanelToCustomPath(a.panels[0], a);
        app.addPanelToCustomPath(b.panels[0], b);
        b.visible = false;
        const resolved = app.getResolvedPathPanels(a, a.customPortPaths[1]);
        return { count: resolved.length,
                 layers: resolved.map(r => r.layer.id) };
    """)
    assert result == {'count': 2, 'layers': [1, 2]}, result


# ═════════════════════════════════════════════════════════════════════════
# 9. AUTOMATIC routing across the members (v0.12)
# ═════════════════════════════════════════════════════════════════════════
#
# Up to here every crossing run in this file was HAND DRAWN. A group of matching
# panels now routes automatically across its members as well - one port walk and
# one circuit walk over the whole wall - which breaks the assumption the arrow
# renderers were written on ("automatic assignment walks one uniform grid and
# never leaves its layer"). These are the two halves that assumption was holding
# up: where the line is DRAWN, and which cabinet gets TINTED.

# Two 6 x 6 sections of 128 px cabinets, stacked. Brompton 8-bit 60 Hz is
# 525,000 px a port and a 6-wide row is 98,304 px, so five rows fit and six do
# not: the wall's twelve rows pack 5 + 5 + 2, and port 2 runs from row 5 of the
# top section into row 3 of the bottom one.
AUTO_STACK = """
    const a = ax.screen({ id: 1, name: 'Top', columns: 6, rows: 6,
        flowPattern: 'tl-h', portMappingMode: 'organized',
        powerFlowPattern: 'tl-h', powerOrganized: true });
    const b = ax.screen({ id: 2, name: 'Bottom', columns: 6, rows: 6,
        offset_y: 768, flowPattern: 'tl-h', portMappingMode: 'organized',
        powerFlowPattern: 'tl-h', powerOrganized: true });
"""

# Every moveTo/lineTo issued while the deferred overlay pass is running, in
# WORLD coords. Scoped to `_crossMemberPass` so an arrow drawn during a member's
# own pass cannot be mistaken for one drawn across the seam.
CROSS_PASS_STROKES = r"""
window.__ax.crossPassStrokes = function () {
    const r = window.canvasRenderer;
    const ctx = r.ctx;
    const origMove = ctx.moveTo;
    const origLine = ctx.lineTo;
    const out = [];
    let passes = 0;
    const origPass = r._renderCrossMemberPaths;
    r._renderCrossMemberPaths = function (kind) {
        if ((this._crossMemberOwners || []).length) passes += 1;
        return origPass.apply(r, arguments);
    };
    const record = (x, y) => {
        if (!r._crossMemberPass) return;
        const m = ctx.getTransform();
        out.push([Math.round(m.a * x + m.c * y + m.e),
                  Math.round(m.b * x + m.d * y + m.f)]);
    };
    ctx.moveTo = function (x, y) { record(x, y); return origMove.call(ctx, x, y); };
    ctx.lineTo = function (x, y) { record(x, y); return origLine.call(ctx, x, y); };
    try { r.render(); } finally {
        ctx.moveTo = origMove;
        ctx.lineTo = origLine;
        delete r._renderCrossMemberPaths;
    }
    return { passes: passes, points: out };
};
"""


def _auto(page, body, view='data-flow'):
    page.evaluate(CROSS_PASS_STROKES)
    return _run(page, AUTO_STACK, body, view=view)


def test_a_crossing_automatic_port_is_drawn_by_the_deferred_overlay_pass(page):
    """The renderers used to return early from the overlay pass for automatic
    maps, on the grounds that an automatic port never leaves its layer. A
    crossing port drawn inside the owner's transform lands in the wrong place on
    a member with a different rotation or Show Look offset, and a member drawn
    later paints over it - so it has to go through the same deferred pass the
    hand-drawn crossing cables use."""
    result = _auto(page, """
        const out = ax.crossPassStrokes();
        return {
            passes: out.passes,
            ys: out.points.map(p => p[1]),
            ports: window.app.calculatePortAssignments(a).reduce(
                (m, x) => Math.max(m, x.port), 0),
        };
    """)
    assert result['ports'] == 3, result
    assert result['passes'] == 1, 'the overlay pass never ran for the automatic port'
    ys = result['ys']
    assert ys, 'the overlay pass drew nothing'
    # The top section occupies y 0..768, the bottom 768..1536. One line, both.
    assert min(ys) < 768, ys[:12]
    assert max(ys) >= 768, ys[-12:]


def test_a_crossing_automatic_circuit_tints_the_peers_cabinet_not_the_owners(page):
    """layer._powerPanelCircuitMap is keyed `${row},${col}`, which names two
    cabinets at once inside a group: the peer's R3C4 and the owner's. The scoped
    twin has to be populated for an automatic crossing circuit too, or the
    colour-coded power view paints the OWNER's R3C4 and leaves the peer's
    cabinet on whatever the owner's own map happened to say."""
    result = _run(page, AUTO_STACK, """
        const r = window.canvasRenderer;
        r.preparePowerLayerRenderData(a);
        r.preparePowerLayerRenderData(b);
        const peerCabinet = window.app.getPanelByRowCol(b, 0, 0);
        const ownerCabinet = window.app.getPanelByRowCol(a, 0, 0);
        const forPeer = r._powerCircuitForPanel(b, peerCabinet);
        const forOwner = r._powerCircuitForPanel(a, ownerCabinet);
        return {
            peer: forPeer && { owner: forPeer.owner.id, circuit: forPeer.circuitNum },
            owner: forOwner && { owner: forOwner.owner.id, circuit: forOwner.circuitNum },
            peerHasOwnMap: (b._powerPanelCircuitMap || new Map()).size,
            crossing: (a._powerCircuitOwners || []).map(
                o => o ? [...new Set(o)] : null),
        };
    """, view='power')
    # The peer's own map is empty - its circuits are the owner's now.
    assert result['peerHasOwnMap'] == 0, result
    # R0C0 of the BOTTOM section is fed by a circuit the TOP section owns, and
    # it is not circuit 1 (which is the top section's own first three rows).
    assert result['peer'] is not None, 'the peer cabinet was left untinted'
    assert result['peer']['owner'] == 1, result
    assert result['peer']['circuit'] != result['owner']['circuit'], result
    assert result['owner'] == {'owner': 1, 'circuit': 1}, result
    # Three rows fit a 4,160 W circuit, so the wall's twelve rows pack 3 + 3 +
    # 3 + 3 and circuits 3 and 4 are made ENTIRELY of the bottom section's
    # cabinets while belonging to the top section. That is the case the
    # unscoped `${row},${col}` map cannot express at all: circuit 3 holds a
    # cabinet at row 0 col 0, and so does circuit 1.
    #
    # The rows hold LAYER IDS with all-home rows normalised to null (see
    # canvas.js _powerOwnerIdRows): a row holding the layer OBJECT put the
    # layer inside its own cache, made the project circular, and broke every
    # JSON.stringify of it - saveState first among them.
    assert result['crossing'] == [None, None, [2], [2]], result


def test_a_peer_of_a_crossing_group_does_not_read_ERROR_in_the_sidebar(page):
    """Cabinets and no ports is an error only when nothing is feeding them.

    Every peer of a crossing group reports zero ports of its own - the wall's
    ports belong to the member that owns the walk - and the sidebar's "cabinets
    but no ports" test would print a red ERROR beside a wall that is correctly
    routed. The same trap was already reachable through a hand-drawn crossing
    cable; both go through isServedByPeerRouting now.
    """
    result = _run(page, AUTO_STACK, """
        const app = window.app;
        const read = (layer) => {
            app.currentLayer = layer;
            app.updatePortCapacityDisplay();
            const el = document.getElementById('ports-required');
            return { text: el.textContent, red: el.style.color };
        };
        return {
            owner: read(a),
            peer: read(b),
            servedOwner: app.isServedByPeerRouting(a, 'data'),
            servedPeer: app.isServedByPeerRouting(b, 'data'),
        };
    """)
    assert result['servedOwner'] is False, result
    assert result['servedPeer'] is True, result
    assert result['owner']['text'] == '3', result
    assert result['peer']['text'] == '0', result
    assert 'rgb(255, 0, 0)' not in result['peer']['red'], result


def test_an_ungrouped_screen_is_never_served_by_a_peer(page):
    """The helper must answer no for everything outside a group, or the sidebar
    would stop reporting a genuine unroutable screen."""
    result = _run(page, AUTO_STACK, """
        return {
            data: window.app.isServedByPeerRouting(a, 'data'),
            power: window.app.isServedByPeerRouting(a, 'power'),
        };
    """, grouped=False)
    assert result == {'data': False, 'power': False}, result


# ═════════════════════════════════════════════════════════════════════════
# 10. "Route data as one screen" - the group's switch on the crossing
# ═════════════════════════════════════════════════════════════════════════
#
# A group of matching panels can now DECLINE the automatic data crossing
# (group.routeDataAsOne = false, group menu): some walls are cabled per
# section on site no matter what the panels would allow. Off means every
# reader of the crossing reverts together - the walk, the counts, the arrows
# and the sidebar - because the switch sits in the one gate they all pass
# through (_autoCrossMembers). Power is untouched: the switch is data only.

def test_route_as_one_off_stops_the_overlay_pass_drawing_across_the_seam(page):
    """No crossing walk means no crossing arrows: the deferred overlay pass has
    nothing to draw, and each member's own pass draws its own serpentine."""
    result = _auto(page, """
        window.app.project.groups[0].routeDataAsOne = false;
        const out = ax.crossPassStrokes();
        return {
            points: out.points.length,
            aPorts: window.app.calculatePortAssignments(a).reduce(
                (m, x) => Math.max(m, x.port), 0),
            bPorts: window.app.calculatePortAssignments(b).reduce(
                (m, x) => Math.max(m, x.port), 0),
        };
    """)
    assert result['points'] == 0, 'the overlay pass still drew across the seam'
    assert result['aPorts'] == 2, result
    assert result['bPorts'] == 2, result


def test_route_as_one_off_gives_the_peer_its_sidebar_figure_back(page):
    """The peer of a crossing group honestly reads 0; the member of a group
    that cables per screen is not a peer and reads its own real figure."""
    result = _run(page, AUTO_STACK, """
        const app = window.app;
        app.project.groups[0].routeDataAsOne = false;
        const read = (layer) => {
            app.currentLayer = layer;
            app.updatePortCapacityDisplay();
            return document.getElementById('ports-required').textContent;
        };
        return {
            owner: read(a),
            peer: read(b),
            servedPeer: app.isServedByPeerRouting(b, 'data'),
        };
    """)
    assert result['servedPeer'] is False, result
    assert result['owner'] == '2', result
    assert result['peer'] == '2', result


# The rest drive the REAL app against the REAL server, because what they pin
# is the trip: the switch has to survive the commit PUT, an undo, a duplicate
# and a reload, and none of that is visible from a synthetic project swap.
# Same pattern as test_audit_groups_ui; the module guard restores the server.

ROUTE_LIFECYCLE_JS = r"""
window.__rt = {
  async fresh() {
    await fetch('/api/project/new', { method: 'POST' });
    const made = [];
    for (let i = 0; i < 2; i++) {
      const l = await (await fetch('/api/layer/add', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ name: 'S' + i, columns: 6, rows: 6,
          cabinet_width: 128, cabinet_height: 128,
          offset_x: 900, offset_y: i * 768 }),
      })).json();
      made.push(l.id);
    }
    const p = await (await fetch('/api/project')).json();
    window.app.project = p;
    window.app.currentLayer = p.layers.find(l => l.id === made[0]);
    window.app.selectedLayerIds = new Set(made);
    window.app.lastSelectedLayerId = made[0];
    window.app.resetHistory('Initial State');
    const gid = await window.app.groupSelectedLayers();
    await this.settle();
    return gid;
  },
  group(gid) {
    return (window.app.project.groups || []).find(g => g.id === gid) || null;
  },
  flag(gid) {
    const g = this.group(gid);
    if (!g) return '<no group>';
    return g.routeDataAsOne === undefined ? '<absent>' : g.routeDataAsOne;
  },
  async serverFlag(gid) {
    const p = await (await fetch('/api/project')).json();
    const g = (p.groups || []).find(x => x.id === gid);
    if (!g) return '<no group>';
    return g.routeDataAsOne === undefined ? '<absent>' : g.routeDataAsOne;
  },
  async settle(ms) { await new Promise(r => setTimeout(r, ms || 400)); },
};
"""


def _rt(page, body):
    page.evaluate(ROUTE_LIFECYCLE_JS)
    return page.evaluate("async () => { const rt = window.__rt; %s }" % body)


def test_route_switch_survives_the_commit_and_a_reload(page):
    out = _rt(page, r"""
        const gid = await rt.fresh();
        const before = await rt.serverFlag(gid);
        await window.app.toggleGroupRouteDataAsOne(gid);
        const client = rt.flag(gid);
        const server = await rt.serverFlag(gid);
        const action = window.app.history[window.app.historyIndex].action;
        // "save to file and open it again" - the PUT funnel every load uses
        const blob = JSON.parse(JSON.stringify(window.app.project));
        const reloaded = await (await fetch('/api/project', {
            method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(blob) })).json();
        const g = (reloaded.groups || []).find(x => x.id === gid);
        return { before, client, server, action,
                 reloaded: g ? g.routeDataAsOne : '<no group>' };
    """)
    assert out['before'] == '<absent>', out
    assert out['client'] is False, out
    assert out['server'] is False, out
    assert out['reloaded'] is False, out
    assert out['action'] == 'Toggle Group Data Routing', out


def test_route_switch_rides_undo_and_redo(page):
    out = _rt(page, r"""
        const gid = await rt.fresh();
        await window.app.toggleGroupRouteDataAsOne(gid);
        const off = rt.flag(gid);
        window.app.undo(); await rt.settle();
        const undone = rt.flag(gid);
        window.app.redo(); await rt.settle();
        const redone = rt.flag(gid);
        window.app.undo(); await rt.settle();
        const serverUndone = await rt.serverFlag(gid);
        return { off, undone, redone, serverUndone };
    """)
    assert out['off'] is False, out
    assert out['undone'] in ('<absent>', True), out
    assert out['redone'] is False, out
    assert out['serverUndone'] in ('<absent>', True), out


def test_route_switch_copies_with_duplicate_group(page):
    out = _rt(page, r"""
        const gid = await rt.fresh();
        await window.app.toggleGroupRouteDataAsOne(gid);
        const copyGid = await window.app.duplicateGroup(gid);
        await rt.settle();
        return { copy: rt.flag(copyGid),
                 server: await rt.serverFlag(copyGid),
                 original: rt.flag(gid) };
    """)
    assert out['copy'] is False, out
    assert out['server'] is False, out
    assert out['original'] is False, out


def test_route_switch_menu_item_checks_toggles_and_greys_out(page):
    """Where the switch LIVES: the group's own menu, checked while the wall
    routes as one, unchecked after, and greyed out - with the reason in the
    tooltip - on a group whose members could never route as one anyway."""
    out = _rt(page, r"""
        const gid = await rt.fresh();
        window.app.renderLayers();
        await rt.settle(200);
        const open = () => {
            document.querySelector(
                '.screen-group[data-group-id="' + gid + '"] .screen-group-menu-btn'
            ).click();
            return document.querySelector(
                '.screen-group-menu-popup [data-action="route-as-one"]');
        };
        const item = open();
        const first = { enabled: !item.disabled,
                        label: item.textContent.trim(), hint: item.title };
        item.click();
        await rt.settle(700);
        const stored = rt.flag(gid);
        const again = open();
        const second = { label: again.textContent.trim() };
        again.click();
        await rt.settle(700);
        const restored = rt.flag(gid);
        // Mixed resolution never crosses, so there is no choice to offer.
        const g = rt.group(gid);
        window.app.project.layers.find(
            l => l.id === g.layer_ids[1]).cabinet_width = 64;
        const mixed = open();
        const third = { enabled: !mixed.disabled, hint: mixed.title };
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
        return { first, stored, second, restored, third };
    """)
    assert out['first']['enabled'] is True, out
    assert out['first']['label'] == '✓ Route data as one screen', out
    assert 'cables on its own' in out['first']['hint'], out
    assert out['stored'] is False, out
    assert out['second']['label'] == 'Route data as one screen', out
    assert out['restored'] is True, out
    assert out['third']['enabled'] is False, out
    assert 'never route as one' in out['third']['hint'], out
