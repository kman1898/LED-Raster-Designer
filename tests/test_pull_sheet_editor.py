"""The in-app pull-sheet editor and the edits both exports read.

"i like option one that i can import and edit further. or better yet edit
in the app and then export a whole file i can share" (user, 2026-09-06).
So: a modal over the engine's list (app-pull-sheet-editor.js) laid out
like the workbook - positions side by side, Cable Type · Length · Qty ·
Label · Notes, TOTALS at the right - whose edits are stored as deltas in
project.pullSheetEdits and overlaid by buildPullSheet(), the ONE list the
workbook export and the binder's pull pages both read. Engine rows keep
their type and length; qty / label / notes override inline; a row can be
hidden and restored; a free row can be added with pickers fed by the
template's GEAR LIST (a value outside it warns, never blocks); an override
the show no longer answers to is kept, flagged stale, never exported.

Run locally (ONE pytest at a time - the browser-test servers use fixed
ports):
    python3 -m pytest tests/test_pull_sheet_editor.py -v --browser chromium
"""

import base64
import io
import json
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
sys.path.insert(0, HERE)

import pull_sheet  # noqa: E402

openpyxl = pytest.importorskip('openpyxl', reason='openpyxl not installed')

from test_pull_list import SEED_JS, LIST_JS, SCRATCH_FIXTURE, _rows  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# ── served ───────────────────────────────────────────────────────────────

def test_the_menu_item_the_modal_the_button_and_the_gear_list_are_served(client):
    html = client.get('/').get_data(as_text=True)
    assert re.search(r'data-action="pull-sheet"[^>]*data-label="Pull Sheet…"', html)
    assert 'id="pull-sheet-modal"' in html and 'id="pull-sheet-board"' in html
    for el in ('pull-sheet-export-xlsx', 'pull-sheet-export-binder', 'pull-sheet-close',
               'pull-sheet-types', 'pull-sheet-lengths', 'export-pull-sheet-edit-rows'):
        assert f'id="{el}"' in html, el
    # the button sits inside the export dialog's Pull Sheet section, raised
    sec = html[html.index('id="export-pull-sheet-section"'):html.index('id="export-binder-section"')]
    assert 'id="export-pull-sheet-edit-rows" class="btn"' in sec
    assert 'tails' not in sec.lower()
    main_js = open(os.path.join(HERE, '..', 'src', 'static', 'js', 'main.js')).read()
    assert "import './app-pull-sheet-editor.js';" in main_js
    # the vocabulary route serves the template's GEAR LIST
    r = client.get('/api/pull-sheet/gear-list')
    assert r.status_code == 200
    v = r.get_json()
    for word in ('Tru-1', 'Multi', 'Ether-con Snake', 'Tru-1 2fer'):
        assert word in v['types'], word
    assert 'EA' in v['lengths'] and "100'" in v['lengths']
    assert v == pull_sheet.gear_list()


# ── the browser ──────────────────────────────────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

SHEET_JS = "() => { window.app._circuitTailCache = null; return JSON.parse(JSON.stringify(window.app.buildPullSheet())); }"
STORE_JS = "() => JSON.parse(JSON.stringify(window.app.project.pullSheetEdits || null))"
HIST_JS = """() => ({steps: window.app.history.length, i: window.app.historyIndex,
                     last: window.app.history[window.app.historyIndex].action})"""

CAPTURE_JS = """() => {
    const app = window.app;
    window.__psBodies = [];
    window.__psCaptured = null;
    if (!window.__psOrigFetch) window.__psOrigFetch = window.fetch;
    window.fetch = (url, opts) => {
        if (String(url).includes('/api/export/pull-sheet') && opts && opts.body) {
            window.__psBodies.push(JSON.parse(opts.body));
        }
        return window.__psOrigFetch(url, opts);
    };
    if (!app.__psOrigSave) app.__psOrigSave = app.saveBlobWithPicker;
    app.saveBlobWithPicker = async (blob, filename, mime) => {
        const bytes = new Uint8Array(await blob.arrayBuffer());
        let bin = '';
        for (let i = 0; i < bytes.length; i += 0x8000) {
            bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
        }
        window.__psCaptured = {filename, mime, size: bytes.length, b64: btoa(bin)};
    };
}"""

RELEASE_JS = """() => {
    const app = window.app;
    if (window.__psOrigFetch) window.fetch = window.__psOrigFetch;
    if (app.__psOrigSave) app.saveBlobWithPicker = app.__psOrigSave;
}"""

RENDER_JS = """([title]) => {
    const app = window.app;
    const opts = { palette: 'colour', sides: {power: true, data: true}, scope: {kind: 'show'},
                   cover: true, pull: true, hardware: true };
    const plan = app.planBinder(opts);
    const idx = plan.findIndex(p => p.title === title);
    if (idx < 0) return { missing: title, plan: plan.map(p => p.title) };
    return { texts: app.renderBinderPage(opts, idx).texts };
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
    # a clean slate: no edits left over from another module's show
    pg.evaluate("""async () => {
        const j = (m, u, b) => fetch(u, {method: m, headers: {'Content-Type': 'application/json'},
            body: b === undefined ? undefined : JSON.stringify(b)}).then(r => r.json());
        const p = await j('GET', '/api/project');
        delete p.pullSheetEdits;
        await j('PUT', '/api/project', p);
    }""")
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(1200)
    assert ids['aCircuits'] == [8, 4] and ids['bCircuits'] == [8, 4], ids
    ids['sr'] = 'g1'
    ids['center'] = f"layer:{ids['c']}"
    yield pg, ids
    context.close()


def _open(pg):
    pg.evaluate("() => { document.getElementById('export-modal').style.display = 'none'; }")
    if not pg.evaluate("() => window.app.isPullSheetEditorOpen()"):
        pg.locator('[data-menu="file"]').click()
        pg.locator('[data-action="pull-sheet"]').click()
    pg.wait_for_timeout(500)
    assert pg.locator('#pull-sheet-modal').is_visible()


def _close(pg):
    if pg.evaluate("() => window.app.isPullSheetEditorOpen()"):
        pg.locator('#pull-sheet-close').click()
        pg.wait_for_timeout(200)


def _pos(pg, key):
    return pg.locator(f'.pull-pos[data-pos="{key}"]')


def _cell(pg, pos_key, row_key, field):
    return _pos(pg, pos_key).locator(f'tr.pull-row[data-key="{row_key}"] input[data-field="{field}"]')


def _set(pg, locator, value):
    locator.fill(value)
    locator.dispatch_event('change')
    pg.wait_for_timeout(350)


def _rows_of(sheet, name):
    return _rows(next(p for p in sheet['positions'] if p['name'] == name)['rows'])


def _totals(sheet):
    return {(t, l): (q, lab, n) for t, l, q, lab, n in _rows(sheet['totals'])}


def _export_xlsx(pg):
    pg.evaluate(CAPTURE_JS)
    pg.locator('#pull-sheet-export-xlsx').click()
    waited = 0
    while waited < 8000 and not pg.evaluate("() => !!window.__psCaptured"):
        pg.wait_for_timeout(250)
        waited += 250
    cap = pg.evaluate("() => window.__psCaptured")
    bodies = pg.evaluate("() => window.__psBodies")
    pg.evaluate(RELEASE_JS)
    assert cap, 'the export never reached saveBlobWithPicker'
    assert cap['mime'] == pull_sheet.XLSX_MIME
    wb = openpyxl.load_workbook(io.BytesIO(base64.b64decode(cap['b64'])))
    return wb, bodies[-1]


def _block(ws, block):
    col0 = pull_sheet.BLOCK_COLS[block]
    out = []
    for r in range(pull_sheet.FIRST_DATA_ROW, pull_sheet.MAX_DATA_ROW + 1):
        if ws.cell(r, col0).value is None:
            break
        out.append(tuple(ws.cell(r, col0 + k).value for k in range(5)))
    return out


def _render(pg, title):
    out = pg.evaluate("(t) => (%s)([t])" % RENDER_JS, title)
    assert 'missing' not in out, out
    return out['texts']


def _triples(texts):
    """(type, length, qty) as the pull table draws its cells in order."""
    out = []
    for i in range(len(texts) - 2):
        out.append((texts[i], texts[i + 1], texts[i + 2]))
    return out


# ── opening ──────────────────────────────────────────────────────────────

def test_the_file_menu_opens_the_editor_laid_out_like_the_workbook(page):
    pg, ids = page
    _open(pg)
    names = pg.locator('.pull-pos .pull-pos-name').all_inner_texts()
    assert names == ['SR Beach', 'CENTER', 'TOTALS']
    assert _pos(pg, ids['sr']).locator('.pull-pos-screens').inner_text() == 'WALL-A, WALL-B'
    # a loose screen is its own position; its name is not said twice
    assert _pos(pg, ids['center']).locator('.pull-pos-screens').inner_text() == ''
    heads = _pos(pg, ids['sr']).locator('thead th').evaluate_all("els => els.map(e => e.textContent)")
    assert heads == ['Cable Type', 'Length', 'Qty', 'Label', 'Notes', '']
    engine = pg.evaluate(LIST_JS)
    keys = _pos(pg, ids['sr']).locator('tr.pull-row').evaluate_all("els => els.map(e => e.dataset.key)")
    assert keys == [f"{r['type']}|{r['length']}" for r in engine['positions'][0]['rows']]
    # type and length are readouts, the three others fields
    first = _pos(pg, ids['sr']).locator('tr.pull-row').first
    assert first.locator('td.pull-ro').count() == 2 and first.locator('input').count() == 3
    assert [f for f in first.locator('input').evaluate_all("els => els.map(e => e.dataset.field)")] == ['qty', 'label', 'notes']
    assert _cell(pg, ids['sr'], "Tru-1|10'", 'qty').input_value() == '2'
    assert _cell(pg, ids['sr'], "Tru-1|10'", 'label').input_value() == 'SR1-1, SR1-2'
    # TOTALS is a readout block with the engine's totals
    tot = pg.locator('#pull-sheet-totals tr').evaluate_all(
        "els => els.slice(1).map(tr => [...tr.children].map(td => td.textContent))")
    assert tot[0] == ['Data Jump', "6'", '8', 'WALL-A, WALL-B, CENTER']
    assert pg.locator('#pull-sheet-totals input').count() == 0
    assert 'tails' not in pg.locator('#pull-sheet-modal').inner_text().lower()
    # the pickers carry the GEAR LIST plus the show's own words
    opts = pg.locator('#pull-sheet-types option').evaluate_all("els => els.map(e => e.value)")
    assert 'Tru-1' in opts and 'Multi' in opts and 'Edison 2fer' in opts and 'Data Jump' in opts
    lens = pg.locator('#pull-sheet-lengths option').evaluate_all("els => els.map(e => e.value)")
    assert 'EA' in lens and "100'" in lens and "125'" in lens
    _close(pg)
    assert not pg.locator('#pull-sheet-modal').is_visible()


def test_the_export_dialogs_button_opens_it_and_close_returns_there(page):
    pg, ids = page
    pg.evaluate("() => window.app.openExportModal('pull-sheet')")
    pg.wait_for_timeout(200)
    assert pg.locator('#export-pull-sheet-edit-rows').is_visible()
    pg.locator('#export-pull-sheet-edit-rows').click()
    pg.wait_for_timeout(500)
    assert pg.locator('#pull-sheet-modal').is_visible()
    assert not pg.locator('#export-modal').is_visible()
    pg.locator('#pull-sheet-close').click()
    pg.wait_for_timeout(300)
    assert not pg.locator('#pull-sheet-modal').is_visible()
    assert pg.locator('#export-modal').is_visible()
    assert pg.locator('#export-format').input_value() == 'pull-sheet'
    pg.locator('#export-cancel').click()
    pg.wait_for_timeout(200)


# ── overrides ────────────────────────────────────────────────────────────

def test_a_qty_override_rides_into_the_wrapper_the_workbook_and_the_binder(page):
    pg, ids = page
    _open(pg)
    before = pg.evaluate(HIST_JS)
    _set(pg, _cell(pg, ids['sr'], "Tru-1|10'", 'qty'), '7')
    assert pg.evaluate(STORE_JS) == {'positions': {'g1': {'rows': [{'key': "Tru-1|10'", 'qty': 7}], 'added': []}}}
    cell = _cell(pg, ids['sr'], "Tru-1|10'", 'qty')
    assert 'pull-edited' in cell.locator('xpath=..').get_attribute('class')
    assert 'pull-row-edited' in cell.locator('xpath=../..').get_attribute('class')
    assert cell.get_attribute('title') == 'The show says 2'
    after = pg.evaluate(HIST_JS)
    assert after['steps'] == before['steps'] + 1 and after['last'] == 'Edit Pull Sheet Row'
    # the wrapper: the position row and the total move; the engine does not
    sheet = pg.evaluate(SHEET_JS)
    assert ('Tru-1', "10'", 7, 'SR1-1, SR1-2', '') in _rows_of(sheet, 'SR Beach')
    assert _totals(sheet)[('Tru-1', "10'")] == (7, 'SR1-1, SR1-2', '')
    engine = pg.evaluate(LIST_JS)
    assert ('Tru-1', "10'", 2, 'SR1-1, SR1-2', '') in _rows(engine['positions'][0]['rows'])
    # an untouched total is the engine's own, folded labels and all
    assert _totals(sheet)[('Tru-1 Breakout', 'EA')] == (2, 'SR 1-2', '')
    assert _totals(sheet)[('Data Jump', "6'")] == (8, 'WALL-A, WALL-B, CENTER', '')
    # the TOTALS block redrew without rebuilding the edited row
    tot = pg.locator('#pull-sheet-totals tr').evaluate_all(
        "els => els.slice(1).map(tr => [...tr.children].map(td => td.textContent))")
    assert ['Tru-1', "10'", '7', 'SR1-1, SR1-2'] in tot
    # the workbook export from the footer posts the edited list
    wb, body = _export_xlsx(pg)
    sr = next(p for p in body['pull_list']['positions'] if p['name'] == 'SR Beach')
    assert {(r['type'], r['length']): r['qty'] for r in sr['rows']}[('Tru-1', "10'")] == 7
    ws = wb['Pull Sheet']
    assert ws.cell(5, 1).value == 'SR Beach'
    assert ('Tru-1', "10'", 7, 'SR1-1, SR1-2', None) in _block(ws, 0)
    assert pg.locator('#pull-sheet-modal').is_visible(), 'the editor stays up after an export'
    # the binder's pull page and its totals page draw the same figure
    texts = _render(pg, 'SR Beach - Pull')
    assert ('Tru-1', "10'", '7') in _triples(texts) and ('Tru-1', "10'", '2') not in _triples(texts)
    totals = _render(pg, 'Pull list - all positions')
    assert ('Tru-1', "10'", '7') in _triples(totals)
    _close(pg)


def test_label_and_notes_overrides_wear_a_dot_and_reset_takes_the_row_back(page):
    pg, ids = page
    _open(pg)
    _set(pg, _cell(pg, ids['sr'], "Multi|125'", 'label'), 'SR 1 (stage left)')
    _set(pg, _cell(pg, ids['sr'], "Multi|125'", 'notes'), 'ramp run')
    store = pg.evaluate(STORE_JS)
    assert {'key': "Multi|125'", 'label': 'SR 1 (stage left)', 'notes': 'ramp run'} in store['positions']['g1']['rows']
    row = _pos(pg, ids['sr']).locator('tr.pull-row[data-key="Multi|125\'"]')
    assert row.locator('td.pull-edited').count() == 2
    assert row.locator('td.pull-edited .pull-dot').evaluate_all(
        "els => els.map(e => getComputedStyle(e).display)") == ['block', 'block']
    assert row.locator('.pull-reset').is_visible()
    sheet = pg.evaluate(SHEET_JS)
    assert ('Multi', "125'", 1, 'SR 1 (stage left)', 'ramp run') in _rows_of(sheet, 'SR Beach')
    assert _totals(sheet)[('Multi', "125'")] == (1, 'SR 1 (stage left)', 'ramp run')
    # typing the show's own value back clears that one override
    _set(pg, _cell(pg, ids['sr'], "Multi|125'", 'notes'), '')
    store = pg.evaluate(STORE_JS)
    assert {'key': "Multi|125'", 'label': 'SR 1 (stage left)'} in store['positions']['g1']['rows']
    assert row.locator('td.pull-edited').count() == 1
    # reset: the show's reading returns, one entry
    before = pg.evaluate(HIST_JS)
    row.locator('.pull-reset').click()
    pg.wait_for_timeout(400)
    after = pg.evaluate(HIST_JS)
    assert after['steps'] == before['steps'] + 1 and after['last'] == 'Reset Pull Sheet Row'
    store = pg.evaluate(STORE_JS)
    assert not any(r['key'] == "Multi|125'" for r in store['positions']['g1']['rows'])
    row = _pos(pg, ids['sr']).locator('tr.pull-row[data-key="Multi|125\'"]')
    assert row.locator('td.pull-edited').count() == 0
    assert not row.locator('.pull-reset').is_visible()
    assert ('Multi', "125'", 1, 'SR 1', '') in _rows_of(pg.evaluate(SHEET_JS), 'SR Beach')
    # a non-number qty is refused, not stored
    _set(pg, _cell(pg, ids['sr'], "Multi|125'", 'qty'), 'lots')
    assert not any(r['key'] == "Multi|125'" for r in pg.evaluate(STORE_JS)['positions']['g1']['rows'])
    assert _cell(pg, ids['sr'], "Multi|125'", 'qty').input_value() == '1'
    _close(pg)


def test_a_hidden_row_leaves_every_paper_and_comes_back_from_the_fold(page):
    pg, ids = page
    _open(pg)
    before = pg.evaluate(HIST_JS)
    row = _pos(pg, ids['sr']).locator('tr.pull-row[data-key="Tru-1 Breakout|EA"]')
    row.locator('.pull-hide').click()
    pg.wait_for_timeout(400)
    after = pg.evaluate(HIST_JS)
    assert after['steps'] == before['steps'] + 1 and after['last'] == 'Remove Pull Sheet Row'
    assert _pos(pg, ids['sr']).locator('tr.pull-row[data-key="Tru-1 Breakout|EA"]').count() == 0
    fold = _pos(pg, ids['sr']).locator('details.pull-hidden')
    assert fold.locator('summary').inner_text() == 'Hidden rows (1)'
    assert 'Tru-1 Breakout · EA · 2' in fold.evaluate("el => el.textContent")
    store = pg.evaluate(STORE_JS)
    assert {'key': 'Tru-1 Breakout|EA', 'removed': True} in store['positions']['g1']['rows']
    sheet = pg.evaluate(SHEET_JS)
    assert not any(t == 'Tru-1 Breakout' for t, *_ in _rows_of(sheet, 'SR Beach'))
    assert ('Tru-1 Breakout', 'EA') not in _totals(sheet), 'no other position has one'
    texts = _render(pg, 'SR Beach - Pull')
    assert 'Tru-1 Breakout' not in texts
    # restore
    fold.locator('summary').click()
    fold.locator('.pull-restore').click()
    pg.wait_for_timeout(400)
    assert pg.evaluate(HIST_JS)['last'] == 'Restore Pull Sheet Row'
    assert _pos(pg, ids['sr']).locator('tr.pull-row[data-key="Tru-1 Breakout|EA"]').count() == 1
    assert _pos(pg, ids['sr']).locator('details.pull-hidden').count() == 0
    assert pg.evaluate(STORE_JS) is None or 'g1' not in pg.evaluate(STORE_JS)['positions'] \
        or not any(r['key'] == 'Tru-1 Breakout|EA' for r in pg.evaluate(STORE_JS)['positions']['g1']['rows'])
    assert _totals(pg.evaluate(SHEET_JS))[('Tru-1 Breakout', 'EA')] == (2, 'SR 1-2', '')
    _close(pg)


def test_an_added_row_with_a_new_type_lands_in_the_export_and_the_gear_list(page):
    pg, ids = page
    _open(pg)
    before = pg.evaluate(HIST_JS)
    _pos(pg, ids['center']).locator('.pull-add').click()
    pg.wait_for_timeout(400)
    after = pg.evaluate(HIST_JS)
    assert after['steps'] == before['steps'] + 1 and after['last'] == 'Add Pull Sheet Row'
    added = _pos(pg, ids['center']).locator('tr.pull-added')
    assert added.count() == 1
    assert pg.evaluate("() => document.activeElement && document.activeElement.dataset.field") == 'type'
    assert added.locator('input[data-field="type"]').get_attribute('list') == 'pull-sheet-types'
    assert added.locator('input[data-field="length"]').get_attribute('list') == 'pull-sheet-lengths'
    _set(pg, added.locator('input[data-field="type"]'), 'Widget Cable')
    _set(pg, added.locator('input[data-field="length"]'), "12'")
    _set(pg, added.locator('input[data-field="qty"]'), '3')
    _set(pg, added.locator('input[data-field="label"]'), 'X')
    _set(pg, added.locator('input[data-field="notes"]'), 'new')
    # a word outside the GEAR LIST warns and is kept; a length it knows is quiet
    assert 'pull-warn' in added.locator('input[data-field="type"]').locator('xpath=..').get_attribute('class')
    assert 'pull-warn' in added.locator('input[data-field="length"]').locator('xpath=..').get_attribute('class')
    _set(pg, added.locator('input[data-field="length"]'), "10'")
    assert 'pull-warn' not in (added.locator('input[data-field="length"]').locator('xpath=..').get_attribute('class') or '')
    _set(pg, added.locator('input[data-field="length"]'), "12'")
    store = pg.evaluate(STORE_JS)
    assert store['positions'][ids['center']]['added'] == [
        {'type': 'Widget Cable', 'length': "12'", 'qty': 3, 'label': 'X', 'notes': 'new'}]
    sheet = pg.evaluate(SHEET_JS)
    center = next(p for p in sheet['positions'] if p['name'] == 'CENTER')
    widget = next(r for r in center['rows'] if r['type'] == 'Widget Cable')
    assert (widget['length'], widget['qty'], widget['label'], widget['notes'], widget['side']) == ("12'", 3, 'X', 'new', 'power')
    assert _totals(sheet)[('Widget Cable', "12'")] == (3, 'X', 'new')
    # sorted into place, EA last
    assert [t for t, *_ in _rows(center['rows'])] == ['Data Jump', 'Edison 2fer', 'Ether-con', 'Tru-1 Power Jump', 'Widget Cable']
    assert _rows(sheet['totals'])[-1][0] == 'Widget Cable' or _rows(sheet['totals'])[-1][1] == 'EA'
    # the export: the row in the CENTER block, the type in the GEAR LIST
    wb, body = _export_xlsx(pg)
    ws = wb['Pull Sheet']
    assert ws.cell(5, 7).value == 'CENTER'
    assert ('Widget Cable', "12'", 3, 'X', 'new') in _block(ws, 1)
    gear = [wb['GEAR LIST'].cell(r, 1).value for r in range(4, 200) if wb['GEAR LIST'].cell(r, 1).value]
    assert 'Widget Cable' in gear
    lengths = [wb['GEAR LIST'].cell(r, 2).value for r in range(4, 61) if wb['GEAR LIST'].cell(r, 2).value]
    assert "12'" in lengths
    # the binder's pull page has it on the power side
    texts = _render(pg, 'CENTER - Pull')
    assert ('Widget Cable', "12'", '3') in _triples(texts)
    # a data word goes to the data side
    idx = pg.evaluate("(k) => window.app.addPullSheetRow(k, {type: 'Ether-con Barrel', length: 'EA', qty: 2})", ids['center'])
    assert idx == 1
    sheet = pg.evaluate(SHEET_JS)
    barrel = next(r for p in sheet['positions'] for r in p['rows'] if r['type'] == 'Ether-con Barrel')
    assert barrel['side'] == 'data'
    pg.evaluate("() => window.app.renderPullSheetEditor()")
    pg.wait_for_timeout(200)
    # removing an added row deletes it outright (no fold - it has no show reading)
    rows = _pos(pg, ids['center']).locator('tr.pull-added')
    assert rows.count() == 2
    rows.nth(1).locator('.pull-hide').click()
    pg.wait_for_timeout(300)
    assert pg.evaluate(HIST_JS)['last'] == 'Remove Pull Sheet Row'
    assert _pos(pg, ids['center']).locator('tr.pull-added').count() == 1
    assert _pos(pg, ids['center']).locator('details.pull-hidden').count() == 0
    _pos(pg, ids['center']).locator('tr.pull-added .pull-hide').click()
    pg.wait_for_timeout(300)
    assert pg.evaluate(STORE_JS) is None or ids['center'] not in pg.evaluate(STORE_JS)['positions']
    _close(pg)


def test_a_stale_override_is_kept_flagged_and_never_exported(page):
    pg, ids = page
    _open(pg)
    # WALL-B circuit 1 is the only 6' cable on SR Beach
    _set(pg, _cell(pg, ids['sr'], "Tru-1|6'", 'qty'), '5')
    assert _totals(pg.evaluate(SHEET_JS))[('Tru-1', "6'")][0] == 5
    # the show changes: that cable becomes 25'
    pg.evaluate("""(ids) => {
        const app = window.app;
        const b = app.project.layers.find(l => l.id === ids.b);
        app.setCircuitCable(b, 1, {ft: 25, connector: null});
        app.renderPullSheetEditor();
    }""", ids)
    pg.wait_for_timeout(500)
    sheet = pg.evaluate(SHEET_JS)
    sr = _rows_of(sheet, 'SR Beach')
    assert not any(t == 'Tru-1' and l == "6'" for t, l, *_ in sr)
    assert ('Tru-1', "25'", 1, 'SR2-1', '') in sr
    assert ('Tru-1', "6'") not in _totals(sheet) and _totals(sheet)[('Tru-1', "25'")][0] == 1
    # kept in the store, flagged on its position, out of the rows
    store = pg.evaluate(STORE_JS)
    assert {'key': "Tru-1|6'", 'qty': 5} in store['positions']['g1']['rows']
    stale = _pos(pg, ids['sr']).locator('.pull-stale')
    assert stale.count() == 1
    assert stale.inner_text().startswith('STALE')
    assert "Tru-1 6' · qty \"5\"" in stale.inner_text()
    assert _pos(pg, ids['sr']).locator('tr.pull-row[data-key="Tru-1|6\'"]').count() == 0
    assert pg.evaluate("() => window.app.pullSheetStaleEdits().map(s => [s.positionKey, s.key])") == [['g1', "Tru-1|6'"]]
    wb, body = _export_xlsx(pg)
    sr_rows = next(p for p in body['pull_list']['positions'] if p['name'] == 'SR Beach')['rows']
    assert not any(r['type'] == 'Tru-1' and r['length'] == "6'" for r in sr_rows)
    assert not any(t == 'Tru-1' and l == "6'" for t, l, *_ in _block(wb['Pull Sheet'], 0))
    # the show comes back: the override applies again
    pg.evaluate("""(ids) => {
        const app = window.app;
        const b = app.project.layers.find(l => l.id === ids.b);
        app.setCircuitCable(b, 1, {ft: 6, connector: null});
        app.renderPullSheetEditor();
    }""", ids)
    pg.wait_for_timeout(500)
    assert _pos(pg, ids['sr']).locator('.pull-stale').count() == 0
    assert _cell(pg, ids['sr'], "Tru-1|6'", 'qty').input_value() == '5'
    assert _totals(pg.evaluate(SHEET_JS))[('Tru-1', "6'")][0] == 5
    # forget it from the stale list when it is stale again
    pg.evaluate("""(ids) => {
        const app = window.app;
        const b = app.project.layers.find(l => l.id === ids.b);
        app.setCircuitCable(b, 1, {ft: 25, connector: null});
        app.renderPullSheetEditor();
    }""", ids)
    pg.wait_for_timeout(400)
    _pos(pg, ids['sr']).locator('.pull-stale .pull-forget').click()
    pg.wait_for_timeout(300)
    assert pg.evaluate(HIST_JS)['last'] == 'Reset Pull Sheet Row'
    store = pg.evaluate(STORE_JS)
    assert store is None or not any(r['key'] == "Tru-1|6'" for r in store['positions'].get('g1', {'rows': []})['rows'])
    pg.evaluate("""(ids) => {
        const app = window.app;
        const b = app.project.layers.find(l => l.id === ids.b);
        app.setCircuitCable(b, 1, {ft: 6, connector: null});
    }""", ids)
    pg.wait_for_timeout(300)
    _close(pg)


# ── history, persistence, keyboard ───────────────────────────────────────

def test_undo_and_redo_step_one_edit_at_a_time(page):
    pg, ids = page
    _open(pg)
    # a clean store and a fresh history, so the first undo below lands on it
    pg.evaluate("""() => { const app = window.app;
        if (app.project.pullSheetEdits) { delete app.project.pullSheetEdits; app._persistPullSheetEdits(); }
        app.resetHistory('Pull Sheet Editor Undo Seed'); }""")
    pg.evaluate("() => window.app.renderPullSheetEditor()")
    pg.wait_for_timeout(300)
    before = pg.evaluate(HIST_JS)
    _set(pg, _cell(pg, ids['sr'], "Multi|100'", 'qty'), '3')
    _set(pg, _cell(pg, ids['sr'], "Multi|100'", 'label'), 'SR 2 long')
    after = pg.evaluate(HIST_JS)
    assert after['steps'] == before['steps'] + 2
    actions = pg.evaluate("() => window.app.history.slice(-2).map(h => h.action)")
    assert actions == ['Edit Pull Sheet Row', 'Edit Pull Sheet Row']
    # blurring an untouched cell grows no step
    _set(pg, _cell(pg, ids['sr'], "Multi|100'", 'notes'), '')
    assert pg.evaluate(HIST_JS)['steps'] == after['steps']
    # Ctrl+Z from the board takes the label back and redraws the board
    _cell(pg, ids['sr'], "Multi|100'", 'qty').focus()
    pg.keyboard.press('Escape')
    pg.evaluate("() => document.activeElement && document.activeElement.blur()")
    pg.keyboard.press('Control+z')
    pg.wait_for_timeout(700)
    store = pg.evaluate(STORE_JS)
    assert store['positions']['g1']['rows'] == [{'key': "Multi|100'", 'qty': 3}]
    assert _cell(pg, ids['sr'], "Multi|100'", 'label').input_value() == 'SR 2'
    assert _cell(pg, ids['sr'], "Multi|100'", 'qty').input_value() == '3'
    pg.evaluate("() => window.app.undo()")
    pg.wait_for_timeout(600)
    assert pg.evaluate(STORE_JS) is None
    pg.evaluate("() => window.app.redo()")
    pg.wait_for_timeout(600)
    assert pg.evaluate(STORE_JS)['positions']['g1']['rows'] == [{'key': "Multi|100'", 'qty': 3}]
    pg.evaluate("() => window.app.renderPullSheetEditor()")
    pg.wait_for_timeout(200)
    assert _cell(pg, ids['sr'], "Multi|100'", 'qty').input_value() == '3'
    _close(pg)


def test_the_edits_persist_through_the_project_api(page):
    pg, ids = page
    # the POST every commit makes merged the store server-side
    served = pg.evaluate("async () => (await (await fetch('/api/project')).json()).pullSheetEdits")
    assert served == {'positions': {'g1': {'rows': [{'key': "Multi|100'", 'qty': 3}], 'added': []}}}
    # a whole-project PUT (file load, undo) carries it, and GET hands it back
    out = pg.evaluate("""async () => {
        const j = (m, u, b) => fetch(u, {method: m, headers: {'Content-Type': 'application/json'},
            body: b === undefined ? undefined : JSON.stringify(b)}).then(r => r.json());
        const p = await j('GET', '/api/project');
        p.pullSheetEdits = {positions: {g1: {rows: [{key: "Multi|100'", qty: 4, notes: 'via PUT'}], added: []}}};
        await j('PUT', '/api/project', p);
        const back = await j('GET', '/api/project');
        window.app.project.pullSheetEdits = back.pullSheetEdits;
        window.app._circuitTailCache = null;
        return {served: back.pullSheetEdits, sheet: JSON.parse(JSON.stringify(window.app.buildPullSheet()))};
    }""")
    assert out['served'] == {'positions': {'g1': {'rows': [{'key': "Multi|100'", 'qty': 4, 'notes': 'via PUT'}], 'added': []}}}
    assert ('Multi', "100'", 4, 'SR 2', 'via PUT') in _rows_of(out['sheet'], 'SR Beach')
    # clearing the last override deletes the key client-side and empties it server-side
    pg.evaluate("""() => window.app.resetPullSheetRow('g1', "Multi|100'")""")
    pg.wait_for_timeout(500)
    assert pg.evaluate(STORE_JS) is None
    served = pg.evaluate("async () => (await (await fetch('/api/project')).json()).pullSheetEdits")
    assert served == {'positions': {}}


def test_tab_walks_qty_label_notes_then_the_next_row(page):
    pg, ids = page
    _open(pg)
    rows = _pos(pg, ids['sr']).locator('tr.pull-row')
    first_key = rows.nth(0).get_attribute('data-key')
    second_key = rows.nth(1).get_attribute('data-key')
    _cell(pg, ids['sr'], first_key, 'qty').focus()
    where = "() => { const a = document.activeElement; return [a.dataset.field, a.closest('tr').dataset.key]; }"
    assert pg.evaluate(where) == ['qty', first_key]
    pg.keyboard.press('Tab')
    assert pg.evaluate(where) == ['label', first_key]
    pg.keyboard.press('Tab')
    assert pg.evaluate(where) == ['notes', first_key]
    pg.keyboard.press('Tab')
    assert pg.evaluate(where) == ['qty', second_key]
    # a commit on the way does not kill the field Tab moves into
    pg.keyboard.type('9')
    pg.keyboard.press('Tab')
    pg.wait_for_timeout(400)
    assert pg.evaluate(where) == ['label', second_key]
    assert _cell(pg, ids['sr'], second_key, 'qty').input_value() == '9'
    pg.evaluate("""(a) => window.app.resetPullSheetRow(a[0], a[1])""", [ids['sr'], second_key])
    pg.wait_for_timeout(300)
    _close(pg)


# ── the smoke: the user's own show ───────────────────────────────────────

SCREENSHOT = os.path.join(os.path.dirname(SCRATCH_FIXTURE), 'pull-sheet-editor-experts-only.png')


@pytest.mark.skipif(not os.path.exists(SCRATCH_FIXTURE),
                    reason='experts-only.json smoke fixture not present')
def test_smoke_experts_only(page):
    """The real show: SR - MAIN's Tru-1 10' row (6 as the show says) edited
    to 7 in the editor; the workbook's cell reads 7."""
    pg, ids = page
    with open(SCRATCH_FIXTURE) as fh:
        project = json.load(fh)
    project.pop('pullSheetEdits', None)
    main_id = pg.evaluate("""async (project) => {
        const app = window.app;
        const j = (method, url, body) => fetch(url, {method,
            headers: {'Content-Type': 'application/json'},
            body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
        await j('PUT', '/api/project', project);
        app.project = await j('GET', '/api/project');
        app.dedupeProjectLayers('pull_editor_smoke');
        app.selectLayer(app.project.layers.find(l => (l.type || 'screen') === 'screen'));
        await app.refreshProcessors();
        await app.refreshPortAssignment();
        app.renderLayers();
        app._circuitTailCache = null;
        return app.project.layers.find(l => l.name === 'SR - MAIN').id;
    }""", project)
    pg.wait_for_timeout(500)
    _open(pg)
    names = pg.locator('.pull-pos .pull-pos-name').all_inner_texts()
    assert names == ['SR - MAIN', 'SR - Return', 'SL - MAIN', 'SL - Return', 'TOTALS']
    key = f'layer:{main_id}'
    assert _cell(pg, key, "Tru-1|10'", 'qty').input_value() == '6'
    _set(pg, _cell(pg, key, "Tru-1|10'", 'qty'), '7')
    pg.screenshot(path=SCREENSHOT, full_page=False)
    sheet = pg.evaluate(SHEET_JS)
    assert ('Tru-1', "10'", 7, 'SR1-1, SR1-6, SR2-2, SR3-1, SR3-6, SR4-1', '') in _rows_of(sheet, 'SR - MAIN')
    assert _totals(sheet)[('Tru-1', "10'")][0] == 9        # 7 + SR - Return's 2
    wb, body = _export_xlsx(pg)
    ws = wb['Pull Sheet']
    assert ws.cell(5, 1).value == 'SR - MAIN'
    block = _block(ws, 0)
    row = next(r for r in block if r[0] == 'Tru-1' and r[1] == "10'")
    assert row[2] == 7
    _close(pg)
    assert os.path.exists(SCREENSHOT)
