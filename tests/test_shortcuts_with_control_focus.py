"""Shortcuts fire past a focused checkbox, radio, range or colour control.

Found by an end-to-end pass (2026-09-23): on the Power tab, tick
``#power-custom-toggle`` (focus stays on the box), Cmd+click a second
Screens row so two screens are selected, press Cmd+J - nothing. With
``document.activeElement.id === 'power-custom-toggle'`` the keydown guard
in canvas-input.js read ``tagName === 'INPUT'`` and called that "typing",
so a control that takes no text at all swallowed every shortcut until the
next click landed elsewhere; ``activeElement.blur()`` and the same key
duplicated. Three other copies of that guard (app-menubar, app-core's Esc,
app-dock-sweep's Alt+Enter) had each drifted to their own tag list.

Ruling pinned here: typing means a text-like input (text, number, search,
email, url, password, tel, the date kinds, or no type), a textarea, a
select, or a contenteditable element. A checkbox, radio, range, color or
button input is a CONTROL, not a field, and every shortcut works with one
focused. ONE predicate - helpers.js ``isTypingTarget`` - answers for every
guard so they cannot drift again. Two deliberate exceptions survive: a
focused BUTTON still owns Tab (user, 2026-09-03), and Space on a focused
checkbox is the checkbox's toggle, not the canvas pan.

Run locally:
    python3 -m pytest tests/test_shortcuts_with_control_focus.py -v --browser chromium
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS_DIR = os.path.join(ROOT, 'src', 'static', 'js')

# The app accepts either metaKey or ctrlKey; press the one the platform's
# users press (on macOS Chromium, Control-chords are not the shortcut).
MODIFIER = "Meta" if sys.platform == "darwin" else "Control"


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
    errors = []
    pg.on('pageerror', lambda err: errors.append(str(err)))
    pg.page_errors = errors
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    yield pg
    context.close()


# Three 2x2 screens, custom power on the first, the Power tab on screen
# (so its checkbox is a real, visible focus target), a fresh history. With
# `multi` the second screen joins the selection the way Cmd+click on its
# Screens row does (toggleLayerSelection is what that click calls).
RESET_JS = """async (multi) => {
    const app = window.app, r = window.canvasRenderer;
    if (document.activeElement && document.activeElement.blur) {
        document.activeElement.blur();
    }
    let project = await (await fetch('/api/project')).json();
    project.layers = [];
    project.groups = [];
    project.distros = [];
    delete project.processors;
    delete project.port_assignments;
    delete project.next_processor_seq;
    await fetch('/api/project', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(project),
    });
    for (let i = 0; i < 3; i++) {
        await fetch('/api/layer/add', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                name: 'Focus' + (i + 1),
                columns: 2, rows: 2, cabinet_width: 128, cabinet_height: 128,
                offset_x: i * 400, offset_y: 0,
            }),
        });
    }
    app.project = await (await fetch('/api/project')).json();
    app.dedupeProjectLayers('shortcut_focus_reset');
    const live = app.project.layers.filter(l => (l.type || 'screen') === 'screen');
    const first = live[0];
    first.powerFlowPattern = 'custom';
    first.powerVoltage = 208; first.powerAmperage = 20; first.panelWatts = 200;
    first.powerCustomPaths = {};
    first.powerCustomIndex = 1;
    app.ensureCustomPowerState(first);
    app.powerCustomSelection.clear();
    app.selectLayer(first);
    if (multi) app.toggleLayerSelection(live[1]);
    app._circuitTailCache = null;
    r.viewMode = 'power';
    if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
    app.resetHistory('Shortcut Focus Reset');
    app.renderLayers();
    app.updateCustomPowerUI();
    r.render();
    return {
        ids: live.map(l => l.id),
        selected: [...app.selectedLayerIds],
        current: app.currentLayer ? app.currentLayer.id : null,
        customPower: app.isCustomPowerEditing(first),
    };
}"""

# Focus an element by selector and report what took focus - the element
# must be on screen for focus() to land, so the report is the premise check.
FOCUS_JS = """(sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    el.focus();
    const a = document.activeElement;
    return a === el ? (a.id || a.tagName) : 'NOT ' + (a ? (a.id || a.tagName) : 'null');
}"""

READ_JS = """() => {
    const app = window.app, l = app.currentLayer;
    const paths = (l && l.powerCustomPaths) || {};
    return {
        layers: app.project.layers.length,
        names: app.project.layers.map(x => x.name),
        current: l ? l.id : null,
        selected: [...(app.selectedLayerIds || [])],
        circuit: l ? l.powerCustomIndex : null,
        path: (paths[1] || []).map(e => [e.row, e.col]),
        focus: document.activeElement ? (document.activeElement.id || document.activeElement.tagName) : null,
        spacePressed: !!window.canvasRenderer.spacePressed,
    };
}"""

# A range control the sidebar does not show on a screen layer: build one
# in the page for the test, and take it away after.
PROBE_RANGE_JS = """() => {
    let el = document.getElementById('shortcut-probe-range');
    if (!el) {
        el = document.createElement('input');
        el.type = 'range';
        el.id = 'shortcut-probe-range';
        el.style.cssText = 'position:fixed;top:4px;left:4px;width:80px;z-index:99999;';
        document.body.appendChild(el);
    }
    return el.id;
}"""

UNPROBE_JS = """() => {
    const el = document.getElementById('shortcut-probe-range');
    if (el) el.remove();
}"""


def reset(page, multi=False):
    del page.page_errors[:]
    page.locator('[data-mode="power"]').click()
    page.wait_for_timeout(300)
    state = page.evaluate(RESET_JS, multi)
    page.wait_for_timeout(300)
    assert len(state['ids']) == 3, state
    assert state['customPower'] is True, state
    return state


def focus(page, selector):
    got = page.evaluate(FOCUS_JS, selector)
    assert got == selector.lstrip('#'), (
        f'{selector} did not take focus (got {got!r}) - the premise of the '
        'test is a focused control')
    return got


def press(page, key, settle=500):
    page.keyboard.press(key)
    page.wait_for_timeout(settle)
    return page.evaluate(READ_JS)


# ── the predicate itself ──────────────────────────────────────────────────

PREDICATE_TABLE_JS = """() => {
    const f = window.isTypingTarget;
    const mk = (tag, attrs) => {
        const el = document.createElement(tag);
        Object.entries(attrs || {}).forEach(([k, v]) => el.setAttribute(k, v));
        return el;
    };
    const ce = mk('div', { contenteditable: 'true' });
    document.body.appendChild(ce);   // isContentEditable needs a document
    const out = {
        checkbox: f(mk('input', { type: 'checkbox' })),
        radio: f(mk('input', { type: 'radio' })),
        range: f(mk('input', { type: 'range' })),
        color: f(mk('input', { type: 'color' })),
        buttonInput: f(mk('input', { type: 'button' })),
        submit: f(mk('input', { type: 'submit' })),
        file: f(mk('input', { type: 'file' })),
        button: f(mk('button')),
        div: f(mk('div')),
        body: f(document.body),
        none: f(null),
        text: f(mk('input', { type: 'text' })),
        untyped: f(mk('input')),
        number: f(mk('input', { type: 'number' })),
        search: f(mk('input', { type: 'search' })),
        email: f(mk('input', { type: 'email' })),
        url: f(mk('input', { type: 'url' })),
        password: f(mk('input', { type: 'password' })),
        tel: f(mk('input', { type: 'tel' })),
        date: f(mk('input', { type: 'date' })),
        textarea: f(mk('textarea')),
        select: f(mk('select')),
        contenteditable: f(ce),
    };
    ce.remove();
    return out;
}"""


def test_the_shared_predicate_reads_controls_as_not_typing(page):
    got = page.evaluate(PREDICATE_TABLE_JS)
    controls = ['checkbox', 'radio', 'range', 'color', 'buttonInput',
                'submit', 'file', 'button', 'div', 'body', 'none']
    fields = ['text', 'untyped', 'number', 'search', 'email', 'url',
              'password', 'tel', 'date', 'textarea', 'select', 'contenteditable']
    wrong = ({k for k in controls if got[k] is not False}
             | {k for k in fields if got[k] is not True})
    assert not wrong, f'isTypingTarget answered wrong for {sorted(wrong)}: {got}'


# ── the reported defect ───────────────────────────────────────────────────

def test_cmd_j_duplicates_with_the_custom_toggle_focused(page):
    state = reset(page, multi=True)
    assert len(state['selected']) == 2, state
    focus(page, '#power-custom-toggle')
    after = press(page, f'{MODIFIER}+KeyJ', settle=700)
    assert after['layers'] == 4, (
        f'Cmd+J with #power-custom-toggle focused made nothing: {after}')
    assert page.page_errors == [], page.page_errors


def test_cmd_z_undoes_with_a_checkbox_focused(page):
    reset(page)
    grown = press(page, f'{MODIFIER}+KeyJ', settle=700)
    assert grown['layers'] == 4, f'the duplicate that undo steps back over: {grown}'
    focus(page, '#power-custom-toggle')
    after = press(page, f'{MODIFIER}+KeyZ', settle=400)
    assert after['layers'] == 3, (
        f'Cmd+Z with a checkbox focused did not undo the duplicate: {after}')
    assert after['focus'] == 'power-custom-toggle', after


@pytest.mark.parametrize('control', ['#shortcut-probe-range', '#power-custom-toggle'])
def test_delete_removes_the_selected_screen_with_a_control_focused(page, control):
    state = reset(page)
    page.evaluate(PROBE_RANGE_JS)
    try:
        focus(page, control)
        after = press(page, 'Delete', settle=900)
        assert after['layers'] == 2, (
            f'Delete with {control} focused did not delete the screen: {after}')
        assert state['current'] not in [
            *(page.evaluate("() => window.app.project.layers.map(l => l.id)"))], (
            'the wrong screen went')
    finally:
        page.evaluate(UNPROBE_JS)


def test_arrow_keys_draw_in_custom_mode_with_a_checkbox_focused(page):
    reset(page)
    page.evaluate("""() => {
        const l = window.app.currentLayer;
        l.powerCustomPaths = { 1: [{ row: 0, col: 0 }] };
    }""")
    focus(page, '#power-custom-toggle')
    after = press(page, 'ArrowRight', settle=300)
    assert after['path'] == [[0, 0], [0, 1]], (
        f'ArrowRight with a checkbox focused did not extend the circuit: {after}')
    assert after['focus'] == 'power-custom-toggle', after


def test_arrow_keys_yield_to_a_focused_slider_in_custom_mode(page):
    """A slider (and a radio group) answers the arrow keys itself, so the
    custom-mode draw leaves them alone; every other shortcut still fires
    with one focused (Delete above)."""
    reset(page)
    page.evaluate("""() => {
        const l = window.app.currentLayer;
        l.powerCustomPaths = { 1: [{ row: 0, col: 0 }] };
    }""")
    page.evaluate(PROBE_RANGE_JS)
    try:
        focus(page, '#shortcut-probe-range')
        after = press(page, 'ArrowRight', settle=300)
        assert after['path'] == [[0, 0]], (
            f'ArrowRight with a slider focused drew a circuit: {after}')
        assert after['focus'] == 'shortcut-probe-range', after
    finally:
        page.evaluate(UNPROBE_JS)


def test_space_toggles_a_focused_checkbox_and_does_not_pan(page):
    reset(page)
    # The real toggle re-wires the layer on change; the assertion is about
    # the keyboard reaching the box, so the handler is stood in for.
    before = page.evaluate("""() => {
        const app = window.app, box = document.getElementById('power-custom-toggle');
        window.__savedToggle = { fn: app.toggleCustomPowerMode, checked: box.checked };
        app.toggleCustomPowerMode = () => {};
        return box.checked;
    }""")
    try:
        focus(page, '#power-custom-toggle')
        page.keyboard.down('Space')
        page.wait_for_timeout(100)
        held = page.evaluate(READ_JS)
        page.keyboard.up('Space')
        page.wait_for_timeout(100)
        assert held['spacePressed'] is False, (
            f'Space on a focused checkbox started the canvas pan: {held}')
        toggled = page.evaluate(
            "() => document.getElementById('power-custom-toggle').checked")
        assert toggled is (not before), (
            'Space on the focused checkbox must still toggle it '
            f'(was {before}, now {toggled})')
        # Same key with nothing focused is still the pan - the control
        # that the probe above is real.
        page.evaluate("() => document.activeElement.blur()")
        page.keyboard.down('Space')
        page.wait_for_timeout(100)
        free = page.evaluate(READ_JS)
        page.keyboard.up('Space')
        assert free['spacePressed'] is True, f'Space from the canvas no longer pans: {free}'
    finally:
        page.evaluate("""() => {
            const app = window.app, s = window.__savedToggle;
            if (!s) return;
            app.toggleCustomPowerMode = s.fn;
            document.getElementById('power-custom-toggle').checked = s.checked;
            delete window.__savedToggle;
        }""")


def test_typing_in_a_text_input_still_blocks_the_shortcuts(page):
    reset(page)
    page.evaluate("""() => {
        window.app.currentLayer.powerCustomPaths = { 1: [{ row: 0, col: 0 }] };
        window.__savedName = document.getElementById('project-name').value;
    }""")
    try:
        focus(page, '#project-name')
        after_j = press(page, f'{MODIFIER}+KeyJ', settle=600)
        assert after_j['layers'] == 3, f'Cmd+J fired out of a text field: {after_j}'
        after_del = press(page, 'Delete', settle=600)
        assert after_del['layers'] == 3, f'Delete fired out of a text field: {after_del}'
        after_arrow = press(page, 'ArrowRight', settle=300)
        assert after_arrow['path'] == [[0, 0]], (
            f'ArrowRight drew a circuit out of a text field: {after_arrow}')
        assert after_arrow['focus'] == 'project-name', after_arrow
    finally:
        # Put the field back BEFORE blurring so no change event renames
        # the project.
        page.evaluate("""() => {
            const f = document.getElementById('project-name');
            if (window.__savedName !== undefined) f.value = window.__savedName;
            delete window.__savedName;
            f.blur();
        }""")


def test_tab_from_a_focused_button_still_moves_focus(page):
    """The 2026-09-03 ruling, untouched: click Next, press Tab - the circuit
    advances once in total, because a focused BUTTON owns Tab."""
    reset(page)
    focus(page, '#power-custom-next')
    after = press(page, 'Tab', settle=250)
    assert after['circuit'] == 1, (
        f'Tab from the focused Next button stepped the circuit: {after}')
    assert after['focus'] != 'power-custom-next', (
        f'Tab from the focused Next button must move focus: {after}')


def test_tab_from_a_focused_checkbox_steps_the_circuit(page):
    """A checkbox is not a BUTTON: the Tab ruling is the button's alone, so
    Tab past a focused checkbox is the keyboard's Next, like every other
    shortcut."""
    reset(page)
    focus(page, '#power-custom-toggle')
    after = press(page, 'Tab', settle=250)
    assert after['circuit'] == 2, (
        f'Tab with a checkbox focused did not step the circuit: {after}')


# ── one predicate, no drift ───────────────────────────────────────────────

GUARD_FILES = ['canvas-input.js', 'app-menubar.js', 'app-core.js', 'app-dock-sweep.js']


def _read(name):
    with open(os.path.join(JS_DIR, name), encoding='utf-8') as fh:
        return fh.read()


def test_every_shortcut_guard_routes_through_the_shared_predicate():
    helpers = _read('helpers.js')
    assert helpers.count('function isTypingTarget(') == 1
    assert 'window.isTypingTarget = isTypingTarget;' in helpers, (
        'canvas-input.js is a classic script and reads the predicate off window')
    inline = re.compile(r"""tagName\s*===?\s*['"](TEXTAREA|SELECT)['"]|isContentEditable""")
    for name in GUARD_FILES:
        source = _read(name)
        assert 'isTypingTarget(document.activeElement)' in source, (
            f'{name} no longer asks helpers.js isTypingTarget - a private '
            'typing guard drifts (2026-09-23)')
        code = '\n'.join(l for l in source.split('\n') if not l.lstrip().startswith('//'))
        assert not inline.search(code), (
            f'{name} grew an inline typing guard again; use isTypingTarget')
