"""A meters show on paper: the binder's headings and the pull-sheet workbook.

  * The binder prints its headings in caps (table titles, the sheet title,
    the column heads). A cable length keeps its unit as every other paper
    prints it: "STRAND MAP · TAC A · TAC 8 · LC DUPLEX · 100 m", never
    "100 M". A feet show reads as it always has ("100'").
  * The workbook is a feet template. In a meters show the copy's GEAR LIST
    Length dropdown offers 1, 2, 3, 5, 10, 15, 20, 25, 30, 50, 75, 100,
    150, 200, 250, 300 m, then EA, then any other length the show uses,
    never the template's feet (the owner's ruling, 2026-10-16). It is a
    list of its own, not the long jumper's rounding ladder, and the in-app
    editor's picker offers the same one; the READ ME gives meters
    examples; and the calc
    tab's sort key reads " m", so TOTALS and Spares list meters lengths in
    size order. A feet export is the 1.4.1 workbook, untouched.

Run locally (each session takes its own free port):
    python3 -m pytest tests/test_metric_paper.py -v --browser chromium
"""

import io
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))

import pull_sheet  # noqa: E402

openpyxl = pytest.importorskip('openpyxl', reason='openpyxl not installed')


def _rows(*lengths):
    return [{'type': 'Tru-1', 'length': ln, 'qty': 1, 'label': '', 'notes': ''} for ln in lengths]


def _book(pull_list, **meta):
    xlsx, warnings = pull_sheet.build_workbook(pull_list, meta)
    return openpyxl.load_workbook(io.BytesIO(xlsx)), warnings


def _gear_lengths(wb):
    ws = wb[pull_sheet.GEAR]
    return [ws.cell(r, pull_sheet.GEAR_LENGTH_COL).value
            for r in range(pull_sheet.GEAR_FIRST_ROW, pull_sheet.GEAR_LENGTH_LAST_ROW + 1)
            if ws.cell(r, pull_sheet.GEAR_LENGTH_COL).value is not None]


# The template's own sheets and the calc tab's length sort key column (D,
# rows 5-364), named here rather than read off pull_sheet so the test reads
# the workbook as Excel does.
README, CALC = 'READ ME', 'calc'
CALC_FIRST_ROW, CALC_LAST_ROW, CALC_SORTKEY_COL = 5, 364, 4


def _template():
    return openpyxl.load_workbook(pull_sheet.TEMPLATE_PATH)


METERS_SHOW = {'positions': [{'name': 'SR', 'rows': _rows('7.5 m', '30 m', '2 m', 'EA')}]}
FEET_SHOW = {'positions': [{'name': 'SR', 'rows': _rows("7.5'", "100'", "12'", 'EA')}]}


# ── the workbook ─────────────────────────────────────────────────────────

METER_DROPDOWN = ['1 m', '2 m', '3 m', '5 m', '10 m', '15 m', '20 m', '25 m', '30 m',
                  '50 m', '75 m', '100 m', '150 m', '200 m', '250 m', '300 m']


def test_a_meters_workbook_offers_meters_lengths_in_its_dropdown():
    """GEAR LIST lengths in a meters show: 1 m to 300 m, EA, then any other
    length the sheet uses - no feet. The Length dropdown still reads the
    GEAR LIST column."""
    wb, warnings = _book(METERS_SHOW, cable_unit='m')
    assert warnings == []
    assert _gear_lengths(wb) == METER_DROPDOWN + ['EA', '7.5 m'], _gear_lengths(wb)
    assert pull_sheet.meter_gear_lengths() == METER_DROPDOWN
    sources = sorted(dv.formula1 for dv in wb[pull_sheet.SHEET].data_validations.dataValidation)
    assert sources == ["'GEAR LIST'!$A$4:$A$200", "'GEAR LIST'!$B$4:$B$60"], sources


def test_the_meters_dropdown_is_not_the_jumper_ladder():
    """The dropdown is its own list: a meters show's long jumpers round to
    the jumper ladder (Preferences jumperStockM), which neither adds to nor
    replaces it. A jumper length off the list arrives as a length the show
    uses, after EA."""
    wb, _ = _book(METERS_SHOW, cable_unit='m', meter_stock=[4, 1.5, 0.5])
    assert _gear_lengths(wb) == METER_DROPDOWN + ['EA', '7.5 m'], _gear_lengths(wb)
    show = {'positions': [{'name': 'SR', 'rows': _rows('4 m', '1.5 m', '400 m')}]}
    wb, _ = _book(show, cable_unit='m')
    assert _gear_lengths(wb) == METER_DROPDOWN + ['EA', '4 m', '1.5 m', '400 m'], _gear_lengths(wb)
    # as app-cable-units.js cableLengthText prints them (toFixed rounds half up)
    assert [pull_sheet.meter_text(n) for n in (2, 2.0, 7.62, 0.3, 7.625, 1.005)] == \
        ['2 m', '2 m', '7.62 m', '0.3 m', '7.63 m', '1 m']


def test_the_meters_dropdown_has_one_source(client):
    """The list lives in pull_sheet.py alone: the gear-list route serves it
    to the in-app editor, whose picker reads it from there - no copy of it
    in the client to drift. The long jumper's ladder stays 1, 2, 3, 5, 10 m."""
    r = client.get('/api/pull-sheet/gear-list')
    assert r.status_code == 200
    assert r.get_json()['meter_lengths'] == METER_DROPDOWN
    js_dir = os.path.join(HERE, '..', 'src', 'static', 'js')
    editor = open(os.path.join(js_dir, 'app-pull-sheet-editor.js'), encoding='utf-8').read()
    assert 'v.meter_lengths' in editor and 'jumperStockLadder' not in editor
    for name in os.listdir(js_dir):
        if name.endswith('.js'):
            text = open(os.path.join(js_dir, name), encoding='utf-8').read()
            assert '150, 200, 250, 300' not in text, name
    cable = open(os.path.join(js_dir, 'app-cable-units.js'), encoding='utf-8').read()
    assert 'JUMPER_STOCK_SHIPPED = { ft: [3, 6, 10, 15, 25], m: [1, 2, 3, 5, 10] };' in cable


def test_a_meters_read_me_gives_meters_examples():
    wb, _ = _book(METERS_SHOW, cable_unit='m')
    texts = [c.value for row in wb[README].iter_rows() for c in row if isinstance(c.value, str)]
    assert any('(1 m, 3 m, 10 m)' in t for t in texts), texts
    assert not [t for t in texts if re.search(r"\d'", t)], [t for t in texts if re.search(r"\d'", t)]


def _metric_key(length):
    """What the meters sort key computes from a length (the formula's
    steps, in Python): lower case, the foot mark and m stripped, trimmed;
    blank 0, a number in centimeters, anything else 99999999 - as eight
    digits."""
    k = length.lower().replace("'", '').replace('m', '').strip()
    if k == '':
        return '00000000'
    try:
        return f'{round(float(k) * 100):08d}'
    except ValueError:
        return '99999999'


def test_a_meters_sort_key_reads_meters_in_size_order():
    """Every calc row's length key in a meters show strips " m" and counts
    centimeters (the template's stripped only the foot mark, so "2 m" sorted
    with EA, and its six digits put 1.5 with 2); the type part and the rest
    of the formula are the template's."""
    wb, _ = _book(METERS_SHOW, cable_unit='m')
    tpl = _template()
    calc, tcalc = wb[CALC], tpl[CALC]
    for r in range(CALC_FIRST_ROW, CALC_LAST_ROW + 1):
        got = calc.cell(r, CALC_SORTKEY_COL).value
        length = f'MID($A{r},FIND("|",$A{r})+1,50)'
        key = f'TRIM(SUBSTITUTE(SUBSTITUTE(LOWER({length}),"\'",""),"m",""))'
        want = f'TEXT(IF({key}="",0,IFERROR(VALUE({key})*100,99999999)),"00000000")'
        assert want in got, (r, got)
        feet = (f'TEXT(IF(SUBSTITUTE({length},"\'","")="",0,'
                f'IFERROR(VALUE(SUBSTITUTE({length},"\'","")),999999)),"000000")')
        assert got == tcalc.cell(r, CALC_SORTKEY_COL).value.replace(feet, want), r
    lengths = ['EA', '10 m', '2 m', '1.5 m', '30 m', '7.5 m', '0.3 m']
    assert sorted(lengths, key=_metric_key) == ['0.3 m', '1.5 m', '2 m', '7.5 m', '10 m', '30 m', 'EA']


def test_a_feet_workbook_keeps_the_template_s_feet():
    """A feet show (and a show that names no unit) writes the template's
    GEAR LIST, READ ME and sort key untouched, only the lengths used
    appended."""
    tpl = _template()
    tpl_lengths = _gear_lengths(tpl)
    tpl_readme = [c.value for row in tpl[README].iter_rows() for c in row]
    tpl_keys = [tpl[CALC].cell(r, CALC_SORTKEY_COL).value
                for r in range(CALC_FIRST_ROW, CALC_LAST_ROW + 1)]
    for meta in ({'cable_unit': 'ft'}, {}):
        wb, _ = _book(FEET_SHOW, **meta)
        assert _gear_lengths(wb) == tpl_lengths + ["7.5'", "12'"], _gear_lengths(wb)
        assert [c.value for row in wb[README].iter_rows() for c in row] == tpl_readme
        assert [wb[CALC].cell(r, CALC_SORTKEY_COL).value
                for r in range(CALC_FIRST_ROW, CALC_LAST_ROW + 1)] == tpl_keys


def test_the_route_writes_the_show_s_unit_and_the_meters_dropdown(client):
    """POST /api/export/pull-sheet reads the show's unit off the server's
    project; the meters dropdown is the same whatever the Preferences'
    jumper ladder says."""
    import app as app_module
    app_module.server_preferences = {'jumperStockM': [0.5, 1.5, 4]}
    body = {'project_name': 'Units', 'pull_list': METERS_SHOW, 'date': '', 'date_iso': ''}
    app_module.current_project['cableUnit'] = 'm'
    resp = client.post('/api/export/pull-sheet', json=body)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    wb = openpyxl.load_workbook(io.BytesIO(resp.data))
    assert _gear_lengths(wb) == METER_DROPDOWN + ['EA', '7.5 m'], _gear_lengths(wb)
    app_module.current_project['cableUnit'] = 'ft'
    resp = client.post('/api/export/pull-sheet', json=dict(body, pull_list=FEET_SHOW))
    wb = openpyxl.load_workbook(io.BytesIO(resp.data))
    assert _gear_lengths(wb) == _gear_lengths(_template()) + ["7.5'", "12'"]


# ── the binder ───────────────────────────────────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project (and the preferences) as found."""


SEED_JS = """async () => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.fiberCables;
    delete proj.pullSheetEdits;
    await j('PUT', '/api/project', proj);
    await j('POST', '/api/layer/add', {name: 'W1', columns: 8, rows: 12,
                                       cabinet_width: 200, cabinet_height: 200,
                                       processorType: 'novastar-armor'});
    let st = await j('POST', '/api/processors', {deviceId: 'novastar-h9', name: 'SR RACK'});
    const pid = st.processors[0].id;
    st = await j('PUT', `/api/processors/${pid}/slots/0`, {deviceId: 'novastar-card-h-4xfiber'});
    const cardId = st.processors[0].slots[0].card.id;
    st = await j('POST', `/api/processors/${pid}/cards/${cardId}/cvts`, {deviceId: 'novastar-cvt10', pair: false});
    const box = st.processors[0].slots[0].card.cvts[0].id;
    await j('POST', '/api/fiber-cables', {kind: 'tac', strands: 8, ft: 100, connector: 'LC duplex',
                                          link: {boxId: box, key: 'p1'}});
    const app = window.app;
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('metric_paper_setup');
    app.selectLayer(app.project.layers[0]);
    await app.refreshProcessors();
    await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
        {layerId: String(app.project.layers[0].id), cardId, firstPort: 1, lastPort: 8});
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    app.renderHardwareDock();
    app.resetHistory('Metric Paper Seed');
    return { pid };
}"""

UNIT_JS = """async (unit) => {
    window.app.project.cableUnit = unit;
    await fetch('/api/project', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({cableUnit: unit})});
}"""

PROCESSOR_SHEET_JS = """() => {
    const app = window.app;
    const opts = { sheet: 'tabloid', palette: 'colour', sides: {power: false, data: true},
                   scope: {kind: 'show'}, cover: false, pull: true, hardware: true, titleBlock: true };
    const plan = app.planBinder(opts);
    const i = plan.findIndex(p => p.title.startsWith('Processor'));
    if (i < 0) return { titles: plan.map(p => p.title), texts: null };
    return { titles: plan.map(p => p.title), texts: app.renderBinderPage(opts, i).texts };
}"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    # the app's own first load lands before the test touches the project
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    pg.wait_for_timeout(2000)
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(500)
    pg.evaluate(SEED_JS)
    pg.wait_for_timeout(800)
    yield pg, errors
    pg.evaluate(UNIT_JS, 'ft')
    context.close()


def test_the_strand_map_heading_keeps_meters_lower_case(page):
    """The processor sheet's strand map heading, drawn in caps: "100 m" in
    a meters show, "100'" in a feet one."""
    pg, errors = page
    pg.evaluate(UNIT_JS, 'm')
    out = pg.evaluate(PROCESSOR_SHEET_JS)
    texts = out['texts']
    assert texts is not None, out['titles']
    maps = [t for t in texts if t.startswith('STRAND MAP')]
    assert maps == ['STRAND MAP · TAC A · TAC 8 · LC DUPLEX · 100 m'], maps
    assert not [t for t in texts if re.search(r'\d M\b', t)], [t for t in texts if re.search(r'\d M\b', t)]

    pg.evaluate(UNIT_JS, 'ft')
    texts = pg.evaluate(PROCESSOR_SHEET_JS)['texts']
    maps = [t for t in texts if t.startswith('STRAND MAP')]
    assert maps == ["STRAND MAP · TAC A · TAC 8 · LC DUPLEX · 100'"], maps
    assert errors == [], errors


def test_the_editor_picker_offers_the_meters_dropdown(page):
    """The in-app editor's Length picker in a meters show offers what the
    workbook's dropdown does: 1 m to 300 m, EA, then the show's own lengths;
    a feet show keeps the template's feet."""
    pg, errors = page
    pg.evaluate(UNIT_JS, 'm')
    got = pg.evaluate("""async () => {
        const app = window.app;
        app._pullSheetVocab = null;
        app._pullSheetVocabLoading = null;
        app._pullSheetLoadVocab();
        await app._pullSheetVocabLoading;
        const list = { positions: [{ rows: [{ type: 'Tru-1', length: '7.5 m' },
                                            { type: 'Tru-1', length: '30 m' }] }] };
        return app.pullSheetVocabulary(list).lengths;
    }""")
    assert got == METER_DROPDOWN + ['EA', '7.5 m'], got
    pg.evaluate(UNIT_JS, 'ft')
    got = pg.evaluate("() => window.app.pullSheetVocabulary({ positions: [] }).lengths")
    assert got == pull_sheet.gear_list()['lengths'], got
    assert errors == [], errors


def test_every_caps_heading_keeps_a_length_s_meters(page):
    """The one caps rule every heading goes through (_bText upper, the
    sheet title, a column head's measure): in a meters show a length - a
    figure, a space, m - keeps its m; every other letter is in caps, and a
    word that only starts with m is a word. A feet show is plain caps."""
    pg, errors = page
    cases = ['Strand map · MTP · MTP 24 · 250 m', 'SR 30 m +5 m', 'Run 7.62 m', 'Port 1 main',
             'Cat6 runs 30.48 m max', 'W1m 2 mm', "Strand map · TAC A · 100'"]
    pg.evaluate(UNIT_JS, 'm')
    got = pg.evaluate("""(cases) => {
        const app = window.app;
        const book = { ctx: document.createElement('canvas').getContext('2d'), log: null, page: null };
        return cases.map(t => app._bText(book, t, 0, 0, { upper: true }));
    }""", cases)
    want = ['STRAND MAP · MTP · MTP 24 · 250 m', 'SR 30 m +5 m', 'RUN 7.62 m', 'PORT 1 MAIN',
            'CAT6 RUNS 30.48 m MAX', 'W1M 2 MM', "STRAND MAP · TAC A · 100'"]
    assert got == want, got
    pg.evaluate(UNIT_JS, 'ft')
    got = pg.evaluate("""(cases) => {
        const book = { ctx: document.createElement('canvas').getContext('2d'), log: null, page: null };
        return cases.map(t => window.app._bText(book, t, 0, 0, { upper: true }));
    }""", cases)
    assert got == [t.upper() for t in cases], got
    assert errors == [], errors
