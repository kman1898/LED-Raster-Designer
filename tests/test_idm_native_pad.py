"""The computer's game controller, read natively, on the IDM Locator tab
(app-idm-native-pad.js, src/native_pad.py; owner, 2026-11-17).

What this file pins, with the reader played by the test (the server's
bridge is handed the reader's messages, as the real reader's would be):

* A touchpad slide is module steps at the panel's speed (16 modules for the
  pad's width at the middle setting, 1.4 times as far or less a setting
  up or down), what is under a module carried over, a slant walked as a
  slant, never more than 8 steps an axis at once.
* On the host page: the connect toast and the panel name the pad and its
  battery, the touchpad and its speed show, and the note says it works
  with another window in front. It acts with the window unfocused and
  with no animation frames at all (a window behind another may get none).
  A held D-pad repeats, speeding up, and stops when let go (owner,
  2026-11-24). A slide glides the highlight; A held while sliding paints;
  the speed setting is kept. LB or RB held while sliding moves by whole cabinets.
* A page that loads (or reloads) with a pad already connected takes it in
  silence: only a connect or disconnect after that is toasted.
* A press never acts twice: the browser seeing the same pad changes
  nothing while the reader has it, and says nothing.
* On another tab nothing happens; back on the tab it acts again.
* Moves stay on the canvas the highlight is on; View / Share (the one
  button table's next canvas) takes it to the next.
* Only one page gets it: a page on another machine is never told; a second
  designer page on this computer that opens the tab takes it, and the
  first lets go of what it held.
* With no controller the panel says nothing about one, whatever the
  reader's state (owner, 2026-11-17); the real reader's status reaches the
  page and the reader goes with the app.

Run locally:
    python -m pytest tests/test_idm_native_pad.py -v -n 4 --dist loadfile --browser chromium
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from conftest import settled  # noqa: E402
from test_idm_field_highlight import (  # noqa: E402
    _new_page, reset_project, set_layout, open_tab, marks_of, hl, wait_layers,
)

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

import native_pad  # noqa: E402

MOD = "const m = await import('/static/js/app-idm-native-pad.js');"
DUALSENSE = {'id': 1, 'name': 'DualSense Wireless Controller', 'battery': 'full', 'touchpad': True}


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project exactly as this module found it
    (see conftest.server_project_guard)."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context, pg = _new_page(pw_browser, e2e_server)
    yield pg
    context.close()


@pytest.fixture
def bridge(page):
    """The reader's side, played here: running, no pad yet."""
    b = native_pad.BRIDGE
    b.handle({'t': 'status', 'pads': []})
    b.handle({'t': 'reader', 'state': 'running'})
    yield b
    b.handle({'t': 'status', 'pads': []})
    b.handle({'t': 'reader', 'state': 'off'})


def connect(b, *pads):
    b.handle({'t': 'reader', 'state': 'running'})
    b.handle({'t': 'status', 'pads': list(pads or [DUALSENSE]), 'inputMonitoring': None})


def state(b, pressed=(), axes=(0, 0, 0, 0), touch=(0, 0), pad=1):
    b.handle({'t': 'state', 'id': pad, 'buttons': [1 if i in pressed else 0 for i in range(17)],
              'axes': list(axes), 'touch': list(touch)})


def tap(b, pg, button):
    """A press and its release, each read by the page."""
    state(b, [button])
    pg.wait_for_timeout(60)
    state(b, [])
    pg.wait_for_timeout(60)


def host_ready(pg, b):
    """The page told the server its tab is open and heard back."""
    settled(pg, lambda: b.target, lambda v: v is not None)
    assert b.target is not None
    pg.wait_for_function("() => window.app._idmNative && window.app._idmNative.host", timeout=5000)


def unfocused_and_no_frames(pg):
    """The window behind another: no focus, and no animation frames."""
    pg.evaluate("""() => {
        Object.defineProperty(document, 'hasFocus', {configurable: true, value: () => false});
        window.__raf = window.requestAnimationFrame;
        window.requestAnimationFrame = () => 0;
    }""")


def set_speed(pg, value):
    pg.evaluate("""(v) => { const el = document.getElementById('idm-pad-touch-speed');
        el.value = String(v); el.dispatchEvent(new Event('input')); }""", value)


def frames_back(pg):
    pg.evaluate("""() => {
        delete document.hasFocus;
        if (window.__raf) window.requestAnimationFrame = window.__raf;
    }""")


# ── the glide, apart from the app ─────────────────────────────────────────

def test_a_slide_is_module_steps_at_the_panel_speed(page):
    got = page.evaluate("""async () => { """ + MOD + """
        const g = (rest, dx, dy, s) => m.idmTouchGlide(rest, dx, dy, s);
        return {
            mid: m.idmTouchModulesPerWidth(5), slow: m.idmTouchModulesPerWidth(1),
            fast: m.idmTouchModulesPerWidth(9), junk: m.idmTouchModulesPerWidth('x'),
            three: g(null, 3 / 16, 0, 5).steps,
            left: g(null, -2 / 16, 0, 5).steps,
            slant: g(null, 3 / 16, 2 / 16, 5).steps,
            small: [g(null, 0.4 / 16, 0, 5), g(g(null, 0.4 / 16, 0, 5).rest, 0.7 / 16, 0, 5)],
            cap: g(null, 1, -1, 9).steps,
            label: [m.idmNativePadLabel({name: 'DualSense Wireless Controller', battery: 'low'}),
                    m.idmNativePadLabel({name: 'Xbox Wireless Controller', battery: 'wired'}),
                    m.idmNativePadLabel({name: 'Pad', battery: 'unknown'})],
        };
    }""")
    assert got['mid'] == 16 and got['junk'] == 16
    assert got['slow'] == pytest.approx(16 / 1.4 ** 4)
    assert got['fast'] == pytest.approx(16 * 1.4 ** 4)
    assert got['three'] == ['right', 'right', 'right']
    assert got['left'] == ['left', 'left']
    assert got['slant'] == ['right', 'down', 'right', 'down', 'right']
    first, second = got['small']
    assert first['steps'] == [] and first['rest'][0] == pytest.approx(0.4)
    assert second['steps'] == ['right'] and second['rest'][0] == pytest.approx(0.1)
    assert got['cap'].count('right') == 8 and got['cap'].count('up') == 8
    assert got['label'] == ['DualSense Wireless Controller, battery low',
                            'Xbox Wireless Controller, on a cable', 'Pad']


# ── on the host page ──────────────────────────────────────────────────────

def test_the_host_page_names_the_pad_and_acts_behind_another_window(page, bridge):
    reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    host_ready(page, bridge)
    assert not page.is_visible('#idm-pad-help')
    connect(bridge)
    page.wait_for_function("() => window.app._idmNative.pads.size === 1", timeout=5000)
    toast = page.locator('#app-toast-host').inner_text()
    assert 'Controller connected: DualSense Wireless Controller, battery full' in toast, toast
    assert page.is_visible('#idm-pad-help')
    assert page.inner_text('#idm-pad-help-name') == 'DualSense Wireless Controller, battery full'
    assert page.is_visible('#idm-pad-touch')
    assert 'Slide a finger to move the highlight' in page.inner_text('#idm-pad-touch')
    assert page.inner_text('#idm-pad-help-focus') == 'Works while this tab is open, even with another window in front.'
    unfocused_and_no_frames(page)
    try:
        page.evaluate("""() => { const app = window.app;
            app.selectLayer(app.project.layers.find(x => x.name === 'IdmA')); }""")
        tap(bridge, page, 15)                   # the first step starts it
        assert settled(page, lambda: hl(page), lambda v: v == ['IdmA', '0,0,0,0']) == ['IdmA', '0,0,0,0']
        tap(bridge, page, 15)
        assert settled(page, lambda: hl(page), lambda v: v == ['IdmA', '0,0,1,0']) == ['IdmA', '0,0,1,0']
        tap(bridge, page, 0)                    # A: mark
        got = settled(page, lambda: marks_of(page, 'IdmA'), lambda v: '0,0,1,0' in v)
        assert list(got) == ['0,0,1,0'], got
        # held: the reader sends it again and again, and it repeats
        start = hl(page)
        for _ in range(20):
            state(bridge, [13])                 # D-pad down, held
            page.wait_for_timeout(35)
        state(bridge, [])
        assert hl(page) != start
        # held longer, it speeds up as a held arrow does (owner,
        # 2026-11-24), and stops the moment it is let go
        page.evaluate("""() => { const app = window.app; window.__steps = [];
            if (!app.__stepSpy) { const real = app._idmStep.bind(app); app.__stepSpy = true;
                app._idmStep = function (...a) { window.__steps.push(performance.now()); return real(...a); }; } }""")
        for _ in range(36):
            state(bridge, [15])                 # D-pad right, held
            page.wait_for_timeout(35)
        released = page.evaluate("() => performance.now()")
        state(bridge, [])
        page.wait_for_timeout(400)
        steps = page.evaluate("() => window.__steps.slice()")
        gaps = [round(b - a) for a, b in zip(steps, steps[1:])]
        assert [t for t in steps if t > released + 50] == [], (steps, released)
        assert len(steps) >= 10 and gaps[0] >= 300 and max(gaps[-3:]) <= 80, gaps
    finally:
        frames_back(page)
    assert not page._errors, page._errors


def test_a_slide_glides_paints_with_a_held_and_the_speed_is_kept(page, bridge):
    reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    host_ready(page, bridge)
    connect(bridge)
    page.wait_for_function("() => window.app._idmNative.pads.size === 1", timeout=5000)
    page.evaluate("""() => { const app = window.app, a = app.project.layers.find(x => x.name === 'IdmA');
        app.selectLayer(a); app._idmSetHighlight(a.id, '0,0,0,0'); }""")
    unfocused_and_no_frames(page)
    try:
        # three modules' worth to the right at the middle speed
        state(bridge, [], touch=(3 / 16, 0))
        assert settled(page, lambda: hl(page), lambda v: v == ['IdmA', '1,0,1,0']) == ['IdmA', '1,0,1,0']
        # a slant: one down, one left
        state(bridge, [], touch=(-1 / 16, 1 / 16 + 0.001))
        assert settled(page, lambda: hl(page), lambda v: v == ['IdmA', '1,0,0,1']) == ['IdmA', '1,0,0,1']
        # A held while sliding left paints every module passed
        state(bridge, [0])
        page.wait_for_timeout(60)
        state(bridge, [0], touch=(-2 / 16 - 0.001, 0))
        page.wait_for_timeout(60)
        state(bridge, [])
        got = settled(page, lambda: marks_of(page, 'IdmA'), lambda v: len(v) == 3)
        assert set(got) == {'1,0,0,1', '0,0,1,1', '0,0,0,1'}, got
    finally:
        frames_back(page)
    # the speed: faster goes further, and is kept for this viewer
    page.evaluate("() => window.app._idmSetHighlight(window.app.project.layers.find(x => x.name === 'IdmA').id, '0,0,0,0')")
    set_speed(page, 9)
    assert page.evaluate("() => localStorage.getItem('lrdIdmTouchSpeed')") == '9'
    state(bridge, [], touch=(1 / 16, 0))         # 3.8 modules at speed 9
    assert settled(page, lambda: hl(page), lambda v: v == ['IdmA', '1,0,1,0']) == ['IdmA', '1,0,1,0']
    set_speed(page, 5)
    assert not page._errors, page._errors


SPEED_JS = """() => [document.getElementById('idm-pad-touch-speed').value,
                       window.app._idmNative.speed]"""
WIRED_JS = "() => window.app && window.app._idmNative && window.app._idmNative.wired"


def test_the_touchpad_speed_is_the_viewers_and_survives_a_reload(e2e_server, pw_browser):
    """The speed is this viewer's setting, kept in the browser: a reload
    shows it on the slider and the glide reads it; it never touches the show
    (no layer or project write, nothing to undo). Nothing stored, or a
    value off the slider, reads as the middle setting."""
    context, pg = _new_page(pw_browser, e2e_server)
    try:
        pg.wait_for_function(WIRED_JS, timeout=10000)
        speed = lambda: pg.evaluate(SPEED_JS)  # noqa: E731
        assert speed() == ['5', 5]
        pg.evaluate("""() => { window.__writes = [];
            const f = window.fetch;
            window.fetch = (url, o) => { const m = (o && o.method) || 'GET';
                const u = String(url);
                if (m !== 'GET' && (u.includes('/api/layer') || u.includes('/api/project'))) {
                    window.__writes.push(m + ' ' + u);
                }
                return f(url, o); }; }""")
        project = pg.evaluate("() => JSON.stringify(window.app.project)")
        history = pg.evaluate("() => window.app.history.length")
        set_speed(pg, 8)
        pg.wait_for_timeout(400)
        assert speed() == ['8', 8]
        assert pg.evaluate("() => localStorage.getItem('lrdIdmTouchSpeed')") == '8'
        assert pg.evaluate("() => window.__writes") == []
        assert pg.evaluate("() => JSON.stringify(window.app.project)") == project
        assert pg.evaluate("() => window.app.history.length") == history
        pg.reload(wait_until='domcontentloaded')
        pg.wait_for_function(WIRED_JS, timeout=15000)
        assert speed() == ['8', 8]
        # a value off the slider reads as the middle setting
        pg.evaluate("() => localStorage.setItem('lrdIdmTouchSpeed', '42')")
        pg.reload(wait_until='domcontentloaded')
        pg.wait_for_function(WIRED_JS, timeout=15000)
        assert speed() == ['5', 5]
        assert not pg._errors, pg._errors
    finally:
        context.close()


def test_lb_or_rb_held_while_sliding_moves_by_whole_cabinets(page, bridge):
    """IdmA is 3 x 2 cabinets of 2 x 2 modules: a key is "column,row,module
    x,module y". A bumper held turns each module's worth of slide into a
    whole cabinet, the module within it kept."""
    reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    host_ready(page, bridge)
    connect(bridge)
    page.wait_for_function("() => window.app._idmNative.pads.size === 1", timeout=5000)
    page.evaluate("""() => { const app = window.app, a = app.project.layers.find(x => x.name === 'IdmA');
        app.selectLayer(a); app._idmSetHighlight(a.id, '0,0,0,0'); }""")
    one = 1 / 16 + 0.01                          # a module's worth at the middle speed

    def slide(pressed, dx, dy, want):
        """The bumpers as given, pressed first on their own, then a slide
        with nothing carried over from the last one."""
        page.evaluate("() => { window.app._idmNative.rest = [0, 0]; }")
        state(bridge, pressed)
        page.wait_for_timeout(60)
        state(bridge, pressed, touch=(dx, dy))
        got = settled(page, lambda: hl(page), lambda v: v == ['IdmA', want])
        state(bridge, [])
        page.wait_for_timeout(60)
        return got

    assert slide([4], one, 0, '1,0,0,0') == ['IdmA', '1,0,0,0']          # LB: a cabinet right
    assert slide([4], -one, 0, '0,0,0,0') == ['IdmA', '0,0,0,0']         # and back
    assert slide([4], 2 * one, 0, '2,0,0,0') == ['IdmA', '2,0,0,0']      # two: two cabinets
    assert slide([5], 0, one, '2,1,0,0') == ['IdmA', '2,1,0,0']          # RB: a cabinet down
    assert slide([], one, 0, '2,1,1,0') == ['IdmA', '2,1,1,0']           # none: one module
    assert slide([5], -one, 0, '1,1,1,0') == ['IdmA', '1,1,1,0']         # RB: a cabinet left, module kept
    assert slide([4, 5], 0, -one, '1,0,1,0') == ['IdmA', '1,0,1,0']      # both: a cabinet up
    assert not marks_of(page, 'IdmA'), 'a bumper marks nothing'
    assert not page._errors, page._errors


# Every toast the app puts up, from the page's first moment (a status can
# land before a test could look).
TOAST_SPY = """
window.__toasts = [];
(() => { let app;
    Object.defineProperty(window, 'app', {configurable: true, get: () => app, set: (v) => {
        app = v;
        const toast = v && v._toast;
        if (typeof toast === 'function') {
            v._toast = function (msg, ...rest) { window.__toasts.push(String(msg)); return toast.call(this, msg, ...rest); };
        }
    }});
})();
"""


def _page_with_toast_spy(pw_browser, url):
    context = pw_browser.new_context(viewport={'width': 1200, 'height': 900})
    context.add_init_script("try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    context.add_init_script(TOAST_SPY)
    pg = context.new_page()
    pg._errors = []
    pg.on('pageerror', lambda err: pg._errors.append(str(err)))
    pg.goto(url, wait_until='domcontentloaded')
    _wait_ready(pg)
    return context, pg


def _wait_ready(pg):
    pg.wait_for_function("() => window.app && window.app.project && window.app.history"
                         " && window.app.socket && window.app.socket.connected", timeout=15000)
    pg.wait_for_function("() => window.app._idmNative && window.app._idmNative.host", timeout=10000)


def test_a_page_that_loads_with_a_pad_connected_says_nothing_until_it_changes(page, bridge, e2e_server,
                                                                              pw_browser):
    """A load or reload is not a controller connecting: the page's first
    status takes the pads already there in silence."""
    reset_project(page)
    host_ready(page, bridge)
    connect(bridge)
    page.wait_for_function("() => window.app._idmNative.pads.size === 1", timeout=5000)
    toasts = lambda pg: [t for t in pg.evaluate("() => window.__toasts") if 'Controller' in t]
    context, fresh = _page_with_toast_spy(pw_browser, e2e_server)
    try:
        assert fresh.evaluate("() => window.app._idmNative.pads.size") == 1
        open_tab(fresh)
        fresh.wait_for_timeout(300)
        assert fresh.inner_text('#idm-pad-help-name') == 'DualSense Wireless Controller, battery full'
        assert toasts(fresh) == []
        # a reload is a load: silent again
        fresh.reload(wait_until='domcontentloaded')
        _wait_ready(fresh)
        fresh.wait_for_timeout(300)
        assert fresh.evaluate("() => window.app._idmNative.pads.size") == 1
        assert toasts(fresh) == []
        # a real change after that is said
        bridge.handle({'t': 'status', 'pads': []})
        fresh.wait_for_function("() => window.app._idmNative.pads.size === 0", timeout=5000)
        connect(bridge)
        fresh.wait_for_function("() => window.app._idmNative.pads.size === 1", timeout=5000)
        assert toasts(fresh) == ['Controller disconnected: DualSense Wireless Controller',
                                 'Controller connected: DualSense Wireless Controller, battery full']
        assert not fresh._errors, fresh._errors
    finally:
        context.close()
    # the first page takes the controller back
    page.evaluate("() => window.dispatchEvent(new Event('focus'))")
    assert settled(page, lambda: bridge.target, lambda v: v is not None)
    assert not page._errors, page._errors


def test_a_press_never_acts_twice_when_the_browser_sees_the_pad_too(page, bridge):
    reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    host_ready(page, bridge)
    connect(bridge)
    page.wait_for_function("() => window.app._idmNative.pads.size === 1", timeout=5000)
    page.evaluate("""() => { const app = window.app, a = app.project.layers.find(x => x.name === 'IdmA');
        app.selectLayer(a); app._idmSetHighlight(a.id, '0,0,0,0');
        const pad = {id: 'DualSense Wireless Controller (STANDARD GAMEPAD Vendor: 054c Product: 0ce6)',
            index: 0, connected: true, mapping: 'standard', axes: [0, 0, 0, 0], timestamp: 0,
            buttons: Array.from({length: 17}, () => ({pressed: false, touched: false, value: 0}))};
        window.__pad = pad;
        Object.defineProperty(navigator, 'getGamepads', {configurable: true, value: () => [window.__pad, null, null, null]});
        window.__toasts = 0;
        const host = document.getElementById('app-toast-host');
        new MutationObserver(() => { window.__toasts++; }).observe(host, {childList: true, subtree: true});
        const ev = new Event('gamepadconnected'); ev.gamepad = pad; window.dispatchEvent(ev);
    }""")
    page.wait_for_timeout(200)
    assert page.evaluate("() => window.__toasts") == 0, 'the browser pad is not announced again'
    assert page.inner_text('#idm-pad-help-name') == 'DualSense Wireless Controller, battery full'
    # the same press seen by both: one step
    page.evaluate("() => { window.__pad.buttons[15].pressed = true; window.__pad.buttons[15].value = 1; }")
    state(bridge, [15])
    page.wait_for_timeout(150)
    page.evaluate("() => { window.__pad.buttons[15].pressed = false; window.__pad.buttons[15].value = 0; }")
    state(bridge, [])
    page.wait_for_timeout(300)
    assert hl(page) == ['IdmA', '0,0,1,0']
    # the browser pressing alone does nothing while the reader has the pad
    page.evaluate("() => { window.__pad.buttons[15].pressed = true; window.__pad.buttons[15].value = 1; }")
    page.wait_for_timeout(300)
    page.evaluate("() => { window.__pad.buttons[15].pressed = false; window.__pad.buttons[15].value = 0; }")
    page.wait_for_timeout(100)
    assert hl(page) == ['IdmA', '0,0,1,0']
    page.evaluate("""() => { window.__pad.connected = false;
        const ev = new Event('gamepaddisconnected'); ev.gamepad = window.__pad; window.dispatchEvent(ev);
        Object.defineProperty(navigator, 'getGamepads', {configurable: true, value: () => [null, null, null, null]}); }""")
    assert not page._errors, page._errors


def test_on_another_tab_nothing_happens(page, bridge):
    reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    host_ready(page, bridge)
    connect(bridge)
    page.wait_for_function("() => window.app._idmNative.pads.size === 1", timeout=5000)
    page.evaluate("""() => { const app = window.app, a = app.project.layers.find(x => x.name === 'IdmA');
        app._idmSetHighlight(a.id, '0,0,0,0'); }""")
    page.click('.view-tab[data-mode="pixel-map"]')
    settled(page, lambda: bridge.target, lambda v: v is None)
    assert bridge.target is None
    page.evaluate("() => { window.__inputs = 0; const f = window.app._idmNativeInput.bind(window.app);"
                  " window.app._idmNativeInput = (d) => { window.__inputs++; return f(d); }; }")
    tap(bridge, page, 15)
    state(bridge, [], touch=(0.5, 0))
    page.wait_for_timeout(200)
    assert page.evaluate("() => window.__inputs") == 0
    assert page.evaluate("() => window.app._idmHl() && window.app._idmHl().key") == '0,0,0,0'
    open_tab(page)
    host_ready(page, bridge)
    tap(bridge, page, 15)
    assert settled(page, lambda: hl(page), lambda v: v == ['IdmA', '0,0,1,0']) == ['IdmA', '0,0,1,0']
    page.evaluate("() => { delete window.app._idmNativeInput; }")
    assert not page._errors, page._errors


SECOND_CANVAS_JS = """async () => {
    const post = (url, body) => fetch(url, {method: 'POST',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    const put = (url, body) => fetch(url, {method: 'PUT',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    const first = window.app.project.canvases[0].id;
    const made = await (await post('/api/canvas', {raster_width: 640, raster_height: 360})).json();
    const c2 = (made.canvases || []).find(c => c.id !== first);
    await put('/api/canvas/' + c2.id, {raster_width: 640, raster_height: 360, workspace_x: 2400, workspace_y: 0});
    await post('/api/layer/add', {name: 'IdmC', columns: 2, rows: 1,
        cabinet_width: 160, cabinet_height: 160, offset_x: 0, offset_y: 0, canvas_id: c2.id});
    await put('/api/canvas/' + first + '/active', {});
    window.app.loadProject();
    return c2.id;
}"""


def test_a_slide_stays_on_the_canvas_the_highlight_is_on(page, bridge):
    reset_project(page)
    page.evaluate(SECOND_CANVAS_JS)
    wait_layers(page, 3)
    page.wait_for_timeout(500)
    set_layout(page, 'IdmB', 2, 2)
    host_ready(page, bridge)
    connect(bridge)
    page.wait_for_function("() => window.app._idmNative.pads.size === 1", timeout=5000)
    page.evaluate("""() => { const app = window.app, b = app.project.layers.find(x => x.name === 'IdmB');
        app._idmSetHighlight(b.id, '1,0,1,0'); }""")
    for _ in range(4):
        state(bridge, [], touch=(0.5, 0))
        page.wait_for_timeout(80)
    page.wait_for_timeout(200)
    assert hl(page) == ['IdmB', '1,0,1,0']
    # the one table's View / Share: the next canvas, and the slide keeps to it
    tap(bridge, page, 8)
    assert settled(page, lambda: hl(page), lambda v: v and v[0] == 'IdmC')[0] == 'IdmC'
    state(bridge, [], touch=(-0.5, 0))
    page.wait_for_timeout(200)
    assert hl(page)[0] == 'IdmC'
    assert not page._errors, page._errors


def test_one_page_at_a_time_and_never_a_page_on_another_machine(page, bridge, e2e_server, pw_browser,
                                                                 monkeypatch):
    import routes_dialog
    reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    host_ready(page, bridge)
    first = bridge.target
    connect(bridge)
    page.wait_for_function("() => window.app._idmNative.pads.size === 1", timeout=5000)
    page.evaluate("""() => { const app = window.app, a = app.project.layers.find(x => x.name === 'IdmA');
        app._idmSetHighlight(a.id, '0,0,0,0'); }""")
    # a tablet: this computer's controller is none of its business
    same = {'yes': False}
    real = routes_dialog._is_same_machine
    monkeypatch.setattr(routes_dialog, '_is_same_machine', lambda addr: same['yes'] and real(addr))
    context, tab = _new_page(pw_browser, e2e_server, viewport=(1200, 900))
    try:
        wait_layers(tab)
        open_tab(tab)
        tab.wait_for_function("() => window.app._idmNative && window.app._idmNative.sentIdm === true", timeout=5000)
        tab.wait_for_timeout(300)
        assert bridge.target == first
        tab.evaluate("() => { window.__inputs = 0; const f = window.app._idmNativeInput.bind(window.app);"
                     " window.app._idmNativeInput = (d) => { window.__inputs++; return f(d); }; }")
        tap(bridge, page, 15)
        assert settled(page, lambda: hl(page), lambda v: v == ['IdmA', '0,0,1,0']) == ['IdmA', '0,0,1,0']
        tab.wait_for_timeout(200)
        assert tab.evaluate("() => window.__inputs") == 0
        assert tab.evaluate("() => window.app._idmNative.host") is False
        assert not tab.is_visible('#idm-pad-help')
        # now a second designer window on THIS computer: it takes the
        # controller when it opens the tab or takes the focus, and the
        # first lets go of what it held
        same['yes'] = True
        state(bridge, [0])                       # A held on the first page
        page.wait_for_timeout(100)
        tab.evaluate("() => window.dispatchEvent(new Event('focus'))")
        settled(page, lambda: bridge.target, lambda v: v not in (None, first))
        assert bridge.target not in (None, first)
        # the paint the first page had going ends there, as one edit
        assert settled(page, lambda: page.evaluate("() => !window.app._idmState().stroke"), bool)
        assert '0,0,1,0' in marks_of(page, 'IdmA')
        state(bridge, [])
        tap(bridge, page, 15)
        tab.wait_for_timeout(200)
        assert tab.evaluate("() => window.__inputs") >= 2
        # the first page takes it back with the focus
        page.evaluate("() => window.dispatchEvent(new Event('focus'))")
        settled(page, lambda: bridge.target, lambda v: v == first)
        assert bridge.target == first
    finally:
        context.close()
    assert not page._errors, page._errors


# Nothing about a controller in the panel: no button list, and no line
# that once said why none was found.
NONE_SHOWN = """() => {
    const el = document.getElementById('idm-pad-help');
    return {help: !!el && !el.hidden && el.getBoundingClientRect().height > 0,
            line: !!document.getElementById('idm-pad-native')};
}"""


def test_with_no_controller_the_panel_says_nothing_about_one(page, bridge):
    """Owner, 2026-11-17: "Dont do anything when no controller is found"."""
    reset_project(page)
    host_ready(page, bridge)
    for reader in ('running', 'unavailable', 'failed', 'restarting', 'off'):
        bridge.handle({'t': 'reader', 'state': reader, 'why': 'test'})
        bridge.handle({'t': 'status', 'pads': [], 'inputMonitoring': 'denied'})
        page.wait_for_timeout(150)
        got = page.evaluate(NONE_SHOWN)
        assert got == {'help': False, 'line': False}, (reader, got)
    # a pad: its line as built; gone again: nothing
    connect(bridge)
    page.wait_for_function("() => window.app._idmNative.pads.size === 1", timeout=5000)
    assert page.inner_text('#idm-pad-help-name') == 'DualSense Wireless Controller, battery full'
    bridge.handle({'t': 'status', 'pads': []})
    page.wait_for_function("() => window.app._idmNative.pads.size === 0", timeout=5000)
    assert 'Controller disconnected: DualSense Wireless Controller' in page.locator('#app-toast-host').inner_text()
    assert page.evaluate(NONE_SHOWN) == {'help': False, 'line': False}
    assert not page._errors, page._errors


def test_the_real_reader_reaches_the_page_and_quits_with_the_app(page, bridge):
    """The whole chain with the real reader process and no controller:
    started beside the server, its status on the host page (and nothing
    shown, there being no pad), gone on quit."""
    pytest.importorskip('pygame')
    reset_project(page)
    host_ready(page, bridge)
    bridge.handle({'t': 'reader', 'state': 'off'})
    page.wait_for_function("() => window.app._idmNative.status && window.app._idmNative.status.reader === 'off'",
                           timeout=5000)
    sup = native_pad.start_reader()
    try:
        assert sup is not None
        page.wait_for_function("() => window.app._idmNative.status.reader === 'running'", timeout=30000)
        assert page.evaluate("() => window.app._idmNative.status.pads.length") == 0
        assert not page.is_visible('#idm-pad-help')
        proc = sup.proc
        assert proc.poll() is None
    finally:
        native_pad.stop_reader()
    assert proc.wait(10) is not None
    page.wait_for_function("() => window.app._idmNative.status.reader === 'off'", timeout=5000)
    assert not page._errors, page._errors
