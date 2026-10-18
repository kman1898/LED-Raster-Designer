"""Brompton hardware goes by its plain model name: SX40, XD, S8, never
"Tessera SX40".

The owner (2026-10-17): "we dont need to call it tessera XD. tessera is not
needed" - and, asked which names, "All of them". The catalog is the one
place a model's name is written (processor_catalog.json `name`); every
paper reads it from there - the dock, the pickers, the binder, the pull
sheet and its workbook, the refusals. The stable ids ('brompton-sx40',
'brompton-xd', ...) are what a saved show stores, so they stay; a show
saved before the rename stores no model name at all (an unnamed unit's
`name` is ''), so it opens reading the new names without a byte of it
rewritten. The one place an old show holds the old spelling is a pull
sheet edit, keyed on the type its row printed ("Tessera XD|EA"): that
edit still lands on the row ("XD|EA").

"Brompton" stays where it is the maker: the picker's vendor heading and
the Processing dropdown's "Brompton".

Run locally:
    python3 -m pytest tests/test_brompton_names.py -v --browser chromium
"""

import copy
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import port_assignment  # noqa: E402
import processor_catalog as catalog  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')

# Every Brompton device, by the id a saved show stores, and the name it
# shows. The ids are the files' keys and never change.
BROMPTON_NAMES = {
    'brompton-sx40': 'SX40',
    'brompton-s8': 'S8',
    'brompton-s4': 'S4',
    'brompton-m2': 'M2',
    'brompton-t1': 'T1',
    'brompton-sq200': 'SQ200',
    'brompton-card-qd-s': 'QD-S',
    'brompton-xd': 'XD',
    'brompton-xd-s': 'XD-S',
    'brompton-xd-t': 'XD-T',
    'brompton-qd-s': 'QD-S',
}


def _shown_catalog_strings(device):
    """The catalog strings a page can print for one device: its name, its
    short name and unit word, and what its canvas refusal calls it."""
    out = [device.get('name'), device.get('vendor'), device.get('shortName'),
           device.get('unitWord'), (device.get('canvas') or {}).get('says')]
    return [s for s in out if isinstance(s, str)]


def _names_in(node):
    """Every name and title a resolved processor view carries."""
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, str) and (key in ('name', 'title', 'unitTitle')
                                           or key.endswith(('Name', 'Title'))):
                yield value
            else:
                yield from _names_in(value)
    elif isinstance(node, list):
        for value in node:
            yield from _names_in(value)


# ── the catalog: the one source ─────────────────────────────────────────

def test_every_brompton_device_keeps_its_id_and_shows_its_plain_model():
    brompton = {d['id']: d for d in catalog.devices() if d.get('vendor') == 'Brompton'}
    assert {i: d['name'] for i, d in brompton.items()} == BROMPTON_NAMES
    assert all(d.get('family') == 'brompton' for d in brompton.values())


def test_no_catalog_string_a_page_can_show_says_tessera():
    for device in catalog.devices():
        for text in _shown_catalog_strings(device):
            assert 'tessera' not in text.lower(), (device['id'], text)


def test_the_processing_setting_says_brompton_the_maker():
    assert port_assignment.PLATFORM_LABELS['brompton'] == 'Brompton'
    with open(os.path.join(ROOT, 'src', 'templates', 'index.html'), encoding='utf-8') as fh:
        html = fh.read()
    options = re.findall(r'<option value="brompton">([^<]*)</option>', html)
    assert options == ['Brompton', 'Brompton'], options
    assert 'Tessera' not in html


# ── an old show: the names resolve, nothing is written ──────────────────

def test_an_old_sx40_show_reads_the_new_names_and_stores_none(client):
    proc = catalog.new_processor('brompton-sx40', 1)
    stored = copy.deepcopy(proc)
    project = client.get('/api/project').get_json()
    project['processors'] = [proc]
    project['next_processor_seq'] = 2
    assert client.put('/api/project', json=project).status_code == 200
    state = client.get('/api/processors').get_json()
    res = state['resolved'][0]
    card = res['slots'][0]['card']
    assert res['deviceName'] == 'SX40'
    assert card['deviceName'] == 'SX40'
    assert [b['deviceName'] for b in card['cvts']] == ['XD'] * 4
    assert [b['displayTitle'] for b in card['cvts']] == ['XD A', 'XD B', 'XD C', 'XD D']
    names = list(_names_in(state['resolved']))
    assert names and not [n for n in names if 'Tessera' in n], names
    # what the show keeps is ids and empty names - nothing to rewrite
    raw = client.get('/api/project').get_json()['processors'][0]
    assert raw == stored, 'opening the show rewrote its processor'
    assert raw['deviceId'] == 'brompton-sx40'
    assert raw['name'] == ''
    assert [b['deviceId'] for b in raw['slots'][0]['card']['cvts']] == ['brompton-xd'] * 4
    assert [b['name'] for b in raw['slots'][0]['card']['cvts']] == [''] * 4


# ── the browser: the dock, the binder, the pull sheet ───────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# WALL, a Brompton wall, on an unnamed SX40 (its four XDs as it arrives)
# and an unnamed S8 beside it.
SEED_JS = """async () => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.fiberCables;
    delete proj.pullSheetEdits;
    await j('PUT', '/api/project', proj);
    const wall = await j('POST', '/api/layer/add', {name: 'WALL', columns: 12, rows: 10,
                                                     cabinet_width: 200, cabinet_height: 200});
    await j('PUT', `/api/layer/${wall.id}`, {processorType: 'brompton'});
    let st = await j('POST', '/api/processors', {deviceId: 'brompton-sx40'});
    const sx = st.processors[0];
    st = await j('POST', '/api/processors', {deviceId: 'brompton-s8'});
    const app = window.app;
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('brompton_names');
    app.selectLayer(app.project.layers[0]);
    await app.refreshProcessors();
    await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
        {layerId: String(wall.id), cardId: sx.slots[0].card.id, lastIndex: 19});
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    app.renderHardwareDock();
    app.resetHistory('Brompton Names Seed');
    return {sx: sx.id, card: sx.slots[0].card.id, wall: wall.id};
}"""

# Every string the dock shows: its text, and the names, tooltips and
# placeholders on its controls.
DOCK_JS = """() => {
    window.app.renderHardwareDock();
    const dock = document.getElementById('hardware-dock');
    const out = [dock.innerText];
    dock.querySelectorAll('*').forEach(el => {
        for (const a of ['title', 'placeholder', 'data-tooltip', 'aria-label']) {
            const v = el.getAttribute(a);
            if (v) out.push(v);
        }
        if (el.tagName === 'INPUT' && el.value) out.push(el.value);
        if (el.tagName === 'OPTION') out.push(el.textContent);
    });
    return out;
}"""

# Every text op of every binder sheet, the hardware and pull pages on.
BINDER_JS = """() => {
    const app = window.app;
    const opts = {sheet: 'tabloid', palette: 'colour', sides: {power: true, data: true},
                  scope: {kind: 'show'}, cover: true, pull: true, hardware: true, wiring: true};
    const plan = app.planBinder(opts);
    const pages = [];
    for (let i = 0; i < plan.length; i++) {
        const r = app.renderBinderPage(opts, i);
        pages.push({kind: plan[i].kind, title: plan[i].title,
                    texts: r.record.ops.filter(o => o.op === 'text').map(o => String(o.text))});
    }
    return pages;
}"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 1000})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(500)
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(1200)
    ids['errors'] = errors
    yield pg, ids
    context.close()


def test_the_dock_names_the_brompton_gear_plainly(page):
    pg, ids = page
    shown = pg.evaluate(DOCK_JS)
    text = '\n'.join(shown)
    assert 'Tessera' not in text, [s for s in shown if 'Tessera' in s][:5]
    assert 'SX40' in text and 'S8' in text, text[:600]
    assert 'XD A' in shown, [s for s in shown if 'XD' in s][:10]
    # the add-a-processor picker: Brompton is the heading, the models plain
    picker = pg.evaluate("""() => [...document.querySelectorAll('optgroup')]
        .filter(g => g.label === 'Brompton')
        .map(g => [...g.querySelectorAll('option')].map(o => o.textContent))""")
    for options in picker:
        assert all('Tessera' not in o for o in options), options
    assert ids['errors'] == []


def test_every_binder_sheet_names_the_brompton_gear_plainly(page):
    pg, ids = page
    pages = pg.evaluate(BINDER_JS)
    assert pages, 'the show planned no sheet'
    said = [(p['title'], t) for p in pages for t in p['texts'] if 'Tessera' in t]
    assert not said, said[:5]
    every = [t for p in pages for t in p['texts']]
    assert any('SX40' in t for t in every), 'no sheet names the SX40'
    assert any(re.search(r'\bXD [A-D]\b', t) for t in every), 'no sheet names an XD box'
    # the pull sheet's rows carry the plain model as their type
    rows = pg.evaluate("""() => { window.app._circuitTailCache = null;
        return window.app.buildPullSheet().totals.map(r => r.type); }""")
    assert 'XD' in rows, rows
    assert not [r for r in rows if 'Tessera' in r], rows
    assert ids['errors'] == []


def test_an_old_pull_sheet_edit_on_the_old_name_still_lands_on_its_row(page):
    """A show saved before the rename keyed its edit on "Tessera XD|EA".
    Open, the edit is on the XD row and is not stale, and the stored key is
    left as it was; the next edit to that row stores it as "XD|EA", once."""
    pg, ids = page
    out = pg.evaluate("""() => {
        const app = window.app;
        app._circuitTailCache = null;
        const pos = app.buildPullList().positions
            .find(p => p.rows.some(r => r.type === 'XD' && r.length === 'EA'));
        const pk = app.pullPositionKey(pos);
        app.project.pullSheetEdits = {positions: {[pk]: {rows: [
            {key: 'Tessera XD|EA', label: 'OLD LABEL'}], added: []}}};
        const read = () => {
            app._circuitTailCache = null;
            const sheet = app.buildPullSheet();
            const p = sheet.positions.find(x => app.pullPositionKey(x) === pk);
            return {row: p.rows.find(r => r.type === 'XD' && r.length === 'EA'),
                    total: sheet.totals.find(r => r.type === 'XD' && r.length === 'EA'),
                    stale: app.pullSheetStaleEdits(),
                    stored: app.project.pullSheetEdits
                        ? JSON.parse(JSON.stringify(app.project.pullSheetEdits)) : null};
        };
        const opened = read();
        app.setPullSheetRowEdit(pk, 'XD|EA', {notes: 'spare in case'});
        const edited = read();
        app.resetPullSheetRow(pk, 'XD|EA');
        const reset = read();
        return {pk, opened, edited, reset};
    }""")
    pk = out['pk']
    opened = out['opened']
    assert opened['row']['label'] == 'OLD LABEL', opened
    assert opened['total']['label'] == 'OLD LABEL', opened
    assert opened['stale'] == [], opened
    assert opened['stored'] == {'positions': {pk: {'rows': [
        {'key': 'Tessera XD|EA', 'label': 'OLD LABEL'}], 'added': []}}}, opened
    edited = out['edited']
    assert edited['row']['label'] == 'OLD LABEL' and edited['row']['notes'] == 'spare in case', edited
    assert edited['stored']['positions'][pk]['rows'] == [
        {'key': 'XD|EA', 'label': 'OLD LABEL', 'notes': 'spare in case'}], edited
    assert out['reset']['row']['label'] != 'OLD LABEL', out['reset']
    assert out['reset']['stored'] is None, out['reset']
    assert ids['errors'] == []
