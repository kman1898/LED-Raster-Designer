"""A wall that shrinks trims its drawn data ports.

The owner, 2026-11-02, on a show drawn 90 cabinets wide and then cut to 85:
the drawn ports kept the cabinets of columns 85-89, which no longer exist,
so ports sat wholly off the wall and left holes in the numbering. His
ruling, pinned here in a real browser:

* TRIM - when a wall shrinks (columns or rows, typed, by Size by Wall
  Dimensions or through its group), every drawn data port drops the
  cabinets that fell off the wall.
* CLOSE UP - a port left with no cabinets is removed and the later port
  numbers close up the way Redraw-as-one closes them: the overrides, the
  active port, the typed port names and the card pins all follow.
* LOAD - a show already saved in that state is repaired the same way when
  it is opened.

The walls are synthetic: 90 x 5 cabinets of 192 x 384 on NovaStar Armor at
8-bit 60 Hz, eight cabinets to a port, walked tl-h, Organized, numbered
Across. Every row cuts into eleven ports of eight and a leftover of two
(columns 88-89), so row r holds ports 12r+1 .. 12r+12 and the leftovers are
ports 12, 24, 36, 48 and 60. Cut to 85 columns, each row keeps ten ports of
eight and a port of five (columns 80-84); the leftovers are gone.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

LEFTOVERS = [12, 24, 36, 48, 60]


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project exactly as this module found it
    (see conftest.server_project_guard)."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1400, 'height': 900})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.evaluate(HELPERS_JS)
    yield pg
    context.close()


HELPERS_JS = """
window.__shr = {
    async reset(opts) {
        opts = opts || {};
        const app = window.app, r = window.canvasRenderer;
        app._mergeRedraw = null;
        app._portPicks = null;
        app._overrideEditing = null;
        let project = await (await fetch('/api/project')).json();
        project.layers = [];
        project.groups = [];
        project.port_assignments = { auto: false, autoRetired: true, pins: [] };
        await fetch('/api/project', {
            method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(project),
        });
        await fetch('/api/layer/add', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                name: 'ShrinkWall',
                columns: 90, rows: 5, cabinet_width: 192, cabinet_height: 384,
                offset_x: 0, offset_y: 0,
            }),
        });
        app.project = await (await fetch('/api/project')).json();
        app.dedupeProjectLayers('shrink_reset');
        const layer = app.project.layers.filter(
            l => (l.type || 'screen') === 'screen')[0];
        layer.flowPattern = 'tl-h';
        layer.portMappingMode = 'organized';
        layer.portNumberOrder = 'across';
        layer.processorType = 'novastar-armor';
        layer.bitDepth = 8;
        layer.frameRate = 60;
        layer.lowLatency = false;
        layer.sizeByDimensions = false;
        layer.customPortPaths = {};
        layer.customPortOverrides = [];
        layer.customPortIndex = 1;
        layer.portLabelOverridesPrimary = {};
        layer.portLabelOverridesReturn = {};
        if (opts.custom) {
            // Whole-screen custom, drawn the way the automatic walk had it.
            const items = app.calculatePortAssignments(layer) || [];
            const paths = {};
            items.forEach(it => {
                (paths[it.port] = paths[it.port] || []).push({ row: it.panel.row, col: it.panel.col });
            });
            layer.lastFlowPattern = 'tl-h';
            layer.flowPattern = 'custom';
            layer.customPortPaths = paths;
        }
        (opts.overrides || []).forEach(n => app.overrideRun(layer, 'data', n));
        if (app._overrideEditing) app.endOverrideEdit();
        if (opts.index) layer.customPortIndex = opts.index;
        if (opts.labels) layer.portLabelOverridesPrimary = opts.labels;
        if (opts.pins) {
            app.project.port_assignments = { auto: false, autoRetired: true,
                pins: opts.pins.map(([index, port]) =>
                    ({ layerId: String(layer.id), index, cardId: 'card-test', port })) };
        }
        // the take-overs' own layer saves land first, or one of them could
        // arrive after this PUT and put an older copy of the screen back
        await app._layerSavesSettled();
        await fetch('/api/project', { method: 'PUT',
            headers: {'Content-Type': 'application/json'}, body: JSON.stringify(app.project) });
        app.project = await (await fetch('/api/project')).json();
        app.dedupeProjectLayers('shrink_reset');
        const live = app.project.layers.find(l => l.id === layer.id);
        app.selectLayer(live);
        app.selectedLayerIds = new Set([live.id]);
        if (typeof app.hideContextMenu === 'function') app.hideContextMenu();
        r.viewMode = 'data-flow';
        r.zoom = 0.05;
        r.panX = 20;
        r.panY = 60;
        r.render();
        if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
        app.resetHistory('Shrink Test Baseline');
        window.__notes = [];
        window.__errs = [];
        if (!app.__shrToastWrapped) {
            const real = app._toast.bind(app);
            app._toast = (m, err, ms) => {
                (err ? window.__errs : window.__notes).push(m);
                return real(m, err, ms);
            };
            app.__shrToastWrapped = true;
        }
        return live.id;
    },

    layer(id) {
        return window.app.project.layers.find(l => l.id === id);
    },

    // port -> [[row, col], ...] as the map feeds them, on any screen kind:
    // the drawn paths on a custom screen, the walk with its overrides on
    // an automatic one.
    ports(id) {
        const app = window.app, layer = this.layer(id);
        const out = {};
        if (app.isCustomFlow(layer)) {
            Object.keys(layer.customPortPaths || {}).forEach(k => {
                const path = layer.customPortPaths[k] || [];
                if (path.length) out[k] = path.map(e => [e.row, e.col]);
            });
            return out;
        }
        (app.calculatePortAssignments(layer) || []).forEach(it => {
            (out[it.port] = out[it.port] || []).push([it.panel.row, it.panel.col]);
        });
        return out;
    },

    state(id) {
        const app = window.app, layer = this.layer(id);
        const steps = [];
        Object.keys(layer.customPortPaths || {}).forEach(k =>
            (layer.customPortPaths[k] || []).forEach(e => steps.push([+k, e.row, e.col])));
        return {
            columns: layer.columns, rows: layer.rows,
            panels: (layer.panels || []).length,
            overrides: app.getOverrideNums(layer, 'data'),
            index: layer.customPortIndex,
            labels: layer.portLabelOverridesPrimary || {},
            pathKeys: Object.keys(layer.customPortPaths || {}).map(Number).sort((a, b) => a - b),
            steps,
            required: app.getLayerPortsRequired(layer),
            pins: ((app.project.port_assignments || {}).pins || [])
                .map(p => [p.index, p.port]),
            historyAction: (app.history && app.history[app.historyIndex])
                ? app.history[app.historyIndex].action : null,
            historyIndex: app.historyIndex,
            firstEntryPins: ((((app.history || [])[0] || {}).project || {})
                .port_assignments || {}).pins,
        };
    },
};
"""


def reset(page, **opts):
    lid = page.evaluate("(o) => window.__shr.reset(o)", opts)
    page.wait_for_timeout(300)
    return lid


def st(page, lid):
    return page.evaluate("(id) => window.__shr.state(id)", lid)


def ports(page, lid):
    return {int(k): v for k, v in page.evaluate("(id) => window.__shr.ports(id)", lid).items()}


def server_pins(page):
    return page.evaluate("""async () => (((await (await fetch('/api/project')).json())
        .port_assignments || {}).pins || []).map(p => [p.index, p.port])""")


def server_layer(page, lid):
    return page.evaluate("""async (id) => (await (await fetch('/api/project')).json())
        .layers.find(l => l.id === id)""", lid)


def type_columns(page, n):
    """The Screen Info Columns field, set and committed with the change
    event a user's Tab or Enter fires (the Data view keeps Screen Info out
    of sight, so the value is set on the field itself)."""
    page.evaluate("""(n) => {
        const el = document.getElementById('screen-columns');
        el.value = String(n);
        el.dispatchEvent(new Event('change', { bubbles: true }));
    }""", n)
    page.wait_for_timeout(700)


def row_ports_across(columns):
    """The ports of the synthetic wall numbered Across: [[(row, col)...]]."""
    out = []
    for r in range(5):
        c = 0
        while c < columns:
            out.append([[r, x] for x in range(c, min(c + 8, columns))])
            c += 8
    return out


def assert_every_cabinet_once(p, columns, rows=5):
    cells = [tuple(c) for run in p.values() for c in run]
    assert len(cells) == len(set(cells)), 'a cabinet sits on two ports'
    assert set(cells) == {(r, c) for r in range(rows) for c in range(columns)}, \
        'the ports do not cover the wall exactly'


# ── the synthetic wall ────────────────────────────────────────────────────

def test_the_wall_is_what_the_docstring_says(page):
    lid = reset(page, custom=True)
    p = ports(page, lid)
    assert sorted(p) == list(range(1, 61))
    assert [p[n] for n in LEFTOVERS] == [[[r, 88], [r, 89]] for r in range(5)]
    assert p[11] == [[0, c] for c in range(80, 88)]


# ── a custom screen shrinks ───────────────────────────────────────────────

def test_custom_ports_trim_and_close_up_when_columns_shrink(page):
    lid = reset(page, custom=True, index=13,
                labels={'12': 'GONE', '13': 'ROW 2 FIRST', '59': 'LAST'},
                pins=[[10, 1], [11, 2], [12, 3], [58, 4]])
    type_columns(page, 85)
    s = st(page, lid)
    p = ports(page, lid)
    # every step is on the wall, and the five leftovers are gone
    assert all(c < 85 for _, _, c in s['steps']), 'a step was left off the wall'
    assert sorted(p) == list(range(1, 56))
    assert [p[n] for n in range(1, 56)] == row_ports_across(85)
    assert_every_cabinet_once(p, 85)
    assert s['required'] == 55
    # the names and the active port follow their ports
    assert s['labels'] == {'12': 'ROW 2 FIRST', '55': 'LAST'}
    assert s['index'] == 12
    # the cards follow: port 12's socket is released, 13 is now 12 on its
    # own socket, 59 is now 55 on its own
    expected = [[10, 1], [11, 3], [54, 4]]
    assert s['pins'] == expected
    assert server_pins(page) == expected
    assert server_layer(page, lid)['customPortPaths'] == page.evaluate(
        "(id) => window.__shr.layer(id).customPortPaths", lid)
    # said, not silent
    notes = page.evaluate("() => window.__notes")
    assert any('ports P12, P24, P36, P48, P60' in n and 'came off the wall' in n for n in notes), notes
    # the trim is part of the shrink's own undo step, pins included
    assert s['historyAction'] == 'Update Properties'
    assert s['firstEntryPins'] is not None
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(800)
    back = st(page, lid)
    assert back['columns'] == 90
    assert sorted(ports(page, lid)) == list(range(1, 61))
    assert back['labels'] == {'12': 'GONE', '13': 'ROW 2 FIRST', '59': 'LAST'}
    assert back['pins'] == [[10, 1], [11, 2], [12, 3], [58, 4]]
    assert server_pins(page) == [[10, 1], [11, 2], [12, 3], [58, 4]]
    # and redo brings the trimmed wall back with its moved pins
    page.evaluate("() => window.app.redo()")
    page.wait_for_timeout(800)
    again = st(page, lid)
    assert again['columns'] == 85
    assert sorted(ports(page, lid)) == list(range(1, 56))
    assert again['pins'] == expected
    assert server_pins(page) == expected


def test_rows_shrinking_drops_the_last_rows_ports(page):
    """Rows go the same way, through the funnel every layer commit takes
    (updateLayers): Size by Wall Dimensions and a group's shared size
    both land there."""
    lid = reset(page, custom=True)
    page.evaluate("""(id) => { const app = window.app, l = window.__shr.layer(id);
        l.rows = 4; app.updateLayers([l]); app.saveState('Update Properties'); }""", lid)
    page.wait_for_timeout(700)
    p = ports(page, lid)
    assert sorted(p) == list(range(1, 49))
    assert_every_cabinet_once(p, 90, rows=4)
    assert st(page, lid)['panels'] == 360


def test_size_by_wall_dimensions_trims_too(page):
    lid = reset(page, custom=True)
    page.evaluate("""(id) => { const app = window.app, l = window.__shr.layer(id);
        l.sizeByDimensions = true; l.targetUnit = 'px';
        l.targetWidth = 85 * 192; l.targetHeight = 5 * 384;
        const fit = app.computeTilesForWall(l);
        l.columns = fit.columns; l.rows = fit.rows;
        app.updateLayers([l]); app.saveState('Update Properties'); }""", lid)
    page.wait_for_timeout(700)
    assert st(page, lid)['columns'] == 85
    p = ports(page, lid)
    assert sorted(p) == list(range(1, 56))
    assert_every_cabinet_once(p, 85)


def test_a_wall_that_grows_is_untouched(page):
    lid = reset(page, custom=True, labels={'12': 'KEEP'})
    before = page.evaluate("(id) => window.__shr.layer(id).customPortPaths", lid)
    type_columns(page, 92)
    s = st(page, lid)
    assert s['columns'] == 92
    assert page.evaluate("(id) => window.__shr.layer(id).customPortPaths", lid) == before
    assert s['labels'] == {'12': 'KEEP'}
    assert page.evaluate("() => window.__notes") == []


# ── an automatic screen with redrawn ports ────────────────────────────────

def test_overrides_trim_and_close_up_on_an_automatic_screen(page):
    """11 runs into the cut (it keeps five cabinets), 12 is the row-0
    leftover (it goes), 13 is row 1's first port (it becomes 12). The walk
    fills every other number with no hole."""
    lid = reset(page, overrides=[11, 12, 13], pins=[[11, 7], [12, 8], [20, 9]])
    s0 = st(page, lid)
    assert s0['overrides'] == [11, 12, 13]
    type_columns(page, 85)
    s = st(page, lid)
    layer_paths = page.evaluate("(id) => window.__shr.layer(id).customPortPaths", lid)
    assert s['overrides'] == [11, 12]
    assert [[e['row'], e['col']] for e in layer_paths['11']] == [[0, c] for c in range(80, 85)]
    assert [[e['row'], e['col']] for e in layer_paths['12']] == [[1, c] for c in range(8)]
    assert all(c < 85 for _, _, c in s['steps'])
    p = ports(page, lid)
    n = len(p)
    assert sorted(p) == list(range(1, n + 1)), 'the numbers have a hole'
    assert n == s['required']
    assert_every_cabinet_once(p, 85)
    # the leftover's pin is released, the later ones close up by one
    assert s['pins'] == [[11, 8], [19, 9]]
    assert server_pins(page) == [[11, 8], [19, 9]]


# ── a group ───────────────────────────────────────────────────────────────

def test_a_path_crossing_onto_a_group_peer_drops_the_peers_lost_row(page):
    import app as app_module
    lid = reset(page)
    peer = page.evaluate("""async () => {
        const res = await fetch('/api/layer/add', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ name: 'ShrinkPeer', columns: 90, rows: 5,
                cabinet_width: 192, cabinet_height: 384, offset_x: 90 * 192, offset_y: 0 }),
        });
        return (await res.json()).id;
    }""")
    group = app_module._create_group(app_module.current_project, [lid, peer], name='ShrinkGroup')
    assert group is not None
    page.evaluate("""async ([id, peer]) => {
        const app = window.app;
        app.project = await (await fetch('/api/project')).json();
        app.dedupeProjectLayers('shrink_group');
        const owner = window.__shr.layer(id);
        // one hand-drawn port: across the owner's last row, then the peer's
        owner.customPortOverrides = [1];
        owner.customPortPaths = { 1: [
            { row: 4, col: 88 }, { row: 4, col: 89 },
            { row: 4, col: 0, layerId: peer }, { row: 4, col: 1, layerId: peer },
            { row: 3, col: 1, layerId: peer },
        ] };
        app.updateLayers([owner]);
        app.resetHistory('Shrink Group Baseline');
    }""", [lid, peer])
    page.wait_for_timeout(500)
    page.evaluate("""(peer) => { const app = window.app, l = window.__shr.layer(peer);
        l.rows = 4; app.updateLayers([l]); app.saveState('Update Properties'); }""", peer)
    page.wait_for_timeout(700)
    path = page.evaluate("(id) => window.__shr.layer(id).customPortPaths['1']", lid)
    assert path == [{'row': 4, 'col': 88}, {'row': 4, 'col': 89},
                    {'row': 3, 'col': 1, 'layerId': peer}]
    stored = server_layer(page, lid)['customPortPaths']['1']
    assert stored == path, 'the trimmed owner did not ride the PUT'


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


def _saved_shrunk_without_trim(page, lid, name):
    """The project as an older version saved it: cut to 85 columns, the
    panels rebuilt, the drawn paths left as they were."""
    return page.evaluate("""([id, name]) => {
        const p = JSON.parse(JSON.stringify(window.app.project));
        p.name = name;
        const l = p.layers.find(x => x.id === id);
        l.columns = 85;
        l.panels = l.panels.filter(q => q.col < 85);
        return p;
    }""", [lid, name])


def test_a_saved_custom_show_is_repaired_when_opened(page, tmp_path):
    lid = reset(page, custom=True, index=13,
                labels={'12': 'GONE', '13': 'ROW 2 FIRST', '59': 'LAST'},
                pins=[[10, 1], [11, 2], [12, 3], [58, 4]])
    project = _saved_shrunk_without_trim(page, lid, 'ShrinkSavedCustom')
    _open_file(page, tmp_path, project, 'ShrinkSavedCustom')
    s = st(page, lid)
    p = ports(page, lid)
    assert s['columns'] == 85
    assert all(c < 85 for _, _, c in s['steps'])
    assert [p[n] for n in range(1, 56)] == row_ports_across(85)
    assert sorted(p) == list(range(1, 56))
    assert s['labels'] == {'12': 'ROW 2 FIRST', '55': 'LAST'}
    assert s['index'] == 12
    expected = [[10, 1], [11, 3], [54, 4]]
    assert s['pins'] == expected
    assert server_pins(page) == expected
    # the opened show's first undo step carries the moved pins too
    assert [[q['index'], q['port']] for q in s['firstEntryPins']] == expected
    assert s['historyAction'] == 'Initial State'
    notes = page.evaluate("() => window.__notes")
    assert any('had no cabinets on the wall' in n for n in notes), notes


def test_a_saved_automatic_show_is_repaired_when_opened(page, tmp_path):
    """The owner's shape: an override held empty (a redraw saved before it
    was drawn), one standing wholly on cabinets that are gone, and one that
    is real. The first two go and the third closes up onto the first's
    number."""
    lid = reset(page, overrides=[13])
    project = _saved_shrunk_without_trim(page, lid, 'ShrinkSavedAuto')
    layer = next(x for x in project['layers'] if x['id'] == lid)
    layer['customPortOverrides'] = [12, 13, 14]
    layer['customPortPaths']['12'] = []
    layer['customPortPaths']['14'] = [{'row': 1, 'col': 88}, {'row': 1, 'col': 89}]
    _open_file(page, tmp_path, project, 'ShrinkSavedAuto')
    s = st(page, lid)
    assert s['overrides'] == [12]
    paths = page.evaluate("(id) => window.__shr.layer(id).customPortPaths", lid)
    assert [[e['row'], e['col']] for e in paths['12']] == [[1, c] for c in range(8)]
    assert '13' not in paths and '14' not in paths
    p = ports(page, lid)
    assert sorted(p) == list(range(1, len(p) + 1)), 'the numbers have a hole'
    assert_every_cabinet_once(p, 85)
    assert server_layer(page, lid)['customPortOverrides'] == [12]
    # opening it again changes nothing more
    assert page.evaluate("() => window.app.trimPortsOffWall({ load: true }).length") == 0



# ── QA, 1.6.0 ─────────────────────────────────────────────────────────────

def test_an_unused_old_drawing_closes_up_with_the_cut(page):
    """An automatic screen keeps the drawing of an earlier custom spell,
    unused. Cut, its ports left with no cabinet go and its later numbers
    close up like the live ports', so custom mode turned on again finds no
    holes where the wall shrank."""
    lid = reset(page, custom=True)
    page.evaluate("""(id) => { const app = window.app, l = window.__shr.layer(id);
        l.flowPattern = 'tl-h'; app.updateLayers([l]); app.resetHistory('Unused Drawing'); }""", lid)
    page.wait_for_timeout(400)
    assert st(page, lid)['pathKeys'] == list(range(1, 61))
    type_columns(page, 85)
    s = st(page, lid)
    assert s['pathKeys'] == list(range(1, 56)), s['pathKeys']
    paths = page.evaluate("(id) => window.__shr.layer(id).customPortPaths", lid)
    assert [[[e['row'], e['col']] for e in paths[str(n)]] for n in range(1, 56)] == row_ports_across(85)
    assert s['overrides'] == []
    # the automatic walk itself is whole
    p = ports(page, lid)
    assert sorted(p) == list(range(1, len(p) + 1))
    assert_every_cabinet_once(p, 85)


def test_a_screen_locked_when_opened_is_repaired_when_unlocked(page, tmp_path):
    """A locked screen is left as it is when its show is opened. Unlocked,
    it gets the open's whole repair in the unlock's own step: the override
    held empty goes as well as the one standing off the wall."""
    lid = reset(page, overrides=[13])
    project = _saved_shrunk_without_trim(page, lid, 'ShrinkSavedLocked')
    layer = next(x for x in project['layers'] if x['id'] == lid)
    layer['customPortOverrides'] = [12, 13, 14]
    layer['customPortPaths']['12'] = []
    layer['customPortPaths']['14'] = [{'row': 1, 'col': 88}, {'row': 1, 'col': 89}]
    layer['locked'] = True
    _open_file(page, tmp_path, project, 'ShrinkSavedLocked')
    assert st(page, lid)['overrides'] == [12, 13, 14], 'a locked screen was changed'
    page.evaluate("""(id) => { const app = window.app;
        app.selectLayer(window.__shr.layer(id));
        app.selectedLayerIds = new Set([id]);
        app.setLockOnSelected(false); }""", lid)
    page.wait_for_timeout(800)
    s = st(page, lid)
    assert s['overrides'] == [12]
    assert s['historyAction'] == 'Unlock Layers'
    paths = page.evaluate("(id) => window.__shr.layer(id).customPortPaths", lid)
    assert [[e['row'], e['col']] for e in paths['12']] == [[1, c] for c in range(8)]
    p = ports(page, lid)
    assert sorted(p) == list(range(1, len(p) + 1)), 'the numbers have a hole'
    stored = server_layer(page, lid)
    assert stored['customPortOverrides'] == [12] and stored['locked'] is False
    # undo puts the lock and the screen back together
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(500)
    assert st(page, lid)['overrides'] == [12, 13, 14]


# ── no gaps in the custom numbers (the owner, 2026-11-03) ─────────────────

def test_a_saved_custom_show_with_a_hole_opens_numbered_without_gaps(page, tmp_path):
    """"on custom there should be no gaps like automatic": a custom drawing
    saved with nothing on port 3 opens as 1..N - the ports after it move up
    with their names and their cards."""
    lid = reset(page, custom=True, labels={'4': 'FOUR', '60': 'LAST'},
                pins=[[3, 7], [59, 9]])
    project = json.loads(json.dumps(page.evaluate("() => window.app.project")))
    project['name'] = 'GapSavedCustom'
    layer = next(x for x in project['layers'] if x['id'] == lid)
    four = layer['customPortPaths']['4']
    del layer['customPortPaths']['3']
    _open_file(page, tmp_path, project, 'GapSavedCustom')
    s = st(page, lid)
    assert s['pathKeys'] == list(range(1, 60))
    paths = page.evaluate("(id) => window.__shr.layer(id).customPortPaths", lid)
    assert paths['3'] == four
    assert s['labels'] == {'3': 'FOUR', '59': 'LAST'}
    assert s['pins'] == [[2, 7], [58, 9]]
    assert server_pins(page) == [[2, 7], [58, 9]]
    assert server_layer(page, lid)['customPortPaths']['3'] == four
    notes = page.evaluate("() => window.__notes")
    assert any('port P3 had nothing drawn on it' in n and '1-59' in n for n in notes), notes


def test_an_unused_drawing_opens_without_gaps_round_a_live_override(page, tmp_path):
    """An automatic screen's unused drawing with a hole closes up when the
    show opens, stepping round the live override, which keeps its number
    and its path."""
    lid = reset(page, custom=True)
    page.evaluate("""(id) => { const app = window.app, l = window.__shr.layer(id);
        l.flowPattern = 'tl-h'; app.updateLayers([l]); }""", lid)
    page.wait_for_timeout(300)
    page.evaluate("(id) => { window.app.overrideRun(window.__shr.layer(id), 'data', 30); "
                  "window.app.endOverrideEdit(); }", lid)
    page.wait_for_timeout(300)
    project = json.loads(json.dumps(page.evaluate("() => window.app.project")))
    project['name'] = 'GapSavedUnused'
    layer = next(x for x in project['layers'] if x['id'] == lid)
    thirty = layer['customPortPaths']['30']
    del layer['customPortPaths']['5']
    _open_file(page, tmp_path, project, 'GapSavedUnused')
    s = st(page, lid)
    assert s['overrides'] == [30]
    assert s['pathKeys'] == list(range(1, 60))
    paths = page.evaluate("(id) => window.__shr.layer(id).customPortPaths", lid)
    assert paths['30'] == thirty, 'the live override moved'
    # turned custom, the drawing runs 1-59 with no hole
    page.evaluate("(id) => { const app = window.app; app.selectLayer(window.__shr.layer(id)); "
                  "app.toggleCustomFlowMode(true); }", lid)
    page.wait_for_timeout(300)
    p = ports(page, lid)
    assert sorted(p) == list(range(1, 60))


def test_turning_custom_on_closes_the_drawings_gaps(page):
    lid = reset(page, custom=True, labels={'7': 'SEVEN'})
    page.evaluate("""(id) => { const app = window.app, l = window.__shr.layer(id);
        l.flowPattern = 'tl-h';
        delete l.customPortPaths[5];
        l.customPortPaths[6] = [];
        app.updateLayers([l]); app.resetHistory('Gap Baseline'); }""", lid)
    page.wait_for_timeout(300)
    seven = page.evaluate("(id) => window.__shr.layer(id).customPortPaths[7]", lid)
    page.evaluate("(id) => { const app = window.app; app.selectLayer(window.__shr.layer(id)); "
                  "app.toggleCustomFlowMode(true); }", lid)
    page.wait_for_timeout(400)
    s = st(page, lid)
    assert s['historyAction'] == 'Custom Mode Toggle'
    assert s['pathKeys'] == list(range(1, 59))
    assert page.evaluate("(id) => window.__shr.layer(id).customPortPaths[5]", lid) == seven
    assert s['labels'] == {'5': 'SEVEN'}
    assert sorted(ports(page, lid)) == list(range(1, 59))


# ── No phantom ports (QA, 1.6.0) ──────────────────────────────────────────
#
# Every port number has cabinets. A single redraw that ends with its number
# held empty (Redraw port, Clear Port, Esc) hands the number back to the
# walk instead of leaving a phantom a card could be filled onto, and the
# names and cards follow the cabinets.

def _redraw(page, lid, num):
    page.evaluate("(a) => window.app.overrideRun(window.__shr.layer(a[0]), 'data', a[1])",
                  [lid, num])
    page.wait_for_timeout(300)


def _clear_port(page):
    page.evaluate("() => document.getElementById('custom-clear-port').click()")
    page.wait_for_timeout(300)


def _esc(page):
    page.mouse.move(700, 450)
    page.keyboard.press('Escape')
    page.wait_for_timeout(700)


def test_a_redraw_cleared_and_ended_hands_its_number_back(page):
    pins = [[i, 100 + i] for i in range(14)]
    lid = reset(page, pins=pins)
    before = ports(page, lid)
    _redraw(page, lid, 3)
    _clear_port(page)
    assert st(page, lid)['overrides'] == [3], 'the open redraw keeps its number'
    _esc(page)
    s = st(page, lid)
    assert s['overrides'] == []
    p = ports(page, lid)
    assert sorted(p) == list(range(1, 61)), 'the numbers have a hole'
    assert p == before, 'the cabinets went back where they were'
    assert s['pins'] == pins and server_pins(page) == pins
    assert s['historyAction'] == 'Return Port To Auto'
    notes = page.evaluate("() => window.__notes")
    assert any('nothing was drawn on port P3, so it went back to automatic' in n
               for n in notes), notes


def test_the_names_and_cards_follow_the_cabinets_when_a_redraw_ends(page):
    """P2 is cleared, P3 picked up (the cleared cabinets stay held) and
    redrawn onto P2's cabinets. At the end P2 is handed back: the walk gives
    it P3's old cabinets, so the two ports swap numbers, and the pins and
    names swap with them."""
    pins = [[i, 100 + i] for i in range(14)]
    lid = reset(page, pins=pins, labels={'2': 'TWO', '3': 'THREE'})
    before = ports(page, lid)
    _redraw(page, lid, 2)
    _clear_port(page)
    _redraw(page, lid, 3)
    _clear_port(page)
    page.evaluate("""(id) => { const app = window.app;
        for (let c = 8; c < 16; c++) { const l = window.__shr.layer(id);
            app.addPanelToCustomPath(l.panels.find(p => p.row === 0 && p.col === c), l,
                                     { click: true }); } }""", lid)
    page.wait_for_timeout(400)
    errs = page.evaluate("() => window.__errs")
    assert errs == [], errs
    _esc(page)
    s = st(page, lid)
    p = ports(page, lid)
    assert sorted(p) == list(range(1, 61))
    assert p[3] == before[2] and p[2] == before[3]
    assert s['overrides'] == [3]
    want = [[0, 100], [1, 102], [2, 101]] + pins[3:]
    assert s['pins'] == want and server_pins(page) == want
    assert s['labels'] == {'2': 'THREE', '3': 'TWO'}


def test_nothing_lands_on_a_number_held_empty(page):
    lid = reset(page)
    _redraw(page, lid, 3)
    _clear_port(page)
    page.wait_for_timeout(300)
    out = page.evaluate("""async (id) => { const app = window.app;
        const screens = app._assignmentScreens();
        const scr = screens.find(s => s.layerId === String(id));
        const body = await (await fetch('/api/port-assignments/resolve', { method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ screens }) })).json();
        const res = body.resolution.screens.find(s => s.layerId === String(id));
        return { empty: scr.emptyPorts, unplaced: res.unplaced }; }""", lid)
    assert out['empty'] == [2]
    assert 2 not in out['unplaced'] and 3 in out['unplaced']
    _esc(page)


def test_an_empty_override_outside_a_redraw_closes_up_at_the_next_edit(page):
    lid = reset(page, pins=[[1, 5], [2, 6], [3, 7]])
    page.evaluate("""(id) => { const app = window.app, l = window.__shr.layer(id);
        l.customPortOverrides = [3]; l.customPortPaths = { 3: [] };
        app.updateLayers([l]); }""", lid)
    page.wait_for_timeout(500)
    s = st(page, lid)
    assert s['overrides'] == []
    assert sorted(ports(page, lid)) == list(range(1, 61))
    # the phantom's pin is released and the next one closes up onto it
    assert s['pins'] == [[1, 5], [2, 7]]
