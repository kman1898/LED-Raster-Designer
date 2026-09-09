"""A snake holds sockets from any device: the show's snakes.

"also when i pair things in snakes they need to be able to be able to be
grouped together as well as done across cvt's" (user, 2026-09-09), and,
asked what one snake may hold: "Any sockets, any device". His example, from
the Kelly Clarkson show (IMAG A backed 1:1 by IMAG B): "i have ... ports 1-6
on a screen so ports 1-4 primary is snaked and backup 1-4 are snaked. then i
have 5 and 6 that i want to snake" - A-5, A-6, B-5 and B-6 as ONE 4-way,
across two breakout boxes on two cards.

So a snake cannot live on a card or a box any more. It lives on the SHOW and
names its members:

    project['snakes'] = [{id, name, ft?, connector?,
                          members: [{kind: 'card'|'cvt', id, socket}, ...]}]

  - POST /api/snakes forms one, PUT /api/snakes/<id> renames / re-lengths /
    re-plugs it, PUT /api/snakes/<id>/members sets its whole membership,
    POST /api/snakes/loosen takes members out of whatever holds them (one
    request, because one gesture is one undo step) and DELETE takes the
    loom apart. Every member must exist on its device, a socket rides ONE
    snake, and the connector must be one the list offers.
  - A member names the device that DELIVERS its socket - the box where one
    carries it, the card otherwise - and the server re-homes it when that
    changes (prune_show_snakes). That is the fix for the bug this model was
    built on: a snake typed on a card went invisible the moment a breakout
    box was hung on that card, because every reader is routed to the box
    and the box's own store had never heard of it.
  - Old saves are migrated on load: a card's or a box's `snakes` become
    show snakes over that device's sockets and the per-device key is
    dropped (migrate_device_snakes).

Port cables stay per device: a snaked socket's entry is its EXTENSION from
the snake's fan-out, and that is a fact about the socket.

Run locally (ONE pytest at a time - the browser-test servers use fixed
ports):
    python -m pytest tests/test_snakes_across.py -v --browser chromium
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import processor_catalog as catalog  # noqa: E402

SCRATCH_FIXTURE = os.path.join(
    '/private/tmp/claude-501',
    '-Users-mattknotts-Nextcloud-LED-LED-Wall-Tech-Raster-Software-LED-Raster-Designer',
    'be6afb3b-7607-4f06-8c12-a10cd58068e9', 'scratchpad',
    'experts-only-fixture.json')


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# ── the store, through the Flask client ──────────────────────────────────

def _two_cards_with_boxes(client, box='novastar-cvt4k-s'):
    """An H9 with two H_16xRJ45+2xfiber cards, a breakout box on each.

    The shape his example is drawn on: A and its 1:1 backup B, each
    delivering its card's sockets through a box of its own.
    """
    st = client.post('/api/processors',
                     json={'deviceId': 'novastar-h9'}).get_json()
    pid = st['processors'][-1]['id']
    ids = {'pid': pid}
    for slot, name in ((0, 'A'), (1, 'B')):
        st = client.put(f'/api/processors/{pid}/slots/{slot}',
                        json={'deviceId':
                              'novastar-card-h-16xrj45-2xfiber'}).get_json()
        proc = next(p for p in st['processors'] if p['id'] == pid)
        card = proc['slots'][slot]['card']
        client.put(f'/api/processors/{pid}/cards/{card["id"]}',
                   json={'name': name})
        ids[f'card{name}'] = card['id']
        if box:
            r = client.post(f'/api/processors/{pid}/cards/{card["id"]}/cvts',
                            json={'deviceId': box, 'pair': False})
            assert r.status_code == 201, r.get_data(as_text=True)
            proc = next(p for p in r.get_json()['processors']
                        if p['id'] == pid)
            ids[f'box{name}'] = proc['slots'][slot]['card']['cvts'][0]['id']
    return ids


def _member(kind, ident, socket):
    return {'kind': kind, 'id': ident, 'socket': socket}


def _served_snakes(client):
    return client.get('/api/processors').get_json()['snakes']


def _project(client):
    return client.get('/api/project').get_json()


def test_one_snake_holds_sockets_from_two_boxes(client):
    """A-5, A-6, B-5, B-6 in ONE snake: POST /api/snakes takes members
    from as many devices as the gesture gathered, the state comes back
    with the snake on the show (not on either box), and its name, length
    and membership are edited through the snake, wherever it is read
    from."""
    ids = _two_cards_with_boxes(client)
    members = [_member('cvt', ids['boxA'], 5), _member('cvt', ids['boxA'], 6),
               _member('cvt', ids['boxB'], 5), _member('cvt', ids['boxB'], 6)]
    r = client.post('/api/snakes', json={'members': members, 'ft': '150'})
    assert r.status_code == 201, r.get_data(as_text=True)
    snakes = r.get_json()['snakes']
    assert len(snakes) == 1
    snake = snakes[0]
    assert snake['name'] == 'SNAKE A' and snake['ft'] == 150
    assert snake['id'].startswith('snk')
    assert snake['members'] == members, snake
    # It hangs on the SHOW - neither box carries a snakes key.
    proc = next(p for p in _project(client)['processors']
                if p['id'] == ids['pid'])
    for slot in proc['slots']:
        card = slot.get('card')
        if not card:
            continue
        assert 'snakes' not in card
        for cvt in card.get('cvts') or []:
            assert 'snakes' not in cvt
    assert len(_project(client)['snakes']) == 1
    # One name, one home run, edited once.
    r = client.put(f'/api/snakes/{snake["id"]}',
                   json={'name': ' 5-6 PAIR ', 'ft': 175, 'connector': 'cat'})
    assert r.status_code == 200, r.get_data(as_text=True)
    again = _served_snakes(client)[0]
    assert (again['name'], again['ft'], again['connector']) \
        == ('5-6 PAIR', 175, 'cat')
    # The bulk membership door: the whole loom at once.
    r = client.put(f'/api/snakes/{snake["id"]}/members',
                   json={'members': members[:2]
                         + [_member('card', ids['cardA'], 9)]})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert [(m['kind'], m['id'], m['socket'])
            for m in _served_snakes(client)[0]['members']] \
        == [('cvt', ids['boxA'], 5), ('cvt', ids['boxA'], 6),
            ('cvt', ids['boxA'], 9)], (
        "a member names the device that DELIVERS its socket, so card A's "
        "9 - which its box carries - is stored as the box's")
    # Unsnaking members takes them out in ONE request, whatever it crosses.
    r = client.post('/api/snakes/loosen',
                    json={'members': [_member('cvt', ids['boxA'], 9),
                                      _member('cvt', ids['boxA'], 6)]})
    assert r.status_code == 200
    assert [(m['id'], m['socket'])
            for m in _served_snakes(client)[0]['members']] \
        == [(ids['boxA'], 5)]
    # The last member goes and the snake goes with it.
    r = client.post('/api/snakes/loosen',
                    json={'members': [_member('cvt', ids['boxA'], 5)]})
    assert r.status_code == 200
    assert _served_snakes(client) == []
    assert 'snakes' not in _project(client)


def test_a_socket_rides_one_snake(client):
    """A socket already in a snake is refused with the reason, wherever
    the second snake tries to take it from - and nothing is stored."""
    ids = _two_cards_with_boxes(client)
    first = [_member('cvt', ids['boxA'], 1), _member('cvt', ids['boxA'], 2)]
    r = client.post('/api/snakes', json={'members': first})
    assert r.status_code == 201, r.get_data(as_text=True)
    r = client.post('/api/snakes', json={
        'members': [_member('cvt', ids['boxA'], 2),
                    _member('cvt', ids['boxB'], 2)]})
    assert r.status_code == 400
    assert 'is already in SNAKE A' in r.get_json()['error']
    assert 'a socket rides one snake' in r.get_json()['error']
    assert len(_served_snakes(client)) == 1, 'nothing stored on a refusal'
    assert [m['socket'] for m in _served_snakes(client)[0]['members']] == [1, 2]
    # The other refusals name their reason too.
    for body, reason in (
            ({'members': []}, 'a snake holds at least one socket'),
            ({'members': [_member('cvt', 'cvt999', 1)]},
             'there is no breakout box cvt999 in this project'),
            ({'members': [_member('cvt', ids['boxB'], 99)]},
             'there is no socket 99 on'),
            ({'members': [_member('cvt', ids['boxB'], 3),
                          _member('cvt', ids['boxB'], 3)]},
             'is named twice'),
            ({'members': [_member('cvt', ids['boxB'], 3)],
              'connector': 'fiber'}, "unknown connector 'fiber'"),
            ({'members': [_member('cvt', ids['boxB'], 3)], 'ft': 'ten'},
             'ft must be a number of feet')):
        r = client.post('/api/snakes', json=body)
        assert r.status_code == 400, (body, r.get_data(as_text=True))
        assert reason in r.get_json()['error'], (body, r.get_json())
    assert len(_served_snakes(client)) == 1


def test_deleting_a_box_drops_its_members_and_an_empty_snake_goes(client):
    """A member goes with the device it names. A snake that also reached
    another box keeps that half; one that held only the deleted box's
    sockets goes with them."""
    ids = _two_cards_with_boxes(client)
    across = client.post('/api/snakes', json={'members': [
        _member('cvt', ids['boxA'], 5), _member('cvt', ids['boxB'], 5)],
        'name': 'ACROSS'}).get_json()['snakes'][-1]
    only_b = client.post('/api/snakes', json={'members': [
        _member('cvt', ids['boxB'], 7)], 'name': 'B ONLY'}).get_json()
    assert len(only_b['snakes']) == 2
    r = client.delete(f'/api/processors/{ids["pid"]}/cvts/{ids["boxB"]}')
    assert r.status_code == 200, r.get_data(as_text=True)
    snakes = _served_snakes(client)
    assert [s['name'] for s in snakes] == ['ACROSS'], snakes
    assert [(m['kind'], m['id'], m['socket']) for m in snakes[0]['members']] \
        == [('cvt', ids['boxA'], 5)], snakes
    assert across['name'] == 'ACROSS'
    # And the card going takes the rest.
    r = client.put(f'/api/processors/{ids["pid"]}/slots/0',
                   json={'deviceId': None})
    assert r.status_code == 200
    assert _served_snakes(client) == []


def test_a_card_snake_moves_to_the_box_that_takes_over_its_sockets(client):
    """THE BUG THIS MODEL WAS BUILT ON. A snake typed on a card, then a
    breakout box hung on that card delivering the same sockets: every
    reader is routed to the box, so before the show snakes the card's
    snake simply vanished - the sockets printed as loose rows. Now the
    member names the device that DELIVERS the socket, and the server
    re-homes it: the snake is the box's to read, and comes back to the
    card when the box goes."""
    ids = _two_cards_with_boxes(client, box=None)
    card = ids['cardA']
    r = client.put(f'/api/processors/{ids["pid"]}/cards/{card}',
                   json={'snakes': [{'ports': [1, 2, 3, 4], 'name': 'SR'}]})
    assert r.status_code == 200, r.get_data(as_text=True)
    snake = _served_snakes(client)[0]
    assert [(m['kind'], m['id']) for m in snake['members']] \
        == [('card', card)] * 4
    r = client.post(f'/api/processors/{ids["pid"]}/cards/{card}/cvts',
                    json={'deviceId': 'novastar-cvt4k-s', 'pair': False})
    assert r.status_code == 201, r.get_data(as_text=True)
    box = next(p for p in r.get_json()['processors']
               if p['id'] == ids['pid'])['slots'][0]['card']['cvts'][0]['id']
    snake = _served_snakes(client)[0]
    assert snake['name'] == 'SR' and snake['ft'] is None
    assert [(m['kind'], m['id'], m['socket']) for m in snake['members']] \
        == [('cvt', box, n) for n in (1, 2, 3, 4)], (
            'the box delivers those sockets now, so the snake is read there')
    # The reading a sheet, a bracket and the pull list all make - the
    # socket's owner is the box, and the box's snake is this one.
    assert catalog.snake_device_index(
        _project(client)['processors'])[1][(card, 1)] == box
    # Deleting the box takes its members with it (the loom hung off the
    # box), and the snake goes with its last member.
    assert client.delete(
        f'/api/processors/{ids["pid"]}/cvts/{box}').status_code == 200
    assert _served_snakes(client) == []


def test_a_re_homed_member_never_takes_a_socket_another_snake_holds(client):
    """Where re-homing would land two snakes on one socket - a card's
    leftover snake meeting the box's own - the one already on the device
    keeps it, and the re-homed member goes. A socket rides one snake, on
    the load funnel as much as on the routes."""
    ids = _two_cards_with_boxes(client, box=None)
    card = ids['cardA']
    project = _project(client)
    proc = next(p for p in project['processors'] if p['id'] == ids['pid'])
    rec = proc['slots'][0]['card']
    rec['snakes'] = [{'id': 'snk90', 'name': 'OLD CARD', 'ft': 150,
                      'ports': [1, 2]}]
    rec['cvts'] = [{'id': 'cvt91', 'deviceId': 'novastar-cvt4k-s',
                    'name': 'BOX', 'mode': None,
                    'snakes': [{'id': 'snk92', 'name': 'BOX SNAKE',
                                'ft': 100, 'ports': [1, 2]}]}]
    r = client.put('/api/project', json=project)
    assert r.status_code == 200, r.get_data(as_text=True)
    snakes = _served_snakes(client)
    assert [s['name'] for s in snakes] == ['BOX SNAKE'], snakes
    assert [(m['kind'], m['id'], m['socket']) for m in snakes[0]['members']] \
        == [('cvt', 'cvt91', 1), ('cvt', 'cvt91', 2)]
    assert card  # the card is still there; only the shadowed snake went


def test_the_migration_folds_per_device_snakes_into_the_show(client):
    """A save with per-device snakes loads as show snakes with the same
    members and the same lengths, and the per-device key is gone.
    Idempotent: restoring the same project twice does not change it."""
    ids = _two_cards_with_boxes(client, box=None)
    project = _project(client)
    proc = next(p for p in project['processors'] if p['id'] == ids['pid'])
    proc['slots'][0]['card']['snakes'] = [
        {'id': 'snk40', 'name': 'A PRIME', 'ft': 150, 'ports': [1, 2, 3, 4]}]
    proc['slots'][1]['card']['snakes'] = [
        {'id': 'snk41', 'name': 'B PRIME', 'ports': [1, 2]},
        {'name': 'B TAIL', 'ft': 75, 'ports': [9]}]
    project.pop('snakes', None)
    r = client.put('/api/project', json=project)
    assert r.status_code == 200, r.get_data(as_text=True)
    snakes = _served_snakes(client)
    assert [(s['id'], s['name'], s['ft']) for s in snakes] == [
        ('snk40', 'A PRIME', 150), ('snk41', 'B PRIME', None),
        (snakes[2]['id'], 'B TAIL', 75)], snakes
    assert [[(m['kind'], m['id'], m['socket']) for m in s['members']]
            for s in snakes] == [
        [('card', ids['cardA'], n) for n in (1, 2, 3, 4)],
        [('card', ids['cardB'], n) for n in (1, 2)],
        [('card', ids['cardB'], 9)]], snakes
    stored = _project(client)
    proc = next(p for p in stored['processors'] if p['id'] == ids['pid'])
    for slot in proc['slots']:
        assert 'snakes' not in (slot.get('card') or {})
    # the counter is above every snake id it just read, so nothing can
    # mint snk40 again
    assert stored['next_processor_seq'] > 41
    again = client.put('/api/project', json=stored)
    assert again.status_code == 200
    assert _project(client)['snakes'] == stored['snakes']


@pytest.mark.skipif(not os.path.exists(SCRATCH_FIXTURE),
                    reason='experts-only-fixture.json smoke fixture not present')
def test_the_smoke_fixture_migrates_to_the_show(client):
    """The user's own show, FROZEN as experts-only-fixture.json (his save
    of 2026-09-07 23:43): four boxes each carrying a four-way snake, and
    - on Card 1 and Card 3 - a snake left on the CARD from before the box
    existed. Those two were already invisible everywhere the sockets are
    read, because the box delivers all 16: the migration re-homes them
    onto the box, finds the box's own snake already on those sockets, and
    drops them. What the paperwork prints does not move - which is what
    test_pull_list's and test_binder's smoke pin."""
    with open(SCRATCH_FIXTURE) as fh:
        project = json.load(fh)
    assert [s['name'] for s in project['processors'][0]['slots'][0]
            ['card']['snakes']] == ['SR Prime'], 'the fixture has the shadow'
    r = client.put('/api/project', json=project)
    assert r.status_code == 200, r.get_data(as_text=True)
    snakes = _served_snakes(client)
    assert [(s['name'], s['ft'], len(s['members'])) for s in snakes] == [
        ('SR A', 150, 4), ('SR B', 100, 4), ('SL A', 100, 4),
        ('SL B', 150, 4)], snakes
    assert {m['kind'] for s in snakes for m in s['members']} == {'cvt'}
    stored = _project(client)
    for proc in stored['processors']:
        for slot in proc['slots']:
            card = slot.get('card')
            if not card:
                continue
            assert 'snakes' not in card
            for cvt in card.get('cvts') or []:
                assert 'snakes' not in cvt
    # the per-socket extensions the boxes carry are untouched - a port
    # cable is a fact about the socket and stays on its device
    box = stored['processors'][0]['slots'][0]['card']['cvts'][0]
    assert box['portCables'] == {'1': {'ft': 10}, '3': {'ft': 25},
                                 '4': {'ft': 25}, '5': {'ft': 100}}


def test_the_catalog_re_homes_without_a_server(client):
    """prune_show_snakes on its own, so the rule is readable in one
    place: a member on a card whose socket a box delivers becomes the
    box's, an unknown device's member goes, and running it twice changes
    nothing."""
    ids = _two_cards_with_boxes(client)
    project = _project(client)
    project['snakes'] = [{
        'id': 'snk50', 'name': 'MIXED', 'members': [
            {'kind': 'card', 'id': ids['cardA'], 'socket': 3},
            {'kind': 'cvt', 'id': 'cvt-gone', 'socket': 1},
            {'kind': 'card', 'id': ids['cardB'], 'socket': 99},
        ]}]
    assert catalog.prune_show_snakes(project) is True
    assert [(m['kind'], m['id'], m['socket'])
            for m in project['snakes'][0]['members']] \
        == [('cvt', ids['boxA'], 3)]
    assert catalog.prune_show_snakes(project) is False


# ── the browser: his example, end to end ─────────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

# One H9: slot 0 card A with a CVT4K-S delivering its 16 sockets, slot 1
# card B the same, B backing A 1:1. WALL 8 × 12 of 200 px cabinets takes
# six ports onto card A - so its primaries are box A's sockets 1-6 and
# their returns are box B's 1-6, the shape his example is drawn on.
SEED_JS = """async () => {
    const proj = await (await fetch('/api/project')).json();
    proj.layers = [];
    proj.groups = [];
    proj.processors = [];
    proj.distros = [];
    proj.snakes = [];
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
    const ids = {procId: pid};
    for (const [slot, name] of [[0, 'A'], [1, 'B']]) {
        st = await put(`/api/processors/${pid}/slots/${slot}`,
                       {deviceId: 'novastar-card-h-16xrj45-2xfiber'});
        const cardId = st.processors[0].slots[slot].card.id;
        await put(`/api/processors/${pid}/cards/${cardId}`, {name});
        st = await post(`/api/processors/${pid}/cards/${cardId}/cvts`,
                        {deviceId: 'novastar-cvt4k-s', pair: false});
        const boxId = st.processors[0].slots[slot].card.cvts[0].id;
        // Named, so the two boxes are told apart on the sheets the way
        // the tray tells them apart: "BOX A" and "BOX B".
        await put(`/api/processors/${pid}/cvts/${boxId}`,
                  {name: `BOX ${name}`});
        ids[`card${name}`] = cardId;
        ids[`box${name}`] = boxId;
    }
    await put(`/api/processors/${pid}`, {redundancy: true});
    await put(`/api/processors/${pid}/cards/${ids.cardA}`,
              {backupCardId: ids.cardB});
    const app = window.app;
    const p1 = await (await fetch('/api/project')).json();
    for (const l of p1.layers) {
        await put(`/api/layer/${l.id}`, {processorType: 'novastar-armor'});
    }
    app.project = await (await fetch('/api/project')).json();
    app.dedupeProjectLayers('snakes_across_setup');
    const wall = app.project.layers[0];
    app.selectLayer(wall);
    await app.refreshProcessors();
    await app._assignmentRequest('/api/port-assignments/place-overflow',
                                 'POST', {layerId: String(wall.id),
                                          cardId: ids.cardA});
    app.renderLayers();
    app.renderHardwareDock();
    app.resetHistory('Snakes Across Seed');
    const scr = app._assignment.screens.find(
        s => s.layerId === String(wall.id));
    ids.id = wall.id;
    ids.ports = scr.ports.map(pt => [pt.number, pt.cardId, pt.port]);
    return ids;
}"""

# The show's snakes as the client holds them, and where history stands.
SHOW_JS = """() => {
    const app = window.app;
    return {
        snakes: app.getShowSnakes().map(s => ({
            id: s.id, name: s.name, ft: s.ft,
            members: s.members.map(m => [m.kind, m.id, m.socket]),
        })),
        action: app.history[app.historyIndex].action,
        index: app.historyIndex,
    };
}"""

# One sheet's snake rows: the cap, the name, and the dim "+ … on …" that
# names the members this sheet cannot show.
SHEET_JS = """([kind, id]) => {
    const sheet = document.querySelector(
        `.hw-dock-cablesheet[data-lrd-cable-sheet="${kind}:${id}"]`);
    if (!sheet) return null;
    return [...sheet.querySelectorAll('tr.hw-dock-cable-snake')].map(tr => ({
        cap: tr.querySelector('.hw-dock-cable-snake-cap').textContent,
        name: tr.querySelector('.hw-dock-cable-name').value,
        away: (tr.querySelector('.hw-dock-cable-snake-away')
            || {}).textContent || '',
        members: (() => {
            const out = [];
            let n = tr.nextElementSibling;
            while (n && n.classList.contains('hw-dock-cable-member')) {
                out.push(n.querySelectorAll('td')[1].textContent);
                n = n.nextElementSibling;
            }
            return out;
        })(),
    }));
}"""

TRAY_JS = """([kind, id]) => {
    const grid = document.querySelector(
        `.hw-dock-grid[data-lrd-snake-owner="${kind}:${id}"]`);
    if (!grid) return null;
    return [...grid.querySelectorAll('.hw-dock-snake')].map(b => ({
        ghost: b.classList.contains('hw-dock-snake-ghost'),
        tag: (b.querySelector('.hw-dock-snake-tag') || {}).textContent || null,
    }));
}"""

PULL_JS = """() => {
    const app = window.app;
    app._circuitTailCache = null;
    const list = app.buildPullList();
    return {
        rows: list.positions.map(p => [p.name, p.rows.map(
            r => [r.type, r.length, r.qty, r.label, r.notes])]),
        hardware: (list.hardware || []).map(
            h => [h.kind, h.name, h.rows.map(r => [r.type, r.length, r.qty])]),
    };
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
    assert [p[0] for p in ids['ports']] == [1, 2, 3, 4, 5, 6], ids
    yield pg, ids
    context.close()


def _sheet_open(page, kind, owner_id, want_open=True):
    up = page.evaluate(
        """([kind, id]) => !!document.querySelector(
            `.hw-dock-cablesheet[data-lrd-cable-sheet="${kind}:${id}"]`)""",
        [kind, owner_id])
    if up != want_open:
        page.locator(f'[data-lrd-field="data-cable-sheet-{owner_id}"]').click()
        page.wait_for_timeout(500)


def test_five_and_six_at_both_ends_are_one_four_way(page):
    """His example, whole. Tick A-5 and A-6 on box A's sheet, tick B-5 and
    B-6 on box B's, press Snake on either: ONE 4-way, ONE 'Snake Ports'
    entry. Both sheets show the SAME row - the same name field, "4-way",
    and the members from the other box named dim beside it - and both
    grids draw its bracket with a "↔". The pull list says the snake ONCE
    (its key is the snake, not the device it was met on) and lands its
    row on the processor it touches. An extension on A-5 and on B-5 takes
    a barrel each. Undo removes the snake whole."""
    pg, ids = page
    _sheet_open(pg, 'cvt', ids['boxA'], True)
    _sheet_open(pg, 'cvt', ids['boxB'], True)
    for n in (5, 6):
        pg.locator(
            f'[data-lrd-field="data-snake-tick-{ids["boxA"]}-{n}"]').check()
        pg.locator(
            f'[data-lrd-field="data-snake-tick-{ids["boxB"]}-{n}"]').check()
    index = pg.evaluate(SHOW_JS)['index']
    pg.locator(f'[data-lrd-field="data-cable-snake-{ids["boxA"]}"]').click()
    pg.wait_for_timeout(1200)
    show = pg.evaluate(SHOW_JS)
    assert show['action'] == 'Snake Ports' and show['index'] == index + 1, show
    assert len(show['snakes']) == 1, show
    snake = show['snakes'][0]
    assert snake['members'] == [['cvt', ids['boxA'], 5], ['cvt', ids['boxA'], 6],
                                ['cvt', ids['boxB'], 5], ['cvt', ids['boxB'], 6]], \
        snake
    assert snake['name'] == 'SNAKE A', snake
    # Both sheets carry the same row, each naming the other box's half.
    rows_a = pg.evaluate(SHEET_JS, ['cvt', ids['boxA']])
    rows_b = pg.evaluate(SHEET_JS, ['cvt', ids['boxB']])
    assert len(rows_a) == 1 and len(rows_b) == 1, (rows_a, rows_b)
    assert rows_a[0]['cap'] == 'SNAKE A · 4-way', rows_a
    assert rows_b[0]['cap'] == 'SNAKE A · 4-way', rows_b
    assert rows_a[0]['name'] == rows_b[0]['name'] == 'SNAKE A'
    # the members it cannot show, named - the box once, its sockets by
    # the part of their label that is not the box's own name
    assert rows_a[0]['away'] == ' + 5, 6 on BOX B', rows_a
    assert rows_b[0]['away'] == ' + 5, 6 on BOX A', rows_b
    assert [m.split(' · ')[0] for m in rows_a[0]['members']] == ['5', '6'], rows_a
    assert [m.split(' · ')[0] for m in rows_b[0]['members']] == ['5', '6'], rows_b
    # One name, wherever it is typed: rename on B's sheet, A's row follows.
    name_b = pg.locator(
        f'[data-lrd-field="data-snake-name-{ids["boxB"]}-{snake["id"]}"]')
    name_b.fill('5-6 PAIR')
    name_b.press('Tab')
    pg.wait_for_timeout(1000)
    assert pg.evaluate(SHEET_JS, ['cvt', ids['boxA']])[0]['name'] == '5-6 PAIR'
    assert pg.evaluate(SHOW_JS)['action'] == 'Rename Snake'
    # A home run typed once, read on both.
    ft = pg.locator(
        f'[data-lrd-field="data-snake-ft-{ids["boxA"]}-{snake["id"]}"]')
    ft.fill('150')
    ft.press('Tab')
    pg.wait_for_timeout(1000)
    assert pg.evaluate(SHOW_JS)['snakes'][0]['ft'] == 150
    # The extensions: A-5 and B-5, one barrel each.
    for box in ('boxA', 'boxB'):
        cell = pg.locator(
            f'[data-lrd-field="data-cable-ft-{ids[box]}-5"]')
        cell.fill('25')
        cell.press('Tab')
        pg.wait_for_timeout(900)
    # The brackets: one per unit, the whole snake's ways, and the "↔".
    _sheet_open(pg, 'cvt', ids['boxA'], False)
    _sheet_open(pg, 'cvt', ids['boxB'], False)
    pg.wait_for_timeout(500)
    tags_a = [b['tag'] for b in pg.evaluate(TRAY_JS, ['cvt', ids['boxA']])]
    tags_b = [b['tag'] for b in pg.evaluate(TRAY_JS, ['cvt', ids['boxB']])]
    assert tags_a == ["5-6 PAIR · 4-way · 150' ↔"], tags_a
    assert tags_b == ["5-6 PAIR · 4-way · 150' ↔"], tags_b
    # The pull list: the snake said ONCE, two extensions, two barrels.
    pull = pg.evaluate(PULL_JS)
    rows = [r for _name, rs in pull['rows'] for r in rs]
    snakes = [r for r in rows if r[0] == 'Ether-con Snake']
    assert snakes == [['Ether-con Snake', "150'", 1, '5-6 PAIR', '4-way']], rows
    barrels = [r for r in rows if r[0] == 'Ether-con Barrel']
    assert [r[2] for r in barrels] == [2], barrels
    exts = [r for r in rows if r[0] == 'Ether-con' and 'ext' in r[4]]
    assert [r[1] for r in exts] == ["25'"] and [r[2] for r in exts] == [2], exts
    # and once on the processor's own sheet, whatever it crosses
    hw = [h for h in pull['hardware'] if h[0] == 'processor']
    assert len(hw) == 1, hw
    assert len([r for r in hw[0][2] if r[0] == 'Ether-con Snake']) == 1, hw
    # Undo: the extensions, then the home run, the name, and the snake -
    # whole, in one step, off both boxes at once.
    for _ in range(5):
        pg.evaluate('() => window.app.undo()')
        pg.wait_for_timeout(900)
    show = pg.evaluate(SHOW_JS)
    assert show['snakes'] == [], show
    assert show['index'] == 0, show
