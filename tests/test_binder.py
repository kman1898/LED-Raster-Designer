"""The binder: the show's power and data maps bound into one PDF - as a
DRAWING SET (2026-09-08, on the NCMF packet the user held up: "this is a
great example to base our binder off of").

Every sheet is a landscape page of one size - Tabloid 17 x 11 by default
("17x11 i think is great . nice middle gound. but maybe have option for all
sizes"), Letter, ARCH C, ARCH D, A4, A3 to pick - at 200 px/in in page
units and inches x 72 in points, with a border a quarter inch in, a TITLE
BLOCK column 2.4 in wide down the right ("mimic whats in their drawing":
the compass, the prepared-by wordmark, REVISIONS, NOTES, the show / venue /
dates, Designer, Project Manager, Drafter, the SHEET TITLE, the Sheet
Number, the drawing date) and the drawing area to its left. Type sizes are
in inches: a bigger sheet holds more, it does not print bigger type.

Sheets number by SERIES, by subject: 1.1 the overview (the show map as
view 1, POSITIONS / SHOW TOTALS / CONTENTS), 2.n a POWER sheet per screen,
3.n a DATA sheet per screen, 4.n a PULL sheet per position, 5.n the
hardware (a distro, a processor, the totals). A sheet whose tables do not
fit continues on the next number "(cont.)"; the map never splits. Each
map is a numbered VIEW - a bubble with the number and the name in caps
under it ("Yes, bubble and view name").

Layout inside the drawing area: map-left / tables-right in the fewest
3.5-in columns that hold the tables whole, never past half the width;
else the map on top at full width and the tables below in columns; the
map's zoom min(fit, 3x). The tables are packed by _bPack: a block follows
the one before it in its column, moves whole to the next column where it
fits there and not here, and is split at a line only where it is taller
than a column - its head lines repeated where it continues, a band never
left as the last line over nothing.

Type A of binder-mock.html is still the sheet's map: rulers around the
wall (numbering "2"), a bracket per soca / L21-30 outside it with its
home run (the unit named by its TYPE - "Soca 208", "L21-30" - never by a
generic noun: not "Box", not "Multi", not "Breakout"), then Circuits ·
Cables · Facts, and a Gangs table only when the screen has 2fers / 3fers.
The brackets: one distance per side, a bracket stepping out only when its
row span truly overlaps another's. Colour and Printer palettes - the
renderer's printerMode (canvas.js) draws greys, black runs told apart by a
dash per circuit, white discs. Every sheet is painted onto the book canvas
(the pixels the tests read) and RECORDED as a display list - rects, lines,
text and the map bitmap in page units - which /api/export/pdf-from-pages
replays in points, the text set in Helvetica as real PDF text.

The title block's fields live in project.binder (the export dialog edits
them, one undo entry per field; the routes keep them like pullSheet), the
sheet size and the prepared-by name in the preferences.

Run locally (ONE pytest at a time - the browser-test servers use fixed
ports):
    LRD_E2E_PORT=15797 python3 -m pytest tests/test_binder.py -v --browser chromium
"""

import base64
import io
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH_FIXTURE = os.environ.get('LRD_PULL_SMOKE_JSON') or os.path.join(
    '/private/tmp/claude-501',
    '-Users-mattknotts-Nextcloud-LED-LED-Wall-Tech-Raster-Software-LED-Raster-Designer',
    'be6afb3b-7607-4f06-8c12-a10cd58068e9', 'scratchpad', 'experts-only.json')

BOX_WORD = re.compile(r'\b(box|boxes)\b', re.I)
# "breakout" as the generic noun for the power unit is gone (2026-09-07);
# the pull list's "Tru-1 Breakout" CABLE row and the data side's "breakout
# box" keep their names.
BREAKOUT_WORD = re.compile(r'\bbreakouts?\b', re.I)


def _generic_breakout(texts):
    return [t for t in texts if BREAKOUT_WORD.search(t)
            and 'breakout box' not in t.lower() and 'Tru-1 Breakout' not in t]


# The sheets (app-binder.js): inches x 200 in page pixels, inches x 72 in
# points, landscape.
SHEETS = {
    'tabloid': (3400, 2200, [1224, 792]),
    'letter': (2200, 1700, [792, 612]),
    'archd': (7200, 4800, [2592, 1728]),
}
W, H, PT = SHEETS['tabloid']
SCALE = 2
# The frame: the border PAD in, the title block TB_W wide inside it on the
# right, the drawing area DA_PAD in from both.
PAD, TB_W, DA_PAD = 50, 480, 30
DA = {'x': PAD + DA_PAD, 'y': PAD + DA_PAD, 'w': W - PAD - TB_W - PAD - DA_PAD * 2, 'h': H - PAD * 2 - DA_PAD * 2}
TB_X = W - PAD - TB_W
# The tables' column, the gap, the view bubble's room under a map; the
# map's gutters (the rulers' and the brackets' room) and its zoom cap.
COL_W, COL_GAP, BUBBLE_H = 700, 30, 96
DATA_COL_W = 1020        # the data sheet's Ports table asks for a wider column
GUT = {'left': 200, 'right': 180, 'top': 74, 'bottom': 16}
MAP_ZOOM_CAP = 3
# The filler's line heights (app-binder.js): title, heading, band, row.
H4_H, TH_H, BAND_H, ROW_H, BLOCK_GAP = 46, 40, 46, 38, 22


def _side_area(cols=1, col_w=COL_W):
    """The map's area on a Tabloid sheet laid map-left / tables-right in
    `cols` columns of `col_w`."""
    tables = cols * col_w + (cols - 1) * COL_GAP
    return {'x': DA['x'], 'y': DA['y'], 'w': DA['w'] - tables - COL_GAP, 'h': DA['h'] - BUBBLE_H}


def _zoom(area, cols, rows, cab_w, cab_h=None):
    inner_w = area['w'] - GUT['left'] - GUT['right']
    inner_h = area['h'] - GUT['top'] - GUT['bottom']
    return min(inner_w / (cols * cab_w), inner_h / (rows * (cab_h or cab_w)), MAP_ZOOM_CAP)


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# ── served pieces and the route ───────────────────────────────────────────

def test_the_menu_items_the_format_option_and_the_section_are_served(client):
    html = client.get('/').get_data(as_text=True)
    assert re.search(r'data-action="export-binder"[^>]*data-label="Export Binder"', html)
    assert re.search(r'class="menu-option screen-export-only" data-action="export-screen-binder"', html)
    assert '<option value="binder">Binder (PDF)</option>' in html
    assert 'id="export-binder-section"' in html
    for field in ('scope', 'sheet', 'colour', 'printer', 'side-power', 'side-data', 'side-both',
                  'cover', 'pull', 'hardware', 'engineer', 'rev',
                  'venue', 'dates', 'designer', 'pm-name', 'pm-phone', 'pm-email', 'drafter',
                  'prepared-by', 'notes', 'revisions'):
        assert f'id="export-binder-{field}"' in html, field
    # the sheet select carries every size, Tabloid picked
    sec = html[html.index('id="export-binder-section"'):html.index('id="export-scale-row"')]
    for key in ('letter', 'tabloid', 'archc', 'archd', 'a4', 'a3'):
        assert f'<option value="{key}"' in sec, key
    assert '<option value="tabloid" selected>' in sec
    assert 'tail' not in sec.lower()
    # the title block's fields sit in their own raised group
    assert sec.count('class="export-views"') == 2
    assert 'Title block:' in sec
    main_js = open(os.path.join(HERE, '..', 'src', 'static', 'js', 'main.js')).read()
    assert "import './app-binder.js';" in main_js
    # the binder's own strings say circuits - never tails, never Multi,
    # never "breakout" as the generic noun (the data side's "breakout box"
    # keeps its name), and never "Palette" on a sheet
    binder_js = open(os.path.join(HERE, '..', 'src', 'static', 'js', 'app-binder.js')).read()
    code = '\n'.join(l for l in binder_js.splitlines() if not l.strip().startswith('//'))
    literals = re.findall(r"'[^'\n]*'|\"[^\"\n]*\"|`[^`]*`", code)
    assert not [l for l in literals if re.search(r'\btails?\b', l)], [l for l in literals if 'tail' in l]
    # "Multi" may name a CABLE (the GEAR LIST's word); it never names the unit
    assert not [l for l in literals if 'Multi' in l], [l for l in literals if 'Multi' in l]
    generic = [l for l in literals if BREAKOUT_WORD.search(l) and 'breakout box' not in l.lower()]
    assert not generic, generic
    assert not [l for l in literals if 'Palette' in l], [l for l in literals if 'Palette' in l]
    # the modal's textareas wear the inset look the fields do
    css = open(os.path.join(HERE, '..', 'src', 'static', 'css', 'theme.css')).read()
    assert '#export-modal textarea' in css


def _png(color=(255, 0, 0, 255), size=(20, 10)):
    from PIL import Image
    img = Image.new('RGBA', size, color)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()


def test_the_pdf_route_takes_letter_pages_and_no_stamped_label(client_with_layer):
    """The image route still takes real page sizes in points and no view
    label on top; every other caller's request still comes out the way it
    always did."""
    resp = client_with_layer.post('/api/export/pdf-from-images', json={
        'project_name': 'Show', 'labels': False,
        'images': [{'name': f'p{i}', 'data': _png(), 'width': 2200, 'height': 1700,
                    'page_size': [792, 612]} for i in range(3)],
    })
    assert resp.status_code == 200 and resp.data[:5] == b'%PDF-'
    pdf = resp.data
    assert len(re.findall(rb'/Type\s*/Page[^s]', pdf)) == 3
    assert re.search(rb'/MediaBox\s*\[\s*0\s+0\s+792\s+612\s*\]', pdf)
    assert b'Helvetica-Bold' not in pdf
    # the old shape: page = image pixels, label stamped
    old = client_with_layer.post('/api/export/pdf-from-images', json={
        'project_name': 'Show',
        'images': [{'name': 'Pixel Map', 'data': _png(), 'width': 100, 'height': 100}],
    })
    assert old.status_code == 200
    assert re.search(rb'/MediaBox\s*\[\s*0\s+0\s+100\s+100\s*\]', old.data)
    assert b'Helvetica-Bold' in old.data


def test_project_binder_round_trips_through_the_routes(client):
    """project.binder rides the project the way pullSheet does: a POST
    merges it in, a GET serves it back, a PUT (undo, file load) keeps
    whatever the file carries, and a new project has none."""
    binder = {'venue': 'Harbor Field', 'dates': '9/4/26 - 9/6/26', 'designer': 'Northlight',
              'projectManager': {'name': 'Jordan', 'phone': '555', 'email': 'n@x.com'},
              'drafter': 'Sam', 'notes': 'note', 'revisions': [{'date': '7/24/26', 'by': 'MK', 'description': 'Overview'}]}
    assert client.post('/api/project', json={'binder': binder}).status_code == 200
    assert client.get('/api/project').get_json()['binder'] == binder
    proj = client.get('/api/project').get_json()
    proj['binder'] = {**binder, 'venue': 'Elsewhere'}
    resp = client.put('/api/project', json=proj)
    assert resp.status_code == 200 and resp.get_json()['binder']['venue'] == 'Elsewhere'
    assert client.get('/api/project').get_json()['binder']['venue'] == 'Elsewhere'
    assert 'binder' not in client.post('/api/project/new').get_json()


# ── the browser ──────────────────────────────────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

# Two positions: SR Beach (WALL-A and WALL-B, 4 x 3 of 200 px cabinets) and
# the loose CENTER (3 x 5 Edison wall that gangs its first two columns
# through a 2fer). One distro SR: WALL-A's box on number 1 at 125', WALL-B's
# on 2 at 100'. WALL-A's circuits 1 and 2 carry 10' cables and its cable
# tags are ON; WALL-B's circuit 1 carries 6' with the tags off. One H9 with
# a 16 x RJ45 card named SR holding every screen's port.
SEED_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.binder;
    await j('PUT', '/api/project', proj);
    const add = (body) => j('POST', '/api/layer/add', body);
    await add({name: 'WALL-A', columns: 4, rows: 3, cabinet_width: 200, cabinet_height: 200,
               powerVoltage: 208, powerAmperage: 10, panelWatts: 200,
               powerFlowPattern: 'tl-h', powerOrganized: true, flowPattern: 'tl-h',
               processorType: 'novastar-armor'});
    await add({name: 'WALL-B', columns: 4, rows: 3, cabinet_width: 200, cabinet_height: 200,
               powerVoltage: 208, powerAmperage: 10, panelWatts: 250,
               powerFlowPattern: 'tl-h', powerOrganized: true, flowPattern: 'tl-h',
               processorType: 'novastar-armor', offset_x: 900});
    await add({name: 'CENTER', columns: 3, rows: 5, cabinet_width: 128, cabinet_height: 128,
               powerVoltage: 110, powerAmperage: 15, panelWatts: 100,
               powerFlowPattern: 'tl-v', powerOrganized: true, flowPattern: 'tl-h',
               powerSplitters: {enabled: true, maxWays: 2, manual: {merge: [], split: []}},
               processorType: 'novastar-armor', offset_x: 1800});
    let p = await j('GET', '/api/project');
    const A = p.layers.find(l => l.name === 'WALL-A');
    const B = p.layers.find(l => l.name === 'WALL-B');
    p.groups = [{id: 'g1', name: 'SR Beach', layer_ids: [A.id, B.id], routeDataAsOne: false}];
    await j('PUT', '/api/project', p);
    let st = await j('POST', '/api/processors', {deviceId: 'novastar-h9'});
    const pid = st.processors[0].id;
    st = await j('PUT', `/api/processors/${pid}/slots/0`, {deviceId: 'novastar-card-h-16xrj45-2xfiber'});
    const cardId = st.processors[0].slots[0].card.id;
    await j('PUT', `/api/processors/${pid}/cards/${cardId}`, {name: 'SR'});
    p = await j('GET', '/api/project');
    app.project = p;
    app.dedupeProjectLayers('binder_setup');
    const a = app.project.layers.find(l => l.id === A.id);
    const b = app.project.layers.find(l => l.id === B.id);
    const c = app.project.layers.find(l => l.name === 'CENTER');
    app.selectLayer(a);
    const d = app.addDistro({name: 'SR'});
    app.setSocaDistro(a, 1, d.id); app.setSocaNumber(a, 1, 1); app.setSocaLength(a, 1, '125');
    app.setSocaDistro(b, 1, d.id); app.setSocaNumber(b, 1, 2); app.setSocaLength(b, 1, '100');
    app.setCircuitCable(a, 1, {ft: 10, connector: null});
    app.setCircuitCable(a, 2, {ft: 10, connector: null});
    app.setCircuitCable(b, 1, {ft: 6, connector: null});
    a.showPowerCableTags = true;
    b.showPowerCableTags = false;
    await app.refreshProcessors();
    for (const l of [a, b, c]) {
        await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
                                     {layerId: String(l.id), cardId});
    }
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    window.canvasRenderer.render();
    app.resetHistory('Binder Seed');
    return { a: a.id, b: b.id, c: c.id, distroId: d.id, procId: pid, cardId,
             centerRunIds: app.screenCircuits(c).map(x => x.runIds || [x.num]),
             aCircuits: app.screenCircuits(a).length };
}"""

SHOW = """{ sheet: 'tabloid', palette: 'colour', sides: {power: true, data: true}, scope: {kind: 'show'},
            cover: true, pull: true, hardware: true }"""
# The whole-show options as JSON, for evaluate() calls that take them as data.
_SHOW_JSON = ('{"sheet": "tabloid", "palette": "colour", "sides": {"power": true, "data": true}, "scope": {"kind": "show"},'
              ' "cover": true, "pull": true, "hardware": true}')

# The set on two positions: 11 sheets.
PLAN = [
    ['overview', '1.1', 'Overview'],
    ['power', '2.1', 'WALL-A - Power'], ['power', '2.2', 'WALL-B - Power'], ['power', '2.3', 'CENTER - Power'],
    ['data', '3.1', 'WALL-A - Data'], ['data', '3.2', 'WALL-B - Data'], ['data', '3.3', 'CENTER - Data'],
    ['pull', '4.1', 'SR Beach - Pull'], ['pull', '4.2', 'CENTER - Pull'],
    ['distro', '5.1', 'SR - Distro'],
    ['processor', '5.2', 'H9 - Processor'],
    ['totals', '5.3', 'Pull list - all positions'],
]


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(500)
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(1200)
    assert ids['centerRunIds'] == [[1, 2], [3]], f'fixture: CENTER must gang columns 1+2: {ids}'
    assert ids['aCircuits'] == 2, f'fixture: WALL-A is two circuits: {ids}'
    ids['errors'] = errors
    yield pg, ids
    context.close()


def _plan(pg, opts_js):
    return pg.evaluate("() => window.app.planBinder(%s).map(p => [p.kind, p.number, p.title])" % opts_js)


RENDER_JS = """([opts, title]) => {
    const app = window.app;
    const plan = app.planBinder(opts);
    const idx = plan.findIndex(p => p.title === title);
    if (idx < 0) return { missing: title, plan: plan.map(p => p.title) };
    const r = app.renderBinderPage(opts, idx);
    const c = r.canvas, ctx = c.getContext('2d');
    const d = ctx.getImageData(0, 0, c.width, c.height).data;
    let coloured = 0, samples = 0;
    for (let i = 0; i < d.length; i += 4 * 61) {
        samples++;
        const R = d[i], G = d[i + 1], B = d[i + 2];
        if (Math.abs(R - G) > 10 || Math.abs(G - B) > 10 || Math.abs(R - B) > 10) coloured++;
    }
    const cols = r.record.ops.filter(o => o.op === 'text' && o.size === 25 && o.weight === 700);
    return { texts: r.texts, textInfo: r.textInfo, mapTexts: r.mapTexts, dashes: r.dashes,
             map: r.map, brackets: r.brackets, bubble: r.bubble, titleBlock: r.titleBlock,
             coloured, samples, pages: r.pages, index: idx, width: c.width, height: c.height,
             page: r.page, sheet: r.sheet, headings: cols.map(o => [o.text, o.x, o.y]) };
}"""


def _render(pg, opts_js, title):
    out = pg.evaluate("(t) => (%s)([%s, t])" % (RENDER_JS, opts_js), title)
    assert 'missing' not in out, out
    return out


def _on_map(map_texts, label):
    """Is `label` drawn on the map - whole, or stacked? How a label disc
    breaks a label is the renderer's own rule (canvas.js: a spaced label at
    its spaces, an unspaced one at a hyphen or a letter-digit seam, the
    pieces rejoining to the label exactly); the binder only asks that the
    label is there. Consecutive fillText pieces that rejoin to the label,
    with nothing or a space between, count as the label."""
    if label in map_texts:
        return True
    for i in range(len(map_texts)):
        for n in range(2, 5):
            pieces = map_texts[i:i + n]
            if len(pieces) < n:
                break
            if ''.join(pieces) == label or ' '.join(pieces) == label:
                return True
    return False


def _title_block(texts, sheet_title, number, show='Untitled Project'):
    """The title block's texts, in the order the column draws them."""
    for t in ('US', 'DS', 'SR', 'SL', 'Revisions:', 'No.', 'Date', 'By', 'Description', 'Notes',
              show, 'Designer:', 'Project Manager:', 'Drafter:', sheet_title, 'Sheet Number', number, 'Drawing Date'):
        assert t in texts, (t, texts[:60])
    order = [texts.index(t) for t in ('US', 'Revisions:', 'Notes', show, 'Designer:', sheet_title, 'Sheet Number', number)]
    assert order == sorted(order), order


def test_the_sheets_come_in_series_by_subject(page):
    """1.1 the overview; 2.n power per screen in position order; 3.n data
    per screen; 4.n pull per position; 5.n the hardware then the totals.
    Every sheet is the Tabloid default."""
    pg, ids = page
    plan = _plan(pg, SHOW)
    assert plan == PLAN
    full = pg.evaluate("(o) => window.app.planBinder(o)", json.loads(_SHOW_JSON))
    assert all((p['w'], p['h'], p['sheet']) == (W, H, 'tabloid') for p in full), full
    assert [p['view'] for p in full] == [1, 2, 3, 4, 5, 6, 7, None, None, None, None, None]
    assert all(p['sheetTitle'] == p['sheetTitle'].upper() for p in full)
    assert [p['sheetTitle'] for p in full][:4] == ['OVERVIEW', 'WALL-A · POWER', 'WALL-B · POWER', 'CENTER · POWER']
    assert ids['errors'] == []
    # power only, no extras: just the maps, 2.1 - 2.3
    only = _plan(pg, SHOW.replace("data: true", "data: false")
                 .replace("cover: true, pull: true, hardware: true", "cover: false, pull: false, hardware: false"))
    assert only == [['power', '2.1', 'WALL-A - Power'], ['power', '2.2', 'WALL-B - Power'], ['power', '2.3', 'CENTER - Power']]


def test_the_power_sheet_carries_its_title_block_and_says_home_run_once_per_box(page):
    pg, ids = page
    out = _render(pg, SHOW, 'WALL-A - Power')
    texts = out['texts']
    # painted at 2x, the Tabloid sheet
    assert out['width'] == W * SCALE and out['height'] == H * SCALE
    assert out['sheet']['key'] == 'tabloid' and out['sheet']['pt'] == PT
    _title_block(texts, 'WALL-A · POWER', '2.1')
    assert 'rev 1.0' in texts
    # the wordmark: the prepared-by preference, else the engineer, else the app
    mark = pg.evaluate("() => window.app.getPreparedBy().toUpperCase()")
    assert mark in texts and mark in ('LED RASTER DESIGNER', pg.evaluate("() => window.app.getEngineerName().toUpperCase()"))
    bands = [t for t in texts if 'home run' in t]
    assert bands == ["SR1 · Soca 208 · 125' home run · 2 circuits"], texts
    # Multi is a cable row, never a heading and never the breakout's name
    assert not any(t.strip() == 'MULTI' for t in texts), [t for t in texts if t.strip() == 'MULTI']
    assert not any('Multi' in b for b in bands), bands
    assert not any(re.search(r'\btails?\b', t.lower()) for t in texts), [t for t in texts if 'tail' in t.lower()]
    # the bracket outside the wall carries the box and its home run once
    assert texts.count("SR1 · 125'") == 1
    # the circuit rows under CIRCUIT · NO. · PANELS · AMPS · CABLE, the
    # cable typed on each, the cables table, the facts
    i = texts.index('CIRCUITS')
    assert texts[i + 1:i + 6] == ['CIRCUIT', 'NO.', 'PANELS', 'AMPS', 'CABLE']
    assert 'SR1-1' in texts and 'SR1-2' in texts
    assert texts.count("10' True1") >= 2
    assert 'CABLES THIS SCREEN' in texts and 'FACTS' in texts
    assert 'Multi' in texts and "125'" in texts      # the breakout's cable, in the GEAR LIST's word
    assert 'Tru-1 Breakout' in texts
    assert 'GANGS' not in texts
    assert not [t for t in texts if 'Palette' in t]
    # the view bubble under the map: view 2, the sheet's name
    assert out['bubble']['number'] == 2 and out['bubble']['name'] == 'WALL-A · POWER'
    assert out['page']['layout'] == 'side' and out['page']['cols'] == 1


def test_gangs_are_listed_only_where_a_screen_has_them(page):
    pg, ids = page
    plain = _render(pg, SHOW, 'WALL-B - Power')['texts']
    assert 'GANGS' not in plain and '2fer' not in plain
    ganged = _render(pg, SHOW, 'CENTER - Power')['texts']
    assert 'GANGS' in ganged
    i = ganged.index('GANGS')
    assert ganged[i:i + 7] == ['GANGS', 'CIRCUIT', 'GANG', 'AMPS', ganged[i + 4], '2fer', ganged[i + 6]]
    assert ganged[i + 4].endswith('1') or ganged[i + 4]   # the shared circuit's label
    assert 'Edison 2fer' in ganged


def test_the_rulers_number_every_fifth_column_and_the_ends_in_bold(page):
    pg, ids = page
    out = _render(pg, SHOW, 'CENTER - Power')
    rulers = [t for t in out['textInfo'] if t['size'] == 22 and t['weight'] == 700]
    assert [t['text'] for t in rulers] == ['1', '3', '1', '2', '3', '4', '5'], rulers
    assert all(t['weight'] == 700 for t in rulers)


def test_the_printer_sheet_has_no_colour_and_a_dash_per_circuit(page):
    pg, ids = page
    printer = SHOW.replace("palette: 'colour'", "palette: 'printer'")
    out = _render(pg, printer, 'WALL-A - Power')
    assert out['coloured'] == 0, f'{out["coloured"]} of {out["samples"]} samples carry colour'
    patterns = sorted({tuple(d) for d in out['dashes']})
    non_solid = [p for p in patterns if p]
    # two circuits: the first solid, the second its own dash
    assert len(non_solid) == 1 and non_solid[0][0] > 0, patterns
    assert () in patterns
    # the same sheet in colour: colour on the wall, every run solid
    colour = _render(pg, SHOW, 'WALL-A - Power')
    assert colour['coloured'] > 0
    assert not [d for d in colour['dashes'] if d]
    # the printer band is drawn as a rule, the text the same
    assert [t for t in out['texts'] if 'home run' in t] == [t for t in colour['texts'] if 'home run' in t]


def test_cable_tags_follow_the_screens_switch(page):
    pg, ids = page
    on = _render(pg, SHOW, 'WALL-A - Power')['mapTexts']
    assert "10' True1" in on and _on_map(on, 'SR1-1'), on
    off = _render(pg, SHOW, 'WALL-B - Power')['mapTexts']
    assert _on_map(off, 'SR2-1') and "6' True1" not in off, off
    # flip WALL-A off, and the tag leaves the map
    pg.evaluate("(id) => { window.app.project.layers.find(l => l.id === id).showPowerCableTags = false; }", ids['a'])
    try:
        flipped = _render(pg, SHOW, 'WALL-A - Power')['mapTexts']
        assert "10' True1" not in flipped and _on_map(flipped, 'SR1-1'), flipped
    finally:
        pg.evaluate("(id) => { window.app.project.layers.find(l => l.id === id).showPowerCableTags = true; }", ids['a'])


def test_a_single_screen_scope_yields_only_that_screens_sheets(page):
    pg, ids = page
    one = _plan(pg, """{ sheet: 'tabloid', palette: 'colour', sides: {power: true, data: true},
                         scope: {kind: 'screen', layerId: '%s'}, cover: false, pull: false, hardware: false }""" % ids['b'])
    assert one == [['power', '2.1', 'WALL-B - Power'], ['data', '3.1', 'WALL-B - Data']]
    ticked = _plan(pg, """{ sheet: 'tabloid', palette: 'colour', sides: {power: true, data: false},
                            scope: {kind: 'screen', layerId: '%s'}, cover: false, pull: true, hardware: false }""" % ids['b'])
    assert ticked == [['power', '2.1', 'WALL-B - Power'], ['pull', '4.1', 'SR Beach - Pull'],
                      ['totals', '5.1', 'Pull list - all positions']]
    # the dialog: the canvas's right-click presets the scope and unticks the extras
    out = pg.evaluate("""(id) => {
        const app = window.app;
        const layer = app.project.layers.find(l => l.id === id);
        app.openScreenBinderExport(layer);
        const v = (i) => document.getElementById(i).value;
        const on = (i) => document.getElementById(i).checked;
        const vis = (i) => document.getElementById(i).style.display !== 'none';
        const out = { format: v('export-format'), scope: v('export-binder-scope'), sheet: v('export-binder-sheet'),
                      cover: on('export-binder-cover'), pull: on('export-binder-pull'), hardware: on('export-binder-hardware'),
                      section: vis('export-binder-section'), views: vis('export-views-section'),
                      canvases: vis('export-canvases-section'), preview: document.getElementById('export-preview').textContent,
                      opts: app.readBinderOptions() };
        document.getElementById('export-cancel').click();
        return out;
    }""", ids['b'])
    assert out['format'] == 'binder' and out['scope'] == f"screen:{ids['b']}" and out['sheet'] == 'tabloid'
    assert (out['cover'], out['pull'], out['hardware']) == (False, False, False)
    assert out['section'] and not out['views'] and not out['canvases']
    assert out['preview'].endswith('WALL-B - binder rev 1.0.pdf')
    assert out['opts']['scope'] == {'kind': 'screen', 'layerId': str(ids['b'])} and out['opts']['sheet'] == 'tabloid'
    # the menu item shows for a screen under the cursor / selected, never on the dock
    menu = pg.evaluate("""() => {
        const app = window.app;
        const cr = window.canvasRenderer;
        const r = cr.canvas.getBoundingClientRect();
        app.showContextMenu(r.left + r.width / 2, r.top + r.height / 2);
        const el = document.querySelector('.menu-option.screen-export-only');
        const shown = el.style.display !== 'none';
        app.hideContextMenu();
        return { shown, label: el.textContent, layer: app._binderMenuLayer && app._binderMenuLayer.name };
    }""")
    assert menu['shown'] and menu['label'].startswith('Export this screen')
    assert menu['layer'] in ('WALL-A', 'WALL-B', 'CENTER')


def test_every_sheet_is_the_picked_size(page):
    """Letter and ARCH D picked: every sheet that size in page pixels and
    in points, the canvas at 2x up to Tabloid and 1x for the ARCH sheets;
    an unknown key falls back to Tabloid. Type stays the same size in
    inches - the headings are 25 px on every sheet."""
    pg, ids = page
    for key, (w, h, pt) in SHEETS.items():
        opts = json.loads(_SHOW_JSON)
        opts['sheet'] = key
        full = pg.evaluate("(o) => window.app.planBinder(o)", opts)
        assert len(full) == len(PLAN)
        assert all((p['w'], p['h'], p['sheet']) == (w, h, key) for p in full), (key, full[:2])
        out = pg.evaluate("""(o) => {
            const app = window.app;
            const r = app.renderBinderPage(o, 1);
            return { w: r.canvas.width, h: r.canvas.height, rec: [r.record.width, r.record.height, r.record.page_size],
                     sizes: [...new Set(r.record.ops.filter(x => x.op === 'text').map(x => x.size))].sort((a, b) => a - b),
                     texts: r.texts };
        }""", opts)
        scale = 1 if key == 'archd' else 2
        assert (out['w'], out['h']) == (w * scale, h * scale), (key, out)
        assert out['rec'] == [w, h, pt], (key, out['rec'])
        assert 25 in out['sizes'] and 24 in out['sizes'] and 56 in out['sizes'], (key, out['sizes'])
        _title_block(out['texts'], 'WALL-A · POWER', '2.1')
    opts = json.loads(_SHOW_JSON)
    opts['sheet'] = 'napkin'
    assert pg.evaluate("(o) => window.app.planBinder(o)[0].sheet", opts) == 'tabloid'


def test_the_pdf_route_receives_one_display_list_per_sheet(page):
    """exportBinder posts every sheet to /api/export/pdf-from-pages as a
    display list - { name, width, height, page_size, ops, images } in page
    units, the Tabloid size in points - and no sheet bitmap at all; the
    maps and the overview's raster ride inside the records as images. The
    PDF that comes back is saved through the picker under the binder's
    name with the rev."""
    pg, ids = page
    out = pg.evaluate("""async (opts) => {
        const app = window.app;
        const realFetch = window.fetch;
        const saved = app.saveBlobWithPicker;
        const seen = { posts: [], saved: null, urls: [] };
        window.fetch = async (url, init) => {
            if (String(url).includes('/api/export/pdf-from-')) {
                seen.urls.push(String(url));
                seen.posts.push(JSON.parse(init.body));
                return { ok: true, blob: async () => new Blob(['%PDF-fake'], {type: 'application/pdf'}) };
            }
            return realFetch(url, init);
        };
        app.saveBlobWithPicker = async (blob, filename, mime) => { seen.saved = { filename, mime, size: blob.size }; };
        // the dialog's state is what exportBinder reads
        document.getElementById('export-format').value = 'binder';
        document.getElementById('export-format').dispatchEvent(new Event('change'));
        document.getElementById('export-binder-scope').value = 'show';
        document.getElementById('export-binder-scope').dispatchEvent(new Event('change'));
        document.getElementById('export-binder-printer').checked = true;
        try {
            const res = await app.exportBinder('Two Positions');
            const body = seen.posts[0];
            const plan = app.planBinder(app.readBinderOptions());
            const kinds = (p) => [...new Set(p.ops.map(o => o.op))].sort();
            return { pages: res.pages, posts: seen.posts.length, urls: seen.urls, keys: Object.keys(body).sort(),
                     n: body.pages.length, pageKeys: body.pages.map(p => Object.keys(p).sort()),
                     names: body.pages.map(p => p.name), sizes: body.pages.map(p => p.page_size),
                     dims: body.pages.map(p => [p.width, p.height]),
                     kinds: body.pages.map(kinds),
                     texts: body.pages.map(p => p.ops.filter(o => o.op === 'text').length),
                     imageIds: body.pages.map(p => Object.keys(p.images)),
                     imageOps: body.pages.map(p => p.ops.filter(o => o.op === 'image').map(o => o.id)),
                     png: body.pages.every(p => Object.values(p.images).every(d => d.startsWith('data:image/png;base64,'))),
                     bitmaps: body.pages.some(p => 'dataUrl' in p || 'data' in p),
                     firstOps: body.pages[0].ops.slice(0, 3),
                     saved: seen.saved, plan: plan.length,
                     kindsByPage: plan.map(p => p.kind) };
        } finally {
            window.fetch = realFetch;
            app.saveBlobWithPicker = saved;
            document.getElementById('export-binder-colour').checked = true;
        }
    }""", None)
    assert out['posts'] == 1 and out['urls'] == ['/api/export/pdf-from-pages']
    assert out['keys'] == ['pages', 'project_name']
    assert out['n'] == out['plan'] == out['pages'] == len(PLAN)
    assert all(k == ['height', 'images', 'name', 'ops', 'page_size', 'width'] for k in out['pageKeys']), out['pageKeys']
    assert not out['bitmaps'], 'the export sends no sheet bitmap'
    assert out['names'][0] == 'Overview' and out['names'][-1] == 'Pull list - all positions'
    assert out['dims'] == [[W, H]] * len(PLAN), out['dims']
    assert out['sizes'] == [PT] * len(PLAN), out['sizes']
    # every sheet is text, rects and lines at least; the first ops are the
    # sheet's white and its border
    assert all('text' in k and 'rect' in k and 'line' in k for k in out['kinds']), out['kinds']
    assert all(n > 0 for n in out['texts']), out['texts']
    assert out['firstOps'][0] == {'op': 'rect', 'x': 0, 'y': 0, 'w': W, 'h': H, 'fill': '#ffffff'}
    assert out['firstOps'][1] == {'op': 'rect', 'x': PAD, 'y': PAD, 'w': W - PAD * 2, 'h': H - PAD * 2, 'stroke': '#111111', 'width': 3}
    # only the map sheets and the overview (its raster) carry images - one
    # each, the op naming the bitmap the record holds, as a PNG
    for kind, ids_, ops_ in zip(out['kindsByPage'], out['imageIds'], out['imageOps']):
        if kind in ('overview', 'power', 'data'):
            assert len(ids_) == 1 and ops_ == ids_, (kind, ids_, ops_)
        else:
            assert ids_ == [] and ops_ == [], (kind, ids_, ops_)
    assert out['png']
    assert out['saved'] == {'filename': 'Two Positions - binder rev 1.0.pdf', 'mime': 'application/pdf', 'size': 9}


def _record(pg, opts, title, bitmaps=False):
    """One sheet's record (the display list) with the texts it logged, from
    renderBinderPage; `opts` as JSON."""
    out = pg.evaluate("""([opts, title, bitmaps]) => {
        const app = window.app;
        const plan = app.planBinder(opts);
        const idx = plan.findIndex(p => p.title === title);
        if (idx < 0) return { missing: title, plan: plan.map(p => p.title) };
        const r = app.renderBinderPage(opts, idx, { bitmaps });
        const rec = r.record;
        return { texts: r.texts, textInfo: r.textInfo, kind: plan[idx].kind, page: plan[idx],
                 record: rec && { name: rec.name, width: rec.width, height: rec.height, page_size: rec.page_size,
                                  ops: rec.ops, imageIds: Object.keys(rec.images),
                                  imageSizes: Object.fromEntries(Object.entries(rec.images).map(([k, v]) => [k, v.length])),
                                  dataUrl: rec.dataUrl ? rec.dataUrl.slice(0, 22) : null },
                 map: r.map, brackets: r.brackets, bubble: r.bubble };
    }""", [opts, title, bitmaps])
    assert 'missing' not in out, out
    return out


def _texts_match(op_texts, log_texts):
    """The recorded text ops, in order, are the log's texts - save that a
    two-line cell ("A / B", _bTextTwoLines) is logged once and drawn
    twice."""
    i = 0
    for t in log_texts:
        if i < len(op_texts) and op_texts[i] == t:
            i += 1
            continue
        parts = t.split(' / ')
        if len(parts) == 2 and op_texts[i:i + 2] == parts:
            i += 2
            continue
        return False, (t, op_texts[i:i + 3])
    return i == len(op_texts), (len(op_texts), len(log_texts))


def test_every_sheet_record_is_a_display_list_of_its_texts(page):
    """Every sheet's record carries ops, its text ops the very texts the
    sheet logged, in order, the title block's first; the map sheets and
    the overview carry one image (the map, the raster) and no other sheet
    carries any; the wordmark and the brackets' labels are recorded turned
    a quarter with their anchor, never as a raw transform; every op is in
    page units with its colour as hex; and the record has no bitmap of the
    sheet unless asked."""
    pg, ids = page
    plan = _plan(pg, SHOW)
    assert len(plan) == len(PLAN)
    for kind, number, title in plan:
        out = _record(pg, json.loads(_SHOW_JSON), title)
        rec = out['record']
        assert rec, title
        assert rec['name'] == title and rec['width'] == W and rec['height'] == H
        assert rec['page_size'] == PT
        assert rec['dataUrl'] is None
        ops = rec['ops']
        assert ops and ops[0] == {'op': 'rect', 'x': 0, 'y': 0, 'w': W, 'h': H, 'fill': '#ffffff'}, ops[:2]
        assert {o['op'] for o in ops} <= {'rect', 'line', 'text', 'image'}, title
        texts = [o for o in ops if o['op'] == 'text']
        assert texts, title
        ok, why = _texts_match([o['text'] for o in texts], out['texts'])
        assert ok, (title, why)
        for o in texts:
            assert set(o) == {'op', 'text', 'x', 'y', 'size', 'weight', 'align', 'baseline', 'color', 'rotate'}, o
            assert re.fullmatch(r'#[0-9a-f]{6}', o['color']) and o['align'] in ('left', 'center', 'right'), o
            assert o['baseline'] == 'alphabetic' and o['weight'] in (400, 600, 700, 800), o
            assert 0 <= o['x'] <= W and 0 <= o['y'] <= H, (title, o)
        # the title block first: the compass's US, then the sheet number
        # set large in the corner
        assert (texts[0]['text'], texts[0]['size'], texts[0]['weight']) == ('US', 24, 700), texts[0]
        numbers = [o for o in texts if o['size'] == 56]
        assert [(o['text'], o['weight']) for o in numbers] == [(number, 800)], numbers
        assert numbers[0]['x'] > TB_X and numbers[0]['y'] > H - PAD - 150, numbers[0]
        for o in ops:
            if o['op'] == 'rect':
                assert re.fullmatch(r'#[0-9a-f]{6}', o.get('fill') or o.get('stroke')), o
                assert 0 <= o['x'] and o['x'] + o['w'] <= W + 1 and o['w'] > 0 and o['h'] > 0, (title, o)
            elif o['op'] == 'line':
                assert len(o['points']) >= 2 and o['width'] > 0 and isinstance(o['dash'], list), o
                assert re.fullmatch(r'#[0-9a-f]{6}', o['stroke']), o
        images = [o for o in ops if o['op'] == 'image']
        if kind in ('overview', 'power', 'data'):
            assert len(images) == 1 and [o['id'] for o in images] == rec['imageIds'], (title, images, rec['imageIds'])
            im = images[0]
            assert im['w'] > 0 and im['h'] > 0 and im['x'] >= DA['x'] and im['x'] + im['w'] <= DA['x'] + DA['w'] + 1, im
            assert rec['imageSizes'][im['id']] > 1000
            if kind != 'overview':
                assert (im['x'], im['y'], im['w'], im['h']) == (out['map']['area']['x'], out['map']['area']['y'],
                                                                out['map']['area']['w'], out['map']['area']['h']), (im, out['map'])
            # the view bubble sits under the image, in the drawing area
            b = out['bubble']
            assert b and b['number'] == out['page']['view'] and b['name'] == out['page']['sheetTitle'], (b, out['page'])
            assert b['y'] - b['r'] >= im['y'] + im['h'] and b['y'] + b['r'] <= DA['y'] + DA['h'] + 1, (b, im)
            # the bubble is a polyline circle, a line op of many points
            circles = [o for o in ops if o['op'] == 'line' and len(o['points']) == 37]
            assert len(circles) == 1, len(circles)
        else:
            assert images == [] and rec['imageIds'] == [], (title, images)
            assert out['bubble'] is None
        # the wordmark is a rotated text op on every sheet; a bracket label
        # is a rotated text op at its anchor; every other text lies flat
        turned = [o for o in texts if o['rotate']]
        marks = [o for o in turned if o['weight'] == 800]
        assert len(marks) == 1 and abs(marks[0]['rotate'] + 1.5707963) < 1e-4 and marks[0]['x'] > TB_X, marks
        labels = [o for o in turned if o['weight'] != 800]
        if kind == 'power':
            assert len(labels) == len(out['brackets']) >= 1, (title, labels)
            for o, b in zip(labels, out['brackets']):
                assert abs(abs(o['rotate']) - 1.5707963) < 1e-4 and (o['rotate'] > 0) == (b['side'] == 'R'), (o, b)
                assert o['align'] == 'center' and o['weight'] == 700 and o['size'] == 28, o
                # the anchor: 24 out from the bracket, the baseline 9 in
                # from centre, turned - the text is centred on the span
                dir_ = 1 if b['side'] == 'R' else -1
                assert abs(o['x'] - (b['x'] + dir_ * 24 - dir_ * 9)) < 0.6, (o, b)
                assert abs(o['y'] - (b['y1'] + b['y2']) / 2) < 0.6, (o, b)
        else:
            assert labels == [], (title, labels)
    # asked for, the record carries the painted sheet as a PNG at 2x
    out = _record(pg, json.loads(_SHOW_JSON), 'Overview', bitmaps=True)
    assert out['record']['dataUrl'] == 'data:image/png;base64,'


def test_the_map_carries_no_screen_name_plate_but_the_export_still_does(page):
    """"the main label is over the circuits so that is bad": the binder's
    map draws no screen-name plate - the title block names the screen - on
    the power and the data sheet alike, and the ordinary export (exportMode
    without the binder's flag) paints the name exactly as before."""
    pg, ids = page
    for title in ('WALL-A - Power', 'WALL-A - Data'):
        out = _render(pg, SHOW, title)
        assert not _on_map(out['mapTexts'], 'WALL-A'), (title, out['mapTexts'])
        assert 'WALL-A · POWER' in out['texts'] or 'WALL-A · DATA' in out['texts']
        assert _on_map(out['mapTexts'], 'SR1-1') or _on_map(out['mapTexts'], 'SR-1'), out['mapTexts']
    # the same exportMode render with the binder's flag pinned off is the
    # ordinary export, and it paints the name
    export = pg.evaluate("""([opts, title]) => {
        const app = window.app, r = window.canvasRenderer;
        const idx = app.planBinder(opts).findIndex(p => p.title === title);
        Object.defineProperty(r, 'hideScreenNames', { get: () => false, set: () => {}, configurable: true });
        try {
            return { mapTexts: app.renderBinderPage(opts, idx).mapTexts };
        } finally {
            delete r.hideScreenNames;
            r.hideScreenNames = false;
        }
    }""", [json.loads(_SHOW_JSON), 'WALL-A - Power'])
    assert _on_map(export['mapTexts'], 'WALL-A'), export['mapTexts'][:40]
    assert pg.evaluate("() => window.canvasRenderer.hideScreenNames") is False


def test_no_sheet_says_box_breakout_or_palette(page):
    """No sheet text says box ("I dont like calling them boxes"), none
    says breakout as the generic noun ("no need to call it a breakout") -
    save a data-side breakout box's own name and the pull list's "Tru-1
    Breakout" cable row - and none says Palette. The distro sheet names
    its table by what it lists: "2 Soca 208", the units by type."""
    pg, ids = page
    n = pg.evaluate("(o) => window.app.planBinder(o).length", json.loads(_SHOW_JSON))
    assert n == len(PLAN)
    for idx in range(n):
        texts = pg.evaluate("([o, i]) => window.app.renderBinderPage(o, i).texts", [json.loads(_SHOW_JSON), idx])
        boxy = [t for t in texts if BOX_WORD.search(t) and 'breakout box' not in t.lower()]
        assert not boxy, (idx, boxy)
        assert not _generic_breakout(texts), (idx, _generic_breakout(texts))
        assert not [t for t in texts if 'palette' in t.lower()], (idx, texts)
        assert not [t for t in texts if re.search(r'\btails?\b', t.lower())], (idx, texts)
    distro = _render(pg, SHOW, 'SR - Distro')['texts']
    i = distro.index('2 SOCA 208')
    assert distro[i + 1] == 'NAME' and distro[i + 2] == 'TYPE' and 'SR 1' in distro and 'SR 2' in distro
    assert 'BREAKOUTS' not in distro and 'Breakouts' not in distro
    assert [t for t in distro if re.fullmatch(r'\d+ on 2 Soca 208', t)], distro


def _map_of(out):
    m = out['map']
    assert m, out.keys()
    return m


def test_the_map_takes_the_width_the_tables_leave(page):
    """Map-left / tables-right: the tables of these screens hold in one
    column, so the map has the drawing area less that column, the wall
    scaled UNIFORMLY to fit it between the gutters (a tiny wall stops at
    3x). WALL-A (4 x 3 of 200 px) fills the area's width; CENTER (3 x 5 of
    128 px) is tiny, its height stops it under the cap. The table headings
    sit right of the map, never over it; the bubble under the map."""
    pg, ids = page
    for title, cols, rows, cab in (('WALL-A - Power', 4, 3, 200), ('WALL-A - Data', 4, 3, 200),
                                   ('CENTER - Power', 3, 5, 128)):
        col_w = DATA_COL_W if title.endswith('Data') else COL_W
        area = _side_area(1, col_w)
        out = _render(pg, SHOW, title)
        assert out['page']['layout'] == 'side' and out['page']['cols'] == 1, out['page']
        m = _map_of(out)
        want = cols / rows
        assert abs(m['w'] / m['h'] - want) / want < 0.01, (title, m)
        zoom = _zoom(area, cols, rows, cab)
        assert abs(m['w'] - cols * cab * zoom) <= 1 and abs(m['zoom'] - zoom) < 1e-6, (title, m, zoom)
        assert m['area'] == {**area, 'h': m['area']['h']} and m['area']['h'] <= area['h'], (m['area'], area)
        assert m['x'] >= area['x'] and m['x'] + m['w'] <= area['x'] + area['w'], (title, m)
        # every table heading right of the map's area, inside the drawing area
        heads = out['headings']
        assert heads and all(x >= area['x'] + area['w'] + COL_GAP - 1 for _t, x, _y in heads), heads
        assert all(x + col_w <= DA['x'] + DA['w'] + 1 for _t, x, _y in heads), heads
        assert 'FACTS' in out['texts'] and 'CABLES THIS SCREEN' in out['texts'], title
        assert not [t for t in out['texts'] if '(cont.)' in t or '(CONT.)' in t], title
        b = out['bubble']
        assert b['y'] - b['r'] >= m['area']['y'] + m['area']['h'], (b, m['area'])
    area = _side_area(1)
    a = _render(pg, SHOW, 'WALL-A - Power')
    assert _map_of(a)['w'] / area['w'] > 0.8, a['map']
    c = _render(pg, SHOW, 'CENTER - Power')
    assert abs(_map_of(c)['zoom'] - (area['h'] - GUT['top'] - GUT['bottom']) / (5 * 128)) < 1e-6 \
        and _map_of(c)['zoom'] < MAP_ZOOM_CAP, c['map']


def test_brackets_share_one_distance_unless_their_spans_overlap(page):
    """One bracket distance per side: brackets whose row spans do not
    overlap sit at the same x; a bracket steps out only where its span
    truly crosses another's. WALL-B's two circuits are rows 1-2 and row 3:
    one unit each, no overlap, one x. On WALL-A one unit is crafted over
    both circuits (rows 1-3) and a second over circuit 2 alone (row 3) -
    the spans cross, so the second steps out one level."""
    pg, ids = page
    js = """([layerId, boxes, area]) => {
        const app = window.app;
        const layer = app.project.layers.find(l => l.id === layerId);
        const c = document.createElement('canvas'); c.width = 3400; c.height = 2200;
        const ctx = c.getContext('2d');
        const book = { ctx, measureCtx: ctx, meta: { palette: 'colour' }, page: { painting: false }, scale: 2,
                       log: { texts: [], textInfo: [], mapTexts: [], dashes: [] } };
        const geo = app._bMap(book, layer, 'power', area);
        book.page.painting = true;      // the brackets' text is logged as drawn
        app._bBoxBrackets(book, layer, { boxes }, geo);
        const rows = app.screenCircuits(layer).map(x => [x.num,
            Math.min(...x.panels.map(p => p.row)), Math.max(...x.panels.map(p => p.row))]);
        return { brackets: book.log.brackets || [], rows, wall: geo.wall, texts: book.log.texts };
    }"""
    area = _side_area(1)
    boxes = [{'name': 'K1', 'homeRun': '100', 'circuits': [{'num': 1}]},
             {'name': 'K2', 'homeRun': '100', 'circuits': [{'num': 2}]}]
    b = pg.evaluate(js, [ids['b'], boxes, area])
    assert b['rows'] == [[1, 0, 1], [2, 2, 2]], f"fixture: WALL-B's circuits are rows 1-2 and row 3: {b['rows']}"
    k1, k2 = b['brackets']
    assert (k1['name'], k2['name']) == ('K1', 'K2')
    assert k1['side'] == k2['side'] and k1['depth'] == 0 and k2['depth'] == 0, b['brackets']
    assert k1['x'] == k2['x'], b['brackets']
    assert abs(k1['y2'] - k2['y1']) < 2, b['brackets']          # they share an edge
    crossing = [{'name': 'K1', 'homeRun': '100', 'circuits': [{'num': 1}, {'num': 2}]},
                {'name': 'K2', 'homeRun': '100', 'circuits': [{'num': 2}]}]
    a = pg.evaluate(js, [ids['a'], crossing, area])
    assert a['rows'] == [[1, 0, 1], [2, 2, 2]], a['rows']
    k1, k2 = a['brackets']
    assert k1['y1'] < k2['y1'] < k1['y2'], a['brackets']            # the spans cross
    assert k1['side'] == k2['side'] and k1['depth'] == 0 and k2['depth'] == 1, a['brackets']
    step = k2['x'] - k1['x']
    assert (step > 0) == (k1['side'] == 'R') and abs(step) == 78, a['brackets']
    # the labels: name and home run, once each
    assert a['texts'] == ["K1 · 100'", "K2 · 100'"], a['texts']


PACK_JS = """([colH, maxCols]) => {
    const app = window.app;
    const c = document.createElement('canvas'); c.width = 3400; c.height = 2200;
    const ctx = c.getContext('2d');
    const book = { ctx, measureCtx: ctx, meta: { palette: 'colour' }, page: { painting: true },
                   log: { texts: [], textInfo: [], mapTexts: [], dashes: [] } };
    const table = (title, bands) => {
        const rows = [];
        for (const [name, n] of bands) { rows.push({ band: name }); for (let i = 1; i <= n; i++) rows.push({ cells: [`${name}-${i}`, 'x'] }); }
        return app._bTableLines(book, { title, cols: [{ title: 'a', w: 1 }, { title: 'b', w: 1 }], rows });
    };
    const blocks = [{ lines: table('T1', [['BAND A', 5], ['BAND B', 7], ['BAND C', 3]]) },
                    { lines: table('T2', [['BAND D', 2]]) },
                    { lines: table('T3', [['BAND E', 1]]) },
                    { lines: table('T4', [['BAND F', 4]]) }];
    // every line knows its text, for the reading below
    const name = (l) => { const before = book.log.texts.length; l.draw(ctx, 0, 0, 600); return book.log.texts[before]; };
    blocks.forEach(b => b.lines.forEach(l => { l.name = name(l); }));
    const pack = app._bPack(blocks, colH, maxCols);
    return { cols: pack.cols.map(col => ({ h: col.h, items: col.items.map(it => [it.line.name, it.y, it.line.h, !!it.line.head, !!it.line.band]) })),
             rest: pack.rest.map(b => b.lines.map(l => l.name)) };
}"""


def test_the_packer_lays_blocks_whole_splits_only_the_tall_and_repeats_the_heads(page):
    """Four tables into columns: with room, a block follows the one before
    it (a gap between) and moves whole to the next column where it would
    not fit under; a block taller than a column is split at a line, its
    title and heading repeated where it continues, and a band never ends
    a column; what no column holds comes back as the rest, the split
    block's remainder headed, for the next sheet."""
    pg, ids = page
    t1 = H4_H + TH_H + 3 * BAND_H + 15 * ROW_H          # 794
    t2 = H4_H + TH_H + BAND_H + 2 * ROW_H               # 208
    t3 = H4_H + TH_H + BAND_H + ROW_H                   # 170
    t4 = H4_H + TH_H + BAND_H + 4 * ROW_H               # 284
    # room: T1 fills column 1; T2 would not fit under it and fits a column
    # whole, so it opens column 2, T3 and T4 follow it there
    out = pg.evaluate(PACK_JS, [900, 3])
    assert out['rest'] == []
    assert len(out['cols']) == 2
    c1, c2 = out['cols']
    assert [i[0] for i in c1['items']] == ['T1', 'A', 'BAND A'] + [f'BAND A-{i}' for i in range(1, 6)] \
        + ['BAND B'] + [f'BAND B-{i}' for i in range(1, 8)] + ['BAND C'] + [f'BAND C-{i}' for i in range(1, 4)]
    assert c1['h'] == t1
    assert [i[0] for i in c2['items']] == ['T2', 'A', 'BAND D', 'BAND D-1', 'BAND D-2', 'T3', 'A', 'BAND E', 'BAND E-1',
                                  'T4', 'A', 'BAND F'] + [f'BAND F-{i}' for i in range(1, 5)]
    ys = {i[0]: i[1] for i in c2['items']}
    assert ys['T3'] == t2 + BLOCK_GAP and ys['T4'] == t2 + BLOCK_GAP + t3 + BLOCK_GAP
    assert c2['h'] == t2 + BLOCK_GAP + t3 + BLOCK_GAP + t4
    # every line follows the one before it with no gap but the block gap
    for col in (c1, c2):
        for a, b in zip(col['items'], col['items'][1:]):
            assert b[1] in (a[1] + a[2], a[1] + a[2] + BLOCK_GAP), (a, b)
    # too little room: T1 is split - column 1 holds its heads, band A and
    # its rows, band B and the rows that fit; column 2 opens with the
    # heads again over the rest of band B and band C; T2 - T4 are the rest
    out = pg.evaluate(PACK_JS, [500, 2])
    c1, c2 = out['cols']
    assert [i[0] for i in c1['items']] == ['T1', 'A', 'BAND A'] + [f'BAND A-{i}' for i in range(1, 6)] \
        + ['BAND B', 'BAND B-1', 'BAND B-2', 'BAND B-3']
    assert c1['h'] <= 500
    assert [i[0] for i in c2['items']] == ['T1', 'A', 'BAND B-4', 'BAND B-5', 'BAND B-6', 'BAND B-7', 'BAND C'] \
        + [f'BAND C-{i}' for i in range(1, 4)]
    assert c2['h'] <= 500
    assert out['rest'] == [['T2', 'A', 'BAND D', 'BAND D-1', 'BAND D-2'], ['T3', 'A', 'BAND E', 'BAND E-1'],
                           ['T4', 'A', 'BAND F'] + [f'BAND F-{i}' for i in range(1, 5)]]
    # a band never ends a column: with room for exactly the heads, band A,
    # its rows and band B, band B waits for the next column
    exact = H4_H + TH_H + BAND_H + 5 * ROW_H + BAND_H
    out = pg.evaluate(PACK_JS, [exact, 2])
    c1, c2 = out['cols']
    assert [i[0] for i in c1['items']] == ['T1', 'A', 'BAND A'] + [f'BAND A-{i}' for i in range(1, 6)]
    assert [i[0] for i in c2['items']][:4] == ['T1', 'A', 'BAND B', 'BAND B-1']
    # a column too short for even a row still takes the heads and one row,
    # so nothing loops
    out = pg.evaluate(PACK_JS, [10, 1])
    assert [i[0] for i in out['cols'][0]['items']] == ['T1', 'A', 'BAND A', 'BAND A-1']
    assert out['rest'][0][:4] == ['T1', 'A', 'BAND A-2', 'BAND A-3']


def test_a_sheet_whose_tables_do_not_fit_continues_on_the_next_number(page):
    """A pull sheet stuffed past a Tabloid's three columns continues on
    the next number of its series, "(cont.)", the table's title and
    heading repeated at the top of the continuation; the sheets after it
    take the numbers after that, and the CONTENTS lists them all."""
    pg, ids = page
    out = pg.evaluate("""(opts) => {
        const app = window.app;
        const real = app._bPullBlocks;
        app._bPullBlocks = function (book, pos, members) {
            const blocks = real.call(this, book, pos, members);
            if (pos.name !== 'SR Beach') return blocks;
            const rows = [];
            for (let i = 1; i <= 200; i++) rows.push({ cells: [`EXTRA-${i}`, 'x'] });
            blocks.push({ lines: this._bTableLines(book, { title: 'Stuffing', cols: [{ title: 'a', w: 1 }, { title: 'b', w: 1 }], rows }) });
            return blocks;
        };
        try {
            const plan = app.planBinder(opts);
            const i = plan.findIndex(p => p.title === 'SR Beach - Pull (cont.)');
            const cont = app.renderBinderPage(opts, i);
            const overview = app.renderBinderPage(opts, 0);
            return { plan: plan.map(p => [p.kind, p.number, p.title, p.sheetTitle, p.layout, p.cols]),
                     contTexts: cont.texts, contBubble: cont.bubble, overview: overview.texts };
        } finally {
            app._bPullBlocks = real;
        }
    }""", json.loads(_SHOW_JSON))
    plan = out['plan']
    titles = [p[2] for p in plan]
    i = titles.index('SR Beach - Pull')
    assert titles[i:i + 3] == ['SR Beach - Pull', 'SR Beach - Pull (cont.)', 'CENTER - Pull'], titles
    assert [p[1] for p in plan[i:i + 3]] == ['4.1', '4.2', '4.3'], plan
    assert plan[i + 1][3] == 'SR BEACH · PULL (CONT.)' and plan[i + 1][4] == 'tables' and plan[i + 1][5] == 3
    assert [p[1] for p in plan if p[0] in ('distro', 'processor', 'totals')] == ['5.1', '5.2', '5.3']
    # the continuation: its title block says (CONT.) and 4.2; the first
    # thing in its drawing area is the stuffed table's title and heading
    # again over the rows that did not fit
    texts = out['contTexts']
    assert 'SR BEACH · PULL (CONT.)' in texts and '4.2' in texts
    k = texts.index('STUFFING')
    assert texts[k + 1:k + 3] == ['A', 'B'] and texts[k + 3].startswith('EXTRA-') and texts[k + 3] != 'EXTRA-1'
    assert out['contBubble'] is None
    # the contents on 1.1 lists every sheet, the continuation too
    ov = out['overview']
    c = ov.index('CONTENTS')
    listed = [(ov[c + 3 + 2 * n], ov[c + 4 + 2 * n]) for n in range(len(plan))]
    assert listed == [(p[1], p[3]) for p in plan], listed


def test_the_overview_maps_the_show_and_lists_the_contents(page):
    """Sheet 1.1: the POSITIONS, SHOW TOTALS and CONTENTS tables in the
    top-left, the show map under them as view 1 across the width with its
    bubble "1 OVERVIEW"; the contents names every sheet by number and
    title and matches the plan; no Palette line anywhere."""
    pg, ids = page
    out = _render(pg, SHOW, 'Overview')
    texts = out['texts']
    _title_block(texts, 'OVERVIEW', '1.1')
    assert out['page']['layout'] == 'overview' and out['page']['view'] == 1
    assert out['bubble']['number'] == 1 and out['bubble']['name'] == 'OVERVIEW'
    p = texts.index('POSITIONS')
    assert texts[p + 1:p + 5] == ['POSITION', 'SCREENS', 'CIRCUITS', 'PORTS']
    assert texts[p + 5:p + 7] == ['SR Beach', 'WALL-A, WALL-B'] and texts[p + 9:p + 11] == ['CENTER', 'CENTER'], texts[p:p + 14]
    circuits = int(texts[p + 7]) + int(texts[p + 11])
    ports = int(texts[p + 8]) + int(texts[p + 12])
    assert circuits >= 5 and ports == 3, texts[p:p + 14]
    s = texts.index('SHOW TOTALS')
    totals = dict(zip(texts[s + 1:s + 15:2], texts[s + 2:s + 16:2]))
    assert totals['Screens'] == '3' and totals['Circuits'] == str(circuits) and totals['Ports'] == str(ports)
    assert totals['Panels'] == '39' and totals['Distros'] == '1' and totals['Processors'] == '1'
    assert totals['Load'].endswith(' kW')
    c = texts.index('CONTENTS')
    assert texts[c + 1:c + 3] == ['SHEET', 'TITLE']
    listed = [(texts[c + 3 + 2 * n], texts[c + 4 + 2 * n]) for n in range(len(PLAN))]
    full = pg.evaluate("(o) => window.app.planBinder(o).map(p => [p.number, p.sheetTitle])", json.loads(_SHOW_JSON))
    assert listed == [tuple(x) for x in full], listed
    assert not [t for t in texts if 'palette' in t.lower() or 'engineer' in t.lower()]
    # the three tables across the top in three columns, the map under
    # them at the drawing area's width, the bubble under the map
    heads = {t: (x, y) for t, x, y in out['headings']}
    assert heads['POSITIONS'][1] == heads['SHOW TOTALS'][1] == heads['CONTENTS'][1]
    assert heads['POSITIONS'][0] < heads['SHOW TOTALS'][0] < heads['CONTENTS'][0]
    m = _map_of(out)
    assert m['area']['x'] == DA['x'] and m['area']['w'] == DA['w']
    assert m['y'] > max(y for _x, y in heads.values()) and m['w'] <= DA['w'] and m['x'] >= DA['x']
    assert m['zoom'] <= MAP_ZOOM_CAP
    b = out['bubble']
    assert b['y'] - b['r'] >= m['y'] + m['h'] and b['y'] + b['r'] <= DA['y'] + DA['h'] + 1, (b, m)


def test_the_title_block_prints_the_projects_fields_and_they_ride_the_project(page):
    """The export dialog's Title block fields commit to project.binder -
    one undo entry per field - and every sheet's title block prints them:
    the VENUE in caps under the show, the dates, the designer, the
    project manager's name / phone / email, the drafter (blank, the
    engineer), the notes wrapped, the REVISIONS rows numbered; the
    prepared-by preference sets the wordmark. Blank fields print their
    labels and nothing else. The block rides the project through the
    routes and undo."""
    pg, ids = page
    out = pg.evaluate("""async () => {
        const app = window.app;
        const j = (method, url, body) => fetch(url, {method, headers: {'Content-Type': 'application/json'},
            body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
        const set = (id, v) => { const el = document.getElementById(id); el.value = v; el.dispatchEvent(new Event('change')); };
        document.getElementById('export-format').value = 'binder';
        document.getElementById('export-format').dispatchEvent(new Event('change'));
        const h0 = app.historyIndex;
        set('export-binder-venue', 'Harbor Field');
        set('export-binder-dates', '9/4/26 - 9/6/26');
        set('export-binder-designer', 'Northlight Design');
        set('export-binder-pm-name', 'Jordan Reyes');
        set('export-binder-pm-phone', '(555) 010-2030');
        set('export-binder-pm-email', 'jreyes@example.com');
        set('export-binder-notes', 'All socas land SR. Verify the L21-30 legs before the walk.');
        set('export-binder-revisions', '7/24/26 · MK · Overview\\n7/27/26 | JR | Patch & circuit\\n\\n7/29/26');
        const h1 = app.historyIndex;
        const actions = app.history.slice(h0 + 1, h1 + 1).map(h => h.action);
        const stored = JSON.parse(JSON.stringify(app.project.binder));
        const revText = document.getElementById('export-binder-revisions').value;
        await app._binderPushQueue;
        const served = (await j('GET', '/api/project')).binder;
        app.setEngineerName('Matt Knotts');
        await new Promise(r => setTimeout(r, 300));
        app.syncBinderControls();
        const drafterPlaceholder = document.getElementById('export-binder-drafter').placeholder;
        return { actions, stored, served, revText, drafterPlaceholder, info: app.getBinderInfo() };
    }""")
    try:
        assert out['actions'] == ['Set Binder Venue', 'Set Binder Dates', 'Set Binder Designer', 'Set Binder Project Manager',
                                  'Set Binder Project Manager Phone', 'Set Binder Project Manager Email',
                                  'Set Binder Notes', 'Set Binder Revisions'], out['actions']
        want = {'venue': 'Harbor Field', 'dates': '9/4/26 - 9/6/26', 'designer': 'Northlight Design',
                'projectManager': {'name': 'Jordan Reyes', 'phone': '(555) 010-2030', 'email': 'jreyes@example.com'},
                'notes': 'All socas land SR. Verify the L21-30 legs before the walk.',
                'revisions': [{'date': '7/24/26', 'by': 'MK', 'description': 'Overview'},
                              {'date': '7/27/26', 'by': 'JR', 'description': 'Patch & circuit'},
                              {'date': '7/29/26', 'by': '', 'description': ''}]}
        assert out['stored'] == want, out['stored']
        assert out['served'] == want, out['served']
        assert out['revText'] == '7/24/26 · MK · Overview\n7/27/26 · JR · Patch & circuit\n7/29/26 ·  · '
        assert out['drafterPlaceholder'] == 'Matt Knotts'
        assert out['info']['drafter'] == '' and out['info']['revisions'] == want['revisions']
        r = _render(pg, SHOW, 'WALL-B - Data')
        texts = r['texts']
        _title_block(texts, 'WALL-B · DATA', '3.2')
        for t in ('HARBOR FIELD', '9/4/26 - 9/6/26', 'Northlight Design', 'Jordan Reyes', '(555) 010-2030',
                  'jreyes@example.com', 'Matt Knotts', '7/24/26', 'MK', 'Overview', '7/27/26', 'JR', 'Patch & circuit', '7/29/26'):
            assert t in texts, (t, texts[:60])
        assert texts[texts.index('Drafter:') + 1] == 'Matt Knotts'          # the engineer, no drafter typed
        assert texts[texts.index('Designer:') + 1] == 'Northlight Design'
        assert texts[texts.index('Project Manager:') + 1:texts.index('Project Manager:') + 4] == \
            ['Jordan Reyes', '(555) 010-2030', 'jreyes@example.com']
        assert texts[texts.index('Untitled Project') + 1:texts.index('Untitled Project') + 3] == ['HARBOR FIELD', '9/4/26 - 9/6/26']
        n = texts.index('Notes')
        note = ' '.join(t for t in texts[n + 1:n + 4] if t and t != 'Untitled Project')
        assert note.startswith('All socas land SR.') and 'before the walk.' in note, texts[n:n + 5]
        assert texts[texts.index('Description') + 1:texts.index('Description') + 5] == ['1', '7/24/26', 'MK', 'Overview']
        assert 'MATT KNOTTS' in texts                                       # the wordmark: no prepared-by, the engineer
        tb = r['titleBlock']
        assert tb['x'] == TB_X and tb['w'] == TB_W and tb['sections']['revisions']['rows'] == 3
        assert tb['sections']['notes']['lines'] == 2
        # a typed drafter and a prepared-by name take over
        pg.evaluate("""async () => {
            const app = window.app;
            app.setBinderField('drafter', 'Sam Okafor', 'Set Binder Drafter');
            await app.setPreparedBy('Northlight Design');
        }""")
        texts = _render(pg, SHOW, 'WALL-B - Data')['texts']
        assert texts[texts.index('Drafter:') + 1] == 'Sam Okafor' and 'NORTHLIGHT DESIGN' in texts and 'MATT KNOTTS' not in texts
        assert pg.evaluate("() => window.app.getPreferences().preparedBy") == 'Northlight Design'
        # undo takes the drafter back, one step
        pg.evaluate("() => window.app.undo()")
        pg.wait_for_timeout(500)
        assert pg.evaluate("() => window.app.getBinderInfo().drafter") == ''
        assert pg.evaluate("() => window.app.getBinderInfo().venue") == 'Harbor Field'
        # a file load (PUT) keeps the block
        loaded = pg.evaluate("""async () => {
            const j = (method, url, body) => fetch(url, {method, headers: {'Content-Type': 'application/json'},
                body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
            const p = await j('GET', '/api/project');
            return (await j('PUT', '/api/project', p)).binder;
        }""")
        assert loaded['venue'] == 'Harbor Field' and loaded['revisions'][1]['by'] == 'JR'
    finally:
        pg.evaluate("""async () => {
            const app = window.app;
            delete app.project.binder;
            await app._persistBinderInfo();
            await app.setPreparedBy('');
            await app.setEngineerName('');
            app.syncBinderControls();
        }""")
    # blank again: the labels print, no invented text
    texts = _render(pg, SHOW, 'WALL-B - Data')['texts']
    _title_block(texts, 'WALL-B · DATA', '3.2')
    assert texts[texts.index('Designer:') + 1] == '' and texts[texts.index('Drafter:') + 1] == ''
    assert 'LED RASTER DESIGNER' in texts
    assert not [t for t in texts if 'Harbor' in t or 'Northlight' in t or 'Sam' in t]
    assert ids['errors'] == []


def test_the_data_sheet_prints_the_return_end_and_the_processor_once(page):
    """Card SR backed 1:1 by a second (unnamed) card: the BACKUP cell is the
    return end the tray states - the backup port's label and where it lands,
    "SR-1R · H9 slot 2 · 1" - never "slot 2 1"; the Processor line names the
    unit once ("H9", not "H9 · H9"); Redundancy reads the bar ("Per card").
    HOME RUN says both ends' runs as each card's own ≡ sheet typed them
    ("SR Primary 100' / SR Backup 150' +25'" - the backup's snake and the
    extension on its socket, 2026-09-07: "i have no way of putting lengths
    for redundancy cables"), never cut to "…"; Cables this screen lists the
    backup's snake, the extension and the extension's `Ether-con Barrel`
    (one per extension, 2026-09-07); the processor sheet lists the
    extension as an `ext` row under its snake."""
    pg, ids = page
    backup_id = pg.evaluate("""async (ids) => {
        const app = window.app;
        const j = (method, url, body) => fetch(url, {method,
            headers: {'Content-Type': 'application/json'},
            body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
        let st = await j('PUT', `/api/processors/${ids.procId}/slots/1`, {deviceId: 'novastar-card-h-16xrj45-2xfiber'});
        const backupId = st.processors[0].slots[1].card.id;
        await j('PUT', `/api/processors/${ids.procId}`, {redundancy: true});
        st = await j('PUT', `/api/processors/${ids.procId}/cards/${ids.cardId}`, {backupCardId: backupId});
        await app.refreshProcessors();
        // WALL-A's port sits on SR's socket 1 and returns on slot 2's socket 1
        const sock = app._assignment.screens.find(s => s.layerId === String(ids.a)).ports[0].port;
        const bb = app._pullBackedBy(ids.cardId, sock);
        await j('PUT', `/api/processors/${ids.procId}/cards/${ids.cardId}`,
                {snakes: [{ports: [sock], ft: 100, name: 'SR Primary'}]});
        await j('PUT', `/api/processors/${ids.procId}/cards/${backupId}`,
                {snakes: [{ports: [bb.port], ft: 150, name: 'SR Backup'}], portCables: {[String(bb.port)]: {ft: 25}}});
        await app.refreshProcessors();
        await app.refreshPortAssignment();
        app.renderLayers();
        return backupId;
    }""", ids)
    try:
        out = _render(pg, SHOW, 'WALL-A - Data')
        texts = out['texts']
        i = texts.index('H9 SR · H_16xRJ45+2xfiber · 16 ports')
        assert texts[texts.index('PORTS') + 1:texts.index('PORTS') + 7] == \
            ['PORT', 'PRIMARY', 'BACKUP', 'PANELS', 'PX', 'HOME RUN']
        rows = []
        j = i + 1
        while j + 5 < len(texts) and re.fullmatch(r'SR-\d+', texts[j]):
            rows.append(texts[j:j + 6]); j += 6
        assert rows, texts[i:i + 20]
        for label, primary, backup, _panels, _px, home in rows:
            # the sending card the primary lands on, and the one the backup does
            assert re.fullmatch(r'H9 SR · \d+', primary), (label, primary)
            socket = primary.rsplit(' · ', 1)[-1]
            assert backup == f'{label}R · H9 slot 2 · {socket}', (label, backup)
            assert _on_map(out['mapTexts'], f'{label}R'), (label, out['mapTexts'])
            # both ends' runs, whole
            assert home == "SR Primary 100' / SR Backup 150' +25'", (label, home)
        assert not [t for t in texts if t.startswith('slot ') or t.endswith('…')]
        cables = texts[texts.index('CABLES THIS SCREEN'):texts.index('Screen')]
        assert ['Ether-con', "25'", '1'] == cables[cables.index('Ether-con'):cables.index('Ether-con') + 3], cables
        k = cables.index('Ether-con Barrel')
        assert cables[k:k + 3] == ['Ether-con Barrel', 'EA', '1'], cables
        assert cables.count('Ether-con Barrel') == 1, cables
        assert cables.count('Ether-con Snake') == 2, cables
        assert "150'" in cables and "100'" in cables, cables
        # the Facts say how many ports, never a px-per-port ceiling
        assert texts[texts.index('Ports') + 1] == '1 port' and not [t for t in texts if 'px/port' in t]
        assert texts[texts.index('Processor') + 1] == 'H9' and 'H9 · H9' not in texts
        assert texts[texts.index('Redundancy') + 1] == 'Per card'
        proc = _render(pg, SHOW, 'H9 - Processor')['texts']
        assert proc[proc.index('Redundancy') + 1] == 'Per card'
        assert not [t for t in proc if BOX_WORD.search(t)]
        # the unnamed card's device name is what the run column shrinks and
        # cuts (an unnamed card has no shorter name to print); the row is
        # its socket, 'ext', the length and the snake it hangs off
        k = proc.index('ext')
        assert proc[k - 1].startswith('H_16xRJ') and proc[k:k + 3] == ['ext', "25'", 'SR Backup'], proc[k - 3:k + 4]
        assert proc[proc.index('SR Backup') : proc.index('SR Backup') + 3] == ['SR Backup', '1-way', "150'"], proc
    finally:
        pg.evaluate("""async ([ids, backupId]) => {
            const app = window.app;
            const j = (method, url, body) => fetch(url, {method,
                headers: {'Content-Type': 'application/json'},
                body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
            await j('PUT', `/api/processors/${ids.procId}/cards/${ids.cardId}`, {backupCardId: null, snakes: [], portCables: {}});
            await j('PUT', `/api/processors/${ids.procId}/cards/${backupId}`, {snakes: [], portCables: {}});
            await j('PUT', `/api/processors/${ids.procId}`, {redundancy: false});
            await app.refreshProcessors();
            await app.refreshPortAssignment();
            app.renderLayers();
        }""", [ids, backup_id])
    assert ids['errors'] == []


def test_a_box_delivering_the_port_is_listed_instead_of_the_card(page):
    """"if cvt's are used then we will list those instead of sending card":
    a CVT4K-S on card SR (both OPTs, all 16 sockets again) delivers WALL-A's
    port, so PRIMARY reads the box and its own socket ("CVT4K-S SR · 1"),
    the band is the box's - its trunk as the card's face prints it, its
    sockets, its fiber ("12 Tac Fiber 250'") or "no fiber length" - the
    Cables table and the processor sheet carry the fiber, and the box's
    paper title is model + typed name ("CVT4K-S SR"), the way a card is
    "H9 SR"."""
    pg, ids = page
    box_id = pg.evaluate("""async (ids) => {
        const app = window.app;
        const j = (method, url, body) => fetch(url, {method,
            headers: {'Content-Type': 'application/json'},
            body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
        const st = await j('POST', `/api/processors/${ids.procId}/cards/${ids.cardId}/cvts`,
                           {deviceId: 'novastar-cvt4k-s', pair: false});
        const boxId = st.processors[0].slots[0].card.cvts[0].id;
        await j('PUT', `/api/processors/${ids.procId}/cvts/${boxId}`, {fiberType: '12 Tac Fiber', fiberFt: 250});
        await app.refreshProcessors();
        await app.refreshPortAssignment();
        app.renderLayers();
        return boxId;
    }""", ids)
    try:
        out = _render(pg, SHOW, 'WALL-A - Data')
        texts = out['texts']
        band = "CVT4K-S A-B · OPT 1-2 · 16 ports · 12 Tac Fiber 250'"
        assert band in texts, texts
        i = texts.index(band)
        assert texts[i + 1:i + 4] == ['SR-1', 'CVT4K-S A-B · 1', '—'], texts[i:i + 8]
        assert not [t for t in texts if t.startswith('H9 SR ·')], 'the card is not listed where the box delivers'
        k = texts.index('CABLES THIS SCREEN')
        assert texts[k + 4:k + 7] == ['12 Tac Fiber', "250'", '1'], texts[k:k + 12]
        assert not [t for t in texts if t.endswith('…') or 'px/port' in t]
        # the box named: model + name, as the card reads model + name
        pg.evaluate("""async ([ids, boxId]) => {
            const app = window.app;
            await fetch(`/api/processors/${ids.procId}/cvts/${boxId}`, {method: 'PUT',
                headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name: 'SR'})});
            await app.refreshProcessors(); await app.refreshPortAssignment(); app.renderLayers();
        }""", [ids, box_id])
        texts = _render(pg, SHOW, 'WALL-A - Data')['texts']
        assert "CVT4K-S SR · OPT 1-2 · 16 ports · 12 Tac Fiber 250'" in texts, texts
        assert 'CVT4K-S SR · 1' in texts
        # the processor sheet: the box under its card, with its fiber
        proc = _render(pg, SHOW, 'H9 - Processor')['texts']
        b = proc.index('BREAKOUT BOXES')
        assert proc[b + 1:b + 6] == ['BREAKOUT BOX', 'CARD', 'TRUNK', 'PORTS', 'FIBER']
        assert proc[b + 6:b + 11] == ['CVT4K-S SR', 'SR', 'OPT 1-2', '16', "12 Tac Fiber 250'"], proc[b:b + 12]
        assert ['12 Tac Fiber', "250'", '1', 'CVT4K-S SR'] == proc[proc.index('PULL LIST') + 5:proc.index('PULL LIST') + 9]
        # no sheet says box, save the breakout box's own table
        for t in texts + proc:
            assert not (BOX_WORD.search(t) and 'breakout box' not in t.lower()), t
        # no fiber length: the band says so, the Cables table has no fiber row
        pg.evaluate("""async ([ids, boxId]) => {
            const app = window.app;
            await fetch(`/api/processors/${ids.procId}/cvts/${boxId}`, {method: 'PUT',
                headers: {'Content-Type': 'application/json'}, body: JSON.stringify({fiberFt: null})});
            await app.refreshProcessors(); await app.refreshPortAssignment(); app.renderLayers();
        }""", [ids, box_id])
        texts = _render(pg, SHOW, 'WALL-A - Data')['texts']
        assert 'CVT4K-S SR · OPT 1-2 · 16 ports · no fiber length' in texts, texts
        assert '12 Tac Fiber' not in texts
        proc = _render(pg, SHOW, 'H9 - Processor')['texts']
        assert proc[proc.index('BREAKOUT BOXES') + 10] == 'no fiber length'
        # the backup end lands on a box the same way: the second card's own
        # CVT4K-S (named BK) carries WALL-A's return, so the return label is
        # that box's own ("BK-1" - the mapped port's label, the tray's rule)
        # and BACKUP names the box and its socket
        backup = pg.evaluate("""async (ids) => {
            const app = window.app;
            const j = (method, url, body) => fetch(url, {method,
                headers: {'Content-Type': 'application/json'},
                body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
            let st = await j('PUT', `/api/processors/${ids.procId}/slots/1`, {deviceId: 'novastar-card-h-16xrj45-2xfiber'});
            const backupId = st.processors[0].slots[1].card.id;
            st = await j('POST', `/api/processors/${ids.procId}/cards/${backupId}/cvts`, {deviceId: 'novastar-cvt4k-s', pair: false});
            const backupBox = st.processors[0].slots[1].card.cvts[0].id;
            await j('PUT', `/api/processors/${ids.procId}/cvts/${backupBox}`, {name: 'BK'});
            await j('PUT', `/api/processors/${ids.procId}`, {redundancy: true});
            await j('PUT', `/api/processors/${ids.procId}/cards/${ids.cardId}`, {backupCardId: backupId});
            await app.refreshProcessors(); await app.refreshPortAssignment(); app.renderLayers();
            return {backupId, backupBox};
        }""", ids)
        try:
            texts = _render(pg, SHOW, 'WALL-A - Data')['texts']
            i = texts.index('SR-1')
            assert texts[i:i + 3] == ['SR-1', 'CVT4K-S SR · 1', 'BK-1 · CVT4K-S BK · 1'], texts[i:i + 6]
            assert not [t for t in texts if t.endswith('…')]
        finally:
            pg.evaluate("""async ([ids, b]) => {
                const app = window.app;
                const j = (method, url, body) => fetch(url, {method,
                    headers: {'Content-Type': 'application/json'},
                    body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
                await j('PUT', `/api/processors/${ids.procId}/cards/${ids.cardId}`, {backupCardId: null});
                await j('PUT', `/api/processors/${ids.procId}`, {redundancy: false});
                await j('DELETE', `/api/processors/${ids.procId}/cvts/${b.backupBox}`);
                await app.refreshProcessors(); await app.refreshPortAssignment(); app.renderLayers();
            }""", [ids, backup])
    finally:
        pg.evaluate("""async ([ids, boxId]) => {
            const app = window.app;
            await fetch(`/api/processors/${ids.procId}/cvts/${boxId}`, {method: 'DELETE'});
            await app.refreshProcessors(); await app.refreshPortAssignment(); app.renderLayers();
        }""", [ids, box_id])
    after = _render(pg, SHOW, 'WALL-A - Data')['texts']
    assert 'H9 SR · H_16xRJ45+2xfiber · 16 ports' in after and 'H9 SR · 1' in after
    assert ids['errors'] == []


def test_the_port_cell_reads_a_long_label_whole(page):
    """The user's PDF cut "SR A-1" to "SR A…" in the PORT column: the column
    takes the width its longest label needs. Card SR renamed "SR A" names
    every port "SR A-n"; the cell reads it whole, and the row's other
    cells are still whole too."""
    pg, ids = page
    rename = """async ([ids, name]) => {
        const app = window.app;
        await fetch(`/api/processors/${ids.procId}/cards/${ids.cardId}`, {method: 'PUT',
            headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name})});
        await app.refreshProcessors(); await app.refreshPortAssignment(); app.renderLayers();
    }"""
    pg.evaluate(rename, [ids, 'SR A'])
    try:
        out = _render(pg, SHOW, 'WALL-A - Data')
        texts = out['texts']
        assert 'SR A-1' in texts, texts
        i = texts.index('SR A-1')
        assert texts[i:i + 3] == ['SR A-1', 'H9 SR A · 1', '—'], texts[i:i + 6]
        assert not [t for t in texts if t.endswith('…')], [t for t in texts if t.endswith('…')]
        assert _on_map(out['mapTexts'], 'SR A-1'), out['mapTexts']
    finally:
        pg.evaluate(rename, [ids, 'SR'])
    assert 'SR-1' in _render(pg, SHOW, 'WALL-A - Data')['texts']


# ── the smoke: the user's own show ───────────────────────────────────────

@pytest.mark.skipif(not os.path.exists(SCRATCH_FIXTURE),
                    reason='experts-only.json smoke fixture not present')
def test_smoke_experts_only(page):
    """The real show: SR - MAIN's 22 custom circuits on four socas, SR -
    Return's six on soca 5 with five 2fers, SL mirroring SR. 17 Tabloid
    sheets by series, none continued: SR - MAIN's power sheet (28 x 11, 22
    circuits) is ONE sheet, map-left / tables-right in one column, the map
    and the CIRCUITS table disjoint; its data sheet the same wall; a Return
    (6 x 11) is a tall wall stopped by the area's height."""
    pg, ids = page
    with open(SCRATCH_FIXTURE) as fh:
        project = json.load(fh)
    pages = pg.evaluate("""async (project) => {
        const app = window.app;
        const j = (method, url, body) => fetch(url, {method,
            headers: {'Content-Type': 'application/json'},
            body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
        await j('PUT', '/api/project', project);
        app.project = await j('GET', '/api/project');
        app.dedupeProjectLayers('binder_smoke');
        app.selectLayer(app.project.layers.find(l => (l.type || 'screen') === 'screen'));
        await app.refreshProcessors();
        await app.refreshPortAssignment();
        app.renderLayers();
        return app.planBinder(%s).map(p => [p.number, p.title, p.layout, p.cols, p.view]);
    }""" % SHOW, project)
    plan = [(n, t) for n, t, _l, _c, _v in pages]
    assert plan == [
        ('1.1', 'Overview'),
        ('2.1', 'SR - MAIN - Power'), ('2.2', 'SR - Return - Power'), ('2.3', 'SL - MAIN - Power'), ('2.4', 'SL - Return - Power'),
        ('3.1', 'SR - MAIN - Data'), ('3.2', 'SR - Return - Data'), ('3.3', 'SL - MAIN - Data'), ('3.4', 'SL - Return - Data'),
        ('4.1', 'SR - MAIN - Pull'), ('4.2', 'SR - Return - Pull'), ('4.3', 'SL - MAIN - Pull'), ('4.4', 'SL - Return - Pull'),
        ('5.1', 'SR - Distro'), ('5.2', 'SL - Distro'), ('5.3', 'H9 - Processor'),
        ('5.4', 'Pull list - all positions'),
    ]
    layouts = {t: (l, c, v) for _n, t, l, c, v in pages}
    assert layouts['SR - MAIN - Power'] == ('side', 1, 2) and layouts['SR - Return - Power'] == ('side', 1, 3)
    assert layouts['Overview'] == ('overview', 3, 1) and layouts['SR - MAIN - Pull'] == ('tables', 3, None)
    assert not [t for _n, t in plan if '(cont.)' in t]
    main = _render(pg, SHOW, 'SR - MAIN - Power')
    texts = main['texts']
    _title_block(texts, 'SR - MAIN · POWER', '2.1', show='2026 Experts Only')
    # one Tabloid sheet, painted at 2x
    assert main['width'] == W * SCALE and main['height'] == H * SCALE
    # the map: the wall 28 x 11 of 60 x 120 px, uniformly, in the area the
    # one table column leaves
    area = _side_area(1)
    m = main['map']
    want_main = (28 * 60) / (11 * 120)
    assert abs(m['w'] / m['h'] - want_main) / want_main < 0.01, m
    zoom = _zoom(area, 28, 11, 60, 120)
    assert abs(m['zoom'] - zoom) < 1e-6 and abs(m['w'] - 28 * 60 * zoom) <= 1, (m, zoom)
    assert m['area']['x'] == area['x'] and m['area']['w'] == area['w'] and m['area']['h'] <= area['h'], (m['area'], area)
    assert m['w'] / area['w'] > 0.75, m
    # the CIRCUITS table beside the map, disjoint from it: every heading
    # right of the map's area
    heads = {t: (x, y) for t, x, y in main['headings']}
    assert 'CIRCUITS' in heads and 'CABLES THIS SCREEN' in heads and 'FACTS' in heads, heads
    assert all(x >= m['area']['x'] + m['area']['w'] + COL_GAP - 1 for x, _y in heads.values()), (heads, m['area'])
    assert heads['CIRCUITS'][1] < heads['CABLES THIS SCREEN'][1] < heads['FACTS'][1]
    # the view bubble under the map
    b = main['bubble']
    assert b['number'] == 2 and b['name'] == 'SR - MAIN · POWER'
    assert b['y'] - b['r'] >= m['area']['y'] + m['area']['h'] and b['y'] + b['r'] <= DA['y'] + DA['h'] + 1
    # the brackets: SR1 and SR2 down the right at ONE distance (rows 1-6 over
    # rows 7-11 share an edge, they do not overlap); SR3 and SR4 down the left
    br = {x['name']: x for x in main['brackets']}
    assert sorted(br) == ['SR1', 'SR2', 'SR3', 'SR4'], main['brackets']
    assert br['SR1']['side'] == br['SR2']['side'] == 'R' and br['SR3']['side'] == br['SR4']['side'] == 'L'
    assert all(x['depth'] == 0 for x in br.values()), main['brackets']
    assert br['SR1']['x'] == br['SR2']['x'] and br['SR3']['x'] == br['SR4']['x'], main['brackets']
    assert br['SR1']['x'] > m['x'] + m['w'] and br['SR3']['x'] < m['x']
    assert br['SR1']['x'] + 24 + 14 < m['area']['x'] + m['area']['w'], 'the brackets stay inside the map area'
    # the circuits table AND the map on the one sheet, every band whole
    assert 'CIRCUITS' in texts and 'FACTS' in texts and 'CABLES THIS SCREEN' in texts
    bands = [t for t in texts if 'home run' in t]
    assert bands == [
        "SR1 · Soca 208 · 125' home run · 6 circuits",
        "SR2 · Soca 208 · 100' home run · 5 circuits",
        "SR3 · Soca 208 · 125' home run · 6 circuits",
        "SR4 · Soca 208 · 100' home run · 5 circuits",
    ]
    assert len([t for t in texts if re.fullmatch(r'SR[1-4]-\d', t)]) == 22
    assert 'FACTS' in texts and 'GANGS' not in texts
    assert not any(t.strip() == 'MULTI' for t in texts), [t for t in texts if t.strip() == 'MULTI']
    assert '22 at 208 V / 20 A · 14 panels each' in texts
    rulers = [t['text'] for t in main['textInfo'] if t['size'] == 22 and t['weight'] == 700]
    assert rulers[:7] == ['1', '5', '10', '15', '20', '25', '28'] and rulers[7:] == [str(i) for i in range(1, 12)]
    assert ["SR1 · 125'", "SR2 · 100'", "SR3 · 125'", "SR4 · 100'"] == [t for t in main['texts'] if re.fullmatch(r"SR\d · \d+'", t)]
    # the map: every label, and the typed cables as tags (the screen's switch is on);
    # no screen-name plate over them - the title block names the screen
    assert _on_map(main['mapTexts'], 'SR1-1') and "10' True1" in main['mapTexts'], main['mapTexts'][:20]
    assert not _on_map(main['mapTexts'], 'SR - MAIN')
    # the band rule: every band is followed straight by its first circuit
    for band in bands:
        assert texts[texts.index(band) + 1] == band.split(' ')[0] + '-' + ('2' if band.startswith('SR2') else '1'), \
            (band, texts[texts.index(band):texts.index(band) + 3])
    assert not [t for t in texts if '(cont.)' in t or '(CONT.)' in t]
    # printer: no colour, ten distinct dashes across 22 circuits
    printer = _render(pg, SHOW.replace("palette: 'colour'", "palette: 'printer'"), 'SR - MAIN - Power')
    assert printer['coloured'] == 0
    assert len({tuple(d) for d in printer['dashes'] if d}) == 10    # ten dashed patterns + the solid one
    # the tall narrow wall (6 x 11 of 60 x 120): the area's height stops
    # it, well under the 3x cap and the width, the aspect kept, every
    # table beside it
    retp = _render(pg, SHOW, 'SR - Return - Power')
    rm = retp['map']
    want = (6 * 60) / (11 * 120)
    assert abs(rm['w'] / rm['h'] - want) / want < 0.01, rm
    zoom = _zoom(area, 6, 11, 60, 120)
    assert zoom == (area['h'] - GUT['top'] - GUT['bottom']) / (11 * 120) and abs(rm['zoom'] - zoom) < 1e-6 \
        and abs(rm['w'] - 6 * 60 * zoom) <= 1 and abs(rm['h'] - 11 * 120 * zoom) <= 1, (rm, zoom)
    assert len(retp['brackets']) == 1 and retp['brackets'][0]['depth'] == 0
    ret = retp['texts']
    assert 'GANGS' in ret
    i = ret.index('GANGS')
    assert ret[i + 4:i + 4 + 15:3] == ['SR5-1', 'SR5-2', 'SR5-3', 'SR5-4', 'SR5-5']
    assert ret.count('2fer') == 5
    assert "SR5 · Soca 208 · 125' home run · 6 circuits" in ret
    dpage = _render(pg, SHOW, 'SR - MAIN - Data')
    assert not _on_map(dpage['mapTexts'], 'SR - MAIN')
    _title_block(dpage['texts'], 'SR - MAIN · DATA', '3.1', show='2026 Experts Only')
    # the same wall beside the wider Ports column (six columns of whole
    # names), so a little smaller; four ports beside it
    dm = dpage['map']
    assert abs(dm['w'] / dm['h'] - want_main) / want_main < 0.01, dm
    darea = _side_area(1, DATA_COL_W)
    assert dm['area']['w'] == darea['w'] and abs(dm['zoom'] - _zoom(darea, 28, 11, 60, 120)) < 1e-6, (dm, darea)
    assert layouts['SR - MAIN - Data'] == ('side', 1, 6)
    assert 'PORTS' in dpage['texts']
    data = dpage['texts']
    # the box delivering the ports is the band (2026-09-07: a CVT4K-S on
    # each card, all 16 sockets), the ports its own labels
    assert 'CVT4K-S A · OPT 1-2 · 16 ports · no fiber length' in data
    assert ['A-1', 'A-2', 'A-3', 'A-4'] == [t for t in data if re.fullmatch(r'A-\d', t)]
    # the return end, whole: the backup port's label and where it lands
    assert [t for t in data if re.fullmatch(r'B-\d · CVT4K-S B · \d', t)] == [
        'B-1 · CVT4K-S B · 1', 'B-2 · CVT4K-S B · 2', 'B-3 · CVT4K-S B · 3', 'B-4 · CVT4K-S B · 4']
    assert not [t for t in data if t.startswith('slot ')]
    # both ends' runs, and one barrel per extension in Cables this screen
    assert data[data.index('A-1') + 5] == "SNAKE A 150' +10' / SNAKE A · no length", data
    cables = data[data.index('CABLES THIS SCREEN'):data.index('FACTS')]
    k = cables.index('Ether-con Barrel')
    assert cables[k:k + 3] == ['Ether-con Barrel', 'EA', '3'], cables
    # the processor once, the redundancy in the bar's words
    assert data[data.index('Processor') + 1] == 'H9' and 'H9 · H9' not in data
    assert data[data.index('Redundancy') + 1] == 'Per card'
    # the overview's contents names every sheet
    ov = _render(pg, SHOW, 'Overview')['texts']
    c = ov.index('CONTENTS')
    listed = [(ov[c + 3 + 2 * n], ov[c + 4 + 2 * n]) for n in range(len(plan))]
    assert [n for n, _t in listed] == [n for n, _t in plan]
    assert listed[1] == ('2.1', 'SR - MAIN · POWER') and listed[-1] == ('5.4', 'PULL LIST · ALL POSITIONS')
    # no sheet says box, none says breakout as the generic noun, none Palette
    for idx in range(len(plan)):
        texts_i = pg.evaluate("([o, i]) => window.app.renderBinderPage(o, i).texts", [json.loads(_SHOW_JSON), idx])
        boxy = [t for t in texts_i if BOX_WORD.search(t) and 'breakout box' not in t.lower()]
        assert not boxy, (idx, boxy)
        assert not _generic_breakout(texts_i), (idx, _generic_breakout(texts_i))
        assert not [t for t in texts_i if 'palette' in t.lower()], idx
    distro = _render(pg, SHOW, 'SR - Distro')['texts']
    assert '5 SOCA 208' in distro and 'NAME' in distro
    assert '28 on 5 Soca 208' in distro, [t for t in distro if 'Soca 208' in t]
    assert 'BREAKOUTS' not in distro and 'Breakouts' not in distro
    assert ids['errors'] == []
