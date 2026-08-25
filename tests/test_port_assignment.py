"""Screens onto sending-card ports: numbering, clashes, overflow, overrides.

The rule this whole file is built to prove is that THE APP DETECTS AND OFFERS,
IT NEVER SILENTLY REARRANGES. Looms are made up and labelled off the drawing
days before anything is hung, so a numbering that changes by itself hands back
a drawing that no longer matches the truck. Almost every test below is
therefore in two halves: the problem is FOUND, and the numbering is UNCHANGED
until somebody takes the offer.

The four behaviours, and the reason each is awkward:

* AUTO-NUMBERING PACKS DENSELY IN SCREEN ORDER. Six ports takes 1-6, the next
  screen starts at 7. That is the behaviour asked for by name.
* A CLASH IS REPORTED, NOT FIXED. Both claimants keep the port. Bumping the
  loser is the silent renumber.
* A SCREEN'S PORTS NEVER SPAN TWO CARDS UNASKED. Seventeen ports on a sixteen-
  port card leaves one unplaced and says so; putting it on another card is a
  patching decision with a physical consequence and belongs to a person.
* A PIN WINS. Auto works around it and never over it, and releasing it hands
  the port straight back.

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


# ── helpers ───────────────────────────────────────────────────────────────

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
    """Cards in the order the panel draws them, which is the order auto fills
    them - processor by processor, slot 1 downward."""
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
    """One port of one screen onto one card port - the request both panels
    send, from either end of the cable."""
    body = {'layerId': layer_id, 'index': index, 'cardId': card_id,
            'port': port, 'screens': sc}
    if confirm:
        body['confirm'] = True
    return client.post('/api/port-assignments/place', json=body)


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


# ── 1. Auto-numbering ─────────────────────────────────────────────────────

def test_ports_pack_densely_in_screen_order(one_card):
    """The behaviour asked for by name: a screen needing six ports takes 1-6
    and the next one starts at 7. Screen order is the order the caller sent,
    which is project layer order - re-sorting it here would renumber a show
    behind the user's back."""
    client, _pid, card = one_card
    res = resolve(client, ('Main', 6), ('Side', 4), ('Upstage', 3))

    assert numbers(res, 'Main') == [1, 2, 3, 4, 5, 6]
    assert numbers(res, 'Side') == [7, 8, 9, 10]
    assert numbers(res, 'Upstage') == [11, 12, 13]
    assert all(c == card for c, _p in spots(res, 'Side'))
    assert sources(res, 'Main') == ['auto'] * 6
    assert res['issues'] == [], res['issues']


def test_auto_is_on_before_anybody_turns_it_on(one_card):
    """A project that has never been touched here must number itself, or the
    panel opens on a wall of blanks and every screen needs a decision before it
    says anything."""
    client, _pid, _card = one_card
    res = resolve(client, ('Main', 3))
    assert res['auto'] is True
    assert numbers(res, 'Main') == [1, 2, 3]
    # And the panel reading itself did not stamp state onto the project.
    assert assignment.STATE_KEY not in client.get('/api/project').get_json()


def test_turning_auto_off_leaves_only_what_was_pinned(two_cards):
    client, _pid, card_a, _card_b = two_cards
    resp = client.post('/api/port-assignments/pin', json={
        'layerId': 'Main', 'index': 1, 'cardId': card_a, 'port': 9,
        'screens': screens(('Main', 3)),
    })
    assert resp.status_code == 200
    resp = client.put('/api/port-assignments', json={'auto': False})
    assert resp.status_code == 200
    res = resp.get_json()['resolution']
    assert res['auto'] is False
    # Sent with no screens, so nothing resolves; ask again with them.
    res = resolve(client, ('Main', 3))
    assert numbers(res, 'Main') == [None, 9, None]
    assert 'auto-off' in kinds(res)


def test_the_card_a_screen_lands_on_is_the_first_with_room_for_all_of_it(two_cards):
    """Filling a card's last four ports with the first four of a six-port
    screen would split a run for no reason. A screen goes onto the first card
    that can hold the whole thing."""
    client, _pid, card_a, card_b = two_cards
    res = resolve(client, ('Main', 14), ('Side', 6))
    assert all(c == card_a for c, _p in spots(res, 'Main'))
    assert spots(res, 'Side') == [(card_b, n) for n in range(1, 7)]
    assert by_name(res, 'Side')['split'] is False
    assert res['issues'] == [], res['issues']


def test_a_cvt_gives_a_copy_opt_card_no_extra_ports_to_hand_out(one_card):
    """The 16xRJ45+2xfiber's OPTs copy Ethernet 1-8 and 9-16, so a breakout box
    on one is another place to plug into ports that already exist. If the model
    counted it as eight more, this card would offer 24 ports and a 20-cabinet
    wall would look like it fitted. It does not, and it must keep not fitting
    with both boxes hung on it."""
    client, pid, card = one_card
    for boxes in (0, 1, 2):
        res = resolve(client, ('Main', 17))
        assert res['cards'][0]['capacity'] == 16, (
            f'{boxes} CVTs made a 16-port card offer '
            f'{res["cards"][0]["capacity"]} ports')
        assert by_name(res, 'Main')['unplaced'] == [16], (
            'the seventeenth port found room that does not exist')
        assert 'overflow' in kinds(res)
        client.post(f'/api/processors/{pid}/cards/{card}/cvts',
                    json={'deviceId': 'novastar-cvt10'})


def test_boxes_hung_on_trunks_that_do_not_exist_hand_out_no_ports(client):
    """The panel refuses to ADD a box with no OPT left, but a project can still
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

    res = resolve(client, ('Main', 40))
    assert res['cards'][0]['capacity'] == 32, (
        'boxes on trunks that do not exist became assignable ports')
    assert numbers(res, 'Main')[:32] == list(range(1, 33))
    assert by_name(res, 'Main')['unplaced'] == list(range(32, 40))
    assert 'overflow' in kinds(res)


def test_a_card_whose_boxes_cannot_reach_its_ceiling_says_so_here_too(client):
    """Two CVT4K-S boxes on an enhanced H_4xfiber use all four OPTs and deliver
    32 of its 40. Assignment still plans against the card's 40 - which box
    delivers a port is a patching decision and can still change - but the eight
    that no box will hand out have to be said out loud on the panel that is
    handing ports to walls."""
    state = add_processor(client, 'novastar-h9')
    pid = state['resolved'][0]['id']
    state = set_card(client, pid, 0, 'novastar-card-h-4xfiber-enhanced')
    card = card_ids(state)[0]
    for _ in range(2):
        assert client.post(f'/api/processors/{pid}/cards/{card}/cvts',
                           json={'deviceId': 'novastar-cvt4k-s'}
                           ).status_code == 201

    res = resolve(client, ('Main', 40))
    assert res['cards'][0]['capacity'] == 40
    assert by_name(res, 'Main')['unplaced'] == []
    short = issue(res, 'card-short-of-its-ceiling')
    assert short['delivered'] == 32 and short['capacity'] == 40
    assert 'CVT10' in short['message']


def test_a_half_patched_card_is_not_flagged_on_the_assignment_panel(client):
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

    res = resolve(client, ('Main', 10))
    labels = [p['label'] for p in by_name(res, 'Main')['ports']]
    assert labels[:3] == ['CVT-A-1', 'CVT-A-2', 'CVT-A-3']
    assert labels[8:] == ['SR-9', 'SR-10'], (
        'ports past the box should still read off the card')
    assert numbers(res, 'Main') == list(range(1, 11)), (
        'the box changed the numbering as well as the label')


def test_a_card_with_no_settled_port_count_is_not_filled_by_auto(client):
    """The SQ200 publishes connectors and no port count. Auto-numbering onto a
    guessed ceiling would silently cap a wall, which is the failure the catalog
    exists to prevent, so it is offered to pins and to nothing else."""
    add_processor(client, 'brompton-sq200')
    res = resolve(client, ('Main', 4))
    assert numbers(res, 'Main') == [None, None, None, None]
    assert 'capacity-unknown' in kinds(res)
    assert issue(res, 'capacity-unknown')['reason']


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


def test_auto_alone_never_produces_a_clash(two_cards):
    """Two screens can only land on one port if somebody put them there. Auto
    hands out each port once, so a clash is always a pin against a pin."""
    client, _pid, _a, _b = two_cards
    res = resolve(client, ('A', 5), ('B', 5), ('C', 5), ('D', 5), ('E', 5))
    seen = [(p['cardId'], p['port']) for s in res['screens'] for p in s['ports']
            if p['cardId']]
    assert len(seen) == len(set(seen)), 'auto handed the same port out twice'
    assert 'overlap' not in kinds(res)


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
    assert numbers(resolve(client, ('Main', 4), ('Side', 4)), 'Main') == [1, 2, 3, 4]

    resp = client.post('/api/port-assignments/move-block',
                       json={'layerId': 'Main', 'screens': sc})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    res = resp.get_json()['resolution']

    # Side holds 5-8, so the next free run of four above Main's old start is
    # 9-12. Consecutive, in the same order, all four of them.
    assert numbers(res, 'Main') == [9, 10, 11, 12]
    assert numbers(res, 'Side') == [5, 6, 7, 8], "another screen's pins moved"
    assert all(c == card for c, _p in spots(res, 'Main'))


def test_auto_ports_repack_and_pinned_ones_do_not(one_card):
    """The trade-off in "packed densely", stated outright rather than left to
    be discovered on site.

    An auto port is arithmetic, not a decision: it is recomputed from scratch
    every time and it re-packs into whatever room appears, so moving one screen
    does slide another screen's AUTO ports down into the gap. That is the same
    behaviour as a screen being deleted, and it is what dense packing means.

    The way to hold a numbering is to pin it, which is the whole reason pinning
    exists, and the panel prints PINNED against every port that will not move.
    Nothing here happens quietly: the marks are on the page before the move."""
    client, _pid, card = one_card
    sc = screens(('Main', 4), ('Side', 4))
    assert numbers(resolve(client, ('Main', 4), ('Side', 4)), 'Side') == [5, 6, 7, 8]

    resp = client.post('/api/port-assignments/move-block',
                       json={'layerId': 'Main', 'screens': sc})
    assert resp.status_code == 200
    res = resp.get_json()['resolution']
    assert numbers(res, 'Side') == [1, 2, 3, 4], (
        'auto ports that could pack tighter did not')
    assert sources(res, 'Side') == ['auto'] * 4, (
        'a port that re-packed was still labelled as held')

    # Pin them and the same move leaves them exactly where they were.
    for index, port in enumerate((1, 2, 3, 4)):
        client.post('/api/port-assignments/pin', json={
            'layerId': 'Side', 'index': index, 'cardId': card, 'port': port,
            'screens': sc})
    before = numbers(resolve(client, ('Main', 4), ('Side', 4)), 'Side')
    client.post('/api/port-assignments/move-block',
                json={'layerId': 'Main', 'screens': sc})
    after = numbers(resolve(client, ('Main', 4), ('Side', 4)), 'Side')
    assert after == before == [1, 2, 3, 4]


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
    screen at the new block. Honouring its old pins would mean moving only the
    auto ports and tearing the run in two, which is what the move exists to
    prevent. Another screen's pins are obstacles and are never touched."""
    client, _pid, card = one_card
    sc = screens(('Main', 4), ('Side', 2))
    client.post('/api/port-assignments/pin', json={
        'layerId': 'Main', 'index': 2, 'cardId': card, 'port': 15, 'screens': sc})
    client.post('/api/port-assignments/pin', json={
        'layerId': 'Side', 'index': 0, 'cardId': card, 'port': 2, 'screens': sc})

    before = resolve(client, ('Main', 4), ('Side', 2))
    assert numbers(before, 'Main')[2] == 15, 'the pin did not hold'

    resp = client.post('/api/port-assignments/move-block',
                       json={'layerId': 'Main', 'screens': sc})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    res = resp.get_json()['resolution']

    main = numbers(res, 'Main')
    assert main == list(range(main[0], main[0] + 4)), (
        f'the block is not consecutive: {main}')
    assert 15 not in main or main[2] == 15
    assert sources(res, 'Main') == ['pin'] * 4, (
        'a block move must pin the whole set, or auto would undo it')
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
    before = resolve(client, ('Main', 10), ('Side', 5))
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
    assert numbers(resolve(client, ('Main', 6)), 'Main') == [1, 2, 3, 4, 5, 6]

    resp = place(client, 'Main', 2, card, 12, sc)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    res = resp.get_json()['resolution']
    assert spots(res, 'Main')[2] == (card, 12)
    assert sources(res, 'Main')[2] == 'pin'
    assert resp.get_json()['moved']['port'] == 12
    assert resp.get_json()['moved']['from'] == {'cardId': card, 'port': 3}


def test_placing_one_port_leaves_the_screens_other_ports_where_they_were(one_card):
    """The whole point of the control. Left to itself the tail of the run would
    slide down into the port that was vacated - an auto port is arithmetic and
    re-packs into whatever room appears - so one click would renumber four
    ports on a drawing. The rest of the run is held first, which is the same
    trade the block move makes and prints PINNED on the page just as loudly."""
    client, _pid, card = one_card
    sc = screens(('Main', 6),)
    before = numbers(resolve(client, ('Main', 6)), 'Main')

    resp = place(client, 'Main', 2, card, 12, sc)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    after = numbers(resp.get_json()['resolution'], 'Main')

    assert after == [1, 2, 12, 4, 5, 6], after
    assert [after[i] for i in (0, 1, 3, 4, 5)] == \
        [before[i] for i in (0, 1, 3, 4, 5)], 'a port nobody moved was renumbered'
    assert resp.get_json()['moved']['held'] == 5
    assert 'held where they were' in resp.get_json()['moved']['note']


def test_placing_one_port_leaves_another_screens_pins_alone(one_card):
    client, _pid, card = one_card
    sc = screens(('Main', 4), ('Side', 3))
    for index, port in enumerate((10, 11, 12)):
        client.post('/api/port-assignments/pin', json={
            'layerId': 'Side', 'index': index, 'cardId': card, 'port': port,
            'screens': sc})

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
    assert numbers(resolve(client, ('Main', 4), ('Side', 4)), 'Side') == [5, 6, 7, 8]

    resp = place(client, 'Side', 0, card, 2, sc)
    assert resp.status_code == 409, resp.get_data(as_text=True)
    body = resp.get_json()
    assert 'Main port 2' in body['error'], body['error']
    assert body['conflict']['port'] == 2
    assert [o['name'] for o in body['conflict']['occupants']] == ['Main']

    after = resolve(client, ('Main', 4), ('Side', 4))
    assert numbers(after, 'Main') == [1, 2, 3, 4], 'the occupant was displaced'
    assert numbers(after, 'Side') == [5, 6, 7, 8], 'the refused move happened'
    assert assignment.STATE_KEY not in client.get('/api/project').get_json(), (
        'a refused placement stamped state onto the project')


def test_the_refusal_says_which_of_the_two_things_would_happen(one_card):
    """The two outcomes are nothing like each other, so a refusal that only
    said "occupied" would be no use in choosing. An auto port gets out of the
    way, which is the same thing as saying its screen is renumbered; a pinned
    one is somebody's decision and stays, and the socket ends up claimed
    twice."""
    client, _pid, card = one_card
    sc = screens(('Main', 4), ('Side', 4))
    auto = place(client, 'Side', 0, card, 2, sc).get_json()['error']
    assert 'renumbers that screen' in auto, auto

    client.post('/api/port-assignments/pin', json={
        'layerId': 'Main', 'index': 1, 'cardId': card, 'port': 2,
        'screens': sc})
    held = place(client, 'Side', 0, card, 2, sc).get_json()['error']
    assert 'draw as a clash' in held, held


def test_confirming_over_an_auto_port_packs_it_around_and_says_so(one_card):
    """Nothing was silently rearranged: the renumbering was named in the
    refusal, agreed to, and named again in what came back."""
    client, _pid, card = one_card
    sc = screens(('Main', 4), ('Side', 4))
    assert place(client, 'Side', 0, card, 2, sc).status_code == 409

    resp = place(client, 'Side', 0, card, 2, sc, confirm=True)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    res = resp.get_json()['resolution']
    assert numbers(res, 'Side')[0] == 2
    assert numbers(res, 'Main') == [1, 3, 4, 5], 'auto did not pack around it'
    assert 'Main' in resp.get_json()['moved']['note']


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
    machines, which auto-numbering would never have chosen on its own. It is
    allowed - somebody asked - and it is said out loud, because two cards is
    two trunks to one wall."""
    client, pid, card_a = one_card
    state = set_card(client, pid, 1, 'novastar-card-h-16xrj45-2xfiber')
    card_b = card_ids(state)[1]
    sc = screens(('Main', 5),)

    resp = place(client, 'Main', 4, card_b, 1, sc)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    res = resp.get_json()['resolution']
    assert spots(res, 'Main') == [(card_a, 1), (card_a, 2), (card_a, 3),
                                  (card_a, 4), (card_b, 1)]
    assert by_name(res, 'Main')['split'] is True
    assert 'spans 2 cards' in resp.get_json()['moved']['note']


def test_a_placement_names_the_socket_it_landed_on(one_card):
    """The note is what the panel prints after the move, and a port number on
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
    assert assignment.STATE_KEY not in client.get('/api/project').get_json()


def test_a_placement_of_a_port_the_screen_does_not_have_is_refused(one_card):
    client, _pid, card = one_card
    resp = place(client, 'Main', 7, card, 1, screens(('Main', 3),))
    assert resp.status_code == 409
    assert 'no port 8' in resp.get_json()['error']


def test_a_card_with_no_settled_count_still_takes_a_placement(client):
    """"Ports can still be pinned to it by hand" is what the panel says about
    an SQ200, and this is the by-hand path. There is no ceiling to check
    against, and inventing one to check against is the failure the catalog
    exists to prevent."""
    state = add_processor(client, 'brompton-sq200')
    card = card_ids(state)[0]
    resp = place(client, 'Main', 0, card, 6, screens(('Main', 2),))
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert spots(resp.get_json()['resolution'], 'Main')[0] == (card, 6)


def test_assigning_from_the_socket_lands_where_pinning_from_the_screen_does(
        one_card):
    """The Processors panel knows a card and a port number and asks which
    screen plugs in; the assignment side knows a screen's port and asks
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
    res = resolve(client, ('Main', 17))
    assert numbers(res, 'Main')[:16] == list(range(1, 17))
    assert numbers(res, 'Main')[16] is None
    assert by_name(res, 'Main')['unplaced'] == [16]

    over = issue(res, 'overflow')
    assert over['layerId'] == 'Main'
    assert over['ports'] == [17], 'reported in the screen\'s own numbering'
    assert '17' in over['message']


def test_the_overflow_can_be_placed_on_a_different_card(two_cards):
    """A single screen's ports MAY span two cards - `.scr` stores the sending
    card per cabinet, so the format has no objection either. It just may not
    happen unasked."""
    client, _pid, card_a, card_b = two_cards
    sc = screens(('Main', 17),)
    res = resolve(client, ('Main', 17))
    offer = next(o for o in issue(res, 'overflow')['offers']
                 if o['cardId'] == card_b)
    assert offer['action'] == 'place-overflow'

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


def test_placed_overflow_survives_the_next_auto_pass(two_cards):
    """The overflow is stored as pins, so the numbering someone decided on
    stays decided when the next screen is added."""
    client, _pid, card_a, card_b = two_cards
    client.post('/api/port-assignments/place-overflow', json={
        'layerId': 'Main', 'cardId': card_b, 'screens': screens(('Main', 17))})
    res = resolve(client, ('Main', 17), ('Side', 4))
    assert spots(res, 'Main')[16] == (card_b, 1)
    assert sources(res, 'Main')[16] == 'pin'
    # The new screen works around it rather than over it.
    assert spots(res, 'Side') == [(card_b, n) for n in (2, 3, 4, 5)]


def test_an_overflow_with_no_card_anywhere_says_so(one_card):
    client, _pid, _card = one_card
    res = resolve(client, ('Main', 16), ('Side', 4))
    over = issue(res, 'overflow')
    assert over['layerId'] == 'Side'
    assert over['offers'] == [], 'a card was offered that has no free ports'
    assert 'full' in over['message']


# ── 5. Manual override, and it wins ───────────────────────────────────────

def test_auto_works_around_a_pin_and_never_over_it(one_card):
    """Pins are placed first and auto fills in around whatever is left. Auto
    cannot move a pin, only avoid it - and avoiding it leaves a gap in the run,
    which is honest about where the ports actually are."""
    client, _pid, card = one_card
    resp = client.post('/api/port-assignments/pin', json={
        'layerId': 'Side', 'index': 0, 'cardId': card, 'port': 3,
        'screens': screens(('Main', 4), ('Side', 1))})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    res = resolve(client, ('Main', 4), ('Side', 1))
    assert numbers(res, 'Side') == [3], 'the pinned port moved'
    assert sources(res, 'Side') == ['pin']
    assert numbers(res, 'Main') == [1, 2, 4, 5], (
        'auto stamped over the pin or failed to work around it')
    assert sources(res, 'Main') == ['auto'] * 4


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
    """Not just the first, and not just to the card auto chose. The port in the
    middle of a run is exactly the one somebody needs to hold when a patch was
    made up before the drawing was."""
    client, _pid, card_a, card_b = two_cards
    sc = screens(('Main', 5),)
    resp = client.post('/api/port-assignments/pin', json={
        'layerId': 'Main', 'index': 3, 'cardId': card_b, 'port': 7,
        'screens': sc})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    res = resp.get_json()['resolution']
    assert spots(res, 'Main')[3] == (card_b, 7)
    assert sources(res, 'Main') == ['auto', 'auto', 'auto', 'pin', 'auto']
    assert [c for c, _p in spots(res, 'Main')][:3] == [card_a] * 3
    assert by_name(res, 'Main')['split'] is True, (
        'a pin onto another card splits the screen and should read that way')


def test_a_pin_without_a_port_number_takes_the_cards_lowest_free_one(two_cards):
    """"Put this one on that card" is the decision; which free number it lands
    on is arithmetic. Leaving the number out is the normal case from the panel,
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
    resolve(client, ('Main', 16), ('Side', 2))
    resp = client.post('/api/port-assignments/pin', json={
        'layerId': 'Side', 'index': 0, 'cardId': card_a, 'screens': sc})
    assert resp.status_code == 409
    assert 'free' in resp.get_json()['error']


def test_which_ports_are_pinned_is_visible(one_card):
    client, _pid, card = one_card
    client.post('/api/port-assignments/pin', json={
        'layerId': 'Main', 'index': 1, 'cardId': card, 'port': 9,
        'screens': screens(('Main', 3))})
    res = resolve(client, ('Main', 3))
    assert sources(res, 'Main') == ['auto', 'pin', 'auto']


def test_releasing_a_pin_returns_the_port_to_auto(one_card):
    """There is nothing to restore, because auto was never stored - it is
    derived on every resolve, so the port simply falls back into the pack."""
    client, _pid, card = one_card
    sc = screens(('Main', 3),)
    client.post('/api/port-assignments/pin', json={
        'layerId': 'Main', 'index': 1, 'cardId': card, 'port': 9, 'screens': sc})
    assert numbers(resolve(client, ('Main', 3)), 'Main') == [1, 9, 2]

    resp = client.post('/api/port-assignments/unpin',
                       json={'layerId': 'Main', 'index': 1, 'screens': sc})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    res = resp.get_json()['resolution']
    assert numbers(res, 'Main') == [1, 2, 3]
    assert sources(res, 'Main') == ['auto'] * 3
    assert resp.get_json()['state']['pins'] == []


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
    assert numbers(res, 'Main') == [1, 2, 3]
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
    assert assignment.STATE_KEY not in client.get('/api/project').get_json()


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


def test_only_pins_and_the_auto_flag_are_stored(one_card):
    """Nothing derived is kept. Storing the auto numbering would put a stale
    copy in the file the moment a screen changed size, and the file would then
    disagree with the panel drawn beside it."""
    client, _pid, card = one_card
    client.post('/api/port-assignments/pin', json={
        'layerId': 'Main', 'index': 0, 'cardId': card, 'port': 3,
        'screens': screens(('Main', 8))})
    stored = client.get('/api/project').get_json()[assignment.STATE_KEY]
    assert set(stored) == {'auto', 'pins'}
    assert stored['pins'] == [{'layerId': 'Main', 'index': 0,
                               'cardId': card, 'port': 3}]


# ── 7. The regression bar ─────────────────────────────────────────────────

def test_a_project_with_no_processors_is_shaped_exactly_as_before(client):
    """Anyone who never opens the Data view, or defines no processor, sees no
    change - including in the file they save. Resolving must not stamp the key
    onto a project that has none, and an undefined machine is not an error to
    report at somebody, it is the default."""
    before = client.get('/api/project').get_json()
    assert 'processors' not in before
    assert assignment.STATE_KEY not in before

    res = resolve(client, ('Main', 6), ('Side', 4))
    assert res['configured'] is False
    assert res['cards'] == []
    assert res['issues'] == [], 'a project with no processors was nagged at'
    assert numbers(res, 'Main') == [None] * 6

    after = client.get('/api/project').get_json()
    assert after == before, 'merely resolving changed the project'
    assert after['is_pristine'] is True, 'a read marked the project dirty'


def test_a_refused_edit_leaves_no_state_behind(client):
    """A 409 must not be the thing that puts the key into a project. Editing
    the stored dict in place and then refusing is exactly how that happens."""
    resp = client.post('/api/port-assignments/move-block',
                       json={'layerId': 'Main', 'screens': screens(('Main', 4))})
    assert resp.status_code == 409
    project = client.get('/api/project').get_json()
    assert assignment.STATE_KEY not in project
    assert project['is_pristine'] is True


def test_a_placement_with_no_processor_leaves_the_project_alone(client):
    """There is no socket to place onto, and saying so must not be the thing
    that stamps assignment state onto a project that has none."""
    resp = client.post('/api/port-assignments/place', json={
        'layerId': 'Main', 'index': 0, 'cardId': 'cardNope', 'port': 1,
        'screens': screens(('Main', 2))})
    assert resp.status_code == 404
    project = client.get('/api/project').get_json()
    assert assignment.STATE_KEY not in project
    assert project['is_pristine'] is True


def test_releasing_a_pin_that_was_never_made_changes_nothing(client):
    resp = client.post('/api/port-assignments/unpin',
                       json={'layerId': 'Main', 'screens': screens(('Main', 2))})
    assert resp.status_code == 200
    project = client.get('/api/project').get_json()
    assert assignment.STATE_KEY not in project
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
    assert assignment.STATE_KEY not in \
        client_with_layer.get('/api/project').get_json()


def test_the_panel_ships_no_declared_fields_into_the_field_sweep():
    """tests/test_all_fields_sweep.py drives every control declared inside a
    .tab-panel straight at the selected LAYER. Assignment is project state and
    its controls are built in JS for that reason; a control declared in the
    template here would be swept and would fail for a reason that has nothing
    to do with it."""
    template = os.path.join(os.path.dirname(__file__), '..', 'src',
                            'templates', 'index.html')
    with open(template, encoding='utf-8') as fh:
        html = fh.read()
    start = html.index('<h2>Port Numbering</h2>')
    end = html.index('<h2>Port Labels</h2>')
    panel = html[start:end]
    for tag in ('<input', '<select', '<textarea'):
        assert tag not in panel, (
            f'{tag} declared in the Port Numbering panel markup - the field '
            f'sweep would drive it at the selected layer')
    assert 'id="port-assignment-issues"' in panel


# ── 8. Labels come from the one place that owns them ──────────────────────

def test_a_ports_label_is_the_one_the_catalog_derived(one_card):
    """No second implementation of "which name wins". The label on an assigned
    port is read straight off the resolved card, so naming the card renames
    every port assigned to it with no further work here."""
    client, pid, card = one_card
    resp = client.put(f'/api/processors/{pid}/cards/{card}', json={'name': 'SR'})
    assert resp.status_code == 200
    res = resolve(client, ('Main', 3))
    assert [p['label'] for p in by_name(res, 'Main')['ports']] == \
        ['SR-1', 'SR-2', 'SR-3']


def test_an_unnamed_card_gives_its_ports_no_label(one_card):
    """With nothing named upstream there is no processor-derived label, which
    leaves the per-screen templates in charge exactly as before."""
    client, _pid, _card = one_card
    res = resolve(client, ('Main', 2))
    assert [p['label'] for p in by_name(res, 'Main')['ports']] == [None, None]
    assert numbers(res, 'Main') == [1, 2], 'an unnamed card still numbers'


def test_a_card_summary_carries_the_names_its_ports_go_by(one_card):
    """A panel offering somebody a choice of sockets has to call each one what
    the box calls it. Without the names the list reads 1, 2, 3 while the card
    in the rack reads SR-1, SR-2, and the two get matched up by counting."""
    client, pid, card = one_card
    client.put(f'/api/processors/{pid}/cards/{card}', json={'name': 'SR'})
    summary = resolve(client, ('Main', 2))['cards'][0]
    assert summary['labels']['1'] == 'SR-1'
    assert summary['labels']['16'] == 'SR-16'


# ── 9. Both ends of one cable ─────────────────────────────────────────────
#
# The Port Numbering module asks "where did my ports go" and the Processors
# panel asks "what is on this socket". They are the same question from the two
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
    changed. The placement lives in the panel module (_placePort) and the
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


def test_the_per_port_rows_stay_out_of_the_panel():
    """The dock's drag is the assignment gesture, so the panel's per-port
    pin selects, movers and release buttons - and the per-screen "Move whole
    block" tools - are gone, from both panels. This pins the strip the way
    the Processors panel's stripped chooser is pinned, so the rows cannot
    quietly come back and grow a second set of assignment rules.

    (Two prior tests lived here: one held the mover's data-lrd-field keys
    for the focus guard, one held the mover's half-made choice off the DOM
    in _movingPort. Both drove UI that no longer exists - the focus guard
    itself is still exercised by the auto toggle's key below.)"""
    panel = js('app-port-assignment.js')
    for gone in ('port-move-card-', 'port-move-port-', 'port-pin-',
                 '_movingPort', 'Move whole block', 'Release all pins',
                 '_buildAssignmentScreen', '_buildAssignmentPort'):
        assert gone not in panel, (
            f'{gone!r} is back in the panel module - assignment controls '
            f'belong to the dock now')
    assert 'processor-port-assign-' not in js('app-processors.js'), (
        'the stripped chooser is back in the Processors panel')
    # What deliberately STAYS: the refuse-and-offer surface and the auto
    # toggle. The dock does not replace warnings.
    assert '_buildIssue(issue) {' in panel
    assert '_buildOffer(offer) {' in panel
    assert "dataset.lrdField = 'port-assignment-auto'" in panel


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
    res = resolve(client, ('Main', 3))
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
# auto numbers around it, a block cannot land across it, and a hand
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


def test_auto_numbering_skips_the_backing_ports(client):
    """Three ports on a sequential six land on 1, 3, 5 - the odd mains - and
    the card is full at three, because the evens are its returns."""
    _pid, card = sequential_card(client)
    sc = [('Wall', 3)]
    res = resolve(client, *sc)
    assert spots(res, 'Wall') == [(card, 1), (card, 3), (card, 5)]

    res = resolve(client, ('Wall', 4))
    assert numbers(res, 'Wall') == [1, 3, 5, None]
    assert issue(res, 'overflow')


def test_placing_onto_a_backing_port_is_refused_naming_the_main(client):
    """The refusal is hard - no confirm - and it says whose return the
    socket carries. Nothing moves and nothing is stamped on the project."""
    _pid, card = sequential_card(client)
    sc = screens(('Wall', 2))
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
    assert assignment.STATE_KEY not in client.get('/api/project').get_json()


def test_a_1to1_backup_unit_takes_nothing_and_refuses_by_role(client):
    """Every port of the designated backup unit is consumed: auto never
    reaches it, and a hand placement is refused with the main port it
    returns - the claimed-by-role treatment, unit-wide."""
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
    res = resolve(client, ('Wall', 8))
    assert spots(res, 'Wall')[:6] == [(main_card, n) for n in range(1, 7)]
    assert spots(res, 'Wall')[6:] == [(None, None), (None, None)]
    assert issue(res, 'overflow')

    resp = place(client, 'Wall', 6, backup_card, 3, screens(('Wall', 8)))
    assert resp.status_code == 409, resp.get_data(as_text=True)
    assert 'backs up P1-3' in resp.get_json()['error'], \
        resp.get_json()['error']


def test_the_card_summary_counts_backing_ports_out_of_free(client):
    """The dock's used/capacity line and the pin picker's (full) tell both
    read the summary, so a sequential card must not promise six sockets when
    three of them are spoken for by the role."""
    _pid, card = sequential_card(client)
    res = resolve(client, ('Wall', 2))
    summary = next(c for c in res['cards'] if c['cardId'] == card)
    assert summary['capacity'] == 6
    assert summary['used'] == 2
    assert summary['backing'] == 3
    assert summary['free'] == 1


def test_a_block_cannot_land_across_a_backing_port(client):
    """A block is contiguous or it is not a block, and the evens of a
    sequential card break every run of two - so the move is refused rather
    than landed astride a return socket."""
    _pid, _card = sequential_card(client)
    sc = screens(('Wall', 2))
    resolve(client, ('Wall', 2))
    resp = client.post('/api/port-assignments/move-block',
                       json={'layerId': 'Wall', 'screens': sc})
    assert resp.status_code == 409, resp.get_data(as_text=True)
    assert 'consecutive free ports' in resp.get_json()['error']
