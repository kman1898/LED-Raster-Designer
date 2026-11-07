"""MIXED redundancy on one processor: the server side.

The owner (2026-10-29): "sometimes on say H series i have 3 16 port cards.
and i want card 1 and 2 to be primary and backup but then card 3 i want
port level backup." Offered three ways to reach it, he chose: "i want to
leave the bar. so i think adding mixed makes the most sense." So a
chassis's bar is Off · Per card · Per port · Mixed, and under Mixed each
card picks its own kind - 1:1 onto a partner card, or a port shape of its
own - through the card's own route.

What the server holds for it, and what these tests pin:

* the cards' kinds are what they always were - each card's redundancyMode
  and backupCardId - so a mixed chassis needs no new card field, and one
  saved before Mixed existed is already mixed;
* the bar's Mixed PICK is one processor field, `redundancyMixed: true`,
  stored only as True, only with redundancy on, only on a chassis with
  more than one slot (no vendor-fixed pairing), and resolved back as a
  boolean - so the bar can stay on Mixed while the cards happen to agree;
* Per card / Per port (cardsRedundancyMode) and Off drop the pick;
* a per-card write may carry the pick (a Mixed row's write keeps the bar
  at Mixed) and still writes only its own card;
* it rides the project through save, undo/redo and file open, held to its
  shape at that funnel;
* everything downstream reads per card: the port assignment of a chassis
  with cards 1+2 at 1:1 and card 3 at halves, then at sequential.

The browser half (the bar, the rows, the pills, the binder, the pull
sheet) is tests/test_mixed_redundancy_ui.py.

Run locally:
    python -m pytest tests/test_mixed_redundancy.py -q
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import processor_catalog as catalog  # noqa: E402

CARD16 = 'novastar-card-h-16xrj45-2xfiber'


@pytest.fixture(scope="module", autouse=True)
def _guard(flask_project_guard):
    """Every test builds its own project through `client`, which swaps the
    module-global the live e2e server also serves; the guard hands the
    project back the way this module found it (see conftest)."""


# ── helpers ───────────────────────────────────────────────────────────────

def add_chassis(client, cards=(CARD16,) * 3, device='novastar-h9'):
    resp = client.post('/api/processors', json={'deviceId': device})
    assert resp.status_code == 201, resp.get_data(as_text=True)
    pid = resp.get_json()['resolved'][-1]['id']
    for index, card in enumerate(cards):
        resp = client.put(f'/api/processors/{pid}/slots/{index}',
                          json={'deviceId': card})
        assert resp.status_code == 200, resp.get_data(as_text=True)
    return pid


def state(client):
    return client.get('/api/processors').get_json()


def stored(client, pid):
    return next(p for p in state(client)['processors'] if p['id'] == pid)


def resolved(client, pid):
    return next(p for p in state(client)['resolved'] if p['id'] == pid)


def cards_of(client, pid):
    return [s['card'] for s in stored(client, pid)['slots'] if s.get('card')]


def rcards(client, pid):
    return [s['card'] for s in resolved(client, pid)['slots'] if s.get('card')]


def put_proc(client, pid, body):
    return client.put(f'/api/processors/{pid}', json=body)


def put_card(client, pid, cid, body):
    return client.put(f'/api/processors/{pid}/cards/{cid}', json=body)


def mixed_chassis(client, third='halves', name=True):
    """The owner's H9: three 16-port cards, card 1 backed 1:1 by card 2,
    card 3 in a port shape of its own (`third`)."""
    pid = add_chassis(client)
    c1, c2, c3 = [c['id'] for c in cards_of(client, pid)]
    if name:
        for cid, n in ((c1, 'P1'), (c2, 'P2'), (c3, 'P3')):
            assert put_card(client, pid, cid, {'name': n}).status_code == 200
    assert put_proc(client, pid, {'redundancy': True,
                                  'redundancyMixed': True}).status_code == 200
    resp = put_card(client, pid, c1, {'backupCardId': c2,
                                      'redundancyMixed': True})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    resp = put_card(client, pid, c3, {'redundancyMode': third,
                                      'redundancyMixed': True})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return pid, (c1, c2, c3)


# ── 1. The flag: stored, returned, refused where there is nothing to mix ──

def test_the_mixed_pick_is_stored_and_returned_and_changes_no_card(client):
    """Mixed from a uniform level changes no card, only the pick: the
    stored processor carries `redundancyMixed: true`, the resolved one
    reads it back as a boolean, and every card's mode and partner stand
    exactly as they were."""
    pid = add_chassis(client)
    assert put_proc(client, pid, {'redundancy': True}).status_code == 200
    before = cards_of(client, pid)
    assert resolved(client, pid)['redundancyMixed'] is False
    assert 'redundancyMixed' not in stored(client, pid)

    resp = put_proc(client, pid, {'redundancy': True, 'redundancyMixed': True})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert stored(client, pid)['redundancyMixed'] is True
    assert resolved(client, pid)['redundancyMixed'] is True
    assert cards_of(client, pid) == before, 'Mixed moved a card'

    # Cleared: no key left behind, never a stored False.
    assert put_proc(client, pid, {'redundancyMixed': False}).status_code == 200
    assert 'redundancyMixed' not in stored(client, pid)
    assert resolved(client, pid)['redundancyMixed'] is False


def test_mixed_from_off_turns_redundancy_on_in_the_same_write(client):
    pid = add_chassis(client)
    resp = put_proc(client, pid, {'redundancy': True, 'redundancyMixed': True})
    assert resp.status_code == 200
    proc = resolved(client, pid)
    assert proc['redundancy'] is True and proc['redundancyMixed'] is True


def test_the_pick_is_refused_where_there_is_nothing_to_mix(client):
    """A standalone unit is its one card; a vendor-fixed pairing has no
    kind to pick; a value that is not a boolean is not a pick. Each is
    refused with its reason and nothing in the body is written."""
    resp = client.post('/api/processors', json={'deviceId': 'novastar-mx20'})
    mx = resp.get_json()['resolved'][-1]['id']
    resp = put_proc(client, mx, {'redundancy': True, 'redundancyMixed': True})
    assert resp.status_code == 400
    assert 'Mixed is for a chassis' in resp.get_json()['error']
    assert not stored(client, mx).get('redundancy'), (
        'a refused pick still applied the rest of the body')

    resp = client.post('/api/processors', json={'deviceId': 'brompton-sx40'})
    sx = resp.get_json()['resolved'][-1]['id']
    resp = put_proc(client, sx, {'redundancy': True, 'redundancyMixed': True})
    assert resp.status_code == 400
    assert 'redundancyMixed' not in stored(client, sx)

    pid = add_chassis(client)
    resp = put_proc(client, pid, {'redundancy': True, 'redundancyMixed': 'yes'})
    assert resp.status_code == 400
    assert 'true or false' in resp.get_json()['error']
    assert 'redundancyMixed' not in stored(client, pid)


def test_the_catalog_refusal_names_each_case():
    assert catalog.mixed_redundancy_refusal(
        {'deviceId': 'novastar-h9', 'slots': [{'index': 0}, {'index': 1}]}) is None
    assert 'one unit' in catalog.mixed_redundancy_refusal(
        {'deviceId': 'novastar-mx20', 'slots': [{'index': 0}]})
    assert 'pairs its outputs itself' in catalog.mixed_redundancy_refusal(
        {'deviceId': 'brompton-sq200', 'slots': [{'index': 0}, {'index': 1}]})


# ── 2. Per card, Per port and Off let go of it ───────────────────────────

def test_per_card_and_per_port_convert_every_card_and_drop_the_pick(client):
    """From Mixed, Per card and Per port convert every card exactly as
    they always did - one write, every card the same - and the pick goes
    with them, so the bar reads the level they wrote."""
    pid, (c1, c2, c3) = mixed_chassis(client)
    resp = put_proc(client, pid, {'redundancy': True,
                                  'cardsRedundancyMode': 'sequential'})
    assert resp.status_code == 200
    assert [c.get('redundancyMode') for c in cards_of(client, pid)] == \
        ['sequential'] * 3
    assert 'redundancyMixed' not in stored(client, pid)

    assert put_proc(client, pid, {'redundancyMixed': True}).status_code == 200
    resp = put_proc(client, pid, {'redundancy': True,
                                  'cardsRedundancyMode': '1to1'})
    assert resp.status_code == 200
    assert all('redundancyMode' not in c for c in cards_of(client, pid))
    assert 'redundancyMixed' not in stored(client, pid)
    # the stored partner survived underneath, as it always has
    assert cards_of(client, pid)[0]['backupCardId'] == c2


def test_off_drops_the_pick(client):
    pid, _cards = mixed_chassis(client)
    assert put_proc(client, pid, {'redundancy': False}).status_code == 200
    assert 'redundancyMixed' not in stored(client, pid)
    assert resolved(client, pid)['redundancyMixed'] is False


# ── 3. A Mixed row writes only its own card ──────────────────────────────

def test_a_row_write_touches_only_its_card_and_keeps_the_pick(client):
    """The per-card route with `redundancyMixed: true` writes that card's
    mode or partner and nothing else: the other cards' stored records are
    byte-for-byte what they were, and the processor stays at Mixed."""
    pid, (c1, c2, c3) = mixed_chassis(client)
    before = {c['id']: c for c in cards_of(client, pid)}
    resp = put_card(client, pid, c3, {'redundancyMode': 'sequential',
                                      'redundancyMixed': True})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    after = {c['id']: c for c in cards_of(client, pid)}
    assert after[c1] == before[c1] and after[c2] == before[c2]
    assert after[c3]['redundancyMode'] == 'sequential'
    assert stored(client, pid)['redundancyMixed'] is True

    # A row write that leaves the cards agreeing (card 3 back to 1:1)
    # still holds the bar at Mixed - the pick is what remembers it.
    resp = put_card(client, pid, c3, {'redundancyMode': '1to1',
                                      'redundancyMixed': True})
    assert resp.status_code == 200
    assert all('redundancyMode' not in c for c in cards_of(client, pid))
    assert resolved(client, pid)['redundancyMixed'] is True


def test_a_row_write_is_refused_whole_where_the_partner_cannot_mirror(client):
    """The Mixed row's partner pick is held to the same rules Per card's
    is: a 20-port card cannot mirror a 16-port one, the reason names both
    counts, and nothing is written."""
    pid = add_chassis(client, cards=(CARD16, CARD16, 'novastar-card-h-20xrj45'))
    c1, _c2, c3 = [c['id'] for c in cards_of(client, pid)]
    put_proc(client, pid, {'redundancy': True, 'redundancyMixed': True})
    resp = put_card(client, pid, c1, {'backupCardId': c3,
                                      'redundancyMixed': True})
    assert resp.status_code == 400
    assert 'counts must match' in resp.get_json()['error']
    assert 'backupCardId' not in cards_of(client, pid)[0]


def test_a_row_write_on_a_unit_that_cannot_mix_is_refused(client):
    resp = client.post('/api/processors', json={'deviceId': 'novastar-mx20'})
    proc = resp.get_json()['resolved'][-1]
    cid = proc['slots'][0]['card']['id']
    put_proc(client, proc['id'], {'redundancy': True})
    resp = put_card(client, proc['id'], cid, {'redundancyMode': 'halves',
                                              'redundancyMixed': True})
    assert resp.status_code == 400
    assert 'redundancyMode' not in cards_of(client, proc['id'])[0], (
        'a refused row write still stored the mode')


# ── 4. Save, undo/redo, file open ────────────────────────────────────────

def test_a_mixed_chassis_round_trips_and_keeps_its_pick(client):
    """The project file carries the pick and every card's own kind; the
    load path undo/redo and file open share (PUT /api/project) and a save
    (POST) both bring it back as it was."""
    pid, (c1, c2, c3) = mixed_chassis(client)
    saved = client.get('/api/project').get_json()
    raw = next(p for p in saved['processors'] if p['id'] == pid)
    assert raw['redundancyMixed'] is True

    assert client.post('/api/project', json=saved).status_code == 200
    assert client.put('/api/project', json=saved).status_code == 200
    proc = resolved(client, pid)
    assert proc['redundancyMixed'] is True
    cards = rcards(client, pid)
    assert [c['redundancyShape']['mode'] for c in cards] == \
        ['1to1', '1to1', 'halves']
    assert cards[0]['backupCardId'] == c2
    assert cards[1]['backupFor']['cardId'] == c1


def test_undo_and_redo_restore_the_pick(client):
    """Undo is a whole-project restore of the snapshot before the edit,
    redo of the one after: the pick comes and goes with them."""
    pid = add_chassis(client)
    put_proc(client, pid, {'redundancy': True})
    before = client.get('/api/project').get_json()
    put_proc(client, pid, {'redundancyMixed': True})
    after = client.get('/api/project').get_json()

    assert client.put('/api/project', json=before).status_code == 200   # undo
    assert resolved(client, pid)['redundancyMixed'] is False
    assert 'redundancyMixed' not in stored(client, pid)
    assert client.put('/api/project', json=after).status_code == 200    # redo
    assert resolved(client, pid)['redundancyMixed'] is True


def test_a_mixed_chassis_from_an_older_show_opens_unchanged(client):
    """A show saved before Mixed existed, with card 1 at 1:1 onto card 2
    and card 3 in halves, carries no pick - and loads exactly as it was:
    no card reset to sequential, no pick invented (the bar reads Mixed
    from the cards themselves)."""
    pid, (c1, c2, c3) = mixed_chassis(client)
    saved = client.get('/api/project').get_json()
    raw = next(p for p in saved['processors'] if p['id'] == pid)
    raw.pop('redundancyMixed')
    assert client.put('/api/project', json=saved).status_code == 200
    assert 'redundancyMixed' not in stored(client, pid)
    assert [c.get('redundancyMode') for c in cards_of(client, pid)] == \
        [None, None, 'halves']
    assert cards_of(client, pid)[0]['backupCardId'] == c2


def test_the_funnel_holds_the_pick_to_its_shape(client):
    """A hand-edited file: a pick that is not True, a pick with redundancy
    off, a pick on a standalone unit - each is dropped where the project
    enters server state, and a good one is kept. Idempotent."""
    pid = add_chassis(client)
    put_proc(client, pid, {'redundancy': True})
    resp = client.post('/api/processors', json={'deviceId': 'novastar-mx20'})
    mx = resp.get_json()['resolved'][-1]['id']
    off = add_chassis(client)
    keep = add_chassis(client)
    put_proc(client, keep, {'redundancy': True, 'redundancyMixed': True})
    saved = client.get('/api/project').get_json()
    by_id = {p['id']: p for p in saved['processors']}
    by_id[pid]['redundancyMixed'] = 'yes'
    by_id[mx]['redundancy'] = True
    by_id[mx]['redundancyMixed'] = True
    by_id[off]['redundancyMixed'] = True
    for _ in range(2):
        assert client.put('/api/project', json=saved).status_code == 200
        procs = {p['id']: p for p in state(client)['processors']}
        assert 'redundancyMixed' not in procs[pid]
        assert 'redundancyMixed' not in procs[mx]
        assert 'redundancyMixed' not in procs[off]
        assert procs[keep]['redundancyMixed'] is True
        saved = client.get('/api/project').get_json()


# ── 5. Downstream reads per card: the resolution and the port assignment ──

def _numbers(res, name):
    return [p['port'] for p in
            next(s for s in res['screens'] if s['layerId'] == name)['ports']]


def _attach(client, layer_id, card_id, count):
    sc = [{'layerId': layer_id, 'name': layer_id, 'ports': count}]
    resp = client.post('/api/port-assignments/place-overflow',
                       json={'layerId': layer_id, 'cardId': card_id,
                             'screens': sc})
    return resp


@pytest.mark.parametrize('third,mains,returns', [
    ('halves', list(range(1, 9)), {n: n + 8 for n in range(1, 9)}),
    ('sequential', list(range(1, 17, 2)), {n: n + 1 for n in range(1, 17, 2)}),
])
def test_each_card_resolves_its_own_kind_on_one_chassis(client, third, mains,
                                                        returns):
    """Card 1's sixteen ports return on card 2's same sixteen; card 2 is
    consumed whole as card 1's backup; card 3's ports pair inside it -
    port N on N+8 in halves, on N+1 in sequential. Nothing is read per
    processor."""
    pid, (c1, c2, c3) = mixed_chassis(client, third=third)
    cards = {c['id']: c for c in rcards(client, pid)}
    one = {p['number']: p for p in cards[c1]['ports']}
    assert all(one[n]['backedBy']['cardId'] == c2
               and one[n]['backedBy']['port'] == n for n in range(1, 17))
    assert cards[c2]['backupFor']['cardId'] == c1
    assert all(p.get('backsUp') for p in cards[c2]['ports'])
    three = {p['number']: p for p in cards[c3]['ports']}
    for main, ret in returns.items():
        assert three[main]['backedBy']['cardId'] == c3, (main, three[main])
        assert three[main]['backedBy']['port'] == ret
        assert three[ret]['backsUp']['port'] == main
    assert cards[c3]['redundancyShape']['mode'] == third


@pytest.mark.parametrize('third,expect', [
    ('halves', list(range(1, 9)) + [None, None]),
    ('sequential', list(range(1, 17, 2)) + [None, None]),
])
def test_the_port_assignment_reads_each_card_of_a_mixed_chassis(
        client, third, expect):
    """The fill on a mixed chassis: a wall on card 1 takes all sixteen
    ports (its returns ride card 2), card 2 has no free port at all (it is
    card 1's backup), and a wall on card 3 takes only the mains its own
    shape leaves - the front half in halves, the odd ports in
    sequential."""
    pid, (c1, c2, c3) = mixed_chassis(client, third=third)
    resp = _attach(client, 'WALL', c1, 16)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _numbers(resp.get_json()['resolution'], 'WALL') == list(range(1, 17))
    resp = _attach(client, 'BACK', c2, 2)
    assert resp.status_code == 409, 'a wall landed on the backup card'
    assert 'no free ports' in resp.get_json()['error']
    resp = _attach(client, 'SOLO', c3, 10)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _numbers(resp.get_json()['resolution'], 'SOLO') == expect
