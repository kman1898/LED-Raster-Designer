"""Cmd/Ctrl+click on the CANVAS toggles a layer in/out of the multi-selection.

The sidebar has had Ctrl-click multi-select for a while (toggleLayerSelection,
writing app.selectedLayerIds); the canvas only ever replaced the selection.
These tests drive REAL mouse clicks (Playwright page.mouse with the Control
key held) against the live canvas element and assert on the ONE selection
model everything downstream reads: app.selectedLayerIds, mirrored by the
sidebar's .layer-item.active rows.

Pinned behaviours:

* Ctrl/Cmd+click on an unselected layer ADDS it (selection grows, sidebar
  shows both rows active).
* Ctrl/Cmd+click on a selected layer REMOVES it.
* A PLAIN click still replaces the whole multi-selection with the clicked
  layer - exactly the pre-existing behaviour.
* Ctrl/Cmd+click on empty canvas keeps the selection (plain-click semantics
  of "clear" do not apply to the toggle gesture).
* Groups: the toggle unit is whatever a plain click would select - the WHOLE
  group when the clicked layer is a grouped member. Toggling a selected
  group's member takes the whole group out.
* Selection is view state: none of this records history (no saveState).

Run locally:
    python -m pytest tests/test_canvas_multiselect.py -v --browser chromium
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
    """One long-lived page; each test resets to a known project first."""
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)  # socket connect + app init
    yield pg
    context.close()


# ── helpers ───────────────────────────────────────────────────────────────

# Three 2x2 screens of 128px cabinets (256x256 world units each), spaced
# well apart so a click at a screen's centre can only hit that screen.
# Offsets are given to the real add endpoint so panel x/y are built to match.
LAYER_OFFSETS = [(0, 0), (600, 0), (1200, 0)]

# The app accepts either metaKey or ctrlKey. The tests must pick per platform:
# on macOS, Chromium synthesises Ctrl+left-click as a RIGHT click (contextmenu),
# so only Cmd exercises the toggle path there; everywhere else Ctrl is the key
# users actually press.
MODIFIER = "Meta" if sys.platform == "darwin" else "Control"

RESET_JS = """async (offsets) => {
    const app = window.app;
    const r = window.canvasRenderer;
    // The live server is shared with every other browser test file; clear
    // whatever they left behind and build exactly our screens through the
    // real add endpoint so panels/offsets are the real article.
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
                name: 'MultiSel' + (i + 1),
                columns: 2, rows: 2, cabinet_width: 128, cabinet_height: 128,
                offset_x: offsets[i][0], offset_y: offsets[i][1],
            }),
        });
    }
    app.project = await (await fetch('/api/project')).json();
    app.dedupeProjectLayers('canvas_multiselect_test_reset');
    const screens = app.project.layers.filter(
        l => (l.type || 'screen') === 'screen').slice(0, offsets.length);
    app.currentLayer = screens[0];
    app.selectedLayerIds = new Set([screens[0].id]);
    app.lastSelectedLayerId = screens[0].id;
    app.selectionAnchorLayerId = screens[0].id;
    if (app.pixelMapSelection) app.pixelMapSelection.clear();
    // Deterministic camera so world -> client coordinate math is exact.
    r.viewMode = 'pixel-map';
    r.zoom = 0.5; r.panX = 40; r.panY = 40;
    if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
    app.renderLayers();
    r.render();
    return screens.map(l => l.id);
}"""


def reset_project(page):
    ids = page.evaluate(RESET_JS, LAYER_OFFSETS)
    page.wait_for_timeout(500)
    assert len(ids) == len(LAYER_OFFSETS), ids
    return ids


def layer_center_client(page, index):
    """Client (viewport) coords of the centre of the index-th test screen."""
    wx = LAYER_OFFSETS[index][0] + 128
    wy = LAYER_OFFSETS[index][1] + 128
    return world_to_client(page, wx, wy)


def world_to_client(page, wx, wy):
    pt = page.evaluate("""([wx, wy]) => {
        const r = window.canvasRenderer;
        const rect = r.canvas.getBoundingClientRect();
        return { x: rect.left + wx * r.zoom + r.panX,
                 y: rect.top + wy * r.zoom + r.panY };
    }""", [wx, wy])
    return pt['x'], pt['y']


def click_layer(page, index, modifier=None):
    x, y = layer_center_client(page, index)
    if modifier:
        page.keyboard.down(modifier)
    try:
        page.mouse.click(x, y)
    finally:
        if modifier:
            page.keyboard.up(modifier)
    page.wait_for_timeout(150)


def selection_state(page):
    """The one model everything reads, plus the sidebar's mirror of it."""
    return page.evaluate("""() => {
        const app = window.app;
        const sidebar = [...document.querySelectorAll('.layer-item.active')]
            .map(el => parseInt(el.dataset.layerId, 10)).sort((a, b) => a - b);
        return {
            selected: [...app.selectedLayerIds].sort((a, b) => a - b),
            sidebar: sidebar,
            current: app.currentLayer ? app.currentLayer.id : null,
        };
    }""")


def make_group(page, member_ids):
    """Cheapest real group: the model shape app-screen-groups.js resolves.
    PUT back to the server too, so a late socket echo of the project cannot
    replace app.project with a copy that never had the group."""
    page.evaluate("""async (ids) => {
        const app = window.app;
        app.project.groups = [{ id: 'g_ms', name: 'MS Wall', layer_ids: ids }];
        app.project.layers.forEach(l => {
            if (ids.includes(l.id)) l.group_id = 'g_ms';
        });
        await fetch('/api/project', {
            method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(app.project),
        });
        app.renderLayers();
        window.canvasRenderer.render();
    }""", member_ids)
    page.wait_for_timeout(200)


# ── the toggle gesture ────────────────────────────────────────────────────

def test_ctrl_click_adds_second_layer_and_sidebar_shows_both(page):
    ids = reset_project(page)
    click_layer(page, 0)                      # plain click: screen 1 selected
    click_layer(page, 1, modifier=MODIFIER)  # toggle screen 2 IN
    got = selection_state(page)
    assert got['selected'] == sorted([ids[0], ids[1]]), got
    assert got['sidebar'] == sorted([ids[0], ids[1]]), got
    assert got['current'] == ids[1], got


def test_ctrl_click_on_selected_layer_removes_it(page):
    # NOTE the layer clicked back OUT is a selected NON-current layer: in
    # pixel-map, a modifier-click on the CURRENT layer's own panel belongs to
    # the pre-existing panel multi-select (bulk blank / half-tile) and is
    # deliberately left to it - pinned further down.
    ids = reset_project(page)
    click_layer(page, 0)
    click_layer(page, 1, modifier=MODIFIER)  # {1, 2}, current = screen 2
    click_layer(page, 0, modifier=MODIFIER)  # toggle screen 1 back OUT
    got = selection_state(page)
    assert got['selected'] == [ids[1]], got
    assert got['sidebar'] == [ids[1]], got


def test_plain_click_replaces_multi_selection(page):
    ids = reset_project(page)
    click_layer(page, 1, modifier=MODIFIER)
    click_layer(page, 2, modifier=MODIFIER)  # {1, 2, 3}, current = screen 3
    assert selection_state(page)['selected'] == sorted(ids)
    click_layer(page, 0)                      # plain click: back to one
    got = selection_state(page)
    assert got['selected'] == [ids[0]], got
    assert got['sidebar'] == [ids[0]], got
    assert got['current'] == ids[0], got


def test_ctrl_click_on_empty_canvas_keeps_selection(page):
    ids = reset_project(page)
    click_layer(page, 0)
    click_layer(page, 1, modifier=MODIFIER)
    # World (900, 900): inside the default 1920x1080 canvas, far from every
    # layer and from the dashed canvas edge (edge-drag band is ~6px).
    x, y = world_to_client(page, 900, 900)
    page.keyboard.down(MODIFIER)
    try:
        page.mouse.click(x, y)
    finally:
        page.keyboard.up(MODIFIER)
    page.wait_for_timeout(150)
    got = selection_state(page)
    assert got['selected'] == sorted([ids[0], ids[1]]), got


def test_no_history_entry_from_toggle_clicks(page):
    """Selection is view state - the toggle must not record undo steps."""
    ids = reset_project(page)
    page.wait_for_timeout(700)  # let any debounced snapshot land
    before = page.evaluate("() => window.app.history.length")
    click_layer(page, 1, modifier=MODIFIER)  # add    -> {1, 2}
    click_layer(page, 0, modifier=MODIFIER)  # remove -> {2}
    page.wait_for_timeout(700)
    after = page.evaluate("() => window.app.history.length")
    assert after == before, (before, after)
    assert selection_state(page)['selected'] == [ids[1]]


# ── composition with screen groups ────────────────────────────────────────

def test_ctrl_click_on_group_member_toggles_whole_group(page):
    ids = reset_project(page)
    make_group(page, [ids[0], ids[1]])
    click_layer(page, 2)                      # plain click: screen 3 only
    assert selection_state(page)['selected'] == [ids[2]]
    click_layer(page, 0, modifier=MODIFIER)  # member -> whole group IN
    got = selection_state(page)
    assert got['selected'] == sorted(ids), got
    assert got['sidebar'] == sorted(ids), got
    # Toggling a selected group's member (the OTHER member, deliberately)
    # removes the whole group, not just the clicked layer.
    click_layer(page, 1, modifier=MODIFIER)
    got = selection_state(page)
    assert got['selected'] == [ids[2]], got
    assert got['sidebar'] == [ids[2]], got


def test_plain_click_on_group_member_still_selects_whole_group(page):
    """The pre-existing v0.11.0 rule the toggle unit is defined by.
    Clicks the member that is NOT current: in pixel-map a plain click on the
    current layer's own panel is the panel-select gesture, not layer-select."""
    ids = reset_project(page)
    make_group(page, [ids[0], ids[1]])
    click_layer(page, 1)
    got = selection_state(page)
    assert got['selected'] == sorted([ids[0], ids[1]]), got


# ── views and reserved gestures ───────────────────────────────────────────

def set_view(page, mode):
    page.evaluate(
        "(m) => { const r = window.canvasRenderer; r.viewMode = m; r.render(); }",
        mode)
    page.wait_for_timeout(100)


def test_toggle_works_in_cabinet_id_view_even_on_current_layer(page):
    """No panel gesture competes outside pixel-map, so there the CURRENT
    layer itself can be modifier-clicked out of the selection."""
    ids = reset_project(page)
    set_view(page, 'cabinet-id')
    click_layer(page, 1, modifier=MODIFIER)  # {1, 2}, current = screen 2
    assert selection_state(page)['selected'] == sorted([ids[0], ids[1]])
    click_layer(page, 1, modifier=MODIFIER)  # current layer toggles OUT
    got = selection_state(page)
    assert got['selected'] == [ids[0]], got
    assert got['sidebar'] == [ids[0]], got


def test_pixelmap_modifier_click_on_current_layers_panel_stays_panel_select(page):
    """Reserved gesture, pinned: in pixel-map, Cmd/Ctrl+click on a panel of
    the CURRENT layer toggles that PANEL's selection (bulk blank / half-tile
    flow) and must leave the layer selection alone."""
    ids = reset_project(page)
    click_layer(page, 0, modifier=MODIFIER)  # current layer's own panel
    got = selection_state(page)
    assert got['selected'] == [ids[0]], got  # layer selection untouched
    assert page.evaluate("() => window.app.pixelMapSelection.size") == 1


def test_power_custom_draw_modifier_click_stays_a_drawing_click(page):
    """Reserved gesture, pinned: with the current layer in custom power mode,
    clicks in Power view (modifier or not) belong to path drawing / panel
    marquee - the layer selection must not change under the modifier."""
    ids = reset_project(page)
    page.evaluate(
        "() => { window.app.currentLayer.powerFlowPattern = 'custom'; }")
    set_view(page, 'power')
    click_layer(page, 0, modifier=MODIFIER)
    got = selection_state(page)
    assert got['selected'] == [ids[0]], got
