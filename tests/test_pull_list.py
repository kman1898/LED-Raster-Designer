"""The pull list and the pull-sheet workbook.

"Export a file shaped to my template ... that i can import and edit
further" (user, 2026-09-06). The list is built ONCE on the client
(app-pull-list.js buildPullList) from the project - positions are the
screen GROUPS (an ungrouped screen is its own position), a box on a distro
is one `Multi` row plus one `<connector> Breakout`, a circuit's cable is
its connector's name plus its length, a 2fer / 3fer is `<connector> 2fer`
EA, a loose CAT port cable is `Ether-con` + length, a snake is one
`Ether-con Snake` row with its way count in Notes, and JUMPERS are one
per ROW STEP within a run (per port for data, per circuit for power), named
and sized per project (project.pullSheet). The server (pull_sheet.py) lays
the list into a copy of the user's workbook: positions side by side in the
six blocks the hidden calc tab scans, GEAR LIST grown to accept every type
and length written, TOTALS / Spares / calc formulas untouched.

Run locally (ONE pytest at a time - the browser-test servers use fixed
ports):
    python3 -m pytest tests/test_pull_list.py -v --browser chromium
"""

import io
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pull_sheet  # noqa: E402

openpyxl = pytest.importorskip('openpyxl', reason='openpyxl not installed')

HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH_FIXTURE = os.environ.get('LRD_PULL_SMOKE_JSON') or os.path.join(
    '/private/tmp/claude-501',
    '-Users-mattknotts-Nextcloud-LED-LED-Wall-Tech-Raster-Software-LED-Raster-Designer',
    'be6afb3b-7607-4f06-8c12-a10cd58068e9', 'scratchpad', 'experts-only.json')


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


def _formula_text(v):
    return v.text if hasattr(v, 'text') else v


# ── the shipped template ─────────────────────────────────────────────────

def test_the_shipped_template_is_the_scrubbed_workbook():
    """Every tab, both validations, the merges, the freeze pane and the
    hidden calc tab survive; the three named positions are blank and the
    header cells empty. Scrubbing it again changes nothing."""
    wb = openpyxl.load_workbook(pull_sheet.TEMPLATE_PATH)
    assert wb.sheetnames == ['Pull Sheet', 'Spares', 'TOTALS', 'GEAR LIST', 'READ ME', 'calc']
    assert wb['calc'].sheet_state == 'hidden'
    ws = wb['Pull Sheet']
    assert [ws.cell(5, c).value for c in pull_sheet.BLOCK_COLS[:4]] == [
        'POSITION 1', 'POSITION 2', 'POSITION 3', 'NEW POSITION']
    assert all(ws[ref].value is None for ref in ('B2', 'B3', 'E2', 'E3'))
    assert all(ws.cell(r, c).value is None
               for b in pull_sheet.BLOCK_COLS[:3] for r in range(7, 37) for c in range(b, b + 5))
    assert ws.freeze_panes == 'A7'
    assert sorted(str(dv.sqref) for dv in ws.data_validations.dataValidation) == [
        'A7:A36 G7:G36 M7:M36 S7:S36', 'B7:B36 H7:H36 N7:N36 T7:T36']
    assert 'A5:B5' in {str(r) for r in ws.merged_cells.ranges}
    # formula-built tabs are formula-built
    assert _formula_text(wb['calc']['A5'].value).startswith('=IF(N(INDIRECT("\'Pull Sheet\'!C7"))')
    assert _formula_text(wb['calc']['A364'].value).startswith('=IF(N(INDIRECT("\'Pull Sheet\'!AG66"))')
    assert wb['TOTALS']['C5'].value == '=IF($H5="","",SUMIF(calc!$A:$A,$H5,calc!$C:$C))'
    assert _formula_text(wb['Spares']['F6'].value) == '=IFERROR(INDEX(calc!$A:$A,MATCH(1,calc!$E:$E,0)),"")'
    # the GEAR LIST vocabulary the list writes in
    types = [wb['GEAR LIST'].cell(r, 1).value for r in range(4, 40)]
    for word in ('Multi', 'Tru-1', 'Tru-1 Breakout', 'Tru-1 2fer', 'Tru-1 3fer', 'Ether-con', 'Ether-con Snake'):
        assert word in types, word
    # idempotent
    again = io.BytesIO()
    pull_sheet.scrub_template(pull_sheet.TEMPLATE_PATH, again)
    wb2 = openpyxl.load_workbook(io.BytesIO(again.getvalue()))
    for name in wb.sheetnames:
        a, b = wb[name], wb2[name]
        for r in range(1, 70):
            for c in range(1, 40):
                assert _formula_text(a.cell(r, c).value) == _formula_text(b.cell(r, c).value), (name, r, c)


# ── the route ────────────────────────────────────────────────────────────

def _post_sheet(client, positions, **meta):
    body = {'project_name': meta.pop('project_name', 'Show X'), 'pull_list': {'positions': positions}}
    body.update(meta)
    return client.post('/api/export/pull-sheet', json=body)


def test_the_route_lays_the_list_into_the_workbook(client):
    """Two positions land in blocks A and G with their rows from row 7;
    the header cells are filled; a type and a length the GEAR LIST lacked
    are appended so the dropdowns accept them; TOTALS / Spares / calc
    keep their formulas and calc stays hidden."""
    positions = [
        {'name': 'SR Beach', 'rows': [
            {'type': 'Multi', 'length': "125'", 'qty': 2, 'label': 'SR 1-2', 'notes': ''},
            {'type': 'Tru-1', 'length': "10'", 'qty': 6, 'label': 'SR1-1, SR1-6', 'notes': ''},
            {'type': 'Widget Cable', 'length': "12'", 'qty': 1, 'label': 'X', 'notes': 'new'},
        ]},
        {'name': 'CENTER', 'rows': [
            {'type': 'Ether-con Snake', 'length': "100'", 'qty': 1, 'label': 'SNAKE A', 'notes': '6-way'},
        ]},
    ]
    r = _post_sheet(client, positions, engineer='Eng Name', rev='2.0',
                    date='Sep 6, 2026', date_iso='2026-09-06')
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.mimetype == pull_sheet.XLSX_MIME
    assert 'Show X-pull-sheet.xlsx' in r.headers['Content-Disposition']
    assert json.loads(r.headers['X-Pull-Sheet-Warnings']) == []
    assert r.data[:2] == b'PK'
    wb = openpyxl.load_workbook(io.BytesIO(r.data))
    ws = wb['Pull Sheet']
    assert ws['B2'].value == 'Show X' and ws['B3'].value == 'Eng Name' and ws['E3'].value == '2.0'
    assert ws['E2'].value.date().isoformat() == '2026-09-06' and ws['E2'].number_format == 'mmm d, yyyy'
    assert [ws.cell(5, c).value for c in pull_sheet.BLOCK_COLS] == [
        'SR Beach', 'CENTER', 'POSITION 3', 'NEW POSITION', None, None]
    assert [[ws.cell(r, c).value for c in range(1, 6)] for r in range(7, 10)] == [
        ['Multi', "125'", 2, 'SR 1-2', None],
        ['Tru-1', "10'", 6, 'SR1-1, SR1-6', None],
        ['Widget Cable', "12'", 1, 'X', 'new'],
    ]
    assert ws.cell(10, 1).value is None
    assert [ws.cell(7, c).value for c in range(7, 12)] == ['Ether-con Snake', "100'", 1, 'SNAKE A', '6-way']
    assert ws.cell(7, 13).value is None
    gear = wb['GEAR LIST']
    types = [gear.cell(r, 1).value for r in range(4, 100) if gear.cell(r, 1).value]
    lengths = [gear.cell(r, 2).value for r in range(4, 61) if gear.cell(r, 2).value]
    assert types[-1] == 'Widget Cable' and types.count('Multi') == 1
    assert lengths[-1] == "12'" and lengths.count("125'") == 1
    assert wb['calc'].sheet_state == 'hidden'
    assert _formula_text(wb['calc']['A5'].value).startswith('=IF(N(INDIRECT(')
    assert wb['TOTALS']['E5'].value == '=IF($H5="","",$C5+$D5)'
    assert _formula_text(wb['Spares']['F6'].value).startswith('=IFERROR(INDEX(calc!$A:$A')
    assert sorted(str(dv.sqref) for dv in ws.data_validations.dataValidation) == [
        'A7:A36 G7:G36 M7:M36 S7:S36', 'B7:B36 H7:H36 N7:N36 T7:T36']
    assert 'Overflow' not in wb.sheetnames


def test_four_to_six_positions_take_the_s_y_ae_blocks_and_more_overflow(client):
    """The fourth position takes the tan block (restyled as a position,
    the copy-me block moving right), Y and AE are styled from it, more
    than 30 rows grow every block in place to the calc tab's 66 with the
    dropdowns following, and a seventh position lands on an Overflow tab
    with a warning the client shows."""
    def rows(n, t='Multi'):
        return [{'type': f'{t} {k}', 'length': "6'", 'qty': 1, 'label': '', 'notes': ''} for k in range(n)]
    four = [{'name': f'P{i}', 'rows': rows(2)} for i in range(4)]
    r = _post_sheet(client, four)
    wb = openpyxl.load_workbook(io.BytesIO(r.data))
    ws = wb['Pull Sheet']
    assert [ws.cell(5, c).value for c in pull_sheet.BLOCK_COLS] == ['P0', 'P1', 'P2', 'P3', 'NEW POSITION', None]
    assert ws['S5'].fill.fgColor.rgb == ws['A5'].fill.fgColor.rgb and ws['U5'].value is None
    assert ws['Y5'].fill.fgColor.rgb == 'FFFBE9D0' and ws['AA5'].value == '< copy to add a position >'
    assert ws['Y6'].value == 'Cable Type' and ws['Y7'].border.left.style == 'thin'
    assert wb.defined_names['NEW_BLOCK_TEMPLATE'].attr_text == "'Pull Sheet'!$Y$5:$AC$36"
    assert 'Y7:Y36' in str([str(dv.sqref) for dv in ws.data_validations.dataValidation])

    seven = [{'name': f'P{i}', 'rows': rows(2)} for i in range(7)]
    seven[1]['rows'] = rows(35, 'Type')
    r = _post_sheet(client, seven)
    warnings = json.loads(r.headers['X-Pull-Sheet-Warnings'])
    assert len(warnings) == 1 and 'P6' in warnings[0] and 'Overflow' in warnings[0]
    wb = openpyxl.load_workbook(io.BytesIO(r.data))
    ws = wb['Pull Sheet']
    assert [ws.cell(5, c).value for c in pull_sheet.BLOCK_COLS] == ['P0', 'P1', 'P2', 'P3', 'P4', 'P5']
    assert ws['AE5'].fill.fgColor.rgb == ws['A5'].fill.fgColor.rgb
    assert [ws.cell(41, c).value for c in range(7, 12)] == ['Type 34', "6'", 1, None, None]
    assert ws['A41'].border.left.style == 'thin' and ws['AE41'].border.left.style == 'thin'
    assert sorted(str(dv.sqref) for dv in ws.data_validations.dataValidation) == [
        'A7:A41 G7:G41 M7:M41 S7:S41 Y7:Y41 AE7:AE41', 'B7:B41 H7:H41 N7:N41 T7:T41 Z7:Z41 AF7:AF41']
    ov = wb['Overflow']
    assert [c.value for c in ov[1]] == ['Position', 'Cable Type', 'Length', 'Qty', 'Label', 'Notes']
    assert [c.value for c in ov[2]] == ['P6', 'Multi 0', "6'", 1, None, None]
    assert wb['calc'].sheet_state == 'hidden'

    # a 61st row overflows too: the calc tab stops at row 66
    big = [{'name': 'BIG', 'rows': rows(61, 'Row')}]
    r = _post_sheet(client, big)
    wb = openpyxl.load_workbook(io.BytesIO(r.data))
    ws = wb['Pull Sheet']
    assert ws.cell(66, 1).value == 'Row 59' and ws.cell(67, 1).value is None
    assert [c.value for c in wb['Overflow'][2]] == ['BIG', 'Row 60', "6'", 1, None, None]
    assert any('more than 60 rows' in w for w in json.loads(r.headers['X-Pull-Sheet-Warnings']))


def test_the_route_refuses_a_shapeless_body(client):
    r = client.post('/api/export/pull-sheet', json={'project_name': 'X'})
    assert r.status_code == 400
    assert 'pull_list' in r.get_json()['error']


def test_the_menu_item_and_the_format_option_are_served(client):
    html = client.get('/').get_data(as_text=True)
    assert re.search(r'data-action="export-pull-sheet"[^>]*data-label="Export Pull Sheet"', html)
    assert '<option value="pull-sheet">' in html
    assert 'id="export-pull-sheet-section"' in html
    for field in ('data-jump-name', 'data-jump-length', 'power-jump-name',
                  'power-jump-length', 'engineer', 'rev'):
        assert f'id="export-pull-sheet-{field}"' in html, field
    # the module is registered
    main_js = open(os.path.join(HERE, '..', 'src', 'static', 'js', 'main.js')).read()
    assert "import './app-pull-list.js';" in main_js


# ── the browser: the engine ──────────────────────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

# Two grouped screens (SR Beach: WALL-A and WALL-B, 4 × 3 of 200 px
# cabinets, routed per member for data) and one loose screen (CENTER, the
# 3 × 5 Edison wall that gangs its first two columns through a 2fer). One
# distro SR: WALL-A's multi on box 1 at 125', WALL-B's on box 2 at 100'.
# Cables: WALL-A circuits 1 and 2 at 10', WALL-B circuit 1 at 6'. One H9
# with a 16 × RJ45 card: every screen's single port placed on it, sockets
# 1-2 in SNAKE A (100'), socket 3 with a 50' cable.
#
# Power packing, organized, top-left horizontal: WALL-A at 200 W / 208 V /
# 10 A holds two rows (1600 W) per circuit - circuits [rows 1-2] and
# [row 3], one multi; WALL-B at 250 W the same (2000 W). Watts differ so
# power does NOT cross the group, and routeDataAsOne is off so data is
# per member: each 4 × 3 wall is one port over three rows.
SEED_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet;
    await j('PUT', '/api/project', proj);
    const add = (body) => j('POST', '/api/layer/add', body);
    await add({name: 'WALL-A', columns: 4, rows: 3, cabinet_width: 200, cabinet_height: 200,
               powerVoltage: 208, powerAmperage: 10, panelWatts: 200,
               powerFlowPattern: 'tl-h', powerOrganized: true, flowPattern: 'tl-h',
               processorType: 'novastar-armor'});
    await add({name: 'WALL-B', columns: 4, rows: 3, cabinet_width: 200, cabinet_height: 200,
               powerVoltage: 208, powerAmperage: 10, panelWatts: 250,
               powerFlowPattern: 'tl-h', powerOrganized: true, flowPattern: 'tl-h',
               processorType: 'novastar-armor'});
    await add({name: 'CENTER', columns: 3, rows: 5, cabinet_width: 128, cabinet_height: 128,
               powerVoltage: 110, powerAmperage: 15, panelWatts: 100,
               powerFlowPattern: 'tl-v', powerOrganized: true, flowPattern: 'tl-h',
               powerSplitters: {enabled: true, maxWays: 2, manual: {merge: [], split: []}},
               processorType: 'novastar-armor'});
    let p = await j('GET', '/api/project');
    const A = p.layers.find(l => l.name === 'WALL-A');
    const B = p.layers.find(l => l.name === 'WALL-B');
    const C = p.layers.find(l => l.name === 'CENTER');
    p.groups = [{id: 'g1', name: 'SR Beach', layer_ids: [A.id, B.id], routeDataAsOne: false}];
    await j('PUT', '/api/project', p);
    // the processor: one H9, slot 0 a 16 x RJ45 card named SR
    let st = await j('POST', '/api/processors', {deviceId: 'novastar-h9'});
    const pid = st.processors[0].id;
    st = await j('PUT', `/api/processors/${pid}/slots/0`, {deviceId: 'novastar-card-h-16xrj45-2xfiber'});
    const cardId = st.processors[0].slots[0].card.id;
    await j('PUT', `/api/processors/${pid}/cards/${cardId}`, {name: 'SR'});
    p = await j('GET', '/api/project');
    app.project = p;
    app.dedupeProjectLayers('pull_list_setup');
    const a = app.project.layers.find(l => l.id === A.id);
    const b = app.project.layers.find(l => l.id === B.id);
    const c = app.project.layers.find(l => l.id === C.id);
    app.selectLayer(a);
    const d = app.addDistro({name: 'SR'});
    app.setSocaDistro(a, 1, d.id); app.setSocaNumber(a, 1, 1); app.setSocaLength(a, 1, '125');
    app.setSocaDistro(b, 1, d.id); app.setSocaNumber(b, 1, 2); app.setSocaLength(b, 1, '100');
    app.setCircuitCable(a, 1, {ft: 10, connector: null});
    app.setCircuitCable(a, 2, {ft: 10, connector: null});
    app.setCircuitCable(b, 1, {ft: 6, connector: null});
    await app.refreshProcessors();
    for (const l of [a, b, c]) {
        await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
                                     {layerId: String(l.id), cardId});
    }
    const sockets = {};
    for (const s of app._assignment.screens) {
        sockets[s.name] = s.ports.map(pt => pt.port);
    }
    await j('PUT', `/api/processors/${pid}/cards/${cardId}`, {
        snakes: [{ports: [sockets['WALL-A'][0], sockets['WALL-B'][0]], ft: 100}],
        portCables: {[String(sockets['CENTER'][0])]: {ft: 50}},
    });
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    app.renderHardwareDock();
    window.canvasRenderer.render();
    app.resetHistory('Pull List Seed');
    return {
        a: a.id, b: b.id, c: c.id, distroId: d.id, procId: pid, cardId, sockets,
        centerRunIds: app.screenCircuits(c).map(x => x.runIds || [x.num]),
        centerLabel: app.getPowerCircuitLabel(c, 1),
        centerPortLabel: app.getPortLabelText(c, 1, 'primary'),
        aCircuits: app.screenCircuits(a).map(x => x.panels.length),
        bCircuits: app.screenCircuits(b).map(x => x.panels.length),
    };
}"""

LIST_JS = """() => {
    const app = window.app;
    app._circuitTailCache = null;
    const out = app.buildPullList();
    return JSON.parse(JSON.stringify(out));
}"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(500)
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(1200)
    assert ids['centerRunIds'] == [[1, 2], [3]], f'fixture: CENTER must gang columns 1+2: {ids}'
    assert ids['aCircuits'] == [8, 4] and ids['bCircuits'] == [8, 4], (
        f'fixture: two rows per circuit on the 4 x 3 walls: {ids}')
    assert all(len(v) == 1 for v in ids['sockets'].values()), f'fixture: one port per screen: {ids}'
    yield pg, ids
    context.close()


def _rows(rows):
    return [(r['type'], r['length'], r['qty'], r['label'], r['notes']) for r in rows]


def test_positions_are_the_groups_and_the_rows_read_in_the_sheets_vocabulary(page):
    pg, ids = page
    out = pg.evaluate(LIST_JS)
    assert [p['name'] for p in out['positions']] == ['SR Beach', 'CENTER']
    assert out['positions'][0]['layerIds'] == [ids['a'], ids['b']]
    assert out['positions'][0]['groupId'] == 'g1' and out['positions'][1]['groupId'] is None
    sr = _rows(out['positions'][0]['rows'])
    # WALL-A: circuit 1 spans two rows (one row step), circuit 2 one row;
    # WALL-B the same -> 2 power jumpers. Data: one port over three rows
    # each -> 2 + 2 data jumpers.
    assert sr == [
        ('Data Jump', "6'", 4, 'WALL-A, WALL-B', ''),
        ('Ether-con Snake', "100'", 1, 'SNAKE A', '2-way'),
        ('Multi', "100'", 1, 'SR 2', ''),
        ('Multi', "125'", 1, 'SR 1', ''),
        ('Tru-1', "6'", 1, 'SR2-1', ''),
        ('Tru-1', "10'", 2, 'SR1-1, SR1-2', ''),
        ('Tru-1 Breakout', 'EA', 2, 'SR 1-2', ''),
        ('Tru-1 Power Jump', "6'", 2, 'WALL-A, WALL-B', ''),
    ]
    # CENTER: vertical-first columns of five cabinets - every step in a
    # run changes row: 3 runs x 4 = 12 power jumpers; the port walks
    # 5 rows horizontally = 4 data jumpers; no distro, so no Multi and no
    # breakout; a 110 V screen breaks out to Edison, so the gang is an
    # Edison 2fer and the loose port cable is 50' of Ether-con.
    center = _rows(out['positions'][1]['rows'])
    assert center == [
        ('Data Jump', "6'", 4, 'CENTER', ''),
        ('Edison 2fer', 'EA', 1, ids['centerLabel'], ''),
        ('Ether-con', "50'", 1, ids['centerPortLabel'], ''),
        ('Tru-1 Power Jump', "6'", 12, 'CENTER', ''),
    ]
    # totals merge the same (type, length) across positions
    totals = {(t, l): q for t, l, q, _, _ in _rows(out['totals'])}
    assert totals[('Data Jump', "6'")] == 8
    assert totals[('Tru-1 Power Jump', "6'")] == 14
    assert totals[('Tru-1', "10'")] == 2 and totals[('Tru-1', "6'")] == 1
    assert totals[('Multi', "125'")] == 1 and totals[('Multi', "100'")] == 1
    assert totals[('Tru-1 Breakout', 'EA')] == 2 and totals[('Edison 2fer', 'EA')] == 1
    assert len(out['totals']) == 10
    # EA sorts after every length; types are A-Z
    types = [r['type'] for r in out['totals']]
    assert types == sorted(types, key=str.lower)
    assert out['unmodelled'] and 'Fiber trunk' in out['unmodelled'][0]


def test_the_per_screen_readings_the_packet_will_print(page):
    pg, ids = page
    out = pg.evaluate(LIST_JS)
    a = out['byScreen'][str(ids['a'])]
    assert a['name'] == 'WALL-A' and a['jumpers'] == {'data': 2, 'power': 1}
    assert len(a['boxes']) == 1
    box = a['boxes'][0]
    assert (box['distro'], box['number'], box['homeRun'], box['type'], box['connector'], box['shared']) == (
        'SR', 1, '125', 'Soca 208', 'Tru-1', False)
    assert [(c['num'], c['label'], c['tail'], c['cable']) for c in box['circuits']] == [
        (1, 'SR1-1', 1, "10' True1"), (2, 'SR1-2', 2, "10' True1")]
    assert a['gangs'] == {'twofer': 0, 'threefer': 0}
    assert [(p['num'], p['snake'], p['cable']) for p in a['ports']] == [(1, 'SNAKE A', None)]
    assert [(s['name'], s['ways'], s['ft']) for s in a['snakes']] == [('SNAKE A', 2, 100)]
    b = out['byScreen'][str(ids['b'])]
    assert b['snakes'] == [] and b['ports'][0]['snake'] == 'SNAKE A', 'the snake is said once'
    assert b['boxes'][0]['homeRun'] == '100' and b['jumpers'] == {'data': 2, 'power': 1}
    c = out['byScreen'][str(ids['c'])]
    assert c['gangs'] == {'twofer': 1, 'threefer': 0}
    assert c['boxes'][0]['distro'] is None and c['boxes'][0]['connector'] == 'Edison'
    assert [(p['num'], p['snake'], p['cable']) for p in c['ports']] == [(1, None, "50' CAT")]
    # hardware: the distro's boxes, the processor's cable
    kinds = {(h['kind'], h['name']): _rows(h['rows']) for h in out['hardware']}
    assert kinds[('distro', 'SR')] == [
        ('Multi', "100'", 1, 'SR 2', ''), ('Multi', "125'", 1, 'SR 1', ''),
        ('Tru-1 Breakout', 'EA', 2, 'SR 1-2', '')]
    proc_rows = next(v for (k, n), v in kinds.items() if k == 'processor')
    assert proc_rows == [('Ether-con', "50'", 1, ids['centerPortLabel'], ''),
                         ('Ether-con Snake', "100'", 1, 'SNAKE A', '2-way')]


def test_row_steps_horizontal_first_is_one_per_row_change_and_vertical_first_every_step(page):
    """One 4 x 3 screen on one circuit and one port: a horizontal-first
    serpentine changes row twice (3 rows) - 2 jumpers; a vertical-first
    one changes row on every step inside a column (2 per column x 4) and
    never on the hop between columns - 8 jumpers. The same rule on both
    sides of the wall."""
    pg, ids = page
    out = pg.evaluate("""(ids) => {
        const app = window.app;
        const c = app.project.layers.find(l => l.id === ids.c);
        // CENTER is loose: reshape it into the probe (4 x 3, one circuit,
        // one port) without touching the seeded walls.
        const keep = JSON.parse(JSON.stringify(c));
        const probe = (powerPattern, dataPattern) => {
            Object.assign(c, {powerFlowPattern: powerPattern, flowPattern: dataPattern,
                              powerAmperage: 30, powerVoltage: 208, panelWatts: 100,
                              powerSplitters: {enabled: false, maxWays: 3, manual: {merge: [], split: []}}});
            app._circuitTailCache = null;
            const s = app.buildPullList().byScreen[String(c.id)];
            return {power: s.jumpers.power, data: s.jumpers.data,
                    circuits: app.screenCircuits(c).length};
        };
        const h = probe('tl-h', 'tl-h');
        const v = probe('tl-v', 'tl-v');
        Object.assign(c, keep);
        app._circuitTailCache = null;
        return {h, v};
    }""", ids)
    assert out['h']['circuits'] == 1 and out['v']['circuits'] == 1
    # CENTER is 3 x 5: horizontal-first = 4 row changes; vertical-first =
    # 4 steps per column x 3 columns = 12.
    assert out['h'] == {'power': 4, 'data': 4, 'circuits': 1}
    assert out['v'] == {'power': 12, 'data': 12, 'circuits': 1}


def test_a_box_without_a_length_says_so_and_a_hidden_screen_is_off_the_list(page):
    pg, ids = page
    out = pg.evaluate("""(ids) => {
        const app = window.app;
        const b = app.project.layers.find(l => l.id === ids.b);
        const keep = JSON.parse(JSON.stringify(b.powerSocaLengths || {}));
        b.powerSocaLengths = {};
        app._circuitTailCache = null;
        const noLen = app.buildPullList().positions[0].rows
            .filter(r => r.type === 'Multi').map(r => [r.length, r.qty, r.label, r.notes]);
        b.powerSocaLengths = keep;
        b.visible = false;
        app._circuitTailCache = null;
        const hidden = app.buildPullList();
        b.visible = true;
        app._circuitTailCache = null;
        return {noLen, names: hidden.positions.map(p => p.name),
                srLayers: hidden.positions[0].layerIds,
                multis: hidden.positions[0].rows.filter(r => r.type === 'Multi').length};
    }""", ids)
    # a blank length sorts after the numbers and before EA
    assert out['noLen'] == [["125'", 1, 'SR 1', ''], ['', 1, 'SR 2', 'no length']]
    assert out['names'] == ['SR Beach', 'CENTER']
    assert out['srLayers'] == [ids['a']] and out['multis'] == 1


# ── the browser: the settings, the menu, the export ─────────────────────

def test_the_jumper_settings_are_project_state_with_one_entry_per_edit(page):
    pg, ids = page
    before = pg.evaluate("() => ({steps: window.app.history.length, i: window.app.historyIndex})")
    pg.locator('[data-menu="file"]').click()
    pg.locator('[data-action="export-pull-sheet"]').click()
    pg.wait_for_timeout(300)
    assert pg.locator('#export-pull-sheet-data-jump-name').input_value() == 'Data Jump'
    assert pg.locator('#export-pull-sheet-power-jump-length').input_value() == '6'
    pg.locator('#export-pull-sheet-data-jump-name').fill('Absen Long Data Jump')
    pg.locator('#export-pull-sheet-data-jump-name').dispatch_event('change')
    pg.locator('#export-pull-sheet-power-jump-length').fill('10')
    pg.locator('#export-pull-sheet-power-jump-length').dispatch_event('change')
    pg.wait_for_timeout(600)
    st = pg.evaluate("""() => {
        const app = window.app;
        return {settings: app.getPullSheetSettings(), stored: app.project.pullSheet,
                steps: app.history.length, i: app.historyIndex,
                actions: app.history.slice(-2).map(h => h.action)};
    }""")
    assert st['stored'] == {'dataJumpName': 'Absen Long Data Jump', 'powerJumpLength': 10}
    assert st['settings']['dataJumpName'] == 'Absen Long Data Jump'
    assert st['settings']['powerJumpLength'] == 10 and st['settings']['powerJumpName'] == 'Tru-1 Power Jump'
    assert st['steps'] == before['steps'] + 2 and st['actions'] == [
        'Set Data Jumper Name', 'Set Power Jumper Length']
    # the list reads them
    rows = _rows(pg.evaluate(LIST_JS)['totals'])
    assert ('Absen Long Data Jump', "6'", 8, 'WALL-A, WALL-B, CENTER', '') in rows
    assert ('Tru-1 Power Jump', "10'", 14, 'WALL-A, WALL-B, CENTER', '') in rows
    # served: a reload would keep them
    served = pg.evaluate("async () => (await (await fetch('/api/project')).json()).pullSheet")
    assert served == {'dataJumpName': 'Absen Long Data Jump', 'powerJumpLength': 10}
    # undo takes the last edit back, and only that one
    pg.locator('#export-cancel').click()
    pg.evaluate("() => window.app.undo()")
    pg.wait_for_timeout(600)
    assert pg.evaluate("() => window.app.project.pullSheet") == {'dataJumpName': 'Absen Long Data Jump'}
    pg.evaluate("() => window.app.redo()")
    pg.wait_for_timeout(600)
    assert pg.evaluate("() => window.app.getPullSheetSettings().powerJumpLength") == 10


def test_the_engineer_lives_in_the_preferences(page):
    pg, ids = page
    pg.evaluate("() => window.app.openExportModal('pull-sheet')")
    pg.wait_for_timeout(200)
    pg.locator('#export-pull-sheet-engineer').fill('Test Engineer')
    pg.locator('#export-pull-sheet-engineer').dispatch_event('change')
    pg.wait_for_timeout(600)
    assert pg.evaluate("() => window.app.getEngineerName()") == 'Test Engineer'
    served = pg.evaluate("async () => (await (await fetch('/api/preferences')).json()).engineerName")
    assert served == 'Test Engineer'
    assert 'engineer' not in json.dumps(pg.evaluate("() => window.app.project.pullSheet || {}"))
    # the Preferences modal's own save carries it through untouched
    carried = pg.evaluate("() => window.app.readPreferencesFromUI().engineerName")
    assert carried == 'Test Engineer'
    pg.locator('#export-cancel').click()


def test_the_file_menu_opens_the_export_dialog_on_the_pull_sheet_format(page):
    pg, ids = page
    pg.evaluate("() => { document.getElementById('export-modal').style.display = 'none'; }")
    pg.locator('[data-menu="file"]').click()
    pg.locator('[data-action="export-pull-sheet"]').click()
    pg.wait_for_timeout(300)
    assert pg.locator('#export-modal').is_visible()
    assert pg.locator('#export-format').input_value() == 'pull-sheet'
    assert pg.locator('#export-pull-sheet-section').is_visible()
    assert not pg.locator('#export-views-section').is_visible()
    assert not pg.locator('#export-canvases-section').is_visible()
    assert not pg.locator('#export-options-section').is_visible()
    assert not pg.locator('#export-scale-row').is_visible()
    name = pg.locator('#export-name').input_value()
    assert pg.locator('#export-preview').inner_text().strip() == f'{name}-pull-sheet.xlsx'
    # switching back to PNG brings the picture sections back
    pg.select_option('#export-format', 'png')
    pg.wait_for_timeout(200)
    assert pg.locator('#export-views-section').is_visible()
    assert pg.locator('#export-canvases-section').is_visible()
    assert not pg.locator('#export-pull-sheet-section').is_visible()
    pg.select_option('#export-format', 'pull-sheet')
    pg.wait_for_timeout(200)
    assert pg.locator('#export-pull-sheet-section').is_visible()
    pg.locator('#export-cancel').click()
    pg.wait_for_timeout(200)
    assert not pg.locator('#export-modal').is_visible()


def test_export_saves_the_workbook_through_the_picker_path(page):
    """The confirm button posts the list and hands the xlsx to
    saveBlobWithPicker - the same save path as the PDF, no window, no
    print dialog. The blob is a real workbook carrying the positions."""
    pg, ids = page
    pg.evaluate("""() => {
        const app = window.app;
        window.__pullCaptured = null;
        app.__origSave = app.saveBlobWithPicker;
        app.saveBlobWithPicker = async (blob, filename, mime) => {
            const bytes = new Uint8Array(await blob.arrayBuffer());
            let bin = '';
            for (let i = 0; i < bytes.length; i += 0x8000) {
                bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
            }
            window.__pullCaptured = {filename, mime, size: bytes.length, b64: btoa(bin)};
        };
        window.open = () => { window.__pullOpened = true; return null; };
        window.print = () => { window.__pullPrinted = true; };
    }""")
    pg.evaluate("() => window.app.openExportModal('pull-sheet')")
    pg.wait_for_timeout(200)
    pg.locator('#export-name').fill('Test Show')
    pg.locator('#export-name').dispatch_event('input')
    pg.locator('#export-confirm').click()
    waited = 0
    while waited < 8000 and not pg.evaluate("() => !!window.__pullCaptured"):
        pg.wait_for_timeout(250)
        waited += 250
    cap = pg.evaluate("() => window.__pullCaptured")
    pg.evaluate("() => { window.app.saveBlobWithPicker = window.app.__origSave; }")
    assert cap, 'the export never reached saveBlobWithPicker'
    assert cap['filename'] == 'Test Show-pull-sheet.xlsx'
    assert cap['mime'] == pull_sheet.XLSX_MIME
    assert not pg.evaluate("() => !!window.__pullOpened") and not pg.evaluate("() => !!window.__pullPrinted")
    import base64
    data = base64.b64decode(cap['b64'])
    assert data[:2] == b'PK'
    wb = openpyxl.load_workbook(io.BytesIO(data))
    ws = wb['Pull Sheet']
    assert ws['B2'].value == 'Test Show' and ws['B3'].value == 'Test Engineer'
    assert [ws.cell(5, c).value for c in pull_sheet.BLOCK_COLS[:3]] == ['SR Beach', 'CENTER', 'POSITION 3']
    assert [ws.cell(7, c).value for c in range(1, 6)] == ['Absen Long Data Jump', "6'", 4, 'WALL-A, WALL-B', None]
    assert ws['E2'].value is not None and ws['E3'].value == '1.0'
    gear_types = [wb['GEAR LIST'].cell(r, 1).value for r in range(4, 100) if wb['GEAR LIST'].cell(r, 1).value]
    assert 'Edison 2fer' in gear_types and 'Tru-1 Power Jump' in gear_types
    assert gear_types.count('Absen Long Data Jump') == 1
    assert wb['calc'].sheet_state == 'hidden'
    assert not pg.locator('#export-modal').is_visible()


# ── the smoke: the user's own show ───────────────────────────────────────

@pytest.mark.skipif(not os.path.exists(SCRATCH_FIXTURE),
                    reason='experts-only.json smoke fixture not present')
def test_smoke_experts_only(page):
    """The real show: SR - MAIN's 22 custom circuits on four boxes SR 1-4
    (125' / 100' / 125' / 100') with typed cables; SR - Return on box 5;
    SL mirroring it with no lengths and no cables. No groups in the file,
    so every screen is its own position, named after it."""
    pg, ids = page
    with open(SCRATCH_FIXTURE) as fh:
        project = json.load(fh)
    out = pg.evaluate("""async (project) => {
        const app = window.app;
        const j = (method, url, body) => fetch(url, {method,
            headers: {'Content-Type': 'application/json'},
            body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
        await j('PUT', '/api/project', project);
        app.project = await j('GET', '/api/project');
        app.dedupeProjectLayers('pull_smoke');
        app.selectLayer(app.project.layers.find(l => (l.type || 'screen') === 'screen'));
        await app.refreshProcessors();
        await app.refreshPortAssignment();
        app.renderLayers();
        app._circuitTailCache = null;
        const list = JSON.parse(JSON.stringify(app.buildPullList()));
        const ret = app.project.layers.find(l => l.name === 'SR - Return');
        list.returnLegs = app.getSocaPlan(ret).map(s => s.legs.map(g => [g.circuit, g.label]));
        return list;
    }""", project)
    names = [p['name'] for p in out['positions']]
    assert names == ['SR - MAIN', 'SR - Return', 'SL - MAIN', 'SL - Return']
    by = {p['name']: _rows(p['rows']) for p in out['positions']}
    # SR - MAIN: four boxes SR 1-4 at 125' / 100' / 125' / 100' (two plan
    # entries share box 3 and two share box 4 - one Multi each), the 14
    # typed cables, one breakout per box. Its 22 hand-drawn circuits each
    # stay on ONE row (verified against the file), so no power jumper row;
    # the auto ports of the 28 x 11 wall step rows 7 times.
    assert by['SR - MAIN'] == [
        ('Data Jump', "6'", 7, 'SR - MAIN', ''),
        ('Multi', "100'", 2, 'SR 2, 4', ''),
        ('Multi', "125'", 2, 'SR 1, 3', ''),
        ('Tru-1', "6'", 8, 'SR1-2, SR1-5, SR2-3, SR2-6, SR3-2, SR3-5, SR4-2, SR4-6', ''),
        ('Tru-1', "10'", 6, 'SR1-1, SR1-6, SR2-2, SR3-1, SR3-6, SR4-1', ''),
        ('Tru-1 Breakout', 'EA', 4, 'SR 1-4', ''),
    ]
    # SR - Return: box 5 at 125', its cables as typed; the auto wall packs
    # with splitters on (maxWays 3) and gangs circuits 1-5 through 2fers.
    assert by['SR - Return'] == [
        ('Data Jump', "6'", 10, 'SR - Return', ''),
        ('Multi', "125'", 1, 'SR 5', ''),
        ('Tru-1', "6'", 1, 'SR5-3', ''),
        ('Tru-1', "10'", 2, 'SR5-2, SR5-5', ''),
        ('Tru-1', "25'", 2, 'SR5-1, SR5-6', ''),
        ('Tru-1 2fer', 'EA', 5, 'SR5-1, SR5-2, SR5-3, SR5-4, SR5-5', ''),
        ('Tru-1 Breakout', 'EA', 1, 'SR 5', ''),
    ]
    assert out['returnLegs'] == [[[1, 'SR5-1'], [2, 'SR5-2'], [3, 'SR5-3'], [4, 'SR5-4'], [5, 'SR5-5'], [6, 'SR5-6']]]
    # SL mirrors SR with no lengths and no cables
    assert by['SL - MAIN'] == [
        ('Data Jump', "6'", 7, 'SL - MAIN', ''),
        ('Multi', '', 4, 'SL 1-4', 'no length'),
        ('Tru-1 Breakout', 'EA', 4, 'SL 1-4', ''),
    ]
    assert by['SL - Return'] == [
        ('Data Jump', "6'", 10, 'SL - Return', ''),
        ('Multi', '', 1, 'SL 5', 'no length'),
        ('Tru-1 2fer', 'EA', 5, 'SL5-1, SL5-2, SL5-3, SL5-4, SL5-5', ''),
        ('Tru-1 Breakout', 'EA', 1, 'SL 5', ''),
    ]
    assert _rows(out['totals']) == [
        ('Data Jump', "6'", 34, 'SR - MAIN, SR - Return, SL - MAIN, SL - Return', ''),
        ('Multi', "100'", 2, 'SR 2, 4', ''),
        ('Multi', "125'", 3, 'SR 1, 3, 5', ''),
        ('Multi', '', 5, 'SL 1-5', 'no length'),
        ('Tru-1', "6'", 9, 'SR1-2 … SR5-3 (9)', ''),
        ('Tru-1', "10'", 8, 'SR1-1, SR1-6, SR2-2, SR3-1, SR3-6, SR4-1, SR5-2, SR5-5', ''),
        ('Tru-1', "25'", 2, 'SR5-1, SR5-6', ''),
        ('Tru-1 2fer', 'EA', 10, 'SR5-1 … SL5-5 (10)', ''),
        ('Tru-1 Breakout', 'EA', 10, 'SR 1-5, SL 1-5', ''),
    ]
    # the file types no data cable, so no Ether-con rows
    assert not any(r[0].startswith('Ether-con') for rows in by.values() for r in rows)
    # the workbook takes it: four positions, the tan block moved to Y
    r = pg.evaluate("""async (list) => {
        const res = await fetch('/api/export/pull-sheet', {method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({project_name: '2026 Experts Only', pull_list: list,
                                  engineer: 'E', rev: '1.0', date_iso: '2026-09-06'})});
        const bytes = new Uint8Array(await (await res.blob()).arrayBuffer());
        let bin = '';
        for (let i = 0; i < bytes.length; i += 0x8000) {
            bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
        }
        return {status: res.status, warnings: res.headers.get('X-Pull-Sheet-Warnings'),
                b64: btoa(bin)};
    }""", out)
    assert r['status'] == 200 and json.loads(r['warnings']) == []
    import base64
    wb = openpyxl.load_workbook(io.BytesIO(base64.b64decode(r['b64'])))
    ws = wb['Pull Sheet']
    assert [ws.cell(5, c).value for c in pull_sheet.BLOCK_COLS] == [
        'SR - MAIN', 'SR - Return', 'SL - MAIN', 'SL - Return', 'NEW POSITION', None]
    assert ws['B2'].value == '2026 Experts Only'
    assert ('Multi', "125'", 2) in {(ws.cell(rr, 1).value, ws.cell(rr, 2).value, ws.cell(rr, 3).value)
                                    for rr in range(7, 37)}
