"""Gear lives at a location; the pull sheet lists the CVTs and the distros.

"We need to be able to put CVT's or prcessor's at beach locations so they
can be accounted for on the pull sheets. and CVT's or XD's or what have you
need to be able to be listed in the pullsheets as well" (user, 2026-09-07).

  - A breakout box carries `location` (free text, blank clears) the way it
    carries fiberType: PUT /api/processors/<id>/cvts/<cvtId>, resolved onto
    the box. A distro already had one. BEACHES (2026-09-08): the project
    keeps its beaches as a list (project.beaches, POST /api/beaches), and a
    box, a distro and a screen each PICK one by `beachId` - the Beach
    picker in the box's and the distro's gear popovers ('Set Box Beach',
    'Set Distro Beach') replaced the typed Location fields; a typed
    location left on a record migrates into a beach of that name on load.
    The beaches lead the positions in their order (key `beach:<id>`), a
    group called like a beach folds into it, and pullKnownLocations() is
    the beach names.
  - Every row a DEVICE produces is pulled where the device sits: a distro's
    Multi / Breakout / circuit cables / gangs / power jumpers at the
    distro's location; a box's data rows, fiber and jumpers at the box's
    location. A location name IS a position - matched case-blind against
    the groups, so a distro at "SR Beach" and the group "SR Beach" are one
    position (the group's key); a name no group carries is its own,
    keyed `loc:<name lower-cased>`.
  - Gear rows, EA: one per breakout box (its catalog model as the type,
    its name or letter as the label; two at one beach merge to qty 2), one
    per distro with a box in use ("12 way" for 1-2 boxes, "24 way" 3-4,
    "36 way" 5-6, "48 way" 7-8 - past 8 the type stays "48 way" and Notes
    say how many).

Run locally (ONE pytest at a time - the browser-test servers use fixed
ports):
    LRD_E2E_PORT=15793 python3 -m pytest tests/test_pull_locations.py -v --browser chromium
"""

import base64
import io
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
sys.path.insert(0, HERE)

import pull_sheet  # noqa: E402

openpyxl = pytest.importorskip('openpyxl', reason='openpyxl not installed')

from test_pull_list import SEED_JS, LIST_JS, _rows  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# ── the store, through the Flask client ──────────────────────────────────

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


def test_a_boxs_location_round_trips_trims_and_clears(client):
    pid, bid = _h9_with_box(client)
    assert _resolved_box(client, pid)['location'] == ''
    r = client.put(f'/api/processors/{pid}/cvts/{bid}', json={'location': '  SL Beach '})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert _raw_box(client, pid)['location'] == 'SL Beach'
    assert _resolved_box(client, pid)['location'] == 'SL Beach'
    # a PUT without the key leaves it alone; the other fields still land
    assert client.put(f'/api/processors/{pid}/cvts/{bid}', json={'name': 'SR', 'fiberFt': 50}).status_code == 200
    raw = _raw_box(client, pid)
    assert (raw['location'], raw['name'], raw['fiberFt']) == ('SL Beach', 'SR', 50)
    # blank / null clear and leave no key behind
    for body in ({'location': ''}, {'location': None}, {'location': '   '}):
        assert client.put(f'/api/processors/{pid}/cvts/{bid}', json={'location': 'X'}).status_code == 200
        assert client.put(f'/api/processors/{pid}/cvts/{bid}', json=body).status_code == 200, body
        assert 'location' not in _raw_box(client, pid), body
    assert _resolved_box(client, pid)['location'] == ''
    # not text is refused with the reason, and nothing changes
    assert client.put(f'/api/processors/{pid}/cvts/{bid}', json={'location': 'SR Beach'}).status_code == 200
    r = client.put(f'/api/processors/{pid}/cvts/{bid}', json={'location': 5})
    assert r.status_code == 400 and r.get_json()['error'] == 'Location must be text'
    assert _raw_box(client, pid)['location'] == 'SR Beach'


# ── the browser ──────────────────────────────────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

# The show of test_pull_list: group SR Beach (WALL-A and WALL-B) on distro
# SR boxes 1 and 2, the loose CENTER; card SR with WALL-A's and WALL-B's
# ports in SNAKE A and CENTER's on a 50' cable.

REBUILD_JS = """async () => {
    const app = window.app;
    await app.refreshProcessors(); await app.refreshPortAssignment();
    app._circuitTailCache = null;
    return JSON.parse(JSON.stringify(app.buildPullList()));
}"""

POS_JS = """() => {
    const app = window.app;
    app._circuitTailCache = null;
    const out = app.buildPullList();
    return JSON.parse(JSON.stringify(out.positions.map(p => ({
        name: p.name, key: p.key, groupId: p.groupId, location: p.location,
        memberIds: p.memberIds, layerIds: p.layerIds, rows: p.rows }))));
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
    pg.wait_for_timeout(2000)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(500)
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(1200)
    assert ids['centerRunIds'] == [[1, 2], [3]], f'fixture: CENTER must gang columns 1+2: {ids}'
    ids['errors'] = errors
    yield pg, ids
    context.close()


def _set_distro_location(pg, ids, text):
    pg.evaluate("([id, text]) => window.app.updateDistro(id, {location: text})", [ids['distroId'], text])


def _by_name(positions):
    return {p['name']: p for p in positions}


def test_a_distro_at_the_groups_beach_is_the_groups_position(page):
    """"SR Beach" typed on the distro, in any case, matches the group SR
    Beach: one position, the group's key, the rows exactly where they
    were with no location."""
    pg, ids = page
    before = pg.evaluate(POS_JS)
    assert [p['name'] for p in before] == ['SR Beach', 'CENTER']
    assert [p['key'] for p in before] == ['g1', f"layer:{ids['c']}"]
    assert before[0]['memberIds'] == [ids['a'], ids['b']] and before[0]['location'] == 'SR Beach'
    for text in ('SR Beach', 'sr beach', '  SR BEACH  '):
        _set_distro_location(pg, ids, text)
        after = pg.evaluate(POS_JS)
        assert [p['name'] for p in after] == ['SR Beach', 'CENTER'], text
        assert after[0]['key'] == 'g1' and after[0]['groupId'] == 'g1', text
        assert _rows(after[0]['rows']) == _rows(before[0]['rows']), text
        assert _rows(after[1]['rows']) == _rows(before[1]['rows']), text
    _set_distro_location(pg, ids, '')
    assert ids['errors'] == []


def test_a_distro_at_its_own_beach_pulls_the_power_rows_there(page):
    """SR at "Dimmer Beach" (no group of that name): every row SR produces
    - its "12 way", both Multis, both Breakouts, the circuit cables and the
    power jumpers of the circuits on it - leaves SR Beach for a position of
    its own, keyed `loc:dimmer beach`, whose layerIds are the screens it
    pulled in. The data rows stay with the screens; CENTER (no distro) is
    untouched; the totals do not change."""
    pg, ids = page
    before = pg.evaluate(LIST_JS)
    _set_distro_location(pg, ids, 'Dimmer Beach')
    out = pg.evaluate(LIST_JS)
    pos = _by_name(out['positions'])
    assert [p['name'] for p in out['positions']] == ['SR Beach', 'CENTER', 'Dimmer Beach']
    dimmer = pos['Dimmer Beach']
    assert dimmer['key'] == 'loc:dimmer beach' and dimmer['groupId'] is None
    assert dimmer['location'] == 'Dimmer Beach'
    assert dimmer['memberIds'] == [] and dimmer['layerIds'] == [ids['a'], ids['b']]
    assert _rows(dimmer['rows']) == [
        ('12 way', 'EA', 1, 'SR', ''),
        ('Multi', "100'", 1, 'SR 2', ''),
        ('Multi', "125'", 1, 'SR 1', ''),
        ('Tru-1', "6'", 1, 'SR2-1', ''),
        ('Tru-1', "10'", 2, 'SR1-1, SR1-2', ''),
        ('Tru-1 Breakout', 'EA', 2, 'SR 1-2', ''),
        ('Tru-1 Power Jump', "6'", 2, 'WALL-A, WALL-B', ''),
    ]
    assert _rows(pos['SR Beach']['rows']) == [
        ('Data Jump', "6'", 4, 'WALL-A, WALL-B', ''),
        ('Ether-con Snake', "100'", 1, 'SNAKE A', '2-way'),
    ]
    assert pos['SR Beach']['layerIds'] == [ids['a'], ids['b']]
    assert _rows(pos['CENTER']['rows']) == _rows(_by_name(before['positions'])['CENTER']['rows'])
    # the totals keep every (type, length, qty); only the order the labels
    # were met in moves with the position
    counts = lambda rows: [(t, l, q) for t, l, q, _, _ in _rows(rows)]
    assert counts(out['totals']) == counts(before['totals'])
    # byScreen is the screen's whole reading wherever it was pulled
    a = out['byScreen'][str(ids['a'])]
    assert _rows(a['rows']) == _rows(before['byScreen'][str(ids['a'])]['rows'])
    # the distro's hardware list carries its gear row
    hw = {(h['kind'], h['name']): _rows(h['rows']) for h in out['hardware']}
    assert hw[('distro', 'SR')][0] == ('12 way', 'EA', 1, 'SR', '')
    assert ids['errors'] == []


def test_the_editor_keys_a_device_location_and_the_edit_survives_a_rebuild(page):
    pg, ids = page
    key = 'loc:dimmer beach'
    out = pg.evaluate("""(key) => {
        const app = window.app;
        app._circuitTailCache = null;
        const list = app.buildPullList();
        const pos = list.positions.find(p => p.name === 'Dimmer Beach');
        const posKey = app.pullPositionKey(pos);
        const engine = pos.rows.find(r => r.type === 'Multi' && r.length === "125'");
        const changed = app.setPullSheetRowEdit(key, "Multi|125'", {qty: 3, notes: 'ramp'}, engine);
        const read = () => {
            app._circuitTailCache = null;
            const sheet = app.buildPullSheet();
            const p = sheet.positions.find(x => x.name === 'Dimmer Beach');
            const r = p.rows.find(x => x.type === 'Multi' && x.length === "125'");
            return [r.qty, r.notes, sheet.totals.find(x => x.type === 'Multi' && x.length === "125'").qty];
        };
        const first = read();
        app.renderLayers();
        const second = read();
        return { posKey, changed, first, second,
                 store: JSON.parse(JSON.stringify(app.project.pullSheetEdits)),
                 stale: app.pullSheetStaleEdits().map(s => [s.positionKey, s.key]) };
    }""", key)
    assert out['posKey'] == key and out['changed'] is True
    assert out['first'] == [3, 'ramp', 3] and out['second'] == [3, 'ramp', 3]
    assert out['store'] == {'positions': {key: {'rows': [{'key': "Multi|125'", 'qty': 3, 'notes': 'ramp'}], 'added': []}}}
    assert out['stale'] == []
    # with the distro back home the edit is stale (kept, flagged), and the
    # SR Beach row reads the engine again
    _set_distro_location(pg, ids, '')
    out = pg.evaluate("""() => {
        const app = window.app;
        app._circuitTailCache = null;
        const sheet = app.buildPullSheet();
        return { names: sheet.positions.map(p => p.name),
                 multi: sheet.positions[0].rows.filter(r => r.type === 'Multi').map(r => [r.length, r.qty, r.notes]),
                 stale: app.pullSheetStaleEdits().map(s => [s.positionKey, s.key]) };
    }""")
    assert out['names'] == ['SR Beach', 'CENTER']
    assert out['multi'] == [["100'", 1, ''], ["125'", 1, '']]
    assert out['stale'] == [[key, "Multi|125'"]]
    pg.evaluate("(k) => window.app.resetPullSheetRow(k, \"Multi|125'\")", key)
    assert pg.evaluate("() => window.app.project.pullSheetEdits || null") is None
    assert ids['errors'] == []


def test_the_workbook_and_the_binder_take_a_device_location(page):
    """The route lays "Dimmer Beach" into its own column block with the
    "12 way" row; the binder plans a pull page for it and prints WALL-A's
    POWER page once, under SR Beach; the cover says whose gear it holds."""
    pg, ids = page
    _set_distro_location(pg, ids, 'Dimmer Beach')
    out = pg.evaluate("""async () => {
        const app = window.app;
        app._circuitTailCache = null;
        const list = JSON.parse(JSON.stringify(app.buildPullSheet()));
        const resp = await fetch('/api/export/pull-sheet', {method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({pull_list: list, project_name: 'Beaches', engineer: '', rev: '1.0', date: '', date_iso: ''})});
        const bytes = new Uint8Array(await resp.arrayBuffer());
        let bin = ''; for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
        const opts = { palette: 'colour', sides: {power: true, data: true}, scope: {kind: 'show'},
                       cover: true, pull: true, hardware: true };
        const plan = app.planBinder(opts).map(p => p.title);
        const cover = app.renderBinderPage(opts, 0).texts;   // sheet 1.1, the overview
        return { status: resp.status, b64: btoa(bin), plan, cover };
    }""")
    assert out['status'] == 200
    wb = openpyxl.load_workbook(io.BytesIO(base64.b64decode(out['b64'])))
    ws = wb['Pull Sheet']
    titles = [ws.cell(5, c).value for c in pull_sheet.BLOCK_COLS]
    assert titles[:3] == ['SR Beach', 'CENTER', 'Dimmer Beach'], titles
    col = pull_sheet.BLOCK_COLS[2]
    rows = [tuple(ws.cell(r, col + i).value for i in range(4)) for r in range(7, 20)]
    assert ('12 way', 'EA', 1, 'SR') in rows, rows
    assert ('Multi', "125'", 1, 'SR 1') in rows, rows
    # the positions side by side on one pull sheet, in position order, the
    # device location last
    pulls = [t for t in out['plan'] if t.startswith('Pull - ')]
    assert pulls == ['Pull - SR Beach, CENTER, Dimmer Beach'], out['plan']
    assert out['plan'].count('WALL-A - Power') == 1 and out['plan'].count('WALL-B - Power') == 1
    # the set runs by series: every screen sheet (2.x, power then data) before
    # the pull sheet (3.x)
    assert out['plan'].index('WALL-A - Power') + 1 == out['plan'].index('WALL-A - Data') < out['plan'].index(pulls[0])
    i = out['cover'].index('Dimmer Beach')
    assert out['cover'][i + 1] == 'gear for WALL-A, WALL-B', out['cover'][i:i + 4]
    _set_distro_location(pg, ids, '')
    assert ids['errors'] == []


def test_a_box_at_its_beach_pulls_its_ports_rows_and_two_boxes_list_once(page):
    """Two CVT10s on card SR (OPT 1 delivers sockets 1-8 again - every
    port here; OPT 2 delivers 9-16, nothing), both on the beach "SL Beach"
    - a beach the project keeps (project.beaches, made the way the picker
    makes one) that each box PICKS by id. The sockets' home runs are the
    box's now (its snake of sockets 1-2 with a 10' extension on socket 1,
    its 50' cable on 3), so the snake, the extension and its `Ether-con
    Barrel` (one per extension, 2026-09-07), CENTER's cable, every data
    jumper, box A's fiber and ONE "CVT10 EA" row of qty 2 labelled "A, B"
    land on SL Beach, whose layerIds are the three screens; the power rows
    stay where they were. The beaches lead the positions in THEIR order,
    a beach called like the group SR Beach folds the group into it, and
    the loose screen comes last. Boxes on no beach fall back to the first
    screen they deliver, and a box delivering nothing on no beach is not
    listed. A second spelling of a beach's name is the same beach; a
    beachId the project does not know is refused."""
    pg, ids = page
    out = pg.evaluate("""async (ids) => {
        const app = window.app;
        const j = (method, url, body) => fetch(url, {method,
            headers: {'Content-Type': 'application/json'},
            body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
        // The typed locations the tests above put on the distro migrated
        // into beaches on the server's project funnel (_normalize_beaches
        // runs on every project PUT) and stayed there with nothing on
        // them; the beaches from here are this test's own.
        const results = {};
        results.leftovers = ((await j('GET', '/api/beaches')).beaches || []).map(b => b.name);
        for (const b of (await j('GET', '/api/beaches')).beaches || []) await fetch(`/api/beaches/${b.id}`, {method: 'DELETE'});
        app.project = await j('GET', '/api/project');
        app.dedupeProjectLayers('pull_locations_boxes');
        let st = await j('POST', `/api/processors/${ids.procId}/cards/${ids.cardId}/cvts`, {deviceId: 'novastar-cvt10', pair: false});
        const boxA = st.processors[0].slots[0].card.cvts[0].id;
        st = await j('POST', `/api/processors/${ids.procId}/cards/${ids.cardId}/cvts`, {deviceId: 'novastar-cvt10', pair: false});
        const boxB = st.processors[0].slots[0].card.cvts[1].id;
        const rebuild = %s;
        results.boxA = boxA; results.boxB = boxB;
        results.noLocation = await rebuild();
        results.knownBefore = app.pullKnownLocations();
        // the beaches, the way the picker makes them: SL Beach first, then
        // one called like the group
        const sl = await app.createBeach('SL Beach');
        const sr = await app.createBeach('SR Beach');
        results.beaches = app.getBeaches().map(b => [b.id, b.name]);
        results.sl = sl && sl.id; results.sr = sr && sr.id;
        // the same name in another spelling answers with THAT beach
        const again = await fetch('/api/beaches', {method: 'POST', headers: {'Content-Type': 'application/json'},
                                                   body: JSON.stringify({name: '  sl beach '})});
        const body = await again.json();
        results.again = [again.status, body.created, body.beach, (body.project.beaches || []).length];
        // a beach the project does not have is refused, and nothing changes
        const bad = await fetch(`/api/processors/${ids.procId}/cvts/${boxB}`, {method: 'PUT',
            headers: {'Content-Type': 'application/json'}, body: JSON.stringify({beachId: 'b999'})});
        results.bad = [bad.status, (await bad.json()).error];
        await j('PUT', `/api/processors/${ids.procId}/cvts/${boxA}`, {beachId: sl.id, fiberType: '12 Tac Fiber', fiberFt: 250,
                 snakes: [{ports: [1, 2], ft: 100}], portCables: {'3': {ft: 50}, '1': {ft: 10}}});
        await j('PUT', `/api/processors/${ids.procId}/cvts/${boxB}`, {beachId: sl.id});
        results.located = await rebuild();
        results.boxBeaches = [app._dockFindCvt(boxA).cvt.beachId, app._dockFindCvt(boxB).cvt.beachId];
        results.where = [app.pullLocationOf(app._dockFindCvt(boxA).cvt), app.pullLocationOf(app._dockFindCvt(boxB).cvt)];
        results.known = app.pullKnownLocations();
        const c = app.project.layers.find(l => l.id === ids.c);
        results.centerLabel = app.getPortLabelText(c, 1, 'primary');
        results.aLabel = app.getPortLabelText(app.project.layers.find(l => l.id === ids.a), 1, 'primary');
        results.snakeName = app._dockFindCvt(boxA).cvt.snakes[0].name;
        return results;
    }""" % REBUILD_JS, ids)
    # no beach: box A's gear row and fiber sit with the first screen it
    # delivers (WALL-A -> SR Beach); box B delivers nothing and is not listed
    no = _by_name(out['noLocation']['positions'])
    assert [p['name'] for p in out['noLocation']['positions']] == ['SR Beach', 'CENTER']
    assert [r for r in _rows(no['SR Beach']['rows']) if r[0] == 'CVT10'] == [('CVT10', 'EA', 1, 'A', '')]
    assert not [r for r in _rows(no['CENTER']['rows']) if r[0] == 'CVT10']
    assert out['knownBefore'] == [], 'a project with no beaches knows no location'
    # the beaches: two, in the order they were made, one spelling each
    sl_id, sr_id = out['sl'], out['sr']
    assert out['beaches'] == [[sl_id, 'SL Beach'], [sr_id, 'SR Beach']] and sl_id != sr_id, out['beaches']
    assert out['again'] == [200, False, {'id': sl_id, 'name': 'SL Beach'}, 2], out['again']
    assert out['bad'] == [400, 'Unknown beach'], out['bad']
    assert out['boxBeaches'] == [sl_id, sl_id] and out['where'] == ['SL Beach', 'SL Beach'], out
    # located: the beaches lead in their order, the loose screen last
    pos = _by_name(out['located']['positions'])
    assert [p['name'] for p in out['located']['positions']] == ['SL Beach', 'SR Beach', 'CENTER']
    assert [p['key'] for p in out['located']['positions']] == [f'beach:{sl_id}', f'beach:{sr_id}', f"layer:{ids['c']}"]
    sl = pos['SL Beach']
    assert sl['memberIds'] == [] and sl['layerIds'] == [ids['a'], ids['b'], ids['c']]
    # the group SR Beach folds into the beach of its name: its members are
    # the beach's own
    assert pos['SR Beach']['memberIds'] == [ids['a'], ids['b']] and pos['SR Beach']['location'] == 'SR Beach'
    assert _rows(sl['rows']) == [
        ('12 Tac Fiber', "250'", 1, 'CVT10 A', ''),
        ('CVT10', 'EA', 2, 'A, B', ''),
        ('Data Jump', "6'", 8, 'WALL-A, WALL-B, CENTER', ''),
        ('Ether-con', "10'", 1, out['aLabel'], f"ext · {out['snakeName']}"),
        ('Ether-con', "50'", 1, out['centerLabel'], ''),
        ('Ether-con Barrel', 'EA', 1, out['aLabel'], ''),
        ('Ether-con Snake', "100'", 1, out['snakeName'], '2-way'),
    ]
    assert all(r['side'] == 'data' for r in sl['rows'])
    assert _rows(pos['SR Beach']['rows']) == [
        ('12 way', 'EA', 1, 'SR', ''),
        ('Multi', "100'", 1, 'SR 2', ''),
        ('Multi', "125'", 1, 'SR 1', ''),
        ('Tru-1', "6'", 1, 'SR2-1', ''),
        ('Tru-1', "10'", 2, 'SR1-1, SR1-2', ''),
        ('Tru-1 Breakout', 'EA', 2, 'SR 1-2', ''),
        ('Tru-1 Power Jump', "6'", 2, 'WALL-A, WALL-B', ''),
    ]
    assert _rows(pos['CENTER']['rows']) == [
        ('Edison 2fer', 'EA', 1, ids['centerLabel'], ''),
        ('Tru-1 Power Jump', "6'", 12, 'CENTER', ''),
    ]
    # the processor's hardware list carries both boxes' gear rows
    hw = {(h['kind'],): _rows(h['rows']) for h in out['located']['hardware'] if h['kind'] == 'processor'}
    assert ('CVT10', 'EA', 2, 'A, B', '') in hw[('processor',)]
    # every location the project knows: the beach names, in beach order
    assert out['known'] == ['SL Beach', 'SR Beach']
    assert ids['errors'] == []


def _open_gear(pg, pop_id):
    """Open the tray gear `pop_id` (box-<id>, distro-<id>) if its popover
    is not already showing; True when it is up."""
    return pg.evaluate("""(popId) => {
        const app = window.app;
        const up = () => {
            const pop = document.getElementById('hw-gear-popover');
            return !!(pop && pop.style.display !== 'none');
        };
        if (up() && app._hwPopover && app._hwPopover.id === popId) return true;
        const gear = document.querySelector(`[data-hwpop="${popId}"]`);
        if (!gear) return false;
        gear.click();
        return up();
    }""", pop_id)


def _beach_picker(pg, key):
    """The Beach picker keyed `key` in the open gear popover: its value,
    its [value, text] options, and where it sits."""
    return pg.evaluate("""(key) => {
        const sel = document.querySelector(`[data-lrd-field="${key}"]`);
        return { found: !!sel, tag: sel && sel.tagName,
                 inPop: !!(sel && sel.closest('#hw-gear-popover')), value: sel && sel.value,
                 options: sel ? [...sel.options].map(o => [o.value, o.textContent]) : null,
                 labels: [...document.querySelectorAll('#hw-gear-popover label')].map(l => l.textContent),
                 typed: [...document.querySelectorAll('#hw-gear-popover [data-lrd-field]')]
                     .map(el => el.dataset.lrdField).filter(k => /-location-/.test(k)),
                 index: window.app.historyIndex };
    }""", key)


def _box_beach(pg, box_id):
    return pg.evaluate("(bid) => { const f = window.app._dockFindCvt(bid); return f ? (f.cvt.beachId || null) : 'gone'; }", box_id)


def _wait_box_beach(pg, box_id, beach_id):
    """The resolved tree follows a project round-trip; wait for it."""
    waited, got = 0, None
    while waited < 4000:
        got = _box_beach(pg, box_id)
        if got == beach_id:
            break
        pg.wait_for_timeout(200)
        waited += 200
    return got


def test_the_box_gear_has_a_beach_picker_with_the_projects_beaches(page):
    """The box gear popover carries the Beach picker keyed
    processor-cvt-beach-<id> (no typed Location field): a <select> of the
    project's beaches in THEIR order between a blank entry and "+ New
    beach…". Picking a beach PUTs beachId and takes one 'Set Box Beach'
    entry; "+ New beach…" prompts for a name, makes the beach and picks it
    as ONE entry, so one undo takes back both the pick and the beach. The
    distro gear's picker (distro-beach-<id>) offers the same list."""
    pg, ids = page
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(400)
    # The boxes above were made by raw fetches (no history entry): take the
    # project as served as the floor of the history, so undo below takes
    # back a pick and not the boxes or the beaches.
    pg.evaluate("""async () => {
        const app = window.app;
        app.project = await (await fetch('/api/project')).json();
        app.dedupeProjectLayers('pull_locations_gear');
        await app.refreshProcessors(); await app.refreshPortAssignment();
        app.renderLayers(); app.renderHardwareDock();
        app.resetHistory('Beaches Seed');
    }""")
    pg.wait_for_timeout(300)
    beaches = pg.evaluate("() => window.app.getBeaches().map(b => [b.id, b.name])")
    assert [n for _, n in beaches] == ['SL Beach', 'SR Beach'], beaches
    sl_id, sr_id = beaches[0][0], beaches[1][0]
    box_b = pg.evaluate("() => window.app._processorsResolved[0].slots[0].card.cvts[1].id")
    assert _box_beach(pg, box_b) == sl_id
    assert _open_gear(pg, f'box-{box_b}'), 'the box gear did not open'
    pg.wait_for_timeout(300)
    key = f'processor-cvt-beach-{box_b}'
    out = _beach_picker(pg, key)
    assert out['found'] and out['inPop'] and out['tag'] == 'SELECT', out
    assert out['value'] == sl_id, out
    assert out['options'] == [['', '— no beach —'], [sl_id, 'SL Beach'], [sr_id, 'SR Beach'],
                              ['__new_beach__', '+ New beach…']], out['options']
    assert 'Beach' in out['labels'] and out['typed'] == [], out
    # pick SR Beach: one 'Set Box Beach' entry, the box's beachId follows
    pg.locator(f'[data-lrd-field="{key}"]').select_option(sr_id)
    pg.wait_for_timeout(900)
    assert _wait_box_beach(pg, box_b, sr_id) == sr_id
    st = pg.evaluate("""() => {
        const app = window.app;
        return { action: app.history[app.historyIndex].action, index: app.historyIndex,
                 known: app.pullKnownLocations(), beaches: app.getBeaches().map(b => b.name) };
    }""")
    assert st['action'] == 'Set Box Beach' and st['index'] == out['index'] + 1, st
    assert st['known'] == ['SL Beach', 'SR Beach'] and st['beaches'] == ['SL Beach', 'SR Beach'], st
    # "+ New beach…": the prompt names it, the beach is made at the end of
    # the list and picked - ONE entry for the gesture
    assert _open_gear(pg, f'box-{box_b}'), 'the box gear did not open again'
    pg.wait_for_timeout(300)
    assert _beach_picker(pg, key)['value'] == sr_id
    pg.once('dialog', lambda d: d.accept('Dimmer Beach'))
    pg.locator(f'[data-lrd-field="{key}"]').select_option('__new_beach__')
    pg.wait_for_timeout(1200)
    st = pg.evaluate("""() => {
        const app = window.app;
        return { action: app.history[app.historyIndex].action, index: app.historyIndex,
                 known: app.pullKnownLocations(), beaches: app.getBeaches().map(b => [b.id, b.name]) };
    }""")
    assert [n for _, n in st['beaches']] == ['SL Beach', 'SR Beach', 'Dimmer Beach'], st
    dimmer_id = st['beaches'][2][0]
    assert dimmer_id not in (sl_id, sr_id)
    assert _wait_box_beach(pg, box_b, dimmer_id) == dimmer_id
    assert st['action'] == 'Set Box Beach' and st['index'] == out['index'] + 2, st
    assert st['known'] == ['SL Beach', 'SR Beach', 'Dimmer Beach'], st
    # the picker on screen shows the new beach selected, listed last
    if _open_gear(pg, f'box-{box_b}'):
        pg.wait_for_timeout(300)
        now = _beach_picker(pg, key)
        assert now['value'] == dimmer_id and now['options'][1:-1] == [
            [sl_id, 'SL Beach'], [sr_id, 'SR Beach'], [dimmer_id, 'Dimmer Beach']], now
    # one undo takes back the pick AND the beach it made
    pg.evaluate('() => window.app.undo()')
    assert _wait_box_beach(pg, box_b, sr_id) == sr_id
    st = pg.evaluate("""() => {
        const app = window.app;
        return { index: app.historyIndex, beaches: app.getBeaches().map(b => b.name), known: app.pullKnownLocations() };
    }""")
    assert st['index'] == out['index'] + 1 and st['beaches'] == ['SL Beach', 'SR Beach'], st
    assert st['known'] == ['SL Beach', 'SR Beach'], st
    # the distro gear's picker carries the same list (SR sits on no beach)
    pg.keyboard.press('Escape')
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(400)
    pg.evaluate("() => { window.app.renderHardwareDock(); }")
    pg.wait_for_timeout(300)
    assert _open_gear(pg, f"distro-{ids['distroId']}"), 'the distro gear did not open'
    pg.wait_for_timeout(300)
    d = _beach_picker(pg, f"distro-beach-{ids['distroId']}")
    assert d['found'] and d['inPop'] and d['tag'] == 'SELECT' and d['value'] == '', d
    assert d['options'] == [['', '— no beach —'], [sl_id, 'SL Beach'], [sr_id, 'SR Beach'],
                            ['__new_beach__', '+ New beach…']], d['options']
    assert 'Beach' in d['labels'] and d['typed'] == [], d
    pg.keyboard.press('Escape')
    # the boxes and the beaches go; the card's own cables come back and the
    # group SR Beach is a position of its own again
    left = _clear_boxes_and_beaches(pg, ids)
    assert left['names'] == ['SR Beach', 'CENTER'] and left['keys'] == ['g1', f"layer:{ids['c']}"], left
    assert left['beaches'] == [] and left['boxes'] == 0, left
    assert ids['errors'] == []


def _clear_boxes_and_beaches(pg, ids):
    """Every breakout box off card SR and every beach off the project, the
    app re-read from the server: the show of the fixture again (the group
    SR Beach and the loose CENTER). Returns the positions it leaves."""
    return pg.evaluate("""async (ids) => {
        const app = window.app;
        const j = (url) => fetch(url).then(r => r.json());
        const boxes = ((await j('/api/processors')).processors.find(p => p.id === ids.procId) || {slots: []})
            .slots.flatMap(s => (s && s.card && s.card.cvts) || []).map(c => c.id);
        for (const box of boxes) await fetch(`/api/processors/${ids.procId}/cvts/${box}`, {method: 'DELETE'});
        for (const b of (await j('/api/beaches')).beaches || []) await fetch(`/api/beaches/${b.id}`, {method: 'DELETE'});
        app.project = await j('/api/project');
        app.dedupeProjectLayers('pull_locations_clear');
        await app.refreshProcessors(); await app.refreshPortAssignment();
        app.renderLayers(); app.renderHardwareDock();
        app._circuitTailCache = null;
        const list = app.buildPullList();
        return { names: list.positions.map(p => p.name), keys: list.positions.map(p => p.key),
                 beaches: app.getBeaches(), boxes: app._processorsResolved[0].slots[0].card.cvts.length };
    }""", ids)


def test_a_distro_is_named_by_its_holes_one_to_nine_boxes(page):
    """1-2 boxes "12 way", 3-4 "24 way", 5-6 "36 way", 7-8 "48 way"; a
    ninth keeps "48 way" and says "9 multis" in Notes - the user's table
    ends at 8 and nothing larger is assumed. A 54-wide single-row screen
    packed by column, one 2000 W cabinet per 10 A circuit, gives nine
    socas to put on a fresh distro (DIM - a name ending in a digit would
    fold in the label) one at a time."""
    pg, ids = page
    # the fixture's show, whatever the test before left (its boxes, its beaches)
    slate = _clear_boxes_and_beaches(pg, ids)
    assert slate['names'] == ['SR Beach', 'CENTER'], slate
    assert pg.evaluate("() => [1,2,3,4,5,6,7,8,9].map(n => window.app.pullDistroWayType(n))") == [
        '12 way', '12 way', '24 way', '24 way', '36 way', '36 way', '48 way', '48 way', '48 way']
    out = pg.evaluate("""async () => {
        const app = window.app;
        const j = (method, url, body) => fetch(url, {method,
            headers: {'Content-Type': 'application/json'},
            body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
        await j('POST', '/api/layer/add', {name: 'TALL', columns: 54, rows: 1, cabinet_width: 100, cabinet_height: 100,
                                           powerVoltage: 208, powerAmperage: 10, panelWatts: 2000,
                                           powerFlowPattern: 'tl-v', powerOrganized: true, flowPattern: 'tl-h',
                                           processorType: 'novastar-armor', offset_x: 3000});
        app.project = await j('GET', '/api/project');
        app.dedupeProjectLayers('pull_locations_tall');
        const t = app.project.layers.find(l => l.name === 'TALL');
        app.selectLayer(t);
        // the circuits are worked out on a render
        app.renderLayers(); window.canvasRenderer.render();
        const d2 = app.addDistro({name: 'DIM'});
        const socas = app.getSocaPlan(t).length;
        const steps = [];
        for (let k = 1; k <= 9 && k <= socas; k++) {
            app.setSocaDistro(t, k, d2.id); app.setSocaNumber(t, k, k);
            app._circuitTailCache = null;
            const list = app.buildPullList();
            const pos = list.positions.find(p => p.name === 'TALL');
            const row = pos.rows.find(r => /way$/.test(r.type));
            steps.push([k, row.type, row.qty, row.label, row.notes]);
        }
        t.visible = false;
        app._circuitTailCache = null;
        const gone = app.buildPullList().positions.map(p => p.name);
        app.renderLayers();
        return { socas, steps, gone };
    }""")
    assert out['socas'] == 9, out
    assert out['steps'] == [
        [1, '12 way', 1, 'DIM', ''], [2, '12 way', 1, 'DIM', ''],
        [3, '24 way', 1, 'DIM', ''], [4, '24 way', 1, 'DIM', ''],
        [5, '36 way', 1, 'DIM', ''], [6, '36 way', 1, 'DIM', ''],
        [7, '48 way', 1, 'DIM', ''], [8, '48 way', 1, 'DIM', ''],
        [9, '48 way', 1, 'DIM', '9 multis'],
    ]
    assert out['gone'] == ['SR Beach', 'CENTER']
    assert ids['errors'] == []
