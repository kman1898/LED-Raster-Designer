"""In custom data / power mode, a drag that starts OUTSIDE the screen is a
layer marquee again.

Reported against v0.11.1: "while you're in custom data (or power) mode, the
ordinary layer marquee - drag a rubber-band on empty canvas to select multiple
screens - is dead."

The cause is two branches in handleMouseDown that armed the PANEL marquee with
no position test whatsoever:

    if (isCustomFlow(currentLayer)) { isSelectingPanels = true; ...; return }
    if (isCustomPower(currentLayer)) { isSelectingPanels = true; ...; return }

Every press on the canvas hit one of those and returned, so the layer marquee
further down was unreachable for as long as custom mode was on. Pixel Map's
panel drag - the same gesture, one view over - has always hit-tested first and
fallen through when the press missed, which is why only custom mode showed it.

Pinned here:

* Inside the screen that owns the path, the press still draws. This is the
  half that always worked and must not move.
* Inside a group PEER the path can reach, the press still draws - a wall is
  drawn across its members, so "outside the current layer" is not the test.
* On empty canvas, the press starts a layer marquee and sweeps up the screens
  it crosses, in both custom views.
* Falling through drops a stale panel selection, the way Pixel Map does.

The assertions are on WHICH marquee armed (isSelectingPanels vs
isSelectingLayers), read mid-drag while the button is still down. That is the
branch under test; the selection each marquee produces afterwards is separate
machinery with its own tests.

Run locally:
    python -m pytest tests/test_custom_mode_layer_marquee.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project exactly as this module found it
    (see conftest.server_project_guard)."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    yield pg
    context.close()


# Two 2x2 screens of 128px cabinets - 256x256 world units each - far enough
# apart that a point between them is unambiguously empty canvas.
LAYER_OFFSETS = [(0, 0), (600, 0)]

RESET_JS = """async ([offsets, view]) => {
    const app = window.app, r = window.canvasRenderer;
    // The live server is shared with the other browser test files; build our
    // screens from scratch through the real add endpoint.
    let project = await (await fetch('/api/project')).json();
    project.layers = [];
    project.groups = [];
    await fetch('/api/project', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(project),
    });
    for (let i = 0; i < offsets.length; i++) {
        await fetch('/api/layer/add', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                name: 'Marquee' + (i + 1),
                columns: 2, rows: 2, cabinet_width: 128, cabinet_height: 128,
                offset_x: offsets[i][0], offset_y: offsets[i][1],
            }),
        });
    }
    app.project = await (await fetch('/api/project')).json();
    app.dedupeProjectLayers('custom_marquee_test_reset');
    const screens = app.project.layers.filter(
        l => (l.type || 'screen') === 'screen').slice(0, offsets.length);

    // Put BOTH patterns on custom. A screen in a group is always in this
    // state - the flow pattern is shared across members - so it is the state
    // worth testing, and it also proves the view guard is doing the choosing.
    screens.forEach(l => {
        l.flowPattern = 'custom';
        l.powerFlowPattern = 'custom';
        app.ensureCustomFlowState(l);
        app.ensureCustomPowerState(l);
    });
    app.currentLayer = screens[0];
    app.selectedLayerIds = new Set([screens[0].id]);
    app.lastSelectedLayerId = screens[0].id;
    app.selectionAnchorLayerId = screens[0].id;
    if (app.customSelection) app.customSelection.clear();
    if (app.powerCustomSelection) app.powerCustomSelection.clear();
    if (app.pixelMapSelection) app.pixelMapSelection.clear();
    // Deterministic camera so world -> client math is exact. The pan is
    // generous on purpose: the empty-canvas presses below sit at NEGATIVE
    // world coordinates, and they have to land inside the canvas ELEMENT or
    // no mousedown fires at all and every assertion here reads as "nothing
    // armed" - which looks exactly like the bug under test.
    r.viewMode = view;
    r.zoom = 0.5; r.panX = 200; r.panY = 200;
    if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
    app.renderLayers();
    r.render();
    return {
        ids: screens.map(l => l.id),
        isCustomFlow: app.isCustomFlow(screens[0]),
        isCustomPower: app.isCustomPower(screens[0]),
        view: r.viewMode,
    };
}"""


def reset_project(page, view):
    state = page.evaluate(RESET_JS, [LAYER_OFFSETS, view])
    page.wait_for_timeout(400)
    assert len(state['ids']) == len(LAYER_OFFSETS), state
    return state


def world_to_client(page, wx, wy):
    pt = page.evaluate("""([wx, wy]) => {
        const r = window.canvasRenderer;
        const rect = r.canvas.getBoundingClientRect();
        return { x: rect.left + wx * r.zoom + r.panX,
                 y: rect.top + wy * r.zoom + r.panY };
    }""", [wx, wy])
    return pt['x'], pt['y']


# Centre of a test screen, and a point in the gap between the two of them.
def screen_center(index):
    return LAYER_OFFSETS[index][0] + 128, LAYER_OFFSETS[index][1] + 128


EMPTY_START = (-120, 420)      # below and left of everything
EMPTY_END = (900, 500)         # still empty, a long way across


def drag_and_peek(page, start_world, end_world):
    """Press, move, and read the renderer WHILE THE BUTTON IS DOWN.

    Which marquee is armed is only observable mid-drag; both flags are cleared
    on mouse-up. The selection left behind afterwards is reported too, for the
    tests that care what the layer marquee actually swept.
    """
    sx, sy = world_to_client(page, *start_world)
    ex, ey = world_to_client(page, *end_world)
    page.mouse.move(sx, sy)
    page.mouse.down()
    page.mouse.move((sx + ex) / 2, (sy + ey) / 2, steps=4)
    page.mouse.move(ex, ey, steps=4)
    armed = page.evaluate("""() => {
        const r = window.canvasRenderer, app = window.app;
        return {
            panels: !!r.isSelectingPanels,
            layers: !!r.isSelectingLayers,
            current: app.currentLayer ? app.currentLayer.id : null,
        };
    }""")
    page.mouse.up()
    page.wait_for_timeout(200)
    after = page.evaluate("""() => {
        const app = window.app;
        return {
            selected: [...app.selectedLayerIds].sort((a, b) => a - b),
            custom: app.customSelection ? app.customSelection.size : 0,
            power: app.powerCustomSelection ? app.powerCustomSelection.size : 0,
        };
    }""")
    return armed, after


# ── the premise ───────────────────────────────────────────────────────────

@pytest.mark.parametrize('view', ['data-flow', 'power'])
def test_the_screen_really_is_in_custom_mode(page, view):
    """If the setup stopped producing a custom-mode screen, everything below
    would pass for the wrong reason - nothing would be armed either way."""
    state = reset_project(page, view)
    assert state['isCustomFlow'] is True
    assert state['isCustomPower'] is True
    assert state['view'] == view


# ── the half that always worked, and must not move ───────────────────────

@pytest.mark.parametrize('view', ['data-flow', 'power'])
def test_a_drag_inside_the_screen_still_draws(page, view):
    reset_project(page, view)
    cx, cy = screen_center(0)
    armed, _ = drag_and_peek(page, (cx - 60, cy - 60), (cx + 60, cy + 60))
    assert armed['panels'] is True, (
        "a drag inside the screen no longer draws the path - the scope guard "
        "is rejecting presses it should accept")
    assert armed['layers'] is False, "drawing inside the screen armed the layer marquee"


@pytest.mark.parametrize('view', ['data-flow', 'power'])
def test_a_drag_inside_a_group_peer_still_draws(page, view):
    """A wall is drawn across its members, so "not the current layer" is not
    the test - a peer the path can reach is in scope too."""
    state = reset_project(page, view)
    page.evaluate("""async (ids) => {
        const app = window.app;
        app.project.groups = [{ id: 'g_marq', name: 'Marquee Wall', layer_ids: ids }];
        app.project.layers.forEach(l => { if (ids.includes(l.id)) l.group_id = 'g_marq'; });
        await fetch('/api/project', {
            method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(app.project),
        });
        app.renderLayers();
        window.canvasRenderer.render();
    }""", state['ids'])
    page.wait_for_timeout(250)

    cx, cy = screen_center(1)                      # the PEER, not the owner
    armed, _ = drag_and_peek(page, (cx - 60, cy - 60), (cx + 60, cy + 60))
    assert armed['panels'] is True, (
        "a drag over a group peer stopped drawing - the path can reach it, so "
        "it is part of the same gesture")
    assert armed['current'] == state['ids'][0], (
        "drawing over a peer moved currentLayer onto the peer - the path would "
        "change owner mid-draw")


# ── the reported bug ─────────────────────────────────────────────────────

@pytest.mark.parametrize('view', ['data-flow', 'power'])
def test_a_drag_on_empty_canvas_is_a_layer_marquee(page, view):
    """The bug: this press armed the panel marquee and returned, so the layer
    marquee was unreachable for the whole time custom mode was on."""
    reset_project(page, view)
    armed, _ = drag_and_peek(page, EMPTY_START, EMPTY_END)
    assert armed['layers'] is True, (
        "a drag starting on empty canvas did not start a layer marquee - "
        "multi-select is dead while custom mode is on")
    assert armed['panels'] is False, (
        "a drag starting on empty canvas armed the PANEL marquee - it is "
        "drawing a port with a rectangle that begins nowhere near a cabinet")


@pytest.mark.parametrize('view', ['data-flow', 'power'])
def test_the_empty_canvas_marquee_selects_the_screens_it_sweeps(page, view):
    """Arming the right marquee is not enough on its own - it has to end with
    both screens selected, which is the thing the user was trying to do."""
    state = reset_project(page, view)
    # A band from above-left of screen 1 across to the far side of screen 2.
    _, after = drag_and_peek(page, (-120, -120), (1000, 300))
    assert after['selected'] == sorted(state['ids']), (
        f"marquee over both screens selected {after['selected']}, "
        f"expected {sorted(state['ids'])}")


@pytest.mark.parametrize('view,field', [('data-flow', 'custom'), ('power', 'power')])
def test_falling_through_drops_a_stale_panel_selection(page, view, field):
    """Clicking away is how you drop a selection everywhere else in the app.
    Leaving the panels lit made the next click inside the screen extend a
    selection the user thought they had already dropped."""
    reset_project(page, view)
    cx, cy = screen_center(0)
    drag_and_peek(page, (cx - 60, cy - 60), (cx + 60, cy + 60))   # select panels
    before = page.evaluate("""(f) => {
        const app = window.app;
        return f === 'custom' ? app.customSelection.size : app.powerCustomSelection.size;
    }""", field)
    assert before > 0, (
        "the drag inside the screen selected no panels, so this test could "
        "not tell a working clear from a no-op")

    _, after = drag_and_peek(page, EMPTY_START, EMPTY_END)
    assert after[field] == 0, (
        f"{after[field]} panels stayed selected after clicking away from the "
        "screen entirely")
