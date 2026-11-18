"""A held number spinner is one undo step (owner, 2026-11-18).

Holding a number field's spinner saved on every tick, and every tick was
its own undo step: thirty steps for one hold. Now a hold (the spinner held
down, or an arrow key held in the field) is one step, from the value it
started at to the one it ended on, like a canvas drag. A separate click is
still its own step. The shared hold lives in app-history (_wireNumberHold)
and covers every number field and slider; the Data tab's Label Size field
(#label-size, 'Change Data Flow Label Size') is the one driven here.

Run locally:
    python -m pytest tests/test_number_hold_undo.py -n 4 --dist loadfile --browser chromium
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from conftest import settled  # noqa: E402

ACTION = 'Change Data Flow Label Size'


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1500, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && Array.isArray(window.app.history)", timeout=30000)
    yield pg
    context.close()


RESET_JS = """async () => {
    const app = window.app, r = window.canvasRenderer;
    let project = await (await fetch('/api/project')).json();
    project.layers = []; project.groups = [];
    await fetch('/api/project', {method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(project)});
    await fetch('/api/layer/add', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: 'Hold1', columns: 4, rows: 3, cabinet_width: 128,
            cabinet_height: 128, offset_x: 0, offset_y: 0})});
    app.project = await (await fetch('/api/project')).json();
    const live = app.project.layers.filter(l => (l.type || 'screen') === 'screen');
    live[0].dataFlowLabelSize = 30;
    app.currentLayer = live[0];
    app.selectedLayerIds = new Set([live[0].id]);
    app.lastSelectedLayerId = live[0].id;
    app._flushPendingSaveState();
    app.resetHistory('Hold Reset');
    app.renderLayers();
    app.updateLayerProperties ? app.updateLayerProperties() : null;
    r.render();
    return live[0].id;
}"""


def _reset(page):
    lid = page.evaluate(RESET_JS)
    page.locator('[data-mode="data-flow"]').click()
    settled(page, lambda: page.evaluate("() => window.canvasRenderer.viewMode"),
            lambda v: v == 'data-flow')
    field = page.locator('#label-size')
    field.scroll_into_view_if_needed()
    page.evaluate("() => { const el = document.getElementById('label-size'); el.value = '30'; }")
    return lid, field


def _steps(page):
    return page.evaluate(f"""() => window.app.history.slice(1)
        .filter(s => s.action === {ACTION!r}).length""")


def _size(page, lid):
    return page.evaluate(f"""() => window.app.project.layers
        .find(l => l.id === {lid!r}).dataFlowLabelSize""")


def _up_arrow(field):
    """The spinner's up half: inside the field's right padding, just above
    the middle."""
    box = field.bounding_box()
    return box['x'] + box['width'] - 14, box['y'] + box['height'] / 2 - 4


# The Mac app's WebKit fires `change` on every tick of a held spinner
# (thirty saves, thirty steps, before the fix); Chromium fires one `change`
# on the release. 'every-tick' replays WebKit's order in the test browser:
# each trusted tick's `input` is followed by a `change`.
EVERY_TICK_JS = """() => {
    const el = document.getElementById('label-size');
    el.__everyTick = (e) => { if (e.isTrusted) el.dispatchEvent(new Event('change', { bubbles: true })); };
    el.addEventListener('input', el.__everyTick);
}"""
EVERY_TICK_OFF_JS = """() => {
    const el = document.getElementById('label-size');
    if (el.__everyTick) el.removeEventListener('input', el.__everyTick);
    el.__everyTick = null;
}"""


@pytest.mark.parametrize('order', ['every-tick', 'on-release'])
def test_holding_the_spinner_is_one_undo_step(page, order):
    lid, field = _reset(page)
    assert _size(page, lid) == 30
    if order == 'every-tick':
        page.evaluate(EVERY_TICK_JS)
    try:
        x, y = _up_arrow(field)
        page.mouse.move(x, y)
        page.mouse.down()
        page.wait_for_timeout(1200)   # the spinner repeats while held
        page.mouse.up()
        settled(page, lambda: _steps(page), lambda n: n >= 1)
        page.wait_for_timeout(200)
    finally:
        page.evaluate(EVERY_TICK_OFF_JS)
    end = _size(page, lid)
    assert end >= 33, f'the hold stepped only to {end}; was the spinner pressed?'
    assert _steps(page) == 1, page.evaluate("() => window.app.history.map(s => s.action)")
    assert int(field.input_value()) == end
    page.evaluate("() => window.app.undo()")
    assert _size(page, lid) == 30
    page.evaluate("() => window.app.redo()")
    assert _size(page, lid) == end


def test_two_separate_clicks_are_two_steps(page):
    lid, field = _reset(page)
    x, y = _up_arrow(field)
    for _ in range(2):
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.up()
        page.wait_for_timeout(250)
    settled(page, lambda: _steps(page), lambda n: n >= 2)
    assert _size(page, lid) == 32
    assert _steps(page) == 2, page.evaluate("() => window.app.history.map(s => s.action)")
    page.evaluate("() => window.app.undo()")
    assert _size(page, lid) == 31
    page.evaluate("() => window.app.undo()")
    assert _size(page, lid) == 30


def test_holding_an_arrow_key_is_one_undo_step(page):
    lid, field = _reset(page)
    field.focus()
    page.keyboard.down('ArrowUp')
    for _ in range(5):   # the key repeating, as a held key does
        page.keyboard.down('ArrowUp')
    page.keyboard.up('ArrowUp')
    field.press('Enter')
    settled(page, lambda: _size(page, lid), lambda v: v == 36)
    page.wait_for_timeout(200)
    assert _steps(page) == 1, page.evaluate("() => window.app.history.map(s => s.action)")
    page.evaluate("() => window.app.undo()")
    assert _size(page, lid) == 30


def test_typing_a_value_and_enter_is_one_step(page):
    lid, field = _reset(page)
    field.click(click_count=3)
    page.keyboard.type('44')
    page.keyboard.press('Enter')
    settled(page, lambda: _size(page, lid), lambda v: v == 44)
    page.wait_for_timeout(200)
    assert _steps(page) == 1
    page.evaluate("() => window.app.undo()")
    assert _size(page, lid) == 30
