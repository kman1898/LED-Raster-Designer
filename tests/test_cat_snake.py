"""A Cat snake carries XD links the way a TAC carries fiber.

The owner (2026-11-18): "We need to be able to use a Cat snake for XD
boxes. Since those accept cat cables. Mind you CVT and new XD boxes dont
accept cat cables."

- A Cat snake is one more cable of the show's list, {kind: 'cat-snake',
  copper: 'Cat6A' | 'Cat6' | 'Cat5e', strands: <channels>, ft?, name},
  made once from an XD link (New Cat snake) and picked again on other XDs.
  Each link takes ONE channel, the next free one unless another is picked;
  a full snake is refused on the server and reads "full" in the picker.
- Its default name is its kind, "snake" and a letter, "Cat6A snake A",
  lettered like TACs; a default follows a kind change, a typed name stays.
- Only a box whose catalog entry takes Cat cable (copperLinks, the XD)
  takes one: an XD-S, an XD-T and every CVT are refused, and a link stored
  on one by hand is dropped on open.
- A backup link (X2 off the backup processor) picks per link: sent with
  no cable it follows its primary's snake to the next free channel, and it
  can move to another snake.
- Past its kind's 10G length it warns, as a single Cat link does, and is
  never refused.
- It prints wherever a TAC prints: the box's Fiber row (a "Ch 1" chip),
  the pull sheet once, the binder's Fiber connections, a CHANNEL map, the
  Cat snake page (test_binder_cat_snake_page.py), the box summary and the
  Data Wiring inputs. No colors, no
  polarity, no swap, no extension, and never the word "copper".
- Shows with no snake load exactly as before.

Run locally (each session takes its own free port):
    python -m pytest tests/test_cat_snake.py -v --browser chromium
"""

import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))

import processor_catalog as catalog  # noqa: E402

SHOTS = os.environ.get('CAT_SNAKE_SHOTS')
H16 = 'novastar-card-h-16xrj45-2xfiber'


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# ── helpers ──────────────────────────────────────────────────────────────

def _ok(resp, code=200):
    assert resp.status_code == code, resp.get_data(as_text=True)[:400]
    return resp.get_json()


def _refused(resp):
    assert resp.status_code == 400, resp.get_data(as_text=True)[:400]
    return resp.get_json()['error']


def _boxes(client):
    out = {}
    for proc in client.get('/api/processors').get_json()['processors']:
        for slot in proc['slots']:
            for box in (slot.get('card') or {}).get('cvts') or []:
                out[box['id']] = box
    return out


def _links(client, box_id):
    return _boxes(client)[box_id].get('fiberLinks') or {}


def _cables(client):
    return client.get('/api/project').get_json().get('fiberCables') or []


def _cable(client, cable_id):
    return next(c for c in _cables(client) if c['id'] == cable_id)


def _sx40(client, backup=False):
    st = _ok(client.post('/api/processors', json={'deviceId': 'brompton-sx40'}), 201)
    proc = st['processors'][-1]
    if backup:
        _ok(client.put(f"/api/processors/{proc['id']}", json={'backupUnit': True}))
    return proc['id'], [b['id'] for b in proc['slots'][0]['card']['cvts']]


def _cvt10(client):
    st = _ok(client.post('/api/processors', json={'deviceId': 'novastar-h9'}), 201)
    pid = st['processors'][-1]['id']
    st = _ok(client.put(f'/api/processors/{pid}/slots/0', json={'deviceId': H16}))
    cid = next(p for p in st['processors'] if p['id'] == pid)['slots'][0]['card']['id']
    st = _ok(client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                         json={'deviceId': 'novastar-cvt10', 'pair': False}), 201)
    card = next(p for p in st['processors'] if p['id'] == pid)['slots'][0]['card']
    return pid, card['cvts'][0]['id']


def _xd_s(client):
    st = _ok(client.post('/api/processors', json={'deviceId': 'brompton-sq200'}), 201)
    pid = st['processors'][-1]['id']
    st = _ok(client.put(f'/api/processors/{pid}/slots/0', json={'deviceId': 'brompton-card-qd-s'}))
    cid = next(p for p in st['processors'] if p['id'] == pid)['slots'][0]['card']['id']
    st = _ok(client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                         json={'deviceId': 'brompton-xd-s'}), 201)
    card = next(p for p in st['processors'] if p['id'] == pid)['slots'][0]['card']
    return pid, card['cvts'][-1]['id']


def _snake(client, channels=4, copper='Cat6A', link=None, **kw):
    body = dict(kind='cat-snake', copper=copper, strands=channels, **kw)
    if link:
        body['link'] = link
    return client.post('/api/fiber-cables', json=body)


def _made(client, *a, **kw):
    return _ok(_snake(client, *a, **kw), 201)['fiberCables'][-1]


def _link(client, pid, box, key, body):
    return client.put(f'/api/processors/{pid}/cvts/{box}/fiber-links/{key}', json=body)


def _card_link(client, pid, card, key, body):
    return client.put(f'/api/processors/{pid}/cards/{card}/fiber-links/{key}', json=body)


# ── the server ──────────────────────────────────────────────────────────

def test_a_snake_is_made_on_an_xd_link_and_named_by_its_kind(client):
    pid, xds = _sx40(client)
    a = _made(client, 4, link={'boxId': xds[0], 'key': 'p1'}, ft=150)
    assert {k: a[k] for k in ('kind', 'copper', 'strands', 'ft', 'name')} == {
        'kind': 'cat-snake', 'copper': 'Cat6A', 'strands': 4, 'ft': 150, 'name': 'Cat6A snake A'}
    # stored plainly: no colors, ends or polarity on a snake
    raw = next(c for c in client.get('/api/project').get_json()['fiberCables'] if c['id'] == a['id'])
    assert raw == {'id': a['id'], 'kind': 'cat-snake', 'copper': 'Cat6A', 'strands': 4,
                   'ft': 150, 'name': 'Cat6A snake A'}
    # the link takes channel 1, stored as its one strand
    assert _links(client, xds[0]) == {'p1': {'cable': a['id'], 'strands': [1]}}
    # lettered per kind, the way TACs are
    b = _made(client, 6, link={'boxId': xds[1], 'key': 'p1'})
    c = _made(client, 2, copper='Cat6', link={'boxId': xds[2], 'key': 'p1'})
    assert (b['name'], c['name']) == ('Cat6A snake B', 'Cat6 snake A')
    # a typed name is kept through a kind change; a default follows the kind
    _ok(client.put(f"/api/fiber-cables/{b['id']}", json={'copper': 'Cat5e'}))
    assert _cable(client, b['id'])['name'] == 'Cat5e snake B'
    _ok(client.put(f"/api/fiber-cables/{b['id']}", json={'name': '  SL rack '}))
    _ok(client.put(f"/api/fiber-cables/{b['id']}", json={'copper': 'Cat6'}))
    assert (_cable(client, b['id'])['name'], _cable(client, b['id'])['copper']) == ('SL rack', 'Cat6')
    # a blank name hands the default back
    _ok(client.put(f"/api/fiber-cables/{b['id']}", json={'name': ''}))
    assert _cable(client, b['id'])['name'] == 'Cat6 snake B'
    # the words it prints under, and its channel names
    assert catalog.fiber_cable_type_text(a) == 'Cat6A snake · 4 channel'
    assert catalog.fiber_strand_name(3, a) == 'Ch 3'
    # a snake has a Cat kind, never colors, ends, polarity or an extension
    assert 'one of Cat6A, Cat6, Cat5e' in _refused(_snake(client, 4, copper='Cat7'))
    assert 'one of Cat6A, Cat6, Cat5e' in _refused(
        client.post('/api/fiber-cables', json={'kind': 'cat-snake', 'strands': 4}))
    assert 'numbered' in _refused(client.put(f"/api/fiber-cables/{a['id']}", json={'labels': 'numbers'}))
    assert 'Only a TAC' in _refused(client.put(f"/api/fiber-cables/{a['id']}", json={'connector': 'ST'}))
    assert 'Only an MTP' in _refused(client.put(f"/api/fiber-cables/{a['id']}", json={'polarity': 'B'}))
    assert 'Cat snake' in _refused(_link(client, pid, xds[0], 'p1', {'extension': {}}))
    tac = _ok(client.post('/api/fiber-cables', json={'kind': 'tac', 'strands': 12}), 201)['fiberCables'][-1]
    assert 'Only a Cat snake' in _refused(client.put(f"/api/fiber-cables/{tac['id']}", json={'copper': 'Cat6'}))
    assert 'channel count' in _refused(_snake(client, 0))


def test_each_link_takes_the_next_free_channel_and_may_change_it(client):
    pid, xds = _sx40(client)
    s = _made(client, 4, link={'boxId': xds[0], 'key': 'p1'})
    _ok(_link(client, pid, xds[1], 'p1', {'cable': s['id']}))
    assert _links(client, xds[1])['p1'] == {'cable': s['id'], 'strands': [2]}
    # moved to channel 4 by hand; the next box takes the lowest free one
    _ok(_link(client, pid, xds[1], 'p1', {'cable': s['id'], 'strands': [4]}))
    _ok(_link(client, pid, xds[2], 'p1', {'cable': s['id']}))
    assert _links(client, xds[2])['p1']['strands'] == [2]
    # a channel already held is refused, and so is one past the count or two
    assert _refused(_link(client, pid, xds[3], 'p1', {'cable': s['id'], 'strands': [1]})) == (
        'Cat6A snake A channel 1 is already used by XD A X1. A channel carries one link.')
    assert _refused(_link(client, pid, xds[3], 'p1', {'cable': s['id'], 'strands': [5]})) == (
        'Cat6A snake A has channels 1-4. There is no channel 5.')
    assert _refused(_link(client, pid, xds[3], 'p1', {'cable': s['id'], 'strands': [3, 4]})) == (
        'XD D X1 takes 1 channel of a Cat snake.')
    # the count cannot go under a channel in use
    assert 'Channel 4 is in use' in _refused(client.put(f"/api/fiber-cables/{s['id']}", json={'strands': 3}))
    # clearing the last link lets go of the snake, as a TAC goes
    for b in xds[:3]:
        _ok(_link(client, pid, b, 'p1', {'cable': None}))
    assert s['id'] not in [c['id'] for c in _cables(client)]


def test_a_full_snake_is_refused(client):
    pid, xds = _sx40(client)
    s = _made(client, 2, link={'boxId': xds[0], 'key': 'p1'})
    _ok(_link(client, pid, xds[1], 'p1', {'cable': s['id']}))
    assert _refused(_link(client, pid, xds[2], 'p1', {'cable': s['id']})) == (
        'Cat6A snake A is full: every channel is in use.')
    assert 'fiberLinks' not in _boxes(client)[xds[2]]
    # a channel more makes room
    _ok(client.put(f"/api/fiber-cables/{s['id']}", json={'strands': 3}))
    _ok(_link(client, pid, xds[2], 'p1', {'cable': s['id']}))
    assert _links(client, xds[2])['p1']['strands'] == [3]


def test_only_a_box_that_takes_cat_cable_takes_a_snake(client):
    pid, xds = _sx40(client)
    s = _made(client, 4, link={'boxId': xds[0], 'key': 'p1'})
    hid, cvt = _cvt10(client)
    before = [c['id'] for c in _cables(client)]
    # a CVT is refused, and nothing is left behind by a refused New
    assert _refused(_snake(client, 4, link={'boxId': cvt, 'key': 'p1'})) == (
        'CVT10-S takes fiber only on its links. A Cat snake is offered on an XD.')
    assert [c['id'] for c in _cables(client)] == before
    assert _refused(_link(client, hid, cvt, 'p1', {'cable': s['id']})) == (
        'CVT10-S takes fiber only on its links. A Cat snake is offered on an XD.')
    # so is an XD-S
    qid, xds_box = _xd_s(client)
    assert 'XD-S takes fiber only' in _refused(_link(client, qid, xds_box, 'p1', {'cable': s['id']}))
    assert not catalog.get_device('brompton-xd-s').get('copperLinks')
    assert not catalog.get_device('brompton-xd-t').get('copperLinks')
    # a snake link put on a CVT by hand (a file edited outside) goes on open
    project = client.get('/api/project').get_json()
    for proc in project['processors']:
        for slot in proc['slots']:
            for box in (slot.get('card') or {}).get('cvts') or []:
                if box['id'] == cvt:
                    box['fiberLinks'] = {'p1': {'cable': s['id'], 'strands': [3]}}
    _ok(client.put('/api/project', json=project))
    assert 'fiberLinks' not in _boxes(client)[cvt]
    assert _links(client, xds[0])['p1'] == {'cable': s['id'], 'strands': [1]}


def test_a_backup_link_picks_per_link(client):
    pid, xds = _sx40(client, backup=True)
    s = _made(client, 4, link={'boxId': xds[0], 'key': 'p1'})
    # X2 sent with no cable follows its primary's snake to the next channel
    _ok(_link(client, pid, xds[0], 'b1', {}))
    assert _links(client, xds[0])['b1'] == {'cable': s['id'], 'strands': [2]}
    # and can move to another snake of its own
    t = _made(client, 2, copper='Cat6')
    _ok(_link(client, pid, xds[0], 'b1', {'cable': t['id']}))
    assert _links(client, xds[0])['b1'] == {'cable': t['id'], 'strands': [1]}
    # a primary's snake with no channel left is said, not taken
    _ok(_link(client, pid, xds[1], 'p1', {'cable': s['id']}))
    _ok(_link(client, pid, xds[2], 'p1', {'cable': s['id']}))
    _ok(_link(client, pid, xds[3], 'p1', {'cable': s['id']}))
    assert _refused(_link(client, pid, xds[1], 'b1', {})) == 'Cat6A snake A is full: every channel is in use.'


def test_past_the_kinds_10g_length_it_is_kept_never_refused(client):
    pid, xds = _sx40(client)
    s = _made(client, 4, copper='Cat5e', ft=250, link={'boxId': xds[0], 'key': 'p1'})
    assert (s['copper'], s['ft']) == ('Cat5e', 250)
    _ok(client.put(f"/api/fiber-cables/{s['id']}", json={'ft': 400}))
    assert _cable(client, s['id'])['ft'] == 400
    assert catalog.copper_link_max_ft('Cat5e') < 250


def test_an_old_show_loads_as_before_and_a_snake_round_trips(client):
    """A show from before the snake (a TAC, a single Cat link) opens byte
    for byte the same; one with a snake saves and opens the same too."""
    pid, xds = _sx40(client)
    _ok(_link(client, pid, xds[0], 'p1', {'copper': 'Cat6A', 'ft': 150}))
    tac = _ok(client.post('/api/fiber-cables', json={'kind': 'tac', 'strands': 12, 'ft': 500,
                                                     'link': {'boxId': xds[1], 'key': 'p1'}}), 201)
    old = client.get('/api/project').get_json()
    assert not [c for c in old.get('fiberCables') or [] if c.get('kind') == 'cat-snake']
    _ok(client.put('/api/project', json=copy.deepcopy(old)))
    again = client.get('/api/project').get_json()
    assert again['processors'] == old['processors']
    assert again['fiberCables'] == old['fiberCables']
    assert catalog.settle_fiber(copy.deepcopy(again)) is False
    assert tac['fiberCables'][-1]['kind'] == 'tac'
    # a snake saved and opened again is the same snake on the same channels
    s = _made(client, 4, link={'boxId': xds[2], 'key': 'p1'}, ft=90)
    _ok(_link(client, pid, xds[3], 'p1', {'cable': s['id']}))
    saved = client.get('/api/project').get_json()
    _ok(client.put('/api/project', json=copy.deepcopy(saved)))
    opened = client.get('/api/project').get_json()
    assert opened['processors'] == saved['processors']
    assert opened['fiberCables'] == saved['fiberCables']
    assert catalog.settle_fiber(copy.deepcopy(opened)) is False


def test_an_8_fiber_mtp_on_9_to_12_beside_a_snake_survives_settle(client):
    """settle_fiber holds each cable to its own strands: a snake beside an
    8 fiber MTP (strands 1-4 and 9-12) never drops the MTP's links on 9-12,
    and the show opens and settles the same."""
    pid, xds = _sx40(client)
    s = _made(client, 4, link={'boxId': xds[0], 'key': 'p1'})
    hid, box = _cvt10(client)
    hid2, box2 = _cvt10(client)
    mtp = _ok(client.post('/api/fiber-cables', json={'kind': 'mtp', 'strands': 8,
                                                     'link': {'boxId': box, 'key': 'p1'}}), 201)['fiberCables'][-1]
    _ok(_link(client, hid, box, 'p1', {'cable': mtp['id'], 'strands': [9, 10]}))
    _ok(_link(client, hid2, box2, 'p1', {'cable': mtp['id'], 'strands': [11, 12]}))
    project = client.get('/api/project').get_json()
    assert catalog.settle_fiber(copy.deepcopy(project)) is False
    _ok(client.put('/api/project', json=copy.deepcopy(project)))
    assert _links(client, box)['p1'] == {'cable': mtp['id'], 'strands': [9, 10]}
    assert _links(client, box2)['p1'] == {'cable': mtp['id'], 'strands': [11, 12]}
    assert _links(client, xds[0])['p1'] == {'cable': s['id'], 'strands': [1]}


def test_a_snake_with_no_links_changes_its_channel_count(client):
    """A snake made and not yet picked (no link holds a channel) takes any
    count, up or down, without a server error."""
    s = _made(client, 4)
    _ok(client.put(f"/api/fiber-cables/{s['id']}", json={'strands': 2}))
    assert _cable(client, s['id'])['strands'] == 2
    _ok(client.put(f"/api/fiber-cables/{s['id']}", json={'strands': 6}))
    assert _cable(client, s['id'])['strands'] == 6
    assert 'channel count' in _refused(client.put(f"/api/fiber-cables/{s['id']}", json={'strands': 0}))


def test_a_cat_link_on_a_fiber_only_box_is_refused_in_plain_words(client):
    hid, cvt = _cvt10(client)
    assert _refused(_link(client, hid, cvt, 'p1', {'copper': 'Cat6A'})) == (
        'CVT10-S takes fiber only on its links. A Cat cable is offered on an XD.')


def test_making_and_editing_a_snake_is_logged_with_its_values(client, monkeypatch):
    import routes_processors
    seen = []
    monkeypatch.setattr(routes_processors, 'log_event', lambda a, d=None, **k: seen.append((a, d)))
    pid, xds = _sx40(client)
    s = _made(client, 4, copper='Cat6', ft=120, link={'boxId': xds[0], 'key': 'p1'})
    add = [d for a, d in seen if a == 'fiber_cable_add']
    assert add == [{'id': s['id'], 'kind': 'cat-snake', 'link': {'boxId': xds[0], 'key': 'p1'},
                    'copper': 'Cat6', 'channels': 4, 'ft': 120}], add
    _ok(client.put(f"/api/fiber-cables/{s['id']}", json={'strands': 6, 'ft': 90, 'copper': 'Cat5e'}))
    upd = [d for a, d in seen if a == 'fiber_cable_update']
    assert len(upd) == 1 and sorted(upd[0]['changed']) == ['copper', 'ft', 'strands'], upd
    assert {k: upd[0][k] for k in ('id', 'values')} == {
        'id': s['id'], 'values': {'channels': 6, 'ft': 90, 'copper': 'Cat5e'}}, upd


# ── the browser ─────────────────────────────────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from conftest import settled  # noqa: E402

# WALL, a Brompton wall on an SX40 named WALL SR with its backup processor
# on (each XD has X1 and X2); an H9 with a CVT10 on its fiber card.
SEED_JS = """async () => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.fiberCables;
    delete proj.pullSheetEdits;
    await j('PUT', '/api/project', proj);
    const wall = await j('POST', '/api/layer/add', {name: 'WALL', columns: 12, rows: 30,
                                                     cabinet_width: 200, cabinet_height: 200});
    await j('PUT', `/api/layer/${wall.id}`, {processorType: 'brompton'});
    let st = await j('POST', '/api/processors', {deviceId: 'brompton-sx40', name: 'WALL SR'});
    const sx = st.processors[0];
    await j('PUT', `/api/processors/${sx.id}`, {backupUnit: true});
    const xds = sx.slots[0].card.cvts.map(b => b.id);
    st = await j('POST', '/api/processors', {deviceId: 'novastar-h9'});
    const h9 = st.processors[st.processors.length - 1].id;
    st = await j('PUT', `/api/processors/${h9}/slots/0`, {deviceId: '%s'});
    const cid = st.processors.find(p => p.id === h9).slots[0].card.id;
    st = await j('POST', `/api/processors/${h9}/cards/${cid}/cvts`, {deviceId: 'novastar-cvt10', pair: false});
    const cvt = st.processors.find(p => p.id === h9).slots[0].card.cvts[0].id;
    const app = window.app;
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('cat_snake_setup');
    app.selectLayer(app.project.layers[0]);
    await app.refreshProcessors();
    await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
        {layerId: String(wall.id), cardId: sx.slots[0].card.id, lastIndex: 19});
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    for (const k of Object.keys(localStorage)) {
        if (k.startsWith('lrd_data_cable_sheet_')) {
            try { localStorage.removeItem(k); } catch (e) { /* none */ }
        }
    }
    app.renderLayers();
    app.renderHardwareDock();
    app.resetHistory('Cat Snake Seed');
    return {sx: sx.id, xds, h9, cvt, wall: wall.id};
}""" % H16

# One box's sheet opened alone; a link row's select, its chips and warning.
ROW_JS = """([boxId, key]) => {
    for (const k of Object.keys(localStorage)) {
        if (k.startsWith('lrd_data_cable_sheet_')) {
            try { localStorage.removeItem(k); } catch (e) { /* none */ }
        }
    }
    window.app._setDataCableSheetOpen({kind: 'cvt', id: boxId}, true);
    window.app.renderHardwareDock();
    const row = document.querySelector(`[data-lrd-fiber-link="${boxId}:${key}"]`);
    if (!row) return null;
    row.scrollIntoView({block: 'center'});
    const sel = row.querySelector('select');
    return {
        value: sel.value,
        options: [...sel.options].map(o => [o.value, o.textContent, o.disabled]),
        chips: [...row.querySelectorAll('.hw-dock-fiber-strand')].map(c => c.textContent),
        swatches: row.querySelectorAll('.hw-dock-fiber-swatch').length,
        warn: (row.querySelector('.hw-dock-fiber-warn') || {}).textContent || '',
        extension: !!row.querySelector('[data-lrd-field^="fiber-ext-add-"]'),
        text: row.textContent,
    };
}"""

LINK_JS = """([boxId, key]) => {
    const box = window.app.fiberBoxById(boxId);
    const l = box && box.fiberLinks && box.fiberLinks[key];
    if (!l) return null;
    const c = window.app.getFiberCable(l.cable);
    return {cable: c ? c.name : null, kind: c ? c.kind : null, strands: l.strands};
}"""

HISTORY_JS = """() => ({index: window.app.historyIndex,
    action: (window.app.history[window.app.historyIndex] || {}).action})"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 1000})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(500)
    ids = pg.evaluate(SEED_JS)
    # a processor with no screens is off the binder and the pull sheet
    # (owner, 2026-11-17): every processor here gets one
    from test_hidden_screen_binder import FEED_JS
    pg.evaluate(FEED_JS)
    pg.wait_for_timeout(1200)
    ids['errors'] = errors
    yield pg, ids
    context.close()


def _link_of(pg, box, key='p1'):
    return pg.evaluate(LINK_JS, [box, key])


def _shot(pg, selector, name):
    if not SHOTS:
        return
    os.makedirs(SHOTS, exist_ok=True)
    pg.locator(selector).first.screenshot(path=os.path.join(SHOTS, name))


def test_new_cat_snake_makes_one_on_an_xd_link(page):
    """XD A's X1 lists New Cat snake with the Cat kinds, never on the CVT;
    the step takes a kind, 2, 4 or 6 channels and a length, and makes the
    snake on the link in one request and one undo step."""
    pg, ids = page
    a = ids['xds'][0]
    row = pg.evaluate(ROW_JS, [a, 'p1'])
    values = [o[0] for o in row['options']]
    assert 'new:cat-snake' in values, row
    assert ['new:cat-snake', 'New Cat snake…', False] in row['options'], row
    assert not [o for o in row['options'] if 'copper' in o[1].lower()], row
    # the CVT10 offers no Cat snake at all
    cvt = pg.evaluate(ROW_JS, [ids['cvt'], 'p1'])
    assert not [o for o in cvt['options'] if 'snake' in o[1].lower() or o[0].startswith('cu:')], cvt
    pg.evaluate(ROW_JS, [a, 'p1'])
    before = pg.evaluate(HISTORY_JS)
    pg.locator(f'[data-lrd-field="fiber-link-cable-{a}-p1"]').select_option('new:cat-snake')
    base = f'fiber-new-{a}-p1'
    kind = pg.locator(f'[data-lrd-field="{base}-copper"]')
    kind.wait_for()
    assert kind.input_value() == 'Cat6A'
    assert [o for o in kind.locator('option').all_text_contents()] == ['Cat6A', 'Cat6', 'Cat5e']
    for n in (2, 4, 6):
        assert pg.locator(f'[data-lrd-field="{base}-strands-{n}"]').count() == 1
    pg.locator(f'[data-lrd-field="{base}-strands-4"]').click()
    ft = pg.locator(f'[data-lrd-field="{base}-ft"]')
    ft.wait_for()
    ft.fill('150')
    ft.press('Enter')
    link = settled(pg, lambda: _link_of(pg, a), lambda v: bool(v), 5000)
    assert link == {'cable': 'Cat6A snake A', 'kind': 'cat-snake', 'strands': [1]}, link
    hist = pg.evaluate(HISTORY_JS)
    assert (hist['index'], hist['action']) == (before['index'] + 1, 'New Cat snake'), hist
    row = settled(pg, lambda: pg.evaluate(ROW_JS, [a, 'p1']), lambda r: r and r['chips'] == ['Ch 1'], 5000)
    assert row['chips'] == ['Ch 1'] and row['swatches'] == 0 and not row['extension'], row
    assert "Cat6A snake A · 4 channel · 150'" in [o[1] for o in row['options']], row
    assert row['warn'] == '', row
    _shot(pg, f'[data-lrd-fiber-row="{a}"]', 'cat_snake_box_fiber_row.png')
    # undo takes the snake and the link away; redo puts them back
    pg.evaluate('() => window.app.undo()')
    assert settled(pg, lambda: _link_of(pg, a), lambda v: v is None, 5000) is None
    assert pg.evaluate('() => (window.app.project.fiberCables || []).length') == 0
    pg.evaluate('() => window.app.redo()')
    assert settled(pg, lambda: _link_of(pg, a), lambda v: bool(v), 5000) == link
    assert ids['errors'] == []


def test_a_second_xd_picks_the_snake_and_a_full_one_says_so(page):
    """XD B picks Cat6A snake A off its list and takes Ch 2; its chip moves
    it to Ch 4. Once every channel is taken, an XD's backup X2 lists the
    snake as full, first as its primary's and again in the list."""
    pg, ids = page
    a, b, c, d = ids['xds']
    if not _link_of(pg, a):
        pg.evaluate("""async (box) => { await window.app.createFiberCable({kind: 'cat-snake',
            copper: 'Cat6A', strands: 4, ft: 150, link: {boxId: box, key: 'p1'}}, 'New Cat snake'); }""", a)
        settled(pg, lambda: _link_of(pg, a), lambda v: bool(v), 5000)
    snake = pg.evaluate("() => window.app.getFiberCables()[0].id")
    pg.evaluate(ROW_JS, [b, 'p1'])
    pg.locator(f'[data-lrd-field="fiber-link-cable-{b}-p1"]').select_option(snake)
    assert settled(pg, lambda: _link_of(pg, b), lambda v: bool(v), 5000)['strands'] == [2]
    assert pg.evaluate(HISTORY_JS)['action'] == 'Set Fiber Link'
    # undo and redo the pick
    pg.evaluate('() => window.app.undo()')
    assert settled(pg, lambda: _link_of(pg, b), lambda v: v is None, 5000) is None
    pg.evaluate('() => window.app.redo()')
    assert settled(pg, lambda: _link_of(pg, b), lambda v: bool(v), 5000)['strands'] == [2]
    # the chip opens a pick of the channels, the held ones named and disabled
    row = settled(pg, lambda: pg.evaluate(ROW_JS, [b, 'p1']), lambda r: r and r['chips'] == ['Ch 2'], 5000)
    assert row['chips'] == ['Ch 2'], row
    pg.locator(f'[data-lrd-field="fiber-strand-{b}-p1-0"]').click()
    pick = pg.locator(f'[data-lrd-field="fiber-strand-pick-{b}-p1-0"]')
    pick.wait_for()
    opts = pg.evaluate("""(key) => [...document.querySelector(`[data-lrd-field="${key}"]`).options]
        .map(o => [o.textContent, o.disabled])""", f'fiber-strand-pick-{b}-p1-0')
    assert opts == [['Ch 1 · XD A · X1', True], ['Ch 2', False], ['Ch 3', False], ['Ch 4', False]], opts
    pick.select_option('4')
    assert settled(pg, lambda: _link_of(pg, b), lambda v: v['strands'] == [4], 5000)['strands'] == [4]
    assert pg.evaluate(HISTORY_JS)['action'] == 'Set Snake Channel'
    # C and D take the lowest free channels; the snake is then full
    for box in (c, d):
        pg.evaluate("""async ([box, id]) => { await window.app.setFiberLink(
            window.app.fiberBoxById(box), 'p1', {cable: id}); }""", [box, snake])
    assert settled(pg, lambda: _link_of(pg, d), lambda v: bool(v), 5000)['strands'] == [3]
    assert _link_of(pg, c)['strands'] == [2]
    row = pg.evaluate(ROW_JS, [a, 'b1'])
    full = [o for o in row['options'] if o[0] == snake]
    assert full == [[snake, "Cat6A snake A · 4 channel · 150' · same as X1 · full", True],
                    [snake, "Cat6A snake A · 4 channel · 150' · full", True]], row
    assert ids['errors'] == []


def test_the_pull_sheet_counts_the_snake_once(page):
    pg, ids = page
    rows = pg.evaluate("""() => { window.app._circuitTailCache = null;
        return JSON.parse(JSON.stringify(window.app.buildPullList())).totals
            .filter(r => /snake/.test(r.type)).map(r => [r.type, r.length, r.qty, r.label, r.notes]); }""")
    assert rows == [['Cat6A snake · 4 channel', "150'", 1, 'Cat6A snake A', '']], rows


BINDER_JS = """(ids) => {
    const app = window.app;
    const box = (id) => app.fiberBoxById(id);
    const sx = app._processorsResolved.find(p => p.id === ids.sx);
    const maps = app._bStrandMaps(sx).map(m => ({title: m.title, cols: m.cols.map(c => c.title),
        rows: m.rows.map(r => [r.cells[0], r.cells[1], r.swatch || null])}));
    const conn = app._bFiberConnectionRows(sx, 'WALL SR')
        .filter(r => r.link && r.link.cable && r.link.cable.kind === 'cat-snake')
        .map(r => r.cells.slice(1));
    // (the snake's links print on the Cat snake page, never the Fiber page)
    const page = app.binderCatSnakePage();
    const fiber = app.binderFiberPage();
    return {
        maps, conn,
        fiberSnakes: fiber.procs.flatMap(p => p.links).filter(l => /snake/.test(l.cable)).length
            + fiber.cables.filter(c => /snake/.test(c.title)).length,
        pageMaps: page.cables.map(c => c.title),
        pageLinks: page.procs.flatMap(p => p.links).filter(l => /snake/.test(l.cable))
            .map(l => [l.cable, l.atProcessor, l.atBreakout]),
        summary: app.fiberLinkSummary(box(ids.xds[0])),
        wiring: app._bwBoxInputs(box(ids.xds[1])),
        groups: (app._bBoxInputGroups(box(ids.xds[0])) || []).map(g => [g.head, g.sub, (g.strands || []).map(s => s.text)]),
    };
}"""


def test_the_binder_maps_each_channel_to_its_box_link(page):
    """The processor page's CHANNEL map puts each channel on its box and
    link; Fiber connections name the snake (its kind the first time) and
    the channel at either end; the Cat snake page (never the Fiber page),
    the box summary and the Data Wiring inputs say the same, with no color
    anywhere."""
    pg, ids = page
    out = pg.evaluate(BINDER_JS, ids)
    assert out['fiberSnakes'] == 0, out
    assert out['maps'] == [{
        'title': "Channel map · Cat6A snake A · 4 channel · 150'",
        'cols': ['channel', 'link', 'box ports'],
        'rows': [['1', 'XD A · X1', None], ['2', 'XD C · X1', None],
                 ['3', 'XD D · X1', None], ['4', 'XD B · X1', None]],
    }], out['maps']
    assert out['conn'] == [
        ['Cat6A snake A (4 channel)', 'Ch 1', 'X1 on XD A', 'Ch 1'],
        ['Cat6A snake A', 'Ch 4', 'X1 on XD B', 'Ch 4'],
        ['Cat6A snake A', 'Ch 2', 'X1 on XD C', 'Ch 2'],
        ['Cat6A snake A', 'Ch 3', 'X1 on XD D', 'Ch 3'],
    ], out['conn']
    assert "Channel map · Cat6A snake A · 4 channel · 150'" in out['pageMaps'], out
    assert ["Cat6A snake A · 4 channel · 150'", ['Ch 1'], ['Ch 1']] in out['pageLinks'], out
    assert out['summary'] == 'X1 Cat6A snake A (4 channel) Ch 1', out
    assert out['wiring'] == [{'head': 'X1', 'sub': 'Cat6A snake A (4 channel)',
                              'strands': [{'text': 'Ch 4', 'swatch': None}]}], out
    assert out['groups'] == [['X1', 'Cat6A snake A (4 channel)', ['Ch 1']]], out
    # the word snake once, and never "channels" or "ch" as a size
    texts = repr(out)
    assert 'snake A (Cat6A snake' not in texts and ' ch)' not in texts and '4 channels' not in texts, out
    # never the word copper (owner, 2026-11-07), nor a fiber strand's
    assert 'copper' not in repr(out).lower(), out
    assert not [t for t in out['pageMaps'] if t.startswith('Strand map') and 'snake' in t], out
    if SHOTS:
        data = pg.evaluate("""() => {
            const app = window.app;
            const opts = {sheet: 'tabloid', palette: 'colour', sides: {power: true, data: true},
                          scope: {kind: 'show'}, cover: true, pull: true, hardware: true,
                          fiber: true, titleBlock: true};
            const plan = app.planBinder(opts);
            const i = plan.findIndex(p => p.kind === 'processor');
            return i < 0 ? null : app.renderBinderPage(opts, i).canvas.toDataURL('image/png');
        }""")
        assert data, 'no processor sheet'
        import base64
        os.makedirs(SHOTS, exist_ok=True)
        with open(os.path.join(SHOTS, 'cat_snake_binder_channel_map.png'), 'wb') as f:
            f.write(base64.b64decode(data.split(',', 1)[1]))
    assert ids['errors'] == []


def test_past_its_10g_length_the_snake_warns_everywhere(page):
    """Made Cat5e at 150 ft, the snake's row, its pull row and its channel
    map say "Cat5e runs 98.4 ft max at 10G", the way a Cat link does; the
    default name follows the kind; undo puts it back."""
    pg, ids = page
    a = ids['xds'][0]
    snake = pg.evaluate("() => window.app.getFiberCables()[0].id")
    pg.evaluate(ROW_JS, [a, 'p1'])
    pg.locator(f'[data-lrd-field="fiber-edit-{a}-p1"]').click()
    kind = pg.locator(f'[data-lrd-field="fiber-cable-copper-{snake}"]')
    kind.wait_for()
    kind.select_option('Cat5e')
    assert settled(pg, lambda: _link_of(pg, a), lambda v: v['cable'] == 'Cat5e snake A', 5000)['cable'] \
        == 'Cat5e snake A'
    assert pg.evaluate(HISTORY_JS)['action'] == 'Set Cat Snake Kind'
    warn = 'Cat5e runs 98.4 ft max at 10G'
    row = settled(pg, lambda: pg.evaluate(ROW_JS, [a, 'p1']), lambda r: r and r['warn'] == warn, 5000)
    assert row['warn'] == warn, row
    notes = pg.evaluate("""() => { window.app._circuitTailCache = null;
        return JSON.parse(JSON.stringify(window.app.buildPullList())).totals
            .filter(r => /snake/.test(r.type)).map(r => [r.type, r.notes]); }""")
    assert notes == [['Cat5e snake · 4 channel', warn]], notes
    title = pg.evaluate("""(sx) => window.app._bStrandMaps(window.app._processorsResolved
        .find(p => p.id === sx))[0].title""", ids['sx'])
    assert title.endswith(f"150' · {warn}"), title
    pg.evaluate('() => window.app.undo()')
    assert settled(pg, lambda: _link_of(pg, a), lambda v: v['cable'] == 'Cat6A snake A', 5000)['cable'] \
        == 'Cat6A snake A'
    assert ids['errors'] == []


def test_a_metres_show_warns_in_metres(page):
    """In a metres show a Cat5e snake past its 10G length says so in
    metres, the way a single Cat link does, and its channel map says it
    after its length."""
    pg, ids = page
    out = pg.evaluate("""() => {
        const app = window.app;
        const unit = app.project.cableUnit;
        const snake = {id: 'x', kind: 'cat-snake', copper: 'Cat5e', strands: 4, ft: 31, name: 'Cat5e snake Z'};
        try {
            app.project.cableUnit = 'm';
            return [app.fiberCableOverText(snake), app._bStrandMapTitle(snake),
                    app.fiberCableOverText({...snake, ft: 30})];
        } finally {
            app.project.cableUnit = unit;
        }
    }""")
    assert out == ['Cat5e runs 30 m max at 10G',
                   'Channel map · Cat5e snake Z · 4 channel · 31 m · Cat5e runs 30 m max at 10G', ''], out
    assert ids['errors'] == []


def test_snake_words_never_say_snake_twice(page):
    """The size is "4 channel" after a name that says the snake and its
    kind, its kind kept after one that does not, and the whole "Cat6A
    snake · 4 channel" after a name that says neither."""
    pg, ids = page
    out = pg.evaluate("""() => {
        const app = window.app;
        const c = (name) => ({kind: 'cat-snake', copper: 'Cat6A', strands: 4, name});
        return [app.fiberCableTypeText(c('x')),
                app.fiberCableShortKind(c('Cat6A snake A'), 'Cat6A snake A'),
                app.fiberCableShortKind(c('Snake 2'), 'Snake 2'),
                app.fiberCableShortKind(c('SL rack'), 'SL rack'),
                app.fiberCableShortKind(c('Cat6 snake A'), 'Cat6 snake A'),
                app.fiberCableOptionText({...c('SL rack'), ft: 50})];
    }""")
    assert out == ['Cat6A snake · 4 channel', '4 channel', 'Cat6A · 4 channel', 'Cat6A snake · 4 channel',
                   'Cat6A · 4 channel', "SL rack · Cat6A snake · 4 channel · 50'"], out


def test_the_dock_editor_changes_the_channels_and_the_length(page):
    """Edit on a snake's link: the channels field and the length field each
    write once, one history entry each, and the list's option follows."""
    pg, ids = page
    a = ids['xds'][0]
    snake = pg.evaluate("() => window.app.getFiberCables()[0].id")
    pg.evaluate(ROW_JS, [a, 'p1'])
    if not pg.locator(f'[data-lrd-field="fiber-cable-strands-{snake}"]').count():
        pg.locator(f'[data-lrd-field="fiber-edit-{a}-p1"]').click()
    n = pg.locator(f'[data-lrd-field="fiber-cable-strands-{snake}"]')
    n.wait_for()

    def cable():
        return pg.evaluate("(id) => { const c = window.app.getFiberCable(id); "
                           "return {strands: c.strands, ft: c.ft}; }", snake)

    before = pg.evaluate(HISTORY_JS)
    n.fill('6')
    n.dispatch_event('change')
    assert settled(pg, cable, lambda v: v['strands'] == 6, 5000)['strands'] == 6
    hist = pg.evaluate(HISTORY_JS)
    assert (hist['index'], hist['action']) == (before['index'] + 1, 'Set Cat Snake Channels'), hist
    ft = pg.locator(f'[data-lrd-field="fiber-cable-ft-{snake}"]')
    ft.wait_for()
    ft.fill('120')
    ft.dispatch_event('change')
    assert settled(pg, cable, lambda v: v['ft'] == 120, 5000) == {'strands': 6, 'ft': 120}
    hist = pg.evaluate(HISTORY_JS)
    assert (hist['index'], hist['action']) == (before['index'] + 2, 'Set Cat Snake Length'), hist
    want = "Cat6A snake A · 6 channel · 120'"
    row = settled(pg, lambda: pg.evaluate(ROW_JS, [a, 'p1']),
                  lambda r: r and want in [o[1] for o in r['options']], 5000)
    assert want in [o[1] for o in row['options']], row
    # both undo, back to 4 channel at 150'
    pg.evaluate('() => window.app.undo()')
    pg.evaluate('() => window.app.undo()')
    assert settled(pg, cable, lambda v: v == {'strands': 4, 'ft': 150}, 5000) == {'strands': 4, 'ft': 150}
    assert ids['errors'] == []


def test_a_backup_link_on_the_snake_prints_beside_its_main(page):
    """XD A's X2 off the backup processor picks the snake (given a 5th
    channel): Fiber connections print it straight after XD A's X1, on Ch 5,
    the snake named without its size the second time."""
    pg, ids = page
    a = ids['xds'][0]
    snake = pg.evaluate("() => window.app.getFiberCables()[0].id")
    pg.evaluate("""async (id) => { await window.app.setFiberCable(id, {strands: 5}, 'Set Cat Snake Channels'); }""",
                snake)
    settled(pg, lambda: pg.evaluate("(id) => window.app.getFiberCable(id).strands", snake), lambda v: v == 5, 5000)
    pg.evaluate("""async ([box, id]) => { await window.app.setFiberLink(
        window.app.fiberBoxById(box), 'b1', {cable: id}); }""", [a, snake])
    assert settled(pg, lambda: _link_of(pg, a, 'b1'), lambda v: bool(v), 5000)['strands'] == [5]
    rows = pg.evaluate("""(sx) => window.app._bFiberConnectionRows(
            window.app._processorsResolved.find(p => p.id === sx), 'WALL SR')
        .filter(r => r.link && r.link.cable && r.link.cable.kind === 'cat-snake')
        .map(r => r.cells)""", ids['sx'])
    assert [r[1:] for r in rows[:2]] == [['Cat6A snake A (5 channel)', 'Ch 1', 'X1 on XD A', 'Ch 1'],
                                         ['Cat6A snake A', 'Ch 5', 'X2 on XD A', 'Ch 5']], rows
    pg.evaluate('() => window.app.undo()')
    pg.evaluate('() => window.app.undo()')
    assert settled(pg, lambda: _link_of(pg, a, 'b1'), lambda v: v is None, 5000) is None
    assert settled(pg, lambda: pg.evaluate("(id) => window.app.getFiberCable(id).strands", snake),
                   lambda v: v == 4, 5000) == 4
    assert ids['errors'] == []


# ── an undo while an edit is still landing (1.7.0 CI) ────────────────────
#
# A field's write takes its history step when the server's reply lands
# (_processorRequest). On a Linux runner an undo ran while a length write
# was still out: it stepped back over the channel step instead, and the
# reply then took a new "Set Cat Snake Length" step on top of the undo, so
# the next undo took that back and the channels were never undone. Held
# here by holding the reply, so neither test leans on timing.

def _snake_editor(pg, ids):
    a = ids['xds'][0]
    snake = pg.evaluate("() => window.app.getFiberCables()[0].id")
    pg.evaluate(ROW_JS, [a, 'p1'])
    if not pg.locator(f'[data-lrd-field="fiber-cable-strands-{snake}"]').count():
        pg.locator(f'[data-lrd-field="fiber-edit-{a}-p1"]').click()
    pg.locator(f'[data-lrd-field="fiber-cable-strands-{snake}"]').wait_for()
    return snake


def _snake_now(pg, snake):
    return pg.evaluate("(id) => { const c = window.app.getFiberCable(id); "
                       "return {strands: c.strands, ft: c.ft}; }", snake)


def _channels_typed(pg, snake, value):
    """Type the channel count and press Enter, the way a user commits it."""
    n = pg.locator(f'[data-lrd-field="fiber-cable-strands-{snake}"]')
    n.fill(str(value))
    n.press('Enter')
    settled(pg, lambda: _snake_now(pg, snake), lambda v: v['strands'] == value, 5000)
    assert settled(pg, lambda: pg.evaluate(HISTORY_JS),
                   lambda h: h['action'] == 'Set Cat Snake Channels', 5000)['action'] == 'Set Cat Snake Channels'


REDO_ACTION_JS = """() => ({redo: (window.app.history[window.app.historyIndex + 1] || {}).action,
    index: window.app.historyIndex, actions: window.app.history.map(h => h.action)})"""


def test_an_undo_pressed_before_the_length_lands_waits_for_it(page):
    """Channels to 6, then a length of 120 typed and committed; Undo is
    pressed while the server has not answered the length yet. The undo
    waits for the reply, then steps back over the length: 6 channels at
    150', the length the redo. Played at once, it stepped back over the
    channels and the reply wrote 120' as a new step after it."""
    pg, ids = page
    snake = _snake_editor(pg, ids)
    start = _snake_now(pg, snake)
    assert start == {'strands': 4, 'ft': 150}, start
    _channels_typed(pg, snake, 6)
    before = pg.evaluate(HISTORY_JS)
    held = []

    def hold(route):
        if route.request.method == 'PUT' and '"ft"' in (route.request.post_data or ''):
            held.append(route)
            return
        route.continue_()

    pg.route('**/api/fiber-cables/*', hold)
    try:
        ft = pg.locator(f'[data-lrd-field="fiber-cable-ft-{snake}"]')
        ft.fill('120')
        ft.press('Enter')
        assert settled(pg, lambda: len(held), lambda n: n == 1, 5000) == 1
        pg.evaluate('() => window.app.undo()')
        # nothing stepped yet: the undo waits for the length's step
        assert pg.evaluate(HISTORY_JS) == before
        held.pop().continue_()
        # the length's reply lands, takes its step, and the held undo
        # steps back over it: 6 channels at 150', the length the redo
        got = settled(pg, lambda: (_snake_now(pg, snake), pg.evaluate(HISTORY_JS),
                                   pg.evaluate(REDO_ACTION_JS)['redo']),
                      lambda v: v[2] is not None, 5000)
        assert got == ({'strands': 6, 'ft': 150}, before, 'Set Cat Snake Length'), (
            got, pg.evaluate(REDO_ACTION_JS))
    finally:
        # a reply still held goes on before the route comes off
        for r in held:
            r.continue_()
        pg.unroute('**/api/fiber-cables/*')
    pg.evaluate('() => window.app.undo()')
    assert settled(pg, lambda: _snake_now(pg, snake), lambda v: v == start, 5000) == start
    assert ids['errors'] == []


def test_ctrl_z_in_a_length_being_typed_steps_back_over_it(page):
    """A length typed and not yet committed, then Ctrl+Z in the field: the
    typed length commits and the undo steps back over it, so the snake is
    6 channels at 150' with the length the redo. Before, the undo stepped
    back over the channels and the rebuilt tray committed the typed 120'
    after it, as a new step that cut the redo."""
    pg, ids = page
    snake = _snake_editor(pg, ids)
    start = _snake_now(pg, snake)
    assert start == {'strands': 4, 'ft': 150}, start
    _channels_typed(pg, snake, 6)
    before = pg.evaluate(HISTORY_JS)
    ft = pg.locator(f'[data-lrd-field="fiber-cable-ft-{snake}"]')
    ft.click()
    pg.keyboard.press('ControlOrMeta+a')
    pg.keyboard.type('120')
    pg.keyboard.press('ControlOrMeta+z')
    got = settled(pg, lambda: (_snake_now(pg, snake), pg.evaluate(HISTORY_JS),
                               pg.evaluate(REDO_ACTION_JS)['redo']),
                  lambda v: v[2] is not None, 5000)
    assert got == ({'strands': 6, 'ft': 150}, before, 'Set Cat Snake Length'), (
        got, pg.evaluate(REDO_ACTION_JS))
    # and no write lands after it
    pg.wait_for_timeout(500)
    assert (_snake_now(pg, snake), pg.evaluate(HISTORY_JS)) == ({'strands': 6, 'ft': 150}, before)
    assert pg.locator(f'[data-lrd-field="fiber-cable-ft-{snake}"]').input_value() == '150'
    pg.evaluate('() => window.app.undo()')
    assert settled(pg, lambda: _snake_now(pg, snake), lambda v: v == start, 5000) == start
    assert ids['errors'] == []
