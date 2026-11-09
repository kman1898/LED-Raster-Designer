"""A game controller on the IDM Locator tab (app-idm-gamepad.js).

What this file pins:

* The map, in the browser's standard layout (the same numbers for
  PlayStation and Xbox pads): the D-pad and the left stick (past its
  deadzone, along its stronger axis) move the highlight one module, LB / L1
  or RB / R1 held makes it a cabinet, A / Cross marks or clears, B / Circle
  undoes, X / Square steps the field color, Y / Triangle goes to the next
  screen, View / Share clears the highlight.
* The repeat: a held direction steps at once, again after 350 ms, then
  every 90 ms; a late frame never fires a burst; let go and pressed again,
  it steps at once.
* In the app, with a fake pad: the connect toast names the pad and the help
  card shows while it is connected; moves, the cabinet jump, a mark toggle
  (one undo step), a paint while A is held (the first module decides mark
  or clear, one undo step), undo, the next screen, the field color; nothing
  acts while the window has no focus; a locked screen refuses with the
  usual error; the disconnect toast hides the card and stops the frame
  loop, and no loop runs with no pad or off the tab.

Run locally:
    python -m pytest tests/test_idm_gamepad.py -v -p no:cacheprovider
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from conftest import settled  # noqa: E402
from test_idm_field_highlight import (  # noqa: E402
    _new_page, reset_project, set_layout, served_idm, marks_of, hl, served_field,
)

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project exactly as this module found it
    (see conftest.server_project_guard)."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context, pg = _new_page(pw_browser, e2e_server)
    yield pg
    context.close()


MOD = "const m = await import('/static/js/app-idm-gamepad.js');"


# ── the map and the repeat, apart from the app ────────────────────────────

def test_the_standard_layout_numbers(page):
    got = page.evaluate("async () => { " + MOD + " return m.PAD_BUTTONS; }")
    assert {k: got[k] for k in ('A', 'B', 'X', 'Y', 'LB', 'RB', 'VIEW', 'UP', 'DOWN', 'LEFT', 'RIGHT')} == {
        'A': 0, 'B': 1, 'X': 2, 'Y': 3, 'LB': 4, 'RB': 5, 'VIEW': 8,
        'UP': 12, 'DOWN': 13, 'LEFT': 14, 'RIGHT': 15}


def test_the_direction_from_the_d_pad_and_the_stick(page):
    got = page.evaluate("""async () => { """ + MOD + """
        const pad = (pressed, axes) => ({axes: axes || [0, 0],
            buttons: Array.from({length: 17}, (_, i) => ({pressed: pressed.includes(i), value: pressed.includes(i) ? 1 : 0}))});
        const d = (p) => m.idmPadDirection(p);
        return [d(pad([12])), d(pad([13])), d(pad([14])), d(pad([15])), d(pad([])),
                d(pad([], [0.3, 0.2])), d(pad([], [0.8, 0.1])), d(pad([], [-0.2, -0.9])),
                d(pad([], [0.6, 0.7])), d(pad([15], [-1, 0]))];
    }""")
    assert got == ['up', 'down', 'left', 'right', None, None, 'right', 'up', 'down', 'right']


def test_a_held_direction_repeats_after_a_wait_and_never_bursts(page):
    got = page.evaluate("""async () => { """ + MOD + """
        const pad = (pressed) => ({axes: [0, 0],
            buttons: Array.from({length: 17}, (_, i) => ({pressed: pressed.includes(i), value: 0}))});
        let st = null; const out = [];
        const at = (t, p) => { const r = m.idmPadFrame(st, p, t); st = r.state;
            out.push([t, r.actions.filter(a => a.type === 'move').map(a => a.dir + (a.cabinet ? '+cab' : '')).join(',')]); };
        at(0, pad([15]));       // pressed: a step at once
        at(16, pad([15]));
        at(349, pad([15]));     // still waiting
        at(350, pad([15]));     // the first repeat
        at(400, pad([15]));
        at(440, pad([15]));     // 90 ms on
        at(1500, pad([15]));    // a late frame: one step, not a burst
        at(1520, pad([15]));
        at(1600, pad([]));      // let go
        at(1610, pad([15]));    // pressed again: at once
        at(1620, pad([15, 4])); // LB held: a cabinet (on the next step)
        at(1960, pad([15, 4]));
        at(1970, pad([12]));    // another direction: at once
        return out;
    }""")
    assert got == [[0, 'right'], [16, ''], [349, ''], [350, 'right'], [400, ''], [440, 'right'],
                   [1500, 'right'], [1520, ''], [1600, ''], [1610, 'right'], [1620, ''],
                   [1960, 'right+cab'], [1970, 'up']], got


def test_button_presses_and_releases_are_edges(page):
    got = page.evaluate("""async () => { """ + MOD + """
        const pad = (pressed) => ({axes: [0, 0],
            buttons: Array.from({length: 17}, (_, i) => ({pressed: pressed.includes(i), value: 0}))});
        let st = null; const out = [];
        for (const [t, p] of [[0, []], [10, [0]], [20, [0]], [30, [0, 1]], [40, [1]], [50, []]]) {
            const r = m.idmPadFrame(st, pad(p), t); st = r.state;
            out.push(r.actions.filter(a => a.type !== 'move').map(a => a.type + a.button).join(','));
        }
        return [out, m.idmPadName('Xbox Wireless Controller (STANDARD GAMEPAD Vendor: 045e Product: 0b13)'),
                m.idmPadName('DualSense Wireless Controller (STANDARD GAMEPAD Vendor: 054c Product: 0ce6)'),
                m.idmPadName('')];
    }""")
    assert got == [['', 'press0', '', 'press1', 'release0', 'release1'],
                   'Xbox Wireless Controller', 'DualSense Wireless Controller', 'Controller'], got


# ── a fake pad in the app ─────────────────────────────────────────────────

FAKE_JS = """() => {
    const pad = {id: 'Xbox Wireless Controller (STANDARD GAMEPAD Vendor: 045e Product: 0b13)',
        index: 0, connected: true, mapping: 'standard', axes: [0, 0, 0, 0], timestamp: 0,
        buttons: Array.from({length: 17}, () => ({pressed: false, touched: false, value: 0}))};
    window.__pad = pad;
    window.__focus = true;
    Object.defineProperty(navigator, 'getGamepads', {configurable: true, value: () => [window.__pad, null, null, null]});
    Object.defineProperty(document, 'hasFocus', {configurable: true, value: () => window.__focus});
    const ev = new Event('gamepadconnected');
    ev.gamepad = pad;
    window.dispatchEvent(ev);
}"""


SEEN_JS = """([bs, down]) => {
    const p = window.app._idmPad, s = p && p.pads.get(0);
    return !!s && bs.every(b => !!s.buttons[b] === down);
}"""


def press(pg, *buttons):
    """Down, and held until the app's frame has read it (never a sleep: a
    busy machine runs fewer frames)."""
    pg.evaluate("(bs) => bs.forEach(b => { window.__pad.buttons[b].pressed = true; window.__pad.buttons[b].value = 1; })",
                list(buttons))
    pg.wait_for_function(SEEN_JS, arg=[list(buttons), True], timeout=5000)


def release(pg, *buttons):
    pg.evaluate("(bs) => bs.forEach(b => { window.__pad.buttons[b].pressed = false; window.__pad.buttons[b].value = 0; })",
                list(buttons))
    pg.wait_for_function(SEEN_JS, arg=[list(buttons), False], timeout=5000)


def tap(pg, *buttons):
    """A press the app reads, then the release it reads."""
    press(pg, *buttons)
    release(pg, *buttons)


def history_index(pg):
    return pg.evaluate("() => window.app.historyIndex")


def frame_running(pg):
    return pg.evaluate("() => !!(window.app._idmPad && window.app._idmPad.frame)")


def test_no_frame_loop_without_a_pad(page):
    reset_project(page)
    assert not frame_running(page)
    assert not page.is_visible('#idm-pad-help')


def test_a_fake_pad_walks_marks_paints_and_undoes(page):
    reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    page.evaluate(FAKE_JS)
    toast = page.locator('#app-toast-host').inner_text()
    assert 'Controller connected: Xbox Wireless Controller' in toast, toast
    assert page.is_visible('#idm-pad-help')
    assert 'A / Cross' in page.inner_text('#idm-pad-help')
    assert 'focus' in page.inner_text('#idm-pad-help')
    page.wait_for_function("() => !!window.app._idmPad.frame")
    page.evaluate("""() => { const app = window.app;
        app.selectLayer(app.project.layers.find(x => x.name === 'IdmA')); }""")
    # the first step starts the highlight on the selected screen
    tap(page, 15)
    got = settled(page, lambda: hl(page), lambda v: v == ['IdmA', '0,0,0,0'])
    assert got == ['IdmA', '0,0,0,0'], got
    tap(page, 15)
    assert settled(page, lambda: hl(page), lambda v: v == ['IdmA', '0,0,1,0']) == ['IdmA', '0,0,1,0']
    tap(page, 13)
    assert settled(page, lambda: hl(page), lambda v: v == ['IdmA', '0,0,1,1']) == ['IdmA', '0,0,1,1']
    # RB held: a whole cabinet
    press(page, 5)
    tap(page, 15)
    release(page, 5)
    assert settled(page, lambda: hl(page), lambda v: v == ['IdmA', '1,0,1,1']) == ['IdmA', '1,0,1,1']
    # A: mark, one undo step; A again: clear
    h0 = history_index(page)
    tap(page, 0)
    got = settled(page, lambda: served_idm(page, 'IdmA'), lambda v: v and '1,0,1,1' in v['marks'])
    assert list(got['marks']) == ['1,0,1,1'], got
    assert history_index(page) == h0 + 1
    tap(page, 0)
    settled(page, lambda: served_idm(page, 'IdmA'), lambda v: v and v['marks'] == {})
    assert history_index(page) == h0 + 2
    # B: undo brings the mark back
    tap(page, 1)
    assert settled(page, lambda: marks_of(page, 'IdmA'), lambda v: '1,0,1,1' in v) == {
        '1,0,1,1': {'style': 'color', 'color': '#ff1a1a'}}
    # paint: A held, two steps left - the first module was marked, so the
    # paint CLEARS what it passes (never flips back and forth)
    page.evaluate("""() => { const app = window.app, l = app.project.layers.find(x => x.name === 'IdmA');
        l.idm = {modulesX: 2, modulesY: 2, marks: {'1,0,1,1': {style: 'color', color: '#ff1a1a'},
                                                  '1,0,0,1': {style: 'color', color: '#ff1a1a'}}};
        app.updateLayers([l], true, 'Marks'); window.canvasRenderer.render(); }""")
    settled(page, lambda: served_idm(page, 'IdmA'), lambda v: v and len(v['marks']) == 2)
    h1 = history_index(page)
    press(page, 0)
    tap(page, 14)                     # onto 1,0,0,1 (marked): cleared
    tap(page, 14)                     # onto 0,0,1,1 (unmarked): stays clear
    release(page, 0)
    got = settled(page, lambda: served_idm(page, 'IdmA'), lambda v: v and v['marks'] == {})
    assert got['marks'] == {}, got
    assert history_index(page) == h1 + 1
    # and a mark paint: A on an unmarked module, two steps right
    press(page, 0)
    tap(page, 15)
    tap(page, 15)
    release(page, 0)
    got = settled(page, lambda: served_idm(page, 'IdmA'), lambda v: v and len(v['marks']) == 3)
    assert set(got['marks']) == {'0,0,1,1', '1,0,0,1', '1,0,1,1'}, got
    assert history_index(page) == h1 + 2
    # Y: the next screen; X: the next field color
    tap(page, 3)
    assert settled(page, lambda: hl(page), lambda v: v and v[0] == 'IdmB')[0] == 'IdmB'
    tap(page, 2)
    assert settled(page, lambda: (served_field(page) or {}).get('color'), lambda v: v == '#ff0000') == '#ff0000'
    # View / Share: clear the highlight
    tap(page, 8)
    assert settled(page, lambda: hl(page), lambda v: v is None) is None
    # held: the repeat runs on its own
    tap(page, 15)
    start = hl(page)
    press(page, 13)
    page.wait_for_timeout(700)
    release(page, 13)
    assert hl(page) != start
    assert not page._errors, page._errors


def test_out_of_focus_nothing_acts_and_a_locked_screen_refuses(page):
    reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    page.evaluate(FAKE_JS)
    page.wait_for_function("() => !!window.app._idmPad.frame")
    page.evaluate("""() => { const app = window.app, a = app.project.layers.find(x => x.name === 'IdmA');
        app.selectLayer(a); app._idmSetHighlight(a.id, '0,0,0,0'); }""")
    page.evaluate("() => { window.__focus = false; }")
    tap(page, 15)
    tap(page, 0)
    assert hl(page) == ['IdmA', '0,0,0,0']
    assert marks_of(page, 'IdmA') == {}
    # back in focus: a button held while away does not fire
    press(page, 0)
    page.evaluate("() => { window.__focus = true; }")
    page.wait_for_timeout(100)
    release(page, 0)
    assert marks_of(page, 'IdmA') == {}
    # a locked screen: the usual error, no mark
    page.evaluate("""() => { const app = window.app, a = app.project.layers.find(x => x.name === 'IdmA');
        a.locked = true; }""")
    tap(page, 0)
    page.wait_for_timeout(200)
    assert marks_of(page, 'IdmA') == {}
    assert 'IdmA is locked' in page.locator('#app-toast-host').inner_text()
    page.evaluate("""() => { const a = window.app.project.layers.find(x => x.name === 'IdmA');
        a.locked = false; }""")


def test_disconnect_and_leaving_the_tab_stop_the_loop(page):
    reset_project(page)
    page.evaluate(FAKE_JS)
    page.wait_for_function("() => !!window.app._idmPad.frame")
    page.click('.view-tab[data-mode="pixel-map"]')
    page.wait_for_function("() => !window.app._idmPad.frame")
    page.click('.view-tab[data-mode="idm"]')
    page.wait_for_function("() => !!window.app._idmPad.frame")
    page.evaluate("""() => { window.__pad.connected = false;
        const ev = new Event('gamepaddisconnected'); ev.gamepad = window.__pad; window.dispatchEvent(ev);
        Object.defineProperty(navigator, 'getGamepads', {configurable: true, value: () => [null, null, null, null]}); }""")
    page.wait_for_function("() => !window.app._idmPad.frame")
    assert 'Controller disconnected: Xbox Wireless Controller' in page.locator('#app-toast-host').inner_text()
    assert not page.is_visible('#idm-pad-help')
