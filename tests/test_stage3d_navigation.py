"""Getting around the 3D tab, and moving screens with its handles.

The owner's rulings (2026-11-08): the 3D view uses standard 3D navigation,
and screens are moved and turned with on-screen handles.

What this file pins, each with real mouse, wheel and key events:

* Middle-drag orbits round the point under the cursor (it stays put on the
  page), or round the view's centre from empty space; Shift+middle-drag and
  right-drag pan (what was grabbed follows the cursor, and the right
  button's menu does not open after a pan); Alt+drag orbits and
  Alt+Shift+drag pans for a mouse with no middle button.
* The wheel zooms toward the pointer: the world point under it stays under
  it. Ctrl+wheel and a trackpad pinch (a wheel event with ctrlKey) zoom the
  same way; a trackpad's two-finger drag orbits and Shift pans.
* A left click selects and never moves the camera; Shift+click adds; a
  click on empty space lets go; a left drag on empty space box-selects.
* F frames the selection, double-click focuses a screen, 1 to 6 and the
  view buttons glide to a view, Home goes back to the starting view; none of
  the keys fire while a field is being typed in.
* The camera is view state: no undo step, saved with the show, kept across a
  tab switch and a reload.
* The handles: an arrow moves along one axis only, a ring turns only its
  own angle, Ctrl snaps (6 in, 0.1 m in meters, 15 degrees), Esc puts the
  drag back, one undo step per drag, a locked screen refuses and is named, a
  group moves as one, W and E switch, and the arrow keys nudge in one undo
  step per burst.

Run locally:
    python -m pytest tests/test_stage3d_navigation.py -v -p no:cacheprovider
"""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from conftest import settled  # noqa: E402
from test_stage3d import (  # noqa: E402
    FT, TWO, _context, dbg, group_two, history_len, open_3d, open_tab, reset,
    screen, served, set_locked, stored, toast_says, type_field, undo,
)


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project exactly as this module found it
    (see conftest.server_project_guard)."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = _context(pw_browser)
    pg = context.new_page()
    pg.errors = []
    pg.on('pageerror', lambda err: pg.errors.append(str(err)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    yield pg
    context.close()


# ── helpers ─────────────────────────────────────────────────────────────

def camera(page):
    return dbg(page)['camera']


def landed(page):
    """The camera has finished any glide (a view button, F, Home)."""
    return settled(page, lambda: dbg(page), lambda d: not d['gliding'], 3000)['camera']


def view(page, name):
    page.click(f'[data-s3d-view="{name}"]')
    return landed(page)


def probe(page, x, y):
    return page.evaluate(f"window.app._s3dDebugProbe({x}, {y})")


def where(page, point):
    return page.evaluate("(p) => window.app._s3dDebugWhere(p)", point)


def drag(page, start, end, button='left', steps=12, keys=(), before_up=None):
    for k in keys:
        page.keyboard.down(k)
    page.mouse.move(start[0], start[1])
    page.mouse.down(button=button)
    for i in range(1, steps + 1):
        page.mouse.move(start[0] + (end[0] - start[0]) * i / steps,
                        start[1] + (end[1] - start[1]) * i / steps)
        page.wait_for_timeout(15)
    if before_up:
        before_up()
    page.mouse.up(button=button)
    for k in reversed(keys):
        page.keyboard.up(k)
    page.wait_for_timeout(150)


def angle_of(cam):
    """Azimuth and elevation of the camera round its centre, degrees."""
    dx, dy, dz = (cam['position'][i] - cam['target'][i] for i in range(3))
    return (math.degrees(math.atan2(dx, dz)),
            math.degrees(math.atan2(dy, math.hypot(dx, dz))))


def dist(a, b):
    return math.dist(a, b)


def selected(page):
    return page.evaluate("""() => {
        const a = window.app;
        const ids = a.selectedLayerIds && a.selectedLayerIds.size ? [...a.selectedLayerIds]
            : (a.currentLayer ? [a.currentLayer.id] : []);
        return ids.sort((x, y) => x - y);
    }""")


def handles(page):
    return settled(page, lambda: dbg(page)['handles'], lambda h: h and h['shown'], 3000)


def wheel_event(page, x, y, **init):
    """A wheel event the way a trackpad sends it (Playwright's own wheel is
    a mouse wheel)."""
    page.evaluate("""([x, y, init]) => {
        const cv = document.getElementById('s3d-canvas');
        const ev = new WheelEvent('wheel', Object.assign({
            bubbles: true, cancelable: true, clientX: x, clientY: y, deltaMode: 0}, init));
        cv.dispatchEvent(ev);
    }""", [x, y, init])


def fresh(page, specs=TWO):
    ids = reset(page, specs)
    open_3d(page, len(specs))
    landed(page)
    page.click('#s3d-tool-move')
    return ids


def clear_toasts(page):
    page.evaluate("(() => { const h = document.getElementById('app-toast-host'); if (h) h.innerHTML = ''; })()")


# ── the camera ──────────────────────────────────────────────────────────

def test_middle_drag_orbits_round_the_point_under_the_cursor(page):
    ids = fresh(page)
    view(page, 'iso')
    at = screen(page, ids[1])['at']
    grabbed = probe(page, *at)
    assert grabbed, 'nothing under the cursor'
    before = camera(page)
    steps = history_len(page)
    drag(page, at, (at[0] + 120, at[1] + 40), button='middle')
    after = camera(page)
    a0, a1 = angle_of(before), angle_of(after)
    assert abs(a1[0] - a0[0]) > 10, (before, after)
    assert abs(a1[1] - a0[1]) > 2, (before, after)
    # what was grabbed stays put on the page
    now = where(page, grabbed)
    assert dist(now, at) < 2, (now, at)
    assert history_len(page) == steps, 'the camera is view state'
    saved = settled(page, lambda: page.evaluate(
        "async () => (await (await fetch('/api/project')).json()).stage3dCamera"),
        lambda v: v and v['position'] == after['position'])
    assert saved['position'] == after['position']
    assert page.errors == []


def test_middle_drag_on_empty_space_orbits_round_the_view_centre(page):
    fresh(page)
    view(page, 'front')
    rect = page.evaluate("document.getElementById('s3d-canvas').getBoundingClientRect().toJSON()")
    corner = (rect['left'] + 30, rect['top'] + 30)
    assert probe(page, *corner) is None
    before = camera(page)
    drag(page, corner, (corner[0] + 100, corner[1]), button='middle')
    after = camera(page)
    assert after['target'] == pytest.approx(before['target'], abs=0.5)
    assert abs(angle_of(after)[0] - angle_of(before)[0]) > 10


def test_shift_middle_drag_and_right_drag_pan_and_no_menu_after_a_pan(page):
    ids = fresh(page)
    view(page, 'front')
    at = screen(page, ids[0])['at']
    grabbed = probe(page, *at)
    before = camera(page)
    drag(page, at, (at[0] + 90, at[1] - 50), button='middle', keys=('Shift',))
    after = camera(page)
    assert angle_of(after) == pytest.approx(angle_of(before), abs=0.01), 'a pan turned the camera'
    assert dist(after['target'], before['target']) > 50
    assert dist(where(page, grabbed), (at[0] + 90, at[1] - 50)) < 2
    # right-drag pans the same way, and opens no menu
    at2 = where(page, grabbed)
    drag(page, at2, (at2[0] - 70, at2[1] + 30), button='right')
    assert dist(where(page, grabbed), (at2[0] - 70, at2[1] + 30)) < 2
    page.wait_for_timeout(200)
    assert page.evaluate("getComputedStyle(document.getElementById('context-menu')).display") == 'none'


def test_alt_drag_orbits_and_alt_shift_drag_pans(page):
    ids = fresh(page)
    view(page, 'iso')
    at = screen(page, ids[0])['at']
    sel = selected(page)
    before = camera(page)
    drag(page, at, (at[0] + 100, at[1]), keys=('Alt',))
    mid = camera(page)
    assert abs(angle_of(mid)[0] - angle_of(before)[0]) > 10
    assert stored(page, ids[0]) is None, 'an Alt drag moved the screen'
    drag(page, at, (at[0] + 60, at[1] + 60), keys=('Alt', 'Shift'))
    after = camera(page)
    assert angle_of(after) == pytest.approx(angle_of(mid), abs=0.01)
    assert dist(after['target'], mid['target']) > 50
    assert selected(page) == sel


def test_the_wheel_zooms_toward_the_pointer(page):
    ids = fresh(page)
    view(page, 'iso')
    at = screen(page, ids[1])['at']
    point = (at[0] + 15, at[1] + 5)
    grabbed = probe(page, *point)
    assert grabbed
    before = camera(page)
    page.mouse.move(*point)
    for _ in range(3):
        page.mouse.wheel(0, -100)
        page.wait_for_timeout(60)
    after = camera(page)
    assert dbg(page)['wheel'] == 'wheel'
    assert dist(after['position'], grabbed) < dist(before['position'], grabbed) * 0.8
    assert dist(where(page, grabbed), point) < 1.5
    # and back out
    page.mouse.wheel(0, 300)
    page.wait_for_timeout(100)
    assert dist(where(page, grabbed), point) < 1.5
    assert dist(camera(page)['position'], grabbed) > dist(after['position'], grabbed)


def test_ctrl_wheel_and_a_pinch_zoom_toward_the_pointer(page):
    ids = fresh(page)
    view(page, 'iso')
    at = screen(page, ids[0])['at']
    point = (at[0] - 20, at[1] + 10)
    grabbed = probe(page, *point)
    start = camera(page)
    page.mouse.move(*point)
    page.keyboard.down('Control')
    page.mouse.wheel(0, -100)
    page.keyboard.up('Control')
    page.wait_for_timeout(100)
    mid = camera(page)
    assert dbg(page)['wheel'] == 'pinch'
    assert dist(mid['position'], grabbed) < dist(start['position'], grabbed)
    assert dist(where(page, grabbed), point) < 1.5
    # a trackpad pinch: small steps, ctrlKey set by the browser
    for _ in range(10):
        wheel_event(page, point[0], point[1], deltaY=-4, ctrlKey=True)
    page.wait_for_timeout(100)
    end = camera(page)
    assert dist(end['position'], grabbed) < dist(mid['position'], grabbed) * 0.85
    assert dist(where(page, grabbed), point) < 1.5


def test_a_trackpad_two_finger_drag_orbits_and_shift_pans(page):
    ids = fresh(page)
    view(page, 'iso')
    at = screen(page, ids[0])['at']
    grabbed = probe(page, *at)
    before = camera(page)
    for _ in range(8):
        wheel_event(page, at[0], at[1], deltaX=-12, deltaY=0, wheelDeltaX=36)
    page.wait_for_timeout(100)
    mid = camera(page)
    assert dbg(page)['wheel'] == 'pad'
    assert abs(angle_of(mid)[0] - angle_of(before)[0]) > 5
    assert dist(where(page, grabbed), at) < 2, 'the orbit did not turn round the point under the pointer'
    page.wait_for_timeout(300)   # a new gesture
    for _ in range(6):
        wheel_event(page, at[0], at[1], deltaX=-10, deltaY=-6, shiftKey=True)
    page.wait_for_timeout(100)
    after = camera(page)
    assert angle_of(after) == pytest.approx(angle_of(mid), abs=0.01)
    assert dist(after['target'], mid['target']) > 20


def test_a_left_click_selects_and_never_moves_the_camera(page):
    ids = fresh(page)
    view(page, 'front')
    cam = camera(page)
    lower = screen(page, ids[1])['at']
    upper = screen(page, ids[0])['at']
    page.mouse.click(*lower)
    page.wait_for_timeout(300)
    assert selected(page) == [ids[1]]
    page.keyboard.down('Shift')
    page.mouse.click(*upper)
    page.keyboard.up('Shift')
    page.wait_for_timeout(300)
    assert selected(page) == sorted(ids)
    rect = page.evaluate("document.getElementById('s3d-canvas').getBoundingClientRect().toJSON()")
    page.mouse.click(rect['left'] + 30, rect['top'] + 30)
    page.wait_for_timeout(300)
    assert selected(page) == []
    assert page.evaluate("document.getElementById('s3d-none').hidden") is False
    assert camera(page) == cam, 'a left click moved the camera'


def test_a_left_drag_on_empty_space_box_selects(page):
    ids = fresh(page)
    view(page, 'front')
    cam = camera(page)
    lower = screen(page, ids[1])['at']
    upper = screen(page, ids[0])['at']
    rect = page.evaluate("document.getElementById('s3d-canvas').getBoundingClientRect().toJSON()")
    corner = (rect['left'] + 20, rect['top'] + 20)
    # across both
    drag(page, corner, (upper[0] + 5, lower[1] + 5))
    assert selected(page) == sorted(ids)
    assert camera(page) == cam, 'a box select moved the camera'
    assert stored(page, ids[0]) is None and stored(page, ids[1]) is None
    # round the lower one only, from below it
    bottom = (lower[0] - 10, rect['bottom'] - 10)
    drag(page, bottom, (lower[0] + 10, lower[1] + 5))
    assert selected(page) == [ids[1]]
    # Shift adds
    drag(page, corner, (upper[0], upper[1]), keys=('Shift',))
    assert selected(page) == sorted(ids)
    assert page.evaluate("document.getElementById('s3d-box').hidden")


def test_f_frames_the_selection_and_double_click_focuses(page):
    ids = fresh(page)
    view(page, 'iso')
    page.evaluate(f"window.app.setSelectedLayersByIds([{ids[1]}], {ids[1]})")
    page.wait_for_timeout(300)
    page.mouse.move(5, 5)
    page.keyboard.press('f')
    cam = landed(page)
    lower = screen(page, ids[1])['world']
    centre = [(lower['min'][i] + lower['max'][i]) / 2 for i in range(3)]
    assert cam['target'] == pytest.approx(centre, abs=1)
    # nothing selected: every screen
    page.evaluate("window.app.setSelectedLayersByIds([], null)")
    page.wait_for_timeout(300)
    page.keyboard.press('f')
    cam = landed(page)
    assert cam['target'] != pytest.approx(centre, abs=1)
    # double-click the upper screen
    at = screen(page, ids[0])['at']
    page.mouse.dblclick(*at)
    cam = landed(page)
    upper = screen(page, ids[0])['world']
    assert cam['target'] == pytest.approx([(upper['min'][i] + upper['max'][i]) / 2 for i in range(3)], abs=1)
    assert stored(page, ids[0]) is None, 'the double-click moved the screen'


def test_view_keys_buttons_and_home_glide_and_keys_wait_for_typing(page):
    fresh(page)
    page.mouse.move(5, 5)
    page.keyboard.press('5')
    top = landed(page)
    assert top['position'][1] - top['target'][1] > 10 * abs(top['position'][2] - top['target'][2])
    page.keyboard.press('Numpad1')
    front = landed(page)
    assert front['position'][2] - front['target'][2] > 1000
    assert abs(front['position'][1] - front['target'][1]) < 1
    # a button glides there over a moment
    page.click('[data-s3d-view="left"]')
    assert dbg(page)['gliding'] is True
    left = landed(page)
    assert left['position'][0] < left['target'][0]
    # Home: perspective, the starting angle
    page.click('#s3d-mode-ortho')
    page.wait_for_timeout(200)
    page.keyboard.press('Home')
    home = landed(page)
    assert home['mode'] == 'perspective'
    az, el = angle_of(home)
    assert az == pytest.approx(math.degrees(math.atan2(0.35, 1)), abs=0.5)
    assert el > 5
    # typing in a field: the keys are the field's
    page.click('#s3d-tool-move')
    page.evaluate(f"window.app.setSelectedLayersByIds([window.app.project.layers[0].id], window.app.project.layers[0].id)")
    page.wait_for_timeout(300)
    page.click('#s3d-x')
    page.keyboard.press('5')
    page.keyboard.press('e')
    page.wait_for_timeout(500)
    assert dbg(page)['camera'] == home
    assert dbg(page)['tool'] == 'move'
    assert '5e' in page.input_value('#s3d-x')
    page.keyboard.press('Escape')
    page.evaluate("document.activeElement.blur()")


def test_the_camera_is_kept_across_a_tab_switch_and_a_reload(page):
    ids = fresh(page)
    view(page, 'iso')
    at = screen(page, ids[0])['at']
    drag(page, at, (at[0] + 80, at[1] - 20), button='middle')
    page.mouse.move(at[0], at[1])
    page.mouse.wheel(0, -200)
    page.wait_for_timeout(100)
    cam = camera(page)
    settled(page, lambda: page.evaluate(
        "async () => (await (await fetch('/api/project')).json()).stage3dCamera"),
        lambda v: v and v['position'] == cam['position'])
    open_tab(page, 'pixel-map')
    open_tab(page, '3d')
    page.wait_for_timeout(400)
    assert camera(page) == cam
    page.reload(wait_until='domcontentloaded')
    page.wait_for_timeout(2500)
    open_3d(page, 2)
    back = settled(page, lambda: camera(page), lambda v: v and v['position'] == pytest.approx(cam['position'], abs=0.05))
    assert back['position'] == pytest.approx(cam['position'], abs=0.05)
    assert back['target'] == pytest.approx(cam['target'], abs=0.05)


# ── the handles ─────────────────────────────────────────────────────────

def grip_drag(page, name, by, keys=(), before_up=None):
    h = handles(page)
    g = h['grips'][name]
    drag(page, g, (g[0] + by[0], g[1] + by[1]), keys=keys, before_up=before_up)


def test_an_arrow_moves_along_its_axis_only_in_one_undo_step(page):
    ids = fresh(page)
    view(page, 'iso')
    page.evaluate(f"window.app.setSelectedLayersByIds([{ids[0]}], {ids[0]})")
    h = handles(page)
    assert h['ids'] == [ids[0]] and h['tool'] == 'move' and set(h['grips']) >= {'x', 'y', 'z'}
    before = screen(page, ids[0])['placement']
    steps = history_len(page)
    cam = camera(page)
    # a drag that wanders off the arrow still slides along it only
    grip_drag(page, 'x', (90, 40))
    after = stored(page, ids[0])
    assert after, 'the arrow moved nothing'
    assert after['x'] > before['x'] + 100
    assert (after['y'], after['z']) == pytest.approx((before['y'], before['z']), abs=0.001)
    assert history_len(page) == steps + 1
    assert camera(page) == cam
    assert page.input_value('#s3d-x') == f"{after['x'] / FT:.2f}"
    grip_drag(page, 'y', (0, -60))
    up = stored(page, ids[0])
    assert up['y'] > after['y'] + 100 and up['x'] == pytest.approx(after['x'])
    grip_drag(page, 'z', (-50, 40))
    toward = stored(page, ids[0])
    assert toward['z'] != pytest.approx(up['z']) and toward['y'] == pytest.approx(up['y'])
    assert history_len(page) == steps + 3
    undo(page)
    undo(page)
    undo(page)
    assert stored(page, ids[0]) is None


def test_a_ring_turns_only_its_own_angle(page):
    ids = fresh(page)
    page.evaluate(f"window.app.setSelectedLayersByIds([{ids[0]}], {ids[0]})")
    type_field(page, 's3d-pitch', '10')
    view(page, 'iso')
    page.mouse.move(5, 5)
    page.keyboard.press('e')
    assert settled(page, lambda: dbg(page)['tool'], lambda t: t == 'rotate') == 'rotate'
    assert page.evaluate("document.getElementById('s3d-tool-rotate').classList.contains('active')")
    start = stored(page, ids[0])
    steps = history_len(page)
    grip_drag(page, 'yaw', (0, 70))
    turned = stored(page, ids[0])
    assert abs(turned['yaw'] - start['yaw']) > 5, (start, turned)
    assert turned['pitch'] == pytest.approx(10, abs=1e-6)
    assert turned['roll'] == pytest.approx(0, abs=1e-6)
    assert (turned['x'], turned['y'], turned['z']) == pytest.approx((start['x'], start['y'], start['z']), abs=0.001)
    assert history_len(page) == steps + 1
    grip_drag(page, 'roll', (0, 60))
    rolled = stored(page, ids[0])
    assert abs(rolled['roll']) > 5
    assert rolled['yaw'] == pytest.approx(turned['yaw'], abs=1e-6)
    assert rolled['pitch'] == pytest.approx(10, abs=1e-6)
    grip_drag(page, 'pitch', (0, 60))
    pitched = stored(page, ids[0])
    assert abs(pitched['pitch'] - 10) > 3
    assert pitched['yaw'] == pytest.approx(rolled['yaw'], abs=1e-6)
    assert pitched['roll'] == pytest.approx(rolled['roll'], abs=1e-6)
    page.keyboard.press('w')
    assert settled(page, lambda: dbg(page)['tool'], lambda t: t == 'move') == 'move'


def test_ctrl_snaps_moves_and_turns_and_the_figure_rides_the_cursor(page):
    ids = fresh(page)
    view(page, 'iso')
    page.evaluate(f"window.app.setSelectedLayersByIds([{ids[0]}], {ids[0]})")
    handles(page)
    seen = {}

    def read():
        seen['text'] = page.evaluate("(() => { const r = document.getElementById('s3d-readout');"
                                     " return r && !r.hidden ? r.textContent : ''; })()")
    x0 = screen(page, ids[0])['placement']['x']
    grip_drag(page, 'x', (83, 0), keys=('Control',), before_up=read)
    dx = stored(page, ids[0])['x'] - x0
    assert dx / 152.4 == pytest.approx(round(dx / 152.4), abs=1e-6) and abs(dx) >= 152.4, dx
    assert seen['text'].startswith('X +') and seen['text'].endswith((' ft', ' in')), seen
    # meters: 0.1 m steps
    page.click('#s3d-units-m')
    page.wait_for_timeout(200)
    x0 = stored(page, ids[0])['x']
    grip_drag(page, 'x', (71, 0), keys=('Control',), before_up=read)
    dx = stored(page, ids[0])['x'] - x0
    assert dx / 100 == pytest.approx(round(dx / 100), abs=1e-6) and abs(dx) >= 100, dx
    assert seen['text'].endswith(' m'), seen
    page.click('#s3d-units-ft')
    # turns: whole 15 degrees
    page.mouse.move(5, 5)
    page.keyboard.press('e')
    grip_drag(page, 'yaw', (0, 55), keys=('Control',), before_up=read)
    yaw = stored(page, ids[0])['yaw']
    assert yaw % 15 == pytest.approx(0, abs=1e-6) or yaw % 15 == pytest.approx(15, abs=1e-6), yaw
    assert yaw != 0
    assert seen['text'].startswith('Yaw ') and seen['text'].endswith('°'), seen
    page.keyboard.press('w')


def test_esc_puts_a_handle_drag_back(page):
    ids = fresh(page)
    view(page, 'iso')
    page.evaluate(f"window.app.setSelectedLayersByIds([{ids[0]}], {ids[0]})")
    before = screen(page, ids[0])['placement']
    steps = history_len(page)
    grip_drag(page, 'x', (90, 0), before_up=lambda: page.keyboard.press('Escape'))
    assert stored(page, ids[0]) is None
    assert history_len(page) == steps
    assert screen(page, ids[0])['placement'] == before
    world = page.evaluate(f"""(() => {{ const e = window.app._s3d.entries.get({ids[0]});
        return e.obj.position.toArray(); }})()""")
    assert world == pytest.approx([before['x'], before['y'], before['z']], abs=0.01)
    assert page.evaluate("document.getElementById('s3d-readout').hidden")
    # a body drag too
    at = screen(page, ids[0])['at']
    drag(page, at, (at[0] + 60, at[1]), before_up=lambda: page.keyboard.press('Escape'))
    assert stored(page, ids[0]) is None and history_len(page) == steps


def test_a_locked_screen_refuses_the_handles_and_the_nudges(page):
    ids = fresh(page)
    view(page, 'iso')
    page.evaluate(f"window.app.setSelectedLayersByIds([{ids[0]}], {ids[0]})")
    set_locked(page, ids[0])
    clear_toasts(page)
    steps = history_len(page)
    said = 'Upper is locked. Unlock it to change it.'
    grip_drag(page, 'x', (80, 0))
    assert said in toast_says(page, said)
    assert stored(page, ids[0]) is None and history_len(page) == steps
    clear_toasts(page)
    page.mouse.move(5, 5)
    page.keyboard.press('ArrowRight')
    assert said in toast_says(page, said)
    page.wait_for_timeout(900)
    assert stored(page, ids[0]) is None and history_len(page) == steps
    set_locked(page, ids[0], False)


def test_a_group_moves_as_one_on_the_handles(page):
    ids = reset(page, [
        {'name': 'Left', 'columns': 2, 'rows': 2, 'offset_x': 0, 'offset_y': 0},
        {'name': 'Right', 'columns': 2, 'rows': 2, 'offset_x': 256, 'offset_y': 0},
    ])
    group_two(page, ids)
    open_3d(page, 2)
    page.click('#s3d-tool-move')
    view(page, 'iso')
    h = handles(page)
    assert sorted(h['ids']) == sorted(ids)
    a0, b0 = screen(page, ids[0])['placement'], screen(page, ids[1])['placement']
    steps = history_len(page)
    grip_drag(page, 'z', (-40, 40))
    a, b = stored(page, ids[0]), stored(page, ids[1])
    assert a and b
    assert a['z'] - a0['z'] == pytest.approx(b['z'] - b0['z'], abs=0.001)
    assert abs(a['z'] - a0['z']) > 50
    assert history_len(page) == steps + 1
    assert settled(page, lambda: served(page, ids[1]), lambda v: v and v['z'] == pytest.approx(b['z']))


def test_arrow_keys_nudge_in_one_undo_step_per_burst(page):
    ids = fresh(page)
    view(page, 'front')
    page.evaluate(f"window.app.setSelectedLayersByIds([{ids[0]}], {ids[0]})")
    page.wait_for_timeout(300)
    before = screen(page, ids[0])['placement']
    steps = history_len(page)
    page.mouse.move(5, 5)
    for _ in range(3):
        page.keyboard.press('ArrowRight')
    page.keyboard.press('Shift+ArrowRight')
    page.keyboard.press('PageUp')
    page.keyboard.press('ArrowUp')         # from the front: away from the audience
    got = settled(page, lambda: stored(page, ids[0]), bool, 3000)
    assert got['x'] == pytest.approx(before['x'] + 3 * 25.4 + 152.4, abs=0.01)
    assert got['y'] == pytest.approx(before['y'] + 25.4, abs=0.01)
    assert got['z'] == pytest.approx(before['z'] - 25.4, abs=0.01)
    assert history_len(page) == steps + 1
    # in a field, the arrows are the field's
    page.click('#s3d-x')
    page.keyboard.press('ArrowRight')
    page.wait_for_timeout(900)
    assert stored(page, ids[0]) == got
    page.evaluate("document.activeElement.blur()")
    undo(page)
    assert stored(page, ids[0]) is None
    assert page.errors == []


def test_one_gesture_after_another(page):
    """The gestures in the order a person uses them: orbit, select, move,
    undo, zoom, frame, another tab and back, a reload. Each leaves the next
    one working and the camera where the last one put it."""
    ids = fresh(page)
    view(page, 'iso')
    lower = screen(page, ids[1])['at']
    drag(page, lower, (lower[0] + 70, lower[1] + 20), button='middle')
    orbited = camera(page)
    lower = screen(page, ids[1])['at']
    page.mouse.click(*lower)
    page.wait_for_timeout(300)
    assert selected(page) == [ids[1]] and camera(page) == orbited
    steps = history_len(page)
    before = screen(page, ids[1])['placement']
    drag(page, lower, (lower[0] + 60, lower[1]))
    moved = stored(page, ids[1])
    assert moved and moved['x'] != pytest.approx(before['x']) and history_len(page) == steps + 1
    assert camera(page) == orbited
    undo(page)
    assert stored(page, ids[1]) is None
    page.mouse.move(*lower)
    page.mouse.wheel(0, -200)
    page.wait_for_timeout(100)
    zoomed = camera(page)
    assert zoomed != orbited
    page.mouse.move(5, 5)
    page.keyboard.press('f')
    framed = landed(page)
    w = screen(page, ids[1])['world']
    assert framed['target'] == pytest.approx([(w['min'][i] + w['max'][i]) / 2 for i in range(3)], abs=1)
    settled(page, lambda: page.evaluate(
        "async () => (await (await fetch('/api/project')).json()).stage3dCamera"),
        lambda v: v and v['position'] == framed['position'])
    open_tab(page, 'show-look')
    open_tab(page, '3d')
    page.wait_for_timeout(400)
    assert camera(page) == framed
    page.reload(wait_until='domcontentloaded')
    page.wait_for_timeout(2500)
    open_3d(page, 2)
    back = settled(page, lambda: camera(page),
                   lambda v: v and v['position'] == pytest.approx(framed['position'], abs=0.05))
    assert back['target'] == pytest.approx(framed['target'], abs=0.05)
    page.wait_for_timeout(800)
    assert camera(page)['position'] == pytest.approx(framed['position'], abs=0.05), 'something moved the camera after the reload'
    assert page.errors == []


# ── Delete and the right-click menu on the 3D tab ───────────────────────
# Matt, 2026-11-08: Delete and Backspace on the 3D tab do nothing (too easy
# to hit there by accident); the right-click Delete Screen stays. Previous
# and Next Port mean nothing in 3D, so the menu drops them there.

def layer_ids(page):
    return page.evaluate("window.app.project.layers.map(l => l.id).sort((a, b) => a - b)")


def menu_shows(page, action):
    return page.evaluate("""(a) => { const el = document.querySelector(`#context-menu [data-action="${a}"]`);
        return !!el && getComputedStyle(el).display !== 'none'; }""", action)


PORT_DIVIDER_JS = """() => { const el = document.querySelector('#context-menu .menu-divider.port-step-only');
    return !!el && getComputedStyle(el).display !== 'none'; }"""


def test_delete_and_backspace_on_3d_leave_the_selected_screen(page):
    ids = fresh(page)
    at = screen(page, ids[0])['at']
    page.mouse.click(*at)
    page.wait_for_timeout(300)
    assert selected(page) == [ids[0]]
    steps = history_len(page)
    for key in ('Delete', 'Backspace'):
        page.keyboard.press(key)
        page.wait_for_timeout(400)
        assert layer_ids(page) == sorted(ids), key
        assert selected(page) == [ids[0]], key
    assert history_len(page) == steps
    # Both screens selected: still nothing goes.
    page.keyboard.down('Shift')
    page.mouse.click(*screen(page, ids[1])['at'])
    page.keyboard.up('Shift')
    page.wait_for_timeout(300)
    assert selected(page) == sorted(ids)
    page.keyboard.press('Delete')
    page.wait_for_timeout(400)
    assert layer_ids(page) == sorted(ids)
    # A field keeps its own Backspace and Delete.
    page.mouse.click(*at)
    page.wait_for_timeout(300)
    page.click('#s3d-x')
    page.keyboard.press('End')
    page.keyboard.type('9')
    typed = page.input_value('#s3d-x')
    page.keyboard.press('Backspace')
    assert page.input_value('#s3d-x') == typed[:-1]
    page.keyboard.press('Home')
    page.keyboard.press('Delete')
    assert page.input_value('#s3d-x') == typed[1:-1]
    page.keyboard.press('Escape')
    page.mouse.click(5, 5)
    assert layer_ids(page) == sorted(ids)
    assert page.errors == []


def test_delete_on_pixel_map_still_deletes(page):
    ids = fresh(page)
    open_tab(page, 'pixel-map')
    page.evaluate("(id) => window.app.selectLayer(window.app.project.layers.find(l => l.id === id))", ids[1])
    page.wait_for_timeout(200)
    page.evaluate("document.activeElement && document.activeElement.blur && document.activeElement.blur()")
    page.keyboard.press('Delete')
    got = settled(page, lambda: layer_ids(page), lambda v: v == [ids[0]], 5000)
    assert got == [ids[0]], got


def test_the_3d_menu_has_no_port_steps_and_pixel_map_keeps_them(page):
    ids = fresh(page)
    at = screen(page, ids[0])['at']
    page.mouse.click(*at)
    page.wait_for_timeout(300)
    page.mouse.click(*at, button='right')
    page.wait_for_selector('#context-menu', state='visible')
    try:
        assert not menu_shows(page, 'prev-port')
        assert not menu_shows(page, 'next-port')
        assert not page.evaluate(PORT_DIVIDER_JS)
        # Delete Screen stays, without a Del key it would not answer to here.
        assert menu_shows(page, 'delete')
        assert page.inner_text('#context-menu [data-action="delete"]') == 'Delete Screen'
    finally:
        page.evaluate("window.app.hideContextMenu()")
    # Delete Screen from the menu still deletes on 3D.
    page.mouse.click(*at, button='right')
    page.wait_for_selector('#context-menu', state='visible')
    page.click('#context-menu [data-action="delete"]')
    got = settled(page, lambda: layer_ids(page), lambda v: v == [ids[1]], 5000)
    assert got == [ids[1]], got
    # Pixel Map: the two are back, with their divider and the Del key.
    open_tab(page, 'pixel-map')
    page.evaluate("(id) => window.app.selectLayer(window.app.project.layers.find(l => l.id === id))", ids[1])
    box = page.locator('#main-canvas').bounding_box()
    page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2, button='right')
    page.wait_for_selector('#context-menu', state='visible')
    try:
        assert menu_shows(page, 'prev-port') and menu_shows(page, 'next-port')
        assert page.evaluate(PORT_DIVIDER_JS)
        assert page.inner_text('#context-menu [data-action="prev-port"]').startswith('Previous Port')
        assert page.inner_text('#context-menu [data-action="delete"]').startswith('Delete Screen (')
    finally:
        page.evaluate("window.app.hideContextMenu()")
    assert page.errors == []
