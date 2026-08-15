"""Port/circuit authority reconciliation - the fork's rack/power side now
answers through upstream's group-aware authorities.

On a GROUPED wall the two systems used to disagree: the sidebar and group
roll-up asked getLayerPortsRequired / getLayerCircuitsRequired
(app-screen-info.js - a member fully served by a peer's cross-member path
needs 0 ports/circuits of its own), while the patch bay, report and soca plan
asked screenPortCount (app-rack.js) / screenCircuits + screenCircuitCount
(app-power.js), which had no peer concept. Result: phantom ports allocated
for peer-served members, double-counted totals, and cross-member power
circuits computing watts from the WRONG member's grid (getPanelByRowCol on
the owner ignored a step's layerId, landing on the owner's cabinet at that
address - a different physical cabinet).

NOT COVERED HERE. The rack, the patch bay and the report do not exist on
this branch, so the tests that probed their entry points were removed rather
than skipped:
  - test_grouped_peer_served_member_needs_zero_ports_everywhere asserted
    that a peer-served member answers 0 through screenPortCount (rack),
    _allocPortCount (patch bay) and the report's processor.portsRequired,
    as well as getLayerPortsRequired. Only the last of those exists here.
  - test_duplicate_canvas_clears_clone_rack_allocation needed the canvas
    duplicate route's rack rule, which lives in routes_canvas.py and was
    not ported.
  - the ungrouped pins below lost their `ports` probe for the same reason
    (see the note on UNGROUPED_PINS_JS); the power pins are intact.
  - test_duplicate_layer_to_canvas_clears_clone_rack_allocation asserted
    that PUT /api/layer/<id>/canvas with mode=duplicate leaves the source's
    rackAllocation intact but stamps the clone's to None, so the copy does
    not become a second consumer of the original's physical ports.
  - test_move_layer_to_canvas_keeps_rack_allocation asserted the opposite
    half of the same rule: mode=move changes canvas_id but KEEPS
    rackAllocation, because the rack is project-global and a screen the
    user merely reorganised must not silently unpatch.
    Both went when the rackAllocation residue came out of routes_layers.py
    (whitelists + the clone-stamping line). Nothing in this tree writes the
    field, so the rules they pinned no longer exist to be tested; restore
    them alongside the rack if it is ever ported.

The browser tests use the synthetic-project style of
test_screen_group_totals.py: window.app.project is swapped for a hand-built
one inside a single page.evaluate and restored in a finally. The backend
tests use the Flask test client, like test_multi_canvas.py.

Run locally (ONE pytest at a time - the browser-test servers use fixed
ports):
    python -m pytest tests/test_authority_reconciliation.py -v --browser chromium
"""

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(e2e_server):
    """Keeps this module invisible to its neighbours. A Flask `client` test
    resets the module-global project (the conftest `client` fixture rebuilds
    it per test), and this file runs alphabetically BEFORE the browser-test
    files that share the live e2e server - they would inherit whatever
    project it left behind (test_browser_flows' alt-click test trips over
    it). Snapshot the server state when this module starts and put it back
    when it ends. Depends on e2e_server so the snapshot is taken AFTER the
    shared server has seeded its Screen1 project, not before.

    The backend tests this originally guarded went with the rackAllocation
    residue (see the module docstring), so today it is a no-op standing
    guard: the file is currently all browser tests. Kept because it is
    autouse and free, and the next Flask-client test added here would
    silently poison its neighbours without it."""
    import copy
    import app as app_module
    saved_project = copy.deepcopy(app_module.current_project)
    saved_next = app_module.next_layer_id
    yield
    app_module.current_project = saved_project
    app_module.next_layer_id = saved_next


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)  # socket connect + app init
    pg.evaluate(HELPERS_JS)
    yield pg
    context.close()


# Same builder shape as test_screen_group_totals.py, plus withProject.
HELPERS_JS = """
window.__ar = {
    screen(opts) {
        const o = Object.assign({
            id: 1, name: 'S', type: 'screen', visible: true,
            columns: 2, rows: 2,
            cabinet_width: 128, cabinet_height: 128,
            offset_x: 0, offset_y: 0,
            panel_weight: 20, weight_unit: 'kg',
            panelWatts: 200, powerVoltage: 208, powerAmperage: 20,
            processorType: 'brompton', bitDepth: 8, frameRate: 60,
            lowLatency: false,
            flowPattern: 'tl-h', portMappingMode: 'organized',
            powerFlowPattern: 'tl-h', powerOrganized: false, powerMaximize: false,
            group_id: null,
        }, opts || {});
        const panels = [];
        for (let r = 0; r < o.rows; r++) {
            for (let c = 0; c < o.columns; c++) {
                panels.push({
                    row: r, col: c,
                    x: o.offset_x + c * o.cabinet_width,
                    y: o.offset_y + r * o.cabinet_height,
                    width: o.cabinet_width, height: o.cabinet_height,
                    hidden: false, blank: false, halfTile: 'none',
                });
            }
        }
        o.panels = panels;
        return o;
    },
    withProject(layers, groups, fn) {
        const saved = window.app.project;
        window.app.project = { layers: layers, groups: groups, canvases: [], rack: [] };
        try { return fn(); } finally { window.app.project = saved; }
    },
};
"""


# ── Cross-member power: the peer's cabinets at the PEER's wattage ─────────

# Owner A (200 W/panel) and peer B (90 W/panel, offset to x 256..512),
# grouped. A's custom POWER circuit 1 is its own four cabinets; circuit 2 is
# all four of B's, via cross-member steps. B: custom power, nothing drawn.
GROUPED_POWER_WALL_JS = """() => {
    const ar = window.__ar;
    const A = ar.screen({
        id: 1, name: 'Owner', group_id: 'g1',
        powerFlowPattern: 'custom', powerCustomIndex: 1,
        powerCustomPaths: {
            1: [{row:0,col:0},{row:0,col:1},{row:1,col:0},{row:1,col:1}],
            2: [{row:0,col:0,layerId:2},{row:0,col:1,layerId:2},
                {row:1,col:0,layerId:2},{row:1,col:1,layerId:2}],
        },
    });
    const B = ar.screen({
        id: 2, name: 'Peer', group_id: 'g1', offset_x: 256, panelWatts: 90,
        powerFlowPattern: 'custom', powerCustomIndex: 1, powerCustomPaths: {},
    });
    const group = { id: 'g1', name: 'Wall', layer_ids: [1, 2] };
    return ar.withProject([A, B], [group], () => {
        const app = window.app;
        const planA = app.getSocaPlan(A);
        return {
            ownerPlan: planA.map(s => ({
                soca: s.soca, watts: s.watts,
                legs: s.legs.map(l => [l.leg, l.circuit, l.tiles, l.watts,
                                       l.x1, l.x2]),
            })),
            peerPlan: app.getSocaPlan(B),
            ownerCircuitCount: app.screenCircuitCount(A),
            peerCircuitCount: app.screenCircuitCount(B),
        };
    });
}"""


def test_cross_member_circuit_charges_peer_cabinets_at_peer_wattage(page):
    """Circuit 2 crosses onto the peer: 4 cabinets x 90 W = 360 W, spanning
    the PEER's x extent (256..512). This is the assertion that fails against
    getPanelByRowCol resolution, which lands every step on the OWNER's
    cabinet at that (row, col): 4 x 200 W = 800 W at x 0..256 - a different
    physical wall's load on the breaker label."""
    out = page.evaluate(GROUPED_POWER_WALL_JS)
    assert len(out['ownerPlan']) == 1
    soca = out['ownerPlan'][0]
    # leg 1: owner's own circuit, untouched: 4 x 200 W over x 0..256
    # leg 2: the cross-member circuit: 4 x 90 W over x 256..512
    assert soca['legs'] == [
        [1, 1, 4, 800, 0, 256],
        [2, 2, 4, 360, 256, 512],
    ]
    assert soca['watts'] == 800 + 360


def test_peer_served_member_has_empty_soca_plan(page):
    """The peer's power arrives on the owner's circuits (where its cabinets
    are counted, above). Its own plan must be EMPTY - the auto fallback used
    to fabricate a plan for cables that do not exist, double-counting the
    load in every distro roll-up - and its circuit count 0, agreeing with the
    group-aware authority. The owner counts its two drawn circuits."""
    out = page.evaluate(GROUPED_POWER_WALL_JS)
    assert out['peerPlan'] == []
    assert out['peerCircuitCount'] == 0
    assert out['ownerCircuitCount'] == 2


# ── Ungrouped screens: byte-identical to before the change ────────────────

# Expected values captured from the PRE-change implementations (commit
# c71722a) by running these exact layers through the old
# screenCircuits / screenCircuitCount / getSocaPlan in the live app, then
# hardcoded here. If reconciliation moves any of these, an ungrouped project
# changed behaviour.
#
# The upstream version of this fixture also probed screenPortCount and pinned
# a `ports` figure per case. screenPortCount is the RACK-side port authority
# and lives in the rack module, which this branch does not carry; the probe
# and its two assertions were dropped so the power pins below still run. The
# power-side authorities are pinned in full. Restore the `ports` probe and the
# p1/p2/p4 port assertions if and when the rack lands.
UNGROUPED_PINS_JS = """() => {
    const ar = window.__ar;
    const run = (layer) => ar.withProject([layer], [], () => ({
        circuits: window.app.screenCircuitCount(layer),
        circuitShape: window.app.screenCircuits(layer).map(c => [c.num, c.panels.length]),
    }));
    const out = {};
    // P1: plain auto flow / auto power, 4x3 of 128px @ 200 W on 208 V / 20 A
    out.p1 = run(ar.screen({ id: 11, columns: 4, rows: 3 }));
    // P2: custom flow, ports 1..3 drawn (cursor parked on port 2 - a cursor,
    // never a count)
    out.p2 = run(ar.screen({ id: 12, columns: 4, rows: 3,
        flowPattern: 'custom', customPortIndex: 2,
        customPortPaths: {
            1: [{row:0,col:0},{row:0,col:1}],
            2: [{row:1,col:0},{row:1,col:1}],
            3: [{row:2,col:0}],
        } }));
    // P3: custom power, circuits 1..2 drawn - plan shape and soca legs
    const p3 = ar.screen({ id: 13, columns: 4, rows: 3,
        powerFlowPattern: 'custom', powerCustomIndex: 1,
        powerCustomPaths: {
            1: [{row:0,col:0},{row:0,col:1},{row:0,col:2}],
            2: [{row:1,col:0},{row:1,col:1}],
        } });
    out.p3 = run(p3);
    out.p3.soca = ar.withProject([p3], [], () =>
        window.app.getSocaPlan(p3).map(s => ({
            soca: s.soca, watts: s.watts,
            legs: s.legs.map(l => [l.leg, l.circuit, l.tiles, l.watts,
                                   Number(l.amps.toFixed(6)), l.x1, l.x2]),
        })));
    // P4: custom flow AND custom power with NOTHING drawn, ungrouped - the
    // auto-fallback branch (no peers, so the only-honest-zero rule is inert)
    out.p4 = run(ar.screen({ id: 14, columns: 4, rows: 3,
        flowPattern: 'custom', customPortPaths: {}, customPortIndex: 1,
        powerFlowPattern: 'custom', powerCustomPaths: {}, powerCustomIndex: 1 }));
    return out;
}"""


def test_ungrouped_outputs_pinned_to_pre_change_values(page):
    out = page.evaluate(UNGROUPED_PINS_JS)
    assert out['p1'] == {'circuits': 1, 'circuitShape': [[1, 12]]}
    assert out['p3']['circuits'] == 2
    assert out['p3']['circuitShape'] == [[1, 3], [2, 2]]
    assert out['p3']['soca'] == [{
        'soca': 1, 'watts': 1000,
        'legs': [[1, 1, 3, 600, 2.884615, 0, 384],
                 [2, 2, 2, 400, 1.923077, 0, 256]],
    }]
    assert out['p4'] == {'circuits': 1, 'circuitShape': [[1, 12]]}
