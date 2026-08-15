"""Drag-resizable docked panels: left sidebar, Signal panel, right sidebar.

The resize code (theme.js) was hardcoded to the two string literals 'left' and
'right', so the Signal panel - a third, middle column added later - collapsed
but could not be resized. It is now a table of panels, the same shape as the
collapse table in app-core.js initSidebarToggles, and these tests pin the
behaviour that table has to keep producing.

What these tests pin:

* All three panels carry a drag strip on their inner edge, and dragging it
  really changes the panel's width - not just the CSS variable.
* The width clamps between 180 and 560 so a panel can neither vanish nor
  swallow the canvas, and it survives a reload.
* The Signal panel's strip leaves with the panel. Outside Data view the panel
  is display:none, and a fixed-position strip left floating over the canvas
  there would be a live bug: a 7px column of the drawing that silently starts
  a resize instead of a selection.
* The collapse toggle stays on top of the strip. They occupy the same seam,
  and the toggle is the only way back from a collapsed panel.
* Dragging re-measures the canvas. The canvas backing store is sized from its
  wrapper in setupCanvas(), whose only automatic trigger is the window resize
  listener, so before this change a drag left the canvas painting at its
  pre-drag pixel width until the window itself was resized.
* No toggle and no drag strip is ever left floating over the drawing. Reported
  as "the sidebar is still floating in the air": collapsing a panel used to
  reposition only its own toggle, so collapsing the left sidebar slid the
  Signal panel across without telling its toggle, stranding it mid-canvas.
  These assert on coordinates, because in that bug every class was already
  correct.

Run locally:
    python3 -m pytest tests/test_sidebar_resize.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


# theme.js clamps every panel to this range. Mirrored here deliberately: the
# numbers are the contract, and a silent change to either end is exactly the
# regression worth catching.
MIN_W = 180
MAX_W = 560
DEFAULT_W = 260

# Wide enough that the canvas wrapper still has slack after a panel grows to
# its maximum - at 1280 the canvas container is already pinned to its own
# minimum width, which would make the re-measure assertions vacuous.
VIEWPORT = {'width': 1700, 'height': 900}

PANELS = {
    'left': 'left-sidebar',
    'data': 'data-sidebar',
    'right': 'right-sidebar',
}


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport=VIEWPORT)
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)  # socket connect + app init
    yield pg
    context.close()


# ── helpers ───────────────────────────────────────────────────────────────

def open_view(page, mode):
    page.locator(f'[data-mode="{mode}"]').click()
    page.wait_for_timeout(400)


def reset_widths(page):
    """Back to the default width on every panel, through the same localStorage
    keys theme.js reads on boot, so each test starts from a known geometry."""
    page.evaluate(
        """(w) => {
            ['lrd_left_w', 'lrd_data_w', 'lrd_right_w'].forEach(
                k => localStorage.setItem(k, String(w)));
        }""", DEFAULT_W)
    page.reload(wait_until='domcontentloaded')
    page.wait_for_timeout(2000)
    open_view(page, 'data-flow')


def width(page, key):
    return page.evaluate(
        "(id) => Math.round(document.getElementById(id).getBoundingClientRect().width)",
        PANELS[key])


HANDLE_JS = """(key) => {
    const h = document.querySelector(
        '.lrd-resize-handle[data-lrd-resize="' + key + '"]');
    if (!h) return null;
    if (getComputedStyle(h).display === 'none') return null;
    const r = h.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return null;
    return { x: r.left + r.width / 2, y: r.top + 40,
             left: r.left, top: r.top, height: r.height };
}"""


def handle(page, key):
    """The visible drag strip for a panel, or None. `y` deliberately sits near
    the top of the strip: the collapse toggle sits over its middle."""
    return page.evaluate(HANDLE_JS, key)


def drag(page, key, dx):
    """Drag a panel's strip by dx pixels and answer the panel's new width.

    Stepped moves, not one jump: the handler works off mousemove, and a single
    synthetic jump would exercise a code path no user can produce."""
    h = handle(page, key)
    assert h, f"no visible resize handle for the {key} panel"
    page.mouse.move(h['x'], h['y'])
    page.mouse.down()
    for step in range(1, 5):
        page.mouse.move(h['x'] + dx * step / 4.0, h['y'])
    page.mouse.up()
    page.wait_for_timeout(400)
    return width(page, key)


CANVAS_JS = """() => {
    const c = document.getElementById('main-canvas');
    const w = document.getElementById('canvas-wrapper');
    return { canvasW: c.width, wrapperW: w.clientWidth,
             canvasH: c.height, wrapperH: w.clientHeight };
}"""


def assert_canvas_matches_wrapper(page, why):
    m = page.evaluate(CANVAS_JS)
    assert m['canvasW'] == m['wrapperW'], (
        f"the canvas kept its old pixel width after {why}: {m}")
    assert m['canvasH'] == m['wrapperH'], (
        f"the canvas kept its old pixel height after {why}: {m}")


# ── the handles exist and are where they should be ────────────────────────

def test_every_docked_panel_has_a_drag_strip_in_data_view(page):
    reset_widths(page)
    for key in PANELS:
        assert handle(page, key), f"the {key} panel has no resize handle"


@pytest.mark.parametrize('key,edge', [
    ('left', 'right'), ('data', 'right'), ('right', 'left')])
def test_each_strip_sits_on_its_panels_inner_edge(page, key, edge):
    """The Signal panel is a middle column docked left, so it is dragged from
    the right exactly like the left sidebar - not from the left because it is
    'the second panel'."""
    reset_widths(page)
    h = handle(page, key)
    rect = page.evaluate(
        "(id) => { const r = document.getElementById(id).getBoundingClientRect();"
        "return { left: r.left, right: r.right }; }", PANELS[key])
    target = rect['right'] if edge == 'right' else rect['left']
    assert abs(h['left'] - target) <= 6, (
        f"the {key} panel's strip is not on its {edge} edge: "
        f"strip at {h['left']}, edge at {target}")


# ── dragging the Signal panel ─────────────────────────────────────────────

def test_dragging_the_signal_panel_changes_its_width(page):
    reset_widths(page)
    before = width(page, 'data')
    after = drag(page, 'data', 120)
    assert after > before + 80, (
        f"the Signal panel did not widen: {before} -> {after}")
    assert abs(after - (before + 120)) <= 8, (
        f"the Signal panel did not follow the pointer: {before} -> {after}")


def test_the_signal_panel_width_survives_a_reload(page):
    reset_widths(page)
    dragged = drag(page, 'data', 120)

    page.reload(wait_until='domcontentloaded')
    page.wait_for_timeout(2000)
    open_view(page, 'data-flow')
    assert abs(width(page, 'data') - dragged) <= 2, (
        f"the Signal panel came back at {width(page, 'data')}, not {dragged}")

    # And the other way round, so this cannot pass on a panel that is simply
    # always wide.
    reset_widths(page)
    assert abs(width(page, 'data') - DEFAULT_W) <= 2, (
        "the Signal panel ignored a stored default width")


def test_the_signal_panel_clamps_at_the_minimum(page):
    reset_widths(page)
    assert drag(page, 'data', -600) == MIN_W, (
        "the Signal panel can be dragged narrower than the clamp")


def test_the_signal_panel_clamps_at_the_maximum(page):
    reset_widths(page)
    assert drag(page, 'data', 600) == MAX_W, (
        "the Signal panel can be dragged wider than the clamp")


def test_resizing_one_panel_leaves_the_others_alone(page):
    reset_widths(page)
    drag(page, 'left', 100)
    assert width(page, 'left') == DEFAULT_W + 100, "the left sidebar did not resize"
    assert width(page, 'data') == DEFAULT_W, (
        "resizing the left sidebar resized the Signal panel with it")
    assert width(page, 'right') == DEFAULT_W, (
        "resizing the left sidebar resized the right sidebar with it")


# ── the strip leaves when the panel does ──────────────────────────────────

@pytest.mark.parametrize('mode', ['pixel-map', 'cabinet-id', 'show-look', 'power'])
def test_the_signal_strip_is_gone_outside_data_view(page, mode):
    reset_widths(page)
    open_view(page, mode)
    assert handle(page, 'data') is None, (
        f"the Signal panel's drag strip is still over the canvas in {mode}")
    # The other two are unaffected - the strip did not simply stop being drawn.
    assert handle(page, 'left') and handle(page, 'right'), (
        f"leaving Data view took the other panels' strips with it, in {mode}")


def test_the_signal_strip_is_gone_while_the_panel_is_collapsed(page):
    reset_widths(page)
    page.locator('#data-sidebar-toggle').click()
    page.wait_for_timeout(500)
    assert handle(page, 'data') is None, (
        "a collapsed panel still offers a strip to drag")
    page.locator('#data-sidebar-toggle').click()
    page.wait_for_timeout(500)
    assert handle(page, 'data'), "the strip did not come back with the panel"


def test_the_strip_does_not_swallow_the_collapse_toggle(page):
    """They share the same seam and the strip is full height. The toggle is the
    only way back from a collapsed panel, so it has to win the hit test."""
    reset_widths(page)
    for toggle_id in ('left-sidebar-toggle', 'data-sidebar-toggle',
                      'right-sidebar-toggle'):
        hit = page.evaluate(
            """(id) => {
                const r = document.getElementById(id).getBoundingClientRect();
                const el = document.elementFromPoint(
                    Math.round(r.left + r.width / 2),
                    Math.round(r.top + r.height / 2));
                return el ? (el.id || el.className) : null;
            }""", toggle_id)
        assert hit == toggle_id, (
            f"#{toggle_id} is covered by {hit} - the resize strip is on top "
            f"of the only control that can expand the panel again")


# ── the canvas keeps up ───────────────────────────────────────────────────

@pytest.mark.parametrize('key', ['left', 'data', 'right'])
def test_dragging_a_panel_re_measures_the_canvas(page, key):
    """setupCanvas() sizes the canvas from its wrapper and only runs itself on
    a window resize, so a drag used to leave the canvas painting at its
    pre-drag pixel width until the window was touched."""
    reset_widths(page)
    assert_canvas_matches_wrapper(page, "a reset")
    dx = -140 if key == 'right' else 140
    drag(page, key, dx)
    assert_canvas_matches_wrapper(page, f"dragging the {key} panel")


def test_the_canvas_keeps_up_during_the_drag_not_only_at_the_end(page):
    """The width transition is suppressed while dragging, so every frame is
    already in layout - the canvas is re-measured per move rather than left to
    the staged settle on mouseup."""
    reset_widths(page)
    h = handle(page, 'data')
    page.mouse.move(h['x'], h['y'])
    page.mouse.down()
    page.mouse.move(h['x'] + 60, h['y'])
    page.mouse.move(h['x'] + 120, h['y'])
    page.wait_for_timeout(120)
    mid = page.evaluate(CANVAS_JS)
    page.mouse.up()
    page.wait_for_timeout(400)
    assert mid['canvasW'] == mid['wrapperW'], (
        f"the canvas lagged the pointer mid-drag: {mid}")


# ── nothing stranded over the drawing ─────────────────────────────────────
#
# Reported as "you can see the sidebar is still floating in the air": with the
# panels collapsed, a chevron tab sat in the middle of the artwork.
#
# The cause was that collapsing a panel repositioned only its OWN toggle, while
# collapsing the left sidebar MOVES the Signal panel - the next flex column -
# without changing its size. Its toggle was never told, and the ResizeObserver
# that was meant to be the safety net watches size, not position, so it never
# fired either. Nothing else repositions toggles, so it stayed stranded.
#
# These assert on geometry rather than on a class: in the reported bug every
# class was correct and only the coordinates were wrong.

STRAYS_JS = """() => {
    const shown = el => el && getComputedStyle(el).display !== 'none';
    const canvas = document.getElementById('canvas-container').getBoundingClientRect();
    const panels = [
        { key: 'left',  sidebar: 'left-sidebar',  toggle: 'left-sidebar-toggle',  inner: 'right' },
        { key: 'data',  sidebar: 'data-sidebar',  toggle: 'data-sidebar-toggle',  inner: 'right' },
        { key: 'right', sidebar: 'right-sidebar', toggle: 'right-sidebar-toggle', inner: 'left'  },
    ];
    const strays = [];
    panels.forEach(p => {
        const edge = document.getElementById(p.sidebar)
                             .getBoundingClientRect()[p.inner];
        const controls = [
            ['toggle', document.getElementById(p.toggle)],
            ['handle', document.querySelector(
                '.lrd-resize-handle[data-lrd-resize="' + p.key + '"]')],
        ];
        controls.forEach(([kind, el]) => {
            if (!shown(el)) return;   // out of layout can't be floating
            const r = el.getBoundingClientRect();
            // Both controls straddle the seam, so measure whichever of their
            // own edges faces the panel they belong to.
            const own = p.inner === 'right' ? r.left : r.right;
            const drift = Math.abs(own - edge);
            if (drift <= 8) return;
            strays.push({
                kind: kind, key: p.key,
                drift: Math.round(drift),
                at: Math.round(own), edge: Math.round(edge),
                intoCanvas: Math.round(p.inner === 'right'
                    ? r.left - canvas.left : canvas.right - r.right),
            });
        });
    });
    return strays;
}"""


def assert_nothing_stranded(page, where):
    strays = page.evaluate(STRAYS_JS)
    assert not strays, (
        f"a control is floating away from the panel it belongs to, {where}: "
        f"{strays} (drift is px from its panel's inner edge; intoCanvas is how "
        f"far into the drawing it is sitting)")


def set_collapsed(page, key, want):
    sidebar = PANELS[key]
    is_collapsed = page.evaluate(
        "(id) => document.getElementById(id).classList.contains('collapsed')",
        sidebar)
    if is_collapsed == want:
        return
    page.locator(f'#{key}-sidebar-toggle').click()
    page.wait_for_timeout(500)


def test_collapsing_the_left_sidebar_takes_the_signal_toggle_with_it(page):
    """The reported repro, exactly: in Data view, collapse the Signal panel and
    then the left sidebar. The Signal panel slides left without resizing, and
    its toggle used to stay behind in the middle of the drawing."""
    reset_widths(page)
    set_collapsed(page, 'data', True)
    assert_nothing_stranded(page, "with only the Signal panel collapsed")
    set_collapsed(page, 'left', True)
    page.wait_for_timeout(500)
    assert_nothing_stranded(
        page, "after collapsing the left sidebar behind a collapsed Signal panel")
    set_collapsed(page, 'left', False)
    set_collapsed(page, 'data', False)


def test_resizing_the_left_sidebar_takes_the_signal_toggle_with_it(page):
    """The same failure the drag handles could reintroduce: widening the left
    sidebar moves the Signal panel without resizing it."""
    reset_widths(page)
    drag(page, 'left', 140)
    assert_nothing_stranded(page, "after widening the left sidebar")
    drag(page, 'left', -140)
    assert_nothing_stranded(page, "after narrowing the left sidebar again")


@pytest.mark.parametrize('mode', ['pixel-map', 'cabinet-id', 'show-look',
                                  'data-flow', 'power'])
def test_no_control_is_stranded_in_any_view_or_collapse_order(page, mode):
    """Every view, and both collapse orders - the bug only appeared in one of
    them, so a single ordering would have missed it."""
    reset_widths(page)
    open_view(page, mode)
    in_data = mode == 'data-flow'

    for key in (['left', 'data', 'right'] if in_data else ['left', 'right']):
        set_collapsed(page, key, False)
    assert_nothing_stranded(page, f"in {mode} with everything expanded")

    # left first, then the rest
    for key in (['left', 'data', 'right'] if in_data else ['left', 'right']):
        set_collapsed(page, key, True)
        assert_nothing_stranded(page, f"in {mode} after collapsing {key} first")
    for key in (['left', 'data', 'right'] if in_data else ['left', 'right']):
        set_collapsed(page, key, False)

    # and the reverse order, which is what actually stranded the Signal toggle
    for key in (['right', 'data', 'left'] if in_data else ['right', 'left']):
        set_collapsed(page, key, True)
        assert_nothing_stranded(page, f"in {mode} collapsing inwards, at {key}")
    for key in (['left', 'data', 'right'] if in_data else ['left', 'right']):
        set_collapsed(page, key, False)


def test_nothing_is_stranded_across_a_view_switch(page):
    """A panel leaving layout entirely moves everything to its right."""
    reset_widths(page)
    set_collapsed(page, 'left', True)
    for mode in ('data-flow', 'pixel-map', 'data-flow', 'power', 'data-flow'):
        open_view(page, mode)
        assert_nothing_stranded(page, f"after switching to {mode}")
    set_collapsed(page, 'left', False)
