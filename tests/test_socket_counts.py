"""Every "sockets in use" count counts every socket taken - primary or return.

The owner's report (2026-09-24): "there is a counting issue. right now it
shows 11/40 ports being used when I have 11 primary and 11 redundant. so
that means it's 22/40". The n of every n/N the app prints for a card or a
breakout box is the sockets on it that hold a primary OR carry a placed
primary's return (port_assignment._taken_sockets, served as the card
summary's `taken` and per box as `boxes`). A return counts where its SOCKET
lives, whatever shape put it there:

* SX40 fixed pairing / sequential / halves - the return socket is on the
  same card (an SX40's box B carries box A's returns), so it counts there;
* per-card 1:1 and whole-unit mirror - the returns sit on the partner
  card, so they count on the partner and never on the main;
* manual - on whichever card the picked socket is.

A return socket whose main nobody placed carries nothing: it is reserved
(out of `free`, as it always was) but not taken. `used` stays the
primaries alone and `free` is unchanged, so taken + free + the reserved
returns of the free mains = the sockets there.

Run locally:
    python3 -m pytest tests/test_socket_counts.py -q --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# ── helpers ───────────────────────────────────────────────────────────────

def add_processor(client, device_id):
    resp = client.post('/api/processors', json={'deviceId': device_id})
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


def cards_of(state):
    return [slot['card']['id'] for proc in state['resolved']
            for slot in proc.get('slots') or [] if slot.get('card')]


def screens(name, count):
    return [{'layerId': name, 'name': name, 'ports': count}]


def attach(client, layer_id, card_id, sc, first=None, last=None):
    body = {'layerId': layer_id, 'cardId': card_id, 'screens': sc}
    if first is not None:
        body['firstPort'] = first
    if last is not None:
        body['lastPort'] = last
    resp = client.post('/api/port-assignments/place-overflow', json=body)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()['resolution']


def summary(res, card_id):
    return next(c for c in res['cards'] if c['cardId'] == card_id)


def counts(res, card_id):
    s = summary(res, card_id)
    return {k: s[k] for k in ('capacity', 'used', 'backing', 'taken', 'free')}


def mx20(client, redundancy=True, mode=None):
    """One MX20 (six sockets on its face)."""
    state = add_processor(client, 'novastar-mx20')
    pid = state['resolved'][-1]['id']
    card = cards_of(state)[-1]
    if redundancy:
        client.put(f'/api/processors/{pid}', json={'redundancy': True})
    if mode:
        resp = client.put(f'/api/processors/{pid}/cards/{card}',
                          json={'redundancyMode': mode})
        assert resp.status_code == 200, resp.get_data(as_text=True)
    return pid, card


# ── 1. The server's count, in every redundancy shape ──────────────────────

def test_sequential_counts_each_primary_and_its_return(client):
    """Two primaries on a sequential six land on 1 and 3 and return on 2
    and 4: four sockets taken. Free stays the one main left (5) - its
    return (6) is reserved, not taken and not free."""
    _pid, card = mx20(client, mode='sequential')
    res = attach(client, 'Wall', card, screens('Wall', 2))
    assert counts(res, card) == {'capacity': 6, 'used': 2, 'backing': 3,
                                 'taken': 4, 'free': 1}


def test_a_sequential_card_full_of_pairs_is_taken_to_the_last_socket(client):
    _pid, card = mx20(client, mode='sequential')
    res = attach(client, 'Wall', card, screens('Wall', 3))
    assert counts(res, card) == {'capacity': 6, 'used': 3, 'backing': 3,
                                 'taken': 6, 'free': 0}


def test_halves_counts_the_back_half_returns_on_the_same_card(client):
    state = add_processor(client, 'novastar-h9')
    pid = state['resolved'][0]['id']
    resp = client.put(f'/api/processors/{pid}/slots/0',
                      json={'deviceId': 'novastar-card-h-16xrj45-2xfiber'})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    card = cards_of(resp.get_json())[0]
    client.put(f'/api/processors/{pid}', json={'redundancy': True})
    client.put(f'/api/processors/{pid}/cards/{card}',
               json={'redundancyMode': 'halves'})
    res = attach(client, 'Wall', card, screens('Wall', 3))
    assert counts(res, card) == {'capacity': 16, 'used': 3, 'backing': 8,
                                 'taken': 6, 'free': 5}


def test_the_sx40s_returns_count_on_the_box_they_land_on(client):
    """The owner's USC SR: eleven primaries on a redundant SX40 sit on
    A 1-10 and C 1; their returns on B 1-10 and D 1. 22/40, box by box
    10 + 10 + 1 + 1, and nine mains still free."""
    state = add_processor(client, 'brompton-sx40')
    pid = state['resolved'][0]['id']
    card = cards_of(state)[0]
    boxes = [b['id'] for b in state['resolved'][0]['slots'][0]['card']['cvts']]
    client.put(f'/api/processors/{pid}', json={'redundancy': True})
    res = attach(client, 'Wall', card, screens('Wall', 11))
    assert counts(res, card) == {'capacity': 40, 'used': 11, 'backing': 20,
                                 'taken': 22, 'free': 9}
    per_box = summary(res, card)['boxes']
    assert [(per_box[b]['taken'], per_box[b]['sockets']) for b in boxes] == \
        [(10, 10), (10, 10), (1, 10), (1, 10)]


def test_a_1to1_partner_carries_the_returns_not_the_main(client):
    """Per-card 1:1: three primaries on the main MX20 return on the
    partner's 1-3. The main reads 3 taken, the partner 3 - never 6 on the
    main - and the partner, all of whose sockets are spoken for by role,
    has nothing free."""
    main_pid, main_card = mx20(client)
    _bpid, backup_card = mx20(client, redundancy=False)
    resp = client.put(f'/api/processors/{main_pid}/cards/{main_card}',
                      json={'backupCardId': backup_card})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    res = attach(client, 'Wall', main_card, screens('Wall', 3))
    assert counts(res, main_card) == {'capacity': 6, 'used': 3,
                                      'backing': 0, 'taken': 3, 'free': 3}
    assert counts(res, backup_card) == {'capacity': 6, 'used': 0,
                                        'backing': 6, 'taken': 3, 'free': 0}


def test_a_manual_pick_counts_on_the_card_the_picked_socket_is_on(client):
    """Manual mode, the return picked on ANOTHER card: it counts there."""
    main_pid, main_card = mx20(client, mode='manual')
    _bpid, other = mx20(client, redundancy=False)
    resp = client.put(
        f'/api/processors/{main_pid}/cards/{main_card}/ports/1',
        json={'backup': {'cardId': other, 'port': 4}})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    res = attach(client, 'Wall', main_card, screens('Wall', 2))
    assert summary(res, main_card)['taken'] == 2
    assert summary(res, other)['taken'] == 1
    assert summary(res, other)['used'] == 0


def test_redundancy_off_counts_primaries_only(client):
    _pid, card = mx20(client, redundancy=False)
    res = attach(client, 'Wall', card, screens('Wall', 3))
    assert counts(res, card) == {'capacity': 6, 'used': 3, 'backing': 0,
                                 'taken': 3, 'free': 3}


# ── 2. The tray and the binder read the one count ─────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

# Two redundant SX40s: FULL keeps only boxes A and B (twenty sockets), FOUR
# keeps all four. WALL is a Brompton wall big enough to fill either.
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
    const made = {};
    for (const [name, oy] of [['WALL', 0], ['OTHER', 1500]]) {
        const r = await send('/api/layer/add', 'POST', {name, columns: 12,
            rows: 30, cabinet_width: 200, cabinet_height: 200,
            offset_x: 0, offset_y: oy});
        await send(`/api/layer/${r.id}`, 'PUT', {processorType: 'brompton'});
        made[name] = r.id;
    }
    const units = {};
    for (const name of ['FOUR', 'FULL']) {
        const added = await send('/api/processors', 'POST',
                                 {deviceId: 'brompton-sx40'});
        const proc = added.resolved[added.resolved.length - 1];
        await send(`/api/processors/${proc.id}`, 'PUT',
                   {name, redundancy: true});
        units[name] = {procId: proc.id, cardId: proc.slots[0].card.id,
                       boxes: proc.slots[0].card.cvts.map(b => b.id)};
    }
    for (const box of units.FULL.boxes.slice(2)) {
        await send(`/api/processors/${units.FULL.procId}/cvts/${box}`,
                   'DELETE', {});
    }
    units.FULL.boxes = units.FULL.boxes.slice(0, 2);
    const app = window.app;
    app.project = await (await fetch('/api/project')).json();
    await app.refreshProcessors();
    app.renderLayers();
    await app.refreshPortAssignment();
    const need = {};
    for (const l of app.project.layers) {
        need[l.name] = app.getLayerPortsRequired(l);
    }
    // Eleven primaries onto FOUR (A 1-10, C 1), ten onto FULL (A 1-10).
    await app._assignmentRequest('/api/port-assignments/place-overflow',
        'POST', {layerId: String(made.WALL), cardId: units.FOUR.cardId,
                 lastIndex: 10});
    await app._assignmentRequest('/api/port-assignments/place-overflow',
        'POST', {layerId: String(made.OTHER), cardId: units.FULL.cardId,
                 lastIndex: 9});
    app.resetHistory('Socket Count Seed');
    return {walls: made, units, need};
}"""

# A header's glance: the n/N text and the fill line's width.
GLANCE_JS = """(key) => {
    const head = document.querySelector(`[data-hwdock="${key}"]`);
    if (!head) return null;
    const use = head.querySelector('.hw-dock-unit-use');
    const bar = head.querySelector('.hw-dock-headbar > i');
    return {text: use && use.textContent,
            barW: bar && parseFloat(bar.style.width),
            over: !!(bar && bar.classList.contains('hw-dock-bar-over'))};
}"""

# The binder's Cards table rows for one processor, captured at the table
# builder (the drawing itself needs a whole book).
BINDER_ROWS_JS = """(procId) => {
    const app = window.app;
    const proc = (app._processorsResolved || []).find(p => p.id === procId);
    const cards = (proc.slots || []).filter(s => s && s.card)
        .map(s => ({slot: s.index, card: s.card}));
    const seen = [];
    app._bTableLines = (book, spec) => { seen.push(spec); return []; };
    app._bKvLines = () => [];
    app._bPullLines = () => [];
    try {
        app._bProcessorBlocks({list: {hardware: []}}, proc, cards);
    } finally {
        delete app._bTableLines;
        delete app._bKvLines;
        delete app._bPullLines;
    }
    const table = seen.find(s => s.title === 'Cards');
    return table ? table.rows.map(r => r.cells[3]) : null;
}"""


@pytest.fixture(scope="module")
def count_page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(800)
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(600)
    assert ids['need']['WALL'] >= 11 and ids['need']['OTHER'] >= 10, ids
    yield pg, ids
    context.close()


def test_the_sx40_header_counts_primaries_and_returns(count_page):
    """Eleven primaries in the fixed sequential pairing read 22/40."""
    page, ids = count_page
    four = ids['units']['FOUR']
    glance = page.evaluate(GLANCE_JS, f"card-{four['cardId']}")
    assert glance and glance['text'] == '22/40', glance
    assert abs(glance['barW'] - 55) < 0.5, glance


def test_each_box_header_counts_its_own_sockets(count_page):
    """A 10/10 (the mains), B 10/10 (their returns), C 1/10, D 1/10."""
    page, ids = count_page
    four = ids['units']['FOUR']
    texts = [(page.evaluate(GLANCE_JS, f'box-{b}') or {}).get('text')
             for b in four['boxes']]
    assert texts == ['10/10', '10/10', '1/10', '1/10'], texts


def test_a_unit_full_of_pairs_reads_full(count_page):
    """Ten primaries and their ten returns on a two-box SX40: 20/20 and a
    full fill line - the owner's USC SL, which read 10/20."""
    page, ids = count_page
    full = ids['units']['FULL']
    glance = page.evaluate(GLANCE_JS, f"card-{full['cardId']}")
    assert glance and glance['text'] == '20/20', glance
    assert glance['barW'] == 100 and not glance['over'], glance
    texts = [(page.evaluate(GLANCE_JS, f'box-{b}') or {}).get('text')
             for b in full['boxes']]
    assert texts == ['10/10', '10/10'], texts


def test_the_binder_cards_table_prints_the_same_count(count_page):
    page, ids = count_page
    rows = {name: page.evaluate(BINDER_ROWS_JS, unit['procId'])
            for name, unit in ids['units'].items()}
    assert rows == {'FOUR': ['22 / 40'], 'FULL': ['20 / 20']}, rows
