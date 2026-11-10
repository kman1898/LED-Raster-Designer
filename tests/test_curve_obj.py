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
* Lit sizes that cannot cover the wall exactly lay nothing and name the
  gap. The datum drags onto any panel middle or joint. Ways to build it
  lists every build, and a pick holds until the curve changes. The math
  runs in a worker: the page keeps running, the newest edit wins, and an
  undo while it works takes back that edit.
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
    // The last test's writes land first: a layer PUT still on its way
    // would otherwise reach the server after this reset and write an old
    // screen over the new one that took its id.
    for (let i = 0; i < 600; i++) {
        const out = (app._inflightLayerPuts && app._inflightLayerPuts.size)
            || (typeof app.riggingCurveBusy === 'function' && app.riggingCurveBusy());
        if (!out) break;
        await new Promise(r => setTimeout(r, 25));
    }
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


def idle(page, timeout=15000):
    """The Curve works in the background (curve-worker.js): wait until it
    has answered and its edit has landed, on the app's own state."""
    assert settled(page, lambda: page.evaluate('window.app.riggingCurveBusy()'), lambda b: not b, timeout) is False


def act(page, fn):
    """One Curve edit, then the wait for it to land."""
    fn()
    idle(page)


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
    # off, the settings show (and save) but nothing is laid or worked out
    assert page.is_visible('#rigging-curve-fields')
    assert not page.is_visible('#rigging-curve-result')
    assert 'Tick Curve' in page.inner_text('#rigging-curve-note')
    page.check('#rigging-curve-on')
    idle(page)
    lay = layer(page, ids[0])
    assert (lay.get('riggingCurve') or {}).get('on') and lay.get('stage3d')
    assert not page.is_visible('#rigging-curve-working')
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
    srv = settled(page, lambda: served(page, ids[0]), lambda l: l.get('riggingBars') == [1] * 16)
    assert srv['riggingCurve']['on'] is True and srv['riggingBars'] == [1] * 16
    assert joints_of(srv) == want['joints']
    assert page.errors == []


def test_each_edit_lays_it_again_and_undoes_one_step_at_a_time(page):
    ids = reset(page)
    open_rigging(page)
    singles_only(page)
    act(page, lambda: page.check('#rigging-curve-on'))
    first = layer(page, ids[0])
    n = history_len(page)

    act(page, lambda: page.click('#rigging-curve-bend [data-value="convex"]'))
    convex = layer(page, ids[0])
    assert convex['riggingCurve']['bend'] == 'convex'
    assert joints_of(convex) == [-a if a else 0 for a in joints_of(first)]

    act(page, lambda: page.click('#rigging-curve-goal [data-value="even"]'))
    even = layer(page, ids[0])
    bent = [a for a in joints_of(even) if a]
    assert len(set(bent)) == 1, joints_of(even)

    # % to degrees says the same curve: 20% is 72 degrees, nothing moves
    act(page, lambda: page.click('#rigging-curve-entry [data-value="degrees"]'))
    deg = layer(page, ids[0])
    assert deg['riggingCurve']['value'] == 72
    assert joints_of(deg) == joints_of(even)
    assert page.input_value('#rigging-curve-value') == '72'

    page.fill('#rigging-curve-angles', '5')
    act(page, lambda: page.press('#rigging-curve-angles', 'Enter'))
    five = layer(page, ids[0])
    assert five['riggingCurve']['angles'] == [5]
    assert set(joints_of(five)) <= {0, -5}

    # the lit sizes are the stock: laid again, the sizes in the same step
    act(page, lambda: page.click('#rigging-size-picker .rigging-size-btn[data-size="2"]'))
    act(page, lambda: page.click('#rigging-size-picker .rigging-size-btn[data-size="1"]'))
    doubles = layer(page, ids[0])
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
    act(page, lambda: page.check('#rigging-curve-on'))
    act(page, lambda: page.click('#rigging-curve-goal [data-value="tightest"]'))
    # The goal is saved at once and the answer's bars and angles in a second
    # save when it lands: wait for the server to hold what the app holds,
    # not just the goal (the first save alone once raced this read).
    mine = layer(page, ids[0])
    assert (mine.get('riggingCurve') or {}).get('goal') == 'tightest'
    laid = settled(page, lambda: served(page, ids[0]),
                   lambda l: l.get('riggingCurve') == mine['riggingCurve']
                   and l.get('riggingBars') == mine['riggingBars'] and joints_of(l) == joints_of(mine))
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
    act(page, lambda: page.check('#rigging-curve-on'))
    lay = layer(page, ids[0])
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
    act(page, lambda: page.click('#rigging-auto-btn'))
    assert layer(page, ids[0])['riggingBars'] == lay['riggingBars']
    page.click('#rigging-clear-btn')
    off = settled(page, lambda: layer(page, ids[0]), lambda l: not l.get('riggingBars'))
    assert not off['riggingCurve']['on']
    assert joints_of(off) == []
    assert not page.is_checked('#rigging-curve-on')
    assert page.errors == []


def test_a_grouped_row_is_refused_and_named_and_a_turned_screen_curves(page):
    # A Pixel Map rotation turns only the picture: the bars and joints stay
    # the wall's own columns, so a turned screen takes a Curve (owner,
    # 2026-11-10).
    ids = reset(page, [{'name': 'TURNED', 'columns': 6, 'rows': 2, 'offset_x': 0, 'offset_y': 0}])
    page.evaluate("(id) => { const l = window.app.project.layers.find(x => x.id === id); l.rotation = 90; window.app.updateLayers([l], false); }", ids[0])
    open_rigging(page)
    singles_only(page)
    act(page, lambda: page.check('#rigging-curve-on'))
    turned = layer(page, ids[0])
    assert (turned.get('riggingCurve') or {}).get('on')
    assert turned['riggingBars'] == [1] * 6 and joints_of(turned) == expected(page, ids[0])['joints']

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
    assert not page.is_visible('#rigging-curve-result')
    page.click('#view-tabs .view-tab[data-mode="3d"]')
    page.wait_for_timeout(800)
    open_rigging(page)
    page.wait_for_timeout(300)
    now = served(page, ids[1])
    assert now == old
    assert history_len(page) == n
    assert page.errors == []


def test_leftover_stock_is_named_and_lays_nothing(page):
    """Matt, 2026-11-09: lit sizes that cannot cover the wall exactly warn
    and lay nothing; the screen's bars and joints stay as they were."""
    ids = reset(page, [{'name': 'ODD', 'columns': 15, 'rows': 2, 'offset_x': 0, 'offset_y': 0}])
    open_rigging(page)
    singles_only(page)
    page.click('#rigging-auto-btn')
    before = settled(page, lambda: layer(page, ids[0]), lambda l: l.get('riggingBars') == [1] * 15)
    assert before['riggingBars'] == [1] * 15
    # doubles only: 15 panels leave one over
    page.click('#rigging-size-picker .rigging-size-btn[data-size="2"]')
    page.click('#rigging-size-picker .rigging-size-btn[data-size="1"]')
    act(page, lambda: page.check('#rigging-curve-on'))
    now = layer(page, ids[0])
    assert now['riggingCurve']['on'] is True
    assert page.inner_text('#rigging-curve-errors') == \
        'These bar sizes leave 1 panel uncovered on a 15-panel wall. Light another size.'
    assert not page.is_visible('#rigging-curve-result')
    assert now['riggingBars'] == [1] * 15
    assert not now.get('stage3d')
    # Auto says so too, and still lays nothing
    act(page, lambda: page.click('#rigging-auto-btn'))
    assert 'No exact fit with these sizes: ODD' in page.inner_text('#rigging-status')
    assert layer(page, ids[0])['riggingBars'] == [1] * 15 and not layer(page, ids[0]).get('stage3d')
    # light singles again and it lays
    n = history_len(page)
    act(page, lambda: page.click('#rigging-size-picker .rigging-size-btn[data-size="1"]'))
    laid = layer(page, ids[0])
    assert laid.get('stage3d') and len(joints_of(laid)) == 14
    assert not page.is_visible('#rigging-curve-errors')
    assert history_len(page) == n + 1
    assert page.errors == []


def plan_spot(page, at):
    """The client point of the plan's spot `at` (half panels along the wall)."""
    return page.evaluate("""(at) => {
        const host = document.getElementById('rigging-curve-plan');
        // the plan sits low in the sidebar: bring it into view as a
        // person would scroll to it
        host.scrollIntoView({ block: 'center' });
        const plan = host._curvePlan;
        const s = plan.spots.find(x => x.at === at);
        const b = plan.svg.getBoundingClientRect();
        return { x: b.left + s.x, y: b.top + s.y };
    }""", at)


def solve_now(page, layer_id):
    return page.evaluate("""(id) => {
        const out = window.app.riggingCurveSolve(window.app.project.layers.find(x => x.id === id));
        return { joints: out.joints, datum: out.result.datum_at,
                 chosen: out.result.chosen_option_id, app: out.result.recommended_option_id,
                 options: out.result.options.map(o => o.id) };
    }""", layer_id)


def test_the_datum_drags_onto_any_panel_or_joint(page):
    ids = reset(page)
    open_rigging(page)
    singles_only(page)
    act(page, lambda: page.check('#rigging-curve-on'))
    assert page.get_attribute('#rigging-curve-plan circle', 'data-datum') == '8.5'
    n = history_len(page)
    a, b = plan_spot(page, 8.5), plan_spot(page, 4)
    page.mouse.move(a['x'], a['y'])
    page.mouse.down()
    page.mouse.move((a['x'] + b['x']) / 2, (a['y'] + b['y']) / 2, steps=4)
    page.mouse.move(b['x'], b['y'], steps=4)
    # the mark follows the pointer before anything is laid
    assert page.get_attribute('#rigging-curve-plan circle', 'data-datum') == '4'
    assert history_len(page) == n
    act(page, lambda: page.mouse.up())
    now = layer(page, ids[0])
    assert now['riggingCurve']['from'] == 4
    assert history_len(page) == n + 1
    want = solve_now(page, ids[0])
    assert want['datum'] == 4 and joints_of(now) == want['joints']
    assert page.get_attribute('#rigging-curve-sheet path[data-datum]', 'data-datum') == '4'
    assert 'From panel 4' in page.inner_text('#rigging-curve-from-label')
    # dragging selected no text on the page
    assert page.evaluate('String(window.getSelection())') == ''
    # a joint, in half steps
    c = plan_spot(page, 11.5)
    page.mouse.move(c['x'], c['y'])
    page.mouse.down()
    act(page, lambda: page.mouse.up())
    assert layer(page, ids[0])['riggingCurve']['from'] == 11.5
    assert 'between panels 11 and 12' in page.inner_text('#rigging-curve-from-label')
    # the quick picks still work, and undo walks back through the drags
    act(page, lambda: page.click('#rigging-curve-from [data-value="left"]'))
    assert layer(page, ids[0])['riggingCurve']['from'] == 'left'
    page.evaluate('window.app.undo()')
    assert settled(page, lambda: layer(page, ids[0])['riggingCurve']['from'], lambda f: f == 11.5) == 11.5
    assert page.errors == []


def test_ways_to_build_it_lists_every_build_and_a_pick_holds_until_the_curve_changes(page):
    ids = reset(page)
    open_rigging(page)
    singles_only(page)
    act(page, lambda: page.check('#rigging-curve-on'))
    want = solve_now(page, ids[0])
    shown = page.evaluate("[...document.querySelectorAll('#rigging-curve-ways [data-way]')].map(e => e.dataset.way)")
    assert shown == want['options'] and shown[0] == '7.5'
    assert '2.5+7.5' in shown
    # the closest even build is always offered
    assert any(w.endswith(' even') for w in shown), shown
    assert page.is_visible('#rigging-curve-ways')
    assert 'in use' in page.inner_text('#rigging-curve-ways [data-way="7.5"]')
    # Use this: the wall is built that way, one undo step
    n = history_len(page)
    act(page, lambda: page.click('#rigging-curve-ways [data-pick="2.5+7.5"]'))
    picked = layer(page, ids[0])
    assert picked['riggingCurve']['pick']['id'] == '2.5+7.5'
    assert {a for a in joints_of(picked) if a} == {2.5, 7.5}
    assert history_len(page) == n + 1
    assert 'You picked this one by hand' in page.inner_text('#rigging-curve-ways')
    assert page.inner_text('#rigging-curve-reason').startswith('Your pick')
    # the datum does not reset it
    act(page, lambda: page.click('#rigging-curve-from [data-value="left"]'))
    assert solve_now(page, ids[0])['chosen'] == '2.5+7.5'
    assert 'You picked this one by hand' in page.inner_text('#rigging-curve-ways')
    # a change to the curve does: the app picks again
    page.fill('#rigging-curve-value', '21')
    act(page, lambda: page.press('#rigging-curve-value', 'Enter'))
    assert 'You picked this one by hand' not in page.inner_text('#rigging-curve-ways')
    again = solve_now(page, ids[0])
    assert again['chosen'] == again['app']
    assert joints_of(layer(page, ids[0])) == again['joints']
    # and Let the app pick drops a pick at once
    act(page, lambda: page.click('#rigging-curve-ways [data-pick="2.5+7.5"]'))
    act(page, lambda: page.click('#rigging-curve-ways [data-pick="auto"]'))
    assert layer(page, ids[0])['riggingCurve']['pick'] is None
    assert page.errors == []


def test_the_math_runs_in_a_worker_and_the_newest_edit_wins(page):
    ids = reset(page, [{'name': 'BIG', 'columns': 48, 'rows': 2, 'offset_x': 0, 'offset_y': 0}])
    open_rigging(page)
    page.evaluate("""(id) => { const l = window.app.project.layers.find(x => x.id === id); l.riggingSizes = [1, 2, 3, 4];
        window.app.refreshRiggingPanel(); }""", ids[0])
    page.check('#rigging-curve-on')
    assert page.is_visible('#rigging-curve-working')
    # the page keeps running while it works: a timer every 20 ms is never
    # held up by the math (it took over a second on this wall on the page)
    lag = page.evaluate("""() => new Promise(res => { const t0 = performance.now(); let worst = 0, last = t0;
        const id = setInterval(() => { const now = performance.now(); worst = Math.max(worst, now - last); last = now;
            if (!window.app.riggingCurveBusy() || now - t0 > 20000) { clearInterval(id); res(worst); } }, 20); })""")
    assert page.evaluate('!!window.app._curveWorkerObj && !window.app._curveWorkerBroken')
    assert lag < 400, lag
    idle(page, 60000)
    assert not page.is_visible('#rigging-curve-working')
    # two edits close together: only the newest lands, as one step
    n = history_len(page)
    page.click('#rigging-curve-goal [data-value="even"]')
    page.click('#rigging-curve-goal [data-value="tightest"]')
    idle(page, 60000)
    now = layer(page, ids[0])
    assert now['riggingCurve']['goal'] == 'tightest'
    assert joints_of(now) == solve_now(page, ids[0])['joints']
    assert history_len(page) == n + 1
    # an undo while it works takes back that edit, and its answer never
    # lands; a redo brings the edit back and the tab says it is not laid
    m = history_len(page)
    page.click('#rigging-curve-bend [data-value="convex"]')
    assert page.evaluate('window.app.riggingCurveBusy()')
    page.evaluate('window.app.undo()')
    idle(page, 60000)
    after = layer(page, ids[0])
    assert after['riggingCurve']['bend'] == 'concave', after['riggingCurve']
    assert after['riggingCurve']['goal'] == 'tightest'
    assert joints_of(after) == joints_of(now)
    assert history_len(page) == m + 1
    page.evaluate('window.app.redo()')
    page.evaluate('window.app.refreshRiggingPanel()')
    assert layer(page, ids[0])['riggingCurve']['bend'] == 'convex'
    assert 'not this curve' in page.inner_text('#rigging-curve-note')
    act(page, lambda: page.click('#rigging-auto-btn'))
    assert joints_of(layer(page, ids[0])) == solve_now(page, ids[0])['joints']
    assert all(a <= 0 for a in joints_of(layer(page, ids[0])))
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
    """The screen as its Curve leaves it: the Curve on and these angles at
    its column joints (the Curve is the only source of joint angles; a
    screen with its Curve off stands flat)."""
    page.evaluate("""([id, joints]) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === id);
        l.riggingCurve = { ...(l.riggingCurve || {}), on: true };
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
    # the grouping's own step lands when the server has answered
    page.evaluate("async () => { await window.app._groupCommitChain; }")


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


CALC_JS = """async (cases) => {
    const m = await import('/static/js/curve-math.js');
    return cases.map(([n, angle]) => {
        const got = m.buildCurve({widths: new Array(n).fill(0.5), joints: new Array(n - 1).fill(angle),
            direction: 'concave', pivotOffsetM: 0, panelDepthM: 0.085, wallHeightM: 6}).measurements;
        return {face: got.radius_face_m, joints: got.radius_joints_m, chord: got.chord_m,
                faceAgain: m.faceRadiusForAngle(0.5, angle), jointsAgain: m.radiusForAngle(0.5, angle)};
    });
}"""

# (cabinets, degrees at every joint): the calculator's reference wall
# (5.725941 m to the face, 7.368141 m chord), and two more.
RADIUS_CASES = [(16, 5), (24, 2.5), (10, 7.5)]


@pytest.mark.parametrize('n,angle', RADIUS_CASES, ids=[f'{n}x500mm_at_{a}deg' for n, a in RADIUS_CASES])
def test_every_obj_face_sits_on_the_calculators_face_radius(page, n, angle):
    """The radii and chord come from curve-math.js itself (buildCurve and
    its closed forms, which must agree), not typed in; then every face of
    the exported OBJ, one at a time, sits with its middle on the face
    radius and both its edges on the joint radius, to 0.1 mm, about one
    centre, and the ends are the chord apart."""
    want = page.evaluate(CALC_JS, [[n, angle]])[0]
    assert want['face'] == pytest.approx(want['faceAgain'], abs=1e-9)
    assert want['joints'] == pytest.approx(want['jointsAgain'], abs=1e-9)
    if (n, angle) == (16, 5):
        # the reference wall's published figures
        assert want['face'] == pytest.approx(5.725941, abs=1e-6)
        assert want['chord'] == pytest.approx(7.368141, abs=1e-6)
    ids = reset(page, [dict(WALL, columns=n)])
    set_joints(page, ids[0], [angle] * (n - 1))
    obj = read_obj(obj_files(page)['Test_Show_WALL.obj'])
    pts = face_corners_xz(obj)
    assert len(pts) == n + 1
    c = circumcenter(pts[0], pts[n // 2], pts[n])
    for i in range(n):
        a, b = pts[i], pts[i + 1]
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        assert abs(math.dist(mid, c) - want['face']) < 1e-4, (i, math.dist(mid, c), want['face'])
        assert abs(math.dist(a, c) - want['joints']) < 1e-4, (i, math.dist(a, c), want['joints'])
    assert abs(math.dist(pts[-1], c) - want['joints']) < 1e-4
    assert abs(math.dist(pts[0], pts[-1]) - want['chord']) < 1e-4
    assert page.errors == []


def test_an_obj_of_a_curved_screen_reads_back_right(page):
    ids = reset(page)
    open_rigging(page)
    singles_only(page)
    act(page, lambda: page.check('#rigging-curve-on'))
    lay = layer(page, ids[0])
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
    # the group as the app names it: one file, named after the group
    files = obj_files(page)
    assert sorted(files) == ['Test_Show_Canvas_1_Pixel_Map.png', 'Test_Show_Group_1.mtl', 'Test_Show_Group_1.obj',
                             'Test_Show_SIDE.mtl', 'Test_Show_SIDE.obj'], sorted(files)
    center = read_obj(files['Test_Show_Group_1.obj'])
    assert [o['name'] for o in center['objects']] == ['LEFT', 'RIGHT']
    assert [len(o['faces']) for o in center['objects']] == [8, 8]
    assert {o['material'] for o in center['objects']} == {'Canvas_1'}
    assert any('Group: Group 1, 2 screens' in c for c in center['comments'])
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


# Which sections of the Export dialog each format shows. Recorded off the
# app before OBJ came in (8c6f7b87), every format opened and switched to,
# and OBJ's own row added: its screens come off the 3D stage, so no views
# and no canvas list, the background option kept, its note shown.
EXPORT_SECTIONS = ['export-canvases-section', 'export-views-section', 'export-options-section',
                   'export-pull-sheet-section', 'export-binder-section', 'export-obj-note',
                   'export-scale-row', 'export-psd-layers-row']
_PICTURE = (True, True, True, False, False, False, False, False)
EXPORT_SHOWS = {
    'png': _PICTURE,
    'svg': _PICTURE,
    'pdf': _PICTURE,
    'psd': (True, True, True, False, False, False, True, True),
    'resolume-xml': (True, False, True, False, False, False, False, False),
    'pull-sheet': (False, False, False, True, False, False, False, False),
    'binder': (False, False, False, False, True, False, False, False),
    'obj': (False, False, True, False, False, True, False, False),
}


def test_every_export_format_shows_its_own_sections(page):
    reset(page)
    formats = page.evaluate("[...document.querySelectorAll('#export-format option')].map(o => o.value)")
    assert sorted(formats) == sorted(EXPORT_SHOWS), formats
    # Every format both ways: the dialog opened on it, and switched to from
    # each other format, since each format's own sync runs on a switch.
    walk = []
    for fmt in formats:
        walk.append((fmt, 'open', None))
        for prev in formats:
            if prev != fmt:
                walk.append((fmt, 'switch', prev))
    for fmt, how, prev in walk:
        if how == 'open':
            page.evaluate("(f) => { document.getElementById('export-modal').style.display = 'none'; window.app.openExportModal(f); }", fmt)
        else:
            page.evaluate("(f) => { document.getElementById('export-modal').style.display = 'none'; window.app.openExportModal(f); }", prev)
            page.select_option('#export-format', fmt)
        got = page.evaluate("(ids) => ids.map(id => { const e = document.getElementById(id); return !!e && e.offsetParent !== null; })",
                            EXPORT_SECTIONS)
        want = list(EXPORT_SHOWS[fmt])
        assert got == want, (fmt, how, prev, dict(zip(EXPORT_SECTIONS, got)))
    page.evaluate("() => { document.getElementById('export-modal').style.display = 'none'; }")
    assert page.errors == []


def test_settings_edited_with_the_curve_off_are_kept_and_lay_nothing(page):
    """Every field that shows writes the screen (test_all_fields_sweep's
    rule): with Curve off the settings are kept for when it is ticked, and
    no bar or joint changes; focus stays in the form after Tab."""
    ids = reset(page)
    open_rigging(page)
    singles_only(page)
    n = history_len(page)
    page.fill('#rigging-curve-value', '30')
    page.press('#rigging-curve-value', 'Tab')
    lay = settled(page, lambda: layer(page, ids[0]), lambda l: (l.get('riggingCurve') or {}).get('value') == 30)
    assert lay['riggingCurve']['on'] is False and lay['riggingCurve']['value'] == 30
    assert not lay.get('stage3d') and not lay.get('riggingBars')
    assert history_len(page) == n + 1
    assert page.evaluate('document.activeElement && document.activeElement !== document.body')
    page.fill('#rigging-curve-angles', '5 and 10')
    page.press('#rigging-curve-angles', 'Tab')
    assert settled(page, lambda: layer(page, ids[0])['riggingCurve']['angles'], lambda a: a == [5, 10]) == [5, 10]
    srv = settled(page, lambda: served(page, ids[0]), lambda l: (l.get('riggingCurve') or {}).get('angles') == [5, 10])
    assert srv['riggingCurve']['value'] == 30 and srv['riggingCurve']['on'] is False
    # ticking it lays the curve from those settings
    act(page, lambda: page.check('#rigging-curve-on'))
    on = layer(page, ids[0])
    assert on['riggingCurve']['value'] == 30 and on['riggingBars'] == [1] * 16
    assert {abs(a) for a in joints_of(on) if a} <= {5, 10}
    assert page.errors == []


def test_the_curves_angles_over_15_reach_3d_and_the_obj_unchanged(page):
    """Found in QA (2026-11-10): the Curve laid 20 degree joints (lock
    angle 20) and the build sheet said so, but the 3D place held every
    joint to 15, so the 3D tab and the OBJ drew a shallower wall than the
    one the crew builds. The joints the Curve lays are stored, built and
    exported exactly as laid."""
    ids = reset(page, [dict(WALL, columns=9)])
    open_rigging(page)
    singles_only(page)
    page.fill('#rigging-curve-angles', '20')
    page.press('#rigging-curve-angles', 'Tab')
    page.fill('#rigging-curve-value', '40')
    page.press('#rigging-curve-value', 'Tab')
    settled(page, lambda: layer(page, ids[0])['riggingCurve'],
            lambda c: c and c.get('value') == 40 and c.get('angles') == [20])
    act(page, lambda: page.check('#rigging-curve-on'))
    want = expected(page, ids[0])
    assert want['errors'] == []
    assert max(want['joints']) == 20, want['joints']
    # stored as laid, here and on the server
    lay = layer(page, ids[0])
    assert joints_of(lay) == want['joints']
    srv = settled(page, lambda: served(page, ids[0]), lambda l: joints_of(l) == want['joints'])
    assert joints_of(srv) == want['joints']
    # built as laid: the 3D stage's own column chain
    built = page.evaluate("""async (id) => {
        const m = await import('/static/js/app-stage3d.js');
        const l = window.app.project.layers.find(x => x.id === id);
        return m.s3dBuild(l, window.app._s3dPlacementOf(l)).colJ;
    }""", ids[0])
    assert built == want['joints']
    # exported as laid: the turn between neighboring faces, read off the OBJ
    obj = read_obj(obj_files(page)['Test_Show_WALL.obj'])
    pts = face_corners_xz(obj)
    assert len(pts) == 10
    heads = [math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) for a, b in zip(pts, pts[1:])]
    turns = [h1 - h0 for h0, h1 in zip(heads, heads[1:])]
    assert turns == pytest.approx(want['joints'], abs=1e-3)
    assert page.errors == []


def test_lock_angles_past_20_are_refused_and_the_field_goes_back(page):
    """The owner, 2026-11-10: "lets limit to 20". 20 is taken; 20.5 and 25
    are refused, said, and the field shows what it held."""
    ids = reset(page)
    open_rigging(page)
    singles_only(page)
    page.fill('#rigging-curve-angles', '5, 20')
    page.press('#rigging-curve-angles', 'Tab')
    assert settled(page, lambda: layer(page, ids[0])['riggingCurve']['angles'], lambda a: a == [5, 20]) == [5, 20]
    for typed in ('20.5', '10, 25'):
        n = history_len(page)
        page.fill('#rigging-curve-angles', typed)
        page.press('#rigging-curve-angles', 'Tab')
        said = toast_says(page, 'past the 20° a curve lock bends')
        assert 'Type angles up to 20°' in said, said
        assert page.input_value('#rigging-curve-angles') == '5, 20'
        assert layer(page, ids[0])['riggingCurve']['angles'] == [5, 20]
        assert history_len(page) == n
    assert page.errors == []


def test_a_curve_needing_more_than_20_a_joint_is_refused_and_says_how_much_fits(page):
    ids = reset(page, [dict(WALL, columns=9)])
    open_rigging(page)
    singles_only(page)
    page.fill('#rigging-curve-angles', '10, 20')
    page.press('#rigging-curve-angles', 'Tab')
    page.fill('#rigging-curve-value', '55')
    page.press('#rigging-curve-value', 'Tab')
    settled(page, lambda: layer(page, ids[0])['riggingCurve'], lambda c: c.get('value') == 55)
    act(page, lambda: page.check('#rigging-curve-on'))
    want = expected(page, ids[0])
    assert want['errors'] == ['This curve needs 22° at each joint on a 9-panel wall, past the 20° a curve lock takes. Ask for 50% or less.']
    lay = layer(page, ids[0])
    assert not lay.get('riggingBars') and not joints_of(lay)
    said = settled(page, lambda: page.inner_text('#rigging-curve-errors'), lambda s: 'Ask for 50% or less' in s)
    assert 'needs 22° at each joint' in said, said
    assert page.errors == []


def test_a_corner_folds_90_in_3d_and_the_obj_whatever_the_curve_limit(page):
    """A corner's 90 is riggingCorners, never held to the 20 a curve joint
    is: a seam corner beside curve joints stored at 30 (held to 20)."""
    ids = reset(page, [dict(WALL, columns=6)])
    page.evaluate("""(id) => { const a = window.app; const l = a.project.layers.find(x => x.id === id);
        l.riggingCorners = [{at: 3.5, angle: 90, side: 'interior'}];
        // the stored angles are a Curve's (only a screen with its Curve on
        // stands them)
        l.riggingCurve = {on: true};
        l.stage3d = {x: 0, y: 0, z: 0, pitch: 0, yaw: 0, roll: 0, pivot: 'bottom', jointsCol: {'0': 30, '4': 30}};
        a.updateLayers([l], true, 'Test'); }""", ids[0])
    page.wait_for_timeout(300)
    built = page.evaluate("""async (id) => {
        const m = await import('/static/js/app-stage3d.js');
        const l = window.app.project.layers.find(x => x.id === id);
        return { colJ: m.s3dBuild(l, window.app._s3dPlacementOf(l)).colJ };
    }""", ids[0])
    srv = settled(page, lambda: served(page, ids[0]), lambda l: (l.get('stage3d') or {}).get('jointsCol'))
    assert srv['stage3d']['jointsCol'] == {'0': 20, '4': 20}
    assert srv['riggingCorners'][0]['at'] == 3.5
    assert built['colJ'] == [20, 0, 90, 0, 20]
    obj = read_obj(obj_files(page)['Test_Show_WALL.obj'])
    pts = face_corners_xz(obj)
    heads = [math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) for a, b in zip(pts, pts[1:])]
    turns = [h1 - h0 for h0, h1 in zip(heads, heads[1:])]
    assert turns == pytest.approx([20, 0, 90, 0, 20], abs=1e-3)
    assert page.errors == []
