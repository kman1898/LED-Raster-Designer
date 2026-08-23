"""Held-key and drag state must unlatch when the release lands off the canvas.

Reported against v0.11.x, working the app live: "if i hold space bar and drag
around the raster and i move the mouse off the raster and i let go of the
click and space bar it will remain pressed when i bring the mouse back onto
the raster and it is hard to get it unlocked". Shift-click drags latch the
same way.

The mechanism is listener scope. handleMouseDown arms a flag (isDragging for
the space/middle-button pan, isDraggingLayer / isDraggingScreenName for the
shift drags), and the finalizer that clears it - handleMouseUp - listened on
the CANVAS element. A release over the sidebar, a toolbar, or outside the
browser window targets some other element, the canvas listener never hears
it, and the flag stays armed: the next time the cursor crosses the raster,
mousemove resumes the drag with no button held. spacePressed has the sibling
disease one level up: keyup listens on document, which is wide enough for
in-page releases, but cmd-tab with space held delivers the keyup to the
OTHER app, so the grab state latched until the next tap of space.

Pinned here, with real input events end to end:

* Space-pan: press off-canvas-release resumes nothing - isDragging is
  cleared by the window-level mouseup, and a buttonless pass over the
  canvas afterwards does not pan.
* Middle-button pan: same flag, same release path.
* Shift+drag (layer move on pixel-map) and shift+drag (screen-name move on
  data-flow): the two shift gestures the same mousedown arms, released
  off-canvas, both unlatch.
* Window blur and tab-hide clear spacePressed (the cmd-tab latch).

And the logs "From:"/"To:" filter parser, same live session: "having to type
1 m is dumb. it should be min by default". A bare number used to fall through
BOTH grammars (relative required a unit, absolute required a full date) and
came back null, flagging the field invalid. Bare numbers now read as minutes;
every explicit form is unchanged.

Run locally:
    python -m pytest tests/test_input_state_latch.py -v --browser chromium
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


RESET_JS = """() => {
    const app = window.app, r = window.canvasRenderer;
    // Belt and braces: start every test from a known-idle input state so a
    // latch left behind by an earlier (failing) test cannot cascade.
    r.isDragging = false;
    r.isDraggingLayer = false;
    r.isDraggingScreenName = false;
    r.isDraggingGroupName = false;
    r.isDraggingCanvas = false;
    r.isAltPainting = false;
    r.isSelectingLayers = false;
    r.isSelectingPanels = false;
    r.isSelectingPixelMapPanels = false;
    r.layerSelectionRect = null;
    r.selectionRect = null;
    r.spacePressed = false;
    app.currentLayer = app.project.layers[0] || null;
    if (app.currentLayer) {
        app.selectedLayerIds = new Set([app.currentLayer.id]);
        app.lastSelectedLayerId = app.currentLayer.id;
    }
    r.viewMode = 'pixel-map';
    // Deterministic camera so world -> client math is exact.
    r.zoom = 1; r.panX = 60; r.panY = 60;
    r.render();
    return {
        layers: app.project.layers.length,
        currentId: app.currentLayer ? app.currentLayer.id : null,
    };
}"""


def reset_state(page, view='pixel-map'):
    state = page.evaluate(RESET_JS)
    if view != 'pixel-map':
        page.evaluate(
            "(v) => { window.canvasRenderer.viewMode = v; window.canvasRenderer.render(); }",
            view)
    assert state['layers'] >= 1 and state['currentId'] is not None, state
    return state


def flags(page):
    return page.evaluate("""() => {
        const r = window.canvasRenderer;
        return {
            space: !!r.spacePressed,
            pan: !!r.isDragging,
            layer: !!r.isDraggingLayer,
            name: !!r.isDraggingScreenName,
            panX: r.panX, panY: r.panY,
        };
    }""")


def world_to_client(page, wx, wy):
    pt = page.evaluate("""([wx, wy]) => {
        const r = window.canvasRenderer;
        const rect = r.canvas.getBoundingClientRect();
        return { x: rect.left + wx * r.zoom + r.panX,
                 y: rect.top + wy * r.zoom + r.panY };
    }""", [wx, wy])
    return pt['x'], pt['y']


def off_canvas_point(page):
    """A viewport point that is NOT over the canvas element - where the
    user's release actually lands when they drift off the raster."""
    pt = page.evaluate("""() => {
        const canvas = window.canvasRenderer.canvas;
        const rect = canvas.getBoundingClientRect();
        const candidates = [
            { x: rect.left - 40, y: rect.top + rect.height / 2 },
            { x: rect.left + rect.width / 2, y: rect.top - 40 },
            { x: rect.right + 40, y: rect.top + rect.height / 2 },
            { x: rect.left + rect.width / 2, y: rect.bottom + 40 },
        ];
        for (const c of candidates) {
            if (c.x < 5 || c.y < 5) continue;
            if (c.x > window.innerWidth - 5 || c.y > window.innerHeight - 5) continue;
            const el = document.elementFromPoint(c.x, c.y);
            if (el && el !== canvas) return c;
        }
        return null;
    }""")
    assert pt, "no point outside the canvas but inside the viewport"
    return pt['x'], pt['y']


# The seeded Screen1 is 4x3 cabinets of 128px at offset (0,0): world
# 0..512 x 0..384, so (256, 192) is its centre.
LAYER_CENTER_WORLD = (256, 192)


def sweep_canvas_no_buttons(page):
    """Bring the cursor back onto the raster and move around with NO buttons
    held - the exact moment the user sees the latched drag resume."""
    cx, cy = world_to_client(page, 100, 100)
    page.mouse.move(cx, cy, steps=2)
    page.mouse.move(cx + 150, cy + 90, steps=5)
    page.mouse.move(cx + 40, cy + 20, steps=5)


# ── space-pan latch ───────────────────────────────────────────────────────

def test_space_pan_unlatches_on_off_canvas_release(page):
    reset_state(page)
    sx, sy = world_to_client(page, *LAYER_CENTER_WORLD)
    ox, oy = off_canvas_point(page)

    page.keyboard.down('Space')
    assert flags(page)['space'] is True
    page.mouse.move(sx, sy)
    page.mouse.down()
    assert flags(page)['pan'] is True, "pan never armed - premise broken"
    # Drift off the raster while dragging, release button and key out there.
    page.mouse.move(ox, oy, steps=4)
    page.mouse.up()
    page.keyboard.up('Space')
    page.wait_for_timeout(100)

    after = flags(page)
    assert after['pan'] is False, "pan drag stayed latched after off-canvas release"
    assert after['space'] is False

    # Back over the raster with nothing held: the view must not pan.
    before = flags(page)
    sweep_canvas_no_buttons(page)
    after = flags(page)
    assert after['pan'] is False
    assert (after['panX'], after['panY']) == (before['panX'], before['panY']), \
        "buttonless mousemove panned the view - drag state was latched"


def test_middle_button_pan_unlatches_on_off_canvas_release(page):
    reset_state(page)
    sx, sy = world_to_client(page, *LAYER_CENTER_WORLD)
    ox, oy = off_canvas_point(page)

    page.mouse.move(sx, sy)
    page.mouse.down(button='middle')
    assert flags(page)['pan'] is True, "middle-button pan never armed - premise broken"
    page.mouse.move(ox, oy, steps=4)
    page.mouse.up(button='middle')
    page.wait_for_timeout(100)

    before = flags(page)
    assert before['pan'] is False, "middle-button pan stayed latched after off-canvas release"
    sweep_canvas_no_buttons(page)
    after = flags(page)
    assert (after['panX'], after['panY']) == (before['panX'], before['panY'])


# ── the cmd-tab latch: focus loss must drop held-key state ────────────────

def test_window_blur_clears_space_state(page):
    reset_state(page)
    page.keyboard.down('Space')
    assert flags(page)['space'] is True
    # cmd-tab: the keyup is delivered to the other application, the page
    # only sees its window blur.
    page.evaluate("() => window.dispatchEvent(new Event('blur'))")
    assert flags(page)['space'] is False, "spacePressed survived window blur"
    page.keyboard.up('Space')


def test_tab_hide_clears_space_state(page):
    reset_state(page)
    page.keyboard.down('Space')
    assert flags(page)['space'] is True
    page.evaluate("""() => {
        Object.defineProperty(document, 'hidden',
            { configurable: true, get: () => true });
        document.dispatchEvent(new Event('visibilitychange'));
        delete document.hidden;
    }""")
    assert flags(page)['space'] is False, "spacePressed survived tab hide"
    page.keyboard.up('Space')


# ── shift-drag latches (both gestures the shift mousedown can arm) ────────

def test_shift_layer_drag_unlatches_on_off_canvas_release(page):
    reset_state(page, view='pixel-map')
    sx, sy = world_to_client(page, *LAYER_CENTER_WORLD)
    ox, oy = off_canvas_point(page)

    page.keyboard.down('Shift')
    page.mouse.move(sx, sy)
    page.mouse.down()
    assert flags(page)['layer'] is True, "shift layer-drag never armed - premise broken"
    page.mouse.move(ox, oy, steps=4)
    page.mouse.up()
    page.keyboard.up('Shift')
    page.wait_for_timeout(300)

    assert flags(page)['layer'] is False, \
        "shift layer-drag stayed latched after off-canvas release"

    # Back over the raster with nothing held: the layer must not move.
    before = page.evaluate(
        "() => [window.app.currentLayer.offset_x, window.app.currentLayer.offset_y]")
    sweep_canvas_no_buttons(page)
    page.wait_for_timeout(100)
    after = page.evaluate(
        "() => [window.app.currentLayer.offset_x, window.app.currentLayer.offset_y]")
    assert after == before, "buttonless mousemove kept dragging the layer"


def test_shift_screen_name_drag_unlatches_on_off_canvas_release(page):
    # On data-flow, the same shift mousedown arms the screen-NAME drag
    # instead of the whole-layer drag; it latched the same way.
    reset_state(page, view='data-flow')
    sx, sy = world_to_client(page, *LAYER_CENTER_WORLD)
    ox, oy = off_canvas_point(page)

    page.keyboard.down('Shift')
    page.mouse.move(sx, sy)
    page.mouse.down()
    assert flags(page)['name'] is True, "shift name-drag never armed - premise broken"
    page.mouse.move(ox, oy, steps=4)
    page.mouse.up()
    page.keyboard.up('Shift')
    page.wait_for_timeout(300)

    assert flags(page)['name'] is False, \
        "screen-name drag stayed latched after off-canvas release"


# ── logs since/until parser: bare numbers are minutes ─────────────────────

def test_since_parser_bare_number_means_minutes(page):
    res = page.evaluate("""() => {
        const app = window.app;
        const now = Date.now();
        return {
            now,
            one: app.parseLogFilterTime('1'),
            five: app.parseLogFilterTime('5'),
            frac: app.parseLogFilterTime('1.5'),
            spaced: app.parseLogFilterTime(' 30 '),
        };
    }""")
    for key, minutes in (('one', 1), ('five', 5), ('frac', 1.5), ('spaced', 30)):
        got = res[key]
        assert got is not None, f"bare number {key!r} did not parse"
        expect = res['now'] - minutes * 60 * 1000
        assert abs(got - expect) < 2000, \
            f"bare number {key!r}: got {got}, expected ~{expect} ({minutes} min ago)"


def test_since_parser_explicit_grammar_unchanged(page):
    res = page.evaluate("""() => {
        const app = window.app;
        const now = Date.now();
        return {
            now,
            s30: app.parseLogFilterTime('30s'),
            m10: app.parseLogFilterTime('10 min ago'),
            h2: app.parseLogFilterTime('2h'),
            d1: app.parseLogFilterTime('1d'),
            word: app.parseLogFilterTime('now'),
            absDate: app.parseLogFilterTime('2026-07-25'),
            absFull: app.parseLogFilterTime('2026-07-25 20:14:16'),
            junk: app.parseLogFilterTime('abc'),
            blank: app.parseLogFilterTime('   '),
            partialDate: app.parseLogFilterTime('2026-07'),
        };
    }""")
    checks = (('s30', 30 * 1000), ('m10', 10 * 60 * 1000),
              ('h2', 2 * 3600 * 1000), ('d1', 24 * 3600 * 1000))
    for key, ms in checks:
        assert res[key] is not None, f"{key} stopped parsing"
        assert abs(res[key] - (res['now'] - ms)) < 2000, key
    assert abs(res['word'] - res['now']) < 2000
    assert res['absDate'] is not None and res['absFull'] is not None
    # 2026-07-25 00:00 local precedes 20:14:16 the same day.
    assert res['absDate'] < res['absFull']
    assert res['junk'] is None
    assert res['blank'] is None
    # A dash means the user is typing an absolute date; incomplete stays
    # invalid rather than guessing.
    assert res['partialDate'] is None


def test_since_field_hint_names_the_default_unit(page):
    hint = page.evaluate("""() => {
        const el = document.getElementById('logs-since');
        return { placeholder: el.placeholder, title: el.title };
    }""")
    blob = (hint['placeholder'] + ' ' + hint['title']).lower()
    assert 'minute' in blob, \
        f"since-field hint does not say bare numbers are minutes: {hint}"
