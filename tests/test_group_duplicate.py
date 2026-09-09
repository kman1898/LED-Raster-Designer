"""Duplicating a screen group - every path that can copy a grouped wall.

User report (2026-09-09, v0.11.2): "when he duplicated grouped screens they
only copy 1 screen".

A group IS ONE WALL. Copying it has to hand back the whole wall again: every
member, in the same order, enrolled in ONE new group, with the wiring pointing
at the copy's own peers. These tests walk every path in the app that can
duplicate a grouped screen and assert that, because the report is about a path
that copies a single member and calls it done:

    the group ⋮ menu -> Duplicate Group            duplicateGroup()
    Cmd/Ctrl+J and the canvas context menu         handleMenuAction('duplicate')
                                                   -> duplicateLayer()
    cross-canvas drag with Alt/Cmd held, one       moveLayerCrossCanvas()
    cross-canvas drag with Alt/Cmd held, many      moveLayersCrossCanvas()
    the canvas ⋮ menu -> Duplicate                 duplicateCanvas()

What decides whether a duplicate is aimed at THE WALL or at one screen is the
selection, because that is what the Screens list already means: clicking a
group's row selects every member ("select the whole wall, which is what every
downstream edit then acts on", _wireScreenGroupEl), and expanding the group to
click one member row selects that member alone. Duplicate now reads the same
signal - selectedWholeGroupFor in app-screen-groups.js.

Three rulings these tests deliberately keep from the existing suites:

* A COPY NEVER JOINS THE SOURCE'S GROUP. It forms its own (test_screen_groups
  .py::test_a_duplicate_does_not_join_the_group). Enrolling it would change the
  source wall's totals, port numbering and export without the user asking.
* HALF A WALL IS NOT A WALL. Copying SOME members of a group (one member of
  three, or a canvas holding only part of a group) hands back loose screens,
  not a group claiming to be the wall - test_screen_groups.py::
  test_cross_canvas_duplicate_does_not_carry_group_id and
  test_cross_layer_paths.py::test_canvas_duplicate_leaves_a_half_group_loose.
* A MEMBER PICKED OUT OF THE WALL still duplicates as one loose screen, with
  the path steps naming its peers dropped - test_cross_layer_paths_lifecycle
  .py::test_duplicating_one_member_drops_its_cross_member_entries.

And per-member power/data assignments COME ALONG: the group suites already
rule that a copied wall keeps its hand-drawn ports and circuits, remapped onto
the copy's own peers rather than dropped (app-screen-groups.js's remap call and
test_cross_layer_paths.py::test_canvas_duplicate_brings_the_group_and_
repoints_the_wiring), so that is asserted here too.

The N -> N guard (test_a_group_of_n_duplicates_to_n) is the one that fails
loudest if a future change drops members again.

Run locally:
    python -m pytest tests/test_group_duplicate.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project exactly as this module found it
    (see conftest.server_project_guard)."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    """One long-lived page; each test rebuilds a known project first."""
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)  # socket connect + app init
    yield pg
    context.close()


# ── the wall under test ───────────────────────────────────────────────────
#
# N screens of DIFFERENT sizes (the whole reason a wall needs more than one
# layer), the last one rotated, the first carrying a hand-drawn port run and
# power circuit that cross onto the second - the only cross-member state a
# copy can lose - then grouped, then history rebased so "one undo step" is
# measurable.

BUILD_JS = """async (n) => {
    const app = window.app;
    const jget = async (u) => (await fetch(u)).json();
    const send = async (u, method, body) => (await fetch(u, {
        method, headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
    })).json();

    // The live server is shared with every other browser suite, so start from
    // a project holding nothing but the screens this module made.
    let project = await jget('/api/project');
    project.layers = [];
    project.groups = [];
    await send('/api/project', 'PUT', project);

    for (let i = 0; i < n; i++) {
        await send('/api/layer/add', 'POST', {
            name: 'Wall' + (i + 1),
            columns: 2 + i, rows: 2 + (i % 2),
            cabinet_width: (i === 1 ? 64 : 128), cabinet_height: 128,
            offset_x: i * 700, offset_y: 0,
        });
    }

    app.project = await jget('/api/project');
    app.dedupeProjectLayers('group_duplicate_test_build');
    const screens = app.project.layers
        .filter(l => (l.type || 'screen') === 'screen').slice(0, n);
    const ids = screens.map(l => l.id);
    // Matching shared settings, so grouping needs no mismatch dialog.
    screens.forEach(l => {
        l.processorType = 'brompton'; l.bitDepth = 10; l.frameRate = 60;
        l.lowLatency = false; l.powerVoltage = 208;
    });
    screens[screens.length - 1].rotation = 90;
    await send('/api/project', 'PUT', app.project);
    app.project = await jget('/api/project');

    app.setSelectedLayersByIds(ids, ids[0]);
    const gid = await app.groupSelectedLayers();

    // Hand-assigned run + circuit on the first member, each crossing onto the
    // second. Written AFTER grouping, because a step naming a non-peer is
    // pruned by _enforce_group_integrity on the way in.
    const a = app.project.layers.find(l => l.id === ids[0]);
    a.customPortOverrides = [2];
    a.customPortPaths = {'2': [
        {row: 0, col: 0}, {row: 0, col: 1}, {row: 0, col: 0, layerId: ids[1]},
    ]};
    a.powerCustomOverrides = [1];
    a.powerCustomPaths = {'1': [
        {row: 1, col: 0}, {row: 1, col: 0, layerId: ids[1]},
    ]};
    await send('/api/project', 'PUT', app.project);
    app.project = await jget('/api/project');
    app.setSelectedLayersByIds(ids, ids[0]);

    // Land any debounced snapshot still in flight BEFORE rebasing, otherwise
    // it fires later and shows up as a second entry against the duplicate.
    if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
    app.resetHistory('Test Reset');
    app.renderLayers();
    if (window.canvasRenderer) window.canvasRenderer.render();
    return {ids, gid, groups: (app.project.groups || []).length};
}"""


def build_group(page, n=3):
    """`n` differently-sized screens joined into one group. Returns
    (ids, gid)."""
    out = page.evaluate(BUILD_JS, n)
    page.wait_for_timeout(700)
    assert out['gid'], out
    assert out['groups'] == 1, out
    assert len(out['ids']) == n, out
    return out['ids'], out['gid']


# ── readers ───────────────────────────────────────────────────────────────

MODEL_JS = """(args) => {
    const [ids, gid] = args;
    const app = window.app;
    const layers = app.project.layers || [];
    const groups = app.project.groups || [];
    const copies = layers.filter(l => !ids.includes(l.id)
        && (l.type || 'screen') === 'screen');
    const copyGroups = groups.filter(g => g.id !== gid);
    const shape = (l) => ({
        id: l.id, name: l.name, group_id: l.group_id ?? null,
        columns: l.columns, rows: l.rows,
        cabinet_width: l.cabinet_width, cabinet_height: l.cabinet_height,
        rotation: l.rotation || 0,
        offset_x: l.offset_x, offset_y: l.offset_y,
        canvas_id: l.canvas_id,
        customPortPaths: l.customPortPaths || null,
        powerCustomPaths: l.powerCustomPaths || null,
        customPortOverrides: l.customPortOverrides || [],
        powerCustomOverrides: l.powerCustomOverrides || [],
    });
    return {
        layerCount: layers.length,
        sources: ids.map(id => shape(layers.find(l => l.id === id))),
        copies: copies.map(shape),
        sourceGroup: (groups.find(g => g.id === gid) || {}).layer_ids || null,
        copyGroups: copyGroups.map(g => ({id: g.id, name: g.name,
                                          layer_ids: g.layer_ids})),
        groupCount: groups.length,
        lastAction: app.history[app.history.length - 1].action,
    };
}"""


def model(page, ids, gid):
    return page.evaluate(MODEL_JS, [ids, gid])


def server_model(page, ids, gid):
    """The same picture, read back from the server rather than the client -
    a copy the client believes in but never persisted is not a copy."""
    return page.evaluate("""async (args) => {
        const [ids, gid] = args;
        const p = await (await fetch('/api/project')).json();
        const copies = (p.layers || []).filter(
            l => !ids.includes(l.id) && (l.type || 'screen') === 'screen');
        return {
            layerCount: (p.layers || []).length,
            copyIds: copies.map(l => l.id),
            copyGroupIds: copies.map(l => l.group_id ?? null),
            groups: (p.groups || []).map(g => ({id: g.id,
                                                layer_ids: g.layer_ids})),
        };
    }""", [ids, gid])


def history_len(page):
    return page.evaluate("window.app.history.length")


def history_actions(page):
    return page.evaluate("window.app.history.map(h => h.action)")


def undo(page):
    page.evaluate("window.app.handleMenuAction('undo')")
    page.wait_for_timeout(900)


def _next_duplicate_name(name):
    """The app's own convention (app-screen-groups.js _nextDuplicateName /
    app-history.js getNextName): a trailing number increments, otherwise " 1"
    is appended."""
    import re
    m = re.match(r'^(.*?)(\d+)$', name)
    if m:
        return f'{m.group(1)}{int(m.group(2)) + 1}'
    return f'{name} 1'


def assert_whole_wall_copied(page, ids, gid, state, *, nudged=True):
    """Every shared assertion about "the wall came across whole"."""
    n = len(ids)
    assert len(state['copies']) == n, (
        f'{n}-screen wall duplicated to {len(state["copies"])} screen(s): '
        f'{state["copies"]}')
    assert len(state['copyGroups']) == 1, (
        f'the copies did not form ONE new group: {state["copyGroups"]}')
    copy_group = state['copyGroups'][0]
    assert copy_group['id'] != gid, state
    # Same order as the source wall, member for member.
    assert copy_group['layer_ids'] == [c['id'] for c in state['copies']], state
    assert len(copy_group['layer_ids']) == n, copy_group
    assert all(c['group_id'] == copy_group['id'] for c in state['copies']), state
    # The source wall is untouched.
    assert state['sourceGroup'] == ids, state
    # Per-member geometry rides along: the sizes are why the wall needed
    # more than one layer, and the rotation is one member's own.
    for src, copy in zip(state['sources'], state['copies']):
        assert (copy['columns'], copy['rows']) == (src['columns'], src['rows']), \
            (src, copy)
        assert (copy['cabinet_width'], copy['cabinet_height']) \
            == (src['cabinet_width'], src['cabinet_height']), (src, copy)
        assert copy['rotation'] == src['rotation'], (src, copy)
        assert copy['name'] == _next_duplicate_name(src['name']), (src, copy)
        if nudged:
            assert copy['offset_x'] == src['offset_x'] + 50, (src, copy)
            assert copy['offset_y'] == src['offset_y'] + 50, (src, copy)
    # The hand-drawn run and circuit came across, repointed at the COPY's own
    # peer - never back into the wall they were copied from.
    copy_a, copy_b = state['copies'][0], state['copies'][1]
    assert copy_a['customPortOverrides'] == [2], copy_a
    assert copy_a['powerCustomOverrides'] == [1], copy_a
    assert copy_a['customPortPaths'] == {'2': [
        {'row': 0, 'col': 0}, {'row': 0, 'col': 1},
        {'row': 0, 'col': 0, 'layerId': copy_b['id']},
    ]}, copy_a
    assert copy_a['powerCustomPaths'] == {'1': [
        {'row': 1, 'col': 0}, {'row': 1, 'col': 0, 'layerId': copy_b['id']},
    ]}, copy_a
    # And the server holds the same wall the client drew.
    stored = server_model(page, ids, gid)
    assert len(stored['copyIds']) == n, stored
    assert len(set(stored['copyGroupIds'])) == 1, stored
    assert stored['copyGroupIds'][0] == copy_group['id'], stored
    return copy_group


def assert_copies_are_independent(page, ids, state):
    """Editing a copy must not reach back into the source wall."""
    copy_ids = [c['id'] for c in state['copies']]
    out = page.evaluate("""async (args) => {
        const [ids, copyIds] = args;
        const app = window.app;
        const byId = (id) => app.project.layers.find(l => l.id === id);
        copyIds.forEach((id, i) => { byId(id).name = 'Edited' + i; });
        byId(copyIds[0]).offset_x = 9999;
        byId(copyIds[0]).customPortPaths = {'2': [{row: 5, col: 5}]};
        await app.updateLayers(copyIds.map(byId), false);
        return {
            sourceNames: ids.map(id => byId(id).name),
            sourceOffsets: ids.map(id => byId(id).offset_x),
            sourcePaths: byId(ids[0]).customPortPaths,
        };
    }""", [ids, copy_ids])
    return out


# ══════════════════════════════════════════════════════════════════════════
# 1. the group ⋮ menu -> "Duplicate Group"
# ══════════════════════════════════════════════════════════════════════════

def test_duplicate_group_menu_copies_every_member(page):
    ids, gid = build_group(page, 3)
    before_layers = page.evaluate("window.app.project.layers.length")
    before_history = history_len(page)
    before_sources = model(page, ids, gid)['sources']

    # The real menu path, not duplicateGroup() directly.
    page.evaluate("""async (gid) => {
        const group = window.app.resolveGroup(gid);
        window.app._handleScreenGroupMenuAction(group, 'duplicate');
    }""", gid)
    page.wait_for_timeout(1400)

    state = model(page, ids, gid)
    assert state['layerCount'] == before_layers + 3, state
    copy_group = assert_whole_wall_copied(page, ids, gid, state)
    assert copy_group['name'] == _next_duplicate_name('Group 1'), copy_group
    assert state['lastAction'] == 'Duplicate Group', state
    assert history_len(page) == before_history + 1, history_actions(page)

    # One undo takes the WHOLE duplication back.
    undo(page)
    after = model(page, ids, gid)
    assert after['layerCount'] == before_layers, after
    assert after['copies'] == [], after
    assert after['groupCount'] == 1, after
    assert after['sourceGroup'] == ids, after
    assert [s['name'] for s in after['sources']] \
        == [s['name'] for s in before_sources], after


def test_duplicate_group_copies_are_independent_of_the_source(page):
    ids, gid = build_group(page, 3)
    page.evaluate("(g) => window.app.duplicateGroup(g)", gid)
    page.wait_for_timeout(1400)
    state = model(page, ids, gid)
    assert len(state['copies']) == 3, state

    out = assert_copies_are_independent(page, ids, state)
    assert out['sourceNames'] == ['Wall1', 'Wall2', 'Wall3'], out
    assert out['sourceOffsets'] == [0, 700, 1400], out
    assert out['sourcePaths'] == {'2': [
        {'row': 0, 'col': 0}, {'row': 0, 'col': 1},
        {'row': 0, 'col': 0, 'layerId': ids[1]},
    ]}, out


@pytest.mark.parametrize('n', [2, 3, 4])
def test_a_group_of_n_duplicates_to_n(page, n):
    """The count guard. A wall of N screens copies to N screens in one new
    group - if a future change drops members, this is what says so."""
    ids, gid = build_group(page, n)
    page.evaluate("(g) => window.app.duplicateGroup(g)", gid)
    page.wait_for_timeout(1400)

    state = model(page, ids, gid)
    assert len(state['copies']) == n, (
        f'group of {n} duplicated to {len(state["copies"])}')
    assert len(state['copyGroups']) == 1, state
    assert len(state['copyGroups'][0]['layer_ids']) == n, state
    stored = server_model(page, ids, gid)
    assert len(stored['copyIds']) == n, stored


# ══════════════════════════════════════════════════════════════════════════
# 2. Cmd/Ctrl+J and the canvas context menu -> "Duplicate"
# ══════════════════════════════════════════════════════════════════════════

def test_duplicating_a_grouped_screen_copies_the_whole_wall(page):
    """THE REPORTED BUG. With a group selected, Duplicate (Cmd/Ctrl+J, the
    canvas context menu, the menu bar) copied ONE member: the wall came back
    as a single loose screen."""
    ids, gid = build_group(page, 3)
    before_layers = page.evaluate("window.app.project.layers.length")
    before_history = history_len(page)

    page.evaluate("() => window.app.handleMenuAction('duplicate')")
    page.wait_for_timeout(1600)

    state = model(page, ids, gid)
    assert state['layerCount'] == before_layers + 3, (
        'Duplicate on a grouped screen copied '
        f'{len(state["copies"])} of 3 members: {state["copies"]}')
    assert_whole_wall_copied(page, ids, gid, state)
    assert history_len(page) == before_history + 1, history_actions(page)

    undo(page)
    after = model(page, ids, gid)
    assert after['layerCount'] == before_layers, after
    assert after['groupCount'] == 1, after


def test_duplicating_the_wall_works_from_any_member(page):
    """Same path with the wall selected but the LAST member in hand: the wall
    is the wall whichever of its screens the gesture started from."""
    ids, gid = build_group(page, 3)
    page.evaluate("(ids) => window.app.setSelectedLayersByIds(ids, ids[2])", ids)
    page.wait_for_timeout(200)

    page.evaluate("() => window.app.duplicateLayer(window.app.currentLayer)")
    page.wait_for_timeout(1600)

    state = model(page, ids, gid)
    assert len(state['copies']) == 3, state
    assert len(state['copyGroups']) == 1, state
    assert state['copyGroups'][0]['layer_ids'] == [c['id'] for c in state['copies']], state


def test_duplicating_one_member_picked_out_of_the_wall_makes_one_screen(page):
    """The counterweight, and the existing ruling this fix keeps: expand the
    group, click ONE member, Duplicate - and you get that one screen, loose,
    with the path step naming its peer dropped (it has no peer any more).

    Pinned here as well as in test_cross_layer_paths_lifecycle.py because the
    two gestures now part company inside duplicateLayer, and the difference
    between them is the whole fix."""
    ids, gid = build_group(page, 3)
    before = page.evaluate("window.app.project.layers.length")
    page.evaluate("(ids) => window.app.setSelectedLayersByIds([ids[0]], ids[0])", ids)
    page.wait_for_timeout(200)

    page.evaluate("() => window.app.duplicateLayer(window.app.currentLayer)")
    page.wait_for_timeout(1600)

    state = model(page, ids, gid)
    assert state['layerCount'] == before + 1, state
    assert len(state['copies']) == 1, state
    copy = state['copies'][0]
    assert copy['group_id'] is None, copy
    assert state['copyGroups'] == [], state
    assert state['sourceGroup'] == ids, state
    # The cross-member step went with the peer it named; the rest stayed.
    assert copy['customPortPaths'] == {'2': [
        {'row': 0, 'col': 0}, {'row': 0, 'col': 1},
    ]}, copy


def test_duplicating_an_ungrouped_screen_still_makes_one_loose_screen(page):
    """The counterweight: a screen in no group duplicates to exactly one
    screen, in no group. Copying the wall must not leak into the ordinary
    case."""
    ids, gid = build_group(page, 3)
    solo = page.evaluate("""async () => {
        const app = window.app;
        const created = await (await fetch('/api/layer/add', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name: 'Solo1', columns: 2, rows: 2,
                                  cabinet_width: 128, cabinet_height: 128,
                                  offset_x: 3000}),
        })).json();
        app.project = await (await fetch('/api/project')).json();
        app.setSelectedLayersByIds([created.id], created.id);
        return created.id;
    }""")
    page.wait_for_timeout(400)
    before = page.evaluate("window.app.project.layers.length")

    page.evaluate("() => window.app.handleMenuAction('duplicate')")
    page.wait_for_timeout(1400)

    out = page.evaluate("""(args) => {
        const [ids, solo] = args;
        const app = window.app;
        const known = ids.concat([solo]);
        const extras = app.project.layers.filter(l => !known.includes(l.id));
        return {
            count: app.project.layers.length,
            extras: extras.map(l => ({name: l.name, group_id: l.group_id ?? null})),
            groups: (app.project.groups || []).length,
        };
    }""", [ids, solo])
    assert out['count'] == before + 1, out
    assert len(out['extras']) == 1, out
    assert out['extras'][0]['group_id'] is None, out
    assert out['extras'][0]['name'] == 'Solo2', out
    assert out['groups'] == 1, out


# ══════════════════════════════════════════════════════════════════════════
# 3. cross-canvas duplicate (Alt/Cmd-drag onto another canvas)
# ══════════════════════════════════════════════════════════════════════════

def add_canvas(page):
    return page.evaluate("""async () => {
        const app = window.app;
        const p = await (await fetch('/api/canvas', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name: 'Target'}),
        })).json();
        app.project = await (await fetch('/api/project')).json();
        return p.canvases[p.canvases.length - 1].id;
    }""")


def test_cross_canvas_duplicate_of_a_whole_group_lands_as_one_wall(page):
    """Dragging the whole wall onto another canvas with Alt/Cmd held copies
    the wall - all of it, still a wall - onto that canvas."""
    ids, gid = build_group(page, 3)
    target = add_canvas(page)
    page.wait_for_timeout(300)
    before_layers = page.evaluate("window.app.project.layers.length")

    page.evaluate("""async (args) => {
        const [ids, target] = args;
        await window.app.moveLayersCrossCanvas(ids, target, 'duplicate');
    }""", [ids, target])
    page.wait_for_timeout(1600)

    state = model(page, ids, gid)
    assert state['layerCount'] == before_layers + 3, (
        f'3-screen wall duplicated to {len(state["copies"])} screen(s) on the '
        f'target canvas: {state["copies"]}')
    assert len(state['copies']) == 3, state
    assert all(c['canvas_id'] == target for c in state['copies']), state
    assert len(state['copyGroups']) == 1, (
        f'the copies landed loose instead of as one wall: {state["copyGroups"]}')
    copy_group = state['copyGroups'][0]
    assert copy_group['id'] != gid, state
    assert copy_group['layer_ids'] == [c['id'] for c in state['copies']], state
    assert state['sourceGroup'] == ids, state
    stored = server_model(page, ids, gid)
    assert len(stored['copyIds']) == 3, stored
    assert len(set(stored['copyGroupIds'])) == 1, stored
    assert stored['copyGroupIds'][0] is not None, stored


def test_cross_canvas_duplicate_of_one_member_stays_a_loose_screen(page):
    """Half a wall is not a wall: copying ONE member onto another canvas
    hands back a loose screen (the ruling in test_screen_groups.py::
    test_cross_canvas_duplicate_does_not_carry_group_id)."""
    ids, gid = build_group(page, 3)
    target = add_canvas(page)
    page.wait_for_timeout(300)

    page.evaluate("""async (args) => {
        const [id, target] = args;
        await window.app.moveLayerCrossCanvas(id, target, 'duplicate');
    }""", [ids[0], target])
    page.wait_for_timeout(1400)

    state = model(page, ids, gid)
    assert len(state['copies']) == 1, state
    assert state['copies'][0]['group_id'] is None, state
    assert state['copyGroups'] == [], state
    assert state['sourceGroup'] == ids, state


def test_cross_canvas_move_of_a_whole_group_keeps_the_wall_together(page):
    """The move half of the same gesture: the wall arrives on the target
    canvas still grouped, not as three loose screens."""
    ids, gid = build_group(page, 3)
    target = add_canvas(page)
    page.wait_for_timeout(300)
    before_layers = page.evaluate("window.app.project.layers.length")

    page.evaluate("""async (args) => {
        const [ids, target] = args;
        await window.app.moveLayersCrossCanvas(ids, target, 'move');
    }""", [ids, target])
    page.wait_for_timeout(1600)

    out = page.evaluate("""(args) => {
        const [ids, gid, target] = args;
        const app = window.app;
        const layers = app.project.layers || [];
        const members = ids.map(id => layers.find(l => l.id === id));
        return {
            count: layers.length,
            canvases: members.map(l => l.canvas_id),
            groupIds: members.map(l => l.group_id ?? null),
            groups: (app.project.groups || []).map(
                g => ({id: g.id, layer_ids: g.layer_ids})),
        };
    }""", [ids, gid, target])
    assert out['count'] == before_layers, out
    assert out['canvases'] == [target] * 3, out
    assert len(out['groups']) == 1, (
        f'the wall dissolved on the way across: {out}')
    assert out['groups'][0]['layer_ids'] == ids, out
    assert out['groupIds'] == [out['groups'][0]['id']] * 3, out


# ══════════════════════════════════════════════════════════════════════════
# 4. the canvas ⋮ menu -> "Duplicate" (a canvas holding the group)
# ══════════════════════════════════════════════════════════════════════════

def test_duplicating_a_canvas_brings_the_whole_group(page):
    ids, gid = build_group(page, 3)
    before_layers = page.evaluate("window.app.project.layers.length")

    page.evaluate("""async () => {
        const app = window.app;
        await app.duplicateCanvas(app.project.active_canvas_id);
    }""")
    page.wait_for_timeout(1600)

    state = model(page, ids, gid)
    assert state['layerCount'] == before_layers + 3, state
    assert len(state['copies']) == 3, state
    assert len(state['copyGroups']) == 1, state
    copy_group = state['copyGroups'][0]
    assert len(copy_group['layer_ids']) == 3, copy_group
    assert copy_group['id'] != gid, state
    assert all(c['group_id'] == copy_group['id'] for c in state['copies']), state
    assert state['sourceGroup'] == ids, state
    # The copy's wiring points at the copy's own peer.
    copy_a, copy_b = state['copies'][0], state['copies'][1]
    assert copy_a['customPortPaths'] == {'2': [
        {'row': 0, 'col': 0}, {'row': 0, 'col': 1},
        {'row': 0, 'col': 0, 'layerId': copy_b['id']},
    ]}, copy_a
