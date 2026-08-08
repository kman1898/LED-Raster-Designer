"""Issue #111 - arrow keys walk the cable backwards in Rear view.

Reported by tomierna against 0.10.8.1:

    Create a layer, go to the data or power tabs, click the "Rear" button
    under "View". Choose "Enable Custom Mode". Click the first tile to start
    the port/circuit. Note that right button moves left and left button
    moves right.

The keys were never wrong. Rear perspective draws the canvas through
ctx.scale(-1, 1), so world +X appears on the viewer's LEFT - and the step was
computed in unmirrored world space. Pressing Right therefore added the cabinet
the user saw to the left of the one they were on.

Vertical is unaffected: the mirror is left-to-right only. That asymmetry is
asserted here too, because "just flip both" would be an equally plausible and
completely wrong fix.

Run locally:
    python -m pytest tests/test_rear_view_arrows.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    yield pg
    context.close()


SETUP_JS = """([view, perspective]) => {
    const app = window.app;
    const r = window.canvasRenderer;
    // One 4x3 screen on one canvas, in custom mode for the view under test.
    const layer = {
        id: 501, name: 'Rear Test', type: 'screen', visible: true,
        canvas_id: 'c1', columns: 4, rows: 3,
        cabinet_width: 128, cabinet_height: 128,
        panel_width_mm: 500, panel_height_mm: 500,
        offset_x: 0, offset_y: 0, rotation: 0,
        processorType: 'brompton', bitDepth: 8, frameRate: 60,
        color1: {r: 64, g: 70, b: 128}, color2: {r: 149, g: 156, b: 184},
        flowPattern: 'custom', powerFlowPattern: 'custom',
        customPortPaths: {}, customPortIndex: 1,
        powerCustomPaths: {}, powerCustomIndex: 1,
        panels: [],
    };
    for (let row = 0; row < layer.rows; row++) {
        for (let col = 0; col < layer.columns; col++) {
            layer.panels.push({
                id: row * layer.columns + col + 1,
                number: row * layer.columns + col + 1,
                row, col,
                x: col * layer.cabinet_width, y: row * layer.cabinet_height,
                width: layer.cabinet_width, height: layer.cabinet_height,
                hidden: false, blank: false, halfTile: 'none',
                is_color1: (row + col) % 2 === 0,
            });
        }
    }
    window.__rearSaved = {
        project: app.project, currentLayer: app.currentLayer,
        selected: app.selectedLayerIds, viewMode: r.viewMode,
        updateLayers: app.updateLayers, saveClientSideProperties: app.saveClientSideProperties,
        renderLayers: app.renderLayers,
    };
    app.updateLayers = () => {};
    app.saveClientSideProperties = () => {};
    app.renderLayers = () => {};
    app.project = {
        layers: [layer], groups: [],
        canvases: [{
            id: 'c1', name: 'Canvas 1',
            workspace_x: 0, workspace_y: 0,
            show_workspace_x: 0, show_workspace_y: 0,
            raster_width: 4096, raster_height: 4096,
            show_raster_width: 4096, show_raster_height: 4096,
            color: '#ff0000', visible: true,
            data_flow_perspective: perspective,
            power_perspective: perspective,
        }],
        active_canvas_id: 'c1',
    };
    app.currentLayer = layer;
    app.selectedLayerIds = new Set([layer.id]);
    r.viewMode = view;
    // Start the cable on the MIDDLE cabinet so there is room to step either
    // way without hitting an edge and confusing a real bug with a swallow.
    const startKey = view === 'power' ? 'powerCustomPaths' : 'customPortPaths';
    layer[startKey][1] = [{row: 1, col: 1}];
    return {mirrored: r._isCanvasMirrored(app.project.canvases[0])};
}"""

RESTORE_JS = """() => {
    const app = window.app, r = window.canvasRenderer, s = window.__rearSaved;
    if (!s) return;
    app.project = s.project; app.currentLayer = s.currentLayer;
    app.selectedLayerIds = s.selected; r.viewMode = s.viewMode;
    app.updateLayers = s.updateLayers;
    app.saveClientSideProperties = s.saveClientSideProperties;
    app.renderLayers = s.renderLayers;
    delete window.__rearSaved;
}"""


def _press(page, view, perspective, code):
    """Set up, press one arrow, return the cabinet it landed on."""
    state = page.evaluate(SETUP_JS, [view, perspective])
    try:
        page.evaluate("(code) => window.app.handleCustomArrowKey({code})", code)
        page.wait_for_timeout(250)
        landed = page.evaluate("""(view) => {
            const l = window.app.project.layers[0];
            const key = view === 'power' ? 'powerCustomPaths' : 'customPortPaths';
            const path = l[key][1] || [];
            const step = path[path.length - 1];
            return {col: step.col, row: step.row, length: path.length};
        }""", view)
    finally:
        page.evaluate(RESTORE_JS)
    return state, landed


@pytest.mark.parametrize('view', ['data-flow', 'power'])
def test_rear_view_is_actually_mirrored(page, view):
    """Guard the premise: if Rear ever stops mirroring, the tests below would
    pass for the wrong reason."""
    state, _ = _press(page, view, 'back', 'ArrowRight')
    assert state['mirrored'] is True


@pytest.mark.parametrize('view', ['data-flow', 'power'])
def test_right_goes_right_on_screen_in_rear_view(page, view):
    """The reported bug. Start on col 1; the cabinet to the VIEWER's right is
    the one at a lower world x, because the canvas is mirrored."""
    _, landed = _press(page, view, 'back', 'ArrowRight')
    assert landed['length'] == 2, 'the key was swallowed'
    assert landed['col'] == 0, (
        f"ArrowRight in Rear view added col {landed['col']}; the cabinet on "
        'the viewer\'s right is col 0 because the canvas is mirrored')


@pytest.mark.parametrize('view', ['data-flow', 'power'])
def test_left_goes_left_on_screen_in_rear_view(page, view):
    _, landed = _press(page, view, 'back', 'ArrowLeft')
    assert landed['length'] == 2, 'the key was swallowed'
    assert landed['col'] == 2, (
        f"ArrowLeft in Rear view added col {landed['col']}; expected col 2")


@pytest.mark.parametrize('view', ['data-flow', 'power'])
@pytest.mark.parametrize('code,expected_row', [('ArrowUp', 0), ('ArrowDown', 2)])
def test_vertical_is_not_flipped_in_rear_view(page, view, code, expected_row):
    """The mirror is left-to-right ONLY. Flipping both axes would be an
    equally plausible fix and completely wrong."""
    _, landed = _press(page, view, 'back', code)
    assert landed['row'] == expected_row, (
        f'{code} in Rear view moved to row {landed["row"]}, expected '
        f'{expected_row} - vertical must not be mirrored')


# ── Front view must be untouched ──────────────────────────────────────────

@pytest.mark.parametrize('view', ['data-flow', 'power'])
def test_front_view_arrows_are_unchanged(page, view):
    """The regression guard. Front is not mirrored, so every direction steps
    exactly as it always did."""
    _, right = _press(page, view, 'front', 'ArrowRight')
    assert right['col'] == 2, right
    _, left = _press(page, view, 'front', 'ArrowLeft')
    assert left['col'] == 0, left
    _, up = _press(page, view, 'front', 'ArrowUp')
    assert up['row'] == 0, up
    _, down = _press(page, view, 'front', 'ArrowDown')
    assert down['row'] == 2, down
