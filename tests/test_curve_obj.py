"""The Header/Footer tab's Curve (app-curve.js) and Export > OBJ
(app-obj-export.js, obj-export.js), in the real app.

What this file pins:

* Ticking Curve lays the calculator's bars on the screen's side and writes
  the angle at every column joint into its 3D place, one undo step; the
  form's edits and the lit sizes lay it again; undo, redo and a reload keep
  every step; Custom and Remove Bar leave a curved screen alone; Clear turns
  the Curve off.
* A show without the Curve opens unchanged, and looking at the tab writes
  nothing.
* The OBJ export: one file per physical screen (a group is one file unless
  its Show Look Names switch is Screens; an ungrouped screen is its own),
  read back: the vertex count, a face per cabinet, texture coordinates
  inside the screen's spot in its canvas, the size in meters, and the
  angle at a curved joint measured off the vertices. The reference wall
  (sixteen 500 mm cabinets at 5 degrees a joint) reads the calculator's
  face radius and chord off the OBJ to 0.1 mm.
* The dialog lists the files and saves them straight to a folder.

Run locally:
    python -m pytest tests/test_curve_obj.py -v -p no:cacheprovider --browser chromium
"""
import json
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from conftest import settled  # noqa: E402


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
    # A real folder chooser must never open on the test machine.
    pg.route('**/api/native-dialog/**', lambda r: r.fulfill(status=503, body='{}'))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    yield pg
    context.close()


RESET_JS = """async (specs) => {
    const app = window.app;
    let project = await (await fetch('/api/project')).json();
    project.layers = [];
    project.groups = [];
    delete project.riggingTool;
    delete project.groupNameDisplayByView;
    delete project.groupNameDisplay;
    await fetch('/api/project', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(project),
    });
    const ids = [];
    for (const s of specs) {
        const made = await (await fetch('/api/layer/add', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(Object.assign({
                cabinet_width: 128, cabinet_height: 128,
                panel_width_mm: 500, panel_height_mm: 500,
            }, s)),
        })).json();
        ids.push(made.id);
    }
    app.project = await (await fetch('/api/project')).json();
    app.dedupeProjectLayers('curve_test_reset');
    if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
    app.resetHistory('Curve Test Reset');
    app.selectLayer(app.project.layers.find(l => l.id === ids[0]));
    app.updateUI();
    return ids;
}"""

WALL = {'name': 'WALL', 'columns': 16, 'rows': 2, 'offset_x': 0, 'offset_y': 0}


def reset(page, specs=(WALL,)):
    ids = page.evaluate(RESET_JS, list(specs))
    page.wait_for_timeout(300)
    return ids


def layer(page, layer_id):
    return page.evaluate("(id) => JSON.parse(JSON.stringify(window.app.project.layers.find(l => l.id === id)))", layer_id)


def served(page, layer_id):
    return page.evaluate("""async (id) => {
        const p = await (await fetch('/api/project')).json();
        return p.layers.find(l => l.id === id);
    }""", layer_id)


def open_rigging(page):
    page.click('#view-tabs .view-tab[data-mode="rigging"]')
    page.wait_for_timeout(200)


def singles_only(page):
    """Light singles alone: the calculator then has every joint to work with."""
    lit = page.evaluate("() => window.app._riggingSizesOf(window.app.currentLayer)")
    if 1 not in lit:
        page.click('#rigging-size-picker .rigging-size-btn[data-size="1"]')
    if 2 in lit:
        page.click('#rigging-size-picker .rigging-size-btn[data-size="2"]')
    page.wait_for_timeout(200)


def expected(page, layer_id):
    """The calculator's own answer for the screen as it stands."""
    return page.evaluate("""(id) => {
        const l = window.app.project.layers.find(x => x.id === id);
        const out = window.app.riggingCurveSolve(l);
        return { bars: out.bars, joints: out.joints, errors: out.errors };
    }""", layer_id)


def joints_of(lay):
    table = ((lay or {}).get('stage3d') or {}).get('jointsCol') or {}
    return [table.get(str(j)) for j in range(len(table))]


def history_len(page):
    return page.evaluate('window.app.history.length')


def toast_says(page, text):
    host = '#app-toast-host'
    return settled(page, lambda: page.inner_text(host) if page.query_selector(host) else '',
                   lambda t: text in t, 3000)


# ── the Curve on the Header/Footer tab ───────────────────────────────────

def test_the_curve_checkbox_lays_the_bars_and_the_angles(page):
    ids = reset(page)
    open_rigging(page)
    singles_only(page)
    before = history_len(page)
    assert page.is_visible('#rigging-curve-on')
    assert not page.is_visible('#rigging-curve-fields')
    page.check('#rigging-curve-on')
    lay = settled(page, lambda: layer(page, ids[0]),
                  lambda l: (l.get('riggingCurve') or {}).get('on') and l.get('stage3d'))
    want = expected(page, ids[0])
    assert want['errors'] == []
    # the calculator's headline case: sixteen 500 mm tiles at 20%
    assert lay['riggingBars'] == [1] * 16 == want['bars']
    assert joints_of(lay) == want['joints']
    assert sorted(set(want['joints'])) == [0, 7.5]
    assert want['joints'].count(7.5) == 9
    assert history_len(page) == before + 1
    # the form and the result show; the readouts read the built wall
    assert page.is_visible('#rigging-curve-fields')
    assert page.inner_text('#rigging-curve-head') == '7.5° at 9 joints, 6 flat'
    read = page.inner_text('#rigging-curve-readouts')
    assert '19.8% of a circle' in read and 'Off the drawing' in read
    assert page.locator('#rigging-curve-sheet svg rect[data-bar]').count() == 16
    assert page.locator('#rigging-curve-sheet svg text[data-angle]').count() == 9
    # the server holds the same
    srv = settled(page, lambda: served(page, ids[0]), lambda l: (l.get('riggingCurve') or {}).get('on'))
    assert srv['riggingCurve']['on'] is True and srv['riggingBars'] == [1] * 16
    assert joints_of(srv) == want['joints']
    assert page.errors == []


def test_each_edit_lays_it_again_and_undoes_one_step_at_a_time(page):
    ids = reset(page)
    open_rigging(page)
    singles_only(page)
    page.check('#rigging-curve-on')
    settled(page, lambda: layer(page, ids[0]), lambda l: (l.get('riggingCurve') or {}).get('on'))
    first = layer(page, ids[0])
    n = history_len(page)

    page.click('#rigging-curve-bend [data-value="convex"]')
    convex = settled(page, lambda: layer(page, ids[0]), lambda l: l['riggingCurve']['bend'] == 'convex')
    assert joints_of(convex) == [-a if a else 0 for a in joints_of(first)]

    page.click('#rigging-curve-goal [data-value="even"]')
    even = settled(page, lambda: layer(page, ids[0]), lambda l: l['riggingCurve']['goal'] == 'even')
    bent = [a for a in joints_of(even) if a]
    assert len(set(bent)) == 1, joints_of(even)

    # % to degrees says the same curve: 20% is 72 degrees, nothing moves
    page.click('#rigging-curve-entry [data-value="degrees"]')
    deg = settled(page, lambda: layer(page, ids[0]), lambda l: l['riggingCurve']['entry'] == 'degrees')
    assert deg['riggingCurve']['value'] == 72
    assert joints_of(deg) == joints_of(even)
    assert page.input_value('#rigging-curve-value') == '72'

    page.fill('#rigging-curve-angles', '5')
    page.press('#rigging-curve-angles', 'Enter')
    five = settled(page, lambda: layer(page, ids[0]), lambda l: l['riggingCurve']['angles'] == [5])
    assert set(joints_of(five)) <= {0, -5}

    # the lit sizes are the stock: doubles laid again in the same step
    page.click('#rigging-size-picker .rigging-size-btn[data-size="2"]')
    page.click('#rigging-size-picker .rigging-size-btn[data-size="1"]')
    doubles = settled(page, lambda: layer(page, ids[0]), lambda l: l['riggingBars'] == [2] * 8)
    assert doubles['riggingBars'] == [2] * 8
    assert all(joints_of(doubles)[j] == 0 for j in range(0, 15, 2)), joints_of(doubles)

    steps = history_len(page) - n
    assert steps == 6, steps
    # each undo takes back one of them, in order
    page.evaluate('window.app.undo()')
    back = settled(page, lambda: layer(page, ids[0]), lambda l: l['riggingBars'] != [2] * 8)
    assert back['riggingCurve']['angles'] == [5] and 1 in back['riggingSizes']
    for _ in range(5):
        page.evaluate('window.app.undo()')
        page.wait_for_timeout(250)
    back = settled(page, lambda: layer(page, ids[0]), lambda l: l['riggingCurve']['bend'] == 'concave')
    assert joints_of(back) == joints_of(first) and back['riggingBars'] == first['riggingBars']
    page.evaluate('window.app.undo()')
    off = settled(page, lambda: layer(page, ids[0]), lambda l: not (l.get('riggingCurve') or {}).get('on'))
    assert not (off.get('riggingCurve') or {}).get('on')
    assert not page.is_checked('#rigging-curve-on')
    page.evaluate('window.app.redo()')
    on = settled(page, lambda: layer(page, ids[0]), lambda l: (l.get('riggingCurve') or {}).get('on'))
    assert joints_of(on) == joints_of(first)
    assert page.errors == []


def test_a_reload_keeps_the_curve_and_the_tab_shows_it(page, e2e_server):
    ids = reset(page)
    open_rigging(page)
    singles_only(page)
    page.check('#rigging-curve-on')
    page.click('#rigging-curve-goal [data-value="tightest"]')
    laid = settled(page, lambda: served(page, ids[0]), lambda l: (l.get('riggingCurve') or {}).get('goal') == 'tightest')
    page.reload(wait_until='domcontentloaded')
    page.wait_for_timeout(2000)
    page.evaluate("(id) => { window.app.selectLayer(window.app.project.layers.find(l => l.id === id)); window.app.updateUI(); }", ids[0])
    open_rigging(page)
    lay = layer(page, ids[0])
    assert lay['riggingCurve'] == laid['riggingCurve']
    assert lay['riggingBars'] == laid['riggingBars'] and joints_of(lay) == joints_of(laid)
    assert page.is_checked('#rigging-curve-on')
    assert page.evaluate("document.querySelector('#rigging-curve-goal [data-value=\"tightest\"]').classList.contains('active')")
    assert page.errors == []


def test_custom_and_remove_bar_leave_a_curved_screen_alone_and_clear_turns_it_off(page):
    ids = reset(page)
    open_rigging(page)
    singles_only(page)
    page.check('#rigging-curve-on')
    lay = settled(page, lambda: layer(page, ids[0]), lambda l: (l.get('riggingCurve') or {}).get('on'))
    n = history_len(page)
    page.click('#rigging-tool-picker [data-tool="custom"]')
    assert 'Custom does not' in page.inner_text('#rigging-curve-note')
    refused = page.evaluate("(id) => window.app.riggingBeginPlace(window.app.project.layers.find(l => l.id === id), 'header', 3) === null", ids[0])
    assert refused
    assert 'laid by the Curve' in toast_says(page, 'laid by the Curve')
    page.evaluate("(id) => window.app.pickRiggingBar({ layerId: id, row: 'header', start: 0, span: 1 })", ids[0])
    assert page.evaluate('window.app.removePickedRiggingBar()') is False
    assert layer(page, ids[0])['riggingBars'] == lay['riggingBars']
    assert history_len(page) == n
    page.click('#rigging-tool-picker [data-tool="auto"]')
    # Auto on a curved screen lays the curve again, not a plain fit
    page.click('#rigging-auto-btn')
    page.wait_for_timeout(300)
    assert layer(page, ids[0])['riggingBars'] == lay['riggingBars']
    page.click('#rigging-clear-btn')
    off = settled(page, lambda: layer(page, ids[0]), lambda l: not l.get('riggingBars'))
    assert not off['riggingCurve']['on']
    assert joints_of(off) == []
    assert not page.is_checked('#rigging-curve-on')
    assert page.errors == []


def test_a_grouped_row_or_a_turned_screen_is_refused_and_named(page):
    ids = reset(page, [{'name': 'TURNED', 'columns': 6, 'rows': 2, 'offset_x': 0, 'offset_y': 0}])
    page.evaluate("(id) => { const l = window.app.project.layers.find(x => x.id === id); l.rotation = 90; window.app.updateLayers([l], false); }", ids[0])
    open_rigging(page)
    page.click('#rigging-curve-on')
    page.wait_for_timeout(300)
    assert not page.is_checked('#rigging-curve-on')
    assert 'TURNED cannot take a Curve' in toast_says(page, 'TURNED cannot take a Curve')
    assert not (layer(page, ids[0]).get('riggingCurve') or {}).get('on')

    # two grouped screens standing edge to edge share one row of bars
    ids = reset(page, [{'name': 'LEFT', 'columns': 4, 'rows': 2, 'offset_x': 0, 'offset_y': 0},
                       {'name': 'RIGHT', 'columns': 4, 'rows': 2, 'offset_x': 512, 'offset_y': 0}])
    group_two(page, ids)
    open_rigging(page)
    page.evaluate(f"window.app.setSelectedLayersByIds({ids}, {ids[0]})")
    page.click('#rigging-auto-btn')
    settled(page, lambda: layer(page, ids[0]).get('riggingBars'), bool)
    n = history_len(page)
    page.click('#rigging-curve-on')
    page.wait_for_timeout(300)
    said = toast_says(page, 'RIGHT cannot take a Curve')
    assert 'LEFT cannot take a Curve: its bars run across its group' in said, said
    assert not any((layer(page, i).get('riggingCurve') or {}).get('on') for i in ids)
    assert history_len(page) == n
    assert page.errors == []


def test_an_old_show_opens_unchanged_and_looking_writes_nothing(page):
    ids = reset(page, [WALL, {'name': 'OLD', 'columns': 8, 'rows': 2, 'offset_x': 0, 'offset_y': 400,
                              'riggingBars': [2, 2, 2, 2]}])
    old = served(page, ids[1])
    assert 'riggingCurve' not in old and 'stage3d' not in old
    page.evaluate("(id) => { window.app.selectLayer(window.app.project.layers.find(l => l.id === id)); window.app.updateUI(); }", ids[1])
    open_rigging(page)
    n = history_len(page)
    assert not page.is_checked('#rigging-curve-on')
    assert not page.is_visible('#rigging-curve-fields')
    page.click('#view-tabs .view-tab[data-mode="3d"]')
    page.wait_for_timeout(800)
    open_rigging(page)
    page.wait_for_timeout(300)
    now = served(page, ids[1])
    assert now == old
    assert history_len(page) == n
    assert page.errors == []


# ── Export > OBJ ──────────────────────────────────────────────────────────

def read_obj(text):
    out = {'v': [], 'vt': [], 'vn': [], 'objects': [], 'mtllib': None, 'comments': []}
    cur = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith('#'):
            out['comments'].append(line)
            continue
        tag, *rest = line.split()
        if tag == 'v':
            out['v'].append([float(x) for x in rest])
        elif tag == 'vt':
            out['vt'].append([float(x) for x in rest])
        elif tag == 'vn':
            out['vn'].append([float(x) for x in rest])
        elif tag == 'mtllib':
            out['mtllib'] = ' '.join(rest)
        elif tag == 'o':
            cur = {'name': ' '.join(rest), 'faces': [], 'material': None}
            out['objects'].append(cur)
        elif tag == 'usemtl':
            cur['material'] = ' '.join(rest)
        elif tag == 'f':
            cur['faces'].append([[int(i) for i in t.split('/')] for t in rest])
    return out


OBJ_FILES_JS = """async (name) => {
    const r = await window.app.objExportFiles(name);
    const out = {};
    for (const f of r.files) out[f.filename] = f.filename.endsWith('.png') ? f.blob.size : await f.blob.text();
    return out;
}"""


def obj_files(page, name='Test Show'):
    return page.evaluate(OBJ_FILES_JS, name)


def set_joints(page, layer_id, joints):
    page.evaluate("""([id, joints]) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === id);
        const p = app._s3dPlacementOf(l);
        const table = {};
        joints.forEach((a, j) => { table[String(j)] = a; });
        l.stage3d = { ...p, jointsCol: table };
        app.updateLayers([l], true, 'Test Joints');
    }""", [layer_id, joints])
    page.wait_for_timeout(200)


def group_two(page, ids):
    page.evaluate("""(ids) => window.app.project.layers.filter(l => ids.includes(l.id))
        .forEach(l => { l.processorType = 'brompton'; l.bitDepth = 10; l.frameRate = 60; })""", ids)
    page.evaluate(f"window.app.setSelectedLayersByIds({ids}, {ids[0]})")
    page.evaluate("() => { window.app.groupSelectedLayers(); }")
    assert settled(page, lambda: page.evaluate(
        f"window.app.project.layers.find(l => l.id === {ids[1]}).group_id"), bool)


def face_corners_xz(obj, row_top=True):
    """The front face's bottom edge, left to right, in plan (x, z): one
    point per corner along the wall from the faces of one row."""
    ys = sorted({round(v[1], 6) for v in obj['v']})
    base = ys[0]
    pts = []
    for face in obj['objects'][0]['faces']:
        bl, br = obj['v'][face[0][0] - 1], obj['v'][face[1][0] - 1]
        if abs(bl[1] - base) < 1e-6 and abs(br[1] - base) < 1e-6:
            pts.append((bl[0], bl[2], br[0], br[2]))
    pts.sort(key=lambda p: p[0])
    out = [(pts[0][0], pts[0][1])]
    for p in pts:
        out.append((p[2], p[3]))
    return out


def circumcenter(a, b, c):
    bx, by = b[0] - a[0], b[1] - a[1]
    cx, cy = c[0] - a[0], c[1] - a[1]
    d = 2 * (bx * cy - by * cx)
    return (a[0] + (cy * (bx * bx + by * by) - by * (cx * cx + cy * cy)) / d,
            a[1] + (bx * (cx * cx + cy * cy) - cx * (bx * bx + by * by)) / d)


def test_the_reference_wall_reads_the_calculator_radius_and_chord_off_the_obj(page):
    """Sixteen 500 mm cabinets at 5 degrees a joint, hinged at the front
    face: face radius 5.725941 m and chord 7.368141 m (the curve
    calculator's reference wall), read off the OBJ to 0.1 mm."""
    ids = reset(page, [WALL])
    set_joints(page, ids[0], [5] * 15)
    files = obj_files(page)
    obj = read_obj(files['Test_Show_WALL.obj'])
    pts = face_corners_xz(obj)
    assert len(pts) == 17
    chord = math.dist(pts[0], pts[-1])
    assert abs(chord - 7.368141) < 1e-4, chord
    c = circumcenter(pts[0], pts[8], pts[16])
    mids = [((pts[i][0] + pts[i + 1][0]) / 2, (pts[i][1] + pts[i + 1][1]) / 2) for i in range(16)]
    face_r = sum(math.dist(m, c) for m in mids) / 16
    assert abs(face_r - 5.725941) < 1e-4, face_r
    # concave: the ends come toward the audience (+Z)
    assert pts[0][1] > pts[8][1] and pts[16][1] > pts[8][1]


def test_an_obj_of_a_curved_screen_reads_back_right(page):
    ids = reset(page)
    open_rigging(page)
    singles_only(page)
    page.check('#rigging-curve-on')
    lay = settled(page, lambda: layer(page, ids[0]), lambda l: (l.get('riggingCurve') or {}).get('on'))
    files = obj_files(page)
    assert sorted(files) == ['Test_Show_Canvas_1_Pixel_Map.png', 'Test_Show_WALL.mtl', 'Test_Show_WALL.obj'], sorted(files)
    assert files['Test_Show_Canvas_1_Pixel_Map.png'] > 1000
    obj = read_obj(files['Test_Show_WALL.obj'])
    assert any('Units: meters' in c for c in obj['comments'])
    assert obj['mtllib'] == 'Test_Show_WALL.mtl'
    assert 'map_Kd Test_Show_Canvas_1_Pixel_Map.png' in files['Test_Show_WALL.mtl']
    # one face per cabinet, four corners each: split at every joint
    assert len(obj['objects']) == 1 and obj['objects'][0]['name'] == 'WALL'
    assert len(obj['objects'][0]['faces']) == 32
    assert len(obj['v']) == 128 and len(obj['vt']) == 128
    # the size in meters: every cabinet 0.5 x 0.5, the wall 1 m tall
    for face in obj['objects'][0]['faces']:
        bl, br, tr = (obj['v'][face[k][0] - 1] for k in range(3))
        assert abs(math.dist(bl, br) - 0.5) < 1e-6 and abs(math.dist(br, tr) - 0.5) < 1e-6
    ys = [v[1] for v in obj['v']]
    assert abs(max(ys) - min(ys) - 1.0) < 1e-6
    # texture coordinates inside the screen's spot in its canvas raster
    raster = page.evaluate("() => { const c = window.app.project.canvases[0]; return [c.raster_width, c.raster_height]; }")
    w_px, h_px = 16 * 128, 2 * 128
    for u, v in obj['vt']:
        assert -1e-9 <= u <= w_px / raster[0] + 1e-6
        assert 1 - h_px / raster[1] - 1e-6 <= v <= 1 + 1e-9
    us = sorted({round(t[0], 6) for t in obj['vt']})
    assert us[0] == 0 and abs(us[-1] - w_px / raster[0]) < 1e-6 and len(us) == 17
    # the angle at each joint, measured off the vertices, is the curve's
    pts = face_corners_xz(obj)
    for j, want in enumerate(joints_of(lay)):
        a, b, c = pts[j], pts[j + 1], pts[j + 2]
        h1 = math.atan2(b[1] - a[1], b[0] - a[0])
        h2 = math.atan2(c[1] - b[1], c[0] - b[0])
        # +Z is toward the audience: walking left to right, a concave bend
        # turns the heading toward it (the coordinates are written to the
        # micrometer, so the angle reads to a thousandth of a degree)
        turn = math.degrees(h2 - h1)
        assert abs(abs(turn) - abs(want)) < 1e-3, (j, turn, want)
        if want:
            assert (turn > 0) == (want > 0), (j, turn, want)
    assert page.errors == []


def test_a_group_is_one_file_unless_set_to_screens_and_a_loose_screen_is_its_own(page):
    ids = reset(page, [
        {'name': 'LEFT', 'columns': 4, 'rows': 2, 'offset_x': 0, 'offset_y': 0},
        {'name': 'RIGHT', 'columns': 4, 'rows': 2, 'offset_x': 512, 'offset_y': 0},
        {'name': 'SIDE', 'columns': 2, 'rows': 2, 'offset_x': 0, 'offset_y': 600},
    ])
    group_two(page, ids[:2])
    # the group has landed on the server before it is renamed, so no late
    # reply to the grouping puts the old name back
    served_groups = "fetch('/api/project').then(r => r.json()).then(p => (p.groups || []).map(g => g.name))"
    assert settled(page, lambda: page.evaluate(served_groups), lambda n: len(n) == 1, 5000)
    page.evaluate("async () => { await window.app.renameGroup(window.app.project.groups[0].id, 'CENTER'); }")
    assert settled(page, lambda: page.evaluate(served_groups), lambda n: n == ['CENTER'], 5000) == ['CENTER']
    assert settled(page, lambda: page.evaluate("window.app.project.groups.map(g => g.name)"), lambda n: n == ['CENTER']) == ['CENTER']
    files = obj_files(page)
    assert sorted(files) == ['Test_Show_CENTER.mtl', 'Test_Show_CENTER.obj', 'Test_Show_Canvas_1_Pixel_Map.png',
                             'Test_Show_SIDE.mtl', 'Test_Show_SIDE.obj'], sorted(files)
    center = read_obj(files['Test_Show_CENTER.obj'])
    assert [o['name'] for o in center['objects']] == ['LEFT', 'RIGHT']
    assert [len(o['faces']) for o in center['objects']] == [8, 8]
    assert {o['material'] for o in center['objects']} == {'Canvas_1'}
    assert any('Group: CENTER, 2 screens' in c for c in center['comments'])
    # each member keeps its own place in the canvas: RIGHT starts where LEFT ends
    left_u = [center['vt'][i - 1][0] for f in center['objects'][0]['faces'] for i in (k[1] for k in f)]
    right_u = [center['vt'][i - 1][0] for f in center['objects'][1]['faces'] for i in (k[1] for k in f)]
    assert abs(max(left_u) - min(right_u)) < 1e-9
    side = read_obj(files['Test_Show_SIDE.obj'])
    assert [o['name'] for o in side['objects']] == ['SIDE'] and len(side['objects'][0]['faces']) == 4

    # Both is still one physical screen; Screens is a file per member
    for value, want in (('both', 2), ('screens', 3)):
        page.evaluate("(v) => { const g = window.app.project.groups[0]; g.nameDisplayByView = { ...(g.nameDisplayByView || {}), 'show-look': v }; }", value)
        objs = sorted(n for n in obj_files(page) if n.endswith('.obj'))
        assert len(objs) == want, objs
    assert sorted(n for n in obj_files(page) if n.endswith('.obj')) == [
        'Test_Show_LEFT.obj', 'Test_Show_RIGHT.obj', 'Test_Show_SIDE.obj']
    assert page.errors == []


def test_the_dialog_lists_the_files_and_saves_them_to_a_folder(page):
    ids = reset(page)
    written = []

    def dialog(route):
        url = route.request.url
        if url.endswith('/available'):
            route.fulfill(status=200, body='{"ok": true}', content_type='application/json')
        elif url.endswith('/select-directory'):
            route.fulfill(status=200, body=json.dumps({'ok': True, 'path': 'C:/shows/out'}),
                          content_type='application/json')
        elif url.endswith('/write-file'):
            body = route.request.post_data_buffer or b''
            written.append(body)
            route.fulfill(status=200, body='{"ok": true}', content_type='application/json')
        else:
            route.fulfill(status=503, body='{}')

    page.unroute('**/api/native-dialog/**')
    page.route('**/api/native-dialog/**', dialog)
    try:
        page.evaluate("() => { window.app._hostCapabilityProbe = null; window.app._isHostClient = undefined; }")
        page.evaluate("() => window.app.openExportModal('obj')")
        page.wait_for_timeout(300)
        assert page.input_value('#export-format') == 'obj'
        assert page.is_visible('#export-obj-note')
        assert not page.is_visible('#export-views-section')
        assert not page.is_visible('#export-canvases-section')
        page.fill('#export-name', 'Tour')
        page.dispatch_event('#export-name', 'input')
        listed = page.inner_text('#export-preview').split('\n')
        assert listed == ['Tour_WALL.obj', 'Tour_WALL.mtl', 'Tour_Canvas_1_Pixel_Map.png'], listed
        page.click('#export-confirm')
        settled(page, lambda: len(written), lambda n: n >= 3, 10000)
        names = sorted(b.split(b'C:/shows/out/')[1].split(b'\r\n')[0].decode() for b in written)
        assert names == sorted(listed), names
        assert not page.is_visible('#export-modal')
    finally:
        page.unroute('**/api/native-dialog/**')
        page.route('**/api/native-dialog/**', lambda r: r.fulfill(status=503, body='{}'))
    assert page.errors == []
