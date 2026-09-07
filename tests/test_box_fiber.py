"""A breakout box's fiber trunk: its type and its length.

"we need to add fiber types when cvt's or similar are used. and if cvt's
are used then we will list those instead of sending card" (user,
2026-09-07). A breakout box (a CVT4K-S, a CVT10, a Tessera XD - any `cvt`)
now carries two facts about the fiber that feeds it:

  - `fiberType` - free text, the pull sheet's GEAR LIST fiber words offered
    ("12 Tac Fiber", "10G Single-Mode SFP"); blank clears it.
  - `fiberFt`   - a finite number of feet, 0 or more; null / blank / 0 clears
    it; anything else is refused with the reason.

Both are stored on the box record (PUT /api/processors/<id>/cvts/<cvtId>),
ride resolve_card's box out to every reader, and are typed in the box's ⚙
on the hardware dock - one 'Set Box Fiber' history entry per commit. The
pull list adds ONE row per box with a length - the type (or "Fiber"), the
length, qty 1, the box's title - and its `unmodelled` note about fiber is
gone. The binder's data page lists the box instead of the card for the ports
it delivers (tests/test_binder.py).

Run locally (ONE pytest at a time - the browser-test servers use fixed
ports):
    LRD_E2E_PORT=15797 python3 -m pytest tests/test_box_fiber.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# ── the store, through the Flask client ──────────────────────────────────

def _h9_with_box(client, card='novastar-card-h-16xrj45-2xfiber',
                 box='novastar-cvt4k-s'):
    st = client.post('/api/processors', json={'deviceId': 'novastar-h9'}).get_json()
    pid = st['processors'][-1]['id']
    st = client.put(f'/api/processors/{pid}/slots/0', json={'deviceId': card}).get_json()
    proc = next(p for p in st['processors'] if p['id'] == pid)
    cid = proc['slots'][0]['card']['id']
    r = client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                    json={'deviceId': box, 'pair': False})
    assert r.status_code == 201, r.get_data(as_text=True)
    proc = next(p for p in r.get_json()['processors'] if p['id'] == pid)
    return pid, cid, proc['slots'][0]['card']['cvts'][0]['id']


def _raw_box(client, pid):
    st = client.get('/api/processors').get_json()
    return next(p for p in st['processors'] if p['id'] == pid)['slots'][0]['card']['cvts'][0]


def _resolved_box(client, pid):
    st = client.get('/api/processors').get_json()
    return next(p for p in st['resolved'] if p['id'] == pid)['slots'][0]['card']['cvts'][0]


def test_the_fiber_fields_round_trip_and_clear(client):
    """Typed and stored trimmed; a string length is a number; the resolved
    box carries both (and the trunk as the card's face prints it, "OPT 1-2"
    for a CVT4K-S on both OPTs of an H card); blank / null clear, and a
    cleared field leaves no key behind. Unset, the resolved box says '' and
    None - never a guessed length."""
    pid, cid, bid = _h9_with_box(client)
    box = _resolved_box(client, pid)
    assert (box['fiberType'], box['fiberFt']) == ('', None)
    assert box['trunkTitle'] == 'OPT 1-2' and box['trunkLetter'] == 'A-B'
    r = client.put(f'/api/processors/{pid}/cvts/{bid}',
                   json={'fiberType': '  12 Tac Fiber ', 'fiberFt': '250'})
    assert r.status_code == 200, r.get_data(as_text=True)
    raw = _raw_box(client, pid)
    assert (raw['fiberType'], raw['fiberFt']) == ('12 Tac Fiber', 250)
    box = _resolved_box(client, pid)
    assert (box['fiberType'], box['fiberFt']) == ('12 Tac Fiber', 250)
    # a fractional length keeps its fraction; an integral float is an int
    assert client.put(f'/api/processors/{pid}/cvts/{bid}', json={'fiberFt': 12.5}).status_code == 200
    assert _raw_box(client, pid)['fiberFt'] == 12.5
    assert client.put(f'/api/processors/{pid}/cvts/{bid}', json={'fiberFt': 100.0}).status_code == 200
    assert _raw_box(client, pid)['fiberFt'] == 100
    # the other fields of the same PUT still land, and a PUT without the
    # fiber keys leaves them alone
    assert client.put(f'/api/processors/{pid}/cvts/{bid}', json={'name': 'SR'}).status_code == 200
    raw = _raw_box(client, pid)
    assert raw['name'] == 'SR' and raw['fiberFt'] == 100 and raw['fiberType'] == '12 Tac Fiber'
    # clearing: blank type, null / blank / 0 length
    for body in ({'fiberFt': None}, {'fiberFt': ''}, {'fiberFt': 0}):
        assert client.put(f'/api/processors/{pid}/cvts/{bid}', json={'fiberFt': 60}).status_code == 200
        assert client.put(f'/api/processors/{pid}/cvts/{bid}', json=body).status_code == 200, body
        assert 'fiberFt' not in _raw_box(client, pid), body
    assert client.put(f'/api/processors/{pid}/cvts/{bid}', json={'fiberType': '  '}).status_code == 200
    raw = _raw_box(client, pid)
    assert 'fiberType' not in raw and raw['name'] == 'SR'
    box = _resolved_box(client, pid)
    assert (box['fiberType'], box['fiberFt']) == ('', None)


@pytest.mark.parametrize('body', [
    {'fiberFt': 'abc'}, {'fiberFt': -1}, {'fiberFt': True}, {'fiberFt': [250]},
    {'fiberFt': float('inf')}, {'fiberType': 5},
])
def test_a_bad_fiber_field_is_refused_with_the_reason(client, body):
    pid, cid, bid = _h9_with_box(client)
    assert client.put(f'/api/processors/{pid}/cvts/{bid}',
                      json={'fiberType': 'OM4', 'fiberFt': 50}).status_code == 200
    r = client.put(f'/api/processors/{pid}/cvts/{bid}', json=body)
    assert r.status_code == 400, r.get_data(as_text=True)
    assert r.get_json()['error'].startswith('Fiber ')
    # the refusal changed nothing
    raw = _raw_box(client, pid)
    assert (raw['fiberType'], raw['fiberFt']) == ('OM4', 50)


def test_the_trunk_title_follows_the_catalogs_word_or_the_letter(client):
    """"OPT" only where the card's catalog entry says so (the NovaStar H
    cards' notes); a trunked card without the word gets the app's own
    "trunk A"; a box past its trunks, or on a card with one trunk, gets
    nothing. No hardware assumptions: the word is the catalog's, not
    the vendor's."""
    pid, cid, bid = _h9_with_box(client, card='novastar-card-h-4xfiber', box='novastar-cvt10')
    st = client.get('/api/processors').get_json()
    card = next(p for p in st['resolved'] if p['id'] == pid)['slots'][0]['card']
    assert card['cvts'][0]['trunkTitle'] == 'OPT 1'
    r = client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                    json={'deviceId': 'novastar-cvt10', 'pair': False})
    assert r.status_code == 201
    card = next(p for p in r.get_json()['resolved'] if p['id'] == pid)['slots'][0]['card']
    assert [c['trunkTitle'] for c in card['cvts']] == ['OPT 1', 'OPT 2']
    # a card whose entry carries no trunk word: the letter
    st = client.post('/api/processors', json={'deviceId': 'novastar-mx6000-pro'}).get_json()
    mx = st['processors'][-1]['id']
    st = client.put(f'/api/processors/{mx}/slots/0', json={'deviceId': 'novastar-card-mx-4x10g'}).get_json()
    mxcard = next(p for p in st['processors'] if p['id'] == mx)['slots'][0]['card']['id']
    r = client.post(f'/api/processors/{mx}/cards/{mxcard}/cvts', json={'deviceId': 'novastar-cvt10', 'pair': False})
    assert r.status_code == 201, r.get_data(as_text=True)
    card = next(p for p in r.get_json()['resolved'] if p['id'] == mx)['slots'][0]['card']
    assert card['cvts'][0]['trunkTitle'] == 'trunk A' and card['cvts'][0]['trunkLetter'] == 'A'


# ── the browser: the box's ⚙, one entry per commit, the pull list ────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

# One H9: slot 0 an H_16xRJ45+2xfiber named SR with a CVT10 on OPT 1 (the
# box delivers 1-8 again). WALL 8 × 12 of 200 px cabinets on the Legacy
# platform needs six ports, placed onto the card in order: 1-6, the box's
# sockets.
SEED_JS = """async () => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet;
    await j('PUT', '/api/project', proj);
    await j('POST', '/api/layer/add', {name: 'WALL', columns: 8, rows: 12,
                                       cabinet_width: 200, cabinet_height: 200,
                                       processorType: 'novastar-armor'});
    let st = await j('POST', '/api/processors', {deviceId: 'novastar-h9'});
    const pid = st.processors[0].id;
    st = await j('PUT', `/api/processors/${pid}/slots/0`, {deviceId: 'novastar-card-h-16xrj45-2xfiber'});
    const cardId = st.processors[0].slots[0].card.id;
    await j('PUT', `/api/processors/${pid}/cards/${cardId}`, {name: 'SR'});
    st = await j('POST', `/api/processors/${pid}/cards/${cardId}/cvts`, {deviceId: 'novastar-cvt10', pair: false});
    const boxId = st.processors[0].slots[0].card.cvts[0].id;
    const app = window.app;
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('box_fiber_setup');
    const wall = app.project.layers[0];
    app.selectLayer(wall);
    await app.refreshProcessors();
    await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
                                 {layerId: String(wall.id), cardId});
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    app.renderHardwareDock();
    app.resetHistory('Box Fiber Seed');
    const scr = app._assignment.screens.find(s => s.layerId === String(wall.id));
    return { id: wall.id, procId: pid, cardId, boxId,
             ports: scr.ports.map(pt => [pt.number, pt.cardId, pt.port]) };
}"""

STATE_JS = """(ids) => {
    const app = window.app;
    const box = app._dockFindCvt(ids.boxId).cvt;
    return { type: box.fiberType, ft: box.fiberFt,
             action: app.history[app.historyIndex].action, index: app.historyIndex };
}"""

SERVED_JS = """async (ids) => {
    const st = await (await fetch('/api/processors')).json();
    const box = st.processors.find(p => p.id === ids.procId).slots[0].card.cvts[0];
    return { type: box.fiberType === undefined ? null : box.fiberType,
             ft: box.fiberFt === undefined ? null : box.fiberFt };
}"""

OPEN_GEAR_JS = """(popId) => {
    const gear = document.querySelector(`[data-hwpop="${popId}"]`);
    if (!gear) return false;
    const pop = document.getElementById('hw-gear-popover');
    const open = !!(pop && pop.style.display !== 'none'
        && window.app._hwPopover && window.app._hwPopover.id === popId);
    if (!open) gear.click();
    const after = document.getElementById('hw-gear-popover');
    return !!(after && after.style.display !== 'none');
}"""

LIST_JS = """() => {
    const app = window.app;
    app._circuitTailCache = null;
    const out = JSON.parse(JSON.stringify(app.buildPullList()));
    const rows = (list) => list.map(r => [r.type, r.length, r.qty, r.label, r.notes, r.side]);
    return { rows: rows(out.positions[0].rows), unmodelled: out.unmodelled,
             hardware: out.hardware.filter(h => h.kind === 'processor').map(h => rows(h.rows)),
             ports: out.byScreen[Object.keys(out.byScreen)[0]].ports.map(p => [p.num, p.box]) };
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
    # the tray draws processors on the data side
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(500)
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(1200)
    assert [p[2] for p in ids['ports']] == [1, 2, 3, 4, 5, 6], f'fixture: six ports on sockets 1-6: {ids}'
    ids['errors'] = errors
    yield pg, ids
    context.close()


def _served(pg, ids, ok, timeout=4000):
    waited = 0
    while waited < timeout:
        s = pg.evaluate(SERVED_JS, ids)
        if ok(s):
            return s
        pg.wait_for_timeout(200)
        waited += 200
    return pg.evaluate(SERVED_JS, ids)


def _open_box_gear(pg, ids):
    assert pg.evaluate(OPEN_GEAR_JS, f"box-{ids['boxId']}"), 'the box gear did not open'
    pg.wait_for_timeout(300)


def test_the_box_gear_offers_the_gear_lists_fiber_words_and_takes_any(page):
    """The ⚙ carries a Fiber type field (a datalist seeded from the GEAR
    LIST's fiber-ish entries - "12 Tac Fiber", "10G Single-Mode SFP" - and
    nothing that is not fiber) and a feet field, both keyed for focus
    restore, both empty on a box nobody typed on."""
    pg, ids = page
    _open_box_gear(pg, ids)
    bid = ids['boxId']
    waited = 0
    while waited < 4000 and pg.evaluate(f"() => document.querySelectorAll('#hw-fiber-types-{bid} option').length") == 0:
        pg.wait_for_timeout(200)
        waited += 200
    out = pg.evaluate("""(bid) => {
        const type = document.querySelector(`[data-lrd-field="processor-cvt-fiber-type-${bid}"]`);
        const ft = document.querySelector(`[data-lrd-field="processor-cvt-fiber-ft-${bid}"]`);
        return {
            inPop: !!(type && type.closest('#hw-gear-popover')) && !!(ft && ft.closest('#hw-gear-popover')),
            typeValue: type && type.value, ftValue: ft && ft.value, ftType: ft && ft.type,
            list: type && type.getAttribute('list'),
            options: [...document.querySelectorAll(`#hw-fiber-types-${bid} option`)].map(o => o.value),
            labels: [...document.querySelectorAll('#hw-gear-popover label')].map(l => l.textContent),
        };
    }""", bid)
    assert out['inPop'], out
    assert (out['typeValue'], out['ftValue'], out['ftType']) == ('', '', 'number')
    assert out['list'] == f'hw-fiber-types-{bid}'
    assert '12 Tac Fiber' in out['options'] and '10G Single-Mode SFP' in out['options'], out['options']
    assert not [o for o in out['options'] if o in ('Tru-1', 'Multi', 'Ether-con', 'HDMI', 'CVT Rack')], out['options']
    assert 'Fiber' in out['labels'] and 'Fiber ft' in out['labels'], out['labels']


def test_each_commit_is_one_set_box_fiber_entry_and_undo_takes_it_back(page):
    pg, ids = page
    bid = ids['boxId']
    _open_box_gear(pg, ids)
    index = pg.evaluate(STATE_JS, ids)['index']
    field = pg.locator(f'[data-lrd-field="processor-cvt-fiber-type-{bid}"]')
    field.fill('12 Tac Fiber')
    field.press('Tab')
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids)
    assert st['type'] == '12 Tac Fiber' and st['ft'] is None, st
    assert st['action'] == 'Set Box Fiber' and st['index'] == index + 1, st
    _open_box_gear(pg, ids)
    ft = pg.locator(f'[data-lrd-field="processor-cvt-fiber-ft-{bid}"]')
    ft.fill('250')
    ft.press('Tab')
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids)
    assert st['ft'] == 250 and st['type'] == '12 Tac Fiber', st
    assert st['action'] == 'Set Box Fiber' and st['index'] == index + 2, st
    served = _served(pg, ids, lambda s: s['ft'] == 250)
    assert served == {'type': '12 Tac Fiber', 'ft': 250}, served
    # the fields read the stored values back after the dock rebuilt
    _open_box_gear(pg, ids)
    assert pg.locator(f'[data-lrd-field="processor-cvt-fiber-type-{bid}"]').input_value() == '12 Tac Fiber'
    assert pg.locator(f'[data-lrd-field="processor-cvt-fiber-ft-{bid}"]').input_value() == '250'
    # undo: the length, then the type; redo brings both back
    pg.evaluate('() => window.app.undo()')
    served = _served(pg, ids, lambda s: s['ft'] is None)
    assert served == {'type': '12 Tac Fiber', 'ft': None}, served
    pg.evaluate('() => window.app.undo()')
    served = _served(pg, ids, lambda s: s['type'] is None)
    assert served == {'type': None, 'ft': None}, served
    assert pg.evaluate(STATE_JS, ids)['index'] == index
    pg.evaluate('() => window.app.redo()')
    pg.evaluate('() => window.app.redo()')
    served = _served(pg, ids, lambda s: s['ft'] == 250)
    assert served == {'type': '12 Tac Fiber', 'ft': 250}, served
    assert pg.evaluate(STATE_JS, ids)['index'] == index + 2
    # a blank length clears without a refusal; a bad one is refused and the
    # stored value stands
    _open_box_gear(pg, ids)
    ft = pg.locator(f'[data-lrd-field="processor-cvt-fiber-ft-{bid}"]')
    ft.fill('')
    ft.press('Tab')
    pg.wait_for_timeout(900)
    served = _served(pg, ids, lambda s: s['ft'] is None)
    assert served == {'type': '12 Tac Fiber', 'ft': None}
    assert pg.evaluate(STATE_JS, ids)['index'] == index + 3
    refused = pg.evaluate("""async (ids) => {
        const r = await fetch(`/api/processors/${ids.procId}/cvts/${ids.boxId}`, {method: 'PUT',
            headers: {'Content-Type': 'application/json'}, body: JSON.stringify({fiberFt: -5})});
        return { status: r.status, body: await r.json() };
    }""", ids)
    assert refused['status'] == 400 and refused['body']['error'].startswith('Fiber length')
    pg.evaluate("""async (ids) => {
        await fetch(`/api/processors/${ids.procId}/cvts/${ids.boxId}`, {method: 'PUT',
            headers: {'Content-Type': 'application/json'}, body: JSON.stringify({fiberFt: 250})});
        await window.app.refreshProcessors();
    }""", ids)
    assert ids['errors'] == []


def test_the_pull_list_lists_the_boxs_fiber_once_and_nothing_is_unmodelled(page):
    """Six ports ride the box; its fiber is ONE row - "12 Tac Fiber" 250'
    qty 1, labelled with the box's title, on the data side - in the
    position and on the processor's hardware list; every port names its
    box; `unmodelled` is empty. Untyped, the row is "Fiber"; with no
    length, no row."""
    pg, ids = page
    out = pg.evaluate(LIST_JS)
    fiber = [r for r in out['rows'] if 'Fiber' in r[0]]
    assert fiber == [['12 Tac Fiber', "250'", 1, 'CVT10 A', '', 'data']], out['rows']
    assert out['unmodelled'] == []
    assert out['hardware'] == [[['12 Tac Fiber', "250'", 1, 'CVT10 A', '', 'data']]], out['hardware']
    assert out['ports'] == [[n, 'CVT10 A'] for n in range(1, 7)], out['ports']
    pg.evaluate("""async (ids) => {
        await fetch(`/api/processors/${ids.procId}/cvts/${ids.boxId}`, {method: 'PUT',
            headers: {'Content-Type': 'application/json'}, body: JSON.stringify({fiberType: '', name: 'SR'})});
        await window.app.refreshProcessors(); await window.app.refreshPortAssignment();
    }""", ids)
    out = pg.evaluate(LIST_JS)
    assert [r for r in out['rows'] if 'Fiber' in r[0]] == [['Fiber', "250'", 1, 'CVT10 SR', '', 'data']], out['rows']
    pg.evaluate("""async (ids) => {
        await fetch(`/api/processors/${ids.procId}/cvts/${ids.boxId}`, {method: 'PUT',
            headers: {'Content-Type': 'application/json'}, body: JSON.stringify({fiberFt: null})});
        await window.app.refreshProcessors(); await window.app.refreshPortAssignment();
    }""", ids)
    out = pg.evaluate(LIST_JS)
    assert not [r for r in out['rows'] if 'Fiber' in r[0]], out['rows']
    assert out['ports'] == [[n, 'CVT10 SR'] for n in range(1, 7)]
    assert ids['errors'] == []
