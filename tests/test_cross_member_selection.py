"""Screen groups (v0.10.9) - MARQUEE SELECT and APPLY PATTERN across members.

The report this exists for: "when we do custom mode on a group i need to be
able to select panels across layers. i can draw across fine but select and use
serpentine isnt working."

Step 6 shipped click-to-add across members. The marquee and Apply-pattern were
deliberately left behind, for a real reason: ``customSelection`` /
``powerCustomSelection`` were keyed by the UNSCOPED ``${row},${col}``, so member
A's R0C0 and member B's R0C0 were ONE entry in the Set, and the pattern pass
read the Set back against ``currentLayer.panels`` alone. A cross-member marquee
could therefore only ever have committed the owner's own cabinets under the
peer's row and column - silently wrong, not partly working.

Two things had to change and both are pinned here:

* SCOPED KEYS. The two custom Sets are keyed by
  ``getScopedPanelKey(layerId, panel)``. ``pixelMapSelection`` deliberately is
  NOT - it is a single-screen feature and its overlay still parses the key with
  ``split(',')``. There is a test for that, because a scoped key parsed by the
  old splitter yields ``parseInt("3:0") === 3``: the wrong panel, no error.

* A POSITION LATTICE, not row/col indices. A 1m member's row 1 and a 0.5m
  member's row 1 are different physical heights, so a serpentine ordered by
  index zig-zags through an order that exists nowhere on site. Every member's
  column and row slots are pooled and ranked by where they sit
  (``buildPositionLattice``), which is the same rank-position mapping step 5
  built for continuous cabinet numbering. The serpentine then alternates per
  LATTICE row and snakes across the whole wall.

Everything runs against SYNTHETIC projects: window.app.project is swapped for a
hand-built one inside a single page.evaluate and restored in a finally, so
nothing leaks into the session-shared page. The methods that would reach the
server or rebuild sidebar DOM for layer ids that do not exist server-side are
stubbed for the duration and restored with the project - a late .then() from one
of those would otherwise land on the REAL project after the swap-back.

Nothing here asserts ``el.style.*``: theme.css uses ``!important`` throughout, so
an inline style that never renders would read back as a false pass. These
assertions are all against the model - the Sets and the stored path entries -
which is where the bug lived anyway.

Run locally:
    python -m pytest tests/test_cross_member_selection.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


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
    yield pg
    context.close()


HELPERS_JS = """
window.__cx = {
    // A screen the way create_layer builds one, in custom mode on both wiring
    // views with empty paths, so each test draws only what it draws.
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
        // Show Look sits exactly on the processor position, so the render
        // offset is zero and world coords equal panel coords. Keeps every
        // assertion below about the lattice rather than about offsets.
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

    // Swap in a synthetic project (plus a clean selection, history and view),
    // run fn, and put everything back no matter what fn does.
    withProject(layers, groups, viewMode, fn) {
        const app = window.app;
        const r = window.canvasRenderer;
        // Land any debounced snapshot on the REAL history before the swap;
        // saveState flushes one on its way in, and a stray entry would show up
        // in the history assertions below as a phantom action.
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
        app._activateCanvasForLayer = () => {};
        this.toasts = [];
        app._toast = (msg, isError) => { window.__cx.toasts.push(String(msg)); };
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
            app._activateCanvasForLayer = saved.activateCanvas;
            app._toast = saved.toast;
            r.viewMode = saved.viewMode;
            r.zoom = saved.zoom; r.panX = saved.panX; r.panY = saved.panY;
            r.render();
        }
    },

    // A world-space marquee, the shape canvas.js hands the selectors.
    rect(x1, y1, x2, y2) { return { x1: x1, y1: y1, x2: x2, y2: y2 }; },

    // The stored path, as plain comparable rows. An entry with no layerId is
    // reported as layerId null so the assertion can see the difference between
    // "the owner's own cabinet" and "a peer's".
    path(layer, portNum) {
        return (layer.customPortPaths[portNum] || []).map(e => ({
            row: e.row, col: e.col,
            layerId: (e.layerId === undefined) ? null : e.layerId,
            hasLayerId: Object.prototype.hasOwnProperty.call(e, 'layerId'),
        }));
    },

    powerPath(layer, circuitNum) {
        return (layer.powerCustomPaths[circuitNum] || []).map(e => ({
            row: e.row, col: e.col,
            layerId: (e.layerId === undefined) ? null : e.layerId,
            hasLayerId: Object.prototype.hasOwnProperty.call(e, 'layerId'),
        }));
    },
};
"""


# ── The mixed wall this feature exists for ────────────────────────────────
#
#   A "JP5"  3 cols x 2 rows of 128px cabinets, x 0..384,   y 0..256
#   B "Half" 3 cols x 4 rows of  64px cabinets, x 384..576, y 0..256
#
# One 576 x 256 wall out of two grids that share no index space at all.
#
# The wall LATTICE that comes out of that:
#   column slots  0, 128, 256 | 384, 448, 512   -> ranks 0 1 2 | 3 4 5
#   row slots     0, 128      | 0, 64, 128, 192 -> ranks 0, 2  | 0 1 2 3
#
# so A's row 1 is lattice row 2 (it is twice as tall), which is precisely the
# thing an index-ordered serpentine gets wrong.

MIXED_WALL_JS = """
    const a = cx.screen({
        id: 1, name: 'JP5', columns: 3, rows: 2,
        cabinet_width: 128, cabinet_height: 128,
    });
    const b = cx.screen({
        id: 2, name: 'Half Panels', columns: 3, rows: 4,
        cabinet_width: 64, cabinet_height: 64,
        offset_x: 384,
    });
"""


def _grouped(page, body, view='data-flow'):
    """Run `body` (JS; has `cx`, `a`, `b` in scope) with A and B grouped."""
    return page.evaluate("""() => {
        const cx = window.__cx;
        %s
        a.group_id = 'g1';
        b.group_id = 'g1';
        const group = cx.group([a, b]);
        return cx.withProject([a, b], [group], '%s', () => {
            %s
        });
    }""" % (MIXED_WALL_JS, view, body))


def _ungrouped(page, body, view='data-flow'):
    """The same two screens with no group at all."""
    return page.evaluate("""() => {
        const cx = window.__cx;
        %s
        return cx.withProject([a, b], [], '%s', () => {
            %s
        });
    }""" % (MIXED_WALL_JS, view, body))


# ── The headline: a marquee spanning two members hits both ────────────────

def test_a_marquee_across_two_members_selects_cabinets_in_both(page):
    """Drag one box over the whole wall, get the whole wall.

    A contributes 3x2 = 6, B contributes 3x4 = 12, so 18 cabinets - and the
    keys are SCOPED, which is the change that makes 18 distinct entries
    possible at all (under `${row},${col}` A's R0C0 and B's R0C0 collapse
    into one and the answer would be 12).
    """
    result = _grouped(page, """
        const app = window.app;
        app.selectPanelsInRect(app.currentLayer, cx.rect(0, 0, 576, 256));
        return {
            keys: [...app.customSelection].sort(),
            fromA: [...app.customSelection].filter(k => k.startsWith('1:')).length,
            fromB: [...app.customSelection].filter(k => k.startsWith('2:')).length,
        };
    """)
    assert result['fromA'] == 6, result
    assert result['fromB'] == 12, result
    assert len(result['keys']) == 18, result
    # Both members' R0C0 survive as separate entries - the collision the
    # unscoped key produced.
    assert '1:0,0' in result['keys'] and '2:0,0' in result['keys'], result


def test_a_marquee_over_only_the_peer_still_selects_it(page):
    """The owner's port may be drawn entirely onto a peer's cabinets.

    Nothing here is currentLayer's own grid, which under the old code meant an
    empty selection.
    """
    result = _grouped(page, """
        const app = window.app;
        app.selectPanelsInRect(app.currentLayer, cx.rect(390, 5, 570, 250));
        return [...app.customSelection].sort();
    """)
    assert result == sorted([
        '2:%d,%d' % (r, c) for r in range(4) for c in range(3)
    ]), result


def test_a_marquee_stops_at_a_screen_that_is_not_a_group_peer(page):
    """Reach is the group's, not the canvas's - an unrelated screen under the
    box must not be dragged into someone else's port."""
    result = page.evaluate("""() => {
        const cx = window.__cx;
        %s
        a.group_id = 'g1';
        b.group_id = 'g1';
        const solo = cx.screen({
            id: 3, name: 'Solo', columns: 2, rows: 2,
            cabinet_width: 128, cabinet_height: 128, offset_x: 640,
        });
        const group = cx.group([a, b]);
        return cx.withProject([a, b, solo], [group], 'data-flow', () => {
            const app = window.app;
            app.selectPanelsInRect(app.currentLayer, cx.rect(0, 0, 2000, 2000));
            return [...app.customSelection].sort();
        });
    }""" % MIXED_WALL_JS)
    assert not any(k.startswith('3:') for k in result), result
    assert len(result) == 18, result


# ── The serpentine: physical order, not index order ───────────────────────
#
# tl-h over the lattice above. Lattice rows 0..3, lattice cols 0..5:
#
#   row 0   A(0,0) A(0,1) A(0,2) | B(0,0) B(0,1) B(0,2)
#   row 1     -      -      -    | B(1,0) B(1,1) B(1,2)
#   row 2   A(1,0) A(1,1) A(1,2) | B(2,0) B(2,1) B(2,2)
#   row 3     -      -      -    | B(3,0) B(3,1) B(3,2)
#
# and a serpentine alternates per LATTICE row: row 0 left to right, row 1 right
# to left (B only), row 2 left to right, row 3 right to left.
#
# Ordered by the panels' own INDICES instead, A's row 1 and B's row 1 would be
# treated as the same height and the cable would leave A's second row to run
# through B's second row - halfway up B's grid, skipping B's third and fourth
# rows entirely until later. That is the bug.

SERPENTINE_EXPECTED = [
    # lattice row 0, left to right: A's top row, then B's top row
    (0, 0, None), (0, 1, None), (0, 2, None),
    (0, 0, 2), (0, 1, 2), (0, 2, 2),
    # lattice row 1, right to left: B only (A has no cabinet this high)
    (1, 2, 2), (1, 1, 2), (1, 0, 2),
    # lattice row 2, left to right: A's second row, then B's third row
    (1, 0, None), (1, 1, None), (1, 2, None),
    (2, 0, 2), (2, 1, 2), (2, 2, 2),
    # lattice row 3, right to left: B only
    (3, 2, 2), (3, 1, 2), (3, 0, 2),
]


def _as_tuples(rows):
    return [(r['row'], r['col'], r['layerId']) for r in rows]


def test_a_serpentine_across_two_cabinet_sizes_snakes_in_physical_order(page):
    """The exact path, step for step - not just its length."""
    result = _grouped(page, """
        const app = window.app;
        app.selectPanelsInRect(app.currentLayer, cx.rect(0, 0, 576, 256));
        app.applyPatternToSelection('tl-h');
        return cx.path(app.currentLayer, 1);
    """)
    assert _as_tuples(result) == SERPENTINE_EXPECTED, _as_tuples(result)


def test_the_path_stores_a_layer_id_on_peers_and_omits_it_on_the_owner(page):
    """`layerId` is written ONLY when it differs from the owner, so a step on
    the owner's own cabinet keeps the exact shape every pre-group project has.
    """
    result = _grouped(page, """
        const app = window.app;
        app.selectPanelsInRect(app.currentLayer, cx.rect(0, 0, 576, 256));
        app.applyPatternToSelection('tl-h');
        return {
            entries: cx.path(app.currentLayer, 1),
            ownerId: app.currentLayer.id,
            // the port stays on currentLayer; the peer stores nothing
            peerPaths: Object.keys(app.project.layers[1].customPortPaths),
        };
    """)
    assert result['ownerId'] == 1
    assert result['peerPaths'] == [], result['peerPaths']
    owners = [e for e in result['entries'] if e['layerId'] is None]
    peers = [e for e in result['entries'] if e['layerId'] is not None]
    assert len(owners) == 6 and len(peers) == 12, result['entries']
    # Not merely "layerId is undefined" - the key must be ABSENT, which is what
    # makes the stored JSON identical to a pre-group project's.
    assert all(e['hasLayerId'] is False for e in owners), owners
    assert all(e['hasLayerId'] is True and e['layerId'] == 2 for e in peers), peers


def test_a_vertical_serpentine_also_runs_on_the_lattice(page):
    """tl-v snakes down lattice COLUMNS, so it must walk A's two tall cabinets
    then B's four short ones - never interleaving them by index."""
    result = _grouped(page, """
        const app = window.app;
        app.selectPanelsInRect(app.currentLayer, cx.rect(0, 0, 576, 256));
        app.applyPatternToSelection('tl-v');
        return cx.path(app.currentLayer, 1);
    """)
    assert _as_tuples(result) == [
        # lattice col 0 top to bottom (A only), col 1 bottom to top, col 2 down
        (0, 0, None), (1, 0, None),
        (1, 1, None), (0, 1, None),
        (0, 2, None), (1, 2, None),
        # lattice cols 3..5 are B's, four rows deep
        (3, 0, 2), (2, 0, 2), (1, 0, 2), (0, 0, 2),
        (0, 1, 2), (1, 1, 2), (2, 1, 2), (3, 1, 2),
        (3, 2, 2), (2, 2, 2), (1, 2, 2), (0, 2, 2),
    ], _as_tuples(result)


def test_the_power_marquee_and_serpentine_cross_members_too(page):
    """Power circuits get the identical treatment - same Set scoping, same
    lattice, same makePathEntry write-through."""
    result = _grouped(page, """
        const app = window.app;
        app.selectPowerPanelsInRect(app.currentLayer, cx.rect(0, 0, 576, 256));
        const selected = app.powerCustomSelection.size;
        app.applyPowerPatternToSelection('tl-h');
        return { selected: selected, path: cx.powerPath(app.currentLayer, 1) };
    """, view='power')
    assert result['selected'] == 18, result
    assert _as_tuples(result['path']) == SERPENTINE_EXPECTED, _as_tuples(result['path'])


# ── Regression: an ungrouped screen is untouched ──────────────────────────

def test_an_ungrouped_screen_selects_and_orders_exactly_as_before(page):
    """The primary guard. One screen, no group: the marquee reaches only that
    screen, the serpentine runs on its own indices, and every stored step is a
    plain {row, col} with no layerId anywhere.
    """
    result = _ungrouped(page, """
        const app = window.app;
        // The box covers BOTH screens; with no group the second is unreachable.
        app.selectPanelsInRect(app.currentLayer, cx.rect(0, 0, 576, 256));
        app.applyPatternToSelection('tl-h');
        return {
            keys: [...app.customSelection].sort(),
            entries: cx.path(app.currentLayer, 1),
            raw: JSON.stringify(app.currentLayer.customPortPaths[1]),
        };
    """)
    assert result['keys'] == sorted(
        ['1:%d,%d' % (r, c) for r in range(2) for c in range(3)]), result['keys']
    # 3x2, serpentine: top row left to right, second row right to left.
    assert _as_tuples(result['entries']) == [
        (0, 0, None), (0, 1, None), (0, 2, None),
        (1, 2, None), (1, 1, None), (1, 0, None),
    ], _as_tuples(result['entries'])
    # Byte for byte the shape a pre-group project stores.
    assert result['raw'] == (
        '[{"row":0,"col":0},{"row":0,"col":1},{"row":0,"col":2},'
        '{"row":1,"col":2},{"row":1,"col":1},{"row":1,"col":0}]'
    ), result['raw']


def test_a_uniform_group_orders_the_same_as_one_equivalent_screen(page):
    """Two 3x2 members of the SAME cabinet size, side by side, are physically a
    6x2 wall - and must wire in exactly the order a single 6x2 screen would.

    Compared by position on the wall (member A's col c is the wall's col c,
    member B's col c is the wall's col c + 3) so the two are directly
    comparable despite living in different index spaces.
    """
    result = page.evaluate("""() => {
        const cx = window.__cx;
        const run = (layers, groups) => cx.withProject(layers, groups, 'data-flow', () => {
            const app = window.app;
            app.selectPanelsInRect(app.currentLayer, cx.rect(0, 0, 768, 256));
            app.applyPatternToSelection('tl-h');
            return cx.path(app.currentLayer, 1);
        });

        const a = cx.screen({ id: 1, name: 'Left', columns: 3, rows: 2 });
        const b = cx.screen({ id: 2, name: 'Right', columns: 3, rows: 2, offset_x: 384 });
        a.group_id = 'g1'; b.group_id = 'g1';
        const grouped = run([a, b], [cx.group([a, b])]);

        const one = cx.screen({ id: 7, name: 'Whole', columns: 6, rows: 2 });
        const single = run([one], []);

        return {
            grouped: grouped.map(e => ({
                row: e.row, col: e.col + (e.layerId === 2 ? 3 : 0) })),
            single: single.map(e => ({ row: e.row, col: e.col })),
        };
    }""")
    assert result['grouped'] == result['single'], result
    # ...and it really is a serpentine over six columns, not two of three.
    assert [(r['row'], r['col']) for r in result['single']] == [
        (0, 0), (0, 1), (0, 2), (0, 3), (0, 4), (0, 5),
        (1, 5), (1, 4), (1, 3), (1, 2), (1, 1), (1, 0),
    ], result['single']


def test_pixel_map_bulk_select_is_unaffected_by_the_key_change(page):
    """pixelMapSelection keeps the UNSCOPED key on purpose.

    Its overlay parses the key back with `key.split(',').map(parseInt)`, and a
    scoped key run through that splitter yields parseInt("2:0") === 2 - the
    wrong panel, silently, with no error anywhere. It is also a single-screen
    feature: even inside a group it must only ever see currentLayer.
    """
    result = _grouped(page, """
        const app = window.app;
        app.selectPixelMapPanelsInRect(app.currentLayer, cx.rect(0, 0, 576, 256));
        return {
            keys: [...app.pixelMapSelection].sort(),
            selected: app.getPixelMapSelectedPanels().map(p => [p.row, p.col]),
        };
    """, view='pixel-map')
    assert result['keys'] == sorted(
        ['%d,%d' % (r, c) for r in range(2) for c in range(3)]), result['keys']
    assert all(':' not in k for k in result['keys']), result['keys']
    assert len(result['selected']) == 6, result['selected']


# ── Conflicts: all-or-nothing, and it says WHICH screen ───────────────────

def test_a_cross_member_conflict_rejects_the_whole_apply_and_names_the_screen(page):
    """One already-wired cabinet on a PEER kills the entire apply.

    A partial apply is the worst outcome available here: the user would get a
    path that looks drawn but is missing the cabinets that were taken, and no
    way to tell which. So nothing is written at all, and the message says both
    which screen the cabinet is on and which port already holds it.
    """
    result = _grouped(page, """
        const app = window.app;
        // Port 2 of the OWNER already claims one of the PEER's cabinets.
        app.currentLayer.customPortPaths[2] = [{ row: 1, col: 1, layerId: 2 }];
        app.currentLayer.customPortIndex = 1;
        app.selectPanelsInRect(app.currentLayer, cx.rect(0, 0, 576, 256));
        app.applyPatternToSelection('tl-h');
        return {
            port1: cx.path(app.currentLayer, 1),
            port2: cx.path(app.currentLayer, 2),
            toasts: window.__cx.toasts.slice(),
            historyActions: app.history.map(h => h.action),
        };
    """)
    # All or nothing: port 1 was never written, port 2 is exactly as it was.
    assert result['port1'] == [], result['port1']
    assert _as_tuples(result['port2']) == [(1, 1, 2)], result['port2']
    assert result['historyActions'] == [], result['historyActions']
    assert len(result['toasts']) == 1, result['toasts']
    msg = result['toasts'][0]
    assert 'Cannot apply: 1 panel already wired to other ports' in msg, msg
    # Names the cabinet's screen AND the port that holds it. R2C2 alone stops
    # meaning anything the moment two grids are in play.
    assert 'R2C2 on Half Panels' in msg, msg
    assert 'port 2' in msg, msg


def test_a_conflict_on_a_peers_own_port_is_seen_and_named(page):
    """The claim can live on the PEER's paths, not the owner's - a port drawn
    from member B holds a cabinet just as firmly as one drawn from A."""
    result = _grouped(page, """
        const app = window.app;
        // The PEER owns port 3, and it runs over the peer's own R0C0.
        app.project.layers[1].customPortPaths[3] = [{ row: 0, col: 0 }];
        app.selectPanelsInRect(app.currentLayer, cx.rect(0, 0, 576, 256));
        app.applyPatternToSelection('tl-h');
        return {
            port1: cx.path(app.currentLayer, 1),
            toasts: window.__cx.toasts.slice(),
        };
    """)
    assert result['port1'] == [], result['port1']
    msg = result['toasts'][0]
    assert 'port 3 on Half Panels' in msg, msg


def test_a_clean_apply_leaves_no_toast_and_one_history_step(page):
    """The other side of the conflict test: when nothing is taken, it applies
    once, quietly."""
    result = _grouped(page, """
        const app = window.app;
        app.selectPanelsInRect(app.currentLayer, cx.rect(0, 0, 576, 256));
        app.applyPatternToSelection('tl-h');
        return {
            count: (app.currentLayer.customPortPaths[1] || []).length,
            toasts: window.__cx.toasts.slice(),
            historyActions: app.history.map(h => h.action),
        };
    """)
    assert result['count'] == 18, result
    assert result['toasts'] == [], result['toasts']
    assert result['historyActions'] == ['Custom Pattern Apply'], result['historyActions']


# ── Hidden cabinets ───────────────────────────────────────────────────────

def test_a_hidden_cabinet_on_a_peer_is_never_selected_or_wired(page):
    """Hiding a cabinet takes it off the wall, so a marquee must not pick it up
    on a peer any more than it does on the owner."""
    result = _grouped(page, """
        const app = window.app;
        app.project.layers[1].panels.find(p => p.row === 0 && p.col === 0).hidden = true;
        app.selectPanelsInRect(app.currentLayer, cx.rect(0, 0, 576, 256));
        app.applyPatternToSelection('tl-h');
        return {
            keys: [...app.customSelection].sort(),
            entries: cx.path(app.currentLayer, 1),
        };
    """)
    assert '2:0,0' not in result['keys'], result['keys']
    assert len(result['keys']) == 17, result['keys']
    assert (0, 0, 2) not in _as_tuples(result['entries']), _as_tuples(result['entries'])
    assert len(result['entries']) == 17, result['entries']
