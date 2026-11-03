"""The processor's capacity reads usable ports, with the backups beside them.

The owner's ruling (2026-11-03), off an MX6000 Pro whose second card backs
up its first: the processor's header read "80 / 80 ports"; it reads
"40 / 40 ports · 40 backup". Every redundancy shape that consumes ports
counts the same way - a 1:1 backup card, a port shape's returns (halves,
sequential), a loop or backup box - because all of them land on the one
`backsUp` link, which processor_catalog._count_backup_ports counts into
`backupCount` on each resolved card and processor. The gear's capacity rows
take it off both sides (app-processors.js _buildCapacityRow).

The same ruling, Per card (beta.4): a card that is another card's 1:1
backup offers no "backed up by…" pick - its row reads "backs up Card 1" -
and no partner pick offers a card that already backs up another.

Run locally:
    python -m pytest tests/test_processor_usable_ports.py -q
"""

import pytest

H9 = 'novastar-h9'
CARD16 = 'novastar-card-h-16xrj45-2xfiber'


def _ok(resp):
    assert resp.status_code in (200, 201), resp.get_data(as_text=True)
    return resp.get_json()


def _chassis(client, cards):
    state = _ok(client.post('/api/processors', json={'deviceId': H9}))
    pid = state['resolved'][-1]['id']
    for i, device_id in enumerate(cards):
        state = _ok(client.put(f'/api/processors/{pid}/slots/{i}',
                               json={'deviceId': device_id}))
    proc = next(p for p in state['resolved'] if p['id'] == pid)
    return pid, [s['card']['id'] for s in proc['slots'] if s['card']]


def _proc(state, pid):
    return next(p for p in state['resolved'] if p['id'] == pid)


def _counts(proc):
    return (proc['defined'], proc['ceiling'], proc['backupCount'],
            [s['card']['backupCount'] for s in proc['slots'] if s['card']])


def test_no_redundancy_counts_no_backup(client):
    pid, _ids = _chassis(client, [CARD16, CARD16])
    state = _ok(client.get('/api/processors'))
    assert _counts(_proc(state, pid)) == (32, 32, 0, [0, 0])


def test_a_one_to_one_backup_card_is_all_backup(client):
    pid, (c1, c2) = _chassis(client, [CARD16, CARD16])
    _ok(client.put(f'/api/processors/{pid}', json={'redundancy': True}))
    state = _ok(client.put(f'/api/processors/{pid}/cards/{c1}',
                           json={'backupCardId': c2}))
    assert _counts(_proc(state, pid)) == (32, 32, 16, [0, 16])


@pytest.mark.parametrize('shape', ['halves', 'sequential'])
def test_a_port_shape_counts_its_returns(client, shape):
    pid, _ids = _chassis(client, [CARD16])
    state = _ok(client.put(f'/api/processors/{pid}', json={
        'redundancy': True, 'cardsRedundancyMode': shape}))
    assert _counts(_proc(state, pid)) == (16, 16, 8, [8])


def test_a_loop_pair_counts_its_far_boxes(client):
    """An SX40's loops, A to B and C to D: B and D carry the returns."""
    state = _ok(client.post('/api/processors', json={'deviceId': 'brompton-sx40'}))
    pid = state['resolved'][-1]['id']
    state = _ok(client.put(f'/api/processors/{pid}', json={'redundancy': True}))
    assert _counts(_proc(state, pid)) == (40, 40, 20, [20])
