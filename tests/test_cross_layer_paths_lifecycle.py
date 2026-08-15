"""Cross-member manual paths (v0.11.0, step 6) - the COPY lifecycle (Playwright).

A customPortPaths / powerCustomPaths entry is normally {row, col}: a panel in
the layer that owns the path, which is how every project written before step 6
looks. A path hand-drawn across a group's members stores {row, col, layerId}
for the panels living in a peer member.

layerId is a layer id, and a layer id only means something inside the project
that minted it. Duplicate, paste and presets all deep-copied paths verbatim,
so this file pins what each of them is allowed to carry:

* REMAP when the named peer is copied too (duplicating a whole wall keeps its
  wiring), DROP when it is not.
* DROP is the answer for paste in particular, because the clipboard outlives
  the project it was filled from. A stale layerId that lands on a same-numbered
  layer in another project would attach the pasted screen's port to an
  unrelated wall silently - strictly worse than losing the entry.
* A path that loses every entry loses its KEY too. An empty path is not a path;
  leaving `{"1": []}` behind advertises port 1 as hand-routed with nothing drawn.
* A plain {row, col} path is the regression guard and appears in nearly every
  test here: a project with no groups must behave EXACTLY as it did before.

Run locally:
    python -m pytest tests/test_cross_layer_paths_lifecycle.py -v --browser chromium
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
    """One long-lived page; each test resets to a known project first."""
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)  # socket connect + app init
    yield pg
    context.close()


@pytest.fixture(autouse=True)
def settle(page):
    """Let each test's trailing writes land before the next one starts.

    duplicate, paste, group, ungroup and duplicateGroup all finish with a fetch
    the caller does not await. One of them completing during the NEXT test puts
    the previous project back on the server underneath it, and the test that
    fails is then the innocent one downstream."""
    yield
    page.wait_for_timeout(1200)


# ── helpers ───────────────────────────────────────────────────────────────

RESET_JS = """async (count) => {
    const app = window.app;
    // The live server is shared with every other browser test file, so start
    // from an empty layer list and build exactly `count` screens through the
    // real add endpoint - every assertion below is then about layers this
    // module created.
    let project = await (await fetch('/api/project')).json();
    project.layers = [];
    project.groups = [];
    await fetch('/api/project', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(project),
    });
    for (let i = 0; i < count; i++) {
        await fetch('/api/layer/add', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                name: 'PathTest' + (i + 1),
                columns: 2, rows: 2, cabinet_width: 128, cabinet_height: 128,
            }),
        });
    }
    app.project = await (await fetch('/api/project')).json();
    app.dedupeProjectLayers('cross_layer_paths_test_reset');
    const screens = app.project.layers.filter(
        l => (l.type || 'screen') === 'screen').slice(0, count);
    // Grouping refuses screens whose shared settings disagree, and the
    // mismatch dialog is not what this file is testing.
    screens.forEach(l => {
        l.processorType = 'brompton'; l.bitDepth = 10; l.frameRate = 60;
        l.customPortPaths = {}; l.powerCustomPaths = {};
    });
    await fetch('/api/project', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(app.project),
    });
    app.currentLayer = screens[0];
    app.selectedLayerIds = new Set([screens[0].id]);
    if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
    app.resetHistory('Test Reset');
    app.renderLayers();
    return screens.map(l => l.id);
}"""


def reset_project(page, count=3):
    """Deterministic starting point: `count` ungrouped 2x2 screens with
    matching settings and no paths. Returns those ids and no others.

    Verified against the SERVER, and retried, because every action in this file
    ends in a PUT the test does not await (duplicate, paste, group, ungroup all
    fire and forget). One of those landing in the middle of the next test's
    reset would restore the previous project on top of the fresh one, and the
    test that then failed would be the innocent one downstream."""
    server_ids = None
    for _ in range(4):
        page.wait_for_timeout(600)   # let anything still in flight land first
        ids = page.evaluate(RESET_JS, count)
        page.wait_for_timeout(700)
        read_server = ("async () => (await (await fetch('/api/project')).json())"
                       ".layers.map(l => l.id)")
        server_ids = page.evaluate(read_server)
        if len(ids) != count or server_ids != ids:
            continue
        # Read it a second time after a gap: a PUT that was already on the wire
        # when the first read answered would otherwise put the old project back
        # underneath a test that has just checked its state.
        page.wait_for_timeout(500)
        if page.evaluate(read_server) == ids:
            return ids
    raise AssertionError(
        f'project would not settle to {count} clean screens: '
        f'client {ids}, server {server_ids}')


def select(page, ids):
    page.evaluate("""(ids) => {
        window.app.setSelectedLayersByIds(ids, ids[0]);
        window.app.currentLayer = window.app.project.layers.find(l => l.id === ids[0]);
    }""", ids)
    page.wait_for_timeout(200)


def set_paths(page, layer_id, custom_port_paths=None, power_paths=None):
    page.evaluate("""(args) => {
        const layer = window.app.project.layers.find(l => l.id === args.id);
        if (args.ports) layer.customPortPaths = args.ports;
        if (args.power) layer.powerCustomPaths = args.power;
    }""", {'id': layer_id, 'ports': custom_port_paths, 'power': power_paths})


def paths_of(page, layer_id):
    return page.evaluate("""(id) => {
        const layer = window.app.project.layers.find(l => l.id === id);
        if (!layer) return null;
        return {
            ports: layer.customPortPaths || {},
            power: layer.powerCustomPaths || {},
        };
    }""", layer_id)


def group(page, ids):
    """Group `ids` and return the new group id.

    Membership is re-read after the commit rather than trusted from the return
    value: the server repairs group membership on the PUT inside
    _commitGroupChange, so a group that did not survive that has to fail HERE.
    Every cross-member assertion below is meaningless without a real group."""
    select(page, ids)
    gid = page.evaluate("window.app.groupSelectedLayers()")
    page.wait_for_timeout(900)
    assert gid, 'grouping failed - a settings mismatch dialog is likely open'
    membership = page.evaluate("""(args) => args.ids.map(id => {
        const layer = window.app.project.layers.find(l => l.id === id);
        return layer ? (layer.group_id ?? null) : 'missing';
    })""", {'ids': ids})
    assert membership == [gid] * len(ids), (
        f'group {gid} did not stick: {membership}')
    return gid


def duplicate_and_get_clone(page, layer_id):
    """Run the real duplicateLayer and return the id of what it created.

    Read off currentLayer rather than by name or by diffing the layer list:
    duplicateLayer's name incrementing ("PathTest1" -> "PathTest2") can collide
    with a name another screen already has, and a list diff picks up anything a
    still-in-flight fetch from an earlier test drops in. duplicateLayer selects
    what it made, so waiting for the selection to move is the one signal that
    means "this duplicate finished"."""
    select(page, [layer_id])
    page.evaluate("""(id) => {
        const layer = window.app.project.layers.find(l => l.id === id);
        window.app.duplicateLayer(layer);
    }""", layer_id)
    page.wait_for_function(
        "id => window.app.currentLayer && window.app.currentLayer.id !== id",
        arg=layer_id, timeout=10000)
    return page.evaluate("window.app.currentLayer.id")


def paste_and_get_new(page):
    """Run the real pasteLayer and return the id of what it created. Same
    currentLayer signal as duplicate_and_get_clone."""
    before = page.evaluate("window.app.currentLayer ? window.app.currentLayer.id : null")
    page.evaluate("window.app.pasteLayer()")
    page.wait_for_function(
        "id => window.app.currentLayer && window.app.currentLayer.id !== id",
        arg=before, timeout=10000)
    return page.evaluate("window.app.currentLayer.id")


def layer_ids_in(paths):
    """Every layerId appearing anywhere in a {ports, power} snapshot."""
    found = []
    for group_of_paths in (paths['ports'], paths['power']):
        for path in group_of_paths.values():
            for entry in path:
                if isinstance(entry, dict) and entry.get('layerId') is not None:
                    found.append(entry['layerId'])
    return found


# ── the regression guard: no groups, no layerId, nothing changes ──────────


def test_a_plain_path_survives_duplicate_untouched(page):
    """The primary regression guard. A path with no cross-member entry is
    every path in every project written before step 6, and duplicate has to
    keep copying it verbatim - same keys, same entries, same order."""
    ids = reset_project(page, 2)
    ports = {'1': [{'row': 0, 'col': 0}, {'row': 0, 'col': 1}, {'row': 1, 'col': 1}],
             '2': [{'row': 1, 'col': 0}]}
    power = {'1': [{'row': 0, 'col': 0}, {'row': 1, 'col': 0}]}
    set_paths(page, ids[0], ports, power)

    clone_id = duplicate_and_get_clone(page, ids[0])
    clone = paths_of(page, clone_id)

    assert clone['ports'] == ports, clone
    assert clone['power'] == power, clone
    # And the source is not disturbed by having been copied.
    assert paths_of(page, ids[0])['ports'] == ports


def test_a_plain_path_survives_paste_untouched(page):
    """Same guard on the clipboard path."""
    ids = reset_project(page, 2)
    ports = {'3': [{'row': 0, 'col': 1}, {'row': 1, 'col': 1}]}
    set_paths(page, ids[0], ports, {})
    select(page, [ids[0]])
    page.evaluate("window.app.copyLayer()")

    pasted_id = paste_and_get_new(page)
    assert paths_of(page, pasted_id)['ports'] == ports


# ── duplicate ─────────────────────────────────────────────────────────────


def test_duplicating_one_member_drops_its_cross_member_entries(page):
    """Duplicate makes a new UNGROUPED screen (it deliberately does not carry
    group_id), so no peer comes with it. The entry naming that peer cannot be
    remapped and must not be kept: keeping it would leave the copy's port
    reaching into the ORIGINAL wall, from outside that wall's group.

    The plain entries in the same path survive - the part of the route that is
    still inside the copy is still the user's route."""
    ids = reset_project(page, 3)
    a, b = ids[0], ids[1]
    group(page, [a, b])
    set_paths(page, a, {'1': [
        {'row': 0, 'col': 0},
        {'row': 0, 'col': 1, 'layerId': b},
        {'row': 1, 'col': 0},
    ]})

    clone_id = duplicate_and_get_clone(page, a)
    clone = paths_of(page, clone_id)

    assert clone['ports'] == {'1': [{'row': 0, 'col': 0}, {'row': 1, 'col': 0}]}, clone
    assert layer_ids_in(clone) == [], clone
    # The original keeps its cross-member entry - a copy must not edit it.
    assert layer_ids_in(paths_of(page, a)) == [b]


def test_duplicate_removes_a_path_that_loses_every_entry(page):
    """A path made ENTIRELY of peer panels has nothing left after the drop, so
    the key goes too. `{"2": []}` would show port 2 as hand-routed with an
    empty route, which is not a state the user can reach or clear."""
    ids = reset_project(page, 3)
    a, b = ids[0], ids[1]
    group(page, [a, b])
    set_paths(
        page, a,
        {'1': [{'row': 0, 'col': 0}],
         '2': [{'row': 0, 'col': 0, 'layerId': b}, {'row': 1, 'col': 1, 'layerId': b}]},
        {'4': [{'row': 1, 'col': 1, 'layerId': b}]},
    )

    clone_id = duplicate_and_get_clone(page, a)
    clone = paths_of(page, clone_id)

    assert list(clone['ports'].keys()) == ['1'], clone
    assert clone['ports']['1'] == [{'row': 0, 'col': 0}], clone
    assert clone['power'] == {}, clone


def test_duplicating_a_whole_group_remaps_layer_ids_to_the_clones(page):
    """The remap case. When the peer a path names IS copied alongside the
    owner, the user duplicated a wall and expects the wiring to come with it,
    so the entry is re-pointed at that peer's CLONE - never left pointing at
    the original, which would make the new wall drive the old one's cabinets.

    remapCopiedLayerPaths is the whole-set entry point; it always derives the
    clone's paths from the source's, so running it twice is a no-op and this
    test stays honest once duplicateGroup calls it itself."""
    ids = reset_project(page, 3)
    a, b = ids[0], ids[1]
    gid = group(page, [a, b])
    # A owns a port that reaches into B, and B owns a circuit that reaches
    # back into A - both directions have to land on the right clone.
    set_paths(page, a, {'1': [{'row': 0, 'col': 0}, {'row': 0, 'col': 1, 'layerId': b}]})
    set_paths(page, b, None, {'2': [{'row': 1, 'col': 1, 'layerId': a}, {'row': 1, 'col': 0}]})

    result = page.evaluate("""async (gid) => {
        const app = window.app;
        const sources = app.getGroupMembers(gid);
        const newGid = await app.duplicateGroup(gid);
        const clones = app.getGroupMembers(newGid);
        app.remapCopiedLayerPaths(
            sources.map((s, i) => ({ source: s, clone: clones[i] })));
        return {
            newGid: newGid,
            sourceIds: sources.map(l => l.id),
            cloneIds: clones.map(l => l.id),
            clonePorts: clones.map(l => l.customPortPaths || {}),
            clonePower: clones.map(l => l.powerCustomPaths || {}),
            sourcePorts: sources.map(l => l.customPortPaths || {}),
        };
    }""", gid)
    page.wait_for_timeout(600)

    clone_a, clone_b = result['cloneIds']
    assert clone_a not in (a, b) and clone_b not in (a, b), result

    # A' -> B' (the clone), NOT the original B.
    entry = result['clonePorts'][0]['1'][1]
    assert entry['layerId'] == clone_b, result
    assert entry['layerId'] != b, result
    assert result['clonePorts'][0]['1'][0] == {'row': 0, 'col': 0}, result

    # B' -> A', the other direction.
    back = result['clonePower'][1]['2'][0]
    assert back['layerId'] == clone_a, result
    assert back['layerId'] != a, result

    # The source wall is untouched by having been duplicated.
    assert result['sourcePorts'][0]['1'][1]['layerId'] == b, result


# ── paste ─────────────────────────────────────────────────────────────────


def test_paste_into_another_project_attaches_nothing_to_an_unrelated_screen(page):
    """The clipboard outlives the project it was filled from, and layer ids are
    per project. This reproduces the id landing on a DIFFERENT screen: the
    copied entry names a layer id that, by the time of the paste, belongs to an
    unrelated ungrouped screen. The paste must not wire the pasted port into
    it - the entry is dropped."""
    ids = reset_project(page, 3)
    a, b = ids[0], ids[1]
    group(page, [a, b])
    set_paths(page, a, {'1': [{'row': 0, 'col': 0}, {'row': 1, 'col': 1, 'layerId': b}]})
    select(page, [a])
    page.evaluate("window.app.copyLayer()")

    # A different project: new layers, new ids, no groups.
    fresh = reset_project(page, 3)
    stranger = fresh[2]
    # Re-point the stale entry at a layer id that now names an unrelated
    # screen - the exact collision a second project makes possible.
    page.evaluate("""(sid) => {
        window.app.clipboard.customPortPaths['1'][1].layerId = sid;
    }""", stranger)

    pasted_id = paste_and_get_new(page)
    assert pasted_id not in fresh, (
        f'paste reused an existing layer id ({pasted_id} of {fresh}) - the '
        f'project was not settled, so this run proves nothing')
    pasted = paths_of(page, pasted_id)
    assert pasted['ports'] == {'1': [{'row': 0, 'col': 0}]}, pasted
    assert layer_ids_in(pasted) == [], pasted
    # The unrelated screen gained no wiring of its own.
    assert paths_of(page, stranger)['ports'] == {}


# ── presets ───────────────────────────────────────────────────────────────


def test_a_preset_never_carries_a_layer_id_out_of_its_project(page):
    """A preset is reused in other projects, so it is the same hazard as the
    clipboard with a longer memory. Cross-member entries are stripped when the
    preset is serialized, and again when it is applied; the plain {row, col}
    route travels, because the geometry that gives it meaning travels too."""
    ids = reset_project(page, 3)
    a, b = ids[0], ids[1]
    group(page, [a, b])
    set_paths(page, a,
              {'1': [{'row': 0, 'col': 0}, {'row': 0, 'col': 1, 'layerId': b}],
               '2': [{'row': 1, 'col': 1, 'layerId': b}]},
              {'1': [{'row': 0, 'col': 0}]})

    preset = page.evaluate("""(id) => {
        const layer = window.app.project.layers.find(l => l.id === id);
        return window.app.serializeLayerAsPreset(layer);
    }""", a)

    assert preset['customPortPaths'] == {'1': [{'row': 0, 'col': 0}]}, preset
    assert preset['powerCustomPaths'] == {'1': [{'row': 0, 'col': 0}]}, preset

    # And a preset hand-edited (or written by an in-between build) to hold a
    # layerId still cannot land one on a layer.
    applied = page.evaluate("""(args) => {
        const layer = { id: 999999, type: 'screen' };
        const preset = JSON.parse(JSON.stringify(args.preset));
        preset.customPortPaths = {'1': [
            {row: 0, col: 0}, {row: 0, col: 1, layerId: args.peer}]};
        window.app.applyPresetClientProps(layer, preset);
        return layer.customPortPaths;
    }""", {'preset': preset, 'peer': b})
    assert applied == {'1': [{'row': 0, 'col': 0}]}, applied


def test_a_preset_from_an_ungrouped_screen_is_unchanged(page):
    """Regression guard for the preset path: a screen with no cross-member
    entries serializes exactly the paths it holds."""
    ids = reset_project(page, 2)
    ports = {'1': [{'row': 0, 'col': 0}, {'row': 1, 'col': 0}]}
    set_paths(page, ids[0], ports, {})

    preset = page.evaluate("""(id) => {
        const layer = window.app.project.layers.find(l => l.id === id);
        return window.app.serializeLayerAsPreset(layer);
    }""", ids[0])
    assert preset['customPortPaths'] == ports, preset


# ── restore paths (localStorage / File > Open / Recent Files) ─────────────


def test_a_restored_peer_reference_that_is_no_longer_reachable_is_dropped(page):
    """localStorage client props are keyed by layer id, and File > Open trusts
    the file. Either can hand back an entry naming a layer that is no longer a
    peer - here the group is dissolved after the paths were written. The load
    pass drops it so the canvas cannot draw a port reaching into a screen that
    is not part of this wall, even before the server's prune answers."""
    ids = reset_project(page, 3)
    a, b = ids[0], ids[1]
    if not page.evaluate("typeof window.app.canPathReachLayer === 'function'"):
        pytest.skip('canPathReachLayer (app-power.js) not present in this build')

    group(page, [a, b])
    set_paths(page, a,
              {'1': [{'row': 0, 'col': 0}, {'row': 0, 'col': 1, 'layerId': b}],
               '2': [{'row': 1, 'col': 1, 'layerId': b}]})

    # Still a legal reference while they are one wall.
    page.evaluate("""(id) => window.app.applyMissingLayerDefaults(
        window.app.project.layers.find(l => l.id === id))""", a)
    assert layer_ids_in(paths_of(page, a)) == [b, b], paths_of(page, a)

    select(page, [a, b])
    page.evaluate("window.app.ungroupSelectedLayers()")
    page.wait_for_timeout(900)

    page.evaluate("""(id) => window.app.applyMissingLayerDefaults(
        window.app.project.layers.find(l => l.id === id))""", a)
    after = paths_of(page, a)
    assert after['ports'] == {'1': [{'row': 0, 'col': 0}]}, after
    assert layer_ids_in(after) == [], after
