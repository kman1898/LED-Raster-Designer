"""One screen of a group, picked in the Screens list, moves alone in 3D too.

A user asked to move one screen of a group in 3D without ungrouping it. On
Pixel Map and Show Look, opening the group in the Screens list and clicking
one of its screens already moves that screen alone, with a note saying so
(tests/test_group_member_moves_alone.py). 3D ignored that pick and moved the
whole group as one.

The owner's ruling (2026-11-24): 3D follows the list pick, with the same
gesture. While one member is picked alone in the Screens list, 3D's X / Y /
Z, its turn and its drag move ONLY that screen, and the panel says so in
the 2D note's words. A click on the wall in the view picks the whole group
again. The default stays rigid.

A group that curves as one wall (the Header/Footer Curve, 2026-11-17) is
refused (the owner, 2026-11-24, "refuse, say why"): its screens are chained
along one Curve, so a member picked alone cannot move or turn on its own.
The note says so up front; a field edit or a drag says why in a red toast,
naming the way out, and moves nothing.

What this file pins, each through the gestures that follow it:

* Typed fields and the rotation menu move only the picked member; the
  handles sit on it alone; one undo step each, undo and redo.
* A drag in the view and the arrow keys move only it.
* A click on the wall ends the pick: the note reads the group's again and
  a typed figure moves every member rigidly.
* Save, reload and a second page joined live show the member where it was
  moved, and the rest of the group where it stood.
* The member's header bars and corners ride with it; the OBJ export
  writes it where it stands, the others unchanged.
* A curved group refuses, says why and changes nothing; a click on the
  wall then moves it whole.

Run locally:
    python -m pytest tests/test_stage3d_member_alone.py -n 4 --dist loadfile
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from conftest import settled  # noqa: E402

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_curve_obj import (  # noqa: E402
    act, group_two, open_rigging, reset as curve_reset, singles_only,
)
from test_stage3d import (  # noqa: E402
    FT, _context, bars_of, dbg, history_len, open_3d, redo, reset, rotation_menu, screen, served, set_bars,
    stored, type_field, undo, view_from,
)


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project exactly as this module found it
    (see conftest.server_project_guard)."""


def _open(context, url):
    pg = context.new_page()
    pg.errors = []
    pg.on('pageerror', lambda err: pg.errors.append(str(err)))
    pg.goto(url, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)
    pg.wait_for_timeout(1500)
    return pg


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = _context(pw_browser)
    pg = _open(context, e2e_server)
    pg.route('**/api/native-dialog/**', lambda r: r.fulfill(status=503, body='{}'))
    pg.e2e_server = e2e_server
    yield pg
    context.close()


# Three 2 x 2 screens standing edge to edge (128 px, 500 mm cabinets).
ROW = [{'name': n, 'columns': 2, 'rows': 2, 'offset_x': i * 256, 'offset_y': 0}
       for i, n in enumerate(('Left', 'Middle', 'Right'))]

# The same wall wider, for the Curve: three 4 x 2 screens edge to edge.
CURVED = [{'name': n, 'columns': 4, 'rows': 2, 'offset_x': i * 512, 'offset_y': 0}
          for i, n in enumerate(('C1', 'C2', 'C3'))]


# ── gestures ─────────────────────────────────────────────────────────────

def make_wall(page, specs=ROW, curve_locks=False):
    ids = curve_reset(page, specs) if curve_locks else reset(page, specs)
    group_two(page, ids)
    page.evaluate(f"window.app.selectLayer(window.app.project.layers.find(l => l.id === {ids[0]}))")
    page.wait_for_timeout(200)
    return ids


def list_pick(page, layer_id):
    """A plain click on the screen's own row in the opened group."""
    gid = page.evaluate(f"window.app.project.layers.find(l => l.id === {layer_id}).group_id")
    page.evaluate(f"() => {{ window.app.setGroupExpanded({json.dumps(gid)}, true); window.app.renderLayers(); }}")
    page.locator(f'#layers-list .layer-item[data-layer-id="{layer_id}"]').click()
    assert settled(page, lambda: picked(page), lambda v: v == layer_id, 3000) == layer_id
    page.wait_for_timeout(300)


def picked(page):
    return page.evaluate("() => { const l = window.app._listPickedMember(); return l ? l.id : null; }")


def click_on_stage(page, layer_id):
    at = screen(page, layer_id)['at']
    page.mouse.click(at[0], at[1])
    page.wait_for_timeout(400)


def drag_on_stage(page, layer_id, dx):
    at = screen(page, layer_id)['at']
    page.mouse.move(at[0], at[1])
    page.mouse.down()
    for step in range(1, 9):
        page.mouse.move(at[0] + step * dx / 8, at[1])
        page.wait_for_timeout(20)
    page.mouse.up()
    page.wait_for_timeout(500)


# ── reads ────────────────────────────────────────────────────────────────

def note(page):
    """(text, shown, kind) of the note under the 3D panel's name."""
    return page.evaluate("""() => { const el = document.getElementById('s3d-group-note');
        return [el.textContent, !el.hidden && el.offsetParent !== null, el.dataset.groupMove || '']; }""")


def placements(page, ids):
    return [screen(page, i)['placement'] for i in ids]


def toast_text(page):
    return page.evaluate("(() => { const h = document.getElementById('app-toast-host'); return h ? h.innerText : ''; })()")


def clear_toasts(page):
    page.evaluate("(() => { const h = document.getElementById('app-toast-host'); if (h) h.innerHTML = ''; })()")


def handle_ids(page):
    h = settled(page, lambda: dbg(page)['handles'], lambda v: v and v['shown'], 3000)
    return sorted(h['ids'])


# ── the fields ───────────────────────────────────────────────────────────

def test_typed_figures_and_a_turn_move_only_the_picked_member(page):
    left, mid, right = make_wall(page)
    open_3d(page, 3)
    page.click('#s3d-tool-move')
    # picked on the stage, the whole group moves (the default)
    click_on_stage(page, mid)
    text, shown, kind = note(page)
    assert shown and kind == 'group' and text.startswith('Moves and turns with its group'), text
    assert handle_ids(page) == sorted([left, mid, right])

    list_pick(page, mid)
    text, shown, kind = note(page)
    assert shown and kind == 'one', (text, kind)
    assert text.startswith('Moves only Middle in its group'), text
    assert '—' not in text and '–' not in text
    # the handles sit on the picked screen alone
    assert settled(page, lambda: handle_ids(page), lambda v: v == [mid], 3000) == [mid]

    others = placements(page, [left, right])
    steps = history_len(page)
    type_field(page, 's3d-x', '12')
    m = stored(page, mid)
    assert m and m['x'] == pytest.approx(12 * FT), m
    assert stored(page, left) is None and stored(page, right) is None
    assert placements(page, [left, right]) == others
    assert history_len(page) == steps + 1
    # still picked: the next figure and a turn move it alone too
    assert picked(page) == mid
    type_field(page, 's3d-z', '-3')
    rotation_menu(page, 'yaw', '+90')
    m = stored(page, mid)
    assert m['z'] == pytest.approx(-3 * FT) and m['yaw'] == 90, m
    assert stored(page, left) is None and stored(page, right) is None
    assert placements(page, [left, right]) == others
    assert history_len(page) == steps + 3
    want = m
    assert settled(page, lambda: served(page, mid), lambda v: v == want) == want
    assert served(page, left) is None and served(page, right) is None

    # one undo a step, the others untouched throughout
    undo(page)
    assert stored(page, mid)['yaw'] == 0
    undo(page)
    undo(page)
    assert not stored(page, mid)
    assert settled(page, lambda: served(page, mid), lambda v: not v) in (None, {})
    redo(page)
    redo(page)
    redo(page)
    assert stored(page, mid) == want
    assert stored(page, left) is None and stored(page, right) is None
    assert settled(page, lambda: served(page, mid), lambda v: v == want) == want
    assert page.errors == []


def test_a_drag_and_the_arrow_keys_move_only_the_picked_member(page):
    left, mid, right = make_wall(page)
    open_3d(page, 3)
    view_from(page, 'top')
    list_pick(page, mid)
    before = screen(page, mid)['placement']
    others = placements(page, [left, right])
    steps = history_len(page)
    drag_on_stage(page, mid, 80)
    m = stored(page, mid)
    assert m and m['x'] > before['x'] + 50, (before, m)
    assert stored(page, left) is None and stored(page, right) is None
    assert placements(page, [left, right]) == others
    assert history_len(page) == steps + 1
    # a drag is no click: the pick holds
    assert picked(page) == mid

    page.mouse.move(5, 5)
    for _ in range(2):
        page.keyboard.press('ArrowRight')
    got = settled(page, lambda: stored(page, mid), lambda v: v and v['x'] == pytest.approx(m['x'] + 2 * 25.4, abs=0.01), 3000)
    assert got['x'] == pytest.approx(m['x'] + 2 * 25.4, abs=0.01)
    assert stored(page, left) is None and stored(page, right) is None
    assert history_len(page) == steps + 2
    undo(page)
    undo(page)
    assert not stored(page, mid)
    assert page.errors == []


def test_a_click_on_the_wall_moves_the_whole_group_again(page):
    left, mid, right = make_wall(page)
    open_3d(page, 3)
    list_pick(page, mid)
    assert note(page)[2] == 'one'
    click_on_stage(page, mid)
    assert picked(page) is None
    text, shown, kind = note(page)
    assert shown and kind == 'group', (text, kind)
    assert settled(page, lambda: handle_ids(page), lambda v: v == sorted([left, mid, right]), 3000) \
        == sorted([left, mid, right])
    a0, b0, c0 = placements(page, [left, mid, right])
    type_field(page, 's3d-z', '4')
    a, b, c = (stored(page, i) for i in (left, mid, right))
    assert a and b and c
    for p in (a, b, c):
        assert p['z'] == pytest.approx(4 * FT)
    assert b['x'] - a['x'] == pytest.approx(b0['x'] - a0['x'])
    assert c['x'] - b['x'] == pytest.approx(c0['x'] - b0['x'])
    assert page.errors == []


# ── it stays where it was put ────────────────────────────────────────────

def test_save_reload_and_a_second_page_show_the_member_where_it_was_moved(page, pw_browser):
    left, mid, right = make_wall(page)
    open_3d(page, 3)
    other_ctx = _context(pw_browser)
    other = _open(other_ctx, page.e2e_server)
    try:
        other.click('#view-tabs .view-tab[data-mode="3d"]')
        list_pick(page, mid)
        type_field(page, 's3d-x', '9')
        type_field(page, 's3d-y', '2')
        want = stored(page, mid)
        assert want['x'] == pytest.approx(9 * FT) and want['y'] == pytest.approx(2 * FT)
        assert settled(page, lambda: served(page, mid), lambda v: v == want) == want
        # the second page follows without writing
        theirs = settled(other, lambda: other.evaluate(
            f"(window.app.project.layers.find(l => l.id === {mid}) || {{}}).stage3d || null"),
            lambda v: v == want, 6000)
        assert theirs == want
        on_stage = settled(other, lambda: screen(other, mid), lambda s: s and s['placement'] == want, 6000)
        assert on_stage['placement'] == want
        assert other.evaluate(f"""() => [{left}, {right}].map(id =>
            window.app.project.layers.find(l => l.id === id).stage3d || null)""") == [None, None]
        assert other.errors == []
    finally:
        other_ctx.close()

    others = placements(page, [left, right])
    page.reload(wait_until='domcontentloaded')
    page.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)
    page.wait_for_timeout(1500)
    assert stored(page, mid) == want
    assert stored(page, left) is None and stored(page, right) is None
    open_3d(page, 3)
    assert screen(page, mid)['placement'] == want
    assert placements(page, [left, right]) == others
    assert page.errors == []


def test_bars_corners_and_the_obj_follow_the_member(page):
    left, mid, right = make_wall(page)
    set_bars(page, left, [2], [])
    set_bars(page, mid, [2], [])
    set_bars(page, right, [2], [])
    page.evaluate(f"""() => {{ const a = window.app;
        a.setRiggingCornerAt(a.project.layers.find(l => l.id === {mid}), 1, 'exterior'); }}""")
    page.wait_for_timeout(400)
    open_3d(page, 3)
    corners = page.evaluate(f"""() => [{left}, {mid}, {right}].map(id => window.app.project.layers.find(l => l.id === id))
        .map(l => (l.riggingCorners || []).map(c => [c.at, c.side]))""")
    assert corners == [[], [[1, 'exterior']], []]
    obj_before = page.evaluate(f"""() => [{left}, {mid}, {right}].map(id =>
        window.app.objFacesOf(window.app.project.layers.find(l => l.id === id), {{w: 1920, h: 1080}}))""")
    world_before = {i: screen(page, i)['world'] for i in (left, right)}
    bars_before = {i: bars_of(page, i)['header'] for i in (left, mid, right)}

    list_pick(page, mid)
    type_field(page, 's3d-z', '6')
    m = stored(page, mid)
    assert m['z'] == pytest.approx(6 * FT)
    # the corner is its own still, the others' none
    assert page.evaluate(f"""() => [{left}, {mid}, {right}].map(id => window.app.project.layers.find(l => l.id === id))
        .map(l => (l.riggingCorners || []).map(c => [c.at, c.side]))""") == corners
    # its header rides with it, in its own frame, unchanged; the others' bars
    # and the others themselves stand where they stood
    s = settled(page, lambda: screen(page, mid), lambda v: v['placement'] == m)
    assert bars_of(page, mid)['header']['first'] == bars_before[mid]['first']
    assert bars_of(page, mid)['header']['shown']
    for i in (left, right):
        assert bars_of(page, i)['header'] == bars_before[i]
        assert screen(page, i)['world'] == world_before[i]
    assert s['world']['max'][2] > world_before[left]['max'][2] + 6 * FT - 1
    # the OBJ writes the member where it stands now, the others as before
    obj_after = page.evaluate(f"""() => [{left}, {mid}, {right}].map(id =>
        window.app.objFacesOf(window.app.project.layers.find(l => l.id === id), {{w: 1920, h: 1080}}))""")
    assert obj_after[0] == obj_before[0] and obj_after[2] == obj_before[2]
    moved = [c[2] - b[2] for fa, fb in zip(obj_after[1], obj_before[1])
             for c, b in zip(fa['corners'], fb['corners'])]
    assert all(d == pytest.approx(6 * FT / 1000, abs=1e-6) for d in moved), moved[:4]
    assert page.errors == []


# ── a curved wall holds its screens together ─────────────────────────────

def test_a_curved_group_refuses_to_move_one_member_and_says_why(page):
    ids = make_wall(page, CURVED, curve_locks=True)
    c1, c2, c3 = ids
    open_rigging(page)
    page.evaluate(f"window.app.setSelectedLayersByIds([{c2}], {c2})")
    page.evaluate("window.app.refreshRiggingPanel()")
    singles_only(page)
    act(page, lambda: page.check('#rigging-curve-on'))
    assert all((page.evaluate(f"window.app.project.layers.find(l => l.id === {i}).riggingCurve") or {}).get('on')
               for i in ids)
    open_3d(page, 3)
    page.click('#s3d-tool-move')
    list_pick(page, c2)
    text, shown, kind = note(page)
    assert shown and kind == 'held', (text, kind)
    assert 'curves as one wall, so C2 cannot move or turn on its own' in text, text
    assert 'Turn the Curve off' in text and 'ungroup' in text, text
    assert '—' not in text and '–' not in text

    before = [stored(page, i) for i in ids]
    steps = history_len(page)
    said = 'curves as one wall, so C2 cannot move or turn on its own'

    clear_toasts(page)
    type_field(page, 's3d-x', '20')
    assert said in settled(page, lambda: toast_text(page), lambda t: said in t, 3000)
    clear_toasts(page)
    rotation_menu(page, 'yaw', '+90')
    assert said in settled(page, lambda: toast_text(page), lambda t: said in t, 3000)
    clear_toasts(page)
    view_from(page, 'front')   # a curved wall seen from above is a thin arc
    drag_on_stage(page, c2, 80)
    assert said in settled(page, lambda: toast_text(page), lambda t: said in t, 3000)
    clear_toasts(page)
    page.mouse.move(5, 5)
    page.keyboard.press('ArrowRight')
    assert said in settled(page, lambda: toast_text(page), lambda t: said in t, 3000)
    page.wait_for_timeout(900)
    assert [stored(page, i) for i in ids] == before
    assert history_len(page) == steps
    # the panel shows where it still stands
    assert page.input_value('#s3d-x') == f"{screen(page, c2)['shown']['x'] / FT:.2f}"

    # a click on the wall: the whole curved wall moves as one
    click_on_stage(page, c2)
    assert picked(page) is None
    assert note(page)[2] == 'group'
    type_field(page, 's3d-z', '5')
    after = [stored(page, i) for i in ids]
    dz = after[1]['z'] - before[1]['z']
    assert abs(dz) > 100
    for a, b in zip(after, before):
        assert a['z'] - b['z'] == pytest.approx(dz, abs=0.01)
        assert a['x'] == pytest.approx(b['x'], abs=0.01)
        assert a['yaw'] == pytest.approx(b['yaw'], abs=1e-6)
    assert history_len(page) == steps + 1
    assert page.errors == []


# ── the guide ────────────────────────────────────────────────────────────

@pytest.mark.parametrize('run', range(3))
def test_the_guide_step_plays_on_its_own(page, run):
    """The 3D and Output guide's step, played alone as What's New's Show me
    plays it: the demo walls are grouped, DEMO WALL 2 is picked in the
    Screens list and moved toward the audience and back on its own, and the
    note under the figures says so. Three times: a guide step passes first
    try, every time."""
    p = page
    p.evaluate("""() => {
        const q = window.QuickStart, keys = q.tours().threeD
            .map(s => Object.keys(q.steps()).find(k => q.steps()[k] === s));
        if (keys[keys.indexOf('s3dPng') + 1] !== 's3dGroupMember') throw new Error('out of place');
        if (keys[keys.indexOf('s3dGroupMember') + 1] !== 'outputOpen') throw new Error('out of place');
        if (q.steps().s3dGroupMember.since !== '1.7.0') throw new Error('since');
        // never in a later guide's demo show
        if (q.prepOf && ['idm', 'binder'].some(g => (q.prepOf(g) || []).includes('s3dGroupMember'))) throw new Error('in a prep');
    }""")
    body = p.evaluate("() => window.QuickStart.steps().s3dGroupMember.body")
    assert len(body) <= 220 and body.count('. ') <= 1, body
    assert '\u2014' not in body and '\u2013' not in body
    p.evaluate("() => { window.QuickStart.setSpeed(6); window.QuickStart.startSteps(['s3dGroupMember']); }")
    p.wait_for_function("""() => {
        const c = document.getElementById('qs-callout');
        return c && ['done', 'failed'].includes(c.getAttribute('data-qs-state'));
    }""", timeout=180000)
    state = p.evaluate("() => document.getElementById('qs-callout').getAttribute('data-qs-state')")
    note = p.locator('#qs-callout .qs-result').text_content()
    assert state == 'done', note
    assert 'toward the audience and back on its own' in note, note
    assert p.evaluate("() => (window.app.project.groups || []).length") == 1
    assert p.evaluate("() => window.app._listPickedMember().name") == 'DEMO WALL 2'
    assert p.locator('#s3d-group-note').text_content().startswith('Moves only DEMO WALL 2 in its group')
    p.evaluate("() => window.QuickStart.end()")
    p.wait_for_function("() => !window.QuickStart.state().running && !window.QuickStart.state().visible",
                        timeout=60000)
    p.wait_for_timeout(300)
