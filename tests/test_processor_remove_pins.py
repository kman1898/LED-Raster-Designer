"""Removing hardware takes the pins that pointed at it.

The owner's beta.3 log: Remove processor on an H9 left all 48 of Screen1's
pins behind, each one reading "pinned to a card that is no longer in this
project", and he clicked Release pin 48 times. A processor delete only let
go of the redundancy links that named its cards; emptying a slot and
swapping the card in it did the same.

Now each of the three drops every pin on the cards that went
(routes_processors._drop_card_pins), the way a box delete on a box-fed
unit drops the pins on its sockets:

* the screen ports read unplaced again, with no pin-card-gone issue left;
* the reply carries a note naming them - "Removed H9: 16 ports of WALL
  are unplaced again" - and the pruned pin state, so the client's undo
  snapshot holds the pins as the server now does;
* undo (the whole-project PUT of the prior snapshot) brings the hardware
  and its pins back together;
* a pin on any other card stays exactly where it was.

Run locally:
    python -m pytest tests/test_processor_remove_pins.py -q
"""

import copy
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import port_assignment as assignment  # noqa: E402

H9 = 'novastar-h9'
CARD16 = 'novastar-card-h-16xrj45-2xfiber'
CARD4F = 'novastar-card-h-4xfiber'


def add_layer(client, name, cols=6, rows=4, x=0):
    resp = client.post('/api/layer/add', json={
        'name': name, 'columns': cols, 'rows': rows,
        'cabinet_width': 500, 'cabinet_height': 500, 'offset_x': x})
    assert resp.status_code in (200, 201), resp.get_data(as_text=True)
    return str(resp.get_json()['id'])


def add_chassis(client, cards):
    resp = client.post('/api/processors', json={'deviceId': H9})
    assert resp.status_code == 201, resp.get_data(as_text=True)
    pid = resp.get_json()['resolved'][-1]['id']
    for i, device_id in enumerate(cards):
        resp = client.put(f'/api/processors/{pid}/slots/{i}',
                          json={'deviceId': device_id})
        assert resp.status_code == 200, resp.get_data(as_text=True)
    proc = next(p for p in resp.get_json()['resolved'] if p['id'] == pid)
    return pid, [s['card']['id'] for s in proc['slots'] if s['card']]


def screens(*pairs):
    return [{'layerId': lid, 'name': name, 'ports': n, 'platform': None}
            for lid, name, n in pairs]


def place(client, lid, cid, sc, first=None, last=None):
    body = {'layerId': lid, 'cardId': cid, 'screens': sc}
    if first is not None:
        body.update(firstPort=first, lastPort=last)
    resp = client.post('/api/port-assignments/place-overflow', json=body)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()['resolution']


def pins(client):
    state = client.get('/api/project').get_json().get(assignment.STATE_KEY)
    return sorted((p['layerId'], p['cardId'], p['port'])
                  for p in (state or {}).get('pins') or [])


def issue_kinds(client, sc):
    resp = client.post('/api/port-assignments/resolve', json={'screens': sc})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return [i['kind'] for i in resp.get_json()['resolution']['issues']]


def _two_cards(client):
    """WALL on card 1's 1-6, SIDE on card 2's 1-4, one H9."""
    wall = add_layer(client, 'WALL')
    side = add_layer(client, 'SIDE', x=4000)
    pid, (c1, c2) = add_chassis(client, [CARD16, CARD16])
    sc = screens((wall, 'WALL', 6), (side, 'SIDE', 4))
    place(client, wall, c1, sc, first=1, last=6)
    place(client, side, c2, sc, first=1, last=4)
    assert len(pins(client)) == 10
    return pid, c1, c2, wall, side, sc


def test_removing_a_processor_drops_its_pins_and_says_so(client):
    wall = add_layer(client, 'WALL')
    pid, (c1,) = add_chassis(client, [CARD16])
    sc = screens((wall, 'WALL', 6))
    place(client, wall, c1, sc, first=1, last=6)
    assert [p[2] for p in pins(client)] == [1, 2, 3, 4, 5, 6]
    before = copy.deepcopy(client.get('/api/project').get_json())

    resp = client.delete(f'/api/processors/{pid}')
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body['note'] == 'Removed H9: 6 ports of WALL are unplaced again'
    assert body['portAssignments']['pins'] == []
    assert pins(client) == [], 'the removed processor left its pins behind'
    assert 'pin-card-gone' not in issue_kinds(client, sc)

    # Undo: the prior snapshot puts the machine and its pins back together.
    resp = client.put('/api/project', json=before)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert [p[2] for p in pins(client)] == [1, 2, 3, 4, 5, 6]
    assert [p['id'] for p in client.get('/api/processors').get_json()
            ['processors']] == [pid]


def test_emptying_a_slot_drops_only_that_cards_pins(client):
    pid, c1, c2, wall, side, sc = _two_cards(client)
    resp = client.put(f'/api/processors/{pid}/slots/0', json={'deviceId': None})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body['note'] == 'Removed Card 1: 6 ports of WALL are unplaced again'
    assert pins(client) == [(side, c2, n) for n in (1, 2, 3, 4)], (
        'the other card lost its pins, or the emptied slot kept its own')
    assert sorted((p['layerId'], p['port'])
                  for p in body['portAssignments']['pins']) == \
        [(side, n) for n in (1, 2, 3, 4)]
    assert 'pin-card-gone' not in issue_kinds(client, sc)


def test_swapping_the_card_in_a_slot_drops_the_old_cards_pins(client):
    pid, c1, c2, wall, side, sc = _two_cards(client)
    resp = client.put(f'/api/processors/{pid}/slots/1',
                      json={'deviceId': CARD4F})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body['note'] == 'Replaced Card 2: 4 ports of SIDE are unplaced again'
    assert pins(client) == [(wall, c1, n) for n in (1, 2, 3, 4, 5, 6)]
    assert 'pin-card-gone' not in issue_kinds(client, sc)


def test_hardware_with_no_pins_says_nothing(client):
    """No pins on the removed card: no note and no pin state in the reply,
    the way an empty box delete answers."""
    add_layer(client, 'WALL')
    pid, _cards = add_chassis(client, [CARD16, CARD16])
    body = client.put(f'/api/processors/{pid}/slots/0',
                      json={'deviceId': None}).get_json()
    assert 'note' not in body and 'portAssignments' not in body
    body = client.delete(f'/api/processors/{pid}').get_json()
    assert 'note' not in body and 'portAssignments' not in body
