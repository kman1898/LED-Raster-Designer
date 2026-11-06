"""Cable stock: the cable lengths a show has on hand, and every length
written out as the stock pieces that make it (app-cable-units.js
breakCableLength / cableStockText, app-cable-stock.js, routes_cable_stock.py).

Owner rulings, 2026-10-20:

  * "if i have 25, 50 and 100 but on cable length on the show file i chose
    125 then it will need to change to 100+25 on the pull sheet or anywhere
    it is written out".
  * Covered: multi home runs, data snakes and port cables (snake home runs,
    loose port cables, extensions), circuit power cables. Not fiber, not the
    cabinet jumpers.
  * The stock lives in the SHOW (project.cableStock), saved, loaded and
    undone with it; a show without one writes every length as typed.
  * One shared list, or a list per kind; feet and meters each their own.
  * Least extra length wins, then the fewest pieces: 125 -> 100+25, 60 ->
    50+25, 130 -> 100+50. Unlimited pieces; an empty list is no breakdown.
  * The typed length stays as typed; it is WRITTEN as the pieces, "100'+25'",
    and the pull sheet counts the pieces.

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_cable_stock.py -v --browser chromium
"""

import base64
import io
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
sys.path.insert(0, HERE)

FEET = {'perKind': False, 'ft': {'all': [25, 50, 100]}, 'm': {'all': [10, 15, 30]}}


# ── the server: presets and a new show ───────────────────────────────────

@pytest.fixture()
def presets_file():
    """A clean presets file for one test, put back after."""
    import routes_cable_stock
    path = routes_cable_stock.CABLE_STOCK_PRESETS_FILE
    before = open(path, encoding='utf-8').read() if os.path.exists(path) else None
    if os.path.exists(path):
        os.remove(path)
    yield path
    if before is None:
        if os.path.exists(path):
            os.remove(path)
    else:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(before)


def test_a_stock_is_cleaned_and_a_junk_one_refused():
    import routes_cable_stock as rcs
    s = rcs.normalize_stock({'perKind': True, 'ft': {'multi': [100, 25, 50, 25.0]},
                             'm': {'all': [7.62]}})
    # a stock saved before the L21-30, Harting, direct-output and feeder
    # lists (2026-10-21) reads the L21-30 and Harting lists from its multi
    # list and the direct-output list from its circuit list
    assert s == {'perKind': True,
                 'ft': {'all': [], 'multi': [25, 50, 100], 'data': [], 'circuit': [],
                        'l2130': [25, 50, 100], 'harting': [25, 50, 100], 'direct': [], 'feeder': [],
                        'fiber': []},
                 'm': {'all': [7.62], 'multi': [], 'data': [], 'circuit': [],
                       'l2130': [], 'harting': [], 'direct': [], 'feeder': [],
                       'fiber': []}}
    # a list present, even empty, is that kind's own
    s = rcs.normalize_stock({'perKind': True, 'ft': {'multi': [50], 'circuit': [10], 'l2130': [],
                                                     'direct': [5], 'feeder': [100]}})
    assert (s['ft']['l2130'], s['ft']['harting'], s['ft']['direct'], s['ft']['feeder']) == ([], [50], [5], [100])
    for junk in (None, [], 'x', {'perKind': 'yes'}, {'ft': {'all': [0]}},
                 {'ft': {'all': ['25']}}, {'ft': {'all': [True]}}, {'ft': [25]},
                 {'m': {'data': [-5]}}, {'ft': {'all': list(range(1, 60))}}):
        assert rcs.normalize_stock(junk) is None, junk


def test_presets_save_list_replace_and_delete(client, presets_file):
    """PUT saves under a name (the same name in any case replaces it), GET
    lists them by name, DELETE removes one; a bad stock or a blank name is
    refused and nothing is written."""
    r = client.put('/api/cable-stock-presets', json={'name': 'Shop  A', 'stock': FEET})
    assert r.status_code == 200
    assert [p['name'] for p in r.get_json()['presets']] == ['Shop A']
    client.put('/api/cable-stock-presets', json={'name': 'Vendor', 'stock': {'ft': {'all': [50]}}})
    r = client.put('/api/cable-stock-presets', json={'name': 'shop a', 'stock': {'ft': {'all': [10]}}})
    got = {p['name']: p['stock']['ft']['all'] for p in r.get_json()['presets']}
    assert got == {'shop a': [10], 'Vendor': [50]}, got
    assert client.put('/api/cable-stock-presets', json={'name': '', 'stock': FEET}).status_code == 400
    assert client.put('/api/cable-stock-presets',
                      json={'name': 'Bad', 'stock': {'ft': {'all': ['x']}}}).status_code == 400
    listed = client.get('/api/cable-stock-presets').get_json()['presets']
    assert [p['name'] for p in listed] == ['shop a', 'Vendor']
    r = client.delete('/api/cable-stock-presets', json={'name': 'VENDOR'})
    assert [p['name'] for p in r.get_json()['presets']] == ['shop a']
    assert client.delete('/api/cable-stock-presets', json={'name': 'Vendor'}).status_code == 404
    with open(presets_file, encoding='utf-8') as f:
        assert [p['name'] for p in json.load(f)['presets']] == ['shop a']


def test_a_damaged_presets_file_is_moved_aside_not_overwritten(client, presets_file):
    os.makedirs(os.path.dirname(presets_file), exist_ok=True)
    with open(presets_file, 'w', encoding='utf-8') as f:
        f.write('{not json')
    assert client.get('/api/cable-stock-presets').get_json()['presets'] == []
    assert client.put('/api/cable-stock-presets', json={'name': 'A', 'stock': FEET}).status_code == 200
    folder = os.path.dirname(presets_file)
    aside = [n for n in os.listdir(folder) if '.corrupt-' in n]
    assert aside, os.listdir(folder)
    for n in aside:
        os.remove(os.path.join(folder, n))


def test_a_preset_saved_with_a_fiber_list_per_mode_opens_with_one(client, presets_file):
    """Owner, 2026-11-05: one Fiber list. A presets file saved with the list
    per mode lists every length of both on it, in feet and in meters; the
    next save writes that preset back on the one list, and an entry this
    app cannot read is left as it came."""
    os.makedirs(os.path.dirname(presets_file), exist_ok=True)
    junk = {'name': 'Junk', 'stock': {'ft': {'fiberSingle': ['x']}}}
    with open(presets_file, 'w', encoding='utf-8') as f:
        json.dump({'presets': [
            {'name': 'Shop', 'stock': {'perKind': True,
                                       'ft': {'all': [100], 'fiberSingle': [500, 250], 'fiberMulti': [300, 250]},
                                       'm': {'fiberMulti': [90]}}},
            junk,
        ]}, f)
    listed = client.get('/api/cable-stock-presets').get_json()['presets']
    assert [p['name'] for p in listed] == ['Shop'], listed
    stock = listed[0]['stock']
    assert (stock['ft']['fiber'], stock['m']['fiber']) == ([250, 300, 500], [90]), stock
    assert not {'fiberSingle', 'fiberMulti'} & (set(stock['ft']) | set(stock['m'])), stock
    assert client.put('/api/cable-stock-presets', json={'name': 'Other', 'stock': FEET}).status_code == 200
    with open(presets_file, encoding='utf-8') as f:
        stored = {p['name']: p['stock'] for p in json.load(f)['presets']}
    assert stored['Shop']['ft'] == {'all': [100], 'fiber': [250, 300, 500]}, stored
    assert stored['Shop']['m'] == {'fiber': [90]}, stored
    assert stored['Junk'] == junk['stock'], stored


def test_two_full_fiber_lists_fold_into_a_preset_that_still_saves(client, presets_file):
    """Two lists at the limit of one are more lengths than one list may
    hold: nothing typed is lost, so the fiber list holds both, and the
    preset can be saved again from the fields it fills."""
    import routes_cable_stock as rcs
    single = list(range(1, rcs.MAX_LENGTHS + 1))
    multi = list(range(1001, 1001 + rcs.MAX_LENGTHS))
    stock = rcs.normalize_stock({'ft': {'fiberSingle': single, 'fiberMulti': multi}})
    assert stock['ft']['fiber'] == single + multi, stock
    r = client.put('/api/cable-stock-presets', json={'name': 'Full', 'stock': stock})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()['presets'][0]['stock']['ft']['fiber'] == single + multi
    # a copper list is held to the limit as ever, and the fiber list to its own
    assert rcs.normalize_stock({'ft': {'all': single + [999]}}) is None
    assert rcs.normalize_stock({'ft': {'fiber': single + multi + [5000]}}) is None


def test_a_default_preset_with_a_fiber_list_per_mode_stamps_one_list(client, presets_file):
    import app as app_module
    import routes_cable_stock as rcs
    os.makedirs(os.path.dirname(presets_file), exist_ok=True)
    with open(presets_file, 'w', encoding='utf-8') as f:
        json.dump({'presets': [{'name': 'Shop', 'stock': {
            'ft': {'fiberSingle': [500], 'fiberMulti': [300]}}}]}, f)
    before = app_module.server_preferences.get('cableStockDefault')
    app_module.server_preferences['cableStockDefault'] = 'Shop'
    try:
        stamped = rcs.default_stock(app_module.server_preferences)
    finally:
        if before is None:
            app_module.server_preferences.pop('cableStockDefault', None)
        else:
            app_module.server_preferences['cableStockDefault'] = before
    assert stamped['ft']['fiber'] == [300, 500], stamped
    assert 'fiberSingle' not in stamped['ft'] and 'fiberMulti' not in stamped['ft'], stamped


def test_a_new_show_starts_with_the_default_preset(client, presets_file):
    """POST /api/project/new stamps the stock of the preset the Preferences
    name as the default. No default, or a default whose preset is gone: the
    show carries no stock, as every show did before."""
    import app as app_module
    client.put('/api/cable-stock-presets', json={'name': 'Shop', 'stock': FEET})
    app_module.server_preferences = {}
    assert 'cableStock' not in client.post('/api/project/new').get_json()
    app_module.server_preferences = {'cableStockDefault': 'shop'}
    p = client.post('/api/project/new').get_json()
    assert p['cableStock']['ft']['all'] == [25, 50, 100] and p['cableStock']['perKind'] is False
    app_module.server_preferences = {'cableStockDefault': 'Gone'}
    assert 'cableStock' not in client.post('/api/project/new').get_json()


def test_the_show_s_stock_rides_save_and_restore(client):
    """The stock is a top-level project key: POST merges it, PUT (undo, a
    file load) restores exactly what it carries - none when it carries
    none."""
    import app as app_module
    client.post('/api/project', json={'cableStock': FEET})
    assert app_module.current_project['cableStock'] == FEET
    proj = client.get('/api/project').get_json()
    proj.pop('cableStock')
    client.put('/api/project', json=proj)
    assert 'cableStock' not in app_module.current_project


OLD_FIBER = {'perKind': True,
             'ft': {'all': [100], 'multi': [25], 'fiberSingle': [500, 250], 'fiberMulti': [300, 250]},
             'm': {'fiberSingle': [150], 'fiberMulti': [150]}}


@pytest.mark.parametrize('how', ['file load or undo', 'save'])
def test_a_show_saved_with_a_fiber_list_per_mode_is_stored_with_one(client, how):
    """Owner, 2026-11-05: a show saved with the two lists opens with one -
    the same lengths kept once, different ones all kept - and the old keys
    are gone from what the server holds, so no save writes them back. The
    other lists are not touched."""
    import copy
    import app as app_module
    stock = copy.deepcopy(OLD_FIBER)
    if how == 'save':
        client.post('/api/project', json={'cableStock': stock})
    else:
        proj = client.get('/api/project').get_json()
        proj['cableStock'] = stock
        reply = client.put('/api/project', json=proj).get_json()
        assert reply['cableStock']['ft']['fiber'] == [250, 300, 500], reply['cableStock']
    want = {'perKind': True,
            'ft': {'all': [100], 'multi': [25], 'fiber': [250, 300, 500]},
            'm': {'fiber': [150]}}
    assert app_module.current_project['cableStock'] == want
    assert client.get('/api/project').get_json()['cableStock'] == want
    # the fold is idempotent, and a stock on the one list is left as it is
    client.post('/api/project', json={'cableStock': want})
    assert app_module.current_project['cableStock'] == want
    client.post('/api/project', json={'cableStock': None})


def test_the_fold_keeps_what_the_client_reads_and_nothing_else():
    """A show's stock is the client's to clean, so a list the client reads
    around a stray value keeps its lengths, a list held to no limit keeps
    them all, and what is not a stock is left alone."""
    import routes_cable_stock as rcs
    stock = {'ft': {'fiberSingle': [500, 'x', None, -1, 0, '250'], 'fiberMulti': 'junk'}, 'm': None}
    assert rcs.fold_fiber_lists(stock) is True
    assert stock == {'ft': {'fiber': [250, 500]}, 'm': None}, stock
    assert rcs.fold_fiber_lists(stock) is False
    for not_a_stock in (None, [], 'x', 5):
        assert rcs.fold_fiber_lists(not_a_stock) is False
    long = {'ft': {'fiberSingle': list(range(1, 200)), 'fiber': [1000]}}
    rcs.fold_fiber_lists(long)
    assert long['ft'] == {'fiber': list(range(1, 200)) + [1000]}, long


# ── the browser ───────────────────────────────────────────────────────────

import openpyxl  # noqa: E402

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_power_cables import SEED_JS as POWER_SEED_JS  # noqa: E402
from test_data_snakes import SEED_JS as DATA_SEED_JS  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project (and the preferences) as found."""


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
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(500)
    yield pg, errors
    context.close()


BREAK_JS = """async ([cases]) => {
    const { breakCableLength } = await import('/static/js/app-cable-units.js');
    return cases.map(([n, stock]) => breakCableLength(n, stock));
}"""


def test_the_breakdown_least_extra_then_fewest_pieces(page):
    """The owner's three, then the edges: an exact stock length is itself, a
    length under the shortest takes the shortest, several of one length,
    a tie on extra broken by the fewest pieces, meters to the centimeter,
    and nothing to break (no length, no stock)."""
    pg, errors = page
    s = [25, 50, 100]
    table = [
        ((125, s), [100, 25]),
        ((60, s), [50, 25]),
        ((130, s), [100, 50]),
        ((100, s), [100]),
        ((10, s), [25]),
        ((25, s), [25]),
        ((26, s), [50]),
        ((175, s), [100, 50, 25]),
        ((300, s), [100, 100, 100]),
        ((240, s), [100, 100, 50]),
        ((0.5, s), [25]),
        # a tie on extra (both 150): two pieces beat four
        ((150, [25, 50, 100]), [100, 50]),
        # 7.62 m: 2 x 3.81 is exact
        ((7.62, [3.81, 10]), [3.81, 3.81]),
        ((12, [5, 7.5]), [7.5, 5]),
        ((20, [7.5, 15]), [15, 7.5]),
        # one length only: as many as it takes
        ((310, [100]), [100, 100, 100, 100]),
        # unsorted, repeated stock
        ((60, [50, 25, 25, 100]), [50, 25]),
        ((0, s), None),
        ((-5, s), None),
        ((125, []), None),
        ((125, None), None),
    ]
    got = pg.evaluate(BREAK_JS, [[list(c) for c, _ in table]])
    assert got == [w for _, w in table], [(c, g, w) for (c, w), g in zip(table, got) if g != w]
    assert errors == [], errors


TEXT_JS = """([stock, unit, cases]) => {
    const app = window.app;
    const keep = app.project.cableStock, keepUnit = app.project.cableUnit;
    app.project.cableStock = stock;
    app.project.cableUnit = unit;
    try {
        return cases.map(([n, kind]) => app.cableStockText(n, kind));
    } finally {
        app.project.cableStock = keep;
        app.project.cableUnit = keepUnit;
    }
}"""


def test_one_formatter_writes_the_pieces(page):
    """cableStockText: the pieces joined by + in the show's unit ("100'+25'",
    "30 m+10 m"), the length as typed where the stock has nothing to say -
    no stock (an old show), an empty list for that kind, a jumper (no kind)
    or a length nobody typed."""
    pg, errors = page
    cases = [[125, 'multi'], [60, 'data'], [130, 'circuit'], [100, 'multi'], ['125', 'multi'],
             [125, None], [125, 'fiber'], ['', 'multi'], [0, 'multi']]
    assert pg.evaluate(TEXT_JS, [FEET, 'ft', cases]) == [
        "100'+25'", "50'+25'", "100'+50'", "100'", "100'+25'", "125'", "125'", '', '']
    # a show with no stock - every file saved before the setting
    assert pg.evaluate(TEXT_JS, [None, 'ft', cases[:3]]) == ["125'", "60'", "130'"]
    # meters reads the meters list
    assert pg.evaluate(TEXT_JS, [FEET, 'm', [[40, 'multi'], [36, 'data'], [30, 'circuit']]]) == [
        '30 m+10 m', '30 m+10 m', '30 m']
    # a list per kind: each kind its own, an empty one writes as typed
    per = {'perKind': True, 'ft': {'all': [25, 50, 100], 'multi': [50, 100], 'data': [25, 50],
                                   'circuit': []}}
    assert pg.evaluate(TEXT_JS, [per, 'ft', [[125, 'multi'], [125, 'data'], [125, 'circuit']]]) == [
        "100'+50'", "50'+50'+25'", "125'"]
    assert errors == [], errors


def _power_seed(pg, stock):
    """WALL on SR box 1 (test_power_cables): multi 1's home run 125,
    circuit 1 a 60 cable and circuit 2 a 25 one, the show's stock `stock`."""
    ids = pg.evaluate(POWER_SEED_JS)
    pg.wait_for_timeout(500)
    pg.evaluate("""async (stock) => {
        const app = window.app;
        const wall = app.project.layers[0];
        app.setSocaLength(wall, 1, '125', false);
        app.setCircuitCable(wall, 1, {ft: 60}, false);
        app.setCircuitCable(wall, 2, {ft: 25}, false);
        app.updateLayers([wall]);
        app.project.cableUnit = 'ft';
        app.project.cableStock = stock;
        delete app.project.pullSheetEdits;
        await fetch('/api/project', {method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({cableUnit: 'ft', cableStock: stock, pullSheetEdits: null})});
        app._circuitTailCache = null;
        app.resetHistory('Stock Seed');
        app.renderHardwareDock();
    }""", stock)
    pg.wait_for_timeout(500)
    return ids


PULL_ROWS_JS = """() => {
    const app = window.app;
    app._circuitTailCache = null;
    const list = app.buildPullSheet();
    return {
        rows: list.positions.flatMap(p => p.rows).map(r => [r.type, r.length, r.qty, r.label]),
        totals: list.totals.map(r => [r.type, r.length, r.qty]),
        hardware: list.hardware.flatMap(h => h.rows).map(r => [r.type, r.length, r.qty]),
    };
}"""

TAG_TEXTS_JS = """(exportMode) => {
    const app = window.app, r = window.canvasRenderer, ctx = r.ctx;
    const l = app.project.layers[0];
    const brackets = l.showSocaBrackets;
    l.showPowerCableTags = true;
    l.showSocaBrackets = true;
    const oT = ctx.fillText, texts = [];
    ctx.fillText = function (t, x, y, w) { texts.push(String(t)); return oT.call(ctx, t, x, y, w); };
    const prev = r.viewMode, prevExport = r.exportMode;
    try { r.viewMode = 'power'; r.exportMode = exportMode; r.render(); }
    finally { ctx.fillText = oT; r.viewMode = prev; r.exportMode = prevExport; }
    l.showPowerCableTags = false;
    l.showSocaBrackets = brackets;
    r.render();
    return texts;
}"""


def test_power_lengths_are_written_as_pieces_everywhere(page):
    """With 25 / 50 / 100 on hand: multi 1's typed 125 home run and circuit
    1's 60 cable are written 100'+25' and 50'+25' TRUE1 - the chip, the map
    tag, the exported map's bracket, the pull sheet (which counts the
    pieces: a 100' and a 25' Multi, a 50' and two 25' TRUE1 with circuit
    2's own 25), the workbook, the binder - while the multi's own field
    still holds 125."""
    pg, errors = page
    ids = _power_seed(pg, FEET)
    cable = pg.evaluate("([id]) => window.app.powerCircuitCable(window.app.project.layers.find(l => l.id === id), 1)",
                        [ids['id']])
    assert cable['text'] == "50'+25' TRUE1" and cable['ft'] == 60, cable

    pull = pg.evaluate(PULL_ROWS_JS)
    multis = sorted((r[1], r[2]) for r in pull['totals'] if r[0] == 'Multi')
    assert multis == [("100'", 1), ("25'", 1)], pull['totals']
    tru = sorted((r[1], r[2]) for r in pull['totals'] if r[0] == 'TRUE1')
    assert tru == [("25'", 2), ("50'", 1)], pull['totals']
    assert not [r for r in pull['rows'] if '+' in str(r[1])], 'the sheet lists pieces, never sums'
    # a power multi joins without a barrel (2026-10-21), and a TRUE1
    # cable without a coupler - a female mates with a male
    assert not [r for r in pull['totals'] if 'Barrel' in r[0]], pull['totals']
    assert not [r for r in pull['totals'] if 'Coupler' in r[0]], pull['totals']
    # the pieces keep the row's label
    assert ['Multi', "100'", 1, 'SR1'] in pull['rows'] and ['Multi', "25'", 1, 'SR1'] in pull['rows'], pull['rows']
    # the distro's hardware rows count the same pieces
    assert sorted((r[1], r[2]) for r in pull['hardware'] if r[0] == 'Multi') == [("100'", 1), ("25'", 1)]

    tags = pg.evaluate(TAG_TEXTS_JS, False)
    # a tag too wide for its disc wraps under its length (test_cable_tag_wrap)
    assert "50'+25' TRUE1" in ' '.join(tags) and "25' TRUE1" in tags, tags
    exported = pg.evaluate(TAG_TEXTS_JS, True)
    assert any("SR1 · 100'+25'" in t for t in exported), [t for t in exported if 'SR1' in t]

    # the workbook: the piece rows, and the GEAR LIST takes them
    b64 = pg.evaluate("""async () => {
        const list = window.app.buildPullSheet();
        const resp = await fetch('/api/export/pull-sheet', {method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({pull_list: list, project_name: 'Stock', engineer: '', rev: '1.0',
                                  date: '', date_iso: ''})});
        const bytes = new Uint8Array(await resp.arrayBuffer());
        let bin = ''; for (let i = 0; i < bytes.length; i += 0x8000)
            bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
        return btoa(bin);
    }""")
    wb = openpyxl.load_workbook(io.BytesIO(base64.b64decode(b64)))
    import pull_sheet
    ws = wb['Pull Sheet']
    col = pull_sheet.BLOCK_COLS[0]
    block = [tuple(ws.cell(r, col + i).value for i in range(4)) for r in range(7, 40)]
    assert ('Multi', "100'", 1, 'SR1') in block and ('Multi', "25'", 1, 'SR1') in block, block
    assert ('TRUE1', "50'", 1) in [b[:3] for b in block], block
    assert not [b for b in block if b[1] and '+' in str(b[1])], block

    # the binder's power sheet: the circuits table and the multi's band
    texts = pg.evaluate("""() => {
        const app = window.app;
        const opts = { sheet: 'tabloid', palette: 'colour', sides: {power: true, data: false},
                       scope: {kind: 'show'}, cover: false, pull: true, hardware: true, titleBlock: true };
        const plan = app.planBinder(opts);
        const out = [];
        plan.forEach((p, i) => { out.push(...app.renderBinderPage(opts, i).texts); });
        return out;
    }""")
    assert "50'+25' TRUE1" in texts, [t for t in texts if 'TRUE1' in t]
    assert any("100'+25'" in t and 'SR1' in t for t in texts), [t for t in texts if 'SR1' in t]
    assert not [t for t in texts if "125'" in t or "60' TRUE1" in t], [t for t in texts if "125'" in t]

    # the tray: the multi's field keeps what was typed, its tooltip says how
    # it is pulled; the circuit's sheet field the same
    dock = pg.evaluate("""([id, distroId]) => {
        const app = window.app;
        const f = document.querySelector(`[data-lrd-field="power-soca-length-${id}-1"]`);
        app._setCableSheetOpen(distroId, 1, true);
        app.renderHardwareDock();
        const c = document.querySelector(`[data-lrd-field="power-cable-ft-${id}-1"]`);
        const out = { value: f && f.value, title: f && f.title, cvalue: c && c.value, ctitle: c && c.title };
        app._setCableSheetOpen(distroId, 1, false);
        app.renderHardwareDock();
        return out;
    }""", [ids['id'], ids['distroId']])
    assert dock['value'] == '125' and "Pulled as 100'+25' from this show's cable stock." in dock['title'], dock
    assert dock['cvalue'] == '60' and "Pulled as 50'+25'" in dock['ctitle'], dock
    assert errors == [], errors


def test_a_powercon_join_takes_a_coupler(page):
    """A powerCON cable the stock splits is joined by one "powerCON
    Coupler" EA per join, under the cable's label (owner, 2026-10-21):
    circuit 1's 60 is 50'+25' - one join, one coupler; circuit 2's 25 is
    one piece - none; the multi's 100'+25' joins with nothing."""
    pg, errors = page
    ids = _power_seed(pg, FEET)
    pg.evaluate("""() => {
        const app = window.app;
        const wall = app.project.layers[0];
        app.setCircuitCable(wall, 1, {ft: 60, connector: 'powercon'}, false);
        app.setCircuitCable(wall, 2, {ft: 25, connector: 'powercon'}, false);
        app.updateLayers([wall]);
        app._circuitTailCache = null;
    }""")
    pull = pg.evaluate(PULL_ROWS_JS)
    label = pg.evaluate("([id]) => window.app.getPowerCircuitLabel(window.app.project.layers.find(l => l.id === id), 1)",
                        [ids['id']])
    assert sorted((r[1], r[2]) for r in pull['totals'] if r[0] == 'powerCON') == [("25'", 2), ("50'", 1)], pull['totals']
    assert [r for r in pull['totals'] if 'Coupler' in r[0]] == [['powerCON Coupler', 'EA', 1]], pull['totals']
    assert ['powerCON Coupler', 'EA', 1, label] in pull['rows'], pull['rows']
    assert not [r for r in pull['totals'] if 'Barrel' in r[0]], pull['totals']
    assert errors == [], errors


def test_an_old_show_without_a_stock_reads_as_before(page):
    """No cableStock (a file saved before the setting) or an emptied one:
    every length as typed, one row each, exactly as before."""
    pg, errors = page
    for stock in (None, {'perKind': False, 'ft': {'all': []}, 'm': {'all': []}}):
        ids = _power_seed(pg, stock)
        pull = pg.evaluate(PULL_ROWS_JS)
        assert sorted((r[1], r[2]) for r in pull['totals'] if r[0] == 'Multi') == [("125'", 1)], pull
        assert sorted((r[1], r[2]) for r in pull['totals'] if r[0] == 'TRUE1') == [("25'", 1), ("60'", 1)]
        cable = pg.evaluate("([id]) => window.app.powerCircuitCable(window.app.project.layers.find(l => l.id === id), 1).text",
                            [ids['id']])
        assert cable == "60' TRUE1"
    assert errors == [], errors


def test_setting_the_stock_is_one_undo_step_the_server_holds(page):
    """setCableStock: one 'Set Cable Stock' entry, the server holds the new
    stock, the papers follow; undo puts the old one back on both sides, and
    redo again. An unchanged stock records nothing."""
    pg, errors = page
    _power_seed(pg, None)
    st = pg.evaluate("""async (stock) => {
        const app = window.app;
        const n0 = app.history.length;
        const changed = app.setCableStock(stock);
        const again = app.setCableStock(stock);
        await app._pullSheetStateSettled();
        const served = (await (await fetch('/api/project')).json()).cableStock;
        return { changed, again, steps: app.history.length - n0,
                 action: app.history[app.historyIndex].action, served,
                 text: app.cableStockText(125, 'multi') };
    }""", FEET)
    assert st['changed'] is True and st['again'] is False and st['steps'] == 1, st
    assert st['action'] == 'Set Cable Stock' and st['text'] == "100'+25'", st
    assert st['served']['ft']['all'] == [25, 50, 100], st
    undone = pg.evaluate("""async () => {
        const app = window.app;
        app.undo();
        await new Promise(r => setTimeout(r, 600));
        const served = (await (await fetch('/api/project')).json()).cableStock;
        return { stock: app.cableStock(), served: served === undefined ? null : served,
                 text: app.cableStockText(125, 'multi') };
    }""")
    assert undone['stock'] is None and not undone['served'] and undone['text'] == "125'", undone
    redone = pg.evaluate("""async () => {
        const app = window.app;
        app.redo();
        await new Promise(r => setTimeout(r, 600));
        return { text: app.cableStockText(125, 'multi'),
                 served: (await (await fetch('/api/project')).json()).cableStock };
    }""")
    assert redone['text'] == "100'+25'" and redone['served']['ft']['all'] == [25, 50, 100], redone
    assert errors == [], errors


def test_data_lengths_are_written_as_pieces_everywhere(page):
    """Data: a snake's 130 home run is "100'+50'" on its tag and run text,
    a snaked port's 60 extension "+50'+25'", a loose port's 125 cable
    "100'+25'" on its chip corner and map tag; the pull sheet counts the
    pieces, and the binder's run cells say the same."""
    pg, errors = page
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(400)
    ids = pg.evaluate(DATA_SEED_JS)
    pg.wait_for_timeout(800)
    out = pg.evaluate("""async ([ids, stock]) => {
        const app = window.app;
        app.project.cableStock = stock;
        app.project.cableUnit = 'ft';
        await fetch('/api/project', {method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({cableStock: stock, cableUnit: 'ft'})});
        const box = () => app._dataCableOwner('cvt', ids.boxId);
        await app.snakePorts(app.snakeMembersOf(box(), [2, 3]));
        const snake = app.getShowSnakes()[0];
        await app.setSnake(snake.id, {ft: '130'}, 'Set Snake Home Run');
        await app.setPortCable(box(), 3, {ft: '60', connector: ''});
        await app.setPortCable(box(), 1, {ft: '125', connector: ''});
        app.renderHardwareDock();
        const loose = app.dataPortCable(ids.cardId, 1);
        const snaked = app.dataPortCable(ids.cardId, 3);
        const list = app.buildPullSheet();
        const s = app.getShowSnakes()[0];
        return {
            loose: loose.text, snaked: snaked.text, run: app.runText(snaked),
            tag: app.snakeTagText(s),
            corner: (document.querySelector(`[data-hwdock="port-${ids.boxId}-1"] .hw-dock-chip-cable`)
                     || document.querySelector(`[data-hwdock="port-${ids.cardId}-1"] .hw-dock-chip-cable`) || {}).textContent || null,
            totals: list.totals.map(r => [r.type, r.length, r.qty]),
        };
    }""", [ids, FEET])
    assert out['loose'].startswith("100'+25'"), out
    assert out['snaked'].endswith("+50'+25'"), out
    assert "100'+50'" in out['run'] and out['run'].endswith("+50'+25'"), out
    assert out['tag'].endswith(" · 100'+50'"), out
    lengths = {}
    for t, length, q in out['totals']:
        if length and length != 'EA':
            lengths.setdefault(t, []).append((length, q))
    assert not [r for r in out['totals'] if '+' in str(r[1])], out['totals']
    snake_rows = [v for k, v in lengths.items() if k.endswith('Snake')]
    assert snake_rows and sorted(snake_rows[0]) == [("100'", 1), ("50'", 1)], lengths
    # the loose 125 (100 + 25) and the extension 60 (50 + 25)
    assert sorted(lengths.get('Cat6', [])) == [("100'", 1), ("25'", 1)], lengths
    assert sorted(lengths.get('Cat6 Extension', [])) == [("25'", 1), ("50'", 1)], lengths
    # every stock join takes a barrel (2026-10-21): the loose run's one
    # join, the extension's one, the 2 channel snake's one join per
    # channel (2), plus the extension's own coupler to the fan-out
    barrels = [q for t, length, q in out['totals'] if t == 'Cat6 Barrel' and length == 'EA']
    assert barrels == [5], out['totals']
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(300)
    assert errors == [], errors
