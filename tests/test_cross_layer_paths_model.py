"""Screen groups (v0.11.0) - the CLIENT model behind cross-member manual paths.

test_cross_layer_paths.py covers the server: what survives a restore and what
``_prune_cross_layer_paths`` repairs. This file covers the other half, in a real
browser, because every one of these decisions is made in JS before the server
ever sees the file:

* RESOLUTION. ``{row, col}`` means the owning layer; ``{row, col, layerId}``
  means a peer. A pointer at a layer that was deleted, or at one that is not a
  reachable peer, must read as nothing rather than as some other screen's
  cabinet - the renderer would otherwise draw a cable onto an unrelated wall.
* WRITING. ``layerId`` is written ONLY when it differs from the owner, so a
  path that never leaves its own screen keeps the exact shape every project
  written before this feature has. That is the primary regression guard here.
* OWNERSHIP. Conflict detection and dedupe both key on (layerId, row, col).
  Keyed on ``${row},${col}`` alone - which is what they did before - R0C0 of
  one member and R0C0 of the next read as the same cabinet, so the second one
  silently refuses to be added and a genuine double-booking goes unnoticed.
* GEOMETRY. Arrow-key handoff steps in WORLD coordinates. row/col are per-layer
  grid indices and a member built from a different cabinet size has a
  completely different index space, so "row + 1" is meaningless the instant it
  crosses the boundary. Asserted against members with DIFFERENT cabinet sizes
  for exactly that reason - equal sizes would pass with the naive maths too.
* ACCOUNTING. A port drawn across two members is ONE port. Three near-identical
  ports-required implementations existed; a group that reports two mains for a
  wall with one cable in it is the failure this pins.

Run locally:
    python -m pytest tests/test_cross_layer_paths_model.py -v --browser chromium
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


# ── helpers ───────────────────────────────────────────────────────────────

# Two members side by side with DIFFERENT cabinet sizes, which is the whole
# reason a wall ever needs to be two layers:
#
#   A: 2x2 of 128px cabinets at x 0..256
#   B: 3x3 of  96px cabinets at x 256..544
#
# A's R0C1 spans y 0..128, so its vertical midpoint (64) sits unambiguously
# inside B's first row (0..96) rather than on a shared cabinet edge - the
# handoff assertion is about which member answers, not about how a tie breaks.
LAYOUT = [
    {'name': 'PathA', 'columns': 2, 'rows': 2, 'cw': 128, 'ch': 128, 'x': 0, 'y': 0},
    {'name': 'PathB', 'columns': 3, 'rows': 3, 'cw': 96, 'ch': 96, 'x': 256, 'y': 0},
]

RESET_JS = """async (specs) => {
    const app = window.app;
    // The live server is shared with every other browser test file, so the
    // project holds whatever they left behind. Clear it outright and build
    // exactly these layers through the real add endpoint.
    let project = await (await fetch('/api/project')).json();
    project.layers = [];
    project.groups = [];
    await fetch('/api/project', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(project),
    });
    for (const s of specs) {
        await fetch('/api/layer/add', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                name: s.name, columns: s.columns, rows: s.rows,
                cabinet_width: s.cw, cabinet_height: s.ch,
                offset_x: s.x, offset_y: s.y,
            }),
        });
    }
    app.project = await (await fetch('/api/project')).json();
    app.dedupeProjectLayers('cross_layer_path_test_reset');
    const screens = app.project.layers.filter(
        l => (l.type || 'screen') === 'screen').slice(0, specs.length);
    screens.forEach(l => {
        l.processorType = 'brompton'; l.bitDepth = 10; l.frameRate = 60;
        // Both wiring views in custom mode, with empty paths: every test below
        // draws its own, so nothing carries over between them.
        l.flowPattern = 'custom'; l.customPortPaths = {}; l.customPortIndex = 1;
        l.powerFlowPattern = 'custom'; l.powerCustomPaths = {}; l.powerCustomIndex = 1;
        // Show Look sits exactly on the processor position, so the render
        // offset is zero and world coords equal panel coords. Keeps the
        // handoff assertions about the boundary rather than about offsets.
        l.showOffsetX = l.offset_x; l.showOffsetY = l.offset_y;
        // No Show Look canvas override: both members live on one canvas, which
        // is what makes them reachable from each other at all.
        l.show_canvas_id = null;
    });
    await fetch('/api/project', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(app.project),
    });
    app.project = await (await fetch('/api/project')).json();
    app.currentLayer = app.project.layers.find(l => l.id === screens[0].id);
    app.selectedLayerIds = new Set([screens[0].id]);
    if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
    app.resetHistory('Test Reset');
    window.canvasRenderer.viewMode = 'data-flow';
    return screens.map(l => l.id);
}"""


def reset_project(page, layout=None):
    """Deterministic starting point. Returns the ids of exactly the layers
    this module created - the shared server may hold others."""
    specs = layout if layout is not None else LAYOUT
    ids = page.evaluate(RESET_JS, specs)
    page.wait_for_timeout(700)
    assert len(ids) == len(specs), ids
    return ids


GROUP_JS = """async (ids) => {
    // Built directly rather than through groupSelectedLayers() so no mismatch
    // dialog and no extra history entry can affect what is being asserted.
    const app = window.app;
    app.project.groups = [{id: 'g1', name: 'Test Wall', layer_ids: ids}];
    ids.forEach(id => {
        app.project.layers.find(l => l.id === id).group_id = 'g1';
    });
    await fetch('/api/project', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(app.project),
    });
    // Re-read rather than trust the local mutation: a project_updated
    // broadcast still in flight from the reset's own PUT lands on window.app
    // asynchronously and would otherwise replace the group with the
    // group-less snapshot it was carrying.
    app.project = await (await fetch('/api/project')).json();
    return (app.project.groups || []).map(g => (g.layer_ids || []).length);
}"""


def make_group(page, ids):
    """Group every id, and do not return until window.app is actually holding
    the group. Racing on to the assertions produces failures that look like a
    reachability bug and are not one."""
    for _ in range(10):
        sizes = page.evaluate(GROUP_JS, ids)
        if sizes == [len(ids)]:
            return
        page.wait_for_timeout(300)
    raise AssertionError(f'group never settled on the client: {sizes!r}')


def grouped(page, layout=None):
    """Reset, group every member, and select the first. Returns the ids.

    Polls until the scope is actually what it should be. Every PUT makes the
    server broadcast the whole project back over the socket, and app-core
    replaces window.app.project wholesale when it arrives - so a late echo of
    an EARLIER put can drop the group again a beat after it was written. That
    surfaces as a peer reading unreachable, which looks exactly like a bug in
    the code under test and is not one."""
    ids = reset_project(page, layout)
    scope = None
    for _ in range(12):
        make_group(page, ids)
        page.wait_for_timeout(350)
        scope = page.evaluate("""(ids) => {
            const app = window.app;
            app.currentLayer = app.project.layers.find(l => l.id === ids[0]);
            app.selectedLayerIds = new Set(ids);
            return app.getPathScopeLayers(app.currentLayer).map(l => l.id);
        }""", ids)
        if scope == ids:
            return ids
    raise AssertionError(f'path scope never settled: {scope!r} (wanted {ids!r})')


def paths_of(page, layer_id, key='customPortPaths'):
    """The raw stored paths, exactly as they would be written to the file."""
    return page.evaluate("""([id, key]) => {
        const l = window.app.project.layers.find(x => x.id === id);
        return (l && l[key]) || {};
    }""", [layer_id, key])


def draw(page, owner_id, panel_layer_id, row, col, key='ArrowNone'):
    """Append one cabinet to the active port of `owner_id`'s path.

    `panel_layer_id` is the member the cabinet belongs to, which is the whole
    point: the port stays on the owner either way."""
    return page.evaluate("""([ownerId, panelLayerId, row, col]) => {
        const app = window.app;
        const owner = app.project.layers.find(l => l.id === ownerId);
        const src = app.project.layers.find(l => l.id === panelLayerId);
        app.currentLayer = owner;
        app.addPanelToCustomPath(app.getPanelByRowCol(src, row, col), src);
    }""", [owner_id, panel_layer_id, row, col])


def last_toast(page):
    return page.evaluate("""() => {
        const host = document.getElementById('app-toast-host');
        if (!host || !host.lastElementChild) return null;
        return host.lastElementChild.textContent;
    }""")


def clear_toasts(page):
    page.evaluate("""() => {
        const host = document.getElementById('app-toast-host');
        if (host) host.innerHTML = '';
    }""")


# ── entry resolution ──────────────────────────────────────────────────────


def test_plain_entry_resolves_to_the_owner(page):
    """The shape every project written before v0.11.0 has. It must resolve
    against the owning layer and never consult the group at all."""
    ids = grouped(page)
    res = page.evaluate("""(ids) => {
        const app = window.app;
        const a = app.project.layers.find(l => l.id === ids[0]);
        const r = app.resolvePathEntry(a, {row: 1, col: 1});
        return {
            layerId: r && r.layer.id,
            row: r && r.panel.row, col: r && r.panel.col,
            entryLayer: app.resolvePathEntryLayer(a, {row: 1, col: 1}).id,
            crosses: app.pathCrossesMembers(a, [{row: 0, col: 0}, {row: 1, col: 1}]),
        };
    }""", ids)
    assert res['layerId'] == ids[0], res
    assert (res['row'], res['col']) == (1, 1), res
    assert res['entryLayer'] == ids[0], res
    assert res['crosses'] is False, res


def test_cross_layer_entry_resolves_to_the_peer(page):
    """A step naming a peer resolves to THAT member's cabinet, at that
    member's own (row, col) - not the owner's."""
    ids = grouped(page)
    res = page.evaluate("""(ids) => {
        const app = window.app;
        const a = app.project.layers.find(l => l.id === ids[0]);
        const entry = {row: 2, col: 2, layerId: ids[1]};
        const r = app.resolvePathEntry(a, entry);
        return {
            layerId: r && r.layer.id,
            width: r && r.panel.width,
            crosses: app.pathCrossesMembers(a, [{row: 0, col: 0}, entry]),
            reach: app.canPathReachLayer(a, app.project.layers.find(
                l => l.id === ids[1])),
        };
    }""", ids)
    assert res['layerId'] == ids[1], res
    # Resolved through the PEER's grid: R2C2 does not even exist in A (2x2),
    # and the cabinet handed back is the peer's size, not the owner's.
    assert res['width'] == 96, res
    assert res['crosses'] is True, res
    assert res['reach'] is True, res


def test_dangling_entry_resolves_to_nothing(page):
    """A pointer at a layer that no longer exists is dead, not drawable."""
    ids = grouped(page)
    res = page.evaluate("""(ids) => {
        const app = window.app;
        const a = app.project.layers.find(l => l.id === ids[0]);
        const dead = {row: 0, col: 0, layerId: 999999};
        return {
            layer: app.resolvePathEntryLayer(a, dead),
            entry: app.resolvePathEntry(a, dead),
            resolved: app.getResolvedPathPanels(
                a, [{row: 0, col: 0}, dead]).length,
        };
    }""", ids)
    assert res['layer'] is None, res
    assert res['entry'] is None, res
    # The live step still draws; only the dead one drops out.
    assert res['resolved'] == 1, res


def test_entry_outside_the_group_resolves_to_nothing(page):
    """A layer that exists but is not a reachable peer is NOT a legal target.
    Two ungrouped screens are two screens, not a wall - resolving anyway would
    render a cable across a boundary the user never drew."""
    ids = reset_project(page)          # deliberately NOT grouped
    res = page.evaluate("""(ids) => {
        const app = window.app;
        const a = app.project.layers.find(l => l.id === ids[0]);
        const b = app.project.layers.find(l => l.id === ids[1]);
        return {
            scope: app.getPathScopeLayers(a).map(l => l.id),
            reach: app.canPathReachLayer(a, b),
            entry: app.resolvePathEntry(a, {row: 0, col: 0, layerId: ids[1]}),
        };
    }""", ids)
    assert res['scope'] == [ids[0]], res
    assert res['reach'] is False, res
    assert res['entry'] is None, res


def test_make_path_entry_omits_layer_id_for_the_owner(page):
    """The stored shape for an own-layer cabinet is byte-for-byte what it has
    always been. A layerId written here would change every existing file."""
    ids = grouped(page)
    res = page.evaluate("""(ids) => {
        const app = window.app;
        const a = app.project.layers.find(l => l.id === ids[0]);
        const b = app.project.layers.find(l => l.id === ids[1]);
        return {
            own: app.makePathEntry(a, a, app.getPanelByRowCol(a, 0, 1)),
            peer: app.makePathEntry(a, b, app.getPanelByRowCol(b, 1, 2)),
        };
    }""", ids)
    assert res['own'] == {'row': 0, 'col': 1}, res
    assert 'layerId' not in res['own'], res
    assert res['peer'] == {'row': 1, 'col': 2, 'layerId': ids[1]}, res


# ── writing ───────────────────────────────────────────────────────────────


def test_ungrouped_path_is_stored_exactly_as_before(page):
    """The primary regression guard: with no group in play, drawing a path
    produces plain {row, col} steps and nothing else."""
    ids = reset_project(page)
    draw(page, ids[0], ids[0], 0, 0)
    draw(page, ids[0], ids[0], 0, 1)
    page.wait_for_timeout(500)
    stored = paths_of(page, ids[0])
    assert stored == {'1': [{'row': 0, 'col': 0}, {'row': 0, 'col': 1}]}, stored


def test_peer_cabinet_is_stored_with_its_layer_id_on_the_owner(page):
    """The port never moves. Clicking a peer's cabinet writes onto the OWNER's
    path; only the step learns which member it landed on."""
    ids = grouped(page)
    draw(page, ids[0], ids[0], 0, 1)
    draw(page, ids[0], ids[1], 0, 0)
    page.wait_for_timeout(600)
    assert paths_of(page, ids[0]) == {'1': [
        {'row': 0, 'col': 1},
        {'row': 0, 'col': 0, 'layerId': ids[1]},
    ]}, paths_of(page, ids[0])
    # The peer itself gained nothing - it does not own this port.
    assert paths_of(page, ids[1]) == {}, paths_of(page, ids[1])


def test_the_owning_layer_is_persisted_even_when_it_is_not_selected(page):
    """updateLayers only PUTs what it is handed. Clicking a peer's cabinet
    writes onto the OWNER, and the owner is not guaranteed to be in the
    selection - so it has to be sent explicitly or the whole edit is lost on
    the next reload with no error anywhere."""
    ids = grouped(page)
    page.evaluate("""(ids) => {
        const app = window.app;
        // currentLayer owns the port; ONLY the peer is selected.
        app.currentLayer = app.project.layers.find(l => l.id === ids[0]);
        app.selectedLayerIds = new Set([ids[1]]);
        const b = app.project.layers.find(l => l.id === ids[1]);
        app.addPanelToCustomPath(app.getPanelByRowCol(b, 1, 1), b);
    }""", ids)
    page.wait_for_timeout(900)

    # Poll: the PUT is fired and not awaited, so reading the server too soon
    # says "lost" for a write that is merely still in flight.
    stored = None
    for _ in range(10):
        stored = page.evaluate("""async (ids) => {
            const p = await (await fetch('/api/project')).json();
            const a = p.layers.find(l => l.id === ids[0]);
            return (a && a.customPortPaths) || {};
        }""", ids)
        if stored.get('1'):
            break
        page.wait_for_timeout(300)
    assert stored == {'1': [{'row': 1, 'col': 1, 'layerId': ids[1]}]}, stored


def test_dedupe_is_per_member_not_per_row_col(page):
    """R0C0 of one member and R0C0 of the next are two different cabinets. A
    bare `${row},${col}` compare refuses the second one; the same cabinet
    twice must still be refused."""
    ids = grouped(page)
    draw(page, ids[0], ids[0], 0, 0)
    draw(page, ids[0], ids[1], 0, 0)     # same row/col, different member
    draw(page, ids[0], ids[1], 0, 0)     # genuine duplicate
    page.wait_for_timeout(700)
    assert paths_of(page, ids[0]) == {'1': [
        {'row': 0, 'col': 0},
        {'row': 0, 'col': 0, 'layerId': ids[1]},
    ]}, paths_of(page, ids[0])


# ── conflict detection ────────────────────────────────────────────────────


def test_cabinet_claimed_by_a_peers_port_reads_as_taken(page):
    """Port 1 of member A and port 1 of member B are two different physical
    outputs, so a cabinet the peer's port already claimed really is taken -
    and the toast has to name the SCREEN, because R1C1 alone is ambiguous the
    moment two grids are in play."""
    ids = grouped(page)
    # B owns port 1, and it reaches across onto A's R0C0.
    page.evaluate("""(ids) => {
        const app = window.app;
        const b = app.project.layers.find(l => l.id === ids[1]);
        app.currentLayer = b;
        app.addPanelToCustomPath(app.getPanelByRowCol(b, 0, 0), b);
        app.addPanelToCustomPath(app.getPanelByRowCol(
            app.project.layers.find(l => l.id === ids[0]), 0, 0),
            app.project.layers.find(l => l.id === ids[0]));
    }""", ids)
    page.wait_for_timeout(600)
    assert paths_of(page, ids[1]).get('1'), paths_of(page, ids[1])

    clear_toasts(page)
    draw(page, ids[0], ids[0], 0, 0)     # A drawing its own R0C0 - taken
    page.wait_for_timeout(500)

    # Nothing appended. (The empty port key is pre-existing behaviour: the
    # active port's array is created before the conflict check runs, and an
    # empty path is filtered out of every count.)
    assert paths_of(page, ids[0]).get('1') == [], paths_of(page, ids[0])
    toast = last_toast(page)
    assert toast, 'no toast raised for a cross-member conflict'
    assert 'port 1' in toast, toast
    assert 'PathB' in toast, (
        'the toast does not name the screen the conflicting port lives on: %r'
        % (toast,))


def test_conflict_within_one_screen_still_names_only_the_port(page):
    """Regression guard on the message: with no peer involved the wording is
    exactly what it was, so the group feature is invisible to a lone screen."""
    ids = reset_project(page)
    draw(page, ids[0], ids[0], 0, 0)
    page.wait_for_timeout(400)
    page.evaluate("""(ids) => {
        window.app.project.layers.find(l => l.id === ids[0]).customPortIndex = 2;
    }""", ids)
    clear_toasts(page)
    draw(page, ids[0], ids[0], 0, 0)
    page.wait_for_timeout(400)

    toast = last_toast(page)
    assert toast == ('Panel R1C1 is already wired to port 1. '
                     'Clear it from port 1 first.'), toast


# ── arrow-key handoff ─────────────────────────────────────────────────────


def arrow(page, code='ArrowRight'):
    return page.evaluate(
        "(code) => window.app.handleCustomArrowKey({code})", code)


def test_arrow_key_hands_off_into_a_peer_with_a_different_cabinet_size(page):
    """At the grid edge the wall does not stop, it continues on the next
    member - so the key steps in WORLD coordinates. A's 128px grid ends at
    col 1; the peer's 96px grid has a completely different index space, and
    "col + 1" there would land on nothing or on the wrong cabinet."""
    ids = grouped(page)
    draw(page, ids[0], ids[0], 0, 1)     # A's right-hand column
    page.wait_for_timeout(400)

    assert arrow(page, 'ArrowRight') is True
    page.wait_for_timeout(500)

    stored = paths_of(page, ids[0])
    assert stored == {'1': [
        {'row': 0, 'col': 1},
        {'row': 0, 'col': 0, 'layerId': ids[1]},
    ]}, stored


def test_arrow_key_inside_one_grid_is_unchanged(page):
    """Everything short of the boundary still steps by grid index, which is
    what makes the peer handoff a pure addition."""
    ids = grouped(page)
    draw(page, ids[0], ids[0], 0, 0)
    page.wait_for_timeout(400)
    assert arrow(page, 'ArrowRight') is True
    assert arrow(page, 'ArrowDown') is True
    page.wait_for_timeout(600)
    assert paths_of(page, ids[0]) == {'1': [
        {'row': 0, 'col': 0}, {'row': 0, 'col': 1}, {'row': 1, 'col': 1},
    ]}, paths_of(page, ids[0])


def test_arrow_key_at_the_edge_of_a_lone_screen_is_swallowed(page):
    """No peer to hand off to: the key is still consumed and nothing is
    appended, exactly as before v0.11.0."""
    ids = reset_project(page)            # ungrouped
    draw(page, ids[0], ids[0], 0, 1)
    page.wait_for_timeout(400)
    assert arrow(page, 'ArrowRight') is True, (
        'the key must stay swallowed, not fall through to a pan')
    page.wait_for_timeout(400)
    assert paths_of(page, ids[0]) == {'1': [{'row': 0, 'col': 1}]}, \
        paths_of(page, ids[0])


def test_arrow_key_with_nothing_drawn_falls_through(page):
    """An empty path is not ours to consume - the key belongs to whatever
    handles it next."""
    grouped(page)
    assert arrow(page, 'ArrowRight') is False


# ── accounting ────────────────────────────────────────────────────────────


def test_port_spanning_two_members_counts_once(page):
    """One cable is one port. The member being fed contributes none of its
    own, so the wall reports 1 Main and not 2.

    FIXTURE CORRECTED (v0.11.0 audit, finding 1). This used to put ONE of B's
    nine cabinets on A's port and still expect B to report 0 - which is the
    finding, not the feature: a single cabinet picked up by a neighbour zeroed
    the whole member, so B's other eight cabinets were planned for with no port
    at all. "The member being fed" means fed, so the cable now runs across
    every one of B's cabinets, and the zero is real."""
    ids = grouped(page)
    draw(page, ids[0], ids[0], 0, 0)
    for row in range(3):
        for col in range(3):
            draw(page, ids[0], ids[1], row, col)
    page.wait_for_timeout(600)

    res = page.evaluate("""(ids) => {
        const app = window.app;
        const a = app.project.layers.find(l => l.id === ids[0]);
        const b = app.project.layers.find(l => l.id === ids[1]);
        const totals = app.getGroupTotals('g1');
        return {
            owner: app.getLayerPortsRequired(a),
            fed: app.getLayerPortsRequired(b),
            fedCabinets: (b.panels || []).length,
            onPath: (a.customPortPaths[1] || []).filter(e => e.layerId === b.id).length,
            groupPorts: totals.portsPrimary,
        };
    }""", ids)
    assert res['onPath'] == res['fedCabinets'], (
        'the fixture did not put every one of the peer\'s cabinets on the '
        'cable: %r' % (res,))
    assert res['owner'] == 1, res
    assert res['fed'] == 0, (
        'the member fed by the peer is counting a port of its own: %r' % (res,))
    assert res['groupPorts'] == 1, res


def test_a_peer_only_partly_fed_still_counts_its_own_ports(page):
    """The other side of the rule above, and the v0.11.0 audit's most
    dangerous finding: ONE of B's nine cabinets on A's cable used to zero B
    entirely, so eight cabinets were planned for with no port. Partial
    coverage counts what the uncovered cabinets still need."""
    ids = grouped(page)
    draw(page, ids[0], ids[0], 0, 0)
    draw(page, ids[0], ids[1], 0, 0)
    page.wait_for_timeout(600)

    res = page.evaluate("""(ids) => {
        const app = window.app;
        const a = app.project.layers.find(l => l.id === ids[0]);
        const b = app.project.layers.find(l => l.id === ids[1]);
        return {
            owner: app.getLayerPortsRequired(a),
            fed: app.getLayerPortsRequired(b),
            uncovered: (b.panels || []).length - 1,
            groupPorts: app.getGroupTotals('g1').portsPrimary,
        };
    }""", ids)
    assert res['uncovered'] == 8, res
    assert res['owner'] == 1, res
    assert res['fed'] >= 1, (
        '%d of the peer\'s cabinets have no port drawn on them and the peer '
        'reports %r ports' % (res['uncovered'], res['fed']))
    assert res['groupPorts'] == res['owner'] + res['fed'], res


def test_a_member_with_its_own_port_still_counts_it(page):
    """The zero above is specifically "fed by a peer", not "is a group
    member". Two cables are two ports."""
    ids = grouped(page)
    draw(page, ids[0], ids[0], 0, 0)
    page.evaluate("""(ids) => {
        const app = window.app;
        const b = app.project.layers.find(l => l.id === ids[1]);
        app.currentLayer = b;
        app.addPanelToCustomPath(app.getPanelByRowCol(b, 0, 0), b);
    }""", ids)
    page.wait_for_timeout(600)

    res = page.evaluate("""() => {
        const app = window.app;
        return {group: app.getGroupTotals('g1').portsPrimary};
    }""")
    assert res['group'] == 2, res


# ── canvas scope ──────────────────────────────────────────────────────────


def test_path_scope_excludes_a_member_on_another_canvas(page):
    """A group split across canvases is two workspaces. A cable drawn onto the
    far member would be drawn at a position that means nothing, so the peer is
    simply not reachable - the same rule the canvas applies when it decides
    which members it draws as one screen."""
    ids = grouped(page)
    res = page.evaluate("""(ids) => {
        const app = window.app;
        const a = app.project.layers.find(l => l.id === ids[0]);
        const b = app.project.layers.find(l => l.id === ids[1]);
        const before = app.getPathScopeLayers(a).map(l => l.id);
        // Unique id, because the shared server keeps whatever canvases another
        // test file (or an earlier run of this one) left in the project.
        const far = 'cx_' + Date.now();
        app.project.canvases.push({
            id: far, name: 'Far Canvas', color: '#F5A623',
            workspace_x: 4000, workspace_y: 0,
            raster_width: 1920, raster_height: 1080,
            show_raster_width: 1920, show_raster_height: 1080,
            visible: true,
        });
        // Both, because Data and Power read the Show Look override first: a
        // member moved on only one of the two is still reachable on the other.
        b.canvas_id = far;
        b.show_canvas_id = far;
        const after = app.getPathScopeLayers(a).map(l => l.id);
        return {
            before, after,
            reach: app.canPathReachLayer(a, b),
            entry: app.resolvePathEntry(a, {row: 0, col: 0, layerId: ids[1]}),
            groupIntact: (app.project.groups[0].layer_ids || []).length,
        };
    }""", ids)
    assert res['before'] == ids, res
    assert res['after'] == [ids[0]], res
    assert res['reach'] is False, res
    assert res['entry'] is None, res
    # Still one group - the members did not stop being grouped, they stopped
    # being REACHABLE. The distinction matters: moving the member back must
    # bring its steps straight back with it.
    assert res['groupIntact'] == 2, res
