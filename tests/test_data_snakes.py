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
    numbers; a port is in at most one snake; a port in a snake rides the
    snake's home run, and its own portCables entry is its EXTENSION from
    the snake's fan-out ("when i use a snake i need to be able to add a
    secondary cable length incase i need an extension", 2026-09-07);
    connector null follows the port (the catalog's documented kind, else
    nothing). The connector list is CAT only: "panels dont take fiber.
    what would take fiber is processor to breakout box" - fiber is the
    box's trunk (test_box_fiber), never a port's or a snake's plug.
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

import json
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
                                                 'connector': 'cat'},
                       '12': {'ft': 0}},
    })
    assert r.status_code == 200, r.get_data(as_text=True)
    card = _raw(client, pid)['slots'][0]['card']
    assert [s['ports'] for s in card['snakes']] == [[9, 10, 11], [13, 14]]
    assert [s['name'] for s in card['snakes']] == ['SNAKE A', 'SNAKE B']
    assert card['snakes'][0]['ft'] == 100 and 'ft' not in card['snakes'][1]
    assert all(s['id'].startswith('snk') for s in card['snakes'])
    assert card['portCables'] == {
        '15': {'ft': 50}, '16': {'ft': 75, 'connector': 'cat'}}
    rcard = _resolved(client, pid)['slots'][0]['card']
    assert rcard['snakes'][0] == {
        'id': card['snakes'][0]['id'], 'name': 'SNAKE A', 'ft': 100,
        'connector': None, 'ports': [9, 10, 11]}
    assert rcard['portCables']['16'] == {'ft': 75, 'connector': 'cat'}
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
    # A snaked port's own cable is KEPT: it is the socket's extension from
    # the snake's fan-out (9 rides SNAKE A; 30' is the extension to its
    # panel), stored in the very same key a loose port's home run uses.
    r = client.put(f'/api/processors/{pid}/cards/{cid}', json={
        'portCables': {'9': {'ft': 30}, '15': {'ft': 50}}})
    assert r.status_code == 200
    assert _raw(client, pid)['slots'][0]['card']['portCables'] == {
        '9': {'ft': 30}, '15': {'ft': 50}}
    assert _resolved(client, pid)['slots'][0]['card']['portCables']['9'] \
        == {'ft': 30, 'connector': None}
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
    # fiber is the box's trunk, never a port's or a snake's plug
    ({'snakes': [{'ports': [1], 'connector': 'fiber'}]},
     "unknown connector 'fiber'"),
    ({'portCables': {'3': {'ft': 10, 'connector': 'fiber'}}},
     "unknown connector 'fiber'"),
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
    state payload - CAT alone: "panels dont take fiber. what would take
    fiber is processor to breakout box" (2026-09-07). A card's followed
    connector is the catalog's documented copper (rj45 → cat) and NOTHING
    where it is silent or fiber - the no-hardware-assumptions rule, so an
    undocumented box, and a panel lead off a fiber card, print a bare
    length rather than a guessed plug. A 'fiber' pick stored by an older
    file reads as "follows the port" rather than a plug the sheet cannot
    offer."""
    st = client.get('/api/processors').get_json()
    assert st['dataCableConnectors'] == [{'id': 'cat', 'name': 'CAT'}]
    assert catalog.data_port_connector(None, {'connector': 'rj45'}, None) \
        == 'cat'
    assert catalog.data_port_connector(None, {'connector': 'fiber'}, None) \
        is None
    assert catalog.data_port_connector({}, {}, {}) is None
    pid, cid, bid = _h9_with_card_and_box(client, 'novastar-card-h-4xfiber')
    rcard = _resolved(client, pid)['slots'][0]['card']
    assert rcard['portConnector'] is None
    assert rcard['cvts'][0]['portConnector'] is None, (
        'the CVT10 documents no connector and its card is fiber: nothing')
    snakes, cables = catalog.resolved_cable_store({
        'snakes': [{'id': 'snk1', 'name': 'OLD', 'ports': [1, 2],
                    'connector': 'fiber'}],
        'portCables': {'3': {'ft': 40, 'connector': 'fiber'},
                       '4': {'ft': 10, 'connector': 'cat'}}})
    assert snakes[0]['connector'] is None
    assert cables == {'3': {'ft': 40, 'connector': None},
                      '4': {'ft': 10, 'connector': 'cat'}}


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

# The sheet's rows as read: snake rows and port rows in order, its
# headers, how many selects it holds (none - the data plug is CAT and not
# asked), the buttons by key and by label, and whether the controls row
# comes BEFORE the table in DOM order (the controls ride on top).
SHEET_JS = """([kind, id]) => {
    const sheet = document.querySelector(
        `.hw-dock-cablesheet[data-lrd-cable-sheet="${kind}:${id}"]`);
    if (!sheet) return null;
    const table = sheet.querySelector('table');
    const quick = sheet.querySelector('.hw-dock-cable-quick');
    return {
        headers: [...sheet.querySelectorAll('th')].map(th => th.textContent),
        selects: sheet.querySelectorAll('select').length,
        cells: [...sheet.querySelectorAll('tr')].filter(tr => tr.querySelector('td'))
            .map(tr => tr.querySelectorAll('td').length),
        quickFirst: !!(quick && table && sheet.firstElementChild === quick
            && (quick.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING)),
        rows: [...sheet.querySelectorAll('tr')].filter(tr => tr.querySelector('td'))
            .map(tr => {
                const tds = [...tr.querySelectorAll('td')];
                const ft = tr.querySelector('.hw-dock-cable-ft');
                const name = tr.querySelector('.hw-dock-cable-name');
                return {
                    kind: tr.classList.contains('hw-dock-cable-snake') ? 'snake'
                        : tr.classList.contains('hw-dock-cable-member') ? 'member'
                        : tr.classList.contains('hw-dock-cable-free') ? 'free' : 'port',
                    label: name ? tr.querySelector('.hw-dock-cable-snake-cap').textContent
                        : tds[1].textContent,
                    name: name ? name.value : null,
                    nameSize: name ? name.size : null,
                    who: tds[2].textContent,
                    ft: ft ? ft.value : tds[3].textContent,
                    ftKey: ft ? ft.dataset.lrdField : null,
                };
            }),
        buttons: [...sheet.querySelectorAll('[data-lrd-field]')]
            .filter(el => el.tagName === 'BUTTON').map(el => el.dataset.lrdField),
        labels: [...sheet.querySelectorAll('.hw-dock-cable-quick button')]
            .map(el => el.textContent),
        unsnakeTitle: (sheet.querySelector(`[data-lrd-field="data-cable-loosen-${id}"]`) || {}).title,
        tickTitles: [...sheet.querySelectorAll('.hw-dock-cable-tick')].map(t => t.title),
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
    a lit chip: "Snake these 6 (Alt+Enter)" and "Set home run…" - no Unsnake,
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
    FOUR columns (tick · port · screen · home run - no CONNECTOR column and
    no select anywhere on it: CAT is the only data plug, so it is not
    asked; sheet-fit-mock.html Option A), the controls row ABOVE the rows
    reading Snake / Unsnake / all 100' / none, eight free rows with a
    field on every one. 50 on 9 is ONE 'Set Port Cable'; Tab lands on 10's
    field, 75 there is another. A plug stored on an entry (the model keeps
    `connector`) rides a re-typed length untouched. Flipped back, the chips
    wear 50' and 75' beside their occupant in blue, the rest nothing."""
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
    # four columns, no plug column, no select anywhere on the data sheet
    assert sheet['headers'] == ['', 'port', 'screen', 'home run'], sheet
    assert sheet['selects'] == 0 and set(sheet['cells']) == {4}, sheet
    assert pg.evaluate(f"""() => !document.querySelector(
        '[data-lrd-field="data-cable-connector-{cid}-9"]')"""), (
        'the data sheet asks no connector')
    # the controls ride on top, before the rows, and the word is Unsnake
    assert sheet['quickFirst'], sheet
    assert sheet['buttons'] == [
        f'data-cable-snake-{cid}', f'data-cable-loosen-{cid}',
        f'data-cable-fill-{cid}-100', f'data-cable-fill-{cid}-none'], sheet
    assert sheet['labels'] == ['Snake', 'Unsnake', "all 100'", 'none'], sheet
    assert 'Loosen' not in sheet['unsnakeTitle'], sheet['unsnakeTitle']
    assert all('Loosen' not in t and 'loosen' not in t
               for t in sheet['tickTitles']), sheet['tickTitles']
    assert all('above' in t for t in sheet['tickTitles']), sheet['tickTitles']
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
    # a plug stored on 10 through the model (the store keeps `connector`;
    # the pull list reads it) - then the sheet re-types 10's length and
    # the plug rides along untouched: nothing on the sheet writes it
    pg.evaluate("""(ids) => window.app.setPortCable(
        window.app._dataCableOwner('card', ids.cardId), 10,
        {ft: '70', connector: 'cat'})""", ids)
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids)
    assert st['card']['cables']['10'] == {'ft': 70, 'connector': 'cat'}, st
    assert st['action'] == 'Set Port Cable' and st['index'] == index + 3, st
    ft10 = pg.locator(f'[data-lrd-field="data-cable-ft-{cid}-10"]')
    ft10.fill('75')
    ft10.press('Tab')
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids)
    assert st['card']['cables']['10'] == {'ft': 75, 'connector': 'cat'}, st
    assert st['action'] == 'Set Port Cable' and st['index'] == index + 4, st
    reading = pg.evaluate("""(ids) => [9, 10].map(n =>
        window.app.dataPortCable(ids.cardId, n).text)""", ids)
    assert reading == ["50' CAT", "75' CAT"], reading
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
    as members that each carry an EXTENSION field (blank - "ext ␣ ft"),
    Tab walking the ft column through them in order. 25 on member 12 is
    ONE 'Set Port Extension' and reads "SNAKE A +25'"; undo takes the
    extension, then the snake."""
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
    # a member row carries its extension field, blank, keyed like a loose
    # port's ft (the same store); no plug column on member rows either
    assert [r['ft'] for r in sheet['rows'][3:6]] == [''] * 3, sheet
    assert [r['ftKey'] for r in sheet['rows'][3:6]] == [
        f'data-cable-ft-{cid}-{n}' for n in (11, 12, 13)], sheet
    assert sheet['selects'] == 0 and set(sheet['cells']) == {4}, sheet
    assert sheet['rows'][2]['name'] == 'SNAKE A', sheet
    # the snake's name field is sized to its text: max(6, len + 1)
    assert sheet['rows'][2]['nameSize'] == len('SNAKE A') + 1, sheet['rows'][2]
    # Tab walks from the snake's ft into its members' ext fields in order
    pg.locator(f'[data-lrd-field="data-snake-ft-{cid}-{st["card"]["ids"][0]}"]').focus()
    pg.keyboard.press('Tab')
    assert pg.evaluate(FOCUS_JS) == f'data-cable-ft-{cid}-11'
    pg.keyboard.press('Tab')
    assert pg.evaluate(FOCUS_JS) == f'data-cable-ft-{cid}-12'
    pg.keyboard.type('25')
    pg.keyboard.press('Tab')
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids)
    assert st['card']['cables'] == {'9': {'ft': 50, 'connector': None},
                                    '10': {'ft': 75, 'connector': 'cat'},
                                    '12': {'ft': 25, 'connector': None}}, st
    assert st['action'] == 'Set Port Extension' and st['index'] == index + 2, st
    assert st['card']['snakes'][0]['ports'] == [11, 12, 13], 'still snaked'
    reading = pg.evaluate("""(ids) => {
        const c = window.app.dataPortCable(ids.cardId, 12);
        return [c.kind, c.ext, c.text, window.app.runText(c)];
    }""", ids)
    assert reading == ['snake', 25, "SNAKE A +25'", "SNAKE A · no length +25'"], reading
    pg.evaluate('() => window.app.undo()')
    pg.wait_for_timeout(1200)
    st = pg.evaluate(STATE_JS, ids)
    assert '12' not in st['card']['cables'] and st['index'] == index + 1, st
    pg.evaluate('() => window.app.undo()')
    pg.wait_for_timeout(1200)
    st = pg.evaluate(STATE_JS, ids)
    assert st['card']['snakes'] == [] and st['index'] == index, st
    pg.evaluate('() => window.app.redo()')
    pg.wait_for_timeout(1200)
    assert pg.evaluate(STATE_JS, ids)['card']['snakes'][0]['ports'] == [11, 12, 13]
    _sheet_open(pg, 'card', cid, False)


def test_rename_and_home_run_commit_one_entry_each(page):
    """The box's sheet: its snake row carries the name and the ft (no
    plug - the data sheet asks none). FOH is 'Rename Snake', 100 is 'Set
    Snake Home Run' - one entry each; a plug set on the snake through the
    model (setSnake, 'Set Snake Home Run') is served and kept - and the
    bracket's tag follows: "FOH · 6-way · 100'"."""
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
    # Tab from the snake's ft walks on down the column: its first member's
    # ext field (1), the members in order, then the loose rows (7, 8)
    assert pg.evaluate(FOCUS_JS) == f'data-cable-ft-{bid}-1'
    pg.keyboard.press('Tab')
    pg.keyboard.press('Tab')
    pg.keyboard.press('Tab')
    pg.keyboard.press('Tab')
    pg.keyboard.press('Tab')
    pg.keyboard.press('Tab')
    assert pg.evaluate(FOCUS_JS) == f'data-cable-ft-{bid}-7'
    assert pg.evaluate(f"""() => !document.querySelector(
        '[data-lrd-field="data-snake-connector-{bid}-{snake_id}"]')"""), (
        'the snake row asks no connector')
    pg.evaluate("""([ids, sid]) => window.app.setSnake(
        window.app._dataCableOwner('cvt', ids.boxId), sid,
        {connector: 'cat'}, 'Set Snake Home Run')""", [ids, snake_id])
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids)
    assert st['box']['snakes'][0]['connector'] == 'cat', st
    assert st['action'] == 'Set Snake Home Run' and st['index'] == index + 3
    served = _served(pg, ids, lambda s: s['boxSnakes']
                     and s['boxSnakes'][0].get('connector') == 'cat')
    assert served['boxSnakes'][0] == {
        'id': snake_id, 'name': 'FOH', 'ft': 100, 'connector': 'cat',
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


def test_an_extension_reads_on_the_corner_the_tag_and_survives_loosen(page):
    """"when i use a snake i need to be able to add a secondary cable
    length incase i need an extension" (2026-09-07). 25 on box socket 3
    (it rides FOH) is ONE 'Set Port Extension': the chip wears "+25'" in
    its blue corner (the others in FOH nothing), the canvas tag beside
    WALL's port 3 reads "FOH +25'" with Show Cable Tags on, runText says
    "FOH 100' +25'", and the box's sheet member row holds 25. Unsnaking 3
    keeps the entry - it reads as the socket's own home run now ("25'
    CAT"). Undo twice puts it all back."""
    pg, ids = page
    bid = ids['boxId']
    index = pg.evaluate(STATE_JS, ids)['index']
    pg.evaluate("""(ids) => {
        const app = window.app;
        const owner = app._dataCableOwner('cvt', ids.boxId);
        return app.setPortCable(owner, 3, {ft: '25', connector: ''});
    }""", ids)
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids)
    assert st['box']['cables'] == {'3': {'ft': 25, 'connector': None}}, st
    assert st['action'] == 'Set Port Extension' and st['index'] == index + 1, st
    assert st['box']['snakes'][0]['ports'] == [1, 2, 3, 4, 5, 6]
    tray = pg.evaluate(TRAY_JS, ['cvt', bid])
    assert tray['corners'] == {'1': None, '2': None, '3': "+25'", '4': None,
                               '5': None, '6': None, '7': None, '8': None}, tray
    assert [b['tag'] for b in tray['brackets']] == ["FOH · 6-way · 100'"], (
        'the bracket tag is the snake\'s alone')
    reading = pg.evaluate("""(ids) => {
        const app = window.app;
        const c = app.dataPortCable(ids.cardId, 3);
        return [c.kind, c.ext, c.extConnector, c.text, app.runText(c),
                app.runText(app.dataPortCable(ids.cardId, 2))];
    }""", ids)
    assert reading == ['snake', 25, None, "FOH +25'", "FOH 100' +25'", "FOH 100'"], reading
    # the sheet's member row holds it
    assert _sheet_open(pg, 'cvt', bid)['sheet']
    sheet = pg.evaluate(SHEET_JS, ['cvt', bid])
    members = [(r['kind'], r['ft'], r['ftKey']) for r in sheet['rows'][1:7]]
    assert members[2] == ('member', '25', f'data-cable-ft-{bid}-3'), members
    assert [m[1] for m in members] == ['', '', '25', '', '', ''], members
    _sheet_open(pg, 'cvt', bid, False)
    # the canvas tag: the snake's name plus the extension
    frame = pg.evaluate("""(ids) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === ids.id);
        l.showDataCableTags = true;
        try { return (%s)(); } finally { l.showDataCableTags = false; }
    }""" % FRAME_TEXTS_JS, ids)
    assert sorted(frame['interactive']) == sorted(['FOH'] * 5 + ["FOH +25'"]), frame
    assert sorted(frame['exported']) == sorted(frame['interactive']), frame
    # unsnake 3 out of FOH: the entry stays and is its own home run now
    pg.evaluate("""(ids) => {
        const app = window.app;
        return app.loosenPorts(app._dataCableOwner('cvt', ids.boxId), [3]);
    }""", ids)
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids)
    assert st['box']['snakes'][0]['ports'] == [1, 2, 4, 5, 6], st
    assert st['box']['cables'] == {'3': {'ft': 25, 'connector': None}}, st
    assert st['action'] == 'Unsnake' and st['index'] == index + 2, st
    loose = pg.evaluate("""(ids) => {
        const c = window.app.dataPortCable(ids.cardId, 3);
        return [c.kind, c.text];
    }""", ids)
    assert loose == ['cable', "25' CAT"], loose
    assert pg.evaluate(TRAY_JS, ['cvt', bid])['corners']['3'] == "25'"
    for _ in range(2):
        pg.evaluate('() => window.app.undo()')
        pg.wait_for_timeout(1200)
    st = pg.evaluate(STATE_JS, ids)
    assert st['box']['cables'] == {} and st['index'] == index, st
    assert st['box']['snakes'][0]['ports'] == [1, 2, 3, 4, 5, 6], st


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


def test_unsnake_from_the_bracket_menu_and_from_lit_chips(page):
    """Right-click the snake's tag: Rename / Set home run / Unsnake FOH
    ("dont call it loosen", 2026-09-07 - Unsnake is the opposite of the
    Snake button; Unpair is the redundancy bar's word). Unsnake is ONE
    'Unsnake' entry that empties the box's snakes; undo brings FOH back
    whole. Then a sweep inside the snake offers Unsnake for just those
    chips, and takes them out leaving the rest snaked."""
    pg, ids = page
    bid = ids['boxId']
    tag = pg.locator(
        f'.hw-dock-grid[data-lrd-snake-owner="cvt:{bid}"] .hw-dock-snake-tag')
    tag.scroll_into_view_if_needed()
    b = tag.bounding_box()
    menu = _right_click(pg, b['x'] + b['width'] / 2, b['y'] + b['height'] / 2)
    assert [i['text'] for i in menu['items']] == [
        'Rename FOH', 'Set home run of FOH…', 'Unsnake FOH'], menu
    index = pg.evaluate(STATE_JS, ids)['index']
    pg.locator('#context-menu [data-action="hw-snake-n2"]').click()
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids)
    assert st['box']['snakes'] == [], st
    assert st['action'] == 'Unsnake' and st['index'] == index + 1, st
    assert pg.evaluate(TRAY_JS, ['cvt', bid])['brackets'] == []
    pg.evaluate('() => window.app.undo()')
    pg.wait_for_timeout(1200)
    st = pg.evaluate(STATE_JS, ids)
    assert st['box']['snakes'][0]['name'] == 'FOH' and st['index'] == index
    assert st['box']['snakes'][0]['ports'] == [1, 2, 3, 4, 5, 6]
    # a sweep over 5-6 inside FOH: Unsnake these 2
    _alt_sweep(pg, ids['cardId'], 5, 6)
    x, y = _chip_center(pg, ids['cardId'], 5)
    menu = _right_click(pg, x, y)
    texts = [i['text'] for i in menu['items']]
    assert 'Snake these 2 (Alt+Enter)' in texts and 'Unsnake these 2' in texts
    assert not any('Loosen' in t for t in texts), texts
    pg.locator('#context-menu .menu-option', has_text='Unsnake these 2').click()
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids)
    assert st['box']['snakes'][0]['ports'] == [1, 2, 3, 4], st
    assert st['action'] == 'Unsnake' and st['index'] == index + 1, st
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
    CAT pick; none forgets them all as one; undo restores."""
    pg, ids = page
    cid = ids['cardId']
    assert _sheet_open(pg, 'card', cid)['sheet']
    index = pg.evaluate(STATE_JS, ids)['index']
    pg.locator(f'[data-lrd-field="data-cable-fill-{cid}-100"]').click()
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids)
    assert st['card']['cables'] == {
        '9': {'ft': 100, 'connector': None},
        '10': {'ft': 100, 'connector': 'cat'},
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
                                    '10': {'ft': 75, 'connector': 'cat'}}
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


# ── the backup sheet reads like the primary ───────────────────────────────
#
# The user's own show (experts-only.json): card "Card 1" backed 1:1 by
# "Card 4"; box A on Card 1 carries SNAKE A over sockets 1-4 (SR - MAIN's
# four ports), box B on Card 4 carries a SNAKE A over the sockets their
# returns land on. Box B's snake row once read "SR - MAIN p1 return, SR -
# MAIN p2 return, SR - MAIN p3 return, SR - MAIN p4 return" - a 1012px
# table inside a 491px sheet, the HOME RUN and CONNECTOR cells (the
# extension inputs) pushed off the right edge. "when redundancy is set and
# a snake is used there is way too much info and it pushes all the
# extension area off screen ... it can look just like the primary"
# (2026-09-07).

SCRATCH_FIXTURE = os.environ.get('LRD_PULL_SMOKE_JSON') or os.path.join(
    '/private/tmp/claude-501',
    '-Users-mattknotts-Nextcloud-LED-LED-Wall-Tech-Raster-Software-LED-Raster-Designer',
    'be6afb3b-7607-4f06-8c12-a10cd58068e9', 'scratchpad', 'experts-only.json')

# One box's sheet as laid out: every row's SCREEN cell and title, and the
# geometry the bug was - the table against the sheet, and the HOME RUN
# cell (the last column now - no CONNECTOR column on the data sheet)
# against the sheet's right edge.
BOX_SHEET_JS = """(id) => {
    const sheet = document.querySelector(
        `.hw-dock-cablesheet[data-lrd-cable-sheet="cvt:${id}"]`);
    if (!sheet) return null;
    const table = sheet.querySelector('table');
    const s = sheet.getBoundingClientRect(), t = table.getBoundingClientRect();
    const rows = [...table.querySelectorAll('tr')].filter(tr => tr.querySelector('td'));
    return {
        sheetW: s.width, tableW: t.width, tableRight: t.right, sheetRight: s.right,
        rows: rows.map(tr => {
            const tds = [...tr.querySelectorAll('td')];
            const who = tr.querySelector('td.hw-dock-cable-who');
            const text = who.querySelector('.hw-dock-cable-who-text');
            const r3 = tds[3].getBoundingClientRect();
            return {
                kind: tr.classList.contains('hw-dock-cable-snake') ? 'snake'
                    : tr.classList.contains('hw-dock-cable-member') ? 'member'
                    : tr.classList.contains('hw-dock-cable-free') ? 'free' : 'port',
                who: who.textContent, whoTitle: who.title, rowTitle: tr.title,
                whoClipped: text.scrollWidth > text.clientWidth + 1,
                homeRunOn: r3.right <= s.right + 0.5 && r3.width > 0,
                cells: tds.length,
            };
        }),
    };
}"""


@pytest.mark.skipif(not os.path.exists(SCRATCH_FIXTURE),
                    reason='experts-only.json smoke fixture not present')
def test_the_backup_boxs_sheet_reads_like_the_primarys(e2e_server, pw_browser):
    """On his file, box B's snake row and its four member rows read
    "SR - MAIN" - exactly what box A's read - with the "p1 return" detail
    on the row's title; the table is never wider than the sheet, and the
    HOME RUN cell (the last one - four columns) sits on it, on both boxes.
    Runs in its own
    page so the module's seed is left alone, and puts the server's project
    back when it is done."""
    with open(SCRATCH_FIXTURE) as fh:
        project = json.load(fh)
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    try:
        pg.goto(e2e_server, wait_until='domcontentloaded')
        pg.wait_for_timeout(2000)
        before = pg.evaluate("async () => (await fetch('/api/project')).json()")
        try:
            pg.locator('[data-mode="data-flow"]').click()
            pg.wait_for_timeout(400)
            ids = pg.evaluate("""async (project) => {
                const app = window.app;
                const j = (method, url, body) => fetch(url, {method,
                    headers: {'Content-Type': 'application/json'},
                    body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
                await j('PUT', '/api/project', project);
                app.project = await j('GET', '/api/project');
                app.dedupeProjectLayers('snakes_backup_sheet');
                app.selectLayer(app.project.layers.find(l => l.name === 'SR - MAIN'));
                await app.refreshProcessors();
                await app.refreshPortAssignment();
                app.renderLayers();
                app.renderHardwareDock();
                const card = app._dockFindCard('card2').card;
                const backup = app._dockFindCard('card3').card;
                const boxA = card.cvts.find(c => c.name === 'A');
                const boxB = backup.cvts.find(c => c.name === 'B');
                return { a: boxA.id, b: boxB.id, snakeA: boxA.snakes[0].ports, snakeB: boxB.snakes[0].ports,
                         backup: backup.backupFor ? backup.backupFor.title : null };
            }""", project)
            pg.wait_for_timeout(800)
            assert ids['a'] == 'cvt8' and ids['b'] == 'cvt9', ids
            assert ids['snakeA'] == [1, 2, 3, 4] and ids['snakeB'] == [1, 2, 3, 4], ids
            assert ids['backup'], f'fixture: Card 4 must back Card 1: {ids}'
            sheets = {}
            for which in ('a', 'b'):
                pg.locator(f'[data-lrd-field="data-cable-sheet-{ids[which]}"]').click()
                pg.wait_for_timeout(500)
                sheets[which] = pg.evaluate(BOX_SHEET_JS, ids[which])
                assert sheets[which], f'box {which} has no sheet open'
            a, b = sheets['a'], sheets['b']
            # the primary: the snake row and its four members name the screen
            assert a['rows'][0]['kind'] == 'snake' and a['rows'][0]['who'] == 'SR - MAIN', a['rows'][0]
            assert [r['who'] for r in a['rows'][1:5]] == ['SR - MAIN'] * 4, a['rows']
            assert [r['kind'] for r in a['rows'][1:5]] == ['member'] * 4, a['rows']
            # the backup reads the same - the "p1 return" detail rides the titles
            assert b['rows'][0]['kind'] == 'snake' and b['rows'][0]['who'] == 'SR - MAIN', b['rows'][0]
            assert [r['who'] for r in b['rows'][1:5]] == ['SR - MAIN'] * 4, b['rows']
            assert 'p1 return' in b['rows'][0]['rowTitle'] and 'p4 return' in b['rows'][0]['rowTitle'], b['rows'][0]
            assert b['rows'][0]['whoTitle'] == b['rows'][0]['rowTitle'], b['rows'][0]
            for n, r in enumerate(b['rows'][1:5], start=1):
                assert r['rowTitle'] == f'SR - MAIN p{n} return', (n, r)
                assert r['whoTitle'] == f'SR - MAIN p{n} return', (n, r)
            # a primary row says nothing more than its cell, so no row title
            assert all(r['rowTitle'] == '' for r in a['rows'][:5]), a['rows']
            # the geometry: never a table wider than its sheet, every HOME
            # RUN cell on the sheet, four cells a row, nothing cut
            for which, sh in sheets.items():
                assert sh['tableW'] <= sh['sheetW'] + 0.5, (which, sh['tableW'], sh['sheetW'])
                assert sh['tableRight'] <= sh['sheetRight'] + 0.5, (which, sh)
                assert all(r['homeRunOn'] and r['cells'] == 4 for r in sh['rows']), (which, sh['rows'])
                assert not any(r['whoClipped'] for r in sh['rows']), (which, sh['rows'])
            assert errors == [], errors
        finally:
            pg.evaluate("""async (project) => {
                await fetch('/api/project', {method: 'PUT',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(project)});
            }""", before)
    finally:
        context.close()


def test_a_long_list_of_screens_cuts_to_an_ellipsis_never_widening_the_sheet(page):
    """Belt and braces for the cell itself: a SCREEN cell holding more than
    ~24ch of names clips with an ellipsis and carries the whole text as its
    title, so no list of screens can ever push the inputs off the sheet
    again - checked on the seed's card sheet by planting a long text in a
    cell's text block and measuring the table against the sheet."""
    pg, ids = page
    _sheet_open(pg, 'card', ids['cardId'], True)
    out = pg.evaluate("""(id) => {
        const sheet = document.querySelector(`.hw-dock-cablesheet[data-lrd-cable-sheet="card:${id}"]`);
        const table = sheet.querySelector('table');
        const td = sheet.querySelector('td.hw-dock-cable-who');
        const text = td.querySelector('.hw-dock-cable-who-text');
        const long = Array.from({length: 12}, (_, i) => `SCREEN NUMBER ${i + 1}`).join(', ');
        const before = table.getBoundingClientRect().width;
        text.textContent = long;
        td.title = long;
        const after = table.getBoundingClientRect().width;
        const cs = getComputedStyle(text);
        const r = td.getBoundingClientRect();
        return { before, after, sheetW: sheet.getBoundingClientRect().width,
                 clipped: text.scrollWidth > text.clientWidth + 1, cellW: r.width,
                 overflow: cs.overflow, ellipsis: cs.textOverflow, title: td.title === long };
    }""", ids['cardId'])
    _sheet_open(pg, 'card', ids['cardId'], False)
    assert out['after'] <= out['sheetW'] + 0.5, out
    assert out['clipped'] and out['overflow'] == 'hidden' and out['ellipsis'] == 'ellipsis', out
    assert out['title'], out


# The sheet against its box, the unit against the tray: widths read once
# the sheet is up, plus where every unit in the tray sits.
SHEET_FIT_JS = """([kind, id]) => {
    const sheet = document.querySelector(
        `.hw-dock-cablesheet[data-lrd-cable-sheet="${kind}:${id}"]`);
    if (!sheet) return null;
    const table = sheet.querySelector('table');
    const unit = sheet.closest('.hw-dock-unit');
    const body = document.getElementById('hardware-dock-body');
    const bs = getComputedStyle(body);
    const rect = (el) => { const r = el.getBoundingClientRect(); return {x: r.left, y: r.top, w: r.width, right: r.right}; };
    return {
        viewport: [window.innerWidth, window.innerHeight],
        sheet: rect(sheet), table: rect(table), unit: rect(unit),
        body: rect(body),
        bodyContentW: body.clientWidth - parseFloat(bs.paddingLeft) - parseFloat(bs.paddingRight),
        bodyContentLeft: body.getBoundingClientRect().left + body.clientLeft + parseFloat(bs.paddingLeft),
        units: [...body.querySelectorAll('.hw-dock-unit')].map(u => ({
            name: (u.querySelector('.hw-dock-unit-name') || {}).textContent || '',
            hasSheet: u === unit, ...rect(u)})),
        sheetMinW: parseFloat(getComputedStyle(sheet).minWidth),
        tableCssW: getComputedStyle(table).width,
        nameW: (() => { const n = sheet.querySelector('.hw-dock-cable-name');
            return n ? n.getBoundingClientRect().width : null; })(),
        sheetScrolls: sheet.scrollWidth > sheet.clientWidth + 1,
    };
}"""


def test_a_sheet_sizes_to_its_table_within_the_floor(page):
    """sheet-fit-mock.html, "i like option A but if we pass a threshold
    then grow like option B" (2026-09-07). On a 1440x900 window with TWO
    cards in the tray, a unit whose sheet is open takes what its table
    needs and no more: the table is never wider than the sheet, the unit
    is at least the sheet's 480px floor and never wider than the tray
    body, and the sheet has nothing to scroll sideways for. Then B's
    growth: the snake renamed to something long - its name field sized to
    its text - widens the table and the unit with it, still inside the
    tray; undo puts the name back."""
    pg, ids = page
    _sheet_open(pg, 'cvt', ids['boxId'], False)
    _sheet_open(pg, 'card', ids['cardId'], False)
    snake_id = pg.evaluate(STATE_JS, ids)['box']['ids'][0]
    try:
        pg.set_viewport_size({'width': 1440, 'height': 900})
        pg.wait_for_timeout(400)
        tray = _sheet_open(pg, 'cvt', ids['boxId'], True)
        assert tray['sheet'], tray
        out = pg.evaluate(SHEET_FIT_JS, ['cvt', ids['boxId']])
        assert out, 'the box has no sheet open'
        print('\nsheet fit at 1440x900:', json.dumps({k: out[k] for k in (
            'viewport', 'sheet', 'table', 'unit', 'bodyContentW', 'sheetMinW',
            'tableCssW', 'nameW', 'sheetScrolls', 'units')}))
        assert out['viewport'] == [1440, 900], out['viewport']
        # two cards in the tray, the sheet's on one of them
        assert len(out['units']) >= 2 and sum(1 for u in out['units'] if u['hasSheet']) == 1, out['units']
        # the table is no wider than the sheet, and lays out at content width
        assert out['table']['w'] <= out['sheet']['w'] + 1, (out['table'], out['sheet'])
        assert out['table']['right'] <= out['sheet']['right'] + 1, (out['table'], out['sheet'])
        assert not out['sheetScrolls'], out
        # the floor: 480px on the sheet; the unit is at least that and
        # never wider than the tray body - Option A, not the whole row
        assert out['sheetMinW'] == 480, out['sheetMinW']
        assert out['sheet']['w'] >= 480 - 0.5, out['sheet']
        assert 480 <= out['unit']['w'] <= out['bodyContentW'] + 1, (out['unit'], out['bodyContentW'])
        assert out['unit']['w'] < out['bodyContentW'] - 100, (
            'the unit must size to its table, not take the tray row', out['unit'], out['bodyContentW'])
        # B's growth: a long name widens the field, the table and the unit
        name = pg.locator(f'[data-lrd-field="data-snake-name-{ids["boxId"]}-{snake_id}"]')
        long_name = 'SR PRIMARY SNAKE TO FOH LEFT'
        index = pg.evaluate(STATE_JS, ids)['index']
        name.fill(long_name)
        name.press('Tab')
        pg.wait_for_timeout(900)
        st = pg.evaluate(STATE_JS, ids)
        assert st['box']['snakes'][0]['name'] == long_name and st['index'] == index + 1, st
        grown = pg.evaluate(SHEET_FIT_JS, ['cvt', ids['boxId']])
        print('sheet fit after the long name:', json.dumps({k: grown[k] for k in (
            'sheet', 'table', 'unit', 'nameW', 'sheetScrolls', 'units')}))
        size = pg.evaluate(f"""() => document.querySelector(
            '[data-lrd-field="data-snake-name-{ids["boxId"]}-{snake_id}"]').size""")
        assert size == len(long_name) + 1, size
        assert grown['nameW'] > out['nameW'] + 40, (grown['nameW'], out['nameW'])
        assert grown['table']['w'] > out['table']['w'] + 40, (grown['table'], out['table'])
        assert grown['unit']['w'] > out['unit']['w'] + 40, (grown['unit'], out['unit'])
        assert grown['table']['w'] <= grown['sheet']['w'] + 1, (grown['table'], grown['sheet'])
        assert grown['unit']['w'] <= grown['bodyContentW'] + 1, (grown['unit'], grown['bodyContentW'])
        assert not grown['sheetScrolls'], grown
        pg.evaluate('() => window.app.undo()')
        pg.wait_for_timeout(1200)
        st = pg.evaluate(STATE_JS, ids)
        assert st['box']['snakes'][0]['name'] == 'FOH' and st['index'] == index, st
        back = pg.evaluate(SHEET_FIT_JS, ['cvt', ids['boxId']])
        assert abs(back['unit']['w'] - out['unit']['w']) <= 1, (back['unit'], out['unit'])
    finally:
        _sheet_open(pg, 'cvt', ids['boxId'], False)
        pg.set_viewport_size({'width': 1700, 'height': 950})
        pg.wait_for_timeout(400)


# One port chip's occupant line as laid out: the occupant's text and the
# length beside it - does each read whole, and do the two ever overlap.
CHIP_LINE_JS = """([key, plant]) => {
    const face = document.querySelector(`[data-hwdock="${key}"]`);
    const tile = face && face.closest('.lrd-tile');
    if (!tile) return null;
    const lines = [...tile.querySelectorAll('.lrd-tile-face .lrd-tile-line')];
    const line = lines[1];
    const text = line.querySelector('.lrd-tile-text');
    const len = line.querySelector('.hw-dock-chip-cable-data');
    if (plant && text) text.textContent = plant;
    const r = (el) => el.getBoundingClientRect();
    const lr = r(line), tr = text ? r(text) : null, nr = len ? r(len) : null;
    return {
        lineText: line.textContent, flex: getComputedStyle(line).display,
        wrapped: !!text, who: text ? text.textContent : line.textContent,
        len: len ? len.textContent : null,
        whoFits: text ? text.scrollWidth <= text.clientWidth + 1 : null,
        lenFits: len ? len.scrollWidth <= len.clientWidth + 1 : null,
        disjoint: (text && len) ? (tr.right <= nr.left + 0.5 || nr.right <= tr.left + 0.5) : null,
        sameLine: (text && len) ? Math.abs(tr.bottom - nr.bottom) < 6 : null,
        lenOnLine: len ? (nr.left >= lr.left - 0.5 && nr.right <= lr.right + 0.5) : null,
        lenColor: len ? getComputedStyle(len).color : null,
        cableClass: line.classList.contains('lrd-tile-line-cable'),
        barBelow: (() => { const bar = tile.querySelector('.hw-dock-bar');
            return bar ? r(bar).top >= lr.bottom - 0.5 : null; })(),
    };
}"""


def test_a_chip_reads_its_occupant_and_its_length_side_by_side(page):
    """"adding the extensions on data ... you cant read them" (2026-09-07):
    the corner length sat OVER the occupant line. Now the length is in
    flow at the END of the occupant line: box port 5 carrying SL - MAIN
    (the wall renamed) and a 10' home run reads "SL - MAIN" then "10'" -
    the length whole, in the data blue, side by side and never
    overlapping (the occupant may ellipsize on a narrow chip; it is never
    drawn over), the bar row below them; a long occupant planted in the
    same chip ellipsizes while the length still reads whole and the two
    stay disjoint. A chip with no length keeps its plain line."""
    pg, ids = page
    cid, bid = ids['cardId'], ids['boxId']
    _sheet_open(pg, 'cvt', bid, False)
    index = pg.evaluate(STATE_JS, ids)['index']
    pg.evaluate("""(ids) => window.app.setPortCable(
        window.app._dataCableOwner('cvt', ids.boxId), 5, {ft: '10'})""", ids)
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids)
    assert st['box']['cables'].get('5') == {'ft': 10, 'connector': None}, st
    assert st['index'] == index + 1, st
    try:
        who = pg.evaluate("""async (ids) => {
            const app = window.app;
            await fetch(`/api/layer/${ids.id}`, {method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({name: 'SL - MAIN'})});
            app.project = await (await fetch('/api/project')).json();
            app.dedupeProjectLayers('snakes_chip_line');
            app.selectLayer(app.project.layers.find(l => l.id === ids.id));
            await app.refreshPortAssignment();
            app.renderLayers();
            app.renderHardwareDock();
            return app._portOccupants(ids.cardId, 5).map(o => o.name);
        }""", ids)
        pg.wait_for_timeout(600)
        assert who == ['SL - MAIN'], who
        line = pg.evaluate(CHIP_LINE_JS, [f'port-{cid}-5', None])
        print('\nchip line:', json.dumps(line))
        assert line and line['wrapped'] and line['cableClass'] and line['flex'] == 'flex', line
        assert line['who'] == 'SL - MAIN' and line['len'] == "10'", line
        # the LENGTH always reads whole; the occupant may ellipsize on a
        # narrow chip (the brief's rule) - it is never drawn over
        assert line['lenFits'], line
        assert line['disjoint'] and line['sameLine'] and line['lenOnLine'], line
        assert line['lenColor'] == 'rgb(143, 208, 255)', line['lenColor']
        assert line['barBelow'], line
        # a long occupant: the text ellipsizes, the length still reads whole
        long = pg.evaluate(CHIP_LINE_JS, [f'port-{cid}-5', 'SL - MAIN UPSTAGE LEFT WIDE RETURN'])
        print('chip line, long occupant:', json.dumps(long))
        assert long['whoFits'] is False, long
        assert long['lenFits'] and long['disjoint'] and long['lenOnLine'], long
        assert long['len'] == "10'", long
        # a chip with no length: the plain line, nothing wrapped
        plain = pg.evaluate(CHIP_LINE_JS, [f'port-{cid}-6', None])
        assert plain and not plain['wrapped'] and not plain['cableClass'], plain
        assert plain['len'] is None and plain['who'] == 'SL - MAIN', plain
    finally:
        pg.evaluate("""async (ids) => {
            const app = window.app;
            await fetch(`/api/layer/${ids.id}`, {method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({name: 'WALL'})});
            app.project = await (await fetch('/api/project')).json();
            app.dedupeProjectLayers('snakes_chip_line_back');
            app.selectLayer(app.project.layers.find(l => l.id === ids.id));
            await app.refreshPortAssignment();
            app.renderLayers();
            app.renderHardwareDock();
        }""", ids)
        pg.wait_for_timeout(600)
        pg.evaluate('() => window.app.undo()')
        pg.wait_for_timeout(1200)
    st = pg.evaluate(STATE_JS, ids)
    assert '5' not in st['box']['cables'] and st['index'] == index, st
    assert pg.evaluate("(ids) => window.app._portOccupants(ids.cardId, 5).map(o => o.name)", ids) == ['WALL']
