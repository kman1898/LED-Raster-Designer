"""Circuit sharing via power splitters (2fer/3fer/4fer Y-cables).

Real rigs gang multiple SHORT adjacent power runs onto ONE circuit through a
splitter: a wall cabled top-down in 5-tall columns at a 15-tile circuit
capacity feeds three adjacent columns from one feed labelled S1-1 on every
tile, through a 3fer. The feature under test:

  - layer.powerSplitters = {enabled, maxWays, manual: {merge, split}} -
    per-screen AUTO packing toggle (organized modes) + MANUAL merge/split.
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
