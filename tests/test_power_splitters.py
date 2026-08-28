"""Circuit sharing via power splitters (2fer/3fer/4fer Y-cables).

Real rigs gang multiple SHORT adjacent power runs onto ONE circuit through a
splitter: a wall cabled top-down in 5-tall columns at a 15-tile circuit
capacity feeds three adjacent columns from one feed labelled S1-1 on every
tile, through a 3fer. The feature under test:

  - layer.powerSplitters = {enabled, maxWays, manual: {merge, split}} -
    per-screen AUTO packing toggle (organized modes) + MANUAL merge/split.
    In the app the packing knobs (enable checkbox, splitter-size row) are
    static controls in the LEFT sidebar's Power Settings "Multis &
    Splitters" block, synced by refreshSplitterPanel; the manual lever is
    the right-click Share / Un-share on the circuit itself - a drawn run
    or its occupied dock chip (app-dock.js _prepareShareMenus).
  - The engine (calculatePowerAssignments) forms one RUN per row/column unit
    and gangs CONSECUTIVE runs while the branch count stays within maxWays
    and the summed load fits the circuit - never skipping a run to pair two
    non-neighbours. Return shape grows additively: {circuits, runs, runIds}
    with circuits[i] still the concatenation, so every index-aligned
    consumer is untouched.
  - Custom-drawn screens are NEVER auto-packed (the numbering is user
    intent); manual merge collapses drawn circuits into one shared circuit.
  - Default off: output byte-identical to the pre-splitter engine and power
    sheets (pins captured on this exact tree at 23c3175, BEFORE the engine
    edits - scratchpad capture_baseline.py).

Browser tests use the synthetic-project style of test_doc_geometry.py.

NOT COVERED HERE. Upstream this file also carried three tests that render
the splitter through features this branch does not have. They were removed
rather than skipped, so nothing sits here rotting:
  - test_power_sheet_draws_one_feed_with_branch_stubs_and_3fer_tag and
    test_power_sheet_with_splitters_absent_is_byte_identical_to_capture
    need the SCHEMATIC sheet renderer (_schemUnitPowerChains /
    _schemSheetRanges / _schemPowerSheetSvg).
  - test_gear_list_counts_the_splitters needs the REPORT feature
    (buildProductionReportData) for its per-circuit "<N>fer" gear tally.
Restore them from the source branch when those features land.

Run locally (ONE pytest at a time - the browser-test servers use fixed
ports):
    python -m pytest tests/test_power_splitters.py -v --browser chromium
"""

import hashlib
import json
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(e2e_server):
    """Same isolation as test_doc_geometry.py: snapshot the live e2e
    server's project when this module starts and put it back when it ends."""
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


# Same builder shape as test_doc_geometry.py. withProject swaps the whole
# project and restores it in a finally.
HELPERS_JS = """
window.__sp = {
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
    // the motivating rig: N adjacent 5-tall columns, 100W tiles on a
    // 100V x 15A circuit = a 15-tile capacity, cabled top-down (tl-v),
    // organized columns
    column_wall(cols, extra) {
        return this.screen(Object.assign({
            id: 1, name: 'Wall', columns: cols, rows: 5,
            panelWatts: 100, powerVoltage: 100, powerAmperage: 15,
            powerFlowPattern: 'tl-v', powerOrganized: true,
        }, extra || {}));
    },
    splitters(maxWays, manual) {
        return { enabled: true, maxWays: maxWays || 3,
                 manual: manual || { merge: [], split: [] } };
    },
    withProject(project, fn) {
        const saved = window.app.project;
        window.app.project = Object.assign(
            { layers: [], groups: [], canvases: [], rack: [] }, project);
        try { return fn(); } finally { window.app.project = saved; }
    },
};
"""


# ── 1. The motivating case ────────────────────────────────────────────────

def test_three_adjacent_column_runs_share_one_circuit_via_3fer(page):
    """Three adjacent 5-tile column runs at a 15-tile capacity, organized
    tl-v, splitters enabled (maxWays 3): ONE circuit of three 5-tile
    branches, every tile keyed to circuit 1 (= labelled S1-1), and a soca
    plan of ONE leg carrying all 15 tiles."""
    out = page.evaluate("""() => {
        const sp = window.__sp;
        const S = sp.column_wall(3, { powerSplitters: sp.splitters(3) });
        return sp.withProject({ layers: [S] }, () => {
            const app = window.app;
            const a = app.calculatePowerAssignments(S);
            const circuits = app.screenCircuits(S);
            const plan = app.getSocaPlan(S);
            // the canvas prep maps every tile to its circuit number - the
            // number the on-wall label prints through getPowerCircuitLabel
            const cr = window.canvasRenderer;
            cr.preparePowerLayerRenderData(S);
            const mapped = [...S._powerPanelCircuitMap.values()];
            return {
                circuitSizes: (a.circuits || []).map(c => c.length),
                runs: a.runs, runIds: a.runIds,
                count: app.screenCircuitCount(S),
                branches: circuits.map(c => (c.branches || []).map(b => b.length)),
                label: app.getPowerCircuitLabel(S, 1),
                mappedCount: mapped.length,
                mappedNums: [...new Set(mapped)],
                legs: plan.flatMap(p => p.legs.map(l =>
                    ({ label: l.label, tiles: l.tiles }))),
            };
        });
    }""")
    assert out['circuitSizes'] == [15], 'ONE circuit carrying all 15 tiles'
    assert out['runs'] == [[5, 5, 5]], 'three 5-tile branches'
    assert out['runIds'] == [[1, 2, 3]], 'runs 1..3 ganged in traversal order'
    assert out['count'] == 1
    assert out['branches'] == [[5, 5, 5]], 'screenCircuits carries the branches'
    assert out['label'] == 'S1-1'
    assert out['mappedCount'] == 15 and out['mappedNums'] == [1], \
        'every tile keys to circuit 1 - one label, S1-1, on all 15'
    assert out['legs'] == [{'label': 'S1-1', 'tiles': 15}], \
        'the soca plan sees ONE leg of 15 tiles'


# ── 2. maxWays cap ────────────────────────────────────────────────────────

def test_max_ways_caps_the_gang_even_when_watts_would_fit(page):
    """Four 5-tile columns at a 20-tile capacity fit ONE circuit by watts,
    but maxWays 3 caps the splitter: [3 runs] + [1 run]."""
    out = page.evaluate("""() => {
        const sp = window.__sp;
        const S = sp.column_wall(4, {
            powerAmperage: 20,  // 100V x 20A / 100W = 20-tile capacity
            powerSplitters: sp.splitters(3),
        });
        return sp.withProject({ layers: [S] }, () =>
            window.app.calculatePowerAssignments(S).runs);
    }""")
    assert out == [[5, 5, 5], [5]], 'a 3fer is the largest allowed gang'


def test_raising_max_ways_lets_the_fourth_run_join(page):
    """Same wall, maxWays raised to 4: one circuit through a 4fer."""
    out = page.evaluate("""() => {
        const sp = window.__sp;
        const S = sp.column_wall(4, {
            powerAmperage: 20,
            powerSplitters: sp.splitters(4),
        });
        return sp.withProject({ layers: [S] }, () =>
            window.app.calculatePowerAssignments(S).runs);
    }""")
    assert out == [[5, 5, 5, 5]]


# ── 3. capacity cap ───────────────────────────────────────────────────────

def test_capacity_allows_only_2fers_when_three_runs_exceed_the_circuit(page):
    """Four 5-tile columns at a 10-tile capacity: three runs would be 15
    tiles - over capacity - so the packer stops at 2fers: [2, 2]."""
    out = page.evaluate("""() => {
        const sp = window.__sp;
        const S = sp.column_wall(4, {
            powerAmperage: 10,  // 100V x 10A / 100W = 10-tile capacity
            powerSplitters: sp.splitters(3),
        });
        return sp.withProject({ layers: [S] }, () =>
            window.app.calculatePowerAssignments(S).runs);
    }""")
    assert out == [[5, 5], [5, 5]], 'capacity caps the gang below maxWays'


# ── 4. adjacency ──────────────────────────────────────────────────────────

def test_non_adjacent_runs_never_gang_across_a_big_middle_run(page):
    """Run loads 5 / 12 / 5 tiles at a 15-tile capacity: 1+2 and 2+3 are
    both over, and 1+3 would fit - but they are not adjacent, so the packer
    must NOT skip run 2 to pair them. Three separate circuits."""
    out = page.evaluate("""() => {
        const sp = window.__sp;
        const S = sp.screen({ id: 1, name: 'Adj', columns: 3, rows: 12,
            panelWatts: 100, powerVoltage: 100, powerAmperage: 15,
            powerFlowPattern: 'tl-v', powerOrganized: true,
            powerSplitters: sp.splitters(3) });
        // shape the wall: columns 1 and 3 keep 5 tiles, column 2 keeps 12
        S.panels.forEach(p => {
            if ((p.col === 0 || p.col === 2) && p.row >= 5) p.hidden = true;
        });
        return sp.withProject({ layers: [S] }, () => {
            const a = window.app.calculatePowerAssignments(S);
            return {
                runs: a.runs, runIds: a.runIds,
                cols: (a.circuits || []).map(c => [...new Set(c.map(p => p.col))]),
            };
        });
    }""")
    assert out['runs'] == [[5], [12], [5]], 'three circuits, nothing ganged'
    assert out['runIds'] == [[1], [2], [3]]
    for cols in out['cols']:
        assert not (0 in cols and 2 in cols), \
            'columns 1 and 3 must never share a circuit across column 2'


# ── 5. manual merge of drawn custom circuits ──────────────────────────────

def test_manual_merge_of_two_drawn_custom_paths_shares_one_circuit(page):
    """Two drawn custom paths merged by hand: ONE circuit numbered by the
    first member, two branches, getLayerCircuitsRequired = 1, one soca leg,
    and the sticker path covers BOTH member paths (every tile labelled)."""
    out = page.evaluate("""() => {
        const sp = window.__sp;
        const S = sp.screen({ id: 1, name: 'Cust', columns: 2, rows: 2,
            powerFlowPattern: 'custom', powerCustomIndex: 3,
            powerCustomPaths: {
                1: [{row:0,col:0},{row:1,col:0}],
                2: [{row:0,col:1},{row:1,col:1}],
            },
            powerSplitters: { enabled: false, maxWays: 3,
                              manual: { merge: [[1, 2]], split: [] } } });
        return sp.withProject({ layers: [S] }, () => {
            const app = window.app;
            const circuits = app.screenCircuits(S);
            return {
                n: circuits.length,
                nums: circuits.map(c => c.num),
                branches: circuits.map(c => (c.branches || []).map(b => b.length)),
                required: app.getLayerCircuitsRequired(S, 0),
                legs: app.getSocaPlan(S).flatMap(p => p.legs.map(l =>
                    ({ label: l.label, tiles: l.tiles }))),
                mergedPath: app._splitterMergedPathFor(S, 1).length,
            };
        });
    }""")
    assert out['n'] == 1 and out['nums'] == [1]
    assert out['branches'] == [[2, 2]], 'two drawn paths become two branches'
    assert out['required'] == 1, 'the count authority sees ONE merged circuit'
    assert out['legs'] == [{'label': 'S1-1', 'tiles': 4}]
    assert out['mergedPath'] == 4, 'the sticker path covers both member paths'


def test_manual_merge_ids_that_no_longer_resolve_are_dropped(page):
    """A merge naming a circuit that is no longer drawn is silently dropped
    on read; a group left with one member dissolves entirely."""
    out = page.evaluate("""() => {
        const sp = window.__sp;
        const S = sp.screen({ id: 1, name: 'Stale', columns: 2, rows: 2,
            powerFlowPattern: 'custom', powerCustomIndex: 3,
            powerCustomPaths: {
                1: [{row:0,col:0},{row:1,col:0}],
            },
            powerSplitters: { enabled: false, maxWays: 3,
                              manual: { merge: [[1, 9]], split: [] } } });
        return sp.withProject({ layers: [S] }, () => {
            const circuits = window.app.screenCircuits(S);
            return {
                groups: window.app.appliedSplitterGroups(S, [1]).merge,
                n: circuits.length,
                branches: circuits.map(c => (c.branches || []).length),
            };
        });
    }""")
    assert out['groups'] == [], 'the group dissolved - id 9 does not resolve'
    assert out['n'] == 1 and out['branches'] == [0], 'no phantom branches'


# ── 6. manual split pin ───────────────────────────────────────────────────

def test_manual_split_pin_defeats_auto_pack(page):
    """The motivating wall packs [5,5,5] - but run 2 pinned out by hand
    stays its own circuit, and (adjacency) runs 1 and 3 cannot gang across
    it: three circuits."""
    out = page.evaluate("""() => {
        const sp = window.__sp;
        const packed = sp.withProject(
            { layers: [sp.column_wall(3, { powerSplitters: sp.splitters(3) })] },
            () => window.app.calculatePowerAssignments(
                window.app.project.layers[0]).runs);
        const S = sp.column_wall(3, { powerSplitters: sp.splitters(3,
            { merge: [], split: [2] }) });
        const pinned = sp.withProject({ layers: [S] }, () => ({
            runs: window.app.calculatePowerAssignments(S).runs,
            count: window.app.screenCircuitCount(S),
        }));
        return { packed, pinned };
    }""")
    assert out['packed'] == [[5, 5, 5]], 'without the pin the wall packs'
    assert out['pinned']['runs'] == [[5], [5], [5]], 'the pin defeats packing'
    assert out['pinned']['count'] == 3


# ── 7. schematic power sheet ──────────────────────────────────────────────
# ── 8. Flask persistence ──────────────────────────────────────────────────

SPLITTERS = {'enabled': True, 'maxWays': 4,
             'manual': {'merge': [[1, 2]], 'split': [3]}}


def test_put_round_trips_power_splitters(client_with_layer):
    client = client_with_layer
    layer = client.get('/api/project').get_json()['layers'][0]
    layer['powerSplitters'] = SPLITTERS
    resp = client.put(f"/api/layer/{layer['id']}", json=layer)
    assert resp.status_code == 200
    assert resp.get_json()['powerSplitters'] == SPLITTERS, \
        'the PUT echo must carry the field, not drop it on the floor'
    served = client.get('/api/project').get_json()['layers'][0]
    assert served['powerSplitters'] == SPLITTERS


def test_post_add_carries_power_splitters(client):
    """Duplicate/paste posts the whole layer through /api/layer/add."""
    resp = client.post('/api/layer/add', json={
        'name': 'Copy', 'columns': 3, 'rows': 5,
        'cabinet_width': 128, 'cabinet_height': 128,
        'powerSplitters': SPLITTERS,
    })
    assert resp.status_code == 200
    assert resp.get_json()['powerSplitters'] == SPLITTERS
    served = client.get('/api/project').get_json()['layers'][0]
    assert served['powerSplitters'] == SPLITTERS


# ── 9. default-off identity (captured BEFORE the engine edits) ────────────

def test_engine_output_with_field_absent_equals_pre_change_capture(page):
    """calculatePowerAssignments with powerSplitters absent must equal the
    output this exact tree produced at 23c3175 - organized (both
    directions), maximize, and plain greedy. The pins are the raw
    JSON.stringify bytes captured by scratchpad capture_baseline.py BEFORE
    the engine was touched."""
    out = page.evaluate("""() => {
        const sp = window.__sp;
        const battery = {
            org_v: sp.screen({ id: 1, name: 'OrgV', columns: 6, rows: 5,
                panelWatts: 100, powerVoltage: 100, powerAmperage: 15,
                powerFlowPattern: 'tl-v', powerOrganized: true }),
            org_h: sp.screen({ id: 2, name: 'OrgH', columns: 4, rows: 3,
                panelWatts: 500, powerFlowPattern: 'tl-h', powerOrganized: true }),
            max_h: sp.screen({ id: 3, name: 'MaxH', columns: 4, rows: 3,
                panelWatts: 500, powerMaximize: true, powerOrganized: true }),
            greedy: sp.screen({ id: 4, name: 'Greedy', columns: 4, rows: 3,
                panelWatts: 500 }),
            org_br: sp.screen({ id: 5, name: 'OrgBR', columns: 6, rows: 5,
                panelWatts: 100, powerVoltage: 100, powerAmperage: 15,
                powerFlowPattern: 'br-v', powerOrganized: true }),
        };
        const out = {};
        for (const key of Object.keys(battery)) {
            const s = battery[key];
            out[key] = sp.withProject({ layers: [s] }, () =>
                JSON.stringify(window.app.calculatePowerAssignments(s)));
        }
        return out;
    }""")
    for key, pin in PIN_ASSIGNMENTS.items():
        assert out[key] == pin, f'{key}: default-off engine output moved'
        # belt and braces: structural equality for a readable diff
        assert json.loads(out[key]) == json.loads(pin)


def test_disabled_field_present_equals_field_absent(page):
    """An explicit {enabled: false} (the stamped default) behaves exactly
    like the absent field - byte-for-byte."""
    out = page.evaluate("""() => {
        const sp = window.__sp;
        const bare = sp.column_wall(6);
        const stamped = sp.column_wall(6, { powerSplitters: {
            enabled: false, maxWays: 3, manual: { merge: [], split: [] } } });
        return {
            bare: sp.withProject({ layers: [bare] }, () =>
                JSON.stringify(window.app.calculatePowerAssignments(bare))),
            stamped: sp.withProject({ layers: [stamped] }, () =>
                JSON.stringify(window.app.calculatePowerAssignments(stamped))),
        };
    }""")
    assert out['bare'] == out['stamped']
    assert out['bare'] == PIN_ASSIGNMENTS['org_v']


# ── 10. soca / distro ─────────────────────────────────────────────────────

def test_merged_circuits_produce_fewer_soca_legs_and_offset_clamps(page):
    """Six drawn custom circuits merged into pairs: the soca plan drops from
    6 legs to 3, and the phase-offset clamp follows the MERGED leg count -
    a stored offset of 4 degrades to 3 (6 - 3 legs), so no circuit slides
    off the 6-way fan."""
    out = page.evaluate("""() => {
        const sp = window.__sp;
        const paths = {};
        for (let c = 0; c < 6; c++) {
            paths[c + 1] = [{row:0,col:c},{row:1,col:c}];
        }
        const mk = (splitters) => {
            const s = sp.screen({ id: 1, name: 'Six', columns: 6, rows: 2,
                powerFlowPattern: 'custom', powerCustomIndex: 7,
                powerCustomPaths: paths,
                powerSocaPhaseOffset: { 1: 4 } });
            if (splitters) s.powerSplitters = splitters;
            return s;
        };
        const plain = mk(null);
        const merged = mk({ enabled: false, maxWays: 3,
            manual: { merge: [[1, 2], [3, 4], [5, 6]], split: [] } });
        const legsOf = (s) => sp.withProject({ layers: [s] }, () =>
            window.app.getSocaPlan(s).flatMap(p => p.legs.map(l =>
                ({ circuit: l.circuit, tiles: l.tiles }))));
        const clampOf = (s, legs) => sp.withProject({ layers: [s] }, () => ({
            offset: window.app.socaPhaseOffset(s, 1, legs),
            positions: window.app.socaCircuitPositions(s, 1, legs),
        }));
        return {
            plainLegs: legsOf(plain),
            mergedLegs: legsOf(merged),
            plainClamp: clampOf(plain, 6),
            mergedClamp: clampOf(merged, 3),
        };
    }""")
    assert len(out['plainLegs']) == 6
    assert len(out['mergedLegs']) == 3, 'merged circuits = fewer soca legs'
    assert [l['tiles'] for l in out['mergedLegs']] == [4, 4, 4]
    assert [l['circuit'] for l in out['mergedLegs']] == [1, 3, 5], \
        'each merged circuit keeps its first member number'
    # a full multi cannot slide at all; the 3-leg merged multi clamps 4 -> 3
    assert out['plainClamp']['offset'] == 0
    assert out['mergedClamp']['offset'] == 3
    assert out['mergedClamp']['positions'] == [4, 5, 6], \
        'the clamped offset keeps every circuit on the 6-way fan'
PIN_SVG_LEN = 15674
PIN_SVG_SHA256 = '0330e43f4b11555e83e52bc6d1f3aefadcf5607794fe3d5d24831a0953aeeb9d'
PIN_ASSIGNMENTS = {
    'org_v': '{"circuits":[[{"row":0,"col":0,"x":0,"y":0,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":1,"col":0,"x":0,"y":128,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":2,"col":0,"x":0,"y":256,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":3,"col":0,"x":0,"y":384,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":4,"col":0,"x":0,"y":512,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":4,"col":1,"x":128,"y":512,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":3,"col":1,"x":128,"y":384,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":2,"col":1,"x":128,"y":256,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":1,"col":1,"x":128,"y":128,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":0,"col":1,"x":128,"y":0,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":0,"col":2,"x":256,"y":0,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":1,"col":2,"x":256,"y":128,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":2,"col":2,"x":256,"y":256,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":3,"col":2,"x":256,"y":384,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":4,"col":2,"x":256,"y":512,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"}],[{"row":0,"col":3,"x":384,"y":0,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":1,"col":3,"x":384,"y":128,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":2,"col":3,"x":384,"y":256,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":3,"col":3,"x":384,"y":384,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":4,"col":3,"x":384,"y":512,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":4,"col":4,"x":512,"y":512,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":3,"col":4,"x":512,"y":384,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":2,"col":4,"x":512,"y":256,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":1,"col":4,"x":512,"y":128,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":0,"col":4,"x":512,"y":0,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":0,"col":5,"x":640,"y":0,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":1,"col":5,"x":640,"y":128,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":2,"col":5,"x":640,"y":256,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":3,"col":5,"x":640,"y":384,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":4,"col":5,"x":640,"y":512,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"}]],"error":null}',
    'org_h': '{"circuits":[[{"row":0,"col":0,"x":0,"y":0,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":0,"col":1,"x":128,"y":0,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":0,"col":2,"x":256,"y":0,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":0,"col":3,"x":384,"y":0,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":1,"col":3,"x":384,"y":128,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":1,"col":2,"x":256,"y":128,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":1,"col":1,"x":128,"y":128,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":1,"col":0,"x":0,"y":128,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"}],[{"row":2,"col":0,"x":0,"y":256,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":2,"col":1,"x":128,"y":256,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":2,"col":2,"x":256,"y":256,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":2,"col":3,"x":384,"y":256,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"}]],"error":null}',
    'max_h': '{"circuits":[[{"row":0,"col":0,"x":0,"y":0,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":0,"col":1,"x":128,"y":0,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":0,"col":2,"x":256,"y":0,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":0,"col":3,"x":384,"y":0,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":1,"col":3,"x":384,"y":128,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":1,"col":2,"x":256,"y":128,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":1,"col":1,"x":128,"y":128,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":1,"col":0,"x":0,"y":128,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"}],[{"row":2,"col":0,"x":0,"y":256,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":2,"col":1,"x":128,"y":256,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":2,"col":2,"x":256,"y":256,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":2,"col":3,"x":384,"y":256,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"}]],"error":null}',
    'greedy': '{"circuits":[[{"row":0,"col":0,"x":0,"y":0,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":0,"col":1,"x":128,"y":0,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":0,"col":2,"x":256,"y":0,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":0,"col":3,"x":384,"y":0,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":1,"col":3,"x":384,"y":128,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":1,"col":2,"x":256,"y":128,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":1,"col":1,"x":128,"y":128,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":1,"col":0,"x":0,"y":128,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"}],[{"row":2,"col":0,"x":0,"y":256,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":2,"col":1,"x":128,"y":256,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":2,"col":2,"x":256,"y":256,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":2,"col":3,"x":384,"y":256,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"}]],"error":null}',
    'org_br': '{"circuits":[[{"row":4,"col":5,"x":640,"y":512,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":3,"col":5,"x":640,"y":384,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":2,"col":5,"x":640,"y":256,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":1,"col":5,"x":640,"y":128,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":0,"col":5,"x":640,"y":0,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":0,"col":4,"x":512,"y":0,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":1,"col":4,"x":512,"y":128,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":2,"col":4,"x":512,"y":256,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":3,"col":4,"x":512,"y":384,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":4,"col":4,"x":512,"y":512,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":4,"col":3,"x":384,"y":512,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":3,"col":3,"x":384,"y":384,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":2,"col":3,"x":384,"y":256,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":1,"col":3,"x":384,"y":128,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":0,"col":3,"x":384,"y":0,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"}],[{"row":4,"col":2,"x":256,"y":512,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":3,"col":2,"x":256,"y":384,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":2,"col":2,"x":256,"y":256,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":1,"col":2,"x":256,"y":128,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":0,"col":2,"x":256,"y":0,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":0,"col":1,"x":128,"y":0,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":1,"col":1,"x":128,"y":128,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":2,"col":1,"x":128,"y":256,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":3,"col":1,"x":128,"y":384,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":4,"col":1,"x":128,"y":512,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":4,"col":0,"x":0,"y":512,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":3,"col":0,"x":0,"y":384,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":2,"col":0,"x":0,"y":256,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":1,"col":0,"x":0,"y":128,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"},{"row":0,"col":0,"x":0,"y":0,"width":128,"height":128,"hidden":false,"blank":false,"halfTile":"none"}]],"error":null}',
}


# ── 11. the packing knobs and the right-click share menu ──────────────────
#
# The Power sidebar's Splitters panel is gone; its levers consolidated into
# two homes:
#
#   - The PACKING knobs - the enable checkbox and the "Max splitter" size
#     row - are STATIC controls in the left sidebar's Power Settings
#     "Multis & Splitters" block, synced in place by refreshSplitterPanel
#     (no innerHTML wipe). Splitters default OFF, and the size select
#     drives only the packer - so #power-splitters-maxways-row SHOWS only
#     while sharing is on. The controls stay in the DOM; what the old
#     panel wore as absence, the static row wears as display:none, and
#     VISIBILITY is the contract these tests pin.
#   - The per-circuit Merge/Split rows became the right-click Share /
#     Un-share on the circuit itself (app-dock.js _prepareShareMenus):
#     armed in power view on a drawn circuit run or an occupied circuit
#     chip, and only when packing is on OR the screen routes custom - the
#     old rows' gate, unchanged. A hand-merge on a custom-drawn screen
#     never consults maxWays, so the two conditions stay separate: the
#     menu can be armed while the size row is hidden.
#
# MIXED MULTI-SELECTION. The enable checkbox writes through _socaPanelTargets
# to every selected screen, but it can only SHOW one state, and it shows the
# screen the panel is displaying. The size row follows that same flag, so the
# row never contradicts the box beside it; one tick settles both, because the
# write lands on every selected screen.

PANEL_INSTALL_JS = """(specs) => {
    const sp = window.__sp;
    const app = window.app;
    const layers = specs.map((s, i) => sp.column_wall(3, Object.assign(
        { id: 9900 + i, name: 'Panel' + (i + 1) }, s)));
    // Save the REAL tree once - a test may install twice, and the second
    // install must not capture the first synthetic project as "saved".
    if (!window.__panelSaved) {
        window.__panelSaved = { project: app.project, layer: app.currentLayer,
                                sel: app.selectedLayerIds,
                                update: app.updateLayers };
    }
    app.project = { layers: layers, groups: [], canvases: [], rack: [] };
    app.currentLayer = layers[0];
    app.selectedLayerIds = new Set(layers.map(l => l.id));
    // a synthetic tree makes no server trip - but record the history
    // action each write claims, so the tests can pin it
    window.__panelActions = [];
    app.updateLayers = (list, save, action) => {
        window.__panelActions.push(action);
    };
    // The knobs live in the Power Settings tab-panel, whose visibility is
    // computed from the selection - restate it for the synthetic screens.
    if (app.updateLayerPanelVisibility) app.updateLayerPanelVisibility(false, false);
    app.refreshSplitterPanel();
    return layers.map(l => l.id);
}"""

PANEL_RESTORE_JS = """() => {
    const app = window.app;
    const s = window.__panelSaved;
    if (!s) return;
    app.project = s.project;
    app.currentLayer = s.layer;
    app.selectedLayerIds = s.sel;
    app.updateLayers = s.update;
    delete window.__panelSaved;
    delete window.__panelActions;
    app.refreshSplitterPanel();
    if (app.renderHardwareDock) app.renderHardwareDock();
}"""

PANEL_READ_JS = """() => {
    const vis = (el) => !!(el && el.offsetParent !== null);
    const en = document.getElementById('power-splitters-enabled');
    const row = document.getElementById('power-splitters-maxways-row');
    const mw = document.getElementById('power-splitters-maxways');
    const mwc = document.getElementById('power-splitters-maxways-custom');
    const labels = row ? [...row.querySelectorAll('label')]
        .map(l => l.textContent.trim()) : [];
    return {
        enableBox: vis(en),
        checked: !!(en && en.checked),
        sizeRow: vis(row),
        sizeSelect: vis(mw),
        sizeLabel: vis(row) && labels.includes('Max splitter'),
        customInput: vis(mwc),
        mwValue: mw ? mw.value : null,
        mwcValue: mwc ? mwc.value : null,
        actions: window.__panelActions || [],
        enabledFlags: window.app.project.layers.map(
            l => window.app.getPowerSplitters(l).enabled),
    };
}"""

# A distro pushed straight into the synthetic project's own bucket -
# app.addDistro would saveState and POST the synthetic tree to the shared
# server - and the current screen's multi assigned to it, so its circuits
# occupy tail chips in the hardware dock. Returns the occupied-chip count.
DOCK_INSTALL_JS = """() => {
    const app = window.app;
    app.getDistros().push({ id: 'd1', name: 'PD', ratingA: 400,
                            voltage: 208, phase: 3 });
    app.currentLayer.powerSocaDistro = { 1: 'd1' };
    app._circuitTailCache = null;
    app.renderHardwareDock();
    return document.querySelectorAll('#hardware-dock [data-lrd-tile]').length;
}"""

# Arm the share menu at circuit `num`'s occupied chip face - the real
# gesture's coordinates, through the real hit test (_dockCircuitAt reads
# document.elementFromPoint). `view`, when given, probes with the renderer
# claiming that view, to pin the power-view gate.
SHARE_PROBE_JS = """([num, view]) => {
    const app = window.app, r = window.canvasRenderer;
    const l = app.currentLayer;
    const fld = document.querySelector(
        '[data-lrd-field="power-label-' + l.id + '-' + num + '"]');
    const tile = fld && fld.closest('[data-lrd-tile]');
    const face = tile && tile.querySelector('[data-hwdock-payload]');
    if (!face) return { found: false };
    face.scrollIntoView({ block: 'nearest' });
    const rect = face.getBoundingClientRect();
    const saved = r.viewMode;
    if (view) r.viewMode = view;
    try {
        const m = app._prepareShareMenus(rect.left + rect.width / 2,
                                         rect.top + rect.height / 2);
        return { found: true,
                 share: m.share ? m.share.label : null,
                 unshare: m.unshare ? m.unshare.label : null };
    } finally { r.viewMode = saved; }
}"""

# The same probe on a FREE tail chip - occupied tiles carry data-lrd-tile,
# a free tail's does not - where neither menu item may arm.
FREE_PROBE_JS = """() => {
    const app = window.app;
    const free = [...document.querySelectorAll(
        '#hardware-dock [data-hwdock-payload]')].find(el => {
        let p = null;
        try { p = JSON.parse(el.dataset.hwdockPayload); } catch (e) {}
        return p && p.type === 'tail'
            && !(el.parentElement && el.parentElement.dataset.lrdTile);
    });
    if (!free) return { found: false };
    free.scrollIntoView({ block: 'nearest' });
    const rect = free.getBoundingClientRect();
    const m = app._prepareShareMenus(rect.left + rect.width / 2,
                                     rect.top + rect.height / 2);
    return { found: true, share: !!m.share, unshare: !!m.unshare };
}"""

# Arm at circuit `num`'s chip and .run() the chosen entry - the whole
# manual lever, exactly as the context menu dispatches it.
SHARE_RUN_JS = """([num, which]) => {
    const app = window.app;
    const l = app.currentLayer;
    const fld = document.querySelector(
        '[data-lrd-field="power-label-' + l.id + '-' + num + '"]');
    const tile = fld && fld.closest('[data-lrd-tile]');
    const face = tile && tile.querySelector('[data-hwdock-payload]');
    if (!face) return false;
    face.scrollIntoView({ block: 'nearest' });
    const rect = face.getBoundingClientRect();
    const m = app._prepareShareMenus(rect.left + rect.width / 2,
                                     rect.top + rect.height / 2);
    const entry = which === 'unshare' ? m.unshare : m.share;
    if (!entry) return false;
    entry.run();
    return true;
}"""

# Three drawn custom paths of two tiles each - the gate's OTHER arm, and
# the shape whose hand-merge the ops tests below lean on.
CUSTOM3 = {'powerFlowPattern': 'custom', 'powerCustomIndex': 4,
           'powerCustomPaths': {str(c + 1): [{'row': 0, 'col': c},
                                             {'row': 1, 'col': c}]
                                for c in range(3)}}


@pytest.fixture
def panel(page):
    """Install a synthetic project the real left-sidebar knobs and the
    hardware dock can render, and put the page's own project back
    afterwards. Unlike __sp.withProject this outlives the call, so the
    deferred _rebuildAfterGesture restate lands on it."""
    page.locator('[data-mode="power"]').click()   # the knobs' own view
    page.wait_for_timeout(400)

    def install(*specs):
        page.evaluate(PANEL_INSTALL_JS, list(specs))
        return page.evaluate(PANEL_READ_JS)
    yield install
    page.evaluate(PANEL_RESTORE_JS)


def test_splitter_size_row_hides_until_sharing_is_switched_on(page, panel):
    """Splitters off - the default - and the Max splitter row shows
    nothing: label, select and all. (The controls are static in the left
    sidebar since the consolidation, so the old absence is worn as
    display:none.) Ticking the box shows it with no further gesture from
    the user, and the write claims the panel rows' old history action."""
    off = panel({})
    assert off['enableBox'] and not off['checked'], 'fixture: sharing starts off'
    assert not off['sizeRow'] and not off['sizeSelect'] and not off['sizeLabel'], (
        f"the splitter size row is on screen with the packer switched "
        f"off, driving nothing: {off}")

    page.locator('#power-splitters-enabled').click()
    page.wait_for_timeout(300)   # the knobs restate past the gesture
    on = page.evaluate(PANEL_READ_JS)
    assert on['checked'] and on['enabledFlags'] == [True], on
    assert on['actions'][-1] == 'Change Splitter Packing', on
    assert on['sizeRow'] and on['sizeSelect'] and on['sizeLabel'], (
        f"ticking the box did not show the size row: {on}")

    page.locator('#power-splitters-enabled').click()
    page.wait_for_timeout(300)
    back = page.evaluate(PANEL_READ_JS)
    assert not back['checked'] and not back['sizeRow'], (
        f"switching sharing off left the size row on screen: {back}")


def test_a_custom_splitter_size_hides_with_its_row(page, panel):
    """The number input for a non-stock size is part of the row, so it goes
    with it - a 5fer stored on a screen with sharing off shows nothing."""
    off = panel({'powerSplitters': {'enabled': False, 'maxWays': 5,
                                    'manual': {'merge': [], 'split': []}}})
    assert not off['sizeRow'] and not off['customInput'], (
        f"a stored custom size kept the row on screen: {off}")

    page.evaluate("""() => {
        const app = window.app;
        const l = app.currentLayer;
        l.powerSplitters = { ...app.getPowerSplitters(l), enabled: true };
        app.refreshSplitterPanel();
    }""")
    on = page.evaluate(PANEL_READ_JS)
    assert on['sizeSelect'] and on['customInput'], (
        f"the custom size input did not come back with the row: {on}")
    assert on['mwValue'] == 'custom' and on['mwcValue'] == '5', (
        f"the row came back but does not state the stored 5fer: {on}")


def test_share_menu_arms_by_the_old_rows_gate(page, panel):
    """The right-click Share/Un-share - the retired Merge/Split rows' lever
    - arms on an occupied circuit chip only in power view and only when
    packing is on OR the screen routes custom. A custom screen with sharing
    off arms Share (and shows NO size row - a hand-merge never consults
    maxWays, so the two conditions are not the same condition); Un-share
    stays off an unmerged circuit; a free chip, and any point probed
    outside power view, arm nothing; and so does a plain screen with
    sharing off, occupied chips and all."""
    out = panel(CUSTOM3)
    assert not out['sizeRow'], (
        f"custom routing alone must not surface the packing size row: {out}")
    chips = page.evaluate(DOCK_INSTALL_JS)
    assert chips == 3, f"fixture: three occupied circuit chips, got {chips}"

    armed = page.evaluate(SHARE_PROBE_JS, [1, None])
    assert armed['found'], armed
    assert armed['share'] == 'Share with next run via 2fer', armed
    assert armed['unshare'] is None, (
        f"Un-share offered on an unmerged circuit: {armed}")

    off_view = page.evaluate(SHARE_PROBE_JS, [1, 'data-flow'])
    assert off_view == {'found': True, 'share': None, 'unshare': None}, (
        f"the share menu armed outside power view: {off_view}")

    free = page.evaluate(FREE_PROBE_JS)
    assert free['found'], 'fixture: the multi has free tails'
    assert not free['share'] and not free['unshare'], (
        f"the share menu armed on a FREE chip: {free}")

    # packing off and nothing custom: the gate holds on occupied chips too
    plain = panel({})
    assert plain['enabledFlags'] == [False], 'fixture: sharing off'
    assert page.evaluate(DOCK_INSTALL_JS) >= 1, 'fixture: an occupied chip'
    gated = page.evaluate(SHARE_PROBE_JS, [1, None])
    assert gated['found'], gated
    assert gated['share'] is None and gated['unshare'] is None, (
        f"sharing off and nothing custom, yet the menu armed: {gated}")


def test_share_and_unshare_drive_the_merge_ops_from_the_chip(page, panel):
    """.run() on the armed entries is the manual lever itself. Share gangs
    the circuit with the next run (mergeSplitterCircuits, under the rows'
    old 'Edit Splitter Groups' action); the merged chip re-arms as a 3fer
    Share plus Un-share while the LAST circuit still offers neither; and
    Un-share dissolves the group (splitSplitterCircuits) without pinning
    the drawn circuits."""
    panel(CUSTOM3)
    assert page.evaluate(DOCK_INSTALL_JS) == 3

    assert page.evaluate(SHARE_RUN_JS, [1, 'share']) is True
    state = page.evaluate("""() => {
        const app = window.app, l = app.currentLayer;
        const circuits = app.screenCircuits(l);
        return {
            merge: app.getPowerSplitters(l).manual.merge,
            nums: circuits.map(c => c.num),
            branches: circuits.map(c => (c.branches || []).map(b => b.length)),
            actions: window.__panelActions,
        };
    }""")
    assert state['merge'] == [[1, 2]], state
    assert state['nums'] == [1, 3], (
        f"the merged circuit must keep its first member number: {state}")
    assert state['branches'][0] == [2, 2], state
    assert state['actions'][-1] == 'Edit Splitter Groups', state

    page.wait_for_timeout(100)   # the deferred restate re-renders the dock
    page.evaluate("() => window.app.renderHardwareDock()")
    merged = page.evaluate(SHARE_PROBE_JS, [1, None])
    assert merged['share'] == 'Share with next run via 3fer', merged
    assert merged['unshare'] == 'Un-share', merged
    last = page.evaluate(SHARE_PROBE_JS, [3, None])
    assert last['found'] and last['unshare'] is None, (
        f"Un-share belongs only on a merged circuit: {last}")

    assert page.evaluate(SHARE_RUN_JS, [1, 'unshare']) is True
    after = page.evaluate("""() => {
        const app = window.app, l = app.currentLayer;
        const sp = app.getPowerSplitters(l);
        return { merge: sp.manual.merge, split: sp.manual.split,
                 nums: app.screenCircuits(l).map(c => c.num) };
    }""")
    assert after['merge'] == [], after
    assert after['split'] == [], (
        f"drawn custom circuits are never pinned by un-share: {after}")
    assert after['nums'] == [1, 2, 3], after


def test_mixed_selection_shows_the_panel_screen_and_the_tick_settles_both(page, panel):
    """Two screens selected, the shown one off and the other on. The row
    follows the checkbox, which shows the screen the knobs are displaying -
    so the block never states two things at once. The tick writes through to
    every selected screen, which makes the states agree."""
    mixed = panel({}, {'powerSplitters': {'enabled': True, 'maxWays': 3,
                                          'manual': {'merge': [], 'split': []}}})
    assert mixed['enabledFlags'] == [False, True], 'fixture: mixed states'
    assert not mixed['checked'] and not mixed['sizeRow'], (
        f"the row disagreed with the checkbox beside it: {mixed}")

    page.locator('#power-splitters-enabled').click()
    page.wait_for_timeout(300)
    after = page.evaluate(PANEL_READ_JS)
    assert after['enabledFlags'] == [True, True], (
        f"the tick did not reach every selected screen: {after}")
    assert after['checked'] and after['sizeRow'], after
