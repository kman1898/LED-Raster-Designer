"""A wall that shrinks trims its drawn power circuits.

The data side came first (tests/test_shrink_trims_ports.py). Power had the
same fault: a circuit taken over by hand across columns 0-9 still listed
columns 6-9 after the wall was cut to 6 columns, and in custom power a
circuit drawn wholly on columns 6-9 stayed as a circuit with no cabinets,
still listed and still counted in circuits required. The owner's ruling,
2026-11-02, pinned here in a real browser:

* TRIM - when a wall shrinks, every drawn circuit (custom paths and the
  circuits taken over on an automatic screen) drops the cabinets that fell
  off the wall.
* LEAVE THE HOLE - a circuit left with no cabinets is removed and the other
  circuits KEEP their numbers. It no longer counts toward circuits required
  and is no longer listed.
* FEEDS - a removed circuit comes off its distro the way Unplug circuit
  takes it off, with its typed lengths; every other circuit keeps its
  distro, its multi number and its tail.
* 2FERS / 3FERS - a share keeps the legs that still have cabinets and
  dissolves only when one leg or none is left.
* LOAD - a show saved in that state is repaired the same way when opened.
* LOCKED - a locked screen is left as it is.

The walls are synthetic: cabinets of 200 x 200 drawing 150 W on 208 V x
20 A, so one circuit carries 27 cabinets and three 5-cabinet columns share
one through a 3fer.
"""

import json
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
    context = pw_browser.new_context(viewport={'width': 1400, 'height': 900})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}"
    )
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(f'{e.message} {e.stack}'))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.evaluate(HELPERS_JS)
    pg._ct_errors = errors
    yield pg
    context.close()


HELPERS_JS = r"""
window.__ct = {
    // One screen, `columns` x `rows` cabinets, with `fields` laid over the
    // power setup and `distros` on the show. With `peer` (fields of its
    // own) a second screen of the same size sits to its right and the two
    // are grouped as one wall; a step naming layerId 'PEER' names it.
    // With `extra` ({ name, columns, fields }) a screen of its own sits
    // below, not grouped.
    async reset(spec) {
        const app = window.app, r = window.canvasRenderer;
        app._overrideEditing = null;
        delete app._halfLockHolders;
        app._circuitTrimHeld = null;
        await app._layerSavesSettled();
        let project = await (await fetch('/api/project')).json();
        project.layers = [];
        project.groups = [];
        project.distros = (spec.distros || []).map(d =>
            Object.assign({ ratingA: 400, voltage: 208, phase: 3 }, d));
        await fetch('/api/project', {
            method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(project),
        });
        await fetch('/api/layer/add', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                name: 'TrimWall', columns: spec.columns || 10, rows: spec.rows || 5,
                cabinet_width: 200, cabinet_height: 200, offset_x: 0, offset_y: 0,
            }),
        });
        if (spec.peer) {
            await fetch('/api/layer/add', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    name: 'TrimPeer', columns: spec.columns || 10, rows: spec.rows || 5,
                    cabinet_width: 200, cabinet_height: 200,
                    offset_x: (spec.columns || 10) * 200, offset_y: 0,
                }),
            });
        }
        if (spec.extra) {
            await fetch('/api/layer/add', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    name: spec.extra.name, columns: spec.extra.columns, rows: spec.rows || 5,
                    cabinet_width: 200, cabinet_height: 200, offset_x: 0, offset_y: 2000,
                }),
            });
        }
        project = await (await fetch('/api/project')).json();
        const layer = project.layers.find(l => l.name === 'TrimWall');
        const peer = project.layers.find(l => l.name === 'TrimPeer') || null;
        const extra = spec.extra
            ? project.layers.find(l => l.name === spec.extra.name) : null;
        const power = (fields) => Object.assign({
            powerFlowPattern: 'tl-v', lastPowerFlowPattern: 'tl-v',
            powerCustomPath: false, powerOrganized: true, powerMaximize: false,
            powerVoltage: 208, powerAmperage: 20, panelWatts: 150,
            powerCustomPaths: {}, powerCustomIndex: 1, powerCustomOverrides: [],
            powerSplitters: { enabled: false, maxWays: 3,
                              manual: { merge: [], split: [] } },
            powerLabelOverrides: {}, powerCircuitCables: {},
            sizeByDimensions: false, locked: false,
        }, fields || {});
        Object.assign(layer, power(spec.fields));
        if (extra) Object.assign(extra, power(spec.extra.fields));
        if (peer) {
            Object.assign(peer, power(spec.peer.fields), { group_id: 'gT' });
            layer.group_id = 'gT';
            project.groups = [{ id: 'gT', name: 'TRIM WALL', layer_ids: [layer.id, peer.id] }];
            Object.values(layer.powerCustomPaths || {}).forEach(path => path.forEach(e => {
                if (e.layerId === 'PEER') e.layerId = peer.id;
            }));
        }
        await fetch('/api/project', {
            method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(project),
        });
        app.project = await (await fetch('/api/project')).json();
        app.dedupeProjectLayers('trim_circuits_reset');
        const live = app.project.layers.find(l => l.id === layer.id);
        app.selectLayer(live);
        app.selectedLayerIds = new Set([live.id]);
        app._circuitTailCache = null;
        r.viewMode = 'power';
        r.zoom = 0.2; r.panX = 20; r.panY = 60;
        r.render();
        if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
        app.resetHistory('Trim Circuits Baseline');
        window.__notes = [];
        window.__errs = [];
        if (!app.__ctToastWrapped) {
            const real = app._toast.bind(app);
            app._toast = (m, err, ms) => {
                (err ? window.__errs : window.__notes).push(m);
                return real(m, err, ms);
            };
            app.__ctToastWrapped = true;
        }
        if (extra) return [live.id, extra.id];
        return peer ? [live.id, peer.id] : live.id;
    },

    layer(id) {
        return window.app.project.layers.find(l => l.id === id);
    },

    state(id) {
        const app = window.app, l = this.layer(id);
        app._circuitTailCache = null;
        const paths = {};
        Object.keys(l.powerCustomPaths || {}).forEach(k => {
            paths[k] = (l.powerCustomPaths[k] || []).map(e => [e.row, e.col]);
        });
        const circuits = app.screenCircuits(l).map(c => ({
            num: c.num, runIds: c.runIds || null, cabinets: c.panels.length,
            label: app.getPowerCircuitLabel(l, c.num),
        }));
        // circuit -> [multi number, tail, distro] off the plan the
        // paperwork reads
        const feeds = {};
        app.getSocaPlan(l).forEach(s => s.legs.forEach(g => {
            feeds[g.circuit] = [s.distroId ? s.number : null, g.leg, s.distroId || null];
        }));
        const m = app.getPowerSplitters(l).manual;
        return {
            columns: l.columns,
            paths,
            keys: Object.keys(l.powerCustomPaths || {}).map(Number).sort((a, b) => a - b),
            overrides: app.getOverrideNums(l, 'power'),
            circuits,
            required: app.getLayerCircuitsRequired(l, app.calculatePowerAssignments(l).circuits.length),
            count: app.screenCircuitCount(l),
            feeds,
            merge: (m.merge || []).map(g => g.map(Number).sort((a, b) => a - b))
                .sort((a, b) => a[0] - b[0]),
            labels: l.powerLabelOverrides || {},
            cables: l.powerCircuitCables || {},
            lengths: l.powerSocaLengths || {},
            historyAction: (app.history && app.history[app.historyIndex])
                ? app.history[app.historyIndex].action : null,
        };
    },
};
"""


def reset(page, **spec):
    lid = page.evaluate("(s) => window.__ct.reset(s)", spec)
    page.wait_for_timeout(300)
    return lid


def st(page, lid):
    return page.evaluate("(id) => window.__ct.state(id)", lid)


def notes(page):
    return page.evaluate("() => window.__notes")


def errs(page):
    return page.evaluate("() => window.__errs")


def shrink(page, lid, columns):
    """Cut a screen's columns through the funnel every layer commit takes
    (updateLayers), the way the group test cuts a peer."""
    page.evaluate("""([id, n]) => { const app = window.app, l = window.__ct.layer(id);
        l.columns = n; app.updateLayers([l]); app.saveState('Update Properties'); }""",
                  [lid, columns])
    page.wait_for_timeout(800)


def power_fields(page, lid):
    return page.evaluate("""(id) => { const l = window.__ct.layer(id), out = {};
        Object.keys(l).forEach(k => { if (k.startsWith('power')) out[k] = l[k]; });
        return JSON.parse(JSON.stringify(out)); }""", lid)


def server_layer(page, lid):
    return page.evaluate("""async (id) => (await (await fetch('/api/project')).json())
        .layers.find(l => l.id === id)""", lid)


def type_columns(page, n):
    """The Screen Info Columns field, set and committed with the change
    event a user's Tab or Enter fires."""
    page.evaluate("""(n) => {
        const el = document.getElementById('screen-columns');
        el.value = String(n);
        el.dispatchEvent(new Event('change', { bubbles: true }));
    }""", n)
    page.wait_for_timeout(800)


def cells(rows, cols):
    """Path steps over rows x cols, row by row."""
    return [{'row': r, 'col': c} for r in rows for c in cols]


def pairs(rows, cols):
    return [[r, c] for r in rows for c in cols]


# ── an automatic screen with circuits taken over by hand ──────────────────

def test_a_taken_over_circuit_drops_the_cabinets_off_the_wall(page):
    """The owner's case: circuit 1 taken over across columns 0-9 of row 0
    keeps only columns 0-5 once the wall is cut to 6 columns. Circuit 2,
    taken over wholly on columns 6-9, goes, and its cable with it; the walk
    fills the rest."""
    lid = reset(page, fields={
        'powerCustomOverrides': [1, 2],
        'powerCustomPaths': {'1': cells([0], range(10)),
                             '2': cells([1, 2], range(6, 10))},
        'powerCircuitCables': {'1': {'ft': 25, 'connector': None},
                               '2': {'ft': 50, 'connector': None}},
    })
    type_columns(page, 6)
    s = st(page, lid)
    assert s['columns'] == 6
    assert s['paths']['1'] == pairs([0], range(6))
    assert '2' not in s['paths']
    assert s['overrides'] == [1]
    assert s['cables'] == {'1': {'ft': 25, 'connector': None}}
    assert all(c['cabinets'] > 0 for c in s['circuits'])
    stored = server_layer(page, lid)
    assert [[e['row'], e['col']] for e in stored['powerCustomPaths']['1']] == pairs([0], range(6))
    assert stored['powerCustomOverrides'] == [1]
    assert s['historyAction'] == 'Update Properties'
    assert any('came off the wall' in n for n in notes(page)), notes(page)


# ── a custom screen: the hole stays ───────────────────────────────────────

GAP_PATHS = {
    '1': cells([0], range(10)),
    '2': cells([1, 2], range(6, 10)),
    '3': cells([1, 2], range(6)),
    '4': cells([3, 4], range(10)),
}


def test_a_custom_circuit_wholly_off_the_wall_goes_and_leaves_a_hole(page):
    lid = reset(page, fields={
        'powerFlowPattern': 'custom', 'powerCustomPaths': GAP_PATHS,
        'powerLabelOverrides': {'2': 'GONE', '3': 'KEEP'},
        'powerCircuitCables': {'2': {'ft': 50, 'connector': None},
                               '3': {'ft': 25, 'connector': None}},
    })
    s0 = st(page, lid)
    assert s0['required'] == 4 and s0['count'] == 4
    type_columns(page, 6)
    s = st(page, lid)
    # every step is on the wall
    assert all(c < 6 for p in s['paths'].values() for _, c in p)
    # circuit 2 is gone, 3 and 4 keep their numbers
    assert s['keys'] == [1, 3, 4]
    assert [c['num'] for c in s['circuits']] == [1, 3, 4]
    assert all(c['cabinets'] > 0 for c in s['circuits'])
    assert s['paths']['1'] == pairs([0], range(6))
    assert s['paths']['3'] == pairs([1, 2], range(6))
    assert s['paths']['4'] == pairs([3, 4], range(6))
    # it no longer counts
    assert s['required'] == 3
    assert s['count'] == 3
    # its label and cable went with it, the others' stay
    assert s['labels'] == {'3': 'KEEP'}
    assert s['cables'] == {'3': {'ft': 25, 'connector': None}}
    stored = server_layer(page, lid)
    assert sorted(int(k) for k in stored['powerCustomPaths']) == [1, 3, 4]
    msgs = notes(page)
    assert any('circuit GONE' in n and 'came off the wall' in n
               and 'keep their numbers' in n for n in msgs), msgs
    # one undo puts the wall and the circuit back
    assert s['historyAction'] == 'Update Properties'
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(800)
    back = st(page, lid)
    assert back['columns'] == 10
    assert back['keys'] == [1, 2, 3, 4]
    assert back['labels'] == {'2': 'GONE', '3': 'KEEP'}


def test_a_circuit_crossing_onto_a_group_peer_drops_the_peers_lost_row(page):
    """A custom group is one wall, its first screen owning every circuit.
    Circuit 1 runs along the owner's last row and onto the peer, circuit 2
    sits wholly on the peer's last row, circuit 3 on the owner. The peer
    loses a row: circuit 1 drops the peer's lost cabinets, circuit 2 goes
    and circuit 3 keeps its number. The owner rides the shrink's PUT."""
    lid, peer = reset(page, fields={
        'powerFlowPattern': 'custom', 'powerCustomPaths': {
            '1': [{'row': 4, 'col': 8}, {'row': 4, 'col': 9},
                  {'row': 4, 'col': 0, 'layerId': 'PEER'},
                  {'row': 4, 'col': 1, 'layerId': 'PEER'},
                  {'row': 3, 'col': 1, 'layerId': 'PEER'}],
            '2': [{'row': 4, 'col': c, 'layerId': 'PEER'} for c in range(2, 6)],
            '3': cells(range(4), [0]),
        }}, peer={'fields': {'powerFlowPattern': 'custom'}})
    page.evaluate("""(peer) => { const app = window.app, l = window.__ct.layer(peer);
        l.rows = 4; app.updateLayers([l]); app.saveState('Update Properties'); }""", peer)
    page.wait_for_timeout(800)
    s = st(page, lid)
    path = page.evaluate("(id) => window.__ct.layer(id).powerCustomPaths['1']", lid)
    assert path == [{'row': 4, 'col': 8}, {'row': 4, 'col': 9},
                    {'row': 3, 'col': 1, 'layerId': peer}]
    assert s['keys'] == [1, 3]
    assert [c['num'] for c in s['circuits']] == [1, 3]
    assert s['required'] == 2
    stored = server_layer(page, lid)['powerCustomPaths']
    assert stored['1'] == path, 'the trimmed owner did not ride the PUT'
    assert sorted(int(k) for k in stored) == [1, 3]


def test_a_wall_that_grows_leaves_the_circuits_alone(page):
    lid = reset(page, fields={'powerFlowPattern': 'custom', 'powerCustomPaths': GAP_PATHS})
    before = st(page, lid)['paths']
    type_columns(page, 12)
    s = st(page, lid)
    assert s['columns'] == 12
    assert s['paths'] == before
    assert notes(page) == []


# ── feeds: the removed circuit is unplugged, the others stay put ──────────

def test_a_removed_circuit_comes_off_its_multi_and_the_others_stay(page):
    """Eight circuits, one per column, on two multis of one distro: S1
    holds circuits 1-6 on tails 1-6, S2 holds 7-8 on tails 1-2. Circuit 2
    is drawn on the last column, so cutting the wall by one column takes
    it off the wall. It comes off S1 with its cable; every other circuit
    keeps its multi number and its tail, S1's home run included - even
    circuit 7, which a plain renumbering would have pulled into S1."""
    cols = {1: 0, 2: 8, 3: 1, 4: 2, 5: 3, 6: 4, 7: 5, 8: 6}
    paths = {str(n): cells(range(5), [c]) for n, c in cols.items()}
    lid = reset(page, columns=9, distros=[{'id': 'dtr', 'name': 'S'}], fields={
        'powerFlowPattern': 'custom', 'powerCustomPaths': paths,
        'powerSocaDistro': {'1': 'dtr', '2': 'dtr'},
        'powerSocaNumber': {'1': 1, '2': 2},
        'powerSocaLengths': {'1': '100', '2': '75'},
        'powerCircuitCables': {'2': {'ft': 50, 'connector': None},
                               '7': {'ft': 25, 'connector': None}},
    })
    s0 = st(page, lid)
    assert s0['feeds'] == {
        '1': [1, 1, 'dtr'], '2': [1, 2, 'dtr'], '3': [1, 3, 'dtr'],
        '4': [1, 4, 'dtr'], '5': [1, 5, 'dtr'], '6': [1, 6, 'dtr'],
        '7': [2, 1, 'dtr'], '8': [2, 2, 'dtr'],
    }
    type_columns(page, 8)
    s = st(page, lid)
    assert s['keys'] == [1, 3, 4, 5, 6, 7, 8]
    assert s['feeds'] == {
        '1': [1, 1, 'dtr'], '3': [1, 3, 'dtr'], '4': [1, 4, 'dtr'],
        '5': [1, 5, 'dtr'], '6': [1, 6, 'dtr'],
        '7': [2, 1, 'dtr'], '8': [2, 2, 'dtr'],
    }
    labels = {c['num']: c['label'] for c in s['circuits']}
    assert labels == {1: 'S1-1', 3: 'S1-3', 4: 'S1-4', 5: 'S1-5', 6: 'S1-6',
                      7: 'S2-1', 8: 'S2-2'}
    # its cable went, the others' stay; both home runs stay
    assert s['cables'] == {'7': {'ft': 25, 'connector': None}}
    assert sorted(s['lengths'].values()) == ['100', '75']
    assert s['required'] == 7
    msgs = notes(page)
    assert any('S1-2' in n and 'unplugged' in n for n in msgs), msgs


def test_a_circuit_alone_on_its_multi_takes_its_home_run_with_it(page):
    """Circuits 1-2 on S1, circuit 3 split off on its own multi S2 with a
    home run, drawn on the last column: it goes, S2 and its home run go,
    S1 stays as it was."""
    paths = {'1': cells(range(5), [0]), '2': cells(range(5), [1]),
             '3': cells(range(5), [2])}
    lid = reset(page, columns=3, distros=[{'id': 'dtr', 'name': 'S'}], fields={
        'powerFlowPattern': 'custom', 'powerCustomPaths': paths,
        'powerSocaSplits': [2],
        'powerSocaDistro': {'1': 'dtr', '2': 'dtr'},
        'powerSocaNumber': {'1': 1, '2': 2},
        'powerSocaLengths': {'1': '100', '2': '75'},
    })
    assert st(page, lid)['feeds']['3'] == [2, 1, 'dtr']
    type_columns(page, 2)
    s = st(page, lid)
    assert s['keys'] == [1, 2]
    assert s['feeds'] == {'1': [1, 1, 'dtr'], '2': [1, 2, 'dtr']}
    assert list(s['lengths'].values()) == ['100']


# ── 2fers and 3fers ───────────────────────────────────────────────────────

def test_shares_keep_the_legs_left_on_the_wall(page):
    """Four shared custom circuits on a 10-column wall cut to 8:
    * runs 1-3 (columns 0-2) are all on the wall: still a 3fer;
    * runs 4-6 (column 3, column 8 rows 2-4, column 9 rows 0-2) lose two
      legs: one is left, so the share dissolves and run 4 is a plain
      circuit;
    * runs 7-9 (column 8 rows 0-1, columns 4 and 5) lose their HEAD leg:
      a 2fer of runs 8-9 now, and the label and cable typed on the
      circuit follow it to its new first run;
    * runs 10-11 (column 9 rows 3 and 4) lose both legs: the circuit goes."""
    paths = {
        '1': cells(range(5), [0]), '2': cells(range(5), [1]), '3': cells(range(5), [2]),
        '4': cells(range(5), [3]), '5': cells(range(2, 5), [8]), '6': cells(range(3), [9]),
        '7': cells(range(2), [8]), '8': cells(range(5), [4]), '9': cells(range(5), [5]),
        '10': cells([3], [9]), '11': cells([4], [9]),
    }
    lid = reset(page, fields={
        'powerFlowPattern': 'custom', 'powerCustomPaths': paths,
        'powerSplitters': {'enabled': True, 'maxWays': 3, 'manual': {
            'merge': [[1, 2, 3], [4, 5, 6], [7, 8, 9], [10, 11]],
            'split': [], 'space': 'custom'}},
        'powerLabelOverrides': {'7': 'HEAD'},
        'powerCircuitCables': {'7': {'ft': 25, 'connector': None}},
    })
    s0 = st(page, lid)
    assert [c['runIds'] for c in s0['circuits']] == [[1, 2, 3], [4, 5, 6], [7, 8, 9], [10, 11]]
    assert s0['required'] == 4
    type_columns(page, 8)
    s = st(page, lid)
    assert s['keys'] == [1, 2, 3, 4, 8, 9]
    assert [(c['num'], c['runIds']) for c in s['circuits']] == [
        (1, [1, 2, 3]), (4, None), (8, [8, 9])]
    assert s['merge'] == [[1, 2, 3], [8, 9]]
    assert s['labels'] == {'8': 'HEAD'}
    assert s['cables'] == {'8': {'ft': 25, 'connector': None}}
    assert s['required'] == 3
    gangs = page.evaluate("""(id) => { window.app._circuitTailCache = null;
        return window.canvasRenderer._nferGangs(window.__ct.layer(id))
            .map(g => [g.num, g.ways]); }""", lid)
    assert sorted(gangs) == [[1, 3], [8, 2]]


def test_a_taken_over_3fer_keeps_its_runs_on_the_wall(page):
    """On an automatic screen a 3fer taken over by hand is one path whose
    runs start at a `branch` mark. Cut by two columns, its middle run loses
    its head cabinet and its last run is gone: the middle run still starts
    where its first cabinet left on the wall is, so it is a 2fer of two
    5-cabinet runs."""
    path = ([{'row': r, 'col': 0} for r in range(5)]
            + [{'row': 0, 'col': 8, 'branch': True}] + [{'row': r, 'col': 4} for r in range(5)]
            + [{'row': r, 'col': 9, 'branch': True} for r in range(1)]
            + [{'row': r, 'col': 9} for r in range(1, 5)])
    lid = reset(page, fields={
        'powerCustomOverrides': [1], 'powerCustomPaths': {'1': path},
    })
    type_columns(page, 8)
    layer_path = page.evaluate("(id) => window.__ct.layer(id).powerCustomPaths['1']", lid)
    assert [[e['row'], e['col'], bool(e.get('branch'))] for e in layer_path] == (
        [[r, 0, False] for r in range(5)]
        + [[0, 4, True]] + [[r, 4, False] for r in range(1, 5)])
    runs = page.evaluate("""(id) => { const app = window.app, l = window.__ct.layer(id);
        app._circuitTailCache = null;
        const c = app.screenCircuits(l).find(x => x.num === 1);
        return (c.branches || [c.panels]).map(b => b.length); }""", lid)
    assert runs == [5, 5]


# ── a show saved in the broken state ──────────────────────────────────────

def _open_file(page, tmp_path, project, name):
    path = tmp_path / f'{name}.json'
    path.write_text(json.dumps(project), encoding='utf-8')
    with page.expect_file_chooser() as chooser:
        page.evaluate("window.app.loadProjectFromFile()")
    chooser.value.set_files(str(path))
    page.wait_for_function(
        f"() => window.app.project && window.app.project.name === {json.dumps(name)}",
        timeout=10000)
    page.wait_for_timeout(1200)


def _saved_shrunk_without_trim(page, lid, name, columns, locked=False):
    """The project as an older version saved it: cut to `columns`, the
    panels rebuilt, the drawn circuits left as they were."""
    return page.evaluate("""([id, name, columns, locked]) => {
        const p = JSON.parse(JSON.stringify(window.app.project));
        p.name = name;
        const l = p.layers.find(x => x.id === id);
        l.columns = columns;
        l.panels = l.panels.filter(q => q.col < columns);
        if (locked) l.locked = true;
        return p;
    }""", [lid, name, columns, locked])


def test_a_saved_custom_show_is_repaired_when_opened(page, tmp_path):
    lid = reset(page, fields={
        'powerFlowPattern': 'custom', 'powerCustomPaths': GAP_PATHS,
        'powerLabelOverrides': {'2': 'GONE'},
    })
    project = _saved_shrunk_without_trim(page, lid, 'TrimSavedCustom', 6)
    _open_file(page, tmp_path, project, 'TrimSavedCustom')
    s = st(page, lid)
    assert s['columns'] == 6
    assert s['keys'] == [1, 3, 4]
    assert all(c < 6 for p in s['paths'].values() for _, c in p)
    assert [c['num'] for c in s['circuits']] == [1, 3, 4]
    assert s['required'] == 3
    assert s['labels'] == {}
    assert s['historyAction'] == 'Initial State'
    stored = server_layer(page, lid)
    assert sorted(int(k) for k in stored['powerCustomPaths']) == [1, 3, 4]
    msgs = notes(page)
    assert any('had no cabinets on the wall' in n and 'circuit' in n for n in msgs), msgs
    # opening it again changes nothing more
    assert page.evaluate("() => window.app.trimPortsOffWall({ load: true }).length") == 0


def test_a_locked_screen_is_left_as_it_is(page, tmp_path):
    lid = reset(page, fields={'powerFlowPattern': 'custom', 'powerCustomPaths': GAP_PATHS})
    project = _saved_shrunk_without_trim(page, lid, 'TrimSavedLocked', 6, locked=True)
    _open_file(page, tmp_path, project, 'TrimSavedLocked')
    s = st(page, lid)
    assert s['columns'] == 6
    assert s['keys'] == [1, 2, 3, 4]
    assert s['paths']['1'] == pairs([0], range(10))
    assert not any('circuit' in n for n in notes(page))
    # never silent: the locked error says what the lock kept
    e = errs(page)
    assert any('TrimWall: circuit S1-2 had no cabinets on the wall and stays as it is' in m
               and 'TrimWall is locked. Unlock it to change it.' in m for m in e), e


# ── locked screens a trim would reach ─────────────────────────────────────

def _shared_box(locked_fields=None):
    """TrimWall's circuits 1-3 (columns 0, 2, 1: circuit 2 on the last
    column) on S1 of one distro, pinned to number 1; TrimLocked's two
    circuits pinned to the same box, so the two screens share one multi.
    Neither stores its tails: the box deals them in layer order, TrimWall
    on 1-3 and TrimLocked on 4-5."""
    return dict(
        columns=3, distros=[{'id': 'dtr', 'name': 'S'}],
        fields={
            'powerFlowPattern': 'custom', 'powerCustomPaths': {
                '1': cells(range(5), [0]), '2': cells(range(5), [2]),
                '3': cells(range(5), [1])},
            'powerSocaDistro': {'1': 'dtr'}, 'powerSocaNumber': {'1': 1},
        },
        extra={'name': 'TrimLocked', 'columns': 2, 'fields': dict({
            'powerFlowPattern': 'custom', 'powerCustomPaths': {
                '1': cells(range(5), [0]), '2': cells(range(5), [1])},
            'powerSocaDistro': {'1': 'dtr'}, 'powerSocaNumber': {'1': 1},
            'locked': True,
        }, **(locked_fields or {}))})


def test_a_removal_that_would_move_a_locked_screens_tails_waits(page):
    """Taking circuit 2 off would free tail 2, and TrimLocked, dealt the
    box's lowest free tails, would move from 4-5 onto 2 and 4. A locked
    screen stays as it is, so the removal waits: TrimWall keeps circuit 2,
    TrimLocked keeps every store and every tail, and the locked error says
    which screen kept what and why - once, not on every save after.
    Unlocked, the next save makes the removal."""
    lid, locked = reset(page, **_shared_box())
    before = power_fields(page, locked)
    s0 = st(page, locked)
    assert [s0['feeds'][k] for k in ('1', '2')] == [[1, 4, 'dtr'], [1, 5, 'dtr']]
    shrink(page, lid, 2)
    s = st(page, lid)
    assert s['keys'] == [1, 2, 3]
    assert s['feeds']['2'] == [1, 2, 'dtr']
    assert power_fields(page, locked) == before
    assert st(page, locked)['feeds'] == s0['feeds']
    e = errs(page)
    assert len(e) == 1, e
    assert 'circuit S1-2 had only cabinets that came off the wall and stays for now' in e[0]
    assert 'TrimLocked is locked, and this would move its circuits on a shared multi' in e[0]
    # another save says nothing more
    page.evaluate("(id) => window.app.updateLayers([window.__ct.layer(id)])", lid)
    page.wait_for_timeout(500)
    assert len(errs(page)) == 1
    assert st(page, lid)['keys'] == [1, 2, 3]
    # unlocked, the next save takes the circuit off
    page.evaluate("""(id) => { const app = window.app, l = window.__ct.layer(id);
        l.locked = false; app.updateLayers([l]); }""", locked)
    page.wait_for_timeout(800)
    assert st(page, lid)['keys'] == [1, 3]


def test_a_locked_screen_holding_its_tails_lets_the_removal_through(page):
    """The same box with TrimLocked's tails stored (4-5): taking circuit 2
    off moves nothing of TrimLocked's, so the removal goes through and
    TrimLocked is not written at all."""
    lid, locked = reset(page, **_shared_box({'powerSocaPhasePos': {'1': [4, 5]}}))
    before = power_fields(page, locked)
    shrink(page, lid, 2)
    s = st(page, lid)
    assert s['keys'] == [1, 3]
    assert s['feeds'] == {'1': [1, 1, 'dtr'], '3': [1, 3, 'dtr']}
    assert power_fields(page, locked) == before
    assert st(page, locked)['feeds'] == {'1': [1, 4, 'dtr'], '2': [1, 5, 'dtr']}
    assert errs(page) == []


def test_a_group_owner_held_by_a_locked_member_keeps_its_circuits_and_says_so(page, tmp_path):
    """A show saved with its wall's owner unlocked and the other member
    locked (a half-locked group, read as locked until the user picks) and
    a circuit wholly off the owner's wall: the owner keeps its circuits,
    and the locked error names the locked member and the circuit kept."""
    lid, peer = reset(page, fields={
        'powerFlowPattern': 'custom', 'powerCustomPaths': GAP_PATHS,
        'powerLabelOverrides': {'2': 'GONE'},
    }, peer={'fields': {}})
    project = _saved_shrunk_without_trim(page, lid, 'TrimHalfLocked', 6)
    next(x for x in project['layers'] if x['id'] == peer)['locked'] = True
    _open_file(page, tmp_path, project, 'TrimHalfLocked')
    s = st(page, lid)
    assert s['keys'] == [1, 2, 3, 4]
    assert s['paths']['1'] == pairs([0], range(10))
    e = errs(page)
    assert any('circuit GONE had no cabinets on the wall and stays as it is' in m
               and 'TrimPeer is locked' in m for m in e), e


def test_a_removal_that_would_repack_a_locked_group_member_waits(page):
    """The repack lock every unplug runs: a removal that moves a locked
    group member's packing % is put back and said. Circuit 2, alone on a
    multi of a distro with 100% rated breakers, is the wall's only feed
    there, so taking it off would drop the locked member from 100% to 80%.
    (A half-locked group reads its unlocked members as locked too, which
    the trim refuses before this; the read is switched off here so the
    owner can reach the repack lock behind it.)"""
    lid, peer = reset(page, columns=3,
                      distros=[{'id': 'd100', 'name': 'S', 'system': '120/208',
                                'breakers100': True}],
                      fields={
                          'powerFlowPattern': 'custom', 'powerCustomPaths': {
                              '1': cells(range(5), [0]), '2': cells(range(5), [2])},
                          'powerSocaSplits': [1],
                          'powerSocaDistro': {'2': 'd100'},
                      }, peer={'fields': {'locked': True}})
    page.evaluate("() => { window.app._halfLockHolders = () => []; }")
    pct = "(id) => { window.app._circuitTailCache = null; " \
          "return window.app.circuitCapacity(window.__ct.layer(id)).pct; }"
    assert page.evaluate(pct, peer) == 1
    before = power_fields(page, peer)
    shrink(page, lid, 2)
    s = st(page, lid)
    assert s['keys'] == [1, 2]
    assert s['feeds']['2'][2] == 'd100'
    assert page.evaluate(pct, peer) == 1
    assert power_fields(page, peer) == before
    e = errs(page)
    assert any('stays for now' in m and 'TrimPeer is locked, and this would repack its circuits' in m
               for m in e), e


def test_no_page_errors(page):
    assert page._ct_errors == [], ' || '.join(page._ct_errors)
