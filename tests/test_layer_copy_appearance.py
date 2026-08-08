"""v0.11.0 - a copied screen arrived without its gradient.

Found while auditing the reload fix. Duplicate and Paste each build their own
payload by hand for POST /api/layer/add, and both were missing the appearance
block - so was that route's own allow-list. The two failed differently, which
is why neither was obvious:

  Duplicate  the browser applied the gradient to the response afterwards
             (clientProps), so the copy LOOKED right and the server held a
             screen with no gradient. Gone on the next reload.
  Paste      pasteClientProps is eight colours and nothing else, so nothing
             papered over it. The pasted screen came out plain immediately.

Both are the same defect and both are checked here against the SERVER's copy,
because that is what a reload reads. Asserting the browser's copy would have
passed for Duplicate while the bug was live.

Run locally:
    python -m pytest tests/test_layer_copy_appearance.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

STOPS = [{'pos': 0, 'color': '#ff0040'},
         {'pos': 0.5, 'color': '#ffee00'},
         {'pos': 1, 'color': '#0099ff'}]
PALETTE = ['#123456', '#654321']


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


# Dress the current screen and push it to the server, then hand back the ids
# that existed at that moment so the copy can be identified by difference.
DRESS_JS = """([stops, palette]) => {
    const app = window.app;
    const l = app.currentLayer;
    l.gradientEnabled = true;
    l.gradientType = 'radial';
    l.gradientScope = 'panel';
    l.gradientAngle = 90;
    l.gradientOpacity = 1;
    l.gradientBlend = 'color';
    l.gradientStops = stops.map(s => ({pos: s.pos, color: s.color}));
    l.panelColorMode = 'rows';
    l.panelColors = palette.slice();
    l.transparentFill = true;
    l.screenNameOffsetXPixelMap = 33;
    l.screenNameOffsetYShowLook = -12;
    app.updateLayers([l]);
    return {sourceId: l.id, before: app.project.layers.map(x => x.id)};
}"""

# Read the SERVER's copy - a reload reads this, not the browser's.
SERVER_COPY_JS = """(before) => fetch('/api/project')
    .then(r => r.json())
    .then(p => {
        const fresh = p.layers.filter(l => !before.includes(l.id));
        if (fresh.length !== 1) return {error: `${fresh.length} new layers`};
        const l = fresh[0];
        return {
            gradientEnabled: l.gradientEnabled,
            gradientType: l.gradientType,
            gradientScope: l.gradientScope,
            gradientBlend: l.gradientBlend,
            gradientStops: (l.gradientStops || [])
                .map(s => ({pos: s.pos, color: s.color})),
            panelColorMode: l.panelColorMode,
            panelColors: l.panelColors,
            transparentFill: l.transparentFill,
            screenNameOffsetXPixelMap: l.screenNameOffsetXPixelMap,
            screenNameOffsetYShowLook: l.screenNameOffsetYShowLook,
        };
    })"""


def _assert_dressed(copy, how):
    assert 'error' not in copy, f'{how}: {copy["error"]}'
    assert copy['gradientEnabled'] is True, f'{how} lost gradientEnabled'
    assert copy['gradientStops'] == STOPS, (
        f'{how} reached the server without its gradient stops: '
        f'{copy["gradientStops"]} - the copy loses them on reload')
    assert copy['gradientType'] == 'radial', f'{how} lost gradientType'
    assert copy['gradientScope'] == 'panel', f'{how} lost gradientScope'
    assert copy['gradientBlend'] == 'color', f'{how} lost gradientBlend'
    assert copy['panelColorMode'] == 'rows', f'{how} lost panelColorMode'
    assert copy['panelColors'] == PALETTE, f'{how} lost panelColors'
    assert copy['transparentFill'] is True, f'{how} lost transparentFill'
    assert copy['screenNameOffsetXPixelMap'] == 33, f'{how} lost Pixel Map offset'
    assert copy['screenNameOffsetYShowLook'] == -12, f'{how} lost Show Look offset'


def test_duplicated_screen_reaches_the_server_dressed(page):
    state = page.evaluate(DRESS_JS, [STOPS, PALETTE])
    page.wait_for_timeout(700)
    page.evaluate("""(id) => {
        const l = window.app.project.layers.find(x => x.id === id);
        window.app.duplicateLayer(l);
    }""", state['sourceId'])
    page.wait_for_timeout(1200)

    _assert_dressed(page.evaluate(SERVER_COPY_JS, state['before']), 'Duplicate')


def test_pasted_screen_reaches_the_server_dressed(page):
    state = page.evaluate(DRESS_JS, [STOPS, PALETTE])
    page.wait_for_timeout(700)
    page.evaluate("""(id) => {
        const app = window.app;
        app.currentLayer = app.project.layers.find(x => x.id === id);
        app.copyLayer();
        app.pasteLayer();
    }""", state['sourceId'])
    page.wait_for_timeout(1200)

    _assert_dressed(page.evaluate(SERVER_COPY_JS, state['before']), 'Paste')


def test_a_copy_does_not_share_its_gradient_array_with_the_original(page):
    """duplicateData deep-copies the stops, but clientProps used to hand the
    ORIGINAL's array straight to the copy afterwards, undoing that. Nothing
    mutates the array in place today, so this held by luck rather than by
    design - one in-place edit away from two screens sharing one gradient."""
    state = page.evaluate(DRESS_JS, [STOPS, PALETTE])
    page.wait_for_timeout(700)
    page.evaluate("""(id) => {
        const l = window.app.project.layers.find(x => x.id === id);
        window.app.duplicateLayer(l);
    }""", state['sourceId'])
    page.wait_for_timeout(1200)

    shared = page.evaluate("""([before, sourceId]) => {
        const app = window.app;
        const src = app.project.layers.find(l => l.id === sourceId);
        const copy = app.project.layers.find(l => !before.includes(l.id));
        if (!src || !copy) return {error: 'layers not found'};
        return {
            stops: src.gradientStops === copy.gradientStops,
            colors: src.panelColors === copy.panelColors,
        };
    }""", [state['before'], state['sourceId']])

    assert 'error' not in shared, shared
    assert shared['stops'] is False, (
        'the copy and the original share one gradientStops array')
    assert shared['colors'] is False, (
        'the copy and the original share one panelColors array')
