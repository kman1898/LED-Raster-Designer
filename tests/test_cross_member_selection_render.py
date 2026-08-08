"""Screen groups (v0.11.0) - DRAWING a selection that crosses members.

Step 6 let a hand-drawn port run off one member of a group and onto the next.
The marquee could not follow, because `customSelection` / `powerCustomSelection`
were keyed by the UNSCOPED `${row},${col}`: member A's R0C0 and member B's R0C0
were the same entry in the Set, so a cross-member selection was not expressible
at all. Those two Sets are now keyed by getScopedPanelKey,
`${layerId}:${row},${col}`, and this file covers the canvas half of that - what
the highlight overlay actually draws once the keys carry a layer.

Four things are pinned here deliberately:

* THE WRONG-PANEL BUG IS ASSERTED DIRECTLY. The old parser was
  `key.split(',').map(n => parseInt(n, 10))`, and against a scoped key that
  yields `parseInt("2:0") === 2` - a real row, a real cabinet, the WRONG one,
  silently and with no error. The owner here is three rows tall precisely so
  that row 2 EXISTS: under the old parser a peer key would light one of the
  owner's own cabinets, which is what the assertions rule out.

* THE MEMBERS DISAGREE ON WHERE THEY ARE. B is at offset_x 600 in processor
  coords but dragged to showOffsetX 2000 for the show file, so the owner's
  frame and the peer's frame are 1400 px apart. A highlight drawn in the wrong
  member's transform cannot land on the right pixels by accident.

* PIXEL MAP IS A DIFFERENT FEATURE. `pixelMapSelection` is bulk hide/blank
  within ONE screen, it keeps the unscoped key and the old parser, and grouping
  the screens must not change one fill it issues.

* THE REGRESSION GUARD. An ungrouped screen's overlay has to draw exactly what
  it drew before - asserted by rendering the same selection grouped and
  ungrouped and demanding identical fills, and by feeding in a legacy unscoped
  key and getting the same single highlight.

Asserted from recorded ctx calls mapped through the live transform into world
coords - never from element styles. theme.css uses !important, so an inline
style assertion passes without anything being rendered.

Everything runs against SYNTHETIC projects, swapped in and restored in a
finally, following test_screen_groups_canvas.py.

Run locally:
    python -m pytest tests/test_cross_member_selection_render.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


HELPERS_JS = r"""
window.__cs = {
    // A screen shaped the way create_layer builds one, in BOTH custom modes so
    // the two selection overlays are live without any UI interaction.
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
            show_numbers: false, number_size: 30,
            show_panel_borders: false, panel_border_width: 2,
            border_color: '#ffffff', rotation: 0,
            flowPattern: 'custom', portMappingMode: 'organized',
            customPortPaths: {}, customPortIndex: 1,
            powerFlowPattern: 'custom', powerOrganized: true, powerMaximize: false,
            powerCustomPaths: {}, powerCustomIndex: 1,
            transparentFill: true,
            showLabelName: false, showLabelInfo: false,
            showDataFlowPortInfo: false, showPowerCircuitInfo: false,
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

    canvas(id, opts) {
        return Object.assign({
            id: id, name: id, workspace_x: 0, workspace_y: 0,
            show_workspace_x: 0, show_workspace_y: 0,
            raster_width: 8192, raster_height: 8192,
            show_raster_width: 8192, show_raster_height: 8192,
            color: '#ff0000', visible: true,
        }, opts || {});
    },

    project(layers, groups) {
        return {
            layers: layers,
            groups: groups || [],
            canvases: [this.canvas('c1')],
            active_canvas_id: 'c1',
        };
    },

    group(layers, opts) {
        return Object.assign({
            id: 'g1', name: 'Main Wall', layer_ids: layers.map(l => l.id),
        }, opts || {});
    },

    // Swap in a synthetic project, run fn, put everything back whatever fn
    // does. The methods that would reach the server or rebuild the sidebar for
    // layer ids that exist only in this frame are stubbed for the duration - a
    // late .then() from one of them would otherwise land on the REAL project.
    //
    // The three selection Sets are swapped and restored here too: they live on
    // the app, not on the project, so a test that left one populated would leak
    // a highlight into every later frame of the shared page.
    withProject(layers, groups, viewMode, fn) {
        const app = window.app;
        const r = window.canvasRenderer;
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
            updateCustomFlowUI: app.updateCustomFlowUI,
            updateCustomPowerUI: app.updateCustomPowerUI,
            updatePixelMapBulkActionUI: app.updatePixelMapBulkActionUI,
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
        app.updateCustomFlowUI = () => {};
        app.updateCustomPowerUI = () => {};
        app.updatePixelMapBulkActionUI = () => {};
        app._activateCanvasForLayer = () => {};
        app.project = this.project(layers, groups);
        app.currentLayer = layers[0] || null;
        app.selectedLayerIds = new Set();
        app.history = [];
        app.historyIndex = -1;
        app.customSelection = new Set();
        app.powerCustomSelection = new Set();
        app.pixelMapSelection = new Set();
        r.viewMode = viewMode || 'data-flow';
        r.zoom = 1; r.panX = 0; r.panY = 0;
        r.magneticSnap = false;
        try {
            return fn();
        } finally {
            app.project = saved.project;
            app.currentLayer = saved.currentLayer;
            app.selectedLayerIds = saved.selectedLayerIds;
            app.history = saved.history;
            app.historyIndex = saved.historyIndex;
            app.customSelection = saved.customSelection;
            app.powerCustomSelection = saved.powerCustomSelection;
            app.pixelMapSelection = saved.pixelMapSelection;
            app.updateLayers = saved.updateLayers;
            app.renderLayers = saved.renderLayers;
            app.loadLayerToInputs = saved.loadLayerToInputs;
            app.loadTextLayerToInputs = saved.loadTextLayerToInputs;
            app.saveClientSideProperties = saved.saveClientSideProperties;
            app.updateCustomFlowUI = saved.updateCustomFlowUI;
            app.updateCustomPowerUI = saved.updateCustomPowerUI;
            app.updatePixelMapBulkActionUI = saved.updatePixelMapBulkActionUI;
            app._activateCanvasForLayer = saved.activateCanvas;
            r.viewMode = saved.viewMode;
            r.zoom = saved.zoom; r.panX = saved.panX; r.panY = saved.panY;
            r.magneticSnap = saved.magneticSnap;
            // A test that pressed the mouse down and never let go must not
            // leave the shared page mid-drag.
            r.isSelectingPanels = false;
            r.isSelectingPixelMapPanels = false;
            r.isSelectingLayers = false;
            r.isDraggingLayer = false;
            r.selectionRect = null;
            r.layerSelectionRect = null;
            r.render();
        }
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

    // Every fillRect ONE overlay issues during a real frame, in WORLD coords.
    //
    // Scoped to the overlay method rather than filtered by colour: the active
    // port badge fills its background in the same rgba(0,0,0,0.6), and a test
    // that could not tell the two apart would pass on the badge alone. World
    // coords, because the whole point of the peer branch is that it draws under
    // a DIFFERENT transform from the owner's - the raw fillRect arguments of
    // the two are not comparable, only the resolved pixels are.
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
                    w: Math.round(m.a * w), h: Math.round(m.d * h),
                    color: String(ctx.fillStyle).toLowerCase(),
                });
            }
            return origFill.call(ctx, x, y, w, h);
        };
        try { r.render(); } finally { ctx.fillRect = origFill; delete r[method]; }
        return out;
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
    pg.wait_for_timeout(2000)  # socket connect + app init
    pg.evaluate(HELPERS_JS)
    return pg


# ── the wall ──────────────────────────────────────────────────────────────
#
# A (the OWNER, currentLayer) is 2 wide x 3 TALL of 128 px cabinets at the
# origin. Three rows so that row 2 exists: `parseInt("2:0")` is 2, so under the
# old unscoped parser the peer key '2:0,0' would resolve to A's own R2C0 and
# paint a highlight at (0, 256). Every peer assertion below rules that out.
#
# B (the PEER) is 2 x 2 at offset_x 600 in processor coords, dragged to
# showOffsetX 2000 for the show file. Data Flow and Power draw at the SHOW
# position, so the owner's frame and the peer's frame are 1400 px apart and no
# assertion can pass in the wrong one.

WALL_JS = """
    const cs = window.__cs;
    const A = cs.screen({ id: 1, name: 'A', columns: 2, rows: 3 });
    const B = cs.screen({ id: 2, name: 'B', columns: 2, rows: 2,
                          offset_x: 600, offset_y: 0,
                          showOffsetX: 2000, showOffsetY: 0 });
"""

A00 = {'x': 0, 'y': 0, 'w': 128, 'h': 128}        # owner R0C0
A01 = {'x': 128, 'y': 0, 'w': 128, 'h': 128}      # owner R0C1
A20 = {'x': 0, 'y': 256, 'w': 128, 'h': 128}      # owner R2C0 - the wrong-parse trap
B00 = {'x': 2000, 'y': 0, 'w': 128, 'h': 128}     # peer R0C0, where the show file puts it
B00_PROC_X = 600                                   # ...and where it is NOT drawn


def _run(page, body, grouped=True, view='data-flow'):
    """`body` is JS with cs, A, B (and `group` when grouped) in scope."""
    return page.evaluate("""() => {
        %s
        %s
        return cs.withProject([A, B], %s, '%s', () => { %s });
    }""" % (
        WALL_JS,
        ("A.group_id = 'g1'; B.group_id = 'g1'; const group = cs.group([A, B]);"
         if grouped else "const group = null;"),
        "[group]" if grouped else "[]",
        view, body,
    ))


def _boxes(fills):
    """Just the geometry, so a colour change is a separate assertion."""
    return [{'x': f['x'], 'y': f['y'], 'w': f['w'], 'h': f['h']} for f in fills]


# ── 1. A selection that spans two members highlights BOTH, in their own frames

def test_a_scoped_selection_highlights_cabinets_in_both_members(page):
    """One selection, two members, two frames 1400 px apart.

    The owner is not dragged (its show and processor positions coincide) and the
    peer is, so a peer highlight drawn under the OWNER's transform would land at
    the peer's PROCESSOR x of 600 instead of its show x of 2000. Both are real
    coordinates on this canvas, so only the right one passes.
    """
    fills = _run(page, """
        window.app.currentLayer = A;
        window.app.customSelection = new Set(['1:0,0', '2:0,0']);
        return cs.overlayFills('renderCustomSelectionOverlay');
    """)
    boxes = _boxes(fills)
    assert len(boxes) == 2, boxes
    assert A00 in boxes, boxes
    assert B00 in boxes, boxes
    assert all(b['x'] != B00_PROC_X for b in boxes), (
        'the peer was drawn in the owner\'s frame, at its processor x', boxes)
    assert all(f['color'] == 'rgba(0, 0, 0, 0.6)' for f in fills), fills


def test_the_power_selection_overlay_spans_members_the_same_way(page):
    """The Power twin is a separate function and gets its own guard."""
    fills = _run(page, """
        window.app.currentLayer = A;
        window.app.powerCustomSelection = new Set(['1:0,1', '2:0,0']);
        return cs.overlayFills('renderPowerSelectionOverlay');
    """, view='power')
    boxes = _boxes(fills)
    assert len(boxes) == 2, boxes
    assert A01 in boxes, boxes
    assert B00 in boxes, boxes


# ── 2. THE BUG: a peer cabinet at the owner's own row/col ──────────────────

def test_a_peer_cabinet_highlights_the_peer_not_the_owners_same_row_col(page):
    """'2:0,0' is B's R0C0. A has an R0C0 too, and it must stay dark.

    This is the exact failure the unscoped key caused: one Set entry for two
    cabinets, so the owner's was highlighted (and, later, wired) under the
    peer's row and column. It is also the exact failure the OLD PARSER caused
    from the other direction - `parseInt("2:0")` is 2, so the key would have
    resolved to A's R2C0 at (0, 256).
    """
    fills = _run(page, """
        window.app.currentLayer = A;
        window.app.customSelection = new Set(['2:0,0']);
        return cs.overlayFills('renderCustomSelectionOverlay');
    """)
    boxes = _boxes(fills)
    assert boxes == [B00], boxes
    assert A00 not in boxes, 'the owner\'s own R0C0 was highlighted instead'
    assert A20 not in boxes, 'the scoped key was parsed as row 2 of the owner'


def test_a_key_naming_an_unreachable_layer_highlights_nothing(page):
    """Ungrouped, B is not reachable, so a key naming it resolves to nothing.

    Not to "the owner's cabinet at that row and column", which is what a
    resolver that shrugged and fell back to currentLayer would do - and what
    would silently wire the wrong screen after a group is broken up.
    """
    fills = _run(page, """
        window.app.currentLayer = A;
        window.app.customSelection = new Set(['2:0,0']);
        return cs.overlayFills('renderCustomSelectionOverlay');
    """, grouped=False)
    assert fills == [], fills


# ── 3. Pixel Map is a different feature and is untouched ───────────────────

def test_pixel_map_selection_is_unaffected_by_grouping(page):
    """Same unscoped key, same single fill, grouped or not.

    pixelMapSelection is bulk hide / blank within ONE screen. It keeps the
    unscoped `${row},${col}` key and the original parser, and the peer's R0C0
    must not join the selection just because the screens are now a wall.
    """
    body = """
        window.app.currentLayer = A;
        window.app.pixelMapSelection = new Set(['0,0']);
        return cs.overlayFills('renderPixelMapSelectionOverlay');
    """
    grouped = _run(page, body, grouped=True, view='pixel-map')
    ungrouped = _run(page, body, grouped=False, view='pixel-map')

    assert grouped == ungrouped, (grouped, ungrouped)
    # Pixel Map draws a fill AND a stroke per panel; only the fill is recorded.
    assert _boxes(grouped) == [A00], grouped
    assert grouped[0]['color'] == 'rgba(74, 144, 226, 0.35)', grouped


def test_pixel_map_ignores_a_scoped_key_rather_than_misreading_it(page):
    """Nothing writes a scoped key into pixelMapSelection - and if anything
    ever did, the honest outcome is no highlight, not a highlight on row 2."""
    fills = _run(page, """
        window.app.currentLayer = A;
        window.app.pixelMapSelection = new Set(['2:0,0']);
        return cs.overlayFills('renderPixelMapSelectionOverlay');
    """, view='pixel-map')
    assert _boxes(fills) == [A20], (
        'documenting the unscoped parser: it reads "2:0" as row 2. Nothing '
        'produces such a key for this Set; if that ever changes, this overlay '
        'has to be scoped too', fills)


# ── 4. THE REGRESSION GUARD ───────────────────────────────────────────────

def test_an_ungrouped_screens_selection_draws_exactly_as_before(page):
    """Owner-only selection: identical fills grouped and ungrouped.

    Every project on disk is this case. Grouping may not move the highlight by
    a pixel, and the peer branch must not fire when no key names a peer.
    """
    body = """
        window.app.currentLayer = A;
        window.app.customSelection = new Set(['1:0,0', '1:0,1']);
        return cs.overlayFills('renderCustomSelectionOverlay');
    """
    grouped = _run(page, body, grouped=True)
    ungrouped = _run(page, body, grouped=False)

    assert grouped == ungrouped, (grouped, ungrouped)
    boxes = _boxes(ungrouped)
    assert len(boxes) == 2, boxes
    assert A00 in boxes and A01 in boxes, boxes


def test_a_legacy_unscoped_key_still_reads_as_the_owners_cabinet(page):
    """'0,0' - the key shape every pre-v0.11.0 Set held - is owner-relative.

    Not a compatibility nicety for saved data (selections are never persisted),
    but the guarantee that a caller which has not been scoped yet keeps working
    exactly as it did instead of failing silently.
    """
    scoped = _run(page, """
        window.app.currentLayer = A;
        window.app.customSelection = new Set(['1:0,0']);
        return cs.overlayFills('renderCustomSelectionOverlay');
    """)
    legacy = _run(page, """
        window.app.currentLayer = A;
        window.app.customSelection = new Set(['0,0']);
        return cs.overlayFills('renderCustomSelectionOverlay');
    """)
    assert legacy == scoped, (legacy, scoped)
    assert _boxes(legacy) == [A00], legacy


# ── 5. Starting the drag over the NEXT member of the wall ─────────────────

def test_a_marquee_can_start_over_a_peers_cabinets_without_stealing_the_port(page):
    """Press down on B while drawing A's port: the marquee starts, and A is
    still the layer that owns what is being drawn.

    A plain click on a panel normally promotes that panel's layer to
    currentLayer. Mid-draw that silently moves ownership of the path onto the
    peer - the marquee would fill B's port instead of the one the user has
    open, and step 6's cross-member click-to-add gate would never see a peer at
    all, because currentLayer would already BE that peer.
    """
    state = _run(page, """
        const r = window.canvasRenderer;
        window.app.currentLayer = A;
        r.handleMouseDown(cs.ev(2064, 64));   // B's R0C0, at its SHOW position
        return {
            owner: window.app.currentLayer.id,
            selecting: !!r.isSelectingPanels,
            rect: r.selectionRect && { x: Math.round(r.selectionRect.x1),
                                       y: Math.round(r.selectionRect.y1) },
        };
    """)
    assert state['owner'] == 1, 'the peer stole the port being drawn'
    assert state['selecting'] is True, state
    assert state['rect'] == {'x': 2064, 'y': 64}, state


def test_clicking_a_peer_still_selects_it_when_not_drawing_a_path(page):
    """The regression half: outside custom mode a click on another screen
    selects that screen, exactly as it always has."""
    owner = _run(page, """
        A.flowPattern = 'tl-h';
        B.flowPattern = 'tl-h';
        window.app.currentLayer = A;
        window.canvasRenderer.handleMouseDown(cs.ev(2064, 64));
        return window.app.currentLayer.id;
    """)
    assert owner == 2, 'clicking another screen no longer selects it'


# ── 6. The wall lattice the flow patterns order by ────────────────────────
#
# getGroupLattice is the extracted form of the step-5 numbering ranks, and the
# ONE implementation both the cabinet IDs and app-power.js's cross-member flow
# patterns order by. Its contract is asserted here because a second copy of it
# appearing anywhere is the failure mode.

LATTICE_WALL_JS = """
    const cs = window.__cs;
    // 2 x 2 of 1 m cabinets with a 4 x 1 strip of 0.5 m cabinets underneath:
    // columns pooled across the wall are x = 0, 64, 128, 192 -> ranks 0..3, so
    // the big member's own columns rank 0 and 2 and the strip's rank 0..3.
    // Rows are y = 0, 128 (big) and 256 (strip) -> ranks 0, 1, 2.
    const A = cs.screen({ id: 1, name: 'Big', columns: 2, rows: 2,
                          cabinet_width: 128, cabinet_height: 128 });
    const B = cs.screen({ id: 2, name: 'Strip', columns: 4, rows: 1,
                          cabinet_width: 64, cabinet_height: 64,
                          offset_y: 256 });
"""


def _lattice(page, body, grouped=True, via='getGroupLattice(A)'):
    return page.evaluate("""() => {
        %s
        %s
        return cs.withProject([A, B], %s, 'cabinet-id', () => {
            const lattice = window.canvasRenderer.%s;
            %s
        });
    }""" % (
        LATTICE_WALL_JS,
        ("A.group_id = 'g1'; B.group_id = 'g1'; const group = cs.group([A, B]);"
         if grouped else "const group = null;"),
        "[group]" if grouped else "[]",
        via, body,
    ))


RANKS_JS = """
    const at = (l, r, c) => l.panels.find(p => p.row === r && p.col === c);
    return {
        bigC0: lattice.colOf(A, at(A, 0, 0)),
        bigC1: lattice.colOf(A, at(A, 0, 1)),
        stripC1: lattice.colOf(B, at(B, 0, 1)),
        stripC3: lattice.colOf(B, at(B, 0, 3)),
        bigR1: lattice.rowOf(A, at(A, 1, 0)),
        stripR0: lattice.rowOf(B, at(B, 0, 0)),
        members: lattice.members.map(m => m.id),
    };
"""


def test_the_lattice_ranks_cabinets_by_where_they_sit_not_by_index(page):
    """The big member's column 1 is the wall's column 2, because a 0.5 m
    cabinet edge falls between them. Ordering a serpentine by the panels' own
    indices instead would zig-zag the wall in the wrong order."""
    ranks = _lattice(page, RANKS_JS)
    assert ranks['bigC0'] == 0 and ranks['bigC1'] == 2, ranks
    assert ranks['stripC1'] == 1 and ranks['stripC3'] == 3, ranks
    assert ranks['bigR1'] == 1, ranks
    assert ranks['stripR0'] == 2, ranks
    assert ranks['members'] == [1, 2], ranks


def test_the_lattice_is_the_same_one_whichever_door_it_is_reached_through(page):
    """getPositionLattice(members) is the implementation; getGroupLattice(layer)
    is the group's members handed to it. app-power.js calls the first with its
    own path scope, the cabinet numbering calls the second - one lattice, so
    the order a wall is wired in and the numbers written on it agree."""
    by_group = _lattice(page, RANKS_JS)
    by_list = _lattice(page, RANKS_JS, via='getPositionLattice([A, B])')
    assert by_list == by_group, (by_list, by_group)


def test_a_one_screen_lattice_ranks_that_screens_own_grid(page):
    """The ungrouped path: for a uniform grid the ranks ARE the panels' own
    indices, so a single screen ordered through the lattice comes out in the
    order it has always come out in."""
    ranks = _lattice(page, """
        const at = (l, r, c) => l.panels.find(p => p.row === r && p.col === c);
        return {
            c0: lattice.colOf(A, at(A, 0, 0)), c1: lattice.colOf(A, at(A, 0, 1)),
            r0: lattice.rowOf(A, at(A, 0, 0)), r1: lattice.rowOf(A, at(A, 1, 0)),
            // A panel from a screen outside the list falls back to its own
            // index rather than throwing or returning NaN.
            outside: lattice.colOf(B, at(B, 0, 3)),
        };
    """, grouped=False, via='getPositionLattice([A])')
    assert ranks == {'c0': 0, 'c1': 1, 'r0': 0, 'r1': 1, 'outside': 3}, ranks


def test_the_lattice_orders_a_cross_member_set_in_reading_order(page):
    """`compare` is the wall's reading order over {layer, panel} pairs - what a
    cross-member pattern sorts a mixed selection with."""
    order = _lattice(page, """
        const at = (l, r, c) => ({ layer: l, panel: l.panels.find(p => p.row === r && p.col === c) });
        const picked = [at(B, 0, 3), at(A, 1, 0), at(A, 0, 1), at(B, 0, 0)];
        picked.sort(lattice.compare);
        return picked.map(h => h.layer.name + ' r' + h.panel.row + 'c' + h.panel.col);
    """)
    assert order == ['Big r0c1', 'Big r1c0', 'Strip r0c0', 'Strip r0c3'], order


def test_the_lattice_is_null_for_a_screen_that_is_not_in_a_group(page):
    """Null is what keeps every single-screen caller on the path it always
    took - the numbering, and the flow patterns."""
    assert _lattice(page, "return lattice;", grouped=False) is None
