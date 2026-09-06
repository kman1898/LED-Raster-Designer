"""Data snakes and port home runs: where they are formed, typed and read.

"we need to have the same option for data homeruns. we can combine ports
into a snake as well as adding lengths to each if not snakes." (user,
2026-09-06). Of src/static/snake-mock.html the pick was "B to form it and A
to type it but can be made with both": the Alt-sweep across port chips forms
a snake by right-click (B), and the card's / box's cable sheet types the
names, home runs and the loose ports' lengths (A).

The shape mirrors power's distro → multi → circuit cable as card or box →
SNAKE (one name, one home run, N ports) → port cable, with one deliberate
difference: the stores live on the HARDWARE record, not the screen -

  - card.snakes / card.portCables on a processor card, the same two on a
    breakout box (cvt) for the ports it delivers; sockets are card-wide port
    numbers; a port is in at most one snake; a port in a snake has no own
    cable; connector null follows the port (the catalog's documented kind,
    else nothing).
  - PUT /api/processors/<id>/cards/<cid> and …/cvts/<cvtId> take both,
    validated (range, no port in two snakes, ft a non-negative number,
    connector in the list or null) and refuse with the reason.
  - A port released from a screen KEEPS its snake and cable: the loom hangs
    off the socket whatever the wall does. (Power's per-screen cable is
    programming and a clear forgets it.)
  - layer.showDataCableTags (default FALSE), "Show Cable Tags" under Show
    Port Load %; on, a blue tag beside the port's label on screen and in
    exportMode alike: the snake's name, or "50' CAT".

Run locally (ONE pytest at a time - the browser-test servers use fixed
ports):
    python -m pytest tests/test_data_snakes.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import processor_catalog as catalog  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# ── the store, through the Flask client ──────────────────────────────────

def _h9_with_card_and_box(client, card='novastar-card-h-16xrj45-2xfiber',
                          box='novastar-cvt10'):
    st = client.post('/api/processors', json={'deviceId': 'novastar-h9'}
                     ).get_json()
    pid = st['processors'][-1]['id']
    st = client.put(f'/api/processors/{pid}/slots/0',
                    json={'deviceId': card}).get_json()
    proc = next(p for p in st['processors'] if p['id'] == pid)
    cid = proc['slots'][0]['card']['id']
    bid = None
    if box:
        r = client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                        json={'deviceId': box, 'pair': False})
        assert r.status_code == 201, r.get_data(as_text=True)
        proc = next(p for p in r.get_json()['processors'] if p['id'] == pid)
        bid = proc['slots'][0]['card']['cvts'][0]['id']
    return pid, cid, bid


def _raw(client, pid):
    st = client.get('/api/processors').get_json()
    return next(p for p in st['processors'] if p['id'] == pid)


def _resolved(client, pid):
    st = client.get('/api/processors').get_json()
    return next(p for p in st['resolved'] if p['id'] == pid)


def test_the_store_round_trips_on_a_card_and_a_box(client):
    """A PUT of snakes + portCables lands on the card record and comes
    back resolved: ports sorted, the name defaulted to SNAKE A (the next
    to SNAKE B), ids minted off the processor counter, a zero length
    dropped, and the box keeping its own store against the sockets it
    delivers. GET /api/processors serves the same - a reload keeps it."""
    pid, cid, bid = _h9_with_card_and_box(client)
    r = client.put(f'/api/processors/{pid}/cards/{cid}', json={
        'snakes': [{'ports': [11, 9, 10], 'ft': '100'},
                   {'ports': [14, 13]}],
        'portCables': {'15': {'ft': 50}, '16': {'ft': 75,
                                                 'connector': 'fiber'},
                       '12': {'ft': 0}},
    })
    assert r.status_code == 200, r.get_data(as_text=True)
    card = _raw(client, pid)['slots'][0]['card']
    assert [s['ports'] for s in card['snakes']] == [[9, 10, 11], [13, 14]]
    assert [s['name'] for s in card['snakes']] == ['SNAKE A', 'SNAKE B']
    assert card['snakes'][0]['ft'] == 100 and 'ft' not in card['snakes'][1]
    assert all(s['id'].startswith('snk') for s in card['snakes'])
    assert card['portCables'] == {
        '15': {'ft': 50}, '16': {'ft': 75, 'connector': 'fiber'}}
    rcard = _resolved(client, pid)['slots'][0]['card']
    assert rcard['snakes'][0] == {
        'id': card['snakes'][0]['id'], 'name': 'SNAKE A', 'ft': 100,
        'connector': None, 'ports': [9, 10, 11]}
    assert rcard['portCables']['16'] == {'ft': 75, 'connector': 'fiber'}
    # the card's sockets follow its documented kind: RJ45 → CAT
    assert rcard['portConnector'] == 'cat'
    # The box: its own record, its own sockets (the CVT10 on OPT 1 of this
    # card delivers 1-8 again - copy delivery), its own SNAKE A.
    r = client.put(f'/api/processors/{pid}/cvts/{bid}', json={
        'snakes': [{'ports': [1, 2, 3, 4, 5, 6], 'name': ' FOH '}],
        'portCables': {'7': {'ft': 25}},
    })
    assert r.status_code == 200, r.get_data(as_text=True)
    box = _raw(client, pid)['slots'][0]['card']['cvts'][0]
    assert box['snakes'] == [{'id': box['snakes'][0]['id'], 'name': 'FOH',
                              'ports': [1, 2, 3, 4, 5, 6]}]
    assert box['portCables'] == {'7': {'ft': 25}}
    rbox = _resolved(client, pid)['slots'][0]['card']['cvts'][0]
    assert rbox['snakes'][0]['name'] == 'FOH'
    assert rbox['portConnector'] == 'cat', 'a box with no documented ' \
        'connector follows its card'
    # the card store never saw the box's PUT
    assert [s['ports'] for s in _raw(client, pid)['slots'][0]['card']
            ['snakes']] == [[9, 10, 11], [13, 14]]
    # A snaked port's own cable is stripped: its run is the snake's.
    r = client.put(f'/api/processors/{pid}/cards/{cid}', json={
        'portCables': {'9': {'ft': 30}, '15': {'ft': 50}}})
    assert r.status_code == 200
    assert _raw(client, pid)['slots'][0]['card']['portCables'] == {
        '15': {'ft': 50}}
    # Emptying both stores leaves no key behind.
    r = client.put(f'/api/processors/{pid}/cards/{cid}',
                   json={'snakes': [], 'portCables': {}})
    assert r.status_code == 200
    card = _raw(client, pid)['slots'][0]['card']
    assert 'snakes' not in card and 'portCables' not in card


@pytest.mark.parametrize('body, reason', [
    ({'snakes': [{'ports': [1, 2]}, {'ports': [2, 3]}]},
     'socket 2 is already in another snake'),
    ({'snakes': [{'ports': [1, 99]}]}, 'no socket 99 on this card'),
    ({'portCables': {'40': {'ft': 10}}}, 'no socket 40 on this card'),
    ({'portCables': {'3': {'ft': -1}}}, 'non-negative'),
    ({'portCables': {'3': {'ft': 'ten'}}}, 'number of feet'),
    ({'snakes': [{'ports': [1], 'connector': 'usb'}]},
     "unknown connector 'usb'"),
    ({'snakes': 'SNAKE A'}, 'snakes must be a list'),
])
def test_the_server_refuses_a_bad_store_with_the_reason(client, body,
                                                        reason):
    pid, cid, bid = _h9_with_card_and_box(client, box=None)
    ok = client.put(f'/api/processors/{pid}/cards/{cid}',
                    json={'snakes': [{'ports': [5, 6]}]})
    assert ok.status_code == 200
    r = client.put(f'/api/processors/{pid}/cards/{cid}', json=body)
    assert r.status_code == 400, r.get_data(as_text=True)
    assert reason in r.get_json()['error'], r.get_json()
    # nothing stored: the earlier snake is exactly what is there
    assert [s['ports'] for s in _raw(client, pid)['slots'][0]['card']
            ['snakes']] == [[5, 6]]


def test_a_box_refuses_a_socket_it_does_not_deliver(client):
    pid, cid, bid = _h9_with_card_and_box(client)
    r = client.put(f'/api/processors/{pid}/cvts/{bid}',
                   json={'snakes': [{'ports': [1, 9]}]})
    assert r.status_code == 400
    assert 'no socket 9 on this box (sockets 1-8)' in r.get_json()['error']


def test_a_mode_change_prunes_what_the_card_no_longer_has(client):
    """H_4xfiber independent → copy/backup halves the card 32 → 16: a
    snake on 20-25 goes, one on 1-3 stays, and a cable on 30 goes."""
    pid, cid, bid = _h9_with_card_and_box(client, 'novastar-card-h-4xfiber',
                                          None)
    r = client.put(f'/api/processors/{pid}/cards/{cid}', json={
        'snakes': [{'ports': [1, 2, 3]}, {'ports': [20, 21, 22, 23, 24, 25]}],
        'portCables': {'30': {'ft': 10}, '4': {'ft': 10}}})
    assert r.status_code == 200, r.get_data(as_text=True)
    r = client.put(f'/api/processors/{pid}/cards/{cid}',
                   json={'mode': 'copy-backup'})
    assert r.status_code == 200
    card = _raw(client, pid)['slots'][0]['card']
    assert [s['ports'] for s in card['snakes']] == [[1, 2, 3]]
    assert card['portCables'] == {'4': {'ft': 10}}


def test_removing_a_card_or_a_box_drops_its_snakes(client):
    """The stores ride the record: clear the slot and the card's snakes
    are gone with it; delete the box and its snake goes too."""
    pid, cid, bid = _h9_with_card_and_box(client)
    assert client.put(f'/api/processors/{pid}/cvts/{bid}',
                      json={'snakes': [{'ports': [1, 2]}]}).status_code == 200
    assert client.put(f'/api/processors/{pid}/cards/{cid}',
                      json={'snakes': [{'ports': [9, 10]}]}).status_code == 200
    r = client.delete(f'/api/processors/{pid}/cvts/{bid}')
    assert r.status_code == 200
    card = _raw(client, pid)['slots'][0]['card']
    assert card['cvts'] == [] and [s['ports'] for s in card['snakes']] == [
        [9, 10]]
    r = client.put(f'/api/processors/{pid}/slots/0', json={'deviceId': None})
    assert r.status_code == 200
    assert _raw(client, pid)['slots'][0]['card'] is None
    # the counter noted the snake ids, so an undo-shaped restore cannot
    # hand one back out (sync_next_processor_seq sees snk ids)
    project = {'processors': [{'id': 'proc1', 'slots': [{'index': 0, 'card': {
        'id': 'card2', 'cvts': [], 'snakes': [{'id': 'snk7', 'ports': [1]}]}}]}]}
    assert catalog.sync_next_processor_seq(project) == 8


def test_the_connector_list_is_served_and_follows_the_catalog(client):
    """getDataCableConnectors mirrors DATA_CABLE_CONNECTORS through the
    state payload; a card's followed connector is the catalog's documented
    kind (rj45 → cat, fiber → fiber) and NOTHING where it is silent - the
    no-hardware-assumptions rule, so an undocumented box prints a bare
    length rather than a guessed plug."""
    st = client.get('/api/processors').get_json()
    assert st['dataCableConnectors'] == [{'id': 'cat', 'name': 'CAT'},
                                         {'id': 'fiber', 'name': 'Fiber'}]
    assert catalog.data_port_connector(None, {'connector': 'rj45'}, None) \
        == 'cat'
    assert catalog.data_port_connector(None, {'connector': 'fiber'}, None) \
        == 'fiber'
    assert catalog.data_port_connector({}, {}, {}) is None
    pid, cid, bid = _h9_with_card_and_box(client, 'novastar-card-h-4xfiber')
    rcard = _resolved(client, pid)['slots'][0]['card']
    assert rcard['portConnector'] == 'fiber'
    assert rcard['cvts'][0]['portConnector'] == 'fiber', (
        'the CVT10 documents no connector, so its sockets follow the card')


# ── the browser: the sweep, the sheet, the tags ───────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

# One H9: slot 0 an H_16xRJ45+2xfiber named SR with a CVT10 on OPT 1 (the
# box delivers 1-8 again; 9-16 stay loose on the card), slot 1 an H_20xRJ45
# (a second card, for the cross-card refusal). WALL 8 × 12 of 200 px
# cabinets on the Legacy platform (the H series is Legacy gear - the
# platform wall, 2026-08-28) needs six ports, placed onto the card in
# order: 1-6, the box's sockets.
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
    await fetch('/api/layer/add', {method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: 'WALL', columns: 8, rows: 12,
                              cabinet_width: 200, cabinet_height: 200})});
    const post = (url, body) => fetch(url, {method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body)}).then(r => r.json());
    const put = (url, body) => fetch(url, {method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body)}).then(r => r.json());
    let st = await post('/api/processors', {deviceId: 'novastar-h9'});
    const pid = st.processors[0].id;
    st = await put(`/api/processors/${pid}/slots/0`,
                   {deviceId: 'novastar-card-h-16xrj45-2xfiber'});
    const cardId = st.processors[0].slots[0].card.id;
    await put(`/api/processors/${pid}/cards/${cardId}`, {name: 'SR'});
    st = await post(`/api/processors/${pid}/cards/${cardId}/cvts`,
                    {deviceId: 'novastar-cvt10', pair: false});
    const boxId = st.processors[0].slots[0].card.cvts[0].id;
    st = await put(`/api/processors/${pid}/slots/1`,
                   {deviceId: 'novastar-card-h-20xrj45'});
    const card2Id = st.processors[0].slots[1].card.id;
    const app = window.app;
    const p1 = await (await fetch('/api/project')).json();
    for (const l of p1.layers) {
        await put(`/api/layer/${l.id}`, {processorType: 'novastar-armor'});
    }
    const p = await (await fetch('/api/project')).json();
    app.project = p;
    app.dedupeProjectLayers('snakes_setup');
    const wall = app.project.layers[0];
    app.selectLayer(wall);
    await app.refreshProcessors();
    await app._assignmentRequest('/api/port-assignments/place-overflow',
                                 'POST', {layerId: String(wall.id), cardId});
    app.renderLayers();
    app.renderHardwareDock();
    const r = window.canvasRenderer;
    r.zoom = 0.3; r.panX = 60; r.panY = 40; r.render();
    app.resetHistory('Snakes Seed');
    const scr = app._assignment.screens.find(s => s.layerId === String(wall.id));
    return {
        id: wall.id, procId: pid, cardId, boxId, card2Id,
        ports: scr.ports.map(pt => [pt.number, pt.cardId, pt.port]),
    };
}"""

# Both stores as the dock reads them (the resolved tree), the layer's tag
# flag, and where history stands.
STATE_JS = """(ids) => {
    const app = window.app;
    const card = app._dockFindCard(ids.cardId).card;
    const box = card.cvts.find(c => c.id === ids.boxId);
    const l = app.project.layers.find(x => x.id === ids.id);
    const store = (rec) => ({
        snakes: rec.snakes.map(s => ({name: s.name, ft: s.ft,
                                      connector: s.connector, ports: s.ports})),
        ids: rec.snakes.map(s => s.id),
        cables: rec.portCables,
    });
    return {
        card: store(card), box: store(box),
        flag: l.showDataCableTags,
        action: app.history[app.historyIndex].action,
        index: app.historyIndex,
    };
}"""

SERVED_JS = """async (ids) => {
    const st = await (await fetch('/api/processors')).json();
    const proc = st.processors.find(p => p.id === ids.procId);
    const card = proc.slots[0].card;
    const box = card.cvts.find(c => c.id === ids.boxId);
    const p = await (await fetch('/api/project')).json();
    const l = (p.layers || []).find(x => x.id === ids.id);
    return {
        cardSnakes: card.snakes || null, cardCables: card.portCables || null,
        boxSnakes: box.snakes || null, boxCables: box.portCables || null,
        flag: l ? l.showDataCableTags : undefined,
    };
}"""

# What the tray shows for one record: the lit chips, the brackets with
# their tags, the corner cables, whether the sheet or the grid is up.
TRAY_JS = """([kind, id]) => {
    const grid = document.querySelector(
        `.hw-dock-grid[data-lrd-snake-owner="${kind}:${id}"]`);
    const sec = grid ? grid.parentElement : null;
    const sheet = document.querySelector(
        `.hw-dock-cablesheet[data-lrd-cable-sheet="${kind}:${id}"]`);
    const btn = document.querySelector(`[data-lrd-field="data-cable-sheet-${id}"]`);
    const sock = (t) => parseInt(t.dataset.lrdTile.split('-').pop(), 10);
    return {
        grid: !!grid, sheet: !!sheet,
        btn: !!btn, on: !!(btn && btn.classList.contains('hw-dock-cablebtn-on')),
        lit: grid ? [...grid.querySelectorAll('.hw-dock-chip-sel')].map(sock) : null,
        snaked: grid && grid.classList.contains('hw-dock-grid-snaked'),
        brackets: grid ? [...grid.querySelectorAll('.hw-dock-snake')].map(b => ({
            ghost: b.classList.contains('hw-dock-snake-ghost'),
            snakeId: b.dataset.lrdSnakeId || null,
            tag: (b.querySelector('.hw-dock-snake-tag') || {}).textContent || null,
            width: b.getBoundingClientRect().width,
        })) : null,
        corners: grid ? Object.fromEntries([...grid.querySelectorAll('.lrd-tile')]
            .map(t => [sock(t),
                (t.querySelector('.hw-dock-chip-cable-data') || {}).textContent || null]))
            : null,
    };
}"""

# The sheet's rows as read: snake rows and port rows in order.
SHEET_JS = """([kind, id]) => {
    const sheet = document.querySelector(
        `.hw-dock-cablesheet[data-lrd-cable-sheet="${kind}:${id}"]`);
    if (!sheet) return null;
    return {
        rows: [...sheet.querySelectorAll('tr')].filter(tr => tr.querySelector('td'))
            .map(tr => {
                const tds = [...tr.querySelectorAll('td')];
                const ft = tr.querySelector('.hw-dock-cable-ft');
                const sel = tr.querySelector('.hw-dock-cable-connector');
                const name = tr.querySelector('.hw-dock-cable-name');
                return {
                    kind: tr.classList.contains('hw-dock-cable-snake') ? 'snake'
                        : tr.classList.contains('hw-dock-cable-member') ? 'member'
                        : tr.classList.contains('hw-dock-cable-free') ? 'free' : 'port',
                    label: name ? tr.querySelector('.hw-dock-cable-snake-cap').textContent
                        : tds[1].textContent,
                    name: name ? name.value : null,
                    who: tds[2].textContent,
                    ft: ft ? ft.value : tds[3].textContent,
                    ftKey: ft ? ft.dataset.lrdField : null,
                    connector: sel ? sel.value : tds[4].textContent,
                    blank: sel ? sel.options[0].textContent : null,
                };
            }),
        buttons: [...sheet.querySelectorAll('[data-lrd-field]')]
            .filter(el => el.tagName === 'BUTTON').map(el => el.dataset.lrdField),
    };
}"""

# Every fillText the data pass paints that reads like a home-run tag -
# interactively and in exportMode.
FRAME_TEXTS_JS = """() => {
    const r = window.canvasRenderer, ctx = r.ctx;
    const oT = ctx.fillText;
    const grab = () => {
        const texts = [];
        ctx.fillText = function (t, x, y, w) { texts.push(String(t)); return oT.call(ctx, t, x, y, w); };
        try { r.render(); } finally { ctx.fillText = oT; }
        return texts.filter(t => /^(SNAKE |FOH|\\d+(\\.\\d+)?' )/.test(t));
    };
    const prevMode = r.viewMode, prevExport = r.exportMode;
    let interactive, exported;
    try {
        r.viewMode = 'data-flow';
        r.exportMode = false;
        interactive = grab();
        r.exportMode = true;
        exported = grab();
    } finally {
        r.exportMode = prevExport;
        r.viewMode = prevMode;
        r.render();
    }
    return { interactive, exported };
}"""

MENU_JS = """() => {
    const menu = document.getElementById('context-menu');
    const shown = menu && menu.style.display === 'block';
    return {
        shown: !!shown,
        items: !shown ? [] : [...menu.querySelectorAll('.menu-option')]
            .filter(el => getComputedStyle(el).display !== 'none')
            .filter(el => !el.closest('.menu-submenu'))
            .map(el => ({action: el.dataset.action, text: el.textContent.trim()})),
    };
}"""

FOCUS_JS = """() => {
    const a = document.activeElement;
    return a && a.dataset ? (a.dataset.lrdField || a.tagName) : null;
}"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(500)
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(1200)
    assert ids['ports'] == [[i, ids['cardId'], i] for i in range(1, 7)], (
        f'fixture: WALL must take card sockets 1-6 (the box\'s): {ids}')
    yield pg, ids
    context.close()


def _chip_center(page, card_id, n):
    page.evaluate("""(key) => {
        const el = document.querySelector(`[data-hwdock="${key}"]`);
        if (el) el.scrollIntoView({ block: 'nearest' });
    }""", f'port-{card_id}-{n}')
    box = page.locator(f'[data-hwdock="port-{card_id}-{n}"]').bounding_box()
    assert box, f'no chip port-{card_id}-{n}'
    return box['x'] + box['width'] / 2, box['y'] + box['height'] / 2


def _alt_sweep(page, card_id, a, b):
    """Hold Alt, press on chip a, drag across to chip b, release."""
    x1, y1 = _chip_center(page, card_id, a)
    x2, y2 = _chip_center(page, card_id, b)
    page.keyboard.down('Alt')
    page.mouse.move(x1, y1)
    page.mouse.down()
    page.mouse.move((x1 + x2) / 2, (y1 + y2) / 2, steps=4)
    page.mouse.move(x2, y2, steps=4)
    page.mouse.up()
    page.keyboard.up('Alt')
    page.wait_for_timeout(300)


def _right_click(page, x, y):
    page.mouse.click(x, y, button='right')
    page.wait_for_timeout(400)
    return page.evaluate(MENU_JS)


def _close_menu(page):
    pt = page.evaluate("""() => {
        const r = window.canvasRenderer.canvas.getBoundingClientRect();
        return {x: r.left + 15, y: r.top + 15};
    }""")
    page.mouse.click(pt['x'], pt['y'])
    page.wait_for_timeout(250)


def _sheet_open(page, kind, owner_id, want_open=True):
    """Flip the record's sheet to the wanted face (the ≡ is a toggle)."""
    tray = page.evaluate(TRAY_JS, [kind, owner_id])
    if bool(tray['sheet']) != want_open:
        page.locator(f'[data-lrd-field="data-cable-sheet-{owner_id}"]').click()
        page.wait_for_timeout(400)
    return page.evaluate(TRAY_JS, [kind, owner_id])


def _served(page, ids, want, timeout_ms=4000):
    waited = 0
    served = None
    while waited <= timeout_ms:
        served = page.evaluate(SERVED_JS, ids)
        if served and want(served):
            return served
        page.wait_for_timeout(250)
        waited += 250
    return served


def test_the_sweep_lights_chips_and_a_right_click_snakes_them(page):
    """Alt+drag across the box's chips 1-6: the six light, the grid opens
    its bracket lane and a dashed ghost says "snake · 6-way". Right-click
    a lit chip: "Snake these 6 (Alt+Enter)" and "Set home run…" - no Loosen,
    nothing is in a snake yet. Take it: ONE 'Snake Ports' entry, the store
    holds SNAKE A on 1-6, the bracket wears "SNAKE A · 6-way", the server
    has it, and undo loosens the lot; redo brings it back."""
    pg, ids = page
    st = pg.evaluate(STATE_JS, ids)
    assert st['box']['snakes'] == [] and st['card']['snakes'] == [], st
    assert st['flag'] is False, 'the tag switch defaults OFF'
    _alt_sweep(pg, ids['cardId'], 1, 6)
    tray = pg.evaluate(TRAY_JS, ['cvt', ids['boxId']])
    assert tray['lit'] == [1, 2, 3, 4, 5, 6], tray
    assert tray['snaked'] and tray['brackets'], tray
    assert tray['brackets'][0]['ghost'] and tray['brackets'][0]['tag'] \
        == 'snake · 6-way', tray
    x, y = _chip_center(pg, ids['cardId'], 6)
    menu = _right_click(pg, x, y)
    assert [i['action'] for i in menu['items']] == [
        'hw-clear', 'hw-snake-n0', 'hw-snake-n1'], menu
    assert menu['items'][1]['text'] == 'Snake these 6 (Alt+Enter)', menu
    assert menu['items'][2]['text'] == 'Set home run…', menu
    index = pg.evaluate(STATE_JS, ids)['index']
    pg.locator('#context-menu [data-action="hw-snake-n0"]').click()
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids)
    assert st['box']['snakes'] == [{'name': 'SNAKE A', 'ft': None,
                                    'connector': None,
                                    'ports': [1, 2, 3, 4, 5, 6]}], st
    assert st['action'] == 'Snake Ports' and st['index'] == index + 1, st
    tray = pg.evaluate(TRAY_JS, ['cvt', ids['boxId']])
    assert tray['lit'] == [], 'the snake takes the selection with it'
    assert [b['tag'] for b in tray['brackets']] == ['SNAKE A · 6-way'], tray
    assert not tray['brackets'][0]['ghost'] and tray['brackets'][0]['width'] > 300
    assert tray['corners'] == {str(n): None for n in range(1, 9)}, tray
    served = _served(pg, ids, lambda s: bool(s['boxSnakes']))
    assert served['boxSnakes'][0]['ports'] == [1, 2, 3, 4, 5, 6], served
    pg.evaluate('() => window.app.undo()')
    pg.wait_for_timeout(1200)
    st = pg.evaluate(STATE_JS, ids)
    assert st['box']['snakes'] == [] and st['index'] == index, st
    assert pg.evaluate(TRAY_JS, ['cvt', ids['boxId']])['brackets'] == []
    pg.evaluate('() => window.app.redo()')
    pg.wait_for_timeout(1200)
    st = pg.evaluate(STATE_JS, ids)
    assert st['box']['snakes'][0]['ports'] == [1, 2, 3, 4, 5, 6], st


def test_the_sweep_refuses_a_second_card_and_escape_clears(page):
    """A sweep that reaches into the other card's chips keeps its range
    and says so in the status bar; Escape drops it, and a plain click
    elsewhere would too."""
    pg, ids = page
    x1, y1 = _chip_center(pg, ids['cardId'], 7)
    x2, y2 = _chip_center(pg, ids['card2Id'], 1)
    pg.keyboard.down('Alt')
    pg.mouse.move(x1, y1)
    pg.mouse.down()
    pg.mouse.move(x2, y2, steps=6)
    pg.mouse.up()
    pg.keyboard.up('Alt')
    pg.wait_for_timeout(300)
    tray = pg.evaluate(TRAY_JS, ['cvt', ids['boxId']])
    assert tray['lit'] == [7], tray
    assert pg.evaluate(TRAY_JS, ['card', ids['card2Id']])['lit'] == []
    assert 'one card or box' in pg.locator('#status-message').text_content()
    pg.keyboard.press('Escape')
    pg.wait_for_timeout(200)
    tray = pg.evaluate(TRAY_JS, ['cvt', ids['boxId']])
    assert tray['lit'] == [] and [b['ghost'] for b in tray['brackets']] == [False]


def test_the_card_sheet_types_loose_lengths_that_read_in_the_corner(page):
    """The card's ≡ (its loose sockets 9-16) flips the grid into the sheet:
    eight free rows, fields on every one, the connector blank reading
    "follows port (CAT)" - the card is RJ45. 50 on 9 is ONE 'Set Port
    Cable'; Tab lands on 10's field, 75 there is another. Flipped back, the
    chips wear 50' and 75' in their corners in blue, the rest nothing."""
    pg, ids = page
    cid = ids['cardId']
    tray = pg.evaluate(TRAY_JS, ['card', cid])
    assert tray['grid'] and tray['btn'] and not tray['on'], tray
    pg.locator(f'[data-lrd-field="data-cable-sheet-{cid}"]').click()
    pg.wait_for_timeout(400)
    tray = pg.evaluate(TRAY_JS, ['card', cid])
    assert tray['sheet'] and tray['on'] and not tray['grid'], tray
    sheet = pg.evaluate(SHEET_JS, ['card', cid])
    assert [r['kind'] for r in sheet['rows']] == ['free'] * 8, sheet
    assert [r['label'] for r in sheet['rows']] == [
        f'{n} · SR-{n}' for n in range(9, 17)], sheet
    assert all(r['blank'] == 'follows port (CAT)' for r in sheet['rows'])
    assert sheet['buttons'] == [
        f'data-cable-snake-{cid}', f'data-cable-loosen-{cid}',
        f'data-cable-fill-{cid}-100', f'data-cable-fill-{cid}-none'], sheet
    index = pg.evaluate(STATE_JS, ids)['index']
    ft9 = pg.locator(f'[data-lrd-field="data-cable-ft-{cid}-9"]')
    ft9.fill('50')
    ft9.press('Tab')
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids)
    assert st['card']['cables'] == {'9': {'ft': 50, 'connector': None}}, st
    assert st['action'] == 'Set Port Cable' and st['index'] == index + 1, st
    assert pg.evaluate(FOCUS_JS) == f'data-cable-ft-{cid}-10', (
        'Tab must walk to the next row\'s ft field across the rebuild')
    pg.keyboard.type('75')
    pg.keyboard.press('Tab')
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids)
    assert st['card']['cables'] == {'9': {'ft': 50, 'connector': None},
                                    '10': {'ft': 75, 'connector': None}}, st
    assert st['index'] == index + 2, st
    # the connector pick on 10: fiber - its own entry
    pg.locator(f'[data-lrd-field="data-cable-connector-{cid}-10"]'
               ).select_option('fiber')
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids)
    assert st['card']['cables']['10'] == {'ft': 75, 'connector': 'fiber'}, st
    assert st['action'] == 'Set Port Cable' and st['index'] == index + 3, st
    reading = pg.evaluate("""(ids) => [9, 10].map(n =>
        window.app.dataPortCable(ids.cardId, n).text)""", ids)
    assert reading == ["50' CAT", "75' Fiber"], reading
    pg.locator(f'[data-lrd-field="data-cable-sheet-{cid}"]').click()
    pg.wait_for_timeout(400)
    tray = pg.evaluate(TRAY_JS, ['card', cid])
    assert tray['grid'] and not tray['sheet'], tray
    assert tray['corners'] == {'9': "50'", '10': "75'", '11': None,
                               '12': None, '13': None, '14': None,
                               '15': None, '16': None}, tray


def test_the_sheet_ticks_and_snakes_and_undo_loosens(page):
    """Option A whole: tick 11, 12, 13 in the card's sheet, press Snake -
    ONE 'Snake Ports' entry, the card's own SNAKE A (its first; the box's
    SNAKE A is another record's), the three rows fold under a snake row
    reading "in snake", and undo loosens them."""
    pg, ids = page
    cid = ids['cardId']
    assert _sheet_open(pg, 'card', cid)['sheet']
    for n in (11, 12, 13):
        pg.locator(f'[data-lrd-field="data-snake-tick-{cid}-{n}"]').check()
    index = pg.evaluate(STATE_JS, ids)['index']
    pg.locator(f'[data-lrd-field="data-cable-snake-{cid}"]').click()
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids)
    assert st['card']['snakes'] == [{'name': 'SNAKE A', 'ft': None,
                                     'connector': None, 'ports': [11, 12, 13]}]
    assert st['action'] == 'Snake Ports' and st['index'] == index + 1, st
    sheet = pg.evaluate(SHEET_JS, ['card', cid])
    kinds = [(r['kind'], r['label']) for r in sheet['rows']]
    assert kinds[:2] == [('free', '9 · SR-9'), ('free', '10 · SR-10')], kinds
    assert kinds[2] == ('snake', 'SNAKE A · 3-way'), kinds
    assert kinds[3:6] == [('member', '11 · SR-11'), ('member', '12 · SR-12'),
                          ('member', '13 · SR-13')], kinds
    assert [r['ft'] for r in sheet['rows'][3:6]] == ['in snake'] * 3
    assert sheet['rows'][2]['name'] == 'SNAKE A', sheet
    pg.evaluate('() => window.app.undo()')
    pg.wait_for_timeout(1200)
    st = pg.evaluate(STATE_JS, ids)
    assert st['card']['snakes'] == [] and st['index'] == index, st
    pg.evaluate('() => window.app.redo()')
    pg.wait_for_timeout(1200)
    assert pg.evaluate(STATE_JS, ids)['card']['snakes'][0]['ports'] == [11, 12, 13]
    _sheet_open(pg, 'card', cid, False)


def test_rename_home_run_and_connector_commit_one_entry_each(page):
    """The box's sheet: its snake row carries the name, the ft and the
    connector. FOH is 'Rename Snake', 100 is 'Set Snake Home Run', fiber is
    'Set Snake Home Run' - one entry each - and the bracket's tag follows:
    "FOH · 6-way · 100'"."""
    pg, ids = page
    bid = ids['boxId']
    snake_id = pg.evaluate(STATE_JS, ids)['box']['ids'][0]
    assert _sheet_open(pg, 'cvt', bid)['sheet']
    sheet = pg.evaluate(SHEET_JS, ['cvt', bid])
    assert sheet['rows'][0]['kind'] == 'snake' and sheet['rows'][0]['who'] == 'WALL'
    assert [r['kind'] for r in sheet['rows'][1:7]] == ['member'] * 6
    assert [r['kind'] for r in sheet['rows'][7:]] == ['free', 'free'], sheet
    index = pg.evaluate(STATE_JS, ids)['index']
    name = pg.locator(f'[data-lrd-field="data-snake-name-{bid}-{snake_id}"]')
    name.fill('FOH')
    name.press('Tab')
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids)
    assert st['box']['snakes'][0]['name'] == 'FOH', st
    assert st['action'] == 'Rename Snake' and st['index'] == index + 1, st
    ft = pg.locator(f'[data-lrd-field="data-snake-ft-{bid}-{snake_id}"]')
    ft.fill('100')
    ft.press('Tab')
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids)
    assert st['box']['snakes'][0]['ft'] == 100, st
    assert st['action'] == 'Set Snake Home Run' and st['index'] == index + 2
    # Tab from the snake's ft walks on to the first loose row's ft (7)
    assert pg.evaluate(FOCUS_JS) == f'data-cable-ft-{bid}-7'
    pg.locator(f'[data-lrd-field="data-snake-connector-{bid}-{snake_id}"]'
               ).select_option('fiber')
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids)
    assert st['box']['snakes'][0]['connector'] == 'fiber', st
    assert st['action'] == 'Set Snake Home Run' and st['index'] == index + 3
    served = _served(pg, ids, lambda s: s['boxSnakes']
                     and s['boxSnakes'][0].get('connector') == 'fiber')
    assert served['boxSnakes'][0] == {
        'id': snake_id, 'name': 'FOH', 'ft': 100, 'connector': 'fiber',
        'ports': [1, 2, 3, 4, 5, 6]}, served
    tray = _sheet_open(pg, 'cvt', bid, False)
    assert [b['tag'] for b in tray['brackets']] == ["FOH · 6-way · 100'"], tray


def test_a_port_cleared_from_its_screen_keeps_its_snake(page):
    """Release WALL's port 1 from socket 1 (the right-click clear): the
    socket is free on the tray, and FOH still holds 1-6 - the loom is
    hardware, not the screen's programming. Undo puts the port back."""
    pg, ids = page
    pg.evaluate("""(ids) => window.app._assignmentRequest(
        '/api/port-assignments/unpin', 'POST',
        {layerId: String(ids.id), index: 0}, null, 'Release Port')""", ids)
    pg.wait_for_timeout(1200)
    st = pg.evaluate(STATE_JS, ids)
    assert st['action'] == 'Release Port', st
    assert st['box']['snakes'][0]['ports'] == [1, 2, 3, 4, 5, 6], (
        f'a released port keeps its snake: {st}')
    who = pg.evaluate("""(ids) => window.app._portOccupants(ids.cardId, 1)""",
                      ids)
    assert who == [], 'socket 1 must be free'
    sheet_free = pg.evaluate("""(ids) => {
        const app = window.app;
        const rec = app._dockFindCard(ids.cardId).card;
        return rec.cvts[0].portCables;
    }""", ids)
    assert sheet_free == {}, 'no own cable grew on the released socket'
    pg.evaluate('() => window.app.undo()')
    probe = """(ids) => ({
        pins: ((window.app.project.port_assignments || {}).pins || [])
            .map(p => [p.index, p.port]),
        occ: window.app._portOccupants(ids.cardId, 1).length,
        hist: window.app.history.map(h => h.action).slice(-4),
        index: window.app.historyIndex,
    })"""
    waited = 0
    back = pg.evaluate(probe, ids)
    while waited < 4000 and not back['occ']:
        pg.wait_for_timeout(250)
        waited += 250
        back = pg.evaluate(probe, ids)
    assert back['occ'] == 1 and [0, 1] in back['pins'], (
        f'undo must put the port back on socket 1: {back}')
    assert pg.evaluate(STATE_JS, ids)['box']['snakes'][0]['ports'] == [
        1, 2, 3, 4, 5, 6]


def test_the_canvas_tag_follows_the_switch_and_the_export(page):
    """Off (the default): the data pass paints no home-run text on screen
    or in exportMode. Tick Show Cable Tags: one 'Toggle Data Cable Tags'
    step, the flag lands on the server, and both passes paint FOH beside
    ports 1-6 (their sockets ride the snake). Undo un-ticks and un-paints."""
    pg, ids = page
    box = pg.locator('#show-data-cable-tags')
    assert box.is_visible() and not box.is_checked(), 'default OFF'
    assert pg.evaluate(FRAME_TEXTS_JS) == {'interactive': [], 'exported': []}
    index = pg.evaluate(STATE_JS, ids)['index']
    box.click()
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids)
    assert st['flag'] is True and st['action'] == 'Toggle Data Cable Tags', st
    assert st['index'] == index + 1, st
    frame = pg.evaluate(FRAME_TEXTS_JS)
    assert frame['interactive'] == ['FOH'] * 6, frame
    assert frame['exported'] == ['FOH'] * 6, (
        f'the export pass must match the screen: {frame}')
    served = _served(pg, ids, lambda s: s['flag'] is True)
    assert served and served['flag'] is True, served
    # A loose port with its own cable prints "50' CAT": move WALL's port 6
    # onto card socket 9 (the card's loose 50' CAT) and read the tag.
    pg.evaluate("""(ids) => window.app._assignmentRequest(
        '/api/port-assignments/place', 'POST',
        {layerId: String(ids.id), index: 5, cardId: ids.cardId, port: 9},
        null, 'Place Port')""", ids)
    pg.wait_for_timeout(1200)
    frame = pg.evaluate(FRAME_TEXTS_JS)
    assert sorted(frame['interactive']) == sorted(['FOH'] * 5 + ["50' CAT"]), frame
    assert sorted(frame['exported']) == sorted(frame['interactive']), frame
    pg.evaluate('() => window.app.undo()')
    pg.wait_for_timeout(1200)
    pg.evaluate('() => window.app.undo()')
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids)
    assert st['flag'] is False and not box.is_checked(), st
    assert pg.evaluate(FRAME_TEXTS_JS) == {'interactive': [], 'exported': []}
    pg.evaluate('() => window.app.redo()')
    pg.wait_for_timeout(900)
    assert pg.evaluate(STATE_JS, ids)['flag'] is True and box.is_checked()
    box.click()
    pg.wait_for_timeout(600)
    assert pg.evaluate(STATE_JS, ids)['flag'] is False


def test_the_switch_reads_the_selected_screen(page):
    """loadLayerToInputs: the box follows the layer it shows, and an absent
    key reads OFF - opted into, never inherited."""
    pg, ids = page
    out = pg.evaluate("""() => {
        const app = window.app;
        const l = app.currentLayer;
        const box = document.getElementById('show-data-cable-tags');
        l.showDataCableTags = true;
        app.loadLayerToInputs();
        const on = box.checked;
        l.showDataCableTags = false;
        app.loadLayerToInputs();
        const off = box.checked;
        delete l.showDataCableTags;
        app.loadLayerToInputs();
        const absent = box.checked;
        l.showDataCableTags = false;
        return { on, off, absent };
    }""")
    assert out == {'on': True, 'off': False, 'absent': False}, out


def test_loosen_from_the_bracket_menu_and_from_lit_chips(page):
    """Right-click the snake's tag: Rename / Set home run / Loosen FOH.
    Loosen is ONE 'Loosen Snake' entry that empties the box's snakes; undo
    brings FOH back whole. Then a sweep inside the snake offers Loosen for
    just those chips, and takes them out leaving the rest snaked."""
    pg, ids = page
    bid = ids['boxId']
    tag = pg.locator(
        f'.hw-dock-grid[data-lrd-snake-owner="cvt:{bid}"] .hw-dock-snake-tag')
    tag.scroll_into_view_if_needed()
    b = tag.bounding_box()
    menu = _right_click(pg, b['x'] + b['width'] / 2, b['y'] + b['height'] / 2)
    assert [i['text'] for i in menu['items']] == [
        'Rename FOH', 'Set home run of FOH…', 'Loosen FOH'], menu
    index = pg.evaluate(STATE_JS, ids)['index']
    pg.locator('#context-menu [data-action="hw-snake-n2"]').click()
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids)
    assert st['box']['snakes'] == [], st
    assert st['action'] == 'Loosen Snake' and st['index'] == index + 1, st
    assert pg.evaluate(TRAY_JS, ['cvt', bid])['brackets'] == []
    pg.evaluate('() => window.app.undo()')
    pg.wait_for_timeout(1200)
    st = pg.evaluate(STATE_JS, ids)
    assert st['box']['snakes'][0]['name'] == 'FOH' and st['index'] == index
    assert st['box']['snakes'][0]['ports'] == [1, 2, 3, 4, 5, 6]
    # a sweep over 5-6 inside FOH: Loosen these 2
    _alt_sweep(pg, ids['cardId'], 5, 6)
    x, y = _chip_center(pg, ids['cardId'], 5)
    menu = _right_click(pg, x, y)
    texts = [i['text'] for i in menu['items']]
    assert 'Snake these 2 (Alt+Enter)' in texts and 'Loosen these 2' in texts
    pg.locator('#context-menu .menu-option', has_text='Loosen these 2').click()
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids)
    assert st['box']['snakes'][0]['ports'] == [1, 2, 3, 4], st
    assert st['action'] == 'Loosen Snake' and st['index'] == index + 1, st
    tray = pg.evaluate(TRAY_JS, ['cvt', bid])
    assert [b['tag'] for b in tray['brackets']] == ["FOH · 4-way · 100'"], tray
    # "Set home run…" on a fresh selection snakes it and lands on its ft
    _alt_sweep(pg, ids['cardId'], 7, 8)
    x, y = _chip_center(pg, ids['cardId'], 8)
    _right_click(pg, x, y)
    pg.locator('#context-menu [data-action="hw-snake-n1"]').click()
    pg.wait_for_timeout(1200)
    st = pg.evaluate(STATE_JS, ids)
    assert [s['ports'] for s in st['box']['snakes']] == [[1, 2, 3, 4], [7, 8]]
    assert st['box']['snakes'][1]['name'] == 'SNAKE A', (
        'the first free default letter - FOH took none')
    new_id = st['box']['ids'][1]
    assert pg.evaluate(FOCUS_JS) == f'data-snake-ft-{bid}-{new_id}', (
        'Set home run… must open the sheet on the new snake\'s length')
    pg.keyboard.type('60')
    pg.keyboard.press('Tab')
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids)
    assert st['box']['snakes'][1]['ft'] == 60 and st['action'] == 'Set Snake Home Run'
    _sheet_open(pg, 'cvt', bid, False)


def test_quick_fill_is_one_entry_and_leaves_snakes_alone(page):
    """all 100' on the card's sheet writes every LOOSE socket (9, 10, 14,
    15, 16 - 11-13 ride SNAKE A) as ONE 'Set Port Cable', keeping 10's
    fiber pick; none forgets them all as one; undo restores."""
    pg, ids = page
    cid = ids['cardId']
    assert _sheet_open(pg, 'card', cid)['sheet']
    index = pg.evaluate(STATE_JS, ids)['index']
    pg.locator(f'[data-lrd-field="data-cable-fill-{cid}-100"]').click()
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids)
    assert st['card']['cables'] == {
        '9': {'ft': 100, 'connector': None},
        '10': {'ft': 100, 'connector': 'fiber'},
        '14': {'ft': 100, 'connector': None},
        '15': {'ft': 100, 'connector': None},
        '16': {'ft': 100, 'connector': None}}, st
    assert st['action'] == 'Set Port Cable' and st['index'] == index + 1, st
    assert st['card']['snakes'][0]['ports'] == [11, 12, 13]
    pg.locator(f'[data-lrd-field="data-cable-fill-{cid}-none"]').click()
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids)
    assert st['card']['cables'] == {} and st['index'] == index + 2, st
    pg.evaluate('() => window.app.undo()')
    pg.wait_for_timeout(1200)
    assert pg.evaluate(STATE_JS, ids)['card']['cables']['16'] == {
        'ft': 100, 'connector': None}
    pg.evaluate('() => window.app.undo()')
    pg.wait_for_timeout(1200)
    st = pg.evaluate(STATE_JS, ids)
    assert st['card']['cables'] == {'9': {'ft': 50, 'connector': None},
                                    '10': {'ft': 75, 'connector': 'fiber'}}
    _sheet_open(pg, 'card', cid, False)


# ── the sheet leaves the fold alone ──────────────────────────────────────
#
# The power side's rule ("when i have the multi collapsed and i open the
# cable size page and make changes and close the page it uncollapses the
# multi" - user, 2026-09-06), worn by the card and the box: the sheet
# rides between the header and the foldable body, so a folded record
# shows it without unfolding, and the commit's rebuild never opens a
# fold that never hid the field.

FOLD_JS = """([secId, kind, id]) => {
    const head = document.querySelector(`[data-lrd-sec="${secId}"]`);
    const sec = head.parentElement;
    const body = sec.querySelector(':scope > .lrd-sec-body');
    const sheet = document.querySelector(
        `.hw-dock-cablesheet[data-lrd-cable-sheet="${kind}:${id}"]`);
    const grid = document.querySelector(
        `.hw-dock-grid[data-lrd-snake-owner="${kind}:${id}"]`);
    return {
        collapsed: sec.classList.contains('lrd-sec-collapsed'),
        stored: localStorage.getItem(`ledRasterPanelCollapsed_${secId}`),
        bodyHidden: getComputedStyle(body).display === 'none',
        sheet: !!sheet,
        sheetVisible: !!(sheet && sheet.offsetParent !== null),
        gridVisible: !!(grid && grid.offsetParent !== null),
    };
}"""


def _fold_arrow(page, sec_id):
    page.locator(f'[data-lrd-sec="{sec_id}"] .lrd-sec-arrow').click()
    page.wait_for_timeout(300)


@pytest.mark.parametrize('which', ['card', 'box'])
def test_the_sheet_leaves_the_fold_alone(page, which):
    """Fold the record, open its sheet, type a length, close the sheet:
    still folded, key and render alike; unfolded stays unfolded through
    the same round."""
    pg, ids = page
    kind = 'card' if which == 'card' else 'cvt'
    owner = ids['cardId'] if which == 'card' else ids['boxId']
    sec = (f'hwdock-card-{ids["cardId"]}' if which == 'card'
           else f'hwdock-box-{ids["boxId"]}')
    _sheet_open(pg, kind, owner, False)
    args = [sec, kind, owner]
    _fold_arrow(pg, sec)
    st = pg.evaluate(FOLD_JS, args)
    assert st['collapsed'] and st['stored'] == '1' and st['bodyHidden'], st
    _sheet_open(pg, kind, owner, True)
    st = pg.evaluate(FOLD_JS, args)
    assert st['sheet'] and st['sheetVisible'], (
        f'a folded {which} must still show the sheet it was asked for: {st}')
    assert st['collapsed'] and st['stored'] == '1', (
        f'opening the sheet unfolded the {which}: {st}')
    sheet = pg.evaluate(SHEET_JS, [kind, owner])
    row = next(r for r in sheet['rows'] if r['ftKey'] and r['kind'] != 'snake')
    index = pg.evaluate(STATE_JS, ids)['index']
    ft = pg.locator(f'[data-lrd-field="{row["ftKey"]}"]')
    ft.fill('20')
    ft.press('Tab')
    pg.wait_for_timeout(900)
    assert pg.evaluate(STATE_JS, ids)['index'] == index + 1
    st = pg.evaluate(FOLD_JS, args)
    assert st['collapsed'] and st['stored'] == '1' and st['sheetVisible'], (
        f'a length commit unfolded the {which}: {st}')
    _sheet_open(pg, kind, owner, False)
    st = pg.evaluate(FOLD_JS, args)
    assert not st['sheet'] and not st['gridVisible'], st
    assert st['collapsed'] and st['stored'] == '1' and st['bodyHidden'], (
        f'closing the sheet unfolded the {which}: {st}')
    _fold_arrow(pg, sec)
    st = pg.evaluate(FOLD_JS, args)
    assert not st['collapsed'] and st['stored'] == '0' and st['gridVisible'], st
    # unfolded stays unfolded through the same round
    _sheet_open(pg, kind, owner, True)
    ft = pg.locator(f'[data-lrd-field="{row["ftKey"]}"]')
    ft.fill('30')
    ft.press('Tab')
    pg.wait_for_timeout(900)
    assert pg.evaluate(STATE_JS, ids)['index'] == index + 2
    st = pg.evaluate(FOLD_JS, args)
    assert st['sheetVisible'] and not st['collapsed'] and st['stored'] == '0', st
    _sheet_open(pg, kind, owner, False)
    st = pg.evaluate(FOLD_JS, args)
    assert st['gridVisible'] and not st['collapsed'] and st['stored'] == '0', st
    pg.evaluate('() => window.app.undo()')
    pg.wait_for_timeout(1200)
    pg.evaluate('() => window.app.undo()')
    pg.wait_for_timeout(1200)
    assert pg.evaluate(STATE_JS, ids)['index'] == index
