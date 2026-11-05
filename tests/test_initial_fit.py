"""The fit a launch makes never lands on a view already set (1.6.0).

The app fits the view a moment after its first load reports done. A view
set in that gap was fitted over: CI, 2026-11-04, a browser module set its
zoom right after the load, the fit landed after it, and six drags aimed at
the far side of the walls missed the canvas.

The gap is a timer, so each test stretches it to hold the order still.

Run locally (each session takes its own free port):
    python -m pytest tests/test_initial_fit.py -v --browser chromium
"""

import pytest

from conftest import open_app

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

STRETCH_THE_FIT_TIMER = """(() => {
    const later = window.setTimeout;
    window.setTimeout = (fn, ms, ...rest) => later(fn, ms === 100 ? 800 : ms, ...rest);
    try { localStorage.setItem('lrd_quickstart_first_run_done', '1'); } catch (e) {}
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
