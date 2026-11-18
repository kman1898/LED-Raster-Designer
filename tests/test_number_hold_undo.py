"""A held number spinner is one undo step (owner, 2026-11-18).

Holding a number field's spinner saved on every tick, and every tick was
its own undo step: thirty steps for one hold. Now a hold (the spinner held
down, an arrow key held in the field, a slider dragged) is one step, from
the value it started at to the one it ended on, like a canvas drag. A
separate click is still its own step. The shared hold lives in app-history
(_wireNumberHold) and covers every number field and slider; the Data tab's
Label Size field (#label-size, 'Change Data Flow Label Size') and the
gradient's angle slider are the ones driven here.

What else the hold must not swallow: a step it did not make (another
action's, or another page's change) stays its own step and carries none of
the hold's ticks; an undo in the middle of a hold steps over the ticks so
far and the rest is one more step; a release the page never saw ends the
hold on the next move with no button down.

The Mac app's WebKit fires `change` on every tick of a held spinner;
Chromium fires one `change` on the release. 'every-tick' replays WebKit's
order in the test browser (each trusted `input` followed by a `change`),
so these tests fail without the hold.

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
FOREIGN = 'Changes From Another Page'

# A release the page never sees: a window-capture listener added before the
# app's own, which swallows pointerup while the test asks it to.
DROP_POINTERUP_JS = """
window.__dropPointerUp = false;
window.addEventListener('pointerup', (e) => {
    if (window.__dropPointerUp) e.stopImmediatePropagation();
}, true);
"""


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def context(e2e_server, pw_browser):
    ctx = pw_browser.new_context(viewport={'width': 1500, 'height': 950})
    ctx.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}"
    )
    ctx.add_init_script(DROP_POINTERUP_JS)
    yield ctx
    ctx.close()


@pytest.fixture(scope="module")
def page(e2e_server, context):
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && Array.isArray(window.app.history)", timeout=30000)
    yield pg


RESET_JS = """async () => {
    const app = window.app, r = window.canvasRenderer;
    let project = await (await fetch('/api/project')).json();
    project.layers = []; project.groups = [];
    await fetch('/api/project', {method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(project)});
    for (const [name, x] of [['Hold1', 0], ['Hold2', 1000]]) {
        await fetch('/api/layer/add', {method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name, columns: 4, rows: 3, cabinet_width: 128,
                cabinet_height: 128, offset_x: x, offset_y: 0})});
    }
    app.project = await (await fetch('/api/project')).json();
    const live = app.project.layers.filter(l => (l.type || 'screen') === 'screen');
    live[0].dataFlowLabelSize = 30;
    live[0].gradientAngle = 0;
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


def _tab(page, mode):
    page.locator(f'[data-mode="{mode}"]').click()
    settled(page, lambda: page.evaluate("() => window.canvasRenderer.viewMode"),
            lambda v: v == mode)


def _reset(page):
    lid = page.evaluate(RESET_JS)
    _tab(page, 'data-flow')
    field = page.locator('#label-size')
    field.scroll_into_view_if_needed()
    page.evaluate("() => { const el = document.getElementById('label-size'); el.value = '30'; }")
    return lid, field


def _every_tick(page, field_id, on):
    if on:
        page.evaluate("""(id) => {
            const el = document.getElementById(id);
            el.__everyTick = (e) => { if (e.isTrusted) el.dispatchEvent(new Event('change', { bubbles: true })); };
            el.addEventListener('input', el.__everyTick);
        }""", field_id)
    else:
        page.evaluate("""(id) => {
            const el = document.getElementById(id);
            if (el.__everyTick) el.removeEventListener('input', el.__everyTick);
            el.__everyTick = null;
        }""", field_id)


def _actions(page):
    return page.evaluate("() => window.app.history.map(s => s.action)")


def _steps(page, action=ACTION):
    return page.evaluate(f"""() => window.app.history.slice(1)
        .filter(s => s.action === {action!r}).length""")


def _size(page, lid):
    return page.evaluate(f"""() => window.app.project.layers
        .find(l => l.id === {lid!r}).dataFlowLabelSize""")


def _entry_size(page, index, lid):
    return page.evaluate(f"""() => window.app.history[{index}].project.layers
        .find(l => l.id === {lid!r}).dataFlowLabelSize""")


def _up_arrow(field):
    """The spinner's up half: inside the field's right padding, just above
    the middle."""
    box = field.bounding_box()
    return box['x'] + box['width'] - 14, box['y'] + box['height'] / 2 - 4


def _hold(page, field, ms, order='every-tick', during=None):
    """Hold the spinner's up arrow for `ms`, running `during(page)` half way."""
    if order == 'every-tick':
        _every_tick(page, 'label-size', True)
    try:
        x, y = _up_arrow(field)
        page.mouse.move(x, y)
        page.mouse.down()
        page.wait_for_timeout(ms // 2)
        if during:
            during(page)
        page.wait_for_timeout(ms - ms // 2)
        page.mouse.up()
        page.wait_for_timeout(200)
    finally:
        _every_tick(page, 'label-size', False)


@pytest.mark.parametrize('order', ['every-tick', 'on-release'])
def test_holding_the_spinner_is_one_undo_step(page, order):
    lid, field = _reset(page)
    assert _size(page, lid) == 30
    _hold(page, field, 1200, order)
    settled(page, lambda: _steps(page), lambda n: n >= 1)
    end = _size(page, lid)
    assert end >= 33, f'the hold stepped only to {end}; was the spinner pressed?'
    assert _steps(page) == 1, _actions(page)
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
    assert _steps(page) == 2, _actions(page)
    page.evaluate("() => window.app.undo()")
    assert _size(page, lid) == 31
    page.evaluate("() => window.app.undo()")
    assert _size(page, lid) == 30


def test_holding_an_arrow_key_is_one_undo_step(page):
    lid, field = _reset(page)
    _every_tick(page, 'label-size', True)
    try:
        field.focus()
        page.keyboard.down('ArrowUp')
        for _ in range(5):   # the key repeating, as a held key does
            page.keyboard.down('ArrowUp')
        page.keyboard.up('ArrowUp')
        page.wait_for_timeout(200)
    finally:
        _every_tick(page, 'label-size', False)
    field.press('Enter')
    settled(page, lambda: _size(page, lid), lambda v: v == 36)
    page.wait_for_timeout(200)
    assert _steps(page) == 1, _actions(page)
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


def test_dragging_a_slider_is_one_undo_step(page):
    """The gradient's angle slider, dragged slowly: the gradient's own
    debounced step would land between moves, one per pause."""
    lid = page.evaluate(RESET_JS)
    angle_of = f"() => window.app.project.layers.find(l => l.id === {lid!r}).gradientAngle"
    _tab(page, 'pixel-map')
    enabled = page.locator('#gradient-enabled')
    enabled.scroll_into_view_if_needed()
    enabled.check()
    settled(page, lambda: _steps(page, 'Update Gradient'), lambda n: n >= 1, 3000)
    before = _steps(page, 'Update Gradient')
    slider = page.locator('#gradient-angle')
    slider.scroll_into_view_if_needed()
    _every_tick(page, 'gradient-angle', True)
    try:
        box = slider.bounding_box()
        y = box['y'] + box['height'] / 2
        x = box['x'] + 4
        page.mouse.move(x, y)
        page.mouse.down()
        for i in range(1, 5):
            page.mouse.move(x + i * box['width'] / 8, y, steps=3)
            page.wait_for_timeout(500)   # past the 400 ms debounce
        page.mouse.up()
        page.wait_for_timeout(700)
    finally:
        _every_tick(page, 'gradient-angle', False)
    angle = page.evaluate(angle_of)
    assert angle > 45, angle
    assert _steps(page, 'Update Gradient') - before == 1, _actions(page)
    page.evaluate("() => window.app.undo()")
    assert page.evaluate(angle_of) == 0


def test_another_step_during_a_hold_stays_its_own(page):
    """A step the hold did not make (here a rename of the project, the way a
    late step of an earlier action lands) is its own step, and carries none
    of the hold's ticks."""
    lid, field = _reset(page)

    def rename(pg):
        pg.evaluate("() => { window.app.project.name = 'Hold Renamed'; window.app.saveState('Rename Project'); }")

    _hold(page, field, 1200, during=rename)
    settled(page, lambda: _steps(page), lambda n: n >= 2)
    actions = _actions(page)
    assert actions.count('Rename Project') == 1, actions
    r = actions.index('Rename Project')
    assert actions[r - 1] == ACTION and actions[-1] == ACTION, actions
    # the rename's entry holds the label where the hold had taken it, no further
    assert _entry_size(page, r, lid) == _entry_size(page, r - 1, lid)
    end = _size(page, lid)
    mid = _entry_size(page, r, lid)
    assert 30 < mid < end, (mid, end)
    page.evaluate("() => window.app.undo()")
    assert _size(page, lid) == mid
    page.evaluate("() => window.app.undo()")
    assert page.evaluate("() => window.app.project.name") != 'Hold Renamed'
    assert _size(page, lid) == mid
    page.evaluate("() => window.app.undo()")
    assert _size(page, lid) == 30


def test_another_pages_change_during_a_hold_carries_none_of_its_ticks(page, context, e2e_server):
    lid, field = _reset(page)
    other = context.new_page()
    try:
        other.goto(e2e_server, wait_until='domcontentloaded')
        other.wait_for_function(
            "() => window.app && window.app.project && (window.app.project.layers || []).some(l => l.name === 'Hold2')",
            timeout=30000)
        other.wait_for_timeout(500)

        def rename_elsewhere(pg):
            other.evaluate("""() => {
                const l = window.app.project.layers.find(x => x.name === 'Hold2');
                l.name = 'Renamed Elsewhere';
                window.app.updateLayers([l], true, 'Rename Screen');
            }""")
            settled(page, lambda: _actions(page), lambda a: FOREIGN in a, 3000)

        _hold(page, field, 1400, during=rename_elsewhere)
    finally:
        other.close()
    actions = _actions(page)
    assert actions.count(FOREIGN) == 1, actions
    f = actions.index(FOREIGN)
    assert actions[f - 1] == ACTION and actions[-1] == ACTION, actions
    mid = _entry_size(page, f - 1, lid)
    assert _entry_size(page, f, lid) == mid, 'the other page\'s step took in this page\'s ticks'
    end = _size(page, lid)
    assert 30 < mid < end, (mid, end)
    name = "() => window.app.project.layers.find(l => l.offset_x === 1000).name"
    page.evaluate("() => window.app.undo()")
    assert _size(page, lid) == mid
    assert page.evaluate(name) == 'Renamed Elsewhere'
    page.evaluate("() => window.app.undo()")          # the other page's change
    assert page.evaluate(name) == 'Hold2'
    assert _size(page, lid) == mid
    page.evaluate("() => window.app.undo()")
    assert _size(page, lid) == 30


def test_undo_during_a_hold_leaves_one_step_after_it(page):
    lid, field = _reset(page)

    def undo(pg):
        pg.evaluate("() => window.app.undo()")

    _hold(page, field, 1200, during=undo)
    settled(page, lambda: _steps(page), lambda n: n >= 1)
    actions = _actions(page)
    assert actions == ['Hold Reset', ACTION], actions
    assert page.evaluate("() => window.app.historyIndex") == 1
    end = _size(page, lid)
    assert end > 30
    page.evaluate("() => window.app.undo()")
    assert _size(page, lid) == 30


def test_a_release_the_page_never_saw_ends_the_hold(page):
    """Let go outside the window: no pointerup arrives. The next move with
    no button down ends the hold, and the next typed value is its own step."""
    lid, field = _reset(page)
    x, y = _up_arrow(field)
    page.mouse.move(x, y)
    page.mouse.down()
    page.wait_for_timeout(600)
    page.evaluate("() => { window.__dropPointerUp = true; }")
    try:
        page.mouse.up()
    finally:
        page.evaluate("() => { window.__dropPointerUp = false; }")
    page.mouse.move(x - 40, y + 30)
    page.wait_for_timeout(200)
    assert _steps(page) == 1, _actions(page)
    held_to = _size(page, lid)
    assert held_to > 31
    field.click(click_count=3)
    page.keyboard.type('70')
    page.keyboard.press('Enter')
    settled(page, lambda: _size(page, lid), lambda v: v == 70)
    page.wait_for_timeout(200)
    assert _steps(page) == 2, _actions(page)
    page.evaluate("() => window.app.undo()")
    assert _size(page, lid) == held_to
    page.evaluate("() => window.app.undo()")
    assert _size(page, lid) == 30
