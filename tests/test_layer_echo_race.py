"""v0.11.0 - a slow PUT put back the value the user had just replaced.

Second half of the "things revert" report. updateLayers() sends the layer, then
re-stamps a set of fields onto the server's echo because the echo does not
carry them the way the client holds them. That re-stamp used to snapshot the
VALUES at request time:

    const preservedProps = { ..., gradientStops: layer.gradientStops, ... };
    fetch(...).then(updated => { updated[k] = preservedProps[k]; ... });

Every gradient control assigns a brand-new stops array (_applyGradient maps a
fresh object per stop), so the snapshot is a different array from the one a
later edit installs. Edit while a PUT is still in flight and its response
re-stamps the OLD array over the new one: the stop the user just dragged moves
back on its own, and the debounced undo snapshot 400ms later records the
reverted value as though it were chosen.

The fix reads the live layer at RESPONSE time, so the re-stamp can only ever
carry the newest value.

The delay here is applied to the client's HANDLING of the response, which is
where the defect lives - the request itself goes out untouched.

Run locally:
    python -m pytest tests/test_layer_echo_race.py -v --browser chromium
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

STOPS_FIRST = [{'pos': 0, 'color': '#111111'}, {'pos': 1, 'color': '#222222'}]
STOPS_SECOND = [{'pos': 0, 'color': '#aabbcc'}, {'pos': 1, 'color': '#ddeeff'}]


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


# Hold the RESPONSE HANDLING of layer PUTs, not the requests. Held promises
# resolve with the real Response, body unread, so the caller's .json() works.
INSTALL_HOLD_JS = """() => {
    window.__held = [];
    window.__hold = true;
    if (!window.__origFetch) {
        window.__origFetch = window.fetch.bind(window);
        window.fetch = (input, init) => {
            const url = typeof input === 'string'
                ? input : (input && input.url) || '';
            const p = window.__origFetch(input, init);
            const isLayerPut = window.__hold
                && /\\/api\\/layer\\//.test(url)
                && init && init.method === 'PUT';
            if (!isLayerPut) return p;
            return new Promise(resolve => {
                window.__held.push(() => p.then(resolve));
            });
        };
    }
}"""

UNINSTALL_HOLD_JS = """() => {
    if (window.__origFetch) { window.fetch = window.__origFetch; }
    delete window.__origFetch;
    window.__hold = false;
    (window.__held || []).forEach(f => f());
    window.__held = [];
}"""


def _stops(page):
    return page.evaluate("""() => {
        const l = window.app.currentLayer;
        return (l.gradientStops || []).map(s => ({pos: s.pos, color: s.color}));
    }""")


def test_a_reply_to_an_older_edit_cannot_undo_a_newer_one(page):
    page.evaluate(INSTALL_HOLD_JS)
    try:
        # Edit 1 - its PUT goes out, its reply is held.
        page.evaluate("(stops) => window.app._applyGradient("
                      "{gradientEnabled: true, gradientStops: stops}, true)",
                      STOPS_FIRST)
        page.wait_for_timeout(300)
        assert page.evaluate("() => window.__held.length") == 1, (
            'nothing was held - the test is not exercising the race')

        # Edit 2, while edit 1 is still unanswered. This one completes.
        page.evaluate("() => { window.__hold = false; }")
        page.evaluate("(stops) => window.app._applyGradient("
                      "{gradientStops: stops}, true)", STOPS_SECOND)
        page.wait_for_timeout(600)
        assert _stops(page) == STOPS_SECOND, 'edit 2 did not land at all'

        # Now let edit 1's reply arrive, last.
        page.evaluate("() => { window.__held.forEach(f => f());"
                      " window.__held = []; }")
        page.wait_for_timeout(600)

        assert _stops(page) == STOPS_SECOND, (
            "the reply to edit 1 put edit 1's stops back over edit 2 - this is "
            'the drag snapping back under the user')
    finally:
        page.evaluate(UNINSTALL_HOLD_JS)


def test_the_late_reply_does_not_poison_the_undo_snapshot(page):
    """The visible symptom was the snap-back; the lasting damage was that the
    debounced snapshot recorded the reverted value, so Ctrl+Z stepped through
    states the user never chose."""
    page.evaluate(INSTALL_HOLD_JS)
    try:
        page.evaluate("(stops) => window.app._applyGradient("
                      "{gradientEnabled: true, gradientStops: stops}, true)",
                      STOPS_FIRST)
        page.wait_for_timeout(300)
        page.evaluate("() => { window.__hold = false; }")
        page.evaluate("(stops) => window.app._applyGradient("
                      "{gradientStops: stops}, true)", STOPS_SECOND)
        page.wait_for_timeout(200)
        # Reply lands INSIDE the 400ms debounce window, so whatever it leaves
        # behind is what the undo step captures.
        page.evaluate("() => { window.__held.forEach(f => f());"
                      " window.__held = []; }")
        page.wait_for_timeout(900)

        snapshot = page.evaluate("""() => {
            const h = window.app.history[window.app.historyIndex];
            const id = window.app.currentLayer.id;
            const l = h.project.layers.find(x => x.id === id);
            return {
                action: h.action,
                stops: (l.gradientStops || [])
                    .map(s => ({pos: s.pos, color: s.color})),
            };
        }""")
        assert snapshot['stops'] == STOPS_SECOND, (
            f"undo step '{snapshot['action']}' recorded "
            f"{snapshot['stops']} - a state the user never chose")
    finally:
        page.evaluate(UNINSTALL_HOLD_JS)
