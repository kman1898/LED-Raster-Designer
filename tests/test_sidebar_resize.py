"""Drag-resizable docked panels: left sidebar, Signal panel, Power panel, right
sidebar.

The resize code (theme.js) was hardcoded to the two string literals 'left' and
'right', so the Signal panel - a middle column added later - collapsed but could
not be resized. It is now a table of panels, the same shape as the collapse
table in app-core.js initSidebarToggles, and these tests pin the behaviour that
table has to keep producing. The Power panel is the second middle column and
went in as one more row of each table, so every assertion below runs against
both of them rather than against a copy of the file.

What these tests pin:

* Every panel carries a drag strip on its inner edge, and dragging it really
  changes the panel's width - not just the CSS variable.
* The width clamps between 180 and 560 so a panel can neither vanish nor
  swallow the canvas, and it survives a reload.
* Each middle panel's strip leaves with the panel. Outside its own view the
  panel is display:none, and a fixed-position strip left floating over the
  canvas there would be a live bug: a 7px column of the drawing that silently
  starts a resize instead of a selection.
* The two middle panels are independent. Signal and Power keep their own width
  and their own collapsed state, and neither moves when the other is dragged.
* The collapse toggle stays on top of the strip. They occupy the same seam,
  and the toggle is the only way back from a collapsed panel.
* Dragging re-measures the canvas. The canvas backing store is sized from its
  wrapper in setupCanvas(), whose only automatic trigger is the window resize
  listener, so before this change a drag left the canvas painting at its
  pre-drag pixel width until the window itself was resized.
* No toggle and no drag strip is ever left floating over the drawing. Reported
  as "the sidebar is still floating in the air": collapsing a panel used to
  reposition only its own toggle, so collapsing the left sidebar slid the
  middle panel across without telling its toggle, stranding it mid-canvas.
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


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project exactly as this module found it -
    the distro seeds persist server-side and their cleanup POST can be
    aborted by the next test's reload (see conftest.server_project_guard)."""


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
    'power': 'power-sidebar',
    'right': 'right-sidebar',
}

# The middle columns and the one view each belongs to. The left and right
# sidebars are in every view, so they have no entry here.
VIEW_OF = {'data': 'data-flow', 'power': 'power'}

ALL_VIEWS = ['pixel-map', 'cabinet-id', 'show-look', 'data-flow', 'power']

# Every (middle panel, view it is absent from) pair, which is what the
# "the strip left with the panel" assertions have to sweep.
ABSENT = [(key, mode) for key in VIEW_OF for mode in ALL_VIEWS
          if mode != VIEW_OF[key]]


def keys_in(mode):
    """The panels that are in layout in `mode`, left to right."""
    middle = [k for k, v in VIEW_OF.items() if v == mode]
    return ['left'] + middle + ['right']


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


def reset_widths(page, mode='data-flow'):
    """Back to the default width and expanded on every panel, through the same
    localStorage keys app-core.js and theme.js read on boot, so each test starts
    from a known geometry no matter what the one before it left collapsed."""
    page.evaluate(
        """(w) => {
            ['lrd_left_w', 'lrd_data_w', 'lrd_power_w', 'lrd_right_w'].forEach(
                k => localStorage.setItem(k, String(w)));
            ['left', 'data', 'power', 'right'].forEach(
                k => localStorage.setItem('ledRasterSidebarCollapsed_' + k, '0'));
        }""", DEFAULT_W)
    page.reload(wait_until='domcontentloaded')
    page.wait_for_timeout(2000)
    open_view(page, mode)


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

@pytest.mark.parametrize('mode', ALL_VIEWS)
def test_every_docked_panel_in_a_view_has_a_drag_strip(page, mode):
    reset_widths(page, mode)
    for key in keys_in(mode):
        assert handle(page, key), f"the {key} panel has no resize handle in {mode}"


@pytest.mark.parametrize('key,edge', [
    ('left', 'right'), ('data', 'right'), ('power', 'right'), ('right', 'left')])
def test_each_strip_sits_on_its_panels_inner_edge(page, key, edge):
    """The middle panels dock left, so they are dragged from the right exactly
    like the left sidebar - not from the left because they are 'the second
    panel'."""
    reset_widths(page, VIEW_OF.get(key, 'data-flow'))
    h = handle(page, key)
    rect = page.evaluate(
        "(id) => { const r = document.getElementById(id).getBoundingClientRect();"
        "return { left: r.left, right: r.right }; }", PANELS[key])
    target = rect['right'] if edge == 'right' else rect['left']
    assert abs(h['left'] - target) <= 6, (
        f"the {key} panel's strip is not on its {edge} edge: "
        f"strip at {h['left']}, edge at {target}")


# ── dragging a middle panel ───────────────────────────────────────────────

@pytest.mark.parametrize('key', sorted(VIEW_OF))
def test_dragging_a_middle_panel_changes_its_width(page, key):
    reset_widths(page, VIEW_OF[key])
    before = width(page, key)
    after = drag(page, key, 120)
    assert after > before + 80, f"the {key} panel did not widen: {before} -> {after}"
    assert abs(after - (before + 120)) <= 8, (
        f"the {key} panel did not follow the pointer: {before} -> {after}")


@pytest.mark.parametrize('key', sorted(VIEW_OF))
def test_a_middle_panels_width_survives_a_reload(page, key):
    mode = VIEW_OF[key]
    reset_widths(page, mode)
    dragged = drag(page, key, 120)

    page.reload(wait_until='domcontentloaded')
    page.wait_for_timeout(2000)
    open_view(page, mode)
    assert abs(width(page, key) - dragged) <= 2, (
        f"the {key} panel came back at {width(page, key)}, not {dragged}")

    # And the other way round, so this cannot pass on a panel that is simply
    # always wide.
    reset_widths(page, mode)
    assert abs(width(page, key) - DEFAULT_W) <= 2, (
        f"the {key} panel ignored a stored default width")


@pytest.mark.parametrize('key', sorted(VIEW_OF))
def test_a_middle_panel_clamps_at_the_minimum(page, key):
    reset_widths(page, VIEW_OF[key])
    assert drag(page, key, -600) == MIN_W, (
        f"the {key} panel can be dragged narrower than the clamp")


@pytest.mark.parametrize('key', sorted(VIEW_OF))
def test_a_middle_panel_clamps_at_the_maximum(page, key):
    reset_widths(page, VIEW_OF[key])
    assert drag(page, key, 600) == MAX_W, (
        f"the {key} panel can be dragged wider than the clamp")


@pytest.mark.parametrize('mode', ['data-flow', 'power'])
def test_resizing_one_panel_leaves_the_others_alone(page, mode):
    reset_widths(page, mode)
    drag(page, 'left', 100)
    assert width(page, 'left') == DEFAULT_W + 100, "the left sidebar did not resize"
    for key in keys_in(mode)[1:]:
        assert width(page, key) == DEFAULT_W, (
            f"resizing the left sidebar resized the {key} panel with it")


def test_the_two_middle_panels_keep_their_own_widths(page):
    """Signal and Power occupy the same slot and are never both in layout, so a
    shared storage key would look right until the user switched tabs."""
    reset_widths(page, 'data-flow')
    signal = drag(page, 'data', 120)

    open_view(page, 'power')
    assert width(page, 'power') == DEFAULT_W, (
        f"widening Signal widened Power with it: {width(page, 'power')}")
    power = drag(page, 'power', -60)

    open_view(page, 'data-flow')
    assert width(page, 'data') == signal, (
        f"the Signal panel came back at {width(page, 'data')}, not {signal} - "
        f"resizing Power overwrote it")
    open_view(page, 'power')
    assert width(page, 'power') == power, (
        f"the Power panel came back at {width(page, 'power')}, not {power}")

    stored = page.evaluate(
        """() => ({ data: localStorage.getItem('lrd_data_w'),
                    power: localStorage.getItem('lrd_power_w') })""")
    assert stored['data'] != stored['power'], (
        f"both panels are persisting through the same value: {stored}")


# ── the strip leaves when the panel does ──────────────────────────────────

@pytest.mark.parametrize('key,mode', ABSENT)
def test_a_middle_strip_is_gone_outside_its_own_view(page, key, mode):
    reset_widths(page, mode)
    assert handle(page, key) is None, (
        f"the {key} panel's drag strip is still over the canvas in {mode}")
    # The other two are unaffected - the strip did not simply stop being drawn.
    assert handle(page, 'left') and handle(page, 'right'), (
        f"leaving {VIEW_OF[key]} took the other panels' strips with it, in {mode}")


@pytest.mark.parametrize('key', sorted(VIEW_OF))
def test_a_middle_strip_is_gone_while_the_panel_is_collapsed(page, key):
    reset_widths(page, VIEW_OF[key])
    page.locator(f'#{key}-sidebar-toggle').click()
    page.wait_for_timeout(500)
    assert handle(page, key) is None, (
        f"a collapsed {key} panel still offers a strip to drag")
    page.locator(f'#{key}-sidebar-toggle').click()
    page.wait_for_timeout(500)
    assert handle(page, key), f"the {key} strip did not come back with the panel"


@pytest.mark.parametrize('mode', ['data-flow', 'power'])
def test_the_strip_does_not_swallow_the_collapse_toggle(page, mode):
    """They share the same seam and the strip is full height. The toggle is the
    only way back from a collapsed panel, so it has to win the hit test."""
    reset_widths(page, mode)
    for key in keys_in(mode):
        toggle_id = f'{key}-sidebar-toggle'
        hit = page.evaluate(
            """(id) => {
                const r = document.getElementById(id).getBoundingClientRect();
                const el = document.elementFromPoint(
                    Math.round(r.left + r.width / 2),
                    Math.round(r.top + r.height / 2));
                return el ? (el.id || el.className) : null;
            }""", toggle_id)
        assert hit == toggle_id, (
            f"#{toggle_id} is covered by {hit} in {mode} - the resize strip is "
            f"on top of the only control that can expand the panel again")


# ── the canvas keeps up ───────────────────────────────────────────────────

@pytest.mark.parametrize('key', ['left', 'data', 'power', 'right'])
def test_dragging_a_panel_re_measures_the_canvas(page, key):
    """setupCanvas() sizes the canvas from its wrapper and only runs itself on
    a window resize, so a drag used to leave the canvas painting at its
    pre-drag pixel width until the window was touched."""
    reset_widths(page, VIEW_OF.get(key, 'data-flow'))
    assert_canvas_matches_wrapper(page, "a reset")
    dx = -140 if key == 'right' else 140
    drag(page, key, dx)
    assert_canvas_matches_wrapper(page, f"dragging the {key} panel")


@pytest.mark.parametrize('key', sorted(VIEW_OF))
def test_the_canvas_keeps_up_during_the_drag_not_only_at_the_end(page, key):
    """The width transition is suppressed while dragging, so every frame is
    already in layout - the canvas is re-measured per move rather than left to
    the staged settle on mouseup."""
    reset_widths(page, VIEW_OF[key])
    h = handle(page, key)
    page.mouse.move(h['x'], h['y'])
    page.mouse.down()
    page.mouse.move(h['x'] + 60, h['y'])
    page.mouse.move(h['x'] + 120, h['y'])
    page.wait_for_timeout(120)
    mid = page.evaluate(CANVAS_JS)
    page.mouse.up()
    page.wait_for_timeout(400)
    assert mid['canvasW'] == mid['wrapperW'], (
        f"the canvas lagged the pointer mid-drag on the {key} panel: {mid}")


# ── nothing stranded over the drawing ─────────────────────────────────────
#
# Reported as "you can see the sidebar is still floating in the air": with the
# panels collapsed, a chevron tab sat in the middle of the artwork.
#
# The cause was that collapsing a panel repositioned only its OWN toggle, while
# collapsing the left sidebar MOVES the middle panel - the next flex column -
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
        { key: 'power', sidebar: 'power-sidebar', toggle: 'power-sidebar-toggle', inner: 'right' },
        { key: 'right', sidebar: 'right-sidebar', toggle: 'right-sidebar-toggle', inner: 'left'  },
    ];
    const strays = [];
    panels.forEach(p => {
        const panel = document.getElementById(p.sidebar);
        // A panel that has left layout has no geometry to measure against, so
        // the bar for it is simply that neither of its controls is drawn.
        const inLayout = shown(panel);
        const edge = panel.getBoundingClientRect()[p.inner];
        const controls = [
            ['toggle', document.getElementById(p.toggle)],
            ['handle', document.querySelector(
                '.lrd-resize-handle[data-lrd-resize="' + p.key + '"]')],
        ];
        controls.forEach(([kind, el]) => {
            if (!shown(el)) return;   // out of layout can't be floating
            const r = el.getBoundingClientRect();
            if (!inLayout) {
                strays.push({ kind: kind, key: p.key, reason: 'panel not in layout',
                              at: Math.round(r.left),
                              intoCanvas: Math.round(r.left - canvas.left) });
                return;
            }
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


@pytest.mark.parametrize('key', sorted(VIEW_OF))
def test_collapsing_the_left_sidebar_takes_the_middle_toggle_with_it(page, key):
    """The reported repro, exactly: in the panel's own view, collapse the middle
    panel and then the left sidebar. The middle panel slides left without
    resizing, and its toggle used to stay behind in the middle of the
    drawing."""
    reset_widths(page, VIEW_OF[key])
    set_collapsed(page, key, True)
    assert_nothing_stranded(page, f"with only the {key} panel collapsed")
    set_collapsed(page, 'left', True)
    page.wait_for_timeout(500)
    assert_nothing_stranded(
        page, f"after collapsing the left sidebar behind a collapsed {key} panel")
    set_collapsed(page, 'left', False)
    set_collapsed(page, key, False)


@pytest.mark.parametrize('mode', ['data-flow', 'power'])
def test_resizing_the_left_sidebar_takes_the_middle_toggle_with_it(page, mode):
    """The same failure the drag handles could reintroduce: widening the left
    sidebar moves the middle panel without resizing it."""
    reset_widths(page, mode)
    drag(page, 'left', 140)
    assert_nothing_stranded(page, f"after widening the left sidebar in {mode}")
    drag(page, 'left', -140)
    assert_nothing_stranded(
        page, f"after narrowing the left sidebar again in {mode}")


@pytest.mark.parametrize('mode', ALL_VIEWS)
def test_no_control_is_stranded_in_any_view_or_collapse_order(page, mode):
    """Every view, and both collapse orders - the bug only appeared in one of
    them, so a single ordering would have missed it."""
    reset_widths(page, mode)
    order = keys_in(mode)

    for key in order:
        set_collapsed(page, key, False)
    assert_nothing_stranded(page, f"in {mode} with everything expanded")

    # left first, then the rest
    for key in order:
        set_collapsed(page, key, True)
        assert_nothing_stranded(page, f"in {mode} after collapsing {key} first")
    for key in order:
        set_collapsed(page, key, False)

    # and the reverse order, which is what actually stranded the middle toggle
    for key in reversed(order):
        set_collapsed(page, key, True)
        assert_nothing_stranded(page, f"in {mode} collapsing inwards, at {key}")
    for key in order:
        set_collapsed(page, key, False)


def test_nothing_is_stranded_across_a_view_switch(page):
    """A panel leaving layout entirely moves everything to its right."""
    reset_widths(page)
    set_collapsed(page, 'left', True)
    for mode in ('data-flow', 'pixel-map', 'data-flow', 'power', 'show-look',
                 'power', 'data-flow'):
        open_view(page, mode)
        assert_nothing_stranded(page, f"after switching to {mode}")
    set_collapsed(page, 'left', False)


# ── the contents fit the panel at the minimum ─────────────────────────────
#
# The clamp is shared by every panel, so a row that only fits at 260 is the
# row's bug and not the clamp's. The distro rows are the dense ones: rating,
# unit, voltage and phase, then a phasing select and a per-leg summary, all in
# a column ~119px wide once the sidebar's padding, its stable scrollbar gutter
# and the panel's own padding come off 180. They were laid out as flex rows
# with no flex-wrap, so at the minimum they overflowed and the sidebar's
# overflow-x:hidden simply cut them off - the phase select sliced in half and
# + Add pushed off the edge entirely.

DISTRO_SEED_JS = """() => {
    const app = window.app;
    // Answer the id only if this test made it, so the cleanup cannot delete a
    // distro the shared project already had.
    const added = app.getDistros().length ? null : app.addDistro().id;
    app.refreshDistroPanel();
    return { added: added, distros: app.getDistros().length };
}"""

DISTRO_CLEANUP_JS = """(id) => {
    if (!id) return;
    window.app.removeDistro(id);
    window.app.refreshDistroPanel();
}"""

# Measured against the HOST's content box, not the sidebar's: the sidebar's own
# padding would hide the first 10px of any overhang.
OVERFLOW_JS = """() => {
    const host = document.getElementById('power-distros');
    const box = host.getBoundingClientRect();
    const strays = [];
    host.querySelectorAll('*').forEach(el => {
        const r = el.getBoundingClientRect();
        if (r.width === 0 && r.height === 0) return;
        if (r.right > box.right + 0.5 || r.left < box.left - 0.5) {
            strays.push({
                tag: el.tagName,
                key: el.getAttribute('data-lrd-field') || el.className || null,
                over: Math.round(Math.max(r.right - box.right,
                                          box.left - r.left)),
            });
        }
    });
    // The centre line, not the top edge: a number input and a select are not
    // the same height, and align-items:center leaves their top edges several
    // px apart on the very same row.
    const mid = (cls) => {
        const el = host.querySelector('.' + cls);
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return Math.round(r.top + r.height / 2);
    };
    return { hostW: Math.round(box.width), scrollW: host.scrollWidth,
             clientW: host.clientWidth, strays: strays,
             rating: mid('distro-rating'), voltage: mid('distro-voltage'),
             phase: mid('distro-phase') };
}"""


@pytest.mark.parametrize('w', [MIN_W, DEFAULT_W])
def test_the_distro_rows_fit_inside_the_power_panel(page, w):
    reset_widths(page, 'power')
    seeded = page.evaluate(DISTRO_SEED_JS)
    try:
        assert seeded['distros'] > 0, f"no distro row to measure: {seeded}"
        if w != DEFAULT_W:
            assert drag(page, 'power', w - DEFAULT_W) == w
        page.wait_for_timeout(300)
        m = page.evaluate(OVERFLOW_JS)
        assert not m['strays'], (
            f"distro controls hang outside the panel at {w}px, where the "
            f"sidebar's overflow-x:hidden clips them: {m['strays']} "
            f"(over is px past the host's edge; host is {m['hostW']}px)")
        assert m['scrollW'] <= m['clientW'], (
            f"the distro list scrolls sideways at {w}px: content {m['scrollW']}px "
            f"in a {m['clientW']}px column")
    finally:
        page.evaluate(DISTRO_CLEANUP_JS, seeded['added'])


# The Splitters block above the distros carries the other row that comes and
# goes: "Max splitter" only renders while sharing is switched on, so both
# states have to fit the same 180px column.

SPLITTER_SEED_JS = """(enabled) => {
    const app = window.app;
    const l = app.currentLayer;
    if (!l) return null;
    // In-memory only - no updateLayers, so nothing is written to the server
    // and the shared project is handed back untouched by the cleanup.
    if (window.__spSaved === undefined) {
        window.__spSaved = l.powerSplitters ? JSON.parse(JSON.stringify(l.powerSplitters)) : null;
    }
    l.powerSplitters = { ...app.getPowerSplitters(l), enabled: enabled };
    app.refreshSplitterPanel();
    return { size: !!document.getElementById('power-splitters-maxways'),
             box: !!document.getElementById('power-splitters-enabled') };
}"""

SPLITTER_CLEANUP_JS = """() => {
    const app = window.app;
    const l = app.currentLayer;
    if (l && window.__spSaved !== undefined) {
        if (window.__spSaved === null) delete l.powerSplitters;
        else l.powerSplitters = window.__spSaved;
    }
    delete window.__spSaved;
    app.refreshSplitterPanel();
}"""

SPLITTER_OVERFLOW_JS = """() => {
    const host = document.getElementById('power-splitters');
    const box = host.getBoundingClientRect();
    const strays = [];
    host.querySelectorAll('*').forEach(el => {
        const r = el.getBoundingClientRect();
        if (r.width === 0 && r.height === 0) return;
        if (r.right > box.right + 0.5 || r.left < box.left - 0.5) {
            strays.push({ tag: el.tagName,
                          key: el.getAttribute('data-lrd-field') || el.className || null,
                          over: Math.round(Math.max(r.right - box.right,
                                                    box.left - r.left)) });
        }
    });
    return { hostW: Math.round(box.width), scrollW: host.scrollWidth,
             clientW: host.clientWidth, strays: strays };
}"""


@pytest.mark.parametrize('w', [MIN_W, DEFAULT_W])
@pytest.mark.parametrize('enabled', [False, True])
def test_the_splitter_rows_fit_inside_the_power_panel(page, w, enabled):
    reset_widths(page, 'power')
    seeded = page.evaluate(SPLITTER_SEED_JS, enabled)
    try:
        assert seeded and seeded['box'], (
            f"the splitter panel never rendered its enable checkbox: {seeded}")
        assert seeded['size'] is enabled, (
            f"the Max splitter row must follow the enable checkbox - present "
            f"only when sharing is on: {seeded}")
        if w != DEFAULT_W:
            assert drag(page, 'power', w - DEFAULT_W) == w
        page.wait_for_timeout(300)
        m = page.evaluate(SPLITTER_OVERFLOW_JS)
        assert not m['strays'], (
            f"splitter controls hang outside the panel at {w}px with sharing "
            f"{'on' if enabled else 'off'}: {m['strays']} (host {m['hostW']}px)")
        assert m['scrollW'] <= m['clientW'], (
            f"the splitter block scrolls sideways at {w}px: content "
            f"{m['scrollW']}px in a {m['clientW']}px column")
    finally:
        page.evaluate(SPLITTER_CLEANUP_JS)


# The soca rows carry three fields of their own now - a name, a distro and a
# home-run length - and the circuit label editor came into this panel with
# them. Both have to fit the same 180px column the distro rows were taught to.

NAMING_SEED_JS = """() => {
    const app = window.app;
    const l = app.currentLayer;
    if (!l) return null;
    // In-memory only, like the splitter seed: the stamp the editor sizes
    // itself from is a client-side figure, so nothing here is written to the
    // server and the shared project is handed back untouched.
    if (window.__nmSaved === undefined) {
        window.__nmSaved = l._powerCircuitsRequired;
    }
    l._powerCircuitsRequired = app.screenCircuitCount(l);
    const added = app.getDistros().length ? null : app.addDistro().id;
    app.refreshSocaRuns();
    app.refreshDistroPanel();
    app.updatePowerLabelEditor();
    return {
        added: added,
        socaRows: document.querySelectorAll('#power-soca-runs .power-soca-row').length,
        labelRows: document.querySelectorAll('#power-label-list > div').length,
    };
}"""

NAMING_CLEANUP_JS = """(id) => {
    const app = window.app;
    const l = app.currentLayer;
    if (l && window.__nmSaved !== undefined) {
        l._powerCircuitsRequired = window.__nmSaved;
    }
    delete window.__nmSaved;
    if (id) app.removeDistro(id);
    app.refreshSocaRuns();
    app.refreshDistroPanel();
    app.updatePowerLabelEditor();
}"""

# Same measurement as the distro rows above, against any host in the panel.
HOST_OVERFLOW_JS = """(hostId) => {
    const host = document.getElementById(hostId);
    if (!host) return null;
    const box = host.getBoundingClientRect();
    const strays = [];
    host.querySelectorAll('*').forEach(el => {
        const r = el.getBoundingClientRect();
        if (r.width === 0 && r.height === 0) return;
        if (r.right > box.right + 0.5 || r.left < box.left - 0.5) {
            strays.push({ tag: el.tagName,
                          key: el.getAttribute('data-lrd-field') || el.className || null,
                          over: Math.round(Math.max(r.right - box.right,
                                                    box.left - r.left)) });
        }
    });
    return { hostW: Math.round(box.width), scrollW: host.scrollWidth,
             clientW: host.clientWidth, strays: strays };
}"""


@pytest.mark.parametrize('w', [MIN_W, DEFAULT_W])
@pytest.mark.parametrize('host', ['power-soca-runs', 'power-label-list'])
def test_the_naming_rows_fit_inside_the_power_panel(page, host, w):
    reset_widths(page, 'power')
    seeded = page.evaluate(NAMING_SEED_JS)
    try:
        assert seeded, "no current layer to build a soca plan from"
        assert seeded['socaRows'] > 0, (
            f"the soca panel built no multi rows to measure: {seeded}")
        assert seeded['labelRows'] > 0, (
            f"the circuit label editor built no rows to measure: {seeded}")
        if w != DEFAULT_W:
            assert drag(page, 'power', w - DEFAULT_W) == w
        page.wait_for_timeout(300)
        m = page.evaluate(HOST_OVERFLOW_JS, host)
        assert m, f"#{host} is not in the document"
        assert not m['strays'], (
            f"#{host} controls hang outside their host at {w}px, where the "
            f"sidebar's overflow-x:hidden clips them: {m['strays']} "
            f"(host is {m['hostW']}px)")
        assert m['scrollW'] <= m['clientW'], (
            f"#{host} scrolls sideways at {w}px: content {m['scrollW']}px in "
            f"a {m['clientW']}px column")
    finally:
        page.evaluate(NAMING_CLEANUP_JS, seeded and seeded['added'])


def test_the_rating_row_is_one_line_at_the_default_and_wraps_at_the_minimum(page):
    """The wrap has to be a wrap, not a permanent restack: at the 260px default
    rating, voltage and phase still read as one line, and only the drag to the
    clamp breaks them apart."""
    reset_widths(page, 'power')
    seeded = page.evaluate(DISTRO_SEED_JS)
    try:
        wide = page.evaluate(OVERFLOW_JS)
        assert wide['rating'] == wide['voltage'] == wide['phase'], (
            f"the rating row is no longer one line at the {DEFAULT_W}px "
            f"default: {wide}")
        assert drag(page, 'power', MIN_W - DEFAULT_W) == MIN_W
        page.wait_for_timeout(300)
        narrow = page.evaluate(OVERFLOW_JS)
        assert narrow['voltage'] > narrow['rating'] + 6, (
            f"the rating row did not wrap at {MIN_W}px, so the fit assertions "
            f"prove nothing: {narrow}")
        assert narrow['voltage'] == narrow['phase'], (
            f"voltage and phase parted company - they travel as one group so "
            f"they drop to the next line together: {narrow}")
    finally:
        page.evaluate(DISTRO_CLEANUP_JS, seeded['added'])


@pytest.mark.parametrize('key', sorted(VIEW_OF))
def test_a_collapsed_middle_panel_stays_collapsed_across_a_view_switch(page, key):
    """Collapsing a panel and then leaving its view must not silently
    re-expand it on the way back - the visibility pass touches .view-hidden and
    nothing else."""
    mode = VIEW_OF[key]
    reset_widths(page, mode)
    set_collapsed(page, key, True)
    open_view(page, 'pixel-map')
    open_view(page, mode)
    still = page.evaluate(
        "(id) => document.getElementById(id).classList.contains('collapsed')",
        PANELS[key])
    assert still, f"the {key} panel came back expanded after a view switch"
    assert_nothing_stranded(page, f"back in {mode} with {key} still collapsed")
    set_collapsed(page, key, False)
