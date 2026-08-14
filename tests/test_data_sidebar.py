"""The Signal panel: a third sidebar that exists only in Data view.

The left sidebar had no room left for the processor work Data view is about to
grow, so signal got its own panel between the left sidebar and the canvas, and
the port labelling UI moved into it.

What these tests pin:

* The panel is in layout in Data view and OUT of layout everywhere else -
  Pixel Map, Cabinet ID, Show Look and Power must be exactly as they were
  before it existed, which means display:none rather than a zero-width
  collapse (a collapsed panel still takes a flex slot and still draws a
  border).
* It collapses and expands on its own toggle, and the state survives a reload
  the same way the other two panels' does.
* The port label editor really is inside it, the ids are still unique, and
  nothing was left behind in the left sidebar.
* Editing a port label and pressing Tab still leaves focus in a real field
  after the server round-trip rebuilds the editor. This deliberately overlaps
  tests/test_label_editor_focus.py: moving the markup is precisely the change
  that could break _preserveEditorFocus.
* Collapsing one panel does not move the other two.

Run locally:
    python3 -m pytest tests/test_data_sidebar.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


# Build our OWN project through the real endpoints. The live server is shared
# with every other browser test file, and inheriting whatever the previous one
# left behind has produced "passes alone, fails together" twice in this repo.
#
# 4x4 of 128px cabinets is deliberate: it builds at least two ports, so the
# editor has a Port 1 Return for Tab to move INTO. On a screen small enough to
# need one port, Tab leaves the editor and the focus test proves nothing.
RESET_JS = """async () => {
    const app = window.app;
    let project = await (await fetch('/api/project')).json();
    project.layers = [];
    project.groups = [];
    await fetch('/api/project', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(project),
    });
    await fetch('/api/layer/add', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            name: 'SignalPanel',
            columns: 4, rows: 4, cabinet_width: 128, cabinet_height: 128,
        }),
    });
    app.project = await (await fetch('/api/project')).json();
    app.dedupeProjectLayers('data_sidebar_test_reset');
    const screen = app.project.layers.find(l => (l.type || 'screen') === 'screen');
    app.currentLayer = screen;
    app.selectedLayerIds = new Set([screen.id]);
    app.lastSelectedLayerId = screen.id;
    app.renderLayers();
    app.loadLayerToInputs(screen);
    // The editor sizes itself from _portsRequired, which is a client-side
    // computation - a layer fetched straight from the server carries none.
    app.updatePortCapacityDisplay();
    app.updatePortLabelEditor();
    if (window.canvasRenderer) window.canvasRenderer.render();
    return screen.id;
}"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)  # socket connect + app init
    assert pg.evaluate(RESET_JS), "test project was not created"
    pg.wait_for_timeout(600)
    yield pg
    context.close()


# ── helpers ───────────────────────────────────────────────────────────────

STATE_JS = """() => {
    const read = (id) => {
        const el = document.getElementById(id);
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return {
            displayed: getComputedStyle(el).display !== 'none',
            collapsed: el.classList.contains('collapsed'),
            width: Math.round(r.width),
            left: Math.round(r.left),
            right: Math.round(r.right),
        };
    };
    const btn = document.getElementById('data-sidebar-toggle');
    return {
        data: read('data-sidebar'),
        left: read('left-sidebar'),
        right: read('right-sidebar'),
        canvas: read('canvas-container'),
        toggleShown: btn ? getComputedStyle(btn).display !== 'none' : null,
    };
}"""


def open_view(page, mode):
    page.locator(f'[data-mode="{mode}"]').click()
    page.wait_for_timeout(400)


def state(page):
    return page.evaluate(STATE_JS)


def set_data_panel_collapsed(page, collapsed):
    """Drive the real toggle button, not the class, so the click handler and
    its localStorage write are the things under test."""
    if state(page)['data']['collapsed'] == collapsed:
        return
    page.locator('#data-sidebar-toggle').click()
    page.wait_for_timeout(400)
    assert state(page)['data']['collapsed'] == collapsed


# ── Data view only ────────────────────────────────────────────────────────

def test_the_signal_panel_is_in_layout_in_data_view(page):
    open_view(page, 'data-flow')
    s = state(page)
    assert s['data']['displayed'], "the Signal panel is not in Data view"
    assert s['data']['width'] > 0, f"in layout but zero width: {s['data']}"
    assert s['toggleShown'], "the panel is shown but its collapse toggle is not"


@pytest.mark.parametrize('mode', ['pixel-map', 'cabinet-id', 'show-look', 'power'])
def test_the_signal_panel_is_absent_from_every_other_view(page, mode):
    """The regression bar for this feature: anyone who never opens Data view
    sees no change at all. Out of layout, not merely collapsed."""
    open_view(page, mode)
    s = state(page)
    assert not s['data']['displayed'], (
        f"the Signal panel is still in layout in {mode}: {s['data']}")
    assert s['data']['width'] == 0, f"it still takes width in {mode}: {s['data']}"
    assert not s['toggleShown'], (
        f"a toggle for a panel that is not there, in {mode}")
    # The canvas has to start where it always did, hard against the left
    # sidebar - a collapsed-but-present panel would leave its border behind.
    assert abs(s['canvas']['left'] - s['left']['right']) <= 1, (
        f"the canvas moved in {mode}: canvas left {s['canvas']['left']}, "
        f"left sidebar right {s['left']['right']}")


def test_the_panel_sits_between_the_left_sidebar_and_the_canvas(page):
    open_view(page, 'data-flow')
    s = state(page)
    assert s['left']['right'] <= s['data']['left'] + 1, (
        f"the Signal panel is not right of the left sidebar: {s}")
    assert s['data']['right'] <= s['canvas']['left'] + 1, (
        f"the Signal panel is not left of the canvas: {s}")


# ── Collapse ──────────────────────────────────────────────────────────────

def test_it_collapses_and_expands_on_its_own_toggle(page):
    open_view(page, 'data-flow')
    set_data_panel_collapsed(page, True)
    # <= 1, not == 0: the theme keeps each docked panel's 1px inner border at
    # full width even when the panel itself is zero, so a collapsed panel is a
    # hairline seam. The left and right sidebars have always behaved this way
    # and this one matches them on purpose.
    assert state(page)['data']['width'] <= 1, "collapsed but still taking width"
    set_data_panel_collapsed(page, False)
    assert state(page)['data']['width'] > 100, "expanded but still not a panel"


def test_the_collapsed_state_survives_a_reload(page):
    open_view(page, 'data-flow')
    set_data_panel_collapsed(page, True)

    page.reload(wait_until='domcontentloaded')
    page.wait_for_timeout(2000)
    open_view(page, 'data-flow')
    assert state(page)['data']['collapsed'], (
        "the Signal panel came back expanded after a reload")

    # And the other way round, so the test cannot pass on a panel that is
    # simply always collapsed.
    set_data_panel_collapsed(page, False)
    page.reload(wait_until='domcontentloaded')
    page.wait_for_timeout(2000)
    open_view(page, 'data-flow')
    assert not state(page)['data']['collapsed'], (
        "the Signal panel came back collapsed after a reload")
    page.evaluate(RESET_JS)
    page.wait_for_timeout(600)


def test_the_three_panels_collapse_independently(page):
    open_view(page, 'data-flow')
    set_data_panel_collapsed(page, False)

    def collapse(toggle_id):
        page.locator(f'#{toggle_id}').click()
        page.wait_for_timeout(400)

    collapse('left-sidebar-toggle')
    s = state(page)
    assert s['left']['collapsed'], "the left sidebar did not collapse"
    assert not s['data']['collapsed'], "collapsing left took the Signal panel"
    assert not s['right']['collapsed'], "collapsing left took the right sidebar"

    collapse('data-sidebar-toggle')
    s = state(page)
    assert s['data']['collapsed'], "the Signal panel did not collapse"
    assert not s['right']['collapsed'], "collapsing Signal took the right sidebar"

    collapse('right-sidebar-toggle')
    s = state(page)
    assert s['right']['collapsed'], "the right sidebar did not collapse"

    # Back out, one at a time, and each must come back alone.
    collapse('left-sidebar-toggle')
    s = state(page)
    assert not s['left']['collapsed'], "the left sidebar did not expand"
    assert s['data']['collapsed'], "expanding left dragged the Signal panel back"
    assert s['right']['collapsed'], "expanding left dragged the right sidebar back"

    collapse('data-sidebar-toggle')
    collapse('right-sidebar-toggle')
    s = state(page)
    assert not s['data']['collapsed'] and not s['right']['collapsed'], s


# ── The port label editor came with it ────────────────────────────────────

PORT_LABEL_IDS = [
    'port-label-template-primary',
    'port-label-template-return',
    'port-label-bulk-primary',
    'port-label-bulk-return',
    'port-label-apply-selected',
    'port-label-clear-selected',
    'port-label-select-all',
    'port-label-deselect-all',
    'port-label-list',
]


def test_the_port_label_markup_moved_whole_and_kept_its_ids(page):
    open_view(page, 'data-flow')
    for element_id in PORT_LABEL_IDS:
        found = page.evaluate(
            """(id) => {
                const all = document.querySelectorAll('[id="' + id + '"]');
                const inPanel = document.querySelectorAll(
                    '#data-sidebar [id="' + id + '"]').length;
                const inLeft = document.querySelectorAll(
                    '#left-sidebar [id="' + id + '"]').length;
                return { total: all.length, inPanel, inLeft };
            }""", element_id)
        assert found['total'] == 1, (
            f"#{element_id} is not unique in the document: {found}")
        assert found['inPanel'] == 1, f"#{element_id} is not in the Signal panel"
        assert found['inLeft'] == 0, f"#{element_id} was left in the left sidebar"


def test_the_editor_builds_its_rows_inside_the_signal_panel(page):
    open_view(page, 'data-flow')
    page.wait_for_timeout(300)
    fields = page.evaluate(
        """() => [...document.querySelectorAll('#data-sidebar [data-lrd-field]')]
               .map(el => el.dataset.lrdField)""")
    assert 'port-primary-1' in fields, f"no Port 1 Primary field: {fields}"
    assert 'port-return-1' in fields, (
        f"no Port 1 Return field - Tab out of Primary would leave the editor "
        f"and the focus test below would prove nothing: {fields}")


FOCUS_JS = """() => {
    const a = document.activeElement;
    return {
        tag: a ? a.tagName : null,
        key: (a && a.dataset) ? (a.dataset.lrdField || null) : null,
        isBody: a === document.body,
        inPanel: !!(a && a.closest && a.closest('#data-sidebar')),
        stamped: !!(a && a.__stamp),
    };
}"""


def test_typing_a_label_and_pressing_tab_keeps_focus_in_a_real_field(page):
    """The editor wipes itself with innerHTML = '' on every server round-trip,
    so the field Tab just moved into is destroyed under the user's fingers.
    _preserveEditorFocus (app-power.js) restores it by data-lrd-field key -
    moving the markup is exactly what could have broken that."""
    open_view(page, 'data-flow')
    page.evaluate("""() => {
        const l = window.app.currentLayer;
        l.portLabelOverridesPrimary = {};
        l.portLabelOverridesReturn = {};
        window.app.updatePortLabelEditor();
    }""")
    page.wait_for_timeout(200)

    # Stamp the current fields. Element identity does not survive a rebuild,
    # so a still-stamped field afterwards would mean no rebuild happened and
    # the focus assertion would be passing for the wrong reason.
    stamped = page.evaluate(
        """() => {
            const els = document.querySelectorAll('#port-label-list input');
            els.forEach(el => { el.__stamp = 1; });
            return els.length;
        }""")
    assert stamped >= 2, f"the editor built no fields to test: {stamped}"

    page.evaluate(
        """() => document.querySelector(
               '[data-lrd-field="port-primary-1"]').focus()""")
    page.keyboard.type("SIG-A")
    page.keyboard.press("Tab")
    assert page.evaluate(FOCUS_JS)['key'] == 'port-return-1', (
        "Tab did not move to Port 1 Return - the moved markup changed the "
        "tab order inside the editor")

    page.wait_for_function(
        """() => {
            const el = document.querySelector('[data-lrd-field="port-return-1"]');
            return !!el && !el.__stamp;
        }""",
        timeout=5000,
    )
    after = page.evaluate(FOCUS_JS)
    assert not after['isBody'], (
        f"focus fell to <body> after the rebuild: {after}")
    assert after['tag'] == 'INPUT', f"focus left the editor entirely: {after}"
    assert after['key'] == 'port-return-1', f"focus moved elsewhere: {after}"
    assert after['inPanel'], (
        f"focus is outside the Signal panel, so the field it landed on is not "
        f"the moved editor's: {after}")
    assert not after['stamped'], (
        "the editor never rebuilt, so this proved nothing - the fixture or "
        "the round-trip changed")

    stored = page.evaluate(
        "() => window.app.currentLayer.portLabelOverridesPrimary")
    assert stored.get('1') == 'SIG-A', (
        f"the edit did not survive the move: {stored}")
