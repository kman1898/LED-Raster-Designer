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
    act, face_corners_xz, group_two, history_len, idle, layer, obj_files, open_rigging, plan_spot, read_obj, reset,
    served, singles_only, toast_says,
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
    act(page, lambda: page.click('#rigging-tool-picker [data-tool="auto"]'))
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


def test_a_two_row_stack_curves_as_one_wall(page):
    """TOP is 8 panels wide; LOW, 4 wide, hangs under TOP's panels 3 to 6.
    One curve across the wall: LOW takes the angles of the columns it
    hangs under, carries no header bars, and stands under them in 3D."""
    ids = reset(page, [{'name': 'TOP', 'columns': 8, 'rows': 2, 'offset_x': 0, 'offset_y': 0},
                       {'name': 'LOW', 'columns': 4, 'rows': 2, 'offset_x': 256, 'offset_y': 256}])
    group(page, ids)
    open_rigging(page)
    # ticked from the lower screen: it is the wall's Curve all the same
    select(page, [ids[1]])
    singles_only(page)
    page.evaluate("window.app.setRiggingCurveField('value', 10)")
    n = history_len(page)
    act(page, lambda: page.check('#rigging-curve-on'))
    top, low = layer(page, ids[0]), layer(page, ids[1])
    assert top['riggingCurve']['on'] and low['riggingCurve']['on']
    assert top['riggingCurve'] == low['riggingCurve']
    assert history_len(page) == n + 1
    want = solve(page, ids[0])
    assert want['errors'] == [] and len(want['joints']) == 7 and any(want['joints']), want
    assert solve(page, ids[1]) == want
    # identical column angles: LOW's are the wall's over its columns
    assert own_joints(top) == want['joints']
    assert own_joints(low) == want['joints'][2:5]
    # the bars run along the top row only
    assert sum(top.get('riggingBars') or []) == 8
    assert not (low.get('riggingBars') or [])
    # 3D: LOW stands under TOP's columns 3 to 6, bent at the same seams
    top_edge, low_edge = wall_edges(page, ids)
    assert len(top_edge) == 9 and len(low_edge) == 5
    for a, b in zip(low_edge, top_edge[2:7]):
        assert math.dist(a, b) < 0.01, (a, b)
    for a, b in zip(turns(low_edge), turns(top_edge)[2:5]):
        assert abs(a - b) < 1e-3, (a, b)
    assert page.inner_text('#rigging-curve-group') == 'Group 1 curves as one wall across its 2 screens. A change here sets both.'
    assert 'not this curve' not in page.inner_text('#rigging-curve-note')
    assert page.errors == []


def grid():
    """A 2 by 2 grid of 4 panel screens: TL, TR over BL, BR."""
    return [{'name': n, 'columns': 4, 'rows': 2, 'offset_x': x, 'offset_y': y}
            for n, x, y in (('TL', 0, 0), ('TR', 512, 0), ('BL', 0, 256), ('BR', 512, 256))]


def test_a_grid_group_curves_as_one_wall(page):
    ids = reset(page, grid())
    group(page, ids)
    open_rigging(page)
    select(page, [ids[3]])
    singles_only(page)
    page.evaluate("window.app.setRiggingCurveField('value', 10)")
    act(page, lambda: page.check('#rigging-curve-on'))
    lays = [layer(page, i) for i in ids]
    assert all(l['riggingCurve']['on'] for l in lays)
    assert len({str(sorted(l['riggingCurve'].items())) for l in lays}) == 1
    want = solve(page, ids[0])
    assert want['errors'] == [] and len(want['joints']) == 7 and any(want['joints']), want
    assert all(solve(page, i) == want for i in ids[1:])
    # both rows: the same joints at the same seams
    tl, tr, bl, br = lays
    assert own_joints(tl) == own_joints(bl) == want['joints'][0:3]
    assert own_joints(tr) == own_joints(br) == want['joints'][4:7]
    # the bars run along the top row only
    assert sum(sum(l.get('riggingBars') or []) for l in (tl, tr)) == 8
    assert not (bl.get('riggingBars') or []) and not (br.get('riggingBars') or [])
    # 3D: two rows, each one joined edge bent as the calculator says, the
    # lower one right under the upper
    upper = joined(wall_edges(page, ids[:2]))
    lower = joined(wall_edges(page, ids[2:]))
    for a, b in zip(upper, lower):
        assert math.dist(a, b) < 0.01, (a, b)
    for j, (a, b) in enumerate(zip(turns(lower), want['joints'])):
        assert abs(a - b) < 1e-3, (j, a, b)
    # Export OBJ: the lower row's faces bend at the same seams
    files = obj_files(page)
    name = [f for f in files if f.endswith('.obj')]
    assert name == ['Test_Show_Group_1.obj'], sorted(files)
    obj = read_obj(files[name[0]])
    assert [o['name'] for o in obj['objects']] == ['TL', 'TR', 'BL', 'BR']
    pts = []
    for o in (2, 3):
        edge = face_corners_xz(dict(obj, objects=[obj['objects'][o]]))
        if pts:
            assert math.dist(pts[-1], edge[0]) < 1e-5, (o, pts[-1], edge[0])
            edge = edge[1:]
        pts.extend(edge)
    assert len(pts) == 9
    for j, (a, b) in enumerate(zip(turns(pts), want['joints'])):
        assert abs(a - b) < 1e-3, (j, a, b)
    assert page.inner_text('#rigging-curve-group') == 'Group 1 curves as one wall across its 4 screens. A change here sets all four.'
    # the 3D panel reads the wall's joints from a lower screen too
    text = page.evaluate(f"""() => {{ const app = window.app; const l = app.project.layers.find(x => x.id === {ids[2]});
        return app._s3dCurveText(l, app._s3dPlacementOf(l)); }}""")
    assert text.endswith('It runs across Group 1.'), text
    # Curve off lays every row flat again, one under the other
    act(page, lambda: page.uncheck('#rigging-curve-on'))
    upper = joined(wall_edges(page, ids[:2]))
    lower = joined(wall_edges(page, ids[2:]))
    assert all(abs(t) < 1e-6 for t in turns(upper) + turns(lower))
    for a, b in zip(upper, lower):
        assert math.dist(a, b) < 0.01, (a, b)
    assert page.errors == []


def test_a_stack_whose_seams_do_not_line_up_is_refused(page):
    ids = reset(page, [{'name': 'TOP', 'columns': 8, 'rows': 2, 'offset_x': 0, 'offset_y': 0},
                       {'name': 'LOW', 'columns': 8, 'rows': 2, 'offset_x': 64, 'offset_y': 256}])
    group(page, ids)
    open_rigging(page)
    select(page, [ids[0]])
    n = history_len(page)
    page.click('#rigging-curve-on')
    said = toast_says(page, 'cannot take a Curve')
    assert 'TOP and LOW cannot take a Curve' in said, said
    assert 'the panel seams of LOW do not line up with the top row' in said, said
    assert not any((layer(page, i).get('riggingCurve') or {}).get('on') for i in ids)
    assert history_len(page) == n
    # the tab says so too
    assert 'panel seams of LOW do not line up' in page.inner_text('#rigging-curve-note')
    assert page.errors == []


def test_a_stack_reaching_past_its_top_row_is_refused(page):
    ids = reset(page, [{'name': 'TOP', 'columns': 4, 'rows': 2, 'offset_x': 256, 'offset_y': 0},
                       {'name': 'WIDE', 'columns': 8, 'rows': 2, 'offset_x': 0, 'offset_y': 256}])
    group(page, ids)
    open_rigging(page)
    select(page, [ids[1]])
    n = history_len(page)
    page.click('#rigging-curve-on')
    said = toast_says(page, 'cannot take a Curve')
    assert 'WIDE reaches past the ends of the top row' in said, said
    assert not any((layer(page, i).get('riggingCurve') or {}).get('on') for i in ids)
    assert history_len(page) == n
    assert page.errors == []


# ── where the group builds from ──────────────────────────────────────────

def point_at(pts, at):
    """The point of a plan polyline (one point per seam, 0 the left end)
    at a build-from spot in half panels: a joint, or a panel's middle."""
    if at != int(at):
        return pts[int(at - 0.5)]
    a, b = pts[int(at) - 1], pts[int(at)]
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


@pytest.mark.parametrize('pick,at', [('left', 0.5), ('right', 12.5), ('center', 6.5), (4.5, 4.5), (6, 6)])
def test_the_group_builds_from_the_point_picked(page, pick, at):
    """Left, Center, Right or a point on the plan: that point of the whole
    wall keeps its place in 3D and the rest bends away from it."""
    ids = reset(page, three())
    group(page, ids)
    open_rigging(page)
    select(page, [ids[1]])
    singles_only(page)
    # (set with the Curve off, when only its switch shows: the setting is
    # kept for when it goes on)
    page.evaluate("(p) => window.app.setRiggingCurveField('from', p)", pick)
    idle(page)
    assert all(layer(page, i)['riggingCurve']['from'] == pick for i in ids)
    flat = joined(wall_edges(page, ids))
    act(page, lambda: page.check('#rigging-curve-on'))
    curved = joined(wall_edges(page, ids))
    assert math.dist(point_at(curved, at), point_at(flat, at)) < 0.01, (pick, point_at(curved, at), point_at(flat, at))
    # the rest of the wall bends away from it
    far = curved[0] if at > 6.5 else curved[-1]
    near = flat[0] if at > 6.5 else flat[-1]
    assert math.dist(far, near) > 10, (pick, far, near)
    # the strip and the plan mark the same point
    assert page.get_attribute('#rigging-curve-sheet path[data-datum]', 'data-datum') == (str(int(at)) if at == int(at) else str(at))
    assert page.errors == []


def test_a_dragged_build_from_point_stays_put_in_3d(page):
    ids = reset(page, three())
    group(page, ids)
    open_rigging(page)
    select(page, [ids[0]])
    singles_only(page)
    act(page, lambda: page.check('#rigging-curve-on'))
    before = joined(wall_edges(page, ids))
    # drag the red dot from the middle of the wall to the joint between
    # panels 2 and 3, on the first screen
    a, b = plan_spot(page, 6.5), plan_spot(page, 2.5)
    page.mouse.move(a['x'], a['y'])
    page.mouse.down()
    page.mouse.move(b['x'], b['y'], steps=4)
    act(page, lambda: page.mouse.up())
    assert all(layer(page, i)['riggingCurve']['from'] == 2.5 for i in ids)
    assert 'between panels 2 and 3' in page.inner_text('#rigging-curve-from-label')
    after = joined(wall_edges(page, ids))
    assert math.dist(after[2], before[2]) < 0.01, (after[2], before[2])
    want = solve(page, ids[0])
    for j, (x, y) in enumerate(zip(turns(after), want['joints'])):
        assert abs(x - y) < 1e-3, (j, x, y)
    assert page.errors == []


def test_a_grid_builds_from_its_right_end(page):
    ids = reset(page, grid())
    group(page, ids)
    open_rigging(page)
    select(page, [ids[0]])
    singles_only(page)
    page.evaluate("window.app.setRiggingCurveField('value', 10)")
    page.evaluate("window.app.setRiggingCurveField('from', 'right')")
    idle(page)
    flat_up, flat_low = joined(wall_edges(page, ids[:2])), joined(wall_edges(page, ids[2:]))
    act(page, lambda: page.check('#rigging-curve-on'))
    up, low = joined(wall_edges(page, ids[:2])), joined(wall_edges(page, ids[2:]))
    # the right end of both rows stands where it stood; the left end moved
    assert math.dist(up[-1], flat_up[-1]) < 0.01 and math.dist(low[-1], flat_low[-1]) < 0.01
    assert math.dist(up[0], flat_up[0]) > 10
    assert page.errors == []


def test_an_old_show_with_a_stacked_curve_opens_as_it_was(page):
    """A show saved before a stack curved as one wall: each screen curved
    on its own, bars on both. It opens and stands exactly as it was until
    it is edited; Auto then lays the one wall."""
    ids = reset(page, [{'name': 'TOP', 'columns': 8, 'rows': 2, 'offset_x': 0, 'offset_y': 0},
                       {'name': 'LOW', 'columns': 6, 'rows': 2, 'offset_x': 0, 'offset_y': 256}])
    open_rigging(page)
    for i in ids:
        select(page, [i])
        singles_only(page)
        page.evaluate("window.app.setRiggingCurveField('value', 10)")
        act(page, lambda: page.check('#rigging-curve-on'))
    group(page, ids)
    mine = [layer(page, i) for i in ids]
    assert all(m.get('riggingBars') for m in mine)
    for m in mine:
        assert settled(page, lambda: served(page, m['id']),
                       lambda s: s.get('riggingCurve') == m['riggingCurve'] and s.get('stage3d') == m['stage3d']
                       and s.get('riggingBars') == m['riggingBars'] and s.get('group_id') == m['group_id'])
    corners = page.evaluate(CORNERS_JS, ids)
    page.reload(wait_until='domcontentloaded')
    page.wait_for_timeout(2000)
    page.evaluate("(id) => { window.app.selectLayer(window.app.project.layers.find(l => l.id === id)); window.app.updateUI(); }", ids[0])
    open_rigging(page)
    select(page, [ids[1]])
    page.wait_for_timeout(500)
    for m in mine:
        now = layer(page, m['id'])
        for k in ('riggingCurve', 'riggingBars', 'stage3d', 'group_id'):
            assert now.get(k) == m.get(k), (m['name'], k, now.get(k), m.get(k))
    assert page.evaluate(CORNERS_JS, ids) == corners
    assert 'not this curve' in page.inner_text('#rigging-curve-note')
    # edited: Auto lays the one wall
    act(page, lambda: page.click('#rigging-tool-picker [data-tool="auto"]'))
    want = solve(page, ids[0])
    assert own_joints(layer(page, ids[0])) == want['joints']
    assert own_joints(layer(page, ids[1])) == want['joints'][:5]
    assert not (layer(page, ids[1]).get('riggingBars') or [])
    assert 'not this curve' not in page.inner_text('#rigging-curve-note')
    assert page.errors == []


CORNERS_JS = """async (ids) => {
    const m = await import('/static/js/app-stage3d.js');
    const app = window.app;
    return ids.map(id => {
        const l = app.project.layers.find(x => x.id === id);
        return m.s3dWorldCorners(l, app._s3dPlacementOf(l)).map(q => q.corners.map(c => c.map(v => Math.round(v * 1000) / 1000)));
    });
}"""


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


# ── a group lays the bars one wide screen lays ───────────────────────────
#
# Owner's report (2026-11-18): "screen 1 will only do single headers". A
# group of 13, 13 and 4 columns curved from its middle laid singles over the
# whole first screen and doubles on the others, for joints that mirror. The
# calculator's layout search walked from the left end and kept the first of
# every tie; between two bends the bars are now the fewest, the larger
# nearest the Build from point (curve-math.js fewestBetweenBends). The group
# lays what one 30 column screen lays, and a bar runs past a screen's edge
# only across a seam into the next screen of the row, never past the wall.

def wide_and_group():
    """The 13, 13 and 4 column group of 192 x 384 px, 500 x 1000 mm panels,
    and one 30 column screen of the same panel below it."""
    panel = {'rows': 9, 'cabinet_width': 192, 'cabinet_height': 384,
             'panel_width_mm': 500, 'panel_height_mm': 1000}
    return [dict(panel, name=f'S{i + 1}', columns=c, offset_x=x, offset_y=0)
            for i, (c, x) in enumerate([(13, 0), (13, 2496), (4, 4992)])] + \
        [dict(panel, name='WIDE', columns=30, offset_x=0, offset_y=4000)]


def row_bars(page, ids):
    """The bars of a row of screens as [start, size] in the row's panels."""
    out, at = [], 0
    for i in ids:
        lay = layer(page, i)
        bars = lay.get('riggingBars') or []
        starts = lay.get('riggingBarStarts')
        run = 0
        for k, size in enumerate(bars):
            s = starts[k] if starts else run
            out.append([at + s, size])
            run = s + size
        at += lay['columns']
    return sorted(out)


def curve_wide_and_group(page, ids, settings):
    """The same Curve on the group and on the wide screen, each ticked on."""
    for pick in ([ids[3]], [ids[0]]):
        select(page, pick)
        for key, value in settings.items():
            page.evaluate("([k, v]) => window.app.setRiggingCurveField(k, v)", [key, value])
            idle(page)
        act(page, lambda: page.check('#rigging-curve-on'))


@pytest.mark.parametrize('settings', [
    {'value': 20, 'goal': 'simplest', 'from': 'center'},
    {'value': 30, 'goal': 'even', 'from': 'center'},
    {'value': 25, 'goal': 'simplest', 'from': 19},
    {'value': 25, 'goal': 'simplest', 'from': 25.5},
    {'value': 20, 'goal': 'tightest', 'from': 'center'},
], ids=['simplest-20-center', 'even-30-center', 'simplest-25-from-19', 'simplest-25-from-25.5', 'tightest-20-center'])
def test_a_13_13_4_group_lays_the_bars_one_30_column_screen_lays(page, settings):
    ids = reset(page, wide_and_group())
    group(page, ids[:3])
    open_rigging(page)
    curve_wide_and_group(page, ids, settings)
    lays = [layer(page, i) for i in ids]
    assert all((l.get('riggingCurve') or {}).get('on') for l in lays), [l.get('riggingCurve') for l in lays]
    assert all(l['riggingCurve'] == lays[3]['riggingCurve'] for l in lays), [l['riggingCurve'] for l in lays]
    wide = row_bars(page, [ids[3]])
    walled = row_bars(page, ids[:3])
    assert walled == wide, (walled, wide)
    # the same joints, seams included
    joints = own_joints(lays[0]) + [None] + own_joints(lays[1]) + [None] + own_joints(lays[2])
    want = own_joints(lays[3])
    assert [a for a, b in zip(joints, want) if a is not None] == [b for a, b in zip(joints, want) if a is not None]
    # every bend sits between two bars, and nothing runs past the wall
    starts = {s for s, _ in wide}
    assert all(s + n <= 30 for s, n in wide)
    for j, a in enumerate(want):
        if a:
            assert j + 1 in starts, (j, wide)
    # a bar past a screen's edge only carries on into the next screen
    for k, lay in enumerate(lays[:3]):
        for s, n in row_bars(page, [ids[k]]):
            assert s + n <= lay['columns'] + (0 if k == 2 else 1), (k, s, n)
    # between two bends: one single when the stretch is odd, else none
    cuts = [0] + [j + 1 for j, a in enumerate(want) if a] + [30]
    for lo, hi in zip(cuts, cuts[1:]):
        inside = [n for s, n in wide if lo <= s < hi]
        assert sum(inside) == hi - lo and inside.count(1) == (hi - lo) % 2, (lo, hi, wide)
    if settings['from'] == 'center' and want == want[::-1]:
        assert sorted([30 - s - n, n] for s, n in wide) == wide, wide
    # the first screen is not all singles
    if settings['goal'] != 'tightest':
        assert any(n == 2 for s, n in row_bars(page, [ids[0]])), row_bars(page, [ids[0]])
    assert page.errors == []


# ── Curve off hands the bars back to Auto ────────────────────────────────
#
# Owner's log (2026-11-18): on the 13, 13 and 4 column group, Curve On at
# 15% laid the Curve's bars (Screen1 all singles then); Curve Off left them,
# and the clicks after it (the Auto/Custom picker's Auto, Footer and Header,
# a lit size off and on) never lay bars, so the Curve's stayed on a wall
# that no longer curves. Curve off now lays the wall's Auto bars from its
# lit sizes, in the same undo step; a wall whose bars were laid by hand
# keeps them.

def curved_group(page, value=15):
    ids = reset(page, wide_and_group()[:3])
    group(page, ids)
    open_rigging(page)
    select(page, [ids[0]])
    page.evaluate("(v) => window.app.setRiggingCurveField('value', v)", value)
    idle(page)
    act(page, lambda: page.check('#rigging-curve-on'))
    return ids


AUTO_ROW = [[0, 2], [2, 2], [4, 2], [6, 2], [8, 2], [10, 2], [12, 2], [14, 2], [16, 2], [18, 2], [20, 2],
            [22, 2], [24, 2], [26, 2], [28, 2]]


def test_curve_off_lays_the_groups_auto_bars_in_the_same_step(page):
    ids = curved_group(page)
    curved = row_bars(page, ids)
    assert curved != AUTO_ROW, curved
    n = history_len(page)
    act(page, lambda: page.uncheck('#rigging-curve-on'))
    lays = [layer(page, i) for i in ids]
    assert not any(l['riggingCurve']['on'] for l in lays)
    # the Curve's bars are gone: Auto's, fifteen doubles across the seams
    assert row_bars(page, ids) == AUTO_ROW, row_bars(page, ids)
    assert lays[0]['riggingBars'] == [2] * 7 and lays[1]['riggingBarStarts'] == [1, 3, 5, 7, 9, 11]
    assert all(l.get('riggingCustom') is False for l in lays)
    assert all(not any(own_joints(l)) for l in lays)
    assert history_len(page) == n + 1
    # one undo puts the curve back, bars and all; redo takes it off again
    page.evaluate('window.app.undo()')
    back = settled(page, lambda: layer(page, ids[0]), lambda l: (l.get('riggingCurve') or {}).get('on'))
    assert back['riggingCurve']['on'] and row_bars(page, ids) == curved
    page.evaluate('window.app.redo()')
    settled(page, lambda: layer(page, ids[0]), lambda l: not (l.get('riggingCurve') or {}).get('on'))
    assert row_bars(page, ids) == AUTO_ROW
    # what he clicked next changes none of it
    page.click('#rigging-tool-picker [data-tool="auto"]')
    page.click('#rigging-mode-picker [data-mode="footer"]')
    page.click('#rigging-mode-picker [data-mode="header"]')
    page.wait_for_timeout(300)
    assert row_bars(page, ids) == AUTO_ROW
    assert page.errors == []


def test_curve_off_on_a_single_screen_lays_its_auto_bars(page):
    ids = reset(page, wide_and_group()[3:])
    open_rigging(page)
    page.evaluate("(v) => window.app.setRiggingCurveField('value', v)", 15)
    idle(page)
    act(page, lambda: page.check('#rigging-curve-on'))
    assert layer(page, ids[0])['riggingBars'] != [2] * 15
    act(page, lambda: page.uncheck('#rigging-curve-on'))
    lay = layer(page, ids[0])
    assert lay['riggingBars'] == [2] * 15 and not lay.get('riggingBarStarts')
    assert not any(own_joints(lay))
    assert page.errors == []


def test_after_curve_off_the_auto_button_still_lays_from_the_lit_sizes(page):
    """The Auto button (not the Auto/Custom picker) lays the lit sizes, the
    Curve's bars or not: the doubles alone, then singles and doubles."""
    ids = curved_group(page)
    act(page, lambda: page.uncheck('#rigging-curve-on'))
    page.click('#rigging-size-picker .rigging-size-btn[data-size="1"]')
    idle(page)
    assert layer(page, ids[0])['riggingSizes'] == [2]
    act(page, lambda: page.click('#rigging-tool-picker [data-tool="auto"]'))
    assert row_bars(page, ids) == AUTO_ROW
    assert page.errors == []


# ── a lit size lays a plain wall's Auto bars at once ────────────────────
#
# Owner's ruling (2026-11-18): on a plain header, lighting or unlighting a
# bar size lays the Auto bars again right away, the same as on a curved
# wall; a row laid by hand in Custom is left alone.

def size_click(page, size):
    page.click(f'#rigging-size-picker .rigging-size-btn[data-size="{size}"]')
    idle(page)


def test_a_lit_size_lays_a_groups_auto_bars_again_in_one_step(page):
    ids = reset(page, wide_and_group()[:3])
    group(page, ids)
    open_rigging(page)
    select(page, [ids[0]])
    act(page, lambda: page.click('#rigging-tool-picker [data-tool="auto"]'))
    assert row_bars(page, ids) == AUTO_ROW
    n = history_len(page)
    size_click(page, 2)
    # doubles off: singles across the whole wall, every screen's sizes too
    assert row_bars(page, ids) == [[p, 1] for p in range(30)], row_bars(page, ids)
    assert all(layer(page, i)['riggingSizes'] == [1] for i in ids)
    assert history_len(page) == n + 1
    size_click(page, 2)
    assert row_bars(page, ids) == AUTO_ROW
    assert history_len(page) == n + 2
    page.evaluate('window.app.undo()')
    settled(page, lambda: row_bars(page, ids), lambda b: b == [[p, 1] for p in range(30)])
    assert page.errors == []


def test_a_lit_size_lays_a_screen_again_and_says_when_it_cannot(page):
    ids = reset(page, wide_and_group()[:1])
    open_rigging(page)
    act(page, lambda: page.click('#rigging-tool-picker [data-tool="auto"]'))
    assert layer(page, ids[0])['riggingBars'] == [2, 2, 2, 1, 2, 2, 2]
    # doubles alone cannot make 13: the bars stay, and the tab says so
    size_click(page, 1)
    lay = layer(page, ids[0])
    assert lay['riggingSizes'] == [2] and lay['riggingBars'] == [2, 2, 2, 1, 2, 2, 2]
    assert 'No exact fit with these sizes: S1' in page.inner_text('#rigging-status')
    size_click(page, 1)
    assert layer(page, ids[0])['riggingBars'] == [2, 2, 2, 1, 2, 2, 2]
    assert page.inner_text('#rigging-status') == ''
    assert page.errors == []


def test_a_lit_size_leaves_a_custom_row_and_a_wall_with_no_bars(page):
    ids = reset(page, wide_and_group()[:1] + [dict(wide_and_group()[3], name='BARE', offset_y=5000)])
    open_rigging(page)
    select(page, [ids[0]])
    page.click('#rigging-tool-picker [data-tool="custom"]')
    page.evaluate("""(id) => { const a = window.app; const l = a.project.layers.find(x => x.id === id);
        a._riggingCustomSize = 2; const d = a.riggingBeginPlace(l, 'header', 0); a.riggingPreviewPlace(d, 3);
        a.riggingEndDrag(d, true); }""", ids[0])
    # Auto picked with nothing selected only picks the way of working
    page.evaluate("() => { window.app.setSelectedLayersByIds([], null); window.app.refreshRiggingPanel(); }")
    page.click('#rigging-tool-picker [data-tool="auto"]')
    select(page, [ids[0]])
    custom = layer(page, ids[0])
    assert custom['riggingCustom'] is True and custom['riggingBars'] == [2, 2]
    size_click(page, 2)
    assert layer(page, ids[0])['riggingBars'] == [2, 2]
    select(page, [ids[1]])
    size_click(page, 2)
    bare = layer(page, ids[1])
    assert bare['riggingSizes'] == [1] and not bare.get('riggingBars')
    assert page.errors == []


# ── the Auto / Custom switch lays the bars ──────────────────────────────
#
# Owner's ruling (2026-11-18): the separate Auto button is gone. Picking
# Auto on the Auto / Custom switch lays the selected screens' bars from the
# lit sizes at once, and picking it again lays them again: a group's row
# across its seams, a row laid by hand handed back to Auto.

def test_picking_auto_lays_the_bars_and_picking_it_again_lays_them_again(page):
    ids = reset(page, wide_and_group()[:3])
    group(page, ids)
    open_rigging(page)
    assert page.locator('#rigging-auto-btn').count() == 0
    select(page, [ids[0]])
    n = history_len(page)
    act(page, lambda: page.click('#rigging-tool-picker [data-tool="auto"]'))
    assert row_bars(page, ids) == AUTO_ROW
    assert history_len(page) == n + 1
    # Custom by hand, then Auto: the row is Auto's again, in one step
    page.click('#rigging-tool-picker [data-tool="custom"]')
    page.evaluate("""(id) => { const a = window.app; const l = a.project.layers.find(x => x.id === id);
        a._riggingCustomSize = 1; const d = a.riggingBeginPlace(l, 'header', 0); a.riggingPreviewPlace(d, 1);
        a.riggingEndDrag(d, true); }""", ids[0])
    assert layer(page, ids[0])['riggingCustom'] is True and row_bars(page, ids) != AUTO_ROW
    n = history_len(page)
    act(page, lambda: page.click('#rigging-tool-picker [data-tool="auto"]'))
    assert row_bars(page, ids) == AUTO_ROW and layer(page, ids[0])['riggingCustom'] is False
    assert history_len(page) == n + 1
    # picked again after a Clear: laid again
    page.click('#rigging-clear-btn')
    settled(page, lambda: row_bars(page, ids), lambda b: b == [])
    act(page, lambda: page.click('#rigging-tool-picker [data-tool="auto"]'))
    assert row_bars(page, ids) == AUTO_ROW
    assert page.errors == []
