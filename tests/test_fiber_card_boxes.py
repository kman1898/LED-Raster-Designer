"""A fiber-only card has no port without a breakout box, and adding one
opens its box picker.

The owner's ruling (2026-10-04): "So when using quad opt or quad opt
enhanced which is 8 OPT's, you cannot show it as having 32 or 40/80 with
backup without having CVT's so when you add that maybe we throw up a dialog
asking you to add them?" - for EVERY fiber-only card, and "Yes, same
dialog" for the SX40 and HELIOS. So:

* THE FIBER-ONLY CARDS ARE BOX-FED, by the catalog's `requiresDistribution`
  (processor_catalog.is_box_fed) - the one flag the SX40 and the HELIOS
  Standard already carry. Every card whose connector is fiber carries it.
* A BARE CARD HAS NO PORT. Its sockets are its boxes' spans: none with no
  box, and each box adds what it delivers - its own count, capped by the
  card's ports per trunk (a CVT10 is 8 on an H_4xfiber). The MX_1x40G
  takes the CVT8-5G and nothing else; copy/backup still halves; unchanged.
* A PORT NO BOX COVERS IS REFUSED, with the SX40's own sentence.
* A SHOW SAVED WITH PORTS MAPPED ON A BARE CARD STILL LOADS. Its pins stay
  as stored - the SX40's path for a pin outside every box: kept, read
  beyondCapacity, labelled by nothing - and a box on the OPT makes them
  sockets again.
* ADDING ONE OPENS THE "+ BOX" LIST on the new card - from the Add
  processor button (a HELIOS Standard) and from a slot's card pick (each
  fiber card). Never on a load, an undo or a redo, and never on a card
  that arrives with its boxes (the stocked SX40).

Run locally:
    python3 -m pytest tests/test_fiber_card_boxes.py -q --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import port_assignment as assignment  # noqa: E402
import processor_catalog as catalog  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# card -> (the chassis it goes in, the box that fits its trunk)
FIBER_CARDS = {
    'novastar-card-h-4xfiber': ('novastar-h9', 'novastar-cvt10'),
    'novastar-card-h-4xfiber-enhanced': ('novastar-h9', 'novastar-cvt10'),
    'novastar-card-mx-4x10g': ('novastar-mx2000-pro', 'novastar-cvt10'),
    'novastar-card-mx-1x40g': ('novastar-mx2000-pro', 'novastar-cvt8-5g'),
}
SX40 = 'brompton-sx40'
HELIOS_8K = 'megapixel-helios-8k'


# ── helpers ───────────────────────────────────────────────────────────────

def add_layer(client, name):
    resp = client.post('/api/layer/add', json={
        'name': name, 'columns': 4, 'rows': 3,
        'cabinet_width': 200, 'cabinet_height': 200})
    assert resp.status_code in (200, 201), resp.get_data(as_text=True)
    return str(resp.get_json()['id'])


def chassis_with(client, chassis, card_device):
    st = client.post('/api/processors', json={'deviceId': chassis}).get_json()
    pid = st['processors'][-1]['id']
    resp = client.put(f'/api/processors/{pid}/slots/0',
                      json={'deviceId': card_device})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    proc = next(p for p in resp.get_json()['resolved'] if p['id'] == pid)
    return pid, proc['slots'][0]['card']


def add_box(client, pid, cid, box, **extra):
    return client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                       json=dict({'deviceId': box}, **extra))


def resolved_card(body, cid):
    for proc in body['resolved']:
        for slot in proc['slots']:
            if slot['card'] and slot['card']['id'] == cid:
                return slot['card']
    raise AssertionError(f'no card {cid}')


def numbers(card):
    return [p['number'] for p in card['ports']]


def resolve(client, sc):
    resp = client.post('/api/port-assignments/resolve', json={'screens': sc})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()['resolution']


def summary(res, cid):
    return next(c for c in res['cards'] if c['cardId'] == cid)


# ── 1. The flag ───────────────────────────────────────────────────────────

def test_every_fiber_only_card_is_box_fed_off_the_catalog():
    """is_box_fed reads requiresDistribution and nothing else; the four
    fiber-only cards carry it, and so does every card whose connector is
    fiber - a fiber card added later without the flag fails here."""
    for card_id in FIBER_CARDS:
        device = catalog.get_device(card_id)
        assert device['kind'] == 'card' and device['connector'] == 'fiber'
        assert device.get('requiresDistribution') is True, card_id
        assert catalog.is_box_fed(device) is True, card_id
    fiber = sorted(d['id'] for d in catalog.devices('card')
                   if d.get('connector') == 'fiber')
    assert fiber == sorted(FIBER_CARDS), fiber
    # the copper card with two copy OPTs keeps its own sixteen
    assert not catalog.is_box_fed(
        catalog.get_device('novastar-card-h-16xrj45-2xfiber'))


# ── 2. No box, no port; each box adds its share ───────────────────────────

@pytest.mark.parametrize('card_device', sorted(FIBER_CARDS))
def test_a_bare_card_has_no_port_and_each_box_adds_its_share(client,
                                                            card_device):
    chassis, box = FIBER_CARDS[card_device]
    pid, card = chassis_with(client, chassis, card_device)
    cid = card['id']
    assert card['boxFed'] is True
    assert numbers(card) == [], f'a bare {card_device} lists ports'
    assert card['defined'] == 0
    res = resolve(client, [{'layerId': 'W', 'name': 'W', 'ports': 4}])
    assert (summary(res, cid)['capacity'], summary(res, cid)['free']) == (0, 0)

    device = catalog.get_device(card_device)
    per_box = min(catalog.port_capacity(box)['count'], device['portsPerTrunk'])
    ceiling = catalog.port_capacity(card_device)['count']
    for n in range(1, device['trunks'] + 1):
        resp = add_box(client, pid, cid, box)
        assert resp.status_code == 201, resp.get_data(as_text=True)
        card = resolved_card(resp.get_json(), cid)
        assert numbers(card) == list(range(1, min(n * per_box, ceiling) + 1))
        assert all(p['cvtId'] for p in card['ports'])
    res = resolve(client, [{'layerId': 'W', 'name': 'W', 'ports': 4}])
    assert summary(res, cid)['capacity'] == ceiling
    # and the card is full: nothing more goes on
    assert add_box(client, pid, cid, box).status_code == 400


def test_the_box_is_capped_at_the_cards_ports_per_trunk(client):
    """A CVT10 is ten ports on a 64B/66B trunk and eight on the H_4xfiber's
    8B/10B one; the enhanced card's OPT carries ten."""
    pid, card = chassis_with(client, 'novastar-h9', 'novastar-card-h-4xfiber')
    resp = add_box(client, pid, card['id'], 'novastar-cvt10')
    assert len(resolved_card(resp.get_json(), card['id'])['ports']) == 8
    pid, card = chassis_with(client, 'novastar-h9',
                             'novastar-card-h-4xfiber-enhanced')
    resp = add_box(client, pid, card['id'], 'novastar-cvt10')
    assert len(resolved_card(resp.get_json(), card['id'])['ports']) == 10


def test_the_40g_card_takes_only_the_cvt8_5g(client):
    pid, card = chassis_with(client, 'novastar-mx2000-pro',
                             'novastar-card-mx-1x40g')
    resp = add_box(client, pid, card['id'], 'novastar-cvt10')
    assert resp.status_code == 400
    assert 'rates must match' in resp.get_json()['error']
    resp = add_box(client, pid, card['id'], 'novastar-cvt8-5g')
    assert resp.status_code == 201
    assert numbers(resolved_card(resp.get_json(), card['id'])) \
        == list(range(1, 9))


def test_copy_backup_still_halves_what_the_boxes_give(client):
    """H_4xfiber in copy/backup is 16: a CVT10 brings its backup box on the
    copy OPT (NovaStar's default pair), and the pair is ports 1-8 once."""
    pid, card = chassis_with(client, 'novastar-h9', 'novastar-card-h-4xfiber')
    cid = card['id']
    resp = client.put(f'/api/processors/{pid}/cards/{cid}',
                      json={'mode': 'copy-backup'})
    assert resp.status_code == 200
    assert numbers(resolved_card(resp.get_json(), cid)) == []
    resp = add_box(client, pid, cid, 'novastar-cvt10')
    card = resolved_card(resp.get_json(), cid)
    assert len(card['cvts']) == 2
    assert numbers(card) == list(range(1, 9))
    resp = add_box(client, pid, cid, 'novastar-cvt10')
    assert numbers(resolved_card(resp.get_json(), cid)) == list(range(1, 17))


# ── 3. A port no box covers is refused ────────────────────────────────────

@pytest.mark.parametrize('card_device', sorted(FIBER_CARDS))
def test_a_port_on_a_bare_card_is_refused_as_on_an_sx40(client, card_device):
    chassis, box = FIBER_CARDS[card_device]
    wall = add_layer(client, 'WALL')
    pid, card = chassis_with(client, chassis, card_device)
    cid = card['id']
    sc = [{'layerId': wall, 'name': 'WALL', 'ports': 2}]
    resp = client.post('/api/port-assignments/place', json={
        'layerId': wall, 'index': 0, 'cardId': cid, 'port': 1,
        'screens': sc})
    assert resp.status_code == 409, resp.get_data(as_text=True)
    assert resp.get_json()['error'].endswith(
        'has no port 1 - on this device a port is only inside a breakout '
        'box.'), resp.get_json()
    # a whole-card fill (the card dragged onto the wall) is refused too
    resp = client.post('/api/port-assignments/place-overflow', json={
        'layerId': wall, 'cardId': cid, 'screens': sc})
    assert resp.status_code == 409, resp.get_data(as_text=True)
    assert resp.get_json()['error'].endswith('has no free ports.')
    assert client.get('/api/project').get_json().get(
        assignment.STATE_KEY, {}).get('pins', []) == []
    # with a box on, port 1 is a socket
    assert add_box(client, pid, cid, box).status_code == 201
    resp = client.post('/api/port-assignments/place', json={
        'layerId': wall, 'index': 0, 'cardId': cid, 'port': 1,
        'screens': sc})
    assert resp.status_code == 200, resp.get_data(as_text=True)


# ── 4. A show saved before the ruling ─────────────────────────────────────

def _legacy_show(client, route):
    """An H9 with a bare H_4xfiber and WALL's four ports pinned to 1-4 on
    it - the shape a file saved before 2026-10-04 carries - entering
    server state by `route` (POST = open a file, PUT = the restore funnel
    undo and a file load share)."""
    wall = add_layer(client, 'WALL')
    project = client.get('/api/project').get_json()
    project['processors'] = [{
        'id': 'proc1', 'deviceId': 'novastar-h9', 'name': 'SR',
        'mode': None, 'redundancy': False,
        'slots': [{'index': 0, 'card': {
            'id': 'card2', 'deviceId': 'novastar-card-h-4xfiber', 'name': '',
            'mode': 'independent', 'fixed': False, 'cvts': []}}]
        + [{'index': i, 'card': None} for i in range(1, 5)],
    }]
    project['next_processor_seq'] = 3
    project[assignment.STATE_KEY] = {
        'auto': False, 'autoRetired': True,
        'pins': [{'layerId': wall, 'index': i, 'cardId': 'card2',
                  'port': i + 1} for i in range(4)]}
    resp = getattr(client, route)('/api/project', json=project)
    assert resp.status_code in (200, 201), resp.get_data(as_text=True)
    return wall


@pytest.mark.parametrize('route', ['put', 'post'])
def test_a_show_mapped_on_a_bare_card_still_loads(client, route):
    wall = _legacy_show(client, route)
    stored = client.get('/api/project').get_json()
    pins = sorted((p['index'], p['port'])
                  for p in stored[assignment.STATE_KEY]['pins'])
    assert pins == [(0, 1), (1, 2), (2, 3), (3, 4)], (
        'loading dropped the pins a saved show carried')
    # nothing was invented: no box stocked onto the card
    assert stored['processors'][0]['slots'][0]['card']['cvts'] == []
    sc = [{'layerId': wall, 'name': 'WALL', 'ports': 4}]
    res = resolve(client, sc)
    ports = res['screens'][0]['ports']
    assert [p['port'] for p in ports] == [1, 2, 3, 4]
    assert all(p['beyondCapacity'] for p in ports), ports
    assert summary(res, 'card2')['capacity'] == 0
    # a CVT10 on OPT 1 makes 1-8 sockets, and the saved pins hold again
    assert add_box(client, 'proc1', 'card2', 'novastar-cvt10').status_code \
        == 201
    res = resolve(client, sc)
    ports = res['screens'][0]['ports']
    assert not any(p['beyondCapacity'] for p in ports), ports
    assert [p['label'] for p in ports] == ['SR-1', 'SR-2', 'SR-3', 'SR-4']


# ── 5. The box picker after an add ────────────────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

SEED_JS = """async () => {
    const proj = await (await fetch('/api/project')).json();
    proj.layers = [];
    proj.groups = [];
    proj.processors = [];
    proj.distros = [];
    delete proj.port_assignments;
    await fetch('/api/project', {method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(proj)});
    const app = window.app;
    app.project = await (await fetch('/api/project')).json();
    await app.refreshProcessors();
    app.renderLayers();
    app.resetHistory('Picker Seed');
    return true;
}"""

# Which popover is open, what its box list offers, and the new card's
# boxes - read off the live app.
STATE_JS = """(cardId) => {
    const app = window.app;
    const pop = document.getElementById('hw-gear-popover');
    const open = !!(pop && pop.style.display !== 'none' && app._hwPopover);
    const found = cardId ? app._dockFindCard(cardId) : null;
    return {
        popover: open ? app._hwPopover.id : null,
        items: open ? [...pop.querySelectorAll('.hw-dock-addbox-item')]
            .map(b => b.textContent) : [],
        boxes: found ? (found.card.cvts || []).length : null,
        ports: found ? (found.card.ports || []).length : null,
    };
}"""

# Every card id on the tree, by processor.
CARDS_JS = """() => (window.app._processorsResolved || []).map(p => ({
    id: p.id, deviceId: p.deviceId,
    cards: (p.slots || []).filter(s => s.card).map(s => s.card.id)}))"""

OPEN_GEAR_JS = """(popId) => {
    const gear = document.querySelector(`[data-hwpop="${popId}"]`);
    if (!gear) return false;
    gear.click();
    const pop = document.getElementById('hw-gear-popover');
    return !!(pop && pop.style.display !== 'none');
}"""

HIST_JS = "() => window.app.history[window.app.historyIndex].action"


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
    pg.evaluate(SEED_JS)
    pg.wait_for_timeout(800)
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(600)
    yield pg, errors
    context.close()


def close_popover(pg):
    pg.evaluate("() => window.app._hwPopoverClose()")


def add_unit(pg, device_id):
    """The header's Add processor: pick the device, press Add. Returns the
    new processor's id and its card ids."""
    before = {p['id'] for p in pg.evaluate(CARDS_JS)}
    pg.select_option('#processor-add-device', device_id)
    pg.locator('#processor-add-btn').click()
    pg.wait_for_timeout(1000)
    new = [p for p in pg.evaluate(CARDS_JS) if p['id'] not in before]
    assert len(new) == 1, new
    return new[0]['id'], new[0]['cards']


def test_adding_a_helios_opens_its_box_picker(page):
    pg, errors = page
    close_popover(pg)
    pid, cards = add_unit(pg, HELIOS_8K)
    assert len(cards) == 1
    card = cards[0]
    st = pg.evaluate(STATE_JS, card)
    assert st['popover'] == f'addbox-{card}', st
    fits = pg.evaluate(
        "(c) => window.app._cardBoxFits(window.app._dockFindCard(c).card)"
        ".map(d => d.name)", card)
    assert st['items'] == fits and fits, st
    assert st['boxes'] == 0 and st['ports'] == 0
    # a pick puts ONE box on and closes the list
    pg.locator('#hw-gear-popover .hw-dock-addbox-item').first.click()
    pg.wait_for_timeout(1000)
    st = pg.evaluate(STATE_JS, card)
    assert st['boxes'] == 1 and st['ports'] > 0, st
    assert st['popover'] is None, st
    assert pg.evaluate(HIST_JS) == 'Add Breakout Box'

    # UNDO takes the box off - the card is bare again, and nothing opens
    pg.evaluate("() => window.app.undo()")
    pg.wait_for_timeout(1000)
    st = pg.evaluate(STATE_JS, card)
    assert st['boxes'] == 0 and st['popover'] is None, st
    # undo the add itself, then REDO it: the bare HELIOS is back, unasked
    pg.evaluate("() => window.app.undo()")
    pg.wait_for_timeout(1000)
    assert pid not in [p['id'] for p in pg.evaluate(CARDS_JS)]
    pg.evaluate("() => window.app.redo()")
    pg.wait_for_timeout(1000)
    st = pg.evaluate(STATE_JS, card)
    assert st['boxes'] == 0 and st['popover'] is None, st
    pg.evaluate("() => window.app.redo()")
    pg.wait_for_timeout(1000)
    st = pg.evaluate(STATE_JS, card)
    assert st['boxes'] == 1 and st['popover'] is None, st
    assert errors == []


def test_a_stocked_sx40_opens_nothing(page):
    """An SX40 arrives with its four XDs (the 2026-08-25 default) - a box
    already on every trunk, so there is nothing to ask."""
    pg, errors = page
    close_popover(pg)
    _pid, cards = add_unit(pg, SX40)
    st = pg.evaluate(STATE_JS, cards[0])
    assert st['boxes'] == 4 and st['popover'] is None, st
    assert errors == []


@pytest.mark.parametrize('card_device', sorted(FIBER_CARDS))
def test_a_fiber_card_picked_into_a_slot_opens_its_box_picker(page,
                                                              card_device):
    pg, errors = page
    chassis, box = FIBER_CARDS[card_device]
    close_popover(pg)
    pid, cards = add_unit(pg, chassis)
    assert cards == []
    assert pg.evaluate(STATE_JS, None)['popover'] is None, (
        'an empty chassis opened a picker')
    assert pg.evaluate(OPEN_GEAR_JS, f'proc-{pid}')
    pg.select_option(f'#hw-gear-popover [data-lrd-field="processor-slot-'
                     f'{pid}-0"]', card_device)
    pg.wait_for_timeout(1000)
    card = next(p for p in pg.evaluate(CARDS_JS) if p['id'] == pid)['cards'][0]
    st = pg.evaluate(STATE_JS, card)
    assert st['popover'] == f'addbox-{card}', st
    assert st['ports'] == 0 and st['boxes'] == 0, st
    if card_device == 'novastar-card-mx-1x40g':
        assert st['items'] == ['CVT8-5G'], st
    else:
        assert 'CVT10' in st['items'], st
    # closing it leaves the card with no ports - and no chip in the tray
    pg.keyboard.press('Escape')
    pg.wait_for_timeout(300)
    st = pg.evaluate(STATE_JS, card)
    assert st['popover'] is None and st['ports'] == 0, st
    chips = pg.evaluate(
        "(c) => document.querySelectorAll(`[data-lrd-tile^='port-${c}-']`)"
        ".length", card)
    assert chips == 0
    assert errors == []


def test_a_load_opens_nothing(page):
    """A file entering the page - a bare fiber card in it - is the
    restore funnel and a re-read, never an add."""
    pg, errors = page
    close_popover(pg)
    pg.evaluate("""async () => {
        const proj = await (await fetch('/api/project')).json();
        proj.processors = [{id: 'proc90', deviceId: 'novastar-h9', name: '',
            mode: null, redundancy: false,
            slots: [{index: 0, card: {id: 'card91',
                deviceId: 'novastar-card-h-4xfiber-enhanced', name: '',
                mode: 'default', fixed: false, cvts: []}}]}];
        proj.next_processor_seq = 92;
        await fetch('/api/project', {method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(proj)});
        const app = window.app;
        app.project = await (await fetch('/api/project')).json();
        await app.refreshProcessors();
    }""")
    pg.wait_for_timeout(800)
    st = pg.evaluate(STATE_JS, 'card91')
    assert st['boxes'] == 0 and st['popover'] is None, st
    assert errors == []
