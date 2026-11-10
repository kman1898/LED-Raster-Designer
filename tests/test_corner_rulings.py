"""Corners, the owner's rulings of 2026-11-09 (app-corners.js, the bars in
app-rigging.js and rigging-math.js, the shape in app-stage3d.js s3dBuild):

* Interior folds the sides toward the audience, Exterior away from them.
* The side at the Curve's build-from point stays put in 3D and the rest
  folds away from it; without a Curve the middle does. The OBJ is the same
  build.
* "Think of the 90 as the edge of a wall": a corner's seam carries no curve
  angle, the corner takes its place, and every other seam keeps its own,
  the ones either side of a folded panel too. The stored angles are left
  as they are. The Where list and the plan say so.
* Header and footer bars split at a corner: a "Header Bar - Corner" (or
  "Footer Bar - Corner") covers the panels touching it, the folded panel
  (250 mm + 250 mm on a 500 mm panel) or one either side of a seam (500 mm
  + 500 mm), regular bars fill the rest, and it is counted with the other
  bars on the tab, the pull sheet and the binder. In 3D it stands as an L.
  Since 2026-11-10 the 1 panel and the 2 panel piece are two parts,
  "Header Bar - Corner (1 panel)" and "(2 panel)", each its own line
  (tests/test_corner_bars.py has the rest of that day's rulings).
* Custom: a click on a corner's panels lays its corner bar, a bar beside a
  corner stops at it or is refused, a bar laid by hand on a corner's
  panels makes way for the corner bar, and Delete takes a picked one off.
* A footer that comes or goes because of a group change (not a bar edit)
  lifts or drops a placed screen's panels 6 in too.
* Shows without corners are unchanged.

Run locally:
    python -m pytest tests/test_corner_rulings.py -n 4 --dist loadfile -p no:cacheprovider
"""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from conftest import settled  # noqa: E402
from test_corners import (  # noqa: E402
    COLUMN, OBJ_FILES_JS, RESET_JS, corners_of, history_len, layer, open_3d, open_rigging, plan_turns,
    read_obj, row, s3d_quads, served,
)

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

FOOT_MM = 152.4


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project as this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1500, 'height': 950})
    context.add_init_script("try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.errors = []
    pg.on('pageerror', lambda err: pg.errors.append(str(err)))
    pg.route('**/api/native-dialog/**', lambda r: r.fulfill(status=503, body='{}'))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app._initialLoadComplete")
    pg.wait_for_timeout(1200)
    yield pg
    context.close()


def reset(page, specs=(COLUMN,)):
    page.evaluate("""() => { const t = document.querySelector('#view-tabs .view-tab[data-mode="pixel-map"]');
        if (t) t.click(); }""")
    page.wait_for_timeout(150)
    ids = page.evaluate(RESET_JS, [dict(s) for s in specs])
    page.evaluate("() => { const a = window.app; if (a._riggingToolNow() === 'custom') a.setRiggingTool('auto'); }")
    page.wait_for_timeout(300)
    return ids


def toasts(page):
    return page.evaluate("() => [...document.querySelectorAll('#app-toast-host *')].map(e => e.textContent).join(' | ')")


def clear_toasts(page):
    page.evaluate("() => { const h = document.getElementById('app-toast-host'); if (h) h.innerHTML = ''; }")


# The pure build of a 6 x 2 wall of 500 mm panels, as the corners make it.
BUILD_JS = """async (cases) => {
    const m = await import('/static/js/app-stage3d.js');
    const grid = (cols, rows) => {
        const panels = [];
        for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
            panels.push({row: r, col: c, x: c * 128, y: r * 128, width: 128, height: 128});
        }
        return {type: 'screen', columns: cols, rows, cabinet_width: 128, cabinet_height: 128,
                panel_width_mm: 500, panel_height_mm: 500, panels};
    };
    const flat = {x: 0, y: 0, z: 0, pitch: 0, yaw: 0, roll: 0, curveCol: 0, curveRow: 0,
                  jointsCol: {}, jointsRow: {}, pivot: 'bottom'};
    const out = {};
    for (const [name, c] of Object.entries(cases)) {
        const wall = {...grid(c.cols || 6, 2), riggingCorners: c.corners || [], riggingCurve: c.curve};
        const p = {...flat, jointsCol: c.joints || {}};
        const built = m.s3dBuild(wall, p);
        const bare = m.s3dBuild({...wall, riggingCorners: []}, p);
        const pick = (b) => b.quads.map(q => ({row: q.row, col: q.col, fold: q.fold === undefined ? null : q.fold,
                                                tl: q.tl, tr: q.tr, br: q.br, bl: q.bl}));
        out[name] = {quads: pick(built), bare: pick(bare), colJ: built.colJ,
                     seams: [...built.cornerSeams.keys()], anchor: m.s3dCornerAnchor(wall, c.cols || 6)};
    }
    return out;
}"""


def _same(a, b, tol=0.1):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def _fixed(case, cols):
    """True when every cabinet of columns `cols` stands where it stands
    without the corners, to 0.1 mm."""
    bare = {(q['row'], q['col']): q for q in case['bare']}
    for q in case['quads']:
        if q['col'] in cols:
            assert q['fold'] is None, q
            b = bare[(q['row'], q['col'])]
            for k in ('tl', 'tr', 'br', 'bl'):
                if not _same(q[k], b[k]):
                    return False
    return True


# ── 1. Interior and Exterior ─────────────────────────────────────────────

def test_interior_folds_the_sides_toward_the_audience_exterior_away(page):
    out = page.evaluate(BUILD_JS, {
        'seamIn': {'corners': [{'at': 4.5, 'angle': 90, 'side': 'interior'}]},
        'seamOut': {'corners': [{'at': 4.5, 'angle': 90, 'side': 'exterior'}]},
        'foldIn': {'corners': [{'at': 3, 'angle': 90, 'side': 'interior'}]},
        'foldOut': {'corners': [{'at': 3, 'angle': 90, 'side': 'exterior'}]},
    })
    for name, toward in (('seamIn', True), ('seamOut', False), ('foldIn', True), ('foldOut', False)):
        quads = [q for q in out[name]['quads'] if q['row'] == 1]
        quads.sort(key=lambda q: (q['col'], q['fold'] or 0))
        # the hinge: where panel 4 meets panel 5, or the fold in panel 3
        hinge = quads[3]['br'] if name.startswith('seam') else next(q for q in quads if q['col'] == 2 and q['fold'] == 0)['br']
        left, right = quads[0]['bl'], quads[-1]['br']
        # +Z is toward the audience. The side holding the build-from point
        # (the middle) stays on the line of the hinge; the other folds.
        fixed, folded = sorted([left, right], key=lambda p: abs(p[2] - hinge[2]))
        assert fixed[2] == pytest.approx(hinge[2], abs=0.1), (name, left, hinge, right)
        if toward:
            assert folded[2] > hinge[2] + 100, (name, left, hinge, right)
        else:
            assert folded[2] < hinge[2] - 100, (name, left, hinge, right)


# ── 2. The side at the build-from point stays put ────────────────────────

def test_the_build_from_side_stays_put_to_a_tenth_of_a_mm(page):
    five = {str(j): 5 for j in range(5)}
    out = page.evaluate(BUILD_JS, {
        # no curve: the middle (the seam between panels 3 and 4) stays put
        'none': {'corners': [{'at': 5, 'angle': 90}]},
        'noneL': {'corners': [{'at': 1.5, 'angle': 90}]},
        # a stored Build from on a Curve that is off is the middle too
        'off': {'corners': [{'at': 1.5, 'angle': 90}], 'curve': {'on': False, 'from': 'right'}},
        # the Curve's own Build from, with its angles on the other seams
        'left': {'corners': [{'at': 3.5, 'angle': 90}], 'joints': five, 'curve': {'on': True, 'from': 'left'}},
        'right': {'corners': [{'at': 2.5, 'angle': 90, 'side': 'exterior'}], 'joints': five,
                  'curve': {'on': True, 'from': 'right'}},
        'spot': {'corners': [{'at': 4, 'angle': 90}], 'joints': five, 'curve': {'on': True, 'from': 2}},
        'center': {'corners': [{'at': 4.5, 'angle': 90}], 'joints': five, 'curve': {'on': True, 'from': 'center'}},
        # a corner right on the build-from point folds both sides evenly
        'onIt': {'corners': [{'at': 3.5, 'angle': 90}]},
    })
    assert out['none']['anchor'] == 'center' and out['off']['anchor'] == 'center'
    assert out['left']['anchor'] == 'left' and out['spot']['anchor'] == 2
    assert _fixed(out['none'], {0, 1, 2, 3}) and not _fixed(out['none'], {5})
    assert _fixed(out['noneL'], {2, 3, 4, 5}) and not _fixed(out['noneL'], {0})
    assert _fixed(out['off'], {2, 3, 4, 5}) and not _fixed(out['off'], {0})
    assert _fixed(out['left'], {0, 1, 2}) and not _fixed(out['left'], {3})
    assert _fixed(out['right'], {2, 3, 4, 5}) and not _fixed(out['right'], {1})
    # from the middle of panel 2: panels 1 to 3 and the near half of panel 4
    assert _fixed(out['spot'], {0, 1, 2}) and not _fixed(out['spot'], {4})
    bare = {(q['row'], q['col']): q for q in out['spot']['bare']}
    half = next(q for q in out['spot']['quads'] if (q['row'], q['col'], q['fold']) == (1, 3, 0))
    assert _same(half['bl'], bare[(1, 3)]['bl']) and _same(half['tl'], bare[(1, 3)]['tl'])
    assert _fixed(out['center'], {0, 1, 2, 3}) and not _fixed(out['center'], {4})
    # on the build-from point itself: the hinge stays, the sides mirror
    quads = sorted((q for q in out['onIt']['quads'] if q['row'] == 1), key=lambda q: q['col'])
    hinge = quads[2]['br']
    bare = {(q['row'], q['col']): q for q in out['onIt']['bare']}
    assert _same(hinge, bare[(1, 2)]['br'])
    left, right = quads[0]['bl'], quads[-1]['br']
    assert left[0] == pytest.approx(-right[0], abs=0.1) and left[2] == pytest.approx(right[2], abs=0.1)
    assert page.errors == []


def test_the_fixed_side_stays_put_on_the_3d_tab_and_in_the_obj(page):
    """A screen placed and turned on the stage, its Curve on and built from
    the left: Add corner (between panels 3 and 4) leaves panels 1 to 3
    where they stood, cabinet for cabinet, on the 3D tab and in the OBJ.
    The Curve lays its bars again around the corner (2026-11-10); a curve
    of 0% lays every joint flat, so only the fold moves anything."""
    flat = {str(j): 0 for j in range(5)}
    spec = dict(COLUMN, extra={
        'riggingCurve': {'on': True, 'from': 'left', 'value': 0},
        'stage3d': {'x': 1200, 'y': 300, 'z': -800, 'pitch': 0, 'yaw': 0, 'roll': 0,
                    'jointsCol': flat, 'pivot': 'bottom'},
    })
    ids = reset(page, [spec])
    open_3d(page, 1)
    before = settled(page, lambda: s3d_quads(page, ids[0]), lambda q: q and len(q) == 12)
    obj_before = read_obj(page.evaluate(OBJ_FILES_JS, 'Rulings')['Rulings_COLUMN.obj'])
    open_rigging(page)
    page.click('#rigging-corner-add')
    # the Curve lays its bars and the corner bar around the corner
    got = settled(page, lambda: corners_of(page, ids[0]),
                  lambda v: v and v[0].get('bar') and page.evaluate('!window.app.riggingCurveBusy()'), 15000)
    assert got == [{'at': 3.5, 'angle': 90, 'side': 'interior', 'bar': True}]
    # the block says which side stays put
    assert 'the left end stays put' in page.inner_text('#rigging-corner-hold')
    open_3d(page, 1)
    after = settled(page, lambda: s3d_quads(page, ids[0]),
                    lambda q: q and not _same(q[-1]['corners'][1], before[-1]['corners'][1], 1))
    was = {(q['row'], q['col']): q['corners'] for q in before}
    for q in after:
        moved = any(not _same(a, b) for a, b in zip(q['corners'], was[(q['row'], q['col'])]))
        assert moved == (q['col'] >= 3), (q['row'], q['col'])
    # the OBJ: every point of panels 1 to 3 is where it was, to 0.1 mm
    obj_after = read_obj(page.evaluate(OBJ_FILES_JS, 'Rulings')['Rulings_COLUMN.obj'])
    x0 = min(v[0] for v in obj_before['v'])
    left = [v for v in obj_before['v'] if v[0] <= x0 + 1.5 + 1e-6]
    assert len(left) >= 8
    for v in left:
        assert any(_same(v, w, 1e-4) for w in obj_after['v']), v
    far = max(obj_before['v'], key=lambda v: v[0])
    assert not any(_same(far, w, 1e-4) for w in obj_after['v'])
    assert page.errors == []


# ── 3. A corner's seam takes no curve angle ──────────────────────────────

def test_a_corners_seam_takes_no_curve_angle_and_the_other_seams_keep_theirs(page):
    five = {str(j): 5 for j in range(5)}
    out = page.evaluate(BUILD_JS, {
        'seam': {'corners': [{'at': 3.5, 'angle': 90}], 'joints': five},
        'fold': {'corners': [{'at': 3, 'angle': 90}], 'joints': five},
        'bare': {'joints': five},
    })
    _, turns = plan_turns(out['seam']['quads'], 1)
    assert turns == [pytest.approx(5), pytest.approx(5), pytest.approx(90), pytest.approx(5), pytest.approx(5)]
    assert out['seam']['colJ'] == [5, 5, 90, 5, 5] and out['seam']['seams'] == [2]
    # down a panel's middle: the seams either side of that panel keep 5
    _, turns = plan_turns(out['fold']['quads'], 1)
    assert turns == [pytest.approx(5), pytest.approx(5), pytest.approx(90), pytest.approx(5),
                     pytest.approx(5), pytest.approx(5)]
    assert out['fold']['colJ'] == [5, 5, 5, 5, 5] and out['fold']['seams'] == []
    _, turns = plan_turns(out['bare']['quads'], 1)
    assert turns == [pytest.approx(5)] * 5


def test_the_where_list_the_note_and_the_plan_show_the_seam_has_no_curve_angle(page):
    five = {str(j): 5 for j in range(5)}
    ids = reset(page, [dict(COLUMN, extra={'stage3d': {'x': 0, 'y': 0, 'z': 0, 'pitch': 0, 'yaw': 0, 'roll': 0,
                                                        'jointsCol': five, 'pivot': 'bottom'}})])
    open_rigging(page)
    page.click('#rigging-corner-add')
    sel = f"{row(page, 3.5)} [data-corner-at] option"
    labels = page.evaluate(f"Object.fromEntries([...document.querySelectorAll('{sel}')].map(o => [o.value, o.textContent]))")
    assert labels['3.5'] == 'Between panels 3 and 4, curve 5°'
    assert labels['1.5'] == 'Between panels 1 and 2, curve 5°'
    assert labels['1'] == 'Middle of panel 1'
    note = page.inner_text(f"{row(page, 3.5)} .rigging-corner-replaces")
    assert 'no curve angle' in note and '5°' in note
    # the plan: one red corner, four grey seams the curve bends
    assert page.locator('#rigging-corner-plan svg [data-corner-dot]').count() == 1
    assert page.locator('#rigging-corner-plan svg [data-curve-dot]').count() == 4
    # the stored angles are left as they are
    assert layer(page, ids[0])['stage3d']['jointsCol'] == five
    # moved to the middle of panel 3: no seam is a corner, the note goes
    page.select_option(f'{row(page, 3.5)} [data-corner-at]', '3')
    settled(page, lambda: corners_of(page, ids[0]), lambda v: v[0]['at'] == 3)
    page.wait_for_timeout(150)
    assert page.locator(f"{row(page, 3)} .rigging-corner-replaces").count() == 0
    assert page.locator('#rigging-corner-plan svg [data-curve-dot]').count() == 5
    # the Curve's strip says Corner on a corner's seam, never its angle
    strip = page.evaluate("""() => { const a = window.app; const host = document.createElement('div');
        document.body.appendChild(host);
        a._curveDrawSheet(host, { bars: [1, 1, 1, 1, 1, 1], joints: [5, 5, 5, 5, 5], result: { datum_at: 3.5 } },
                          new Map([[2, { at: 3.5 }]]));
        const out = { corner: [...host.querySelectorAll('[data-corner-seam]')].map(t => [t.getAttribute('data-corner-seam'), t.textContent]),
                      angles: [...host.querySelectorAll('[data-angle]')].map(t => t.getAttribute('data-angle')) };
        host.remove(); return out; }""")
    assert strip == {'corner': [['2', 'Corner']], 'angles': ['0', '1', '3', '4']}
    assert page.errors == []


# ── 4. Corner bars ───────────────────────────────────────────────────────

def bars3d(page, layer_id):
    d = page.evaluate('window.app._s3dDebug()')
    return next(s for s in d['screens'] if s['id'] == layer_id)['bars']


def _len(q):
    return math.dist(q['bl'], q['br'])


def _cos(a, b):
    u = [a['br'][k] - a['bl'][k] for k in range(3)]
    v = [b['br'][k] - b['bl'][k] for k in range(3)]
    return sum(x * y for x, y in zip(u, v)) / (math.hypot(*u) * math.hypot(*v))


def pull_rig(page):
    return page.evaluate("""() => window.app.buildPullSheet().totals.filter(t => t.side === 'rigging')
        .map(t => [t.type, t.qty])""")


BINDER = {'sheet': 'tabloid', 'palette': 'colour', 'sides': {'power': False, 'data': False},
          'scope': {'kind': 'show'}, 'cover': False, 'pull': True, 'hardware': False,
          'wiring': False, 'rigging': True, 'titleBlock': True}


def binder_texts(page):
    return page.evaluate("""(o) => { const a = window.app; const plan = a.planBinder(o);
        const i = plan.findIndex(x => x.kind === 'rigging');
        const j = plan.findIndex(x => x.kind === 'pull');
        return { sheet: i < 0 ? [] : a.renderBinderPage(o, i).texts, pull: j < 0 ? [] : a.renderBinderPage(o, j).texts }; }""",
                         BINDER)


def test_corner_bars_for_a_mid_panel_corner_and_a_seam_corner(page):
    ids = reset(page, [dict(COLUMN, extra={'riggingSizes': [1, 2]})])
    open_rigging(page)
    page.click('#rigging-corner-add')
    page.select_option(f'{row(page, 3.5)} [data-corner-at]', '3')
    settled(page, lambda: corners_of(page, ids[0]), lambda v: v[0]['at'] == 3)
    n = history_len(page)
    page.click('#rigging-auto-btn')
    # down the middle of panel 3: the corner bar is that panel, a double
    # on panels 1 and 2, a single and a double on 4 to 6
    lay = settled(page, lambda: layer(page, ids[0]), lambda v: v.get('riggingBars'))
    assert lay['riggingBars'] == [2, 1, 2] and lay['riggingBarStarts'] == [0, 3, 4]
    assert lay['riggingCorners'] == [{'at': 3, 'angle': 90, 'side': 'interior', 'bar': True}]
    assert history_len(page) == n + 1
    assert page.inner_text('#rigging-total-count') == '4'
    assert page.inner_text('#rigging-total-breakdown').split('\n') == ['Double: 2', 'Single: 1', 'Corner (1 panel): 1']
    assert sorted(pull_rig(page)) == [['Header Bar - Corner (1 panel)', 1], ['Header Bar - Double', 2], ['Header Bar - Single', 1]]
    assert not page.locator('#rigging-fit-warning').is_visible()
    # the Header/Footer tab draws it, a hit of its own
    hits = page.evaluate("() => { window.canvasRenderer.render(); return window.canvasRenderer._riggingHits.map(h => [h.start, h.span, h.corner == null ? null : h.corner]); }")
    assert [2, 1, 3] in hits
    # in 3D: an L of 250 mm + 250 mm at right angles, touching the panels
    open_3d(page, 1)
    rows = settled(page, lambda: bars3d(page, ids[0]), lambda r: r and r[0]['corners'].count(True) == 1)
    head = rows[0]
    assert head['corners'] == [False, True, False, False]
    piece = [q for q in head['quads'] if q['slot'] == 2]
    assert len(piece) == 2 and [_len(q) for q in piece] == [pytest.approx(250, abs=0.01)] * 2
    assert _cos(piece[0], piece[1]) == pytest.approx(0, abs=1e-4)
    # touching the panels: in the screen's own frame its foot is the top
    # of the two 500 mm rows, and it stands 3.5 in tall
    assert head['heightMm'] == pytest.approx(88.9)
    for q in piece:
        assert q['bl'][1] == pytest.approx(1000, abs=0.01) and q['br'][1] == pytest.approx(1000, abs=0.01)
        assert q['tl'][1] == pytest.approx(1088.9, abs=0.01)
    # on the seam between panels 3 and 4: one panel either side, 500 + 500
    open_rigging(page)
    page.select_option(f'{row(page, 3)} [data-corner-at]', '3.5')
    lay = settled(page, lambda: layer(page, ids[0]), lambda v: v['riggingCorners'][0]['at'] == 3.5)
    assert lay['riggingBars'] == [2, 2] and lay['riggingBarStarts'] == [0, 4]
    assert lay['riggingCorners'] == [{'at': 3.5, 'angle': 90, 'side': 'interior', 'bar': True}]
    assert page.inner_text('#rigging-total-breakdown').split('\n') == ['Double: 2', 'Corner (2 panel): 1']
    assert page.inner_text('#rigging-total-count') == '3'
    open_3d(page, 1)
    rows = settled(page, lambda: bars3d(page, ids[0]), lambda r: r and r[0]['starts'] == [0, 2, 4])
    piece = [q for q in rows[0]['quads'] if q['slot'] in (2, 3)]
    assert [_len(q) for q in piece] == [pytest.approx(500, abs=0.01)] * 2
    assert _cos(piece[0], piece[1]) == pytest.approx(0, abs=1e-4)
    assert _same(piece[0]['br'], piece[1]['bl'], 0.001)
    # the binder's Header/Footer sheet and its pull sheet list it with the bars
    out = binder_texts(page)
    head = out['sheet'][out['sheet'].index('HEADER BARS'):]
    i = head.index('Header Bar - Corner (2 panel)')
    assert head[i + 1:i + 3] == ['2', '1'], head
    assert head[head.index('Total') + 1:head.index('Total') + 3] in (['', '3'], ['3']), head
    assert 'Header Bar - Corner (2 panel)' in out['pull'] and 'Header Bar - Double' in out['pull']
    # on the footer side it is the Footer Bar - Corner (2 panel)
    open_rigging(page)
    page.click('#rigging-mode-picker .rigging-mode-btn[data-mode="footer"]')
    settled(page, lambda: pull_rig(page), lambda r: ['Footer Bar - Corner (2 panel)', 1] in r)
    assert sorted(pull_rig(page)) == [['Footer Bar - Corner (2 panel)', 1], ['Footer Bar - Double', 2]]
    # Clear takes the corner bar off with the rest
    page.click('#rigging-clear-btn')
    lay = settled(page, lambda: layer(page, ids[0]), lambda v: not v.get('riggingFooterBars'))
    assert lay['riggingCorners'] == [{'at': 3.5, 'angle': 90, 'side': 'interior'}]
    assert pull_rig(page) == []
    assert page.errors == []


def test_moving_or_taking_off_a_corner_lays_an_auto_row_again(page):
    ids = reset(page, [dict(COLUMN, extra={'riggingSizes': [2]})])
    open_rigging(page)
    page.click('#rigging-auto-btn')
    settled(page, lambda: layer(page, ids[0]), lambda v: v.get('riggingBars') == [2, 2, 2])
    n = history_len(page)
    # Add corner (between panels 3 and 4) splits the row in the same step
    page.click('#rigging-corner-add')
    lay = settled(page, lambda: layer(page, ids[0]), lambda v: v.get('riggingBars') == [2, 2])
    assert lay['riggingBarStarts'] == [0, 4] and lay['riggingCorners'][0].get('bar') is True
    assert history_len(page) == n + 1
    # off again: the row runs end to end as before
    page.click(f'{row(page, 3.5)} [data-corner-remove]')
    lay = settled(page, lambda: layer(page, ids[0]), lambda v: v.get('riggingBars') == [2, 2, 2])
    assert lay.get('riggingBarStarts') is None and lay['riggingCorners'] == []
    assert history_len(page) == n + 2
    # undo brings back the split row and its corner bar, in one step
    page.evaluate('window.app.undo()')
    lay = settled(page, lambda: layer(page, ids[0]), lambda v: v.get('riggingBars') == [2, 2])
    assert lay['riggingCorners'][0].get('bar') is True
    assert page.errors == []


def test_custom_lays_the_corner_bar_and_stops_bars_at_the_corner(page):
    ids = reset(page, [dict(COLUMN, extra={'riggingCorners': [{'at': 3.5, 'angle': 90, 'side': 'interior'}]})])
    open_rigging(page)
    page.evaluate("() => window.app.setRiggingTool('custom')")
    lay_js = """([id, from, to, size]) => { const a = window.app; a._riggingCustomSize = size;
        const l = a.project.layers.find(x => x.id === id);
        const d = a.riggingBeginPlace(l, 'header', from); if (!d) return null;
        a.riggingPreviewPlace(d, to); a.riggingEndDrag(d, true);
        const k = a.project.layers.find(x => x.id === id);
        return { bars: a.riggingPlaced(k, 'header').map(b => [b.start, b.size]),
                 corner: a.riggingCornerPiecesOf(k).map(p => [p.at, p.start, p.size]) }; }"""
    # a click on a corner's panel lays its corner bar, nothing else
    assert page.evaluate(lay_js, [ids[0], 3, 3, 2]) == {'bars': [], 'corner': [[3.5, 2, 2]]}
    # a double clicked on panel 2 (0-based 1) stops at the corner: panels 1 and 2
    assert page.evaluate(lay_js, [ids[0], 1, 1, 2]) == {'bars': [[0, 2]], 'corner': [[3.5, 2, 2]]}
    # a quad has no room between the corner and the right edge: refused, said
    clear_toasts(page)
    n = history_len(page)
    assert page.evaluate(lay_js, [ids[0], 5, 5, 4]) == {'bars': [[0, 2]], 'corner': [[3.5, 2, 2]]}
    assert 'does not fit between this corner' in toasts(page)
    assert history_len(page) == n
    # Delete on a picked corner bar takes it off, one step
    page.evaluate("""(id) => { const a = window.app;
        a.pickRiggingBar({ layerId: id, row: 'header', start: 2, span: 2, corner: 3.5 });
        a.riggingDeleteKey(); }""", ids[0])
    lay = settled(page, lambda: layer(page, ids[0]), lambda v: not v['riggingCorners'][0].get('bar'))
    assert lay['riggingBars'] == [2]
    assert history_len(page) == n + 1
    # a drag across the corner lays doubles on each side and the corner bar
    page.evaluate("(id) => { const a = window.app; const l = a.project.layers.find(x => x.id === id); a._riggingWrite(l, 'header', []); }", ids[0])
    assert page.evaluate(lay_js, [ids[0], 0, 5, 2]) == {'bars': [[0, 2], [4, 2]], 'corner': [[3.5, 2, 2]]}
    # nothing on a corner's panels is counted twice
    assert sorted(pull_rig(page)) == [['Header Bar - Corner (2 panel)', 1], ['Header Bar - Double', 2]]
    assert page.errors == []


def test_a_bar_laid_by_hand_across_a_new_corner_makes_way_for_the_corner_bar(page):
    ids = reset(page)
    open_rigging(page)
    page.evaluate("() => window.app.setRiggingTool('custom')")
    page.evaluate("""(id) => { const a = window.app; a._riggingCustomSize = 2;
        const l = a.project.layers.find(x => x.id === id);
        for (const at of [0, 2]) { const d = a.riggingBeginPlace(l, 'header', at); a.riggingPreviewPlace(d, at); a.riggingEndDrag(d, true); } }""",
                  ids[0])
    assert layer(page, ids[0])['riggingBars'] == [2, 2]
    clear_toasts(page)
    page.click('#rigging-corner-add')
    lay = settled(page, lambda: layer(page, ids[0]), lambda v: v.get('riggingCorners'))
    # the double on panels 3 and 4 is where the corner bar goes: it makes way
    assert lay['riggingBars'] == [2]
    assert lay['riggingCorners'] == [{'at': 3.5, 'angle': 90, 'side': 'interior', 'bar': True}]
    assert 'made way for the Header Bar - Corner (2 panel)' in toasts(page)
    assert sorted(pull_rig(page)) == [['Header Bar - Corner (2 panel)', 1], ['Header Bar - Double', 1]]
    assert page.errors == []


def test_panels_a_corner_bar_leaves_bare_in_a_custom_row_are_named(page):
    """QA, 2026-11-10: in a custom row a corner's bar takes the place of the
    bars laid by hand on its panels; moved on (or taken off), it left those
    panels with no bar and nothing said so, since a custom row may have
    gaps. The panels it leaves bare are named, with what to do."""
    ids = reset(page)
    open_rigging(page)
    page.evaluate("() => window.app.setRiggingTool('custom')")
    page.evaluate("""(id) => { const a = window.app; a._riggingCustomSize = 2;
        const l = a.project.layers.find(x => x.id === id);
        for (const at of [0, 2, 4]) { const d = a.riggingBeginPlace(l, 'header', at); a.riggingPreviewPlace(d, at); a.riggingEndDrag(d, true); } }""",
                  ids[0])
    assert layer(page, ids[0])['riggingBars'] == [2, 2, 2]
    page.click('#rigging-corner-add')
    lay = settled(page, lambda: layer(page, ids[0]), lambda v: v.get('riggingCorners'))
    assert lay['riggingBars'] == [2, 2] and lay['riggingBarStarts'] == [0, 4]
    # moved one seam right: its bar now covers panels 4 and 5, the double
    # there makes way, and panel 3 is left with nothing on it
    clear_toasts(page)
    page.evaluate("() => window.app.setRiggingCorner(3.5, 'at', 4.5)")
    lay = settled(page, lambda: layer(page, ids[0]), lambda v: v['riggingCorners'][0]['at'] == 4.5)
    assert lay['riggingBars'] == [2] and lay['riggingCorners'][0].get('bar') is True
    said = settled(page, lambda: toasts(page), lambda s: 'Panel 3 of COLUMN' in s)
    assert 'Panel 3 of COLUMN is left without a header bar' in said, said
    # taken off: its two panels are left bare too
    clear_toasts(page)
    page.click(f'{row(page, 4.5)} [data-corner-remove]')
    settled(page, lambda: layer(page, ids[0]), lambda v: v['riggingCorners'] == [])
    said = settled(page, lambda: toasts(page), lambda s: 'of COLUMN' in s)
    assert 'Panels 4 and 5 of COLUMN are left without a header bar' in said, said
    assert page.errors == []


def test_a_row_crossing_a_corner_says_so_and_auto_splits_it(page):
    """Bars stored across a corner (a show from before corner bars, or
    laid while the Curve owned the bars) are never changed silently: the
    tab says they cross a corner, and Auto splits them."""
    ids = reset(page, [dict(COLUMN, extra={'riggingBars': [2, 2, 2], 'riggingSizes': [2],
                                           'riggingCorners': [{'at': 3.5, 'angle': 90, 'side': 'interior', 'bar': True}]})])
    open_rigging(page)
    assert page.locator('#rigging-fit-warning').is_visible()
    assert 'cross a corner' in page.inner_text('#rigging-fit-text')
    page.click('#rigging-fit-auto')
    lay = settled(page, lambda: layer(page, ids[0]), lambda v: v.get('riggingBars') == [2, 2])
    assert lay['riggingBarStarts'] == [0, 4]
    assert not page.locator('#rigging-fit-warning').is_visible()
    assert page.errors == []


# ── 5. The footer lift on a group change ─────────────────────────────────

PLACED = {'x': 2000, 'y': 0, 'z': 0, 'pitch': 0, 'yaw': 0, 'roll': 0, 'pivot': 'bottom'}


def test_a_footer_a_group_change_brings_lifts_the_placed_member_and_undo_drops_it(page):
    """WALL-L's footer runs a double past its own edge; grouped with
    WALL-R, edge to edge, that double stands under WALL-R too, so WALL-R,
    already placed in 3D, lifts 6 in. Undo drops it back. Hiding WALL-L
    takes its bar off WALL-R, which drops back too."""
    ids = reset(page, [
        {'name': 'WALL-L', 'columns': 3, 'rows': 2, 'extra': {'riggingFooterBars': [2, 2], 'riggingSide': 'footer',
                                                              'riggingCustom': True}},
        {'name': 'WALL-R', 'columns': 3, 'rows': 2, 'offset_x': 384,
         'extra': {'riggingSide': 'footer', 'stage3d': dict(PLACED)}},
    ])
    L, R = ids
    assert layer(page, R)['stage3d']['y'] == 0
    n = history_len(page)
    page.evaluate(f"async () => {{ const a = window.app; a.setSelectedLayersByIds([{L}, {R}], {L}); await a.groupSelectedLayers(); }}")
    lifted = settled(page, lambda: layer(page, R)['stage3d'], lambda s: s['y'] > 1)
    assert lifted['y'] == pytest.approx(FOOT_MM, abs=0.002) and lifted['x'] == 2000 and lifted['z'] == 0
    assert history_len(page) == n + 1
    assert settled(page, lambda: served(page, R)['stage3d'], lambda s: s['y'] > 1)['y'] == pytest.approx(FOOT_MM, abs=0.002)
    # undo takes the group and the lift back together; redo brings both
    page.evaluate('window.app.undo()')
    assert settled(page, lambda: layer(page, R)['stage3d'], lambda s: s['y'] < 1)['y'] == 0
    page.evaluate('window.app.redo()')
    assert settled(page, lambda: layer(page, R)['stage3d'], lambda s: s['y'] > 1)['y'] == pytest.approx(FOOT_MM, abs=0.002)
    # WALL-L hidden: its double no longer stands under WALL-R, which drops
    page.evaluate(f"window.app.toggleLayerVisibility({L})")
    assert settled(page, lambda: layer(page, R)['stage3d'], lambda s: s['y'] < 1)['y'] == pytest.approx(0, abs=0.002)
    assert settled(page, lambda: served(page, R)['stage3d'], lambda s: s['y'] < 1)['y'] == pytest.approx(0, abs=0.002)
    # shown again, it lifts again; ungrouped, it drops again
    page.evaluate(f"window.app.toggleLayerVisibility({L})")
    assert settled(page, lambda: layer(page, R)['stage3d'], lambda s: s['y'] > 1)['y'] == pytest.approx(FOOT_MM, abs=0.002)
    page.evaluate(f"""async () => {{ const a = window.app; const g = a.project.layers.find(l => l.id === {L}).group_id;
        await a.ungroupSelectedLayers(g); }}""")
    assert settled(page, lambda: layer(page, R)['stage3d'], lambda s: s['y'] < 1)['y'] == pytest.approx(0, abs=0.002)
    assert page.errors == []


# ── 6. Shows without corners ─────────────────────────────────────────────

def test_a_show_without_corners_builds_counts_and_saves_as_before(page):
    five = {str(j): 5 for j in range(5)}
    ids = reset(page, [dict(COLUMN, extra={'riggingBars': [2, 2, 2], 'riggingSizes': [2],
                                           'riggingCurve': {'on': True, 'from': 'left'},
                                           'stage3d': dict(PLACED, jointsCol=five)})])
    before = served(page, ids[0])
    # the build-from point only moves a screen that has corners
    out = page.evaluate("""async (id) => { const m = await import('/static/js/app-stage3d.js');
        const l = window.app.project.layers.find(x => x.id === id);
        const p = window.app._s3dPlacementOf(l);
        const a = m.s3dBuild(l, p).quads.map(q => [q.tl, q.br]);
        const b = m.s3dBuild({ ...l, riggingCurve: undefined }, p).quads.map(q => [q.tl, q.br]);
        return { same: JSON.stringify(a) === JSON.stringify(b), n: a.length }; }""", ids[0])
    assert out == {'same': True, 'n': 12}
    open_rigging(page)
    assert pull_rig(page) == [['Header Bar - Double', 3]]
    assert page.inner_text('#rigging-total-breakdown') == 'Double: 3'
    assert page.locator('#rigging-corner-hold').is_hidden()
    open_3d(page, 1)
    page.evaluate(f"""() => {{ const a = window.app; const l = a.project.layers.find(x => x.id === {ids[0]});
        l.riggingColor = '#224466'; a.updateLayers([l], true, 'Bar Color'); }}""")
    settled(page, lambda: served(page, ids[0]).get('riggingColor'), lambda v: v == '#224466')
    after = served(page, ids[0])
    for key in ('stage3d', 'riggingBars', 'riggingBarStarts', 'riggingCurve', 'panels'):
        assert after.get(key) == before.get(key), key
    assert 'riggingCorners' not in after
    assert page.errors == []
