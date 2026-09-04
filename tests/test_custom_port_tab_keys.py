"""Tab / Shift+Tab stepped the DATA port while you were in Power view.

Reported against v0.11.0: "on custom power path, tab and shift tab aren't
changing port numbers", followed by "data works exactly as i would expect".
That pair is the whole diagnosis. isCustomFlow(layer) is a pure layer-state
predicate - `flowPattern === 'custom'` - not a view test, and the Tab handler
checked it FIRST with no view guard:

    if (isCustomFlow(layer))        { ...advance customPortIndex... }
    else if (isCustomPower(layer))  { ...advance powerCustomIndex... }

So on a screen carrying BOTH a custom data pattern and custom power, Tab in
POWER view took the data branch and moved the data port. The circuit never
budged, so the key looked dead. In DATA view the first branch is the correct
one, which is why only half the feature appeared broken - and why nothing
caught it.

Every sibling handler in canvas.js already guarded on viewMode (mousedown,
drag-select, the [ and ] shortcuts). Only these two did not.

A screen in a GROUP is always in the both-custom state, because the flow
pattern is shared across members - so this got more likely, not less, as
groups got used.

Second defect fixed at the same time: the handler mutated the index inline and
never called updateLayers(), so even when it moved the right one the change
never reached the server and was lost on reload.

Run locally:
    python -m pytest tests/test_custom_port_tab_keys.py -v --browser chromium
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


# A screen with BOTH custom patterns - the state a grouped screen is always
# in. `view` selects which tab we are standing on when Tab is pressed.
SETUP_JS = """(view) => {
    const app = window.app, r = window.canvasRenderer;
    const layer = app.currentLayer;
    // Drop focus first. These handlers all skip when the user is typing, and
    // the Pixel Map case below presses Tab UNHANDLED - so the browser moves
    // focus into an input and every later key in this file reads as typing.
    // Without this the tests pass alone and fail together, which is worse
    // than failing outright.
    if (document.activeElement && document.activeElement.blur) {
        document.activeElement.blur();
    }
    window.__saved = {
        flowPattern: layer.flowPattern,
        powerFlowPattern: layer.powerFlowPattern,
        customPortIndex: layer.customPortIndex,
        powerCustomIndex: layer.powerCustomIndex,
        viewMode: r.viewMode,
        updateLayers: app.updateLayers,
    };
    layer.flowPattern = 'custom';          // BOTH custom: the trap
    layer.powerFlowPattern = 'custom';
    layer.customPortIndex = 1;
    layer.powerCustomIndex = 1;
    app.ensureCustomFlowState(layer);
    app.ensureCustomPowerState(layer);
    r.viewMode = view;
    // Record server syncs instead of performing them - the assertion is that
    // the handler asks for one, which the old inline copy never did.
    window.__puts = 0;
    app.updateLayers = () => { window.__puts++; };
    return {
        isCustomFlow: app.isCustomFlow(layer),
        isCustomPower: app.isCustomPower(layer),
        view: r.viewMode,
    };
}"""

RESTORE_JS = """() => {
    const app = window.app, r = window.canvasRenderer, s = window.__saved;
    if (!s) return;
    const l = app.currentLayer;
    l.flowPattern = s.flowPattern;
    l.powerFlowPattern = s.powerFlowPattern;
    l.customPortIndex = s.customPortIndex;
    l.powerCustomIndex = s.powerCustomIndex;
    r.viewMode = s.viewMode;
    app.updateLayers = s.updateLayers;
    delete window.__saved;
}"""

READ_JS = """() => {
    const l = window.app.currentLayer;
    return {
        port: l.customPortIndex,
        circuit: l.powerCustomIndex,
        puts: window.__puts,
    };
}"""


def _press_tab(page, view, shift=False):
    state = page.evaluate(SETUP_JS, view)
    try:
        page.keyboard.press("Shift+Tab" if shift else "Tab")
        page.wait_for_timeout(350)
        after = page.evaluate(READ_JS)
    finally:
        page.evaluate(RESTORE_JS)
    return state, after


def test_the_layer_really_is_in_the_both_custom_state(page):
    """Guard the premise. If the setup stopped producing a layer with both
    patterns custom, the tests below would pass for the wrong reason."""
    state, _ = _press_tab(page, 'power')
    assert state['isCustomFlow'] is True
    assert state['isCustomPower'] is True
    assert state['view'] == 'power'


def test_tab_in_power_steps_the_circuit_not_the_data_port(page):
    """The reported bug."""
    _, after = _press_tab(page, 'power')
    assert after['circuit'] == 2, (
        f"Tab in Power left the circuit at {after['circuit']} - the key looks "
        "dead because it stepped the data port instead")
    assert after['port'] == 1, (
        f"Tab in Power moved the DATA port to {after['port']} - that is the "
        "bug: isCustomFlow won because it is not a view test")


def test_shift_tab_in_power_steps_the_circuit_back(page):
    _, after = _press_tab(page, 'power')          # 1 -> 2
    page.evaluate(SETUP_JS, 'power')
    page.evaluate("() => { window.app.currentLayer.powerCustomIndex = 3; }")
    page.keyboard.press("Shift+Tab")
    page.wait_for_timeout(350)
    got = page.evaluate(READ_JS)
    page.evaluate(RESTORE_JS)
    assert got['circuit'] == 2, f"Shift+Tab left the circuit at {got['circuit']}"
    assert got['port'] == 1, "Shift+Tab in Power moved the data port"


def test_data_flow_is_unchanged(page):
    """The half that always worked, and must keep working - in Data Flow the
    data branch IS the right one."""
    _, after = _press_tab(page, 'data-flow')
    assert after['port'] == 2, f"Tab in Data Flow left the port at {after['port']}"
    assert after['circuit'] == 1, "Tab in Data Flow moved the power circuit"


def test_the_step_is_pushed_to_the_server(page):
    """The handler mutated the index inline and never PUT it, so a Tab'd index
    was lost on the next reload even when it moved the right one."""
    for view in ('power', 'data-flow'):
        _, after = _press_tab(page, view)
        assert after['puts'] >= 1, (
            f"Tab in {view} changed the index without asking for a server "
            "sync - the change would not survive a reload")


def test_tab_is_inert_outside_the_custom_views(page):
    """Pixel Map has no custom port concept; Tab must fall through to the
    browser rather than quietly renumbering something off-screen."""
    _, after = _press_tab(page, 'pixel-map')
    assert after['port'] == 1 and after['circuit'] == 1, (
        f"Tab in Pixel Map changed an index: {after}")
    assert after['puts'] == 0, "Tab in Pixel Map hit the server"


# ── Same family, found by sweeping for the pattern ────────────────────────

def _press_bracket(page, view, key):
    page.evaluate(SETUP_JS, view)
    try:
        page.keyboard.press(key)
        page.wait_for_timeout(350)
        after = page.evaluate(READ_JS)
    finally:
        page.evaluate(RESTORE_JS)
    return after


@pytest.mark.parametrize('view,key,field,expect', [
    ('power', 'BracketRight', 'circuit', 2),
    ('power', 'BracketLeft', 'circuit', 1),      # clamped at 1
    ('data-flow', 'BracketRight', 'port', 2),
    ('data-flow', 'BracketLeft', 'port', 1),
])
def test_bracket_keys_step_and_persist(page, view, key, field, expect):
    """[ and ] were correctly view-guarded but mutated the index inline with
    no updateLayers() and no saveClientSideProperties() - so the step was
    never written anywhere and snapped back on the next reload or PUT."""
    after = _press_bracket(page, view, key)
    assert after[field] == expect, f"{key} in {view}: {field}={after[field]}"
    assert after['puts'] >= 1, (
        f"{key} in {view} changed the index without a server sync - lost on "
        "the next reload")


def test_bracket_keys_do_not_cross_views(page):
    after = _press_bracket(page, 'power', 'BracketRight')
    assert after['port'] == 1, "] in Power moved the DATA port"
    after = _press_bracket(page, 'data-flow', 'BracketRight')
    assert after['circuit'] == 1, "] in Data Flow moved the power circuit"


CURSOR_JS = """([view, flowCustom, powerCustom]) => {
    const app = window.app, r = window.canvasRenderer, l = app.currentLayer;
    const saved = {f: l.flowPattern, p: l.powerFlowPattern, v: r.viewMode,
                   c: r.canvas.style.cursor};
    l.flowPattern = flowCustom ? 'custom' : 'tl-h';
    l.powerFlowPattern = powerCustom ? 'custom' : 'tl-h';
    r.viewMode = view;
    r.canvas.style.cursor = 'default';
    // loadLayerToInputs refreshes the data side then the power side; the
    // power call used to win because neither checked the view.
    app.updateCustomFlowUI();
    app.updateCustomPowerUI();
    const cursor = r.canvas.style.cursor;
    l.flowPattern = saved.f; l.powerFlowPattern = saved.p;
    r.viewMode = saved.v; r.canvas.style.cursor = saved.c;
    return cursor;
}"""


@pytest.mark.parametrize('view,flow_custom,power_custom,expected', [
    # custom data flow, automatic power - the normal grouped-screen state.
    ('data-flow', True, False, 'crosshair'),
    # the inverse: no crosshair in Data Flow just because power is custom
    ('data-flow', False, True, 'default'),
    ('power', False, True, 'crosshair'),
    ('power', True, False, 'default'),
])
def test_canvas_cursor_follows_the_view_not_just_the_layer(
        page, view, flow_custom, power_custom, expected):
    """One canvas, one cursor, two functions writing it from their own
    pattern with no view test - so whichever ran last won, and that was
    always the power one."""
    got = page.evaluate(CURSOR_JS, [view, flow_custom, power_custom])
    assert got == expected, (
        f"{view} view, flow_custom={flow_custom}, power_custom={power_custom}: "
        f"cursor was {got!r}, expected {expected!r}")



# ── the step buttons cannot double-step ──────────────────────────────────
#
# User (2026-09-03), a brand-new show drawn 1-4, 6-23: one circuit number
# skipped while clicking Next between circuits. Proven on a clean page:
# the Next button keeps keyboard focus after a mouse click, the document
# Tab handler above only deferred to INPUT/TEXTAREA, so Tab stepped AGAIN
# (2 -> 3), and Enter re-fired the focused button (4 -> 5). Ruling: click
# Next then Tab advances exactly once in total (Tab from a focused control
# moves focus, the shortcut is the canvas's), and Enter / Space on the
# focused button add nothing. Same for Prev, and for both custom controls.

STEP_SETUP_JS = """(view) => {
    const app = window.app, r = window.canvasRenderer;
    const layer = app.currentLayer;
    if (document.activeElement && document.activeElement.blur) {
        document.activeElement.blur();
    }
    window.__saved = {
        flowPattern: layer.flowPattern,
        powerFlowPattern: layer.powerFlowPattern,
        customPortIndex: layer.customPortIndex,
        powerCustomIndex: layer.powerCustomIndex,
        viewMode: r.viewMode,
        updateLayers: app.updateLayers,
    };
    layer.flowPattern = 'custom';
    layer.powerFlowPattern = 'custom';
    layer.customPortIndex = 5;
    layer.powerCustomIndex = 5;
    app.ensureCustomFlowState(layer);
    app.ensureCustomPowerState(layer);
    r.viewMode = view;
    window.__puts = 0;
    app.updateLayers = () => { window.__puts++; };
    // The controls only show for the view on screen; the buttons must be
    // real, visible targets for the mouse.
    if (view === 'power') app.updateCustomPowerUI(); else app.updateCustomFlowUI();
}"""

STEP_READ_JS = """(view) => {
    const l = window.app.currentLayer;
    return {
        idx: view === 'power' ? l.powerCustomIndex : l.customPortIndex,
        focus: document.activeElement ? (document.activeElement.id || document.activeElement.tagName) : null,
    };
}"""


@pytest.mark.parametrize("view,button,delta", [
    ('power', '#power-custom-next', 1),
    ('power', '#power-custom-prev', -1),
    ('data-flow', '#custom-next-port', 1),
    ('data-flow', '#custom-prev-port', -1),
])
def test_a_step_button_steps_once_however_the_keyboard_follows(page, view, button, delta):
    # The real view button first: the custom controls live in that view's
    # sidebar panel, and SETUP_JS only sets the renderer's viewMode - so
    # without this the Next/Prev buttons exist but are not on screen, and
    # the mouse click below times out on "element is not visible" (the
    # 4 failed / 41 passed on the tip). Same wiring on both sides; only
    # the pin's target was off screen.
    page.locator(f'[data-mode="{view}"]').click()
    page.wait_for_timeout(400)
    page.evaluate(STEP_SETUP_JS, view)
    try:
        page.locator(button).click()
        page.wait_for_timeout(150)
        clicked = page.evaluate(STEP_READ_JS, view)
        assert clicked['idx'] == 5 + delta, clicked
        assert clicked['focus'] == button.lstrip('#'), (
            f'the button should still hold focus after the click: {clicked}')
        page.keyboard.press('Tab')
        page.wait_for_timeout(200)
        after_tab = page.evaluate(STEP_READ_JS, view)
        assert after_tab['idx'] == 5 + delta, (
            f'click then Tab must advance exactly once in total: {after_tab}')
        assert after_tab['focus'] != button.lstrip('#'), (
            f'Tab from the focused button must move focus: {after_tab}')
        # Back onto the button (focus, not click) and try the keys that
        # fire a focused button.
        page.locator(button).focus()
        for key in ('Enter', 'Space'):
            page.keyboard.press(key)
            page.wait_for_timeout(150)
            after_key = page.evaluate(STEP_READ_JS, view)
            assert after_key['idx'] == 5 + delta, (
                f'{key} on the focused button must not step again: {after_key}')
    finally:
        page.evaluate(RESTORE_JS)


def test_tab_from_the_canvas_still_steps(page):
    """The other side of the same ruling: with nothing focused, Tab is
    still the keyboard's Next - the canvas shortcut is untouched."""
    page.evaluate(STEP_SETUP_JS, 'power')
    try:
        page.keyboard.press('Tab')
        page.wait_for_timeout(200)
        assert page.evaluate(STEP_READ_JS, 'power')['idx'] == 6
    finally:
        page.evaluate(RESTORE_JS)
