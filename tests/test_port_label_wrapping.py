"""Port/circuit labels wrap at spaces instead of inflating their circles.

The port and circuit markers grow to fit their text (labels are never
clipped), so a renamed port like "SR A1" used to blow the circle up until it
swallowed the neighboring cabinets. _layoutCircleLabel now breaks a spaced
label at the spaces ("SR" over "A1") whenever that needs a smaller circle,
keeping the text at the user's label size. These tests pin:

  - a spaced label that overflows its natural circle paints as stacked
    lines, and the full text still reaches the drawing (joined back
    together, the painted pieces are the label);
  - a label that fits, spaced or not, still paints as ONE line;
  - the wrapped circle is smaller than the single line would have needed;
  - the export pass draws the same wrapped label as the screen (one
    renderer, exportMode only changes line-width rounding).

Everything runs against a synthetic in-page project (swapped in and restored
around each evaluate), so the shared e2e server's project is never touched.

Run locally (ALONE - the harness pins one port):
    python -m pytest tests/test_port_label_wrapping.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")


# Shared session fixtures (one Playwright driver + one live server) live in
# conftest.py: browser_name, e2e_server, pw_browser.

@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


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


# Synthetic-project harness, same shape as test_audit_regressions.py's:
# window.app.project is swapped for a hand-built one inside a single evaluate
# and restored in a finally, so nothing leaks into the module-shared page.
HELPERS_JS = """
window.__wr = {
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
            show_numbers: false, number_size: 30,
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

    withProject(layers, viewMode, fn) {
        const app = window.app;
        const r = window.canvasRenderer;
        const saved = {
            project: app.project, currentLayer: app.currentLayer,
            selectedLayerIds: app.selectedLayerIds,
            updateLayers: app.updateLayers, renderLayers: app.renderLayers,
            loadLayerToInputs: app.loadLayerToInputs,
            loadTextLayerToInputs: app.loadTextLayerToInputs,
            saveClientSideProperties: app.saveClientSideProperties,
            activateCanvas: app._activateCanvasForLayer,
            viewMode: r.viewMode, zoom: r.zoom, panX: r.panX, panY: r.panY,
            exportMode: r.exportMode,
        };
        app.updateLayers = () => {};
        app.renderLayers = () => {};
        app.loadLayerToInputs = () => {};
        app.loadTextLayerToInputs = () => {};
        app.saveClientSideProperties = () => {};
        app._activateCanvasForLayer = () => {};
        app.project = {
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
        app.currentLayer = layers[0] || null;
        app.selectedLayerIds = new Set(layers.map(l => l.id));
        r.viewMode = viewMode || 'data-flow';
        r.zoom = 1; r.panX = 0; r.panY = 0;
        try {
            return fn();
        } finally {
            Object.assign(app, {
                project: saved.project, currentLayer: saved.currentLayer,
                selectedLayerIds: saved.selectedLayerIds,
                updateLayers: saved.updateLayers, renderLayers: saved.renderLayers,
                loadLayerToInputs: saved.loadLayerToInputs,
                loadTextLayerToInputs: saved.loadTextLayerToInputs,
                saveClientSideProperties: saved.saveClientSideProperties,
                _activateCanvasForLayer: saved.activateCanvas,
            });
            r.viewMode = saved.viewMode;
            r.zoom = saved.zoom; r.panX = saved.panX; r.panY = saved.panY;
            r.exportMode = saved.exportMode;
            r.render();
        }
    },

    // Every string drawn in one frame with its raw anchor, plus every arc,
    // in draw order. `asExport` runs the frame with exportMode on - the
    // same render the PDF/PNG pipeline rasterizes.
    frame(asExport) {
        const r = window.canvasRenderer, ctx = r.ctx;
        const oT = ctx.fillText, oA = ctx.arc;
        const texts = [], arcs = [];
        ctx.fillText = function (t, x, y, w) {
            texts.push({ t: String(t), x: Math.round(x), y: Math.round(y) });
            return oT.call(ctx, t, x, y, w);
        };
        ctx.arc = function (x, y, rad, a, b, c) {
            arcs.push(Math.round(rad));
            return oA.call(ctx, x, y, rad, a, b, c);
        };
        const prevExport = r.exportMode;
        if (asExport) r.exportMode = true;
        try { r.render(); }
        finally { ctx.fillText = oT; ctx.arc = oA; r.exportMode = prevExport; }
        return { texts, arcs };
    },

    // What the OLD single-line layout would have needed for this label at
    // this size: max(natural radius, textWidth/2 + padding), measured with
    // the same font the renderer uses.
    singleLineRadius(label, fontPx, minRadius, padding) {
        const ctx = window.canvasRenderer.ctx;
        ctx.save();
        ctx.font = 'bold ' + fontPx + 'px ' + (window.app.getProjectFont
            ? window.app.getProjectFont() : 'Arial');
        const w = ctx.measureText(label).width;
        ctx.restore();
        return Math.max(minRadius, w / 2 + padding);
    },
};
"""


def _strings(frame):
    return [t['t'] for t in frame['texts']]


def _data_frame(page, override, as_export=False):
    """One 6x4 Brompton screen (a single port) in Data Flow, port 1 renamed."""
    return page.evaluate("""(cfg) => {
        const wr = window.__wr;
        const s = wr.screen({ id: 1 });
        s.portLabelOverridesPrimary = { 1: cfg.override };
        return wr.withProject([s], 'data-flow', () => wr.frame(cfg.asExport));
    }""", {'override': override, 'asExport': as_export})


# ── data view ─────────────────────────────────────────────────────────────

def test_a_spaced_port_label_that_overflows_stacks_at_the_space(page):
    """"SR A1" paints as "SR" over "A1", not as one wide line."""
    frame = _data_frame(page, 'SR A1')
    texts = frame['texts']
    strings = _strings(frame)
    assert 'SR A1' not in strings, f'the label did not wrap: {strings}'
    assert 'SR' in strings and 'A1' in strings, strings

    # The two pieces are one stacked block: same center, one leading apart
    # (labelSize 30 + 4), top line first. Joined back together they are the
    # label - wrapping changed the layout, never the text.
    sr = texts[strings.index('SR')]
    a1 = texts[strings.index('A1')]
    assert strings.index('A1') == strings.index('SR') + 1, strings
    assert sr['x'] == a1['x'], (sr, a1)
    assert a1['y'] - sr['y'] == 34, (sr, a1)
    assert ' '.join([sr['t'], a1['t']]) == 'SR A1'

    # And the wrap is the point: the circle is smaller than the single line
    # would have forced (natural radius 30 * 1.2, padding max(4, 30 * 0.2)).
    single = page.evaluate(
        "() => window.__wr.singleLineRadius('SR A1', 30, 36, 6)")
    assert single > 36, 'test premise broken: the label no longer overflows'
    assert frame['arcs'], 'no port circles drawn'
    assert max(frame['arcs']) < single, (frame['arcs'], single)


def test_a_fitting_spaced_label_stays_one_line(page):
    """A space alone is no reason to wrap - "A B" fits its circle."""
    strings = _strings(_data_frame(page, 'A B'))
    assert 'A B' in strings, strings
    assert 'A' not in strings and 'B' not in strings, strings


def test_the_default_labels_are_untouched(page):
    """No spaces, no wrap: the stock P#/R# labels paint exactly as before."""
    frame = page.evaluate("""() => {
        const wr = window.__wr;
        return wr.withProject([wr.screen({ id: 1 })], 'data-flow',
                              () => wr.frame(false));
    }""")
    strings = _strings(frame)
    assert 'P1' in strings and 'R1' in strings, strings
    # Both circles at the natural radius - nothing grew, nothing shrank.
    assert frame['arcs'] == [36, 36], frame['arcs']


# ── power view ────────────────────────────────────────────────────────────

def test_a_power_circuit_label_wraps_the_same_way(page):
    """Same helper, second view: circuit 1 renamed "SR A1" stacks too."""
    frame = page.evaluate("""() => {
        const wr = window.__wr;
        const s = wr.screen({ id: 1 });
        s.powerLabelSize = 24;
        s.powerLabelOverrides = { 1: 'SR A1' };
        return wr.withProject([s], 'power', () => wr.frame(false));
    }""")
    strings = _strings(frame)
    assert 'SR A1' not in strings, f'the circuit label did not wrap: {strings}'
    sr = strings.index('SR')
    assert strings[sr + 1] == 'A1', strings
    # The untouched circuit keeps its stock single-line label.
    assert 'S1-2' in strings, strings


# ── export pass ───────────────────────────────────────────────────────────

def test_the_export_pass_draws_the_wrapped_label_too(page):
    """The PDF pipeline rasterizes this same render, so what it captures
    here is what the exported map shows."""
    strings = _strings(_data_frame(page, 'SR A1', as_export=True))
    assert 'SR A1' not in strings, f'export drew the unwrapped label: {strings}'
    sr = strings.index('SR')
    assert strings[sr + 1] == 'A1', strings
