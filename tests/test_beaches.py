"""Beaches are a list the project keeps, and everything picks from it.

"beach locations need to be addable for data" / "you can either create a
beach or you can pick one from the drop-down of one that you created
earlier in the project" / the typed Location on the distro and box gears:
"Replace it with the picker" (user, 2026-09-08).

  - project.beaches = [{id, name}, ...] in ORDER (the pull-sheet position
    order, the binder's screen order). POST /api/beaches (a duplicate name,
    case-blind, answers with the existing beach), PUT /api/beaches/<id>
    {name}, DELETE /api/beaches/<id> (clears every beachId that pointed at
    it), PUT /api/beaches/order {ids}. Ids come off next_beach_seq.
  - layer.beachId / distro.beachId / cvt.beachId, each nullable, allow-listed
    where the record's fields are validated and echoed resolved.
  - MIGRATION on load: a distro or box with a typed `location` and no
    beachId gets a beach of that name and its id; the location key goes.
  - ONE picker (app-beaches.js): the project's beaches in order, a blank
    entry, and "+ New beach..." which prompts, creates and selects. Screen
    Info's #layer-beach ('Set Beach'), the distro gear's distro-beach-<id>
    ('Set Distro Beach'), the box gear's processor-cvt-beach-<id> ('Set
    Box Beach'). The beaches are renamed / reordered / removed on a BEACHES
    line in the Screens panel.
  - Positions (pullPositions) are the beaches in order with the screens on
    them, then every screen on no beach as its own; a device's rows are
    pulled to its beach; a group named like a beach folds into it.

Run locally (ONE pytest at a time - the browser-test servers use fixed
ports):
    LRD_E2E_PORT=15796 python3 -m pytest tests/test_beaches.py -v --browser chromium
"""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
sys.path.insert(0, HERE)

import app as app_module  # noqa: E402

from test_pull_list import SEED_JS, LIST_JS, _rows  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# ── the wiring (new files must not rot) ──────────────────────────────────

def test_the_beaches_module_is_imported_and_defines_the_picker():
    main_js = open(os.path.join(HERE, '..', 'src', 'static', 'js', 'main.js')).read()
    assert "import './app-beaches.js';" in main_js
    src = open(os.path.join(HERE, '..', 'src', 'static', 'js', 'app-beaches.js')).read()
    for fn in ('fillBeachPicker(', 'wireBeachPicker(', 'buildBeachPicker(', 'renderBeaches(',
               'createBeach(', 'renameBeach(', 'removeBeach(', 'reorderBeaches('):
        assert fn in src, fn
    html = open(os.path.join(HERE, '..', 'src', 'templates', 'index.html')).read()
    assert 'id="layer-beach"' in html and 'id="beaches-panel"' in html
    # the typed Location fields are gone with the picker
    for name in ('app-power.js', 'app-processors.js'):
        js = open(os.path.join(HERE, '..', 'src', 'static', 'js', name), errors='replace').read()
        assert 'distro-location-' not in js and 'processor-cvt-location-' not in js, name
        assert 'pullLocationDatalist' not in js, name


# ── the model, through the Flask client ──────────────────────────────────

def _beaches(client):
    return client.get('/api/project').get_json()['beaches']


def _add_layer(client, name):
    r = client.post('/api/layer/add', json={'name': name, 'columns': 2, 'rows': 2,
                                            'cabinet_width': 100, 'cabinet_height': 100})
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()['id']


def _layer(client, lid):
    return next(l for l in client.get('/api/project').get_json()['layers'] if l['id'] == lid)


def _h9_with_box(client):
    st = client.post('/api/processors', json={'deviceId': 'novastar-h9'}).get_json()
    pid = st['processors'][-1]['id']
    st = client.put(f'/api/processors/{pid}/slots/0',
                    json={'deviceId': 'novastar-card-h-16xrj45-2xfiber'}).get_json()
    proc = next(p for p in st['processors'] if p['id'] == pid)
    cid = proc['slots'][0]['card']['id']
    r = client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                    json={'deviceId': 'novastar-cvt4k-s', 'pair': False})
    assert r.status_code == 201, r.get_data(as_text=True)
    proc = next(p for p in r.get_json()['processors'] if p['id'] == pid)
    return pid, proc['slots'][0]['card']['cvts'][0]['id']


def _raw_box(client, pid):
    st = client.get('/api/processors').get_json()
    return next(p for p in st['processors'] if p['id'] == pid)['slots'][0]['card']['cvts'][0]


def _resolved_box(client, pid):
    st = client.get('/api/processors').get_json()
    return next(p for p in st['resolved'] if p['id'] == pid)['slots'][0]['card']['cvts'][0]


def test_a_fresh_project_has_an_empty_beach_list_and_a_counter(client):
    p = client.get('/api/project').get_json()
    assert p['beaches'] == [] and p['next_beach_seq'] == 1


def test_create_pick_rename_order_and_delete(client):
    # create: trimmed, ids off the counter, in order
    r = client.post('/api/beaches', json={'name': '  SR '})
    assert r.status_code == 201, r.get_data(as_text=True)
    assert r.get_json()['beach'] == {'id': 'b1', 'name': 'SR'} and r.get_json()['created'] is True
    assert r.get_json()['project']['beaches'] == [{'id': 'b1', 'name': 'SR'}]
    r = client.post('/api/beaches', json={'name': 'SL'})
    assert r.status_code == 201 and r.get_json()['beach'] == {'id': 'b2', 'name': 'SL'}
    # a duplicate name, in any case, is the SAME beach - never a second one
    for dup in ('sr', 'SR', ' Sr '):
        r = client.post('/api/beaches', json={'name': dup})
        assert r.status_code == 200 and r.get_json()['beach'] == {'id': 'b1', 'name': 'SR'}, dup
        assert r.get_json()['created'] is False
    assert _beaches(client) == [{'id': 'b1', 'name': 'SR'}, {'id': 'b2', 'name': 'SL'}]
    # blank and non-text names are refused
    for body in ({'name': ''}, {'name': '   '}, {}, {'name': 5}):
        r = client.post('/api/beaches', json=body)
        assert r.status_code == 400 and 'Beach name' in r.get_json()['error'], body
    # pick: a screen, a distro, a box
    lid = _add_layer(client, 'A')
    r = client.put(f'/api/layer/{lid}', json={'beachId': 'b1'})
    assert r.status_code == 200 and r.get_json()['beachId'] == 'b1'
    assert _layer(client, lid)['beachId'] == 'b1'
    # an id nothing answers to leaves the screen where it was; null clears
    r = client.put(f'/api/layer/{lid}', json={'beachId': 'b99'})
    assert r.status_code == 200 and r.get_json()['beachId'] == 'b1'
    r = client.put(f'/api/layer/{lid}', json={'beachId': None})
    assert r.status_code == 200 and r.get_json()['beachId'] is None
    assert client.put(f'/api/layer/{lid}', json={'beachId': 'b2'}).get_json()['beachId'] == 'b2'
    proj = client.get('/api/project').get_json()
    proj['distros'] = [{'id': 'd1', 'name': 'SR', 'ratingA': 400, 'voltage': 208, 'phase': 3, 'beachId': 'b2'},
                       {'id': 'd2', 'name': 'DIM', 'ratingA': 400, 'voltage': 208, 'phase': 3, 'beachId': 'b77'}]
    assert client.post('/api/project', json={'distros': proj['distros']}).status_code == 200
    distros = client.get('/api/project').get_json()['distros']
    assert [d['beachId'] for d in distros] == ['b2', None]   # the unknown one is cleared
    pid, bid = _h9_with_box(client)
    assert _resolved_box(client, pid)['beachId'] is None
    r = client.put(f'/api/processors/{pid}/cvts/{bid}', json={'beachId': 'b2'})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert _raw_box(client, pid)['beachId'] == 'b2' and _resolved_box(client, pid)['beachId'] == 'b2'
    r = client.put(f'/api/processors/{pid}/cvts/{bid}', json={'beachId': 'b99'})
    assert r.status_code == 400 and r.get_json()['error'] == 'Unknown beach'
    assert _raw_box(client, pid)['beachId'] == 'b2'
    # rename: trimmed; a name another beach has is refused
    r = client.put('/api/beaches/b2', json={'name': ' Stage Left '})
    assert r.status_code == 200 and r.get_json()['beach'] == {'id': 'b2', 'name': 'Stage Left'}
    r = client.put('/api/beaches/b2', json={'name': 'sr'})
    assert r.status_code == 400 and 'already a beach called SR' in r.get_json()['error']
    assert client.put('/api/beaches/b9', json={'name': 'X'}).status_code == 404
    # order: a permutation of the ids, nothing else
    r = client.put('/api/beaches/order', json={'ids': ['b2', 'b1']})
    assert r.status_code == 200
    assert [b['id'] for b in _beaches(client)] == ['b2', 'b1']
    for bad in ({'ids': ['b1']}, {'ids': ['b1', 'b1']}, {'ids': ['b1', 'b3']}, {}, {'ids': 'b1b2'}):
        assert client.put('/api/beaches/order', json=bad).status_code == 400, bad
    assert [b['id'] for b in _beaches(client)] == ['b2', 'b1']
    # delete clears every beachId that pointed at it - screen, distro, box
    r = client.delete('/api/beaches/b2')
    assert r.status_code == 200
    p = client.get('/api/project').get_json()
    assert p['beaches'] == [{'id': 'b1', 'name': 'SR'}]
    assert _layer(client, lid)['beachId'] is None
    assert p['distros'][0]['beachId'] is None
    assert _raw_box(client, pid)['beachId'] is None and _resolved_box(client, pid)['beachId'] is None
    assert client.delete('/api/beaches/b2').status_code == 404
    # a freed id is never handed out again
    r = client.post('/api/beaches', json={'name': 'SL'})
    assert r.get_json()['beach'] == {'id': 'b3', 'name': 'SL'}


def test_a_typed_location_becomes_a_beach_on_load(client):
    """A saved file with distro.location 'SR Beach' (and a box at 'sr
    beach') loads with ONE beach 'SR Beach', both records' beachId on it,
    and no `location` key left behind. Loading again changes nothing."""
    pid, bid = _h9_with_box(client)
    assert client.put(f'/api/processors/{pid}/cvts/{bid}', json={'location': 'sr beach'}).status_code == 200
    proj = client.get('/api/project').get_json()
    proj['distros'] = [{'id': 'd1', 'name': 'SR', 'ratingA': 400, 'voltage': 208, 'phase': 3,
                        'location': 'SR Beach'},
                       {'id': 'd2', 'name': 'FOH', 'ratingA': 400, 'voltage': 208, 'phase': 3,
                        'location': 'FOH'}]
    proj.pop('beaches', None)
    proj.pop('next_beach_seq', None)
    r = client.put('/api/project', json=proj)
    assert r.status_code == 200, r.get_data(as_text=True)
    p = client.get('/api/project').get_json()
    assert p['beaches'] == [{'id': 'b1', 'name': 'SR Beach'}, {'id': 'b2', 'name': 'FOH'}]
    d1, d2 = p['distros']
    assert d1['beachId'] == 'b1' and 'location' not in d1
    assert d2['beachId'] == 'b2' and 'location' not in d2
    box = _raw_box(client, pid)
    assert box['beachId'] == 'b1' and 'location' not in box
    assert _resolved_box(client, pid)['beachId'] == 'b1' and _resolved_box(client, pid)['location'] == ''
    # idempotent
    assert client.put('/api/project', json=p).status_code == 200
    again = client.get('/api/project').get_json()
    assert again['beaches'] == p['beaches'] and again['distros'] == p['distros']
    assert again['next_beach_seq'] == p['next_beach_seq'] == 3
    # picking a beach on a box retires a typed location left on it
    assert client.put(f'/api/processors/{pid}/cvts/{bid}', json={'location': 'Old Words'}).status_code == 200
    assert _raw_box(client, pid)['location'] == 'Old Words'
    assert client.put(f'/api/processors/{pid}/cvts/{bid}', json={'beachId': 'b2'}).status_code == 200
    box = _raw_box(client, pid)
    assert box['beachId'] == 'b2' and 'location' not in box


def test_the_list_is_repaired_on_load(client):
    """Malformed shapes converge: a non-list becomes [], a blank name is
    dropped, a duplicate name folds into the first and its pointers move,
    a missing id is minted, a pointer at nothing is cleared, and the
    counter seeds above the highest id in the file."""
    lid_a = _add_layer(client, 'A')
    lid_b = _add_layer(client, 'B')
    lid_c = _add_layer(client, 'C')
    proj = client.get('/api/project').get_json()
    proj['beaches'] = [{'id': 'b4', 'name': 'SR'}, {'id': 'b9', 'name': ' sr '}, {'name': 'SL'},
                       {'id': 'b5', 'name': '  '}, 'junk', None]
    proj['next_beach_seq'] = 2
    for l in proj['layers']:
        l['beachId'] = {lid_a: 'b4', lid_b: 'b9', lid_c: 'gone'}[l['id']]
    assert client.put('/api/project', json=proj).status_code == 200
    p = client.get('/api/project').get_json()
    assert p['beaches'] == [{'id': 'b4', 'name': 'SR'}, {'id': 'b10', 'name': 'SL'}]
    by_id = {l['id']: l['beachId'] for l in p['layers']}
    assert by_id == {lid_a: 'b4', lid_b: 'b4', lid_c: None}
    assert p['next_beach_seq'] == 11
    proj = client.get('/api/project').get_json()
    proj['beaches'] = 'nope'
    assert client.put('/api/project', json=proj).status_code == 200
    p = client.get('/api/project').get_json()
    assert p['beaches'] == [] and all(l['beachId'] is None for l in p['layers'])


def test_round_trip_through_save_and_load(client):
    lid = _add_layer(client, 'A')
    assert client.post('/api/beaches', json={'name': 'SR'}).status_code == 201
    assert client.post('/api/beaches', json={'name': 'SL'}).status_code == 201
    assert client.put(f'/api/layer/{lid}', json={'beachId': 'b2'}).status_code == 200
    assert client.put('/api/beaches/order', json={'ids': ['b2', 'b1']}).status_code == 200
    saved = client.get('/api/project').get_json()
    assert client.post('/api/project/new').status_code == 200
    assert client.get('/api/project').get_json()['beaches'] == []
    assert client.put('/api/project', json=saved).status_code == 200
    p = client.get('/api/project').get_json()
    assert p['beaches'] == [{'id': 'b2', 'name': 'SL'}, {'id': 'b1', 'name': 'SR'}]
    assert _layer(client, lid)['beachId'] == 'b2'
    assert p['next_beach_seq'] == 3


# ── the browser ──────────────────────────────────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

# The show of test_pull_list (WALL-A and WALL-B grouped "SR Beach" on distro
# SR, CENTER loose, card SR) plus two more loose screens, LEFT and SPARE.

MORE_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    // The Flask-client tests above share this server's project; start
    // the browser from no beaches and a fresh counter.
    const p0 = await j('GET', '/api/project');
    p0.beaches = []; p0.next_beach_seq = 1;
    for (const l of p0.layers) delete l.beachId;
    for (const d of p0.distros || []) delete d.beachId;
    await j('PUT', '/api/project', p0);
    const add = (body) => j('POST', '/api/layer/add', body);
    await add({name: 'LEFT', columns: 2, rows: 2, cabinet_width: 200, cabinet_height: 200,
               powerVoltage: 208, powerAmperage: 10, panelWatts: 200,
               powerFlowPattern: 'tl-h', powerOrganized: true, flowPattern: 'tl-h',
               processorType: 'novastar-armor', offset_x: 2000});
    await add({name: 'SPARE', columns: 2, rows: 2, cabinet_width: 200, cabinet_height: 200,
               powerVoltage: 208, powerAmperage: 10, panelWatts: 200,
               powerFlowPattern: 'tl-h', powerOrganized: true, flowPattern: 'tl-h',
               processorType: 'novastar-armor', offset_x: 2600});
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('beaches_setup');
    app.selectLayer(app.project.layers.find(l => l.name === 'WALL-A'));
    app.renderLayers();
    app.renderHardwareDock();
    window.canvasRenderer.render();
    app.resetHistory('Beaches Seed');
    const byName = {};
    for (const l of app.project.layers) byName[l.name] = l.id;
    return byName;
}"""

POS_JS = """() => {
    const app = window.app;
    app._circuitTailCache = null;
    const out = app.buildPullList();
    return JSON.parse(JSON.stringify(out.positions.map(p => ({
        name: p.name, key: p.key, groupId: p.groupId, memberIds: p.memberIds,
        layerIds: p.layerIds, rows: p.rows }))));
}"""

PANEL_JS = """() => ({
    rows: [...document.querySelectorAll('#beaches-panel .beach-row')].map(r => [
        r.dataset.beachId, r.querySelector('.beach-name-input').value,
        r.querySelector('.beach-count').textContent]),
    picker: [...document.querySelectorAll('#layer-beach option')].map(o => [o.value, o.textContent]),
    beaches: JSON.parse(JSON.stringify(window.app.project.beaches || [])),
})"""


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
    pg.wait_for_timeout(800)
    assert ids['centerRunIds'] == [[1, 2], [3]], f'fixture: CENTER must gang columns 1+2: {ids}'
    names = pg.evaluate(MORE_JS)
    pg.wait_for_timeout(800)
    ids['names'] = names
    ids['errors'] = errors
    yield pg, ids
    context.close()


def _history(pg):
    return pg.evaluate("() => ({ action: window.app.history[window.app.historyIndex].action, index: window.app.historyIndex })")


def _select_layer(pg, layer_id):
    pg.evaluate("(id) => { const app = window.app; app.selectLayer(app.project.layers.find(l => l.id === id)); }", layer_id)
    pg.wait_for_timeout(200)


def test_the_panel_and_the_picker_start_empty_and_list_what_is_made(page):
    pg, ids = page
    st = pg.evaluate(PANEL_JS)
    assert st['rows'] == [] and st['beaches'] == []
    assert st['picker'] == [['', '— no beach —'], ['__new_beach__', '+ New beach…']]
    assert pg.locator('#beaches-panel .beaches-empty').count() == 1
    # made in the app (the same route the panel's + Add beach uses)
    pg.evaluate("async () => { await window.app.createBeach('SR'); await window.app.createBeach('SL'); }")
    pg.wait_for_timeout(300)
    st = pg.evaluate(PANEL_JS)
    assert st['beaches'] == [{'id': 'b1', 'name': 'SR'}, {'id': 'b2', 'name': 'SL'}]
    assert st['rows'] == [['b1', 'SR', ''], ['b2', 'SL', '']]
    assert st['picker'] == [['', '— no beach —'], ['b1', 'SR'], ['b2', 'SL'], ['__new_beach__', '+ New beach…']]
    # a duplicate is the same beach, and the history took one entry per make
    assert pg.evaluate("async () => (await window.app.createBeach('sr')).id") == 'b1'
    assert _history(pg)['action'] == 'Add Beach'
    assert ids['errors'] == []


def test_the_screen_picker_sets_the_beach_with_one_undo_entry(page):
    pg, ids = page
    # Screen Info's Beach row lives on the Pixel Map tab of the left panel
    pg.locator('[data-mode="pixel-map"]').click()
    pg.wait_for_timeout(400)
    _select_layer(pg, ids['c'])
    assert pg.evaluate("() => document.getElementById('layer-beach').value") == ''
    before = _history(pg)
    pg.select_option('#layer-beach', 'b2')
    pg.wait_for_timeout(600)
    after = _history(pg)
    assert after['action'] == 'Set Beach' and after['index'] == before['index'] + 1
    assert pg.evaluate("(id) => window.app.project.layers.find(l => l.id === id).beachId", ids['c']) == 'b2'
    served = pg.evaluate("async (id) => (await (await fetch('/api/project')).json()).layers.find(l => l.id === id).beachId", ids['c'])
    assert served == 'b2'
    # the panel counts it; reselecting the screen shows it
    assert pg.evaluate(PANEL_JS)['rows'] == [['b1', 'SR', ''], ['b2', 'SL', '1']]
    _select_layer(pg, ids['a'])
    assert pg.evaluate("() => document.getElementById('layer-beach').value") == ''
    _select_layer(pg, ids['c'])
    assert pg.evaluate("() => document.getElementById('layer-beach').value") == 'b2'
    # a mixed selection shows a dash and nothing selected
    pg.evaluate("(ids) => window.app.setSelectedLayersByIds([ids.a, ids.c], ids.a)", {'a': ids['a'], 'c': ids['c']})
    pg.wait_for_timeout(200)
    assert pg.evaluate("() => [document.getElementById('layer-beach').value, document.getElementById('layer-beach').options[0].textContent]") == ['', '-']
    # undo takes it back
    _select_layer(pg, ids['c'])
    pg.evaluate("() => window.app.undo()")
    pg.wait_for_timeout(800)
    assert pg.evaluate("(id) => window.app.project.layers.find(l => l.id === id).beachId", ids['c']) is None
    pg.evaluate("() => window.app.redo()")
    pg.wait_for_timeout(800)
    assert pg.evaluate("(id) => window.app.project.layers.find(l => l.id === id).beachId", ids['c']) == 'b2'
    assert ids['errors'] == []


def test_new_beach_from_the_picker_creates_and_selects_in_one_step(page):
    pg, ids = page
    pg.locator('[data-mode="pixel-map"]').click()
    pg.wait_for_timeout(400)
    _select_layer(pg, ids['names']['LEFT'])
    before = _history(pg)
    pg.once('dialog', lambda d: d.accept('  Dimmer Beach '))
    pg.select_option('#layer-beach', '__new_beach__')
    pg.wait_for_timeout(900)
    st = pg.evaluate(PANEL_JS)
    assert st['beaches'] == [{'id': 'b1', 'name': 'SR'}, {'id': 'b2', 'name': 'SL'}, {'id': 'b3', 'name': 'Dimmer Beach'}]
    assert pg.evaluate("(id) => window.app.project.layers.find(l => l.id === id).beachId", ids['names']['LEFT']) == 'b3'
    assert pg.evaluate("() => document.getElementById('layer-beach').value") == 'b3'
    after = _history(pg)
    assert after['action'] == 'Set Beach' and after['index'] == before['index'] + 1
    # a cancelled prompt makes nothing and puts the select back
    pg.once('dialog', lambda d: d.dismiss())
    pg.select_option('#layer-beach', '__new_beach__')
    pg.wait_for_timeout(500)
    assert pg.evaluate("() => document.getElementById('layer-beach').value") == 'b3'
    assert len(pg.evaluate(PANEL_JS)['beaches']) == 3
    assert _history(pg) == after
    # tidy: LEFT goes back to SL for the positions test, the extra beach goes
    pg.select_option('#layer-beach', 'b2')
    pg.wait_for_timeout(500)
    pg.evaluate("async () => { await window.app.removeBeach('b3'); }")
    pg.wait_for_timeout(300)
    assert [b['id'] for b in pg.evaluate(PANEL_JS)['beaches']] == ['b1', 'b2']
    assert ids['errors'] == []


def test_positions_are_the_beaches_in_order_then_the_loose_screens(page):
    """WALL-A and WALL-B on SR, CENTER and LEFT on SL, SPARE on nothing:
    two positions in beach order carrying their screens, then SPARE as
    its own. Reordering the beaches reorders the positions."""
    pg, ids = page
    pg.evaluate("""(ids) => {
        const app = window.app;
        for (const id of [ids.a, ids.b]) {
            app.selectLayer(app.project.layers.find(l => l.id === id));
            app.applyToSelectedLayers(l => { l.beachId = 'b1'; });
            app.updateLayers(app.getSelectedLayers(), true, 'Set Beach');
        }
    }""", {'a': ids['a'], 'b': ids['b']})
    pg.wait_for_timeout(800)
    pos = pg.evaluate(POS_JS)
    assert [(p['name'], p['key'], p['groupId']) for p in pos] == [
        ('SR', 'beach:b1', None), ('SL', 'beach:b2', None), ('SPARE', f"layer:{ids['names']['SPARE']}", None)]
    assert pos[0]['memberIds'] == [ids['a'], ids['b']]
    assert pos[1]['memberIds'] == [ids['c'], ids['names']['LEFT']]
    assert pos[2]['memberIds'] == [ids['names']['SPARE']]
    # the SR rows are WALL-A's and WALL-B's, at SR - the group's old key g1
    # is not a position any more
    assert ('Multi', "125'", 1, 'SR 1', '') in _rows(pos[0]['rows'])
    assert pos[0]['layerIds'] == [ids['a'], ids['b']]
    assert pg.evaluate("() => window.app.pullKnownLocations()") == ['SR', 'SL']
    # reorder: SL first
    assert pg.evaluate("() => window.app.moveBeachBefore('b2', 'b1')") is True
    pg.wait_for_timeout(500)
    assert [b['id'] for b in pg.evaluate(PANEL_JS)['beaches']] == ['b2', 'b1']
    assert _history(pg)['action'] == 'Reorder Beaches'
    pos = pg.evaluate(POS_JS)
    assert [p['name'] for p in pos] == ['SL', 'SR', 'SPARE']
    assert pg.evaluate("() => window.app.moveBeachBefore('b2', null)") is True
    pg.wait_for_timeout(500)
    assert [p['name'] for p in pg.evaluate(POS_JS)] == ['SR', 'SL', 'SPARE']
    assert pg.evaluate(PANEL_JS)['rows'] == [['b1', 'SR', '2'], ['b2', 'SL', '2']]
    assert ids['errors'] == []


def test_a_group_named_like_a_beach_folds_into_it(page):
    """WALL-A and WALL-B are the group "SR Beach". With their own beachIds
    cleared and the beach renamed "sr beach", they are on it by the
    group's name - the earlier "groups are beaches" files keep working."""
    pg, ids = page
    pg.evaluate("""(ids) => {
        const app = window.app;
        app.setSelectedLayersByIds([ids.a, ids.b], ids.a);
        app.applyToSelectedLayers(l => { l.beachId = null; });
        app.updateLayers(app.getSelectedLayers(), true, 'Set Beach');
    }""", {'a': ids['a'], 'b': ids['b']})
    pg.wait_for_timeout(800)
    pos = pg.evaluate(POS_JS)
    assert [p['name'] for p in pos] == ['SL', 'SR Beach', 'SPARE']
    assert pos[1]['key'] == 'g1' and pos[1]['memberIds'] == [ids['a'], ids['b']]
    pg.evaluate("async () => { await window.app.renameBeach('b1', 'sr beach'); }")
    pg.wait_for_timeout(500)
    assert _history(pg)['action'] == 'Rename Beach'
    pos = pg.evaluate(POS_JS)
    assert [(p['name'], p['key']) for p in pos] == [
        ('sr beach', 'beach:b1'), ('SL', 'beach:b2'), ('SPARE', f"layer:{ids['names']['SPARE']}")]
    assert pos[0]['memberIds'] == [ids['a'], ids['b']]
    assert ('Multi', "125'", 1, 'SR 1', '') in _rows(pos[0]['rows'])
    pg.evaluate("async () => { await window.app.renameBeach('b1', 'SR'); }")
    pg.wait_for_timeout(500)
    pos = pg.evaluate(POS_JS)
    assert [p['name'] for p in pos] == ['SL', 'SR Beach', 'SPARE']
    # back on SR by their own picks
    pg.evaluate("""(ids) => {
        const app = window.app;
        app.setSelectedLayersByIds([ids.a, ids.b], ids.a);
        app.applyToSelectedLayers(l => { l.beachId = 'b1'; });
        app.updateLayers(app.getSelectedLayers(), true, 'Set Beach');
    }""", {'a': ids['a'], 'b': ids['b']})
    pg.wait_for_timeout(800)
    assert [p['name'] for p in pg.evaluate(POS_JS)] == ['SR', 'SL', 'SPARE']
    assert ids['errors'] == []


def test_the_distro_picker_pulls_the_power_rows_to_its_beach(page):
    """Distro SR put on SL through its gear: its "12 way", both Multis,
    the Breakouts, the circuit cables and the power jumpers of WALL-A and
    WALL-B leave SR for SL; the data rows stay; one 'Set Distro Beach'."""
    pg, ids = page
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(400)
    pg.evaluate("() => { window.app.renderHardwareDock(); }")
    pg.wait_for_timeout(300)
    before = pg.evaluate(LIST_JS)
    assert pg.evaluate("""(popId) => {
        const gear = document.querySelector(`[data-hwpop="${popId}"]`);
        if (!gear) return false;
        gear.click();
        const pop = document.getElementById('hw-gear-popover');
        return !!(pop && pop.style.display !== 'none');
    }""", f"distro-{ids['distroId']}"), 'the distro gear did not open'
    pg.wait_for_timeout(300)
    out = pg.evaluate("""(id) => {
        const sel = document.querySelector(`[data-lrd-field="distro-beach-${id}"]`);
        return { inPop: !!(sel && sel.closest('#hw-gear-popover')), tag: sel && sel.tagName,
                 value: sel && sel.value, options: sel ? [...sel.options].map(o => o.textContent) : null,
                 labels: [...document.querySelectorAll('#hw-gear-popover label')].map(l => l.textContent),
                 typed: !!document.querySelector(`[data-lrd-field="distro-location-${id}"]`) };
    }""", ids['distroId'])
    assert out['inPop'] and out['tag'] == 'SELECT' and out['value'] == '', out
    assert out['options'] == ['— no beach —', 'SR', 'SL', '+ New beach…'], out
    assert 'Beach' in out['labels'] and 'Location' not in out['labels'] and not out['typed'], out
    h0 = _history(pg)
    pg.select_option(f'[data-lrd-field="distro-beach-{ids["distroId"]}"]', 'b2')
    pg.wait_for_timeout(800)
    h1 = _history(pg)
    assert h1['action'] == 'Set Distro Beach' and h1['index'] == h0['index'] + 1
    assert pg.evaluate("(id) => window.app.getDistros().find(d => d.id === id).beachId", ids['distroId']) == 'b2'
    # the popover re-rendered with the pick in place
    assert pg.evaluate("(id) => document.querySelector(`[data-lrd-field=\"distro-beach-${id}\"]`).value", ids['distroId']) == 'b2'
    pg.keyboard.press('Escape')
    out = pg.evaluate(LIST_JS)
    pos = {p['name']: p for p in out['positions']}
    assert [p['name'] for p in out['positions']] == ['SR', 'SL', 'SPARE']
    sl_rows = _rows(pos['SL']['rows'])
    for row in [('12 way', 'EA', 1, 'SR', ''), ('Multi', "100'", 1, 'SR 2', ''), ('Multi', "125'", 1, 'SR 1', ''),
                ('Tru-1 Breakout', 'EA', 2, 'SR 1-2', '')]:
        assert row in sl_rows, (row, sl_rows)
    # the walls' power jumpers merged with CENTER's and LEFT's own, at SL
    jumps = [r for r in sl_rows if r[0] == 'Tru-1 Power Jump']
    assert len(jumps) == 1 and 'WALL-A' in jumps[0][3] and 'WALL-B' in jumps[0][3], sl_rows
    assert not [r for r in _rows(pos['SR']['rows']) if r[0] in ('12 way', 'Multi', 'Tru-1 Breakout')]
    assert ('Ether-con Snake', "100'", 1, 'SNAKE A', '2-way') in _rows(pos['SR']['rows'])
    assert set(pos['SL']['layerIds']) >= {ids['a'], ids['b'], ids['c']}
    counts = lambda rows: sorted((t, l, q) for t, l, q, _, _ in _rows(rows))
    assert counts(out['totals']) == counts(before['totals'])
    assert pg.evaluate(PANEL_JS)['rows'] == [['b1', 'SR', '2'], ['b2', 'SL', '3']]
    # the served distro carries it
    served = pg.evaluate("async (id) => (await (await fetch('/api/project')).json()).distros.find(d => d.id === id).beachId", ids['distroId'])
    assert served == 'b2'
    assert ids['errors'] == []


def test_the_box_picker_pulls_its_rows_to_its_beach(page):
    """A CVT10 on card SR, put on SR through its gear: the box's own
    "CVT10 EA" row lands on SR (it delivers WALL-A's socket, which is on SR
    anyway); one 'Set Box Beach'; the resolved box carries the id."""
    pg, ids = page
    box = pg.evaluate("""async (ids) => {
        const app = window.app;
        const j = (method, url, body) => fetch(url, {method,
            headers: {'Content-Type': 'application/json'},
            body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
        const st = await j('POST', `/api/processors/${ids.procId}/cards/${ids.cardId}/cvts`, {deviceId: 'novastar-cvt10', pair: false});
        const id = st.processors[0].slots[0].card.cvts[0].id;
        app.project = await j('GET', '/api/project');
        app.dedupeProjectLayers('beaches_box');
        await app.refreshProcessors(); await app.refreshPortAssignment();
        app.renderLayers(); app.renderHardwareDock();
        app.resetHistory('Box Seed');
        return id;
    }""", ids)
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(400)
    pg.evaluate("() => { window.app.renderHardwareDock(); }")
    pg.wait_for_timeout(300)
    assert pg.evaluate("""(popId) => {
        const gear = document.querySelector(`[data-hwpop="${popId}"]`);
        if (!gear) return false;
        gear.click();
        const pop = document.getElementById('hw-gear-popover');
        return !!(pop && pop.style.display !== 'none');
    }""", f'box-{box}'), 'the box gear did not open'
    pg.wait_for_timeout(300)
    out = pg.evaluate("""(bid) => {
        const sel = document.querySelector(`[data-lrd-field="processor-cvt-beach-${bid}"]`);
        return { inPop: !!(sel && sel.closest('#hw-gear-popover')), tag: sel && sel.tagName,
                 value: sel && sel.value, options: sel ? [...sel.options].map(o => o.textContent) : null,
                 labels: [...document.querySelectorAll('#hw-gear-popover label')].map(l => l.textContent),
                 typed: !!document.querySelector(`[data-lrd-field="processor-cvt-location-${bid}"]`) };
    }""", box)
    assert out['inPop'] and out['tag'] == 'SELECT' and out['value'] == '', out
    assert out['options'] == ['— no beach —', 'SR', 'SL', '+ New beach…'], out
    assert 'Beach' in out['labels'] and 'Fiber' in out['labels'] and 'Location' not in out['labels'], out
    assert not out['typed']
    h0 = _history(pg)
    pg.select_option(f'[data-lrd-field="processor-cvt-beach-{box}"]', 'b1')
    pg.wait_for_timeout(900)
    h1 = _history(pg)
    assert h1['action'] == 'Set Box Beach' and h1['index'] == h0['index'] + 1
    assert pg.evaluate("(bid) => window.app._dockFindCvt(bid).cvt.beachId", box) == 'b1'
    assert pg.evaluate("(bid) => document.querySelector(`[data-lrd-field=\"processor-cvt-beach-${bid}\"]`).value", box) == 'b1'
    # "+ New beach..." from the gear: prompt, create, select - one entry
    pg.once('dialog', lambda d: d.accept('Video Village'))
    pg.select_option(f'[data-lrd-field="processor-cvt-beach-{box}"]', '__new_beach__')
    pg.wait_for_timeout(1200)
    h2 = _history(pg)
    assert h2['action'] == 'Set Box Beach' and h2['index'] == h1['index'] + 1
    st = pg.evaluate(PANEL_JS)
    assert [b['name'] for b in st['beaches']] == ['SR', 'SL', 'Video Village']
    vv = st['beaches'][2]['id']
    assert pg.evaluate("(bid) => window.app._dockFindCvt(bid).cvt.beachId", box) == vv
    assert pg.evaluate("(bid) => document.querySelector(`[data-lrd-field=\"processor-cvt-beach-${bid}\"]`).value", box) == vv
    pg.keyboard.press('Escape')
    out = pg.evaluate(LIST_JS)
    pos = {p['name']: p for p in out['positions']}
    assert [p['name'] for p in out['positions']] == ['SR', 'SL', 'Video Village', 'SPARE']
    assert ('CVT10', 'EA', 1, 'A', '') in _rows(pos['Video Village']['rows'])
    assert pos['Video Village']['key'] == f'beach:{vv}' and pos['Video Village']['memberIds'] == []
    # undo the pick: the box is back on SR (the resolved tree follows a round-trip)
    pg.evaluate('() => window.app.undo()')
    waited, got = 0, None
    while waited < 4000:
        got = pg.evaluate("(bid) => { const f = window.app._dockFindCvt(bid); return f ? f.cvt.beachId : null; }", box)
        if got == 'b1':
            break
        pg.wait_for_timeout(200)
        waited += 200
    assert got == 'b1', got
    # tidy: the box and the extra beach go
    pg.evaluate("""async (ids) => {
        const app = window.app;
        for (const box of [...app._processorsResolved[0].slots[0].card.cvts].map(c => c.id)) {
            await fetch(`/api/processors/${ids.procId}/cvts/${box}`, {method: 'DELETE'});
        }
        await app.refreshProcessors(); await app.refreshPortAssignment();
    }""", ids)
    pg.evaluate("async (id) => { await window.app.removeBeach(id); }", vv)
    pg.wait_for_timeout(400)
    assert [p['name'] for p in pg.evaluate(POS_JS)] == ['SR', 'SL', 'SPARE']
    assert ids['errors'] == []


def test_the_beaches_line_renames_and_removes(page):
    """Double-click a name to rename it; x removes the beach and every
    screen, distro and box on it falls back to its own position."""
    pg, ids = page
    name = pg.locator('#beaches-panel .beach-row[data-beach-id="b2"] .beach-name-input')
    name.dblclick()
    pg.wait_for_timeout(100)
    name.fill('Stage Left')
    name.press('Enter')
    pg.wait_for_timeout(600)
    st = pg.evaluate(PANEL_JS)
    assert st['beaches'] == [{'id': 'b1', 'name': 'SR'}, {'id': 'b2', 'name': 'Stage Left'}]
    assert _history(pg)['action'] == 'Rename Beach'
    assert [p['name'] for p in pg.evaluate(POS_JS)] == ['SR', 'Stage Left', 'SPARE']
    # a rename to a name another beach has is refused and the row reads the stored name
    name = pg.locator('#beaches-panel .beach-row[data-beach-id="b2"] .beach-name-input')
    name.dblclick()
    pg.wait_for_timeout(100)
    name.fill('sr')
    name.press('Enter')
    pg.wait_for_timeout(600)
    assert pg.evaluate(PANEL_JS)['rows'] == [['b1', 'SR', '2'], ['b2', 'Stage Left', '3']]
    # remove SL: CENTER and LEFT and the distro fall back
    pg.locator('#beaches-panel .beach-row[data-beach-id="b2"] .beach-remove').click()
    pg.wait_for_timeout(600)
    st = pg.evaluate(PANEL_JS)
    assert st['beaches'] == [{'id': 'b1', 'name': 'SR'}] and st['rows'] == [['b1', 'SR', '2']]
    assert _history(pg)['action'] == 'Remove Beach'
    cleared = pg.evaluate("""(ids) => {
        const app = window.app;
        return [ids.c, ids.left].map(id => app.project.layers.find(l => l.id === id).beachId)
            .concat([app.getDistros().find(d => d.id === ids.distroId).beachId]);
    }""", {'c': ids['c'], 'left': ids['names']['LEFT'], 'distroId': ids['distroId']})
    assert cleared == [None, None, None]
    pos = pg.evaluate(POS_JS)
    assert [p['name'] for p in pos] == ['SR', 'CENTER', 'LEFT', 'SPARE']
    assert ('Multi', "125'", 1, 'SR 1', '') in _rows(pos[0]['rows'])
    # undo brings the beach and its pointers back
    pg.evaluate('() => window.app.undo()')
    pg.wait_for_timeout(900)
    st = pg.evaluate(PANEL_JS)
    assert [b['name'] for b in st['beaches']] == ['SR', 'Stage Left']
    assert [p['name'] for p in pg.evaluate(POS_JS)] == ['SR', 'Stage Left', 'SPARE']
    assert ids['errors'] == []


def test_round_trip_through_save_and_load_in_the_browser(page):
    pg, ids = page
    out = pg.evaluate("""async () => {
        const app = window.app;
        const saved = JSON.parse(JSON.stringify(app.project));
        const res = await fetch('/api/project', {method: 'PUT', headers: {'Content-Type': 'application/json'},
                                                  body: JSON.stringify(saved)});
        const back = await res.json();
        app.project = back;
        app.dedupeProjectLayers('beaches_roundtrip');
        app.renderLayers();
        app._circuitTailCache = null;
        return { beaches: back.beaches, seq: back.next_beach_seq,
                 layers: back.layers.map(l => [l.name, l.beachId || null]),
                 distro: back.distros[0].beachId,
                 positions: app.buildPullList().positions.map(p => [p.name, p.key]) };
    }""")
    assert out['beaches'] == [{'id': 'b1', 'name': 'SR'}, {'id': 'b2', 'name': 'Stage Left'}]
    assert dict(out['layers']) == {'WALL-A': 'b1', 'WALL-B': 'b1', 'CENTER': 'b2', 'LEFT': 'b2', 'SPARE': None}
    assert out['distro'] == 'b2'
    assert out['positions'] == [['SR', 'beach:b1'], ['Stage Left', 'beach:b2'], ['SPARE', f"layer:{ids['names']['SPARE']}"]]
    assert ids['errors'] == []
