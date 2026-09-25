"""Fiber cables on breakout boxes: TAC, MTP and opticalCON.

"tac is just for stranded fiber" (owner, 2026-09-25). The fiber that feeds
a breakout box is a CABLE the show owns - project['fiberCables'] - and each
of the box's trunk links takes strands of one (cvt['fiberLinks']):

  - a TAC or an MTP ("mtp is basically a packaged tac", its own kind by the
    ruling "If i choose tac 12 call it that if i choose mtp 12 choose
    that") has any strand count and is SHARED by several boxes' links;
  - an opticalCON DUO (2) or QUAD (4) is one box's (ownerBoxId);
  - a link takes 2 strands, 1 on a NovaStar or Megapixel box switched to
    BiDi; a strand carries one link show-wide;
  - a backup record bound to its primary - NovaStar backupOf and Brompton's
    adjacent pair automatically, a backup processor's box by hand - is the
    same physical box taking a second fiber: its backup links live on the
    primary, and it is not a second box on the pull sheet;
  - strand names follow TIA-598-D;
  - a cable no link uses any more is pruned; the list is absent when empty.

Run locally (each session takes its own free port):
    python3 -m pytest tests/test_fiber_cables.py -v --browser chromium
"""

import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import processor_catalog as catalog  # noqa: E402

H4 = 'novastar-card-h-4xfiber'
H16 = 'novastar-card-h-16xrj45-2xfiber'


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# ── helpers ──────────────────────────────────────────────────────────────

def _ok(resp, code=200):
    assert resp.status_code == code, resp.get_data(as_text=True)[:300]
    return resp.get_json()


def _refused(resp):
    assert resp.status_code == 400, resp.get_data(as_text=True)[:300]
    return resp.get_json()['error']


def _h9(client, card=H4, mode=None):
    st = _ok(client.post('/api/processors', json={'deviceId': 'novastar-h9'}), 201)
    pid = st['processors'][-1]['id']
    st = _ok(client.put(f'/api/processors/{pid}/slots/0', json={'deviceId': card}))
    cid = next(p for p in st['processors'] if p['id'] == pid)['slots'][0]['card']['id']
    if mode:
        _ok(client.put(f'/api/processors/{pid}/cards/{cid}', json={'mode': mode}))
    return pid, cid


def _add_box(client, pid, cid, device='novastar-cvt10', pair=False):
    st = _ok(client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                         json={'deviceId': device, 'pair': pair}), 201)
    card = next(p for p in st['processors'] if p['id'] == pid)['slots'][0]['card']
    return [b['id'] for b in card['cvts']]


def _state(client):
    return client.get('/api/processors').get_json()


def _raw_box(client, box_id):
    for proc in _state(client)['processors']:
        for slot in proc['slots']:
            for box in (slot.get('card') or {}).get('cvts') or []:
                if box['id'] == box_id:
                    return box
    return None


def _res_box(client, box_id):
    for proc in _state(client)['resolved']:
        for slot in proc['slots']:
            for box in (slot.get('card') or {}).get('cvts') or []:
                if box['id'] == box_id:
                    return box
    return None


def _link(client, pid, box, key, body):
    return client.put(f'/api/processors/{pid}/cvts/{box}/fiber-links/{key}', json=body)


def _box_fiber(client, pid, box, body):
    return client.put(f'/api/processors/{pid}/cvts/{box}/fiber', json=body)


def _new_tac(client, strands=12, link=None, **kw):
    body = dict(kind='tac', strands=strands, **kw)
    if link:
        body['link'] = link
    st = _ok(client.post('/api/fiber-cables', json=body), 201)
    return st['fiberCables'][-1]


def _links(client, box_id):
    return (_raw_box(client, box_id) or {}).get('fiberLinks')


# ── the store, through the Flask client ──────────────────────────────────

def test_a_tac_is_made_named_and_shared_by_strand_across_two_boxes(client):
    """A new TAC takes the first free letter show-wide, its fields as sent;
    a link picking it with no strands takes its next free ones - box A's
    Primary 1 takes 1-2, box B's 3-4 - and one TAC carries both."""
    pid, cid = _h9(client)
    a = _add_box(client, pid, cid)[0]
    b = _add_box(client, pid, cid)[-1]
    tac = _new_tac(client, 12, ft=1000, connector='ST',
                   link={'boxId': a, 'key': 'p1'})
    assert tac['name'] == 'TAC A' and tac['kind'] == 'tac'
    assert (tac['strands'], tac['ft'], tac['connector']) == (12, 1000, 'ST')
    assert tac['id'].startswith('fib')
    assert _links(client, a) == {'p1': {'cable': tac['id'], 'strands': [1, 2]}}
    _ok(_link(client, pid, b, 'p1', {'cable': tac['id']}))
    assert _links(client, b) == {'p1': {'cable': tac['id'], 'strands': [3, 4]}}
    # the resolved boxes carry the links, a second TAC is TAC B
    assert _res_box(client, b)['fiberLinks']['p1']['strands'] == [3, 4]
    assert _new_tac(client, 24)['name'] == 'TAC B'
    # strands picked by hand land as sent
    _ok(_link(client, pid, b, 'p1', {'cable': tac['id'], 'strands': [11, 12]}))
    assert _links(client, b)['p1']['strands'] == [11, 12]


def test_a_cvt4k_takes_two_primary_links(client):
    """A CVT4K-S takes 2 trunks in (catalog trunksIn), so it has Primary 1
    and Primary 2 - and no Primary 3."""
    pid, cid = _h9(client, H16)
    box = _add_box(client, pid, cid, 'novastar-cvt4k-s')[0]
    assert _res_box(client, box)['fiberLinkKeys'] == ['p1', 'p2']
    tac = _new_tac(client, 12, link={'boxId': box, 'key': 'p1'})
    _ok(_link(client, pid, box, 'p2', {'cable': tac['id']}))
    assert _links(client, box) == {'p1': {'cable': tac['id'], 'strands': [1, 2]},
                                   'p2': {'cable': tac['id'], 'strands': [3, 4]}}
    assert 'Primary 3' in _refused(_link(client, pid, box, 'p3', {'cable': tac['id']}))


def test_the_refusals_say_why_and_store_nothing(client):
    pid, cid = _h9(client)
    a, b = _add_box(client, pid, cid)[0], _add_box(client, pid, cid)[-1]
    tac = _new_tac(client, 6, link={'boxId': a, 'key': 'p1'})
    # a strand another link holds
    why = _refused(_link(client, pid, b, 'p1', {'cable': tac['id'], 'strands': [2, 3]}))
    assert 'strand 2 Orange is already used by' in why and 'Primary 1' in why, why
    # a count the link does not take
    assert 'needs 2 strands' in _refused(_link(client, pid, b, 'p1', {'cable': tac['id'], 'strands': [3]}))
    assert 'needs 2 strands' in _refused(_link(client, pid, b, 'p1', {'cable': tac['id'], 'strands': [3, 4, 5]}))
    # out of range
    assert 'strands 1-6' in _refused(_link(client, pid, b, 'p1', {'cable': tac['id'], 'strands': [6, 7]}))
    assert 'strands 1-6' in _refused(_link(client, pid, b, 'p1', {'cable': tac['id'], 'strands': [0, 3]}))
    # twice in one link
    assert 'named twice' in _refused(_link(client, pid, b, 'p1', {'cable': tac['id'], 'strands': [3, 3]}))
    # no such cable / link
    assert 'not in this project' in _refused(_link(client, pid, b, 'p1', {'cable': 'fib999'}))
    assert 'no link Backup 1' in _refused(_link(client, pid, b, 'b1', {'cable': tac['id']}))
    # an opticalCON on another box
    duo = _ok(client.post('/api/fiber-cables', json={'kind': 'opticalcon-quad', 'ownerBoxId': a}), 201)['fiberCables'][-1]
    assert duo['name'] == 'QUAD 1' and duo['ownerBoxId'] == a and duo['strands'] == 4
    why = _refused(_link(client, pid, b, 'p1', {'cable': duo['id']}))
    assert 'opticalCON feeds its own box only' in why, why
    # shrinking a TAC below a used strand
    _ok(_link(client, pid, b, 'p1', {'cable': tac['id'], 'strands': [5, 6]}))
    why = _refused(client.put(f'/api/fiber-cables/{tac["id"]}', json={'strands': 5}))
    assert 'Strand 6 is in use' in why, why
    assert _ok(client.put(f'/api/fiber-cables/{tac["id"]}', json={'strands': 6}))
    # a refused link wrote nothing
    assert _links(client, b) == {'p1': {'cable': tac['id'], 'strands': [5, 6]}}
    # no free strands left: C takes the last pair, D finds none
    c = _add_box(client, pid, cid)[-1]
    _ok(_link(client, pid, c, 'p1', {'cable': tac['id']}))
    assert _links(client, c)['p1']['strands'] == [3, 4]
    d = _add_box(client, pid, cid)[-1]
    assert 'no 2 free strands' in _refused(_link(client, pid, d, 'p1', {'cable': tac['id']}))


def test_a_refused_first_link_leaves_no_cable_behind(client):
    pid, cid = _h9(client)
    a = _add_box(client, pid, cid)[0]
    _new_tac(client, 12, link={'boxId': a, 'key': 'p1'})
    n = len(_state(client)['fiberCables'])
    why = _refused(client.post('/api/fiber-cables', json={
        'kind': 'tac', 'strands': 12, 'link': {'boxId': a, 'key': 'p1', 'strands': [1, 2, 3]}}))
    assert 'needs 2 strands' in why
    why = _refused(client.post('/api/fiber-cables', json={
        'kind': 'tac', 'strands': 12, 'link': {'boxId': a, 'key': 'p9'}}))
    assert 'no link Primary 9' in why
    assert len(_state(client)['fiberCables']) == n
    for body in ({'kind': 'tac'}, {'kind': 'tac', 'strands': 0}, {'kind': 'tac', 'strands': 2.5},
                 {'kind': 'tac', 'strands': True}, {'kind': 'fiber', 'strands': 12},
                 {'kind': 'mtp', 'strands': 12, 'connector': 'ST'},
                 {'kind': 'opticalcon-duo'}, {'kind': 'opticalcon-duo', 'ownerBoxId': a, 'strands': 4},
                 {'kind': 'tac', 'strands': 12, 'ft': 'far'}, {'kind': 'tac', 'strands': 12, 'labels': 'hex'}):
        _refused(client.post('/api/fiber-cables', json=body))
    assert len(_state(client)['fiberCables']) == n


def test_an_mtp_is_its_own_kind_and_assigns_strands_across_two_boxes_like_a_tac(client):
    """"if mtp/mpo is set to a box then we still need to set the strands
    just like with a tac" - and it is its own kind: MTP A, MTP B on their
    own letters beside the TACs', no connector, strands picked per link and
    shared by two boxes."""
    pid, cid = _h9(client)
    a, b = _add_box(client, pid, cid)[0], _add_box(client, pid, cid)[-1]
    tac = _new_tac(client, 12)
    st = _ok(client.post('/api/fiber-cables', json={'kind': 'mtp', 'strands': 12, 'ft': 300,
                                                     'link': {'boxId': a, 'key': 'p1'}}), 201)
    mtp = next(c for c in st['fiberCables'] if c['kind'] == 'mtp')
    assert mtp['name'] == 'MTP A' and tac['name'] == 'TAC A'
    assert 'connector' not in mtp and mtp['strands'] == 12 and mtp['ft'] == 300
    _ok(_link(client, pid, b, 'p1', {'cable': mtp['id'], 'strands': [7, 8]}))
    assert _links(client, a) == {'p1': {'cable': mtp['id'], 'strands': [1, 2]}}
    assert _links(client, b) == {'p1': {'cable': mtp['id'], 'strands': [7, 8]}}
    assert 'already used' in _refused(_link(client, pid, b, 'p1', {'cable': mtp['id'], 'strands': [2, 3]}))
    assert catalog.fiber_cable_type_text(mtp) == 'MTP 12'
    st = _ok(client.post('/api/fiber-cables', json={'kind': 'mtp', 'strands': 24}), 201)
    assert st['fiberCables'][-1]['name'] == 'MTP B'


def test_bidi_is_offered_on_novastar_and_megapixel_boxes_only_and_refits_the_links(client):
    pid, cid = _h9(client)
    a, b = _add_box(client, pid, cid)[0], _add_box(client, pid, cid)[-1]
    assert _res_box(client, a)['bidiAllowed'] is True
    tac = _new_tac(client, 12, link={'boxId': a, 'key': 'p1'})
    _ok(_link(client, pid, b, 'p1', {'cable': tac['id']}))           # 3-4
    # on: each link keeps its first strand
    _ok(_box_fiber(client, pid, a, {'bidi': True}))
    assert _raw_box(client, a)['bidi'] is True
    assert _links(client, a) == {'p1': {'cable': tac['id'], 'strands': [1]}}
    assert 'needs 1 strand' in _refused(_link(client, pid, a, 'p1', {'cable': tac['id'], 'strands': [1, 2]}))
    # off: the next strand where free ...
    _ok(_box_fiber(client, pid, a, {'bidi': False}))
    assert 'bidi' not in _raw_box(client, a)
    assert _links(client, a) == {'p1': {'cable': tac['id'], 'strands': [1, 2]}}
    # ... else the link is cleared
    _ok(_box_fiber(client, pid, a, {'bidi': True}))
    _ok(_link(client, pid, a, 'p1', {'cable': tac['id'], 'strands': [2]}))
    _ok(_link(client, pid, b, 'p1', {'cable': tac['id'], 'strands': [3, 4]}))
    _ok(_box_fiber(client, pid, a, {'bidi': False}))
    assert _links(client, a) is None
    # a Brompton box: no BiDi
    st = _ok(client.post('/api/processors', json={'deviceId': 'brompton-sx40'}), 201)
    sx = st['processors'][-1]
    xd = sx['slots'][0]['card']['cvts'][0]['id']
    assert _res_box(client, xd)['bidiAllowed'] is False
    why = _refused(_box_fiber(client, sx['id'], xd, {'bidi': True}))
    assert 'Brompton' in why and 'NovaStar and Megapixel' in why, why
    assert 'bidi' not in _raw_box(client, xd)
    # a Megapixel box: offered, from the catalog's vendor
    st = _ok(client.post('/api/processors', json={'deviceId': 'megapixel-helios-8k'}), 201)
    hel = st['processors'][-1]
    hcard = hel['slots'][0]['card']['id']
    rs = _add_box(client, hel['id'], hcard, 'megapixel-rs12')[0]
    assert _res_box(client, rs)['bidiAllowed'] is True
    _ok(_box_fiber(client, hel['id'], rs, {'bidi': True}))


def test_a_cable_goes_with_its_last_link_and_an_opticalcon_with_its_box(client):
    pid, cid = _h9(client)
    a, b = _add_box(client, pid, cid)[0], _add_box(client, pid, cid)[-1]
    tac = _new_tac(client, 12, link={'boxId': a, 'key': 'p1'})
    _ok(_link(client, pid, b, 'p1', {'cable': tac['id']}))
    # one link lets go: the TAC stays for the other
    _ok(_link(client, pid, a, 'p1', {'cable': None}))
    assert _links(client, a) is None
    assert [c['id'] for c in _state(client)['fiberCables']] == [tac['id']]
    # the last lets go: the TAC goes, and the key with it
    st = _ok(_link(client, pid, b, 'p1', {'cable': None}))
    assert st['fiberCables'] == []
    import app as app_module
    assert 'fiberCables' not in app_module.current_project
    # a cable made with no link yet is not pruned by the next edit
    spare = _new_tac(client, 12)
    _ok(client.put(f'/api/processors/{pid}/cvts/{a}', json={'name': 'SR'}))
    assert [c['id'] for c in _state(client)['fiberCables']] == [spare['id']]
    # box delete: its links go, its opticalCON goes, a TAC it last used goes
    tac2 = _new_tac(client, 12, link={'boxId': b, 'key': 'p1'})
    st = _ok(client.post('/api/fiber-cables', json={'kind': 'opticalcon-duo',
                                                     'link': {'boxId': a, 'key': 'p1'}}), 201)
    duo = st['fiberCables'][-1]
    assert duo['ownerBoxId'] == a and _links(client, a)['p1'] == {'cable': duo['id'], 'strands': [1, 2]}
    st = _ok(client.delete(f'/api/processors/{pid}/cvts/{a}'))
    assert duo['id'] not in [c['id'] for c in st['fiberCables']]
    st = _ok(client.delete(f'/api/processors/{pid}/cvts/{b}'))
    assert tac2['id'] not in [c['id'] for c in st['fiberCables']]
    assert [c['id'] for c in st['fiberCables']] == [spare['id']]


def test_a_processor_delete_prunes_the_same_way(client):
    pid, cid = _h9(client)
    a = _add_box(client, pid, cid)[0]
    tac = _new_tac(client, 12, link={'boxId': a, 'key': 'p1'})
    st = _ok(client.delete(f'/api/processors/{pid}'))
    assert tac['id'] not in [c['id'] for c in st['fiberCables']]


def test_fib_ids_come_off_the_one_counter_and_the_sync_counts_them(client):
    pid, cid = _h9(client)
    a = _add_box(client, pid, cid)[0]
    tac = _new_tac(client, 12, link={'boxId': a, 'key': 'p1'})
    st = _ok(client.post('/api/snakes', json={'members': [{'kind': 'cvt', 'id': a, 'socket': 1}]}), 201)
    snk = st['snakes'][-1]['id']
    b = _add_box(client, pid, cid)[-1]
    mtp = _ok(client.post('/api/fiber-cables', json={'kind': 'mtp', 'strands': 12}), 201)['fiberCables'][-1]
    ids = [pid, cid, a, b, snk, tac['id'], mtp['id']]
    assert snk.startswith('snk') and mtp['id'].startswith('fib')
    nums = [int(''.join(ch for ch in i if ch.isdigit()) or 0) for i in ids]
    assert len(set(nums)) == len(nums), ids
    # the sync seeds above a fib id that outruns the tree
    project = {'processors': [], 'fiberCables': [{'id': 'fib41', 'kind': 'tac', 'strands': 12}]}
    assert catalog.sync_next_processor_seq(project) == 42
    assert catalog.sync_next_processor_seq({'fiberCables': [{'id': 'fib7'}],
                                            'next_processor_seq': 3}) == 8
    # and a project with no fiber, no processors, no counter is untouched
    bare = {'layers': []}
    catalog.sync_next_processor_seq(bare)
    assert bare == {'layers': []}


def test_undo_restores_the_cables_and_the_links(client):
    """The undo snapshot is the whole project PUT back: a pruned cable and
    the links that named it come back together, and the counter never
    hands its id out again."""
    pid, cid = _h9(client)
    a = _add_box(client, pid, cid)[0]
    tac = _new_tac(client, 12, link={'boxId': a, 'key': 'p1'})
    snapshot = copy.deepcopy(client.get('/api/project').get_json())
    assert snapshot['fiberCables'][0]['id'] == tac['id']
    _ok(client.delete(f'/api/processors/{pid}/cvts/{a}'))
    assert 'fiberCables' not in client.get('/api/project').get_json()
    snapshot.pop('next_processor_seq', None)
    _ok(client.put('/api/project', json=snapshot))
    assert [c['id'] for c in _state(client)['fiberCables']] == [tac['id']]
    assert _links(client, a) == {'p1': {'cable': tac['id'], 'strands': [1, 2]}}
    fresh = _new_tac(client, 12)
    assert fresh['id'] != tac['id']


def test_cable_edits_rename_recount_and_name_strands(client):
    pid, cid = _h9(client)
    a = _add_box(client, pid, cid)[0]
    tac = _new_tac(client, 12, link={'boxId': a, 'key': 'p1'})
    url = f'/api/fiber-cables/{tac["id"]}'
    c = _ok(client.put(url, json={'name': 'SR TRUNK', 'ft': '250', 'connector': 'LC duplex',
                                  'labels': 'numbers', 'subunits': True}))['fiberCables'][0]
    assert (c['name'], c['ft'], c['connector'], c['labels'], c['subunits']) == \
        ('SR TRUNK', 250, 'LC duplex', 'numbers', True)
    c = _ok(client.put(url, json={'strandName': {'strand': 3, 'name': ' spare pair '}}))['fiberCables'][0]
    assert c['strandNames'] == {'3': 'spare pair'}
    c = _ok(client.put(url, json={'strandName': {'strand': 3, 'name': ''}}))['fiberCables'][0]
    assert c['strandNames'] == {}
    assert 'no strand 13' in _refused(client.put(url, json={'strandName': {'strand': 13, 'name': 'x'}}))
    c = _ok(client.put(url, json={'ft': None, 'connector': '', 'name': ''}))['fiberCables'][0]
    assert 'ft' not in c or c['ft'] is None
    assert 'connector' not in c and c['name'] == 'SR TRUNK'
    assert 'kind cannot change' in _refused(client.put(url, json={'kind': 'mtp'}))
    assert client.put('/api/fiber-cables/fib999', json={'name': 'x'}).status_code == 404


# ── binding a backup record to its physical box ─────────────────────────

def test_a_novastar_backup_box_is_bound_automatically_and_can_be_unbound(client):
    """An H_4xfiber in copy/backup pairs a new box with a backup on OPT 3
    (backupOf). The backup record IS the primary taking a second fiber: it
    is bound (boundTo / boundBackup), the primary gains Backup 1, and the
    backup's pick defaults to the primary's TAC at the next free strands."""
    pid, cid = _h9(client, H4, 'copy-backup')
    a, ab = _add_box(client, pid, cid, pair=True)
    res_a, res_ab = _res_box(client, a), _res_box(client, ab)
    assert res_ab['boundTo'] == a and res_ab['boundManual'] is False
    assert res_a['boundBackup'] == ab and res_a['fiberLinkKeys'] == ['p1', 'b1']
    assert res_ab['fiberLinkKeys'] == []
    tac = _new_tac(client, 12, link={'boxId': a, 'key': 'p1'})
    _ok(_link(client, pid, a, 'b1', {}))
    assert _links(client, a) == {'p1': {'cable': tac['id'], 'strands': [1, 2]},
                                 'b1': {'cable': tac['id'], 'strands': [3, 4]}}
    # the bound record takes no link of its own
    assert 'its fiber is set there' in _refused(_link(client, pid, ab, 'p1', {'cable': tac['id']}))
    # a backup link can take a different TAC
    tac_b = _new_tac(client, 12)
    _ok(_link(client, pid, a, 'b1', {'cable': tac_b['id']}))
    assert _links(client, a)['b1'] == {'cable': tac_b['id'], 'strands': [1, 2]}
    # unbind: the backup link goes (and TAC B with it, its last link)
    st = _ok(_box_fiber(client, pid, ab, {'unbound': True}))
    assert _raw_box(client, ab)['unbound'] is True
    assert _res_box(client, ab)['boundTo'] is None
    assert _res_box(client, a)['fiberLinkKeys'] == ['p1']
    assert _links(client, a) == {'p1': {'cable': tac['id'], 'strands': [1, 2]}}
    assert tac_b['id'] not in [c['id'] for c in st['fiberCables']]
    # unbound, the backup box has links of its own
    _ok(_link(client, pid, ab, 'p1', {'cable': tac['id']}))
    # rebind: the flag clears, its own links go
    _ok(_box_fiber(client, pid, ab, {'unbound': False}))
    assert 'unbound' not in _raw_box(client, ab)
    assert _res_box(client, ab)['boundTo'] == a and _links(client, ab) is None
    # a box that backs up nothing has nothing to unbind
    assert 'nothing to unbind' in _refused(_box_fiber(client, pid, a, {'unbound': True}))
    # deleting the primary: the backup is its own box again
    _ok(client.delete(f'/api/processors/{pid}/cvts/{a}'))
    raw = _raw_box(client, ab)
    assert 'backupOf' not in raw and 'unbound' not in raw
    assert _res_box(client, ab)['boundTo'] is None


def test_an_sx40s_backup_xd_is_the_same_xd_taking_a_second_fiber(client):
    """Brompton's adjacent pairing: with redundancy on, the XD on trunk B
    backs up A's - "an SX40's backup XD on the next trunk is the SAME XD
    taking a second fiber" - so B is bound to A, D to C."""
    st = _ok(client.post('/api/processors', json={'deviceId': 'brompton-sx40'}), 201)
    pid = st['processors'][-1]['id']
    xds = [b['id'] for b in st['processors'][-1]['slots'][0]['card']['cvts']]
    assert all(_res_box(client, x)['boundTo'] is None for x in xds)
    _ok(client.put(f'/api/processors/{pid}', json={'redundancy': True}))
    res = [_res_box(client, x) for x in xds]
    assert [r['boundTo'] for r in res] == [None, xds[0], None, xds[2]]
    assert [r['boundBackup'] for r in res] == [xds[1], None, xds[3], None]
    assert res[0]['fiberLinkKeys'] == ['p1', 'b1']
    tac = _new_tac(client, 12, link={'boxId': xds[0], 'key': 'p1'})
    _ok(_link(client, pid, xds[0], 'b1', {}))
    assert _links(client, xds[0])['b1'] == {'cable': tac['id'], 'strands': [3, 4]}
    # redundancy off: no binding, the backup link lets go
    _ok(client.put(f'/api/processors/{pid}', json={'redundancy': False}))
    assert _res_box(client, xds[1])['boundTo'] is None
    assert _links(client, xds[0]) == {'p1': {'cable': tac['id'], 'strands': [1, 2]}}


def _paired_h9s(client):
    """Two H9s with an H_16xRJ45+2xfiber and a CVT10 each. The first is
    the main; the second backs it up whole (the main's cards point 1:1 at
    the backup's - backupProcessorId on the main names its backup)."""
    main, mcard = _h9(client, H16)
    back, bcard = _h9(client, H16)
    primary = _add_box(client, main, mcard)[0]
    backup = _add_box(client, back, bcard)[0]
    _ok(client.put(f'/api/processors/{main}', json={'redundancy': True,
                                                    'backupProcessorId': back}))
    return main, back, primary, backup


def test_a_backup_processors_box_is_bound_by_hand_and_cleared_with_its_primary(client):
    main, back, primary, backup = _paired_h9s(client)
    targets = _res_box(client, backup)['fiberBindTargets']
    assert [t['id'] for t in targets] == [primary], targets
    assert _res_box(client, backup)['boundTo'] is None
    # the main's box is on no backup card: it is not bound by hand
    assert _res_box(client, primary)['fiberBindTargets'] is None
    assert 'bound by hand' in _refused(_box_fiber(client, main, primary, {'boundTo': backup}))
    assert 'not bound already' in _refused(_box_fiber(client, back, backup, {'boundTo': 'cvt999'}))
    _ok(_box_fiber(client, back, backup, {'boundTo': primary}))
    assert _raw_box(client, backup)['boundTo'] == primary
    res = _res_box(client, backup)
    assert res['boundTo'] == primary and res['boundManual'] is True
    assert _res_box(client, primary)['fiberLinkKeys'] == ['p1', 'b1']
    # the backup link lives on the primary, and may take another TAC
    tac = _new_tac(client, 12, link={'boxId': primary, 'key': 'p1'})
    _ok(_link(client, main, primary, 'b1', {}))
    assert _links(client, primary)['b1'] == {'cable': tac['id'], 'strands': [3, 4]}
    # the primary's delete clears the binding
    _ok(client.delete(f'/api/processors/{main}/cvts/{primary}'))
    assert 'boundTo' not in _raw_box(client, backup)
    assert _res_box(client, backup)['boundTo'] is None


def test_a_manual_binding_goes_when_the_backup_relation_does(client):
    main, back, primary, backup = _paired_h9s(client)
    _ok(_box_fiber(client, back, backup, {'boundTo': primary}))
    # the pairing released: the relation is gone, and so is the binding
    _ok(client.put(f'/api/processors/{main}', json={'backupProcessorId': ''}))
    assert 'boundTo' not in _raw_box(client, backup)
    # unbind by hand: boundTo null
    _ok(client.put(f'/api/processors/{main}', json={'backupProcessorId': back}))
    _ok(_box_fiber(client, back, backup, {'boundTo': primary}))
    _ok(_box_fiber(client, back, backup, {'boundTo': None}))
    assert 'boundTo' not in _raw_box(client, backup)


# ── strand names (TIA-598-D) ─────────────────────────────────────────────

@pytest.mark.parametrize('n, name', [
    (1, '1 Blue'), (12, '12 Aqua'), (13, '13 Blue/Black'), (14, '14 Orange/Black'),
    (20, '20 Black/White'), (24, '24 Aqua/Black'), (26, '26 Orange/Black x2'),
    (32, '32 Black/White x2'), (48, '48 Aqua/Black x3'), (49, '49 Blue/Black x4'),
])
def test_strand_names_follow_tia_598(n, name):
    assert catalog.fiber_strand_name(n) == name


def test_strand_names_in_subunits_numbers_and_renamed():
    assert catalog.fiber_strand_name(14, {'subunits': True}) == 'Orange unit · 2 Orange'
    assert catalog.fiber_strand_name(3, {'subunits': True}) == 'Blue unit · 3 Green'
    assert catalog.fiber_strand_name(25, {'subunits': True}) == 'Green unit · 1 Blue'
    assert catalog.fiber_strand_name(14, {'labels': 'numbers'}) == '14'
    assert catalog.fiber_strand_name(14, {'labels': 'numbers', 'subunits': True}) == '14'
    assert catalog.fiber_strand_name(3, {'strandNames': {'3': 'SR spare'}}) == 'SR spare'
    assert catalog.fiber_strand_name(3, {'strandNames': {'3': '  '}}) == '3 Green'


def test_a_settle_on_a_project_with_no_fiber_changes_nothing():
    project = {'processors': [], 'layers': []}
    assert catalog.settle_fiber(project) is False
    assert project == {'processors': [], 'layers': []}
    project = {'fiberCables': []}
    catalog.settle_fiber(project)
    assert 'fiberCables' not in project


# ── the browser: the Fiber section, the pull sheet, the binder ──────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

# SR RACK, an H9: slot 0 an H_4xfiber (independent) with CVT10s A-D, one
# per OPT. BK RACK, a second H9: an H_4xfiber in copy/backup with a CVT10
# pair - BK1 on OPT 1, its backup (bound to it) on OPT 3 - both at "SR
# Beach". An SX40 beside them (Brompton: no BiDi). Four walls W1-W4, 8 x 12
# cabinets of 200 px on the Legacy platform (six ports each), are placed
# one on each of A-D's spans, so every box delivers ports.
SEED_JS = """async () => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.fiberCables;
    delete proj.pullSheetEdits;
    await j('PUT', '/api/project', proj);
    for (const name of ['W1', 'W2', 'W3', 'W4']) {
        await j('POST', '/api/layer/add', {name, columns: 8, rows: 12,
                                           cabinet_width: 200, cabinet_height: 200,
                                           processorType: 'novastar-armor'});
    }
    let st = await j('POST', '/api/processors', {deviceId: 'novastar-h9', name: 'SR RACK'});
    const pid = st.processors[0].id;
    st = await j('PUT', `/api/processors/${pid}/slots/0`, {deviceId: 'novastar-card-h-4xfiber'});
    const cardId = st.processors[0].slots[0].card.id;
    await j('PUT', `/api/processors/${pid}/cards/${cardId}`, {name: 'SR'});
    for (let i = 0; i < 4; i++) {
        st = await j('POST', `/api/processors/${pid}/cards/${cardId}/cvts`, {deviceId: 'novastar-cvt10', pair: false});
    }
    const boxes = st.processors[0].slots[0].card.cvts.map(b => b.id);
    st = await j('POST', '/api/processors', {deviceId: 'novastar-h9', name: 'BK RACK'});
    const bk = st.processors[1].id;
    st = await j('PUT', `/api/processors/${bk}/slots/0`, {deviceId: 'novastar-card-h-4xfiber'});
    const bkCard = st.processors[1].slots[0].card.id;
    await j('PUT', `/api/processors/${bk}/cards/${bkCard}`, {mode: 'copy-backup'});
    st = await j('POST', `/api/processors/${bk}/cards/${bkCard}/cvts`, {deviceId: 'novastar-cvt10'});
    const [e, f] = st.processors[1].slots[0].card.cvts.map(b => b.id);
    await j('PUT', `/api/processors/${bk}/cvts/${e}`, {name: 'BK1', location: 'SR Beach'});
    await j('PUT', `/api/processors/${bk}/cvts/${f}`, {location: 'SR Beach'});
    st = await j('POST', '/api/processors', {deviceId: 'brompton-sx40'});
    const sx = st.processors[2];
    const app = window.app;
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('fiber_setup');
    app.selectLayer(app.project.layers[0]);
    await app.refreshProcessors();
    for (let i = 0; i < 4; i++) {
        await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
            {layerId: String(app.project.layers[i].id), cardId,
             firstPort: i * 8 + 1, lastPort: i * 8 + 8});
    }
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    app.renderHardwareDock();
    app.resetHistory('Fiber Seed');
    const sockets = (app._assignment.screens || []).flatMap(s => (s.ports || []).map(pt => pt.port));
    return { procId: pid, bkId: bk, cardId, boxes, e, f, sxId: sx.id,
             xd: sx.slots[0].card.cvts[0].id,
             sockets };
}"""

OPEN_SHEET_JS = """(boxId) => {
    const up = () => document.querySelector(`[data-lrd-cable-sheet="cvt:${boxId}"]`);
    if (!up()) {
        const btn = document.querySelector(`[data-lrd-field="data-cable-sheet-${boxId}"]`);
        if (!btn) return false;
        btn.scrollIntoView();
        btn.click();
    }
    return !!up();
}"""

SECTION_JS = """(boxId) => {
    const sec = document.querySelector(`[data-lrd-fiber-row="${boxId}"]`);
    if (!sec) return null;
    return {
        caption: sec.querySelector('.hw-dock-cable-fiber-cap').textContent,
        bidi: !!sec.querySelector(`[data-lrd-field="fiber-bidi-${boxId}"]`),
        rows: [...sec.querySelectorAll('.hw-dock-fiber-link')].map(r => ({
            role: r.querySelector('.hw-dock-fiber-role').textContent,
            backup: r.classList.contains('hw-dock-fiber-link-backup'),
            value: r.querySelector('select').value,
            options: [...r.querySelector('select').options].map(o => o.textContent),
            chips: [...r.querySelectorAll('.hw-dock-fiber-strand')].map(c => c.textContent),
        })),
        bound: (sec.querySelector('.hw-dock-fiber-bound-text') || {}).textContent || null,
        legacy: (sec.querySelector('.hw-dock-fiber-legacy-text') || {}).textContent || null,
        first: sec.parentElement && sec.parentElement.firstElementChild === sec,
    };
}"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(500)
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(1200)
    ids['errors'] = errors
    yield pg, ids
    context.close()


def _served(pg):
    return pg.evaluate("async () => (await (await fetch('/api/processors')).json())")


def _wait(pg, ok, timeout=15000):
    waited = 0
    while waited < timeout:
        st = _served(pg)
        if ok(st):
            pg.wait_for_timeout(300)
            return st
        pg.wait_for_timeout(200)
        waited += 200
    return _served(pg)


def _box_links(st, box_id):
    for proc in st['processors']:
        for slot in proc['slots']:
            for box in (slot.get('card') or {}).get('cvts') or []:
                if box['id'] == box_id:
                    return box.get('fiberLinks')
    return None


def _section(pg, box_id):
    assert pg.evaluate(OPEN_SHEET_JS, box_id), f'the cable sheet of {box_id} did not open'
    pg.wait_for_timeout(200)
    return pg.evaluate(SECTION_JS, box_id)


def test_the_fiber_section_builds_a_tac_through_new_tac(page):
    """The box's ≡ sheet opens on its Fiber section - the first block -
    with Primary 1. "New TAC…" asks the strand count, the length, then the
    ends; the TAC is made on the link in ONE step (one history entry) and
    takes strands 1-2, swatched and named."""
    pg, ids = page
    assert sorted(set(ids['sockets'])) == [n for k in range(4) for n in range(k * 8 + 1, k * 8 + 7)], ids['sockets']
    a = ids['boxes'][0]
    sec = _section(pg, a)
    assert sec['first'], sec
    assert sec['caption'] == 'Fiber · CVT10 A', sec
    assert [(r['role'], r['backup']) for r in sec['rows']] == [('Primary 1', False)]
    opts = sec['rows'][0]['options']
    assert opts == ['New TAC…', 'New MTP…', 'New opticalCON DUO…', 'New opticalCON QUAD…', 'None'], opts
    assert sec['rows'][0]['value'] == ''
    index = pg.evaluate('() => window.app.historyIndex')
    pg.locator(f'[data-lrd-field="fiber-link-cable-{a}-p1"]').select_option('new:tac')
    pg.wait_for_timeout(300)
    pg.locator(f'[data-lrd-field="fiber-new-{a}-p1-strands-24"]').click()
    pg.wait_for_timeout(300)
    ft = pg.locator(f'[data-lrd-field="fiber-new-{a}-p1-ft"]')
    assert pg.evaluate('() => document.activeElement.dataset.lrdField') == f'fiber-new-{a}-p1-ft'
    ft.fill('1000')
    ft.press('Enter')
    pg.wait_for_timeout(300)
    pg.locator(f'[data-lrd-field="fiber-new-{a}-p1-conn-ST"]').click()
    st = _wait(pg, lambda s: (s.get('fiberCables') or []))
    tac = st['fiberCables'][0]
    assert (tac['name'], tac['kind'], tac['strands'], tac['ft'], tac['connector']) == \
        ('TAC A', 'tac', 24, 1000, 'ST'), tac
    assert _box_links(st, a) == {'p1': {'cable': tac['id'], 'strands': [1, 2]}}
    pg.wait_for_timeout(400)
    assert pg.evaluate('() => window.app.history[window.app.historyIndex].action') == 'New TAC'
    assert pg.evaluate('() => window.app.historyIndex') == index + 1
    sec = _section(pg, a)
    assert sec['rows'][0]['value'] == tac['id']
    assert sec['rows'][0]['chips'] == ['1 Blue', '2 Orange'], sec
    assert "TAC A · 24 · 1000' · ST" in sec['rows'][0]['options']
    assert ids['errors'] == []


def test_picking_the_tac_on_other_boxes_fills_the_next_free_strands(page):
    """B, C and D pick TAC A and take 3-4, 5-6, 7-8. BK1 on the other
    processor takes 9-10; its backup record is bound to it, so BK1 has a
    tinted Backup 1 that lists its primary's TAC first and takes 11-12, and
    the backup record says where its fiber is set. A strand chip changes
    through a pick where the strands other links hold are disabled."""
    pg, ids = page
    a, b, c, d = ids['boxes']
    tac = _served(pg)['fiberCables'][0]
    for box, want in ((b, [3, 4]), (c, [5, 6]), (d, [7, 8]), (ids['e'], [9, 10])):
        _section(pg, box)
        pg.locator(f'[data-lrd-field="fiber-link-cable-{box}-p1"]').select_option(tac['id'])
        st = _wait(pg, lambda s, box=box: _box_links(s, box))
        assert _box_links(st, box) == {'p1': {'cable': tac['id'], 'strands': want}}, box
    e, f = ids['e'], ids['f']
    sec = _section(pg, e)
    assert [(r['role'], r['backup']) for r in sec['rows']] == [('Primary 1', False), ('Backup 1', True)]
    assert sec['rows'][1]['value'] == '' and sec['rows'][1]['options'][0].startswith('TAC A'), sec
    pg.locator(f'[data-lrd-field="fiber-link-cable-{e}-b1"]').select_option(tac['id'])
    st = _wait(pg, lambda s: 'b1' in (_box_links(s, e) or {}))
    assert _box_links(st, e)['b1'] == {'cable': tac['id'], 'strands': [11, 12]}
    sec = _section(pg, f)
    assert sec['bound'] == 'Bound to BK1; its fiber is set there.', sec
    assert sec['rows'] == [] and not sec['bidi']
    sec = _section(pg, b)
    assert sec['rows'][0]['chips'] == ['3 Green', '4 Brown'], sec
    pg.locator(f'[data-lrd-field="fiber-strand-{b}-p1-0"]').click()
    pick = pg.locator(f'[data-lrd-field="fiber-strand-pick-{b}-p1-0"]')
    disabled = pick.evaluate("s => [...s.options].filter(o => o.disabled).map(o => o.value)")
    assert disabled == ['1', '2', '5', '6', '7', '8', '9', '10', '11', '12'], disabled
    pick.select_option('13')
    st = _wait(pg, lambda s: (_box_links(s, b) or {}).get('p1', {}).get('strands') == [13, 4])
    assert _box_links(st, b)['p1']['strands'] == [13, 4]
    sec = _section(pg, b)
    assert sec['rows'][0]['chips'] == ['13 Blue/Black', '4 Brown'], sec
    assert ids['errors'] == []


def test_the_bidi_switch_shows_only_for_novastar_and_megapixel(page):
    pg, ids = page
    a = ids['boxes'][0]
    assert _section(pg, a)['bidi'] is True
    assert _section(pg, ids['xd'])['bidi'] is False
    _section(pg, a)
    pg.locator(f'[data-lrd-field="fiber-bidi-{a}"]').check()
    st = _wait(pg, lambda s: len((_box_links(s, a) or {}).get('p1', {}).get('strands', [])) == 1)
    assert _box_links(st, a)['p1']['strands'] == [1]
    _section(pg, a)
    pg.locator(f'[data-lrd-field="fiber-bidi-{a}"]').uncheck()
    st = _wait(pg, lambda s: len((_box_links(s, a) or {}).get('p1', {}).get('strands', [])) == 2)
    assert _box_links(st, a)['p1']['strands'] == [1, 2]
    assert ids['errors'] == []


PUT_JS = """async ([url, body]) => {
    const r = await fetch(url, {method: url.endsWith('fiber-cables') ? 'POST' : 'PUT',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    const out = await r.json();
    await window.app.refreshProcessors(); await window.app.refreshPortAssignment();
    return out;
}"""

FIT_JS = """(titles) => {
    const app = window.app;
    const opts = { sheet: 'tabloid', palette: 'colour', sides: {power: false, data: true},
                   scope: {kind: 'show'}, cover: false, pull: true, hardware: true, titleBlock: true };
    const plan = app.planBinder(opts);
    const out = {};
    for (const t of titles) {
        const i = plan.findIndex(p => p.title.startsWith(t));
        if (i < 0) { out[t] = null; continue; }
        out[t] = app.renderBinderPage(opts, i).textInfo;
    }
    return out;
}"""


def test_the_binder_maps_every_strand_and_summarises_each_box(page):
    """The strand map sits on the page of the processor feeding the cable's
    first link and nowhere else - TAC A on SR RACK's, "Also on BK RACK" on
    its own line under the header; TAC B (BK1's Backup 1 only) on BK RACK's.
    Every strand is listed, "spare" where no link holds it. The box's fiber
    reads SHORT - "TAC A 9-10 · backup TAC B 1-2", the bound backup record
    "same box as BK1" - in its band and in the Breakout boxes table, and on
    a tabloid sheet nothing of it is shrunk or cut: FIBER wraps at its " · "
    instead."""
    pg, ids = page
    made = pg.evaluate(PUT_JS, ['/api/fiber-cables', {
        'kind': 'tac', 'strands': 6, 'ft': 1000, 'connector': 'LC duplex',
        'link': {'boxId': ids['e'], 'key': 'b1'}}])
    tac_b = made['fiberCables'][-1]
    assert tac_b['name'] == 'TAC B', made['fiberCables']
    pg.wait_for_timeout(300)
    out = pg.evaluate("""(ids) => {
        const app = window.app;
        const boxes = ids.boxes.concat([ids.e, ids.f]).map(id => app._dockFindCvt(id).cvt);
        const maps = (pid) => app._bStrandMaps(app._processorsResolved.find(p => p.id === pid));
        const shape = (m) => ({ title: m.title, note: m.note, rows: m.rows.map(r => r.cells),
                                swatch: m.rows[0].swatch, sw13: (m.rows[12] || {}).swatch });
        return { bands: boxes.map(b => app._bBoxBandText(b)),
                 fiber: boxes.map(b => app._bBoxFiberText(b)),
                 maps: maps(ids.procId).map(shape), bk: maps(ids.bkId).map(shape),
                 sx: maps(ids.sxId).length };
    }""", ids)
    bands, fiber = out['bands'], out['fiber']
    assert bands[0] == 'CVT10 A · OPT 1 · 8 ports · TAC A 1-2', bands
    assert fiber[1] == 'TAC A 4, 13', fiber
    assert fiber[4] == 'TAC A 9-10 · backup TAC B 1-2', fiber
    assert fiber[5] == 'same box as BK1', fiber
    assert bands[5].endswith(' · same box as BK1'), bands
    assert len(out['maps']) == 1 and out['sx'] == 0
    m = out['maps'][0]
    assert m['title'] == "Strand map · TAC A · TAC 24 · ST · 1000'", m['title']
    assert m['note'] == 'Also on BK RACK', m
    rows = m['rows']
    assert len(rows) == 24
    assert rows[0] == ['1 Blue', 'CVT10 A', 'Primary 1']
    assert rows[2] == ['3 Green', 'spare', '']
    assert rows[3] == ['4 Brown', 'CVT10 B', 'Primary 1']
    assert rows[8] == ['9 Yellow', 'CVT10 BK1', 'Primary 1']
    assert rows[10] == ['11 Rose', 'spare', '']
    assert rows[12] == ['13 Blue/Black', 'CVT10 B', 'Primary 1']
    assert rows[23] == ['24 Aqua/Black', 'spare', '']
    assert m['swatch'] == {'base': '#1F5FA8', 'tracer': None}
    assert m['sw13'] == {'base': '#1F5FA8', 'tracer': '#1A1A1A'}
    assert [(x['title'], x['note']) for x in out['bk']] == \
        [("Strand map · TAC B · TAC 6 · LC duplex · 1000'", '')], out['bk']
    assert out['bk'][0]['rows'][:3] == [['1 Blue', 'CVT10 BK1', 'Backup 1'],
                                        ['2 Orange', 'CVT10 BK1', 'Backup 1'],
                                        ['3 Green', 'spare', '']]
    # the fit, on the painted sheets: every fiber text whole, at the cell's
    # own size (never shrunk), nothing on the sheets cut to an ellipsis
    fit = pg.evaluate(FIT_JS, ['Processors -', 'W1 - Data - Front View'])
    procs, data = fit['Processors -'], fit['W1 - Data - Front View']
    assert procs and data, list(fit)
    for info in (procs, data):
        assert not [t for t in info if t['text'].endswith('…')], [t['text'] for t in info if t['text'].endswith('…')]
    size = {t['text']: t['size'] for t in procs}
    for text in ('TAC A 1-2', 'TAC A 4, 13', 'same box as BK1', 'Also on BK RACK'):
        assert size.get(text) == 24, (text, sorted(k for k in size if 'TAC' in k or 'BK' in k))
    # the two-link box wraps at its " · ", each line whole at the cell's
    # size (a list cell is logged as the one text it drew)
    assert size.get('TAC A 9-10 · backup TAC B 1-2') == 24, sorted(k for k in size if 'TAC' in k)
    lines = pg.evaluate("""() => {
        const app = window.app;
        const book = { measureCtx: document.createElement('canvas').getContext('2d') };
        return app._bCellLines(book, 'TAC A 9-10 · backup TAC B 1-2', 24, 400, 200, 2);
    }""")
    assert all(not t.endswith('…') and 'more' not in t for t in lines), lines
    assert size.get("STRAND MAP · TAC A · TAC 24 · ST · 1000'") == 25, sorted(k for k in size if 'STRAND' in k)
    assert size.get("STRAND MAP · TAC B · TAC 6 · LC DUPLEX · 1000'") == 25
    band = [t for t in data if t['text'] == 'CVT10 A · OPT 1 · 8 ports · TAC A 1-2']
    assert band and band[0]['size'] == 24, [t for t in data if 'CVT10' in t['text']]
    assert ids['errors'] == []


LIST_JS = """() => {
    const app = window.app;
    app._circuitTailCache = null;
    const out = JSON.parse(JSON.stringify(app.buildPullList()));
    const rows = (list) => list.map(r => [r.type, r.length, r.qty, r.label, r.notes]);
    return { totals: rows(out.totals),
             hardware: out.hardware.filter(h => h.kind === 'processor').map(h => [h.id, rows(h.rows)]) };
}"""




def test_the_pull_sheet_counts_a_shared_tac_once_and_no_second_box_for_a_bound_backup(page):
    """TAC A is taken by five links on five boxes and two processors: it is
    ONE row, "TAC 24 · ST" 1000'. TAC B, taken only by a backup link on a
    box no screen port reaches, is one row too. The CVT10s count A-D and BK1 - five; BK1's
    bound backup is BK1 taking a second fiber and adds none. A typed 1.3
    note does not print on a box with a link, and prints as before once the
    box has none. An MTP 12 shared by two boxes is one "MTP 12" row."""
    pg, ids = page
    a, b, c, d = ids['boxes']
    pid = ids['procId']
    pg.evaluate(PUT_JS, [f'/api/processors/{pid}/cvts/{a}', {'fiberType': '12 Tac Fiber', 'fiberFt': 250}])
    pg.evaluate(PUT_JS, [f'/api/processors/{pid}/cvts/{d}', {'fiberType': 'OLD', 'fiberFt': 90}])
    pg.wait_for_timeout(300)
    out = pg.evaluate(LIST_JS)
    tacs = [r for r in out['totals'] if r[0].startswith('TAC 24')]
    assert tacs == [['TAC 24 · ST', "1000'", 1, 'TAC A', '']], out['totals']
    assert sum(r[2] for r in out['totals'] if r[0] == 'CVT10') == 5, out['totals']
    assert not [r for r in out['totals'] if r[0] in ('12 Tac Fiber', 'OLD')], out['totals']
    hw = dict(out['hardware'])[pid]
    assert ['TAC 24 · ST', "1000'", 1, 'TAC A', ''] in hw, hw
    # TAC B, taken ONLY by BK1's Backup 1 - a box no screen's port comes
    # out of - is still one row, on BK RACK's list and in the totals
    assert [r for r in out['totals'] if r[0] == 'TAC 6 · LC duplex'] == \
        [['TAC 6 · LC duplex', "1000'", 1, 'TAC B', '']], out['totals']
    bk = dict(out['hardware'])[ids['bkId']]
    assert ['TAC 6 · LC duplex', "1000'", 1, 'TAC B', ''] in bk, bk
    assert not [r for r in hw if r[0].startswith('TAC 6')], hw
    # D lets go of its link: its typed note prints again
    pg.evaluate(PUT_JS, [f'/api/processors/{pid}/cvts/{d}/fiber-links/p1', {'cable': None}])
    pg.wait_for_timeout(300)
    out = pg.evaluate(LIST_JS)
    assert ['OLD', "90'", 1, 'CVT10 D', ''] in out['totals'], out['totals']
    assert not [r for r in out['totals'] if r[0] == '12 Tac Fiber'], out['totals']
    # an MTP 12, shared by B and C by strand
    made = pg.evaluate(PUT_JS, ['/api/fiber-cables', {'kind': 'mtp', 'strands': 12, 'ft': 300,
                                                      'link': {'boxId': b, 'key': 'p1'}}])
    mtp = next(x for x in made['fiberCables'] if x['kind'] == 'mtp')
    pg.evaluate(PUT_JS, [f'/api/processors/{pid}/cvts/{c}/fiber-links/p1',
                         {'cable': mtp['id'], 'strands': [5, 6]}])
    pg.wait_for_timeout(300)
    st = _served(pg)
    assert _box_links(st, b)['p1'] == {'cable': mtp['id'], 'strands': [1, 2]}
    assert _box_links(st, c)['p1'] == {'cable': mtp['id'], 'strands': [5, 6]}
    out = pg.evaluate(LIST_JS)
    assert [r for r in out['totals'] if r[0].startswith('MTP')] == [['MTP 12', "300'", 1, 'MTP A', '']], out['totals']
    assert [r for r in out['totals'] if r[0].startswith('TAC 24')] == [['TAC 24 · ST', "1000'", 1, 'TAC A', '']]
    assert ids['errors'] == []


def test_a_link_cleared_in_the_section_is_one_entry_and_undo_brings_it_back(page):
    pg, ids = page
    a = ids['boxes'][0]
    before = _box_links(_served(pg), a)
    assert before and before['p1']['strands'] == [1, 2], before
    _section(pg, a)
    index = pg.evaluate('() => window.app.historyIndex')
    pg.locator(f'[data-lrd-field="fiber-link-cable-{a}-p1"]').select_option('')
    st = _wait(pg, lambda s: _box_links(s, a) is None)
    assert _box_links(st, a) is None
    pg.wait_for_timeout(300)
    assert pg.evaluate('() => window.app.history[window.app.historyIndex].action') == 'Clear Fiber Link'
    assert pg.evaluate('() => window.app.historyIndex') == index + 1
    pg.evaluate('() => window.app.undo()')
    st = _wait(pg, lambda s: _box_links(s, a) == before)
    assert _box_links(st, a) == before
    assert ids['errors'] == []


def test_the_js_and_python_strand_names_agree(page):
    pg, _ids = page
    cables = [{}, {'subunits': True}, {'labels': 'numbers'},
              {'strandNames': {'3': 'SR spare', '5': ' '}}]
    for cable in cables:
        js = pg.evaluate("""(cable) => Array.from({length: 60}, (_, i) =>
            window.app.fiberStrandName(i + 1, cable))""", cable)
        py = [catalog.fiber_strand_name(n, cable) for n in range(1, 61)]
        assert js == py, cable
    js = pg.evaluate("""() => import('/static/js/app-fiber.js').then(m => m.FIBER_COLORS)""")
    assert [tuple(c) for c in js] == list(catalog.FIBER_COLORS)
