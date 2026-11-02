"""Panel counts on the pull sheet (owner, 2026-10-22: "we need to have the
pull sheet include panel counts").

  * One row per panel type a screen hangs, EA, under the screen's own
    position and labelled with its name; TOTALS add them up across the
    show. Two screens of one type on one position (a group's members)
    merge into one row, "WALL-A, WALL-B".
  * The type is the panel SAVED on the screen ("It has to be saved to the
    screen considering we derive the half tiles the same way"): a pick
    from the panel library writes its model, its name and its halves'
    names onto the screen, and they ride the server, the file, a reload
    and a copy. Screen Info's Panel field names a custom panel; a hand
    change of the cabinet's pixels or mm forgets the saved panel.
  * A half tile is a row of its own, and its name, watts and weight read
    the saved model first - even where other library models share its
    figures. A show saved before is named by the library where its size
    and weight find one model; a cabinet nothing names is its size, always
    in mm ("500 × 500 mm panel"), in a feet show too.
  * A half with no library match is "<name> half"; a square cabinet's two
    halves are one cabinet turned, any other's are told apart by their
    sizes.
  * Blank and hidden cabinets, and hidden screens, count none.
  * The rows are side 'panel': on the pull sheet, its TOTALS, the xlsx,
    the GEAR LIST and the binder's pull pages (a Panels block), never on a
    screen's CABLES THIS SCREEN table or a hardware pull list. A pull-sheet
    edit (hide, count) works on them like any other row.

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_pull_panels.py -v --browser chromium
"""

import io
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
sys.path.insert(0, HERE)

openpyxl = pytest.importorskip('openpyxl', reason='openpyxl not installed')
pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# QUARTZ: the library's ROE Black Quartz 3.9 Full Tile (500 x 1000 mm,
# 128 x 256 px, 22 kg - no other model has those figures), 4 x 3, its last
# row half tiles halved in height (the library's Half Tile), one cabinet
# halved in width (no library match: "<name> half" with its size), one
# blank and one hidden cabinet. WALL-A (3 x 2) and WALL-B (2 x 2) are a
# group of 500 x 500 mm cabinets the library cannot name, WALL-B with one
# half tile; FLOOR (2 x 1) the same cabinet on its own; GHOST a hidden
# screen.
SEED_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.pullSheetEdits;
    delete proj.cableUnit; delete proj.beaches;
    await j('PUT', '/api/project', proj);
    const add = (body) => j('POST', '/api/layer/add', body);
    const plain = {cabinet_width: 128, cabinet_height: 128, panel_width_mm: 500, panel_height_mm: 500,
                   panel_weight: 20, weight_unit: 'kg', powerVoltage: 208, powerAmperage: 20, panelWatts: 100};
    await add({name: 'QUARTZ', columns: 4, rows: 3, cabinet_width: 128, cabinet_height: 256,
               panel_width_mm: 500, panel_height_mm: 1000, panel_weight: 22, weight_unit: 'kg',
               halfLastRow: true, powerVoltage: 208, powerAmperage: 20, panelWatts: 100});
    await add({name: 'WALL-A', columns: 3, rows: 2, ...plain});
    await add({name: 'WALL-B', columns: 2, rows: 2, ...plain});
    await add({name: 'FLOOR', columns: 2, rows: 1, ...plain});
    await add({name: 'GHOST', columns: 2, rows: 2, ...plain});
    let p = await j('GET', '/api/project');
    const byName = (n) => p.layers.find(l => l.name === n);
    p.groups = [{id: 'g1', name: 'SR Beach', layer_ids: [byName('WALL-A').id, byName('WALL-B').id]}];
    byName('GHOST').visible = false;
    await j('PUT', '/api/project', p);
    p = await j('GET', '/api/project');
    app.project = p;
    app.dedupeProjectLayers('pull_panels_setup');
    const L = (n) => app.project.layers.find(l => l.name === n);
    const at = (l, r, c) => l.panels.find(x => x.row === r && x.col === c);
    at(L('QUARTZ'), 0, 3).halfTile = 'width';
    at(L('QUARTZ'), 0, 0).blank = true;
    at(L('QUARTZ'), 1, 0).hidden = true;
    at(L('WALL-B'), 1, 1).halfTile = 'height';
    await app.pullPanelCatalogReady();
    app.renderLayers();
    app.resetHistory('Pull Panels Seed');
    return {quartz: L('QUARTZ').id, a: L('WALL-A').id, b: L('WALL-B').id, floor: L('FLOOR').id,
            ghost: L('GHOST').id,
            halves: L('QUARTZ').panels.filter(x => x.halfTile === 'height').length};
}"""

LIST_JS = """() => {
    const app = window.app;
    app._circuitTailCache = null;
    return JSON.parse(JSON.stringify(app.buildPullList()));
}"""

SHEET_JS = """() => {
    const app = window.app;
    app._circuitTailCache = null;
    return JSON.parse(JSON.stringify(app.buildPullSheet()));
}"""

FULL = 'ROE Black Quartz 3.9 Full Tile'
HALF = 'ROE Black Quartz 3.9 Half Tile'
SIDE_HALF = 'ROE Black Quartz 3.9 Full Tile half (250 × 1000 mm)'
PLAIN = '500 × 500 mm panel'
PLAIN_HALF = '500 × 250 mm half panel'


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
    pg.wait_for_timeout(1500)
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(800)
    assert ids['halves'] == 4, f'fixture: QUARTZ\'s last row is half tiles: {ids}'
    yield pg, ids, errors
    context.close()


def _clear_edits(pg):
    pg.evaluate("""async () => {
        const app = window.app;
        delete app.project.pullSheetEdits;
        await fetch('/api/project', {method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({pullSheetEdits: {positions: {}}})});
    }""")


@pytest.fixture()
def seeded(page):
    """The seeded page with no pull-sheet edits after the test."""
    yield page
    _clear_edits(page[0])


def _panels(rows):
    return [(r['type'], r['length'], r['qty'], r['label'], r['notes'])
            for r in rows if r.get('side') == 'panel']


def test_each_screen_counts_its_panels_by_type_under_its_own_position(seeded):
    pg, ids, errors = seeded
    out = pg.evaluate(LIST_JS)
    by = {p['name']: p for p in out['positions']}
    # GHOST is hidden: no position, no panels
    assert sorted(by) == ['FLOOR', 'QUARTZ', 'SR Beach'], sorted(by)
    # 12 cabinets: 4 half tiles (height), 1 halved in width, 1 blank and
    # 1 hidden - 5 full ones hang
    assert _panels(by['QUARTZ']['rows']) == [
        (FULL, 'EA', 5, 'QUARTZ', ''),
        (SIDE_HALF, 'EA', 1, 'QUARTZ', ''),
        (HALF, 'EA', 4, 'QUARTZ', ''),
    ]
    # the group: both members' cabinets of one type on one row, the
    # screens in the label; WALL-B's half tile its own row
    # (the sheet's natural sort: 250 before 500)
    assert _panels(by['SR Beach']['rows']) == [
        (PLAIN_HALF, 'EA', 1, 'WALL-B', ''),
        (PLAIN, 'EA', 9, 'WALL-A, WALL-B', ''),
    ]
    assert _panels(by['FLOOR']['rows']) == [(PLAIN, 'EA', 2, 'FLOOR', '')]
    # TOTALS add them up across the show
    assert _panels(out['totals']) == [
        (PLAIN_HALF, 'EA', 1, 'WALL-B', ''),
        (PLAIN, 'EA', 11, 'WALL-A, WALL-B, FLOOR', ''),
        (FULL, 'EA', 5, 'QUARTZ', ''),
        (SIDE_HALF, 'EA', 1, 'QUARTZ', ''),
        (HALF, 'EA', 4, 'QUARTZ', ''),
    ]
    # the screens' own readings (CABLES THIS SCREEN) and the hardware pull
    # lists carry no panel row
    for scr in out['byScreen'].values():
        assert not [r for r in scr['rows'] + scr['rowsOn'] if r.get('side') == 'panel'], scr['name']
    for h in out['hardware']:
        assert not [r for r in h['rows'] if r.get('side') == 'panel'], h['name']
    assert errors == []


def test_a_square_cabinets_halves_are_one_type_and_the_library_names_its_half(seeded):
    pg, ids, _ = seeded
    got = pg.evaluate("""(ids) => {
        const app = window.app;
        const L = (id) => app.project.layers.find(l => l.id === id);
        return {quartz: app.pullPanelTypes(L(ids.quartz)), wall: app.pullPanelTypes(L(ids.a)),
                ruby: app.pullPanelTypes({panel_width_mm: 500, panel_height_mm: 500, cabinet_width: 256,
                                          cabinet_height: 256, panel_weight: 9.2, weight_unit: 'kg'}),
                bp2: app.pullPanelTypes({panel_width_mm: 500, panel_height_mm: 500, cabinet_width: 176,
                                         cabinet_height: 176, panel_weight: 9.35, weight_unit: 'kg'}),
                typed: app.pullPanelTypes({panel_width_mm: 600, panel_height_mm: 337.5, cabinet_width: 192,
                                           cabinet_height: 108, panel_weight: 9, weight_unit: 'kg'})};
    }""", ids)
    assert got['quartz'] == {'none': FULL, 'height': HALF, 'width': SIDE_HALF}, got['quartz']
    assert got['wall'] == {'none': PLAIN, 'height': PLAIN_HALF, 'width': PLAIN_HALF}, got['wall']
    # a square library model with no half in the library: "<name> half",
    # one row whichever way it is halved
    assert got['ruby'] == {'none': 'ROE Ruby 1.9B V2', 'height': 'ROE Ruby 1.9B V2 half',
                           'width': 'ROE Ruby 1.9B V2 half'}, got['ruby']
    # figures four library models share (BP2, BP2V2, ...) name none of them
    assert got['bp2'] == {'none': PLAIN, 'height': PLAIN_HALF, 'width': PLAIN_HALF}, got['bp2']
    # a cabinet typed by hand, not square: its halves differ - in mm in
    # this feet show
    assert got['typed'] == {'none': '600 × 337.5 mm panel', 'height': '600 × 168.8 mm half panel',
                            'width': '300 × 337.5 mm half panel'}, got['typed']


def test_the_size_is_mm_in_a_feet_show_and_a_meters_one(seeded):
    """The owner, 2026-10-22: the size fallback is always mm."""
    pg, ids, _ = seeded
    assert pg.evaluate("() => window.app.cableUnit()") == 'ft'
    feet = pg.evaluate(LIST_JS)
    assert _panels(next(p for p in feet['positions'] if p['name'] == 'SR Beach')['rows']) == [
        (PLAIN_HALF, 'EA', 1, 'WALL-B', ''),
        (PLAIN, 'EA', 9, 'WALL-A, WALL-B', ''),
    ]
    got = pg.evaluate("""(ids) => {
        const app = window.app;
        const was = app.project.cableUnit;
        app.project.cableUnit = 'm';
        try {
            app._circuitTailCache = null;
            const list = JSON.parse(JSON.stringify(app.buildPullList()));
            return list.positions.find(p => p.name === 'SR Beach').rows;
        } finally {
            if (was === undefined) delete app.project.cableUnit; else app.project.cableUnit = was;
        }
    }""", ids)
    assert _panels(got) == [
        ('500 × 250 mm half panel', 'EA', 1, 'WALL-B', ''),
        ('500 × 500 mm panel', 'EA', 9, 'WALL-A, WALL-B', ''),
    ]


def test_an_edit_on_a_panel_row_reaches_the_sheet_and_its_totals(seeded):
    pg, ids, _ = seeded
    sheet = pg.evaluate("""([ids, plain, half]) => {
        const app = window.app;
        const engine = app.buildPullList();
        const sr = engine.positions.find(p => p.name === 'SR Beach');
        const row = sr.rows.find(r => r.type === plain);
        app.setPullSheetRowEdit(app.pullPositionKey(sr), app.pullRowKey(row), {qty: 12}, row);
        const q = engine.positions.find(p => p.name === 'QUARTZ');
        app.removePullSheetRow(app.pullPositionKey(q), `${half}|EA`);
        app._circuitTailCache = null;
        return JSON.parse(JSON.stringify(app.buildPullSheet()));
    }""", [ids, PLAIN, HALF])
    by = {p['name']: p for p in sheet['positions']}
    assert _panels(by['SR Beach']['rows'])[1] == (PLAIN, 'EA', 12, 'WALL-A, WALL-B', '')
    assert HALF not in [r['type'] for r in by['QUARTZ']['rows']]
    totals = {r['type']: r for r in sheet['totals'] if r.get('side') == 'panel'}
    assert totals[PLAIN]['qty'] == 14 and HALF not in totals, totals
    # the screens' readings are untouched by it
    for scr in sheet['byScreen'].values():
        assert not [r for r in scr['rows'] if r.get('side') == 'panel']
    # the edit is the user's: undo takes it back
    pg.evaluate("() => window.app.undo()")
    pg.evaluate("() => window.app.undo()")
    back = pg.evaluate(SHEET_JS)
    totals = {r['type']: r['qty'] for r in back['totals'] if r.get('side') == 'panel'}
    assert totals[PLAIN] == 11 and totals[HALF] == 4, totals


def test_a_free_row_naming_a_panel_lands_on_the_panel_side(seeded):
    pg, _, _ = seeded
    got = pg.evaluate("""([full, plain]) => {
        const app = window.app;
        return [full, full.toUpperCase(), plain, 'Spare panel', 'Half tile', 'Socapex panel',
                'Cat6 Barrel', 'Shackle'].map(t => app.pullGuessSide(t));
    }""", [FULL, PLAIN])
    assert got == ['panel', 'panel', 'panel', 'panel', 'panel', 'power', 'data', 'power'], got


def test_the_xlsx_and_its_gear_list_carry_the_panel_rows(seeded, e2e_server):
    """The workbook is the edited sheet: the panel rows in their positions'
    blocks with an edit on one, and every written panel type appended to
    the GEAR LIST's Cable Type column."""
    pg, _, _ = seeded
    import urllib.request
    sheet = pg.evaluate("""([plain]) => {
        const app = window.app;
        const engine = app.buildPullList();
        const f = engine.positions.find(p => p.name === 'FLOOR');
        const row = f.rows.find(r => r.type === plain);
        app.setPullSheetRowEdit(app.pullPositionKey(f), app.pullRowKey(row), {qty: 3, notes: 'one spare'}, row);
        app._circuitTailCache = null;
        return JSON.parse(JSON.stringify(app.buildPullSheet()));
    }""", [PLAIN])
    body = json.dumps({'project_name': 'Panels', 'pull_list': sheet}).encode('utf-8')
    req = urllib.request.Request(f'{e2e_server}/api/export/pull-sheet', data=body,
                                 headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req) as r:
        data = r.read()
    wb = openpyxl.load_workbook(io.BytesIO(data))
    ws = wb['Pull Sheet']
    import pull_sheet
    blocks = {}
    for col in pull_sheet.BLOCK_COLS:
        name = ws.cell(5, col).value
        rows = []
        for r in range(7, 67):
            t = ws.cell(r, col).value
            if t is None:
                continue
            rows.append(tuple(ws.cell(r, col + k).value for k in range(5)))
        blocks[name] = rows
    assert (PLAIN, 'EA', 3, 'FLOOR', 'one spare') in blocks['FLOOR'], blocks['FLOOR']
    assert (FULL, 'EA', 5, 'QUARTZ', None) in blocks['QUARTZ'], blocks['QUARTZ']
    assert (HALF, 'EA', 4, 'QUARTZ', None) in blocks['QUARTZ'], blocks['QUARTZ']
    assert (PLAIN, 'EA', 9, 'WALL-A, WALL-B', None) in blocks['SR Beach'], blocks['SR Beach']
    gear = [wb['GEAR LIST'].cell(r, 1).value for r in range(4, 201)]
    for t in (FULL, HALF, SIDE_HALF, PLAIN, PLAIN_HALF):
        assert t in gear, t


def test_the_binder_pull_page_prints_a_panels_block(seeded):
    """The pull pages mirror the pull sheet: a Panels block beside the
    hardware, one row per type with its count and screens."""
    pg, _, errors = seeded
    got = pg.evaluate("""() => {
        const app = window.app;
        const o = app.readBinderOptions();
        const plan = app.planBinder(o);
        return plan.map((p, i) => ({ title: p.title, kind: p.kind,
                                     texts: app.renderBinderPage(o, i, { bitmaps: false }).texts }));
    }""")
    pulls = [p for p in got if str(p['title']).startswith('Pull')]
    assert pulls, [p['title'] for p in got]
    flat = [t for p in pulls for t in p['texts']]
    assert 'PANELS' in flat and 'PANEL' in flat, flat
    assert FULL in flat and HALF in flat and PLAIN in flat, flat
    # the screens' own sheets say nothing of the panel types
    others = [t for p in got if not str(p['title']).startswith('Pull') and 'all positions' not in str(p['title'])
              for t in p['texts']]
    assert FULL not in others and PLAIN not in others
    assert errors == []


# ── the panel saved on the screen (owner, 2026-10-22) ─────────────────────

# KINESIK's AirScreen Pro Curve 3.9 Full Tile: 500 x 1000 mm, 128 x 256 px,
# 11 kg - figures seven other library models share, each with its own half
# or none, so matching them names nothing and finds no half. Saved on the
# screen, its own half (7.5 kg, 125.4 W of its 249.7 W) answers.
AIR_ID = 'KINESIK|AirScreen Pro Curve 3.9 Full Tile'
AIR = 'KINESIK AirScreen Pro Curve 3.9 Full Tile'
AIR_HALF = 'KINESIK AirScreen Pro Curve 3.9 Half Tile'

PICK_JS = """async () => {
    const app = window.app;
    await app._ensurePanelCatalogData();
    const panel = app._panelCatalog.KINESIK.find(p => p.name === 'AirScreen Pro Curve 3.9 Full Tile');
    const before = app.project.layers.length;
    app.addLayer(app._panelToPresetData({ ...panel, _mfr: 'KINESIK' }));
    for (let i = 0; i < 100 && app.project.layers.length === before; i++) await new Promise(r => setTimeout(r, 50));
    // Renamed the way the name field does it - saved through updateLayers.
    // A name set only on the page was lost whenever the add's own save
    // answered after it, since a layer's echo carries the server's name.
    const id = app.project.layers[app.project.layers.length - 1].id;
    const layer = app.project.layers.find(l => l.id === id);
    layer.name = 'AIR';
    app.updateLayers([layer]);
    for (let i = 0; i < 100; i++) {
        const p = await (await fetch('/api/project')).json();
        const s = p.layers.find(l => l.id === id);
        if (s && s.name === 'AIR' && app.project.layers.find(l => l.id === id).name === 'AIR') break;
        await new Promise(r => setTimeout(r, 50));
    }
    await new Promise(r => setTimeout(r, 600));
    return id;
}"""

MODEL_JS = """(id) => {
    const l = window.app.project.layers.find(x => x.id === id);
    return l ? { id: l.panelModelId ?? null, name: l.panelModelName ?? null,
                 halves: l.panelModelHalves ?? null } : null;
}"""

SERVER_MODEL_JS = """async (id) => {
    const p = await (await fetch('/api/project')).json();
    const l = p.layers.find(x => x.id === id);
    return l ? { id: l.panelModelId ?? null, name: l.panelModelName ?? null,
                 halves: l.panelModelHalves ?? null } : null;
}"""

SAVED = {'id': AIR_ID, 'name': AIR, 'halves': {'height': AIR_HALF, 'width': None}}


@pytest.fixture(scope="module")
def picked(page):
    pg, ids, _ = page
    air = pg.evaluate(PICK_JS)
    return pg, ids, air


def test_a_library_pick_saves_the_model_on_the_screen(picked):
    pg, _, air = picked
    assert pg.evaluate(MODEL_JS, air) == SAVED
    # on the server, in the file, and after a reload in a fresh page
    assert pg.evaluate(SERVER_MODEL_JS, air) == SAVED
    saved = pg.evaluate("""(id) => {
        const app = window.app;
        const file = JSON.parse(app.serializeProjectForFile(JSON.parse(JSON.stringify(app.project))));
        const l = file.layers.find(x => x.id === id);
        return { id: l.panelModelId, name: l.panelModelName, halves: l.panelModelHalves };
    }""", air)
    assert saved == SAVED, saved
    fresh = pg.context.new_page()
    try:
        fresh.goto(pg.url, wait_until='domcontentloaded')
        fresh.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
        assert fresh.evaluate(MODEL_JS, air) == SAVED
    finally:
        fresh.close()
    # the pull sheet names it, under its own position
    out = pg.evaluate(LIST_JS)
    assert _panels(next(p for p in out['positions'] if p['name'] == 'AIR')['rows'])[0][0] == AIR


def test_a_copy_hangs_the_same_panel(picked):
    pg, _, air = picked
    copy = pg.evaluate("""async (id) => {
        const app = window.app;
        const before = app.project.layers.length;
        app.duplicateLayer(app.project.layers.find(l => l.id === id));
        for (let i = 0; i < 100 && app.project.layers.length === before; i++) await new Promise(r => setTimeout(r, 50));
        await new Promise(r => setTimeout(r, 400));
        return app.project.layers[app.project.layers.length - 1].id;
    }""", air)
    assert copy != air
    assert pg.evaluate(MODEL_JS, copy) == SAVED
    assert pg.evaluate(SERVER_MODEL_JS, copy) == SAVED
    pg.evaluate("""async (id) => {
        const app = window.app;
        await fetch(`/api/layer/${id}`, { method: 'DELETE' });
        app.project.layers = app.project.layers.filter(l => l.id !== id);
    }""", copy)


def test_the_halves_read_the_saved_model_where_other_models_share_its_figures(picked):
    pg, _, air = picked
    got = pg.evaluate("""(id) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === id);
        const old = { ...l, panelModelId: null, panelModelName: null, panelModelHalves: null };
        const half = { width: 128, height: 128, halfTile: 'height' };
        const read = (x) => ({ types: app.pullPanelTypes(x), kg: app.catalogHalfWeightKg(x, 'height'),
                               watts: app.catalogHalfWattsRatio(x, 'height'),
                               load: app.getPanelLoadFactor(x, half) });
        // BP2V2 saved: four models share its figures, the screen says which
        const bp2v2 = { panel_width_mm: 500, panel_height_mm: 500, cabinet_width: 176, cabinet_height: 176,
                        panel_weight: 9.35, weight_unit: 'kg',
                        panelModelId: 'ROE|Black Pearl BP2V2', panelModelName: 'ROE Black Pearl BP2V2',
                        panelModelHalves: { height: null, width: null } };
        return { saved: read(l), old: read(old), bp2v2: app.pullPanelTypes(bp2v2) };
    }""", air)
    s = got['saved']
    assert s['types'] == {'none': AIR, 'height': AIR_HALF, 'width': f'{AIR} half (250 × 1000 mm)'}, s
    assert s['kg'] == 7.5, s
    assert abs(s['watts'] - 125.4 / 249.7) < 1e-9 and abs(s['load'] - 125.4 / 249.7) < 1e-9, s
    # the same figures with nothing saved (a show saved before): eight
    # models match, no one name and no one half - its size, 0.65 of the
    # weight (the caller's) and half the watts
    o = got['old']
    assert o['types'] == {'none': '500 × 1000 mm panel', 'height': '500 × 500 mm half panel',
                          'width': '250 × 1000 mm half panel'}, o
    assert o['kg'] is None and o['watts'] is None and o['load'] == 0.5, o
    assert got['bp2v2'] == {'none': 'ROE Black Pearl BP2V2', 'height': 'ROE Black Pearl BP2V2 half',
                            'width': 'ROE Black Pearl BP2V2 half'}, got['bp2v2']


SCREEN_INFO_JS = """async ([id, field, value]) => {
    const app = window.app;
    const l = app.project.layers.find(x => x.id === id);
    app.selectLayer(l);
    app.loadLayerToInputs();
    const el = document.getElementById(field);
    el.value = value;
    el.dispatchEvent(new Event('change'));
    await new Promise(r => setTimeout(r, 500));
    return { id: l.panelModelId ?? null, name: l.panelModelName ?? null, halves: l.panelModelHalves ?? null,
             shown: document.getElementById('panel-model-name').value,
             placeholder: document.getElementById('panel-model-name').placeholder };
}"""


def test_screen_info_names_the_panel_and_a_hand_edit_of_its_size_forgets_it(picked):
    pg, _, air = picked
    # Screen Info shows the saved name; a weight edit keeps the panel
    got = pg.evaluate(SCREEN_INFO_JS, [air, 'panel-weight-kg', '12'])
    assert (got['id'], got['name'], got['shown']) == (AIR_ID, AIR, AIR), got
    # a name typed over it names the panel; the library model stays (its
    # halves' weight and watts still read it) and its halves read "<name>
    # half" with their sizes (a cabinet that is not square)
    got = pg.evaluate(SCREEN_INFO_JS, [air, 'panel-model-name', 'Curve wall tile'])
    assert (got['id'], got['name']) == (AIR_ID, 'Curve wall tile'), got
    types = pg.evaluate("(id) => window.app.pullPanelTypes(window.app.project.layers.find(l => l.id === id))", air)
    assert types == {'none': 'Curve wall tile', 'height': 'Curve wall tile half (500 × 500 mm)',
                     'width': 'Curve wall tile half (250 × 1000 mm)'}, types
    # the half follows the 12 kg typed over the library's 11 kg (owner,
    # 2026-10-23): the library's 7.5 / 11 of it
    half = pg.evaluate("(id) => window.app.catalogHalfWeightKg("
                       "window.app.project.layers.find(l => l.id === id), 'height')", air)
    assert abs(half - 7.5 / 11 * 12) < 1e-9, half
    assert pg.evaluate(SERVER_MODEL_JS, air)['name'] == 'Curve wall tile'
    # a hand change of the cabinet's mm forgets it all; the field then
    # shows the size the pull sheet falls back to as its placeholder
    got = pg.evaluate(SCREEN_INFO_JS, [air, 'panel-width-mm', '600'])
    assert (got['id'], got['name'], got['halves'], got['shown']) == (None, None, None, ''), got
    assert got['placeholder'] == '600 × 1000 mm panel', got
    assert pg.evaluate(SERVER_MODEL_JS, air) == {'id': None, 'name': None, 'halves': None}
    # a custom panel named by hand: its name, its halves "<name> half"
    got = pg.evaluate(SCREEN_INFO_JS, [air, 'panel-model-name', 'House tile'])
    assert (got['id'], got['name']) == (None, 'House tile'), got
    # the same for the pixels; clearing the name saves no panel
    got = pg.evaluate(SCREEN_INFO_JS, [air, 'cabinet-width', '120'])
    assert (got['id'], got['name']) == (None, None), got
    pg.evaluate(SCREEN_INFO_JS, [air, 'panel-model-name', 'Again'])
    got = pg.evaluate(SCREEN_INFO_JS, [air, 'panel-model-name', ''])
    assert (got['id'], got['name'], got['halves']) == (None, None, None), got
    # undo walks the name back
    pg.evaluate("() => window.app.undo()")
    assert pg.evaluate(MODEL_JS, air)['name'] == 'Again'


# A cabinet given as bare figures (a preset saved before panels were saved,
# say) names no panel, so the screen keeps none. Until 1.6.0 the picker's
# Preferences default was such a pick; the panel is no preference now.
def test_change_cabinet_saves_the_new_panel_and_bare_figures_save_none(picked):
    pg, ids, _ = picked
    got = pg.evaluate("""async (id) => {
        const app = window.app;
        await app._ensurePanelCatalogData();
        const panel = app._panelCatalog.ROE.find(p => p.name === 'Black Quartz 3.9 Full Tile');
        app.changeCabinetForLayers([id], app._panelToPresetData({ ...panel, _mfr: 'ROE' }));
        const l = app.project.layers.find(x => x.id === id);
        const picked = { id: l.panelModelId, name: l.panelModelName, halves: l.panelModelHalves };
        app.changeCabinetForLayers([id], { cabinet_width: 128, cabinet_height: 128,
            panel_width_mm: 500, panel_height_mm: 500, panel_weight: 20, weight_unit: 'kg' });
        const dflt = { id: l.panelModelId, name: l.panelModelName, halves: l.panelModelHalves };
        return { picked, dflt };
    }""", ids['floor'])
    assert got['picked'] == {'id': 'ROE|Black Quartz 3.9 Full Tile', 'name': FULL,
                             'halves': {'height': HALF, 'width': None}}, got
    assert got['dflt'] == {'id': None, 'name': None, 'halves': None}, got
