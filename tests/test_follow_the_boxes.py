"""On a box-fed card, every count follows the ports the boxes give.

The owner's rulings (2026-10-04):

* "Follow the boxes" - on a box-fed device (processor_catalog.is_box_fed:
  the fiber-only cards, the SX40, the HELIOS Standard, the QD-S) the
  capacity row, the processor's sum, the usable count and the split read
  ONLY the ports the boxes deliver, never the mode count. A bare enhanced
  H_4xfiber is 0 / 0; one CVT10 on it is 10 / 10. resolve_card reports it
  as the card's `ceiling` (its reach); `modeCeiling` keeps the 40.
* "we should throw an error but only do real ports beyond that" - a box
  missing between boxes leaves its trunk's ports gone. The card says so
  ("OPT 2 has no box - ports 11-20 are missing.", in its gear and as an
  error on the dock strip) and the split runs over the ports that exist:
  CVT10s on OPT 1, 3 and 4 are ports 1-10 and 21-40, so 1-10 and 21-25
  are backed by 26-40, and nothing is paired onto 11-20.
* A stocked SX40 - four XDs, every trunk - reads exactly as before: 40.

Run locally:
    python3 -m pytest tests/test_follow_the_boxes.py -q --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import processor_catalog as catalog  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


ENHANCED = 'novastar-card-h-4xfiber-enhanced'
CVT10 = 'novastar-cvt10'
SX40 = 'brompton-sx40'


# ── helpers ───────────────────────────────────────────────────────────────

def h9_with(client, card_device=ENHANCED):
    st = client.post('/api/processors', json={'deviceId': 'novastar-h9'}
                     ).get_json()
    pid = st['processors'][-1]['id']
    st = client.put(f'/api/processors/{pid}/slots/0',
                    json={'deviceId': card_device}).get_json()
    cid = next(p for p in st['processors'] if p['id'] == pid
               )['slots'][0]['card']['id']
    return pid, cid


def tree(client):
    return client.get('/api/processors').get_json()['resolved']


def proc_of(client, pid):
    return next(p for p in tree(client) if p['id'] == pid)


def card_of(client, cid):
    for proc in tree(client):
        for slot in proc['slots']:
            if slot['card'] and slot['card']['id'] == cid:
                return slot['card']
    raise AssertionError(f'no card {cid}')


def add_box(client, pid, cid):
    resp = client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                       json={'deviceId': CVT10, 'pair': False})
    assert resp.status_code == 201, resp.get_data(as_text=True)


def set_halves(client, pid, cid):
    assert client.put(f'/api/processors/{pid}',
                      json={'redundancy': True}).status_code == 200
    resp = client.put(f'/api/processors/{pid}/cards/{cid}',
                      json={'redundancyMode': 'halves'})
    assert resp.status_code == 200, resp.get_data(as_text=True)


def backups(card):
    """{main: backing port} off the resolved card's ports."""
    return {p['number']: p['backedBy']['port'] for p in card['ports']
            if p.get('backedBy')}


def gap_card(client):
    """An enhanced card with CVT10s on OPT 1, 3 and 4 - OPT 2's box put on
    and taken off again, which leaves its trunk empty (the boxes hold their
    trunks on a box-fed card)."""
    pid, cid = h9_with(client)
    for _ in range(4):
        add_box(client, pid, cid)
    box_b = card_of(client, cid)['cvts'][1]
    assert box_b['trunkIndex'] == 1
    assert client.delete(f'/api/processors/{pid}/cvts/{box_b["id"]}'
                         ).status_code == 200
    return pid, cid


# ── 1. The counts follow the boxes ────────────────────────────────────────

def test_a_bare_card_reads_0_of_0_and_each_box_adds_its_ports(client):
    pid, cid = h9_with(client)
    card = card_of(client, cid)
    assert (card['defined'], card['ceiling'], card['modeCeiling']) \
        == (0, 0, 40)
    assert proc_of(client, pid)['ceiling'] == 0
    for n in (1, 2, 3, 4):
        add_box(client, pid, cid)
        card = card_of(client, cid)
        assert (card['defined'], card['ceiling'], card['modeCeiling']) \
            == (10 * n, 10 * n, 40)
        # the processor's row sums the cards' reach
        assert proc_of(client, pid)['ceiling'] == 10 * n
    res = client.post('/api/port-assignments/resolve', json={
        'screens': [{'layerId': 'W', 'name': 'W', 'ports': 2}]}
    ).get_json()['resolution']
    assert next(c for c in res['cards'] if c['cardId'] == cid
                )['capacity'] == 40


def test_the_split_and_usable_move_with_the_boxes(client):
    pid, cid = h9_with(client)
    set_halves(client, pid, cid)
    card = card_of(client, cid)
    assert card['redundancyShape']['usable'] == 0
    assert backups(card) == {} and card['halvesSpans'] is None
    add_box(client, pid, cid)
    card = card_of(client, cid)
    assert backups(card) == {n: n + 5 for n in range(1, 6)}
    assert card['redundancyShape']['usable'] == 5
    assert card['halvesSpans'] == {'mains': '1-5', 'backs': '6-10'}
    add_box(client, pid, cid)
    card = card_of(client, cid)
    assert backups(card) == {n: n + 10 for n in range(1, 11)}
    assert card['redundancyShape']['usable'] == 10
    for _ in range(2):
        add_box(client, pid, cid)
    card = card_of(client, cid)
    # all four boxes: the old 40-port split exactly
    assert backups(card) == {n: n + 20 for n in range(1, 21)}
    assert card['redundancyShape']['usable'] == 20


# ── 2. A box missing between boxes ────────────────────────────────────────

def test_a_box_missing_between_boxes_is_named_and_its_ports_are_gone(client):
    pid, cid = gap_card(client)
    card = card_of(client, cid)
    numbers = [p['number'] for p in card['ports']]
    assert numbers == list(range(1, 11)) + list(range(21, 41))
    assert (card['defined'], card['ceiling']) == (30, 30)
    assert [g['message'] for g in card['gaps']] \
        == ['OPT 2 has no box - ports 11-20 are missing.']
    assert card['gaps'][0]['ports'] == list(range(11, 21))
    # ...and on the dock strip, as an error with the card's name on it
    res = client.post('/api/port-assignments/resolve', json={
        'screens': [{'layerId': 'W', 'name': 'W', 'ports': 2}]}
    ).get_json()['resolution']
    gap = [i for i in res['issues'] if i['kind'] == 'card-trunk-gap']
    assert len(gap) == 1, res['issues']
    assert gap[0]['message'].endswith(
        ': OPT 2 has no box - ports 11-20 are missing.'), gap
    # a box back on OPT 2 closes it
    add_box(client, pid, cid)
    card = card_of(client, cid)
    assert card['gaps'] == [] and card['ceiling'] == 40


def test_the_split_runs_over_the_ports_that_exist(client):
    """The ruling's own example: 1-10 and 21-25 backed by 26-40."""
    pid, cid = gap_card(client)
    set_halves(client, pid, cid)
    card = card_of(client, cid)
    mains = list(range(1, 11)) + list(range(21, 26))
    assert backups(card) == dict(zip(mains, range(26, 41)))
    assert card['redundancyShape']['usable'] == 15
    assert card['halvesSpans'] == {'mains': '1-10, 21-25', 'backs': '26-40'}
    assert not any(11 <= n <= 20 for pair in backups(card).items()
                   for n in pair)


def test_an_empty_trunk_past_the_last_box_is_no_gap(client):
    """Two boxes on a four-OPT card is a card not finished yet."""
    pid, cid = h9_with(client)
    add_box(client, pid, cid)
    add_box(client, pid, cid)
    assert card_of(client, cid)['gaps'] == []


def test_the_rule_is_one_helper():
    assert catalog.halves_split(range(1, 17)) \
        == [(n, n + 8) for n in range(1, 9)]
    # odd: the middle port is a main with no backup, as before
    assert catalog.halves_split(range(1, 12)) \
        == [(n, n + 6) for n in range(1, 6)]
    assert catalog.halves_split([]) == []


# ── 3. The SX40 reads as before ───────────────────────────────────────────

def test_a_stocked_sx40_reads_as_before(client):
    st = client.post('/api/processors', json={'deviceId': SX40}).get_json()
    proc = st['resolved'][-1]
    card = proc['slots'][0]['card']
    assert len(card['cvts']) == 4
    assert (card['defined'], card['ceiling'], card['modeCeiling']) \
        == (40, 40, 40)
    assert proc['ceiling'] == 40 and card['gaps'] == []
    resp = client.put(f'/api/processors/{proc["id"]}',
                      json={'redundancy': True})
    card = next(p for p in resp.get_json()['resolved']
                if p['id'] == proc['id'])['slots'][0]['card']
    # A to B and C to D: 20 usable, 1 returns on 11, 21 on 31
    assert card['redundancyShape']['usable'] == 20
    assert backups(card)[1] == 11 and backups(card)[21] == 31


# ── 4. The gear says it ───────────────────────────────────────────────────

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
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)})
        .then(r => r.json());
    let st = await j('POST', '/api/processors', {deviceId: 'novastar-h9'});
    const pid = st.processors[0].id;
    st = await j('PUT', `/api/processors/${pid}/slots/0`,
                 {deviceId: '%s'});
    const cid = st.processors[0].slots[0].card.id;
    await j('PUT', `/api/processors/${pid}`, {redundancy: true});
    await j('PUT', `/api/processors/${pid}/cards/${cid}`,
            {redundancyMode: 'halves'});
    const app = window.app;
    app.project = await (await fetch('/api/project')).json();
    await app.refreshProcessors();
    app.renderLayers();
    app.resetHistory('Follow Seed');
    return {pid, cid};
}""" % ENHANCED

# The card gear's capacity row, its gap lines and the Split chip's tip,
# and the proc gear's capacity row - opened fresh each time.
GEAR_JS = """async ([pid, cid]) => {
    const app = window.app;
    await app.refreshProcessors();
    const open = (id) => {
        app._hwPopoverClose();
        const gear = document.querySelector(`[data-hwpop="${id}"]`);
        if (!gear) return null;
        gear.click();
        return document.getElementById('hw-gear-popover');
    };
    let pop = open(`card-${cid}`);
    const rows = [...pop.querySelectorAll('div')].map(d => d.textContent);
    const cap = rows.find(t => / ports( - over capacity)?$/.test(t)
                          && /^\\d+ \\/ \\d+/.test(t));
    const gaps = [...pop.querySelectorAll('.hw-pop-gap')]
        .map(d => d.textContent);
    pop = open(`proc-${pid}`);
    const chip = pop.querySelector('[data-mode="halves"]');
    const prows = [...pop.querySelectorAll('div')].map(d => d.textContent);
    const pcap = prows.find(t => /^\\d+ \\/ \\d+ ports$/.test(t));
    app._hwPopoverClose();
    const strip = [...document.querySelectorAll('.hw-dock-issue')]
        .map(r => r.textContent);
    return {cap, gaps, tip: chip ? chip.title : null, pcap, strip};
}"""

BOX_JS = """async ([pid, cid, verb, box]) => {
    if (verb === 'add') {
        await fetch(`/api/processors/${pid}/cards/${cid}/cvts`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({deviceId: 'novastar-cvt10', pair: false})});
    } else {
        await fetch(`/api/processors/${pid}/cvts/${box}`, {method: 'DELETE'});
    }
    await window.app.refreshProcessors();
    await window.app.refreshPortAssignment();
    const found = window.app._dockFindCard(cid);
    return found.card.cvts.map(b => b.id);
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
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(800)
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(600)
    yield pg, ids, errors
    context.close()


def test_the_gear_follows_the_boxes_and_says_the_gap(page):
    pg, ids, errors = page
    pid, cid = ids['pid'], ids['cid']
    gear = pg.evaluate(GEAR_JS, [pid, cid])
    assert gear['cap'] == '0 / 0 ports', gear
    assert gear['pcap'] == '0 / 0 ports', gear
    assert gear['gaps'] == []
    boxes = []
    for n in (1, 2, 3, 4):
        boxes = pg.evaluate(BOX_JS, [pid, cid, 'add', None])
        gear = pg.evaluate(GEAR_JS, [pid, cid])
        assert gear['cap'] == f'{10 * n} / {10 * n} ports', gear
        assert gear['pcap'] == f'{10 * n} / {10 * n} ports', gear
    assert gear['tip'].startswith(
        'Ports 21-40 carry the returns of 1-20.'), gear
    # OPT 2's box off: the hole is said in the gear and on the strip, and
    # the split's tip names the ports that exist
    pg.evaluate(BOX_JS, [pid, cid, 'del', boxes[1]])
    pg.wait_for_timeout(300)
    gear = pg.evaluate(GEAR_JS, [pid, cid])
    assert gear['cap'] == '30 / 30 ports', gear
    assert gear['gaps'] == ['OPT 2 has no box - ports 11-20 are missing.']
    assert gear['tip'] == 'Ports 26-40 carry the returns of 1-10, 21-25.', gear
    assert any(t.endswith(': OPT 2 has no box - ports 11-20 are missing.')
               for t in gear['strip']), gear['strip']
    assert errors == []
