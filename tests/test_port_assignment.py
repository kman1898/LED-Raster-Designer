"""Screens onto sending-card ports: numbering, clashes, overflow, overrides.

The rule this whole file is built to prove is that THE APP DETECTS AND OFFERS,
IT NEVER SILENTLY REARRANGES. Looms are made up and labelled off the drawing
days before anything is hung, so a numbering that changes by itself hands back
a drawing that no longer matches the truck. Almost every test below is
therefore in two halves: the problem is FOUND, and the numbering is UNCHANGED
until somebody takes the offer.

The four behaviours, and the reason each is awkward:

* NOTHING LANDS BY ITSELF. A port is on a card only because somebody put it
  there - a card drop fills a screen in order (place-overflow), a port drop
  names a socket (place), and every placement is a pin. An unplaced port
  is "not attached" and reported, never dealt out. Auto-numbering is
  retired (user ruling, 2026-09-03: "we have no way to turn on or off auto.
  but honestly auto should be removed now.").
* A CLASH IS REPORTED, NOT FIXED. Both claimants keep the port. Bumping the
  loser is the silent renumber.
* A SCREEN'S PORTS NEVER SPAN TWO CARDS UNASKED. Seventeen ports dropped on
  a sixteen-port card leaves one unattached and says so; putting it on
  another card is a patching decision with a physical consequence and
  belongs to a person.
* A PIN HOLDS. Nothing re-packs around a release, nothing moves when a
  neighbour moves, and a release leaves the port unattached until it is
  placed again.

The reporting surface moved with the consolidation round: the retired Port
Numbering panel's issue boxes are rows on the hardware dock's issues strip
(#hw-dock-issues) and the per-card usage foot is the card headers'
used/capacity glance. The numbering itself never left the server, which is
why almost everything here drives the API. A project saved under the old
rule is frozen into pins once on load (section 1b) so its drawing does not
change; PUT /api/port-assignments, the old auto switch, is 410 Gone.

Values are asserted as they come BACK from the server, never as they were
sent - this codebase drops unlisted fields silently in two separate places and
a test that only checks its own request body passes straight through that.

Run locally:
    python3 -m pytest tests/test_port_assignment.py -q
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import port_assignment as assignment  # noqa: E402
import processor_catalog as catalog  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(flask_project_guard):
    """Leave the shared server project the way this module found it.

    Every test here builds its own project through the `client` fixture,
    which swaps the module-global the LIVE e2e server also serves - so the
    last test's leftovers (a processor tree, a set of pins) would otherwise
    become the next browser module's starting state. The guard is the
    documented idiom for exactly this (see conftest)."""

def add_processor(client, device_id):
    resp = client.post('/api/processors', json={'deviceId': device_id})
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


def set_card(client, proc_id, slot, device_id):
    resp = client.put(f'/api/processors/{proc_id}/slots/{slot}',
                      json={'deviceId': device_id})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()


def card_ids(state):
    """Cards in the order the dock draws them, which is the order a block
    move searches them - processor by processor, slot 1 downward."""
    out = []
    for proc in state['resolved']:
        for slot in proc['slots']:
            if slot['card']:
                out.append(slot['card']['id'])
    return out


def screens(*pairs):
    """(name, ports) in the order they are to be allocated."""
    return [{'layerId': name, 'name': name, 'ports': count}
            for name, count in pairs]


def resolve(client, *pairs):
    resp = client.post('/api/port-assignments/resolve',
                       json={'screens': screens(*pairs)})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()['resolution']


def by_name(resolution, name):
    return next(s for s in resolution['screens'] if s['layerId'] == name)


def place(client, layer_id, index, card_id, port, sc, confirm=False):
    """One port of one screen onto one card port - the request a hand
    placement sends, from either end of the cable (the dock's drop is the
    gesture that sends it in the app)."""
    body = {'layerId': layer_id, 'index': index, 'cardId': card_id,
            'port': port, 'screens': sc}
    if confirm:
        body['confirm'] = True
    return client.post('/api/port-assignments/place', json=body)


def attach(client, layer_id, card_id, sc, first=None, last=None):
    """Land one screen's unattached ports on a card, in order - the request
    a card or box drop sends (place-overflow), and since auto-numbering was
    retired (2026-09-03) the one way a whole screen gets onto a card. Every
    port it lands is a pin. Returns the resolution that came back."""
    body = {'layerId': layer_id, 'cardId': card_id, 'screens': sc}
    if first is not None:
        body['firstPort'] = first
    if last is not None:
        body['lastPort'] = last
    resp = client.post('/api/port-assignments/place-overflow', json=body)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()['resolution']


def stored_state(client):
    return client.get('/api/project').get_json().get(assignment.STATE_KEY)


# What every project carries from birth (app._build_initial_project) and
# what a legacy file is stamped with once it has been through retire_auto:
# no pins, auto off for good, and the mark that says so.
STAMP = {'auto': False, 'autoRetired': True, 'pins': []}


def spots(resolution, name):
    """(cardId, port) for each of one screen's own ports, in its own order.
    None where a port has nowhere to go."""
    return [(p['cardId'], p['port']) for p in by_name(resolution, name)['ports']]


def numbers(resolution, name):
    return [p['port'] for p in by_name(resolution, name)['ports']]


def sources(resolution, name):
    return [p['source'] for p in by_name(resolution, name)['ports']]


def kinds(resolution):
    return [i['kind'] for i in resolution['issues']]


def issue(resolution, kind):
    found = [i for i in resolution['issues'] if i['kind'] == kind]
    assert found, f'no {kind} issue in {kinds(resolution)}'
    return found[0]


@pytest.fixture()
def one_card(client):
    """One 16-port RJ45 sending card in an H9. Sixteen is the number that makes
    a 17-port wall a real problem rather than a contrived one."""
    state = add_processor(client, 'novastar-h9')
    pid = state['resolved'][0]['id']
    state = set_card(client, pid, 0, 'novastar-card-h-16xrj45-2xfiber')
    return client, pid, card_ids(state)[0]


@pytest.fixture()
def two_cards(client):
    state = add_processor(client, 'novastar-h9')
    pid = state['resolved'][0]['id']
    set_card(client, pid, 0, 'novastar-card-h-16xrj45-2xfiber')
    state = set_card(client, pid, 1, 'novastar-card-h-16xrj45-2xfiber')
    ids = card_ids(state)
    return client, pid, ids[0], ids[1]


# ── 1. Nothing lands by itself ────────────────────────────────────────────
#
# Auto-numbering retired (user ruling, 2026-09-03). A screen's ports are on
# a card because somebody dropped the screen on it - place-overflow, the
# request a card drop sends - and the fill packs them in order from the
# card's lowest free socket. Until then they are not attached, and the
# resolution says so.

def test_a_card_drop_fills_a_screen_in_order_and_the_next_follows_on(one_card):
    """The drop's arithmetic: a screen needing six ports takes 1-6 on the
    card it was dropped on, and the next screen dropped there starts at 7.
    Every port it lands is a pin - there is no other way onto a card."""
    client, _pid, card = one_card
    sc = screens(('Main', 6), ('Side', 4), ('Upstage', 3))
    attach(client, 'Main', card, sc)
    attach(client, 'Side', card, sc)
    res = attach(client, 'Upstage', card, sc)

    assert numbers(res, 'Main') == [1, 2, 3, 4, 5, 6]
    assert numbers(res, 'Side') == [7, 8, 9, 10]
    assert numbers(res, 'Upstage') == [11, 12, 13]
    assert all(c == card for c, _p in spots(res, 'Side'))
    assert sources(res, 'Main') == ['pin'] * 6
    assert res['issues'] == [], res['issues']


def test_nothing_lands_until_somebody_places_it(one_card):
    """A card with sixteen free sockets and a screen needing three: the
    screen stays OFF the card until it is dropped there. The resolution
    reports the three as not attached, and merely reading it changes
    nothing on the project - the state is the birth stamp, untouched."""
    client, _pid, _card = one_card
    res = resolve(client, ('Main', 3))
    assert numbers(res, 'Main') == [None, None, None]
    assert sources(res, 'Main') == [None] * 3
    assert issue(res, 'overflow')['ports'] == [1, 2, 3]
    assert 'auto' not in res, 'the resolution still carries an auto flag'
    assert stored_state(client) == STAMP


def test_the_auto_switch_is_gone_for_good(two_cards):
    """PUT /api/port-assignments was the auto switch. It answers 410 in
    both directions and changes nothing: a pinned port stays pinned, the
    screen's other ports stay unattached, and no auto-off row (or offer to
    turn it back on) exists to be raised."""
    client, _pid, card_a, _card_b = two_cards
    resp = client.post('/api/port-assignments/pin', json={
        'layerId': 'Main', 'index': 1, 'cardId': card_a, 'port': 9,
        'screens': screens(('Main', 3)),
    })
    assert resp.status_code == 200
    before = stored_state(client)
    for flag in (False, True):
        resp = client.put('/api/port-assignments', json={'auto': flag})
        assert resp.status_code == 410, resp.get_data(as_text=True)
        assert 'retired' in resp.get_json()['error']
    assert stored_state(client) == before
    res = resolve(client, ('Main', 3))
    assert numbers(res, 'Main') == [None, 9, None]
    assert 'auto-off' not in kinds(res)
    assert not any(o['action'] == 'auto-on'
                   for i in res['issues'] for o in i['offers'])


def test_a_screen_lands_on_the_card_it_was_dropped_on_and_nowhere_else(two_cards):
    """Fourteen ports fill card A, and a six-port screen dropped on card A
    takes the two sockets left and STOPS - the fill never walks on to card
    B by itself. The four that did not fit are reported, and the second
    card takes them only when the screen is dropped there too."""
    client, _pid, card_a, card_b = two_cards
    sc = screens(('Main', 14), ('Side', 6))
    attach(client, 'Main', card_a, sc)
    resp = client.post('/api/port-assignments/place-overflow',
                       json={'layerId': 'Side', 'cardId': card_a, 'screens': sc})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert 'took 2 of 6 ports. 4 still have nowhere to go.' in \
        resp.get_json()['moved']['note']
    res = resp.get_json()['resolution']
    assert all(c == card_a for c, _p in spots(res, 'Main'))
    assert spots(res, 'Side') == [(card_a, 15), (card_a, 16)] + [(None, None)] * 4
    assert issue(res, 'overflow')['ports'] == [3, 4, 5, 6]
    assert not any(c == card_b for s in res['screens']
                   for c, _p in [(p['cardId'], p['port']) for p in s['ports']])

    res = attach(client, 'Side', card_b, sc)
    assert spots(res, 'Side')[2:] == [(card_b, n) for n in range(1, 5)]
    assert by_name(res, 'Side')['split'] is True
    assert res['issues'] == [], res['issues']


def test_a_cvt_gives_a_copy_opt_card_no_extra_ports_to_hand_out(one_card):
    """The 16xRJ45+2xfiber's OPTs copy Ethernet 1-8 and 9-16, so a breakout box
    on one is another place to plug into ports that already exist. If the model
    counted it as eight more, this card would offer 24 ports and a 20-cabinet
    wall would look like it fitted. It does not, and it must keep not fitting
    with both boxes hung on it."""
    client, pid, card = one_card
    sc = screens(('Main', 17))
    attach(client, 'Main', card, sc)
    for boxes in (0, 1, 2):
        res = resolve(client, ('Main', 17))
        assert res['cards'][0]['capacity'] == 16, (
            f'{boxes} CVTs made a 16-port card offer '
            f'{res["cards"][0]["capacity"]} ports')
        assert by_name(res, 'Main')['unplaced'] == [16], (
            'the seventeenth port found room that does not exist')
        assert 'overflow' in kinds(res)
        # And a second drop finds the card as full as the first left it.
        resp = client.post('/api/port-assignments/place-overflow',
                           json={'layerId': 'Main', 'cardId': card,
                                 'screens': sc})
        assert resp.status_code == 409, resp.get_data(as_text=True)
        client.post(f'/api/processors/{pid}/cards/{card}/cvts',
                    json={'deviceId': 'novastar-cvt10'})


def test_boxes_hung_on_trunks_that_do_not_exist_hand_out_no_ports(client):
    """The app refuses to ADD a box with no OPT left (the card gear's box
    picker), but a project can still
    arrive carrying one - a file saved before that rule, or hand-edited. The
    read path has to stay safe on its own, because the number it produces is
    what a wall gets packed onto: 40 cabinets assigned to 48 ports of a 32-port
    machine is sixteen with nothing to plug into on the day.

    Allocation is capped by the card's real ceiling, never by what was drawn."""
    state = add_processor(client, 'novastar-h9')
    pid = state['resolved'][0]['id']
    state = set_card(client, pid, 0, 'novastar-card-h-4xfiber')
    card = card_ids(state)[0]
    for _ in range(2):
        assert client.post(f'/api/processors/{pid}/cards/{card}/cvts',
                           json={'deviceId': 'novastar-cvt4k-s'}
                           ).status_code == 201

    # Six OPTs into four, arriving the only way it still can.
    project = client.get('/api/project').get_json()
    boxes = project['processors'][0]['slots'][0]['card']['cvts']
    boxes.append({'id': 'cvtX', 'deviceId': 'novastar-cvt4k-s', 'name': '',
                  'portLabelTemplate': '{name}-#', 'mode': 'default'})
    assert client.put('/api/project', json=project).status_code == 200

    drawn = client.get('/api/processors').get_json()['resolved'][0]
    card = drawn['slots'][0]['card']
    assert card['trunksUsed'] == 6 and card['trunks'] == 4
    assert card['over'] is True, 'the over-subscribed drawing stopped showing'

    res = attach(client, 'Main', card['id'], screens(('Main', 40)))
    assert res['cards'][0]['capacity'] == 32, (
        'boxes on trunks that do not exist became assignable ports')
    assert numbers(res, 'Main')[:32] == list(range(1, 33))
    assert by_name(res, 'Main')['unplaced'] == list(range(32, 40))
    assert 'overflow' in kinds(res)


def test_a_card_whose_boxes_cannot_reach_its_ceiling_says_so_here_too(client):
    """Two CVT4K-S boxes on an enhanced H_4xfiber use all four OPTs and deliver
    32 of its 40. Assignment still plans against the card's 40 - which box
    delivers a port is a patching decision and can still change - but the eight
    that no box will hand out have to be said out loud on the dock strip that
    is handing ports to walls."""
    state = add_processor(client, 'novastar-h9')
    pid = state['resolved'][0]['id']
    state = set_card(client, pid, 0, 'novastar-card-h-4xfiber-enhanced')
    card = card_ids(state)[0]
    for _ in range(2):
        assert client.post(f'/api/processors/{pid}/cards/{card}/cvts',
                           json={'deviceId': 'novastar-cvt4k-s'}
                           ).status_code == 201

    res = attach(client, 'Main', card, screens(('Main', 40)))
    assert res['cards'][0]['capacity'] == 40
    assert by_name(res, 'Main')['unplaced'] == []
    short = issue(res, 'card-short-of-its-ceiling')
    assert short['delivered'] == 32 and short['capacity'] == 40
    assert 'CVT10' in short['message']


def test_a_half_patched_card_is_not_flagged_on_the_dock_strip(client):
    """One box on a four-OPT card is a card someone has not finished patching,
    not a shortfall. Nagging about it would train people to ignore the message
    that matters."""
    state = add_processor(client, 'novastar-h9')
    pid = state['resolved'][0]['id']
    state = set_card(client, pid, 0, 'novastar-card-h-4xfiber-enhanced')
    card = card_ids(state)[0]
    client.post(f'/api/processors/{pid}/cards/{card}/cvts',
                json={'deviceId': 'novastar-cvt10'})
    res = resolve(client, ('Main', 10))
    assert 'card-short-of-its-ceiling' not in kinds(res), res['issues']


def test_ports_taken_out_at_a_box_carry_that_boxs_label(one_card):
    """Which delivery a port comes out of is what a tech reads a number off, so
    an assigned port takes the box's name once there is a box on that trunk -
    and the ones still on the card's own copper keep the card's."""
    client, pid, card = one_card
    client.put(f'/api/processors/{pid}/cards/{card}', json={'name': 'SR'})
    resp = client.post(f'/api/processors/{pid}/cards/{card}/cvts',
                       json={'deviceId': 'novastar-cvt10'})
    cvt_id = resp.get_json()['resolved'][0]['slots'][0]['card']['cvts'][0]['id']
    client.put(f'/api/processors/{pid}/cvts/{cvt_id}', json={'name': 'CVT-A'})

    res = attach(client, 'Main', card, screens(('Main', 10)))
    labels = [p['label'] for p in by_name(res, 'Main')['ports']]
    assert labels[:3] == ['CVT-A-1', 'CVT-A-2', 'CVT-A-3']
    assert labels[8:] == ['SR-9', 'SR-10'], (
        'ports past the box should still read off the card')
    assert numbers(res, 'Main') == list(range(1, 11)), (
        'the box changed the numbering as well as the label')


def test_a_card_with_no_settled_port_count_takes_no_whole_card_fill(client):
    """The SQ200 publishes connectors and no port count. Filling onto a
    guessed ceiling would silently cap a wall, which is the failure the
    catalog exists to prevent, so a card drop is refused and the strip row
    says the ports can still be placed one at a time (section 3b proves
    that path)."""
    state = add_processor(client, 'brompton-sq200')
    card = card_ids(state)[0]
    resp = client.post('/api/port-assignments/place-overflow',
                       json={'layerId': 'Main', 'cardId': card,
                             'screens': screens(('Main', 4))})
    assert resp.status_code == 409, resp.get_data(as_text=True)
    assert 'no free ports' in resp.get_json()['error']
    res = resolve(client, ('Main', 4))
    assert numbers(res, 'Main') == [None, None, None, None]
    assert 'capacity-unknown' in kinds(res)
    assert issue(res, 'capacity-unknown')['reason']
    assert 'one at a time' in issue(res, 'capacity-unknown')['message']
    assert 'auto' not in issue(res, 'capacity-unknown')['message'].lower()


# ── 1b. A pre-ruling file is frozen into pins, once ───────────────────────
#
# A project saved while auto-numbering still ran was DRAWN with its ports
# dealt out, and looms were cut to that drawing. Retiring auto must not
# blank it: on load, every port the old rule dealt becomes a pin at that
# exact socket (port_assignment.retire_auto), the state is stamped
# autoRetired, and the freeze never runs again. The port counts that decide
# where those ports were live on the client, so the freeze happens on the
# first request that carries them - the resolve the client fires after a
# load - and the project funnel (PUT /api/project) settles only the cases
# it can without counts. A project born in this version carries the stamp
# from birth and never goes near the freeze.

def add_screen(client, name, columns=4, rows=1):
    """A real screen layer, so the migration's this-project check has a
    layer id and name to match the sent screens against."""
    resp = client.post('/api/layer/add', json={
        'name': name, 'columns': columns, 'rows': rows,
        'cabinet_width': 128, 'cabinet_height': 128})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return str(resp.get_json()['id'])


def make_legacy(client, state):
    """Round-trip the project through the funnel carrying a pre-ruling
    state (or none), the way a saved file arrives. Returns the stored
    state after the funnel has had its say."""
    project = client.get('/api/project').get_json()
    if state is None:
        project.pop(assignment.STATE_KEY, None)
    else:
        project[assignment.STATE_KEY] = state
    assert client.put('/api/project', json=project).status_code == 200
    return stored_state(client)


def lscreens(*pairs):
    """(layerId, name, ports) as the client sends them after a load."""
    return [{'layerId': lid, 'name': name, 'ports': count}
            for lid, name, count in pairs]


def test_a_legacy_file_is_frozen_into_pins_on_its_first_resolve(one_card):
    """The user's own H9 show: every port dealt by auto, zero pins. Loaded
    now, the funnel cannot place anything (no port counts), the first
    resolve - which carries them - pins Main on 1-6 and Side on 7-10
    exactly where the old rule drew them, says so with `migrated`, and
    stamps the state so the drawing is frozen from here on."""
    client, _pid, card = one_card
    main, side = add_screen(client, 'Main'), add_screen(client, 'Side')
    assert make_legacy(client, None) is None, (
        'the funnel stamped a project whose ports it could not place')

    sc = lscreens((main, 'Main', 6), (side, 'Side', 4))
    resp = client.post('/api/port-assignments/resolve', json={'screens': sc})
    assert resp.status_code == 200
    assert resp.get_json().get('migrated') is True
    res = resp.get_json()['resolution']
    assert spots(res, main) == [(card, n) for n in range(1, 7)]
    assert spots(res, side) == [(card, n) for n in range(7, 11)]
    assert sources(res, main) == ['pin'] * 6
    stored = stored_state(client)
    assert stored['auto'] is False and stored['autoRetired'] is True
    assert len(stored['pins']) == 10
    assert res['issues'] == [], res['issues']


def test_the_freeze_runs_once_and_never_again(one_card):
    """Idempotent by the stamp: a second resolve, another trip through the
    funnel, and a screen that has since grown a port all leave the frozen
    pins exactly as they were. The new port is simply not attached - the
    old rule would have dealt it out; the new one waits for a drop."""
    client, _pid, card = one_card
    main = add_screen(client, 'Main')
    make_legacy(client, {'auto': True, 'pins': []})
    sc = lscreens((main, 'Main', 3))
    first = client.post('/api/port-assignments/resolve', json={'screens': sc})
    assert first.get_json().get('migrated') is True
    frozen = stored_state(client)

    again = client.post('/api/port-assignments/resolve', json={'screens': sc})
    assert 'migrated' not in again.get_json()
    assert stored_state(client) == frozen
    project = client.get('/api/project').get_json()
    assert client.put('/api/project', json=project).status_code == 200
    assert stored_state(client) == frozen

    grown = client.post('/api/port-assignments/resolve',
                        json={'screens': lscreens((main, 'Main', 4))})
    assert 'migrated' not in grown.get_json()
    res = grown.get_json()['resolution']
    assert spots(res, main) == [(card, 1), (card, 2), (card, 3), (None, None)]
    assert stored_state(client) == frozen


def test_the_freeze_keeps_pins_clashes_and_overflow_as_drawn(two_cards):
    """The awkward legacy shapes, each frozen to what the old rule drew.
    Two pins on one socket stay a clash (the fill never lands on a claimed
    socket, so it adds none). A seventeen-port wall no card could hold
    whole went, under the old rule, onto the FIRST card with any free
    socket - card A's thirteen, around the pins - and the four that did
    not fit stayed unattached; the freeze pins exactly that, never tidying
    the wall onto card B where it would fit better. Card B stays empty."""
    client, _pid, card_a, card_b = two_cards
    main, side = add_screen(client, 'Main'), add_screen(client, 'Side')
    wall = add_screen(client, 'Wall')
    make_legacy(client, {'auto': True, 'pins': [
        {'layerId': main, 'index': 0, 'cardId': card_a, 'port': 5},
        {'layerId': side, 'index': 0, 'cardId': card_a, 'port': 5},
    ]})
    sc = lscreens((main, 'Main', 2), (side, 'Side', 2), (wall, 'Wall', 17))
    resp = client.post('/api/port-assignments/resolve', json={'screens': sc})
    assert resp.get_json().get('migrated') is True
    res = resp.get_json()['resolution']
    assert spots(res, main) == [(card_a, 5), (card_a, 1)]
    assert spots(res, side) == [(card_a, 5), (card_a, 2)]
    assert issue(res, 'overlap')['port'] == 5
    assert spots(res, wall)[:13] == \
        [(card_a, n) for n in [3, 4] + list(range(6, 17))]
    assert spots(res, wall)[13:] == [(None, None)] * 4
    assert issue(res, 'overflow')['ports'] == [14, 15, 16, 17]
    assert next(c for c in res['cards'] if c['cardId'] == card_b)['used'] == 0
    assert all(s == 'pin' for name in (main, side) for s in sources(res, name))
    assert len(stored_state(client)['pins']) == 17


def test_the_freeze_pins_mains_and_the_backup_mirrors_follow(client):
    """A sequential card's returns are derived from the mains on every
    resolve, never stored - so the freeze pins the odd mains the old rule
    dealt (1, 3) and the even sockets go on mirroring them, with nothing
    extra in the file."""
    _pid, card = sequential_card(client)
    wall = add_screen(client, 'Wall')
    make_legacy(client, None)
    resp = client.post('/api/port-assignments/resolve',
                       json={'screens': lscreens((wall, 'Wall', 2))})
    assert resp.get_json().get('migrated') is True
    res = resp.get_json()['resolution']
    assert spots(res, wall) == [(card, 1), (card, 3)]
    assert returns_on(res, card, 2) == \
        [('Wall', 1, 'return', 'return', 1, 'SR-1')]
    assert [(p['index'], p['port']) for p in stored_state(client)['pins']] == \
        [(0, 1), (1, 3)]


def test_a_legacy_file_with_auto_off_is_stamped_and_nothing_is_added(one_card):
    """Auto off in the file means nothing was ever dealt: the funnel stamps
    the state where it stands - its pins kept, no counts needed - and the
    resolve that follows has nothing to freeze."""
    client, _pid, card = one_card
    main = add_screen(client, 'Main')
    stored = make_legacy(client, {'auto': False, 'pins': [
        {'layerId': main, 'index': 1, 'cardId': card, 'port': 9}]})
    assert stored == {'auto': False, 'autoRetired': True, 'pins': [
        {'layerId': main, 'index': 1, 'cardId': card, 'port': 9}]}
    resp = client.post('/api/port-assignments/resolve',
                       json={'screens': lscreens((main, 'Main', 3))})
    assert 'migrated' not in resp.get_json()
    assert spots(resp.get_json()['resolution'], main) == \
        [(None, None), (card, 9), (None, None)]


def test_a_legacy_file_with_no_hardware_is_stamped_at_the_funnel(client):
    """No card with a settled count means the old rule drew nothing, so the
    funnel can settle it alone: the stamp, no pins. Same for a file with
    hardware but no screen layer."""
    add_screen(client, 'Main')
    assert make_legacy(client, None) == STAMP
    assert make_legacy(client, {'auto': True, 'pins': []}) == STAMP
    add_processor(client, 'brompton-sq200')  # connectors, no settled count
    assert make_legacy(client, None) == STAMP


def test_the_freeze_waits_for_this_projects_own_screens(one_card):
    """The counts arrive from the client, and a resolve fired for the
    project that was open a moment ago must not freeze ITS counts onto the
    file just loaded - layer ids collide across projects, so the sent
    screens have to carry this project's layer names. A list that does not
    match is left alone (no freeze, no stamp, no `migrated`); an empty one
    too; the matching list that follows does the job."""
    client, _pid, card = one_card
    main = add_screen(client, 'Main')
    make_legacy(client, None)
    for stale in (lscreens((main, 'Old Show Wall', 6)),
                  lscreens(('99', 'Main', 6)), []):
        resp = client.post('/api/port-assignments/resolve',
                           json={'screens': stale})
        assert resp.status_code == 200
        assert 'migrated' not in resp.get_json(), stale
        assert stored_state(client) is None, stale
    resp = client.post('/api/port-assignments/resolve',
                       json={'screens': lscreens((main, 'Main', 2))})
    assert resp.get_json().get('migrated') is True
    assert spots(resp.get_json()['resolution'], main) == [(card, 1), (card, 2)]


def test_an_edit_freezes_first_so_it_lands_on_the_frozen_drawing(one_card):
    """A legacy file's first request need not be a resolve: a place lands
    on the drawing as frozen - Main on 1-2 and Side on 3, every one a pin
    - so the old auto tenant of socket 1 is a pin the refusal can name,
    the freeze is stored even though the edit was refused, and the edit
    that follows moves Side's one port and nothing else."""
    client, _pid, card = one_card
    main, side = add_screen(client, 'Main'), add_screen(client, 'Side')
    make_legacy(client, None)
    sc = lscreens((main, 'Main', 2), (side, 'Side', 1))
    resp = place(client, side, 0, card, 1, sc)
    assert resp.status_code == 409, 'the freeze did not run before the edit'
    assert 'Main port 1' in resp.get_json()['error']
    stored = stored_state(client)
    assert stored['autoRetired'] is True
    assert [(p['layerId'], p['port']) for p in stored['pins']] == \
        [(main, 1), (main, 2), (side, 3)]
    resp = place(client, side, 0, card, 5, sc)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    res = resp.get_json()['resolution']
    assert spots(res, side) == [(card, 5)]
    assert spots(res, main) == [(card, 1), (card, 2)]
    assert resp.get_json()['moved']['from'] == {'cardId': card, 'port': 3}
    assert len(stored_state(client)['pins']) == 3


def test_a_project_born_here_never_meets_the_freeze(one_card):
    """The other side of the stamp: a fresh project carries it from birth,
    so an undo snapshot of it going through the funnel with hardware and
    screens is NOT mistaken for a legacy file - nothing is pinned that
    nobody placed, before or after the round trip."""
    client, _pid, _card = one_card
    main = add_screen(client, 'Main')
    assert stored_state(client) == STAMP
    project = client.get('/api/project').get_json()
    assert client.put('/api/project', json=project).status_code == 200
    assert stored_state(client) == STAMP
    resp = client.post('/api/port-assignments/resolve',
                       json={'screens': lscreens((main, 'Main', 3))})
    assert 'migrated' not in resp.get_json()
    assert spots(resp.get_json()['resolution'], main) == [(None, None)] * 3
    assert stored_state(client) == STAMP


# ── 2. A clash is found, and left alone ───────────────────────────────────

def test_two_screens_on_one_port_are_reported_and_neither_is_moved(one_card):
    """Both claimants keep the port. By the time a numbering is wrong the loom
    is usually made up to it, so bumping the loser would hand back a drawing
    that no longer matches the cable."""
    client, _pid, card = one_card
    for layer in ('Main', 'Side'):
        resp = client.post('/api/port-assignments/pin', json={
            'layerId': layer, 'index': 0, 'cardId': card, 'port': 5,
            'screens': screens(('Main', 2), ('Side', 2)),
        })
        assert resp.status_code == 200, resp.get_data(as_text=True)

    res = resolve(client, ('Main', 2), ('Side', 2))
    clash = issue(res, 'overlap')
    assert clash['port'] == 5 and clash['cardId'] == card
    assert sorted(clash['layerIds']) == ['Main', 'Side']
    assert 'Main' in clash['message'] and 'Side' in clash['message']

    # Neither was renumbered out of the way, and both draw as clashing.
    assert numbers(res, 'Main')[0] == 5
    assert numbers(res, 'Side')[0] == 5
    assert by_name(res, 'Main')['ports'][0]['overlap'] is True
    assert by_name(res, 'Side')['ports'][0]['overlap'] is True


def test_three_screens_on_one_port_reads_as_a_sentence(one_card):
    """Rarer than two, and it happens. "A and B and C both claim" is the kind
    of sentence that makes someone stop trusting the rest of the message."""
    client, _pid, card = one_card
    sc = screens(('Main', 1), ('Side', 1), ('Upstage', 1))
    for layer in ('Main', 'Side', 'Upstage'):
        client.post('/api/port-assignments/pin', json={
            'layerId': layer, 'index': 0, 'cardId': card, 'port': 7,
            'screens': sc})
    clash = issue(resolve(client, ('Main', 1), ('Side', 1), ('Upstage', 1)),
                  'overlap')
    assert clash['message'].startswith('Main, Side and Upstage all claim '
                                       'port 7'), clash['message']
    assert len(clash['offers']) == 3


def test_the_clash_comes_with_an_offer_for_each_screen_on_it(one_card):
    """Detect and OFFER. The offer is a block move per screen and never a
    single port, because a screen is one cable run."""
    client, _pid, card = one_card
    for layer in ('Main', 'Side'):
        client.post('/api/port-assignments/pin', json={
            'layerId': layer, 'index': 0, 'cardId': card, 'port': 5,
            'screens': screens(('Main', 2), ('Side', 2)),
        })
    offers = issue(resolve(client, ('Main', 2), ('Side', 2)), 'overlap')['offers']
    assert {o['action'] for o in offers} == {'move-block'}
    assert sorted(o['layerId'] for o in offers) == ['Main', 'Side']


def test_card_drops_alone_never_produce_a_clash(two_cards):
    """Two screens can only share a socket if somebody NAMED that socket
    (a port drop, confirmed). A card drop hands out free sockets only, so
    five screens dropped across two cards never collide, and the one that
    finds its card full is left unattached rather than doubled up."""
    client, _pid, card_a, card_b = two_cards
    sc = screens(('A', 5), ('B', 5), ('C', 5), ('D', 5), ('E', 5))
    for name in ('A', 'B', 'C'):
        attach(client, name, card_a, sc)
    attach(client, 'D', card_a, sc)  # one socket left: D takes it and stops
    attach(client, 'D', card_b, sc)  # the rest of D lands where it is dropped
    res = attach(client, 'E', card_b, sc)
    seen = [(p['cardId'], p['port']) for s in res['screens'] for p in s['ports']
            if p['cardId']]
    assert len(seen) == 25 and len(seen) == len(set(seen)), (
        'a drop handed the same socket out twice')
    assert 'overlap' not in kinds(res)
    assert spots(res, 'D') == [(card_a, 16)] + [(card_b, n) for n in (1, 2, 3, 4)]


# ── 3. The block move ─────────────────────────────────────────────────────

def test_the_block_move_relocates_the_whole_set_in_order(one_card):
    """Whole set, same relative order, or not at all. Shifting one port out of
    the middle of a run to clear a clash leaves a loom whose labels no longer
    match what it is plugged into."""
    client, _pid, card = one_card
    sc = screens(('Main', 4), ('Side', 4))
    for index, port in enumerate((5, 6, 7, 8)):
        client.post('/api/port-assignments/pin', json={
            'layerId': 'Side', 'index': index, 'cardId': card, 'port': port,
            'screens': sc})
    assert numbers(attach(client, 'Main', card, sc), 'Main') == [1, 2, 3, 4]

    resp = client.post('/api/port-assignments/move-block',
                       json={'layerId': 'Main', 'screens': sc})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    res = resp.get_json()['resolution']

    # Side holds 5-8, so the next free run of four above Main's old start is
    # 9-12. Consecutive, in the same order, all four of them.
    assert numbers(res, 'Main') == [9, 10, 11, 12]
    assert numbers(res, 'Side') == [5, 6, 7, 8], "another screen's pins moved"
    assert all(c == card for c, _p in spots(res, 'Main'))


def test_nothing_repacks_when_a_screen_moves(one_card):
    """The other half of "nothing lands by itself": nothing SLIDES by
    itself either. Under the retired auto rule a moved screen left a gap
    the next screen's auto ports packed down into; now every port is a
    pin, so Main moving up to 9-12 leaves 1-4 empty and Side exactly where
    it was on 5-8. A hole on a card is a hole until somebody fills it."""
    client, _pid, card = one_card
    sc = screens(('Main', 4), ('Side', 4))
    attach(client, 'Main', card, sc)
    assert numbers(attach(client, 'Side', card, sc), 'Side') == [5, 6, 7, 8]

    resp = client.post('/api/port-assignments/move-block',
                       json={'layerId': 'Main', 'screens': sc})
    assert resp.status_code == 200
    res = resp.get_json()['resolution']
    assert numbers(res, 'Main') == [9, 10, 11, 12]
    assert numbers(res, 'Side') == [5, 6, 7, 8], (
        "Side's ports re-packed into the room Main left")
    assert sources(res, 'Side') == ['pin'] * 4
    summary = next(c for c in res['cards'] if c['cardId'] == card)
    assert (summary['used'], summary['free']) == (8, 8)


def test_a_block_move_clears_a_clash_without_touching_the_other_screen(one_card):
    client, _pid, card = one_card
    sc = screens(('Main', 3), ('Side', 3))
    for layer in ('Main', 'Side'):
        client.post('/api/port-assignments/pin', json={
            'layerId': layer, 'index': 0, 'cardId': card, 'port': 4,
            'screens': sc})
    assert 'overlap' in kinds(resolve(client, ('Main', 3), ('Side', 3)))

    resp = client.post('/api/port-assignments/move-block',
                       json={'layerId': 'Main', 'screens': sc})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    res = resp.get_json()['resolution']
    assert 'overlap' not in kinds(res), res['issues']
    assert numbers(res, 'Side')[0] == 4, 'the screen that stayed put moved'
    moved = numbers(res, 'Main')
    assert moved == list(range(moved[0], moved[0] + 3)), moved


def test_a_block_move_overrides_the_moving_screens_own_pins(one_card):
    """A named decision, and worth naming: the move re-pins every port of THIS
    screen at the new block. Honouring its old pins would mean moving only
    the rest and tearing the run in two, which is what the move exists to
    prevent. Another screen's pins are obstacles and are never touched."""
    client, _pid, card = one_card
    sc = screens(('Main', 4), ('Side', 2))
    client.post('/api/port-assignments/pin', json={
        'layerId': 'Side', 'index': 0, 'cardId': card, 'port': 2, 'screens': sc})
    attach(client, 'Main', card, sc)  # 1, 3, 4, 5 - around Side's pin
    client.post('/api/port-assignments/pin', json={
        'layerId': 'Main', 'index': 2, 'cardId': card, 'port': 15, 'screens': sc})

    before = resolve(client, ('Main', 4), ('Side', 2))
    assert numbers(before, 'Main') == [1, 3, 15, 5], 'the pin did not hold'

    resp = client.post('/api/port-assignments/move-block',
                       json={'layerId': 'Main', 'screens': sc})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    res = resp.get_json()['resolution']

    main = numbers(res, 'Main')
    assert main == list(range(main[0], main[0] + 4)), (
        f'the block is not consecutive: {main}')
    assert 15 not in main or main[2] == 15
    assert sources(res, 'Main') == ['pin'] * 4, (
        'a block move must pin the whole set')
    assert numbers(res, 'Side')[0] == 2, "another screen's pin was moved"


def test_a_block_move_onto_a_named_card_moves_there(two_cards):
    client, _pid, _card_a, card_b = two_cards
    sc = screens(('Main', 5),)
    resp = client.post('/api/port-assignments/move-block',
                       json={'layerId': 'Main', 'cardId': card_b, 'screens': sc})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    res = resp.get_json()['resolution']
    assert spots(res, 'Main') == [(card_b, n) for n in range(1, 6)]


def test_a_block_move_with_nowhere_to_land_is_refused_not_half_done(one_card):
    """No card has a run that long, so nothing changes at all. A move that
    placed what fitted and gave up would be the split this module refuses."""
    client, _pid, card = one_card
    sc = screens(('Main', 10), ('Side', 5))
    attach(client, 'Main', card, sc)
    before = attach(client, 'Side', card, sc)
    assert numbers(before, 'Side') == [11, 12, 13, 14, 15]
    resp = client.post('/api/port-assignments/move-block',
                       json={'layerId': 'Main', 'screens': sc})
    assert resp.status_code == 409, resp.get_data(as_text=True)
    assert 'error' in resp.get_json()
    after = resolve(client, ('Main', 10), ('Side', 5))
    assert numbers(after, 'Main') == numbers(before, 'Main')
    assert numbers(after, 'Side') == numbers(before, 'Side')


# ── 3b. One port, placed by hand ──────────────────────────────────────────
#
# The block move is for a screen cabled as one run. This is for the port that
# is not like its neighbours - the spare patched across the room, the run the
# house rig was already made up to - and the rule it adds is that moving one
# port moves ONE port.

def test_one_port_can_be_placed_on_the_card_port_somebody_chose(one_card):
    client, _pid, card = one_card
    sc = screens(('Main', 6),)
    assert numbers(attach(client, 'Main', card, sc), 'Main') == [1, 2, 3, 4, 5, 6]

    resp = place(client, 'Main', 2, card, 12, sc)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    res = resp.get_json()['resolution']
    assert spots(res, 'Main')[2] == (card, 12)
    assert sources(res, 'Main')[2] == 'pin'
    assert resp.get_json()['moved']['port'] == 12
    assert resp.get_json()['moved']['from'] == {'cardId': card, 'port': 3}


def test_placing_one_port_leaves_the_screens_other_ports_where_they_were(one_card):
    """The whole point of the control: moving one port moves ONE port. The
    rest of the run are pins already - every port on a card is - so they
    stay exactly where they were, socket 3 is left empty, and the note
    names the one socket that changed and nothing else."""
    client, _pid, card = one_card
    sc = screens(('Main', 6),)
    before = numbers(attach(client, 'Main', card, sc), 'Main')

    resp = place(client, 'Main', 2, card, 12, sc)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    after = numbers(resp.get_json()['resolution'], 'Main')

    assert after == [1, 2, 12, 4, 5, 6], after
    assert [after[i] for i in (0, 1, 3, 4, 5)] == \
        [before[i] for i in (0, 1, 3, 4, 5)], 'a port nobody moved was renumbered'
    assert 'held' not in resp.get_json()['moved'], (
        'the placement reports holding ports - nothing needs holding now')
    assert resp.get_json()['moved']['note'] == (
        'Main port 3 is now on H9 slot 1 port 12.')
    assert resp.get_json()['resolution']['occupancy'][card].get('3') is None


def test_a_port_can_be_placed_before_the_rest_of_its_screen(one_card):
    """A port drop needs no card drop first: the one port lands, the
    screen's other ports stay unattached (never dealt out beside it), and
    the flag's report names exactly those."""
    client, _pid, card = one_card
    sc = screens(('Main', 4),)
    resp = place(client, 'Main', 2, card, 12, sc)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    res = resp.get_json()['resolution']
    assert spots(res, 'Main') == [(None, None), (None, None), (card, 12),
                                  (None, None)]
    assert resp.get_json()['moved']['from'] is None
    assert issue(res, 'overflow')['ports'] == [1, 2, 4]


def test_placing_one_port_leaves_another_screens_pins_alone(one_card):
    client, _pid, card = one_card
    sc = screens(('Main', 4), ('Side', 3))
    for index, port in enumerate((10, 11, 12)):
        client.post('/api/port-assignments/pin', json={
            'layerId': 'Side', 'index': index, 'cardId': card, 'port': port,
            'screens': sc})
    attach(client, 'Main', card, sc)

    resp = place(client, 'Main', 0, card, 16, sc)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    res = resp.get_json()['resolution']
    assert numbers(res, 'Side') == [10, 11, 12], "another screen's pins moved"
    assert numbers(res, 'Main') == [16, 2, 3, 4]


def test_placing_onto_an_occupied_port_is_reported_rather_than_taken(one_card):
    """Detect and OFFER, at the finest grain the feature has. The refusal names
    who is on the socket and what happens if this lands on it as well, and
    nothing has moved by the time it is read - so the answer is a person's,
    not a retry's."""
    client, _pid, card = one_card
    sc = screens(('Main', 4), ('Side', 4))
    attach(client, 'Main', card, sc)
    assert numbers(attach(client, 'Side', card, sc), 'Side') == [5, 6, 7, 8]
    before = stored_state(client)

    resp = place(client, 'Side', 0, card, 2, sc)
    assert resp.status_code == 409, resp.get_data(as_text=True)
    body = resp.get_json()
    assert 'Main port 2' in body['error'], body['error']
    assert body['conflict']['port'] == 2
    assert [o['name'] for o in body['conflict']['occupants']] == ['Main']

    after = resolve(client, ('Main', 4), ('Side', 4))
    assert numbers(after, 'Main') == [1, 2, 3, 4], 'the occupant was displaced'
    assert numbers(after, 'Side') == [5, 6, 7, 8], 'the refused move happened'
    assert stored_state(client) == before, (
        'a refused placement changed the stored state')


def test_the_refusal_says_the_tenant_keeps_its_claim(one_card):
    """Under the retired auto rule the refusal had two outcomes to choose
    between (an auto tenant packed out of the way, a pinned one stayed).
    Every tenant is a pin now, so there is one outcome and the refusal
    says it: the socket would draw as a clash, nothing is renumbered."""
    client, _pid, card = one_card
    sc = screens(('Main', 4), ('Side', 4))
    attach(client, 'Main', card, sc)
    error = place(client, 'Side', 0, card, 2, sc).get_json()['error']
    assert 'keeps its claim' in error, error
    assert 'draw as a clash' in error, error
    assert 'renumber' not in error and 'automatically' not in error, error


def test_confirming_over_a_pinned_port_keeps_both_claims(one_card):
    """Two screens on one socket is a real thing - a hot spare on the same
    port - so it stays reachable once it has been read out. Both keep the
    claim, both draw as a clash, and neither is renumbered."""
    client, _pid, card = one_card
    sc = screens(('Main', 4), ('Side', 4))
    client.post('/api/port-assignments/pin', json={
        'layerId': 'Main', 'index': 1, 'cardId': card, 'port': 2,
        'screens': sc})
    assert place(client, 'Side', 0, card, 2, sc).status_code == 409

    resp = place(client, 'Side', 0, card, 2, sc, confirm=True)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    res = resp.get_json()['resolution']
    assert numbers(res, 'Main')[1] == 2, 'the occupant was pushed off'
    assert numbers(res, 'Side')[0] == 2
    assert by_name(res, 'Side')['ports'][0]['overlap'] is True
    assert 'overlap' in kinds(res)
    assert 'nothing was displaced' in resp.get_json()['moved']['note']


def test_a_placement_onto_another_card_says_the_run_now_spans_two(one_card):
    """The honest half of a per-port move: it CAN strand a run across two
    machines, which a card drop would never do on its own. It is allowed -
    somebody asked - and it is said out loud, because two cards is two
    trunks to one wall."""
    client, pid, card_a = one_card
    state = set_card(client, pid, 1, 'novastar-card-h-16xrj45-2xfiber')
    card_b = card_ids(state)[1]
    sc = screens(('Main', 5),)
    attach(client, 'Main', card_a, sc)

    resp = place(client, 'Main', 4, card_b, 1, sc)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    res = resp.get_json()['resolution']
    assert spots(res, 'Main') == [(card_a, 1), (card_a, 2), (card_a, 3),
                                  (card_a, 4), (card_b, 1)]
    assert by_name(res, 'Main')['split'] is True
    assert 'spans 2 cards' in resp.get_json()['moved']['note']


def test_a_placement_names_the_socket_it_landed_on(one_card):
    """The note is what the dock strip prints after the move (its quiet blue
    row), and a port number on
    its own is not what the tech is standing in front of. The card's name is
    not repeated in front of a label already built out of it - "SR SR-9" reads
    like two different things."""
    client, pid, card = one_card
    client.put(f'/api/processors/{pid}/cards/{card}', json={'name': 'SR'})
    resp = place(client, 'Main', 0, card, 9, screens(('Main', 3),))
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert 'is now on SR-9.' in resp.get_json()['moved']['note'], \
        resp.get_json()['moved']['note']


def test_a_socket_a_box_named_is_called_by_both_names(one_card):
    """The other half of the same rule. A CVT's ports are named after the box,
    so the label alone does not say which card it hangs off - and that is the
    thing somebody is about to plug into."""
    client, pid, card = one_card
    client.put(f'/api/processors/{pid}/cards/{card}', json={'name': 'SR'})
    resp = client.post(f'/api/processors/{pid}/cards/{card}/cvts',
                       json={'deviceId': 'novastar-cvt10'})
    cvt_id = resp.get_json()['resolved'][0]['slots'][0]['card']['cvts'][0]['id']
    client.put(f'/api/processors/{pid}/cvts/{cvt_id}', json={'name': 'BOX-A'})

    resp = place(client, 'Main', 0, card, 5, screens(('Main', 3),))
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert 'is now on SR BOX-A-5.' in resp.get_json()['moved']['note'], \
        resp.get_json()['moved']['note']


def test_a_placement_past_the_cards_last_port_is_refused(one_card):
    """Sixteen ports is a fact about metal. There is no port 20 to place onto,
    and offering one would put a wall on a socket that does not exist."""
    client, _pid, card = one_card
    resp = place(client, 'Main', 0, card, 20, screens(('Main', 2),))
    assert resp.status_code == 409
    assert '16 ports' in resp.get_json()['error']
    assert stored_state(client) == STAMP


def test_a_placement_of_a_port_the_screen_does_not_have_is_refused(one_card):
    client, _pid, card = one_card
    resp = place(client, 'Main', 7, card, 1, screens(('Main', 3),))
    assert resp.status_code == 409
    assert 'no port 8' in resp.get_json()['error']


def test_a_card_with_no_settled_count_still_takes_a_placement(client):
    """"Ports can still be placed on it one at a time" is what the
    capacity-unknown row on the dock strip says about an SQ200, and this is
    that path. There is no ceiling to check against, and inventing one to
    check against is the failure the catalog exists to prevent."""
    state = add_processor(client, 'brompton-sq200')
    card = card_ids(state)[0]
    resp = place(client, 'Main', 0, card, 6, screens(('Main', 2),))
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert spots(resp.get_json()['resolution'], 'Main')[0] == (card, 6)


def test_assigning_from_the_socket_lands_where_pinning_from_the_screen_does(
        one_card):
    """The dock's socket end knows a card and a port number and asks which
    screen plugs in; the screen end knows a screen's port and asks
    where it goes. Same cable, two ends, and they have to write the same pin -
    two implementations of "what does that mean" would disagree the first time
    a socket was already claimed."""
    client, _pid, card = one_card
    sc = screens(('Main', 4), ('Side', 2))
    assert client.post('/api/port-assignments/pin', json={
        'layerId': 'Main', 'index': 2, 'cardId': card, 'port': 11,
        'screens': sc}).status_code == 200
    pinned = spots(resolve(client, ('Main', 4), ('Side', 2)), 'Main')

    client.post('/api/port-assignments/unpin',
                json={'layerId': 'Main', 'screens': sc})
    assert place(client, 'Main', 2, card, 11, sc).status_code == 200
    placed = spots(resolve(client, ('Main', 4), ('Side', 2)), 'Main')

    assert placed[2] == pinned[2] == (card, 11)
    stored = [p for p in
              client.get('/api/project').get_json()[assignment.STATE_KEY]['pins']
              if p['index'] == 2]
    assert stored == [{'layerId': 'Main', 'index': 2, 'cardId': card,
                       'port': 11}]


# ── 4. Overflow onto another card ─────────────────────────────────────────

def test_a_wall_bigger_than_its_card_is_reported_rather_than_spilled(one_card):
    """Seventeen ports on a sixteen-port card. The seventeenth is left with no
    card at all: putting it on another one is a patching decision with a
    physical consequence - a second trunk to one wall - and belongs to a
    person, not to the app."""
    client, _pid, card = one_card
    res = attach(client, 'Main', card, screens(('Main', 17)))
    assert numbers(res, 'Main')[:16] == list(range(1, 17))
    assert numbers(res, 'Main')[16] is None
    assert by_name(res, 'Main')['unplaced'] == [16]

    over = issue(res, 'overflow')
    assert over['layerId'] == 'Main'
    assert over['ports'] == [17], 'reported in the screen\'s own numbering'
    assert '17' in over['message']
    assert 'not attached' in over['message']
    # The row only states the fact. Attaching the spare ports is a drag onto
    # a card in the dock, so the strip offers no place buttons for it.
    assert over['offers'] == []


def test_the_overflow_can_be_placed_on_a_different_card(two_cards):
    """A single screen's ports MAY span two cards - `.scr` stores the sending
    card per cabinet, so the format has no objection either. It just may not
    happen unasked: the deciding gesture is the dock drag, which lands on
    this same endpoint."""
    client, _pid, card_a, card_b = two_cards
    sc = screens(('Main', 17),)
    attach(client, 'Main', card_a, sc)

    resp = client.post('/api/port-assignments/place-overflow',
                       json={'layerId': 'Main', 'cardId': card_b, 'screens': sc})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    res = resp.get_json()['resolution']

    assert spots(res, 'Main')[:16] == [(card_a, n) for n in range(1, 17)]
    assert spots(res, 'Main')[16] == (card_b, 1)
    assert by_name(res, 'Main')['unplaced'] == []
    assert by_name(res, 'Main')['split'] is True
    assert by_name(res, 'Main')['cardIds'] == [card_a, card_b]
    assert 'overflow' not in kinds(res)


def test_placed_overflow_stays_put_when_the_next_screen_arrives(two_cards):
    """The overflow is stored as pins, so the numbering someone decided on
    stays decided when the next screen is dropped beside it - the new
    screen's fill works around the pin rather than over it."""
    client, _pid, card_a, card_b = two_cards
    sc = screens(('Main', 17), ('Side', 4))
    attach(client, 'Main', card_a, sc)
    attach(client, 'Main', card_b, sc)
    res = attach(client, 'Side', card_b, sc)
    assert spots(res, 'Main')[16] == (card_b, 1)
    assert sources(res, 'Main')[16] == 'pin'
    assert spots(res, 'Side') == [(card_b, n) for n in (2, 3, 4, 5)]


def test_an_overflow_with_no_card_anywhere_reads_the_same(one_card):
    """Whether room exists elsewhere or nowhere, the row is the same plain
    fact - the ports are not attached. The strip stopped weighing the
    project's spare room the day it stopped offering places, and a drop on
    a full card is refused with the same plain fact."""
    client, _pid, card = one_card
    sc = screens(('Main', 16), ('Side', 4))
    attach(client, 'Main', card, sc)
    resp = client.post('/api/port-assignments/place-overflow',
                       json={'layerId': 'Side', 'cardId': card, 'screens': sc})
    assert resp.status_code == 409, resp.get_data(as_text=True)
    assert 'no free ports' in resp.get_json()['error']
    res = resolve(client, ('Main', 16), ('Side', 4))
    over = issue(res, 'overflow')
    assert over['layerId'] == 'Side'
    assert over['offers'] == []
    assert 'not attached' in over['message']


# ── 5. A pin holds ────────────────────────────────────────────────────────

def test_a_fill_works_around_a_pin_and_never_over_it(one_card):
    """A card drop fills the free sockets and only the free sockets. A pin
    sitting at port 3 makes the next screen take 1, 2, 4, 5 - a gap in the
    run, which is honest about where the ports actually are (the block
    move is the way out of it)."""
    client, _pid, card = one_card
    sc = screens(('Main', 4), ('Side', 1))
    resp = client.post('/api/port-assignments/pin', json={
        'layerId': 'Side', 'index': 0, 'cardId': card, 'port': 3,
        'screens': sc})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    res = attach(client, 'Main', card, sc)
    assert numbers(res, 'Side') == [3], 'the pinned port moved'
    assert sources(res, 'Side') == ['pin']
    assert numbers(res, 'Main') == [1, 2, 4, 5], (
        'the fill stamped over the pin or failed to work around it')
    assert sources(res, 'Main') == ['pin'] * 4


def test_a_pin_holds_through_screens_being_added_and_removed(two_cards):
    client, _pid, card_a, card_b = two_cards
    client.post('/api/port-assignments/pin', json={
        'layerId': 'Upstage', 'index': 0, 'cardId': card_b, 'port': 12,
        'screens': screens(('Upstage', 2))})
    for lineup in (
        (('Upstage', 2),),
        (('Main', 6), ('Upstage', 2)),
        (('Main', 6), ('Side', 9), ('Upstage', 2)),
        (('Upstage', 2), ('Main', 6)),
    ):
        res = resolve(client, *lineup)
        assert spots(res, 'Upstage')[0] == (card_b, 12), lineup


def test_any_port_of_any_screen_can_be_pinned(two_cards):
    """Not just the first, and not just on the card the screen was dropped
    on. The port in the middle of a run is exactly the one somebody needs
    to hold when a patch was made up before the drawing was."""
    client, _pid, card_a, card_b = two_cards
    sc = screens(('Main', 5),)
    attach(client, 'Main', card_a, sc)
    resp = client.post('/api/port-assignments/pin', json={
        'layerId': 'Main', 'index': 3, 'cardId': card_b, 'port': 7,
        'screens': sc})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    res = resp.get_json()['resolution']
    assert spots(res, 'Main')[3] == (card_b, 7)
    assert sources(res, 'Main') == ['pin'] * 5
    assert [c for c, _p in spots(res, 'Main')][:3] == [card_a] * 3
    assert by_name(res, 'Main')['split'] is True, (
        'a pin onto another card splits the screen and should read that way')


def test_a_pin_without_a_port_number_takes_the_cards_lowest_free_one(two_cards):
    """"Put this one on that card" is the decision; which free number it lands
    on is arithmetic. Leaving the number out is the normal case from the dock,
    and the server owns the answer - working it out in the browser would be a
    second implementation of "which ports are free" that gets it wrong the
    first time a pin leaves a hole in the middle of a card."""
    client, _pid, card_a, card_b = two_cards
    sc = screens(('Main', 3), ('Side', 2))
    # A hole: Side holds card B's port 1, so the lowest FREE one is 2.
    client.post('/api/port-assignments/pin', json={
        'layerId': 'Side', 'index': 0, 'cardId': card_b, 'port': 1,
        'screens': sc})

    resp = client.post('/api/port-assignments/pin', json={
        'layerId': 'Main', 'index': 1, 'cardId': card_b, 'screens': sc})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()['pinned'] == {'cardId': card_b, 'port': 2}
    res = resp.get_json()['resolution']
    assert spots(res, 'Main')[1] == (card_b, 2)
    assert sources(res, 'Main')[1] == 'pin'
    assert 'overlap' not in kinds(res), 'it landed on a port already held'


def test_a_pin_onto_a_full_card_is_refused_rather_than_stacked(two_cards):
    client, _pid, card_a, _card_b = two_cards
    sc = screens(('Main', 16), ('Side', 2))
    attach(client, 'Main', card_a, sc)
    resp = client.post('/api/port-assignments/pin', json={
        'layerId': 'Side', 'index': 0, 'cardId': card_a, 'screens': sc})
    assert resp.status_code == 409
    assert 'free' in resp.get_json()['error']


def test_which_ports_are_attached_is_visible(one_card):
    """A port's source says how it got there - 'pin' for every port on a
    card, None for one that is not attached - so the dock can draw the
    difference between held and missing without a second derivation."""
    client, _pid, card = one_card
    sc = screens(('Main', 3))
    client.post('/api/port-assignments/pin', json={
        'layerId': 'Main', 'index': 1, 'cardId': card, 'port': 9,
        'screens': sc})
    res = resolve(client, ('Main', 3))
    assert sources(res, 'Main') == [None, 'pin', None]
    res = attach(client, 'Main', card, sc)
    assert sources(res, 'Main') == ['pin', 'pin', 'pin']
    assert numbers(res, 'Main') == [1, 9, 2]


def test_releasing_a_pin_leaves_the_port_unattached(one_card):
    """A release takes the port off its card and nothing more: the socket
    it left stays empty, the screen's other ports stay where they are, and
    the port is reported as not attached until somebody places it again."""
    client, _pid, card = one_card
    sc = screens(('Main', 3),)
    attach(client, 'Main', card, sc)
    client.post('/api/port-assignments/pin', json={
        'layerId': 'Main', 'index': 1, 'cardId': card, 'port': 9, 'screens': sc})
    assert numbers(resolve(client, ('Main', 3)), 'Main') == [1, 9, 3]

    resp = client.post('/api/port-assignments/unpin',
                       json={'layerId': 'Main', 'index': 1, 'screens': sc})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    res = resp.get_json()['resolution']
    assert numbers(res, 'Main') == [1, None, 3]
    assert sources(res, 'Main') == ['pin', None, 'pin']
    assert issue(res, 'overflow')['ports'] == [2]
    assert [p['index'] for p in resp.get_json()['state']['pins']] == [0, 2]


def test_releasing_a_whole_screen_releases_every_one_of_its_pins(one_card):
    client, _pid, card = one_card
    sc = screens(('Main', 3),)
    for index, port in ((0, 11), (1, 12), (2, 13)):
        client.post('/api/port-assignments/pin', json={
            'layerId': 'Main', 'index': index, 'cardId': card, 'port': port,
            'screens': sc})
    assert numbers(resolve(client, ('Main', 3)), 'Main') == [11, 12, 13]

    resp = client.post('/api/port-assignments/unpin',
                       json={'layerId': 'Main', 'screens': sc})
    assert resp.status_code == 200
    res = resp.get_json()['resolution']
    assert numbers(res, 'Main') == [None, None, None]
    assert resp.get_json()['state']['pins'] == []


def test_a_pin_to_a_card_that_is_gone_is_reported_not_dropped(one_card):
    """Pulling a card out from under a pin is a real edit someone makes. The
    pin is kept and reported rather than deleted, because the alternative is
    the app throwing away a decision it was told to hold."""
    client, pid, card = one_card
    client.post('/api/port-assignments/pin', json={
        'layerId': 'Main', 'index': 0, 'cardId': card, 'port': 4,
        'screens': screens(('Main', 2))})
    resp = client.put(f'/api/processors/{pid}/slots/0', json={'deviceId': None})
    assert resp.status_code == 200

    res = resolve(client, ('Main', 2))
    gone = issue(res, 'pin-card-gone')
    assert gone['layerId'] == 'Main' and gone['port'] == 4
    assert gone['offers'][0]['action'] == 'release'
    stored = client.get('/api/project').get_json()[assignment.STATE_KEY]
    assert stored['pins'], 'the pin was silently discarded'


def test_a_pin_is_refused_onto_a_card_that_is_not_in_the_project(one_card):
    client, _pid, _card = one_card
    resp = client.post('/api/port-assignments/pin', json={
        'layerId': 'Main', 'index': 0, 'cardId': 'cardNope', 'port': 1,
        'screens': screens(('Main', 2))})
    assert resp.status_code == 404
    assert stored_state(client) == STAMP


# ── 6. Storage ────────────────────────────────────────────────────────────

def test_pins_round_trip_through_save_and_reload(two_cards):
    """Project-level state rides the whole-project POST / PUT, so this is the
    same path undo/redo and a file open take."""
    client, _pid, card_a, card_b = two_cards
    sc = screens(('Main', 4),)
    client.post('/api/port-assignments/pin', json={
        'layerId': 'Main', 'index': 2, 'cardId': card_b, 'port': 6,
        'screens': sc})

    saved = client.get('/api/project').get_json()
    assert saved[assignment.STATE_KEY]['pins'], 'the pin never reached the project'

    assert client.post('/api/project', json=saved).status_code == 200
    assert client.put('/api/project', json=saved).status_code == 200

    res = resolve(client, ('Main', 4))
    assert spots(res, 'Main')[2] == (card_b, 6)
    assert sources(res, 'Main')[2] == 'pin'


def test_only_pins_and_the_retired_auto_stamp_are_stored(one_card):
    """Nothing derived is kept. Storing a numbering would put a stale copy
    in the file the moment a screen changed size, and the file would then
    disagree with the dock drawn beside it. What IS stored beside the pins
    is the retired-auto stamp: `auto` False for good, and `autoRetired`,
    the mark that keeps the migration from ever running twice."""
    client, _pid, card = one_card
    client.post('/api/port-assignments/pin', json={
        'layerId': 'Main', 'index': 0, 'cardId': card, 'port': 3,
        'screens': screens(('Main', 8))})
    stored = client.get('/api/project').get_json()[assignment.STATE_KEY]
    assert set(stored) == {'auto', 'autoRetired', 'pins'}
    assert stored['auto'] is False and stored['autoRetired'] is True
    assert stored['pins'] == [{'layerId': 'Main', 'index': 0,
                               'cardId': card, 'port': 3}]


# ── 7. The regression bar ─────────────────────────────────────────────────
#
# Every project is BORN with the state key now (the stamp, no pins) - that
# is how the funnel tells a fresh project from a pre-ruling file. What the
# bar holds is the same as ever: a read adds nothing, a refused edit adds
# nothing, and a project nobody wired carries the stamp and only the stamp.

def test_a_project_with_no_processors_carries_the_stamp_and_nothing_else(client):
    """Anyone who never opens the Data view, or defines no processor, sees
    the birth stamp and no more - including in the file they save.
    Resolving must not add to it, and an undefined machine is not an error
    to report at somebody, it is the default."""
    before = client.get('/api/project').get_json()
    assert 'processors' not in before
    assert before[assignment.STATE_KEY] == STAMP

    res = resolve(client, ('Main', 6), ('Side', 4))
    assert res['configured'] is False
    assert res['cards'] == []
    assert res['issues'] == [], 'a project with no processors was nagged at'
    assert numbers(res, 'Main') == [None] * 6

    after = client.get('/api/project').get_json()
    assert after == before, 'merely resolving changed the project'
    assert after['is_pristine'] is True, 'a read marked the project dirty'


def test_a_refused_edit_leaves_no_state_behind(client):
    """A 409 must not be the thing that changes the stored state. Editing
    the stored dict in place and then refusing is exactly how that happens."""
    resp = client.post('/api/port-assignments/move-block',
                       json={'layerId': 'Main', 'screens': screens(('Main', 4))})
    assert resp.status_code == 409
    project = client.get('/api/project').get_json()
    assert project[assignment.STATE_KEY] == STAMP
    assert project['is_pristine'] is True


def test_a_placement_with_no_processor_leaves_the_project_alone(client):
    """There is no socket to place onto, and saying so must not be the thing
    that writes assignment state onto a project that has none."""
    resp = client.post('/api/port-assignments/place', json={
        'layerId': 'Main', 'index': 0, 'cardId': 'cardNope', 'port': 1,
        'screens': screens(('Main', 2))})
    assert resp.status_code == 404
    project = client.get('/api/project').get_json()
    assert project[assignment.STATE_KEY] == STAMP
    assert project['is_pristine'] is True


def test_releasing_a_pin_that_was_never_made_changes_nothing(client):
    resp = client.post('/api/port-assignments/unpin',
                       json={'layerId': 'Main', 'screens': screens(('Main', 2))})
    assert resp.status_code == 200
    project = client.get('/api/project').get_json()
    assert project[assignment.STATE_KEY] == STAMP
    assert project['is_pristine'] is True


def test_the_per_screen_port_templates_are_untouched(client_with_layer):
    """Assignment sits beside the existing port labels, not on top of them. A
    project with no processors still gets its labels from the screen's own
    templates, exactly as it always did."""
    project = client_with_layer.get('/api/project').get_json()
    layer_id = project['layers'][0]['id']
    resp = client_with_layer.put(f'/api/layer/{layer_id}', json={
        'portLabelTemplatePrimary': 'SR-#',
        'portLabelTemplateReturn': 'SRB-#',
    })
    assert resp.status_code == 200
    layer = client_with_layer.get('/api/project').get_json()['layers'][0]
    assert layer['portLabelTemplatePrimary'] == 'SR-#'
    assert layer['portLabelTemplateReturn'] == 'SRB-#'
    assert stored_state(client_with_layer) == STAMP


def test_the_docks_assignment_controls_stay_out_of_the_field_sweep():
    """tests/test_all_fields_sweep.py drives every control declared inside a
    .tab-panel straight at the selected LAYER. Assignment is project state,
    and since the consolidation its one declared control - the
    add-processor picker - lives in the dock's static markup, OUTSIDE every
    panel, so the sweep must never find it; swept, it would fail for a
    reason that has nothing to do with it. The issue rows themselves are
    still built in JS, onto #hw-dock-issues, and the retired panel's
    #port-assignment-issues host must stay gone - as must the retired auto
    checkbox, whose only UI remnant is the strip's turn-back-on offer."""
    from html.parser import HTMLParser

    template = os.path.join(os.path.dirname(__file__), '..', 'src',
                            'templates', 'index.html')
    with open(template, encoding='utf-8') as fh:
        html = fh.read()

    void = {'input', 'br', 'hr', 'img', 'meta', 'link', 'col', 'wbr',
            'area', 'base', 'embed', 'source', 'track', 'param'}

    class Scan(HTMLParser):
        """The sweep's panel scope, re-derived: a control counts as swept
        when it sits inside a .tab-panel (or #text-layer-panel)."""

        def __init__(self):
            super().__init__(convert_charrefs=True)
            self._stack = []
            self._panels = []
            self.declared = set()
            self.swept = set()

        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if tag not in void:
                self._stack.append(tag)
                classes = (a.get('class') or '').split()
                if ('tab-panel' in classes
                        or a.get('id') == 'text-layer-panel'):
                    self._panels.append(len(self._stack))
            if tag in ('input', 'select', 'textarea') and a.get('id'):
                self.declared.add(a['id'])
                if self._panels:
                    self.swept.add(a['id'])

        def handle_endtag(self, tag):
            if tag in void:
                return
            while self._stack and self._stack[-1] != tag:
                self._stack.pop()
            if self._stack:
                self._stack.pop()
            while self._panels and self._panels[-1] > len(self._stack):
                self._panels.pop()

    scan = Scan()
    scan.feed(html)
    key = 'processor-add-device'
    assert key in scan.declared, f'{key} is missing from the template'
    assert key not in scan.swept, (
        f'{key} is declared inside a .tab-panel - the field sweep would '
        f'drive project state at the selected layer')
    assert 'id="hw-dock-issues"' in html, 'the issues strip host is gone'
    assert 'id="hw-dock-flag"' in html, 'the attachment flag pill is gone'
    assert 'id="hw-dock-attach"' in html, 'the flag rows host is gone'
    assert 'id="port-assignment-issues"' not in html, (
        'the retired Port Numbering issue host is back')
    # The auto checkbox is retired whole, and so is auto itself (2026-09-03):
    # a resurrected declaration would offer a switch that no longer exists.
    assert 'id="port-assignment-auto"' not in html
    assert 'id="hw-dock-auto-wrap"' not in html


# ── 8. Labels come from the one place that owns them ──────────────────────

def test_a_ports_label_is_the_one_the_catalog_derived(one_card):
    """No second implementation of "which name wins". The label on an assigned
    port is read straight off the resolved card, so naming the card renames
    every port assigned to it with no further work here."""
    client, pid, card = one_card
    resp = client.put(f'/api/processors/{pid}/cards/{card}', json={'name': 'SR'})
    assert resp.status_code == 200
    res = attach(client, 'Main', card, screens(('Main', 3)))
    assert [p['label'] for p in by_name(res, 'Main')['ports']] == \
        ['SR-1', 'SR-2', 'SR-3']


def test_an_unnamed_card_gives_its_ports_no_label(one_card):
    """With nothing named upstream there is no processor-derived label, which
    leaves the per-screen templates in charge exactly as before."""
    client, _pid, card = one_card
    res = attach(client, 'Main', card, screens(('Main', 2)))
    assert [p['label'] for p in by_name(res, 'Main')['ports']] == [None, None]
    assert numbers(res, 'Main') == [1, 2], 'an unnamed card still numbers'


def test_a_card_summary_carries_the_names_its_ports_go_by(one_card):
    """A surface offering somebody a choice of sockets - the dock's chips -
    has to call each one what the box calls it. Without the names the list
    reads 1, 2, 3 while the card in the rack reads SR-1, SR-2, and the two get
    matched up by counting."""
    client, pid, card = one_card
    client.put(f'/api/processors/{pid}/cards/{card}', json={'name': 'SR'})
    summary = resolve(client, ('Main', 2))['cards'][0]
    assert summary['labels']['1'] == 'SR-1'
    assert summary['labels']['16'] == 'SR-16'


# ── 9. Both ends of one cable ─────────────────────────────────────────────
#
# The assignment module asks "where did my ports go" and the dock's chips ask
# "what is on this socket". They are the same question from the two
# ends of one cable, and the answer has to be written once.

def js(filename):
    path = os.path.join(os.path.dirname(__file__), '..', 'src', 'static', 'js',
                        filename)
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def function_body(source, signature):
    """One method out of a mixin class, from its signature to the closing brace
    at method indentation. Crude, and it only has to be good enough to prove
    which branch is where."""
    start = source.index(signature)
    return source[start:source.index('\n    }', start)]


def test_both_surfaces_place_a_port_through_the_one_request():
    """Two request builders would be two sets of rules about what may land on
    an occupied socket, and they would disagree the first time one was
    changed. The placement lives in the assignment module (_placePort) and the
    hardware dock - the only surface that still sends it - calls it."""
    panel = js('app-port-assignment.js')
    dock = js('app-dock.js')
    assert panel.count("'/api/port-assignments/place'") == 1
    assert '_placePort(spot, confirmed) {' in panel
    assert 'this._placePort(' in dock, (
        'the hardware dock does not use the shared placement')
    assert '/api/port-assignments/place' not in dock, (
        'the hardware dock built its own placement request')


def test_a_placement_asks_before_it_lands_on_somebody():
    """The refusal is a question, not a failure. Retrying it automatically
    would put the app back to rearranging things nobody agreed to."""
    body = function_body(js('app-port-assignment.js'),
                         '_placePort(spot, confirmed) {')
    assert 'if (confirmed || !data.conflict) return false;' in body
    assert 'window.confirm(' in body
    assert 'this._placePort(spot, true);' in body


def test_the_per_port_rows_stay_out_of_the_assignment_module():
    """The dock's drag is the assignment gesture, so the retired panel's
    per-port pin selects, movers and release buttons - and the per-screen
    "Move whole block" tools - are gone for good. This pins the module the
    way the stripped socket chooser is pinned, so the rows cannot quietly
    come back and grow a second set of assignment rules.

    (Two prior tests lived here: one held the mover's data-lrd-field keys
    for the focus guard, one held the mover's half-made choice off the DOM
    in _movingPort. Both drove UI that no longer exists - the focus guard's
    auto-toggle key rides in the static dock markup now, asserted with the
    field-sweep test above.)"""
    panel = js('app-port-assignment.js')
    for gone in ('port-move-card-', 'port-move-port-', 'port-pin-',
                 '_movingPort', 'Move whole block', 'Release all pins',
                 '_buildAssignmentScreen', '_buildAssignmentPort',
                 '_buildAssignmentFoot'):
        assert gone not in panel, (
            f'{gone!r} is back in the assignment module - assignment '
            f'controls belong to the dock now')
    assert 'processor-port-assign-' not in js('app-processors.js'), (
        'the stripped chooser is back in the processors module')
    # The dock's chip editors took over the per-port naming, and they must
    # not regrow the chooser either: the drag is the one assignment gesture.
    assert 'processor-port-assign-' not in js('app-dock.js'), (
        'the stripped chooser reappeared in the dock chip editor')
    # What deliberately STAYS: the refuse-and-offer surface, re-hosted as
    # rows on the dock's issues strip. The dock does not replace warnings.
    assert '_buildIssue(issue) {' in panel
    assert '_buildOffer(offer) {' in panel
    assert "getElementById('hw-dock-issues')" in panel, (
        'the issue rows stopped rendering onto the dock strip')
    # Auto-numbering is retired outright (2026-09-03): no checkbox, no
    # auto-off row, no turn-back-on offer, and no request to the old switch
    # (PUT /api/port-assignments answers 410 now).
    assert "port-assignment-auto" not in panel, (
        'the retired auto checkbox is back in the assignment module')
    for gone in ('auto: false', 'auto:false', 'auto: true', 'auto:true',
                 "'auto-on'", "'auto-off'", "'/api/port-assignments', 'PUT'",
                 'Toggle Auto Numbering'):
        assert gone not in panel, (
            f'{gone!r} is back in the assignment module - auto-numbering '
            f'is retired and nothing may offer it')
    # The overflow story lives under the attachment flag, not the strip.
    assert "kind !== 'overflow'" in panel, (
        'the strip is rendering overflow rows again - that story belongs '
        'to the dock header flag')


def test_the_backup_template_rides_the_return_labels_here_too(one_card):
    """returnLabels is this module's half of the one authority: the return
    ladder resolves in resolve_card and the assignment only carries the
    answer. A card-level backup template, a per-port typed name over it, and
    the derived <primary>R where neither speaks - all three rungs arrive in
    the same resolution the canvas indexes."""
    client, pid, card = one_card
    client.put(f'/api/processors/{pid}/cards/{card}',
               json={'name': 'SR', 'returnLabelTemplate': 'BU-#'})
    client.put(f'/api/processors/{pid}/cards/{card}/ports/2',
               json={'returnName': 'HOUSE-RTN'})
    res = attach(client, 'Main', card, screens(('Main', 3)))
    scr = by_name(res, 'Main')
    assert [p['returnLabel'] for p in scr['ports']] == \
        ['BU-1', 'HOUSE-RTN', 'BU-3']

    # Template cleared: rung three is back, and it is the same old default.
    client.put(f'/api/processors/{pid}/cards/{card}',
               json={'returnLabelTemplate': ''})
    res = resolve(client, ('Main', 3))
    scr = by_name(res, 'Main')
    assert [p['returnLabel'] for p in scr['ports']] == \
        ['SR-1R', 'HOUSE-RTN', 'SR-3R']


# ── 10. Ports claimed by a redundancy role ────────────────────────────────
#
# A port consumed by the redundancy mapping - the even half of a sequential
# card, every port of a 1:1 backup unit, a manual pick - is CLAIMED BY ROLE:
# a card drop fills around it, a block cannot land across it, and a hand
# placement is refused outright with the main it returns named in the
# refusal. Outright, unlike the occupied-port question: sharing a socket
# with another screen is a real rig (a hot spare), sharing it with its own
# backup role is not a rig at all.

def sequential_card(client):
    """One MX20 named SR, redundancy on, sequential: 6 ports, odds usable."""
    state = add_processor(client, 'novastar-mx20')
    pid = state['resolved'][0]['id']
    card = card_ids(state)[0]
    client.put(f'/api/processors/{pid}/cards/{card}', json={'name': 'SR'})
    client.put(f'/api/processors/{pid}', json={'redundancy': True})
    resp = client.put(f'/api/processors/{pid}/cards/{card}',
                      json={'redundancyMode': 'sequential'})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return pid, card


def test_a_card_drop_skips_the_backing_ports(client):
    """Three ports dropped on a sequential six land on 1, 3, 5 - the odd
    mains - and the card is full at three, because the evens are its
    returns. A fourth has nowhere to go, and a pin with no port number
    (the card-level drop) finds the same three sockets and no more."""
    _pid, card = sequential_card(client)
    res = attach(client, 'Wall', card, screens(('Wall', 3)))
    assert spots(res, 'Wall') == [(card, 1), (card, 3), (card, 5)]

    client.post('/api/port-assignments/unpin', json={'layerId': 'Wall'})
    resp = client.post('/api/port-assignments/place-overflow',
                       json={'layerId': 'Wall', 'cardId': card,
                             'screens': screens(('Wall', 4))})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert 'took 3 of 4 ports' in resp.get_json()['moved']['note']
    res = resp.get_json()['resolution']
    assert numbers(res, 'Wall') == [1, 3, 5, None]
    assert issue(res, 'overflow')
    resp = client.post('/api/port-assignments/pin', json={
        'layerId': 'Wall', 'index': 3, 'cardId': card,
        'screens': screens(('Wall', 4))})
    assert resp.status_code == 409, 'a card-level pin landed on a return socket'
    assert 'no free ports' in resp.get_json()['error']


def test_placing_onto_a_backing_port_is_refused_naming_the_main(client):
    """The refusal is hard - no confirm - and it says whose return the
    socket carries. Nothing moves and nothing is stamped on the project."""
    _pid, card = sequential_card(client)
    sc = screens(('Wall', 2))
    attach(client, 'Wall', card, sc)
    before = stored_state(client)
    resp = place(client, 'Wall', 1, card, 2, sc)
    assert resp.status_code == 409, resp.get_data(as_text=True)
    body = resp.get_json()
    assert 'backs up SR-1' in body['error'], body['error']
    assert 'return end' in body['error'], body['error']
    assert body.get('conflict') is None, (
        'a role refusal offered the occupied-port confirm')
    after = resolve(client, ('Wall', 2))
    assert spots(after, 'Wall') == [(card, 1), (card, 3)], (
        'the refused placement moved something')
    assert stored_state(client) == before


def test_a_1to1_backup_unit_takes_nothing_and_refuses_by_role(client):
    """Every port of the designated backup unit is consumed: a card drop
    finds nothing free on it, and a hand placement is refused with the
    main port it returns - the claimed-by-role treatment, unit-wide."""
    state = add_processor(client, 'novastar-mx20')
    main_pid = state['resolved'][0]['id']
    main_card = card_ids(state)[0]
    state = add_processor(client, 'novastar-mx20')
    backup_card = card_ids(state)[1]
    client.put(f'/api/processors/{main_pid}/cards/{main_card}',
               json={'name': 'P1'})
    backup_pid = state['resolved'][1]['id']
    client.put(f'/api/processors/{backup_pid}/cards/{backup_card}',
               json={'name': 'R1'})
    client.put(f'/api/processors/{main_pid}', json={'redundancy': True})
    resp = client.put(f'/api/processors/{main_pid}/cards/{main_card}',
                      json={'backupCardId': backup_card})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    # Eight ports against a mirrored six: the main fills, the backup takes
    # none, and the spill has nowhere to go.
    sc = screens(('Wall', 8))
    res = attach(client, 'Wall', main_card, sc)
    assert spots(res, 'Wall')[:6] == [(main_card, n) for n in range(1, 7)]
    assert spots(res, 'Wall')[6:] == [(None, None), (None, None)]
    assert issue(res, 'overflow')
    resp = client.post('/api/port-assignments/place-overflow',
                       json={'layerId': 'Wall', 'cardId': backup_card,
                             'screens': sc})
    assert resp.status_code == 409, 'the spill landed on the backup unit'
    assert 'no free ports' in resp.get_json()['error']

    resp = place(client, 'Wall', 6, backup_card, 3, screens(('Wall', 8)))
    assert resp.status_code == 409, resp.get_data(as_text=True)
    assert 'backs up P1-3' in resp.get_json()['error'], \
        resp.get_json()['error']


def test_the_card_summary_counts_backing_ports_out_of_free(client):
    """The card headers' used/capacity glance and the gear popover's capacity
    row both read the summary, so a sequential card must not promise six
    sockets when three of them are spoken for by the role."""
    _pid, card = sequential_card(client)
    res = attach(client, 'Wall', card, screens(('Wall', 2)))
    summary = next(c for c in res['cards'] if c['cardId'] == card)
    assert summary['capacity'] == 6
    assert summary['used'] == 2
    assert summary['backing'] == 3
    assert summary['free'] == 1


def test_a_block_cannot_land_across_a_backing_port(client):
    """A block is contiguous or it is not a block, and the evens of a
    sequential card break every run of two - so the move is refused rather
    than landed astride a return socket."""
    _pid, card = sequential_card(client)
    sc = screens(('Wall', 2))
    attach(client, 'Wall', card, sc)
    resp = client.post('/api/port-assignments/move-block',
                       json={'layerId': 'Wall', 'screens': sc})
    assert resp.status_code == 409, resp.get_data(as_text=True)
    assert 'consecutive free ports' in resp.get_json()['error']


def test_the_sx40_pair_claims_the_backing_boxes_whole(client):
    """The trunk-level pairing at the assignment's end - "10 per box"
    (2026-08-25): with redundancy on, the four stocked XDs are boxes A/C
    driving and B/D returning, so a twelve-port wall packs sockets 1-10 and
    jumps to 21 - every socket keeps its number on the drawing while B's
    and D's twenty are claimed by role, and a hand placement onto socket 11
    gets the same hard refusal every backing socket gets."""
    state = add_processor(client, 'brompton-sx40')
    pid = state['resolved'][0]['id']
    card = card_ids(state)[0]
    client.put(f'/api/processors/{pid}', json={'redundancy': True})

    res = attach(client, 'Wall', card, screens(('Wall', 12)))
    assert numbers(res, 'Wall') == list(range(1, 11)) + [21, 22]
    summary = next(c for c in res['cards'] if c['cardId'] == card)
    assert (summary['capacity'], summary['backing']) == (40, 20)
    assert (summary['used'], summary['free']) == (12, 8)

    resp = place(client, 'Wall', 0, card, 11, screens(('Wall', 12)))
    assert resp.status_code == 409, resp.get_data(as_text=True)
    body = resp.get_json()
    assert 'backs up' in body['error'] and 'return end' in body['error']
    # Socket 11 is box B's socket 1 (the 2026-08-27 silkscreen ruling), and
    # with nothing named upstream the refusal has to say so in the numbers
    # on the metal: the main it returns is box A's port 1, never "port 1"
    # bare - every box has a port 1 now - and never the card-wide 11.
    assert 'port 1 on Tessera XD A' in body['error'], body['error']


def test_the_halves_mode_claims_the_back_half_by_role(client):
    """The 2026-08-27 arrangement at the assignment's end: "1-8 on
    processor 1 and 9-16 as backups". With halves mode on a 16-port card,
    a card drop packs the front half and stops - the back half is spoken
    for by role - and a hand placement onto socket 9 gets the same hard
    refusal every backing socket gets, naming the main whose return it
    carries."""
    state = add_processor(client, 'novastar-h9')
    pid = state['resolved'][0]['id']
    state = set_card(client, pid, 0, 'novastar-card-h-16xrj45-2xfiber')
    card = card_ids(state)[0]
    client.put(f'/api/processors/{pid}/cards/{card}', json={'name': 'P1'})
    client.put(f'/api/processors/{pid}', json={'redundancy': True})
    resp = client.put(f'/api/processors/{pid}/cards/{card}',
                      json={'redundancyMode': 'halves'})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    res = attach(client, 'Wall', card, screens(('Wall', 10)))
    assert numbers(res, 'Wall') == list(range(1, 9)) + [None, None], (
        'the fill crossed into the back half')
    assert issue(res, 'overflow')
    summary = next(c for c in res['cards'] if c['cardId'] == card)
    assert (summary['capacity'], summary['backing']) == (16, 8)
    assert (summary['used'], summary['free']) == (8, 0)

    resp = place(client, 'Wall', 8, card, 9, screens(('Wall', 10)))
    assert resp.status_code == 409, resp.get_data(as_text=True)
    body = resp.get_json()
    assert 'backs up P1-1' in body['error'], body['error']
    assert 'return end' in body['error'], body['error']


# ── 11. A backup socket displays the occupancy of the socket it backs ─────
#
# Assign main A-1 to a screen and its return loom physically lands on B-1,
# so B-1 reading "free" - or only "backs up A-1" - understates a socket
# that is now carrying that screen's return. The resolution mirrors the
# main's occupant onto the backup socket, marked role 'return' and naming
# the main it follows. DERIVED, NEVER STORED: the mirrored entry is read
# through the backedBy link on every resolve, so un-assigning the main
# clears the backup's display with it, nothing lands in the project, and
# there is nothing extra to undo. One rule for every pairing shape that
# wires port-level links - the SX40's fixed boxes, sequential, 1:1, manual.

def returns_on(res, card, port):
    """The mirrored entries on one socket, flattened for comparison."""
    return [(o['name'], o['number'], o.get('role'), o['source'],
             (o.get('main') or {}).get('port'),
             (o.get('main') or {}).get('label'))
            for o in res['occupancy'].get(card, {}).get(str(port), [])]


def test_the_sx40s_b_sockets_carry_the_screens_returns(client):
    """The user's case, verbatim shape: "when i map A to a screen the B
    ports need to fill automatically." Twelve ports on a redundant SX40
    sit on sockets 1-10 and 21-22, so B's sockets 11-20 and D's 31-32 read
    as those screen-ports' return ends - each mirrored entry names the
    screen, the screen's own port number, and the main socket (by its A-n
    label) the display follows. The claims themselves are untouched: used,
    backing and free stand exactly as they did, and the project stores
    nothing for any of it."""
    state = add_processor(client, 'brompton-sx40')
    pid = state['resolved'][0]['id']
    card = card_ids(state)[0]
    boxes = state['resolved'][0]['slots'][0]['card']['cvts']
    for box, name in zip(boxes, ('A', 'B', 'C', 'D')):
        client.put(f'/api/processors/{pid}/cvts/{box["id"]}',
                   json={'name': name})
    client.put(f'/api/processors/{pid}', json={'redundancy': True})

    res = attach(client, 'Wall', card, screens(('Wall', 12)))
    assert returns_on(res, card, 11) == \
        [('Wall', 1, 'return', 'return', 1, 'A-1')]
    assert returns_on(res, card, 20) == \
        [('Wall', 10, 'return', 'return', 10, 'A-10')]
    assert returns_on(res, card, 31) == \
        [('Wall', 11, 'return', 'return', 21, 'C-1')]
    assert returns_on(res, card, 32) == \
        [('Wall', 12, 'return', 'return', 22, 'C-2')]
    assert returns_on(res, card, 33) == [], (
        'a free main grew a mirrored return')
    summary = next(c for c in res['cards'] if c['cardId'] == card)
    assert (summary['used'], summary['backing'], summary['free']) == \
        (12, 20, 8), 'the mirrored display leaked into the claim counts'
    assert len(stored_state(client)['pins']) == 12, (
        'derived occupancy stamped state onto the project')

    # Un-assigning the mains clears the backups' display with them - the
    # mirror is the main's occupant, so there is nothing to clear twice.
    client.post('/api/port-assignments/unpin', json={'layerId': 'Wall'})
    res = resolve(client, ('Wall', 12))
    assert res['occupancy'] == {}


def test_sequential_and_manual_sockets_mirror_the_same_way(client):
    """The same follow-through on the port-level shapes: a sequential
    card's even sockets carry the odd mains' occupants, and a manual pick
    mirrors exactly the socket somebody named - nothing else."""
    pid, card = sequential_card(client)
    res = attach(client, 'Wall', card, screens(('Wall', 2)))
    assert spots(res, 'Wall') == [(card, 1), (card, 3)]
    assert returns_on(res, card, 2) == \
        [('Wall', 1, 'return', 'return', 1, 'SR-1')]
    assert returns_on(res, card, 4) == \
        [('Wall', 2, 'return', 'return', 3, 'SR-3')]
    assert returns_on(res, card, 6) == []

    client.put(f'/api/processors/{pid}/cards/{card}',
               json={'redundancyMode': 'manual'})
    client.put(f'/api/processors/{pid}/cards/{card}/ports/1',
               json={'backup': {'cardId': card, 'port': 5}})
    res = resolve(client, ('Wall', 1))
    assert returns_on(res, card, 5) == \
        [('Wall', 1, 'return', 'return', 1, 'SR-1')]
    assert returns_on(res, card, 2) == [], (
        'manual is explicit - an unpicked socket mirrors nothing')


def test_a_1to1_backup_units_sockets_mirror_their_mains(client):
    """The designated backup unit stops looking idle the moment its main
    carries a show: every occupied main mirrors onto the same-numbered
    socket of the unit that returns it, across processors."""
    state = add_processor(client, 'novastar-mx20')
    main_pid = state['resolved'][0]['id']
    main_card = card_ids(state)[0]
    state = add_processor(client, 'novastar-mx20')
    backup_card = card_ids(state)[1]
    client.put(f'/api/processors/{main_pid}/cards/{main_card}',
               json={'name': 'P1'})
    client.put(f'/api/processors/{main_pid}', json={'redundancy': True})
    client.put(f'/api/processors/{main_pid}/cards/{main_card}',
               json={'backupCardId': backup_card})

    res = attach(client, 'Wall', main_card, screens(('Wall', 3)))
    assert spots(res, 'Wall') == [(main_card, n) for n in (1, 2, 3)]
    for n in (1, 2, 3):
        assert returns_on(res, backup_card, n) == \
            [('Wall', n, 'return', 'return', n, f'P1-{n}')]
    assert returns_on(res, backup_card, 4) == []


def test_a_mirrored_return_is_not_a_pin_and_follows_the_mains_clear(client):
    """The mirrored entry's source is 'return', never 'pin', so no release
    path can mistake it for a claim it may act on - and releasing the MAIN
    is the whole of clearing both ends: with the pin gone the mirror is
    gone, and the project holds pins and the retired-auto stamp and
    nothing else."""
    _pid, card = sequential_card(client)
    resp = place(client, 'Wall', 0, card, 1, screens(('Wall', 1)))
    assert resp.status_code == 200, resp.get_data(as_text=True)
    res = resolve(client, ('Wall', 1))
    assert returns_on(res, card, 2) == \
        [('Wall', 1, 'return', 'return', 1, 'SR-1')]
    assert all(o['source'] == 'pin'
               for o in res['occupancy'][card]['1']), (
        'the main claim itself must stay a pin')

    client.post('/api/port-assignments/unpin',
                json={'layerId': 'Wall', 'index': 0})
    res = resolve(client, ('Wall', 1))
    assert res['occupancy'].get(card, {}).get('2', []) == [], (
        'clearing the main left the mirrored return behind')
    assert stored_state(client) == STAMP, (
        'something beyond pins and the stamp was stored')


# ── 12. The platform wall ─────────────────────────────────────────────────
#
# A screen's Processing setting and a card's product line have to agree
# before a port may land (ruling, 2026-08-28): a Legacy screen never lands
# on COEX gear, a NovaStar screen never lands on a Brompton, and so on for
# every pairing. Every placement path - the card drop's fill included -
# refuses with both sides named; a saved pin that already violates the
# wall is reported red and NEVER silently released.


def pscreens(*triples):
    """(name, ports, platform) - the screens as the client sends them since
    the wall: the layer's Processing setting rides beside the port count."""
    return [{'layerId': name, 'name': name, 'ports': count,
             'platform': platform}
            for name, count, platform in triples]


def presolve(client, sc):
    resp = client.post('/api/port-assignments/resolve',
                       json={'screens': sc})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()['resolution']


@pytest.fixture()
def mixed_lines(client):
    """One COEX all-in-one and one legacy card, COEX FIRST - so a legacy
    screen landing anywhere proves the skip, not the ordering."""
    state = add_processor(client, 'novastar-mx40-pro')
    mx_card = card_ids(state)[0]
    state = add_processor(client, 'novastar-h9')
    pid = state['resolved'][1]['id']
    state = set_card(client, pid, 0, 'novastar-card-h-16xrj45-2xfiber')
    return client, mx_card, card_ids(state)[1]


def test_the_matrix_covers_every_ported_device():
    """Every processor and card in the catalog answers the matrix from its
    family, except the two devices ruled (or pending) past their family's
    line. A device this test does not expect would land in the else branch
    unrestricted - which is the deliberate default, but never silently for
    a device carrying a family the matrix claims to know."""
    by_family = {
        'novastar-mx': {'novastar-coex-1g'},
        'novastar-cx': {'novastar-5g'},
        'novastar-vx': {'novastar-armor'},
        'novastar-mctrl': {'novastar-armor'},
        'novastar-novapro': {'novastar-armor'},
        'novastar-h': {'novastar-armor'},
        'brompton': {'brompton'},
        'megapixel': {'megapixel-1g', 'megapixel-2.5g'},
    }
    overrides = {
        # Ruled COEX (2026-08-28, hedged); the 1G/5G sub-split is unruled,
        # so the gate takes both COEX settings until it is.
        'novastar-ku20': {'novastar-coex-1g', 'novastar-5g'},
        # "mx6000 and 2000 with 5g fiber only work with 5g settings".
        'novastar-card-mx-1x40g': {'novastar-5g'},
    }
    for device in catalog.devices():
        if device.get('kind') not in ('processor', 'card'):
            continue
        got = assignment.accepted_platforms(device['id'])
        want = overrides.get(device['id'],
                             by_family.get(device.get('family')))
        assert got == want, (
            f'{device["id"]}: accepts {got}, the matrix says {want}')


def test_a_card_drop_lands_only_on_its_own_lines_gear(mixed_lines):
    """The Legacy screen dropped on the COEX card is refused with both
    sides named; dropped on the H card it lands, and the COEX screen takes
    the COEX card - one wall, the same answer whichever card the drop
    names."""
    client, mx_card, h_card = mixed_lines
    sc = pscreens(('LEG', 2, 'novastar-armor'), ('CX1', 2, 'novastar-coex-1g'))
    resp = client.post('/api/port-assignments/place-overflow',
                       json={'layerId': 'LEG', 'cardId': mx_card, 'screens': sc})
    assert resp.status_code == 409
    assert resp.get_json()['error'] == (
        'LEG is programmed NovaStar (Legacy); MX40 Pro slot 1 is COEX gear.')
    attach(client, 'LEG', h_card, sc)
    res = attach(client, 'CX1', mx_card, sc)
    assert spots(res, 'LEG') == [(h_card, 1), (h_card, 2)]
    assert spots(res, 'CX1') == [(mx_card, 1), (mx_card, 2)]
    assert kinds(res) == []


def test_a_wall_with_no_matching_gear_stays_unplaced(mixed_lines):
    """A Brompton screen among NovaStar cards goes NOWHERE - every drop is
    refused, never landed on the least-wrong card - and the overflow
    report says its ports are not attached. No mismatch row: nothing is
    pinned, so nothing is wrong that a matching processor would not fix."""
    client, mx_card, h_card = mixed_lines
    sc = pscreens(('Wall', 3, 'brompton'))
    for card in (mx_card, h_card):
        resp = client.post('/api/port-assignments/place-overflow',
                           json={'layerId': 'Wall', 'cardId': card,
                                 'screens': sc})
        assert resp.status_code == 409, resp.get_data(as_text=True)
        assert 'is programmed Brompton Tessera' in resp.get_json()['error']
    res = presolve(client, sc)
    assert spots(res, 'Wall') == [(None, None)] * 3
    assert issue(res, 'overflow')['layerId'] == 'Wall'
    assert 'platform-mismatch' not in kinds(res)


def test_a_hand_placement_across_the_wall_is_refused_naming_both_sides(
        mixed_lines):
    """The refusal is a fact with both halves stated - what the screen is
    programmed, what the card is - because the fix could be either side
    and the message is all the strip shows."""
    client, mx_card, h_card = mixed_lines
    sc = pscreens(('IMAG SR', 2, 'novastar-armor'))
    attach(client, 'IMAG SR', h_card, sc)
    resp = place(client, 'IMAG SR', 0, mx_card, 1, sc)
    assert resp.status_code == 409
    assert resp.get_json()['error'] == (
        'IMAG SR is programmed NovaStar (Legacy); '
        'MX40 Pro slot 1 is COEX gear.')
    res = presolve(client, sc)
    assert spots(res, 'IMAG SR') == [(h_card, n) for n in (1, 2)], (
        'the refused placement moved something')


def test_the_pin_and_overflow_paths_hold_the_same_wall(mixed_lines):
    """One matrix, every door: the card-level pin and the overflow fill
    refuse across the wall with the same both-sides message the socket
    placement speaks."""
    client, mx_card, _h = mixed_lines
    sc = pscreens(('IMAG SR', 20, 'novastar-armor'))
    resp = client.post('/api/port-assignments/pin',
                       json={'layerId': 'IMAG SR', 'index': 0,
                             'cardId': mx_card, 'screens': sc})
    assert resp.status_code == 409
    assert 'is COEX gear' in resp.get_json()['error']
    # 20 Legacy ports on a 16-port H card: four genuinely overflow, and
    # the COEX card still may not take the tail.
    resp = client.post('/api/port-assignments/place-overflow',
                       json={'layerId': 'IMAG SR', 'cardId': mx_card,
                             'screens': sc})
    assert resp.status_code == 409
    assert 'is COEX gear' in resp.get_json()['error']


def test_move_block_stays_on_matching_gear(mixed_lines):
    """The block move's search walks matching cards only - so the next
    free block for a Legacy run is further down its own card, never the
    COEX card beside it - and naming the COEX card outright is refused."""
    client, mx_card, h_card = mixed_lines
    sc = pscreens(('LEG', 2, 'novastar-armor'))
    resp = client.post('/api/port-assignments/move-block',
                       json={'layerId': 'LEG', 'cardId': mx_card,
                             'screens': sc})
    assert resp.status_code == 409
    assert 'is COEX gear' in resp.get_json()['error']
    resp = client.post('/api/port-assignments/move-block',
                       json={'layerId': 'LEG', 'screens': sc})
    assert resp.status_code == 200
    assert resp.get_json()['moved']['cardId'] == h_card


def test_a_violating_pin_is_reported_red_and_kept(mixed_lines):
    """A saved project can hold a pin the wall now forbids - pinned before
    the screen's Processing changed, or before the wall existed. It is
    reported as its own red row and the pin STAYS: releasing it would
    renumber a drawing the truck was packed to, which is the one thing
    this module never does by itself."""
    client, mx_card, _h = mixed_lines
    # The pin lands while the screen carries no platform - exactly an old
    # project's shape - and the violation appears when the platform does.
    resp = place(client, 'IMAG SR', 0, mx_card, 3,
                 screens(('IMAG SR', 1)))
    assert resp.status_code == 200, resp.get_data(as_text=True)
    res = presolve(client, pscreens(('IMAG SR', 1, 'novastar-armor')))
    row = issue(res, 'platform-mismatch')
    assert row['layerId'] == 'IMAG SR' and row['cardId'] == mx_card
    assert 'Nothing has been unpinned' in row['message']
    assert {o['action'] for o in row['offers']} == {'move-block', 'release'}
    assert spots(res, 'IMAG SR') == [(mx_card, 3)], (
        'the report released the pin by itself')
    assert sources(res, 'IMAG SR') == ['pin']


def test_ku20_takes_both_coex_settings_and_nothing_else(client):
    """The KU20 is ruled COEX (2026-08-28, hedged) with the 1G/5G
    sub-split still open, so BOTH COEX settings pass and everything else
    is refused. When the sub-split is ruled, one of the two 200s below
    flips to a 409 and this test names the day."""
    state = add_processor(client, 'novastar-ku20')
    card = card_ids(state)[0]
    ok_1g = place(client, 'A', 0, card, 1,
                  pscreens(('A', 1, 'novastar-coex-1g')))
    assert ok_1g.status_code == 200, ok_1g.get_data(as_text=True)
    ok_5g = place(client, 'B', 0, card, 2,
                  pscreens(('A', 1, 'novastar-coex-1g'),
                           ('B', 1, 'novastar-5g')))
    assert ok_5g.status_code == 200, ok_5g.get_data(as_text=True)
    for platform in ('novastar-armor', 'brompton'):
        resp = place(client, 'C', 0, card, 3,
                     pscreens(('C', 1, platform)))
        assert resp.status_code == 409, platform


def test_cx_gear_takes_only_the_5g_setting(client):
    """"CX only map to 5G": the CX80 Pro takes the 5G setting and refuses
    both other NovaStar settings - the 1G COEX line is not its line."""
    state = add_processor(client, 'novastar-cx80-pro')
    card = card_ids(state)[0]
    ok = place(client, 'FIVE', 0, card, 1,
               pscreens(('FIVE', 1, 'novastar-5g')))
    assert ok.status_code == 200, ok.get_data(as_text=True)
    for platform in ('novastar-coex-1g', 'novastar-armor'):
        resp = place(client, 'X', 0, card, 2,
                     pscreens(('X', 1, platform)))
        assert resp.status_code == 409, platform
        assert '5G COEX gear' in resp.get_json()['error']


def test_the_vendor_walls_hold_both_ways(client):
    """Brompton screens to Brompton gear, Megapixel screens (either rate)
    to Megapixel gear, and never across. Both directions are asserted
    because the ruling was given in both: "cannot be mapped to a Brompton
    processor and vice versa"."""
    state = add_processor(client, 'brompton-sx40')
    sx_card = card_ids(state)[0]
    state = add_processor(client, 'megapixel-helios-jr')
    mp_card = card_ids(state)[1]
    sc = pscreens(('BR', 2, 'brompton'), ('M1', 2, 'megapixel-1g'),
                  ('M2', 2, 'megapixel-2.5g'))
    attach(client, 'BR', sx_card, sc)
    attach(client, 'M1', mp_card, sc)
    res = attach(client, 'M2', mp_card, sc)
    assert {c for c, _p in spots(res, 'BR')} == {sx_card}
    assert {c for c, _p in spots(res, 'M1')} == {mp_card}
    assert {c for c, _p in spots(res, 'M2')} == {mp_card}
    resp = place(client, 'BR', 0, mp_card, 1,
                 pscreens(('BR', 1, 'brompton')))
    assert resp.status_code == 409
    assert 'Megapixel gear' in resp.get_json()['error']
    resp = place(client, 'M1', 0, sx_card, 1,
                 pscreens(('M1', 1, 'megapixel-1g')))
    assert resp.status_code == 409
    assert 'Brompton gear' in resp.get_json()['error']


def test_the_40g_mx_card_is_5g_gear(client):
    """The MX chassis card whose one trunk is 40G feeds the CVT8-5G and
    only the CVT8-5G, so its ports are 5GBASE-T: "mx6000 and 2000 with 5g
    fiber only work with 5g settings". The 1G COEX setting its chassis
    family would suggest is refused."""
    state = add_processor(client, 'novastar-mx2000-pro')
    pid = state['resolved'][0]['id']
    state = set_card(client, pid, 0, 'novastar-card-mx-1x40g')
    card = card_ids(state)[0]
    ok = place(client, 'FIVE', 0, card, 1,
               pscreens(('FIVE', 1, 'novastar-5g')))
    assert ok.status_code == 200, ok.get_data(as_text=True)
    resp = place(client, 'ONE', 0, card, 2,
                 pscreens(('ONE', 1, 'novastar-coex-1g')))
    assert resp.status_code == 409
    assert '5G fiber gear' in resp.get_json()['error']


def test_a_screen_with_no_platform_is_never_refused(client):
    """A payload with no platform - an old client, an old test - lands
    anywhere, because the safe side of not knowing is a warning missed,
    not a wall stranded on site."""
    state = add_processor(client, 'novastar-mx40-pro')
    card = card_ids(state)[0]
    resp = place(client, 'Wall', 0, card, 1, screens(('Wall', 1)))
    assert resp.status_code == 200, resp.get_data(as_text=True)


def test_the_card_summary_carries_the_servers_word(mixed_lines):
    """Any client-side gating reads each card's `platforms` list off the
    resolution rather than a second copy of the matrix - so the list has
    to be there, and None has to mean no restriction."""
    client, mx_card, h_card = mixed_lines
    res = presolve(client, pscreens(('LEG', 1, 'novastar-armor')))
    by_card = {c['cardId']: c for c in res['cards']}
    assert by_card[mx_card]['platforms'] == ['novastar-coex-1g']
    assert by_card[h_card]['platforms'] == ['novastar-armor']
