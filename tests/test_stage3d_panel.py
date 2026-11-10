"""The 3D Placement panel as fields in 3D software (the owner, 2026-11-10:
"why is there so much space next to all the text boxes? also we need these
to be like real 3D software not just text boxes"), and the corners set on
the 3D tab ("it's supposed to be 90 only and can go out or in").

What this file pins (app-stage3d-panel.js):

* Position and Rotation each sit on one row: three compact fields with an
  axis tag colored as the view's arrows and rings, at the panel's narrow and
  wide widths, and no step buttons.
* A press and drag sideways changes a figure, the view following live; Shift
  steps finely, Ctrl snaps to 1 in (1 cm) or 15 degrees; the whole drag is
  one undo step, and Esc during it puts everything back. A drag down first
  gathers the next fields of the row, and the sideways drag moves them all.
  The < > arrows on hover step a figure. A click puts the caret where it
  lands, a double-click selects the figure; typing takes math, *2 and /2,
  and units; a figure that is not one goes back with a note. Enter commits
  and lets go; Esc puts the figure back; Tab and Shift+Tab go X, Y, Z,
  Pitch, Yaw, Roll; Up and Down nudge as one step; the wheel changes
  nothing. Right-click gives Reset, copy and paste of one figure or all
  three, and +90 and -90 on a rotation; each section's reset icon puts its
  figures back.
* In the view, a square between two arrows moves the selection on its
  plane, and G and R move and turn it from the keyboard: X, Y or Z locks,
  a typed figure sets it, Enter keeps it, Esc puts it back.
* A click on a seam or a panel's middle of the selected screen offers a
  corner: None, Interior 90 or Exterior 90, written to riggingCorners, the
  same data the Header/Footer tab writes, which shows it. A spot too close to
  another corner offers none.
* There is no free joint angle: the Curve (the Header/Footer tab's) is shown
  as it stands, with a link to its settings.

Run locally:
    python -m pytest tests/test_stage3d_panel.py -p no:cacheprovider
"""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from conftest import settled  # noqa: E402

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_stage3d import (  # noqa: E402
    FT, _context, dbg, history_len, open_3d, reset, screen, served, set_curve, stored, undo, view_from,
)

ONE = [{'name': 'Wall', 'columns': 6, 'rows': 2, 'offset_x': 0, 'offset_y': 0}]


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


def field(page, key):
    return page.input_value(f'#s3d-{key}')


def focused(page):
    return page.evaluate("document.activeElement && document.activeElement.id")


def centre(page, key):
    box = page.locator(f'#s3d-{key}').bounding_box()
    return box['x'] + box['width'] / 2, box['y'] + box['height'] / 2


def press_and_drag(page, key, dx, steps=10, keys=(), check=None):
    """Press on a field, drag `dx` px sideways in `steps` moves, `check()`
    while still held, then let go."""
    x, y = centre(page, key)
    page.mouse.move(x, y)
    for k in keys:
        page.keyboard.down(k)
    page.mouse.down()
    for i in range(1, steps + 1):
        page.mouse.move(x + dx * i / steps, y)
        page.wait_for_timeout(15)
    held = check() if check else None
    page.mouse.up()
    for k in keys:
        page.keyboard.up(k)
    page.wait_for_timeout(400)
    return held


def rows_of(page):
    return page.evaluate("""() => ['x', 'y', 'z', 'pitch', 'yaw', 'roll'].map(k => {
        const el = document.getElementById('s3d-' + k);
        const f = el.closest('.s3d-field');
        const r = f.getBoundingClientRect();
        const tag = f.querySelector('.s3d-tag');
        return {k, top: Math.round(r.top), w: r.width, tag: tag.textContent,
                color: getComputedStyle(tag).backgroundColor, cursor: getComputedStyle(el).cursor};
    })""")


# ── 1. one row each ───────────────────────────────────────────────────────

@pytest.mark.parametrize('width', [260, 460])
def test_the_figures_sit_on_one_row_each_at_any_panel_width(page, width):
    reset(page, ONE)
    open_3d(page, 1)
    page.evaluate(f"""() => {{
        const p = document.querySelector('.tab-panel[data-tab="3d"]');
        const side = p.closest('#left-sidebar, #right-sidebar, .lrd-panel') || p.parentElement;
        side.style.width = '{width}px';
    }}""")
    page.wait_for_timeout(200)
    rows = rows_of(page)
    pos, rot = rows[:3], rows[3:]
    assert len({r['top'] for r in pos}) == 1 and len({r['top'] for r in rot}) == 1, rows
    assert pos[0]['top'] < rot[0]['top']
    # compact: never wider than 120 px, never so narrow a figure is cut
    assert all(60 <= r['w'] <= 120 for r in rows), rows
    # the tags, colored as the move arrows and the rings
    red, green, blue = 'rgb(229, 72, 77)', 'rgb(76, 187, 90)', 'rgb(61, 126, 242)'
    assert [(r['tag'], r['color']) for r in rows] == [
        ('X', red), ('Y', green), ('Z', blue), ('P', red), ('Y', green), ('R', blue)]
    assert all(r['cursor'] == 'ew-resize' for r in rows)
    # the step buttons and the free angle fields are gone
    assert page.locator('[data-s3d-step], .s3d-steps, #s3d-curve-col, #s3d-curve-row, #s3d-joint-angle').count() == 0
    page.evaluate("""() => {
        const p = document.querySelector('.tab-panel[data-tab="3d"]');
        const side = p.closest('#left-sidebar, #right-sidebar, .lrd-panel') || p.parentElement;
        side.style.width = '';
    }""")
    assert page.errors == []


# ── 2. drag to change ─────────────────────────────────────────────────────

def test_a_drag_changes_the_figure_live_and_lands_as_one_undo_step(page):
    ids = reset(page, ONE)
    open_3d(page, 1)
    view_from(page, 'front')
    x0 = screen(page, ids[0])['placement']['x']
    box0 = screen(page, ids[0])['world']
    start = history_len(page)

    def mid_drag():
        # the view follows while the button is held; nothing is saved yet
        return {'world': screen(page, ids[0])['world'], 'stored': stored(page, ids[0]),
                'steps': history_len(page), 'field': field(page, 'x'),
                'scrubbing': page.evaluate("document.body.classList.contains('s3d-scrubbing')")}
    held = press_and_drag(page, 'x', 100, check=mid_drag)
    assert held['stored'] is None and held['steps'] == start, held
    assert held['scrubbing']
    assert held['world']['min'][0] == pytest.approx(box0['min'][0] + 100 * 25.4, abs=30), (box0, held)
    assert float(held['field']) == pytest.approx((x0 + 100 * 25.4) / FT, abs=0.1)
    # let go: one step, an inch a pixel in feet
    after = stored(page, ids[0])
    assert after['x'] - x0 == pytest.approx(100 * 25.4, abs=30)
    assert history_len(page) == start + 1
    assert focused(page) != 's3d-x', 'a drag does not leave the caret in the field'
    assert settled(page, lambda: served(page, ids[0]), lambda v: v == after) == after
    undo(page)
    assert stored(page, ids[0]) is None
    assert page.errors == []


def test_shift_steps_finely_and_ctrl_snaps(page):
    ids = reset(page, ONE)
    open_3d(page, 1)
    page.fill('#s3d-x', '1.03')
    page.press('#s3d-x', 'Enter')
    page.wait_for_timeout(300)
    x0 = stored(page, ids[0])['x']
    # Shift: a tenth of an inch a pixel
    press_and_drag(page, 'x', 100, keys=('Shift',))
    x1 = stored(page, ids[0])['x']
    assert x1 - x0 == pytest.approx(254, abs=5)
    # Ctrl: whole inches
    press_and_drag(page, 'x', 37, keys=('Control',))
    x2 = stored(page, ids[0])['x']
    assert x2 != x1 and x2 / 25.4 == pytest.approx(round(x2 / 25.4), abs=1e-6), x2
    # angles: half a degree a pixel, Ctrl snaps to 15
    press_and_drag(page, 'yaw', 40)
    assert stored(page, ids[0])['yaw'] == pytest.approx(20, abs=1)
    press_and_drag(page, 'yaw', 30, keys=('Control',))
    assert stored(page, ids[0])['yaw'] == 30
    # meters: a centimeter a pixel, Ctrl snaps to whole centimeters
    page.click('#s3d-units-m')
    page.wait_for_timeout(200)
    z0 = stored(page, ids[0])['z']
    press_and_drag(page, 'z', -50)
    assert stored(page, ids[0])['z'] - z0 == pytest.approx(-500, abs=15)
    press_and_drag(page, 'z', 7, keys=('Shift',))      # 7 mm
    press_and_drag(page, 'z', 23, keys=('Control',))   # 230 mm, to the centimeter
    z = stored(page, ids[0])['z']
    assert z - z0 == pytest.approx(-260, abs=10) and z / 10 == pytest.approx(round(z / 10), abs=1e-6), z
    page.click('#s3d-units-ft')
    assert page.errors == []


def test_esc_during_a_drag_puts_the_screen_back(page):
    ids = reset(page, ONE)
    open_3d(page, 1)
    start = history_len(page)
    box0 = screen(page, ids[0])['world']
    x, y = centre(page, 'z')
    page.mouse.move(x, y)
    page.mouse.down()
    for i in range(1, 9):
        page.mouse.move(x + 10 * i, y)
        page.wait_for_timeout(15)
    page.keyboard.press('Escape')
    page.mouse.up()
    page.wait_for_timeout(300)
    assert stored(page, ids[0]) is None and history_len(page) == start
    assert screen(page, ids[0])['world'] == box0
    assert field(page, 'z') == '0.00'


# ── 3. typing, Enter, Esc, the arrows, the wheel ──────────────────────────

def test_a_click_types_enter_commits_esc_cancels(page):
    ids = reset(page, ONE)
    open_3d(page, 1)
    start = history_len(page)
    page.dblclick('#s3d-y')
    assert focused(page) == 's3d-y', 'a click without a drag puts the caret in'
    assert page.evaluate("(() => { const e = document.getElementById('s3d-y');"
                         " return [e.selectionStart, e.selectionEnd, e.value.length]; })()") == [0, 4, 4], \
        'a double-click selects the whole figure'
    page.keyboard.type('3')
    page.keyboard.press('Enter')
    page.wait_for_timeout(400)
    assert stored(page, ids[0])['y'] == pytest.approx(3 * FT)
    assert focused(page) != 's3d-y', 'Enter ends the edit'
    assert history_len(page) == start + 1
    # Esc: the figure goes back, nothing is saved
    page.click('#s3d-y')
    page.keyboard.type('9')
    page.keyboard.press('Escape')
    page.wait_for_timeout(300)
    assert field(page, 'y') == '3.00' and focused(page) != 's3d-y'
    assert stored(page, ids[0])['y'] == pytest.approx(3 * FT)
    assert history_len(page) == start + 1
    # a figure that is not one puts the old one back, and says so
    page.fill('#s3d-y', 'abc')
    page.press('#s3d-y', 'Enter')
    page.wait_for_timeout(300)
    assert field(page, 'y') == '3.00' and history_len(page) == start + 1
    note = page.locator('[data-s3d-note="position"]')
    assert note.is_visible() and note.inner_text() == '"abc" is not a figure; Y is back to 3.00.'
    assert page.errors == []


def test_a_single_click_puts_the_caret_where_it_lands(page):
    reset(page, ONE)
    open_3d(page, 1)
    page.fill('#s3d-x', '12.5')
    page.press('#s3d-x', 'Enter')
    page.wait_for_timeout(300)
    assert field(page, 'x') == '12.50'
    box = page.locator('#s3d-x').bounding_box()
    sel_js = "(() => { const e = document.getElementById('s3d-x'); return [e.selectionStart, e.selectionEnd]; })()"
    # the middle of the figure: the caret inside it, nothing selected (the
    # step arrows take the field's first and last 12 px while it is hovered)
    page.mouse.click(box['x'] + box['width'] - 4 - 2.5 * 7, box['y'] + box['height'] / 2)
    page.wait_for_timeout(100)
    assert focused(page) == 's3d-x'
    a, b = page.evaluate(sel_js)
    assert a == b and 0 < a < 5, (a, b)
    page.keyboard.press('Escape')
    # left of the figure: the caret before its first digit
    page.mouse.click(box['x'] + 14, box['y'] + box['height'] / 2)
    page.wait_for_timeout(100)
    assert focused(page) == 's3d-x'
    assert page.evaluate(sel_js) == [0, 0]
    page.keyboard.press('Escape')
    assert field(page, 'x') == '12.50', 'the clicks stepped nothing'
    assert page.errors == []


def test_typing_takes_math_scaling_and_units(page):
    ids = reset(page, ONE)
    open_3d(page, 1)

    def put(key, text):
        page.dblclick(f'#s3d-{key}')
        page.keyboard.type(text)
        page.keyboard.press('Enter')
        page.wait_for_timeout(300)

    put('x', '16.4+2')
    assert stored(page, ids[0])['x'] == pytest.approx(18.4 * FT)
    put('x', '*2')
    assert stored(page, ids[0])['x'] == pytest.approx(36.8 * FT)
    put('x', '/4')
    assert stored(page, ids[0])['x'] == pytest.approx(9.2 * FT)
    put('x', '-1.5')
    assert stored(page, ids[0])['x'] == pytest.approx(-1.5 * FT)
    put('z', "6' 6\"")
    assert stored(page, ids[0])['z'] == pytest.approx(6 * FT + 6 * 25.4)
    put('z', '6ft 6in')
    assert stored(page, ids[0])['z'] == pytest.approx(6 * FT + 6 * 25.4)
    put('z', '2m')
    assert stored(page, ids[0])['z'] == pytest.approx(2000)
    put('z', '250mm')
    assert stored(page, ids[0])['z'] == pytest.approx(250)
    put('z', '35cm')
    assert stored(page, ids[0])['z'] == pytest.approx(350)
    put('yaw', '45*2')
    assert stored(page, ids[0])['yaw'] == 90
    # in meters, a plain figure is meters and feet still read as feet
    page.click('#s3d-units-m')
    page.wait_for_timeout(200)
    put('x', '2.5')
    assert stored(page, ids[0])['x'] == pytest.approx(2500)
    put('x', "3'")
    assert stored(page, ids[0])['x'] == pytest.approx(3 * FT)
    page.click('#s3d-units-ft')
    assert page.errors == []


def test_tab_and_shift_tab_go_through_the_six_figures(page):
    reset(page, ONE)
    open_3d(page, 1)
    page.dblclick('#s3d-x')
    seen = [focused(page)]
    for _ in range(5):
        page.keyboard.press('Tab')
        seen.append(focused(page))
    assert seen == ['s3d-x', 's3d-y', 's3d-z', 's3d-pitch', 's3d-yaw', 's3d-roll']
    back = []
    for _ in range(5):
        page.keyboard.press('Shift+Tab')
        back.append(focused(page))
    assert back == ['s3d-yaw', 's3d-pitch', 's3d-z', 's3d-y', 's3d-x']
    page.keyboard.press('Escape')


def test_the_step_arrows_show_on_hover_and_step_once_a_click(page):
    ids = reset(page, ONE)
    open_3d(page, 1)
    opacity = "(k) => getComputedStyle(document.getElementById('s3d-' + k).closest('.s3d-field').querySelector('.s3d-nudge-up')).opacity"
    page.mouse.move(5, 5)
    assert page.evaluate(opacity, 'x') == '0'
    page.hover('#s3d-x')
    assert page.evaluate(opacity, 'x') == '1'
    start = history_len(page)
    page.click('#s3d-x ~ .s3d-nudge-up')
    page.wait_for_timeout(300)
    assert stored(page, ids[0])['x'] == pytest.approx(screen(page, ids[0])['placement']['x'])
    x1 = stored(page, ids[0])['x']
    page.click('#s3d-x ~ .s3d-nudge-up')
    page.wait_for_timeout(300)
    assert stored(page, ids[0])['x'] - x1 == pytest.approx(25.4)
    assert focused(page) != 's3d-x', 'a step does not put the caret in'
    page.hover('#s3d-yaw')
    page.click('.s3d-field:has(#s3d-yaw) .s3d-nudge-dn')
    page.wait_for_timeout(300)
    assert stored(page, ids[0])['yaw'] == -1
    assert history_len(page) == start + 3
    assert page.errors == []


def test_a_drag_down_then_sideways_moves_every_field_it_crossed(page):
    ids = reset(page, ONE)
    open_3d(page, 1)
    before = screen(page, ids[0])['placement']
    start = history_len(page)
    x, y = centre(page, 'x')
    page.mouse.move(x, y)
    page.mouse.down()
    for i in range(1, 7):                     # down two fields' worth: Y and Z
        page.mouse.move(x, y + 8 * i)
        page.wait_for_timeout(15)
    gathered = page.evaluate("[...document.querySelectorAll('.s3d-field.s3d-gathered input')].map(e => e.id)")
    assert gathered == ['s3d-x', 's3d-y', 's3d-z']
    for i in range(1, 11):
        page.mouse.move(x + 4 * i, y + 48)
        page.wait_for_timeout(15)
    page.mouse.up()
    page.wait_for_timeout(400)
    after = stored(page, ids[0])
    for k in ('x', 'y', 'z'):
        assert after[k] - before[k] == pytest.approx(40 * 25.4, abs=1e-6), (k, before, after)
    assert history_len(page) == start + 1
    assert page.evaluate("document.querySelectorAll('.s3d-gathered').length") == 0
    # from Roll, a drag UP gathers Yaw too (and Pitch stays out), and Esc
    # puts both back with no undo step
    x, y = centre(page, 'roll')
    page.mouse.move(x, y)
    page.mouse.down()
    for i in range(1, 4):
        page.mouse.move(x, y - 8 * i)
        page.wait_for_timeout(15)
    gathered = page.evaluate("[...document.querySelectorAll('.s3d-field.s3d-gathered input')].map(e => e.id)")
    assert gathered == ['s3d-yaw', 's3d-roll']
    for i in range(1, 6):
        page.mouse.move(x + 6 * i, y - 24)
        page.wait_for_timeout(15)
    assert float(field(page, 'yaw')) == pytest.approx(15) and float(field(page, 'roll')) == pytest.approx(15)
    page.keyboard.press('Escape')
    page.mouse.up()
    page.wait_for_timeout(300)
    assert stored(page, ids[0]) == after and history_len(page) == start + 1
    assert field(page, 'yaw') == '0' and field(page, 'roll') == '0'
    assert page.errors == []


def test_up_and_down_nudge_as_one_step_and_the_wheel_does_nothing(page):
    ids = reset(page, ONE)
    open_3d(page, 1)
    start = history_len(page)
    page.click('#s3d-z')
    for _ in range(3):
        page.keyboard.press('ArrowUp')
    page.keyboard.press('Shift+ArrowDown')
    page.wait_for_timeout(200)
    # the view follows, nothing saved while the field holds the caret
    assert stored(page, ids[0]) is None and history_len(page) == start
    page.keyboard.press('Enter')
    page.wait_for_timeout(400)
    assert stored(page, ids[0])['z'] == pytest.approx(3 * 25.4 - 2.54, abs=1e-6)
    assert history_len(page) == start + 1
    # Ctrl+Up: a 15 degree step
    page.click('#s3d-roll')
    page.keyboard.press('Control+ArrowUp')
    page.keyboard.press('Enter')
    page.wait_for_timeout(400)
    assert stored(page, ids[0])['roll'] == 15
    # the wheel over a field, focused or not, changes nothing
    before = stored(page, ids[0])
    x, y = centre(page, 'x')
    page.mouse.move(x, y)
    page.mouse.wheel(0, -300)
    page.click('#s3d-x')
    page.mouse.wheel(0, 300)
    page.keyboard.press('Escape')
    page.wait_for_timeout(300)
    assert stored(page, ids[0]) == before
    assert page.errors == []


def menu_items(page):
    return page.evaluate("[...document.querySelectorAll('#s3d-field-menu [data-s3d-menu]')].map(b => b.textContent)")


def menu_pick(page, key, item):
    page.click(f'#s3d-{key}', button='right')
    page.click(f'#s3d-field-menu [data-s3d-menu="{item}"]')
    page.wait_for_timeout(300)


def test_the_right_click_menu_copies_and_pastes_one_figure_or_all_three(page):
    ids = reset(page, ONE)
    open_3d(page, 1)
    home = screen(page, ids[0])['placement']
    page.click('#s3d-x', button='right')
    assert menu_items(page) == ['Reset', 'Copy value', 'Paste value', 'Copy all three', 'Paste all three']
    # nothing copied yet: Paste is grayed out
    assert page.evaluate("document.querySelector('#s3d-field-menu [data-s3d-menu=\"paste\"]').disabled")
    page.keyboard.press('Escape')
    page.fill('#s3d-x', '7')
    page.press('#s3d-x', 'Enter')
    page.wait_for_timeout(300)
    menu_pick(page, 'x', 'copy')
    start = history_len(page)
    menu_pick(page, 'z', 'paste')
    assert stored(page, ids[0])['z'] == pytest.approx(7 * FT)
    assert history_len(page) == start + 1
    # all three: copied, changed, pasted back in one step
    menu_pick(page, 'y', 'copy-all')
    want = stored(page, ids[0])
    page.fill('#s3d-x', '1')
    page.press('#s3d-x', 'Enter')
    page.fill('#s3d-y', '2')
    page.press('#s3d-y', 'Enter')
    page.wait_for_timeout(300)
    start = history_len(page)
    menu_pick(page, 'z', 'paste-all')
    got = stored(page, ids[0])
    assert (got['x'], got['y'], got['z']) == pytest.approx((want['x'], want['y'], want['z']), abs=0.5)
    assert history_len(page) == start + 1
    # a length copied never pastes into an angle
    page.click('#s3d-roll', button='right')
    assert page.evaluate("document.querySelector('#s3d-field-menu [data-s3d-menu=\"paste\"]').disabled")
    page.keyboard.press('Escape')
    # Reset puts that one figure back where Show Look stands it, the others kept
    kept = stored(page, ids[0])
    menu_pick(page, 'x', 'reset')
    got = stored(page, ids[0])
    assert got['x'] == pytest.approx(home['x'], abs=0.01)
    assert (got['y'], got['z']) == pytest.approx((kept['y'], kept['z']), abs=0.01)
    assert page.errors == []


def test_the_rotation_menu_and_the_reset_icons(page):
    ids = reset(page, ONE)
    open_3d(page, 1)
    page.click('#s3d-yaw', button='right')
    items = menu_items(page)
    assert items == ['Reset', 'Copy value', 'Paste value', 'Copy all three', 'Paste all three', '+90°', '-90°']
    page.click('#s3d-field-menu [data-s3d-menu="+90"]')
    page.wait_for_timeout(300)
    assert stored(page, ids[0])['yaw'] == 90
    assert page.locator('#s3d-field-menu').count() == 0
    page.click('#s3d-yaw', button='right')
    page.click('#s3d-field-menu [data-s3d-menu="reset"]')
    page.wait_for_timeout(300)
    assert stored(page, ids[0])['yaw'] == 0
    # Esc closes the menu with nothing changed
    page.click('#s3d-pitch', button='right')
    page.keyboard.press('Escape')
    assert page.locator('#s3d-field-menu').count() == 0
    # the reset icons: Position back to Show Look, the rotation kept; then
    # Rotation upright, the position kept
    home = screen(page, ids[0])['placement']
    page.fill('#s3d-x', '12')
    page.press('#s3d-x', 'Enter')
    page.fill('#s3d-pitch', '30')
    page.press('#s3d-pitch', 'Enter')
    page.wait_for_timeout(300)
    start = history_len(page)
    page.click('#s3d-reset-position')
    page.wait_for_timeout(300)
    p = stored(page, ids[0])
    assert (p['x'], p['y'], p['z']) == pytest.approx((home['x'], home['y'], home['z']), abs=0.01)
    assert p['pitch'] == 30
    page.click('#s3d-reset-rotation')
    page.wait_for_timeout(300)
    p = stored(page, ids[0])
    assert (p['pitch'], p['yaw'], p['roll']) == (0, 0, 0)
    assert (p['x'], p['y'], p['z']) == pytest.approx((home['x'], home['y'], home['z']), abs=0.01)
    assert history_len(page) == start + 2
    assert page.errors == []


# ── 4. corners picked in the view ─────────────────────────────────────────

def corners_of(page, layer_id):
    return page.evaluate(f"""() => (window.app.project.layers.find(l => l.id === {layer_id}).riggingCorners || [])
        .map(c => ({{at: c.at, side: c.side, angle: c.angle}}))""")


def click_spot(page, layer_id, at):
    pt = page.evaluate(f"window.app._s3dDebugSpot({layer_id}, {at})")
    assert pt, f'spot {at} is not in the view'
    page.mouse.click(pt[0], pt[1])
    page.wait_for_timeout(300)
    return pt


def pop_open(page):
    return page.evaluate("!document.getElementById('s3d-corner-pop').hidden")


def test_a_corner_picked_in_the_view_is_the_header_footer_tabs_corner(page):
    ids = reset(page, ONE)
    wall = ids[0]
    open_3d(page, 1)
    view_from(page, 'front')
    start = history_len(page)
    # the seam between panels 3 and 4
    click_spot(page, wall, 3.5)
    assert pop_open(page)
    assert dbg(page)['corner'] == {'layerId': wall, 'at': 3.5}
    assert page.inner_text('#s3d-corner-pop-title') == 'Corner, between panels 3 and 4'
    assert page.evaluate("[...document.querySelectorAll('#s3d-corner-pop [data-s3d-corner]')].map(b => b.textContent)") \
        == ['None', 'Interior 90°', 'Exterior 90°']
    assert page.evaluate("document.querySelector('#s3d-corner-pop [data-s3d-corner=\"none\"]').classList.contains('active')")
    page.click('#s3d-corner-pop [data-s3d-corner="interior"]')
    got = settled(page, lambda: corners_of(page, wall), lambda v: len(v) == 1)
    assert got == [{'at': 3.5, 'side': 'interior', 'angle': 90}]
    assert not pop_open(page)
    assert history_len(page) == start + 1
    served_corners = settled(page, lambda: page.evaluate(f"""async () => ((await (await fetch('/api/project'))
        .json()).layers.find(l => l.id === {wall}).riggingCorners || []).map(c => [c.at, c.side])"""),
        lambda v: v == [[3.5, 'interior']])
    assert served_corners == [[3.5, 'interior']]
    # the stage folds: the ends come toward the audience
    s = settled(page, lambda: screen(page, wall), lambda v: v['world']['max'][2] > 500)
    assert s['world']['max'][2] > 500
    assert page.inner_text('#s3d-corner-info') == 'Between panels 3 and 4: Interior 90°'
    # a panel's middle, then Exterior: the same rows on the Header/Footer tab
    click_spot(page, wall, 6)
    assert page.inner_text('#s3d-corner-pop-title') == 'Corner, middle of panel 6'
    page.click('#s3d-corner-pop [data-s3d-corner="exterior"]')
    got = settled(page, lambda: corners_of(page, wall), lambda v: len(v) == 2)
    assert got == [{'at': 3.5, 'side': 'interior', 'angle': 90}, {'at': 6, 'side': 'exterior', 'angle': 90}]
    page.click('#view-tabs .view-tab[data-mode="rigging"]')
    page.wait_for_timeout(300)
    rows = page.evaluate("""() => [...document.querySelectorAll('#rigging-corner-list [data-corner]')].map(r => [
        Number(r.dataset.corner), r.querySelector('[data-corner-side].active').dataset.cornerSide])""")
    assert rows == [[3.5, 'interior'], [6, 'exterior']]
    # back on 3D: the seam picked again shows its side, and None takes it off
    open_3d(page, 1)
    view_from(page, 'front')
    click_spot(page, wall, 3.5)
    assert page.evaluate("document.querySelector('#s3d-corner-pop [data-s3d-corner=\"interior\"]').classList.contains('active')")
    page.click('#s3d-corner-pop [data-s3d-corner="exterior"]')
    assert settled(page, lambda: corners_of(page, wall), lambda v: v and v[0]['side'] == 'exterior')[0]['side'] == 'exterior'
    click_spot(page, wall, 3.5)
    page.click('#s3d-corner-pop [data-s3d-corner="none"]')
    got = settled(page, lambda: corners_of(page, wall), lambda v: len(v) == 1)
    assert got == [{'at': 6, 'side': 'exterior', 'angle': 90}]
    assert history_len(page) == start + 4
    undo(page)
    assert [c['at'] for c in corners_of(page, wall)] == [3.5, 6]
    assert page.errors == []


def test_a_spot_too_close_to_a_corner_offers_none_and_esc_closes(page):
    ids = reset(page, ONE)
    wall = ids[0]
    page.evaluate(f"""() => {{ const a = window.app; const l = a.project.layers.find(x => x.id === {wall});
        l.riggingCorners = [{{at: 3.5, angle: 90, side: 'interior'}}]; a.updateLayers([l], true, 'Test Corner'); }}""")
    open_3d(page, 1)
    view_from(page, 'front')
    start = history_len(page)
    # the middle of panel 4 sits under the 3.5 corner's bar
    click_spot(page, wall, 4)
    assert pop_open(page)
    assert page.evaluate("""() => [...document.querySelectorAll('#s3d-corner-pop [data-s3d-corner]')]
        .map(b => b.disabled)""") == [False, True, True]
    assert 'Too close to another corner' in page.inner_text('#s3d-corner-pop-note')
    page.keyboard.press('Escape')
    assert not pop_open(page)
    assert dbg(page)['corner'] is None
    # a click away from any seam or middle offers nothing
    pt = page.evaluate(f"window.app._s3dDebugSpot({wall}, 2)")
    box = page.evaluate(f"window.app._s3dDebugSpot({wall}, 2.5)")
    page.mouse.click((pt[0] + box[0]) / 2 + 8, pt[1])
    page.wait_for_timeout(300)
    assert not pop_open(page)
    assert history_len(page) == start
    assert page.errors == []


def test_a_locked_screen_refuses_a_corner(page):
    ids = reset(page, ONE)
    wall = ids[0]
    page.evaluate(f"""() => {{ const a = window.app; const l = a.project.layers.find(x => x.id === {wall});
        l.locked = true; a.updateLayers([l], true, 'Lock'); }}""")
    open_3d(page, 1)
    view_from(page, 'front')
    start = history_len(page)
    click_spot(page, wall, 2.5)
    page.click('#s3d-corner-pop [data-s3d-corner="interior"]')
    said = settled(page, lambda: page.inner_text('#app-toast-host'), lambda t: 'is locked' in t, 3000)
    assert 'Wall is locked' in said
    assert corners_of(page, wall) == [] and history_len(page) == start


# ── 5. the Curve, shown; no free joint angle ──────────────────────────────

def test_the_curve_is_shown_as_it_stands_with_a_link_to_its_settings(page):
    ids = reset(page, ONE)
    open_3d(page, 1)
    assert page.inner_text('#s3d-curve-info').startswith('No curve.')
    set_curve(page, ids[0], 7.5)
    text = settled(page, lambda: page.inner_text('#s3d-curve-info'), lambda t: t.startswith('Curve:'))
    assert text == 'Curve: 7.5° per joint, concave, 37.5° in all.'
    # the stage bends by the Curve's angles
    s = settled(page, lambda: screen(page, ids[0]), lambda v: v['world']['max'][2] > 100)
    assert s['world']['max'][2] > 100
    # a corner's seam takes no curve angle
    page.evaluate(f"""() => {{ const a = window.app; const l = a.project.layers.find(x => x.id === {ids[0]});
        l.riggingCorners = [{{at: 3.5, angle: 90, side: 'interior'}}]; a.updateLayers([l], true, 'Test Corner'); }}""")
    text = settled(page, lambda: page.inner_text('#s3d-curve-info'), lambda t: '30°' in t)
    assert text == 'Curve: 7.5° per joint, concave, 30° in all.'
    page.click('#s3d-curve-edit')
    page.wait_for_timeout(400)
    assert page.evaluate("document.querySelector('#view-tabs .view-tab.active').dataset.mode") == 'rigging'
    assert page.evaluate("getComputedStyle(document.getElementById('rigging-curve')).display") != 'none'
    assert page.errors == []


# ── 6. in the view: the plane squares, and G and R ───────────────────────

def test_a_square_between_two_arrows_moves_on_its_plane_in_one_step(page):
    ids = reset(page, ONE)
    open_3d(page, 1)
    view_from(page, 'iso')
    page.click('#s3d-tool-move')
    h = settled(page, lambda: page.evaluate('window.app._s3dHandlesDebug()'),
                lambda v: v and v.get('shown') and v['grips'].get('xz'), 4000)
    assert set(h['grips']) >= {'x', 'y', 'z', 'xy', 'xz', 'yz'}, h['grips']
    before = screen(page, ids[0])['placement']
    start = history_len(page)
    def drag(grip, dx, dy):
        gx, gy = grip
        page.mouse.move(gx, gy)
        page.mouse.down()
        for i in range(1, 11):
            page.mouse.move(gx + dx * i / 10, gy + dy * i / 10)
            page.wait_for_timeout(20)
        page.mouse.up()
        page.wait_for_timeout(400)
    drag(h['grips']['xz'], 30, 60)
    after = stored(page, ids[0])
    assert after, 'the square moved nothing'
    assert after['y'] == pytest.approx(before['y'], abs=0.01), 'the floor square keeps the height'
    assert math.hypot(after['x'] - before['x'], after['z'] - before['z']) > 100, (before, after)
    assert history_len(page) == start + 1
    # the XY square keeps the depth
    h = settled(page, lambda: page.evaluate('window.app._s3dHandlesDebug()'),
                lambda v: v and v.get('shown') and v['grips'].get('xy'), 4000)
    drag(h['grips']['xy'], 40, -40)
    again = stored(page, ids[0])
    assert again['z'] == pytest.approx(after['z'], abs=0.01)
    assert math.hypot(again['x'] - after['x'], again['y'] - after['y']) > 100, (after, again)
    assert history_len(page) == start + 2
    undo(page)
    undo(page)
    assert stored(page, ids[0]) is None
    assert page.errors == []


def _view_point(page):
    box = page.locator('#s3d-view canvas').bounding_box()
    return box['x'] + box['width'] * 0.3, box['y'] + box['height'] * 0.7


def test_g_moves_with_the_mouse_x_locks_a_typed_figure_sets_it(page):
    ids = reset(page, ONE)
    open_3d(page, 1)
    view_from(page, 'front')
    before = screen(page, ids[0])['placement']
    box0 = screen(page, ids[0])['world']
    start = history_len(page)
    x, y = _view_point(page)
    page.mouse.move(x, y)
    page.keyboard.press('g')
    # the mouse moves it, no button held, nothing saved yet
    for i in range(1, 6):
        page.mouse.move(x + 20 * i, y)
        page.wait_for_timeout(20)
    moved = screen(page, ids[0])['world']
    assert moved['min'][0] > box0['min'][0] + 10, (box0, moved)
    assert stored(page, ids[0]) is None and history_len(page) == start
    assert 'Move free' in page.evaluate("document.getElementById('s3d-readout').textContent")
    # Esc puts it back, no undo step
    page.keyboard.press('Escape')
    page.wait_for_timeout(200)
    assert screen(page, ids[0])['world'] == box0 and history_len(page) == start
    # G, Z locks the axis, 2 typed, Enter: exactly 2 ft toward the audience
    page.keyboard.press('g')
    page.keyboard.press('z')
    page.keyboard.type('2')
    page.mouse.move(x + 200, y - 100)          # the typed figure holds
    page.keyboard.press('Enter')
    page.wait_for_timeout(400)
    after = stored(page, ids[0])
    assert (after['x'], after['y'], after['z']) == pytest.approx((before['x'], before['y'], before['z'] + 2 * FT), abs=0.01)
    assert history_len(page) == start + 1
    # a figure with no axis locked goes along X
    page.keyboard.press('g')
    page.keyboard.type('-1.5')
    page.keyboard.press('Enter')
    page.wait_for_timeout(400)
    assert stored(page, ids[0])['x'] == pytest.approx(before['x'] - 1.5 * FT, abs=0.01)
    assert history_len(page) == start + 2
    assert page.errors == []


def test_r_turns_a_locked_angle_by_a_typed_figure_and_a_click_keeps_it(page):
    ids = reset(page, ONE)
    open_3d(page, 1)
    view_from(page, 'front')
    start = history_len(page)
    x, y = _view_point(page)
    page.mouse.move(x, y)
    page.keyboard.press('r')
    page.keyboard.press('x')                   # pitch
    page.keyboard.type('30')
    page.mouse.down()                          # a click keeps it
    page.mouse.up()
    page.wait_for_timeout(400)
    p = stored(page, ids[0])
    assert p['pitch'] == pytest.approx(30) and p['yaw'] == 0 and p['roll'] == 0
    assert history_len(page) == start + 1
    # R unlocked turns the yaw with sideways travel; a right-click puts it back
    page.keyboard.press('r')
    for i in range(1, 6):
        page.mouse.move(x + 15 * i, y)
        page.wait_for_timeout(20)
    page.mouse.click(x + 75, y, button='right')
    page.wait_for_timeout(300)
    assert stored(page, ids[0]) == p and history_len(page) == start + 1
    # the keys are the view's only: typed into a field, g and r are text
    page.dblclick('#s3d-x')
    page.keyboard.type('g')
    assert field(page, 'x') == 'g'
    page.keyboard.press('Escape')
    assert dbg(page)['handles'] is not None and page.evaluate('!window.app._s3d.keyX')
    assert page.errors == []
