"""Screen groups (v0.10.9) - DRAWING and SCORING a path that crosses members.

test_cross_layer_paths.py covers the server side: what a `{row, col, layerId}`
step is, and what the integrity pass does to a stale one. This file covers the
canvas: whether the crossing path actually comes out as one continuous cable,
whether it stops at the group's edge, and whether the port under it is scored
against a number that means something.

Four things pinned here deliberately:

* THE REGRESSION GUARD COMES FIRST. A path with no cross-layer step must render
  through the code it always rendered through. It is asserted by drawing the
  same path twice - once in a grouped project and once ungrouped - and
  demanding the two frames produce the SAME segments. Every existing project on
  disk is that case, so if grouping perturbs it at all the feature is not worth
  having.

* TWO FRAMES, NOT ONE. Load and capacity are PROCESSOR facts (the NovaStar
  Armor rectangle constraint is about the pixel rectangle the processor pushes;
  the low-latency derate measures Y down the processor raster), while the cable
  is drawn where the SHOW file puts the screens. Those two disagree the moment
  a member is dragged in Show Look, so the members here are given a Show Look
  offset that makes them disagree by a wide margin and both frames are asserted
  separately. A test where showOffset happens to equal offset_x would pass with
  the two frames swapped.

* CANNOT-SCORE IS A REAL ANSWER. Show Look can move a member onto another
  canvas, which leaves two members sharing an effective canvas while their
  panels are laid out against different processor rasters. There is no honest
  rectangle across two rasters, so the port is not scored at all rather than
  scored wrongly, and that is asserted as the ABSENCE of the badge.

* ASSERTED FROM WHAT THE CONTEXT WAS ASKED TO DRAW - recorded ctx calls, mapped
  through the live transform into world coords - never from element styles. The
  point of an overlay pass is precisely that the transform is different, so a
  test that read anything but the resolved coordinates would not be testing it.

Everything runs against SYNTHETIC projects, swapped in and restored in a
finally, following test_screen_groups_canvas.py.

Run locally:
    python -m pytest tests/test_cross_layer_paths_render.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


HELPERS_JS = r"""
window.__xp = {
    // A screen shaped the way create_layer builds one. 2 x 2 of 128 px unless
    // the caller says otherwise, so panel (0,0) of a screen at offset_x = N
    // covers N..N+128 and its centre is N + 64 - the number the assertions
    // below are written in.
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
            flowPattern: 'tl-h', portMappingMode: 'organized',
            powerFlowPattern: 'tl-h', powerOrganized: true, powerMaximize: false,
            // Distinctive, so the recorders below can pick this renderer's
            // strokes out of everything else the frame draws.
            dataFlowColor: '#00ff88',
            powerLineColor: '#ff00cc',
            arrowColor: '#0042aa',
            transparentFill: true,
            showLabelName: false, showLabelInfo: false,
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

    project(layers, groups, canvases) {
        return {
            layers: layers,
            groups: groups || [],
            canvases: canvases || [this.canvas('c1')],
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
    withProject(layers, groups, viewMode, fn, canvases) {
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
        app.project = this.project(layers, groups, canvases);
        app.currentLayer = layers[0] || null;
        app.selectedLayerIds = new Set();
        app.history = [];
        app.historyIndex = -1;
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
            app.updateLayers = saved.updateLayers;
            app.renderLayers = saved.renderLayers;
            app.loadLayerToInputs = saved.loadLayerToInputs;
            app.loadTextLayerToInputs = saved.loadTextLayerToInputs;
            app.saveClientSideProperties = saved.saveClientSideProperties;
            app._activateCanvasForLayer = saved.activateCanvas;
            r.viewMode = saved.viewMode;
            r.zoom = saved.zoom; r.panX = saved.panX; r.panY = saved.panY;
            r.magneticSnap = saved.magneticSnap;
            r.render();
        }
    },

    // Every STROKED straight segment drawn in `color` during one frame, in
    // WORLD coordinates.
    //
    // World, not local: the whole reason a crossing path needs its own pass is
    // that it is drawn under a different ctx transform from the per-layer one,
    // so the raw moveTo/lineTo arguments of the two passes are not comparable.
    // Each point is pushed through ctx.getTransform() at the moment it is
    // issued, which is the only frame both passes agree in.
    //
    // Stroked only: the arrowheads are moveTo/lineTo/lineTo/closePath/fill, so
    // segments are held pending and committed on stroke(), discarded on fill().
    strokes(color) {
        const r = window.canvasRenderer;
        const ctx = r.ctx;
        const o = {
            beginPath: ctx.beginPath, moveTo: ctx.moveTo, lineTo: ctx.lineTo,
            stroke: ctx.stroke, fill: ctx.fill,
        };
        const want = String(color).toLowerCase();
        const out = [];
        let pending = [];
        let cur = null;
        const xf = (x, y) => {
            const m = ctx.getTransform();
            return { x: m.a * x + m.c * y + m.e, y: m.b * x + m.d * y + m.f };
        };
        ctx.beginPath = function () { pending = []; cur = null; return o.beginPath.call(ctx); };
        ctx.moveTo = function (x, y) { cur = xf(x, y); return o.moveTo.call(ctx, x, y); };
        ctx.lineTo = function (x, y) {
            const p = xf(x, y);
            if (cur) pending.push({ x1: cur.x, y1: cur.y, x2: p.x, y2: p.y });
            cur = p;
            return o.lineTo.call(ctx, x, y);
        };
        ctx.stroke = function () {
            if (String(ctx.strokeStyle).toLowerCase() === want) out.push(...pending);
            pending = [];
            return o.stroke.call(ctx);
        };
        ctx.fill = function () { pending = []; return o.fill.call(ctx); };
        try { r.render(); } finally { Object.assign(ctx, o); }
        return out.map(s => ({
            x1: Math.round(s.x1), y1: Math.round(s.y1),
            x2: Math.round(s.x2), y2: Math.round(s.y2),
        }));
    },

    // Every fillRect issued in one frame, in world coords, with the colour it
    // was filled in - how the colour-coded power view is asserted.
    fills() {
        const r = window.canvasRenderer;
        const ctx = r.ctx;
        const original = ctx.fillRect;
        const out = [];
        ctx.fillRect = function (x, y, w, h) {
            const m = ctx.getTransform();
            out.push({
                x: Math.round(m.a * x + m.c * y + m.e),
                y: Math.round(m.b * x + m.d * y + m.f),
                w: Math.round(m.a * w), h: Math.round(m.d * h),
                color: String(ctx.fillStyle).toLowerCase(),
            });
            return original.call(ctx, x, y, w, h);
        };
        try { r.render(); } finally { ctx.fillRect = original; }
        return out;
    },

    // Every string drawn in one frame, in draw order.
    texts() {
        const r = window.canvasRenderer;
        const ctx = r.ctx;
        const original = ctx.fillText;
        const out = [];
        ctx.fillText = function (t, x, y, w) {
            out.push(String(t));
            return original.call(ctx, t, x, y, w);
        };
        try { r.render(); } finally { ctx.fillText = original; }
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
# Two 2x2 members of 128 px cabinets. B sits at offset_x = 600 in PROCESSOR
# coords but is dragged to showOffsetX = 2000 for the show file, so the two
# frames the renderer has to keep apart are 1400 px apart and no assertion can
# accidentally pass in the wrong one. A is not dragged, so its two frames
# coincide and its own numbers stay readable.

#
# B draws its own automatic port map and its own automatic circuits in its own
# colours, which is exactly what a second screen does. Those are given
# different colours from A's so the recorders can say "the cable A drew" - the
# path under test belongs to A even where it lands on B's cabinets.

WALL_JS = """
    const xp = window.__xp;
    const A = xp.screen({ id: 1, name: 'A', offset_x: 0, offset_y: 0 });
    const B = xp.screen({ id: 2, name: 'B', offset_x: 600, offset_y: 0,
                          showOffsetX: 2000, showOffsetY: 0,
                          dataFlowColor: '#3366ff', powerLineColor: '#3366ff' });
"""

# Panel centres, so the assertions read as the geometry they are about.
A00 = (64, 64)         # A panel (0,0), processor AND show (A is not dragged)
A01 = (192, 64)        # A panel (0,1)
B00_SHOW = (2064, 64)  # B panel (0,0) where the SHOW file puts it
B00_PROC = (664, 64)   # ...and where the processor sees it


def _run(page, body, grouped=True, view='data-flow'):
    """`body` is JS with xp, A, B (and `group` when grouped) in scope."""
    return page.evaluate("""() => {
        %s
        %s
        return xp.withProject([A, B], %s, '%s', () => { %s });
    }""" % (
        WALL_JS,
        ("A.group_id = 'g1'; B.group_id = 'g1'; const group = xp.group([A, B]);"
         if grouped else "const group = null;"),
        "[group]" if grouped else "[]",
        view, body,
    ))


# ── 1. THE REGRESSION GUARD ───────────────────────────────────────────────

def test_a_path_that_stays_home_draws_the_same_grouped_or_not(page):
    """The case every project on disk is in.

    A custom port drawn entirely on its owner has no cross-layer step, so it
    must never touch the overlay pass - it takes the per-layer branch it always
    took. Asserted by drawing the identical path in a grouped and an ungrouped
    project and demanding the two frames match segment for segment: if merely
    being in a group perturbs an ordinary path, the feature has broken every
    existing wall to serve a new one.
    """
    body = """
        A.flowPattern = 'custom';
        A.customPortPaths = { 1: [{row: 0, col: 0}, {row: 0, col: 1},
                                  {row: 1, col: 1}] };
        return xp.strokes('#00ff88');
    """
    grouped = _run(page, body, grouped=True)
    ungrouped = _run(page, body, grouped=False)

    assert grouped == ungrouped, (
        'grouping changed how an ordinary single-layer path draws\n'
        f'grouped:   {grouped}\nungrouped: {ungrouped}')
    # And it is the path that was actually drawn, not two empty lists agreeing.
    assert grouped == [
        {'x1': A00[0], 'y1': A00[1], 'x2': A01[0], 'y2': A01[1]},
        {'x1': A01[0], 'y1': A01[1], 'x2': 192, 'y2': 192},
    ], grouped


def test_a_path_that_stays_home_is_drawn_exactly_once(page):
    """The overlay pass must not draw it a second time on top.

    A duplicate would be invisible on screen - same colour, same coordinates -
    and would only ever surface as doubled ink in an export, so it is asserted
    as a segment COUNT rather than by eye.
    """
    segs = _run(page, """
        A.flowPattern = 'custom';
        A.customPortPaths = { 1: [{row: 0, col: 0}, {row: 0, col: 1}] };
        return xp.strokes('#00ff88');
    """)
    assert len(segs) == 1, segs


# ── 2. THE CROSSING CABLE ─────────────────────────────────────────────────

def test_a_port_crossing_into_a_peer_draws_one_continuous_line(page):
    """The feature.

    A runs its port across its own two cabinets and then onto B. B is dragged
    1400 px away from its processor position for the show file, so the third
    point can only be right if it went through B's OWN render offset - drawing
    the whole path under A's transform would put it at B's processor position,
    and drawing it under B's would move A's two points instead.
    """
    segs = _run(page, """
        A.flowPattern = 'custom';
        A.customPortPaths = { 1: [{row: 0, col: 0}, {row: 0, col: 1},
                                  {row: 0, col: 0, layerId: 2}] };
        return xp.strokes('#00ff88');
    """)
    assert segs == [
        {'x1': A00[0], 'y1': A00[1], 'x2': A01[0], 'y2': A01[1]},
        {'x1': A01[0], 'y1': A01[1], 'x2': B00_SHOW[0], 'y2': B00_SHOW[1]},
    ], segs
    # Continuous: every segment starts where the last one ended. A path that
    # resolved half its points in one frame and half in another would still
    # produce two segments - it would just have a gap in the middle.
    for i in range(len(segs) - 1):
        assert (segs[i]['x2'], segs[i]['y2']) == (segs[i + 1]['x1'], segs[i + 1]['y1']), segs
    # And emphatically not at B's PROCESSOR position, which is what drawing it
    # inside A's per-layer transform would have produced.
    assert all(s['x2'] != B00_PROC[0] for s in segs), segs


def test_a_crossing_power_circuit_draws_the_same_way(page):
    """Power is a second, independent copy of the same branch - it has to be
    asserted separately or it can drift out of step with data flow."""
    segs = _run(page, """
        A.powerFlowPattern = 'custom';
        A.powerCustomPaths = { 1: [{row: 0, col: 0},
                                   {row: 0, col: 0, layerId: 2}] };
        B.powerFlowPattern = 'custom';
        B.powerCustomPaths = {};
        return xp.strokes('#ff00cc');
    """, view='power')
    assert segs == [
        {'x1': A00[0], 'y1': A00[1], 'x2': B00_SHOW[0], 'y2': B00_SHOW[1]},
    ], segs


def test_a_crossing_path_is_not_drawn_onto_a_member_on_another_canvas(page):
    """_groupDrawnMembers deliberately excludes a member sitting on a different
    effective canvas: that is another workspace, so a cable drawn onto it would
    land at a position that means nothing. The step is dropped, and what is
    left of the path still draws.
    """
    segs = page.evaluate("""() => {
        %s
        A.group_id = 'g1'; B.group_id = 'g1';
        B.canvas_id = 'c2';            // a different workspace entirely
        B.showOffsetX = 2000;
        const group = xp.group([A, B]);
        A.flowPattern = 'custom';
        A.customPortPaths = { 1: [{row: 0, col: 0}, {row: 0, col: 1},
                                  {row: 0, col: 0, layerId: 2}] };
        return xp.withProject([A, B], [group], 'data-flow',
            () => xp.strokes('#00ff88'),
            [xp.canvas('c1'), xp.canvas('c2', {workspace_x: 9000,
                                               show_workspace_x: 9000})]);
    }""" % WALL_JS)

    assert segs == [
        {'x1': A00[0], 'y1': A00[1], 'x2': A01[0], 'y2': A01[1]},
    ], segs


# ── 3. THE COLOUR-CODED POWER FILL ────────────────────────────────────────

def test_a_crossing_circuit_tints_cabinets_in_both_members(page):
    """_powerPanelCircuitMap is per layer, so a circuit that crosses used to
    tint only the half of itself sitting on the layer being drawn - the other
    half stayed plain and read as unwired.

    B is put into custom power mode with no circuits of its own, so nothing but
    A's circuit can be tinting it, and the colour asserted is the one A's
    palette gives circuit 1 - the circuit belongs to A, so the colour does too.
    """
    got = page.evaluate("""() => {
        %s
        A.group_id = 'g1'; B.group_id = 'g1';
        const group = xp.group([A, B]);
        A.powerFlowPattern = 'custom';
        A.powerColorCodedView = true;
        A.powerCustomPaths = { 1: [{row: 0, col: 0},
                                   {row: 0, col: 0, layerId: 2}] };
        B.powerFlowPattern = 'custom';
        B.powerColorCodedView = true;
        B.powerCustomPaths = {};
        return xp.withProject([A, B], [group], 'power', () => ({
            fills: xp.fills(),
            circuitColor: window.canvasRenderer
                .getPowerCircuitColor(window.app.project.layers[0], 1)
                .toLowerCase(),
        }));
    }""" % WALL_JS)

    color = got['circuitColor']
    at = {(f['x'], f['y']): f for f in got['fills'] if f['color'] == color}
    # A's cabinet (0,0) at its own origin, B's at its SHOW origin.
    assert (0, 0) in at, (color, got['fills'])
    assert (2000, 0) in at, (
        "the peer's half of the circuit was not tinted: %r" % (got['fills'],))
    assert at[(0, 0)]['w'] == 128 and at[(0, 0)]['h'] == 128, at
    assert at[(2000, 0)]['w'] == 128 and at[(2000, 0)]['h'] == 128, at
    # Only the two cabinets the circuit actually claimed, not a whole member.
    assert len(at) == 2, at


def test_an_uncrossed_circuit_still_tints_only_its_own_member(page):
    """The other direction. A's circuit stays home, so B's cabinets must be
    left alone - a peer lookup that matched on the unscoped `${row},${col}`
    key would tint B's (0,0) as well, because it cannot tell the two apart.
    """
    got = page.evaluate("""() => {
        %s
        A.group_id = 'g1'; B.group_id = 'g1';
        const group = xp.group([A, B]);
        A.powerFlowPattern = 'custom';
        A.powerColorCodedView = true;
        A.powerCustomPaths = { 1: [{row: 0, col: 0}, {row: 0, col: 1}] };
        B.powerFlowPattern = 'custom';
        B.powerColorCodedView = true;
        B.powerCustomPaths = {};
        return xp.withProject([A, B], [group], 'power', () => ({
            fills: xp.fills(),
            circuitColor: window.canvasRenderer
                .getPowerCircuitColor(window.app.project.layers[0], 1)
                .toLowerCase(),
        }));
    }""" % WALL_JS)

    tinted = {(f['x'], f['y']) for f in got['fills']
              if f['color'] == got['circuitColor']}
    assert (0, 0) in tinted, got['fills']
    assert (128, 0) in tinted, got['fills']
    assert (2000, 0) not in tinted, (
        "member B's own (0,0) was tinted by A's circuit - the peer lookup "
        "matched on an unscoped row,col key: %r" % (got['fills'],))


# ── 4. WHAT THE PORT IS SCORED ON ─────────────────────────────────────────

def test_a_crossing_ports_rectangle_load_is_measured_in_processor_coords(page):
    """NovaStar Armor charges a port for the pixel RECTANGLE enclosing its
    cabinets, and that rectangle is a fact about the processor's raster.

    Panel x/y are already canvas-relative - _build_panels lays each column out
    from layer.offset_x - so two members of one processor canvas share a frame
    and union directly. B is at offset_x = 600 there but showOffsetX = 2000 in
    the show file, which is the whole point of this test: the two frames give
    very different answers and only one of them is the load the processor has
    to push.

        processor:  x 0 .. 728  (A's 0..128 with B's 600..728), y 0 .. 128
                    728 x 128 = 93184
        show:       x 0 .. 2128                              = 272384
    """
    got = _run(page, """
        A.processorType = 'novastar-armor';
        B.processorType = 'novastar-armor';
        A.flowPattern = 'custom';
        A.customPortPaths = { 1: [{row: 0, col: 0},
                                  {row: 0, col: 0, layerId: 2}] };
        const r = window.canvasRenderer;
        const path = A.customPortPaths[1];
        const load = r._crossMemberLoadPanels(A, path);
        return {
            crosses: window.app.pathCrossesMembers(A, path),
            count: load ? load.length : null,
            pixels: r.getPortPixelLoad(A, load),
        };
    """)

    assert got['crosses'] is True, got
    assert got['count'] == 2, got
    assert got['pixels'] == 728 * 128, got
    assert got['pixels'] != 2128 * 128, (
        'the rectangle was unioned in show-look world coords, so the load '
        'follows where the screen was dragged rather than what the processor '
        'has to push')


def test_a_crossing_port_is_not_scored_across_two_processor_rasters(page):
    """Show Look can move a member onto another canvas (show_canvas_id), which
    leaves two members sharing an EFFECTIVE canvas - all a path needs - while
    their panels are laid out against different processor rasters.

    There is no honest rectangle across two rasters and no honest H for the
    (1 - Y/H) derate, so the port is not scored at all. Asserted as the absence
    of the load badge, because "no number" is the behaviour that matters; a
    figure quietly unioned across two rasters would look perfectly plausible.
    """
    got = page.evaluate("""() => {
        %s
        A.group_id = 'g1'; B.group_id = 'g1';
        A.processorType = 'novastar-armor';
        B.processorType = 'novastar-armor';
        B.canvas_id = 'c2';          // a different processor raster...
        B.show_canvas_id = 'c1';     // ...but dragged back onto c1 for the show
        A.flowPattern = 'custom';
        A.showDataFlowPortLoad = true;
        A.customPortPaths = { 1: [{row: 0, col: 0},
                                  {row: 0, col: 0, layerId: 2}] };
        const group = xp.group([A, B]);
        return xp.withProject([A, B], [group], 'data-flow', () => {
            const r = window.canvasRenderer;
            return {
                reachable: window.app.canPathReachLayer(A, B),
                load: r._crossMemberLoadPanels(A, A.customPortPaths[1]),
                texts: xp.texts(),
            };
        }, [xp.canvas('c1'), xp.canvas('c2', {workspace_x: 9000,
                                              show_workspace_x: 9000})]);
    }""" % WALL_JS)

    assert got['reachable'] is True, (
        'the two members share a show canvas, so the path is legal - this test '
        'is about scoring it, not about reaching it')
    assert got['load'] is None, got['load']
    assert not [t for t in got['texts'] if t.endswith('%')], got['texts']


def test_a_scoreable_crossing_port_still_gets_its_badge(page):
    """The companion to the refusal above: when the members DO share a
    processor raster the badge is drawn, so the null case is a real decision
    and not the badge quietly never rendering in the overlay pass at all."""
    texts = _run(page, """
        A.processorType = 'novastar-armor';
        B.processorType = 'novastar-armor';
        A.flowPattern = 'custom';
        A.showDataFlowPortLoad = true;
        A.customPortPaths = { 1: [{row: 0, col: 0},
                                  {row: 0, col: 0, layerId: 2}] };
        return xp.texts();
    """)
    assert [t for t in texts if t.endswith('%')], texts


def test_the_active_port_badge_counts_cabinets_on_both_members(page):
    """"N on port" is what the user is watching while they draw. A cabinet on
    the next member is still wired to the port, so it has to be counted -
    otherwise the number sticks the moment the path leaves its own screen."""
    got = _run(page, """
        A.flowPattern = 'custom';
        A.customPortPaths = { 1: [{row: 0, col: 0}, {row: 0, col: 1},
                                  {row: 0, col: 0, layerId: 2},
                                  {row: 0, col: 1, layerId: 2}] };
        return window.canvasRenderer._getCustomPortPanelCount(A, 1);
    """)
    assert got == 4, got
