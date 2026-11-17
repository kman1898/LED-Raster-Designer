"""A grouped wall takes ONE Curve (app-curve.js), in the real app.

Owner's report (2026-11-16): "groups arent allowing curve which is not
correct". The members of a group that stand edge to edge carry one row of
bars (app-rigging.js riggingRow); the Curve now runs across that row the
same way: one curve laid by the calculator over every member's columns in
wall order, the seams between the screens ordinary joints, one Curve
setting for the group set from any member.

What this file pins:

* Ticking Curve on one member of a three screen group curves the whole
  wall: every member's Curve is on with the same settings, the bars cover
  the row, each member's joints are its part of the calculator's answer for
  a wall as wide as the row, and that answer is the one a single screen of
  the same width gets. One undo step.
* In 3D (and so in the OBJ) the members meet at their seams and the angle
  at every joint, the seams included, is the calculator's; the middle of
  the wall stays where it stood. The OBJ of the group reads the same.
* The pull list counts the bars the Curve laid, once each.
* Curve off flattens the group back into one straight wall.
* Refused, said and nothing changed: panels of different widths, panels
  that share no lock position but flat, a locked group, and a member that
  stands beside the row with its edge out of line. Panels with some lock
  positions in common lay only those.
* A member's corner splits the wall into sides, as on a screen.
* Grouping two screens that each had a Curve: nothing moves until Auto,
  which lays one curve across both. Ungrouping keeps each screen as it
  stands. A stacked group takes the setting on each screen.

Run locally:
    python -m pytest tests/test_curve_group.py -n 4 --dist loadfile
"""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from conftest import settled  # noqa: E402
from test_curve_obj import (  # noqa: E402
    act, face_corners_xz, group_two, history_len, idle, layer, obj_files, open_rigging, read_obj, reset,
    singles_only, toast_says,
)


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project as this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1500, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.errors = []
    pg.on('pageerror', lambda err: pg.errors.append(str(err)))
    pg.route('**/api/native-dialog/**', lambda r: r.fulfill(status=503, body='{}'))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    yield pg
    context.close()


def three(name='M', cols=4, y=0, **extra):
    """Three screens `cols` wide standing edge to edge (128 px cabinets)."""
    return [dict({'name': f'{name}{i + 1}', 'columns': cols, 'rows': 2,
                  'offset_x': i * cols * 128, 'offset_y': y}, **extra) for i in range(3)]


def group(page, ids):
    """`ids` grouped (the module's own two-screen helper takes any count)."""
    group_two(page, ids)


def select(page, ids, primary=None):
    page.evaluate(f"window.app.setSelectedLayersByIds({list(ids)}, {primary if primary is not None else ids[0]})")
    page.evaluate("window.app.refreshRiggingPanel()")


def solve(page, layer_id):
    return page.evaluate("""(id) => {
        const l = window.app.project.layers.find(x => x.id === id);
        const out = window.app.riggingCurveSolve(l);
        return { bars: out.bars, joints: out.joints, errors: out.errors, placed: out.placed || null };
    }""", layer_id)


def own_joints(lay):
    """A screen's own column joints, 0 to columns - 2."""
    table = ((lay or {}).get('stage3d') or {}).get('jointsCol') or {}
    return [table.get(str(j)) for j in range(lay['columns'] - 1)]


WALL_JS = """async (ids) => {
    const m = await import('/static/js/app-stage3d.js');
    const app = window.app;
    // the bottom edge of every member, left to right, in world mm (x, z)
    return ids.map(id => {
        const l = app.project.layers.find(x => x.id === id);
        const quads = m.s3dWorldCorners(l, app._s3dPlacementOf(l));
        const last = Math.max(...quads.map(q => q.row));
        const bottom = quads.filter(q => q.row === last).sort((a, b) => a.col - b.col || (a.fold || 0) - (b.fold || 0));
        const pts = [[bottom[0].corners[3][0], bottom[0].corners[3][2]]];
        bottom.forEach(q => pts.push([q.corners[2][0], q.corners[2][2]]));
        return pts;
    });
}"""


def wall_edges(page, ids):
    return page.evaluate(WALL_JS, list(ids))


def turns(points):
    """The turn in degrees at every inner point of a plan polyline."""
    out = []
    for i in range(1, len(points) - 1):
        a, b, c = points[i - 1], points[i], points[i + 1]
        h1 = math.atan2(b[1] - a[1], b[0] - a[0])
        h2 = math.atan2(c[1] - b[1], c[0] - b[0])
        d = math.degrees(h2 - h1)
        while d > 180:
            d -= 360
        while d < -180:
            d += 360
        out.append(d)
    return out


def joined(edges):
    """The members' bottom edges as one polyline, each seam checked to meet."""
    pts = list(edges[0])
    for e in edges[1:]:
        assert math.dist(pts[-1], e[0]) < 0.01, ('the members do not meet', pts[-1], e[0])
        pts.extend(e[1:])
    return pts


def placement(page, layer_id):
    return page.evaluate("(id) => window.app._s3dPlacementOf(window.app.project.layers.find(l => l.id === id))", layer_id)


# ── one curve across the group ────────────────────────────────────────────

def test_a_three_screen_group_curves_as_one_wall(page):
    ids = reset(page, three() + [{'name': 'SOLO', 'columns': 12, 'rows': 2, 'offset_x': 0, 'offset_y': 800}])
    grouped, solo = ids[:3], ids[3]
    group(page, grouped)
    open_rigging(page)
    select(page, [grouped[1]])
    singles_only(page)
    middle_before = placement(page, grouped[1])
    n = history_len(page)
    act(page, lambda: page.check('#rigging-curve-on'))
    lays = [layer(page, i) for i in grouped]
    # every member on, one setting
    assert all((l.get('riggingCurve') or {}).get('on') for l in lays), [l.get('riggingCurve') for l in lays]
    assert len({str(sorted(l['riggingCurve'].items())) for l in lays}) == 1
    assert history_len(page) == n + 1
    # the calculator over the whole row: the answer a 12 wide screen gets
    want = solve(page, grouped[0])
    assert want['errors'] == []
    assert solve(page, grouped[2]) == want
    page.evaluate(f"() => {{ window.app.project.layers.find(x => x.id === {solo}).riggingSizes = [1]; }}")
    single = solve(page, solo)
    assert want['bars'] == single['bars'] and want['joints'] == single['joints'], (want, single)
    assert len(want['joints']) == 11 and any(want['joints'])
    # the bars cover the row, each stored on the member it starts on
    assert sum(sum(l.get('riggingBars') or []) for l in lays) == 12
    # each member's joints are its part of the answer
    for k, lay in enumerate(lays):
        assert own_joints(lay) == want['joints'][k * 4:k * 4 + 3], (k, own_joints(lay))
    # 3D: the members meet, and every joint (the seams too) bends as laid
    pts = joined(wall_edges(page, grouped))
    assert len(pts) == 13
    got = turns(pts)
    for j, (a, b) in enumerate(zip(got, want['joints'])):
        assert abs(a - b) < 1e-3, (j, a, b)
    # the middle of the wall stands where it stood, facing the same way
    mid = placement(page, grouped[1])
    assert abs(mid['x'] - middle_before['x']) < 0.01 and abs(mid['z'] - middle_before['z']) < 0.01
    assert abs(mid['yaw']) < 1e-6
    # the 3D panel reads the row's joints, the seams among them
    text = page.evaluate(f"""() => {{ const app = window.app; const l = app.project.layers.find(x => x.id === {grouped[0]});
        return app._s3dCurveText(l, app._s3dPlacementOf(l)); }}""")
    bent = [a for a in want['joints'] if a]
    assert text.startswith('Curve: '), text
    if len(bent) < 11:
        assert f'at {len(bent)} of 11 joints' in text, text
    assert text.endswith('It runs across Group 1.'), text
    # the tab shows the one curve: a strip of 12 panels with its angles
    assert page.locator('#rigging-curve-sheet svg rect[data-bar]').count() == len(want['bars'])
    assert 'not this curve' not in page.inner_text('#rigging-curve-note')
    assert page.errors == []


def test_the_obj_and_the_pull_list_follow_the_group_curve(page):
    ids = reset(page, three())
    group(page, ids)
    open_rigging(page)
    select(page, ids)
    singles_only(page)
    act(page, lambda: page.check('#rigging-curve-on'))
    want = solve(page, ids[0])
    files = obj_files(page)
    name = [f for f in files if f.endswith('.obj')]
    assert name == ['Test_Show_Group_1.obj'], sorted(files)
    obj = read_obj(files[name[0]])
    assert [o['name'] for o in obj['objects']] == ['M1', 'M2', 'M3']
    # the faces of the three members, one bottom edge across the wall
    pts = []
    for o in range(3):
        one = dict(obj, objects=[obj['objects'][o]])
        edge = face_corners_xz(one)
        if pts:
            assert math.dist(pts[-1], edge[0]) < 1e-5, (o, pts[-1], edge[0])
            edge = edge[1:]
        pts.extend(edge)
    assert len(pts) == 13
    for j, (a, b) in enumerate(zip(turns(pts), want['joints'])):
        assert abs(a - b) < 1e-3, (j, a, b)
    # the pull list counts every bar the Curve laid, once
    rows = page.evaluate(f"""() => {ids}.flatMap(id => window.app.riggingPullRows(
        window.app.project.layers.find(l => l.id === id)))""")
    assert sum(r['qty'] for r in rows) == len(want['bars'])
    assert all('no longer fit' not in r['label'] for r in rows)
    assert page.errors == []


def test_curve_off_lays_the_group_flat_in_one_line(page):
    ids = reset(page, three())
    group(page, ids)
    open_rigging(page)
    select(page, [ids[0]])
    singles_only(page)
    act(page, lambda: page.check('#rigging-curve-on'))
    act(page, lambda: page.uncheck('#rigging-curve-on'))
    lays = [layer(page, i) for i in ids]
    assert not any((l.get('riggingCurve') or {}).get('on') for l in lays)
    pts = joined(wall_edges(page, ids))
    assert all(abs(t) < 1e-6 for t in turns(pts)), turns(pts)
    assert all(abs(p[1] - pts[0][1]) < 0.01 for p in pts)
    assert page.errors == []


def test_a_form_edit_on_one_member_lays_the_group_again(page):
    ids = reset(page, three())
    group(page, ids)
    open_rigging(page)
    select(page, [ids[2]])
    singles_only(page)
    act(page, lambda: page.check('#rigging-curve-on'))
    act(page, lambda: page.click('#rigging-curve-bend [data-value="convex"]'))
    lays = [layer(page, i) for i in ids]
    assert all(l['riggingCurve']['bend'] == 'convex' for l in lays)
    want = solve(page, ids[1])
    assert all(a <= 0 for a in want['joints']) and any(want['joints'])
    pts = joined(wall_edges(page, ids))
    for j, (a, b) in enumerate(zip(turns(pts), want['joints'])):
        assert abs(a - b) < 1e-3, (j, a, b)
    # the datum is the whole wall's: panel 6 is the middle member's second
    act(page, lambda: page.evaluate("window.app.setRiggingCurveField('from', 6)"))
    assert all(layer(page, i)['riggingCurve']['from'] == 6 for i in ids)
    assert 'panel 6' in page.inner_text('#rigging-curve-from-label')
    assert page.errors == []


def test_the_group_moves_as_one_in_3d_and_a_reset_keeps_it_curved(page):
    ids = reset(page, three())
    group(page, ids)
    open_rigging(page)
    select(page, [ids[0]])
    singles_only(page)
    flat = placement(page, ids[1])
    act(page, lambda: page.check('#rigging-curve-on'))
    want = solve(page, ids[0])
    # moved and turned on the 3D tab: the group goes as one, still joined
    page.evaluate(f"""() => {{ const app = window.app; const l = app.project.layers.find(x => x.id === {ids[1]});
        const p = app._s3dPlacementOf(l); app._s3dCommit(l, {{ ...p, x: p.x + 1000, yaw: 30 }}, 'Test Move'); }}""")
    pts = joined(wall_edges(page, ids))
    for j, (a, b) in enumerate(zip(turns(pts), want['joints'])):
        assert abs(a - b) < 1e-3, (j, a, b)
    # Reset to Show Look: the middle back where Show Look stands it, the
    # wall still curved and joined
    page.evaluate(f"() => {{ const app = window.app; app.selectLayer(app.project.layers.find(x => x.id === {ids[1]})); app._s3dReset(); }}")
    pts = joined(wall_edges(page, ids))
    for j, (a, b) in enumerate(zip(turns(pts), want['joints'])):
        assert abs(a - b) < 1e-3, (j, a, b)
    mid = placement(page, ids[1])
    assert abs(mid['x'] - flat['x']) < 0.01 and abs(mid['z'] - flat['z']) < 0.01 and abs(mid['yaw']) < 1e-6
    assert page.errors == []


# ── what the group refuses ────────────────────────────────────────────────

def test_panels_of_different_widths_are_refused(page):
    specs = three()
    specs[2]['panel_width_mm'] = 600
    ids = reset(page, specs)
    group(page, ids)
    open_rigging(page)
    select(page, [ids[0]])
    n = history_len(page)
    page.click('#rigging-curve-on')
    said = toast_says(page, 'cannot take a Curve')
    assert 'different widths' in said and 'M3 600 mm' in said, said
    assert not any((layer(page, i).get('riggingCurve') or {}).get('on') for i in ids)
    assert history_len(page) == n
    assert page.errors == []


LOCK_KEYS_JS = """([ids, lists]) => {
    const app = window.app;
    const map = {};
    ids.forEach((id, i) => {
        const l = app.project.layers.find(x => x.id === id);
        l.panelModelName = 'PANEL ' + i;
        map[app.curveLockKey(l)] = lists[i];
    });
    app.project.panelCurveLocks = map;
}"""


def test_panels_with_no_lock_position_in_common_are_refused(page):
    ids = reset(page, three())
    group(page, ids)
    page.evaluate(LOCK_KEYS_JS, [ids, [[-5, 0, 5], [-5, 0, 5], [-7.5, 0, 7.5]]])
    open_rigging(page)
    select(page, [ids[0]])
    page.click('#rigging-curve-on')
    said = toast_says(page, 'cannot take a Curve')
    assert 'share no lock position' in said, said
    assert not any((layer(page, i).get('riggingCurve') or {}).get('on') for i in ids)
    assert page.errors == []


def test_panels_with_some_lock_positions_in_common_lay_only_those(page):
    ids = reset(page, three(cols=6))
    group(page, ids)
    page.evaluate(LOCK_KEYS_JS, [ids, [[-5, 0, 5, 7.5], [-5, 0, 5], [-7.5, -5, 0, 5, 7.5]]])
    open_rigging(page)
    select(page, [ids[0]])
    singles_only(page)
    act(page, lambda: page.check('#rigging-curve-on'))
    want = solve(page, ids[0])
    assert want['errors'] == [] and set(want['joints']) <= {0, 5} and 5 in want['joints'], want
    assert all((layer(page, i).get('riggingCurve') or {}).get('on') for i in ids)
    chips = page.eval_on_selector_all('#rigging-curve-lock-chips [data-lock]', 'els => els.map(e => Number(e.dataset.lock))')
    assert chips == [-5, 0, 5]
    assert page.errors == []


def test_a_locked_group_is_refused_and_named(page):
    ids = reset(page, three())
    group(page, ids)
    page.evaluate(f"""() => {{ window.app.project.layers.filter(l => {ids}.includes(l.id))
        .forEach(l => {{ l.locked = true; }}); }}""")
    open_rigging(page)
    select(page, [ids[1]])
    n = history_len(page)
    page.click('#rigging-curve-on')
    page.wait_for_timeout(300)
    said = toast_says(page, 'locked')
    assert 'M1, M2 and M3 are locked' in said, said
    assert not any((layer(page, i).get('riggingCurve') or {}).get('on') for i in ids)
    assert history_len(page) == n
    assert page.errors == []


def test_a_member_beside_the_row_out_of_line_is_refused(page):
    specs = three()
    specs[2]['offset_y'] = 64
    ids = reset(page, specs)
    group(page, ids)
    open_rigging(page)
    select(page, [ids[0]])
    n = history_len(page)
    page.click('#rigging-curve-on')
    said = toast_says(page, 'cannot take a Curve')
    assert 'M3 stands beside' in said and 'do not line up' in said, said
    assert not any((layer(page, i).get('riggingCurve') or {}).get('on') for i in ids)
    assert history_len(page) == n
    assert page.errors == []


# ── corners, old shows, ungrouping, stacking ──────────────────────────────

def test_a_members_corner_splits_the_group_into_sides(page):
    ids = reset(page, three(cols=6))
    group(page, ids)
    # a seam corner between panels 3 and 4 of the first member
    page.evaluate(f"""() => {{ const l = window.app.project.layers.find(x => x.id === {ids[0]});
        l.riggingCorners = [{{ at: 3.5, angle: 90, side: 'interior' }}]; window.app.updateLayers([l], true, 'Test Corner'); }}""")
    open_rigging(page)
    select(page, [ids[1]])
    singles_only(page)
    page.evaluate("window.app.setRiggingCurveField('value', 5)")
    act(page, lambda: page.check('#rigging-curve-on'))
    want = solve(page, ids[0])
    assert want['errors'] == [], want
    assert want['joints'][2] == 0
    first = layer(page, ids[0])
    assert any(c.get('bar') for c in first.get('riggingCorners') or [])
    pts = joined(wall_edges(page, ids))
    got = turns(pts)
    # the fold is the corner's 90, every other joint the Curve's
    assert abs(got[2] - 90) < 1e-3, got
    for j, (a, b) in enumerate(zip(got, want['joints'])):
        if j != 2:
            assert abs(a - b) < 1e-3, (j, a, b)
    assert page.locator('#rigging-curve-sheet svg [data-corner-seam]').count() == 1
    assert page.errors == []


def test_two_curved_screens_grouped_wait_for_auto_then_curve_as_one(page):
    ids = reset(page, three(cols=8)[:2])
    open_rigging(page)
    for i in ids:
        select(page, [i])
        singles_only(page)
        act(page, lambda: page.check('#rigging-curve-on'))
    alone = [layer(page, i) for i in ids]
    group(page, ids)
    select(page, [ids[0]])
    # nothing moved: each still stands as its own curve laid it
    assert [layer(page, i)['riggingBars'] for i in ids] == [a['riggingBars'] for a in alone]
    assert [own_joints(layer(page, i)) for i in ids] == [own_joints(a) for a in alone]
    assert 'not this curve' in page.inner_text('#rigging-curve-note')
    act(page, lambda: page.click('#rigging-auto-btn'))
    want = solve(page, ids[0])
    assert own_joints(layer(page, ids[0])) == want['joints'][:7]
    assert own_joints(layer(page, ids[1])) == want['joints'][8:]
    joined(wall_edges(page, ids))
    assert 'not this curve' not in page.inner_text('#rigging-curve-note')
    assert page.errors == []


def test_ungrouping_keeps_each_screen_as_it_stands(page):
    ids = reset(page, three(cols=8))
    group(page, ids)
    open_rigging(page)
    select(page, ids)
    singles_only(page)
    act(page, lambda: page.check('#rigging-curve-on'))
    before = [layer(page, i) for i in ids]
    page.evaluate("async () => { await window.app.ungroupSelectedLayers(); }")
    settled(page, lambda: layer(page, ids[0]).get('group_id'), lambda g: not g)
    page.wait_for_timeout(300)
    after = [layer(page, i) for i in ids]
    for b, a in zip(before, after):
        assert a['riggingCurve'] == b['riggingCurve']
        assert a['riggingBars'] == b['riggingBars']
        assert a['stage3d'] == b['stage3d']
    joined(wall_edges(page, ids))
    select(page, [ids[0]])
    assert 'not this curve' in page.inner_text('#rigging-curve-note')
    assert page.errors == []


def test_a_stacked_group_takes_the_setting_on_each_screen(page):
    ids = reset(page, [{'name': 'TOP', 'columns': 8, 'rows': 2, 'offset_x': 0, 'offset_y': 0},
                       {'name': 'LOW', 'columns': 8, 'rows': 2, 'offset_x': 0, 'offset_y': 256}])
    group(page, ids)
    open_rigging(page)
    select(page, [ids[0]])
    singles_only(page)
    act(page, lambda: page.check('#rigging-curve-on'))
    top, low = layer(page, ids[0]), layer(page, ids[1])
    assert top['riggingCurve']['on'] and low['riggingCurve']['on']
    assert own_joints(top) == solve(page, ids[0])['joints'] == own_joints(low)
    assert page.errors == []


def test_members_of_different_heights_curve_as_one(page):
    specs = three()
    specs[1]['rows'] = 3
    ids = reset(page, specs)
    group(page, ids)
    open_rigging(page)
    select(page, [ids[0]])
    singles_only(page)
    act(page, lambda: page.check('#rigging-curve-on'))
    assert all(layer(page, i)['riggingCurve']['on'] for i in ids)
    joined(wall_edges(page, ids))
    assert page.errors == []
