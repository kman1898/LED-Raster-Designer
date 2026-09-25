"""A box-fed unit has no port outside a breakout box.

The owner's ruling (2026-09-24): "I can remove boxes from SX40's but then it
adds those ports back to the SX40 outside of an XD box. SX40's can't use
ports outside of an XD box. So that makes no sense and we need to remove
that functionality" - and "same goes for Helios". Until then a removed box's
span fell back to the unit's fixed card as loose ports: they showed in the
tray as the unit's own sockets, took pins, printed on labels and counted in
the summaries. Now:

* WHICH UNITS ARE BOX-FED IS THE CATALOG'S CALL, by `requiresDistribution`
  and nothing else (processor_catalog.is_box_fed / box_fed_device_ids).
  The set is read off the catalog, never listed in code: the tests below
  name the rule and check the members the ruling named are in it - and that
  the HELIOS Jr, 1G copper straight to tiles, is not.
* ON SUCH A UNIT ONLY THE BOXES' SPANS ARE SOCKETS. resolve_card lists no
  port that no box delivers; the assignment's socket set (cards_in
  `sockets`), its free count, its fills, its hand placements and its
  labels all follow that list. A stocked SX40 has forty sockets, all of
  them a box's; with box B removed it has thirty, and 11-20 are nowhere.
* REMOVING A BOX TAKES ITS SOCKETS AND ITS PINS. The pins that pointed
  into the box come off (port_assignment.prune_pins_off_sockets), the
  reply carries a note naming them - "Removed box Tessera XD B - 3 ports
  of LEFT are unplaced again" - and the pruned pin state, and the tray
  toasts the note. The other boxes hold their trunks (hold_box_trunks):
  C stays 21-30, it does not slide down onto B's trunk.
* UNDO BRINGS BOX AND PINS BACK TOGETHER - the whole-project PUT of the
  prior snapshot, as every undo is.
* AN UNFLAGGED UNIT KEEPS TODAY'S LOOSE PORTS EXACTLY: a NovaStar
  all-in-one's ports are on its face, a box there is another place to plug
  into them, and a box delete leaves every port and every pin where it was.

Run locally:
    python3 -m pytest tests/test_box_fed_units.py -q --browser chromium
"""

import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import port_assignment as assignment  # noqa: E402
import processor_catalog as catalog  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# ── helpers ───────────────────────────────────────────────────────────────

SX40 = 'brompton-sx40'
XD = 'brompton-xd'
HELIOS_8K = 'megapixel-helios-8k'
RS12 = 'megapixel-rs12'
# The unflagged one-box unit the "keeps its loose ports" test uses: a
# NovaStar all-in-one whose trunks carry blocks of ITS OWN ports.
MX40 = 'novastar-mx40-pro'
CVT10 = 'novastar-cvt10'


def add_layer(client, name, cols=4, rows=3, x=0):
    resp = client.post('/api/layer/add', json={
        'name': name, 'columns': cols, 'rows': rows,
        'cabinet_width': 200, 'cabinet_height': 200, 'offset_x': x})
    assert resp.status_code in (200, 201), resp.get_data(as_text=True)
    return str(resp.get_json()['id'])


def add_processor(client, device_id):
    resp = client.post('/api/processors', json={'deviceId': device_id})
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


def add_box(client, pid, cid, device_id):
    resp = client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                       json={'deviceId': device_id})
    assert resp.status_code in (200, 201), resp.get_data(as_text=True)
    return resp.get_json()


def unit(state):
    """The one unit in the state, its fixed card and that card's boxes."""
    assert len(state['resolved']) == 1, state['resolved']
    proc = state['resolved'][0]
    card = proc['slots'][0]['card']
    return proc, card, card['cvts']


def resolved_card(client, cid):
    for proc in client.get('/api/processors').get_json()['resolved']:
        for slot in proc['slots']:
            if slot['card'] and slot['card']['id'] == cid:
                return slot['card']
    raise AssertionError(f'no card {cid}')


def socket_numbers(card):
    return [p['number'] for p in card['ports']]


def screens(*pairs):
    return [{'layerId': lid, 'name': name, 'ports': n, 'platform': plat}
            for lid, name, n, plat in pairs]


def resolve(client, sc):
    resp = client.post('/api/port-assignments/resolve', json={'screens': sc})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()['resolution']


def attach(client, lid, cid, sc, first=None, last=None):
    body = {'layerId': lid, 'cardId': cid, 'screens': sc}
    if first is not None:
        body['firstPort'] = first
    if last is not None:
        body['lastPort'] = last
    resp = client.post('/api/port-assignments/place-overflow', json=body)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()['resolution']


def summary(res, cid):
    return next(c for c in res['cards'] if c['cardId'] == cid)


def ports_of(res, lid):
    scr = next(s for s in res['screens'] if s['layerId'] == lid)
    return [p['port'] for p in scr['ports']], scr['unplaced']


def pins(client):
    state = client.get('/api/project').get_json().get(assignment.STATE_KEY)
    return sorted((p['layerId'], p['index'], p['port'])
                  for p in (state or {}).get('pins') or [])


# ── 1. The set is the catalog's ───────────────────────────────────────────

def test_the_box_fed_set_is_read_off_the_catalog():
    """is_box_fed reads `requiresDistribution` and nothing else, and
    box_fed_device_ids is exactly the processors that carry it. The
    ruling's named units are in the set; the HELIOS Jr is not."""
    flagged = catalog.box_fed_device_ids()
    expected = sorted(d['id'] for d in catalog.devices('processor')
                      if d.get('requiresDistribution'))
    assert flagged == expected and flagged, flagged
    for device_id in (SX40, HELIOS_8K, 'megapixel-helios-4k'):
        assert device_id in flagged, f'{device_id} is not box-fed: {flagged}'
    assert 'megapixel-helios-jr' not in flagged, (
        'the HELIOS Jr has its own copper ports and is not flagged')
    assert catalog.is_box_fed(catalog.get_device(SX40)) is True
    assert catalog.is_box_fed(catalog.get_device('megapixel-helios-jr')) is False
    assert catalog.is_box_fed({}) is False and catalog.is_box_fed(None) is False
    # Every member is a processor, not a box or a card.
    kinds = {d['id']: d.get('kind') for d in catalog.devices()}
    assert all(kinds[i] == 'processor' for i in flagged), flagged
    # And the rule is the flag: a device with the flag is box-fed whatever
    # else it says, a device without it is not.
    assert catalog.is_box_fed({'requiresDistribution': True})
    assert not catalog.is_box_fed({'trunks': 4, 'defaultCvt': XD})


# ── 2. Only the boxes' spans are sockets ──────────────────────────────────

def test_a_stocked_sx40_has_no_loose_sockets(client):
    state = add_processor(client, SX40)
    _proc, card, boxes = unit(state)
    assert card['boxFed'] is True
    assert len(boxes) == 4
    assert socket_numbers(card) == list(range(1, 41))
    assert all(p['cvtId'] for p in card['ports']), (
        'a port of a stocked SX40 sits outside every box')
    spans = sorted(n for b in boxes for n in (p['number'] for p in b['ports']))
    assert spans == socket_numbers(card)
    res = resolve(client, screens(('1', 'Wall', 4, 'brompton')))
    assert (summary(res, card['id'])['capacity'],
            summary(res, card['id'])['free']) == (40, 40)


def test_removing_box_b_takes_its_ten_sockets_and_the_pins_on_them(client):
    """LEFT on B's 11-13, CENTER on C's 21-22. Delete B: 11-20 vanish from
    the resolved card, its labels and the summary; LEFT's pins are pruned
    and named in the reply, CENTER's stand; A, C and D keep their trunks
    and their sockets; nothing outside a box can be placed onto."""
    left = add_layer(client, 'LEFT')
    center = add_layer(client, 'CENTER', x=1000)
    state = add_processor(client, SX40)
    proc, card, boxes = unit(state)
    pid, cid = proc['id'], card['id']
    box_b = boxes[1]
    assert box_b['displayTitle'] == 'Tessera XD B'
    sc = screens((left, 'LEFT', 3, 'brompton'), (center, 'CENTER', 2, 'brompton'))
    attach(client, left, cid, sc, first=11, last=20)
    res = attach(client, center, cid, sc, first=21, last=30)
    assert ports_of(res, left) == ([11, 12, 13], [])
    assert ports_of(res, center) == ([21, 22], [])

    resp = client.delete(f'/api/processors/{pid}/cvts/{box_b["id"]}')
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body['note'] == \
        'Removed box Tessera XD B - 3 ports of LEFT are unplaced again'
    assert sorted((p['layerId'], p['port'])
                  for p in body['portAssignments']['pins']) == \
        [(center, 21), (center, 22)]

    # the sockets: 1-10 and 21-40, nothing in between, on the card, on its
    # labels and on the summary
    after = body['resolved'][0]['slots'][0]['card']
    survivors = list(range(1, 11)) + list(range(21, 41))
    assert socket_numbers(after) == survivors
    assert all(p['cvtId'] for p in after['ports'])
    assert after['defined'] == 30 and after['trunksFree'] == 1
    assert [(b['displayTitle'], b['firstPort'], b['trunkIndex'])
            for b in after['cvts']] == \
        [('Tessera XD A', 1, 0), ('Tessera XD C', 21, 2), ('Tessera XD D', 31, 3)], (
            'a surviving box slid onto the removed trunk')
    res = resolve(client, sc)
    summ = summary(res, cid)
    assert sorted(int(k) for k in summ['labels']) == survivors
    assert (summ['capacity'], summ['used'], summ['free']) == (30, 2, 28)
    assert ports_of(res, left) == ([None, None, None], [0, 1, 2]), (
        'LEFT still reads placed on sockets that are gone')
    assert ports_of(res, center) == ([21, 22], [])
    assert pins(client) == [(center, 0, 21), (center, 1, 22)]

    # nothing outside a box is offered: a hand placement onto 15 is
    # refused in the device's own words, and a fill skips 11-20
    resp = client.post('/api/port-assignments/place', json={
        'layerId': left, 'index': 0, 'cardId': cid, 'port': 15, 'screens': sc})
    assert resp.status_code == 409, resp.get_data(as_text=True)
    assert 'no port 15' in resp.get_json()['error'], resp.get_json()
    assert 'inside a breakout box' in resp.get_json()['error']
    filler = add_layer(client, 'FILLER', x=2000)
    sc2 = sc + screens((filler, 'FILLER', 8, 'brompton'))
    attach(client, filler, cid, sc2, first=1, last=10)
    res = attach(client, left, cid, sc2)
    assert ports_of(res, filler)[0] == list(range(1, 9))
    assert ports_of(res, left) == ([9, 10, 23], []), (
        'the fill landed on a socket no box delivers')

    # a box added back takes the empty trunk and its ten come back
    state = add_box(client, pid, cid, XD)
    _proc, card, boxes = unit(state)
    assert socket_numbers(card) == list(range(1, 41))
    assert [(b['displayTitle'], b['firstPort']) for b in boxes][-1] == \
        ('Tessera XD B', 11)


def test_a_box_delete_with_no_pins_on_it_says_nothing(client):
    state = add_processor(client, SX40)
    proc, card, boxes = unit(state)
    resp = client.delete(f'/api/processors/{proc["id"]}/cvts/{boxes[3]["id"]}')
    assert resp.status_code == 200
    body = resp.get_json()
    assert 'note' not in body and 'portAssignments' not in body
    assert socket_numbers(body['resolved'][0]['slots'][0]['card']) == \
        list(range(1, 31))


def test_the_helios_8k_the_same(client):
    """A HELIOS Standard 8K arrives with no box and shows NO sockets - its
    eight fiber outs are trunks, not fixture ports. An RS12 on it is
    twelve sockets; a wall on six of them; delete the box and the sockets,
    the labels and the pins go with it, named in the reply."""
    wall = add_layer(client, 'WALL')
    state = add_processor(client, HELIOS_8K)
    proc, card, boxes = unit(state)
    pid, cid = proc['id'], card['id']
    assert card['boxFed'] is True and boxes == []
    assert socket_numbers(card) == [], (
        'a boxless HELIOS lists ports of its own')
    sc = screens((wall, 'WALL', 6, 'megapixel-1g'))
    res = resolve(client, sc)
    assert summary(res, cid)['capacity'] == 0

    state = add_box(client, pid, cid, RS12)
    _proc, card, boxes = unit(state)
    assert len(boxes) == 1
    assert socket_numbers(card) == [p['number'] for p in boxes[0]['ports']]
    assert socket_numbers(card)[:6] == [1, 2, 3, 4, 5, 6]
    res = attach(client, wall, cid, sc)
    assert ports_of(res, wall) == ([1, 2, 3, 4, 5, 6], [])

    resp = client.delete(f'/api/processors/{pid}/cvts/{boxes[0]["id"]}')
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body['note'].startswith('Removed box ')
    assert body['note'].endswith(' - 6 ports of WALL are unplaced again'), body
    assert body['portAssignments']['pins'] == []
    assert socket_numbers(body['resolved'][0]['slots'][0]['card']) == []
    res = resolve(client, sc)
    assert summary(res, cid)['labels'] == {}
    assert summary(res, cid)['capacity'] == 0
    assert ports_of(res, wall) == ([None] * 6, [0, 1, 2, 3, 4, 5])
    assert pins(client) == []


def test_an_unflagged_unit_keeps_its_loose_ports_after_a_box_delete(client):
    """The MX40 Pro's forty are on its face; a CVT10 on OPT 1 is another
    place to plug into 1-10. Delete the box and the ports, the labels, the
    summary and the pins stand exactly as they were - no note, no
    pruning."""
    wall = add_layer(client, 'WALL')
    state = add_processor(client, MX40)
    proc, card, boxes = unit(state)
    pid, cid = proc['id'], card['id']
    assert card['boxFed'] is False and boxes == []
    assert socket_numbers(card) == list(range(1, 41))
    state = add_box(client, pid, cid, CVT10)
    _proc, card, boxes = unit(state)
    assert [p['number'] for p in boxes[0]['ports']] == list(range(1, 11))
    sc = screens((wall, 'WALL', 4, 'novastar-coex-1g'))
    res = attach(client, wall, cid, sc, first=1, last=10)
    assert ports_of(res, wall) == ([1, 2, 3, 4], [])
    before = summary(res, cid)

    resp = client.delete(f'/api/processors/{pid}/cvts/{boxes[0]["id"]}')
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert 'note' not in body and 'portAssignments' not in body
    after = body['resolved'][0]['slots'][0]['card']
    assert socket_numbers(after) == list(range(1, 41))
    assert after['cvts'] == []
    res = resolve(client, sc)
    # The card's figures stand; only the deleted box's own per-box count
    # (the summary's `boxes`, the box header's n/N) goes with the box.
    card_only = lambda s: {k: v for k, v in s.items() if k != 'boxes'}
    assert card_only(summary(res, cid)) == card_only(before)
    assert before['boxes'] == {boxes[0]['id']: {'taken': 4, 'sockets': 10}}
    assert summary(res, cid)['boxes'] == {}
    assert ports_of(res, wall) == ([1, 2, 3, 4], [])
    assert pins(client) == [(wall, i, i + 1) for i in range(4)]
    raw = client.get('/api/project').get_json()['processors'][0]
    assert 'trunk' not in str(raw['slots'][0]['card']), (
        'an unflagged unit was stamped with trunk holds')


def test_undo_brings_the_box_and_its_pins_back(client):
    """Undo is the whole-project PUT of the snapshot before the delete: the
    box is back on trunk B, LEFT is back on 11-13, and the snapshot's
    boxes carry no trunk stamps (they predate the delete)."""
    left = add_layer(client, 'LEFT')
    state = add_processor(client, SX40)
    proc, card, boxes = unit(state)
    pid, cid = proc['id'], card['id']
    sc = screens((left, 'LEFT', 3, 'brompton'))
    attach(client, left, cid, sc, first=11, last=20)
    snapshot = copy.deepcopy(client.get('/api/project').get_json())
    assert len(snapshot[assignment.STATE_KEY]['pins']) == 3

    resp = client.delete(f'/api/processors/{pid}/cvts/{boxes[1]["id"]}')
    assert resp.status_code == 200
    assert pins(client) == []
    assert len(resolved_card(client, cid)['cvts']) == 3

    resp = client.put('/api/project', json=snapshot)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    card = resolved_card(client, cid)
    assert [b['id'] for b in card['cvts']] == [b['id'] for b in boxes]
    assert socket_numbers(card) == list(range(1, 41))
    assert pins(client) == [(left, 0, 11), (left, 1, 12), (left, 2, 13)]
    res = resolve(client, sc)
    assert ports_of(res, left) == ([11, 12, 13], [])
    raw = client.get('/api/project').get_json()['processors'][0]
    assert all('trunk' not in b for b in raw['slots'][0]['card']['cvts'])


# ── 3. The tray ───────────────────────────────────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_dock_drag_data import (  # noqa: E402
    PINS_JS, dock_grip_center, drag, port_point, unplaced, wall_pins)

# An SX40 as it leaves the shop (four XDs), a Brompton-programmed WALL and a
# FILLER wall tall enough to fill a whole box under any port figure.
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
    const send = (url, method, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body)}).then(r => r.json());
    const walls = [
        ['WALL', 12, 6, 0, 0],
        ['FILLER', 12, 30, 0, 1500],
    ];
    const made = {};
    for (const [name, cols, rows, ox, oy] of walls) {
        const r = await send('/api/layer/add', 'POST', {name, columns: cols,
            rows, cabinet_width: 200, cabinet_height: 200,
            offset_x: ox, offset_y: oy});
        await send(`/api/layer/${r.id}`, 'PUT', {processorType: 'brompton'});
        made[name] = r.id;
    }
    const added = await send('/api/processors', 'POST',
                             {deviceId: '%s'});
    const proc = added.resolved[0];
    const card = proc.slots[0].card;
    const app = window.app;
    const p = await (await fetch('/api/project')).json();
    app.project = p;
    app.currentLayer = p.layers[0];
    app.selectedLayerIds = new Set([p.layers[0].id]);
    await app.refreshProcessors();
    app.renderLayers();
    const r = window.canvasRenderer;
    r.zoom = 0.25; r.panX = 60; r.panY = 40; r.render();
    await app.refreshPortAssignment();
    app.resetHistory('Dock Seed');
    const need = {};
    for (const l of app.project.layers) need[l.name] = app.getLayerPortsRequired(l);
    return {wall: made.WALL, filler: made.FILLER, procId: proc.id,
            cardId: card.id, boxes: card.cvts.map(b => b.id), need};
}""" % SX40

OPEN_GEAR_JS = """(popId) => {
    const gear = document.querySelector(`[data-hwpop="${popId}"]`);
    if (!gear) return false;
    gear.click();
    const pop = document.getElementById('hw-gear-popover');
    return !!(pop && pop.style.display !== 'none');
}"""

# The tray as drawn for one card: the chips outside every box (the loose
# grid), the boxes with their headers, and whether a given socket's chip
# is anywhere in the unit.
TRAY_JS = """(cardId) => {
    const head = document.querySelector(`[data-hwdock="card-${cardId}"]`);
    const unit = head && head.closest('.hw-dock-unit, .hw-dock-card')
        || (head && head.parentElement);
    if (!unit) return null;
    const chips = [...unit.querySelectorAll('.hw-dock-tile')];
    const loose = chips.filter(t => !t.closest('.hw-dock-box'));
    const boxes = [...unit.querySelectorAll('.hw-dock-box')].map(b => ({
        title: (b.querySelector('.hw-dock-name') || {}).placeholder
            || b.querySelector('[data-hwdock]').textContent.trim(),
        chips: b.querySelectorAll('.hw-dock-tile').length,
    }));
    return {
        loose: loose.map(t => t.dataset.lrdTile),
        boxes,
        has15: !!unit.querySelector(`[data-lrd-tile="port-${cardId}-15"]`),
    };
}"""

TOASTS_JS = """() => [...document.querySelectorAll('#app-toast-host div')]
    .map(t => t.textContent)"""

ADD_BOX_JS = """(cardId) => {
    const pop = document.getElementById('hw-gear-popover');
    if (!pop || pop.style.display === 'none') return null;
    const sel = pop.querySelector(`[data-lrd-field="processor-cvt-add-${cardId}"]`);
    if (!sel) return {picker: false};
    const btn = sel.parentElement.querySelector('button');
    return {picker: true, options: [...sel.options].map(o => o.value),
            plus: !!btn && btn.textContent === '+' && !btn.disabled};
}"""


@pytest.fixture(scope="module")
def sx_page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(1200)
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(600)
    assert len(ids['boxes']) == 4, ids
    assert ids['need']['WALL'] >= 3, (
        f'the seed must make WALL at least a three-port screen: {ids["need"]}')
    assert ids['need']['FILLER'] >= 10, (
        f'the seed must make FILLER at least a ten-port screen: {ids["need"]}')
    yield pg, ids
    context.close()


def test_the_tray_after_remove_box_shows_the_trunk_empty_and_toasts(sx_page):
    """WALL's first three ports on box B. Remove box from B's gear: the
    toast names the box and the ports; the card draws A, C and D and NO
    loose chips (socket 15 is nowhere); the card's gear still offers a
    box to add; WALL reads unplaced on client and server; a card drag then
    lands only inside the boxes that remain - A full, it skips 11-20 and
    lands on C - and undo brings B and its pins back."""
    page, ids = sx_page
    wall, card, filler = ids['wall'], ids['cardId'], ids['filler']
    box_b = ids['boxes'][1]
    page.evaluate("""async (ids) => {
        await window.app._assignmentRequest(
            '/api/port-assignments/place-overflow', 'POST',
            {layerId: String(ids.wall), cardId: ids.cardId,
             firstPort: 11, lastPort: 20, lastIndex: 2});
        window.app.resetHistory('Dock Seed');
    }""", ids)
    page.wait_for_timeout(500)
    assert wall_pins(page, wall) == [(0, 11), (1, 12), (2, 13)], (
        page.evaluate(PINS_JS))
    before = page.evaluate(TRAY_JS, card)
    assert before and before['loose'] == [] and len(before['boxes']) == 4, before
    assert before['has15'] is True

    assert page.evaluate(OPEN_GEAR_JS, f'box-{box_b}'), 'the box gear did not open'
    page.locator('#hw-gear-popover .hw-pop-remove').click()
    page.wait_for_timeout(1200)

    toasts = page.evaluate(TOASTS_JS)
    assert 'Removed box Tessera XD B - 3 ports of WALL are unplaced again' \
        in toasts, toasts
    after = page.evaluate(TRAY_JS, card)
    assert after['loose'] == [], (
        f'the removed box\'s sockets came back as loose chips: {after}')
    assert after['has15'] is False, after
    assert [b['chips'] for b in after['boxes']] == [10, 10, 10], after
    assert wall_pins(page, wall) == [], page.evaluate(PINS_JS)
    assert wall_pins(page, wall, from_server=True) == []
    assert unplaced(page, wall) == list(range(ids['need']['WALL']))
    assert page.evaluate(
        "() => window.app._assignment.cards.find(c => c.cardId === '%s').free"
        % card) == 30

    # the affordance to add a box back is where it always was
    assert page.evaluate(OPEN_GEAR_JS, f'card-{card}'), 'the card gear did not open'
    offer = page.evaluate(ADD_BOX_JS, card)
    assert offer and offer['picker'] and offer['plus'], offer
    assert XD in offer['options'], offer
    page.evaluate("() => window.app._hwPopoverClose()")
    page.wait_for_timeout(200)

    # a card drag offers only sockets inside the remaining boxes: fill A
    # with FILLER, then the drag over WALL port 3 lands 21-23 on C
    page.evaluate("""async (ids) => {
        await window.app._assignmentRequest(
            '/api/port-assignments/place-overflow', 'POST',
            {layerId: String(ids.filler), cardId: ids.cardId,
             firstPort: 1, lastPort: 10});
    }""", ids)
    page.wait_for_timeout(500)
    assert len(wall_pins(page, filler)) == 10, page.evaluate(PINS_JS)
    sx, sy = dock_grip_center(page, f'card-{card}')
    tgt = port_point(page, wall, 3)
    mid = drag(page, sx, sy, tgt['x'], tgt['y'])
    assert mid['target']['kind'] == 'screen', mid
    assert mid['target']['nums'] == [1, 2, 3], mid
    assert mid['pill'] == {'text': '3 ports', 'bad': False}, mid
    assert wall_pins(page, wall) == [(0, 21), (1, 22), (2, 23)], (
        f'the drop landed outside the remaining boxes: {page.evaluate(PINS_JS)}')
    assert wall_pins(page, wall, from_server=True) == [(0, 21), (1, 22), (2, 23)]

    # undo the drop and the removal (the FILLER fill above took no history
    # entry): B is back, and WALL's pins on it
    for _ in range(2):
        page.evaluate("() => window.app.undo()")
        page.wait_for_timeout(900)
    restored = page.evaluate(TRAY_JS, card)
    assert len(restored['boxes']) == 4 and restored['has15'], restored
    assert restored['loose'] == [], restored
    assert wall_pins(page, wall) == [(0, 11), (1, 12), (2, 13)], (
        page.evaluate(PINS_JS))
    assert wall_pins(page, wall, from_server=True) == [(0, 11), (1, 12), (2, 13)]
