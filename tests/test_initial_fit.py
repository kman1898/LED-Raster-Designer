"""The fit a launch makes never lands on a view already set (1.6.0).

The app fits the view a moment after its first load reports done. A view
set in that gap was fitted over: CI, 2026-11-04, a browser module set its
zoom right after the load, the fit landed after it, and six drags aimed at
the far side of the walls missed the canvas.

The gap is a timer, so each test stretches it to hold the order still.

The same fit landed on input from BEFORE the load reported done (1.6.0 QA,
beta.6: reload with a show open, wheel on the canvas as soon as it appears,
10 of 12 went back to the fit), because the view it compared with was read
after the input. Owner, 2026-11-05: zooming or panning right as the app opens
stays put. The fit now compares with the view the renderer was built with.
Those tests hold the page's first GET /api/project until the input is in, so
the order is the same on any machine.

Run locally (each session takes its own free port):
    python -m pytest tests/test_initial_fit.py -v --browser chromium
"""

import pytest

from conftest import open_app, settled

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

STRETCH_THE_FIT_TIMER = """(() => {
    const later = window.setTimeout;
    window.setTimeout = (fn, ms, ...rest) => later(fn, ms === 100 ? 800 : ms, ...rest);
    try { localStorage.setItem('lrd_quickstart_first_run_done', '1'); } catch (e) {}
})();"""

# The page's reads of the project wait until the test lets them go.
HOLD_THE_LOAD = """(() => {
    const send = window.fetch;
    let open;
    const held = new Promise((resolve) => { open = resolve; });
    window.__releaseProject = open;
    window.fetch = function (url, opts) {
        const read = !(opts && opts.method && opts.method !== 'GET');
        if (read && String(url).split('?')[0].endsWith('/api/project')) {
            return held.then(() => send.call(window, url, opts));
        }
        return send.apply(this, arguments);
    };
})();"""

VIEW_JS = """() => {
    const r = window.canvasRenderer;
    return {zoom: r.zoom, panX: r.panX, panY: r.panY};
}"""


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture
def pg(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(STRETCH_THE_FIT_TIMER)
    page = context.new_page()
    open_app(page, e2e_server)
    yield page
    context.close()


def test_a_view_set_before_the_fit_stays(pg):
    pg.evaluate("""() => {
        const r = window.canvasRenderer;
        r.zoom = 0.22; r.panX = 60; r.panY = 60; r.render();
    }""")
    pg.wait_for_timeout(1500)
    assert pg.evaluate(VIEW_JS) == {'zoom': 0.22, 'panX': 60, 'panY': 60}


def test_a_launch_left_alone_still_fits(pg):
    before = pg.evaluate(VIEW_JS)
    pg.wait_for_timeout(1500)
    fitted = pg.evaluate(VIEW_JS)
    assert fitted != before, 'the launch never fitted the view'
    again = pg.evaluate("""() => {
        const r = window.canvasRenderer;
        r.fitToView();
        return {zoom: r.zoom, panX: r.panX, panY: r.panY};
    }""")
    assert fitted == again


def test_a_real_wheel_after_the_load_and_before_the_fit_stays(pg):
    box = pg.locator('#main-canvas').bounding_box()
    pg.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
    pg.mouse.wheel(0, -100)
    moved = settled(pg, lambda: pg.evaluate(VIEW_JS), lambda v: v['zoom'] != 1)
    assert moved['zoom'] != 1
    pg.wait_for_timeout(1500)
    assert pg.evaluate(VIEW_JS) == moved


# ── input before the load reports done ────────────────────────────────────

@pytest.fixture
def held(e2e_server, pw_browser):
    """A page up to the canvas, its project still on the way. Plays the
    load out through release(), for a test that has made its gesture."""
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(STRETCH_THE_FIT_TIMER + HOLD_THE_LOAD)
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(e2e_server, wait_until='domcontentloaded')
    page.wait_for_function("() => !!window.canvasRenderer")
    assert page.evaluate("() => window.app._initialLoadComplete") is not True

    def release():
        page.evaluate("() => window.__releaseProject()")
        page.wait_for_function("() => window.app._initialLoadComplete === true", timeout=20000)
        page.wait_for_timeout(1500)     # the fit's stretched timer, and more

    yield page, release, errors
    context.close()


def _over_the_canvas(pg):
    box = pg.locator('#main-canvas').bounding_box()
    x, y = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2
    pg.mouse.move(x, y)
    return x, y


def _wheel_zoom(pg):
    _over_the_canvas(pg)
    pg.mouse.wheel(0, -100)


def _wheel_pan(pg):
    _over_the_canvas(pg)
    pg.mouse.wheel(60, 0)


def _middle_drag_pan(pg):
    x, y = _over_the_canvas(pg)
    pg.mouse.down(button='middle')
    pg.mouse.move(x + 40, y + 30, steps=4)
    pg.mouse.up(button='middle')


def _zoom_button(pg):
    pg.locator('#btn-zoom-in').click()


@pytest.mark.parametrize('gesture', [_wheel_zoom, _wheel_pan, _middle_drag_pan, _zoom_button],
                         ids=['wheel-zoom', 'wheel-pan', 'middle-drag', 'zoom-button'])
def test_input_before_the_load_is_done_stays(held, gesture):
    pg, release, errors = held
    before = pg.evaluate(VIEW_JS)
    gesture(pg)
    moved = settled(pg, lambda: pg.evaluate(VIEW_JS), lambda v: v != before)
    assert moved != before, 'the gesture never reached the view'
    release()
    assert pg.evaluate(VIEW_JS) == moved
    assert errors == [], errors


def test_the_view_kept_is_a_working_view(held):
    pg, release, errors = held
    _wheel_zoom(pg)
    moved = settled(pg, lambda: pg.evaluate(VIEW_JS), lambda v: v['zoom'] != 1)
    release()
    kept = pg.evaluate(VIEW_JS)
    assert kept == moved
    # the next wheel goes on from it
    pg.mouse.wheel(0, -100)
    on = settled(pg, lambda: pg.evaluate(VIEW_JS), lambda v: v != kept)
    assert on['zoom'] > kept['zoom']
    # Fit still fits
    pg.locator('#btn-fit').click()
    fitted = pg.evaluate(VIEW_JS)
    assert fitted == pg.evaluate("""() => {
        const r = window.canvasRenderer;
        r.fitToView();
        return {zoom: r.zoom, panX: r.panX, panY: r.panY};
    }""")
    assert fitted != on
    assert errors == [], errors


def test_a_load_left_alone_still_fits_however_late_it_lands(held):
    pg, release, errors = held
    before = pg.evaluate(VIEW_JS)
    pg.wait_for_timeout(500)
    assert pg.evaluate(VIEW_JS) == before
    release()
    fitted = pg.evaluate(VIEW_JS)
    assert fitted != before, 'the launch never fitted the view'
    assert fitted == pg.evaluate("""() => {
        const r = window.canvasRenderer;
        r.fitToView();
        return {zoom: r.zoom, panX: r.panX, panY: r.panY};
    }""")
    assert errors == [], errors


def test_a_reload_left_alone_fits_after_a_view_that_stayed(held):
    """What a view was kept for lasts until the page goes: a reload starts
    fresh, as the 2026-11-04 ruling has it."""
    pg, release, errors = held
    _wheel_zoom(pg)
    settled(pg, lambda: pg.evaluate(VIEW_JS), lambda v: v['zoom'] != 1)
    release()
    pg.reload(wait_until='domcontentloaded')
    pg.wait_for_function("() => !!window.canvasRenderer")
    pg.evaluate("() => window.__releaseProject()")
    pg.wait_for_function("() => window.app._initialLoadComplete === true", timeout=20000)
    pg.wait_for_timeout(1500)
    assert pg.evaluate(VIEW_JS) == pg.evaluate("""() => {
        const r = window.canvasRenderer;
        r.fitToView();
        return {zoom: r.zoom, panX: r.panX, panY: r.panY};
    }""")
    assert errors == [], errors
