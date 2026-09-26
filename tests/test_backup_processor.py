"""Backup processors, loops as their own boxes, box port names, XD copper.

The owner's model (2026-09-25), which matches the vendors' manuals - two
kinds of redundancy that combine into "true full" redundancy:

  1. IN-UNIT redundancy is a LOOP: an SX40's trunk A strings run out of XD A
     and back into XD B on the same port number; NovaStar port backup does
     the same. The far end of a loop is its OWN box, with its own links -
     shown together with the near box as a pair, never bound into it. An
     SX40's loops are independent: "you can do A to B or C to D or A to B
     and C to D".
  2. A BACKUP PROCESSOR is an OPTION on the main: "when we add backup
     processor it's just an option on the primary and then we are capable
     of naming but everything else is automatic". Stored as its name
     (proc['backupUnit']); it is the main again - model, cards, loops -
     each output backing up the main's same output, landing on the same
     boxes' backup inputs: an XD's X2, a CVT10's OPT 2, a CVT4K-S's OPT 3
     and 4, rows in the box's Fiber section. A box with no documented
     backup input (a HELIOS's RS12) gets a twin of its own on the backup.
     Off takes the unit and those rows away; one undo brings them back. A
     chassis mirrored card for card by another unit (the old "Whole unit")
     converts on load - only where it converts cleanly.

A box's links are named by its ports (X1 / X2, OPT 1-4, else Link 1), and
an XD's link may run on copper - Cat6A, Cat6 or Cat5e - with a plain
warning past the kind's 10G length.

Run locally (each session takes its own free port):
    python3 -m pytest tests/test_backup_processor.py -v --browser chromium
"""

import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import processor_catalog as catalog  # noqa: E402

SCRATCH = os.environ.get('LRD_BACKUP_BUILD_DIR')

H16 = 'novastar-card-h-16xrj45-2xfiber'
H4 = 'novastar-card-h-4xfiber'


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# ── helpers ──────────────────────────────────────────────────────────────

def _ok(resp, code=200):
    assert resp.status_code == code, resp.get_data(as_text=True)[:400]
    return resp.get_json()


def _refused(resp):
    assert resp.status_code == 400, resp.get_data(as_text=True)[:400]
    return resp.get_json()['error']


def _state(client):
    return client.get('/api/processors').get_json()


def _raw_proc(client, pid):
    return next(p for p in _state(client)['processors'] if p['id'] == pid)


def _res_proc(client, pid):
    return next(p for p in _state(client)['resolved'] if p['id'] == pid)


def _res_card(client, pid, index=0):
    return next(s['card'] for s in _res_proc(client, pid)['slots']
                if s['index'] == index)


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


def _sx40(client, name=''):
    st = _ok(client.post('/api/processors', json={'deviceId': 'brompton-sx40',
                                                  'name': name}), 201)
    proc = st['processors'][-1]
    return proc['id'], [b['id'] for b in proc['slots'][0]['card']['cvts']]


def _h9(client, cards=(H16,)):
    st = _ok(client.post('/api/processors', json={'deviceId': 'novastar-h9'}), 201)
    pid = st['processors'][-1]['id']
    ids = []
    for index, card in enumerate(cards):
        st = _ok(client.put(f'/api/processors/{pid}/slots/{index}',
                            json={'deviceId': card}))
        proc = next(p for p in st['processors'] if p['id'] == pid)
        ids.append(next(s['card']['id'] for s in proc['slots']
                        if s['index'] == index))
    return pid, ids


def _add_box(client, pid, cid, device='novastar-cvt10', pair=False):
    st = _ok(client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                         json={'deviceId': device, 'pair': pair}), 201)
    proc = next(p for p in st['processors'] if p['id'] == pid)
    card = next(s['card'] for s in proc['slots']
                if s.get('card') and s['card']['id'] == cid)
    return [b['id'] for b in card['cvts']]


def _backup(client, pid, value):
    return client.put(f'/api/processors/{pid}', json={'backupUnit': value})


def _link(client, pid, box, key, body):
    return client.put(f'/api/processors/{pid}/cvts/{box}/fiber-links/{key}',
                      json=body)


def _new_tac(client, strands=12, link=None, **kw):
    body = dict(kind='tac', strands=strands, **kw)
    if link:
        body['link'] = link
    st = _ok(client.post('/api/fiber-cables', json=body), 201)
    return st['fiberCables'][-1]


def _restore(client, project):
    """Through the undo / file-load funnel."""
    _ok(client.put('/api/project', json=project))


# ── A. loops are their own boxes ─────────────────────────────────────────

def test_a_loops_far_box_is_its_own_box_with_its_own_link(client):
    """An SX40's XD B loops back into A's strings (backupOf A) but is NOT
    bound to it: it takes its own X1, and so does a NovaStar backupOf box."""
    pid, xds = _sx40(client)
    _ok(client.put(f'/api/processors/{pid}', json={'redundancy': True}))
    res = [_res_box(client, x) for x in xds]
    assert [r['backupOf'] for r in res] == [None, xds[0], None, xds[2]]
    assert not any('boundTo' in r or 'boundBackup' in r for r in res)
    assert [r['fiberLinkKeys'] for r in res] == [['p1']] * 4
    assert res[1]['linkTitles'] == {'p1': 'X1', 'b1': 'X2'}
    tac = _new_tac(client, 12, link={'boxId': xds[0], 'key': 'p1'})
    _ok(_link(client, pid, xds[1], 'p1', {'cable': tac['id']}))
    assert _raw_box(client, xds[1])['fiberLinks'] == {
        'p1': {'cable': tac['id'], 'strands': [3, 4]}}
    # a NovaStar loop the same way: the backup box on OPT 3 is its own box
    hid, (card,) = _h9(client, (H4,))
    _ok(client.put(f'/api/processors/{hid}/cards/{card}', json={'mode': 'copy-backup'}))
    a, ab = _add_box(client, hid, card, pair=True)
    assert _res_box(client, ab)['backupOf'] == a
    assert _res_box(client, ab)['fiberLinkKeys'] == ['p1']
    assert _res_box(client, a)['fiberLinkKeys'] == ['p1']
    _ok(_link(client, hid, ab, 'p1', {'cable': tac['id']}))
    assert _raw_box(client, ab)['fiberLinks']['p1']['strands'] == [5, 6]
    # the old binding switches are gone, and say where binding lives
    why = _refused(client.put(f'/api/processors/{hid}/cvts/{ab}/fiber',
                              json={'unbound': True}))
    assert 'not bound any more' in why, why


def _beta_project(client):
    """A synthetic 1.4.0-beta file: an SX40 with both loops, TAC A on XD A's
    X1 and - the beta's auto-binding - XD B's feed stored as XD A's b1; XD C
    carries a b1 too while XD D already has its own p1 (so C's b1 drops);
    and the beta's binding markers on the far boxes."""
    project = client.get('/api/project').get_json()
    project['processors'] = []
    project.pop('fiberCables', None)
    _restore(client, project)
    pid, xds = _sx40(client, 'USC SR')
    _ok(client.put(f'/api/processors/{pid}', json={'redundancy': True}))
    project = client.get('/api/project').get_json()
    project['fiberCables'] = [{'id': 'fib5', 'name': 'TAC A', 'kind': 'tac',
                               'strands': 12, 'labels': 'colors',
                               'subunits': False, 'strandNames': {}}]
    boxes = project['processors'][0]['slots'][0]['card']['cvts']
    boxes[0]['fiberLinks'] = {'p1': {'cable': 'fib5', 'strands': [1, 2]},
                              'b1': {'cable': 'fib5', 'strands': [3, 4]}}
    boxes[1]['boundTo'] = xds[0]
    boxes[2]['fiberLinks'] = {'p1': {'cable': 'fib5', 'strands': [5, 6]},
                              'b1': {'cable': 'fib5', 'strands': [7, 8]}}
    boxes[3]['fiberLinks'] = {'p1': {'cable': 'fib5', 'strands': [9, 10]}}
    boxes[3]['unbound'] = False
    project['next_processor_seq'] = max(project.get('next_processor_seq') or 1, 6)
    return pid, xds, project


def test_a_beta_files_loop_links_move_to_the_far_box_and_a_load_is_idempotent(client):
    """USR A b1 = {fib5, [3, 4]} becomes USR B p1 = {fib5, [3, 4]}; C's b1
    is dropped (D's own X1 is set); the beta's boundTo / unbound go; and
    loading the migrated file again changes nothing."""
    pid, xds, project = _beta_project(client)
    _restore(client, project)
    raw = [_raw_box(client, x) for x in xds]
    assert raw[0]['fiberLinks'] == {'p1': {'cable': 'fib5', 'strands': [1, 2]}}
    assert raw[1]['fiberLinks'] == {'p1': {'cable': 'fib5', 'strands': [3, 4]}}
    assert raw[2]['fiberLinks'] == {'p1': {'cable': 'fib5', 'strands': [5, 6]}}
    assert raw[3]['fiberLinks'] == {'p1': {'cable': 'fib5', 'strands': [9, 10]}}
    assert not any('boundTo' in r or 'unbound' in r for r in raw), raw
    once = client.get('/api/project').get_json()
    _restore(client, copy.deepcopy(once))
    twice = client.get('/api/project').get_json()
    assert twice['processors'] == once['processors']
    assert twice['fiberCables'] == once['fiberCables']


def test_the_migration_runs_on_the_file_open_funnel_too():
    """The same move, straight through the catalog - the function both load
    funnels call - on a beta project that was never near a server."""
    proc = catalog.new_processor('brompton-sx40', 1)
    proc['redundancy'] = True
    a, b = proc['slots'][0]['card']['cvts'][:2]
    a['fiberLinks'] = {'p1': {'cable': 'fib9', 'strands': [1, 2]},
                       'b1': {'cable': 'fib9', 'strands': [3, 4]}}
    project = {'processors': [proc],
               'fiberCables': [{'id': 'fib9', 'kind': 'tac', 'strands': 12}]}
    assert catalog.migrate_backup_processors(project) is True
    assert a['fiberLinks'] == {'p1': {'cable': 'fib9', 'strands': [1, 2]}}
    assert b['fiberLinks'] == {'p1': {'cable': 'fib9', 'strands': [3, 4]}}
    before = copy.deepcopy(project)
    assert catalog.migrate_backup_processors(project) is False
    assert project == before


# ── B. an SX40's loops are independent ───────────────────────────────────

def test_an_sx40_running_a_to_b_alone_leaves_c_and_d_primaries(client):
    """redundancyPairs ['A']: B loops A's strings (backupOf, 1 backed by
    11); C and D are plain primaries with their own boxes; 30 of 40 usable;
    the statement says so; and the port count takes C's and D's sockets as
    primaries while B carries A's returns."""
    pid, xds = _sx40(client)
    st = _ok(client.put(f'/api/processors/{pid}',
                        json={'redundancy': True, 'redundancyPairs': ['A']}))
    assert _raw_proc(client, pid)['redundancyPairs'] == ['A']
    proc = next(p for p in st['resolved'] if p['id'] == pid)
    assert proc['redundancyPairs'] == ['A']
    assert proc['redundancyPairMarks'] == ['A', 'C']
    card = proc['slots'][0]['card']
    assert [b['backupOf'] for b in card['cvts']] == [None, xds[0], None, None]
    assert card['redundancyShape']['usable'] == 30
    assert card['redundancyShape']['pairs'] == [0]
    assert proc['redundancyPairing']['statement'] == 'A backs up to B; C and D are primaries.'
    ports = {p['number']: p for p in card['ports']}
    assert ports[1]['backedBy']['port'] == 11 and ports[11]['backsUp']['port'] == 1
    assert 'backedBy' not in ports[21] and 'backsUp' not in ports[31]
    # the counts: 3 on A (returns on B) and 3 on each of C and D
    res = _ok(client.post('/api/port-assignments/place-overflow', json={
        'layerId': 'Wall', 'cardId': card['id'],
        'screens': [{'layerId': 'Wall', 'name': 'Wall', 'ports': 3}]}))['resolution']
    summary = next(c for c in res['cards'] if c['cardId'] == card['id'])
    per_box = summary['boxes']
    assert [per_box[x]['taken'] for x in xds] == [3, 3, 0, 0], per_box
    res = _ok(client.post('/api/port-assignments/place-overflow', json={
        'layerId': 'Wall2', 'cardId': card['id'], 'firstPort': 21, 'lastPort': 40,
        'screens': [{'layerId': 'Wall', 'name': 'Wall', 'ports': 3},
                    {'layerId': 'Wall2', 'name': 'Wall2', 'ports': 14}]}))['resolution']
    summary = next(c for c in res['cards'] if c['cardId'] == card['id'])
    assert [summary['boxes'][x]['taken'] for x in xds] == [3, 3, 10, 4], summary['boxes']
    # C to D alone the other way round
    st = _ok(client.put(f'/api/processors/{pid}', json={'redundancyPairs': ['C']}))
    proc = next(p for p in st['resolved'] if p['id'] == pid)
    assert proc['redundancyPairing']['statement'] == 'C backs up to D; A and B are primaries.'
    card = proc['slots'][0]['card']
    assert [b['backupOf'] for b in card['cvts']] == [None, None, None, xds[2]]


def test_the_legacy_redundancy_true_reads_as_both_loops_and_pairs_are_checked(client):
    pid, xds = _sx40(client)
    _ok(client.put(f'/api/processors/{pid}', json={'redundancy': True}))
    proc = _res_proc(client, pid)
    assert 'redundancyPairs' not in _raw_proc(client, pid)
    assert proc['redundancyPairs'] == ['A', 'C']
    assert proc['redundancyPairing']['statement'] == 'A backs up to B and C backs up to D.'
    assert [b['backupOf'] for b in proc['slots'][0]['card']['cvts']] == \
        [None, xds[0], None, xds[2]]
    # both named stores nothing - it is what absence means
    _ok(client.put(f'/api/processors/{pid}', json={'redundancyPairs': ['A', 'C']}))
    assert 'redundancyPairs' not in _raw_proc(client, pid)
    assert 'must name the pairs' in _refused(client.put(
        f'/api/processors/{pid}', json={'redundancyPairs': ['B']}))
    hid, _cards = _h9(client)
    assert 'no trunk pairs' in _refused(client.put(
        f'/api/processors/{hid}', json={'redundancyPairs': ['A']}))
    # the S8 pairs adjacent too, but has no lettered trunk pairs to pick
    st = _ok(client.post('/api/processors', json={'deviceId': 'brompton-s8'}), 201)
    s8 = st['processors'][-1]['id']
    assert 'no trunk pairs' in _refused(client.put(
        f'/api/processors/{s8}', json={'redundancyPairs': ['A']}))


# ── C. the backup processor, an option on the main ───────────────────────

def test_an_sx40s_backup_processor_is_a_named_option_that_feeds_each_xds_x2(client):
    """Switched on, the backup is NOT a processor record: the main stores
    its name ('' reads "<main> BU"), every XD on the main gains X2, the
    in-unit loops and the data map are the main's as they were, and the
    name is the one thing typed."""
    main, xds = _sx40(client, 'USC SR Main')
    _ok(client.put(f'/api/processors/{main}', json={'redundancy': True}))
    before = [p['id'] for p in _state(client)['processors']]
    st = _ok(_backup(client, main, {}))
    assert [p['id'] for p in st['processors']] == before
    assert _raw_proc(client, main)['backupUnit'] == {'name': ''}
    rmain = _res_proc(client, main)
    assert rmain['backupUnit']['name'] == 'USC SR Main BU'
    assert rmain['backupUnit']['boxes'] == []
    boxes = rmain['slots'][0]['card']['cvts']
    for box in boxes:
        assert box['fiberLinkKeys'] == ['p1', 'b1'] and box['backupInputs'] is True
        assert [box['linkTitles'][k] for k in box['fiberLinkKeys']] == ['X1', 'X2']
    # the loops and the data map are untouched: A-1 still returns on B-1
    ports = {p['number']: p for p in rmain['slots'][0]['card']['ports']}
    assert ports[1]['backedBy']['port'] == 11 and ports[1]['backedBy']['processorId'] == main
    assert [b['backupOf'] for b in boxes] == [None, xds[0], None, xds[2]]
    # named, and a blank name hands it back to the default
    _ok(_backup(client, main, {'name': 'USC SR BU'}))
    assert _res_proc(client, main)['backupUnit']['name'] == 'USC SR BU'
    assert _res_proc(client, main)['backupUnit']['typedName'] == 'USC SR BU'
    _ok(_backup(client, main, {'name': '  '}))
    assert _res_proc(client, main)['backupUnit']['name'] == 'USC SR Main BU'
    _ok(_backup(client, main, {'name': 'USC SR BU'}))
    # a switch-on that names nothing keeps the typed name
    _ok(_backup(client, main, True))
    assert _raw_proc(client, main)['backupUnit'] == {'name': 'USC SR BU'}
    # X2 takes a fiber of its own - its own cable and strands
    tac = _new_tac(client, 12, link={'boxId': xds[0], 'key': 'p1'})
    tac_b = _new_tac(client, 12, link={'boxId': xds[0], 'key': 'b1'})
    assert _raw_box(client, xds[0])['fiberLinks'] == {
        'p1': {'cable': tac['id'], 'strands': [1, 2]},
        'b1': {'cable': tac_b['id'], 'strands': [1, 2]}}
    assert _res_box(client, xds[0])['fiberLinks']['b1']['strands'] == [1, 2]
    # the far box of the loop has its own X1 and X2
    _ok(_link(client, main, xds[1], 'b1', {'cable': tac_b['id']}))
    assert _raw_box(client, xds[1])['fiberLinks']['b1'] == {'cable': tac_b['id'], 'strands': [3, 4]}


def test_switching_the_backup_off_takes_its_rows_and_one_undo_brings_them_back(client):
    main, xds = _sx40(client, 'MAIN')
    _ok(_backup(client, main, {'name': 'BU'}))
    tac = _new_tac(client, 12, link={'boxId': xds[0], 'key': 'p1'})
    tac_b = _new_tac(client, 6, link={'boxId': xds[0], 'key': 'b1'})
    before = client.get('/api/project').get_json()
    st = _ok(_backup(client, main, None))
    assert 'backupUnit' not in _raw_proc(client, main)
    assert _res_proc(client, main)['backupUnit'] is None
    assert _raw_box(client, xds[0])['fiberLinks'] == {'p1': {'cable': tac['id'], 'strands': [1, 2]}}
    assert all(b['fiberLinkKeys'] == ['p1'] for b in _res_card(client, main)['cvts'])
    # TAC B went with its last link
    assert tac_b['id'] not in [c['id'] for c in st['fiberCables']]
    _restore(client, before)
    assert _raw_proc(client, main)['backupUnit'] == {'name': 'BU'}
    assert _raw_box(client, xds[0])['fiberLinks']['b1'] == {'cable': tac_b['id'], 'strands': [1, 2]}
    assert tac_b['id'] in [c['id'] for c in _state(client)['fiberCables']]
    # the switch's refusals
    assert 'must be true, null or {name}' in _refused(_backup(client, main, 'yes'))
    assert 'must be text' in _refused(_backup(client, main, {'name': 5}))
    why = _refused(client.put(f'/api/processors/{main}', json={'backupProcessorId': 'proc9'}))
    assert 'option on its main' in why, why


def test_a_novastar_backup_lands_on_opt_2_and_a_cvt4k_on_opt_3_and_4(client):
    main, (mc,) = _h9(client, (H16,))
    cvt10 = _add_box(client, main, mc, 'novastar-cvt10')[0]
    _ok(_backup(client, main, {}))
    res = _res_box(client, cvt10)
    assert res['fiberLinkKeys'] == ['p1', 'b1']
    assert [res['linkTitles'][k] for k in res['fiberLinkKeys']] == ['OPT 1', 'OPT 2']
    assert _res_proc(client, main)['backupUnit']['boxes'] == []
    main2, (mc2,) = _h9(client, (H16,))
    big = _add_box(client, main2, mc2, 'novastar-cvt4k-s')[0]
    _ok(_backup(client, main2, {}))
    res = _res_box(client, big)
    assert res['fiberLinkKeys'] == ['p1', 'p2', 'b1', 'b2']
    assert [res['linkTitles'][k] for k in res['fiberLinkKeys']] == \
        ['OPT 1', 'OPT 2', 'OPT 3', 'OPT 4']
    tac = _new_tac(client, 12, link={'boxId': big, 'key': 'p1'})
    _ok(_link(client, main2, big, 'b2', {'cable': tac['id']}))
    assert _raw_box(client, big)['fiberLinks']['b2'] == {'cable': tac['id'], 'strands': [3, 4]}
    # a box that documents no backup input is twinned instead, and keeps
    # its neutral names
    assert catalog.fiber_link_title('p1', catalog.get_device('novastar-cvt8-5g')) == 'Link 1'
    assert catalog.fiber_link_title('p2', catalog.get_device('megapixel-rs12')) == 'Link 2'


def test_a_helios_backup_keeps_its_own_switches(client):
    """Megapixel: a backup HELIOS keeps its OWN switches - the backup unit
    lists a twin of each RS12 (counted as hardware) and the main's RS12
    gains no backup row."""
    st = _ok(client.post('/api/processors', json={'deviceId': 'megapixel-helios-8k',
                                                  'name': 'HX'}), 201)
    main = st['processors'][-1]['id']
    mc = st['processors'][-1]['slots'][0]['card']['id']
    rs12 = _add_box(client, main, mc, 'megapixel-rs12')[0]
    _ok(_backup(client, main, {}))
    unit = _res_proc(client, main)['backupUnit']
    assert unit['name'] == 'HX BU'
    assert [(b['mirrorOf'], b['deviceId']) for b in unit['boxes']] == [(rs12, 'megapixel-rs12')]
    assert _res_box(client, rs12)['fiberLinkKeys'] == ['p1']
    assert _res_box(client, rs12)['linkTitles']['p1'] == 'Link 1'


def _legacy_pair(client, partner_name='H9 BACKUP'):
    """The old "Whole unit": two H9s, the main's two cards 1:1 onto the
    partner's slot for slot, each with a CVT10 on OPT 1, the partner's
    box carrying its own fiber."""
    project = client.get('/api/project').get_json()
    project['processors'] = []
    project.pop('fiberCables', None)
    project.pop('port_assignments', None)
    _restore(client, project)
    main, mcards = _h9(client, (H16, H16))
    back, bcards = _h9(client, (H16, H16))
    _ok(client.put(f'/api/processors/{back}', json={'name': partner_name}))
    mbox = _add_box(client, main, mcards[0])[0]
    bbox = _add_box(client, back, bcards[0])[0]
    tac = _new_tac(client, 12, link={'boxId': bbox, 'key': 'p1'})
    _ok(client.put(f'/api/processors/{main}', json={'redundancy': True}))
    for mc, bc in zip(mcards, bcards):
        _ok(client.put(f'/api/processors/{main}/cards/{mc}', json={'backupCardId': bc}))
    return main, back, mbox, bbox, bcards, tac


def _as_old_file(client):
    """The project as a build before the backup-processor option saved
    it: no processor carries pairingsPerCard."""
    project = client.get('/api/project').get_json()
    for proc in project['processors']:
        proc.pop('pairingsPerCard', None)
    return project


def test_a_chassis_mirrored_card_for_card_converts_to_its_backup_processor(client):
    """Today's derived whole-unit pairing converts on load: the partner
    becomes the main's backup unit under its own name, its record goes,
    its box's fiber moves onto the main box's OPT 2, and the main's
    in-unit bar reads Off. Loading again changes nothing."""
    main, back, mbox, bbox, _bc, tac = _legacy_pair(client)
    # made in this build, the pairing is per card by choice and stays
    _restore(client, client.get('/api/project').get_json())
    assert back in [p['id'] for p in _state(client)['processors']]
    assert 'backupUnit' not in _raw_proc(client, main)
    _restore(client, _as_old_file(client))
    ids = [p['id'] for p in _state(client)['processors']]
    assert back not in ids and main in ids
    raw = _raw_proc(client, main)
    assert raw['backupUnit'] == {'name': 'H9 BACKUP'} and raw['redundancy'] is False
    assert all('backupCardId' not in s['card'] for s in raw['slots'] if s.get('card'))
    assert _raw_box(client, mbox)['fiberLinks'] == {'b1': {'cable': tac['id'], 'strands': [1, 2]}}
    assert _res_proc(client, main)['backupUnit']['name'] == 'H9 BACKUP'
    assert tac['id'] in [c['id'] for c in _state(client)['fiberCables']]
    once = client.get('/api/project').get_json()
    _restore(client, copy.deepcopy(once))
    again = client.get('/api/project').get_json()
    assert again['processors'] == once['processors']


def test_a_legacy_pairing_that_would_lose_something_is_left_exactly_as_it_is(client):
    """A port name typed on the partner has nowhere to go on a derived
    backup unit, so the file stays exactly as it was - and a 1:1 inside one
    chassis is in-unit redundancy, which stays too."""
    main, back, _mbox, _bbox, bcards, _tac = _legacy_pair(client)
    _ok(client.put(f'/api/processors/{back}/cards/{bcards[1]}/ports/3',
                   json={'name': 'SPARE'}))
    before = _as_old_file(client)
    _restore(client, copy.deepcopy(before))
    after = client.get('/api/project').get_json()
    for proc in after['processors']:
        assert proc.pop('pairingsPerCard') is True
    assert after['processors'] == before['processors']
    # a hand-added, unpaired second SX40 is a unit of its own and stays
    a, _ = _sx40(client, 'USC SR')
    b, _ = _sx40(client, 'USC SR BU')
    _restore(client, _as_old_file(client))
    ids = [p['id'] for p in _state(client)['processors']]
    assert a in ids and b in ids
    # a card paired 1:1 with another card of the SAME chassis stays
    solo, cards = _h9(client, (H16, H16))
    _ok(client.put(f'/api/processors/{solo}', json={'redundancy': True}))
    _ok(client.put(f'/api/processors/{solo}/cards/{cards[0]}', json={'backupCardId': cards[1]}))
    _restore(client, _as_old_file(client))
    raw = _raw_proc(client, solo)
    assert 'backupUnit' not in raw
    assert raw['slots'][0]['card']['backupCardId'] == cards[1]


# ── E. copper on an XD's link ────────────────────────────────────────────

def test_an_xd_link_may_be_copper_and_nothing_else_takes_it(client):
    pid, xds = _sx40(client)
    _ok(_link(client, pid, xds[0], 'p1', {'copper': 'Cat6', 'ft': 150}))
    assert _raw_box(client, xds[0])['fiberLinks'] == {'p1': {'copper': 'Cat6', 'ft': 150}}
    assert _res_box(client, xds[0])['fiberLinks']['p1'] == {'copper': 'Cat6', 'ft': 150}
    assert _res_box(client, xds[0])['copperLinks'] is True
    # over its 100 ft is said, not refused; blank is no length
    _ok(_link(client, pid, xds[1], 'p1', {'copper': 'Cat6A', 'ft': None}))
    assert _raw_box(client, xds[1])['fiberLinks'] == {'p1': {'copper': 'Cat6A'}}
    assert 'one of Cat6A, Cat6, Cat5e' in _refused(
        _link(client, pid, xds[0], 'p1', {'copper': 'Cat7'}))
    hid, (card,) = _h9(client, (H16,))
    box = _add_box(client, hid, card)[0]
    assert 'fiber only' in _refused(_link(client, hid, box, 'p1', {'copper': 'Cat6A'}))
    # the XD-S and XD-T are fiber only by their datasheets
    assert not catalog.get_device('brompton-xd-s').get('copperLinks')
    assert not catalog.get_device('brompton-xd-t').get('copperLinks')
    # a cable picked later replaces the copper; clearing clears either
    tac = _new_tac(client, 12)
    _ok(_link(client, pid, xds[0], 'p1', {'cable': tac['id']}))
    assert _raw_box(client, xds[0])['fiberLinks']['p1'] == {'cable': tac['id'], 'strands': [1, 2]}
    _ok(_link(client, pid, xds[1], 'p1', {'cable': None}))
    assert 'fiberLinks' not in _raw_box(client, xds[1])
    assert [k for k, _ft in catalog.COPPER_LINK_KINDS] == ['Cat6A', 'Cat6', 'Cat5e']
    assert dict(catalog.COPPER_LINK_KINDS) == {'Cat6A': 196, 'Cat6': 100, 'Cat5e': 98}


# ── the browser: the ⚙, the grouped Fiber section, the binder, the pull ──

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

# USC SR Main: an SX40 with both loops and its backup processor on (named
# USC SR BU); TAC A on XD A's X1 and TAC B on its X2; XD C's X1 on Cat6 at
# 150 ft (past its 100). HX: a HELIOS Standard 8K with one RS12 and a
# backup processor of its own. WALL, a Brompton wall, takes A's and C's
# primaries.
SEED_JS = """async () => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.fiberCables;
    delete proj.pullSheetEdits;
    await j('PUT', '/api/project', proj);
    const wall = await j('POST', '/api/layer/add', {name: 'WALL', columns: 12, rows: 30,
                                                     cabinet_width: 200, cabinet_height: 200});
    await j('PUT', `/api/layer/${wall.id}`, {processorType: 'brompton'});
    let st = await j('POST', '/api/processors', {deviceId: 'brompton-sx40', name: 'USC SR Main'});
    const sx = st.processors[0];
    const xds = sx.slots[0].card.cvts.map(b => b.id);
    await j('PUT', `/api/processors/${sx.id}`, {redundancy: true, backupUnit: {name: 'USC SR BU'}});
    await j('POST', '/api/fiber-cables', {kind: 'tac', strands: 12, ft: 500, connector: 'ST',
                                          link: {boxId: xds[0], key: 'p1'}});
    await j('POST', '/api/fiber-cables', {kind: 'tac', strands: 12, ft: 500, connector: 'ST',
                                          link: {boxId: xds[0], key: 'b1'}});
    await j('PUT', `/api/processors/${sx.id}/cvts/${xds[2]}/fiber-links/p1`, {copper: 'Cat6', ft: 150});
    st = await j('POST', '/api/processors', {deviceId: 'megapixel-helios-8k', name: 'HX'});
    const hx = st.processors[1];
    st = await j('POST', `/api/processors/${hx.id}/cards/${hx.slots[0].card.id}/cvts`,
                 {deviceId: 'megapixel-rs12'});
    const rs12 = st.processors[1].slots[0].card.cvts[0].id;
    await j('PUT', `/api/processors/${hx.id}/cvts/${rs12}`, {location: 'FOH'});
    await j('PUT', `/api/processors/${hx.id}`, {backupUnit: {}});
    const app = window.app;
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('backup_setup');
    app.selectLayer(app.project.layers[0]);
    await app.refreshProcessors();
    await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
        {layerId: String(wall.id), cardId: sx.slots[0].card.id, lastIndex: 19});
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    for (const id of xds) {
        try { localStorage.removeItem(`lrd_data_cable_sheet_cvt_${id}`); } catch (e) { /* none */ }
    }
    app.renderLayers();
    app.renderHardwareDock();
    app.resetHistory('Backup Seed');
    return {sx: sx.id, xds, hx: hx.id, rs12, wall: wall.id};
}"""

OPEN_GEAR_JS = """(popId) => {
    const gear = document.querySelector(`[data-hwpop="${popId}"]`);
    if (!gear) return false;
    const pop = document.getElementById('hw-gear-popover');
    const open = !!(pop && pop.style.display !== 'none'
        && window.app._hwPopover && window.app._hwPopover.id === popId);
    if (!open) gear.click();
    const after = document.getElementById('hw-gear-popover');
    return !!(after && after.style.display !== 'none');
}"""

SHEET_JS = """([boxId, others]) => {
    for (const id of others) {
        try { localStorage.removeItem(`lrd_data_cable_sheet_cvt_${id}`); } catch (e) { /* none */ }
    }
    try { localStorage.setItem(`lrd_data_cable_sheet_cvt_${boxId}`, '1'); } catch (e) { /* none */ }
    window.app.renderHardwareDock();
    const sec = document.querySelector(`[data-lrd-fiber-row="${boxId}"]`);
    if (!sec) return null;
    sec.scrollIntoView({block: 'center'});
    return {
        caption: sec.querySelector('.hw-dock-cable-fiber-cap').textContent,
        rows: [...sec.querySelectorAll('.hw-dock-fiber-link')].map(r => ({
            role: r.querySelector('.hw-dock-fiber-role').textContent,
            link: r.dataset.lrdFiberLink,
            backup: r.classList.contains('hw-dock-fiber-link-backup'),
            value: r.querySelector('select').value,
            options: [...r.querySelector('select').options].map(o => o.textContent),
            ft: (r.querySelector('input.hw-dock-cable-ft') || {}).value || null,
            warn: (r.querySelector('.hw-dock-fiber-warn') || {}).textContent || null,
        })),
    };
}"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 1000})
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


def _shot(pg, locator, name):
    """A render for the owner, only where a scratch folder is named."""
    if SCRATCH:
        os.makedirs(SCRATCH, exist_ok=True)
        locator.screenshot(path=os.path.join(SCRATCH, name))


def test_the_sx40_gear_has_the_two_loops_and_the_backup_processor_switch(page):
    """The ⚙: REDUNDANCY as two switches, "A to B" and "C to D" - either
    alone, both the old On - each click one request and one history entry;
    under them BACKUP PROCESSOR, On, with its name; and the main's header
    carries "+ BU: USC SR BU"."""
    pg, ids = page
    sx = ids['sx']
    assert pg.evaluate(OPEN_GEAR_JS, f'proc-{sx}')
    pg.wait_for_timeout(300)
    loops = f'#hw-gear-popover [data-lrd-field="processor-redundancy-{sx}"]'
    read = """(sel) => [...document.querySelectorAll(sel + ' button')].map(b =>
        [b.textContent, b.getAttribute('aria-pressed')])"""
    assert pg.evaluate(read, loops) == [['A to B', 'true'], ['C to D', 'true']]
    bu = f'#hw-gear-popover [data-lrd-field="processor-backup-{sx}"]'
    assert pg.locator(bu + ' .hw-pop-seg-on').text_content() == 'On'
    name = pg.locator(f'[data-lrd-field="processor-backup-name-{sx}"]')
    assert name.input_value() == 'USC SR BU'
    assert name.get_attribute('placeholder') == 'USC SR Main BU'
    _shot(pg, pg.locator('#hw-gear-popover'), 'sx40-gear-popover.png')
    pill = pg.evaluate("""(sx) => {
        const strip = document.querySelector(`[data-lrd-field="processor-name-${sx}"]`);
        const p = strip.closest('.hw-dock-proc-name').querySelector('.hw-dock-backuppill');
        return p ? [p.textContent, getComputedStyle(p).color] : null;
    }""", sx)
    assert pill == ['+ BU: USC SR BU', 'rgb(240, 212, 138)'], pill
    # A to B off: C to D alone
    index = pg.evaluate('() => window.app.historyIndex')
    pg.locator(loops + ' [data-pair="A"]').click()
    pg.wait_for_timeout(900)
    assert pg.evaluate('() => window.app.history[window.app.historyIndex].action') == 'Set Redundancy Loops'
    assert pg.evaluate('() => window.app.historyIndex') == index + 1
    stored = pg.evaluate("(sx) => window.app.project.processors.find(p => p.id === sx)", sx)
    assert stored['redundancy'] is True and stored['redundancyPairs'] == ['C'], stored
    assert pg.evaluate(OPEN_GEAR_JS, f'proc-{sx}')
    assert pg.evaluate(read, loops) == [['A to B', 'false'], ['C to D', 'true']]
    # C to D off too: redundancy off; A to B back on alone
    pg.locator(loops + ' [data-pair="C"]').click()
    pg.wait_for_timeout(900)
    stored = pg.evaluate("(sx) => window.app.project.processors.find(p => p.id === sx)", sx)
    assert stored['redundancy'] is False, stored
    assert pg.evaluate(OPEN_GEAR_JS, f'proc-{sx}')
    pg.locator(loops + ' [data-pair="A"]').click()
    pg.wait_for_timeout(900)
    stored = pg.evaluate("(sx) => window.app.project.processors.find(p => p.id === sx)", sx)
    assert stored['redundancy'] is True and stored['redundancyPairs'] == ['A'], stored
    # three undos: both loops again
    for _ in range(3):
        pg.evaluate('() => window.app.undo()')
        pg.wait_for_timeout(700)
    stored = pg.evaluate("(sx) => window.app.project.processors.find(p => p.id === sx)", sx)
    assert stored['redundancy'] is True and 'redundancyPairs' not in stored, stored
    pg.keyboard.press('Escape')
    assert ids['errors'] == []


def test_a_loops_sheet_shows_the_pair_near_box_first_with_x1_and_x2(page):
    """XD B's ≡ sheet, opened alone, shows the loop as ONE section - "Fiber
    · Tessera XD A ↔ Tessera XD B (loop)" - XD A's rows first, each named by
    its box and port, the backup unit's X2 rows tinted; XD C's X1 runs on
    Cat6 at 150 ft with the plain warning."""
    pg, ids = page
    a, b, c, d = ids['xds']
    sec = pg.evaluate(SHEET_JS, [b, ids['xds']])
    assert sec['caption'] == 'Fiber · Tessera XD A ↔ Tessera XD B (loop)', sec
    assert [(r['role'], r['backup']) for r in sec['rows']] == [
        ('Tessera XD A · X1', False), ('Tessera XD A · X2', True),
        ('Tessera XD B · X1', False), ('Tessera XD B · X2', True)], sec
    assert [r['link'] for r in sec['rows']] == [f'{a}:p1', f'{a}:b1', f'{b}:p1', f'{b}:b1']
    assert 'Cat6A copper' in sec['rows'][2]['options'], sec['rows'][2]['options']
    # an empty X2 offers its X1's cable on top, named, with a gap under it,
    # and the rest of the list keeps its own order ("that reads as
    # confusing ... maybe we do this with a gap", owner 2026-09-25)
    for i in (1, 3):
        x1, x2 = sec['rows'][i - 1], sec['rows'][i]
        if x2['value'] or not x1['value']:
            continue
        opts = x2['options']
        assert opts[0].endswith(' · same as X1') and opts[1] == '──────────', opts
        rest = [o for o in opts[2:] if o.startswith(('TAC', 'MTP'))]
        assert rest == sorted(rest), opts
    pg.wait_for_timeout(300)
    _shot(pg, pg.locator(f'[data-lrd-fiber-row="{b}"]'), 'xd-loop-fiber-section.png')
    sec = pg.evaluate(SHEET_JS, [c, ids['xds']])
    assert sec['caption'] == 'Fiber · Tessera XD C ↔ Tessera XD D (loop)', sec
    row = sec['rows'][0]
    assert (row['role'], row['value'], row['ft'], row['warn']) == \
        ('Tessera XD C · X1', 'cu:Cat6', '150', 'Cat6 runs 100 ft max at 10G'), row
    # the copper length commits as one entry
    pg.locator(f'[data-lrd-field="fiber-copper-ft-{c}-p1"]').fill('90')
    pg.locator(f'[data-lrd-field="fiber-copper-ft-{c}-p1"]').press('Enter')
    pg.wait_for_timeout(900)
    assert pg.evaluate('() => window.app.history[window.app.historyIndex].action') == 'Set Copper Length'
    sec = pg.evaluate(SHEET_JS, [c, ids['xds']])
    assert sec['rows'][0]['ft'] == '90' and sec['rows'][0]['warn'] is None, sec
    pg.evaluate('() => window.app.undo()')
    pg.wait_for_timeout(900)
    pg.evaluate(SHEET_JS, [None, ids['xds']])
    assert ids['errors'] == []


def test_the_binder_and_the_pull_sheet_name_the_ports_and_count_the_backup(page):
    """The box summary reads "TAC A 1-2 · X2 TAC B 1-2" and "X1 Cat6 150'
    (…)"; a strand map names the box and its port; the loop's far box is
    marked "loop of"; the backup unit is its own column, "USC SR BU · backup
    of USC SR Main"; and the pull sheet lists every processor by model -
    the main and, marked, its backup ("List mains and backups") - the
    HELIOS's backup its own RS12, and no second XD."""
    pg, ids = page
    a, b, c, d = ids['xds']
    out = pg.evaluate("""(ids) => {
        const app = window.app;
        const box = (id) => app._dockFindCvt(id).cvt;
        const sx = app._processorsResolved.find(p => p.id === ids.sx);
        const seen = [];
        const keep = app._bTableLines;
        app._bTableLines = (book, spec) => { seen.push(spec); return []; };
        app._bKvLines = (book, title, pairs) => { seen.push({title, pairs}); return []; };
        const book = {list: {hardware: []}};
        const group = app._bProcessorGroup(book, sx);
        const bu = app._bBackupUnitGroup(book, sx, group.name);
        app._bTableLines = keep;
        const maps = app._bStrandMaps(sx);
        return {
            a: app.fiberLinkSummary(box(ids.xds[0])),
            c: app.fiberLinkSummary(box(ids.xds[2])),
            boxes: (seen.find(t => t.title === 'Breakout boxes') || {}).rows.map(r => r.cells[0]),
            red: app._bRedundancyText(sx),
            bu: bu.name,
            map: maps[0].rows.slice(0, 3).map(r => r.cells),
            cols: maps[0].cols.map(c => c.title),
        };
    }""", ids)
    assert out['a'] == 'TAC A 1-2 · X2 TAC B 1-2', out
    assert out['c'] == "X1 Cat6 150' (Cat6 runs 100 ft max at 10G)", out
    assert out['boxes'] == ['Tessera XD A', 'Tessera XD B · loop of Tessera XD A',
                            'Tessera XD C', 'Tessera XD D · loop of Tessera XD C'], out
    assert out['red'] == 'On · backed up by USC SR BU', out
    assert out['bu'] == 'USC SR BU · backup of USC SR Main', out
    assert out['cols'] == ['strand', 'link'], out
    assert out['map'] == [['1 Blue', 'Tessera XD A · X1'], ['2 Orange', 'Tessera XD A · X1'],
                          ['3 Green', 'spare']], out
    rows = pg.evaluate("""() => {
        const app = window.app;
        app._circuitTailCache = null;
        return JSON.parse(JSON.stringify(app.buildPullList())).totals
            .map(r => [r.type, r.length, r.qty, r.label, r.notes]);
    }""")
    # every processor, mains and backups, counted by model with its names
    assert ['Tessera SX40', 'EA', 2, 'USC SR Main, USC SR BU (backup)', ''] in rows, rows
    assert ['HELIOS Standard 8K / 8K Extreme', 'EA', 2, 'HX, HX BU (backup)', ''] in rows, rows
    assert ['RS12 / MSM4214X', 'EA', 2, 'RS12 / MSM4214X, HX BU', ''] in rows, rows
    xd_on = sum(r[2] for r in rows if r[0] == 'Tessera XD')
    cat6 = [r for r in rows if r[0] == 'Cat6']
    assert cat6 == [['Cat6', "150'", 1, 'Tessera XD C (X1)', 'Cat6 runs 100 ft max at 10G']], rows
    # the backup unit off: the same XDs, and no SX40 row
    pg.evaluate("""async (sx) => { await window.app._processorRequest(
        `/api/processors/${sx}`, 'PUT', {backupUnit: null}, 'Remove Backup Processor'); }""", ids['sx'])
    pg.wait_for_timeout(600)
    rows = pg.evaluate("""() => { window.app._circuitTailCache = null;
        return window.app.buildPullList().totals.map(r => [r.type, r.qty, r.label]); }""")
    assert sum(r[1] for r in rows if r[0] == 'Tessera XD') == xd_on, rows
    assert [r for r in rows if r[0] == 'Tessera SX40'] == [['Tessera SX40', 1, 'USC SR Main']], rows
    pg.evaluate('() => window.app.undo()')
    pg.wait_for_timeout(900)
    assert pg.evaluate("(sx) => window.app.project.processors.find(p => p.id === sx).backupUnit",
                       ids['sx']) == {'name': 'USC SR BU'}
    assert ids['errors'] == []


def test_the_js_and_python_copper_kinds_agree(page):
    pg, _ids = page
    js = pg.evaluate("() => import('/static/js/app-fiber.js').then(m => m.COPPER_LINK_KINDS)")
    assert [tuple(k) for k in js] == list(catalog.COPPER_LINK_KINDS)
