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
    figures.
  * A screen with no panel name saved on it has no panel row (owner,
    2026-11-05: "most will use a panel type and be auto named. when it is
    not names we can leave the panel type off."): never a model guessed
    from its size, pixels and weight, never its size, an older show
    included. A show with no named panel has no Panels block at all.
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


# QUARTZ: the library's ROE Black Quartz 3.9 Full Tile saved on the screen
# (500 x 1000 mm, 128 x 256 px, 22 kg), 4 x 3, its last row half tiles
# halved in height (the library's Half Tile), one cabinet halved in width
# (no library match: "<name> half" with its size), one blank and one hidden
# cabinet. WALL-A (3 x 2) and WALL-B (2 x 2) are a group of 500 x 500 mm
# cabinets named by hand, WALL-B with one half tile; FLOOR (2 x 1) the same
# cabinet on its own; GHOST a hidden screen. BARE names no panel, and its
# cabinet has figures only one library model matches: 500 x 500 mm,
# 256 x 256 px, 6.3 kg, one half tile.
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
                   panel_weight: 20, weight_unit: 'kg', powerVoltage: 208, powerAmperage: 20, panelWatts: 100,
                   panelModelName: 'House tile'};
    await add({name: 'QUARTZ', columns: 4, rows: 3, cabinet_width: 128, cabinet_height: 256,
               panel_width_mm: 500, panel_height_mm: 1000, panel_weight: 22, weight_unit: 'kg',
               halfLastRow: true, powerVoltage: 208, powerAmperage: 20, panelWatts: 100,
               panelModelId: 'ROE|Black Quartz 3.9 Full Tile', panelModelName: 'ROE Black Quartz 3.9 Full Tile',
               panelModelHalves: {height: 'ROE Black Quartz 3.9 Half Tile', width: null}});
    await add({name: 'WALL-A', columns: 3, rows: 2, ...plain});
    await add({name: 'WALL-B', columns: 2, rows: 2, ...plain});
    await add({name: 'FLOOR', columns: 2, rows: 1, ...plain});
    await add({name: 'GHOST', columns: 2, rows: 2, ...plain});
    await add({name: 'BARE', columns: 2, rows: 2, cabinet_width: 256, cabinet_height: 256,
               panel_width_mm: 500, panel_height_mm: 500, panel_weight: 6.3, weight_unit: 'kg',
               powerVoltage: 208, powerAmperage: 20, panelWatts: 100});
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
    at(L('BARE'), 1, 1).halfTile = 'height';
    await app._ensurePanelCatalogData();
    app.renderLayers();
    app.resetHistory('Pull Panels Seed');
    return {quartz: L('QUARTZ').id, a: L('WALL-A').id, b: L('WALL-B').id, floor: L('FLOOR').id,
            ghost: L('GHOST').id, bare: L('BARE').id,
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
PLAIN = 'House tile'
PLAIN_HALF = 'House tile half'
# What an unnamed cabinet printed before 2026-11-05.
SIZE_ROW = '500 × 500 mm panel'
SIZE_HALF_ROW = '500 × 250 mm half panel'


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
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
    assert sorted(by) == ['BARE', 'FLOOR', 'QUARTZ', 'SR Beach'], sorted(by)
    # 12 cabinets: 4 half tiles (height), 1 halved in width, 1 blank and
    # 1 hidden - 5 full ones hang
    assert _panels(by['QUARTZ']['rows']) == [
        (FULL, 'EA', 5, 'QUARTZ', ''),
        (SIDE_HALF, 'EA', 1, 'QUARTZ', ''),
        (HALF, 'EA', 4, 'QUARTZ', ''),
    ]
    # the group: both members' cabinets of one type on one row, the
    # screens in the label; WALL-B's half tile its own row
    assert _panels(by['SR Beach']['rows']) == [
        (PLAIN, 'EA', 9, 'WALL-A, WALL-B', ''),
        (PLAIN_HALF, 'EA', 1, 'WALL-B', ''),
    ]
    assert _panels(by['FLOOR']['rows']) == [(PLAIN, 'EA', 2, 'FLOOR', '')]
    # TOTALS add them up across the show
    assert _panels(out['totals']) == [
        (PLAIN, 'EA', 11, 'WALL-A, WALL-B, FLOOR', ''),
        (PLAIN_HALF, 'EA', 1, 'WALL-B', ''),
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
                                          cabinet_height: 256, panel_weight: 9.2, weight_unit: 'kg',
                                          panelModelId: 'ROE|Ruby 1.9B V2', panelModelName: 'ROE Ruby 1.9B V2',
                                          panelModelHalves: {height: null, width: null}}),
                typed: app.pullPanelTypes({panel_width_mm: 600, panel_height_mm: 337.5, cabinet_width: 192,
                                           cabinet_height: 108, panel_weight: 9, weight_unit: 'kg',
                                           panelModelName: 'Long tile'})};
    }""", ids)
    assert got['quartz'] == {'none': FULL, 'height': HALF, 'width': SIDE_HALF}, got['quartz']
    assert got['wall'] == {'none': PLAIN, 'height': PLAIN_HALF, 'width': PLAIN_HALF}, got['wall']
    # a square library model with no half in the library: "<name> half",
    # one row whichever way it is halved
    assert got['ruby'] == {'none': 'ROE Ruby 1.9B V2', 'height': 'ROE Ruby 1.9B V2 half',
                           'width': 'ROE Ruby 1.9B V2 half'}, got['ruby']
    # a cabinet named by hand, not square: its halves differ - in mm in
    # this feet show
    assert got['typed'] == {'none': 'Long tile', 'height': 'Long tile half (600 × 168.8 mm)',
                            'width': 'Long tile half (300 × 337.5 mm)'}, got['typed']


def test_a_halfs_size_is_mm_in_a_feet_show_and_a_meters_one(seeded):
    """The owner, 2026-10-22: a size on a panel row is always mm."""
    pg, ids, _ = seeded
    assert pg.evaluate("() => window.app.cableUnit()") == 'ft'
    feet = pg.evaluate(LIST_JS)
    assert (SIDE_HALF, 'EA', 1, 'QUARTZ', '') in _panels(
        next(p for p in feet['positions'] if p['name'] == 'QUARTZ')['rows'])
    got = pg.evaluate("""(ids) => {
        const app = window.app;
        const was = app.project.cableUnit;
        app.project.cableUnit = 'm';
        try {
            app._circuitTailCache = null;
            const list = JSON.parse(JSON.stringify(app.buildPullList()));
            return list.positions.find(p => p.name === 'QUARTZ').rows;
        } finally {
            if (was === undefined) delete app.project.cableUnit; else app.project.cableUnit = was;
        }
    }""", ids)
    assert (SIDE_HALF, 'EA', 1, 'QUARTZ', '') in _panels(got)


# ── a screen with no panel name (owner, 2026-11-05) ───────────────────────

# A model of the library's that BARE's figures match, read off the library
# so no brand is spelled here: what the old guess printed.
GUESSED_JS = """(id) => {
    const app = window.app;
    const l = app.project.layers.find(x => x.id === id);
    const hits = app._panelCatalogFlat.filter(p => p.width_mm === l.panel_width_mm
        && p.height_mm === l.panel_height_mm && p.pixels_w === l.cabinet_width
        && p.pixels_h === l.cabinet_height && Math.abs(p.weight_kg - l.panel_weight) <= 0.006);
    return hits.map(p => app._catalogModelLabel(p._mfr, p));
}"""


def test_a_screen_with_no_panel_name_is_never_named_by_a_guess(seeded):
    """The friend's show: 500 x 500 mm, 256 x 256 px, 6.3 kg with no panel
    picked printed the one library model those figures match. Nothing
    prints now: no model, no size, full or half, on the positions, the
    totals or the edited sheet."""
    pg, ids, errors = seeded
    guessed = pg.evaluate(GUESSED_JS, ids['bare'])
    assert len(guessed) == 1, guessed
    got = pg.evaluate("""(id) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === id);
        return { types: app.pullPanelTypes(l), counts: app.pullPanelCounts(l),
                 names: [...app._pullPanelTypeNames()] };
    }""", ids['bare'])
    assert got['types'] == {'none': '', 'height': '', 'width': ''}, got
    assert got['counts'] == [], got
    # what pullGuessSide reads as a panel holds no blank and no guess
    assert '' not in got['names'] and guessed[0].lower() not in got['names'], got
    assert {n.lower() for n in (FULL, HALF, SIDE_HALF, PLAIN, PLAIN_HALF)} <= set(got['names']), got
    for read in (LIST_JS, SHEET_JS):
        out = pg.evaluate(read)
        bare = next(p for p in out['positions'] if p['name'] == 'BARE')
        assert _panels(bare['rows']) == [], bare['rows']
        labels = ' '.join(r['label'] for r in out['totals'] if r.get('side') == 'panel')
        assert 'BARE' not in labels, out['totals']
        types = [r['type'] for r in out['totals']] + [r['type'] for p in out['positions'] for r in p['rows']]
        assert guessed[0] not in types and not any(' mm panel' in t or ' mm half panel' in t for t in types), types
    assert errors == []


def test_an_older_show_is_treated_the_same(seeded):
    """A screen saved before panels were stored has none of the keys."""
    pg, ids, _ = seeded
    got = pg.evaluate("""(id) => {
        const app = window.app;
        const l = { ...app.project.layers.find(x => x.id === id) };
        delete l.panelModelId; delete l.panelModelName; delete l.panelModelHalves;
        const blank = { ...l, panelModelName: '   ' };
        return { old: app.pullPanelTypes(l), counts: app.pullPanelCounts(l),
                 blank: app.pullPanelCounts(blank), nothing: app.pullPanelTypes(null) };
    }""", ids['bare'])
    empty = {'none': '', 'height': '', 'width': ''}
    assert got == {'old': empty, 'counts': [], 'blank': [], 'nothing': empty}, got


def test_a_group_lists_only_its_named_members(seeded):
    """A name forgotten on one member of a group takes that member's
    cabinets and its label off the row, the other member's stay."""
    pg, ids, _ = seeded
    rows = pg.evaluate("""(ids) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === ids.b);
        const was = l.panelModelName;
        l.panelModelName = null;
        try {
            app._circuitTailCache = null;
            return JSON.parse(JSON.stringify(app.buildPullList())).positions
                .find(p => p.name === 'SR Beach').rows;
        } finally { l.panelModelName = was; }
    }""", ids)
    assert _panels(rows) == [(PLAIN, 'EA', 6, 'WALL-A', '')], rows


def _strip_names(pg):
    """Every screen on the page with no panel name; returns the undo."""
    pg.evaluate("""() => {
        const app = window.app;
        app._savedPanelNames = app.project.layers.map(l => [l, l.panelModelName]);
        app.project.layers.forEach(l => { l.panelModelName = null; });
        app._circuitTailCache = null;
    }""")


def _restore_names(pg):
    pg.evaluate("""() => {
        const app = window.app;
        app._savedPanelNames.forEach(([l, name]) => { l.panelModelName = name; });
        delete app._savedPanelNames;
        app._circuitTailCache = null;
    }""")


def test_a_show_with_no_named_panels_has_no_panels_block_anywhere(seeded, e2e_server):
    """No side-'panel' row in the list, no PANEL table on the binder's pull
    pages (the heading "PANELS" that stays is the SCREENS table's column),
    and nothing panel on the workbook."""
    pg, _, errors = seeded
    import urllib.request
    pages_js = """() => {
        const app = window.app;
        const o = app.readBinderOptions();
        return app.planBinder(o).map((p, i) => ({ title: p.title,
            texts: app.renderBinderPage(o, i, { bitmaps: false }).texts }))
            .filter(p => String(p.title).startsWith('Pull'));
    }"""
    named = [t for p in pg.evaluate(pages_js) for t in p['texts']]
    assert 'PANEL' in named, named
    _strip_names(pg)
    try:
        sheet = pg.evaluate(SHEET_JS)
        pulls = pg.evaluate(pages_js)
    finally:
        _restore_names(pg)
    assert not [r for r in sheet['totals'] if r.get('side') == 'panel'], sheet['totals']
    assert not [r for p in sheet['positions'] for r in p['rows'] if r.get('side') == 'panel']
    flat = [t for p in pulls for t in p['texts']]
    assert pulls and 'PANEL' not in flat, flat
    assert flat.count('PANELS') < named.count('PANELS'), (flat.count('PANELS'), named.count('PANELS'))
    assert not [t for t in flat if ' mm panel' in t or ' mm half panel' in t], flat
    body = json.dumps({'project_name': 'Panels', 'pull_list': sheet}).encode('utf-8')
    req = urllib.request.Request(f'{e2e_server}/api/export/pull-sheet', data=body,
                                 headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req) as r:
        wb = openpyxl.load_workbook(io.BytesIO(r.read()))
    cells = [str(c.value) for ws in (wb['Pull Sheet'], wb['GEAR LIST']) for row in ws.iter_rows() for c in row
             if c.value is not None]
    for gone in (FULL, HALF, PLAIN, SIZE_ROW, SIZE_HALF_ROW):
        assert gone not in cells, gone
    assert errors == []


def test_an_edit_keyed_on_the_old_row_goes_stale_and_prints_nothing(seeded):
    """A show whose sheet was edited while the unnamed screen still printed
    its size or a guess: the row is gone, so the edit is stale - kept and
    shown in the editor, never exported - and it brings no row back."""
    pg, ids, _ = seeded
    guessed = pg.evaluate(GUESSED_JS, ids['bare'])[0]
    got = pg.evaluate("""([size, half, guess]) => {
        const app = window.app;
        const engine = app.buildPullList();
        const bare = engine.positions.find(p => p.name === 'BARE');
        const key = app.pullPositionKey(bare);
        app.project.pullSheetEdits = { positions: { [key]: {
            rows: [{ key: `${size}|EA`, qty: 12, notes: 'one spare' }, { key: `${guess}|EA`, qty: 9 },
                   { key: `${half}|EA`, removed: true }], added: [] } } };
        app._circuitTailCache = null;
        const sheet = JSON.parse(JSON.stringify(app.buildPullSheet()));
        const stale = app.pullSheetStaleEdits(engine).map(s => s.key).sort();
        return { rows: sheet.positions.find(p => p.name === 'BARE').rows, stale,
                 totals: sheet.totals.map(r => r.type) };
    }""", [SIZE_ROW, SIZE_HALF_ROW, guessed])
    assert _panels(got['rows']) == [], got
    for gone in (SIZE_ROW, SIZE_HALF_ROW, guessed):
        assert gone not in got['totals'], got['totals']
    assert got['stale'] == sorted(f'{t}|EA' for t in (SIZE_ROW, SIZE_HALF_ROW, guessed)), got


def test_a_free_row_keeps_its_side_when_the_screen_is_unnamed(seeded):
    """A row somebody typed is theirs: an added row spelled like the old
    size row stays on the sheet, on the panel side, by its words."""
    pg, ids, _ = seeded
    got = pg.evaluate("""([size]) => {
        const app = window.app;
        const engine = app.buildPullList();
        const bare = engine.positions.find(p => p.name === 'BARE');
        app.project.pullSheetEdits = { positions: { [app.pullPositionKey(bare)]: {
            rows: [], added: [{ type: size, length: 'EA', qty: 2, label: '', notes: '' }] } } };
        app._circuitTailCache = null;
        return JSON.parse(JSON.stringify(app.buildPullSheet())).positions.find(p => p.name === 'BARE').rows;
    }""", [SIZE_ROW])
    assert _panels(got) == [(SIZE_ROW, 'EA', 2, '', '')], got


def test_the_panel_fields_tooltip_says_the_row_is_left_off():
    path = os.path.join(HERE, '..', 'src', 'templates', 'index.html')
    with open(path, encoding='utf-8') as f:
        html = f.read()
    assert "the library's name for its size" not in html
    assert 'A screen with no name here has no panel row on the pull sheet.' in html


def test_the_guess_and_its_wait_are_gone_and_the_half_lookups_stay(seeded):
    pg, ids, _ = seeded
    got = pg.evaluate("""(id) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === id);
        return { names: typeof app.catalogPanelNames, ready: typeof app.pullPanelCatalogReady,
                 kg: app.catalogHalfWeightKg(l, 'height'), watts: typeof app.catalogHalfWattsRatio };
    }""", ids['quartz'])
    assert got['names'] == 'undefined' and got['ready'] == 'undefined', got
    assert got['watts'] == 'function' and got['kg'] > 0, got


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
    assert _panels(by['SR Beach']['rows'])[0] == (PLAIN, 'EA', 12, 'WALL-A, WALL-B', '')
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
    the GEAR LIST's Gear column."""
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
    # models match, no one half - no panel row, 0.65 of the weight (the
    # caller's) and half the watts
    o = got['old']
    assert o['types'] == {'none': '', 'height': '', 'width': ''}, o
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
    # a hand change of the cabinet's mm forgets it all; the field is then
    # blank, its placeholder too: nothing names the panel, so no row prints
    got = pg.evaluate(SCREEN_INFO_JS, [air, 'panel-width-mm', '600'])
    assert (got['id'], got['name'], got['halves'], got['shown']) == (None, None, None, ''), got
    assert got['placeholder'] == '', got
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
