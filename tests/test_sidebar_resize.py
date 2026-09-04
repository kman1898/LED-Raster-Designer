"""Drag-resizable docked panels: left sidebar, right sidebar - and the
hardware dock, the same system turned on its side.

The resize code (theme.js) is a table of panels, the same shape as the
collapse table in app-core.js initSidebarToggles, and these tests pin the
behaviour that table has to keep producing. The Signal and Power middle
columns were rows of both tables once; the consolidation retired them - the
hardware itself (processors, cards, boxes, distros, multis) lives in the
hardware dock now, and the per-screen knobs moved into the LEFT sidebar's
Data Settings / Power Settings panels. So the tables carry exactly three
rows: left, right, and the dock.

The hardware dock is the horizontal member of both tables: it collapses from
a chevron pinned above its top edge (its own ledRasterSidebarCollapsed_dock
key) and drag-resizes in HEIGHT from a strip on that same edge (lrd_dock_h /
--lrd-dock-h), with its own clamp - so the dock tests below are the sidebar
assertions transposed, not a separate mechanism's.

What these tests pin:

* Every panel carries a drag strip on its inner edge, and dragging it really
  changes the panel's width - not just the CSS variable.
* The width clamps between 180 and 560 so a panel can neither vanish nor
  swallow the canvas, and it survives a reload.
* The retired middle panels are GONE, not dormant: no resize/collapse pass
  ever writes their storage keys again, and no data/power drag strip exists
  in any view. A leftover strip would be a live bug - a 7px column of the
  drawing that silently starts a resize instead of a selection.
* The collapse toggle stays on top of the strip. They occupy the same seam,
  and the toggle is the only way back from a collapsed panel.
* Dragging re-measures the canvas. The canvas backing store is sized from its
  wrapper in setupCanvas(), whose only automatic trigger is the window resize
  listener, so before this change a drag left the canvas painting at its
  pre-drag pixel width until the window itself was resized.
* No toggle and no drag strip is ever left floating over the drawing.
  Reported as "the sidebar is still floating in the air": collapsing a panel
  used to reposition only its own toggle, so collapsing the left sidebar
  moved the next flex member without telling its controls. Today that next
  member is the hardware dock, whose chevron and strip ride its top edge.
  These assert on coordinates, because in that bug every class was already
  correct.
* The re-homed power surfaces fit their new homes: the per-screen splitter
  and label knobs fit the left sidebar down to its 180px clamp, the distro
  headers fit the dock without a sideways scroll, and the distro's
  electrical setup fits its own gear popover.

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

# The dock's own clamp (theme.js dock row), mirrored for the same reason.
# 100 is its header plus one unit head and one chip row - the smallest tray
# that still shows a draggable chip; 420 keeps the canvas the star of the
# column; 172 is the old fixed footprint (21px header + 1px border + the
# 150px body cap), so an untouched layout looks exactly as it did.
DOCK_MIN_H = 100
DOCK_MAX_H = 420
DOCK_DEFAULT_H = 172

# Wide enough that the canvas wrapper still has slack after a panel grows to
# its maximum - at 1280 the canvas container is already pinned to its own
# minimum width, which would make the re-measure assertions vacuous.
VIEWPORT = {'width': 1700, 'height': 900}

# The vertical panels still in the tables. The dock is the third row of both
# tables and keeps its own constants above.
PANELS = {
    'left': 'left-sidebar',
    'right': 'right-sidebar',
}
PANEL_KEYS = ['left', 'right']

# Which way a positive-x drag moves each panel's width: the left sidebar's
# strip is on its right edge (drag right = wider), the right sidebar's on its
# left edge (drag right = narrower).
GROW = {'left': 1, 'right': -1}

# The retired middle columns. Their strips must not EXIST anywhere and their
# storage keys must never be written again - the negative pins below.
RETIRED = ['data', 'power']
RETIRED_STORAGE = [
    'lrd_data_w', 'lrd_power_w',
    'ledRasterSidebarCollapsed_data', 'ledRasterSidebarCollapsed_power',
]

ALL_VIEWS = ['pixel-map', 'cabinet-id', 'show-look', 'data-flow', 'power']


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
    """Back to the default size and expanded on every panel - the dock
    included - through the same localStorage keys app-core.js and theme.js
    read on boot, so each test starts from a known geometry no matter what
    the one before it left collapsed. Only the surviving keys: seeding the
    retired data/power keys here would defeat the never-written pins."""
    page.evaluate(
        """(args) => {
            ['lrd_left_w', 'lrd_right_w'].forEach(
                k => localStorage.setItem(k, String(args.w)));
            localStorage.setItem('lrd_dock_h', String(args.dockH));
            ['left', 'right', 'dock'].forEach(
                k => localStorage.setItem('ledRasterSidebarCollapsed_' + k, '0'));
        }""", {'w': DEFAULT_W, 'dockH': DOCK_DEFAULT_H})
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


def widen(page, key, by):
    """Drag a panel `by` px WIDER regardless of which edge its strip is on."""
    return drag(page, key, by * GROW[key])


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
def test_every_docked_panel_has_a_drag_strip_and_no_retired_strip_exists(page, mode):
    """Left and right are in every view now that the middle columns are gone -
    and gone means gone: a data/power strip existing in ANY view would be a
    7px slice of the canvas that starts a resize of a panel that is not
    there."""
    reset_widths(page, mode)
    for key in PANEL_KEYS:
        assert handle(page, key), f"the {key} panel has no resize handle in {mode}"
    leftovers = page.evaluate(
        """(keys) => keys.filter(k => document.querySelector(
               '.lrd-resize-handle[data-lrd-resize="' + k + '"]'))""",
        RETIRED)
    assert not leftovers, (
        f"the retired {leftovers} strip(s) still exist in the DOM in {mode} - "
        f"the middle sidebars were removed in the consolidation")


@pytest.mark.parametrize('key,edge', [('left', 'right'), ('right', 'left')])
def test_each_strip_sits_on_its_panels_inner_edge(page, key, edge):
    reset_widths(page)
    h = handle(page, key)
    rect = page.evaluate(
        "(id) => { const r = document.getElementById(id).getBoundingClientRect();"
        "return { left: r.left, right: r.right }; }", PANELS[key])
    target = rect['right'] if edge == 'right' else rect['left']
    assert abs(h['left'] - target) <= 6, (
        f"the {key} panel's strip is not on its {edge} edge: "
        f"strip at {h['left']}, edge at {target}")


# ── dragging a sidebar ────────────────────────────────────────────────────

@pytest.mark.parametrize('key', PANEL_KEYS)
def test_dragging_a_sidebar_changes_its_width(page, key):
    reset_widths(page)
    before = width(page, key)
    after = widen(page, key, 120)
    assert after > before + 80, f"the {key} panel did not widen: {before} -> {after}"
    assert abs(after - (before + 120)) <= 8, (
        f"the {key} panel did not follow the pointer: {before} -> {after}")


@pytest.mark.parametrize('key', PANEL_KEYS)
def test_a_sidebars_width_survives_a_reload(page, key):
    reset_widths(page)
    dragged = widen(page, key, 120)

    page.reload(wait_until='domcontentloaded')
    page.wait_for_timeout(2000)
    open_view(page, 'data-flow')
    assert abs(width(page, key) - dragged) <= 2, (
        f"the {key} panel came back at {width(page, key)}, not {dragged}")

    # And the other way round, so this cannot pass on a panel that is simply
    # always wide.
    reset_widths(page)
    assert abs(width(page, key) - DEFAULT_W) <= 2, (
        f"the {key} panel ignored a stored default width")


@pytest.mark.parametrize('key', PANEL_KEYS)
def test_a_sidebar_clamps_at_the_minimum(page, key):
    reset_widths(page)
    assert widen(page, key, -600) == MIN_W, (
        f"the {key} panel can be dragged narrower than the clamp")


@pytest.mark.parametrize('key', PANEL_KEYS)
def test_a_sidebar_clamps_at_the_maximum(page, key):
    reset_widths(page)
    assert widen(page, key, 600) == MAX_W, (
        f"the {key} panel can be dragged wider than the clamp")


@pytest.mark.parametrize('mode', ['data-flow', 'power'])
def test_resizing_one_panel_leaves_the_others_alone(page, mode):
    reset_widths(page, mode)
    drag(page, 'left', 100)
    assert width(page, 'left') == DEFAULT_W + 100, "the left sidebar did not resize"
    assert width(page, 'right') == DEFAULT_W, (
        "resizing the left sidebar resized the right panel with it")


def test_no_resize_or_collapse_pass_writes_the_retired_keys(page):
    """The Signal and Power sidebars did not merely hide - their rows left
    both tables. A full resize pass and a full collapse pass over everything
    that still exists must write only the survivors' keys; a data/power key
    reappearing means a retired row grew back."""
    reset_widths(page, 'power')
    page.evaluate(
        "(keys) => keys.forEach(k => localStorage.removeItem(k))",
        RETIRED_STORAGE)

    # A resize pass over every surviving member...
    widen(page, 'left', 60)
    widen(page, 'right', 60)
    drag_dock(page, -40)
    # ...and a collapse/expand pass.
    for key in PANEL_KEYS:
        set_collapsed(page, key, True)
        set_collapsed(page, key, False)
    page.locator('#hardware-dock-toggle').click()
    page.wait_for_timeout(500)
    page.locator('#hardware-dock-toggle').click()
    page.wait_for_timeout(500)

    written = page.evaluate(
        """(keys) => Object.fromEntries(
               keys.map(k => [k, localStorage.getItem(k)])
                   .filter(([, v]) => v !== null))""",
        RETIRED_STORAGE)
    assert not written, (
        f"a resize/collapse pass wrote the retired middle panels' storage "
        f"keys: {written}")


# ── the strip leaves when the panel does ──────────────────────────────────

@pytest.mark.parametrize('key', PANEL_KEYS)
def test_a_strip_is_gone_while_the_panel_is_collapsed(page, key):
    reset_widths(page)
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
    for key in PANEL_KEYS:
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

@pytest.mark.parametrize('key', PANEL_KEYS)
def test_dragging_a_panel_re_measures_the_canvas(page, key):
    """setupCanvas() sizes the canvas from its wrapper and only runs itself on
    a window resize, so a drag used to leave the canvas painting at its
    pre-drag pixel width until the window was touched."""
    reset_widths(page)
    assert_canvas_matches_wrapper(page, "a reset")
    widen(page, key, 140)
    assert_canvas_matches_wrapper(page, f"dragging the {key} panel")


@pytest.mark.parametrize('key', PANEL_KEYS)
def test_the_canvas_keeps_up_during_the_drag_not_only_at_the_end(page, key):
    """The width transition is suppressed while dragging, so every frame is
    already in layout - the canvas is re-measured per move rather than left to
    the staged settle on mouseup."""
    reset_widths(page)
    h = handle(page, key)
    dx = GROW[key] * 60
    page.mouse.move(h['x'], h['y'])
    page.mouse.down()
    page.mouse.move(h['x'] + dx, h['y'])
    page.mouse.move(h['x'] + dx * 2, h['y'])
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
# The cause was that collapsing a panel repositioned only its OWN toggle,
# while collapsing the left sidebar MOVES the next flex member without
# changing its size. Its controls were never told, and the ResizeObserver
# that was meant to be the safety net watches size, not position, so it never
# fired either. The middle sidebars that first showed the bug are gone, but
# the mechanism is not: the hardware dock's chevron and strip ride the tray's
# top edge and the tray's left edge follows the left sidebar, so the same
# orphaning is still one missed reposition away.
#
# These assert on geometry rather than on a class: in the reported bug every
# class was correct and only the coordinates were wrong.

STRAYS_JS = """() => {
    const shown = el => el && getComputedStyle(el).display !== 'none';
    const canvas = document.getElementById('canvas-container').getBoundingClientRect();
    const panels = [
        { key: 'left',  sidebar: 'left-sidebar',  toggle: 'left-sidebar-toggle',  inner: 'right' },
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
    // The hardware dock is the horizontal member of the same family: in its
    // views it must sit flush under the canvas wrapper and inside the canvas
    // column, and out of them it must be out of layout entirely - a tray
    // floating over the canvas is the same class of bug as a stranded
    // toggle, and the two panel rows above would never see it.
    const dock = document.getElementById('hardware-dock');
    const dockControls = [
        ['dock-toggle', document.getElementById('hardware-dock-toggle'), 'bottom'],
        ['dock-strip', document.querySelector(
            '.lrd-resize-handle[data-lrd-resize="dock"]'), 'top'],
    ];
    if (dock && shown(dock)) {
        const wrap = document.getElementById('canvas-wrapper')
            .getBoundingClientRect();
        const r = dock.getBoundingClientRect();
        const drift = Math.abs(r.top - wrap.bottom);
        if (drift > 8) {
            strays.push({ kind: 'dock', key: 'hardware', drift: Math.round(drift),
                          at: Math.round(r.top), edge: Math.round(wrap.bottom),
                          intoCanvas: Math.round(wrap.bottom - r.top) });
        }
        if (r.left < canvas.left - 0.5 || r.right > canvas.right + 0.5) {
            strays.push({ kind: 'dock-width', key: 'hardware',
                          at: Math.round(r.left),
                          edge: Math.round(canvas.left),
                          intoCanvas: Math.round(canvas.right - r.right) });
        }
        // Its collapse toggle and drag strip are the transposed control
        // rows: each must sit flush on the tray's TOP edge (the toggle by
        // its bottom, the strip by its own top edge), never adrift over the
        // drawing - the sidebar assertions above, turned on their side.
        dockControls.forEach(([kind, el, side]) => {
            if (!shown(el)) return;
            const rr = el.getBoundingClientRect();
            const d = Math.abs(rr[side] - r.top);
            if (d > 8) {
                strays.push({ kind: kind, key: 'hardware',
                              drift: Math.round(d),
                              at: Math.round(rr[side]),
                              edge: Math.round(r.top),
                              intoCanvas: Math.round(r.top - rr[side]) });
            }
        });
    } else {
        // Out of its views the dock leaves layout entirely, and so must
        // both of its controls - a chevron or strip floating over the
        // canvas in Pixel Map is the same class of bug as a stranded
        // sidebar toggle.
        dockControls.forEach(([kind, el]) => {
            if (!shown(el)) return;
            const rr = el.getBoundingClientRect();
            strays.push({ kind: kind, key: 'hardware',
                          reason: 'dock not in layout',
                          at: Math.round(rr.top),
                          intoCanvas: Math.round(canvas.bottom - rr.top) });
        });
    }
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


@pytest.mark.parametrize('mode', ['data-flow', 'power'])
def test_collapsing_the_left_sidebar_takes_the_dock_controls_with_it(page, mode):
    """Collapsing the left sidebar moves the canvas column - and the dock
    with it - without resizing either, which is exactly the shape of the
    original stranded-toggle bug: reposition is nobody's job unless the
    positioners are re-run."""
    reset_widths(page, mode)
    set_collapsed(page, 'left', True)
    page.wait_for_timeout(500)
    assert_nothing_stranded(
        page, f"after collapsing the left sidebar in {mode}")
    set_collapsed(page, 'left', False)
    assert_nothing_stranded(
        page, f"after expanding the left sidebar again in {mode}")


@pytest.mark.parametrize('mode', ['data-flow', 'power'])
def test_resizing_the_left_sidebar_takes_the_dock_with_it(page, mode):
    """The same failure the drag handles could reintroduce: widening the left
    sidebar moves the canvas column and the tray docked under it without
    resizing the sidebar's own controls."""
    reset_widths(page, mode)
    drag(page, 'left', 140)
    assert_nothing_stranded(page, f"after widening the left sidebar in {mode}")
    drag(page, 'left', -140)
    assert_nothing_stranded(
        page, f"after narrowing the left sidebar again in {mode}")


@pytest.mark.parametrize('mode', ALL_VIEWS)
def test_no_control_is_stranded_in_any_view_or_collapse_order(page, mode):
    """Every view, and both collapse orders - the original bug only appeared
    in one of them, so a single ordering would have missed it."""
    reset_widths(page, mode)
    order = PANEL_KEYS

    for key in order:
        set_collapsed(page, key, False)
    assert_nothing_stranded(page, f"in {mode} with everything expanded")

    # left first, then the rest
    for key in order:
        set_collapsed(page, key, True)
        assert_nothing_stranded(page, f"in {mode} after collapsing {key} first")
    for key in order:
        set_collapsed(page, key, False)

    # and the reverse order, which is what actually stranded a toggle
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


# ── the re-homed power surfaces fit their new homes ───────────────────────
#
# The consolidation moved the Power sidebar's contents to two places: the
# per-screen knobs (breakout, splitters, brackets, the circuit label
# template) into the LEFT sidebar's Power Settings panel, and the hardware
# itself (distro headers, multis, circuit chips) into the hardware dock. The
# left sidebar shares the 180-560 clamp with every panel, so a knob row that
# only fits at 260 is the row's bug and not the clamp's; the dock reflows
# instead of clamping, so its bar is "never a sideways scroll".

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

# The distro's dock footprint: its header controls (the inline name, the
# Balance button, the gear, the legs line when a 3-phase load exists) must
# stay inside the tray, and the tray's body must reflow rather than scroll
# sideways - the dock spans the whole canvas column, so a horizontal
# scrollbar means a row refused to wrap.
DOCK_DISTRO_FIT_JS = """() => {
    const dock = document.getElementById('hardware-dock');
    const body = document.getElementById('hardware-dock-body');
    const box = dock.getBoundingClientRect();
    const strays = [];
    dock.querySelectorAll(
        '.hw-dock-name, .hw-dock-gear, .hw-dock-legs, '
        + '[data-lrd-field^="distro-balance-"]').forEach(el => {
        const r = el.getBoundingClientRect();
        if (r.width === 0 && r.height === 0) return;
        if (r.right > box.right + 0.5 || r.left < box.left - 0.5) {
            strays.push({
                key: el.getAttribute('data-lrd-field') || el.className,
                over: Math.round(Math.max(r.right - box.right,
                                          box.left - r.left)),
            });
        }
    });
    return { dockW: Math.round(box.width),
             scrollW: body.scrollWidth, clientW: body.clientWidth,
             headers: dock.querySelectorAll('[data-hwpop^="distro-"]').length,
             strays: strays };
}"""


def test_the_distro_rows_fit_inside_the_hardware_dock(page):
    """The distro rows left the Power sidebar for the dock, so the fit
    contract moved with them: at the dock's default height the header
    controls stay inside the tray and the body never scrolls sideways."""
    reset_widths(page, 'power')
    seeded = page.evaluate(DISTRO_SEED_JS)
    try:
        assert seeded['distros'] > 0, f"no distro row to measure: {seeded}"
        page.wait_for_timeout(300)
        m = page.evaluate(DOCK_DISTRO_FIT_JS)
        assert m['headers'] > 0, (
            f"the dock built no distro section to measure: {m}")
        assert not m['strays'], (
            f"distro header controls hang outside the dock's box: "
            f"{m['strays']} (over is px past the tray's edge; the tray is "
            f"{m['dockW']}px wide)")
        assert m['scrollW'] <= m['clientW'], (
            f"the dock body scrolls sideways: content {m['scrollW']}px in a "
            f"{m['clientW']}px tray - the dock reflows, it never scrolls "
            f"horizontally")
    finally:
        page.evaluate(DISTRO_CLEANUP_JS, seeded['added'])


# The per-screen knobs live in the LEFT sidebar's Power Settings panel now:
# breakout type, the splitter enable and its Max splitter row, the map
# brackets, and the circuit label template/apply pair. The Max splitter row
# is a static row toggled display:flex/none by refreshSplitterPanel, so both
# states have to fit the same 180px column.

POWER_KNOB_IDS = [
    'power-breakout-type',
    'power-splitters-enabled',
    'power-splitters-maxways-row',
    'power-splitters-maxways',
    'power-splitters-maxways-custom',
    'show-soca-brackets',
    'power-label-template',
    'power-label-bulk',
]

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
    const row = document.getElementById('power-splitters-maxways-row');
    return { box: !!document.getElementById('power-splitters-enabled'),
             rowDisplay: row ? getComputedStyle(row).display : null };
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

# Each knob and its block container, measured against the LEFT sidebar's own
# box: a control poking past the sidebar is clipped by its overflow-x:hidden,
# which is exactly the silent-truncation bug the old panel had.
KNOB_OVERFLOW_JS = """(ids) => {
    const side = document.getElementById('left-sidebar');
    const box = side.getBoundingClientRect();
    const strays = [];
    ids.forEach(id => {
        const el = document.getElementById(id);
        if (!el) { strays.push({ id: id, missing: true }); return; }
        const block = el.closest('.info-row') || el.parentElement;
        [['control', el], ['block', block]].forEach(([kind, node]) => {
            if (!node) return;
            if (getComputedStyle(node).display === 'none') return;
            const r = node.getBoundingClientRect();
            if (r.width === 0 && r.height === 0) return;
            if (r.right > box.right + 0.5 || r.left < box.left - 0.5) {
                strays.push({
                    id: id, kind: kind,
                    over: Math.round(Math.max(r.right - box.right,
                                              box.left - r.left)),
                });
            }
        });
    });
    return { sideW: Math.round(box.width), strays: strays };
}"""


@pytest.mark.parametrize('w', [MIN_W, DEFAULT_W])
@pytest.mark.parametrize('enabled', [False, True])
def test_the_power_knobs_fit_inside_the_left_sidebar(page, w, enabled):
    """The splitter and label knobs came into the left sidebar, so they must
    fit its clamp exactly as the distro rows once had to fit the Power
    panel's - and the Max splitter row must follow the enable checkbox,
    shown only while sharing is on (a static row refreshSplitterPanel
    toggles between display:flex and none)."""
    reset_widths(page, 'power')
    seeded = page.evaluate(SPLITTER_SEED_JS, enabled)
    try:
        assert seeded and seeded['box'], (
            f"the Power Settings panel has no splitter enable checkbox: {seeded}")
        assert seeded['rowDisplay'] == ('flex' if enabled else 'none'), (
            f"the Max splitter row must follow the enable checkbox - "
            f"display:flex only while sharing is on: {seeded}")
        if w != DEFAULT_W:
            assert drag(page, 'left', w - DEFAULT_W) == w
        page.wait_for_timeout(300)
        m = page.evaluate(KNOB_OVERFLOW_JS, POWER_KNOB_IDS)
        assert not m['strays'], (
            f"power knobs hang outside the left sidebar at {w}px with sharing "
            f"{'on' if enabled else 'off'}: {m['strays']} (over is px past "
            f"the sidebar's edge; the sidebar is {m['sideW']}px)")
    finally:
        page.evaluate(SPLITTER_CLEANUP_JS)


# The distro's electrical setup - rating, voltage, phase, phasing, location,
# remove - moved off the row entirely, into the ⚙ gear popover. The old
# "rating row wraps at the minimum" test pinned how those fields shared a
# 180px column; the popover sizes itself, so its contract is simpler: it is
# visible when the gear is clicked and nothing inside it overflows its own
# box.

GEAR_POPOVER_FIT_JS = """() => {
    const pop = document.getElementById('hw-gear-popover');
    if (!pop) return null;
    const s = getComputedStyle(pop);
    const box = pop.getBoundingClientRect();
    const strays = [];
    pop.querySelectorAll('*').forEach(el => {
        const r = el.getBoundingClientRect();
        if (r.width === 0 && r.height === 0) return;
        if (r.right > box.right + 0.5 || r.left < box.left - 0.5
                || r.bottom > box.bottom + 0.5 || r.top < box.top - 0.5) {
            strays.push({
                tag: el.tagName,
                key: el.getAttribute('data-lrd-field') || el.className || null,
                over: Math.round(Math.max(
                    r.right - box.right, box.left - r.left,
                    r.bottom - box.bottom, box.top - r.top)),
            });
        }
    });
    return { display: s.display,
             w: Math.round(box.width), h: Math.round(box.height),
             fields: pop.querySelectorAll('[data-lrd-field]').length,
             outputs: pop.querySelectorAll(
                 '[data-lrd-field^="distro-out-"]').length,
             strays: strays };
}"""


def test_the_distro_gear_popover_shows_its_controls_inside_its_own_box(page):
    """Rating, voltage, phase, phasing and location live behind the distro's
    gear now. Clicking the gear must produce a visible popover whose
    controls all sit inside it - the popover's box is the new column the
    old rating row had to fit. The OUTPUTS checklist (2026-08-31, three
    tick rows: Soca 208, Soca 120, L21-30) is part of the same box and the
    same rule - the concept mock's rows ran past its edge, and this is the
    pin that keeps the real ones inside."""
    reset_widths(page, 'power')
    seeded = page.evaluate(DISTRO_SEED_JS)
    try:
        assert seeded['distros'] > 0, f"no distro to open a gear on: {seeded}"
        page.wait_for_timeout(300)
        page.locator('[data-hwpop^="distro-"]').first.click()
        page.wait_for_timeout(300)
        m = page.evaluate(GEAR_POPOVER_FIT_JS)
        assert m, "clicking the distro gear made no #hw-gear-popover"
        assert m['display'] != 'none' and m['w'] > 1 and m['h'] > 1, (
            f"the gear popover is not visible: {m}")
        assert m['fields'] > 0, (
            f"the gear popover opened empty - no data-lrd-field controls: {m}")
        assert m['outputs'] == 3, (
            f"the gear popover carries no OUTPUTS checklist (three ticks): {m}")
        assert not m['strays'], (
            f"gear popover controls overflow the popover's own box: "
            f"{m['strays']} (popover is {m['w']}x{m['h']}px)")
        page.keyboard.press('Escape')
        page.wait_for_timeout(200)
    finally:
        page.evaluate(DISTRO_CLEANUP_JS, seeded['added'])


# One of every gear the dock draws - a processor with slots to fill, a slot
# card, a breakout box hung on it, and a distro - so every popover kind can
# be opened in turn. An H9 rather than the MX40 Pro: the MX40's card is the
# machine's own outputs and carries no Remove, and a Remove that is there
# is what the test below measures.
POPOVER_KINDS_SEED_JS = """async () => {
    const add = await (await fetch('/api/processors', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({deviceId: 'novastar-h9', name: 'POPTEST'}),
    })).json();
    const proc = add.resolved[add.resolved.length - 1];
    const slot = await (await fetch(`/api/processors/${proc.id}/slots/0`, {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({deviceId: 'novastar-card-h-16xrj45-2xfiber'}),
    })).json();
    const card = slot.resolved.find(p => p.id === proc.id).slots[0].card;
    let box = null;
    for (const dev of ['novastar-cvt4k-s', 'novastar-cvt10']) {
        const r = await fetch(
            `/api/processors/${proc.id}/cards/${card.id}/cvts`, {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({deviceId: dev})});
        if (r.ok) { box = (await r.json()).resolved
            .find(p => p.id === proc.id).slots[0].card.cvts[0]; break; }
    }
    const app = window.app;
    const distro = app.getDistros().length ? null : app.addDistro().id;
    await app.refreshProcessors();
    app.refreshDistroPanel();
    return {procId: proc.id, cardId: card.id, boxId: box && box.id,
            distroId: app.getDistros()[0].id, addedDistro: distro};
}"""

POPOVER_KINDS_CLEANUP_JS = """async (ids) => {
    await fetch(`/api/processors/${ids.procId}`, {method: 'DELETE'});
    if (ids.addedDistro) window.app.removeDistro(ids.addedDistro);
    await window.app.refreshProcessors();
    window.app.refreshDistroPanel();
}"""

# The popover's Remove: where it is against the window and the popover's
# own box, and whether a click aimed at its middle would land on it - the
# hit test is the part a bounding box cannot answer, since a button under a
# clipped, scrolling body has a rect and no reachable pixels.
POPOVER_REMOVE_JS = """() => {
    const pop = document.getElementById('hw-gear-popover');
    if (!pop || pop.style.display !== 'block') return null;
    const box = pop.getBoundingClientRect();
    const btn = pop.querySelector('.hw-pop-remove');
    if (!btn) return {label: null};
    const r = btn.getBoundingClientRect();
    const hit = document.elementFromPoint(r.left + r.width / 2,
                                          r.top + r.height / 2);
    return {
        label: btn.textContent,
        inViewport: r.top >= 0 && r.bottom <= window.innerHeight
            && r.left >= 0 && r.right <= window.innerWidth,
        inPopover: r.top >= box.top - 0.5 && r.bottom <= box.bottom + 0.5,
        clickable: !!hit && (hit === btn || btn.contains(hit)),
        popInViewport: box.top >= 0 && box.bottom <= window.innerHeight,
        top: Math.round(r.top), bottom: Math.round(r.bottom),
        vh: window.innerHeight,
    };
}"""


def test_every_gear_popovers_remove_is_on_screen_at_a_short_window(page):
    """Remove processor, Remove card, Remove box, Remove distro: each lives
    at the bottom of its gear popover, and at a laptop-height window the
    popover used to clamp its height and scroll silently - the button was
    in the DOM, below the fold, with nothing saying so (2026-09-03: "we
    have no way of deleting a distro or processor"). The button now sits in
    a footer pinned to the popover's bottom edge, so at 700px every one of
    the four must be inside the viewport, inside the popover's box, and the
    element a click at its center would land on."""
    reset_widths(page, 'data-flow')
    page.set_viewport_size({'width': 1280, 'height': 700})
    page.wait_for_timeout(300)
    ids = page.evaluate(POPOVER_KINDS_SEED_JS)
    try:
        assert ids['boxId'], f"no breakout box would go on the card: {ids}"
        page.wait_for_timeout(400)
        kinds = [('data-flow', f'proc-{ids["procId"]}', 'Remove processor'),
                 ('data-flow', f'card-{ids["cardId"]}', 'Remove card'),
                 ('data-flow', f'box-{ids["boxId"]}', 'Remove box'),
                 ('power', f'distro-{ids["distroId"]}', 'Remove distro')]
        seen = {}
        for mode, key, label in kinds:
            open_view(page, mode)
            page.evaluate("""(k) => {
                const el = document.querySelector(`[data-hwpop="${k}"]`);
                if (el) el.scrollIntoView({block: 'nearest'});
            }""", key)
            page.locator(f'[data-hwpop="{key}"]').click()
            page.wait_for_timeout(300)
            m = page.evaluate(POPOVER_REMOVE_JS)
            seen[label] = m
            assert m, f"clicking the {key} gear opened no popover"
            assert m['label'] == label, (
                f"the {key} popover carries no {label!r}: {m}")
            assert m['inViewport'] and m['popInViewport'], (
                f"{label} sits off-screen at a {m['vh']}px window: {m}")
            assert m['inPopover'], (
                f"{label} lies outside the popover's own box: {m}")
            assert m['clickable'], (
                f"a click at the middle of {label} would not land on it: {m}")
            page.keyboard.press('Escape')
            page.wait_for_timeout(150)
        assert len(seen) == 4, seen
    finally:
        page.keyboard.press('Escape')
        page.evaluate(POPOVER_KINDS_CLEANUP_JS, ids)
        page.set_viewport_size(VIEWPORT)
        page.wait_for_timeout(300)


# ── the hardware dock: the same system turned on its side ─────────────────
#
# The dock collapses from a chevron above its top edge and drag-resizes in
# height from a strip on that same edge. Both are rows of the sidebar tables
# (initSidebarToggles, theme.js PANELS) rather than a parallel mechanism, so
# these are the sidebar assertions transposed to y - including the ones that
# earn their keep only when something regresses: the clamp, the persistence,
# the strip leaving with the tray, and the canvas keeping up mid-drag.

DOCK_VIEWS = ['data-flow', 'power']

DOCK_HANDLE_JS = """() => {
    const h = document.querySelector(
        '.lrd-resize-handle[data-lrd-resize="dock"]');
    if (!h) return null;
    if (getComputedStyle(h).display === 'none') return null;
    const r = h.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return null;
    // x deliberately off-centre: the collapse toggle sits over the strip's
    // middle, exactly as the sidebar toggles sit over theirs.
    return { x: r.left + 80, y: r.top + r.height / 2,
             top: r.top, left: r.left, width: r.width };
}"""

DOCK_TOGGLE_SHOWN_JS = """() => {
    const b = document.getElementById('hardware-dock-toggle');
    return !!(b && getComputedStyle(b).display !== 'none');
}"""

DOCK_STATE_JS = """() => {
    const dock = document.getElementById('hardware-dock');
    const r = dock.getBoundingClientRect();
    return {
        collapsed: dock.classList.contains('collapsed'),
        height: Math.round(r.height),
        stored: localStorage.getItem('ledRasterSidebarCollapsed_dock'),
        storedH: localStorage.getItem('lrd_dock_h'),
    };
}"""


def dock_height(page):
    return page.evaluate(
        """() => Math.round(document.getElementById('hardware-dock')
               .getBoundingClientRect().height)""")


def drag_dock(page, dy):
    """Drag the dock's strip by dy pixels (negative = up = taller) and answer
    the dock's new height. Stepped moves, like drag() above: the handler
    works off mousemove, and a single jump exercises a path no user can."""
    h = page.evaluate(DOCK_HANDLE_JS)
    assert h, "no visible resize strip for the dock"
    page.mouse.move(h['x'], h['y'])
    page.mouse.down()
    for step in range(1, 5):
        page.mouse.move(h['x'], h['y'] + dy * step / 4.0)
    page.mouse.up()
    page.wait_for_timeout(400)
    return dock_height(page)


@pytest.mark.parametrize('mode', ALL_VIEWS)
def test_the_dock_strip_and_toggle_live_only_in_the_hardware_views(page, mode):
    """Both controls belong to the tray, and the tray belongs to Data and
    Power - anywhere else a strip or chevron over the drawing is the stranded-
    control bug all over again."""
    reset_widths(page, mode)
    present = mode in DOCK_VIEWS
    assert (page.evaluate(DOCK_HANDLE_JS) is not None) == present, (
        f"the dock's drag strip is {'missing' if present else 'present'} "
        f"in {mode}")
    assert page.evaluate(DOCK_TOGGLE_SHOWN_JS) == present, (
        f"the dock's collapse toggle is "
        f"{'missing' if present else 'present'} in {mode}")
    assert_nothing_stranded(page, f"in {mode} with the dock at its default")


def test_dragging_the_dock_strip_changes_its_height(page):
    reset_widths(page, 'data-flow')
    before = dock_height(page)
    assert before == DOCK_DEFAULT_H, (
        f"the dock did not start at its default height: {before}")
    after = drag_dock(page, -120)
    assert abs(after - (before + 120)) <= 8, (
        f"the dock did not follow the pointer: {before} -> {after}")
    assert_canvas_matches_wrapper(page, "dragging the dock taller")
    # and the other direction, so this cannot pass on a tray that only grows
    down = drag_dock(page, 90)
    assert abs(down - (after - 90)) <= 8, (
        f"the dock did not shrink back: {after} -> {down}")
    # the height is the dock's own: no sidebar moved with it
    for key in PANEL_KEYS:
        assert width(page, key) == DEFAULT_W, (
            f"resizing the dock resized the {key} panel with it")


def test_the_dock_clamps_at_min_and_max(page):
    reset_widths(page, 'power')
    assert drag_dock(page, 600) == DOCK_MIN_H, (
        "the dock can be dragged shorter than the clamp")
    assert drag_dock(page, -800) == DOCK_MAX_H, (
        "the dock can be dragged taller than the clamp")
    assert_canvas_matches_wrapper(page, "dragging the dock to its clamps")


def test_the_dock_height_survives_a_reload(page):
    reset_widths(page, 'data-flow')
    dragged = drag_dock(page, -100)
    page.reload(wait_until='domcontentloaded')
    page.wait_for_timeout(2000)
    open_view(page, 'data-flow')
    assert abs(dock_height(page) - dragged) <= 2, (
        f"the dock came back at {dock_height(page)}, not {dragged}")
    # And back to the default, so this cannot pass on a tray that is simply
    # always tall.
    reset_widths(page, 'data-flow')
    assert dock_height(page) == DOCK_DEFAULT_H


def test_the_canvas_keeps_up_during_a_dock_drag_not_only_at_the_end(page):
    """The height transition is suppressed while dragging (#app.lrd-resizing),
    so every frame is already in layout and the canvas re-measures per move
    rather than waiting for the staged settle on mouseup."""
    reset_widths(page, 'data-flow')
    h = page.evaluate(DOCK_HANDLE_JS)
    page.mouse.move(h['x'], h['y'])
    page.mouse.down()
    page.mouse.move(h['x'], h['y'] - 40)
    page.mouse.move(h['x'], h['y'] - 80)
    page.wait_for_timeout(120)
    mid = page.evaluate(CANVAS_JS)
    page.mouse.up()
    page.wait_for_timeout(400)
    assert mid['canvasH'] == mid['wrapperH'], (
        f"the canvas lagged the pointer mid-drag on the dock: {mid}")


def test_the_dock_collapse_toggle_folds_and_persists(page):
    reset_widths(page, 'data-flow')
    page.locator('#hardware-dock-toggle').click()
    page.wait_for_timeout(500)
    folded = page.evaluate(DOCK_STATE_JS)
    assert folded['collapsed'] and folded['height'] < 2, (
        f"the toggle did not fold the tray: {folded}")
    assert folded['stored'] == '1', (
        f"the fold did not persist under the dock's own key: {folded}")
    assert page.evaluate(DOCK_HANDLE_JS) is None, (
        "a folded dock still offers a strip to drag")
    assert_canvas_matches_wrapper(page, "folding the dock")
    assert_nothing_stranded(page, "with the dock folded")

    page.reload(wait_until='domcontentloaded')
    page.wait_for_timeout(2000)
    open_view(page, 'data-flow')
    assert page.evaluate(DOCK_STATE_JS)['collapsed'], (
        "the fold did not survive a reload")

    page.locator('#hardware-dock-toggle').click()
    page.wait_for_timeout(500)
    back = page.evaluate(DOCK_STATE_JS)
    assert not back['collapsed'] and back['height'] == DOCK_DEFAULT_H, (
        f"expanding did not restore the tray: {back}")
    assert_canvas_matches_wrapper(page, "expanding the dock again")


def test_the_dock_toggle_wins_the_hit_test_over_its_strip(page):
    """They share the tray's top edge and the strip spans its whole width.
    The toggle is the only way back from a folded tray, so it has to win."""
    reset_widths(page, 'data-flow')
    hit = page.evaluate(
        """() => {
            const r = document.getElementById('hardware-dock-toggle')
                .getBoundingClientRect();
            const el = document.elementFromPoint(
                Math.round(r.left + r.width / 2),
                Math.round(r.bottom - 2));
            return el ? (el.id || el.className) : null;
        }""")
    assert hit == 'hardware-dock-toggle', (
        f"#hardware-dock-toggle is covered by {hit} - the resize strip is on "
        f"top of the only control that can expand the tray again")


def test_a_folded_dock_stays_folded_across_a_view_switch(page):
    """The dock belongs to BOTH hardware views, so the fold must hold through
    Data -> elsewhere -> Power - the visibility pass touches .view-hidden and
    nothing else."""
    reset_widths(page, 'data-flow')
    page.locator('#hardware-dock-toggle').click()
    page.wait_for_timeout(500)
    open_view(page, 'pixel-map')
    assert_nothing_stranded(page, "in pixel-map with the dock folded")
    open_view(page, 'power')
    assert page.evaluate(DOCK_STATE_JS)['collapsed'], (
        "the dock came back expanded in Power after folding in Data")
    assert_nothing_stranded(page, "in power with the dock still folded")
    page.locator('#hardware-dock-toggle').click()
    page.wait_for_timeout(500)
