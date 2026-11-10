"""The Curve's lock positions (app-curve.js, curve-math.js), in the real app.

The owner, 2026-11-10: "the curves allowed should only be via values that
are set. like the roe graphite can only do +-5". A panel's curve locks set
at fixed positions, a list per panel, never a range, and the Curve lays
only those.

What this file pins:

* A ROE Graphite screen locks at -5, 0 and +5 (the owner's list): its
  joints are only those, Ways to build it offers only 5 degree builds, and
  the 3D stage and the OBJ stand exactly the angles laid.
* A panel with no positions cannot be curved: the Curve says so, its
  checkbox waits, and ticking it is refused; set them and it curves.
* A list set by the user is saved with the show for that panel, used by
  every screen of that panel, undone and redone in one step, kept on a
  reload, and carried by a panel preset into a show that has none.
* The panel library's `curve_locks` is used when it has one, over the
  owner's list (a catalog entry stubbed here; dev/draft never edits the
  catalog).
* A curve saved at angles the panel's list does not have opens as it was,
  flagged in plain words, and Auto lays it again from the list.

Run locally:
    python -m pytest tests/test_curve_locks.py -n 4 --dist loadfile
"""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from conftest import settled  # noqa: E402
from test_curve_obj import (  # noqa: E402
    act, edit_locks, expected, face_corners_xz, history_len, idle, joints_of, layer, locks_of, obj_files,
    open_rigging, read_obj, reset, served, singles_only, toast_says,
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


GRAPHITE_ID = 'ROE|Graphite GP2.6 (4 in 1) Full Tile'
GRAPHITE = {'name': 'GRAPHITE', 'columns': 16, 'rows': 2, 'offset_x': 0, 'offset_y': 0,
            'panelModelId': GRAPHITE_ID, 'panelModelName': 'ROE Graphite GP2.6 (4 in 1) Full Tile'}


def chips(page):
    return page.evaluate("[...document.querySelectorAll('#rigging-curve-lock-chips [data-lock]')].map(e => e.textContent)")


def source(page):
    return page.inner_text('#rigging-curve-lock-source')


def select(page, layer_id):
    page.evaluate("(id) => { window.app.setSelectedLayersByIds([id], id); window.app.updateUI(); window.app.refreshRiggingPanel(); }",
                  layer_id)
    page.wait_for_timeout(150)


def ways(page):
    return page.evaluate("[...document.querySelectorAll('#rigging-curve-ways [data-way]')].map(e => e.dataset.way)")


# ── ROE Graphite: -5, 0 and +5 ───────────────────────────────────────────

def test_a_graphite_screen_only_gets_minus_5_0_and_plus_5(page):
    ids = reset(page, [GRAPHITE], locks=None)
    open_rigging(page)
    singles_only(page)
    # the owner's list, shown as chips with where it came from
    assert locks_of(page, ids[0]) == [-5, 0, 5]
    assert chips(page) == ['-5°', '0°', '+5°']
    assert source(page) == 'Owner list'
    assert not page.is_visible('#rigging-curve-lock-none')
    act(page, lambda: page.check('#rigging-curve-on'))
    lay = layer(page, ids[0])
    joints = joints_of(lay)
    assert len(joints) == 15 and set(joints) <= {0, 5} and 5 in joints, joints
    assert joints == expected(page, ids[0])['joints']
    # Ways to build it offers only 5 degree builds, whatever the goal
    for goal in ('simplest', 'even', 'tightest'):
        act(page, lambda: page.click(f'#rigging-curve-goal [data-value="{goal}"]'))
        shown = ways(page)
        assert shown and all(w.replace(' even', '') in ('5', 'flat', '') for w in shown), (goal, shown)
        assert set(joints_of(layer(page, ids[0]))) <= {0, 5}
    # convex: -5 or flat, never anything else
    act(page, lambda: page.click('#rigging-curve-bend [data-value="convex"]'))
    convex = joints_of(layer(page, ids[0]))
    assert set(convex) <= {0, -5} and -5 in convex, convex
    # a curve past what 5 degrees can reach still lays only 5s, and says so
    page.fill('#rigging-curve-value', '40')
    act(page, lambda: page.press('#rigging-curve-value', 'Enter'))
    assert set(joints_of(layer(page, ids[0]))) <= {0, -5}
    assert 'Out of range' in page.inner_text('#rigging-curve-warnings')
    assert page.errors == []


def test_3d_and_the_obj_stand_the_angles_the_curve_lays(page):
    ids = reset(page, [GRAPHITE], locks=None)
    open_rigging(page)
    singles_only(page)
    act(page, lambda: page.check('#rigging-curve-on'))
    want = joints_of(layer(page, ids[0]))
    assert set(want) <= {0, 5} and 5 in want
    srv = settled(page, lambda: served(page, ids[0]), lambda l: joints_of(l) == want)
    assert joints_of(srv) == want
    built = page.evaluate("""async (id) => {
        const m = await import('/static/js/app-stage3d.js');
        const l = window.app.project.layers.find(x => x.id === id);
        return m.s3dBuild(l, window.app._s3dPlacementOf(l)).colJ;
    }""", ids[0])
    assert built == want
    obj = read_obj(obj_files(page)['Test_Show_GRAPHITE.obj'])
    pts = face_corners_xz(obj)
    assert len(pts) == 17
    heads = [math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) for a, b in zip(pts, pts[1:])]
    turns = [h1 - h0 for h0, h1 in zip(heads, heads[1:])]
    assert turns == pytest.approx(want, abs=1e-3)
    assert page.errors == []


# ── No positions, no curve ───────────────────────────────────────────────

def test_a_panel_with_no_positions_cannot_be_curved_and_says_so(page):
    ids = reset(page, locks=None)
    open_rigging(page)
    singles_only(page)
    assert locks_of(page, ids[0]) is None
    assert chips(page) == []
    assert page.inner_text('#rigging-curve-lock-none') == \
        'This panel has no curve lock positions yet. Set them to curve this screen.'
    assert page.is_visible('#rigging-curve-lock-edit')
    assert page.is_disabled('#rigging-curve-on')
    assert 'lock positions' in page.inner_text('#rigging-curve-note')
    # asked anyway (another way in than the checkbox): refused, said, nothing laid
    n = history_len(page)
    page.evaluate('window.app.setRiggingCurveOn(true)')
    said = toast_says(page, 'no curve lock positions')
    assert 'This panel has no curve lock positions yet. Set them to curve this screen.' in said, said
    lay = layer(page, ids[0])
    assert not (lay.get('riggingCurve') or {}).get('on') and not lay.get('stage3d')
    assert history_len(page) == n
    # Save with only flat is refused
    page.click('#rigging-curve-lock-edit')
    page.click('#rigging-curve-lock-save')
    assert 'besides flat' in toast_says(page, 'besides flat')
    page.click('#rigging-curve-lock-cancel')
    # set them, and it curves from them
    edit_locks(page, '-7.5 7.5')
    assert settled(page, lambda: locks_of(page, ids[0]), lambda a: a == [-7.5, 0, 7.5]) == [-7.5, 0, 7.5]
    assert source(page) == 'Set by you'
    assert not page.is_disabled('#rigging-curve-on')
    act(page, lambda: page.check('#rigging-curve-on'))
    joints = joints_of(layer(page, ids[0]))
    assert set(joints) <= {0, 7.5} and 7.5 in joints
    assert page.errors == []


# ── The user's list ──────────────────────────────────────────────────────

def test_a_user_list_is_saved_with_the_show_used_by_every_screen_of_the_panel_and_undoes(page, e2e_server):
    ids = reset(page, [dict(GRAPHITE, name='LEFT'), dict(GRAPHITE, name='RIGHT', offset_y=400),
                       {'name': 'OTHER', 'columns': 8, 'rows': 2, 'offset_x': 0, 'offset_y': 800}], locks=None)
    open_rigging(page)
    singles_only(page)
    # RIGHT curved from the owner's list
    select(page, ids[1])
    singles_only(page)
    act(page, lambda: page.check('#rigging-curve-on'))
    assert set(joints_of(layer(page, ids[1]))) <= {0, 5}
    # LEFT's panel set to +-2.5 and +-5: one step, and RIGHT, the same panel, is laid again from it
    select(page, ids[0])
    n = history_len(page)
    act(page, lambda: edit_locks(page, '-5, -2.5, 2.5, 5'))
    mine = [-5, -2.5, 0, 2.5, 5]
    assert locks_of(page, ids[0]) == mine and locks_of(page, ids[1]) == mine
    assert source(page) == 'Set by you'
    assert locks_of(page, ids[2]) is None
    right = joints_of(layer(page, ids[1]))
    assert set(right) <= {0, 2.5, 5} and right == expected(page, ids[1])['joints']
    assert history_len(page) == n + 1
    # on the server, with the show
    srv = settled(page, lambda: page.evaluate("async () => (await (await fetch('/api/project')).json()).panelCurveLocks"),
                  lambda m: (m or {}).get(GRAPHITE_ID) == mine)
    assert srv == {GRAPHITE_ID: mine}
    # undo takes the list and RIGHT's relay back as one step; redo brings them
    page.evaluate('window.app.undo()')
    settled(page, lambda: locks_of(page, ids[0]), lambda a: a == [-5, 0, 5])
    assert locks_of(page, ids[1]) == [-5, 0, 5]
    assert set(joints_of(layer(page, ids[1]))) <= {0, 5}
    srv = settled(page, lambda: page.evaluate("async () => (await (await fetch('/api/project')).json()).panelCurveLocks"),
                  lambda m: not (m or {}).get(GRAPHITE_ID))
    assert not (srv or {}).get(GRAPHITE_ID)
    page.evaluate('window.app.redo()')
    settled(page, lambda: locks_of(page, ids[0]), lambda a: a == mine)
    assert joints_of(layer(page, ids[1])) == right
    settled(page, lambda: page.evaluate("async () => (await (await fetch('/api/project')).json()).panelCurveLocks"),
            lambda m: (m or {}).get(GRAPHITE_ID) == mine)
    # a reload keeps it
    page.reload(wait_until='domcontentloaded')
    page.wait_for_timeout(2000)
    open_rigging(page)
    select(page, ids[0])
    assert locks_of(page, ids[0]) == mine
    assert chips(page) == ['-5°', '-2.5°', '0°', '+2.5°', '+5°']
    assert source(page) == 'Set by you'
    # back to the owner list: the button says which list applies again
    page.click('#rigging-curve-lock-edit')
    assert page.inner_text('#rigging-curve-lock-reset') == 'Use the owner list'
    act(page, lambda: page.click('#rigging-curve-lock-reset'))
    assert locks_of(page, ids[0]) == [-5, 0, 5] and source(page) == 'Owner list'
    assert set(joints_of(layer(page, ids[1]))) <= {0, 5}
    assert page.errors == []


def test_a_panel_preset_carries_the_users_list_into_a_show_without_one(page):
    ids = reset(page, locks=None)
    open_rigging(page)
    edit_locks(page, '-4, 4')
    key = page.evaluate("(id) => window.app.curveLockKey(window.app.project.layers.find(l => l.id === id))", ids[0])
    settled(page, lambda: locks_of(page, ids[0]), lambda a: a == [-4, 0, 4])
    preset = page.evaluate("(id) => window.app.serializeLayerAsPreset(window.app.project.layers.find(l => l.id === id))", ids[0])
    assert preset['curveLocks'] == [-4, 0, 4]
    # the library's or the owner's list is never carried
    gids = reset(page, [GRAPHITE], locks=None)
    g = page.evaluate("(id) => window.app.serializeLayerAsPreset(window.app.project.layers.find(l => l.id === id))", gids[0])
    assert 'curveLocks' not in g
    # a show with no list for that panel takes the preset's, in the Add Layer step
    reset(page, [], locks=None)
    page.evaluate("async (data) => { await window.app.addLayer(data); }", preset)
    made = settled(page, lambda: page.evaluate("() => window.app.project.layers.length"), lambda n: n == 1)
    assert made == 1
    assert page.evaluate("() => window.app.project.panelCurveLocks") == {key: [-4, 0, 4]}
    assert 'curveLocks' not in page.evaluate("() => window.app.project.layers[0]")
    settled(page, lambda: page.evaluate("async () => (await (await fetch('/api/project')).json()).panelCurveLocks"),
            lambda m: m == {key: [-4, 0, 4]})
    page.evaluate('window.app.undo()')
    settled(page, lambda: page.evaluate("() => window.app.project.layers.length"), lambda n: n == 0)
    assert not page.evaluate("() => window.app.project.panelCurveLocks || {}")
    # a show with its own list keeps it
    reset(page, [], locks=None)
    page.evaluate("(key) => { window.app.project.panelCurveLocks = {[key]: [-6, 0, 6]}; }", key)
    page.evaluate("async (data) => { await window.app.addLayer(data); }", preset)
    settled(page, lambda: page.evaluate("() => window.app.project.layers.length"), lambda n: n == 1)
    assert page.evaluate("() => window.app.project.panelCurveLocks")[key] == [-6, 0, 6]
    assert page.errors == []


# ── The panel library ────────────────────────────────────────────────────

STUB_JS = """async (entries) => {
    const a = window.app;
    await a._ensurePanelCatalogData();
    a._curveCatalogKept = a._curveCatalogKept || a._panelCatalog;
    const cat = JSON.parse(JSON.stringify(a._curveCatalogKept));
    for (const [mfr, entry] of entries) {
        cat[mfr] = (cat[mfr] || []).filter(p => p.name !== entry.name).concat([entry]);
    }
    a._ingestCatalog(cat);
}"""

UNSTUB_JS = """() => { const a = window.app; if (a._curveCatalogKept) a._ingestCatalog(a._curveCatalogKept); a._curveCatalogKept = null; }"""


def test_a_library_curve_locks_value_is_used_when_present(page):
    ids = reset(page, [GRAPHITE, {'name': 'BENDY', 'columns': 8, 'rows': 2, 'offset_x': 0, 'offset_y': 400,
                                  'panelModelId': 'TestMaker|Bendy 500', 'panelModelName': 'TestMaker Bendy 500'}],
                locks=None)
    open_rigging(page)
    try:
        page.evaluate(STUB_JS, [
            ['ROE', {'name': 'Graphite GP2.6 (4 in 1) Full Tile', 'width_mm': 500, 'height_mm': 1000,
                     'pixels_w': 192, 'pixels_h': 384, 'pitch_mm': 2.604, 'weight_kg': 8.6, 'watts_max': 250,
                     'curve_locks': [-2.5, 0, 2.5], 'curve_locks_source': 'test sheet'}],
            ['TestMaker', {'name': 'Bendy 500', 'width_mm': 500, 'height_mm': 500, 'pixels_w': 128,
                           'pixels_h': 128, 'pitch_mm': 3.9, 'weight_kg': 8, 'watts_max': 200,
                           'curve_locks': [-10, -5, 0, 5, 10, 25]}],
        ])
        select(page, ids[0])
        # the library wins over the owner's list once it has one
        assert locks_of(page, ids[0]) == [-2.5, 0, 2.5]
        assert source(page) == 'From the panel library'
        singles_only(page)
        act(page, lambda: page.check('#rigging-curve-on'))
        joints = joints_of(layer(page, ids[0]))
        assert set(joints) <= {0, 2.5} and 2.5 in joints
        # a model only the library knows: its list, anything past 20 dropped
        select(page, ids[1])
        assert locks_of(page, ids[1]) == [-10, -5, 0, 5, 10]
        assert source(page) == 'From the panel library'
        # the user's list wins over the library's, and going back offers the library's
        edit_locks(page, '-3 3')
        settled(page, lambda: locks_of(page, ids[1]), lambda a: a == [-3, 0, 3])
        page.click('#rigging-curve-lock-edit')
        assert page.inner_text('#rigging-curve-lock-reset') == 'Use the panel library list'
        page.click('#rigging-curve-lock-cancel')
    finally:
        page.evaluate(UNSTUB_JS)
    # without the stub, Graphite reads the owner's list again
    assert locks_of(page, ids[0]) == [-5, 0, 5]
    assert page.errors == []


# ── A curve saved before ─────────────────────────────────────────────────

def test_an_old_curve_with_off_list_angles_opens_flagged_and_auto_lays_it_from_the_list(page, e2e_server):
    ids = reset(page, [GRAPHITE], locks=None)
    # as a first 1.7.0 build saved it: typed lock angles, 7.5 at some joints
    old = {'0': 0, '1': 7.5, '2': 0, '3': 7.5, '4': 0, '5': 7.5, '6': 0, '7': 7.5,
           '8': 0, '9': 7.5, '10': 0, '11': 7.5, '12': 0, '13': 7.5, '14': 0}
    page.evaluate("""async ([id, joints]) => {
        const body = {riggingSizes: [1], riggingBars: new Array(16).fill(1),
                      riggingCurve: {on: true, angles: [2.5, 5, 7.5, 10]},
                      stage3d: {x: 0, y: 0, z: 0, pitch: 0, yaw: 0, roll: 0, pivot: 'bottom', jointsCol: joints}};
        await fetch(`/api/layer/${id}`, {method: 'PUT', headers: {'Content-Type': 'application/json'},
                                         body: JSON.stringify(body)});
    }""", [ids[0], old])
    page.reload(wait_until='domcontentloaded')
    page.wait_for_timeout(2000)
    open_rigging(page)
    select(page, ids[0])
    lay = layer(page, ids[0])
    assert joints_of(lay) == [old[str(j)] for j in range(15)]
    assert page.is_checked('#rigging-curve-on')
    note = settled(page, lambda: page.inner_text('#rigging-curve-note'), lambda t: 'does not lock at' in t)
    assert note == 'This screen is laid at +7.5°, which this panel does not lock at. Press Auto to lay it again from its lock positions.'
    # 3D stands it as saved until then
    built = page.evaluate("""async (id) => {
        const m = await import('/static/js/app-stage3d.js');
        const l = window.app.project.layers.find(x => x.id === id);
        return m.s3dBuild(l, window.app._s3dPlacementOf(l)).colJ;
    }""", ids[0])
    assert built == [old[str(j)] for j in range(15)]
    # Auto lays it again from the list, one step
    n = history_len(page)
    act(page, lambda: page.click('#rigging-auto-btn'))
    now = joints_of(layer(page, ids[0]))
    assert set(now) <= {0, 5} and 5 in now and now == expected(page, ids[0])['joints']
    assert history_len(page) == n + 1
    assert 'does not lock at' not in page.inner_text('#rigging-curve-note')
    assert page.errors == []


def test_an_old_curve_whose_panel_has_no_positions_opens_and_keeps_its_angles(page):
    ids = reset(page, locks=None)
    page.evaluate("""async (id) => {
        const body = {riggingSizes: [1], riggingBars: new Array(16).fill(1),
                      riggingCurve: {on: true, angles: [5]},
                      stage3d: {x: 0, y: 0, z: 0, pitch: 0, yaw: 0, roll: 0, pivot: 'bottom', jointsCol: {'3': 5, '7': 5}}};
        await fetch(`/api/layer/${id}`, {method: 'PUT', headers: {'Content-Type': 'application/json'},
                                         body: JSON.stringify(body)});
    }""", ids[0])
    page.reload(wait_until='domcontentloaded')
    page.wait_for_timeout(2000)
    open_rigging(page)
    select(page, ids[0])
    idle(page)
    assert page.is_checked('#rigging-curve-on') and not page.is_disabled('#rigging-curve-on')
    assert 'until its panel\'s lock positions are set' in page.inner_text('#rigging-curve-note')
    assert page.inner_text('#rigging-curve-lock-none') == \
        'This panel has no curve lock positions yet. Set them to curve this screen.'
    # said once, by the lock positions row
    assert not page.is_visible('#rigging-curve-errors')
    # Auto cannot lay it, and leaves it as it was
    page.click('#rigging-auto-btn')
    idle(page)
    table = (layer(page, ids[0]).get('stage3d') or {}).get('jointsCol') or {}
    assert {k: v for k, v in table.items() if v} == {'3': 5, '7': 5}
    assert page.errors == []
