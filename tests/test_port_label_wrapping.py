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
    renderer, exportMode only changes line-width rounding);
  - an UNSPACED label breaks instead at a hyphen (the hyphen staying on
    the upper line the way a hyphenated word breaks) or where a run of
    letters meets the digit after it ("SR" over "3-5"), only when that
    stack needs a smaller circle - "also SR3-5 can be stacked like data if
    it fits better" and, on how: "what about / SR / 3-5" (2026-09-07). A
    digit followed by a letter is no seam ("3A" stays whole). Spaces win
    when the label has any ("SR A-1" is "SR" over "A-1", never broken at
    the hyphen), and the binder's printer pass draws the same lines as the
    screen.

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
    // same render the PDF/PNG pipeline rasterizes; `asPrinter` with
    // printerMode on - the binder's ink-on-paper pass.
    frame(asExport, asPrinter) {
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
        const prevExport = r.exportMode, prevPrinter = r.printerMode;
        if (asExport) r.exportMode = true;
        if (asPrinter) r.printerMode = true;
        try { r.render(); }
        finally {
            ctx.fillText = oT; ctx.arc = oA;
            r.exportMode = prevExport; r.printerMode = prevPrinter;
        }
        return { texts, arcs };
    },

    // _layoutCircleLabel straight from the helper, in the data label's
    // font, for the cases a frame cannot reach (a label that FITS its
    // natural disc: the data view's disc is 1.2 x labelSize, which no
    // five-character label fits at any size).
    layout(label, fontPx, minRadius, padding) {
        const r = window.canvasRenderer, ctx = r.ctx;
        ctx.save();
        ctx.font = 'bold ' + fontPx + 'px ' + (window.app.getProjectFont
            ? window.app.getProjectFont() : 'Arial');
        try { return r._layoutCircleLabel(label, fontPx, minRadius, padding); }
        finally { ctx.restore(); }
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


def _data_frame(page, override, as_export=False, as_printer=False):
    """One 6x4 Brompton screen (a single port) in Data Flow, port 1 renamed."""
    return page.evaluate("""(cfg) => {
        const wr = window.__wr;
        const s = wr.screen({ id: 1 });
        s.portLabelOverridesPrimary = { 1: cfg.override };
        return wr.withProject([s], 'data-flow',
                              () => wr.frame(cfg.asExport, cfg.asPrinter));
    }""", {'override': override, 'asExport': as_export,
           'asPrinter': as_printer})


def _power_frame(page, override, as_export=False, as_printer=False):
    """The same screen in Power, circuit 1 renamed, labels at 24px."""
    return page.evaluate("""(cfg) => {
        const wr = window.__wr;
        const s = wr.screen({ id: 1 });
        s.powerLabelSize = 24;
        s.powerLabelOverrides = { 1: cfg.override };
        return wr.withProject([s], 'power',
                              () => wr.frame(cfg.asExport, cfg.asPrinter));
    }""", {'override': override, 'asExport': as_export,
           'asPrinter': as_printer})


def _stack_of(frame, first):
    """The painted lines of the stacked block that starts with `first`:
    consecutive strings sharing its x, one leading apart."""
    texts = frame['texts']
    i = [t['t'] for t in texts].index(first)
    lines = [texts[i]]
    for t in texts[i + 1:]:
        if t['x'] == lines[-1]['x'] and 0 < t['y'] - lines[-1]['y'] <= 40:
            lines.append(t)
        else:
            break
    return [t['t'] for t in lines]


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


# ── hyphen breaks (unspaced labels) ───────────────────────────────────────

def test_an_unspaced_label_breaks_at_its_letter_digit_seam_when_the_stack_is_smaller(page):
    """"SR3-12" paints as "SR" over "3-12": the side over its number. Its
    pieces are "SR" | "3-" | "12", and the balanced split lands on the
    letter-digit seam - the hyphen break ("SR3-" over "12") would leave a
    wider upper line and a bigger disc. The joined lines are the label."""
    frame = _data_frame(page, 'SR3-12')
    strings = _strings(frame)
    assert 'SR3-12' not in strings, f'the label did not break: {strings}'
    assert _stack_of(frame, 'SR') == ['SR', '3-12'], strings
    assert ''.join(_stack_of(frame, 'SR')) == 'SR3-12'
    assert 'SR3-' not in strings and '12' not in strings, strings

    # The stack is only there because it shrank the disc.
    single = page.evaluate(
        "() => window.__wr.singleLineRadius('SR3-12', 30, 36, 6)")
    assert single > 36, 'test premise broken: the label no longer overflows'
    assert max(frame['arcs']) < single, (frame['arcs'], single)


def test_the_ruling_label_sr3_5_stacks_as_its_side_over_its_number(page):
    """"SR3-5" is the user's example and the ruling on how it stacks is
    "what about / SR / 3-5": the run of letters over the number. The
    pieces are "SR" | "3-" | "5"; the two-line balanced split is "SR"
    over "3-5" and, unlike the old hyphen-only "SR3-" over "5", that
    block needs a SMALLER disc than the one line (measured in the data
    label's font at 30px: about 44.7 against the line's 48.5 - the
    numbers are computed here from the renderer's own widths, not
    pinned). Three lines ("SR" / "3-" / "5") is a taller block and loses."""
    frame = _data_frame(page, 'SR3-5')
    strings = _strings(frame)
    assert 'SR3-5' not in strings, f'the label did not stack: {strings}'
    assert _stack_of(frame, 'SR') == ['SR', '3-5'], strings
    assert ''.join(_stack_of(frame, 'SR')) == 'SR3-5'
    assert 'SR3-' not in strings and '5' not in strings, strings

    # The premise: the line overflows its natural disc (30 * 1.2, padding
    # max(4, 30 * 0.2)), so the stack was weighed against it on size.
    single = page.evaluate(
        "() => window.__wr.singleLineRadius('SR3-5', 30, 36, 6)")
    assert single > 36, 'test premise broken: the label no longer overflows'
    radii = page.evaluate("""() => {
        const ctx = window.canvasRenderer.ctx;
        ctx.save();
        ctx.font = 'bold 30px ' + window.app.getProjectFont();
        const w = (s) => ctx.measureText(s).width;
        // The helper's own radius model: each line a 30px-tall box on a
        // 34px leading, the farthest box corner sets the radius, plus the
        // 6px padding.
        const radiusOf = (lines) => {
            let r = 0;
            lines.forEach((l, i) => {
                const yEdge = Math.abs(i - (lines.length - 1) / 2) * 34 + 15;
                r = Math.max(r, Math.hypot(w(l) / 2, yEdge));
            });
            return Math.max(36, r + 6);
        };
        const out = {
            ruling: radiusOf(['SR', '3-5']),
            hyphenOnly: radiusOf(['SR3-', '5']),
            three: radiusOf(['SR', '3-', '5']),
        };
        ctx.restore();
        return out;
    }""")
    assert radii['ruling'] < single - 0.5, (radii, single)
    assert radii['hyphenOnly'] > single, (radii, single)
    assert radii['three'] > radii['ruling'], radii
    # And the drawn disc is the ruling's, not the line's.
    assert max(frame['arcs']) == round(radii['ruling']), (frame['arcs'], radii)
    assert max(frame['arcs']) < single, (frame['arcs'], single)


def test_an_unspaced_label_that_fits_its_disc_stays_one_line(page):
    """A hyphen alone is no reason to wrap: "SR3-5" inside a disc that
    already holds it paints as one line at the natural radius."""
    layout = page.evaluate(
        "() => window.__wr.layout('SR3-5', 14, 36, 4)")
    assert layout['lines'] == ['SR3-5'], layout
    assert layout['radius'] == 36, layout


def test_spaces_win_over_hyphens(page):
    """"SR A-1" still breaks only at its space: "SR" over "A-1", the
    hyphenated token whole."""
    frame = _data_frame(page, 'SR A-1')
    strings = _strings(frame)
    assert 'SR A-1' not in strings, strings
    assert _stack_of(frame, 'SR') == ['SR', 'A-1'], strings
    assert 'A-' not in strings and '1' not in strings, strings


def test_a_label_with_two_hyphens_breaks_at_one_of_them(page):
    """"S1-12-3" stacks in two lines at whichever seam the balanced split
    picks; joined back together the lines are the label. Its pieces are
    "S" | "1-" | "12-" | "3", so the lone letter "S" is a legal line on
    its own - but only if it wins the circle rule, and here it does not:
    "S" over "1-12-3" is a wide lower line and a bigger disc than "S1-"
    over "12-3", which is where the split lands. Nothing special-cases
    the single letter; the geometry decides."""
    frame = _data_frame(page, 'S1-12-3')
    strings = _strings(frame)
    assert 'S1-12-3' not in strings, strings
    upper = next(t for t in strings if t.startswith('S') and t != 'S1-12-3')
    lines = _stack_of(frame, upper)
    assert len(lines) == 2, lines
    assert not lines[1].startswith('-'), lines
    assert ''.join(lines) == 'S1-12-3', lines
    assert lines == ['S1-', '12-3'], lines
    # (The screen's own name paints as "S" too, so the losing split is
    # pinned by its lower line, not the letter.)
    assert '1-12-3' not in strings, strings


def test_the_seam_cutter_cuts_at_hyphens_and_letter_digit_seams(page):
    """The break units of an unspaced label are cut at two kinds of seam:
    after a hyphen between two non-empty parts (the hyphen stays on the
    piece before it) and between a letter and the digit right after it.
    A digit followed by a letter is NOT a seam ("3A" stays whole), nothing
    cuts inside a run of one class, and a leading, trailing or doubled
    hyphen is part of the name. Joined with nothing, the pieces are the
    label exactly."""
    labels = ['SR3-5', 'SL12-3', '3A', 'A3B4', 'S1-12-3', 'SR3-12',
              '-5', 'SR-', 'A--B', 'P1', 'ABC', '123']
    units = page.evaluate("""(labels) => {
        const r = window.canvasRenderer;
        return labels.map(l => r._unspacedUnits(l));
    }""", labels)
    assert units == [
        ['SR', '3-', '5'],
        ['SL', '12-', '3'],
        ['3A'],
        ['A', '3B', '4'],
        ['S', '1-', '12-', '3'],
        ['SR', '3-', '12'],
        ['-5'], ['SR-'], ['A--B'],
        ['P', '1'],
        ['ABC'], ['123'],
    ], units
    for label, pieces in zip(labels, units):
        assert ''.join(pieces) == label, (label, pieces)
        assert all(pieces), (label, pieces)


# ── power view + binder ───────────────────────────────────────────────────

def test_a_power_circuit_label_breaks_at_its_seam_too(page):
    """Same helper, second view: circuit 1 renamed "SR3-12" stacks as
    "SR" over "3-12", and the stock "S1-2" next to it stays one line
    (it fits its disc, so its "S" | "1-" | "2" pieces never come up)."""
    frame = _power_frame(page, 'SR3-12')
    strings = _strings(frame)
    assert 'SR3-12' not in strings, f'the circuit label did not break: {strings}'
    assert _stack_of(frame, 'SR') == ['SR', '3-12'], strings
    assert 'S1-2' in strings, strings
    assert 'S1-' not in strings and '1-2' not in strings, strings


def test_the_export_and_printer_passes_draw_the_same_lines(page):
    """The binder rasterizes this same render with printerMode on, the
    PDF/PNG export with exportMode on: both paint the label in the exact
    lines the screen does - "SR" over "3-12", "SR" over "3-5", and the
    one-line "SR3-5" of a disc that already holds it never appears."""
    ours = {'SR', '3-12', '3-5', 'SR3-', '12', '5', 'SR3-12', 'SR3-5'}
    for label, stack in (('SR3-12', ['SR', '3-12']), ('SR3-5', ['SR', '3-5'])):
        screen = _strings(_data_frame(page, label))
        export = _strings(_data_frame(page, label, as_export=True))
        printer = _strings(_data_frame(page, label, as_printer=True))
        want = [t for t in screen if t in ours]
        assert want == stack, (label, screen)
        assert [t for t in export if t in ours] == want, (label, export)
        assert [t for t in printer if t in ours] == want, (label, printer)
