"""Clear on a processor or a box is one request (owner, 2026-11-16).

"When I clear distros it is instant but processors is really slow." A
distro's Clear runs in the page and saves once. A card's or a box's Clear
sent one release per port, one after another: each request carried every
screen, the server re-solved the whole assignment and saved the project,
and the page applied the answer and re-drew before the next one went. A
processor with 30 ports took 30 round trips.

Now the card's pins go in ONE release (routes_port_assignment _unpin_many,
`pins` on /api/port-assignments/unpin) and its per-port backup picks in ONE
card edit (`clearBackups` on the card PUT). Each pin comes off exactly as
its own release did: a copy screen's pin unplugs the copy, a released
socket forgets its port cable, a source unplugged takes its copy with it.
The gesture is still one history step, so Ctrl+Z puts pins, picks and
cables back together and Ctrl+Shift+Z takes them off again.

Here:
* the routes, through the Flask client: the batch leaves the project
  exactly as the per-port chain did (mirror rig, port cables, a picked
  backup), and refuses a malformed list;
* the tray, in the browser: a real right-click Clear on an SX40 with its XD
  boxes sends one release (and one card edit for the picks), lands on the
  same state the old per-port chain reached from the same start, and undo
  and redo move it as one step.

Run locally:
    python -m pytest tests/test_card_clear_one_request.py -n 4 --dist loadfile
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import app as app_module  # noqa: E402
from app import _build_initial_project  # noqa: E402

from test_copy_mode import (  # noqa: E402
    H4, _ok, add_boxes, h9, pin, screen, set_mirror, slot_card)


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# ── the routes ────────────────────────────────────────────────────────────

def _fresh():
    app_module.current_project = _build_initial_project()
    app_module.next_layer_id = 1


def _rig(client):
    """A copy-mode card: SL on ports 1-3 with SR mirroring it (on the copy
    sockets 17-19). A plain card beside it: C on ports 1-3, a port cable on
    each, and port 1's hand-picked backup on port 10."""
    pid = h9(client)
    cid = slot_card(client, pid, 0, H4, 'copy')
    add_boxes(client, pid, cid, 4)
    plain = slot_card(client, pid, 1, 'novastar-card-h-20xrj45')
    a = screen(client, 'SL')
    b = screen(client, 'SR')
    c = screen(client, 'C')
    screens = [{'layerId': str(a), 'name': 'SL', 'ports': 3},
               {'layerId': str(b), 'name': 'SR', 'ports': 3},
               {'layerId': str(c), 'name': 'C', 'ports': 3}]
    for i in range(3):
        _ok(pin(client, screens, a, i, cid, i + 1))
        _ok(pin(client, screens, c, i, plain, i + 1))
    set_mirror(client, b, a)
    _ok(client.put(f'/api/processors/{pid}/cards/{plain}', json={
        'portCables': {str(n): {'ft': 50} for n in range(1, 4)}}))
    _ok(client.put(f'/api/processors/{pid}/cards/{plain}/ports/1',
                   json={'backup': {'cardId': plain, 'port': 10}}))
    sent = [dict(s, mirrorOf=str(a)) if s['layerId'] == str(b) else s
            for s in screens]
    # The order the tray lists them in: every screen's ports on the card.
    pins = ([{'layerId': str(a), 'index': i} for i in range(3)]
            + [{'layerId': str(b), 'index': i} for i in range(3)]
            + [{'layerId': str(c), 'index': i} for i in range(3)])
    return pid, plain, b, sent, pins


def _project(client):
    proj = client.get('/api/project').get_json()
    for key in ('is_pristine', 'modified', 'saved_at'):
        proj.pop(key, None)
    return proj


def _old_chain(client, pid, cid, b, sent, pins):
    """What the page used to send: one release per pin, each with the
    screens as the page held them then (a copy it was told it unplugged
    no longer says mirrorOf), then one backup clear per picked port."""
    cleared = set()
    for p in pins:
        screens = [{k: v for k, v in s.items() if k != 'mirrorOf'}
                   if s['layerId'] in cleared else s for s in sent]
        body = _ok(client.post('/api/port-assignments/unpin', json=dict(
            p, screens=screens)))
        cleared.update(str(i) for i in body.get('mirrorsCleared') or [])
    _ok(client.put(f'/api/processors/{pid}/cards/{cid}/ports/1',
                   json={'backup': None}))
    return cleared


def test_one_release_leaves_the_project_as_the_per_port_chain_did(client):
    _fresh()
    pid, cid, b, sent, pins = _rig(client)
    old_cleared = _old_chain(client, pid, cid, b, sent, pins)
    want = _project(client)

    _fresh()
    pid, cid, b, sent, pins = _rig(client)
    body = _ok(client.post('/api/port-assignments/unpin', json={
        'screens': sent, 'pins': pins}))
    # the copy is unplugged once, as it was by the chain
    assert body['mirrorsCleared'] == [b]
    assert old_cleared == {str(b)}
    _ok(client.put(f'/api/processors/{pid}/cards/{cid}',
                   json={'clearBackups': [1]}))
    got = _project(client)
    card = next(s['card'] for s in got['processors'][0]['slots']
                if s['card'] and s['card']['id'] == cid)
    assert 'portCables' not in card and 'backupPorts' not in card, card

    assert got['port_assignments'] == want['port_assignments']
    assert got['port_assignments']['pins'] == []
    assert got['processors'] == want['processors']
    assert [l.get('dataMirrorOf') for l in got['layers']] \
        == [l.get('dataMirrorOf') for l in want['layers']]
    assert got == want


def test_a_release_list_refuses_a_malformed_pin(client):
    _fresh()
    pid, cid, b, sent, pins = _rig(client)
    before = _project(client)
    for bad in ([], 'all', [{'index': 0}], [{'layerId': '1', 'index': 'x'}]):
        resp = client.post('/api/port-assignments/unpin', json={
            'screens': sent, 'pins': bad})
        assert resp.status_code == 400, (bad, resp.get_data(as_text=True))
    for bad in ('4', [0], [True], ['4']):
        resp = client.put(f'/api/processors/{pid}/cards/{cid}',
                          json={'clearBackups': bad})
        assert resp.status_code == 400, (bad, resp.get_data(as_text=True))
    assert _project(client) == before


def test_one_pin_in_the_list_is_the_single_release(client):
    _fresh()
    pid, cid, b, sent, pins = _rig(client)
    _ok(client.post('/api/port-assignments/unpin', json={
        'screens': sent, 'layerId': pins[6]['layerId'], 'index': 0}))
    want = _project(client)
    _fresh()
    pid, cid, b, sent, pins = _rig(client)
    _ok(client.post('/api/port-assignments/unpin', json={
        'screens': sent, 'pins': [pins[6]]}))
    assert _project(client) == want


# ── the tray ──────────────────────────────────────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

MOD = 'Meta' if sys.platform == 'darwin' else 'Control'

# Three Brompton screens on one SX40 (its four XD boxes), a port cable on
# every socket, and hand-picked backups on the first two ports.
SEED_JS = """async () => {
    const j = async (method, url, body) => (await fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)})).json();
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheetEdits;
    delete proj.fiberCables; delete proj.snakes;
    await j('PUT', '/api/project', proj);
    for (let i = 0; i < 3; i++) {
        await j('POST', '/api/layer/add', {name: `W${i + 1}`, columns: 6,
            rows: 4, cabinet_width: 192, cabinet_height: 384,
            offset_x: i * 1152});
    }
    // Brompton screens (the add takes no processing; the layer does)
    const p2 = await j('GET', '/api/project');
    p2.layers.forEach(l => { l.processorType = 'brompton'; });
    await j('PUT', '/api/project', p2);
    const st = await j('POST', '/api/processors', {deviceId: 'brompton-sx40'});
    const pr = st.processors[st.processors.length - 1];
    return {pid: pr.id, cid: pr.slots[0].card.id};
}"""

ATTACH_JS = """async (ids) => {
    const app = window.app;
    for (const l of app.project.layers) {
        await app._assignmentRequest('/api/port-assignments/place-overflow',
            'POST', {layerId: String(l.id), cardId: ids.cid}, null, 'Place');
    }
    const held = [];
    (app._assignment.screens || []).forEach(scr => (scr.ports || [])
        .forEach(p => { if (p.cardId === ids.cid) held.push(p.port); }));
    held.sort((a, b) => a - b);
    const put = (url, body) => fetch(url, {method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body)}).then(r => r.json());
    // each port cable on the box that delivers its socket, where the
    // cable sheet types it
    const card = app._dockCardById(ids.cid).card;
    for (const box of card.cvts || []) {
        const cables = {};
        (box.ports || []).forEach(p => {
            if (held.includes(p.number)) cables[p.number] = {ft: 50};
        });
        if (Object.keys(cables).length) {
            await put(`/api/processors/${ids.pid}/cvts/${box.id}`, {portCables: cables});
        }
    }
    const free = [];
    for (let n = 1; free.length < 2 && n < 200; n++) {
        if (!held.includes(n)) free.push(n);
    }
    const picks = [];
    for (let k = 0; k < 2; k++) {
        const r = await put(`/api/processors/${ids.pid}/cards/${ids.cid}/ports/${held[k]}`,
                            {backup: {cardId: ids.cid, port: free[k]}});
        if (r && r.resolved) picks.push(held[k]);
    }
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.resetHistory('Seed');
    return {held: held.length, picks};
}"""

FETCH_COUNT_JS = """(() => {
    const orig = window.fetch;
    window.__lrdFetches = 0;
    window.__sent = [];
    window.fetch = function (...args) {
        window.__lrdFetches++;
        window.__sent.push([String(args[0]).replace(location.origin, ''),
                            (args[1] && args[1].method) || 'GET']);
        const sent = orig.apply(this, args);
        const done = () => setTimeout(() => { window.__lrdFetches--; }, 0);
        sent.then(r => r.clone().text().then(done, done), done);
        return sent;
    };
})()"""

QUIET_JS = """() => {
    const app = window.app;
    const idle = window.__lrdFetches === 0 && !app._saveStateTimer
        && !app._dockMasonryRaf;
    window.__lrdQuiet = idle ? (window.__lrdQuiet || 0) + 1 : 0;
    return window.__lrdQuiet >= 2;
}"""

# What a Clear changes, in the page and on the server.
STATE_JS = """async (cid) => {
    const app = window.app;
    const card = (procs) => {
        for (const p of procs || []) for (const s of p.slots || []) {
            if (s.card && s.card.id === cid) return s.card;
        }
        return null;
    };
    const some = (o) => (o && Object.keys(o).length ? o : null);
    const pick = (c) => ({backupPorts: some(c.backupPorts),
                          portCables: [c, ...(c.cvts || [])]
                              .map(d => some(d.portCables))});
    const srv = await (await fetch('/api/project')).json();
    return {
        page: {pins: ((app.project.port_assignments || {}).pins || []),
               card: pick(card(app.project.processors))},
        server: {pins: ((srv.port_assignments || {}).pins || []),
                 card: pick(card(srv.processors))},
        onCard: (app._assignment.screens || []).reduce((n, s) => n
            + (s.ports || []).filter(p => p.cardId === cid).length, 0),
        history: app.history.length,
        last: app.history.length ? app.history[app.history.length - 1].action : null,
    };
}"""

# The page's old Clear, step for step: one release per pin (the last one
# taking the history step only when no pick follows), then one backup
# clear per picked port, the last of them taking the step.
OLD_CLEAR_JS = """async (cid) => {
    const app = window.app;
    const pins = [];
    app._assignment.screens.forEach(s => (s.ports || []).forEach(p => {
        if (p.cardId === cid) pins.push({layerId: s.layerId, index: p.index});
    }));
    const found = app._dockCardById(cid);
    const picks = Object.keys(found.card.backupPorts || {}).map(Number);
    for (let i = 0; i < pins.length; i++) {
        await app._assignmentRequest('/api/port-assignments/unpin', 'POST',
            pins[i], null, i === pins.length - 1 && !picks.length
                ? 'Release Ports' : null);
    }
    for (let i = 0; i < picks.length; i++) {
        await app._processorRequest(
            `/api/processors/${found.proc.id}/cards/${cid}/ports/${picks[i]}`,
            'PUT', {backup: null}, i === picks.length - 1 ? 'Old clear' : null);
    }
    return pins.length;
}"""


def landed(pg):
    pg.evaluate("() => { window.__lrdQuiet = 0; }")
    pg.wait_for_function(QUIET_JS, timeout=60000)


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    context.add_init_script(FETCH_COUNT_JS)
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    for ep in ('save-file', 'open-file', 'select-directory'):
        pg.route(f'**/api/native-dialog/{ep}',
                 lambda route: route.fulfill(status=403, body=''))
    ready = ("() => window.app && window.app._initialLoadComplete === true"
             " && window.app._socketConnects >= 1")
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function(ready)
    ids = pg.evaluate(SEED_JS)
    pg.reload(wait_until='domcontentloaded')
    pg.wait_for_function(ready)
    landed(pg)
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_function(
        "() => window.canvasRenderer.viewMode === 'data-flow'")
    landed(pg)
    seeded = pg.evaluate(ATTACH_JS, ids)
    landed(pg)
    yield pg, ids, seeded, errors
    context.close()


def _clear_card(pg, cid):
    key = f'card-{cid}'
    pg.evaluate("""(key) => {
        const el = document.querySelector(`[data-hwdock="${key}"]`);
        if (el) el.scrollIntoView({ block: 'nearest' });
    }""", key)
    box = pg.locator(f'[data-hwdock="{key}"]').bounding_box()
    assert box, f'no dock card {key}'
    pg.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2,
                   button='right')
    item = pg.locator('#context-menu [data-action="hw-clear"]')
    assert item.is_visible(), 'the card menu has no clear'
    pg.evaluate("() => { window.__sent = []; }")
    item.click()
    landed(pg)


def _keys(pg, combo):
    pg.evaluate("() => { if (document.activeElement) document.activeElement.blur(); }")
    pg.keyboard.press(combo)
    landed(pg)


def test_clearing_a_processor_is_one_release_and_one_undo_step(page):
    pg, ids, seeded, errors = page
    cid = ids['cid']
    assert seeded['held'] >= 9, seeded
    assert seeded['picks'], f'no backup pick took on the SX40: {seeded}'
    before = pg.evaluate(STATE_JS, cid)
    assert before['onCard'] == seeded['held']
    assert before['page'] == before['server']
    assert before['page']['card']['backupPorts']
    assert any(before['page']['card']['portCables'])
    word = pg.evaluate(
        "(cid) => window.app.unitWordTitle(window.app.unitWordForCard(cid))",
        cid)

    _clear_card(pg, cid)
    sent = pg.evaluate("() => window.__sent")
    unpins = [s for s in sent if s[0] == '/api/port-assignments/unpin']
    port_puts = [s for s in sent if '/ports/' in s[0]]
    card_puts = [s for s in sent
                 if s == [f"/api/processors/{ids['pid']}/cards/{cid}", 'PUT']]
    assert len(unpins) == 1, (
        f'{len(unpins)} releases for one Clear of {seeded["held"]} ports')
    assert port_puts == [] and len(card_puts) == 1, sent
    after = pg.evaluate(STATE_JS, cid)
    assert after['onCard'] == 0
    assert after['page'] == after['server']
    assert after['page']['card']['backupPorts'] is None
    assert not any(after['page']['card']['portCables'])
    assert after['history'] == before['history'] + 1
    assert after['last'] == f'Clear {word}'

    # one Ctrl+Z puts every pin, pick and cable back
    _keys(pg, f'{MOD}+z')
    undone = pg.evaluate(STATE_JS, cid)
    assert undone['page'] == before['page'], undone
    assert undone['server'] == before['server'], undone
    assert undone['onCard'] == seeded['held']
    # and Ctrl+Shift+Z takes them all off again
    _keys(pg, f'{MOD}+Shift+z')
    redone = pg.evaluate(STATE_JS, cid)
    assert redone['page'] == after['page'], redone
    assert redone['server'] == after['server'], redone
    assert redone['onCard'] == 0

    # The same start, cleared the old way, lands on the same state.
    _keys(pg, f'{MOD}+z')
    assert pg.evaluate(STATE_JS, cid)['page'] == before['page']
    count = pg.evaluate(OLD_CLEAR_JS, cid)
    landed(pg)
    assert count == seeded['held']
    old = pg.evaluate(STATE_JS, cid)
    assert old['page'] == after['page'], old
    assert old['server'] == after['server'], old
    assert errors == []


def test_clearing_one_box_releases_only_its_ports_in_one_request(page):
    pg, ids, seeded, errors = page
    cid = ids['cid']
    # start from every port on the card again
    pg.evaluate("""async (ids) => {
        const app = window.app;
        for (const l of app.project.layers) {
            await app._assignmentRequest('/api/port-assignments/place-overflow',
                'POST', {layerId: String(l.id), cardId: ids.cid}, null, 'Place');
        }
    }""", ids)
    landed(pg)
    payload = pg.evaluate("""(cid) => {
        const el = [...document.querySelectorAll('[data-hwdock^="box-"]')]
            .find(e => JSON.parse(e.dataset.hwdockPayload).cardId === cid);
        return {key: el.dataset.hwdock, ...JSON.parse(el.dataset.hwdockPayload)};
    }""", cid)
    span = pg.evaluate("""([cid, first, last]) => window.app._assignment.screens
        .reduce((n, s) => n + (s.ports || []).filter(p => p.cardId === cid
            && p.port >= first && p.port <= last).length, 0)""",
                       [cid, payload['first'], payload['last']])
    total = pg.evaluate(STATE_JS, cid)['onCard']
    assert span > 1 and total > span, (span, total)
    hist = pg.evaluate("() => window.app.history.length")
    box = pg.locator(f'[data-hwdock="{payload["key"]}"]').bounding_box()
    pg.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2,
                   button='right')
    item = pg.locator('#context-menu [data-action="hw-clear"]')
    assert item.is_visible()
    pg.evaluate("() => { window.__sent = []; }")
    item.click()
    landed(pg)
    sent = pg.evaluate("() => window.__sent")
    assert [s for s in sent if s[0] == '/api/port-assignments/unpin'] \
        == [['/api/port-assignments/unpin', 'POST']], sent
    now = pg.evaluate(STATE_JS, cid)
    assert now['onCard'] == total - span
    assert now['page'] == now['server']
    assert now['history'] == hist + 1 and now['last'] == 'Release Ports'
    assert errors == []
