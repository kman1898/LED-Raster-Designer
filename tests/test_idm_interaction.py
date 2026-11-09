"""How the IDM Locator tab handles in the hand (app-idm-locator.js,
canvas-input.js, canvas-idm.js, app-output-display.js).

What this file pins:

* Space held with a drag pans the view exactly like every other tab and
  marks nothing; a Space TAP (let go at once, no press of the mouse in it)
  marks the highlighted module on its release, one undo step; a long hold
  with no drag does nothing. Middle-button drag pans and the wheel zooms
  without marking.
* The designer's mouse shows on the wall: an arrow at the same spot on
  every IDM Locator output of the canvas the mouse is over, gone when the
  mouse leaves the view or the Show mouse on wall switch is off, drawn over
  the output's last frame (never a render).
* The marking gestures: Esc in the middle of a drag puts the modules back
  and makes no edit; a right-click on a marked module clears it (one undo
  step) and anywhere else opens the menu; a quick drag marks every module
  it crossed; the cursor says mark or clear; no gesture moves a screen.
* Output to Display feeds several displays at once: two outputs with
  different canvases and views both follow edits, closing one leaves the
  other, the dialog offers another output and names the display each is
  on, and a browser that cannot place windows says to drag them.

Run locally:
    python -m pytest tests/test_idm_interaction.py -v -p no:cacheprovider
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from conftest import settled  # noqa: E402
from test_idm_field_highlight import (  # noqa: E402
    _new_page, reset_project, set_layout, served_idm, marks_of, hl, point,
    open_output, pixel, wait_pixel,
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


def pan(pg):
    return pg.evaluate("() => [window.canvasRenderer.panX, window.canvasRenderer.panY]")


def history_index(pg):
    return pg.evaluate("() => window.app.historyIndex")


def offsets(pg):
    return pg.evaluate("() => window.app.project.layers.map(l => [l.name, l.offset_x, l.offset_y])")


def client_of(pg, wx, wy):
    """The client point of a workspace point."""
    return pg.evaluate("""([wx, wy]) => {
        const r = window.canvasRenderer, rect = r.canvas.getBoundingClientRect();
        return {x: rect.left + r.panX + wx * r.zoom, y: rect.top + r.panY + wy * r.zoom};
    }""", [wx, wy])


def pointer(pg):
    return pg.evaluate("() => { const p = window.app._idmS.pointer; return p ? {...p} : null; }")


# ── Space, the middle button and the wheel ────────────────────────────────

def test_space_and_drag_pans_and_marks_nothing(page):
    reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    a = point(page, 'IdmA', 0, 0, 0, 0)
    page.mouse.move(a['x'], a['y'])
    settled(page, lambda: hl(page), lambda v: v == ['IdmA', '0,0,0,0'])
    before_pan, before_hist, before_offsets = pan(page), history_index(page), offsets(page)
    page.keyboard.down('Space')
    assert page.evaluate("() => window.canvasRenderer.spacePressed") is True
    assert page.evaluate("() => window.canvasRenderer.canvas.style.cursor") == 'grab'
    page.mouse.down()
    page.mouse.move(a['x'] + 60, a['y'] + 40, steps=6)
    page.mouse.move(a['x'] + 120, a['y'] + 80, steps=6)
    page.mouse.up()
    page.keyboard.up('Space')
    after = pan(page)
    assert abs(after[0] - before_pan[0] - 120) < 1 and abs(after[1] - before_pan[1] - 80) < 1, (before_pan, after)
    page.wait_for_timeout(300)
    assert marks_of(page, 'IdmA') == {}
    assert history_index(page) == before_hist
    assert offsets(page) == before_offsets
    # pan, then mark: the next click marks as always
    b = point(page, 'IdmA', 1, 0, 1, 1)
    page.mouse.click(b['x'], b['y'])
    got = settled(page, lambda: served_idm(page, 'IdmA'), lambda v: v and '1,0,1,1' in v['marks'])
    assert list(got['marks']) == ['1,0,1,1'], got
    assert history_index(page) == before_hist + 1
    assert not page._errors, page._errors


def test_a_space_tap_marks_on_release_and_a_long_hold_does_not(page):
    reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    a = point(page, 'IdmA', 1, 1, 0, 1)
    page.mouse.move(a['x'], a['y'])
    settled(page, lambda: hl(page), lambda v: v == ['IdmA', '1,1,0,1'])
    h0 = history_index(page)
    page.keyboard.down('Space')
    assert marks_of(page, 'IdmA') == {}          # nothing on the press
    page.keyboard.up('Space')
    got = settled(page, lambda: served_idm(page, 'IdmA'), lambda v: v and '1,1,0,1' in v['marks'])
    assert '1,1,0,1' in got['marks'], got
    assert history_index(page) == h0 + 1
    # mark, then undo: back to no marks, the highlight stays
    page.keyboard.press('Control+z')
    settled(page, lambda: marks_of(page, 'IdmA'), lambda v: v == {})
    assert marks_of(page, 'IdmA') == {}
    assert hl(page) == ['IdmA', '1,1,0,1']
    # a long hold with no drag: nothing
    h1 = history_index(page)
    page.keyboard.down('Space')
    page.wait_for_timeout(800)
    page.keyboard.up('Space')
    page.wait_for_timeout(300)
    assert marks_of(page, 'IdmA') == {}
    assert history_index(page) == h1
    # a mouse move while Space is down keeps the highlight where it was:
    # the tap marks the module that was highlighted
    page.keyboard.down('Space')
    c = point(page, 'IdmA', 0, 0, 0, 0)
    page.mouse.move(c['x'], c['y'])
    assert hl(page) == ['IdmA', '1,1,0,1']
    page.keyboard.up('Space')
    got = settled(page, lambda: marks_of(page, 'IdmA'), lambda v: '1,1,0,1' in v)
    assert list(got) == ['1,1,0,1'], got
    # switch tabs and back: Space still pans and taps still mark
    page.click('.view-tab[data-mode="pixel-map"]')
    page.click('.view-tab[data-mode="idm"]')
    page.wait_for_function("() => window.canvasRenderer.viewMode === 'idm'")
    page.mouse.move(c['x'] + 2, c['y'] + 2)
    settled(page, lambda: hl(page), lambda v: v == ['IdmA', '0,0,0,0'])
    p0 = pan(page)
    page.keyboard.down('Space')
    page.mouse.down()
    page.mouse.move(c['x'] - 40, c['y'] + 30, steps=5)
    page.mouse.up()
    page.keyboard.up('Space')
    assert pan(page) != p0
    page.wait_for_timeout(200)
    assert '0,0,0,0' not in marks_of(page, 'IdmA')
    page.keyboard.press('Space')
    got = settled(page, lambda: marks_of(page, 'IdmA'), lambda v: '0,0,0,0' in v)
    assert '0,0,0,0' in got, got
    assert not page._errors, page._errors


def test_middle_drag_pans_and_the_wheel_zooms_without_marking(page):
    reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    a = point(page, 'IdmA', 0, 0, 1, 0)
    page.mouse.move(a['x'], a['y'])
    settled(page, lambda: hl(page), lambda v: v == ['IdmA', '0,0,1,0'])
    p0, h0 = pan(page), history_index(page)
    page.mouse.down(button='middle')
    page.mouse.move(a['x'] + 50, a['y'] + 30, steps=5)
    page.mouse.up(button='middle')
    p1 = pan(page)
    assert abs(p1[0] - p0[0] - 50) < 1 and abs(p1[1] - p0[1] - 30) < 1, (p0, p1)
    z0 = page.evaluate("() => window.canvasRenderer.zoom")
    page.mouse.wheel(0, -240)
    settled(page, lambda: page.evaluate("() => window.canvasRenderer.zoom"), lambda z: z != z0)
    assert page.evaluate("() => window.canvasRenderer.zoom") != z0
    page.wait_for_timeout(200)
    assert marks_of(page, 'IdmA') == {}
    assert history_index(page) == h0
    # a Space held through a middle drag is no tap
    page.keyboard.down('Space')
    page.mouse.down(button='middle')
    page.mouse.move(a['x'] + 10, a['y'] + 10, steps=3)
    page.mouse.up(button='middle')
    page.keyboard.up('Space')
    page.wait_for_timeout(200)
    assert marks_of(page, 'IdmA') == {}


# ── marking ───────────────────────────────────────────────────────────────

def test_esc_cancels_a_drag_mark(page):
    reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    h0, o0 = history_index(page), offsets(page)
    a = point(page, 'IdmA', 0, 0, 0, 0)
    b = point(page, 'IdmA', 1, 0, 1, 0)
    page.mouse.move(a['x'], a['y'])
    page.mouse.down()
    page.mouse.move(b['x'], b['y'], steps=8)
    assert len(marks_of(page, 'IdmA')) >= 3
    page.keyboard.press('Escape')
    assert marks_of(page, 'IdmA') == {}
    page.mouse.up()
    page.wait_for_timeout(300)
    assert marks_of(page, 'IdmA') == {}
    assert served_idm(page, 'IdmA')['marks'] == {}
    assert history_index(page) == h0
    assert offsets(page) == o0
    # Esc with no drag still clears the highlight
    assert hl(page) is not None
    page.keyboard.press('Escape')
    assert hl(page) is None


def test_a_quick_drag_marks_every_module_it_crosses_and_moves_nothing(page):
    reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    o0 = offsets(page)
    a = point(page, 'IdmA', 0, 0, 0, 0)
    b = point(page, 'IdmA', 2, 0, 1, 0)
    page.mouse.move(a['x'], a['y'])
    page.mouse.down()
    page.mouse.move(b['x'], b['y'], steps=1)     # one jump across the screen
    page.mouse.up()
    want = {'0,0,0,0', '0,0,1,0', '1,0,0,0', '1,0,1,0', '2,0,0,0', '2,0,1,0'}
    got = settled(page, lambda: served_idm(page, 'IdmA'), lambda v: v and set(v['marks']) == want)
    assert set(got['marks']) == want, got
    assert offsets(page) == o0


def test_right_click_clears_a_mark_and_opens_the_menu_elsewhere(page):
    reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    a = point(page, 'IdmA', 0, 1, 1, 0)
    page.mouse.click(a['x'], a['y'])
    settled(page, lambda: served_idm(page, 'IdmA'), lambda v: v and '0,1,1,0' in v['marks'])
    h0 = history_index(page)
    page.mouse.click(a['x'], a['y'], button='right')
    got = settled(page, lambda: served_idm(page, 'IdmA'), lambda v: v and v['marks'] == {})
    assert got['marks'] == {}, got
    assert history_index(page) == h0 + 1
    assert not page.evaluate("() => document.getElementById('context-menu').style.display === 'block'")
    # an unmarked module: the menu as everywhere
    page.mouse.click(a['x'], a['y'], button='right')
    page.wait_for_function("() => document.getElementById('context-menu').style.display === 'block'")
    assert marks_of(page, 'IdmA') == {}
    page.keyboard.press('Escape')
    page.evaluate("() => window.app.hideContextMenu()")
    # undo brings the mark back
    page.keyboard.press('Control+z')
    settled(page, lambda: marks_of(page, 'IdmA'), lambda v: '0,1,1,0' in v)
    assert '0,1,1,0' in marks_of(page, 'IdmA')


def test_the_cursor_says_mark_or_clear(page):
    reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    cursor = lambda: page.evaluate("() => window.canvasRenderer.canvas.style.cursor")  # noqa: E731
    a = point(page, 'IdmA', 0, 0, 0, 0)
    page.mouse.move(a['x'], a['y'])
    assert 'crosshair' in cursor()
    page.mouse.click(a['x'], a['y'])
    page.mouse.move(a['x'] + 1, a['y'] + 1)
    assert 'cell' in cursor()
    gap = client_of(page, 480, 100)          # between the two screens
    page.mouse.move(gap['x'], gap['y'])
    assert cursor() == 'default'
    page.keyboard.down('Space')
    page.mouse.move(gap['x'] + 1, gap['y'])
    assert cursor() == 'grab'
    page.keyboard.up('Space')
    # a locked screen: no-entry
    page.evaluate("""() => { const l = window.app.project.layers.find(x => x.name === 'IdmB');
        l.locked = true; }""")
    b = point(page, 'IdmB', 0, 0, 0, 0)
    page.mouse.move(b['x'], b['y'])
    assert cursor() == 'not-allowed'
    page.evaluate("""() => { const l = window.app.project.layers.find(x => x.name === 'IdmB');
        l.locked = false; }""")


# ── the mouse on the wall ─────────────────────────────────────────────────

def arrow_px(p):
    """A point well inside the arrow whose tip is at workspace p (the arrow
    is 65 px tall on a 1920 x 1080 raster)."""
    return int(round(p['x'] + 6)), int(round(p['y'] + 32))


def test_the_mouse_shows_on_the_output_and_hides_on_leave_and_switch(page):
    cid = reset_project(page)
    page.click('[data-idm-field="#ff0000"]')      # a dark field: a white arrow
    out = open_output(page, cid)
    try:
        gap = client_of(page, 470, 120)            # between the screens, black on the wall
        page.mouse.move(gap['x'], gap['y'])
        p = settled(page, lambda: pointer(page), lambda v: v is not None)
        assert p and p['canvasId'] == cid, p
        assert abs(p['x'] - 470) < 2 and abs(p['y'] - 120) < 2, p
        x, y = arrow_px(p)
        wait_pixel(out, x, y, (255, 255, 255))
        wait_pixel(out, x, int(p['y']) - 12, (0, 0, 0))     # above the tip: the wall
        # it follows the mouse
        gap2 = client_of(page, 500, 400)
        page.mouse.move(gap2['x'], gap2['y'])
        p2 = settled(page, lambda: pointer(page), lambda v: v and abs(v['y'] - 400) < 2)
        wait_pixel(out, *arrow_px(p2), (255, 255, 255))
        wait_pixel(out, x, y, (0, 0, 0))
        # off the view: gone
        page.mouse.move(3, 3)
        settled(page, lambda: pointer(page), lambda v: v is None)
        wait_pixel(out, *arrow_px(p2), (0, 0, 0))
        # the switch off: no arrow while the mouse is over the canvas
        page.click('#idm-pointer')
        assert page.get_attribute('#idm-pointer', 'aria-pressed') == 'false'
        page.mouse.move(gap2['x'], gap2['y'])
        page.mouse.move(gap2['x'] + 1, gap2['y'])
        page.wait_for_timeout(250)
        assert pointer(page) is None
        assert pixel(out, *arrow_px(p2)) == [0, 0, 0]
        assert page.evaluate("() => localStorage.getItem('lrdIdmPointer')") == '0'
        page.click('#idm-pointer')
        page.mouse.move(gap2['x'] + 2, gap2['y'])
        p3 = settled(page, lambda: pointer(page), lambda v: v is not None)
        wait_pixel(out, *arrow_px(p3), (255, 255, 255))
        # moving the arrow is a copy over the last frame, never a render
        renders = page.evaluate("""() => { const r = window.canvasRenderer; r.__n = 0;
            const o = r.render; r.__o = o; r.render = function () { if (this.exportMode) r.__n++; return o.apply(this, arguments); };
            return 0; }""")
        for k in range(8):
            page.mouse.move(gap2['x'] + 4 + k * 3, gap2['y'] + k)
            page.wait_for_timeout(20)
        page.wait_for_timeout(300)
        renders = page.evaluate("() => { const r = window.canvasRenderer; r.render = r.__o; return r.__n; }")
        assert renders == 0, renders
        # leaving the tab takes it off the wall
        page.click('.view-tab[data-mode="pixel-map"]')
        settled(page, lambda: pointer(page), lambda v: v is None)
        assert pointer(page) is None
        page.click('.view-tab[data-mode="idm"]')
        assert not page._errors, page._errors
    finally:
        out.close()


def test_on_a_light_field_the_arrow_is_black_over_a_screen(page):
    cid = reset_project(page)
    out = open_output(page, cid)
    try:
        # IdmB's middle, white field: the arrow is black there
        target = client_of(page, 700, 60)
        page.mouse.move(target['x'], target['y'])
        p = settled(page, lambda: pointer(page), lambda v: v is not None)
        wait_pixel(out, *arrow_px(p), (0, 0, 0))
    finally:
        out.close()


# ── several outputs at once ───────────────────────────────────────────────

def _frames(out):
    return out.evaluate("() => Number(document.body.dataset.frames || 0)")


def _open_from_dialog(page, cid, view, scale='1to1'):
    page.evaluate("window.app.handleMenuAction('output-to-display')")
    page.wait_for_selector('#output-display-modal', state='visible')
    page.select_option('#output-display-canvas', cid)
    page.select_option('#output-display-view', view)
    page.check(f'input[name="output-display-scale"][value="{scale}"]')
    with page.expect_popup() as info:
        page.click('#output-display-open')
    out = info.value
    out.wait_for_load_state('domcontentloaded')
    settled(out, lambda: _frames(out), lambda n: n >= 1, 8000)
    assert _frames(out) >= 1
    return out


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


def test_two_outputs_at_once_follow_edits_and_close_apart(page):
    cid = reset_project(page)
    c2 = page.evaluate(SECOND_CANVAS_JS)
    page.wait_for_function("() => (window.app.project.layers || []).length === 3"
                           " && (window.app.project.canvases || []).length === 2", timeout=10000)
    page.wait_for_timeout(500)
    a = _open_from_dialog(page, cid, 'idm')
    assert page.inner_text('#output-display-open') == 'Open another output'
    b = _open_from_dialog(page, c2, 'pixel-map')
    c = _open_from_dialog(page, cid, 'idm')            # the same canvas on a third display
    try:
        rows = page.locator('#output-display-open-list .od-open-row')
        assert rows.count() == 3
        texts = rows.all_inner_texts()
        assert texts[0].startswith('Canvas 1 · IDM Locator · 1:1 pixel'), texts
        assert texts[1].startswith('Canvas 2 · Pixel Map · 1:1 pixel'), texts
        assert [a_.evaluate("() => document.getElementById('output-canvas').width") for a_ in (a, b, c)] == [1920, 640, 1920]
        # an edit on each canvas reaches its outputs
        fb = _frames(b)
        page.evaluate("""() => { const l = window.app.project.layers.find(x => x.name === 'IdmC');
            l.offset_x = 100; window.app.updateLayers([l], true, 'Move'); window.canvasRenderer.render(); }""")
        settled(b, lambda: _frames(b), lambda n: n > fb, 5000)
        assert _frames(b) > fb
        wait_pixel(b, 50, 50, (0, 0, 0), tol=40)
        page.evaluate("window.app.closeOutputDisplayDialog()")
        page.click('[data-idm-field="#0000ff"]')
        wait_pixel(a, 60, 60, (0, 0, 255), tol=40)
        wait_pixel(c, 60, 60, (0, 0, 255), tol=40)
        # the mouse shows on both IDM outputs of that canvas, not on the
        # Pixel Map one of the other
        gap = client_of(page, 470, 120)
        page.mouse.move(gap['x'], gap['y'])
        p = settled(page, lambda: pointer(page), lambda v: v is not None)
        wait_pixel(a, *arrow_px(p), (255, 255, 255))
        wait_pixel(c, *arrow_px(p), (255, 255, 255))
        page.mouse.move(3, 3)
        # close the first: the others stay and keep following
        page.evaluate("window.app.handleMenuAction('output-to-display')")
        page.wait_for_selector('#output-display-modal', state='visible')
        with a.expect_event('close', timeout=5000):
            rows.first.locator('button').click()
        assert page.evaluate("window.app.listOutputDisplays().length") == 2
        assert not b.is_closed() and not c.is_closed()
        fb = _frames(b)
        page.evaluate("""() => { const l = window.app.project.layers.find(x => x.name === 'IdmC');
            l.offset_x = 0; window.app.updateLayers([l], true, 'Move'); window.canvasRenderer.render(); }""")
        settled(b, lambda: _frames(b), lambda n: n > fb, 5000)
        assert _frames(b) > fb
        page.evaluate("window.app.closeOutputDisplayDialog()")
        page.click('[data-idm-field="#00ff00"]')
        wait_pixel(c, 60, 60, (0, 255, 0), tol=40)
    finally:
        for o in (a, b, c):
            if not o.is_closed():
                o.close()
        page.evaluate("window.app.closeOutputDisplayDialog()")
    page.wait_for_timeout(300)
    assert page.evaluate("window.app.listOutputDisplays().length") == 0


def test_the_dialog_names_each_display_and_moves_on_to_a_free_one(page):
    cid = reset_project(page)
    page.evaluate("window.app.handleMenuAction('output-to-display')")
    page.wait_for_selector('#output-display-modal', state='visible')
    # Two displays far from this window (as the browser lists them when it
    # can place windows), so each output keeps the display it was opened on.
    page.evaluate("""() => {
        const mk = (label, left) => ({label, left, top: 0, width: 1920, height: 1080,
            availLeft: left, availTop: 0, availWidth: 1920, availHeight: 1080, isPrimary: false});
        window.app._outputDisplayScreens = [mk('Wall A', 90000), mk('Wall B', 92000)];
        document.getElementById('output-display-screen-row').hidden = false;
        window.app._outputDisplayFillScreens(false);
    }""")
    assert page.input_value('#output-display-screen') == '0'
    page.select_option('#output-display-canvas', cid)
    page.select_option('#output-display-view', 'idm')
    page.check('input[name="output-display-scale"][value="fit"]')
    with page.expect_popup() as info:
        page.click('#output-display-open')
    out = info.value
    try:
        out.wait_for_load_state('domcontentloaded')
        rows = page.locator('#output-display-open-list .od-open-row')
        assert rows.first.inner_text().startswith('Canvas 1 · IDM Locator · Fit to display · on Wall A'), rows.first.inner_text()
        # the next output goes to the display without one
        assert page.input_value('#output-display-screen') == '1'
        assert 'has an output' in page.inner_text('#output-display-screen option[value="0"]')
    finally:
        out.close()
        page.evaluate("""() => { window.app._outputDisplayScreens = null;
            window.app.closeOutputDisplayDialog(); }""")


def test_a_browser_that_cannot_place_windows_says_to_drag_them(e2e_server, pw_browser):
    context, pg = _new_page(pw_browser, e2e_server)
    try:
        # no Window Management API, as in Firefox and Safari
        pg.add_init_script("delete window.getScreenDetails;")
        pg.reload(wait_until='domcontentloaded')
        pg.wait_for_function("() => window.app && window.app.project", timeout=15000)
        pg.evaluate("window.app.handleMenuAction('output-to-display')")
        pg.wait_for_selector('#output-display-modal', state='visible')
        assert not pg.is_visible('#output-display-screen-row')
        assert pg.is_visible('#output-display-place-note')
        assert 'Drag it onto its display' in pg.inner_text('#output-display-place-note')
    finally:
        context.close()
