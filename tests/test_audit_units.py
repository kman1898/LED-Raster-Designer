"""Units and number formatting - the fixes from a hand-checked audit.

1. A weight unit picked on one group member never relabels a peer's
   figure: weight_unit is no longer a group-shared field, each member keeps
   its own number in its own unit, and the group total stays the same wall.
2. A weight unit change with several screens selected converts each
   screen's OWN weight (it used to write the primary screen's converted
   figure to all of them). A locked screen stays unchanged and is named.
3. The feet-and-fractions size label carries a fraction that rounds to a
   whole inch, and 12 inches into a foot.
4. The feet-and-decimal-inches label never prints 12.0".
5. en-US thousands separators: the canvas weight label, the binder's
   numbers and pull quantities; the group row says "1 screen".
6. The copper 10G maxima in feet are the exact conversions of 60 m and
   30 m, on both the JS and the Python side.
7. cableFigure prints nothing for no length, and never 0 for a positive one.
8. The server's length refusals name the show's cable unit.

Each one fails on the code before the fix. The browser half seeds the
live server through its own endpoints and waits on the app's own saves
(_layerSavesSettled), never on a fixed sleep.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import app as app_module  # noqa: E402
import processor_catalog as catalog  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# ══════════════════════════════════════════════════════════════════════════
# Flask / Python: 6 (the server's table) and 8 (the refusals)
# ══════════════════════════════════════════════════════════════════════════

def test_the_python_copper_maxima_are_the_exact_feet_of_60_and_30_m():
    kinds = dict(catalog.COPPER_LINK_KINDS)
    assert kinds['Cat6A'] == pytest.approx(60 / 0.3048)      # 196.85, not 196
    assert kinds['Cat5e'] == pytest.approx(30 / 0.3048)      # 98.43, not 98
    assert kinds['Cat6'] == 100
    # a 98.4 ft Cat5e run and a 196.8 ft Cat6A run are within the limit
    assert 98.4 <= kinds['Cat5e'] < 98.5
    assert 196.8 <= kinds['Cat6A'] < 196.9


def _h9_with_card_and_box(client):
    st = client.post('/api/processors', json={'deviceId': 'novastar-h9'}).get_json()
    pid = st['processors'][-1]['id']
    st = client.put(f'/api/processors/{pid}/slots/0',
                    json={'deviceId': 'novastar-card-h-16xrj45-2xfiber'}).get_json()
    proc = next(p for p in st['processors'] if p['id'] == pid)
    cid = proc['slots'][0]['card']['id']
    r = client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                    json={'deviceId': 'novastar-cvt10', 'pair': False})
    assert r.status_code == 201, r.get_data(as_text=True)
    proc = next(p for p in r.get_json()['processors'] if p['id'] == pid)
    return pid, cid, proc['slots'][0]['card']['cvts'][0]['id']


def _xd(client):
    st = client.post('/api/processors', json={'deviceId': 'brompton-sx40'})
    assert st.status_code == 201, st.get_data(as_text=True)
    proc = st.get_json()['processors'][-1]
    return proc['id'], proc['slots'][0]['card']['cvts'][0]['id']


def _refusals(client):
    """Every length refusal the audit named, from a show in its unit."""
    pid, cid, bid = _h9_with_card_and_box(client)
    sx, xd = _xd(client)
    asks = {
        'box fiber': client.put(f'/api/processors/{pid}/cvts/{bid}',
                                json={'fiberFt': 'ten'}),
        'copper link': client.put(f'/api/processors/{sx}/cvts/{xd}/fiber-links/p1',
                                  json={'copper': 'Cat6', 'ft': 'ten'}),
        'port cable': client.put(f'/api/processors/{pid}/cards/{cid}',
                                 json={'portCables': {'3': {'ft': 'ten'}}}),
        'snake': client.post('/api/snakes', json={'ft': 'ten'}),
        'fiber cable': client.post('/api/fiber-cables',
                                   json={'kind': 'tac', 'strands': 12, 'ft': 'ten'}),
    }
    out = {}
    for name, r in asks.items():
        assert r.status_code == 400, (name, r.get_data(as_text=True))
        out[name] = r.get_json()['error']
    return out


def test_a_meters_show_is_told_its_lengths_are_meters(client):
    """The refusals said "a number of feet" whatever the show's unit."""
    app_module.current_project['cableUnit'] = 'm'
    errors = _refusals(client)
    for name, text in errors.items():
        assert 'meters' in text and 'feet' not in text, (name, text)


def test_a_feet_show_is_still_told_feet(client):
    app_module.current_project['cableUnit'] = 'ft'
    errors = _refusals(client)
    for name, text in errors.items():
        assert 'feet' in text and 'meters' not in text, (name, text)


def test_the_snake_home_run_tip_does_not_say_feet():
    path = os.path.join(os.path.dirname(__file__), '..', 'src', 'static', 'js',
                        'quickstart.js')
    src = open(path, encoding='utf-8').read()
    m = re.search(r"place: 'top', title: 'The snake&rsquo;s home run',\s*body: '([^']*)'", src)
    assert m, 'the snake home run step is gone'
    assert 'feet' not in m.group(1), m.group(1)


# ══════════════════════════════════════════════════════════════════════════
# The browser
# ══════════════════════════════════════════════════════════════════════════

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    pg.wait_for_function("() => window.app && window.app.project && window.canvasRenderer")
    yield pg, errors
    context.close()


# Screens from specs (name, columns, rows, panel_weight, weight_unit,
# locked, group), the project replaced on the server; the app takes the
# server's project and selects `select` (names). Waits on the saves.
SEED_JS = """async ({specs, select}) => {
    const app = window.app;
    await app._layerSavesSettled();
    const j = async (method, url, body) => (await fetch(url, {
        method, headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body) })).json();
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments;
    await j('PUT', '/api/project', proj);
    let x = 0;
    for (const s of specs) {
        await j('POST', '/api/layer/add', { name: s.name, columns: s.columns, rows: s.rows,
            cabinet_width: 128, cabinet_height: 128, offset_x: x,
            panel_weight: s.weight, weight_unit: s.unit });
        x += s.columns * 128 + 128;
    }
    const p = await j('GET', '/api/project');
    const groups = {};
    for (const s of specs) {
        const l = p.layers.find(q => q.name === s.name);
        Object.assign(l, { processorType: 'brompton', bitDepth: 10, frameRate: 60,
                           locked: !!s.locked });
        if (s.group) {
            l.group_id = s.group;
            (groups[s.group] = groups[s.group] || []).push(l.id);
        }
    }
    p.groups = Object.entries(groups).map(([id, ids]) => ({ id, name: 'Wall ' + id, layer_ids: ids }));
    await j('PUT', '/api/project', p);
    app.project = await j('GET', '/api/project');
    if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
    app.resetHistory('Test Reset');
    const ids = select.map(n => app.project.layers.find(l => l.name === n).id);
    app.setSelectedLayersByIds(ids, ids[0]);
    return ids;
}"""

# Pick a weight unit in Screen Info the way a person does, then wait for
# the app's own PUTs to land; returns the server's layers and the names
# the locked-screen error said.
PICK_UNIT_JS = """async (unit) => {
    const app = window.app;
    const said = [];
    const original = app._showLockedError;
    app._showLockedError = function (layers) {
        (layers || []).forEach(l => said.push(l.name));
        return original.apply(this, arguments);
    };
    try {
        const sel = document.getElementById('panel-weight-unit');
        sel.value = unit;
        sel.dispatchEvent(new Event('change', { bubbles: true }));
    } finally {
        app._showLockedError = original;
    }
    await app._layerSavesSettled();
    const p = await (await fetch('/api/project')).json();
    return {
        said,
        server: Object.fromEntries(p.layers.map(l => [l.name,
            { weight: l.panel_weight, unit: l.weight_unit }])),
        client: Object.fromEntries(app.project.layers.map(l => [l.name,
            { weight: l.panel_weight, unit: l.weight_unit }])),
        field: document.getElementById('panel-weight-kg').value,
    };
}"""


def _seed(pg, specs, select):
    return pg.evaluate(SEED_JS, {'specs': specs, 'select': select})


def _group_total_kg(pg):
    return pg.evaluate("""() => {
        const app = window.app;
        const g = app.project.groups[0];
        return app.getGroupTotals(g).weightKg;
    }""")


# ── 1. a group member's weight unit ───────────────────────────────────────

def test_a_unit_picked_on_one_member_leaves_the_peers_figure_alone(page):
    """Two members at 45.19 lb a cabinet; kg picked on one. The peer keeps
    45.19 lb (it read "45.19 kg", on the server too) and the wall weighs
    what it did (it went from 901.9 to 1,445.2 kg in the audit's show)."""
    pg, errors = page
    _seed(pg, [
        {'name': 'WALL A', 'columns': 4, 'rows': 5, 'weight': 45.19, 'unit': 'lb', 'group': 'g1'},
        {'name': 'WALL B', 'columns': 4, 'rows': 6, 'weight': 45.19, 'unit': 'lb', 'group': 'g1'},
    ], ['WALL A'])
    before = _group_total_kg(pg)
    assert before == pytest.approx(44 * 45.19 / 2.20462, abs=0.01)
    out = pg.evaluate(PICK_UNIT_JS, 'kg')
    # the edited member is converted, its own number
    assert out['server']['WALL A'] == {'weight': 20.5, 'unit': 'kg'}, out
    # the peer is exactly as it was, on the server and in the page
    assert out['server']['WALL B'] == {'weight': 45.19, 'unit': 'lb'}, out
    assert out['client']['WALL B'] == {'weight': 45.19, 'unit': 'lb'}, out
    # the wall's total is the same wall (to the edited member's rounding)
    assert _group_total_kg(pg) == pytest.approx(before, abs=0.1)
    assert 'weight_unit' not in pg.evaluate("window.app.GROUP_SHARED_LAYER_FIELDS")
    assert errors == []


def test_the_group_row_reads_kg_when_the_members_units_differ(page):
    """Mixed units on a wall still give one figure: the row converts each
    member and says kg - the total, not one member's number relabelled."""
    pg, _errors = page
    _seed(pg, [
        {'name': 'WALL A', 'columns': 4, 'rows': 5, 'weight': 20.5, 'unit': 'kg', 'group': 'g1'},
        {'name': 'WALL B', 'columns': 4, 'rows': 6, 'weight': 45.19, 'unit': 'lb', 'group': 'g1'},
    ], ['WALL A'])
    line = pg.evaluate("() => window.app.formatGroupTotalsLine(window.app.project.groups[0])")
    # 20 x 20.5 + 24 x 45.19 / 2.20462 = 410 + 491.95 = 902 kg
    assert line == '2 screens · 44 cab · 902 kg', line


# ── 2. several screens selected ───────────────────────────────────────────

def test_a_unit_change_converts_each_selected_screens_own_weight(page):
    """28.66 lb and 29.98 lb selected together, kg picked: 13.00 and
    13.60 kg - not 13 kg for both. A locked screen in the selection keeps
    its 50 lb and is named."""
    pg, errors = page
    _seed(pg, [
        {'name': 'S1', 'columns': 2, 'rows': 2, 'weight': 28.66, 'unit': 'lb'},
        {'name': 'S2', 'columns': 2, 'rows': 2, 'weight': 29.98, 'unit': 'lb'},
        {'name': 'S3', 'columns': 2, 'rows': 2, 'weight': 50, 'unit': 'lb', 'locked': True},
    ], ['S1', 'S2', 'S3'])
    # the weights differ, so Screen Info shows no one weight
    assert pg.evaluate("document.getElementById('panel-weight-kg').value") == ''
    out = pg.evaluate(PICK_UNIT_JS, 'kg')
    assert out['server']['S1'] == {'weight': 13.0, 'unit': 'kg'}, out
    assert out['server']['S2'] == {'weight': 13.6, 'unit': 'kg'}, out
    assert out['server']['S3'] == {'weight': 50, 'unit': 'lb'}, out
    assert out['client']['S3'] == {'weight': 50, 'unit': 'lb'}, out
    assert 'S3' in out['said'], out
    assert errors == []


def test_a_unit_change_on_one_screen_converts_it_and_back(page):
    """The single-screen case still converts the screen and the field."""
    pg, _errors = page
    _seed(pg, [{'name': 'S1', 'columns': 2, 'rows': 2, 'weight': 20, 'unit': 'kg'}], ['S1'])
    out = pg.evaluate(PICK_UNIT_JS, 'lb')
    assert out['server']['S1'] == {'weight': 44.09, 'unit': 'lb'}, out
    assert float(out['field']) == 44.09
    out = pg.evaluate(PICK_UNIT_JS, 'kg')
    assert out['server']['S1'] == {'weight': 20, 'unit': 'kg'}, out


# ── the canvas labels (3, 4, 5): a synthetic project, every drawn string ──

CANVAS_JS = """(o) => {
    const app = window.app;
    const r = window.canvasRenderer;
    const screen = (s) => {
        const l = Object.assign({
            id: 1, name: 'S', type: 'screen', visible: true, canvas_id: 'c1',
            columns: 1, rows: 1, cabinet_width: 128, cabinet_height: 128,
            panel_width_mm: 500, panel_height_mm: 500, offset_x: 0, offset_y: 0,
            panel_weight: 20, weight_unit: 'kg', panelWatts: 200, powerVoltage: 208,
            powerAmperage: 20, processorType: 'brompton', bitDepth: 8, frameRate: 60,
            color1: { r: 64, g: 70, b: 128 }, color2: { r: 149, g: 156, b: 184 },
            show_numbers: false, rotation: 0, flowPattern: 'tl-h',
            portMappingMode: 'organized', powerFlowPattern: 'tl-h',
            showLabelName: false, showLabelSizePx: false, showLabelSizeM: false,
            showLabelSizeFt: false, showLabelWeight: false, showLabelInfo: false,
        }, s);
        l.panels = [];
        for (let y = 0; y < l.rows; y++) for (let x = 0; x < l.columns; x++) {
            l.panels.push({ id: y * l.columns + x + 1, number: y * l.columns + x + 1,
                row: y, col: x, x: l.offset_x + x * l.cabinet_width,
                y: l.offset_y + y * l.cabinet_height, width: l.cabinet_width,
                height: l.cabinet_height, hidden: false, blank: false, halfTile: 'none',
                is_color1: (x + y) % 2 === 0 });
        }
        return l;
    };
    const layers = o.layers.map(screen);
    const saved = { project: app.project, currentLayer: app.currentLayer,
                    selectedLayerIds: app.selectedLayerIds, viewMode: r.viewMode,
                    zoom: r.zoom, panX: r.panX, panY: r.panY,
                    updateLayers: app.updateLayers, renderLayers: app.renderLayers,
                    loadLayerToInputs: app.loadLayerToInputs };
    app.updateLayers = () => {}; app.renderLayers = () => {}; app.loadLayerToInputs = () => {};
    app.project = { layers, groups: o.groups || [], active_canvas_id: 'c1', cableUnit: 'ft',
        canvases: [{ id: 'c1', name: 'Canvas 1', workspace_x: 0, workspace_y: 0,
            show_workspace_x: 0, show_workspace_y: 0, raster_width: 8192, raster_height: 8192,
            show_raster_width: 8192, show_raster_height: 8192, color: '#ff0000', visible: true }] };
    app.currentLayer = null; app.selectedLayerIds = new Set();
    r.viewMode = 'pixel-map'; r.zoom = 1; r.panX = 0; r.panY = 0;
    const ctx = r.ctx;
    const fill = ctx.fillText;
    const texts = [];
    ctx.fillText = function (t, x, y, w) { texts.push(String(t)); return fill.call(ctx, t, x, y, w); };
    let extra = null;
    try {
        r.render();
        if (o.groupLine) extra = app.formatGroupTotalsLine(app.project.groups[0]);
    } finally {
        ctx.fillText = fill;
        Object.assign(app, { project: saved.project, currentLayer: saved.currentLayer,
            selectedLayerIds: saved.selectedLayerIds, updateLayers: saved.updateLayers,
            renderLayers: saved.renderLayers, loadLayerToInputs: saved.loadLayerToInputs });
        Object.assign(r, { viewMode: saved.viewMode, zoom: saved.zoom, panX: saved.panX, panY: saved.panY });
        r.render();
    }
    return { texts, extra };
}"""


def _size_label(pg, width_mm, height_mm, fractions):
    # one cabinet wide enough that the line is drawn whole, not wrapped
    out = pg.evaluate(CANVAS_JS, {'layers': [{
        'cabinet_width': 3000, 'cabinet_height': 1500,
        'panel_width_mm': width_mm, 'panel_height_mm': height_mm,
        'showLabelSizeFt': True, 'useFractionalInches': fractions}]})
    lines = [t for t in out['texts'] if t.startswith('W ') and "'" in t]
    assert len(lines) == 1, out['texts']
    return lines[0]


@pytest.mark.parametrize('width, height, want', [
    # 3,200 mm = 125.98" -> 126" = 10' 6" (it printed 10' 51")
    (3200, 500, 'W 10\' 6" X H 1\' 7 11/16"'),
    # 4,800 x 17,500 mm = 188.98" x 688.98" (it printed 15' 81" X 57' 41")
    (4800, 17500, 'W 15\' 9" X H 57\' 5"'),
    # 3,657.4 mm = 143.99" -> 144" = 12' 0" (it printed 11' 111")
    (3657.4, 304.8, 'W 12\' 0" X H 1\' 0"'),
    # 6,400 mm = 251.97" is 251 15/16" to the sixteenth - no carry
    (6400, 304.8, 'W 20\' 11 15/16" X H 1\' 0"'),
    # an ordinary fraction is untouched: 500 mm = 19.685" -> 1' 7 11/16"
    (500, 660.4, 'W 1\' 7 11/16" X H 2\' 2"'),
])
def test_the_feet_and_fractions_label_carries_the_inch_and_the_foot(page, width, height, want):
    pg, _errors = page
    assert _size_label(pg, width, height, True) == want


@pytest.mark.parametrize('width, height, want', [
    # 6,400 mm = 251.97" -> 252.0" = 21' 0.0" (it printed 20' 12.0")
    (6400, 500, 'W 21\' 0.0" X H 1\' 7.7"'),
    (3200, 304.8, 'W 10\' 6.0" X H 1\' 0.0"'),
    (1000, 2000, 'W 3\' 3.4" X H 6\' 6.7"'),
])
def test_the_feet_and_decimal_inches_label_never_prints_12_inches(page, width, height, want):
    pg, _errors = page
    assert _size_label(pg, width, height, False) == want


def test_the_canvas_weight_label_has_thousands_separators(page):
    """It printed "Weight 156788.9 kg / 345660.0 lb"."""
    pg, _errors = page
    out = pg.evaluate(CANVAS_JS, {'layers': [{
        'columns': 10, 'rows': 10, 'cabinet_width': 400, 'cabinet_height': 300,
        'panel_weight': 1567.889,
        'showLabelWeight': True, 'showLabelInfo': True}]})
    kg = 100 * 1567.889
    want = f'{kg:,.1f} kg / {kg * 2.20462:,.1f} lb'
    assert want == '156,788.9 kg / 345,659.9 lb'
    assert f'Weight {want}' in out['texts'], out['texts']
    info = ' '.join(out['texts'])
    assert f'Weight: {want}' in info, out['texts']


def test_the_group_row_says_one_screen_not_one_screens(page):
    """A group with one counted member (its peer hidden) reads "1 screen";
    the counts carry separators."""
    pg, _errors = page
    out = pg.evaluate(CANVAS_JS, {
        'layers': [
            {'id': 1, 'name': 'A', 'columns': 40, 'rows': 30, 'group_id': 'g1'},
            {'id': 2, 'name': 'B', 'columns': 2, 'rows': 2, 'offset_x': 6000,
             'group_id': 'g1', 'visible': False},
        ],
        'groups': [{'id': 'g1', 'name': 'Wall', 'layer_ids': [1, 2]}],
        'groupLine': True})
    assert out['extra'] == '1 screen · 1,200 cab · 24,000 kg', out['extra']


# ── 5. the binder's numbers and pull quantities ───────────────────────────

BINDER_JS = """() => {
    const app = window.app;
    const tables = [];
    const original = app._bTableLines;
    const subject = app._bSubjectRows;
    const pullBlock = app._bPullBlock;
    app._bTableLines = function (book, spec) { tables.push(spec); return []; };
    // the pull sheet lays each section out through _bPullBlock (2026-10-18)
    app._bPullBlock = function (book, spec) { tables.push(spec); return { lines: [], w: 0, h: 0 }; };
    app._bSubjectRows = () => [{ type: 'Data Jump', length: "2'", qty: 1517 }];
    const row = { type: 'Data Jump', length: "2'", qty: 1517, label: 'X', side: 'data' };
    try {
        app._bCableTable(null, {}, 'data');
        app._bPullLines(null, 'Pull', [row]);
        app._bPullBlocks({}, { rows: [row] }, []);
    } catch (e) {
        // the blocks after the cable tables need a real book; the tables
        // the rows were handed to are already recorded
    } finally {
        app._bTableLines = original;
        app._bSubjectRows = subject;
        app._bPullBlock = pullBlock;
    }
    const qtys = tables.map(t => t.rows.map(r => r.cells).filter(c => c.includes('Data Jump'))
        .map(c => c[c.indexOf('Data Jump') + 2])).flat();
    return {
        qtys,
        nums: [app._bNum(1724.4, 1), app._bNum(1724.44, 1), app._bNum(1517, 0),
               app._bNum(12.5, 1), app._bNum(-1234.56, 2), app._bNum(NaN, 1)],
    };
}"""


def test_the_binder_numbers_and_pull_quantities_have_separators(page):
    """_bNum added commas only with no decimals ("1724.4 A 1φ"), and the
    pull quantities printed "1517"."""
    pg, _errors = page
    out = pg.evaluate(BINDER_JS)
    assert out['nums'] == ['1,724.4', '1,724.4', '1,517', '12.5', '-1,234.56', '—'], out
    # the cables-this-screen table, the pull lines and the pull blocks
    assert out['qtys'] == ['1,517', '1,517', '1,517'], out


# ── 6. the copper limits in a feet show ───────────────────────────────────

COPPER_JS = """() => {
    const app = window.app;
    const unit = app.project.cableUnit;
    try {
        app.project.cableUnit = 'ft';
        const ft = [
            app.copperOverText({ copper: 'Cat5e', ft: 98.4 }),
            app.copperOverText({ copper: 'Cat5e', ft: 98.5 }),
            app.copperOverText({ copper: 'Cat6A', ft: 196.8 }),
            app.copperOverText({ copper: 'Cat6A', ft: 197 }),
            app.copperOverText({ copper: 'Cat6', ft: 100 }),
            app.copperOverText({ copper: 'Cat6', ft: 101 }),
        ];
        app.project.cableUnit = 'm';
        const m = [
            app.copperOverText({ copper: 'Cat5e', ft: 30 }),
            app.copperOverText({ copper: 'Cat6', ft: 31 }),
        ];
        return { ft, m };
    } finally {
        app.project.cableUnit = unit;
    }
}"""


def test_a_98_4_ft_cat5e_run_is_within_its_limit(page):
    pg, _errors = page
    out = pg.evaluate(COPPER_JS)
    assert out['ft'] == ['', 'Cat5e runs 98.4 ft max at 10G',
                         '', 'Cat6A runs 196.8 ft max at 10G',
                         '', 'Cat6 runs 100 ft max at 10G'], out
    assert out['m'] == ['', 'Cat6 runs 30.48 m max at 10G'], out
    js = pg.evaluate("() => import('/static/js/app-fiber.js').then(m => m.COPPER_LINK_KINDS)")
    assert [tuple(k) for k in js] == list(catalog.COPPER_LINK_KINDS)


# ── 7. cableFigure ────────────────────────────────────────────────────────

def test_no_length_prints_nothing_and_a_tiny_one_prints_its_figure(page):
    pg, _errors = page
    out = pg.evaluate("""() => {
        const app = window.app;
        return [app.cableFigure(null), app.cableFigure(undefined), app.cableFigure(''),
                app.cableFigure('  '), app.cableFigure(0.04, 'ft'), app.cableFigure(0.004, 'm'),
                app.cableFigure(12.34, 'ft'), app.cableFigure(7.625, 'm'), app.cableFigure(25, 'ft'),
                app.cableFigure(0, 'ft'), app.cableLengthText(0.04, 'ft'),
                app.cableLengthText(0.004, 'm'), app.cableLengthWords(null, 'ft')];
    }""")
    assert out == ['', '', '', '', '0.04', '0.004', '12.3', '7.63', '25', '0',
                   "0.04'", '0.004 m', ''], out
