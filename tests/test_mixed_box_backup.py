"""A backup box on a copy OPT backs up its primaries port by port.

The owner, 2026-11-02, on the shapes the one-to-one binding left alone (a
CVT4K-S on two copy OPTs behind two CVT10s, two CVT10s on copy OPTs behind
one CVT4K-S): "pair port by port". The backup box's sockets back up the same
port numbers on whichever primary boxes carry them, each socket numbered with
the port it backs up; a backup port never adds to the card's or processor's
port count; both boxes stay on the pull sheet. resolve_card derives the map
every resolve (`backsUpPorts` on the backup box, `backedUpBy` on each
primary) and stores nothing, so a saved show opens bound and undo follows.

Only products whose catalog mode carries a sourced `copyTrunks` take part:
the enhanced H_4xfiber in Backup, the MX40 Pro in 20-port and the NovaPro
UHD Jr (per box, Backup by default) are the shapes the owner's audit named.

The owner, 2026-11-02, again: "you could use 16 ports on processor and then
opt 3/4 for 16 ports of backup/copy". Where a unit has Ethernet ports of its
own (never a box-fed card), a port no box on a primary OPT carries is the
unit's own port, and a backup box on the copy OPT backs that up (boxId None,
the card's `ownBackedUpBy`). A box goes straight onto a free copy OPT with
`trunk` on the add (the card's `copyTrunksOpen`).
"""
import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import processor_catalog as catalog  # noqa: E402

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


H4E = 'novastar-card-h-4xfiber-enhanced'
MX40 = 'novastar-mx40-pro'
UHD_JR = 'novastar-novapro-uhd-jr'
CVT10 = 'novastar-cvt10'
CVT4K = 'novastar-cvt4k-s'


def _ok(resp):
    assert resp.status_code in (200, 201), resp.get_data(as_text=True)
    return resp.get_json()


def rig(client, unit, mode=None):
    device = catalog.get_device(unit)
    proc_id = 'novastar-h9' if device['kind'] == 'card' else unit
    st = _ok(client.post('/api/processors', json={'deviceId': proc_id}))
    pid = st['processors'][-1]['id']
    if device['kind'] == 'card':
        st = _ok(client.put(f'/api/processors/{pid}/slots/0',
                            json={'deviceId': unit}))
    cid = next(p for p in st['processors'] if p['id'] == pid
               )['slots'][0]['card']['id']
    if mode:
        set_mode(client, pid, cid, mode)
    return pid, cid


def set_mode(client, pid, cid, mode):
    _ok(client.put(f'/api/processors/{pid}/cards/{cid}', json={'mode': mode}))


def add_boxes(client, pid, cid, boxes):
    for device in boxes:
        _ok(client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                        json={'deviceId': device, 'pair': False}))


def add_on_copy(client, pid, cid, device, trunk, **body):
    return client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                       json=dict({'deviceId': device, 'trunk': trunk}, **body))


def card_of(client, cid):
    for proc in client.get('/api/processors').get_json()['resolved']:
        for slot in proc['slots']:
            if slot['card'] and slot['card']['id'] == cid:
                return slot['card']
    raise AssertionError(f'no card {cid}')


def mapping(card):
    """{backup box's OPTs: [(port, its socket, primary's OPTs, primary's
    own number)]} for every box backing anything up."""
    title = {b['id']: b['trunkTitle'] for b in card['cvts']}
    title[None] = 'own'
    return {b['trunkTitle']: [(m['number'], m['socket'], title[m['boxId']],
                               m['local']) for m in b['backsUpPorts']]
            for b in card['cvts'] if b['backsUpPorts']}


def backed_by(card):
    title = {b['id']: b['trunkTitle'] for b in card['cvts']}
    return {b['trunkTitle']: [title[i] for i in b['backedUpBy']]
            for b in card['cvts'] if b['backedUpBy']}


def run(numbers, primary, local_first, socket_first=None):
    """Consecutive card ports on one primary box."""
    numbers = list(numbers)
    first = numbers[0]
    return [(n, n - first + (socket_first or first), primary,
             n - first + local_first) for n in numbers]


# (id, unit, backup mode, other mode, boxes in add order, map, count)
# A CVT4K-S gives 8 outputs an OPT input (owner, 2026-11-02: "Much the same
# if you use a CVT 4K with a VX1000, which does 10 ports, you can only use
# eight of them"), so on the 10-port OPTs of an enhanced H_4xfiber or an
# MX40 Pro it carries 1-8 and 11-18, its sockets 1-8 and 9-16.
SHAPES = [
    # 1. a CVT4K-S on OPT 5-6 behind CVT10s on OPT 1 and 2
    ('h4e-cvt4k-behind-cvt10s', H4E, 'backup', 'copy',
     [CVT10] * 4 + [CVT4K],
     {'OPT 5-6': run(range(1, 9), 'OPT 1', 1)
      + run(range(11, 19), 'OPT 2', 1, socket_first=9)}, 40),
    # 2. CVT10s on OPT 5 and 6 behind a CVT4K-S on OPT 1-2
    ('h4e-cvt10s-behind-cvt4k', H4E, 'backup', 'copy',
     [CVT4K, CVT4K, CVT10, CVT10],
     {'OPT 5': run(range(1, 9), 'OPT 1-2', 1),
      'OPT 6': run(range(11, 19), 'OPT 1-2', 9, socket_first=1)}, 32),
    # 3. a CVT4K-S on OPT 3-4 behind CVT10s on OPT 1 and 2 (8 each)
    ('uhdjr-cvt4k-behind-cvt10s', UHD_JR, None, None,
     [CVT10, CVT10, CVT4K],
     {'OPT 3-4': run(range(1, 9), 'OPT 1', 1)
      + run(range(9, 17), 'OPT 2', 1)}, 16),
    # 4. CVT10s on OPT 3 and 4 behind a CVT4K-S on OPT 1-2
    ('uhdjr-cvt10s-behind-cvt4k', UHD_JR, None, None,
     [CVT4K, CVT10, CVT10],
     {'OPT 3': run(range(1, 9), 'OPT 1-2', 1),
      'OPT 4': run(range(9, 17), 'OPT 1-2', 9, socket_first=1)}, 16),
    # 5. the MX40 Pro 20-port, the same two shapes
    ('mx40-cvt4k-behind-cvt10s', MX40, '20-port', '40-port',
     [CVT10, CVT10, CVT4K],
     {'OPT 3-4': run(range(1, 9), 'OPT 1', 1)
      + run(range(11, 19), 'OPT 2', 1, socket_first=9)}, 20),
    # ...where ports 9-10 and 19-20, on no box, are the MX40 Pro's own
    # RJ45s, and each CVT10's sockets 9-10 back those up
    ('mx40-cvt10s-behind-cvt4k', MX40, '20-port', '40-port',
     [CVT4K, CVT10, CVT10],
     {'OPT 3': run(range(1, 9), 'OPT 1-2', 1)
      + run(range(9, 11), 'own', 9),
      'OPT 4': run(range(11, 19), 'OPT 1-2', 9, socket_first=1)
      + run(range(19, 21), 'own', 19, socket_first=9)}, 20),
]
IDS = [s[0] for s in SHAPES]
PARAMS = 'name,unit,mode,other,boxes,expected,count'


def _expected_backed_by(expected):
    out = {}
    for backup, rows in expected.items():
        for _n, _s, primary, _l in rows:
            if backup not in out.setdefault(primary, []):
                out[primary].append(backup)
    return out


def _own_backed_by(card):
    title = {b['id']: b['trunkTitle'] for b in card['cvts']}
    return [title[i] for i in card['ownBackedUpBy']]


def _check(card, expected, count):
    assert mapping(card) == expected
    want = _expected_backed_by(expected)
    assert _own_backed_by(card) == want.pop('own', [])
    assert backed_by(card) == want
    # the one-to-one pair stays for boxes on the same OPTs only
    assert not any(b['backupOf'] for b in card['cvts'])
    # A backup port never adds to the count: the primaries' ports only.
    primaries = [p for p in card['ports'] if not p['mirrorOf']]
    assert card['ceiling'] == count, card['ceiling']
    assert card['defined'] == count, card['defined']
    assert len(primaries) == count
    backups = {b['id'] for b in card['cvts'] if b['copyRole'] == 'backup'}
    assert not any(p['cvtId'] in backups for p in card['ports'])
    # ...and a backup box lists exactly the ports it backs up
    for box in card['cvts']:
        if box['id'] in backups:
            assert [p['number'] for p in box['ports']] \
                == [m['number'] for m in box['backsUpPorts']]


@pytest.mark.parametrize(PARAMS, SHAPES, ids=IDS)
def test_the_backup_box_backs_up_port_by_port(client, name, unit, mode, other,
                                              boxes, expected, count):
    pid, cid = rig(client, unit, mode)
    add_boxes(client, pid, cid, boxes)
    _check(card_of(client, cid), expected, count)


def test_ports_only_a_backup_box_reaches_are_not_counted(client):
    """The audit's case 2: CVT10s on OPT 5 and 6 behind CVT4K-S boxes on
    OPT 1-2 and 3-4. Ports only the backups reached used to count, and the
    card read 36. The primaries carry 32, 8 off each OPT."""
    pid, cid = rig(client, H4E, 'backup')
    add_boxes(client, pid, cid, [CVT4K, CVT4K, CVT10, CVT10])
    card = card_of(client, cid)
    assert card['ceiling'] == 32, card['ceiling']
    assert card['defined'] == 32, card['defined']
    numbers = [p['number'] for p in card['ports']]
    assert numbers == [n for b in (0, 10, 20, 30)
                       for n in range(b + 1, b + 9)], numbers
    assert sum(1 for p in card['ports'] if not p['mirrorOf']) == 32


def test_the_mx40_pros_own_ports_past_the_primary_box_stay_its_own(client):
    """MX40 Pro, CVT4K-S on OPT 1-2 (1-8 and 11-18): ports 9-10 and 19-20
    are its own RJ45s, not the backup boxes' - those back them up on their
    sockets 9-10 - and they are no box's ports."""
    pid, cid = rig(client, MX40, '20-port')
    add_boxes(client, pid, cid, [CVT4K, CVT10, CVT10])
    card = card_of(client, cid)
    face = [p['number'] for p in card['ports'] if not p['cvtId']]
    assert face == [9, 10, 19, 20]


@pytest.mark.parametrize(PARAMS, SHAPES, ids=IDS)
def test_a_saved_show_opens_bound_and_undo_follows(client, name, unit, mode,
                                                   other, boxes, expected,
                                                   count):
    """Nothing is stored: a delete frees the backup's sockets for that
    primary, and the whole-project PUT (undo, or opening the file) brings
    the map back."""
    pid, cid = rig(client, unit, mode)
    add_boxes(client, pid, cid, boxes)
    before = client.get('/api/project').get_json()
    raw = next(s['card'] for p in before['processors'] for s in p['slots']
               if s.get('card') and s['card']['id'] == cid)
    assert not any('backsUpPorts' in b or 'backedUpBy' in b
                   for b in raw['cvts'])
    first = next(b for b in card_of(client, cid)['cvts']
                 if b['trunkIndex'] == 0)
    _ok(client.delete(f'/api/processors/{pid}/cvts/{first["id"]}'))
    card = card_of(client, cid)
    assert not any(m['boxId'] == first['id']
                   for b in card['cvts'] for m in b['backsUpPorts'])
    _ok(client.put('/api/project', json=copy.deepcopy(before)))
    _check(card_of(client, cid), expected, count)


@pytest.mark.parametrize(PARAMS, SHAPES, ids=IDS)
def test_switching_away_and_back(client, name, unit, mode, other, boxes,
                                 expected, count):
    """Out of Backup (the card's other mode, or each copy box set to Mirror
    where the box picks) nothing backs anything up; back, the map returns."""
    pid, cid = rig(client, unit, mode)
    add_boxes(client, pid, cid, boxes)
    copies = [b['id'] for b in card_of(client, cid)['cvts'] if b['copyRole']]
    if other:
        set_mode(client, pid, cid, other)
    else:
        for box_id in copies:
            _ok(client.put(f'/api/processors/{pid}/cvts/{box_id}',
                           json={'copyRole': 'mirror'}))
    card = card_of(client, cid)
    assert not any(b['backsUpPorts'] or b['backedUpBy'] for b in card['cvts'])
    assert not card['ownBackedUpBy']
    if other:
        set_mode(client, pid, cid, mode)
    else:
        for box_id in copies:
            _ok(client.put(f'/api/processors/{pid}/cvts/{box_id}',
                           json={'copyRole': 'backup'}))
    _check(card_of(client, cid), expected, count)


def test_a_one_to_one_pair_is_mapped_too_and_keeps_backup_of(client):
    pid, cid = rig(client, H4E, 'backup')
    add_boxes(client, pid, cid, [CVT10, CVT10, CVT10, CVT10, CVT10])
    card = card_of(client, cid)
    far = next(b for b in card['cvts'] if b['trunkTitle'] == 'OPT 5')
    near = next(b for b in card['cvts'] if b['trunkTitle'] == 'OPT 1')
    assert far['backupOf'] == near['id']
    assert mapping(card) == {'OPT 5': run(range(1, 11), 'OPT 1', 1)}
    assert near['backedUpBy'] == [far['id']]


# ── the unit's own ports as the primaries ─────────────────────────────────

VX1000_PRO = 'novastar-vx1000-pro'


def _own_ports(card):
    return [p['number'] for p in card['ports'] if not p['mirrorOf']]


# (id, unit, mode, box, trunk, OPTs, ports backed up, count)
OWN = [
    ('uhdjr-cvt4k-opt3-4', UHD_JR, None, CVT4K, 2, 'OPT 3-4',
     range(1, 17), 16),
    ('mx40-cvt4k-opt3-4', MX40, '20-port', CVT4K, 2, 'OPT 3-4',
     [*range(1, 9), *range(11, 19)], 20),
    ('mx40-cvt10-opt4', MX40, '20-port', CVT10, 3, 'OPT 4',
     range(11, 21), 20),
]


@pytest.mark.parametrize('name,unit,mode,box,trunk,opts,backed,count', OWN,
                         ids=[o[0] for o in OWN])
def test_a_box_on_a_copy_opt_backs_up_the_units_own_ports(
        client, name, unit, mode, box, trunk, opts, backed, count):
    """No box on OPT 1/2: the unit's own Ethernet ports are the primaries
    and the copy-OPT box backs each up, never adding a port."""
    pid, cid = rig(client, unit, mode)
    assert trunk in card_of(client, cid)['copyTrunksOpen']
    _ok(add_on_copy(client, pid, cid, box, trunk))
    card = card_of(client, cid)
    assert mapping(card) == {opts: [(n, i + 1, 'own', n)
                                    for i, n in enumerate(backed)]}
    assert _own_backed_by(card) == [opts]
    assert all(p['cvtId'] is None for p in card['ports'])
    assert card['ceiling'] == count and card['defined'] == count
    assert _own_ports(card) == list(range(1, count + 1))
    # set to Mirror, the same box feeds a mirror of those ports instead
    box_id = card['cvts'][0]['id']
    _ok(client.put(f'/api/processors/{pid}/cvts/{box_id}',
                   json={'copyRole': 'mirror'}))
    card = card_of(client, cid)
    assert mapping(card) == {} and card['ownBackedUpBy'] == []
    assert _own_ports(card) == list(range(1, count + 1))
    assert card['ceiling'] == count
    copies = {int(k): v for k, v in card['mirrorSockets'].items()}
    assert sorted(copies) == list(backed)
    assert all(v > count for v in copies.values())


def test_a_box_added_as_a_mirror_on_a_copy_opt_mirrors_the_own_ports(client):
    pid, cid = rig(client, UHD_JR)
    _ok(add_on_copy(client, pid, cid, CVT4K, 2, copyRole='mirror'))
    card = card_of(client, cid)
    assert card['cvts'][0]['copyRole'] == 'mirror'
    assert sorted(int(k) for k in card['mirrorSockets']) == list(range(1, 17))
    assert card['ceiling'] == 16 and len(_own_ports(card)) == 16


def test_own_ports_and_a_primary_box_map_port_by_port(client):
    """UHD Jr: a CVT10 on OPT 1 carries 1-8, the unit's own ports carry
    9-16, and a CVT4K-S on OPT 3-4 backs up both."""
    pid, cid = rig(client, UHD_JR)
    add_boxes(client, pid, cid, [CVT10])
    _ok(add_on_copy(client, pid, cid, CVT4K, 2))
    card = card_of(client, cid)
    assert mapping(card) == {'OPT 3-4': run(range(1, 9), 'OPT 1', 1)
                             + run(range(9, 17), 'own', 9)}
    assert backed_by(card) == {'OPT 1': ['OPT 3-4']}
    assert _own_backed_by(card) == ['OPT 3-4']
    assert card['ceiling'] == 16 and len(_own_ports(card)) == 16


def test_the_copy_opt_holds_through_undo_and_a_delete(client):
    pid, cid = rig(client, UHD_JR)
    _ok(add_on_copy(client, pid, cid, CVT4K, 2))
    before = client.get('/api/project').get_json()
    add_boxes(client, pid, cid, [CVT10])
    card = card_of(client, cid)
    # the next box takes OPT 1, the free primary
    assert [b['trunkTitle'] for b in card['cvts']] == ['OPT 3-4', 'OPT 1']
    primary = card['cvts'][1]['id']
    _ok(client.delete(f'/api/processors/{pid}/cvts/{primary}'))
    assert [b['trunkTitle'] for b in card_of(client, cid)['cvts']] \
        == ['OPT 3-4']
    _ok(client.put('/api/project', json=copy.deepcopy(before)))
    card = card_of(client, cid)
    assert mapping(card) == {'OPT 3-4': run(range(1, 17), 'own', 1)}


@pytest.mark.parametrize('unit,mode,trunk', [
    (UHD_JR, None, 0),       # a primary OPT
    (UHD_JR, None, 3),       # a CVT4K-S takes two OPTs; only OPT 4 is left
    (H4E, 'backup', 4),      # a box-fed card has no ports of its own
    (MX40, '40-port', 2),    # 40-port: OPT 3/4 carry ports of their own
], ids=['primary', 'past-the-end', 'box-fed', 'no-copy-mode'])
def test_a_box_goes_only_onto_an_open_copy_opt(client, unit, mode, trunk):
    pid, cid = rig(client, unit, mode)
    resp = add_on_copy(client, pid, cid, CVT4K, trunk)
    assert resp.status_code == 400, resp.get_data(as_text=True)
    assert not card_of(client, cid)['cvts']


def test_the_rule_is_the_catalogs_copy_word_and_nothing_else(client):
    """A CX80 Pro's OPTs copy its Ethernet ports too (trunkDelivery
    'copy'), but its catalog mode carries no sourced copyTrunks, so no copy
    OPT is offered and none is taken."""
    unit = 'novastar-cx80-pro'
    assert catalog.copy_trunks(catalog.get_device(unit), 'default') is None
    pid, cid = rig(client, unit)
    assert card_of(client, cid)['copyTrunksOpen'] == []
    assert add_on_copy(client, pid, cid, CVT10, 1).status_code == 400


# EVERY UNIT WITH ETHERNET PORTS OF ITS OWN WHOSE CATALOG MODE SOURCES ITS
# COPY OPTS (copyTrunks), as the catalog has them: the box on the copy OPT,
# nothing on the primary OPT, backs up or mirrors the unit's own ports by
# the unit's mode (VX Pros and VX1000: Copy or Backup; MCTRL660 Pro:
# Backup; MX30 and MX20: Copy) or by the box's own role (MCTRL R5 and
# MCTRL4K, Backup by default).
# (unit, backup mode, mirror: ('mode', id) | ('role',) | None, box, its
#  copy OPT, OPTs title, own ports backed, the unit's count)
ALL_OWN = [
    ('novastar-vx400-pro', 'backup', ('mode', 'copy'), CVT10, 1, 'OPT 2',
     4, 4),
    ('novastar-vx600-pro', 'backup', ('mode', 'copy'), CVT10, 1, 'OPT 2',
     6, 6),
    ('novastar-vx1000', 'backup', ('mode', 'copy'), CVT10, 1, 'OPT 2',
     10, 10),
    (VX1000_PRO, 'backup', ('mode', 'copy'), CVT10, 1, 'OPT 2', 10, 10),
    ('novastar-vx2000-pro', 'backup', ('mode', 'copy'), CVT4K, 2,
     'OPT 3-4', [*range(1, 9), *range(11, 19)], 20),
    ('novastar-mctrl660-pro', 'default', None, CVT10, 1, 'OPT 2', 6, 6),
    ('novastar-mctrl-r5', 'default', ('role',), CVT10, 1, 'OPT 2', 8, 8),
    ('novastar-mctrl4k', 'default', ('role',), CVT4K, 2, 'OPT 3-4', 16, 16),
    ('novastar-mx30', None, ('mode', 'default'), CVT10, 1, 'OPT 2', 10, 10),
    ('novastar-mx20', None, ('mode', 'default'), CVT10, 1, 'OPT 2', 6, 6),
]
ALL_OWN_IDS = [u[0].replace('novastar-', '') for u in ALL_OWN]
ALL_OWN_PARAMS = 'unit,backup,mirror,box,trunk,opts,backed,count'


@pytest.mark.parametrize(ALL_OWN_PARAMS, ALL_OWN, ids=ALL_OWN_IDS)
def test_each_sourced_unit_backs_up_or_mirrors_its_own_ports(
        client, unit, backup, mirror, box, trunk, opts, backed, count):
    device = catalog.get_device(unit)
    assert not device.get('requiresDistribution')
    modes = [m for m in ([backup] if backup else [])
             + ([mirror[1]] if mirror and mirror[0] == 'mode' else [])]
    for mode in modes:
        assert catalog.copy_trunks(device, mode), (unit, mode)
    if backup:
        pid, cid = rig(client, unit, backup)
        assert trunk in card_of(client, cid)['copyTrunksOpen']
        _ok(add_on_copy(client, pid, cid, box, trunk))
        card = card_of(client, cid)
        assert card['cvts'][0]['trunkTitle'] == opts
        assert card['cvts'][0]['copyRole'] == 'backup'
        assert mapping(card) == {opts: [(n, i + 1, 'own', n)
                                        for i, n in enumerate(_ports(backed))]}
        assert _own_backed_by(card) == [opts]
        assert all(p['cvtId'] is None for p in card['ports'])
        assert card['ceiling'] == count and card['defined'] == count
        assert _own_ports(card) == list(range(1, count + 1))
        box_id = card['cvts'][0]['id']
        if mirror and mirror[0] == 'mode':
            set_mode(client, pid, cid, mirror[1])
        elif mirror:
            _ok(client.put(f'/api/processors/{pid}/cvts/{box_id}',
                           json={'copyRole': 'mirror'}))
    else:
        pid, cid = rig(client, unit, mirror[1])
        _ok(add_on_copy(client, pid, cid, box, trunk))
    if not mirror:
        return
    card = card_of(client, cid)
    assert card['cvts'][0]['copyRole'] == 'mirror'
    assert mapping(card) == {} and card['ownBackedUpBy'] == []
    assert card['ceiling'] == count
    assert _own_ports(card) == list(range(1, count + 1))
    copies = {int(k): v for k, v in card['mirrorSockets'].items()}
    assert sorted(copies) == _ports(backed)
    assert all(v > count for v in copies.values())


def _ports(backed):
    """ALL_OWN's ports backed: a count from 1, or the list itself."""
    return list(range(1, backed + 1)) if isinstance(backed, int) \
        else list(backed)


# ── a box takes what each OPT carries, up to its outputs an input ─────────
#
# Owner, 2026-11-02: "If you use a CVT 10 with a 16 port card or processor,
# you only get eight ports" and "Much the same if you use a CVT 4K with a
# VX1000, which does 10 ports, you can only use eight of them".

H4 = 'novastar-card-h-4xfiber'
VX1000 = 'novastar-vx1000'


def _boxes(card):
    return {b['trunkTitle']: (b['portNumbers'], b['portCount'])
            for b in card['cvts']}


def test_a_cvt10_on_8_port_opts_gives_8_as_a_backup(client):
    """H_4xfiber in Backup: a CVT4K-S on OPT 1-2 carries 1-16, and the
    CVT10s on OPT 3 and 4 back up 1-8 and 9-16, 8 sockets each."""
    pid, cid = rig(client, H4, 'backup')
    add_boxes(client, pid, cid, [CVT4K, CVT10, CVT10])
    card = card_of(client, cid)
    assert _boxes(card) == {'OPT 1-2': (list(range(1, 17)), 16),
                            'OPT 3': (list(range(1, 9)), 8),
                            'OPT 4': (list(range(9, 17)), 8)}
    assert mapping(card) == {
        'OPT 3': run(range(1, 9), 'OPT 1-2', 1),
        'OPT 4': run(range(9, 17), 'OPT 1-2', 9, socket_first=1)}
    assert card['ceiling'] == 16


def test_the_uhd_jr_the_same(client):
    pid, cid = rig(client, UHD_JR)
    add_boxes(client, pid, cid, [CVT4K, CVT10, CVT10])
    assert _boxes(card_of(client, cid)) == {
        'OPT 1-2': (list(range(1, 17)), 16),
        'OPT 3': (list(range(1, 9)), 8), 'OPT 4': (list(range(9, 17)), 8)}


@pytest.mark.parametrize('unit,mode,ports', [
    (H4, 'backup', range(1, 9)),
    (UHD_JR, None, range(1, 9)),
    # the enhanced card is 10 an OPT: a CVT10 keeps all 10
    (H4E, 'backup', range(1, 11)),
], ids=['h4', 'uhd-jr', 'h4e-keeps-10'])
def test_a_cvt10_primary_gives_what_its_opt_carries(client, unit, mode,
                                                    ports):
    pid, cid = rig(client, unit, mode)
    add_boxes(client, pid, cid, [CVT10])
    assert _boxes(card_of(client, cid)) == {'OPT 1': (list(ports),
                                                      len(ports))}


@pytest.mark.parametrize('unit', [VX1000, VX1000_PRO])
def test_a_cvt4k_on_a_vx1000_gives_8_never_10(client, unit):
    """On one OPT a CVT4K-S gives 8 of a VX1000's 10, ports 9-10 staying
    on the unit's own Ethernet."""
    pid, cid = rig(client, unit)
    _ok(client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                    json={'deviceId': CVT4K, 'inputs': 1, 'pair': False}))
    card = card_of(client, cid)
    assert _boxes(card) == {'OPT 1': (list(range(1, 9)), 8)}
    assert [p['number'] for p in card['ports'] if not p['cvtId']] == [9, 10]
    assert card['ceiling'] == 10


@pytest.mark.parametrize('unit', [VX1000, VX1000_PRO])
def test_a_cvt4k_across_a_vx1000s_opt_1_2_is_its_own_backup(client, unit):
    """Owner, 2026-11-02: a CVT4K-S on OPT 1-2 of a VX1000, whose OPT 2
    copies OPT 1, carries ports 1-8 on its outputs 1-8 and their backup on
    9-16 - its own loop. The count stays 10, 8 of them on the box. In Copy
    its OPT 2 input feeds a mirror instead."""
    pid, cid = rig(client, unit)
    add_boxes(client, pid, cid, [CVT4K])
    card = card_of(client, cid)
    box = card['cvts'][0]
    assert box['trunkTitle'] == 'OPT 1-2'
    assert (box['spansCopy'], box['copyInputRole']) == (True, 'backup')
    assert _boxes(card) == {'OPT 1-2': (list(range(1, 9)), 8)}
    assert box['backNumbers'] == list(range(1, 9))
    assert mapping(card) == {'OPT 1-2': run(range(1, 9), 'OPT 1-2', 1,
                                            socket_first=9)}
    assert backed_by(card) == {'OPT 1-2': ['OPT 1-2']}
    assert card['ceiling'] == 10 and card['defined'] == 10
    assert [p['number'] for p in card['ports'] if not p['cvtId']] == [9, 10]
    # a file carrying one opens the same, and undo follows
    before = client.get('/api/project').get_json()
    _ok(client.delete(f'/api/processors/{pid}/cvts/{box["id"]}'))
    _ok(client.put('/api/project', json=copy.deepcopy(before)))
    assert mapping(card_of(client, cid)) == mapping(card)
    # Copy: the OPT 2 input mirrors 1-8, numbered past the count
    set_mode(client, pid, cid, 'copy')
    card = card_of(client, cid)
    box = card['cvts'][0]
    assert (box['spansCopy'], box['copyInputRole']) == (True, 'mirror')
    assert mapping(card) == {}
    assert {int(k): v for k, v in card['mirrorSockets'].items()} \
        == {n: n + 10 for n in range(1, 9)}
    assert box['portNumbers'] == [*range(1, 9), *range(11, 19)]
    assert card['ceiling'] == 10
    assert len([p for p in card['ports'] if not p['mirrorOf']]) == 10


@pytest.mark.parametrize('unit,role', [
    ('novastar-mctrl660-pro', 'backup'),
    ('novastar-mx30', 'mirror'),
    ('novastar-mctrl-r5', 'backup'),
    (VX1000_PRO, 'backup'),
], ids=['mctrl660-pro', 'mx30', 'r5', 'vx1000-pro'])
def test_each_two_opt_units_straddle_takes_its_modes_word(client, unit,
                                                          role):
    pid, cid = rig(client, unit)
    add_boxes(client, pid, cid, [CVT4K])
    box = card_of(client, cid)['cvts'][0]
    assert (box['spansCopy'], box['copyInputRole']) == (True, role)
    assert box['copyRoleChoice'] == (unit == 'novastar-mctrl-r5')


def test_a_per_box_straddle_picks_mirror_or_backup_and_keeps_its_cables(
        client):
    """MCTRL R5 (per box): the straddling box's COPY strip picks what its
    OPT 2 input carries; its own sockets 1-8 and their home runs stay."""
    pid, cid = rig(client, 'novastar-mctrl-r5')
    add_boxes(client, pid, cid, [CVT4K])
    box = card_of(client, cid)['cvts'][0]
    _ok(client.put(f'/api/processors/{pid}/cvts/{box["id"]}',
                   json={'portCables': {'1': {'ft': 50}}}))
    _ok(client.put(f'/api/processors/{pid}/cvts/{box["id"]}',
                   json={'copyRole': 'mirror'}))
    card = card_of(client, cid)
    box = card['cvts'][0]
    assert box['copyInputRole'] == 'mirror' and mapping(card) == {}
    assert sorted(int(k) for k in card['mirrorSockets']) == list(range(1, 9))
    assert box['portCables'], box['portCables']
    _ok(client.put(f'/api/processors/{pid}/cvts/{box["id"]}',
                   json={'copyRole': 'backup'}))
    card = card_of(client, cid)
    assert card['cvts'][0]['copyInputRole'] == 'backup'
    assert mapping(card) == {'OPT 1-2': run(range(1, 9), 'OPT 1-2', 1,
                                            socket_first=9)}
    assert card['ceiling'] == 8


def test_a_box_drop_lands_on_the_boxs_own_sockets(client):
    """MX40 Pro 20-port, a CVT4K-S on OPT 1-2 (1-8 and 11-18): a 12-port
    screen dropped on the box takes 1-8 and 11-14, never the MX40 Pro's own
    9 and 10 inside the box's span."""
    resp = client.post('/api/layer/add', json={
        'name': 'WALL', 'columns': 4, 'rows': 3,
        'cabinet_width': 200, 'cabinet_height': 200})
    wall = str(_ok(resp)['id'])
    pid, cid = rig(client, MX40, '20-port')
    add_boxes(client, pid, cid, [CVT4K])
    box = card_of(client, cid)['cvts'][0]
    _ok(client.post('/api/port-assignments/place-overflow', json={
        'layerId': wall, 'cardId': cid, 'firstPort': 1, 'lastPort': 18,
        'boxId': box['id'],
        'screens': [{'layerId': wall, 'name': 'WALL', 'ports': 12}]}))
    pins = client.get('/api/project').get_json()['port_assignments']['pins']
    placed = sorted(p['port'] for p in pins if p['layerId'] == wall)
    assert placed == [*range(1, 9), *range(11, 15)]


def test_a_cvt4k_across_a_uhd_jrs_opt_2_3_backs_up_opt_1(client):
    """A CVT10 on OPT 1 leaves OPT 2 and the copies: the next CVT4K-S takes
    OPT 2-3, ports 9-16 on its outputs 1-8, and its OPT 3 input - the copy
    of OPT 1 - backs up the CVT10's 1-8 on its outputs 9-16."""
    pid, cid = rig(client, UHD_JR)
    add_boxes(client, pid, cid, [CVT10, CVT4K])
    card = card_of(client, cid)
    assert _boxes(card)['OPT 2-3'] == (list(range(9, 17)), 8)
    assert mapping(card) == {'OPT 2-3': run(range(1, 9), 'OPT 1', 1,
                                            socket_first=9)}
    assert card['ceiling'] == 16


# Owner, 2026-11-03: "the cvt 1-8 is locked to opt 1 always". A CVT4K-S's
# outputs 1-8 belong to its input 1 and input 2 starts at output 9 whatever
# feeds it, so on OPTs of fewer than 8 ports outputs are left empty between
# the two inputs. (unit, mode, ports per OPT, what OPT 2's input carries)
CVT4K_LOCK = [
    ('novastar-vx400-pro', None, 4, 'backup'),
    ('novastar-vx600-pro', None, 6, 'backup'),
    ('novastar-mctrl660-pro', None, 6, 'backup'),
    ('novastar-mx20', None, 6, 'mirror'),
    (VX1000, None, 8, 'backup'),
]


@pytest.mark.parametrize('unit,mode,per,role', CVT4K_LOCK,
                         ids=[u[0].replace('novastar-', '') for u in CVT4K_LOCK])
def test_a_cvt4ks_second_input_starts_at_output_9(client, unit, mode, per,
                                                  role):
    pid, cid = rig(client, unit, mode)
    add_boxes(client, pid, cid, [CVT4K])
    card = card_of(client, cid)
    box = card['cvts'][0]
    assert (box['trunkTitle'], box['copyInputRole']) == ('OPT 1-2', role)
    # input 1: the main OPT's ports on outputs 1..per
    assert box['portNumbers'][:per] == list(range(1, per + 1))
    assert box['socketNumbers'][:per] == list(range(1, per + 1))
    own = {p['number']: p['localNumber'] for p in card['ports']
           if p['cvtId'] == box['id'] and not p['mirrorOf']}
    assert own == {n: n for n in range(1, per + 1)}
    # input 2: its copy on outputs 9.., never per + 1
    second = list(range(9, 9 + per))
    if role == 'backup':
        assert box['backNumbers'] == list(range(1, per + 1))
        assert box['backSockets'] == second
        assert mapping(card) == {'OPT 1-2': run(range(1, per + 1), 'OPT 1-2',
                                                1, socket_first=9)}
    else:
        assert box['socketNumbers'][per:] == second
        mirrors = sorted(p['localNumber'] for p in card['ports']
                         if p['mirrorOf'] and p['cvtId'] == box['id'])
        assert mirrors == second


def test_the_enhanced_cards_cvt4k_still_reads_1_8_and_9_16(client):
    """10-port OPTs: card ports 1-8 and 11-18 on outputs 1-8 and 9-16, as
    before the lock."""
    pid, cid = rig(client, H4E, 'backup')
    add_boxes(client, pid, cid, [CVT4K])
    box = card_of(client, cid)['cvts'][0]
    assert box['portNumbers'] == [*range(1, 9), *range(11, 19)]
    assert box['socketNumbers'] == list(range(1, 17))


def test_only_the_cvt4k_locks_its_outputs_to_its_inputs():
    # the CVT4K-S and its multimode twin, the CVT4K-M, which behaves
    # exactly like it but for its fiber (owner, 2026-11-04)
    locked = [d['id'] for d in (catalog.devices().values()
                                if isinstance(catalog.devices(), dict)
                                else catalog.devices())
              if catalog.input_outputs(d)]
    assert locked == [CVT4K, 'novastar-cvt4k-m']
    assert catalog.input_outputs(catalog.get_device('novastar-cvt4k-m')) == 8
    assert catalog.input_outputs(catalog.get_device(CVT4K)) == 8


# ── the tray, its sheets, the binder's words and the pull sheet ───────────

FETCH_COUNT_JS = """(() => {
    const orig = window.fetch;
    window.__lrdFetches = 0;
    window.fetch = function (...args) {
        window.__lrdFetches++;
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

SEED_JS = """async ([unit, kind, mode, boxes]) => {
    const send = (url, method, body) => fetch(url, { method,
        headers: { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body) })
        .then(r => r.json());
    const proj = await (await fetch('/api/project')).json();
    proj.layers = [];
    proj.groups = [];
    proj.processors = [];
    proj.distros = [];
    delete proj.port_assignments;
    await send('/api/project', 'PUT', proj);
    await send('/api/layer/add', 'POST', { name: 'WALL', columns: 4,
        rows: 4, cabinet_width: 200, cabinet_height: 200 });
    const st = await send('/api/processors', 'POST',
        { deviceId: kind === 'card' ? 'novastar-h9' : unit });
    const proc = st.processors[st.processors.length - 1];
    let card = proc.slots[0].card && proc.slots[0].card.id;
    if (kind === 'card') {
        const put = await send(`/api/processors/${proc.id}/slots/0`, 'PUT',
                               { deviceId: unit });
        card = put.processors.find(p => p.id === proc.id).slots[0].card.id;
    }
    if (mode) {
        await send(`/api/processors/${proc.id}/cards/${card}`, 'PUT',
                   { mode });
    }
    for (const box of boxes) {
        await send(`/api/processors/${proc.id}/cards/${card}/cvts`, 'POST',
                   { deviceId: box, pair: false });
    }
    await window.app.refreshProcessors();
    return { proc: proc.id, card };
}"""

TRAY_JS = """(cardId) => {
    const app = window.app;
    const card = app._processorsResolved.flatMap(p => p.slots)
        .map(s => s.card).find(c => c && c.id === cardId);
    const title = (id) => card.cvts.find(b => b.id === id).trunkTitle;
    const backups = card.cvts.filter(b => (b.backsUpPorts || []).length);
    const mains = card.cvts.filter(b => (b.backedUpBy || []).length);
    const strips = {};
    let unit = null;
    const ownRows = [...document.querySelectorAll(
        `[data-lrd-loop-own="${cardId}"] [data-lrd-loop-far]`)].map(r => [
            title(r.dataset.lrdLoopFar),
            [...r.querySelectorAll('.lrd-tile-face')].map(f => parseInt(
                f.querySelector('.lrd-tile-line span').textContent, 10)),
        ]);
    for (const near of mains) {
        const sec = document.querySelector(
            `[data-lrd-sec-id="hwdock-box-${near.id}"]`);
        if (!sec) { strips[near.trunkTitle] = null; continue; }
        unit = unit || sec.closest('.hw-dock-unit, .hw-dock-card');
        strips[near.trunkTitle] = {
            loop: sec.classList.contains('hw-dock-loop'),
            fars: [...sec.querySelectorAll('[data-lrd-loop-far]')].map(r => [
                title(r.dataset.lrdLoopFar),
                [...r.querySelectorAll('.lrd-tile-face')].map(f => parseInt(
                    f.querySelector('.lrd-tile-line span').textContent, 10)),
            ]),
        };
    }
    // the backup box's own cable sheet, flipped open: a row per socket,
    // numbered with the port it backs up
    const sheets = {};
    const sheetText = [];
    for (const b of backups) {
        app._setDataCableSheetOpen({ kind: 'cvt', id: b.id }, true);
    }
    app.renderHardwareDock();
    for (const b of backups) {
        const sheet = document.querySelector(
            `[data-lrd-cable-sheet="cvt:${b.id}"]`);
        const rows = sheet ? [...sheet.querySelectorAll('tr')]
            .filter(tr => tr.children[0] && tr.children[0].tagName === 'TD'
                    && !tr.classList.contains('hw-dock-cable-snake')) : [];
        sheets[b.trunkTitle] = sheet
            ? rows.map(tr => parseInt(tr.children[1].textContent, 10)) : null;
        sheetText.push(...rows.map(tr => tr.children[1].textContent));
        app._setDataCableSheetOpen({ kind: 'cvt', id: b.id }, false);
    }
    app.renderHardwareDock();
    unit = unit || document.querySelector(
        `[data-lrd-loop-own="${cardId}"]`)?.closest('.hw-dock-unit, .hw-dock-card');
    return {
        strips,
        ownRows,
        sheets,
        sheetText,
        alone: backups.filter(b => document.querySelector(
            `[data-lrd-sec-id="hwdock-box-${b.id}"]`)).map(b => b.trunkTitle),
        copyTag: !!unit && unit.textContent.includes('(copy)'),
        // the binder's Breakout boxes line and the box's ⚙ read this
        words: Object.fromEntries(backups.map(b => [b.trunkTitle,
            app.boxLoopText(b, card.cvts, x => x.trunkTitle)])),
        // the box sheet's Fiber section reads the loop as one group
        groups: Object.fromEntries(backups.map(b => {
            const g = app.fiberLoopGroup(b);
            return [b.trunkTitle, g ? [g.nears.map(x => x.trunkTitle),
                                       g.fars.map(x => x.trunkTitle)] : null];
        })),
        boxes: card.cvts.length,
        pulled: app._pullAllBoxes().filter(e => e.card.id === cardId).length,
        ceiling: card.ceiling,
    };
}"""


def _spans(rows):
    """'1-10, 1-6 as 11-16' style words, per primary, for one backup."""
    groups = {}
    for _number, _socket, primary, local in rows:
        groups.setdefault(primary, ([], []))
        groups[primary][0].append(local)
        groups[primary][1].append(_socket)

    def text(ns):
        return f'{min(ns)}-{max(ns)}'
    parts = []
    for primary, (locals_, sockets) in groups.items():
        mine, shown = text(locals_), text(sockets)
        primary = 'own ports' if primary == 'own' else primary
        parts.append(f'{primary} {mine}'
                     + (f' on sockets {shown}' if shown != mine else ''))
    return 'loop of ' + ', '.join(parts)


@pytest.mark.parametrize(PARAMS, SHAPES, ids=IDS)
def test_the_tray_draws_each_backup_socket_in_its_primarys_loop(
        e2e_server, pw_browser, name, unit, mode, other, boxes, expected,
        count):
    kind = catalog.get_device(unit)['kind']
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 1100})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    context.add_init_script(FETCH_COUNT_JS)
    page = context.new_page()
    try:
        page.goto(e2e_server, wait_until='domcontentloaded')
        page.wait_for_function(
            "() => window.app && window.app._initialLoadComplete === true"
            " && window.app._socketConnects >= 1")
        page.evaluate("() => { window.__lrdQuiet = 0; }")
        page.wait_for_function(QUIET_JS)
        ids = page.evaluate(SEED_JS, [unit, kind, mode, boxes])
        page.locator('[data-mode="data-flow"]').click()
        page.wait_for_function(
            "() => window.canvasRenderer.viewMode === 'data-flow'")
        page.evaluate("() => { window.__lrdQuiet = 0; }")
        page.wait_for_function(QUIET_JS)
        tray = page.evaluate(TRAY_JS, ids['card'])
    finally:
        context.close()
    # every primary's strip is a loop ending in a row per backup box, each
    # socket numbered with the card port it backs up
    want = {}
    for backup, rows in expected.items():
        for _number, _socket, primary, _local in rows:
            fars = want.setdefault(primary, [])
            if not fars or fars[-1][0] != backup:
                fars.append([backup, []])
            fars[-1][1].append(_socket)
    assert tray['ownRows'] == want.pop('own', []), tray['ownRows']
    assert set(tray['strips']) == set(want), tray['strips']
    for primary, fars in want.items():
        strip = tray['strips'][primary]
        assert strip and strip['loop'], (primary, strip)
        assert strip['fars'] == fars, (primary, strip['fars'])
    # no backup box drawn on its own, and no "(copy)" box of free sockets
    assert tray['alone'] == [], tray['alone']
    assert not tray['copyTag']
    # the backup's cable sheet: every socket by its silkscreen, the port it
    # backs up named beside it
    assert tray['sheets'] == {b: [r[1] for r in rows]
                              for b, rows in expected.items()}
    assert all('backs up' in t for t in tray['sheetText'])
    assert tray['words'] == {b: _spans(rows) for b, rows in expected.items()}
    for backup, rows in expected.items():
        nears, fars = tray['groups'][backup]
        assert backup in fars
        assert {r[2] for r in rows} - {'own'} <= set(nears)
    # both boxes of every loop on the pull sheet; no backup port counted
    assert (tray['boxes'], tray['pulled'], tray['ceiling']) \
        == (len(boxes), len(boxes), count)


OWN_TRAY_JS = """(cardId) => {
    const app = window.app;
    const card = app._processorsResolved.flatMap(p => p.slots)
        .map(s => s.card).find(c => c && c.id === cardId);
    const box = card.cvts[0];
    const own = document.querySelector(`[data-lrd-loop-own="${cardId}"]`);
    const unit = own && own.closest('.hw-dock-unit, .hw-dock-card');
    return {
        rows: own ? [...own.querySelectorAll('[data-lrd-loop-far]')].map(r =>
            [...r.querySelectorAll('.lrd-tile-face')].map(f => parseInt(
                f.querySelector('.lrd-tile-line span').textContent, 10))) : null,
        // the unit's own ports still draw as its own, all of them
        loose: unit ? unit.querySelectorAll(
            ':scope .lrd-tile-grid[data-lrd-snake-owner^="card:"] .lrd-tile-face').length : 0,
        alone: !!document.querySelector(
            `[data-lrd-sec-id="hwdock-box-${box.id}"]`),
        copyTag: !!unit && unit.textContent.includes('(copy)'),
        words: app.boxLoopText(box, card.cvts, x => x.trunkTitle),
        pulled: app._pullAllBoxes().filter(e => e.card.id === cardId).length,
        ceiling: card.ceiling,
    };
}"""

OFFER_JS = """(cardId) => {
    const app = window.app;
    const card = app._processorsResolved.flatMap(p => p.slots)
        .map(s => s.card).find(c => c && c.id === cardId);
    return app._dockCopyPlacements(card, app._cardBoxFits(card))
        .map(c => `${c.fit.name} on ${c.title}`);
}"""


UNIT_TRAY_JS = """async ([proc, cardId, device, trunk]) => {
    const app = window.app;
    const find = () => app._processorsResolved.flatMap(p => p.slots)
        .map(s => s.card).find(c => c && c.id === cardId);
    let card = find();
    const fits = app._cardBoxFits(card).map(d => d.name);
    const offered = app._dockCopyPlacements(card, app._cardBoxFits(card))
        .map(c => [c.fit.id, c.trunk, `${c.fit.name} on ${c.title}`]);
    await fetch(`/api/processors/${proc}/cards/${cardId}/cvts`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ deviceId: device, trunk }) });
    await app.refreshProcessors();
    app.renderHardwareDock();
    card = find();
    const box = card.cvts[0];
    const own = document.querySelector(`[data-lrd-loop-own="${cardId}"]`);
    const alone = document.querySelector(
        `[data-lrd-sec-id="hwdock-box-${box.id}"]`);
    const unit = (own || alone).closest('.hw-dock-unit, .hw-dock-card');
    return {
        fits,
        offered,
        role: box.copyRole,
        rows: own ? [...own.querySelectorAll('[data-lrd-loop-far]')].map(r =>
            [...r.querySelectorAll('.lrd-tile-face')].map(f => parseInt(
                f.querySelector('.lrd-tile-line span').textContent, 10))) : null,
        loose: unit.querySelectorAll(
            '.lrd-tile-grid[data-lrd-snake-owner^="card:"] .lrd-tile-face').length,
        alone: !!alone,
        copyTag: unit.textContent.includes('(copy)'),
        mirrorTag: !!alone && alone.textContent.includes('(mirror)'),
        ceiling: card.ceiling,
    };
}"""


@pytest.mark.parametrize(ALL_OWN_PARAMS, ALL_OWN, ids=ALL_OWN_IDS)
def test_each_sourced_units_tray_offers_the_copy_opt_and_draws_the_loop(
        e2e_server, pw_browser, unit, backup, mirror, box, trunk, opts,
        backed, count):
    """+ Box offers the box on the copy OPT; put there, a backup draws as
    loop rows under the unit's own ports, a mirror as a box of its own."""
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 1100})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    context.add_init_script(FETCH_COUNT_JS)
    page = context.new_page()
    try:
        page.goto(e2e_server, wait_until='domcontentloaded')
        page.wait_for_function(
            "() => window.app && window.app._initialLoadComplete === true"
            " && window.app._socketConnects >= 1")
        page.evaluate("() => { window.__lrdQuiet = 0; }")
        page.wait_for_function(QUIET_JS)
        ids = page.evaluate(SEED_JS, [unit, 'unit', backup or mirror[1], []])
        page.locator('[data-mode="data-flow"]').click()
        page.wait_for_function(
            "() => window.canvasRenderer.viewMode === 'data-flow'")
        page.evaluate("() => { window.__lrdQuiet = 0; }")
        page.wait_for_function(QUIET_JS)
        tray = page.evaluate(UNIT_TRAY_JS,
                             [ids['proc'], ids['card'], box, trunk])
    finally:
        context.close()
    assert [box, trunk] in [o[:2] for o in tray['offered']], tray['offered']
    if catalog.get_device(unit)['trunks'] == 2:
        # a CVT4K-S on OPT 1-2 straddles the main OPT and its copy, its
        # own loop or mirror: + Box offers it whole
        assert 'CVT4K-S' in tray['fits'], tray['fits']
    assert any(o[2].endswith(f' on {opts}') for o in tray['offered'])
    assert tray['loose'] == count and tray['ceiling'] == count
    assert not tray['copyTag']
    if backup:
        assert tray['role'] == 'backup'
        # each socket reads its silkscreen, 1..N
        assert tray['rows'] == [list(range(1, len(_ports(backed)) + 1))], \
            tray['rows']
        assert not tray['alone']
    else:
        assert tray['role'] == 'mirror'
        assert tray['rows'] is None and tray['alone'] and tray['mirrorTag']


def test_the_tray_draws_the_own_ports_backup_as_loop_rows(e2e_server,
                                                          pw_browser):
    """A UHD Jr with no box on OPT 1/2: "+ Box" offers the copy OPTs, and
    a CVT4K-S put on OPT 3-4 draws as the loop end of the unit's own 16
    ports, right under them."""
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 1100})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    context.add_init_script(FETCH_COUNT_JS)
    page = context.new_page()
    try:
        page.goto(e2e_server, wait_until='domcontentloaded')
        page.wait_for_function(
            "() => window.app && window.app._initialLoadComplete === true"
            " && window.app._socketConnects >= 1")
        page.evaluate("() => { window.__lrdQuiet = 0; }")
        page.wait_for_function(QUIET_JS)
        ids = page.evaluate(SEED_JS, [UHD_JR, 'unit', None, []])
        offered = page.evaluate(OFFER_JS, ids['card'])
        assert {'CVT10-S on OPT 3', 'CVT4K-S on OPT 3-4'} <= set(offered), \
            offered
        page.evaluate("""async ([proc, card]) => {
            await fetch(`/api/processors/${proc}/cards/${card}/cvts`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ deviceId: 'novastar-cvt4k-s', trunk: 2 }) });
            await window.app.refreshProcessors();
        }""", [ids['proc'], ids['card']])
        page.locator('[data-mode="data-flow"]').click()
        page.wait_for_function(
            "() => window.canvasRenderer.viewMode === 'data-flow'")
        page.evaluate("() => { window.__lrdQuiet = 0; }")
        page.wait_for_function(QUIET_JS)
        tray = page.evaluate(OWN_TRAY_JS, ids['card'])
    finally:
        context.close()
    assert tray['rows'] == [list(range(1, 17))], tray['rows']
    assert tray['loose'] == 16
    assert not tray['alone'] and not tray['copyTag']
    assert tray['words'] == 'loop of own ports 1-16'
    assert (tray['pulled'], tray['ceiling']) == (1, 16)


STRADDLE_TRAY_JS = """(cardId) => {
    const app = window.app;
    const card = app._processorsResolved.flatMap(p => p.slots)
        .map(s => s.card).find(c => c && c.id === cardId);
    const box = card.cvts[0];
    const sec = document.querySelector(`[data-lrd-sec-id="hwdock-box-${box.id}"]`);
    const chips = (el) => [...el.querySelectorAll('.lrd-tile-face')].map(f =>
        parseInt(f.querySelector('.lrd-tile-line span').textContent, 10));
    const rows = sec ? [...sec.querySelectorAll('.hw-dock-loop-row')] : [];
    const far = rows.find(r => r.dataset.lrdLoopFar);
    return {
        loop: !!sec && sec.classList.contains('hw-dock-loop'),
        near: rows[0] ? chips(rows[0]) : null,
        far: far ? chips(far) : null,
        farHead: far ? far.querySelector('.hw-dock-unit-info').textContent : '',
        names: sec ? sec.querySelector('.hw-dock-loop-names').textContent : '',
        hover: far ? far.querySelector('.lrd-tile-face').title : '',
        words: app.boxLoopText(box, card.cvts, x => x.trunkTitle),
        ceiling: card.ceiling,
    };
}"""


def test_the_tray_draws_a_vx1000_straddle_as_its_own_loop(e2e_server,
                                                          pw_browser):
    """A CVT4K-S on OPT 1-2 of a VX1000: its strip's near row is its
    sockets 1-8, its loop row its sockets 9-16, the backup of 1-8."""
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 1100})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    context.add_init_script(FETCH_COUNT_JS)
    page = context.new_page()
    try:
        page.goto(e2e_server, wait_until='domcontentloaded')
        page.wait_for_function(
            "() => window.app && window.app._initialLoadComplete === true"
            " && window.app._socketConnects >= 1")
        page.evaluate("() => { window.__lrdQuiet = 0; }")
        page.wait_for_function(QUIET_JS)
        ids = page.evaluate(SEED_JS, [VX1000, 'unit', None, [CVT4K]])
        page.locator('[data-mode="data-flow"]').click()
        page.wait_for_function(
            "() => window.canvasRenderer.viewMode === 'data-flow'")
        page.evaluate("() => { window.__lrdQuiet = 0; }")
        page.wait_for_function(QUIET_JS)
        tray = page.evaluate(STRADDLE_TRAY_JS, ids['card'])
    finally:
        context.close()
    assert tray['loop'], tray
    assert tray['near'] == list(range(1, 9)), tray
    assert tray['far'] == list(range(9, 17)), tray
    assert tray['farHead'] == 'ports 1-8', tray
    # a box looping onto itself is named once, by its sockets
    assert tray['names'] == 'A-B 1-8 ↔ 9-16', tray
    assert 'the backup of port 1 on' in tray['hover'], tray['hover']
    # a box backing up its own outputs says so, never its own name
    assert tray['words'] == 'backs up its own outputs 1-8 on 9-16'
    assert tray['ceiling'] == 10


# ── a box backing up its own outputs: each backup output its own cable ────
#
# The owner, 2026-11-03, on the CVT4K-S across a VX1000's OPT 1-2 (ports 1-8
# out on outputs 1-8, their backup on 9-16): "of course it will have its own
# extension". Each backup output is a cable of its own, with its own length
# on the box's cable sheet, and its own row on the pull sheet and the
# binder. Both outputs share the card-wide number, so the backup output's
# cable is kept under 'r<n>' in the box's port cables.

def test_a_box_backing_up_its_own_outputs_links_each_backup_output(client):
    """Each of ports 1-8 is backed by the same box's socket 8 higher, marked
    `self`, and the box keeps a cable for each output: '1' for output 1,
    'r1' for output 9. A released port forgets both."""
    pid, cid = rig(client, VX1000)
    add_boxes(client, pid, cid, [CVT4K])
    card = card_of(client, cid)
    box = card['cvts'][0]
    backed = {p['number']: p['backedBy'] for p in card['ports'] if p.get('backedBy')}
    assert sorted(backed) == list(range(1, 9)), backed
    for n, bb in backed.items():
        assert (bb['cvtId'], bb['port'], bb['localPort'], bb['loop'], bb.get('self')) \
            == (box['id'], n, n + 8, True, True), bb
    _ok(client.put(f'/api/processors/{pid}/cvts/{box["id"]}',
                   json={'portCables': {'1': {'ft': 50}, 'r1': {'ft': 75}}}))
    box = card_of(client, cid)['cvts'][0]
    assert box['portCables']['1']['ft'] == 50
    assert box['portCables']['r1']['ft'] == 75
    # a key naming a socket the box does not have is refused, as ever
    resp = client.put(f'/api/processors/{pid}/cvts/{box["id"]}',
                      json={'portCables': {'r9': {'ft': 10}}})
    assert resp.status_code == 400, resp.get_data(as_text=True)
    procs = copy.deepcopy(client.get('/api/project').get_json()['processors'])
    assert catalog.forget_port_cables(procs, [(cid, 1)]) == 2
    raw = next(c for p in procs for s in p['slots'] if s.get('card')
               for c in s['card'].get('cvts') or [])
    assert 'portCables' not in raw, raw


SELF_BACKUP_JS = """async (cables) => {
    const app = window.app;
    const send = (url, method, body) => fetch(url, { method,
        headers: { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body) })
        .then(r => r.json());
    const card = app._processorsResolved.flatMap(p => p.slots)
        .map(s => s.card).find(c => c && c.cvts && c.cvts.length);
    const box = card.cvts[0];
    const proc = app._processorsResolved.find(p => p.slots.some(s => s.card === card));
    // a wall of four ports
    await send('/api/layer/add', 'POST', { name: 'BIG', columns: 4, rows: 2,
        cabinet_width: 500, cabinet_height: 500 });
    app.project = await send('/api/project', 'GET');
    const wall = app.project.layers.find(l => l.name === 'BIG');
    await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST', {
        layerId: String(wall.id), cardId: card.id, firstPort: 1, lastPort: 8,
        boxId: box.id, screens: [{ layerId: String(wall.id), name: 'BIG',
                                   ports: app.getLayerPortsRequired(wall) }] });
    await send(`/api/processors/${proc.id}/cvts/${box.id}`, 'PUT', { portCables: cables });
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app._setDataCableSheetOpen({ kind: 'cvt', id: box.id }, true);
    app.renderHardwareDock();
    return { box: box.id, ports: app.getLayerPortsRequired(wall) };
}"""

SELF_READ_JS = """(boxId) => {
    const app = window.app;
    const wall = app.project.layers.find(l => l.name === 'BIG');
    const list = app.buildPullList();
    const scr = Object.values(list.byScreen || {}).find(s => s.name === 'BIG');
    const sheet = document.querySelector(`[data-lrd-cable-sheet="cvt:${boxId}"]`);
    const field = (key) => {
        const el = sheet && sheet.querySelector(`[data-lrd-field="data-cable-ft-${boxId}-${key}"]`);
        return el ? el.value : null;
    };
    const rowText = (key) => {
        const el = sheet && sheet.querySelector(`[data-lrd-field="data-cable-ft-${boxId}-${key}"]`);
        return el ? el.closest('tr').children[1].textContent : null;
    };
    return {
        ends: scr.ports.map(p => [p.cable, p.backup && p.backup.cable]),
        rows: (list.totals || []).filter(r => /etherCON|Cat6/.test(r.type))
            .map(r => [r.length, r.qty, r.label]),
        field1: field(1), fieldR1: field('r1'), fieldR2: field('r2'),
        textR1: rowText('r1'),
        tag: (app.dataPortBackupCableForScreen(wall, 1) || {}).text || null,
    };
}"""


# Every text the binder prints, data side and the processor sheets.
BINDER_TEXTS_JS = """() => {
    const app = window.app;
    const opts = { sheet: 'tabloid', palette: 'colour', sides: { power: false, data: true },
                   scope: { kind: 'show' }, cover: false, pull: false, hardware: true,
                   wiring: false };
    const plan = app.planBinder(opts);
    const out = [];
    for (let i = 0; i < plan.length; i++) {
        const r = app.renderBinderPage(opts, i);
        r.record.ops.filter(o => o.op === 'text' && String(o.text).trim())
            .forEach(o => out.push(String(o.text)));
    }
    return out;
}"""


def test_each_backup_output_of_a_self_backing_box_is_its_own_cable(
        e2e_server, pw_browser):
    """The box's cable sheet has a length of its own for each backup output
    (socket 9 backs up port 1), the pull sheet pulls the backup run as its
    own row, and the backup end's tag reads its own length. Typing in the
    backup output's field writes that output only."""
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 1100})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    context.add_init_script(FETCH_COUNT_JS)
    page = context.new_page()
    try:
        page.goto(e2e_server, wait_until='domcontentloaded')
        page.wait_for_function(
            "() => window.app && window.app._initialLoadComplete === true"
            " && window.app._socketConnects >= 1")
        page.evaluate("() => { window.__lrdQuiet = 0; }")
        page.wait_for_function(QUIET_JS)
        page.evaluate(SEED_JS, [VX1000, 'unit', None, [CVT4K]])
        page.locator('[data-mode="data-flow"]').click()
        page.wait_for_function(
            "() => window.canvasRenderer.viewMode === 'data-flow'")
        seeded = page.evaluate(SELF_BACKUP_JS, {'1': {'ft': 50}, 'r1': {'ft': 75}})
        assert seeded['ports'] >= 2, seeded
        page.evaluate("() => window.app.renderLayers()")
        page.evaluate("() => { window.__lrdQuiet = 0; }")
        page.wait_for_function(QUIET_JS)
        got = page.evaluate(SELF_READ_JS, seeded['box'])
        assert got['ends'][0] == ["50' etherCON", "75' etherCON"], got
        assert ["75'", 1, '1R'] in got['rows'], got['rows']
        assert (got['field1'], got['fieldR1']) == ('50', '75'), got
        assert got['textR1'].startswith('9 · backs up port 1'), got['textR1']
        assert got['tag'] == "75' etherCON", got
        # the user types the backup of port 2 on its own row
        field = page.locator(f'[data-lrd-field="data-cable-ft-{seeded["box"]}-r2"]')
        field.click()
        field.fill('100')
        page.keyboard.press('Enter')
        page.evaluate("() => { window.__lrdQuiet = 0; }")
        page.wait_for_function(QUIET_JS)
        got = page.evaluate(SELF_READ_JS, seeded['box'])
        assert got['ends'][1] == [None, "100' etherCON"], got
        assert got['fieldR2'] == '100', got
        # the binder says the box backs up its own outputs, in those words,
        # and never names the box as its own primary
        texts = page.evaluate(BINDER_TEXTS_JS)
        title = page.evaluate("(id) => window.app._bBoxTitle(window.app"
                              "._processorsResolved.flatMap(p => p.slots).map(s => s.card)"
                              ".find(c => c && c.cvts && c.cvts.length).cvts[0])",
                              seeded['box'])
        want = f'{title} backs up its own outputs 1-8 on 9-16'
        assert any(t == want for t in texts), (want, [t for t in texts if 'backs up' in t])
        assert not any(f'{title} backs up {title}' in t for t in texts), texts
        assert any(t == 'Backup boxes' for t in texts), [t for t in texts if 'ackup' in t]
    finally:
        context.close()

