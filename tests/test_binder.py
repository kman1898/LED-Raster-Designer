"""The binder: the show's power and data maps bound into one PDF - as a
DRAWING SET (2026-09-08, on the NCMF packet the user held up: "this is a
great example to base our binder off of").

Every sheet is a landscape page of one size - Tabloid 17 x 11 by default
("17x11 i think is great . nice middle gound. but maybe have option for all
sizes"), Letter, ARCH C, ARCH D, A4, A3 to pick - at 200 px/in in page
units and inches x 72 in points, with a border a quarter inch in, a TITLE
BLOCK column 2.4 in wide down the right ("mimic whats in their drawing":
the logo when one is set, REVISIONS - the log the exports write - the show
/ venue / dates, Designer, Project Manager, Drafter, the SHEET TITLE, the
Sheet Number, the drawing date; 2026-09-08: "we dont need the cardinal
directions", "You put my name where a logo would go", "remove the notes
section") and the drawing area to its left. Type sizes are
in inches: a bigger sheet holds more, it does not print bigger type.

Sheets number by SERIES, by subject: 1.1 the overview (the show map as
view 1, POSITIONS / SHOW TOTALS / CONTENTS), 2.n the screens - each one's
POWER sheet, its DATA sheet, its SIGNAL + POWER sheet (test_binder_wiring.py)
- 3.n a PULL sheet per position, 4.n the hardware (a distro, a processor,
the totals). A sheet whose tables do not
fit continues on the next number "(cont.)"; the map never splits. Each
map is a numbered VIEW - a bubble with the number and the name in caps
under it ("Yes, bubble and view name").

Layout inside the drawing area - COVERAGE DECIDES (2026-09-08, "screens
can enlarge and text can be bigger if it fills the space. only get this
small when there is tons of info"): a map sheet is tried map-left /
tables-right (side) and map-over-tables (stack), each with the TABLES'
type scale s in [1, 2.4] chosen for it - the map taking the room the
tables leave and keeping at least 45 % of the width beside them, of the
height over them, its zoom min(fit, 3x) on the page - and the layout that
covers more of the drawing area (the wall with its gutters plus the
tables' box) wins, stack on a tie. The map paints in page units, its
rulers and brackets at their inch sizes; the tables and the bubble at s.
Tables that fit at 1 in neither layout are "tons of info": the sheet
stays at 1 and continues. The screens run in beach order and, within a
beach, in the SCREEN ORDER the project keeps (project.binder.screenOrder:
alphabetical by default - "i'd want raster A first, then in alphabetical
order" - the Screens panel's order either way, by first port, by first
circuit). The tables are packed by _bPack: a block follows
the one before it in its column, moves whole to the next column where it
fits there and not here, and is split at a line only where it is taller
than a column - its head lines repeated where it continues, a band never
left as the last line over nothing.

Type A of binder-mock.html is still the sheet's map: rulers around the
wall (numbering "2"), a bracket per soca / L21-30 outside it with its
home run (the unit named by its TYPE - "Multi 208", "L21-30" - never by a
generic noun: not "Box", not "Breakout"; the type's word is Multi, user
2026-09-08), then Circuits ·
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
sheet size and the logo in the preferences. A revision is LOGGED ON
EXPORT: an export at a Rev no row carries yet adds a row (the date, the
engineer's initials, the Revision note); the same rev again logs nothing.

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
    'be6afb3b-7607-4f06-8c12-a10cd58068e9', 'scratchpad', 'experts-only-fixture.json')

BOX_WORD = re.compile(r'\b(box|boxes)\b', re.I)
# The band over a multi's circuits: "SR1 · Multi 208 · 125' · 6 circuits" -
# name · type · length · count (no "home run": the length IS the home run,
# user 2026-09-08).
BAND = re.compile(r"^.+ · (Multi (208|120)|L21-30|no distro) · .+ · \d+ circuits?( · .*)?$")
def _bands(texts):
    return [t for t in texts if BAND.match(t)]
# "breakout" as the generic noun for the power unit is gone (2026-09-07);
# the pull list's "Tru-1 Breakout" CABLE row and the data side's "breakout
# box" keep their names - and the Signal + Power sheet's block for a multi
# IS its breakout, the fan-out, named by type ("Multi 208 breakout", user
# 2026-09-08: "it is a breakout also known as a fan out / but i like the
# first option").
BREAKOUT_WORD = re.compile(r'\bbreakouts?\b', re.I)
POWER_BREAKOUT = re.compile(r'\b(Multi (208|120)|L21-30) breakout\b')


def _generic_breakout(texts):
    return [t for t in texts if BREAKOUT_WORD.search(t)
            and 'breakout box' not in t.lower() and 'Tru-1 Breakout' not in t
            and not POWER_BREAKOUT.search(t)]


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


def _da(w, h, block=True):
    """The drawing area on a sheet of `w` x `h` page pixels, with the title
    block column standing or not."""
    return {'x': PAD + DA_PAD, 'y': PAD + DA_PAD,
            'w': w - PAD * 2 - (TB_W if block else 0) - DA_PAD * 2,
            'h': h - PAD * 2 - DA_PAD * 2}


# The title block switch (the export dialog's Binder block, default ON).
# OFF, the sheet loses its border, the whole title block column and the rev
# line, and the drawing area takes the sheet inside the same small margin -
# exactly TB_W wider. A run with LRD_BINDER_NO_TITLE_BLOCK=1 puts the SHOW
# options and the drawing area below into that state, so the suites that
# import them (test_binder_ink, test_binder_wiring,
# test_map_label_collisions) can be run the other way without a second copy
# of themselves. This module is run in the default state; its own
# both-ways tests carry the switch in their options instead.
TITLE_BLOCK = os.environ.get('LRD_BINDER_NO_TITLE_BLOCK', '').strip().lower() \
    not in ('1', 'true', 'yes', 'on')
DA_BLOCK = _da(W, H, True)
DA_PLAIN = _da(W, H, False)
DA = DA_BLOCK if TITLE_BLOCK else DA_PLAIN
TB_X = W - PAD - TB_W
# The tables' column, the gap, the view bubble's room under a map; the
# map's gutters (the rulers' and the brackets' room) and its zoom cap.
COL_W, COL_GAP, BUBBLE_H = 700, 30, 96
DATA_COL_W = 1020        # the data sheet's Ports table asks for a wider column
GUT = {'left': 200, 'right': 180, 'top': 74, 'bottom': 16}
MAP_ZOOM_CAP = 3
# The filler's line heights (app-binder.js): title, heading, band, row.
H4_H, TH_H, BAND_H, ROW_H, BLOCK_GAP = 46, 40, 46, 38, 22


# The fill: the tables' scale cap, the share of the area the map keeps.
FILL_CAP = 2.4
MAP_MIN_FRAC = 0.45


def _fit(room_w, room_h, ww, wh):
    """The wall's page zoom in a room of page units - _bMapLayout's fit,
    _bMap's own arithmetic."""
    return min((room_w - GUT['left'] - GUT['right']) / ww, (room_h - GUT['top'] - GUT['bottom']) / wh, MAP_ZOOM_CAP)


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
                  'cover', 'pull', 'hardware', 'wiring', 'title-block', 'engineer', 'rev',
                  'venue', 'dates', 'designer', 'pm-name', 'pm-phone', 'pm-email', 'drafter',
                  'logo', 'logo-preview', 'logo-remove', 'logo-status', 'revision-note', 'revisions'):
        assert f'id="export-binder-{field}"' in html, field
    # the wordmark's field and the NOTES box are gone; the logo takes a
    # PNG or JPEG file
    assert 'export-binder-prepared-by' not in html and 'export-binder-notes' not in html
    assert re.search(r'id="export-binder-logo"[^>]*accept="image/png,image/jpeg"', html)
    # the sheet select carries every size, Tabloid picked
    sec = html[html.index('id="export-binder-section"'):html.index('id="export-scale-row"')]
    for key in ('letter', 'tabloid', 'archc', 'archd', 'a4', 'a3'):
        assert f'<option value="{key}"' in sec, key
    assert '<option value="tabloid" selected>' in sec
    assert 'tail' not in sec.lower()
    # the title block switch stands in the Binder block, ticked
    assert re.search(r'id="export-binder-title-block"[^>]*checked', sec)
    # the title block's fields sit in their own raised group
    assert sec.count('class="export-views"') == 2
    assert 'Title block:' in sec
    main_js = open(os.path.join(HERE, '..', 'src', 'static', 'js', 'main.js')).read()
    assert "import './app-binder.js';" in main_js
    assert "import './app-binder-wiring.js';" in main_js
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
    # the wiring sheet's own strings the same - save the power block's
    # caption, which names the multi's BREAKOUT by its type
    wiring_js = open(os.path.join(HERE, '..', 'src', 'static', 'js', 'app-binder-wiring.js')).read()
    wcode = '\n'.join(l for l in wiring_js.splitlines() if not l.strip().startswith('//'))
    wliterals = re.findall(r"'[^'\n]*'|\"[^\"\n]*\"|`[^`]*`", wcode)
    assert not [l for l in wliterals if re.search(r'\btails?\b', l)], [l for l in wliterals if 'tail' in l]
    # the one literal naming a multi's breakout by its type reads a
    # field called box (the pull list's record) - no sheet word
    caption = re.compile(r"^`\$\{box\.type\} breakout`$")
    assert not [l for l in wliterals if 'Multi' in l or 'Palette' in l or (BOX_WORD.search(l) and not caption.match(l))], wliterals
    assert not [l for l in wliterals if BREAKOUT_WORD.search(l) and not caption.match(l)], wliterals
    # the modal's textareas wear the inset look the fields do; the
    # revision log's rows and their × have their own recipe
    css = open(os.path.join(HERE, '..', 'src', 'static', 'css', 'theme.css')).read()
    assert '#export-modal textarea' in css
    assert '.binder-rev-row' in css and '.binder-rev-remove' in css


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
              'drafter': 'Sam',
              'revisions': [{'no': 1, 'rev': '1.0', 'date': '7/24/26', 'by': 'MK', 'description': 'Overview'}]}
    assert client.post('/api/project', json={'binder': binder}).status_code == 200
    served = client.get('/api/project').get_json()['binder']
    assert served == binder and 'notes' not in served
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

_TB_JS = 'true' if TITLE_BLOCK else 'false'
SHOW = """{ sheet: 'tabloid', palette: 'colour', sides: {power: true, data: true}, scope: {kind: 'show'},
            cover: true, pull: true, hardware: true, titleBlock: %s }""" % _TB_JS
# The whole-show options as JSON, for evaluate() calls that take them as data.
_SHOW_JSON = ('{"sheet": "tabloid", "palette": "colour", "sides": {"power": true, "data": true}, "scope": {"kind": "show"},'
              ' "cover": true, "pull": true, "hardware": true, "titleBlock": %s}' % _TB_JS)
# The same set with the title block the other way, for the both-ways tests.
PLAIN_JSON = _SHOW_JSON.replace('"titleBlock": true', '"titleBlock": false')
BLOCK_JSON = _SHOW_JSON.replace('"titleBlock": false', '"titleBlock": true')
PLAIN = SHOW.replace('titleBlock: true', 'titleBlock: false')
BLOCK = SHOW.replace('titleBlock: false', 'titleBlock: true')

# The set on two positions: 13 sheets - the screens in beach order, each
# screen's POWER, its DATA, its SIGNAL + POWER (2026-09-08); the two
# positions side by side on one pull sheet; the distro; the processor with
# the show's pull list beside it.
PULL = 'Pull - SR Beach, CENTER'
DISTRO = 'Distro - SR'
PROC = 'Processor - H9 · Pull list'
PLAN = [
    ['overview', '1.1', 'Overview'],
    ['power', '2.1', 'WALL-A - Power'], ['data', '2.2', 'WALL-A - Data'], ['wiring', '2.3', 'WALL-A - Signal + Power'],
    ['power', '2.4', 'WALL-B - Power'], ['data', '2.5', 'WALL-B - Data'], ['wiring', '2.6', 'WALL-B - Signal + Power'],
    ['power', '2.7', 'CENTER - Power'], ['data', '2.8', 'CENTER - Data'], ['wiring', '2.9', 'CENTER - Signal + Power'],
    ['pull', '3.1', PULL],
    ['distro', '4.1', DISTRO],
    ['processor', '4.2', PROC],
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
    const sc = plan[idx].scale || 1;
    const cols = r.record.ops.filter(o => o.op === 'text' && Math.abs(o.size - 25 * sc) < 0.02 && o.weight === 700);
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


# The title block's own strings - every one of them, on every sheet - and
# the rev line in the sheet's corner.
TB_STRINGS = ('Revisions:', 'No.', 'Date', 'By', 'Description', 'Designer:',
              'Project Manager:', 'Drafter:', 'Sheet Number', 'Drawing Date')
REV_LINE = re.compile(r'^rev \S+$')


def _title_block(texts, sheet_title, number, show='Untitled Project'):
    """The title block's texts, in the order the column draws them - or,
    on a run made with the block switched off, their absence: the same
    call reads the sheet either way, so the suites that import this
    helper hold the plain sheet to the mirror of the same rule."""
    if not TITLE_BLOCK:
        for t in ('Revisions:', 'Designer:', 'Project Manager:', 'Drafter:',
                  'Sheet Number', 'Drawing Date', show):
            assert t not in texts, (t, texts[:60])
        assert not [t for t in texts if REV_LINE.match(t)], texts[:60]
        return
    for t in ('Revisions:', 'No.', 'Date', 'By', 'Description',
              show, 'Designer:', 'Project Manager:', 'Drafter:', sheet_title, 'Sheet Number', number, 'Drawing Date'):
        assert t in texts, (t, texts[:60])
    order = [texts.index(t) for t in ('Revisions:', show, 'Designer:', sheet_title, 'Sheet Number', number)]
    assert order == sorted(order), order
    # the block is drawn first: nothing before REVISIONS but a logo (an
    # image, no text) - no compass letters, no wordmark, no NOTES box
    assert texts[0] == 'Revisions:', texts[:4]
    head = texts[:texts.index(show)]
    assert not [t for t in head if t in ('US', 'DS', 'SL', 'Notes', 'LED RASTER DESIGNER')], head


def test_the_sheets_come_in_series_by_subject(page):
    """1.1 the overview; 2.n the screens in beach order (the pull list's
    position order), each screen's POWER sheet, its DATA sheet, its SIGNAL +
    POWER sheet; 3.n the pull sheets, positions side by side; 4.n the
    hardware - the distro, then the processor with the show's pull list
    beside it. Every sheet is the Tabloid default."""
    pg, ids = page
    plan = _plan(pg, SHOW)
    assert plan == PLAN
    full = pg.evaluate("(o) => window.app.planBinder(o)", json.loads(_SHOW_JSON))
    assert all((p['w'], p['h'], p['sheet']) == (W, H, 'tabloid') for p in full), full
    assert [p['view'] for p in full] == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, None, None, None]
    assert all(p['sheetTitle'] == p['sheetTitle'].upper() for p in full)
    assert [p['sheetTitle'] for p in full][:5] == ['OVERVIEW', 'WALL-A · POWER', 'WALL-A · DATA',
                                                   'WALL-A · SIGNAL + POWER', 'WALL-B · POWER']
    assert [p['sheetTitle'] for p in full][-3:] == ['PULL · SR BEACH, CENTER', 'DISTRO · SR', 'PROCESSOR · H9 · PULL LIST']
    assert [p['names'] for p in full][-3:] == [['SR Beach', 'CENTER'], ['SR'], ['H9', 'All positions']]
    assert ids['errors'] == []
    # power only, no extras, the Signal + Power tick off: just the maps, 2.1 - 2.3
    only = _plan(pg, SHOW.replace("data: true", "data: false")
                 .replace("cover: true, pull: true, hardware: true", "cover: false, pull: false, hardware: false, wiring: false"))
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
    bands = _bands(texts)
    # the type is Multi, and the length stands alone - "125' home run"
    # said it twice (user, 2026-09-08)
    assert bands == ["SR1 · Multi 208 · 125' · 2 circuits"], texts
    assert not [t for t in texts if 'home run' in t.lower()], [t for t in texts if 'home run' in t.lower()]
    # "Multi" alone is a cable row, never a heading
    assert not any(t.strip() == 'MULTI' for t in texts), [t for t in texts if t.strip() == 'MULTI']
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
    # a squat wall over three short tables: the stack covers most
    assert out['page']['layout'] == 'stack' and out['page']['cols'] == 3


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
    assert _bands(out['texts']) == _bands(colour['texts'])


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
    assert one == [['power', '2.1', 'WALL-B - Power'], ['data', '2.2', 'WALL-B - Data'], ['wiring', '2.3', 'WALL-B - Signal + Power']]
    # the power side alone: its Signal + Power sheet is the power half alone
    ticked = _plan(pg, """{ sheet: 'tabloid', palette: 'colour', sides: {power: true, data: false},
                            scope: {kind: 'screen', layerId: '%s'}, cover: false, pull: true, hardware: false }""" % ids['b'])
    assert ticked == [['power', '2.1', 'WALL-B - Power'], ['wiring', '2.2', 'WALL-B - Signal + Power'],
                      ['pull', '3.1', 'Pull - SR Beach'], ['totals', '4.1', 'Pull list - all positions']]
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
                      wiring: on('export-binder-wiring'),
                      section: vis('export-binder-section'), views: vis('export-views-section'),
                      canvases: vis('export-canvases-section'), preview: document.getElementById('export-preview').textContent,
                      opts: app.readBinderOptions() };
        document.getElementById('export-cancel').click();
        return out;
    }""", ids['b'])
    assert out['format'] == 'binder' and out['scope'] == f"screen:{ids['b']}" and out['sheet'] == 'tabloid'
    assert (out['cover'], out['pull'], out['hardware']) == (False, False, False)
    assert out['wiring'] is True and out['opts']['wiring'] is True, 'the Signal + Power sheet is a screen sheet: it stays ticked'
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
    an unknown key falls back to Tabloid. Type is the base size in inches
    times the sheet's fill scale - the headings 25 px times it (WALL-A's
    tiny wall beside two circuits fills an ARCH D at the cap) - and the
    title block's sheet number 56 px on every sheet."""
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
        s = full[1]['scale']
        assert 1 <= s <= 2.4 and (s == 2.4 if key == 'archd' else True), (key, s)
        assert round(25 * s, 2) in out['sizes'] and round(24 * s, 2) in out['sizes'] and 56 in out['sizes'], (key, s, out['sizes'])
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
                     kindsByPage: plan.map(p => p.kind),
                     logged: JSON.parse(JSON.stringify(app.getBinderInfo().revisions)) };
        } finally {
            window.fetch = realFetch;
            app.saveBlobWithPicker = saved;
            document.getElementById('export-binder-colour').checked = true;
            // the export logged rev 1.0; the log is the next tests' to write
            delete app.project.binder;
            await app._persistBinderInfo();
        }
    }""", None)
    assert out['posts'] == 1 and out['urls'] == ['/api/export/pdf-from-pages']
    assert out['keys'] == ['pages', 'project_name']
    # the export logged its rev: no engineer set, so blank initials; no note
    assert out['logged'] == [{'no': 1, 'rev': '1.0', 'date': _today(), 'by': '', 'description': ''}], out['logged']
    assert out['n'] == out['plan'] == out['pages'] == len(PLAN)
    assert all(k == ['height', 'images', 'name', 'ops', 'page_size', 'width'] for k in out['pageKeys']), out['pageKeys']
    assert not out['bitmaps'], 'the export sends no sheet bitmap'
    assert out['names'][0] == 'Overview' and out['names'][-1] == PROC
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
        elif kind == 'wiring':
            # the two halves' walls - every screen here has both sides
            assert len(ids_) == 2 and ops_ == ids_, (kind, ids_, ops_)
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
    twice, and a wrapped revision description (the title block) is logged
    once and drawn a line at a time."""
    i = 0
    for t in log_texts:
        if i < len(op_texts) and op_texts[i] == t:
            i += 1
            continue
        parts = t.split(' / ')
        if len(parts) == 2 and op_texts[i:i + 2] == parts:
            i += 2
            continue
        for n in (2, 3):
            if ' '.join(op_texts[i:i + n]) == t:
                i += n
                break
        else:
            return False, (t, op_texts[i:i + 3])
    return i == len(op_texts), (len(op_texts), len(log_texts))


def test_every_sheet_record_is_a_display_list_of_its_texts(page):
    """Every sheet's record carries ops, its text ops the very texts the
    sheet logged, in order, the title block's first; the map sheets and
    the overview carry one image (the map, the raster) and no other sheet
    carries any; the brackets' labels are recorded turned a quarter with
    their anchor, never as a raw transform; every op is in
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
        # the title block first: its REVISIONS label, then the sheet
        # number set large in the corner
        assert (texts[0]['text'], texts[0]['size'], texts[0]['weight']) == ('Revisions:', 26, 700), texts[0]
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
        elif kind == 'wiring':
            # the two halves' walls, in the drawing area, the signal one
            # over the power one; the one view bubble under the lower half
            assert len(images) == 2 and [o['id'] for o in images] == rec['imageIds'], (title, images, rec['imageIds'])
            for im in images:
                assert im['w'] > 0 and im['h'] > 0 and im['x'] >= DA['x'] and im['x'] + im['w'] <= DA['x'] + DA['w'] + 1, im
                assert rec['imageSizes'][im['id']] > 1000
            assert images[0]['y'] + images[0]['h'] <= images[1]['y'], images
            b = out['bubble']
            assert b and b['number'] == out['page']['view'] and b['name'] == out['page']['sheetTitle'], (b, out['page'])
            assert b['y'] - b['r'] >= images[1]['y'] + images[1]['h'] and b['y'] + b['r'] <= DA['y'] + DA['h'] + 1, (b, images)
            circles = [o for o in ops if o['op'] == 'line' and len(o['points']) == 37]
            assert len(circles) == 1, len(circles)
        else:
            assert images == [] and rec['imageIds'] == [], (title, images)
            assert out['bubble'] is None
        # a bracket label is a rotated text op at its anchor; every other
        # text lies flat (the wordmark, once the block's one turned text,
        # is gone)
        turned = [o for o in texts if o['rotate']]
        assert not [o for o in turned if o['weight'] == 800], turned
        labels = list(turned)
        s = out['page']['scale']
        if kind == 'power':
            assert len(labels) == len(out['brackets']) >= 1, (title, labels)
            for o, b in zip(labels, out['brackets']):
                assert abs(abs(o['rotate']) - 1.5707963) < 1e-4 and (o['rotate'] > 0) == (b['side'] == 'R'), (o, b)
                # the label at its inch size: the map paints in page
                # units, whatever the sheet's fill scale
                assert o['align'] == 'center' and o['weight'] == 700 and abs(o['size'] - 28) < 0.02, (o, s)
                # the anchor: 24 out from the bracket, the baseline 9 in
                # from centre, turned - the text is centred on the span
                dir_ = 1 if b['side'] == 'R' else -1
                assert abs(o['x'] - (b['x'] + dir_ * 15)) < 0.6, (o, b, s)
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
    its table by what it lists: "2 Multi 208", the units by type."""
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
    distro = _render(pg, SHOW, DISTRO)['texts']
    i = distro.index('2 MULTI 208')
    assert distro[i + 1] == 'NAME' and distro[i + 2] == 'TYPE' and 'SR 1' in distro and 'SR 2' in distro
    assert 'BREAKOUTS' not in distro and 'Breakouts' not in distro
    assert [t for t in distro if re.fullmatch(r'\d+ on 2 Multi 208', t)], distro


def _map_of(out):
    m = out['map']
    assert m, out.keys()
    return m


def test_the_map_takes_the_room_the_tables_leave(page):
    """Coverage decides. WALL-A (4 x 3 of 200 px, squat) over three short
    tables: STACK - the tables side by side at the width-filling scale
    (2760 / 2160 = 1.277), the map taking the height they leave, the wall
    centred between its gutters at the fit of that height (well under 3x),
    the sheet more than 80 % covered. CENTER (3 x 5 of 128 px, tall) beside
    four short tables: SIDE - and here THE SHEET IS FILLED FIRST
    (2026-09-09): the tables used to grow until the map had only its 45 %
    of the width left (s = 2.079), which on a tall wall left the map short
    of the foot of the sheet and the bottom of the page empty. The scale is
    swept for the largest type that still COVERS the area, so the tables
    give a little width back and the map reaches both edges of its room -
    the wall's fit is the same on the width and on the height. Every
    heading lies beside or under the map, never over it, inside the drawing
    area; the bubble sits under the map; the map's rulers and brackets keep
    their inch sizes while the tables scale."""
    pg, ids = page
    ww, wh = 4 * 200, 3 * 200
    for title, cols, col_w in (('WALL-A - Power', 3, COL_W), ('WALL-A - Data', 2, DATA_COL_W)):
        out = _render(pg, SHOW, title)
        p = out['page']
        s = p['scale']
        assert p['layout'] == 'stack' and p['cols'] == cols, p
        # the row of tables sets the scale: (da.w + gap) / (cols x (col + gap))
        row_w = cols * col_w + (cols - 1) * COL_GAP
        assert abs(s - int(DA['w'] / row_w * 1000) / 1000) < 1e-9, (s, row_w)
        m = _map_of(out)
        assert m['area'] == {'x': DA['x'], 'y': DA['y'], 'w': DA['w'], 'h': m['area']['h']}, m['area']
        assert abs(m['w'] / m['h'] - ww / wh) / (ww / wh) < 0.01, (title, m)
        zoom = _fit(DA['w'], m['area']['h'], ww, wh)
        assert abs(m['zoom'] - zoom) < 0.01 and zoom < MAP_ZOOM_CAP and abs(m['w'] - ww * zoom) <= 2, (title, m, zoom)
        inner_cx = DA['x'] + GUT['left'] + (DA['w'] - GUT['left'] - GUT['right']) / 2
        assert abs(m['x'] + m['w'] / 2 - inner_cx) <= 1 and m['y'] == DA['y'] + GUT['top'], m
        assert m['scale'] == s
        heads = out['headings']
        assert heads and all(y >= m['area']['y'] + m['area']['h'] for _t, _x, y in heads), (heads, m['area'])
        xs = sorted({x for _t, x, _y in heads})
        assert xs[0] == DA['x'] and len(xs) == cols, xs
        assert all(b - a >= (col_w + COL_GAP) * s - 1 for a, b in zip(xs, xs[1:])), (xs, s)
        assert xs[-1] + col_w * s <= DA['x'] + DA['w'] + 1, xs
        ext = p['extent']
        assert ext['w'] <= DA['w'] + 1 and ext['h'] <= DA['h'] + 1, ext
        assert p['coverage'] >= 0.75, p
        assert 'FACTS' in out['texts'] and 'CABLES THIS SCREEN' in out['texts'], title
        assert not [t for t in out['texts'] if '(cont.)' in t or '(CONT.)' in t], title
        b = out['bubble']
        assert b['y'] - b['r'] >= m['area']['y'] + m['area']['h'] and b['y'] + b['r'] <= min(y for _t, _x, y in heads), (b, m['area'])
        assert abs(b['r'] - 34 * s) < 0.01, (b, s)
    a = _render(pg, SHOW, 'WALL-A - Power')
    assert a['page']['coverage'] >= 0.8, a['page']
    # CENTER: side - the map keeps 45 % of the width, the tables the rest
    # at the scale that leaves it (the height would allow more)
    c = _render(pg, SHOW, 'CENTER - Power')
    s = c['page']['scale']
    assert c['page']['layout'] == 'side' and c['page']['cols'] == 1, c['page']
    cap = int((DA['w'] - round(DA['w'] * MAP_MIN_FRAC)) / (COL_W + COL_GAP) * 1000) / 1000
    assert 1.3 < s <= cap, (s, cap)
    m = _map_of(c)
    room_w = DA['w'] - (COL_W + COL_GAP) * s
    assert abs(m['area']['w'] - room_w) < 0.01 and m['area']['x'] == DA['x'], (m['area'], room_w)
    assert m['scale'] == s and abs(m['w'] / m['h'] - 3 / 5) < 0.01, m
    zoom = _fit(room_w, DA['h'] - BUBBLE_H * s, 3 * 128, 5 * 128)
    assert abs(m['zoom'] - zoom) < 0.01 and zoom < MAP_ZOOM_CAP, (m, zoom)
    # the sweep's own answer: the map fills its room BOTH ways (the width
    # it was given and the height under the bubble are the same fit), and
    # the sheet is covered - no half-empty page under a small map
    room_h = DA['h'] - BUBBLE_H * s
    assert abs((room_w - GUT['left'] - GUT['right']) / (3 * 128)
               - (room_h - GUT['top'] - GUT['bottom']) / (5 * 128)) < 0.05, (s, room_w, room_h)
    assert c['page']['extent']['h'] >= DA['h'] * 0.98, c['page']['extent']
    # a step of type up would cost the map more than it gains: at the old
    # 45 %-width scale the sheet lost a sixth of its height
    assert cap - s > 0.2, (s, cap)
    assert m['x'] >= DA['x'] and m['x'] + m['w'] <= m['area']['x'] + m['area']['w'] + 1, m
    assert m['area']['y'] + m['area']['h'] <= DA['y'] + DA['h'] + 1, m
    ext = c['page']['extent']
    assert ext['w'] <= DA['w'] + 1 and ext['h'] <= DA['h'] + 1, ext
    heads = c['headings']
    assert heads and all(x >= m['area']['x'] + m['area']['w'] + COL_GAP * s - 1 for _t, x, _y in heads), (heads, m['area'])
    assert all(x + COL_W * s <= DA['x'] + DA['w'] + 1 for _t, x, _y in heads), heads
    b = c['bubble']
    assert b['y'] - b['r'] >= m['area']['y'] + m['area']['h'] and b['y'] + b['r'] <= DA['y'] + DA['h'] + 1, (b, m['area'])
    # the record: the tables' text at base x s, the rulers (22) and the
    # bracket labels (28) at their own sizes, the title block at its own
    rec = _record(pg, json.loads(_SHOW_JSON), 'CENTER - Power')
    sizes = {o['size'] for o in rec['record']['ops'] if o['op'] == 'text'}
    assert round(25 * s, 2) in sizes and round(24 * s, 2) in sizes, (s, sizes)
    assert 22 in sizes and 28 in sizes and 56 in sizes and 25 not in sizes and 24 not in sizes, sizes


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
    """A position stuffed past a Tabloid's four pull columns continues on
    the next number of its series, "(cont.)", the table's title and
    heading repeated at the top of the continuation under the position's
    name again; the next position joins it there; the sheets after take
    the numbers after that, and the CONTENTS lists them all."""
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
            const i = plan.findIndex(p => p.title === 'Pull - SR Beach (cont.), CENTER');
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
    i = titles.index('Pull - SR Beach')
    assert titles[i:i + 3] == ['Pull - SR Beach', 'Pull - SR Beach (cont.), CENTER', DISTRO], titles
    assert [p[1] for p in plan[i:i + 3]] == ['3.1', '3.2', '4.1'], plan
    assert plan[i][4] == 'tables' and plan[i][5] == 4, plan[i]
    assert plan[i + 1][3] == 'PULL · SR BEACH (CONT.), CENTER' and plan[i + 1][4] == 'tables' and plan[i + 1][5] == 2
    assert [p[1] for p in plan if p[0] in ('distro', 'processor', 'totals')] == ['4.1', '4.2']
    # the continuation: its title block says (CONT.) and 3.2; under the
    # position's name again, the first thing is the stuffed table's title
    # and heading over the rows that did not fit; CENTER's column beside
    texts = out['contTexts']
    assert 'PULL · SR BEACH (CONT.), CENTER' in texts and '3.2' in texts
    assert 'SR BEACH (CONT.)' in texts and 'CENTER' in texts
    k = texts.index('STUFFING')
    assert texts[k + 1:k + 3] == ['A', 'B'] and texts[k + 3].startswith('EXTRA-') and texts[k + 3] != 'EXTRA-1'
    assert texts.index('SR BEACH (CONT.)') < k < texts.index('CENTER')
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



def _outlines(ops, screens):
    """The overview's screen outlines: INK 3 px stroked rects, one at each
    screen's page rect, in the screens' order, after the map's image."""
    rects = [(sc['x'], sc['y'], sc['w'], sc['h']) for sc in screens]
    found = [o for o in ops if o['op'] == 'rect' and o.get('stroke') == '#111111' and o['width'] == 3
             and (o['x'], o['y'], o['w'], o['h']) in rects]
    image = next(i for i, o in enumerate(ops) if o['op'] == 'image')
    assert all(ops.index(o) > image for o in found), 'the outlines go over the bitmap'
    return [(o['x'], o['y'], o['w'], o['h']) for o in found]


def test_every_screen_on_the_overview_wears_its_own_outline(page):
    """"the screens look combined on SR and SL" (2026-09-08): over the
    overview's bitmap every screen's bounding rectangle is stroked in INK,
    3 px, as a vector rect op at the page position the crop's own world ->
    page mapping gives it - in both palettes; a show with one screen
    showing carries one outline."""
    pg, ids = page
    for palette in ('colour', 'printer'):
        opts = {**json.loads(_SHOW_JSON), 'palette': palette}
        out = _record(pg, opts, 'Overview')
        m = out['map']
        screens = m['screens']
        assert [sc['name'] for sc in screens] == ['WALL-A', 'WALL-B', 'CENTER'], screens
        rects = _outlines(out['record']['ops'], screens)
        assert rects == [(sc['x'], sc['y'], sc['w'], sc['h']) for sc in screens], (palette, rects, screens)
        for sc in screens:
            assert sc['w'] > 0 and sc['h'] > 0
            assert sc['x'] >= m['x'] - 0.01 and sc['x'] + sc['w'] <= m['x'] + m['w'] + 0.01, (sc, m)
            assert sc['y'] >= m['y'] - 0.01 and sc['y'] + sc['h'] <= m['y'] + m['h'] + 0.01, (sc, m)
        # the walls' proportions survive the mapping: WALL-A is 4 x 3
        a = screens[0]
        assert abs(a['w'] / a['h'] - 4 / 3) < 0.02, a
    # one screen showing: one outline
    pg.evaluate("""(ids) => { const app = window.app;
        for (const l of app.project.layers) if (l.id === ids.b || l.id === ids.c) l.visible = false; }""", ids)
    try:
        out = _record(pg, json.loads(_SHOW_JSON), 'Overview')
        screens = out['map']['screens']
        assert [sc['name'] for sc in screens] == ['WALL-A'], screens
        assert len(_outlines(out['record']['ops'], screens)) == 1
    finally:
        pg.evaluate("""(ids) => { const app = window.app;
            for (const l of app.project.layers) if (l.id === ids.b || l.id === ids.c) l.visible = true;
            window.canvasRenderer.render(); }""", ids)
    assert ids['errors'] == []


def _today():
    import datetime
    d = datetime.date.today()
    return f"{d.month}/{d.day}/{d.year % 100:02d}"


def test_the_sheets_row_keeps_every_box_inside_the_panel_on_one_line(page):
    """Four sheet boxes are wider than the modal. The row wraps, and each
    box keeps its own words on one line - "Signal + Power" was breaking
    mid-phrase and hanging off the right edge of the panel."""
    pg, ids = page
    out = pg.evaluate("""() => {
        document.getElementById('export-format').value = 'binder';
        document.getElementById('export-format').dispatchEvent(new Event('change'));
        const panel = document.getElementById('export-binder-section');
        const p = panel.getBoundingClientRect();
        const boxes = ['export-binder-cover', 'export-binder-pull',
                       'export-binder-hardware', 'export-binder-wiring'];
        return { overflowX: panel.scrollWidth - panel.clientWidth,
                 labels: boxes.map(id => {
                     const el = document.getElementById(id).closest('label');
                     const r = el.getBoundingClientRect();
                     const line = parseFloat(getComputedStyle(el).lineHeight);
                     return { id, text: el.textContent.trim(), height: r.height,
                              line, past: r.right - p.right, before: p.left - r.left };
                 }) };
    }""")
    assert out['overflowX'] <= 0, ('the panel scrolls sideways', out)
    for lab in out['labels']:
        assert lab['past'] <= 0, ('a box hangs off the right edge', lab)
        assert lab['before'] <= 0, ('a box hangs off the left edge', lab)
        # one line: a wrapped label would be two line-heights tall
        assert lab['height'] < lab['line'] * 1.6, ('a box broke mid-phrase', lab)
    assert [l['text'] for l in out['labels']] == \
        ['Overview', 'Pull sheets', 'Hardware', 'Signal + Power'], out['labels']


def test_the_title_block_prints_the_projects_fields_and_they_ride_the_project(page):
    """The export dialog's Title block fields commit to project.binder -
    one undo entry per field - and every sheet's title block prints them:
    the VENUE in caps under the show, the dates, the designer, the
    project manager's name / phone / email, the drafter (blank, the
    engineer). Blank fields print their labels and nothing else. There is
    no NOTES box and no notes field ("remove the notes section"). The
    block rides the project through the routes and undo."""
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
        const h1 = app.historyIndex;
        const actions = app.history.slice(h0 + 1, h1 + 1).map(h => h.action);
        const stored = JSON.parse(JSON.stringify(app.project.binder));
        await app._binderPushQueue;
        const served = (await j('GET', '/api/project')).binder;
        await app.setEngineerName('Morgan Keller');
        app.syncBinderControls();
        const drafterPlaceholder = document.getElementById('export-binder-drafter').placeholder;
        return { actions, stored, served, drafterPlaceholder, info: app.getBinderInfo(),
                 fields: [...document.querySelectorAll('#export-binder-section input, #export-binder-section textarea, #export-binder-section select')].map(e => e.id) };
    }""")
    try:
        assert out['actions'] == ['Set Binder Venue', 'Set Binder Dates', 'Set Binder Designer', 'Set Binder Project Manager',
                                  'Set Binder Project Manager Phone', 'Set Binder Project Manager Email'], out['actions']
        want = {'venue': 'Harbor Field', 'dates': '9/4/26 - 9/6/26', 'designer': 'Northlight Design',
                'projectManager': {'name': 'Jordan Reyes', 'phone': '(555) 010-2030', 'email': 'jreyes@example.com'}}
        assert out['stored'] == want, out['stored']
        assert out['served'] == want, out['served']
        assert 'notes' not in out['stored'] and 'notes' not in out['info'] and 'preparedBy' not in out['info']
        assert 'export-binder-notes' not in out['fields'] and 'export-binder-prepared-by' not in out['fields']
        assert out['drafterPlaceholder'] == 'Morgan Keller'
        assert out['info']['drafter'] == '' and out['info']['revisions'] == []
        r = _render(pg, SHOW, 'WALL-B - Data')
        texts = r['texts']
        _title_block(texts, 'WALL-B · DATA', '2.5')
        for t in ('HARBOR FIELD', '9/4/26 - 9/6/26', 'Northlight Design', 'Jordan Reyes', '(555) 010-2030',
                  'jreyes@example.com', 'Morgan Keller'):
            assert t in texts, (t, texts[:60])
        assert texts[texts.index('Drafter:') + 1] == 'Morgan Keller'          # the engineer, no drafter typed
        assert texts[texts.index('Designer:') + 1] == 'Northlight Design'
        assert texts[texts.index('Project Manager:') + 1:texts.index('Project Manager:') + 4] == \
            ['Jordan Reyes', '(555) 010-2030', 'jreyes@example.com']
        assert texts[texts.index('Untitled Project') + 1:texts.index('Untitled Project') + 3] == ['HARBOR FIELD', '9/4/26 - 9/6/26']
        assert 'Notes' not in texts and 'MATT KNOTTS' not in texts
        tb = r['titleBlock']
        assert tb['x'] == TB_X and tb['w'] == TB_W
        # top to bottom: REVISIONS (no logo set - no logo box at all), the
        # show, the people, the title, the number; nothing else
        assert list(tb['sections']) == ['revisions', 'show', 'people', 'title', 'number'], list(tb['sections'])
        assert tb['sections']['revisions']['y'] == PAD and tb['sections']['revisions']['rows'] == 0
        secs = tb['sections']
        assert secs['revisions']['h'] == H - PAD * 2 - (170 + 330 + 90 + 150), secs['revisions']
        assert secs['show']['y'] == PAD + secs['revisions']['h'] and secs['number']['y'] + 150 == H - PAD, secs
        # a typed drafter takes over
        pg.evaluate("() => window.app.setBinderField('drafter', 'Sam Okafor', 'Set Binder Drafter')")
        texts = _render(pg, SHOW, 'WALL-B - Data')['texts']
        assert texts[texts.index('Drafter:') + 1] == 'Sam Okafor'
        # undo takes the drafter back, one step
        pg.evaluate("() => window.app.undo()")
        pg.wait_for_timeout(500)
        assert pg.evaluate("() => window.app.getBinderInfo().drafter") == ''
        assert pg.evaluate("() => window.app.getBinderInfo().venue") == 'Harbor Field'
        # a file load (PUT) keeps the block, and carries no notes
        loaded = pg.evaluate("""async () => {
            const j = (method, url, body) => fetch(url, {method, headers: {'Content-Type': 'application/json'},
                body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
            const p = await j('GET', '/api/project');
            return (await j('PUT', '/api/project', p)).binder;
        }""")
        assert loaded['venue'] == 'Harbor Field' and 'notes' not in loaded
    finally:
        pg.evaluate("""async () => {
            const app = window.app;
            delete app.project.binder;
            await app._persistBinderInfo();
            await app.setEngineerName('');
            app.syncBinderControls();
        }""")
    # blank again: the labels print, no invented text - and no app name
    # in a wordmark, there being no wordmark
    texts = _render(pg, SHOW, 'WALL-B - Data')['texts']
    _title_block(texts, 'WALL-B · DATA', '2.5')
    assert texts[texts.index('Designer:') + 1] == '' and texts[texts.index('Drafter:') + 1] == ''
    assert 'LED RASTER DESIGNER' not in texts
    assert not [t for t in texts if 'Harbor' in t or 'Northlight' in t or 'Sam' in t]
    assert ids['errors'] == []


def test_a_revision_is_logged_on_export_and_the_log_edits_in_the_dialog(page):
    """"Logged on export": exporting at a Rev no row carries yet adds a
    row - today's date as M/D/YY, the engineer's initials, the Revision
    note - with one undo entry ('Log Revision'), persisted with the
    project, the note cleared; the same rev exported again logs nothing;
    a new rev logs a second row. The rows print in the REVISIONS table in
    order, No. their position; the dialog's list edits a row in place and
    × removes one, the rows after it renumbering."""
    pg, ids = page
    today = _today()
    out = pg.evaluate("""async () => {
        const app = window.app;
        const j = (method, url, body) => fetch(url, {method, headers: {'Content-Type': 'application/json'},
            body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
        const set = (id, v) => { const el = document.getElementById(id); el.value = v; el.dispatchEvent(new Event('change')); };
        const note = document.getElementById('export-binder-revision-note');
        const rows = () => [...document.querySelectorAll('#export-binder-revisions .binder-rev-row')].map(r =>
            [r.querySelector('.binder-rev-no').textContent, r.querySelector('.binder-rev-date').value,
             r.querySelector('.binder-rev-by').value, r.querySelector('.binder-rev-description').value]);
        const revs = () => JSON.parse(JSON.stringify(app.getBinderInfo().revisions));
        const realFetch = window.fetch;
        const saved = app.saveBlobWithPicker;
        window.fetch = async (url, init) => {
            if (String(url).includes('/api/export/pdf-from-')) {
                return { ok: true, blob: async () => new Blob(['%PDF-fake'], {type: 'application/pdf'}) };
            }
            return realFetch(url, init);
        };
        app.saveBlobWithPicker = async () => {};
        try {
            document.getElementById('export-format').value = 'binder';
            document.getElementById('export-format').dispatchEvent(new Event('change'));
            await app.setEngineerName('Morgan Keller');
            app.syncBinderControls();
            const empty = document.getElementById('export-binder-revisions').textContent;
            // the first export at rev 1.0: one row from the note
            set('export-binder-rev', '1.0');
            note.value = 'Overview issued';
            const h0 = app.historyIndex;
            await app.exportBinder('Two Positions');
            const first = { revs: revs(), rows: rows(), note: note.value,
                            actions: app.history.slice(h0 + 1).map(h => h.action) };
            await app._binderPushQueue;
            first.served = (await j('GET', '/api/project')).binder.revisions;
            // the same rev again: nothing logged, the note left alone
            note.value = 'should not log';
            const h1 = app.historyIndex;
            await app.exportBinder('Two Positions');
            const same = { revs: revs(), note: note.value, actions: app.history.slice(h1 + 1).map(h => h.action) };
            note.value = '';
            // rev 1.1: a second row
            set('export-binder-rev', '1.1');
            note.value = 'Patch & circuit';
            await app.exportBinder('Two Positions');
            const second = { revs: revs(), rows: rows(), note: note.value };
            return { empty, first, same, second };
        } finally {
            window.fetch = realFetch;
            app.saveBlobWithPicker = saved;
        }
    }""")
    try:
        assert 'Nothing logged yet' in out['empty']
        row1 = {'no': 1, 'rev': '1.0', 'date': today, 'by': 'MK', 'description': 'Overview issued'}
        row2 = {'no': 2, 'rev': '1.1', 'date': today, 'by': 'MK', 'description': 'Patch & circuit'}
        assert out['first']['revs'] == [row1], out['first']
        assert out['first']['served'] == [row1], out['first']['served']
        assert out['first']['rows'] == [['1', today, 'MK', 'Overview issued']]
        assert out['first']['note'] == ''
        assert out['first']['actions'] == ['Log Revision'], out['first']['actions']
        assert out['same']['revs'] == [row1] and out['same']['note'] == 'should not log' and out['same']['actions'] == []
        assert out['second']['revs'] == [row1, row2], out['second']
        assert out['second']['rows'] == [['1', today, 'MK', 'Overview issued'], ['2', today, 'MK', 'Patch & circuit']]
        assert out['second']['note'] == ''
        # the sheets print the log: No. · Date · By · Description, in order
        r = _render(pg, SHOW, 'WALL-B - Data')
        texts = r['texts']
        _title_block(texts, 'WALL-B · DATA', '2.5')
        i = texts.index('Description')
        assert texts[i + 1:i + 9] == ['1', today, 'MK', 'Overview issued', '2', today, 'MK', 'Patch & circuit'], texts[i:i + 10]
        assert r['titleBlock']['sections']['revisions']['rows'] == 2
        assert 'rev 1.1' in texts
        # the dialog edits a row in place, × removes one and the rest renumber
        out2 = pg.evaluate("""() => {
            const app = window.app;
            const rows = () => [...document.querySelectorAll('#export-binder-revisions .binder-rev-row')].map(r =>
                [r.querySelector('.binder-rev-no').textContent, r.querySelector('.binder-rev-date').value,
                 r.querySelector('.binder-rev-by').value, r.querySelector('.binder-rev-description').value]);
            const h0 = app.historyIndex;
            const desc = document.querySelector('#export-binder-revisions [data-index="1"] .binder-rev-description');
            desc.value = 'Patch, SR legs';
            desc.dispatchEvent(new Event('change', { bubbles: true }));
            const edited = rows();
            document.querySelector('#export-binder-revisions [data-index="0"] .binder-rev-remove').click();
            return { edited, rows: rows(), revs: JSON.parse(JSON.stringify(app.getBinderInfo().revisions)),
                     actions: app.history.slice(h0 + 1).map(h => h.action), stored: JSON.parse(JSON.stringify(app.project.binder)) };
        }""")
        assert out2['edited'][1] == ['2', today, 'MK', 'Patch, SR legs'], out2['edited']
        assert out2['rows'] == [['1', today, 'MK', 'Patch, SR legs']], out2['rows']
        assert out2['revs'] == [{'no': 1, 'rev': '1.1', 'date': today, 'by': 'MK', 'description': 'Patch, SR legs'}]
        assert out2['actions'] == ['Edit Revision', 'Remove Revision'], out2['actions']
        assert sorted(out2['stored']) == ['revisions'] and 'notes' not in out2['stored']
        texts = _render(pg, SHOW, 'WALL-B - Data')['texts']
        i = texts.index('Description')
        assert texts[i + 1:i + 5] == ['1', today, 'MK', 'Patch, SR legs'], texts[i:i + 6]
        # undo takes the removal back
        pg.evaluate("() => window.app.undo()")
        pg.wait_for_timeout(500)
        assert [r['no'] for r in pg.evaluate("() => window.app.getBinderInfo().revisions")] == [1, 2]
        # a blank engineer logs blank initials
        blank = pg.evaluate("""async () => {
            const app = window.app;
            await app.setEngineerName('');
            return app.logBinderRevision('2.0', '  Final  ');
        }""")
        assert blank == {'no': 3, 'rev': '2.0', 'date': today, 'by': '', 'description': 'Final'}
        assert pg.evaluate("() => window.app.binderInitials('jordan  reyes-ortega jr')") == 'JRJ'
    finally:
        pg.evaluate("""async () => {
            const app = window.app;
            delete app.project.binder;
            await app._persistBinderInfo();
            app.setPullSheetSetting('rev', '1.0', 'Set Pull Sheet Revision');
            document.getElementById('export-binder-revision-note').value = '';
            await app.setEngineerName('');
            app.syncBinderControls();
        }""")
    assert pg.evaluate("() => window.app.getBinderInfo().revisions") == []
    assert ids['errors'] == []


def test_a_long_revision_description_wraps_inside_its_row(page):
    """The REVISIONS table cut "Logo and revision log" to "Logo and
    revision …" (2026-09-08): a long description wraps onto further lines
    inside its row instead - a 40-character one prints whole, logged
    once, drawn a line at a time down the Description column."""
    pg, ids = page
    desc = 'Logo and revision log added to the block'
    assert len(desc) == 40
    out = pg.evaluate("""([opts, desc]) => {
        const app = window.app;
        const saved = app.project.binder;
        app.project.binder = { revisions: [
            { rev: '1.0', date: '7/24/26', by: 'MK', description: desc },
            { rev: '1.1', date: '7/27/26', by: 'MK', description: 'Patch' }] };
        try {
            const r = app.renderBinderPage(opts, 1);
            return { texts: r.texts, ops: r.record.ops.filter(o => o.op === 'text'), tb: r.titleBlock };
        } finally { app.project.binder = saved; }
    }""", [json.loads(_SHOW_JSON), desc])
    texts = out['texts']
    assert desc in texts and texts[texts.index('MK') - 2:texts.index('MK') + 2] == ['1', '7/24/26', 'MK', desc], texts[:16]
    assert texts[texts.index(desc) + 1:texts.index(desc) + 5] == ['2', '7/27/26', 'MK', 'Patch']
    assert out['tb']['sections']['revisions']['rows'] == 2
    # the ops: the lines of the description, whole, one under the other in
    # the Description column, then the second row under them
    ops = out['ops']
    k = next(i for i, o in enumerate(ops) if o['text'] == 'MK')
    lines = []
    for o in ops[k + 1:]:
        if o['text'] == '2':
            break
        lines.append(o)
    assert 2 <= len(lines) <= 3 and ' '.join(o['text'] for o in lines) == desc, [o['text'] for o in lines]
    assert not any('…' in o['text'] for o in lines)
    assert len({o['x'] for o in lines}) == 1 and lines[0]['x'] > TB_X, lines
    assert all(b['y'] - a['y'] == 22 for a, b in zip(lines, lines[1:])), lines
    assert all(o['size'] == 20 for o in lines)
    row2 = next(o for o in ops if o['text'] == 'Patch')
    assert row2['y'] > lines[-1]['y'] + 22, (row2, lines[-1])
    ok, why = _texts_match([o['text'] for o in ops], texts)
    assert ok, why


def _logo_png(size, color=(20, 60, 140, 255)):
    """A transparent PNG with an opaque mark in it - the alpha is what
    mask='auto' keeps clean on the page."""
    from PIL import Image, ImageDraw
    img = Image.new('RGBA', size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((size[0] // 10, size[1] // 10, size[0] * 9 // 10, size[1] * 9 // 10), fill=color)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode()


def test_a_logo_heads_the_title_block_on_every_sheet_and_reaches_the_pdf(page):
    """The logo is a preference read from a PNG / JPEG file in the dialog
    (an SVG is refused with a message - the PDF draws bitmaps), downscaled
    to 1200 px on its long side before it is stored as a data URL. Set, a
    box at the top of every sheet's title block holds it fitted and
    centred, drawn through the recorder's image op so the PDF page carries
    it as an XObject; not set, there is no box at all. No sheet says
    Notes, US or DS."""
    pg, ids = page
    png64 = _logo_png((2400, 600))
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10"/></svg>'
    out = pg.evaluate("""async ([png64, svgText]) => {
        const app = window.app;
        const toFile = (b64, name, type) => {
            const bin = atob(b64); const u = new Uint8Array(bin.length);
            for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
            return new File([u], name, { type });
        };
        const feed = (file) => {
            const input = document.getElementById('export-binder-logo');
            const dt = new DataTransfer(); dt.items.add(file);
            input.files = dt.files;
            input.dispatchEvent(new Event('change', { bubbles: true }));
        };
        const until = async (f, ms) => { const t0 = Date.now(); while (!f()) { if (Date.now() - t0 > ms) throw new Error('timeout'); await new Promise(r => setTimeout(r, 50)); } };
        const status = document.getElementById('export-binder-logo-status');
        const preview = document.getElementById('export-binder-logo-preview');
        const remove = document.getElementById('export-binder-logo-remove');
        const none = document.getElementById('export-binder-logo-none');
        document.getElementById('export-format').value = 'binder';
        document.getElementById('export-format').dispatchEvent(new Event('change'));
        const before = { logo: app.getBinderLogo(), none: none.style.display !== 'none', preview: preview.style.display !== 'none' };
        feed(new File([svgText], 'logo.svg', { type: 'image/svg+xml' }));
        await new Promise(r => setTimeout(r, 300));
        const refused = { status: status.textContent, shown: status.style.display !== 'none', logo: app.getBinderLogo() };
        feed(toFile(png64, 'logo.png', 'image/png'));
        await until(() => app.getBinderLogo() && preview.style.display !== 'none', 8000);
        await app._ensureBinderLogo();
        const src = app.getBinderLogo();
        const img = await app._binderLoadImage(src);
        return { before, refused, size: [img.naturalWidth, img.naturalHeight], prefix: src.slice(0, 22),
                 pref: app.getPreferences().binderLogo === src, bytes: src.length,
                 ui: { preview: preview.getAttribute('src') === src, remove: remove.style.display !== 'none',
                       none: none.style.display === 'none', status: status.textContent } };
    }""", [png64, svg])
    try:
        assert out['before'] == {'logo': '', 'none': True, 'preview': False}, out['before']
        assert 'SVG' in out['refused']['status'] and 'PNG or JPEG' in out['refused']['status'] and out['refused']['shown']
        assert out['refused']['logo'] == ''
        assert out['size'] == [1200, 300], out['size']                      # downscaled on read
        assert out['prefix'] == 'data:image/png;base64,' and out['pref'] and out['bytes'] < 400_000
        assert out['ui'] == {'preview': True, 'remove': True, 'none': True, 'status': ''}, out['ui']
        # every sheet: the logo box at the top of the block, the image
        # fitted inside it, REVISIONS under it; the map sheets carry the
        # map as well
        plan = _plan(pg, SHOW)
        h_logo = max(220, min(360, round((H - PAD * 2) * 0.16)))
        first_full = None
        for kind, number, title in plan:
            r = pg.evaluate("""async ([opts, title]) => {
                const app = window.app;
                const plan = app.planBinder(opts);
                const idx = plan.findIndex(p => p.title === title);
                const r = app.renderBinderPage(opts, idx);
                let pdf = null;
                if (idx === 0) {
                    // sheet 1.1's record through the route, on the live server
                    // (never the in-process client: its setup resets the
                    // project these browser tests share)
                    const rec = { name: r.record.name, width: r.record.width, height: r.record.height,
                                  page_size: r.record.page_size, ops: r.record.ops, images: r.record.images };
                    const resp = await fetch('/api/export/pdf-from-pages', { method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ project_name: 'Two Positions', pages: [rec] }) });
                    const buf = new Uint8Array(await resp.arrayBuffer());
                    let bin = '';
                    for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
                    pdf = { status: resp.status, b64: btoa(bin) };
                }
                return { texts: r.texts, logo: r.logo, sections: r.titleBlock.sections,
                         images: r.record.ops.filter(o => o.op === 'image'), pdf };
            }""", [json.loads(_SHOW_JSON), title])
            secs = r['sections']
            assert list(secs) == ['logo', 'revisions', 'show', 'people', 'title', 'number'], (title, list(secs))
            assert secs['logo'] == {'y': PAD, 'h': h_logo} and secs['revisions']['y'] == PAD + h_logo, (title, secs)
            im = r['images'][0]
            assert (im['x'], im['y'], im['w'], im['h']) == (r['logo']['x'], r['logo']['y'], r['logo']['w'], r['logo']['h']), (title, im, r['logo'])
            assert im['x'] >= TB_X + 18 and im['x'] + im['w'] <= TB_X + TB_W - 18, (title, im)
            assert im['y'] >= PAD + 18 and im['y'] + im['h'] <= PAD + h_logo - 18, (title, im)
            assert im['w'] == TB_W - 36 and abs(im['w'] / im['h'] - 4) < 0.05, (title, im)     # fitted to the width, 4:1
            assert abs((im['x'] + im['w'] / 2) - (TB_X + TB_W / 2)) <= 1 and abs((im['y'] + im['h'] / 2) - (PAD + h_logo / 2)) <= 1, (title, im)
            assert len(r['images']) == {'overview': 2, 'power': 2, 'data': 2, 'wiring': 3}.get(kind, 1), (title, r['images'])
            assert not [t for t in r['texts'] if t in ('Notes', 'US', 'DS')], (title, r['texts'][:30])
            if r['pdf']:
                first_full = r['pdf']
        # sheet 1.1's record through the route: the page carries the logo
        # and the raster as image XObjects
        assert first_full and first_full['status'] == 200, first_full
        from pypdf import PdfReader
        pdf_page = PdfReader(io.BytesIO(base64.b64decode(first_full['b64']))).pages[0]
        xobjects = pdf_page['/Resources'].get('/XObject', {})
        images = [x for x in xobjects.values() if x.get_object().get('/Subtype') == '/Image']
        assert len(images) == 2, len(images)
        # Remove: the preference cleared, no box, no image on a pull sheet
        gone = pg.evaluate("""async () => {
            const app = window.app;
            document.getElementById('export-binder-logo-remove').click();
            const t0 = Date.now();
            while (app.getBinderLogo()) { if (Date.now() - t0 > 5000) break; await new Promise(r => setTimeout(r, 50)); }
            await new Promise(r => setTimeout(r, 200));
            const opts = JSON.parse(%r);
            const idx = app.planBinder(opts).findIndex(p => p.kind === 'pull');
            const r = app.renderBinderPage(opts, idx);
            return { logo: app.getBinderLogo(), pref: app.getPreferences().binderLogo,
                     none: document.getElementById('export-binder-logo-none').style.display !== 'none',
                     preview: document.getElementById('export-binder-logo-preview').style.display !== 'none',
                     sections: Object.keys(r.titleBlock.sections), images: r.record.ops.filter(o => o.op === 'image').length,
                     drawn: r.logo };
        }""" % _SHOW_JSON)
        assert gone['logo'] == '' and gone['pref'] == '' and gone['none'] and not gone['preview'], gone
        assert gone['sections'][0] == 'revisions' and 'logo' not in gone['sections'] and gone['images'] == 0 and gone['drawn'] is None, gone
    finally:
        pg.evaluate("async () => { await window.app.setBinderLogo(''); window.app.syncBinderControls(); }")
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
        # A snake states its home run ONCE, as a heading under the unit's
        # band, and the rows beneath carry only what is the port's own
        # (2026-09-10: "Why is the same data written multiple times under
        # the snake under a specific port number"). So the walk steps over
        # the heading rather than assuming the rows start immediately.
        assert texts[i + 1] == \
            "SR Primary · 1-way · 100' / backup SR Backup · 1-way · 150'", texts[i:i + 4]
        rows = []
        j = i + 1
        while j < len(texts) and not re.fullmatch(r'SR-\d+', texts[j]):
            j += 1
        while j + 5 < len(texts) and re.fullmatch(r'SR-\d+', texts[j]):
            rows.append(texts[j:j + 6]); j += 6
        assert rows, texts[i:i + 20]
        for label, primary, backup, _panels, _px, home in rows:
            # the sending card the primary lands on, and the one the backup does
            assert re.fullmatch(r'H9 SR · \d+', primary), (label, primary)
            socket = primary.rsplit(' · ', 1)[-1]
            assert backup == f'{label}R · H9 slot 2 · {socket}', (label, backup)
            assert _on_map(out['mapTexts'], f'{label}R'), (label, out['mapTexts'])
            # the run itself is in the heading; the row says only the
            # extension this port adds, and which end carries it
            assert home == "+25' backup", (label, home)
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
        proc = _render(pg, SHOW, PROC)['texts']
        assert proc[proc.index('Redundancy') + 1] == 'Per card'
        assert not [t for t in proc if BOX_WORD.search(t)]
        # an unnamed card goes by its SLOT on its own processor, never by
        # the device's long model string (_bCardShort's rule, 2026-09-09 -
        # the model was being shrunk and cut); the row is its socket,
        # 'ext', the length and the snake it hangs off
        k = proc.index('ext')
        assert proc[k - 1] == 'H9 slot 2 1' and proc[k:k + 3] == ['ext', "25'", 'SR Backup'], proc[k - 3:k + 4]
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
        proc = _render(pg, SHOW, PROC)['texts']
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
        proc = _render(pg, SHOW, PROC)['texts']
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


# ── the plain sheet: the title block switched off ─────────────────────────
# "so we need to have a way to turn off the frame and extra text like
# overview and designer on the binder. Sometime having more screen real
# estate is better that way the screens fill the pdf" (2026-09-11).
#
# The switch is in the export dialog's Binder block and rides the options
# as `titleBlock`. OFF, a sheet loses three things and nothing else:
#   * the border rule round the sheet,
#   * the whole title block column - logo, REVISIONS, the show, the
#     people, the sheet title, the sheet number, the drawing date,
#   * the "rev 1.3" line in the corner.
# It KEEPS its own naming at the foot: the numbered view bubble and the
# subject heading beside it. Without the title block that line is the only
# thing saying which sheet this is and what order the sheets run in - "if
# you loose that naming then we just keep the naming at the bottom for
# page numbering essentially" - so both halves are asserted here. A test
# that only checked what disappeared would pass on a sheet with no name at
# all, which is the thing the user asked not to happen.
# Default is ON: every sheet is exactly the sheet it is today.

# Every sheet of the set, rendered: what it drew, the bubble it logged, the
# title block it logged, and the sheet-wide border rectangle if any.
SWEEP_JS = """([opts, borderW, borderH]) => {
    const app = window.app;
    const plan = app.planBinder(opts);
    return plan.map((p, i) => {
        const r = app.renderBinderPage(opts, i);
        const ops = (r.record && r.record.ops) || [];
        const border = ops.filter(o => o.op === 'rect' && o.stroke && !o.fill
                                       && Math.abs(o.w - borderW) < 2 && Math.abs(o.h - borderH) < 2)
                          .map(o => [o.x, o.y, o.w, o.h]);
        return { number: p.number, title: p.title, kind: p.kind, view: p.view || null,
                 names: p.names || null, sheetTitle: p.sheetTitle, extent: p.extent,
                 texts: r.texts, border,
                 bubble: r.bubble ? { number: r.bubble.number, name: r.bubble.name,
                                      x: r.bubble.x, y: r.bubble.y, r: r.bubble.r } : null,
                 titleBlock: r.titleBlock ? { x: r.titleBlock.x, w: r.titleBlock.w } : null };
    });
}"""


def _sweep(pg, opts):
    return pg.evaluate(SWEEP_JS, [opts, W - PAD * 2, H - PAD * 2])


def test_the_title_block_is_on_by_default_and_every_sheet_is_as_it_was(page):
    """Default ON. Options that say nothing about the switch plan and
    paint the very same set as options that say titleBlock: true, and every
    sheet of the show carries what it carries today - the border a quarter
    inch in, the title block's fields and rules, the rev line in the
    corner, and, on a map sheet, its numbered bubble and subject heading at
    the foot."""
    pg, ids = page
    bare = json.loads(_SHOW_JSON)
    bare.pop('titleBlock', None)
    on = json.loads(BLOCK_JSON)
    assert pg.evaluate("(o) => window.app.planBinder(o).map(p => [p.number, p.title, p.layout, p.cols, p.scale])", bare) \
        == pg.evaluate("(o) => window.app.planBinder(o).map(p => [p.number, p.title, p.layout, p.cols, p.scale])", on)
    sheets = _sweep(pg, on)
    assert [s['number'] for s in sheets] == [n for _k, n, _t in PLAN], sheets
    for s in sheets:
        where = (s['number'], s['title'])
        assert s['border'] == [[PAD, PAD, W - PAD * 2, H - PAD * 2]], (where, s['border'])
        for t in TB_STRINGS:
            assert t in s['texts'], (where, t)
        assert 'Untitled Project' in s['texts'], where
        assert s['sheetTitle'] in s['texts'] and s['number'] in s['texts'], where
        assert [t for t in s['texts'] if REV_LINE.match(t)] == ['rev 1.0'], where
        assert s['titleBlock'] == {'x': TB_X, 'w': TB_W}, (where, s['titleBlock'])
        # the naming at the foot: a map sheet's bubble, a column sheet's
        # subject heads
        if s['view']:
            assert s['bubble'] and s['bubble']['number'] == s['view'], (where, s['bubble'])
            assert s['bubble']['name'] == s['sheetTitle'].replace(' (CONT.)', ''), (where, s['bubble'])
        else:
            assert s['names'], where
            for n in s['names']:
                assert n.upper() in s['texts'], (where, n)


def test_the_plain_sheet_drops_the_block_and_keeps_its_naming(page):
    """The switch OFF: on NO sheet of the show is a title block string, a
    rev line, the sheet-wide border rectangle or the block's logged column
    drawn at all - AND every sheet still names itself, a map sheet by its
    numbered view bubble and its subject heading at the foot of the
    drawing, a column sheet by its subject heads. Both halves: the naming
    is the only thing left saying which sheet this is."""
    pg, ids = page
    sheets = _sweep(pg, json.loads(PLAIN_JSON))
    assert [s['number'] for s in sheets] == [n for _k, n, _t in PLAN], sheets
    for s in sheets:
        where = (s['number'], s['title'])
        # what goes
        assert s['border'] == [], (where, s['border'])
        assert s['titleBlock'] is None, where
        for t in TB_STRINGS:
            assert t not in s['texts'], (where, t, s['texts'][:40])
        assert not [t for t in s['texts'] if REV_LINE.match(t)], where
        assert 'Drawing Date' not in s['texts'] and 'Sheet Number' not in s['texts'], where
        # what stays - the sheet's own naming, at the foot
        if s['view']:
            b = s['bubble']
            assert b and b['number'] == s['view'], (where, b)
            assert b['name'] == s['sheetTitle'].replace(' (CONT.)', ''), (where, b)
            assert b['y'] + b['r'] <= DA_PLAIN['y'] + DA_PLAIN['h'] + 1, (where, b)
            assert b['y'] - b['r'] >= DA_PLAIN['y'] + DA_PLAIN['h'] * 0.4, (where, b)
        else:
            assert s['names'], where
            for n in s['names']:
                assert n.upper() in s['texts'], (where, n)
    # the whole show is still named somewhere the reader can find it: every
    # sheet number and every sheet title is on the overview's CONTENTS
    contents = sheets[0]['texts']
    for s in sheets:
        assert s['number'] in contents and s['sheetTitle'] in contents, s['number']


def test_the_plain_sheet_gives_the_drawing_the_blocks_width(page):
    """The room is real: with the block off the drawing area is the sheet
    inside the same small margin - exactly TB_W (480 page px, 2.4 in)
    wider than with it on - and a map sheet spends it, its map area the
    full width and its extent covering more of the sheet than before."""
    pg, ids = page
    assert DA_PLAIN['w'] - DA_BLOCK['w'] == TB_W
    # the drawing area itself, read off the sheet: the overview lays its
    # map across the whole of it
    a = _map_of(_render(pg, BLOCK, 'Overview'))['area']
    b = _map_of(_render(pg, PLAIN, 'Overview'))['area']
    assert a['w'] == DA_BLOCK['w'] and b['w'] == DA_PLAIN['w'], (a, b)
    assert b['w'] - a['w'] == TB_W and b['x'] == a['x'] == DA_PLAIN['x'], (a, b)
    # and a map sheet spends the room: WALL-A's wall is drawn bigger and
    # the sheet's own content covers more of the page (the layout is free
    # to change - a wider area can make map-left / tables-right the
    # covering one - so this measures area, not width)
    on = _render(pg, BLOCK, 'WALL-A - Power')
    off = _render(pg, PLAIN, 'WALL-A - Power')
    ma, mb = _map_of(on), _map_of(off)
    assert mb['w'] * mb['h'] > ma['w'] * ma['h'] * 1.1, (ma, mb)
    ea, eb = on['page']['extent'], off['page']['extent']
    assert eb['w'] * eb['h'] > ea['w'] * ea['h'], (ea, eb)
    assert eb['w'] > ea['w'] and eb['w'] == DA_PLAIN['w'], (ea, eb)
    # nothing of the drawing crosses into the sheet's margin
    for s in _sweep(pg, json.loads(PLAIN_JSON)):
        if s['extent']:
            assert s['extent']['w'] <= DA_PLAIN['w'] + 1 and s['extent']['h'] <= DA_PLAIN['h'] + 1, s


def test_the_title_block_switch_is_a_preference_the_dialog_reflects(page):
    """The switch is remembered beside the sheet size and the logo, so it
    survives a restart: the dialog's box writes binderTitleBlock to the
    preferences, the preferences come back through syncBinderControls into
    the box, and readBinderOptions reads the box."""
    pg, ids = page
    try:
        out = pg.evaluate("""async () => {
            const app = window.app;
            const fmt = document.getElementById('export-format');
            fmt.value = 'binder';
            fmt.dispatchEvent(new Event('change'));
            const box = document.getElementById('export-binder-title-block');
            const prefs = () => fetch('/api/preferences').then(r => r.json());
            const start = box.checked;
            // the box, changed the way a click changes it
            box.checked = false;
            box.dispatchEvent(new Event('change', { bubbles: true }));
            await new Promise(r => setTimeout(r, 250));
            const saved = (await prefs()).binderTitleBlock;
            const readOff = app.readBinderOptions().titleBlock;
            // as if the app had just started: the preferences into the dialog
            box.checked = true;
            app.syncBinderControls();
            const reflectedOff = box.checked;
            box.checked = true;
            box.dispatchEvent(new Event('change', { bubbles: true }));
            await new Promise(r => setTimeout(r, 250));
            const savedOn = (await prefs()).binderTitleBlock;
            const readOn = app.readBinderOptions().titleBlock;
            box.checked = false;
            app.syncBinderControls();
            return { start, saved, readOff, reflectedOff, savedOn, readOn,
                     reflectedOn: box.checked, getter: app.getBinderTitleBlock() };
        }""")
    finally:
        pg.evaluate("() => window.app.setBinderTitleBlock(true)")
        pg.wait_for_timeout(250)
    assert out['start'] is True, out                 # default ON
    assert out['saved'] is False and out['readOff'] is False, out
    assert out['reflectedOff'] is False, out
    assert out['savedOn'] is True and out['readOn'] is True, out
    assert out['reflectedOn'] is True and out['getter'] is True, out


# ── the smoke: the user's own show ───────────────────────────────────────

@pytest.mark.skipif(not os.path.exists(SCRATCH_FIXTURE),
                    reason='experts-only-fixture.json smoke fixture not present')
def test_smoke_experts_only(page):
    """The real show, FROZEN as experts-only-fixture.json - his save of
    2026-09-07 23:43 (the file's mtime; the experts-only.json beside it
    drifts with every save, the fixture never moves): SR - MAIN's 22
    custom circuits on four multis, SR - Return's six on multi 5 with
    five 2fers, SL mirroring SR; on data, box SR A on Card 1 and its
    backup end SR B on Card 3 (Card 1's 1:1 partner). 16 Tabloid
    sheets by series, none continued - the four screens, loose (the file
    keeps no beaches), alphabetical: SL before SR, power, data, then
    signal + power each;
    the four positions on ONE pull sheet, in position order; the two distros
    on one hardware sheet, H9 and the show's pull list on the next. SR -
    MAIN's power sheet (28 x 11, 22 circuits) is ONE sheet, map-left /
    tables-right in one column - the tables at the scale that fills the
    height (~1.23), the wall in the width they leave, the map and the
    CIRCUITS table disjoint; its data sheet, four ports, is the wall over
    its tables in two columns at 1.333; a Return (6 x 11) is a tall wall
    beside its tables at ~1.63, the tables to the height."""
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
        return app.planBinder(%s).map(p => [p.number, p.title, p.layout, p.cols, p.view, p.scale, p.extent, p.names]);
    }""" % SHOW, project)
    plan = [(n, t) for n, t, *_rest in pages]
    PULL4 = 'Pull - SR - MAIN, SR - Return, SL - MAIN, SL - Return'
    assert plan == [
        ('1.1', 'Overview'),
        ('2.1', 'SL - MAIN - Power'), ('2.2', 'SL - MAIN - Data'), ('2.3', 'SL - MAIN - Signal + Power'),
        ('2.4', 'SL - Return - Power'), ('2.5', 'SL - Return - Data'), ('2.6', 'SL - Return - Signal + Power'),
        ('2.7', 'SR - MAIN - Power'), ('2.8', 'SR - MAIN - Data'), ('2.9', 'SR - MAIN - Signal + Power'),
        ('2.10', 'SR - Return - Power'), ('2.11', 'SR - Return - Data'), ('2.12', 'SR - Return - Signal + Power'),
        ('3.1', PULL4),
        ('4.1', 'Distros - SR, SL'),
        ('4.2', 'Processor - H9 · Pull list'),
    ]
    layouts = {t: (l, c, v) for _n, t, l, c, v, *_rest in pages}
    scales = {t: sc for _n, t, _l, _c, _v, sc, *_rest in pages}
    extents = {t: e for _n, t, _l, _c, _v, _s, e, _names in pages}
    names = {t: nm for _n, t, _l, _c, _v, _s, _e, nm in pages}
    assert layouts['SR - MAIN - Power'] == ('side', 1, 8) and layouts['SR - Return - Power'] == ('side', 1, 11)
    assert layouts['SR - MAIN - Data'] == ('stack', 2, 9) and layouts['SR - Return - Data'] == ('side', 1, 12)
    assert layouts['SR - MAIN - Signal + Power'] == ('wiring', 2, 10) and layouts['SR - Return - Signal + Power'] == ('wiring', 2, 13)
    assert layouts['SL - MAIN - Power'] == ('side', 1, 2) and layouts['SL - MAIN - Data'] == ('stack', 2, 3)
    assert layouts['Overview'] == ('overview', 3, 1) and layouts[PULL4] == ('tables', 4, None)
    assert not [t for _n, t in plan if '(cont.)' in t]
    # the fill: SR - MAIN's 22 circuits are tons of info - the tables
    # reach the height at ~1.23 and the wall keeps the width they leave;
    # its data sheet stacks at the width-filling 1.333; the Return's
    # tables scale past 1.5 to the height; every extent inside the area;
    # the pull sheet (four columns across) and the hardware sheets scale
    # by the column rule, unchanged
    main_s = scales['SR - MAIN - Power']
    assert 1.15 < main_s < 1.35 and scales['SR - MAIN - Data'] == 1.333, scales
    ret_s = scales['SR - Return - Power']
    assert 1.5 < ret_s <= 2.4, scales
    for t in ('SR - MAIN - Power', 'SR - MAIN - Data', 'SR - Return - Power', 'SR - Return - Data'):
        ext = extents[t]
        assert ext['w'] <= DA['w'] + 1 and ext['h'] <= DA['h'] + 1, (t, ext)
        assert ext['h'] / DA['h'] >= 0.95, (t, ext)
    assert scales[PULL4] > 1 and scales['Distros - SR, SL'] > 1.5, scales
    # the positions side by side, the distros side by side, H9 with the
    # show's pull list beside it
    assert names[PULL4] == ['SR - MAIN', 'SR - Return', 'SL - MAIN', 'SL - Return']
    assert names['Distros - SR, SL'] == ['SR', 'SL'] and names['Processor - H9 · Pull list'] == ['H9', 'All positions']
    # eight positions make two pull sheets, four columns each
    two = pg.evaluate("""(opts) => {
        const app = window.app;
        const real = app.buildPullSheet;
        app.buildPullSheet = function () {
            const list = real.call(this);
            list.positions = list.positions.concat(list.positions.map(p => ({ ...p, name: p.name + ' B', key: p.key + '-b' })));
            return list;
        };
        try { return app.planBinder(opts).filter(p => p.kind === 'pull').map(p => [p.number, p.cols, p.names]); }
        finally { app.buildPullSheet = real; }
    }""", json.loads(_SHOW_JSON))
    assert two == [['3.1', 4, ['SR - MAIN', 'SR - Return', 'SL - MAIN', 'SL - Return']],
                   ['3.2', 4, ['SR - MAIN B', 'SR - Return B', 'SL - MAIN B', 'SL - Return B']]], two
    # on Letter SR - MAIN's power sheet stays at 1 and continues
    letter = pg.evaluate("(o) => window.app.planBinder(o).map(p => [p.title, p.scale])",
                         {**json.loads(_SHOW_JSON), 'sheet': 'letter'})
    k = [t for t, _s in letter].index('SR - MAIN - Power')
    assert letter[k] == ['SR - MAIN - Power', 1] and letter[k + 1][0] == 'SR - MAIN - Power (cont.)', letter
    main = _render(pg, SHOW, 'SR - MAIN - Power')
    texts = main['texts']
    _title_block(texts, 'SR - MAIN · POWER', '2.7', show='2026 Experts Only')
    # one Tabloid sheet, painted at 2x
    assert main['width'] == W * SCALE and main['height'] == H * SCALE
    # the map: the wall 28 x 11 of 60 x 120 px, uniformly, in the width the
    # one table column leaves at its scale - at least 45 % of the area
    m = main['map']
    want_main = (28 * 60) / (11 * 120)
    assert abs(m['w'] / m['h'] - want_main) / want_main < 0.01, m
    room_w = DA['w'] - (COL_W + COL_GAP) * main_s
    assert room_w >= round(DA['w'] * MAP_MIN_FRAC) and abs(m['area']['w'] - room_w) < 0.01 and m['area']['x'] == DA['x'], (m['area'], room_w)
    zoom = _fit(room_w, DA['h'] - BUBBLE_H * main_s, 28 * 60, 11 * 120)
    assert abs(m['zoom'] - zoom) < 0.01 and abs(m['w'] - 28 * 60 * zoom) <= 2, (m, zoom)
    assert m['w'] / room_w > 0.75 and m['scale'] == main_s, m
    # the CIRCUITS table beside the map, disjoint from it: every heading
    # right of the map's area, at the scale
    heads = {t: (x, y) for t, x, y in main['headings']}
    assert 'CIRCUITS' in heads and 'CABLES THIS SCREEN' in heads and 'FACTS' in heads, heads
    assert all(x >= m['area']['x'] + m['area']['w'] + COL_GAP * main_s - 1 for x, _y in heads.values()), (heads, m['area'])
    assert all(x + COL_W * main_s <= DA['x'] + DA['w'] + 1 for x, _y in heads.values()), heads
    assert heads['CIRCUITS'][1] < heads['CABLES THIS SCREEN'][1] < heads['FACTS'][1]
    # the view bubble under the map
    b = main['bubble']
    assert b['number'] == 8 and b['name'] == 'SR - MAIN · POWER'
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
    bands = _bands(texts)
    assert bands == [
        "SR1 · Multi 208 · 125' · 6 circuits",
        "SR2 · Multi 208 · 100' · 5 circuits",
        "SR3 · Multi 208 · 125' · 6 circuits",
        "SR4 · Multi 208 · 100' · 5 circuits",
    ]
    assert not [t for t in texts if 'home run' in t.lower()]
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
    # the tall narrow wall (6 x 11 of 60 x 120) beside four short tables:
    # the tables grow to the height (every text op the base size times the
    # scale), the wall keeps its aspect and fits the height over its
    # bubble in the width they leave, everything inside the area
    retp = _render(pg, SHOW, 'SR - Return - Power')
    rm = retp['map']
    want = (6 * 60) / (11 * 120)
    assert abs(rm['w'] / rm['h'] - want) / want < 0.01, rm
    room_w = DA['w'] - (COL_W + COL_GAP) * ret_s
    zoom = _fit(room_w, DA['h'] - BUBBLE_H * ret_s, 6 * 60, 11 * 120)
    assert zoom == (DA['h'] - BUBBLE_H * ret_s - GUT['top'] - GUT['bottom']) / (11 * 120)
    assert rm['scale'] == ret_s and abs(rm['zoom'] - zoom) < 0.01, (rm, zoom)
    assert rm['x'] >= DA['x'] and rm['y'] + rm['h'] <= DA['y'] + DA['h'] and abs(rm['area']['w'] - room_w) < 0.01, rm
    assert len(retp['brackets']) == 1 and retp['brackets'][0]['depth'] == 0
    rrec = _record(pg, json.loads(_SHOW_JSON), 'SR - Return - Power')
    rsizes = {o['size'] for o in rrec['record']['ops'] if o['op'] == 'text'}
    assert round(25 * ret_s, 2) in rsizes and round(24 * ret_s, 2) in rsizes, (ret_s, rsizes)
    assert 22 in rsizes and 28 in rsizes, rsizes                          # the rulers and the bracket, inch sizes
    assert 26 in rsizes and 56 in rsizes and 25 not in rsizes, rsizes      # the title block at its own size
    rheads = {t: (x, y) for t, x, y in retp['headings']}
    assert {'CIRCUITS', 'CABLES THIS SCREEN', 'FACTS', 'GANGS'} <= set(rheads), rheads
    assert all(x >= rm['area']['x'] + rm['area']['w'] for x, _y in rheads.values()), (rheads, rm['area'])
    ret = retp['texts']
    assert 'GANGS' in ret
    i = ret.index('GANGS')
    assert ret[i + 4:i + 4 + 15:3] == ['SR5-1', 'SR5-2', 'SR5-3', 'SR5-4', 'SR5-5']
    assert ret.count('2fer') == 5
    assert "SR5 · Multi 208 · 125' · 6 circuits" in ret
    dpage = _render(pg, SHOW, 'SR - MAIN - Data')
    assert not _on_map(dpage['mapTexts'], 'SR - MAIN')
    _title_block(dpage['texts'], 'SR - MAIN · DATA', '2.8', show='2026 Experts Only')
    # the same wall over its four ports: the Ports table (six columns of
    # whole names) and the cables in one wide column, the facts in the
    # other, the row filling the width at 1.333, the wall the height left
    dm = dpage['map']
    assert abs(dm['w'] / dm['h'] - want_main) / want_main < 0.01, dm
    assert dm['area']['w'] == DA['w'] and abs(dm['zoom'] - _fit(DA['w'], dm['area']['h'], 28 * 60, 11 * 120)) < 0.01, dm
    dheads = {t: (x, y) for t, x, y in dpage['headings']}
    assert all(y >= dm['area']['y'] + dm['area']['h'] for _x, y in dheads.values()), (dheads, dm['area'])
    assert dheads['PORTS'][0] == DA['x'] and dheads['FACTS'][0] > DA['x'] + DATA_COL_W, dheads
    assert 'PORTS' in dpage['texts']
    data = dpage['texts']
    # the box delivering the ports is the band (2026-09-07: a CVT4K-S on
    # each card, all 16 sockets), the model and the name its ⚙ carries -
    # "CVT4K-S SR A" - the ports its own labels
    assert 'CVT4K-S SR A · OPT 1-2 · 16 ports · no fiber length' in data
    assert ['SR A-1', 'SR A-2', 'SR A-3', 'SR A-4'] == [t for t in data if re.fullmatch(r'SR A-\d', t)]
    # the return end, whole: the backup port's label and where it lands -
    # box SR B on Card 3, Card 1's 1:1 partner
    assert [t for t in data if re.fullmatch(r'SR B-\d · CVT4K-S SR B · \d', t)] == [
        'SR B-1 · CVT4K-S SR B · 1', 'SR B-2 · CVT4K-S SR B · 2', 'SR B-3 · CVT4K-S SR B · 3', 'SR B-4 · CVT4K-S SR B · 4']
    assert not [t for t in data if t.startswith('slot ')]
    # Each snake's home run is stated ONCE, as a heading over the ports
    # that ride it, and a row carries only the extension that port adds
    # (2026-09-10: "Why is the same data written multiple times under the
    # snake under a specific port number"). Where only one end extends,
    # the row says which end, so two mirrored screens do not both read
    # "+25'". One barrel per extension, primary and backup, six in all,
    # still counted in Cables this screen.
    heading = "SR A · 4-way · 150' / backup SR B · 4-way · 100'"
    assert data.count(heading) == 1, [t for t in data if 'SR A ·' in t]
    assert data.index(heading) < data.index('SR A-1'), data
    assert data[data.index('SR A-1') + 5] == "+10' both ends", data
    assert data[data.index('SR A-2') + 5] == '—', data
    assert data[data.index('SR A-3') + 5] == "+25' / +10'", data
    assert data[data.index('SR A-4') + 5] == "+25' / +75'", data
    cables = data[data.index('CABLES THIS SCREEN'):data.index('FACTS')]
    k = cables.index('Ether-con Barrel')
    assert cables[k:k + 3] == ['Ether-con Barrel', 'EA', '6'], cables
    # the processor once, the redundancy in the bar's words
    assert data[data.index('Processor') + 1] == 'H9' and 'H9 · H9' not in data
    assert data[data.index('Redundancy') + 1] == 'Per card'
    # the overview: every wall outlined - the four sit edge to edge and read
    # as one in the bitmap, so each wears its own INK rule, both palettes
    for palette in ('colour', 'printer'):
        rec = _record(pg, {**json.loads(_SHOW_JSON), 'palette': palette}, 'Overview')
        screens = rec['map']['screens']
        assert sorted(sc['name'] for sc in screens) == ['SL - MAIN', 'SL - Return', 'SR - MAIN', 'SR - Return'], screens
        assert len(_outlines(rec['record']['ops'], screens)) == 4, palette
        by = {sc['name']: sc for sc in screens}
        assert abs(by['SR - MAIN']['w'] / by['SR - MAIN']['h'] - (28 * 60) / (11 * 120)) < 0.02, by['SR - MAIN']
        assert abs(by['SR - Return']['w'] / by['SR - Return']['h'] - (6 * 60) / (11 * 120)) < 0.02, by['SR - Return']
    # the overview's contents names every sheet
    ov = _render(pg, SHOW, 'Overview')['texts']
    c = ov.index('CONTENTS')
    listed = [(ov[c + 3 + 2 * n], ov[c + 4 + 2 * n]) for n in range(len(plan))]
    assert [n for n, _t in listed] == [n for n, _t in plan]
    assert listed[1] == ('2.1', 'SL - MAIN · POWER') and listed[2] == ('2.2', 'SL - MAIN · DATA')
    assert listed[3] == ('2.3', 'SL - MAIN · SIGNAL + POWER')
    assert listed[-3:] == [('3.1', 'PULL · SR - MAIN, SR - RETURN, SL - MAIN, SL - RETURN'), ('4.1', 'DISTROS · SR, SL'),
                           ('4.2', 'PROCESSOR · H9 · PULL LIST')], listed[-3:]
    # no sheet says box, none says breakout as the generic noun, none Palette
    for idx in range(len(plan)):
        texts_i = pg.evaluate("([o, i]) => window.app.renderBinderPage(o, i).texts", [json.loads(_SHOW_JSON), idx])
        boxy = [t for t in texts_i if BOX_WORD.search(t) and 'breakout box' not in t.lower()]
        assert not boxy, (idx, boxy)
        assert not _generic_breakout(texts_i), (idx, _generic_breakout(texts_i))
        assert not [t for t in texts_i if 'palette' in t.lower()], idx
    distro = _render(pg, SHOW, 'Distros - SR, SL')['texts']
    assert distro.count('5 MULTI 208') == 2 and 'NAME' in distro, distro
    assert distro.count('28 on 5 Multi 208') == 2, [t for t in distro if 'Multi 208' in t]
    assert distro.index('SR') < distro.index('5 MULTI 208') < distro.index('SL'), distro     # a column each, headed
    # the pull sheet: four columns headed by the positions, every position's
    # four tables under its name
    pull = _render(pg, SHOW, PULL4)
    ptexts = pull['texts']
    for name in ('SR - MAIN', 'SR - RETURN', 'SL - MAIN', 'SL - RETURN'):
        assert name in ptexts, name
    assert ptexts.count('POWER CABLES') == 4 and ptexts.count('SCREENS') == 4, ptexts
    heads = pull['headings']
    xs = sorted({x for t, x, _y in heads if t == 'POWER CABLES'})
    assert len(xs) == 4 and all(b - a > 600 for a, b in zip(xs, xs[1:])), xs
    assert 'BREAKOUTS' not in distro and 'Breakouts' not in distro
    assert ids['errors'] == []


# The buddy's show, in shape only (2026-09-08: seven IMAG and delay walls on
# separate canvases, 9 x 5 and 6 x 4 and 5 x 3 of 216 px, no beaches; the
# file itself is his and stays out of the repo): one 9 x 5 wall of 216 px
# at 208 V / 20 A / 800 W a panel - a column of five panels a circuit, nine
# circuits on two multis of one distro - with its ports on one card. Built fresh on the
# server; the module's guard puts the show back afterwards.
NINE_BY_FIVE_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = []; proj.beaches = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.binder;
    proj.name = 'Nine by Five';
    await j('PUT', '/api/project', proj);
    await j('POST', '/api/layer/add', {name: 'D - OffSL IMAG', columns: 9, rows: 5, cabinet_width: 216, cabinet_height: 216,
               powerVoltage: 208, powerAmperage: 20, panelWatts: 800,
               powerFlowPattern: 'tl-v', powerOrganized: true, flowPattern: 'tl-h',
               processorType: 'novastar-armor'});
    let st = await j('POST', '/api/processors', {deviceId: 'novastar-h9'});
    const pid = st.processors[0].id;
    st = await j('PUT', `/api/processors/${pid}/slots/0`, {deviceId: 'novastar-card-h-16xrj45-2xfiber'});
    const cardId = st.processors[0].slots[0].card.id;
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('binder_nine_by_five');
    const l = app.project.layers.find(x => x.name === 'D - OffSL IMAG');
    app.selectLayer(l);
    const d = app.addDistro({name: 'SR'});
    app.setSocaDistro(l, 1, d.id); app.setSocaNumber(l, 1, 1); app.setSocaLength(l, 1, '125');
    app.setSocaDistro(l, 2, d.id); app.setSocaNumber(l, 2, 2); app.setSocaLength(l, 2, '100');
    // the multi edits PUT their layer fire-and-forget: land the whole
    // project before the processor calls read it back
    await j('PUT', '/api/project', app.project);
    await app.refreshProcessors();
    await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST', {layerId: String(l.id), cardId});
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    window.canvasRenderer.render();
    app.resetHistory('Nine by Five');
    const plan = app.getSocaPlan(l);
    return { id: l.id, circuits: app.screenCircuits(l).length, multis: plan.map(s => [s.name, s.legs.length]) };
}"""

# ARCH C: 24 x 18 in at 200 px/in, its drawing area by the same frame.
ARCHC_W, ARCHC_H = 4800, 3600
DA_ARCHC = {'x': PAD + DA_PAD, 'y': PAD + DA_PAD, 'w': ARCHC_W - PAD - TB_W - PAD - DA_PAD * 2, 'h': ARCHC_H - PAD * 2 - DA_PAD * 2}
def test_the_fill_picks_the_layout_that_covers_most(page):
    """Coverage decides (2026-09-08, on his buddy's 9 x 5 IMAG walls: the map
    filled the width, the tables sat at 1x in one column and the lower
    half of the Tabloid sheet was empty; on ARCH C the map was near its 3x
    cap over tables at 1x, tiny). Both layouts are tried with the TABLES'
    scale chosen for each, the map taking the room the tables leave, and
    the one whose ink covers more of the drawing area wins. The 9 x 5 wall
    (1944 x 1080 px, nine circuits on two multis) at Tabloid: STACK, the
    map across the full width, the tables at ~1.28 under it in three
    columns, coverage past 0.8; at ARCH C: STACK, the map at full width
    (zoom ~1.94, under the cap), the tables at ~1.93. The map is painted
    in page units - its rulers and brackets at their inch sizes - and the
    tables at the scale; nothing reaches past the drawing area."""
    pg, ids = page
    seed = pg.evaluate(NINE_BY_FIVE_JS)
    assert seed['circuits'] == 9 and [n for _name, n in seed['multis']] == [6, 3], seed
    pg.wait_for_timeout(600)
    title = 'D - OffSL IMAG - Power'
    ww, wh = 9 * 216, 5 * 216
    tabloid = _render(pg, SHOW, title)
    p = tabloid['page']
    m = _map_of(tabloid)
    s = p['scale']
    assert p['layout'] == 'stack' and p['cols'] == 3, p
    assert abs(s - 1.278) < 0.1, p
    assert p['coverage'] >= 0.8, p
    # the map: full width, the wall centred in it, its zoom the fit of the
    # height the tables leave (they set it: the row fills the width)
    assert m['area']['x'] == DA['x'] and m['area']['w'] == DA['w'] and m['area']['y'] == DA['y'], m
    assert abs(m['w'] / m['h'] - ww / wh) / (ww / wh) < 0.01, m
    zoom = _fit(DA['w'], m['area']['h'], ww, wh)
    assert abs(m['zoom'] - zoom) < 0.01 and abs(m['w'] - ww * zoom) <= 2, (m, zoom)
    inner_cx = DA['x'] + GUT['left'] + (DA['w'] - GUT['left'] - GUT['right']) / 2
    assert 1150 <= m['area']['h'] <= 1300 and abs(m['x'] + m['w'] / 2 - inner_cx) <= 1, m
    assert m['scale'] == s
    # the three tables under it, side by side, at the scale - each heading
    # below the map, the row across the width, inside the area
    heads = {t: (x, y) for t, x, y in tabloid['headings']}
    assert set(heads) == {'CIRCUITS', 'CABLES THIS SCREEN', 'FACTS'}, heads
    xs = sorted(x for x, _y in heads.values())
    assert all(y >= m['area']['y'] + m['area']['h'] for _x, y in heads.values()), (heads, m['area'])
    assert xs[0] == DA['x'] and all(b - a >= (COL_W + COL_GAP) * s - 1 for a, b in zip(xs, xs[1:])), xs
    assert xs[-1] + COL_W * s <= DA['x'] + DA['w'] + 1, xs
    ext = p['extent']
    assert ext['w'] <= DA['w'] + 1 and ext['h'] <= DA['h'] + 1, ext
    b = tabloid['bubble']
    assert b['y'] - b['r'] >= m['area']['y'] + m['area']['h'] and b['y'] + b['r'] <= min(y for _x, y in heads.values()), (b, heads)
    # the bands and the rows say what the wall is
    texts = tabloid['texts']
    bands = _bands(texts)
    assert bands == ["SR1 · Multi 208 · 125' · 6 circuits", "SR2 · Multi 208 · 100' · 3 circuits"], bands
    assert len([t for t in texts if re.fullmatch(r'SR[12]-\d', t)]) == 9
    # the record: the tables' text at base x s, the rulers and brackets at
    # their own sizes, the title block at its own
    rec = _record(pg, json.loads(_SHOW_JSON), title)
    sizes = {o['size'] for o in rec['record']['ops'] if o['op'] == 'text'}
    assert round(25 * s, 2) in sizes and round(24 * s, 2) in sizes and round(21 * s, 2) in sizes, (s, sizes)
    assert 22 in sizes and 28 in sizes and 56 in sizes and 25 not in sizes, sizes
    img = [o for o in rec['record']['ops'] if o['op'] == 'image']
    assert len(img) == 1 and img[0]['x'] == DA['x'] and img[0]['y'] == DA['y'] and img[0]['w'] == DA['w'], img
    # ARCH C: the same rule, the wall filling the width under the cap
    archc = _render(pg, SHOW.replace("sheet: 'tabloid'", "sheet: 'archc'"), title)
    pc = archc['page']
    mc = _map_of(archc)
    sc = pc['scale']
    assert pc['layout'] == 'stack' and pc['cols'] == 3 and 1.85 <= sc <= 2.05, pc
    assert mc['area']['w'] == DA_ARCHC['w'] and abs(mc['w'] - (DA_ARCHC['w'] - GUT['left'] - GUT['right'])) <= 2, mc
    assert abs(mc['zoom'] - (DA_ARCHC['w'] - GUT['left'] - GUT['right']) / ww) < 0.01 and mc['zoom'] < MAP_ZOOM_CAP, mc
    assert pc['coverage'] >= 0.8, pc
    cheads = {t: (x, y) for t, x, y in archc['headings']}
    assert all(y >= mc['area']['y'] + mc['area']['h'] for _x, y in cheads.values()), (cheads, mc['area'])
    assert max(x for x, _y in cheads.values()) + COL_W * sc <= DA_ARCHC['x'] + DA_ARCHC['w'] + 1, cheads
    assert pc['extent']['w'] <= DA_ARCHC['w'] + 1 and pc['extent']['h'] <= DA_ARCHC['h'] + 1, pc['extent']
    # the data sheet of the same wall: three short tables - stack too, the
    # map over them, everything inside the area
    data = _render(pg, SHOW, 'D - OffSL IMAG - Data')
    pd = data['page']
    assert pd['layout'] == 'stack' and pd['scale'] > 1 and pd['coverage'] > 0.6, pd
    assert pd['extent']['w'] <= DA['w'] + 1 and pd['extent']['h'] <= DA['h'] + 1, pd
    # the whole set's sheets, every one inside its drawing area
    plan = pg.evaluate("(o) => window.app.planBinder(o)", json.loads(_SHOW_JSON))
    for e in plan:
        if e['extent']:
            assert e['extent']['w'] <= DA['w'] + 1 and e['extent']['h'] <= DA['h'] + 1, e
    # the sheets as PDFs, for a look (pdftoppm), when asked
    out_dir = os.environ.get('LRD_BINDER_PDF_DIR')
    if out_dir:
        for key in ('tabloid', 'archc'):
            pdf = pg.evaluate("""async ([opts, title]) => {
                const app = window.app;
                const plan = app.planBinder(opts);
                const idx = plan.findIndex(p => p.title === title);
                const pages = app.renderBinderPages(opts, { bitmaps: false }).slice(idx, idx + 1);
                const resp = await fetch('/api/export/pdf-from-pages', { method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ project_name: app.project.name, pages }) });
                const buf = new Uint8Array(await resp.arrayBuffer());
                let bin = ''; for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
                return { status: resp.status, b64: btoa(bin) };
            }""", [{**json.loads(_SHOW_JSON), 'sheet': key}, title])
            assert pdf['status'] == 200
            with open(os.path.join(out_dir, f'fill-9x5-{key}.pdf'), 'wb') as fh:
                fh.write(base64.b64decode(pdf['b64']))
    assert ids['errors'] == []


# Three screens, "B - X", "A - Y", "C - Z", added in that order (so the
# layer list runs B, A, C and the Screens panel, newest on top, shows C, A,
# B), one distro and one H9 card. Built fresh; the guard restores.
ORDER_SEED_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = []; proj.beaches = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.binder;
    proj.name = 'Three Walls';
    await j('PUT', '/api/project', proj);
    let x = 0;
    for (const name of ['B - X', 'A - Y', 'C - Z']) {
        await j('POST', '/api/layer/add', {name, columns: 4, rows: 3, cabinet_width: 200, cabinet_height: 200,
                   powerVoltage: 208, powerAmperage: 10, panelWatts: 200,
                   powerFlowPattern: 'tl-h', powerOrganized: true, flowPattern: 'tl-h',
                   processorType: 'novastar-armor', offset_x: x});
        x += 900;
    }
    let st = await j('POST', '/api/processors', {deviceId: 'novastar-h9'});
    const pid = st.processors[0].id;
    st = await j('PUT', `/api/processors/${pid}/slots/0`, {deviceId: 'novastar-card-h-16xrj45-2xfiber'});
    const cardId = st.processors[0].slots[0].card.id;
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('binder_order');
    const L = (n) => app.project.layers.find(l => l.name === n);
    const b = L('B - X'), a = L('A - Y'), c = L('C - Z');
    app.selectLayer(b);
    const d = app.addDistro({name: 'SR'});
    // power: B on multi 1, A on 2, C on 3 of the one distro
    app.setSocaDistro(b, 1, d.id); app.setSocaNumber(b, 1, 1); app.setSocaLength(b, 1, '125');
    app.setSocaDistro(a, 1, d.id); app.setSocaNumber(a, 1, 2); app.setSocaLength(a, 1, '100');
    app.setSocaDistro(c, 1, d.id); app.setSocaNumber(c, 1, 3); app.setSocaLength(c, 1, '75');
    await j('PUT', '/api/project', app.project);
    await app.refreshProcessors();
    // data: C's ports placed first, then B's, then A's - C on socket 1
    for (const l of [c, b, a]) {
        await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
                                     {layerId: String(l.id), cardId});
    }
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    window.canvasRenderer.render();
    app.resetHistory('Three Walls');
    return { ids: { a: a.id, b: b.id, c: c.id }, layerOrder: app.project.layers.map(l => l.name),
             firstSockets: Object.fromEntries(app.project.layers.map(l => {
                 const asg = (app._assignment.screens || []).find(s => String(s.layerId) === String(l.id));
                 return [l.name, Math.min(...((asg && asg.ports) || []).map(p => parseInt(p.port, 10)))];
             })) };
}"""

SCREENS_JS = """(o) => window.app.planBinder(o).filter(p => p.kind === 'power').map(p => p.subject)"""


def test_the_screens_run_in_the_order_the_project_keeps(page):
    """project.binder.screenOrder (2026-09-08, his buddy's walls "A - OffSR
    IMAG" … "G - E3 Delay": "i'd want raster A first, then in alphabetical
    order"): alphabetical by default, natural; the Screens panel's order
    top-down or bottom-up; by first port (processor, card slot, socket);
    by first circuit (distro, multi, circuit). Beaches still come first -
    the order sorts within one. The export dialog's Screen order select
    sets it with one undo entry, saved through the project like the title
    block's fields and read back from a loaded file; the CONTENTS and the
    view numbers follow."""
    pg, ids = page
    seed = pg.evaluate(ORDER_SEED_JS)
    pg.wait_for_timeout(600)
    assert seed['layerOrder'] == ['B - X', 'A - Y', 'C - Z'], seed
    assert seed['firstSockets']['C - Z'] == 1 and seed['firstSockets']['B - X'] < seed['firstSockets']['A - Y'], seed
    opts = json.loads(_SHOW_JSON)
    order = lambda: pg.evaluate(SCREENS_JS, opts)  # noqa: E731
    set_order = lambda v: pg.evaluate("(v) => window.app.setBinderField('screenOrder', v, 'Set Screen Order')", v)  # noqa: E731
    # the default: alphabetical
    assert pg.evaluate("() => window.app.getBinderInfo().screenOrder") == 'alpha'
    assert order() == ['A - Y', 'B - X', 'C - Z']
    # the Screens panel's order, top-down (newest on top) and bottom-up
    set_order('layers')
    assert order() == ['C - Z', 'A - Y', 'B - X']
    set_order('layers-up')
    assert order() == ['B - X', 'A - Y', 'C - Z']
    # by first port: C was placed first
    set_order('data')
    assert order() == ['C - Z', 'B - X', 'A - Y']
    # by first circuit: B is on multi 1
    set_order('power')
    assert order() == ['B - X', 'A - Y', 'C - Z']
    # natural: "Wall 2" before "Wall 10"
    natural = pg.evaluate("""() => {
        const app = window.app;
        const L = (n) => app.project.layers.find(l => l.name === n);
        const [b, a, c] = [L('B - X'), L('A - Y'), L('C - Z')];
        const names = [b.name, a.name, c.name];
        [b.name, a.name, c.name] = ['Wall 10', 'Wall 2', 'wall 1'];
        try {
            app.setBinderField('screenOrder', 'alpha', 'Set Screen Order');
            return app.planBinder(%s).filter(p => p.kind === 'power').map(p => p.subject);
        } finally { [b.name, a.name, c.name] = names; }
    }""" % _SHOW_JSON)
    assert natural == ['wall 1', 'Wall 2', 'Wall 10'], natural
    # beaches first: C on SR, A and B on SL, SR before SL - then alphabetical
    # within each
    beached = pg.evaluate("""async (ids) => {
        const app = window.app;
        const j = (method, url, body) => fetch(url, {method, headers: {'Content-Type': 'application/json'},
            body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
        const sr = (await j('POST', '/api/beaches', {name: 'SR'})).beach;
        const sl = (await j('POST', '/api/beaches', {name: 'SL'})).beach;
        const p = await j('GET', '/api/project');
        for (const l of p.layers) l.beachId = l.id === ids.c ? sr.id : sl.id;
        await j('PUT', '/api/project', p);
        app.project = await j('GET', '/api/project');
        app.dedupeProjectLayers('binder_order_beaches');
        app._circuitTailCache = null;
        const plan = app.planBinder(%s);
        const overview = app.renderBinderPage(%s, 0).texts;
        return { screens: plan.filter(x => x.kind === 'power').map(x => [x.subject, x.number, x.view]),
                 titles: plan.map(x => [x.number, x.sheetTitle]), overview, beaches: app.project.beaches.map(b => b.name) };
    }""" % (_SHOW_JSON, _SHOW_JSON), seed['ids'])
    assert beached['beaches'] == ['SR', 'SL'], beached['beaches']
    assert beached['screens'] == [['C - Z', '2.1', 2], ['A - Y', '2.4', 5], ['B - X', '2.7', 8]], beached['screens']
    # the CONTENTS on 1.1 lists them so
    ov = beached['overview']
    k = ov.index('CONTENTS')
    listed = [(ov[k + 3 + 2 * n], ov[k + 4 + 2 * n]) for n in range(len(beached['titles']))]
    assert listed == [tuple(t) for t in beached['titles']], listed
    assert listed[1:4] == [('2.1', 'C - Z · POWER'), ('2.2', 'C - Z · DATA'), ('2.3', 'C - Z · SIGNAL + POWER')], listed
    # the dialog's select: one undo entry, the same POST as the other
    # fields, read back from a loaded file; a stray value reads as alpha
    out = pg.evaluate("""async () => {
        const app = window.app;
        const j = (method, url, body) => fetch(url, {method, headers: {'Content-Type': 'application/json'},
            body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
        document.getElementById('export-format').value = 'binder';
        document.getElementById('export-format').dispatchEvent(new Event('change'));
        const sel = document.getElementById('export-binder-screen-order');
        const shown = sel.value;
        const options = [...sel.options].map(o => [o.value, o.textContent]);
        const h0 = app.historyIndex;
        sel.value = 'layers';
        sel.dispatchEvent(new Event('change'));
        const actions = app.history.slice(h0 + 1).map(h => h.action);
        await app._binderPushQueue;
        const served = (await j('GET', '/api/project')).binder;
        const p = await j('GET', '/api/project');
        p.binder = { ...(p.binder || {}), screenOrder: 'power' };
        await j('PUT', '/api/project', p);
        app.project = await j('GET', '/api/project');
        app.syncBinderControls();
        const loaded = { info: app.getBinderInfo().screenOrder, select: sel.value,
                         screens: app.planBinder(%s).filter(x => x.kind === 'power').map(x => x.subject) };
        app.project.binder.screenOrder = 'sideways';
        const stray = app.getBinderInfo().screenOrder;
        return { shown, options, actions, served, loaded, stray, tail: options.some(([_v, t]) => /\\btails?\\b/i.test(t)) };
    }""" % _SHOW_JSON)
    assert out['shown'] == 'alpha', out['shown']
    assert [v for v, _t in out['options']] == ['alpha', 'layers', 'layers-up', 'data', 'power'], out['options']
    assert out['actions'] == ['Set Screen Order'], out['actions']
    assert out['served']['screenOrder'] == 'layers', out['served']
    assert out['loaded'] == {'info': 'power', 'select': 'power', 'screens': ['C - Z', 'B - X', 'A - Y']}, out['loaded']
    assert out['stray'] == 'alpha' and not out['tail'], out
    assert ids['errors'] == []


# The Screens panel's rows as the eye reads them, TOP FIRST, straight off
# the DOM: renderLayers reverses the layer array, regroupLayersByCanvas
# deals the rows into canvas groups and regroupLayersByGroup gathers a
# screen group - so the panel is not "the layer array reversed" the moment
# a show has more than one canvas.
PANEL_ORDER_JS = """() => {
    const app = window.app;
    const byId = new Map((app.project.layers || []).map(
        l => [String(l.id), l.name]));
    return [...document.querySelectorAll('#layers-list .layer-item')]
        .map(el => byId.get(String(el.dataset.layerId)))
        .filter(Boolean);
}"""

SECOND_CANVAS_JS = """async (name) => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)})
        .then(r => r.json());
    await app.addCanvas();
    const p = await j('GET', '/api/project');
    const cid = p.canvases[p.canvases.length - 1].id;
    for (const l of p.layers) if (l.name === name) l.canvas_id = cid;
    await j('PUT', '/api/project', p);
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('binder_order_canvas');
    app.renderLayers();
    return cid;
}"""

RESTORE_CANVAS_JS = """async (o) => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)})
        .then(r => r.json());
    const p = await j('GET', '/api/project');
    const home = p.canvases[0].id;
    for (const l of p.layers) if (l.canvas_id === o.cid) l.canvas_id = home;
    p.active_canvas_id = home;
    await j('PUT', '/api/project', p);
    await fetch(`/api/canvas/${o.cid}`, {method: 'DELETE'});
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('binder_order_canvas_restore');
    app.renderLayers();
    return app.project.canvases.length;
}"""


def test_the_layers_order_is_the_screens_panel_read_top_down(page):
    """"top to bottom does bottom to top actually" (2026-09-09). The
    'layers' order is the Screens panel EXACTLY as the user reads it -
    the topmost card first - and 'layers-up' is that list reversed. Pinned
    against the panel's own DOM, not against a model of it: the panel is
    the layer array reversed, dealt into canvas groups, with screen groups
    gathered, and reading the array backwards stopped being the same thing
    the moment a show had a second canvas."""
    pg, ids = page
    seed = pg.evaluate(ORDER_SEED_JS)
    pg.wait_for_timeout(600)
    assert seed['layerOrder'] == ['B - X', 'A - Y', 'C - Z'], seed
    opts = json.loads(_SHOW_JSON)
    order = lambda: pg.evaluate(SCREENS_JS, opts)  # noqa: E731
    set_order = lambda v: pg.evaluate(  # noqa: E731
        "(v) => window.app.setBinderField('screenOrder', v, 'Set Screen Order')", v)
    cid = None
    try:
        for where in ('one canvas', 'two canvases'):
            panel = pg.evaluate(PANEL_ORDER_JS)
            print(f'\npanel top-down, {where}:', panel)
            assert len(panel) == 3, panel
            set_order('layers')
            down = order()
            set_order('layers-up')
            up = order()
            print(f'plan under layers, {where}:', down, '| layers-up:', up)
            # the plan carries the screens the panel shows, in the panel's
            # own order - and the other way for 'layers-up'
            kept = [n for n in panel if n in down]
            assert down == kept, (down, panel)
            assert up == kept[::-1], (up, panel)
            if where == 'two canvases':
                break
            cid = pg.evaluate(SECOND_CANVAS_JS, 'A - Y')
            pg.wait_for_timeout(600)
            assert cid, 'no second canvas'
            moved = pg.evaluate(PANEL_ORDER_JS)
            assert moved != panel, (
                'the second canvas must change the panel, or this proves '
                'nothing', moved, panel)
    finally:
        if cid:
            left = pg.evaluate(RESTORE_CANVAS_JS, {'cid': cid})
            pg.wait_for_timeout(500)
            assert left == 1, left
        set_order('alpha')
        pg.wait_for_timeout(300)
