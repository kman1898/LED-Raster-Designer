"""Power cable naming (owner rulings, 2026-10-21).

  * panels take power in on TRUE1 or powerCON only; a TRUE1 / powerCON
    breakout IS the panel input, an Edison or L6-20 screen carries its own
    "Panel input" (layer.powerPanelInput, absent reads TRUE1), shown in the
    Power sidebar only for those breakouts
  * "TRUE1" and "powerCON" on every surface - the pull sheet, the xlsx
    (the template's own "Tru-1" words read TRUE1), the binder, the map
  * one power jumper name per panel input, "TRUE1 Power Jump" and
    "powerCON Power Jump", one row per connector AND length, each link named
    by its cabinet's own screen; an old customised single name carries over
    to TRUE1 only, and edits saved on "Tru-1 ..." rows answer to the TRUE1 row
  * an Edison / L6-20 screen lists one "Edison → TRUE1 cable" per circuit
    (never "tail"; an edit saved on the old "… tail" row answers to it),
    and its splitters are on the panels' side ("TRUE1 2fer")
  * a direct distro output's cable names both ends where the outlet is not
    the panel input ("Edison → powerCON"), the panel input alone where it
    is ("TRUE1"); the length is its own column, and the pull sheet, the map
    tag, the binder's band, caption and Distro page all say the same
  * two screens breaking one multi out to different connectors take one
    breakout row per connector; the binder's band names the connector
  * a blank cabinet on a hand-drawn power run counts no jumper

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_power_naming.py -q --browser chromium
"""

import io
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pull_sheet  # noqa: E402

openpyxl = pytest.importorskip('openpyxl', reason='openpyxl not installed')


# ── the xlsx: the template's words in the app's spelling ──────────────────

def test_the_workbook_and_the_gear_list_spell_true1_the_apps_way():
    data, _ = pull_sheet.build_workbook({'positions': [{'name': 'P', 'rows': [
        {'type': 'TRUE1 Breakout', 'length': 'EA', 'qty': 1, 'label': 'PD 1', 'notes': ''}]}]})
    wb = openpyxl.load_workbook(io.BytesIO(data))
    gear = [wb['GEAR LIST'].cell(r, 1).value for r in range(4, 200) if wb['GEAR LIST'].cell(r, 1).value]
    assert 'TRUE1' in gear and 'TRUE1 2fer' in gear and 'TRUE1 3fer' in gear
    assert gear.count('TRUE1 Breakout') == 1, 'the row written is the template\'s own word now'
    assert not [t for t in gear if 'Tru-1' in t or 'TRU-1' in t], gear
    readme = ' '.join(str(c.value) for row in wb['READ ME'].iter_rows() for c in row if c.value)
    assert 'TRUE1 2fer before TRUE1 3fer' in readme and 'Tru-1' not in readme
    types = pull_sheet.gear_list()['types']
    assert 'TRUE1' in types and not [t for t in types if 'Tru-1' in t or 'TRU-1' in t], types
    assert pull_sheet.true1_spelling('Absen TRU-1 Long Power Jump') == 'Absen TRUE1 Long Power Jump'
    assert pull_sheet.true1_spelling('TRUE1 Breakout') == 'TRUE1 Breakout'


# ── the browser ──────────────────────────────────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


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
    pg.wait_for_function("() => window.app && window.app.project "
                         "&& typeof window.app.distroFace === 'function' && window.canvasRenderer")
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(300)
    # WALL A 10 x 6 and WALL B 6 x 3 beside it, 200 px cabinets
    pg.evaluate("""async () => {
        const app = window.app;
        await app._layerSavesSettled();
        const j = async (method, url, body) => (await fetch(url, {
            method, headers: {'Content-Type': 'application/json'},
            body: body === undefined ? undefined : JSON.stringify(body) })).json();
        const proj = await j('GET', '/api/project');
        proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
        delete proj.port_assignments; delete proj.pullSheet; delete proj.pullSheetEdits;
        await j('PUT', '/api/project', proj);
        await j('POST', '/api/layer/add', { name: 'WALL A', columns: 10, rows: 6,
            cabinet_width: 200, cabinet_height: 200 });
        await j('POST', '/api/layer/add', { name: 'WALL B', columns: 6, rows: 3,
            cabinet_width: 200, cabinet_height: 200, offset_x: 2600 });
        const p = await j('GET', '/api/project');
        app.project = p;
        app.selectLayer(p.layers[0]);
        app.renderLayers();
    }""")
    pg.wait_for_function("() => window.app.project.layers.length === 2")
    yield pg, errors
    context.close()


# Socapex 208 x2 (outputs 1-2), Edison x2 (3-4), TRUE1 x2 (5-6).
DIST = {'id': 'd1', 'name': 'PD', 'ratingA': 200, 'system': '120/208',
        'outputRows': [{'id': 'r1', 'connector': 'soca', 'count': 2, 'coupling': 'll', 'breakerA': 20},
                       {'id': 'r2', 'connector': 'edison', 'count': 2, 'coupling': 'ln', 'breakerA': 20},
                       {'id': 'r3', 'connector': 'true1', 'count': 2, 'coupling': 'll', 'breakerA': 20}]}

SETUP_JS = """(o) => {
    const app = window.app;
    for (const l of app.project.layers) {
        const key = l.name === 'WALL A' ? 'a' : 'b';
        for (const p of l.panels || []) delete p.blank;
        // A US circuit packs to 80 percent of its breaker (2026-10-22): the amps here are x 1.25, so a circuit carries what this wall was laid out for.
        Object.assign(l, { powerVoltage: 208, powerAmperage: 25, panelWatts: 200,
                           powerFlowPattern: 'tl-h', powerCustomPaths: {}, powerCustomIndex: 1,
                           powerSocaDistro: {}, powerSocaNumber: {}, powerSocaPhasePos: {},
                           powerSocaLengths: {}, powerSocaSplits: [], powerSocaNames: {},
                           powerLabelOverrides: {}, powerCircuitCables: {},
                           powerJumpV: 1, powerJumpH: 1, powerPanelInput: undefined,
                           powerBreakoutType: null, locked: false },
                      (o.walls || {})[key] || {});
        app.normalizePowerBreakout(l);
    }
    app.project.distros = (o.distros || []).map(d => JSON.parse(JSON.stringify(d)));
    app.project.cableUnit = 'ft';
    app.project.groups = [];
    delete app.project.pullSheet;
    delete app.project.pullSheetEdits;
    app._circuitTailCache = null;
    app._distroFaceMemo = null;
    app.getDistros();
    const out = {};
    for (const l of app.project.layers) out[l.name] = app.screenCircuits(l).map(c => c.num);
    return out;
}"""

ROWS_JS = """() => window.app.buildPullList().totals.map(r => [r.type, r.length, r.qty, r.label, r.notes])"""


def ev(pg, body, arg=None):
    return pg.evaluate(
        "(arg) => { const app = window.app; "
        "const A = app.project.layers.find(l => l.name === 'WALL A'); "
        "const B = app.project.layers.find(l => l.name === 'WALL B'); "
        f"{body} }}", arg)


def setup(pg, **o):
    pg.wait_for_timeout(300)
    return pg.evaluate(SETUP_JS, o)


def _qty(rows, type_):
    return {r[1]: r[2] for r in rows if r[0] == type_}


def test_the_names_are_true1_and_powercon(page):
    pg, errors = page
    names = ev(pg, """return {
        breakouts: app.getPowerBreakoutTypes().map(t => t.name),
        connectors: app.getPowerCableConnectors().map(c => c.name),
        face: app.distroConnector('true1').name,
        inputs: app.getPanelInputTypes().map(t => t.name) };""")
    assert names['breakouts'][:2] == ['Multi → TRUE1', 'Multi → powerCON'], names
    assert 'L21-30 (3 × 208V) → TRUE1' in names['breakouts']
    assert names['connectors'][:4] == ['TRUE1', 'powerCON', 'Edison', 'L6-20'], names
    # every distro face connector a cable can be typed as
    for word in ('CEE 16A', 'Schuko', 'Stage pin', 'L5-20', 'powerCON XX'):
        assert word in names['connectors'], (word, names)
    assert names['face'] == 'TRUE1' and names['inputs'] == ['TRUE1', 'powerCON']
    html = pg.content()
    assert 'True1' not in pg.locator('#power-breakout-type').inner_text()
    assert 'Tru-1' not in html
    assert errors == [], errors


def test_jumpers_and_breakouts_follow_each_screens_connector(page):
    """WALL A breaks out to TRUE1, WALL B to powerCON, and both share
    output 1 (A's first three circuits, B's three): one Multi, a TRUE1
    Breakout AND a powerCON Breakout on it; each wall's power jumpers under
    its own connector's name, one row per length."""
    pg, errors = page
    # the Socapex on the walls' own 12.5 A: plugged-in circuits pack to the
    # output's breaker (owner, 2026-11-12), so each wall keeps its circuits
    soca = [dict(DIST['outputRows'][0], breakerA=12.5)] + DIST['outputRows'][1:]
    setup(pg, distros=[dict(DIST, outputRows=soca)], walls={
        'a': {'powerBreakoutType': 'soca-true1', 'powerSocaSplits': [3], 'powerAmperage': 12.5,
              'powerSocaDistro': {'1': 'd1', '2': 'd1'}, 'powerSocaNumber': {'1': 1, '2': 2},
              'powerSocaLengths': {'1': '100', '2': '50'}},
        'b': {'powerBreakoutType': 'soca-powercon', 'powerJumpV': 2, 'powerJumpH': 2, 'powerAmperage': 12.5,
              'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1},
              'powerSocaLengths': {'1': '100'}}})
    plan = ev(pg, "return [A, B].map(l => app.getSocaPlan(l).map(s => [s.number, s.legs.length]));")
    assert plan == [[[1, 3], [2, 3]], [[1, 3]]], plan
    rows = pg.evaluate(ROWS_JS)
    assert _qty(rows, 'Multi') == {"50'": 1, "100'": 1}, rows
    assert _qty(rows, 'TRUE1 Breakout') == {'EA': 2}, rows
    assert _qty(rows, 'powerCON Breakout') == {'EA': 1}, rows
    assert set(_qty(rows, 'TRUE1 Power Jump')) == {"1'"}, rows
    assert set(_qty(rows, 'powerCON Power Jump')) == {"2'"}, rows
    # the names are the project's: each connector its own
    ev(pg, "app.project.pullSheet = { powerJumpNamePowercon: 'PC Jumper' }; return null;")
    rows = pg.evaluate(ROWS_JS)
    assert set(_qty(rows, 'PC Jumper')) == {"2'"} and not _qty(rows, 'powerCON Power Jump'), rows
    assert set(_qty(rows, 'TRUE1 Power Jump')) == {"1'"}, rows
    # the binder's band names the breakout's connector
    bands = ev(pg, """const list = app.buildPullList();
        return [A, B].map(l => list.byScreen[l.id].boxes.map(b => app._bBoxTypeText(b)));""")
    # (a face distro names its multi output by the connector, "Socapex 208V")
    assert bands == [['Socapex 208V TRUE1 breakout', 'Socapex 208V TRUE1 breakout'],
                     ['Socapex 208V powerCON breakout']], bands
    assert errors == [], errors


def test_a_grouped_walls_jumpers_take_each_members_connector(page):
    """Two members of one wall with different breakouts: a power jumper
    is named by the panel input of the cabinet's own screen, whichever
    member carries the circuit."""
    pg, errors = page
    setup(pg, walls={'a': {'powerBreakoutType': 'soca-true1'},
                     'b': {'powerBreakoutType': 'soca-powercon', 'powerJumpV': 2, 'powerJumpH': 2}})
    out = ev(pg, """
        app.project.groups = [{ id: 'g1', name: 'WALL', layer_ids: [A.id, B.id] }];
        A.group_id = 'g1'; B.group_id = 'g1';
        app._circuitTailCache = null;
        const list = app.buildPullList();
        const rows = list.positions.flatMap(p => p.rows).filter(r => /Power Jump/.test(r.type))
            .map(r => [r.type, r.length, r.qty, r.label]);
        app.project.groups = []; delete A.group_id; delete B.group_id;
        app._circuitTailCache = null;
        return rows;""")
    assert {r[0] for r in out} == {'TRUE1 Power Jump', 'powerCON Power Jump'}, out
    for type_, length, qty, label in out:
        assert label == ('WALL A' if type_.startswith('TRUE1') else 'WALL B'), out
        if length in ("1'", "2'"):
            assert length == ("1'" if label == 'WALL A' else "2'"), out
    assert errors == [], errors


def test_an_edison_screen_picks_its_panel_input(page):
    """A 120V Edison wall: the Panel input row shows, an adapter cable per circuit,
    TRUE1 jumpers; picked powerCON (one 'Change Panel Input' entry, served)
    the adapter cables, the jumpers and the splitters are powerCON. A TRUE1 wall
    has no Panel input row - its breakout is its input."""
    pg, errors = page
    nums = setup(pg, walls={'b': {'powerVoltage': 120, 'powerAmperage': 12.5,
                                  'powerBreakoutType': 'soca-edison'}})['WALL B']
    assert len(nums) == 3, nums
    rows = pg.evaluate(ROWS_JS)
    # the outlet its 12.5 A Amperage picks, a 5-15 (owner, 2026-11-12)
    assert _qty(rows, 'Edison 5-15 → TRUE1 cable') == {'EA': 3}, rows
    # never "tail" (the owner, 2026-10-21)
    assert not [r for r in rows if re.search(r'\btails?\b', str(r[0]).lower())], rows
    assert _qty(rows, 'TRUE1 Power Jump') and not _qty(rows, 'Edison Power Jump'), rows
    ev(pg, "app.selectLayer(B); app.refreshSocaRuns(); return null;")
    pg.wait_for_timeout(300)
    assert pg.locator('#power-panel-input-row').is_visible()
    assert pg.locator('#power-panel-input').input_value() == 'true1'
    assert pg.locator('#power-panel-input option').all_inner_texts() == ['TRUE1', 'powerCON']
    pg.locator('#power-panel-input').select_option('powercon')
    pg.wait_for_timeout(800)
    st = ev(pg, "return { stored: B.powerPanelInput, action: app.history[app.historyIndex].action };")
    assert st == {'stored': 'powercon', 'action': 'Change Panel Input'}, st
    served = pg.evaluate("""async (id) => ((await (await fetch('/api/project')).json())
        .layers.find(l => l.id === id) || {}).powerPanelInput""", ev(pg, "return B.id;"))
    assert served == 'powercon', served
    rows = pg.evaluate(ROWS_JS)
    assert _qty(rows, 'Edison 5-15 → powerCON cable') == {'EA': 3}         and not _qty(rows, 'Edison 5-15 → TRUE1 cable'), rows
    assert _qty(rows, 'powerCON Power Jump') and not [r for r in rows if r[0] == 'TRUE1 Power Jump'
                                                       and r[3] == 'WALL B'], rows
    # the splitter is on the panels' side
    ev(pg, "B.powerSplitters = { enabled: true, maxWays: 3, manual: { merge: [[1, 2]], split: [] } };"
           " app._circuitTailCache = null; return null;")
    rows = pg.evaluate(ROWS_JS)
    fers = [r[0] for r in rows if r[0].endswith('fer')]
    assert fers and all(f.startswith('powerCON ') for f in fers), rows
    # an L6-20 wall the same
    ev(pg, "B.powerSplitters = { enabled: false, maxWays: 3, manual: { merge: [], split: [] } };"
           " app.setScreenVoltage(B, 208); B.powerBreakoutType = 'soca-l620';"
           " app._circuitTailCache = null; return null;")
    assert _qty(pg.evaluate(ROWS_JS), 'L6-20 → powerCON cable') == {'EA': 3}
    # a TRUE1 wall: no row, its breakout is its input, whatever was stored
    ev(pg, "B.powerBreakoutType = 'soca-true1'; app.refreshSocaRuns(); return null;")
    pg.wait_for_timeout(200)
    assert not pg.locator('#power-panel-input-row').is_visible()
    assert ev(pg, "return app.panelInput(B).name;") == 'TRUE1'
    rows = pg.evaluate(ROWS_JS)
    assert not [r for r in rows if r[0].endswith(' cable')], rows
    assert errors == [], errors


def test_a_direct_outputs_cable_names_both_ends_where_they_differ(page):
    """WALL B (120V, powerCON panels) on PD 3, an Edison outlet, home run
    25'; WALL A (TRUE1) on PD 5, a TRUE1 outlet, 15'. The pull sheet, the
    map tag, the binder's band and wiring caption and the Distro page all
    say "Edison → powerCON" and "TRUE1", the length its own column."""
    pg, errors = page
    nums = setup(pg, distros=[DIST], walls={
        'a': {'powerBreakoutType': 'soca-true1', 'powerSocaSplits': [1],
              'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 5},
              'powerSocaLengths': {'1': '15'}},
        'b': {'powerVoltage': 120, 'powerBreakoutType': 'soca-powercon', 'powerSocaSplits': [1],
              'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 3},
              'powerSocaLengths': {'1': '25'}}})
    rows = pg.evaluate(ROWS_JS)
    assert ['Edison → powerCON', "25'", 1, 'PD3', ''] in rows, rows
    assert ['TRUE1', "15'", 1, 'PD5', ''] in rows, rows
    # the circuit's own cable is that cable
    b1 = nums['WALL B'][0]
    ev(pg, "B.powerCircuitCables = { [arg]: { ft: 10, connector: null } }; return null;", b1)
    rows = pg.evaluate(ROWS_JS)
    assert ['Edison → powerCON', "10'", 1, 'PD3', ''] in rows, rows
    assert not [r for r in rows if r[0] in ('powerCON', 'Edison') or "'" in r[0]], rows
    tag = ev(pg, "const c = app.powerCircuitCable(B, arg); const d = app.directCircuitCable(B, arg);"
                 " return [c.name, c.text, d.text];", b1)
    assert tag == ['Edison → powerCON', "10' Edison → powerCON", "10' Edison → powerCON"], tag
    caps = ev(pg, """const list = app.buildPullSheet();
        const book = { list, layers: new Map(app.project.layers.map(l => [String(l.id), l])) };
        return [A, B].map(L => app._bwPowerFacts(book, L, list.byScreen[L.id]).devices[0].title);""")
    assert caps == ["PD5 · TRUE1 · 15'", "PD3 · Edison → powerCON · 10'"], caps
    bands = ev(pg, """const list = app.buildPullList();
        return [A, B].map(l => app._bBoxTypeText(list.byScreen[l.id].boxes[0]));""")
    assert bands == ['TRUE1', 'Edison → powerCON'], bands
    distro = ev(pg, """const caught = [];
        const orig = app._bDistroBlocks;
        app._bDistroBlocks = function (book, d, load, boxes) {
            caught.push(...boxes.map(b => b.cells)); return orig.apply(this, arguments); };
        try {
            app.planBinder(Object.assign(app.readBinderOptions(),
                { scope: { kind: 'show' }, hardware: true, pull: false, cover: false }));
        } finally { app._bDistroBlocks = orig; }
        return caught.map(c => [c[0], c[1], c[2]]);""")
    assert ['PD3', 'Edison → powerCON', "10'"] in distro and ['PD5', 'TRUE1', "15'"] in distro, distro
    # the cable sheet's blank pick says what it follows
    follows = ev(pg, """const d = app.getDistros()[0];
        return app.directCableType(app.cableConnectorName(app.boxTailConnector(d, 3, B)), B);""")
    assert follows == 'Edison → powerCON'
    assert errors == [], errors


def test_the_old_names_carry_over(page):
    """A customised single powerJumpName (project or preference) is the
    TRUE1 jumper's name; the shipped "Tru-1 Power Jump" carries nothing.
    An edit saved on a "Tru-1 ..." row answers to its TRUE1 row."""
    pg, errors = page
    setup(pg, distros=[DIST], walls={'a': {'powerBreakoutType': 'soca-true1',
                                           'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1},
                                           'powerSocaLengths': {'1': '100'}}})
    got = ev(pg, """
        const read = (stored) => { app.project.pullSheet = stored; return app.getPullSheetSettings(); };
        const out = {
            custom: read({ powerJumpName: 'Long Power Jump' }),
            shipped: read({ powerJumpName: 'Tru-1 Power Jump' }),
            both: read({ powerJumpName: 'Long Power Jump', powerJumpNameTrue1: 'New' }),
        };
        delete app.project.pullSheet;
        const saved = app._serverPreferences;
        app._serverPreferences = Object.assign({}, saved || {}, { powerJumpName: 'Pref Jump' });
        delete app._serverPreferences.powerJumpNameTrue1;
        out.prefs = app.getPreferences().powerJumpNameTrue1;
        out.prefsDefault = app.getPullSheetDefaults().powerJumpNameTrue1;
        out.prefsLegacyKey = 'powerJumpName' in app.getPreferences();
        app._serverPreferences = saved;
        return out;""")
    assert got['custom']['powerJumpNameTrue1'] == 'Long Power Jump', got
    assert got['custom']['powerJumpNamePowercon'] == 'powerCON Power Jump', got
    assert got['shipped']['powerJumpNameTrue1'] == 'TRUE1 Power Jump', got
    assert got['both']['powerJumpNameTrue1'] == 'New', got
    assert got['prefs'] == 'Pref Jump' and got['prefsDefault'] == 'Pref Jump', got
    assert got['prefsLegacyKey'] is False, got
    edited = ev(pg, """
        const pos = app.buildPullList().positions[0];
        const key = app.pullPositionKey ? app.pullPositionKey(pos) : (pos.key || `layer:${A.id}`);
        app.project.pullSheetEdits = { positions: { [key]: { rows: [
            { key: 'Tru-1 Breakout|EA', qty: 5 }, { key: "Tru-1 Power Jump|1'", notes: 'old' }], added: [] } } };
        const keys = app.getPullSheetEdits().positions[key].rows.map(r => r.key);
        const rows = app.buildPullSheet().positions[0].rows.map(r => [r.type, r.length, r.qty, r.notes]);
        delete app.project.pullSheetEdits;
        return { keys, rows };""")
    assert edited['keys'] == ['TRUE1 Breakout|EA', "TRUE1 Power Jump|1'"], edited
    assert ['TRUE1 Breakout', 'EA', 5, ''] in edited['rows'], edited
    assert [r for r in edited['rows'] if r[0] == 'TRUE1 Power Jump' and r[3] == 'old'], edited
    assert errors == [], errors


def test_an_edit_on_the_old_edison_tail_row_answers_to_the_cable_row(page):
    """The 1.5.4 betas printed the Edison adapter as "Edison → TRUE1 tail";
    it is "Edison → TRUE1 cable" since (the owner, 2026-10-21: never
    "tail"), and "Edison 5-15 → TRUE1 cable" on a 12.5 A Edison screen
    now (its outlet, 2026-11-12). An edit a file saved on the old row (its
    count, its note) lands on the cable row, and the sheet says tail
    nowhere."""
    pg, errors = page
    setup(pg, walls={'b': {'powerVoltage': 120, 'powerAmperage': 12.5,
                           'powerBreakoutType': 'soca-edison'}})
    keys = ev(pg, """return ['Edison → TRUE1 tail|EA', 'L6-20 → powerCON tail|EA',
                             'Edison → TRUE1 tail', 'Edison → TRUE1 tailgate|EA',
                             'TRUE1|10\\'']
        .map(k => app.pullEditKey(k));""")
    assert keys == ['Edison → TRUE1 cable|EA', 'L6-20 → powerCON cable|EA',
                    'Edison → TRUE1 cable', 'Edison → TRUE1 tailgate|EA', "TRUE1|10'"], keys
    edited = ev(pg, """
        const sheet = app.buildPullSheet();
        const pos = sheet.positions.find(p => p.rows.some(r => r.type === 'Edison 5-15 → TRUE1 cable'));
        const key = app.pullPositionKey(pos);
        app.project.pullSheetEdits = { positions: { [key]: { rows: [
            { key: 'Edison → TRUE1 tail|EA', qty: 7, notes: 'spares' }], added: [] } } };
        const keys = app.getPullSheetEdits().positions[key].rows.map(r => r.key);
        const rows = app.buildPullSheet().positions.find(p => app.pullPositionKey(p) === key).rows
            .map(r => [r.type, r.length, r.qty, r.notes]);
        delete app.project.pullSheetEdits;
        return { keys, rows };""")
    assert edited['keys'] == ['Edison 5-15 → TRUE1 cable|EA'], edited
    assert ['Edison 5-15 → TRUE1 cable', 'EA', 7, 'spares'] in edited['rows'], edited
    assert not [r for r in edited['rows'] if re.search(r'\btails?\b', str(r[0]).lower())], edited
    assert errors == [], errors


def test_a_blank_cabinet_on_a_drawn_power_run_counts_no_jumper(page):
    """WALL B's hand-drawn circuit 1 runs its top row and steps over a
    blank third cabinet: the blank takes no power, so no jumper lands on
    it - four links, not five, as the automatic runs (which never hold a
    blank) count."""
    pg, errors = page
    setup(pg)
    out = ev(pg, """
        const path = [0, 1, 2, 3, 4, 5].map(col => ({ row: 0, col }));
        B.powerFlowPattern = 'custom';
        B.powerCustomPaths = { 1: path };
        const blank = B.panels.find(p => p.row === 0 && p.col === 2);
        blank.blank = true;
        app._circuitTailCache = null;
        const c = app.screenCircuits(B)[0];
        const links = app.jumperLinksOfRun(c.panels, c.layers, B, 'power');
        const data = app.jumperLinksOfRun(c.panels, c.layers, B, 'data');
        const scr = app.buildPullList().byScreen[B.id];
        // and it is counted nowhere else either (the owner, 2026-10-21):
        // the soca plan's panels (the binder's CIRCUITS PANELS and "N
        // panels each") and the custom run's load against its cap
        const tiles = app.getSocaPlan(B)[0].legs[0].tiles;
        const load = app.customRunFill(B, 'power', 1).load;
        const hit = app.customHitLoad('power', B, blank);
        const res = { panels: c.panels.length, links: links.length, data: data.length,
                      touchesBlank: links.some(l => l.a.blank || l.b.blank), power: scr.jumpers.power };
        Object.assign(res, { tiles, load, hit, watts: parseFloat(B.panelWatts) || 0 });
        delete blank.blank;
        B.powerFlowPattern = 'tl-h'; B.powerCustomPaths = {};
        app._circuitTailCache = null;
        return res;""")
    assert out['panels'] == 6 and out['links'] == 4 and not out['touchesBlank'], out
    assert out['power'] == 4, out
    assert out['data'] == 5, 'the data side is not this ruling'
    assert out['tiles'] == 5 and out['hit'] == 0, out
    assert out['load'] == pytest.approx(5 * out['watts']), out
    assert errors == [], errors
